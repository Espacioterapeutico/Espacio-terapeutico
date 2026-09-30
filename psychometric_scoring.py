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
# 10. TAS-20 (ESCALA DE ALEXITIMIA DE TORONTO - BAGBY, PARKER & TAYLOR)
# =========================================================================
def process_tas20_scoring(answers):
    """
    TAS-20 (Toronto Alexithymia Scale - Bagby, Parker & Taylor, 1994)
    20 ítems con escala Likert de 5 puntos (1 a 5).
    Ítems inversos: 4, 5, 10, 18, 19 (Puntuación invertida: 6 - valor).
    Subescalas:
    - F1: Dificultad para Identificar Sentimientos (DIF): ítems 1, 3, 6, 7, 9, 13, 14 (rango 7-35).
    - F2: Dificultad para Describir Sentimientos (DDF): ítems 2, 4, 11, 12, 17 (rango 5-25).
    - F3: Pensamiento Orientado Externamente (EOT): ítems 5, 8, 10, 15, 16, 18, 19, 20 (rango 8-40).
    Puntuación Total Directa: 20 a 100 pts.
    Puntos de corte oficiales:
    - <= 51: Sin Alexitimia (Normal)
    - 52 a 60: Alexitimia Posible / Límite
    - >= 61: Presencia Significativa de Alexitimia (Clínico)
    """
    ans_map = _extract_answer_map(answers)
    reverse_items = {4, 5, 10, 18, 19}
    
    scored_items = {}
    for i in range(1, 21):
        raw = ans_map.get(i, 3)
        if raw in (0, 1, 2, 3, 4) and max(ans_map.values(), default=0) <= 4:
            raw = raw + 1
        if raw < 1: raw = 1
        if raw > 5: raw = 5
        scored_items[i] = (6 - raw) if i in reverse_items else raw
        
    dif_items = [1, 3, 6, 7, 9, 13, 14]
    ddf_items = [2, 4, 11, 12, 17]
    eot_items = [5, 8, 10, 15, 16, 18, 19, 20]
    
    dif_score = sum(scored_items[i] for i in dif_items)
    ddf_score = sum(scored_items[i] for i in ddf_items)
    eot_score = sum(scored_items[i] for i in eot_items)
    total_score = dif_score + ddf_score + eot_score
    
    if total_score <= 51:
        classification = "Sin Alexitimia (Nivel Normal)"
        alerta = "normal"
        desc_global = "Puntuación dentro de la normalidad. La persona presenta adecuada capacidad para identificar, diferenciar y verbalizar sus estados afectivos, manteniendo un estilo introspectivo saludable."
    elif total_score <= 60:
        classification = "Alexitimia Posible / Zona Límite (Riesgo Moderado)"
        alerta = "moderado"
        desc_global = "Puntuación límite o intermedia. Sugiere dificultades moderadas para conectar con el mundo afectivo interno o verbalizar emociones en momentos de estrés o conflicto interpersonal."
    else:
        classification = "Presencia Significativa de Alexitimia (Criterio Clínico)"
        alerta = "severo"
        desc_global = "Puntuación con significación clínica elevada. Indica marcadas dificultades para identificar emociones, severa limitación para verbalizar sentimientos a otros y un estilo cognitivo predominantemente concreto y orientado al exterior."
        
    subscales_dict = {
        "Dificultad para Identificar Sentimientos (DIF)": {
            "pd": f"{dif_score} / 35",
            "nivel": "Elevado" if dif_score >= 22 else ("Moderado" if dif_score >= 15 else "Bajo / Adecuado"),
            "alerta": "severo" if dif_score >= 22 else ("moderado" if dif_score >= 15 else "normal"),
            "criterio": "Ítems 1, 3, 6, 7, 9, 13, 14"
        },
        "Dificultad para Describir Sentimientos (DDF)": {
            "pd": f"{ddf_score} / 25",
            "nivel": "Elevado" if ddf_score >= 16 else ("Moderado" if ddf_score >= 11 else "Bajo / Adecuado"),
            "alerta": "severo" if ddf_score >= 16 else ("moderado" if ddf_score >= 11 else "normal"),
            "criterio": "Ítems 2, 4, 11, 12, 17"
        },
        "Pensamiento Orientado Externamente (EOT)": {
            "pd": f"{eot_score} / 40",
            "nivel": "Elevado" if eot_score >= 25 else ("Moderado" if eot_score >= 18 else "Bajo / Adecuado"),
            "alerta": "severo" if eot_score >= 25 else ("moderado" if eot_score >= 18 else "normal"),
            "criterio": "Ítems 5, 8, 10, 15, 16, 18, 19, 20"
        },
        "Puntuación Total TAS-20": {
            "pd": f"{total_score} / 100",
            "nivel": classification,
            "alerta": alerta,
            "criterio": "Baremo de Bagby, Parker & Taylor (Corte <=51 / 52-60 / >=61)"
        }
    }
    
    interpretation = (
        f"INFORME PSICOMÉTRICO: ESCALA DE ALEXITIMIA DE TORONTO (TAS-20)\n\n"
        f"• Puntuación Total: {total_score}/100 pts\n"
        f"• Clasificación Clínica: {classification}\n\n"
        f"Interpretación Diagnóstica:\n{desc_global}\n\n"
        f"Desglose por Factores Dimensionales:\n"
        f"1. Dificultad para Identificar Sentimientos (DIF): {dif_score}/35 pts — Nivel {subscales_dict['Dificultad para Identificar Sentimientos (DIF)']['nivel']}.\n"
        f"2. Dificultad para Describir Sentimientos (DDF): {ddf_score}/25 pts — Nivel {subscales_dict['Dificultad para Describir Sentimientos (DDF)']['nivel']}.\n"
        f"3. Pensamiento Orientado Externamente (EOT): {eot_score}/40 pts — Nivel {subscales_dict['Pensamiento Orientado Externamente (EOT)']['nivel']}.\n\n"
        f"Sugerencias Clínicas: " + (
            "Se aconseja trabajar en psicoeducación emocional, conexión somatosensorial y ampliación del vocabulario afectivo para facilitar la regulación de las emociones."
            if total_score >= 52 else "Mantiene un perfil emocional funcional adecuado para el abordaje terapéutico regular."
        )
    )
    return float(total_score), subscales_dict, classification, interpretation


