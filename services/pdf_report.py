"""
pdf_report.py — PDF rapor üretim servisi.

ReportLab ile bellekte PDF oluşturur, diske yazmaz.
Admin panelindeki günlük rapor indirme işlevi burayı kullanır.
"""

import io
import re
from datetime import datetime, timedelta

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from flask import request, redirect, url_for, flash, make_response
from flask_login import login_required, current_user

from models import db, Pitch, Reservation, BlockedSlot
from extensions import limiter
from models import PitchTimeSlot
from utils.helpers import audit
from utils.timeutil import now_tr


# ── Renk tanımları ──────────────────────────────────────────────────

TEAL       = colors.HexColor('#0ea874')
GRAY_200   = colors.HexColor('#e2e4e8')

CLR_APPROVED_BG  = colors.HexColor('#b2f0d6')
CLR_APPROVED_TX  = colors.HexColor('#065f3e')
CLR_PENDING_BG   = colors.HexColor('#fde68a')
CLR_PENDING_TX   = colors.HexColor('#713f12')
CLR_REJECTED_BG  = colors.HexColor('#fca5a5')
CLR_REJECTED_TX  = colors.HexColor('#7f1d1d')
CLR_EXPIRED_BG   = colors.HexColor('#e5e7eb')
CLR_EXPIRED_TX   = colors.HexColor('#4b5563')
CLR_BLOCKED_BG   = colors.HexColor('#e9d5ff')
CLR_BLOCKED_TX   = colors.HexColor('#581c87')
CLR_AVAILABLE_TX = colors.HexColor('#6b7280')

STATUS_TR = {
    'Pending':  '● Bekliyor',
    'Approved': '✓ Onaylandı',
    'Rejected': '✗ Reddedildi',
    'Expired':  '○ Süresi Doldu',
}


