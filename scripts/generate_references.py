"""
Documentation Generator.
Scans the codebase using AST to extract docstrings and builds the `scriptReferences.md` map.
"""
import os
import ast
import argparse

def get_docstring_summary(docstring):
    """Extracts the first line or summary from a docstring."""
    if not docstring:
        return ""
    lines = docstring.strip().split('\n')
    summary = lines[0].strip()
    return summary

def analyze_file(filepath, rel_path):
    """Parses a Python file and returns a summary of its contents."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            code = f.read()
            tree = ast.parse(code)
    except Exception as e:
        return f"| {rel_path} | (Error parsing: {e}) |"

    # File Docstring
    file_doc = ast.get_docstring(tree)
    file_summary = get_docstring_summary(file_doc)
    
    # Classes and Functions
    details = []
    
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            cls_doc = get_docstring_summary(ast.get_docstring(node))
            details.append(f"  - `class {node.name}`: {cls_doc}")
            # Methods? (Maybe too detailed for high-level map, keeping it simple for now)
        elif isinstance(node, ast.FunctionDef):
            func_doc = get_docstring_summary(ast.get_docstring(node))
            details.append(f"  - `def {node.name}`: {func_doc}")

    content = f"| **[{rel_path}]({rel_path})** | {file_summary} |\n"
    if details:
        content += "| | " + "<br>".join(details) + " |\n"
    
    return content

def main():
    parser = argparse.ArgumentParser(description="Generate scriptReferences.md")
    parser.add_argument("--root", default=".", help="Root directory to scan")
    parser.add_argument("--output", default="scriptReferences.md", help="Output file")
    args = parser.parse_args()

    root_dir = os.path.abspath(args.root)
    output_lines = [
        "# Codebase Map (scriptReferences)",
        "",
        "This file is auto-generated. It provides a high-level overview of the available modules and scripts.",
        "**Agent Instruction:** Use this map to locate relevant functionality before falling back to global search.",
        "",
        "| File / Module | Description / Contents |",
        "| :--- | :--- |"
    ]

    # Dirs to include
    include_dirs = ['toolbox/bin', 'toolbox/services', 'toolbox/lib', 'plaud', 'toolbox/scripts', 'setup/scripts', 'toolbox/n8n']
    # Files to exclude (common noise)
    exclude_files = ['__init__.py', 'setup.py']

    for include_dir in include_dirs:
        abs_include_dir = os.path.join(root_dir, include_dir)
        if not os.path.exists(abs_include_dir):
            continue

        for root, dirs, files in os.walk(abs_include_dir):
            # Skip hidden dirs and venvs
            dirs[:] = [d for d in dirs if not d.startswith('.') and 'venv' not in d and 'pycache' not in d]
            
            for file in sorted(files):
                if file.endswith(".py") and file not in exclude_files:
                    filepath = os.path.join(root, file)
                    rel_path = os.path.relpath(filepath, root_dir)
                    
                    entry = analyze_file(filepath, rel_path)
                    output_lines.append(entry)

    with open(args.output, 'w', encoding='utf-8') as f:
        f.write("\n".join(output_lines))
    
    print(f"Generated {args.output} with {len(output_lines)-6} entries.")

if __name__ == "__main__":
    main()
