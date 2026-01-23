#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
#===============================================================================
  Description
  -----------

    `md2html` is a sophisticated Python-based converter that transforms Markdown
    files into professional, styled HTML documents. It is designed for reliability,
    especially with complex technical and academic content, featuring a
    fault-tolerant, block-based architecture that prevents single errors from
    failing the entire document. Key features include smart code-fence repair,
    advanced LaTeX rendering, interactive tables of contents, and Obsidian-style
    callouts.

    - Example Usage

        python md2html.py input.md
        python md2html.py input.md input.html
        python md2html.py input.md --theme one-dark

    Version:  1.0
    Created:  2025-09-01 20:43
     Author:  Zhiyuan Yao, zhiyuan.yao@icloud.com
  Institute:  Lanzhou Center for Theoretical Physics, Lanzhou University
#===============================================================================
  TODO:
#===============================================================================
"""
import os
import re
import sys
import mistune
import argparse
from pre_code_patch import process_pre_code_blocks
from parse_blocks import MarkdownBlock, parse_markdown_blocks
from fence_utils import is_valid_code_fence

# Get the directory where this script is located
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PRISM_DIR = os.path.join(SCRIPT_DIR, '.prism')

# --- Helper Functions ---

def has_standalone_toc_marker(md_text):
    """
    Check if [TOC] appears as a standalone line in the markdown text, excluding code blocks.

    Args:
        md_text (str): The markdown text to check

    Returns:
        bool: True if [TOC] appears alone on a line outside code blocks, False otherwise
    """
    lines = md_text.split('\n')
    in_code_block = False

    for line in lines:
        # Check if we're entering or exiting a code block using unified function
        if is_valid_code_fence(line, in_code_block):
            in_code_block = not in_code_block
            continue

        # Only check for [TOC] if we're NOT inside a code block
        stripped = line.strip()
        if not in_code_block and stripped == '[TOC]':
            return True

    return False


def find_standalone_toc_positions(md_text):
    """
    Find line numbers where [TOC] appears as standalone lines (not in code blocks).

    Args:
        md_text (str): The markdown text to check

    Returns:
        list: List of line numbers (0-indexed) where standalone [TOC] appears
    """
    lines = md_text.split('\n')
    in_code_block = False
    positions = []

    for line_num, line in enumerate(lines):
        # Check if we're entering or exiting a code block using unified function
        if is_valid_code_fence(line, in_code_block):
            in_code_block = not in_code_block
            continue

        # Only check for [TOC] if we're NOT inside a code block
        stripped = line.strip()
        if not in_code_block and stripped == '[TOC]':
            positions.append(line_num)

    return positions


def process_choice_options(html_content):
    """
    Convert choice options to single line format with special styling.

    Supports three common formats:
    A. option text  (uppercase with period)
    A) option text  (uppercase with parenthesis)
    (A) option text (uppercase in parentheses)

    And converts them to styled single-line paragraphs.

    Args:
        html_content (str): HTML content to process

    Returns:
        str: HTML content with choice options formatted as single lines
    """
    import re

    # Pattern to match paragraphs containing choice options with <br /> separators
    def process_choice_paragraph(paragraph_match):
        paragraph_content = paragraph_match.group(1)

        # Split by <br /> tags and newlines to get individual lines
        lines = re.split(r'<br\s*/?>\s*', paragraph_content)
        # Further split by newlines in case there are embedded newlines
        all_lines = []
        for line in lines:
            all_lines.extend(line.split('\n'))
        lines = [line.strip() for line in all_lines if line.strip()]

        # Check if this looks like a choice options sequence
        choice_options = []
        before_choices = []
        after_choices = []
        current_letter = ord('A')
        choice_found = False
        choice_sequence_ended = False
        choice_format = None  # Track format: 'A.', 'A)', '(A)'

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Check if this line is a choice option (three formats)
            expected_letter = chr(current_letter)

            # Try different patterns
            patterns = [
                (rf'^{expected_letter}\.\s*(.+)$', f'{expected_letter}.', 'A.'),           # A.
                (rf'^{expected_letter}\)\s*(.+)$', f'{expected_letter})', 'A)'),          # A)
                (rf'^\({expected_letter}\)\s*(.+)$', f'({expected_letter})', '(A)'),      # (A)
            ]

            choice_match = None
            display_text = None
            format_type = None

            for pattern, display, fmt in patterns:
                match = re.match(pattern, line)
                if match:
                    # If this is the first choice, set the format
                    if choice_format is None:
                        choice_format = fmt
                        choice_match = match
                        display_text = display
                        format_type = fmt
                        break
                    # If format matches existing format, accept it
                    elif choice_format == fmt:
                        choice_match = match
                        display_text = display
                        format_type = fmt
                        break

            if choice_match and not choice_sequence_ended:
                # This is a valid choice option in sequence
                content = choice_match.group(1).strip()
                choice_options.append((display_text, content))
                current_letter += 1
                choice_found = True
            elif choice_found and not choice_sequence_ended:
                # We found choices before, but this line doesn't match - sequence ended
                choice_sequence_ended = True
                after_choices.append(line)
            elif not choice_found:
                # We haven't found any choices yet, this goes before
                before_choices.append(line)
            else:
                # Add to content after choices
                after_choices.append(line)

        # If we found at least 2 consecutive choice options starting with A or (A)
        if len(choice_options) >= 2 and (choice_options[0][0].startswith('A') or choice_options[0][0].startswith('(A')):
            # Build the result with proper separation
            result_lines = []

            # Add content before choices
            if before_choices:
                before_text = ' '.join(before_choices)
                result_lines.append(f'<p>{before_text}</p>')

            # Add choice options as individual lines
            for display_text, content in choice_options:
                result_lines.append(f'<p class="choice-option"><strong>{display_text}</strong> {content}</p>')

            # Add content after choices
            if after_choices:
                after_text = ' '.join(after_choices)
                result_lines.append(f'<p>{after_text}</p>')

            return '\n'.join(result_lines)

        # If not a choice options paragraph, return original
        return paragraph_match.group(0)

    # Process paragraphs that might contain choice options
    html_content = re.sub(r'<p>(.*?)</p>', process_choice_paragraph, html_content, flags=re.DOTALL)

    return html_content


def process_mermaid_diagrams(html_content):
    """
    Convert ```mermaid code blocks to Mermaid diagram containers.

    Transforms code blocks with language-mermaid class into div containers
    that Mermaid.js can render as diagrams.

    Args:
        html_content (str): HTML content to process

    Returns:
        str: HTML content with Mermaid code blocks converted to diagram containers
    """
    import re

    def convert_mermaid_block(match):
        # Extract the mermaid code content
        code_content = match.group(1)

        # Generate a unique ID for this diagram
        import hashlib
        diagram_id = "mermaid-" + hashlib.md5(code_content.encode()).hexdigest()[:8]

        # Return the mermaid container div
        return f'''<div class="mermaid-diagram" id="{diagram_id}">
{code_content}
</div>'''

    # Pattern to match <pre><code class="language-mermaid">...</code></pre> blocks
    mermaid_pattern = r'<pre><code class="[^"]*language-mermaid[^"]*">(.*?)</code></pre>'

    # Convert all mermaid code blocks
    html_content = re.sub(mermaid_pattern, convert_mermaid_block, html_content, flags=re.DOTALL)

    return html_content


def wrap_long_code_blocks(html_content, max_lines):
    """
    Wrap code blocks longer than max_lines in collapsible HTML structure.

    Args:
        html_content (str): HTML content with code blocks
        max_lines (int): Maximum lines before wrapping in collapsible

    Returns:
        str: HTML content with long code blocks wrapped in collapsible sections
    """
    # Counter for unique IDs
    collapse_counter = 0

    def replace_code_block(match):
        nonlocal collapse_counter

        # Extract the full code block
        full_match = match.group(0)
        start_pos = match.start()

        # Check if this code block is inside a <details> tag or existing collapsible
        # Look backwards from the match position for unclosed <details> tags
        text_before = html_content[:start_pos]

        # Count <details> tags (opening) and </details> tags (closing) before this position
        details_open = len(re.findall(
            r'<details[^>]*>', text_before, re.IGNORECASE))
        details_close = len(re.findall(
            r'</details>', text_before, re.IGNORECASE))

        # If we're inside an unclosed <details> tag, don't add additional collapse
        if details_open > details_close:
            return full_match

        # Also check for existing wrap-collabsible divs
        if '<div class="wrap-collabsible">' in text_before.split('</div>')[-1]:
            return full_match

        # Count lines in the code block
        # Look for the content between <code> and </code>
        code_content = re.search(
            r'<code[^>]*>(.*?)</code>', full_match, re.DOTALL)
        if not code_content:
            return full_match

        lines = code_content.group(1).count('\n') + 1

        # If code block is short enough, return as-is
        if lines <= max_lines:
            return full_match

        # Generate unique ID for this collapsible
        collapse_counter += 1
        collapse_id = f"code-collapse-{collapse_counter}"

        # Extract language from class attribute if present
        lang_match = re.search(r'class="[^"]*language-([^"\s]+)', full_match)
        language = lang_match.group(1) if lang_match else "code"

        # Special handling for JSON - if it looks like JSON but uses javascript class, show as JSON
        if language == "javascript":
            # Check if the content looks like JSON (starts with { or [, has quotes around keys)
            content_text = code_content.group(1).strip()
            if re.search(r'^\s*[\{\[]', content_text) and re.search(r'"[^"]+"\s*:', content_text):
                language = "json"

        # Create collapsible wrapper (Prism.js will add toolbar automatically)
        collapsible_html = f'''<div class="wrap-content-collapsible">
    <input id="{collapse_id}" class="toggle" type="checkbox">
    <label for="{collapse_id}" class="lbl-toggle">{language.upper()} ({lines} lines)</label>
    <div class="content-collapsible-content">
        <div class="content-inner">
{full_match}
        </div>
    </div>
</div>'''

        return collapsible_html

    # Find and replace code blocks
    # Pattern matches <pre><code>...</code></pre> structures
    pattern = r'<pre[^>]*><code[^>]*>.*?</code></pre>'
    result = re.sub(pattern, replace_code_block, html_content, flags=re.DOTALL)

    return result


def create_mistune_with_toc():
    """
    Create mistune markdown parser with native TOC hook support.

    Returns:
        mistune.Markdown: Configured markdown parser with TOC support
    """
    from mistune.toc import add_toc_hook

    # Create basic mistune markdown parser
    md = mistune.create_markdown(
        escape=False,
        plugins=['strikethrough', 'table', 'footnotes', 'task_lists']
    )

    # Add native TOC hook for extracting headers
    add_toc_hook(md)

    return md


def fix_toc_ids_globally(html_content, global_counter):
    """
    Fix TOC IDs in a single block to be globally unique across all blocks.

    Args:
        html_content (str): HTML content from a single block
        global_counter (dict): Mutable counter {'count': N} shared across blocks

    Returns:
        str: HTML content with globally unique TOC IDs
    """
    import re

    def replace_toc_id(match):
        # Increment global counter for each header found
        global_counter['count'] += 1
        header_tag = match.group(1)  # h1, h2, etc.
        header_content = match.group(2)  # everything between tags

        # Replace toc_N with globally unique toc_M
        new_id = f"toc_{global_counter['count']}"
        return f'<{header_tag} id="{new_id}">{header_content}</{header_tag}>'

    # Find headers with toc_ IDs and replace them with globally unique ones
    toc_pattern = r'<(h[1-6])[^>]*id="toc_\d+"[^>]*>([^<]+)</(h[1-6])>'
    html_content = re.sub(toc_pattern, replace_toc_id, html_content)

    return html_content


def convert_toc_ids_to_slugs(html_body, toc_items, md_text):
    """
    Convert toc_N style IDs to user-specified slug IDs found in markdown links.

    Args:
        html_body (str): HTML content with toc_N IDs
        toc_items (list): List of (level, anchor, title) tuples
        md_text (str): Original markdown text to extract link slugs from

    Returns:
        str: HTML with user-specified slug IDs
    """
    import re

    # Extract all markdown links and their targets
    link_pattern = r'\[([^\]]+)\]\(#([^)]+)\)'
    links = re.findall(link_pattern, md_text)

    # Create mapping of link text to slug
    text_to_slug = {}
    for link_text, slug in links:
        text_to_slug[link_text.strip()] = slug

    # Find all headers in the HTML and replace their IDs with matching slugs
    def replace_header_id(match):
        header_tag = match.group(1)  # h1, h2, etc.
        current_id = match.group(2)  # current ID
        header_text = match.group(3)  # header text

        # Look for user-provided slug for this header text
        user_slug = text_to_slug.get(header_text.strip())
        if user_slug:
            return f'<{header_tag} id="{user_slug}">{header_text}</{header_tag}>'
        else:
            # Keep original ID if no slug found
            return match.group(0)

    # Replace header IDs with user slugs
    header_pattern = r'<(h[1-6])[^>]*id="([^"]+)"[^>]*>([^<]+)</(h[1-6])>'
    html_body = re.sub(header_pattern, replace_header_id, html_body)

    return html_body


def update_toc_items_with_new_anchors(html_body, toc_items):
    """
    Update toc_items list with the actual anchor IDs found in the HTML
    after slug replacement has occurred.

    Args:
        html_body (str): HTML content with updated anchor IDs
        toc_items (list): Original list of (level, anchor, title) tuples

    Returns:
        list: Updated toc_items with current anchor IDs from HTML
    """
    import re

    # Extract current header IDs from HTML
    header_pattern = r'<h([1-6])[^>]*id="([^"]+)"[^>]*>([^<]+)</h[1-6]>'
    current_headers = re.findall(header_pattern, html_body)

    # Create mapping of title to current ID
    title_to_id = {}
    for level, anchor_id, title in current_headers:
        title_to_id[title.strip()] = anchor_id

    # Update toc_items with current IDs
    updated_toc_items = []
    for level, old_anchor, title in toc_items:
        current_id = title_to_id.get(title, old_anchor)
        updated_toc_items.append((level, current_id, title))

    return updated_toc_items


def find_toc_insertion_point(html_body):
    """
    Find the optimal insertion point for TOC:
    - After h1 title and any following paragraphs/content
    - But before the first h2 section

    Args:
        html_body (str): HTML content

    Returns:
        int: Position index where TOC should be inserted
    """
    import re

    # Find first h1
    h1_match = re.search(r'<h1[^>]*>.*?</h1>', html_body, re.DOTALL)
    if not h1_match:
        # No h1 found, find first h2 or insert at beginning
        h2_match = re.search(r'<h2[^>]*>', html_body)
        return h2_match.start() if h2_match else 0

    # Start searching after the h1 tag
    search_start = h1_match.end()

    # Find first h2 after h1
    h2_match = re.search(r'<h2[^>]*>', html_body[search_start:])
    if not h2_match:
        # No h2 found, insert at end
        return len(html_body)

    # Get absolute position of h2
    h2_pos = search_start + h2_match.start()

    # Look backwards from h2 to find the last complete block element
    # Search in the content between h1 end and h2 start
    content_section = html_body[search_start:h2_pos]

    # Find all closing block tags and their positions
    block_pattern = r'</(?:p|div|ul|ol|blockquote|pre|table|hr|h[1-6])>'

    last_block_end = None
    for match in re.finditer(block_pattern, content_section):
        # Get absolute position in the full HTML
        absolute_pos = search_start + match.end()
        if last_block_end is None or absolute_pos > last_block_end:
            last_block_end = absolute_pos

    # If we found block elements, insert after the last complete one
    if last_block_end is not None:
        return last_block_end

    # If no block elements found, insert right before h2
    # This handles cases where there might be just text or malformed HTML
    return h2_pos


def generate_and_insert_toc(html_body, toc_items, md_text):
    """
    Generate TOC HTML and insert it where [TOC] placeholder appears,
    exactly where [TOC] placeholder appears.

    Args:
        html_body (str): Complete HTML body content
        toc_items (list): List of (level, anchor, title) tuples from all blocks
        md_text (str): Original markdown text to check for [TOC] placeholder

    Returns:
        str: HTML with TOC inserted
    """
    import re

    if not toc_items:
        return html_body

    # Filter TOC items to exclude headers before [TOC] placeholder
    # Note: This function is only called when standalone [TOC] exists
    toc_position = md_text.find('[TOC]')
    lines_before_toc = md_text[:toc_position].count('\n')

    # Get header positions in original markdown
    header_lines = {}
    for line_num, line in enumerate(md_text.split('\n')):
        if re.match(r'^#+\s', line):
            header_text = re.sub(r'^#+\s*', '', line).strip()
            header_lines[header_text] = line_num

    # Filter toc_items to only include those after TOC position
    filtered_toc_items = []
    for level, anchor, title in toc_items:
        if title in header_lines and header_lines[title] > lines_before_toc:
            filtered_toc_items.append((level, anchor, title))

    # Generate TOC HTML with proper header
    if filtered_toc_items:
        toc_html = '<h2>Table of Contents</h2>\n<div class="toc">'
        toc_html += render_toc_ul_with_symbols(filtered_toc_items)
        toc_html += '</div>'
    else:
        toc_html = ''

    # Replace [TOC] placeholder in HTML - only replace standalone occurrences
    # The most reliable pattern is <p>[TOC]</p> since standalone [TOC] becomes a paragraph
    if '<p>[TOC]</p>' in html_body:
        html_body = html_body.replace('<p>[TOC]</p>', toc_html, 1)  # Replace only first occurrence
    elif '[TOC]' in html_body:
        # Fallback for other cases
        html_body = html_body.replace('[TOC]', toc_html, 1)  # Replace only first occurrence

    return html_body


def render_toc_ul_with_symbols(toc_items):
    """
    Custom TOC renderer that adds different list symbols for different levels with proper nesting.
    """
    symbols = ['', '●', '○', '▪', '▫', '▸', '▹']

    if not toc_items:
        return ''

    html = []
    current_level = 0
    open_lists = []

    for level, anchor, title in toc_items:
        symbol = symbols[(level - 1) % len(symbols)]

        # Close lists if we're at a shallower level
        while current_level > level:
            html.append('  ' * (current_level - 1) + '</ul>')
            open_lists.pop()
            current_level -= 1

        # Open new lists if we're at a deeper level
        while current_level < level:
            html.append('  ' * current_level + '<ul>')
            open_lists.append(level)
            current_level += 1

        # Add the list item
        indent = '  ' * (level - 1)
        html.append(f'{indent}  <li><span class="toc-symbol" data-level="{level}">{symbol}</span><a href="#{anchor}">{title}</a></li>')

    # Close all remaining lists
    while open_lists:
        current_level -= 1
        html.append('  ' * current_level + '</ul>')
        open_lists.pop()

    return '\n'.join(html) + '\n'


def process_toc_with_native_mistune(md_text):
    """
    Process markdown with native mistune TOC functions,
    excluding headers before [TOC] placeholder.

    Args:
        md_text (str): Markdown text with [TOC] placeholders

    Returns:
        tuple: (html_content, toc_items_after_toc)
    """
    if '[TOC]' not in md_text:
        # No TOC requested, use regular processing
        md = mistune.create_markdown(
            escape=False,
            plugins=['strikethrough', 'table', 'footnotes', 'task_lists']
        )
        return md(md_text), []

    import re
    from mistune.toc import add_toc_hook, render_toc_ul

    # Create mistune with TOC hook - use basic mistune, not the wrapper
    md = mistune.create_markdown(
        escape=False,
        plugins=['strikethrough', 'table', 'footnotes', 'task_lists'],
        renderer=mistune.HTMLRenderer(escape=False)
    )
    add_toc_hook(md, min_level=1, max_level=5)

    # Find position of [TOC] in the original markdown
    toc_position = md_text.find('[TOC]')
    lines_before_toc = md_text[:toc_position].count('\n')

    # Replace [TOC] with a placeholder that will survive markdown processing
    toc_placeholder = '<!--TOC_PLACEHOLDER-->'
    temp_md_text = md_text.replace('[TOC]', toc_placeholder)

    # Parse the markdown to get TOC items
    html_content, state = md.parse(temp_md_text)

    # Get all TOC items
    all_toc_items = state.env.get('toc_items', [])

    # Get header positions in original markdown
    header_lines = {}
    for line_num, line in enumerate(md_text.split('\n')):
        if re.match(r'^#+\s', line):
            header_text = re.sub(r'^#+\s*', '', line).strip()
            header_lines[header_text] = line_num

    # Filter toc_items to only include those after TOC position
    filtered_toc_items = []
    for level, anchor, title in all_toc_items:
        # Check if this header appears after the TOC in the original text
        if title in header_lines and header_lines[title] > lines_before_toc:
            filtered_toc_items.append((level, anchor, title))

    # Generate TOC HTML using native render_toc_ul with custom symbols
    if filtered_toc_items:
        toc_html = '<div class="toc">'
        toc_html += render_toc_ul_with_symbols(filtered_toc_items)
        toc_html += '</div>'
    else:
        toc_html = ''

    # Replace the placeholder with actual TOC HTML
    html_content = html_content.replace(toc_placeholder, toc_html)

    # Also handle case where placeholder got wrapped in <p> tags
    html_content = html_content.replace(f'<p>{toc_placeholder}</p>', toc_html)

    return html_content, filtered_toc_items


# --- Unit-Based Block Rendering Architecture ---

def process_block_safely(block, conversion_func):
    """
    Process a single markdown block with error isolation.

    Args:
        block (MarkdownBlock): Block to process
        conversion_func (callable): Function to convert markdown to HTML

    Returns:
        bool: True if successful, False if error occurred
    """
    try:
        # Process only this block's immediate content (not children)
        block.html = conversion_func(block.content)
        block.error = None
        return True

    except Exception as e:
        # Isolate error to this block only
        block.error = str(e)
        block.html = f'''<div class="block-error">
            <h3>⚠️ Block Processing Error</h3>
            <p><strong>Block:</strong> {block.title} (Level {block.level})</p>
            <p><strong>Error:</strong> {block.error}</p>
            <details>
                <summary>Raw Content</summary>
                <pre><code>{block.content[:200]}{'...' if len(block.content) > 200 else ''}</code></pre>
            </details>
        </div>'''
        return False


def reassemble_processed_blocks(blocks):
    """
    Reassemble processed blocks back into hierarchical HTML structure.

    Args:
        blocks (list): List of processed MarkdownBlock objects

    Returns:
        str: Complete HTML content
    """
    def render_block_tree(block):
        """Recursively render block and its children."""
        html_parts = [block.html]

        for child in block.children:
            html_parts.append(render_block_tree(child))

        return '\n'.join(html_parts)

    # Render all root blocks
    html_parts = []
    for block in blocks:
        if block.is_root():
            html_parts.append(render_block_tree(block))

    return '\n'.join(html_parts)


def add_topic_thumbnail_admonitions(html_content):
    """
    Convert Topic and Thumbnail pairs under Problem sections to a single orange admonition.

    Example:
    **Topic**: Multicritical points (123)
    **Thumbnail**: Description text

    Becomes:
    <div class="admonition orange">
        <p class="admonition-orange">Multicritical points (123)</p>
        Description text
    </div>
    """
    import re

    # Pattern to match Topic followed by Thumbnail
    pattern = r'<p><strong>Topic</strong>:\s*(.*?)</p>\s*<p><strong>Thumbnail</strong>:\s*(.*?)</p>'

    def replace_with_combined_admonition(match):
        # Content of Topic (becomes title)
        topic_content = match.group(1)
        # Content of Thumbnail (becomes body)
        thumbnail_content = match.group(2)

        return f'''<div class="admonition-wrapper">
    <div class="admonition orange">
        <p class="admonition-orange">{topic_content}</p>
        {thumbnail_content}
    </div>
</div>'''

    # Also handle cases where there's only Topic (no Thumbnail)
    pattern_topic_only = r'<p><strong>Topic</strong>:\s*(.*?)</p>(?!\s*<p><strong>Thumbnail</strong>)'

    def replace_topic_only(match):
        topic_content = match.group(1)
        return f'''<div class="admonition-wrapper">
    <div class="admonition orange">
        <p class="admonition-orange">{topic_content}</p>
    </div>
</div>'''

    # First handle Topic+Thumbnail pairs, then handle standalone Topics
    html_content = re.sub(
        pattern, replace_with_combined_admonition, html_content, flags=re.DOTALL)
    html_content = re.sub(
        pattern_topic_only, replace_topic_only, html_content, flags=re.DOTALL)

    return html_content


def process_standalone_boxed_math(text):
    """
    Process standalone \boxed{...} expressions on their own lines.

    Converts lines that start with \boxed{...} into display math format.
    Only processes lines that:
    1. Start with \boxed (after optional whitespace)
    2. Are not inside code blocks or other protected environments

    Args:
        text (str): The text content to process

    Returns:
        str: Text with standalone \boxed expressions converted to display math
    """
    lines = text.split('\n')
    result_lines = []

    for line in lines:
        # Check if line starts with \boxed (no leading whitespace allowed)
        if line.startswith('\\boxed{'):
            # Simple check for balanced braces - find the matching closing brace
            brace_count = 0
            boxed_end = -1
            for i, char in enumerate(line):
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0 and i > 7:  # After "\boxed{"
                        boxed_end = i
                        break

            # If we found a complete \boxed{...} expression and it's the whole line
            if boxed_end > 0 and line[boxed_end + 1:].strip() == '':
                boxed_expr = line[:boxed_end + 1]
                # Convert to display math format
                display_math = f'$${boxed_expr}$$'
                result_lines.append(display_math)
            else:
                # Incomplete or malformed, keep as is
                result_lines.append(line)
        else:
            # Not a boxed expression, keep as is
            result_lines.append(line)

    return '\n'.join(result_lines)


def process_standalone_math_envs(text, protected_math):
    r"""
    Find standalone LaTeX \begin{env}...\end{env} math environments,
    wrap them in $$...$$, and add to protected_math with consecutive numbering.

    Called AFTER code protection, so code blocks are already CODEPROTECT{n}.
    Called AFTER basic math protection, so $$...$$ are already MATHEXPR{n}.
    Any \begin{equation} inside those is hidden - only standalone ones remain.

    Args:
        text (str): Text with code/math already protected as placeholders
        protected_math (list): Existing protected math list (will append to this)

    Returns:
        str: Text with standalone math environments replaced by MATHEXPR{n}MATHEXPR
    """
    import re

    # Whitelist of LaTeX math environments (NOT lists like itemize)
    MATH_ENVIRONMENTS = {
        'align', 'align*', 'equation', 'equation*',
        'gather', 'gather*', 'multline', 'multline*',
        'split', 'cases', 'matrix', 'pmatrix', 'bmatrix',
        'vmatrix', 'Vmatrix', 'smallmatrix', 'array',
        'eqnarray', 'eqnarray*', 'alignat', 'alignat*',
        'flalign', 'flalign*'
    }

    lines = text.split('\n')
    result_lines = []
    in_math_env = False
    math_env_lines = []
    env_name = None

    for line in lines:
        # Check for \begin{environment}
        begin_match = re.match(r'^\s*\\begin\{([a-zA-Z*]+)\}', line)
        if begin_match and not in_math_env:
            env_name = begin_match.group(1)
            if env_name in MATH_ENVIRONMENTS:
                in_math_env = True
                math_env_lines = [line]
                continue

        # Check for \end{environment}
        end_match = re.match(r'^\s*\\end\{([a-zA-Z*]+)\}', line)
        if end_match and in_math_env and end_match.group(1) == env_name:
            math_env_lines.append(line)

            # Wrap environment in $$...$$ and protect it
            env_content = '\n'.join(math_env_lines)
            wrapped = f'$${env_content}$$'

            # Add to protected_math with CONSECUTIVE numbering
            protected_math.append(wrapped)
            placeholder = f'MATHEXPR{len(protected_math)-1}MATHEXPR'

            result_lines.append(placeholder)

            in_math_env = False
            math_env_lines = []
            env_name = None
            continue

        # Accumulate math environment lines
        if in_math_env:
            math_env_lines.append(line)
        else:
            result_lines.append(line)

    # Handle unclosed environments (keep as-is with warning)
    if in_math_env:
        print(f"⚠️  Warning: Unclosed math environment \\begin{{{env_name}}}")
        result_lines.extend(math_env_lines)

    return '\n'.join(result_lines)


def convert_latex_lists_to_markdown(text):
    r"""
    Convert LaTeX list environments to Markdown list syntax.

    Called AFTER code/math protection, so code/math blocks are already placeholders.
    Only processes standalone \begin{itemize}/\begin{enumerate} that remain visible.

    Converts:
    - \begin{itemize} ... \end{itemize} -> Markdown unordered list (-)
    - \begin{enumerate} ... \end{enumerate} -> Markdown ordered list (1., 2., ...)
    - \item content -> list item

    Args:
        text (str): Text with code/math already protected

    Returns:
        str: Text with LaTeX lists converted to Markdown
    """
    import re

    lines = text.split('\n')
    result_lines = []
    in_list = False
    list_type = None  # 'itemize' or 'enumerate'
    item_counter = 0

    for line in lines:
        # Detect list start
        if re.match(r'^\s*\\begin\{itemize\}\s*$', line):
            in_list = True
            list_type = 'itemize'
            item_counter = 0
            continue
        elif re.match(r'^\s*\\begin\{enumerate\}\s*$', line):
            in_list = True
            list_type = 'enumerate'
            item_counter = 0
            continue

        # Detect list end
        if re.match(r'^\s*\\end\{(itemize|enumerate)\}\s*$', line):
            in_list = False
            list_type = None
            result_lines.append('')  # Blank line after list
            continue

        # Convert \item
        if in_list:
            item_match = re.match(r'^\s*\\item\s+(.+)$', line)
            if item_match:
                content = item_match.group(1)
                if list_type == 'itemize':
                    result_lines.append(f'- {content}')
                else:  # enumerate
                    item_counter += 1
                    result_lines.append(f'{item_counter}. {content}')
            elif line.strip():
                # Non-empty line inside list (continuation of previous item)
                result_lines.append(f'  {line.strip()}')
            continue

        result_lines.append(line)

    return '\n'.join(result_lines)


def process_obsidian_callouts(html_content):
    """
    Convert Obsidian-style callouts to HTML callout format.

    Example:
    > [!bug] Incomplete Code Block
    > python code block automatically closed here

    Becomes:
    <div class="callout" data-callout="bug">
        <div class="callout-title">
            <div class="callout-icon"></div>
            Incomplete Code Block
            <div class="callout-fold"></div>
        </div>
        <div class="callout-content">
            python code block automatically closed here
        </div>
    </div>
    """
    import re

    # Pattern to match Obsidian-style callouts
    # Matches entire blockquote containing [!TYPE] and content
    callout_pattern = r'<blockquote>(.*?)</blockquote>'

    def replace_callout(match):
        blockquote_content = match.group(1).strip()

        # Check if this blockquote contains a callout marker
        if not re.search(r'\[!(.*?)\]', blockquote_content):
            return match.group(0)  # Return original if no callout marker

        # Extract callout type and title from the first paragraph that contains [!TYPE]
        first_p_match = re.search(r'<p>\[!(.*?)\](.*?)</p>', blockquote_content)
        if not first_p_match:
            return match.group(0)  # Return original if can't parse

        callout_type = first_p_match.group(1).lower()
        title = first_p_match.group(2).strip()  # Only the text on the same line as [!TYPE]

        # Collect all content after the title paragraph
        content_parts = []

        # Find the position after the title paragraph to get all remaining content
        title_p_end = blockquote_content.find('</p>', blockquote_content.find('[!' + callout_type.upper() + ']')) + 4
        remaining_content = blockquote_content[title_p_end:].strip()

        if remaining_content:
            # Keep all remaining HTML elements (paragraphs, code blocks, etc.)
            content_parts.append(remaining_content)

        # Build the callout HTML
        callout_html = f'<div class="callout is-open" data-callout="{callout_type}">'

        # Add title with icon and fold indicator
        callout_html += f'''
    <div class="callout-title">
        <div class="callout-icon"></div>
        {title}
        <div class="callout-fold"></div>
    </div>'''

        # Add content if exists
        if content_parts:
            # Join content parts without adding <br> tags since they're already HTML
            content_html = "\n        ".join(content_parts)
            callout_html += f'''
    <div class="callout-content">
        {content_html}
    </div>'''

        callout_html += '</div>'

        return callout_html

    # Replace Obsidian-style callouts
    html_content = re.sub(callout_pattern, replace_callout, html_content, flags=re.DOTALL)

    return html_content


# --- HTML Template ---
# This template wraps the converted Markdown content and includes placeholders
# for the title, custom CSS, and the code highlighting CSS.
HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>

    <!-- MathJax Configuration and Loading - NOTE: Requires internet for LaTeX rendering -->
    <script type="text/x-mathjax-config">
    MathJax.Hub.Config({{
      tex2jax: {{
        inlineMath: [['$', '$'], ['\\\\(', '\\\\)']],
        displayMath: [['$$', '$$'], ['\\\\[', '\\\\]']],
        processEscapes: true,
        processEnvironments: true,
        processClass: "math"
      }},
      TeX: {{
        extensions: ["mhchem.js", "AMSmath.js", "AMSsymbols.js", "AMScd.js"],
        Macros: {{
          llbracket:      ['⟦', 0],
          rrbracket:      ['⟧', 0],
          llparenthesis:  ['⟪', 0],
          rrparenthesis:  ['⟫', 0],
          llfloor:        ['⌊⌊', 0],
          rrfloor:        ['⌋⌋', 0]
        }}
      }},
      "CommonHTML": {{
        linebreaks: {{ automatic: true }},
        scale: 90
      }}
    }});
    </script>
    <script type="text/javascript" async
      src="https://cdnjs.cloudflare.com/ajax/libs/mathjax/2.7.7/MathJax.js?config=TeX-MML-AM_CHTML">
    </script>
{mermaid_js}
    <!-- Prism.js for Code Highlighting - 100% offline with embedded theme -->
    <!-- Modern CSS frameworks for cross-platform support -->
    <style>
/* Normalize.css for consistent cross-browser rendering */
{normalize_css}

/* Modern base styles with CSS variables and accessibility */
{modern_base_css}

/* Mobile-responsive styles */
{mobile_responsive_css}

/* Prism {prism_theme} theme - embedded for offline use */
{prism_theme_css}

/* Block error styling */
.block-error {{
    background-color: #fff3cd;
    border: 1px solid #ffeaa7;
    border-radius: 6px;
    padding: 15px;
    margin: 20px 0;
    color: #856404;
}}

.block-error h3 {{
    margin-top: 0;
    color: #dc3545;
}}

.block-error pre {{
    background-color: #f8f9fa;
    padding: 10px;
    border-radius: 4px;
    overflow-x: auto;
    font-size: 0.9em;
}}
    </style>
    {line_numbers_css}
    <!-- Copy the exact prism.js that demo.html uses -->
    <script>
{prism_js_content}
    </script>
    <script>
        // Ensure Prism highlights all code blocks when page loads
        document.addEventListener('DOMContentLoaded', function() {{
            Prism.highlightAll();
        }});
    </script>

    <!-- Callouts functionality -->
    <script>
{callouts_js_content}
    </script>

    <style>
{custom_css}
    </style>
</head>
<body{body_class}>
    <div id="__next">
        <div id="page-ctn">
            <header id="page-header">
                <h3></h3>
            </header>
            <section class="markdown-body">
{html_body}
            </section>
        </div>
    </div>

    <!-- Section folding JavaScript is included by the folding function -->
</body>
</html>"""


def download_all_prism_themes():
    """Download and cache all available Prism themes for offline use."""
    # Official Prism themes from CDNJS
    official_themes = [
        'prism', 'prism-dark', 'prism-funky', 'prism-okaidia',
        'prism-twilight', 'prism-coy', 'prism-solarizedlight',
        'prism-tomorrow'
    ]

    # Popular editor themes from prism-themes repository
    prism_themes = [
        'prism-one-dark', 'prism-gruvbox-dark', 'prism-gruvbox-light',
        'prism-material-dark', 'prism-material-light', 'prism-material-oceanic',
        'prism-nord', 'prism-night-owl', 'prism-shades-of-purple',
        'prism-dracula', 'prism-atom-dark', 'prism-base16-ateliersulphurpool.light',
        'prism-cb', 'prism-duotone-dark', 'prism-duotone-earth', 'prism-duotone-forest',
        'prism-duotone-light', 'prism-duotone-sea', 'prism-duotone-space',
        'prism-ghcolors', 'prism-hopscotch', 'prism-pojoaque', 'prism-vs',
        'prism-xonokai', 'prism-z-touch'
    ]

    import urllib.request
    import os

    os.makedirs(PRISM_DIR, exist_ok=True)
    downloaded = 0

    # Download official themes
    for theme in official_themes:
        cache_file = os.path.join(PRISM_DIR, f"theme-{theme}.css")
        if not os.path.exists(cache_file):
            try:
                theme_url = f"https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/themes/{theme}.min.css"
                print(f"Downloading official theme: {theme}")
                with urllib.request.urlopen(theme_url) as response:
                    theme_css = response.read().decode('utf-8')

                with open(cache_file, 'w', encoding='utf-8') as f:
                    f.write(theme_css)
                downloaded += 1
            except Exception as e:
                print(f"Failed to download {theme}: {e}")

    # Download prism-themes repository themes
    for theme in prism_themes:
        cache_file = os.path.join(PRISM_DIR, f"theme-{theme}.css")
        if not os.path.exists(cache_file):
            try:
                # prism-themes uses different URL structure
                theme_name = theme.replace('prism-', '')
                theme_url = f"https://cdn.jsdelivr.net/npm/prism-themes@1.9.0/themes/{theme}.css"
                print(f"Downloading prism-themes: {theme}")
                with urllib.request.urlopen(theme_url) as response:
                    theme_css = response.read().decode('utf-8')

                with open(cache_file, 'w', encoding='utf-8') as f:
                    f.write(theme_css)
                downloaded += 1
            except Exception as e:
                print(f"Failed to download {theme}: {e}")

    print(
        f"Downloaded {downloaded} new themes. All themes are now cached locally!")
    print(f"Total available themes: {len(official_themes + prism_themes)}")
    print("Popular editor themes now available: one-dark, gruvbox-dark, gruvbox-light, material-dark, nord, night-owl, dracula")


def add_universal_section_folding(html_content, default_collapsed_sections=None, is_dark_theme=False):
    """
    Simple section folding using JavaScript DOM manipulation instead of complex HTML parsing.
    This avoids breaking existing HTML structure and code blocks.

    Args:
        html_content (str): HTML content with headers
        default_collapsed_sections (list): Section titles that start collapsed (default: ["Solution"])
        is_dark_theme (bool): Whether to apply dark theme to code blocks (default: False)

    Returns:
        str: HTML content with collapsible sections added via JavaScript
    """
    if default_collapsed_sections is None:
        default_collapsed_sections = ["Solution", "Answer"]

    # Convert collapsed sections list to JavaScript array
    collapsed_sections_js = str(default_collapsed_sections).replace("'", '"')

    # Add JavaScript that will process the DOM after page load
    folding_script = f'''

    <script>
    document.addEventListener('DOMContentLoaded', function() {{
        const collapsedSections = {collapsed_sections_js};
        const isDarkTheme = {str(is_dark_theme).lower()};

        // Apply dark theme only to pre code blocks if needed
        if (isDarkTheme) {{
            const codeBlocks = document.querySelectorAll('pre');
            codeBlocks.forEach(function(pre) {{
                pre.classList.add('dark-theme');
            }});
        }}

        // Check table widths and apply reduced padding if they exceed 70% of content width
        const markdownBody = document.querySelector('.markdown-body');
        const contentWidth = 700; // markdown-body width is 700px
        const threshold = contentWidth * 0.7; // 70% = 490px

        const tables = document.querySelectorAll('.markdown-body table');
        tables.forEach(function(table) {{
            // Force table layout to calculate natural width
            table.style.width = 'auto';

            // Get the actual rendered width of the table
            const tableWidth = table.getBoundingClientRect().width;

            if (tableWidth > threshold) {{
                // Table exceeds 70% of content width, reduce padding
                const ths = table.querySelectorAll('th');
                const tds = table.querySelectorAll('td');

                ths.forEach(function(th) {{
                    th.style.padding = '12px 20px';
                }});

                tds.forEach(function(td) {{
                    td.style.padding = '11px 20px';
                }});
            }}
        }});

        // Find all headers h2-h6
        const headers = document.querySelectorAll('.markdown-body h2, .markdown-body h3, .markdown-body h4, .markdown-body h5, .markdown-body h6');

        headers.forEach(function(header, index) {{
            // Skip headers inside code blocks
            if (header.closest('pre, code')) {{
                return;
            }}

            const level = parseInt(header.tagName.substring(1));
            const text = header.textContent;
            const sectionId = 'section-' + index;

            // Check if this section should be collapsed by default (exact match only)
            const isCollapsed = collapsedSections.some(section =>
                text.toLowerCase().trim() === section.toLowerCase().trim()
            );

            // Create wrapper div for the header
            const headerDiv = document.createElement('div');
            headerDiv.className = 'section-collapsible-header ' + (isCollapsed ? 'collapsed' : 'expanded');
            headerDiv.onclick = function() {{ toggleSection(sectionId); }};

            // Create collapse icon
            const icon = document.createElement('span');
            icon.className = 'collapse-icon';
            icon.innerHTML = '⌄';

            // Replace header with wrapped version
            header.parentNode.insertBefore(headerDiv, header);
            headerDiv.appendChild(header);
            headerDiv.appendChild(icon);

            // Create content div and collect content until next same-level header
            const contentDiv = document.createElement('div');
            contentDiv.className = 'section-collapsible-content ' + (isCollapsed ? 'collapsed' : 'expanded');
            contentDiv.id = sectionId;

            let nextElement = headerDiv.nextElementSibling;
            while (nextElement) {{
                // Stop at next header of same or higher level
                if (nextElement.tagName && nextElement.tagName.match(/^H[1-6]$/)) {{
                    const nextLevel = parseInt(nextElement.tagName.substring(1));
                    if (nextLevel <= level) {{
                        break;
                    }}
                }}

                const elementToMove = nextElement;
                nextElement = nextElement.nextElementSibling;
                contentDiv.appendChild(elementToMove);
            }}

            // Insert content div after header
            headerDiv.parentNode.insertBefore(contentDiv, headerDiv.nextElementSibling);
        }});
    }});

    function toggleSection(sectionId) {{
        const content = document.getElementById(sectionId);
        const header = content.previousElementSibling;

        if (content.classList.contains('collapsed')) {{
            content.classList.remove('collapsed');
            content.classList.add('expanded');
            header.classList.remove('collapsed');
            header.classList.add('expanded');
        }} else {{
            content.classList.remove('expanded');
            content.classList.add('collapsed');
            header.classList.remove('expanded');
            header.classList.add('collapsed');
        }}
    }}
    </script>'''

    return html_content + folding_script


def convert_md_to_html_block_based(md_file_path, css_file_path='style.css', prism_theme='prism', line_numbers=False, collapse_lines=10, inline_lang='python', foldable_sections=None, boxed_math=True, choice_options=False, mermaid=False):
    """
    Converts a Markdown file to HTML using unit-based block rendering for stability.

    This approach processes markdown in hierarchical blocks separately to prevent
    formatting errors in one section from corrupting the entire document.

    Args:
        md_file_path (str): Path to the input Markdown file.
        css_file_path (str, optional): Path to a custom CSS file. Defaults to 'style.css'.
        prism_theme (str, optional): Prism.js theme name. Defaults to 'prism'.
        line_numbers (bool, optional): Enable line numbers in code blocks. Defaults to False.
        collapse_lines (int, optional): Auto-collapse code blocks longer than this many lines. Defaults to 10.
        inline_lang (str, optional): Language for highlighting inline code. Defaults to 'python'.

    Returns:
        str: A complete HTML document as a string.
    """
    # --- 0. Handle theme aliases ---
    theme_aliases = {
        'one-dark': 'prism-one-dark',
        'gruvbox-dark': 'prism-gruvbox-dark',
        'gruvbox-light': 'prism-gruvbox-light',
        'material-dark': 'prism-material-dark',
        'material-light': 'prism-material-light',
        'material-oceanic': 'prism-material-oceanic',
        'nord': 'prism-nord',
        'night-owl': 'prism-night-owl',
        'dracula': 'prism-dracula',
        'atom-dark': 'prism-atom-dark',
        'dark': 'prism-dark',
        'okaidia': 'prism-okaidia',
        'tomorrow': 'prism-tomorrow',
        'twilight': 'prism-twilight',
        'coy': 'prism-coy',
        'solarizedlight': 'prism-solarizedlight',
        'funky': 'prism-funky'
    }

    # Convert short names to full prism theme names
    if prism_theme in theme_aliases:
        prism_theme = theme_aliases[prism_theme]

    # Determine if this is a dark theme
    dark_themes = [
        'prism-one-dark', 'prism-gruvbox-dark', 'prism-material-dark', 'prism-nord',
        'prism-night-owl', 'prism-dracula', 'prism-atom-dark', 'prism-dark',
        'prism-okaidia', 'prism-twilight', 'prism-material-oceanic', 'prism-tomorrow'
    ]
    is_dark_theme = prism_theme in dark_themes

    # --- 1. Load Markdown file & preprocess pre code blocks to ensure ``` paired ---
    try:
        with open(md_file_path, 'r', encoding='utf-8') as f:
            md_text = f.read()
    except FileNotFoundError:
        print(f"Error: Input Markdown file not found at '{md_file_path}'")
        sys.exit(1)

    md_text = process_pre_code_blocks(md_text)

    # Load all CSS and JS resources
    custom_css = ""
    try:
        with open(css_file_path, 'r', encoding='utf-8') as f:
            custom_css = f.read()
    except FileNotFoundError:
        print(f"Warning: Custom CSS file not found at '{css_file_path}'. Proceeding without it.")

    # Load cached resources
    prism_js_content = ""
    try:
        with open(os.path.join(PRISM_DIR, 'prism.js'), 'r', encoding='utf-8') as f:
            prism_js_content = f.read()
    except FileNotFoundError:
        print(f"Warning: Local prism.js not found. Using fallback CDN approach.")

    callouts_js_content = ""
    try:
        with open(os.path.join(PRISM_DIR, 'callouts.js'), 'r', encoding='utf-8') as f:
            callouts_js_content = f.read()
    except FileNotFoundError:
        print(f"Warning: Local callouts.js not found. Callouts functionality will not be available.")

    prism_theme_css = ""
    cache_file = os.path.join(PRISM_DIR, f"theme-{prism_theme}.css")
    try:
        with open(cache_file, 'r', encoding='utf-8') as f:
            prism_theme_css = f.read()
    except FileNotFoundError:
        print(f"Warning: Theme '{prism_theme}' not found in cache.")

    # Load modern CSS frameworks
    normalize_css = ""
    modern_base_css = ""
    mobile_responsive_css = ""

    try:
        with open(os.path.join(PRISM_DIR, 'normalize.css'), 'r', encoding='utf-8') as f:
            normalize_css = f.read()
    except FileNotFoundError:
        pass

    try:
        with open(os.path.join(PRISM_DIR, 'modern-base.css'), 'r', encoding='utf-8') as f:
            modern_base_css = f.read()
    except FileNotFoundError:
        pass

    try:
        with open(os.path.join(PRISM_DIR, 'mobile-responsive.css'), 'r', encoding='utf-8') as f:
            mobile_responsive_css = f.read()
    except FileNotFoundError:
        pass

    # Configure line numbers
    if line_numbers:
        line_numbers_css = '<link href="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/plugins/line-numbers/prism-line-numbers.min.css" rel="stylesheet" />'
        body_class = ' class="line-numbers"'
    else:
        line_numbers_css = ''
        body_class = ''

    # --- 2. UNIT-BASED BLOCK PROCESSING ---

    # Step 1: Parse markdown into hierarchical blocks
    blocks = parse_markdown_blocks(md_text)

    # Step 2: Create conversion function with all preprocessing
    def convert_block_content(block_content):
        """Convert a single block's markdown content to HTML with full pipeline."""
        import re

        # Apply table formatting fixes
        lines = block_content.split('\n')
        # ... (table formatting code would go here, simplified for now)

        # Protect math expressions from corruption
        def protect_math_expressions(text):
            protected_math = []
            protected_code = []

            def protect_code(match):
                protected_code.append(match.group(0))
                return f"CODEPROTECT{len(protected_code)-1}CODEPROTECT"

            def protect_math(match):
                full_expression = match.group(0)
                protected_math.append(full_expression)
                return f"MATHEXPR{len(protected_math)-1}MATHEXPR"

            # Protect inline code first (single backticks) - but skip content inside code blocks
            def protect_inline_code_smartly(text):
                from fence_utils import get_fence_info
                lines = text.split('\n')
                result_lines = []
                in_code_block = False

                for line_num, line in enumerate(lines, 1):
                    # Check if we're entering or exiting a code block
                    if is_valid_code_fence(line, in_code_block):
                        in_code_block = not in_code_block
                        # Don't process fence lines themselves for inline code
                        result_lines.append(line)
                    elif in_code_block:
                        # Inside code block - don't process inline code
                        result_lines.append(line)
                    else:
                        # Outside code block - check for invalid standalone fences and process inline code
                        stripped = line.strip()

                        # Check for invalid standalone fences (outside code blocks)
                        if stripped.startswith('```'):
                            fence_info = get_fence_info(line)
                            if fence_info and not fence_info['is_valid']:
                                # Invalid fence found outside code block - add warning
                                print(f"⚠️  WARNING: Invalid fence: {repr(line)}")
                                print(f"   Reason: {fence_info['type']} fence with invalid format")

                                # Replace invalid fence with warning callout HTML directly
                                warning_html = f'''<div class="callout is-open" data-callout="warning">
    <div class="callout-title">
        <div class="callout-icon"></div>
        Invalid Code Fence
        <div class="callout-fold"></div>
    </div>
    <div class="callout-content">
        <code class="language-python">{line.strip()}</code>
    </div>
</div>

'''
                                # Add the warning with proper blank line separation
                                result_lines.append(warning_html.rstrip())
                                result_lines.append("")  # Force blank line after warning
                            else:
                                # Valid fence or not a fence at all
                                processed_line = re.sub(r'`[^`\n]+?`', protect_code, line)
                                result_lines.append(processed_line)
                        else:
                            # Regular line - process inline code normally
                            processed_line = re.sub(r'`[^`\n]+?`', protect_code, line)
                            result_lines.append(processed_line)

                return '\n'.join(result_lines)

            temp_text = protect_inline_code_smartly(text)

            # Protect code blocks (triple backticks) with proper fence validation
            def protect_valid_code_blocks(text):
                lines = text.split('\n')
                result_lines = []
                in_code_block = False
                current_block_lines = []

                for line in lines:
                    # Check if this line contains a valid code fence using unified function
                    is_fence = is_valid_code_fence(line, in_code_block)

                    if is_fence:
                        if in_code_block:
                            # End of code block - protect the entire block
                            current_block_lines.append(line)
                            block_content = '\n'.join(current_block_lines)
                            protected_code.append(block_content)
                            result_lines.append(f"CODEPROTECT{len(protected_code)-1}CODEPROTECT")
                            in_code_block = False
                            current_block_lines = []
                        else:
                            # Start of code block
                            in_code_block = True
                            current_block_lines = [line]
                    elif in_code_block:
                        current_block_lines.append(line)
                    else:
                        result_lines.append(line)

                return '\n'.join(result_lines)

            temp_text = protect_valid_code_blocks(temp_text)

            # FIRST: Preprocess multiline display math to single line format
            # Convert: $$\n content \n$$ -> $$content$$
            temp_text = re.sub(r'\$\$\s*\n(.+?)\n\s*\$\$', r'$$\1$$', temp_text, flags=re.DOTALL)
            # Convert: \[\n content \n\] -> \[content\]
            temp_text = re.sub(r'\\\[\s*\n(.+?)\n\s*\\\]', r'\\[\1\\]', temp_text, flags=re.DOTALL)

            # Process standalone boxed math expressions (if enabled)
            if boxed_math:
                temp_text = process_standalone_boxed_math(temp_text)

            # Protect math expressions
            # Order matters: protect $$ before $ to avoid conflicts
            temp_text = re.sub(r'\$\$(.+?)\$\$', protect_math, temp_text, flags=re.DOTALL)
            temp_text = re.sub(r'\\\[(.+?)\\\]', protect_math, temp_text, flags=re.DOTALL)
            temp_text = re.sub(r'\\\((.+?)\\\)', protect_math, temp_text)
            # Protect inline math $...$ (must come after $$ to avoid conflicts)
            temp_text = re.sub(r'\$([^$\n]+?)\$', protect_math, temp_text)

            # Process standalone math environments (after basic math protection, before code restoration)
            temp_text = process_standalone_math_envs(temp_text, protected_math)

            # Convert LaTeX lists to Markdown (while code is still protected)
            temp_text = convert_latex_lists_to_markdown(temp_text)

            # Restore protected code
            def restore_code(match):
                index = int(match.group(1))
                return protected_code[index]

            temp_text = re.sub(r'CODEPROTECT(\d+)CODEPROTECT', restore_code, temp_text)

            return temp_text, protected_math

        temp_content, protected_math = protect_math_expressions(block_content)

        # Convert to HTML using mistune
        from mistune.toc import add_toc_hook
        mistune_md = mistune.create_markdown(
            escape=False,
            plugins=['strikethrough', 'table', 'footnotes', 'task_lists'],
            renderer=mistune.HTMLRenderer(escape=False)
        )
        add_toc_hook(mistune_md, min_level=1, max_level=6)

        html_content, state = mistune_md.parse(temp_content)

        # Replace \\command with \command (but preserve legitimate double backslashes)
        def fix_latex_commands(text):
            # This pattern looks for double backslashes followed by a LaTeX command
            pattern = r'\\\\([a-zA-Z]+)(?=\s|$|[^a-zA-Z])'
            corrected = re.sub(pattern, r'\\\1', text)
            return corrected

        # Restore protected math and escape HTML characters
        def restore_math(match):
            index = int(match.group(1))
            math_content = protected_math[index]
            # Escape < and > characters in math expressions to prevent HTML parsing issues
            escaped_math = math_content.replace('<', '&lt;').replace('>', '&gt;')
            # Fix \\ in LaTeX command to \ in math expressions
            escaped_math = fix_latex_commands(escaped_math)
            return escaped_math

        html_content = re.sub(r'MATHEXPR(\d+)MATHEXPR', restore_math, html_content)

        return html_content

    # Step 3: Process each block safely in isolation with global TOC counter
    successful_blocks = 0
    failed_blocks = 0
    all_toc_items = []  # Collect all TOC items from all blocks
    global_toc_counter = {'count': 0}  # Mutable counter shared across all blocks

    def process_block_recursively(block):
        """Process a block and all its children recursively."""
        nonlocal successful_blocks, failed_blocks, all_toc_items

        # Process this block
        success = process_block_safely(block, convert_block_content)
        if success:
            successful_blocks += 1
            # Fix TOC IDs to be globally unique
            block.html = fix_toc_ids_globally(block.html, global_toc_counter)

            # Extract TOC items from this block's HTML if it has headers
            import re
            header_matches = re.findall(r'<h([1-6])[^>]*id="([^"]+)"[^>]*>([^<]+)</h[1-6]>', block.html)
            for level, anchor, title in header_matches:
                all_toc_items.append((int(level), anchor, title.strip()))
            # For block debug usage
            # print("------------------------------------------------------------")
            # print(f"Sucessfully to process block")
            # print("------------------------------------------------------------")
            # print(f"{block.content}")
            # print()
        else:
            failed_blocks += 1
            print("------------------------------------------------------------")
            print(f"⚠️ Failed to process block")
            print("------------------------------------------------------------")
            print(f"{block.content}")
            print()

        # Process all children
        for child in block.children:
            process_block_recursively(child)

    # Process all root blocks
    for root_block in blocks:
        process_block_recursively(root_block)

    # Step 4: Reassemble processed blocks into final HTML
    html_body = reassemble_processed_blocks(blocks)

    # Convert toc_N IDs to user-specified slugs from markdown links
    html_body = convert_toc_ids_to_slugs(html_body, all_toc_items, md_text)

    # Update toc_items with the new slugs for TOC generation
    updated_toc_items = update_toc_items_with_new_anchors(html_body, all_toc_items)

    # Generate and insert TOC only if [TOC] appears as standalone line
    if has_standalone_toc_marker(md_text):
        html_body = generate_and_insert_toc(html_body, updated_toc_items, md_text)

    # --- 3. Apply post-processing ---

    # Process Obsidian-style callouts (> [!TYPE] format)
    html_body = process_obsidian_callouts(html_body)

    # Add Topic/Thumbnail admonitions
    html_body = add_topic_thumbnail_admonitions(html_body)

    # Process choice options (A. B. C. D.) if enabled
    if choice_options:
        html_body = process_choice_options(html_body)

    # Process Mermaid diagrams if enabled
    if mermaid:
        html_body = process_mermaid_diagrams(html_body)

    # Apply collapsible code blocks
    if collapse_lines:
        html_body = wrap_long_code_blocks(html_body, collapse_lines)

    # Add section folding
    if foldable_sections is not None:
        html_body = add_universal_section_folding(html_body, foldable_sections, is_dark_theme)

    # Handle JSON highlighting
    html_body = html_body.replace('class="language-json"', 'class="language-javascript"')

    # Add inline code highlighting
    if inline_lang:
        def add_inline_lang(match):
            code_content = match.group(1)
            highlight_lang = "javascript" if inline_lang == "json" else inline_lang
            return f'<code class="language-{highlight_lang}">{code_content}</code>'

        html_body = re.sub(r'(?<!<pre>)<code>([^<]+)</code>', add_inline_lang, html_body)

    # Extract title
    title = md_file_path.split('/')[-1].split('.')[0].replace('_', ' ').title()
    if '<h1>' in html_body:
        title = html_body.split('<h1>')[1].split('</h1>')[0]

    # Add TOC CSS only if [TOC] appears as standalone line
    if has_standalone_toc_marker(md_text):
        try:
            with open(os.path.join(PRISM_DIR, 'mistune_toc.css'), 'r', encoding='utf-8') as toc_file:
                custom_css += toc_file.read()
        except FileNotFoundError:
            print("⚠️  TOC CSS file not found. Skipping toc css style customization.")

    # Add choice options CSS if enabled
    if choice_options:
        choice_options_css = """
/* Choice Options Styling - Simple with padding */
.choice-option {
    margin: 2px 0 !important;
    padding: 0 0 0 0.5em !important;
    background: none !important;
    border: none !important;
    font-size: inherit !important;
    line-height: inherit !important;
}

.choice-option strong {
    font-weight: bold !important;
    margin-right: 4px !important;
}
"""
        custom_css += choice_options_css

    # Add Mermaid CSS if enabled
    mermaid_js = ""
    if mermaid:
        mermaid_css = """
/* Mermaid Diagram Styling */
.mermaid-diagram {
    width: 100%;
    <!-- display: flex; -->
    justify-content: center;
    align-items: center;
    margin: 20px 0;
    padding: 15px;
    background: #f8f9fa;
    border: 1px solid #e9ecef;
    border-radius: 8px;
    text-align: center;
}

.mermaid-diagram svg {
    max-width: 100%;
    height: auto;
}
"""
        custom_css += mermaid_css

        # Add Mermaid.js script
        mermaid_js = """
    <!-- Mermaid.js for Diagram Rendering -->
    <script src="https://cdn.jsdelivr.net/npm/mermaid@10.6.1/dist/mermaid.min.js"></script>
    <script>
        mermaid.initialize({
            startOnLoad: true,
            theme: 'default',
            securityLevel: 'loose'
        });

        // Initialize diagrams after page load
        document.addEventListener('DOMContentLoaded', function() {
            mermaid.init(undefined, '.mermaid-diagram');
        });
    </script>
"""

    # --- 4. Generate final HTML ---
    final_html = HTML_TEMPLATE.format(
        title=title,
        custom_css=custom_css,
        html_body=html_body,
        prism_theme=prism_theme,
        prism_theme_css=prism_theme_css,
        normalize_css=normalize_css,
        modern_base_css=modern_base_css,
        mobile_responsive_css=mobile_responsive_css,
        line_numbers_css=line_numbers_css,
        body_class=body_class,
        prism_js_content=prism_js_content,
        callouts_js_content=callouts_js_content,
        mermaid_js=mermaid_js
    )

    # Report processing statistics
    total_blocks = successful_blocks + failed_blocks
    if failed_blocks > 0:
        print(f"⚠️  Block processing: {successful_blocks}/{total_blocks} successful, {failed_blocks} failed")
    else:
        print(f"✅ All {total_blocks} blocks processed successfully")

    return final_html


