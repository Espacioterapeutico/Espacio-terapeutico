# -*- coding: utf-8 -*-
"""
Módulo de Recursos Terapéuticos (routes_recursos.py)
Gestión de fichas de trabajo psicoterapéuticas interactivas (Pros y Contras, Cuestionando Creencias,
Diversificando el Pensamiento, Pensamientos Negativos, Segmentación de Objetivos, Sobrepensamiento).
Soporta edición colaborativa en vivo (psicólogo y paciente), integración en el portal del paciente,
historial de versiones y exportación a Word (.docx) y PDF.
"""

import os
import io
import json
import uuid
import sqlite3
from datetime import datetime
from functools import wraps
from flask import Blueprint, request, jsonify, session, g, send_file, render_template

recursos_bp = Blueprint('recursos', __name__)

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
        if 'user_id' not in session and 'patient_id' not in session:
            return jsonify({'error': 'No autorizado. Por favor inicia sesión.'}), 401
        return f(*args, **kwargs)
    return decorated_function

def psychologist_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Acceso reservado a terapeutas/administradores.'}), 403
        return f(*args, **kwargs)
    return decorated_function

# Catálogo oficial de recursos homologados
RECURSOS_CATALOGO = [
    {
        "id": "pros_contras",
        "titulo": "Pros y Contras (Toma de Decisiones)",
        "subtitulo": "Matriz cuantitativa y ponderada para desbloquear la indecisión entre dos alternativas.",
        "descripcion": "Evalúa y califica del 1 al 5 el impacto positivo y negativo de dos opciones (A vs B), calculando automáticamente subtotales, balance matemático y validación emocional.",
        "icono": "⚖️",
        "categoria": "Resolución de Problemas",
        "tiempo_estimado": "10-15 min",
        "color": "#7e22ce",
        "color_bg": "#f3e8ff",
        "default_content": {
            "alternativa_a": "",
            "alternativa_b": "",
            "pros_a": [{"texto": "", "pts": 0}],
            "contras_a": [{"texto": "", "pts": 0}],
            "pros_b": [{"texto": "", "pts": 0}],
            "contras_b": [{"texto": "", "pts": 0}],
            "reflexion_emocional": "",
            "decision_final": ""
        }
    },
    {
        "id": "cuestionando_creencias",
        "titulo": "Cuestionando Creencias (Diálogo Socrático)",
        "subtitulo": "Reestructuración profunda de pensamientos automáticos paso a paso.",
        "descripcion": "Identifica una creencia o pensamiento limitante y profundiza en él seleccionando 1 sola pregunta reflexiva a la vez para evitar la sobrecarga cognitiva.",
        "icono": "🔍",
        "categoria": "Reestructuración Cognitiva",
        "tiempo_estimado": "10-15 min",
        "color": "#2563eb",
        "color_bg": "#dbeafe",
        "preguntas_banco": [
            {"id": "p1", "categoria": "Evidencia", "texto": "¿Qué pruebas tienes de que esta creencia o pensamiento es cierta al 100%?"},
            {"id": "p2", "categoria": "Evidencia", "texto": "¿Qué pruebas tienes de que podría NO ser cierta o de que estás exagerando?"},
            {"id": "p3", "categoria": "Objetividad", "texto": "¿Qué hechos objetivos y comprobables apoyan o contradicen lo que piensas?"},
            {"id": "p4", "categoria": "Experiencia", "texto": "¿Has tenido alguna experiencia en el pasado que demuestre lo contrario?"},
            {"id": "p5", "categoria": "Perspectiva", "texto": "¿Qué le dirías a un buen amigo si tuviera exactamente esta misma creencia?"},
            {"id": "p6", "categoria": "Impacto Vital", "texto": "¿Qué efecto y consecuencias tiene en tu vida diaria mantener esta creencia?"},
            {"id": "p7", "categoria": "Flexibilidad", "texto": "¿Qué pasaría si dejaras de lado esta creencia o pensamiento, aunque sea por un momento?"},
            {"id": "p8", "categoria": "Descatastrofización", "texto": "¿Qué es lo peor que realmente podría pasar si esta creencia fuera cierta?"},
            {"id": "p9", "categoria": "Impacto Real", "texto": "Si eso peor llegara a pasar, ¿cómo te afectaría en tu vida real y por cuánto tiempo?"},
            {"id": "p10", "categoria": "Afrontamiento", "texto": "¿Qué recursos personales, fortalezas o apoyos externos podrías usar para afrontarlo?"},
            {"id": "p11", "categoria": "Resiliencia", "texto": "¿Has superado antes una situación parecida? ¿Qué aprendiste de esa experiencia?"}
        ],
        "default_content": {
            "pensamiento_central": "",
            "tipo_apertura": "Tengo el pensamiento de que:",
            "preguntas_seleccionadas": [],
            "respuestas": {},
            "conclusion_realista": ""
        }
    },
    {
        "id": "diversificando_pensamiento",
        "titulo": "Diversificando el Pensamiento (Lentes Cognitivos)",
        "subtitulo": "Flexibilidad cognitiva evaluando un dilema bajo 6 perspectivas distintas.",
        "descripcion": "Adapta los Seis Sombreros de De Bono para desmontar bloqueos: Racional, Emocional, Crítico, Optimista, Creativo y Organizado, con caso clínico de ejemplo.",
        "icono": "🧠",
        "categoria": "Flexibilidad Cognitiva",
        "tiempo_estimado": "15-20 min",
        "color": "#0d9488",
        "color_bg": "#ccfbf1",
        "lentes": [
            {"key": "racional", "nombre": "Pensamiento Racional", "icono": "⚪", "color": "#475569", "guia": "Neutralidad y hechos objetivos, centrado en datos verificables."},
            {"key": "emocional", "nombre": "Pensamiento Emocional", "icono": "🔴", "color": "#dc2626", "guia": "Intuición, sentimientos y temores sin necesidad de justificación."},
            {"key": "critico", "nombre": "Pensamiento Crítico", "icono": "⚫", "color": "#1e293b", "guia": "Juicio cauteloso, pesimismo lógico y riesgos potenciales."},
            {"key": "optimista", "nombre": "Pensamiento Optimista", "icono": "🟡", "color": "#d97706", "guia": "Búsqueda de beneficios, valor personal y viabilidad positiva."},
            {"key": "creativo", "nombre": "Pensamiento Creativo", "icono": "🟢", "color": "#16a34a", "guia": "Alternativas novedosas, pensamiento lateral y soluciones 'fuera de la caja'."},
            {"key": "organizado", "nombre": "Pensamiento Organizado", "icono": "🔵", "color": "#2563eb", "guia": "Gestión del proceso, visión panorámica y plan de acción."}
        ],
        "default_content": {
            "pensamiento_central": "",
            "racional": "",
            "emocional": "",
            "critico": "",
            "optimista": "",
            "creativo": "",
            "organizado": "",
            "sintesis": ""
        }
    },
    {
        "id": "pensamientos_negativos",
        "titulo": "Pensamientos Negativos (Real vs. Imaginario)",
        "subtitulo": "Separación consciente de hechos empíricos frente a suposiciones y distorsiones.",
        "descripcion": "Filtro en dos columnas para cortar la rumiación: situaciones reales con base fáctica vs. situaciones imaginarias (lecturas de pensamiento y miedos no demostrados).",
        "icono": "🛡️",
        "categoria": "Distorsiones Cognitivas",
        "tiempo_estimado": "10 min",
        "color": "#ea580c",
        "color_bg": "#ffedd5",
        "default_content": {
            "malestar_actual": "",
            "situaciones_reales": [""],
            "situaciones_imaginarias": [""],
            "conclusion_discriminativa": ""
        }
    },
    {
        "id": "segmentacion_objetivos",
        "titulo": "Segmentación de Objetivos (Plan de Acción)",
        "subtitulo": "Estrategia por etapas para evitar la parálisis por agobio de metas grandes.",
        "descripcion": "Divide el proyecto vital en: Corto plazo (lo que puedo hacer hoy con mis recursos), Mediano plazo (recursos que necesito adquirir) y Largo plazo (metas mayores alcanzables).",
        "icono": "🎯",
        "categoria": "Activación Conductual",
        "tiempo_estimado": "15 min",
        "color": "#16a34a",
        "color_bg": "#dcfce7",
        "default_content": {
            "meta_global": "",
            "corto_plazo": {"descripcion": "¿Qué puedo hacer hoy o esta semana con lo que ya tengo?", "items": [""]},
            "mediano_plazo": {"descripcion": "¿Qué recursos o habilidades necesito conseguir y cómo?", "items": [""]},
            "largo_plazo": {"descripcion": "¿Qué puedo construir con los recursos que habré conseguido?", "items": [""]}
        }
    },
    {
        "id": "sobrepensamiento",
        "titulo": "Sobre-pensamiento (De la Rumiación a la Acción)",
        "subtitulo": "Protocolo de 4 pasos para desbloquear el bucle mental hacia una micro-acción.",
        "descripcion": "Embudo terapéutico: Vaciar la Situación → Reconocer Limitaciones incontrolables → Identificar Ventajas disponibles → Fijar 1 Acción concreta para esta semana.",
        "icono": "🚀",
        "categoria": "Gestión del Malestar",
        "tiempo_estimado": "10-12 min",
        "color": "#9333ea",
        "color_bg": "#f3e8ff",
        "default_content": {
            "situaciones_cabeza": "",
            "limitaciones": "",
            "ventajas_recursos": "",
            "accion_concreta_semana": ""
        }
    }
]

