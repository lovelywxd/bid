"""图片提取工具 - 从 DOCX/PDF/PPTX 中提取图片"""
import os

def extract_images_from_docx(docx_path, output_dir='output/images'):
    from docx import Document
    doc = Document(docx_path)
    basename = os.path.splitext(os.path.basename(docx_path))[0]
    extracted = []
    for i, rel in enumerate(doc.part.rels.values()):
        if "image" in rel.reltype:
            img_data = rel.target_part.blob
            ext = os.path.splitext(rel.target_ref)[1] or '.png'
            filename = f"{basename}_img{i}{ext}"
            filepath = os.path.join(output_dir, filename)
            with open(filepath, 'wb') as f:
                f.write(img_data)
            extracted.append({'file': filename, 'source': docx_path, 'index': i})
    return extracted

def extract_images_from_pptx(pptx_path, output_dir='output/images'):
    from pptx import Presentation
    from pptx.enum.shapes import MSO_SHAPE_TYPE
    prs = Presentation(pptx_path)
    basename = os.path.splitext(os.path.basename(pptx_path))[0]
    extracted = []
    img_count = 0
    for slide_num, slide in enumerate(prs.slides, 1):
        for shape in slide.shapes:
            if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
                img = shape.image
                ext = img.content_type.split('/')[-1]
                if ext == 'jpeg': ext = 'jpg'
                filename = f"{basename}_slide{slide_num}_img{img_count}.{ext}"
                filepath = os.path.join(output_dir, filename)
                with open(filepath, 'wb') as f:
                    f.write(img.blob)
                extracted.append({
                    'file': filename, 'source': pptx_path,
                    'slide': slide_num,
                    'title': slide.shapes.title.text if slide.shapes.title else ''
                })
                img_count += 1
    return extracted

def extract_images_from_pdf(pdf_path, output_dir='output/images'):
    from PyPDF2 import PdfReader
    reader = PdfReader(pdf_path)
    basename = os.path.splitext(os.path.basename(pdf_path))[0]
    extracted = []
    img_count = 0
    for page_num, page in enumerate(reader.pages, 1):
        if '/XObject' not in (page.get('/Resources') or {}):
            continue
        xobjects = page['/Resources']['/XObject'].get_object()
        for obj_name in xobjects:
            obj = xobjects[obj_name].get_object()
            if obj.get('/Subtype') == '/Image':
                ext = 'png'
                if obj.get('/Filter') == '/DCTDecode': ext = 'jpg'
                elif obj.get('/Filter') == '/JPXDecode': ext = 'jp2'
                filename = f"{basename}_p{page_num}_img{img_count}.{ext}"
                filepath = os.path.join(output_dir, filename)
                try:
                    with open(filepath, 'wb') as f:
                        f.write(obj.get_data())
                    extracted.append({'file': filename, 'source': pdf_path, 'page': page_num})
                    img_count += 1
                except Exception:
                    pass
    return extracted