def convert_md_to_html(md_file_path, css_file_path='style.css', prism_theme='prism', line_numbers=False, collapse_lines=10, inline_lang='python', foldable_sections=None, boxed_math=True, choice_options=True, mermaid=True):
    """
    Converts a Markdown file to a full HTML document with styling.

    This is the main entry point that uses the new unit-based block rendering
    architecture for improved stability and error isolation.

    Args:
        md_file_path (str): Path to the input Markdown file.
        css_file_path (str, optional): Path to a custom CSS file. Defaults to 'style.css'.
        prism_theme (str, optional): Prism.js theme name. Defaults to 'prism'.
        line_numbers (bool, optional): Enable line numbers in code blocks. Defaults to False.
        collapse_lines (int, optional): Auto-collapse code blocks longer than this many lines. Defaults to 10.
        inline_lang (str, optional): Language for highlighting inline code. Defaults to 'python'.

    Returns:
        str: A complete HTML document as a string.
    """
    # Use the new block-based rendering system
    return convert_md_to_html_block_based(
        md_file_path, css_file_path, prism_theme, line_numbers,
        collapse_lines, inline_lang, foldable_sections, boxed_math, choice_options, mermaid
    )


def main():
    """Main function to handle command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Convert a Markdown file to a styled HTML document.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("input_file", nargs='?',
                        help="Path to the input Markdown file (.md).")
    parser.add_argument("output_file", nargs='?',
                        help="Path for the output HTML file (.html). If not provided, uses input filename with .html extension.")
    parser.add_argument(
        "--css",
        default=os.path.join(PRISM_DIR, "style.css"),
        help="Path to a custom CSS file to include (default: style.css)."
    )
    parser.add_argument(
        "--theme",
        default="prism",
        help="Prism.js theme for code highlighting.\nShort names: gruvbox-dark, one-dark, nord, dracula, material-dark, atom-dark, etc.\nFull names: prism-gruvbox-dark, prism-one-dark, prism-nord, prism, prism-solarizedlight, etc.\nDefault: prism."
    )
    parser.add_argument(
        "--line-numbers",
        action="store_true",
        help="Enable line numbers in code blocks."
    )
    parser.add_argument(
        "--collapse",
        type=int,
        default=50,
        metavar="N",
        help="Auto-collapse code blocks longer than N lines into collapsible sections (default: 10). Use 0 to disable."
    )
    parser.add_argument(
        "--download-themes",
        action="store_true",
        help="Download and cache all Prism themes for offline use, then exit."
    )
    parser.add_argument(
        "--inline-lang",
        default="python",
        help="Language for highlighting inline code (default: python). Use 'none' to disable inline code highlighting."
    )
    parser.add_argument(
        "--fold-sections",
        nargs='*',
        default=None,  # Use None as default to distinguish from empty list
        help="Section titles to make foldable (default: ['Solution']). Use --fold-sections without arguments for default sections, or provide specific section names."
    )
    parser.add_argument(
        "--no-boxed-math",
        dest='boxed_math',
        action='store_false',
        help="Disable standalone \\boxed{...} math rendering"
    )
    parser.set_defaults(boxed_math=True)  # default ON
    parser.add_argument(
        "--no-choice-options",
        dest="choice_options",
        action='store_false',
        help="Disable rendering choice options A. B. C.,  A) B) C) as separate lines"
    )
    parser.set_defaults(choice_options=True)  # default ON
    parser.add_argument(
        "--no-mermaid",
        dest="mermaid",
        action="store_false",
        help="Disable Mermaid diagram rendering")
    parser.set_defaults(mermaid=True)  # default ON

    args = parser.parse_args()
    # from pathlib import Path
    # args.input_file = r"F:\SciencePedia\topic_book_generation\workspace\docs\可控核聚变_job.md"
    # args.output_file = Path(r"F:\SciencePedia\topic_book_generation\workspace\output\html\可控核聚变\可控核聚变_job.html")
    
    # Handle download themes command
    if args.download_themes:
        download_all_prism_themes()
        return

    # Ensure input file is provided for conversion
    if not args.input_file:
        parser.error("input_file is required unless using --download-themes")

    # Determine output filename
    if args.output_file:
        output_file = args.output_file
    else:
        from pathlib import Path
        input_path = Path(args.input_file)
        output_file = input_path.stem + '.html'

    # Perform conversion
    inline_lang = None if args.inline_lang.lower() == 'none' else args.inline_lang
    collapse_lines = None if args.collapse == 0 else args.collapse
    # Handle fold-sections argument properly
    if args.fold_sections == []:  # Empty list when --fold-sections used without args - use default
        foldable_sections = ["Solution"]  # Use the default value
    elif args.fold_sections is None:  # Not provided at all - use default sections
        foldable_sections = ["Solution"]  # Enable by default
    else:  # Non-empty list - use as provided
        foldable_sections = args.fold_sections
    full_html = convert_md_to_html(args.input_file, args.css, args.theme,
                                   args.line_numbers, collapse_lines, inline_lang, foldable_sections, args.boxed_math, args.choice_options, args.mermaid)

    # Write to output file
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(full_html)
        print(
            f"✅ Successfully converted '{args.input_file}' to '{output_file}'")
    except IOError as e:
        print(f"Error: Could not write to output file '{output_file}'.\n{e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
