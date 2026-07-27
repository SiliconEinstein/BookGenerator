import os
import json
import logging
from typing import Dict, List, Optional, Any

from ..insert.position_selector import InsertPositionSelector
from ..insert.tag_inserter import build_image_marker, insert_image_tags
from .draw_by_text import generate_image_from_context


INSERT_META_MAX_ATTEMPTS = 3
logger = logging.getLogger(__name__)


async def generate_images_from_markdown(
    markdown_path: str,
    output_dir: str,
    prompt_dir: str = "./prompt",
    save_manifest: Optional[str] = None,
    client: Optional[Any] = None,
) -> List[Dict[str, str]]:
    if client is None:
        raise ValueError("client 不能为空，请传入 DrawImageAgent 实例")
    with open(markdown_path, "r", encoding="utf-8") as f:
        markdown_text = f.read()
    selector = InsertPositionSelector(client, prompt_dir=prompt_dir)
    tagged_markdown = ""
    inserted: List[Dict[str, object]] = []

    for attempt in range(INSERT_META_MAX_ATTEMPTS):
        positions = await selector.select(markdown_text)
        tagged_markdown, inserted = insert_image_tags(markdown_text, positions)
        if inserted:
            break
        if attempt < INSERT_META_MAX_ATTEMPTS - 1:
            logger.warning(
                "未选出插入位置（inserted 为空），第 %d/%d 次重试…",
                attempt + 2,
                INSERT_META_MAX_ATTEMPTS,
            )

    os.makedirs(output_dir, exist_ok=True)
    meta_path = os.path.join(output_dir, "insert_meta.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(inserted, f, indent=4, ensure_ascii=False)
    results: List[Dict[str, str]] = []
    for item in inserted:
        image_name = f"image_{item['index']}.png"
        context = item['context_text']
        reason = item['reason']
        image_path = await generate_image_from_context(
            context=context,
            output_dir=output_dir,
            image_name=image_name,
            reason=reason,
            prompt_dir=prompt_dir,
            client=client,
        )
        if not image_path:
            # 出图失败时摘掉占位标签，否则成书里会留下指向空文件的图片链接
            logger.warning("image_%s 生成失败，已从正文中移除该插图标签", item['index'])
            tagged_markdown = _drop_marker(tagged_markdown, int(item['index']))
            continue
        results.append({"index": str(item['index']), "context": context, "image_path": image_path, "reason": reason})
    if inserted:
        final_path = os.path.join(output_dir, "with_images.md")
        with open(final_path, "w", encoding="utf-8") as f:
            f.write(tagged_markdown)
    if save_manifest:
        with open(save_manifest, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=4, ensure_ascii=False)
    return results


def _drop_marker(markdown_text: str, index: int) -> str:
    marker = build_image_marker(index)
    return "\n".join(line for line in markdown_text.splitlines() if line.strip() != marker)