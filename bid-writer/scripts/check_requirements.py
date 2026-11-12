"""废标检查 - 对照实质性要求逐条检查响应状态"""
import json

def check_mandatory_requirements(requirements_path='output/requirements.json'):
    with open(requirements_path, 'r', encoding='utf-8') as f:
        reqs = json.load(f)
    results = []
    for req in reqs.get('mandatory_requirements', []):
        results.append({
            'id': req['id'],
            'content': req['content'],
            'status': '待检查',
            'location': ''
        })
    return results

if __name__ == '__main__':
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else 'output/requirements.json'
    for r in check_mandatory_requirements(path):
        print(f"[{r['status']}] {r['id']}: {r['content']}")
