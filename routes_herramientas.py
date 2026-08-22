# -*- coding: utf-8 -*-
"""
Módulo de Herramientas Terapéuticas Interactivas (routes_herramientas.py)
Encapsula el catálogo y asignación de herramientas terapéuticas para consultantes:
- Higiene del Sueño
- Diario de Ansiedad y Síntomas
- Registro de Consumo y Sobriedad
- Tracker de Tiempo en Pantallas
- Adherencia al Tratamiento Farmacológico
- Activación Conductual
- Ingesta de Alimentos y Apetito
- Registro Cognitivo (TCC)
"""

import os
import json
import sqlite3
import threading
import secrets
from datetime import datetime, timedelta
from functools import wraps
from flask import Blueprint, request, jsonify, session, g, render_template

herramientas_bp = Blueprint('herramientas', __name__)

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

# ==========================================
# RUTAS DE MÓDULOS TERAPÉUTICOS PERSONALIZADOS
# (Sueño, Ansiedad, Sobriedad, Adherencia, Activación, Ingesta, Cognitivo, Pantallas)
# ==========================================

@herramientas_bp.route('/api/patients/<int:patient_id>/modules', methods=['GET'])
@login_required
def get_patient_modules(patient_id):
    import secrets
    from datetime import datetime, timedelta
    user_id = session.get('user_id')
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute("SELECT id, nombres, apellidos, telefono FROM pacientes WHERE id = ? AND psicologo_id = ?", (patient_id, user_id))
    patient = cursor.fetchone()
    if not patient:
        return jsonify({'error': 'Paciente no encontrado o sin permisos.'}), 404
        
    cursor.execute("SELECT modulo_clave, activo FROM modulos_terapeuticos_paciente WHERE paciente_id = ?", (patient_id,))
    rows = cursor.fetchall()
    active_map = {r['modulo_clave']: r['activo'] for r in rows}
    
    host_url = request.host_url.rstrip('/')
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")

    catalog_raw = [
        {'clave': 'sueno', 'nombre': 'Higiene del Sueño'},
        {'clave': 'ansiedad', 'nombre': 'Diario de Ansiedad (Checklist)'},
        {'clave': 'sobriedad', 'nombre': 'Registro de Consumo (Días Consecutivos)'},
        {'clave': 'pantalla', 'nombre': 'Registro de Consumo de Pantallas (Uso Digital)'},
        {'clave': 'adherencia', 'nombre': 'Adherencia al Tratamiento (Medicación)'},
        {'clave': 'activacion', 'nombre': 'Activación Conductual (Tareas Diarias)'},
        {'clave': 'ingesta', 'nombre': 'Ingesta de Alimentos y Apetito'},
        {'clave': 'cognitivo', 'nombre': 'Registro Cognitivo (TCC)'}
    ]

    modules = []
    for m in catalog_raw:
        clave = m['clave']
        activo = active_map.get(clave, 0)
        token_str = None
        link_str = None

        if activo:
            cursor.execute("""
                SELECT token FROM tokens_herramientas 
                WHERE paciente_id = ? AND herramienta_tipo = ? AND usado = 0 
                ORDER BY id DESC LIMIT 1
            """, (patient_id, clave))
            t_row = cursor.fetchone()
            if t_row:
                token_str = t_row['token']
            else:
                token_str = secrets.token_urlsafe(32)
                expiracion = now + timedelta(days=7)
                cursor.execute("""
                    INSERT INTO tokens_herramientas (
                        token, paciente_id, psicologo_id, herramienta_tipo, fecha_programada, fecha_expiracion, usado
                    ) VALUES (?, ?, ?, ?, ?, ?, 0)
                """, (token_str, patient_id, user_id, clave, today_str, expiracion.strftime("%Y-%m-%d %H:%M:%S")))
                db.commit()
            link_str = f"{host_url}/herramienta/directa?token={token_str}"

        m_dict = dict(m)
        m_dict['activo'] = activo
        m_dict['token'] = token_str
        m_dict['link'] = link_str
        modules.append(m_dict)

    return jsonify({'patient': dict(patient), 'modules': modules})

@herramientas_bp.route('/api/patients/<int:patient_id>/modules/toggle', methods=['POST'])
@login_required
def toggle_patient_module(patient_id):
    user_id = session.get('user_id')
    data = request.json or {}
    modulo_clave = data.get('modulo_clave')
    activo = int(data.get('activo', 0))
    
    if not modulo_clave:
        return jsonify({'error': 'Clave de módulo requerida.'}), 400
        
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT id FROM pacientes WHERE id = ? AND psicologo_id = ?", (patient_id, user_id))
    if not cursor.fetchone():
        return jsonify({'error': 'Paciente no encontrado o sin permisos.'}), 404
        
    cursor.execute("""
        INSERT INTO modulos_terapeuticos_paciente (paciente_id, modulo_clave, activo)
        VALUES (?, ?, ?)
        ON CONFLICT(paciente_id, modulo_clave) DO UPDATE SET activo = excluded.activo
    """, (patient_id, modulo_clave, activo))
    db.commit()
    
    try:
        from app import sync_patient_to_firebase, notify_patient_firebase
        threading.Thread(target=sync_patient_to_firebase, args=(patient_id,)).start()
        
        if activo == 1:
            mod_nombres = {
                'sueno': 'Registro de Higiene del Sueño',
                'ansiedad': 'Diario de Ansiedad',
                'sobriedad': 'Registro de Consumo y Sobriedad',
                'adherencia': 'Adherencia a Medicación',
                'activacion': 'Activación Conductual',
                'ingesta': 'Ingesta y Apetito',
                'cognitivo': 'Registro Cognitivo',
                'pantalla': 'Tracker de Pantalla'
            }
            mod_nombre = mod_nombres.get(modulo_clave, modulo_clave.capitalize())
            notify_patient_firebase(
                patient_id,
                "🛠️ Nueva Herramienta Asignada",
                f"Tu psicólogo te ha asignado la herramienta '{mod_nombre}' en tu portal.",
                icon="🛠️"
            )
    except Exception as _fe:
        print("Aviso sync firebase herramientas:", _fe)
    
    return jsonify({'success': True, 'modulo_clave': modulo_clave, 'activo': activo})

