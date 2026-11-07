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
def _update_google_calendar_status_bg(event_id, status, motivo=None):
    """
    Actualiza el estado de la cita en Google Calendar en background con colores y prefijos visuales.
    status: 'esperando'/'pendiente', 'confirmada', 'cancelada'
    NUNCA borra el evento de Google Calendar.
    """
    import os, sys
    import sqlite3
    import threading
    from routes_admin import get_calendar_service, update_calendar_event_status

    def run():
        try:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            db_path = os.path.join(base_dir, 'clinica.db')
            db = sqlite3.connect(db_path, timeout=30.0)
            db.row_factory = sqlite3.Row
            cursor = db.cursor()
            
            cursor.execute("""
                SELECT af.id, af.fecha, af.hora, af.google_event_id, af.tipo_consulta, p.psicologo_id, 
                       af.creado_por_user_id, p.nombres, p.apellidos, p.email, p.cedula
                FROM agenda_finanzas af
                LEFT JOIN pacientes p ON af.paciente_id = p.id
                WHERE af.id = ?
            """, (event_id,))
            cita = cursor.fetchone()
            if not cita:
                db.close()
                return

            google_event_id = cita['google_event_id']
            psych_id = cita['psicologo_id'] or cita['creado_por_user_id'] or 1
            pac_nombre = f"{cita['nombres'] or ''} {cita['apellidos'] or ''}".strip()
            
            service = get_calendar_service(psych_id, db=db)
            if not service and cita['creado_por_user_id']:
                service = get_calendar_service(cita['creado_por_user_id'], db=db)
            if not service:
                service = get_calendar_service(1, db=db)

            if service:
                if google_event_id:
                    update_calendar_event_status(
                        service, google_event_id, status,
                        paciente_nombre=pac_nombre,
                        tipo_consulta=cita['tipo_consulta'],
                        motivo=motivo
                    )
                else:
                    # Si no tenía google_event_id, crear el evento directamente con el estatus correcto
                    norm_st = (status or 'pendiente').lower().strip()
                    status_map = {
                        'pendiente': {'colorId': '6', 'prefix': '🟠'},
                        'esperando': {'colorId': '6', 'prefix': '🟠'},
                        'confirmada': {'colorId': '10', 'prefix': '🟢'},
                        'cancelada': {'colorId': '11', 'prefix': '🔴'}
                    }
                    st_info = status_map.get(norm_st, status_map['pendiente'])
                    
                    hora_str = str(cita['hora']).strip()
                    h_parts = hora_str.split(':')
                    h_int = int(h_parts[0]) if (h_parts and h_parts[0].isdigit()) else 0
                    end_h = str(h_int + 1).zfill(2) if h_int < 23 else "23"
                    m_part = h_parts[1].split(' ')[0] if len(h_parts) > 1 else "00"
                    
                    start_dt = f"{cita['fecha']}T{str(h_int).zfill(2)}:{m_part}:00-04:00"
                    end_dt = f"{cita['fecha']}T{end_h}:{m_part}:00-04:00"
                    
                    event_body = {
                        'summary': f"{st_info['prefix']} Consulta Psicológica - {pac_nombre}",
                        'colorId': st_info['colorId'],
                        'description': f"Modalidad: {cita['tipo_consulta']}\nMotivo/Nota: {motivo or ''}".strip(),
                        'start': {'dateTime': start_dt, 'timeZone': 'America/Caracas'},
                        'end': {'dateTime': end_dt, 'timeZone': 'America/Caracas'}
                    }
                    if cita['email'] and '@' in cita['email'] and '.' in cita['email']:
                        event_body['attendees'] = [{'email': cita['email'].strip(), 'displayName': pac_nombre}]
                    try:
                        g_event = service.events().insert(calendarId='primary', body=event_body).execute()
                        new_gid = g_event.get('id')
                        if new_gid:
                            cursor.execute("UPDATE agenda_finanzas SET google_event_id = ? WHERE id = ?", (new_gid, event_id))
                            db.commit()
                    except Exception as ins_err:
                        print("Error al insertar evento en Google Calendar desde background sync:", ins_err)
                    
            db.close()
        except Exception as e:
            print("Error fatal GC sync status:", e)

    threading.Thread(target=run, daemon=True).start()


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
    if t_str in ('00:00', '0:00', '00:00:00'):
        return "00:00"
    is_pm = 'pm' in t_str or 'p.m.' in t_str or 'tarde' in t_str or 'noche' in t_str
    is_am = 'am' in t_str or 'a.m.' in t_str or 'mañana' in t_str
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
        elif not is_am and not is_pm and 1 <= h <= 6:
            # En contexto clínico de consultas, horas escritas como "2:00" o "4:30" (sin AM/PM y sin cero inicial) corresponden a la tarde (14:00 o 16:30)
            # Pero horas con cero explícito a la izquierda como "06:00" o "05:00" son formato 24h de la mañana
            if not parts[0].startswith('0'):
                h += 12
        return f"{h:02d}:{m:02d}"
    except:
        return "00:00"

def convert_time_vet_to_tz(fecha_str, hora_str, target_tz_str):
    """
    Convierte una fecha y hora dada en zona de Venezuela (America/Caracas, GMT-4)
    a la zona horaria del paciente (target_tz_str). Retorna la hora en formato HH:MM.
    """
    if not hora_str:
        return "00:00"
    if not target_tz_str or target_tz_str == 'America/Caracas':
        return normalize_time_str(hora_str)
    try:
        import zoneinfo
        norm_f = normalize_date_str(fecha_str) if fecha_str else datetime.now().strftime("%Y-%m-%d")
        norm_h = normalize_time_str(hora_str)
        tz_vet = zoneinfo.ZoneInfo("America/Caracas")
        tz_target = zoneinfo.ZoneInfo(target_tz_str)
        dt_vet = datetime.strptime(f"{norm_f} {norm_h}", "%Y-%m-%d %H:%M").replace(tzinfo=tz_vet)
        dt_target = dt_vet.astimezone(tz_target)
        return dt_target.strftime("%H:%M")
    except Exception:
        return normalize_time_str(hora_str)

def get_appointment_fee(cursor, patient_id, psicologo_id=None, modalidad=None):
    """Calcula la tarifa (monto y moneda) para una consulta."""
    monto = 0.0
    moneda = 'USD'
    if patient_id:
        cursor.execute("SELECT costo_personalizado, moneda_personalizada FROM pacientes WHERE id = ?", (patient_id,))
        row = cursor.fetchone()
        if row:
            if row['costo_personalizado'] is not None and row['costo_personalizado'] > 0:
                monto = float(row['costo_personalizado'])
            if row['moneda_personalizada']:
                moneda = row['moneda_personalizada']
    if (monto == 0.0 or not moneda or moneda == '$') and psicologo_id:
        try:
            cursor.execute("SELECT configuracion_horarios_visual FROM usuarios WHERE id = ?", (psicologo_id,))
            u_r = cursor.fetchone()
            if u_r and u_r['configuracion_horarios_visual']:
                import json
                vis = json.loads(u_r['configuracion_horarios_visual'])
                for p in vis.get('perfiles', []):
                    if modalidad and (p.get('nombre') == modalidad or p.get('modalidad') == modalidad):
                        if p.get('costo') is not None and float(p.get('costo')) > 0:
                            monto = float(p.get('costo'))
                            moneda = p.get('moneda') or moneda
                            break
        except Exception:
            pass
    if monto == 0.0:
        monto = 35.0
        moneda = 'USD'
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

def get_appointment_duration_and_recess(tipo_consulta, perfiles, default_duracion=60, default_receso=0):
    tipo_clean = (tipo_consulta or '').strip().lower()
    if not tipo_clean:
        return default_duracion, default_receso

    # 1. Coincidencia exacta (por ID único de perfil, nombre o modalidad)
    for p in perfiles:
        p_id = str(p.get('id') or '').strip().lower()
        p_name = (p.get('nombre') or p.get('modalidad') or '').strip().lower()
        p_mod = (p.get('modalidad') or p.get('nombre') or '').strip().lower()
        if (p_id and tipo_clean == p_id) or tipo_clean == p_name or tipo_clean == p_mod:
            try:
                dur = int(p.get('duracion')) if p.get('duracion') is not None and str(p.get('duracion')).strip() != '' else default_duracion
            except: dur = default_duracion
            try:
                rec = int(p.get('receso')) if p.get('receso') is not None and str(p.get('receso')).strip() != '' else default_receso
            except: rec = default_receso
            return dur, rec

    # 2. Coincidencia secundaria si no hubo exacta
    for p in perfiles:
        p_id = str(p.get('id') or '').strip().lower()
        p_name = (p.get('nombre') or p.get('modalidad') or '').strip().lower()
        p_mod = (p.get('modalidad') or p.get('nombre') or '').strip().lower()
        if (tipo_clean in p_name or p_name in tipo_clean or tipo_clean in p_mod or p_mod in tipo_clean):
            try:
                dur = int(p.get('duracion')) if p.get('duracion') is not None and str(p.get('duracion')).strip() != '' else default_duracion
            except: dur = default_duracion
            try:
                rec = int(p.get('receso')) if p.get('receso') is not None and str(p.get('receso')).strip() != '' else default_receso
            except: rec = default_receso
            return dur, rec
    return default_duracion, default_receso

def check_appointment_interval_collision(cursor, psicologo_id, fecha, hora, tipo_consulta, exclude_appt_id=None, duracion_override=None):
    """
    Verifica si una consulta a programarse colisiona en horario (por coincidencia exacta o solapamiento de intervalos)
    con cualquier otra consulta activa del psicólogo.
    Retorna True si hay colisión, False si el espacio está libre.
    """
    if not fecha or not hora:
        return False
    hora_clean = normalize_time_str(hora)
    if hora_clean == '00:00':
        return False

    try:
        req_start = datetime.strptime(hora_clean, "%H:%M")
    except:
        return False

    try:
        psic_id_int = int(psicologo_id) if psicologo_id is not None else 1
    except:
        psic_id_int = 1

    cursor.execute("SELECT configuracion_horarios_visual FROM usuarios WHERE id = ?", (psic_id_int,))
    u_row = cursor.fetchone()
    cfg_perfiles = []
    cfg_dur = 60
    cfg_rec = 0
    if u_row:
        raw_cfg = u_row['configuracion_horarios_visual'] if (isinstance(u_row, dict) or hasattr(u_row, 'keys')) else u_row[0]
        if raw_cfg:
            try:
                cfg = json.loads(raw_cfg)
                cfg_dur = int(cfg.get('duracion', 60))
                cfg_rec = int(cfg.get('receso', 0))
                raw_p = cfg.get('perfiles', [])
                if isinstance(raw_p, dict):
                    cfg_perfiles = list(raw_p.values())
                elif isinstance(raw_p, list):
                    cfg_perfiles = raw_p
            except: pass

    if duracion_override:
        req_dur = int(duracion_override)
        req_rec = cfg_rec
    else:
        req_dur, req_rec = get_appointment_duration_and_recess(tipo_consulta, cfg_perfiles, cfg_dur, cfg_rec)

    req_end = req_start + timedelta(minutes=req_dur)
    req_busy_until = req_end + timedelta(minutes=req_rec)

    f_norm = normalize_date_str(fecha)
    alt_f = f_norm
    try:
        dt_t = datetime.strptime(f_norm, "%Y-%m-%d")
        alt_f = dt_t.strftime("%d/%m/%Y")
    except:
        try:
            dt_t = datetime.strptime(f_norm, "%d/%m/%Y")
            alt_f = dt_t.strftime("%Y-%m-%d")
        except: pass

    query = """
        SELECT af.id, af.fecha, af.hora, af.tipo_consulta, af.cantidad_sesiones
        FROM agenda_finanzas af
        LEFT JOIN pacientes p ON af.paciente_id = p.id
        WHERE (af.fecha = ? OR af.fecha = ? OR TRIM(af.fecha) = ? OR TRIM(af.fecha) = ?)
          AND (p.psicologo_id = ? OR af.creado_por_user_id = ? OR (p.psicologo_id IS NULL AND af.creado_por_user_id IS NULL) OR ? IS NULL)
          AND (af.estado_pago IS NULL OR (af.estado_pago NOT LIKE 'Cancelada%' AND af.estado_pago != 'Reprogramada'))
    """
    cursor.execute(query, (f_norm, alt_f, f_norm, alt_f, psic_id_int, psic_id_int, psic_id_int))
    existing = cursor.fetchall()

    for ea in existing:
        if exclude_appt_id and ea['id'] == exclude_appt_id:
            continue
        raw_ea_h = str(ea['hora'] or '').strip()
        if not raw_ea_h or raw_ea_h == '00:00':
            continue
        ea_h_clean = normalize_time_str(raw_ea_h)
        if ea_h_clean == '00:00':
            continue
        try:
            ea_start = datetime.strptime(ea_h_clean, "%H:%M")
            ea_dur, ea_rec = get_appointment_duration_and_recess(ea['tipo_consulta'], cfg_perfiles, cfg_dur, cfg_rec)
            ea_cant = int(ea['cantidad_sesiones'] or 1)
            ea_total_dur = ea_dur * ea_cant
            ea_end = ea_start + timedelta(minutes=ea_total_dur)
            ea_busy_until = ea_end + timedelta(minutes=ea_rec)

            # Colisión: solapamiento directo del intervalo de sesión y receso
            if req_start < ea_busy_until and req_busy_until > ea_start:
                return True
        except Exception as _e_ea:
            pass

    return False

