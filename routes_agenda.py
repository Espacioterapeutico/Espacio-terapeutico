# -*- coding: utf-8 -*-
"""
Módulo de Agenda, Citas y Gestión de Disponibilidad (routes_agenda.py)
Encapsula el calendario de citas, eventos personales/bloqueos horarios,
cálculo de slots dinámicos de disponibilidad por modalidad (Presencial/Online),
reserva rápida pública (Fast Booking) y sincronización con Google Calendar.
"""

import os
import re
import json
import sqlite3
from datetime import datetime, timedelta
from functools import wraps
from flask import Blueprint, request, jsonify, session, g, render_template

agenda_bp = Blueprint('agenda', __name__)

def normalize_date_str(d_str):
    if not d_str:
        return ""
    d_str = str(d_str).strip()
    try:
        dt = datetime.strptime(d_str, "%Y-%m-%d")
        return dt.strftime("%Y-%m-%d")
    except:
        pass
    try:
        dt = datetime.strptime(d_str, "%d/%m/%Y")
        return dt.strftime("%Y-%m-%d")
    except:
        pass
    try:
        parts = d_str.split('-')
        if len(parts) == 3 and len(parts[0]) == 4:
            return f"{parts[0]}-{parts[1].zfill(2)}-{parts[2].zfill(2)}"
    except:
        pass
    return d_str

def normalize_time_str(t_str):
    if not t_str:
        return "00:00"
    t_str = str(t_str).strip().lower()
    is_pm = 'pm' in t_str
    is_am = 'am' in t_str
    clean_t = re.sub(r'[^\d:]', '', t_str)
    parts = clean_t.split(':')
    if not parts or not parts[0]:
        return "00:00"
    try:
        h = int(parts[0])
        m = int(parts[1]) if len(parts) > 1 and parts[1] else 0
        if is_pm and h < 12:
            h += 12
        elif is_am and h == 12:
            h = 0
        return f"{h:02d}:{m:02d}"
    except:
        return "00:00"

def get_appointment_fee(cursor, patient_id, psicologo_id=None, modalidad=None):
    """Calcula la tarifa (monto y moneda) para una consulta."""
    monto = 0.0
    moneda = '$'
    if patient_id:
        cursor.execute("SELECT costo_personalizado, moneda_personalizada FROM pacientes WHERE id = ?", (patient_id,))
        row = cursor.fetchone()
        if row:
            if row['costo_personalizado'] is not None and row['costo_personalizado'] > 0:
                monto = float(row['costo_personalizado'])
            if row['moneda_personalizada']:
                moneda = row['moneda_personalizada']
    return monto, moneda

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

def sync_patient_to_firebase(patient_id):
    try:
        from app import sync_patient_to_firebase as _sync
        _sync(patient_id)
    except Exception as _e:
        print(f"[WARN] Error en sync_patient_to_firebase({patient_id}): {_e}")

def get_psicologo_id_filter():
    role = session.get('role')
    user_id = session.get('user_id')
    username = session.get('username', '')
    
    if (role in ['admin', 'superadmin']) and (username.lower() != 'pamoraro' and user_id != 1):
        return -1
        
    return user_id if user_id else 1

def generate_dynamic_slots(cursor, psicologo_id, target_date_str, requested_modality='all', exclude_appt_id=None):
    """
    Genera dinámicamente los slots de disponibilidad a partir de configuracion_horarios_visual.
    """
    cursor.execute("SELECT configuracion_horarios_visual FROM usuarios WHERE id = ?", (psicologo_id,))
    u_row = cursor.fetchone()
    
    config = {}
    if u_row and u_row['configuracion_horarios_visual']:
        try:
            config = json.loads(u_row['configuracion_horarios_visual'])
        except: pass

    if not config:
        cursor.execute("SELECT valor FROM configuracion WHERE clave = 'configuracion_horarios_visual'")
        row = cursor.fetchone()
        if row and row['valor']:
            try:
                config = json.loads(row['valor'])
            except: pass

    duracion = int(config.get('duracion', 60))
    receso = int(config.get('receso', 0))
    antelacion = int(config.get('antelacion', 24))
    raw_perfiles = config.get('perfiles', [])
    perfiles = []
    if isinstance(raw_perfiles, dict):
        for k, v in raw_perfiles.items():
            if isinstance(v, dict):
                v_copy = dict(v)
                if 'nombre' not in v_copy: v_copy['nombre'] = k
                perfiles.append(v_copy)
    elif isinstance(raw_perfiles, list):
        perfiles = raw_perfiles

    try:
        target_dt = datetime.strptime(target_date_str, "%Y-%m-%d")
    except:
        return []

    day_num = (target_dt.weekday() + 1) % 7
    candidate_slots = []
    seen_hours = set()
    req_mod_clean = str(requested_modality or 'all').strip().lower()

    for perf in perfiles:
        perf_modalidad = str(perf.get('modalidad') or perf.get('nombre') or '').strip()
        perf_nombre = str(perf.get('nombre') or perf.get('modalidad') or '').strip()
        perf_mod_clean = perf_modalidad.lower()
        perf_nom_clean = perf_nombre.lower()

        if req_mod_clean not in ('all', ''):
            is_match = False
            if (req_mod_clean in perf_mod_clean or perf_mod_clean in req_mod_clean or
                req_mod_clean in perf_nom_clean or perf_nom_clean in req_mod_clean):
                is_match = True
            elif 'online' in req_mod_clean and ('online' in perf_mod_clean or 'online' in perf_nom_clean):
                is_match = True
            elif 'presencial' in req_mod_clean and ('presencial' in perf_mod_clean or 'presencial' in perf_nom_clean):
                is_match = True
            elif not any(restrictive in perf_nom_clean or restrictive in perf_mod_clean for restrictive in ['online', 'presencial', 'uptaeb']):
                is_match = True
            
            if not is_match:
                continue

        dias_list = perf.get('dias', [])
        for d in dias_list:
            d_num = int(d.get('dia', -1))
            is_today = (d_num == day_num) or (d_num in (0, 7) and day_num in (0, 7))
            if is_today and d.get('activo', False):
                rangos = d.get('rangos', [])
                for r in rangos:
                    inicio_str = r.get('inicio')
                    fin_str = r.get('fin')
                    if not inicio_str or not fin_str: continue
                    try:
                        start_time = datetime.strptime(inicio_str, "%H:%M")
                        end_time = datetime.strptime(fin_str, "%H:%M")

                        if start_time.hour < 7 and end_time.hour <= 12 and start_time.hour < end_time.hour:
                            start_time = start_time.replace(hour=start_time.hour + 12)
                            if end_time.hour < 12:
                                end_time = end_time.replace(hour=end_time.hour + 12)

                        curr = start_time
                        duration_td = timedelta(minutes=duracion)
                        recess_td = timedelta(minutes=receso)

                        while curr + duration_td <= end_time:
                            h_str = curr.strftime("%H:%M")
                            mod_label = perf_nombre or perf_modalidad or 'Online'
                            if h_str not in seen_hours:
                                seen_hours.add(h_str)
                                candidate_slots.append({
                                    'hora_literal': h_str,
                                    'hora_inicio': h_str,
                                    'hora_fin': (curr + duration_td).strftime("%H:%M"),
                                    'modalidad': mod_label,
                                    'perfil': perf_nombre
                                })
                            curr = curr + duration_td + recess_td
                    except Exception as _re:
                        print("Error calculando rango horario:", _re)

    # Filtrar horas ocupadas en la base de datos
    alt_date_str = target_date_str
    try:
        alt_date_str = target_dt.strftime("%d/%m/%Y")
    except: pass

    query_busy = """
        SELECT af.hora, af.id FROM agenda_finanzas af
        LEFT JOIN pacientes p ON af.paciente_id = p.id
        WHERE (af.fecha = ? OR af.fecha = ?)
          AND (p.psicologo_id = ? OR p.psicologo_id IS NULL OR ? IS NULL)
          AND (af.estado_pago IS NULL OR (af.estado_pago NOT LIKE 'Cancelada%' AND af.estado_pago != 'Reprogramada'))
    """
    cursor.execute(query_busy, (target_date_str, alt_date_str, psicologo_id, psicologo_id))
    busy_rows = cursor.fetchall()
    busy_hours = set()
    for br in busy_rows:
        if exclude_appt_id and br['id'] == exclude_appt_id:
            continue
        h_val = (br['hora'] or '').strip()
        if h_val:
            busy_hours.add(h_val[:5])

    # Bloqueos personales del psicólogo
    cursor.execute("""
        SELECT hora_inicio, hora_fin, todo_el_dia FROM bloqueos_agenda_especificos
        WHERE psicologo_id = ? AND fecha = ?
    """, (psicologo_id, target_date_str))
    blocks = cursor.fetchall()
    
    for blk in blocks:
        if blk['todo_el_dia'] == 1:
            return []
        b_in = blk['hora_inicio']
        b_fi = blk['hora_fin']
        if b_in and b_fi:
            for s in list(candidate_slots):
                if b_in <= s['hora_inicio'] < b_fi:
                    busy_hours.add(s['hora_literal'])

    now_dt = datetime.now()
    min_allowed_dt = now_dt + timedelta(hours=antelacion)

    valid_slots = []
    for slot in candidate_slots:
        h_lit = slot['hora_literal']
        if h_lit in busy_hours:
            continue
            
        slot_dt = datetime.strptime(f"{target_date_str} {h_lit}", "%Y-%m-%d %H:%M")
        if slot_dt < min_allowed_dt:
            continue

        slot['iso_timestamp'] = slot_dt.strftime("%Y-%m-%dT%H:%M:%S-04:00")
        slot['iso'] = slot['iso_timestamp']
        valid_slots.append(slot)

    valid_slots.sort(key=lambda x: x['hora_literal'])
    return valid_slots

