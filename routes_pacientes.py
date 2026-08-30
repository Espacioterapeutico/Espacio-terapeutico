# -*- coding: utf-8 -*-
"""
Módulo de Gestión de Expedientes de Pacientes (routes_pacientes.py)
Encapsula la creación, consulta, actualización y eliminación de expedientes clínicos de consultantes,
búsqueda dinámica por cédula e integración con Firebase Realtime DB.
"""

import os
import re
import sqlite3
import json
from datetime import datetime
from functools import wraps
from flask import Blueprint, request, jsonify, session, g
from werkzeug.security import generate_password_hash, check_password_hash

from routes_finanzas import auto_settle_patient_debts
from routes_agenda import generate_dynamic_slots

pacientes_bp = Blueprint('pacientes', __name__)

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

def get_deadline_datetime(fecha_str, hora_str, rule_type, rule_value):
    """Calcula la fecha y hora límite para cancelar/reprogramar una cita según la regla del psicólogo."""
    from datetime import datetime, timedelta
    try:
        f_norm = normalize_date_str(fecha_str)
        h_norm = normalize_time_str(hora_str)
        cita_dt = datetime.strptime(f"{f_norm} {h_norm}", "%Y-%m-%d %H:%M")
    except Exception:
        return datetime.now() + timedelta(days=365)

    rule_val = float(rule_value or 24)
    if rule_type == 'dias':
        return cita_dt - timedelta(days=rule_val)
    else:
        return cita_dt - timedelta(hours=rule_val)

def get_rule_description(rule_type, rule_value):
    rule_val = int(float(rule_value or 24))
    if rule_type == 'dias':
        return f"{rule_val} día(s) antes de la cita"
    return f"{rule_val} hora(s) antes de la cita"

def create_auto_cancellation_session(db, patient_id, appt_id, fecha, modalidad, estado, motivo):
    """Registra o actualiza el estado de sesión cancelada en la tabla sesiones."""
    try:
        cursor = db.cursor()
        cursor.execute("SELECT id FROM sesiones WHERE paciente_id = ? AND fecha = ?", (patient_id, fecha))
        s_row = cursor.fetchone()
        if s_row:
            cursor.execute("UPDATE sesiones SET estado = ?, resumen_paciente = ? WHERE id = ?", (estado, motivo, s_row['id']))
        else:
            cursor.execute("""
                INSERT INTO sesiones (paciente_id, fecha, modalidad, estado, resumen_paciente)
                VALUES (?, ?, ?, ?, ?)
            """, (patient_id, fecha, modalidad, estado, motivo))
        db.commit()
    except Exception as ex:
        print("Error en create_auto_cancellation_session:", ex)

def clean_digits_only(s):
    if not s:
        return ""
    return re.sub(r'\D', '', str(s))

def decrypt_clinical_text(txt):
    if not txt:
        return ""
    return str(txt)

def delete_patient_from_firebase(patient_id):
    try:
        from app import delete_patient_from_firebase as _dpf
        return _dpf(patient_id)
    except Exception as ex:
        print("Error borrando paciente de Firebase:", ex)

def get_db():
    """Obtiene la conexión a la base de datos desde el contexto global g de Flask."""
    db = getattr(g, '_database', None)
    if db is None:
        import sys
        if getattr(sys, 'frozen', False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))
        db_path = os.path.join(base_dir, 'clinica.db')
        db = g._database = sqlite3.connect(db_path, timeout=30.0)
        db.row_factory = sqlite3.Row
        
        try:
            db.execute("ALTER TABLE pacientes ADD COLUMN estado TEXT DEFAULT 'Activo'")
            db.commit()
        except:
            pass
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
        pid = session.get('patient_id') or request.args.get('patient_id')
        if not pid and 'user_id' in session:
            pid = session.get('last_viewed_patient_id')
        if not pid:
            return jsonify({'error': 'Sesión expirada o no iniciada.'}), 401
        session['patient_id'] = int(pid)
        return f(*args, **kwargs)
    return decorated_function

def get_psicologo_id_filter():
    role = session.get('role')
    user_id = session.get('user_id')
    username = session.get('username', '')
    if (role in ['admin', 'superadmin']) and (username.lower() != 'pamoraro' and user_id != 1):
        return -1
    return user_id if user_id else 1

# --- RUTAS DE API DE PACIENTES Y EXPEDIENTES ---

@pacientes_bp.route('/api/pacientes/buscar_cedula/<cedula>', methods=['GET'])
@login_required
def buscar_paciente_por_cedula(cedula):
    cedula_clean = cedula.strip()
    if not cedula_clean:
        return jsonify({'found': False}), 404
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT nombres, apellidos, cedula, pronombre, genero, edad, lugar_nacimiento, fecha_nacimiento,
               residencia_actual, con_quien_reside, nivel_academico, ocupacion, estado_civil, telefono, email, pais, ciudad
        FROM pacientes
        WHERE cedula = ?
        ORDER BY id DESC LIMIT 1
    """, (cedula_clean,))
    row = cursor.fetchone()
    if not row:
        return jsonify({'found': False}), 404
    return jsonify({
        'found': True,
        'paciente': dict(row)
    })

@pacientes_bp.route('/api/patients', methods=['GET'])
@login_required
def get_patients():
    search = request.args.get('search', '').strip()
    db = get_db()
    cursor = db.cursor()
    
    role = session.get('role', '')
    user_id = session.get('user_id')
    psic_id = get_psicologo_id_filter()
    
    if psic_id == -1 or psic_id is None:
        if role in ['admin', 'superadmin']:
            psic_id = None
        else:
            psic_id = user_id if user_id else 1
    
    if search:
        query = "%" + search + "%"
        if psic_id is not None:
            cursor.execute("""
                SELECT p.id, p.nombres, p.apellidos, p.cedula, p.edad, p.genero, p.residencia_actual, p.pais, p.ciudad, p.organizacion_id, p.estado, o.nombre as organizacion_nombre 
                FROM pacientes p
                LEFT JOIN organizaciones o ON p.organizacion_id = o.id
                WHERE (p.psicologo_id = ? OR p.psicologo_id IS NULL) AND (p.nombres LIKE ? OR p.apellidos LIKE ? OR p.cedula LIKE ?)
                ORDER BY p.nombres ASC, p.apellidos ASC
            """, (psic_id, query, query, query))
        else:
            cursor.execute("""
                SELECT p.id, p.nombres, p.apellidos, p.cedula, p.edad, p.genero, p.residencia_actual, p.pais, p.ciudad, p.organizacion_id, p.estado, o.nombre as organizacion_nombre 
                FROM pacientes p
                LEFT JOIN organizaciones o ON p.organizacion_id = o.id
                WHERE p.nombres LIKE ? OR p.apellidos LIKE ? OR p.cedula LIKE ?
                ORDER BY p.nombres ASC, p.apellidos ASC
            """, (query, query, query))
    else:
        if psic_id is not None:
            cursor.execute("""
                SELECT p.id, p.nombres, p.apellidos, p.cedula, p.edad, p.genero, p.residencia_actual, p.pais, p.ciudad, p.organizacion_id, p.estado, o.nombre as organizacion_nombre 
                FROM pacientes p
                LEFT JOIN organizaciones o ON p.organizacion_id = o.id
                WHERE (p.psicologo_id = ? OR p.psicologo_id IS NULL) 
                ORDER BY p.nombres ASC, p.apellidos ASC
            """, (psic_id,))
        else:
            cursor.execute("""
                SELECT p.id, p.nombres, p.apellidos, p.cedula, p.edad, p.genero, p.residencia_actual, p.pais, p.ciudad, p.organizacion_id, p.estado, o.nombre as organizacion_nombre 
                FROM pacientes p
                LEFT JOIN organizaciones o ON p.organizacion_id = o.id
                ORDER BY p.nombres ASC, p.apellidos ASC
            """)
        
    patients = [dict(row) for row in cursor.fetchall()]
    return jsonify(patients)

@pacientes_bp.route('/api/patients/<int:patient_id>', methods=['GET'])
@login_required
def get_patient(patient_id):
    db = get_db()
    cursor = db.cursor()
    psic_id = get_psicologo_id_filter()
    if psic_id is not None:
        cursor.execute("""
            SELECT p.*, o.nombre as organizacion_nombre
            FROM pacientes p
            LEFT JOIN organizaciones o ON p.organizacion_id = o.id
            WHERE p.id = ? AND p.psicologo_id = ?
        """, (patient_id, psic_id))
    else:
        cursor.execute("""
            SELECT p.*, o.nombre as organizacion_nombre
            FROM pacientes p
            LEFT JOIN organizaciones o ON p.organizacion_id = o.id
            WHERE p.id = ?
        """, (patient_id,))
    row = cursor.fetchone()
    if row is None:
        return jsonify({'error': 'Paciente no encontrado.'}), 404
    p_dict = dict(row)
    from app import decrypt_clinical_text
    for k in ['diagnostico', 'antecedentes_medicos_personales', 'antecedentes_psicologicos_personales', 'historia_clinica']:
        if k in p_dict and p_dict[k]:
            p_dict[k] = decrypt_clinical_text(p_dict[k])
    return jsonify(p_dict)

@pacientes_bp.route('/api/patients', methods=['POST'])
@login_required
def create_patient():
    data = request.json or {}
    db = get_db()
    cursor = db.cursor()
    
    nombres = data.get('nombres')
    apellidos = data.get('apellidos')
    cedula = data.get('cedula', '').strip()
    if not cedula:
        cedula = None
    estado = data.get('estado', 'Activo')
    if not nombres or not apellidos:
        return jsonify({'error': 'Nombres y Apellidos son campos obligatorios.'}), 400
        
    psic_id = session.get('user_id', 1)
    if cedula:
        cursor.execute("SELECT id FROM pacientes WHERE cedula = ? AND psicologo_id = ?", (cedula, psic_id))
        if cursor.fetchone() is not None:
            return jsonify({'error': f'Ya tienes un paciente registrado con la cédula {cedula}.'}), 400

    costo_personalizado = data.get('costo_personalizado')
    if costo_personalizado == '' or costo_personalizado is None:
        costo_personalizado = None
    else:
        try: costo_personalizado = float(costo_personalizado)
        except: costo_personalizado = None
    moneda_personalizada = data.get('moneda_personalizada', 'USD') or 'USD'
        
    costo_paquete_personalizado = data.get('costo_paquete_personalizado')
    if costo_paquete_personalizado == '' or costo_paquete_personalizado is None:
        costo_paquete_personalizado = None
    else:
        try: costo_paquete_personalizado = float(costo_paquete_personalizado)
        except: costo_paquete_personalizado = None

    sesiones_paquete_personalizado = data.get('sesiones_paquete_personalizado')
    if sesiones_paquete_personalizado == '' or sesiones_paquete_personalizado is None:
        sesiones_paquete_personalizado = None
    else:
        try: sesiones_paquete_personalizado = int(sesiones_paquete_personalizado)
        except: sesiones_paquete_personalizado = None

    raw_org = data.get('organizacion_id')
    org_id_val = None
    if raw_org is not None and str(raw_org).strip().lower() not in ['null', '0', 'none', '']:
        try: org_id_val = int(raw_org)
        except: org_id_val = None

    try:
        import time
        if cedula:
            base_username = cedula
            cursor.execute("SELECT id FROM pacientes WHERE username = ?", (base_username,))
            if cursor.fetchone() is not None:
                base_username = f"{cedula}_{psic_id}"
            username = base_username
            password_hash = generate_password_hash(cedula)
        else:
            username = f"user_{int(time.time())}_{psic_id}"
            password_hash = ""
        
        cursor.execute("""
            INSERT INTO pacientes (
                nombres, apellidos, cedula, pronombre, genero, edad, lugar_nacimiento, fecha_nacimiento,
                residencia_actual, pais, ciudad, con_quien_reside, nivel_academico, ocupacion, estado_civil,
                telefono, email,
                antecedentes_medicos_familiares, antecedentes_medicos_personales,
                antecedentes_psicologicos_familiares, antecedentes_psicologicos_personales,
                asistencia_previa_psicologo, motivo_consulta, expectativas, farmacologia,
                contacto_emergencia_nombre, contacto_emergencia_parentesco, diagnostico,
                username, password_hash, psicologo_id, costo_personalizado, moneda_personalizada,
                costo_paquete_personalizado, sesiones_paquete_personalizado, organizacion_id, estado
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            nombres, apellidos, cedula, data.get('pronombre'), data.get('genero'), data.get('edad'),
            data.get('lugar_nacimiento'), data.get('fecha_nacimiento'), data.get('residencia_actual'),
            data.get('pais'), data.get('ciudad'),
            data.get('con_quien_reside'), data.get('nivel_academico'), data.get('ocupacion'), data.get('estado_civil'),
            data.get('telefono'), data.get('email'),
            data.get('antecedentes_medicos_familiares'), data.get('antecedentes_medicos_personales'),
            data.get('antecedentes_psicologicos_familiares'), data.get('antecedentes_psicologicos_personales'),
            data.get('asistencia_previa_psicologo'), data.get('motivo_consulta'), data.get('expectativas'),
            data.get('farmacologia'), data.get('contacto_emergencia_nombre'), data.get('contacto_emergencia_parentesco'),
            data.get('diagnostico'), username, password_hash, session.get('user_id'), costo_personalizado, moneda_personalizada,
            costo_paquete_personalizado, sesiones_paquete_personalizado, org_id_val, estado
        ))
        db.commit()
        patient_id = cursor.lastrowid
        
        try:
            from app import sync_patient_to_firebase
            import threading
            threading.Thread(target=sync_patient_to_firebase, args=(patient_id,)).start()
        except Exception: pass
        
        return jsonify({'success': 'Paciente registrado con éxito.', 'id': patient_id})
    except Exception as e:
        return jsonify({'error': f'Error al registrar paciente: {str(e)}'}), 500

