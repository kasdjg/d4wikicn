"""
格式化输出模块
将翻译结果格式化为可读文本
"""
from .translator import TranslatedBuild, TranslatedItem


def format_build_text(build: TranslatedBuild, show_english: bool = True) -> str:
    """
    将翻译后的 Build 格式化为纯文本
    show_english: 是否同时显示英文原文（英中对照模式）
    """
    lines = []

    # 标题
    lines.append("=" * 60)
    lines.append(f"  {build.build_name}")
    lines.append(f"  职业: {build.class_cn} ({build.class_en})")
    lines.append(f"  方案: {build.profile_name}")
    lines.append("=" * 60)
    lines.append("")

    # 装备列表
    for item in build.items:
        lines.append(_format_item(item, show_english))
        lines.append("")

    return "\n".join(lines)


def _format_item(item: TranslatedItem, show_english: bool) -> str:
    """格式化单件装备"""
    lines = []

    # 装备头部
    quality = "先祖" if item.is_ancestral else ""
    if item.is_mythic:
        rarity = f"【{quality}神话暗金】" if quality else "【神话暗金】"
    elif item.is_unique:
        rarity = f"【{quality}暗金】" if quality else "【暗金】"
    else:
        rarity = f"【{quality}传奇】" if quality else "【传奇】"

    # 精确装备子类型
    subtype = item.item_subtype or item.slot

    lines.append(f"┌─ {subtype} ─────────────────────────────")
    if show_english and item.en_name != item.cn_name:
        lines.append(f"│ {rarity} {item.cn_name} ({item.en_name})")
    else:
        lines.append(f"│ {rarity} {item.cn_name}")

    if item.power:
        lines.append(f"│ 物品等级: {item.power}  强化: +{item.upgrade}")

    # 固有词条
    if item.implicits:
        lines.append("│")
        lines.append("│ ── 固有词条 ──")
        for affix in item.implicits:
            if show_english and affix["en"] != affix["cn"]:
                lines.append(f"│  ◇ {affix['cn']}")
                lines.append(f"│     ({affix['en']})")
            else:
                lines.append(f"│  ◇ {affix['cn']}")

    # 随机词条
    if item.explicits:
        lines.append("│")
        lines.append("│ ── 词条 ──")
        for affix in item.explicits:
            marker = "🔥" if affix.get("greater") else "◇"
            if show_english and affix["en"] != affix["cn"]:
                lines.append(f"│  {marker} {affix['cn']}")
                lines.append(f"│     ({affix['en']})")
            else:
                lines.append(f"│  {marker} {affix['cn']}")

    # 淬炼词条
    if item.tempered:
        lines.append("│")
        lines.append("│ ── 淬炼词条 ──")
        for affix in item.tempered:
            if show_english and affix["en"] != affix["cn"]:
                lines.append(f"│  🔨 {affix['cn']}")
                lines.append(f"│     ({affix['en']})")
            else:
                lines.append(f"│  🔨 {affix['cn']}")

    # 暗金特效
    if item.is_unique and item.unique_effect_cn:
        lines.append("│")
        lines.append("│ ── 独特特效 ──")
        lines.append(f"│  ★ {item.unique_effect_cn}")
        if show_english and item.unique_effect_en:
            lines.append(f"│     ({item.unique_effect_en})")

    # 传奇特效
    if item.aspects:
        lines.append("│")
        lines.append("│ ── 传奇特效 ──")
        for asp in item.aspects:
            if show_english:
                lines.append(f"│  ⚡ {asp['cn_name']}")
                lines.append(f"│     ({asp['en_name']})")
                if asp["cn_desc"]:
                    lines.append(f"│     {asp['cn_desc']}")
            else:
                lines.append(f"│  ⚡ {asp['cn_name']}")
                if asp["cn_desc"]:
                    lines.append(f"│     {asp['cn_desc']}")

    # 镶嵌
    if item.sockets:
        lines.append("│")
        lines.append("│ ── 镶嵌 ──")
        for sock in item.sockets:
            if isinstance(sock, dict) and "display" in sock:
                lines.append(f"│  💎 {sock['display']}")
            elif isinstance(sock, str):
                lines.append(f"│  💎 {sock}")
            else:
                lines.append(f"│  💎 {sock}")

    lines.append("└─────────────────────────────────────")
    return "\n".join(lines)


def format_build_markdown(build: TranslatedBuild) -> str:
    """将翻译后的 Build 格式化为 Markdown"""
    lines = []

    lines.append(f"# {build.build_name}")
    lines.append(f"**职业:** {build.class_cn} ({build.class_en})")
    lines.append(f"**方案:** {build.profile_name}")
    lines.append("")
    lines.append("---")
    lines.append("")

    for item in build.items:
        lines.append(_format_item_md(item))
        lines.append("")

    return "\n".join(lines)


def _format_item_md(item: TranslatedItem) -> str:
    """格式化单件装备为 Markdown"""
    lines = []

    rarity = ""
    if item.is_mythic:
        rarity = "🟣 神话暗金"
    elif item.is_unique:
        rarity = "🟠 暗金"
    else:
        rarity = "🟡 传奇"

    lines.append(f"### {item.slot} — {item.cn_name}")
    if item.en_name != item.cn_name:
        lines.append(f"*{item.en_name}* | {rarity} | 物品等级 {item.power}")
    else:
        lines.append(f"{rarity} | 物品等级 {item.power}")
    lines.append("")

    if item.implicits:
        lines.append("**固有词条:**")
        for affix in item.implicits:
            lines.append(f"- ◇ {affix['cn']} *({affix['en']})*")
        lines.append("")

    if item.explicits:
        lines.append("**词条:**")
        for affix in item.explicits:
            marker = "🔥" if affix.get("greater") else "◇"
            lines.append(f"- {marker} {affix['cn']} *({affix['en']})*")
        lines.append("")

    if item.tempered:
        lines.append("**淬炼词条:**")
        for affix in item.tempered:
            lines.append(f"- 🔨 {affix['cn']} *({affix['en']})*")
        lines.append("")

    if item.is_unique and item.unique_effect_cn:
        lines.append("**独特特效:**")
        # 处理描述中的换行，确保在 Markdown 引用块内
        cn_effect = item.unique_effect_cn.replace("\n\n", " ").replace("\n", " ")
        lines.append(f"> ★ {cn_effect}")
        if item.unique_effect_en:
            en_effect = item.unique_effect_en.replace("\n\n", " ").replace("\n", " ")
            lines.append(f"> *({en_effect})*")
        lines.append("")

    if item.aspects:
        lines.append("**传奇特效:**")
        for asp in item.aspects:
            lines.append(f"> ⚡ **{asp['cn_name']}** *({asp['en_name']})*")
            if asp["cn_desc"]:
                cn_desc = asp['cn_desc'].replace("\n\n", " ").replace("\n", " ")
                lines.append(f"> {cn_desc}")
        lines.append("")

    if item.sockets:
        lines.append("**镶嵌:**")
        for sock in item.sockets:
            if isinstance(sock, dict) and "display" in sock:
                lines.append(f"- 💎 {sock['display']}")
            elif isinstance(sock, str):
                lines.append(f"- 💎 {sock}")
            else:
                lines.append(f"- 💎 {sock}")
        lines.append("")

    return "\n".join(lines)
