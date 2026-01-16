# gui/worker.py
import time
import os
import json
import cv2
import numpy as np
import carla
import traceback

from PyQt5.QtCore import QThread, pyqtSignal

# 引入你项目中的模块
from simulation.sensor_manager import SyncSensorManager
# from simulation.traffic_manager import NPCManager # 如果你暂时没用到 NPCManager，可以先注释掉
from core.generator import OpenLaneGenerator
from core.geometry import GeometryUtils

class CarlaWorker(QThread):
    # 定义信号：发送给 UI 线程的数据
    log_signal = pyqtSignal(str)          # 发送日志文本
    image_signal = pyqtSignal(np.ndarray) # 发送 OpenCV 图片
    progress_signal = pyqtSignal(int)     # 发送进度 (0-100)
    status_signal = pyqtSignal(str)       # 简短状态 (如 "Speed: 30km/h")
    finished_signal = pyqtSignal()        # 任务结束

    def __init__(self, config):
        super().__init__()
        self.cfg = config
        self.is_running = True
        self.client = None
        self.world = None
        
    def stop(self):
        """外部调用此方法请求停止"""
        self.is_running = False

    def run(self):
        """线程入口"""
        try:
            self.log_signal.emit(f"Connecting to CARLA at {self.cfg['host']}:{self.cfg['port']}...")
            
            client = carla.Client(self.cfg['host'], self.cfg['port'])
            client.set_timeout(20.0)

            # 1. 加载地图
            curr_map = client.get_world().get_map().name.split('/')[-1]
            if curr_map != self.cfg['town']:
                self.log_signal.emit(f"Loading map: {self.cfg['town']}...")
                world = client.load_world(self.cfg['town'])
            else:
                world = client.get_world()

            # 2. 设置同步模式 (必须)
            settings = world.get_settings()
            settings.synchronous_mode = True
            settings.fixed_delta_seconds = 0.1 # 10 FPS
            world.apply_settings(settings)
            
            # 设置交通管理器 (可选)
            tm = client.get_trafficmanager(self.cfg['tm_port'])
            tm.set_synchronous_mode(True)
            tm.set_random_device_seed(self.cfg['seed'])

            # 3. 生成主车 (Ego)
            bp_lib = world.get_blueprint_library()
            vehicle_bp = bp_lib.find('vehicle.tesla.model3')
            vehicle_bp.set_attribute('role_name', 'hero')
            
            spawn_points = world.get_map().get_spawn_points()
            ego_vehicle = None
            
            # 简单的寻找出生点逻辑
            import random
            random.shuffle(spawn_points) # 随机打乱，防止每次都在同一个点
            
            for sp in spawn_points:
                ego_vehicle = world.try_spawn_actor(vehicle_bp, sp)
                if ego_vehicle: break
            
            if not ego_vehicle:
                # 尝试抬高 Z 轴强行生成
                spawn_points[0].location.z += 2.0
                ego_vehicle = world.try_spawn_actor(vehicle_bp, spawn_points[0])
                
            if not ego_vehicle:
                raise RuntimeError("Failed to spawn ego vehicle")

            ego_vehicle.set_autopilot(True, tm.get_port())
            tm.ignore_lights_percentage(ego_vehicle, 100.0)
            tm.auto_lane_change(ego_vehicle, False)

            # 4. 初始化传感器管理器
            W, H = 1920, 1280
            FOV = 51.0
            sensor_mgr = SyncSensorManager(world, ego_vehicle, w=W, h=H, fov=FOV)
            
            # 初始化生成器
            K = GeometryUtils.build_projection_matrix(W, H, FOV)
            generator = OpenLaneGenerator(world, camera_k=K)

            # 5. 准备保存目录
            output_dir = "data/OpenLane"
            img_dir = os.path.join(output_dir, "images", self.cfg['split'], self.cfg['segment'])
            json_dir = os.path.join(output_dir, "lane3d_1000", self.cfg['split'], self.cfg['segment'])
            os.makedirs(img_dir, exist_ok=True)
            os.makedirs(json_dir, exist_ok=True)

            self.log_signal.emit("Warming up simulation...")
            for _ in range(20): 
                world.tick()

            frame_count = 0
            last_save_loc = None
            target_frames = self.cfg['frames']

            self.log_signal.emit(">>> Start Recording <<<")

            # === 主循环 ===
            while self.is_running and frame_count < target_frames:
                # [关键修复] 获取 frame_id
                frame_id = world.tick()

                # [关键修复] 传入 frame_id 给 sensor_manager
                rgb, depth, seg, tf = sensor_mgr.get_synced_frames(frame_id, timeout=2.0)
                
                if rgb is None: 
                    # self.log_signal.emit("Frame Drop or Timeout")
                    continue
                
                # 处理图像显示
                img_bgra = np.frombuffer(rgb.raw_data, dtype=np.uint8).reshape(H, W, 4)
                img_bgr = img_bgra[:, :, :3]
                img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
                self.image_signal.emit(img_rgb) # 发送给 UI 显示

                # 状态更新
                loc = ego_vehicle.get_location()
                v = ego_vehicle.get_velocity()
                speed = 3.6 * (v.x**2 + v.y**2 + v.z**2)**0.5 # km/h
                self.status_signal.emit(f"Speed: {speed:.1f} km/h | Frames: {frame_count}/{target_frames}")

                # 过滤逻辑 (停车时不保存)
                if speed < self.cfg['min_speed']: continue
                if last_save_loc and loc.distance(last_save_loc) < self.cfg['min_dist']: continue

                # 生成 OpenLane 数据
                result = generator.process_frame(ego_vehicle, tf, seg_image=seg)
                lane_count = len(result['lane_lines'])

                if lane_count > 0:
                    file_id = f"{frame_count:06d}"
                    
                    # 保存图片 (OpenCV 使用 BGR)
                    cv2.imwrite(os.path.join(img_dir, f"{file_id}.jpg"), img_bgr)
                    
                    # 保存 JSON
                    result["file_path"] = f"{self.cfg['split']}/{self.cfg['segment']}/{file_id}.jpg"
                    with open(os.path.join(json_dir, f"{file_id}.json"), 'w') as f:
                        json.dump(result, f)

                    frame_count += 1
                    last_save_loc = loc
                    
                    # 更新进度
                    progress = int((frame_count / target_frames) * 100)
                    self.progress_signal.emit(progress)
                    if frame_count % 10 == 0:
                        self.log_signal.emit(f"Saved {file_id} | Lanes: {lane_count}")

            self.log_signal.emit("Collection Finished.")

        except Exception as e:
            self.log_signal.emit(f"ERROR: {str(e)}")
            traceback.print_exc()
        finally:
            # 清理资源
            self.log_signal.emit("Cleaning up actors...")
            if 'settings' in locals():
                settings.synchronous_mode = False
                world.apply_settings(settings)
            if 'sensor_mgr' in locals() and sensor_mgr: sensor_mgr.destroy()
            if 'ego_vehicle' in locals() and ego_vehicle: ego_vehicle.destroy()
            self.finished_signal.emit()