# =========================================================================
# 11. ERQ (CUESTIONARIO DE REGULACIÓN EMOCIONAL - GROSS & JOHN / CANALES)
# =========================================================================
def process_erq_scoring(answers, patient_info=None):
    """
    ERQ (Emotion Regulation Questionnaire - Gross & John, 2003 / Canales et al., 2022)
    10 ítems con escala Likert de 7 puntos (1 a 7).
    Subescalas:
    - Reevaluación Cognitiva (CR): ítems 1, 3, 5, 7, 8, 10 (rango 6 a 42).
    - Supresión Expresiva (ES): ítems 2, 4, 6, 9 (rango 4 a 28).
    Baremos normativos (Canales et al., 2022):
    - Reevaluación: Bajo <= 26, Promedio 27-34, Alto >= 35.
    - Supresión:
      * Hombres: Bajo <= 11, Promedio 12-19, Alto >= 20.
      * Mujeres: Bajo <= 9, Promedio 10-17, Alto >= 18.
    """
    ans_map = _extract_answer_map(answers)
    patient_info = patient_info or {}
    genero_str = (patient_info.get('genero') or '').strip().lower()
    is_male = genero_str in ['m', 'masculino', 'hombre', 'varon', 'varón'] or any(genero_str.startswith(g) for g in ['masc', 'homb', 'var'])
    is_female = genero_str in ['f', 'femenino', 'mujer'] or any(genero_str.startswith(g) for g in ['fem', 'muj'])
    
    scored_items = {}
    for i in range(1, 11):
        v = ans_map.get(i, 4)
        if v < 1: v = 1
        if v > 7: v = 7
        scored_items[i] = v
        
    cr_items = [1, 3, 5, 7, 8, 10]
    es_items = [2, 4, 6, 9]
    
    cr_score = sum(scored_items[i] for i in cr_items)
    es_score = sum(scored_items[i] for i in es_items)
    total_score = cr_score + es_score
    
    # Niveles Reevaluación
    if cr_score <= 26:
        cr_nivel = "Uso Bajo (Dificultad de Reevaluación Adaptativa)"
        cr_alerta = "moderado"
        cr_interp = "Tiende a experimentar dificultades para reformular cognitivamente las situaciones estresantes antes de que provoquen una respuesta emocional displacentera."
    elif cr_score <= 34:
        cr_nivel = "Uso Promedio / Normativo"
        cr_alerta = "normal"
        cr_interp = "Presenta un empleo habitual y adecuado de la reinterpretación cognitiva para amortiguar estados emocionales negativos o potenciar los positivos."
    else:
        cr_nivel = "Uso Alto / Frecuente (Estrategia Adaptativa)"
        cr_alerta = "normal"
        cr_interp = "Alta capacidad y disposición para modificar su perspectiva y pensamiento ante acontecimientos difíciles, manteniendo una buena autorregulación emocional."
        
    # Niveles Supresión (diferenciado por sexo)
    if is_female:
        if es_score <= 9:
            es_nivel = "Uso Bajo (Alta Expresividad Emocional)"
            es_alerta = "normal"
            es_desc = "Baja inhibición; expresa espontánea y saludablemente sus estados afectivos en sus interacciones."
        elif es_score <= 17:
            es_nivel = "Uso Promedio / Normativo"
            es_alerta = "normal"
            es_desc = "Nivel normativo de contención emocional acorde a los contextos interpersonales."
        else:
            es_nivel = "Uso Alto (Inhibición Expresiva Marcada)"
            es_alerta = "severo"
            es_desc = "Fuerte tendencia a ocultar e inhibir las emociones internas, lo cual se asocia con mayor sobrecarga alostática y menor intimidad relacional."
    elif is_male:
        if es_score <= 11:
            es_nivel = "Uso Bajo (Alta Expresividad Emocional)"
            es_alerta = "normal"
            es_desc = "Baja inhibición; expresa espontánea y abiertamente lo que experimenta internamente."
        elif es_score <= 19:
            es_nivel = "Uso Promedio / Normativo"
            es_alerta = "normal"
            es_desc = "Nivel normativo de contención emocional en consonancia con el promedio poblacional."
        else:
            es_nivel = "Uso Alto (Inhibición Expresiva Marcada)"
            es_alerta = "severo"
            es_desc = "Tendencia significativa a reprimir la expresión externa de emociones tanto positivas como negativas, pudiendo generar distanciamiento interpersonal o somatizaciones."
    else:
        if es_score <= 10:
            es_nivel = "Uso Bajo (Alta Expresividad Emocional)"
            es_alerta = "normal"
            es_desc = "Baja inhibición expresiva general."
        elif es_score <= 18:
            es_nivel = "Uso Promedio / Normativo"
            es_alerta = "normal"
            es_desc = "Nivel estándar de contención expresiva."
        else:
            es_nivel = "Uso Alto (Inhibición Emocional Marcada)"
            es_alerta = "severo"
            es_desc = "Tendencia relevante a sofocar la manifestación externa de las emociones."

    # Clasificación Global del Perfil
    es_alta = (es_score >= 18 if is_female else (es_score >= 20 if is_male else es_score >= 19))
    cr_alta = cr_score >= 27
    if cr_alta and not es_alta:
        classification = "Perfil Regulador Adaptativo (Alta Reevaluación / Baja Inhibición)"
    elif cr_alta and es_alta:
        classification = "Perfil Regulador Mixto (Estratégico pero con Inhibición Afectiva)"
    elif not cr_alta and es_alta:
        classification = "Perfil Desadaptativo / Supresor (Baja Flexibilidad y Alta Represión)"
    else:
        classification = "Perfil No Regulado / Reactivo (Baja Reevaluación y Baja Inhibición)"

    subscales_dict = {
        "Reevaluación Cognitiva (CR)": {
            "pd": f"{cr_score} / 42",
            "nivel": cr_nivel,
            "alerta": cr_alerta,
            "criterio": "Media pop: ~29.9 (Bajo <=26, Medio 27-34, Alto >=35)"
        },
        "Supresión Expresiva (ES)": {
            "pd": f"{es_score} / 28",
            "nivel": es_nivel,
            "alerta": es_alerta,
            "criterio": f"Baremo {'Mujeres' if is_female else ('Hombres' if is_male else 'General')}"
        },
        "Puntuación Global ERQ": {
            "pd": f"{total_score} / 70",
            "nivel": classification,
            "alerta": "moderado" if not cr_alta or es_alta else "normal",
            "criterio": "Gross & John / Canales et al."
        }
    }

    interpretation = (
        f"INFORME DEL CUESTIONARIO DE REGULACIÓN EMOCIONAL (ERQ):\n\n"
        f"• Perfil de Regulación Emocional: {classification}\n"
        f"• Baremo Aplicado: {'Baremo Femenino' if is_female else ('Baremo Masculino' if is_male else 'Baremo General')}\n\n"
        f"1. Reevaluación Cognitiva (CR): {cr_score}/42 pts — {cr_nivel}\n"
        f"   {cr_interp}\n\n"
        f"2. Supresión Expresiva (ES): {es_score}/28 pts — {es_nivel}\n"
        f"   {es_desc}\n\n"
        f"Recomendación Terapéutica: " + (
            "Se sugiere fortalecer la reestructuración cognitiva y desensibilizar el temor a la expresión emocional libre y asertiva."
            if not cr_alta or es_alta else "Perfil regulatorio adaptativo que favorece una adecuada resiliencia psicológica y salud relacional."
        )
    )
    return float(total_score), subscales_dict, classification, interpretation


