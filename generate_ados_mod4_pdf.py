# -*- coding: utf-8 -*-
"""
Generador de alta precisión clínica para:
Protocolo de Entrevista Semiestructurada y Observación Clínica para Evaluación de TEA en Adultos (Estructura Módulo 4)
"""

import os
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
    KeepTogether,
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


# Paleta de Colores Clínica Formal (Gris Pizarra y Azul Clínico Suave)
C_SLATE_DARK = colors.HexColor("#1E293B")      # Gris pizarra profundo (títulos y encabezados)
C_SLATE_MED = colors.HexColor("#334155")       # Texto principal
C_SLATE_MUTED = colors.HexColor("#64748B")     # Subtítulos y etiquetas secundarias
C_CLINICAL_BLUE = colors.HexColor("#1E40AF")   # Azul clínico institucional
C_CLINICAL_ACCENT = colors.HexColor("#2563EB") # Azul acento clínico
C_BLUE_SOFT_BG = colors.HexColor("#EFF6FF")    # Fondo azul clínico muy suave
C_BLUE_BORDER = colors.HexColor("#BFDBFE")     # Borde azul clínico suave
C_SLATE_BG = colors.HexColor("#F8FAFC")        # Fondo gris pizarra muy tenue
C_SLATE_HEADER = colors.HexColor("#F1F5F9")    # Encabezado de tabla suave
C_BORDER = colors.HexColor("#CBD5E1")          # Borde de tablas y cajas
C_LINE_FAINT = colors.HexColor("#E2E8F0")      # Líneas tenues para escritura manual
C_WHITE = colors.HexColor("#FFFFFF")


def register_clean_fonts():
    """Registra una tipografía sans-serif limpia (Segoe UI / Arial / Helvetica fallback)."""
    win_fonts = r"C:\Windows\Fonts"
    candidates = [
        ("ClinicalSans", "segoeui.ttf", "segoeuib.ttf", "segoeuii.ttf", "seguisb.ttf"),
        ("ClinicalSans", "arial.ttf", "arialbd.ttf", "ariali.ttf", "arialbi.ttf"),
    ]
    for family, reg, bold, ital, bi in candidates:
        reg_p = os.path.join(win_fonts, reg)
        bold_p = os.path.join(win_fonts, bold)
        ital_p = os.path.join(win_fonts, ital)
        bi_p = os.path.join(win_fonts, bi)
        if os.path.exists(reg_p) and os.path.exists(bold_p):
            try:
                pdfmetrics.registerFont(TTFont("ClinicalSans", reg_p))
                pdfmetrics.registerFont(TTFont("ClinicalSans-Bold", bold_p))
                if os.path.exists(ital_p):
                    pdfmetrics.registerFont(TTFont("ClinicalSans-Italic", ital_p))
                else:
                    pdfmetrics.registerFont(TTFont("ClinicalSans-Italic", reg_p))
                if os.path.exists(bi_p):
                    pdfmetrics.registerFont(TTFont("ClinicalSans-BoldItalic", bi_p))
                else:
                    pdfmetrics.registerFont(TTFont("ClinicalSans-BoldItalic", bold_p))
                pdfmetrics.registerFontFamily(
                    "ClinicalSans",
                    normal="ClinicalSans",
                    bold="ClinicalSans-Bold",
                    italic="ClinicalSans-Italic",
                    boldItalic="ClinicalSans-BoldItalic",
                )
                return "ClinicalSans", "ClinicalSans-Bold", "ClinicalSans-Italic"
            except Exception:
                pass
    return "Helvetica", "Helvetica-Bold", "Helvetica-Oblique"


FONT_REG, FONT_BOLD, FONT_ITALIC = register_clean_fonts()


