# -*- coding: utf-8 -*-
"""
psychometric_scoring.py
Motor psicométrico y baremos de corrección oficial para evaluaciones psicológicas en Espacio Terapéutico:
- ASRS v1.1 OMS (Adult ADHD Self-Report Scale - TDAH Adultos)
- BDI-II (Inventario de Depresión de Beck - Segunda Edición)
- BAI (Inventario de Ansiedad de Beck)
- AQ (Cociente de Espectro Autista - Baron-Cohen)
- CAT-Q (Cuestionario de Camuflaje de Rasgos Autistas - Hull et al.)
- TCS (Escala de Congruencia Transgénero)
- UGDS-GS (Escala de Disforia de Género de Utrecht)
- RAADS-R (Escala Revisada para Diagnóstico de Autismo y Asperger)
- HOLLAND (Test de Intereses Vocacionales RIASEC)
"""

import json

def _extract_answer_map(answers):
    """Extrae un mapa {item_num: valor_int} seguro a partir de cualquier estructura de respuestas."""
    ans_map = {}
    if not isinstance(answers, dict):
        return ans_map
    for k, v in answers.items():
        try:
            num_digits = ''.join(c for c in str(k) if c.isdigit())
            if not num_digits:
                continue
            num = int(num_digits)
            # Manejar valor
            if isinstance(v, (int, float)):
                ans_map[num] = int(v)
            elif str(v).strip().replace('.', '', 1).isdigit():
                ans_map[num] = int(float(str(v).strip()))
        except (ValueError, TypeError):
            continue
    return ans_map


# =========================================================================
# 1. ASRS v1.1 OMS (TDAH EN EL ADULTO)
# =========================================================================
def process_asrs_adhd_scoring(answers):
    """
    ASRS v1.1 OMS (Adult ADHD Self-Report Scale)
    18 ítems con escala Likert de 5 opciones (0=Nunca, 1=Raramente, 2=Algunas veces, 3=A menudo, 4=Muy a menudo).
    
    Estructura Oficial OMS / DSM-5:
    - Parte A (Screener OMS de 6 preguntas, ítems 1-6):
        * Ítems 1, 2, 3: respuesta >= 2 (Algunas veces) = 1 punto screener.
        * Ítems 4, 5, 6: respuesta >= 3 (A menudo) = 1 punto screener.
        * Umbral Clínico OMS: Puntaje >= 4/6 indica ALTA PROBABILIDAD DE TDAH.
    - Subescala Desatención (Ítems 1 al 9, 0 a 36 pts).
    - Subescala Hiperactividad / Impulsividad (Ítems 10 al 18, 0 a 36 pts).
    - Puntuación Total Directa: 0 a 72 pts.
    """
    ans_map = _extract_answer_map(answers)
    
    inattention_items = [1, 2, 3, 4, 5, 6, 7, 8, 9]
    hyper_items = [10, 11, 12, 13, 14, 15, 16, 17, 18]
    
    inattention_score = sum(ans_map.get(i, 0) for i in inattention_items)
    hyper_score = sum(ans_map.get(i, 0) for i in hyper_items)
    total_score = inattention_score + hyper_score
    
    # Screener OMS (ítems 1 al 6)
    screener_score = 0
    for num in [1, 2, 3]:
        if ans_map.get(num, 0) >= 2:
            screener_score += 1
    for num in [4, 5, 6]:
        if ans_map.get(num, 0) >= 3:
            screener_score += 1

    screener_pos = screener_score >= 4
    
    # Niveles dimensionales
    def get_dim_level(score):
        if score >= 24:
            return "Elevado (Clínicamente Significativo)", "severo"
        elif score >= 17:
            return "Moderado (Sintomatología Probable)", "moderado"
        elif score >= 12:
            return "Leve / Subclínico", "leve"
        else:
            return "Normal / No Significativo", "normal"
            
    inat_desc, inat_alerta = get_dim_level(inattention_score)
    hyper_desc, hyper_alerta = get_dim_level(hyper_score)
    
    # Clasificación diagnóstica (DSM-5 / OMS)
    if inattention_score >= 24 and hyper_score >= 24:
        classification = "TDAH - Presentación Combinada (Inatención e Hiperactividad)"
        subtipo = "Presentación Combinada (TDAH-C) - Alta Severidad"
        alerta_global = "severo"
    elif inattention_score >= 24:
        classification = "TDAH - Presentación Predominantemente Inatenta (TDAH-I)"
        subtipo = "Presentación Predominantemente Inatenta"
        alerta_global = "severo"
    elif hyper_score >= 24:
        classification = "TDAH - Presentación Predominantemente Hiperactiva/Impulsiva (TDAH-HI)"
        subtipo = "Presentación Predominantemente Hiperactiva/Impulsiva"
        alerta_global = "severo"
    elif screener_pos or total_score >= 32:
        classification = "Sintomatología Sugestiva de TDAH (Cribado OMS Positivo)"
        subtipo = "Sintomatología Subclínica o en Rango Límite"
        alerta_global = "moderado"
    else:
        classification = "Sin indicadores significativos de TDAH (Dentro de límites normales)"
        subtipo = "Dentro de Límites Normales"
        alerta_global = "normal"
        
    subscales_dict = {
        "Cribado Rápido OMS (Parte A - Ítems 1-6)": {
            "pd": f"{screener_score} / 6",
            "baremo": "Punto de corte clínico >= 4",
            "nivel": "Positivo para TDAH" if screener_pos else "Negativo",
            "criterio": "Alta probabilidad de TDAH en el adulto según baremo OMS" if screener_pos else "Baja probabilidad según cribado inicial",
            "alerta": "severo" if screener_pos else "normal"
        },
        "Desatención (Ítems 1 al 9)": {
            "pd": f"{inattention_score} / 36",
            "baremo": "Corte >= 24 Elevado (17-23 Moderado, 0-16 Normal)",
            "nivel": inat_desc,
            "criterio": "Déficit atencional y de organización clínicamente relevante" if inattention_score >= 17 else "Dentro del rango esperado",
            "alerta": inat_alerta
        },
        "Hiperactividad e Impulsividad (Ítems 10 al 18)": {
            "pd": f"{hyper_score} / 36",
            "baremo": "Corte >= 24 Elevado (17-23 Moderado, 0-16 Normal)",
            "nivel": hyper_desc,
            "criterio": "Inquietud psicomotora, impulsividad y verborrea relevante" if hyper_score >= 17 else "Dentro del rango esperado",
            "alerta": hyper_alerta
        },
        "Puntuación Total ASRS (18 Ítems)": {
            "pd": f"{total_score} / 72",
            "baremo": "Corte sugerido: >= 40 muy alto, 24-39 moderado",
            "nivel": "Elevado" if total_score >= 40 else ("Moderado" if total_score >= 24 else "Normal"),
            "criterio": classification,
            "alerta": alerta_global
        }
    }
    
    screener_txt = "POSITIVO (cumple 4 o más criterios sombreados de la OMS)" if screener_pos else "NEGATIVO (no alcanza el umbral de cribado OMS)"
    interpretation = (
        f"INFORME PSICOMÉTRICO ASRS v1.1 OMS (TDAH EN EL ADULTO):\n"
        f"• Clasificación Clínica según Baremo: {classification}\n"
        f"• Subtipo según Criterios DSM-5: {subtipo}\n"
        f"• Cribado OMS (Ítems 1 al 6): {screener_score}/6 puntos — {screener_txt}.\n"
        f"• Desatención (Ítems 1-9): {inattention_score}/36 pts ({inat_desc}).\n"
        f"• Hiperactividad e Impulsividad (Ítems 10-18): {hyper_score}/36 pts ({hyper_desc}).\n"
        f"• Puntuación Total Directa: {total_score}/72 pts.\n\n"
        f"Juicio Clínico: "
        + (f"El perfil obtenido presenta sintomatología congruente con un Trastorno por Déficit de Atención e Hiperactividad en el adulto. Los puntajes reflejan dificultades significativas en autorregulación ejecutiva, atención focalizada y/o control de impulsos. Se sugiere correlacionar con historia retrospectiva en la infancia y evaluación neuropsicológica complementaria." if screener_pos or total_score >= 28 else "Las puntuaciones obtenidas no alcanzan significación clínica para sospecha de TDAH. Las funciones de atención y control de impulsos se sitúan dentro de la norma poblacional.")
    )
    
    return float(total_score), subscales_dict, classification, interpretation


