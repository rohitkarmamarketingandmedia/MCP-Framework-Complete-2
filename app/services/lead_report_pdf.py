# app/services/lead_report_pdf.py
"""
Lead Activity Report — PDF Generator
Produces a branded, professional PDF with lead details, summary stats, and source breakdown.
"""
import io
import logging
from datetime import datetime, timedelta
from collections import Counter

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor, black, white
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable
)

logger = logging.getLogger(__name__)

# Brand colors
PRIMARY = HexColor('#6366f1')      # Indigo-500
PRIMARY_DARK = HexColor('#4338ca')  # Indigo-700
ACCENT = HexColor('#10b981')        # Emerald-500
LIGHT_BG = HexColor('#f8fafc')      # Slate-50
DARK_TEXT = HexColor('#1e293b')      # Slate-800
MED_TEXT = HexColor('#64748b')       # Slate-500
BORDER = HexColor('#e2e8f0')        # Slate-200
ROW_ALT = HexColor('#f1f5f9')       # Slate-100

# Status colors
STATUS_COLORS = {
    'new': HexColor('#3b82f6'),
    'contacted': HexColor('#f59e0b'),
    'qualified': HexColor('#10b981'),
    'converted': HexColor('#8b5cf6'),
    'lost': HexColor('#ef4444'),
}

# Source labels
SOURCE_LABELS = {
    'call': 'Phone Call',
    'form': 'Form Submission',
    'chat': 'Chat Lead',
    'gbp': 'Google Business',
    'referral': 'Referral',
}


def _fmt_date(dt_str):
    """Format ISO date string to readable format."""
    if not dt_str:
        return ''
    try:
        dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
        return dt.strftime('%b %d, %Y  %I:%M %p')
    except Exception:
        return str(dt_str)[:16]


def _fmt_phone(phone):
    """Format phone number."""
    if not phone:
        return ''
    digits = ''.join(d for d in str(phone) if d.isdigit())
    if len(digits) == 10:
        return f'({digits[:3]}) {digits[3:6]}-{digits[6:]}'
    elif len(digits) == 11 and digits[0] == '1':
        return f'({digits[1:4]}) {digits[4:7]}-{digits[7:]}'
    return str(phone)


