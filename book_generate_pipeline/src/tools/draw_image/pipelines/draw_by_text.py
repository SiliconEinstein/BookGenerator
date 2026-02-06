import os
from typing import Optional, Any


async def generate_image_from_context(
    context: str,
    output_dir: str,
    image_name: str,
    reason: Optional[str] = None,
    prompt_dir: str = "./prompt",
    client: Optional[Any] = None,
) -> str:
    if client is None:
        raise ValueError("client 不能为空，请传入 DrawImageAgent 实例")
    if not context.strip():
        raise ValueError("context 不能为空")
    os.makedirs(output_dir, exist_ok=True)
    prompt_content = {"【CONTEXT】": context, "【REASON】": reason or ""}
    prompt = client.get_prompt(prompt_dir, "draw_by_text", prompt_content)
    await client.produce_image(prompt, output_dir=output_dir, image_name=image_name)
    return os.path.join(output_dir, image_name)