@herramientas_bp.route('/api/patient/active-modules', methods=['GET'])
@patient_login_required
def get_patient_active_modules():
    patient_id = session.get('patient_id')
    if not patient_id:
        return jsonify({'error': 'No autenticado'}), 401
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT modulo_clave FROM modulos_terapeuticos_paciente WHERE paciente_id = ? AND activo = 1", (patient_id,))
    active_keys = [r['modulo_clave'] for r in cursor.fetchall()]
    return jsonify({'active_modules': active_keys})

# --- RUTAS DE REGISTRO Y SEGUIMIENTO POR HERRAMIENTA ---

@herramientas_bp.route('/api/patient/sleep/log', methods=['POST'])
@patient_login_required
def log_patient_sleep():
    patient_id = session.get('patient_id')
    data = request.json or {}
    fecha = data.get('fecha') or datetime.now().strftime('%Y-%m-%d')
    
    situaciones_dia = data.get('situaciones_dia', '')
    emociones_dia = data.get('emociones_dia', '')
    proceso_dormir = data.get('proceso_dormir', '')
    hora_dormi = data.get('hora_dormi', '')
    desperto_noche = 1 if data.get('desperto_noche') else 0
    cant_despertares = int(data.get('cant_despertares', 0) or 0)
    hora_desperto = data.get('hora_desperto', '')
    senti_descanso = 1 if data.get('senti_descanso') else 0
    somnolencia_dia = 1 if data.get('somnolencia_dia') else 0
    pesadez_dia = 1 if data.get('pesadez_dia') else 0
    agotamiento_dia = 1 if data.get('agotamiento_dia') else 0
    
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        INSERT INTO registros_sueno (
            paciente_id, fecha, situaciones_dia, emociones_dia, proceso_dormir,
            hora_dormi, desperto_noche, cant_despertares, hora_desperto,
            senti_descanso, somnolencia_dia, pesadez_dia, agotamiento_dia
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(paciente_id, fecha) DO UPDATE SET
            situaciones_dia=excluded.situaciones_dia,
            emociones_dia=excluded.emociones_dia,
            proceso_dormir=excluded.proceso_dormir,
            hora_dormi=excluded.hora_dormi,
            desperto_noche=excluded.desperto_noche,
            cant_despertares=excluded.cant_despertares,
            hora_desperto=excluded.hora_desperto,
            senti_descanso=excluded.senti_descanso,
            somnolencia_dia=excluded.somnolencia_dia,
            pesadez_dia=excluded.pesadez_dia,
            agotamiento_dia=excluded.agotamiento_dia
    """, (
        patient_id, fecha, situaciones_dia, emociones_dia, proceso_dormir,
        hora_dormi, desperto_noche, cant_despertares, hora_desperto,
        senti_descanso, somnolencia_dia, pesadez_dia, agotamiento_dia
    ))
    db.commit()

    try:
        cursor.execute("SELECT nombres, apellidos, psicologo_id FROM pacientes WHERE id = ?", (patient_id,))
        pac = cursor.fetchone()
        if pac:
            pac_nombre = f"{pac['nombres']} {pac['apellidos']}".strip()
            psic_id = pac['psicologo_id'] or 1
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            notif_title = "🌙 Registro de Higiene del Sueño"
            notif_msg = f"El consultante {pac_nombre} completó su registro diario de higiene del sueño para el {fecha}."
            cursor.execute("""
                INSERT INTO notificaciones (user_id, tipo, titulo, mensaje, fecha, leida, link)
                VALUES (?, 'herramienta_terapeutica', ?, ?, ?, 0, '/#therapist-tools')
            """, (psic_id, notif_title, notif_msg, now_str))
            db.commit()
            try:
                from app import send_webpush_notification
                send_webpush_notification(user_id=psic_id, title=notif_title, body=notif_msg, url="/#therapist-tools")
            except Exception: pass
    except Exception as _ne:
        print("Error al notificar registro de sueño:", _ne)

    return jsonify({'success': True, 'message': 'Registro de sueño guardado exitosamente.'})

@herramientas_bp.route('/api/patient/sleep/history', methods=['GET'])
@patient_login_required
def get_patient_sleep_history():
    patient_id = session.get('patient_id')
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM registros_sueno WHERE paciente_id = ? ORDER BY fecha DESC LIMIT 30", (patient_id,))
    rows = [dict(r) for r in cursor.fetchall()]
    return jsonify(rows)

@herramientas_bp.route('/api/patient/anxiety/log', methods=['POST'])
@patient_login_required
def log_patient_anxiety():
    patient_id = session.get('patient_id')
    data = request.json or {}
    fecha = data.get('fecha') or datetime.now().strftime('%Y-%m-%d')
    nivel_ansiedad = int(data.get('nivel_ansiedad', 1) or 1)
    sintomas = data.get('sintomas', [])
    situacion = data.get('situacion_desencadenante', '')
    
    sintomas_json = json.dumps(sintomas)
    
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        INSERT INTO registros_ansiedad (paciente_id, fecha, nivel_ansiedad, sintomas_json, situacion_desencadenante)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(paciente_id, fecha) DO UPDATE SET
            nivel_ansiedad=excluded.nivel_ansiedad,
            sintomas_json=excluded.sintomas_json,
            situacion_desencadenante=excluded.situacion_desencadenante
    """, (patient_id, fecha, nivel_ansiedad, sintomas_json, situacion))
    db.commit()

    try:
        cursor.execute("SELECT nombres, apellidos, psicologo_id FROM pacientes WHERE id = ?", (patient_id,))
        pac = cursor.fetchone()
        if pac:
            pac_nombre = f"{pac['nombres']} {pac['apellidos']}".strip()
            psic_id = pac['psicologo_id'] or 1
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            notif_title = "⚡ Diario de Ansiedad Actualizado"
            notif_msg = f"El consultante {pac_nombre} registró su nivel de ansiedad ({nivel_ansiedad}/10) para el {fecha}."
            cursor.execute("""
                INSERT INTO notificaciones (user_id, tipo, titulo, mensaje, fecha, leida, link)
                VALUES (?, 'herramienta_terapeutica', ?, ?, ?, 0, '/#therapist-tools')
            """, (psic_id, notif_title, notif_msg, now_str))
            db.commit()
            try:
                from app import send_webpush_notification
                send_webpush_notification(user_id=psic_id, title=notif_title, body=notif_msg, url="/#therapist-tools")
            except Exception: pass
    except Exception as _ne:
        print("Error al notificar registro de ansiedad:", _ne)

    return jsonify({'success': True, 'message': 'Registro de ansiedad guardado exitosamente.'})

