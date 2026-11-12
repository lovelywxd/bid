"""章节合并与目录生成 - 将分章 Word 文件合并为完整文档"""
from docx import Document
from docx.shared import Pt
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from docx.enum.text import WD_ALIGN_PARAGRAPH
import glob, re, os

def merge_chapters(output_dir='output', final_name='技术标_完整版.docx'):
    chapter_files = sorted(
        glob.glob(os.path.join(output_dir, '第*章_*.docx')),
        key=lambda x: int(re.search(r'第(\d+)章', os.path.basename(x)).group(1))
    )
    if not chapter_files:
        print("未找到章节文件")
        return None

    merged = Document(chapter_files[0])
    for chapter_file in chapter_files[1:]:
        merged.add_page_break()
        sub_doc = Document(chapter_file)
        for element in sub_doc.element.body:
            merged.element.body.append(element)

    output_path = os.path.join(output_dir, final_name)
    merged.save(output_path)
    print(f"已合并 {len(chapter_files)} 个章节 -> {output_path}")
    return output_path

def add_toc(doc):
    """在文档开头插入自动目录域代码"""
    toc_title = doc.add_paragraph()
    toc_title.text = '目  录'
    toc_title.alignment = 1
    run = toc_title.runs[0]
    run.font.size = Pt(22)
    run.font.name = '黑体'
    run._element.rPr.rFonts.set(qn('w:eastAsia'), '黑体')
    run.bold = True
    doc.element.body.insert(0, toc_title._element)

    p = doc.add_paragraph()
    run = p.add_run()
    fldChar1 = OxmlElement('w:fldChar')
    fldChar1.set(qn('w:fldCharType'), 'begin')
    run._element.append(fldChar1)
    run2 = p.add_run()
    instrText = OxmlElement('w:instrText')
    instrText.set(qn('xml:space'), 'preserve')
    instrText.text = ' TOC \\o "1-4" \\h \\z \\u '
    run2._element.append(instrText)
    run3 = p.add_run()
    fldChar2 = OxmlElement('w:fldChar')
    fldChar2.set(qn('w:fldCharType'), 'end')
    run3._element.append(fldChar2)
    doc.element.body.insert(1, p._element)

    pb = doc.add_paragraph()
    pb_run = pb.add_run()
    br = OxmlElement('w:br')
    br.set(qn('w:type'), 'page')
    pb_run._element.append(br)
    doc.element.body.insert(2, pb._element)

def add_header_footer(doc, header_text='技术标', project_name=''):
    for section in doc.sections:
        hp = section.header.paragraphs[0]
        hp.text = f"{project_name} {header_text}"
        hp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for run in hp.runs:
            run.font.size = Pt(9)
            run.font.name = '仿宋'

        fp = section.footer.paragraphs[0]
        fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = fp.add_run()
        fldChar1 = run._element.makeelement(qn('w:fldChar'), {qn('w:fldCharType'): 'begin'})
        run._element.append(fldChar1)
        run2 = fp.add_run()
        instrText = run2._element.makeelement(qn('w:instrText'), {})
        instrText.text = 'PAGE'
        run2._element.append(instrText)
        run3 = fp.add_run()
        fldChar2 = run3._element.makeelement(qn('w:fldChar'), {qn('w:fldCharType'): 'end'})
        run3._element.append(fldChar2)

if __name__ == '__main__':
    import sys
    output_dir = sys.argv[1] if len(sys.argv) > 1 else 'output'
    merge_chapters(output_dir)
