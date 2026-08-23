import os, sys

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.enums import TA_LEFT

    path = r'D:\PYTHON\WORK_RESEARCHER_MCP\CV_collection\Cover_Letter_Geophysical_Logging.pdf'
    body = ParagraphStyle('Body', parent=getSampleStyleSheet()['Normal'], fontSize=10, leading=14, alignment=TA_LEFT, spaceAfter=6)

    txt_path = r'D:\PYTHON\WORK_RESEARCHER_MCP\CV_collection\Cover_Letter_Geophysical_Logging.txt'
    with open(txt_path, 'r', encoding='utf-8') as f:
        text = f.read()

    story = []
    for line in text.split('\n'):
        if line.strip() == '':
            story.append(Spacer(1, 6))
        else:
            story.append(Paragraph(line, body))

    doc = SimpleDocTemplate(path, pagesize=A4, topMargin=15*mm, bottomMargin=15*mm, leftMargin=20*mm, rightMargin=20*mm)
    doc.build(story)
    sys.stdout.write(f'exists: {os.path.exists(path)} size: {os.path.getsize(path)}\n')
    sys.stdout.flush()
except Exception as e:
    sys.stdout.write(f'ERROR: {e}\n')
    sys.stdout.flush()
