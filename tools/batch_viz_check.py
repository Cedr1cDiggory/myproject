import json
import cv2
import numpy as np
import os
import sys
import argparse
import glob

# ==========================================
# 1. 审美配置：颜色定义 (BGR 格式)
# ==========================================
# [修改点] 白色车道线 -> 改为鲜绿色，对比度最高
COLOR_WHITE  = (0, 255, 0)      # 绿色 (用于代表现实中的白色线)
COLOR_YELLOW = (0, 215, 255)    # 金黄 (OpenCV BGR: Gold)
COLOR_RED    = (50, 50, 255)    # 鲜红 (路沿)
COLOR_UNKNOWN= (255, 0, 255)    # 紫色 (未知类型，防止和绿色混淆)

# ==========================================
# 2. 映射定义：ID -> 样式
# ==========================================
LANE_STYLES = {
    # White Lines (1-6) -> 统一用绿色显示
    1:  {'color': COLOR_WHITE,  'name': 'White Broken'},
    2:  {'color': COLOR_WHITE,  'name': 'White Solid'},
    3:  {'color': COLOR_WHITE,  'name': 'White Dbl Broken'},
    4:  {'color': COLOR_WHITE,  'name': 'White Dbl Solid'},
    5:  {'color': COLOR_WHITE,  'name': 'White Brk/Sld'},
    6:  {'color': COLOR_WHITE,  'name': 'White Sld/Brk'},
    
    # Yellow Lines (7-12) -> 保持黄色
    7:  {'color': COLOR_YELLOW, 'name': 'Yellow Broken'},
    8:  {'color': COLOR_YELLOW, 'name': 'Yellow Solid'},
    9:  {'color': COLOR_YELLOW, 'name': 'Yellow Dbl Broken'},
    10: {'color': COLOR_YELLOW, 'name': 'Yellow Dbl Solid'},
    11: {'color': COLOR_YELLOW, 'name': 'Yellow Brk/Sld'},
    12: {'color': COLOR_YELLOW, 'name': 'Yellow Sld/Brk'},
    
    # Curb (20) -> 保持红色
    20: {'color': COLOR_RED,    'name': 'Curb'},
    21: {'color': COLOR_RED,    'name': 'Curb'},
}

def draw_text_box(img, text, pos, bg_color=(0,0,0), txt_color=(255,255,255)):
    """绘制带背景框的文字"""
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 0.5
    thickness = 1
    (t_w, t_h), _ = cv2.getTextSize(text, font, scale, thickness)
    x, y = pos
    h, w = img.shape[:2]
    
    # 简单的边界保护，防止文字画出屏幕
    x = max(0, min(x, w - t_w))
    y = max(t_h + 5, min(y, h))
    
    # 背景框
    cv2.rectangle(img, (x, y - t_h - 4), (x + t_w + 4, y + 4), bg_color, -1)
    # 文字
    # 如果背景是亮绿色/黄色，文字用黑色更清晰；如果是深红/紫，文字用白色
    # 这里为了统一简化，统一用黑色文字，背景色用线条颜色
    cv2.putText(img, text, (x + 2, y), font, scale, (0,0,0), thickness, cv2.LINE_AA)

