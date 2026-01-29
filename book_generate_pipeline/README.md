# Topic Book Generator

A Python-based tool for generating educational books on STEM topics using AI and LLM models.

## Project Structure

```
book_generate_pipeline/
├── src/                      # Source code
│   ├── core/                 # Core business logic
│   │   ├── chapter_generator.py
│   │   ├── book_generator.py
│   │   └── topic_book_generator.py
│   ├── models/               # LLM provider interfaces
│   │   ├── base.py
│   │   └── llm_providers.py
│   ├── tools/                # Utility tools
│   │   ├── convert_format.py
│   │   ├── database.py
│   │   ├── md2html_wrapper.py
│   │   └── md2html/          # Markdown to HTML converter
│   └── utils/                # Utility functions
│       ├── config.py
│       └── file_helpers.py
├── prompts/                  # Prompt templates for Chinese (language='ch')
├── prompts_en/               # Prompt templates for English (language='en')
├── config/                   # Configuration files
├── tests/                    # Test files
├── docs/                     # Documentation
├── scripts/                  # Utility scripts
├── output/                   # Generated output
│   ├── books/                # Generated books
│   └── temp/                 # Temporary files
├── main.py                  # Main entry point
├── requirements.txt         # Python dependencies
└── pyproject.toml           # Project configuration
```

### Prompt Directory Selection

The system automatically selects the appropriate prompt directory based on the `language` parameter:

- `language="ch"` or `language="cn"` → Uses `prompts/` (Chinese prompts)
- `language="en"` → Uses `prompts_en/` (English prompts)

This behavior is configured in `config/config.dev.yaml`:

```yaml
prompts:
  base_dir_ch: "prompts"      # Chinese prompts
  base_dir_en: "prompts_en"    # English prompts
```

## Installation

1. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Install Playwright browsers:
```bash
playwright install chromium
```

## Configuration

Set up environment variables in `.env`:

```bash
LITELLM_API_KEY=your_litellm_api_key
GPUGEEK_API_KEY=your_gpugeek_api_key
```

Or modify `config/config.dev.yaml` directly.

## Usage

### Basic Usage

Run the main script:
```bash
python main.py
```

### Command Line Interface

```bash
python scripts/generate_book.py --course-name "可控核聚变" --language ch
```

### Using as a Module

```python
import asyncio
from src.core.topic_book_generator import TopicBookGenerator

async def main():
    agent = TopicBookGenerator(language="ch")
    book_info = ["本科", "可控核聚变", "50", "860559", "1545472"] # 860559 and 1545472 are the related course IDs in SciencePedia

    # 中文: output, 英文: output_en
    await agent.generate_chapter(book_info, "output/chapter/可控核聚变.md", "./docs_input")
    await agent.generate_book("output/chapter/可控核聚变.md", "output/books/可控核聚变")

asyncio.run(main())
```

## Pipeline Stages

1. **Phase 1: Generate Chapter Outline**
   - Creates a structured syllabus with chapters and subchapters
   - Uses battle mechanism between two models to refine the outline

2. **Phase 2: Generate Abstracts**
   - Creates abstracts for each subchapter
   - Caches results for reuse

3. **Phase 3: Generate Subchapter Content**
   - Generates detailed content for each subchapter
   - Uses MCP tools for content generation

4. **Phase 4: Insert Projects and Refine**
   - Integrates projects into chapters
   - Refines content for consistency

5. **Phase 5: Format Conversion**
   - Converts Markdown to HTML
   - Converts HTML to PDF

## Supported Models

- Gemini 3 Pro
- GPT 5.2
- DeepSeek V3
- Qwen VL
- Doubao

## License

MIT License