# =========================================================================
# 2. BDI-II (INVENTARIO DE DEPRESIÓN DE BECK - SEGUNDA EDICIÓN)
# =========================================================================
def process_bdi2_scoring(answers):
    """
    Inventario de Depresión de Beck - Segunda Edición (BDI-II)
    21 ítems, rango 0 a 63 puntos.
    Baremos Oficiales de Beck:
      0 - 13: Depresión Mínima (Dentro de límites normales)
      14 - 19: Depresión Leve
      20 - 28: Depresión Moderada
      29 - 63: Depresión Grave / Severa
    Alerta Crítica: Ítem 9 (Ideación Suicida).
    """
    ans_map = _extract_answer_map(answers)
    total_score = sum(ans_map.get(i, 0) for i in range(1, 22))
    
    cog_items = list(range(1, 14))
    som_items = list(range(14, 22))
    score_cog = sum(ans_map.get(i, 0) for i in cog_items)
    score_som = sum(ans_map.get(i, 0) for i in som_items)
    
    item_9 = ans_map.get(9, 0)
    suicide_alert = item_9 > 0
    
    if total_score <= 13:
        classification = "Depresión Mínima (Normal)"
        alerta = "normal"
    elif total_score <= 19:
        classification = "Depresión Leve"
        alerta = "leve"
    elif total_score <= 28:
        classification = "Depresión Moderada"
        alerta = "moderado"
    else:
        classification = "Depresión Grave"
        alerta = "severo"
        
    suicide_text = ""
    if item_9 == 1:
        suicide_text = "⚠️ ATENCIÓN: Puntuó 1 en Ítem 9 (Tiene pensamientos de suicidio, pero sin intención inmediata)."
    elif item_9 == 2:
        suicide_text = "🚨 ALERTA CLÍNICA: Puntuó 2 en Ítem 9 (Desea quitarse la vida). Requiere evaluación inmediata de riesgo suicida."
    elif item_9 == 3:
        suicide_text = "🚨 URGENCIA VITAL: Puntuó 3 en Ítem 9 (Se quitaría la vida si tuviera oportunidad). Activar protocolo de contención y seguridad."

    subscales_dict = {
        "Puntuación Global BDI-II": {
            "pd": f"{total_score} / 63",
            "baremo": "0-13 Mínima, 14-19 Leve, 20-28 Moderada, 29-63 Grave",
            "nivel": classification,
            "criterio": f"Rango clínico de {classification.lower()}",
            "alerta": alerta
        },
        "Factor Cognitivo-Afectivo (Ítems 1-13)": {
            "pd": f"{score_cog} / 39",
            "baremo": "Tristeza, pesimismo, fracaso, culpa, autocrítica y desvalorización",
            "nivel": "Elevado" if score_cog >= 18 else ("Moderado" if score_cog >= 10 else "Bajo"),
            "criterio": "Afectación cognitiva depresiva presente" if score_cog >= 10 else "Dentro de parámetros esperados",
            "alerta": "severo" if score_cog >= 18 else ("moderado" if score_cog >= 10 else "normal")
        },
        "Factor Somático-Vegetativo (Ítems 14-21)": {
            "pd": f"{score_som} / 24",
            "baremo": "Patrón de sueño, fatiga, apetito, concentración y libido",
            "nivel": "Elevado" if score_som >= 12 else ("Moderado" if score_som >= 7 else "Bajo"),
            "criterio": "Afectación neurovegetativa relevante" if score_som >= 7 else "Dentro de parámetros esperados",
            "alerta": "severo" if score_som >= 12 else ("moderado" if score_som >= 7 else "normal")
        }
    }
    
    if suicide_alert:
        subscales_dict["Alerta de Riesgo de Suicidio (Ítem 9)"] = {
            "pd": f"{item_9} / 3",
            "baremo": "0 = Ausente, >= 1 = Alerta clínica obligatoria",
            "nivel": "ALERTA RIESGO SUICIDA",
            "criterio": suicide_text,
            "alerta": "severo"
        }

    interpretation = (
        f"INFORME DEL INVENTARIO DE DEPRESIÓN DE BECK (BDI-II):\n"
        f"• Puntuación Directa Total: {total_score} / 63 puntos.\n"
        f"• Clasificación Diagnóstica según Baremo: {classification}.\n"
        f"• Dimensión Cognitivo-Afectiva: {score_cog} / 39 pts.\n"
        f"• Dimensión Somático-Vegetativa: {score_som} / 24 pts.\n"
    )
    if suicide_text:
        interpretation += f"\n{suicide_text}\n"
    interpretation += (
        f"\nConclusión Terapéutica: El consultante presenta un cuadro de {classification.lower()}. "
        + ("Se recomienda abordaje psicoterapéutico focalizado en reestructuración de pensamientos automáticos disfuncionales, activación conductual y regulación afectiva." if total_score >= 14 else "No se aprecian indicadores clínicamente significativos de depresión en la actualidad.")
    )
    
    return float(total_score), subscales_dict, classification, interpretation


