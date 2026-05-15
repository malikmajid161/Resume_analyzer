"""
PDF Generator for Resume Builder
Produces a clean, professional resume PDF from user-inputted data.
"""

import io
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)

def generate_resume_pdf(data: dict) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1.5*cm, leftMargin=1.5*cm,
        topMargin=1.5*cm, bottomMargin=1.5*cm,
    )

    styles = getSampleStyleSheet()
    story = []

    accent_color = colors.HexColor(data.get('accentColor', '#4f46e5'))
    text_color = colors.HexColor("#1e293b")
    muted_color = colors.HexColor("#64748b")

    # ── Styles ──────────────────────────────────
    name_style = ParagraphStyle(
        "name", parent=styles["Title"],
        textColor=accent_color, fontSize=28, spaceAfter=2, alignment=1 if data.get('template') == 'executive' else 0
    )
    contact_style = ParagraphStyle(
        "contact", parent=styles["Normal"],
        textColor=muted_color, fontSize=9, spaceAfter=12, alignment=1 if data.get('template') == 'executive' else 0
    )
    section_title_style = ParagraphStyle(
        "section_title", parent=styles["Heading2"],
        textColor=accent_color, fontSize=12, spaceBefore=12, spaceAfter=6,
        textTransform='uppercase', borderPadding=(0, 0, 2, 0),
        borderWidth=0, borderStyle=None
    )
    
    # ── Header ──────────────────────────────────
    story.append(Paragraph(data.get('fullName', 'Your Name'), name_style))
    contact_info = f"{data.get('email', '')}  |  {data.get('phone', '')}  |  {data.get('linkedin', '')}"
    story.append(Paragraph(contact_info, contact_style))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#f1f5f9")))
    story.append(Spacer(1, 0.5*cm))

    # ── Professional Summary ─────────────────────
    if data.get('summary'):
        story.append(Paragraph("Professional Summary", section_title_style))
        story.append(Paragraph(data['summary'], styles["Normal"]))
        story.append(Spacer(1, 0.4*cm))

    # ── Work Experience ──────────────────────────
    experience = data.get('experience', [])
    if experience:
        story.append(Paragraph("Experience", section_title_style))
        for exp in experience:
            if not exp.get('title') and not exp.get('company'): continue
            exp_header = Paragraph(f"<b>{exp.get('title', 'Job Title')}</b>", styles["Normal"])
            exp_sub = Paragraph(f"<font color='#64748b'><i>{exp.get('company', 'Company')}  |  {exp.get('date', '')}</i></font>", styles["Normal"])
            story.append(exp_header)
            story.append(exp_sub)
            desc = exp.get('description', '')
            if desc:
                story.append(Paragraph(desc.replace('\n', '<br/>'), styles["Normal"]))
            story.append(Spacer(1, 0.3*cm))

    # ── Education ───────────────────────────────
    education = data.get('education', [])
    if education:
        story.append(Paragraph("Education", section_title_style))
        for edu in education:
            if not edu.get('degree') and not edu.get('school'): continue
            edu_item = Paragraph(f"<b>{edu.get('degree', 'Degree')}</b>", styles["Normal"])
            edu_sub = Paragraph(f"<font color='#64748b'>{edu.get('school', 'University')}</font>", styles["Normal"])
            story.append(edu_item)
            story.append(edu_sub)
            story.append(Spacer(1, 0.2*cm))

    # ── Skills ──────────────────────────────────
    if data.get('skills'):
        story.append(Paragraph("Skills", section_title_style))
        skills_text = ", ".join(s.strip() for s in data['skills'].split(',') if s.strip())
        story.append(Paragraph(skills_text, styles["Normal"]))

    doc.build(story)
    return buffer.getvalue()
