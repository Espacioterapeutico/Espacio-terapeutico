# -*- coding: utf-8 -*-
"""
Módulo de Estimulación Cognitiva (routes_estimulacion.py)
Encapsula la biblioteca personalizable de carpetas y ejercicios cognitivos,
asignación rotativa y secuencial a consultantes, cron de envíos por WhatsApp,
y portal web accesible para descarga y registro de progreso del consultante.
"""

import os
import json
import uuid
import secrets
import sqlite3
from datetime import datetime, timezone, timedelta
from functools import wraps
from flask import Blueprint, request, jsonify, render_template, current_app, redirect, session, g, send_from_directory
from werkzeug.utils import secure_filename

estimulacion_bp = Blueprint('estimulacion', __name__)

ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'webp', 'doc', 'docx', 'xls', 'xlsx'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_db():
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

def get_public_base_url():
    try:
        from flask import has_request_context
        if has_request_context() and request and request.host_url:
            h = request.host_url.rstrip('/')
            if 'localhost' not in h and '127.0.0.1' not in h and '0.0.0.0' not in h:
                if h.startswith('http://'):
                    h = 'https://' + h[7:]
                return h
    except Exception:
        pass
    return os.environ.get('APP_URL', 'https://www.espacioterapeutico.net').rstrip('/')

def ensure_estimulacion_tables(db=None):
    if db is None:
        db = get_db()
    cursor = db.cursor()
    
    # 1. Carpetas de estimulación cognitiva
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cat_carpetas_cognitivas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            psicologo_id INTEGER,
            titulo TEXT NOT NULL,
            descripcion TEXT,
            color TEXT DEFAULT '#9333ea',
            icono TEXT DEFAULT '🧠',
            fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 2. Ejercicios / Fichas dentro de cada carpeta
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cat_ejercicios_cognitivos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            carpeta_id INTEGER NOT NULL,
            psicologo_id INTEGER,
            orden INTEGER DEFAULT 1,
            titulo TEXT NOT NULL,
            instrucciones TEXT,
            tipo_archivo TEXT DEFAULT 'pdf',
            archivo_url TEXT,
            enlace_externo TEXT,
            fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (carpeta_id) REFERENCES cat_carpetas_cognitivas(id) ON DELETE CASCADE
        )
    """)

    # 3. Asignación activa a consultante
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS paciente_estimulacion_cognitiva (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id INTEGER NOT NULL,
            psicologo_id INTEGER NOT NULL,
            carpeta_id INTEGER NOT NULL,
            frecuencia TEXT DEFAULT 'dias_semana',
            dias_semana_json TEXT DEFAULT '[1,3,5]',
            hora_recordatorio TEXT DEFAULT '09:00',
            modo_rotacion TEXT DEFAULT 'secuencial',
            al_terminar TEXT DEFAULT 'pausar',
            ultimo_ejercicio_id INTEGER,
            activa INTEGER DEFAULT 1,
            token_acceso TEXT UNIQUE,
            fecha_asignacion DATETIME DEFAULT CURRENT_TIMESTAMP,
            fecha_culminacion DATETIME,
            FOREIGN KEY (carpeta_id) REFERENCES cat_carpetas_cognitivas(id)
        )
    """)

    # 4. Registro de entregas y ejecuciones del consultante
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS registro_estimulacion_cognitiva (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asignacion_id INTEGER NOT NULL,
            paciente_id INTEGER NOT NULL,
            ejercicio_id INTEGER NOT NULL,
            token_acceso TEXT UNIQUE,
            fecha_envio TEXT NOT NULL,
            hora_envio TEXT NOT NULL,
            descargado INTEGER DEFAULT 0,
            fecha_descarga DATETIME,
            completado INTEGER DEFAULT 0,
            dificultad TEXT,
            tiempo_minutos INTEGER,
            observaciones TEXT,
            archivo_respuesta_url TEXT,
            fecha_completado DATETIME,
            FOREIGN KEY (asignacion_id) REFERENCES paciente_estimulacion_cognitiva(id),
            FOREIGN KEY (ejercicio_id) REFERENCES cat_ejercicios_cognitivos(id)
        )
    """)
    db.commit()

    # Limpieza preventiva: evitar que cola_recordatorios_herramientas guarde registros erróneos de estimulación
    try:
        cursor.execute("DELETE FROM cola_recordatorios_herramientas WHERE herramienta_tipo IN ('estimulacion_cognitiva', 'estimulacion')")
        cursor.execute("DELETE FROM tokens_herramientas WHERE herramienta_tipo IN ('estimulacion_cognitiva', 'estimulacion') AND usado = 0")
        db.commit()
    except Exception:
        pass

# =======================================================
# GESTIÓN DE CARPETAS / BIBLIOTECAS (PROFESIONAL)
# =======================================================

@estimulacion_bp.route('/api/estimulacion/carpetas', methods=['GET', 'POST'])
@login_required
def api_carpetas():
    db = get_db()
    cursor = db.cursor()
    user_id = session.get('user_id')
    ensure_estimulacion_tables(db)

    if request.method == 'GET':
        cursor.execute("""
            SELECT c.*, 
                   (SELECT COUNT(*) FROM cat_ejercicios_cognitivos e WHERE e.carpeta_id = c.id) as total_ejercicios
            FROM cat_carpetas_cognitivas c
            WHERE c.psicologo_id = ? OR c.psicologo_id IS NULL
            ORDER BY c.fecha_creacion DESC
        """, (user_id,))
        rows = [dict(r) for r in cursor.fetchall()]
        return jsonify({'carpetas': rows})

    elif request.method == 'POST':
        data = request.get_json() or {}
        titulo = data.get('titulo', '').strip()
        if not titulo:
            return jsonify({'error': 'El título de la carpeta es obligatorio.'}), 400

        descripcion = data.get('descripcion', '').strip()
        color = data.get('color', '#9333ea').strip()
        icono = data.get('icono', '🧠').strip()

        cursor.execute("""
            INSERT INTO cat_carpetas_cognitivas (psicologo_id, titulo, descripcion, color, icono)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, titulo, descripcion, color, icono))
        db.commit()
        new_id = cursor.lastrowid
        return jsonify({'success': 'Carpeta creada exitosamente.', 'id': new_id}), 201

