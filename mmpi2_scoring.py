# -*- coding: utf-8 -*-
"""
Módulo de Corrección Psicométrica Automatizada para el MMPI-2 (567 reactivos)
Calcula:
1. Puntuaciones Directas (PD) para las 3 escalas de validez (L, F, K) y las 10 clínicas básicas.
2. Corrección K fraccionada oficial (+0.5K, +0.4K, +1.0K, +1.0K, +0.2K).
3. Puntuaciones T estandarizadas (Media 50, DE 10) según baremos normativos por sexo (Varones / Mujeres).
4. Determinación de elevaciones clínicas (T >= 65, T >= 75) y códigos de perfil (Codetypes).
5. Interpretación clínica diagnóstica automatizada en 4 secciones.
"""

import os
import json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
NORMAS_FILE = os.path.join(BASE_DIR, "mmpi2_t_normas.json")
RULES_FILE = os.path.join(BASE_DIR, "mmpi2_item_rules.json")

with open(RULES_FILE, 'r', encoding='utf-8') as f:
    MMPI2_ITEM_RULES = json.load(f)

with open(NORMAS_FILE, 'r', encoding='utf-8') as f:
    MMPI2_T_NORMAS = json.load(f)

SCALE_METADATA = {
    'L':  {'nombre': 'Mentira (L)', 'num': 'L', 'es_validez': True},
    'F':  {'nombre': 'Infrecuencia / Incoherencia (F)', 'num': 'F', 'es_validez': True},
    'K':  {'nombre': 'Corrección / Defensividad (K)', 'num': 'K', 'es_validez': True},
    'Hs': {'nombre': '1 - Hipocondriasis (Hs)', 'num': '1', 'es_validez': False, 'k_factor': 0.5},
    'D':  {'nombre': '2 - Depresión (D)', 'num': '2', 'es_validez': False, 'k_factor': 0.0},
    'Hy': {'nombre': '3 - Histeria de Conversión (Hy)', 'num': '3', 'es_validez': False, 'k_factor': 0.0},
    'Pd': {'nombre': '4 - Desviación Psicopática (Pd)', 'num': '4', 'es_validez': False, 'k_factor': 0.4},
    'Mf': {'nombre': '5 - Masculinidad / Feminidad (Mf)', 'num': '5', 'es_validez': False, 'k_factor': 0.0},
    'Pa': {'nombre': '6 - Paranoia (Pa)', 'num': '6', 'es_validez': False, 'k_factor': 0.0},
    'Pt': {'nombre': '7 - Psicastenia (Pt)', 'num': '7', 'es_validez': False, 'k_factor': 1.0},
    'Sc': {'nombre': '8 - Esquizofrenia (Sc)', 'num': '8', 'es_validez': False, 'k_factor': 1.0},
    'Ma': {'nombre': '9 - Hipomanía (Ma)', 'num': '9', 'es_validez': False, 'k_factor': 0.2},
    'Si': {'nombre': '0 - Introversión Social (Si)', 'num': '0', 'es_validez': False, 'k_factor': 0.0}
}

SCALE_DESCRIPTIONS = {
    'Hs': "Preocupaciones excesivas por el funcionamiento corporal, múltiples quejas somáticas sin causa médica evidente, fatiga y somatización del estrés",
    'D':  "Estado de ánimo disfórico, pesimismo, apatía, sentimientos de tristeza, culpa, enlentecimiento y falta de energía vital",
    'Hy': "Inseguridad emocional, necesidad de afecto y aprobación, reactividad al estrés mediante síntomas físicos y negación de conflictos psicológicos",
    'Pd': "Dificultades en el acatamiento de normas, impulsividad, baja tolerancia a la frustración, conflictiva interpersonal y rebeldía frente a la autoridad",
    'Mf': "Flexibilidad o rigidez en roles tradicionales de género, intereses estéticos, pautas de sensibilidad y expresión afectiva",
    'Pa': "Sensibilidad interpersonal aumentada, suspicacia, cautela, tendencia a sentirse incomprendido o agraviado, suspicacia o rigidez de criterio",
    'Pt': "Nivel elevado de ansiedad subjetiva, rumiaciones obsesivas, perfeccionismo angustiante, dudas constantes, sentimientos de culpa y miedo al fracaso",
    'Sc': "Alienación social, sensaciones de extrañeza, pensamiento poco convencional o confuso, tendencia al aislamiento y desvinculación emocional",
    'Ma': "Aceleración del ritmo psicomotor, euforia, impulsividad, proyectos múltiples y dispersión de energía, irritabilidad si se limita su actividad",
    'Si': "Retraimiento en interacciones grupales, timidez, incomodidad en situaciones sociales multitudinarias y preferencia por la soledad"
}

