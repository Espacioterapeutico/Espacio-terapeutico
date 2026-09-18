"""
Módulo de Corrección Psicométrica Automatizada para el MCMI-II
(Inventario Multiaxial Clínico de Millon - 175 Reactivos)
Implementa los algoritmos mecanizados oficiales con baremos diferenciados
para Varones y Mujeres, ajustes de Sinceridad (X), Distorsión Depresiva (DD),
Ajuste Ansiedad/Depresión (DA) y Negación/Queja (DC).
"""

import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
NORMAS_FILE = os.path.join(BASE_DIR, "mcmi2_tb_normas.json")
RULES_FILE = os.path.join(BASE_DIR, "mcmi2_item_rules.json")

# Cargar reglas y baremos
with open(RULES_FILE, 'r', encoding='utf-8') as f:
    MCMI2_ITEM_RULES = json.load(f)

with open(NORMAS_FILE, 'r', encoding='utf-8') as f:
    MCMI2_NORMAS = json.load(f)

SCALE_METADATA = {
    "1": {"code": "1", "nombre": "Esquizoide", "cat": "Patrones Clínicos de Personalidad"},
    "2": {"code": "2", "nombre": "Fóbica (Evitativa)", "cat": "Patrones Clínicos de Personalidad"},
    "3": {"code": "3", "nombre": "Dependiente", "cat": "Patrones Clínicos de Personalidad"},
    "4": {"code": "4", "nombre": "Histriónica", "cat": "Patrones Clínicos de Personalidad"},
    "5": {"code": "5", "nombre": "Narcisista", "cat": "Patrones Clínicos de Personalidad"},
    "6A": {"code": "6A", "nombre": "Antisocial", "cat": "Patrones Clínicos de Personalidad"},
    "6B": {"code": "6B", "nombre": "Agresivo/Sádica", "cat": "Patrones Clínicos de Personalidad"},
    "7": {"code": "7", "nombre": "Compulsiva (Rígida)", "cat": "Patrones Clínicos de Personalidad"},
    "8A": {"code": "8A", "nombre": "Pasivo/Agresiva (Negativista)", "cat": "Patrones Clínicos de Personalidad"},
    "8B": {"code": "8B", "nombre": "Autodestructiva (Masoquista)", "cat": "Patrones Clínicos de Personalidad"},
    "S": {"code": "S", "nombre": "Esquizotípica", "cat": "Patología Grave de la Personalidad"},
    "C": {"code": "C", "nombre": "Límite (Borderline)", "cat": "Patología Grave de la Personalidad"},
    "P": {"code": "P", "nombre": "Paranoide", "cat": "Patología Grave de la Personalidad"},
    "A": {"code": "A", "nombre": "Ansiedad", "cat": "Síndromes Clínicos"},
    "H": {"code": "H", "nombre": "Histeriforme / Somatomorfo", "cat": "Síndromes Clínicos"},
    "N": {"code": "N", "nombre": "Hipomanía", "cat": "Síndromes Clínicos"},
    "D": {"code": "D", "nombre": "Neurosis Depresiva / Distimia", "cat": "Síndromes Clínicos"},
    "B": {"code": "B", "nombre": "Abuso de Alcohol", "cat": "Síndromes Clínicos"},
    "T": {"code": "T", "nombre": "Abuso de Drogas", "cat": "Síndromes Clínicos"},
    "SS": {"code": "SS", "nombre": "Pensamiento Psicótico", "cat": "Síndromes Clínicos Graves"},
    "CC": {"code": "CC", "nombre": "Depresión Mayor", "cat": "Síndromes Clínicos Graves"},
    "PP": {"code": "PP", "nombre": "Delirios Psicóticos", "cat": "Síndromes Clínicos Graves"},
    "V": {"code": "V", "nombre": "Validez", "cat": "Modificadores de Validez"},
    "X": {"code": "X", "nombre": "Sinceridad", "cat": "Modificadores de Validez"},
    "Y": {"code": "Y", "nombre": "Deseabilidad Social", "cat": "Modificadores de Validez"},
    "Z": {"code": "Z", "nombre": "Autodescalificación / Alteración", "cat": "Modificadores de Validez"}
}