def generate_dynamic_slots(cursor, psicologo_id, target_date_str, requested_modality='all', exclude_appt_id=None):
    """
    Genera dinámicamente los slots de disponibilidad a partir de configuracion_horarios_visual.
    Aplica recálculo dinámico continuo por ventanas libres (Floating Slots):
    Si una consulta previa termina a una hora (ej. 13:00 + 60m + 5m receso = 14:05),
    la siguiente ventana libre comienza inmediatamente a las 14:05, recalculando los turnos
    consecutivos según la duración y el receso del perfil solicitado sin perder tiempo muerto.
    """
    try:
        psic_id_int = int(psicologo_id) if (psicologo_id is not None and str(psicologo_id).isdigit()) else 1
    except:
        psic_id_int = 1

    cursor.execute("SELECT configuracion_horarios_visual FROM usuarios WHERE id = ?", (psic_id_int,))
    u_row = cursor.fetchone()
    
    config = {}
    raw_u_cfg = (u_row['configuracion_horarios_visual'] if hasattr(u_row, 'keys') else u_row[0]) if u_row else None
    if raw_u_cfg:
        try:
            config = json.loads(raw_u_cfg)
        except: pass

    if not config:
        cursor.execute("SELECT valor FROM configuracion WHERE clave = 'configuracion_horarios_visual'")
        row = cursor.fetchone()
        raw_val = (row['valor'] if hasattr(row, 'keys') else row[0]) if row else None
        if raw_val:
            try:
                config = json.loads(raw_val)
            except: pass

    try:
        duracion = int(config.get('duracion') or 60)
    except: duracion = 60
    try:
        receso = int(config.get('receso') or 0)
    except: receso = 0
    try:
        antelacion = int(config.get('antelacion') or 24)
    except: antelacion = 24
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

    # Auto-healing runtime: asegurar que cada perfil tenga su ID único con prefijo de psicólogo
    for idx, p in enumerate(perfiles):
        p_id = str(p.get('id') or '').strip()
        if not p_id or (not p_id.startswith(f"p_{psic_id_int}_") and not p.get('es_horario_clinica')):
            p['id'] = f"p_{psic_id_int}_{idx + 1}"

    try:
        target_dt = datetime.strptime(target_date_str, "%Y-%m-%d")
    except:
        return []

    day_num = (target_dt.weekday() + 1) % 7
    req_mod_clean = str(requested_modality or 'all').strip().lower()

    # 1. Obtener todas las citas activas del psicólogo para la fecha objetivo
    alt_date_str = target_date_str
    try:
        alt_date_str = target_dt.strftime("%d/%m/%Y")
    except: pass

    query_busy = """
        SELECT af.hora, af.id, af.tipo_consulta, af.cantidad_sesiones FROM agenda_finanzas af
        LEFT JOIN pacientes p ON af.paciente_id = p.id
        WHERE (af.fecha = ? OR af.fecha = ? OR TRIM(af.fecha) = ? OR TRIM(af.fecha) = ?)
          AND (p.psicologo_id = ? OR af.creado_por_user_id = ? OR (p.psicologo_id IS NULL AND af.creado_por_user_id IS NULL) OR ? IS NULL)
          AND (af.estado_pago IS NULL OR (af.estado_pago NOT LIKE 'Cancelada%' AND af.estado_pago != 'Reprogramada'))
    """
    cursor.execute(query_busy, (target_date_str, alt_date_str, target_date_str, alt_date_str, psic_id_int, psic_id_int, psic_id_int))
    busy_rows = cursor.fetchall()

    base_busy_intervals = []
    for br in busy_rows:
        if exclude_appt_id and br['id'] == exclude_appt_id:
            continue
        raw_h = (br['hora'] or '').strip()
        if not raw_h or raw_h == '00:00':
            continue
        h_norm = normalize_time_str(raw_h)
        if h_norm == '00:00':
            continue
        try:
            b_start = datetime.strptime(h_norm, "%H:%M")
            b_dur, b_rec = get_appointment_duration_and_recess(br['tipo_consulta'], perfiles, duracion, receso)
            b_cant = int(br['cantidad_sesiones'] or 1)
            b_total_dur = b_dur * b_cant
            b_end = b_start + timedelta(minutes=b_total_dur)
            b_busy_until = b_end + timedelta(minutes=b_rec)
            base_busy_intervals.append({
                'start': b_start,
                'end': b_end,
                'busy_until': b_busy_until,
                'tipo_consulta': br['tipo_consulta']
            })
        except Exception:
            pass

    # 2. Obtener bloqueos personales y específicos
    try:
        cursor.execute("PRAGMA table_info(bloqueos_agenda_especificos)")
        cols_b = [c[1] for c in cursor.fetchall()]
        if 'modalidad' not in cols_b:
            cursor.execute("ALTER TABLE bloqueos_agenda_especificos ADD COLUMN modalidad TEXT DEFAULT 'Todas'")
        if 'fecha_fin' not in cols_b:
            cursor.execute("ALTER TABLE bloqueos_agenda_especificos ADD COLUMN fecha_fin TEXT")
        db.commit()
    except:
        pass

    cursor.execute("""
        SELECT hora_inicio, hora_fin, todo_el_dia, modalidad, fecha, fecha_fin 
        FROM bloqueos_agenda_especificos
        WHERE psicologo_id = ? 
          AND (fecha = ? OR (fecha_fin IS NOT NULL AND fecha_fin != '' AND fecha <= ? AND fecha_fin >= ?))
    """, (ps_id := psic_id_int, target_date_str, target_date_str, target_date_str))
    blocks_rows = cursor.fetchall()

    candidate_slots = []
    seen_keys = set()
    now_dt = datetime.now()

    # 3. Determinar si existe coincidencia para la modalidad o perfil solicitado
    # Prioridad 1: Coincidencia EXACTA por ID único e inconmutable de perfil (ej. p_1_3)
    id_matches = []
    exact_name_matches = []
    if req_mod_clean not in ('all', ''):
        for perf in perfiles:
            perf_id = str(perf.get('id') or '').strip().lower()
            perf_modalidad = str(perf.get('modalidad') or perf.get('nombre') or '').strip().lower()
            perf_nombre = str(perf.get('nombre') or perf.get('modalidad') or '').strip().lower()
            if perf_id and req_mod_clean == perf_id:
                id_matches.append(perf)
            elif req_mod_clean == perf_modalidad or req_mod_clean == perf_nombre:
                exact_name_matches.append(perf)

    exact_matches = id_matches if id_matches else exact_name_matches

    # Iterar cada perfil configurado
    for perf in perfiles:
        perf_modalidad = str(perf.get('modalidad') or perf.get('nombre') or '').strip()
        perf_nombre = str(perf.get('nombre') or perf.get('modalidad') or '').strip()
        perf_mod_clean = perf_modalidad.lower()
        perf_nom_clean = perf_nombre.lower()

        if req_mod_clean not in ('all', ''):
            if exact_matches:
                # Si hay coincidencia exacta (ej. 'UPTAEB Online' vs 'UPTAEB' vs 'Online'),
                # ÚNICAMENTE evaluar ese perfil exacto para evitar mezclas o solapamientos.
                if perf not in exact_matches:
                    continue
            else:
                # Si ningún perfil coincide exactamente (ej. la solicitud viene como 'Consulta Online' o 'Horario Presencial'):
                norm_req = req_mod_clean
                for prefix in ('consulta ', 'horario ', 'sesion ', 'sesión ', 'atencion ', 'atención '):
                    if norm_req.startswith(prefix):
                        norm_req = norm_req[len(prefix):].strip()

                norm_perf = perf_nom_clean
                for prefix in ('consulta ', 'horario ', 'sesion ', 'sesión ', 'atencion ', 'atención '):
                    if norm_perf.startswith(prefix):
                        norm_perf = norm_perf[len(prefix):].strip()

                is_match = False
                if norm_req == norm_perf or norm_req == perf_mod_clean:
                    is_match = True
                else:
                    # Comprobación de palabras clave respetando sub-modalidades:
                    # Si la solicitud incluye 'uptaeb', SOLO puede coincidir con perfiles 'uptaeb'
                    req_is_uptaeb = 'uptaeb' in req_mod_clean
                    perf_is_uptaeb = ('uptaeb' in perf_nom_clean or 'uptaeb' in perf_mod_clean)

                    if req_is_uptaeb != perf_is_uptaeb:
                        is_match = False
                    elif 'online' in req_mod_clean and ('online' in perf_mod_clean or 'online' in perf_nom_clean):
                        is_match = True
                    elif 'presencial' in req_mod_clean and ('presencial' in perf_mod_clean or 'presencial' in perf_nom_clean):
                        is_match = True
                    elif not any(restrictive in perf_nom_clean or restrictive in perf_mod_clean for restrictive in ['online', 'presencial', 'uptaeb']):
                        is_match = True

                if not is_match:
                    continue

        # Parámetros específicos de la modalidad
        p_dur = perf.get('duracion')
        p_rec = perf.get('receso')
        p_ant = perf.get('antelacion')
        
        try:
            perf_duracion = int(p_dur) if p_dur is not None and str(p_dur).strip() != '' else duracion
        except:
            perf_duracion = duracion
            
        try:
            perf_receso = int(p_rec) if p_rec is not None and str(p_rec).strip() != '' else receso
        except:
            perf_receso = receso
            
        try:
            perf_antelacion = int(p_ant) if p_ant is not None and str(p_ant).strip() != '' else antelacion
        except:
            perf_antelacion = antelacion

        duration_td = timedelta(minutes=perf_duracion)
        recess_td = timedelta(minutes=perf_receso)

        # Evaluar bloqueos aplicables a este perfil
        perf_blocks = []
        is_all_day_blocked = False
        for blk in blocks_rows:
            blk_dict = dict(blk)
            blk_mod = (blk_dict.get('modalidad') or 'Todas').strip().lower()
            is_all_mod = blk_mod in ('todas', 'all', '', 'todas las modalidades')
            if is_all_mod:
                mod_match = True
            elif blk_mod == perf_nom_clean or blk_mod == perf_mod_clean:
                mod_match = True
            else:
                blk_is_online = 'online' in blk_mod
                blk_is_presencial = 'presencial' in blk_mod
                perf_is_online = ('online' in perf_mod_clean or 'online' in perf_nom_clean)
                perf_is_presencial = ('presencial' in perf_mod_clean or 'presencial' in perf_nom_clean)

                if blk_mod == 'online' and not perf_is_online:
                    mod_match = False
                elif blk_mod == 'presencial' and not perf_is_presencial:
                    mod_match = False
                elif 'uptaeb' in blk_mod and ('uptaeb' not in perf_nom_clean and 'uptaeb' not in perf_mod_clean):
                    mod_match = False
                elif blk_is_online != perf_is_online and ('online' in blk_mod or 'online' in perf_nom_clean):
                    mod_match = False
                else:
                    mod_match = (blk_mod in perf_nom_clean or perf_nom_clean in blk_mod or blk_mod in perf_mod_clean or perf_mod_clean in blk_mod)
            if not mod_match:
                continue
            if blk_dict.get('todo_el_dia') == 1:
                is_all_day_blocked = True
                break
            b_in = (blk_dict.get('hora_inicio') or '').strip()
            b_fi = (blk_dict.get('hora_fin') or '').strip()
            if b_in and b_fi:
                try:
                    perf_blocks.append({
                        'start': datetime.strptime(normalize_time_str(b_in), "%H:%M"),
                        'busy_until': datetime.strptime(normalize_time_str(b_fi), "%H:%M")
                    })
                except: pass

        if is_all_day_blocked:
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

                        duration_td = timedelta(minutes=perf_duracion)
                        recess_td = timedelta(minutes=perf_receso)

                        # Recolectar intervalos ocupados que intersecten con este rango laboral
                        raw_busy = []
                        for bi in base_busy_intervals:
                            if bi['busy_until'] <= start_time or bi['start'] >= end_time:
                                continue
                            raw_busy.append({
                                'start': max(bi['start'], start_time),
                                'busy_until': min(bi['busy_until'], end_time),
                                'actual_busy_until': bi['busy_until']
                            })
                        for p_b in perf_blocks:
                            if p_b['busy_until'] <= start_time or p_b['start'] >= end_time:
                                continue
                            raw_busy.append({
                                'start': max(p_b['start'], start_time),
                                'busy_until': min(p_b['busy_until'], end_time),
                                'actual_busy_until': p_b['busy_until']
                            })

                        raw_busy.sort(key=lambda x: x['start'])

                        # Fusionar intervalos ocupados superpuestos o contiguos
                        merged_busy = []
                        for b in raw_busy:
                            if not merged_busy:
                                merged_busy.append(b)
                            else:
                                prev = merged_busy[-1]
                                if b['start'] <= prev['actual_busy_until']:
                                    prev['actual_busy_until'] = max(prev['actual_busy_until'], b['actual_busy_until'])
                                    prev['busy_until'] = max(prev['busy_until'], b['busy_until'])
                                else:
                                    merged_busy.append(b)

                        # Generar turnos en ventanas libres según duración y receso del perfil
                        curr_free_start = start_time
                        for b in merged_busy:
                            curr = curr_free_start
                            # En ventana previa a una cita ocupada, la sesión + receso debe culminar antes de la cita
                            while curr + duration_td + recess_td <= b['start']:
                                h_str = curr.strftime("%H:%M")
                                h_fin_str = (curr + duration_td).strftime("%H:%M")
                                mod_label = perf_nombre or perf_modalidad or 'Online'
                                slot_key = (h_str, mod_label)
                                if slot_key not in seen_keys:
                                    seen_keys.add(slot_key)
                                    candidate_slots.append({
                                        'id': perf.get('id'),
                                        'perfil_id': perf.get('id'),
                                        'hora_literal': h_str,
                                        'hora_inicio': h_str,
                                        'hora_fin': h_fin_str,
                                        'modalidad': mod_label,
                                        'perfil': perf_nombre,
                                        'antelacion': perf_antelacion,
                                        'duracion': perf_duracion,
                                        'receso': perf_receso
                                    })
                                curr = curr + duration_td + recess_td
                            curr_free_start = max(curr_free_start, b['actual_busy_until'])

                        # Ventana libre final hasta el cierre del rango laboral
                        curr = curr_free_start
                        while curr + duration_td <= end_time and curr + duration_td + recess_td <= end_time + timedelta(minutes=5):
                            h_str = curr.strftime("%H:%M")
                            h_fin_str = (curr + duration_td).strftime("%H:%M")
                            mod_label = perf_nombre or perf_modalidad or 'Online'
                            slot_key = (h_str, mod_label)
                            if slot_key not in seen_keys:
                                seen_keys.add(slot_key)
                                candidate_slots.append({
                                    'id': perf.get('id'),
                                    'perfil_id': perf.get('id'),
                                    'hora_literal': h_str,
                                    'hora_inicio': h_str,
                                    'hora_fin': h_fin_str,
                                    'modalidad': mod_label,
                                    'perfil': perf_nombre,
                                    'antelacion': perf_antelacion,
                                    'duracion': perf_duracion,
                                    'receso': perf_receso
                                })
                            curr = curr + duration_td + recess_td

                    except Exception as _re:
                        print("Error calculando rango horario:", _re)

    # 4. Validar antelación mínima y formato ISO
    valid_slots = []
    for slot in candidate_slots:
        h_lit = normalize_time_str(slot['hora_literal'])
        try:
            slot_dt = datetime.strptime(f"{target_date_str} {h_lit}", "%Y-%m-%d %H:%M")
            slot_antelacion = slot.get('antelacion', antelacion)
            min_allowed_dt = now_dt + timedelta(hours=slot_antelacion)
            if slot_dt < min_allowed_dt:
                continue

            slot['iso_timestamp'] = slot_dt.strftime("%Y-%m-%dT%H:%M:%S-04:00")
            slot['iso'] = slot['iso_timestamp']
            valid_slots.append(slot)
        except Exception:
            pass

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

def normalize_slug_text(val):
    if not val:
        return ''
    import unicodedata
    val = unicodedata.normalize('NFKD', str(val)).encode('ASCII', 'ignore').decode('utf-8')
    val = val.lower().strip()
    for prefix in ['psicologa.', 'psicologa-', 'psicologa_', 'psicologo.', 'psicologo-', 'psicologo_', 'psico.', 'psico-', 'psic.', 'psic-', 'psic_']:
        if val.startswith(prefix):
            val = val[len(prefix):]
    return re.sub(r'[^a-z0-9]', '', val)

def get_psychologist_by_id_or_slug(cursor, identifier):
    """
    Busca un psicólogo en la tabla usuarios por ID (int) o por slug / username / nombre.
    """
    if not identifier:
        return None
    ident_str = str(identifier).strip()
    if ident_str.isdigit():
        cursor.execute("SELECT * FROM usuarios WHERE id = ?", (int(ident_str),))
        row = cursor.fetchone()
        if row:
            return dict(row)
    norm_ident = normalize_slug_text(ident_str)
    cursor.execute("SELECT * FROM usuarios")
    rows = [dict(r) for r in cursor.fetchall()]
    for r in rows:
        u_slug = normalize_slug_text(r.get('slug'))
        u_user = normalize_slug_text(r.get('username'))
        u_full = normalize_slug_text(f"{r.get('nombres','')} {r.get('apellidos','')}")
        if norm_ident and (norm_ident == u_slug or norm_ident == u_user or norm_ident == u_full):
            return r
    for r in rows:
        u_slug = normalize_slug_text(r.get('slug'))
        u_user = normalize_slug_text(r.get('username'))
        u_full = normalize_slug_text(f"{r.get('nombres','')} {r.get('apellidos','')}")
        if norm_ident and len(norm_ident) >= 4:
            if norm_ident in u_slug or u_slug in norm_ident or norm_ident in u_user or norm_ident in u_full:
                return r
    if any(k in ident_str.lower() for k in ['paulo', 'mora', 'pamoraro']):
        cursor.execute("SELECT * FROM usuarios WHERE id = 1")
        row1 = cursor.fetchone()
        if row1:
            return dict(row1)
    return None

