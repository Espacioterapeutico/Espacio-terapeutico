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
from datetime import datetime
from functools import wraps
from flask import Blueprint, request, jsonify, session, g

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
    user_id = session.get('user_id')
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute("SELECT id, nombres, apellidos FROM pacientes WHERE id = ? AND psicologo_id = ?", (patient_id, user_id))
    patient = cursor.fetchone()
    if not patient:
        return jsonify({'error': 'Paciente no encontrado o sin permisos.'}), 404
        
    cursor.execute("SELECT modulo_clave, activo FROM modulos_terapeuticos_paciente WHERE paciente_id = ?", (patient_id,))
    rows = cursor.fetchall()
    active_map = {r['modulo_clave']: r['activo'] for r in rows}
    
    catalog = [
        {'clave': 'sueno', 'nombre': 'Higiene del Sueño', 'activo': active_map.get('sueno', 0)},
        {'clave': 'ansiedad', 'nombre': 'Diario de Ansiedad (Checklist)', 'activo': active_map.get('ansiedad', 0)},
        {'clave': 'sobriedad', 'nombre': 'Registro de Consumo (Días Consecutivos)', 'activo': active_map.get('sobriedad', 0)},
        {'clave': 'pantalla', 'nombre': 'Registro de Consumo de Pantallas (Uso Digital)', 'activo': active_map.get('pantalla', 0)},
        {'clave': 'adherencia', 'nombre': 'Adherencia al Tratamiento (Medicación)', 'activo': active_map.get('adherencia', 0)},
        {'clave': 'activacion', 'nombre': 'Activación Conductual (Tareas Diarias)', 'activo': active_map.get('activacion', 0)},
        {'clave': 'ingesta', 'nombre': 'Ingesta de Alimentos y Apetito', 'activo': active_map.get('ingesta', 0)},
        {'clave': 'cognitivo', 'nombre': 'Registro Cognitivo (TCC)', 'activo': active_map.get('cognitivo', 0)}
    ]
    return jsonify({'patient': dict(patient), 'modules': catalog})

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
    return jsonify(rows)

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
        # Tables may not exist yet - return empty array gracefully
        print(f"[WARN] Error fetching report for {modulo_clave}: {e}")
        return jsonify([])

# --- ENDPOINTS ADHERENCIA AL TRATAMIENTO ---



@herramientas_bp.route('/api/therapist/patients/<int:patient_id>/activation/activities', methods=['GET', 'POST'])
@login_required
def therapist_patient_activation_activities(patient_id):
    user_id = session.get('user_id')
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute("SELECT id FROM pacientes WHERE id = ? AND psicologo_id = ?", (patient_id, user_id))
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


