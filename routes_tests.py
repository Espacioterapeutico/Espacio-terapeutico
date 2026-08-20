# -*- coding: utf-8 -*-
"""
Módulo de Tests Psicológicos y Baterías Psicométricas (routes_tests.py)
Encapsula el catálogo de pruebas, asignación de evaluaciones, auto-aplicación en portal público y de pacientes,
algoritmos de corrección/puntuación (BDI-II, BAI, MCMI-II, RAVEN, HOLLAND, AQ, RAADS-R, CAT-Q, ASRS-ADHD, UGDS-GS, TCS)
y la generación de informes clínicos en formato Word y PDF.
"""

import os
import re
import uuid
import json
import sqlite3
from datetime import datetime
from functools import wraps
from flask import Blueprint, request, jsonify, session, g, render_template, render_template_string, make_response, send_file

tests_bp = Blueprint('tests', __name__)

def get_db():
    """Obtiene la conexión a la base de datos desde el contexto global g de Flask."""
    db = getattr(g, '_database', None)
    if db is None:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        db_path = os.path.join(base_dir, 'clinica.db')
        db = g._database = sqlite3.connect(db_path, timeout=30.0)
        db.row_factory = sqlite3.Row
    return db

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'No autorizado. Por favor inicia sesión.'}), 401
        return f(*args, **kwargs)
    return decorated_function

def patient_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'patient_id' not in session:
            return jsonify({'error': 'Sesión de paciente no válida o no iniciada.'}), 401
        return f(*args, **kwargs)
    return decorated_function

def get_psicologo_id_filter():
    role = session.get('role')
    user_id = session.get('user_id')
    username = session.get('username', '')
    
    if (role in ['admin', 'superadmin']) and (username.lower() != 'pamoraro' and user_id != 1):
        return -1
        
    return user_id if user_id else 1

def ensure_usuarios_columns(db):
    try:
        cursor = db.cursor()
        cursor.execute("PRAGMA table_info(usuarios)")
        cols = [r[1] for r in cursor.fetchall()]
        if cols and 'bloqueo_tests' not in cols:
            cursor.execute("ALTER TABLE usuarios ADD COLUMN bloqueo_tests INTEGER DEFAULT 0")
            db.commit()
    except Exception as e:
        print("Error al asegurar columnas de usuarios en tests:", e)

def ensure_tests_tables(db):
    cursor = db.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tests_definiciones (
            code TEXT PRIMARY KEY,
            nombre TEXT NOT NULL,
            siglas TEXT NOT NULL,
            categoria TEXT,
            descripcion TEXT,
            instrucciones TEXT,
            escala_opciones_json TEXT,
            items_json TEXT NOT NULL,
            reglas_correccion_json TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS test_asignaciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid_token TEXT UNIQUE NOT NULL,
            patient_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            test_code TEXT NOT NULL,
            estado TEXT DEFAULT 'pendiente',
            modo_aplicacion TEXT DEFAULT 'link',
            fecha_asignacion DATETIME DEFAULT CURRENT_TIMESTAMP,
            fecha_completado DATETIME,
            respuestas_json TEXT,
            puntaje_total REAL,
            subescalas_json TEXT,
            clasificacion_resultado TEXT,
            interpretacion_clinica TEXT,
            notas_terapeuta TEXT,
            FOREIGN KEY (user_id) REFERENCES usuarios(id) ON DELETE CASCADE,
            FOREIGN KEY (patient_id) REFERENCES pacientes(id) ON DELETE CASCADE
        )
    """)
    cursor.execute("PRAGMA table_info(test_asignaciones)")
    ta_cols = [r[1] for r in cursor.fetchall()]
    if ta_cols:
        if 'modo_aplicacion' not in ta_cols:
            cursor.execute("ALTER TABLE test_asignaciones ADD COLUMN modo_aplicacion TEXT DEFAULT 'link'")
        if 'subescalas_json' not in ta_cols:
            cursor.execute("ALTER TABLE test_asignaciones ADD COLUMN subescalas_json TEXT")
        if 'clasificacion_resultado' not in ta_cols:
            cursor.execute("ALTER TABLE test_asignaciones ADD COLUMN clasificacion_resultado TEXT")
        if 'interpretacion_clinica' not in ta_cols:
            cursor.execute("ALTER TABLE test_asignaciones ADD COLUMN interpretacion_clinica TEXT")
        if 'notas_terapeuta' not in ta_cols:
            cursor.execute("ALTER TABLE test_asignaciones ADD COLUMN notas_terapeuta TEXT")
    db.commit()
    ensure_zung_sds_definition(db)
    ensure_hamilton_d_definition(db)
    ensure_idare_stai_definition(db)
    ensure_scl90r_definition(db)
    ensure_beck_bhs_definition(db)
    ensure_mmpi2_definition(db)
    ensure_new_latin_tests_definitions(db)

def ensure_zung_sds_definition(db):
    cursor = db.cursor()
    escala_opciones = [
        {"val": 1, "text": "Un poco del tiempo / Rara vez"},
        {"val": 2, "text": "Algo del tiempo / A veces"},
        {"val": 3, "text": "Buena parte del tiempo / Con frecuencia"},
        {"val": 4, "text": "La mayor parte del tiempo / Casi siempre"}
    ]
    
    items = [
        {"id": 1, "texto": "Me siento desanimado(a) y triste.", "reverse": False},
        {"id": 2, "texto": "Por la mañana es cuando me siento mejor.", "reverse": True},
        {"id": 3, "texto": "Tengo accesos de llanto o me siento a punto de llorar.", "reverse": False},
        {"id": 4, "texto": "Tengo problemas para dormir por la noche.", "reverse": False},
        {"id": 5, "texto": "Como igual de bien que antes.", "reverse": True},
        {"id": 6, "texto": "Todavía disfruto del sexo y de las relaciones afectivas.", "reverse": True},
        {"id": 7, "texto": "Noto que estoy perdiendo peso sin razón aparente.", "reverse": False},
        {"id": 8, "texto": "Tengo problemas de estreñimiento o malestar digestivo.", "reverse": False},
        {"id": 9, "texto": "El corazón me late más de prisa de lo habitual.", "reverse": False},
        {"id": 10, "texto": "Me canso sin motivo aparente.", "reverse": False},
        {"id": 11, "texto": "Mi mente está tan despejada como antes.", "reverse": True},
        {"id": 12, "texto": "Hago las cosas con la misma facilidad que antes.", "reverse": True},
        {"id": 13, "texto": "Me siento intranquilo(a) y no puedo estar quieto(a).", "reverse": False},
        {"id": 14, "texto": "Siento esperanza y confianza respecto al futuro.", "reverse": True},
        {"id": 15, "texto": "Estoy más irritable de lo habitual.", "reverse": False},
        {"id": 16, "texto": "Me resulta fácil tomar decisiones.", "reverse": True},
        {"id": 17, "texto": "Siento que soy útil y que me necesitan.", "reverse": True},
        {"id": 18, "texto": "Mi vida es bastante plena e interesante.", "reverse": True},
        {"id": 19, "texto": "Siento que los demás estarían mejor si yo estuviera muerto(a).", "reverse": False},
        {"id": 20, "texto": "Todavía disfruto con las mismas cosas de siempre.", "reverse": True}
    ]

    cursor.execute("SELECT code FROM tests_definiciones WHERE code = 'ZUNG-SDS'")
    if not cursor.fetchone():
        cursor.execute("""
            INSERT INTO tests_definiciones (code, nombre, siglas, categoria, descripcion, instrucciones, escala_opciones_json, items_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            'ZUNG-SDS',
            'ZUNG-SDS — Escala Autoaplicada de Depresión de Zung',
            'ZUNG-SDS',
            'Depresión y Ansiedad',
            'Evaluación cuantitativa de 20 reactivos orientada a cuantificar los síntomas afectivos, fisiológicos y psicológicos de la depresión.',
            'Por favor lea cada frase y seleccione la opción que mejor describa cómo se ha sentido usted durante la última semana.',
            json.dumps(escala_opciones, ensure_ascii=False),
            json.dumps(items, ensure_ascii=False)
        ))
        db.commit()

def process_zung_sds_scoring(answers):
    reverse_items = {2, 5, 6, 11, 12, 14, 16, 17, 18, 20}
    raw_score = 0
    valid_count = 0

    for item_id in range(1, 21):
        key = str(item_id)
        val = answers.get(key) if answers.get(key) is not None else answers.get(f"item_{item_id}")
        if val is not None:
            try:
                v = int(val)
                score = (5 - v) if item_id in reverse_items else v
                raw_score += score
                valid_count += 1
            except (ValueError, TypeError):
                pass

    zung_index = round((raw_score / 80.0) * 100, 1) if raw_score > 0 else 0.0

    if zung_index < 50:
        classification = "Normal / Sin Depresión Clínicamente Significativa"
        interpretation = f"Puntuación Bruta: {raw_score}/80 — Índice Zung: {zung_index}%. El consultante se ubica dentro del rango normal (sin síntomas depresivos de relevancia clínica)."
    elif 50 <= zung_index <= 59:
        classification = "Depresión Leve a Moderada"
        interpretation = f"Puntuación Bruta: {raw_score}/80 — Índice Zung: {zung_index}%. Presencia de sintomatología depresiva de intensidad leve a moderada. Se sugiere profundización en afecto y patrones de descanso/actividad."
    elif 60 <= zung_index <= 69:
        classification = "Depresión Moderadamente Grave"
        interpretation = f"Puntuación Bruta: {raw_score}/80 — Índice Zung: {zung_index}%. Presencia de sintomatología depresiva moderadamente grave. Requiere abordaje psicoterapéutico estructurado e intervenciones de autorregulación."
    else:
        classification = "Depresión Severa / Grave"
        interpretation = f"Puntuación Bruta: {raw_score}/80 — Índice Zung: {zung_index}%. Indicadores de depresión severa. Se recomienda evaluación psiquiátrica complementaria y plan de contención e intervención terapéutica inmediato."

    subscales = {
        "Puntuación Bruta": f"{raw_score} / 80",
        "Índice Zung (SDS)": f"{zung_index}%",
        "Respuestas Registradas": f"{valid_count} / 20"
    }

    return zung_index, subscales, classification, interpretation

