#!/usr/bin/env python3
"""
Demo script comparing Python markdown library vs mistune library
Shows their different capabilities and output formats
"""

import sys
import subprocess

def install_packages_if_needed():
    """Install required packages if not available"""
    packages_to_check = ['markdown', 'mistune']
    
    for package in packages_to_check:
        try:
            __import__(package)
        except ImportError:
            print(f"Installing {package}...")
            try:
                subprocess.run([
                    sys.executable, "-m", "pip", "install", 
                    package, "--break-system-packages"
                ], check=True, capture_output=True)
                print(f"✅ {package} installed successfully")
            except subprocess.CalledProcessError:
                print(f"❌ Failed to install {package}")
                return False
    return True

def demo_markdown_libraries(markdown_file):
    """Demo both markdown libraries with content from input file"""
    
    if not install_packages_if_needed():
        print("Failed to install required packages")
        return
    
    # Import after installation
    import markdown
    import mistune
    from pathlib import Path
    
    # Read input markdown file
    try:
        with open(markdown_file, 'r', encoding='utf-8') as f:
            test_markdown = f.read()
        print(f"📖 Read markdown file: {markdown_file}")
        print(f"📏 Input size: {len(test_markdown)} characters")
    except FileNotFoundError:
        print(f"❌ File not found: {markdown_file}")
        return
    except Exception as e:
        print(f"❌ Error reading file: {e}")
        return
    
    # Get base filename for outputs
    input_path = Path(markdown_file)
    base_name = input_path.stem  # filename without extension

    print("MARKDOWN VS MISTUNE COMPARISON")
    print("=" * 60)
    
    # Python markdown library
    print("\\n🔸 PYTHON MARKDOWN LIBRARY")
    print("-" * 40)
    
    try:
        # Create markdown instance with extensions
        md = markdown.Markdown(
            extensions=[
                'codehilite',
                'fenced_code', 
                'tables',
                'toc'
            ],
            extension_configs={
                'codehilite': {
                    'css_class': 'highlight',
                    'use_pygments': True
                }
            }
        )
        
        markdown_html = md.convert(test_markdown)
        
        print(f"✅ Successfully converted with Python markdown")
        print(f"📏 Output length: {len(markdown_html)} characters")
        
        # Check for specific features
        features_markdown = {
            'Tables': '<table>' in markdown_html,
            'Code highlighting': 'class="highlight"' in markdown_html or 'class="language-' in markdown_html,
            'Nested lists': '<ul>' in markdown_html and '<li>' in markdown_html,
            'LaTeX math': '$' in markdown_html,
            'Bold formatting': '<strong>' in markdown_html or '<b>' in markdown_html
        }
        
        print("📋 Features detected:")
        for feature, detected in features_markdown.items():
            status = "✅" if detected else "❌"
            print(f"  {status} {feature}")
            
    except Exception as e:
        print(f"❌ Python markdown failed: {e}")
        markdown_html = None
        features_markdown = {}

    # Mistune library  
    print("\\n🔹 MISTUNE LIBRARY")
    print("-" * 40)
    
    try:
        # Create mistune instance
        mistune_md = mistune.create_markdown(
            escape=False,
            plugins=[
                'strikethrough', 
                'table',
                'footnotes',
                'task_lists'
            ]
        )
        
        mistune_html = mistune_md(test_markdown)
        
        print(f"✅ Successfully converted with mistune")
        print(f"📏 Output length: {len(mistune_html)} characters")
        
        # Check for specific features
        features_mistune = {
            'Tables': '<table>' in mistune_html,
            'Code highlighting': 'class="language-' in mistune_html or '<code class=' in mistune_html,
            'Nested lists': '<ul>' in mistune_html and '<li>' in mistune_html,
            'LaTeX math': '$' in mistune_html,
            'Bold formatting': '<strong>' in mistune_html or '<b>' in mistune_html
        }
        
        print("📋 Features detected:")
        for feature, detected in features_mistune.items():
            status = "✅" if detected else "❌"
            print(f"  {status} {feature}")
            
    except Exception as e:
        print(f"❌ Mistune failed: {e}")
        mistune_html = None
        features_mistune = {}

    # Comparison
    print("\\n📊 FEATURE COMPARISON")
    print("-" * 40)
    
    if markdown_html and mistune_html:
        all_features = set(features_markdown.keys()) | set(features_mistune.keys())
        
        print(f"{'Feature':<20} {'Markdown':<10} {'Mistune':<10}")
        print("-" * 40)
        
        for feature in sorted(all_features):
            md_status = "✅" if features_markdown.get(feature, False) else "❌"
            mt_status = "✅" if features_mistune.get(feature, False) else "❌"
            print(f"{feature:<20} {md_status:<10} {mt_status:<10}")
        
        # Size comparison
        print(f"\\n📏 SIZE COMPARISON")
        print(f"Markdown output: {len(markdown_html):,} characters")
        print(f"Mistune output:  {len(mistune_html):,} characters")
        
        if len(mistune_html) < len(markdown_html):
            reduction = ((len(markdown_html) - len(mistune_html)) / len(markdown_html)) * 100
            print(f"Mistune is {reduction:.1f}% more compact")
        elif len(mistune_html) > len(markdown_html):
            increase = ((len(mistune_html) - len(markdown_html)) / len(markdown_html)) * 100
            print(f"Mistune is {increase:.1f}% larger")
        else:
            print("Both outputs are the same size")

    # Save outputs for inspection using requested naming convention
    markdown_output_file = f"{base_name}_markdown.html"
    mistune_output_file = f"{base_name}_mistune.html"
    
    if markdown_html:
        with open(markdown_output_file, 'w', encoding='utf-8') as f:
            f.write(f"""<!DOCTYPE html>
<html>
<head>
    <title>Python Markdown Output - {base_name}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; line-height: 1.6; }}
        .highlight {{ background: #f8f8f8; padding: 10px; border-radius: 4px; }}
        pre {{ background: #f8f8f8; padding: 10px; border-radius: 4px; overflow-x: auto; }}
        table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #f2f2f2; }}
        code {{ background: #f1f1f1; padding: 2px 4px; border-radius: 3px; }}
        blockquote {{ border-left: 4px solid #ddd; margin: 0; padding-left: 20px; }}
        h1, h2, h3, h4, h5, h6 {{ color: #333; }}
    </style>
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
      "HTML-CSS": {{ 
        linebreaks: {{ automatic: true }},
        scale: 90
      }}
    }});
    </script>
    <script type="text/javascript" async
      src="https://cdnjs.cloudflare.com/ajax/libs/mathjax/2.7.7/MathJax.js?config=TeX-MML-AM_CHTML">
    </script>
</head>
<body>
<h1>Python Markdown Library Output</h1>
<p><strong>Source:</strong> {markdown_file}</p>
<hr>
{markdown_html}
</body>
</html>""")
        print(f"\\n💾 Saved Python markdown output to: {markdown_output_file}")

    if mistune_html:
        with open(mistune_output_file, 'w', encoding='utf-8') as f:
            f.write(f"""<!DOCTYPE html>
<html>
<head>
    <title>Mistune Output - {base_name}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; line-height: 1.6; }}
        pre {{ background: #f8f8f8; padding: 10px; border-radius: 4px; overflow-x: auto; }}
        table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #f2f2f2; }}
        code {{ background: #f1f1f1; padding: 2px 4px; border-radius: 3px; }}
        blockquote {{ border-left: 4px solid #ddd; margin: 0; padding-left: 20px; }}
        h1, h2, h3, h4, h5, h6 {{ color: #333; }}
    </style>
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
      "HTML-CSS": {{ 
        linebreaks: {{ automatic: true }},
        scale: 90
      }}
    }});
    </script>
    <script type="text/javascript" async
      src="https://cdnjs.cloudflare.com/ajax/libs/mathjax/2.7.7/MathJax.js?config=TeX-MML-AM_CHTML">
    </script>
</head>
<body>
<h1>Mistune Library Output</h1>
<p><strong>Source:</strong> {markdown_file}</p>
<hr>
{mistune_html}
</body>
</html>""")
        print(f"💾 Saved mistune output to: {mistune_output_file}")

    print(f"\\n🎉 Demo complete! Compare outputs:")
    print(f"  Python markdown: {markdown_output_file}")
    print(f"  Mistune:         {mistune_output_file}")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python3 demo_markdown_vs_mistune.py <markdown_file>")
        print("Example: python3 demo_markdown_vs_mistune.py sample.md")
        print("\\nOutput files: <filename>_markdown.html and <filename>_mistune.html")
        sys.exit(1)
    
    markdown_file = sys.argv[1]
    demo_markdown_libraries(markdown_file)