@pacientes_bp.route('/api/patients/<int:patient_id>', methods=['PUT'])
@login_required
def update_patient(patient_id):
    data = request.json or {}
    db = get_db()
    cursor = db.cursor()
    
    nombres = data.get('nombres')
    apellidos = data.get('apellidos')
    cedula = data.get('cedula', '').strip()
    if not cedula:
        cedula = None
    estado = data.get('estado', 'Activo')
    if not nombres or not apellidos:
        return jsonify({'error': 'Nombres y Apellidos son obligatorios.'}), 400
        
    psic_id = session.get('user_id', 1)
    if cedula:
        cursor.execute("SELECT id FROM pacientes WHERE cedula = ? AND psicologo_id = ? AND id != ?", (cedula, psic_id, patient_id))
        if cursor.fetchone() is not None:
            return jsonify({'error': f'Ya tienes otro paciente registrado con la cédula {cedula}.'}), 400
        
    costo_personalizado = data.get('costo_personalizado')
    if costo_personalizado == '' or costo_personalizado is None:
        costo_personalizado = None
    else:
        try: costo_personalizado = float(costo_personalizado)
        except: costo_personalizado = None
    moneda_personalizada = data.get('moneda_personalizada', 'USD') or 'USD'

    costo_paquete_personalizado = data.get('costo_paquete_personalizado')
    if costo_paquete_personalizado == '' or costo_paquete_personalizado is None:
        costo_paquete_personalizado = None
    else:
        try: costo_paquete_personalizado = float(costo_paquete_personalizado)
        except: costo_paquete_personalizado = None

    sesiones_paquete_personalizado = data.get('sesiones_paquete_personalizado')
    if sesiones_paquete_personalizado == '' or sesiones_paquete_personalizado is None:
        sesiones_paquete_personalizado = None
    else:
        try: sesiones_paquete_personalizado = int(sesiones_paquete_personalizado)
        except: sesiones_paquete_personalizado = None

    raw_org = data.get('organizacion_id')
    org_id_val = None
    if raw_org is not None and str(raw_org).strip().lower() not in ['null', '0', 'none', '']:
        try: org_id_val = int(raw_org)
        except: org_id_val = None

    try:
        cursor.execute("""
            UPDATE pacientes SET 
                nombres = ?, apellidos = ?, cedula = ?, pronombre = ?, genero = ?, edad = ?,
                lugar_nacimiento = ?, fecha_nacimiento = ?, residencia_actual = ?, pais = ?, ciudad = ?,
                con_quien_reside = ?, nivel_academico = ?, ocupacion = ?, estado_civil = ?,
                telefono = ?, email = ?,
                antecedentes_medicos_familiares = ?, antecedentes_medicos_personales = ?,
                antecedentes_psicologicos_familiares = ?, antecedentes_psicologicos_personales = ?,
                asistencia_previa_psicologo = ?, motivo_consulta = ?, expectativas = ?, farmacologia = ?,
                contacto_emergencia_nombre = ?, contacto_emergencia_parentesco = ?, diagnostico = ?,
                costo_personalizado = ?, moneda_personalizada = ?,
                costo_paquete_personalizado = ?, sesiones_paquete_personalizado = ?,
                organizacion_id = ?, estado = ?
            WHERE id = ?
        """, (
            nombres, apellidos, cedula, data.get('pronombre'), data.get('genero'), data.get('edad'),
            data.get('lugar_nacimiento'), data.get('fecha_nacimiento'), data.get('residencia_actual'),
            data.get('pais'), data.get('ciudad'),
            data.get('con_quien_reside'), data.get('nivel_academico'), data.get('ocupacion'), data.get('estado_civil'),
            data.get('telefono'), data.get('email'),
            data.get('antecedentes_medicos_familiares'), data.get('antecedentes_medicos_personales'),
            data.get('antecedentes_psicologicos_familiares'), data.get('antecedentes_psicologicos_personales'),
            data.get('asistencia_previa_psicologo'), data.get('motivo_consulta'), data.get('expectativas'),
            data.get('farmacologia'), data.get('contacto_emergencia_nombre'), data.get('contacto_emergencia_parentesco'),
            data.get('diagnostico'), costo_personalizado, moneda_personalizada,
            costo_paquete_personalizado, sesiones_paquete_personalizado, org_id_val, estado, patient_id
        ))
        db.commit()
        
        try:
            from app import sync_patient_to_firebase
            import threading
            threading.Thread(target=sync_patient_to_firebase, args=(patient_id,)).start()
        except Exception: pass
        
        return jsonify({'success': 'Expediente actualizado con éxito.'})
    except Exception as e:
        return jsonify({'error': f'Error al actualizar expediente: {str(e)}'}), 500

@pacientes_bp.route('/api/patients/<int:patient_id>/toggle-estado', methods=['POST'])
@login_required
def toggle_estado(patient_id):
    db = get_db()
    cursor = db.cursor()
    psic_id = session.get('user_id', 1)
    
    cursor.execute("SELECT estado FROM pacientes WHERE id = ? AND (psicologo_id = ? OR psicologo_id IS NULL)", (patient_id, psic_id))
    row = cursor.fetchone()
    if not row:
        return jsonify({'error': 'Paciente no encontrado'}), 404
        
    current_estado = dict(row).get('estado') or 'Activo'
    new_estado = 'De Alta' if current_estado == 'Activo' else 'Activo'
    
    try:
        cursor.execute("UPDATE pacientes SET estado = ? WHERE id = ?", (new_estado, patient_id))
        db.commit()
        return jsonify({'success': True, 'new_estado': new_estado})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@pacientes_bp.route('/api/patients/<int:patient_id>/reset-credentials', methods=['POST'])
@login_required
def reset_patient_credentials(patient_id):
    db = get_db()
    cursor = db.cursor()
    psic_id = get_psicologo_id_filter()
    
    cursor.execute("SELECT cedula, psicologo_id FROM pacientes WHERE id = ?", (patient_id,))
    pac_info = cursor.fetchone()
    if not pac_info:
        return jsonify({'error': 'Paciente no encontrado.'}), 404
        
    if psic_id is not None and pac_info['psicologo_id'] != psic_id:
        return jsonify({'error': 'No tienes permisos para modificar a este paciente.'}), 403

    cedula = pac_info['cedula']
    if not cedula:
        return jsonify({'error': 'El paciente no tiene cédula registrada.'}), 400

    new_hash = generate_password_hash(cedula)
    
    try:
        cursor.execute("""
            UPDATE pacientes 
            SET username = ?, 
                password_hash = ?, 
                pregunta_seguridad_1 = NULL, 
                pregunta_seguridad_2 = NULL, 
                respuesta_seguridad_1_hash = NULL, 
                respuesta_seguridad_2_hash = NULL 
            WHERE id = ?
        """, (cedula, new_hash, patient_id))
        db.commit()
        
        try:
            import threading
            from app import sync_patient_to_firebase
            threading.Thread(target=sync_patient_to_firebase, args=(patient_id,)).start()
        except Exception:
            pass
            
        return jsonify({'success': 'Credenciales restablecidas correctamente.'})
    except Exception as e:
        return jsonify({'error': f'Error al restablecer credenciales: {str(e)}'}), 500

@pacientes_bp.route('/api/patients/<int:patient_id>', methods=['DELETE'])
@login_required
def delete_patient(patient_id):
    db = get_db()
    cursor = db.cursor()
    psic_id = get_psicologo_id_filter()
    
    cursor.execute("SELECT username, cedula, psicologo_id FROM pacientes WHERE id = ?", (patient_id,))
    pac_info = cursor.fetchone()
    if not pac_info:
        return jsonify({'error': 'Paciente no encontrado.'}), 404
        
    if psic_id is not None and pac_info['psicologo_id'] != psic_id:
        return jsonify({'error': 'No tienes permisos para eliminar este paciente.'}), 403
        
    username_key = (pac_info['username'] or pac_info['cedula'] or '').strip()
    
    try:
        cursor.execute("DELETE FROM agenda_finanzas WHERE paciente_id = ?", (patient_id,))
        cursor.execute("DELETE FROM sesiones WHERE paciente_id = ?", (patient_id,))
        cursor.execute("DELETE FROM pizarra_terapeutica WHERE paciente_id = ?", (patient_id,))
        cursor.execute("DELETE FROM pagos_notificados WHERE paciente_id = ?", (patient_id,))
        cursor.execute("DELETE FROM pacientes WHERE id = ?", (patient_id,))
        db.commit()
        
        try:
            from app import delete_patient_from_firebase
            delete_patient_from_firebase(patient_id, username_key)
        except Exception: pass
        
        return jsonify({'success': 'Paciente y todos sus registros clínicos/financieros fueron eliminados con éxito.'})
    except Exception as e:
        return jsonify({'error': f'Error al eliminar paciente: {str(e)}'}), 500


# --- RUTAS MIGRADAS AUTOMÁTICAMENTE DE AUDITORÍA ---