def build_styles():
    getSampleStyleSheet()

    s_super = ParagraphStyle(
        "SuperHeader",
        fontName=FONT_BOLD,
        fontSize=7.2,
        leading=9.5,
        textColor=C_CLINICAL_ACCENT,
        alignment=TA_LEFT,
        spaceAfter=1.5,
    )
    s_title = ParagraphStyle(
        "MainTitle",
        fontName=FONT_BOLD,
        fontSize=12.6,
        leading=15.5,
        textColor=C_SLATE_DARK,
        alignment=TA_LEFT,
        spaceAfter=2,
    )
    s_subtitle = ParagraphStyle(
        "SubTitle",
        fontName=FONT_ITALIC,
        fontSize=8.8,
        leading=11.5,
        textColor=C_SLATE_MUTED,
        alignment=TA_LEFT,
        spaceAfter=5,
    )
    s_sec_hdr = ParagraphStyle(
        "SectionHeader",
        fontName=FONT_BOLD,
        fontSize=9.8,
        leading=12.5,
        textColor=C_SLATE_DARK,
        spaceBefore=3,
        spaceAfter=4,
    )
    s_block_title = ParagraphStyle(
        "BlockTitle",
        fontName=FONT_BOLD,
        fontSize=9.0,
        leading=11.5,
        textColor=C_WHITE,
        alignment=TA_LEFT,
    )
    s_block_sub = ParagraphStyle(
        "BlockSub",
        fontName=FONT_BOLD,
        fontSize=7.8,
        leading=10.2,
        textColor=C_CLINICAL_BLUE,
        spaceBefore=1,
        spaceAfter=2,
    )
    s_body = ParagraphStyle(
        "BodyClinical",
        fontName=FONT_REG,
        fontSize=8.0,
        leading=10.8,
        textColor=C_SLATE_MED,
        alignment=TA_LEFT,
    )
    s_body_just = ParagraphStyle(
        "BodyClinicalJust",
        fontName=FONT_REG,
        fontSize=7.9,
        leading=10.6,
        textColor=C_SLATE_MED,
        alignment=TA_JUSTIFY,
    )
    s_bullet = ParagraphStyle(
        "BulletClinical",
        fontName=FONT_REG,
        fontSize=7.8,
        leading=10.4,
        textColor=C_SLATE_MED,
        leftIndent=8,
        firstLineIndent=-6,
        spaceAfter=1.4,
    )
    s_field_lbl = ParagraphStyle(
        "FieldLabel",
        fontName=FONT_BOLD,
        fontSize=7.4,
        leading=9.4,
        textColor=C_SLATE_MUTED,
    )
    s_field_val = ParagraphStyle(
        "FieldVal",
        fontName=FONT_REG,
        fontSize=8.0,
        leading=10.0,
        textColor=C_SLATE_DARK,
    )
    s_tbl_hdr = ParagraphStyle(
        "TableHeader",
        fontName=FONT_BOLD,
        fontSize=7.6,
        leading=9.6,
        textColor=C_WHITE,
        alignment=TA_LEFT,
    )
    s_tbl_hdr_c = ParagraphStyle(
        "TableHeaderCenter",
        fontName=FONT_BOLD,
        fontSize=7.6,
        leading=9.6,
        textColor=C_WHITE,
        alignment=TA_CENTER,
    )
    s_tbl_code = ParagraphStyle(
        "TableCode",
        fontName=FONT_BOLD,
        fontSize=7.9,
        leading=9.8,
        textColor=C_CLINICAL_BLUE,
        alignment=TA_CENTER,
    )
    s_tbl_item = ParagraphStyle(
        "TableItem",
        fontName=FONT_BOLD,
        fontSize=7.7,
        leading=9.8,
        textColor=C_SLATE_DARK,
    )
    s_tbl_crit = ParagraphStyle(
        "TableCrit",
        fontName=FONT_REG,
        fontSize=7.4,
        leading=9.6,
        textColor=C_SLATE_MED,
    )
    s_tbl_score = ParagraphStyle(
        "TableScore",
        fontName=FONT_BOLD,
        fontSize=7.9,
        leading=9.8,
        textColor=C_SLATE_DARK,
        alignment=TA_CENTER,
    )
    s_notes_lbl = ParagraphStyle(
        "NotesLabel",
        fontName=FONT_BOLD,
        fontSize=7.3,
        leading=9.2,
        textColor=C_SLATE_MUTED,
    )
    return {
        "super": s_super,
        "title": s_title,
        "subtitle": s_subtitle,
        "sec_hdr": s_sec_hdr,
        "block_title": s_block_title,
        "block_sub": s_block_sub,
        "body": s_body,
        "body_just": s_body_just,
        "bullet": s_bullet,
        "field_lbl": s_field_lbl,
        "field_val": s_field_val,
        "tbl_hdr": s_tbl_hdr,
        "tbl_hdr_c": s_tbl_hdr_c,
        "tbl_code": s_tbl_code,
        "tbl_item": s_tbl_item,
        "tbl_crit": s_tbl_crit,
        "tbl_score": s_tbl_score,
        "notes_lbl": s_notes_lbl,
    }


def draw_page_header_footer(canvas, doc):
    """Dibuja encabezado sutil en páginas 2+ y pie de página numerado en todas las hojas."""
    canvas.saveState()
    page_num = canvas.getPageNumber()
    w, h = letter
    left_m = doc.leftMargin
    right_m = w - doc.rightMargin

    # Barra superior decorativa institucional fina
    canvas.setStrokeColor(C_CLINICAL_BLUE)
    canvas.setLineWidth(1.4)
    canvas.line(left_m, h - 10.5 * mm, right_m, h - 10.5 * mm)

    if page_num > 1:
        canvas.setFont(FONT_BOLD, 7.0)
        canvas.setFillColor(C_SLATE_MUTED)
        canvas.drawString(
            left_m,
            h - 9.0 * mm,
            "PROTOCOLO DE ENTREVISTA SEMIESTRUCTURADA Y OBSERVACIÓN CLÍNICA PARA TEA EN ADULTOS (MÓDULO 4)",
        )
        canvas.setFont(FONT_REG, 7.0)
        canvas.drawRightString(right_m, h - 9.0 * mm, "Evaluado(a): ____________________________")

    # Pie de página
    canvas.setStrokeColor(C_BORDER)
    canvas.setLineWidth(0.6)
    canvas.line(left_m, 11.5 * mm, right_m, 11.5 * mm)

    canvas.setFont(FONT_REG, 7.0)
    canvas.setFillColor(C_SLATE_MUTED)
    canvas.drawString(
        left_m,
        8.2 * mm,
        "Espacio Terapéutico • Instrumento Clínico Estandarizado de Observación y Codificación Conductual (ADOS-2 / Módulo 4)",
    )
    canvas.setFont(FONT_BOLD, 7.3)
    canvas.setFillColor(C_SLATE_DARK)
    canvas.drawRightString(right_m, 8.2 * mm, f"Página {page_num} de 4")
    canvas.restoreState()


