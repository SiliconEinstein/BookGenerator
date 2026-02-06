import json
from typing import List, Dict


def evaluate_images(items: List[Dict[str, object]], output_path: str) -> None:
    """简单评估占位：将结果写入 JSON，避免 CLI 失败。"""
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=4, ensure_ascii=False)