@pacientes_bp.route('/api/patient/update-timezone', methods=['POST'])
@patient_login_required
def update_patient_timezone():
    data = request.json or {}
    tz_name = data.get('timezone', 'America/Caracas').strip()
    offset_min = data.get('utc_offset', 240)
    try:
        offset_min = int(offset_min)
    except Exception:
        offset_min = 240

    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        UPDATE pacientes SET zona_horaria = ?, utc_offset = ? WHERE id = ?
    """, (tz_name, offset_min, session['patient_id']))
    db.commit()
    return jsonify({'success': 'Zona horaria de paciente actualizada.'})

# Endpoints de autenticación y seguridad de pacientes (PWA)


@pacientes_bp.route('/api/patient/login', methods=['POST'])
def patient_login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({'error': 'Usuario y contraseña son requeridos.'}), 400
        
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM pacientes WHERE LOWER(username) = ?", (username.lower(),))
    patient = cursor.fetchone()
    
    if not patient:
        cursor.execute("SELECT * FROM pacientes WHERE cedula = ?", (username,))
        patient = cursor.fetchone()
        
    if not patient:
        digits_user = clean_digits_only(username)
        if digits_user:
            cursor.execute("""
                SELECT * FROM pacientes 
                WHERE REPLACE(REPLACE(REPLACE(REPLACE(cedula, 'V-', ''), 'E-', ''), '.', ''), ' ', '') = ?
            """, (digits_user,))
            patient = cursor.fetchone()
        
    if not patient:
        return jsonify({'error': 'Usuario no registrado.'}), 401
        
    is_default = False
    if not patient['password_hash']:
        pwd_lower = (password or '').strip().lower()
        ced_lower = (patient['cedula'] or '').strip().lower()
        usr_lower = (patient['username'] or '').strip().lower()
        clean_pwd = clean_digits_only(password)
        clean_ced = clean_digits_only(patient['cedula'])
        clean_usr = clean_digits_only(patient['username'])
        
        is_default = (
            pwd_lower == ced_lower or 
            pwd_lower == usr_lower or 
            (clean_pwd != '' and clean_pwd == clean_ced) or 
            (clean_pwd != '' and clean_pwd == clean_usr)
        )
    else:
        is_default = check_password_hash(patient['password_hash'], password)
        
    if not is_default:
        return jsonify({'error': 'Contraseña incorrecta.'}), 401
        
    needs_setup = (patient['pregunta_seguridad_1'] is None or patient['respuesta_seguridad_1_hash'] is None)
    
    session.permanent = True
    session['patient_id'] = patient['id']
    session['patient_username'] = patient['username'] or patient['cedula']
    session['role'] = 'paciente'
    
    if needs_setup:
        return jsonify({
            'success': 'Primer acceso detectado. Requiere configuración.',
            'first_login': True,
            'patient_id': patient['id'],
            'username': patient['username'] or patient['cedula'],
            'patient_data': {
                'nombres': patient['nombres'] or '',
                'apellidos': patient['apellidos'] or '',
                'cedula': patient['cedula'] or '',
                'fecha_nacimiento': patient['fecha_nacimiento'] or '',
                'pais': patient['pais'] or '',
                'ciudad': patient['ciudad'] or '',
                'telefono': patient['telefono'] or '',
                'email': patient['email'] or ''
            }
        })
    
    return jsonify({
        'success': 'Inicio de sesión correcto.',
        'role': 'paciente',
        'patient_id': patient['id'],
        'nombres': patient['nombres'],
        'apellidos': patient['apellidos']
    })



@pacientes_bp.route('/api/patient/setup-first-login', methods=['POST'])
def patient_setup_first_login():
    data = request.json
    patient_id = data.get('patient_id')
    username = data.get('username')
    new_password = data.get('new_password')
    pregunta_1 = data.get('pregunta_1')
    respuesta_1 = data.get('respuesta_1')
    pregunta_2 = data.get('pregunta_2')
    respuesta_2 = data.get('respuesta_2')
    
    if not patient_id or not username or not new_password or not pregunta_1 or not respuesta_1 or not pregunta_2 or not respuesta_2:
        return jsonify({'error': 'Todos los campos son obligatorios.'}), 400
        
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute("SELECT id FROM pacientes WHERE LOWER(username) = ? AND id != ?", (username.lower(), patient_id))
    if cursor.fetchone() is not None:
        return jsonify({'error': 'El nombre de usuario ya está en uso por otro paciente.'}), 400
        
    password_hash = generate_password_hash(new_password)
    resp_1_hash = generate_password_hash(respuesta_1.strip().lower())
    resp_2_hash = generate_password_hash(respuesta_2.strip().lower())
    
    cursor.execute("SELECT * FROM pacientes WHERE id = ?", (patient_id,))
    curr_pac = cursor.fetchone()
    curr = dict(curr_pac) if curr_pac else {}

    def get_val(key):
        val = data.get(key)
        if val is not None and str(val).strip() != '':
            return val
        return curr.get(key)

    try:
        cursor.execute("""
            UPDATE pacientes 
            SET username = ?, password_hash = ?, 
                pregunta_seguridad_1 = ?, respuesta_seguridad_1_hash = ?,
                pregunta_seguridad_2 = ?, respuesta_seguridad_2_hash = ?,
                pronombre = ?, genero = ?, edad = ?, lugar_nacimiento = ?, fecha_nacimiento = ?, 
                residencia_actual = ?, pais = ?, ciudad = ?, con_quien_reside = ?, nivel_academico = ?, ocupacion = ?, estado_civil = ?,
                telefono = ?, email = ?,
                antecedentes_medicos_familiares = ?, antecedentes_medicos_personales = ?,
                antecedentes_psicologicos_familiares = ?, antecedentes_psicologicos_personales = ?,
                asistencia_previa_psicologo = ?, motivo_consulta = ?, expectativas = ?, farmacologia = ?,
                contacto_emergencia_nombre = ?, contacto_emergencia_parentesco = ?
            WHERE id = ?
        """, (
            username, password_hash, pregunta_1, resp_1_hash, pregunta_2, resp_2_hash,
            get_val('pronombre'), get_val('genero'), get_val('edad'), get_val('lugar_nacimiento'), get_val('fecha_nacimiento'),
            get_val('residencia_actual'), get_val('pais'), get_val('ciudad'), get_val('con_quien_reside'), get_val('nivel_academico'), get_val('ocupacion'), get_val('estado_civil'),
            get_val('telefono'), get_val('email'),
            get_val('antecedentes_medicos_familiares'), get_val('antecedentes_medicos_personales'),
            get_val('antecedentes_psicologicos_familiares'), get_val('antecedentes_psicologicos_personales'),
            get_val('asistencia_previa_psicologo'), get_val('motivo_consulta'), get_val('expectativas'), get_val('farmacologia'),
            get_val('contacto_emergencia_nombre'), get_val('contacto_emergencia_parentesco'),
            patient_id
        ))
        db.commit()
        
        session['patient_id'] = patient_id
        session['patient_username'] = username
        session['role'] = 'paciente'
        
        try:
            sync_patient_to_firebase(patient_id)
        except Exception as _sync_err:
            print(f"Error en sync_patient_to_firebase: {_sync_err}")
        
        return jsonify({'success': 'Perfil e historia clínica configurados con éxito. Sesión iniciada.'})
    except Exception as e:
        return jsonify({'error': f'Error al configurar perfil: {str(e)}'}), 500



@pacientes_bp.route('/api/patient/change-password', methods=['POST'])
@patient_login_required
def patient_change_password():
    data = request.json or {}
    current_password = data.get('current_password')
    new_password = data.get('new_password')
    confirm_password = data.get('confirm_password')
    
    if not current_password or not new_password:
        return jsonify({'error': 'Ambas contraseñas son obligatorias.'}), 400

    if confirm_password and new_password != confirm_password:
        return jsonify({'error': 'La nueva contraseña y su confirmación no coinciden.'}), 400

    if len(new_password) < 6:
        return jsonify({'error': 'La nueva contraseña debe tener al menos 6 caracteres.'}), 400
        
    patient_id = session['patient_id']
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT password_hash FROM pacientes WHERE id = ?", (patient_id,))
    patient = cursor.fetchone()
    
    if not patient or not check_password_hash(patient['password_hash'], current_password):
        return jsonify({'error': 'La contraseña actual es incorrecta.'}), 401
        
    password_hash = generate_password_hash(new_password)
    try:
        cursor.execute("UPDATE pacientes SET password_hash = ? WHERE id = ?", (password_hash, patient_id))
        db.commit()
        
        import threading
        threading.Thread(target=sync_patient_to_firebase, args=(patient_id,)).start()
        
        return jsonify({'success': 'Contraseña actualizada con éxito.'})
    except Exception as e:
        db.rollback()
        return jsonify({'error': f'Error al actualizar contraseña: {str(e)}'}), 500



@pacientes_bp.route('/api/patient/appointments', methods=['GET'])
@patient_login_required
def patient_appointments():
    patient_id = session['patient_id']
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT af.id, af.fecha, af.hora, af.tipo_consulta, af.estado_pago, af.referencia,
               (CASE WHEN s.id IS NOT NULL THEN 1 ELSE 0 END) as evolucionada
        FROM agenda_finanzas af
        LEFT JOIN sesiones s ON af.id = s.agenda_id
        WHERE af.paciente_id = ?
        ORDER BY af.fecha DESC, af.hora DESC
    """, (patient_id,))
    rows = cursor.fetchall()
    return jsonify([dict(r) for r in rows])



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

@pacientes_bp.route('/api/patient/available-dates', methods=['GET'])
def get_available_dates():
    year = request.args.get('year')
    month = request.args.get('month')
    modalidad = request.args.get('modalidad', 'all')
    exclude_appt_id = request.args.get('exclude_appt_id')
    
    if not year or not month:
        return jsonify({'error': 'Año y mes son requeridos.'}), 400
        
    try:
        import calendar as pycalendar
        year = int(year)
        month = int(month)
        
        db = get_db()
        cursor = db.cursor()
        
        psic_param = request.args.get('psicologo_id')
        psicologo_id = None
        if psic_param:
            psych = get_psychologist_by_id_or_slug(cursor, psic_param)
            if psych:
                psicologo_id = psych['id']
        if not psicologo_id and 'patient_id' in session:
            cursor.execute("SELECT psicologo_id FROM pacientes WHERE id = ?", (session['patient_id'],))
            p_row = cursor.fetchone()
            if p_row:
                psicologo_id = p_row['psicologo_id']
        if not psicologo_id and 'user_id' in session:
            psicologo_id = session['user_id']
        if not psicologo_id:
            cursor.execute("SELECT id FROM usuarios WHERE role = 'psicologo' ORDER BY id ASC LIMIT 1")
            first_u = cursor.fetchone()
            if first_u:
                psicologo_id = first_u[0]
            else:
                psicologo_id = 1

        num_days = pycalendar.monthrange(year, month)[1]
        available_dates = []

        for day in range(1, num_days + 1):
            date_str = f"{year}-{month:02d}-{day:02d}"
            slots = generate_dynamic_slots(cursor, psicologo_id, date_str, modalidad, exclude_appt_id)
            if len(slots) > 0:
                available_dates.append(date_str)
                
        return jsonify({'dates': available_dates})
    except Exception as e:
        return jsonify({'error': f'Error al obtener fechas disponibles: {str(e)}'}), 500




@pacientes_bp.route('/api/patient/available-slots', methods=['GET'])
def get_available_slots():
    date_str = request.args.get('date')
    modalidad = request.args.get('modalidad', 'all')
    exclude_appt_id = request.args.get('exclude_appt_id')
    
    if not date_str:
        return jsonify({'error': 'Fecha es requerida.'}), 400
        
    try:
        db = get_db()
        cursor = db.cursor()
        
        psic_param = request.args.get('psicologo_id')
        psicologo_id = None
        if psic_param:
            psych = get_psychologist_by_id_or_slug(cursor, psic_param)
            if psych:
                psicologo_id = psych['id']
        if not psicologo_id and 'patient_id' in session:
            cursor.execute("SELECT psicologo_id FROM pacientes WHERE id = ?", (session['patient_id'],))
            p_row = cursor.fetchone()
            if p_row:
                psicologo_id = p_row['psicologo_id']
        if not psicologo_id and 'user_id' in session:
            psicologo_id = session['user_id']
        if not psicologo_id:
            cursor.execute("SELECT id FROM usuarios WHERE role = 'psicologo' ORDER BY id ASC LIMIT 1")
            first_u = cursor.fetchone()
            if first_u:
                psicologo_id = first_u[0]
            else:
                psicologo_id = 1

        slots = generate_dynamic_slots(cursor, psicologo_id, date_str, modalidad, exclude_appt_id)
        return jsonify({'slots': slots})
    except Exception as e:
        return jsonify({'error': f'Error al obtener disponibilidad: {str(e)}'}), 500