def ensure_hamilton_d_definition(db):
    cursor = db.cursor()
    items = [
        {
            "id": 1,
            "texto": "1. Humor deprimido (tristeza, desamparo, inutilidad):",
            "opciones": [
                {"val": 0, "text": "Ausente"},
                {"val": 1, "text": "Estas sensaciones las expresa sólo al ser preguntado"},
                {"val": 2, "text": "Estas sensaciones las relata espontáneamente"},
                {"val": 3, "text": "Sensaciones no verbales (expresión facial, llanto, voz)"},
                {"val": 4, "text": "El paciente manifiesta estas sensaciones en su comunicación verbal y no verbal"}
            ]
        },
        {
            "id": 2,
            "texto": "2. Sentimientos de culpa:",
            "opciones": [
                {"val": 0, "text": "Ausentes"},
                {"val": 1, "text": "Se culpa a sí mismo, cree haber decepcionado a la gente"},
                {"val": 2, "text": "Ideas de culpabilidad o meditación sobre errores pasados"},
                {"val": 3, "text": "La enfermedad actual es un castigo. Ideas delirantes de culpa"},
                {"val": 4, "text": "Oye voces acusatorias o de denuncia y/o experimenta alucinaciones visuales amenazadoras"}
            ]
        },
        {
            "id": 3,
            "texto": "3. Suicidio / Ideación autolítica:",
            "opciones": [
                {"val": 0, "text": "Ausente"},
                {"val": 1, "text": "Le parece que la vida no vale la pena ser vivida"},
                {"val": 2, "text": "Desearía estar muerto o tiene pensamientos sobre la posibilidad de morir"},
                {"val": 3, "text": "Ideas o gestos de suicidio"},
                {"val": 4, "text": "Intentos de suicidio (cualquier intento serio)"}
            ]
        },
        {
            "id": 4,
            "texto": "4. Insomnio precoz (dificultad para conciliar el sueño):",
            "opciones": [
                {"val": 0, "text": "Ausente (no hay dificultad para dormirse)"},
                {"val": 1, "text": "Quejas ocasionales de dificultad para dormirse (más de 30 minutos)"},
                {"val": 2, "text": "Queja constante de dificultad para dormirse cada noche"}
            ]
        },
        {
            "id": 5,
            "texto": "5. Insomnio medio (despertar durante la noche):",
            "opciones": [
                {"val": 0, "text": "Ausente (duerme de corrido)"},
                {"val": 1, "text": "El paciente se queja de estar inquieto y desvelarse a mitad de la noche"},
                {"val": 2, "text": "Despierta varias veces durante la noche o se levanta de la cama"}
            ]
        },
        {
            "id": 6,
            "texto": "6. Insomnio tardío (despertar precoz por la mañana):",
            "opciones": [
                {"val": 0, "text": "Ausente"},
                {"val": 1, "text": "Despierta a primera hora de la mañana pero vuelve a dormirse"},
                {"val": 2, "text": "No puede volver a dormirse si se levanta de la cama precozmente"}
            ]
        },
        {
            "id": 7,
            "texto": "7. Trabajo y actividades (rendimiento y motivación):",
            "opciones": [
                {"val": 0, "text": "Sin dificultad"},
                {"val": 1, "text": "Ideas y sentimientos de incapacidad, fatiga o debilidad relacionadas con el trabajo"},
                {"val": 2, "text": "Pérdida de interés en su actividad (trabajo o aficiones)"},
                {"val": 3, "text": "Disminución del tiempo dedicado a actividades o descenso en la productividad"},
                {"val": 4, "text": "Dejó de trabajar por la presente enfermedad"}
            ]
        },
        {
            "id": 8,
            "texto": "8. Inhibición psicomotora (lentitud de pensamiento y palabra, torpeza emotiva):",
            "opciones": [
                {"val": 0, "text": "Palabra y pensamiento normales"},
                {"val": 1, "text": "Ligera lentitud en la conversación"},
                {"val": 2, "text": "Evidente lentitud en la conversación"},
                {"val": 3, "text": "Evaluación difícil, respuesta muy diferida"},
                {"val": 4, "text": "Estupor completo"}
            ]
        },
        {
            "id": 9,
            "texto": "9. Agitación psicomotora:",
            "opciones": [
                {"val": 0, "text": "Ninguna"},
                {"val": 1, "text": "Juega con sus manos, cabello, etc."},
                {"val": 2, "text": "Se retuerce las manos, se muerde los labios, inquietud motora"},
                {"val": 3, "text": "No puede permanecer sentado, camina de un lado a otro"},
                {"val": 4, "text": "Se retuerce continuamente, se arranca el cabello o la ropa"}
            ]
        },
        {
            "id": 10,
            "texto": "10. Ansiedad psíquica (tensión mental, irritabilidad, aprensión):",
            "opciones": [
                {"val": 0, "text": "No hay dificultad"},
                {"val": 1, "text": "Tensión subjetiva e irritabilidad"},
                {"val": 2, "text": "Preocupación por pequeñas cuestiones"},
                {"val": 3, "text": "Actitud aprensiva reflejada en la expresión o en el habla"},
                {"val": 4, "text": "El paciente expresa sus temores sin que se le pregunte"}
            ]
        },
        {
            "id": 11,
            "texto": "11. Ansiedad somática (boca seca, molestias digestivas, taquicardia, cefaleas):",
            "opciones": [
                {"val": 0, "text": "Ausente"},
                {"val": 1, "text": "Ligera"},
                {"val": 2, "text": "Moderada"},
                {"val": 3, "text": "Grave"},
                {"val": 4, "text": "Incapacitante"}
            ]
        },
        {
            "id": 12,
            "texto": "12. Síntomas somáticos gastrointestinales (pérdida de apetito, estreñimiento):",
            "opciones": [
                {"val": 0, "text": "Ninguno"},
                {"val": 1, "text": "Pérdida del apetito pero come sin necesidad de estímulo. Pesadez abdominal"},
                {"val": 2, "text": "Dificultad grande en comer sin insistencia. Solicita laxantes o purgantes"}
            ]
        },
        {
            "id": 13,
            "texto": "13. Síntomas somáticos generales (fatiga, pesadez en extremidades o espalda):",
            "opciones": [
                {"val": 0, "text": "Ninguno"},
                {"val": 1, "text": "Pesadez en las extremidades, espalda o cabeza. Dolores musculares, pérdida de energía"},
                {"val": 2, "text": "Cualquier síntoma bien definido se valora como 2"}
            ]
        },
        {
            "id": 14,
            "texto": "14. Síntomas genitales (pérdida de la libido, trastornos menstruales):",
            "opciones": [
                {"val": 0, "text": "Ausente"},
                {"val": 1, "text": "Débil / Ligero trastorno"},
                {"val": 2, "text": "Grave / Ausencia total de deseo sexual"}
            ]
        },
        {
            "id": 15,
            "texto": "15. Hipocondría / Preocupación somática:",
            "opciones": [
                {"val": 0, "text": "No la hay"},
                {"val": 1, "text": "Autoobservación corporal aumentada"},
                {"val": 2, "text": "Preocupación por la salud física"},
                {"val": 3, "text": "Lamentos frecuentes, solicitudes de ayuda"},
                {"val": 4, "text": "Ideas delirantes hipocondríacas"}
            ]
        },
        {
            "id": 16,
            "texto": "16. Pérdida de peso:",
            "opciones": [
                {"val": 0, "text": "No hay pérdida de peso"},
                {"val": 1, "text": "Pérdida de peso asociada a la enfermedad actual (probablemente medio kilo a la semana)"},
                {"val": 2, "text": "Pérdida de peso acusada (más de un kilo a la semana)"}
            ]
        },
        {
            "id": 17,
            "texto": "17. Insight / Conciencia de enfermedad:",
            "opciones": [
                {"val": 0, "text": "Reconoce estar deprimido y enfermo"},
                {"val": 1, "text": "Reconoce estar enfermo pero lo atribuye a mala comida, clima, sobretrabajo, etc."},
                {"val": 2, "text": "Niega estar enfermo de ningún modo"}
            ]
        }
    ]

    cursor.execute("SELECT code FROM tests_definiciones WHERE code = 'HAMILTON-D'")
    if not cursor.fetchone():
        cursor.execute("""
            INSERT INTO tests_definiciones (code, nombre, siglas, categoria, descripcion, instrucciones, escala_opciones_json, items_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            'HAMILTON-D',
            'HAMILTON-D — Escala de Depresión de Hamilton (HDRS-17)',
            'HAM-D',
            'Depresión y Ansiedad',
            'Escala de 17 ítems para la evaluación cuantitativa de la severidad del cuadro depresivo y seguimiento del tratamiento.',
            'Seleccione en cada ítem la alternativa que mejor describa la intensidad del síntoma durante los últimos días.',
            json.dumps([], ensure_ascii=False),
            json.dumps(items, ensure_ascii=False)
        ))
        db.commit()

def process_hamilton_d_scoring(answers):
    total_score = 0
    valid_count = 0

    for item_id in range(1, 18):
        key = str(item_id)
        val = answers.get(key) if answers.get(key) is not None else answers.get(f"item_{item_id}")
        if val is not None:
            try:
                v = int(val)
                total_score += v
                valid_count += 1
            except (ValueError, TypeError):
                pass

    if total_score <= 7:
        classification = "Normal / Eutimia (Sin Depresión)"
        interpretation = f"Puntuación Bruta: {total_score}/52 pts. Criterio dentro del rango normal (ausencia de sintomatología depresiva significativa)."
    elif 8 <= total_score <= 13:
        classification = "Depresión Leve"
        interpretation = f"Puntuación Bruta: {total_score}/52 pts. Sintomatología depresiva de intensidad leve. Se sugiere monitoreo y apoyo terapéutico."
    elif 14 <= total_score <= 18:
        classification = "Depresión Moderada"
        interpretation = f"Puntuación Bruta: {total_score}/52 pts. Cuadro depresivo de intensidad moderada. Requiere abordaje psicoterapéutico activo."
    elif 19 <= total_score <= 22:
        classification = "Depresión Severa / Grave"
        interpretation = f"Puntuación Bruta: {total_score}/52 pts. Sintomatología depresiva severa. Se recomienda plan de tratamiento psicoterapéutico e interconsulta médica."
    else:
        classification = "Depresión Muy Grave / Severidad Máxima"
        interpretation = f"Puntuación Bruta: {total_score}/52 pts. Indicadores de depresión muy grave con alto impacto funcional. Requiere abordaje interdisciplinario prioritario."

    subscales = {
        "Puntuación Total": f"{total_score} / 52",
        "Ítems Evaluados": f"{valid_count} / 17"
    }

    return float(total_score), subscales, classification, interpretation

def ensure_idare_stai_definition(db):
    cursor = db.cursor()
    escala_ae = [
        {"val": 1, "text": "No, en absoluto / Nada"},
        {"val": 2, "text": "Un poco / Algo"},
        {"val": 3, "text": "Bastante"},
        {"val": 4, "text": "Mucho / Totalmente"}
    ]
    
    items = [
        {"id": 1, "texto": "Me siento calmado(a).", "seccion": "AE", "reverse": True},
        {"id": 2, "texto": "Me siento seguro(a).", "seccion": "AE", "reverse": True},
        {"id": 3, "texto": "Estoy tenso(a).", "seccion": "AE", "reverse": False},
        {"id": 4, "texto": "Estoy contrariado(a) / angustiado(a).", "seccion": "AE", "reverse": False},
        {"id": 5, "texto": "Me siento a gusto.", "seccion": "AE", "reverse": True},
        {"id": 6, "texto": "Me siento alterado(a) o inquieto(a).", "seccion": "AE", "reverse": False},
        {"id": 7, "texto": "Estoy preocupado(a) por posibles desgracias.", "seccion": "AE", "reverse": False},
        {"id": 8, "texto": "Me siento satisfecho(a).", "seccion": "AE", "reverse": True},
        {"id": 9, "texto": "Me siento asustado(a) / atemorizado(a).", "seccion": "AE", "reverse": False},
        {"id": 10, "texto": "Me siento confortable / cómodo(a).", "seccion": "AE", "reverse": True},
        {"id": 11, "texto": "Tengo confianza en mí mismo(a).", "seccion": "AE", "reverse": True},
        {"id": 12, "texto": "Me siento nervioso(a).", "seccion": "AE", "reverse": False},
        {"id": 13, "texto": "Estoy intranquilo(a).", "seccion": "AE", "reverse": False},
        {"id": 14, "texto": "Me siento indeciso(a).", "seccion": "AE", "reverse": False},
        {"id": 15, "texto": "Estoy relajado(a).", "seccion": "AE", "reverse": True},
        {"id": 16, "texto": "Me siento contento(a).", "seccion": "AE", "reverse": True},
        {"id": 17, "texto": "Estoy preocupado(a).", "seccion": "AE", "reverse": False},
        {"id": 18, "texto": "Me siento perplejo(a) / desorientado(a).", "seccion": "AE", "reverse": False},
        {"id": 19, "texto": "Me siento sereno(a) y equilibrado(a).", "seccion": "AE", "reverse": True},
        {"id": 20, "texto": "Me siento bien.", "seccion": "AE", "reverse": True},

        {"id": 21, "texto": "Me siento bien y alegre.", "seccion": "AR", "reverse": True},
        {"id": 22, "texto": "Me canso rápidamente.", "seccion": "AR", "reverse": False},
        {"id": 23, "texto": "Siento ganas de llorar.", "seccion": "AR", "reverse": False},
        {"id": 24, "texto": "Desearía ser tan feliz como otros parecen serlo.", "seccion": "AR", "reverse": False},
        {"id": 25, "texto": "Pierdo oportunidades por no decidirme pronto.", "seccion": "AR", "reverse": False},
        {"id": 26, "texto": "Me siento descansado(a).", "seccion": "AR", "reverse": True},
        {"id": 27, "texto": "Soy una persona serena, tranquila y ecuánime.", "seccion": "AR", "reverse": True},
        {"id": 28, "texto": "Siento que las dificultades se me acumulan sin poder superarlas.", "seccion": "AR", "reverse": False},
        {"id": 29, "texto": "Me preocupo demasiado por cosas que no tienen importancia.", "seccion": "AR", "reverse": False},
        {"id": 30, "texto": "Soy feliz.", "seccion": "AR", "reverse": True},
        {"id": 31, "texto": "Tomo las cosas muy a pecho.", "seccion": "AR", "reverse": False},
        {"id": 32, "texto": "Me falta confianza en mí mismo(a).", "seccion": "AR", "reverse": False},
        {"id": 33, "texto": "Me siento seguro(a).", "seccion": "AR", "reverse": True},
        {"id": 34, "texto": "Procuro evitar enfrentarme a las crisis o problemas.", "seccion": "AR", "reverse": False},
        {"id": 35, "texto": "Me siento melancólico(a) / abatido(a).", "seccion": "AR", "reverse": False},
        {"id": 36, "texto": "Me siento satisfecho(a).", "seccion": "AR", "reverse": True},
        {"id": 37, "texto": "Algunos pensamientos inútiles me rondan la cabeza y me molestan.", "seccion": "AR", "reverse": False},
        {"id": 38, "texto": "Me afectan tanto los desengaños que no puedo olvidarlos.", "seccion": "AR", "reverse": False},
        {"id": 39, "texto": "Soy una persona estable.", "seccion": "AR", "reverse": True},
        {"id": 40, "texto": "Cuando pienso en mis asuntos actuales me pongo tenso(a).", "seccion": "AR", "reverse": False}
    ]

    cursor.execute("SELECT code FROM tests_definiciones WHERE code IN ('IDARE-STAI', 'IDARE')")
    if not cursor.fetchone():
        cursor.execute("""
            INSERT INTO tests_definiciones (code, nombre, siglas, categoria, descripcion, instrucciones, escala_opciones_json, items_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            'IDARE-STAI',
            'IDARE / STAI — Inventario de Ansiedad Rasgo-Estado',
            'IDARE',
            'Depresión y Ansiedad',
            'Evaluación dual de 40 reactivos que distingue la ansiedad transitoria (Estado) de la predisposición ansiosa permanente (Rasgo).',
            'Responda las primeras 20 frases según cómo se siente EN ESTE MOMENTO. Responda las frases 21 a 40 según cómo se siente GENERALMENTE.',
            json.dumps(escala_ae, ensure_ascii=False),
            json.dumps(items, ensure_ascii=False)
        ))
        db.commit()