@agenda_bp.route('/api/agenda/disponibilidad', methods=['GET'])
def get_agenda_disponibilidad():
    psicologo_id = request.args.get('psicologo_id')
    fecha_str = request.args.get('fecha')
    profile_id = request.args.get('profile_id')
    modalidad = profile_id or request.args.get('modalidad', 'all')
    
    db = get_db()
    cursor = db.cursor()
    
    if psicologo_id:
        try:
            from app import get_psychologist_by_id_or_slug
            psych = get_psychologist_by_id_or_slug(cursor, psicologo_id)
            if psych:
                psicologo_id = int(psych['id'])
            elif str(psicologo_id).isdigit():
                psicologo_id = int(psicologo_id)
        except Exception: pass

    if not psicologo_id and 'patient_id' in session:
        cursor.execute("SELECT psicologo_id FROM pacientes WHERE id = ?", (session['patient_id'],))
        p_row = cursor.fetchone()
        if p_row and p_row['psicologo_id']: psicologo_id = int(p_row['psicologo_id']) if str(p_row['psicologo_id']).isdigit() else 1
    if not psicologo_id and 'user_id' in session:
        psicologo_id = int(session['user_id']) if str(session['user_id']).isdigit() else 1
    if not psicologo_id:
        cursor.execute("SELECT id FROM usuarios WHERE role != 'superadmin' AND activo = 1 ORDER BY id ASC LIMIT 1")
        first_u = cursor.fetchone()
        psicologo_id = int(first_u[0]) if first_u else 1

    from routes_admin import is_user_subscription_expired
    if is_user_subscription_expired(cursor, psicologo_id):
        # Si la consulta viene de un paciente o usuario no logueado como este psicólogo:
        if 'user_id' not in session or session.get('user_id') != psicologo_id:
            return jsonify({
                "modalidades": [],
                "horas_disponibles": [],
                "slots": [],
                "psicologo_timezone": "America/Caracas",
                "expirado": True,
                "error": "El especialista no tiene disponibilidad para agendar citas en este momento."
            })
        
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
    
    # Auto-curar registros huérfanos con slugs en vez de IDs si existieran
    try:
        from app import heal_orphaned_slug_records
        heal_orphaned_slug_records(cursor, db)
    except Exception:
        pass

    # Auto-evaluar citas expiradas no confirmadas
    try:
        from app import auto_cancel_unconfirmed_sessions
        auto_cancel_unconfirmed_sessions(db)
    except Exception as e_ac:
        print("Aviso al auto-evaluar cancelaciones en get_agenda:", e_ac)
        
    psic_id = get_psicologo_id_filter()
    if psic_id is not None:
        try:
            psic_id = int(psic_id)
        except:
            pass
        cursor.execute("""
            SELECT af.*, p.nombres, p.apellidos, p.cedula, p.telefono, p.telefono as paciente_telefono,
                   (CASE WHEN EXISTS (
                       SELECT 1 FROM sesiones s 
                       WHERE (s.agenda_id = af.id OR (s.paciente_id = af.paciente_id AND s.fecha = af.fecha))
                         AND (s.estado IS NULL OR (s.estado NOT LIKE '%Cancelad%' AND s.estado != 'Reprogramada'))
                   ) THEN 1 ELSE 0 END) as has_session
            FROM agenda_finanzas af
            JOIN pacientes p ON af.paciente_id = p.id
            WHERE (af.hora != '00:00' AND af.hora != '' AND af.hora IS NOT NULL)
              AND (
                  p.psicologo_id = ? 
                  OR af.creado_por_user_id = ?
                  OR CAST(p.psicologo_id AS TEXT) = CAST(? AS TEXT)
                  OR CAST(af.creado_por_user_id AS TEXT) = CAST(? AS TEXT)
                  OR (? = 1 AND (af.creado_por_user_id LIKE '%mora%' OR p.psicologo_id LIKE '%mora%'))
              )
            ORDER BY af.fecha ASC, af.hora ASC
        """, (psic_id, psic_id, psic_id, psic_id, psic_id))
    else:
        cursor.execute("""
            SELECT af.*, p.nombres, p.apellidos, p.cedula, p.telefono, p.telefono as paciente_telefono,
                   (CASE WHEN EXISTS (
                       SELECT 1 FROM sesiones s 
                       WHERE (s.agenda_id = af.id OR (s.paciente_id = af.paciente_id AND s.fecha = af.fecha))
                         AND (s.estado IS NULL OR (s.estado NOT LIKE '%Cancelad%' AND s.estado != 'Reprogramada'))
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
        fecha_fin = (data.get('fecha_fin') or '').strip()
        modalidad = (data.get('modalidad') or 'Todas').strip()
        hora_inicio = (data.get('hora_inicio') or '').strip()
        hora_fin = (data.get('hora_fin') or '').strip()
        motivo = (data.get('motivo') or 'Bloqueo de Espacio / Horario').strip()
        todo_el_dia = 1 if data.get('todo_el_dia') else 0

        if not fecha:
            return jsonify({'error': 'La fecha es obligatoria para registrar un bloqueo de espacio / horario.'}), 400

        try:
            cursor.execute("PRAGMA table_info(bloqueos_agenda_especificos)")
            cols_b = [c[1] for c in cursor.fetchall()]
            if 'modalidad' not in cols_b:
                cursor.execute("ALTER TABLE bloqueos_agenda_especificos ADD COLUMN modalidad TEXT DEFAULT 'Todas'")
            if 'fecha_fin' not in cols_b:
                cursor.execute("ALTER TABLE bloqueos_agenda_especificos ADD COLUMN fecha_fin TEXT")
            db.commit()
        except:
            pass

        cursor.execute("""
            INSERT INTO bloqueos_agenda_especificos (psicologo_id, fecha, fecha_fin, modalidad, hora_inicio, hora_fin, motivo, todo_el_dia)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (target_psic_id, fecha, fecha_fin or None, modalidad, hora_inicio, hora_fin, motivo, todo_el_dia))
        db.commit()
        block_id = cursor.lastrowid

        google_event_id = None
        sincronizar_google = bool(data.get('sincronizar_google', False))
        if sincronizar_google:
            try:
                from routes_admin import get_calendar_service
                service = get_calendar_service(target_psic_id)
                if service:
                    end_date_for_g = fecha_fin if fecha_fin else fecha
                    if todo_el_dia or not hora_inicio:
                        start_dict = {'date': fecha}
                        end_dict = {'date': end_date_for_g}
                    else:
                        h_start = hora_inicio if len(hora_inicio) == 5 else f"{hora_inicio}:00"
                        h_end = hora_fin if hora_fin and len(hora_fin) == 5 else f"{h_start[:2]}:59"
                        start_dict = {'dateTime': f"{fecha}T{h_start}:00-04:00", 'timeZone': 'America/Caracas'}
                        end_dict = {'dateTime': f"{end_date_for_g}T{h_end}:00-04:00", 'timeZone': 'America/Caracas'}
                    
                    mod_label = f" [{modalidad}]" if modalidad and modalidad != 'Todas' else ""
                    event_body = {
                        'summary': f"⛔ {motivo}{mod_label}",
                        'description': f"Bloqueo de espacio en Espacio Terapéutico (Modalidad: {modalidad})",
                        'start': start_dict,
                        'end': end_dict
                    }
                    g_event = service.events().insert(calendarId='primary', body=event_body).execute()
                    google_event_id = g_event.get('id')
            except Exception as ge:
                print("Error sincronizando bloqueo con Google Calendar:", ge)
        return jsonify({
            'success': 'Bloqueo de espacio / horario registrado correctamente.',
            'message': 'Bloqueo de espacio / horario registrado correctamente.',
            'google_synced': bool(google_event_id),
            'block': {
                'id': block_id,
                'psicologo_id': target_psic_id,
                'fecha': fecha,
                'fecha_fin': fecha_fin or None,
                'modalidad': modalidad,
                'hora_inicio': hora_inicio,
                'hora_fin': hora_fin,
                'motivo': motivo,
                'todo_el_dia': todo_el_dia
            }
        })

    cursor.execute("""
        SELECT * FROM bloqueos_agenda_especificos
        WHERE psicologo_id = ?
        ORDER BY fecha DESC, hora_inicio ASC
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
    raw_fecha = data.get('fecha')
    raw_hora = data.get('hora')
    tipo_consulta = data.get('tipo_consulta', 'Presencial')
    consultorio_nombre = data.get('consultorio_nombre')
    creado_por_user_id = data.get('creado_por_user_id') or session.get('user_id')
    
    if not paciente_id or not raw_fecha or not raw_hora or not tipo_consulta:
        return jsonify({'error': 'Paciente, Fecha, Hora y Tipo de consulta son obligatorios.'}), 400

    fecha = normalize_date_str(raw_fecha)
    hora = normalize_time_str(raw_hora)

    cursor.execute("SELECT psicologo_id FROM pacientes WHERE id = ?", (paciente_id,))
    pac_row = cursor.fetchone()
    raw_target_id = (pac_row['psicologo_id'] if pac_row and pac_row['psicologo_id'] else None) or creado_por_user_id or session.get('user_id') or 1
    try:
        target_psic_id = int(raw_target_id)
    except:
        target_psic_id = 1
    creado_por_user_id = target_psic_id

    from routes_admin import is_user_subscription_expired
    if is_user_subscription_expired(cursor, target_psic_id) or is_user_subscription_expired(cursor, session.get('user_id')):
        return jsonify({
            'error': 'Tu suscripción o período de prueba ha finalizado. Tu cuenta se encuentra en modo solo lectura (consulta y descarga). No es posible agendar nuevas citas.'
        }), 403

    if check_appointment_interval_collision(cursor, target_psic_id, fecha, hora, tipo_consulta):
        return jsonify({
            'error': f'🚫 El psicólogo ya tiene otra consulta programada que coincide o se solapa con el horario {hora} el día {fecha}.'
        }), 400

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
    confirmada_raw = data.get('confirmada')
    from datetime import datetime
    is_same_day = (fecha == datetime.now().strftime("%Y-%m-%d"))
    if confirmada_raw is not None and str(confirmada_raw).strip() != '':
        confirmada = int(confirmada_raw)
    elif is_same_day:
        confirmada = 1
    else:
        confirmada = 0
    hora_paciente = (data.get('hora_paciente') or '').strip() or None  # Hora en zona horaria del paciente (calculada en frontend)
    if not hora_paciente and paciente_id:
        try:
            cursor.execute("SELECT zona_horaria FROM pacientes WHERE id = ?", (paciente_id,))
            _p_tz_row = cursor.fetchone()
            if _p_tz_row and _p_tz_row['zona_horaria'] and _p_tz_row['zona_horaria'] != 'America/Caracas':
                hora_paciente = convert_time_vet_to_tz(fecha, hora, _p_tz_row['zona_horaria'])
        except Exception:
            pass

    # 1. Guardar primero en la base de datos local y asegurar la transacción
    cursor.execute("""
        INSERT INTO agenda_finanzas (
            paciente_id, fecha, hora, tipo_consulta, monto, moneda, 
            estado_pago, control_uso, google_event_id, cantidad_sesiones,
            referencia, metodo_pago, fecha_pago, confirmada, consultorio_nombre, creado_por_user_id,
            hora_paciente
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        paciente_id, fecha, hora, tipo_consulta, monto, moneda,
        estado_pago, control_uso, cantidad_sesiones,
        referencia, metodo_pago, fecha_pago, confirmada, consultorio_nombre, creado_por_user_id,
        hora_paciente
    ))
    db.commit()
    event_id = cursor.lastrowid

    # 2. Una vez guardado con éxito en la app, sincronizar con Google Calendar de forma aislada
    google_event_id = None
    try:
        from routes_admin import get_calendar_service
        psych_gc_id = target_psic_id or creado_por_user_id or session.get('user_id') or 1
        service = get_calendar_service(psych_gc_id, db=db)
        if not service and creado_por_user_id:
            service = get_calendar_service(creado_por_user_id, db=db)
        if not service:
            service = get_calendar_service(1, db=db)

        if service and paciente_id:
            cursor.execute("SELECT nombres, apellidos, email FROM pacientes WHERE id = ?", (paciente_id,))
            pac_row = cursor.fetchone()
            if pac_row:
                pac_nombre = f"{pac_row['nombres']} {pac_row['apellidos']}".strip()
                # Obtener duración configurada para este perfil/modalidad
                from datetime import datetime as _dt_local, timedelta as _td_local
                cursor.execute("SELECT configuracion_horarios_visual FROM usuarios WHERE id = ?", (psych_gc_id,))
                _u_cfg_row = cursor.fetchone()
                _cfg_perfiles = []
                _cfg_dur_default = 60
                if _u_cfg_row:
                    import json as _json
                    _raw = (_u_cfg_row['configuracion_horarios_visual'] if hasattr(_u_cfg_row, 'keys') else _u_cfg_row[0]) or ''
                    if _raw:
                        try:
                            _cfg = _json.loads(_raw)
                            _cfg_dur_default = int(_cfg.get('duracion', 60))
                            _raw_p = _cfg.get('perfiles', [])
                            _cfg_perfiles = list(_raw_p.values()) if isinstance(_raw_p, dict) else _raw_p
                        except:
                            pass
                _session_dur, _ = get_appointment_duration_and_recess(tipo_consulta, _cfg_perfiles, _cfg_dur_default)
                _total_duration = _session_dur * max(1, cantidad_sesiones)

                try:
                    start_dt_obj = _dt_local.strptime(f"{fecha} {hora}", "%Y-%m-%d %H:%M")
                    end_dt_obj = start_dt_obj + _td_local(minutes=_total_duration)
                    start_dt = start_dt_obj.strftime("%Y-%m-%dT%H:%M:%S-04:00")
                    end_dt = end_dt_obj.strftime("%Y-%m-%dT%H:%M:%S-04:00")
                except Exception as _dt_err:
                    print("Error calculando start_dt/end_dt para Google Calendar:", _dt_err)
                    h_parts = hora.split(':')
                    h_int = int(h_parts[0]) if (h_parts and h_parts[0].isdigit()) else 0
                    m_int = int(h_parts[1]) if (len(h_parts) > 1 and h_parts[1].isdigit()) else 0
                    end_h = str((h_int + 1) % 24).zfill(2)
                    start_dt = f"{fecha}T{str(h_int).zfill(2)}:{str(m_int).zfill(2)}:00-04:00"
                    end_dt = f"{fecha}T{end_h}:{str(m_int).zfill(2)}:00-04:00"
                
                is_conf = bool(confirmada)
                prefix = "🟢 " if is_conf else "🟠 "
                c_id = '10' if is_conf else '6'
                mod_label = (tipo_consulta or '').strip()
                summary_text = f"{prefix}Consulta {mod_label} - {pac_nombre}" if mod_label else f"{prefix}Consulta Psicológica - {pac_nombre}"

                event_body = {
                    'summary': summary_text,
                    'colorId': c_id,
                    'description': f"Modalidad: {tipo_consulta}",
                    'start': {'dateTime': start_dt, 'timeZone': 'America/Caracas'},
                    'end': {'dateTime': end_dt, 'timeZone': 'America/Caracas'}
                }
                if pac_row['email'] and '@' in pac_row['email'] and '.' in pac_row['email']:
                    event_body['attendees'] = [{'email': pac_row['email'].strip(), 'displayName': pac_nombre}]
                    g_event = service.events().insert(calendarId='primary', body=event_body, sendUpdates='all').execute()
                else:
                    g_event = service.events().insert(calendarId='primary', body=event_body).execute()
                
                google_event_id = g_event.get('id')
                if google_event_id:
                    cursor.execute("UPDATE agenda_finanzas SET google_event_id = ? WHERE id = ?", (google_event_id, event_id))
                    db.commit()
    except Exception as ge:
        print("Error creando cita en Google Calendar:", ge)

    if paciente_id and creado_por_user_id and creado_por_user_id > 0:
        try:
            cursor.execute("""
                UPDATE pacientes 
                SET psicologo_id = ? 
                WHERE id = ?
            """, (creado_por_user_id, paciente_id))
            db.commit()
        except Exception:
            pass

    # Notificar al consultante vía SQLite nativo y WebPush/FCM
    if paciente_id:
        try:
            from app import notify_patient
            hora_display = hora_paciente or hora  # Mostrar la hora en la zona horaria del paciente
            notify_patient(
                patient_id=paciente_id,
                titulo="📅 Nueva Cita Agendada",
                mensaje=f"Tu psicólogo ha programado una consulta para el {fecha} a las {hora_display}.",
                link="/#patient-home",
                icon="📅",
                tipo="cita"
            )
        except Exception as _ex_pac:
            print("Error notificando al paciente sobre cita creada:", _ex_pac)
    
    # Notificación automática e inmediata por WhatsApp al paciente
    try:
        from routes_notificaciones import send_booking_notification_wa
        send_booking_notification_wa(event_id, target_psic_id or creado_por_user_id)
    except Exception as _wa_err:
        print("[WA-BOOKING] Error al despachar notificación de agendamiento:", _wa_err)

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
    motivo = (data.get('motivo') or '').strip()
    notificar_wa = data.get('notificar_wa', True)
    
    # 1. Consultar datos actuales de la cita y paciente
    cursor.execute("""
        SELECT af.*, p.nombres, p.apellidos, p.telefono, p.pais, p.psicologo_id,
               p.costo_personalizado, p.moneda_personalizada,
               u.nombres as psic_nombres, u.apellidos as psic_apellidos
        FROM agenda_finanzas af 
        JOIN pacientes p ON af.paciente_id = p.id 
        LEFT JOIN usuarios u ON (p.psicologo_id = u.id OR (p.psicologo_id IS NULL AND u.id = 1))
        WHERE af.id = ?
    """, (event_id,))
    cita_raw = cursor.fetchone()
    if not cita_raw:
        return jsonify({'error': 'Cita no encontrada.'}), 404
    cita = dict(cita_raw)

    updates = []
    params = []
    
    target_cancellation = None
    cancellation_options = ['Cancelada con aviso', 'Cancelada sin aviso', 'Cancelada', 'Cancelada por el terapeuta', 'Cancelada por el psicólogo']
    if estado_pago in cancellation_options:
        target_cancellation = estado_pago
    elif estado in cancellation_options:
        target_cancellation = estado

    if target_cancellation in ['Cancelada con aviso', 'Cancelada por el terapeuta', 'Cancelada por el psicólogo']:
        updates.append("estado_pago = ?")
        params.append(target_cancellation)
        updates.append("confirmada = 0")
        if cita['estado_pago'] == 'Prepagada' or cita['tipo_consulta'] == 'Paquete Prepagado' or cita['metodo_pago'] == 'Descontado de Prepago':
            # Si era una sesión descontada de prepago, devolverla al paquete prepagado activo
            cursor.execute("""
                SELECT id FROM agenda_finanzas 
                WHERE paciente_id = ? AND estado_pago = 'Prepagada' AND control_uso = 'No consumida'
                ORDER BY id DESC LIMIT 1
            """, (cita['paciente_id'],))
            pkg = cursor.fetchone()
            if pkg:
                cursor.execute("UPDATE agenda_finanzas SET cantidad_sesiones = cantidad_sesiones + 1 WHERE id = ?", (pkg['id'],))
            updates.append("control_uso = 'Consumida'")
        else:
            updates.append("monto = 0.0")
        if motivo:
            new_ref = f"{target_cancellation}: {motivo}" if not cita['referencia'] else f"{cita['referencia']} | {target_cancellation}: {motivo}"
            updates.append("referencia = ?")
            params.append(new_ref)
            
        try:
            from app import create_auto_cancellation_session
            canc_tag = "por el terapeuta" if ('terapeuta' in target_cancellation.lower() or 'psic' in target_cancellation.lower()) else "con aviso por el terapeuta"
            cancellation_reason = f"Consulta cancelada {canc_tag}. Motivo: {motivo}" if motivo else f"Consulta cancelada {canc_tag}."
            create_auto_cancellation_session(db, cita['paciente_id'], event_id, cita['fecha'], cita['tipo_consulta'], target_cancellation, cancellation_reason)
        except Exception as se:
            print(f"Error creando sesion de {target_cancellation}:", se)
            
        _update_google_calendar_status_bg(event_id, 'cancelada')

    elif target_cancellation == 'Cancelada sin aviso':
        updates.append("estado_pago = 'Cancelada sin aviso'")
        updates.append("confirmada = 0")
        if cita['estado_pago'] == 'Prepagada' or cita['tipo_consulta'] == 'Paquete Prepagado':
            updates.append("control_uso = 'Consumida'")
        else:
            if cita['monto'] == 0.0:
                costo_real = cita['costo_personalizado'] or 0.0
                moneda_real = cita['moneda_personalizada'] or cita['moneda'] or 'USD'
                if costo_real == 0.0:
                    cursor.execute("SELECT valor FROM configuracion WHERE clave = 'costo_consulta_general'")
                    cfg_costo = cursor.fetchone()
                    if cfg_costo and cfg_costo['valor']:
                        try:
                            costo_real = float(cfg_costo['valor'])
                        except Exception:
                            pass
                if costo_real > 0:
                    updates.append("monto = ?")
                    params.append(costo_real)
                    updates.append("moneda = ?")
                    params.append(moneda_real)
        if motivo:
            new_ref = f"Cancelada sin aviso: {motivo}" if not cita['referencia'] else f"{cita['referencia']} | Cancelada sin aviso: {motivo}"
            updates.append("referencia = ?")
            params.append(new_ref)

        try:
            from app import create_auto_cancellation_session
            cancellation_reason = f"Consulta cancelada sin aviso. Registrada para cobro. Motivo: {motivo}" if motivo else "Consulta cancelada sin aviso. Registrada para cobro."
            create_auto_cancellation_session(db, cita['paciente_id'], event_id, cita['fecha'], cita['tipo_consulta'], 'Cancelada sin aviso', cancellation_reason)
        except Exception as se:
            print("Error creando sesion de cancelacion sin aviso:", se)

        _update_google_calendar_status_bg(event_id, 'cancelada')

    elif target_cancellation == 'Cancelada':
        updates.append("estado_pago = 'Cancelada'")
        updates.append("confirmada = 0")
        _update_google_calendar_status_bg(event_id, 'cancelada')
    else:
        if confirmada is not None:
            updates.append("confirmada = ?")
            params.append(int(confirmada))
            if int(confirmada) == 1:
                _update_google_calendar_status_bg(event_id, 'confirmada')
            
        if estado_pago is not None and str(estado_pago).strip() != '':
            updates.append("estado_pago = ?")
            params.append(str(estado_pago).strip())
            if str(estado_pago).strip() == 'Paga':
                today_vet = datetime.now().strftime('%Y-%m-%d')
                updates.append("fecha_pago = COALESCE(NULLIF(fecha_pago, ''), ?)")
                params.append(today_vet)
                updates.append("fecha_liquidacion = COALESCE(NULLIF(fecha_liquidacion, ''), ?)")
                params.append(today_vet)
        elif estado == 'Confirmada':
            updates.append("confirmada = 1")
            _update_google_calendar_status_bg(event_id, 'confirmada')
        
    if not updates:
        return jsonify({'success': True, 'message': 'Sin cambios'}), 200
        
    params.append(event_id)
    sql = f"UPDATE agenda_finanzas SET {', '.join(updates)} WHERE id = ?"
    cursor.execute(sql, params)
    db.commit()
    
    is_confirming = (confirmada == 1 or estado == 'Confirmada')
    is_cancelling = bool(target_cancellation)

    if is_cancelling:
        try:
            cursor.execute("UPDATE solicitudes_fuera_horario SET estado = 'Cancelada' WHERE agenda_id = ?", (event_id,))
        except Exception:
            pass

    # Enviar mensaje de WhatsApp si corresponde
    try:
        from routes_notificaciones import make_wa_http_request, format_whatsapp_message
        from routes_herramientas import clean_phone_number

        if is_cancelling and cita and cita.get('token_confirmacion'):
            try:
                cursor.execute("""
                    INSERT OR REPLACE INTO citas_canceladas_log (
                        agenda_id, token_confirmacion, paciente_id, psicologo_id,
                        paciente_nombre, fecha_cita, hora_cita, tipo_consulta, motivo_cancelacion
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    event_id, cita['token_confirmacion'], cita['paciente_id'],
                    cita.get('psicologo_id'), f"{cita.get('nombres','')} {cita.get('apellidos','')}".strip(),
                    cita.get('fecha'), cita.get('hora'), cita.get('tipo_consulta'),
                    f"Cancelada: {motivo or target_cancellation}"
                ))
            except Exception as _e_canc_log:
                print("Error registering cancellation in citas_canceladas_log:", _e_canc_log)

        if (is_confirming or (is_cancelling and notificar_wa)) and cita and cita['telefono']:
            phone_clean = clean_phone_number(cita['telefono'])
            psych_id = cita['psicologo_id'] or session.get('user_id') or 1
            
            # Fetch templates (globales y específicas del psicólogo)
            cursor.execute("SELECT clave, valor FROM configuracion WHERE clave IN ('msg_confirmacion_ok', 'msg_cancelacion_ok', 'msg_cancelacion_no_conf')")
            templates = {r['clave']: r['valor'] for r in cursor.fetchall()}
            
            cursor.execute("SELECT clave, valor FROM configuracion WHERE clave IN (?, ?, ?)", (
                f"msg_confirmacion_ok_{psych_id}",
                f"msg_cancelacion_ok_{psych_id}",
                f"msg_cancelacion_no_conf_{psych_id}"
            ))
            for r in cursor.fetchall():
                base_k = r['clave'].rsplit('_', 1)[0]
                if r['valor']:
                    templates[base_k] = r['valor']
            
            # Obtener slug y datos del psicólogo
            cursor.execute("SELECT username, slug FROM usuarios WHERE id = ?", (psych_id,))
            u_info = cursor.fetchone()
            
            patient_dict = {
                'nombres': cita['nombres'],
                'apellidos': cita['apellidos'],
                'pais': cita['pais'] or ''
            }
            cita_dict = {
                'nombre': f"{cita['nombres']} {cita['apellidos']}".strip(),
                'fecha': cita['fecha'],
                'hora': cita['hora_paciente'] or cita['hora'],
                'modalidad': cita['tipo_consulta'] or 'Presencial'
            }
            psicologo_data = {
                'nombres': cita['psic_nombres'],
                'apellidos': cita['psic_apellidos'],
                'username': u_info['username'] if u_info else '',
                'slug': u_info['slug'] if u_info else ''
            }
            
            is_no_conf = bool(
                'no confirm' in (motivo or '').lower() or
                'falta de confirmaci' in (motivo or '').lower() or
                (request.json and request.json.get('motivo_tipo') == 'no_confirmo')
            )
            
            if is_confirming:
                template = templates.get('msg_confirmacion_ok') or "¡Excelente! ✅ Tu cita ha sido confirmada exitosamente. Nos vemos pronto en Espacio Terapéutico."
            elif is_no_conf:
                template = templates.get('msg_cancelacion_no_conf') or "Saludos *{nombre}*, espero estés bien. No he recibido tu confirmación de la cita para el *{fecha}* a las *{hora}*, por ende procedemos a cancelarla. En caso de que desees volver a agendar:\n{link_agendar}"
            elif target_cancellation in ['Cancelada por el terapeuta', 'Cancelada por el psicólogo']:
                template = templates.get('msg_cancelacion_terapeuta') or "Hola *{nombre}*, te notifico que por causas de fuerza mayor debo cancelar nuestra sesión pautada para el *{fecha}* a las *{hora}*. Te ofrezco disculpas por el inconveniente. Puedes reagendar tu cita en:\n{link_agendar}"
            else:
                template = templates.get('msg_cancelacion_ok') or "Entendido. ❌ Tu cita ha sido cancelada. Si deseas reagendar o tienes alguna duda, por favor contáctanos."
            
            msg = format_whatsapp_message(template, patient_dict, cita_dict, psicologo_data)
            make_wa_http_request('POST', '/send', json_data={'phone': phone_clean, 'text': msg, 'user_id': psych_id}, timeout=10, user_id=psych_id)
    except Exception as e:
        print("Error sending manual confirmation WA:", e)

    # Notificar al consultante en su portal (campanita y push multidispositivo)
    if cita and cita.get('paciente_id'):
        try:
            from app import notify_patient
            if is_confirming:
                notify_patient(
                    patient_id=cita['paciente_id'],
                    titulo="✅ Cita Confirmada",
                    mensaje=f"Tu sesión del {cita['fecha']} a las {cita['hora']} ha sido confirmada por tu psicólogo.",
                    link="/#patient-home",
                    icon="✅",
                    tipo="cita"
                )
            elif is_cancelling:
                canc_desc = "por el terapeuta" if ('terapeuta' in str(target_cancellation).lower() or 'psic' in str(target_cancellation).lower()) else ""
                mot_desc = f" Motivo: {motivo}" if motivo else ""
                notify_patient(
                    patient_id=cita['paciente_id'],
                    titulo="⚠️ Sesión Cancelada",
                    mensaje=f"Tu sesión del {cita['fecha']} a las {cita['hora']} ha sido cancelada {canc_desc}.{mot_desc}".strip(),
                    link="/#patient-home",
                    icon="⚠️",
                    tipo="cita"
                )
        except Exception as _nep:
            print("Error notificando estado de cita al paciente:", _nep)

    try:
        if cita and cita['paciente_id']:
            from app import sync_patient_to_firebase
            import threading
            threading.Thread(target=sync_patient_to_firebase, args=(cita['paciente_id'],), daemon=True).start()
    except Exception as fe:
        print("Error al sincronizar paciente tras actualizar cita:", fe)
    
    return jsonify({'success': True, 'message': 'Cita actualizada exitosamente.'})


@agenda_bp.route('/api/agenda/<int:event_id>', methods=['DELETE'])
@agenda_bp.route('/api/agenda/events/<int:event_id>', methods=['DELETE'])
@login_required
def delete_agenda_event(event_id):
    db = get_db()
    cursor = db.cursor()
    user_id = session.get('user_id')

    # 1. Consultar cita antes de borrar para limpiar Google Calendar y guardar en citas_canceladas_log
    cursor.execute("""
        SELECT af.id, af.google_event_id, af.paciente_id, af.creado_por_user_id, af.token_confirmacion,
               af.fecha, af.hora, af.tipo_consulta, p.nombres, p.apellidos, p.psicologo_id,
               u.nombres as psic_nombres, u.apellidos as psic_apellidos, u.slug as psic_slug, u.whatsapp_publico as psic_wa
        FROM agenda_finanzas af
        LEFT JOIN pacientes p ON af.paciente_id = p.id
        LEFT JOIN usuarios u ON u.id = COALESCE(p.psicologo_id, af.creado_por_user_id, 1)
        WHERE af.id = ?
    """, (event_id,))
    cita_row = cursor.fetchone()
    cita = dict(cita_row) if cita_row else None

    if cita and cita.get('google_event_id'):
        psych_id = cita.get('psicologo_id') or cita.get('creado_por_user_id') or user_id or 1
        if isinstance(psych_id, str) and not psych_id.isdigit():
            from app import get_psychologist_by_id_or_slug
            p_obj = get_psychologist_by_id_or_slug(cursor, psych_id)
            psych_id = int(p_obj['id']) if p_obj else 1
        elif str(psych_id).isdigit():
            psych_id = int(psych_id)
        try:
            from routes_admin import get_calendar_service, delete_calendar_event
            service = get_calendar_service(psych_id, db=db)
            if service:
                delete_calendar_event(service, cita['google_event_id'])
        except Exception as ge:
            print("Error al eliminar evento en Google Calendar al borrar cita:", ge)

    if cita and cita.get('token_confirmacion'):
        try:
            cursor.execute("""
                INSERT OR REPLACE INTO citas_canceladas_log (
                    agenda_id, token_confirmacion, paciente_id, psicologo_id,
                    paciente_nombre, psicologo_nombre, psicologo_slug, psicologo_telefono,
                    fecha_cita, hora_cita, tipo_consulta, motivo_cancelacion
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                event_id, cita.get('token_confirmacion'), cita.get('paciente_id'),
                cita.get('psicologo_id') or cita.get('creado_por_user_id'),
                f"{cita.get('nombres','')} {cita.get('apellidos','')}".strip(),
                f"{cita.get('psic_nombres','')} {cita.get('psic_apellidos','')}".strip(),
                cita.get('psic_slug') or 'psic.paulomora',
                cita.get('psic_wa') or '584245926114',
                cita.get('fecha'), cita.get('hora'), cita.get('tipo_consulta'),
                'Cancelada / Eliminada de la agenda'
            ))
        except Exception as _e_del_log:
            print("Error logging deleted appointment in citas_canceladas_log:", _e_del_log)

    cursor.execute("DELETE FROM sesiones WHERE agenda_id = ?", (event_id,))
    cursor.execute("DELETE FROM agenda_finanzas WHERE id = ?", (event_id,))
    try:
        cursor.execute("UPDATE solicitudes_fuera_horario SET estado = 'Cancelada' WHERE agenda_id = ?", (event_id,))
    except Exception:
        pass
    db.commit()

    # Notificar al consultante en su portal (campanita y push)
    if cita and cita.get('paciente_id'):
        try:
            from app import notify_patient
            notify_patient(
                patient_id=cita['paciente_id'],
                titulo="🗑️ Cita Eliminada",
                mensaje=f"Tu cita programada para el {cita.get('fecha')} a las {cita.get('hora')} ha sido eliminada.",
                link="/#patient-home",
                icon="🗑️",
                tipo="cita"
            )
        except Exception as _e_del_notif:
            print("Error notificando cita eliminada al paciente:", _e_del_notif)

    if cita and cita['paciente_id']:
        try:
            import threading
            threading.Thread(target=sync_patient_to_firebase, args=(cita['paciente_id'],), daemon=True).start()
        except Exception as fe:
            print("Error al sincronizar paciente tras borrar cita:", fe)

    return jsonify({'success': 'Cita eliminada correctamente de la agenda y Google Calendar.'})

