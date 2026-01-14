#遮挡剔除。输入 3D 点 + Depth Map，输出 visibility 数组
import numpy as np

class VisibilityHandler:
    @staticmethod
    def decode_carla_depth(image_data_bgra):
        """
        将 CARLA Raw Depth 解码为米
        公式: (R + G*256 + B*256*256) / (256^3 - 1) * 1000
        """
        # 输入可能是 flat buffer，先 reshape
        if len(image_data_bgra.shape) == 1:
            # 这里假设外部已经处理了 reshape，或者传入的是 raw bytes
            pass 
        
        data = image_data_bgra.astype(np.float32)
        B, G, R = data[:,:,0], data[:,:,1], data[:,:,2]
        
        normalized = (R + G * 256 + B * 256 * 256) / (256**3 - 1)
        return normalized * 1000.0

    @staticmethod
    def compute_visibility(uv_points, z_geo_values, depth_map_meters, w, h, threshold=0.4):
        """
        Z-Buffer Test
        threshold: 遮挡容忍度(米)，防止深度图精度误差导致自遮挡
        """
        visibility = []
        
        for i, (u, v) in enumerate(uv_points):
            z_real = z_geo_values[i]
            u_int, v_int = int(u), int(v)

            # 1. 越界检查
            if u_int < 0 or u_int >= w or v_int < 0 or v_int >= h:
                visibility.append(0.0)
                continue
            
            if z_real <= 0:
                visibility.append(0.0)
                continue

            # 2. 读取传感器深度
            d_sensor = depth_map_meters[v_int, u_int]

            # 3. 比较
            # 如果点的几何深度 比 传感器看到的深度 大（远），说明前面有障碍物
            if z_real > (d_sensor + threshold):
                visibility.append(0.0)
            else:
                visibility.append(1.0)

        return visibility