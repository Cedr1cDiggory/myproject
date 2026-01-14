# [复用] 基于 map_info.py
# 主要用途：提供 CARLA 不同 Town 中 road_id → 车道线数量的先验标注信息，
#           并标记存在车道线质量问题的道路

import sys

# 支持的 Town 名称列表
# 用于上层逻辑判断当前地图是否有对应的先验信息
available_town_info = ['Town01', 'Town03', 'Town04', 'Town05', 'Town07', 'Town10', 'Town10HD']

import re
import random


def get_town_info(town_name):
    """
    根据 Town 名称获取对应的 Town 类对象

    输入：
    - town_name: str
        CARLA 地图名称，例如 'Town05'、'Town10HD'

    输出：
    - TownXX 类
        返回当前模块中定义的 Town 类（如 Town05、Town10）

    说明：
    - Town10HD 在数据层面与 Town10 共用，因此统一映射为 Town10
    - 通过 sys.modules[__name__] 动态获取当前模块内的类定义
    """
    if town_name == 'Town10HD':
        town_name = 'Town10'
    return getattr(sys.modules[__name__], town_name)


def get_gt_lane_count(town_name, road_id):
    """
    查询指定 Town 中某条 road_id 的 GT（Ground Truth）车道数量

    输入：
    - town_name: str
        Town 名称
    - road_id: int
        CARLA 地图中的 road_id

    输出：
    - int
        返回该 road_id 对应的车道数量（包含道路两侧 curb）
        若未找到对应 road_id，则返回 -1

    说明：
    - 每个 Town 类中使用 lane_count 字典维护：
        key   -> 车道数量
        value -> 具有该车道数量的 road_id 列表
    """
    town = get_town_info(town_name)
    for count, road_ids in town.lane_count.items():
        if road_id in road_ids:
            return count
    return -1


def is_bad_road_id(town_name, road_id):
    """
    判断指定 road_id 是否属于车道线质量异常的道路

    输入：
    - town_name: str
        Town 名称
    - road_id: int
        CARLA 地图中的 road_id

    输出：
    - bool
        True  -> 该 road_id 在车道线数据中存在问题
        False -> 该 road_id 未被标记为异常

    说明：
    - bad_road_ids 通常表示：
        - 车道线错位（misalignment）
        - 车道线缺失
        - curb 不完整
    """
    town = get_town_info(town_name)
    if road_id in town.bad_road_ids:
        return True
    return False


# ============================================================
# [NEW] Multi-map episode helpers (for dataset generation)
# ============================================================

import re
import random
from typing import List, Optional


def normalize_town_name(town_name: str) -> str:
    """
    Normalize CARLA map name to a canonical Town string.

    Examples:
      - 'Town10HD' -> 'Town10HD'
      - 'Carla/Maps/Town05' -> 'Town05'
      - '/Game/Carla/Maps/Town04' -> 'Town04'

    Why:
      CARLA APIs sometimes return full map paths; our GT tables use 'TownXX'.
    """
    if not town_name:
        return town_name

    # keep only last token after '/' and remove extensions if any
    t = town_name.split('/')[-1]
    t = re.sub(r'\.\w+$', '', t)

    # normalize Town10HD mapping rule for GT lookup if needed
    return t


def town_key_for_gt(town_name: str) -> str:
    """
    Map town name to the GT table key.
    Current convention: Town10HD shares Town10's prior.
    """
    t = normalize_town_name(town_name)
    if t == 'Town10HD':
        return 'Town10'
    return t


def town_slug(town_name: str) -> str:
    """
    A lowercase slug for folder naming.
      Town10HD -> town10hd
      Carla/Maps/Town05 -> town05
    """
    return normalize_town_name(town_name).lower()


def make_segment_name(town_name: str, episode_idx: int) -> str:
    """
    Segment naming rule required by your pipeline:
      segment-town10hd-000

    Why:
      It keeps data organized by (town, episode) and allows easy resuming.
    """
    return f"segment-{town_slug(town_name)}-{episode_idx:03d}"


def parse_towns_arg(towns: Optional[str], fallback_town: str) -> List[str]:
    """
    Parse '--towns Town10HD,Town04,Town05' style input into a list.
    If towns is None or empty -> [fallback_town]
    """
    if towns is None:
        return [normalize_town_name(fallback_town)]
    items = [normalize_town_name(t.strip()) for t in towns.split(',') if t.strip()]
    return items if items else [normalize_town_name(fallback_town)]


def pick_town_for_episode(town_list: List[str],
                          episode_idx: int,
                          episode_start: int = 0,
                          mode: str = 'roundrobin',
                          rng: Optional[random.Random] = None) -> str:
    """
    Decide which town to use for a given episode.

    mode:
      - 'roundrobin': deterministic cycling, good for balanced coverage
      - 'random': random choice, good for mixed distribution

    This keeps multi-map scheduling logic out of main.py.
    """
    if not town_list:
        raise ValueError("town_list is empty")

    if mode == 'random':
        if rng is None:
            rng = random.Random(0)
        return rng.choice(town_list)

    # roundrobin
    idx = (episode_idx - episode_start) % len(town_list)
    return town_list[idx]


# ============================================================
# [OPT] Faster lookup cache for get_gt_lane_count / bad roads
# (optional but recommended if called frequently per-frame)
# ============================================================

_road_to_lane_count_cache = {}  # (town_key) -> dict[road_id] = lane_count
_bad_road_cache = {}            # (town_key) -> set(road_id)


