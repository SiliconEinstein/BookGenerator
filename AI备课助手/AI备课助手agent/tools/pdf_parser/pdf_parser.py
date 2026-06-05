"""PDF 解析：支持 file / url / snip 三种模式，输出 markdown/latex/html/plain/markup"""

import argparse
import base64
import importlib
import io
import json
import os
import re
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import requests

DEFAULT_HOST = os.getenv("PDF_HOST", "http://101.126.82.63:40001")
TIMEOUT = 60
DEFAULT_OUTPUT_SUBDIR = "outputs_result"

# 语义解析配置
# textual: Disable=0 / OCRFast=1 / OCRHighQuality=2 / DigitalExported=3
# 其他:    sable=0 / OCRFast=1
SEMANTIC_CFG: Dict = {
    "textual": 3,
    "chart": 1,
    "table": True,
    "molecule": True,
    "equation": True,
    "figure": False,
    "expression": True,
}

FORMAT_META = {
    "latex":    ("tex",   "\\documentclass{article}\n\n\\usepackage{booktabs}\n\n\\begin{document}\n", "\\end{document}"),
    "html":     ("html",  "<html>\n<body>\n", "</body>\n</html>"),
    "markdown": ("md",    "", ""),
    "plain":    ("plain", "", ""),
    "markup":   ("txt",   "", ""),
}


def make_token(source: str) -> str:
    """从文件路径或 URL 生成合法 token（满足正则 ^[-._?=&a-zA-Z0-9]{1,128}$）"""
    raw = os.path.basename(source.rstrip("/"))
    safe = re.sub(r"[^-\._?=&a-zA-Z0-9]", "", raw)[:128]
    return safe or re.sub(r"[^-\._?=&a-zA-Z0-9]", "", str(abs(hash(raw))))[:128] or "default"


def trigger_parse(mode: str, source: str, host: str = DEFAULT_HOST) -> str:
    endpoints = {
        "file": f"{host}/trigger-file-async",
        "url":  f"{host}/trigger-url-async",
        "snip": f"{host}/trigger-snip-async",
    }
    # sync，True，同步请求，不直接返回，等待解析完成后返回
    payload = {"token": make_token(source), "sync": True, **SEMANTIC_CFG}
    if mode == "file":
        with open(source, "rb") as f:
            resp = requests.post(endpoints[mode], data=payload, files={"file": f}, timeout=TIMEOUT)
    elif mode == "url":
        resp = requests.post(endpoints[mode], json={"url": source, **payload}, timeout=TIMEOUT)
    else:  # snip
        try:
            image_module = importlib.import_module("PIL.Image")
            Image = image_module.Image
            img = Image.open(source).convert("RGB")
            buf = io.BytesIO()
            img.save(buf, format="JPEG")
            img_b64 = base64.b64encode(buf.getvalue()).decode()
        except ModuleNotFoundError:
            with open(source, "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode()
        resp = requests.post(endpoints[mode], data={"img": img_b64, **payload}, timeout=TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    if data.get("status") in {"error", "failed", "rejected"}:
        raise RuntimeError(f"server rejected: {data}")
    return data.get("token", payload["token"])

# 轮询结果，直到完成或超时
def poll_result(token: str, host: str = DEFAULT_HOST, attempts: int = 18) -> Dict:
    url = f"{host}/get-result"
    payload = {"token": token, "return_half": False, "content": False,
               "objects": False, "pages_dict": True, "molecule_source": False}
    wait = {"undefined", "processing", "pending", "queued", None}
    for _ in range(attempts):
        resp = requests.post(url, json=payload, timeout=TIMEOUT)
        resp.raise_for_status()
        result = resp.json()
        if result.get("status") not in wait:
            return result
        time.sleep(2)
    raise RuntimeError(f"poll timeout after {attempts} attempts")


def resolve_output_dir(output_dir: Optional[str]) -> Path:
    if output_dir:
        return Path(output_dir).expanduser().resolve()
    work_dir = os.getenv("OPENCLAW_WORKDIR") or os.getenv("WORK_DIR") or os.getcwd()
    return Path(work_dir).expanduser().resolve() / DEFAULT_OUTPUT_SUBDIR


def save_result_json(result: Dict, token: str, output_dir: Path) -> str:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{token}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return str(path)


def fetch_formatted(token: str, formats: Iterable[str], host: str = DEFAULT_HOST,
                    output_dir: Optional[Path] = None) -> List[str]:
    result_url = f"{host}/get-formatted"
    out_dir = output_dir or resolve_output_dir(None)
    out_dir.mkdir(parents=True, exist_ok=True)
    saved = []
    for fmt in formats:
        if fmt not in FORMAT_META:
            continue
        suffix, head, tail = FORMAT_META[fmt]
        data = {"token": token,
                **{k: fmt for k in ("textual", "chart", "table", "molecule", "equation", "expression")}}
        resp = requests.post(result_url, json=data, timeout=TIMEOUT)
        resp.raise_for_status()
        content = resp.json().get("content", "")
        path = out_dir / f"{token}-parser.{suffix}"
        with open(path, "w", encoding="utf-8") as f:
            if head:
                f.write(head + "\n")
            f.write(content)
            if tail:
                f.write("\n" + tail + "\n")
        saved.append(str(path))
    return saved


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="PDF parser: file/url/snip -> markdown/latex/html/plain/markup")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--file", default=os.getenv("PDF_FILE"))
    g.add_argument("--url",  default=os.getenv("PDF_URL"))
    g.add_argument("--snip", default=os.getenv("PDF_SNIP"))
    p.add_argument("--formats",    default=os.getenv("FORMATS", "markdown"))
    p.add_argument("--host",       default=os.getenv("PDF_HOST", DEFAULT_HOST))
    p.add_argument("--output-dir", default=None)
    p.add_argument("--no-poll", action="store_true", help="Only trigger parsing, do not poll for result")
    p.add_argument("--poll-attempts", type=int, default=18, help="Max polling attempts, 2s interval")
    args = p.parse_args()

    mode    = "file" if args.file else ("url" if args.url else "snip")
    source  = args.file or args.url or args.snip
    fmts    = [f.strip() for f in args.formats.split(",") if f.strip()]
    out_dir = resolve_output_dir(args.output_dir)

    token = trigger_parse(mode, source, args.host)
    if args.no_poll:
        print(json.dumps({"token": token, "status": "submitted", "output_dir": str(out_dir)}, ensure_ascii=False))
    else:
        result = poll_result(token, args.host, max(1, args.poll_attempts))
        json_path = save_result_json(result, token, out_dir)
        saved = fetch_formatted(token, fmts, args.host, out_dir)
        print(json.dumps({"token": token, "result_json": json_path, "formatted_files": saved}, ensure_ascii=False))