SCALE_DESCRIPTIONS = {
    "1": "Distanciamiento de las relaciones sociales y restricción de la expresión emocional",
    "2": "Inhibición social, sentimientos de inferioridad e hipersensibilidad a la evaluación negativa",
    "3": "Necesidad excesiva de que se ocupen de uno, sumisión, adhesión y temores de separación",
    "4": "Excesiva emotividad y búsqueda de atención",
    "5": "Grandiosidad, necesidad de admiración y falta de empatía",
    "6A": "Patrón general de desprecio y violación de los derechos de los demás",
    "6B": "Patrón hostil, agresivo, abusador y destructivo",
    "7": "Preocupación por el orden, el perfeccionismo y el control, a expensas de la flexibilidad",
    "8A": "Sentimientos ambivalentes; pasividad y condescendencia que ocultan sentimientos oposicionistas",
    "8B": "En sus relaciones interpersonales fomentan que los demás les exploten y se aprovechen de ellos",
    "S": "Distorsiones cognitivas o perceptivas y excentricidades del comportamiento",
    "C": "Inestabilidad en las relaciones interpersonales, la autoimagen y los afectos, con notable impulsividad",
    "P": "Desconfianza y suspicacia generalizada hacia los demás",
    "A": "Tensión, aprensión, hiperactividad autonómica e inquietud",
    "H": "Preocupaciones somáticas recurrentes, fatiga e hipersensibilidad corporal",
    "N": "Períodos de euforia, hiperactividad, optimismo desmedido y menor necesidad de descanso",
    "D": "Desesperanza, desánimo persistente, baja autoestima e inhibición conductual",
    "B": "Historia o presencia de consumo problemático y recurrente de alcohol",
    "T": "Historia o presencia de consumo recurrente de sustancias psicoactivas",
    "SS": "Ideas delirantes, confusión, desconexión del entorno o alucinaciones",
    "CC": "Incapacidad para funcionar en el día a día, lentitud psicomotora y abatimiento profundo",
    "PP": "Creencias delirantes fijas, hostilidad velada o suspicacia persecutoria"
}

def eval_tokens(tokens, val):
    for op, target, res in tokens:
        if op == '<' and val < target: return res
        elif op == '<=' and val <= target: return res
        elif op in ('=', '==') and val == target: return res
        elif op == '>' and val > target: return res
        elif op == '>=' and val >= target: return res
    return 0

def get_x_factors(pd_x):
    ranges_x = [
        (144, 150, 11, 5), (149, 160, 10, 5), (159, 170, 9, 4),
        (169, 180, 8, 4), (179, 190, 7, 3), (189, 200, 6, 3),
        (199, 210, 5, 2), (209, 220, 4, 2), (219, 230, 3, 2),
        (229, 240, 2, 1), (239, 250, 1, 1)
    ]
    for low, high, f_x, f_half_x in ranges_x:
        if low < pd_x < high:
            return f_x, f_half_x
    return 0, 0

