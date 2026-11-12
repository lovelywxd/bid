"""标题树提取 - 从 docx 文件提取标题层级结构"""
from docx import Document

def extract_heading_tree(docx_path):
    doc = Document(docx_path)
    headings = []
    for para in doc.paragraphs:
        if para.style.name.startswith('Heading'):
            level = int(para.style.name.replace('Heading ', ''))
            headings.append({'level': level, 'text': para.text.strip()})
        elif para.text.strip() and any(
            para.text.strip().startswith(p) for p in
            ['第', '一、', '二、', '三、', '（一）', '（二）', '1.', '2.', '1、', '2、']
        ):
            text = para.text.strip()
            if text.startswith('第') and '章' in text:
                level = 1
            elif any(text.startswith(c) for c in ['一、','二、','三、','四、','五、','六、','七、','八、','九、','十']):
                level = 2
            elif text.startswith('（') and '）' in text[:5]:
                level = 3
            elif text[0].isdigit() and ('.' in text[:4] or '、' in text[:4]):
                level = 4
            else:
                continue
            headings.append({'level': level, 'text': text})
    return headings

if __name__ == '__main__':
    import sys, json
    if len(sys.argv) > 1:
        tree = extract_heading_tree(sys.argv[1])
        print(json.dumps(tree, ensure_ascii=False, indent=2))
