"""
核心翻译引擎
将 Maxroll build 数据翻译为中文
"""
import re
from typing import List, Dict, Optional, Tuple
from .data_loader import D4Database, get_database
from .maxroll_api import MaxrollBuild


# 从 item_id 前缀推断精确装备子类型
ITEM_ID_SUBTYPE = {
    "1HAxe": ("斧", "Axe"),
    "1HDagger": ("匕首", "Dagger"),
    "1HFocus": ("聚能器", "Focus"),
    "1HMace": ("钉锤", "Mace"),
    "1HScythe": ("镰刀", "Scythe"),
    "1HShield": ("盾", "Shield"),
    "1HSword": ("剑", "Sword"),
    "1HTotem": ("图腾", "Totem"),
    "1HWand": ("魔杖", "Wand"),
    "2HAxe": ("双手斧", "Two-Handed Axe"),
    "2HBow": ("弓", "Bow"),
    "2HCrossbow": ("弩", "Crossbow"),
    "2HGlaive": ("剑刃戟", "Glaive"),
    "2HMace": ("双手钉锤", "Two-Handed Mace"),
    "2HPolearm": ("长柄武器", "Polearm"),
    "2HQuarterstaff": ("长杖", "Quarterstaff"),
    "2HScythe": ("双手镰刀", "Two-Handed Scythe"),
    "2HStaff": ("杖", "Staff"),
    "2HSword": ("双手剑", "Two-Handed Sword"),
    "Boots": ("靴子", "Boots"),
    "Helm": ("头盔", "Helm"),
    "Chest": ("胸甲", "Chest Armor"),
    "Gloves": ("手套", "Gloves"),
    "Pants": ("裤子", "Pants"),
    "Amulet": ("护符", "Amulet"),
    "Ring": ("戒指", "Ring"),
}


def _get_subtype(item_id: str) -> Tuple[str, str]:
    """从 item_id 推断精确装备子类型，返回 (cn, en)"""
    prefix = item_id.split("_")[0]
    return ITEM_ID_SUBTYPE.get(prefix, ("", ""))


class TranslatedItem:
    """翻译后的单件装备"""

    def __init__(self):
        self.slot: str = ""           # 槽位名（中文）
        self.item_id: str = ""        # 原始 ID
        self.en_name: str = ""        # 英文装备名
        self.cn_name: str = ""        # 中文装备名
        self.is_unique: bool = False  # 是否暗金
        self.is_mythic: bool = False  # 是否神话
        self.is_ancestral: bool = False  # 是否先祖
        self.power: int = 0           # 物品等级
        self.upgrade: int = 0         # 强化等级
        self.item_subtype: str = ""   # 精确装备子类型中文（如"聚能器"）
        self.item_subtype_en: str = "" # 精确装备子类型英文
        self.implicits: List[dict] = []   # 固有词条 [{en, cn}]
        self.explicits: List[dict] = []   # 随机词条 [{en, cn, greater}]
        self.tempered: List[dict] = []    # 淬炼词条 [{en, cn}]
        self.aspects: List[dict] = []     # 传奇特效 [{en_name, cn_name, en_desc, cn_desc}]
        self.unique_effect_en: str = ""   # 暗金特效英文
        self.unique_effect_cn: str = ""   # 暗金特效中文
        self.sockets: List[dict] = []     # 镶嵌


class TranslatedBuild:
    """翻译后的完整 Build"""

    def __init__(self):
        self.build_name: str = ""
        self.class_en: str = ""
        self.class_cn: str = ""
        self.profile_name: str = ""
        self.items: List[TranslatedItem] = []


def translate_build(build: MaxrollBuild, profile_index: int = None) -> TranslatedBuild:
    """
    翻译一个 Maxroll Build
    """
    db = get_database()
    result = TranslatedBuild()
    result.build_name = build.name
    result.class_en = build.class_en
    result.class_cn = build.class_cn

    profile = build.get_profile(profile_index)
    result.profile_name = profile.get("name", "Default")

    equipped = build.get_equipped_items(profile_index)

    for equip in equipped:
        item = _translate_item(equip, db)
        result.items.append(item)

    return result