def generate_default_slug_for_user(u):
    if not u:
        return 'psic.profesional'
    if isinstance(u, sqlite3.Row):
        u = dict(u)
    if u.get('slug'):
        return u.get('slug')
    nombres = u.get('nombres') or ''
    apellidos = u.get('apellidos') or ''
    full = f"{nombres} {apellidos}".strip().lower()
    if not full:
        full = u.get('username') or f"user{u.get('id', '1')}"
    clean = re.sub(r'[^a-z0-9]+', '.', full.lower()).strip('.')
    return f"psic.{clean}"

def get_psychologist_by_id_or_slug(cursor, identifier):
    """
    Busca un psicólogo en la tabla usuarios por ID (int) o por slug / username.
    """
    if not identifier:
        return None
    ident_str = str(identifier).strip()
    if ident_str.isdigit():
        cursor.execute("SELECT * FROM usuarios WHERE id = ?", (int(ident_str),))
        row = cursor.fetchone()
        if row:
            return dict(row)
    clean_slug = ident_str.lower().replace('psic.', '').replace('psic-', '').strip()
    cursor.execute("SELECT * FROM usuarios")
    rows = cursor.fetchall()
    for r in rows:
        r_dict = dict(r)
        uid = str(r_dict.get('id', ''))
        u_slug = str(r_dict.get('slug') or '').lower().replace('psic.', '').replace('psic-', '').strip()
        u_user = str(r_dict.get('username') or '').lower().replace('psic.', '').replace('psic-', '').strip()
        if ident_str == uid or clean_slug == u_slug or clean_slug == u_user:
            return r_dict
    for r in rows:
        r_dict = dict(r)
        u_slug = str(r_dict.get('slug') or '').lower()
        u_user = str(r_dict.get('username') or '').lower()
        if clean_slug and (clean_slug in u_slug or clean_slug in u_user or u_slug in clean_slug):
            return r_dict
    return None

@agenda_bp.route('/api/agenda/disponibilidad', methods=['GET'])
def get_agenda_disponibilidad():
    psicologo_id = request.args.get('psicologo_id')
    fecha_str = request.args.get('fecha')
    modalidad = request.args.get('modalidad', 'all')
    
    db = get_db()
    cursor = db.cursor()
    
    if psicologo_id:
        try:
            from app import get_psychologist_by_id_or_slug
            psych = get_psychologist_by_id_or_slug(cursor, psicologo_id)
            if psych: psicologo_id = psych['id']
        except Exception: pass

    if not psicologo_id and 'patient_id' in session:
        cursor.execute("SELECT psicologo_id FROM pacientes WHERE id = ?", (session['patient_id'],))
        p_row = cursor.fetchone()
        if p_row and p_row['psicologo_id']: psicologo_id = p_row['psicologo_id']
    if not psicologo_id and 'user_id' in session:
        psicologo_id = session['user_id']
    if not psicologo_id:
        cursor.execute("SELECT id FROM usuarios WHERE role != 'superadmin' AND activo = 1 ORDER BY id ASC LIMIT 1")
        first_u = cursor.fetchone()
        psicologo_id = first_u[0] if first_u else 1
        
    cursor.execute("SELECT configuracion_horarios_visual FROM usuarios WHERE id = ?", (psicologo_id,))
    u_row = cursor.fetchone()
    modalidades_list = ["Online", "Presencial"]
    if u_row and u_row[0]:
        try:
            config = json.loads(u_row[0])
            raw_perfiles = config.get('perfiles', [])
            if isinstance(raw_perfiles, dict):
                modalidades_list = list(raw_perfiles.keys())
            elif isinstance(raw_perfiles, list):
                m_found = [p.get('nombre') or p.get('modalidad') for p in raw_perfiles if (p.get('nombre') or p.get('modalidad'))]
                if m_found: modalidades_list = list(set(m_found))
        except: pass
            
    horas_disponibles = []
    slots = []
    if fecha_str:
        slots = generate_dynamic_slots(cursor, psicologo_id, fecha_str, modalidad)
        horas_disponibles = [s['hora_literal'] for s in slots]
        
    return jsonify({
        "modalidades": modalidades_list,
        "horas_disponibles": horas_disponibles,
        "slots": slots,
        "psicologo_timezone": "America/Caracas"
    })

