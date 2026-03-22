"""
从 d4data StringList 中提取所有装备基底名称（中英文）
生成 BaseItems.enUS.json 和 BaseItems.zhCN.json

数据源: d4data-master/json/{lang}_Text/meta/StringList/Item_*.stl.json
每个文件的 arStrings 中 szLabel=="Name" 的 szText 即为装备显示名

输出格式: {"Boots_Legendary_Generic_053": "Runic Cleats", ...}
映射 key 对应 Maxroll API 的 item_data["id"]
"""

import json
import os
import glob

# 路径配置
D4DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "github_resource", "d4data-master", "json"
)
OUTPUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "data", "raw"
)

# 装备类型前缀（只提取可穿戴装备，排除 Cosmetic/Quest 等）
EQUIP_PREFIXES = (
    "Boots_", "Helm_", "Chest_", "Gloves_", "Pants_",
    "Amulet_", "Ring_",
    "1HAxe_", "1HDagger_", "1HFocus_", "1HMace_", "1HScythe_",
    "1HShield_", "1HSword_", "1HTotem_", "1HWand_",
    "2HAxe_", "2HBow_", "2HCrossbow_", "2HGlaive_", "2HMace_",
    "2HPolearm_", "2HQuarterstaff_", "2HScythe_", "2HStaff_", "2HSword_",
)

# 排除的关键词
EXCLUDE_KEYWORDS = (
    "Cosmetic", "TestLook", "Gambling", "PvP", "QST",
    "BlizzCon", "Promo", "Debug", "Test_",
)


def extract_names(lang: str) -> dict:
    """从指定语言的 StringList 中提取装备名称"""
    stl_dir = os.path.join(D4DATA_DIR, f"{lang}_Text", "meta", "StringList")
    if not os.path.isdir(stl_dir):
        print(f"  错误: 目录不存在 {stl_dir}")
        return {}

    pattern = os.path.join(stl_dir, "Item_*.stl.json")
    files = glob.glob(pattern)
    print(f"  {lang}: 扫描到 {len(files)} 个 Item StringList 文件")

    names = {}
    skipped = 0
    for filepath in files:
        filename = os.path.basename(filepath)
        # Item_Boots_Legendary_Generic_053.stl.json → Boots_Legendary_Generic_053
        item_id = filename[5:-9]  # 去掉 "Item_" 前缀和 ".stl.json" 后缀

        # 过滤：只保留装备类型
        if not item_id.startswith(EQUIP_PREFIXES):
            skipped += 1
            continue

        # 排除测试/外观/PvP等
        if any(kw in item_id for kw in EXCLUDE_KEYWORDS):
            skipped += 1
            continue

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            for entry in data.get("arStrings", []):
                if entry.get("szLabel") == "Name":
                    name = entry.get("szText", "").strip()
                    if name:
                        names[item_id] = name
                    break
        except Exception as e:
            print(f"  警告: 读取失败 {filename}: {e}")

    print(f"  {lang}: 提取 {len(names)} 个装备名称 (跳过 {skipped} 个非装备文件)")
    return names


def main():
    print("=" * 60)
    print("提取装备基底名称 (BaseItems)")
    print("=" * 60)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    for lang in ("enUS", "zhCN"):
        print(f"\n处理 {lang}...")
        names = extract_names(lang)
        if not names:
            print(f"  错误: {lang} 未提取到任何数据!")
            continue

        output_path = os.path.join(OUTPUT_DIR, f"BaseItems.{lang}.json")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(names, f, ensure_ascii=False, indent=1, sort_keys=True)
        print(f"  已写入: {output_path} ({len(names)} 条)")

    # 验证：对比中英文覆盖率
    en_path = os.path.join(OUTPUT_DIR, "BaseItems.enUS.json")
    cn_path = os.path.join(OUTPUT_DIR, "BaseItems.zhCN.json")
    if os.path.exists(en_path) and os.path.exists(cn_path):
        with open(en_path, "r", encoding="utf-8") as f:
            en = json.load(f)
        with open(cn_path, "r", encoding="utf-8") as f:
            cn = json.load(f)
        en_only = set(en.keys()) - set(cn.keys())
        cn_only = set(cn.keys()) - set(en.keys())
        both = set(en.keys()) & set(cn.keys())
        print(f"\n覆盖率统计:")
        print(f"  中英文都有: {len(both)} 个")
        print(f"  仅英文: {len(en_only)} 个")
        print(f"  仅中文: {len(cn_only)} 个")
        if en_only:
            samples = list(en_only)[:5]
            print(f"  仅英文示例: {samples}")

    print("\n完成!")


if __name__ == "__main__":
    main()