def _format_value(val, is_percent: bool = False) -> str:
    """
    格式化数值为字符串
    is_percent=True: 百分比，保留1位小数（如 131.3%）
    is_percent=False: 整数值，四舍五入（如 151、571）
    """
    if isinstance(val, float):
        if is_percent:
            rounded = round(val, 1)
            if rounded == int(rounded):
                return str(int(rounded))
            return f"{rounded:.1f}"
        else:
            return str(round(val))
    return str(val)


def _replace_hashes(template: str, values: list) -> str:
    """
    将模板中的 # 替换为数值
    智能匹配：分析每个 # 是否后跟 %，尝试将值匹配到合适的位置
    """
    if not values:
        return template

    # 分析模板中每个 # 的类型（是否后跟 %）
    placeholders = []  # [(position, is_percent)]
    pos = 0
    temp = template
    while True:
        idx = temp.find("#", pos)
        if idx < 0:
            break
        is_pct = (idx + 1 < len(temp) and temp[idx + 1] == "%")
        placeholders.append((idx, is_pct))
        pos = idx + 1

    if len(placeholders) == 0:
        return template

    # 如果值和占位符数量相等，尝试智能排序
    if len(values) == len(placeholders):
        ordered_values = _smart_order_values(placeholders, values)
    else:
        ordered_values = values

    # 按顺序替换，根据 # 后是否跟 % 决定取整方式
    result = template
    for val in ordered_values:
        hash_pos = result.find("#")
        if hash_pos < 0:
            break
        is_pct = (hash_pos + 1 < len(result) and result[hash_pos + 1] == "%")
        val_str = _format_value(val, is_percent=is_pct)
        result = result[:hash_pos] + val_str + result[hash_pos + 1:]
    return result


def _smart_order_values(placeholders: list, values: list) -> list:
    """
    尝试智能匹配值到占位符
    规则：
    - # (非百分比) 通常是小数值（个数、秒数等，一般 < 10）
    - #% (百分比) 通常是较大数值（百分比，一般 > 5）
    如果直接顺序明显不合理（非%位得到大值，%位得到小值），尝试重排
    """
    if len(values) != len(placeholders) or len(values) <= 1:
        return values

    # 检查当前顺序是否合理
    if _order_seems_reasonable(placeholders, values):
        return values

    # 尝试将较小的值分配给非%位，较大的值分配给%位
    pct_indices = [i for i, (_, is_pct) in enumerate(placeholders) if is_pct]
    non_pct_indices = [i for i, (_, is_pct) in enumerate(placeholders) if not is_pct]

    if not pct_indices or not non_pct_indices:
        return values  # 全部同类型，无法判断

    # 按大小排序值
    sorted_vals = sorted(values)
    result = [None] * len(values)

    # 较小的值给非%位，较大的值给%位
    small_vals = sorted_vals[:len(non_pct_indices)]
    large_vals = sorted_vals[len(non_pct_indices):]

    for i, idx in enumerate(non_pct_indices):
        if i < len(small_vals):
            result[idx] = small_vals[i]
    for i, idx in enumerate(pct_indices):
        if i < len(large_vals):
            result[idx] = large_vals[i]

    # 填补空位
    if None in result:
        return values
    return result


def _order_seems_reasonable(placeholders: list, values: list) -> bool:
    """检查值的顺序是否合理"""
    for i, (_, is_pct) in enumerate(placeholders):
        if i >= len(values):
            break
        val = values[i]
        if not is_pct and val > 20:
            # 非百分比位得到大于20的值，可能不合理
            return False
        if is_pct and val < 1:
            # 百分比位得到小于1的值，可能不合理
            return False
    return True


