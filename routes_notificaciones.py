# -*- coding: utf-8 -*-
"""
Módulo de Notificaciones y Comunicaciones Push (routes_notificaciones.py)
Encapsula las notificaciones en la plataforma para psicólogos y consultantes,
suscripciones WebPush VAPID y marcado de notificaciones leídas.
"""

import os
import sqlite3
from functools import wraps
from flask import Blueprint, request, jsonify, session, g

notificaciones_bp = Blueprint('notificaciones', __name__)

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

def get_psicologo_id_filter():
    role = session.get('role')
    user_id = session.get('user_id')
    username = session.get('username', '')
    if (role in ['admin', 'superadmin']) and (username.lower() != 'pamoraro' and user_id != 1):
        return -1
    return user_id if user_id else 1

# --- RUTAS DE API DE NOTIFICACIONES Y WEBPUSH ---

@notificaciones_bp.route('/api/push/public-key', methods=['GET'])
def get_push_public_key():
    try:
        db = get_db()
        cursor = db.cursor()
        from app import get_vapid_keys
        vapid_keys = get_vapid_keys(cursor)
        return jsonify({'public_key': vapid_keys.get('vapid_public_key', '')})
    except Exception as e:
        print(f"Error fetching public key: {e}")
        return jsonify({'public_key': ''})

@notificaciones_bp.route('/api/push/subscribe', methods=['POST'])
def subscribe_push():
    data = request.json or {}
    endpoint = data.get('endpoint')
    keys = data.get('keys') or {}
    p256dh = keys.get('p256dh')
    auth = keys.get('auth')

    if not endpoint or not p256dh or not auth:
        return jsonify({'error': 'Suscripción inválida.'}), 400

    user_id = session.get('user_id')
    patient_id = session.get('patient_id')

    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO web_push_subscriptions (user_id, patient_id, endpoint, p256dh, auth)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, patient_id, endpoint, p256dh, auth))
    db.commit()
    return jsonify({'success': 'Suscrito exitosamente a notificaciones Push en segundo plano.'})

@notificaciones_bp.route('/api/admin/notifications', methods=['GET'])
@login_required
def get_admin_notifications():
    db = get_db()
    cursor = db.cursor()
    psic_id = get_psicologo_id_filter()
    try:
        if psic_id is not None:
            cursor.execute("""
                SELECT id, tipo, titulo, mensaje, fecha, leida, link
                FROM notificaciones
                WHERE tipo NOT IN ('herramienta_paciente', 'recordatorio_cita_paciente')
                  AND (user_id = ? OR (user_id IS NULL AND ? = 1)) AND leida = 0
                ORDER BY fecha DESC, id DESC LIMIT 25
            """, (psic_id, psic_id))
            rows = cursor.fetchall()
            
            cursor.execute("""
                SELECT COUNT(id) FROM notificaciones 
                WHERE tipo NOT IN ('herramienta_paciente', 'recordatorio_cita_paciente')
                  AND (user_id = ? OR (user_id IS NULL AND ? = 1)) AND leida = 0
            """, (psic_id, psic_id))
            unread_count = cursor.fetchone()[0] or 0
        else:
            cursor.execute("""
                SELECT id, tipo, titulo, mensaje, fecha, leida, link
                FROM notificaciones
                WHERE tipo NOT IN ('herramienta_paciente', 'recordatorio_cita_paciente') AND leida = 0
                ORDER BY fecha DESC, id DESC LIMIT 25
            """)
            rows = cursor.fetchall()
            cursor.execute("SELECT COUNT(id) FROM notificaciones WHERE tipo NOT IN ('herramienta_paciente', 'recordatorio_cita_paciente') AND leida = 0")
            unread_count = cursor.fetchone()[0] or 0
        
        list_notif = [{
            'id': r['id'],
            'tipo': r['tipo'],
            'titulo': r['titulo'],
            'mensaje': r['mensaje'],
            'fecha': r['fecha'],
            'leida': bool(r['leida']),
            'link': r['link']
        } for r in rows]
        
        return jsonify({
            'notifications': list_notif,
            'unread_count': unread_count
        })
    except Exception as e:
        return jsonify({'error': f'Error al obtener notificaciones: {str(e)}'}), 500

@notificaciones_bp.route('/api/admin/notifications/mark-read', methods=['POST'])
@login_required
def admin_notifications_mark_read():
    data = request.json or {}
    notification_id = data.get('notification_id')
    db = get_db()
    cursor = db.cursor()
    psic_id = get_psicologo_id_filter()
    try:
        if notification_id:
            cursor.execute("UPDATE notificaciones SET leida = 1 WHERE id = ?", (notification_id,))
        else:
            if psic_id is not None:
                cursor.execute("""
                    UPDATE notificaciones SET leida = 1 
                    WHERE tipo NOT IN ('herramienta_paciente', 'recordatorio_cita_paciente') 
                      AND (user_id = ? OR (user_id IS NULL AND ? = 1))
                """, (psic_id, psic_id))
            else:
                cursor.execute("UPDATE notificaciones SET leida = 1 WHERE tipo NOT IN ('herramienta_paciente', 'recordatorio_cita_paciente')")
        db.commit()
        return jsonify({'success': 'Notificación marcada como leída.'})
    except Exception as e:
        return jsonify({'error': f'Error al marcar notificaciones: {str(e)}'}), 500

WHATSAPP_SERVICE_URL = os.environ.get('WHATSAPP_SERVICE_URL', 'https://espacio-terapeutico-whatsapp.onrender.com')

_wa_keepalive_started = False

def _start_wa_keepalive_thread():
    global _wa_keepalive_started
    if _wa_keepalive_started:
        return
    _wa_keepalive_started = True

    def _keepalive_loop():
        import time, requests, threading
        while True:
            try:
                url = f"{WHATSAPP_SERVICE_URL.rstrip('/')}/status"
                requests.get(url, params={'user_id': '1'}, timeout=15)
            except Exception:
                pass
            time.sleep(480) # Ping cada 8 minutos para evitar que Render hiberne

    t = threading.Thread(target=_keepalive_loop, daemon=True)
    t.start()

def make_wa_http_request(method, endpoint, json_data=None, timeout=5, user_id=None):
    import requests
    _start_wa_keepalive_thread()
    url = f"{WHATSAPP_SERVICE_URL.rstrip('/')}/{endpoint.lstrip('/')}"
    
    if not user_id:
        try:
            user_id = session.get('user_id')
        except RuntimeError:
            user_id = 1
            
    if not user_id:
        user_id = 1

    headers = {'X-User-ID': str(user_id)}
    params = {'user_id': str(user_id)}
    
    if json_data is not None and isinstance(json_data, dict):
        if 'user_id' not in json_data:
            json_data['user_id'] = user_id

    try:
        s = requests.Session()
        s.trust_env = False
        if method.upper() == 'GET':
            return s.get(url, params=params, headers=headers, timeout=timeout)
        else:
            return s.post(url, json=json_data, params=params, headers=headers, timeout=timeout)
    except Exception:
        if method.upper() == 'GET':
            return requests.get(url, params=params, headers=headers, timeout=timeout)
        else:
            return requests.post(url, json=json_data, params=params, headers=headers, timeout=timeout)