@agenda_bp.route('/api/agenda/events/<int:event_id>/dismiss-evolution', methods=['POST'])
@login_required
def dismiss_pending_evolution(event_id):
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("PRAGMA table_info(agenda_finanzas)")
        cols = [r[1] for r in cursor.fetchall()]
        if 'descartar_evolucion' not in cols:
            cursor.execute("ALTER TABLE agenda_finanzas ADD COLUMN descartar_evolucion INTEGER DEFAULT 0")
    except Exception as e:
        print("Error checking descartar_evolucion column:", e)
        
    cursor.execute("SELECT id, paciente_id, fecha, hora FROM agenda_finanzas WHERE id = ?", (event_id,))
    row = cursor.fetchone()
    if not row:
        return jsonify({'error': 'Cita no encontrada.'}), 404
        
    cursor.execute("UPDATE agenda_finanzas SET descartar_evolucion = 1 WHERE id = ?", (event_id,))
    db.commit()
    return jsonify({'success': True, 'message': 'Cita eliminada de la lista de evoluciones pendientes.'})

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
        "alerta_confirmacion_tipo": "previo",
        "alerta_confirmacion_valor": "08:00",
        "alerta_recordatorio": 2,
        "alerta_recordatorio_tipo": "horas",
        "alerta_recordatorio_valor": 2,
        "alerta_cierre": 2,
        "limite_cancelacion_tipo": "mismo_dia",
        "limite_cancelacion_valor": "07:00",
        "politica_cancelacion_tipo": "horas",
        "politica_cancelacion_valor": 24,
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

        if 'alerta_confirmacion_tipo' not in config:
            config['alerta_confirmacion_tipo'] = 'previo'
            config['alerta_confirmacion_valor'] = '08:00'

        perfiles = config.get('perfiles', [])
        if not isinstance(perfiles, list) or len(perfiles) == 0:
            perfiles = list(default_visual['perfiles'])

        user_id = session.get('user_id')
        needs_save_ids = False
        for idx, p in enumerate(perfiles):
            p_id = str(p.get('id') or '').strip()
            if not p_id or (not p_id.startswith(f"p_{user_id}_") and not p.get('es_horario_clinica')):
                p['id'] = f"p_{user_id}_{idx + 1}"
                needs_save_ids = True

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
        if needs_save_ids and user_id:
            try:
                cursor.execute("UPDATE usuarios SET configuracion_horarios_visual = ? WHERE id = ?", (json.dumps(config), user_id))
                db.commit()
            except Exception: pass

        config['tipo_clinica'] = u_row['tipo_clinica'] if u_row else 0
        config['suscripcion_paga'] = u_row['suscripcion_paga'] if u_row else 0
        config['organizacion_nombre'] = org_name

        return jsonify(config)
    else:
        data = request.json or {}
        user_id = session.get('user_id')
        if isinstance(data.get('perfiles'), list):
            for idx, p in enumerate(data['perfiles']):
                p_id = str(p.get('id') or '').strip()
                if not p_id or (not p_id.startswith(f"p_{user_id}_") and not p.get('es_horario_clinica')):
                    p['id'] = f"p_{user_id}_{idx + 1}"
        try:
            cursor.execute("UPDATE usuarios SET configuracion_horarios_visual = ? WHERE id = ?", (json.dumps(data), user_id))
            db.commit()

            # HOOK (Alternativa 2): Sincronizar inmediatamente las citas activas/futuras con las nuevas reglas
            try:
                from migrations import sync_psychologist_rules_to_appointments
                sync_psychologist_rules_to_appointments(cursor, db, session.get('user_id'), data)
            except Exception as _sync_err:
                print(f"[HOOK] Error al sincronizar reglas con citas: {_sync_err}")

            return jsonify({'success': 'Horarios y disponibilidad guardados con éxito.'})
        except Exception as e:
            return jsonify({'error': f'Error al guardar horarios: {str(e)}'}), 500

