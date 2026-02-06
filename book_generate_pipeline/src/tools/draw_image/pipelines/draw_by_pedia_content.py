import os
import json
from typing import List, Dict, Tuple, Optional, Any, Union

from ..insert.position_selector import InsertPositionSelector
from ..insert.tag_inserter import insert_image_tags
from .draw_by_markdown import generate_images_from_markdown as _generate_images_from_markdown
from ..utils.markdown_tags import parse_image_blocks as _parse_image_blocks


def build_pedia_markdown(main_content: str, applications: str) -> str:
    return "\n\n".join(
        [
            "# Main Content",
            main_content.strip(),
            "# Applications",
            applications.strip(),
        ]
    ).strip()


def parse_image_blocks(markdown_text: str) -> List[Tuple[int, str]]:
    return _parse_image_blocks(markdown_text)


async def generate_images_from_markdown(
    markdown_path: str,
    output_dir: str,
    prompt_dir: str = "./prompt",
    save_manifest: Optional[str] = None,
    client: Optional[Any] = None,
) -> List[Dict[str, str]]:
    return await _generate_images_from_markdown(
        markdown_path=markdown_path,
        output_dir=output_dir,
        prompt_dir=prompt_dir,
        save_manifest=save_manifest,
        client=client,
    )


async def draw_by_pedia_content(
    article_id: int,
    output_dir: str,
    prompt_dir: str = "./prompt",
    client: Optional[Any] = None,
) -> Dict[str, object]:
    if client is None:
        raise ValueError("client 不能为空，请传入 DrawImageAgent 实例")
    os.makedirs(output_dir, exist_ok=True)
    article_content: Union[str, Tuple[str, str]] = client.get_article(article_id)
    if isinstance(article_content, tuple):
        markdown_text = build_pedia_markdown(article_content[0], article_content[1])
    else:
        markdown_text = article_content

    selector = InsertPositionSelector(client, prompt_dir=prompt_dir)
    positions = await selector.select(markdown_text)

    tagged_markdown, inserted = insert_image_tags(markdown_text, positions)
    markdown_path = os.path.join(output_dir, f"{article_id}.md")
    with open(markdown_path, "w", encoding="utf-8") as f:
        f.write(tagged_markdown)

    meta_path = os.path.join(output_dir, f"{article_id}_insert_meta.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(inserted, f, indent=4, ensure_ascii=False)

    images = await generate_images_from_markdown(
        markdown_path=markdown_path,
        output_dir=output_dir,
        prompt_dir=prompt_dir,
        save_manifest=os.path.join(output_dir, f"{article_id}_images.json"),
        client=client,
    )
    return {
        "article_id": article_id,
        "markdown_path": markdown_path,
        "insert_meta_path": meta_path,
        "images": images,
    }