import carla
import logging
import random
import numpy as np
from .objects.vehicle import SmartVehicle

# 如果你想封装行人，也可以加一个 SmartWalker，
# 但行人行为较简单，为了不增加你太多文件，暂时在 Manager 里管理。

class NPCManager(object):
    """
    [架构重构版] 交通流管理器
    特点：
    1. 基于 SmartVehicle 对象管理，逻辑解耦。
    2. 整合了行人生成修复 (Z轴抬升)。
    3. 纯 World 操作，杜绝 Client 同步锁死问题。
    4. 集成混合物理模式与看门狗，防止崩溃与卡死。
    """

    def __init__(self, host, port, tm_port, seed, world, tm, ego_vehicle):
        self.world = world
        self.tm = tm
        self.ego_vehicle = ego_vehicle
        self.tm_port = tm_port
        self.seed = seed
        
        # 容器：存放封装好的对象
        self.vehicle_objects = [] # List[SmartVehicle]
        
        # 容器：存放原始 Actor (行人部分暂未深度封装)
        self.walkers_list = []    
        self.controllers_list = []

        # 计数器 (用于看门狗频率控制)
        self.total_ticks = 0

        # 随机数初始化
        if self.seed:
            random.seed(self.seed)
            np.random.seed(self.seed)

    def spawn_npc(self, num_vehicles, num_walkers):
        """
        生成 NPC 总入口
        """
        print(f"[Traffic] Requesting {num_vehicles} vehicles and {num_walkers} walkers...")

        # 1. 全局配置 (混合物理模式，防崩溃的核心)
        self._setup_tm_global()

        # 2. 生成车辆 (使用 SmartVehicle)
        self._spawn_vehicles(num_vehicles)

        # 3. 生成行人 (使用修复后的逻辑)
        self._spawn_walkers(num_walkers)

    def update(self, world_tick):
        """
        每帧更新
        Args:
            world_tick: 当前仿真帧号 (int)
        """
        self.total_ticks = world_tick

        # 1. 委托给对象自己去 tick (目前 SmartVehicle 主要是占位，未来可加逻辑)
        # for v in self.vehicle_objects: v.tick()

        # 2. 看门狗：清理卡死或太远的车
        self.check_stuck_vehicles()

    def check_stuck_vehicles(self):
        """
        看门狗逻辑：清理僵尸车
        """
        # 每 100 帧 (约5-10秒) 检查一次，不需要每帧都跑
        if self.total_ticks % 100 != 0:
            return
            
        if not self.ego_vehicle:
            return

        ego_loc = self.ego_vehicle.get_location()
        
        # 使用切片 [:] 遍历副本，因为可能会在循环中 remove 元素
        for v_obj in self.vehicle_objects[:]: 
            actor = v_obj.carla_actor
            
            # 基础检查：Actor 是否还活着
            if not actor.is_alive:
                self.vehicle_objects.remove(v_obj)
                continue
                
            v_loc = actor.get_location()
            dist = v_loc.distance(ego_loc)

            # 1. 删除离得太远的车 (超过 200米)
            # 既节省物理算力，又防止远处路口因为没人管而死锁，最后导致全城大堵车
            if dist > 200.0:
                # print(f"[Traffic] Recycling vehicle at dist={dist:.1f}")
                v_obj.destroy() # 安全销毁
                self.vehicle_objects.remove(v_obj)
                continue
                
            # 2. (可选扩展) 删除长时间速度为 0 的车
            # 这里暂时不加，防止把等红灯的车删了。
            # 如果需要，可以在 SmartVehicle 里维护一个 stuck_timer。

    def destory_npc(self):
        """
        销毁所有 NPC
        """
        print(f'\n[Traffic] Cleaning up {len(self.vehicle_objects)} vehicles and {len(self.walkers_list)} walkers...')
        
        # 1. 销毁车辆对象
        for v_obj in self.vehicle_objects:
            v_obj.destroy()
        self.vehicle_objects.clear()

        # 2. 销毁行人相关 Actor
        self._destroy_actors(self.controllers_list)
        self._destroy_actors(self.walkers_list)
        self.controllers_list.clear()
        self.walkers_list.clear()

    # =========================================
    # 内部实现细节 (Private Methods)
    # =========================================

    def _setup_tm_global(self):
        """Traffic Manager 全局设置 (防崩溃关键)"""
        # 开启混合物理模式：
        # 50米半径内的车进行全物理模拟，50米外的车只进行运动学模拟(Teleport)，极大降低 CPU 负载
        self.tm.set_hybrid_physics_mode(True)
        self.tm.set_hybrid_physics_radius(50.0) 
        
        # 设置随机种子，保证行为可复现
        if self.seed:
            self.tm.set_random_device_seed(self.seed)

    def _spawn_vehicles(self, target_count):
        """车辆生成具体逻辑"""
        # 准备蓝图
        bp_lib = self.world.get_blueprint_library()
        blueprints = bp_lib.filter("vehicle.*")
        
        # 过滤掉摩托车、自行车 (容易倒) 和特殊车辆
        blueprints = [x for x in blueprints if int(x.get_attribute('number_of_wheels')) == 4]
        blueprints = [x for x in blueprints if not x.id.endswith('microlino')]
        blueprints = [x for x in blueprints if not x.id.endswith('carlacola')]
        blueprints = [x for x in blueprints if not x.id.endswith('cybertruck')]
        blueprints = [x for x in blueprints if not x.id.endswith('t2')]
        blueprints = [x for x in blueprints if not x.id.endswith('sprinter')]
        blueprints = [x for x in blueprints if not x.id.endswith('firetruck')]
        blueprints = [x for x in blueprints if not x.id.endswith('ambulance')]
        
        spawn_points = self.world.get_map().get_spawn_points()
        random.shuffle(spawn_points)

        hero_loc = self.ego_vehicle.get_location() if self.ego_vehicle else None
        
        count = 0
        for transform in spawn_points:
            if count >= target_count:
                break
            
            # 空间过滤：Ego 20米内不生成，防止开局就撞
            if hero_loc and transform.location.distance(hero_loc) < 20.0:
                continue
            
            # 简单去重：检查与其他 NPC 的距离
            if self._is_location_occupied(transform.location, min_dist=5.0):
                continue
            
            # 准备蓝图
            bp = random.choice(blueprints)
            if bp.has_attribute('color'):
                color = random.choice(bp.get_attribute('color').recommended_values)
                bp.set_attribute('color', color)
            
            # 抬升 Z 轴，防止车轮陷地里
            transform.location.z += 0.2
            
            # 尝试生成 (Raw Spawn)
            raw_actor = self.world.try_spawn_actor(bp, transform)
            
            if raw_actor:
                # --- 核心：封装为 SmartVehicle ---
                vehicle_obj = SmartVehicle(raw_actor, self.tm_port)
                
                # --- 核心：分配行为 (防止拥堵) ---
                # 概率分布：50% 佛系(防遮挡), 30% 普通, 20% 激进
                rand_val = random.random()
                
                # 注意：这里我们调用的是 SmartVehicle 封装好的 apply_behavior
                # 它内部会设置 auto_lane_change, ignore_lights 等激进参数
                if rand_val < 0.5:
                    vehicle_obj.apply_behavior('cautious', self.tm)
                elif rand_val < 0.8:
                    vehicle_obj.apply_behavior('normal', self.tm)
                else:
                    vehicle_obj.apply_behavior('aggressive', self.tm)

                self.vehicle_objects.append(vehicle_obj)
                count += 1
        
        print(f"[Traffic] Spawned {len(self.vehicle_objects)} vehicles.")

    def _spawn_walkers(self, target_count):
        """行人生成具体逻辑 (包含 Z轴修复)"""
        bp_lib = self.world.get_blueprint_library()
        bps_walkers = bp_lib.filter("walker.pedestrian.*")
        bp_controller = bp_lib.find('controller.ai.walker')
        
        hero_loc = self.ego_vehicle.get_location() if self.ego_vehicle else None
        
        count = 0
        max_trials = target_count * 5 # 最多尝试次数，防止死循环
        trial = 0

        while count < target_count and trial < max_trials:
            trial += 1
            # 获取人行道上的随机点
            loc = self.world.get_random_location_from_navigation()
            
            if not loc: continue
            
            # 过滤
            if hero_loc and loc.distance(hero_loc) < 15.0: continue
            # 防止行人重叠
            if self._is_walker_too_close(loc): continue

            # 生成配置
            trans = carla.Transform(loc)
            trans.location.z += 1.0 # [关键] 强制抬高 1米，防止卡死
            
            bp = random.choice(bps_walkers)
            if bp.has_attribute('is_invincible'):
                bp.set_attribute('is_invincible', 'false')
            
            # 生成本体
            walker_actor = self.world.try_spawn_actor(bp, trans)
            
            if walker_actor:
                self.walkers_list.append(walker_actor)
                
                # 生成控制器 (Attach)
                controller = self.world.try_spawn_actor(bp_controller, carla.Transform(), attach_to=walker_actor)
                
                if controller:
                    self.controllers_list.append(controller)
                    # 必须 Tick 一下让 attach 生效 (虽然在 main loop 也会 tick，但这里为了安全)
                    # 由于我们不持有 client，这里不做 world.tick()，依靠 controller.start() 的异步性
                    try:
                        controller.start()
                        controller.go_to_location(self.world.get_random_location_from_navigation())
                        
                        # 速度设置
                        speed = 1.4
                        if bp.has_attribute('speed'):
                             vals = bp.get_attribute('speed').recommended_values
                             speed = float(vals[1] if random.random() > 0.5 else vals[2])
                        controller.set_max_speed(speed)
                        count += 1
                    except Exception:
                        pass
        
        print(f"[Traffic] Spawned {count} walkers.")

    # --- Helpers ---

    def _is_location_occupied(self, loc, min_dist=5.0):
        # 检查是否与现有车辆太近
        for v in self.vehicle_objects:
            if v.get_location().distance(loc) < min_dist:
                return True
        return False

    def _is_walker_too_close(self, loc, min_dist=2.0):
        # 检查是否与现有行人太近
        for w in self.walkers_list:
            # 这里的 w 是原始 actor，可能已经 destroy，需要 check is_alive
            if w.is_alive and w.get_location().distance(loc) < min_dist:
                return True
        return False

    def _destroy_actors(self, actor_list):
        for actor in actor_list:
            if actor and actor.is_alive:
                try: 
                    if isinstance(actor, carla.WalkerAIController):
                        actor.stop()
                    actor.destroy()
                except: pass
    