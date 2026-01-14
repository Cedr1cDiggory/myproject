import carla
import random
from .objects.base import BaseActor

class SceneManager(object):
    """
    场景管理器 (基于用户提供的 Catalogue 适配版)
    职责：在路面上生成符合逻辑的静态障碍物（施工、掉落物、垃圾等）。
    """
    def __init__(self, world):
        self.world = world
        self.prop_actors = [] # List[BaseActor]
        
        # === 核心修改：基于提供的目录筛选出的蓝图 ID ===
        # CARLA 的命名规则通常是 static.prop. + 名称小写并去掉空格
        self.prop_blueprints = [
            # 1. 交通/施工类 (最常见)
            'static.prop.constructioncone',    # 施工锥
            'static.prop.trafficcone01',       # 交通锥 01
            'static.prop.trafficcone02',       # 交通锥 02
            'static.prop.streetbarrier',       # 街道护栏
            'static.prop.warningconstruction', # 施工警告牌
            'static.prop.warningaccident',     # 事故警告牌
            
            # 2. 掉落货物类 (模拟前车掉落)
            'static.prop.box01',
            'static.prop.box02',
            'static.prop.box03',
            'static.prop.creasedbox01', # 褶皱的纸箱
            'static.prop.creasedbox02',
            'static.prop.creasedbox03',
            
            # 3. 垃圾/杂物类 (模拟路面异物)
            'static.prop.trashbag',    # 垃圾袋
            'static.prop.garbage01',   # 垃圾堆 01
            'static.prop.garbage02',
            'static.prop.garbage03',
            
            # 4. 特殊长尾类
            'static.prop.shoppingcart', # 购物车 (经典的 Corner Case)
        ]

    def spawn_props(self, num_props=10):
        """
        在随机生成点附近生成道具
        """
        print(f"[Scene] Spawning {num_props} static props...")
        
        bp_lib = self.world.get_blueprint_library()
        spawn_points = self.world.get_map().get_spawn_points()
        
        # 打乱生成点
        random.shuffle(spawn_points)
        
        count = 0
        for sp in spawn_points:
            if count >= num_props:
                break
                
            # 随机选一个道具
            bp_name = random.choice(self.prop_blueprints)
            
            # 健壮性查找：防止某个具体版本的 CARLA 缺少其中某一个资产
            try:
                bp = bp_lib.find(bp_name)
            except IndexError:
                # 默默跳过，不报错，继续找下一个
                continue
            except Exception as e:
                print(f"[Scene] Error finding blueprint '{bp_name}': {e}")
                continue
            
            # 位置微调：不要完全重合在 spawn point 中心，稍微随机偏移一点
            loc = sp.location
            loc.x += random.uniform(-1.5, 1.5) # 横向/纵向 随机偏移
            loc.y += random.uniform(-1.5, 1.5)
            loc.z += 0.2 # 稍微抬高，防止穿模
            
            trans = carla.Transform(loc, sp.rotation)
            
            # 尝试生成
            # 如果道具有无敌属性，关掉它，这样车撞上去会有物理反馈
            if bp.has_attribute('is_invincible'):
                bp.set_attribute('is_invincible', 'false')
                
            # 部分大物体可能需要设置质量，这里使用默认
            prop_actor = self.world.try_spawn_actor(bp, trans)
            
            if prop_actor:
                # 开启物理模拟：这样车撞到锥桶，锥桶会飞出去，而不是像墙一样
                try:
                    prop_actor.set_simulate_physics(True)
                except:
                    pass
                
                # 封装管理
                self.prop_actors.append(BaseActor(prop_actor))
                count += 1
                
        print(f"[Scene] Successfully spawned {count} props.")

    def destroy_props(self):
        """清理道具"""
        if not self.prop_actors:
            return
            
        print(f"[Scene] Cleaning up {len(self.prop_actors)} props...")
        for prop in self.prop_actors:
            prop.destroy()
        self.prop_actors.clear()