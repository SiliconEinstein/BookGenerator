import json
import asyncio
from pathlib import Path

from draw_image_agent import DrawImageAgent

INPUT_PATH = Path(r"F:\SciencePedia\draw_chem\workspace\output\draw_image_prompts.json")
OUTPUT_DIR = Path(r"F:\SciencePedia\draw_chem\draw_image\output")
PROMPT_DIR = r"F:\SciencePedia\draw_chem\draw_image\prompt"

async def main():
    with INPUT_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)
    agent = DrawImageAgent()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for idx, item in enumerate(data):
        context = (item.get("context") or "").strip()
        if not context:
            continue
        image_name = f"context_{idx}.png"
        await agent.draw_by_text(
            context=context,
            output_dir=str(OUTPUT_DIR),
            image_name=image_name,
            prompt_dir=PROMPT_DIR,
        )

asyncio.run(main())