"""
PPT生成API v2 - 简化版接口

支持直接输入任意文本内容，返回完整的 HTML 文件内容（而非文件路径）。
"""

import logging
from typing import Optional
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
import httpx

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ppt-v2"])

PPT_SERVICE_BASE = "http://127.0.0.1:18765"

# PPT 风格到主题的映射
STYLE_THEME_MAP = {
    # 学术/正式
    "学术简约": "academic-paper",
    "学术论文": "academic-paper",
    "简约白底": "minimal-white",
    "编辑风格": "editorial-serif",
    "瑞士网格": "swiss-grid",

    # 技术/开发
    "技术分享": "tokyo-night",
    "代码风格": "dracula",
    "终端绿": "terminal-green",
    "工程图纸": "blueprint",
    "工程白图": "engineering-whiteprint",

    # 商务/正式
    "企业商务": "corporate-clean",
    "投资路演": "pitch-deck-vc",
    "新闻播报": "news-broadcast",

    # 时尚/设计
    "小红书风": "xiaohongshu-white",
    "柔和粉彩": "soft-pastel",
    "彩虹渐变": "rainbow-gradient",
    "极光渐变": "aurora",
    "玻璃质感": "glassmorphism",
    "新粗野主义": "neo-brutalism",
    "包豪斯": "bauhaus",
    "日式极简": "japanese-minimal",
    "杂志封面": "magazine-bold",

    # 主题色系
    "北欧冷色": "nord",
    "北极冷调": "arctic-cool",
    "日落暖调": "sunset-warm",
    "拿铁浅色": "catppuccin-latte",
    "摩卡深色": "catppuccin-mocha",
    "玫瑰松": "rose-pine",
    "索拉浅色": "solarized-light",
    "gruvbox深色": "gruvbox-dark",

    # 特殊风格
    "赛博朋克": "cyberpunk-neon",
    "蒸汽波": "vaporwave",
    "Y2K复古": "y2k-chrome",
    "复古电视": "retro-tv",
    "孟菲斯": "memphis-pop",
    "世纪中": "midcentury",
    "锐利黑白": "sharp-mono",
}


class PPTGenerateV2Request(BaseModel):
    """PPT生成请求 v2"""
    config: dict = Field(..., description="配置信息")
    content: str = Field(..., description="任意文本内容，由LLM解析并生成PPT")


class PPTGenerateV2Response(BaseModel):
    """PPT生成响应 v2"""
    ok: bool
    html: Optional[str] = None
    slideCount: Optional[int] = None
    theme: Optional[str] = None
    error: Optional[str] = None


def get_theme_from_style(style: str) -> str:
    """根据风格名称获取主题"""
    return STYLE_THEME_MAP.get(style, "minimal-white")


@router.post("/ppt/generate", response_model=PPTGenerateV2Response)
async def generate_ppt_v2(request: PPTGenerateV2Request):
    """
    生成HTML PPT课件

    输入任意文本内容，自动由LLM解析并生成结构化的PPT。
    返回完整的HTML内容（而非文件路径）。
    """
    try:
        config = request.config
        output_language = config.get("outputLanguage", "中文")
        ppt_style = config.get("pptStyle", "学术简约")
        page_min = config.get("pageMin", 8)
        page_max = config.get("pageMax", 12)

        # 映射风格到主题
        theme = get_theme_from_style(ppt_style)

        # 构造 deck 名称
        import time
        deck_name = f"v2-{int(time.time())}"

        # 构建 ppt_service 请求
        payload = {
            "deckName": deck_name,
            "theme": theme,
            "renderThumbnails": False,
            "modelDriven": True,
            "modelProvider": "openai",
            "injectSkillPrompt": True,
            "pageMin": page_min,
            "pageMax": page_max,
            "pptInput": {
                "content": request.content,
                "outputLanguage": output_language,
                "instructions": f"将以下内容转换为 {page_min}-{page_max} 页的 {ppt_style} 风格课件，使用 {output_language}。"
            },
            "modelBaseUrl": "http://127.0.0.1:9000",
            "modelApiKey": "sk-demo-key-replace-this"
        }

        logger.info(f"PPT v2 generate: style={ppt_style}, theme={theme}, pages={page_min}-{page_max}")

        # 调用 ppt_service
        async with httpx.AsyncClient(timeout=180.0) as client:
            resp = await client.post(
                f"{PPT_SERVICE_BASE}/api/ppt/generate",
                json=payload
            )

        if resp.status_code != 200:
            error_text = resp.text
            logger.error(f"ppt_service returned {resp.status_code}: {error_text}")
            return PPTGenerateV2Response(ok=False, error=f"ppt_service error: {error_text}")

        data = resp.json()

        if not data.get("ok"):
            return PPTGenerateV2Response(ok=False, error=data.get("error", "unknown error"))

        result = data["result"]
        html_url = result.get("htmlUrl", "")

        # 读取生成的 HTML 文件内容
        async with httpx.AsyncClient(timeout=10.0) as client:
            html_resp = await client.get(
                f"{PPT_SERVICE_BASE}{html_url}",
                headers={"Host": "127.0.0.1:18765"}
            )

        if html_resp.status_code != 200:
            logger.error(f"Failed to read HTML: {html_resp.status_code}")
            return PPTGenerateV2Response(
                ok=False,
                error=f"HTML file not accessible: {html_resp.status_code}"
            )

        html_content = html_resp.text

        return PPTGenerateV2Response(
            ok=True,
            html=html_content,
            slideCount=result.get("slideCount"),
            theme=theme
        )

    except httpx.ConnectError:
        logger.error("Cannot connect to ppt_service at %s", PPT_SERVICE_BASE)
        raise HTTPException(
            status_code=503,
            detail="PPT服务未启动，请先启动 ppt_service (端口18765)"
        )
    except Exception as e:
        logger.error(f"PPT v2 generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ppt/styles")
async def list_styles():
    """列出所有支持的PPT风格"""
    styles = list(STYLE_THEME_MAP.keys())
    return {
        "styles": styles,
        "count": len(styles),
        "mapping": STYLE_THEME_MAP
    }


@router.post("/ppt/generate-raw", response_class=HTMLResponse)
async def generate_ppt_v2_raw(request: PPTGenerateV2Request):
    """
    生成HTML PPT（直接返回HTML文本）

    与 /ppt/generate 相同，但直接返回 text/html 响应而非 JSON。
    """
    result = await generate_ppt_v2(request)

    if not result.ok:
        raise HTTPException(status_code=500, detail=result.error)

    return HTMLResponse(content=result.html, media_type="text/html")