@estimulacion_bp.route('/api/estimulacion/carpetas/<int:carpeta_id>', methods=['PUT', 'DELETE'])
@login_required
def api_carpeta_detail(carpeta_id):
    db = get_db()
    cursor = db.cursor()
    user_id = session.get('user_id')

    if request.method == 'PUT':
        data = request.get_json() or {}
        titulo = data.get('titulo', '').strip()
        if not titulo:
            return jsonify({'error': 'El título es obligatorio.'}), 400

        descripcion = data.get('descripcion', '').strip()
        color = data.get('color', '#9333ea').strip()
        icono = data.get('icono', '🧠').strip()

        cursor.execute("""
            UPDATE cat_carpetas_cognitivas
            SET titulo = ?, descripcion = ?, color = ?, icono = ?
            WHERE id = ? AND (psicologo_id = ? OR psicologo_id IS NULL)
        """, (titulo, descripcion, color, icono, carpeta_id, user_id))
        db.commit()
        return jsonify({'success': 'Carpeta actualizada exitosamente.'})

    elif request.method == 'DELETE':
        cursor.execute("DELETE FROM cat_ejercicios_cognitivos WHERE carpeta_id = ?", (carpeta_id,))
        cursor.execute("DELETE FROM cat_carpetas_cognitivas WHERE id = ? AND (psicologo_id = ? OR psicologo_id IS NULL)", (carpeta_id, user_id))
        db.commit()
        return jsonify({'success': 'Carpeta y sus ejercicios eliminados exitosamente.'})

# =======================================================
# GESTIÓN DE EJERCICIOS DENTRO DE UNA CARPETA
# =======================================================