CODETYPE_INTERPRETATIONS = {
    ('1', '2'): "Código 1-2 / 2-1: Manifestaciones somáticas crónicas asociadas a estado de ánimo depresivo. El consultante tiende a experimentar su malestar psíquico a través del cuerpo, presentando desgano, irritabilidad y quejas físicas.",
    ('2', '1'): "Código 1-2 / 2-1: Manifestaciones somáticas crónicas asociadas a estado de ánimo depresivo. El consultante tiende a experimentar su malestar psíquico a través del cuerpo, presentando desgano, irritabilidad y quejas físicas.",
    ('1', '3'): "Código 1-3 / 3-1: Perfil de conversión / quejas somáticas funcionales. El consultante niega dificultades psicológicas internas y canaliza la tensión afectiva en síntomas orgánicos, buscando apoyo pero mostrando resistencia a la introspección.",
    ('3', '1'): "Código 1-3 / 3-1: Perfil de conversión / quejas somáticas funcionales. El consultante niega dificultades psicológicas internas y canaliza la tensión afectiva en síntomas orgánicos, buscando apoyo pero mostrando resistencia a la introspección.",
    ('1', '8'): "Código 1-8 / 8-1: Síntomas somáticos extravagantes o poco comunes acompañados de confusión, suspicacia y notable desvinculación afectiva.",
    ('8', '1'): "Código 1-8 / 8-1: Síntomas somáticos extravagantes o poco comunes acompañados de confusión, suspicacia y notable desvinculación afectiva.",
    ('2', '3'): "Código 2-3 / 3-2: Pasividad, cansancio y desánimo. Disminución del interés vital, sobrecontrol emocional, necesidad de apoyo y dificultad para la autoafirmación.",
    ('3', '2'): "Código 2-3 / 3-2: Pasividad, cansancio y desánimo. Disminución del interés vital, sobrecontrol emocional, necesidad de apoyo y dificultad para la autoafirmación.",
    ('2', '4'): "Código 2-4 / 4-2: Conflicto entre impulsividad y remordimiento. Tendencia a actuar de forma precipitada o desafiante, seguida de estados agudos de culpa, angustia y autorreproche.",
    ('4', '2'): "Código 2-4 / 4-2: Conflicto entre impulsividad y remordimiento. Tendencia a actuar de forma precipitada o desafiante, seguida de estados agudos de culpa, angustia y autorreproche.",
    ('2', '7'): "Código 2-7 / 7-2: Síndrome Ansioso-Depresivo. Rumiación constante, autoexigencia severa, inseguridad, sentimientos de incapacidad, tristeza persistente y elevada angustia anticipatoria.",
    ('7', '2'): "Código 2-7 / 7-2: Síndrome Ansioso-Depresivo. Rumiación constante, autoexigencia severa, inseguridad, sentimientos de incapacidad, tristeza persistente y elevada angustia anticipatoria.",
    ('2', '8'): "Código 2-8 / 8-2: Cuadro depresivo severo con enlentecimiento cognitivo, anhedonia marcada, desconexión social y sentimientos intensos de desesperanza o desamparo.",
    ('8', '2'): "Código 2-8 / 8-2: Cuadro depresivo severo con enlentecimiento cognitivo, anhedonia marcada, desconexión social y sentimientos intensos de desesperanza o desamparo.",
    ('3', '4'): "Código 3-4 / 4-3: Agresividad reprimida o pasivo-agresiva. Dificultad para tramitar la hostilidad de manera directa, con riesgo de explosiones emocionales ante situaciones de frustración prolongada.",
    ('4', '3'): "Código 3-4 / 4-3: Agresividad reprimida o pasivo-agresiva. Dificultad para tramitar la hostilidad de manera directa, con riesgo de explosiones emocionales ante situaciones de frustración prolongada.",
    ('4', '6'): "Código 4-6 / 6-4: Suspicacia, resentimiento hacia figuras de autoridad o figuras de apego, hipersensibilidad a la crítica y desconfianza interpersonal.",
    ('6', '4'): "Código 4-6 / 6-4: Suspicacia, resentimiento hacia figuras de autoridad o figuras de apego, hipersensibilidad a la crítica y desconfianza interpersonal.",
    ('4', '9'): "Código 4-9 / 9-4: Impulsividad y búsqueda de estimulación. Dificultad en la postergación de la gratificación, baja tolerancia a las normas y marcada reactividad emocional.",
    ('9', '4'): "Código 4-9 / 9-4: Impulsividad y búsqueda de estimulación. Dificultad en la postergación de la gratificación, baja tolerancia a las normas y marcada reactividad emocional.",
    ('6', '8'): "Código 6-8 / 8-6: Pensamiento suspicaz o delirante, profunda desconfianza en el entorno, suspicacia paranoide y marcado aislamiento defensivo.",
    ('8', '6'): "Código 6-8 / 8-6: Pensamiento suspicaz o delirante, profunda desconfianza en el entorno, suspicacia paranoide y marcado aislamiento defensivo.",
    ('7', '8'): "Código 7-8 / 8-7: Crisis de angustia y desorganización cognitiva. Sensación de pérdida de control mental, confusión, pánico, insomnio severo y rumiación desbordante.",
    ('8', '7'): "Código 7-8 / 8-7: Crisis de angustia y desorganización cognitiva. Sensación de pérdida de control mental, confusión, pánico, insomnio severo y rumiación desbordante.",
    ('8', '9'): "Código 8-9 / 9-8: Agitación ideacional o hiperactividad desorganizada. Labilidad afectiva, desinhibición, posibles ideas grandiosas o bizarrizantes."
}