@pacientes_bp.route('/api/patient/appointment', methods=['POST'])
@patient_login_required
def patient_add_appointment():
    data = request.json
    db = get_db()
    cursor = db.cursor()
    
    patient_id = session['patient_id']
    fecha = data.get('fecha')
    hora = data.get('hora')
    tipo_consulta = data.get('modalidad') # 'Presencial', 'Online'
    nota = data.get('nota', '').strip()
    
    if not fecha or not hora or not tipo_consulta:
        return jsonify({'error': 'Fecha, Hora y Modalidad son obligatorios.'}), 400
        
    try:
        fecha_norm = normalize_date_str(fecha)
        hora_norm = normalize_time_str(hora)
        alt_fecha = fecha_norm
        try:
            dt_tmp = datetime.strptime(fecha_norm, "%Y-%m-%d")
            alt_fecha = dt_tmp.strftime("%d/%m/%Y")
        except:
            pass

        cursor.execute("SELECT nombres, apellidos, cedula, email, psicologo_id FROM pacientes WHERE id = ?", (patient_id,))
        paciente = cursor.fetchone()
        psicologo_id = paciente['psicologo_id'] if paciente else 1

        # Verificar si el horario ya está reservado por otro consultante
        cursor.execute("""
            SELECT af.id FROM agenda_finanzas af
            LEFT JOIN pacientes p ON af.paciente_id = p.id
            WHERE (af.fecha = ? OR af.fecha = ?) 
              AND (af.hora = ? OR af.hora LIKE ?)
              AND (p.psicologo_id = ? OR p.psicologo_id IS NULL OR ? IS NULL)
              AND (af.estado_pago IS NULL OR (af.estado_pago NOT LIKE 'Cancelada%' AND af.estado_pago != 'Reprogramada'))
        """, (fecha_norm, alt_fecha, hora_norm, f"{hora_norm}%", psicologo_id, psicologo_id))
        if cursor.fetchone():
            return jsonify({'error': 'El horario seleccionado ya ha sido reservado. Por favor elige otro horario.'}), 400

        google_event_id = None
        service = None
        try:
            from routes_admin import get_calendar_service
            service = get_calendar_service(psicologo_id)
        except Exception:
            service = None
        
        if service:
            start_datetime = f"{fecha_norm}T{hora_norm}:00-04:00"
            end_hour = str(int(hora_norm.split(':')[0]) + 1).zfill(2)
            end_datetime = f"{fecha_norm}T{end_hour}:{hora_norm.split(':')[1]}:00-04:00"
            
            event_body = {
                'summary': f"Consulta Auto-agendada: {paciente['nombres']} {paciente['apellidos']}",
                'description': f"Modalidad: {tipo_consulta}\nPaciente: {paciente['nombres']} {paciente['apellidos']}\nCédula: {paciente['cedula']}\nNota: {nota}",
                'start': {'dateTime': start_datetime, 'timeZone': 'America/Caracas'},
                'end': {'dateTime': end_datetime, 'timeZone': 'America/Caracas'},
            }
            if paciente and paciente['email']:
                event_body['attendees'] = [{'email': paciente['email'], 'displayName': f"{paciente['nombres']} {paciente['apellidos']}"}]

            try:
                g_event = service.events().insert(calendarId='primary', body=event_body, sendUpdates='all').execute()
                google_event_id = g_event.get('id')
            except Exception as ge:
                print("Error creando evento en Google Calendar desde portal del paciente:", ge)
        
        monto, moneda = get_appointment_fee(cursor, patient_id, psicologo_id, tipo_consulta)
        
        cursor.execute("""
            INSERT INTO agenda_finanzas (
                paciente_id, fecha, hora, tipo_consulta, monto, moneda, 
                estado_pago, control_uso, google_event_id, cantidad_sesiones, referencia
            ) VALUES (?, ?, ?, ?, ?, ?, 'Agendada', 'No consumida', ?, 1, ?)
        """, (patient_id, fecha_norm, hora_norm, tipo_consulta, monto, moneda, google_event_id, f"Auto-agendada por paciente. Nota: {nota}"))
        
        pac_nombre = f"{paciente['nombres']} {paciente['apellidos']}"
        
        from datetime import datetime
        fecha_notif = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
            INSERT INTO notificaciones (user_id, tipo, titulo, mensaje, fecha, leida, link)
            VALUES (?, ?, ?, ?, ?, 0, ?)
        """, (psicologo_id, 'cita', 'Nueva Cita Agendada', f"{pac_nombre} ha agendado una consulta para el {fecha} a las {hora}.", fecha_notif, 'agenda'))
        
        db.commit()

        # Enviar notificación Push al psicólogo
        try:
            from app import send_webpush_notification
            send_webpush_notification(
                user_id=psicologo_id,
                title="📅 Nueva Cita Auto-Agendada",
                body=f"{pac_nombre} ha reservado una consulta para el {fecha} a las {hora}.",
                url="/?view=agenda"
            )
        except Exception as wp_ex:
            print("Error al enviar Push de auto-agendamiento por paciente:", wp_ex)

        try:
            from app import sync_patient_to_firebase
            import threading
            threading.Thread(target=sync_patient_to_firebase, args=(patient_id,)).start()
        except Exception as fb_ex:
            print("Error sincronizando Firebase:", fb_ex)
        
        return jsonify({'success': 'Tu consulta ha sido agendada automáticamente con éxito.', 'google_synced': google_event_id is not None})
    except Exception as e:
        return jsonify({'error': f'Error al agendar consulta automáticamente: {str(e)}'}), 500



@pacientes_bp.route('/api/patient/cancel-appointment', methods=['POST'])
@patient_login_required
def patient_cancel_appointment():
    patient_id = session['patient_id']
    db = get_db()
    cursor = db.cursor()
    
    try:
        from datetime import datetime
        import json
        today_str = datetime.now().strftime("%Y-%m-%d")
        now_time_str = datetime.now().strftime("%H:%M")
        
        req_data = request.json or {}
        appt_id = req_data.get('appt_id')
        
        if appt_id:
            cursor.execute("""
                SELECT id, fecha, hora, tipo_consulta, google_event_id, estado_pago, control_uso, monto, moneda, confirmada
                FROM agenda_finanzas
                WHERE id = ? AND paciente_id = ?
            """, (appt_id, patient_id))
        else:
            cursor.execute("""
                SELECT id, fecha, hora, tipo_consulta, google_event_id, estado_pago, control_uso, monto, moneda, confirmada
                FROM agenda_finanzas
                WHERE paciente_id = ? 
                  AND (fecha > ? OR (fecha = ? AND hora >= ?))
                  AND estado_pago NOT LIKE 'Cancelada%' AND estado_pago != 'Reprogramada'
                ORDER BY fecha ASC, hora ASC LIMIT 1
            """, (patient_id, today_str, today_str, now_time_str))
        
        appt = cursor.fetchone()
        if not appt:
            return jsonify({'error': 'No se encontró la cita especificada o no está activa.'}), 400
            
        appt_dict = dict(appt)
        appt_id = appt_dict['id']
        fecha_cita = appt_dict['fecha']
        hora_cita = appt_dict['hora']
        tipo_consulta = appt_dict.get('tipo_consulta', 'Online')
        google_event_id = appt_dict['google_event_id']
        
        cursor.execute("SELECT nombres, apellidos, psicologo_id FROM pacientes WHERE id = ?", (patient_id,))
        pac = cursor.fetchone()
        pac_nombre = f"{pac['nombres']} {pac['apellidos']}"
        psicologo_id = pac['psicologo_id']
        
        # Obtener límite de cancelación configurado por el psicólogo
        cursor.execute("SELECT configuracion_horarios_visual FROM usuarios WHERE id = ?", (psicologo_id,))
        u_row = cursor.fetchone()
        rule_type = 'horas'
        rule_value = 24
        if u_row and u_row[0]:
            try:
                config = json.loads(u_row[0])
                rule_type = config.get('limite_cancelacion_tipo', 'horas')
                rule_value = config.get('limite_cancelacion_valor', 24)
            except:
                pass
                
        deadline_dt = get_deadline_datetime(fecha_cita, hora_cita, rule_type, rule_value)
        fuera_de_tiempo = datetime.now() > deadline_dt
        
        # Solo se cobra si está fuera de tiempo Y el paciente había confirmado la cita previamente.
        es_late_charge = fuera_de_tiempo and (appt_dict['confirmada'] == 1)
        
        force = req_data.get('force', False)
        
        if es_late_charge and not force:
            desc = get_rule_description(rule_type, rule_value)
            return jsonify({
                'requires_confirmation': True,
                'message': f'Estás cancelando después del límite permitido ({desc}). Esta consulta se cobrará igualmente como cancelada sin aviso. ¿Estás seguro de que deseas proceder?'
            })
            
        if google_event_id:
            service = None
            try:
                from routes_admin import get_calendar_service
                service = get_calendar_service(psicologo_id)
            except Exception:
                service = None
            if service:
                try:
                    service.events().delete(calendarId='primary', eventId=google_event_id).execute()
                except Exception as ge:
                    print("Error al borrar evento de Google Calendar al cancelar paciente:", ge)
                    
        if es_late_charge:
            # Cancelación tardía cobrada: Se cobra o se descuenta de prepago si existe
            if appt_dict['estado_pago'] in ['Paga', 'Prepagada']:
                cursor.execute("""
                    UPDATE agenda_finanzas
                    SET estado_pago = 'Cancelada sin aviso - Paga', control_uso = 'Consumida', google_event_id = NULL,
                        fecha_liquidacion = datetime('now', 'localtime')
                    WHERE id = ?
                """, (appt_id,))
            else:
                cursor.execute("""
                    SELECT id, cantidad_sesiones 
                    FROM agenda_finanzas 
                    WHERE paciente_id = ? AND estado_pago = 'Prepagada' AND control_uso = 'No consumida'
                    ORDER BY fecha ASC, id ASC LIMIT 1
                """, (patient_id,))
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
                        SET estado_pago = 'Cancelada sin aviso - Paga', control_uso = 'Consumida', monto = 0.0, google_event_id = NULL,
                            metodo_pago = 'Descontado de Prepago', referencia = 'Prepago', fecha_liquidacion = datetime('now', 'localtime')
                        WHERE id = ?
                    """, (appt_id,))
                else:
                    if appt_dict['monto'] == 0.0:
                        costo_real, moneda_real = get_appointment_fee(cursor, patient_id, psicologo_id, tipo_consulta)
                    else:
                        costo_real, moneda_real = appt_dict['monto'], appt_dict['moneda']
                    cursor.execute("""
                        UPDATE agenda_finanzas
                        SET estado_pago = 'Cancelada sin aviso', google_event_id = NULL, monto = ?, moneda = ?, referencia = ?
                        WHERE id = ?
                    """, (costo_real, moneda_real, f"Cancelación tardía de consulta del {fecha_cita} a las {hora_cita}.", appt_id))
            
            create_auto_cancellation_session(
                db, patient_id, appt_id, fecha_cita, tipo_consulta,
                'Cancelada sin aviso',
                f"Consulta cancelada por el consultante fuera del límite de tiempo ({fecha_cita} a las {hora_cita}). Registrada para cobro."
            )
            notif_title = 'Cita Cancelada FUERA DE TIEMPO por Paciente'
            notif_msg = f"{pac_nombre} ha cancelado su consulta para el {fecha_cita} a las {hora_cita} fuera del límite de tiempo (Cita Confirmada). Se registrará para cobro."
        else:
            # Cancelación a tiempo (o no confirmada): No se cobra, se libera el prepago
            cursor.execute("""
                UPDATE agenda_finanzas
                SET estado_pago = 'Cancelada con aviso', control_uso = 'No consumida', monto = 0.0, google_event_id = NULL
                WHERE id = ?
            """, (appt_id,))
            
            create_auto_cancellation_session(
                db, patient_id, appt_id, fecha_cita, tipo_consulta,
                'Cancelada con aviso',
                f"Consulta cancelada por el consultante a tiempo ({fecha_cita} a las {hora_cita})."
            )
            notif_title = 'Cita Cancelada por Paciente'
            if fuera_de_tiempo and appt_dict['confirmada'] == 0:
                notif_msg = f"{pac_nombre} ha cancelado su consulta para el {fecha_cita} a las {hora_cita} fuera de tiempo pero sin confirmar, por lo que se procesa sin cargo."
            else:
                notif_msg = f"{pac_nombre} ha cancelado su consulta programada para el {fecha_cita} a las {hora_cita} a tiempo."
            
        fecha_notif = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
            INSERT INTO notificaciones (user_id, tipo, titulo, mensaje, fecha, leida, link)
            VALUES (?, ?, ?, ?, ?, 0, ?)
        """, (psicologo_id, 'cita', notif_title, notif_msg, fecha_notif, 'agenda'))
        
        db.commit()

        # Notificar al psicólogo por Push
        try:
            from app import send_webpush_notification
            send_webpush_notification(
                user_id=psicologo_id,
                title=notif_title,
                body=notif_msg,
                url="/?view=agenda"
            )
        except Exception as wp_ex:
            print("Error al enviar WebPush de cancelación por paciente:", wp_ex)

        try:
            from app import sync_patient_to_firebase
            import threading
            threading.Thread(target=sync_patient_to_firebase, args=(patient_id,)).start()
        except Exception as fb_ex:
            print("Error al sincronizar Firebase en cancelación:", fb_ex)

        return jsonify({'success': 'Cita cancelada con éxito.'})
    except Exception as e:
        return jsonify({'error': f'Error al cancelar cita: {str(e)}'}), 500



@pacientes_bp.route('/api/patient/confirm-appointment', methods=['POST'])
@patient_login_required
def patient_confirm_appointment():
    patient_id = session['patient_id']
    db = get_db()
    cursor = db.cursor()
    try:
        from datetime import datetime
        import json
        today_str = datetime.now().strftime("%Y-%m-%d")
        now_time_str = datetime.now().strftime("%H:%M")
        
        req_data = request.json or {}
        appt_id = req_data.get('appt_id')
        
        if appt_id:
            cursor.execute("""
                SELECT id, fecha, hora
                FROM agenda_finanzas
                WHERE id = ? AND paciente_id = ? AND confirmada = 0
            """, (appt_id, patient_id))
        else:
            cursor.execute("""
                SELECT id, fecha, hora
                FROM agenda_finanzas
                WHERE paciente_id = ? 
                  AND (fecha > ? OR (fecha = ? AND hora >= ?))
                  AND estado_pago NOT LIKE 'Cancelada%' AND estado_pago != 'Reprogramada'
                  AND confirmada = 0
                ORDER BY fecha ASC, hora ASC LIMIT 1
            """, (patient_id, today_str, today_str, now_time_str))
        
        appt = cursor.fetchone()
        if not appt:
            return jsonify({'error': 'No se encontró la cita especificada para confirmar o ya está confirmada.'}), 400
            
        cursor.execute("SELECT psicologo_id FROM pacientes WHERE id = ?", (patient_id,))
        pac = cursor.fetchone()
        psicologo_id = pac['psicologo_id']
        
        cursor.execute("SELECT configuracion_horarios_visual FROM usuarios WHERE id = ?", (psicologo_id,))
        u_row = cursor.fetchone()
        alerta_confirmacion = 24
        if u_row and u_row[0]:
            try:
                config = json.loads(u_row[0])
                alerta_confirmacion = int(config.get('alerta_confirmacion', 24))
            except:
                pass
                
        session_dt = datetime.strptime(f"{appt['fecha']} {appt['hora']}", "%Y-%m-%d %H:%M")
        diff_hours = (session_dt - datetime.now()).total_seconds() / 3600.0
        
        if diff_hours > alerta_confirmacion:
            return jsonify({'error': f'Aún no puedes confirmar esta cita. Estará disponible {alerta_confirmacion} horas antes de la sesión.'}), 400
            
        cursor.execute("UPDATE agenda_finanzas SET confirmada = 1 WHERE id = ?", (appt['id'],))
        
        # Notificar al psicólogo y al paciente
        cursor.execute("SELECT nombres, apellidos, psicologo_id FROM pacientes WHERE id = ?", (patient_id,))
        p_info = cursor.fetchone()
        pac_nombre = f"{p_info['nombres']} {p_info['apellidos']}" if p_info else "El consultante"
        psic_id = (p_info['psicologo_id'] if p_info and p_info['psicologo_id'] else 1)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        cursor.execute("""
            INSERT INTO notificaciones (user_id, tipo, titulo, mensaje, fecha, leida, link)
            VALUES (?, 'cita', '✅ Cita Confirmada', ?, ?, 0, 'agenda')
        """, (psic_id, f"{pac_nombre} ha confirmado su asistencia a la consulta del {appt['fecha']} a las {appt['hora']}.", now_str))
        
        try:
            fb_payload = {
                "id": int(datetime.now().timestamp() * 1000),
                "tipo": "cita",
                "titulo": "✅ Cita Confirmada",
                "mensaje": f"Has confirmado exitosamente tu consulta para el {appt['fecha']} a las {appt['hora']}.",
                "fecha": now_str,
                "leida": False
            }
            requests.post(f"{FIREBASE_DB_URL}/pacientes/{patient_id}/notificaciones.json", json=fb_payload, timeout=2.0)
        except Exception as fe:
            pass

        db.commit()
        
        import threading
        threading.Thread(target=sync_patient_to_firebase, args=(patient_id,)).start()
        
        return jsonify({'success': 'Cita confirmada con éxito.'})
    except Exception as e:
        return jsonify({'error': f'Error al confirmar cita: {str(e)}'}), 500



@pacientes_bp.route('/api/patient/reschedule-appointment', methods=['POST'])
def patient_reschedule_appointment():
    patient_id = session.get('patient_id')
    user_id = session.get('user_id')
    if not patient_id and not user_id:
        return jsonify({'error': 'Debe iniciar sesión para reprogramar.'}), 401
        
    db = get_db()
    cursor = db.cursor()
    data = request.json or {}
    new_date = data.get('fecha')
    new_hour = data.get('hora')
    appt_id = data.get('appt_id')
    
    if not new_date or not new_hour:
        return jsonify({'error': 'Fecha y hora requeridas.'}), 400
        
    try:
        from datetime import datetime, timedelta
        import json
        today_str = datetime.now().strftime("%Y-%m-%d")
        now_time_str = datetime.now().strftime("%H:%M")
        
        if appt_id:
            cursor.execute("""
                SELECT id, fecha, hora, google_event_id, paciente_id
                FROM agenda_finanzas
                WHERE id = ?
            """, (appt_id,))
        elif patient_id:
            cursor.execute("""
                SELECT id, fecha, hora, google_event_id, paciente_id
                FROM agenda_finanzas
                WHERE paciente_id = ? 
                  AND (fecha > ? OR (fecha = ? AND hora >= ?))
                  AND estado_pago NOT LIKE 'Cancelada%' AND estado_pago != 'Reprogramada'
                ORDER BY fecha ASC, hora ASC LIMIT 1
            """, (patient_id, today_str, today_str, now_time_str))
        else:
            return jsonify({'error': 'Cita no especificada.'}), 400
        
        appt = cursor.fetchone()
        if not appt:
            return jsonify({'error': 'No se encontró la cita especificada para reprogramar.'}), 400
            
        patient_id = appt['paciente_id']
        appt_id = appt['id']
        old_fecha = appt['fecha']
        old_hora = appt['hora']
        google_event_id = appt['google_event_id']
        
        cursor.execute("SELECT psicologo_id FROM pacientes WHERE id = ?", (patient_id,))
        pac = cursor.fetchone()
        psicologo_id = pac['psicologo_id'] if pac else user_id
        
        cursor.execute("SELECT configuracion_horarios_visual FROM usuarios WHERE id = ?", (psicologo_id,))
        u_row = cursor.fetchone()
        limite_cancelacion = 24
        if u_row and u_row[0]:
            try:
                config = json.loads(u_row[0])
                limite_cancelacion = int(config.get('limite_cancelacion', 24))
            except:
                pass
                
        session_dt = datetime.strptime(f"{old_fecha} {old_hora}", "%Y-%m-%d %H:%M")
        diff_hours = (session_dt - datetime.now()).total_seconds() / 3600.0
        
        if not user_id and diff_hours <= limite_cancelacion:
            return jsonify({'error': f'No puedes reprogramar esta cita. Has superado el límite de {limite_cancelacion} horas antes de la sesión.'}), 400
            
        cursor.execute("""
            SELECT af.id FROM agenda_finanzas af
            JOIN pacientes p ON af.paciente_id = p.id
            WHERE af.fecha = ? AND af.hora = ? AND p.psicologo_id = ?
              AND af.estado_pago NOT LIKE 'Cancelada%' AND af.estado_pago != 'Reprogramada'
        """, (new_date, new_hour, psicologo_id))
        if cursor.fetchone():
            return jsonify({'error': 'El horario seleccionado ya está reservado.'}), 400
            
        if google_event_id:
            service = None
            try:
                from routes_admin import get_calendar_service
                service = get_calendar_service(psicologo_id)
            except Exception:
                service = None
            if service:
                try:
                    cursor.execute("SELECT configuracion_horarios_visual FROM usuarios WHERE id = ?", (psicologo_id,))
                    u_row2 = cursor.fetchone()
                    duration = 60
                    if u_row2 and u_row2[0]:
                        try:
                            config2 = json.loads(u_row2[0])
                            duration = int(config2.get('duracion', 60))
                        except:
                            pass
                    start_dt = datetime.strptime(f"{new_date} {new_hour}", "%Y-%m-%d %H:%M")
                    start_iso = f"{new_date}T{new_hour}:00-04:00"
                    end_dt = start_dt + timedelta(minutes=duration)
                    end_iso = end_dt.strftime("%Y-%m-%dT%H:%M:%S-04:00")
                    
                    cursor.execute("SELECT nombres, apellidos, email FROM pacientes WHERE id = ?", (patient_id,))
                    pac_row = cursor.fetchone()
                    pac_email = pac_row['email'] if pac_row else None
                    pac_name = f"{pac_row['nombres']} {pac_row['apellidos']}" if pac_row else ""
                    
                    cursor.execute("SELECT nombres FROM usuarios WHERE id = ?", (psicologo_id,))
                    u_row3 = cursor.fetchone()
                    therapist_name = u_row3['nombres'] if u_row3 else "Paulo Mora"
                    
                    event_body = service.events().get(calendarId='primary', eventId=google_event_id).execute()
                    event_body['summary'] = f"Consulta Psicológica - {pac_name}"
                    event_body['description'] = f"Modalidad: {event_body.get('description', '').split('Modalidad:')[-1].splitlines()[0] if 'Modalidad:' in event_body.get('description', '') else 'Online'}\nPsicólogo: Psic. {therapist_name}\n[Reprogramada]"
                    event_body['start'] = {'dateTime': start_iso, 'timeZone': 'America/Caracas'}
                    event_body['end'] = {'dateTime': end_iso, 'timeZone': 'America/Caracas'}
                    event_body['guestsCanInviteOthers'] = False
                    
                    if pac_email:
                        event_body['attendees'] = [
                            {
                                'email': pac_email,
                                'displayName': pac_name
                            }
                        ]
                    service.events().update(calendarId='primary', eventId=google_event_id, body=event_body, sendUpdates='all').execute()
                except Exception as ge:
                    print("Error updating Google Calendar event during reschedule:", ge)
                    
        cursor.execute("""
            UPDATE agenda_finanzas
            SET fecha = ?, hora = ?, confirmada = 0
            WHERE id = ?
        """, (new_date, new_hour, appt_id))
        
        mod_por = 'Psicólogo' if user_id else 'Paciente'
        fecha_reg = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
            INSERT INTO historial_reprogramaciones (
                paciente_id, agenda_id, fecha_anterior, hora_anterior,
                fecha_nueva, hora_nueva, modificado_por, motivo, fecha_registro
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (patient_id, appt_id, old_fecha, old_hora, new_date, new_hour, mod_por, f"Reprogramado del {old_fecha} {old_hora} al {new_date} {new_hour}", fecha_reg))
        
        cursor.execute("SELECT nombres, apellidos, psicologo_id FROM pacientes WHERE id = ?", (patient_id,))
        pac = cursor.fetchone()
        pac_nombre = f"{pac['nombres']} {pac['apellidos']}"
        psic_id = (pac['psicologo_id'] if pac and pac['psicologo_id'] else (psicologo_id or 1))
        
        fecha_notif = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
            INSERT INTO notificaciones (user_id, tipo, titulo, mensaje, fecha, leida, link)
            VALUES (?, ?, ?, ?, ?, 0, ?)
        """, (psic_id, 'cita', 'Cita Reprogramada por Paciente', f"{pac_nombre} ha reprogramado su consulta del {old_fecha} a las {old_hora} para la nueva fecha: {new_date} a las {new_hour}.", fecha_notif, 'agenda'))
        
        db.commit()

        # Notificar al psicólogo por Push si fue el paciente quien reprogramó
        if not user_id:
            try:
                send_webpush_notification(
                    user_id=psicologo_id,
                    title="📆 Cita Reprogramada por Paciente",
                    body=f"{pac_nombre} ha reprogramado su consulta del {old_fecha} a las {old_hora} para el {new_date} a las {new_hour}.",
                    url="/?view=agenda"
                )
            except Exception as wp_ex:
                print("Error al enviar WebPush de reprogramación por paciente:", wp_ex)

        import threading
        threading.Thread(target=sync_patient_to_firebase, args=(patient_id,)).start()

        return jsonify({'success': 'Cita reprogramada con éxito.'})
    except Exception as e:
        return jsonify({'error': f'Error al reprogramar cita: {str(e)}'}), 500



