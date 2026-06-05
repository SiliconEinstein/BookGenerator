"""
PPT生成API路由模块

提供专用的HTML PPT生成接口，代理到 html-ppt-skill 的 ppt_service。
"""

import logging
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import httpx

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ppt"])

# ppt_service 地址
PPT_SERVICE_BASE = "http://127.0.0.1:18765"


class PPTGenerateRequest(BaseModel):
    """PPT生成请求"""
    deckName: str = Field(..., description="生成的deck名称，用于文件命名")
    theme: str = Field(default="aurora", description="主题名称，36个可选主题")
    chapterName: str = Field(default="", description="章节名称")
    sectionName: str = Field(default="", description="小节名称")
    teachingGoal: str = Field(default="", description="教学目标")
    knowledgePoints: str = Field(default="", description="知识点")
    suggestedStructure: str = Field(default="", description="建议的课程结构")
    extraInfo: str = Field(default="", description="额外信息/备注")
    pageMin: int = Field(default=8, description="最少页数")
    pageMax: int = Field(default=12, description="最多页数")
    renderThumbnails: bool = Field(default=False, description="是否渲染缩略图")
    modelDriven: bool = Field(default=True, description="是否使用模型驱动生成")
    modelProvider: str = Field(default="openai", description="模型提供方: gpugeek/anthropic/openai")
    modelName: Optional[str] = Field(default=None, description="模型名称")
    modelBaseUrl: Optional[str] = Field(default=None, description="模型API基础URL")
    modelApiKey: Optional[str] = Field(default=None, description="模型API Key")


class PPTGenerateResponse(BaseModel):
    """PPT生成响应"""
    ok: bool
    result: Optional[dict] = None
    error: Optional[str] = None


@router.post("/ppt/generate", response_model=PPTGenerateResponse)
async def generate_ppt(request: PPTGenerateRequest):
    """
    生成HTML PPT课件

    将请求转发到 html-ppt-skill 的 ppt_service，
    使用模型驱动模式生成专业的HTML演示文稿。
    """
    try:
        # 构建 ppt_service 期望的请求体
        payload = {
            "deckName": request.deckName,
            "theme": request.theme,
            "renderThumbnails": request.renderThumbnails,
            "modelDriven": request.modelDriven,
            "modelProvider": request.modelProvider,
            "injectSkillPrompt": True,
            "pageMin": request.pageMin,
            "pageMax": request.pageMax,
            "pptInput": {
                "chapterName": request.chapterName,
                "sectionName": request.sectionName,
                "teachingGoal": request.teachingGoal,
                "knowledgePoints": request.knowledgePoints,
                "suggestedStructure": request.suggestedStructure,
                "extraInfo": request.extraInfo,
            }
        }

        if request.modelName:
            payload["modelName"] = request.modelName
        if request.modelBaseUrl:
            payload["modelBaseUrl"] = request.modelBaseUrl
        if request.modelApiKey:
            payload["modelApiKey"] = request.modelApiKey

        logger.info(f"PPT generate request: deckName={request.deckName}, theme={request.theme}")

        async with httpx.AsyncClient(timeout=180.0) as client:
            resp = await client.post(
                f"{PPT_SERVICE_BASE}/api/ppt/generate",
                json=payload
            )

        if resp.status_code != 200:
            error_text = resp.text
            logger.error(f"ppt_service returned {resp.status_code}: {error_text}")
            return PPTGenerateResponse(ok=False, error=f"ppt_service error: {error_text}")

        data = resp.json()

        # 补充完整的预览URL
        if data.get("ok") and data.get("result"):
            html_url = data["result"].get("htmlUrl", "")
            data["result"]["previewUrl"] = f"{PPT_SERVICE_BASE}{html_url}"

        return PPTGenerateResponse(ok=data.get("ok", False), result=data.get("result"))

    except httpx.ConnectError:
        logger.error("Cannot connect to ppt_service at %s", PPT_SERVICE_BASE)
        raise HTTPException(
            status_code=503,
            detail="PPT服务未启动，请先启动 ppt_service (端口18765)"
        )
    except Exception as e:
        logger.error(f"PPT generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ppt/themes")
async def list_themes():
    """列出所有可用的PPT主题"""
    themes = [
        "minimal-white", "editorial-serif", "soft-pastel", "sharp-mono",
        "arctic-cool", "sunset-warm", "catppuccin-latte", "catppuccin-mocha",
        "dracula", "tokyo-night", "nord", "solarized-light", "gruvbox-dark",
        "rose-pine", "neo-brutalism", "glassmorphism", "bauhaus", "swiss-grid",
        "terminal-green", "xiaohongshu-white", "rainbow-gradient", "aurora",
        "blueprint", "memphis-pop", "cyberpunk-neon", "y2k-chrome", "retro-tv",
        "japanese-minimal", "vaporwave", "midcentury", "corporate-clean",
        "academic-paper", "news-broadcast", "pitch-deck-vc", "magazine-bold",
        "engineering-whiteprint"
    ]
    return {"themes": themes, "count": len(themes)}


@router.get("/ppt/health")
async def ppt_service_health():
    """检查PPT服务是否可用"""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{PPT_SERVICE_BASE}/healthz")
        if resp.status_code == 200:
            return resp.json()
        return {"ok": False, "error": f"status {resp.status_code}"}
    except httpx.ConnectError:
        return {"ok": False, "error": "ppt_service not running"}