# =========================================================================
# 3. BAI (INVENTARIO DE ANSIEDAD DE BECK)
# =========================================================================
def process_bai_scoring(answers):
    """
    Inventario de Ansiedad de Beck (BAI)
    21 ítems, rango 0 a 63 puntos.
    Baremos Oficiales de Beck:
      0 - 7: Ansiedad Mínima
      8 - 15: Ansiedad Leve
      16 - 25: Ansiedad Moderada
      26 - 63: Ansiedad Grave
    """
    ans_map = _extract_answer_map(answers)
    total_score = sum(ans_map.get(i, 0) for i in range(1, 22))
    
    somatic_items = [1, 2, 3, 6, 7, 8, 12, 13, 19, 20, 21]
    subjective_items = [4, 5, 9, 10, 11, 14, 15, 16, 17, 18]
    score_som = sum(ans_map.get(i, 0) for i in somatic_items)
    score_sub = sum(ans_map.get(i, 0) for i in subjective_items)
    
    if total_score <= 7:
        classification = "Ansiedad Mínima"
        alerta = "normal"
    elif total_score <= 15:
        classification = "Ansiedad Leve"
        alerta = "leve"
    elif total_score <= 25:
        classification = "Ansiedad Moderada"
        alerta = "moderado"
    else:
        classification = "Ansiedad Grave"
        alerta = "severo"

    subscales_dict = {
        "Puntuación Global BAI": {
            "pd": f"{total_score} / 63",
            "baremo": "0-7 Mínima, 8-15 Leve, 16-25 Moderada, 26-63 Grave",
            "nivel": classification,
            "criterio": f"Rango clínico de {classification.lower()}",
            "alerta": alerta
        },
        "Síntomas Somáticos / Neurovegetativos": {
            "pd": f"{score_som} / 33",
            "baremo": "Palpitaciones, temblores, sofocos, respiración agitada y tensión",
            "nivel": "Elevado" if score_som >= 15 else ("Moderado" if score_som >= 8 else "Bajo"),
            "criterio": "Hiperactivación autonómica presente" if score_som >= 8 else "Dentro de parámetros esperados",
            "alerta": "severo" if score_som >= 15 else ("moderado" if score_som >= 8 else "normal")
        },
        "Síntomas Subjetivos y Cognitivos": {
            "pd": f"{score_sub} / 30",
            "baremo": "Miedo a perder el control, temor a morir, aprensión y nerviosismo",
            "nivel": "Elevado" if score_sub >= 14 else ("Moderado" if score_sub >= 7 else "Bajo"),
            "criterio": "Rumiación ansiosa y cognición catastrófica" if score_sub >= 7 else "Dentro de parámetros esperados",
            "alerta": "severo" if score_sub >= 14 else ("moderado" if score_sub >= 7 else "normal")
        }
    }
    
    interpretation = (
        f"INFORME DEL INVENTARIO DE ANSIEDAD DE BECK (BAI):\n"
        f"• Puntuación Directa Total: {total_score} / 63 puntos.\n"
        f"• Clasificación Diagnóstica según Baremo: {classification}.\n"
        f"• Reactividad Somática: {score_som} / 33 pts.\n"
        f"• Componente Cognitivo/Pánico: {score_sub} / 30 pts.\n\n"
        f"Conclusión Terapéutica: El paciente manifiesta un nivel de {classification.lower()}. "
        + ("Se evidencian respuestas fisiológicas y cognitivas de alerta elevada que ameritan entrenamiento en técnicas de respiración diafragmática, desensibilización y manejo de la activación autonómica." if total_score >= 16 else "No se observan niveles de ansiedad clínicamente desadaptativos en este momento.")
    )
    return float(total_score), subscales_dict, classification, interpretation