# ── Türkçe karakter desteği için font kaydı ─────────────────────
def _register_fonts():
    """
    Türkçe karakter desteği için Unicode TTF font kaydet.
    Önce sistem fontlarını (Arial/DejaVu), bulamazsa ReportLab'ın
    kendi Vera.ttf fontunu kullanır.
    """
    import os

    # Zaten kayıtlıysa tekrar kaydetme
    if 'Turkish' in pdfmetrics.getRegisteredFontNames():
        return

    candidates = [
        # Windows
        ('Turkish', os.path.join(os.environ.get('WINDIR', r'C:\Windows'), 'Fonts', 'arial.ttf')),
        ('TurkishBd', os.path.join(os.environ.get('WINDIR', r'C:\Windows'), 'Fonts', 'arialbd.ttf')),
        # Linux
        ('Turkish', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'),
        ('TurkishBd', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'),
    ]

    registered = set()
    for name, path in candidates:
        if name not in registered and os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont(name, path))
                registered.add(name)
            except Exception:
                pass

    # Fallback: ReportLab'ın kendi Vera fontları (her yerde var)
    if 'Turkish' not in registered:
        import reportlab
        font_dir = os.path.join(os.path.dirname(reportlab.__file__), 'fonts')
        try:
            pdfmetrics.registerFont(TTFont('Turkish', os.path.join(font_dir, 'Vera.ttf')))
            registered.add('Turkish')
        except Exception:
            pass

    if 'TurkishBd' not in registered:
        import reportlab
        font_dir = os.path.join(os.path.dirname(reportlab.__file__), 'fonts')
        try:
            pdfmetrics.registerFont(TTFont('TurkishBd', os.path.join(font_dir, 'VeraBd.ttf')))
            registered.add('TurkishBd')
        except Exception:
            pass


FONT_REGULAR = 'Turkish'
FONT_BOLD    = 'TurkishBd'


def _tl(amount):
    """1500 → '1.500 TL'"""
    return f'{amount:,}'.replace(',', '.') + ' TL'


def generate_report(pitch: Pitch, report_date, reservations: list,
                    blocked_dict: dict, customer_types=None, ctype=None) -> bytes:
    """
    Verilen saha ve tarih için PDF rapor üret.
    ctype verilirse yalnızca o müşteri tipinin rezervasyonları listelenir.

    Returns: PDF dosyasının byte içeriği.
    """
    _register_fonts()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=20*mm, bottomMargin=15*mm,
        leftMargin=15*mm, rightMargin=15*mm
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'ReportTitle', parent=styles['Title'],
        fontName=FONT_BOLD, fontSize=16, leading=20, spaceAfter=4,
        textColor=colors.HexColor('#0d1f17')
    )
    subtitle_style = ParagraphStyle(
        'ReportSubtitle', parent=styles['Normal'],
        fontName=FONT_REGULAR, fontSize=10, leading=14, spaceAfter=12,
        textColor=colors.HexColor('#4a5568')
    )
    info_style = ParagraphStyle(
        'InfoText', parent=styles['Normal'],
        fontName=FONT_REGULAR, fontSize=9, leading=12, textColor=colors.HexColor('#4a5568')
    )
    cell_style = ParagraphStyle(
        'Cell', parent=styles['Normal'],
        fontName=FONT_REGULAR, fontSize=8, leading=10
    )
    footer_style = ParagraphStyle(
        'FooterText', parent=styles['Normal'],
        fontName=FONT_REGULAR, fontSize=7, leading=10, textColor=colors.HexColor('#8f97a8'),
        alignment=1
    )

    story = []
    formatted_date = report_date.strftime('%d.%m.%Y')

    # Başlık
    story.append(Paragraph('AYBU SKS Spor Tesisleri', title_style))
    subtitle = f'Günlük Rezervasyon Raporu &mdash; {pitch.name} &mdash; {formatted_date}'
    if ctype:
        subtitle += f' &mdash; Müşteri tipi: <b>{ctype.name}</b>'
    story.append(Paragraph(subtitle, subtitle_style))

    # Özet
    total    = len(reservations)
    pending  = sum(1 for r in reservations if r.status == 'Pending')
    approved = sum(1 for r in reservations if r.status == 'Approved')
    rejected = sum(1 for r in reservations if r.status == 'Rejected')
    expired  = sum(1 for r in reservations if r.status == 'Expired')
    blocked_count = len(blocked_dict)

    summary_text = (
        f'Toplam: <b>{total}</b> rezervasyon | '
        f'<font color="#065f3e">Onaylanmış: <b>{approved}</b></font> | '
        f'<font color="#854d0e">Bekleyen: <b>{pending}</b></font> | '
        f'<font color="#9b2c2c">Reddedilen: <b>{rejected}</b></font> | '
        f'<font color="#6b7280">Süresi Dolmuş: <b>{expired}</b></font> | '
        f'<font color="#6b21a8">Kilitli Slot: <b>{blocked_count}</b></font>'
    )
    story.append(Paragraph(summary_text, info_style))

    # Müşteri tipi kırılımı — aktif (onaylı + bekleyen) rezervasyon ve onaylı gelir
    type_names = {ct.id: ct.name for ct in (customer_types or [])}
    breakdown = {}
    for r in reservations:
        if r.status not in ('Approved', 'Pending'):
            continue
        key = type_names.get(r.customer_type_id, 'Tip belirtilmemiş')
        count, revenue = breakdown.get(key, (0, 0))
        breakdown[key] = (count + 1,
                          revenue + ((r.price or 0) if r.status == 'Approved' else 0))
    if breakdown:
        parts = [f'{name}: <b>{count}</b> rezervasyon, <b>{_tl(revenue)}</b> onaylı gelir'
                 for name, (count, revenue) in breakdown.items()]
        total_revenue = sum(rev for _, rev in breakdown.values())
        story.append(Spacer(1, 2*mm))
        story.append(Paragraph(
            'Tip kırılımı &mdash; ' + ' | '.join(parts)
            + f' | Toplam onaylı gelir: <b>{_tl(total_revenue)}</b>',
            info_style
        ))
    story.append(Spacer(1, 8*mm))

    # Tablo
    header = ['Saat Dilimi', 'Durum', 'Müşteri Tipi / Ücret', 'Müşteri', 'Telefon', 'E-posta']
    table_data = [header]

    res_by_slot = {}
    for r in reservations:
        if r.time_slot not in res_by_slot:
            res_by_slot[r.time_slot] = []
        res_by_slot[r.time_slot].append(r)

    # Sahaya özel saat dilimlerini çek
    pitch_slots = PitchTimeSlot.query.filter_by(pitch_id=pitch.id)\
        .order_by(PitchTimeSlot.start_hour).all()
    valid_slots = [ts.label for ts in pitch_slots]

    def res_row(slot, r):
        type_txt = type_names.get(r.customer_type_id, '—')
        if r.price is not None:
            type_txt += f' · {_tl(r.price)}'
        return [
            slot,
            STATUS_TR.get(r.status, r.status),
            Paragraph(type_txt, cell_style),
            Paragraph(r.customer_name[:40], cell_style),
            r.customer_phone,
            r.customer_email[:30]
        ]

    if ctype:
        # Tip filtresi: yalnızca bu tipin rezervasyonları (slot ortak olduğundan
        # "Müsait" satırı yanıltıcı olur, gösterilmez)
        for slot in valid_slots:
            for r in res_by_slot.get(slot, []):
                table_data.append(res_row(slot, r))
        if len(table_data) == 1:
            table_data.append(['-', 'Kayıt yok', '-', '-', '-', '-'])
    else:
        for slot in valid_slots:
            if slot in blocked_dict:
                table_data.append([
                    slot, f'KİLİTLİ: {blocked_dict[slot]}', '-', '-', '-', '-'
                ])
            elif slot in res_by_slot:
                for r in res_by_slot[slot]:
                    table_data.append(res_row(slot, r))
            else:
                table_data.append([slot, 'Müsait', '-', '-', '-', '-'])

    col_widths = [25*mm, 28*mm, 34*mm, 32*mm, 24*mm, 37*mm]
    table = Table(table_data, colWidths=col_widths, repeatRows=1)

    style_cmds = [
        ('BACKGROUND',    (0, 0), (-1, 0), TEAL),
        ('TEXTCOLOR',     (0, 0), (-1, 0), colors.white),
        ('FONTNAME',      (0, 0), (-1, 0), FONT_BOLD),
        ('FONTSIZE',      (0, 0), (-1, 0), 9),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('TOPPADDING',    (0, 0), (-1, 0), 8),
        ('FONTNAME',      (0, 1), (-1, -1), FONT_REGULAR),
        ('FONTSIZE',      (0, 1), (-1, -1), 8),
        ('TOPPADDING',    (0, 1), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 5),
        ('GRID',          (0, 0), (-1, -1), 0.5, GRAY_200),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
    ]

    for i in range(1, len(table_data)):
        status_cell = table_data[i][1]
        style_cmds.append(('FONTNAME', (1, i), (1, i), FONT_BOLD))

        if 'Onaylandı' in status_cell:
            style_cmds.append(('BACKGROUND', (0, i), (-1, i), CLR_APPROVED_BG))
            style_cmds.append(('TEXTCOLOR',  (0, i), (-1, i), CLR_APPROVED_TX))
        elif 'Bekliyor' in status_cell:
            style_cmds.append(('BACKGROUND', (0, i), (-1, i), CLR_PENDING_BG))
            style_cmds.append(('TEXTCOLOR',  (0, i), (-1, i), CLR_PENDING_TX))
        elif 'Reddedildi' in status_cell:
            style_cmds.append(('BACKGROUND', (0, i), (-1, i), CLR_REJECTED_BG))
            style_cmds.append(('TEXTCOLOR',  (0, i), (-1, i), CLR_REJECTED_TX))
        elif 'Süresi Doldu' in status_cell:
            style_cmds.append(('BACKGROUND', (0, i), (-1, i), CLR_EXPIRED_BG))
            style_cmds.append(('TEXTCOLOR',  (0, i), (-1, i), CLR_EXPIRED_TX))
        elif 'KİLİTLİ' in status_cell:
            style_cmds.append(('BACKGROUND', (0, i), (-1, i), CLR_BLOCKED_BG))
            style_cmds.append(('TEXTCOLOR',  (0, i), (-1, i), CLR_BLOCKED_TX))
        elif 'Müsait' in status_cell:
            style_cmds.append(('BACKGROUND', (0, i), (-1, i), colors.white))
            style_cmds.append(('TEXTCOLOR',  (0, i), (-1, i), CLR_AVAILABLE_TX))

    table.setStyle(TableStyle(style_cmds))
    story.append(table)

    # Footer
    story.append(Spacer(1, 10*mm))
    now_str = now_tr().strftime('%d.%m.%Y %H:%M')
    story.append(Paragraph(
        f'Rapor oluşturma: {now_str} | Oluşturan: {current_user.username} | '
        f'Bu belge AYBU SKS Spor Tesisleri yonetim sistemi tarafından üretilmiştir.',
        footer_style
    ))

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()