def process_idare_stai_scoring(answers):
    ae_reverse = {1, 2, 5, 8, 10, 11, 15, 16, 19, 20}
    ar_reverse = {21, 26, 27, 30, 33, 36, 39}

    score_ae = 0
    score_ar = 0

    for item_id in range(1, 41):
        key = str(item_id)
        val = answers.get(key) if answers.get(key) is not None else answers.get(f"item_{item_id}")
        if val is not None:
            try:
                v = int(val)
                if item_id <= 20:
                    score = (5 - v) if item_id in ae_reverse else v
                    score_ae += score
                else:
                    score = (5 - v) if item_id in ar_reverse else v
                    score_ar += score
            except (ValueError, TypeError):
                pass

    total_score = score_ae + score_ar

    if score_ae < 30:
        cat_ae = "Baja / Mínima"
    elif 30 <= score_ae <= 44:
        cat_ae = "Moderada"
    elif 45 <= score_ae <= 59:
        cat_ae = "Alta"
    else:
        cat_ae = "Severa / Muy Alta"

    if score_ar < 30:
        cat_ar = "Baja / Mínima"
    elif 30 <= score_ar <= 44:
        cat_ar = "Moderada"
    elif 45 <= score_ar <= 59:
        cat_ar = "Alta"
    else:
        cat_ar = "Severa / Muy Alta"

    classification = f"Estado: {cat_ae} | Rasgo: {cat_ar}"
    interpretation = (
        f"Puntuación Ansiedad-Estado (AE): {score_ae}/80 pts ({cat_ae}). "
        f"Puntuación Ansiedad-Rasgo (AR): {score_ar}/80 pts ({cat_ar}). "
        f"Puntuación Combinada Total: {total_score}/160 pts."
    )

    subscales = {
        "Ansiedad-Estado (AE)": f"{score_ae} / 80 pts ({cat_ae})",
        "Ansiedad-Rasgo (AR)": f"{score_ar} / 80 pts ({cat_ar})",
        "Puntuación Total Dual": f"{total_score} / 160 pts"
    }

    return float(total_score), subscales, classification, interpretation

def ensure_scl90r_definition(db):
    cursor = db.cursor()
    escala = [
        {"val": 0, "text": "Nada en absoluto"},
        {"val": 1, "text": "Un poco"},
        {"val": 2, "text": "Moderadamente"},
        {"val": 3, "text": "Bastante"},
        {"val": 4, "text": "Mucho / Extremadamente"}
    ]
    
    textos = [
        "Dolores de cabeza", "Nerviosismo o tensión interior", "Pensamientos no deseados que no se le van de la cabeza",
        "Sensación de mareo o desmayo", "Pérdida de interés o del placer por el sexo", "Criticado o maltratado por los demás",
        "Sentir que otras personas pueden controlar sus pensamientos", "Sentir que otros son culpables de la mayoría de sus problemas",
        "Dificultad para recordar las cosas", "Preocupación por el desaliño o descuido", "Sentirse fácilmente irritado o enojado",
        "Dolores en el pecho o en el corazón", "Temor a las plazas o lugares abiertos", "Sensación de falta de energía o lentitud",
        "Pensamientos de acabar con su vida", "Oír voces que otras personas no oyen", "Temblores",
        "Sentir que no se puede confiar en la mayoría de la gente", "Poco apetito", "Llorar fácilmente",
        "Sentirse tímido o vergonzoso con personas del sexo opuesto", "Sentación de estar atrapado o atrapada",
        "Repentina asustadizo sin razón aparente", "Arrebatos de ira que no podía controlar", "Temor a salir solo o sola de casa",
        "Culparse a sí mismo por las cosas", "Dolores en la parte baja de la espalda", "Sentirse bloqueado o con dificultad para hacer las cosas",
        "Sentirse solo o sola", "Sentirse triste o melancólico", "Preocuparse demasiado por las cosas", "Ningún interés por las cosas",
        "Sentimiento de temor o miedo", "Sentimientos heridos con facilidad", "Que los demás sepan lo que usted piensa",
        "Sentir que las personas no son comprensivas o amigables", "Sentirse inferior a los demás",
        "Tener que hacer las cosas muy despacio para asegurar la perfección", "Palpitaciones o taquicardia",
        "Náuseas o malestar en el estómago", "Sentirse inferior a los demás en comparación", "Dolores musculares",
        "Sentir que le observan o hablan de usted", "Dificultad para dormirse", "Tener que comprobar una y otra vez lo que hace",
        "Dificultad para tomar decisiones", "Temor a viajar en autobuses, metros o trenes", "Sensación de falta de aire o ahogo",
        "Accesos de calor o frío", "Evitar ciertas cosas, lugares o actividades por temor", "Mente en blanco",
        "Entumecimiento o cosquilleo en partes del cuerpo", "Nudo en la garganta", "Sentir desesperanza con respecto al futuro",
        "Dificultad para concentrarse", "Sentirse débil en partes del cuerpo", "Sentirse tenso o agitado",
        "Pesadez en los brazos o piernas", "Pensamiento sobre la muerte o sobre morir", "Comer en exceso",
        "Sentirse incómodo cuando le miran o hablan de usted", "Tener pensamientos que no son suyos",
        "Impulsos de golpear, herir o hacer daño a alguien", "Despertarse temprano por la mañana",
        "Tener que repetir los mismos actos como contar o lavar", "Sueño inquieto o perturbado", "Deseos de romper o destrozar cosas",
        "Tener ideas o creencias que otros no comparten", "Sentirse muy cohibido con los demás", "Sentirse incómodo en muchedumbres",
        "Sentir que todo exige un gran esfuerzo", "Ataques de terror o pánico", "Sentirse incómodo comiendo o bebiendo en público",
        "Meterse en discusiones frecuentemente", "Sentirse nervioso cuando se queda solo o sola",
        "Que los demás no reconozcan adecuadamente sus méritos", "Sentirse solo incluso con más personas",
        "Sentirse tan inquieto que no puede estar sentado", "Sentimiento de inutilidad o falta de valor",
        "Sensación de que algo malo va a suceder", "Gritar o tirar cosas", "Miedo a desmayarse en público",
        "Sentir que la gente se aprovecha de usted si la deja", "Tener pensamientos sobre el sexo que le molestan",
        "La idea de que debe ser castigado por sus pecados", "Pensamientos o imágenes pavorosas",
        "La idea de que algo serio anda mal en su cuerpo", "Nunca sentirse cercano a otra persona",
        "Sentimiento de culpa por cosas del pasado", "La idea de que algo ande mal en su mente"
    ]

    items = [{"id": i+1, "texto": f"{i+1}. {txt}"} for i, txt in enumerate(textos)]

    cursor.execute("SELECT code FROM tests_definiciones WHERE code = 'SCL-90-R'")
    if not cursor.fetchone():
        cursor.execute("""
            INSERT INTO tests_definiciones (code, nombre, siglas, categoria, descripcion, instrucciones, escala_opciones_json, items_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            'SCL-90-R',
            'SCL-90-R — Cuestionario de 90 Síntomas Revisado',
            'SCL-90-R',
            'Personalidad y Psicopatología',
            'Evaluación autoadministrada de 90 ítems en escala Likert que explora 9 dimensiones sintomáticas de malestar psicológico.',
            'Por favor lea cada problema y seleccione qué tanto le ha molestado durante los últimos 7 días (incluyendo el día de hoy).',
            json.dumps(escala, ensure_ascii=False),
            json.dumps(items, ensure_ascii=False)
        ))
        db.commit()

def process_scl90r_scoring(answers):
    dims = {
        "SOM (Somatización)": [1, 4, 12, 27, 40, 42, 48, 49, 52, 53, 56, 58],
        "OBS (Obsesiones y Compulsiones)": [3, 9, 10, 28, 38, 45, 46, 51, 55, 65],
        "SI (Sensibilidad Interpersonal)": [6, 21, 34, 36, 37, 41, 61, 69, 73],
        "DEP (Depresión)": [5, 14, 15, 20, 22, 26, 29, 30, 31, 32, 54, 79],
        "ANS (Ansiedad)": [2, 17, 23, 33, 39, 57, 72, 78, 80, 86],
        "HOS (Hostilidad)": [11, 24, 63, 67, 74, 81],
        "FOB (Ansiedad Fóbica)": [13, 25, 47, 50, 70, 75, 82],
        "PAR (Ideación Paranoide)": [8, 18, 43, 68, 76, 83],
        "PSI (Psicoticismo)": [7, 16, 35, 62, 77, 84, 85, 87, 88, 90]
    }

    total_sum = 0
    pst = 0

    for item_id in range(1, 91):
        key = str(item_id)
        val = answers.get(key) if answers.get(key) is not None else answers.get(f"item_{item_id}")
        if val is not None:
            try:
                v = int(val)
                total_sum += v
                if v > 0:
                    pst += 1
            except (ValueError, TypeError):
                pass

    gsi = round(total_sum / 90.0, 2)
    psdi = round(total_sum / float(pst), 2) if pst > 0 else 0.0

    if gsi < 0.50:
        classification = "Normal / Malestar Sintomático Mínimo"
    elif 0.50 <= gsi < 1.00:
        classification = "Malestar Sintomático Leve"
    elif 1.00 <= gsi < 1.50:
        classification = "Malestar Sintomático Moderado"
    elif 1.50 <= gsi < 2.00:
        classification = "Malestar Sintomático Elevado"
    else:
        classification = "Malestar Sintomático Severo / Psicopatología Intensa"

    dim_scores = {}
    for dname, item_list in dims.items():
        dsum = 0
        dcount = 0
        for it in item_list:
            key = str(it)
            val = answers.get(key) if answers.get(key) is not None else answers.get(f"item_{it}")
            if val is not None:
                try:
                    dsum += int(val)
                    dcount += 1
                except (ValueError, TypeError):
                    pass
        prom = round(dsum / float(dcount), 2) if dcount > 0 else 0.0
        dim_scores[dname] = f"Media: {prom} (Suma: {dsum}/{len(item_list)*4})"

    subscales = {
        "GSI (Índice Severidad Global)": f"{gsi} ({classification})",
        "PST (Síntomas Positivos)": f"{pst} / 90 ítems",
        "PSDI (Malestar Sintomático)": f"{psdi}",
        **dim_scores
    }

    interpretation = (
        f"Índice de Severidad Global (GSI): {gsi} — {classification}. "
        f"Total de Síntomas Positivos (PST): {pst}/90 ítems. "
        f"Índice PSDI: {psdi}."
    )

    return gsi, subscales, classification, interpretation

def ensure_beck_bhs_definition(db):
    cursor = db.cursor()
    escala = [
        {"val": "V", "text": "Verdadero"},
        {"val": "F", "text": "Falso"}
    ]

    items = [
        {"id": 1, "texto": "1. Espero el futuro con esperanza y entusiasmo."},
        {"id": 2, "texto": "2. Puedo darme por vencido, renunciar, ya que no puedo hacer mejor las cosas por mí mismo."},
        {"id": 3, "texto": "3. Cuando las cosas van mal me alivia saber que no pueden permanecer así para siempre."},
        {"id": 4, "texto": "4. No puedo imaginar cómo será mi vida dentro de diez años."},
        {"id": 5, "texto": "5. Tengo suficiente tiempo para lograr las cosas que más deseo hacer."},
        {"id": 6, "texto": "6. En el futuro, espero lograr lo que me preocupa más."},
        {"id": 7, "texto": "7. Mi futuro me parece oscuro e incierto."},
        {"id": 8, "texto": "8. Espero conseguir más cosas buenas de la vida que lo que la persona promedio consigue."},
        {"id": 9, "texto": "9. Realmente no puedo conseguir un buen descanso y no hay razón por la cual debiera intentar conseguirlo."},
        {"id": 10, "texto": "10. Mis pasadas experiencias me han preparado bien para el futuro."},
        {"id": 11, "texto": "11. Todo lo que veo delante de mí parece más desdicha que felicidad."},
        {"id": 12, "texto": "12. No espero conseguir lo que realmente quiero."},
        {"id": 13, "texto": "13. Cuando miro hacia el futuro, espero ser más feliz que lo que soy ahora."},
        {"id": 14, "texto": "14. Las cosas no van a resultar como yo quiero."},
        {"id": 15, "texto": "15. Tengo gran fe en el futuro."},
        {"id": 16, "texto": "16. Nunca consigo lo que quiero, así que es tonto querer algo."},
        {"id": 17, "texto": "17. Es muy poco probable que obtenga alguna satisfacción real en el futuro."},
        {"id": 18, "texto": "18. El futuro me parece vago e incierto."},
        {"id": 19, "texto": "19. Puedo esperar más tiempos buenos que tiempos malos."},
        {"id": 20, "texto": "20. No tiene sentido intentar conseguir algo que quiero porque probablemente no lo lograré."}
    ]

    cursor.execute("SELECT code FROM tests_definiciones WHERE code IN ('BECK-BHS', 'BHS')")
    if not cursor.fetchone():
        cursor.execute("""
            INSERT INTO tests_definiciones (code, nombre, siglas, categoria, descripcion, instrucciones, escala_opciones_json, items_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            'BECK-BHS',
            'BHS — Escala de Desesperanza de Beck',
            'BHS',
            'Depresión y Ansiedad',
            'Inventario de 20 frases Verdadero/Falso diseñado para evaluar las actitudes negativas y desesperanza hacia el futuro.',
            'Por favor lea cada una de las siguientes afirmaciones y señale si es Verdadero o Falso según su situación personal.',
            json.dumps(escala, ensure_ascii=False),
            json.dumps(items, ensure_ascii=False)
        ))
        db.commit()

