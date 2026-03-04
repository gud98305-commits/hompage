import os

target_dir = r"C:\Users\hyeon\Desktop\hompage\0227 test"
output_file = os.path.join(target_dir, "project_homepage.md")

exclude_dirs = {
    'node_modules', '.next', '__pycache__', 'pycache', '.git',
    'build', 'dist', 'venv', '.venv', 'env', '.env',
    'crawler', '.claude', 'tmp'
}
exclude_files = {
    'temp_extract_homepage.py', 'project_homepage.md',
    'package-lock.json', 'yarn.lock'
}
target_exts = {
    '.py', '.js', '.jsx', '.ts', '.tsx',
    '.html', '.css', '.json', '.env', '.md', '.txt', '.toml', '.cfg', '.yaml', '.yml'
}

def is_target_file(filename):
    if filename in exclude_files:
        return False
    if filename.startswith('.') and filename not in {'.env.example', '.env'}:
        return False
    ext = os.path.splitext(filename)[1].lower()
    if ext == '.json' and any(x in filename.lower() for x in ['lock', 'package-lock']):
        return False
    return ext in target_exts

tree_lines = []
file_contents = []

def walk(path, prefix=""):
    try:
        entries = sorted(os.listdir(path))
    except PermissionError:
        return
    dirs = [e for e in entries if os.path.isdir(os.path.join(path, e)) and e not in exclude_dirs and not e.startswith('.')]
    files = [e for e in entries if os.path.isfile(os.path.join(path, e))]
    all_entries = dirs + files
    for i, entry in enumerate(all_entries):
        full = os.path.join(path, entry)
        is_last = (i == len(all_entries) - 1)
        connector = "└── " if is_last else "├── "
        tree_lines.append(f"{prefix}{connector}{entry}")
        if os.path.isdir(full):
            walk(full, prefix + ("    " if is_last else "│   "))
        elif is_target_file(entry):
            rel = os.path.relpath(full, target_dir).replace('\\', '/')
            ext = os.path.splitext(entry)[1][1:] or ''
            ext_map = {'py':'python','js':'javascript','jsx':'javascript','ts':'typescript','tsx':'typescript','html':'html','css':'css','json':'json','yaml':'yaml','yml':'yaml','toml':'toml'}
            lang = ext_map.get(ext, ext)
            try:
                with open(full, 'r', encoding='utf-8') as f:
                    content = f.read()
                file_contents.append(f"\n### `{rel}`\n\n```{lang}\n{content}\n```\n")
            except Exception as e:
                file_contents.append(f"\n### `{rel}`\n\n```\nError: {e}\n```\n")

walk(target_dir)

with open(output_file, 'w', encoding='utf-8') as f:
    f.write("# 홈페이지 프로젝트 구조 및 소스 코드\n\n")
    f.write("## 폴더 트리\n```text\n")
    f.write('\n'.join(tree_lines))
    f.write("\n```\n\n## 소스 코드\n")
    f.write('\n'.join(file_contents))

print(f"완료: {len(file_contents)}개 파일 → {output_file}")
