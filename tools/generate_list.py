import os
import glob

data_root = "data/OpenLane"

def generate_list(split_name):
    # 查找 images/split_name 下所有的 jpg
    # split_name 是 "training" 或 "validation"
    search_path = os.path.join(data_root, "images", split_name, "**", "*.jpg")
    files = glob.glob(search_path, recursive=True)
    
    output_txt = os.path.join(data_root, "data_lists", f"{split_name}.txt")
    os.makedirs(os.path.dirname(output_txt), exist_ok=True)
    
    print(f"Found {len(files)} files for {split_name}...")
    
    with open(output_txt, 'w') as f:
        for file_path in files:
            # 转换为相对路径: training/segment-xxx/000xxx
            rel_path = os.path.relpath(file_path, os.path.join(data_root, "images"))
            # 去掉 .jpg 后缀
            line_str = os.path.splitext(rel_path)[0]
            f.write(line_str + "\n")
    print(f"Saved list to {output_txt}")

if __name__ == "__main__":
    generate_list("training")
    generate_list("validation")