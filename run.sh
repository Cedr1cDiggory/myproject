#!/bin/bash

# 1. 进入脚本目录
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

# 2. 开启日志
LOG_FILE="$DIR/launch_log.txt"
exec > >(tee -a "$LOG_FILE") 2>&1

echo ">>> 启动时间: $(date)"
echo ">>> 工作目录: $DIR"

# 3. 初始化 Conda
source /home/zxw/anaconda3/etc/profile.d/conda.sh

# 4. 激活环境
echo ">>> 正在激活 Carla_3.8 环境..."
conda activate Carla_3.8

# =======================================================
# 核心修复：强制只加载 Python 3.x 的 .egg 文件
# =======================================================
CARLA_EGG_DIR="/home/zxw/CARLA/PythonAPI/carla/dist"

if [ -d "$CARLA_EGG_DIR" ]; then
    echo ">>> 正在搜索 Python 3.x 版本的 CARLA 库..."
    
    # 修改点：将原来的 *.egg 改为 *-py3.*.egg
    # 这样就会忽略掉那个 py2.7 的文件
    FOUND_EGG=false
    for egg in "$CARLA_EGG_DIR"/*-py3.7*.egg; do
        if [ -f "$egg" ]; then
            export PYTHONPATH=$PYTHONPATH:$egg
            echo ">>> 已添加 CARLA 库: $egg"
            FOUND_EGG=true
        fi
    done
    
    if [ "$FOUND_EGG" = false ]; then
        echo ">>> [错误] 在 $CARLA_EGG_DIR 下未找到 Python 3 的 egg 文件！"
        echo ">>> 请检查该目录下是否有类似 carla-*-py3.7-*.egg 的文件。"
    fi
else
    echo ">>> 警告: 未找到 CARLA dist 目录: $CARLA_EGG_DIR"
fi
# =======================================================

# 6. 运行 Python
echo ">>> 启动 GUI..."
python launch_gui.py

# 7. 错误捕获
if [ $? -ne 0 ]; then
    echo "!!! 程序崩溃 !!!"
    echo "请检查上方报错信息。"
    read -p "按回车键退出..."
fi

sleep 2