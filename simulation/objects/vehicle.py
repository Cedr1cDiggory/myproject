import carla
import random
import logging
from carla import VehicleLightState as vls
from .base import BaseActor

class SmartVehicle(BaseActor):
    """
    智能车辆封装 - [流畅采集版]
    核心改动：大幅提高忽略红绿灯的概率，允许全员变道，防止堵车。
    """
    def __init__(self, carla_actor: carla.Vehicle, tm_port: int, role='npc'):
        super().__init__(carla_actor)
        self.tm_port = tm_port
        self.role = role
        self.behavior_state = 'unknown'
        
        # 初始化
        self._setup_autopilot()
        self._setup_lights()

    def _setup_autopilot(self):
        """开启 TM 托管"""
        if self.role == 'npc':
            self.carla_actor.set_autopilot(True, self.tm_port)

    def _setup_lights(self):
        """强制开启车灯"""
        lights = vls.Position | vls.LowBeam
        self.carla_actor.set_light_state(carla.VehicleLightState(lights))

    def apply_behavior(self, behavior_type: str, tm_instance):
        """
        应用驾驶风格
        Args:
            behavior_type: 'cautious' | 'normal' | 'aggressive'
            tm_instance: carla.TrafficManager 实例
        """
        self.behavior_state = behavior_type
        actor = self.carla_actor

        # -------------------------------------------------------------
        # 核心策略调整：为了数据采集流畅，所有人都要学会“抢行”和“变道”
        # -------------------------------------------------------------

        if behavior_type == 'cautious': 
            # 佛系车：虽然慢，但也得允许它闯红灯，否则它就是路障
            tm_instance.vehicle_percentage_speed_difference(actor, random.uniform(10, 20)) # 慢 10-20%
            tm_instance.distance_to_leading_vehicle(actor, 10.0) # 保持距离，露出路面
            # [改动] 50% 概率闯红灯，防止完全堵死路口
            tm_instance.ignore_lights_percentage(actor, 50.0)
            # [改动] 允许变道，否则它停在那谁也过不去
            tm_instance.auto_lane_change(actor, True)

        elif behavior_type == 'normal':
            # 普通车：像老司机一样开
            tm_instance.vehicle_percentage_speed_difference(actor, random.uniform(-5, 5))
            tm_instance.distance_to_leading_vehicle(actor, 5.0)
            # [改动] 80% 概率闯红灯
            tm_instance.ignore_lights_percentage(actor, 80.0)
            # [改动] 允许变道
            tm_instance.auto_lane_change(actor, True)

        elif behavior_type == 'aggressive':
            # 激进车：完全无视规则，只求速度
            tm_instance.vehicle_percentage_speed_difference(actor, random.uniform(-20, -10)) # 超速
            tm_instance.distance_to_leading_vehicle(actor, 2.0)
            # [改动] 100% 闯红灯
            tm_instance.ignore_lights_percentage(actor, 100.0)
            tm_instance.auto_lane_change(actor, True)

    def tick(self):
        """
        每帧更新接口
        """
        pass