@agenda_bp.route('/api/active-psychologists', methods=['GET'])
def get_active_psychologists():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT id, nombres, apellidos, username, slug, role, foto_titulo
        FROM usuarios
        WHERE role IN ('psicologo', 'admin', 'superadmin', 'psicologo_admin')
          AND COALESCE(activo, 1) = 1
          AND COALESCE(mostrar_en_directorio, 1) = 1
          AND LOWER(username) NOT IN ('admin', 'superadmin', 'psicologa.valeria')
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
            'slug': slug,
            'foto_titulo': r_dict.get('foto_titulo') or ''
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
    modalities = [
        {"id": f"p_{psic_id}_1", "profile_id": f"p_{psic_id}_1", "nombre": "Online", "modalidad": "Online", "descripcion": "Consultas a través de WhatsApp y Google Meet videollamadas"},
        {"id": f"p_{psic_id}_2", "profile_id": f"p_{psic_id}_2", "nombre": "Presencial", "modalidad": "Presencial", "descripcion": "Consultas presenciales en consultorio físico"}
    ]
    if u_row and u_row[0]:
        try:
            import json
            config = json.loads(u_row[0])
            raw_perfiles = config.get('perfiles', [])
            if isinstance(raw_perfiles, dict):
                m_names = list(raw_perfiles.keys())
                if m_names:
                    modalities = [{"id": raw_perfiles[k].get('id') or f"p_{psic_id}_{i+1}", "profile_id": raw_perfiles[k].get('id') or f"p_{psic_id}_{i+1}", "nombre": k, "modalidad": k, "descripcion": ""} for i, k in enumerate(m_names)]
            elif isinstance(raw_perfiles, list) and len(raw_perfiles) > 0:
                result = []
                for idx, p in enumerate(raw_perfiles):
                    nom = p.get('nombre') or p.get('modalidad')
                    if nom:
                        p_id = p.get('id') or f"p_{psic_id}_{idx+1}"
                        result.append({
                            "id": p_id,
                            "profile_id": p_id,
                            "nombre": nom,
                            "modalidad": p.get('modalidad') or nom,
                            "descripcion": p.get('descripcion') or '',
                            "consultorio": p.get('consultorio') or ''
                        })
                if result:
                    modalities = result
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
        psicologo_id = int(psych['id'])
    elif str(psicologo_id).isdigit():
        psicologo_id = int(psicologo_id)
    else:
        cursor.execute("SELECT id FROM usuarios WHERE role != 'superadmin' AND activo = 1 ORDER BY id ASC LIMIT 1")
        first_u = cursor.fetchone()
        psicologo_id = int(first_u['id'] if hasattr(first_u, 'keys') else first_u[0]) if first_u else 1

    profile_id_used = data.get('profile_id') or (modalidad if str(modalidad).startswith('p_') else None)
    # Si modalidad viene como ID de perfil (ej. p_1_3), resolver al nombre legible del perfil
    if str(modalidad).startswith('p_'):
        cursor.execute("SELECT configuracion_horarios_visual FROM usuarios WHERE id = ?", (psicologo_id,))
        _u_cfg = cursor.fetchone()
        if _u_cfg and _u_cfg[0]:
            try:
                _cfg_json = json.loads(_u_cfg[0])
                for _pf in _cfg_json.get('perfiles', []):
                    if _pf.get('id') == modalidad:
                        modalidad = _pf.get('nombre') or _pf.get('modalidad') or modalidad
                        break
            except Exception: pass

    from routes_admin import is_user_subscription_expired
    if is_user_subscription_expired(cursor, psicologo_id):
        return jsonify({'error': 'El especialista no está disponible para recibir nuevas citas en este momento.'}), 400

    hora_paciente = (data.get('hora_paciente') or '').strip() or None
    zona_horaria = (data.get('zona_horaria') or '').strip() or None

    fecha_norm = normalize_date_str(fecha)
    hora_norm = normalize_time_str(hora)

    # Si no vino hora_paciente explícita pero hay zona_horaria diferente a Caracas, calcularla
    if not hora_paciente and zona_horaria and zona_horaria != 'America/Caracas':
        hora_paciente = convert_time_vet_to_tz(fecha_norm, hora_norm, zona_horaria)

    alt_fecha = fecha_norm
    try:
        dt_tmp = datetime.strptime(fecha_norm, "%Y-%m-%d")
        alt_fecha = dt_tmp.strftime("%d/%m/%Y")
    except:
        pass

    # 0. Verificar si el horario seleccionado ya está reservado o colisiona con otra cita en ese psicólogo
    if check_appointment_interval_collision(cursor, psicologo_id, fecha_norm, hora_norm, profile_id_used or modalidad):
        return jsonify({'error': 'El horario seleccionado ya fue reservado o coincide con otra consulta programada del psicólogo. Por favor elige otro horario.'}), 400
    
    # 1. Verificar si el paciente existe por cédula limpia (dígitos), usuario o teléfono
    clean_cedula = cedula.strip()
    digits_cedula = re.sub(r'\D', '', clean_cedula) if clean_cedula else ''
    digits_telefono = re.sub(r'\D', '', telefono) if telefono else ''

    cursor.execute("""
        SELECT id, nombres, apellidos, telefono, email, psicologo_id, zona_horaria
        FROM pacientes 
        WHERE ((LOWER(REPLACE(REPLACE(REPLACE(REPLACE(cedula, 'V-', ''), 'E-', ''), '.', ''), ' ', '')) = ? AND ? != '')
           OR (LOWER(REPLACE(REPLACE(REPLACE(cedula, '.', ''), '-', ''), ' ', '')) = LOWER(REPLACE(REPLACE(REPLACE(?, '.', ''), '-', ''), ' ', '')))
           OR (LOWER(username) = LOWER(?) AND username != ''))
           AND (psicologo_id = ? OR psicologo_id IS NULL)
    """, (digits_cedula, digits_cedula, clean_cedula, clean_cedula.lower(), psicologo_id))
    patient = cursor.fetchone()
    
    is_new_patient = False
    if not patient:
        is_new_patient = True
        try:
            cursor.execute("""
                INSERT INTO pacientes (nombres, apellidos, cedula, telefono, email, psicologo_id, zona_horaria)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (nombres, apellidos, cedula, telefono, email, psicologo_id, zona_horaria or 'America/Caracas'))
            patient_id = cursor.lastrowid
            pac_nombre = f"{nombres} {apellidos}"
        except Exception as ex:
            return jsonify({'error': f'Error al registrar paciente automáticamente: {str(ex)}'}), 500
    else:
        patient_id = patient['id']
        # REGLA DE PREVALENCIA DEL PSICÓLOGO:
        # 1. Nombres y apellidos guardados por el psicólogo SIEMPRE prevalecen
        pac_nombre = f"{patient['nombres']} {patient['apellidos']}".strip() or f"{nombres} {apellidos}".strip()
        
        # 2. Contacto y zona horaria
        updates = []
        params = []
        clean_new_tel = telefono.strip() if telefono else ''
        if clean_new_tel and clean_new_tel != (patient['telefono'] or '').strip():
            updates.append("telefono = ?")
            params.append(clean_new_tel)
            
        clean_new_email = email.strip() if email else ''
        if clean_new_email and clean_new_email != (patient['email'] or '').strip():
            updates.append("email = ?")
            params.append(clean_new_email)

        if zona_horaria and zona_horaria != (patient['zona_horaria'] or '').strip():
            updates.append("zona_horaria = ?")
            params.append(zona_horaria)
            
        if updates:
            params.append(patient_id)
            cursor.execute(f"UPDATE pacientes SET {', '.join(updates)} WHERE id = ?", params)
            db.commit()

        # Si aún no tenemos hora_paciente, verificar si el paciente existente tiene zona horaria
        if not hora_paciente:
            p_tz = (patient['zona_horaria'] or '').strip()
            if p_tz and p_tz != 'America/Caracas':
                hora_paciente = convert_time_vet_to_tz(fecha_norm, hora_norm, p_tz)
        
    try:
        monto, moneda = get_appointment_fee(cursor, patient_id, psicologo_id, modalidad)
        
        # Citas agendadas para el mismo día se consideran confirmadas por defecto (coordinación previa directa)
        from datetime import datetime
        is_same_day = (fecha_norm == datetime.now().strftime("%Y-%m-%d"))
        confirmada_val = 1 if is_same_day else 0

        cursor.execute("""
            INSERT INTO agenda_finanzas (
                paciente_id, fecha, hora, hora_paciente, tipo_consulta, monto, moneda, 
                estado_pago, control_uso, google_event_id, cantidad_sesiones, referencia, creado_por_user_id,
                confirmada
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'Agendada', 'No consumida', NULL, 1, ?, ?, ?)
        """, (patient_id, fecha_norm, hora_norm, hora_paciente, modalidad, monto, moneda, f"Auto-agendada rápida por paciente. Cédula: {cedula}", psicologo_id, confirmada_val))
        agenda_id = cursor.lastrowid
        
        if patient_id and psicologo_id:
            try:
                cursor.execute("""
                    UPDATE pacientes 
                    SET psicologo_id = ? 
                    WHERE id = ?
                """, (psicologo_id, patient_id))
            except Exception:
                pass

        # Detectar si esta cita corresponde a una reprogramación previa
        reprogramar_token = data.get('reprogramar_token')
        old_appt = None
        if reprogramar_token:
            cursor.execute("SELECT id, fecha, hora, tipo_consulta, referencia FROM agenda_finanzas WHERE token_confirmacion = ?", (reprogramar_token,))
            old_appt = cursor.fetchone()

        if not old_appt and patient_id:
            cursor.execute("""
                SELECT id, fecha, hora, tipo_consulta, referencia
                FROM agenda_finanzas
                WHERE paciente_id = ? AND estado_pago = 'Reprogramada' AND id != ?
                ORDER BY id DESC LIMIT 1
            """, (patient_id, agenda_id))
            old_appt = cursor.fetchone()

        from datetime import datetime
        fecha_notif = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if old_appt:
            old_appt_dict = dict(old_appt) if hasattr(old_appt, 'keys') else dict(zip([c[0] for c in cursor.description], old_appt))
            old_fecha = old_appt_dict.get('fecha')
            old_hora = old_appt_dict.get('hora')
            old_id = old_appt_dict.get('id')

            try:
                cursor.execute("""
                    UPDATE agenda_finanzas 
                    SET referencia = CASE 
                        WHEN referencia IS NULL OR referencia = '' THEN ?
                        ELSE referencia || ' | ' || ?
                    END
                    WHERE id = ?
                """, (f"Reprogramada a nueva cita #{agenda_id} ({fecha} {hora})", f"Reprogramada a nueva cita #{agenda_id} ({fecha} {hora})", old_id))
            except Exception as _e_upd:
                print("Error actualizando referencia de cita previa:", _e_upd)

            try:
                cursor.execute("""
                    INSERT INTO historial_reprogramaciones (
                        paciente_id, agenda_id, fecha_anterior, hora_anterior,
                        fecha_nueva, hora_nueva, modificado_por, motivo, fecha_registro
                    ) VALUES (?, ?, ?, ?, ?, ?, 'Paciente', ?, ?)
                """, (patient_id, agenda_id, old_fecha, old_hora, fecha, hora, 'Reprogramada desde portal de confirmación', fecha_notif))
            except Exception as _e_hist:
                print("Error registrando historial_reprogramaciones:", _e_hist)

            notif_titulo = '🔄 Cita Reprogramada'
            notif_mensaje = f"{pac_nombre} ha reprogramado la consulta del día {old_fecha} a las {old_hora}, para el día {fecha} a las {hora}."
        else:
            notif_titulo = 'Nueva Cita Agendada (Rápida)'
            notif_mensaje = f"{pac_nombre} ha auto-agendado una consulta para el {fecha} a las {hora}."

        cursor.execute("""
            INSERT INTO notificaciones (user_id, tipo, titulo, mensaje, fecha, leida, link)
            VALUES (?, ?, ?, ?, ?, 0, ?)
        """, (psicologo_id, 'cita', notif_titulo, notif_mensaje, fecha_notif, 'agenda'))
        
        db.commit()

        # Una vez asegurada la cita en la base de datos local, sincronizamos con Google Calendar
        google_event_id = None
        try:
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
                
                mod_label = (modalidad or '').strip()
                summary_text = f"🟠 Consulta {mod_label} - {pac_nombre}" if mod_label else f"🟠 Consulta Psicológica - {pac_nombre}"
                
                event_body = {
                    'summary': summary_text,
                    'colorId': '6',
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
                g_event = service.events().insert(calendarId='primary', body=event_body, sendUpdates='all').execute()
                google_event_id = g_event.get('id')
                if google_event_id:
                    cursor.execute("UPDATE agenda_finanzas SET google_event_id = ? WHERE id = ?", (google_event_id, agenda_id))
                    db.commit()
        except Exception as ge:
            print("Error creando evento en Google Calendar desde fast-booking:", ge)

        # Enviar notificación WebPush al psicólogo
        try:
            from app import send_webpush_notification
            send_webpush_notification(
                user_id=psicologo_id,
                title=notif_titulo,
                body=notif_mensaje,
                url="/?view=agenda"
            )
        except Exception as wp_ex:
            print("Error al enviar WebPush de auto-agendamiento:", wp_ex)
        
        # Sincronización en Firebase
        try:
            from app import sync_patient_to_firebase
            import threading
            threading.Thread(target=sync_patient_to_firebase, args=(patient_id,)).start()
        except Exception as fb_err:
            print("Error iniciando sync_patient_to_firebase en fast-booking:", fb_err)
        
        # Notificación automática e inmediata por WhatsApp al paciente
        try:
            from routes_notificaciones import send_booking_notification_wa
            send_booking_notification_wa(agenda_id, psicologo_id)
        except Exception as _wa_err:
            print("[WA-BOOKING] Error al despachar notificación de agendamiento en fast-booking:", _wa_err)

        psych_phone = None
        psych_name = "el profesional"
        if psych and isinstance(psych, dict):
            psych_phone = psych.get('whatsapp_publico') or psych.get('telefono')
            p_nom = psych.get('nombres', '')
            p_ape = psych.get('apellidos', '')
            if p_nom or p_ape:
                psych_name = f"Psic. {p_nom} {p_ape}".strip()

        return jsonify({
            'success': 'Tu consulta ha sido agendada con éxito automáticamente.',
            'google_synced': google_event_id is not None,
            'is_new_patient': is_new_patient,
            'psych_phone': psych_phone,
            'psych_name': psych_name,
            'first_time_message': 'Bienvenido/a. Como eres un consultante de primera vez, es importante que te comuniques vía WhatsApp con el profesional para recibir la información del encuadre terapeútico, métodos de pago y el enlace de la sesión.'
        })
    except Exception as e:
        try:
            db.rollback()
        except: pass
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
            SELECT COALESCE(af.id, s.id) as id,
                   s.id as sesion_id,
                   s.fecha,
                   COALESCE(af.hora, '') as hora,
                   COALESCE(s.modalidad, af.tipo_consulta, 'Consulta') as tipo_consulta,
                   COALESCE(af.monto, 0) as monto,
                   COALESCE(af.moneda, 'USD') as moneda,
                   COALESCE(af.estado_pago, 'Paga') as estado_pago,
                   af.control_uso,
                   af.metodo_pago,
                   af.referencia,
                   af.fecha_liquidacion,
                   p.id as paciente_id,
                   p.nombres,
                   p.apellidos,
                   p.cedula,
                   p.telefono
            FROM sesiones s
            JOIN pacientes p ON s.paciente_id = p.id
            LEFT JOIN agenda_finanzas af ON s.agenda_id = af.id
            WHERE p.psicologo_id = ?
              AND s.fecha LIKE ?
              AND (s.estado IS NULL OR (s.estado != 'Cancelada' AND s.estado NOT LIKE 'Cancelada%' AND s.estado NOT LIKE '%cancelad%'))
              AND (s.estado = 'Realizada' OR (s.resumen IS NOT NULL AND TRIM(s.resumen) != ''))
            ORDER BY s.fecha DESC, COALESCE(af.hora, '') DESC
        """, (user_id, date_prefix))
        
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
            from routes_admin import get_calendar_service, delete_calendar_event
            service = get_calendar_service(user_id, db=db)
            if service:
                try:
                    delete_calendar_event(service, google_event_id)
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