def _count_hashes(template: str) -> int:
    """计算模板中 # 占位符的数量"""
    return template.count("#")


# ============================================================
# Localisation 感知的智能 # 替换
# ============================================================

def _parse_loc_placeholders(loc_str: str) -> list:
    """
    解析 Localisation 字符串，按出现顺序提取占位符规格。
    
    Localisation 示例:
      {c_random}[Affix_Value_1|%x|]{/c}          → 可变值 (来自 API values)
      {c_number}[Affix."Static Value 0"]{/c}      → 固定值 (游戏常量，API 不提供)
      {c_random}[Affix_Value_2 * 100%|%x|]{/c}    → 可变值，需乘以 100
      {c_random}[Affix_Value_1 * Affix."Static Value 0"|%x|]{/c} → 混合 (无法精确计算)
    
    返回: [{"type": "variable"|"static"|"mixed", "idx": N, "mult100": bool}, ...]
    """
    if not loc_str:
        return []

    # 匹配 {c_XXX}[FORMULA]{/c} 或 {c_XXX}[FORMULA|FORMAT|]{/c}
    pattern = r'\{c_\w+\}\[([^\]]+)\]\{/c[_\w]*\}'
    specs = []
    for m in re.finditer(pattern, loc_str):
        formula = m.group(1)
        # 去除尾部格式说明符 (|%x|, |%+|, |%| 等)
        formula_core = re.sub(r'\|[^|]*\|$', '', formula).strip()

        value_match = re.search(r'Affix_Value_(\d+)', formula_core)
        static_match = re.search(r'Affix\.\s*"Static Value (\d+)"', formula_core)

        if value_match and not static_match:
            # 纯可变值: Affix_Value_N
            idx = int(value_match.group(1)) - 1  # 1-indexed → 0-indexed
            has_mult = bool(re.search(r'\*\s*100', formula_core))
            # 检测武器伤害公式（含 Owner.Weapon_Damage）
            has_weapon_dmg = bool(re.search(r'Owner\.Weapon_Damage', formula_core))
            specs.append({"type": "variable", "idx": idx, "mult100": has_mult, "weapon_dmg": has_weapon_dmg})
        elif static_match and not value_match:
            # 纯固定值: Affix."Static Value N"
            static_idx = int(static_match.group(1))
            specs.append({"type": "static", "static_idx": static_idx})
        elif value_match and static_match:
            # 混合公式: Affix_Value_N * Affix."Static Value M"
            # 可以精确计算: value * static_value
            idx = int(value_match.group(1)) - 1
            static_idx = int(static_match.group(1))
            specs.append({"type": "mixed", "idx": idx, "static_idx": static_idx})
        else:
            # 其他复杂公式（如武器伤害计算），尝试提取 Affix_Value
            val_m = re.search(r'Affix_Value_(\d+)', formula)
            if val_m:
                idx = int(val_m.group(1)) - 1
                specs.append({"type": "variable", "idx": idx, "mult100": False})
            else:
                # 尝试提取 static value index
                sv_m = re.search(r'Affix\.\s*"Static Value (\d+)"', formula)
                if sv_m:
                    specs.append({"type": "static", "static_idx": int(sv_m.group(1))})
                else:
                    specs.append({"type": "static"})

    return specs


