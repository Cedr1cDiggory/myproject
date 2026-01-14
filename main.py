import carla
import argparse
import os
import json
import cv2
import numpy as np
import time
import random

# ==========================================
# 模块导入：接口保持不变，底层逻辑已换血
# ==========================================
from simulation.sensor_manager import SyncSensorManager
from simulation.traffic_manager import NPCManager  # 现在的 NPCManager 已经是重构后的版本
from core.generator import OpenLaneGenerator
from core.geometry import GeometryUtils
#[新增]
from simulation.weather_manager import WeatherManager
from simulation.scene_manager import SceneManager
from utils import map_utils # 保持你原有的多地图工具

def _get_existing_progress(img_dir, json_dir, target_frames):
    """
    检查已保存的文件数量，实现断点续传
    返回: next_frame_id (int)
    """
    if not os.path.exists(img_dir) or not os.path.exists(json_dir):
        return 0
    
    # 获取所有 jpg 和 json
    imgs = set([f.split('.')[0] for f in os.listdir(img_dir) if f.endswith('.jpg')])
    jsons = set([f.split('.')[0] for f in os.listdir(json_dir) if f.endswith('.json')])
    
    # 只有同时存在图片和json才算有效
    valid_ids = imgs.intersection(jsons)
    count = len(valid_ids)
    
    if count == 0:
        return 0
    
    # 找到最大的 ID
    # 假设文件名是 000000.jpg, 000001.jpg ...
    try:
        max_id = max([int(fid) for fid in valid_ids])
        next_id = max_id + 1
    except ValueError:
        # 如果文件名格式不对，就按数量估算
        next_id = count

    return next_id
def _ensure_world(client, target_town: str, fixed_delta=0.1):
    """
    [MULTI-MAP] 切地图专用
    """
    cur_world = client.get_world()
    cur_name = cur_world.get_map().name.split('/')[-1]
    target_town = map_utils.normalize_town_name(target_town)

    if cur_name != target_town:
        print(f"[MULTI-MAP] Loading world: {target_town} (current={cur_name})")
        world = client.load_world(target_town)
    else:
        world = cur_world

    settings = world.get_settings()
    settings.synchronous_mode = True
    settings.fixed_delta_seconds = fixed_delta  # 10 FPS
    world.apply_settings(settings)
    world.tick()
    return world


def _spawn_ego(world, tm, rng: random.Random):
    """
    生成 Ego 车辆
    """
    bp_lib = world.get_blueprint_library()
    vehicle_bp = bp_lib.find('vehicle.tesla.model3')
    vehicle_bp.set_attribute('role_name', 'hero')

    spawn_points = world.get_map().get_spawn_points()
    rng.shuffle(spawn_points)

    ego_vehicle = None
    # 尝试在车道上生成
    for sp in spawn_points:
        wp = world.get_map().get_waypoint(sp.location, project_to_road=True)
        if wp is None or wp.lane_type != carla.LaneType.Driving:
            continue
        ego_vehicle = world.try_spawn_actor(vehicle_bp, sp)
        if ego_vehicle:
            break

    if not ego_vehicle:
        raise RuntimeError("Could not spawn ego vehicle!")

    # Ego 必须交给 TM 托管才能动
    ego_vehicle.set_autopilot(True, tm.get_port())
    tm.ignore_lights_percentage(ego_vehicle, 100.0) # Ego 稍微奔放点没关系
    tm.auto_lane_change(ego_vehicle, False)
    return ego_vehicle