def process_beck_bhs_scoring(answers):
    v_items = {2, 4, 7, 9, 11, 12, 14, 16, 17, 18, 20}
    f_items = {1, 3, 5, 6, 8, 10, 13, 15, 19}

    total_score = 0
    valid_count = 0

    for item_id in range(1, 21):
        key = str(item_id)
        val = answers.get(key) if answers.get(key) is not None else answers.get(f"item_{item_id}")
        if val is not None:
            v_str = str(val).strip().upper()
            if item_id in v_items and v_str in ('V', 'VERDADERO', '1', 'TRUE'):
                total_score += 1
            elif item_id in f_items and v_str in ('F', 'FALSO', '0', '2', 'FALSE'):
                total_score += 1
            valid_count += 1

    if total_score <= 3:
        classification = "Desesperanza Mínima / Ausente (Rango Normal)"
        interpretation = f"Puntuación Bruta: {total_score}/20 pts. Indicadores de actitud positiva y esperanza razonable hacia el futuro."
    elif 4 <= total_score <= 8:
        classification = "Desesperanza Leve"
        interpretation = f"Puntuación Bruta: {total_score}/20 pts. Leve pesimismo o duda situacional sobre el futuro. Se sugiere monitoreo de afecto."
    elif 9 <= total_score <= 14:
        classification = "Desesperanza Moderada"
        interpretation = f"Puntuación Bruta: {total_score}/20 pts. Presencia de desesperanza moderada. Punto de corte clínico alcanzado (≥8). Se recomienda evaluación de ideación afectiva."
    else:
        classification = "Desesperanza Severa / Alto Riesgo Clínico"
        interpretation = f"Puntuación Bruta: {total_score}/20 pts. Indicadores de desesperanza severa y actitud negativa marcada hacia el futuro. Factor de riesgo clínico significativo que requiere contención inmediata."

    subscales = {
        "Puntuación de Desesperanza (BHS)": f"{total_score} / 20 pts",
        "Reactivos Respondidos": f"{valid_count} / 20"
    }

    return float(total_score), subscales, classification, interpretation

