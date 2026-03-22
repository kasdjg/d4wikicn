"""
导出翻译后的 Build 数据为 JSON，供前端页面使用
"""
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.data_loader import get_database
from src.maxroll_api import extract_build_id, fetch_build, MaxrollBuild
from src.translator import translate_build, TranslatedBuild, TranslatedItem


def build_to_dict(build: TranslatedBuild) -> dict:
    """将 TranslatedBuild 转换为可序列化的字典"""
    items = []
    for item in build.items:
        items.append({
            "slot": item.slot,
            "item_id": item.item_id,
            "en_name": item.en_name,
            "cn_name": item.cn_name,
            "is_unique": item.is_unique,
            "is_mythic": item.is_mythic,
            "is_ancestral": item.is_ancestral,
            "power": item.power,
            "upgrade": item.upgrade,
            "item_subtype": item.item_subtype,
            "item_subtype_en": item.item_subtype_en,
            "implicits": item.implicits,
            "explicits": item.explicits,
            "tempered": item.tempered,
            "aspects": item.aspects,
            "unique_effect_en": item.unique_effect_en,
            "unique_effect_cn": item.unique_effect_cn,
            "sockets": item.sockets,
        })

    return {
        "build_name": build.build_name,
        "class_en": build.class_en,
        "class_cn": build.class_cn,
        "profile_name": build.profile_name,
        "items": items,
    }


def export_build_json(build_id_or_url: str, profile_index: int = None, output_path: str = None):
    """导出 build 为 JSON 文件"""
    db = get_database()

    build_id = extract_build_id(build_id_or_url)
    print(f"Build ID: {build_id}")

    # 尝试从本地缓存加载
    cache_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "test_build.json")
    if os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
        if raw_data.get("id") == build_id:
            print("从本地缓存加载...")
        else:
            print("正在从 Maxroll 获取...")
            raw_data = fetch_build(build_id)
    else:
        print("正在从 Maxroll 获取...")
        raw_data = fetch_build(build_id)

    build = MaxrollBuild(raw_data)
    print(f"Build: {build.name} ({build.class_cn})")
    print(f"方案列表: {build.get_profile_names()}")

    if profile_index is None:
        profile_index = build.active_profile

    translated = translate_build(build, profile_index)
    result = build_to_dict(translated)

    # 添加额外信息：所有方案列表
    result["all_profiles"] = build.get_profile_names()
    result["active_profile_index"] = profile_index

    if output_path is None:
        output_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web", "build_data.json")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"JSON 已导出到: {output_path}")
    return result


if __name__ == "__main__":
    if len(sys.argv) > 1:
        url = sys.argv[1]
    else:
        url = "x61ej0y7"  # 默认测试 build

    profile_idx = int(sys.argv[2]) if len(sys.argv) > 2 else None
    export_build_json(url, profile_idx)
