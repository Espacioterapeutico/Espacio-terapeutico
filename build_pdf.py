import os
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY

pdf_filename = "Informe_Costos_y_Modelo_Negocio_Mi_Consultorio.pdf"
doc = SimpleDocTemplate(
    pdf_filename,
    pagesize=letter,
    rightMargin=40,
    leftMargin=40,
    topMargin=40,
    bottomMargin=40
)

styles = getSampleStyleSheet()

# Estilos personalizados
title_style = ParagraphStyle(
    'DocTitle',
    parent=styles['Heading1'],
    fontName='Helvetica-Bold',
    fontSize=20,
    leading=24,
    textColor=colors.HexColor("#5D3A6F"),
    alignment=TA_CENTER,
    spaceAfter=6
)

subtitle_style = ParagraphStyle(
    'DocSubTitle',
    parent=styles['Normal'],
    fontName='Helvetica-Oblique',
    fontSize=10,
    leading=14,
    textColor=colors.HexColor("#6B7280"),
    alignment=TA_CENTER,
    spaceAfter=15
)

h1_style = ParagraphStyle(
    'Heading1_Custom',
    parent=styles['Heading2'],
    fontName='Helvetica-Bold',
    fontSize=13,
    leading=17,
    textColor=colors.HexColor("#5D3A6F"),
    spaceBefore=14,
    spaceAfter=8
)

body_style = ParagraphStyle(
    'Body_Custom',
    parent=styles['Normal'],
    fontName='Helvetica',
    fontSize=9.5,
    leading=13.5,
    textColor=colors.HexColor("#1F2937"),
    spaceAfter=6
)

bullet_style = ParagraphStyle(
    'Bullet_Custom',
    parent=body_style,
    leftIndent=15,
    spaceAfter=4
)

tbl_hdr_style = ParagraphStyle(
    'TblHdr',
    parent=styles['Normal'],
    fontName='Helvetica-Bold',
    fontSize=9,
    leading=11,
    textColor=colors.white,
    alignment=TA_CENTER
)

tbl_cell_style = ParagraphStyle(
    'TblCell',
    parent=styles['Normal'],
    fontName='Helvetica',
    fontSize=8.5,
    leading=11,
    textColor=colors.HexColor("#1F2937")
)

tbl_cell_bold = ParagraphStyle(
    'TblCellBold',
    parent=tbl_cell_style,
    fontName='Helvetica-Bold',
    textColor=colors.HexColor("#5D3A6F")
)

story = []

# Título y Subtítulo
story.append(Paragraph("Informe Técnico, Proyección de Costos y Modelo de Negocio", title_style))
story.append(Paragraph("Plataforma Mi Consultorio — Análisis de Escalabilidad e Infraestructura", subtitle_style))
story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#5D3A6F"), spaceAfter=15))

# Sección 1
story.append(Paragraph("1. 🛠️ Servicios Utilizados Actualmente", h1_style))
story.append(Paragraph("Actualmente la plataforma opera con una arquitectura multi-servicio basada en proveedores cloud de alto rendimiento con niveles gratuitos:", body_style))

data1 = [
    [Paragraph("Servicio", tbl_hdr_style), Paragraph("Función en la App", tbl_hdr_style), Paragraph("Plan Actual", tbl_hdr_style)],
    [Paragraph("PythonAnywhere", tbl_cell_bold), Paragraph("Servidor Backend (Python/Flask) y BD (SQLite)", tbl_cell_style), Paragraph("Gratuito (Free Tier)", tbl_cell_style)],
    [Paragraph("Render", tbl_cell_bold), Paragraph("Microservicio WhatsApp Web (Node.js + Baileys)", tbl_cell_style), Paragraph("Gratuito (Free Tier)", tbl_cell_style)],
    [Paragraph("Firebase (Google)", tbl_cell_bold), Paragraph("Notificaciones Push (FCM) y Realtime DB", tbl_cell_style), Paragraph("Gratuito (Spark)", tbl_cell_style)],
    [Paragraph("cron-job.org", tbl_cell_bold), Paragraph("Automatizador de tareas diarias (Recordatorios 8 AM)", tbl_cell_style), Paragraph("100% Gratuito", tbl_cell_style)],
    [Paragraph("GitHub", tbl_cell_bold), Paragraph("Alojamiento y control de versiones del código", tbl_cell_style), Paragraph("100% Gratuito", tbl_cell_style)]
]

t1 = Table(data1, colWidths=[1.4*inch, 3.8*inch, 1.8*inch])
t1.setStyle(TableStyle([
    ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#5D3A6F")),
    ('ALIGN', (0,0), (-1,-1), 'LEFT'),
    ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E5E7EB")),
    ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.HexColor("#F9F5FB"), colors.white]),
    ('TOPPADDING', (0,0), (-1,-1), 5),
    ('BOTTOMPADDING', (0,0), (-1,-1), 5),
]))
story.append(t1)
story.append(Spacer(1, 10))

# Sección 2
story.append(Paragraph("2. 📈 Proyección: Límites Gratuitos y Escalabilidad", h1_style))

story.append(Paragraph("<b>A. PythonAnywhere (Backend Flask):</b>", body_style))
story.append(Paragraph("• <b>Límite actual:</b> 512 MB de almacenamiento y 100 CPU-segundos diarios de procesamiento.", bullet_style))
story.append(Paragraph("• <b>Capacidad estimada:</b> Soporta entre 3 y 5 psicólogos activos usando la app diariamente, o ~150-200 peticiones diarias.", bullet_style))
story.append(Paragraph("• <b>Cuándo escalar:</b> Al superar los 5-7 psicólogos simultáneos o acumular más de 400 MB en fotos/adjuntos.", bullet_style))

