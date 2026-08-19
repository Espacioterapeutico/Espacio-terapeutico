# -*- coding: utf-8 -*-
"""
Módulo de Pizarra Terapéutica (routes_pizarra.py)
Encapsula el registro de pensamientos/estado de ánimo del consultante, la sincronización en Firebase,
notificaciones Push/WebPush y las respuestas y consulta del psicólogo.
"""

import os
import sqlite3
from datetime import datetime
from functools import wraps
from flask import Blueprint, request, jsonify, session, g

pizarra_bp = Blueprint('pizarra', __name__)

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

def _ensure_pizarra_columns(cursor):
    try:
        cursor.execute("PRAGMA table_info(pizarra_terapeutica)")
        cols = [r[1] for r in cursor.fetchall()]
        if cols:
            if 'archivo_adjunto' not in cols:
                cursor.execute("ALTER TABLE pizarra_terapeutica ADD COLUMN archivo_adjunto TEXT")
            if 'estado_animo' not in cols:
                cursor.execute("ALTER TABLE pizarra_terapeutica ADD COLUMN estado_animo TEXT")
            if 'comentario_animo' not in cols:
                cursor.execute("ALTER TABLE pizarra_terapeutica ADD COLUMN comentario_animo TEXT")
            if 'emoji_animo' not in cols:
                cursor.execute("ALTER TABLE pizarra_terapeutica ADD COLUMN emoji_animo TEXT")
            if 'respuesta_psicologo' not in cols:
                cursor.execute("ALTER TABLE pizarra_terapeutica ADD COLUMN respuesta_psicologo TEXT")
            if 'fecha_respuesta' not in cols:
                cursor.execute("ALTER TABLE pizarra_terapeutica ADD COLUMN fecha_respuesta TEXT")
    except Exception as _e:
        print("Error al asegurar columnas de pizarra:", _e)

