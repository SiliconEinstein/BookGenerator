#!/usr/bin/env python
"""
#===================================================================================
  Pre-Code Block Patch Tool
  -------------------------
  
  Comprehensive markdown pre-code block fence repair tool that fixes both dangling 
  language fences (```python, ```javascript, etc.) and dangling plain fences (```).
  
  Features:
  - Detects dangling language fences and adds appropriate closing fences
  - Groups plain fences and applies 2n+1 optimization algorithm that minimizes header 
    tags #, ##, etc trapped in code blocks  
  - Adds warning messages for auto-completed blocks
  
  Usage:
    python process_pre_code_blocks.py input.md
    python process_pre_code_blocks.py input.md -o output.md
      
    Version:  1.0
    Created:  2025-09-01 19:43
     Author:  Zhiyuan Yao, zhiyuan.yao@icloud.com
  Institute:  Lanzhou Center for Theoretical Physics, Lanzhou University
#===================================================================================
"""
import re
import sys
import os
import argparse
from typing import List, Set, Tuple
from fence_utils import is_valid_code_fence

# Old function removed - now using unified fence_utils.is_valid_code_fence()

def lang_pre_code_patch(content: str) -> str:
    """
    Step-by-step patch process:
    1. Identify all ```xxx ``` code blocks (properly paired language-plain blocks)
    2. Identify ```xxx preceding ```xxx ``` paired blocks (dangling language fences)
    3. Add ``` & warning after dangling ```xxx at 1st empty line or before next ```xxx
    """
    
    lines = content.split('\n')
    
    # Step 1: Find all fences (excluding those inside inline code or existing code blocks)
    fences = []
    in_code_block = False
    for i, line in enumerate(lines):
        # Check if this line is a valid fence, considering current code block state
        if is_valid_code_fence(line, in_code_block):
            # Update code block state after processing this fence
            if not in_code_block:
                # Entering a code block
                in_code_block = True
            else:
                # Exiting a code block
                in_code_block = False
            stripped = line.strip()
            content_after = stripped[3:].strip()
            if content_after == '':
                fence_type = 'plain'
                language = None
            else:
                fence_type = 'language'
                language = content_after.split()[0]
            
            fences.append({
                'line': i + 1,  # 1-based line numbers
                'type': fence_type,
                'content': stripped,
                'language': language,
                'original_index': i  # Keep 0-based for line modification
            })
    
    for i, fence in enumerate(fences):
        lang_info = f" (lang: {fence['language']})" if fence['language'] else ""
    
    # Step 2: Identify properly paired ```xxx ... ``` blocks
    valid_language_pairs = []
    dangling_language_fences = set()
    
    for i, fence in enumerate(fences):
        if fence['type'] == 'language':
            # Look for closing plain fence
            for j in range(i + 1, len(fences)):
                next_fence = fences[j]
                if next_fence['type'] == 'plain':
                    # Found valid ```xxx ... ``` pair
                    valid_language_pairs.append((fence, next_fence))
                    break
                elif next_fence['type'] == 'language':
                    # Hit another language fence - current one is dangling
                    dangling_language_fences.add(i)
                    break
            else:
                # Reached end without closing - dangling
                dangling_language_fences.add(i)
                # print(f"  DANGLING: ```{fence['language']} at line {fence['line']} (EOF)")
    
    # Step 3: Create patched content by adding closing ``` and warnings
    patched_lines = lines[:]
    
    # Process dangling language fences in forward order and track cumulative insertions
    insertions = []  # Track all insertions to apply them in reverse order
    
    for fence_idx in sorted(dangling_language_fences):
        fence = fences[fence_idx]
        insert_after_line = fence['original_index']
        
        # Processing dangling by first find where to insert closing ``` 
        # 1. Look for first empty line after dangling ```xxx
        # 2. If no empty line, add just before next ```xxx
        insert_line = None
        
        # Check for FIRST empty line after the dangling ```xxx
        for check_line in range(insert_after_line + 1, len(patched_lines)):
            line_content = patched_lines[check_line].strip()
            
            # Check if this is an empty line
            if line_content == "":
                insert_line = check_line
                break
                
            # If we hit another valid fence before finding empty line, insert before it
            # Note: At this point we're outside any code block (looking for insertion point)
            if is_valid_code_fence(lines[check_line], in_code_block=False):
                insert_line = check_line
                break
        
        if insert_line is None:
            # No blank line and no next fence - insert at end
            insert_line = len(patched_lines)
        
        # Store insertion info to apply later in reverse order
        closing_fence = "```"
        warning = f"> [!WARNING] Incomplete Code Block\n> {fence['language']} code block automatically closed here"
        
        insertions.append({
            'line': insert_line,
            'content': [closing_fence, warning],
            'fence_language': fence['language']
        })
        
    # Step 4: Apply insertions in reverse order to maintain correct line numbers
    for insertion in reversed(insertions):
        insert_line = insertion['line']
        content = insertion['content']
        for i, line_content in enumerate(content):
            patched_lines.insert(insert_line + i, line_content)
    return '\n'.join(patched_lines)


