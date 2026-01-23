#!/usr/bin/env python
import sys
from fence_utils import is_valid_code_fence

"""
#===============================================================================
  Description
  -----------
      

    Version:  1.0
    Created:  2025-09-02 11:57
     Author:  Zhiyuan Yao, zhiyuan.yao@icloud.com
  Institute:  Lanzhou Center for Theoretical Physics, Lanzhou University
#===============================================================================
"""

class MarkdownBlock:
    """Represents a hierarchical block of markdown content."""
    
    def __init__(self, level, title, content, line_start, line_end):
        self.level = level  # Header level (1-6)
        self.title = title  # Header title
        self.content = content  # Block content including header
        self.line_start = line_start  # Starting line number
        self.line_end = line_end  # Ending line number
        self.children = []  # Sub-blocks
        self.parent = None  # Parent block
        self.html = ""  # Processed HTML
        self.error = None  # Processing error if any
    
    def add_child(self, child_block):
        """Add a child block to this block."""
        child_block.parent = self
        self.children.append(child_block)
    
    def is_root(self):
        """Check if this is a root-level block."""
        return self.parent is None
    
    def get_full_content(self):
        """Get full content including all children for processing."""
        lines = [self.content]
        for child in self.children:
            lines.append(child.get_full_content())
        return '\n'.join(lines)


def parse_markdown_blocks(md_text):
    """
    Parse markdown into hierarchical blocks based on header levels.
    
    Headers inside code blocks and pre-code are ignored and not used as section dividers.
    
    Args:
        md_text (str): Raw markdown text
        
    Returns:
        list: List of root-level MarkdownBlock objects
    """
    import re
    
    lines = md_text.split('\n')
    blocks = []
    current_blocks = {}  # Level -> current block at that level
    
    # Track content before first header as level-0 block
    preamble_lines = []
    first_header_found = False
    
    # Track whether we're inside a code block
    in_code_block = False
    
    # Use unified fence validation function from fence_utils
    # Note: We pass in_code_block to handle context-aware validation
    
    for line_num, line in enumerate(lines):
        # Check if we're entering or exiting a code block
        if is_valid_code_fence(line, in_code_block):
            in_code_block = not in_code_block
        
        # Only process headers if we're NOT inside a code block
        header_match = None
        if not in_code_block:
            # Also check if the line has headers inside inline code (`...`)
            # If the header pattern is within backticks, ignore it
            line_to_check = line.strip()
            
            # Quick check: if line contains backticks, verify header is not inside them
            if '`' in line_to_check:
                # Split by backticks and only check odd-indexed parts (outside code)
                parts = line_to_check.split('`')
                header_outside_code = False
                
                for i, part in enumerate(parts):
                    # Even indices (0, 2, 4...) are outside inline code
                    if i % 2 == 0 and re.match(r'^(#{1,6})\s*(.+)', part):
                        header_outside_code = True
                        break
                
                if header_outside_code:
                    header_match = re.match(r'^(#{1,6})\s*(.+)', line_to_check)
            else:
                # No inline code, check normally
                header_match = re.match(r'^(#{1,6})\s*(.+)', line_to_check)
        
        if header_match:
            first_header_found = True
            level = len(header_match.group(1))
            title = header_match.group(2).strip()
            
            # Create preamble block if we have content before first header
            if preamble_lines and not blocks:
                preamble_block = MarkdownBlock(
                    level=0,
                    title="Preamble", 
                    content='\n'.join(preamble_lines),
                    line_start=0,
                    line_end=line_num - 1
                )
                blocks.append(preamble_block)
                current_blocks[0] = preamble_block
                preamble_lines = []
            
            # Close any blocks at same or deeper level
            levels_to_close = [l for l in current_blocks.keys() if l >= level]
            for l in levels_to_close:
                if l in current_blocks:
                    current_blocks[l].line_end = line_num - 1
                    del current_blocks[l]
            
            # Create new block
            block = MarkdownBlock(
                level=level,
                title=title,
                content=line,
                line_start=line_num,
                line_end=len(lines) - 1  # Will be updated when block closes
            )
            
            # Find parent block (closest higher level)
            parent_level = level - 1
            while parent_level >= 0:
                if parent_level in current_blocks:
                    current_blocks[parent_level].add_child(block)
                    break
                parent_level -= 1
            else:
                # No parent found, this is a root block
                blocks.append(block)
            
            current_blocks[level] = block
            
        else:
            # Add content to appropriate block
            if not first_header_found:
                preamble_lines.append(line)
            else:
                # Find the deepest current block to add this content to
                if current_blocks:
                    deepest_level = max(current_blocks.keys())
                    current_blocks[deepest_level].content += '\n' + line
    
    # Handle case where there are no headers at all
    if not first_header_found and preamble_lines:
        preamble_block = MarkdownBlock(
            level=0,
            title="Document",
            content='\n'.join(preamble_lines),
            line_start=0,
            line_end=len(lines) - 1
        )
        blocks.append(preamble_block)
    
    return blocks


