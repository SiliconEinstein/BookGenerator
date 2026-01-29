# Tools 工具模块说明

本目录包含书籍生成流水线中使用的各类工具函数和模块。

## 目录结构

```
tools/
├── __init__.py              # 模块初始化，导出所有公共接口
├── convert_format.py        # 格式转换工具（MD→HTML→PDF）
├── database.py              # 数据库操作工具
├── get_qa_pair.py           # 问答对检索工具
├── get_wiki_article.py      # Wiki 文章搜索工具
├── md2html_wrapper.py       # Markdown 转 HTML 封装
├── md2html/                 # Markdown 转 HTML 核心模块
│   ├── md2html.py           # 核心转换逻辑
│   ├── parse_blocks.py      # Markdown 块解析
│   ├── fence_utils.py       # 代码块处理工具
│   ├── pre_code_patch.py    # 代码块预处理
│   └── .prism/              # Prism 代码高亮样式
└── qa_retrieve/             # 问答对检索模块
    ├── pipeline.py          # 检索流水线
    ├── retriever.py         # 检索器
    ├── opensearch.py        # OpenSearch 客户端
    ├── prompt.py            # 提示词模板
    └── utils.py             # 工具函数
```

## 工具说明

### convert_format.py
格式转换工具，支持 Markdown → HTML → PDF 的完整流水线。

**主要功能：**
- `md2html_single_file(md_file, html_file)` - 单个 MD 文件转 HTML
- `md_to_html(md_files_dir, html_output_dir)` - 批量 MD 转 HTML（异步并发）
- `html2pdf_single_file(html_file, pdf_file)` - 单个 HTML 文件转 PDF
- `html_to_pdf(html_files_dir, pdf_output_dir)` - 批量 HTML 转 PDF（复用浏览器实例）
- `_html_to_pdf(page, html_path, pdf_path)` - HTML 转 PDF 内部函数

**特性：**
- 使用 Playwright 进行 HTML → PDF 转换
- 支持 MathJax 数学公式渲染
- 异步并发处理提高效率
- 可自定义 PDF 格式（A4）和边距

### database.py
数据库操作管理器，用于从 MySQL 数据库获取 Wiki 相关内容。

**主要功能：**
- `init_get_article_content()` - 获取文章内容
- `init_get_field_index_content()` - 获取领域索引结构
- `init_get_overall_index_content()` - 获取整体索引
- `init_get_page_content()` - 根据页面类型获取内容

**数据表：**
- `articles` - 文章表
- `wiki_index` - Wiki 索引表
- `revisions` - 版本表

### get_qa_pair.py
问答对检索工具，为章节大纲检索相关的问答题目。

**主要功能：**
- `extract_keywords_from_outline()` - 从大纲中提取关键词
- `search_qa_pairs_for_subchapter()` - 为子章节搜索问答对
- `get_qa_pair_for_subchapter()` - 获取子章节问答对
- `search_qa_pairs_by_outline()` - 批量为章节结构搜索问答对

**特性：**
- 支持在线关键词提取（使用 LLM）
- 支持关键词变体生成
- 去重和结果汇总

### get_wiki_article.py
Wiki 文章搜索工具，根据子章节标题和主题检索相关 Wiki 文章。

**主要功能：**
- `search_wiki_articles_for_subchapter()` - 搜索子章节相关 Wiki 文章

**特性：**
- 基于关键词的混合搜索
- 支持中英文搜索
- 自动去重
- 限制返回数量（最多 5 篇）

### md2html_wrapper.py
Markdown 转 HTML 的封装模块，提供简化的调用接口。

**主要功能：**
- `convert_md_file(md_file_path, output_file, **overrides)` - 转换 MD 文件为 HTML
- `save_md_as_html(md_file_path, output_file, **overrides)` - 转换并保存 HTML

**默认配置：**
- `prism_theme`: "prism" - Prism 代码高亮主题
- `line_numbers`: False - 不显示行号
- `collapse_lines`: 50 - 超过 50 行的代码块折叠
- `inline_lang`: "python" - 内联代码语言
- `foldable_sections`: ["Solution"] - 可折叠区块
- `boxed_math`: True - 数学公式使用方框
- `choice_options`: True - 选项格式化
- `mermaid`: True - 支持 Mermaid 图表

### md2html/ 子模块
Markdown 转 HTML 的核心实现，包含以下模块：

- **md2html.py** - 核心转换逻辑，处理各类 Markdown 语法
- **parse_blocks.py** - 解析 Markdown 块结构
- **fence_utils.py** - 代码块处理工具
- **pre_code_patch.py** - 代码块预处理和增强
- **.prism/** - Prism 代码高亮样式文件

### qa_retrieve/ 子模块
问答对检索模块，从 OpenSearch 中检索相关问答对。

**主要模块：**
- **pipeline.py** - 检索流水线核心
  - `retrieve_and_check_qa()` - 检索并检查问答对
  - `expand_keywords()` - 关键词扩展
  - `filter_problems_by_query()` - 按查询过滤题目
- **retriever.py** - OpenSearch 检索器实现
- **opensearch.py** - OpenSearch 客户端封装
- **prompt.py** - LLM 提示词模板
- **utils.py** - 工具函数

## 使用示例

### 格式转换
```python
from src.tools import md2html_single_file, html2pdf_single_file
import asyncio

async def convert():
    await md2html_single_file("input.md", "output.html")
    await html2pdf_single_file("output.html", "output.pdf")

asyncio.run(convert())
```

### 检索 Wiki 文章
```python
from src.tools import search_wiki_articles_for_subchapter

articles, titles = await search_wiki_articles_for_subchapter(
    subchapter_title="傅里叶变换",
    topics=["频域分析", "信号处理"],
    k=5
)
```

### 检索问答对
```python
from src.tools import search_qa_pairs_for_subchapter

result = await search_qa_pairs_for_subchapter(
    subchapter_title="傅里叶变换",
    topics=["频域分析", "信号处理"],
    max_keywords=10,
    max_results_per_keyword=1
)
```

### 数据库操作
```python
from src.tools import DatabaseManager

db = DatabaseManager(llm_config)
page_info = {
    "page_type": "article",
    "page_id": 12345
}
content = await db.init_get_page_content()(page_info)
```

## 依赖项

- **Playwright** - HTML 转 PDF
- **aiohttp** - 异步 HTTP 请求
- **mysql-connector-python** - MySQL 数据库连接
- **OpenSearch-py** - OpenSearch 客户端
- **Prism** - 代码高亮
- **MathJax** - 数学公式渲染（HTML 中引用）
