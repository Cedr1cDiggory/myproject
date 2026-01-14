# [复用] 基于 hud.py，用于可视化
#
# HUD（Head-Up Display）模块：
# 用于在 CARLA 仿真窗口中实时显示车辆状态、仿真状态、调试信息

import datetime
import math
import os

import pygame
import carla

import utils


class HUD(object):
    """
    HUD 主类，用于在屏幕左侧实时渲染调试信息，包括：
    - FPS（服务器 / 客户端）
    - 车辆状态（速度、方向、位置）
    - 地图与道路信息
    - GNSS 信息
    - 碰撞历史
    - 周围车辆信息
    """

    def __init__(self, width, height, doc):
        """
        HUD 初始化函数

        输入参数:
            width (int):
                窗口宽度（像素）
            height (int):
                窗口高度（像素）
            doc (str):
                文档字符串，通常来自 __doc__，
                用于 HelpText 中显示帮助说明

        输出:
            None

        函数作用:
            初始化 HUD 显示所需的字体、缓存变量和子组件
        """
        self.dim = (width, height)

        font = pygame.font.Font(pygame.font.get_default_font(), 20)

        font_name = 'courier' if os.name == 'nt' else 'mono'
        fonts = [x for x in pygame.font.get_fonts() if font_name in x]
        default_font = 'ubuntumono'
        mono = default_font if default_font in fonts else fonts[0]
        mono = pygame.font.match_font(mono)

        self._font_mono = pygame.font.Font(mono, 12 if os.name == 'nt' else 14)

        # 左下角渐隐提示文本
        self._notifications = FadingText(font, (width, 40), (0, height - 40))

        # 帮助信息面板
        self.help = HelpText(doc, pygame.font.Font(mono, 24), width, height)

        # 仿真状态变量
        self.server_fps = 0
        self.frame = 0
        self.simulation_time = 0
        self.map_name = None

        self._show_info = True
        self._info_text = []

        self._server_clock = pygame.time.Clock()

    def on_world_tick(self, timestamp):
        """
        CARLA 世界 tick 回调函数

        输入参数:
            timestamp (carla.Timestamp):
                CARLA 在每个 tick 时提供的时间戳对象

        输出:
            None

        函数作用:
            - 更新服务器 FPS
            - 更新当前帧编号
            - 更新仿真运行时间
        """
        self._server_clock.tick()
        self.server_fps = self._server_clock.get_fps()
        self.frame = timestamp.frame_count
        self.simulation_time = timestamp.elapsed_seconds

    def tick(self, world, clock):
        """
        HUD 每帧更新函数

        输入参数:
            world (World):
                当前仿真世界对象（automatic_control.py 中的 World）
            clock (pygame.time.Clock):
                客户端时钟，用于获取客户端 FPS

        输出:
            None

        函数作用:
            收集并整理当前帧需要显示的所有信息，
            但不负责真正的绘制
        """
        self._notifications.tick(world, clock)
        self.map_name = world.map.name

        if not self._show_info:
            return

        transform = world.player.get_transform()
        vel = world.player.get_velocity()
        control = world.player.get_control()

        # 计算航向角方向（N/E/S/W）
        heading = 'N' if abs(transform.rotation.yaw) < 89.5 else ''
        heading += 'S' if abs(transform.rotation.yaw) > 90.5 else ''
        heading += 'E' if 179.5 > transform.rotation.yaw > 0.5 else ''
        heading += 'W' if -0.5 > transform.rotation.yaw > -179.5 else ''

        # 碰撞历史（用于绘制柱状图）
        colhist = world.collision_sensor.get_collision_history()
        collision = [colhist[x + self.frame - 200] for x in range(0, 200)]
        max_col = max(1.0, max(collision))
        collision = [x / max_col for x in collision]

        vehicles = world.world.get_actors().filter('vehicle.*')
        ego_location = world.player.get_location()
        waypoint = world.map.get_waypoint(ego_location, project_to_road=True)

        # 自动将红灯切换为绿灯（防止车辆卡死）
        if world.player.is_at_traffic_light():
            traffic_light = world.player.get_traffic_light()
            if traffic_light.get_state() == carla.TrafficLightState.Red:
                world.hud.notification("Traffic light changed! Good to go!")
                traffic_light.set_state(carla.TrafficLightState.Green)

        # HUD 文本内容构建
        self._info_text = [
            'Server:  % 16.0f FPS' % self.server_fps,
            'Client:  % 16.0f FPS' % clock.get_fps(),
            '',
            'Vehicle: % 20s' % utils.get_actor_display_name(world.player, truncate=20),
            'Map:     % 20s' % world.map.name,
            'Road id: % 20s' % waypoint.road_id,
            'Simulation time: % 12s' % datetime.timedelta(seconds=int(self.simulation_time)),
            '',
            'Speed:   % 15.0f km/h' %
            (3.6 * math.sqrt(vel.x**2 + vel.y**2 + vel.z**2)),
            u'Heading:% 16.0f\N{DEGREE SIGN} % 2s' %
            (transform.rotation.yaw, heading),
            'Location:% 20s' %
            ('(% 5.1f, % 5.1f)' %
             (transform.location.x, transform.location.y)),
            'GNSS:% 24s' %
            ('(% 2.6f, % 3.6f)' %
             (world.gnss_sensor.lat, world.gnss_sensor.lon)),
            'Height:  % 18.0f m' % transform.location.z,
            ''
        ]

        # 根据控制类型区分车辆 / 行人
        if isinstance(control, carla.VehicleControl):
            self._info_text += [
                ('Throttle:', control.throttle, 0.0, 1.0),
                ('Steer:', control.steer, -1.0, 1.0),
                ('Brake:', control.brake, 0.0, 1.0),
                ('Reverse:', control.reverse),
                ('Hand brake:', control.hand_brake),
                ('Manual:', control.manual_gear_shift),
                'Gear:        %s' %
                {-1: 'R', 0: 'N'}.get(control.gear, control.gear)
            ]
        elif isinstance(control, carla.WalkerControl):
            self._info_text += [
                ('Speed:', control.speed, 0.0, 5.556),
                ('Jump:', control.jump)
            ]

        self._info_text += [
            '',
            'Collision:',
            collision,
            '',
            'Number of vehicles: % 8d' % len(vehicles)
        ]

        # 附近车辆列表
        if len(vehicles) > 1:
            self._info_text += ['Nearby vehicles:']

        def dist(l):
            return math.sqrt(
                (l.x - transform.location.x) ** 2 +
                (l.y - transform.location.y) ** 2 +
                (l.z - transform.location.z) ** 2
            )

        vehicles = [
            (dist(x.get_location()), x)
            for x in vehicles if x.id != world.player.id
        ]

        for d, vehicle in sorted(vehicles):
            if d > 200.0:
                break
            vehicle_type = utils.get_actor_display_name(vehicle, truncate=22)
            self._info_text.append('% 4dm %s' % (d, vehicle_type))

    def toggle_info(self):
        """
        切换 HUD 信息显示开关

        输入参数:
            None

        输出:
            None

        函数作用:
            用于在仿真过程中临时隐藏 / 显示 HUD 信息
        """
        self._show_info = not self._show_info

    def notification(self, text, seconds=2.0):
        """
        显示提示信息（带自动淡出）

        输入参数:
            text (str):
                提示文本
            seconds (float):
                显示持续时间（秒）

        输出:
            None

        函数作用:
            在屏幕底部显示临时提示信息
        """
        self._notifications.set_text(text, seconds=seconds)

    def error(self, text):
        """
        显示错误信息

        输入参数:
            text (str):
                错误提示文本

        输出:
            None
        """
        self._notifications.set_text('Error: %s' % text, (255, 0, 0))

    def render(self, display):
        """
        将 HUD 信息绘制到屏幕

        输入参数:
            display (pygame.Surface):
                Pygame 主显示窗口

        输出:
            None

        函数作用:
            负责将 tick() 中整理好的信息真正渲染出来
        """
        if self._show_info:
            info_surface = pygame.Surface((250, self.dim[1]))
            info_surface.set_alpha(100)
            display.blit(info_surface, (0, 0))

            v_offset = 4
            bar_h_offset = 100
            bar_width = 106

            for item in self._info_text:
                if v_offset + 18 > self.dim[1]:
                    break

                if isinstance(item, list):
                    if len(item) > 1:
                        points = [
                            (x + 8, v_offset + 8 + (1 - y) * 30)
                            for x, y in enumerate(item)
                        ]
                        pygame.draw.lines(display, (255, 136, 0), False, points, 2)
                    item = None
                    v_offset += 18

                elif isinstance(item, tuple):
                    if isinstance(item[1], bool):
                        rect = pygame.Rect((bar_h_offset, v_offset + 8), (6, 6))
                        pygame.draw.rect(
                            display, (255, 255, 255), rect, 0 if item[1] else 1)
                    else:
                        rect_border = pygame.Rect(
                            (bar_h_offset, v_offset + 8), (bar_width, 6))
                        pygame.draw.rect(display, (255, 255, 255), rect_border, 1)

                        fig = (item[1] - item[2]) / (item[3] - item[2])
                        if item[2] < 0.0:
                            rect = pygame.Rect(
                                (bar_h_offset + fig * (bar_width - 6),
                                 v_offset + 8), (6, 6))
                        else:
                            rect = pygame.Rect(
                                (bar_h_offset, v_offset + 8),
                                (fig * bar_width, 6))
                        pygame.draw.rect(display, (255, 255, 255), rect)
                    item = item[0]

                if item:
                    surface = self._font_mono.render(item, True, (255, 255, 255))
                    display.blit(surface, (8, v_offset))

                v_offset += 18

        self._notifications.render(display)
        self.help.render(display)



