#!/usr/bin/env python3
"""
Unified Code Fence Detection Utilities

This module provides a single, robust implementation of code fence validation
that is used consistently across all components of the md2html system.

The validation logic handles complex edge cases including:
- Inline code containing triple backticks
- Trailing spaces and invalid content
- Proper language identifier validation
- Context-aware detection

Author: md2html system
Version: 1.0
"""

import re
from typing import Optional


def is_valid_code_fence(line: str, in_code_block: bool = False) -> bool:
    """
    Check if a line contains a valid markdown code fence.
    
    This is the unified, robust fence validation function used across all
    md2html components. It implements comprehensive validation criteria
    to distinguish genuine code block fences from inline code examples,
    documentation, and malformed content.
    
    Args:
        line (str): The line to check for a valid code fence
        in_code_block (bool): Whether we're currently inside a code block.
                             This affects language validation for closing fences.
    
    Returns:
        bool: True if the line contains a valid code fence, False otherwise
        
    Validation Criteria:
        1. Must start with exactly ``` (three backticks) after stripping whitespace
        2. The ``` must be at the very beginning of the stripped content
        3. Must not be inside inline code that started earlier in the line
        4. Must contain only the fence and optional language specifier
        5. Language specifiers must follow proper naming conventions
        6. Must not have trailing spaces or extra content
    
    Examples:
        Valid fences:
        - ```
        - ```python
        - ```javascript
        - ```shell-script
        - ```c++
        -     ``` (indented)
        
        Invalid fences:
        - To prevent ````` ``` ````` from corrupting (inline code)
        - ``` extra text after
        - ```python print("hello") (code on same line)
        - ```123invalid (language starts with number)
        - ```-invalid (language starts with hyphen)
        - Text before ``` fence
        
    Note: Trailing spaces are automatically stripped and do not invalidate fences.
    This makes the function more user-friendly for real-world usage where
    trailing spaces are commonly introduced accidentally.
    """
    # Allow trailing spaces but strip them for validation
    # This makes the function more user-friendly for real-world usage
    stripped = line.strip()
    
    # 1. Must start with exactly three backticks
    if not stripped.startswith('```'):
        return False
    
    # 2. The ``` must be at the very beginning of the stripped content
    # This ensures we're not detecting ``` that appears later in the line
    if stripped.find('```') != 0:
        return False
    
    # 3. Check if there are any backticks before the start of the stripped content
    # This handles cases where the ``` appears to start the stripped line but
    # is actually inside inline code that started earlier in the line
    leading_whitespace_end = len(line) - len(line.lstrip())
    text_before_stripped = line[:leading_whitespace_end]
    
    if '`' in text_before_stripped:
        backticks_before = text_before_stripped.count('`')
        if backticks_before % 2 == 1:
            return False  # Inside inline code
    
    # 4. Extract content after ``` for validation
    after_fence = stripped[3:]
    
    # 5. Validate fence content
    if after_fence == '':
        # Plain fence: ``` - always valid
        return True
    elif not in_code_block:
        # Language fence: ```language - only valid when opening a block
        # Language must:
        # - Start with a letter (not number or hyphen)
        # - Contain only letters, numbers, hyphens, underscores, and plus signs
        # - Be a single word (no spaces)
        
        # Check if it's a single word (no spaces in the content after ```)
        if ' ' in after_fence:
            return False
        
        # Validate language identifier format
        if re.match(r'^[a-zA-Z][a-zA-Z0-9_+-]*$', after_fence):
            return True
        else:
            return False
    else:
        # When in_code_block=True, only plain fences (```) are valid for closing
        # Any content after ``` when closing a block is invalid
        return False


