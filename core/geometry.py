import numpy as np
import math
import carla

class GeometryUtils:
    @staticmethod
    def build_projection_matrix(w, h, fov):
        """构建相机内参矩阵 K"""
        focal = w / (2.0 * math.tan(fov * math.pi / 360.0))
        K = np.identity(3)
        K[0, 0] = K[1, 1] = focal
        K[0, 2] = w / 2.0
        K[1, 2] = h / 2.0
        return K

    @staticmethod
    def world_to_camera_matrix(sensor_transform):
        """
        构建 [World -> Camera] 的 4x4 外参矩阵
        包含坐标系转换：UE4 (X前 Y右 Z上) -> Camera (X右 Y下 Z前)
        """
        # 1. World -> Sensor (UE4 Frame)
        # 这一步将世界坐标转为相对于传感器的坐标，但轴向仍是 UE4 定义
        w2s_ue4 = np.array(sensor_transform.get_inverse_matrix())

        # 2. Axis Swap Matrix (UE4 -> Standard Camera)
        # Cam_X = UE_Y
        # Cam_Y = -UE_Z
        # Cam_Z = UE_X
        ue4_to_cv = np.array([
            [0, 1, 0, 0],
            [0, 0, -1, 0],
            [1, 0, 0, 0],
            [0, 0, 0, 1]
        ])

        # 组合变换矩阵
        extrinsic = np.dot(ue4_to_cv, w2s_ue4)
        return extrinsic

    @staticmethod
    def project_3d_to_2d(points_3d, K, extrinsic):
        """
        将 3D 世界坐标点投影到 2D 像素平面
        Returns:
            uv: (N, 2) 像素坐标
            points_cam: (N, 3) 相机坐标系下的点
            valid_mask: (N,) Z>0 的有效点掩码
        """
        if len(points_3d) == 0:
            return np.array([]), np.array([]), np.array([])

        points_np = np.array(points_3d)
        
        # 1. World -> Camera Frame
        # 构造齐次坐标 (N, 4)
        points_hom = np.hstack((points_np, np.ones((len(points_np), 1))))
        # 矩阵乘法: (N, 4) @ (4, 4).T -> (N, 4)
        points_cam_hom = np.dot(points_hom, extrinsic.T)
        points_cam = points_cam_hom[:, :3]

        # 2. Camera -> Image Plane
        # (N, 3) @ (3, 3).T -> (N, 3)
        points_img = np.dot(points_cam, K.T)
        
        # 3. 透视除法
        z = points_img[:, 2:3]
        valid_mask = (z > 0).flatten()
        
        # 避免除以 0
        z_safe = np.where(z <= 0, 1e-5, z)
        uv = points_img[:, :2] / z_safe

        return uv, points_cam, valid_mask