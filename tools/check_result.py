import json
import cv2
import os
import glob
import numpy as np
import argparse
import random

def viz_lane_data(img_path, json_path):
    if not os.path.exists(img_path) or not os.path.exists(json_path):
        print(f"Error: Pair not found.\nImg: {img_path}\nJson: {json_path}")
        return

    # 1. 读取图片
    img = cv2.imread(img_path)
    if img is None:
        print("Error: Failed to load image.")
        return

    # 2. 读取 JSON
    with open(json_path, 'r') as f:
        data = json.load(f)

    # 打印基础信息
    print(f"--- Checking: {os.path.basename(img_path)} ---")
    print(f"File Path in JSON: {data.get('file_path', 'N/A')}")
    
    lane_lines = data.get('lane_lines', [])
    print(f"Detected Lanes: {len(lane_lines)}")

    # 3. 可视化绘制 (假设 JSON 中包含 2D 投影点 'uv' 或类似字段)
    # OpenLane 格式通常包含 '2d_lane_center' 或在 points 里有 uv
    colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0), (0, 255, 255)]
    
    for i, lane in enumerate(lane_lines):
        color = colors[i % len(colors)]
        
        # 尝试提取 2D 点。不同的 Generator 格式略有不同，这里兼容常见的几种
        points_2d = []
        
        # Case A: 标准 OpenLane 格式 (points 列表里有 uv)
        # 假设 lane 结构是 list of points 或 dict
        if isinstance(lane, list): 
            # 可能是 [[x,y,z], ...] 或 [[u,v], ...]
            # 这里需要根据你的 Generator 具体输出调整
            pass 
        elif isinstance(lane, dict):
            # 常见格式: lane['uv'] 是 [[u,v], ...] 列表
            if 'uv' in lane:
                points_2d = lane['uv']
            # 或者 lane['2d_lane_center']
            elif '2d_lane_center' in lane:
                points_2d = lane['2d_lane_center']
        
        # 绘制
        if len(points_2d) > 0:
            for pt in points_2d:
                u, v = int(pt[0]), int(pt[1])
                # 过滤屏幕外的点
                if 0 <= u < img.shape[1] and 0 <= v < img.shape[0]:
                    cv2.circle(img, (u, v), 3, color, -1)
            
            # 连线
            pts = np.array(points_2d, dtype=np.int32)
            pts = pts.reshape((-1, 1, 2))
            cv2.polylines(img, [pts], False, color, 2)

    # 显示天气/道具统计 (如果 JSON 里存了 metadata)
    # cv2.putText(img, f"Lanes: {len(lane_lines)}", (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

    # 缩放以便查看 (1080p 屏幕可能放不下原图)
    img_show = cv2.resize(img, (1280, 720))
    cv2.imshow("OpenLane training", img_show)
    print("Press any key for next image, 'q' to quit.")
    key = cv2.waitKey(0)
    if key == ord('q'):
        return False
    return True

def main():
    # 自动寻找最近生成的 segment
    base_dir = "data/OpenLane/images/training"
    if not os.path.exists(base_dir):
        print(f"Data directory not found: {base_dir}")
        return

    # 获取所有 segment 文件夹
    segments = sorted(glob.glob(os.path.join(base_dir, "*")))
    if not segments:
        print("No segments found.")
        return

    # 选最新的一个
    latest_segment = segments[-1]
    print(f"Validating Segment: {latest_segment}")

    # 获取该 segment 下的所有图片
    images = sorted(glob.glob(os.path.join(latest_segment, "*.jpg")))
    
    # 随机抽查或者顺序查看
    # random.shuffle(images) 

    json_base = latest_segment.replace("images", "lane3d_1000")
    
    for img_path in images:
        filename = os.path.basename(img_path).replace(".jpg", ".json")
        json_path = os.path.join(json_base, filename)
        
        if not viz_lane_data(img_path, json_path):
            break
            
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()