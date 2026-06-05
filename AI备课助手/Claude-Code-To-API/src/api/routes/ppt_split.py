"""
PPT生成API - 按页拆分版本

生成 PPT 后将每一页拆分为独立的 HTML 文件。
"""

import logging
import re
import base64
from typing import Optional, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import httpx
from pathlib import Path

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ppt-split"])

PPT_SERVICE_BASE = "http://127.0.0.1:18765"

# 复用 ppt_v2 的风格映射
from .ppt_v2 import STYLE_THEME_MAP, get_theme_from_style

# html-ppt-skill 的 assets 目录路径
HTML_PPT_ASSETS = Path("/personal/AI备课助手/html-ppt-skill/assets")


class PPTPageHTML(BaseModel):
    """单页 HTML"""
    page: int = Field(..., description="页码（从1开始）")
    title: str = Field(..., description="页面标题")
    html: str = Field(..., description="完整的单页 HTML 内容")


class PPTGenerateSplitRequest(BaseModel):
    """PPT 拆分生成请求"""
    config: dict = Field(..., description="配置信息")
    content: str = Field(..., description="任意文本内容")


class PPTGenerateSplitResponse(BaseModel):
    """PPT 拆分生成响应"""
    ok: bool
    slideCount: Optional[int] = None
    theme: Optional[str] = None
    pages: Optional[List[PPTPageHTML]] = None
    error: Optional[str] = None


def extract_slides_from_html(html_content: str) -> List[tuple]:
    """
    从完整 HTML 中提取每个 slide 的内容

    返回: [(page_num, title, slide_html), ...]
    """
    # 提取所有 <section class="slide"> 块
    pattern = r'<section class="slide"[^>]*?data-title="([^"]*)"[^>]*?>(.*?)</section>'
    matches = re.findall(pattern, html_content, re.DOTALL)

    slides = []
    for idx, (title, content) in enumerate(matches, start=1):
        slides.append((idx, title, content))

    return slides


def load_css_resources(theme: str) -> str:
    """
    加载并合并所有CSS资源（fonts, base, theme, animations）

    返回完整的内联CSS内容
    """
    css_parts = []

    # 1. fonts.css
    fonts_css = HTML_PPT_ASSETS / "fonts.css"
    if fonts_css.exists():
        css_parts.append(fonts_css.read_text(encoding="utf-8"))

    # 2. base.css
    base_css = HTML_PPT_ASSETS / "base.css"
    if base_css.exists():
        css_parts.append(base_css.read_text(encoding="utf-8"))

    # 3. theme CSS (如 aurora.css)
    theme_css = HTML_PPT_ASSETS / "themes" / f"{theme}.css"
    if theme_css.exists():
        css_parts.append(theme_css.read_text(encoding="utf-8"))

    # 4. animations.css
    animations_css = HTML_PPT_ASSETS / "animations" / "animations.css"
    if animations_css.exists():
        css_parts.append(animations_css.read_text(encoding="utf-8"))

    return "\n\n".join(css_parts)


def build_single_page_html(
    title: str,
    theme: str,
    page_num: int,
    total_pages: int,
    slide_content: str,
    deck_title: str
) -> str:
    """
    构建单页独立 HTML

    所有CSS完全内联，无外部依赖
    """
    # 加载完整CSS
    inline_css = load_css_resources(theme)

    return f"""<!DOCTYPE html>
<html lang="zh-CN" data-theme="{theme}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>
{inline_css}

/* 单页适配样式 - 覆盖多页演示的默认隐藏行为 */
.slide {{
  opacity: 1 !important;
  pointer-events: auto !important;
  transform: none !important;
  position: absolute;
  inset: 0;
}}

.slide-number:after {{
  content: "{page_num} / {total_pages}";
}}
</style>
</head>
<body class="single">
<div class="deck">
  <section class="slide is-active" data-title="{title}">
    {slide_content}
  </section>
</div>
</body>
</html>
"""


@router.post("/ppt/generate-split", response_model=PPTGenerateSplitResponse)
async def generate_ppt_split(request: PPTGenerateSplitRequest):
    """
    生成 HTML PPT 并按页拆分

    返回每一页的独立 HTML 文件内容。
    每个 HTML 都是完整的、可独立打开的文件（CSS 内联）。
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
        deck_name = f"split-{int(time.time())}"

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

        logger.info(f"PPT split generate: style={ppt_style}, theme={theme}, pages={page_min}-{page_max}")

        # 调用 ppt_service 生成完整 HTML
        async with httpx.AsyncClient(timeout=180.0) as client:
            resp = await client.post(
                f"{PPT_SERVICE_BASE}/api/ppt/generate",
                json=payload
            )

        if resp.status_code != 200:
            error_text = resp.text
            logger.error(f"ppt_service returned {resp.status_code}: {error_text}")
            return PPTGenerateSplitResponse(ok=False, error=f"ppt_service error: {error_text}")

        data = resp.json()

        if not data.get("ok"):
            return PPTGenerateSplitResponse(ok=False, error=data.get("error", "unknown error"))

        result = data["result"]
        html_url = result.get("htmlUrl", "")
        slide_count = result.get("slideCount", 0)

        # 读取生成的完整 HTML
        async with httpx.AsyncClient(timeout=10.0) as client:
            html_resp = await client.get(
                f"{PPT_SERVICE_BASE}{html_url}",
                headers={"Host": "127.0.0.1:18765"}
            )

        if html_resp.status_code != 200:
            logger.error(f"Failed to read HTML: {html_resp.status_code}")
            return PPTGenerateSplitResponse(
                ok=False,
                error=f"HTML file not accessible: {html_resp.status_code}"
            )

        full_html = html_resp.text

        # 提取 deck 标题
        deck_title_match = re.search(r'<title>([^<]+)</title>', full_html)
        deck_title = deck_title_match.group(1) if deck_title_match else "PPT"

        # 提取每一页的 slide
        slides = extract_slides_from_html(full_html)

        if not slides:
            return PPTGenerateSplitResponse(
                ok=False,
                error="无法从生成的 HTML 中提取 slide 内容"
            )

        # 为每一页生成独立的 HTML
        pages = []
        for page_num, slide_title, slide_content in slides:
            single_html = build_single_page_html(
                title=slide_title,
                theme=theme,
                page_num=page_num,
                total_pages=len(slides),
                slide_content=slide_content,
                deck_title=deck_title
            )

            pages.append(PPTPageHTML(
                page=page_num,
                title=slide_title,
                html=single_html
            ))

        logger.info(f"Successfully split {len(pages)} pages")

        return PPTGenerateSplitResponse(
            ok=True,
            slideCount=slide_count,
            theme=theme,
            pages=pages
        )

    except httpx.ConnectError:
        logger.error("Cannot connect to ppt_service at %s", PPT_SERVICE_BASE)
        raise HTTPException(
            status_code=503,
            detail="PPT服务未启动，请先启动 ppt_service (端口18765)"
        )
    except Exception as e:
        logger.error(f"PPT split generation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