@pacientes_bp.route('/api/patient/payment', methods=['POST'])
@patient_login_required
def patient_add_payment_report():
    patient_id = session['patient_id']
    data = request.json
    
    monto = data.get('monto')
    moneda = data.get('moneda')
    metodo = data.get('metodo')
    referencia = data.get('referencia')
    fecha = data.get('fecha')
    
    if not monto or not moneda or not metodo or not fecha:
        return jsonify({'error': 'Monto, moneda, método y fecha son obligatorios.'}), 400
        
    try:
        import requests
        from datetime import datetime
        fecha_registro = datetime.now().isoformat()
        
        db = get_db()
        cursor = db.cursor()
        
        # Anti-duplicados: Evitar registros repetidos si se presiona varias veces o por reintentos de red
        if referencia and str(referencia).strip():
            cursor.execute("""
                SELECT id FROM pagos_notificados 
                WHERE paciente_id = ? AND referencia = ? AND estado = 'Pendiente de verificación'
            """, (patient_id, str(referencia).strip()))
            if cursor.fetchone():
                return jsonify({'success': 'El reporte de pago ya fue registrado anteriormente.', 'duplicate': True})
        else:
            cursor.execute("""
                SELECT id FROM pagos_notificados 
                WHERE paciente_id = ? AND monto = ? AND moneda = ? AND fecha = ? AND estado = 'Pendiente de verificación'
            """, (patient_id, monto, moneda, fecha))
            if cursor.fetchone():
                return jsonify({'success': 'El reporte de pago ya fue registrado anteriormente.', 'duplicate': True})

        cursor.execute("""
            INSERT INTO pagos_notificados (paciente_id, monto, moneda, metodo, referencia, fecha, estado, fecha_registro)
            VALUES (?, ?, ?, ?, ?, ?, 'Pendiente de verificación', ?)
        """, (patient_id, monto, moneda, metodo, referencia, fecha, fecha_registro))
        
        # Sincronización secundaria a Firebase (en segundo plano / opcional)
        try:
            fb_res = requests.post(f"{FIREBASE_DB_URL}/pacientes/{patient_id}/pagos_notificados.json", json=payment_payload, timeout=5)
        except Exception as fe:
            print("Error secundario al guardar pago en Firebase:", fe)
            
        cursor.execute("SELECT nombres, apellidos, psicologo_id FROM pacientes WHERE id = ?", (patient_id,))
        pac = cursor.fetchone()
        pac_nombre = f"{pac['nombres']} {pac['apellidos']}"
        psicologo_id = pac['psicologo_id'] or 1
        
        fecha_notif = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
            INSERT INTO notificaciones (user_id, tipo, titulo, mensaje, fecha, leida, link)
            VALUES (?, ?, ?, ?, ?, 0, ?)
        """, (psicologo_id, 'pago', 'Nuevo Pago Notificado', f"{pac_nombre} notificó un pago de {monto} {moneda}.", fecha_notif, 'finance'))
        db.commit()

        # Enviar notificación WebPush al psicólogo
        try:
            send_webpush_notification(
                user_id=psicologo_id,
                title="Nuevo Pago Notificado",
                body=f"El paciente {pac_nombre} ha reportado un pago de {monto} {moneda} para su verificación.",
                url="/?view=finanzas"
            )
        except Exception as wp_ex:
            print("Error al enviar WebPush de pago notificado:", wp_ex)
        
        return jsonify({'success': 'Pago notificado con éxito. Su psicólogo lo verificará pronto.'})
    except Exception as e:
        return jsonify({'error': f'Error al notificar pago: {str(e)}'}), 500

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


def get_patient_portal_data_dict(patient_id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT p.*, u.nombres as psicologo_nombres, u.apellidos as psicologo_apellidos,
               u.metodos_pago as psicologo_metodos_pago, u.terminos_condiciones as psicologo_terminos,
               u.modalidades_json as psicologo_modalidades_json
        FROM pacientes p
        LEFT JOIN usuarios u ON p.psicologo_id = u.id
        WHERE p.id = ?
    """, (patient_id,))
    row = cursor.fetchone()
    if not row:
        return None
        
    p_dict = dict(row)
    p_dict.pop('password_hash', None)
    
    psic_nom = f"Psic. {p_dict.get('psicologo_nombres') or ''} {p_dict.get('psicologo_apellidos') or ''}".strip()
    if psic_nom == "Psic.":
        psic_nom = "Psic. Paulo Mora"
    p_dict['psicologo_asignado'] = psic_nom
    
    modalidades = ["Online", "Presencial"]
    if p_dict.get('psicologo_modalidades_json'):
        try:
            m_raw = json.loads(p_dict['psicologo_modalidades_json'])
            if isinstance(m_raw, list):
                modalidades = m_raw
            elif isinstance(m_raw, dict):
                m_list = []
                if m_raw.get('online'): m_list.append("Online")
                if m_raw.get('presencial'): m_list.append("Presencial")
                if m_raw.get('domicilio'): m_list.append("Domicilio")
                if m_list: modalidades = m_list
        except Exception:
            pass
            
    terms = (p_dict.get('psicologo_terminos') or '').strip()
    if not terms:
        terms = DEFAULT_TERMS_TEXT
        
    metodos = (p_dict.get('psicologo_metodos_pago') or '').strip()
    if not metodos:
        metodos = "Contacta a tu psicólogo para conocer los métodos de pago disponibles."

    # 1. Citas próximas activas del consultante
    from datetime import datetime
    today_str = datetime.now().strftime("%Y-%m-%d")
    now_time_str = datetime.now().strftime("%H:%M")

    cursor.execute("""
        SELECT af.id, af.fecha, af.hora, af.tipo_consulta, af.confirmada, af.estado_pago, af.referencia
        FROM agenda_finanzas af
        WHERE af.paciente_id = ?
          AND (af.fecha > ? OR (af.fecha = ? AND af.hora >= ?))
          AND (af.estado_pago IS NULL OR (af.estado_pago NOT LIKE 'Cancelada%' AND af.estado_pago != 'Reprogramada'))
        ORDER BY af.fecha ASC, af.hora ASC
    """, (patient_id, today_str, today_str, now_time_str))
    
    citas_rows = cursor.fetchall()
    proximas_citas = []

    psicologo_id = p_dict.get('psicologo_id')
    rule_type = 'horas'
    rule_value = 24
    if psicologo_id:
        cursor.execute("SELECT configuracion_horarios_visual FROM usuarios WHERE id = ?", (psicologo_id,))
        u_row = cursor.fetchone()
        if u_row and u_row[0]:
            try:
                config = json.loads(u_row[0])
                rule_type = config.get('limite_cancelacion_tipo', 'horas')
                rule_value = config.get('limite_cancelacion_valor', 24)
            except:
                pass

    for c in citas_rows:
        c_dict = dict(c)
        try:
            c_dt = datetime.strptime(f"{c_dict['fecha']} {c_dict['hora']}", "%Y-%m-%d %H:%M")
            time_diff = (c_dt - datetime.now()).total_seconds() / 3600.0
        except Exception:
            time_diff = 48.0
        c_dict['tiempo_restante_horas'] = time_diff
        c_dict['limite_cancelacion'] = rule_value if rule_type == 'horas' else rule_value * 24
        proximas_citas.append(c_dict)

    # 2. Resumen de la última sesión evolucionada del consultante
    cursor.execute("""
        SELECT resumen_paciente, anotaciones_proxima, tareas_asignadas, recursos_entregados, archivo_adjunto
        FROM sesiones
        WHERE paciente_id = ? AND (estado IS NULL OR estado != 'Cancelada')
        ORDER BY fecha DESC, id DESC LIMIT 1
    """, (patient_id,))
    s_row = cursor.fetchone()
    compartido = {}
    if s_row:
        compartido = {
            'resumen_sesion': s_row['resumen_paciente'] or '',
            'temas_proxima_sesion': s_row['anotaciones_proxima'] or '',
            'tareas_asignadas': s_row['tareas_asignadas'] or '',
            'recursos_entregados': s_row['recursos_entregados'] or '',
            'archivo_adjunto': s_row['archivo_adjunto'] or ''
        }

    # 3. Resumen financiero (prepagadas y deudas)
    cursor.execute("""
        SELECT SUM(cantidad_sesiones) as total_prepago
        FROM agenda_finanzas
        WHERE paciente_id = ? AND estado_pago = 'Prepagada' AND control_uso = 'No consumida'
    """, (patient_id,))
    pre_row = cursor.fetchone()
    prepagadas = (pre_row['total_prepago'] or 0) if pre_row else 0

    cursor.execute("""
        SELECT id, fecha, hora, tipo_consulta, monto, moneda
        FROM agenda_finanzas
        WHERE paciente_id = ? 
          AND (estado_pago = 'Pendiente' OR estado_pago = 'Agendada' OR estado_pago LIKE 'Cancelada sin aviso%')
          AND monto > 0
    """, (patient_id,))
    debt_rows = cursor.fetchall()
    deuda = {}
    deudas_detalle = []
    for d in debt_rows:
        d_dict = dict(d)
        mon = d_dict.get('moneda') or '$'
        deuda[mon] = deuda.get(mon, 0.0) + float(d_dict.get('monto') or 0)
        deudas_detalle.append(d_dict)

    finanzas = {
        'prepagadas': prepagadas,
        'deuda': deuda,
        'deudas_detalle': deudas_detalle
    }

    return {
        'perfil': p_dict,
        'modalidades': modalidades,
        'metodos_pago': metodos,
        'terminos_texto': terms,
        'terminos_requeridos': (p_dict.get('terminos_aceptados') != 1),
        'proximas_citas': proximas_citas,
        'compartido': compartido,
        'finanzas': finanzas
    }