story.append(Spacer(1, 4))
story.append(Paragraph("<b>B. Render (Microservicio WhatsApp Web):</b>", body_style))
story.append(Paragraph("• <b>Límite actual:</b> 750 horas mensuales (512 MB RAM). Se suspende ('duerme') tras 15 min sin tráfico.", bullet_style))
story.append(Paragraph("• <b>Capacidad estimada:</b> Soporta entre 10 y 15 sesiones de WhatsApp vinculadas simultáneamente.", bullet_style))
story.append(Paragraph("• <b>Cuándo escalar:</b> Cuando se requiera respuesta instantánea 24/7 sin tiempo de espera inicial o >15 psicólogos activos.", bullet_style))

story.append(Spacer(1, 4))
story.append(Paragraph("<b>C. Firebase FCM (Notificaciones Push):</b>", body_style))
story.append(Paragraph("• Notificaciones Push 100% ilimitadas y gratuitas de por vida respaldadas por la infraestructura de Google Cloud.", bullet_style))

story.append(Spacer(1, 10))

# Sección 3
story.append(Paragraph("3. 💵 Presupuesto de Mantención (Fase de Crecimiento)", h1_style))
story.append(Paragraph("Para mantener la plataforma funcionando 24/7 sin interrupciones ni tiempos de espera al escalar hasta 50 psicólogos:", body_style))

data2 = [
    [Paragraph("Concepto", tbl_hdr_style), Paragraph("Proveedor Sugerido", tbl_hdr_style), Paragraph("Costo Estimado", tbl_hdr_style)],
    [Paragraph("Servidor Web + BD", tbl_cell_bold), Paragraph("PythonAnywhere Hacker Plan / Render Web", tbl_cell_style), Paragraph("$5.00 - $7.00 USD / mes", tbl_cell_style)],
    [Paragraph("Microservicio WhatsApp", tbl_cell_bold), Paragraph("Render Starter Instance (24/7 activo)", tbl_cell_style), Paragraph("$7.00 USD / mes", tbl_cell_style)],
    [Paragraph("Dominio Propio", tbl_cell_bold), Paragraph("Dominio .com o .app (ej: miconsultorio.app)", tbl_cell_style), Paragraph("$1.00 USD / mes ($12/año)", tbl_cell_style)],
    [Paragraph("Asistente IA (Antigravity)", tbl_cell_bold), Paragraph("Licencia / Suscripción IA de desarrollo", tbl_cell_style), Paragraph("$20.00 USD / mes", tbl_cell_style)],
    [Paragraph("COSTO TOTAL MENSUAL", tbl_cell_bold), Paragraph("Mantenimiento integral 24/7", tbl_cell_bold), Paragraph("~$33.00 - $35.00 USD / mes", tbl_cell_bold)]
]

t2 = Table(data2, colWidths=[2.0*inch, 3.2*inch, 1.8*inch])
t2.setStyle(TableStyle([
    ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#5D3A6F")),
    ('ALIGN', (0,0), (-1,-1), 'LEFT'),
    ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E5E7EB")),
    ('ROWBACKGROUNDS', (0,1), (-1,-2), [colors.HexColor("#F9F5FB"), colors.white]),
    ('BACKGROUND', (0,-1), (-1,-1), colors.HexColor("#F3E8FF")),
    ('TOPPADDING', (0,0), (-1,-1), 5),
    ('BOTTOMPADDING', (0,0), (-1,-1), 5),
]))
story.append(t2)
story.append(Spacer(1, 10))

# Sección 4
story.append(Paragraph("4. 🏷️ Propuesta de Modelo de Negocio y Precios (SaaS)", h1_style))
story.append(Paragraph("Propuesta comercial de suscripción por terapeuta para rentabilizar la aplicación:", body_style))

story.append(Paragraph("• <b>Prueba Gratuita (Free Trial):</b> 7 Días de acceso completo para agendamiento y recordatorios por WhatsApp.", bullet_style))
story.append(Paragraph("• <b>Suscripción Mensual:</b> <b>$9.99 USD / mes</b> por psicólogo.", bullet_style))
story.append(Paragraph("• <b>Suscripción Trimestral:</b> <b>$24.99 USD / 3 meses</b> (Ahorra $5.00 USD).", bullet_style))
story.append(Paragraph("• <b>Suscripción Anual:</b> <b>$79.99 USD / año</b> (Equivalente a ~$6.60 USD / mes).", bullet_style))

story.append(Spacer(1, 6))
story.append(Paragraph("<b>⚖️ Punto de Equilibrio (Break-Even):</b>", body_style))
story.append(Paragraph("Con solo <b>4 psicólogos suscriptores</b> ($9.99/mes), la plataforma genera <b>$40.00 USD/mes</b>, cubriendo el 100% de los costos de servidores, microservicio de WhatsApp, dominio e IA. La aplicación se vuelve 100% autosustentable.", bullet_style))
story.append(Paragraph("Con <b>20 psicólogos suscriptores</b>, el ingreso bruto será de <b>$200.00 USD/mes</b> (~$165.00 USD de ganancia neta mensual).", bullet_style))
story.append(Paragraph("Con <b>50 psicólogos suscriptores</b>, el ingreso bruto será de <b>$500.00 USD/mes</b> (~$460.00 USD de ganancia neta mensual).", bullet_style))

doc.build(story)
print("PDF generado exitosamente:", pdf_filename)
