# -*- coding: utf-8 -*-
"""
Módulo de Evoluciones Clínicas e Historia del Consultante (routes_evoluciones.py)
Encapsula el registro de sesiones terapéuticas (SOAP/Evolución),
ficha resumen del consultante, impresión de historia clínica y ajuste de saldos prepagados.
"""

import os
import json
import sqlite3
import datetime
from functools import wraps
from flask import Blueprint, request, jsonify, session, g, render_template_string

evoluciones_bp = Blueprint('evoluciones', __name__)

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

# ==========================================
# FICHA RESUMEN Y HISTORIAL DEL CONSULTANTE
# ==========================================

@evoluciones_bp.route('/api/patients/<int:patient_id>/summary', methods=['GET'])
@login_required
def get_patient_summary(patient_id):
    db = get_db()
    cursor = db.cursor()
    psic_id = get_psicologo_id_filter()
    
    if psic_id is not None:
        cursor.execute("""
            SELECT id, nombres, apellidos, cedula, edad, genero, pronombre, telefono, email, estado, costo_personalizado, moneda_personalizada, costo_paquete_personalizado, sesiones_paquete_personalizado, residencia_actual, pais, ciudad, diagnostico,
                   fecha_nacimiento, con_quien_reside, antecedentes_medicos_personales, antecedentes_psicologicos_personales
            FROM pacientes WHERE id = ? AND psicologo_id = ?
        """, (patient_id, psic_id))
    else:
        cursor.execute("""
            SELECT id, nombres, apellidos, cedula, edad, genero, pronombre, telefono, email, estado, costo_personalizado, moneda_personalizada, costo_paquete_personalizado, sesiones_paquete_personalizado, residencia_actual, pais, ciudad, diagnostico,
                   fecha_nacimiento, con_quien_reside, antecedentes_medicos_personales, antecedentes_psicologicos_personales
            FROM pacientes WHERE id = ?
        """, (patient_id,))
    patient = cursor.fetchone()
    if not patient:
        return jsonify({'error': 'Paciente no encontrado'}), 404
        
    try:
        from routes_finanzas import auto_settle_patient_debts
        auto_settle_patient_debts(db, patient_id)
    except Exception: pass
        
    cursor.execute("""
        SELECT fecha, modalidad, resumen, observaciones_clinicas, tareas_asignadas, anotaciones_proxima 
        FROM sesiones 
        WHERE paciente_id = ? 
        ORDER BY fecha DESC, id DESC LIMIT 1
    """, (patient_id,))
    last_session = cursor.fetchone()
    
    cursor.execute("""
        SELECT 
            SUM(CASE WHEN estado_pago IN ('Paga', 'Cancelada sin aviso - Paga') THEN cantidad_sesiones ELSE 0 END) as pagas,
            SUM(CASE WHEN estado_pago IN ('Pendiente', 'Cancelada sin aviso') THEN cantidad_sesiones ELSE 0 END) as pendientes,
            SUM(CASE WHEN estado_pago = 'Prepagada' AND control_uso = 'No consumida' THEN cantidad_sesiones ELSE 0 END) as prepagadas_no_consumidas,
            SUM(CASE WHEN (estado_pago = 'Prepagada' AND control_uso = 'Consumida') OR (estado_pago = 'Paga' AND control_uso = 'Consumida') THEN cantidad_sesiones ELSE 0 END) as prepagadas_consumidas
        FROM agenda_finanzas 
        WHERE paciente_id = ?
    """, (patient_id,))
    finance_stats = cursor.fetchone()
    
    cursor.execute("""
        SELECT moneda, SUM(monto) as total
        FROM agenda_finanzas
        WHERE paciente_id = ? AND estado_pago IN ('Pendiente', 'Cancelada sin aviso')
        GROUP BY moneda
    """, (patient_id,))
    deuda_monto_rows = cursor.fetchall()
    deuda_monto_str = ""
    for r in deuda_monto_rows:
        if r['total'] and r['total'] > 0:
            if deuda_monto_str:
                deuda_monto_str += " + "
            deuda_monto_str += f"{r['total']:,.2f} {r['moneda'] or 'USD'}"
    if not deuda_monto_str:
        deuda_monto_str = "0.00 USD"

    cursor.execute("""
        SELECT id, fecha, tipo_consulta, monto, moneda, estado_pago
        FROM agenda_finanzas
        WHERE paciente_id = ? AND estado_pago IN ('Pendiente', 'Cancelada sin aviso')
        ORDER BY fecha DESC, id DESC
    """, (patient_id,))
    deudas_detalle = [dict(row) for row in cursor.fetchall()]
    
    cursor.execute("""
        SELECT estado, COUNT(id) as cnt
        FROM sesiones
        WHERE paciente_id = ?
        GROUP BY estado
    """, (patient_id,))
    session_counts_raw = cursor.fetchall()
    session_counts = {'Realizada': 0, 'Cancelada': 0, 'Reprogramada': 0, 'Agendada': 0}
    for row in session_counts_raw:
        if row['estado'] in session_counts:
            session_counts[row['estado']] = row['cnt']

    patient_dict = dict(patient)
    from app import decrypt_clinical_text
    for k in ['diagnostico', 'antecedentes_medicos_personales', 'antecedentes_psicologicos_personales']:
        if k in patient_dict and patient_dict[k]:
            patient_dict[k] = decrypt_clinical_text(patient_dict[k])
            
    last_session_dict = dict(last_session) if last_session else None
    if last_session_dict:
        for k in ['resumen', 'observaciones_clinicas', 'tareas_asignadas', 'anotaciones_proxima']:
            if k in last_session_dict and last_session_dict[k]:
                last_session_dict[k] = decrypt_clinical_text(last_session_dict[k])

    summary = {
        'patient': patient_dict,
        'last_session': last_session_dict,
        'finance': {
            'pagas': finance_stats['pagas'] or 0,
            'pendientes': finance_stats['pendientes'] or 0,
            'prepagadas_no_consumidas': finance_stats['prepagadas_no_consumidas'] or 0,
            'prepagadas_consumidas': finance_stats['prepagadas_consumidas'] or 0,
            'deuda_monto_str': deuda_monto_str,
            'deudas_detalle': deudas_detalle
        },
        'session_counts': session_counts
    }
    return jsonify(summary)

