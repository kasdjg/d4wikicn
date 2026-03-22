"""管理后台 API 路由"""

import asyncio
import json
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import StreamingResponse

from .history import load_history, save_history
from .pipeline import STEPS, STEP_MAP, PipelineRunner
from .version_check import check_update as do_check_update

router = APIRouter()

# 全局状态
_runner: PipelineRunner | None = None
_pipeline_running = False  # 同步标志，在路由处理器中立即设置
_log_subscribers: list[asyncio.Queue] = []

DATA_RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"


@router.get("/status")
async def get_status():
    """管线状态 + 每步上次执行时间/结果"""
    history = load_history()

    steps = []
    for s in STEPS:
        step_info = {
            "id": s.id,
            "name": s.name,
            "status": "pending",
            "last_run": None,
            "elapsed": None,
        }
        # 从历史记录中获取
        if s.id in history.get("steps", {}):
            h = history["steps"][s.id]
            step_info["last_run"] = h.get("last_run")
            step_info["elapsed"] = h.get("elapsed")
            step_info["status"] = h.get("status", "pending")

        # 如果当前正在运行，用运行时状态覆盖
        if _pipeline_running and _runner and s.id in _runner.step_results:
            step_info["status"] = _runner.step_results[s.id].status

        steps.append(step_info)

    return {
        "running": _pipeline_running,
        "current_step": _runner.current_step_id if _runner else None,
        "last_run": history.get("last_run"),
        "build_version": history.get("build_version"),
        "steps": steps,
    }


@router.get("/check-update")
async def check_update():
    """检查更新：对比本地 vs 服务器版本"""
    return do_check_update()


@router.post("/run")
async def run_all(background_tasks: BackgroundTasks):
    """执行全部 4 步"""
    global _pipeline_running
    if _pipeline_running:
        return {"error": "管线正在执行中，请等待完成或取消"}

    _pipeline_running = True  # 同步设置，防止重复点击
    background_tasks.add_task(_run_pipeline, None)
    return {"message": "已开始执行全部步骤"}


@router.post("/run/{step_id}")
async def run_step(step_id: str, background_tasks: BackgroundTasks):
    """执行指定步骤"""
    global _pipeline_running
    if step_id not in STEP_MAP:
        return {"error": f"未知步骤: {step_id}"}

    if _pipeline_running:
        return {"error": "管线正在执行中，请等待完成或取消"}

    _pipeline_running = True  # 同步设置
    background_tasks.add_task(_run_pipeline, [step_id])
    return {"message": f"已开始执行: {STEP_MAP[step_id].name}"}


@router.post("/cancel")
async def cancel():
    """取消当前步骤"""
    if not _pipeline_running or not _runner:
        return {"error": "没有正在执行的任务"}

    _runner.cancel()
    return {"message": "已发送取消请求"}


@router.get("/logs")
async def logs():
    """SSE 端点，实时推送日志（持久连接，带心跳保活）"""
    queue = asyncio.Queue()
    _log_subscribers.append(queue)

    async def event_stream():
        try:
            while True:
                try:
                    event_type, data = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    # 心跳保活，防止连接超时断开
                    yield ": heartbeat\n\n"
                    continue

                if event_type == "log":
                    payload = {
                        "time": data.time,
                        "step": data.step,
                        "type": data.type,
                        "text": data.text,
                    }
                    yield f"event: log\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                elif event_type == "step_status":
                    payload = {
                        "step": data.step_id,
                        "status": data.status,
                        "elapsed": data.elapsed,
                    }
                    yield f"event: step_status\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                elif event_type == "done":
                    yield f"event: done\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
        finally:
            if queue in _log_subscribers:
                _log_subscribers.remove(queue)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/data-stats")
async def data_stats():
    """data/raw/ 各文件的大小、修改时间、数据条数"""
    files = []
    if DATA_RAW_DIR.exists():
        for f in sorted(DATA_RAW_DIR.glob("*.json")):
            stat = f.stat()
            count = None
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                if isinstance(data, (list, dict)):
                    count = len(data)
            except Exception:
                pass

            files.append({
                "name": f.name,
                "size": stat.st_size,
                "size_display": _format_size(stat.st_size),
                "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%m-%d %H:%M"),
                "count": count,
            })
    return {"files": files}


def _format_size(size: int) -> str:
    if size < 1024:
        return f"{size}B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f}KB"
    return f"{size / (1024 * 1024):.1f}MB"


async def _run_pipeline(step_ids: list[str] | None):
    """后台执行管线，并将日志广播给所有 SSE 订阅者"""
    global _runner, _pipeline_running
    try:
        _runner = PipelineRunner()
        runner = _runner

        # 启动一个任务来广播日志
        broadcast_task = asyncio.create_task(_broadcast_logs(runner))

        await runner.run_all(step_ids)

        # 等广播任务处理完队列中剩余消息
        await asyncio.sleep(0.3)
        broadcast_task.cancel()
        try:
            await broadcast_task
        except asyncio.CancelledError:
            pass

        # 保存执行历史
        history = load_history()
        for step_id, result in runner.step_results.items():
            if result.status in ("success", "error"):
                history["steps"][step_id] = {
                    "last_run": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "status": result.status,
                    "elapsed": result.elapsed,
                }
        history["last_run"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if runner.captured_version:
            history["build_version"] = runner.captured_version
            parts = runner.captured_version.split(".")
            if parts:
                try:
                    history["build_id"] = int(parts[-1])
                except ValueError:
                    pass
        save_history(history)
    finally:
        _pipeline_running = False


async def _broadcast_logs(runner: PipelineRunner):
    """从 runner 的日志队列中读取，广播给所有 SSE 订阅者"""
    try:
        while True:
            msg = await runner.log_queue.get()
            for sub_queue in list(_log_subscribers):
                try:
                    sub_queue.put_nowait(msg)
                except asyncio.QueueFull:
                    pass
    except asyncio.CancelledError:
        # 处理队列中剩余消息
        while not runner.log_queue.empty():
            msg = runner.log_queue.get_nowait()
            for sub_queue in list(_log_subscribers):
                try:
                    sub_queue.put_nowait(msg)
                except asyncio.QueueFull:
                    pass