def visualize_uv(json_path, img_path, output_path):
    # 1. 检查文件
    if not os.path.exists(json_path):
        return False
    if not os.path.exists(img_path):
        print(f"Error: Image not found: {img_path}")
        return False

    # 2. 读取数据
    try:
        with open(json_path, 'r') as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error loading JSON {json_path}: {e}")
        return False
    
    img = cv2.imread(img_path)
    if img is None:
        print(f"Error: Failed to load image {img_path}")
        return False

    height, width = img.shape[:2]
    
    lane_lines = data.get('lane_lines', [])

    for i, lane in enumerate(lane_lines):
        if 'uv' not in lane:
            continue
            
        uvs = np.array(lane['uv']) 
        
        # 兼容性处理: 确保形状为 (2, N) 转置为 (N, 2)
        if len(uvs.shape) == 2 and uvs.shape[0] == 2 and uvs.shape[1] > 2:
            uvs = uvs.T
        
        # 空数据保护
        if len(uvs.shape) < 2 or uvs.shape[1] == 0:
            continue

        # --- 获取样式 ---
        # 优先用 category_id，如果没有则尝试 category
        cat_id = lane.get('category_id', lane.get('category', 0))
        style = LANE_STYLES.get(cat_id, {'color': COLOR_UNKNOWN, 'name': f'Unknown({cat_id})'})
        color = style['color']
        
        # 记录第一个有效的屏幕内点，用于画标签
        first_valid_pt = None

        for j in range(uvs.shape[0]):
            u = uvs[j, 0]
            v = uvs[j, 1]
            
            # 过滤无效点 (-1) 和 图像外点
            if u < 0 or v < 0 or u >= width or v >= height:
                continue
                
            # 记录第一个点
            if first_valid_pt is None:
                first_valid_pt = (int(u), int(v))

            # 绘制实心圆点
            cv2.circle(img, (int(u), int(v)), 3, color, -1)
            
        # --- 绘制信息标注 ---
        if first_valid_pt:
            label_text = f"ID:{i} {style['name']}"
            draw_text_box(img, label_text, first_valid_pt, bg_color=color, txt_color=(0,0,0))

    # 4. 叠加 Extrinsic 信息 (可选)
    if 'extrinsic' in data:
        ext = np.array(data['extrinsic'])
        trans = ext[:3, 3] 
        info_text = f"Ext T: [{trans[0]:.2f}, {trans[1]:.2f}, {trans[2]:.2f}]"
        cv2.putText(img, info_text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
    
    # 文件名标注
    cv2.putText(img, os.path.basename(img_path), (10, height - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)

    # 5. 保存
    cv2.imwrite(output_path, img)
    return True

def main():
    argparser = argparse.ArgumentParser(description='批量可视化 OpenLane 数据集 (清晰版)')
    
    argparser.add_argument('--root_dir', default="data/OpenLane", help='数据根目录')
    argparser.add_argument('--split', default="validation", help='training 或 validation')
    argparser.add_argument('--segment', default="segment-Town03-sunset_overcast-000", help='要可视化的 segment 文件夹名')
    argparser.add_argument('--max_frames', type=int, default=None, help='最大可视化帧数，不填则全部处理')
    
    args = argparser.parse_args()

    # 1. 构造路径
    json_dir = os.path.join(args.root_dir, "lane3d_1000", args.split, args.segment)
    img_dir = os.path.join(args.root_dir, "images", args.split, args.segment)
    
    # 2. 设置输出目录
    output_base_dir = "vis_data"
    output_dir = os.path.join(output_base_dir, args.segment)
    
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"Created output directory: {output_dir}")
    
    # 3. 获取文件列表
    if not os.path.exists(json_dir):
        print(f"Error: Directory not found: {json_dir}")
        return

    json_files = sorted(glob.glob(os.path.join(json_dir, "*.json")))
    
    if not json_files:
        print("No JSON files found.")
        return

    print(f"Found {len(json_files)} frames in {args.segment}. Processing...")

    # 4. 批量处理
    count = 0
    for json_file in json_files:
        if args.max_frames is not None and count >= args.max_frames:
            break

        filename = os.path.basename(json_file)
        frame_id = filename.split('.')[0]
        
        img_file = os.path.join(img_dir, f"{frame_id}.jpg")
        out_file = os.path.join(output_dir, f"{frame_id}_vis.jpg")
        
        success = visualize_uv(json_file, img_file, out_file)
        
        if success:
            count += 1
            if count % 50 == 0:
                print(f"Processed {count} frames...")

    print(f"\nDone! Processed {count} images.")
    print(f"Results are saved in: {output_dir}")

if __name__ == "__main__":
    main()