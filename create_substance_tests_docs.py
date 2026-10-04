# -*- coding: utf-8 -*-
"""
Script para generar los documentos Word (.docx) oficiales de los tests:
1. CAST (Cannabis Abuse Screening Test)
2. CUDIT-R (Cannabis Use Disorders Identification Test - Revised)
en la carpeta 'Test psicologicos/Abuso de sustancias'.
"""

import os
import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml import parse_xml, OxmlElement
from docx.oxml.ns import nsdecls, qn

def set_cell_background(cell, fill_hex):
    tcPr = cell._tc.get_or_add_tcPr()
    tcPr.append(parse_xml(f'<w:shd {nsdecls("w")} w:fill="{fill_hex}"/>'))

def set_cell_margins(cell, top=100, bottom=100, left=150, right=150):
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = parse_xml(f'<w:tcMar {nsdecls("w")}><w:top w:w="{top}" w:type="dxa"/><w:bottom w:w="{bottom}" w:type="dxa"/><w:left w:w="{left}" w:type="dxa"/><w:right w:w="{right}" w:type="dxa"/></w:tcMar>')
    tcPr.append(tcMar)

def create_cast_document(output_path):
    doc = docx.Document()
    
    # Configuración de márgenes
    for section in doc.sections:
        section.top_margin = Inches(0.8)
        section.bottom_margin = Inches(0.8)
        section.left_margin = Inches(0.85)
        section.right_margin = Inches(0.85)
        
    # Título Principal
    p_title = doc.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run_title = p_title.add_run("TEST CAST\nCANNABIS ABUSE SCREENING TEST")
    run_title.font.name = 'Calibri'
    run_title.font.size = Pt(20)
    run_title.font.bold = True
    run_title.font.color.rgb = RGBColor(112, 46, 94) # Color institucional
    
    p_sub = doc.add_paragraph()
    p_sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run_sub = p_sub.add_run("Cuestionario de Despistaje de Consumo Problemático de Cannabis\nCuadernillo de Aplicación, Algoritmo de Corrección y Baremos Clínicos")
    run_sub.font.name = 'Calibri'
    run_sub.font.size = Pt(11)
    run_sub.font.italic = True
    run_sub.font.color.rgb = RGBColor(100, 116, 139)
    
    doc.add_paragraph().paragraph_format.space_after = Pt(6)
    
    # 1. FICHA TÉCNICA
    h1 = doc.add_paragraph()
    r_h1 = h1.add_run("1. FICHA TÉCNICA")
    r_h1.font.name = 'Calibri'
    r_h1.font.size = Pt(13)
    r_h1.font.bold = True
    r_h1.font.color.rgb = RGBColor(112, 46, 94)
    h1.paragraph_format.space_after = Pt(4)
    
    ficha_data = [
        ("Nombre original:", "Cannabis Abuse Screening Test (CAST)"),
        ("Autores:", "Stéphane Legleye, Michel Karila, François Beck & Michel Reynaud (2007)."),
        ("Adaptaciones y validación:", "Observatorio Europeo de las Drogas y las Toxicomanías (EMCDDA), Observatorio Español sobre Drogas y Adicciones (OEDA), Observatorio Peruano de Drogas (DEVIDA, 2014)."),
        ("Objetivo:", "Identificar de forma breve y sensible el consumo problemático y de riesgo de cannabis en adolescentes y adultos jóvenes en los últimos 12 meses."),
        ("Nº de ítems:", "6 preguntas en escala tipo Likert de 5 opciones (0 = Nunca a 4 = Muy a menudo)."),
        ("Tiempo de aplicación:", "Aproximadamente 2 a 3 minutos (autoaplicado o heteroaplicado en entrevista clínica)."),
        ("Confiabilidad:", "Alfa de Cronbach α = 0.78 a 0.82; excelente consistencia interna y validez convergente con criterios diagnósticos DSM-IV/DSM-5 y CIE-10.")
    ]
    
    table_ficha = doc.add_table(rows=len(ficha_data), cols=2)
    table_ficha.alignment = WD_TABLE_ALIGNMENT.CENTER
    table_ficha.autofit = False
    
    for row_idx, (k, v) in enumerate(ficha_data):
        row = table_ficha.rows[row_idx]
        cell_k, cell_v = row.cells[0], row.cells[1]
        cell_k.width = Inches(2.2)
        cell_v.width = Inches(4.5)
        set_cell_margins(cell_k, 50, 50, 80, 80)
        set_cell_margins(cell_v, 50, 50, 80, 80)
        set_cell_background(cell_k, "F8FAFC")
        
        p_k = cell_k.paragraphs[0]
        r_k = p_k.add_run(k)
        r_k.font.bold = True
        r_k.font.size = Pt(9.5)
        
        p_v = cell_v.paragraphs[0]
        r_v = p_v.add_run(v)
        r_v.font.size = Pt(9.5)
        
    doc.add_paragraph().paragraph_format.space_after = Pt(8)
    
    # 2. CUADERNILLO DE APLICACIÓN
    h2 = doc.add_paragraph()
    r_h2 = h2.add_run("2. CUADERNILLO DE APLICACIÓN (PARA EL PACIENTE)")
    r_h2.font.name = 'Calibri'
    r_h2.font.size = Pt(13)
    r_h2.font.bold = True
    r_h2.font.color.rgb = RGBColor(112, 46, 94)
    h2.paragraph_format.space_after = Pt(4)
    
    p_inst = doc.add_paragraph()
    r_inst = p_inst.add_run("Instrucciones: ")
    r_inst.font.bold = True
    p_inst.add_run("A continuación se presentan 6 preguntas acerca de sus hábitos y experiencias con respecto al consumo de cannabis (marihuana, hachís, aceite o derivados) durante los últimos 12 meses. Por favor, marque con una equis (X) la opción que mejor describa su situación en cada caso.")
    p_inst.paragraph_format.space_after = Pt(8)
    
    # Encabezado paciente
    table_pac = doc.add_table(rows=2, cols=2)
    table_pac.alignment = WD_TABLE_ALIGNMENT.CENTER
    table_pac.rows[0].cells[0].paragraphs[0].add_run("Nombre del consultante: ________________________________________").font.size = Pt(9.5)
    table_pac.rows[0].cells[1].paragraphs[0].add_run("Fecha: ____/____/________").font.size = Pt(9.5)
    table_pac.rows[1].cells[0].paragraphs[0].add_run("Edad: _____ años    Sexo: [  ] M   [  ] F").font.size = Pt(9.5)
    table_pac.rows[1].cells[1].paragraphs[0].add_run("Evaluador(a): _________________________").font.size = Pt(9.5)
    
    doc.add_paragraph().paragraph_format.space_after = Pt(6)
    
    # Tabla de preguntas CAST
    preguntas_cast = [
        ("1", "¿Has fumado cannabis antes del mediodía?", "0 = Nunca", "1 = Raramente / Casi nunca", "2 = De vez en cuando", "3 = Bastante a menudo", "4 = Muy a menudo"),
        ("2", "¿Has fumado cannabis cuando estabas solo/a?", "0 = Nunca", "1 = Raramente / Casi nunca", "2 = De vez en cuando", "3 = Bastante a menudo", "4 = Muy a menudo"),
        ("3", "¿Has tenido problemas de memoria al fumar cannabis?", "0 = Nunca", "1 = Raramente / Casi nunca", "2 = De vez en cuando", "3 = Bastante a menudo", "4 = Muy a menudo"),
        ("4", "¿Te han dicho amigos o miembros de tu familia que deberías reducir tu consumo de cannabis?", "0 = Nunca", "1 = Raramente / Casi nunca", "2 = De vez en cuando", "3 = Bastante a menudo", "4 = Muy a menudo"),
        ("5", "¿Has intentado reducir o dejar de consumir cannabis sin conseguirlo?", "0 = Nunca", "1 = Raramente / Casi nunca", "2 = De vez en cuando", "3 = Bastante a menudo", "4 = Muy a menudo"),
        ("6", "¿Has tenido problemas debido a tu consumo de cannabis (discusiones, peleas, accidentes, bajo rendimiento escolar o laboral, problemas legales)?", "0 = Nunca", "1 = Raramente / Casi nunca", "2 = De vez en cuando", "3 = Bastante a menudo", "4 = Muy a menudo")
    ]
    
    table_items = doc.add_table(rows=len(preguntas_cast) + 1, cols=7)
    table_items.alignment = WD_TABLE_ALIGNMENT.CENTER
    table_items.autofit = False
    
    col_widths = [Inches(0.4), Inches(2.7), Inches(0.7), Inches(0.7), Inches(0.7), Inches(0.7), Inches(0.7)]
    headers = ["Nº", "Pregunta (Últimos 12 meses)", "Nunca\n(0)", "Raras veces\n(1)", "A veces\n(2)", "A menudo\n(3)", "Muy a menudo\n(4)"]
    
    # Fila cabecera
    hdr_row = table_items.rows[0]
    for c_idx, title in enumerate(headers):
        cell = hdr_row.cells[c_idx]
        cell.width = col_widths[c_idx]
        set_cell_background(cell, "702E5E")
        set_cell_margins(cell, 80, 80, 50, 50)
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(title)
        r.font.bold = True
        r.font.size = Pt(8.5)
        r.font.color.rgb = RGBColor(255, 255, 255)
        
    for r_idx, item in enumerate(preguntas_cast):
        row = table_items.rows[r_idx + 1]
        for c_idx in range(7):
            cell = row.cells[c_idx]
            cell.width = col_widths[c_idx]
            set_cell_margins(cell, 60, 60, 50, 50)
            if r_idx % 2 == 1:
                set_cell_background(cell, "F9FAFB")
            p = cell.paragraphs[0]
            if c_idx == 0:
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                p.add_run(item[0]).font.bold = True
            elif c_idx == 1:
                p.alignment = WD_ALIGN_PARAGRAPH.LEFT
                p.add_run(item[1]).font.size = Pt(9)
            else:
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                r_box = p.add_run("[   ]")
                r_box.font.size = Pt(9)
                r_box.font.color.rgb = RGBColor(148, 163, 184)
                
    doc.add_paragraph().paragraph_format.space_after = Pt(10)
    
    # 3. ALGORITMO DE CORRECCIÓN Y BAREMO
    h3 = doc.add_paragraph()
    r_h3 = h3.add_run("3. ALGORITMO DE CORRECCIÓN Y BAREMO CLÍNICO")
    r_h3.font.name = 'Calibri'
    r_h3.font.size = Pt(13)
    r_h3.font.bold = True
    r_h3.font.color.rgb = RGBColor(112, 46, 94)
    h3.paragraph_format.space_after = Pt(4)
    
    p_alg = doc.add_paragraph()
    p_alg.add_run("La Escala CAST dispone de dos modalidades complementarias de corrección psicométrica validadas internacionalmente:\n")
    p_alg.add_run("A) Método de Puntuación Directa Aditiva Continua (0 a 24 puntos).\n").bold = True
    p_alg.add_run("B) Método Dicotomizado Oficial del Observatorio Europeo / OEDA / DEVIDA (0 a 6 puntos).\n").bold = True
    
    # Tabla Método A
    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    p_mA = doc.add_paragraph()
    p_mA.add_run("A) Baremo de Puntuación Directa Aditiva (Suma simple: 0 a 24 puntos):").bold = True
    
    table_baremo_a = doc.add_table(rows=4, cols=4)
    table_baremo_a.alignment = WD_TABLE_ALIGNMENT.CENTER
    col_w_a = [Inches(1.2), Inches(1.8), Inches(1.0), Inches(2.7)]
    hdr_a = ["Puntuación", "Clasificación Clínica", "Nivel de Alerta", "Significado y Conducta Sugerida"]
    
    for c_idx, title in enumerate(hdr_a):
        cell = table_baremo_a.rows[0].cells[c_idx]
        cell.width = col_w_a[c_idx]
        set_cell_background(cell, "334155")
        set_cell_margins(cell, 60, 60, 50, 50)
        p = cell.paragraphs[0]
        r = p.add_run(title)
        r.font.bold = True
        r.font.size = Pt(8.5)
        r.font.color.rgb = RGBColor(255, 255, 255)
        
    data_a = [
        ("0 a 2 puntos", "Consumo No Problemático", "Bajo / Verde", "Consumo experimental o recreativo esporádico. Sin evidencia de interferencia o dependencia. Recomendación: Prevención y psicoeducación."),
        ("3 a 6 puntos", "Consumo Problemático Moderado", "Moderado / Amarillo", "Consumo con signos de alarma o interferencia incipiente en actividades cotidianas. Recomendación: Intervención breve, balance decisional y monitoreo."),
        ("7 a 24 puntos", "Consumo Problemático de Alto Riesgo", "Severo / Rojo", "Fuerte sospecha de Trastorno por Consumo de Cannabis / Dependencia. Interferencia marcada en salud, relaciones y desempeño. Recomendación: Evaluación diagnóstica completa y tratamiento especializado.")
    ]
    for r_idx, (p_pts, p_clas, p_ale, p_sig) in enumerate(data_a):
        row = table_baremo_a.rows[r_idx + 1]
        vals = [p_pts, p_clas, p_ale, p_sig]
        for c_idx in range(4):
            cell = row.cells[c_idx]
            cell.width = col_w_a[c_idx]
            set_cell_margins(cell, 50, 50, 50, 50)
            p = cell.paragraphs[0]
            p.add_run(vals[c_idx]).font.size = Pt(8.5)
            
    doc.add_paragraph().paragraph_format.space_after = Pt(6)
    
    # Tabla Método B
    p_mB = doc.add_paragraph()
    p_mB.add_run("B) Baremo Oficial Dicotomizado (EMCDDA / OEDA / DEVIDA: 0 a 6 puntos):").bold = True
    p_mB_desc = doc.add_paragraph()
    p_mB_desc.add_run("• Ítems 1 y 2: Puntúa 1 si la respuesta es ≥ 2 ('De vez en cuando' o más); 0 si es Nunca/Raras veces.\n"
                       "• Ítems 3, 4, 5 y 6: Puntúa 1 si la respuesta es ≥ 1 ('Raras veces' o más); 0 si es Nunca.\n"
                       "• Puntuación dicotomizada = Suma de los 6 ítems binarios (0 a 6).")
    p_mB_desc.paragraph_format.space_after = Pt(4)
    
    table_baremo_b = doc.add_table(rows=4, cols=4)
    table_baremo_b.alignment = WD_TABLE_ALIGNMENT.CENTER
    hdr_b = ["Puntaje Dicotomizado", "Categoría Epidemiológica", "Nivel de Riesgo", "Correspondencia Clínica (DSM / CIE)"]
    
    for c_idx, title in enumerate(hdr_b):
        cell = table_baremo_b.rows[0].cells[c_idx]
        cell.width = col_w_a[c_idx]
        set_cell_background(cell, "702E5E")
        set_cell_margins(cell, 60, 60, 50, 50)
        p = cell.paragraphs[0]
        r = p.add_run(title)
        r.font.bold = True
        r.font.size = Pt(8.5)
        r.font.color.rgb = RGBColor(255, 255, 255)
        
    data_b = [
        ("0 a 1 punto", "No Problemático", "Bajo", "Consumidor sin criterios de riesgo o dependencia. No requiere intervención clínica intensiva."),
        ("2 a 3 puntos", "Problemático - Bajo/Medio Riesgo", "Moderado", "Consumo de riesgo incipiente. Al menos 2 criterios de abuso/dependencia presentes. Requiere asesoramiento breve."),
        ("4 a 6 puntos", "Problemático - Alto Riesgo", "Severo", "Cumple criterios equivalentes a Abuso/Dependencia severa (DSM-IV/DSM-5 / CIE-11). Sensibilidad > 90% para trastorno adictivo. Tratamiento ambulatorio o multidisciplinar.")
    ]
    for r_idx, (p_pts, p_clas, p_ale, p_sig) in enumerate(data_b):
        row = table_baremo_b.rows[r_idx + 1]
        vals = [p_pts, p_clas, p_ale, p_sig]
        for c_idx in range(4):
            cell = row.cells[c_idx]
            cell.width = col_w_a[c_idx]
            set_cell_margins(cell, 50, 50, 50, 50)
            p = cell.paragraphs[0]
            p.add_run(vals[c_idx]).font.size = Pt(8.5)
            
    doc.add_paragraph().paragraph_format.space_after = Pt(8)
    
    # 4. RECOMENDACIONES CLÍNICAS
    h4 = doc.add_paragraph()
    r_h4 = h4.add_run("4. ORIENTACIÓN Y PAUTAS DE INTERVENCIÓN")
    r_h4.font.name = 'Calibri'
    r_h4.font.size = Pt(13)
    r_h4.font.bold = True
    r_h4.font.color.rgb = RGBColor(112, 46, 94)
    h4.paragraph_format.space_after = Pt(4)
    
    p_rec = doc.add_paragraph()
    p_rec.add_run("• Consumo No Problemático (0-2 pts PD / 0-1 Dicot.): Reforzar estilos de vida saludables, brindar información sobre riesgos a largo plazo en memoria y cognición.\n"
                  "• Consumo Problemático Moderado (3-6 pts PD / 2-3 Dicot.): Aplicar Entrevista Motivacional (Miller & Rollnick), explorar situaciones detonantes (consumo en soledad o matutino), establecer metas de reducción o abstinencia acordadas.\n"
                  "• Consumo Problemático de Alto Riesgo (≥7 pts PD / ≥4 Dicot.): Terapia Cognitivo-Conductual para adicciones, entrenamiento en habilidades de afrontamiento, control de impulsos y valoración psiquiátrica si existe comorbilidad ansioso-depresiva.")
    
    doc.save(output_path)
    print(f"[OK] Documento creado exitosamente: {output_path}")


