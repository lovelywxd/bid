"""文件读取工具 - 支持 .doc/.docx/.pdf/.pptx 多格式读取"""
import os, sys

def read_doc_via_com(doc_path):
    """使用 Word COM 对象读取 .doc 文件（仅 Windows）"""
    import win32com.client
    word = win32com.client.Dispatch('Word.Application')
    word.Visible = False
    doc = word.Documents.Open(os.path.abspath(doc_path))
    text = doc.Content.Text
    doc.Close()
    word.Quit()
    return text

def read_docx_chapter(docx_path, target_h1_text, max_chars=50000):
    """按 H1 标题提取单章内容，避免加载整个文件到上下文"""
    from docx import Document
    doc = Document(docx_path)
    capturing = False
    content = []
    total_chars = 0
    for para in doc.paragraphs:
        is_h1 = (para.style.name == 'Heading 1' or
                 (para.text.strip().startswith('第') and '章' in para.text))
        if is_h1:
            if capturing:
                break
            if target_h1_text in para.text:
                capturing = True
        if capturing:
            text = para.text.strip()
            if text:
                content.append(text)
                total_chars += len(text)
                if total_chars > max_chars:
                    content.append('...[内容截断，请按需继续读取]...')
                    break
    return '\n'.join(content)

def read_pdf_pages(pdf_path, start_page=0, num_pages=15):
    """按页码范围读取 PDF"""
    from PyPDF2 import PdfReader
    reader = PdfReader(pdf_path)
    texts = []
    end = min(start_page + num_pages, len(reader.pages))
    for i in range(start_page, end):
        texts.append(f"--- 第{i+1}页 ---\n{reader.pages[i].extract_text()}")
    return '\n'.join(texts)

def read_pptx_slides(pptx_path, start=0, count=8):
    """按幻灯片范围读取 PPTX"""
    from pptx import Presentation
    prs = Presentation(pptx_path)
    texts = []
    for i, slide in enumerate(prs.slides[start:start+count], start=start+1):
        slide_text = []
        for shape in slide.shapes:
            if shape.has_text_frame:
                slide_text.append(shape.text_frame.text)
        texts.append(f"--- 幻灯片{i} ---\n" + '\n'.join(slide_text))
    return '\n'.join(texts)

def safe_read_strategy(file_path):
    """根据文件大小返回推荐的读取策略: full/chapter/targeted"""
    size_mb = os.path.getsize(file_path) / (1024 * 1024)
    if size_mb < 5:
        return 'full'
    elif size_mb < 50:
        return 'chapter'
    else:
        return 'targeted'
