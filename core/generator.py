import carla
import numpy as np
import math
from scipy.interpolate import interp1d

# ============================================================
# 坐标系约定（最终与 Anchor3DLane/OpenLane 预处理兼容）
# ------------------------------------------------------------
# Ground/Ego(我们生成 lane 用的地面车体系):
#   x: 右
#   y: 前
#   z: 上
#
# Apollo Camera (预处理里 extrinsic 对应的相机系):
#   x: 右
#   y: 下
#   z: 前
#
# OpenLane Camera (预处理里 json 的 xyz 所在相机系):
#   x: 前
#   y: 左
#   z: 上
#
# 预处理做的是:
#   lane_apollo = T_open->apollo * lane_open
#   lane_ground = E_apollo_cam_to_ground * lane_apollo
# 所以我们必须在 json 里存 lane_open，并存 E_apollo_cam_to_ground。
# ============================================================

def _mat44_from_carla_transform(tf: carla.Transform) -> np.ndarray:
    """CARLA Transform -> 4x4 (float64)"""
    return np.array(tf.get_matrix(), dtype=np.float64)

def _swap_vehicle_to_ground() -> np.ndarray:
    """
    CARLA Vehicle frame 通常是:
      X: forward, Y: right, Z: up
    我们的 ground/ego 定义为:
      x: right, y: forward, z: up
    所以 ground = S_v2g * vehicle
    即: x=Y, y=X, z=Z
    """
    S = np.eye(4, dtype=np.float64)
    S[0, 0] = 0.0; S[0, 1] = 1.0
    S[1, 0] = 1.0; S[1, 1] = 0.0
    # z 不变
    return S

def _carla_cam_to_apollo_cam() -> np.ndarray:
    """
    CARLA Camera frame(常见):
      X: forward, Y: right, Z: up
    Apollo Camera frame(标准 pinhole 常用):
      x: right, y: down, z: forward

    映射：
      x_apollo =  Y_carla
      y_apollo = -Z_carla
      z_apollo =  X_carla
    """
    R = np.eye(4, dtype=np.float64)
    R[0, :] = [0, 1, 0, 0]   # x_apollo
    R[1, :] = [0, 0, -1, 0]  # y_apollo
    R[2, :] = [1, 0, 0, 0]   # z_apollo
    return R

def _T_apollo_to_openlane() -> np.ndarray:
    """
    这就是你预处理里写的 "apollo camera -> openlane camera" 那个矩阵。
    注意：预处理里实际用的是 inv(T_apollo_to_openlane)，也就是 T_open->apollo。
    """
    T = np.eye(4, dtype=np.float64)
    T[0, :3] = [0, 0, 1]
    T[1, :3] = [-1, 0, 0]
    T[2, :3] = [0, -1, 0]
    return T

def _project_ground_to_uv(points_ground_3xN: np.ndarray, E_cam_to_ground: np.ndarray, K: np.ndarray, W: int, H: int, zmin=0.1):
    """
    与 projection_g2im_extrinsic(E,K) 完全一致的投影方式：
      P = K * inv(E)[:3,:]   (ground -> cam)
      uv = P * [X,Y,Z,1]
    这里 points_ground 用的是我们的 ground/ego 坐标(x右,y前,z上)。
    """
    if points_ground_3xN.shape[1] == 0:
        return np.zeros((2, 0), dtype=np.float32), np.zeros((0,), dtype=np.float32)

    P = K @ np.linalg.inv(E_cam_to_ground)[0:3, :]  # 3x4
    N = points_ground_3xN.shape[1]
    pts_h = np.vstack([points_ground_3xN, np.ones((1, N), dtype=np.float64)])  # 4xN

    proj = P @ pts_h  # 3xN
    z = proj[2, :]
    vis = z > zmin
    z_safe = np.where(vis, z, 1.0)

    u = proj[0, :] / z_safe
    v = proj[1, :] / z_safe

    in_img = (u >= 0) & (u < W) & (v >= 0) & (v < H)
    vis = vis & in_img

    u = np.where(vis, u, -1.0).astype(np.float32)
    v = np.where(vis, v, -1.0).astype(np.float32)
    return np.stack([u, v], axis=0), vis.astype(np.float32)