@evoluciones_bp.route('/api/patients/<int:patient_id>/adjust-prepay-balance', methods=['POST'])
@login_required
def adjust_patient_prepay_balance(patient_id):
    db = get_db()
    cursor = db.cursor()
    psic_id = get_psicologo_id_filter()
    
    if psic_id is not None:
        cursor.execute("SELECT id FROM pacientes WHERE id = ? AND psicologo_id = ?", (patient_id, psic_id))
    else:
        cursor.execute("SELECT id FROM pacientes WHERE id = ?", (patient_id,))
    if not cursor.fetchone():
        return jsonify({'error': 'Paciente no encontrado'}), 404
        
    data = request.json or {}
    nueva_cantidad = data.get('cantidad_disponible')
    if nueva_cantidad is None or not isinstance(nueva_cantidad, int) or nueva_cantidad < 0:
        return jsonify({'error': 'Debes ingresar un número entero válido (>= 0)'}), 400

    cursor.execute("""
        SELECT SUM(cantidad_sesiones) FROM agenda_finanzas 
        WHERE paciente_id = ? AND estado_pago = 'Prepagada' AND control_uso = 'No consumida'
    """, (patient_id,))
    actual_sum = cursor.fetchone()[0] or 0

    if nueva_cantidad == actual_sum:
        return jsonify({'success': True, 'nueva_cantidad': nueva_cantidad, 'message': 'El saldo ya es igual al valor indicado.'})

    if nueva_cantidad < actual_sum:
        diff = actual_sum - nueva_cantidad
        cursor.execute("""
            SELECT id, cantidad_sesiones, control_uso FROM agenda_finanzas
            WHERE paciente_id = ? AND estado_pago = 'Prepagada' AND control_uso = 'No consumida'
            ORDER BY id ASC
        """, (patient_id,))
        rows = cursor.fetchall()
        for r in rows:
            if diff <= 0:
                break
            r_cant = r['cantidad_sesiones'] or 1
            if r_cant <= diff:
                cursor.execute("UPDATE agenda_finanzas SET control_uso = 'Consumida' WHERE id = ?", (r['id'],))
                diff -= r_cant
            else:
                nuevas_ses = r_cant - diff
                cursor.execute("UPDATE agenda_finanzas SET cantidad_sesiones = ? WHERE id = ?", (nuevas_ses, r['id']))
                diff = 0
    else:
        diff = nueva_cantidad - actual_sum
        cursor.execute("""
            SELECT id, cantidad_sesiones FROM agenda_finanzas
            WHERE paciente_id = ? AND estado_pago = 'Prepagada' AND control_uso = 'No consumida'
            ORDER BY id DESC LIMIT 1
        """, (patient_id,))
        last_prep = cursor.fetchone()
        if last_prep:
            cursor.execute("UPDATE agenda_finanzas SET cantidad_sesiones = cantidad_sesiones + ? WHERE id = ?", (diff, last_prep['id']))
        else:
            now_date = datetime.datetime.now().strftime('%Y-%m-%d')
            cursor.execute("""
                INSERT INTO agenda_finanzas (paciente_id, fecha, hora, tipo_consulta, monto, moneda, estado_pago, control_uso, cantidad_sesiones, referencia)
                VALUES (?, ?, '00:00', 'Prepago', 0.0, 'USD', 'Prepagada', 'No consumida', ?, 'Ajuste manual de saldo')
            """, (patient_id, now_date, diff))

    db.commit()
    try:
        from app import sync_patient_to_firebase
        sync_patient_to_firebase(patient_id)
    except Exception as s_err:
        print(f"Error sincronizando prepago a Firebase: {s_err}")
    return jsonify({'success': True, 'nueva_cantidad': nueva_cantidad, 'message': f'Saldo de consultas prepagadas ajustado exitosamente a {nueva_cantidad}.'})

