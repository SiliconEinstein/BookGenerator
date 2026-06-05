"""
PPT生成API v3 - 基于 Claude CLI + html-ppt skill

直接调用 Claude CLI，让 Claude 使用 html-ppt skill 自主决策布局和内容组织。
"""

import logging
import re
import json
from typing import Optional
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ...services.claude_service import ClaudeProcess, ClaudeProcessConfig

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ppt-v3"])

# 复用 ppt_v2 的风格映射
from .ppt_v2 import STYLE_THEME_MAP, get_theme_from_style

# html-ppt-skill 的输出目录
HTML_PPT_OUTPUT = Path("/personal/AI备课助手/html-ppt-skill/output")


class PPTGenerateV3Request(BaseModel):
    """PPT生成请求 v3"""
    config: dict = Field(..., description="配置信息")
    content: str = Field(..., description="任意文本内容")


class PPTGenerateV3Response(BaseModel):
    """PPT生成响应 v3"""
    ok: bool
    html: Optional[str] = None
    slideCount: Optional[int] = None
    theme: Optional[str] = None
    error: Optional[str] = None


def build_claude_prompt(content: str, style: str, theme: str, page_min: int, page_max: int, output_language: str) -> str:
    """构建给 Claude CLI 的 prompt"""

    return f"""请为以下内容生成一个 HTML 演示文稿。

**内容：**
{content}

**要求：**
- 主题（theme）：{theme}
- 页数范围：{page_min}-{page_max} 页
- 输出语言：{output_language}
- 输出文件路径：output/ppt-v3-latest.html

**具体步骤：**
1. 使用 Read 工具读取 templates/deck.html 作为基础模板
2. 使用 Glob 工具列出 templates/single-page/ 目录下的所有布局文件
3. 根据内容特点，选择 2-4 种合适的布局类型（如 cover.html, bullets.html, two-column.html 等）
4. 使用 Read 工具读取选定的布局文件，了解每种布局的 HTML 结构
5. 基于 deck.html 的结构，将选定的布局组装成完整的 HTML 文件
6. 确保 HTML 中设置 data-theme="{theme}"
7. 使用 Write 工具将最终的 HTML 内容写入 output/ppt-v3-latest.html

现在开始执行这些步骤。"""


@router.post("/ppt/generate-v3", response_model=PPTGenerateV3Response)
async def generate_ppt_v3(request: PPTGenerateV3Request):
    """
    使用 Claude CLI + html-ppt skill 生成 HTML PPT

    Claude 会自主决策布局选择和内容组织。
    """
    try:
        config = request.config
        output_language = config.get("outputLanguage", "中文")
        ppt_style = config.get("pptStyle", "学术简约")
        page_min = config.get("pageMin", 4)
        page_max = config.get("pageMax", 8)

        # 映射风格到主题
        theme = get_theme_from_style(ppt_style)

        logger.info(f"PPT v3 generate: style={ppt_style}, theme={theme}, pages={page_min}-{page_max}")

        # 构建 prompt
        prompt = build_claude_prompt(
            content=request.content,
            style=ppt_style,
            theme=theme,
            page_min=page_min,
            page_max=page_max,
            output_language=output_language
        )

        # 调用 Claude CLI
        process_config = ClaudeProcessConfig(
            working_dir="/personal/AI备课助手/html-ppt-skill",
            timeout=300
        )

        claude_process = ClaudeProcess(process_config)
        await claude_process.start()

        # 收集 Claude 的完整响应
        full_response = ""
        async for chunk in claude_process.send_message(prompt):
            full_response += chunk

        logger.info(f"Claude response length: {len(full_response)}")

        # 查找生成的文件
        output_file = HTML_PPT_OUTPUT / "ppt-v3-latest.html"

        if not output_file.exists():
            # 尝试从响应中提取文件路径
            logger.warning(f"Expected file not found: {output_file}")
            # 查找最新生成的 HTML 文件
            if HTML_PPT_OUTPUT.exists():
                html_files = sorted(HTML_PPT_OUTPUT.glob("*.html"), key=lambda p: p.stat().st_mtime, reverse=True)
                if html_files:
                    output_file = html_files[0]
                    logger.info(f"Using latest HTML file: {output_file}")
                else:
                    return PPTGenerateV3Response(
                        ok=False,
                        error=f"Claude 未生成 HTML 文件。响应内容：{full_response[:500]}"
                    )
            else:
                return PPTGenerateV3Response(
                    ok=False,
                    error=f"输出目录不存在: {HTML_PPT_OUTPUT}"
                )

        # 读取生成的 HTML
        html_content = output_file.read_text(encoding="utf-8")

        # 计算 slide 数量
        slide_count = len(re.findall(r'<section class="slide[\s"]', html_content))

        return PPTGenerateV3Response(
            ok=True,
            html=html_content,
            slideCount=slide_count,
            theme=theme
        )

    except Exception as e:
        logger.error(f"PPT v3 generation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ppt/v3/status")
async def get_v3_status():
    """检查 v3 版本的依赖状态"""

    skill_dir = Path("/personal/AI备课助手/html-ppt-skill")
    output_dir = HTML_PPT_OUTPUT
    skill_registered = Path.home() / ".claude/skills/html-ppt"

    return {
        "skill_exists": skill_dir.exists(),
        "skill_md_exists": (skill_dir / "SKILL.md").exists(),
        "templates_exist": (skill_dir / "templates").exists(),
        "output_dir_exists": output_dir.exists(),
        "output_dir_writable": output_dir.exists() and output_dir.is_dir(),
        "skill_registered": skill_registered.exists(),
        "skill_link_target": str(skill_registered.resolve()) if skill_registered.exists() else None
    }