# =========================================================================
# 12. TMMS-24 (TRAIT META-MOOD SCALE - FERNÁNDEZ-BERROCAL ET AL., 2004)
# =========================================================================
def process_tmms24_scoring(answers, patient_info=None):
    """
    TMMS-24 (Escala de Inteligencia Emocional Percibida - Salovey & Mayer / Fernández-Berrocal et al., 2004)
    24 ítems con escala Likert de 5 puntos (1 a 5).
    Subescalas (8 ítems cada una, rango 8 a 40):
    - Atención Emocional (ítems 1-8).
    - Claridad Emocional (ítems 9-16).
    - Reparación Emocional (ítems 17-24).
    Baremos normativos diferenciados por sexo (Fernández-Berrocal et al., 2004).
    """
    ans_map = _extract_answer_map(answers)
    patient_info = patient_info or {}
    genero_str = (patient_info.get('genero') or '').strip().lower()
    is_male = genero_str in ['m', 'masculino', 'hombre', 'varon', 'varón'] or any(genero_str.startswith(g) for g in ['masc', 'homb', 'var'])
    is_female = genero_str in ['f', 'femenino', 'mujer'] or any(genero_str.startswith(g) for g in ['fem', 'muj'])
    
    scored_items = {}
    for i in range(1, 25):
        v = ans_map.get(i, 3)
        if v < 1: v = 1
        if v > 5: v = 5
        scored_items[i] = v
        
    atencion_items = list(range(1, 9))
    claridad_items = list(range(9, 17))
    reparacion_items = list(range(17, 25))
    
    atencion_score = sum(scored_items[i] for i in atencion_items)
    claridad_score = sum(scored_items[i] for i in claridad_items)
    reparacion_score = sum(scored_items[i] for i in reparacion_items)
    total_score = atencion_score + claridad_score + reparacion_score
    
    # Baremos oficiales por sexo
    if is_female:
        if atencion_score < 24:
            atn_desc = "Debe mejorar su atención: presta poca atención a sus emociones"
            atn_alerta = "moderado"
        elif atencion_score <= 35:
            atn_desc = "Adecuada atención a sus emociones"
            atn_alerta = "normal"
        else:
            atn_desc = "Debe mejorar su atención: presta demasiada atención (posible hipervigilancia/rumiación)"
            atn_alerta = "moderado"
            
        if claridad_score < 23:
            cla_desc = "Debe mejorar su claridad: dificultad para comprender lo que siente"
            cla_alerta = "moderado"
        elif claridad_score <= 34:
            cla_desc = "Adecuada comprensión de sus estados emocionales"
            cla_alerta = "normal"
        else:
            cla_desc = "Excelente comprensión y claridad emocional"
            cla_alerta = "normal"
            
        if reparacion_score < 23:
            rep_desc = "Debe mejorar su capacidad de regulación / reparación emocional"
            rep_alerta = "moderado"
        elif reparacion_score <= 34:
            rep_desc = "Adecuada capacidad para reparar y regular estados de ánimo negativos"
            rep_alerta = "normal"
        else:
            rep_desc = "Excelente capacidad de regulación y optimismo reparador"
            rep_alerta = "normal"
            
    elif is_male:
        if atencion_score < 21:
            atn_desc = "Debe mejorar su atención: presta poca atención a sus emociones"
            atn_alerta = "moderado"
        elif atencion_score <= 32:
            atn_desc = "Adecuada atención a sus emociones"
            atn_alerta = "normal"
        else:
            atn_desc = "Debe mejorar su atención: presta demasiada atención (hipervigilancia/rumiación)"
            atn_alerta = "moderado"
            
        if claridad_score < 25:
            cla_desc = "Debe mejorar su claridad: dificultad para comprender lo que siente"
            cla_alerta = "moderado"
        elif claridad_score <= 35:
            cla_desc = "Adecuada comprensión de sus estados emocionales"
            cla_alerta = "normal"
        else:
            cla_desc = "Excelente comprensión y claridad emocional"
            cla_alerta = "normal"
            
        if reparacion_score < 23:
            rep_desc = "Debe mejorar su capacidad de regulación / reparación emocional"
            rep_alerta = "moderado"
        elif reparacion_score <= 35:
            rep_desc = "Adecuada capacidad para reparar y regular estados de ánimo negativos"
            rep_alerta = "normal"
        else:
            rep_desc = "Excelente capacidad de regulación y optimismo reparador"
            rep_alerta = "normal"
            
    else:
        if atencion_score < 22:
            atn_desc = "Poca atención a las emociones (Debe mejorar)"
            atn_alerta = "moderado"
        elif atencion_score <= 33:
            atn_desc = "Adecuada atención emocional"
            atn_alerta = "normal"
        else:
            atn_desc = "Demasiada atención emocional (Riesgo de rumiación)"
            atn_alerta = "moderado"

        if claridad_score < 24:
            cla_desc = "Baja claridad emocional (Debe mejorar)"
            cla_alerta = "moderado"
        elif claridad_score <= 34:
            cla_desc = "Adecuada claridad emocional"
            cla_alerta = "normal"
        else:
            cla_desc = "Excelente claridad emocional"
            cla_alerta = "normal"

        if reparacion_score < 23:
            rep_desc = "Baja capacidad de reparación (Debe mejorar)"
            rep_alerta = "moderado"
        elif reparacion_score <= 34:
            rep_desc = "Adecuada reparación emocional"
            rep_alerta = "normal"
        else:
            rep_desc = "Excelente capacidad de reparación emocional"
            rep_alerta = "normal"

    alertas_count = sum(1 for a in [atn_alerta, cla_alerta, rep_alerta] if a == 'moderado')
    if alertas_count == 0:
        classification = "Inteligencia Emocional Percibida Óptima y Equilibrada"
    elif alertas_count == 1:
        classification = "Inteligencia Emocional Percibida con Área Específica a Fortalecer"
    else:
        classification = "Dificultades en Inteligencia Emocional Percibida (Atención, Claridad o Regulación)"

    subscales_dict = {
        "Atención Emocional": {
            "pd": f"{atencion_score} / 40",
            "nivel": atn_desc,
            "alerta": atn_alerta,
            "criterio": "Baremo Fernández-Berrocal"
        },
        "Claridad Emocional": {
            "pd": f"{claridad_score} / 40",
            "nivel": cla_desc,
            "alerta": cla_alerta,
            "criterio": "Baremo Fernández-Berrocal"
        },
        "Reparación Emocional": {
            "pd": f"{reparacion_score} / 40",
            "nivel": rep_desc,
            "alerta": rep_alerta,
            "criterio": "Baremo Fernández-Berrocal"
        },
        "Puntuación Global TMMS-24": {
            "pd": f"{total_score} / 120",
            "nivel": classification,
            "alerta": "moderado" if alertas_count > 0 else "normal",
            "criterio": "Evaluación Perceptivo-Emocional"
        }
    }

    interpretation = (
        f"INFORME PSICOMÉTRICO: TRAIT META-MOOD SCALE-24 (TMMS-24)\n\n"
        f"• Puntuación Total Global: {total_score}/120 pts\n"
        f"• Diagnóstico del Perfil: {classification}\n"
        f"• Grupo de Baremo Aplicado: {'Norma Femenina' if is_female else ('Norma Masculina' if is_male else 'Norma Poblacional General')}\n\n"
        f"Resultados por Dimensiones de Inteligencia Emocional:\n"
        f"1. Atención Emocional: {atencion_score}/40 pts\n"
        f"   Dictamen: {atn_desc}\n\n"
        f"2. Claridad Emocional: {claridad_score}/40 pts\n"
        f"   Dictamen: {cla_desc}\n\n"
        f"3. Reparación Emocional: {reparacion_score}/40 pts\n"
        f"   Dictamen: {rep_desc}\n\n"
        f"Conclusión Clínica: " + (
            "Se observa un patrón armónico de autoconocimiento, comprensión de estados internos y habilidad para modular el afecto disfórico."
            if alertas_count == 0 else "Se recomienda orientar la intervención hacia el entrenamiento en habilidades de comprensión emocional o técnicas de desactivación rumiativa / reparación del estado de ánimo."
        )
    )
    return float(total_score), subscales_dict, classification, interpretation


