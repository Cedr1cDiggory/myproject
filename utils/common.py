# [复用] 基于 utils.py
# Modified work Copyright (c) 2021 Anita Hu.
# Original work Copyright (c) 2018 Intel Labs.
# authors: German Ros (german.ros@intel.com)
#
# This work is licensed under the terms of the MIT license.
# For a copy, see <https://opensource.org/licenses/MIT>.
#
# Original source: https://github.com/carla-simulator/carla/blob/0.9.11/PythonAPI/examples/automatic_control.py

import random


def get_actor_display_name(actor, truncate=250):
    """
    功能：
        根据 CARLA Actor 的 type_id 生成一个可读性较好的显示名称

    输入参数：
        actor:
            carla.Actor 对象
        truncate:
            显示名称的最大长度（字符数）
            超过该长度时会被截断并在末尾添加省略号

    输出：
        name (str):
            处理后的 Actor 显示名称字符串

    说明：
        - 将 type_id 中的 '_' 替换为 '.'
        - 使用 title() 提升可读性
        - 去掉命名空间前缀（如 vehicle. / walker.）
        - 主要用于 UI 显示、日志打印等非逻辑用途
    """
    name = ' '.join(actor.type_id.replace('_', '.').title().split('.')[1:])
    return (name[:truncate - 1] + u'\u2026') if len(name) > truncate else name


def get_different_spawn_point(world, player):
    """
    功能：
        从地图中获取一个与当前玩家位置不同的出生点

    输入参数：
        world:
            carla.World 对象，用于访问地图信息
        player:
            当前玩家车辆（carla.Actor），用于获取当前位置

    输出：
        spawn_points:
            地图中所有出生点的列表（已随机打乱顺序）
        spawn_point:
            与玩家当前位置不同的一个出生点（carla.Transform）

    说明：
        - 该函数假设地图中至少存在两个 spawn point
        - 常用于重新生成玩家车辆，避免重生在原位置
        - 返回完整 spawn_points 主要用于外部复用或调试
    """
    spawn_points = world.map.get_spawn_points()
    random.shuffle(spawn_points)

    # 若第一个出生点不等于玩家当前位置，则直接使用
    if spawn_points[0].location != player.get_location():
        return spawn_points, spawn_points[0]
    else:
        # 否则使用第二个出生点
        return spawn_points, spawn_points[1]
