#基于 automatic_control.py 的 World 类
class World(object):
    """
    World 类用于统一封装 CARLA 仿真世界的运行环境，主要职责包括：
    - 地图加载与管理
    - 玩家车辆（ego vehicle）的生成与销毁
    - 各类传感器的创建与生命周期管理
    - 天气系统的更新
    """

    def __init__(self, carla_world, hud, args):
        """
        World 构造函数

        输入参数:
            carla_world (carla.World):
                CARLA 客户端返回的世界对象

            hud (HUD):
                用于屏幕显示调试信息的 HUD 对象

            args (argparse.Namespace):
                命令行解析后的参数集合，用于配置车辆、相机、天气等

        输出:
            None

        函数作用:
            初始化世界状态，并立即调用 restart() 生成玩家车辆与传感器
        """
        self.world = carla_world
        try:
            self.map = self.world.get_map()
        except RuntimeError as error:
            print('地图加载失败:', error)
            sys.exit(1)

        self.hud = hud

        # Ego Vehicle（主车）
        self.player = None

        # 各类传感器
        self.collision_sensor = None
        self.lane_invasion_sensor = None
        self.gnss_sensor = None
        self.camera_manager = None
        self.segmentation_manager = None

        # 天气系统
        self._weather_speed_factor = 0.05
        self.weather = None

        # 车辆蓝图与相机 gamma
        self._actor_filter = args.filter
        self._gamma = args.gamma

        # 初始化世界
        self.restart(args)

        # 注册 tick 回调
        self.world.on_tick(hud.on_world_tick)

    def restart(self, args):
        """
        重置世界状态（核心函数）

        输入参数:
            args (argparse.Namespace):
                启动参数，用于控制随机种子、相机参数、天气恢复等

        输出:
            None

        函数作用:
            - 生成或重新生成 ego vehicle
            - 初始化 RGB 相机 / 分割相机
            - 初始化碰撞、车道入侵、GNSS 等传感器
            - 初始化天气系统

        该函数是：
            每次切换 Town / 车辆卡死重生 / 恢复进度 时的关键入口
        """
        cam_index = self.camera_manager.index if self.camera_manager is not None else 0
        cam_pos_id = self.camera_manager.transform_index if self.camera_manager is not None else 0
        seg_index = self.segmentation_manager.index if self.segmentation_manager is not None else 5
        seg_pos_id = self.segmentation_manager.transform_index if self.segmentation_manager is not None else 0

        if args.seed is not None:
            random.seed(args.seed)

        blueprint = random.choice(
            self.world.get_blueprint_library().filter(self._actor_filter)
        )
        blueprint.set_attribute('role_name', 'hero')

        if blueprint.has_attribute('color'):
            blueprint.set_attribute(
                'color',
                random.choice(blueprint.get_attribute('color').recommended_values)
            )

        # 如果已有玩家，先销毁再生成
        if self.player is not None:
            spawn_point = self.player.get_transform()
            spawn_point.location.z += 2.0
            self.destroy()
            self.player = self.world.try_spawn_actor(blueprint, spawn_point)

        # 直到成功生成玩家
        while self.player is None:
            spawn_points = self.map.get_spawn_points()
            random.shuffle(spawn_points)
            spawn_point = spawn_points[0]
            spawn_waypoint = self.map.get_waypoint(spawn_point.location, project_to_road=True)

            idx = 1
            while map_info.is_bad_road_id(self.map.name, spawn_waypoint.road_id):
                spawn_point = spawn_points[idx]
                spawn_waypoint = self.map.get_waypoint(spawn_point.location, project_to_road=True)
                idx += 1

            self.player = self.world.try_spawn_actor(blueprint, spawn_point)

        # 初始化传感器
        self.collision_sensor = CollisionSensor(self.player, self.hud)
        self.lane_invasion_sensor = LaneInvasionSensor(self.player, self.hud)
        self.gnss_sensor = GnssSensor(self.player)

        self.camera_manager = CameraManager(self.player, self.hud, self._gamma)
        self.camera_manager.transform_index = cam_pos_id
        self.camera_manager.set_sensor(cam_index, notify=False)

        self.segmentation_manager = CameraManager(self.player, self.hud, self._gamma)
        self.segmentation_manager.transform_index = seg_pos_id
        self.segmentation_manager.set_sensor(seg_index, notify=False)

        self.hud.notification(get_actor_display_name(self.player))

        # 天气初始化
        self.weather = Weather(self.world.get_weather())
        if args.resume_weather is not None:
            self.weather.resume_state(args.resume_weather)
            self.world.set_weather(self.weather.weather)

    def update_weather(self, clock):
        """
        更新天气状态

        输入参数:
            clock (pygame.time.Clock):
                用于获取当前 FPS，控制天气变化速度

        输出:
            None

        函数作用:
            - 动态变化天气
            - 夜间自动开启车辆灯光
        """
        self.weather.tick(self._weather_speed_factor * clock.get_fps())
        self.world.set_weather(self.weather.weather)

    def tick(self, clock):
        """
        每一帧调用的世界更新函数

        输入参数:
            clock (pygame.time.Clock)

        输出:
            None

        函数作用:
            - 更新 HUD
            - 更新天气
        """
        self.hud.tick(self, clock)
        self.update_weather(clock)

    def render(self, display):
        """
        渲染当前帧画面

        输入参数:
            display (pygame.Surface):
                Pygame 显示窗口

        输出:
            None
        """
        self.camera_manager.render(display)
        self.hud.render(display)

    def destroy(self):
        """
        销毁世界中所有 Actor

        输入参数:
            None

        输出:
            None

        函数作用:
            在退出或切换 Town 时，确保所有资源被正确释放
        """
        actors = [
            self.camera_manager.sensor,
            self.segmentation_manager.sensor,
            self.collision_sensor.sensor,
            self.lane_invasion_sensor.sensor,
            self.gnss_sensor.sensor,
            self.player
        ]
        for actor in actors:
            if actor is not None:
                actor.destroy()