def lookup_t_score(scale_code, raw_value, tables, is_female):
    mapping = tables.get(scale_code, {})
    if not mapping:
        return 50

    int_keys = sorted([int(k) for k in mapping.keys()])
    min_k, max_k = int_keys[0], int_keys[-1]

    # Invertida únicamente en Mf para mujeres (raw alto = T bajo)
    is_inverted = (scale_code == 'Mf' and is_female)

    if is_inverted:
        if raw_value <= min_k:
            return mapping[str(min_k)]
        if raw_value >= max_k:
            return mapping[str(max_k)]
    else:
        if raw_value <= min_k:
            return mapping[str(min_k)]
        if raw_value >= max_k:
            return mapping[str(max_k)]

    key_str = str(int(raw_value))
    if key_str in mapping:
        return mapping[key_str]

    # Fallback aproximación lineal entre claves vecinas
    lower = max([k for k in int_keys if k <= raw_value])
    upper = min([k for k in int_keys if k >= raw_value])
    if lower == upper:
        return mapping[str(lower)]
    t_low = mapping[str(lower)]
    t_upp = mapping[str(upper)]
    fraction = (raw_value - lower) / float(upper - lower)
    return int(round(t_low + fraction * (t_upp - t_low)))


def process_mmpi2_scoring(answers, patient_info=None):
    """
    Procesa las respuestas de un test MMPI-2 (567 reactivos) y calcula:
    - Puntuaciones Directas (PD)
    - Corrección K fraccionada
    - Puntuaciones T estandarizadas (Media 50, DE 10)
    - Subescalas diagnósticas estructuradas
    - Códigos de tipo (Codetypes)
    - Interpretación clínica narrativa completa
    """
    patient_info = patient_info or {}
    genero_raw = str(patient_info.get('genero') or '').strip().lower()
    is_female = genero_raw in ('f', 'femenino', 'female', 'mujer')
    normas_key = 'mujeres' if is_female else 'varones'
    tables = MMPI2_T_NORMAS.get(normas_key, MMPI2_T_NORMAS['varones'])

    # Normalizar respuestas en enteros {item_int: val_int} (1=Verdadero, 2=Falso)
    norm_answers = {}
    for k, v in answers.items():
        try:
            it_num = int(str(k).replace('item_', ''))
            v_str = str(v).strip().upper()
            if v_str in ('1', 'V', 'VERDADERO', 'TRUE'):
                val = 1
            elif v_str in ('2', '0', 'F', 'FALSO', 'FALSE'):
                val = 2
            else:
                val = int(v)
            norm_answers[it_num] = val
        except (ValueError, TypeError):
            pass

    answered_count = len(norm_answers)
    pct_complete = round((answered_count / 567.0) * 100, 1)

    # 1. Puntuaciones Directas (PD)
    raw_scores = {}
    for scale_code in ['L', 'F', 'K', 'Hs', 'D', 'Hy', 'Pd', 'Pa', 'Pt', 'Sc', 'Ma', 'Si']:
        rules = MMPI2_ITEM_RULES.get(scale_code, [])
        score = 0
        for r in rules:
            if norm_answers.get(r['item']) == r['ans']:
                score += 1
        raw_scores[scale_code] = score

    # Mf tiene claves según género
    mf_key = 'Mf_F' if is_female else 'Mf_M'
    rules_mf = MMPI2_ITEM_RULES.get(mf_key, MMPI2_ITEM_RULES.get('Mf_M', []))
    score_mf = 0
    for r in rules_mf:
        if norm_answers.get(r['item']) == r['ans']:
            score_mf += 1
    raw_scores['Mf'] = score_mf

    # 2. Corrección K fraccionada
    k_raw = raw_scores.get('K', 0)
    k_fractions = {
        'Hs': int(round(0.5 * k_raw)),
        'Pd': int(round(0.4 * k_raw)),
        'Pt': k_raw,
        'Sc': k_raw,
        'Ma': int(round(0.2 * k_raw))
    }

    corrected_raw = {}
    for s in ['L', 'F', 'K', 'Hs', 'D', 'Hy', 'Pd', 'Mf', 'Pa', 'Pt', 'Sc', 'Ma', 'Si']:
        base = raw_scores.get(s, 0)
        frac = k_fractions.get(s, 0)
        corrected_raw[s] = base + frac

    # 3. Puntuaciones T
    t_scores = {}
    for s in ['L', 'F', 'K', 'Hs', 'D', 'Hy', 'Pd', 'Mf', 'Pa', 'Pt', 'Sc', 'Ma', 'Si']:
        val_for_lookup = corrected_raw[s]
        t_scores[s] = lookup_t_score(s, val_for_lookup, tables, is_female)

    # 4. Diccionario de Subescalas
    subscales_dict = {}
    for s in ['L', 'F', 'K', 'Hs', 'D', 'Hy', 'Pd', 'Mf', 'Pa', 'Pt', 'Sc', 'Ma', 'Si']:
        meta = SCALE_METADATA[s]
        t_val = t_scores[s]
        pd_val = raw_scores[s]
        k_val = k_fractions.get(s, 0)
        subscales_dict[s] = {
            't': t_val,
            'tb': t_val, # Compatible con renderizado de interfaz existente
            'pd': pd_val,
            'k_corr': k_val,
            'puntuacion_corregida': corrected_raw[s],
            'nombre': meta['nombre'],
            'es_validez': meta['es_validez']
        }

    # 5. Identificar elevaciones clínicas (T >= 65 clínico, T >= 75 severo)
    clinical_order = ['Hs', 'D', 'Hy', 'Pd', 'Mf', 'Pa', 'Pt', 'Sc', 'Ma', 'Si']
    elevations = []
    for s in clinical_order:
        t_val = t_scores[s]
        if t_val >= 65:
            meta = SCALE_METADATA[s]
            tag = "Elevación Severa" if t_val >= 75 else "Significativo"
            elevations.append((s, meta['num'], meta['nombre'], t_val, tag, SCALE_DESCRIPTIONS.get(s, '')))

    # 6. Codetype de 2 puntos clínicos (escalas 1 a 9 excluyendo 5, más elevadas con T >= 65)
    codetype_pool = [(s, SCALE_METADATA[s]['num'], t_scores[s]) for s in ['Hs', 'D', 'Hy', 'Pd', 'Pa', 'Pt', 'Sc', 'Ma'] if t_scores[s] >= 65]
    codetype_pool.sort(key=lambda x: x[2], reverse=True)

    codetype_str = "Sin código de tipo definido (Perfil dentro de límites normales)"
    codetype_desc = ""
    codetype_key = None

    if len(codetype_pool) >= 2:
        top1, top2 = codetype_pool[0], codetype_pool[1]
        codetype_key = (top1[1], top2[1])
        codetype_str = f"Código {top1[1]}-{top2[1]} ({top1[0]}-{top2[0]})"
        codetype_desc = CODETYPE_INTERPRETATIONS.get(codetype_key, "")
        if not codetype_desc:
            alt_key = (top2[1], top1[1])
            codetype_desc = CODETYPE_INTERPRETATIONS.get(alt_key, "")
        if not codetype_desc:
            codetype_desc = f"Elevación combinada de las escalas {top1[1]} ({top1[0]}) y {top2[1]} ({top2[0]}), denotando una interacción entre {SCALE_DESCRIPTIONS.get(top1[0], '')} y {SCALE_DESCRIPTIONS.get(top2[0], '')}."
    elif len(codetype_pool) == 1:
        top = codetype_pool[0]
        codetype_str = f"Pico Uniescalar en {top[1]} ({top[0]})"
        codetype_desc = f"Elevación aislada de significación clínica en la escala {top[1]} ({SCALE_METADATA[top[0]]['nombre']}): {SCALE_DESCRIPTIONS.get(top[0], '')}."

    # Clasificación global breve
    if pct_complete < 80:
        classification = f"Protocolo Incompleto ({pct_complete}%)"
    elif codetype_pool:
        top_scales_summary = ", ".join([f"{SCALE_METADATA[x[0]]['nombre']} (T {x[2]})" for x in codetype_pool[:2]])
        classification = f"Perfil Clínico Significativo: {top_scales_summary}"
    else:
        classification = "Perfil dentro de Límites Normales (T < 65 en todas las escalas)"

    # 7. Redacción de Interpretación Clínica en 4 Secciones
    l_t = t_scores['L']
    f_t = t_scores['F']
    k_t = t_scores['K']

    lines = []
    lines.append(f"🧪 INVENTARIO MULTIFÁSICO DE PERSONALIDAD DE MINNESOTA (MMPI-2) — BAREMO: {'MUJERES' if is_female else 'VARONES'}\n")

    lines.append("1. ÍNDICES DE VALIDEZ Y ACTITUD ANTE LA PRUEBA:")
    lines.append(f"• Ítems respondidos: {answered_count} de 567 ({pct_complete}% completado).")
    
    # Análisis de validez
    if f_t >= 80:
        lines.append(f"• Escala F (Infrecuencia) = T {f_t} [ELEVADA]: Manifiesta una marcada cantidad de síntomas atípicos o severos. Puede reflejar una crisis aguda de angustia ('grito de ayuda') o exacerbación sintomática.")
    elif f_t >= 65:
        lines.append(f"• Escala F (Infrecuencia) = T {f_t} [MODERADA]: Reconocimiento abierto de dificultades emocionales y malestar psicológico real.")
    else:
        lines.append(f"• Escala F (Infrecuencia) = T {f_t} [NORMAL]: Protocolo coherente y consistente, sin respuestas incongruentes.")

    if l_t >= 65:
        lines.append(f"• Escala L (Mentira) = T {l_t} [ELEVADA]: Tendencia a presentarse de manera socialmente virtuosa o rígida, negando faltas humanas comunes.")
    else:
        lines.append(f"• Escala L (Mentira) = T {l_t} [NORMAL]: Actitud franca y colaboradora frente a la evaluación.")

    if k_t >= 65:
        lines.append(f"• Escala K (Defensividad) = T {k_t} [ELEVADA]: Tendencia a la reserva defensiva y autocontrol emocional, minimizando vulnerabilidades personales.")
    elif k_t <= 40:
        lines.append(f"• Escala K (Defensividad) = T {k_t} [BAJA]: Escasos recursos defensivos frente al estrés; sensación de vulnerabilidad y desbordamiento afectivo.")
    else:
        lines.append(f"• Escala K (Defensividad) = T {k_t} [ADECUADA]: Equilibrio adecuado entre apertura psicológica y mecanismos de defensa.")

    # Configuración de validez
    if l_t >= 65 and f_t <= 50 and k_t >= 65:
        lines.append("• Configuración de Validez: Perfil defensivo en 'V' (intento de proyectar una imagen positiva o adaptada).")
    elif l_t <= 50 and f_t >= 65 and k_t <= 50:
        lines.append("• Configuración de Validez: Perfil en 'V invertida' (reconocimiento abierto de sufrimiento psicológico agudo y necesidad de ayuda terapéutica).")
    lines.append("")

    lines.append("2. ESCALAS CLÍNICAS BÁSICAS Y NIVELES DE ELEVACIÓN:")
    if elevations:
        for s, num, name, t_val, tag, desc in elevations:
            severidad = "ELEVACIÓN SEVERA (T >= 75)" if t_val >= 75 else "INDICADOR CLÍNICO SIGNIFICATIVO (T >= 65)"
            k_note = f" (PD: {raw_scores[s]} + {k_fractions[s]}K = {corrected_raw[s]})" if k_fractions.get(s) else f" (PD: {raw_scores[s]})"
            lines.append(f"• [{num}] {name} (T {t_val} — {severidad}){k_note}:")
            lines.append(f"  {desc}.")
    else:
        lines.append("• Ninguna de las 10 escalas clínicas supera el punto de corte psicopatológico (T >= 65). El perfil refleja ausencia de sintomatología clínica aguda al momento de la aplicación.")
    lines.append("")

    lines.append("3. ANÁLISIS DEL PERFIL Y CÓDIGO CLÍNICO (CODETYPE):")
    lines.append(f"• {codetype_str}.")
    if codetype_desc:
        lines.append(f"• {codetype_desc}")
    lines.append("")

    lines.append("4. IMPLICACIONES TERAPÉUTICAS Y RECOMENDACIONES:")
    if any(s in ('D', 'Pt') for s, _, _, _, _, _ in elevations):
        lines.append("• Se evidencia un foco afectivo-ansioso predominante. Se recomienda priorizar intervenciones dirigidas a la regulación del estado de ánimo, reducción de la rumiación cognitiva y estrategias de afrontamiento ante la autoexigencia.")
    if any(s in ('Hs', 'Hy') for s, _, _, _, _, _ in elevations):
        lines.append("• Atención a posibles manifestaciones de somatización. Es clave validar el malestar del consultante sin reforzar la focalización en síntomas corporales, explorando los estresores psicosociales asociados.")
    if any(s in ('Pd', 'Ma') for s, _, _, _, _, _ in elevations):
        lines.append("• Se aconseja trabajar en el encuadre terapéutico sobre la tolerancia a la frustración, el control de impulsos y el análisis de consecuencias en vínculos interpersonales.")
    if not elevations:
        lines.append("• El consultante cuenta con recursos adaptativos y defensivos estables. Se sugiere contrastar los resultados con la entrevista clínica inicial.")

    interpretation = "\n".join(lines)
    total_score = float(answered_count)

    return total_score, subscales_dict, classification, interpretation
