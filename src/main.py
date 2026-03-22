"""
暗黑4英文攻略翻译工具 - 主入口
用户输入 Maxroll Planner 链接，输出中文版 BD 攻略
"""
import sys
import os

# 确保可以导入 src 包
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.data_loader import get_database
from src.maxroll_api import extract_build_id, fetch_build, MaxrollBuild
from src.translator import translate_build
from src.formatter import format_build_text, format_build_markdown


def main():
    print("=" * 60)
    print("  暗黑4 英文攻略翻译工具 v0.1")
    print("  支持: Maxroll Planner 链接")
    print("=" * 60)
    print()

    # 获取输入
    if len(sys.argv) > 1:
        url = sys.argv[1]
    else:
        url = input("请输入 Maxroll Planner 链接 (或 build ID): ").strip()

    if not url:
        print("错误: 请输入有效的链接")
        return

    # 提取 build ID
    build_id = extract_build_id(url)
    print(f"\nBuild ID: {build_id}")

    # 加载数据库
    db = get_database()

    # 获取 build 数据
    print(f"\n正在获取 build 数据...")
    try:
        raw_data = fetch_build(build_id)
    except Exception as e:
        print(f"错误: {e}")
        return

    build = MaxrollBuild(raw_data)
    print(f"Build: {build.name} ({build.class_cn})")
    print(f"方案列表: {build.get_profile_names()}")

    # 选择方案
    profile_index = None
    if len(sys.argv) > 2:
        profile_index = int(sys.argv[2])
    elif len(build.profiles) > 1:
        print()
        for i, name in enumerate(build.get_profile_names()):
            active = " ← 默认" if i == build.active_profile else ""
            print(f"  [{i}] {name}{active}")
        choice = input(f"\n选择方案 (回车使用默认 [{build.active_profile}]): ").strip()
        if choice:
            profile_index = int(choice)

    # 翻译
    print(f"\n正在翻译...")
    translated = translate_build(build, profile_index)

    # 输出
    output = format_build_text(translated, show_english=True)
    print()
    print(output)

    # 保存 Markdown 版本
    md_output = format_build_markdown(translated)
    md_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_output)
    print(f"\nMarkdown 版本已保存到: {md_path}")


if __name__ == "__main__":
    main()