def main():
    argparser = argparse.ArgumentParser(description='CARLA OpenLane Data Collector')

    # --- 基础连接参数 ---
    argparser.add_argument('--host', default='127.0.0.1', help='IP of the host server')
    argparser.add_argument('--port', default=2000, type=int, help='TCP port')
    argparser.add_argument('--tm_port', default=8000, type=int)

    # --- 地图与任务参数 ---
    argparser.add_argument('--town', default='Town10HD', help='Map to load')
    argparser.add_argument('--towns', default=None, help='List of towns for multi-map mode')
    argparser.add_argument('--town_mode', default='roundrobin', choices=['roundrobin', 'random'])
    argparser.add_argument('--seed', default=42, type=int)
    argparser.add_argument('--num_props', default=30, type=int, help='Number of static obstacles')
    argparser.add_argument('--weather_mode', default='random', choices=['random', 'long_tail', 'clear'], help='Weather generation mode')
    
    # --- 采集参数 ---
    argparser.add_argument('--split', default='training', choices=['training', 'validation'])
    argparser.add_argument('--episodes', default=1, type=int)
    argparser.add_argument('--frames_per_episode', default=1000, type=int)
    argparser.add_argument('--episode_start', default=0, type=int)
    
    # 兼容旧参数
    argparser.add_argument('--frames', default=None, type=int) 
    argparser.add_argument('--segment_name', default=None)

    # --- 过滤参数 ---
    argparser.add_argument('--min_dist', default=3.0, type=float)
    argparser.add_argument('--min_speed', default=1.0, type=float)
    argparser.add_argument('--skip_bad_roads', action='store_true')

    # --- 交通流参数 (适配新 NPCManager) ---
    argparser.add_argument('--num_npc_vehicles', default=30, type=int)
    argparser.add_argument('--num_npc_walkers', default=10, type=int)

    args = argparser.parse_args()
    rng = random.Random(args.seed)

    # 1. 建立连接
    client = carla.Client(args.host, args.port)
    client.set_timeout(20.0)

    town_list = map_utils.parse_towns_arg(args.towns, args.town)

    # 初始化变量
    sensor_mgr = None
    npc_mgr = None
    ego_vehicle = None
    tm = None
    world = None

    try:
        # 兼容逻辑
        if args.episodes == 1 and args.frames is not None:
            args.frames_per_episode = int(args.frames)

        # ------------------- Episode 循环 -------------------
        for epi in range(args.episode_start, args.episode_start + args.episodes):
            
            # # =======================================================
            # # [新增] 断点续传检查 (在加载 World 之前做，极大节省时间)
            # # =======================================================
            
            # # 1. 预先计算路径 (代码从下方移上来)
            # # 注意：pick_town_for_episode 需要在这里先确定 town
            # # 如果你的 map_utils 依赖 world 才能工作，可能需要调整。
            # # 这里假设 town_list 是固定的，我们可以直接算出 town
            # if args.town_mode == 'roundrobin':
            #     town_idx = (epi - args.episode_start) % len(town_list)
            #     town = town_list[town_idx]
            # else:
            #     # 随机模式无法预测，只能先 Random。
            #     # 但为了续传，建议固定 seed，这样随机序列也是固定的。
            #     # 这里我们先用一个临时的 rng 模拟一下，或者直接由 pick_town 决定
            #     # 简单起见，我们先加载 town 字符串，不做 world 切换
            #     town = map_utils.pick_town_for_episode(town_list, epi, args.episode_start, args.town_mode, rng)

            # if args.segment_name is not None and args.episodes == 1:
            #     segment_name = args.segment_name
            # else:
            #     segment_name = map_utils.make_segment_name(town, epi)

            # output_dir = "data/OpenLane"
            # img_dir = os.path.join(output_dir, "images", args.split, segment_name)
            # json_dir = os.path.join(output_dir, "lane3d_1000", args.split, segment_name)
            
            # # 2. 检查已有进度
            # start_frame_count = _get_existing_progress(img_dir, json_dir, args.frames_per_episode)
            
            # if start_frame_count >= args.frames_per_episode:
            #     print(f"✅ [Episode {epi}] Segment {segment_name} already completed ({start_frame_count} frames). Skipping...")
            #     continue # 直接跳过本轮循环，不加载地图
            
            # if start_frame_count > 0:
            #     print(f"⚠️ [Episode {epi}] Resuming {segment_name} from frame {start_frame_count}...")
            # else:
            #     print(f"🚀 [Episode {epi}] Starting new segment {segment_name}...")
                
            # # 创建目录
            # os.makedirs(img_dir, exist_ok=True)
            # os.makedirs(json_dir, exist_ok=True)
            # 2. 准备世界
            town = map_utils.pick_town_for_episode(town_list, epi, args.episode_start, args.town_mode, rng)
            world = _ensure_world(client, town, fixed_delta=0.1)

            # 3. 准备 TM (同步模式)
            tm = client.get_trafficmanager(args.tm_port)
            tm.set_synchronous_mode(True)
            tm.set_random_device_seed(args.seed)

            # 4. 生成 Ego
            ego_vehicle = _spawn_ego(world, tm, rng)
            print(f"[Episode {epi}] Town={town} Ego spawned: {ego_vehicle.id}")

            #[新增] 环境配置(Weather & Scene)
            weather_mgr = WeatherManager(world)
            if args.weather_mode == 'random':
                curr_weather = weather_mgr.set_random()
                print(f"[Episode {epi}] Weather set to: {curr_weather}")
            elif args.weather_mode == 'long_tail':
                curr_weather = weather_mgr.apply_long_tail_weather()
                print(f"[Episode {epi}] Weather set to Long-Tail: {curr_weather}")
            else:
                weather_mgr.set_preset('ClearNoon')
                
            scene_mgr = SceneManager(world)
            # 在路上随机撒点东西，增加难度
            scene_mgr.spawn_props(num_props=args.num_props)

            # 5. 生成传感器 (SyncSensorManager)
            # 使用 refactor 后的鲁棒版 sensor_manager
            W, H = 1920, 1280
            FOV = 51.0
            sensor_mgr = SyncSensorManager(world, ego_vehicle, w=W, h=H, fov=FOV)

            # 6. 生成交通流 (核心适配点)
            # ------------------------------------------------------------------
            # [适配说明] 
            # 这里的调用方式完全没变！
            # 但底层现在会创建 SmartVehicle 对象，自动应用“佛系/激进”策略。
            # ------------------------------------------------------------------
            npc_mgr = NPCManager(
                host=args.host, port=args.port, tm_port=args.tm_port,
                seed=args.seed, world=world, tm=tm, ego_vehicle=ego_vehicle
            )
            npc_mgr.spawn_npc(num_vehicles=args.num_npc_vehicles, num_walkers=args.num_npc_walkers)

            # [修复] 必须先初始化计数器，再调用 update
            total_ticks = 0
            npc_mgr.update(world_tick=total_ticks)

            # 7. 准备生成器
            K = GeometryUtils.build_projection_matrix(W, H, FOV)
            generator = OpenLaneGenerator(world, camera_k=K)

            # 路径设置
            if args.segment_name is not None and args.episodes == 1:
                segment_name = args.segment_name
            else:
                segment_name = map_utils.make_segment_name(town, epi)

            output_dir = "data/OpenLane"
            split_name = args.split
            img_dir = os.path.join(output_dir, "images", split_name, segment_name)
            json_dir = os.path.join(output_dir, "lane3d_1000", split_name, segment_name)
            os.makedirs(img_dir, exist_ok=True)
            os.makedirs(json_dir, exist_ok=True)

            print(f"[Episode {epi}] Start recording {args.frames_per_episode} frames -> {segment_name}")
            print("[Episode] Warming up...")
            
            # 热身 tick (让车跑起来，让行人落地)
            for _ in range(50):
                world.tick()
                npc_mgr.update(world_tick=0) # 也可以在这里让 NPC 更新

            frame_count = 0
            last_save_loc = None

            # ------------------- 采集主循环 -------------------
            while frame_count < args.frames_per_episode:
                # 1. 获取当前世界的真实 Frame ID (Source of Truth)
                # world.tick() 返回的是 frame id
                current_frame_id = world.tick() 
                total_ticks += 1
                
                npc_mgr.update(world_tick=total_ticks)

                # 2. [修改点] 将 frame id 传给 sensor manager
                # 告诉它：“我要这一帧的数据，旧的别给我，新的等着”
                rgb_image, depth_np, seg_np, sensor_tf = sensor_mgr.get_synced_frames(
                    target_frame_id=current_frame_id, 
                    timeout=2.0
                )
                
                if rgb_image is None:
                    # 如果返回 None，说明没对齐或者超时，直接跳过，不要硬存
                    continue

                # --- 过滤逻辑 ---
                loc = ego_vehicle.get_location()
                v = ego_vehicle.get_velocity()
                speed = (v.x**2 + v.y**2 + v.z**2) ** 0.5
                
                if speed < args.min_speed:
                    continue
                if last_save_loc is not None and loc.distance(last_save_loc) < args.min_dist:
                    continue
                
                # Bad Road 过滤
                if args.skip_bad_roads:
                    wp = world.get_map().get_waypoint(loc, project_to_road=True)
                    if wp:
                        road_id = int(wp.road_id)
                        if map_utils.is_bad_road_id_fast(town, road_id):
                            continue

                # --- 生成真值 ---
                result = generator.process_frame(ego_vehicle, sensor_tf, seg_image=seg_np)
                lane_count = len(result.get('lane_lines', []))

                if total_ticks % 50 == 0:
                    print(f"[Episode {epi}] Tick {total_ticks}: Spd={speed:.1f}m/s, Lanes={lane_count}, Saved={frame_count}")

                # 至少要有车道线
                if lane_count <= 0:
                    continue

                # --- 保存 ---
                file_id = f"{frame_count:06d}"
                
                # 转换图像格式 (Carla Raw -> Numpy -> JPG)
                array = np.frombuffer(rgb_image.raw_data, dtype=np.uint8)
                array = np.reshape(array, (rgb_image.height, rgb_image.width, 4))
                # 存 RGB (去除 Alpha 通道)
                cv2.imwrite(os.path.join(img_dir, f"{file_id}.jpg"), array[:, :, :3])

                result["file_path"] = f"{split_name}/{segment_name}/{file_id}.jpg"
                with open(os.path.join(json_dir, f"{file_id}.json"), 'w') as f:
                    json.dump(result, f)

                frame_count += 1
                last_save_loc = loc

            # Episode 结束清理
            print(f"[Episode {epi}] Done.")
            if sensor_mgr: sensor_mgr.destroy(); sensor_mgr = None
            if ego_vehicle: ego_vehicle.destroy(); ego_vehicle = None
            if npc_mgr: npc_mgr.destory_npc(); npc_mgr = None
            
            # 冷却
            for _ in range(20): world.tick()

    except KeyboardInterrupt:
        print("Stopped by user.")
    except Exception as e:
        print(f"Global Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("Cleaning up actors...")
        # 最后的兜底清理
        try:
            if world:
                settings = world.get_settings()
                settings.synchronous_mode = False
                world.apply_settings(settings)
        except: pass

        if tm: tm.set_synchronous_mode(False)
        if sensor_mgr: sensor_mgr.destroy()
        if ego_vehicle: 
            try: ego_vehicle.destroy() 
            except: pass
        if npc_mgr: npc_mgr.destory_npc()

if __name__ == '__main__':
    main()