import os
import shutil
import json
import glob
import random
from tqdm import tqdm

def organize_dataset(data_root, split_ratio=0.9):
    """
    将 CARLA 生成的扁平数据重组为 OpenLane 标准格式:
    
    原结构:
    output_dataset/
      ├── lane3d_1000/xxxx.json
      └── images/xxxx.jpg
      
    新结构 (脚本需要的):
    output_dataset/
      ├── lane3d_1000/training/segment-0/xxxx.json
      └── images/training/segment-0/xxxx.jpg
    """
    
    # 1. 检查源数据
    src_json_dir = os.path.join(data_root, "lane3d_1000")
    src_img_dir = os.path.join(data_root, "images")
    
    # 获取根目录下的所有 json 文件
    # 注意：这里我们只找文件，防止递归找到已经移动进去的文件夹
    json_files = sorted([
        f for f in glob.glob(os.path.join(src_json_dir, "*.json")) 
        if os.path.isfile(f)
    ])
    
    if not json_files:
        print(f"在 {src_json_dir} 未找到扁平结构的 .json 文件，可能已经整理过了？")
        return

    print(f"找到 {len(json_files)} 帧数据，开始重组...")

    # 2. 随机划分训练/验证集
    random.seed(42)
    random.shuffle(json_files)
    split_idx = int(len(json_files) * split_ratio)
    
    splits = {
        "training": json_files[:split_idx],
        "validation": json_files[split_idx:]
    }

    # 3. 执行移动和路径修正
    for split_name, files in splits.items():
        # OpenLane 使用 segment-xxx 分组，我们创建一个虚拟的 segment-0
        segment_name = "segment-0"
        
        # 构建目标文件夹
        dst_json_dir = os.path.join(src_json_dir, split_name, segment_name)
        dst_img_dir = os.path.join(src_img_dir, split_name, segment_name)
        
        os.makedirs(dst_json_dir, exist_ok=True)
        os.makedirs(dst_img_dir, exist_ok=True)
        
        print(f"正在处理 {split_name} 集 ({len(files)} 帧)...")
        
        for json_path in tqdm(files):
            file_name = os.path.basename(json_path)
            file_id = os.path.splitext(file_name)[0]
            
            # 读取原始 JSON
            with open(json_path, 'r') as f:
                data = json.load(f)
            
            # === 关键修正：修改 file_path ===
            # 原脚本逻辑：os.path.join('images', info_dict['file_path'])
            # 我们需要让 file_path = "training/segment-0/xxxx.jpg"
            # 这样拼起来才是：images/training/segment-0/xxxx.jpg (即图片实际位置)
            
            src_img_path = os.path.join(src_img_dir, f"{file_id}.jpg")
            
            if not os.path.exists(src_img_path):
                print(f"警告: 图片 {src_img_path} 缺失，跳过。")
                continue
                
            # 1. 更新 JSON 路径
            new_rel_path = f"{split_name}/{segment_name}/{file_id}.jpg"
            data['file_path'] = new_rel_path
            
            # 2. 保存 JSON 到新目录
            dst_json_path = os.path.join(dst_json_dir, file_name)
            with open(dst_json_path, 'w') as f:
                json.dump(data, f)
            
            # 3. 移动图片到新目录
            dst_img_path = os.path.join(dst_img_dir, f"{file_id}.jpg")
            shutil.move(src_img_path, dst_img_path)
            
            # 4. 删除旧 JSON
            os.remove(json_path)

    print("\n目录重组完成！")

if __name__ == "__main__":
    organize_dataset("output_dataset")