# =========================================================================
# 4. AQ (COCIENTE DE ESPECTRO AUTISTA - BARON-COHEN)
# =========================================================================
def process_aq_scoring(answers):
    """
    Cociente de Espectro Autista (AQ - Baron-Cohen et al., 2001)
    50 ítems, 5 subescalas de 10 ítems cada una.
    Punto de corte clínico oficial: >= 32 puntos (80% sensibilidad/especificidad en TEA adultos).
    Rango 0 a 50 puntos.
    """
    ans_map = _extract_answer_map(answers)
    agree_items = {2, 4, 5, 6, 7, 9, 12, 13, 16, 18, 19, 20, 21, 22, 23, 26, 33, 35, 39, 41, 42, 43, 45, 46}
    disagree_items = {1, 3, 8, 10, 11, 14, 15, 17, 24, 25, 27, 28, 29, 30, 31, 32, 34, 36, 37, 38, 40, 44, 47, 48, 49, 50}
    
    subscales_map = {
        "Habilidades Sociales": [1, 11, 13, 15, 22, 36, 44, 45, 47, 48],
        "Cambio de Atención / Flexibilidad": [2, 4, 10, 16, 25, 32, 34, 37, 43, 46],
        "Atención a los Detalles": [5, 6, 9, 12, 19, 23, 28, 29, 30, 49],
        "Comunicación Social": [7, 18, 26, 27, 31, 33, 35, 38, 39, 50],
        "Imaginación": [3, 8, 14, 17, 20, 21, 24, 40, 41, 42]
    }
    
    scored_items = {}
    for i in range(1, 51):
        resp = ans_map.get(i, 0)
        if i in agree_items:
            scored_items[i] = 1 if resp in (1, 2) else 0
        elif i in disagree_items:
            scored_items[i] = 1 if resp in (3, 4) else 0
        else:
            scored_items[i] = 0
            
    total_score = sum(scored_items.values())
    
    subscales_dict = {}
    for sub_name, item_list in subscales_map.items():
        sub_score = sum(scored_items.get(it, 0) for it in item_list)
        subscales_dict[sub_name] = {
            "pd": f"{sub_score} / 10",
            "baremo": "Corte sugerido >= 6",
            "nivel": "Elevado" if sub_score >= 6 else ("Moderado" if sub_score >= 4 else "Bajo"),
            "criterio": "Rasgos característicos presentes" if sub_score >= 6 else "Parámetros habituales",
            "alerta": "severo" if sub_score >= 6 else ("moderado" if sub_score >= 4 else "normal")
        }
        
    if total_score >= 32:
        classification = "Compatible con Rasgos del Espectro Autista (AQ >= 32)"
        alerta = "severo"
        crit = "Punto de corte clínico alcanzado (Sensibilidad ~80%)"
    elif total_score >= 26:
        classification = "Rasgos Autistas Moderados / Zona Intermedia (AQ 26-31)"
        alerta = "moderado"
        crit = "Presencia de rasgos moderados sin cumplir umbral diagnóstico completo"
    else:
        classification = "Dentro del Rango Neurotípico (AQ < 26)"
        alerta = "normal"
        crit = "Sin indicadores significativos de TEA según el baremo de Baron-Cohen"
        
    subscales_dict["Cociente de Espectro Autista (Total AQ)"] = {
        "pd": f"{total_score} / 50",
        "baremo": "Corte Clínico Oficial >= 32 pts (Baron-Cohen)",
        "nivel": classification,
        "criterio": crit,
        "alerta": alerta
    }
    
    interpretation = (
        f"INFORME DEL COCIENTE DE ESPECTRO AUTISTA (AQ - BARON-COHEN):\n"
        f"• Puntuación Total Directa: {total_score} / 50 puntos.\n"
        f"• Clasificación Clínica según Baremo: {classification}.\n"
        f"• Umbral Clínico Oficial: 32 puntos (el 80% de adultos con TEA obtienen >= 32 frente a solo el 2% del grupo neurotípico de control).\n\n"
        f"Desglose de Subescalas:\n"
        + "\n".join([f"  - {k}: {v['pd']} ({v['nivel']})" for k, v in subscales_dict.items() if k != "Cociente de Espectro Autista (Total AQ)"])
        + f"\n\nConclusión Psicométrica: {'El perfil obtenido sugiere una coincidencia sustancial con el fenotipo del espectro autista en adultos. Se recomienda complementar con entrevista clínica del desarrollo (ADI-R / ADOS-2) para formalizar la evaluación diagnóstica.' if total_score >= 32 else 'Las respuestas se sitúan dentro de la variabilidad neurotípica sin superar el punto de corte diagnóstico.'}"
    )
    return float(total_score), subscales_dict, classification, interpretation