def process_mcmi2_scoring(answers, patient_info=None):
    """
    Procesa las respuestas de un test MCMI-II (175 reactivos) y calcula:
    - Puntuaciones Directas (PD)
    - Puntuaciones de Tasa Base (TB) ajustadas por baremos de Varones o Mujeres
    - Subescalas diagnósticas estructuradas
    - Interpretación clínica narrativa completa
    """
    patient_info = patient_info or {}
    genero_raw = str(patient_info.get('genero') or '').strip().lower()
    is_female = genero_raw in ('f', 'femenino', 'female', 'mujer')
    normas_key = 'mujeres' if is_female else 'varones'
    tables = MCMI2_NORMAS.get(normas_key, MCMI2_NORMAS['varones'])

    # Normalizar respuestas en enteros {item_int: val_int}
    norm_answers = {}
    for k, v in answers.items():
        try:
            it_num = int(str(k).replace('item_', ''))
            val = int(v)
            norm_answers[it_num] = val
        except (ValueError, TypeError):
            pass

    # 1. Puntuaciones Directas (PD)
    pd = {}
    for scale, rules in MCMI2_ITEM_RULES.items():
        if scale == 'X': continue
        score = 0
        for r in rules:
            if norm_answers.get(r['item']) == r['ans']:
                score += r['weight']
        pd[scale] = score

    # Puntuación Directa de X (Sinceridad)
    pd['X'] = round(
        (pd.get('4', 0) + pd.get('8A', 0)) * 1.5 +
        (pd.get('1', 0) + pd.get('2', 0) + pd.get('3', 0) + pd.get('8B', 0)) * 1.6 +
        (pd.get('5', 0) + pd.get('6A', 0) + pd.get('6B', 0) + pd.get('7', 0))
    )

    # 2. TB de la tabla bruta (Col C)
    tb_raw = {}
    for scale, tokens in tables.items():
        tb_raw[scale] = eval_tokens(tokens, pd.get(scale, 0))

    # 3. Factores correctores de Sinceridad (X)
    f_x, f_half_x = get_x_factors(pd['X'])

    col_d = {}
    for s in ['1', '2', '3', '4', '5', '6A', '6B', '7', '8A', '8B', 'A', 'H', 'N', 'D', 'B', 'T']:
        col_d[s] = tb_raw.get(s, 0) + f_x

    col_e = {}
    for s in ['S', 'C', 'P', 'SS', 'CC', 'PP']:
        col_e[s] = tb_raw.get(s, 0) + f_half_x

    # 4. Ajuste DA (Depresión / Ansiedad) para no hospitalizados (J1=0)
    d25 = col_d.get('D', 0)
    d22 = col_d.get('A', 0)
    if d25 < 85: av46 = 0
    elif d25 >= 85 and d22 < 85: av46 = d25 - 85
    else: av46 = (d25 - 85) + (d22 - 85)

    au48 = min(av46 / 4.0, 15.0)
    at48 = min(av46 / 2.0, 10.0)

    # 5. Ajuste DD (Diferencia Deseabilidad Y y Alteración Z)
    diff_yz = abs(tb_raw.get('Y', 0) - tb_raw.get('Z', 0))
    av50 = min(diff_yz / 10.0, 10.0)

    # 6. Ajuste DC (Negación / Queja)
    c_p = {s: tb_raw.get(s, 0) for s in ['1', '2', '3', '4', '5', '6A', '6B', '7', '8A', '8B']}
    bd56 = 0
    if all(c_p['4'] > c_p[s] for s in c_p if s != '4'): bd56 += 1
    if all(c_p['5'] > c_p[s] for s in c_p if s != '5'): bd56 += 1
    if all(c_p['7'] > c_p[s] for s in c_p if s != '7'): bd56 += 1

    bd62 = 0
    if all(c_p['8B'] > c_p[s] for s in c_p if s != '8B'): bd62 += 1
    if all(c_p['2'] > c_p[s] for s in c_p if s != '2'): bd62 += 1

    # 7. TB Final Definitiva
    final_tb = {}
    final_tb['Y'] = tb_raw.get('Y', 0)
    final_tb['Z'] = tb_raw.get('Z', 0)

    final_tb['1'] = col_d.get('1', 0)
    final_tb['2'] = round(col_d.get('2', 0) - au48)
    final_tb['3'] = col_d.get('3', 0)
    final_tb['4'] = col_d.get('4', 0)
    final_tb['5'] = col_d.get('5', 0)
    final_tb['6A'] = col_d.get('6A', 0)
    final_tb['6B'] = col_d.get('6B', 0)
    final_tb['7'] = col_d.get('7', 0)
    final_tb['8A'] = col_d.get('8A', 0)
    final_tb['8B'] = round(col_d.get('8B', 0) - au48)

    s_g = col_e.get('S', 0) + av50
    s_h = s_g + (4 if bd56 >= 1 else 0)
    final_tb['S'] = round(s_h - (2 if bd62 >= 1 else 0))

    c_f = col_e.get('C', 0) - at48
    c_g = c_f + av50
    c_h = c_g + (4 if bd56 >= 1 else 0)
    final_tb['C'] = round(c_h - (6 if bd62 >= 1 else 0))

    p_h = col_e.get('P', 0) + (2 if bd56 >= 1 else 0)
    final_tb['P'] = round(p_h - (6 if bd62 >= 1 else 0))

    a_g = col_d.get('A', 0) + av50
    a_h = a_g + (15 if bd56 >= 1 else 0)
    final_tb['A'] = round(a_h - (7 if bd62 >= 1 else 0))

    h_g = col_d.get('H', 0) + av50
    h_h = h_g + (13 if bd56 >= 1 else 0)
    final_tb['H'] = round(h_h - (5 if bd62 >= 1 else 0))

    final_tb['N'] = col_d.get('N', 0)

    d_g = col_d.get('D', 0) + av50
    d_h = d_g + (15 if bd56 >= 1 else 0)
    final_tb['D'] = round(d_h - (5 if bd62 >= 1 else 0))

    final_tb['B'] = col_d.get('B', 0)
    final_tb['T'] = col_d.get('T', 0)

    final_tb['SS'] = col_e.get('SS', 0)
    final_tb['CC'] = col_e.get('CC', 0)
    final_tb['PP'] = col_e.get('PP', 0)

    # 8. Construcción de Subescalas y Formato Diagnóstico
    subscales_dict = {}
    
    # Validez
    v_val = pd.get('V', 0)
    is_v_valid = (v_val < 2)
    is_x_valid = (145 <= pd['X'] <= 590)

    order_scales = [
        "1", "2", "3", "4", "5", "6A", "6B", "7", "8A", "8B",
        "S", "C", "P",
        "A", "H", "N", "D", "B", "T",
        "SS", "CC", "PP",
        "V", "X", "Y", "Z"
    ]

    for s in order_scales:
        meta = SCALE_METADATA.get(s, {"code": s, "nombre": s, "cat": "Escalas Clínicas"})
        s_code = meta['code']
        s_name = meta['nombre']
        cur_pd = pd.get(s, 0)
        cur_tb = final_tb.get(s, cur_pd)
        
        subscales_dict[f"{s_code} - {s_name}"] = {
            "nombre": s_name,
            "codigo": s_code,
            "categoria": meta['cat'],
            "pd": cur_pd,
            "tb": cur_tb
        }

    # 9. Identificar elevaciones clínicas principales
    elev_personalidad = []
    for s in ["1", "2", "3", "4", "5", "6A", "6B", "7", "8A", "8B", "S", "C", "P"]:
        tb_val = final_tb.get(s, 0)
        if tb_val >= 75:
            meta = SCALE_METADATA[s]
            elev_personalidad.append((s, meta['nombre'], tb_val, SCALE_DESCRIPTIONS.get(s, '')))

    elev_sindromes = []
    for s in ["A", "H", "N", "D", "B", "T", "SS", "CC", "PP"]:
        tb_val = final_tb.get(s, 0)
        if tb_val >= 75:
            meta = SCALE_METADATA[s]
            tag = "Trastorno Severo" if tb_val >= 85 else "Significativo"
            elev_sindromes.append((s, meta['nombre'], tb_val, tag, SCALE_DESCRIPTIONS.get(s, '')))

    elev_personalidad.sort(key=lambda x: x[2], reverse=True)
    elev_sindromes.sort(key=lambda x: x[2], reverse=True)

    clasif_parts = []
    if not is_v_valid or not is_x_valid:
        clasif_parts.append("Protocolo No Válido / Interpretar con Cautela")
    
    for s, name, tb, desc in elev_personalidad[:2]:
        clasif_parts.append(f"{name} (TB {tb})")
    
    for s, name, tb, tag, desc in elev_sindromes[:2]:
        clasif_parts.append(f"{name} ({tag} TB {tb})")

    if not clasif_parts:
        classification = "Perfil dentro de Límites Normales (Sin elevaciones significativas)"
    else:
        classification = " • ".join(clasif_parts)

    lines = []
    lines.append(f"🧪 INVENTARIO MULTIAXIAL CLÍNICO DE MILLON (MCMI-II) — BAREMO: {'MUJERES' if is_female else 'VARONES'}\n")
    
    lines.append("1. ÍNDICES DE VALIDEZ Y ACTITUD ANTE LA PRUEBA:")
    if is_v_valid:
        lines.append(f"• Escala V (Validez): {v_val} — Test Válido. No se detectan inconsistencias ni respuestas incongruentes.")
    else:
        lines.append(f"• Escala V (Validez): {v_val} — Test Inválido en V. Se aconseja interpretar con extrema prudencia.")

    if is_x_valid:
        lines.append(f"• Escala X (Sinceridad): PD={pd['X']} (TB {final_tb.get('X', 45)}) — Test Válido en X. Nivel de apertura y honestidad adecuado.")
    else:
        lines.append(f"• Escala X (Sinceridad): PD={pd['X']} — Fuera del rango esperable ({'Defensividad extrema' if pd['X'] < 145 else 'Exageración de síntomas'}).")

    lines.append(f"• Escala Y (Deseabilidad Social): TB {final_tb.get('Y', 0)} | Escala Z (Autodescalificación): TB {final_tb.get('Z', 0)}\n")

    lines.append("2. PATRONES CLÍNICOS DE PERSONALIDAD:")
    if elev_personalidad:
        for s, name, tb, desc in elev_personalidad:
            severidad = "PATRÓN DESCOMPENSADO / SEVERO" if tb >= 85 else "INDICADOR CLÍNICO POSITIVO"
            lines.append(f"• [{s}] {name} (TB {tb} — {severidad}):")
            lines.append(f"  {desc}.")
    else:
        lines.append("• No se observan patrones básicos de personalidad que alcancen el umbral clínico de 75 puntos TB.")
    lines.append("")

    lines.append("3. SÍNDROMES CLÍNICOS Y ESTADO AFECTIVO:")
    if elev_sindromes:
        for s, name, tb, tag, desc in elev_sindromes:
            lines.append(f"• [{s}] {name} (TB {tb} — {tag.upper()}):")
            lines.append(f"  {desc}.")
    else:
        lines.append("• No se aprecian síndromes clínicos que superen el umbral clínico (TB >= 75).")
    lines.append("")

    lines.append("4. RECOMENDACIONES CLÍNICAS Y TERAPÉUTICAS:")
    if any(s in ('2', '8B') for s, _, _, _ in elev_personalidad) and any(s == 'D' for s, _, _, _, _ in elev_sindromes):
        lines.append("• El consultante presenta una configuración caracterizada por inhibición social, temor al rechazo y sentimientos de inadecuación personal (rasgo evitativo/fóbico), acompañado de un cuadro depresivo-distímico de severidad significativa.")
        lines.append("• Se sugiere priorizar intervenciones enfocadas en la estabilización del estado de ánimo (activación conductual, reestructuración de pensamientos automáticos de desvalorización y desesperanza).")
        lines.append("• En la relación terapéutica, fortalecer un vínculo seguro y no enjuiciador para mitigar la marcada hipersensibilidad a la crítica o al abandono.")
    else:
        lines.append("• Se recomienda contrastar los hallazgos con la entrevista clínica y el motivo de consulta del paciente.")

    interpretation = "\n".join(lines)
    total_score = pd.get('X', 0)

    return total_score, subscales_dict, classification, interpretation