@pizarra_bp.route('/api/patient/pizarra', methods=['GET', 'POST'])
@patient_login_required
def patient_pizarra():
    patient_id = session['patient_id']
    db = get_db()
    cursor = db.cursor()
    _ensure_pizarra_columns(cursor)
    
    if request.method == 'POST':
        data = request.json or {}
        contenido = data.get('contenido', '').strip()
        archivo_adjunto = data.get('archivo_adjunto', None)
        estado_animo = data.get('estado_animo', '').strip()
        comentario_animo = data.get('comentario_animo', '').strip()
        emoji_animo = data.get('emoji_animo', '').strip()
        
        if estado_animo and not contenido:
            contenido = f"Estado de ánimo: {emoji_animo} {estado_animo}"
            if comentario_animo:
                contenido += f" — \"{comentario_animo}\""
        
        if not contenido and not archivo_adjunto:
            return jsonify({'error': 'El contenido o archivo adjunto es requerido.'}), 400
            
        fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        try:
            cursor.execute("""
                INSERT INTO pizarra_terapeutica (paciente_id, fecha, contenido, archivo_adjunto, estado_animo, comentario_animo, emoji_animo)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (patient_id, fecha_actual, contenido, archivo_adjunto, estado_animo, comentario_animo, emoji_animo))
            
            cursor.execute("SELECT nombres, apellidos, psicologo_id FROM pacientes WHERE id = ?", (patient_id,))
            pac = cursor.fetchone()
            pac_nombre = f"{pac['nombres']} {pac['apellidos']}".strip() if pac else "Consultante"
            psicologo_id = (pac['psicologo_id'] if pac and pac['psicologo_id'] else 1)
            
            titulo_notif = "Registro de Estado de Ánimo" if estado_animo else "Actualización de Pizarra"
            mensaje_notif = f"{pac_nombre} registró su estado de ánimo: {emoji_animo} {estado_animo}." if estado_animo else f"{pac_nombre} escribió una reflexión en su pizarra terapéutica."

            cursor.execute("""
                INSERT INTO notificaciones (user_id, tipo, titulo, mensaje, fecha, leida, link)
                VALUES (?, ?, ?, ?, ?, 0, ?)
            """, (psicologo_id, 'pizarra', titulo_notif, mensaje_notif, fecha_actual, 'pizarra-visual'))
            
            db.commit()

            # Enviar notificación WebPush al psicólogo
            try:
                from app import send_webpush_notification
                send_webpush_notification(
                    user_id=psicologo_id,
                    title=titulo_notif,
                    body=mensaje_notif,
                    url="/?view=pizarra-visual"
                )
            except Exception as wp_ex:
                print("Error al enviar WebPush de actualización de pizarra:", wp_ex)
            
            try:
                import requests
                from app import FIREBASE_DB_URL
                firebase_payload = {
                    'fecha': fecha_actual,
                    'contenido': contenido,
                    'archivo_adjunto': archivo_adjunto,
                    'estado_animo': estado_animo,
                    'comentario_animo': comentario_animo,
                    'emoji_animo': emoji_animo
                }
                requests.post(f"{FIREBASE_DB_URL}/pizarra_terapeutica/{patient_id}.json", json=firebase_payload, timeout=2.0)
            except Exception as fb_ex:
                print("Error al sincronizar pizarra con Firebase:", fb_ex)
            
            return jsonify({'success': 'Actualización agregada a tu pizarra con éxito.', 'fecha': fecha_actual})
        except Exception as e:
            return jsonify({'error': f'Error al guardar en pizarra: {str(e)}'}), 500
            
    elif request.method == 'GET':
        try:
            cursor.execute("""
                SELECT id, fecha, contenido, archivo_adjunto, estado_animo, comentario_animo, emoji_animo, respuesta_psicologo, fecha_respuesta FROM pizarra_terapeutica
                WHERE paciente_id = ?
                ORDER BY fecha DESC
            """, (patient_id,))
            rows = cursor.fetchall()
            updates = []
            for r in rows:
                r_keys = r.keys() if hasattr(r, 'keys') else []
                updates.append({
                    'id': r['id'],
                    'fecha': r['fecha'],
                    'contenido': r['contenido'],
                    'archivo_adjunto': r['archivo_adjunto'] if 'archivo_adjunto' in r_keys else None,
                    'estado_animo': r['estado_animo'] if 'estado_animo' in r_keys else None,
                    'comentario_animo': r['comentario_animo'] if 'comentario_animo' in r_keys else None,
                    'emoji_animo': r['emoji_animo'] if 'emoji_animo' in r_keys else None,
                    'respuesta_psicologo': r['respuesta_psicologo'] if 'respuesta_psicologo' in r_keys else None,
                    'fecha_respuesta': r['fecha_respuesta'] if 'fecha_respuesta' in r_keys else None
                })
            return jsonify({'updates': updates})
        except Exception as e:
            return jsonify({'error': f'Error al obtener pizarra: {str(e)}'}), 500

@pizarra_bp.route('/api/admin/pizarra', methods=['GET'])
@login_required
def admin_pizarra():
    patient_id = request.args.get('patient_id')
    db = get_db()
    cursor = db.cursor()
    _ensure_pizarra_columns(cursor)
    psic_id = get_psicologo_id_filter()
    
    try:
        if patient_id:
            if psic_id is not None:
                cursor.execute("""
                    SELECT p.id, p.paciente_id, p.fecha, p.contenido, p.archivo_adjunto, p.estado_animo, p.comentario_animo, p.emoji_animo, p.respuesta_psicologo, p.fecha_respuesta, pac.nombres, pac.apellidos
                    FROM pizarra_terapeutica p
                    JOIN pacientes pac ON p.paciente_id = pac.id
                    WHERE p.paciente_id = ? AND pac.psicologo_id = ?
                    ORDER BY p.fecha DESC
                """, (patient_id, psic_id))
            else:
                cursor.execute("""
                    SELECT p.id, p.paciente_id, p.fecha, p.contenido, p.archivo_adjunto, p.estado_animo, p.comentario_animo, p.emoji_animo, p.respuesta_psicologo, p.fecha_respuesta, pac.nombres, pac.apellidos
                    FROM pizarra_terapeutica p
                    JOIN pacientes pac ON p.paciente_id = pac.id
                    WHERE p.paciente_id = ?
                    ORDER BY p.fecha DESC
                """, (patient_id,))
        else:
            if psic_id is not None:
                cursor.execute("""
                    SELECT p.id, p.paciente_id, p.fecha, p.contenido, p.archivo_adjunto, p.estado_animo, p.comentario_animo, p.emoji_animo, p.respuesta_psicologo, p.fecha_respuesta, pac.nombres, pac.apellidos
                    FROM pizarra_terapeutica p
                    JOIN pacientes pac ON p.paciente_id = pac.id
                    WHERE pac.psicologo_id = ?
                    ORDER BY p.fecha DESC
                """, (psic_id,))
            else:
                cursor.execute("""
                    SELECT p.id, p.paciente_id, p.fecha, p.contenido, p.archivo_adjunto, p.estado_animo, p.comentario_animo, p.emoji_animo, p.respuesta_psicologo, p.fecha_respuesta, pac.nombres, pac.apellidos
                    FROM pizarra_terapeutica p
                    JOIN pacientes pac ON p.paciente_id = pac.id
                    ORDER BY p.fecha DESC
                """)
            
        rows = cursor.fetchall()
        updates = []
        for r in rows:
            r_keys = r.keys() if hasattr(r, 'keys') else []
            updates.append({
                'id': r['id'],
                'paciente_id': r['paciente_id'],
                'fecha': r['fecha'],
                'contenido': r['contenido'],
                'archivo_adjunto': r['archivo_adjunto'] if 'archivo_adjunto' in r_keys else None,
                'estado_animo': r['estado_animo'] if 'estado_animo' in r_keys else None,
                'comentario_animo': r['comentario_animo'] if 'comentario_animo' in r_keys else None,
                'emoji_animo': r['emoji_animo'] if 'emoji_animo' in r_keys else None,
                'respuesta_psicologo': r['respuesta_psicologo'] if 'respuesta_psicologo' in r_keys else None,
                'fecha_respuesta': r['fecha_respuesta'] if 'fecha_respuesta' in r_keys else None,
                'paciente_nombre': f"{r['nombres']} {r['apellidos']}"
            })
        
        return jsonify({'updates': updates})
    except Exception as e:
        return jsonify({'error': f'Error al obtener pizarra para el administrador: {str(e)}'}), 500

@pizarra_bp.route('/api/admin/pizarra/reply', methods=['POST'])
@login_required
def admin_pizarra_reply():
    data = request.json or {}
    update_id = data.get('update_id')
    respuesta = data.get('respuesta', '').strip()
    
    if not update_id or not respuesta:
        return jsonify({'error': 'Faltan parámetros requeridos (update_id, respuesta).'}), 400
        
    db = get_db()
    cursor = db.cursor()
    _ensure_pizarra_columns(cursor)
    
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    try:
        cursor.execute("""
            UPDATE pizarra_terapeutica
            SET respuesta_psicologo = ?, fecha_respuesta = ?
            WHERE id = ?
        """, (respuesta, fecha_actual, update_id))
        
        cursor.execute("SELECT paciente_id FROM pizarra_terapeutica WHERE id = ?", (update_id,))
        row = cursor.fetchone()
        if row:
            patient_id = row['paciente_id']
            cursor.execute("""
                INSERT INTO notificaciones (user_id, tipo, titulo, mensaje, fecha, leida, link)
                VALUES (?, ?, ?, ?, ?, 0, ?)
            """, (patient_id, 'pizarra', '💬 Tu Psicólogo/a respondió en tu Pizarra Terapéutica', f'Tu psicólogo/a ha respondido a tu apunte: "{respuesta[:60]}..."', fecha_actual, 'pizarra-terapeutica'))
            
        db.commit()
        return jsonify({'success': 'Respuesta registrada con éxito.', 'fecha_respuesta': fecha_actual, 'respuesta_psicologo': respuesta})
    except Exception as e:
        return jsonify({'error': f'Error al guardar respuesta: {str(e)}'}), 500