def get_fence_info(line: str) -> Optional[dict]:
    """
    Extract information about a code fence if the line contains one.
    
    Args:
        line (str): The line to analyze
        
    Returns:
        dict or None: Fence information dictionary with keys:
            - 'type': 'plain' or 'language'  
            - 'language': language name (None for plain fences)
            - 'content': the full fence content (e.g., '```python')
            - 'is_valid': whether this is a valid fence
        Returns None if the line doesn't contain a fence.
        
    Example:
        >>> get_fence_info('```python')
        {
            'type': 'language',
            'language': 'python', 
            'content': '```python',
            'is_valid': True
        }
    """
    stripped = line.strip()
    
    if not stripped.startswith('```'):
        return None
    
    is_valid = is_valid_code_fence(line, in_code_block=False)
    after_fence = stripped[3:]  # Don't rstrip here, we need original content
    
    if after_fence.rstrip() == '':
        fence_type = 'plain'
        language = None
    else:
        fence_type = 'language'
        language = after_fence.rstrip() if is_valid else None
    
    return {
        'type': fence_type,
        'language': language,
        'content': stripped,
        'is_valid': is_valid
    }


def validate_fence_pair(opening_line: str, closing_line: str) -> bool:
    """
    Validate that two lines form a proper code fence pair.
    
    Args:
        opening_line (str): The opening fence line
        closing_line (str): The closing fence line
        
    Returns:
        bool: True if they form a valid pair
        
    Rules:
        - Opening fence can be plain (```) or language (```python)
        - Closing fence must be plain (```)
        - Both must be individually valid fences
    """
    # Check opening fence validity
    opening_valid = is_valid_code_fence(opening_line, in_code_block=False)
    if not opening_valid:
        return False
    
    # Check closing fence validity (must be plain fence when in code block)
    closing_valid = is_valid_code_fence(closing_line, in_code_block=True)
    if not closing_valid:
        return False
    
    # Additional check: closing must be a plain fence
    closing_info = get_fence_info(closing_line)
    if not closing_info or closing_info['type'] != 'plain':
        return False
    
    return True


def is_fence_inside_inline_code(line: str, fence_position: int) -> bool:
    """
    Check if a fence at a specific position is inside inline code.
    
    Args:
        line (str): The line containing the fence
        fence_position (int): The position where ``` starts
        
    Returns:
        bool: True if the fence is inside inline code spans
    """
    # Count backticks before the fence position
    before_fence = line[:fence_position]
    backtick_count = before_fence.count('`')
    
    # If odd number of backticks before, we're inside inline code
    return backtick_count % 2 == 1


def find_all_potential_fences(text: str) -> list:
    """
    Find all potential fence positions in text for analysis.
    
    Args:
        text (str): The text to search
        
    Returns:
        list: List of dictionaries with fence information:
            - 'line_number': 1-based line number
            - 'line_content': the full line content
            - 'fence_info': result from get_fence_info()
    """
    lines = text.split('\n')
    potential_fences = []
    
    for line_num, line in enumerate(lines, 1):
        fence_info = get_fence_info(line)
        if fence_info:
            potential_fences.append({
                'line_number': line_num,
                'line_content': line,
                'fence_info': fence_info
            })
    
    return potential_fences


# Legacy compatibility aliases for existing code
# These will be removed after refactoring is complete
def is_valid_code_fence_line(line: str) -> bool:
    """Legacy alias for backward compatibility. Use is_valid_code_fence() instead."""
    return is_valid_code_fence(line, in_code_block=False)


if __name__ == "__main__":
    # Quick test when run directly
    test_cases = [
        ("```", True, "Plain fence"),
        ("```python", True, "Language fence"),
        ("    ```", True, "Indented fence"),
        ("``` ", True, "Trailing space"),
        ("```123", False, "Language starts with number"),
        ("```-invalid", False, "Language starts with hyphen"),
        ("``` extra text", False, "Extra text"),
        ("To prevent ````` ``` `````", False, "Inline code"),
    ]
    
    print("Quick fence validation test:")
    print("-" * 40)
    
    all_passed = True
    for line, expected, description in test_cases:
        result = is_valid_code_fence(line)
        status = "✓" if result == expected else "✗"
        print(f"{status} {description}: {result} (expected {expected})")
        if result != expected:
            all_passed = False
    
    print(f"\nOverall: {'✓ All tests passed' if all_passed else '✗ Some tests failed'}")