def ensure_recursos_tables(cursor):
    """Crea las tablas necesarias para el módulo de recursos si no existen."""
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS paciente_recursos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                psicologo_id INTEGER NOT NULL,
                paciente_id INTEGER NOT NULL,
                recurso_tipo TEXT NOT NULL,
                titulo TEXT NOT NULL,
                contenido_json TEXT NOT NULL,
                estado TEXT DEFAULT 'activo',
                token_compartido TEXT UNIQUE,
                ultima_edicion_por TEXT DEFAULT 'psicologo',
                fecha_ultima_edicion DATETIME DEFAULT CURRENT_TIMESTAMP,
                fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (psicologo_id) REFERENCES usuarios(id) ON DELETE CASCADE,
                FOREIGN KEY (paciente_id) REFERENCES pacientes(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS paciente_recursos_historial (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recurso_id INTEGER NOT NULL,
                contenido_json TEXT NOT NULL,
                editado_por TEXT NOT NULL,
                fecha_registro DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (recurso_id) REFERENCES paciente_recursos(id) ON DELETE CASCADE
            )
        """)
        # Índice para búsquedas rápidas por paciente
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_recursos_paciente ON paciente_recursos(paciente_id, estado)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_recursos_psicologo ON paciente_recursos(psicologo_id)")
    except Exception as _e:
        print("Error en ensure_recursos_tables:", _e)

# =========================================================================
# ENDPOINTS DE CATÁLOGO Y ASIGNACIÓN
# =========================================================================

@recursos_bp.route('/api/recursos/catalogo', methods=['GET'])
@login_required
def get_catalogo():
    """Retorna la lista de recursos disponibles en el sistema."""
    return jsonify(RECURSOS_CATALOGO)

@recursos_bp.route('/api/recursos/paciente/<int:paciente_id>', methods=['GET'])
@login_required
def get_recursos_paciente(paciente_id):
    """Retorna todos los recursos creados/asignados a un paciente."""
    user_id = session.get('user_id')
    patient_id = session.get('patient_id')
    
    # Validar acceso
    if patient_id and patient_id != paciente_id:
        return jsonify({'error': 'No autorizado para ver recursos de otro consultante.'}), 403

    db = get_db()
    cursor = db.cursor()
    ensure_recursos_tables(cursor)

    if user_id:
        # Psicólogo / Admin
        cursor.execute("""
            SELECT r.*, p.nombres, p.apellidos, p.email, p.telefono
            FROM paciente_recursos r
            JOIN pacientes p ON r.paciente_id = p.id
            WHERE r.paciente_id = ? AND r.psicologo_id = ?
            ORDER BY r.fecha_ultima_edicion DESC
        """, (paciente_id, user_id))
    else:
        # Paciente autenticado
        cursor.execute("""
            SELECT r.*, u.nombres as psico_nombres, u.apellidos as psico_apellidos
            FROM paciente_recursos r
            JOIN usuarios u ON r.psicologo_id = u.id
            WHERE r.paciente_id = ?
            ORDER BY r.fecha_ultima_edicion DESC
        """, (paciente_id,))

    rows = cursor.fetchall()
    result = []
    for row in rows:
        d = dict(row)
        try:
            d['contenido'] = json.loads(d['contenido_json'])
        except Exception:
            d['contenido'] = {}
        if not d.get('token_compartido'):
            d['token_compartido'] = uuid.uuid4().hex
            cursor.execute("UPDATE paciente_recursos SET token_compartido = ? WHERE id = ?", (d['token_compartido'], d['id']))
            db.commit()
        # Metadata del tipo de recurso
        meta = next((r for r in RECURSOS_CATALOGO if r['id'] == d['recurso_tipo']), None)
        d['meta'] = meta
        result.append(d)

    return jsonify(result)

@recursos_bp.route('/api/patient/recursos', methods=['GET'])
@login_required
def get_patient_portal_recursos():
    """Endpoint simplificado para que el paciente obtenga sus recursos asignados desde su portal."""
    patient_id = session.get('patient_id')
    if not patient_id:
        return jsonify({'error': 'Sesión de paciente no encontrada.'}), 401

    db = get_db()
    cursor = db.cursor()
    ensure_recursos_tables(cursor)

    cursor.execute("""
        SELECT r.*, u.nombres as psico_nombres, u.apellidos as psico_apellidos
        FROM paciente_recursos r
        JOIN usuarios u ON r.psicologo_id = u.id
        WHERE r.paciente_id = ? AND r.estado = 'activo'
        ORDER BY r.fecha_ultima_edicion DESC
    """, (patient_id,))

    rows = cursor.fetchall()
    result = []
    for row in rows:
        d = dict(row)
        try:
            d['contenido'] = json.loads(d['contenido_json'])
        except Exception:
            d['contenido'] = {}
        meta = next((r for r in RECURSOS_CATALOGO if r['id'] == d['recurso_tipo']), None)
        d['meta'] = meta
        result.append(d)

    return jsonify(result)

@recursos_bp.route('/api/recursos/asignar', methods=['POST'])
@psychologist_required
def asignar_recurso():
    """Crea una nueva pizarra de recurso para un paciente registrado."""
    user_id = session.get('user_id')
    data = request.json or {}

    paciente_id = data.get('paciente_id')
    recurso_tipo = data.get('recurso_tipo')
    titulo = data.get('titulo', '').strip()
    contenido_inicial = data.get('contenido')

    if not paciente_id or not recurso_tipo:
        return jsonify({'error': 'paciente_id y recurso_tipo son requeridos.'}), 400

    meta = next((r for r in RECURSOS_CATALOGO if r['id'] == recurso_tipo), None)
    if not meta:
        return jsonify({'error': 'Tipo de recurso no válido.'}), 400

    if not titulo:
        titulo = f"{meta['titulo']} - {datetime.now().strftime('%d/%m/%Y')}"

    if not contenido_inicial:
        contenido_inicial = meta.get('default_content', {})

    token_compartido = uuid.uuid4().hex

    db = get_db()
    cursor = db.cursor()
    ensure_recursos_tables(cursor)

    # Validar que el paciente pertenece al psicólogo o es admin
    cursor.execute("SELECT id, nombres, apellidos, telefono FROM pacientes WHERE id = ? AND psicologo_id = ?", (paciente_id, user_id))
    pac = cursor.fetchone()
    if not pac and session.get('role') != 'admin':
        return jsonify({'error': 'El paciente no pertenece a tu lista de consultantes registrados.'}), 403

    cursor.execute("""
        INSERT INTO paciente_recursos 
        (psicologo_id, paciente_id, recurso_tipo, titulo, contenido_json, estado, token_compartido, ultima_edicion_por)
        VALUES (?, ?, ?, ?, ?, 'activo', ?, 'psicologo')
    """, (user_id, paciente_id, recurso_tipo, titulo, json.dumps(contenido_inicial, ensure_ascii=False), token_compartido))
    
    recurso_id = cursor.lastrowid

    # Guardar snapshot inicial en historial
    cursor.execute("""
        INSERT INTO paciente_recursos_historial (recurso_id, contenido_json, editado_por)
        VALUES (?, ?, 'psicologo')
    """, (recurso_id, json.dumps(contenido_inicial, ensure_ascii=False)))

    db.commit()

    return jsonify({
        'success': True,
        'recurso_id': recurso_id,
        'titulo': titulo,
        'token_compartido': token_compartido,
        'recurso_tipo': recurso_tipo
    }), 201

# =========================================================================
# ENDPOINTS DE PIZARRA INTERACTIVA (EDICIÓN Y SINCRONIZACIÓN EN VIVO)
# =========================================================================

@recursos_bp.route('/api/recursos/pizarra/<int:recurso_id>', methods=['GET'])
@login_required
def get_pizarra(recurso_id):
    """Obtiene los datos completos de una pizarra de recurso."""
    user_id = session.get('user_id')
    patient_id = session.get('patient_id')

    db = get_db()
    cursor = db.cursor()
    ensure_recursos_tables(cursor)

    cursor.execute("""
        SELECT r.*, 
               p.nombres as pac_nombres, p.apellidos as pac_apellidos, p.email as pac_email, p.telefono as pac_telefono,
               u.nombres as psi_nombres, u.apellidos as psi_apellidos, u.nomenclatura as psi_nom
        FROM paciente_recursos r
        JOIN pacientes p ON r.paciente_id = p.id
        JOIN usuarios u ON r.psicologo_id = u.id
        WHERE r.id = ?
    """, (recurso_id,))
    row = cursor.fetchone()

    if not row:
        return jsonify({'error': 'Recurso no encontrado.'}), 404

    d = dict(row)

    # Validar permisos
    if patient_id and d['paciente_id'] != patient_id:
        return jsonify({'error': 'No tienes permiso para acceder a esta pizarra.'}), 403
    if user_id and d['psicologo_id'] != user_id and session.get('role') != 'admin':
        return jsonify({'error': 'No tienes permiso para acceder a esta pizarra.'}), 403

    try:
        d['contenido'] = json.loads(d['contenido_json'])
    except Exception:
        d['contenido'] = {}

    if not d.get('token_compartido'):
        d['token_compartido'] = uuid.uuid4().hex
        cursor.execute("UPDATE paciente_recursos SET token_compartido = ? WHERE id = ?", (d['token_compartido'], recurso_id))
        db.commit()

    meta = next((r for r in RECURSOS_CATALOGO if r['id'] == d['recurso_tipo']), None)
    d['meta'] = meta

    return jsonify(d)

@recursos_bp.route('/api/recursos/pizarra/<int:recurso_id>', methods=['PUT'])
@login_required
def update_pizarra(recurso_id):
    """
    Actualiza el contenido de una pizarra en tiempo real.
    Permite guardado tanto por el psicólogo como por el paciente.
    """
    user_id = session.get('user_id')
    patient_id = session.get('patient_id')
    data = request.json or {}

    db = get_db()
    cursor = db.cursor()
    ensure_recursos_tables(cursor)

    cursor.execute("SELECT * FROM paciente_recursos WHERE id = ?", (recurso_id,))
    row = cursor.fetchone()
    if not row:
        return jsonify({'error': 'Recurso no encontrado.'}), 404

    r_dict = dict(row)
    editado_por = 'paciente' if patient_id else 'psicologo'

    if patient_id and r_dict['paciente_id'] != patient_id:
        return jsonify({'error': 'Acceso no autorizado.'}), 403
    if user_id and r_dict['psicologo_id'] != user_id and session.get('role') != 'admin':
        return jsonify({'error': 'Acceso no autorizado.'}), 403

    nuevo_contenido = data.get('contenido', {})
    nuevo_titulo = data.get('titulo', r_dict['titulo']).strip() or r_dict['titulo']
    nuevo_estado = data.get('estado', r_dict['estado'])

    contenido_str = json.dumps(nuevo_contenido, ensure_ascii=False)

    cursor.execute("""
        UPDATE paciente_recursos
        SET titulo = ?,
            contenido_json = ?,
            estado = ?,
            ultima_edicion_por = ?,
            fecha_ultima_edicion = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (nuevo_titulo, contenido_str, nuevo_estado, editado_por, recurso_id))

    # Guardar en historial de versiones
    cursor.execute("""
        INSERT INTO paciente_recursos_historial (recurso_id, contenido_json, editado_por)
        VALUES (?, ?, ?)
    """, (recurso_id, contenido_str, editado_por))

    db.commit()

    return jsonify({
        'success': True,
        'recurso_id': recurso_id,
        'ultima_edicion_por': editado_por,
        'fecha_ultima_edicion': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })

@recursos_bp.route('/api/recursos/pizarra/<int:recurso_id>/historial', methods=['GET'])
@login_required
def get_historial(recurso_id):
    """Retorna las versiones guardadas de la pizarra."""
    db = get_db()
    cursor = db.cursor()
    ensure_recursos_tables(cursor)

    cursor.execute("""
        SELECT h.*
        FROM paciente_recursos_historial h
        JOIN paciente_recursos r ON h.recurso_id = r.id
        WHERE h.recurso_id = ?
        ORDER BY h.fecha_registro DESC
        LIMIT 30
    """, (recurso_id,))
    rows = cursor.fetchall()

    result = []
    for row in rows:
        d = dict(row)
        try:
            d['contenido'] = json.loads(d['contenido_json'])
        except Exception:
            d['contenido'] = {}
        result.append(d)

    return jsonify(result)

@recursos_bp.route('/api/recursos/pizarra/<int:recurso_id>', methods=['DELETE'])
@psychologist_required
def delete_recurso(recurso_id):
    """Archiva o elimina una pizarra de recurso."""
    user_id = session.get('user_id')
    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT psicologo_id FROM paciente_recursos WHERE id = ?", (recurso_id,))
    row = cursor.fetchone()
    if not row:
        return jsonify({'error': 'Recurso no encontrado.'}), 404
    if row['psicologo_id'] != user_id and session.get('role') != 'admin':
        return jsonify({'error': 'No autorizado.'}), 403

    cursor.execute("DELETE FROM paciente_recursos WHERE id = ?", (recurso_id,))
    db.commit()
    return jsonify({'success': 'Recurso eliminado correctamente.'})