def create_cudit_r_document(output_path):
    doc = docx.Document()
    
    # Configuración de márgenes
    for section in doc.sections:
        section.top_margin = Inches(0.8)
        section.bottom_margin = Inches(0.8)
        section.left_margin = Inches(0.85)
        section.right_margin = Inches(0.85)
        
    # Título Principal
    p_title = doc.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run_title = p_title.add_run("TEST CUDIT-R\nCANNABIS USE DISORDERS IDENTIFICATION TEST - REVISED")
    run_title.font.name = 'Calibri'
    run_title.font.size = Pt(19)
    run_title.font.bold = True
    run_title.font.color.rgb = RGBColor(112, 46, 94)
    
    p_sub = doc.add_paragraph()
    p_sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run_sub = p_sub.add_run("Test de Identificación de Trastornos por Consumo de Cannabis (Versión Revisada)\nCuadernillo de Aplicación, Algoritmo de Corrección y Baremos Diagnósticos (DSM-5 / CIE-11)")
    run_sub.font.name = 'Calibri'
    run_sub.font.size = Pt(11)
    run_sub.font.italic = True
    run_sub.font.color.rgb = RGBColor(100, 116, 139)
    
    doc.add_paragraph().paragraph_format.space_after = Pt(6)
    
    # 1. FICHA TÉCNICA
    h1 = doc.add_paragraph()
    r_h1 = h1.add_run("1. FICHA TÉCNICA")
    r_h1.font.name = 'Calibri'
    r_h1.font.size = Pt(13)
    r_h1.font.bold = True
    r_h1.font.color.rgb = RGBColor(112, 46, 94)
    h1.paragraph_format.space_after = Pt(4)
    
    ficha_data = [
        ("Nombre original:", "Cannabis Use Disorders Identification Test - Revised (CUDIT-R)"),
        ("Autores:", "Anna Simon Adamson, Frances Kay-Lambkin, Amanda Baker, Terry Lewin, Margaret Thornton, Peter Kelly & Maree Teesson (2010)."),
        ("Fundamento:", "Adaptación psicométrica oficial del AUDIT de la Organización Mundial de la Salud (OMS) para el screening de trastornos por consumo de cannabis según criterios DSM-IV y DSM-5."),
        ("Objetivo:", "Evaluar frecuencia, intensidad, síntomas de dependencia y consecuencias negativas asociadas al consumo de cannabis en los últimos 6 meses."),
        ("Nº de ítems:", "8 ítems (Ítems 1 al 7 puntuados de 0 a 4; Ítem 8 puntuado 0, 2 o 4). Rango total: 0 a 32 puntos."),
        ("Tiempo de aplicación:", "Aproximadamente 3 a 5 minutos."),
        ("Propiedades psicométricas:", "Sensibilidad del 91% y especificidad del 90% para identificar Trastorno por Consumo de Cannabis en punto de corte ≥ 13. Alfa de Cronbach α = 0.84 a 0.91.")
    ]
    
    table_ficha = doc.add_table(rows=len(ficha_data), cols=2)
    table_ficha.alignment = WD_TABLE_ALIGNMENT.CENTER
    table_ficha.autofit = False
    
    for row_idx, (k, v) in enumerate(ficha_data):
        row = table_ficha.rows[row_idx]
        cell_k, cell_v = row.cells[0], row.cells[1]
        cell_k.width = Inches(2.2)
        cell_v.width = Inches(4.5)
        set_cell_margins(cell_k, 50, 50, 80, 80)
        set_cell_margins(cell_v, 50, 50, 80, 80)
        set_cell_background(cell_k, "F8FAFC")
        
        p_k = cell_k.paragraphs[0]
        r_k = p_k.add_run(k)
        r_k.font.bold = True
        r_k.font.size = Pt(9.5)
        
        p_v = cell_v.paragraphs[0]
        r_v = p_v.add_run(v)
        r_v.font.size = Pt(9.5)
        
    doc.add_paragraph().paragraph_format.space_after = Pt(8)
    
    # 2. CUADERNILLO DE APLICACIÓN
    h2 = doc.add_paragraph()
    r_h2 = h2.add_run("2. CUADERNILLO DE AUTOEVALUACIÓN (ÚLTIMOS 6 MESES)")
    r_h2.font.name = 'Calibri'
    r_h2.font.size = Pt(13)
    r_h2.font.bold = True
    r_h2.font.color.rgb = RGBColor(112, 46, 94)
    h2.paragraph_format.space_after = Pt(4)
    
    p_inst = doc.add_paragraph()
    r_inst = p_inst.add_run("Instrucciones: ")
    r_inst.font.bold = True
    p_inst.add_run("El cannabis incluye marihuana, hachís, hierba, 'blunts', porros, extractos o comestibles. Responda a las siguientes preguntas considerando su consumo durante los ÚLTIMOS 6 MESES. Marque con un círculo o equis (X) la opción que mejor se ajuste a su experiencia.")
    p_inst.paragraph_format.space_after = Pt(8)
    
    # Encabezado paciente
    table_pac = doc.add_table(rows=2, cols=2)
    table_pac.alignment = WD_TABLE_ALIGNMENT.CENTER
    table_pac.rows[0].cells[0].paragraphs[0].add_run("Nombre del consultante: ________________________________________").font.size = Pt(9.5)
    table_pac.rows[0].cells[1].paragraphs[0].add_run("Fecha: ____/____/________").font.size = Pt(9.5)
    table_pac.rows[1].cells[0].paragraphs[0].add_run("Edad: _____ años    Sexo: [  ] M   [  ] F").font.size = Pt(9.5)
    table_pac.rows[1].cells[1].paragraphs[0].add_run("Evaluador(a): _________________________").font.size = Pt(9.5)
    
    doc.add_paragraph().paragraph_format.space_after = Pt(6)
    
    # Items CUDIT-R
    items_cudit = [
        ("1", "¿Con qué frecuencia consumes cannabis?", [
            ("0", "Nunca"),
            ("1", "Mensualmente o menos"),
            ("2", "2 a 4 veces al mes"),
            ("3", "2 a 3 veces por semana"),
            ("4", "4 o más veces por semana")
        ]),
        ("2", "¿Cuántas horas estás 'colocado/a' o bajo los efectos del cannabis en un día típico en el que consumes?", [
            ("0", "Menos de 1 hora"),
            ("1", "1 a 2 horas"),
            ("2", "3 a 4 horas"),
            ("3", "5 a 6 horas"),
            ("4", "7 o más horas")
        ]),
        ("3", "¿Con qué frecuencia durante los últimos 6 meses te diste cuenta de que no podías parar de consumir cannabis una vez que habías empezado?", [
            ("0", "Nunca"),
            ("1", "Menos de una vez al mes"),
            ("2", "Mensualmente"),
            ("3", "Semanalmente"),
            ("4", "Diariamente o casi a diario")
        ]),
        ("4", "¿Con qué frecuencia durante los últimos 6 meses dejaste de hacer lo que normalmente se esperaba de ti debido al consumo de cannabis?", [
            ("0", "Nunca"),
            ("1", "Menos de una vez al mes"),
            ("2", "Mensualmente"),
            ("3", "Semanalmente"),
            ("4", "Diariamente o casi a diario")
        ]),
        ("5", "¿Con qué frecuencia durante los últimos 6 meses dedicaste una gran parte de tu tiempo a conseguir, consumir o recuperarte de los efectos del cannabis?", [
            ("0", "Nunca"),
            ("1", "Menos de una vez al mes"),
            ("2", "Mensualmente"),
            ("3", "Semanalmente"),
            ("4", "Diariamente o casi a diario")
        ]),
        ("6", "¿Con qué frecuencia durante los últimos 6 meses has tenido problemas de memoria o concentración después de haber consumido cannabis?", [
            ("0", "Nunca"),
            ("1", "Menos de una vez al mes"),
            ("2", "Mensualmente"),
            ("3", "Semanalmente"),
            ("4", "Diariamente o casi a diario")
        ]),
        ("7", "¿Con qué frecuencia durante los últimos 6 meses has consumido cannabis en situaciones que podrían ser físicamente peligrosas (ej. conducir vehículos, manejar maquinaria peligrosa, cuidar niños o personas a cargo)?", [
            ("0", "Nunca"),
            ("1", "Menos de una vez al mes"),
            ("2", "Mensualmente"),
            ("3", "Semanalmente"),
            ("4", "Diariamente o casi a diario")
        ]),
        ("8", "¿Alguna vez has pensado o intentado reducir o dejar de consumir cannabis?", [
            ("0", "Nunca"),
            ("2", "Sí, pero no en los últimos 6 meses"),
            ("4", "Sí, durante los últimos 6 meses"),
            ("", ""),
            ("", "")
        ])
    ]
    
    for item_num, pregunta, opciones in items_cudit:
        p_q = doc.add_paragraph()
        r_q_num = p_q.add_run(f"{item_num}. ")
        r_q_num.bold = True
        r_q_num.font.color.rgb = RGBColor(112, 46, 94)
        p_q.add_run(pregunta).bold = True
        p_q.paragraph_format.space_after = Pt(2)
        
        # Opciones en tabla horizontal
        t_opts = doc.add_table(rows=1, cols=len(opciones))
        t_opts.alignment = WD_TABLE_ALIGNMENT.CENTER
        t_opts.autofit = False
        
        for o_idx, (pts, opt_txt) in enumerate(opciones):
            cell = t_opts.rows[0].cells[o_idx]
            cell.width = Inches(6.7 / len(opciones))
            set_cell_margins(cell, 30, 30, 30, 30)
            set_cell_background(cell, "F8FAFC" if pts != "" else "FFFFFF")
            p = cell.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            if pts != "":
                p.add_run(f"[{pts} pts]\n").font.size = Pt(7.5)
                p.add_run(opt_txt).font.size = Pt(8)
            else:
                p.add_run("-").font.color.rgb = RGBColor(255, 255, 255)
        doc.add_paragraph().paragraph_format.space_after = Pt(4)
        
    doc.add_paragraph().paragraph_format.space_after = Pt(8)
    
    # 3. ALGORITMO DE CORRECCIÓN Y BAREMO
    h3 = doc.add_paragraph()
    r_h3 = h3.add_run("3. ALGORITMO DE CORRECCIÓN Y BAREMOS CLÍNICOS (CUDIT-R)")
    r_h3.font.name = 'Calibri'
    r_h3.font.size = Pt(13)
    r_h3.font.bold = True
    r_h3.font.color.rgb = RGBColor(112, 46, 94)
    h3.paragraph_format.space_after = Pt(4)
    
    p_sc = doc.add_paragraph()
    p_sc.add_run("Cálculo de la Puntuación Total:\n").bold = True
    p_sc.add_run("Sume las puntuaciones de cada uno de los 8 ítems (Ítems 1-7: valor de 0 a 4; Ítem 8: valor de 0, 2 o 4).\n"
                 "El puntaje total resultante oscila entre 0 y 32 puntos.")
    p_sc.paragraph_format.space_after = Pt(4)
    
    table_baremo = doc.add_table(rows=4, cols=4)
    table_baremo.alignment = WD_TABLE_ALIGNMENT.CENTER
    col_w_c = [Inches(1.2), Inches(1.8), Inches(1.0), Inches(2.7)]
    hdr_c = ["Puntuación Total", "Clasificación Diagnóstica", "Nivel de Riesgo", "Criterios Clínicos e Intervención Sugerida"]
    
    for c_idx, title in enumerate(hdr_c):
        cell = table_baremo.rows[0].cells[c_idx]
        cell.width = col_w_c[c_idx]
        set_cell_background(cell, "702E5E")
        set_cell_margins(cell, 60, 60, 50, 50)
        p = cell.paragraphs[0]
        r = p.add_run(title)
        r.font.bold = True
        r.font.size = Pt(8.5)
        r.font.color.rgb = RGBColor(255, 255, 255)
        
    data_c = [
        ("0 a 7 puntos", "Consumo de Bajo Riesgo / No Problemático", "Bajo / Verde", "No se evidencian criterios de consumo peligroso ni dependencia. Intervención: Psicoeducación preventiva general."),
        ("8 a 11 puntos", "Consumo de Riesgo / Uso Peligroso (Hazardous Use)", "Moderado / Amarillo", "Consumo en niveles que aumentan significativamente la probabilidad de consecuencias perjudiciales físicas, psicológicas o sociales. Intervención: Consejo breve motivacional, reducción de daños y seguimiento."),
        ("12 a 32 puntos", "Probable Trastorno por Consumo de Cannabis (TCC)", "Severo / Rojo", "Cumple criterios clínicos altamente probables para Trastorno por Consumo de Cannabis (DSM-5 / CIE-11). Sensibilidad > 91% en umbral ≥13. Requiere: Evaluación diagnóstica formal, intervención TCC especializada, prevención de recaídas y apoyo psiquiátrico si procede.")
    ]
    for r_idx, (p_pts, p_clas, p_ale, p_sig) in enumerate(data_c):
        row = table_baremo.rows[r_idx + 1]
        vals = [p_pts, p_clas, p_ale, p_sig]
        for c_idx in range(4):
            cell = row.cells[c_idx]
            cell.width = col_w_c[c_idx]
            set_cell_margins(cell, 50, 50, 50, 50)
            p = cell.paragraphs[0]
            p.add_run(vals[c_idx]).font.size = Pt(8.5)
            
    doc.add_paragraph().paragraph_format.space_after = Pt(6)
    
    # 4. SUBESCALAS Y DIMENSIONES EVALUADAS
    h4 = doc.add_paragraph()
    r_h4 = h4.add_run("4. DIMENSIONES CLÍNICAS EVALUADAS")
    r_h4.font.name = 'Calibri'
    r_h4.font.size = Pt(13)
    r_h4.font.bold = True
    r_h4.font.color.rgb = RGBColor(112, 46, 94)
    h4.paragraph_format.space_after = Pt(4)
    
    dims = [
        ("1. Patrón e Intensidad del Consumo (Ítems 1 y 2):", "Evalúa la frecuencia semanal/mensual y la duración del estado de intoxicación diaria (0 a 8 pts)."),
        ("2. Dependencia y Pérdida de Control (Ítems 3, 5 y 8):", "Mide la incapacidad de frenar el consumo una vez iniciado, el tiempo invertido en la sustancia y los intentos fallidos de abandono (0 a 12 pts)."),
        ("3. Consecuencias Psicosociales y Cognitivas (Ítems 4 y 6):", "Evalúa el incumplimiento de obligaciones y problemas de memoria o concentración derivados del uso (0 a 8 pts)."),
        ("4. Consumo en Situaciones Peligrosas (Ítem 7):", "Identifica conductas de alto riesgo físico como conducir o cuidar dependientes bajo efectos (0 a 4 pts).")
    ]
    for d_title, d_desc in dims:
        p_d = doc.add_paragraph()
        p_d.add_run(f"• {d_title} ").bold = True
        p_d.add_run(d_desc)
        p_d.paragraph_format.space_after = Pt(2)
        
    doc.save(output_path)
    print(f"[OK] Documento creado exitosamente: {output_path}")

if __name__ == '__main__':
    base_dir = r"Test psicologicos\Abuso de sustancias"
    cast_path = os.path.join(base_dir, "CAST - Cuestionario y Baremo de Correccion.docx")
    cudit_path = os.path.join(base_dir, "CUDIT-R - Cuestionario y Baremo de Correccion.docx")
    
    create_cast_document(cast_path)
    create_cudit_r_document(cudit_path)