def generate_lead_report_pdf(client, leads, days=30):
    """
    Generate a Lead Activity Report PDF.

    Args:
        client: dict with business_name, industry, geo, phone, email
        leads: list of lead dicts (id, name, phone, email, source, status, created_at, message, etc.)
        days: period in days

    Returns:
        bytes — the PDF file content
    """
    buf = io.BytesIO()

    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        topMargin=0.6 * inch,
        bottomMargin=0.6 * inch,
        leftMargin=0.6 * inch,
        rightMargin=0.6 * inch,
    )

    styles = getSampleStyleSheet()

    # Custom styles
    styles.add(ParagraphStyle(
        'ReportTitle', parent=styles['Title'],
        fontSize=22, textColor=DARK_TEXT, spaceAfter=4, alignment=TA_LEFT,
        fontName='Helvetica-Bold',
    ))
    styles.add(ParagraphStyle(
        'ReportSubtitle', parent=styles['Normal'],
        fontSize=11, textColor=MED_TEXT, spaceAfter=12, alignment=TA_LEFT,
    ))
    styles.add(ParagraphStyle(
        'SectionHead', parent=styles['Heading2'],
        fontSize=14, textColor=PRIMARY_DARK, spaceBefore=18, spaceAfter=8,
        fontName='Helvetica-Bold',
    ))
    styles.add(ParagraphStyle(
        'StatLabel', parent=styles['Normal'],
        fontSize=9, textColor=MED_TEXT, alignment=TA_CENTER,
    ))
    styles.add(ParagraphStyle(
        'StatValue', parent=styles['Normal'],
        fontSize=20, textColor=DARK_TEXT, alignment=TA_CENTER,
        fontName='Helvetica-Bold',
    ))
    styles.add(ParagraphStyle(
        'CellText', parent=styles['Normal'],
        fontSize=8, textColor=DARK_TEXT, leading=11,
    ))
    styles.add(ParagraphStyle(
        'CellTextSmall', parent=styles['Normal'],
        fontSize=7, textColor=MED_TEXT, leading=9,
    ))
    styles.add(ParagraphStyle(
        'Footer', parent=styles['Normal'],
        fontSize=8, textColor=MED_TEXT, alignment=TA_CENTER,
    ))

    story = []
    page_width = letter[0] - 1.2 * inch  # usable width

    # ── HEADER ────────────────────────────────────────
    biz_name = client.get('business_name', 'Client')
    industry = client.get('industry', '')
    geo = client.get('geo', '')
    subtitle_parts = [x for x in [industry, geo] if x]

    story.append(Paragraph(f'Lead Activity Report', styles['ReportTitle']))
    story.append(Paragraph(
        f'{biz_name}' + (f'  &bull;  {" &bull; ".join(subtitle_parts)}' if subtitle_parts else ''),
        styles['ReportSubtitle']
    ))

    period_end = datetime.utcnow()
    period_start = period_end - timedelta(days=days)
    story.append(Paragraph(
        f'{period_start.strftime("%B %d, %Y")} &ndash; {period_end.strftime("%B %d, %Y")}  ({days} days)',
        styles['ReportSubtitle']
    ))
    story.append(HRFlowable(width='100%', thickness=1, color=BORDER, spaceAfter=12))

    # ── SUMMARY STATS ─────────────────────────────────
    total = len(leads)
    source_counts = Counter(l.get('source', 'unknown') for l in leads)
    status_counts = Counter(l.get('status', 'new') for l in leads)

    calls = source_counts.get('call', 0)
    forms = source_counts.get('form', 0)
    chats = source_counts.get('chat', 0)
    new_count = status_counts.get('new', 0)
    contacted = status_counts.get('contacted', 0)
    qualified = status_counts.get('qualified', 0)
    converted = status_counts.get('converted', 0)

    def _stat_cell(value, label, color=DARK_TEXT):
        return [
            Paragraph(f'<font color="{color}">{value}</font>', styles['StatValue']),
            Paragraph(label, styles['StatLabel']),
        ]

    stat_data = [
        [
            _stat_cell(total, 'Total Leads'),
            _stat_cell(calls, 'Phone Calls', '#3b82f6'),
            _stat_cell(forms, 'Form Submissions', '#f59e0b'),
            _stat_cell(chats, 'Chat Leads', '#10b981'),
        ]
    ]

    # Flatten — each cell is a list of two Paragraphs, so wrap in a mini-table
    row = []
    for cell_content in stat_data[0]:
        mini = Table([[cell_content[0]], [cell_content[1]]], colWidths=[page_width / 4 - 6])
        mini.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        row.append(mini)

    stats_table = Table([row], colWidths=[page_width / 4] * 4)
    stats_table.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.5, BORDER),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, BORDER),
        ('BACKGROUND', (0, 0), (-1, -1), LIGHT_BG),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('ROUNDEDCORNERS', [6, 6, 6, 6]),
    ]))
    story.append(stats_table)
    story.append(Spacer(1, 8))

    # Status row
    row2 = []
    for cell_content in [
        _stat_cell(new_count, 'New / Uncontacted', '#3b82f6'),
        _stat_cell(contacted, 'Contacted', '#f59e0b'),
        _stat_cell(qualified, 'Qualified', '#10b981'),
        _stat_cell(converted, 'Won / Converted', '#8b5cf6'),
    ]:
        mini = Table([[cell_content[0]], [cell_content[1]]], colWidths=[page_width / 4 - 6])
        mini.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        row2.append(mini)

    status_table = Table([row2], colWidths=[page_width / 4] * 4)
    status_table.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.5, BORDER),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, BORDER),
        ('BACKGROUND', (0, 0), (-1, -1), LIGHT_BG),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(status_table)
    story.append(Spacer(1, 16))

    # ── SOURCE BREAKDOWN ──────────────────────────────
    if source_counts:
        story.append(Paragraph('Lead Sources', styles['SectionHead']))

        src_rows = [['Source', 'Count', '% of Total']]
        for src, cnt in source_counts.most_common():
            pct = (cnt / total * 100) if total else 0
            src_rows.append([
                SOURCE_LABELS.get(src, src.title()),
                str(cnt),
                f'{pct:.0f}%',
            ])

        src_table = Table(src_rows, colWidths=[page_width * 0.5, page_width * 0.25, page_width * 0.25])
        src_style = [
            ('BACKGROUND', (0, 0), (-1, 0), PRIMARY),
            ('TEXTCOLOR', (0, 0), (-1, 0), white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LEFTPADDING', (0, 0), (-1, -1), 10),
            ('BOX', (0, 0), (-1, -1), 0.5, BORDER),
            ('LINEBELOW', (0, 0), (-1, 0), 1, PRIMARY_DARK),
        ]
        for i in range(1, len(src_rows)):
            if i % 2 == 0:
                src_style.append(('BACKGROUND', (0, i), (-1, i), ROW_ALT))
        src_table.setStyle(TableStyle(src_style))
        story.append(src_table)
        story.append(Spacer(1, 16))

    # ── LEAD DETAIL TABLE ─────────────────────────────
    story.append(Paragraph('Lead Details', styles['SectionHead']))

    col_widths = [
        page_width * 0.14,  # Date
        page_width * 0.18,  # Name
        page_width * 0.16,  # Phone
        page_width * 0.20,  # Email
        page_width * 0.12,  # Source
        page_width * 0.10,  # Status
        page_width * 0.10,  # Service
    ]

    header_row = [
        Paragraph('<b>Date</b>', styles['CellText']),
        Paragraph('<b>Name</b>', styles['CellText']),
        Paragraph('<b>Phone</b>', styles['CellText']),
        Paragraph('<b>Email</b>', styles['CellText']),
        Paragraph('<b>Source</b>', styles['CellText']),
        Paragraph('<b>Status</b>', styles['CellText']),
        Paragraph('<b>Service / Dur.</b>', styles['CellText']),
    ]

    table_data = [header_row]

    for lead in leads:
        date_str = _fmt_date(lead.get('created_at', ''))
        # Shorten date for table
        try:
            dt = datetime.fromisoformat(lead['created_at'].replace('Z', '+00:00'))
            date_str = dt.strftime('%m/%d/%y\n%I:%M %p')
        except Exception:
            pass

        name = lead.get('name', '') or ''
        phone = _fmt_phone(lead.get('phone', ''))
        email = lead.get('email', '') or ''
        source = SOURCE_LABELS.get(lead.get('source', ''), lead.get('source', '') or '')
        status = (lead.get('status', '') or 'new').title()
        # For phone calls, show duration instead of service requested
        service = lead.get('service_requested', '') or ''
        if lead.get('source') == 'call' and lead.get('duration_formatted'):
            service = lead['duration_formatted']
        elif lead.get('source') == 'call' and lead.get('duration'):
            mins, secs = divmod(int(lead['duration']), 60)
            service = f'{mins}:{secs:02d}'

        table_data.append([
            Paragraph(date_str, styles['CellTextSmall']),
            Paragraph(name[:30], styles['CellText']),
            Paragraph(phone, styles['CellTextSmall']),
            Paragraph(email[:28], styles['CellTextSmall']),
            Paragraph(source, styles['CellTextSmall']),
            Paragraph(status, styles['CellText']),
            Paragraph(service[:20], styles['CellTextSmall']),
        ])

    detail_table = Table(table_data, colWidths=col_widths, repeatRows=1)
    detail_style = [
        ('BACKGROUND', (0, 0), (-1, 0), PRIMARY),
        ('TEXTCOLOR', (0, 0), (-1, 0), white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('BOX', (0, 0), (-1, -1), 0.5, BORDER),
        ('LINEBELOW', (0, 0), (-1, 0), 1, PRIMARY_DARK),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, BORDER),
    ]
    for i in range(1, len(table_data)):
        if i % 2 == 0:
            detail_style.append(('BACKGROUND', (0, i), (-1, i), ROW_ALT))

    detail_table.setStyle(TableStyle(detail_style))
    story.append(detail_table)

    # ── FOOTER ────────────────────────────────────────
    story.append(Spacer(1, 24))
    story.append(HRFlowable(width='100%', thickness=0.5, color=BORDER, spaceAfter=6))
    story.append(Paragraph(
        f'Generated {datetime.utcnow().strftime("%B %d, %Y at %I:%M %p UTC")}  &bull;  '
        f'Karma Marketing + Media  &bull;  MCP Framework',
        styles['Footer']
    ))

    # Build
    doc.build(story)
    buf.seek(0)
    return buf.read()
