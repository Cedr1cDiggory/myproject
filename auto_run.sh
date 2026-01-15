#!/bin/bash

# 你的启动命令
CMD="python main.py --split validation --towns Town10HD,Town05 --town_mode roundrobin --episodes 5 --frames_per_episode 1000 --skip_bad_roads"

echo "开始自动采集任务..."

# 无限循环，直到任务真正完成
while true; do
    echo "🚀 启动采集脚本..."
    $CMD
    
    # 获取 Python 脚本的退出代码
    EXIT_CODE=$?
    
    # 如果 Python 正常退出 (0)，说明全部跑完了，跳出循环
    if [ $EXIT_CODE -eq 0 ]; then
        echo "✅ 采集任务全部完成！"
        break
    else
        echo "⚠️ 检测到崩溃 (Code $EXIT_CODE)，3秒后自动重启续传..."
        sleep 3
        # 杀一下残留进程，防止端口占用
        killall -9 CarlaUE4-Linux-Shipping
        # 如果你是无头模式启动的server，可能需要重启server脚本
        # 这里假设你的 server 是单独跑的，通常不需要重启 server，除非 server 也挂了。
        # 如果 server 挂了，你需要在这里加重启 server 的命令。
    fi
done