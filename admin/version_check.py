"""版本检查 — 对比本地数据版本 vs 暴雪/网易服务器版本"""

import urllib.request
from typing import Optional

from .history import get_local_version

VERSIONS_URL = "https://us.version.battle.net/v2/products/fenris/versions"


def fetch_server_version(region: str = "cn") -> Optional[str]:
    """从 Ribbit 版本服务获取指定区域的游戏版本号

    返回格式如 "2.5.3.70582"，失败返回 None
    """
    try:
        req = urllib.request.Request(VERSIONS_URL, headers={"User-Agent": "D4Wiki/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            text = resp.read().decode("utf-8")
    except Exception:
        return None

    # 解析竖线分隔的文本表格
    # 第一行是表头，后面是数据行
    lines = text.strip().split("\n")
    if len(lines) < 2:
        return None

    # 解析表头，找到 Region 和 VersionsName 列索引
    header = lines[0]
    columns = [col.split("!")[0] for col in header.split("|")]
    try:
        region_idx = columns.index("Region")
        version_idx = columns.index("VersionsName")
    except ValueError:
        return None

    # 查找目标区域行
    for line in lines[1:]:
        if not line.strip():
            continue
        fields = line.split("|")
        if len(fields) > max(region_idx, version_idx) and fields[region_idx] == region:
            return fields[version_idx]

    return None


def check_update() -> dict:
    """检查是否有更新

    返回:
        {
            "local_version": "2.5.3.70582" 或 None,
            "server_version": "2.5.3.70582" 或 None,
            "has_update": bool,
            "message": "已是最新" / "有新版本可更新" / "无法获取服务器版本" 等
        }
    """
    local = get_local_version()
    server = fetch_server_version("cn")

    if server is None:
        return {
            "local_version": local,
            "server_version": None,
            "has_update": False,
            "message": "无法获取服务器版本，请检查网络",
        }

    if local is None:
        return {
            "local_version": None,
            "server_version": server,
            "has_update": True,
            "message": f"本地无版本记录，服务器版本: {server}",
        }

    if local == server:
        return {
            "local_version": local,
            "server_version": server,
            "has_update": False,
            "message": "已是最新",
        }

    return {
        "local_version": local,
        "server_version": server,
        "has_update": True,
        "message": f"有新版本可更新（服务器: {server}，本地: {local}）",
    }
