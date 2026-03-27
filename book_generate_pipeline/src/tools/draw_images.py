"""High-level helpers for drawing images into markdown files."""

import os
import re
from pathlib import Path
from typing import Dict, List, Optional

from src.tools.draw_image.draw_image_agent import DrawImageAgent


async def draw_images_for_markdown(
    md_path: str,
    image_output_dir: str,
    new_md_path: str,
    prompt_dir: str = None,
) -> List[Dict[str, str]]:
    """Generate images for a markdown file and save a new markdown with image tags.

    Args:
        md_path: Source markdown file path.
        image_output_dir: Directory to save generated images and manifests.
        new_md_path: Output markdown path with inserted image tags.
        prompt_dir: Prompt directory used by the draw image pipeline.

    Returns:
        List of generated image metadata.
    """
    if prompt_dir is None:
        default_prompt_dir = Path(__file__).parent / "draw_image" / "prompt"
        pack_prompt_dir = Path(md_path).resolve().parents[2] / "pack" / "prompts"
        # 优先使用 pack 中的绘图提示词；其余缺失提示词由 DrawImageAgent 内部回退到默认目录。
        if (pack_prompt_dir / "draw_by_text").exists():
            prompt_dir = pack_prompt_dir
        else:
            prompt_dir = default_prompt_dir
        
    if not os.path.exists(md_path):
        raise FileNotFoundError(f"Markdown file not found: {md_path}")

    os.makedirs(image_output_dir, exist_ok=True)
    os.makedirs(os.path.dirname(new_md_path), exist_ok=True)

    agent = DrawImageAgent()
    manifest_path = os.path.join(image_output_dir, "images.json")

    items = await agent.draw_by_markdown(
        markdown_path=md_path,
        output_dir=image_output_dir,
        prompt_dir=prompt_dir,
        save_manifest=manifest_path,
    )

    tagged_path = os.path.join(image_output_dir, "with_images.md")
    if os.path.exists(tagged_path):
        tagged_content = Path(tagged_path).read_text(encoding="utf-8")
    else:
        tagged_content = Path(md_path).read_text(encoding="utf-8")

    new_md_dir = os.path.dirname(new_md_path)
    for item in items:
        index = str(item.get("index", "")).strip()
        image_path = item.get("image_path", "")
        if not index or not image_path:
            continue
        image_name = f"image_{index}.png"
        rel_path = os.path.relpath(image_path, new_md_dir).replace("\\", "/")
        pattern = re.escape(f"![{image_name}](") + r"[^)]*\)"
        replacement = f"![{image_name}]({rel_path})"
        tagged_content = re.sub(pattern, replacement, tagged_content, count=1)

    Path(new_md_path).write_text(tagged_content, encoding="utf-8")
    return items
