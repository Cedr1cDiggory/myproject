import carla
import numpy as np
import queue
import weakref
import logging

# 配置 Logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SensorWrapper(object):
    """
    仿照 uploaded/sensor.py 的设计：
    1. 拥有独立的 Queue
    2. 使用 weakref 避免内存泄漏
    3. 支持按 Frame ID 检索数据的“追赶”机制
    """
    def __init__(self, parent_actor, sensor_bp, transform, attach_to):
        self.name = sensor_bp.id
        self.queue = queue.Queue()
        self.sensor = parent_actor.spawn_actor(sensor_bp, transform, attach_to=attach_to)
        
        # [成熟方案] 使用 weakref 防止循环引用导致的内存泄漏
        # 参考 sensor.py 中的 data_callback 实现
        weak_self = weakref.ref(self)
        self.sensor.listen(lambda data: SensorWrapper._on_data(weak_self, data))

    @staticmethod
    def _on_data(weak_self, data):
        """静态回调函数，仅负责推入数据"""
        self = weak_self()
        if not self:
            return
        # 仅做最轻量的数据入队
        self.queue.put(data)

    def get_data(self, target_frame, timeout=2.0):
        """
        [核心机制] 获取指定帧的数据
        参考 sensor.py 的 save_to_disk 逻辑：
        循环丢弃旧帧 (sensor_frame < target_frame)，直到追上目标帧。
        """
        while True:
            try:
                # 阻塞等待数据
                data = self.queue.get(block=True, timeout=timeout)
                
                # [关键] 丢弃旧帧 (Drop-Old Strategy)
                if data.frame < target_frame:
                    # logger.debug(f"{self.name}: Dropping old frame {data.frame}, target is {target_frame}")
                    continue
                
                # 如果拿到的是未来帧（极少见），说明错过了目标帧，或者逻辑错位
                if data.frame > target_frame:
                    logger.warning(f"{self.name}: Missed frame {target_frame}, got {data.frame} instead.")
                    return None # 这一帧这一个传感器没对齐，返回空

                # 刚好命中
                if data.frame == target_frame:
                    return data
                    
            except queue.Empty:
                logger.warning(f"{self.name}: Timeout waiting for frame {target_frame}")
                return None

    def destroy(self):
        if self.sensor and self.sensor.is_alive:
            self.sensor.stop()
            self.sensor.destroy()
        self.sensor = None
        # 清空队列断开引用
        with self.queue.mutex:
            self.queue.queue.clear()


class SyncSensorManager:
    """
    管理器现在只负责编排 (Orchestration)，
    具体的队列维护交给 SensorWrapper
    """
    def __init__(self, world, vehicle, w=1920, h=1280, fov=51.0, camera_tf=None):
        self.world = world
        
        bp_lib = world.get_blueprint_library()
        bp_rgb = bp_lib.find('sensor.camera.rgb')
        bp_depth = bp_lib.find('sensor.camera.depth')
        bp_seg = bp_lib.find('sensor.camera.semantic_segmentation')

        for bp in [bp_rgb, bp_depth, bp_seg]:
            bp.set_attribute('image_size_x', str(w))
            bp.set_attribute('image_size_y', str(h))
            bp.set_attribute('fov', str(fov))
            bp.set_attribute('sensor_tick', '0.0')

        if camera_tf is None:
            camera_tf = carla.Transform(carla.Location(x=1.6, z=1.55), carla.Rotation(pitch=-3.0))
        
        # 实例化三个独立的 Wrapper
        self.rgb_wrapper = SensorWrapper(world, bp_rgb, camera_tf, vehicle)
        self.depth_wrapper = SensorWrapper(world, bp_depth, camera_tf, vehicle)
        self.seg_wrapper = SensorWrapper(world, bp_seg, camera_tf, vehicle)

    def get_synced_frames(self, target_frame_id, timeout=2.0):
        """
        [修改接口] 现在需要传入 target_frame_id
        管理器向三个传感器分别“索要”同一帧的数据。
        """
        # 1. 并行/串行获取数据（由于 Queue 是线程安全的，串行调用 get 也会很快，因为数据通常已经在里面了）
        rgb_data = self.rgb_wrapper.get_data(target_frame_id, timeout)
        depth_data = self.depth_wrapper.get_data(target_frame_id, timeout)
        seg_data = self.seg_wrapper.get_data(target_frame_id, timeout)

        # 2. 只有三个都拿到才算成功
        if not (rgb_data and depth_data and seg_data):
            return None, None, None, None

        # 3. 数据转换 (和之前保持一致，但只在确认对齐后才做，节省算力)
        
        # Depth
        depth_array = np.frombuffer(depth_data.raw_data, dtype=np.uint8)
        depth_array = np.reshape(depth_array, (depth_data.height, depth_data.width, 4))
        depth_meters = depth_array[:,:,0].astype(np.float32) + \
                       depth_array[:,:,1].astype(np.float32) * 256.0 + \
                       depth_array[:,:,2].astype(np.float32) * 256.0 * 256.0
        depth_meters = (depth_meters / (256.0**3 - 1)) * 1000.0

        # Seg
        seg_array = np.frombuffer(seg_data.raw_data, dtype=np.uint8)
        seg_array = np.reshape(seg_array, (seg_data.height, seg_data.width, 4))
        seg_class_map = seg_array[:, :, 2] 

        # Return (RGB Raw Data 保持对象返回，main去处理转numpy，和之前兼容)
        return rgb_data, depth_meters, seg_class_map, rgb_data.transform

    def destroy(self):
        self.rgb_wrapper.destroy()
        self.depth_wrapper.destroy()
        self.seg_wrapper.destroy()