@agenda_bp.route('/api/agenda', methods=['GET'])
@login_required
def get_agenda():
    db = get_db()
    cursor = db.cursor()
    psic_id = get_psicologo_id_filter()
    if psic_id is not None:
        cursor.execute("""
            SELECT af.*, p.nombres, p.apellidos, p.cedula, p.telefono, p.telefono as paciente_telefono,
                   (CASE WHEN EXISTS (
                       SELECT 1 FROM sesiones s 
                       WHERE s.agenda_id = af.id OR (s.paciente_id = af.paciente_id AND s.fecha = af.fecha)
                   ) THEN 1 ELSE 0 END) as has_session
            FROM agenda_finanzas af
            JOIN pacientes p ON af.paciente_id = p.id
            WHERE (af.hora != '00:00' AND af.hora != '' AND af.hora IS NOT NULL)
              AND p.psicologo_id = ?
            ORDER BY af.fecha ASC, af.hora ASC
        """, (psic_id,))
    else:
        cursor.execute("""
            SELECT af.*, p.nombres, p.apellidos, p.cedula, p.telefono, p.telefono as paciente_telefono,
                   (CASE WHEN EXISTS (
                       SELECT 1 FROM sesiones s 
                       WHERE s.agenda_id = af.id OR (s.paciente_id = af.paciente_id AND s.fecha = af.fecha)
                   ) THEN 1 ELSE 0 END) as has_session
            FROM agenda_finanzas af
            JOIN pacientes p ON af.paciente_id = p.id
            WHERE (af.hora != '00:00' AND af.hora != '' AND af.hora IS NOT NULL)
            ORDER BY af.fecha ASC, af.hora ASC
        """)
    events = [dict(row) for row in cursor.fetchall()]
    resp = jsonify(events)
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp

@agenda_bp.route('/api/agenda/blocks', methods=['GET', 'POST'])
@login_required
def manage_agenda_blocks():
    db = get_db()
    cursor = db.cursor()
    psic_id = get_psicologo_id_filter()
    user_id = session.get('user_id')
    target_psic_id = psic_id if psic_id is not None else user_id

    if request.method == 'POST':
        data = request.json or {}
        fecha = (data.get('fecha') or '').strip()
        hora_inicio = (data.get('hora_inicio') or '').strip()
        hora_fin = (data.get('hora_fin') or '').strip()
        motivo = (data.get('motivo') or 'Evento Personal / Bloqueo').strip()
        todo_el_dia = 1 if data.get('todo_el_dia') else 0

        if not fecha:
            return jsonify({'error': 'La fecha es obligatoria para agendar un evento personal / bloqueo.'}), 400

        google_event_id = None
        try:
            from routes_admin import get_calendar_service
            service = get_calendar_service(target_psic_id)
            if service:
                if todo_el_dia or not hora_inicio:
                    start_dict = {'date': fecha}
                    end_dict = {'date': fecha}
                else:
                    h_start = hora_inicio if len(hora_inicio) == 5 else f"{hora_inicio}:00"
                    h_end = hora_fin if hora_fin and len(hora_fin) == 5 else f"{h_start[:2]}:59"
                    start_dict = {'dateTime': f"{fecha}T{h_start}:00-04:00", 'timeZone': 'America/Caracas'}
                    end_dict = {'dateTime': f"{fecha}T{h_end}:00-04:00", 'timeZone': 'America/Caracas'}
                
                event_body = {
                    'summary': f"⛔ {motivo}",
                    'description': "Bloqueo de agenda / Evento personal en Espacio Terapéutico",
                    'start': start_dict,
                    'end': end_dict
                }
                g_event = service.events().insert(calendarId='primary', body=event_body).execute()
                google_event_id = g_event.get('id')
        except Exception as ge:
            print("Error sincronizando bloqueo con Google Calendar:", ge)

        cursor.execute("""
            INSERT INTO bloqueos_agenda_especificos (psicologo_id, fecha, hora_inicio, hora_fin, motivo, todo_el_dia)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (target_psic_id, fecha, hora_inicio, hora_fin, motivo, todo_el_dia))
        db.commit()
        block_id = cursor.lastrowid
        return jsonify({
            'success': 'Evento personal / bloqueo registrado correctamente.',
            'message': 'Evento personal / bloqueo registrado correctamente.',
            'google_synced': bool(google_event_id),
            'block': {
                'id': block_id,
                'psicologo_id': target_psic_id,
                'fecha': fecha,
                'hora_inicio': hora_inicio,
                'hora_fin': hora_fin,
                'motivo': motivo,
                'todo_el_dia': todo_el_dia
            }
        })

    cursor.execute("""
        SELECT * FROM bloqueos_agenda_especificos
        WHERE psicologo_id = ?
        ORDER BY fecha ASC, hora_inicio ASC
    """, (target_psic_id,))
    rows = [dict(r) for r in cursor.fetchall()]
    return jsonify(rows)

@agenda_bp.route('/api/agenda/blocks/<int:block_id>', methods=['DELETE'])
@login_required
def delete_agenda_block(block_id):
    db = get_db()
    cursor = db.cursor()
    psic_id = get_psicologo_id_filter()
    user_id = session.get('user_id')
    target_psic_id = psic_id if psic_id is not None else user_id

    cursor.execute("DELETE FROM bloqueos_agenda_especificos WHERE id = ? AND psicologo_id = ?", (block_id, target_psic_id))
    db.commit()
    return jsonify({'success': 'Bloqueo eliminado correctamente.', 'message': 'Bloqueo eliminado correctamente.'})

@agenda_bp.route('/api/agenda', methods=['POST'])
@login_required
def add_agenda_event():
    data = request.json or {}
    db = get_db()
    cursor = db.cursor()
    
    paciente_id = data.get('paciente_id')
    fecha = data.get('fecha')
    hora = data.get('hora')
    tipo_consulta = data.get('tipo_consulta', 'Presencial')
    consultorio_nombre = data.get('consultorio_nombre')
    creado_por_user_id = data.get('creado_por_user_id') or session.get('user_id')
    
    if not paciente_id or not fecha or not hora or not tipo_consulta:
        return jsonify({'error': 'Paciente, Fecha, Hora y Tipo de consulta son obligatorios.'}), 400

    if consultorio_nombre and str(consultorio_nombre).strip():
        cursor.execute("""
            SELECT id FROM agenda_finanzas 
            WHERE (fecha = ? OR fecha LIKE ?) 
              AND (hora = ? OR hora LIKE ?) 
              AND LOWER(TRIM(consultorio_nombre)) = LOWER(?)
              AND (estado_pago IS NULL OR (estado_pago NOT LIKE 'Cancelada%' AND estado_pago != 'Reprogramada'))
        """, (fecha, f"%{fecha}%", hora, f"{hora}%", str(consultorio_nombre).strip()))
        ocupado = cursor.fetchone()
        if ocupado:
            return jsonify({
                'error': f'🚫 El consultorio "{str(consultorio_nombre).strip()}" ya se encuentra reservado el {fecha} a las {hora}.'
            }), 400
        
    estado_pago = data.get('estado_pago', 'Agendada')
    monto = float(data.get('monto', 0.0) or 0.0)
    moneda = data.get('moneda', 'USD')
    control_uso = data.get('control_uso', 'Consumida')
    cantidad_sesiones = int(data.get('cantidad_sesiones', 1) or 1)
    referencia = data.get('referencia')
    metodo_pago = data.get('metodo_pago')
    fecha_pago = data.get('fecha_pago')
    confirmada = int(data.get('confirmada', 0) or 0)

    google_event_id = None
    try:
        from routes_admin import get_calendar_service
        service = get_calendar_service(creado_por_user_id)
        if service and paciente_id:
            cursor.execute("SELECT nombres, apellidos, email FROM pacientes WHERE id = ?", (paciente_id,))
            pac_row = cursor.fetchone()
            if pac_row:
                pac_nombre = f"{pac_row['nombres']} {pac_row['apellidos']}".strip()
                start_dt = f"{fecha}T{hora}:00-04:00"
                h_int = int(hora.split(':')[0]) + 1
                end_h = str(h_int).zfill(2) if h_int < 24 else "23"
                end_dt = f"{fecha}T{end_h}:{hora.split(':')[1]}:00-04:00"
                
                event_body = {
                    'summary': f"Consulta Psicológica - {pac_nombre}",
                    'description': f"Modalidad: {tipo_consulta}",
                    'start': {'dateTime': start_dt, 'timeZone': 'America/Caracas'},
                    'end': {'dateTime': end_dt, 'timeZone': 'America/Caracas'}
                }
                if pac_row['email']:
                    event_body['attendees'] = [{'email': pac_row['email'], 'displayName': pac_nombre}]
                
                g_event = service.events().insert(calendarId='primary', body=event_body, sendUpdates='all').execute()
                google_event_id = g_event.get('id')
    except Exception as ge:
        print("Error creando cita en Google Calendar:", ge)
    
    cursor.execute("""
        INSERT INTO agenda_finanzas (
            paciente_id, fecha, hora, tipo_consulta, monto, moneda, 
            estado_pago, control_uso, google_event_id, cantidad_sesiones,
            referencia, metodo_pago, fecha_pago, confirmada, consultorio_nombre, creado_por_user_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        paciente_id, fecha, hora, tipo_consulta, monto, moneda,
        estado_pago, control_uso, google_event_id, cantidad_sesiones,
        referencia, metodo_pago, fecha_pago, confirmada, consultorio_nombre, creado_por_user_id
    ))
    db.commit()
    event_id = cursor.lastrowid
    
    return jsonify({
        'success': 'Cita agendada exitosamente.',
        'message': 'Cita agendada exitosamente.',
        'google_synced': bool(google_event_id),
        'id': event_id
    })

