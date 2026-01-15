import carla
import random
import logging

class WeatherManager(object):
    """
    基于官方 util/environment.py 重构的天气管理器
    """
    # ---------------------------------------------------------
    # 官方预设 (Copied from environment.py)
    # ---------------------------------------------------------
    SUN_PRESETS = {
        'day': (45.0, 0.0),
        'night': (-90.0, 0.0),
        'sunset': (0.5, 0.0)
    }

    # list format: [cloudiness, precipitation, precipitation_deposits, wind_intensity, 
    #               fog_density, fog_distance, fog_falloff, wetness, 
    #               scattering_intensity, mie_scattering_scale, rayleigh_scattering_scale, dust_storm]
    WEATHER_PRESETS = {
        'clear':    [10.0, 0.0, 0.0, 5.0, 0.0, 0.0, 0.2, 0.0, 0.0, 0.0, 0.0331, 0.0],
        'overcast': [80.0, 0.0, 0.0, 50.0, 2.0, 0.75, 0.1, 10.0, 0.0, 0.03, 0.0331, 0.0],
        'rain':     [100.0, 80.0, 90.0, 100.0, 7.0, 0.75, 0.1, 100.0, 0.0, 0.03, 0.0331, 0.0]
    }

    def __init__(self, world):
        self.world = world
        self.light_manager = world.get_lightmanager()
        self.weather = self.world.get_weather()

    def apply_long_tail_weather(self, target_mode=None):
        """
        自定义长尾/困难场景 (复用官方参数接口)
        target_mode: 可指定 'glare', 'heavy_fog', 'storm_aftermath'。如果为 None 则随机。
        """
        options = ['glare', 'heavy_fog', 'storm_aftermath']
        
        if target_mode is not None and target_mode in options:
            mode = target_mode
        else:
            mode = random.choice(options)
        
        if mode == 'glare':
            # 眩光模式：低太阳角度(sunset) + 湿滑路面(wetness)
            self.set_preset('sunset', 'clear')
            self.weather.wetness = 80.0
            self.weather.precipitation_deposits = 50.0
            
        elif mode == 'heavy_fog':
            # 团雾模式
            self.set_preset('day', 'overcast')
            self.weather.fog_density = 60.0
            self.weather.fog_distance = 10.0
            
        elif mode == 'storm_aftermath':
            # 暴雨后
            self.set_preset('day', 'clear')
            self.weather.precipitation_deposits = 90.0
            self.weather.wetness = 100.0

        self.world.set_weather(self.weather)
        print(f"[Weather] Long-Tail Mode: {mode}")
        return mode
    def set_preset(self, sun_preset='day', weather_preset='clear'):
        """
        组合应用 太阳预设 + 天气预设
        """
        # 1. 设置太阳 (Sun)
        if sun_preset in self.SUN_PRESETS:
            self.weather.sun_altitude_angle = self.SUN_PRESETS[sun_preset][0]
            self.weather.sun_azimuth_angle = self.SUN_PRESETS[sun_preset][1]
        else:
            print(f"[Weather] Warning: Sun preset '{sun_preset}' not found.")

        # 2. 设置天气参数 (Weather Params)
        if weather_preset in self.WEATHER_PRESETS:
            params = self.WEATHER_PRESETS[weather_preset]
            self._apply_params(params)
        else:
            print(f"[Weather] Warning: Weather preset '{weather_preset}' not found.")

        # 3. 应用
        self.world.set_weather(self.weather)
        
        # 4. 自动管理路灯 (如果是晚上，开启路灯)
        self._manage_street_lights(sun_preset)

        print(f"[Weather] Applied: Sun={sun_preset}, Weather={weather_preset}")
        return f"{sun_preset}_{weather_preset}"

    def set_random(self):
        """随机组合"""
        sun = random.choice(list(self.SUN_PRESETS.keys()))
        # 稍微增加白天和日落的概率，减少纯黑夜(看不清车道线)
        if sun == 'night' and random.random() < 0.5:
             sun = 'sunset'

        weather = random.choice(list(self.WEATHER_PRESETS.keys()))
        
        return self.set_preset(sun, weather)

    # ---------------------------------------------------------
    # 内部辅助函数
    # ---------------------------------------------------------
    def _apply_params(self, p):
        """对应 environment.py 中的 apply_weather_presets"""
        self.weather.cloudiness = p[0]
        self.weather.precipitation = p[1]
        self.weather.precipitation_deposits = p[2]
        self.weather.wind_intensity = p[3]
        self.weather.fog_density = p[4]
        self.weather.fog_distance = p[5]
        self.weather.fog_falloff = p[6]
        self.weather.wetness = p[7]
        self.weather.scattering_intensity = p[8]
        self.weather.mie_scattering_scale = p[9]
        self.weather.rayleigh_scattering_scale = p[10]
        self.weather.dust_storm = p[11]

    def _manage_street_lights(self, sun_preset):
        """
        管理路灯开关 (对应 apply_lights_manager)
        """
        if self.light_manager is None:
            return

        # 获取所有路灯
        street_lights = self.light_manager.get_all_lights(carla.LightGroup.Street)
        building_lights = self.light_manager.get_all_lights(carla.LightGroup.Building)

        if sun_preset == 'night':
            self.light_manager.turn_on(street_lights)
            self.light_manager.turn_on(building_lights)
        else:
            self.light_manager.turn_off(street_lights)
            self.light_manager.turn_off(building_lights)

    def set_custom_values(self, **kwargs):
        """
        允许像官方脚本一样单独设置某个值
        Example: set_custom_values(fog=50.0, rain=20.0)
        """
        for key, value in kwargs.items():
            if hasattr(self.weather, key):
                setattr(self.weather, key, value)
            # 兼容官方脚本的简写映射
            elif key == 'clouds': self.weather.cloudiness = value
            elif key == 'rain': self.weather.precipitation = value
            elif key == 'puddles': self.weather.precipitation_deposits = value
            elif key == 'wind': self.weather.wind_intensity = value
            elif key == 'fog': self.weather.fog_density = value
            elif key == 'wetness': self.weather.wetness = value
        
        self.world.set_weather(self.weather)