# =========================================================================
# 5. CAT-Q (CAMOUFLAGING AUTISTIC TRAITS QUESTIONNAIRE)
# =========================================================================
def process_catq_scoring(answers):
    """
    CAT-Q (Hull et al., 2019)
    25 ítems, escala Likert 1 a 7.
    Ítems inversos: 3, 12, 19, 22, 24 (invertidos: 8 - valor).
    Corte clínico: >= 100 puntos indica camuflaje autista significativo.
    """
    ans_map = _extract_answer_map(answers)
    reversed_items = {3, 12, 19, 22, 24}
    scored = {}
    for i in range(1, 26):
        val = ans_map.get(i, 4)
        if i in reversed_items:
            scored[i] = 8 - val
        else:
            scored[i] = val
            
    comp_items = [1, 4, 5, 8, 11, 14, 17, 20, 23]
    mask_items = [2, 6, 9, 12, 15, 18, 21, 24]
    asim_items = [3, 7, 10, 13, 16, 19, 22, 25]
    
    comp_score = sum(scored.get(i, 0) for i in comp_items)
    mask_score = sum(scored.get(i, 0) for i in mask_items)
    asim_score = sum(scored.get(i, 0) for i in asim_items)
    total_score = comp_score + mask_score + asim_score
    
    is_high = total_score >= 100
    classification = "Camuflaje Autista Significativo (CAT-Q >= 100)" if is_high else "Camuflaje dentro de Parámetros Típicos (< 100)"
    
    subscales_dict = {
        "Compensación (Estrategias Sociales Activas)": {
            "pd": f"{comp_score} / 63",
            "baremo": "Media autista: ~42 pts (9 ítems)",
            "nivel": "Elevado" if comp_score >= 42 else ("Moderado" if comp_score >= 30 else "Bajo"),
            "criterio": "Uso de guiones sociales aprendidos y copia de conductas" if comp_score >= 42 else "Estrategias habituales",
            "alerta": "severo" if comp_score >= 42 else ("moderado" if comp_score >= 30 else "normal")
        },
        "Enmascaramiento (Ocultamiento de Rasgos)": {
            "pd": f"{mask_score} / 56",
            "baremo": "Media autista: ~38 pts (8 ítems)",
            "nivel": "Elevado" if mask_score >= 38 else ("Moderado" if mask_score >= 26 else "Bajo"),
            "criterio": "Supresión de estereotipias y forzado de mirada" if mask_score >= 38 else "Normal",
            "alerta": "severo" if mask_score >= 38 else ("moderado" if mask_score >= 26 else "normal")
        },
        "Asimilación (Adaptación y Mimetismo Grupal)": {
            "pd": f"{asim_score} / 56",
            "baremo": "Media autista: ~40 pts (8 ítems)",
            "nivel": "Elevado" if asim_score >= 40 else ("Moderado" if asim_score >= 28 else "Bajo"),
            "criterio": "Sobreesfuerzo por encajar e interpretar un personaje" if asim_score >= 40 else "Normal",
            "alerta": "severo" if asim_score >= 40 else ("moderado" if asim_score >= 28 else "normal")
        },
        "Puntuación Total de Camuflaje (CAT-Q)": {
            "pd": f"{total_score} / 175",
            "baremo": "Corte Clínico Hull et al. >= 100 pts",
            "nivel": "Elevado / Significativo" if is_high else "Dentro de Parámetros Típicos",
            "criterio": classification,
            "alerta": "severo" if is_high else "normal"
        }
    }
    
    interpretation = (
        f"INFORME DEL CUESTIONARIO DE CAMUFLAJE DE RASGOS AUTISTAS (CAT-Q):\n"
        f"• Puntuación Total: {total_score} / 175 puntos.\n"
        f"• Clasificación Clínica: {classification}.\n"
        f"• Subescala Compensación: {comp_score}/63 pts.\n"
        f"• Subescala Enmascaramiento: {mask_score}/56 pts.\n"
        f"• Subescala Asimilación: {asim_score}/56 pts.\n\n"
        f"Conclusión Clínica: {'El puntaje evidencia un nivel de camuflaje y enmascaramiento social clínicamente relevante (>= 100 pts). Este patrón suele correlacionar con agotamiento crónico, fatiga social o burnout autista, enmascarando las dificultades nucleares del espectro.' if is_high else 'Los niveles de enmascaramiento no superan el punto de corte clínico.'}"
    )
    return float(total_score), subscales_dict, classification, interpretation


# =========================================================================
# 6. RAADS-R (RITVO AUTISM ASPERGER DIAGNOSTIC SCALE - REVISED)
# =========================================================================
def process_raads_scoring(answers):
    """
    RAADS-R (Ritvo et al., 2011)
    80 ítems, 4 subescalas. Opciones 0 a 3.
    17 ítems inversos (invertidos: 3 - valor).
    Corte clínico oficial: >= 65 puntos (Sensibilidad 97%, Especificidad 100% en TEA adultos).
    """
    ans_map = _extract_answer_map(answers)
    reversed_items = {3, 6, 11, 18, 23, 27, 33, 37, 43, 47, 52, 58, 63, 67, 72, 77, 80}
    
    soc_items = [1, 6, 8, 11, 14, 18, 20, 23, 26, 27, 31, 33, 37, 38, 39, 43, 44, 47, 48, 52, 53, 54, 58, 60, 61, 63, 64, 65, 68, 69, 70, 72, 74, 75, 76, 77, 78, 79, 80]
    leng_items = [2, 7, 15, 28, 35, 41, 57]
    circ_items = [9, 13, 16, 24, 30, 32, 40, 46, 49, 50, 56, 62, 66, 73]
    sensor_items = [3, 4, 5, 10, 12, 17, 19, 21, 22, 25, 29, 34, 36, 42, 45, 51, 55, 59, 67, 71]

    scored = {}
    for i in range(1, 81):
        raw = ans_map.get(i, 0)
        if i in reversed_items:
            scored[i] = 3 - raw if 0 <= raw <= 3 else 0
        else:
            scored[i] = raw
            
    soc_score = sum(scored.get(i, 0) for i in soc_items)
    leng_score = sum(scored.get(i, 0) for i in leng_items)
    circ_score = sum(scored.get(i, 0) for i in circ_items)
    sensor_score = sum(scored.get(i, 0) for i in sensor_items)
    total_score = soc_score + leng_score + circ_score + sensor_score
    
    is_positive = total_score >= 65
    classification = "Compatible con Espectro Autista (RAADS-R >= 65)" if is_positive else "Por Debajo del Umbral Clínico (RAADS-R < 65)"
    
    subscales_dict = {
        "Relaciones Sociales (39 ítems)": {
            "pd": f"{soc_score} / 117",
            "baremo": "Corte orientativo >= 31",
            "nivel": "Elevado" if soc_score >= 31 else "Normal",
            "criterio": "Dificultades en interacción y reciprocidad social" if soc_score >= 31 else "Dentro de parámetros típicos",
            "alerta": "severo" if soc_score >= 31 else "normal"
        },
        "Lenguaje y Comunicación (7 ítems)": {
            "pd": f"{leng_score} / 21",
            "baremo": "Corte orientativo >= 4",
            "nivel": "Elevado" if leng_score >= 4 else "Normal",
            "criterio": "Pensamiento literal, dificultades con metáforas y pragmática" if leng_score >= 4 else "Dentro de parámetros típicos",
            "alerta": "severo" if leng_score >= 4 else "normal"
        },
        "Intereses Sensoriomotores (20 ítems)": {
            "pd": f"{sensor_score} / 60",
            "baremo": "Corte orientativo >= 16",
            "nivel": "Elevado" if sensor_score >= 16 else "Normal",
            "criterio": "Hipersensibilidad sensorial y conductas autoestimulatorias" if sensor_score >= 16 else "Normal",
            "alerta": "severo" if sensor_score >= 16 else "normal"
        },
        "Intereses Circunscritos (14 ítems)": {
            "pd": f"{circ_score} / 42",
            "baremo": "Corte orientativo >= 15",
            "nivel": "Elevado" if circ_score >= 15 else "Normal",
            "criterio": "Intereses fijos, profundos y necesidad de invariabilidad" if circ_score >= 15 else "Normal",
            "alerta": "severo" if circ_score >= 15 else "normal"
        },
        "Puntuación Total RAADS-R": {
            "pd": f"{total_score} / 240",
            "baremo": "Corte Clínico Ritvo >= 65 pts",
            "nivel": "Positivo para TEA" if is_positive else "Negativo / Subclínico",
            "criterio": classification,
            "alerta": "severo" if is_positive else "normal"
        }
    }
    
    interpretation = (
        f"INFORME DIAGNÓSTICO RAADS-R (RITVO AUTISM ASPERGER DIAGNOSTIC SCALE - REVISED):\n"
        f"• Puntuación Total: {total_score} / 240 puntos.\n"
        f"• Clasificación Clínica según Baremo: {classification}.\n"
        f"• Relaciones Sociales: {soc_score} / 117 pts (Corte >= 31).\n"
        f"• Lenguaje y Comunicación: {leng_score} / 21 pts (Corte >= 4).\n"
        f"• Intereses Sensoriomotores: {sensor_score} / 60 pts (Corte >= 16).\n"
        f"• Intereses Circunscritos: {circ_score} / 42 pts (Corte >= 15).\n\n"
        f"Conclusión Clínica: Ritvo et al. determinaron que una puntuación de 65 o más presenta una sensibilidad del 97% para identificar Trastorno del Espectro Autista en adultos. "
        + ("El perfil del consultante supera el umbral diagnóstico general, mostrando sintomatología característica en la trayectoria evolutiva." if is_positive else "El puntaje obtenido se ubica por debajo del corte diagnóstico.")
    )
    return float(total_score), subscales_dict, classification, interpretation