@notificaciones_bp.route('/api/whatsapp/sync-session', methods=['GET', 'POST', 'DELETE'])
def handle_whatsapp_session_sync():
    """
    Sincroniza y recupera las credenciales de autenticación de Baileys (JSON) 
    en la base de datos SQLite para mantener la sesión de WhatsApp viva de forma permanente.
    """
    db = get_db()
    cursor = db.cursor()
    
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS whatsapp_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                filename TEXT NOT NULL,
                content TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, filename)
            )
        """)
        db.commit()
    except Exception as e_tbl:
        print("Aviso creando tabla whatsapp_sessions:", e_tbl)

    if request.method == 'GET':
        user_id = request.args.get('user_id')
        if not user_id:
            try:
                user_id = session.get('user_id')
            except RuntimeError:
                user_id = 1
        user_id = user_id or 1
        try:
            cursor.execute("SELECT filename, content FROM whatsapp_sessions WHERE user_id = ?", (user_id,))
            rows = cursor.fetchall()
            files_map = {row['filename']: row['content'] for row in rows}
            return jsonify({'success': True, 'user_id': user_id, 'files': files_map})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    elif request.method == 'POST':
        data = request.json or {}
        user_id = data.get('user_id')
        if not user_id:
            try:
                user_id = session.get('user_id')
            except RuntimeError:
                user_id = 1
        user_id = user_id or 1
        files = data.get('files') or {}
        if not files or not isinstance(files, dict):
            return jsonify({'error': 'No files provided'}), 400
        
        try:
            for filename, content in files.items():
                cursor.execute("""
                    INSERT INTO whatsapp_sessions (user_id, filename, content, updated_at)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(user_id, filename) DO UPDATE SET
                        content = excluded.content,
                        updated_at = CURRENT_TIMESTAMP
                """, (user_id, filename, content))
            db.commit()
            return jsonify({'success': True, 'user_id': user_id, 'saved_files': len(files)})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    elif request.method == 'DELETE':
        user_id = request.args.get('user_id')
        if not user_id:
            try:
                user_id = session.get('user_id')
            except RuntimeError:
                user_id = 1
        user_id = user_id or 1
        try:
            cursor.execute("DELETE FROM whatsapp_sessions WHERE user_id = ?", (user_id,))
            db.commit()
            return jsonify({'success': True, 'user_id': user_id, 'message': 'Sesión eliminada de la BD'})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

@notificaciones_bp.route('/api/whatsapp/status', methods=['GET'])
@login_required
def get_whatsapp_status():
    try:
        user_id = session.get('user_id')
        r = make_wa_http_request('GET', '/status', timeout=15, user_id=user_id)
        return jsonify(r.json())
    except Exception as e:
        return jsonify({'status': 'disconnected', 'error': 'Microservicio de WhatsApp no disponible', 'details': str(e)})

@notificaciones_bp.route('/api/whatsapp/qr', methods=['GET'])
@login_required
def get_whatsapp_qr():
    try:
        user_id = session.get('user_id')
        r = make_wa_http_request('GET', '/qr', timeout=25, user_id=user_id)
        return jsonify(r.json())
    except Exception as e:
        return jsonify({'status': 'disconnected', 'qr': None, 'error': str(e)})

@notificaciones_bp.route('/api/whatsapp/force-qr', methods=['POST'])
@login_required
def force_whatsapp_qr():
    try:
        user_id = session.get('user_id')
        r = make_wa_http_request('POST', '/force-qr', timeout=25, user_id=user_id)
        return jsonify(r.json())
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@notificaciones_bp.route('/api/whatsapp/send', methods=['POST'])
@login_required
def send_whatsapp_message():
    data = request.json or {}
    phone = data.get('phone')
    text = data.get('text')
    user_id = session.get('user_id')
    if not phone or not text:
        return jsonify({'error': 'Teléfono y texto son requeridos'}), 400
    try:
        r = make_wa_http_request('POST', '/send', json_data={'phone': phone, 'text': text, 'user_id': user_id}, timeout=15, user_id=user_id)
        return jsonify(r.json()), r.status_code
    except Exception as e:
        return jsonify({'error': f'Error al comunicarse con el microservicio WhatsApp: {str(e)}'}), 500

@notificaciones_bp.route('/api/whatsapp/logout', methods=['POST'])
@login_required
def logout_whatsapp():
    try:
        user_id = session.get('user_id')
        r = make_wa_http_request('POST', '/logout', timeout=10, user_id=user_id)
        return jsonify(r.json())
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@notificaciones_bp.route('/api/admin/message-templates', methods=['GET', 'POST'])
@login_required
def admin_message_templates():
    db = get_db()
    cursor = db.cursor()
    user_id = session.get('user_id')
    
    keys = ['msg_confirmacion', 'msg_confirmacion_ok', 'msg_cancelacion_ok', 'msg_recordatorio', 'msg_reagendamiento', 'msg_cierre', 'auto_reagendamiento_activo', 'msg_cumpleanos', 'auto_cumpleanos_activo', 'msg_herramientas']
    
    if request.method == 'GET':
        templates = {}
        for key in keys:
            # Buscar primero clave específica del psicólogo
            psic_key = f"{key}_{user_id}"
            cursor.execute("SELECT valor FROM configuracion WHERE clave = ?", (psic_key,))
            row = cursor.fetchone()
            if not row or not row['valor']:
                cursor.execute("SELECT valor FROM configuracion WHERE clave = ?", (key,))
                row = cursor.fetchone()
            templates[key] = row['valor'] if row else ""
        return jsonify(templates)
        
    data = request.json or {}
    try:
        for key in keys:
            if key in data:
                psic_key = f"{key}_{user_id}"
                cursor.execute("INSERT OR REPLACE INTO configuracion (clave, valor) VALUES (?, ?)", (psic_key, data[key]))
                cursor.execute("INSERT OR REPLACE INTO configuracion (clave, valor) VALUES (?, ?)", (key, data[key]))
        db.commit()
        return jsonify({'success': 'Plantillas de mensajes actualizadas con éxito.'})
    except Exception as e:
        return jsonify({'error': f'Error al actualizar plantillas: {str(e)}'}), 500

@notificaciones_bp.route('/api/admin/message-templates/render', methods=['GET'])
@login_required
def admin_message_templates_render():
    appt_id = request.args.get('appointment_id')
    template_type = request.args.get('template_type')
    user_id = session.get('user_id')
    
    if not appt_id or not template_type:
        return jsonify({'error': 'appointment_id y template_type son requeridos.'}), 400
        
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("""
            SELECT a.id, a.fecha, a.hora, a.tipo_consulta, p.nombres, p.apellidos, p.telefono
            FROM agenda_finanzas a
            JOIN pacientes p ON a.paciente_id = p.id
            WHERE a.id = ?
        """, (appt_id,))
        appt = cursor.fetchone()
        if not appt:
            return jsonify({'error': 'Cita no encontrada.'}), 404
            
        key = f"msg_{template_type}"
        psic_key = f"{key}_{user_id}"
        cursor.execute("SELECT valor FROM configuracion WHERE clave = ?", (psic_key,))
        row = cursor.fetchone()
        if not row or not row['valor']:
            cursor.execute("SELECT valor FROM configuracion WHERE clave = ?", (key,))
            row = cursor.fetchone()
        template = row['valor'] if row else ""
        
        nombre = f"{appt['nombres']} {appt['apellidos']}"
        fecha = appt['fecha']
        hora = appt['hora']
        modalidad = appt['tipo_consulta']
        
        try:
            from datetime import datetime
            date_obj = datetime.strptime(fecha, "%Y-%m-%d")
            fecha_amigable = date_obj.strftime("%d/%m/%Y")
        except Exception:
            fecha_amigable = fecha
            
        try:
            h, m = map(int, hora.split(':'))
            ampm = "PM" if h >= 12 else "AM"
            h_12 = h - 12 if h > 12 else (12 if h == 0 else h)
            hora_amigable = f"{str(h_12).zfill(2)}:{str(m).zfill(2)} {ampm}"
        except Exception:
            hora_amigable = hora
            
        link_conexion = "https://meet.google.com/abc-defg-hij"
        
        rendered_message = template.replace("{nombre}", nombre)\
                                   .replace("{fecha}", fecha_amigable)\
                                   .replace("{hora}", hora_amigable)\
                                   .replace("{modalidad}", modalidad)\
                                   .replace("{link_conexion}", link_conexion)
                                   
        phone_cleaned = "".join([c for c in appt['telefono'] or "" if c.isdigit()])
        if phone_cleaned and not phone_cleaned.startswith("58") and len(phone_cleaned) == 10:
            phone_cleaned = "58" + phone_cleaned
            
        import urllib.parse
        encoded_message = urllib.parse.quote(rendered_message)
        wa_url = f"https://wa.me/{phone_cleaned}?text={encoded_message}"
        
        return jsonify({
            'message': rendered_message,
            'phone': phone_cleaned,
            'wa_url': wa_url
        })
    except Exception as e:
        return jsonify({'error': f'Error al renderizar mensaje: {str(e)}'}), 500

@notificaciones_bp.route('/api/whatsapp/send-reminder/<int:cita_id>', methods=['POST'])
@login_required
def send_manual_whatsapp_reminder(cita_id):
    user_id = session.get('user_id')
    db = get_db()
    cursor = db.cursor()

    cursor.execute("""
        SELECT af.*, p.nombres as pat_nombres, p.apellidos as pat_apellidos, p.telefono as pat_telefono, p.pais as pat_pais
        FROM agenda_finanzas af
        JOIN pacientes p ON af.paciente_id = p.id
        WHERE af.id = ? AND p.psicologo_id = ?
    """, (cita_id, user_id))
    cita = cursor.fetchone()

    if not cita:
        return jsonify({'error': 'Cita o paciente no encontrado.'}), 404

    phone = cita['pat_telefono']
    if not phone or not phone.strip():
        return jsonify({'error': 'El paciente no tiene un número de teléfono registrado.'}), 400

    cursor.execute("SELECT nombres, apellidos FROM usuarios WHERE id = ?", (user_id,))
    psicologo = cursor.fetchone()

    cursor.execute("SELECT valor FROM configuracion WHERE clave = 'msg_recordatorio'")
    cfg_row = cursor.fetchone()
    template = cfg_row['valor'] if cfg_row and cfg_row['valor'] else None

    cita_dict = {
        'nombre': f"{cita['pat_nombres']} {cita['pat_apellidos']}",
        'fecha': cita['fecha'],
        'hora': cita['hora'],
        'modalidad': cita['tipo_consulta'] or 'Presencial'
    }
    mensaje_texto = format_whatsapp_message(template, cita_dict, cita_dict, psicologo)

    try:
        r = make_wa_http_request('POST', '/send', json_data={'phone': phone, 'text': mensaje_texto}, timeout=15)
        if r and r.status_code == 200:
            cursor.execute("UPDATE agenda_finanzas SET recordatorio_enviado_wa = 1 WHERE id = ?", (cita_id,))
            db.commit()
            return jsonify({'success': f'Recordatorio de WhatsApp enviado con éxito a {phone}.', 'phone': phone})
        else:
            res_data = r.json() if r else {}
            return jsonify({'error': res_data.get('error', 'Error al enviar mensaje por WhatsApp.')}), r.status_code if r else 500
    except Exception as e:
        return jsonify({'error': f'Error conectando con microservicio de WhatsApp: {str(e)}'}), 500



@notificaciones_bp.route('/api/whatsapp/cron-send-reminders', methods=['GET', 'POST'])
def cron_send_whatsapp_reminders():
    import os
    from flask import has_request_context, jsonify
    CRON_SECRET = os.environ.get('CRON_SECRET', 'espacioterapeutico_cron_2024')
    if has_request_context():
        provided = request.args.get('key') or request.headers.get('X-Cron-Key', '')
        if provided != CRON_SECRET:
            return jsonify({'error': 'No autorizado'}), 401

    from datetime import datetime, timedelta
    try:
        import zoneinfo
        tz = zoneinfo.ZoneInfo("America/Caracas")
        now_local = datetime.now(tz)
    except Exception:
        # Fallback a UTC - 4 horas (hora Venezuela)
        now_local = datetime.utcnow() - timedelta(hours=4)

    current_hour = now_local.hour
    # Delimitar horario de envíos automáticos: NO enviar entre las 10:00 PM (22:00) y las 7:59 AM (07:59)
    if current_hour < 8 or current_hour >= 22:
        return jsonify({
            'status': 'skipped',
            'message': f'Filtro de horario laboral activo (10:00 PM - 7:59 AM). Hora actual: {current_hour:02d}:00. Los envíos automáticos están pausados hasta las 8:00 AM.',
            'confirmaciones_enviadas': 0,
            'recordatorios_enviados': 0
        })

    today_str = now_local.strftime('%Y-%m-%d')
    tomorrow_str = (now_local + timedelta(days=1)).strftime('%Y-%m-%d')
    
    db = get_db()
    cursor = db.cursor()

    # Actualizar o asegurar plantilla con SI/NO si la existente es muy antigua o genérica
    cursor.execute("SELECT clave, valor FROM configuracion WHERE clave IN ('msg_confirmacion', 'msg_recordatorio', 'msg_reagendamiento', 'msg_cierre', 'auto_reagendamiento_activo')")
    cfg_rows = {r['clave']: r['valor'] for r in cursor.fetchall()}
    
    tmpl_conf_default = "Hola {nombre}, te escribimos para confirmar tu próxima sesión agendada para el *{fecha}* a las *{hora}* en modalidad *{modalidad}*.\n\nPor favor responde:\n✅ *SI* para confirmar tu asistencia\n❌ *NO* para cancelar\n\n¡Gracias!"
    
    # Si la plantilla guardada en BD no tiene 'SI' o 'NO', la actualizamos para garantizar la instrucción
    msg_conf_db = cfg_rows.get('msg_confirmacion', '')
    if not msg_conf_db or ('SI' not in msg_conf_db and 'Sí' not in msg_conf_db and 'si' not in msg_conf_db):
        cursor.execute("INSERT OR REPLACE INTO configuracion (clave, valor) VALUES ('msg_confirmacion', ?)", (tmpl_conf_default,))
        db.commit()
        msg_conf_db = tmpl_conf_default

    tmpl_rec_default = cfg_rows.get('msg_recordatorio') or "Hola {nombre}, te recordamos que HOY tienes tu cita agendada a las {hora} en modalidad {modalidad}. ¡Nos vemos pronto!"

    enviados_confirmaciones = []
    enviados_recordatorios = []
    errores = []

    future_3days_str = (now_local + timedelta(days=3)).strftime('%Y-%m-%d')

    # 1. ENVIAR CONFIRMACIONES PARA CITAS PRÓXIMAS (Citas no confirmadas en la ventana 24-48h)
    cursor.execute("""
        SELECT af.*, p.nombres as pat_nombres, p.apellidos as pat_apellidos, p.telefono as pat_telefono, p.pais as pat_pais, p.psicologo_id,
               COALESCE(u.nombres, 'Paulo') as psic_nombres, COALESCE(u.apellidos, 'Mora') as psic_apellidos
        FROM agenda_finanzas af
        JOIN pacientes p ON af.paciente_id = p.id
        LEFT JOIN usuarios u ON (p.psicologo_id = u.id OR (p.psicologo_id IS NULL AND u.id = 1))
        WHERE (af.fecha >= ? AND af.fecha <= ?) AND COALESCE(af.confirmada, 0) = 0 AND COALESCE(af.estado_pago, '') != 'Cancelada' AND COALESCE(af.confirmacion_enviada_wa, 0) = 0
    """, (today_str, future_3days_str))
    citas_confirmar = cursor.fetchall()

    for cita in citas_confirmar:
        phone = cita['pat_telefono']
        if not phone or not phone.strip():
            continue
        
        try:
            session_dt = datetime.strptime(f"{cita['fecha']} {cita['hora']}", "%Y-%m-%d %H:%M")
            diff_hours = (session_dt - now_local).total_seconds() / 3600.0
        except Exception:
            diff_hours = 12.0

        # Si la cita está dentro de las 48h o si el usuario hizo clic manual en "Ejecutar Recordatorios Ahora"
        if not (0 < diff_hours <= 48 or has_request_context()):
            continue
        psicologo_data = {'nombres': cita['psic_nombres'], 'apellidos': cita['psic_apellidos']}
        cita_dict = {
            'nombre': f"{cita['pat_nombres']} {cita['pat_apellidos']}",
            'fecha': cita['fecha'],
            'hora': cita['hora'],
            'modalidad': cita['tipo_consulta'] or 'Presencial'
        }
        patient_dict = {
            'nombres': cita['pat_nombres'],
            'apellidos': cita['pat_apellidos'],
            'pais': cita['pat_pais'] or ''
        }
        mensaje_texto = format_whatsapp_message(msg_conf_db, patient_dict, cita_dict, psicologo_data)
        psych_id = cita['psicologo_id'] or 1

        # Marcar inmediatamente para prevenir re-envíos duplicados por timeout o reintentos
        cursor.execute("UPDATE agenda_finanzas SET confirmacion_enviada_wa = 1 WHERE id = ?", (cita['id'],))
        db.commit()

        try:
            r = make_wa_http_request('POST', '/send', json_data={'phone': phone, 'text': mensaje_texto}, timeout=15, user_id=psych_id)
            if r and r.status_code == 200:
                enviados_confirmaciones.append({'cita_id': cita['id'], 'paciente': f"{cita['pat_nombres']} {cita['pat_apellidos']}", 'phone': phone, 'tipo': 'confirmacion'})
            else:
                err_msg = 'Timeout de microservicio'
                if r:
                    try: err_msg = r.json().get('error', r.text)
                    except: err_msg = r.text
                errores.append({'cita_id': cita['id'], 'paciente': f"{cita['pat_nombres']} {cita['pat_apellidos']}", 'phone': phone, 'error': err_msg})
        except Exception as e:
            errores.append({'cita_id': cita['id'], 'paciente': f"{cita['pat_nombres']} {cita['pat_apellidos']}", 'phone': phone, 'error': str(e)})

    # 2. ENVIAR RECORDATORIOS DEL DÍA (Citas de Hoy CONFIRMADAS en Citas O Finanzas)
    cursor.execute("""
        SELECT af.*, p.nombres as pat_nombres, p.apellidos as pat_apellidos, p.telefono as pat_telefono, p.pais as pat_pais, p.psicologo_id,
               COALESCE(u.nombres, 'Paulo') as psic_nombres, COALESCE(u.apellidos, 'Mora') as psic_apellidos
        FROM agenda_finanzas af
        JOIN pacientes p ON af.paciente_id = p.id
        LEFT JOIN usuarios u ON (p.psicologo_id = u.id OR (p.psicologo_id IS NULL AND u.id = 1))
        WHERE af.fecha = ? AND COALESCE(af.confirmada, 0) = 1 AND COALESCE(af.estado_pago, '') != 'Cancelada' AND COALESCE(af.recordatorio_enviado_wa, 0) = 0
    """, (today_str,))
    citas_recordar = cursor.fetchall()

    for cita in citas_recordar:
        phone = cita['pat_telefono']
        if not phone or not phone.strip():
            continue
        psicologo_data = {'nombres': cita['psic_nombres'], 'apellidos': cita['psic_apellidos']}
        cita_dict = {
            'nombre': f"{cita['pat_nombres']} {cita['pat_apellidos']}",
            'fecha': cita['fecha'],
            'hora': cita['hora'],
            'modalidad': cita['tipo_consulta'] or 'Presencial'
        }
        patient_dict = {
            'nombres': cita['pat_nombres'],
            'apellidos': cita['pat_apellidos'],
            'pais': cita['pat_pais'] or ''
        }
        mensaje_texto = format_whatsapp_message(tmpl_rec_default, patient_dict, cita_dict, psicologo_data)
        psych_id = cita['psicologo_id'] or 1

        # Marcar inmediatamente para prevenir re-envíos duplicados
        cursor.execute("UPDATE agenda_finanzas SET recordatorio_enviado_wa = 1 WHERE id = ?", (cita['id'],))
        db.commit()

        try:
            r = make_wa_http_request('POST', '/send', json_data={'phone': phone, 'text': mensaje_texto}, timeout=15, user_id=psych_id)
            if r and r.status_code == 200:
                enviados_recordatorios.append({'cita_id': cita['id'], 'paciente': f"{cita['pat_nombres']} {cita['pat_apellidos']}", 'phone': phone, 'tipo': 'recordatorio'})
            else:
                err_msg = 'Timeout de microservicio'
                if r:
                    try: err_msg = r.json().get('error', r.text)
                    except: err_msg = r.text
                errores.append({'cita_id': cita['id'], 'paciente': f"{cita['pat_nombres']} {cita['pat_apellidos']}", 'phone': phone, 'error': err_msg})
        except Exception as e:
            errores.append({'cita_id': cita['id'], 'paciente': f"{cita['pat_nombres']} {cita['pat_apellidos']}", 'phone': phone, 'error': str(e)})

    # 3. ENVIAR MENSAJES DE CIERRE Y REAGENDAMIENTO AL FINAL DEL HORARIO LABORAL (18:00 a 21:59)
    enviados_reagendamientos = []
    enviados_cierres = []

    if current_hour >= 18 and current_hour < 22:
        auto_reag_activo = (cfg_rows.get('auto_reagendamiento_activo') == '1')
        
        if auto_reag_activo:
            tmpl_reag_default = cfg_rows.get('msg_reagendamiento') or "Hola {nombre}, notamos que no pudimos realizar tu sesión agendada para el *{fecha}*. Te invitamos a agendar un nuevo espacio ingresando a nuestra plataforma o respondiendo a este mensaje. ¡Estamos para acompañarte!"

            cursor.execute("""
                SELECT af.*, p.nombres as pat_nombres, p.apellidos as pat_apellidos, p.telefono as pat_telefono, p.pais as pat_pais, p.psicologo_id,
                       COALESCE(u.nombres, 'Paulo') as psic_nombres, COALESCE(u.apellidos, 'Mora') as psic_apellidos
                FROM agenda_finanzas af
                JOIN pacientes p ON af.paciente_id = p.id
                LEFT JOIN usuarios u ON (p.psicologo_id = u.id OR (p.psicologo_id IS NULL AND u.id = 1))
                WHERE (af.fecha = ? OR af.fecha = ?) 
                  AND COALESCE(af.confirmada, 0) = 0 
                  AND COALESCE(af.reagendamiento_enviado_wa, 0) = 0
                  AND COALESCE(af.estado_pago, '') NOT IN ('Cancelada', 'Pagado', 'Paga', 'Completada')
                  AND NOT EXISTS (
                      SELECT 1 FROM agenda_finanzas af_future 
                      WHERE af_future.paciente_id = af.paciente_id AND af_future.fecha > af.fecha
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM sesiones s 
                      WHERE s.paciente_id = af.paciente_id AND s.fecha >= af.fecha
                  )
            """, (today_str, (now_local - timedelta(days=1)).strftime('%Y-%m-%d')))
            citas_reagendar = cursor.fetchall()

            for cita in citas_reagendar:
                phone = cita['pat_telefono']
                if not phone or not phone.strip():
                    continue
                psicologo_data = {'nombres': cita['psic_nombres'], 'apellidos': cita['psic_apellidos']}
                cita_dict = {
                    'nombre': f"{cita['pat_nombres']} {cita['pat_apellidos']}",
                    'fecha': cita['fecha'],
                    'hora': cita['hora'],
                    'modalidad': cita['tipo_consulta'] or 'Presencial'
                }
                patient_dict = {
                    'nombres': cita['pat_nombres'],
                    'apellidos': cita['pat_apellidos'],
                    'pais': cita['pat_pais'] or ''
                }
                mensaje_texto = format_whatsapp_message(tmpl_reag_default, patient_dict, cita_dict, psicologo_data)
                psych_id = cita['psicologo_id'] or 1

                # Marcar inmediatamente para prevenir re-envíos duplicados
                cursor.execute("UPDATE agenda_finanzas SET reagendamiento_enviado_wa = 1 WHERE id = ?", (cita['id'],))
                db.commit()

                try:
                    r = make_wa_http_request('POST', '/send', json_data={'phone': phone, 'text': mensaje_texto}, timeout=15, user_id=psych_id)
                    if r and r.status_code == 200:
                        enviados_reagendamientos.append({'cita_id': cita['id'], 'paciente': f"{cita['pat_nombres']} {cita['pat_apellidos']}", 'phone': phone, 'tipo': 'reagendamiento'})
                except Exception as e:
                    pass

        # B) Cierre de Sesión (Citas de Hoy finalizadas para invitar a volver a agendar)
        tmpl_cierre_default = cfg_rows.get('msg_cierre') or "Hola {nombre}, gracias por compartir el espacio terapéutico hoy. Recuerda realizar las tareas asignadas. Si deseas agendar o reprogramar tu próxima sesión, puedes hacerlo desde tu portal."

        cursor.execute("""
            SELECT af.*, p.nombres as pat_nombres, p.apellidos as pat_apellidos, p.telefono as pat_telefono, p.pais as pat_pais, p.psicologo_id,
                   COALESCE(u.nombres, 'Paulo') as psic_nombres, COALESCE(u.apellidos, 'Mora') as psic_apellidos
            FROM agenda_finanzas af
            JOIN pacientes p ON af.paciente_id = p.id
            LEFT JOIN usuarios u ON (p.psicologo_id = u.id OR (p.psicologo_id IS NULL AND u.id = 1))
            WHERE af.fecha = ? 
              AND COALESCE(af.confirmada, 0) = 1
              AND COALESCE(af.estado_pago, '') != 'Cancelada'
              AND COALESCE(af.cierre_enviado_wa, 0) = 0
        """, (today_str,))
        citas_cierre = cursor.fetchall()

        for cita in citas_cierre:
            phone = cita['pat_telefono']
            if not phone or not phone.strip():
                continue
            psicologo_data = {'nombres': cita['psic_nombres'], 'apellidos': cita['psic_apellidos']}
            cita_dict = {
                'nombre': f"{cita['pat_nombres']} {cita['pat_apellidos']}",
                'fecha': cita['fecha'],
                'hora': cita['hora'],
                'modalidad': cita['tipo_consulta'] or 'Presencial'
            }
            patient_dict = {
                'nombres': cita['pat_nombres'],
                'apellidos': cita['pat_apellidos'],
                'pais': cita['pat_pais'] or ''
            }
            mensaje_texto = format_whatsapp_message(tmpl_cierre_default, patient_dict, cita_dict, psicologo_data)
            psych_id = cita['psicologo_id'] or 1

            # Marcar inmediatamente para prevenir re-envíos duplicados
            cursor.execute("UPDATE agenda_finanzas SET cierre_enviado_wa = 1 WHERE id = ?", (cita['id'],))
            db.commit()

            try:
                r = make_wa_http_request('POST', '/send', json_data={'phone': phone, 'text': mensaje_texto}, timeout=15, user_id=psych_id)
                if r and r.status_code == 200:
                    enviados_cierres.append({'cita_id': cita['id'], 'paciente': f"{cita['pat_nombres']} {cita['pat_apellidos']}", 'phone': phone, 'tipo': 'cierre'})
            except Exception as e:
                pass

    # 4. ENVIAR RECORDATORIOS DE HERRAMIENTAS TERAPÉUTICAS DIARIAS
    herramientas_enviadas = 0
    try:
        from app import send_hourly_patient_tool_reminders
        herramientas_enviadas = send_hourly_patient_tool_reminders(db, force=True)
    except Exception as e_tools:
        print("Aviso al ejecutar send_hourly_patient_tool_reminders en cron:", e_tools)

    db.commit()

    return jsonify({
        'success': True,
        'confirmaciones_enviadas': len(enviados_confirmaciones),
        'recordatorios_enviados': len(enviados_recordatorios),
        'reagendamientos_enviados': len(enviados_reagendamientos),
        'cierres_enviados': len(enviados_cierres),
        'herramientas_enviadas': herramientas_enviadas,
        'detalles': {
            'confirmaciones': enviados_confirmaciones,
            'recordatorios': enviados_recordatorios,
            'reagendamientos': enviados_reagendamientos,
            'cierres': enviados_cierres,
            'errores': errores
        },
        'summary': {
            'confirmaciones': enviados_confirmaciones,
            'recordatorios': enviados_recordatorios,
            'reagendamientos': enviados_reagendamientos,
            'cierres': enviados_cierres,
            'errores': errores
        }
    })

@notificaciones_bp.route('/api/whatsapp/send-queue-item-now/<item_id>', methods=['POST'])
@login_required
def send_queue_item_now(item_id):
    """
    Envía inmediatamente un mensaje de la cola de WhatsApp (ya sea confirmación de cita, 
    recordatorio de consulta o token de herramienta terapéutica).
    """
    user_id = session.get('user_id')
    db = get_db()
    cursor = db.cursor()

    try:
        if str(item_id).startswith('tool_'):
            tool_queue_id = int(str(item_id).replace('tool_', ''))
            cursor.execute("""
                SELECT c.*, p.nombres, p.apellidos, p.telefono, p.psicologo_id, t.token
                FROM cola_recordatorios_herramientas c
                JOIN pacientes p ON c.paciente_id = p.id
                LEFT JOIN tokens_herramientas t ON c.token_id = t.id
                WHERE c.id = ?
            """, (tool_queue_id,))
            q_row = cursor.fetchone()

            if not q_row:
                return jsonify({'error': 'Registro de herramienta no encontrado'}), 404
            
            p_id = q_row['paciente_id']
            mod_clave = q_row['herramienta_tipo']
            psych_id = q_row['psicologo_id'] or user_id or 1
            phone = q_row['telefono']
            today_str = q_row['fecha_programada']
            token = q_row['token']

            if not phone:
                return jsonify({'error': 'El paciente no tiene teléfono registrado'}), 400

            if not token:
                import secrets
                token = secrets.token_urlsafe(32)
                expiracion = datetime.now() + timedelta(days=7)
                cursor.execute("""
                    INSERT INTO tokens_herramientas (
                        token, paciente_id, psicologo_id, herramienta_tipo, fecha_programada, fecha_expiracion, usado
                    ) VALUES (?, ?, ?, ?, ?, ?, 0)
                """, (token, p_id, psych_id, mod_clave, today_str, expiracion.strftime("%Y-%m-%d %H:%M:%S")))
                token_id = cursor.lastrowid
                db.commit()
            else:
                token_id = q_row['token_id']

            domain_host = request.host_url.rstrip('/') if request else 'https://www.espacioterapeutico.net'
            direct_link = f"{domain_host}/herramienta/directa?token={token}"
            first_name = (q_row['nombres'] or '').strip().split()[0] if q_row['nombres'] else 'Consultante'

            TOOL_NAME_MAP = {
                'pantalla': 'Registro de Consumo de Pantallas',
                'cognitivo': 'Registro Cognitivo (TCC)',
                'ingesta': 'Registro de Ingesta Alimentaria',
                'activacion': 'Checklist de Activación Conductual',
                'adherencia': 'Control de Adherencia a Medicamentos',
                'pizarra': 'Diario / Pizarra Terapéutica',
                'sueno': 'Higiene del Sueño',
                'ansiedad': 'Diario de Ansiedad',
                'sobriedad': 'Registro de Consumo y Sobriedad'
            }
            tool_title = TOOL_NAME_MAP.get(mod_clave, 'Herramienta Terapéutica')

            cursor.execute("SELECT valor FROM configuracion WHERE clave = ?", (f"msg_herramientas_{psych_id}",))
            tmpl_row = cursor.fetchone()
            if not tmpl_row or not tmpl_row['valor']:
                cursor.execute("SELECT valor FROM configuracion WHERE clave = 'msg_herramientas'")
                tmpl_row = cursor.fetchone()

            default_tmpl = (
                "Hola *{nombre}* 👋 Espero te encuentres muy bien.\n\n"
                "Te recuerdo completar tu *{herramienta}* del día de hoy. "
                "Puedes llenarlo en 30 segundos haciendo clic en el siguiente enlace directo (sin iniciar sesión):\n"
                "👉 {link}\n\n"
                "¡Gracias por tu constancia!"
            )
            raw_tmpl = (tmpl_row['valor'] if tmpl_row and tmpl_row['valor'] else default_tmpl)
            msg_wa = raw_tmpl.replace('{nombre}', first_name).replace('{herramienta}', tool_title).replace('{link}', direct_link)

            from routes_herramientas import clean_phone_number
            clean_phone = clean_phone_number(phone)
            res_wa = make_wa_http_request('POST', '/send', json_data={'phone': clean_phone, 'text': msg_wa, 'user_id': psych_id}, timeout=15, user_id=psych_id)

            if res_wa and res_wa.status_code == 200:
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                cursor.execute("""
                    UPDATE cola_recordatorios_herramientas
                    SET estado = 'enviado', enviado = 1, fecha_envio = ?, token_id = ?
                    WHERE id = ?
                """, (now_str, token_id, tool_queue_id))
                db.commit()
                return jsonify({'success': True, 'message': f'Recordatorio de herramienta enviado a {q_row["nombres"]}'})
            else:
                err_text = 'Error enviando por WhatsApp microservicio'
                try: err_text = res_wa.json().get('error', res_wa.text)
                except: pass
                return jsonify({'error': err_text}), 500

        else:
            # Es una cita regular de agenda_finanzas
            appt_id = int(item_id)
            cursor.execute("""
                SELECT af.*, p.nombres as pat_nombres, p.apellidos as pat_apellidos, p.telefono as pat_telefono, p.pais as pat_pais, p.psicologo_id,
                       COALESCE(u.nombres, 'Paulo') as psic_nombres, COALESCE(u.apellidos, 'Mora') as psic_apellidos
                FROM agenda_finanzas af
                JOIN pacientes p ON af.paciente_id = p.id
                LEFT JOIN usuarios u ON (p.psicologo_id = u.id OR (p.psicologo_id IS NULL AND u.id = 1))
                WHERE af.id = ?
            """, (appt_id,))
            cita = cursor.fetchone()

            if not cita:
                return jsonify({'error': 'Cita no encontrada'}), 404

            phone = cita['pat_telefono']
            if not phone:
                return jsonify({'error': 'El paciente no tiene teléfono registrado'}), 400

            psych_id = cita['psicologo_id'] or user_id or 1
            psicologo_data = {'nombres': cita['psic_nombres'], 'apellidos': cita['psic_apellidos']}
            cita_dict = {
                'nombre': f"{cita['pat_nombres']} {cita['pat_apellidos']}",
                'fecha': cita['fecha'],
                'hora': cita['hora'],
                'modalidad': cita['tipo_consulta'] or 'Presencial'
            }
            patient_dict = {
                'nombres': cita['pat_nombres'],
                'apellidos': cita['pat_apellidos'],
                'pais': cita['pat_pais'] or ''
            }

            cursor.execute("SELECT clave, valor FROM configuracion WHERE clave IN ('msg_confirmacion', 'msg_recordatorio')")
            cfg_rows = {r['clave']: r['valor'] for r in cursor.fetchall()}
            
            if cita['confirmada'] == 1:
                tmpl_msg = cfg_rows.get('msg_recordatorio') or "Hola {nombre}, te recordamos que tu cita está agendada para el {fecha} a las {hora} en modalidad {modalidad}. ¡Nos vemos pronto!"
                is_conf_type = False
            else:
                tmpl_msg = cfg_rows.get('msg_confirmacion') or "Hola {nombre}, te escribimos para confirmar tu próxima sesión agendada para el *{fecha}* a las *{hora}* en modalidad *{modalidad}*.\n\nPor favor responde:\n✅ *SI* para confirmar tu asistencia\n❌ *NO* para cancelar\n\n¡Gracias!"
                is_conf_type = True

            mensaje_texto = format_whatsapp_message(tmpl_msg, patient_dict, cita_dict, psicologo_data)
            
            from routes_herramientas import clean_phone_number
            clean_phone = clean_phone_number(phone)
            res_wa = make_wa_http_request('POST', '/send', json_data={'phone': clean_phone, 'text': mensaje_texto}, timeout=15, user_id=psych_id)

            if res_wa and res_wa.status_code == 200:
                if is_conf_type:
                    cursor.execute("UPDATE agenda_finanzas SET confirmacion_enviada_wa = 1 WHERE id = ?", (appt_id,))
                else:
                    cursor.execute("UPDATE agenda_finanzas SET recordatorio_enviado_wa = 1 WHERE id = ?", (appt_id,))
                db.commit()
                return jsonify({'success': True, 'message': f'Mensaje enviado con éxito a {cita["pat_nombres"]}'})
            else:
                err_text = 'Error enviando por WhatsApp microservicio'
                try: err_text = res_wa.json().get('error', res_wa.text)
                except: pass
                return jsonify({'error': err_text}), 500

    except Exception as e:
        return jsonify({'error': f'Error procesando envío individual: {str(e)}'}), 500








@notificaciones_bp.route('/api/whatsapp/queue-status', methods=['GET'])
@login_required
def get_whatsapp_queue_status():
    psic_id = get_psicologo_id_filter()
    db = get_db()
    cursor = db.cursor()

    # Garantizar creación automática de columnas en SQLite
    try:
        cursor.execute("PRAGMA table_info(agenda_finanzas)")
        cols_fin = [r[1] for r in cursor.fetchall()]
        if 'reagendamiento_enviado_wa' not in cols_fin:
            cursor.execute("ALTER TABLE agenda_finanzas ADD COLUMN reagendamiento_enviado_wa INTEGER DEFAULT 0")
        if 'confirmacion_enviada_wa' not in cols_fin:
            cursor.execute("ALTER TABLE agenda_finanzas ADD COLUMN confirmacion_enviada_wa INTEGER DEFAULT 0")
        if 'recordatorio_enviado_wa' not in cols_fin:
            cursor.execute("ALTER TABLE agenda_finanzas ADD COLUMN recordatorio_enviado_wa INTEGER DEFAULT 0")
        db.commit()
    except Exception as ex_col:
        print("Aviso al migrar columnas de cola de WhatsApp en agenda_finanzas:", ex_col)

    try:
        cursor.execute("PRAGMA table_info(citas)")
        cols_citas = [r[1] for r in cursor.fetchall()]
        if cols_citas:
            if 'reagendamiento_enviado_wa' not in cols_citas:
                cursor.execute("ALTER TABLE citas ADD COLUMN reagendamiento_enviado_wa INTEGER DEFAULT 0")
            if 'confirmacion_enviada_wa' not in cols_citas:
                cursor.execute("ALTER TABLE citas ADD COLUMN confirmacion_enviada_wa INTEGER DEFAULT 0")
            if 'recordatorio_enviado_wa' not in cols_citas:
                cursor.execute("ALTER TABLE citas ADD COLUMN recordatorio_enviado_wa INTEGER DEFAULT 0")
            db.commit()
    except Exception as ex_col:
        print("Aviso al migrar columnas de cola de WhatsApp:", ex_col)

    from datetime import datetime, timedelta
    try:
        import zoneinfo
        tz = zoneinfo.ZoneInfo("America/Caracas")
        now_local = datetime.now(tz)
    except Exception:
        now_local = datetime.utcnow() - timedelta(hours=4)

    today_str = now_local.strftime('%Y-%m-%d')
    yesterday_str = (now_local - timedelta(days=1)).strftime('%Y-%m-%d')

    queue = []
    try:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='citas'")
        has_citas_table = cursor.fetchone() is not None
        if has_citas_table:
            join_clause = "LEFT JOIN citas c ON c.paciente_id = p.id AND c.fecha = af.fecha"
            estado_col = "COALESCE(c.estado, 'Agendada') as estado_cita"
        else:
            join_clause = ""
            estado_col = "'Agendada' as estado_cita"

        user_id = session.get('user_id', 1)
        if user_id == 1:
            sql = f"""
                SELECT af.id, af.fecha, af.hora, af.tipo_consulta, af.confirmada, af.estado_pago,
                       COALESCE(af.confirmacion_enviada_wa, 0) as confirmacion_enviada,
                       COALESCE(af.recordatorio_enviado_wa, 0) as recordatorio_enviado,
                       COALESCE(af.reagendamiento_enviado_wa, 0) as reagendamiento_enviado,
                       {estado_col},
                       p.id as paciente_id, p.nombres as pat_nombres, p.apellidos as pat_apellidos, p.telefono as pat_telefono
                FROM agenda_finanzas af
                JOIN pacientes p ON af.paciente_id = p.id
                {join_clause}
                WHERE (p.psicologo_id = 1 OR p.psicologo_id IS NULL) AND af.fecha >= ?
                ORDER BY af.fecha ASC, af.hora ASC
                LIMIT 500
            """
            cursor.execute(sql, (yesterday_str,))
        else:
            sql = f"""
                SELECT af.id, af.fecha, af.hora, af.tipo_consulta, af.confirmada, af.estado_pago,
                       COALESCE(af.confirmacion_enviada_wa, 0) as confirmacion_enviada,
                       COALESCE(af.recordatorio_enviado_wa, 0) as recordatorio_enviado,
                       COALESCE(af.reagendamiento_enviado_wa, 0) as reagendamiento_enviado,
                       {estado_col},
                       p.id as paciente_id, p.nombres as pat_nombres, p.apellidos as pat_apellidos, p.telefono as pat_telefono
                FROM agenda_finanzas af
                JOIN pacientes p ON af.paciente_id = p.id
                {join_clause}
                WHERE p.psicologo_id = ? AND af.fecha >= ?
                ORDER BY af.fecha ASC, af.hora ASC
                LIMIT 500
            """
            cursor.execute(sql, (user_id, yesterday_str))
        
        rows = cursor.fetchall()

        for r in rows:
            fecha_cita = r['fecha']
            hora_cita = r['hora']
            pat_name = f"{r['pat_nombres']} {r['pat_apellidos']}"
            phone = r['pat_telefono'] or ''
            estado_c = r['estado_cita']
            estado_p = str(r['estado_pago'] or '')
            is_confirmada = (r['confirmada'] == 1 or estado_c == 'Confirmada')
            is_cancelada = (estado_c == 'Cancelada' or 'Cancelada' in estado_p or estado_p == 'Reprogramada')
            is_stopped_manual = (r['confirmacion_enviada'] == -1 or r['recordatorio_enviado'] == -1 or r['reagendamiento_enviado'] == -1)

            tomorrow_str = (now_local + timedelta(days=1)).strftime('%Y-%m-%d')
            can_cancel = False

            if is_stopped_manual:
                pipeline_status = 'detenido_manual'
                pipeline_label = '🛑 Envío Detenido Manualmente'
                priority = 6
            elif is_cancelada:
                pipeline_status = 'cancelado'
                pipeline_label = '❌ Cita Cancelada/Eliminada (Envío Inhabilitado)'
                priority = 6
            elif fecha_cita == tomorrow_str:
                if r['confirmacion_enviada'] == 1:
                    if is_confirmada:
                        pipeline_status = 'confirmado'
                        pipeline_label = '✅ Confirmado por Paciente'
                        priority = 4
                    else:
                        pipeline_status = 'enviado_conf'
                        pipeline_label = '🚀 Confirmación Enviada (Esperando Respuesta)'
                        priority = 3
                else:
                    pipeline_status = 'en_cola_conf'
                    pipeline_label = '📥 En Cola (Confirmación 24h)'
                    priority = 1
                    can_cancel = True
            elif fecha_cita > tomorrow_str:
                if r['confirmacion_enviada'] == 1:
                    pipeline_status = 'enviado_conf'
                    pipeline_label = '🚀 Confirmación Enviada'
                    priority = 3
                else:
                    pipeline_status = 'esperando_fecha'
                    pipeline_label = '⏳ Programado en Cola'
                    priority = 2
                    can_cancel = True
            elif fecha_cita == today_str:
                if is_confirmada:
                    if r['recordatorio_enviado'] == 1:
                        pipeline_status = 'enviado_rec'
                        pipeline_label = '🚀 Recordatorio Enviado Hoy'
                        priority = 4
                    else:
                        pipeline_status = 'en_cola'
                        pipeline_label = '📥 En Cola (Recordatorio Hoy)'
                        priority = 1
                        can_cancel = True
                else:
                    if r['reagendamiento_enviado'] == 1:
                        pipeline_status = 'reagendar_enviado'
                        pipeline_label = '🔄 Reagendamiento Enviado'
                        priority = 4
                    else:
                        pipeline_status = 'en_cola_reagendar'
                        pipeline_label = '📥 En Cola (Reagendamiento Fin de Día)'
                        priority = 1
                        can_cancel = True
            else:
                if r['reagendamiento_enviado'] == 1:
                    pipeline_status = 'reagendar_enviado'
                    pipeline_label = '🔄 Reagendamiento Enviado'
                    priority = 4
                elif is_confirmada:
                    pipeline_status = 'completada'
                    pipeline_label = '✅ Cita Realizada'
                    priority = 5
                else:
                    pipeline_status = 'pendiente_reagendar'
                    pipeline_label = '📥 Pendiente Reagendar'
                    priority = 4

            queue.append({
                'cita_id': r['id'],
                'paciente_nombre': pat_name,
                'telefono': phone,
                'fecha': fecha_cita,
                'hora': hora_cita,
                'tipo_consulta': r['tipo_consulta'] or 'Presencial',
                'pipeline_status': pipeline_status,
                'pipeline_label': pipeline_label,
                'priority': priority,
                'can_cancel': can_cancel
            })

        # Incluir también recordatorios de herramientas terapéuticas programados
        try:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cola_recordatorios_herramientas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    psicologo_id INTEGER NOT NULL,
                    paciente_id INTEGER NOT NULL,
                    herramienta_tipo TEXT NOT NULL,
                    fecha_programada DATE NOT NULL,
                    hora_programada TEXT DEFAULT '20:00',
                    estado TEXT DEFAULT 'programado',
                    enviado INTEGER DEFAULT 0,
                    fecha_envio DATETIME NULL,
                    token_id INTEGER NULL,
                    pausado INTEGER DEFAULT 0,
                    fecha_registro DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(paciente_id, herramienta_tipo, fecha_programada)
                )
            """)
            
            tool_sql = """
                SELECT c.id, c.paciente_id, c.herramienta_tipo, c.fecha_programada, c.hora_programada,
                       c.estado, c.enviado, c.pausado, c.token_id,
                       p.nombres as pat_nombres, p.apellidos as pat_apellidos, p.telefono as pat_telefono,
                       t.token
                FROM cola_recordatorios_herramientas c
                JOIN pacientes p ON c.paciente_id = p.id
                LEFT JOIN tokens_herramientas t ON c.token_id = t.id
                WHERE (p.psicologo_id = ? OR ? = 1) AND c.fecha_programada >= ?
                ORDER BY c.fecha_programada ASC, c.hora_programada ASC
                LIMIT 200
            """
            cursor.execute(tool_sql, (user_id, user_id, yesterday_str))
            tool_rows = cursor.fetchall()

            host_url = request.host_url.rstrip('/') if request else ""
            tool_names_map = {
                'sueno': 'Higiene del Sueño',
                'ansiedad': 'Diario de Ansiedad',
                'sobriedad': 'Registro de Consumo',
                'pantalla': 'Consumo de Pantallas',
                'adherencia': 'Adherencia Medicación',
                'activacion': 'Activación Conductual',
                'ingesta': 'Alimentos y Apetito',
                'cognitivo': 'Registro Cognitivo'
            }

            for tr in tool_rows:
                pat_name = f"{tr['pat_nombres']} {tr['pat_apellidos']}"
                phone = tr['pat_telefono'] or ''
                h_tipo = tr['herramienta_tipo']
                h_nombre = tool_names_map.get(h_tipo, 'Herramienta Terapéutica')
                tok = tr['token']

                if not tok:
                    cursor.execute("SELECT token FROM tokens_herramientas WHERE paciente_id = ? AND herramienta_tipo = ? ORDER BY id DESC LIMIT 1", (tr['paciente_id'], h_tipo))
                    t_row = cursor.fetchone()
                    if t_row:
                        tok = t_row['token']

                link_tool = f"{host_url}/herramienta/directa?token={tok}" if tok else ""
                
                st = tr['estado']
                pausado = tr['pausado']
                
                if st == 'cancelado' or pausado == 1:
                    pipeline_status = 'detenido_manual'
                    pipeline_label = '🛑 Recordatorio Pausado'
                    priority = 6
                    can_cancel = False
                elif st == 'completado' or tr['enviado'] == 1:
                    pipeline_status = 'completado'
                    pipeline_label = '🚀 Recordatorio Enviado'
                    priority = 4
                    can_cancel = False
                else:
                    pipeline_status = 'en_cola'
                    hora_disp = tr['hora_programada'] or '20:00'
                    if hora_disp == '08:00':
                        pipeline_label = '⏳ Recordatorio Sueño (08:00 AM)'
                    else:
                        pipeline_label = '⏳ Recordatorio Herramienta (08:00 PM)'
                    priority = 1
                    can_cancel = True

                queue.append({
                    'cita_id': f"tool_{tr['id']}",
                    'paciente_nombre': pat_name,
                    'telefono': phone,
                    'fecha': tr['fecha_programada'],
                    'hora': tr['hora_programada'] or '20:00',
                    'tipo_consulta': f"🛠️ Herramienta: {h_nombre}",
                    'pipeline_status': pipeline_status,
                    'pipeline_label': pipeline_label,
                    'priority': priority,
                    'can_cancel': can_cancel,
                    'token': tok,
                    'link': link_tool
                })
        except Exception as _tool_err:
            print("Aviso al consultar cola de herramientas en queue-status:", _tool_err)

        queue.sort(key=lambda x: (x['priority'], str(x['fecha']), str(x['hora'])))
    except Exception as e_q:
        import traceback
        print("Error en consulta de cola de WhatsApp:", e_q)
        traceback.print_exc()
        return jsonify({'queue': queue, 'debug_error': str(e_q)})

    return jsonify({'queue': queue})


