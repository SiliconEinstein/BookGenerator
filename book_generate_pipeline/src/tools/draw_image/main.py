import argparse
import asyncio
import os
import sys
from pathlib import Path
import json

if __package__ is None or __package__ == "":
    sys.path.append(os.path.dirname(os.path.dirname(__file__)))

try:
    from .draw_image_agent import DrawImageAgent
    from .services.validator import evaluate_images
except ImportError:
    from draw_image_agent import DrawImageAgent
    from services.validator import evaluate_images


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Draw image pipeline")
    # 指定输入类型，包含text、markdown、pedia
    subparsers = parser.add_subparsers(dest="command", default="markdown", required=True)

    text_parser = subparsers.add_parser("text", help="输入上下文生成图片")
    text_parser.add_argument("--context", required=True)
    text_parser.add_argument("--output-dir", default="./output")
    text_parser.add_argument("--image-name", default="image.png")
    text_parser.add_argument("--reason", default="")

    md_parser = subparsers.add_parser("markdown", help="解析markdown标签生成图片")
    md_parser.add_argument(
        "--markdown-path",
        default=r"F:\SciencePedia\topic_book_generation\book_generate_pipeline\output\可控核聚变\temp\md\第1章_工程目标_指标体系与方案闭环边界.md",
        required=True
    )
    md_parser.add_argument("--output-dir", default="./output")
    md_parser.add_argument("--manifest", default="")
    md_parser.add_argument("--eval", action="store_true")

    pedia_parser = subparsers.add_parser("pedia", help="根据文章编号生成md并绘图")
    pedia_parser.add_argument("--article-id", type=int, required=True)
    pedia_parser.add_argument("--output-dir", default="./output")
    pedia_parser.add_argument("--eval", action="store_true")

    return parser


async def run_text(args: argparse.Namespace) -> None:
    agent = DrawImageAgent()
    await agent.draw_by_text(
        context=args.context,
        output_dir=args.output_dir,
        image_name=args.image_name,
        reason=args.reason,
    )


async def run_markdown(args: argparse.Namespace) -> None:
    agent = DrawImageAgent()
    manifest_path = args.manifest or os.path.join(args.output_dir, "images.json")
    items = await agent.draw_by_markdown(
        markdown_path=args.markdown_path,
        output_dir=args.output_dir,
        save_manifest=manifest_path,
    )
    if args.eval:
        evaluate_images(items, os.path.join(args.output_dir, "eval_results.json"))


async def run_pedia(args: argparse.Namespace) -> None:
    agent = DrawImageAgent()
    result = await agent.draw_by_pedia_content(
        article_id=args.article_id,
        output_dir=args.output_dir,
    )
    if args.eval:
        evaluate_images(
            result["images"],
            os.path.join(args.output_dir, f"{args.article_id}_eval_results.json"),
        )

async def run_markdown_file(markdown_path: str, output_dir: str) -> None:
    agent = DrawImageAgent()
    temp_path = os.path.join(output_dir, "images.json")
    await agent.draw_by_markdown(
        markdown_path=markdown_path,
        output_dir=output_dir,
        save_manifest=temp_path,
    )

def main():
    # 测试文本绘图接口
    # input_path = Path(r"F:\SciencePedia\draw_chem\workspace\output\draw_image_prompts.json")
    # output_dir = r"F:\SciencePedia\draw_chem\draw_image\output"
    # with input_path.open("r", encoding="utf-8") as f:
    #     data = json.load(f)
    
    # os.makedirs(output_dir, exist_ok=True)
    # for idx, item in enumerate(data):
    #     image_name = f"context_{idx}.png"
    #     context = (item.get("context") or "").strip()
    #     asyncio.run(run_text(context, output_dir, image_name))
        
    # 测试markdown绘图接口
    markdown_path = r"F:\SciencePedia\topic_book_generation\book_generate_pipeline\output\可控核聚变\temp\md\第1章_工程目标_指标体系与方案闭环边界.md"
    output_dir = r"F:\SciencePedia\topic_book_generation\book_generate_pipeline\output\可控核聚变\images\第1章_工程目标_指标体系与方案闭环边界"
    asyncio.run(run_markdown_file(markdown_path, output_dir))

if __name__ == "__main__":
    main()
