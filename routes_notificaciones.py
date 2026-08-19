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

def make_wa_http_request(method, endpoint, json_data=None, timeout=5, user_id=None):
    import requests
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
    
    keys = ['msg_confirmacion', 'msg_confirmacion_ok', 'msg_cancelacion_ok', 'msg_recordatorio', 'msg_reagendamiento', 'msg_cierre', 'auto_reagendamiento_activo', 'msg_cumpleanos', 'auto_cumpleanos_activo']
    
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


# --- RUTAS MIGRADAS AUTOMÁTICAMENTE DE AUDITORÍA ---

@notificaciones_bp.route('/api/whatsapp/webhook', methods=['POST'])
def whatsapp_webhook():
    data = request.json or {}
    raw_user_id = data.get('user_id')
    raw_phone = str(data.get('phone', '')).strip()
    text = str(data.get('text', '')).strip()
    
    if not raw_phone or not text:
        return jsonify({'error': 'Payload incompleto'}), 400

    db = get_db()
    cursor = db.cursor()

    clean_digits = ''.join(filter(str.isdigit, raw_phone))
    if not clean_digits:
        return jsonify({'status': 'ignored', 'message': 'Número no válido'}), 400

    # 1. Búsqueda de paciente ultra flexible por coincidencia de dígitos telefónicos
    if raw_user_id:
        cursor.execute("SELECT id, nombres, apellidos, telefono, psicologo_id FROM pacientes WHERE psicologo_id = ? ORDER BY id DESC", (raw_user_id,))
    else:
        cursor.execute("SELECT id, nombres, apellidos, telefono, psicologo_id FROM pacientes ORDER BY id DESC")
    candidates = cursor.fetchall()

    patient = None
    for cand in candidates:
        cand_digits = ''.join(filter(str.isdigit, str(cand['telefono'] or '')))
        if not cand_digits:
            continue
        if (clean_digits.endswith(cand_digits) or 
            cand_digits.endswith(clean_digits) or 
            (len(clean_digits) >= 7 and len(cand_digits) >= 7 and clean_digits[-7:] == cand_digits[-7:])):
            patient = cand
            break

    if not patient and raw_user_id:
        cursor.execute("SELECT id, nombres, apellidos, telefono, psicologo_id FROM pacientes ORDER BY id DESC")
        all_cands = cursor.fetchall()
        for cand in all_cands:
            cand_digits = ''.join(filter(str.isdigit, str(cand['telefono'] or '')))
            if not cand_digits:
                continue
            if (clean_digits.endswith(cand_digits) or 
                cand_digits.endswith(clean_digits) or 
                (len(clean_digits) >= 7 and len(cand_digits) >= 7 and clean_digits[-7:] == cand_digits[-7:])):
                patient = cand
                break

    if not patient:
        return jsonify({'status': 'ignored', 'message': f'Teléfono {raw_phone} no asociado a ningún paciente.'})

    patient_id = patient['id']
    patient_name = f"{patient['nombres']} {patient['apellidos']}".strip()
    psic_id = patient['psicologo_id']
    
    import unicodedata, re
    text_lower = text.lower().strip()
    text_norm = unicodedata.normalize('NFD', text_lower)
    text_clean = ''.join(c for c in text_norm if unicodedata.category(c) != 'Mn')
    text_clean = re.sub(r'[^a-z0-9\s👍]', ' ', text_clean).strip()
    words_set = set(text_clean.split())

    confirm_keywords = {
        'si', 'sip', 'sii', 'siii', 'confirmo', 'confirmar', 'confirmado', 'confirmada',
        'asistire', 'ok', 'listo', '1', 's', 'voy', 'asisto', 'seguro', 'perfecto',
        'excelente', 'correcto', 'claro', 'dale', 'ahi', 'estare', 'allí', 'estaré', '👍'
    }

    cancel_keywords = {
        'no', 'nop', 'cancelo', 'cancelar', 'cancelado', 'cancelada', 'imposible',
        'podre', 'asisto', '2'
    }

    is_confirm = any(w in words_set for w in confirm_keywords) or any(k in text_clean for k in ['si', 'confirmo', 'asistire', 'ahi estare', 'allí estaré', '👍'])
    is_cancel = ('no' in words_set and 'si' not in words_set) or any(k in text_clean for k in ['cancelo', 'cancelar', 'no podre', 'no asisto'])

    if not is_confirm and not is_cancel:
        return jsonify({'status': 'text_received_no_action', 'message': f'Mensaje "{text}" recibido pero no requiere acción de confirmación.'})

    # 2. Buscar cita pendiente sin confirmar para este paciente
    cursor.execute("""
        SELECT id, fecha, hora, confirmada, tipo_consulta 
        FROM agenda_finanzas 
        WHERE paciente_id = ? AND (confirmada IS NULL OR confirmada = 0) AND (estado_pago IS NULL OR estado_pago != 'Cancelada')
        ORDER BY fecha ASC, hora ASC LIMIT 1
    """, (patient_id,))
    next_cita = cursor.fetchone()

    if not next_cita:
        cursor.execute("""
            SELECT id, fecha, hora, confirmada, tipo_consulta 
            FROM agenda_finanzas 
            WHERE paciente_id = ? AND (estado_pago IS NULL OR estado_pago != 'Cancelada')
            ORDER BY fecha DESC, hora DESC LIMIT 1
        """, (patient_id,))
        next_cita = cursor.fetchone()

    if not next_cita:
        return jsonify({'status': 'no_upcoming_appointment', 'message': f'No hay citas registradas para {patient_name}'})

    cita_id = next_cita['id']
    cita_fecha = next_cita['fecha']
    cita_hora = next_cita['hora']

    # Configuración de plantilla
    antelacion_horas = 24
    plantilla_encuadre = (
        "¡Gracias por confirmar tu sesión, *{paciente}*! 🌿\n\n"
        "📍 *Detalles de tu cita:*\n"
        "📅 *Fecha:* {fecha}\n"
        "⏰ *Hora:* {hora}\n\n"
        "💡 *Encuadre Terapéutico:*\n"
        "• Recuerda habilitar un espacio tranquilo, cómodo y privado para ti.\n"
        "• Realizar el pago correspondiente de la sesión.\n"
        "• Conectarte o asistir puntualmente a la hora acordada.\n\n"
        "⚠️ *Política de cancelación:* Si necesitas cancelar o reprogramar tu sesión, por favor avísanos con al menos *{horas_antelacion} horas* de anticipación."
    )

    try:
        cursor.execute("SELECT configuracion_horarios_visual FROM usuarios WHERE id = ?", (psic_id,))
        u_row = cursor.fetchone()
        if u_row and u_row['configuracion_horarios_visual']:
            import json
            cfg_json = json.loads(u_row['configuracion_horarios_visual'])
            antelacion_horas = cfg_json.get('limite_cancelacion_valor') or cfg_json.get('limite_cancelacion') or 24
            if cfg_json.get('plantilla_encuadre'):
                plantilla_encuadre = cfg_json.get('plantilla_encuadre')
    except Exception:
        pass

    from datetime import datetime
    now_formatted = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    if is_confirm:
        cursor.execute("UPDATE agenda_finanzas SET confirmada = 1, confirmacion_enviada_wa = 1 WHERE id = ?", (cita_id,))
        try:
            cursor.execute("UPDATE citas SET confirmada = 1 WHERE paciente_id = ? AND fecha = ?", (patient_id, cita_fecha))
        except Exception:
            pass

        notif_msg = f"📱 WhatsApp: {patient_name} CONFIRMÓ su cita del {cita_fecha} a las {cita_hora}."
        cursor.execute("""
            INSERT INTO notificaciones (user_id, tipo, titulo, mensaje, fecha, leida, link)
            VALUES (?, 'whatsapp_confirmation', 'Cita Confirmada por WhatsApp', ?, ?, 0, '#agenda')
        """, (psic_id, notif_msg, now_formatted))
        db.commit()

        cursor.execute("SELECT valor FROM configuracion WHERE clave = 'msg_confirmacion_ok'")
        cfg_ok = cursor.fetchone()
        tmpl_ok = cfg_ok['valor'] if cfg_ok and cfg_ok['valor'] else plantilla_encuadre

        psicologo_data = {'nombres': '', 'apellidos': ''}
        cursor.execute("SELECT nombres, apellidos FROM usuarios WHERE id = ?", (psic_id,))
        u_p = cursor.fetchone()
        if u_p: psicologo_data = dict(u_p)

        cita_dict = {'nombre': patient_name, 'fecha': cita_fecha, 'hora': cita_hora, 'modalidad': next_cita['tipo_consulta'] or 'Presencial'}
        patient_dict = {'nombres': patient['nombres'], 'apellidos': patient['apellidos']}
        
        try:
            reply_text = format_whatsapp_message(tmpl_ok, patient_dict, cita_dict, psicologo_data)
        except Exception:
            reply_text = (
                f"¡Gracias por confirmar tu sesión, *{patient['nombres']}*! 🌿\n\n"
                f"📅 *Fecha:* {cita_fecha}\n"
                f"⏰ *Hora:* {cita_hora}\n\n"
                f"Recuerda habilitar tu espacio privado, realizar el pago y llegar a tiempo."
            )

        try:
            make_wa_http_request('POST', '/send', json_data={'phone': raw_phone, 'text': reply_text}, timeout=10)
        except Exception as wa_err:
            print(f"⚠️ No se pudo responder automáticamente por WhatsApp: {wa_err}")

        return jsonify({'status': 'confirmed', 'message': f'Cita #{cita_id} confirmada para {patient_name}'})

    elif is_cancel:
        cursor.execute("UPDATE agenda_finanzas SET confirmada = 0, estado_pago = 'Cancelada' WHERE id = ?", (cita_id,))
        try:
            cursor.execute("UPDATE citas SET confirmada = 0 WHERE paciente_id = ? AND fecha = ?", (patient_id, cita_fecha))
        except Exception:
            pass

        notif_msg = f"⚠️ WhatsApp: {patient_name} CANCELÓ su cita del {cita_fecha} a las {cita_hora}."
        cursor.execute("""
            INSERT INTO notificaciones (user_id, tipo, titulo, mensaje, fecha, leida, link)
            VALUES (?, 'whatsapp_cancellation', 'Cita Cancelada por WhatsApp', ?, ?, 0, '#agenda')
        """, (psic_id, notif_msg, now_formatted))
        db.commit()

        cursor.execute("SELECT valor FROM configuracion WHERE clave = 'msg_cancelacion_ok'")
        cfg_cancel = cursor.fetchone()
        tmpl_cancel = cfg_cancel['valor'] if cfg_cancel and cfg_cancel['valor'] else (
            "Entendido, *{nombre}*. Hemos registrado la cancelación de tu sesión del *{fecha}* a las *{hora}*.\n\nSi deseas reprogramar en otro momento, no dudes en escribirnos o agendar desde tu portal."
        )

        psicologo_data = {'nombres': '', 'apellidos': ''}
        cursor.execute("SELECT nombres, apellidos FROM usuarios WHERE id = ?", (psic_id,))
        u_p = cursor.fetchone()
        if u_p: psicologo_data = dict(u_p)

        cita_dict = {'nombre': patient_name, 'fecha': cita_fecha, 'hora': cita_hora, 'modalidad': next_cita['tipo_consulta'] or 'Presencial'}
        patient_dict = {'nombres': patient['nombres'], 'apellidos': patient['apellidos']}
        cancel_reply = format_whatsapp_message(tmpl_cancel, patient_dict, cita_dict, psicologo_data)

        try:
            make_wa_http_request('POST', '/send', json_data={'phone': raw_phone, 'text': cancel_reply}, timeout=10)
        except Exception as wa_err:
            print(f"⚠️ No se pudo enviar mensaje de cancelación por WhatsApp: {wa_err}")

        return jsonify({'status': 'cancelled', 'message': f'Cita #{cita_id} cancelada para {patient_name}'})



