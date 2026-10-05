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
            # En contexto clínico de consultas, horas entre 1 y 6 sin AM/PM corresponden a la tarde (13:00 a 18:00)
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

def get_appointment_duration_and_recess(tipo_consulta, perfiles, default_duracion=60, default_receso=0):
    tipo_clean = (tipo_consulta or '').strip().lower()
    for p in perfiles:
        p_name = (p.get('nombre') or p.get('modalidad') or '').strip().lower()
        p_mod = (p.get('modalidad') or p.get('nombre') or '').strip().lower()
        if tipo_clean and (tipo_clean in p_name or p_name in tipo_clean or tipo_clean in p_mod or p_mod in tipo_clean):
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
            ea_end = ea_start + timedelta(minutes=ea_dur * ea_cant)
            ea_busy_until = ea_end + timedelta(minutes=ea_rec)

            # 1. Colisión directa de sesión: dos consultantes citados durante el mismo intervalo de tiempo
            if req_start < ea_end and req_end > ea_start:
                return True
            # 2. Inicia durante el receso/descanso de la cita previa
            if req_start >= ea_start and req_start < ea_busy_until:
                return True
            # 3. La cita previa empieza durante el receso de la nueva cita solicitada
            if ea_start >= req_start and ea_start < req_busy_until:
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
            b_end = b_start + timedelta(minutes=b_dur * b_cant)
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

    # 3. Iterar cada perfil configurado
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
            mod_match = is_all_mod or (blk_mod in perf_mod_clean or perf_mod_clean in blk_mod or blk_mod in perf_nom_clean or perf_nom_clean in blk_mod)
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

                        # Generar turnos en ventanas libres continuas (Floating Slots)
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
    modalidad = request.args.get('modalidad', 'all')
    
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
                       WHERE s.agenda_id = af.id OR (s.paciente_id = af.paciente_id AND s.fecha = af.fecha)
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

        cursor.execute("""
            INSERT INTO bloqueos_agenda_especificos (psicologo_id, fecha, fecha_fin, modalidad, hora_inicio, hora_fin, motivo, todo_el_dia)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (target_psic_id, fecha, fecha_fin or None, modalidad, hora_inicio, hora_fin, motivo, todo_el_dia))
        db.commit()
        block_id = cursor.lastrowid
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
    confirmada = int(data.get('confirmada', 0) or 0)
    hora_paciente = (data.get('hora_paciente') or '').strip() or None  # Hora en zona horaria del paciente (calculada en frontend)

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
    except Exception as ge:
        print("Error creando cita en Google Calendar:", ge)
    
    cursor.execute("""
        INSERT INTO agenda_finanzas (
            paciente_id, fecha, hora, tipo_consulta, monto, moneda, 
            estado_pago, control_uso, google_event_id, cantidad_sesiones,
            referencia, metodo_pago, fecha_pago, confirmada, consultorio_nombre, creado_por_user_id,
            hora_paciente
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        paciente_id, fecha, hora, tipo_consulta, monto, moneda,
        estado_pago, control_uso, google_event_id, cantidad_sesiones,
        referencia, metodo_pago, fecha_pago, confirmada, consultorio_nombre, creado_por_user_id,
        hora_paciente
    ))
    db.commit()
    event_id = cursor.lastrowid

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

    # Notificar al consultante vía WebPush y Firebase si está disponible
    if paciente_id:
        try:
            from app import send_webpush_notification, FIREBASE_DB_URL
            import requests
            hora_display = hora_paciente or hora  # Mostrar la hora en la zona horaria del paciente
            send_webpush_notification(
                patient_id=paciente_id,
                title="📅 Nueva Cita Agendada",
                body=f"Tu psicólogo ha programado una consulta para el {fecha} a las {hora_display}.",
                url="/?view=citas"
            )
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            fb_payload = {
                "id": int(datetime.now().timestamp() * 1000),
                "tipo": "cita",
                "titulo": "📅 Nueva Cita Agendada",
                "mensaje": f"Tu psicólogo ha programado una consulta para el {fecha} a las {hora_display}.",
                "fecha": now_str,
                "leida": False
            }
            requests.post(f"{FIREBASE_DB_URL}/pacientes/{paciente_id}/notificaciones.json", json=fb_payload, timeout=2.0)
        except Exception as _ex_pac:
            print("Error notificando al paciente sobre cita creada:", _ex_pac)
    
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
    cita = cursor.fetchone()
    if not cita:
        return jsonify({'error': 'Cita no encontrada.'}), 404

    updates = []
    params = []
    
    target_cancellation = None
    if estado_pago in ['Cancelada con aviso', 'Cancelada sin aviso', 'Cancelada']:
        target_cancellation = estado_pago
    elif estado in ['Cancelada con aviso', 'Cancelada sin aviso', 'Cancelada']:
        target_cancellation = estado

    if target_cancellation == 'Cancelada con aviso':
        updates.append("estado_pago = 'Cancelada con aviso'")
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
            new_ref = f"Cancelada con aviso: {motivo}" if not cita['referencia'] else f"{cita['referencia']} | Cancelada con aviso: {motivo}"
            updates.append("referencia = ?")
            params.append(new_ref)
            
        try:
            from app import create_auto_cancellation_session
            cancellation_reason = f"Consulta cancelada con aviso por el terapeuta. Motivo: {motivo}" if motivo else "Consulta cancelada con aviso por el terapeuta."
            create_auto_cancellation_session(db, cita['paciente_id'], event_id, cita['fecha'], cita['tipo_consulta'], 'Cancelada con aviso', cancellation_reason)
        except Exception as se:
            print("Error creando sesion de cancelacion con aviso:", se)
            
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
    
    # Enviar mensaje de WhatsApp si corresponde
    try:
        from routes_notificaciones import make_wa_http_request, format_whatsapp_message
        from routes_herramientas import clean_phone_number
        is_confirming = (confirmada == 1 or estado == 'Confirmada')
        is_cancelling = bool(target_cancellation)

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
            else:
                template = templates.get('msg_cancelacion_ok') or "Entendido. ❌ Tu cita ha sido cancelada. Si deseas reagendar o tienes alguna duda, por favor contáctanos."
            
            msg = format_whatsapp_message(template, patient_dict, cita_dict, psicologo_data)
            make_wa_http_request('POST', '/send', json_data={'phone': phone_clean, 'text': msg, 'user_id': psych_id}, timeout=10, user_id=psych_id)
    except Exception as e:
        print("Error sending manual confirmation WA:", e)

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
            from routes_admin import get_calendar_service, update_calendar_event_status
            service = get_calendar_service(psych_id, db=db)
            if service:
                update_calendar_event_status(
                    service, cita['google_event_id'], 'cancelada',
                    motivo="Eliminada de la agenda de la clínica"
                )
        except Exception as ge:
            print("Error al actualizar evento en Google Calendar al borrar cita:", ge)

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
    db.commit()

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
        "alerta_confirmacion_tipo": "horas",
        "alerta_confirmacion_valor": 24,
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
    modalities = [
        {"nombre": "Online", "modalidad": "Online", "descripcion": "Consultas a través de WhatsApp y Google Meet videollamadas"},
        {"nombre": "Presencial", "modalidad": "Presencial", "descripcion": "Consultas presenciales en consultorio físico"}
    ]
    if u_row and u_row[0]:
        try:
            import json
            config = json.loads(u_row[0])
            raw_perfiles = config.get('perfiles', [])
            if isinstance(raw_perfiles, dict):
                m_names = list(raw_perfiles.keys())
                if m_names:
                    modalities = [{"nombre": k, "modalidad": k, "descripcion": ""} for k in m_names]
            elif isinstance(raw_perfiles, list) and len(raw_perfiles) > 0:
                result = []
                for p in raw_perfiles:
                    nom = p.get('nombre') or p.get('modalidad')
                    if nom:
                        result.append({
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
    if check_appointment_interval_collision(cursor, psicologo_id, fecha_norm, hora_norm, modalidad):
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
        
        cursor.execute("""
            INSERT INTO agenda_finanzas (
                paciente_id, fecha, hora, hora_paciente, tipo_consulta, monto, moneda, 
                estado_pago, control_uso, google_event_id, cantidad_sesiones, referencia, creado_por_user_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'Agendada', 'No consumida', NULL, 1, ?, ?)
        """, (patient_id, fecha_norm, hora_norm, hora_paciente, modalidad, monto, moneda, f"Auto-agendada rápida por paciente. Cédula: {cedula}", psicologo_id))
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

        # Enviar notificación al psicólogo en SQLite
        from datetime import datetime
        fecha_notif = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
            INSERT INTO notificaciones (user_id, tipo, titulo, mensaje, fecha, leida, link)
            VALUES (?, ?, ?, ?, ?, 0, ?)
        """, (psicologo_id, 'cita', 'Nueva Cita Agendada (Rápida)', f"{pac_nombre} ha auto-agendado una consulta para el {fecha} a las {hora}.", fecha_notif, 'agenda'))
        
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
                title="Nueva Cita Auto-Agendada",
                body=f"{pac_nombre} ha reservado una consulta para el {fecha} a las {hora}.",
                url="/?view=agenda"
            )
        except Exception as wp_ex:
            print("Error al enviar WebPush de auto-agendamiento:", wp_ex)
        
        # Sincronización en Firebase
        import threading
        threading.Thread(target=sync_patient_to_firebase, args=(patient_id,)).start()
        
        return jsonify({
            'success': 'Tu consulta ha sido agendada con éxito automáticamente.',
            'google_synced': google_event_id is not None,
            'is_new_patient': is_new_patient,
            'psych_phone': psych.get('whatsapp_publico') or psych.get('telefono') if psych else None,
            'psych_name': f"Psic. {psych.get('nombres','')} {psych.get('apellidos','')}".strip() if psych else "el profesional",
            'first_time_message': 'Bienvenido/a. Como eres un consultante de primera vez, es importante que te comuniques vía WhatsApp con el profesional para recibir la información del encuadre terapeútico, métodos de pago y el enlace de la sesión.'
        })
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
            from routes_admin import get_calendar_service, update_calendar_event_status
            service = get_calendar_service(user_id, db=db)
            if service:
                try:
                    update_calendar_event_status(
                        service, google_event_id, 'cancelada',
                        motivo="Eliminada por el psicólogo desde panel"
                    )
                except Exception as ge:
                    print("Error al actualizar evento en Google Calendar:", ge)

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
        cita = dict(cita)
        estado_pago = str(cita.get('estado_pago') or '').strip()
        referencia = str(cita.get('referencia') or '').strip()
        is_cancelled = 'cancelad' in estado_pago.lower() or 'cancelad' in referencia.lower() or (cita.get('confirmada') == 0 and ('falta' in referencia.lower() or 'sistema' in referencia.lower()))

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
        log_dict = dict(log_c) if log_c else {}
        target_slug = log_dict.get('psicologo_slug') or 'psic.paulomora'
        clean_slug = target_slug if str(target_slug).startswith('psic.') else f"psic.{target_slug}"
        return jsonify({
            'error': 'Esta consulta ya ha sido cancelada. Por favor agenda una nueva cita o comunícate con tu especialista.',
            'cancelada': True,
            'fast_booking_url': f"https://www.espacioterapeutico.net/agendar/{clean_slug}"
        }), 400
        
    cita = dict(cita)
        
    appt_id = cita['id']
    psych_id = cita['psicologo_id'] or cita['creado_por_user_id'] or 1
    phone = cita['pat_telefono']
    
    target_slug = cita['psic_slug'] or cita['psic_username'] or 'psic.paulomora'
    clean_slug = target_slug if str(target_slug).startswith('psic.') else f"psic.{target_slug}"
    fast_booking_url = f"https://www.espacioterapeutico.net/agendar/{clean_slug}"
    
    estado_pago = str(cita['estado_pago'] or '').strip()
    referencia = str(cita['referencia'] or '').strip()
    is_cancelled = 'cancelad' in estado_pago.lower() or 'cancelad' in referencia.lower() or (cita.get('confirmada') == 0 and ('falta' in referencia.lower() or 'sistema' in referencia.lower()))

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
        'modalidad': cita['tipo_consulta'] or 'Presencial'
    }
    psicologo_data = {
        'nombres': cita['psic_nombres'],
        'apellidos': cita['psic_apellidos']
    }
    
    cursor.execute("SELECT clave, valor FROM configuracion WHERE clave IN ('msg_confirmacion_ok', 'msg_cancelacion_ok', 'msg_reagendamiento')")
    cfg_rows = {r['clave']: r['valor'] for r in cursor.fetchall()}
    
    template = ""
    
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    pat_full_name = f"{cita['pat_nombres']} {cita['pat_apellidos']}".strip()

    if accion == 'confirmar':
        cursor.execute("UPDATE agenda_finanzas SET confirmada = 1 WHERE id = ?", (appt_id,))
        template = cfg_rows.get('msg_confirmacion_ok') or "¡Excelente! ✅ Tu cita ha sido confirmada exitosamente. Nos vemos pronto."
        _update_google_calendar_status_bg(appt_id, 'confirmada')
        
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

        # 3. Notificación para el paciente en Firebase
        if cita['paciente_id']:
            try:
                from app import FIREBASE_DB_URL
                import requests
                fb_payload = {
                    "id": int(datetime.now().timestamp() * 1000),
                    "tipo": "cita",
                    "titulo": "✅ Cita Confirmada",
                    "mensaje": f"Has confirmado exitosamente tu consulta para el {cita['fecha']} a las {cita['hora']}.",
                    "fecha": now_str,
                    "leida": False
                }
                requests.post(f"{FIREBASE_DB_URL}/pacientes/{cita['paciente_id']}/notificaciones.json", json=fb_payload, timeout=2.0)
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
            except Exception as _e_clog:
                print("Error registrando citas_canceladas_log:", _e_clog)

            template = cfg_rows.get('msg_cancelacion_ok') or "Entendido, tu cita ha sido cancelada."

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

            return jsonify({
                'success': True,
                'late_charge': True,
                'titulo': 'Consulta Cancelada Fuera de Tiempo',
                'mensaje': 'Has cancelado la consulta fuera del tiempo límite permitido. De acuerdo con las normas de atención, esta sesión debe ser cancelada/abonada.',
                'fast_booking_url': fast_booking_url
            })

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

            template = cfg_rows.get('msg_cancelacion_ok') or "Entendido. Tu cita ha sido cancelada."

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

            return jsonify({
                'success': True,
                'late_charge': False,
                'titulo': 'Cita Cancelada',
                'mensaje': 'Has cancelado tu sesión exitosamente sin costo. El horario ha sido liberado.',
                'fast_booking_url': fast_booking_url
            })
        
    elif accion == 'reprogramar':
        cursor.execute("""
            UPDATE agenda_finanzas 
            SET estado_pago = 'Cancelada', confirmada = 0,
                referencia = CASE WHEN referencia IS NULL OR referencia = '' THEN 'Solicitud de reprogramación por consultante' ELSE referencia || ' | Solicitud de reprogramación por consultante' END
            WHERE id = ?
        """, (appt_id,))
        template = cfg_rows.get('msg_reagendamiento') or "Hemos recibido tu solicitud para reprogramar. Pronto nos pondremos en contacto contigo para agendar un nuevo espacio."
        _update_google_calendar_status_bg(appt_id, 'cancelada')
        
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

        # Notificar reprogramación al psicólogo
        try:
            cursor.execute("""
                INSERT INTO notificaciones (user_id, tipo, titulo, mensaje, fecha, leida, link)
                VALUES (?, 'cita', '🔄 Solicitud de Reprogramación', ?, ?, 0, 'agenda')
            """, (psych_id, f"{pat_full_name} solicitó reprogramar su cita del {cita['fecha']} a las {cita['hora']}.", now_str))
        except Exception as _ne:
            print("Error notificando reprogramacion publica:", _ne)

        db.commit()

        try:
            from app import send_webpush_notification
            send_webpush_notification(
                user_id=psych_id,
                title="🔄 Solicitud de Reprogramación",
                body=f"{pat_full_name} solicitó reprogramar su cita del {cita['fecha']} a las {cita['hora']}.",
                url="/?view=agenda"
            )
        except Exception as _wp_ex:
            print("Error enviando WebPush de reprogramacion publica:", _wp_ex)
        
    db.commit()
    
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
                try:
                    if accion == 'cancelar' or accion == 'reprogramar':
                        db_bg.execute("UPDATE agenda_finanzas SET cierre_enviado_wa = 1 WHERE id = ?", (appt_id,))
                    elif accion == 'confirmar':
                        try:
                            db_bg.execute("ALTER TABLE agenda_finanzas ADD COLUMN respuesta_enviada_wa INTEGER DEFAULT 0")
                        except Exception:
                            pass
                        db_bg.execute("UPDATE agenda_finanzas SET respuesta_enviada_wa = 1 WHERE id = ?", (appt_id,))
                    db_bg.commit()
                except Exception as _dbe:
                    print("Aviso actualizando flag en DB bg:", _dbe)
                finally:
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
    clean_cedula = cedula.strip()
    digits_cedula = re.sub(r'\D', '', clean_cedula)
    
    cursor.execute('''
        SELECT nombres, apellidos, telefono, email 
        FROM pacientes 
        WHERE (LOWER(REPLACE(REPLACE(REPLACE(REPLACE(cedula, 'V-', ''), 'E-', ''), '.', ''), ' ', '')) = ? AND ? != '') 
           OR (LOWER(REPLACE(REPLACE(REPLACE(cedula, '.', ''), '-', ''), ' ', '')) = LOWER(REPLACE(REPLACE(REPLACE(?, '.', ''), '-', ''), ' ', '')))
           OR (LOWER(username) = LOWER(?) AND username != '')
        LIMIT 1
    ''', (digits_cedula, digits_cedula, clean_cedula, clean_cedula.lower()))
    
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