@pacientes_bp.route('/api/patient/portal-data', methods=['GET'])
@patient_login_required
def get_patient_portal_data():
    patient_id = session['patient_id']
    try:
        data = get_patient_portal_data_dict(patient_id)
        if not data:
            return jsonify({'error': 'Paciente no encontrado'}), 404
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': f'Error al obtener datos: {str(e)}'}), 500

DEFAULT_TERMS_TEXT = """Términos y Condiciones del Encuadre Terapéutico
Estimado/a consultante:

A continuación se presentan las condiciones operativas que rigen nuestro proceso terapéutico. Este marco tiene como objetivo proteger el tiempo de ambos, garantizar el compromiso mutuo y brindar una estructura clara a nuestras sesiones.

1. Duración de la Sesión
Cada sesión tiene una duración estimada de entre 45 minutos y 1 hora.

2. Gestión del Tiempo y Tardanzas
Retrasos por parte del consultante:
- Si llegas con retraso a la cita, el tiempo extra se otorgará únicamente si la agenda del terapeuta lo permite.
- Si el terapeuta tiene consultas posteriores, la sesión finalizará a la hora programada originalmente para no afectar el espacio de otros consultantes, aprovechando únicamente los minutos restantes.
- Tolerancia máxima: Pasados 15 minutos de retraso sin notificación, la consulta se considerará como consulta perdida (asistencia fallida) y deberá ser abonada en su totalidad (o descontada del paquete activo).

Retrasos por parte del terapeuta:
- En caso de que el terapeuta inicie la sesión con retraso, se garantizará el cumplimiento del tiempo total asignado (45 a 60 minutos), adaptando la agenda para no perjudicar al consultante.

3. Confirmación, Cancelación y Tiempo de Gracia
Confirmación de la cita:
- Toda sesión requiere confirmación previa. Si llega el día de la cita y esta no ha sido confirmada, el espacio no se reservará y la consulta se registrará automáticamente como cancelada con previo aviso.

Regla de cancelación y tiempo de gracia:
- Una vez confirmada la consulta, dispones de un tiempo de gracia de hasta 3 horas antes de la hora agendada para realizar cualquier cambio o cancelación sin costo alguno (cancelación con aviso).
- Pasado dicho límite (menos de 3 horas antes de la sesión), si cancelas o no te presentas, la sesión se computará como realizada y deberá ser abonada en su totalidad.

4. Paquetes de Sesiones
En caso de contar con un paquete de sesiones prepagado, cualquier inasistencia o cancelación fuera del tiempo de gracia permitido se descontará automáticamente del saldo de sesiones disponibles.

5. Cancelaciones por Parte del Terapeuta
Si el terapeuta debiera cancelar una sesión sin el debido aviso previo, asume el compromiso de reprogramar la consulta en la fecha disponible más próxima, habilitando de ser necesario fines de semana o días feriados para garantizar la atención oportuna.

Al agendar y confirmar tus sesiones a través de la plataforma, declaras haber leído y aceptado estos Términos y Condiciones para el desarrollo del proceso terapéutico."""



@pacientes_bp.route('/api/patient/accept-terms', methods=['POST'])
@patient_login_required
def accept_patient_terms():
    patient_id = session['patient_id']
    db = get_db()
    cursor = db.cursor()
    from datetime import datetime
    now_str = datetime.now().strftime("%d/%m/%Y %H:%M")
    try:
        try:
            cursor.execute("PRAGMA table_info(notificaciones)")
            cols_notif = [row[1] for row in cursor.fetchall()]
            if 'user_id' not in cols_notif:
                cursor.execute("ALTER TABLE notificaciones ADD COLUMN user_id INTEGER")
                db.commit()
        except Exception:
            pass

        cursor.execute("UPDATE pacientes SET terminos_aceptados = 1, fecha_aceptacion_terminos = ? WHERE id = ?", (now_str, patient_id))
        cursor.execute("SELECT nombres, apellidos, psicologo_id FROM pacientes WHERE id = ?", (patient_id,))
        p_row = cursor.fetchone()
        if p_row:
            nombres = p_row[0] if isinstance(p_row, (tuple, list)) else p_row['nombres']
            apellidos = p_row[1] if isinstance(p_row, (tuple, list)) else p_row['apellidos']
            psic_id = (p_row[2] if isinstance(p_row, (tuple, list)) else p_row['psicologo_id']) or 1
            pat_name = f"{nombres} {apellidos}".strip()
            notif_msg = f"El consultante {pat_name} ha aceptado los Términos y Condiciones del Encuadre Terapéutico."
            cursor.execute("""
                INSERT INTO notificaciones (user_id, tipo, titulo, mensaje, fecha, leida, link)
                VALUES (?, 'terminos_aceptados', '📜 Términos Aceptados', ?, ?, 0, '/#pacientes')
            """, (psic_id, notif_msg, now_str))
            send_fcm_notification(user_id=psic_id, title="📜 Términos Aceptados", body=notif_msg, url="/#pacientes")
        db.commit()
        return jsonify({'success': 'Términos y condiciones aceptados.', 'fecha': now_str})
    except Exception as e:
        print("Error en accept_patient_terms:", e)
        return jsonify({'error': str(e)}), 500



@pacientes_bp.route('/api/patient/payments/notified', methods=['GET'])
@patient_login_required
def get_patient_notified_payments_history():
    patient_id = session['patient_id']
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT id, monto, moneda, metodo, referencia, fecha, estado, motivo_rechazo, fecha_registro
        FROM pagos_notificados
        WHERE paciente_id = ?
        ORDER BY fecha_registro DESC
    """, (patient_id,))
    rows = cursor.fetchall()
    return jsonify([dict(r) for r in rows])



@pacientes_bp.route('/api/patient/sessions', methods=['GET'])
@patient_login_required
def get_patient_session_history():
    patient_id = session['patient_id']
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT id, fecha, modalidad, resumen_paciente, tareas_asignadas, recursos_entregados, anotaciones_proxima, archivo_adjunto
        FROM sesiones
        WHERE paciente_id = ? AND estado = 'Realizada'
        ORDER BY fecha DESC, id DESC
    """, (patient_id,))
    rows = cursor.fetchall()
    results = []
    for r in rows:
        d = dict(r)
        d['resumen_paciente'] = decrypt_clinical_text(d.get('resumen_paciente')) or ''
        results.append(d)
    return jsonify(results)