class OpenLaneGenerator:
    def __init__(self, world, camera_k, img_w=1920, img_h=1280):
        self.world = world
        self.map = world.get_map()
        self.K = np.array(camera_k, dtype=np.float64)
        self.W = int(img_w)
        self.H = int(img_h)

        self.sample_step = 0.5
        self.max_dist = 103.0
        self.min_dist = 0.0
        self.lateral_range = 35.0
        self.back_dist = 20.0

        # 预处理使用的固定矩阵
        self.T_A2O = _T_apollo_to_openlane()           # Apollo -> OpenLane
        self.T_O2A = np.linalg.inv(self.T_A2O)         # OpenLane -> Apollo

        self.S_v2g = _swap_vehicle_to_ground()         # vehicle -> ground (x=Y, y=X, z=Z)
        self.S_carlaCam2Apollo = _carla_cam_to_apollo_cam()  # carla cam -> apollo cam

    def _get_category(self, carla_marking_type, carla_marking_color):
        is_white = (carla_marking_color == carla.LaneMarkingColor.White)
        is_yellow = (carla_marking_color == carla.LaneMarkingColor.Yellow)
        m_type = carla_marking_type

        if is_white:
            if m_type == carla.LaneMarkingType.Broken: return 1
            elif m_type == carla.LaneMarkingType.Solid: return 2
            elif m_type == carla.LaneMarkingType.BrokenBroken: return 3
            elif m_type == carla.LaneMarkingType.SolidSolid: return 4
            elif m_type == carla.LaneMarkingType.BrokenSolid: return 5
            elif m_type == carla.LaneMarkingType.SolidBroken: return 6
        elif is_yellow:
            if m_type == carla.LaneMarkingType.Broken: return 7
            elif m_type == carla.LaneMarkingType.Solid: return 8
            elif m_type == carla.LaneMarkingType.BrokenBroken: return 9
            elif m_type == carla.LaneMarkingType.SolidSolid: return 10
            elif m_type == carla.LaneMarkingType.BrokenSolid: return 11
            elif m_type == carla.LaneMarkingType.SolidBroken: return 12
        if m_type == carla.LaneMarkingType.Curb: return 20
        return 0
    def _enforce_y_monotonic(self, pts3xN: np.ndarray, min_dy: float = 1e-3) -> np.ndarray:
        """
        强制 ground 坐标下 y 单调递增：
        1) 先按 y 排序（解决 forward/back 拼接或局部抖动）
        2) 再做一次“单调滤波”：只保留 y 比上一个点大的点（允许极小容差 min_dy）
        """
        if pts3xN.shape[1] < 2:
            return pts3xN

        x, y, z = pts3xN[0], pts3xN[1], pts3xN[2]

        # 1) sort by y
        idx = np.argsort(y)
        x, y, z = x[idx], y[idx], z[idx]

        # 2) keep strictly increasing y
        keep = [0]
        last_y = y[0]
        for i in range(1, y.shape[0]):
            if y[i] > last_y + min_dy:
                keep.append(i)
                last_y = y[i]

        if len(keep) < 2:
            return pts3xN[:, :0]  # 返回空，后面会被跳过

        return np.vstack([x[keep], y[keep], z[keep]])


    def process_frame(self, ego_vehicle, sensor_transform, seg_image=None):
        """
        输出字段严格按预处理需要：
          - lane_lines[].xyz : OpenLane camera frame (3 x N)
          - extrinsic        : Apollo camera -> Ground (4x4)
          - intrinsic        : K (3x3)
        """
        # 1) 固定安装位姿（与你 sensor_manager 一致）
        tf_sensor_local = carla.Transform(
            carla.Location(x=1.6, z=1.55),
            carla.Rotation(pitch=-3.0)
        )
        T_v_c_carla_static = _mat44_from_carla_transform(tf_sensor_local)  # Vehicle -> CarlaCam

        # 2) 拍摄时的相机世界位姿 (CarlaCam -> World)
        T_w_c_carla = _mat44_from_carla_transform(sensor_transform)

        # 3) 反推拍摄时 Vehicle->World
        # T_w_v = T_w_c * inv(T_v_c)
        T_w_v_carla = T_w_c_carla @ np.linalg.inv(T_v_c_carla_static)

        # 4) 落地（把 vehicle 原点的 z 固定到路面高度，避免悬挂/坡度抖动）
        ego_loc_temp = carla.Location(
            x=float(T_w_v_carla[0, 3]),
            y=float(T_w_v_carla[1, 3]),
            z=float(T_w_v_carla[2, 3])
        )
        current_waypoint = self.map.get_waypoint(ego_loc_temp, project_to_road=True)

        if (not current_waypoint) or current_waypoint.is_junction:
            return {"lane_lines": [], "intrinsic": [], "extrinsic": [], "file_path": ""}

        ground_z = current_waypoint.transform.location.z
        T_w_v_carla_ground = T_w_v_carla.copy()
        T_w_v_carla_ground[2, 3] = ground_z

        # ============================================================
        # 5) 构造 Ground frame -> World 的矩阵（注意 ground 轴是 x右 y前 z上）
        # world <- ground:
        #   world = T_w_v_carla_ground * inv(S_v2g) * ground
        # 因为: ground = S_v2g * vehicle  => vehicle = inv(S_v2g) * ground
        # ============================================================
        T_w_ground = T_w_v_carla_ground @ np.linalg.inv(self.S_v2g)
        T_ground_w = np.linalg.inv(T_w_ground)  # World -> Ground

        # ============================================================
        # 6) 构造 ApolloCam -> Ground 的外参 E（写入 json）
        # 先得到 CarlaCam -> World，再转到 ApolloCam：
        #   ApolloCam = S_carlaCam2Apollo * CarlaCam
        # => CarlaCam = inv(S) * ApolloCam
        # => World = T_w_c_carla * inv(S) * ApolloCam
        # => T_w_c_apollo = T_w_c_carla * inv(S)
        # ============================================================
        T_w_c_apollo = T_w_c_carla @ np.linalg.inv(self.S_carlaCam2Apollo)
        E_apollo_cam_to_ground = T_ground_w @ T_w_c_apollo  # (ApolloCam -> Ground)

        # ============================================================
        # 7) 采样 lane：我们先在 Ground frame 下采样点（x右 y前 z上）
        # 然后把这些 ground 点变换到 ApolloCam，再变到 OpenLaneCam 存 xyz
        # 因为预处理会做：lane_apollo = T_open->apollo * lane_open
        # 所以我们要存 lane_open，才能被预处理恢复到 apollo 再乘 E。
        # ============================================================
        lanes_to_process = []
        lanes_to_process.append((current_waypoint, -1))
        lanes_to_process.append((current_waypoint, 1))
        l1 = current_waypoint.get_left_lane()
        if l1:
            lanes_to_process.append((l1, -1))
            l2 = l1.get_left_lane()
            if l2: lanes_to_process.append((l2, -1))
        r1 = current_waypoint.get_right_lane()
        if r1:
            lanes_to_process.append((r1, 1))
            r2 = r1.get_right_lane()
            if r2: lanes_to_process.append((r2, 1))

        lane_lines = []
        for wp, side in lanes_to_process:
            marking = wp.left_lane_marking if side == -1 else wp.right_lane_marking
            if marking.type == carla.LaneMarkingType.NONE:
                continue

            category_id = self._get_category(marking.type, marking.color)

            # 采样 world 点 -> ground 点 (3xN)
            points_ground = self._sample_lane_boundary_in_ground(wp, T_ground_w, side)
            if points_ground.shape[1] < 5:
                continue

            # 立交/地道过滤：ground z 太偏离 0 则丢弃
            # z_mean = float(np.mean(points_ground[2, :]))
            # if abs(z_mean) > 0.5:
            #     continue

            # 投影（用 E_apollo_cam_to_ground + K）
            uv, vis = _project_ground_to_uv(points_ground, E_apollo_cam_to_ground, self.K, self.W, self.H)

            if np.sum(vis) < 10:
                continue

            # ground -> apollo cam
            T_apollo_from_ground = np.linalg.inv(E_apollo_cam_to_ground)  # Ground -> ApolloCam
            pts_h = np.vstack([points_ground, np.ones((1, points_ground.shape[1]), dtype=np.float64)])
            pts_apollo = (T_apollo_from_ground @ pts_h)[:3, :]

            # apollo cam -> openlane cam (存入 json 的 xyz)
            # p_open = T_A2O * p_apollo
            pts_apollo_h = np.vstack([pts_apollo, np.ones((1, pts_apollo.shape[1]), dtype=np.float64)])
            pts_open = (self.T_A2O @ pts_apollo_h)[:3, :]

            lane_data = {
                # ★关键：xyz 存 OpenLane camera frame (3xN) ★
                "xyz": pts_open.astype(np.float32).tolist(),
                "uv": uv.tolist(),
                "visibility": vis.tolist(),
                "category": int(category_id)
            }
            lane_lines.append(lane_data)

        # 简单去重（按 y 起点）
        unique_lanes = []
        for lane in lane_lines:
            is_dup = False
            if len(lane["xyz"]) > 0 and len(unique_lanes) > 0:
                curr_y_start = lane["xyz"][1][0]
                for exist in unique_lanes:
                    if len(exist["xyz"]) > 0 and abs(exist["xyz"][1][0] - curr_y_start) < 0.2:
                        is_dup = True
                        break
            if not is_dup:
                unique_lanes.append(lane)
        # [新增适配] 逆向工程：生成适配 OpenLane 预处理脚本的外参矩阵
        # ------------------------------------------------------------
        # 目的：预处理脚本 (openlane.txt) 会假设输入是 Waymo 格式，并执行：
        #      R_final = inv(R_vg) @ R_json @ R_vg @ R_gc
        # 我们需要构造一个 R_json，使得 R_final 等于我们现在计算好的 E_apollo_cam_to_ground
        # 公式：R_json = R_vg @ R_final @ inv(R_gc) @ inv(R_vg)
        # ============================================================
        
        # 1. 定义脚本中的变换矩阵 (完全复制自 openlane.txt)
        R_vg = np.array([[0, 1, 0],
                         [-1, 0, 0],
                         [0, 0, 1]], dtype=np.float64)
                         
        R_gc = np.array([[1, 0, 0],
                         [0, 0, 1],
                         [0, -1, 0]], dtype=np.float64)

        # 2. 取出我们需要脚本最终得到的旋转矩阵 (Target)
        # E_apollo_cam_to_ground 是 4x4，我们只处理前 3x3 旋转部分
        R_target = E_apollo_cam_to_ground[:3, :3]

        # 3. 执行逆运算计算 R_json
        # 注意：R_gc 是正交矩阵，inv(R_gc) == R_gc.T，这里直接用 inv 保持数学直观
        R_json = R_vg @ R_target @ np.linalg.inv(R_gc) @ np.linalg.inv(R_vg)

        # 4. 组装最终写入 JSON 的外参矩阵
        # 脚本只修改旋转矩阵，平移向量 (Translation) 会被直接读取。
        # 这里的平移向量 E_apollo_cam_to_ground[:3, 3] 代表相机在 Ground 坐标系下的位置
        # (即 Camera Height 等)，这正是脚本需要的，所以直接复制。
        E_json_compatible = np.eye(4, dtype=np.float64)
        E_json_compatible[:3, :3] = R_json
        E_json_compatible[:3, 3] = E_apollo_cam_to_ground[:3, 3]

        return {
            "lane_lines": unique_lanes,
            "intrinsic": self.K.tolist(),
            # ★关键：extrinsic 存 ApolloCam -> Ground (cam_to_ground) ★
            "extrinsic": E_json_compatible.tolist(),
            "file_path": ""
        }

    def _sample_lane_boundary_in_ground(self, start_waypoint, T_ground_w, side):
        """
        采样策略保留你的“中心扩散法”，但直接产出 Ground 坐标：
          ground: x右 y前 z上
        """
        step = self.sample_step

        def collect_points(start_wp, move_forward=True):
            collected = []
            curr = start_wp
            dist = 0.0

            if not move_forward:
                prevs = curr.previous(step)
                if not prevs:
                    return []
                curr = prevs[0]
                dist += step

            target_dist = self.max_dist if move_forward else self.back_dist
            max_loops = int(target_dist / step) + 20
            loop_guard = 0

            while dist < target_dist and loop_guard < max_loops:
                loop_guard += 1

                marking = curr.left_lane_marking if side == -1 else curr.right_lane_marking
                if marking.type == carla.LaneMarkingType.NONE:
                    break

                trans = curr.transform
                center_loc = trans.location
                right_vec = trans.get_right_vector()
                half_width = curr.lane_width / 2.0

                bx = center_loc.x + right_vec.x * half_width * side
                by = center_loc.y + right_vec.y * half_width * side
                bz = center_loc.z + right_vec.z * half_width * side

                p_world = np.array([bx, by, bz, 1.0], dtype=np.float64)

                # World -> Ground: p_ground = T_ground_w * p_world
                p_ground = (T_ground_w @ p_world)[:3]

                # ground: x右 y前 z上
                x_g, y_g, z_g = float(p_ground[0]), float(p_ground[1]), float(p_ground[2])

                # 前方/后方距离 & 横向范围过滤（按 ground 的 y / x 来过滤更符合预处理）
                if (y_g > -self.back_dist) and (y_g < self.max_dist) and (abs(x_g) < self.lateral_range):
                    collected.append([x_g, y_g, z_g])

                # 移动 waypoint
                if move_forward:
                    next_wps = curr.next(step)
                    if not next_wps:
                        break
                    curr = next_wps[0]
                else:
                    prev_wps = curr.previous(step)
                    if not prev_wps:
                        break
                    curr = prev_wps[0]

                dist += step

            return collected

        fwd_points = collect_points(start_waypoint, move_forward=True)
        bwd_points = collect_points(start_waypoint, move_forward=False)
        all_points = bwd_points[::-1] + fwd_points

        if len(all_points) < 2:
            return np.zeros((3, 0), dtype=np.float32)
        
        #在生成阶段让 y 单调（不靠预处理擦屁股）
        pts = np.array(all_points, dtype=np.float32).T  # 3xN
        pts = self._enforce_y_monotonic(pts, min_dy=1e-3)
        return pts

        #return np.array(all_points, dtype=np.float32).T  # 3xN
