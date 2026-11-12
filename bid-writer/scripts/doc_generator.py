"""Word 文档生成工具 - 创建标准标书格式的 Word 文档"""
from docx import Document
from docx.shared import Pt, Cm, Inches, RGBColor, Emu
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml.ns import qn, nsdecls
from docx.oxml import parse_xml

HEADING_CONFIG = {
    1: {'size': Pt(22), 'bold': True, 'font': '黑体',  'before': Pt(24), 'after': Pt(12), 'align': WD_ALIGN_PARAGRAPH.CENTER},
    2: {'size': Pt(16), 'bold': True, 'font': '黑体',  'before': Pt(18), 'after': Pt(6),  'align': WD_ALIGN_PARAGRAPH.LEFT},
    3: {'size': Pt(14), 'bold': True, 'font': '仿宋',  'before': Pt(12), 'after': Pt(6),  'align': WD_ALIGN_PARAGRAPH.LEFT},
    4: {'size': Pt(12), 'bold': True, 'font': '仿宋',  'before': Pt(6),  'after': Pt(3),  'align': WD_ALIGN_PARAGRAPH.LEFT},
}

def create_doc():
    """创建带标准标书格式的空文档"""
    doc = Document()

    # A4 纸张 + 页边距
    for section in doc.sections:
        section.page_width = Cm(21.0)
        section.page_height = Cm(29.7)
        section.top_margin = Cm(2.54)
        section.bottom_margin = Cm(2.54)
        section.left_margin = Cm(3.17)
        section.right_margin = Cm(3.17)

    # 正文样式：仿宋小四，首行缩进2字符，1.5倍行距
    style = doc.styles['Normal']
    style.font.name = '仿宋'
    style.font.size = Pt(12)
    style.element.rPr.rFonts.set(qn('w:eastAsia'), '仿宋')
    pf = style.paragraph_format
    pf.line_spacing = 1.5
    pf.first_line_indent = Pt(24)  # 首行缩进2字符
    pf.space_before = Pt(0)
    pf.space_after = Pt(0)

    # 标题样式
    for level, cfg in HEADING_CONFIG.items():
        hs = doc.styles[f'Heading {level}']
        hs.font.size = cfg['size']
        hs.font.bold = cfg['bold']
        hs.font.name = cfg['font']
        hs.element.rPr.rFonts.set(qn('w:eastAsia'), cfg['font'])
        hs.font.color.rgb = RGBColor(0, 0, 0)
        hpf = hs.paragraph_format
        hpf.space_before = cfg['before']
        hpf.space_after = cfg['after']
        hpf.first_line_indent = Pt(0)  # 标题不缩进
        hpf.alignment = cfg['align']
    return doc

def add_para(doc, text, indent=True):
    """添加正文段落，默认首行缩进"""
    p = doc.add_paragraph(text.strip())
    for run in p.runs:
        run.font.name = '仿宋'
        run.font.size = Pt(12)
        run._element.rPr.rFonts.set(qn('w:eastAsia'), '仿宋')
    if not indent:
        p.paragraph_format.first_line_indent = Pt(0)
    return p

def add_table(doc, data):
    """添加表格，表头加粗居中带底色，单元格垂直居中，五号字"""
    rows, cols = len(data), len(data[0])
    table = doc.add_table(rows=rows, cols=cols, style='Table Grid')
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, row_data in enumerate(data):
        for j, cell_text in enumerate(row_data):
            cell = table.cell(i, j)
            cell.text = str(cell_text)
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
            for p in cell.paragraphs:
                p.paragraph_format.first_line_indent = Pt(0)
                p.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER if i == 0 else WD_ALIGN_PARAGRAPH.LEFT
                p.paragraph_format.space_before = Pt(2)
                p.paragraph_format.space_after = Pt(2)
                for run in p.runs:
                    run.font.name = '仿宋'
                    run.font.size = Pt(10.5)
                    run._element.rPr.rFonts.set(qn('w:eastAsia'), '仿宋')
                    if i == 0:
                        run.bold = True
            if i == 0:
                shading = parse_xml(f'<w:shd {nsdecls("w")} w:fill="D9E2F3"/>')
                cell._tc.get_or_add_tcPr().append(shading)
    return table