def optimize_plain_pre_code(patched_content: str) -> Tuple[List, Set[int]]:
    """
    Implement 2n+1 plain plain pre code fence ``` ``` optimization algorithm.
    
    Algorithm:
    1. Find all plain ``` fences in patched content
    2. If 2n+1 plain fences (odd number):
       - Try removing each of the 2n+1 plain fences as dangling
       - For each trial, pair remaining 2n plain fences sequentially: (1st,2nd), (3rd,4th), ..., ((2n-1)th, 2nth)
       - Count headers in all n pairs of code blocks  
       - Choose dangling fence that minimizes total headers
    3. Continue until even number of plain fences remains
    """
    
    lines = patched_content.split('\n')
    
    # Find all fences in patched content (excluding those inside inline code or existing code blocks)
    all_fences = []
    in_code_block = False
    for i, line in enumerate(lines):
        if is_valid_code_fence(line, in_code_block):
            # Update code block state after processing this fence
            in_code_block = not in_code_block
            stripped = line.strip()
            content_after = stripped[3:].strip()
            if content_after == '':
                fence_type = 'plain'
                language = None
            else:
                fence_type = 'language'
                language = content_after.split()[0]
            
            all_fences.append({
                'line': i + 1,  # 1-based line numbers
                'type': fence_type,
                'content': stripped,
                'language': language,
                'original_index': i  # 0-based for counting headers
            })
    
    # Find all standalone plain fences (excluding language-closing fences and warnings)
    all_plain_fences = []
    
    # Track opened language blocks to exclude their closing fences
    open_language_fences = []
    
    for fence in all_fences:
        if fence['type'] == 'language':
            open_language_fences.append(fence)
        elif fence['type'] == 'plain' and not lines[fence['original_index']].startswith('>'):
            if open_language_fences:
                # This closes a language block - don't include in optimization
                open_language_fences.pop()
            else:
                # This is a standalone plain fence
                all_plain_fences.append(fence)
    
    # Group plain fences by language block separators
    # A new group starts after any ```xxx ``` paired block
    fence_groups = []
    current_group = []
    
    # Track position in all_fences to detect language blocks between plain fences
    plain_fence_indices = {f['line']: i for i, f in enumerate(all_plain_fences)}
    
    for i, plain_fence in enumerate(all_plain_fences):
        current_group.append(plain_fence)
        
        # Check if there's a ```xxx ``` language block after this fence and before next plain fence
        has_language_block_after = False
        
        if i + 1 < len(all_plain_fences):
            next_plain_fence = all_plain_fences[i + 1]
            
            # Look for language fences between current and next plain fence
            for check_fence in all_fences:
                if (check_fence['line'] > plain_fence['line'] and 
                    check_fence['line'] < next_plain_fence['line'] and
                    check_fence['type'] == 'language'):
                    has_language_block_after = True
                    break
        
        # If there's a language block after this fence, end current group
        if has_language_block_after:
            fence_groups.append(current_group)
            current_group = []
    
    # Add final group
    if current_group:
        fence_groups.append(current_group)
    
    dangling_plain_fences = set()
    
    # Apply 2n+1 optimization algorithm to each group separately
    for group_idx, group in enumerate(fence_groups):
        # dangling ``` exist for odd ``` 
        if len(group) == 1:
            dangling_plain_fences.add(group[0]['line'])
            continue
        
        # Apply 2n+1 optimization for this group
        group_dangling = set()
        while len([f for f in group if f['line'] not in group_dangling]) % 2 == 1:
            current_group_fences = [f for f in group if f['line'] not in group_dangling]
            n_group = len(current_group_fences)
            best_culprit = None
            min_headers = float('inf')
            
            # Try removing each fence in this group as dangling
            for trial_idx, trial_fence in enumerate(current_group_fences):
                # Create test list excluding this trial fence
                test_group_fences = [f for f in current_group_fences if f['line'] != trial_fence['line']]
                
                # Pair remaining 2n fences sequentially: (1st,2nd), (3rd,4th), ...
                pairs = []
                for i in range(0, len(test_group_fences), 2):
                    if i + 1 < len(test_group_fences):
                        start_fence = test_group_fences[i]
                        end_fence = test_group_fences[i + 1]
                        pairs.append((start_fence, end_fence))
                
                # Count headers in all pairs
                total_headers = 0
                for start, end in pairs:
                    # Count headers between start and end (exclusive)
                    for line_idx in range(start['original_index'] + 1, end['original_index']):
                        if line_idx < len(lines) and re.match(r'^#+\s', lines[line_idx].strip()):
                            total_headers += 1
                
                # Track best solution (prefer first occurrence in case of ties)
                if total_headers < min_headers:
                    min_headers = total_headers
                    best_culprit = trial_fence
            
            # Mark best culprit as dangling (always found since total_headers < float('inf'))
            group_dangling.add(best_culprit['line'])
        
        # Add group dangling fences to global set
        dangling_plain_fences.update(group_dangling)
    
    # Create final pairs with all dangling plain fences removed
    final_plain_fences = [f for f in all_plain_fences if f['line'] not in dangling_plain_fences]
    final_pairs = []
    
    for i in range(0, len(final_plain_fences), 2):
        if i + 1 < len(final_plain_fences):
            start_fence = final_plain_fences[i]
            end_fence = final_plain_fences[i + 1]
            final_pairs.append((start_fence, end_fence))
    return final_pairs, dangling_plain_fences


