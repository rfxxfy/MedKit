import io
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

REASONS = {"SHORTAGE": "Недостача", "EXPIRED": "Просрочено", "EXPIRY_UNKNOWN": "Срок не установлен"}
FONT_PATHS = ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/System/Library/Fonts/Supplemental/Arial.ttf", "/Library/Fonts/Arial.ttf"]


def render_report(inspection: Any) -> bytes:
    font_path = next((p for p in FONT_PATHS if Path(p).exists()), None)
    if font_path is None:
        raise RuntimeError("Install DejaVu Sans for Cyrillic PDF reports")
    if "MedKit" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("MedKit", font_path))
    output = io.BytesIO()
    doc = SimpleDocTemplate(
        output,
        pagesize=(210 * mm, 297 * mm),
        rightMargin=16 * mm,
        leftMargin=16 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=f"MedKit inspection {inspection.id}",
        author="MedKit Inspector",
    )
    styles = getSampleStyleSheet()
    body = ParagraphStyle("MedKitBody", parent=styles["BodyText"], fontName="MedKit", fontSize=9, leading=13)
    title = ParagraphStyle("MedKitTitle", parent=body, fontSize=22, leading=28, textColor=colors.HexColor("#126d60"))

    def p(text: Any) -> Paragraph:
        return Paragraph(escape(str(text)).replace("\n", "<br/>"), body)

    s = inspection.snapshot
    story = [
        Paragraph("MedKit Inspector", title),
        Spacer(1, 5 * mm),
        p(f"Отчёт о проверке № {inspection.id}"),
        p(f"{s['organization_name']} · {s['kit_name']}"),
        p(f"Локация: {s['location']}"),
        p(f"Исполнитель: {s['inspector_name']}"),
        p(f"Дата проверки: {inspection.inspection_date} · {s['timezone']}"),
        p(f"Начало UTC: {inspection.started_at} · Завершение UTC: {inspection.completed_at}"),
        p(f"Шаблон: {s['template_name']} · версия {s['template_version']} · интервал {s['interval_days']} дней"),
        p("Результат: " + ("Есть замечания" if inspection.result == "PROBLEM" else "Отклонений по чек-листу не найдено")),
        Spacer(1, 6 * mm),
    ]
    rows = [[p(v) for v in ["Позиция / сроки", "Норма / факт", "Не хватает", "Проср. / не уст.", "Пополнить"]]]
    for item in inspection.items:
        groups = []
        for g in item["groups"]:
            date_text = (
                f"не установлен ({g['unknown_reason']})"
                if g["expiry_state"] == "UNKNOWN"
                else f"{g['input_value']} → {g['normalized_date']} ({g['precision']}, {g['source']})"
            )
            groups.append(f"{g['qty']} {item['unit']}: {date_text}; подтвердил #{g['confirmed_by']} {g['confirmed_at']}")
        desc = item["name"] + "\n" + "\n".join(groups)
        if item["reasons"]:
            desc += "\n" + ", ".join(REASONS[r] for r in item["reasons"])
        rows.append(
            [
                p(desc),
                p(f"{item['required_qty']} / {item['actual_qty']} {item['unit']}"),
                p(item["shortage_qty"]),
                p(f"{item['expired_qty']} / {item['unknown_qty']}"),
                p(item["replenish_qty"]),
            ]
        )
    table = Table(rows, colWidths=[78 * mm, 28 * mm, 22 * mm, 28 * mm, 22 * mm], repeatRows=1, splitInRow=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e6f3ee")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#dbe5df")),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.extend(
        [
            table,
            Spacer(1, 6 * mm),
            p(
                "Результат отражает состояние на дату проверки. Расход после неё не отслеживается. Сервис учитывает количество и сроки и не оценивает медицинскую пригодность."
            ),
            p("MM/YYYY нормализуется по MONTH_END_V1 после отдельного подтверждения. Неизвестный срок можно уточнить при новой проверке."),
        ]
    )

    def footer(canvas: Any, document: Any) -> None:
        canvas.setFont("MedKit", 8)
        canvas.drawString(16 * mm, 10 * mm, f"MedKit · Проверка #{inspection.id} · Сохранённый снимок")
        canvas.drawRightString(194 * mm, 10 * mm, str(document.page))

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()