# =========================================================================
# WHATSAPP Y ENCOLADO CRON DE PIZARRAS DE TRABAJO
# =========================================================================

@recursos_bp.route('/api/recursos/pizarra/<int:recurso_id>/enviar-whatsapp', methods=['POST'])
@psychologist_required
def enviar_recurso_whatsapp(recurso_id):
    """
    Envía o programa el enlace directo a la pizarra colaborativa por WhatsApp:
    - modo 'inmediato': despacha al instante a través del microservicio WhatsApp / Bot.
    - modo 'cron': agenda en cola_recordatorios_herramientas para que el cron job lo envíe a la hora indicada.
    """
    user_id = session.get('user_id')
    data = request.json or {}
    modo = data.get('modo', 'inmediato')
    hora = (data.get('hora') or '20:00').strip()
    fecha_prog = data.get('fecha') or datetime.now().strftime("%Y-%m-%d")

    db = get_db()
    cursor = db.cursor()
    ensure_recursos_tables(cursor)

    cursor.execute("""
        SELECT r.*, 
               p.nombres as pac_nombres, p.apellidos as pac_apellidos, p.telefono as pac_telefono,
               u.nombres as psi_nombres, u.apellidos as psi_apellidos
        FROM paciente_recursos r
        JOIN pacientes p ON r.paciente_id = p.id
        JOIN usuarios u ON r.psicologo_id = u.id
        WHERE r.id = ?
    """, (recurso_id,))
    row = cursor.fetchone()

    if not row:
        return jsonify({'error': 'Recurso o pizarra no encontrada.'}), 404

    d = dict(row)
    if d['psicologo_id'] != user_id and session.get('role') != 'admin':
        return jsonify({'error': 'No autorizado para gestionar este recurso.'}), 403

    phone = d.get('pac_telefono')
    if not phone or not str(phone).strip():
        return jsonify({'error': 'El consultante no tiene un número de teléfono registrado en su ficha.'}), 400

    token = d.get('token_compartido')
    if not token:
        token = uuid.uuid4().hex
        cursor.execute("UPDATE paciente_recursos SET token_compartido = ? WHERE id = ?", (token, recurso_id))
        db.commit()

    from routes_herramientas import get_public_base_url, clean_phone_number
    host_url = get_public_base_url()
    direct_link = f"{host_url}/pizarra/compartida/{token}"

    first_name = (d.get('pac_nombres') or '').strip().split()[0] if d.get('pac_nombres') else 'Consultante'
    titulo = d.get('titulo') or 'Pizarra de Trabajo'

    msg_wa = (
        f"Hola *{first_name}* 👋\n\n"
        f"Te comparto tu pizarra de trabajo interactivo: *{titulo}*.\n\n"
        f"Puedes abrirla, escribir y reflexionar en ella directamente desde este enlace colaborativo:\n"
        f"👉 {direct_link}\n\n"
        f"Los cambios que realices se guardan automáticamente en tiempo real para nuestra próxima sesión."
    )

    clean_phone = clean_phone_number(phone)

    if modo == 'inmediato':
        try:
            from routes_notificaciones import make_wa_http_request
            res = make_wa_http_request(
                'POST',
                '/send',
                json_data={'phone': clean_phone, 'text': msg_wa, 'user_id': user_id, 'linkPreview': False},
                timeout=15,
                user_id=user_id
            )
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            today_str = datetime.now().strftime("%Y-%m-%d")

            # Registrar en cola de recordatorios como enviado para historial y monitor
            cursor.execute("""
                INSERT INTO cola_recordatorios_herramientas (
                    psicologo_id, paciente_id, herramienta_tipo, fecha_programada, hora_programada, estado, enviado, fecha_envio, token_id
                ) VALUES (?, ?, ?, ?, ?, 'enviado', 1, ?, ?)
                ON CONFLICT(paciente_id, herramienta_tipo, fecha_programada) DO UPDATE SET
                    estado = 'enviado', enviado = 1, fecha_envio = ?, token_id = ?
            """, (user_id, d['paciente_id'], f"pizarra_{recurso_id}", today_str, now_str[11:16], now_str, recurso_id, now_str, recurso_id))
            db.commit()

            if res and res.status_code == 200:
                return jsonify({
                    'success': True,
                    'modo': 'inmediato',
                    'message': f'Pizarra enviada exitosamente por WhatsApp a {first_name}.',
                    'link': direct_link
                })
            else:
                err_msg = 'Error al enviar por microservicio de WhatsApp'
                try: err_msg = res.json().get('error', res.text)
                except: pass
                return jsonify({'error': f'El bot de WhatsApp no pudo entregar el mensaje: {err_msg}'}), 502

        except Exception as ex_wa:
            return jsonify({'error': f'Error de conexión con WhatsApp: {str(ex_wa)}'}), 500

    elif modo == 'cron':
        try:
            cursor.execute("""
                INSERT INTO cola_recordatorios_herramientas (
                    psicologo_id, paciente_id, herramienta_tipo, fecha_programada, hora_programada, estado, enviado, pausado, token_id
                ) VALUES (?, ?, ?, ?, ?, 'programado', 0, 0, ?)
                ON CONFLICT(paciente_id, herramienta_tipo, fecha_programada) DO UPDATE SET
                    hora_programada = ?, estado = 'programado', enviado = 0, pausado = 0, token_id = ?
            """, (user_id, d['paciente_id'], f"pizarra_{recurso_id}", fecha_prog, hora, recurso_id, hora, recurso_id))
            db.commit()

            return jsonify({
                'success': True,
                'modo': 'cron',
                'message': f'Pizarra programada exitosamente en el cron job para enviarse a las {hora}.',
                'hora': hora,
                'fecha': fecha_prog,
                'link': direct_link
            })
        except Exception as ex_cron:
            return jsonify({'error': f'Error al agendar en la cola cron: {str(ex_cron)}'}), 500

    else:
        return jsonify({'error': 'Modo no válido. Debe ser "inmediato" o "cron".'}), 400

