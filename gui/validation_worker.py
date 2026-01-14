# gui/validation_worker.py
import os
import glob
import math
import random
import traceback
import numpy as np
from PyQt5.QtCore import QThread, pyqtSignal

# 引入验证脚本中的核心逻辑
# 确保你已经在 tools/ 下创建了 __init__.py
try:
    from tools.batch_validate_openlane import validate_frame, FrameReport, load_frame, write_csv
except ImportError:
    # 备用方案：如果导入失败，提示用户检查路径
    print("Error: Could not import tools.batch_validate_openlane. Please ensure 'tools/__init__.py' exists.")

class ValidationWorker(QThread):
    log_signal = pyqtSignal(str)          # 发送日志文本
    progress_signal = pyqtSignal(int)     # 发送进度 (0-100)
    finished_signal = pyqtSignal(str)     # 完成信号(返回摘要信息)
    
    def __init__(self, input_dir, num_samples, img_w, img_h, out_csv):
        super().__init__()
        self.input_dir = input_dir
        self.num_samples = num_samples
        self.img_w = img_w
        self.img_h = img_h
        self.out_csv = out_csv
        self.is_running = True

    def stop(self):
        self.is_running = False

    def run(self):
        try:
            self.log_signal.emit(f"Scanning directory: {self.input_dir}")
            
            # 1. 查找文件
            pattern = os.path.join(self.input_dir, "*.json")
            files = sorted(glob.glob(pattern))
            if not files:
                # 尝试 jsonl
                files = sorted(glob.glob(os.path.join(self.input_dir, "*.jsonl")))
            
            if not files:
                self.log_signal.emit("❌ No JSON/JSONL files found!")
                self.finished_signal.emit("Failed: No files found.")
                return

            self.log_signal.emit(f"Found {len(files)} files.")

            # 2. 采样
            if 0 < self.num_samples < len(files):
                self.log_signal.emit(f"Randomly sampling {self.num_samples} files...")
                rng = random.Random(42) # 固定种子方便复现
                files = rng.sample(files, self.num_samples)
            
            # 3. 开始验证循环
            reports = []
            total = len(files)
            
            for i, p in enumerate(files):
                if not self.is_running:
                    self.log_signal.emit("Validation stopped by user.")
                    break
                
                try:
                    frame = load_frame(p)
                    # 调用原始脚本的验证函数
                    rep = validate_frame(frame, p, self.img_w, self.img_h)
                    reports.append(rep)
                    
                    if not rep.ok:
                        short_name = os.path.basename(p)
                        self.log_signal.emit(f"⚠️ Fail [{short_name}]: {rep.reason}")
                
                except Exception as e:
                    self.log_signal.emit(f"Error reading {os.path.basename(p)}: {e}")

                # 更新进度
                if i % 10 == 0 or i == total - 1:
                    progress = int((i + 1) / total * 100)
                    self.progress_signal.emit(progress)

            # 4. 生成统计摘要
            if reports:
                ok_count = sum(1 for r in reports if r.ok)
                fail_count = len(reports) - ok_count
                
                reproj_means = np.array([r.reproj_mean_px for r in reports if not math.isnan(r.reproj_mean_px)])
                
                summary = []
                summary.append("========== Validation Summary ==========")
                summary.append(f"Total: {len(reports)} | OK: {ok_count} | FAIL: {fail_count}")
                
                if reproj_means.size > 0:
                    mean_val = reproj_means.mean()
                    p95_val = np.percentile(reproj_means, 95)
                    summary.append(f"Reproj Error (px): Mean={mean_val:.2f}, P95={p95_val:.2f}")
                
                # 写入 CSV
                write_csv(reports, self.out_csv)
                summary.append(f"Report saved to: {self.out_csv}")
                
                final_text = "\n".join(summary)
                self.log_signal.emit(final_text)
                self.finished_signal.emit("Done")
            else:
                self.finished_signal.emit("Done (No reports)")

        except Exception as e:
            self.log_signal.emit(f"🔥 Critical Error: {str(e)}")
            traceback.print_exc()
            self.finished_signal.emit("Error")