@agenda_bp.route('/api/cita/reprogramar-info/<token>', methods=['GET'])
def get_reprogramar_info(token):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT af.id, af.fecha, af.hora, af.tipo_consulta, p.cedula, p.nombres, p.apellidos, p.telefono, p.email
        FROM agenda_finanzas af
        JOIN pacientes p ON af.paciente_id = p.id
        WHERE af.token_confirmacion = ?
    """, (token,))
    row = cursor.fetchone()
    if not row:
        return jsonify({'error': 'Cita no encontrada'}), 404
    r_dict = dict(row) if hasattr(row, 'keys') else dict(zip([col[0] for col in cursor.description], row))
    return jsonify({
        'success': True,
        'fecha': r_dict.get('fecha'),
        'hora': r_dict.get('hora'),
        'modalidad': r_dict.get('tipo_consulta'),
        'cedula': r_dict.get('cedula'),
        'nombres': r_dict.get('nombres'),
        'apellidos': r_dict.get('apellidos'),
        'telefono': r_dict.get('telefono'),
        'email': r_dict.get('email')
    })


@agenda_bp.route('/cita/confirmar/<token>', methods=['GET'])
def vista_confirmar_cita(token):
    db = get_db()
    try:
        import sqlite3
        db.row_factory = sqlite3.Row
    except Exception:
        pass
    cursor = db.cursor()
    import re, urllib.parse
    
    # 1. Buscar la cita por token en agenda_finanzas
    cursor.execute("""
        SELECT af.*, p.nombres, p.apellidos, p.psicologo_id,
               u.nombres as psic_nombres, u.apellidos as psic_apellidos, u.username as psic_username,
               u.slug as psic_slug, u.whatsapp_publico as psic_whatsapp
        FROM agenda_finanzas af
        JOIN pacientes p ON af.paciente_id = p.id
        LEFT JOIN usuarios u ON u.id = COALESCE(p.psicologo_id, af.creado_por_user_id, 1)
        WHERE af.token_confirmacion = ?
    """, (token,))
    cita = cursor.fetchone()
    if cita:
        cita = dict(cita) if hasattr(cita, 'keys') else dict(zip([col[0] for col in cursor.description], cita))
        estado_pago = str(cita.get('estado_pago') or '').strip()
        referencia = str(cita.get('referencia') or '').strip()
        is_cancelled = 'cancelad' in estado_pago.lower() or 'cancelad' in referencia.lower() or estado_pago == 'Reprogramada' or (cita.get('confirmada') == 0 and ('falta' in referencia.lower() or 'sistema' in referencia.lower()))

        psic_nombre = f"{cita.get('psic_nombres') or ''} {cita.get('psic_apellidos') or ''}".strip() or "Tu especialista"
        pac_primer_nombre = (cita.get('nombres') or '').split()[0] if cita.get('nombres') else 'consultante'
        fecha_display = cita.get('fecha')
        hora_display = cita.get('hora_paciente') or cita.get('hora')
        modalidad_display = cita.get('tipo_consulta') or 'Online'
        
        target_slug = cita.get('psic_slug') or cita.get('psic_username') or 'psic.paulomora'
        clean_slug = target_slug if str(target_slug).startswith('psic.') else f"psic.{target_slug}"
        fast_booking_url = f"https://www.espacioterapeutico.net/agendar/{clean_slug}"
        
        psic_tel = cita.get('psic_whatsapp') or '+584245926114'
        clean_tel = re.sub(r'\D', '', str(psic_tel))
        if clean_tel and not clean_tel.startswith('58') and len(clean_tel) == 10:
            clean_tel = '58' + clean_tel
        wa_text = f"Hola {psic_nombre}, mi cita para el {fecha_display} a las {hora_display} fue cancelada por falta de confirmación y quisiera coordinar una nueva cita."
        whatsapp_url = f"https://wa.me/{clean_tel}?text={urllib.parse.quote(wa_text)}" if clean_tel else None

        if is_cancelled:
            # Determinar el motivo real de la cancelación
            if 'reprogram' in referencia.lower() or estado_pago == 'Reprogramada':
                motivo_tipo = 'reprogramar'
                wa_text = f"Hola {psic_nombre}, solicité reprogramar mi cita del {fecha_display} a las {hora_display} y quisiera coordinar una nueva fecha."
            elif 'falta' in referencia.lower() or 'sistema' in referencia.lower():
                motivo_tipo = 'auto_falta_confirmacion'
                wa_text = f"Hola {psic_nombre}, mi cita para el {fecha_display} a las {hora_display} fue cancelada por falta de confirmación y quisiera coordinar una nueva fecha."
            elif 'fuera de tiempo' in referencia.lower() or estado_pago == 'Cancelada sin aviso':
                motivo_tipo = 'fuera_de_tiempo'
                wa_text = f"Hola {psic_nombre}, he cancelado mi cita del {fecha_display} a las {hora_display} fuera del tiempo límite y quisiera coordinar el pago y una nueva fecha."
            elif 'terapeuta' in referencia.lower() or 'especialista' in referencia.lower():
                motivo_tipo = 'terapeuta'
                wa_text = f"Hola {psic_nombre}, mi cita para el {fecha_display} a las {hora_display} fue cancelada y quisiera coordinar una nueva fecha."
            else:
                # Verificar si hubo notificación de reprogramación registrada en el sistema
                cursor.execute("""
                    SELECT id FROM notificaciones 
                    WHERE tipo = 'cita' AND (titulo LIKE '%Reprogram%' OR mensaje LIKE '%reprogram%')
                      AND mensaje LIKE ? AND mensaje LIKE ?
                    LIMIT 1
                """, (f"%{fecha_display}%", f"%{pac_primer_nombre}%"))
                if cursor.fetchone():
                    motivo_tipo = 'reprogramar'
                    wa_text = f"Hola {psic_nombre}, solicité reprogramar mi cita del {fecha_display} a las {hora_display} y quisiera coordinar una nueva fecha."
                else:
                    motivo_tipo = 'consultante'
                    wa_text = f"Hola {psic_nombre}, he cancelado mi cita del {fecha_display} a las {hora_display} y quisiera coordinar una nueva fecha."
                
            whatsapp_url = f"https://wa.me/{clean_tel}?text={urllib.parse.quote(wa_text)}" if clean_tel else None

            return render_template('cita_cancelada.html',
                paciente_nombre=pac_primer_nombre,
                psicologo_nombre=psic_nombre,
                fecha=fecha_display,
                hora=hora_display,
                modalidad=modalidad_display,
                fast_booking_url=fast_booking_url,
                whatsapp_url=whatsapp_url,
                motivo_tipo=motivo_tipo
            )
            
        from datetime import datetime
        today_str = datetime.now().strftime("%Y-%m-%d")
        
        if cita.get('fecha') < today_str:
            return render_template('cita_invalida.html', mensaje="Esta cita ya ocurrió y no puede ser modificada.")
            
        return render_template('confirmar_cita_public.html', cita=cita)

    # 2. Si no está en agenda_finanzas, verificar en citas_canceladas_log
    cursor.execute("""
        SELECT c.*, u.nombres as psic_u_nombres, u.apellidos as psic_u_apellidos,
               u.slug as psic_u_slug, u.username as psic_u_user, u.whatsapp_publico as psic_u_wa
        FROM citas_canceladas_log c
        LEFT JOIN usuarios u ON c.psicologo_id = u.id
        WHERE c.token_confirmacion = ?
    """, (token,))
    log_c = cursor.fetchone()

    if log_c:
        log_c = dict(log_c)
        psic_nombre = log_c.get('psicologo_nombre') or f"{log_c.get('psic_u_nombres','')} {log_c.get('psic_u_apellidos','')}".strip() or "Tu especialista"
        pac_nombre = log_c.get('paciente_nombre') or 'consultante'
        pac_primer_nombre = pac_nombre.split()[0] if pac_nombre else 'consultante'
        fecha_display = log_c.get('fecha_cita')
        hora_display = log_c.get('hora_cita')
        modalidad_display = log_c.get('tipo_consulta') or 'Online'
        
        target_slug = log_c.get('psicologo_slug') or log_c.get('psic_u_slug') or log_c.get('psic_u_user') or 'psic.paulomora'
        clean_slug = target_slug if str(target_slug).startswith('psic.') else f"psic.{target_slug}"
        fast_booking_url = f"https://www.espacioterapeutico.net/agendar/{clean_slug}"
        
        psic_tel = log_c.get('psicologo_telefono') or log_c.get('psic_u_wa') or '+584245926114'
        clean_tel = re.sub(r'\D', '', str(psic_tel))
        if clean_tel and not clean_tel.startswith('58') and len(clean_tel) == 10:
            clean_tel = '58' + clean_tel

        motivo_log = str(log_c.get('motivo_cancelacion') or '').lower()
        if 'reprogram' in motivo_log:
            motivo_tipo = 'reprogramar'
            wa_text = f"Hola {psic_nombre}, solicité reprogramar mi cita del {fecha_display} a las {hora_display} y quisiera coordinar una nueva fecha."
        elif 'falta' in motivo_log:
            motivo_tipo = 'auto_falta_confirmacion'
            wa_text = f"Hola {psic_nombre}, mi cita para el {fecha_display} a las {hora_display} fue cancelada por falta de confirmación y quisiera coordinar una nueva cita."
        elif 'fuera de tiempo' in motivo_log:
            motivo_tipo = 'fuera_de_tiempo'
            wa_text = f"Hola {psic_nombre}, he cancelado mi cita del {fecha_display} a las {hora_display} fuera del tiempo límite y quisiera coordinar el pago y una nueva fecha."
        elif 'terapeuta' in motivo_log or 'especialista' in motivo_log:
            motivo_tipo = 'terapeuta'
            wa_text = f"Hola {psic_nombre}, mi cita para el {fecha_display} a las {hora_display} fue cancelada y quisiera coordinar una nueva cita."
        else:
            motivo_tipo = 'consultante'
            wa_text = f"Hola {psic_nombre}, he cancelado mi cita del {fecha_display} a las {hora_display} y quisiera coordinar una nueva fecha."

        whatsapp_url = f"https://wa.me/{clean_tel}?text={urllib.parse.quote(wa_text)}" if clean_tel else None

        return render_template('cita_cancelada.html',
            paciente_nombre=pac_primer_nombre,
            psicologo_nombre=psic_nombre,
            fecha=fecha_display,
            hora=hora_display,
            modalidad=modalidad_display,
            fast_booking_url=fast_booking_url,
            whatsapp_url=whatsapp_url,
            motivo_tipo=motivo_tipo
        )

    return render_template('cita_invalida.html', mensaje="El enlace proporcionado no es válido o la cita ya no existe.")

@agenda_bp.route('/api/cita/accion', methods=['POST'])
def accion_cita_publica():
    data = request.json or {}
    token = data.get('token')
    accion = data.get('accion') # 'confirmar', 'cancelar', 'reprogramar'
    
    if not token or accion not in ['confirmar', 'cancelar', 'reprogramar']:
        return jsonify({'error': 'Datos inválidos.'}), 400
        
    db = get_db()
    try:
        import sqlite3
        db.row_factory = sqlite3.Row
    except Exception:
        pass
    cursor = db.cursor()
    
    cursor.execute("""
        SELECT af.id, af.paciente_id, af.fecha, af.hora, af.hora_paciente, af.tipo_consulta, af.confirmada, af.estado_pago, af.referencia, af.monto, af.moneda, af.google_event_id, af.creado_por_user_id, p.nombres as pat_nombres, p.apellidos as pat_apellidos, p.telefono as pat_telefono, p.pais as pat_pais, p.psicologo_id,
               u.nombres as psic_nombres, u.apellidos as psic_apellidos, u.username as psic_username, u.slug as psic_slug
        FROM agenda_finanzas af
        JOIN pacientes p ON af.paciente_id = p.id
        LEFT JOIN usuarios u ON u.id = COALESCE(p.psicologo_id, af.creado_por_user_id, 1)
        WHERE af.token_confirmacion = ?
    """, (token,))
    cita = cursor.fetchone()
    
    if not cita:
        cursor.execute("SELECT * FROM citas_canceladas_log WHERE token_confirmacion = ?", (token,))
        log_c = cursor.fetchone()
        log_dict = (dict(log_c) if hasattr(log_c, 'keys') else dict(zip([col[0] for col in cursor.description], log_c))) if log_c else {}
        target_slug = log_dict.get('psicologo_slug') or 'psic.paulomora'
        clean_slug = target_slug if str(target_slug).startswith('psic.') else f"psic.{target_slug}"
        return jsonify({
            'error': 'Esta consulta ya ha sido cancelada. Por favor agenda una nueva cita o comunícate con tu especialista.',
            'cancelada': True,
            'fast_booking_url': f"https://www.espacioterapeutico.net/agendar/{clean_slug}"
        }), 400
        
    cita = dict(cita) if hasattr(cita, 'keys') else dict(zip([col[0] for col in cursor.description], cita))
        
    appt_id = cita['id']
    psych_id = cita['psicologo_id'] or cita['creado_por_user_id'] or 1
    phone = cita['pat_telefono']
    
    target_slug = cita['psic_slug'] or cita['psic_username'] or 'psic.paulomora'
    clean_slug = target_slug if str(target_slug).startswith('psic.') else f"psic.{target_slug}"
    fast_booking_url = f"https://www.espacioterapeutico.net/agendar/{clean_slug}"
    
    estado_pago = str(cita['estado_pago'] or '').strip()
    referencia = str(cita['referencia'] or '').strip()
    is_cancelled = 'cancelad' in estado_pago.lower() or 'cancelad' in referencia.lower() or estado_pago == 'Reprogramada' or (cita.get('confirmada') == 0 and ('falta' in referencia.lower() or 'sistema' in referencia.lower()))

    # Si la consulta ya fue cancelada, rechazar intento de confirmación
    if accion == 'confirmar' and is_cancelled:
        return jsonify({
            'error': 'Esta consulta ya ha sido cancelada. Por favor agenda una nueva cita o comunícate con tu especialista.',
            'cancelada': True,
            'fast_booking_url': fast_booking_url
        }), 400

    # Prevenir doble-click en confirmar
    if accion == 'confirmar' and cita['confirmada'] == 1:
        return jsonify({'success': True})
    if accion in ('cancelar', 'reprogramar') and is_cancelled:
        return jsonify({'success': True, 'fast_booking_url': fast_booking_url})
    
    # Preparamos datos para Whatsapp (usando la hora calculada para la zona del paciente)
    patient_dict = {
        'nombres': cita['pat_nombres'],
        'apellidos': cita['pat_apellidos'],
        'pais': cita['pat_pais'] or ''
    }
    cita_dict = {
        'nombre': f"{cita['pat_nombres']} {cita['pat_apellidos']}".strip(),
        'fecha': cita['fecha'],
        'hora': cita['hora_paciente'] or cita['hora'],
        'modalidad': cita['tipo_consulta'] or 'Presencial',
        'link_agendar': fast_booking_url,
        'link_reagendar': fast_booking_url,
        'link_confirmacion': f"https://www.espacioterapeutico.net/cita/{token}" if token else ""
    }
    psicologo_data = {
        'nombres': cita['psic_nombres'],
        'apellidos': cita['psic_apellidos'],
        'username': cita['psic_username'],
        'slug': cita['psic_slug']
    }
    
    cursor.execute("""
        SELECT clave, valor FROM configuracion 
        WHERE clave IN (
            'msg_confirmacion_ok', 'msg_cancelacion_ok', 'msg_cancelacion_tardia', 'msg_reprogramacion', 'msg_reagendamiento',
            ?, ?, ?, ?, ?
        )
    """, (
        f'msg_confirmacion_ok_{psych_id}',
        f'msg_cancelacion_ok_{psych_id}',
        f'msg_cancelacion_tardia_{psych_id}',
        f'msg_reprogramacion_{psych_id}',
        f'msg_reagendamiento_{psych_id}'
    ))
    cfg_rows = {r['clave']: r['valor'] for r in cursor.fetchall()}
    
    template = ""
    response_data = {'success': True, 'fast_booking_url': fast_booking_url}
    
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    pat_full_name = f"{cita['pat_nombres']} {cita['pat_apellidos']}".strip()

    if accion == 'confirmar':
        cursor.execute("UPDATE agenda_finanzas SET confirmada = 1 WHERE id = ?", (appt_id,))
        template = cfg_rows.get(f'msg_confirmacion_ok_{psych_id}') or cfg_rows.get('msg_confirmacion_ok') or "¡Excelente! ✅ Tu cita ha sido confirmada exitosamente. Nos vemos pronto."
        _update_google_calendar_status_bg(appt_id, 'confirmada')
        response_data = {
            'success': True,
            'confirmada': True,
            'fast_booking_url': fast_booking_url
        }
        
        # 1. Notificación en campana para el psicólogo
        try:
            cursor.execute("""
                INSERT INTO notificaciones (user_id, tipo, titulo, mensaje, fecha, leida, link)
                VALUES (?, 'cita', '✅ Cita Confirmada', ?, ?, 0, 'agenda')
            """, (psych_id, f"{pat_full_name} ha confirmado su asistencia a la consulta del {cita['fecha']} a las {cita['hora']}.", now_str))
        except Exception as _ne:
            print("Error guardando notificacion de confirmacion:", _ne)

        db.commit()

        # 2. Notificación Push en segundo plano para el psicólogo
        try:
            from app import send_webpush_notification
            send_webpush_notification(
                user_id=psych_id,
                title="✅ Cita Confirmada",
                body=f"{pat_full_name} ha confirmado su asistencia a la consulta del {cita['fecha']} a las {cita['hora']}.",
                url="/?view=agenda"
            )
        except Exception as _wp_ex:
            print("Error enviando WebPush de confirmacion publica:", _wp_ex)

        # 3. Notificación para el paciente en campanita y Push
        if cita['paciente_id']:
            try:
                from app import notify_patient
                notify_patient(
                    patient_id=cita['paciente_id'],
                    titulo="✅ Cita Confirmada",
                    mensaje=f"Has confirmado exitosamente tu consulta para el {cita['fecha']} a las {cita['hora']}.",
                    link="/#patient-home",
                    icon="✅",
                    tipo="cita"
                )
            except Exception:
                pass
        
    elif accion == 'cancelar':
        # 1. Obtener política de cancelación configurada por el psicólogo
        cursor.execute("SELECT configuracion_horarios_visual FROM usuarios WHERE id = ?", (psych_id,))
        u_row = cursor.fetchone()
        rule_type = 'horas'
        rule_value = 24
        if u_row and u_row[0]:
            try:
                config = json.loads(u_row[0])
                rule_type = config.get('politica_cancelacion_tipo') or config.get('limite_cancelacion_tipo', 'horas')
                rule_value = config.get('politica_cancelacion_valor') if config.get('politica_cancelacion_valor') is not None else config.get('limite_cancelacion_valor', 24)
            except Exception:
                pass
                
        from routes_pacientes import get_deadline_datetime, create_auto_cancellation_session
        deadline_dt = get_deadline_datetime(cita['fecha'], cita['hora'], rule_type, rule_value)
        fuera_de_tiempo = datetime.now() > deadline_dt
        
        # Solo se cobra si está fuera de tiempo Y el paciente había confirmado la cita previamente
        es_late_charge = fuera_de_tiempo and (cita['confirmada'] == 1)

        # Actualizar Google Calendar si existe
        google_event_id = cita.get('google_event_id')
        if google_event_id:
            try:
                from routes_admin import get_calendar_service, update_calendar_event_status
                service = get_calendar_service(psych_id, db=db)
                if service:
                    update_calendar_event_status(
                        service, google_event_id, 'cancelada',
                        paciente_nombre=pat_full_name,
                        tipo_consulta=cita['tipo_consulta'],
                        motivo=f"Cancelada por consultante {'fuera de tiempo' if es_late_charge else 'a tiempo'} desde link público"
                    )
            except Exception as _ge:
                print("Error actualizando Google Calendar:", _ge)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS citas_canceladas_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agenda_id INTEGER,
                token_confirmacion TEXT UNIQUE,
                paciente_id INTEGER,
                psicologo_id INTEGER,
                paciente_nombre TEXT,
                psicologo_nombre TEXT,
                psicologo_slug TEXT,
                psicologo_telefono TEXT,
                fecha_cita TEXT,
                hora_cita TEXT,
                tipo_consulta TEXT,
                motivo_cancelacion TEXT,
                fecha_cancelacion DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        if es_late_charge:
            # Cancelación tardía cobrada: Se cobra o se descuenta de prepago si existe
            if cita['estado_pago'] in ['Paga', 'Prepagada']:
                cursor.execute("""
                    UPDATE agenda_finanzas
                    SET estado_pago = 'Cancelada sin aviso - Paga', confirmada = 0, control_uso = 'Consumida',
                        fecha_liquidacion = datetime('now', 'localtime'),
                        referencia = CASE WHEN referencia IS NULL OR referencia = '' THEN 'Cancelada por consultante fuera de tiempo' ELSE referencia || ' | Cancelada fuera de tiempo' END
                    WHERE id = ?
                """, (appt_id,))
            else:
                cursor.execute("""
                    SELECT id, cantidad_sesiones 
                    FROM agenda_finanzas 
                    WHERE paciente_id = ? AND estado_pago = 'Prepagada' AND control_uso = 'No consumida'
                    ORDER BY fecha ASC, id ASC LIMIT 1
                """, (cita['paciente_id'],))
                pkg = cursor.fetchone()
                if pkg:
                    pkg_id = pkg['id']
                    pkg_cant = pkg['cantidad_sesiones']
                    if pkg_cant > 1:
                        cursor.execute("UPDATE agenda_finanzas SET cantidad_sesiones = ? WHERE id = ?", (pkg_cant - 1, pkg_id))
                    else:
                        cursor.execute("UPDATE agenda_finanzas SET control_uso = 'Consumida' WHERE id = ?", (pkg_id,))
                        
                    cursor.execute("""
                        UPDATE agenda_finanzas
                        SET estado_pago = 'Cancelada sin aviso - Paga', confirmada = 0, control_uso = 'Consumida', monto = 0.0,
                            metodo_pago = 'Descontado de Prepago', referencia = 'Prepago | Cancelada fuera de tiempo',
                            fecha_liquidacion = datetime('now', 'localtime')
                        WHERE id = ?
                    """, (appt_id,))
                else:
                    if float(cita.get('monto') or 0.0) == 0.0:
                        costo_real, moneda_real = get_appointment_fee(cursor, cita['paciente_id'], psych_id, cita['tipo_consulta'])
                    else:
                        costo_real, moneda_real = cita['monto'], cita['moneda']
                    cursor.execute("""
                        UPDATE agenda_finanzas
                        SET estado_pago = 'Cancelada sin aviso', confirmada = 0, monto = ?, moneda = ?,
                            referencia = CASE WHEN referencia IS NULL OR referencia = '' THEN 'Cancelada por consultante fuera de tiempo' ELSE referencia || ' | Cancelada fuera de tiempo' END
                        WHERE id = ?
                    """, (costo_real, moneda_real, appt_id))

            create_auto_cancellation_session(
                db, cita['paciente_id'], appt_id, cita['fecha'], cita['tipo_consulta'],
                'Cancelada sin aviso',
                f"Consulta cancelada por el consultante fuera del límite de tiempo ({cita['fecha']} a las {cita['hora']}). Registrada para cobro."
            )

            try:
                cursor.execute("""
                    INSERT OR REPLACE INTO citas_canceladas_log (
                        agenda_id, token_confirmacion, paciente_id, psicologo_id,
                        paciente_nombre, fecha_cita, hora_cita, tipo_consulta, motivo_cancelacion
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    appt_id, token, cita['paciente_id'], psych_id,
                    pat_full_name, cita['fecha'], cita['hora'], cita['tipo_consulta'],
                    'Cancelada por consultante fuera de tiempo'
                ))
                try:
                    cursor.execute("UPDATE solicitudes_fuera_horario SET estado = 'Cancelada' WHERE agenda_id = ?", (appt_id,))
                except Exception:
                    pass
            except Exception as _e_clog:
                print("Error registrando citas_canceladas_log:", _e_clog)

            template = cfg_rows.get(f'msg_cancelacion_tardia_{psych_id}') or cfg_rows.get('msg_cancelacion_tardia') or cfg_rows.get(f'msg_cancelacion_ok_{psych_id}') or cfg_rows.get('msg_cancelacion_ok') or "Entendido, tu cita ha sido cancelada."

            try:
                cursor.execute("""
                    INSERT INTO notificaciones (user_id, tipo, titulo, mensaje, fecha, leida, link)
                    VALUES (?, 'cita', '⚠️ Cita Cancelada FUERA DE TIEMPO por Consultante', ?, ?, 0, 'agenda')
                """, (psych_id, f"{pat_full_name} ha cancelado su cita del {cita['fecha']} a las {cita['hora']} FUERA DEL LÍMITE DE TIEMPO (Cita Confirmada). Se registrará para cobro.", now_str))
            except Exception as _ne:
                print("Error notificando cancelacion publica tardia:", _ne)

            try:
                from app import send_webpush_notification
                send_webpush_notification(
                    user_id=psych_id,
                    title="⚠️ Cita Cancelada FUERA DE TIEMPO",
                    body=f"{pat_full_name} canceló su cita del {cita['fecha']} fuera del límite de tiempo.",
                    url="/?view=agenda"
                )
            except Exception as _wp_ex:
                print("Error enviando WebPush de cancelacion publica:", _wp_ex)

            db.commit()

            response_data = {
                'success': True,
                'late_charge': True,
                'titulo': 'Consulta Cancelada Fuera de Tiempo',
                'mensaje': 'Has cancelado la consulta fuera del tiempo límite permitido. De acuerdo con las normas de atención, esta sesión debe ser cancelada/abonada.',
                'fast_booking_url': fast_booking_url
            }

        else:
            # Cancelación a tiempo (sin cobro) o aún no confirmada
            cursor.execute("""
                UPDATE agenda_finanzas
                SET estado_pago = 'Cancelada con aviso', confirmada = 0, control_uso = 'No consumida', monto = 0.0,
                    referencia = CASE WHEN referencia IS NULL OR referencia = '' THEN 'Cancelada a tiempo por consultante' ELSE referencia || ' | Cancelada a tiempo por consultante' END
                WHERE id = ?
            """, (appt_id,))

            create_auto_cancellation_session(
                db, cita['paciente_id'], appt_id, cita['fecha'], cita['tipo_consulta'],
                'Cancelada con aviso',
                f"Consulta cancelada por el consultante a tiempo ({cita['fecha']} a las {cita['hora']})."
            )

            try:
                cursor.execute("""
                    INSERT OR REPLACE INTO citas_canceladas_log (
                        agenda_id, token_confirmacion, paciente_id, psicologo_id,
                        paciente_nombre, fecha_cita, hora_cita, tipo_consulta, motivo_cancelacion
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    appt_id, token, cita['paciente_id'], psych_id,
                    pat_full_name, cita['fecha'], cita['hora'], cita['tipo_consulta'],
                    'Cancelada por consultante a tiempo'
                ))
            except Exception as _e_clog:
                print("Error registrando citas_canceladas_log:", _e_clog)

            template = cfg_rows.get(f'msg_cancelacion_ok_{psych_id}') or cfg_rows.get('msg_cancelacion_ok') or "Entendido. Tu cita ha sido cancelada."

            try:
                cursor.execute("""
                    INSERT INTO notificaciones (user_id, tipo, titulo, mensaje, fecha, leida, link)
                    VALUES (?, 'cita', '❌ Cita Cancelada por Consultante', ?, ?, 0, 'agenda')
                """, (psych_id, f"{pat_full_name} ha cancelado su cita del {cita['fecha']} a las {cita['hora']}.", now_str))
            except Exception as _ne:
                print("Error notificando cancelacion publica:", _ne)

            try:
                from app import send_webpush_notification
                send_webpush_notification(
                    user_id=psych_id,
                    title="❌ Cita Cancelada",
                    body=f"{pat_full_name} ha cancelado su cita del {cita['fecha']} a las {cita['hora']}.",
                    url="/?view=agenda"
                )
            except Exception as _wp_ex:
                print("Error enviando WebPush de cancelacion publica:", _wp_ex)

            db.commit()

            response_data = {
                'success': True,
                'late_charge': False,
                'titulo': 'Cita Cancelada',
                'mensaje': 'Has cancelado tu sesión exitosamente sin costo. El horario ha sido liberado.',
                'fast_booking_url': fast_booking_url
            }
        
    elif accion == 'reprogramar':
        cursor.execute("""
            UPDATE agenda_finanzas 
            SET estado_pago = 'Reprogramada', confirmada = 0,
                referencia = CASE WHEN referencia IS NULL OR referencia = '' THEN 'Solicitud de reprogramación por consultante' ELSE referencia || ' | Solicitud de reprogramación por consultante' END
            WHERE id = ?
        """, (appt_id,))
        template = cfg_rows.get(f'msg_reprogramacion_{psych_id}') or cfg_rows.get('msg_reprogramacion')
        if not template:
            template = (
                "Hola *{nombre}*, hemos registrado tu solicitud para *reprogramar* tu consulta del *{fecha}* a las *{hora}*. 🔄\n\n"
                "Por favor selecciona tu nueva fecha y horario disponible aquí:\n{link_agendar}\n\n"
                "¡Nos vemos pronto!"
            )
        _update_google_calendar_status_bg(appt_id, 'reprogramada', motivo='Solicitud de reprogramación por consultante')
        
        try:
            cursor.execute("""
                INSERT OR REPLACE INTO citas_canceladas_log (
                    agenda_id, token_confirmacion, paciente_id, psicologo_id,
                    paciente_nombre, fecha_cita, hora_cita, tipo_consulta, motivo_cancelacion
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                appt_id, token, cita['paciente_id'], psych_id,
                pat_full_name, cita['fecha'], cita['hora'], cita['tipo_consulta'],
                'Solicitud de reprogramación por consultante'
            ))
        except Exception as _e_clog:
            print("Error registrando citas_canceladas_log reprogramacion:", _e_clog)

        # No se envía notificación prematura de 'solicitó reprogramar'.
        # La notificación formal se despachará cuando el paciente concrete su nuevo horario en la agenda.
        db.commit()

        reprog_target_url = f"{fast_booking_url}?reprogramar={token}" if token else fast_booking_url
        response_data = {
            'success': True,
            'reprogramada': True,
            'titulo': 'Reprogramar Cita',
            'mensaje': 'Serás redirigido a la agenda para seleccionar tu nuevo horario.',
            'fast_booking_url': reprog_target_url
        }
        
    db.commit()
    
    try:
        from flask import current_app
        app_obj = current_app._get_current_object()
    except Exception:
        app_obj = None

    import threading
    def _background_tasks():
        if phone:
            try:
                from routes_notificaciones import make_wa_http_request, format_whatsapp_message
                from routes_herramientas import clean_phone_number
                msg = format_whatsapp_message(template, patient_dict, cita_dict, psicologo_data)
                clean_phone = clean_phone_number(phone)
                
                # Marcar en DB como enviado usando ruta absoluta segura
                base_dir = os.path.dirname(os.path.abspath(__file__))
                db_path = os.path.join(base_dir, 'clinica.db')
                db_bg = sqlite3.connect(db_path, timeout=30.0)
                should_send_wa = True
                try:
                    if accion in ('cancelar', 'reprogramar'):
                        db_bg.execute("UPDATE agenda_finanzas SET cierre_enviado_wa = 1 WHERE id = ?", (appt_id,))
                    elif accion == 'confirmar':
                        try:
                            db_bg.execute("ALTER TABLE agenda_finanzas ADD COLUMN respuesta_enviada_wa INTEGER DEFAULT 0")
                        except Exception:
                            pass
                        cur_chk = db_bg.cursor()
                        cur_chk.execute("SELECT respuesta_enviada_wa FROM agenda_finanzas WHERE id = ?", (appt_id,))
                        r_chk = cur_chk.fetchone()
                        if r_chk and r_chk[0] == 1:
                            should_send_wa = False
                            print(f"[WA] Respuesta de confirmación ya enviada previamente para cita {appt_id}. Omitiendo envío duplicado.")
                        else:
                            db_bg.execute("UPDATE agenda_finanzas SET respuesta_enviada_wa = 1 WHERE id = ?", (appt_id,))
                    db_bg.commit()
                except Exception as _dbe:
                    print("Aviso actualizando flag en DB bg:", _dbe)
                finally:
                    db_bg.close()
                
                if should_send_wa:
                    make_wa_http_request('POST', '/send', json_data={'phone': clean_phone, 'text': msg, 'user_id': psych_id}, timeout=15, user_id=psych_id)
            except Exception as e:
                print("Error enviando confirmacion WA desde public link:", e)
                
        try:
            from app import push_all_data_to_firebase
            if app_obj:
                with app_obj.app_context():
                    push_all_data_to_firebase()
            else:
                push_all_data_to_firebase()
        except Exception as e:
            print("Error en push_all_data_to_firebase:", e)
            
    threading.Thread(target=_background_tasks, daemon=True).start()
        
    return jsonify(response_data)