@notificaciones_bp.route('/api/whatsapp/sync-session', methods=['GET', 'POST', 'DELETE'])
def sync_whatsapp_session():
    import json
    db = get_db()
    cursor = db.cursor()
    if request.method == 'DELETE':
        cursor.execute("DELETE FROM configuracion WHERE clave = 'wa_auth_session'")
        db.commit()
        return jsonify({'status': 'cleared'})
    elif request.method == 'POST':
        data = request.json or {}
        session_json = json.dumps(data)
        cursor.execute("INSERT OR REPLACE INTO configuracion (clave, valor) VALUES ('wa_auth_session', ?)", (session_json,))
        db.commit()
        return jsonify({'status': 'saved'})
    else:
        cursor.execute("SELECT valor FROM configuracion WHERE clave = 'wa_auth_session'")
        row = cursor.fetchone()
        if row and row['valor']:
            try:
                return jsonify(json.loads(row['valor']))
            except:
                return jsonify({})
        return jsonify({})



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

    # 1. ENVIAR CONFIRMACIONES PARA MAÑANA (Citas no confirmadas de mañana)
    cursor.execute("""
        SELECT af.*, p.nombres as pat_nombres, p.apellidos as pat_apellidos, p.telefono as pat_telefono, p.pais as pat_pais, p.psicologo_id,
               COALESCE(u.nombres, 'Paulo') as psic_nombres, COALESCE(u.apellidos, 'Mora') as psic_apellidos
        FROM agenda_finanzas af
        JOIN pacientes p ON af.paciente_id = p.id
        LEFT JOIN usuarios u ON (p.psicologo_id = u.id OR (p.psicologo_id IS NULL AND u.id = 1))
        WHERE af.fecha = ? AND COALESCE(af.confirmada, 0) = 0 AND COALESCE(af.estado_pago, '') != 'Cancelada' AND COALESCE(af.confirmacion_enviada_wa, 0) = 0
    """, (tomorrow_str,))
    citas_confirmar = cursor.fetchall()

    for cita in citas_confirmar:
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

    db.commit()

    return jsonify({
        'success': True,
        'confirmaciones_enviadas': len(enviados_confirmaciones),
        'recordatorios_enviados': len(enviados_recordatorios),
        'reagendamientos_enviados': len(enviados_reagendamientos),
        'cierres_enviados': len(enviados_cierres),
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

        cursor.execute("PRAGMA table_info(citas)")
        cols_citas = [r[1] for r in cursor.fetchall()]
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
                SELECT af.id, af.fecha, af.hora, af.tipo_consulta, af.confirmada,
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
                LIMIT 50
            """
            cursor.execute(sql, (yesterday_str,))
        else:
            sql = f"""
                SELECT af.id, af.fecha, af.hora, af.tipo_consulta, af.confirmada,
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
                LIMIT 50
            """
            cursor.execute(sql, (user_id, yesterday_str))
        
        rows = cursor.fetchall()

        for r in rows:
            fecha_cita = r['fecha']
            hora_cita = r['hora']
            pat_name = f"{r['pat_nombres']} {r['pat_apellidos']}"
            phone = r['pat_telefono'] or ''
            estado_c = r['estado_cita']
            is_confirmada = (r['confirmada'] == 1 or estado_c == 'Confirmada')
            is_cancelada = (estado_c == 'Cancelada')

            tomorrow_str = (now_local + timedelta(days=1)).strftime('%Y-%m-%d')

            if fecha_cita == tomorrow_str:
                if r['confirmacion_enviada'] == 1:
                    if is_confirmada:
                        pipeline_status = 'confirmado'
                        pipeline_label = '✅ Confirmado por Paciente'
                        priority = 4
                    elif is_cancelada:
                        pipeline_status = 'cancelado'
                        pipeline_label = '❌ Cancelado por Paciente'
                        priority = 5
                    else:
                        pipeline_status = 'enviado_conf'
                        pipeline_label = '🚀 Confirmación Enviada (Esperando Respuesta)'
                        priority = 3
                else:
                    pipeline_status = 'en_cola_conf'
                    pipeline_label = '📥 En Cola (Confirmación 24h)'
                    priority = 1
            elif fecha_cita > tomorrow_str:
                if r['confirmacion_enviada'] == 1:
                    pipeline_status = 'enviado_conf'
                    pipeline_label = '🚀 Confirmación Enviada'
                    priority = 3
                else:
                    pipeline_status = 'esperando_fecha'
                    pipeline_label = '⏳ Programado en Cola'
                    priority = 2
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
                elif is_cancelada:
                    pipeline_status = 'cancelado'
                    pipeline_label = '❌ Cancelado por Paciente'
                    priority = 5
                else:
                    if r['reagendamiento_enviado'] == 1:
                        pipeline_status = 'reagendar_enviado'
                        pipeline_label = '🔄 Reagendamiento Enviado'
                        priority = 4
                    else:
                        pipeline_status = 'en_cola_reagendar'
                        pipeline_label = '📥 En Cola (Reagendamiento Fin de Día)'
                        priority = 1
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
                'priority': priority
            })

        # Ordenar cola: Primero los pendientes/en cola (prioridad 1 y 2), al final los enviados y realizados
        queue.sort(key=lambda x: (x['priority'], x['fecha'], x['hora']))
    except Exception as e_q:
        import traceback
        print("Error en consulta de cola de WhatsApp:", e_q)
        traceback.print_exc()
        return jsonify({'queue': queue, 'debug_error': str(e_q)})

    return jsonify({'queue': queue})

# --- SCHEDULER DE WHATSAPP EN SEGUNDO PLANO (AUTOMÁTICO) ---
_wa_cron_thread_started = False