class FadingText(object):
    """
    渐隐文本类，用于显示临时提示信息
    """

    def __init__(self, font, dim, pos):
        """
        输入参数:
            font (pygame.font.Font): 字体
            dim (tuple): 显示区域尺寸
            pos (tuple): 显示位置
        """
        self.font = font
        self.dim = dim
        self.pos = pos
        self.seconds_left = 0
        self.surface = pygame.Surface(self.dim)

    def set_text(self, text, color=(255, 255, 255), seconds=2.0):
        """
        设置提示文本

        输入参数:
            text (str): 显示文本
            color (tuple): RGB 颜色
            seconds (float): 显示时长
        """
        text_texture = self.font.render(text, True, color)
        self.surface = pygame.Surface(self.dim)
        self.seconds_left = seconds
        self.surface.fill((0, 0, 0, 0))
        self.surface.blit(text_texture, (10, 11))

    def tick(self, _, clock):
        """
        每帧更新透明度

        输入参数:
            clock (pygame.time.Clock)

        输出:
            None
        """
        delta_seconds = 1e-3 * clock.get_time()
        self.seconds_left = max(0.0, self.seconds_left - delta_seconds)
        self.surface.set_alpha(500.0 * self.seconds_left)

    def render(self, display):
        """
        绘制渐隐文本
        """
        display.blit(self.surface, self.pos)



class HelpText(object):
    """
    帮助信息渲染类
    """

    def __init__(self, doc, font, width, height):
        """
        输入参数:
            doc (str): 帮助文档字符串
            font (pygame.font.Font): 字体
            width (int): 窗口宽度
            height (int): 窗口高度
        """
        lines = doc.split('\n')
        self.font = font
        self.dim = (680, len(lines) * 22 + 12)
        self.pos = (
            0.5 * width - 0.5 * self.dim[0],
            0.5 * height - 0.5 * self.dim[1]
        )
        self.surface = pygame.Surface(self.dim)
        self.surface.fill((0, 0, 0, 0))

        for i, line in enumerate(lines):
            text_texture = self.font.render(line, True, (255, 255, 255))
            self.surface.blit(text_texture, (22, i * 22))

        self._render = False
        self.surface.set_alpha(220)

    def toggle(self):
        """
        切换帮助面板显示
        """
        self._render = not self._render

    def render(self, display):
        """
        渲染帮助面板
        """
        if self._render:
            display.blit(self.surface, self.pos)