# =========================================================================
# 7. TCS (ESCALA DE CONGRUENCIA TRANSGÉNERO)
# =========================================================================
def process_tcs_scoring(answers):
    """
    Escala de Congruencia Transgénero (TCS - Kozee et al.)
    12 ítems, Likert 1 a 5.
    Ítems inversos: 2, 6, 8 (invertidos: 6 - valor).
    """
    ans_map = _extract_answer_map(answers)
    reversed_items = {2, 6, 8}
    scored = {}
    for i in range(1, 13):
        val = ans_map.get(i, 3)
        if i in reversed_items:
            scored[i] = 6 - val
        else:
            scored[i] = val
            
    app_score = sum(scored.get(i, 0) for i in range(1, 10))
    ident_score = sum(scored.get(i, 0) for i in range(10, 13))
    total_score = app_score + ident_score
    mean_total = round(total_score / 12, 2)
    mean_app = round(app_score / 9, 2)
    mean_ident = round(ident_score / 3, 2)
    
    if mean_total >= 4.0:
        classification = "Alta Congruencia y Afirmación de Género"
        alerta = "normal"
    elif mean_total >= 3.0:
        classification = "Congruencia de Género Moderada"
        alerta = "leve"
    else:
        classification = "Baja Congruencia / Discrepancia Identitaria Sentida"
        alerta = "severo"

    subscales_dict = {
        "Congruencia de Apariencia Física (Ítems 1-9)": {
            "pd": f"{app_score} / 45 (Media: {mean_app})",
            "baremo": "Rango 1.0 a 5.0 (Mayor puntaje = mayor comodidad con apariencia)",
            "nivel": "Alta" if mean_app >= 4.0 else ("Moderada" if mean_app >= 3.0 else "Baja"),
            "criterio": "Comodidad con la expresión y corporalidad externa",
            "alerta": "normal" if mean_app >= 3.5 else "moderado"
        },
        "Aceptación de la Identidad de Género (Ítems 10-12)": {
            "pd": f"{ident_score} / 15 (Media: {mean_ident})",
            "baremo": "Rango 1.0 a 5.0 (Mayor puntaje = mayor autoaceptación)",
            "nivel": "Alta" if mean_ident >= 4.0 else ("Moderada" if mean_ident >= 3.0 else "Baja"),
            "criterio": "Autoafirmación y orgullo en la propia identidad",
            "alerta": "normal" if mean_ident >= 3.5 else "moderado"
        },
        "Puntuación Global de Congruencia (TCS)": {
            "pd": f"{total_score} / 60 (Media: {mean_total} / 5.0)",
            "baremo": "Media global en escala Likert 1 a 5",
            "nivel": classification,
            "criterio": classification,
            "alerta": alerta
        }
    }
    
    interpretation = (
        f"INFORME DE LA ESCALA DE CONGRUENCIA TRANSGÉNERO (TCS):\n"
        f"• Puntuación Media Global: {mean_total} / 5.0 pts (Total bruto: {total_score} / 60).\n"
        f"• Clasificación según Baremo: {classification}.\n"
        f"• Dimensión Apariencia Física: Media de {mean_app} / 5.0.\n"
        f"• Dimensión Aceptación de la Identidad: Media de {mean_ident} / 5.0.\n\n"
        f"Conclusión Terapéutica: {'El consultante reporta altos niveles de congruencia entre su identidad sentida y su expresión física corporal.' if mean_total >= 4.0 else 'Se aprecian discrepancias entre la identidad sentida y la corporalidad/expresión social externa, sugiriendo acompañamiento afirmativo enfocado en bienestar y congruencia.'}"
    )
    return float(total_score), subscales_dict, classification, interpretation


