"""
数据加载模块
从管线产出的 JSON 文件构建中英文对照映射表
"""
import json
import os
import re
from typing import Dict, List, Optional, Tuple

# 数据文件目录
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "raw")


class D4Database:
    """暗黑4本地化数据库"""

    def __init__(self):
        # 词条映射: {nid_str: {"en": "...", "cn": "..."}}
        self.affixes: Dict[str, dict] = {}
        # 暗金装备映射: {IdName: {"en_name": "...", "cn_name": "...", "en_desc": "...", "cn_desc": "..."}}
        self.uniques: Dict[str, dict] = {}
        # 同时用 IdSno 索引暗金
        self.uniques_by_sno: Dict[str, dict] = {}
        # 传奇特效映射: {IdName: {"en_name": "...", "cn_name": "...", ...}}
        self.aspects: Dict[str, dict] = {}
        self.aspects_by_sno: Dict[str, dict] = {}
        # 装备类型映射
        self.item_types: Dict[str, dict] = {}
        # 装备基底名映射: {"Boots_Legendary_Generic_053": {"en_name": "Runic Cleats", "cn_name": "符文钉鞋"}}
        self.base_items: Dict[str, dict] = {}
        # 巅峰面板
        self.paragon_boards: Dict[str, dict] = {}
        self.paragon_glyphs: Dict[str, dict] = {}
        # 符文映射: {"Rune_Condition_XXX": {"en_name": "Ahu", "cn_name": "阿胡", "en_desc": "...", "cn_desc": "..."}}
        self.runes: Dict[str, dict] = {}
        # 静态值映射 (管线步骤④提取): {IdName: [val0, val1, ...]}
        self.static_values: Dict[str, list] = {}

        self._load_all()

    def _load_json_dict(self, filename: str) -> dict:
        """加载 JSON 文件（dict 格式）"""
        path = os.path.join(DATA_DIR, filename)
        if not os.path.exists(path):
            print(f"  警告: 文件不存在 {filename}")
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _load_json(self, filename: str) -> list:
        """加载 JSON 文件"""
        path = os.path.join(DATA_DIR, filename)
        if not os.path.exists(path):
            print(f"  警告: 文件不存在 {filename}")
            return []
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _load_all(self):
        """加载所有数据文件"""
        print("正在加载本地化数据库...")
        self._load_affixes()
        self._load_uniques()
        self._load_aspects()
        self._load_item_types()
        self._load_base_items()
        self._load_paragons()
        self._load_runes()
        self._load_static_values()
        print(f"  词条(Affixes): {len(self.affixes)} 个 nid")
        print(f"  暗金(Uniques): {len(self.uniques)} 件")
        print(f"  传奇特效(Aspects): {len(self.aspects)} 个")
        print(f"  装备类型(ItemTypes): {len(self.item_types)} 种")
        print(f"  装备基底(BaseItems): {len(self.base_items)} 个")
        print(f"  巅峰(Paragon): {len(self.paragon_boards)} 面板, {len(self.paragon_glyphs)} 雕文")
        print(f"  静态值(StaticValues): {len(self.static_values)} 个")
        print("数据库加载完成!")

    def _load_affixes(self):
        """加载词条数据，用 IdSno 建立映射"""
        en_list = self._load_json("Affixes.enUS.json")
        cn_list = self._load_json("Affixes.zhCN.json")

        # 用 IdSno 构建 CN 映射
        cn_by_sno = {}
        for item in cn_list:
            for sno in item.get("IdSnoList", []):
                cn_by_sno[str(sno)] = item

        # 遍历 EN 数据，与 CN 配对
        for en_item in en_list:
            # 从 AffixAttributes 的 Localisation 解析值乘数
            # 例如 Localisation: "+[{VALUE}*100|1%|]" 表示值需要 ×100
            multiply_100 = self._parse_affix_multipliers(en_item)

            for sno in en_item.get("IdSnoList", []):
                sno_str = str(sno)
                cn_item = cn_by_sno.get(sno_str, {})
                self.affixes[sno_str] = {
                    "en": en_item.get("Description", ""),
                    "cn": cn_item.get("Description", ""),
                    "en_clean": en_item.get("DescriptionClean", ""),
                    "cn_clean": cn_item.get("DescriptionClean", ""),
                    "id_name": en_item.get("IdName", ""),
                    "multiply_100": multiply_100,
                }

    def _load_uniques(self):
        """加载暗金装备数据"""
        en_list = self._load_json("Uniques.enUS.json")
        cn_list = self._load_json("Uniques.zhCN.json")

        # 用 IdSno 建立 CN 映射
        cn_by_sno = {}
        for item in cn_list:
            for sno in item.get("IdSnoList", []):
                cn_by_sno[str(sno)] = item
        # 也用 IdName 建立映射
        cn_by_name = {}
        for item in cn_list:
            for name in item.get("IdNameList", []):
                cn_by_name[name] = item
            # 也用 IdNameItem
            for name in item.get("IdNameItemList", []):
                cn_by_name[name] = item

        for en_item in en_list:
            id_name = en_item.get("IdName", "")
            id_name_item = en_item.get("IdNameItem", id_name)
            cn_item = cn_by_name.get(id_name, cn_by_name.get(id_name_item, {}))

            # 获取 CN Localisation（也通过 IdSno 查找）
            if not cn_item:
                for sno in en_item.get("IdSnoList", []):
                    cn_item = cn_by_sno.get(str(sno), {})
                    if cn_item:
                        break

            entry = {
                "en_name": en_item.get("Name", ""),
                "cn_name": cn_item.get("Name", en_item.get("Name", "")),
                "en_desc": en_item.get("Description", ""),
                "cn_desc": cn_item.get("Description", ""),
                "en_desc_clean": en_item.get("DescriptionClean", ""),
                "cn_desc_clean": cn_item.get("DescriptionClean", ""),
                "en_loc": en_item.get("Localisation", ""),
                "cn_loc": cn_item.get("Localisation", ""),
                "class": en_item.get("AllowedForPlayerClass", []),
                "item_type": en_item.get("ItemType", ""),
                "mythic": en_item.get("MythicUniqueItem", False) or en_item.get("MagicType") == 4,
            }

            # 多种索引方式
            self.uniques[id_name] = entry
            self.uniques[id_name_item] = entry
            for name in en_item.get("IdNameList", []):
                self.uniques[name] = entry
            for name in en_item.get("IdNameItemList", []):
                self.uniques[name] = entry
            for sno in en_item.get("IdSnoList", []):
                self.uniques_by_sno[str(sno)] = entry

    def _load_aspects(self):
        """加载传奇特效数据"""
        en_list = self._load_json("Aspects.enUS.json")
        cn_list = self._load_json("Aspects.zhCN.json")

        cn_by_sno = {}
        for item in cn_list:
            for sno in item.get("IdSnoList", []):
                cn_by_sno[str(sno)] = item
        cn_by_name = {}
        for item in cn_list:
            for name in item.get("IdNameList", []):
                cn_by_name[name] = item

        for en_item in en_list:
            id_name = en_item.get("IdName", "")
            cn_item = cn_by_name.get(id_name, {})
            if not cn_item:
                for sno in en_item.get("IdSnoList", []):
                    cn_item = cn_by_sno.get(str(sno), {})
                    if cn_item:
                        break

            entry = {
                "id_name": id_name,
                "en_name": en_item.get("Name", ""),
                "cn_name": cn_item.get("Name", ""),
                "en_desc": en_item.get("Description", ""),
                "cn_desc": cn_item.get("Description", ""),
                "en_desc_clean": en_item.get("DescriptionClean", ""),
                "cn_desc_clean": cn_item.get("DescriptionClean", ""),
                "en_loc": en_item.get("Localisation", ""),
                "cn_loc": cn_item.get("Localisation", ""),
            }

            self.aspects[id_name] = entry
            for name in en_item.get("IdNameList", []):
                self.aspects[name] = entry
            for sno in en_item.get("IdSnoList", []):
                self.aspects_by_sno[str(sno)] = entry

    def _load_item_types(self):
        """加载装备类型数据"""
        en_list = self._load_json("ItemTypes.enUS.json")
        cn_list = self._load_json("ItemTypes.zhCN.json")

        # 新格式: {"Name": "Common Amulet", "Type": "amulet"}
        # 旧格式: {"IdName": "...", "Name": "..."}
        # 兼容两种格式
        cn_by_type = {}
        cn_by_name = {}
        for item in cn_list:
            t = item.get("Type", "")
            if t:
                cn_by_type[t] = item
            idn = item.get("IdName", "")
            if idn:
                cn_by_name[idn] = item

        for en_item in en_list:
            # 优先用 Type 字段，回退到 IdName
            id_key = en_item.get("Type", "") or en_item.get("IdName", "")
            if not id_key:
                continue
            cn_item = cn_by_type.get(id_key, {}) or cn_by_name.get(id_key, {})
            # 避免同一 Type 重复覆盖（保留第一个即可）
            if id_key not in self.item_types:
                self.item_types[id_key] = {
                    "en_name": en_item.get("Name", ""),
                    "cn_name": cn_item.get("Name", en_item.get("Name", "")),
                }

    def _load_base_items(self):
        """加载装备基底名称数据（由 extract_base_items.py 生成）"""
        en_dict = self._load_json_dict("BaseItems.enUS.json")
        cn_dict = self._load_json_dict("BaseItems.zhCN.json")

        for item_id, en_name in en_dict.items():
            self.base_items[item_id] = {
                "en_name": en_name,
                "cn_name": cn_dict.get(item_id, en_name),
            }
        # 补充仅中文有的条目
        for item_id, cn_name in cn_dict.items():
            if item_id not in self.base_items:
                self.base_items[item_id] = {
                    "en_name": item_id,
                    "cn_name": cn_name,
                }

    def _load_paragons(self):
        """加载巅峰面板数据"""
        en_boards = self._load_json("ParagonBoards.enUS.json")
        cn_boards = self._load_json("ParagonBoards.zhCN.json")

        cn_by_name = {}
        for item in cn_boards:
            cn_by_name[item.get("IdName", "")] = item

        for en_item in en_boards:
            id_name = en_item.get("IdName", "")
            cn_item = cn_by_name.get(id_name, {})
            self.paragon_boards[id_name] = {
                "en_name": en_item.get("Name", ""),
                "cn_name": cn_item.get("Name", ""),
            }

        en_glyphs = self._load_json("ParagonGlyphs.enUS.json")
        cn_glyphs = self._load_json("ParagonGlyphs.zhCN.json")

        cn_by_name = {}
        for item in cn_glyphs:
            cn_by_name[item.get("IdName", "")] = item

        for en_item in en_glyphs:
            id_name = en_item.get("IdName", "")
            cn_item = cn_by_name.get(id_name, {})
            self.paragon_glyphs[id_name] = {
                "en_name": en_item.get("Name", ""),
                "cn_name": cn_item.get("Name", ""),
            }

    def _load_runes(self):
        """加载符文数据"""
        en_list = self._load_json("Runes.enUS.json")
        cn_list = self._load_json("Runes.zhCN.json")

        cn_by_idname = {}
        for item in cn_list:
            cn_by_idname[item.get("IdName", "")] = item

        for en_item in en_list:
            id_name = en_item.get("IdName", "")
            cn_item = cn_by_idname.get(id_name, {})

            entry = {
                "en_name": en_item.get("Name", ""),
                "cn_name": cn_item.get("Name", en_item.get("Name", "")),
                "en_desc": en_item.get("Description", en_item.get("DescriptionClean", "")),
                "cn_desc": cn_item.get("Description", cn_item.get("DescriptionClean", "")),
                "type": en_item.get("RuneType", ""),
            }

            # 多种 key: "Item_Rune_Condition_XXX" 和 "Rune_Condition_XXX"
            self.runes[id_name] = entry
            # Maxroll 使用不带 "Item_" 前缀的名称
            short_name = id_name.replace("Item_", "", 1)
            self.runes[short_name] = entry

    def _load_static_values(self):
        """
        加载 Static Values 数据（由管线步骤④从 .aff.json 提取生成）
        这些是 Aspect/Unique 描述中的固定数值（如秒数、次数等），
        对应 Localisation 中的 Affix."Static Value 0"、Affix."Static Value 1" 等占位符
        """
        path = os.path.join(DATA_DIR, "StaticValues.json")
        if not os.path.exists(path):
            print("  警告: StaticValues.json 不存在，Static Value 将显示为 #")
            print("  提示: 请在管理后台执行数据管线步骤④以生成此文件")
            return
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            self.static_values = data

    @staticmethod
    def _parse_affix_multipliers(en_item: dict) -> bool:
        """
        从 AffixAttributes 的 Localisation 字段解析是否需要 ×100
        例如: Localisation: "+[{VALUE}*100|1%|]" → True (需要 ×100)
              Localisation: "+[{VALUE} * 100|1%|]" → True (有空格也要匹配)
              Localisation: "+[{VALUE}]" → False (不需要)
        """
        attrs = en_item.get("AffixAttributes", [])
        for attr in attrs:
            loc = attr.get("Localisation", "")
            # 检查 Localisation 中是否包含 *100 或 * 100 模式（可能有空格）
            # 使用正则匹配 \*\s*100
            if re.search(r'\*\s*100', loc):
                return True
        return False

    # 宝石等级名称映射
    GEM_NAMES = {
        "Emerald": ("Emerald", "翡翠"),
        "Ruby": ("Ruby", "红宝石"),
        "Diamond": ("Diamond", "钻石"),
        "Topaz": ("Topaz", "黄宝石"),
        "Sapphire": ("Sapphire", "蓝宝石"),
        "Amethyst": ("Amethyst", "紫宝石"),
        "Skull": ("Skull", "头骨"),
    }

    def get_socket_display(self, socket_id: str) -> str:
        """将镶嵌 ID 翻译为可读名称"""
        # 先查符文
        rune = self.runes.get(socket_id)
        if rune:
            rune_type = "触发" if rune["type"] == "condition" else "效果"
            cn_name = rune["cn_name"]
            en_name = rune["en_name"]
            cn_desc = rune["cn_desc"]
            return f"[{rune_type}符文] {cn_name} ({en_name}) — {cn_desc}" if cn_desc else f"[{rune_type}符文] {cn_name} ({en_name})"

        # 宝石: 格式 Gem_Emerald_06
        if socket_id.startswith("Gem_"):
            parts = socket_id.split("_")
            if len(parts) >= 2:
                gem_type = parts[1]
                gem_info = self.GEM_NAMES.get(gem_type)
                if gem_info:
                    return f"{gem_info[1]} ({gem_info[0]})"
            return socket_id

        return socket_id

    def get_affix_cn(self, nid: int, values: list = None) -> Tuple[str, str]:
        """
        通过 nid 获取词条的中英文描述
        返回 (英文, 中文)，并将 # 替换为实际数值
        
        百分比转换逻辑：
        使用 AffixAttributes.Localisation 中的 *100 标记来判断
        Maxroll 存储的是游戏内部值（分数形式），需要 ×100 才能得到显示值
        例如: 内部值 0.35 → 显示 35%，内部值 2 → 显示 200%
        """
        nid_str = str(nid)
        affix = self.affixes.get(nid_str)
        if not affix:
            return (f"[未知词条 nid={nid}]", f"[未知词条 nid={nid}]")

        en_text = affix["en"]
        cn_text = affix["cn"]
        need_multiply = affix.get("multiply_100", False)

        # 替换 # 占位符为实际数值
        if values:
            for val in values:
                actual_val = val
                is_pct = False

                # 根据 AffixAttributes.Localisation 的 *100 标记决定是否乘以 100
                if need_multiply:
                    hash_pos = en_text.find("#")
                    if hash_pos >= 0 and hash_pos + 1 < len(en_text) and en_text[hash_pos + 1] == "%":
                        is_pct = True
                        # 保护：Maxroll 对部分值已预乘，若值 >= 10 且乘后 > 1000 则跳过
                        candidate = val * 100
                        if abs(val) < 10 or abs(candidate) <= 1000:
                            actual_val = candidate

                # 检查模板中当前 # 是否跟 % (用英文模板判断)
                if not is_pct:
                    hash_pos = en_text.find("#")
                    if hash_pos >= 0 and hash_pos + 1 < len(en_text) and en_text[hash_pos + 1] == "%":
                        is_pct = True

                # 格式化数值：百分比保留1位小数，整数值四舍五入
                if isinstance(actual_val, float):
                    if is_pct:
                        rounded = round(actual_val, 1)
                        if rounded == int(rounded):
                            val_str = str(int(rounded))
                        else:
                            val_str = f"{rounded:.1f}"
                    else:
                        val_str = str(round(actual_val))
                else:
                    val_str = str(actual_val)
                en_text = en_text.replace("#", val_str, 1)
                cn_text = cn_text.replace("#", val_str, 1)

        return (en_text, cn_text)

    def get_unique_info(self, item_id: str) -> Optional[dict]:
        """通过装备 ID 名获取暗金装备信息"""
        return self.uniques.get(item_id)

    def get_aspect_info(self, aspect_id: str) -> Optional[dict]:
        """通过特效 ID 获取传奇特效信息"""
        return self.aspects.get(aspect_id) or self.aspects_by_sno.get(str(aspect_id))


# 单例
_db_instance = None

def get_database() -> D4Database:
    """获取数据库单例"""
    global _db_instance
    if _db_instance is None:
        _db_instance = D4Database()
    return _db_instance
