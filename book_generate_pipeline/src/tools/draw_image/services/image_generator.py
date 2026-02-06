import os
from typing import Optional

from ..draw_image_agent import DrawImageAgent


class ImageGenerator:
    def __init__(self, prompt_dir: str = "./prompt") -> None:
        self.prompt_dir = prompt_dir
        self.agent = DrawImageAgent()

    async def generate(
        self,
        context: str,
        output_dir: str,
        image_name: str,
        reason: Optional[str] = None,
    ) -> str:
        if not context.strip():
            raise ValueError("context 不能为空")
        os.makedirs(output_dir, exist_ok=True)
        if reason is None:
            reason = ""
        prompt_content = {"【CONTEXT】": context, "【REASON】": reason}
        prompt = self.agent.get_prompt(self.prompt_dir, "draw_by_text", prompt_content)
        await self.agent.produce_image(prompt, output_dir=output_dir, image_name=image_name)
        return os.path.join(output_dir, image_name)
