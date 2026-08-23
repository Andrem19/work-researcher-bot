import os, sys

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.enums import TA_LEFT, TA_JUSTIFY
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

path = r'D:\PYTHON\WORK_RESEARCHER_MCP\CV_collection\Cover_Letter_Geophysical_Logging.pdf'

styles = getSampleStyleSheet()
header = ParagraphStyle('Header', parent=styles['Normal'], fontSize=12, leading=16, alignment=TA_LEFT, spaceAfter=2, fontName='Helvetica-Bold')
body = ParagraphStyle('Body', parent=styles['Normal'], fontSize=11, leading=16, alignment=TA_JUSTIFY, spaceAfter=8)
title = ParagraphStyle('Title', parent=styles['Normal'], fontSize=14, leading=19, alignment=TA_LEFT, spaceAfter=10, fontName='Helvetica-Bold')
section = ParagraphStyle('Section', parent=styles['Normal'], fontSize=11, leading=16, alignment=TA_LEFT, spaceAfter=6, fontName='Helvetica-Bold')

story = []

# Header
story.append(Paragraph('Andrew Remniow', header))
story.append(Paragraph('Blackpool, UK &nbsp;|&nbsp; +44 7838 228012 &nbsp;|&nbsp; 7255591@gmail.com &nbsp;|&nbsp; Full UK Driving Licence &amp; Own Vehicle', body))
story.append(Spacer(1, 12))

# Date
story.append(Paragraph('23 August 2026', body))
story.append(Spacer(1, 12))

# Recipient
story.append(Paragraph('Ernest Gordon Recruitment', body))
story.append(Paragraph('Re: Graduate/Trainee Field Service Engineer (Geophysical Logging) &mdash; Llandudno (LL30)', section))
story.append(Spacer(1, 12))

# Salutation
story.append(Paragraph('Dear Hiring Manager,', body))
story.append(Spacer(1, 6))

# Body paragraphs
story.append(Paragraph(
    'I am writing to express my strong interest in the Graduate/Trainee Field Service Engineer position in Geophysical Logging. '
    'With a BSc in Geology (UK NARIC: RQF Level 6) and hands-on field experience in engineering geology, I am confident that my '
    'background aligns well with the requirements of this role and that I can make a meaningful contribution to your team from day one.',
    body))

story.append(Paragraph('Relevant Field Experience', section))
story.append(Paragraph(
    'My field experience includes borehole supervision, trial pits, soil and rock sampling, core and cuttings handling, '
    'groundwater observations and basic lithological logging. I have supported geotechnical laboratory operations and '
    'maintained accurate field records, daily logs and factual summaries throughout my work. This directly relates to the '
    'geophysical logging work your team undertakes, and I am familiar with the disciplined, safety-focused approach '
    'required for borehole and wellsite operations. I am accustomed to working in variable outdoor conditions and '
    'maintaining high standards of data quality and operational safety at all times.',
    body))

story.append(Paragraph('Readiness for Field-Based and Travel-Intensive Work', section))
story.append(Paragraph(
    'I hold a full UK driving licence and my own vehicle, and I am fully prepared and enthusiastic about field-based, '
    'travel-intensive work. I am comfortable with rotational work patterns, onshore assignments and extended periods '
    'away from home. My HSE awareness and safety mindset are central to how I operate in the field, and I am confident '
    'working in physically demanding and variable environments. I understand that geophysical logging often requires '
    'working at remote wellsite locations, sometimes on extended rotations, and I am fully committed to this type of '
    'work schedule. I am reliable, punctual and able to maintain focus and accuracy during long field shifts.',
    body))

story.append(Paragraph('Additional Technical Skills', section))
story.append(Paragraph(
    'In addition to my geoscience background, I bring strong digital skills including Python scripting, SQL and PostgreSQL, '
    'and advanced Excel. These support data handling, report generation and QA/QC processes, complementing the '
    'technical and analytical demands of geophysical data collection and interpretation. I am comfortable working with '
    'structured data, producing clear and accurate documentation, and automating repetitive reporting tasks. My '
    'experience with structured record-keeping and QA/QC from both geological field operations and software '
    'development gives me a strong foundation for the data-intensive aspects of geophysical logging.',
    body))

story.append(Paragraph('Motivation and Commitment', section))
story.append(Paragraph(
    'As a trainee candidate, I am eager to undergo the extensive training you offer and to develop into a skilled '
    'field service engineer. I learn quickly, adapt well to new environments and equipment, and am motivated to build '
    'a long-term career in geophysical logging. I am a British citizen with an unrestricted right to work in the UK '
    'and am available to start at short notice. I am based in Blackpool but am fully mobile and willing to travel to '
    'Llandudno or any other base location as required for field operations.',
    body))

story.append(Paragraph(
    'I would welcome the opportunity to discuss how my background, field experience and enthusiasm can contribute to '
    'your team. I am available for an interview at your convenience and can be reached on +44 7838 228012 or by email '
    'at 7255591@gmail.com. Thank you for considering my application. I look forward to hearing from you.',
    body))

story.append(Spacer(1, 12))
story.append(Paragraph('Yours sincerely,', body))
story.append(Spacer(1, 20))
story.append(Paragraph('Andrew Remniow', header))

doc = SimpleDocTemplate(path, pagesize=A4, topMargin=18*mm, bottomMargin=18*mm, leftMargin=22*mm, rightMargin=22*mm,
    title='Cover Letter - Andrew Remniow - Geophysical Logging',
    author='Andrew Remniow',
    subject='Application for Graduate/Trainee Field Service Engineer (Geophysical Logging)')
doc.build(story)

sys.stdout.write(f'exists: {os.path.exists(path)} size: {os.path.getsize(path)}\n')
sys.stdout.flush()
