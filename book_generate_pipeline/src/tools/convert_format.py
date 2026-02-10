"""Format conversion utilities for MD -> HTML -> PDF pipeline."""

import os
import sys
import asyncio
from pathlib import Path

# Add tools/md2html to module search path
md2html_dir = Path(__file__).parent / 'md2html'
sys.path.insert(0, str(md2html_dir))

from src.tools.md2html_wrapper import save_md_as_html
from playwright.async_api import async_playwright, Error as PlaywrightError


async def md2html_single_file(md_file: str, html_file: str):
    """Async wrapper for sync save_md_as_html using thread pool to avoid blocking."""
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, save_md_as_html, md_file, html_file)


async def md_to_html(md_files_dir: str, html_output_dir: str):
    """Batch convert MD files to HTML (async concurrent)."""
    os.makedirs(html_output_dir, exist_ok=True)
    tasks = []
    for name in os.listdir(md_files_dir):
        if not name.endswith(".md"):
            continue
        md_path = os.path.join(md_files_dir, name)
        html_name = name[:-3] + ".html"
        html_path = os.path.join(html_output_dir, html_name)
        tasks.append(md2html_single_file(md_path, html_path))
    await asyncio.gather(*tasks)


def _file_path_to_url(html_path: str) -> str:
    """Build file:// URL for Playwright. Use forward slashes and file:/// (three slashes) for Windows."""
    abs_path = os.path.abspath(html_path)
    url_path = abs_path.replace("\\", "/")
    if not url_path.startswith("/") and len(url_path) >= 2 and url_path[1] == ":":
        url_path = "/" + url_path
    return "file://" + url_path


async def _html_to_pdf(page, html_path: str, pdf_path: str):
    """Internal function to convert HTML to PDF."""
    if not os.path.exists(html_path):
        raise FileNotFoundError(f"HTML file not found: {html_path}")

    url = _file_path_to_url(html_path)
    try:
        # 超时常见原因：1) file:// 下中文路径在部分环境加载慢/失败 2) 页面大、MathJax 等外链脚本加载慢
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)

        # Wait for MathJax rendering to complete
        await page.wait_for_function(
            """
            () => {
                if (typeof MathJax === 'undefined') return true; // Skip if no MathJax
                if (typeof MathJax.typesetPromise === 'function') {
                    // MathJax v3
                    return MathJax.typesetPromise &&
                           (window.MathJax?.Hub?.Queue?.length === 0 ||
                            !window.MathJax?.Hub);
                }
                // MathJax v2
                return window.MathJax?.Hub?.Queue?.length === 0;
            }
            """,
            timeout=60000
        )

        # Extra wait for rendering stability
        await page.wait_for_timeout(500)

        # Hide MathJax processing overlays/messages before PDF
        await page.evaluate(
            """
            () => {
                const ids = ['MathJax_Message'];
                ids.forEach(id => {
                    const el = document.getElementById(id);
                    if (el) el.style.display = 'none';
                });
                document.querySelectorAll('.MathJax_Message,.MathJax-Processing,.MathJax-Loading').forEach(el => {
                    el.style.display = 'none';
                });
            }
            """
        )

        await page.pdf(
            path=pdf_path,
            format="A4",
            print_background=True,
            margin={
                "top": "1cm",
                "bottom": "1cm",
                "left": "1cm",
                "right": "1cm"
            }
        )
    except PlaywrightError as e:
        raise RuntimeError(f"Playwright execution failed (HTML: {html_path}): {str(e)}")
    except Exception as e:
        raise RuntimeError(f"Unknown error during PDF generation (HTML: {html_path}): {str(e)}")


async def html2pdf_single_file(html_file: str, pdf_file: str):
    """Convert a single HTML file to PDF (independent browser instance)."""
    os.makedirs(os.path.dirname(pdf_file), exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        try:
            page = await browser.new_page()
            await _html_to_pdf(page, html_file, pdf_file)
        finally:
            await browser.close()


async def html_to_pdf(html_files_dir: str, pdf_output_dir: str):
    """Batch convert HTML files to PDF (reuse same browser and page for efficiency)."""
    os.makedirs(pdf_output_dir, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()

        files = [f for f in os.listdir(html_files_dir) if f.endswith(".html")]

        for html_file in files:
            html_path = os.path.join(html_files_dir, html_file)
            pdf_path = os.path.join(pdf_output_dir, html_file[:-5] + ".pdf")
            try:
                await _html_to_pdf(page, html_path, pdf_path)
                print(f"✅ {html_file} conversion complete")
            except Exception as e:
                print(f"❌ {html_file} conversion failed: {e}")

        await browser.close()


async def main():
    """Example usage for single file full pipeline."""
    md_file = r"F:\SciencePedia\topic_book_generation\book_generate_pipeline\output\books\可控核聚变\md\第11章_聚变堆工程约束与系统一致性收敛.md"
    html_file = r"F:\SciencePedia\topic_book_generation\book_generate_pipeline\output\books\可控核聚变\md\第11章_聚变堆工程约束与系统一致性收敛.html"
    pdf_file = r"F:\SciencePedia\topic_book_generation\book_generate_pipeline\output\books\可控核聚变\pdf\第11章_聚变堆工程约束与系统一致性收敛.pdf"

    os.makedirs(os.path.dirname(html_file), exist_ok=True)
    os.makedirs(os.path.dirname(pdf_file), exist_ok=True)

    await md2html_single_file(md_file, html_file)
    await html2pdf_single_file(html_file, pdf_file)

if __name__ == "__main__":
    asyncio.run(main())