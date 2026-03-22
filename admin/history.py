"""执行历史记录 — 读写 pipeline_history.json"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

HISTORY_FILE = Path(__file__).resolve().parent.parent / "data" / "pipeline_history.json"


def _default_history() -> dict:
    return {
        "last_run": None,
        "build_version": None,
        "build_id": None,
        "steps": {},
    }


def load_history() -> dict:
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return _default_history()


def save_history(history: dict):
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_FILE.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")


def record_step(step_id: str, status: str, elapsed: str):
    """记录单步执行结果"""
    history = load_history()
    history["steps"][step_id] = {
        "last_run": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "status": status,
        "elapsed": elapsed,
    }
    history["last_run"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    save_history(history)


def record_version(version: str):
    """记录构建版本号"""
    history = load_history()
    history["build_version"] = version
    # 提取 BuildId（最后一段数字）
    parts = version.split(".")
    if parts:
        try:
            history["build_id"] = int(parts[-1])
        except ValueError:
            pass
    save_history(history)


def get_local_version() -> Optional[str]:
    """获取本地记录的版本号"""
    history = load_history()
    return history.get("build_version")