def build_interview_block(
    st,
    usable_w,
    block_num,
    block_title,
    target_domains,
    questions,
    social_pressures,
    focus_indicators,
    note_lines=3,
    line_height=13.5,
):
    """
    Construye un bloque temático completo dentro de un KeepTogether para que ninguna
    tabla quede cortada a la mitad.
    """
    # 1. Fila de encabezado del bloque (auto-height para permitir títulos de 1 o 2 líneas sin solapamiento)
    hdr_left = Paragraph(f"BLOQUE {block_num}: {block_title.upper()}", st["block_title"])
    hdr_right = Paragraph(
        f"<font size='7.3' color='#DBEAFE'><b>Foco Algorítmico:</b> {target_domains}</font>",
        ParagraphStyle("HdrRight", fontName=FONT_REG, fontSize=7.3, leading=9.5, alignment=TA_RIGHT),
    )

    # 2. Columna Izquierda: Preguntas Guía
    q_flow = [Paragraph("PREGUNTAS GUÍA SEMIESTRUCTURADAS", st["block_sub"])]
    for q in questions:
        q_flow.append(Paragraph(f"• {q}", st["bullet"]))

    # 3. Columna Derecha: Presiones Sociales y Focos de Observación
    p_flow = [Paragraph("PRESIONES SOCIALES A APLICAR (ELICITACIÓN)", st["block_sub"])]
    for p in social_pressures:
        p_flow.append(Paragraph(f"› {p}", st["bullet"]))
    if focus_indicators:
        p_flow.append(Spacer(1, 1.5))
        p_flow.append(
            Paragraph(
                f"<b>Indicadores clave a observar:</b> {focus_indicators}",
                ParagraphStyle(
                    "FocusNote",
                    fontName=FONT_REG,
                    fontSize=7.4,
                    leading=9.6,
                    textColor=C_SLATE_DARK,
                ),
            )
        )

    col_left_w = usable_w * 0.54
    col_right_w = usable_w * 0.46

    # 4. Filas de Notas de Observación Clínica con líneas tenues para escritura manual
    notes_header_row = [
        Paragraph(
            "NOTAS DE OBSERVACIÓN CLÍNICA Y EVIDENCIA CONDUCTUAL (Verbal / No Verbal / Reciprocidad):",
            st["notes_lbl"],
        ),
        Paragraph(
            "Cód. preliminar: [ 0 ]  [ 1 ]  [ 2 ]  [ 3 ]",
            ParagraphStyle(
                "PrelimCode",
                fontName=FONT_BOLD,
                fontSize=7.3,
                leading=9.2,
                textColor=C_CLINICAL_BLUE,
                alignment=TA_RIGHT,
            ),
        ),
    ]

    data = [
        [hdr_left, hdr_right],
        [q_flow, p_flow],
        notes_header_row,
    ]

    for _ in range(note_lines):
        data.append(["", ""])

    # None en filas 0, 1 y 2 para que ReportLab calcule la altura exacta sin cortar texto
    row_heights = [None, None, None] + [line_height] * note_lines

    tbl = Table(data, colWidths=[col_left_w, col_right_w], rowHeights=row_heights)
    ts = [
        # Encabezado del bloque
        ("BACKGROUND", (0, 0), (1, 0), C_SLATE_DARK),
        ("VALIGN", (0, 0), (1, 0), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (1, 0), 7),
        ("RIGHTPADDING", (0, 0), (1, 0), 7),
        ("TOPPADDING", (0, 0), (1, 0), 3.5),
        ("BOTTOMPADDING", (0, 0), (1, 0), 3.5),
        # Cuerpo de preguntas y presiones
        ("BACKGROUND", (0, 1), (0, 1), C_WHITE),
        ("BACKGROUND", (1, 1), (1, 1), C_BLUE_SOFT_BG),
        ("VALIGN", (0, 1), (1, 1), "TOP"),
        ("LEFTPADDING", (0, 1), (1, 1), 7),
        ("RIGHTPADDING", (0, 1), (1, 1), 7),
        ("TOPPADDING", (0, 1), (1, 1), 4),
        ("BOTTOMPADDING", (0, 1), (1, 1), 4),
        ("LINEBEFORE", (1, 1), (1, 1), 0.75, C_BLUE_BORDER),
        ("LINEBELOW", (0, 1), (1, 1), 0.75, C_BORDER),
        # Cabecera de notas
        ("BACKGROUND", (0, 2), (1, 2), C_SLATE_BG),
        ("VALIGN", (0, 2), (1, 2), "MIDDLE"),
        ("LEFTPADDING", (0, 2), (1, 2), 7),
        ("RIGHTPADDING", (0, 2), (1, 2), 7),
        ("TOPPADDING", (0, 2), (1, 2), 2.5),
        ("BOTTOMPADDING", (0, 2), (1, 2), 2.5),
        ("LINEBELOW", (0, 2), (1, 2), 0.5, C_LINE_FAINT),
        # Borde exterior general
        ("BOX", (0, 0), (-1, -1), 0.9, C_BORDER),
    ]

    # Líneas tenues horizontales para escritura a mano
    for idx in range(3, 3 + note_lines):
        ts.append(("SPAN", (0, idx), (1, idx)))
        ts.append(("BACKGROUND", (0, idx), (1, idx), C_WHITE))
        if idx < 2 + note_lines:
            ts.append(("LINEBELOW", (0, idx), (1, idx), 0.5, C_LINE_FAINT))

    tbl.setStyle(TableStyle(ts))
    return KeepTogether([tbl, Spacer(1, 5.5)])