def _replace_with_loc(template: str, loc_str: str, values: list, static_values: list = None) -> str:
    """
    使用 Localisation 信息智能替换 Description 中的 # 占位符。
    
    - 可变值 (Affix_Value_N): 用 API values 中对应位置的值替换
    - 固定值 (Static Value N): 用 static_values[N] 替换（来自 d4data 的 arStaticValues）
    - 混合公式: 保留为 # (无法精确计算)
    
    这解决了中英文模板中 # 占位符顺序不同的问题。
    """
    if not values:
        return template

    specs = _parse_loc_placeholders(loc_str)
    if not specs:
        # 无法解析 Localisation，回退到旧的顺序替换
        return _replace_hashes(template, values)

    if static_values is None:
        static_values = []

    result = template
    for spec in specs:
        hash_pos = result.find('#')
        if hash_pos < 0:
            break

        # 判断当前 # 后是否跟 % — 决定取整方式
        is_pct = (hash_pos + 1 < len(result) and result[hash_pos + 1] == "%")

        if spec["type"] == "variable":
            idx = spec["idx"]
            if idx < len(values):
                val = values[idx]
                if spec.get("mult100"):
                    val = val * 100
                    is_pct = True  # mult100 的一定是百分比
                if spec.get("weapon_dmg"):
                    # 武器伤害公式：值是乘数而非显示值，无法精确计算
                    # 保留 # 让前端知道这是动态值
                    result = result[:hash_pos] + '\x00' + result[hash_pos + 1:]
                else:
                    val_str = _format_value(val, is_percent=is_pct)
                    result = result[:hash_pos] + val_str + result[hash_pos + 1:]
            else:
                result = result[:hash_pos] + '\x00' + result[hash_pos + 1:]
        elif spec["type"] == "static" and "static_idx" in spec:
            sidx = spec["static_idx"]
            if sidx < len(static_values):
                val = static_values[sidx]
                val_str = _format_value(val, is_percent=is_pct)
                result = result[:hash_pos] + val_str + result[hash_pos + 1:]
            else:
                result = result[:hash_pos] + '\x00' + result[hash_pos + 1:]
        elif spec["type"] == "mixed" and "idx" in spec and "static_idx" in spec:
            idx = spec["idx"]
            sidx = spec["static_idx"]
            if idx < len(values) and sidx < len(static_values):
                val = values[idx] * static_values[sidx]
                val_str = _format_value(val, is_percent=is_pct)
                result = result[:hash_pos] + val_str + result[hash_pos + 1:]
            else:
                result = result[:hash_pos] + '\x00' + result[hash_pos + 1:]
        else:
            result = result[:hash_pos] + '\x00' + result[hash_pos + 1:]

    # 恢复跳过的占位符为 #
    result = result.replace('\x00', '#')
    return result


# ============================================================
# 传奇装备中文命名
# ============================================================

# 槽位 → 中文装备类型 (基底名查找失败时的兜底)
SLOT_TYPE_CN = {
    "头盔": "头盔",
    "胸甲": "胸甲",
    "手套": "手套",
    "裤子": "裤子",
    "靴子": "靴子",
    "主手武器": "武器",
    "副手": "副手",
    "项链": "项链",
    "戒指1": "戒指",
    "戒指2": "戒指",
}



