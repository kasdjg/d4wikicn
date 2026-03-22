"""
Maxroll Planner API 数据获取与解析模块
"""
import urllib.request
import ssl
import json
import re
from typing import Optional, Dict, List

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

API_BASE = "https://planners.maxroll.gg/profiles/d4"

# Maxroll 装备槽位映射
SLOT_MAP = {
    "4": "头盔",
    "5": "胸甲",
    "6": "副手",
    "7": "主手武器",
    "13": "手套",
    "14": "裤子",
    "15": "靴子",
    "16": "戒指1",
    "17": "戒指2",
    "18": "项链",
}

# 职业 ID 映射
CLASS_MAP = {
    0: "野蛮人",
    1: "德鲁伊",
    2: "潜行者",
    3: "术士",
    4: "死灵法师",
    5: "圣骑士",
    "Barbarian": "野蛮人",
    "Druid": "德鲁伊",
    "Rogue": "潜行者",
    "Sorcerer": "术士",
    "Necromancer": "死灵法师",
    "Paladin": "圣骑士",
}


def extract_build_id(url: str) -> str:
    """从 Maxroll URL 提取 build_id"""
    # 支持格式:
    # https://maxroll.gg/d4/planner/x61ej0y7
    # https://maxroll.gg/d4/planner/x61ej0y7#3
    # x61ej0y7
    match = re.search(r"(?:planner/)?([a-zA-Z0-9]+)(?:#\d+)?$", url.strip())
    if match:
        return match.group(1)
    return url.strip()


def fetch_build(build_id: str) -> dict:
    """从 Maxroll API 获取 build 数据"""
    url = f"{API_BASE}/{build_id}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=15) as response:
            return json.loads(response.read())
    except Exception as e:
        raise RuntimeError(f"无法获取 build 数据: {e}")


class MaxrollBuild:
    """解析后的 Maxroll Build 数据"""

    def __init__(self, raw_data: dict):
        self.raw = raw_data
        self.name = raw_data.get("name", "Unknown")
        self.class_en = raw_data.get("class", "Unknown")
        self.class_cn = CLASS_MAP.get(self.class_en, self.class_en)
        self.date = raw_data.get("date", "")

        # 解析嵌套 data
        inner = json.loads(raw_data["data"])
        self.profiles: List[dict] = inner.get("profiles", [])
        self.items_pool: Dict[str, dict] = inner.get("items", {})
        self.active_profile: int = inner.get("activeProfile", 0)

    def get_profile_names(self) -> List[str]:
        """获取所有配置方案名称"""
        return [p.get("name", f"Profile {i}") for i, p in enumerate(self.profiles)]

    def get_profile(self, index: int = None) -> dict:
        """获取指定配置方案（默认当前激活的）"""
        if index is None:
            index = self.active_profile
        if 0 <= index < len(self.profiles):
            return self.profiles[index]
        return self.profiles[0] if self.profiles else {}

    def get_equipped_items(self, profile_index: int = None) -> List[dict]:
        """
        获取某个配置方案的所有装备
        返回: [{"slot": "头盔", "slot_id": "4", "item_data": {...}}, ...]
        """
        profile = self.get_profile(profile_index)
        items_map = profile.get("items", {})

        equipped = []
        for slot_id, item_pool_id in items_map.items():
            item_data = self.items_pool.get(str(item_pool_id))
            if item_data:
                slot_name = SLOT_MAP.get(slot_id, f"槽位{slot_id}")
                equipped.append({
                    "slot": slot_name,
                    "slot_id": slot_id,
                    "item_data": item_data,
                })

        # 按槽位排序: 头盔、胸甲、主手、副手、手套、裤子、鞋子、项链(18)、戒指1(16)、戒指2(17)
        slot_order = ["4", "5", "7", "6", "13", "14", "15", "18", "16", "17"]
        equipped.sort(key=lambda x: slot_order.index(x["slot_id"]) if x["slot_id"] in slot_order else 99)
        return equipped

    def get_skill_tree(self, profile_index: int = None) -> Optional[dict]:
        """获取技能树数据"""
        profile = self.get_profile(profile_index)
        return profile.get("skillTree", {})

    def get_skill_bar(self, profile_index: int = None) -> Optional[list]:
        """获取技能栏数据"""
        profile = self.get_profile(profile_index)
        return profile.get("skillBar", [])

    def get_paragon(self, profile_index: int = None) -> Optional[dict]:
        """获取巅峰面板数据"""
        profile = self.get_profile(profile_index)
        return profile.get("paragon", {})