@agenda_bp.route('/api/agenda/<int:event_id>', methods=['PUT', 'POST'])
@agenda_bp.route('/api/agenda/events/<int:event_id>', methods=['PUT', 'POST'])
@login_required
def update_agenda_event_status(event_id):
    data = request.json or {}
    db = get_db()
    cursor = db.cursor()
    
    estado = data.get('estado')
    confirmada = data.get('confirmada')
    estado_pago = data.get('estado_pago')
    
    updates = []
    params = []
    
    if confirmada is not None:
        updates.append("confirmada = ?")
        params.append(int(confirmada))
        
    if estado_pago is not None:
        updates.append("estado_pago = ?")
        params.append(estado_pago)
    elif estado == 'Confirmada':
        updates.append("confirmada = 1")
    elif estado == 'Cancelada':
        updates.append("estado_pago = 'Cancelada'")
        updates.append("confirmada = 0")
        
    if not updates:
        return jsonify({'success': True, 'message': 'Sin cambios'}), 200
        
    params.append(event_id)
    sql = f"UPDATE agenda_finanzas SET {', '.join(updates)} WHERE id = ?"
    cursor.execute(sql, params)
    db.commit()
    
    # Enviar mensaje de WhatsApp si se confirmó o canceló manualmente
    try:
        from routes_notificaciones import make_wa_http_request, format_whatsapp_message
        from routes_herramientas import clean_phone_number
        if confirmada == 1 or estado == 'Confirmada' or estado == 'Cancelada':
            cursor.execute("""
                SELECT p.telefono, p.nombres, p.apellidos, p.pais, af.fecha, af.hora, af.tipo_consulta, p.psicologo_id,
                       u.nombres as psic_nombres, u.apellidos as psic_apellidos
                FROM agenda_finanzas af 
                JOIN pacientes p ON af.paciente_id = p.id 
                LEFT JOIN usuarios u ON (p.psicologo_id = u.id OR (p.psicologo_id IS NULL AND u.id = 1))
                WHERE af.id = ?
            """, (event_id,))
            cita = cursor.fetchone()
            if cita and cita['telefono']:
                phone_clean = clean_phone_number(cita['telefono'])
                psych_id = cita['psicologo_id'] or session.get('user_id') or 1
                
                # Fetch templates
                cursor.execute("SELECT clave, valor FROM configuracion WHERE clave IN ('msg_confirmacion_ok', 'msg_cancelacion_ok')")
                templates = {r['clave']: r['valor'] for r in cursor.fetchall()}
                
                patient_dict = {
                    'nombres': cita['nombres'],
                    'apellidos': cita['apellidos'],
                    'pais': cita['pais'] or ''
                }
                cita_dict = {
                    'nombre': f"{cita['nombres']} {cita['apellidos']}".strip(),
                    'fecha': cita['fecha'],
                    'hora': cita['hora'],
                    'modalidad': cita['tipo_consulta'] or 'Presencial'
                }
                psicologo_data = {
                    'nombres': cita['psic_nombres'],
                    'apellidos': cita['psic_apellidos']
                }
                
                if confirmada == 1 or estado == 'Confirmada':
                    template = templates.get('msg_confirmacion_ok') or "¡Excelente! ✅ Tu cita ha sido confirmada exitosamente. Nos vemos pronto en Espacio Terapéutico."
                else:
                    template = templates.get('msg_cancelacion_ok') or "Entendido. ❌ Tu cita ha sido cancelada. Si deseas reagendar o tienes alguna duda, por favor contáctanos."
                
                msg = format_whatsapp_message(template, patient_dict, cita_dict, psicologo_data)
                
                make_wa_http_request('POST', '/send', json_data={'phone': phone_clean, 'text': msg, 'user_id': psych_id}, timeout=10, user_id=psych_id)
    except Exception as e:
        print("Error sending manual confirmation WA:", e)
    
    return jsonify({'success': True, 'message': 'Cita actualizada exitosamente.'})