@herramientas_bp.route('/api/patient/anxiety/history', methods=['GET'])
@patient_login_required
def get_patient_anxiety_history():
    patient_id = session.get('patient_id')
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM registros_ansiedad WHERE paciente_id = ? ORDER BY fecha DESC LIMIT 30", (patient_id,))
    rows = [dict(r) for r in cursor.fetchall()]
    return jsonify(rows)

@herramientas_bp.route('/api/patient/sobriety/checkin', methods=['POST'])
@patient_login_required
def log_patient_sobriety():
    patient_id = session.get('patient_id')
    data = request.json or {}
    fecha = data.get('fecha') or datetime.now().strftime('%Y-%m-%d')
    sobrio = 1 if data.get('sobrio') else 0
    nivel_ansiedad = int(data.get('nivel_ansiedad', 1) or 1)
    disparador = data.get('disparador_emocional', '')
    notas = data.get('notas', '')
    
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        INSERT INTO registros_sobriedad (paciente_id, fecha, sobrio, nivel_ansiedad, disparador_emocional, notas)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(paciente_id, fecha) DO UPDATE SET
            sobrio=excluded.sobrio,
            nivel_ansiedad=excluded.nivel_ansiedad,
            disparador_emocional=excluded.disparador_emocional,
            notas=excluded.notas
    """, (patient_id, fecha, sobrio, nivel_ansiedad, disparador, notas))
    db.commit()
    
    cursor.execute("SELECT fecha, sobrio FROM registros_sobriedad WHERE paciente_id = ? ORDER BY fecha DESC", (patient_id,))
    all_logs = cursor.fetchall()
    streak = 0
    for l in all_logs:
        if l['sobrio'] == 1:
            streak += 1
        else:
            break

    try:
        cursor.execute("SELECT nombres, apellidos, psicologo_id FROM pacientes WHERE id = ?", (patient_id,))
        pac = cursor.fetchone()
        if pac:
            pac_nombre = f"{pac['nombres']} {pac['apellidos']}".strip()
            psic_id = pac['psicologo_id'] or 1
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            status_text = f"Sobrio (Racha: {streak} días)" if sobrio == 1 else "Reporte de recaída / consumo"
            notif_title = "🏅 Tracker de Consumo / Sobriedad"
            notif_msg = f"El consultante {pac_nombre} realizó su check-in: {status_text}."
            cursor.execute("""
                INSERT INTO notificaciones (user_id, tipo, titulo, mensaje, fecha, leida, link)
                VALUES (?, 'herramienta_terapeutica', ?, ?, ?, 0, '/#therapist-tools')
            """, (psic_id, notif_title, notif_msg, now_str))
            db.commit()
            try:
                from app import send_webpush_notification
                send_webpush_notification(user_id=psic_id, title=notif_title, body=notif_msg, url="/#therapist-tools")
            except Exception: pass
    except Exception as _ne:
        print("Error al notificar registro de sobriedad:", _ne)

    return jsonify({'success': True, 'sobrio': sobrio, 'streak': streak, 'message': 'Check-in de sobriedad guardado.'})

@herramientas_bp.route('/api/patient/sobriety/history', methods=['GET'])
@patient_login_required
def get_patient_sobriety_history():
    patient_id = session.get('patient_id')
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM registros_sobriedad WHERE paciente_id = ? ORDER BY fecha DESC", (patient_id,))
    rows = [dict(r) for r in cursor.fetchall()]
    streak = 0
    for l in rows:
        if l.get('sobrio') == 1:
            streak += 1
        else:
            break
    return jsonify({'streak': streak, 'history': rows})

@herramientas_bp.route('/api/therapist/modules/catalog', methods=['GET'])
@login_required
def get_therapist_modules_catalog():
    user_id = session.get('user_id')
    db = get_db()
    cursor = db.cursor()
    
    modules_info = [
        {
            'clave': 'sueno',
            'nombre': 'Registro de Higiene del Sueño',
            'descripcion': 'Cuestionario de 8 ítems diarios para seguimiento del descanso, despertares nocturnos y síntomas de agotamiento.',
            'icono': '🌙'
        },
        {
            'clave': 'ansiedad',
            'nombre': 'Diario de Ansiedad & Síntomas',
            'descripcion': 'Registro en calendario con escala 1-10 y checklist de 11 síntomas físicos y cognitivos.',
            'icono': '⚡'
        },
        {
            'clave': 'sobriedad',
            'nombre': 'Registro de Consumo',
            'descripcion': 'Tracker de seguimiento con contador de días consecutivos sin consumo, medalla de logro y registro de eventos.',
            'icono': '🏅'
        },
        {
            'clave': 'adherencia',
            'nombre': 'Adherencia al Tratamiento (Medicación)',
            'descripcion': 'Seguimiento de dosis y horarios de medicamentos prescritos con checklist y calendario diario.',
            'icono': '💊'
        },
        {
            'clave': 'activacion',
            'nombre': 'Activación Conductual',
            'descripcion': 'Checklist diario de actividades Necesarias, de Disfrute/Placer y Cotidianas/Rutina asignadas por el psicólogo.',
            'icono': '🏃‍♂️'
        },
        {
            'clave': 'ingesta',
            'nombre': 'Ingesta de Alimentos y Apetito',
            'descripcion': 'Registro de comidas (desayuno, almuerzo, merienda, cena), escalas de apetito y saciedad (0-10), contexto, afectividad y conductas.',
            'icono': '🥗'
        },
        {
            'clave': 'cognitivo',
            'nombre': 'Registro Cognitivo',
            'descripcion': 'Reestructuración cognitiva TCC: registro de situación desencadenante, pensamientos automáticos, emoción/sensación (0-10) y conducta realizada.',
            'icono': '🧠'
        },
        {
            'clave': 'pantalla',
            'nombre': 'Tracker de Consumo de Pantalla',
            'descripcion': 'Cuestionario interactivo por chips para monitoreo de tiempo de uso, dispositivos, aplicaciones, contenido, impacto emocional e interferencia.',
            'icono': '📱'
        }
    ]
    
    catalog = []
    
    for mod in modules_info:
        clave = mod['clave']
        try:
            cursor.execute("""
                SELECT mt.paciente_id, p.nombres, p.apellidos, p.cedula
                FROM modulos_terapeuticos_paciente mt
                JOIN pacientes p ON mt.paciente_id = p.id
                WHERE p.psicologo_id = ? AND mt.modulo_clave = ? AND mt.activo = 1
                ORDER BY p.apellidos ASC, p.nombres ASC
            """, (user_id, clave))
            patients_rows = cursor.fetchall()
            
            patients_list = []
            for p_row in patients_rows:
                pid = p_row['paciente_id']
                p_name = f"{p_row['nombres'] or ''} {p_row['apellidos'] or ''}".strip() or f"Consultante #{pid}"
                p_cedula = p_row['cedula'] or ''
                
                metric_text = "Sin registros recientes"
                
                if clave == 'sueno':
                    cursor.execute("""
                        SELECT hora_dormi, hora_desperto, senti_descanso, fecha
                        FROM registros_sueno
                        WHERE paciente_id = ?
                        ORDER BY fecha DESC, id DESC LIMIT 1
                    """, (pid,))
                    r = cursor.fetchone()
                    if r:
                        desc_str = "Reparador" if r['senti_descanso'] == 1 else "No reparador"
                        horario = f"{r['hora_dormi'] or ''} - {r['hora_desperto'] or ''}".strip(' -')
                        metric_text = f"🌙 Último descanso: {horario or desc_str} ({desc_str})"
                
                elif clave == 'ansiedad':
                    cursor.execute("""
                        SELECT nivel_ansiedad, sintomas_json, fecha
                        FROM registros_ansiedad
                        WHERE paciente_id = ?
                        ORDER BY fecha DESC, id DESC LIMIT 1
                    """, (pid,))
                    r = cursor.fetchone()
                    if r:
                        sintomas_count = 0
                        try:
                            sintomas_count = len(json.loads(r['sintomas_json'] or '[]'))
                        except Exception:
                            pass
                        metric_text = f"📊 Última Ansiedad: {r['nivel_ansiedad']}/10 | ⚠️ Síntomas: {sintomas_count}"
                
                elif clave == 'sobriedad':
                    cursor.execute("""
                        SELECT sobrio, nivel_ansiedad, fecha
                        FROM registros_sobriedad
                        WHERE paciente_id = ?
                        ORDER BY fecha DESC, id DESC LIMIT 1
                    """, (pid,))
                    r = cursor.fetchone()
                    if r:
                        estado = "Sobrio 🟢" if r['sobrio'] == 1 else "Recaída/Evento ⚠️"
                        craving = f" | 📈 Craving: {r['nivel_ansiedad']}/10" if r['nivel_ansiedad'] is not None else ""
                        metric_text = f"🏅 Estado: {estado}{craving}"
                
                elif clave == 'adherencia':
                    cursor.execute("""
                        SELECT ar.tomado, ar.fecha, am.nombre_medicamento
                        FROM adherencia_registros ar
                        JOIN adherencia_medicamentos am ON ar.medicamento_id = am.id
                        WHERE ar.paciente_id = ?
                        ORDER BY ar.fecha DESC, ar.id DESC LIMIT 1
                    """, (pid,))
                    r = cursor.fetchone()
                    if r:
                        tomado_str = "Tomado 🟢" if r['tomado'] == 1 else "Pendiente/No tomado 🔴"
                        metric_text = f"⏰ Última Toma: {r['nombre_medicamento']} - {tomado_str}"
                
                elif clave == 'activacion':
                    cursor.execute("""
                        SELECT COUNT(*) as total FROM activacion_actividades WHERE paciente_id = ? AND activa = 1
                    """, (pid,))
                    total_act = cursor.fetchone()['total']
                    cursor.execute("""
                        SELECT COUNT(*) as completadas FROM activacion_registros WHERE paciente_id = ? AND completada = 1
                    """, (pid,))
                    comp_act = cursor.fetchone()['completadas']
                    metric_text = f"✅ Actividades: {comp_act} completadas (Total activas: {total_act})"
                
                elif clave == 'ingesta':
                    cursor.execute("""
                        SELECT tipo_comida, apetito_previo, saciedad, fecha
                        FROM registros_ingesta
                        WHERE paciente_id = ?
                        ORDER BY fecha DESC, id DESC LIMIT 1
                    """, (pid,))
                    r = cursor.fetchone()
                    if r:
                        metric_text = f"🥗 Última Comida: {r['tipo_comida']} | Apetito: {r['apetito_previo'] or 0}/10 | Saciedad: {r['saciedad'] or 0}/10"

                elif clave == 'cognitivo':
                    cursor.execute("""
                        SELECT pensamiento, emocion_sensacion, intensidad_emocion, fecha
                        FROM registros_cognitivos
                        WHERE paciente_id = ?
                        ORDER BY fecha DESC, id DESC LIMIT 1
                    """, (pid,))
                    r = cursor.fetchone()
                    if r:
                        pens = (r['pensamiento'] or '')[:30]
                        metric_text = f"🧠 Último Registro: \"{pens}...\" | Emoción: {r['emocion_sensacion'] or 'N/A'} ({r['intensidad_emocion'] or 0}/10)"

                patients_list.append({
                    'patient_id': pid,
                    'nombre_paciente': p_name,
                    'cedula': p_cedula,
                    'metric_text': metric_text
                })
            
            catalog.append({
                'clave': clave,
                'nombre': mod['nombre'],
                'descripcion': mod['descripcion'],
                'icono': mod['icono'],
                'activos': len(patients_list),
                'pacientes': patients_list
            })
            
        except Exception as e:
            print(f"[WARN] Error loading accordion for module {clave}: {e}")
            catalog.append({
                'clave': clave,
                'nombre': mod['nombre'],
                'descripcion': mod['descripcion'],
                'icono': mod['icono'],
                'activos': 0,
                'pacientes': []
            })
            
    return jsonify(catalog)


# --- RUTAS MIGRADAS AUTOMÁTICAMENTE DE AUDITORÍA ---

@herramientas_bp.route('/api/therapist/modules/report/<string:modulo_clave>', methods=['GET'])
@login_required
def get_therapist_module_report(modulo_clave):
    user_id = session.get('user_id')
    db = get_db()
    cursor = db.cursor()
    
    if modulo_clave in ('consumo', 'sobriedad'):
        modulo_clave = 'sobriedad'
    elif modulo_clave in ('medicacion', 'adherencia'):
        modulo_clave = 'adherencia'



    try:
        if modulo_clave == 'sueno':
            cursor.execute("""
                SELECT rs.*, p.nombres, p.apellidos, p.cedula
                FROM registros_sueno rs
                JOIN pacientes p ON rs.paciente_id = p.id
                WHERE p.psicologo_id = ?
                ORDER BY rs.fecha DESC LIMIT 100
            """, (user_id,))
        elif modulo_clave == 'ansiedad':
            cursor.execute("""
                SELECT ra.*, p.nombres, p.apellidos, p.cedula
                FROM registros_ansiedad ra
                JOIN pacientes p ON ra.paciente_id = p.id
                WHERE p.psicologo_id = ?
                ORDER BY ra.fecha DESC LIMIT 100
            """, (user_id,))
        elif modulo_clave == 'sobriedad':
            cursor.execute("""
                SELECT rsob.*, p.nombres, p.apellidos, p.cedula
                FROM registros_sobriedad rsob
                JOIN pacientes p ON rsob.paciente_id = p.id
                WHERE p.psicologo_id = ?
                ORDER BY rsob.fecha DESC LIMIT 100
            """, (user_id,))
        elif modulo_clave == 'adherencia':
            cursor.execute("""
                SELECT ar.*, am.nombre_medicamento, am.dosis, am.hora_prescrita, p.nombres, p.apellidos, p.cedula
                FROM adherencia_registros ar
                JOIN adherencia_medicamentos am ON ar.medicamento_id = am.id
                JOIN pacientes p ON ar.paciente_id = p.id
                WHERE p.psicologo_id = ?
                ORDER BY ar.fecha DESC LIMIT 100
            """, (user_id,))
        elif modulo_clave == 'activacion':
            cursor.execute("""
                SELECT actr.*, aa.categoria, aa.nombre_actividad, p.nombres, p.apellidos, p.cedula
                FROM activacion_registros actr
                JOIN activacion_actividades aa ON actr.actividad_id = aa.id
                JOIN pacientes p ON actr.paciente_id = p.id
                WHERE p.psicologo_id = ?
                ORDER BY actr.fecha DESC LIMIT 100
            """, (user_id,))
        elif modulo_clave == 'ingesta':
            cursor.execute("""
                SELECT ring.*, p.nombres, p.apellidos, p.cedula
                FROM registros_ingesta ring
                JOIN pacientes p ON ring.paciente_id = p.id
                WHERE p.psicologo_id = ?
                ORDER BY ring.fecha DESC LIMIT 100
            """, (user_id,))
        elif modulo_clave == 'cognitivo':
            cursor.execute("""
                SELECT rcog.*, p.nombres, p.apellidos, p.cedula
                FROM registros_cognitivos rcog
                JOIN pacientes p ON rcog.paciente_id = p.id
                WHERE p.psicologo_id = ?
                ORDER BY rcog.fecha DESC LIMIT 100
            """, (user_id,))
        elif modulo_clave == 'pantalla':
            cursor.execute("""
                SELECT cp.*, p.nombres, p.apellidos, p.cedula
                FROM registro_consumo_pantalla cp
                JOIN pacientes p ON cp.paciente_id = p.id
                WHERE p.psicologo_id = ?
                ORDER BY cp.fecha_registro DESC LIMIT 100
            """, (user_id,))
        else:
            return jsonify({'error': 'Módulo desconocido'}), 400

        rows = [dict(r) for r in cursor.fetchall()]
        return jsonify(rows)
    except Exception as e:
        print(f"[WARN] Error fetching report for {modulo_clave}: {e}")
        return jsonify([])


@herramientas_bp.route('/api/herramientas/consumo-pantalla', methods=['POST'])
def api_log_consumo_pantalla():
    try:
        from routes_pacientes import log_patient_screen_time
        return log_patient_screen_time()
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@herramientas_bp.route('/api/herramientas/consumo-pantalla/<int:patient_id>', methods=['GET'])
def api_get_consumo_pantalla(patient_id):
    try:
        from routes_pacientes import get_patient_screen_time_history
        return get_patient_screen_time_history()
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@herramientas_bp.route('/api/therapist/patients/<int:patient_id>/activation/activities', methods=['GET', 'POST'])
@herramientas_bp.route('/api/therapist/activation/activities/<int:patient_id>', methods=['GET', 'POST'])
@herramientas_bp.route('/api/therapist/activation/activities', methods=['GET', 'POST'])
@login_required
def therapist_patient_activation_activities(patient_id=None):
    if not patient_id:
        patient_id = request.args.get('patient_id') or session.get('last_viewed_patient_id') or 1
    patient_id = int(patient_id)
    user_id = session.get('user_id')
    psic_filter = get_psicologo_id_filter()
    db = get_db()
    cursor = db.cursor()
    
    if psic_filter is not None and psic_filter != -1:
        cursor.execute("SELECT id FROM pacientes WHERE id = ? AND (psicologo_id = ? OR psicologo_id IS NULL OR ? = 1)", (patient_id, psic_filter, psic_filter))
    else:
        cursor.execute("SELECT id FROM pacientes WHERE id = ?", (patient_id,))
        
    if not cursor.fetchone():
        return jsonify({'error': 'Paciente no encontrado o sin permisos.'}), 404
        
    if request.method == 'POST':
        data = request.json or {}
        categoria = data.get('categoria', 'necesaria')
        nombre_actividad = (data.get('nombre_actividad') or '').strip()
        activa = 1 if data.get('activa', True) else 0
        
        if not nombre_actividad:
            return jsonify({'error': 'Nombre de actividad es requerido.'}), 400
            
        cursor.execute("""
            INSERT INTO activacion_actividades (paciente_id, psicologo_id, categoria, nombre_actividad, activa)
            VALUES (?, ?, ?, ?, ?)
        """, (patient_id, user_id, categoria, nombre_actividad, activa))
        db.commit()
        act_id = cursor.lastrowid
        return jsonify({'success': True, 'activity': {'id': act_id, 'categoria': categoria, 'nombre_actividad': nombre_actividad, 'activa': activa}})
        
    cursor.execute("SELECT * FROM activacion_actividades WHERE paciente_id = ? ORDER BY categoria ASC, id ASC", (patient_id,))
    rows = [dict(r) for r in cursor.fetchall()]
    return jsonify(rows)


@herramientas_bp.route('/api/therapist/activation/activities/<int:act_id>/toggle', methods=['POST'])
@login_required
def toggle_activation_activity(act_id):
    data = request.json or {}
    activa = 1 if data.get('activa') else 0
    db = get_db()
    cursor = db.cursor()
    cursor.execute("UPDATE activacion_actividades SET activa = ? WHERE id = ?", (activa, act_id))
    db.commit()
    return jsonify({'success': True, 'activa': activa})


# =========================================================================
# RUTAS Y SERVICIOS: ACCESO DIRECTO POR WHATSAPP (SIN LOGIN) Y COLA AUTOMÁTICA
# =========================================================================

TOOL_NAMES = {
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

def clean_phone_number(phone_str):
    if not phone_str:
        return ""
    digits = "".join([c for c in phone_str if c.isdigit()])
    if digits.startswith("0"):
        digits = "58" + digits[1:]
    elif not (digits.startswith("58") or digits.startswith("54") or digits.startswith("57") or digits.startswith("34") or digits.startswith("1")):
        digits = "58" + digits
    return digits

@herramientas_bp.route('/api/herramientas/generar-link-directo', methods=['POST'])
@login_required
def generar_link_directo_herramienta():
    import urllib.parse
    data = request.json or {}
    patient_id = data.get('patient_id')
    herramienta_tipo = (data.get('herramienta_tipo') or 'pantalla').strip().lower()
    
    if not patient_id:
        return jsonify({'error': 'ID de paciente es requerido.'}), 400
        
    user_id = session.get('user_id')
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute("SELECT id, nombres, apellidos, telefono FROM pacientes WHERE id = ?", (patient_id,))
    paciente = cursor.fetchone()
    if not paciente:
        return jsonify({'error': 'Paciente no encontrado.'}), 404
        
    token = secrets.token_urlsafe(32)
    now = datetime.now()
    expiracion = now + timedelta(days=3)
    today_str = now.strftime("%Y-%m-%d")
    
    # Crear token de único uso
    cursor.execute("""
        INSERT INTO tokens_herramientas (
            token, paciente_id, psicologo_id, herramienta_tipo, fecha_programada, fecha_expiracion, usado
        ) VALUES (?, ?, ?, ?, ?, ?, 0)
    """, (token, patient_id, user_id, herramienta_tipo, today_str, expiracion.strftime("%Y-%m-%d %H:%M:%S")))
    token_id = cursor.lastrowid
    
    # Registrar/Actualizar estado en la cola de envíos de hoy
    cursor.execute("""
        INSERT INTO cola_recordatorios_herramientas (
            psicologo_id, paciente_id, herramienta_tipo, fecha_programada, hora_programada, estado, enviado, fecha_envio, token_id
        ) VALUES (?, ?, ?, ?, '20:00', 'enviado', 1, ?, ?)
        ON CONFLICT(paciente_id, herramienta_tipo, fecha_programada) DO UPDATE SET
            estado = 'enviado', enviado = 1, fecha_envio = ?, token_id = ?
    """, (user_id, patient_id, herramienta_tipo, today_str, now.strftime("%Y-%m-%d %H:%M:%S"), token_id, now.strftime("%Y-%m-%d %H:%M:%S"), token_id))
    db.commit()
    
    # Construir enlace absoluto
    host_url = request.host_url.rstrip('/')
    link_directo = f"{host_url}/herramienta/directa?token={token}"
    
    pac_nombre = f"{paciente['nombres']} {paciente['apellidos']}".strip()
    nombre_tool = TOOL_NAMES.get(herramienta_tipo, 'Herramienta Terapéutica')
    
    mensaje_wa = (
        f"Hola *{paciente['nombres']}* 👋 Espero te encuentres muy bien.\n\n"
        f"Te recuerdo completar tu *{nombre_tool}* del día de hoy. "
        f"Puedes llenarlo directamente haciendo clic aquí (sin iniciar sesión):\n"
        f"👉 {link_directo}\n\n"
        f"¡Gracias por tu compromiso con el proceso terapéutico!"
    )
    
    clean_phone = clean_phone_number(paciente['telefono'])
    wa_url = f"https://wa.me/{clean_phone}?text={urllib.parse.quote(mensaje_wa)}" if clean_phone else ""
    
    return jsonify({
        'success': True,
        'token': token,
        'link': link_directo,
        'mensaje_wa': mensaje_wa,
        'phone': paciente['telefono'],
        'clean_phone': clean_phone,
        'wa_url': wa_url
    })

@herramientas_bp.route('/api/herramientas/programar-recordatorio', methods=['POST'])
@login_required
def programar_recordatorio_herramienta():
    data = request.json or {}
    patient_id = data.get('patient_id')
    herramienta_tipo = (data.get('herramienta_tipo') or 'pantalla').strip().lower()
    hora = (data.get('hora_programada') or '20:00').strip()
    pausado = 1 if data.get('pausado') else 0
    
    if not patient_id:
        return jsonify({'error': 'ID de paciente requerido.'}), 400
        
    user_id = session.get('user_id')
    db = get_db()
    cursor = db.cursor()
    
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    cursor.execute("""
        INSERT INTO cola_recordatorios_herramientas (
            psicologo_id, paciente_id, herramienta_tipo, fecha_programada, hora_programada, estado, enviado, pausado
        ) VALUES (?, ?, ?, ?, ?, 'programado', 0, ?)
        ON CONFLICT(paciente_id, herramienta_tipo, fecha_programada) DO UPDATE SET
            hora_programada = ?, pausado = ?
    """, (user_id, patient_id, herramienta_tipo, today_str, hora, pausado, hora, pausado))
    db.commit()
    
    return jsonify({
        'success': True,
        'message': f'Recordatorio diario para {TOOL_NAMES.get(herramienta_tipo, "Herramienta")} fijado para las {hora}.',
        'pausado': pausado
    })

@herramientas_bp.route('/api/herramientas/estado-cola/<int:patient_id>', methods=['GET'])
@login_required
def get_estado_cola_herramientas(patient_id):
    db = get_db()
    cursor = db.cursor()
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    cursor.execute("""
        SELECT c.*, t.usado, t.fecha_completado
        FROM cola_recordatorios_herramientas c
        LEFT JOIN tokens_herramientas t ON c.token_id = t.id
        WHERE c.paciente_id = ? AND c.fecha_programada = ?
    """, (patient_id, today_str))
    rows = [dict(r) for r in cursor.fetchall()]
    return jsonify(rows)

@herramientas_bp.route('/herramienta/directa', methods=['GET'])
def render_public_tool_page():
    token_str = request.args.get('token', '').strip()
    if not token_str:
        return render_template('public_tool.html', error_msg="Enlace no válido. Falta el token de acceso.")
        
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT t.*, p.nombres, p.apellidos, u.nombres as psic_nombres, u.apellidos as psic_apellidos
        FROM tokens_herramientas t
        JOIN pacientes p ON t.paciente_id = p.id
        LEFT JOIN usuarios u ON t.psicologo_id = u.id
        WHERE t.token = ?
    """, (token_str,))
    token_row = cursor.fetchone()
    
    if not token_row:
        return render_template('public_tool.html', error_msg="El enlace no es válido o ha sido eliminado.")
        
    t_dict = dict(token_row)
    
    if t_dict.get('usado') == 2:
        return render_template('public_tool.html', error_msg="Esta consulta o herramienta ha sido cancelada o ya no está disponible.")

    if t_dict.get('usado') == 1:
        return render_template('public_tool.html', 
                               already_used=True, 
                               patient_name=t_dict['nombres'],
                               completed_at=t_dict.get('fecha_completado') or t_dict.get('fecha_registro'),
                               tool_title=TOOL_NAMES.get(t_dict['herramienta_tipo'], 'Herramienta Terapéutica'))
                               
    # Cargar medicamentos o actividades si la herramienta lo requiere
    extra_data = {}
    if t_dict['herramienta_tipo'] == 'adherencia':
        cursor.execute("SELECT id, nombre_medicamento, dosis, hora_prescrita FROM adherencia_medicamentos WHERE paciente_id = ?", (t_dict['paciente_id'],))
        extra_data['medicamentos'] = [dict(r) for r in cursor.fetchall()]
    elif t_dict['herramienta_tipo'] == 'activacion':
        cursor.execute("SELECT id, categoria, nombre_actividad FROM activacion_actividades WHERE paciente_id = ? AND activa = 1", (t_dict['paciente_id'],))
        extra_data['actividades'] = [dict(r) for r in cursor.fetchall()]

    return render_template('public_tool.html',
                           valid_tool=True,
                           token=token_str,
                           patient_name=t_dict['nombres'],
                           therapist_name=f"Psic. {t_dict.get('psic_nombres') or ''} {t_dict.get('psic_apellidos') or ''}".strip(),
                           tool_type=t_dict['herramienta_tipo'],
                           tool_title=TOOL_NAMES.get(t_dict['herramienta_tipo'], 'Herramienta Terapéutica'),
                           extra_data=extra_data)