# =========================================================================
# VISTA PÚBLICA Y SINCRONIZACIÓN EN TIEMPO REAL (ACCESO CON TOKEN)
# =========================================================================

@recursos_bp.route('/pizarra/compartida/<token>', methods=['GET'])
def view_pizarra_compartida(token):
    """
    Permite al paciente acceder a su pizarra de trabajo interactivo colaborativo
    directamente desde el enlace recibido por WhatsApp (sin requerir login previo).
    """
    db = get_db()
    cursor = db.cursor()
    ensure_recursos_tables(cursor)

    cursor.execute("""
        SELECT r.*, 
               p.nombres as pac_nombres, p.apellidos as pac_apellidos, p.email as pac_email, p.telefono as pac_telefono,
               u.nombres as psi_nombres, u.apellidos as psi_apellidos, u.nomenclatura as psi_nom
        FROM paciente_recursos r
        JOIN pacientes p ON r.paciente_id = p.id
        JOIN usuarios u ON r.psicologo_id = u.id
        WHERE r.token_compartido = ?
    """, (token,))
    row = cursor.fetchone()
    if not row:
        return render_template('portal_recurso_pizarra.html', error_msg="La pizarra solicitada no existe o el enlace es inválido.", pizarra={}, token=token, meta={}), 404

    d = dict(row)
    try:
        d['contenido'] = json.loads(d['contenido_json'])
    except Exception:
        d['contenido'] = {}

    meta = next((r for r in RECURSOS_CATALOGO if r['id'] == d['recurso_tipo']), None)
    d['meta'] = meta

    return render_template('portal_recurso_pizarra.html', pizarra=d, token=token, meta=meta)


