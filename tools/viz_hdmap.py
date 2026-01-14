import open3d as o3d
import numpy as np
import argparse
import os
import json

def load_lane_lines(json_path):
    """
    从 JSON 文件中读取车道线 3D 点 (兼容字典格式)
    """
    with open(json_path, 'r') as f:
        data = json.load(f)
    
    lane_lines = data.get('lane_lines', [])
    lines_geometry = []

    print(f"Loaded JSON: {os.path.basename(json_path)}")
    print(f"Found {len(lane_lines)} lanes.")

    for i, lane in enumerate(lane_lines):
        # [修复] 判断数据类型，如果是字典则提取 'xyz' 字段
        points = None
        
        if isinstance(lane, dict):
            # OpenLane 格式通常把 3D 点存在 'xyz' 键中
            if 'xyz' in lane:
                points = np.array(lane['xyz'], dtype=np.float64)
            elif 'points' in lane:
                points = np.array(lane['points'], dtype=np.float64)
            else:
                print(f"Warning: Lane {i} is a dict but has no 'xyz' or 'points' key. Keys: {list(lane.keys())}")
                continue
        else:
            # 如果本身就是列表
            points = np.array(lane, dtype=np.float64)
        
        # 再次检查点数
        if points is None or len(points) < 2:
            continue

        # --- 坐标系修正 (关键) ---
        # CARLA (左手) -> Open3D (右手)
        # 我们对地图做了 Y 轴取反，所以车道线点也要对 Y 取反才能对齐
        points[:, 1] *= -1 

        # 创建 Open3D 的 LineSet 对象
        line_set = o3d.geometry.LineSet()
        line_set.points = o3d.utility.Vector3dVector(points)
        
        # 构建线条连接索引: [[0,1], [1,2], [2,3], ...]
        lines_indices = [[k, k + 1] for k in range(len(points) - 1)]
        line_set.lines = o3d.utility.Vector2iVector(lines_indices)
        
        # 设置颜色为红色 (R, G, B) = (1, 0, 0)
        colors = [[1, 0, 0] for _ in range(len(lines_indices))]
        line_set.colors = o3d.utility.Vector3dVector(colors)
        
        lines_geometry.append(line_set)

    return lines_geometry

def viz_overlay(ply_path, json_path):
    if not os.path.exists(ply_path):
        print(f"Error: Map file not found: {ply_path}")
        return
    if not os.path.exists(json_path):
        print(f"Error: Json file not found: {json_path}")
        return

    # 1. 加载 HD Map 点云
    print(f"Loading HD Map: {ply_path} ...")
    pcd = o3d.io.read_point_cloud(ply_path)
    
    # --- 坐标系修正 ---
    # 翻转 Y 轴以匹配通用的右手坐标系视图
    R = np.identity(3)
    R[1, 1] = -1  
    pcd.rotate(R, center=(0, 0, 0))
    
    # 将点云设为灰色，方便突出红色的车道线
    pcd.paint_uniform_color([0.5, 0.5, 0.5]) 

    # 2. 加载车道线 (红色线条)
    lane_geometries = load_lane_lines(json_path)

    # 3. 组合并显示
    vis_elements = [pcd] + lane_geometries
    
    # 添加坐标轴 (原点)
    axes = o3d.geometry.TriangleMesh.create_coordinate_frame(size=5.0, origin=[0, 0, 0])
    vis_elements.append(axes)

    print(f"Visualizing... (Red Lines = Lanes, Grey Points = Map)")
    
    # 设置视角
    vis = o3d.visualization.Visualizer()
    vis.create_window(window_name="OpenLane 3D Validation", width=1280, height=720)
    for geom in vis_elements:
        vis.add_geometry(geom)
        
    # 渲染配置：黑色背景
    opt = vis.get_render_option()
    opt.background_color = np.asarray([0.1, 0.1, 0.1])
    opt.point_size = 1.0 # 地图点小一点
    opt.line_width = 5.0 # 线宽一点 (注意：Open3D 某些版本 line_width 无效，视具体版本而定)

    vis.run()
    vis.destroy_window()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Visualize 3D Lanes on HD Map")
    parser.add_argument("--map", type=str, required=True, help="Path to .ply map file")
    parser.add_argument("--json", type=str, required=True, help="Path to .json label file")
    
    args = parser.parse_args()
    viz_overlay(args.map, args.json)