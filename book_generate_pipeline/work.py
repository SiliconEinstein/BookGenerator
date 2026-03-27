import re
import sys
import os
import asyncio
from src.tools.convert_format import md_to_html, html_to_pdf, md2html_single_file, html2pdf_single_file

async def main():
    # 单文件全流程示例
    md_file = r"F:\SciencePedia\topic_book_generation\book_generate_pipeline\output\books\离散数学\md_with_images\第2章_命题逻辑.md"
    html_file = r"F:\SciencePedia\topic_book_generation\book_generate_pipeline\output\books\离散数学\html\第2章_命题逻辑.html"
    pdf_file = r"F:\SciencePedia\topic_book_generation\book_generate_pipeline\output\books\离散数学\pdf\第2章_命题逻辑.pdf"

    # 多文件处理
    md_dir = r"F:\SciencePedia\topic_book_generation\book_generate_pipeline\output\books\可控核聚变\md"
    html_dir = r"F:\SciencePedia\topic_book_generation\book_generate_pipeline\output\books\可控核聚变\html"
    pdf_dir = r"F:\SciencePedia\topic_book_generation\book_generate_pipeline\output\books\可控核聚变\pdf"
    
    # 确保输出目录存在
    os.makedirs(os.path.dirname(html_file), exist_ok=True)
    os.makedirs(os.path.dirname(pdf_file), exist_ok=True)

    # 执行转换流程
    await md2html_single_file(md_file, html_file)
    await html2pdf_single_file(html_file, pdf_file)
    # await md_to_html(md_dir, html_dir)
    # await html_to_pdf(html_dir, pdf_dir)


if __name__ == "__main__":
    asyncio.run(main())