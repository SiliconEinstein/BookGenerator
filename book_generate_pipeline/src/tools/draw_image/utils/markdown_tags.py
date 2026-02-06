import re
from typing import List, Tuple


IMAGE_BLOCK_PATTERN = re.compile(r"<image(\d+)>([\s\S]*?)</image\1>")


def parse_image_blocks(markdown_text: str) -> List[Tuple[int, str]]:
    blocks = []
    for match in IMAGE_BLOCK_PATTERN.finditer(markdown_text):
        idx = int(match.group(1))
        context = match.group(2).strip()
        blocks.append((idx, context))
    return blocks