@pacientes_bp.route('/api/patients/<int:patient_id>/print', methods=['GET'])
@login_required
def print_patient_card(patient_id):
    db = get_db()
    cursor = db.cursor()
    
    # 1. Obtener datos del paciente
    cursor.execute("SELECT * FROM pacientes WHERE id = ?", (patient_id,))
    patient_row = cursor.fetchone()
    if not patient_row:
        return "Paciente no encontrado", 404
        
    patient = dict(patient_row)
    if patient.get('diagnostico'):
        patient['diagnostico'] = decrypt_clinical_text(patient['diagnostico'])
        
    # 2. Obtener sesiones en orden cronológico
    cursor.execute("""
        SELECT fecha, modalidad, resumen, test_aplicados 
        FROM sesiones 
        WHERE paciente_id = ? AND estado = 'Realizada'
        ORDER BY fecha ASC, id ASC
    """, (patient_id,))
    raw_sessions = cursor.fetchall()
    sessions = []
    for s in raw_sessions:
        s_dict = dict(s)
        s_dict['resumen'] = decrypt_clinical_text(s_dict.get('resumen')) or ''
        s_dict['test_aplicados'] = decrypt_clinical_text(s_dict.get('test_aplicados')) or ''
        sessions.append(s_dict)
    
    html_template = """
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <title>Ficha Clínica - {{ patient.nombres }} {{ patient.apellidos }}</title>
        <style>
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                color: #333;
                line-height: 1.6;
                margin: 0;
                padding: 0;
                background-color: #fff;
            }
            .container {
                width: 100%;
                max-width: 800px;
                margin: 0 auto;
                padding: 20px;
            }
            .header {
                border-bottom: 2px solid #5d3a6f;
                padding-bottom: 15px;
                margin-bottom: 30px;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }
            .header h1 {
                margin: 0;
                color: #5d3a6f;
                font-size: 24px;
            }
            .section-title {
                color: #5d3a6f;
                border-bottom: 1px solid #ddd;
                padding-bottom: 5px;
                margin-top: 30px;
                margin-bottom: 15px;
                font-size: 18px;
                font-weight: 700;
            }
            .grid-2 {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 15px 30px;
                margin-bottom: 20px;
            }
            .info-item {
                font-size: 14px;
            }
            .info-item strong {
                color: #555;
                display: block;
                margin-bottom: 2px;
                font-size: 12px;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }
            .diagnostic-box {
                background-color: #f9f9f9;
                border-left: 4px solid #5d3a6f;
                padding: 15px;
                border-radius: 4px;
                font-style: italic;
                font-size: 14px;
                margin-bottom: 20px;
            }
            .session-card {
                border: 1px solid #eee;
                border-radius: 6px;
                padding: 15px;
                margin-bottom: 15px;
                page-break-inside: avoid;
            }
            .session-header {
                display: flex;
                justify-content: space-between;
                border-bottom: 1px dashed #eee;
                padding-bottom: 8px;
                margin-bottom: 10px;
            }
            .session-title-num {
                font-weight: 700;
                color: #5d3a6f;
            }
            .session-date {
                color: #666;
                font-size: 13px;
            }
            .session-body {
                font-size: 14px;
                margin-bottom: 10px;
            }
            .session-tests {
                background-color: #f4f0f6;
                padding: 8px 12px;
                border-radius: 4px;
                font-size: 13px;
                margin-top: 5px;
            }
            .no-print-btn {
                padding: 8px 16px;
                background-color: #5d3a6f;
                color: white;
                border: none;
                border-radius: 4px;
                cursor: pointer;
                font-weight: bold;
                font-size: 14px;
            }
            @media print {
                body {
                    background: white;
                    color: black;
                }
                .container {
                    width: 100%;
                    max-width: 100%;
                    padding: 0;
                }
                .no-print {
                    display: none;
                }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Ficha Clínica Individual</h1>
                <div class="no-print">
                    <button class="no-print-btn" onclick="window.print()">Imprimir Ficha / Guardar como PDF</button>
                </div>
            </div>

            <div class="section-title">Datos Personales</div>
            <div class="grid-2">
                <div class="info-item"><strong>Nombre Completo</strong>{{ patient.nombres }} {{ patient.apellidos }}</div>
                <div class="info-item"><strong>Cédula de Identidad</strong>{{ patient.cedula }}</div>
                <div class="info-item"><strong>Edad</strong>{{ patient.edad or 'No especificado' }} años</div>
                <div class="info-item"><strong>Género</strong>{{ patient.genero or 'No especificado' }}</div>
                <div class="info-item"><strong>Fecha de Nacimiento</strong>{{ patient.fecha_nacimiento or 'No especificado' }}</div>
                <div class="info-item"><strong>Residencia Actual</strong>{{ patient.residencia_actual or 'No especificado' }}</div>
            </div>

            <div class="section-title">Impresión Diagnóstica</div>
            <div class="diagnostic-box">
                {{ patient.diagnostico or 'Sin impresión diagnóstica registrada en la historia clínica.' }}
            </div>

            <div class="section-title">Historial de Sesiones y Evolución</div>
            {% if sessions %}
                {% for s in sessions %}
                    <div class="session-card">
                        <div class="session-header">
                            <span class="session-title-num">Sesión #{{ loop.index }}</span>
                            <span class="session-date">{{ s.fecha }} ({{ s.modalidad }})</span>
                        </div>
                        <div class="session-body">
                            <strong>Temas Abordados:</strong>
                            <div style="margin-top: 5px; white-space: pre-wrap;">{{ s.resumen or 'No especificado' }}</div>
                        </div>
                        {% if s.test_aplicados %}
                            <div class="session-tests">
                                <strong>Pruebas Aplicadas:</strong> {{ s.test_aplicados }}
                            </div>
                        {% endif %}
                    </div>
                {% endfor %}
            {% else %}
                <p style="color: #666; font-style: italic;">No se han registrado sesiones para este consultante.</p>
            {% endif %}
        </div>
        <script>
            window.onload = function() {
                setTimeout(function() {
                    window.print();
                }, 500);
            }
        </script>
    </body>
    </html>
    """
    return render_template_string(html_template, patient=patient, sessions=sessions)


# ==========================================
# SEGUIMIENTO DE SESIÓN (EVOLUCIÓN)
# ==========================================



@pacientes_bp.route('/api/patients/<int:patient_id>/reschedule-history', methods=['GET'])
@login_required
def get_patient_reschedule_history(patient_id):
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("""
            SELECT id, agenda_id, fecha_anterior, hora_anterior, fecha_nueva, hora_nueva,
                   modificado_por, motivo, fecha_registro
            FROM historial_reprogramaciones
            WHERE paciente_id = ?
            ORDER BY fecha_registro DESC
        """, (patient_id,))
        rows = cursor.fetchall()
        return jsonify([dict(r) for r in rows])
    except Exception as e:
        return jsonify({'error': f'Error al consultar historial de reprogramaciones: {str(e)}'}), 500



@pacientes_bp.route('/api/patient/agenda-history', methods=['GET'])
@patient_login_required
def get_patient_agenda_history():
    try:
        patient_id = session.get('patient_id')
        if not patient_id:
            return jsonify({'error': 'No ha iniciado sesión como paciente'}), 401
            
        db = get_db()
        cursor = db.cursor()
        
        # Conciliar deudas automáticamente si tiene prepagos
        auto_settle_patient_debts(db, patient_id)
        
        cursor.execute("""
            SELECT af.id, af.fecha, af.hora, af.tipo_consulta, af.estado_pago, af.control_uso, af.confirmada,
                   af.monto, af.moneda, af.fecha_liquidacion
            FROM agenda_finanzas af
            WHERE af.paciente_id = ?
            ORDER BY af.fecha DESC, af.hora DESC
        """, (patient_id,))
        
        rows = cursor.fetchall()
        result = []
        
        for r in rows:
            row_dict = dict(r)
            est = row_dict['estado_pago']
            
            if est == 'Paga' or est == 'Prepagada' or est == 'Cancelada sin aviso - Paga':
                accion = 'Realizada / Paga'
            elif est == 'Cancelada con aviso':
                accion = 'Cancelada a tiempo'
            elif est == 'Cancelada sin aviso':
                accion = 'Cancelada tardía (sin aviso)'
            elif est == 'Reprogramada':
                accion = 'Reprogramada'
            else:
                if row_dict['confirmada'] == 1:
                    accion = 'Agendada (Confirmada)'
                else:
                    accion = 'Agendada (Pendiente por confirmar)'
                    
            row_dict['accion'] = accion
            result.append(row_dict)
            
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': f'Error al obtener historial de agenda del paciente: {str(e)}'}), 500



@pacientes_bp.route('/api/patient/adherence/medications', methods=['GET', 'POST'])
@patient_login_required
def patient_adherence_medications():
    patient_id = session.get('patient_id')
    db = get_db()
    cursor = db.cursor()
    
    if request.method == 'POST':
        data = request.json or {}
        nombre_medicamento = (data.get('nombre_medicamento') or '').strip()
        dosis = (data.get('dosis') or '').strip()
        hora_prescrita = (data.get('hora_prescrita') or '').strip()
        
        if not nombre_medicamento:
            return jsonify({'error': 'El nombre del medicamento es obligatorio.'}), 400
            
        cursor.execute("""
            INSERT INTO adherencia_medicamentos (paciente_id, nombre_medicamento, dosis, hora_prescrita, activo)
            VALUES (?, ?, ?, ?, 1)
        """, (patient_id, nombre_medicamento, dosis, hora_prescrita))
        db.commit()
        med_id = cursor.lastrowid
        return jsonify({'success': True, 'medication': {'id': med_id, 'nombre_medicamento': nombre_medicamento, 'dosis': dosis, 'hora_prescrita': hora_prescrita, 'activo': 1}})
        
    cursor.execute("SELECT * FROM adherencia_medicamentos WHERE paciente_id = ? AND activo = 1 ORDER BY hora_prescrita ASC, id ASC", (patient_id,))
    rows = [dict(r) for r in cursor.fetchall()]
    return jsonify(rows)



@pacientes_bp.route('/api/patient/adherence/medications/<int:med_id>', methods=['DELETE'])
@patient_login_required
def delete_patient_adherence_medication(med_id):
    patient_id = session.get('patient_id')
    db = get_db()
    cursor = db.cursor()
    cursor.execute("UPDATE adherencia_medicamentos SET activo = 0 WHERE id = ? AND paciente_id = ?", (med_id, patient_id))
    db.commit()
    return jsonify({'success': True})



@pacientes_bp.route('/api/patient/adherence/log', methods=['POST'])
@patient_login_required
def log_patient_adherence():
    patient_id = session.get('patient_id')
    data = request.json or {}
    fecha = data.get('fecha') or datetime.now().strftime('%Y-%m-%d')
    registros = data.get('registros', [])
    
    db = get_db()
    cursor = db.cursor()
    
    for item in registros:
        med_id = item.get('medicamento_id')
        tomado = 1 if item.get('tomado') else 0
        hora_tomado = item.get('hora_tomado', '')
        notas = item.get('notas', '')
        
        if not med_id:
            continue
            
        cursor.execute("""
            INSERT INTO adherencia_registros (paciente_id, medicamento_id, fecha, tomado, hora_tomado, notas)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(paciente_id, medicamento_id, fecha) DO UPDATE SET
                tomado = excluded.tomado,
                hora_tomado = excluded.hora_tomado,
                notas = excluded.notas
        """, (patient_id, med_id, fecha, tomado, hora_tomado, notas))
    db.commit()
    
    try:
        cursor.execute("SELECT nombres, apellidos, psicologo_id FROM pacientes WHERE id = ?", (patient_id,))
        pac = cursor.fetchone()
        if pac:
            pac_nombre = f"{pac['nombres']} {pac['apellidos']}".strip()
            psic_id = pac['psicologo_id'] or 1
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            notif_title = "💊 Adherencia al Tratamiento Registrada"
            notif_msg = f"El consultante {pac_nombre} registró la toma de medicamentos para la fecha {fecha}."
            cursor.execute("""
                INSERT INTO notificaciones (user_id, tipo, titulo, mensaje, fecha, leida, link)
                VALUES (?, 'herramienta_terapeutica', ?, ?, ?, 0, '/#therapist-tools')
            """, (psic_id, notif_title, notif_msg, now_str))
            db.commit()
            try:
                send_webpush_notification(user_id=psic_id, title=notif_title, body=notif_msg, url="/#therapist-tools")
            except Exception:
                pass
    except Exception as _e:
        print("Error notif adherencia:", _e)
        
    return jsonify({'success': True, 'message': 'Registro de adherencia a medicación guardado.'})