# =========================================================================
# 8. UGDS-GS (ESCALA DE DISFORIA DE GÉNERO DE UTRECHT)
# =========================================================================
def process_ugds_scoring(answers):
    """
    UGDS-GS (McGuire et al., 2020)
    18 ítems, Likert 1 a 5.
    Ítems inversos: 2, 6, 10, 15, 16 (invertidos: 6 - valor).
    Corte clínico: >= 54 puntos indica disforia clínicamente significativa.
    """
    ans_map = _extract_answer_map(answers)
    reversed_items = {2, 6, 10, 15, 16}
    scored = {}
    for i in range(1, 19):
        val = ans_map.get(i, 3)
        if i in reversed_items:
            scored[i] = 6 - val
        else:
            scored[i] = val
            
    total_score = sum(scored.get(i, 0) for i in range(1, 19))
    is_dysphoria = total_score >= 54
    
    if total_score >= 65:
        classification = "Disforia de Género Significativa / Alta Intensidad"
        alerta = "severo"
    elif total_score >= 54:
        classification = "Disforia de Género Moderada (Corte Clínico Superado)"
        alerta = "moderado"
    else:
        classification = "Por Debajo del Umbral de Disforia Clínica (< 54 pts)"
        alerta = "normal"
        
    subscales_dict = {
        "Puntuación Total UGDS-GS": {
            "pd": f"{total_score} / 90",
            "baremo": "Corte Clínico >= 54 pts (McGuire et al.)",
            "nivel": classification,
            "criterio": "Indicativo de disforia clínica" if is_dysphoria else "Dentro del rango no disfórico",
            "alerta": alerta
        }
    }
    
    interpretation = (
        f"INFORME DE LA ESCALA DE DISFORIA DE GÉNERO DE UTRECHT (UGDS-GS):\n"
        f"• Puntuación Total Directa: {total_score} / 90 puntos.\n"
        f"• Clasificación Clínica según Baremo: {classification}.\n"
        f"• Punto de Corte Clínico: 54 puntos.\n\n"
        f"Conclusión Terapéutica: {'El puntaje obtenido supera el umbral clínico de disforia de género de Utrecht, indicando malestar significativo asociado a características sexuales o expectativas sociales. Se sugiere acompañamiento psicoterapéutico afirmativo de apoyo y validación.' if is_dysphoria else 'El puntaje se sitúa por debajo del umbral clínico de disforia de género.'}"
    )
    return float(total_score), subscales_dict, classification, interpretation


# =========================================================================
# 9. HOLLAND (TEST DE INTERESES VOCACIONALES RIASEC)
# =========================================================================
def process_holland_scoring(answers, db=None):
    """
    Test de Intereses Vocacionales de Holland (RIASEC)
    221 ítems categorizados en R, I, A, S, E, C.
    Genera el Código Holland de 3 letras (ej. 'SAE', 'IRE').
    """
    import sqlite3
    items = []
    try:
        con = db if db else sqlite3.connect('clinica.db')
        cur = con.cursor()
        cur.execute("SELECT items_json FROM tests_definiciones WHERE code = 'HOLLAND'")
        r = cur.fetchone()
        if r and r[0]:
            items = json.loads(r[0])
    except Exception:
        items = []

    ans_map = _extract_answer_map(answers)

    cat_names = {
        'R': 'Realista (Técnico / Práctico / Mecánico)',
        'I': 'Investigador (Científico / Analítico / Intelectual)',
        'A': 'Artístico (Creativo / Expresivo / Original)',
        'S': 'Social (Asistencial / Educativo / Empático)',
        'E': 'Emprendedor (Liderazgo / Persuasión / Negocios)',
        'C': 'Convencional (Organizado / Metódico / Administrativo)'
    }
    
    scores = {'R': 0, 'I': 0, 'A': 0, 'S': 0, 'E': 0, 'C': 0}
    max_scores = {'R': 0, 'I': 0, 'A': 0, 'S': 0, 'E': 0, 'C': 0}
    
    for it in items:
        num = it.get('num')
        cat = it.get('cat')
        if cat in scores:
            max_scores[cat] += 1
            if ans_map.get(num, 0) == 1:
                scores[cat] += 1
                
    sorted_cats = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    holland_code = "".join([c[0] for c in sorted_cats[:3]])
    
    subscales_dict = {}
    for cat, score in sorted_cats:
        max_c = max_scores.get(cat, 1) or 1
        pct = round((score / max_c) * 100, 1)
        subscales_dict[cat_names[cat]] = {
            "pd": f"{score} / {max_c} ({pct}%)",
            "baremo": f"Dimensión Holland '{cat}'",
            "nivel": "Muy Alto" if pct >= 70 else ("Alto" if pct >= 50 else ("Medio" if pct >= 30 else "Bajo")),
            "criterio": f"Interés vocacional {pct}%",
            "alerta": "normal"
        }
        
    top_3_names = [f"{c[0]}: {cat_names[c[0]].split(' (')[0]}" for c in sorted_cats[:3]]
    classification = f"Código Holland RIASEC: {holland_code} ({' - '.join(top_3_names)})"
    
    total_score = sum(scores.values())
    interpretation = (
        f"INFORME DE INTERESES VOCACIONALES DE HOLLAND (RIASEC):\n"
        f"• Código de Tipología Vocacional Dominante: {holland_code}\n"
        f"• Áreas de Mayor Interés: {', '.join(top_3_names)}\n\n"
        f"Desglose del Perfil RIASEC:\n"
        + "\n".join([f"  - {cat_names[c[0]]}: {c[1]} pts ({round((c[1] / (max_scores.get(c[0], 1) or 1))*100, 1)}%)" for c in sorted_cats])
        + f"\n\nOrientación Vocacional: El código {holland_code} sugiere afinidad hacia carreras u ocupaciones en las que predominen las actividades de tipo {top_3_names[0]}, integradas con {top_3_names[1]} y {top_3_names[2]}."
    )
    return float(total_score), subscales_dict, classification, interpretation


