# 定义 Actor 基类 (参考 Reference actor.py)
import carla
import logging

class BaseActor(object):
    """
    基础 Actor 封装类
    参考自: Reference actor.py
    """
    def __init__(self, carla_actor: carla.Actor):
        self.carla_actor = carla_actor
        self.id = carla_actor.id
        self.type_id = carla_actor.type_id
        self.is_alive = True

    def get_location(self):
        if self.carla_actor and self.is_alive:
            return self.carla_actor.get_location()
        return None

    def get_transform(self):
        if self.carla_actor and self.is_alive:
            return self.carla_actor.get_transform()
        return None

    def destroy(self):
        """安全销毁"""
        if self.carla_actor and self.is_alive:
            try:
                self.carla_actor.destroy()
                self.is_alive = False
                return True
            except RuntimeError as e:
                logging.warning(f"Failed to destroy actor {self.id}: {e}")
        return False