@estimulacion_bp.route('/api/estimulacion/carpetas/<int:carpeta_id>/ejercicios', methods=['GET', 'POST'])
@login_required
def api_carpeta_ejercicios(carpeta_id):
    db = get_db()
    cursor = db.cursor()
    user_id = session.get('user_id')

    if request.method == 'GET':
        cursor.execute("""
            SELECT * FROM cat_ejercicios_cognitivos
            WHERE carpeta_id = ?
            ORDER BY orden ASC, id ASC
        """, (carpeta_id,))
        rows = [dict(r) for r in cursor.fetchall()]
        return jsonify({'ejercicios': rows})

    elif request.method == 'POST':
        titulo = request.form.get('titulo', '').strip()
        if not titulo:
            return jsonify({'error': 'El título del ejercicio es obligatorio.'}), 400

        instrucciones = request.form.get('instrucciones', '').strip()
        enlace_externo = request.form.get('enlace_externo', '').strip()

        cursor.execute("SELECT COALESCE(MAX(orden), 0) + 1 FROM cat_ejercicios_cognitivos WHERE carpeta_id = ?", (carpeta_id,))
        siguiente_orden = cursor.fetchone()[0]

        archivo_url = None
        tipo_archivo = 'enlace' if enlace_externo else 'pdf'

        if 'archivo' in request.files:
            file = request.files['archivo']
            if file and file.filename != '':
                if allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else 'pdf'
                    tipo_archivo = 'imagen' if ext in ['png', 'jpg', 'jpeg', 'webp'] else 'pdf'
                    
                    unique_filename = f"cog_{carpeta_id}_{uuid.uuid4().hex[:10]}.{ext}"
                    base_dir = os.path.dirname(os.path.abspath(__file__))
                    upload_dir = os.path.join(base_dir, 'static', 'uploads', 'estimulacion')
                    os.makedirs(upload_dir, exist_ok=True)
                    
                    filepath = os.path.join(upload_dir, unique_filename)
                    file.save(filepath)
                    archivo_url = f"/static/uploads/estimulacion/{unique_filename}"
                else:
                    return jsonify({'error': 'Tipo de archivo no permitido. Sube PDF, imagen o documento.'}), 400

        cursor.execute("""
            INSERT INTO cat_ejercicios_cognitivos (carpeta_id, psicologo_id, orden, titulo, instrucciones, tipo_archivo, archivo_url, enlace_externo)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (carpeta_id, user_id, siguiente_orden, titulo, instrucciones, tipo_archivo, archivo_url, enlace_externo))
        db.commit()
        return jsonify({'success': 'Ejercicio añadido correctamente.', 'id': cursor.lastrowid}), 201

@estimulacion_bp.route('/api/estimulacion/ejercicios/<int:ejercicio_id>', methods=['PUT', 'DELETE'])
@login_required
def api_ejercicio_detail(ejercicio_id):
    db = get_db()
    cursor = db.cursor()

    if request.method == 'PUT':
        data = request.form if request.form else (request.get_json() or {})
        titulo = data.get('titulo', '').strip()
        instrucciones = data.get('instrucciones', '').strip()
        enlace_externo = data.get('enlace_externo', '').strip()
        orden = data.get('orden')

        cursor.execute("SELECT * FROM cat_ejercicios_cognitivos WHERE id = ?", (ejercicio_id,))
        current_ex = cursor.fetchone()
        if not current_ex:
            return jsonify({'error': 'Ficha o ejercicio no encontrado.'}), 404

        archivo_url = current_ex['archivo_url']
        tipo_archivo = current_ex['tipo_archivo']

        if 'archivo' in request.files:
            file = request.files['archivo']
            if file and file.filename != '':
                if allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else 'pdf'
                    tipo_archivo = 'imagen' if ext in ['png', 'jpg', 'jpeg', 'webp'] else 'pdf'
                    
                    unique_filename = f"cog_{current_ex['carpeta_id']}_{uuid.uuid4().hex[:10]}.{ext}"
                    base_dir = os.path.dirname(os.path.abspath(__file__))
                    upload_dir = os.path.join(base_dir, 'static', 'uploads', 'estimulacion')
                    os.makedirs(upload_dir, exist_ok=True)
                    
                    filepath = os.path.join(upload_dir, unique_filename)
                    file.save(filepath)
                    archivo_url = f"/static/uploads/estimulacion/{unique_filename}"
                else:
                    return jsonify({'error': 'Tipo de archivo no permitido. Sube PDF, imagen o documento.'}), 400

        try:
            orden_val = int(orden) if orden is not None and str(orden).strip() != '' else current_ex['orden']
        except Exception:
            orden_val = current_ex['orden']

        cursor.execute("""
            UPDATE cat_ejercicios_cognitivos
            SET titulo = COALESCE(NULLIF(?, ''), titulo),
                orden = ?,
                instrucciones = ?,
                enlace_externo = ?,
                archivo_url = ?,
                tipo_archivo = ?
            WHERE id = ?
        """, (titulo, orden_val, instrucciones, enlace_externo, archivo_url, tipo_archivo, ejercicio_id))
        db.commit()
        return jsonify({'success': 'Ficha de ejercicio actualizada exitosamente.'})

    elif request.method == 'DELETE':
        cursor.execute("SELECT archivo_url FROM cat_ejercicios_cognitivos WHERE id = ?", (ejercicio_id,))
        row = cursor.fetchone()
        if row and row['archivo_url'] and row['archivo_url'].startswith('/static/uploads/estimulacion/'):
            try:
                base_dir = os.path.dirname(os.path.abspath(__file__))
                rel_path = row['archivo_url'].lstrip('/')
                full_path = os.path.join(base_dir, rel_path.replace('/', os.sep))
                if os.path.exists(full_path):
                    os.remove(full_path)
            except Exception as e:
                print("Aviso al eliminar archivo físico de ejercicio cognitivo:", e)

        cursor.execute("DELETE FROM cat_ejercicios_cognitivos WHERE id = ?", (ejercicio_id,))
        db.commit()
        return jsonify({'success': 'Ejercicio eliminado exitosamente.'})

# =======================================================
# ASIGNACIÓN Y SEGUIMIENTO DEL PACIENTE
# =======================================================

@estimulacion_bp.route('/api/pacientes/<int:patient_id>/estimulacion', methods=['GET', 'POST'])
@login_required
def api_paciente_estimulacion(patient_id):
    db = get_db()
    cursor = db.cursor()
    user_id = session.get('user_id')
    ensure_estimulacion_tables(db)

    if request.method == 'GET':
        cursor.execute("""
            SELECT pec.*, c.titulo as carpeta_titulo, c.color as carpeta_color, c.icono as carpeta_icono,
                   (SELECT COUNT(*) FROM cat_ejercicios_cognitivos WHERE carpeta_id = pec.carpeta_id) as total_ejercicios,
                   (SELECT COUNT(*) FROM registro_estimulacion_cognitiva WHERE asignacion_id = pec.id AND completado = 1) as completados
            FROM paciente_estimulacion_cognitiva pec
            LEFT JOIN cat_carpetas_cognitivas c ON pec.carpeta_id = c.id
            WHERE pec.paciente_id = ?
            ORDER BY pec.id DESC
        """, (patient_id,))
        asigs = [dict(r) for r in cursor.fetchall()]
        return jsonify({'asignaciones': asigs})

    elif request.method == 'POST':
        data = request.get_json() or {}
        carpeta_id = data.get('carpeta_id')
        if not carpeta_id:
            return jsonify({'error': 'Debes seleccionar una carpeta de estimulación.'}), 400

        frecuencia = data.get('frecuencia', 'dias_semana')
        dias_semana = data.get('dias_semana', [1, 3, 5])
        hora = data.get('hora_recordatorio', '09:00').strip()
        modo_rotacion = 'secuencial'
        al_terminar = 'pausar'

        cursor.execute("SELECT id, token_acceso FROM paciente_estimulacion_cognitiva WHERE paciente_id = ?", (patient_id,))
        existing = cursor.fetchone()

        if existing:
            token_acceso = existing['token_acceso'] or secrets.token_urlsafe(24)
            cursor.execute("""
                UPDATE paciente_estimulacion_cognitiva
                SET psicologo_id = ?, carpeta_id = ?, frecuencia = ?, dias_semana_json = ?,
                    hora_recordatorio = ?, modo_rotacion = ?, al_terminar = ?, token_acceso = ?, activa = 1
                WHERE id = ?
            """, (user_id, carpeta_id, frecuencia, json.dumps(dias_semana), hora, modo_rotacion, al_terminar, token_acceso, existing['id']))
            asig_id = existing['id']
        else:
            token_acceso = secrets.token_urlsafe(24)
            cursor.execute("""
                INSERT INTO paciente_estimulacion_cognitiva (
                    paciente_id, psicologo_id, carpeta_id, frecuencia, dias_semana_json,
                    hora_recordatorio, modo_rotacion, al_terminar, token_acceso, activa
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """, (patient_id, user_id, carpeta_id, frecuencia, json.dumps(dias_semana), hora, modo_rotacion, al_terminar, token_acceso))
            asig_id = cursor.lastrowid
        db.commit()

        # También registrar en modulos_terapeuticos_paciente
        cursor.execute("""
            INSERT OR REPLACE INTO modulos_terapeuticos_paciente (paciente_id, modulo_clave, activo)
            VALUES (?, 'estimulacion_cognitiva', 1)
        """, (patient_id,))
        db.commit()

        return jsonify({'success': 'Estimulación Cognitiva asignada correctamente.', 'id': asig_id}), 201

@estimulacion_bp.route('/api/pacientes/<int:patient_id>/estimulacion/<int:asig_id>/toggle', methods=['POST'])
@login_required
def api_toggle_estimulacion(patient_id, asig_id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT activa FROM paciente_estimulacion_cognitiva WHERE id = ? AND paciente_id = ?", (asig_id, patient_id))
    row = cursor.fetchone()
    if not row:
        return jsonify({'error': 'Asignación no encontrada.'}), 404

    nuevo_estado = 0 if row['activa'] == 1 else 1
    cursor.execute("UPDATE paciente_estimulacion_cognitiva SET activa = ? WHERE id = ?", (nuevo_estado, asig_id))
    cursor.execute("UPDATE modulos_terapeuticos_paciente SET activo = ? WHERE paciente_id = ? AND modulo_clave = 'estimulacion_cognitiva'", (nuevo_estado, patient_id))
    db.commit()
    return jsonify({'success': 'Estado actualizado.', 'activa': nuevo_estado})

@estimulacion_bp.route('/api/pacientes/<int:patient_id>/estimulacion/enviar-hoy', methods=['POST'])
@login_required
def api_enviar_estimulacion_hoy(patient_id):
    """
    Fuerza el envío manual inmediato del ejercicio correspondiente de estimulación cognitiva
    por WhatsApp al paciente seleccionado.
    """
    db = get_db()
    try:
        count = auto_send_cognitive_reminders(db, target_patient_id=patient_id, force=True)
        if count and count > 0:
            return jsonify({'success': True, 'message': '¡Ejercicio de Estimulación Cognitiva enviado con éxito por WhatsApp!'})
        else:
            return jsonify({'success': False, 'message': 'No se pudo enviar el ejercicio. Verifica que el paciente tenga una asignación activa con ejercicios disponibles y teléfono celular válido.'}), 400
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error al enviar ejercicio: {str(e)}'}), 500

@estimulacion_bp.route('/api/pacientes/<int:patient_id>/estimulacion/historial', methods=['GET'])
@login_required
def api_historial_estimulacion(patient_id):
    try:
        db = get_db()
        ensure_estimulacion_tables(db)
        cursor = db.cursor()
        cursor.execute("""
            SELECT r.*, e.titulo as ejercicio_titulo, e.tipo_archivo, e.archivo_url, c.titulo as carpeta_titulo
            FROM registro_estimulacion_cognitiva r
            LEFT JOIN cat_ejercicios_cognitivos e ON r.ejercicio_id = e.id
            LEFT JOIN cat_carpetas_cognitivas c ON e.carpeta_id = c.id
            WHERE r.paciente_id = ?
            ORDER BY r.id DESC
        """, (patient_id,))
        rows = [dict(r) for r in cursor.fetchall()]
        return jsonify({'historial': rows})
    except Exception as e:
        print(f"Error en api_historial_estimulacion: {e}")
        return jsonify({'historial': [], 'error': str(e)}), 500

@estimulacion_bp.route('/api/patient/estimulacion', methods=['GET'])
def api_patient_current_estimulacion():
    patient_id = session.get('patient_id')
    if not patient_id:
        return jsonify({'error': 'No autenticado'}), 401
        
    db = get_db()
    cursor = db.cursor()
    ensure_estimulacion_tables(db)

    cursor.execute("""
        SELECT p.*, c.titulo as carpeta_titulo, c.descripcion as carpeta_descripcion, c.color as carpeta_color, c.icono as carpeta_icono
        FROM paciente_estimulacion_cognitiva p
        JOIN cat_carpetas_cognitivas c ON p.carpeta_id = c.id
        WHERE p.paciente_id = ? AND p.activa = 1
        ORDER BY p.id DESC LIMIT 1
    """, (patient_id,))
    asig = cursor.fetchone()
    if not asig:
        return jsonify({'activa': False, 'mensaje': 'No tienes un programa de estimulación cognitiva activo en este momento.'})

    # Obtener última entrega registrada
    cursor.execute("""
        SELECT r.*, e.titulo as ejercicio_titulo, e.instrucciones, e.tipo_archivo, e.archivo_url, e.enlace_externo
        FROM registro_estimulacion_cognitiva r
        JOIN cat_ejercicios_cognitivos e ON r.ejercicio_id = e.id
        WHERE r.asignacion_id = ?
        ORDER BY r.id DESC LIMIT 1
    """, (asig['id'],))
    ultima_entrega = cursor.fetchone()

    # Historial completo del paciente
    cursor.execute("""
        SELECT r.*, e.titulo as ejercicio_titulo
        FROM registro_estimulacion_cognitiva r
        JOIN cat_ejercicios_cognitivos e ON r.ejercicio_id = e.id
        WHERE r.paciente_id = ?
        ORDER BY r.id DESC
    """, (patient_id,))
    historial = [dict(r) for r in cursor.fetchall()]

    return jsonify({
        'activa': True,
        'asignacion': dict(asig),
        'ultima_entrega': dict(ultima_entrega) if ultima_entrega else None,
        'historial': historial
    })

@estimulacion_bp.route('/api/patient/estimulacion/completar', methods=['POST'])
def api_patient_estimulacion_completar():
    patient_id = session.get('patient_id')
    if not patient_id:
        return jsonify({'error': 'No autenticado'}), 401

    db = get_db()
    cursor = db.cursor()
    ensure_estimulacion_tables(db)

    if request.is_json:
        data = request.get_json() or {}
        registro_id = data.get('registro_id')
        dificultad = data.get('dificultad', 'normal')
        tiempo_minutos = data.get('tiempo_minutos')
        observaciones = (data.get('observaciones') or '').strip()
    else:
        registro_id = request.form.get('registro_id')
        dificultad = request.form.get('dificultad', 'normal')
        tiempo = request.form.get('tiempo_minutos', '')
        tiempo_minutos = int(tiempo) if tiempo and tiempo.isdigit() else None
        observaciones = (request.form.get('observaciones') or '').strip()

    if not registro_id:
        return jsonify({'error': 'ID de registro no especificado.'}), 400

    cursor.execute("""
        SELECT r.id, r.paciente_id, r.ejercicio_id, e.titulo as ejercicio_titulo, p.nombres, p.apellidos, p.psicologo_id
        FROM registro_estimulacion_cognitiva r
        JOIN cat_ejercicios_cognitivos e ON r.ejercicio_id = e.id
        JOIN pacientes p ON r.paciente_id = p.id
        WHERE r.id = ? AND r.paciente_id = ?
    """, (registro_id, patient_id))
    row = cursor.fetchone()
    if not row:
        return jsonify({'error': 'Registro no encontrado o no pertenece a este consultante.'}), 404

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
        UPDATE registro_estimulacion_cognitiva
        SET completado = 1,
            descargado = 1,
            dificultad = ?,
            tiempo_minutos = ?,
            observaciones = ?,
            fecha_completado = ?
        WHERE id = ?
    """, (dificultad, tiempo_minutos, observaciones, now_str, row['id']))
    db.commit()

    psic_id = row['psicologo_id'] or 1
    pac_nombre = f"{row['nombres']} {row['apellidos']}"
    notif_msg = f"El consultante {pac_nombre} ha completado el ejercicio: '{row['ejercicio_titulo']}' (Dificultad: {dificultad})."
    cursor.execute("""
        INSERT INTO notificaciones (user_id, tipo, titulo, mensaje, fecha, leida, link)
        VALUES (?, 'herramienta_terapeutica', '🧠 Ejercicio Cognitivo Realizado', ?, ?, 0, '/#pacientes')
    """, (psic_id, notif_msg, now_str))
    db.commit()

    return jsonify({'success': 'Ejercicio marcado como realizado con éxito.'})

# =======================================================
# PORTAL DEL CONSULTANTE (ACCESO POR TOKEN)
# =======================================================

@estimulacion_bp.route('/portal/estimulacion/<token>')
def portal_estimulacion(token):
    db = get_db()
    cursor = db.cursor()
    ensure_estimulacion_tables(db)

    cursor.execute("""
        SELECT r.*, e.titulo as ejercicio_titulo, e.instrucciones, e.tipo_archivo, e.archivo_url, e.enlace_externo,
               c.titulo as carpeta_titulo, c.color as carpeta_color, c.icono as carpeta_icono,
               p.nombres as paciente_nombres, p.apellidos as paciente_apellidos
        FROM registro_estimulacion_cognitiva r
        JOIN cat_ejercicios_cognitivos e ON r.ejercicio_id = e.id
        JOIN cat_carpetas_cognitivas c ON e.carpeta_id = c.id
        JOIN pacientes p ON r.paciente_id = p.id
        WHERE r.token_acceso = ?
    """, (token,))
    registro = cursor.fetchone()
    if not registro:
        return render_template('portal_estimulacion.html', error="El enlace no es válido o ha expirado."), 404

    return render_template('portal_estimulacion.html', item=dict(registro), token=token)

@estimulacion_bp.route('/portal/estimulacion/<token>/descargar')
def portal_estimulacion_descargar(token):
    db = get_db()
    cursor = db.cursor()

    cursor.execute("""
        SELECT r.id, e.archivo_url, e.titulo
        FROM registro_estimulacion_cognitiva r
        JOIN cat_ejercicios_cognitivos e ON r.ejercicio_id = e.id
        WHERE r.token_acceso = ?
    """, (token,))
    row = cursor.fetchone()
    if not row or not row['archivo_url']:
        return "Archivo no encontrado.", 404

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("UPDATE registro_estimulacion_cognitiva SET descargado = 1, fecha_descarga = ? WHERE id = ?", (now_str, row['id']))
    db.commit()

    base_dir = os.path.dirname(os.path.abspath(__file__))
    rel_path = row['archivo_url'].lstrip('/')
    full_path = os.path.join(base_dir, rel_path.replace('/', os.sep))

    if not os.path.exists(full_path):
        return "El archivo físico no se encuentra en el servidor.", 404

    directory = os.path.dirname(full_path)
    filename = os.path.basename(full_path)
    return send_from_directory(directory, filename, as_attachment=True)

@estimulacion_bp.route('/portal/estimulacion/<token>/completar', methods=['POST'])
def portal_estimulacion_completar(token):
    db = get_db()
    cursor = db.cursor()

    cursor.execute("""
        SELECT r.id, r.paciente_id, r.ejercicio_id, e.titulo as ejercicio_titulo, p.nombres, p.apellidos, p.psicologo_id
        FROM registro_estimulacion_cognitiva r
        JOIN cat_ejercicios_cognitivos e ON r.ejercicio_id = e.id
        JOIN pacientes p ON r.paciente_id = p.id
        WHERE r.token_acceso = ?
    """, (token,))
    row = cursor.fetchone()
    if not row:
        return jsonify({'error': 'Registro no encontrado.'}), 404

    dificultad = request.form.get('dificultad', 'normal')
    tiempo = request.form.get('tiempo_minutos', '')
    tiempo_minutos = int(tiempo) if tiempo and tiempo.isdigit() else None
    observaciones = request.form.get('observaciones', '').strip()

    archivo_respuesta_url = None
    if 'foto_respuesta' in request.files:
        file = request.files['foto_respuesta']
        if file and file.filename != '':
            if allowed_file(file.filename):
                filename = secure_filename(file.filename)
                ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else 'jpg'
                unique_filename = f"resp_{row['id']}_{uuid.uuid4().hex[:8]}.{ext}"
                base_dir = os.path.dirname(os.path.abspath(__file__))
                upload_dir = os.path.join(base_dir, 'static', 'uploads', 'estimulacion_respuestas')
                os.makedirs(upload_dir, exist_ok=True)
                filepath = os.path.join(upload_dir, unique_filename)
                file.save(filepath)
                archivo_respuesta_url = f"/static/uploads/estimulacion_respuestas/{unique_filename}"

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
        UPDATE registro_estimulacion_cognitiva
        SET completado = 1,
            descargado = 1,
            dificultad = ?,
            tiempo_minutos = ?,
            observaciones = ?,
            archivo_respuesta_url = COALESCE(?, archivo_respuesta_url),
            fecha_completado = ?
        WHERE id = ?
    """, (dificultad, tiempo_minutos, observaciones, archivo_respuesta_url, now_str, row['id']))
    db.commit()

    psic_id = row['psicologo_id'] or 1
    pac_nombre = f"{row['nombres']} {row['apellidos']}"
    notif_msg = f"El consultante {pac_nombre} ha completado el ejercicio de estimulación: '{row['ejercicio_titulo']}' (Dificultad reportada: {dificultad})."
    cursor.execute("""
        INSERT INTO notificaciones (user_id, tipo, titulo, mensaje, fecha, leida, link)
        VALUES (?, 'herramienta_terapeutica', '🧠 Ejercicio Cognitivo Completado', ?, ?, 0, '/#pacientes')
    """, (psic_id, notif_msg, now_str))
    db.commit()

    return jsonify({'success': '¡Felicitaciones! Has completado tu ejercicio con éxito.'})

# =======================================================
# MOTOR AUTOMATIZADO DE ENVÍOS (CRON / SEGUNDO PLANO)
# =======================================================

def auto_send_cognitive_reminders(db, target_patient_id=None, force=False):
    """
    Evalúa las asignaciones activas de estimulación cognitiva.
    Si hoy coincide con los días de la semana y la hora coincide con hora_recordatorio:
    Envía el siguiente ejercicio secuencial por WhatsApp. Al culminar el último ejercicio de la carpeta,
    se pausa automáticamente la asignación y se notifica al terapeuta.
    """
    cursor = db.cursor()
    ensure_estimulacion_tables(db)
    enviados_count = 0

    try:
        try:
            import zoneinfo
            tz = zoneinfo.ZoneInfo("America/Caracas")
            now_dt = datetime.now(tz)
        except Exception:
            tz = timezone(timedelta(hours=-4))
            now_dt = datetime.now(tz)

        now_time_str = now_dt.strftime("%H:%M")
        today_str = now_dt.strftime("%Y-%m-%d")
        now_full_str = now_dt.strftime("%Y-%m-%d %H:%M:%S")
        weekday = now_dt.isoweekday() # 1=Lunes, 7=Domingo

        where_clauses = ["pec.activa = 1"]
        params = []
        if target_patient_id:
            where_clauses.append("pec.paciente_id = ?")
            params.append(target_patient_id)

        cursor.execute(f"""
            SELECT pec.*, p.nombres, p.apellidos, p.telefono, COALESCE(c.titulo, 'Estimulación Cognitiva') as carpeta_titulo
            FROM paciente_estimulacion_cognitiva pec
            JOIN pacientes p ON pec.paciente_id = p.id
            LEFT JOIN cat_carpetas_cognitivas c ON pec.carpeta_id = c.id
            WHERE {' AND '.join(where_clauses)}
        """, params)
        asignaciones = cursor.fetchall()

        for asig_raw in asignaciones:
            try:
                asig = dict(asig_raw)
                # 1. Verificar si corresponde hoy según los días de la semana (1=Lunes .. 7=Domingo)
                dias_semana = []
                try:
                    raw_dias = json.loads(asig['dias_semana_json'] or '[]')
                    if isinstance(raw_dias, list):
                        dias_semana = [int(d) for d in raw_dias if str(d).isdigit()]
                    elif isinstance(raw_dias, int):
                        dias_semana = [raw_dias]
                except Exception:
                    dias_semana = [1, 3, 5]

                if not force and dias_semana and weekday not in dias_semana:
                    continue

                # Verificar horario programado (enviar cuando la hora actual >= hora_recordatorio)
                hora_str = (asig.get('hora_recordatorio') or '09:00').strip()
                try:
                    h_rec, m_rec = map(int, hora_str.split(':')[:2])
                except Exception:
                    h_rec, m_rec = 9, 0

                curr_total_mins = now_dt.hour * 60 + now_dt.minute
                target_total_mins = h_rec * 60 + m_rec

                if not force:
                    # Aún no es la hora programada
                    if curr_total_mins < target_total_mins:
                        continue
                    # Si pasaron más de 8 horas después de la hora programada, no enviar para evitar spam tardío
                    if curr_total_mins > (target_total_mins + 480):
                        continue

                # 2. Verificar si ya se envió un ejercicio hoy para esta asignación
                if not force:
                    cursor.execute("""
                        SELECT id FROM registro_estimulacion_cognitiva
                        WHERE asignacion_id = ? AND fecha_envio = ?
                    """, (asig['id'], today_str))
                    reg_hoy = cursor.fetchone()
                    if reg_hoy:
                        # Si existe registro de hoy, verificar si el WhatsApp se envió efectivamente
                        first_name_check = asig['nombres'].split()[0] if asig['nombres'] else 'Consultante'
                        cursor.execute("""
                            SELECT id FROM notificaciones 
                            WHERE user_id = ? AND tipo = 'estimulacion_wa' AND fecha LIKE ? AND mensaje LIKE ?
                        """, (asig['psicologo_id'] or 1, f"{today_str}%", f"%{first_name_check}%"))
                        if cursor.fetchone():
                            continue # Ya enviado y confirmado hoy con éxito
                        else:
                            # Fila fallida previa sin entrega de WhatsApp: eliminarla para permitir reintento
                            cursor.execute("DELETE FROM registro_estimulacion_cognitiva WHERE id = ?", (reg_hoy['id'],))
                            db.commit()

                # 3. Obtener ejercicios de la carpeta ordenados secuencialmente
                cursor.execute("""
                    SELECT id, orden, titulo, instrucciones, tipo_archivo
                    FROM cat_ejercicios_cognitivos
                    WHERE carpeta_id = ?
                    ORDER BY orden ASC, id ASC
                """, (asig['carpeta_id'],))
                ejercicios = cursor.fetchall()

                if not ejercicios:
                    print(f"[COGNITIVE-REMINDERS] Carpeta {asig['carpeta_id']} sin ejercicios para paciente {asig['paciente_id']}")
                    continue

                ultimo_id = asig['ultimo_ejercicio_id']
                siguiente_ejercicio = None
                es_ultimo_ejercicio = False

                if not ultimo_id:
                    siguiente_ejercicio = ejercicios[0]
                    if len(ejercicios) == 1:
                        es_ultimo_ejercicio = True
                else:
                    found = False
                    for idx, ej in enumerate(ejercicios):
                        if ej['id'] == ultimo_id:
                            if idx + 1 < len(ejercicios):
                                siguiente_ejercicio = ejercicios[idx + 1]
                                if idx + 1 == len(ejercicios) - 1:
                                    es_ultimo_ejercicio = True
                            else:
                                siguiente_ejercicio = None
                            found = True
                            break
                    if not found:
                        siguiente_ejercicio = ejercicios[0]

                if not siguiente_ejercicio:
                    # Ya no quedan ejercicios por enviar: pausar asignación
                    cursor.execute("UPDATE paciente_estimulacion_cognitiva SET activa = 0, fecha_culminacion = ? WHERE id = ?", (now_full_str, asig['id']))
                    db.commit()
                    continue

                # 4. Generar token seguro y mensaje de WhatsApp
                token_entrega = secrets.token_urlsafe(32)
                app_url = get_public_base_url()
                link = f"{app_url}/portal/estimulacion/{token_entrega}"
                first_name = asig['nombres'].split()[0] if asig['nombres'] else 'Consultante'
                psic_id = asig['psicologo_id'] or 1

                from routes_herramientas import clean_phone_number
                raw_phone = asig['telefono'] or ''
                clean_phone = clean_phone_number(raw_phone)
                if clean_phone and not clean_phone.startswith('58') and len(clean_phone) == 10:
                    clean_phone = '58' + clean_phone

                msg_wa = (
                    f"Hola *{first_name}* 👋🧠\n\n"
                    f"Te comparto tu ejercicio de Estimulación Cognitiva de hoy:\n"
                    f"*{siguiente_ejercicio['titulo']}* ({asig['carpeta_titulo']})\n\n"
                    f"Haz clic en el siguiente enlace para descargarlo y completarlo:\n"
                    f"{link}\n\n"
                    f"_Al terminarlo, presiona 'Marcar como realizado' en ese mismo enlace._"
                )

                # 5. Enviar por WhatsApp primero; sólo registrar en base de datos si la entrega es exitosa
                send_ok = False
                if clean_phone:
                    from routes_notificaciones import make_wa_http_request
                    try:
                        res = make_wa_http_request(
                            'POST', '/send',
                            json_data={'phone': clean_phone, 'text': msg_wa, 'user_id': psic_id},
                            timeout=25, user_id=psic_id
                        )
                        if res and res.status_code == 200:
                            send_ok = True
                            print(f"[COGNITIVE-REMINDERS] WhatsApp enviado con éxito a {clean_phone} para {first_name}")
                        else:
                            err_text = getattr(res, 'text', '')
                            print(f"[COGNITIVE-REMINDERS] Error enviando WhatsApp a {clean_phone} (status {getattr(res, 'status_code', None)}): {err_text}")
                    except Exception as ex_wa:
                        print(f"[COGNITIVE-REMINDERS] Excepción enviando WhatsApp a {clean_phone}: {ex_wa}")
                else:
                    # Si no tiene teléfono configurado, registrar en portal
                    send_ok = True

                if not send_ok:
                    continue

                # 6. Registrar entrega y actualizar estado en base de datos
                cursor.execute("""
                    INSERT INTO registro_estimulacion_cognitiva (
                        asignacion_id, paciente_id, ejercicio_id, token_acceso, fecha_envio, hora_envio
                    ) VALUES (?, ?, ?, ?, ?, ?)
                """, (asig['id'], asig['paciente_id'], siguiente_ejercicio['id'], token_entrega, today_str, now_time_str))

                if es_ultimo_ejercicio:
                    cursor.execute("""
                        UPDATE paciente_estimulacion_cognitiva
                        SET ultimo_ejercicio_id = ?, activa = 0, fecha_culminacion = ?
                        WHERE id = ?
                    """, (siguiente_ejercicio['id'], now_full_str, asig['id']))
                    
                    notif_fin = f"🏁 El consultante {asig['nombres']} {asig['apellidos']} ha recibido la última ficha de la carpeta '{asig['carpeta_titulo']}'. El ciclo se ha pausado automáticamente."
                    cursor.execute("""
                        INSERT INTO notificaciones (user_id, tipo, titulo, mensaje, fecha, leida, link)
                        VALUES (?, 'herramienta_terapeutica', '🏁 Carpeta Cognitiva Culminada', ?, ?, 0, '/#pacientes')
                    """, (psic_id, notif_fin, now_full_str))
                else:
                    cursor.execute("""
                        UPDATE paciente_estimulacion_cognitiva
                        SET ultimo_ejercicio_id = ?
                        WHERE id = ?
                    """, (siguiente_ejercicio['id'], asig['id']))

                if clean_phone:
                    cursor.execute("""
                        INSERT INTO notificaciones (user_id, tipo, titulo, mensaje, fecha, leida, link)
                        VALUES (?, 'estimulacion_wa', '🧠 Ejercicio Cognitivo Enviado', ?, ?, 1, '')
                    """, (psic_id, f"Ficha '{siguiente_ejercicio['titulo']}' enviada a {first_name}", now_full_str))
                
                db.commit()
                enviados_count += 1
            except Exception as e_item:
                print(f"[COGNITIVE-REMINDERS] Error procesando asignación {asig['id']}: {e_item}")

        return enviados_count
    except Exception as e:
        print("Error en auto_send_cognitive_reminders:", e)
        return enviados_count
