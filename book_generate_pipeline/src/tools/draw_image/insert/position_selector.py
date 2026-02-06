import json
from typing import List, Dict, Any

from .text_utils import build_numbered_content


class InsertPositionSelector:
    def __init__(self, agent: Any, prompt_dir: str = "./prompt") -> None:
        self.prompt_dir = prompt_dir
        self.agent = agent

    async def select(self, markdown_text: str) -> List[Dict[str, object]]:
        content_lines, numbered = build_numbered_content(markdown_text)
        if not content_lines:
            return []
        prompt = self.agent.get_prompt(
            self.prompt_dir,
            "get_insert_position",
            {"【ARTICLE】": numbered},
        )
        positions = await self.agent.produce_response(prompt)
        if not positions:
            return []
        return positions
