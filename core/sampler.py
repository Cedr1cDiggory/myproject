import os
import json
import collections
import random
import numpy as np

class DataSampler:
    def __init__(self, args):
        self.args = args
        self.balance_lane = args.balance_lane_count
        self.prefer_junction = args.prefer_junction
        self.weather_quota = args.weather_quota  # 如果是 None 则不限制
        
        # 数据统计容器
        # 结构: self.stats[town][category][key] = {'scanned': 0, 'saved': 0}
        self.stats = collections.defaultdict(
            lambda: collections.defaultdict(
                lambda: collections.defaultdict(lambda: {'scanned': 0, 'saved': 0})
            )
        )
        
        # 全局计数 (用于快速计算均值)
        self.global_lane_counts = collections.defaultdict(int) # {lane_num: saved_count}

    def check_and_update(self, town, weather, lane_count, road_id, is_junction, simulate=True):
        """
        核心决策逻辑
        Args:
            simulate: True 表示只检查不更新(用于决策), False 表示确认保存(更新计数)
        Returns:
            bool: 是否应该保存
        """
        # 1. 记录总扫描量 (Scanned)
        if not simulate:
            self._update_stat(town, 'lane_count', lane_count, 'scanned')
            self._update_stat(town, 'weather', weather, 'scanned')
            self._update_stat(town, 'road_id', road_id, 'scanned')
            if is_junction:
                self._update_stat(town, 'scene', 'junction', 'scanned')
        
        # --- 决策逻辑 ---
        
        # A. 天气配额 (Weather Quota)
        # 如果该天气下的保存数量已经超过配额，且没有强制保存理由，则丢弃
        if self.weather_quota is not None:
            current_weather_saved = self.stats[town]['weather'][weather]['saved']
            if current_weather_saved >= self.weather_quota:
                return False

        # B. 路口优先 (Prefer Junction)
        # 如果是路口，且开启了优先模式，直接通过 (除非被天气配额一票否决)
        if self.prefer_junction and is_junction:
            if not simulate:
                self._commit_save(town, weather, lane_count, road_id, is_junction)
            return True

        # C. 车道数均衡 (Lane Count Balancing)
        # 使用“动态拒绝采样”算法
        if self.balance_lane and self.global_lane_counts:
            current_count = self.global_lane_counts[lane_count]
            values = list(self.global_lane_counts.values())
            avg_count = sum(values) / len(values) if values else 0
            
            # 如果当前类别的数量 显著超过 平均值 (例如 1.5倍)，则概率性丢弃
            if avg_count > 10 and current_count > avg_count * 1.5:
                # 丢弃概率与超出的比例成正比
                drop_prob = 1.0 - (avg_count / current_count)
                if random.random() < drop_prob:
                    return False

        # 默认通过
        if not simulate:
            self._commit_save(town, weather, lane_count, road_id, is_junction)
        
        return True

    def commit(self, town, weather, lane_count, road_id, is_junction):
        """确认保存后调用，更新 Saved 计数"""
        self._commit_save(town, weather, lane_count, road_id, is_junction)

    def _commit_save(self, town, weather, lane_count, road_id, is_junction):
        self._update_stat(town, 'lane_count', lane_count, 'saved')
        self._update_stat(town, 'weather', weather, 'saved')
        self._update_stat(town, 'road_id', road_id, 'saved')
        if is_junction:
            self._update_stat(town, 'scene', 'junction', 'saved')
        
        self.global_lane_counts[lane_count] += 1

    def _update_stat(self, town, category, key, metric):
        self.stats[town][category][key][metric] += 1

    def save_report(self, output_path):
        """生成详细的 JSON 报告"""
        report = {}
        
        for town, categories in self.stats.items():
            report[town] = {}
            for cat, items in categories.items():
                report[town][cat] = {}
                
                # 计算该类别下的总保存数，用于计算占比
                total_saved_in_cat = sum(v['saved'] for v in items.values())
                
                for key, metrics in items.items():
                    scanned = metrics['scanned']
                    saved = metrics['saved']
                    
                    # 占比 (Ratio): 占该类总数的百分比
                    ratio = (saved / total_saved_in_cat) if total_saved_in_cat > 0 else 0.0
                    # 保存率 (Save Rate): 扫描多少帧里存了多少帧
                    save_rate = (saved / scanned) if scanned > 0 else 0.0
                    
                    report[town][cat][key] = {
                        "scanned": scanned,
                        "saved": saved,
                        "ratio": round(ratio, 4),
                        "save_rate": round(save_rate, 4)
                    }

        with open(output_path, 'w') as f:
            json.dump(report, f, indent=4, sort_keys=True)
        
        print(f"[Sampler] Report saved to: {output_path}")