# =========================================================================
# DISPATCHER MAESTRO UNIVERSAL
# =========================================================================
def calculate_test_scoring(test_code, answers, patient_info=None, db=None):
    """
    Dispatcher maestro para calcular el baremo psicométrico oficial de cualquier test.
    Retorna: (total_score, subscales_dict, classification, interpretation)
    """
    code = (test_code or '').strip().upper()
    patient_info = patient_info or {}
    
    # 1. ASRS-ADHD
    if code in ('ASRS-ADHD', 'TDAH', 'ADHD', 'ASRS') or 'ADHD' in code or 'TDAH' in code:
        return process_asrs_adhd_scoring(answers)
        
    # 2. BDI-II
    elif code in ('BDI-II', 'BDI2', 'BDI') or 'BDI' in code:
        return process_bdi2_scoring(answers)
        
    # 3. BAI
    elif code in ('BAI', 'BAI-BECK') or code == 'BAI':
        return process_bai_scoring(answers)
        
    # 4. AQ
    elif code in ('AQ', 'AQ-50', 'COCIENTE-AUTISTA'):
        return process_aq_scoring(answers)
        
    # 5. CAT-Q
    elif code in ('CAT-Q', 'CATQ'):
        return process_catq_scoring(answers)
        
    # 6. TCS
    elif code in ('TCS', 'CONGRUENCIA-TRANS'):
        return process_tcs_scoring(answers)
        
    # 7. UGDS-GS
    elif code in ('UGDS-GS', 'UGDS', 'UTRECHT'):
        return process_ugds_scoring(answers)
        
    # 8. RAADS-R
    elif code in ('RAADS-R', 'RAADS'):
        return process_raads_scoring(answers)
        
    # 9. HOLLAND
    elif code in ('HOLLAND', 'RIASEC'):
        return process_holland_scoring(answers, db=db)
        
    # 10. MMPI-2
    elif code in ('MMPI-2', 'MMPI2', 'MMPI'):
        from mmpi2_scoring import process_mmpi2_scoring
        return process_mmpi2_scoring(answers, patient_info=patient_info)
        
    # 11. MCMI-II
    elif code in ('MCMI-II', 'MCMI2', 'MCMI', 'MILLON', 'MILLON-II'):
        from mcmi2_scoring import process_mcmi2_scoring
        return process_mcmi2_scoring(answers, patient_info=patient_info)
        
    # 12. BARSIT
    elif code == 'BARSIT':
        from barsit_test_data import process_barsit_scoring
        return process_barsit_scoring(answers, patient_info=patient_info)
        
    # 13. ZUNG-SDS
    elif code in ('ZUNG-SDS', 'ZUNG', 'SDS'):
        from routes_tests import process_zung_sds_scoring
        return process_zung_sds_scoring(answers)
        
    # 14. HAMILTON-D
    elif code in ('HAMILTON-D', 'HAM-D', 'HAMD'):
        from routes_tests import process_hamilton_d_scoring
        return process_hamilton_d_scoring(answers)
        
    # 15. IDARE-STAI
    elif code in ('IDARE-STAI', 'IDARE', 'STAI'):
        from routes_tests import process_idare_stai_scoring
        return process_idare_stai_scoring(answers)
        
    # 16. SCL-90-R
    elif code in ('SCL-90-R', 'SCL90', 'SCL-90'):
        from routes_tests import process_scl90r_scoring
        return process_scl90r_scoring(answers, patient_info=patient_info)
        
    # 17. BSI
    elif code in ('BSI', 'BSI-53'):
        from routes_tests import process_bsi_scoring
        return process_bsi_scoring(answers, patient_info=patient_info)
        
    # 18. BECK-BHS
    elif code in ('BECK-BHS', 'BHS'):
        from routes_tests import process_beck_bhs_scoring
        return process_beck_bhs_scoring(answers)
        
    # 19. SWLS
    elif code == 'SWLS':
        from routes_tests import process_swls_scoring
        return process_swls_scoring(answers)
        
    # 20. SHIM
    elif code in ('SHIM', 'IIEF-5'):
        from routes_tests import process_shim_scoring
        return process_shim_scoring(answers)
        
    # 21. NSSS-S
    elif code == 'NSSS-S':
        from routes_tests import process_nsss_s_scoring
        return process_nsss_s_scoring(answers)
        
    # 22. FSFI
    elif code == 'FSFI':
        from routes_tests import process_fsfi_scoring
        return process_fsfi_scoring(answers)
        
    # 23. MMSE
    elif code == 'MMSE':
        from routes_tests import process_mmse_scoring
        return process_mmse_scoring(answers)
        
    # 24. AtAS
    elif code == 'ATAS':
        from routes_tests import process_atas_scoring
        return process_atas_scoring(answers)
        
    # 25. CUVINO
    elif code == 'CUVINO':
        from routes_tests import process_cuvino_scoring
        return process_cuvino_scoring(answers)
        
    # 26. ABUSO-COERCITIVO
    elif code in ('ABUSO-COERCITIVO', 'EAPC'):
        from routes_tests import process_coercitivo_scoring
        return process_coercitivo_scoring(answers)
        
    # 27. VIOLENCIA-ECON
    elif code in ('VIOLENCIA-ECON', 'IVEP'):
        from routes_tests import process_econ_scoring
        return process_econ_scoring(answers)
        
    # 28. BPRS
    elif code == 'BPRS':
        from routes_tests import process_bprs_scoring
        return process_bprs_scoring(answers)
        
    # 29. PANSS-POS
    elif code in ('PANSS-POS', 'PANSS-P'):
        from routes_tests import process_panss_scoring
        return process_panss_scoring(answers)
        
    # 30. JUICIO-REALIDAD
    elif code in ('JUICIO-REALIDAD', 'IPRJC'):
        from routes_tests import process_juicio_scoring
        return process_juicio_scoring(answers)
        
    # 31. BSSC
    elif code == 'BSSC':
        from routes_tests import process_bssc_scoring
        return process_bssc_scoring(answers)
        
    # Fallback genérico
    else:
        try:
            total_score = float(sum(int(float(v)) for v in answers.values() if str(v).replace('.', '', 1).isdigit()))
            classification = "Completado"
            interpretation = f"Puntuación Total Obtenida: {total_score} pts."
            subscales_dict = {"Puntuación Total": total_score}
        except Exception:
            total_score, subscales_dict, classification, interpretation = 0.0, {}, "Completado", "Respuestas registradas exitosamente."
        return total_score, subscales_dict, classification, interpretation
