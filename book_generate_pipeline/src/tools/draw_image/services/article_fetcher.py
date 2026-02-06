from pathlib import Path
def fetch_article_content(article_id: int) -> str:
    base_dir = Path(__file__).resolve().parent
    candidates = [
        base_dir / "articles" / f"{article_id}.md",
        base_dir.parent / "data" / f"{article_id}.md",
        base_dir.parent / "data" / "MainContent.md",
    ]
    for path in candidates:
        if path.exists():
            return path.read_text(encoding="utf-8")
    raise FileNotFoundError(
        f"未找到文章 {article_id} 的本地文件，请将其放到 {base_dir / 'articles'}"
    )