# --- ENDPOINTS DE GESTIÓN DE SESIONES / EVOLUCIONES ---

@evoluciones_bp.route('/api/sessions', methods=['GET', 'POST'])
@login_required
def manage_sessions():
    db = get_db()
    cursor = db.cursor()
    psic_id = get_psicologo_id_filter()
    from app import decrypt_clinical_text, encrypt_clinical_text, sync_patient_to_firebase

    if request.method == 'GET':
        patient_id = request.args.get('patient_id')
        if patient_id:
            if psic_id is not None:
                cursor.execute("""
                    SELECT s.* 
                    FROM sesiones s 
                    JOIN pacientes p ON s.paciente_id = p.id 
                    WHERE s.paciente_id = ? AND p.psicologo_id = ? 
                    ORDER BY s.fecha DESC, s.id DESC
                """, (patient_id, psic_id))
            else:
                cursor.execute("SELECT * FROM sesiones WHERE paciente_id = ? ORDER BY fecha DESC, id DESC", (patient_id,))
        else:
            if psic_id is not None:
                cursor.execute("""
                    SELECT s.*, p.nombres, p.apellidos 
                    FROM sesiones s 
                    JOIN pacientes p ON s.paciente_id = p.id 
                    WHERE p.psicologo_id = ?
                    ORDER BY s.fecha DESC, s.id DESC
                """, (psic_id,))
            else:
                cursor.execute("""
                    SELECT s.*, p.nombres, p.apellidos 
                    FROM sesiones s 
                    JOIN pacientes p ON s.paciente_id = p.id 
                    ORDER BY s.fecha DESC, s.id DESC
                """)
            
        raw_sessions = [dict(row) for row in cursor.fetchall()]
        sessions = []
        for s in raw_sessions:
            s['resumen'] = decrypt_clinical_text(s.get('resumen'))
            s['resumen_paciente'] = decrypt_clinical_text(s.get('resumen_paciente'))
            s['anotaciones_proxima'] = decrypt_clinical_text(s.get('anotaciones_proxima'))
            s['compromisos_psicologo'] = decrypt_clinical_text(s.get('compromisos_psicologo'))
            s['diagnostico'] = decrypt_clinical_text(s.get('diagnostico'))
            s['test_aplicados'] = decrypt_clinical_text(s.get('test_aplicados'))
            sessions.append(s)
        return jsonify(sessions)

    # --- CREAR NUEVA EVOLUCIÓN CLÍNICA (POST) ---
    data = request.json or {}
    try:
        paciente_id = data.get('paciente_id')
        if not paciente_id:
            return jsonify({'error': 'Debe seleccionar un consultante para guardar la evolución.'}), 400

        agenda_id = data.get('agenda_id')
        fecha = data.get('fecha') or datetime.datetime.now().strftime('%Y-%m-%d')
        modalidad = data.get('modalidad', 'Online')
        estado = data.get('estado', 'Realizada')

        resumen = encrypt_clinical_text(data.get('resumen'))
        resumen_paciente = encrypt_clinical_text(data.get('resumen_paciente'))
        tareas_asignadas = data.get('tareas_asignadas', '')
        recursos_entregados = data.get('recursos_entregados', '')
        anotaciones_proxima = encrypt_clinical_text(data.get('anotaciones_proxima'))
        compromisos_psicologo = encrypt_clinical_text(data.get('compromisos_psicologo'))
        diagnostico = encrypt_clinical_text(data.get('diagnostico'))
        test_aplicados = encrypt_clinical_text(data.get('test_aplicados'))
        archivo_adjunto = data.get('archivo_adjunto', '')

        cursor.execute("""
            INSERT INTO sesiones (
                paciente_id, agenda_id, fecha, modalidad, estado,
                resumen, resumen_paciente, tareas_asignadas, recursos_entregados,
                anotaciones_proxima, compromisos_psicologo, diagnostico, test_aplicados, archivo_adjunto
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            paciente_id, agenda_id, fecha, modalidad, estado,
            resumen, resumen_paciente, tareas_asignadas, recursos_entregados,
            anotaciones_proxima, compromisos_psicologo, diagnostico, test_aplicados, archivo_adjunto
        ))
        session_id = cursor.lastrowid

        # Liquidación de finanzas
        tipo_liq = data.get('tipo_liquidacion')
        raw_monto = data.get('monto', 0.0)
        try:
            monto = float(str(raw_monto).replace(',', '.')) if raw_monto is not None else 0.0
        except Exception:
            monto = 0.0

        moneda = data.get('moneda', 'USD')
        metodo_pago = data.get('metodo_pago', '')
        referencia = data.get('referencia', '')
        fecha_pago = data.get('fecha_pago') or fecha

        if agenda_id:
            if tipo_liq in ['Paga', 'Marcar como pagada en esta fecha', 'Pagada', 'Exonerada', 'Exonerar', 'Exonerar pago (Gratuita)']:
                cursor.execute("""
                    UPDATE agenda_finanzas 
                    SET estado_pago = 'Paga', monto = ?, moneda = ?, metodo_pago = ?, referencia = ?, fecha_pago = ?
                    WHERE id = ?
                """, (monto, moneda, metodo_pago, referencia, fecha_pago, agenda_id))
            elif tipo_liq in ['Prepagada', 'Descontar de saldo prepagado', 'Ya prepagada en paquete']:
                cursor.execute("SELECT estado_pago, control_uso FROM agenda_finanzas WHERE id = ?", (agenda_id,))
                orig_state = cursor.fetchone()
                
                cursor.execute("""
                    UPDATE agenda_finanzas 
                    SET estado_pago = 'Prepagada', control_uso = 'Consumida'
                    WHERE id = ?
                """, (agenda_id,))
                
                if orig_state and not (orig_state['estado_pago'] == 'Prepagada' and orig_state['control_uso'] == 'No consumida'):
                    cursor.execute("""
                        SELECT id, cantidad_sesiones FROM agenda_finanzas 
                        WHERE paciente_id = ? AND estado_pago IN ('Prepagada', 'Paga') AND control_uso = 'No consumida'
                        ORDER BY fecha ASC, id ASC LIMIT 1
                    """, (paciente_id,))
                    pkg = cursor.fetchone()
                    if pkg:
                        if pkg['cantidad_sesiones'] > 1:
                            cursor.execute("UPDATE agenda_finanzas SET cantidad_sesiones = ? WHERE id = ?", (pkg['cantidad_sesiones'] - 1, pkg['id']))
                        else:
                            cursor.execute("UPDATE agenda_finanzas SET control_uso = 'Consumida' WHERE id = ?", (pkg['id'],))
            elif tipo_liq in ['Cancelada sin aviso - Paga']:
                cursor.execute("""
                    UPDATE agenda_finanzas 
                    SET estado_pago = 'Cancelada sin aviso - Paga', monto = ?, moneda = ?
                    WHERE id = ?
                """, (monto, moneda, agenda_id))
            elif tipo_liq in ['Cancelada sin aviso']:
                cursor.execute("""
                    UPDATE agenda_finanzas 
                    SET estado_pago = 'Cancelada sin aviso', monto = ?, moneda = ?
                    WHERE id = ?
                """, (monto, moneda, agenda_id))
            else:
                cursor.execute("""
                    UPDATE agenda_finanzas 
                    SET estado_pago = 'Pendiente', monto = ?, moneda = ?
                    WHERE id = ?
                """, (monto, moneda, agenda_id))
        else:
            # Crear entrada en agenda_finanzas si no venía de una cita pre-existente
            estado_pago = 'Pendiente'
            if tipo_liq in ['Paga', 'Marcar como pagada en esta fecha', 'Pagada', 'Exonerada', 'Exonerar', 'Exonerar pago (Gratuita)']:
                estado_pago = 'Paga'
            elif tipo_liq in ['Prepagada', 'Descontar de saldo prepagado', 'Ya prepagada en paquete']:
                estado_pago = 'Prepagada'
            elif tipo_liq in ['Cancelada sin aviso - Paga']:
                estado_pago = 'Cancelada sin aviso - Paga'
            elif tipo_liq in ['Cancelada sin aviso']:
                estado_pago = 'Cancelada sin aviso'

            cursor.execute("""
                INSERT INTO agenda_finanzas (
                    paciente_id, fecha, hora, tipo_consulta, monto, moneda, estado_pago,
                    metodo_pago, referencia, fecha_pago, confirmada, control_uso
                ) VALUES (?, ?, '00:00', ?, ?, ?, ?, ?, ?, ?, 1, 'Consumida')
            """, (paciente_id, fecha, modalidad, monto, moneda, estado_pago, metodo_pago, referencia, fecha_pago))
            
            if estado_pago == 'Prepagada':
                cursor.execute("""
                    SELECT id, cantidad_sesiones FROM agenda_finanzas 
                    WHERE paciente_id = ? AND estado_pago IN ('Prepagada', 'Paga') AND control_uso = 'No consumida'
                    ORDER BY fecha ASC, id ASC LIMIT 1
                """, (paciente_id,))
                pkg = cursor.fetchone()
                if pkg:
                    if pkg['cantidad_sesiones'] > 1:
                        cursor.execute("UPDATE agenda_finanzas SET cantidad_sesiones = ? WHERE id = ?", (pkg['cantidad_sesiones'] - 1, pkg['id']))
                    else:
                        cursor.execute("UPDATE agenda_finanzas SET control_uso = 'Consumida' WHERE id = ?", (pkg['id'],))

        db.commit()

        try:
            from routes_finanzas import auto_settle_patient_debts
            auto_settle_patient_debts(db, paciente_id)
            db.commit()
        except Exception:
            pass

        try:
            sync_patient_to_firebase(paciente_id)
        except Exception as _fb_err:
            print(f"Aviso al sincronizar paciente #{paciente_id} a Firebase: {_fb_err}")

        return jsonify({'success': 'Evolución clínica registrada exitosamente.', 'session_id': session_id}), 201

    except Exception as e:
        db.rollback()
        print(f"Error al guardar evolución clínica: {e}")
        return jsonify({'error': f'Error al guardar evolución clínica: {str(e)}'}), 500

@evoluciones_bp.route('/api/sessions/<int:session_id>', methods=['GET', 'PUT'])
@login_required
def update_session_detail(session_id):
    db = get_db()
    cursor = db.cursor()
    from app import decrypt_clinical_text, encrypt_clinical_text
    
    if request.method == 'GET':
        cursor.execute("SELECT * FROM sesiones WHERE id = ?", (session_id,))
        ses = cursor.fetchone()
        if not ses:
            return jsonify({'error': 'Evolución no encontrada.'}), 404
        s_dict = dict(ses)
        s_dict['resumen'] = decrypt_clinical_text(s_dict.get('resumen'))
        s_dict['resumen_paciente'] = decrypt_clinical_text(s_dict.get('resumen_paciente'))
        s_dict['anotaciones_proxima'] = decrypt_clinical_text(s_dict.get('anotaciones_proxima'))
        s_dict['compromisos_psicologo'] = decrypt_clinical_text(s_dict.get('compromisos_psicologo'))
        s_dict['diagnostico'] = decrypt_clinical_text(s_dict.get('diagnostico'))
        s_dict['test_aplicados'] = decrypt_clinical_text(s_dict.get('test_aplicados'))
        return jsonify(s_dict)
        
    data = request.json or {}
    try:
        cursor.execute("SELECT * FROM sesiones WHERE id = ?", (session_id,))
        ses = cursor.fetchone()
        if not ses:
            return jsonify({'error': 'Evolución no encontrada.'}), 404
            
        estado = data.get('estado', ses['estado'])
        resumen = encrypt_clinical_text(data.get('resumen')) if 'resumen' in data else ses['resumen']
        resumen_paciente = encrypt_clinical_text(data.get('resumen_paciente')) if 'resumen_paciente' in data else ses['resumen_paciente']
        tareas_asignadas = data.get('tareas_asignadas') if 'tareas_asignadas' in data else ses['tareas_asignadas']
        recursos_entregados = data.get('recursos_entregados') if 'recursos_entregados' in data else ses['recursos_entregados']
        anotaciones_proxima = encrypt_clinical_text(data.get('anotaciones_proxima')) if 'anotaciones_proxima' in data else ses['anotaciones_proxima']
        compromisos_psicologo = encrypt_clinical_text(data.get('compromisos_psicologo')) if 'compromisos_psicologo' in data else ses['compromisos_psicologo']
        diagnostico = encrypt_clinical_text(data.get('diagnostico')) if 'diagnostico' in data else ses['diagnostico']
        test_aplicados = encrypt_clinical_text(data.get('test_aplicados')) if 'test_aplicados' in data else ses['test_aplicados']
        archivo_adjunto = data.get('archivo_adjunto') if 'archivo_adjunto' in data else ses['archivo_adjunto']
        
        modalidad = data.get('modalidad', ses['modalidad'])
        fecha = data.get('fecha', ses['fecha'])
        patient_id = data.get('paciente_id', ses['paciente_id'])
        
        cursor.execute("""
            UPDATE sesiones 
            SET estado = ?, resumen = ?, resumen_paciente = ?, tareas_asignadas = ?, recursos_entregados = ?, anotaciones_proxima = ?, compromisos_psicologo = ?,
                diagnostico = ?, test_aplicados = ?, archivo_adjunto = ?, modalidad = ?, fecha = ?, paciente_id = ?
            WHERE id = ?
        """, (estado, resumen, resumen_paciente, tareas_asignadas, recursos_entregados, anotaciones_proxima, compromisos_psicologo, diagnostico, test_aplicados, archivo_adjunto, modalidad, fecha, patient_id, session_id))
        
        db.commit()
        return jsonify({'success': 'Evolución actualizada con éxito.'})
    except Exception as e:
        db.rollback()
        return jsonify({'error': f'Error al actualizar evolución: {str(e)}'}), 500

@evoluciones_bp.route('/api/sessions/<int:session_id>', methods=['DELETE'])
@login_required
def delete_session_detail(session_id):
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("SELECT * FROM sesiones WHERE id = ?", (session_id,))
        ses = cursor.fetchone()
        if not ses:
            return jsonify({'error': 'Evolución no encontrada.'}), 404
            
        agenda_id = ses['agenda_id']
        patient_id = ses['paciente_id']
        
        if agenda_id:
            cursor.execute("""
                UPDATE agenda_finanzas 
                SET estado_pago = 'Agendada', monto = 0.0, metodo_pago = NULL, referencia = NULL, fecha_pago = NULL
                WHERE id = ?
            """, (agenda_id,))
            
        cursor.execute("DELETE FROM sesiones WHERE id = ?", (session_id,))
        db.commit()
        
        try:
            from app import sync_patient_to_firebase
            import threading
            threading.Thread(target=sync_patient_to_firebase, args=(patient_id,)).start()
        except Exception: pass
        
        return jsonify({'success': 'Evolución eliminada con éxito.'})
    except Exception as e:
        db.rollback()
        return jsonify({'error': f'Error al eliminar evolución: {str(e)}'}), 500

@evoluciones_bp.route('/api/sessions/<int:session_id>/remove-attachment', methods=['POST'])
@login_required
def remove_session_attachment(session_id):
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("UPDATE sesiones SET archivo_adjunto = NULL WHERE id = ?", (session_id,))
        db.commit()
        return jsonify({'success': 'Archivo adjunto eliminado con éxito de la evolución.'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