def _build_cache_for_town(town_name: str):
    """
    Build O(1) lookup caches for a town.
    """
    tkey = town_key_for_gt(town_name)
    if tkey in _road_to_lane_count_cache:
        return

    if not hasattr(sys.modules[__name__], tkey):
        _road_to_lane_count_cache[tkey] = {}
        _bad_road_cache[tkey] = set()
        return

    town_cls = getattr(sys.modules[__name__], tkey)

    road2count = {}
    for count, road_ids in town_cls.lane_count.items():
        for rid in road_ids:
            road2count[int(rid)] = int(count)

    _road_to_lane_count_cache[tkey] = road2count
    _bad_road_cache[tkey] = set(int(r) for r in getattr(town_cls, "bad_road_ids", []))


def get_gt_lane_count_fast(town_name: str, road_id: int) -> int:
    """
    Fast O(1) version of get_gt_lane_count.
    Returns -1 if unknown.
    """
    _build_cache_for_town(town_name)
    tkey = town_key_for_gt(town_name)
    return _road_to_lane_count_cache.get(tkey, {}).get(int(road_id), -1)


def is_bad_road_id_fast(town_name: str, road_id: int) -> bool:
    """
    Fast O(1) version of is_bad_road_id.
    Returns False if town unknown.
    """
    _build_cache_for_town(town_name)
    tkey = town_key_for_gt(town_name)
    return int(road_id) in _bad_road_cache.get(tkey, set())

class Town01:
    """
    Town01 地图的先验标注信息

    lane_count:
        key   -> 车道数量（包含左右 curb）
        value -> 对应的 road_id 列表

    bad_road_ids:
        标记存在车道线质量问题的 road_id
    """
    # lane count (including curbs from both sides of the road): road ids
    lane_count = {
        3: [i for i in range(26)]
    }
    # road ids where there are errors in the lanes i.e misalignment or missing lane
    bad_road_ids = []


'''
Town 02 is skipped due to lane misalignment issues throughout the map
Town02 由于整张地图存在严重车道线错位问题，因此未提供 GT 数据
'''


class Town03:
    """
    Town03 地图的先验标注信息
    """
    # lane count (including curbs from both sides of the road): road ids
    lane_count = {
        5: [59, 62],
        7: [17, 18, 19, 20, 21, 22, 23, 41, 42, 43, 74, 75],
        8: [0, 1, 2, 3, 4, 5, 6, 7, 8, 65, 66, 67, 68, 69],
    }
    # road ids where there are errors in the lanes i.e misalignment or missing lane
    bad_road_ids = [7, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 24, 25, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 44, 46,
                    47, 48, 49, 50, 51, 52, 60, 61, 65, 66, 73, 75, 76, 77, 78, 79, 80]


class Town04:
    """
    Town04 地图的先验标注信息
    """
    # lane count (including curbs from both sides of the road): road ids
    lane_count = {
        2: [31, 33, 34, 44],
        3: [5, 14, 22, 23, 25],
        4: [1, 7, 8, 9, 18, 19, 20, 24, 32],
        5: [10, 11, 15, 16, 17, 26, 27, 28, 29, 30],
        10: [6, 35, 36, 38, 39, 40, 41, 45, 46, 47, 48, 49, 50]
    }
    # road ids where there are errors in the lanes i.e misalignment or missing lane
    bad_road_ids = [0, 2, 3, 4, 12, 13, 37, 42, 43, 51, 52]
    # missing: 21


class Town05:
    """
    Town05 地图的先验标注信息
    """
    # lane count (including curbs from both sides of the road): road ids
    lane_count = {
        5: [19, 20, 48],
        7: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 14, 15, 16, 17, 18, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31,
            32, 33, 39, 40, 41, 42, 43, 44, 45, 46, 47, 49, 50, 51, 52],
        10: [12, 34, 35, 36, 37, 38]
    }
    # road ids where there are errors in the lanes i.e misalignment or missing lane
    bad_road_ids = [7, 8, 19, 20, 22, 23, 48]


'''
Town 06 is skipped due to missing left curb throughout the map and lane class issues
Town06 因为全局缺失左侧 curb 且 lane 分类异常，因此未提供 GT
'''


class Town07:
    """
    Town07 地图的先验标注信息
    """
    # lane count (including curbs from both sides of the road): road ids
    lane_count = {
        0: [0, 1, 36, 37, 46, 47],
        2: [6, 9, 10, 31, 32, 40, 45, 49, 50],
        3: [7, 11, 20, 21, 34, 39, 41, 42, 43, 44, 52, 57, 58, 59, 60, 61, 62],
        4: [3, 12, 13, 14, 17, 23, 24, 25, 29, 38, 55, 56],
        5: [15]
    }
    # road ids where there are errors in the lanes i.e misalignment or missing lane
    bad_road_ids = [4, 5, 8, 16, 18, 25, 26, 27, 28, 33, 35, 51, 53]
    # missing: 2, 19, 22, 30, 48, 54


class Town10:
    """
    Town10 / Town10HD 地图的先验标注信息
    """
    # lane count (including curbs from both sides of the road): road ids
    lane_count = {
        5: [12],
        7: [0, 1, 2, 3, 4, 5, 6, 7, 8, 10, 13, 14, 15, 16, 17, 22],
        8: [18, 19, 20, 21]
    }
    # road ids where there are errors in the lanes i.e misalignment or missing lane
    bad_road_ids = [4, 9, 11, 18, 19, 20, 21]
