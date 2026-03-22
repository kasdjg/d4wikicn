"""Build translation API — SSE streaming endpoint for frontend"""

import json
import asyncio
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from src.data_loader import get_database
from src.maxroll_api import fetch_build, MaxrollBuild
from src.translator import translate_build
from src.export_json import build_to_dict

router = APIRouter()

# Common Maxroll profile names → 中文
PROFILE_CN = {
    "starter": "起步", "leveling": "练级", "ancestral": "先祖",
    "mythic": "神话", "sanctification": "圣化", "skills": "技能",
    "endgame": "终局", "speed": "速刷", "boss": "Boss",
    "pit": "深渊", "helltide": "地狱狂潮", "default": "默认",
}


def _sse(evt: str, data: dict) -> str:
    """Format a Server-Sent Event frame"""
    return f"event: {evt}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.get("/translate/{build_id}")
async def translate_all_profiles(build_id: str):
    """
    SSE endpoint: fetch a build from Maxroll and translate ALL profiles.
    Events:
      - progress  {step, message, ...}
      - profile   {index, name, cn_name, data}
      - complete  {build_id, build_name, class_en, class_cn, profile_names}
      - fail      {message}
    """

    async def generate():
        try:
            # 1. Fetch from Maxroll
            yield _sse("progress", {
                "step": "fetch",
                "message": "正在从 Maxroll 下载数据...",
            })

            raw = await asyncio.to_thread(fetch_build, build_id)
            build = MaxrollBuild(raw)
            names = build.get_profile_names()

            if not names:
                yield _sse("fail", {"message": "该 Build 没有配置方案"})
                return

            yield _sse("progress", {
                "step": "fetched",
                "message": f"下载完成 — {build.name}（{build.class_cn}），共 {len(names)} 个方案",
                "build_name": build.name,
                "class_en": build.class_en,
                "class_cn": build.class_cn,
                "profiles": names,
            })

            # 2. Pre-warm translation database (singleton, fast after first load)
            await asyncio.to_thread(get_database)

            # 3. Translate each profile
            for i, name in enumerate(names):
                yield _sse("progress", {
                    "step": "translate",
                    "index": i,
                    "total": len(names),
                    "name": name,
                    "message": f"正在翻译 {name}（{i + 1}/{len(names)}）...",
                })

                translated = await asyncio.to_thread(translate_build, build, i)
                data = build_to_dict(translated)
                cn = PROFILE_CN.get(name.lower().strip(), name)

                yield _sse("profile", {
                    "index": i,
                    "name": name,
                    "cn_name": cn,
                    "data": data,
                })

            # 4. Done
            yield _sse("complete", {
                "build_id": build_id,
                "build_name": build.name,
                "class_en": build.class_en,
                "class_cn": build.class_cn,
                "profile_names": names,
            })

        except Exception as e:
            yield _sse("fail", {"message": str(e)})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
