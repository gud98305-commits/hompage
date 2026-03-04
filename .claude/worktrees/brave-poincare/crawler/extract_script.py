import os

# Configuration
ROOT_DIR = r"c:\Users\hyeon\Downloads\0227 test\0227 test"
OUTPUT_FILE = r"C:\Users\hyeon\.gemini\antigravity\brain\a34ac514-0d7a-4533-b6fe-eafc033ece97\project_analysis.md"

EXCLUDE_DIRS = {
    'node_modules', '.next', '.vercel', 'build', 'dist', '.git', 
    'images', '__MACOSX', '.venv', '__pycache__'
}

TARGET_EXTENSIONS = {'.ts', '.tsx', '.js', '.jsx', '.html', '.css', '.mjs'}
# .json is handled separately, as well as .env.example

LARGE_DATA_EXTENSIONS = {'.json', '.csv', '.sqlite', '.db', '.png', '.jpg', '.jpeg', '.gif', '.svg'}

def is_source_file(filename):
    if filename == '.env.example':
        return True
    ext = os.path.splitext(filename)[1].lower()
    if ext in TARGET_EXTENSIONS:
        return True
    if ext == '.json':
        name = filename.lower()
        if 'package' in name or 'config' in name:
            return True
    return False

def get_tree(dir_path, prefix=""):
    entries = sorted(os.listdir(dir_path))
    entries = [e for e in entries if e not in EXCLUDE_DIRS]
    
    tree_str = ""
    for i, entry in enumerate(entries):
        path = os.path.join(dir_path, entry)
        is_last = (i == len(entries) - 1)
        connector = "└── " if is_last else "├── "
        tree_str += prefix + connector + entry + "\n"
        
        if os.path.isdir(path):
            extension = "    " if is_last else "│   "
            tree_str += get_tree(path, prefix + extension)
            
    return tree_str

def format_size(size):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"

def main():
    tree_structure = f"## 📁 프로젝트 폴더 트리\n```text\n0227 test\n{get_tree(ROOT_DIR)}```\n\n"
    
    source_codes = []
    large_files = []
    
    for root, dirs, files in os.walk(ROOT_DIR):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        
        for file in files:
            path = os.path.join(root, file)
            rel_path = os.path.relpath(path, ROOT_DIR)
            ext = os.path.splitext(file)[1].lower()
            
            # Check for large data file or excluded json
            if ext == '.json':
                name = file.lower()
                if 'package' not in name and 'config' not in name:
                    size = os.path.getsize(path)
                    large_files.append((rel_path, size))
                    continue
            if ext in LARGE_DATA_EXTENSIONS and not is_source_file(file):
                 size = os.path.getsize(path)
                 large_files.append((rel_path, size))
                 continue
                 
            # If it's a source file we want
            if is_source_file(file):
                size = os.path.getsize(path)
                if size > 100 * 1024:  # >100KB might be generated
                    pass
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    lang = ext.replace('.', '')
                    if lang == 'mjs': lang = 'js'
                    if file == '.env.example': lang = 'env'
                    
                    block = f"### 📄 `{rel_path}`\n```{lang}\n{content}\n```\n\n"
                    source_codes.append(block)
                except Exception as e:
                    print(f"Error reading {rel_path}: {e}")
            elif ext not in {'.py', '.txt', '.toml', '.zip', '.md'}: # Maybe add other binaries if needed
                # we track unknown large/binaries just in case
                pass
                
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as out:
        out.write("# 홈페이지 프로젝트 분석 문서\n\n")
        out.write(tree_structure)
        
        out.write("## 📦 대용량 데이터 파일 목록 (크롤링 데이터, JSON 등)\n")
        if large_files:
            out.write("| 파일 경로 | 용량 |\n| --- | --- |\n")
            for fpath, size in sorted(large_files):
                out.write(f"| `{fpath}` | {format_size(size)} |\n")
        else:
            out.write("대용량 데이터 파일이 없습니다.\n")
        out.write("\n\n---\n\n## 📝 소스 코드\n\n")
        
        for code in source_codes:
            out.write(code)

if __name__ == "__main__":
    main()
