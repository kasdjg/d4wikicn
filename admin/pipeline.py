"""数据管线执行引擎 — 4 步命令定义、异步执行、实时日志、产出验证"""

import asyncio
import json
import os
import re
import shutil
import subprocess
import threading
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

# 项目根目录（用 Path 构造，不含手写反斜杠，避免转义问题）
PROJECT_ROOT = Path("D:/diaoblo4_items")
GITHUB_RES = PROJECT_ROOT / "github_resource"

CASC_EXE = (
    GITHUB_RES
    / "CASCExplorer-master"
    / "CASCConsole"
    / "bin"
    / "Release"
    / "net9.0"
    / "CASCConsole.exe"
)
D4DATA_DIR = GITHUB_RES / "d4data-master"
D4PARSER_DIR = GITHUB_RES / "D4DataParser-main"
D4WIKICN_RAW = PROJECT_ROOT / "d4wikicn" / "data" / "raw"


@dataclass
class StepDef:
    id: str
    name: str
    cwd: str
    check_file: str  # 验证产出的文件或目录
    command: str = ""  # shell 命令（与 py_func 二选一）
    py_func: Optional[Callable] = None  # Python 异步函数（替代 shell 命令）


# ═══ 第 ④ 步：用 Python shutil 复制，彻底避免 Windows copy 命令的编码和转义坑 ═══
async def _copy_data_files(runner: "PipelineRunner", step: "StepDef"):
    src_dir = D4PARSER_DIR / "Data"
    dst_dir = D4WIKICN_RAW
    dst_dir.mkdir(parents=True, exist_ok=True)

    await runner._log(step.id, "system", f"源目录: {src_dir}")
    await runner._log(step.id, "system", f"目标目录: {dst_dir}")

    copied = 0
    for pattern in ("*.zhCN.json", "*.enUS.json"):
        for f in sorted(src_dir.glob(pattern)):
            shutil.copy(f, dst_dir / f.name)
            size_kb = f.stat().st_size / 1024
            await runner._log(step.id, "stdout", f"  {f.name} ({size_kb:.0f}KB)")
            copied += 1

    if copied == 0:
        raise FileNotFoundError(f"源目录中没有找到 JSON 文件: {src_dir}")

    await runner._log(step.id, "system", f"复制完成: {copied} 个文件")

    # ── 从步骤2产出的 .aff.json 中提取 StaticValues ──
    affix_dir = D4DATA_DIR / "json" / "base" / "meta" / "Affix"
    if affix_dir.is_dir():
        await runner._log(step.id, "system", "正在从 .aff.json 提取 StaticValues...")
        sv_result = {}
        aff_files = sorted(affix_dir.glob("*.aff.json"))
        for f in aff_files:
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                sv = data.get("arStaticValues", [])
                if sv:
                    id_name = f.name.replace(".aff.json", "")
                    sv_result[id_name] = sv
                    sno_id = data.get("__snoID__")
                    if sno_id:
                        sv_result[str(sno_id)] = sv
            except Exception:
                pass

        if sv_result:
            sv_path = dst_dir / "StaticValues.json"
            with open(sv_path, "w", encoding="utf-8") as fh:
                json.dump(sv_result, fh, indent=2, ensure_ascii=False)
            name_count = len([k for k in sv_result if not k.isdigit()])
            size_kb = sv_path.stat().st_size / 1024
            await runner._log(step.id, "stdout", f"  StaticValues.json ({size_kb:.0f}KB, {name_count} 条)")
        else:
            await runner._log(step.id, "stderr", "警告: 未提取到 StaticValues")
    else:
        await runner._log(step.id, "stderr", "警告: Affix 目录不存在，跳过 StaticValues 提取")


STEPS: list[StepDef] = [
    StepDef(
        id="download",
        name="① 下载游戏数据",
        command=f'"{CASC_EXE}" -o -m Pattern -e "base/*.dat" -d data/ -l enUS -p fenris',
        cwd=str(D4DATA_DIR),
        check_file=str(D4DATA_DIR / "data" / "base" / "StringList-Text-zhCN.dat"),
    ),
    StepDef(
        id="parse",
        name="② 二进制转JSON",
        command="node parse.js data/",
        cwd=str(D4DATA_DIR),
        check_file=str(D4DATA_DIR / "json" / "zhCN_Text" / "meta" / "StringList"),
    ),
    StepDef(
        id="classify",
        name="③ 分类整理",
        command="dotnet run --project D4DataParserCLI -c Release",
        cwd=str(D4PARSER_DIR),
        check_file=str(D4PARSER_DIR / "Data" / "Affixes.zhCN.json"),
    ),
    StepDef(
        id="copy",
        name="④ 复制到翻译工具",
        cwd=str(D4PARSER_DIR),
        check_file=str(D4WIKICN_RAW / "Affixes.zhCN.json"),
        py_func=_copy_data_files,
    ),
]

STEP_MAP: dict[str, StepDef] = {s.id: s for s in STEPS}


@dataclass
class LogEntry:
    time: str
    step: str
    type: str  # stdout / stderr / system
    text: str


@dataclass
class StepResult:
    step_id: str
    status: str  # pending / running / success / error
    elapsed: Optional[str] = None
    error_msg: Optional[str] = None


