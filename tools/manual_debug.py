# [复用] 基于 manual_control.py，用于调试查看生成的 3D 线

#!/usr/bin/env python

"""
功能说明：
    用于在 CARLA 仿真环境中批量生成和销毁 NPC（车辆 + 行人）
    包括：
        - 自动驾驶车辆（Traffic Manager 管理）
        - 行人及其 AI 控制器
"""

import glob
import os
import sys
import time

# 将 CARLA Python API 的 egg 文件路径加入 sys.path
# 以便在不同平台 / Python 版本下正确导入 carla 模块
try:
    sys.path.append(glob.glob('../carla/dist/carla-*%d.%d-%s.egg' % (
        sys.version_info.major,
        sys.version_info.minor,
        'win-amd64' if os.name == 'nt' else 'linux-x86_64'))[0])
except IndexError:
    pass

import carla

# 车辆灯光状态枚举
from carla import VehicleLightState as vls

import logging
from numpy import random


class NPCManager(object):
    """
    类功能：
        NPC 统一管理类，用于：
            - 初始化 CARLA Client 和 TrafficManager
            - 批量生成 NPC 车辆和行人
            - 批量销毁已生成的 NPC

    设计说明：
        该类不直接解析命令行参数，
        而是依赖外部传入的 args（通常来自 argparse）
    """

    def __init__(self, args):
        """
        构造函数

        输入参数：
            args:
                命令行参数对象，通常包含：
                    - host / port
                    - tm_port
                    - num_npc_vehicles
                    - num_npc_walkers
                    - seed
                    - filterv / filterw
                    - safe / hybrid / car_lights_on 等

        成员变量说明：
            vehicles_list:
                已生成车辆的 actor_id 列表
            walkers_list:
                行人信息列表，每个元素为 dict，包含行人和控制器 id
            all_id:
                所有行人及其 controller 的 actor_id（按 controller, actor 顺序存放）
            client:
                carla.Client 实例
            traffic_manager:
                TrafficManager 实例
            all_actors:
                world.get_actors 返回的 Actor 集合
        """
        self.args = args
        self.vehicles_list = []
        self.walkers_list = []
        self.all_id = []
        self.client = carla.Client(args.host, args.port)
        self.traffic_manager = None
        self.all_actors = None

        # 设置随机种子，保证实验可复现
        random.seed(args.seed if args.seed is not None else int(time.time()))

    def spawn_npc(self):
        """
        功能：
            在当前 CARLA world 中生成 NPC
            包括：
                - 自动驾驶车辆
                - 行人及其 AI 控制器

        输入：
            无（使用初始化时传入的 self.args）

        输出：
            无返回值
            但会修改内部状态：
                - self.vehicles_list
                - self.walkers_list
                - self.all_id
                - self.all_actors

        副作用：
            - 在仿真世界中创建大量 Actor
            - Traffic Manager 状态被修改
        """
        print("Spawning NPCs")

        args = self.args
        world = self.client.get_world()

        # 获取 Traffic Manager 并设置基础参数
        self.traffic_manager = self.client.get_trafficmanager(args.tm_port)
        self.traffic_manager.set_global_distance_to_leading_vehicle(1.0)

        # 是否启用混合物理模式（用于大规模 NPC）
        if args.hybrid:
            self.traffic_manager.set_hybrid_physics_mode(True)

        # 设置 Traffic Manager 的随机种子
        if args.seed is not None:
            self.traffic_manager.set_random_device_seed(args.seed)

        # 是否作为同步模式的 master
        synchronous_master = False

        # 获取车辆和行人的蓝图集合
        blueprints = world.get_blueprint_library().filter(args.filterv)
        blueprintsWalkers = world.get_blueprint_library().filter(args.filterw)

        # 安全模式：过滤掉异常或不常用车型
        if args.safe:
            blueprints = [x for x in blueprints if int(x.get_attribute('number_of_wheels')) == 4]
            blueprints = [x for x in blueprints if not x.id.endswith('isetta')]
            blueprints = [x for x in blueprints if not x.id.endswith('carlacola')]
            blueprints = [x for x in blueprints if not x.id.endswith('cybertruck')]
            blueprints = [x for x in blueprints if not x.id.endswith('t2')]

        # 按 blueprint id 排序，保证确定性
        blueprints = sorted(blueprints, key=lambda bp: bp.id)

        # 获取地图中所有可用的车辆出生点
        spawn_points = world.get_map().get_spawn_points()
        number_of_spawn_points = len(spawn_points)

        # 若请求车辆数小于出生点数量，则打乱顺序随机生成
        if args.num_npc_vehicles < number_of_spawn_points:
            random.shuffle(spawn_points)
        elif args.num_npc_vehicles > number_of_spawn_points:
            msg = 'requested %d vehicles, but could only find %d spawn points'
            logging.warning(msg, args.num_npc_vehicles, number_of_spawn_points)
            args.num_npc_vehicles = number_of_spawn_points

        # CARLA command API（用于批量操作）
        SpawnActor = carla.command.SpawnActor
        SetAutopilot = carla.command.SetAutopilot
        SetVehicleLightState = carla.command.SetVehicleLightState
        FutureActor = carla.command.FutureActor

        # ----------------
        # 生成车辆 NPC
        # ----------------
        batch = []
        for n, transform in enumerate(spawn_points):
            if n >= args.num_npc_vehicles:
                break

            blueprint = random.choice(blueprints)

            # 随机设置车辆颜色
            if blueprint.has_attribute('color'):
                color = random.choice(blueprint.get_attribute('color').recommended_values)
                blueprint.set_attribute('color', color)

            # 随机设置驾驶员 ID
            if blueprint.has_attribute('driver_id'):
                driver_id = random.choice(blueprint.get_attribute('driver_id').recommended_values)
                blueprint.set_attribute('driver_id', driver_id)

            # 设置角色为自动驾驶
            blueprint.set_attribute('role_name', 'autopilot')

            # 设置车辆灯光状态
            light_state = vls.NONE
            if args.car_lights_on:
                light_state = vls.Position | vls.LowBeam

            # 批量生成车辆，并同时设置自动驾驶与灯光状态
            batch.append(
                SpawnActor(blueprint, transform)
                .then(SetAutopilot(FutureActor, True, self.traffic_manager.get_port()))
                .then(SetVehicleLightState(FutureActor, light_state))
            )

        # 同步执行批量生成命令
        for response in self.client.apply_batch_sync(batch, synchronous_master):
            if response.error:
                logging.error(response.error)
            else:
                self.vehicles_list.append(response.actor_id)

        # ----------------
        # 生成行人 NPC
        # ----------------
        percentagePedestriansRunning = 0.0  # 行人奔跑比例
        percentagePedestriansCrossing = 0.0  # 行人横穿马路比例

        # 1. 随机生成行人出生位置
        spawn_points = []
        for i in range(args.num_npc_walkers):
            spawn_point = carla.Transform()
            loc = world.get_random_location_from_navigation()
            if (loc != None):
                spawn_point.location = loc
                spawn_points.append(spawn_point)

        # 2. 生成行人 Actor
        batch = []
        walker_speed = []
        for spawn_point in spawn_points:
            walker_bp = random.choice(blueprintsWalkers)

            # 设置为非无敌状态
            if walker_bp.has_attribute('is_invincible'):
                walker_bp.set_attribute('is_invincible', 'false')

            # 设置行人最大速度
            if walker_bp.has_attribute('speed'):
                if (random.random() > percentagePedestriansRunning):
                    walker_speed.append(walker_bp.get_attribute('speed').recommended_values[1])
                else:
                    walker_speed.append(walker_bp.get_attribute('speed').recommended_values[2])
            else:
                print("Walker has no speed")
                walker_speed.append(0.0)

            batch.append(SpawnActor(walker_bp, spawn_point))

        results = self.client.apply_batch_sync(batch, True)

        # 保存成功生成的行人 id
        walker_speed2 = []
        for i in range(len(results)):
            if results[i].error:
                logging.error(results[i].error)
            else:
                self.walkers_list.append({"id": results[i].actor_id})
                walker_speed2.append(walker_speed[i])
        walker_speed = walker_speed2

        # 3. 为每个行人生成 AI 控制器
        batch = []
        walker_controller_bp = world.get_blueprint_library().find('controller.ai.walker')
        for i in range(len(self.walkers_list)):
            batch.append(
                SpawnActor(
                    walker_controller_bp,
                    carla.Transform(),
                    self.walkers_list[i]["id"]
                )
            )

        results = self.client.apply_batch_sync(batch, True)
        for i in range(len(results)):
            if results[i].error:
                logging.error(results[i].error)
            else:
                self.walkers_list[i]["con"] = results[i].actor_id

        # 4. 收集所有 controller 和 actor 的 id
        for i in range(len(self.walkers_list)):
            self.all_id.append(self.walkers_list[i]["con"])
            self.all_id.append(self.walkers_list[i]["id"])

        self.all_actors = world.get_actors(self.all_id)

        # 确保 client 获取到最新 transform
        world.tick()

        # 5. 初始化行人控制器并设置目标
        world.set_pedestrians_cross_factor(percentagePedestriansCrossing)
        for i in range(0, len(self.all_id), 2):
            self.all_actors[i].start()
            self.all_actors[i].go_to_location(
                world.get_random_location_from_navigation()
            )
            self.all_actors[i].set_max_speed(float(walker_speed[int(i / 2)]))

        print('Spawned %d vehicles and %d walkers.' %
              (len(self.vehicles_list), len(self.walkers_list)))

        # 示例：全局降低车辆速度
        self.traffic_manager.global_percentage_speed_difference(30.0)

    def destory_npc(self):
        """
        功能：
            销毁当前已生成的所有 NPC（车辆 + 行人）

        输入：
            无

        输出：
            无返回值

        副作用：
            - 所有对应 Actor 将从仿真世界中移除
            - NPCManager 内部列表仍保留 id 记录（通常用于程序结束前清理）
        """
        print('\nDestroying %d vehicles' % len(self.vehicles_list))
        self.client.apply_batch(
            [carla.command.DestroyActor(x) for x in self.vehicles_list]
        )

        # 停止行人 AI 控制器
        for i in range(0, len(self.all_id), 2):
            self.all_actors[i].stop()

        print('Destroying %d walkers' % len(self.walkers_list))
        self.client.apply_batch(
            [carla.command.DestroyActor(x) for x in self.all_id]
        )

        time.sleep(0.5)