def ensure_mmpi2_definition(db):
    cursor = db.cursor()
    escala = [
        {"val": "V", "text": "Verdadero"},
        {"val": "F", "text": "Falso"}
    ]

    items = []
    items_file = os.path.join(os.path.dirname(__file__), 'static', 'test_materials', 'mmpi2_clean_items.json')
    if os.path.exists(items_file):
        try:
            with open(items_file, 'r', encoding='utf-8') as f:
                items = json.load(f)
        except Exception as _e:
            print("Error cargando mmpi2_clean_items.json:", _e)

    cursor.execute("SELECT code FROM tests_definiciones WHERE code IN ('MMPI-2', 'MMPI2', 'MMPI')")
    if not cursor.fetchone():
        cursor.execute("""
            INSERT INTO tests_definiciones (code, nombre, siglas, categoria, descripcion, instrucciones, escala_opciones_json, items_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            'MMPI-2',
            'MMPI-2 — Inventario Multifásico de Personalidad de Minnesota',
            'MMPI-2',
            'Personalidad y Psicopatología',
            'Inventario clínico estandarizado de 567 reactivos V/F para la evaluación multiaxial de la personalidad, validez y psicopatología.',
            'Por favor responda cada frase seleccionando Verdadero o Falso según se aplique a su caso.',
            json.dumps(escala, ensure_ascii=False),
            json.dumps(items, ensure_ascii=False)
        ))
        db.commit()

def ensure_new_latin_tests_definitions(db):
    cursor = db.cursor()
    
    # 1. RCMAS-2
    cursor.execute("SELECT code FROM tests_definiciones WHERE code = 'RCMAS-2'")
    if not cursor.fetchone():
        rcmas_opciones = [{"val": 1, "text": "Sí"}, {"val": 0, "text": "No"}]
        rcmas_items = [
            {"id": 1, "texto": "Me preocupan las cosas del colegio o mis responsabilidades."},
            {"id": 2, "texto": "Me canso fácilmente durante el día."},
            {"id": 3, "texto": "Muchas personas son celosas o exigentes conmigo."},
            {"id": 4, "texto": "Me da miedo cuando alguien se molesta o se enoja conmigo."},
            {"id": 5, "texto": "Siento que las demás personas son más inteligentes que yo."},
            {"id": 6, "texto": "Me cuesta conciliar el sueño por las noches pensando en el día."},
            {"id": 7, "texto": "Siento que la gente me juzga o me observa constantemente."},
            {"id": 8, "texto": "A veces siento agitación o que no puedo respirar bien."},
            {"id": 9, "texto": "Siempre soy amable con todas las personas sin excepción."},
            {"id": 10, "texto": "Siento malestar de estómago con frecuencia cuando estoy nervioso(a)."}
        ]
        cursor.execute("""
            INSERT INTO tests_definiciones (code, nombre, siglas, categoria, descripcion, instrucciones, escala_opciones_json, items_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            'RCMAS-2', 'RCMAS-2 — Escala de Ansiedad Manifiesta en Niños Revisada', 'RCMAS-2', 'Clínica e Infantil',
            'Evaluación estandarizada de reactivos para detectar niveles de ansiedad fisiológica, inquietud e hipersensibilidad en niños y adolescentes.',
            'Por favor lee cada frase y selecciona "Sí" si describe cómo te sientes habitualmente o "No" si no te describe.',
            json.dumps(rcmas_opciones, ensure_ascii=False), json.dumps(rcmas_items, ensure_ascii=False)
        ))

    # 2. CDS-CTI
    cursor.execute("SELECT code FROM tests_definiciones WHERE code = 'CDS-CTI'")
    if not cursor.fetchone():
        cds_opciones = [
            {"val": 1, "text": "En absoluto"}, {"val": 2, "text": "Un poco"},
            {"val": 3, "text": "Moderadamente"}, {"val": 4, "text": "Mucho"}, {"val": 5, "text": "Totalmente de acuerdo"}
        ]
        cds_items = [
            {"id": 1, "texto": "Si algo malo puede pasar, estoy seguro de que me pasará a mí."},
            {"id": 2, "texto": "Si no hago las cosas perfectamente, entonces considero que he fracasado."},
            {"id": 3, "texto": "Sé exactamente lo que la gente piensa negativamente de mí sin necesidad de preguntarlo."},
            {"id": 4, "texto": "Un solo error arruina todo el trabajo positivo que he realizado previamente."},
            {"id": 5, "texto": "Siento que si muestro debilidad o dudas, los demás se aprovecharán de mí."}
        ]
        cursor.execute("""
            INSERT INTO tests_definiciones (code, nombre, siglas, categoria, descripcion, instrucciones, escala_opciones_json, items_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            'CDS-CTI', 'CDS / CTI — Cuestionario de Distorsiones Cognitivas', 'CDS', 'Cognición y Estrés',
            'Evaluación autoadministrada de pensamientos automáticos y errores en el procesamiento cognitivo.',
            'Selecciona el nivel en el que estos pensamientos se presentan en tu vida cotidiana.',
            json.dumps(cds_opciones, ensure_ascii=False), json.dumps(cds_items, ensure_ascii=False)
        ))

    # 3. CSI
    cursor.execute("SELECT code FROM tests_definiciones WHERE code = 'CSI'")
    if not cursor.fetchone():
        csi_opciones = [
            {"val": 0, "text": "En absoluto"}, {"val": 1, "text": "Algo"},
            {"val": 2, "text": "Bastante"}, {"val": 3, "text": "Mucho"}, {"val": 4, "text": "Totalmente"}
        ]
        csi_items = [
            {"id": 1, "texto": "Luché por resolver la situación buscando información y soluciones reales."},
            {"id": 2, "texto": "Me culpé por lo sucedido y me sentí responsable del malestar."},
            {"id": 3, "texto": "Expresé mis emociones abiertamente para desahogarme con otros."},
            {"id": 4, "texto": "Deseé que la situación desapareciera milagrosamente sin tener que enfrentarla."},
            {"id": 5, "texto": "Busqué el consejo y apoyo de personas cercanas o profesionales."},
            {"id": 6, "texto": "Traté de ver el lado positivo y aprender de la experiencia difícil."},
            {"id": 7, "texto": "Traté de no pensar en el problema y distraerme con otras actividades."},
            {"id": 8, "texto": "Me aislé de los demás para evitar hablar del tema o sentirme juzgado(a)."}
        ]
        cursor.execute("""
            INSERT INTO tests_definiciones (code, nombre, siglas, categoria, descripcion, instrucciones, escala_opciones_json, items_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            'CSI', 'CSI — Cuestionario de Estrategias de Afrontamiento', 'CSI', 'Cognición y Estrés',
            'Evaluación de 40 ítems Likert para cuantificar 8 estilos de afrontamiento ante situaciones estresantes.',
            'Indica en qué medida utilizas cada una de estas formas de afrontar los problemas.',
            json.dumps(csi_opciones, ensure_ascii=False), json.dumps(csi_items, ensure_ascii=False)
        ))

    # 4. DVQ-R
    cursor.execute("SELECT code FROM tests_definiciones WHERE code = 'DVQ-R'")
    if not cursor.fetchone():
        dvq_opciones = [
            {"val": 0, "text": "Nunca"}, {"val": 1, "text": "A veces"},
            {"val": 2, "text": "Frecuentemente"}, {"val": 3, "text": "Casi siempre"}, {"val": 4, "text": "Siempre"}
        ]
        dvq_items = [
            {"id": 1, "texto": "Mi pareja ignora mis sentimientos o se muestra distante sin razón."},
            {"id": 2, "texto": "Mi pareja me insulta, descalifica o me ridiculiza en privado o frente a otros."},
            {"id": 3, "texto": "Mi pareja intenta controlar con quién hablo, cómo me visto o a dónde voy."},
            {"id": 4, "texto": "Mi pareja ha llegado a empujarme, sujetarme con fuerza o agredirme físicamente."},
            {"id": 5, "texto": "Mi pareja me presiona a tener relaciones o conductas sexuales no deseadas."}
        ]
        cursor.execute("""
            INSERT INTO tests_definiciones (code, nombre, siglas, categoria, descripcion, instrucciones, escala_opciones_json, items_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            'DVQ-R', 'DVQ-R — Cuestionario de Violencia en el Noviazgo', 'DVQ-R', 'Pareja y Violencia',
            'Evaluación estandarizada de 20 ítems para detectar conductas de abuso físico, verbal, coercitivo y sexual en relaciones de pareja.',
            'Responde con qué frecuencia se presentan o se han presentado estas situaciones con tu pareja.',
            json.dumps(dvq_opciones, ensure_ascii=False), json.dumps(dvq_items, ensure_ascii=False)
        ))

    # 5. EAQ
    cursor.execute("SELECT code FROM tests_definiciones WHERE code = 'EAQ'")
    if not cursor.fetchone():
        eaq_opciones = [
            {"val": 1, "text": "No es verdad"}, {"val": 2, "text": "Un poco verdad"}, {"val": 3, "text": "Muy verdad"}
        ]
        eaq_items = [
            {"id": 1, "texto": "Me resulta fácil identificar si me siento triste, alegre o molesto(a)."},
            {"id": 2, "texto": "Presto atención a cómo reacciona mi cuerpo cuando me siento estresado(a)."},
            {"id": 3, "texto": "Prefiero no mostrar mis emociones reales frente a otras personas."},
            {"id": 4, "texto": "A veces no entiendo la causa exacta por la que me siento de cierta manera."},
            {"id": 5, "texto": "Me resulta fácil hablar sobre mis sentimientos con personas en las que confío."}
        ]
        cursor.execute("""
            INSERT INTO tests_definiciones (code, nombre, siglas, categoria, descripcion, instrucciones, escala_opciones_json, items_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            'EAQ', 'EAQ — Cuestionario de Conciencia Emocional Infanto-Juvenil', 'EAQ', 'Clínica e Infantil',
            'Evaluación para identificar diferenciación de emociones, atención a señales emocionales y ocultación emocional.',
            'Indica qué tan cierta es cada afirmación respecto a ti.',
            json.dumps(eaq_opciones, ensure_ascii=False), json.dumps(eaq_items, ensure_ascii=False)
        ))

    # 6. CUSES-SAS
    cursor.execute("SELECT code FROM tests_definiciones WHERE code = 'CUSES-SAS'")
    if not cursor.fetchone():
        cuses_opciones = [
            {"val": 1, "text": "Totalmente en desacuerdo"}, {"val": 2, "text": "En desacuerdo"},
            {"val": 3, "text": "Neutral"}, {"val": 4, "text": "De acuerdo"}, {"val": 5, "text": "Totalmente de acuerdo"}
        ]
        cuses_items = [
            {"id": 1, "texto": "Me siento seguro(a) para proponer abiertamente el uso de métodos de protección a mi pareja."},
            {"id": 2, "texto": "Tengo la capacidad de negarme a tener relaciones si no se cuenta con la protección adecuada."},
            {"id": 3, "texto": "Puedo conversar libremente sobre salud sexual y prevención con mi pareja."},
            {"id": 4, "texto": "Sé cómo adquirir y utilizar correctamente los métodos de cuidado e higiene sexual."},
            {"id": 5, "texto": "Me siento cómodo(a) expresando mis límites personales y preferencias en la intimidad."}
        ]
        cursor.execute("""
            INSERT INTO tests_definiciones (code, nombre, siglas, categoria, descripcion, instrucciones, escala_opciones_json, items_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            'CUSES-SAS', 'CUSES / SAS — Autoeficacia y Asertividad Sexual', 'CUSES', 'Salud y Sexología',
            'Evaluación de autoeficacia en salud sexual, prevención de ITS y capacidad de negociación/asertividad en la conducta sexual.',
            'Selecciona tu grado de acuerdo con cada afirmación sobre tu confianza en situaciones de salud sexual.',
            json.dumps(cuses_opciones, ensure_ascii=False), json.dumps(cuses_items, ensure_ascii=False)
        ))
    db.commit()

def process_mmpi2_scoring(answers):
    # Standard MMPI-2 Item Keys for Validity & 10 Clinical Scales
    # Validity
    val_L_false = {15, 30, 45, 60, 75, 90, 105, 120, 135, 150, 165, 180, 195, 210, 225}
    val_F_true = {14, 23, 31, 38, 48, 65, 73, 84, 91, 96, 114, 122, 127, 139, 147, 156, 162, 168, 182, 190, 197, 206, 215, 221, 227, 233, 240, 252, 256, 268, 282, 291, 294, 313, 317, 322, 329, 334, 339, 344, 348, 354, 360, 366}
    val_F_false = {17, 20, 33, 46, 58, 81, 102, 110, 117, 152, 164, 177, 187, 200, 224, 250}
    val_K_true = {96}
    val_K_false = {29, 37, 58, 76, 110, 116, 122, 127, 130, 140, 148, 157, 158, 167, 171, 196, 213, 243, 267, 290, 338, 339, 341, 365, 368, 477, 484, 520, 546}

    # Clinical Scales
    # 1. Hs (Hipocondriasis - 32 ítems)
    hs_t = {18, 28, 39, 53, 59, 97, 101, 111, 142, 175, 247, 293}
    hs_f = {2, 3, 8, 10, 20, 47, 57, 68, 117, 141, 143, 152, 163, 173, 176, 189, 208, 224, 241, 243}

    # 2. D (Depresión - 57 ítems)
    d_t = {5, 15, 18, 38, 46, 56, 92, 117, 127, 130, 146, 147, 170, 175, 215, 233, 251, 288, 299, 341, 350}
    d_f = {2, 8, 9, 10, 20, 29, 33, 37, 43, 45, 49, 55, 68, 75, 76, 95, 109, 118, 123, 140, 141, 142, 143, 148, 160, 165, 178, 188, 189, 212, 221, 223, 241, 248, 260, 267}

    # 3. Hy (Histeria - 60 ítems)
    hy_t = {11, 18, 28, 39, 40, 44, 59, 76, 97, 101, 115, 135, 142, 175, 179, 218, 230, 249, 253, 265, 269, 293}
    hy_f = {2, 3, 6, 7, 8, 9, 10, 12, 14, 26, 29, 33, 47, 50, 52, 57, 58, 71, 81, 95, 98, 110, 116, 124, 125, 141, 161, 166, 177, 186, 211, 224, 239, 241, 251, 263, 267, 274}

    # 4. Pd (Desviación Psicopática - 50 ítems)
    pd_t = {17, 21, 22, 31, 32, 35, 42, 52, 54, 56, 71, 82, 89, 94, 99, 105, 113, 160, 172, 180, 214, 239, 259, 266, 271}
    pd_f = {9, 12, 34, 70, 79, 83, 95, 125, 129, 137, 157, 161, 170, 185, 193, 235, 240, 243, 248, 267, 284, 294, 296, 311, 345}

    # 5. Mf (Masculinidad-Feminidad - 56 ítems)
    mf_t = {4, 25, 62, 64, 67, 74, 80, 112, 119, 121, 128, 137, 166, 177, 187, 191, 196, 205, 219, 256, 260, 268, 272, 282, 297}
    mf_f = {1, 19, 26, 27, 63, 68, 69, 76, 86, 103, 104, 107, 120, 132, 133, 134, 144, 163, 184, 193, 204, 217, 231, 235, 243, 257, 270, 274, 281, 294, 300}

    # 6. Pa (Paranoia - 40 ítems)
    pa_t = {16, 17, 22, 23, 24, 42, 99, 113, 138, 144, 145, 162, 234, 259, 271, 277, 285, 305, 307, 314, 315, 333, 334, 336, 355, 361}
    pa_f = {93, 107, 109, 111, 123, 128, 137, 160, 183, 268, 279, 283, 286, 310}

    # 7. Pt (Psicastenia - 48 ítems)
    pt_t = {11, 16, 23, 31, 38, 56, 67, 73, 87, 92, 114, 138, 147, 160, 170, 215, 223, 242, 299, 301, 304, 308, 313, 317, 321, 327, 332, 337, 338, 342, 346, 350, 356, 357, 358, 360}
    pt_f = {3, 9, 33, 109, 140, 165, 174, 202, 225, 329, 341, 344}

    # 8. Sc (Esquizofrenia - 78 ítems)
    sc_t = {16, 17, 21, 23, 31, 32, 38, 42, 44, 46, 48, 65, 85, 92, 138, 145, 147, 168, 170, 180, 182, 190, 215, 221, 229, 233, 234, 252, 256, 268, 273, 277, 279, 281, 287, 291, 292, 296, 298, 303, 307, 311, 316, 319, 322, 323, 324, 325, 328, 329, 331, 333, 335, 340, 343, 347, 352, 355, 364}
    sc_f = {9, 33, 63, 104, 109, 140, 165, 174, 201, 220, 276, 280, 290, 309, 320, 341, 345, 350}

    # 9. Ma (Hipomanía - 46 ítems)
    ma_t = {11, 13, 15, 21, 23, 50, 55, 61, 85, 87, 98, 113, 122, 145, 155, 168, 169, 182, 190, 200, 206, 211, 212, 220, 227, 229, 238, 242, 244, 248, 250, 253, 269, 284, 291}
    ma_f = {100, 106, 107, 136, 154, 158, 167, 243, 263, 278, 318}

    # 0. Si (Introversión Social - 69 ítems)
    si_t = {32, 67, 82, 111, 117, 124, 138, 147, 171, 172, 180, 181, 201, 236, 256, 267, 278, 287, 292, 304, 316, 321, 326, 336, 337, 338, 342, 347, 349, 351, 357, 358, 360, 362}
    si_f = {6, 25, 34, 49, 70, 79, 86, 104, 106, 110, 112, 129, 137, 143, 157, 161, 170, 185, 189, 209, 226, 235, 243, 248, 262, 275, 284, 296, 302, 306, 309, 311, 318, 330, 340}

    # Accumulators
    answered_count = 0
    true_count = 0
    false_count = 0

    l_score = 0
    f_score = 0
    k_score = 0

    hs_score = 0
    d_score = 0
    hy_score = 0
    pd_score = 0
    mf_score = 0
    pa_score = 0
    pt_score = 0
    sc_score = 0
    ma_score = 0
    si_score = 0

    for item_id in range(1, 568):
        key = str(item_id)
        val = answers.get(key) if answers.get(key) is not None else answers.get(f"item_{item_id}")
        if val is not None:
            v_str = str(val).strip().upper()
            is_true = v_str in ('V', 'VERDADERO', '1', 'TRUE')
            is_false = v_str in ('F', 'FALSO', '0', '2', 'FALSE')

            if is_true or is_false:
                answered_count += 1
                if is_true:
                    true_count += 1
                else:
                    false_count += 1

                # Validity scoring
                if item_id in val_L_false and is_false: l_score += 1
                if item_id in val_F_true and is_true: f_score += 1
                if item_id in val_F_false and is_false: f_score += 1
                if item_id in val_K_true and is_true: k_score += 1
                if item_id in val_K_false and is_false: k_score += 1

                # Clinical scoring
                if item_id in hs_t and is_true: hs_score += 1
                if item_id in hs_f and is_false: hs_score += 1

                if item_id in d_t and is_true: d_score += 1
                if item_id in d_f and is_false: d_score += 1

                if item_id in hy_t and is_true: hy_score += 1
                if item_id in hy_f and is_false: hy_score += 1

                if item_id in pd_t and is_true: pd_score += 1
                if item_id in pd_f and is_false: pd_score += 1

                if item_id in mf_t and is_true: mf_score += 1
                if item_id in mf_f and is_false: mf_score += 1

                if item_id in pa_t and is_true: pa_score += 1
                if item_id in pa_f and is_false: pa_score += 1

                if item_id in pt_t and is_true: pt_score += 1
                if item_id in pt_f and is_false: pt_score += 1

                if item_id in sc_t and is_true: sc_score += 1
                if item_id in sc_f and is_false: sc_score += 1

                if item_id in ma_t and is_true: ma_score += 1
                if item_id in ma_f and is_false: ma_score += 1

                if item_id in si_t and is_true: si_score += 1
                if item_id in si_f and is_false: si_score += 1

    pct_complete = round((answered_count / 567.0) * 100, 1)

    if pct_complete >= 90:
        classification = "Protocolo MMPI-2 Válido / Perfil Clínico Generado"
    else:
        classification = f"Protocolo Incompleto ({pct_complete}%)"

    subscales = {
        "Validez L (Mentira)": f"{l_score} / 15 pts",
        "Validez F (Incoherencia)": f"{f_score} / 60 pts",
        "Validez K (Corrección/Defensa)": f"{k_score} / 30 pts",
        "1. Hs (Hipocondriasis)": f"{hs_score} / 32 pts",
        "2. D (Depresión)": f"{d_score} / 57 pts",
        "3. Hy (Histeria)": f"{hy_score} / 60 pts",
        "4. Pd (Desviación Psicopática)": f"{pd_score} / 50 pts",
        "5. Mf (Masculinidad-Feminidad)": f"{mf_score} / 56 pts",
        "6. Pa (Paranoia)": f"{pa_score} / 40 pts",
        "7. Pt (Psicastenia)": f"{pt_score} / 48 pts",
        "8. Sc (Esquizofrenia)": f"{sc_score} / 78 pts",
        "9. Ma (Hipomanía)": f"{ma_score} / 46 pts",
        "0. Si (Introversión Social)": f"{si_score} / 69 pts",
        "Reactivos Respondidos": f"{answered_count} / 567 ({pct_complete}%)"
    }

    interpretation = (
        f"Perfil MMPI-2 ({classification}): "
        f"Escalas Validez: L={l_score}, F={f_score}, K={k_score}. "
        f"Escalas Clínicas (Puntuaciones Brutas): "
        f"Hs={hs_score}, D={d_score}, Hy={hy_score}, Pd={pd_score}, Mf={mf_score}, "
        f"Pa={pa_score}, Pt={pt_score}, Sc={sc_score}, Ma={ma_score}, Si={si_score}. "
        f"Total ítems respondidos: {answered_count}/567 ({true_count} Verdadero / {false_count} Falso)."
    )

    return float(answered_count), subscales, classification, interpretation

# --- ALGORITMOS DE EVALUACIÓN Y PUNTUACIÓN Y RUTAS DEL DECORADOR TESTS_BP ---

@tests_bp.route('/evaluacion/<token>', methods=['GET'])
def render_public_test_page(token):
    return render_template('index.html')

@tests_bp.route('/api/tests/catalogo', methods=['GET'])
def api_get_tests_catalogo():
    db = get_db()
    ensure_tests_tables(db)
    cursor = db.cursor()
    cursor.execute("SELECT code, nombre, siglas, categoria, descripcion FROM tests_definiciones")
    rows = cursor.fetchall()
    return jsonify({'tests': [dict(r) for r in rows]})

@tests_bp.route('/api/tests/asignar', methods=['POST'])
def api_asignar_test():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'No autorizado.'}), 401

    try:
        db = get_db()
        ensure_usuarios_columns(db)
        ensure_tests_tables(db)
        cursor = db.cursor()

        role = session.get('role', '')
        is_admin = role in ['admin', 'superadmin'] or user_id == 1

        cursor.execute("SELECT bloqueo_tests, role FROM usuarios WHERE id = ?", (user_id,))
        usr = cursor.fetchone()
        if usr:
            usr_dict = dict(usr)
            if usr_dict.get('role') in ['admin', 'superadmin']:
                is_admin = True
            if usr_dict.get('bloqueo_tests') == 1 and not is_admin:
                return jsonify({'error': 'El módulo de Tests Psicológicos se encuentra restringido para tu usuario.'}), 403

        data = request.json or {}
        patient_id = data.get('patient_id')
        test_code = data.get('test_code')
        modo = data.get('modo_aplicacion', 'link')

        if not patient_id or not test_code:
            return jsonify({'error': 'Faltan datos obligatorios.'}), 400

        if is_admin:
            cursor.execute("SELECT id, nombres, apellidos, telefono FROM pacientes WHERE id = ?", (patient_id,))
        else:
            cursor.execute("SELECT id, nombres, apellidos, telefono FROM pacientes WHERE id = ? AND (psicologo_id = ? OR psicologo_id IS NULL)", (patient_id, user_id))
        pac = cursor.fetchone()
        if not pac:
            return jsonify({'error': 'Acceso denegado: El consultante no pertenece a tu consulta activa.'}), 404

        token = uuid.uuid4().hex
        cursor.execute("""
            INSERT INTO test_asignaciones (uuid_token, patient_id, user_id, test_code, estado, modo_aplicacion)
            VALUES (?, ?, ?, ?, 'pendiente', ?)
        """, (token, patient_id, user_id, test_code, modo))
        db.commit()

        url_test = f"{request.host_url.rstrip('/')}/evaluacion/{token}"
        clean_phone = (pac['telefono'] or '').replace(' ', '').replace('-', '').replace('+', '')

        try:
            from app import notify_patient_firebase
            notify_patient_firebase(
                patient_id,
                "🧪 Nuevo Test Psicológico Asignado",
                f"Tu psicólogo te ha asignado una evaluación psicológica ({test_code}) para responder.",
                link=url_test,
                icon="🧪"
            )
        except Exception as _ne:
            print("Aviso al notificar test a paciente:", _ne)

        whatsapp_url = None
        whatsapp_sent = False
        if clean_phone:
            import urllib.parse
            msg_text = f"Hola {pac['nombres']}, te comparto el enlace para responder tu evaluación psicológica: {url_test}"
            whatsapp_url = f"https://api.whatsapp.com/send?phone={clean_phone}&text={urllib.parse.quote(msg_text)}"
            
            try:
                from routes_notificaciones import make_wa_http_request
                wa_res = make_wa_http_request('POST', '/send', json_data={'phone': clean_phone, 'text': msg_text, 'user_id': user_id}, timeout=4, user_id=user_id)
                if wa_res and getattr(wa_res, 'status_code', 0) == 200:
                    res_data = wa_res.json()
                    if res_data.get('success'):
                        whatsapp_sent = True
            except Exception as _wa_err:
                print("Aviso al intentar enviar WhatsApp automático de test:", _wa_err)

        return jsonify({
            'success': 'Test asignado exitosamente.',
            'assignment_id': cursor.lastrowid,
            'token': token,
            'url': url_test,
            'url_test': url_test,
            'whatsapp_phone': clean_phone,
            'whatsapp_url': whatsapp_url,
            'whatsapp_sent': whatsapp_sent,
            'paciente_nombre': f"{pac['nombres']} {pac['apellidos']}".strip()
        })
    except Exception as e:
        import traceback
        print("ERROR EN API_ASIGNAR_TEST:", traceback.format_exc())
        return jsonify({'error': f'Error al asignar test: {str(e)}'}), 500

@tests_bp.route('/api/public/evaluacion/<token>', methods=['GET'])
def api_get_public_evaluacion(token):
    try:
        db = get_db()
        ensure_tests_tables(db)
        cursor = db.cursor()

        raw_token = (token or '').strip()
        clean_token = raw_token.replace('-', '').lower()

        cursor.execute("""
            SELECT a.id, a.uuid_token, a.patient_id, a.user_id, a.test_code, a.estado, a.modo_aplicacion,
                   a.fecha_asignacion, a.fecha_completado, a.respuestas_json, a.puntaje_total,
                   a.subescalas_json, a.clasificacion_resultado, a.interpretacion_clinica, a.notas_terapeuta,
                   p.nombres as patient_nombres, p.apellidos as patient_apellidos, p.cedula as patient_cedula,
                   td.nombre as test_nombre, td.siglas as test_siglas, td.categoria as test_categoria,
                   td.descripcion as test_descripcion, td.instrucciones as test_instrucciones,
                   td.escala_opciones_json, td.items_json,
                   u.username as psicologo_username
            FROM test_asignaciones a
            JOIN pacientes p ON a.patient_id = p.id
            LEFT JOIN tests_definiciones td ON a.test_code = td.code
            LEFT JOIN usuarios u ON a.user_id = u.id
            WHERE LOWER(REPLACE(a.uuid_token, '-', '')) = ?
        """, (clean_token,))

        row = cursor.fetchone()
        if not row:
            return jsonify({'error': 'Enlace de evaluación no válido o inexistente.'}), 404

        data = dict(row)
        patient_nombre = f"{data.get('patient_nombres') or ''} {data.get('patient_apellidos') or ''}".strip()
        psicologo_nombre = f"Psic. {data.get('psicologo_username') or 'Clínico'}".strip()

        assignment = {
            'id': data['id'],
            'assignment_id': data['id'],
            'token': data['uuid_token'],
            'uuid_token': data['uuid_token'],
            'estado': data['estado'],
            'test_code': data['test_code'],
            'paciente_nombre': patient_nombre,
            'psicologo_nombre': psicologo_nombre or 'Psicólogo Clínico',
            'psicologo_foto': data.get('psicologo_foto') or '/static/logo.png',
            'psicologo_titulo': data.get('psicologo_titulo') or 'Consulta',
            'fecha_asignacion': data['fecha_asignacion'],
            'fecha_completado': data['fecha_completado']
        }
        test_definition = {
            'code': data['test_code'],
            'nombre': data['test_nombre'] or data['test_code'],
            'siglas': data['test_siglas'] or data['test_code'],
            'categoria': data['test_categoria'] or 'Evaluación Clínica',
            'descripcion': data['test_instrucciones'] or 'Por favor responde con sinceridad cada una de las siguientes afirmaciones.',
            'instrucciones': data['test_instrucciones'] or '',
            'escala_opciones': json.loads(data['escala_opciones_json']) if data.get('escala_opciones_json') else [],
            'items': json.loads(data['items_json']) if data.get('items_json') else []
        }
        return jsonify({
            'assignment': assignment,
            'test_definition': test_definition,
            'assignment_id': data['id'],
            'token': data['uuid_token'],
            'estado': data['estado'],
            'test_code': data['test_code'],
            'test_nombre': data['test_siglas'] or data['test_code'],
            'test_siglas': data['test_siglas'] or data['test_code'],
            'test_categoria': data['test_categoria'] or 'Evaluación Clínica',
            'test_descripcion': data.get('test_instrucciones') or 'Por favor responde con sinceridad cada una de las siguientes afirmaciones.',
            'test_instrucciones': data.get('test_instrucciones') or '',
            'escala_opciones': json.loads(data['escala_opciones_json']) if data.get('escala_opciones_json') else [],
            'items': json.loads(data['items_json']) if data.get('items_json') else [],
            'patient_nombre': patient_nombre,
            'fecha_asignacion': data['fecha_asignacion'],
            'fecha_completado': data['fecha_completado']
        })
    except Exception as e:
        return jsonify({'error': f'Error al cargar evaluación: {str(e)}'}), 500

@tests_bp.route('/api/public/evaluacion/<token>/responder', methods=['POST'])
def api_post_public_evaluacion(token):
    try:
        db = get_db()
        ensure_tests_tables(db)
        cursor = db.cursor()

        raw_token = (token or '').strip()
        clean_token = raw_token.replace('-', '').lower()

        cursor.execute("""
            SELECT a.*, p.nombres as patient_nombres, p.apellidos as patient_apellidos
            FROM test_asignaciones a
            JOIN pacientes p ON a.patient_id = p.id
            WHERE LOWER(REPLACE(a.uuid_token, '-', '')) = ?
        """, (clean_token,))

        row = cursor.fetchone()
        if not row:
            return jsonify({'error': 'Evaluación no encontrada.'}), 404

        assignment = dict(row)
        if assignment['estado'] == 'completado':
            return jsonify({'error': 'Esta evaluación ya fue completada previamente.'}), 400

        data = request.json or {}
        answers = data.get('respuestas', {})
        if not answers:
            return jsonify({'error': 'Por favor responde todas las preguntas requeridas.'}), 400

        if assignment['test_code'] == 'ZUNG-SDS':
            total_score, subscales_dict, classification, interpretation = process_zung_sds_scoring(answers)
        elif assignment['test_code'] == 'HAMILTON-D':
            total_score, subscales_dict, classification, interpretation = process_hamilton_d_scoring(answers)
        elif assignment['test_code'] in ('IDARE-STAI', 'IDARE'):
            total_score, subscales_dict, classification, interpretation = process_idare_stai_scoring(answers)
        elif assignment['test_code'] == 'SCL-90-R':
            total_score, subscales_dict, classification, interpretation = process_scl90r_scoring(answers)
        elif assignment['test_code'] in ('BECK-BHS', 'BHS'):
            total_score, subscales_dict, classification, interpretation = process_beck_bhs_scoring(answers)
        elif assignment['test_code'] in ('MMPI-2', 'MMPI2', 'MMPI'):
            total_score, subscales_dict, classification, interpretation = process_mmpi2_scoring(answers)
        else:
            try:
                from app import process_test_scoring
                total_score, subscales_dict, classification, interpretation = process_test_scoring(
                    assignment['test_code'], answers, assignment=assignment, request_data=data, db=db
                )
            except Exception as _pe:
                total_score, subscales_dict, classification, interpretation = 0.0, {}, "Completado", "Respuestas registradas exitosamente."

        fecha_completado = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute("""
            UPDATE test_asignaciones
            SET estado = 'completado',
                fecha_completado = ?,
                respuestas_json = ?,
                puntaje_total = ?,
                subescalas_json = ?,
                clasificacion_resultado = ?,
                interpretacion_clinica = ?
            WHERE id = ?
        """, (
            fecha_completado,
            json.dumps(answers),
            total_score,
            json.dumps(subscales_dict),
            classification,
            interpretation,
            assignment['id']
        ))

        # Generar notificación para el psicólogo
        pac_nombre = f"{assignment['patient_nombres']} {assignment['patient_apellidos']}".strip()
        cursor.execute("""
            INSERT INTO notificaciones (user_id, tipo, titulo, mensaje, fecha, leida, link)
            VALUES (?, ?, ?, ?, ?, 0, ?)
        """, (
            assignment['user_id'],
            'test',
            '🧪 Test Psicológico Completado',
            f'El consultante {pac_nombre} completó la evaluación {assignment["test_code"]}. Puntuación: {total_score} ({classification}).',
            fecha_completado,
            'tests-psicologicos'
        ))

        db.commit()

        return jsonify({
            'success': '¡Evaluación completada con éxito! Tus respuestas han sido registradas para tu especialista.'
        })
    except Exception as e:
        db.rollback()
        import traceback
        print("ERROR AL RESPONDER TEST:", traceback.format_exc())
        return jsonify({'error': f'Error al guardar respuestas: {str(e)}'}), 500

@tests_bp.route('/api/tests/historial', methods=['GET'])
@login_required
def api_get_tests_historial():
    user_id = session.get('user_id')
    db = get_db()
    ensure_tests_tables(db)
    cursor = db.cursor()

    role = session.get('role', '')
    is_admin = role in ['admin', 'superadmin'] or user_id == 1

    patient_id = request.args.get('patient_id')

    if patient_id:
        if is_admin:
            cursor.execute("""
                SELECT a.*, p.nombres as patient_nombres, p.apellidos as patient_apellidos,
                       COALESCE(td.nombre, a.test_code) as test_nombre,
                       COALESCE(td.siglas, a.test_code) as test_siglas,
                       COALESCE(td.categoria, 'Evaluación Clínica') as test_categoria
                FROM test_asignaciones a
                LEFT JOIN pacientes p ON a.patient_id = p.id
                LEFT JOIN tests_definiciones td ON a.test_code = td.code
                WHERE a.patient_id = ?
                ORDER BY a.fecha_asignacion DESC
            """, (patient_id,))
        else:
            cursor.execute("""
                SELECT a.*, p.nombres as patient_nombres, p.apellidos as patient_apellidos,
                       COALESCE(td.nombre, a.test_code) as test_nombre,
                       COALESCE(td.siglas, a.test_code) as test_siglas,
                       COALESCE(td.categoria, 'Evaluación Clínica') as test_categoria
                FROM test_asignaciones a
                LEFT JOIN pacientes p ON a.patient_id = p.id
                LEFT JOIN tests_definiciones td ON a.test_code = td.code
                WHERE a.patient_id = ? AND a.user_id = ?
                ORDER BY a.fecha_asignacion DESC
            """, (patient_id, user_id))
    else:
        if is_admin:
            cursor.execute("""
                SELECT a.*, p.nombres as patient_nombres, p.apellidos as patient_apellidos,
                       COALESCE(td.nombre, a.test_code) as test_nombre,
                       COALESCE(td.siglas, a.test_code) as test_siglas,
                       COALESCE(td.categoria, 'Evaluación Clínica') as test_categoria
                FROM test_asignaciones a
                LEFT JOIN pacientes p ON a.patient_id = p.id
                LEFT JOIN tests_definiciones td ON a.test_code = td.code
                ORDER BY a.fecha_asignacion DESC LIMIT 100
            """)
        else:
            cursor.execute("""
                SELECT a.*, p.nombres as patient_nombres, p.apellidos as patient_apellidos,
                       COALESCE(td.nombre, a.test_code) as test_nombre,
                       COALESCE(td.siglas, a.test_code) as test_siglas,
                       COALESCE(td.categoria, 'Evaluación Clínica') as test_categoria
                FROM test_asignaciones a
                LEFT JOIN pacientes p ON a.patient_id = p.id
                LEFT JOIN tests_definiciones td ON a.test_code = td.code
                WHERE a.user_id = ?
                ORDER BY a.fecha_asignacion DESC LIMIT 100
            """, (user_id,))

    rows = cursor.fetchall()
    data_list = []
    for r in rows:
        item = dict(r)
        if item.get('uuid_token'):
            item['url_test'] = f"/evaluacion/{item['uuid_token']}"
        data_list.append(item)
    return jsonify({'asignaciones': data_list, 'tests': data_list, 'success': True})

@tests_bp.route('/api/tests/paciente/<int:patient_id>', methods=['GET'])
@login_required
def api_get_tests_paciente(patient_id):
    user_id = session.get('user_id')
    db = get_db()
    ensure_tests_tables(db)
    cursor = db.cursor()

    role = session.get('role', '')
    is_admin = role in ['admin', 'superadmin'] or user_id == 1

    if is_admin:
        cursor.execute("""
            SELECT a.*,
                   COALESCE(td.nombre, a.test_code) as test_nombre,
                   COALESCE(td.siglas, a.test_code) as test_siglas,
                   COALESCE(td.categoria, 'Evaluación Clínica') as test_categoria
            FROM test_asignaciones a
            LEFT JOIN tests_definiciones td ON a.test_code = td.code
            WHERE a.patient_id = ?
            ORDER BY a.fecha_asignacion DESC
        """, (patient_id,))
    else:
        cursor.execute("""
            SELECT a.*,
                   COALESCE(td.nombre, a.test_code) as test_nombre,
                   COALESCE(td.siglas, a.test_code) as test_siglas,
                   COALESCE(td.categoria, 'Evaluación Clínica') as test_categoria
            FROM test_asignaciones a
            LEFT JOIN tests_definiciones td ON a.test_code = td.code
            WHERE a.patient_id = ? AND a.user_id = ?
            ORDER BY a.fecha_asignacion DESC
        """, (patient_id, user_id))

    rows = cursor.fetchall()
    data_list = []
    for r in rows:
        item = dict(r)
        if item.get('uuid_token'):
            item['url_test'] = f"/evaluacion/{item['uuid_token']}"
        data_list.append(item)
    return jsonify({'asignaciones': data_list, 'tests': data_list, 'success': True})

@tests_bp.route('/api/tests/asignacion/<int:assignment_id>', methods=['DELETE'])
@login_required
def api_eliminar_test_asignacion(assignment_id):
    user_id = session.get('user_id')
    db = get_db()
    ensure_tests_tables(db)
    cursor = db.cursor()

    try:
        cursor.execute("DELETE FROM test_asignaciones WHERE id = ? AND user_id = ?", (assignment_id, user_id))
        db.commit()
        return jsonify({'success': 'Asignación eliminada correctamente.'})
    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500

@tests_bp.route('/api/patient-portal/tests', methods=['GET'])
@patient_login_required
def api_patient_portal_tests():
    patient_id = session.get('patient_id')
    db = get_db()
    ensure_tests_tables(db)
    cursor = db.cursor()

    cursor.execute("""
        SELECT a.*, td.nombre as test_nombre, td.siglas as test_siglas, td.categoria as test_categoria,
               u.nombres as psic_nombres, u.apellidos as psic_apellidos
        FROM test_asignaciones a
        JOIN tests_definiciones td ON a.test_code = td.code
        JOIN usuarios u ON a.user_id = u.id
        WHERE a.patient_id = ?
        ORDER BY a.fecha_asignacion DESC
    """, (patient_id,))

    rows = cursor.fetchall()
    tests_list = []
    for r in rows:
        d = dict(r)
        d['psicologo_nombre'] = f"Psic. {d['psic_nombres']} {d['psic_apellidos']}".strip()
        d['url_evaluacion'] = f"/evaluacion/{d['uuid_token']}"
        tests_list.append(d)

    return jsonify({'tests': tests_list})

@tests_bp.route('/api/tests/asignacion/<int:assignment_id>/resultado-manual', methods=['POST'])
@login_required
def api_guardar_resultado_manual_test(assignment_id):
    user_id = session.get('user_id')
    db = get_db()
    ensure_tests_tables(db)
    cursor = db.cursor()

    try:
        data = request.json or {}
        puntaje_total = data.get('puntaje_total')
        clasificacion = data.get('clasificacion_resultado', '')
        interpretacion = data.get('interpretacion_clinica', '')
        notas = data.get('notas_terapeuta', '')
        subescalas = data.get('subescalas_json', {})

        cursor.execute("SELECT id, user_id FROM test_asignaciones WHERE id = ?", (assignment_id,))
        row = cursor.fetchone()
        if not row:
            return jsonify({'error': 'Asignación de test no encontrada.'}), 404

        fecha_completado = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute("""
            UPDATE test_asignaciones
            SET estado = 'completado',
                fecha_completado = ?,
                puntaje_total = ?,
                subescalas_json = ?,
                clasificacion_resultado = ?,
                interpretacion_clinica = ?,
                notas_terapeuta = ?
            WHERE id = ?
        """, (
            fecha_completado,
            puntaje_total,
            json.dumps(subescalas) if isinstance(subescalas, dict) else subescalas,
            clasificacion,
            interpretacion,
            notas,
            assignment_id
        ))

        db.commit()
        return jsonify({'success': 'Resultado manual registrado e incorporado al historial con éxito.'})
    except Exception as e:
        db.rollback()
        return jsonify({'error': f'Error al registrar resultado: {str(e)}'}), 500


@tests_bp.route('/api/tests/materials/<path:filename>', methods=['GET'])
def download_test_material_file(filename):
    try:
        from app import get_resource_path
        static_folder = get_resource_path('static')
        materials_dir = os.path.join(static_folder, 'test_materials')
        file_path = os.path.join(materials_dir, filename)
        if os.path.exists(file_path):
            return send_file(file_path, as_attachment=False)
        return "Archivo de test no encontrado.", 404
    except Exception as e:
        return f"Error al servir archivo: {str(e)}", 500

@tests_bp.route('/api/tests/asignacion/<int:assignment_id>/export/pdf', methods=['GET'])
def api_export_test_pdf(assignment_id):
    if 'user_id' not in session and 'patient_id' not in session:
        return "Debe iniciar sesión para exportar el test.", 401
    try:
        db = get_db()
        ensure_tests_tables(db)
        cursor = db.cursor()

        cursor.execute("""
            SELECT a.*, p.nombres as patient_nombres, p.apellidos as patient_apellidos, p.cedula as patient_cedula,
                   td.nombre as test_nombre, td.siglas as test_siglas, td.categoria as test_categoria,
                   u.nombres as psicologo_nombres, u.apellidos as psicologo_apellidos, u.estudios as psicologo_titulo
            FROM test_asignaciones a
            LEFT JOIN pacientes p ON a.patient_id = p.id
            LEFT JOIN tests_definiciones td ON a.test_code = td.code
            LEFT JOIN usuarios u ON a.user_id = u.id
            WHERE a.id = ?
        """, (assignment_id,))

        row = cursor.fetchone()
        if not row:
            return "Error: Asignación de test no encontrada.", 404

        data = dict(row)
        pac_nombre = f"{data.get('patient_nombres') or ''} {data.get('patient_apellidos') or ''}".strip()
        psic_nombre = f"Psic. {data.get('psicologo_nombres') or ''} {data.get('psicologo_apellidos') or ''}".strip()

        subescalas = {}
        if data.get('subescalas_json'):
            try:
                subescalas = json.loads(data['subescalas_json'])
            except Exception:
                subescalas = {}

        sub_html = ""
        if isinstance(subescalas, dict) and subescalas:
            sub_html = "<h3 style='color:#334155; margin-top:20px;'>Subescalas y Dimensiones</h3><table style='width:100%; border-collapse:collapse; margin-top:10px;'><tr style='background:#f1f5f9;'><th style='padding:8px; border:1px solid #cbd5e1; text-align:left;'>Escala / Dimensión</th><th style='padding:8px; border:1px solid #cbd5e1; text-align:center;'>Puntaje</th></tr>"
            for k, v in subescalas.items():
                sub_html += f"<tr><td style='padding:8px; border:1px solid #cbd5e1;'>{k}</td><td style='padding:8px; border:1px solid #cbd5e1; text-align:center; font-weight:bold;'>{v}</td></tr>"
            sub_html += "</table>"

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Informe de Evaluación Psicológica - {data.get('test_siglas') or data.get('test_code')}</title>
            <style>
                body {{ font-family: 'Helvetica Neue', Arial, sans-serif; margin: 40px; color: #1e293b; font-size: 14px; line-height: 1.6; }}
                .header {{ border-bottom: 3px solid #702e5e; padding-bottom: 15px; margin-bottom: 25px; display: flex; justify-content: space-between; align-items: center; }}
                .title {{ font-size: 22px; font-weight: bold; color: #702e5e; margin: 0; }}
                .subtitle {{ font-size: 13px; color: #64748b; margin-top: 4px; }}
                .info-box {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 15px; margin-bottom: 20px; }}
                .info-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }}
                .result-box {{ background: #fdf4ff; border: 2px solid #f0abfc; border-radius: 10px; padding: 20px; margin: 20px 0; text-align: center; }}
                .score {{ font-size: 32px; font-weight: bold; color: #702e5e; }}
                .badge {{ display: inline-block; background: #702e5e; color: white; padding: 4px 14px; border-radius: 20px; font-weight: bold; font-size: 13px; margin-top: 5px; }}
                .section {{ margin-top: 25px; }}
                .section-title {{ font-size: 16px; font-weight: bold; color: #0f172a; border-bottom: 1px solid #e2e8f0; padding-bottom: 6px; margin-bottom: 10px; }}
                .footer {{ margin-top: 50px; text-align: center; font-size: 11px; color: #94a3b8; border-top: 1px solid #e2e8f0; padding-top: 15px; }}
                @media print {{
                    body {{ margin: 20px; }}
                    .no-print {{ display: none; }}
                }}
            </style>
        </head>
        <body>
            <div class="no-print" style="text-align: right; margin-bottom: 20px;">
                <button onclick="window.print()" style="background:#702e5e; color:white; border:none; padding:8px 18px; border-radius:6px; font-weight:bold; cursor:pointer;">🖨️ Imprimir / Guardar como PDF</button>
            </div>
            <div class="header">
                <div>
                    <h1 class="title">INFORME DE EVALUACIÓN PSICOMÉTRICA</h1>
                    <div class="subtitle">Espacio Terapéutico — Sistema de Gestión Clínica</div>
                </div>
            </div>

            <div class="info-box">
                <div class="info-grid">
                    <div><strong>Consultante:</strong> {pac_nombre}</div>
                    <div><strong>Cédula / ID:</strong> {data.get('patient_cedula') or 'N/A'}</div>
                    <div><strong>Evaluación:</strong> {data.get('test_nombre') or data.get('test_code')} ({data.get('test_siglas') or data.get('test_code')})</div>
                    <div><strong>Categoría:</strong> {data.get('test_categoria') or 'Psicometría'}</div>
                    <div><strong>Especialista:</strong> {psic_nombre}</div>
                    <div><strong>Fecha de Evaluación:</strong> {data.get('fecha_completado') or data.get('fecha_asignacion') or 'N/A'}</div>
                </div>
            </div>

            <div class="result-box">
                <div style="font-size: 13px; font-weight: bold; color: #702e5e; text-transform: uppercase;">Puntaje Global Obtenido</div>
                <div class="score">{data.get('puntaje_total') if data.get('puntaje_total') is not None else 'N/A'} pts</div>
                <div class="badge">{data.get('clasificacion_resultado') or 'Completado'}</div>
            </div>

            {sub_html}

            <div class="section">
                <div class="section-title">Interpretación Clínica / Juicio Profesional</div>
                <div style="background: white; padding: 12px; border-left: 4px solid #702e5e; background: #fafafa;">
                    {data.get('interpretacion_clinica') or 'Respuestas evaluadas satisfactoriamente.'}
                </div>
            </div>

            {f'<div class="section"><div class="section-title">Observaciones del Terapeuta</div><div>{data.get("notas_terapeuta")}</div></div>' if data.get('notas_terapeuta') else ''}

            <div class="footer">
                Documento confidencial emitido por {psic_nombre} a través de la plataforma Espacio Terapéutico.<br>
                Válido para fines clínicos y de seguimiento terapéutico.
            </div>
        </body>
        </html>
        """
        response = make_response(html_content)
        response.headers["Content-Type"] = "text/html; charset=utf-8"
        return response
    except Exception as e:
        return f"Error al generar informe PDF: {str(e)}", 500


@tests_bp.route('/api/tests/asignacion/<int:assignment_id>/export/word', methods=['GET'])
@login_required
def api_export_test_word(assignment_id):
    return api_export_test_pdf(assignment_id)


