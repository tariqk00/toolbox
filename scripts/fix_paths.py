
import os
import re

PATH_BLOCK = """
import sys
import os
# Add repo root to path
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO_ROOT not in sys.path:
    sys.path.append(REPO_ROOT)
"""

def fix_file(filepath):
    with open(filepath, 'r') as f:
        content = f.read()
    
    # Heuristic: Find where sys.path is appended and replace/inject
    # Many variants. Easier to just inject at top after 'import os' if not present?
    # Or replace existing sys.path lines.
    
    lines = content.splitlines()
    new_lines = []
    has_path_fix = False
    skip_next = False
    
    for i, line in enumerate(lines):
        if skip_next:
            skip_next = False
            continue
            
        if "from toolbox.lib" in line or "from toolbox.services" in line:
             if not has_path_fix:
                 new_lines.append("# --- Path Setup ---")
                 new_lines.append("REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))")
                 new_lines.append("if REPO_ROOT not in sys.path:")
                 new_lines.append("    sys.path.append(REPO_ROOT)")
                 new_lines.append("# ------------------")
                 has_path_fix = True
             new_lines.append(line)
             continue

        # Remove old path logic
        if "sys.path.append" in line and "google-drive" in line:
            continue
        if "repo_root =" in line and "dirname" in line:
            continue
        if "sys.path.append(repo_root)" in line:
             continue
        if "current_dir =" in line and "dirname" in line:
             # Be careful not to delete legitimate uses, but usually strictly for path setup in these scripts
             pass
        
        # Keep other lines
        new_lines.append(line)
        
    # Re-assemble
    # Logic is brittle. Better: just search for imports and prepend path block if missing.
    # Prune known bad lines.
    
    # 2nd pass: Prune bad lines from original content
    clean_lines = []
    for line in lines:
         if "sys.path.append" in line and "google-drive" in line: continue
         if "sys.path.append" in line and "repo_root" in line: continue
         if "repo_root =" in line: continue
         if "current_dir =" in line and "dirname" in line and "abspath" in line: continue 
         clean_lines.append(line)
         
    # Inject patch at top
    # Find last import
    last_import_idx = 0
    for i, line in enumerate(clean_lines):
        if line.startswith("import ") or line.startswith("from "):
            last_import_idx = i
            
    # Actually, inject BEFORE "from toolbox..." imports
    # But AFTER "import os/sys"
    
    final_lines = []
    injected = False
    
    for line in clean_lines:
        if (line.startswith("from toolbox") or line.startswith("from drive_organizer")) and not injected:
            final_lines.append(PATH_BLOCK)
            injected = True
        final_lines.append(line)
        
    if not injected:
         # Prepend to start if no toolbox imports found (unlikely for our targets)
         final_lines.insert(0, PATH_BLOCK)

    new_content = "\n".join(final_lines)
    
    # Remove duplicate imports of sys/os if PATH_BLOCK adds them
    # PATH_BLOCK has import sys, os.
    # If file already has them, it's fine (python handles dupes).
    
    with open(filepath, 'w') as f:
        f.write(new_content)
    print(f"Patched {filepath}")

def main():
    d = 'toolbox/bin'
    if not os.path.exists(d): return
    for root, _, files in os.walk(d):
        for file in files:
            if file.endswith('.py'):
                fix_file(os.path.join(root, file))

if __name__ == "__main__":
    main()
