import os
import sys
import glob

def main():
    project_root = os.environ.get('PIXI_PROJECT_ROOT')
    conda_prefix = os.environ.get('CONDA_PREFIX')

    if not conda_prefix:
        return

    # Fallback logic for project_root
    if not project_root:
        # Check if we are in a pixi project by looking for pixi.toml in CWD
        cwd = os.getcwd()
        if os.path.exists(os.path.join(cwd, 'pixi.toml')):
            project_root = cwd
    
    if not project_root:
        # Still not found, give up
        return

    config_file = os.path.join(project_root, 'pyocd.yaml')
    packs_dir = os.path.join(conda_prefix, 'packs')
    
    # Find packs
    packs = glob.glob(os.path.join(packs_dir, '*.pack'))
    packs = [os.path.normpath(p) for p in packs]

    if not packs:
        return

    # Prepare the block content
    block_start = "# BEGIN PIXI PACKS"
    block_end = "# END PIXI PACKS"
    
    new_block_lines = [block_start + "\n"]
    new_block_lines.append("pack:\n")
    for pack in packs:
        # Use forward slashes for yaml compatibility even on Windows if possible, 
        # but os.path.normpath helps. Yaml handles / fine on windows usually.
        # Let's stick to standard path separators for the OS to be safe, 
        # but ensure consistent indentation.
        new_block_lines.append(f"  - {pack}\n")
    new_block_lines.append(block_end + "\n")


    mode = 'r' if os.path.exists(config_file) else 'w+'
    
    lines = []
    if os.path.exists(config_file):
        with open(config_file, 'r') as f:
            lines = f.readlines()

    # Check for existing block
    start_idx = -1
    end_idx = -1
    
    for i, line in enumerate(lines):
        if line.strip() == block_start:
            start_idx = i
        if line.strip() == block_end:
            end_idx = i
            
    if start_idx != -1 and end_idx != -1:
        # Replace existing block
        lines[start_idx:end_idx+1] = new_block_lines
    else:
        # Append new block
        if lines and not lines[-1].endswith('\n'):
            lines[-1] += '\n'
        lines.extend(new_block_lines)

    with open(config_file, 'w') as f:
        f.writelines(lines)

if __name__ == "__main__":
    main()