def generate_protocol_pdf(output_paths):
    if isinstance(output_paths, str):
        output_paths = [output_paths]

    primary_path = output_paths[0]
    st = build_styles()

    doc = SimpleDocTemplate(
        primary_path,
        pagesize=letter,
        leftMargin=12.5 * mm,
        rightMargin=12.5 * mm,
        topMargin=12.5 * mm,
        bottomMargin=14 * mm,
        title="Protocolo de Entrevista Semiestructurada y Observación Clínica para Evaluación de TEA en Adultos (Estructura Módulo 4)",
        author="Espacio Terapéutico - Departamento de Psicología Clínica y Neuropsicología",
    )

    usable_w = letter[0] - doc.leftMargin - doc.rightMargin
    story = []

    # =========================================================================
    # PÁGINA 1: ENCABEZADO, FICHA CLÍNICA, INSTRUCCIONES Y BLOQUES 1 Y 2
    # =========================================================================
    story.append(
        Paragraph(
            "INSTRUMENTO DE EVALUACIÓN CLÍNICA NEUROPSICOLÓGICA • ESTÁNDAR DIAGNÓSTICO MÓDULO 4",
            st["super"],
        )
    )
    story.append(
        Paragraph(
            "Protocolo de Entrevista Semiestructurada y Observación Clínica para Evaluación de TEA en Adultos (Estructura Módulo 4)",
            st["title"],
        )
    )
    story.append(
        Paragraph(
            "Guía de Administración Conversacional y Codificación Conductual (Adolescentes Tardíos y Adultos con Fluidez Verbal)",
            st["subtitle"],
        )
    )

    # 1. Cuadrícula de Datos del Evaluado (Ficha de Identificación Clínica)
    id_data = [
        [
            Paragraph("<b>NOMBRE COMPLETO DEL EVALUADO(A):</b>", st["field_lbl"]),
            Paragraph("__________________________________________________", st["field_val"]),
            Paragraph("<b>FECHA DE EVALUACIÓN:</b>", st["field_lbl"]),
            Paragraph("____ / ____ / 20____", st["field_val"]),
        ],
        [
            Paragraph("<b>EDAD CRONOLÓGICA:</b>", st["field_lbl"]),
            Paragraph("_____ años  _____ meses   <b>CI / ID:</b> ______________", st["field_val"]),
            Paragraph("<b>EVALUADOR / PSICÓLOGO(A):</b>", st["field_lbl"]),
            Paragraph("________________________________", st["field_val"]),
        ],
        [
            Paragraph("<b>NIVEL DE LENGUAJE OBSERVADO:</b>", st["field_lbl"]),
            Paragraph("[  ] Fluido complejo  [  ] Con latencia  [  ] Pedante", st["field_val"]),
            Paragraph("<b>CONTEXTO DE DERIVACIÓN:</b>", st["field_lbl"]),
            Paragraph("[  ] Propia  [  ] Psiquiatría  [  ] Familiar", st["field_val"]),
        ],
    ]
    id_table = Table(
        id_data,
        colWidths=[usable_w * 0.23, usable_w * 0.34, usable_w * 0.19, usable_w * 0.24],
    )
    id_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), C_SLATE_BG),
                ("BOX", (0, 0), (-1, -1), 0.9, C_BORDER),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, C_LINE_FAINT),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5.5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5.5),
                ("TOPPADDING", (0, 0), (-1, -1), 3.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
            ]
        )
    )
    story.append(id_table)
    story.append(Spacer(1, 5))

    # 2. Recuadro de Instrucciones para el Examinador
    inst_text = (
        "<b>INSTRUCCIONES PARA EL EXAMINADOR (ADMINISTRACIÓN Y PRESIONES SOCIALES):</b><br/>"
        "Mantenga una <b>postura conversacional natural, cálida y semiestructurada</b> (evite un interrogatorio rígido pregunta-respuesta). "
        "Aplique deliberadamente <b>«presiones sociales»</b> durante la entrevista: realice comentarios personales breves sobre experiencias propias para observar si el evaluado "
        "pregunta, valida o continúa únicamente con su propio discurso; introduzca pausas de silencio deliberadas para evaluar iniciativa comunicativa, "
        "y cambie sutilmente de tema para valorar flexibilidad cognitiva. Codifique la conducta observada directamente en sesión según la escala estándar:<br/>"
        "<font color='#1E40AF'><b>[ 0 ] Típico / Sin alteración clínica</b></font> &nbsp;|&nbsp; "
        "<font color='#1E40AF'><b>[ 1 ] Ligeramente atípico / Poco frecuente</b></font> &nbsp;|&nbsp; "
        "<font color='#1E40AF'><b>[ 2 ] Claramente atípico / Interfiere en reciprocidad</b></font> &nbsp;|&nbsp; "
        "<font color='#1E40AF'><b>[ 3 ] Marcadamente atípico / Grave (convierte a 2 en algoritmo)</b></font>"
    )
    inst_tbl = Table([[Paragraph(inst_text, st["body_just"])]], colWidths=[usable_w])
    inst_tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), C_BLUE_SOFT_BG),
                ("BOX", (0, 0), (-1, -1), 0.9, C_BLUE_BORDER),
                ("LINEBEFORE", (0, 0), (0, -1), 3.0, C_CLINICAL_BLUE),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 4.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5),
            ]
        )
    )
    story.append(inst_tbl)
    story.append(Spacer(1, 5.5))

    # Bloque 1
    story.append(
        build_interview_block(
            st,
            usable_w,
            block_num=1,
            block_title="Vida Diaria, Rutinas y Autonomía",
            target_domains="A1, A6, A8, B4",
            questions=[
                "¿A qué te dedicas actualmente (trabajo/estudios) y cómo es un día habitual desde que te levantas?",
                "¿Con quién vives actualmente y cómo se organizan las responsabilidades domésticas y financieras?",
                "¿Cómo gestionas tu tiempo libre y qué rutinas específicas necesitas mantener para sentirte tranquilo(a)?",
                "Cuando surge un cambio imprevisto de planes o se altera tu horario habitual, ¿cómo reaccionas por dentro y por fuera?",
            ],
            social_pressures=[
                "Comentar brevemente: «A mí la semana pasada me cambiaron toda la agenda a última hora y fue caótico…» y hacer una pausa de 4 s para ver si muestra reciprocidad o interés.",
                "Observar si ofrece contexto suficiente al oyente o asume que el evaluador ya conoce personas/lugares específicos.",
                "Indagar sutilmente si sus rutinas son funcionales o ritualizadas/inflexibles ante cambios menores.",
            ],
            focus_indicators="Reciprocidad conversacional (A6), contacto visual espontáneo (A1), rigidez o malestar ante imprevistos (B4).",
            note_lines=3,
            line_height=13,
        )
    )

    # Bloque 2
    story.append(
        build_interview_block(
            st,
            usable_w,
            block_num=2,
            block_title="Intereses Especiales y Foco Profundo",
            target_domains="A3, A5, A6, B1, B2",
            questions=[
                "¿Cuáles son tus principales intereses, aficiones o temas sobre los que te apasiona investigar a profundidad?",
                "¿Cuánto tiempo puedes dedicarle a ese tema cuando estás concentrado(a)? ¿Te ocurre que olvidas comer o descansar?",
                "Cuando conversas con otras personas sobre este interés, ¿cómo notas si a la otra persona le interesa o si se aburre?",
                "¿Te resulta sencillo ceder el turno conversacional y cambiar de tema cuando el interlocutor habla de otra cosa?",
            ],
            social_pressures=[
                "Permitir que hable 1–2 minutos sobre su afición principal para evaluar si entra en monólogo enciclopédico o pedante (B1/B2).",
                "Emitir una señal no verbal sutil de cambio de foco (mirar la libreta, hacer ademán suave de intervenir) y observar si la registra y cede el turno conversacional.",
                "Introducir un tema neutro distinto y evaluar el esfuerzo para desengancharse del interés circunscrito.",
            ],
            focus_indicators="Monólogo unilateral vs. diálogo (A6), disfrute compartido (A5), lenguaje pedante/formal (B1), absorción (B2).",
            note_lines=3,
            line_height=13,
        )
    )

    # Salto limpio a Página 2
    story.append(PageBreak())

    # =========================================================================
    # PÁGINA 2: BLOQUES 3, 4 Y 5
    # =========================================================================
    story.append(
        Paragraph(
            "GUÍA DE ENTREVISTA SEMIESTRUCTURADA POR BLOQUES TEMÁTICOS (CONTINUACIÓN)",
            st["sec_hdr"],
        )
    )

    # Bloque 3
    story.append(
        build_interview_block(
            st,
            usable_w,
            block_num=3,
            block_title="Emociones y Comprensión Socioemocional",
            target_domains="A2, A4, A5, A7",
            questions=[
                "¿Qué situaciones suelen hacerte sentir alegría o entusiasmo? ¿Cómo describes física e internamente esa sensación?",
                "¿Qué cosas te producen tristeza o desánimo y cómo identificas en tu cuerpo o mente cuando estás triste?",
                "¿Qué situaciones detonan enojo/frustración o ansiedad/miedo en ti? ¿Cómo los expresas y qué haces para regularlos?",
                "Cuando alguien cercano atraviesa un problema o llora frente a ti, ¿qué experimentas internamente y cómo respondes?",
            ],
            social_pressures=[
                "Compartir una breve vivencia emocional neutra («Hace poco pasé por una situación muy estresante con un familiar…») para observar ofertas de empatía o validación (A7).",
                "Evaluar si describe las emociones como vivencias internas subjetivas o solo mediante eventos externos/fisiológicos concretos (alexitimia).",
                "Observar congruencia entre afecto relatado, expresión facial dirigida (A4) y sonrisa social recíproca (A2).",
            ],
            focus_indicators="Expresión facial dirigida (A4), sonrisa social recíproca (A2), vocabulario emocional interno vs. literal, empatía (A7).",
            note_lines=3,
            line_height=13.5,
        )
    )

    # Bloque 4
    story.append(
        build_interview_block(
            st,
            usable_w,
            block_num=4,
            block_title="Relaciones Interpersonales, Amistad y Soledad",
            target_domains="A1, A6, A7, A8",
            questions=[
                "Para ti, ¿qué define a un verdadero amigo(a) y qué diferencia la amistad de un conocido o compañero de trabajo/estudios?",
                "¿Qué significa para ti una relación de pareja y cómo manejas la convivencia, la intimidad afectiva y los acuerdos?",
                "¿Qué consideras que aportas tú a tus vínculos cercanos y qué esperas recibir de la otra persona (reciprocidad)?",
                "¿Cómo comprendes y experimentas la soledad? ¿Te sientes solo(a) con frecuencia o disfrutas estar a solas?",
            ],
            social_pressures=[
                "Indagar comprensión de reciprocidad en vínculos: evaluar si define la amistad por apoyo mutuo y afecto o solo por utilidad/intereses compartidos.",
                "Hacer una pausa reflexiva tras la pregunta de soledad para observar si diferencia «aislamiento físico elegido» (descanso sensorial) de «soledad emocional».",
                "Observar iniciativa para sostener el intercambio socioemocional con el evaluador (A8).",
            ],
            focus_indicators="Comprensión de reciprocidad vincular (A6, A7), diferenciación de conceptos socioemocionales, iniciativa (A8).",
            note_lines=3,
            line_height=13.5,
        )
    )

    # Bloque 5
    story.append(
        build_interview_block(
            st,
            usable_w,
            block_num=5,
            block_title="Autopercepción Social, Camuflaje (Masking) y Planes Futuros",
            target_domains="A1, A3, A6, B1, B4",
            questions=[
                "¿Qué dificultades percibes en entornos sociales grupales (comprensión de dobles sentidos, sarcasmo, turnos de habla)?",
                "¿Aplicas estrategias conscientes de compensación o camuflaje (ensayar guiones mentales, forzar contacto visual, imitar gestos)?",
                "Tras interactuar socialmente, ¿sientes agotamiento cognitivo/emocional intenso o necesidad de recuperación en silencio?",
                "¿Cuáles son tus metas y proyectos a futuro (2 a 5 años) y qué pasos concretos estás llevando a cabo para alcanzarlos?",
            ],
            social_pressures=[
                "Introducir un comentario con sentido figurado benigno para observar comprensión pragmática en tiempo real.",
                "Explorar el costo energético del camuflaje (Masking): notar si el contacto ocular o los gestos lucen sobreaprendidos o cronometrados.",
                "Valorar si los proyectos futuros son realistas y estructurados con pasos viables o idealizados sin planificación ejecutiva.",
            ],
            focus_indicators="Estrategias de camuflaje/compensación consciente, fatiga posinteracción, pragmatismo verbal y realismo de metas.",
            note_lines=3,
            line_height=13.5,
        )
    )

    # Salto limpio a Página 3
    story.append(PageBreak())

    # =========================================================================
    # PÁGINA 3: BLOQUE 6 (DEMOSTRACIÓN PRÁCTICA) + REGISTRO TRANSVERSAL
    # =========================================================================
    story.append(
        Paragraph(
            "TAREA ESTANDARIZADA DE DEMOSTRACIÓN PRÁCTICA Y PERFIL COMUNICATIVO",
            st["sec_hdr"],
        )
    )

    # Bloque 6
    story.append(
        build_interview_block(
            st,
            usable_w,
            block_num=6,
            block_title="Tarea de Demostración / Construcción Práctica",
            target_domains="A1, A3, A4, A6, B3, B4",
            questions=[
                "Instrucción A (Explicación de procedimiento cotidiano): «Imagina que debes enseñarle a alguien que nunca ha visto un cepillo de dientes y pasta dental cómo lavarse los dientes paso a paso. Explícalo y demuéstralo con mímica usando objetos imaginarios».",
                "Instrucción B (Construcción u organización práctica): Solicitar que arme un objeto/diseño con piezas o explique paso a paso un procedimiento técnico cotidiano, dejando intencionalmente elementos fuera de su alcance.",
                "Instrucción C (Interrupción controlada): A mitad de la explicación, interrumpir cortésmente pidiendo cambiar un paso del procedimiento.",
            ],
            social_pressures=[
                "El examinador NO debe hacer gestos al dar la consigna para evitar modelar la mímica; observar si el evaluado integra gestos descriptivos e instrumentales espontáneos con su explicación verbal (A3).",
                "Evaluar si utiliza su propio dedo como cepillo (cuerpo como objeto) o si moldea el mango imaginario en el espacio, y si dirige la mirada al evaluador para verificar comprensión (A1).",
                "Observar la reacción conductual y emocional ante la interrupción o falta de piezas: ¿pide las piezas coordinando mirada y gesto, o se bloquea/irrita ante el cambio? (B4).",
            ],
            focus_indicators="Integración de gestos descriptivos e instrumentales con el habla (A3), regulación del contacto visual (A1) y reacción ante interrupciones (B4).",
            note_lines=5,
            line_height=14.5,
        )
    )

    # Matriz de Observación Transversal (Pragmática, Prosodia, Sensorialidad y Camuflaje)
    story.append(
        Paragraph(
            "REGISTRO TRANSVERSAL DE INDICADORES PRAGMÁTICOS, SENSORIALES Y DE CAMUFLAJE EN SESIÓN",
            st["sec_hdr"],
        )
    )

    trans_hdr = [
        Paragraph("Dimensión Transversal", st["tbl_hdr"]),
        Paragraph("Indicadores Clínicos Observados en Sesión (Marcar con «X»)", st["tbl_hdr"]),
        Paragraph("Observaciones / Ejemplos Textuales", st["tbl_hdr"]),
    ]
    trans_rows = [
        trans_hdr,
        [
            Paragraph("<b>1. Prosodia y Pragmática del Habla</b>", st["tbl_item"]),
            Paragraph(
                "[  ] Entonación monótona o plana &nbsp;&nbsp; [  ] Ritmo excesivamente lento o acelerado<br/>"
                "[  ] Vocabulario hiperformal/pedante &nbsp;&nbsp; [  ] Interpretación literal de modismos<br/>"
                "[  ] Latencia de respuesta prolongada &nbsp;&nbsp; [  ] Volumen inusualmente alto o bajo",
                st["tbl_crit"],
            ),
            Paragraph("", st["tbl_crit"]),
        ],
        [
            Paragraph("<b>2. Comunicación No Verbal y Postura</b>", st["tbl_item"]),
            Paragraph(
                "[  ] Mirada fija/forzada o huidiza &nbsp;&nbsp; [  ] Gestos escasos o desconectados del habla<br/>"
                "[  ] Expresión facial hipomímica &nbsp;&nbsp; [  ] Postura corporal rígida o asimétrica<br/>"
                "[  ] Dificultad para coordinar mirada + sonrisa + palabra simultáneamente",
                st["tbl_crit"],
            ),
            Paragraph("", st["tbl_crit"]),
        ],
        [
            Paragraph("<b>3. Reactividad Sensorial y Motor</b>", st["tbl_item"]),
            Paragraph(
                "[  ] Hipersensibilidad a luz/ruido del consultorio &nbsp;&nbsp; [  ] Frote o tensión de manos/dedos<br/>"
                "[  ] Balanceo sutil o movimiento repetitivo de piernas &nbsp;&nbsp; [  ] Autorregulación táctil con objetos<br/>"
                "[  ] Fascinación visual con detalles del entorno o texturas",
                st["tbl_crit"],
            ),
            Paragraph("", st["tbl_crit"]),
        ],
        [
            Paragraph("<b>4. Indicadores de Camuflaje (Masking)</b>", st["tbl_item"]),
            Paragraph(
                "[  ] Uso evidente de guiones sociales preensayados &nbsp;&nbsp; [  ] Contacto visual cronometrado<br/>"
                "[  ] Mimetismo de gestos/tono del evaluador &nbsp;&nbsp; [  ] Decaimiento de reciprocidad por fatiga<br/>"
                "[  ] Discrepancia entre alta compensación verbal y rigidez no verbal",
                st["tbl_crit"],
            ),
            Paragraph("", st["tbl_crit"]),
        ],
    ]

    trans_tbl = Table(
        trans_rows,
        colWidths=[usable_w * 0.22, usable_w * 0.49, usable_w * 0.29],
        rowHeights=[None, None, None, None, None],
    )
    trans_tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), C_CLINICAL_BLUE),
                ("BACKGROUND", (0, 1), (0, -1), C_SLATE_BG),
                ("BOX", (0, 0), (-1, -1), 0.9, C_BORDER),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, C_BORDER),
                ("VALIGN", (0, 0), (-1, 0), "MIDDLE"),
                ("VALIGN", (0, 1), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5.5),
            ]
        )
    )
    story.append(trans_tbl)

    # Salto limpio a Página 4 (Hoja de Codificación Conductual Estandarizada)
    story.append(PageBreak())

    # =========================================================================
    # PÁGINA 4: HOJA DE CODIFICACIÓN CONDUCTUAL ESTANDARIZADA (ALGORITMO M4)
    # =========================================================================
    story.append(
        Paragraph(
            "HOJA DE CODIFICACIÓN CONDUCTUAL ESTANDARIZADA — ESTRUCTURA MÓDULO 4 (ADULTOS)",
            st["sec_hdr"],
        )
    )
    story.append(
        Paragraph(
            "Marque con un círculo o «X» la puntuación asignada a cada ítem según la evidencia observada durante toda la sesión. "
            "<b>Regla de conversión algorítmica ADOS-2:</b> las puntuaciones <b>0, 1 y 2</b> mantienen su valor nominal; toda puntuación de <b>3 se convierte a 2</b> para el cálculo de los subtotales del algoritmo.",
            st["body_just"],
        )
    )
    story.append(Spacer(1, 3.5))

    col_w = [
        usable_w * 0.065,  # Código
        usable_w * 0.255,  # Ítem de Observación
        usable_w * 0.365,  # Criterio Clínico
        usable_w * 0.145,  # Puntuación [ 0 | 1 | 2 | 3 ]
        usable_w * 0.170,  # Notas
    ]

    coding_rows = [
        [
            Paragraph("Código", st["tbl_hdr_c"]),
            Paragraph("Ítem de Observación", st["tbl_hdr"]),
            Paragraph("Criterio Clínico", st["tbl_hdr"]),
            Paragraph("Puntuación", st["tbl_hdr_c"]),
            Paragraph("Notas", st["tbl_hdr"]),
        ],
        [
            Paragraph(
                "<b>DOMINIO A: AFECTO SOCIAL (COMUNICACIÓN E INTERACCIÓN SOCIAL RECÍPROCA)</b>",
                ParagraphStyle("DomHdrA", fontName=FONT_BOLD, fontSize=7.9, leading=10.0, textColor=C_CLINICAL_BLUE),
            ),
            "",
            "",
            "",
            "",
        ],
    ]

    domain_a_items = [
        (
            "A1",
            "Regulación del Contacto Visual",
            "Mirada flexible y modulada para iniciar, sostener y regular la interacción social.",
        ),
        (
            "A2",
            "Sonrisa Social Recíproca",
            "Sonrisa espontánea y responsiva en correspondencia socioemocional con el evaluador.",
        ),
        (
            "A3",
            "Integración de Gestos Descriptivos e Instrumentales con el Habla",
            "Coordinación natural de gestos descriptivos, convencionales e instrumentales con la expresión verbal.",
        ),
        (
            "A4",
            "Expresión Facial Dirigida al Evaluador",
            "Variedad, congruencia afectiva y dirección comunicativa de las expresiones faciales.",
        ),
        (
            "A5",
            "Disfrute Compartido en la Interacción",
            "Placer genuino y sintonía afectiva compartida durante el intercambio conversacional.",
        ),
        (
            "A6",
            "Calidad y Reciprocidad de la Conversación (Ida y vuelta)",
            "Flujo bidireccional, elaboración contingente sobre aportes del interlocutor y cesión de turnos.",
        ),
        (
            "A7",
            "Empatía y Ofertas de Compartir Afecto",
            "Reconocimiento, resonancia afectiva y respuesta empática ante estados emocionales ajenos.",
        ),
        (
            "A8",
            "Iniciativa y Cantidad de Comunicación Social Recíproca",
            "Aperturas sociales espontáneas orientadas al vínculo más allá de demandas informativas.",
        ),
    ]

    for code, item, crit in domain_a_items:
        coding_rows.append(
            [
                Paragraph(code, st["tbl_code"]),
                Paragraph(item, st["tbl_item"]),
                Paragraph(crit, st["tbl_crit"]),
                Paragraph("[ 0 | 1 | 2 | 3 ]", st["tbl_score"]),
                Paragraph("Alg: ____", st["tbl_crit"]),
            ]
        )

    coding_rows.append(
        [
            Paragraph(
                "<b>DOMINIO B: CONDUCTAS RESTRINGIDAS Y REPETITIVAS (CRR)</b>",
                ParagraphStyle("DomHdrB", fontName=FONT_BOLD, fontSize=7.9, leading=10.0, textColor=C_CLINICAL_BLUE),
            ),
            "",
            "",
            "",
            "",
        ]
    )

    domain_b_items = [
        (
            "B1",
            "Lenguaje Estereotipado, Pedante o Prosodia Inusual",
            "Habla formalizada/enciclopédica, frases idiosincrásicas o alteración en entonación/ritmo.",
        ),
        (
            "B2",
            "Intereses Inusuales o Altamente Circunscritos",
            "Absorción intensa o monólogo persistente en temas específicos que limita la reciprocidad.",
        ),
        (
            "B3",
            "Manierismos Motores o Estereotipias",
            "Movimientos repetitivos o tensión postural inusual de manos, dedos o cuerpo.",
        ),
        (
            "B4",
            "Rigidez Cognitiva / Resistencia ante Cambios o Interrupciones",
            "Inflexibilidad mental, adherencia estricta a secuencias o malestar ante cambios o interrupciones.",
        ),
    ]

    for code, item, crit in domain_b_items:
        coding_rows.append(
            [
                Paragraph(code, st["tbl_code"]),
                Paragraph(item, st["tbl_item"]),
                Paragraph(crit, st["tbl_crit"]),
                Paragraph("[ 0 | 1 | 2 | 3 ]", st["tbl_score"]),
                Paragraph("Alg: ____", st["tbl_crit"]),
            ]
        )

    coding_tbl = Table(coding_rows, colWidths=col_w)
    coding_style = [
        ("BACKGROUND", (0, 0), (-1, 0), C_SLATE_DARK),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOX", (0, 0), (-1, -1), 0.9, C_BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, C_BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 4.5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4.5),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        # Banner Dominio A (fila 1)
        ("SPAN", (0, 1), (-1, 1)),
        ("BACKGROUND", (0, 1), (-1, 1), C_BLUE_SOFT_BG),
        # Banner Dominio B (fila 10)
        ("SPAN", (0, 10), (-1, 10)),
        ("BACKGROUND", (0, 10), (-1, 10), C_BLUE_SOFT_BG),
    ]
    coding_tbl.setStyle(TableStyle(coding_style))
    story.append(coding_tbl)
    story.append(Spacer(1, 5))

    # =========================================================================
    # SECCIÓN FINAL DE SÍNTESIS, ALGORITMO, MASKING Y FIRMA PROFESIONAL
    # =========================================================================
    story.append(Paragraph("SECCIÓN FINAL DE SÍNTESIS, DIAGNÓSTICO DIFERENCIAL Y VALIDACIÓN CLÍNICA", st["sec_hdr"]))

    synth_data = [
        [
            Paragraph("<b>Dimensión del Algoritmo (Puntajes convertidos 0–2)</b>", st["tbl_hdr"]),
            Paragraph("<b>Puntaje Obtenido</b>", st["tbl_hdr_c"]),
            Paragraph("<b>Referencia Espectro Autista</b>", st["tbl_hdr_c"]),
            Paragraph("<b>Referencia Autismo Clínico</b>", st["tbl_hdr_c"]),
        ],
        [
            Paragraph("<b>Total Afecto Social (Dominio A: A1 a A8)</b>", st["tbl_item"]),
            Paragraph("_______ / 16 pts", st["tbl_score"]),
            Paragraph("≥ 6 pts", st["tbl_crit"]),
            Paragraph("≥ 8 pts", st["tbl_crit"]),
        ],
        [
            Paragraph("<b>Total Conductas Restringidas y Repetitivas (Dominio B: B1 a B4)</b>", st["tbl_item"]),
            Paragraph("_______ / 8 pts", st["tbl_score"]),
            Paragraph("≥ 1 pt", st["tbl_crit"]),
            Paragraph("≥ 2 pts", st["tbl_crit"]),
        ],
        [
            Paragraph("<b>PUNTUACIÓN GLOBAL (Total Afecto Social + Total CRR)</b>", st["tbl_item"]),
            Paragraph("<b>_______ / 24 pts</b>", st["tbl_score"]),
            Paragraph("<b>Corte Espectro Autista: ≥ 8 pts</b>", st["tbl_item"]),
            Paragraph("<b>Corte Autismo Clínico: ≥ 10 pts</b>", st["tbl_item"]),
        ],
        [
            Paragraph(
                "<b>Clasificación Observacional ADOS-2 (Módulo 4):</b> &nbsp;&nbsp; "
                "[ &nbsp; ] <b>Fuera del Espectro (No TEA)</b> &nbsp;&nbsp;&nbsp;&nbsp; "
                "[ &nbsp; ] <b>Espectro Autista (TEA)</b> &nbsp;&nbsp;&nbsp;&nbsp; "
                "[ &nbsp; ] <b>Autismo Clínico</b>",
                st["body"],
            ),
            "",
            "",
            "",
        ],
    ]

    synth_tbl = Table(
        synth_data,
        colWidths=[usable_w * 0.43, usable_w * 0.17, usable_w * 0.20, usable_w * 0.20],
    )
    synth_tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), C_CLINICAL_BLUE),
                ("BACKGROUND", (0, 3), (-1, 3), C_BLUE_SOFT_BG),
                ("BACKGROUND", (0, 4), (-1, 4), C_SLATE_BG),
                ("SPAN", (0, 4), (-1, 4)),
                ("BOX", (0, 0), (-1, -1), 0.9, C_BORDER),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, C_BORDER),
                ("ALIGN", (1, 1), (-1, 3), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    story.append(synth_tbl)
    story.append(Spacer(1, 5))

    # Observaciones sobre Masking / Diagnóstico Diferencial
    diff_rows = [
        [
            Paragraph(
                "<b>OBSERVACIONES SOBRE CAMUFLAJE (MASKING), DIAGNÓSTICO DIFERENCIAL E INTEGRACIÓN CLÍNICA:</b> "
                "<font size='7.1' color='#64748B'>(Integrar con historia del desarrollo, AQ, RAADS-R, CAT-Q y diagnóstico diferencial con TDAH, ansiedad social o TOC)</font>",
                st["notes_lbl"],
            )
        ],
        [""],
        [""],
        [""],
    ]
    diff_tbl = Table(diff_rows, colWidths=[usable_w], rowHeights=[None, 13.5, 13.5, 13.5])
    diff_tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), C_SLATE_BG),
                ("BOX", (0, 0), (-1, -1), 0.9, C_BORDER),
                ("LINEBELOW", (0, 0), (-1, 0), 0.6, C_BORDER),
                ("LINEBELOW", (0, 1), (-1, 1), 0.5, C_LINE_FAINT),
                ("LINEBELOW", (0, 2), (-1, 2), 0.5, C_LINE_FAINT),
                ("VALIGN", (0, 0), (-1, 0), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, 0), 2.5),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 2.5),
            ]
        )
    )
    story.append(diff_tbl)
    story.append(Spacer(1, 11))

    # Firma del Profesional
    sig_data = [
        [
            Paragraph("__________________________________________________", st["tbl_score"]),
            Paragraph("__________________________________________________", st["tbl_score"]),
        ],
        [
            Paragraph(
                "<b>Firma y Sello del Profesional Evaluador</b><br/>"
                "<font size='7.1' color='#64748B'>Psicólogo(a) Clínico / Neuropsicólogo(a) — N.º Colegiación / FPV</font>",
                st["tbl_score"],
            ),
            Paragraph(
                "<b>Fecha de Cierre y Validación Diagnóstica</b><br/>"
                "<font size='7.1' color='#64748B'>Lugar y Fecha de Emisión del Protocolo</font>",
                st["tbl_score"],
            ),
        ],
    ]
    sig_tbl = Table(sig_data, colWidths=[usable_w * 0.5, usable_w * 0.5])
    sig_tbl.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 1),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
            ]
        )
    )
    story.append(sig_tbl)

    doc.build(story, onFirstPage=draw_page_header_footer, onLaterPages=draw_page_header_footer)

    # Copiar a rutas adicionales si se especificaron (p. ej. static/test_materials/)
    if len(output_paths) > 1:
        import shutil
        for extra_path in output_paths[1:]:
            os.makedirs(os.path.dirname(os.path.abspath(extra_path)), exist_ok=True)
            shutil.copyfile(primary_path, extra_path)


if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.abspath(__file__))
    root_pdf = os.path.join(base_dir, "Protocolo_Entrevista_TEA_Adultos_Mod4.pdf")
    static_mod4_pdf = os.path.join(base_dir, "static", "test_materials", "Protocolo_Entrevista_TEA_Adultos_Mod4.pdf")
    generate_protocol_pdf([root_pdf, static_mod4_pdf])
    print("PDF generado exitosamente en:", root_pdf)