@recursos_bp.route('/api/recursos/compartido/<token>', methods=['GET'])
def api_get_pizarra_compartida(token):
    """Retorna los datos de la pizarra vía token para sincronización colaborativa."""
    db = get_db()
    cursor = db.cursor()
    ensure_recursos_tables(cursor)

    cursor.execute("""
        SELECT r.*, 
               p.nombres as pac_nombres, p.apellidos as pac_apellidos,
               u.nombres as psi_nombres, u.apellidos as psi_apellidos
        FROM paciente_recursos r
        JOIN pacientes p ON r.paciente_id = p.id
        JOIN usuarios u ON r.psicologo_id = u.id
        WHERE r.token_compartido = ?
    """, (token,))
    row = cursor.fetchone()
    if not row:
        return jsonify({'error': 'Pizarra no encontrada.'}), 404

    d = dict(row)
    try:
        d['contenido'] = json.loads(d['contenido_json'])
    except Exception:
        d['contenido'] = {}

    meta = next((r for r in RECURSOS_CATALOGO if r['id'] == d['recurso_tipo']), None)
    d['meta'] = meta
    return jsonify(d)


@recursos_bp.route('/api/recursos/compartido/<token>', methods=['PUT'])
def api_update_pizarra_compartida(token):
    """Guarda las modificaciones realizadas por el consultante desde su enlace público."""
    data = request.json or {}
    nuevo_contenido = data.get('contenido')
    if nuevo_contenido is None:
        return jsonify({'error': 'Contenido requerido.'}), 400

    db = get_db()
    cursor = db.cursor()
    ensure_recursos_tables(cursor)

    cursor.execute("SELECT id FROM paciente_recursos WHERE token_compartido = ?", (token,))
    row = cursor.fetchone()
    if not row:
        return jsonify({'error': 'Pizarra no encontrada.'}), 404

    recurso_id = row['id']
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    cursor.execute("""
        UPDATE paciente_recursos
        SET contenido_json = ?,
            ultima_edicion_por = 'paciente',
            fecha_ultima_edicion = ?
        WHERE id = ?
    """, (json.dumps(nuevo_contenido, ensure_ascii=False), now_str, recurso_id))

    cursor.execute("""
        INSERT INTO paciente_recursos_historial (recurso_id, contenido_json, editado_por)
        VALUES (?, ?, 'paciente')
    """, (recurso_id, json.dumps(nuevo_contenido, ensure_ascii=False)))

    db.commit()

    return jsonify({
        'success': True,
        'fecha_ultima_edicion': now_str,
        'ultima_edicion_por': 'paciente'
    })