def main(input_file):
    with open(input_file, 'r', encoding='utf-8') as f:
        md_text = f.read()
    blocks = parse_markdown_blocks(md_text)

    # Header
    print("╔" + "═" * 80 + "╗")
    print(f"║{f'MARKDOWN DOCUMENT ANALYSIS: {input_file}':^80}║")
    print(f"║{f'Total Blocks: {len(blocks)}':^80}║")
    print("╚" + "═" * 80 + "╝")
    print()

    def print_block_tree(block, indent=0, is_last=True, parent_lines=None):
        if parent_lines is None:
            parent_lines = []
            
        level_indicator = f"H{block.level}" if block.level > 0 else "ROOT"
        
        # Build the prefix showing the tree structure
        prefix = ""
        for has_siblings_below in parent_lines:
            prefix += "│ " if has_siblings_below else "  "
        
        if indent == 0:
            prefix += "└─"
        else:
            prefix += "└─" if is_last else "├─"
            
        print(f"{prefix} {level_indicator} {block.title}")
        
        # Build detail prefix for the content lines
        detail_prefix = ""
        for has_siblings_below in parent_lines:
            detail_prefix += "│ " if has_siblings_below else "  "
        
        if indent > 0:
            # Add connection from parent
            detail_prefix += "  " if is_last else "│ "
        
        detail_prefix += "  "
                
        print(f"{detail_prefix}📍 Lines: {block.line_start}-{block.line_end} ({block.line_end - block.line_start + 1} lines)")
        
        # Content preview - clean up newlines and limit length
        content_preview = block.content.replace('\n', ' ').strip()
        if len(content_preview) > 60:
            content_preview = content_preview[:57] + "..."
        print(f"{detail_prefix}📝 Preview: {content_preview}")
        
        if block.children:
            print(f"{detail_prefix}📂 Children: {len(block.children)}")
            
            # For children, we need to track if this parent has siblings below it
            child_parent_lines = parent_lines + [not is_last]
            
            for i, child in enumerate(block.children):
                child_is_last = (i == len(block.children) - 1)
                print_block_tree(child, indent + 1, child_is_last, child_parent_lines)
        else:
            print(f"{detail_prefix}🍃 Leaf node")
        
        # Only add empty line after root blocks
        if indent == 0:
            print()
            print()

    # Print each root block
    for i, block in enumerate(blocks):
        header_text = f"Block {i + 1} of {len(blocks)}: {block.title}"
        # Truncate if too long, pad if too short to ensure proper alignment
        if len(header_text) > 76:
            header_text = header_text[:73] + "..."
        
        print(f"┌{'─' * 78}┐")
        print(f"│ {header_text:<76} │")
        print(f"└{'─' * 78}┘")
        print()
        print_block_tree(block)

    # Document structure overview
    print("╔" + "═" * 80 + "╗")
    print(f"║{'DOCUMENT STRUCTURE OVERVIEW':^80}║")
    print("╚" + "═" * 80 + "╝")
    print()
    
    lines = md_text.split('\n')
    header_count = 0
    
    # Define circle and arrow symbols for each header level
    level_symbols = {
        1: "●",     # H1 - filled circle
        2: "○",     # H2 - hollow circle
        3: "▪",     # H3 - filled square
        4: "▫",     # H4 - hollow square  
        5: "▸",     # H5 - right arrow
        6: "▹"      # H6 - hollow right arrow
    }
    
    # Track whether we're inside a code block for overview section too
    overview_in_code_block = False
    
    for i, line in enumerate(lines):
        # Check if we're entering or exiting a code block using unified function
        if is_valid_code_fence(line, overview_in_code_block):
            overview_in_code_block = not overview_in_code_block
        
        # Only process headers if we're NOT inside a code block
        if not overview_in_code_block and line.strip().startswith('#'):
            header_count += 1
            level = len(line.strip().split()[0])
            title = line.strip()[level:].strip()
            
            # Create proper indentation with more spacing
            base_indent = "    " * (level - 1)  # 4 spaces per level instead of 2
            symbol = level_symbols.get(level, "◦")
            
            print(f"Line {i:3d}: {base_indent}{symbol} {title}")
            
            # Show all headers (removed the 20 header limit)
            # if header_count >= 20:
            #     remaining_headers = sum(1 for line in lines[i+1:] if line.strip().startswith('#'))
            #     if remaining_headers > 0:
            #         print(f"         ... and {remaining_headers} more headers")
            #     break
    
    print()
    print("╔" + "═" * 80 + "╗")
    print(f"║{'ANALYSIS COMPLETE':^80}║")
    print("╚" + "═" * 80 + "╝")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        main(input_file=sys.argv[1])