@pacientes_bp.route('/api/patient/adherence/history', methods=['GET'])
@patient_login_required
def get_patient_adherence_history():
    patient_id = session.get('patient_id')
    fecha_req = request.args.get('fecha')
    db = get_db()
    cursor = db.cursor()
    
    if fecha_req:
        cursor.execute("""
            SELECT ar.*, am.nombre_medicamento, am.dosis, am.hora_prescrita
            FROM adherencia_registros ar
            JOIN adherencia_medicamentos am ON ar.medicamento_id = am.id
            WHERE ar.paciente_id = ? AND ar.fecha = ?
        """, (patient_id, fecha_req))
    else:
        cursor.execute("""
            SELECT ar.*, am.nombre_medicamento, am.dosis, am.hora_prescrita
            FROM adherencia_registros ar
            JOIN adherencia_medicamentos am ON ar.medicamento_id = am.id
            WHERE ar.paciente_id = ?
            ORDER BY ar.fecha DESC, am.hora_prescrita ASC LIMIT 100
        """, (patient_id,))
    rows = [dict(r) for r in cursor.fetchall()]
    return jsonify(rows)

# --- ENDPOINTS ACTIVACIÓN CONDUCTUAL ---



@pacientes_bp.route('/api/patient/activation/activities', methods=['GET'])
@patient_login_required
def patient_activation_activities():
    patient_id = session.get('patient_id')
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM activacion_actividades WHERE paciente_id = ? AND activa = 1 ORDER BY categoria ASC, id ASC", (patient_id,))
    rows = [dict(r) for r in cursor.fetchall()]
    return jsonify(rows)



@pacientes_bp.route('/api/patient/activation/log', methods=['POST'])
@patient_login_required
def log_patient_activation():
    patient_id = session.get('patient_id')
    data = request.json or {}
    fecha = data.get('fecha') or datetime.now().strftime('%Y-%m-%d')
    registros = data.get('registros', [])
    
    db = get_db()
    cursor = db.cursor()
    
    for item in registros:
        act_id = item.get('actividad_id')
        completada = 1 if item.get('completada') else 0
        notas = item.get('notas', '')
        
        if not act_id:
            continue
            
        cursor.execute("""
            INSERT INTO activacion_registros (paciente_id, actividad_id, fecha, completada, notas)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(paciente_id, actividad_id, fecha) DO UPDATE SET
                completada = excluded.completada,
                notas = excluded.notas
        """, (patient_id, act_id, fecha, completada, notas))
    db.commit()
    
    try:
        cursor.execute("SELECT nombres, apellidos, psicologo_id FROM pacientes WHERE id = ?", (patient_id,))
        pac = cursor.fetchone()
        if pac:
            pac_nombre = f"{pac['nombres']} {pac['apellidos']}".strip()
            psic_id = pac['psicologo_id'] or 1
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            notif_title = "🏃‍♂️ Activación Conductual Registrada"
            notif_msg = f"El consultante {pac_nombre} completó su checklist diario de activación conductual para el {fecha}."
            cursor.execute("""
                INSERT INTO notificaciones (user_id, tipo, titulo, mensaje, fecha, leida, link)
                VALUES (?, 'herramienta_terapeutica', ?, ?, ?, 0, '/#therapist-tools')
            """, (psic_id, notif_title, notif_msg, now_str))
            db.commit()
            try:
                send_webpush_notification(user_id=psic_id, title=notif_title, body=notif_msg, url="/#therapist-tools")
            except Exception:
                pass
    except Exception as _e:
        print("Error notif activacion:", _e)
        
    return jsonify({'success': True, 'message': 'Registro de activación conductual guardado.'})



@pacientes_bp.route('/api/patient/activation/history', methods=['GET'])
@patient_login_required
def get_patient_activation_history():
    patient_id = session.get('patient_id')
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT ar.*, aa.categoria, aa.nombre_actividad
        FROM activacion_registros ar
        JOIN activacion_actividades aa ON ar.actividad_id = aa.id
        WHERE ar.paciente_id = ?
        ORDER BY ar.fecha DESC, aa.categoria ASC
    """, (patient_id,))
    rows = [dict(r) for r in cursor.fetchall()]
    return jsonify(rows)

# --- RUTAS PORTAL DEL PACIENTE ---



@pacientes_bp.route('/api/patient/food-intake/log', methods=['POST'])
@patient_login_required
def log_patient_food_intake():
    patient_id = session.get('patient_id')
    data = request.json or {}
    fecha = (data.get('fecha') or '').strip() or datetime.now().strftime('%Y-%m-%d %H:%M')
    tipo_comida = (data.get('tipo_comida') or 'Almuerzo').strip()
    descripcion_plato = (data.get('descripcion_plato') or '').strip()
    apetito_previo = int(data.get('apetito_previo', 5))
    saciedad = int(data.get('saciedad', 5))
    contexto = (data.get('contexto') or '').strip()
    afectividad = (data.get('afectividad') or '').strip()
    pensamiento = (data.get('pensamiento') or '').strip()
    import json
    conductas_json = json.dumps(data.get('conductas', []), ensure_ascii=False)

    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        INSERT INTO registros_ingesta (
            paciente_id, fecha, tipo_comida, descripcion_plato,
            apetito_previo, saciedad, contexto, afectividad, pensamiento, conductas_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (patient_id, fecha, tipo_comida, descripcion_plato, apetito_previo, saciedad, contexto, afectividad, pensamiento, conductas_json))
    db.commit()

    # Notificar al psicólogo
    try:
        cursor.execute("SELECT nombres, apellidos, psicologo_id FROM pacientes WHERE id = ?", (patient_id,))
        pac = cursor.fetchone()
        if pac:
            pac_nombre = f"{pac['nombres']} {pac['apellidos']}".strip()
            psic_id = pac['psicologo_id'] or 1
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            notif_title = "🥗 Registro de Ingesta y Apetito"
            notif_msg = f"El consultante {pac_nombre} registró una ingesta ({tipo_comida}) para el {fecha}."
            cursor.execute("""
                INSERT INTO notificaciones (user_id, tipo, titulo, mensaje, fecha, leida, link)
                VALUES (?, 'herramienta_terapeutica', ?, ?, ?, 0, '/#therapist-tools')
            """, (psic_id, notif_title, notif_msg, now_str))
            db.commit()
            try:
                send_webpush_notification(user_id=psic_id, title=notif_title, body=notif_msg, url="/#therapist-tools")
            except Exception:
                pass
    except Exception as _ne:
        print("Error al notificar registro de ingesta:", _ne)

    return jsonify({'success': True, 'message': 'Registro de ingesta guardado exitosamente.'})



@pacientes_bp.route('/api/patient/food-intake/history', methods=['GET'])
@patient_login_required
def get_patient_food_intake_history():
    patient_id = session.get('patient_id')
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM registros_ingesta WHERE paciente_id = ? ORDER BY fecha DESC LIMIT 50", (patient_id,))
    rows = [dict(r) for r in cursor.fetchall()]
    return jsonify(rows)


# --- ENDPOINTS REGISTRO COGNITIVO ---



@pacientes_bp.route('/api/patient/cognitive-record/log', methods=['POST'])
@patient_login_required
def log_patient_cognitive_record():
    patient_id = session.get('patient_id')
    data = request.json or {}
    fecha = (data.get('fecha') or '').strip() or datetime.now().strftime('%Y-%m-%d %H:%M')
    situacion = (data.get('situacion') or '').strip()
    pensamiento = (data.get('pensamiento') or '').strip()
    emocion_sensacion = (data.get('emocion_sensacion') or '').strip()
    intensidad_emocion = int(data.get('intensidad_emocion', 5))
    conducta = (data.get('conducta') or '').strip()

    if not situacion or not pensamiento:
        return jsonify({'error': 'La situación y el pensamiento son requeridos.'}), 400

    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        INSERT INTO registros_cognitivos (
            paciente_id, fecha, situacion, pensamiento, emocion_sensacion, intensidad_emocion, conducta
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (patient_id, fecha, situacion, pensamiento, emocion_sensacion, intensidad_emocion, conducta))
    db.commit()

    # Notificar al psicólogo
    try:
        cursor.execute("SELECT nombres, apellidos, psicologo_id FROM pacientes WHERE id = ?", (patient_id,))
        pac = cursor.fetchone()
        if pac:
            pac_nombre = f"{pac['nombres']} {pac['apellidos']}".strip()
            psic_id = pac['psicologo_id'] or 1
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            notif_title = "🧠 Registro Cognitivo (TCC)"
            notif_msg = f"El consultante {pac_nombre} completó un nuevo registro cognitivo para el {fecha}."
            cursor.execute("""
                INSERT INTO notificaciones (user_id, tipo, titulo, mensaje, fecha, leida, link)
                VALUES (?, 'herramienta_terapeutica', ?, ?, ?, 0, '/#therapist-tools')
            """, (psic_id, notif_title, notif_msg, now_str))
            db.commit()
            try:
                send_webpush_notification(user_id=psic_id, title=notif_title, body=notif_msg, url="/#therapist-tools")
            except Exception:
                pass
    except Exception as _ne:
        print("Error al notificar registro cognitivo:", _ne)

    return jsonify({'success': True, 'message': 'Registro cognitivo guardado exitosamente.'})



@pacientes_bp.route('/api/patient/cognitive-record/history', methods=['GET'])
@patient_login_required
def get_patient_cognitive_record_history():
    patient_id = session.get('patient_id')
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM registros_cognitivos WHERE paciente_id = ? ORDER BY fecha DESC LIMIT 50", (patient_id,))
    rows = [dict(r) for r in cursor.fetchall()]
    return jsonify(rows)


# --- ENDPOINTS CONSUMO DE PANTALLA ---



@pacientes_bp.route('/api/patient/screen-time/log', methods=['POST'])
@patient_login_required
def log_patient_screen_time():
    patient_id = session.get('patient_id')
    data = request.json or {}
    dispositivos = (data.get('dispositivos') or '').strip()
    tiempo_uso = (data.get('tiempo_uso') or '').strip()
    aplicaciones = (data.get('aplicaciones') or '').strip()
    tipo_contenido = (data.get('tipo_contenido') or '').strip()
    estado_emocional = (data.get('estado_emocional_posterior') or '').strip()
    interferencia = (data.get('interferencia_actividad') or '').strip()

    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        INSERT INTO registro_consumo_pantalla (
            paciente_id, dispositivos, tiempo_uso, aplicaciones, tipo_contenido,
            estado_emocional_posterior, interferencia_actividad
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (patient_id, dispositivos, tiempo_uso, aplicaciones, tipo_contenido, estado_emocional, interferencia))
    db.commit()

    # Notificar al psicólogo asignado
    try:
        cursor.execute("SELECT nombres, apellidos, psicologo_id FROM pacientes WHERE id = ?", (patient_id,))
        pac = cursor.fetchone()
        if pac:
            pac_nombre = f"{pac['nombres']} {pac['apellidos']}".strip()
            psic_id = pac['psicologo_id'] or 1
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            notif_title = "📱 Tracker de Consumo de Pantalla"
            notif_msg = f"El consultante {pac_nombre} registró su monitoreo diario de uso de pantalla."
            cursor.execute("""
                INSERT INTO notificaciones (user_id, tipo, titulo, mensaje, fecha, leida, link)
                VALUES (?, 'herramienta_terapeutica', ?, ?, ?, 0, '/#therapist-tools')
            """, (psic_id, notif_title, notif_msg, now_str))
            db.commit()
            try:
                send_webpush_notification(user_id=psic_id, title=notif_title, body=notif_msg, url="/#therapist-tools")
            except Exception:
                pass
    except Exception as _ne:
        print("Error al notificar registro de pantalla:", _ne)

    return jsonify({'success': True, 'message': 'Registro de tiempo de pantalla guardado exitosamente.'})



@pacientes_bp.route('/api/patient/screen-time/history', methods=['GET'])
@patient_login_required
def get_patient_screen_time_history():
    patient_id = session.get('patient_id')
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM registro_consumo_pantalla WHERE paciente_id = ? ORDER BY fecha_registro DESC LIMIT 50", (patient_id,))
    rows = [dict(r) for r in cursor.fetchall()]
    return jsonify(rows)


# =========================================================================
# RUTAS DE BACKEND: EXAMEN MENTAL ESTRUCTURADO (MSE) & EXPORTACIÓN
# =========================================================================

def _ensure_examenes_mentales_table(cursor):
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS examenes_mentales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                psicologo_id INTEGER NOT NULL,
                paciente_id INTEGER NOT NULL,
                fecha_evaluacion TEXT NOT NULL,
                medio_evaluacion TEXT NOT NULL,
                datos_evaluacion_json TEXT NOT NULL,
                observaciones_generales TEXT,
                fecha_registro DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (psicologo_id) REFERENCES usuarios(id) ON DELETE CASCADE,
                FOREIGN KEY (paciente_id) REFERENCES pacientes(id) ON DELETE CASCADE
            )
        """)
    except Exception as _e:
        print("Error en _ensure_examenes_mentales_table:", _e)