@recursos_bp.route('/pizarra/compartida/<token>/export-word', methods=['GET'])
def export_word_compartida(token):
    """Permite al consultante descargar su documento Word (.docx) directamente desde el enlace compartido."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT id FROM paciente_recursos WHERE token_compartido = ?", (token,))
    row = cursor.fetchone()
    if not row:
        return jsonify({'error': 'Pizarra no encontrada.'}), 404
    return _generate_word_file(row['id'])

# =========================================================================
# EXPORTACIÓN A WORD (.DOCX)
# =========================================================================

@recursos_bp.route('/api/recursos/pizarra/<int:recurso_id>/export-word', methods=['GET'])
@login_required
def export_word(recurso_id):
    """Genera y descarga un archivo .docx formateado con los datos de la pizarra."""
    return _generate_word_file(recurso_id)

def _generate_word_file(recurso_id):
    import docx
    from docx.shared import Inches, Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.table import WD_TABLE_ALIGNMENT

    db = get_db()
    cursor = db.cursor()

    cursor.execute("""
        SELECT r.*, 
               p.nombres as pac_nombres, p.apellidos as pac_apellidos, p.cedula as pac_cedula,
               u.nombres as psi_nombres, u.apellidos as psi_apellidos, u.nomenclatura as psi_nom
        FROM paciente_recursos r
        JOIN pacientes p ON r.paciente_id = p.id
        JOIN usuarios u ON r.psicologo_id = u.id
        WHERE r.id = ?
    """, (recurso_id,))
    row = cursor.fetchone()
    if not row:
        return jsonify({'error': 'Recurso no encontrado.'}), 404

    d = dict(row)
    try:
        content = json.loads(d['contenido_json'])
    except Exception:
        content = {}

    doc = docx.Document()

    # Configuración de márgenes
    sections = doc.sections
    for section in sections:
        section.top_margin = Inches(0.8)
        section.bottom_margin = Inches(0.8)
        section.left_margin = Inches(0.8)
        section.right_margin = Inches(0.8)

    # Encabezado institucional
    p_header = doc.add_paragraph()
    p_header.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run_inst = p_header.add_run("ESPACIO TERAPÉUTICO | CONSULTORIO CLÍNICO\n")
    run_inst.font.name = "Arial"
    run_inst.font.size = Pt(11)
    run_inst.font.bold = True
    run_inst.font.color.rgb = RGBColor(112, 46, 94)

    run_title = p_header.add_run(d['titulo'].upper())
    run_title.font.name = "Arial"
    run_title.font.size = Pt(14)
    run_title.font.bold = True
    run_title.font.color.rgb = RGBColor(30, 41, 59)

    # Ficha técnica
    doc.add_paragraph()
    tbl_info = doc.add_table(rows=2, cols=2)
    tbl_info.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl_info.autofit = True

    r0c0 = tbl_info.cell(0, 0).paragraphs[0]
    r0c0.add_run("Consultante: ").bold = True
    r0c0.add_run(f"{d['pac_nombres']} {d['pac_apellidos']}")

    r0c1 = tbl_info.cell(0, 1).paragraphs[0]
    r0c1.add_run("Terapeuta: ").bold = True
    r0c1.add_run(f"{d.get('psi_nom', 'Psic.')} {d['psi_nombres']} {d['psi_apellidos']}")

    r1c0 = tbl_info.cell(1, 0).paragraphs[0]
    r1c0.add_run("Fecha de emisión: ").bold = True
    r1c0.add_run(datetime.now().strftime('%d/%m/%Y'))

    r1c1 = tbl_info.cell(1, 1).paragraphs[0]
    r1c1.add_run("Última actualización: ").bold = True
    r1c1.add_run(str(d.get('fecha_ultima_edicion', ''))[:16])

    doc.add_paragraph().paragraph_format.space_after = Pt(12)

    # Generación específica por tipo de recurso
    rtype = d['recurso_tipo']

    if rtype == 'pros_contras':
        alt_a = content.get('alternativa_a', 'Alternativa A')
        alt_b = content.get('alternativa_b', 'Alternativa B')

        p_desc = doc.add_paragraph()
        p_desc.add_run("Evaluación Cuantitativa Ponderada (Puntuación de 1 a 5 por impacto):\n").bold = True
        p_desc.add_run("Balance final = Suma de Pros - Suma de Contras.")

        tbl = doc.add_table(rows=1, cols=4)
        tbl.style = 'Table Grid'
        hdr_cells = tbl.rows[0].cells
        hdr_cells[0].paragraphs[0].add_run(f"PROS: {alt_a}").bold = True
        hdr_cells[1].paragraphs[0].add_run("Pts").bold = True
        hdr_cells[2].paragraphs[0].add_run(f"PROS: {alt_b}").bold = True
        hdr_cells[3].paragraphs[0].add_run("Pts").bold = True

        pros_a = content.get('pros_a', [])
        pros_b = content.get('pros_b', [])
        max_pros = max(len(pros_a), len(pros_b), 1)

        sum_pa = 0
        sum_pb = 0
        for i in range(max_pros):
            row_cells = tbl.add_row().cells
            item_a = pros_a[i] if i < len(pros_a) else {"texto": "", "pts": 0}
            item_b = pros_b[i] if i < len(pros_b) else {"texto": "", "pts": 0}
            row_cells[0].paragraphs[0].add_run(str(item_a.get('texto', '')))
            row_cells[1].paragraphs[0].add_run(str(item_a.get('pts', 0)))
            row_cells[2].paragraphs[0].add_run(str(item_b.get('texto', '')))
            row_cells[3].paragraphs[0].add_run(str(item_b.get('pts', 0)))
            sum_pa += int(item_a.get('pts') or 0)
            sum_pb += int(item_b.get('pts') or 0)

        r_subp = tbl.add_row().cells
        r_subp[0].paragraphs[0].add_run("SUBTOTAL PROS").bold = True
        r_subp[1].paragraphs[0].add_run(str(sum_pa)).bold = True
        r_subp[2].paragraphs[0].add_run("SUBTOTAL PROS").bold = True
        r_subp[3].paragraphs[0].add_run(str(sum_pb)).bold = True

        # Contras
        r_sep = tbl.add_row().cells
        r_sep[0].paragraphs[0].add_run(f"CONTRAS: {alt_a}").bold = True
        r_sep[1].paragraphs[0].add_run("Pts").bold = True
        r_sep[2].paragraphs[0].add_run(f"CONTRAS: {alt_b}").bold = True
        r_sep[3].paragraphs[0].add_run("Pts").bold = True

        contras_a = content.get('contras_a', [])
        contras_b = content.get('contras_b', [])
        max_contras = max(len(contras_a), len(contras_b), 1)

        sum_ca = 0
        sum_cb = 0
        for i in range(max_contras):
            row_cells = tbl.add_row().cells
            item_a = contras_a[i] if i < len(contras_a) else {"texto": "", "pts": 0}
            item_b = contras_b[i] if i < len(contras_b) else {"texto": "", "pts": 0}
            row_cells[0].paragraphs[0].add_run(str(item_a.get('texto', '')))
            row_cells[1].paragraphs[0].add_run(str(item_a.get('pts', 0)))
            row_cells[2].paragraphs[0].add_run(str(item_b.get('texto', '')))
            row_cells[3].paragraphs[0].add_run(str(item_b.get('pts', 0)))
            sum_ca += int(item_a.get('pts') or 0)
            sum_cb += int(item_b.get('pts') or 0)

        r_subc = tbl.add_row().cells
        r_subc[0].paragraphs[0].add_run("SUBTOTAL CONTRAS").bold = True
        r_subc[1].paragraphs[0].add_run(str(sum_ca)).bold = True
        r_subc[2].paragraphs[0].add_run("SUBTOTAL CONTRAS").bold = True
        r_subc[3].paragraphs[0].add_run(str(sum_cb)).bold = True

        bal_a = sum_pa - sum_ca
        bal_b = sum_pb - sum_cb
        r_tot = tbl.add_row().cells
        r_tot[0].paragraphs[0].add_run("BALANCE TOTAL (Pros - Contras)").bold = True
        r_tot[1].paragraphs[0].add_run(f"{bal_a:+d}").bold = True
        r_tot[2].paragraphs[0].add_run("BALANCE TOTAL (Pros - Contras)").bold = True
        r_tot[3].paragraphs[0].add_run(f"{bal_b:+d}").bold = True

        if content.get('reflexion_emocional'):
            doc.add_paragraph()
            p_ref = doc.add_paragraph()
            p_ref.add_run("Reflexión y validación emocional:\n").bold = True
            p_ref.add_run(content['reflexion_emocional'])

        if content.get('decision_final'):
            p_dec = doc.add_paragraph()
            p_dec.add_run("Decisión o camino a seguir acordado:\n").bold = True
            p_dec.add_run(content['decision_final'])

    elif rtype == 'cuestionando_creencias':
        p_c = doc.add_paragraph()
        p_c.add_run("Creencia / Pensamiento Identificado:\n").bold = True
        p_c.add_run(f"\"{content.get('tipo_apertura', 'Yo creo que:')} {content.get('pensamiento_central', '')}\"")

        doc.add_paragraph()
        p_q = doc.add_paragraph()
        p_q.add_run("Cuestionamiento Socrático Profundo:\n").bold = True

        respuestas = content.get('respuestas', {})
        for q_id, r_text in respuestas.items():
            # Buscar texto de la pregunta
            meta_recurso = next((r for r in RECURSOS_CATALOGO if r['id'] == 'cuestionando_creencias'), {})
            banco = meta_recurso.get('preguntas_banco', [])
            item_b = next((b for b in banco if b['id'] == q_id), None)
            q_text = item_b['texto'] if item_b else q_id

            p_item = doc.add_paragraph()
            p_item.add_run(f"• {q_text}\n").bold = True
            p_item.add_run(f"Respuesta: {r_text}\n")

        if content.get('conclusion_realista'):
            doc.add_paragraph()
            p_conc = doc.add_paragraph()
            p_conc.add_run("Pensamiento Alternativo / Más Realista:\n").bold = True
            p_conc.add_run(content['conclusion_realista'])

    elif rtype == 'diversificando_pensamiento':
        p_c = doc.add_paragraph()
        p_c.add_run("Pensamiento o Situación Central:\n").bold = True
        p_c.add_run(content.get('pensamiento_central', ''))

        doc.add_paragraph()
        lentes = [
            ("Racional (Datos objetivos)", content.get('racional', '')),
            ("Emocional (Sentimientos sin juzgar)", content.get('emocional', '')),
            ("Crítico (Riesgos y cautela)", content.get('critico', '')),
            ("Optimista (Beneficios y viabilidad)", content.get('optimista', '')),
            ("Creativo (Soluciones alternativas)", content.get('creativo', '')),
            ("Organizado (Plan y enfoque)", content.get('organizado', ''))
        ]
        for title, val in lentes:
            p_l = doc.add_paragraph()
            p_l.add_run(f"[{title}]:\n").bold = True
            p_l.add_run(val if val else "Sin anotaciones.")

        if content.get('sintesis'):
            doc.add_paragraph()
            p_s = doc.add_paragraph()
            p_s.add_run("Síntesis Global:\n").bold = True
            p_s.add_run(content['sintesis'])

    elif rtype == 'pensamientos_negativos':
        p_m = doc.add_paragraph()
        p_m.add_run("Malestar / Idea que genera ansiedad:\n").bold = True
        p_m.add_run(content.get('malestar_actual', ''))

        doc.add_paragraph()
        tbl = doc.add_table(rows=1, cols=2)
        tbl.style = 'Table Grid'
        hdr = tbl.rows[0].cells
        hdr[0].paragraphs[0].add_run("SITUACIONES REALES\n(Hechos comprobables)").bold = True
        hdr[1].paragraphs[0].add_run("SITUACIONES IMAGINARIAS\n(Supuestos sin evidencia)").bold = True

        reales = content.get('situaciones_reales', [])
        imag = content.get('situaciones_imaginarias', [])
        max_rows = max(len(reales), len(imag), 1)
        for i in range(max_rows):
            rc = tbl.add_row().cells
            txt_r = reales[i] if i < len(reales) else ""
            txt_i = imag[i] if i < len(imag) else ""
            rc[0].paragraphs[0].add_run(f"• {txt_r}" if txt_r else "")
            rc[1].paragraphs[0].add_run(f"• {txt_i}" if txt_i else "")

        if content.get('conclusion_discriminativa'):
            doc.add_paragraph()
            p_cd = doc.add_paragraph()
            p_cd.add_run("Conclusión Discriminativa:\n").bold = True
            p_cd.add_run(content['conclusion_discriminativa'])

    elif rtype == 'segmentacion_objetivos':
        p_mg = doc.add_paragraph()
        p_mg.add_run("Meta Global del Consultante:\n").bold = True
        p_mg.add_run(content.get('meta_global', ''))

        doc.add_paragraph()
        niveles = [
            ("Metas a Corto Plazo (¿Qué puedo hacer hoy/esta semana?)", content.get('corto_plazo', {}).get('items', [])),
            ("Metas a Mediano Plazo (Recursos a conseguir)", content.get('mediano_plazo', {}).get('items', [])),
            ("Metas a Largo Plazo (Con los recursos ya adquiridos)", content.get('largo_plazo', {}).get('items', []))
        ]
        for tit, items in niveles:
            p_n = doc.add_paragraph()
            p_n.add_run(f"{tit}:\n").bold = True
            for it in items:
                if it:
                    p_n.add_run(f"  ✓ {it}\n")

    elif rtype == 'sobrepensamiento':
        fases = [
            ("1. Situación (Ideas dando vueltas en la cabeza)", content.get('situaciones_cabeza', '')),
            ("2. Limitaciones (Lo que escapa de mi control actual)", content.get('limitaciones', '')),
            ("3. Ventajas y Recursos (Fortalezas y apoyos presentes hoy)", content.get('ventajas_recursos', '')),
            ("4. Micro-acción Concreta para esta semana", content.get('accion_concreta_semana', ''))
        ]
        for f_tit, f_val in fases:
            p_f = doc.add_paragraph()
            p_f.add_run(f"{f_tit}:\n").bold = True
            p_f.add_run(f_val if f_val else "Sin registro.")
            doc.add_paragraph()

    # Guardar en memoria y enviar
    stream = io.BytesIO()
    doc.save(stream)
    stream.seek(0)

    filename = f"{rtype}_{d['pac_apellidos']}_{datetime.now().strftime('%Y%m%d')}.docx"
    return send_file(
        stream,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