@notificaciones_bp.route('/api/whatsapp/cancel-queue-item', methods=['POST'])
@login_required
def cancel_whatsapp_queue_item():
    data = request.json or {}
    cita_id = str(data.get('cita_id') or '')
    if not cita_id:
        return jsonify({'error': 'cita_id es obligatorio'}), 400
    db = get_db()
    cursor = db.cursor()
    
    try:
        if cita_id.startswith('tool_'):
            tool_queue_id = int(cita_id.replace('tool_', ''))
            cursor.execute("UPDATE cola_recordatorios_herramientas SET estado = 'cancelado', pausado = 1 WHERE id = ?", (tool_queue_id,))
        else:
            cid = int(cita_id)
            cursor.execute("""
                UPDATE agenda_finanzas
                SET confirmacion_enviada_wa = -1, recordatorio_enviado_wa = -1, reagendamiento_enviado_wa = -1
                WHERE id = ?
            """, (cid,))
            
            cursor.execute("SELECT paciente_id, fecha FROM agenda_finanzas WHERE id = ?", (cid,))
            row = cursor.fetchone()
            if row:
                try:
                    cursor.execute("""
                        UPDATE cola_recordatorios_herramientas
                        SET estado = 'cancelado'
                        WHERE paciente_id = ? AND fecha_programada = ?
                    """, (row['paciente_id'], row['fecha']))
                except Exception as _ex1:
                    print("Aviso actualizando cola_recordatorios_herramientas:", _ex1)
                    
                try:
                    cursor.execute("""
                        UPDATE tokens_herramientas
                        SET usado = 2
                        WHERE paciente_id = ? AND fecha_programada = ?
                    """, (row['paciente_id'], row['fecha']))
                except Exception as _ex2:
                    print("Aviso actualizando tokens_herramientas:", _ex2)
                
        db.commit()
        return jsonify({'success': 'Envío detenido y cancelado manualmente con éxito.'})
    except Exception as e:
        return jsonify({'error': f'Error al detener envío: {str(e)}'}), 500

# --- SCHEDULER DE WHATSAPP EN SEGUNDO PLANO (AUTOMÁTICO) ---
_wa_cron_thread_started = False
