from typing import List
from pydantic import BaseModel, Field


# Keyword expansion output format
class KeywordVariations(BaseModel):
    variations: List[str] = Field(
        ..., 
        description="List of keyword variations generated from the given keyword, including synonyms, related terms, and different expressions"
    )


# Problem filtering output format
class ProblemFilterResult(BaseModel):
    selected_ids: List[str] = Field(
        ...,
        description="List of problem IDs that match the query"
    )


# Keyword expansion system prompt
KEYWORD_VARIATIONS_PROMPT = """
You are an expert assistant specializing in search query formulation and linguistics.
Your main function is to take a user provided topic or query as input, and generate a list of keywords to be used in document search.

## Task
- Generate a list of keywords to be used in document search. Always use English for the generated keywords regardless of the input language.
- These keywords should be diverse and comprehensive, and covering different aspects of the topic. 
- You should also include keywords with semantically equivalent rephrasings capturing variations in natural language where concepts might be slightly reordered or separated by a few words.
You could include variations involve:
    * Reordering of key terms.
    * Using relevant technical or common synonyms.
    * Switching between singular and plural forms.

## EXAMPLE
{
    "query": "superconducting quantum qubits",
}

{
    "variations": [
        "Josephson junctions",
        "superconducting quantum computing",
        "superconducting quantum qubits",
        "quantum computing",
        "quantum information",
        "quantum qubits superconducting",
        "quantum qubits superconductors",
        "superconducting qubits",
        "superconductor quantum bits",
        "qubits based on superconductors",
        "quantum computing with superconducting circuits",
        "Josephson junction qubits",
        "superconducting quantum information processors",
        "solid-state quantum computing",
        "quantum circuits with superconducting materials",
        "microwave-controlled quantum bits",
        "artificial atoms superconducting",
    ]
}
"""


# Problem filtering prompt
PROBLEM_FILTER_PROMPT = """
You are an expert at matching problems to queries. Your task is to select problems that are relevant to the given query.

# Task
Given a query and a list of problems (with IDs and problem text), select the problem IDs that are most relevant to the query.

# Selection Criteria
- The problem should be directly related to the query topic
- The problem should be semantically similar to the query
- Select problems that would help answer or understand the query
- Be selective - only choose highly relevant problems

# Output Format
Output in JSON format with the following field:
- selected_ids: List of problem IDs that match the query
"""