@agenda_bp.route('/api/fast-booking/check-cedula', methods=['POST'])
def fast_booking_check_cedula():
    data = request.json or {}
    cedula = data.get('cedula', '').strip()
    if not cedula:
        return jsonify({'found': False})
    
    db = get_db()
    cursor = db.cursor()
    import re
    import json
    clean_cedula = cedula.strip()
    digits_cedula = re.sub(r'\D', '', clean_cedula)
    
    cursor.execute('''
        SELECT id, nombres, apellidos, telefono, email, costo_personalizado, moneda_personalizada 
        FROM pacientes 
        WHERE (LOWER(REPLACE(REPLACE(REPLACE(REPLACE(cedula, 'V-', ''), 'E-', ''), '.', ''), ' ', '')) = ? AND ? != '') 
           OR (LOWER(REPLACE(REPLACE(REPLACE(cedula, '.', ''), '-', ''), ' ', '')) = LOWER(REPLACE(REPLACE(REPLACE(?, '.', ''), '-', ''), ' ', '')))
           OR (LOWER(username) = LOWER(?) AND username != '')
        LIMIT 1
    ''', (digits_cedula, digits_cedula, clean_cedula, clean_cedula.lower()))
    
    row = cursor.fetchone()
    
    psicologo_id = data.get('psicologo_id')
    slug = data.get('slug')
    modalidad = data.get('modalidad', 'Online')

    if not psicologo_id and slug:
        from app import get_psychologist_by_id_or_slug
        psych = get_psychologist_by_id_or_slug(cursor, slug)
        if psych:
            psicologo_id = psych['id']
            
    # Leer configuración de fuera de jornada del psicólogo
    tipo_cobro = 'recargo'
    recargo_monto = 5.0
    recargo_moneda = 'USD'
    fuera_perfiles = []
    
    if psicologo_id:
        try:
            cursor.execute("SELECT configuracion_horarios_visual FROM usuarios WHERE id = ?", (psicologo_id,))
            u_r = cursor.fetchone()
            if u_r and u_r['configuracion_horarios_visual']:
                cfg_v = json.loads(u_r['configuracion_horarios_visual'])
                tipo_cobro = cfg_v.get('fuera_jornada_tipo_cobro', 'recargo')
                recargo_monto = float(cfg_v.get('fuera_jornada_recargo_monto', 5.0))
                recargo_moneda = cfg_v.get('fuera_jornada_recargo_moneda', 'USD')
                fuera_perfiles = cfg_v.get('fuera_jornada_perfiles', [])
        except Exception:
            pass

    paciente_id = row['id'] if row else 0
    base_fee, moneda = get_appointment_fee(cursor, paciente_id, psicologo_id, modalidad)
    
    if tipo_cobro == 'recargo':
        total_fee = base_fee + recargo_monto
        res_payload = {
            'tipo_cobro': 'recargo',
            'base_fee': base_fee,
            'recargo_monto': recargo_monto,
            'total_fee': total_fee,
            'moneda': moneda or recargo_moneda
        }
    else:
        # Fijo
        fixed_fee = base_fee
        for fp in fuera_perfiles:
            if fp.get('nombre') == modalidad or fp.get('modalidad') == modalidad:
                fixed_fee = float(fp.get('costo') or fixed_fee)
                moneda = fp.get('moneda') or moneda
                break
        res_payload = {
            'tipo_cobro': 'fijo',
            'base_fee': fixed_fee,
            'total_fee': fixed_fee,
            'moneda': moneda
        }

    if row:
        res_payload.update({
            'found': True,
            'nombres': row['nombres'],
            'apellidos': row['apellidos'],
            'telefono': row['telefono'],
            'email': row['email']
        })
    else:
        res_payload.update({
            'found': False
        })
        
    return jsonify(res_payload)


# ==============================================================================
# GESTIÓN DE ATENCIÓN FUERA DE LA JORNADA
# ==============================================================================

