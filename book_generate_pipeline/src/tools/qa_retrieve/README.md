# qa_retrieve

A tool for searching QA pairs based on keywords. Uses LLM to expand keywords, search problems, filter results, and retrieve detailed problem information.

## Quick Start

```python
from MCPs.qa_retrieve import retrieve_and_check_qa

result = await retrieve_and_check_qa(
    keyword="Transformer",
    num_variations=5,
    max_results_per_keyword=2
)
```

## Environment Configuration

Create a `.env` file in the project root:

```env
LLM_MODEL=litellm_proxy/gemini-3-pro-preview
LITELLM_API_KEY=...
LITELLM_BASE_URL=...

OPENSEARCH_HOST=...
OPENSEARCH_USERNAME=admin
OPENSEARCH_PASSWORD=...
```

## Main Functions

- **`retrieve_and_check_qa()`**: End-to-end pipeline (keyword expansion + search + LLM filtering + detail retrieval)
- **`expand_keywords()`**: Generate keyword variations using LLM
- **`filter_problems_by_query()`**: Filter problems using LLM based on query relevance
- **`QARetriever`**: QA pair retriever using OpenSearch

## Output Format

```json
{
  "keyword": "original_keyword",
  "variations": ["variation1", "variation2", ...],
  "results": [
    {
      "problem_thumbnail": "...",
      "problem": "...",
      "ground_truth_answer": "...",
      "solutions": "..."
    }
  ],
  "total_found": 10,
  "selected_count": 8,
  "usage_stats": {
    "total_elapsed_time_seconds": 25.17,
    "llm_calls": 2,
    "total_tokens": 5313,
    "prompt_tokens": 3628,
    "completion_tokens": 1685,
    "timestamp": "2025-12-01 11:08:02"
  }
}
```

## Parameters

- `keyword` (str): Original keyword to search for
- `num_variations` (int, default 5): Number of keyword variations to generate
- `max_results_per_keyword` (int, default 2): Maximum results returned per keyword