def _translate_item(equip: dict, db: D4Database) -> TranslatedItem:
    """翻译单件装备"""
    item = TranslatedItem()
    item.slot = equip["slot"]
    item_data = equip["item_data"]

    item.item_id = item_data.get("id", "")
    item.power = item_data.get("power", 0)
    item.upgrade = item_data.get("upgrade", 0)

    # 先祖品质：物品等级 >= 725 为先祖装备
    item.is_ancestral = item.power >= 725

    # 精确装备子类型
    subtype_cn, subtype_en = _get_subtype(item.item_id)
    item.item_subtype = subtype_cn
    item.item_subtype_en = subtype_en

    # 查暗金装备信息
    unique_info = db.get_unique_info(item.item_id)
    if unique_info:
        item.is_unique = True
        item.is_mythic = unique_info.get("mythic", False)
        item.en_name = unique_info["en_name"]
        item.cn_name = unique_info["cn_name"]
        # 使用带 # 占位符的 Description（非 DescriptionClean）
        item.unique_effect_en = unique_info.get("en_desc", "")
        item.unique_effect_cn = unique_info.get("cn_desc", "")
    else:
        # 非暗金装备：从 BaseItems 数据库查找基底中英文名
        base_info = db.base_items.get(item.item_id)
        if base_info:
            item.en_name = base_info["en_name"]
            item.cn_name = base_info["cn_name"]
        else:
            item.en_name = item_data.get("name", item.item_id)
            item.cn_name = item.en_name

    # 处理暗金特效：收集所有暗金特效专属 nid
    # 参考 D4Companion: 在 Uniques DB 中但不在 Affixes DB 中的 nid 都是暗金特效
    unique_effect_nids = set()
    unique_effect_values = []

    if item.is_unique:
        for affix in item_data.get("explicits", []):
            nid = affix.get("nid")
            if nid and not db.affixes.get(str(nid)):
                # 在 Uniques DB 中的 nid 是暗金特效词条
                unique_from_sno = db.uniques_by_sno.get(str(nid))
                if unique_from_sno:
                    unique_effect_nids.add(nid)
                    unique_effect_values = affix.get("values", [])

        # 用实际数值填充暗金特效描述中的 #
        # 优先使用 Localisation 感知的智能替换
        if unique_effect_values and item.unique_effect_en:
            en_loc = unique_info.get("en_loc", "") if unique_info else ""
            cn_loc = unique_info.get("cn_loc", "") if unique_info else ""

            if en_loc or cn_loc:
                # 查找 static values: 多种方式查找
                # 1. 用 nid 直接查 (snoID 索引)
                # 2. 用 aspect IdName 查
                # 3. 用 affix IdName 查
                sv = []
                for ue_nid in unique_effect_nids:
                    # 直接用 nid 查找 (snoID 索引)
                    sv = db.static_values.get(str(ue_nid), [])
                    if sv:
                        break
                    asp_info_sv = db.aspects_by_sno.get(str(ue_nid))
                    if asp_info_sv:
                        sv = db.static_values.get(asp_info_sv.get("id_name", ""), [])
                        if sv:
                            break
                    aff = db.affixes.get(str(ue_nid))
                    if aff:
                        sv = db.static_values.get(aff.get("id_name", ""), [])
                        if sv:
                            break

                # 使用 Localisation 精确映射可变值到正确的 # 位置
                item.unique_effect_en = _replace_with_loc(
                    item.unique_effect_en, en_loc, unique_effect_values, sv)
                item.unique_effect_cn = _replace_with_loc(
                    item.unique_effect_cn, cn_loc or en_loc, unique_effect_values, sv)
            else:
                # 回退到旧逻辑
                hash_count = _count_hashes(item.unique_effect_en)
                value_count = len(unique_effect_values)
                if value_count == hash_count:
                    item.unique_effect_en = _replace_hashes(item.unique_effect_en, unique_effect_values)
                    item.unique_effect_cn = _replace_hashes(item.unique_effect_cn, unique_effect_values)
                elif value_count > 0:
                    val_strs = [_format_value(v) for v in unique_effect_values]
                    item.unique_effect_en += f" [Rolled: {', '.join(val_strs)}]"
                    item.unique_effect_cn += f" [可变数值: {', '.join(val_strs)}]"

    # 翻译固有词条 (implicits)
    for affix in item_data.get("implicits", []):
        nid = affix.get("nid")
        values = affix.get("values", [])
        if nid:
            en_text, cn_text = db.get_affix_cn(nid, values)
            item.implicits.append({
                "en": en_text,
                "cn": cn_text,
                "nid": nid,
            })

    # 翻译随机词条 (explicits)
    # 参考 D4Companion: 传奇装备最多只取前4条显式词条，多余的是圣化/特殊词条
    explicit_count = 0
    for affix in item_data.get("explicits", []):
        nid = affix.get("nid")
        values = affix.get("values", [])
        greater = affix.get("greater", False)
        if nid:
            # 跳过所有暗金特效相关词条（可能有多个 nid）
            if nid in unique_effect_nids:
                continue
            # 跳过在 Uniques DB 中但不在 Affixes DB 中的未知词条
            if not db.affixes.get(str(nid)) and db.uniques_by_sno.get(str(nid)):
                continue
            # 传奇装备限制4条（第5条起可能是圣化等特殊词条）
            if not item.is_unique:
                explicit_count += 1
                if explicit_count > 4:
                    continue
            en_text, cn_text = db.get_affix_cn(nid, values)
            item.explicits.append({
                "en": en_text,
                "cn": cn_text,
                "nid": nid,
                "greater": greater,
            })

    # 翻译淬炼词条 (tempered)
    for affix in item_data.get("tempered", []):
        nid = affix.get("nid")
        values = affix.get("values", [])
        if nid:
            en_text, cn_text = db.get_affix_cn(nid, values)
            item.tempered.append({
                "en": en_text,
                "cn": cn_text,
                "nid": nid,
            })

    # 翻译传奇特效 (aspects)
    for asp in item_data.get("aspects", []):
        asp_id = asp.get("id", "")
        asp_nid = asp.get("nid", "")
        asp_values = asp.get("values", [])
        # 优先用 id 查找，然后用 nid 查找
        aspect_info = db.get_aspect_info(asp_id) if asp_id else None
        if not aspect_info and asp_nid:
            aspect_info = db.aspects_by_sno.get(str(asp_nid))
        if aspect_info:
            en_desc = aspect_info.get("en_desc", "")
            cn_desc = aspect_info.get("cn_desc", "")
            if asp_values:
                # 优先使用 Localisation 感知的智能替换
                en_loc = aspect_info.get("en_loc", "")
                cn_loc = aspect_info.get("cn_loc", "")
                if en_loc or cn_loc:
                    # 查找 static values: 多种索引方式
                    asp_id_name = aspect_info.get("id_name", "")
                    sv = db.static_values.get(asp_id_name, [])
                    if not sv and asp_nid:
                        sv = db.static_values.get(str(asp_nid), [])
                    en_desc = _replace_with_loc(en_desc, en_loc, asp_values, sv)
                    cn_desc = _replace_with_loc(cn_desc, cn_loc or en_loc, asp_values, sv)
                else:
                    en_desc = _replace_hashes(en_desc, asp_values)
                    cn_desc = _replace_hashes(cn_desc, asp_values)

            item.aspects.append({
                "en_name": aspect_info["en_name"],
                "cn_name": aspect_info["cn_name"],
                "en_desc": en_desc,
                "cn_desc": cn_desc,
            })
        elif asp_id:
            item.aspects.append({
                "en_name": asp_id,
                "cn_name": f"[未知特效: {asp_id}]",
                "en_desc": "",
                "cn_desc": "",
            })

    # 传奇装备中文命名: "特效名 + 基底名" (与国服官方格式一致)
    # 特效名已含连接词: "诅咒光环之" + "厄运步履" = "诅咒光环之厄运步履"
    #                   "牺牲" + "厄运步履" = "牺牲厄运步履"
    if not item.is_unique and item.aspects:
        first_asp_cn = item.aspects[0].get("cn_name", "")
        first_asp_en = item.aspects[0].get("en_name", "")
        if first_asp_cn:
            base_info = db.base_items.get(item.item_id)
            if base_info:
                item.cn_name = f"{first_asp_cn}{base_info['cn_name']}"
                item.en_name = f"{first_asp_en} {base_info['en_name']}"
            else:
                # 兜底：用槽位类型
                slot_type = SLOT_TYPE_CN.get(item.slot, item.slot)
                item.cn_name = f"{first_asp_cn}{slot_type}"

    # 镶嵌 (sockets)
    for sock in item_data.get("sockets", []):
        if isinstance(sock, str):
            display = db.get_socket_display(sock)
            item.sockets.append({"raw": sock, "display": display})
        else:
            item.sockets.append({"raw": str(sock), "display": str(sock)})

    return item