@agenda_bp.route('/api/agenda/<int:event_id>', methods=['DELETE'])
@agenda_bp.route('/api/agenda/events/<int:event_id>', methods=['DELETE'])
@login_required
def delete_agenda_event(event_id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("DELETE FROM agenda_finanzas WHERE id = ?", (event_id,))
    db.commit()
    return jsonify({'message': 'Cita eliminada correctamente.'})

@agenda_bp.route('/api/admin/availability', methods=['GET', 'POST'])
@login_required
def admin_availability():
    db = get_db()
    cursor = db.cursor()
    import json
    
    default_visual = {
        "duracion": 60,
        "receso": 15,
        "antelacion": 24,
        "alerta_confirmacion": 24,
        "alerta_recordatorio": 2,
        "alerta_cierre": 2,
        "limite_cancelacion_tipo": "horas",
        "limite_cancelacion_valor": 24,
        "perfiles": [
            {
                "id": "default_online",
                "nombre": "Horario Online",
                "modalidad": "Online",
                "dias": [
                    {"dia": 1, "nombre": "Lunes", "activo": True, "rangos": [{"inicio": "12:00", "fin": "16:00"}, {"inicio": "18:00", "fin": "22:00"}]},
                    {"dia": 2, "nombre": "Martes", "activo": True, "rangos": [{"inicio": "18:00", "fin": "22:00"}]},
                    {"dia": 3, "nombre": "Miércoles", "activo": False, "rangos": []},
                    {"dia": 4, "nombre": "Jueves", "activo": False, "rangos": []},
                    {"dia": 5, "nombre": "Viernes", "activo": False, "rangos": []},
                    {"dia": 6, "nombre": "Sábado", "activo": False, "rangos": []},
                    {"dia": 0, "nombre": "Domingo", "activo": False, "rangos": []}
                ]
            },
            {
                "id": "default_presencial",
                "nombre": "Horario Presencial",
                "modalidad": "Presencial",
                "dias": [
                    {"dia": 1, "nombre": "Lunes", "activo": False, "rangos": []},
                    {"dia": 2, "nombre": "Martes", "activo": False, "rangos": []},
                    {"dia": 3, "nombre": "Miércoles", "activo": True, "rangos": [{"inicio": "08:00", "fin": "12:00"}]},
                    {"dia": 4, "nombre": "Jueves", "activo": True, "rangos": [{"inicio": "08:00", "fin": "12:00"}]},
                    {"dia": 5, "nombre": "Viernes", "activo": True, "rangos": [{"inicio": "08:00", "fin": "12:00"}]},
                    {"dia": 6, "nombre": "Sábado", "activo": False, "rangos": []},
                    {"dia": 0, "nombre": "Domingo", "activo": False, "rangos": []}
                ]
            }
        ]
    }

    if request.method == 'GET':
        cursor.execute("SELECT configuracion_horarios_visual, tipo_clinica, suscripcion_paga, organizacion_id FROM usuarios WHERE id = ?", (session.get('user_id'),))
        u_row = cursor.fetchone()

        org_name = ""
        if u_row and u_row['organizacion_id']:
            cursor.execute("SELECT nombre FROM organizaciones WHERE id = ?", (u_row['organizacion_id'],))
            o_row = cursor.fetchone()
            if o_row and o_row['nombre']:
                org_name = o_row['nombre']

        config = {}
        if u_row and u_row['configuracion_horarios_visual']:
            try:
                config = json.loads(u_row['configuracion_horarios_visual'])
            except Exception:
                pass

        if not isinstance(config, dict):
            config = {}

        perfiles = config.get('perfiles', [])
        if not isinstance(perfiles, list) or len(perfiles) == 0:
            perfiles = list(default_visual['perfiles'])

        # Si el usuario pertenece a una clínica/organización, garantizar que el perfil de clínica esté presente al inicio
        if u_row and u_row['organizacion_id']:
            org_id = u_row['organizacion_id']
            cursor.execute("SELECT nombre FROM organizaciones WHERE id = ?", (org_id,))
            o_row = cursor.fetchone()
            org_name = o_row['nombre'] if o_row and o_row['nombre'] else "Clínica"

            clinic_prof_id = f"perf_clinica_{org_id}"
            clinic_index = -1
            for idx, p in enumerate(perfiles):
                if p.get('id') == clinic_prof_id or p.get('es_horario_clinica'):
                    clinic_index = idx
                    break

            # Construir/Actualizar perfil de clínica desde la configuración visual
            DAY_MAP = [('domingo', 0, 'Domingo'), ('lunes', 1, 'Lunes'), ('martes', 2, 'Martes'), ('miercoles', 3, 'Miércoles'), ('jueves', 4, 'Jueves'), ('viernes', 5, 'Viernes'), ('sabado', 6, 'Sábado')]
            profile_dias = []
            primary_consultorio = "Consultorio 1"
            for key, dia_num, dia_name in DAY_MAP:
                day_cfg = config.get(key, {})
                is_active = bool(day_cfg.get('activo', False))
                inicio = day_cfg.get('inicio', '08:00')
                fin = day_cfg.get('fin', '17:00')
                if is_active and day_cfg.get('consultorio'):
                    primary_consultorio = day_cfg.get('consultorio')
                rangos = [{'inicio': inicio, 'fin': fin}] if is_active and inicio and fin else []
                profile_dias.append({'dia': dia_num, 'nombre': dia_name, 'activo': is_active, 'rangos': rangos})

            clinic_prof = {
                'id': clinic_prof_id,
                'nombre': f"Horario {org_name}",
                'modalidad': 'Presencial',
                'consultorio': primary_consultorio,
                'dias': profile_dias,
                'es_horario_clinica': True
            }

            if clinic_index >= 0:
                perfiles[clinic_index] = clinic_prof
            else:
                perfiles.insert(0, clinic_prof)

            # Si faltan los perfiles por defecto (Online/Presencial), asegurar que existan
            has_online = any(p.get('modalidad') == 'Online' or 'online' in (p.get('nombre') or '').lower() for p in perfiles)
            if not has_online:
                perfiles.append(default_visual['perfiles'][0])

            has_presencial_indep = any(not p.get('es_horario_clinica') and (p.get('modalidad') == 'Presencial' or 'presencial' in (p.get('nombre') or '').lower()) for p in perfiles)
            if not has_presencial_indep:
                perfiles.append(default_visual['perfiles'][1])

        config['perfiles'] = perfiles
        config['tipo_clinica'] = u_row['tipo_clinica'] if u_row else 0
        config['suscripcion_paga'] = u_row['suscripcion_paga'] if u_row else 0
        config['organizacion_nombre'] = org_name

        return jsonify(config)
    else:
        data = request.json or {}
        try:
            cursor.execute("UPDATE usuarios SET configuracion_horarios_visual = ? WHERE id = ?", (json.dumps(data), session.get('user_id')))
            db.commit()
            return jsonify({'success': 'Horarios y disponibilidad guardados con éxito.'})
        except Exception as e:
            return jsonify({'error': f'Error al guardar horarios: {str(e)}'}), 500

@agenda_bp.route('/api/active-psychologists', methods=['GET'])
def get_active_psychologists():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT id, nombres, apellidos, username, slug, role
        FROM usuarios
        WHERE role IN ('psicologo', 'admin', 'superadmin', 'psicologo_admin') AND COALESCE(activo, 1) = 1
        ORDER BY id ASC
    """)
    raw_rows = cursor.fetchall()
    result = []
    for r in raw_rows:
        r_dict = dict(r)
        slug = r_dict.get('slug') or generate_default_slug_for_user(r_dict)
        result.append({
            'id': r_dict['id'],
            'nombres': r_dict['nombres'],
            'apellidos': r_dict['apellidos'],
            'username': r_dict.get('username') or '',
            'slug': slug
        })
    return jsonify(result)

@agenda_bp.route('/api/psychologists/<identifier>/modalities', methods=['GET'])
def get_psychologist_modalities(identifier):
    db = get_db()
    cursor = db.cursor()
    psych = get_psychologist_by_id_or_slug(cursor, identifier)
    psic_id = psych['id'] if psych else 1
    cursor.execute("SELECT configuracion_horarios_visual FROM usuarios WHERE id = ?", (psic_id,))
    u_row = cursor.fetchone()
    modalities = ["Online", "Presencial"] # Default fallback
    if u_row and u_row[0]:
        try:
            import json
            config = json.loads(u_row[0])
            raw_perfiles = config.get('perfiles', [])
            if isinstance(raw_perfiles, dict):
                m_names = list(raw_perfiles.keys())
                if m_names:
                    modalities = m_names
            elif isinstance(raw_perfiles, list):
                m_names = [p.get('nombre') or p.get('modalidad') for p in raw_perfiles if (p.get('nombre') or p.get('modalidad'))]
                if m_names:
                    modalities = list(set(m_names))
        except:
            pass
    return jsonify(modalities)

@agenda_bp.route('/api/fast-booking/book', methods=['POST'])
def fast_booking_book():
    data = request.json
    psicologo_id = data.get('psicologo_id')
    fecha = data.get('fecha')
    hora = data.get('hora')
    modalidad = data.get('modalidad', 'Online')
    cedula = data.get('cedula', '').strip()
    nombres = data.get('nombres', '').strip()
    apellidos = data.get('apellidos', '').strip()
    telefono = data.get('telefono', '').strip()
    email = data.get('email', '').strip() or data.get('correo', '').strip()
    
    if not psicologo_id or not fecha or not hora or not cedula or not nombres:
        return jsonify({'error': 'Faltan campos requeridos para agendar.'}), 400
        
    db = get_db()
    cursor = db.cursor()

    psych = get_psychologist_by_id_or_slug(cursor, psicologo_id)
    if psych:
        psicologo_id = psych['id']

    fecha_norm = normalize_date_str(fecha)
    hora_norm = normalize_time_str(hora)
    alt_fecha = fecha_norm
    try:
        dt_tmp = datetime.strptime(fecha_norm, "%Y-%m-%d")
        alt_fecha = dt_tmp.strftime("%d/%m/%Y")
    except:
        pass

    # 0. Verificar si el horario seleccionado ya está reservado por cualquier consultante en ese psicólogo
    cursor.execute("""
        SELECT af.id FROM agenda_finanzas af
        LEFT JOIN pacientes p ON af.paciente_id = p.id
        WHERE (af.fecha = ? OR af.fecha = ?) 
          AND (af.hora = ? OR af.hora LIKE ?)
          AND (p.psicologo_id = ? OR p.psicologo_id IS NULL OR ? IS NULL)
          AND (af.estado_pago IS NULL OR (af.estado_pago NOT LIKE 'Cancelada%' AND af.estado_pago != 'Reprogramada'))
    """, (fecha_norm, alt_fecha, hora_norm, f"{hora_norm}%", psicologo_id, psicologo_id))
    if cursor.fetchone():
        return jsonify({'error': 'El horario seleccionado ya fue reservado. Por favor elige otro horario.'}), 400
    
    # 1. Verificar si el paciente existe por cédula limpia (dígitos), usuario o teléfono
    clean_cedula = cedula.strip()
    digits_cedula = re.sub(r'\D', '', clean_cedula) if clean_cedula else ''
    digits_telefono = re.sub(r'\D', '', telefono) if telefono else ''

    cursor.execute("""
        SELECT id, nombres, apellidos, telefono, email 
        FROM pacientes 
        WHERE (LOWER(REPLACE(REPLACE(REPLACE(REPLACE(cedula, 'V-', ''), 'E-', ''), '.', ''), ' ', '')) = ? AND ? != '')
           OR (LOWER(REPLACE(REPLACE(REPLACE(cedula, '.', ''), '-', ''), ' ', '')) = LOWER(REPLACE(REPLACE(REPLACE(?, '.', ''), '-', ''), ' ', '')))
           OR (LOWER(username) = LOWER(?) AND username != '')
    """, (digits_cedula, digits_cedula, clean_cedula, clean_cedula.lower()))
    patient = cursor.fetchone()
    
    is_new_patient = False
    if not patient:
        is_new_patient = True
        try:
            cursor.execute("""
                INSERT INTO pacientes (nombres, apellidos, cedula, telefono, email, psicologo_id)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (nombres, apellidos, cedula, telefono, email, psicologo_id))
            patient_id = cursor.lastrowid
            pac_nombre = f"{nombres} {apellidos}"
        except Exception as ex:
            return jsonify({'error': f'Error al registrar paciente automáticamente: {str(ex)}'}), 500
    else:
        patient_id = patient['id']
        pac_nombre = f"{patient['nombres']} {patient['apellidos']}"
        if email and not patient['email']:
            cursor.execute("UPDATE pacientes SET email = ? WHERE id = ?", (email, patient_id))
        
    try:
        google_event_id = None
        from routes_admin import get_calendar_service
        service = get_calendar_service(psicologo_id)
        if service:
            start_datetime = f"{fecha}T{hora}:00-04:00"
            end_hour = str(int(hora.split(':')[0]) + 1).zfill(2)
            end_datetime = f"{fecha}T{end_hour}:{hora.split(':')[1]}:00-04:00"
            
            # Obtener datos del psicólogo
            cursor.execute("SELECT nombres FROM usuarios WHERE id = ?", (psicologo_id,))
            u_row = cursor.fetchone()
            therapist_name = u_row['nombres'] if u_row else "Paulo Mora"
            
            event_body = {
                'summary': f"Consulta Psicológica - {pac_nombre}",
                'description': f"Modalidad: {modalidad}\nPsicólogo: Psic. {therapist_name}",
                'start': {'dateTime': start_datetime, 'timeZone': 'America/Caracas'},
                'end': {'dateTime': end_datetime, 'timeZone': 'America/Caracas'},
                'guestsCanInviteOthers': False,
                'reminders': {
                    'useDefault': False,
                    'overrides': [
                        { 'method': 'email', 'minutes': 1440 },
                        { 'method': 'popup', 'minutes': 60 }
                    ]
                }
            }
            # Agregar al paciente como invitado en Google Calendar para enviar invitación por correo
            email_paciente = data.get('email', '').strip() or data.get('correo', '').strip()
            if not email_paciente and patient:
                try:
                    email_paciente = patient['email'] if isinstance(patient, dict) and 'email' in patient else (patient[14] if len(patient) > 14 else None)
                except:
                    pass
            
            if email_paciente:
                event_body['attendees'] = [
                    {
                        'email': email_paciente,
                        'displayName': pac_nombre
                    }
                ]
            try:
                g_event = service.events().insert(calendarId='primary', body=event_body, sendUpdates='all').execute()
                google_event_id = g_event.get('id')
            except Exception as ge:
                print("Error creando evento en Google Calendar desde fast-booking:", ge)
                
        monto, moneda = get_appointment_fee(cursor, patient_id, psicologo_id, modalidad)
        
        cursor.execute("""
            INSERT INTO agenda_finanzas (
                paciente_id, fecha, hora, tipo_consulta, monto, moneda, 
                estado_pago, control_uso, google_event_id, cantidad_sesiones, referencia
            ) VALUES (?, ?, ?, ?, ?, ?, 'Agendada', 'No consumida', ?, 1, ?)
        """, (patient_id, fecha, hora, modalidad, monto, moneda, google_event_id, f"Auto-agendada rápida por paciente. Cédula: {cedula}"))
        
        # Enviar notificación al psicólogo en SQLite
        from datetime import datetime
        fecha_notif = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
            INSERT INTO notificaciones (user_id, tipo, titulo, mensaje, fecha, leida, link)
            VALUES (?, ?, ?, ?, ?, 0, ?)
        """, (psicologo_id, 'cita', 'Nueva Cita Agendada (Rápida)', f"{pac_nombre} ha auto-agendado una consulta para el {fecha} a las {hora}.", fecha_notif, 'agenda'))
        
        db.commit()

        # Enviar notificación WebPush al psicólogo
        try:
            from app import send_webpush_notification
            send_webpush_notification(
                user_id=psicologo_id,
                title="Nueva Cita Auto-Agendada",
                body=f"{pac_nombre} ha reservado una consulta para el {fecha} a las {hora}.",
                url="/?view=agenda"
            )
        except Exception as wp_ex:
            print("Error al enviar WebPush de auto-agendamiento:", wp_ex)
        
        # Sincronización en Firebase
        import threading
        threading.Thread(target=sync_patient_to_firebase, args=(patient_id,)).start()
        
        return jsonify({'success': 'Tu consulta ha sido agendada con éxito automáticamente.', 'google_synced': google_event_id is not None})
    except Exception as e:
        db.rollback()
        return jsonify({'error': f'Error al agendar consulta: {str(e)}'}), 500



@agenda_bp.route('/api/admin/consultation-history', methods=['GET'])
@login_required
def get_admin_consultation_history():
    try:
        user_id = session.get('user_id')
        month = request.args.get('month')
        year = request.args.get('year')
        
        if not month or not year:
            now = get_now_vet()
            month = f"{now.month:02d}"
            year = str(now.year)
        else:
            month = f"{int(month):02d}"
            year = str(year)
            
        date_prefix = f"{year}-{month}%"
        
        db = get_db()
        cursor = db.cursor()
        
        cursor.execute("""
            SELECT af.id, af.fecha, af.hora, af.tipo_consulta, af.monto, af.moneda,
                   af.estado_pago, af.control_uso, af.metodo_pago, af.referencia, af.fecha_liquidacion,
                   p.id as paciente_id, p.nombres, p.apellidos, p.cedula, p.telefono
            FROM agenda_finanzas af
            JOIN pacientes p ON af.paciente_id = p.id
            WHERE p.psicologo_id = ? AND (af.fecha LIKE ? OR af.fecha_liquidacion LIKE ?)
            ORDER BY af.fecha DESC, af.hora DESC
        """, (user_id, date_prefix, date_prefix))
        
        rows = [dict(r) for r in cursor.fetchall()]
        return jsonify(rows)
    except Exception as e:
        return jsonify({'error': f'Error al obtener historial de consultas: {str(e)}'}), 500



@agenda_bp.route('/api/admin/consultation-history/<int:event_id>', methods=['DELETE'])
@login_required
def delete_admin_consultation_history_event(event_id):
    try:
        user_id = session.get('user_id')
        db = get_db()
        cursor = db.cursor()

        role = session.get('role', '')
        is_admin = role in ['admin', 'superadmin'] or user_id == 1

        if is_admin:
            cursor.execute("""
                SELECT af.id, af.google_event_id, af.paciente_id 
                FROM agenda_finanzas af
                LEFT JOIN pacientes p ON af.paciente_id = p.id
                WHERE af.id = ?
            """, (event_id,))
        else:
            cursor.execute("""
                SELECT af.id, af.google_event_id, af.paciente_id 
                FROM agenda_finanzas af
                LEFT JOIN pacientes p ON af.paciente_id = p.id
                WHERE af.id = ? AND (p.psicologo_id = ? OR p.psicologo_id IS NULL OR af.paciente_id IS NULL)
            """, (event_id, user_id))
        row = cursor.fetchone()

        if not row:
            return jsonify({'error': 'Consulta no encontrada o sin permiso para eliminar.'}), 404

        google_event_id = row['google_event_id']
        paciente_id = row['paciente_id']

        if google_event_id:
            from routes_admin import get_calendar_service
            service = get_calendar_service(user_id)
            if service:
                try:
                    service.events().delete(calendarId='primary', eventId=google_event_id).execute()
                except Exception as ge:
                    print("Error al eliminar evento en Google Calendar:", ge)

        cursor.execute("DELETE FROM sesiones WHERE agenda_id = ?", (event_id,))
        cursor.execute("DELETE FROM agenda_finanzas WHERE id = ?", (event_id,))
        db.commit()

        if paciente_id:
            import threading
            threading.Thread(target=sync_patient_to_firebase, args=(paciente_id,)).start()

        return jsonify({'success': 'Consulta de prueba eliminada con éxito.'})
    except Exception as e:
        return jsonify({'error': f'Error al eliminar consulta: {str(e)}'}), 500


# --- RUTAS PÚBLICAS PARA CONFIRMACIÓN POR ENLACE ---

@agenda_bp.route('/cita/confirmar/<token>', methods=['GET'])
def vista_confirmar_cita(token):
    db = get_db()
    cursor = db.cursor()
    
    # Buscar la cita por token
    cursor.execute("""
        SELECT af.*, p.nombres, p.apellidos, u.nombres as psic_nombres, u.apellidos as psic_apellidos
        FROM agenda_finanzas af
        JOIN pacientes p ON af.paciente_id = p.id
        LEFT JOIN usuarios u ON p.psicologo_id = u.id
        WHERE af.token_confirmacion = ?
    """, (token,))
    cita = cursor.fetchone()
    
    if not cita:
        return render_template('cita_invalida.html', mensaje="El enlace proporcionado no es válido o la cita ya no existe.")
        
    from datetime import datetime
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    if cita['fecha'] < today_str:
        return render_template('cita_invalida.html', mensaje="Esta cita ya ocurrió y no puede ser modificada.")
        
    return render_template('confirmar_cita_public.html', cita=cita)

@agenda_bp.route('/api/cita/accion', methods=['POST'])
def accion_cita_publica():
    data = request.json or {}
    token = data.get('token')
    accion = data.get('accion') # 'confirmar', 'cancelar', 'reprogramar'
    
    if not token or accion not in ['confirmar', 'cancelar', 'reprogramar']:
        return jsonify({'error': 'Datos inválidos.'}), 400
        
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute("""
        SELECT af.id, af.paciente_id, af.fecha, af.hora, af.tipo_consulta, af.confirmada, af.estado_pago, p.nombres as pat_nombres, p.apellidos as pat_apellidos, p.telefono as pat_telefono, p.pais as pat_pais, p.psicologo_id,
               u.nombres as psic_nombres, u.apellidos as psic_apellidos, u.username as psic_username
        FROM agenda_finanzas af
        JOIN pacientes p ON af.paciente_id = p.id
        LEFT JOIN usuarios u ON p.psicologo_id = u.id
        WHERE af.token_confirmacion = ?
    """, (token,))
    cita = cursor.fetchone()
    
    if not cita:
        return jsonify({'error': 'Cita no encontrada.'}), 404
        
    appt_id = cita['id']
    psych_id = cita['psicologo_id'] or 1
    phone = cita['pat_telefono']
    
    fast_booking_url = f"https://www.espacioterapeutico.net/agendar/{cita['psic_username'] or 'psic.paulomora'}"
    
    # Prevenir doble-click
    if accion == 'confirmar' and cita['confirmada'] == 1:
        return jsonify({'success': True})
    if accion in ('cancelar', 'reprogramar') and cita['estado_pago'] == 'Cancelada':
        return jsonify({'success': True, 'fast_booking_url': fast_booking_url})
    
    # Preparamos datos para Whatsapp
    patient_dict = {
        'nombres': cita['pat_nombres'],
        'apellidos': cita['pat_apellidos'],
        'pais': cita['pat_pais'] or ''
    }
    cita_dict = {
        'nombre': f"{cita['pat_nombres']} {cita['pat_apellidos']}".strip(),
        'fecha': cita['fecha'],
        'hora': cita['hora'],
        'modalidad': cita['tipo_consulta'] or 'Presencial'
    }
    psicologo_data = {
        'nombres': cita['psic_nombres'],
        'apellidos': cita['psic_apellidos']
    }
    
    cursor.execute("SELECT clave, valor FROM configuracion WHERE clave IN ('msg_confirmacion_ok', 'msg_cancelacion_ok', 'msg_reagendamiento')")
    cfg_rows = {r['clave']: r['valor'] for r in cursor.fetchall()}
    
    template = ""
    
    if accion == 'confirmar':
        cursor.execute("UPDATE agenda_finanzas SET confirmada = 1 WHERE id = ?", (appt_id,))
        template = cfg_rows.get('msg_confirmacion_ok') or "¡Excelente! ✅ Tu cita ha sido confirmada exitosamente. Nos vemos pronto."
        
    elif accion == 'cancelar':
        cursor.execute("UPDATE agenda_finanzas SET estado_pago = 'Cancelada', confirmada = 0 WHERE id = ?", (appt_id,))
        template = cfg_rows.get('msg_cancelacion_ok') or "Entendido. ❌ Tu cita ha sido cancelada. Si deseas reagendar, por favor contáctanos."
        
    elif accion == 'reprogramar':
        cursor.execute("UPDATE agenda_finanzas SET estado_pago = 'Cancelada', confirmada = 0 WHERE id = ?", (appt_id,))
        template = cfg_rows.get('msg_reagendamiento') or "Hemos recibido tu solicitud para reprogramar. Pronto nos pondremos en contacto contigo para agendar un nuevo espacio."
        
    db.commit()
    
    import threading
    def _background_tasks():
        if phone:
            try:
                from routes_notificaciones import make_wa_http_request, format_whatsapp_message
                from routes_herramientas import clean_phone_number
                msg = format_whatsapp_message(template, patient_dict, cita_dict, psicologo_data)
                clean_phone = clean_phone_number(phone)
                # Marcar en DB como enviado para evitar duplicado con el cron
                db_bg = sqlite3.connect('clinica.db')
                db_bg.row_factory = sqlite3.Row
                if accion == 'cancelar' or accion == 'reprogramar':
                    db_bg.execute("UPDATE agenda_finanzas SET cierre_enviado_wa = 1 WHERE id = ?", (appt_id,))
                elif accion == 'confirmar':
                    db_bg.execute("UPDATE agenda_finanzas SET respuesta_enviada_wa = 1 WHERE id = ?", (appt_id,))
                db_bg.commit()
                db_bg.close()
                make_wa_http_request('POST', '/send', json_data={'phone': clean_phone, 'text': msg, 'user_id': psych_id}, timeout=15, user_id=psych_id)
            except Exception as e:
                print("Error enviando confirmacion WA desde public link:", e)
                
        try:
            from app import push_all_data_to_firebase
            push_all_data_to_firebase()
        except Exception as e:
            print("Error en push_all_data_to_firebase:", e)
            
    threading.Thread(target=_background_tasks, daemon=True).start()
        
    return jsonify({'success': True, 'fast_booking_url': fast_booking_url})

@agenda_bp.route('/api/fast-booking/check-cedula', methods=['POST'])
def fast_booking_check_cedula():
    data = request.json or {}
    cedula = data.get('cedula', '').strip()
    if not cedula:
        return jsonify({'found': False})
    
    db = get_db()
    cursor = db.cursor()
    import re
    digits_cedula = re.sub(r'\D', '', cedula)
    
    cursor.execute('''
        SELECT nombres, apellidos, telefono, email 
        FROM pacientes 
        WHERE (LOWER(REPLACE(REPLACE(REPLACE(REPLACE(cedula, 'V-', ''), 'E-', ''), '.', ''), ' ', '')) = ? AND ? != '') 
           OR (LOWER(REPLACE(REPLACE(REPLACE(cedula, '.', ''), '-', ''), ' ', '')) = ?)
        LIMIT 1
    ''', (digits_cedula, digits_cedula, cedula.lower()))
    
    row = cursor.fetchone()
    if row:
        return jsonify({
            'found': True,
            'nombres': row['nombres'],
            'apellidos': row['apellidos'],
            'telefono': row['telefono'],
            'email': row['email']
        })
    return jsonify({'found': False})
