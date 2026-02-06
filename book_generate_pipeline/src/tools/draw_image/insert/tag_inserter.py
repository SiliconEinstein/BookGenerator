from typing import List, Dict, Tuple

from .text_utils import build_content_lines, find_insert_index, build_context_text, clean_line


def build_image_marker(index: int) -> str:
    image_name = f"image_{index}.png"
    return f"![{image_name}]({image_name})"


def insert_image_tags(
    markdown_text: str,
    positions: List[Dict[str, object]],
) -> Tuple[str, List[Dict[str, object]]]:
    lines = markdown_text.splitlines()
    content_lines = build_content_lines(markdown_text)
    inserted = []
    cursor = 0

    image_index = 0
    for idx, item in enumerate(positions):
        position_text = str(item.get("position", "")).strip()
        reason = item.get("reason", "")
        context_indices = item.get("context", [])
        if not position_text:
            continue
        insert_at = find_insert_index(
            [clean_line(line) for line in lines], position_text, cursor
        )
        if insert_at == -1:
            continue
        context_text = build_context_text(content_lines, context_indices)
        marker = build_image_marker(image_index)
        lines.insert(insert_at + 1, marker)
        cursor = insert_at + 2
        inserted.append(
            {
                "index": image_index,
                "source_index": idx,
                "position": position_text,
                "reason": reason,
                "context": context_indices,
                "context_text": context_text,
            }
        )
        image_index += 1

    return "\n".join(lines), inserted
