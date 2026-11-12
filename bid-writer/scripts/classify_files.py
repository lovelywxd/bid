"""文件发现与分类脚本 - 扫描项目目录，按关键词启发式分类"""
import os, json, sys

EXCLUDE_DIRS = {'.venv', 'output', '__pycache__', '.git', '.claude'}
EXTENSIONS = {'.doc', '.docx', '.pdf', '.pptx', '.xlsx'}

RULES = {
    'tender': ['招标', '招选', '采购', '磋商', '询价', '比选'],
    'historical': ['标书', '投标', '技术响应', '模板', '标准投标'],
    'product': ['产品', '功能', '从小白到精通', '用户手册', '操作指南'],
    'solution': ['方案', '解决方案', '课件', '领域', '领先方案']
}

def classify_files(root_dir):
    result = {k: [] for k in RULES}
    result['unclassified'] = []
    for dirpath, dirnames, filenames in os.walk(root_dir):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for f in filenames:
            ext = os.path.splitext(f)[1].lower()
            if ext not in EXTENSIONS:
                continue
            full_path = os.path.join(dirpath, f)
            rel_path = os.path.relpath(full_path, root_dir)
            size_mb = os.path.getsize(full_path) / (1024*1024)
            classified = False
            for category, keywords in RULES.items():
                if any(kw in rel_path for kw in keywords):
                    result[category].append({'path': rel_path, 'size_mb': round(size_mb,1), 'ext': ext})
                    classified = True
                    break
            if not classified:
                result['unclassified'].append({'path': rel_path, 'size_mb': round(size_mb,1), 'ext': ext})
    return result

if __name__ == '__main__':
    root = sys.argv[1] if len(sys.argv) > 1 else '.'
    manifest = classify_files(root)
    os.makedirs('output', exist_ok=True)
    with open('output/file_manifest.json', 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