# =========================================================================
# 13. DERS-E (ESCALA DE DIFICULTADES EN LA REGULACIÓN EMOCIONAL - HERVÁS & JÓDAR)
# =========================================================================
def process_ders_scoring(answers, patient_info=None):
    """
    DERS-E (Escala de Dificultades en la Regulación Emocional - Versión adaptada de 28 ítems por Hervás & Jódar, 2008)
    28 ítems con escala Likert de 5 puntos (1 a 5).
    5 Factores:
    - Descontrol Emocional (9 ítems): 3, 13, 14, 15, 17, 22, 25, 26, 28 (Media 16.2, DE 7.1).
    - Rechazo Emocional (7 ítems): 10, 11, 18, 19, 20, 23, 24 (Media 14.7, DE 6.4).
    - Interferencia Cotidiana (4 ítems): 12, 16, 21, 27 (Media 10.1, DE 3.8).
    - Desatención Emocional (4 ítems, inversos): 2, 6, 7, 9 (Media 9.6, DE 3.3).
    - Confusión Emocional (4 ítems, ítem 1 inverso): 1, 4, 5, 8 (Media 7.8, DE 3.1).
    Total: Rango 28 a 140 (Media 58.4, DE 17.6).
    """
    ans_map = _extract_answer_map(answers)
    reverse_items = {1, 2, 6, 7, 9}
    
    scored_items = {}
    for i in range(1, 29):
        v = ans_map.get(i, 3)
        if v < 1: v = 1
        if v > 5: v = 5
        scored_items[i] = (6 - v) if i in reverse_items else v
        
    descontrol_items = [3, 13, 14, 15, 17, 22, 25, 26, 28]
    rechazo_items = [10, 11, 18, 19, 20, 23, 24]
    interferencia_items = [12, 16, 21, 27]
    desatencion_items = [2, 6, 7, 9]
    confusion_items = [1, 4, 5, 8]
    
    descontrol_score = sum(scored_items[i] for i in descontrol_items)
    rechazo_score = sum(scored_items[i] for i in rechazo_items)
    interferencia_score = sum(scored_items[i] for i in interferencia_items)
    desatencion_score = sum(scored_items[i] for i in desatencion_items)
    confusion_score = sum(scored_items[i] for i in confusion_items)
    total_score = descontrol_score + rechazo_score + interferencia_score + desatencion_score + confusion_score
    
    if total_score < 58:
        classification = "Dificultades Bajas / Regulación Emocional Óptima"
        alerta = "normal"
        desc_global = "Puntuación en el percentil inferior a la media normativa. La persona cuenta con recursos psicológicos sólidos para tolerar, comprender y modular sus experiencias emocionales sin verse desbordada."
    elif total_score <= 75:
        classification = "Dificultades Moderadas / Promedio Normativo"
        alerta = "leve"
        desc_global = "Puntuación dentro del rango medio esperado de la población. Manifiesta oscilaciones o dificultades ocasionales en la regulación del afecto displacentero, pero sin compromiso funcional severo."
    elif total_score <= 93:
        classification = "Dificultades Altas en Regulación Emocional (Significación Clínica)"
        alerta = "moderado"
        desc_global = "Puntuación superior a 1 desviación estándar sobre la media. Evidencia dificultades clínicamente significativas para contener impulsos, aceptar emociones desagradables o sostener actividades cotidianas durante episodios de malestar."
    else:
        classification = "Desregulación Emocional Severa (Alerta Clínica Alta)"
        alerta = "severo"
        desc_global = "Puntuación superior a 2 desviaciones estándar sobre la media. Indica dificultades generalizadas y graves en todos los componentes de la regulación afectiva, con alto riesgo de conductas impulsivas o desbordamiento emocional desadaptativo."

    subscales_dict = {
        "Descontrol Emocional": {
            "pd": f"{descontrol_score} / 45",
            "nivel": "Elevado" if descontrol_score >= 23 else ("Moderado" if descontrol_score >= 17 else "Bajo"),
            "alerta": "severo" if descontrol_score >= 23 else ("moderado" if descontrol_score >= 17 else "normal"),
            "criterio": "Norma Hervás: M=16.2, DE=7.1"
        },
        "Rechazo Emocional": {
            "pd": f"{rechazo_score} / 35",
            "nivel": "Elevado" if rechazo_score >= 21 else ("Moderado" if rechazo_score >= 15 else "Bajo"),
            "alerta": "severo" if rechazo_score >= 21 else ("moderado" if rechazo_score >= 15 else "normal"),
            "criterio": "Norma Hervás: M=14.7, DE=6.4"
        },
        "Interferencia Cotidiana": {
            "pd": f"{interferencia_score} / 20",
            "nivel": "Elevado" if interferencia_score >= 14 else ("Moderado" if interferencia_score >= 11 else "Bajo"),
            "alerta": "severo" if interferencia_score >= 14 else ("moderado" if interferencia_score >= 11 else "normal"),
            "criterio": "Norma Hervás: M=10.1, DE=3.8"
        },
        "Desatención Emocional": {
            "pd": f"{desatencion_score} / 20",
            "nivel": "Elevado" if desatencion_score >= 13 else ("Moderado" if desatencion_score >= 10 else "Bajo"),
            "alerta": "severo" if desatencion_score >= 13 else ("moderado" if desatencion_score >= 10 else "normal"),
            "criterio": "Norma Hervás: M=9.6, DE=3.3"
        },
        "Confusión Emocional": {
            "pd": f"{confusion_score} / 20",
            "nivel": "Elevado" if confusion_score >= 11 else ("Moderado" if confusion_score >= 8 else "Bajo"),
            "alerta": "severo" if confusion_score >= 11 else ("moderado" if confusion_score >= 8 else "normal"),
            "criterio": "Norma Hervás: M=7.8, DE=3.1"
        },
        "Puntuación Global DERS-E": {
            "pd": f"{total_score} / 140",
            "nivel": classification,
            "alerta": alerta,
            "criterio": "Baremo Hervás & Jódar (M=58.4, DE=17.6)"
        }
    }

    interpretation = (
        f"INFORME PSICOMÉTRICO: ESCALA DE DIFICULTADES EN LA REGULACIÓN EMOCIONAL (DERS-E)\n\n"
        f"• Puntuación Total Global: {total_score}/140 pts\n"
        f"• Clasificación Clínica: {classification}\n"
        f"• Referencia Baremo: Adaptación española de 28 ítems (Hervás & Jódar, 2008; N=254)\n\n"
        f"Interpretación Diagnóstica:\n{desc_global}\n\n"
        f"Perfil Dimensional por Factores:\n"
        f"1. Descontrol Emocional: {descontrol_score}/45 pts (M=16.2, DE=7.1) — Nivel {subscales_dict['Descontrol Emocional']['nivel']}.\n"
        f"2. Rechazo Emocional: {rechazo_score}/35 pts (M=14.7, DE=6.4) — Nivel {subscales_dict['Rechazo Emocional']['nivel']}.\n"
        f"3. Interferencia Cotidiana: {interferencia_score}/20 pts (M=10.1, DE=3.8) — Nivel {subscales_dict['Interferencia Cotidiana']['nivel']}.\n"
        f"4. Desatención Emocional: {desatencion_score}/20 pts (M=9.6, DE=3.3) — Nivel {subscales_dict['Desatención Emocional']['nivel']}.\n"
        f"5. Confusión Emocional: {confusion_score}/20 pts (M=7.8, DE=3.1) — Nivel {subscales_dict['Confusión Emocional']['nivel']}.\n\n"
        f"Recomendaciones Clínicas: " + (
            "Se recomienda focalizar el plan terapéutico en técnicas de aceptación emocional (reducción de culpa y vergüenza secundaria), entrenamiento en tolerancia al malestar y habilidades DBT de regulación del afecto e impulsividad."
            if total_score >= 76 else "El paciente conserva un repertorio funcional de regulación afectiva adecuado para las demandas de su vida diaria."
        )
    )
    return float(total_score), subscales_dict, classification, interpretation
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
        
    # 32. TAS-20 (Alexitimia de Toronto)
    elif code in ('TAS-20', 'TAS20', 'ALEXITIMIA', 'TORONTO') or 'ALEXITIMIA' in code:
        return process_tas20_scoring(answers)
        
    # 33. ERQ (Cuestionario de Regulación Emocional)
    elif code in ('ERQ', 'REGULACION-EMOCIONAL', 'GROSS'):
        return process_erq_scoring(answers, patient_info=patient_info)
        
    # 34. TMMS-24 (Inteligencia Emocional Percibida)
    elif code in ('TMMS-24', 'TMMS24', 'TMMS', 'INTELIGENCIA-EMOCIONAL'):
        return process_tmms24_scoring(answers, patient_info=patient_info)
        
    # 35. DERS-E (Dificultades en la Regulación Emocional)
    elif code in ('DERS-E', 'DERS', 'DERS-28', 'DERS28'):
        return process_ders_scoring(answers, patient_info=patient_info)
        
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
