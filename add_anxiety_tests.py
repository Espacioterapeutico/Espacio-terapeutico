import os
import json

# 1. Update psychometric_scoring.py
with open('psychometric_scoring.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add scoring functions if not exist
if 'process_lsas_scoring' not in content:
    scoring_code = """
def process_lsas_scoring(answers):
    ans_map = _extract_answer_map(answers)
    total_miedo = 0
    total_evitacion = 0
    for i in range(1, 49):
        val = ans_map.get(i, 0)
        if i % 2 != 0:
            total_miedo += val
        else:
            total_evitacion += val
    total = total_miedo + total_evitacion
    
    if total <= 54: clas = "Ansiedad Social Leve o Inexistente"
    elif total <= 65: clas = "Ansiedad Social Moderada"
    elif total <= 80: clas = "Ansiedad Social Marcada"
    elif total <= 95: clas = "Ansiedad Social Severa"
    else: clas = "Ansiedad Social Muy Severa"
    
    interp = f"Miedo: {total_miedo}/72. Evitación: {total_evitacion}/72. El paciente presenta un cuadro compatible con {clas.lower()}."
    return total, {"Miedo": total_miedo, "Evitación": total_evitacion}, clas, interp

def process_spin_scoring(answers):
    ans_map = _extract_answer_map(answers)
    total = sum(ans_map.get(i, 0) for i in range(1, 18))
    
    if total <= 20: clas = "Sin Ansiedad Social Clínica"
    elif total <= 30: clas = "Ansiedad Social Leve"
    elif total <= 40: clas = "Ansiedad Social Moderada"
    elif total <= 50: clas = "Ansiedad Social Severa"
    else: clas = "Ansiedad Social Muy Severa"
    
    interp = f"Puntuación total: {total}/68. El paciente reporta síntomas compatibles con {clas.lower()}."
    return total, {"Puntuación Total": total}, clas, interp
"""
    content += "\n" + scoring_code

# Add to calculate_test_scoring
if "'LSAS'" not in content:
    hook = """    # LSAS
    elif code in ('LSAS', 'LSAS-SR'):
        return process_lsas_scoring(answers)
        
    # SPIN
    elif code == 'SPIN':
        return process_spin_scoring(answers)
        
    # 4. AQ"""
    content = content.replace("    # 4. AQ", hook)

with open('psychometric_scoring.py', 'w', encoding='utf-8') as f:
    f.write(content)

# 2. Update routes_tests.py
with open('routes_tests.py', 'r', encoding='utf-8') as f:
    rcontent = f.read()

# Add to tests_with_baremo
if "'LSAS'" not in rcontent:
    rcontent = rcontent.replace("'BSSC'", "'BSSC', 'LSAS', 'LSAS-SR', 'SPIN'")
    rcontent = rcontent.replace("'HAM'))", "'HAM', 'LSAS', 'SPIN'))")

# Add definition function
if "def ensure_social_anxiety_tests_definitions(db):" not in rcontent:
    def_code = '''
def ensure_social_anxiety_tests_definitions(db):
    import json
    cursor = db.cursor()
    # SPIN
    spin_opciones = [
        {"val": 0, "text": "Nada"},
        {"val": 1, "text": "Un poco"},
        {"val": 2, "text": "Algo"},
        {"val": 3, "text": "Mucho"},
        {"val": 4, "text": "Extremadamente"}
    ]
    spin_items = [
        {"id": 1, "texto": "Tengo miedo de las personas que tienen autoridad.", "reverse": False},
        {"id": 2, "texto": "Me molesta ruborizarme frente a las personas.", "reverse": False},
        {"id": 3, "texto": "Las fiestas y eventos sociales me asustan.", "reverse": False},
        {"id": 4, "texto": "Evito hablar con personas que no conozco.", "reverse": False},
        {"id": 5, "texto": "Me da mucho miedo que me critiquen.", "reverse": False},
        {"id": 6, "texto": "Evito hacer cosas o hablar con personas por miedo a avergonzarme.", "reverse": False},
        {"id": 7, "texto": "Transpirar frente a las personas me causa angustia.", "reverse": False},
        {"id": 8, "texto": "Evito ir a fiestas.", "reverse": False},
        {"id": 9, "texto": "Evito hacer actividades en las que sea el centro de atencin.", "reverse": False},
        {"id": 10, "texto": "Me da miedo hablar con extraos.", "reverse": False},
        {"id": 11, "texto": "Evito tener que dar discursos.", "reverse": False},
        {"id": 12, "texto": "Hara cualquier cosa por evitar que me critiquen.", "reverse": False},
        {"id": 13, "texto": "Las palpitaciones me molestan cuando estoy con otras personas.", "reverse": False},
        {"id": 14, "texto": "Tengo miedo de hacer las cosas mal cuando me estn observando.", "reverse": False},
        {"id": 15, "texto": "Siento miedo de que la gente me mire.", "reverse": False},
        {"id": 16, "texto": "Evito hablar con cualquier persona que tenga autoridad.", "reverse": False},
        {"id": 17, "texto": "Temblar frente a los dems me angustia.", "reverse": False}
    ]
    cursor.execute("SELECT code FROM tests_definiciones WHERE code = 'SPIN'")
    if not cursor.fetchone():
        cursor.execute("""
            INSERT INTO tests_definiciones (code, nombre, siglas, categoria, descripcion, instrucciones, escala_opciones_json, items_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            'SPIN', 'Inventario de Fobia Social (SPIN)', 'SPIN', 'Ansiedad',
            'Evala la presencia y severidad de los sntomas de fobia social/ansiedad social.',
            'Indique cunto le han molestado las siguientes situaciones durante la ltima semana.',
            json.dumps(spin_opciones), json.dumps(spin_items)
        ))

    # LSAS
    lsas_opciones = [
        {"val": 0, "text": "0 - Ninguno (Miedo) / Nunca (Evitacin)"},
        {"val": 1, "text": "1 - Leve (Miedo) / Rara vez (Evitacin)"},
        {"val": 2, "text": "2 - Moderado (Miedo) / A veces (Evitacin)"},
        {"val": 3, "text": "3 - Severo (Miedo) / Normalmente (Evitacin)"}
    ]
    sit = [
        "Usar el telfono en pblico.",
        "Participar en grupos pequeos.",
        "Comer en lugares pblicos.",
        "Beber con otras personas en lugares pblicos.",
        "Hablar con alguien que tiene autoridad.",
        "Actuar, presentarse o hablar frente a una audiencia.",
        "Ir a una fiesta.",
        "Trabajar mientras lo observan.",
        "Escribir mientras lo observan.",
        "Llamar a alguien que no conoce muy bien.",
        "Hablar con personas que no conoce muy bien.",
        "Conocer a personas extraas.",
        "Orinar en un bao pblico.",
        "Entrar a una habitacin cuando los dems ya estn sentados.",
        "Ser el centro de atencin.",
        "Hablar sin preparacin (improvisar) en una reunin.",
        "Hacer una prueba o examen.",
        "Expresar desacuerdo o desaprobacin a personas que no conoce muy bien.",
        "Mirar a los ojos de personas que no conoce muy bien.",
        "Dar un informe a un grupo.",
        "Intentar conocer a alguien con fines romnticos/sexuales.",
        "Devolver productos a una tienda.",
        "Dar una fiesta.",
        "Resistir la presin de un vendedor."
    ]
    lsas_items = []
    idx = 1
    for s in sit:
        lsas_items.append({"id": idx, "texto": f"MIEDO: {s}", "reverse": False})
        lsas_items.append({"id": idx+1, "texto": f"EVITACIN: {s}", "reverse": False})
        idx += 2
        
    cursor.execute("SELECT code FROM tests_definiciones WHERE code = 'LSAS-SR'")
    if not cursor.fetchone():
        cursor.execute("""
            INSERT INTO tests_definiciones (code, nombre, siglas, categoria, descripcion, instrucciones, escala_opciones_json, items_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            'LSAS-SR', 'Escala de Ansiedad Social de Liebowitz (Auto-reporte)', 'LSAS-SR', 'Ansiedad',
            'Evala el miedo y la evitacin en situaciones sociales y de desempeo.',
            'Para cada situacin, indique el grado de MIEDO que siente y con qu frecuencia EVITA la situacin.',
            json.dumps(lsas_opciones), json.dumps(lsas_items)
        ))
    db.commit()
'''
    rcontent += "\n" + def_code

# Add hook to ensure_tests_tables
if "ensure_social_anxiety_tests_definitions(db)" not in rcontent:
    rcontent = rcontent.replace("ensure_new_sexology_and_cognitive_tests_definitions(db)", "ensure_new_sexology_and_cognitive_tests_definitions(db)\n    ensure_social_anxiety_tests_definitions(db)")

with open('routes_tests.py', 'w', encoding='utf-8') as f:
    f.write(rcontent)

print("Patch successful!")