def plain_pre_code_patch(patched_content: str) -> str:
    """Apply plain fence optimization and add warnings for dangling plain fences."""
    
    pairs, dangling_line_numbers = optimize_plain_pre_code(patched_content)
    if not dangling_line_numbers:
        return patched_content
    
    lines = patched_content.split('\n')
    
    # Process dangling plain fences in reverse order to maintain line indices
    for line_num in sorted(dangling_line_numbers, reverse=True):
        dangling_line_idx = line_num - 1  # Convert to 0-based index
        
        # Find where to insert closing ``` 
        # 1. Look for first blank line after dangling ```
        # 2. If no blank line, add just before next ```
        insert_line = None
        
        # Check for FIRST empty line after the dangling ```
        for check_line in range(dangling_line_idx + 1, len(lines)):
            line_content = lines[check_line].strip()
            
            # Check if this is an empty line
            if line_content == "":
                insert_line = check_line
                break
                
            # If we hit another valid fence before finding empty line, insert before it  
            # Note: At this point we're outside any code block (looking for insertion point)
            if is_valid_code_fence(lines[check_line], in_code_block=False):
                insert_line = check_line
                break
        
        if insert_line is None:
            # No blank line and no next fence - insert at end
            insert_line = len(lines)
        
        # Add closing ``` and warning
        closing_fence = "```"
        warning = "> [!WARNING] Incomplete Code Block\n> Plain code block automatically closed here"

        lines.insert(insert_line, closing_fence)
        lines.insert(insert_line + 1, warning)
        
    optimized_content = '\n'.join(lines)
    return optimized_content


def process_pre_code_blocks(content):
    """Patch the markdown content on dangling ```, if any"""

    # Step 1: Language fence patch 
    patched_content = lang_pre_code_patch(content)

    # Step 2: Plain fence optimization and patch 
    patched_content = plain_pre_code_patch(patched_content)

    return patched_content


def process_markdown_file(input_file: str, output_file: str) -> str:
    """Main processing function: patch + optimization"""
    
    # Read input file
    with open(input_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    patched_content = process_pre_code_blocks(content)
    
    # Save final content
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(patched_content)
    
    return output_file

def main():
    """Main entry point with argument parsing"""
    parser = argparse.ArgumentParser(
        description='Pre-code block fence repair tool for markdown files',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
 python %(prog)s input.md                    # Output: input_fixed.md
 python %(prog)s input.md -o custom.md       # Output: custom.md
 python %(prog)s test_comprehensive_dangling.md
        """
    )
    
    parser.add_argument('input_file', help='Input markdown file')
    parser.add_argument('-o', '--output', help='Output file (default: {filename}_fixed.md)')
    
    args = parser.parse_args()
    
    if not os.path.exists(args.input_file):
        parser.error(f"File '{args.input_file}' not found")
    
    # Generate output filename
    if args.output:
        output_file = args.output
    else:
        base_name = os.path.splitext(args.input_file)[0]
        output_file = f"{base_name}_fixed.md"
    
    try:
        result_file = process_markdown_file(args.input_file, output_file)
        print(f"✅ Processing completed successfully")
        print(f"📁 Input:  {args.input_file}")
        print(f"📁 Output: {result_file}")
        return 0
    except Exception as e:
        parser.error(f"Error processing file: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
