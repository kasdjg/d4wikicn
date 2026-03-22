"""D4Wiki 统一服务入口 — FastAPI 应用"""

import uvicorn
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from admin.router import router as admin_router
from api import router as build_router

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="D4Wiki Server")

# 管理后台 API
app.include_router(admin_router, prefix="/admin/api")

# 翻译 API（供前端调用）
app.include_router(build_router, prefix="/api")

# 管理后台静态页面
app.mount("/admin", StaticFiles(directory=BASE_DIR / "admin" / "static", html=True), name="admin")

# 用户端页面（放最后，因为 / 是通配）
app.mount("/", StaticFiles(directory=BASE_DIR / "web", html=True), name="web")

if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