@herramientas_bp.route('/api/public/herramienta/guardar', methods=['POST'])
def save_public_tool_submission():
    data = request.json or {}
    token_str = (data.get('token') or '').strip()
    payload = data.get('payload') or {}
    
    if not token_str or not payload:
        return jsonify({'error': 'Token y datos del formulario son obligatorios.'}), 400
        
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM tokens_herramientas WHERE token = ?", (token_str,))
    token_row = cursor.fetchone()
    
    if not token_row:
        return jsonify({'error': 'Token no encontrado.'}), 404
        
    t = dict(token_row)
    if t.get('usado') == 1:
        return jsonify({'error': 'Este enlace ya fue utilizado anteriormente.'}), 400
        
    patient_id = t['paciente_id']
    psic_id = t['psicologo_id']
    tool_type = t['herramienta_tipo']
    now_dt = datetime.now()
    now_str = now_dt.strftime("%Y-%m-%d %H:%M:%S")
    today_str = now_dt.strftime("%Y-%m-%d")
    
    # 1. Guardar según tipo de herramienta
    if tool_type == 'pantalla':
        dispositivos = json.dumps(payload.get('dispositivos', []))
        tiempo_uso = payload.get('tiempo_uso', '0')
        aplicaciones = payload.get('aplicaciones', '')
        tipo_contenido = payload.get('tipo_contenido', '')
        estado_emocional = payload.get('estado_emocional_posterior', '')
        interferencia = payload.get('interferencia_actividad', '')
        cursor.execute("""
            INSERT INTO registro_consumo_pantalla (
                paciente_id, dispositivos, tiempo_uso, aplicaciones, tipo_contenido,
                estado_emocional_posterior, interferencia_actividad, fecha_registro
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (patient_id, dispositivos, tiempo_uso, aplicaciones, tipo_contenido, estado_emocional, interferencia, now_str))

    elif tool_type == 'cognitivo':
        cursor.execute("""
            INSERT INTO registros_cognitivos (
                paciente_id, fecha, situacion, pensamiento, emocion_sensacion, intensidad_emocion, conducta, fecha_registro
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (patient_id, today_str, payload.get('situacion', ''), payload.get('pensamiento', ''), payload.get('emocion_sensacion', ''), payload.get('intensidad_emocion', 5), payload.get('conducta', ''), now_str))

    elif tool_type == 'ingesta':
        cursor.execute("""
            INSERT INTO registros_ingesta (
                paciente_id, fecha, tipo_comida, descripcion_plato, apetito_previo, saciedad, contexto, afectividad, pensamiento, conductas_json, fecha_registro
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (patient_id, today_str, payload.get('tipo_comida', 'Almuerzo'), payload.get('descripcion_plato', ''), payload.get('apetito_previo', 3), payload.get('saciedad', 3), payload.get('contexto', ''), payload.get('afectividad', ''), payload.get('pensamiento', ''), json.dumps(payload.get('conductas', [])), now_str))

    elif tool_type == 'activacion':
        for act in payload.get('actividades_log', []):
            cursor.execute("""
                INSERT INTO activacion_registros (paciente_id, activacion_id, fecha, completada, notas, fecha_registro)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (patient_id, act.get('id'), today_str, 1 if act.get('completada') else 0, act.get('notas', ''), now_str))

    elif tool_type == 'adherencia':
        for med in payload.get('medicamentos_log', []):
            cursor.execute("""
                INSERT INTO adherencia_registros (paciente_id, medicamento_id, fecha, tomado, hora_tomado, notas, fecha_registro)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (patient_id, med.get('id'), today_str, 1 if med.get('tomado') else 0, med.get('hora_tomado', ''), med.get('notas', ''), now_str))

    elif tool_type == 'pizarra':
        cursor.execute("""
            INSERT INTO pizarra_terapeutica (paciente_id, tipo_autor, nota_texto, estado_animo, fecha_registro, leida_psicologo)
            VALUES (?, 'paciente', ?, ?, ?, 0)
        """, (patient_id, payload.get('nota_texto', ''), payload.get('estado_animo', 'neutral'), now_str))

    # 2. Marcar Token como Usado
    cursor.execute("""
        UPDATE tokens_herramientas SET usado = 1, fecha_completado = ? WHERE id = ?
    """, (now_str, t['id']))
    
    cursor.execute("""
        UPDATE cola_recordatorios_herramientas SET estado = 'completado' WHERE token_id = ?
    """, (t['id'],))
    
    db.commit()

    # 3. Notificar al Psicólogo Asignado
    try:
        cursor.execute("SELECT nombres, apellidos FROM pacientes WHERE id = ?", (patient_id,))
        pac = cursor.fetchone()
        pac_nombre = f"{pac['nombres']} {pac['apellidos']}".strip() if pac else "Consultante"
        nombre_tool = TOOL_NAMES.get(tool_type, 'Herramienta Terapéutica')
        
        notif_title = f"📱 {nombre_tool} Completado"
        notif_msg = f"El consultante {pac_nombre} completó su registro diario de {nombre_tool} mediante enlace directo de WhatsApp."
        
        cursor.execute("""
            INSERT INTO notificaciones (user_id, tipo, titulo, mensaje, fecha, leida, link)
            VALUES (?, 'herramienta_terapeutica', ?, ?, ?, 0, '/#therapist-tools')
        """, (psic_id, notif_title, notif_msg, now_str))
        db.commit()
        
        try:
            from routes_notificaciones import send_webpush_notification
            send_webpush_notification(user_id=psic_id, title=notif_title, body=notif_msg, url="/#therapist-tools")
        except Exception:
            pass
    except Exception as _ne:
        print("Error en notificación de envío público:", _ne)

    return jsonify({'success': True, 'message': 'Registro guardado exitosamente.'})
