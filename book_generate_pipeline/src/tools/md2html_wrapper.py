# tools/md2html_wrapper.py
import sys
from pathlib import Path

# 获取当前文件所在目录（即 tools/）
TOOLS_DIR = Path(__file__).resolve().parent

# 定位 md2html 子目录
MD2HTML_DIR = TOOLS_DIR / "md2html"

# 将 md2html 目录加入 sys.path，以便导入其内部模块（pre_code_patch 等）
if str(MD2HTML_DIR) not in sys.path:
    sys.path.insert(0, str(MD2HTML_DIR))

# 导入原始转换函数（注意：此时 md2html 已在 path 中，可直接 import）
from md2html import convert_md_to_html

# ✅ 正确构建 CSS 路径：指向 tools/md2html/.prism/style.css
PRISM_CSS_PATH = MD2HTML_DIR / ".prism" / "style.css"

# 可选：检查文件是否存在（调试用）
# assert PRISM_CSS_PATH.exists(), f"CSS file missing: {PRISM_CSS_PATH}"

# 默认参数配置（与 CLI 一致）
DEFAULT_ARGS = {
    "css_file_path": str(PRISM_CSS_PATH),
    "prism_theme": "prism",
    "line_numbers": False,
    "collapse_lines": 50,
    "inline_lang": "python",
    "foldable_sections": ["Solution"],
    "boxed_math": True,
    "choice_options": True,
    "mermaid": True,
}

def convert_md_file(md_file_path, output_file=None, **overrides):
    md_file_path = Path(md_file_path)
    if not md_file_path.exists():
        raise FileNotFoundError(f"Markdown file not found: {md_file_path}")

    config = DEFAULT_ARGS.copy()
    config.update(overrides)

    if config["collapse_lines"] == 0:
        config["collapse_lines"] = None
    if config["inline_lang"] == "none":
        config["inline_lang"] = None

    full_html = convert_md_to_html(
        str(md_file_path),
        css_file_path=config["css_file_path"],
        prism_theme=config["prism_theme"],
        line_numbers=config["line_numbers"],
        collapse_lines=config["collapse_lines"],
        inline_lang=config["inline_lang"],
        foldable_sections=config["foldable_sections"],
        boxed_math=config["boxed_math"],
        choice_options=config["choice_options"],
        mermaid=config["mermaid"]
    )

    output_path = Path(output_file) if output_file else md_file_path.with_suffix(".html")
    return full_html, str(output_path)


def save_md_as_html(md_file_path, output_file=None, **overrides):
    full_html, out_path = convert_md_file(md_file_path, output_file, **overrides)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(full_html)
    return out_path