@dataclass
class PipelineRunner:
    """管线执行器：异步执行命令，实时捕获输出到日志队列"""

    log_queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    step_results: dict[str, StepResult] = field(default_factory=dict)
    running: bool = False
    cancelled: bool = False
    current_process: Optional[subprocess.Popen] = None
    current_step_id: Optional[str] = None
    captured_version: Optional[str] = None  # 从 download 步骤捕获的版本号

    def _now(self) -> str:
        return datetime.now().strftime("%H:%M:%S")

    async def _log(self, step: str, type_: str, text: str):
        entry = LogEntry(time=self._now(), step=step, type=type_, text=text)
        await self.log_queue.put(("log", entry))

    async def _update_step(self, step_id: str, status: str, elapsed: str = None, error_msg: str = None):
        result = StepResult(step_id=step_id, status=status, elapsed=elapsed, error_msg=error_msg)
        self.step_results[step_id] = result
        await self.log_queue.put(("step_status", result))

    async def run_step(self, step: StepDef) -> bool:
        """执行单步，返回是否成功"""
        self.current_step_id = step.id
        await self._update_step(step.id, "running")
        await self._log(step.id, "system", f"开始执行: {step.name}")

        start = time.time()
        try:
            if step.py_func:
                # Python 原生步骤
                await step.py_func(self, step)
            else:
                # Shell 命令步骤
                await self._run_shell(step)

            elapsed = f"{time.time() - start:.0f}s"

            if self.cancelled:
                await self._update_step(step.id, "error", elapsed, "已取消")
                await self._log(step.id, "system", f"{step.name} 已取消")
                return False

            # 验证产出
            await self._verify_output(step)

            await self._update_step(step.id, "success", elapsed)
            await self._log(step.id, "system", f"{step.name} 完成，耗时 {elapsed}")
            return True

        except Exception as e:
            elapsed = f"{time.time() - start:.0f}s"
            self.current_process = None
            error_detail = f"{type(e).__name__}: {e}"
            await self._update_step(step.id, "error", elapsed, error_detail)
            await self._log(step.id, "stderr", f"{step.name} 异常: {error_detail}")
            # 输出完整 traceback 到终端
            for tb_line in traceback.format_exc().strip().split("\n"):
                await self._log(step.id, "stderr", tb_line)
            return False

    async def _run_shell(self, step: StepDef):
        """执行 shell 命令（subprocess.Popen + 线程，兼容 Windows SelectorEventLoop）"""
        await self._log(step.id, "system", f"命令: {step.command}")
        await self._log(step.id, "system", f"工作目录: {step.cwd}")

        loop = asyncio.get_running_loop()

        proc = subprocess.Popen(
            step.command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=step.cwd,
            shell=True,
        )
        self.current_process = proc

        def read_stream(stream, stream_type):
            """在线程中逐行读取输出，通过 run_coroutine_threadsafe 推送日志"""
            try:
                for line in iter(stream.readline, b""):
                    try:
                        text = line.decode("utf-8").rstrip()
                    except UnicodeDecodeError:
                        text = line.decode("gbk", errors="replace").rstrip()
                    if text:
                        fut = asyncio.run_coroutine_threadsafe(
                            self._log(step.id, stream_type, text), loop
                        )
                        try:
                            fut.result(timeout=30)
                        except Exception:
                            break
                        if step.id == "download" and stream_type == "stdout":
                            self._try_capture_version(text)
            finally:
                stream.close()

        t_out = threading.Thread(target=read_stream, args=(proc.stdout, "stdout"), daemon=True)
        t_err = threading.Thread(target=read_stream, args=(proc.stderr, "stderr"), daemon=True)
        t_out.start()
        t_err.start()

        await asyncio.gather(
            loop.run_in_executor(None, t_out.join),
            loop.run_in_executor(None, t_err.join),
        )

        returncode = await loop.run_in_executor(None, proc.wait)
        self.current_process = None

        if returncode != 0:
            raise RuntimeError(f"命令退出码 {returncode}")

    async def _verify_output(self, step: StepDef):
        """验证步骤产出 — 检查关键文件/目录是否存在"""
        check_path = Path(step.check_file)
        if check_path.is_dir():
            files = list(check_path.iterdir())
            count = len(files)
            await self._log(step.id, "system", f"✓ 验证通过: {check_path.name}/ 包含 {count} 个文件")
        elif check_path.is_file():
            size_kb = check_path.stat().st_size / 1024
            mtime = datetime.fromtimestamp(check_path.stat().st_mtime).strftime("%H:%M:%S")
            await self._log(step.id, "system", f"✓ 验证通过: {check_path.name} ({size_kb:.0f}KB, 更新于 {mtime})")
        else:
            await self._log(step.id, "stderr", f"✗ 验证失败: 预期产出 {check_path} 不存在")
            raise FileNotFoundError(f"预期产出不存在: {check_path}")

    def _try_capture_version(self, text: str):
        """尝试从 CASCConsole 输出中捕获版本号"""
        m = re.search(r"(\d+\.\d+\.\d+\.\d+)", text)
        if m:
            self.captured_version = m.group(1)

    async def run_all(self, step_ids: list[str] = None):
        """执行全部或指定步骤"""
        if self.running:
            return
        self.running = True
        self.cancelled = False
        self.captured_version = None

        steps = [STEP_MAP[sid] for sid in step_ids] if step_ids else STEPS

        # 初始化未运行步骤为 pending
        for s in steps:
            await self._update_step(s.id, "pending")

        start_total = time.time()
        all_success = True

        for step in steps:
            if self.cancelled:
                break
            success = await self.run_step(step)
            if not success:
                all_success = False
                break

        total_elapsed = f"{time.time() - start_total:.0f}s"
        self.running = False
        self.current_step_id = None

        # 发送完成事件
        await self.log_queue.put(("done", {
            "success": all_success,
            "total_elapsed": total_elapsed,
            "build_version": self.captured_version,
        }))

    def cancel(self):
        """取消当前执行"""
        self.cancelled = True
        if self.current_process:
            try:
                self.current_process.terminate()
            except ProcessLookupError:
                pass