def ensure_solicitudes_fuera_horario_table(cursor):
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS solicitudes_fuera_horario (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                psicologo_id INTEGER NOT NULL,
                paciente_id INTEGER,
                nombres TEXT NOT NULL,
                apellidos TEXT,
                cedula TEXT,
                telefono TEXT NOT NULL,
                email TEXT,
                tipo_consulta TEXT NOT NULL,
                fecha TEXT NOT NULL,
                hora_inicio TEXT NOT NULL,
                hora_fin TEXT NOT NULL,
                duracion_minutos INTEGER DEFAULT 50,
                monto REAL NOT NULL DEFAULT 0.0,
                moneda TEXT NOT NULL DEFAULT 'USD',
                estado TEXT DEFAULT 'Pendiente',
                motivo_rechazo TEXT,
                agenda_id INTEGER,
                creado_en DATETIME DEFAULT CURRENT_TIMESTAMP,
                respondido_en DATETIME
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_solicitudes_fuera_psicologo ON solicitudes_fuera_horario(psicologo_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_solicitudes_fuera_fecha ON solicitudes_fuera_horario(fecha)")
    except Exception as e:
        print("[FUERA_HORARIO] Error al asegurar tabla solicitudes_fuera_horario:", e)

@agenda_bp.route('/api/public/solicitar-fuera-horario/<path:slug>', methods=['POST'])
def solicitar_fuera_horario(slug):
    """Permite al consultante solicitar una cita fuera del horario habitual."""
    db = get_db()
    cursor = db.cursor()
    ensure_solicitudes_fuera_horario_table(cursor)
    try:
        from app import get_psychologist_by_id_or_slug
        import re
        from datetime import datetime, timedelta
        
        clean_slug = str(slug).strip()
        for prefix in ['psicologo/', 'psic/', 'psic.', 'agendar/', 'registro/']:
            if clean_slug.lower().startswith(prefix):
                clean_slug = clean_slug[len(prefix):]
                
        psych = get_psychologist_by_id_or_slug(cursor, clean_slug)
        if not psych:
            psych = get_psychologist_by_id_or_slug(cursor, slug)
        if not psych:
            return jsonify({'error': 'Especialista no encontrado.'}), 404
            
        psicologo_id = int(psych['id'])
        
        # Verificar si el psicólogo tiene activa la función de fuera de jornada
        cfg_visual = {}
        try:
            if psych['configuracion_horarios_visual']:
                cfg_visual = json.loads(psych['configuracion_horarios_visual'])
        except Exception:
            cfg_visual = {}
            
        if not cfg_visual.get('fuera_jornada_activo'):
            return jsonify({'error': 'El psicólogo no tiene habilitada la recepción de solicitudes fuera de jornada.'}), 400
    
        data = request.json or {}
        fecha = (data.get('fecha') or '').strip()
        hora_inicio = (data.get('hora_inicio') or data.get('hora') or '').strip()
        tipo_consulta = (data.get('tipo_consulta') or data.get('modalidad') or 'Online').strip()
        cedula = (data.get('cedula') or '').strip()
        nombres = (data.get('nombres') or '').strip()
        apellidos = (data.get('apellidos') or '').strip()
        telefono = (data.get('telefono') or '').strip()
        email = (data.get('email') or '').strip()
        
        if not fecha or not hora_inicio or not cedula or not nombres or not telefono:
            return jsonify({'error': 'Todos los campos requeridos deben ser completados.'}), 400
    
        # Normalizar fecha y hora inicio
        fecha_norm = normalize_date_str(fecha)
        hora_inicio_norm = normalize_time_str(hora_inicio)
        
        # Determinar duración de la sesión según perfil o global
        perfiles = cfg_visual.get('perfiles', [])
        duracion = int(cfg_visual.get('duracion', 50))
        for p in perfiles:
            if (p.get('nombre') == tipo_consulta or p.get('modalidad') == tipo_consulta) and p.get('duracion'):
                try:
                    duracion = int(p['duracion'])
                    break
                except Exception:
                    pass
                    
        # Calcular hora fin
        try:
            t_start = datetime.strptime(hora_inicio_norm, "%H:%M")
            t_end = t_start + timedelta(minutes=duracion)
            hora_fin_norm = t_end.strftime("%H:%M")
        except Exception:
            hora_fin_norm = hora_inicio_norm
            
        # La tarifa final se calculará después de identificar al paciente según el tipo de cobro configurado (recargo o fijo)
    
        # Validar contra Franjas Bloqueadas Fijas Fuera de Jornada (ej. trabajo en colegio)
        fuera_bloqueos = cfg_visual.get('fuera_jornada_bloqueos', [])
        if fuera_bloqueos:
            try:
                req_d_obj = datetime.strptime(fecha_norm, "%Y-%m-%d")
                # 0=Domingo, 1=Lunes, ..., 6=Sábado
                req_dow = (req_d_obj.weekday() + 1) % 7
                req_s = datetime.strptime(hora_inicio_norm, "%H:%M")
                req_e = datetime.strptime(hora_fin_norm, "%H:%M")
                
                for b in fuera_bloqueos:
                    b_dias = [int(x) for x in b.get('dias', [])]
                    if req_dow in b_dias:
                        b_ini_str = normalize_time_str(b.get('hora_inicio', '00:00'))
                        b_fin_str = normalize_time_str(b.get('hora_fin', '23:59'))
                        b_s = datetime.strptime(b_ini_str, "%H:%M")
                        b_e = datetime.strptime(b_fin_str, "%H:%M")
                        if max(req_s, b_s) < min(req_e, b_e):
                            motivo = b.get('motivo') or 'Compromiso laboral / Espacio bloqueado'
                            return jsonify({'error': f'El especialista no puede atender en esa franja ({motivo}). Por favor selecciona otra hora o fecha.'}), 400
            except Exception:
                pass
    
        # Validar contra Bloqueos Específicos de Agenda (vacaciones, ausencias puntuales)
        try:
            cursor.execute("""
                SELECT motivo, hora_inicio, hora_fin, todo_el_dia 
                FROM bloqueos_agenda_especificos
                WHERE psicologo_id = ? 
                  AND (fecha = ? OR (? BETWEEN fecha AND COALESCE(fecha_fin, fecha)))
            """, (psicologo_id, fecha_norm, fecha_norm))
            esp_bloqueos = cursor.fetchall()
            for eb in esp_bloqueos:
                if eb['todo_el_dia']:
                    motivo = eb['motivo'] or 'Día no laborable'
                    return jsonify({'error': f'El especialista no tiene disponibilidad en esta fecha ({motivo}).'}), 400
                if eb['hora_inicio'] and eb['hora_fin']:
                    eb_s = datetime.strptime(normalize_time_str(eb['hora_inicio']), "%H:%M")
                    eb_e = datetime.strptime(normalize_time_str(eb['hora_fin']), "%H:%M")
                    req_s = datetime.strptime(hora_inicio_norm, "%H:%M")
                    req_e = datetime.strptime(hora_fin_norm, "%H:%M")
                    if max(req_s, eb_s) < min(req_e, eb_e):
                        motivo = eb['motivo'] or 'Compromiso agendado'
                        return jsonify({'error': f'El especialista tiene un bloqueo en ese horario ({motivo}). Por favor selecciona otra hora.'}), 400
        except Exception:
            pass
    
        # Validar que no choque con citas activas en agenda_finanzas
        cursor.execute("""
            SELECT a.id, a.hora, a.tipo_consulta 
            FROM agenda_finanzas a
            WHERE a.creado_por_user_id = ? AND a.fecha = ?
              AND (a.estado_pago IS NULL OR (a.estado_pago NOT LIKE 'Cancelada%' AND a.estado_pago != 'Reprogramada'))
        """, (psicologo_id, fecha_norm))
        existing_citas = cursor.fetchall()
        
        for c in existing_citas:
            c_hora_str = normalize_time_str(c['hora'])
            try:
                c_start = datetime.strptime(c_hora_str, "%H:%M")
                c_end = c_start + timedelta(minutes=duracion)
                req_start = datetime.strptime(hora_inicio_norm, "%H:%M")
                req_end = datetime.strptime(hora_fin_norm, "%H:%M")
                if max(req_start, c_start) < min(req_end, c_end):
                    return jsonify({'error': 'El especialista ya tiene un compromiso agendado en ese rango de horario. Por favor selecciona otra hora.'}), 400
            except Exception:
                pass
    
        # Validar que no choque con otra solicitud activa en solicitudes_fuera_horario
        cursor.execute("""
            SELECT sf.id, sf.hora_inicio, sf.hora_fin, sf.estado, sf.agenda_id, sf.paciente_id, sf.cedula,
                   af.id as af_id, af.estado_pago as af_estado_pago
            FROM solicitudes_fuera_horario sf
            LEFT JOIN agenda_finanzas af ON sf.agenda_id = af.id
            WHERE sf.psicologo_id = ? AND sf.fecha = ? AND sf.estado IN ('Pendiente', 'Aceptada')
        """, (psicologo_id, fecha_norm))
        existing_reqs = cursor.fetchall()
        for er in existing_reqs:
            # Si estaba Aceptada pero la cita en agenda_finanzas ya no existe o fue cancelada, actualizar estado y no bloquear
            if er['estado'] == 'Aceptada':
                if not er['agenda_id'] or not er['af_id'] or (er['af_estado_pago'] and ('cancelad' in str(er['af_estado_pago']).lower() or str(er['af_estado_pago']) == 'Reprogramada')):
                    try:
                        cursor.execute("UPDATE solicitudes_fuera_horario SET estado = 'Cancelada' WHERE id = ?", (er['id'],))
                        db.commit()
                    except Exception:
                        pass
                    continue

            try:
                er_start = datetime.strptime(normalize_time_str(er['hora_inicio']), "%H:%M")
                er_end = datetime.strptime(normalize_time_str(er['hora_fin']), "%H:%M")
                req_start = datetime.strptime(hora_inicio_norm, "%H:%M")
                req_end = datetime.strptime(hora_fin_norm, "%H:%M")
                if max(req_start, er_start) < min(req_end, er_end):
                    # Si es una solicitud Pendiente previa del mismo paciente (misma cédula), se sustituye limpiamente
                    er_ced = re.sub(r'\D', '', str(er.get('cedula') or ''))
                    cur_ced = re.sub(r'\D', '', str(cedula or ''))
                    if er['estado'] == 'Pendiente' and er_ced and cur_ced and er_ced == cur_ced:
                        cursor.execute("UPDATE solicitudes_fuera_horario SET estado = 'Cancelada' WHERE id = ?", (er['id'],))
                        db.commit()
                        continue
                    return jsonify({'error': 'Ya existe una solicitud pendiente o confirmada para ese rango de horario. Por favor selecciona otra hora.'}), 400
            except Exception:
                pass
    
        # Buscar o registrar paciente
        clean_cedula = cedula.strip()
        digits_cedula = re.sub(r'\D', '', clean_cedula)
        cursor.execute("""
            SELECT id FROM pacientes 
            WHERE ((LOWER(REPLACE(REPLACE(REPLACE(REPLACE(cedula, 'V-', ''), 'E-', ''), '.', ''), ' ', '')) = ? AND ? != '')
               OR (LOWER(REPLACE(REPLACE(REPLACE(cedula, '.', ''), '-', ''), ' ', '')) = LOWER(REPLACE(REPLACE(REPLACE(?, '.', ''), '-', ''), ' ', ''))))
               AND (psicologo_id = ? OR psicologo_id IS NULL)
            LIMIT 1
        """, (digits_cedula, digits_cedula, clean_cedula, psicologo_id))
        p_row = cursor.fetchone()
        if p_row:
            paciente_id = p_row['id']
        else:
            cursor.execute("""
                INSERT INTO pacientes (nombres, apellidos, cedula, telefono, email, psicologo_id)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (nombres, apellidos, cedula, telefono, email, psicologo_id))
            paciente_id = cursor.lastrowid
            db.commit()
    
        # Calcular tarifa de la solicitud según el tipo de cobro configurado (recargo o fijo)
        tipo_cobro = cfg_visual.get('fuera_jornada_tipo_cobro', 'recargo')
        recargo_monto = float(cfg_visual.get('fuera_jornada_recargo_monto', 5.0))
        recargo_moneda = cfg_visual.get('fuera_jornada_recargo_moneda', 'USD')
        fuera_perfiles = cfg_visual.get('fuera_jornada_perfiles', [])

        if tipo_cobro == 'recargo':
            base_fee, base_moneda = get_appointment_fee(cursor, paciente_id, psicologo_id, tipo_consulta)
            monto = base_fee + recargo_monto
            moneda = base_moneda or recargo_moneda
        else:
            monto = 0.0
            moneda = 'USD'
            profile_found = False
            for fp in fuera_perfiles:
                if fp.get('nombre') == tipo_consulta or fp.get('modalidad') == tipo_consulta:
                    monto = float(fp.get('costo') or 0.0)
                    moneda = fp.get('moneda') or 'USD'
                    profile_found = True
                    break
            if not profile_found and fuera_perfiles:
                return jsonify({'error': f'La modalidad "{tipo_consulta}" no está habilitada para citas fuera de jornada.'}), 400
            elif not profile_found:
                base_fee, base_moneda = get_appointment_fee(cursor, paciente_id, psicologo_id, tipo_consulta)
                monto = base_fee
                moneda = base_moneda

        # Insertar en solicitudes_fuera_horario
        cursor.execute("""
            INSERT INTO solicitudes_fuera_horario (
                psicologo_id, paciente_id, nombres, apellidos, cedula, telefono, email,
                tipo_consulta, fecha, hora_inicio, hora_fin, duracion_minutos,
                monto, moneda, estado
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Pendiente')
        """, (
            psicologo_id, paciente_id, nombres, apellidos, cedula, telefono, email,
            tipo_consulta, fecha_norm, hora_inicio_norm, hora_fin_norm, duracion,
            monto, moneda
        ))
        solicitud_id = cursor.lastrowid
    
        # 1. Notificación en campana para el psicólogo
        try:
            cursor.execute("""
                INSERT INTO notificaciones (user_id, tipo, titulo, mensaje, fecha, leida, link)
                VALUES (?, 'solicitud_fuera', ?, ?, CURRENT_TIMESTAMP, 0, 'agenda')
            """, (
                psicologo_id,
                "✨ Solicitud de Consulta Personalizada",
                f"{nombres} {apellidos} ha solicitado consulta ({tipo_consulta}) para el {fecha_norm} a las {hora_inicio_norm}."
            ))
        except Exception as _ne:
            print("[NOTIF] Error guardando notificacion de fuera de jornada:", _ne)

        db.commit()

        # 2. Notificación WebPush en segundo plano para el psicólogo
        try:
            from app import send_webpush_notification
            send_webpush_notification(
                user_id=psicologo_id,
                title="✨ Solicitud de Consulta Personalizada",
                body=f"{nombres} {apellidos} ha solicitado consulta ({tipo_consulta}) para el {fecha_norm} a las {hora_inicio_norm}.",
                url="/?view=agenda"
            )
        except Exception as _wp_ex:
            print("[WEBPUSH] Error enviando WebPush de solicitud fuera de jornada:", _wp_ex)
        
        return jsonify({
            'success': True,
            'solicitud_id': solicitud_id,
            'mensaje': 'Tu solicitud ha sido enviada al especialista. Te responderá a la brevedad vía WhatsApp o llamada.',
            'fecha': fecha_norm,
            'hora_inicio': hora_inicio_norm,
            'hora_fin': hora_fin_norm,
            'monto': monto,
            'moneda': moneda
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Error interno al procesar la solicitud: {str(e)}'}), 500


@agenda_bp.route('/api/admin/solicitudes-fuera-horario', methods=['GET'])
@login_required
def admin_get_solicitudes_fuera_horario():
    """Retorna las solicitudes fuera de jornada del psicólogo logueado."""
    db = get_db()
    cursor = db.cursor()
    ensure_solicitudes_fuera_horario_table(cursor)
    user_id = session.get('user_id')
    
    cursor.execute("""
        SELECT s.*, p.nombres AS pac_nombres, p.apellidos AS pac_apellidos, p.telefono AS pac_telefono
        FROM solicitudes_fuera_horario s
        LEFT JOIN pacientes p ON s.paciente_id = p.id
        WHERE s.psicologo_id = ?
        ORDER BY CASE WHEN s.estado = 'Pendiente' THEN 0 ELSE 1 END, s.fecha DESC, s.hora_inicio DESC
    """, (user_id,))
    
    rows = cursor.fetchall()
    solicitudes = []
    total_pendientes = 0
    for r in rows:
        d = dict(r)
        if d.get('estado') == 'Pendiente':
            total_pendientes += 1
        solicitudes.append(d)
        
    return jsonify({
        'solicitudes': solicitudes,
        'total_pendientes': total_pendientes
    })


@agenda_bp.route('/api/admin/solicitudes-fuera-horario/<int:req_id>/responder', methods=['POST'])
@login_required
def admin_responder_solicitud_fuera_horario(req_id):
    """Acepta o declina una solicitud fuera de jornada y genera el mensaje de WhatsApp/Push."""
    db = get_db()
    cursor = db.cursor()
    ensure_solicitudes_fuera_horario_table(cursor)
    user_id = session.get('user_id')
    import re
    import urllib.parse
    
    cursor.execute("SELECT * FROM solicitudes_fuera_horario WHERE id = ? AND psicologo_id = ?", (req_id, user_id))
    req_row = cursor.fetchone()
    if not req_row:
        return jsonify({'error': 'Solicitud no encontrada.'}), 404
        
    sol = dict(req_row)
    data = request.json or {}
    accion = (data.get('accion') or '').strip().lower()
    motivo = (data.get('motivo') or '').strip()
    
    if accion not in ('aceptar', 'declinar'):
        return jsonify({'error': 'Acción inválida. Debe ser aceptar o declinar.'}), 400

    cursor.execute("SELECT nombres, apellidos, username, slug FROM usuarios WHERE id = ?", (user_id,))
    u_row = cursor.fetchone()
    psicologo_nombre = f"Psic. {u_row['nombres']} {u_row['apellidos']}".strip() if u_row else "Psicólogo"
    from routes_admin import generate_default_slug_for_user
    psic_slug = generate_default_slug_for_user(dict(u_row)) if u_row else 'psicologo'
    link_agendar = f"{request.host_url.rstrip('/')}/agendar/{psic_slug}"

    paciente_id = sol.get('paciente_id')
    pac_telefono = sol.get('telefono', '').strip()
    clean_phone = re.sub(r'\D', '', pac_telefono)
    if clean_phone and not clean_phone.startswith(('58', '57', '1', '34', '54', '56', '51', '52', '593')):
        if clean_phone.startswith('04'):
            clean_phone = '58' + clean_phone[1:]
        elif clean_phone.startswith('4'):
            clean_phone = '58' + clean_phone

    tokens_fcm = []
    if paciente_id:
        try:
            cursor.execute("SELECT token FROM fcm_subscriptions WHERE patient_id = ? OR patient_id = ?", (paciente_id, str(paciente_id)))
            tokens_fcm = [r['token'] for r in cursor.fetchall() if r['token']]
        except Exception:
            pass

    agenda_id = None
    wa_text = ""

    if accion == 'aceptar':
        import secrets
        from datetime import datetime, timedelta
        
        token_conf = secrets.token_urlsafe(16)
        is_same_day = (sol['fecha'] == datetime.now().strftime("%Y-%m-%d"))
        confirmada_val = 1 if is_same_day else 0

        cursor.execute("""
            INSERT INTO agenda_finanzas (
                paciente_id, fecha, hora, tipo_consulta, monto, moneda,
                estado_pago, control_uso, creado_por_user_id, confirmada, token_confirmacion, referencia
            ) VALUES (?, ?, ?, ?, ?, ?, 'Agendada', 'No consumida', ?, ?, ?, ?)
        """, (
            paciente_id,
            sol['fecha'],
            sol['hora_inicio'],
            sol['tipo_consulta'],
            sol['monto'],
            sol['moneda'],
            user_id,
            confirmada_val,
            token_conf,
            f"Solicitud fuera de jornada aprobada #SFH-{sol['id']}"
        ))
        agenda_id = cursor.lastrowid
        
        cursor.execute("""
            UPDATE solicitudes_fuera_horario
            SET estado = 'Aceptada', agenda_id = ?, respondido_en = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (agenda_id, req_id))
        db.commit()

        # Sincronización en Google Calendar
        try:
            from routes_admin import get_calendar_service
            service = get_calendar_service(user_id, db=db)
            if service:
                dur_m = sol.get('duracion_minutos') or 60
                st_obj = datetime.strptime(sol['hora_inicio'], "%H:%M")
                en_obj = st_obj + timedelta(minutes=dur_m)
                start_dt = f"{sol['fecha']}T{sol['hora_inicio']}:00-04:00"
                end_dt = f"{sol['fecha']}T{en_obj.strftime('%H:%M')}:00-04:00"
                summary_text = f"🟠 Consulta {sol['tipo_consulta']} (Personalizada) - {sol.get('nombres','')} {sol.get('apellidos','')}".strip()
                event_body = {
                    'summary': summary_text,
                    'colorId': '6',
                    'description': f"Modalidad: {sol['tipo_consulta']}\nPsicólogo: {psicologo_nombre}\nTarifa especial fuera de jornada: {sol['monto']} {sol['moneda']}",
                    'start': {'dateTime': start_dt, 'timeZone': 'America/Caracas'},
                    'end': {'dateTime': end_dt, 'timeZone': 'America/Caracas'},
                    'guestsCanInviteOthers': False
                }
                if sol.get('email'):
                    event_body['attendees'] = [{'email': sol['email'], 'displayName': f"{sol.get('nombres','')} {sol.get('apellidos','')}".strip()}]
                g_event = service.events().insert(calendarId='primary', body=event_body, sendUpdates='all').execute()
                if g_event and g_event.get('id'):
                    cursor.execute("UPDATE agenda_finanzas SET google_event_id = ? WHERE id = ?", (g_event.get('id'), agenda_id))
                    db.commit()
        except Exception as _gerr:
            print("Error sincronizando solicitud fuera de jornada a Google Calendar:", _gerr)

        # Despachar notificación automática inmediata por WhatsApp si aplica
        try:
            from routes_notificaciones import send_booking_notification_wa
            send_booking_notification_wa(agenda_id, user_id)
        except Exception as _wa_err:
            print("[WA-BOOKING] Error despachando notificacion fuera de jornada:", _wa_err)

        from routes_notificaciones import get_public_base_url
        domain_host = get_public_base_url()
        link_confirmacion = f"{domain_host}/cita/confirmar/{token_conf}"
        
        psic_key = f"msg_fuera_jornada_aceptada_{user_id}"
        cursor.execute("SELECT valor FROM configuracion WHERE clave = ?", (psic_key,))
        cfg_r = cursor.fetchone()
        if not cfg_r or not cfg_r['valor']:
            cursor.execute("SELECT valor FROM configuracion WHERE clave = 'msg_fuera_jornada_aceptada'")
            cfg_r = cursor.fetchone()
            
        raw_tmpl = (cfg_r['valor'] if cfg_r and cfg_r['valor'] else "") or (
            "Hola {nombre}, he revisado y aceptado tu solicitud de consulta personalizada para el *{fecha}* a las *{hora}* ({modalidad}). Monto: *{monto} {moneda}*.\n\nPuedes confirmar tu asistencia ingresando en este enlace:\n{link_confirmacion}\n\n¡Nos vemos pronto!"
        )
        
        wa_text = raw_tmpl.replace('{nombre}', sol.get('nombres', '')).replace('{fecha}', sol.get('fecha', '')).replace('{hora}', sol.get('hora_inicio', '')).replace('{modalidad}', sol.get('tipo_consulta', '')).replace('{monto}', str(sol.get('monto', '0'))).replace('{moneda}', sol.get('moneda', 'USD')).replace('{psicologo}', psicologo_nombre).replace('{link_confirmacion}', link_confirmacion)
        if '{link_confirmacion}' not in raw_tmpl and confirmada_val == 0:
            wa_text += f"\n\nPuedes confirmar tu asistencia aquí:\n{link_confirmacion}"

        if paciente_id:
            try:
                from app import notify_patient
                notify_patient(
                    paciente_id,
                    "¡Solicitud de Consulta Aceptada!",
                    f"Tu cita personalizada ({sol['tipo_consulta']}) para el {sol['fecha']} a las {sol['hora_inicio']} ha sido confirmada por {psicologo_nombre}.",
                    link="/#citas"
                )
            except Exception as _pne:
                print("[NOTIF_PACIENTE] Error:", _pne)

        if tokens_fcm:
            try:
                from app import send_push_notification_to_patient
                send_push_notification_to_patient(
                    paciente_id,
                    "¡Solicitud Fuera de Jornada Aceptada!",
                    f"Tu cita para el {sol['fecha']} a las {sol['hora_inicio']} ha sido aceptada por {psicologo_nombre}."
                )
            except Exception as _pe:
                print(f"[PUSH] Error al enviar push de aceptación: {_pe}")

    else:
        cursor.execute("""
            UPDATE solicitudes_fuera_horario
            SET estado = 'Declinada', motivo_rechazo = ?, respondido_en = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (motivo, req_id))
        
        psic_key = f"msg_fuera_jornada_declinada_{user_id}"
        cursor.execute("SELECT valor FROM configuracion WHERE clave = ?", (psic_key,))
        cfg_r = cursor.fetchone()
        if not cfg_r or not cfg_r['valor']:
            cursor.execute("SELECT valor FROM configuracion WHERE clave = 'msg_fuera_jornada_declinada'")
            cfg_r = cursor.fetchone()
            
        raw_tmpl = (cfg_r['valor'] if cfg_r and cfg_r['valor'] else "") or (
            "Hola {nombre}, lamentablemente no me es posible atender tu solicitud de cita fuera de jornada para el *{fecha}* a las *{hora}*. Te invito a agendar en mis horarios regulares disponibles en:\n{link_agendar}"
        )
        
        wa_text = raw_tmpl.replace('{nombre}', sol.get('nombres', '')).replace('{fecha}', sol.get('fecha', '')).replace('{hora}', sol.get('hora_inicio', '')).replace('{motivo}', motivo or '').replace('{psicologo}', psicologo_nombre).replace('{link_agendar}', link_agendar)

        if tokens_fcm:
            try:
                from app import send_push_notification_to_patient
                send_push_notification_to_patient(
                    paciente_id,
                    "Solicitud Fuera de Jornada",
                    f"Tu solicitud para el {sol['fecha']} a las {sol['hora_inicio']} no pudo ser aceptada."
                )
            except Exception as _pe:
                print(f"[PUSH] Error al enviar push de rechazo: {_pe}")

    db.commit()

    wa_enviado_auto = False
    if clean_phone and wa_text:
        try:
            from routes_notificaciones import make_wa_http_request
            res_wa = make_wa_http_request('POST', '/send', json_data={
                'phone': clean_phone,
                'text': wa_text,
                'user_id': user_id
            })
            if res_wa and res_wa.get('status') == 'success':
                wa_enviado_auto = True
        except Exception:
            pass

    wa_url = f"https://wa.me/{clean_phone}?text={urllib.parse.quote(wa_text)}" if clean_phone else ""

    return jsonify({
        'success': True,
        'accion': accion,
        'agenda_id': agenda_id,
        'has_fcm': len(tokens_fcm) > 0,
        'wa_enviado_auto': wa_enviado_auto,
        'wa_text': wa_text,
        'wa_url': wa_url
    })
