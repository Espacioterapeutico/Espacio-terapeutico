# -*- coding: utf-8 -*-
"""
Módulo de Finanzas, Honorarios y Cobros (routes_finanzas.py)
Encapsula la gestión de ingresos, conciliación automática de deudas de pacientes,
abonos rápidos, configuración de honorarios personalizados por consultante y liquidaciones de pagos.
"""

import os
import json
import sqlite3
import datetime
from functools import wraps
from flask import Blueprint, request, jsonify, session, g

finanzas_bp = Blueprint('finanzas', __name__)

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

def auto_settle_patient_debts(db, patient_id):
    """
    Auto-liquidación de deudas del paciente utilizando sus saldos a favor o sesiones de paquetes prepagados.
    """
    if not patient_id:
        return
    cursor = db.cursor()
    
    cursor.execute("""
        SELECT id, estado_pago, monto, tipo_consulta, referencia 
        FROM agenda_finanzas 
        WHERE paciente_id = ? AND estado_pago IN ('Pendiente', 'Cancelada sin aviso')
          AND (tipo_consulta IS NULL OR tipo_consulta NOT LIKE '%Fraccionad%')
          AND (referencia IS NULL OR referencia NOT LIKE '%pago parcial%')
        ORDER BY fecha ASC, id ASC
    """, (patient_id,))
    debts = cursor.fetchall()
    
    if not debts:
        return
        
    for debt in debts:
        cursor.execute("""
            SELECT id, cantidad_sesiones 
            FROM agenda_finanzas 
            WHERE paciente_id = ? AND estado_pago IN ('Prepagada', 'Paga') AND control_uso = 'No consumida'
              AND id != ?
            ORDER BY fecha ASC, id ASC LIMIT 1
        """, (patient_id, debt['id']))
        pkg = cursor.fetchone()
        if not pkg:
            break
            
        debt_id = debt['id']
        debt_status = debt['estado_pago']
        new_status = 'Cancelada sin aviso - Paga' if debt_status == 'Cancelada sin aviso' else 'Paga'
        
        pkg_id = pkg['id']
        pkg_cant = pkg['cantidad_sesiones']
        if pkg_cant > 1:
            cursor.execute("UPDATE agenda_finanzas SET cantidad_sesiones = ? WHERE id = ?", (pkg_cant - 1, pkg_id))
        else:
            cursor.execute("UPDATE agenda_finanzas SET control_uso = 'Consumida' WHERE id = ?", (pkg_id,))
            
        cursor.execute("""
            UPDATE agenda_finanzas 
            SET estado_pago = ?, control_uso = 'No consumida', monto = 0.0,
                metodo_pago = 'Descontado de Prepago', referencia = 'Prepago',
                fecha_liquidacion = datetime('now', 'localtime')
            WHERE id = ?
        """, (new_status, debt_id))
        
    db.commit()

# --- RUTAS DE API FINANCIERA ---

@finanzas_bp.route('/api/agenda/quick-pay', methods=['POST'])
@login_required
def agenda_quick_pay():
    """Registra un pago o abono directo y lo vincula a la cita del paciente."""
    data = request.json or {}
    db = get_db()
    cursor = db.cursor()

    paciente_id = data.get('paciente_id')
    if not paciente_id:
        return jsonify({'error': 'Paciente requerido.'}), 400

    monto           = float(data.get('monto', 0.0) or 0.0)
    moneda          = data.get('moneda', 'USD')
    tipo_consulta   = data.get('tipo_consulta', 'Individual')
    estado_pago     = data.get('estado_pago', 'Paga')
    cantidad_ses    = int(data.get('cantidad_sesiones', 1) or 1)
    referencia      = data.get('referencia', '')
    metodo_pago     = data.get('metodo_pago', 'Efectivo')
    fecha           = data.get('fecha') or datetime.datetime.now().strftime('%Y-%m-%d')
    fecha_pago      = data.get('fecha_pago') or fecha
    hora            = data.get('hora', '00:00')

    try:
        # 1. Si el paciente tiene una cita agendada pendiente, actualizar dicha cita
        cursor.execute("""
            SELECT id FROM agenda_finanzas
            WHERE paciente_id = ? AND estado_pago = 'Pendiente'
            ORDER BY ABS(JULIANDAY(fecha) - JULIANDAY(?)) ASC, id ASC LIMIT 1
        """, (paciente_id, fecha))
        pending_match = cursor.fetchone()

        if pending_match and not data.get('forzar_nuevo_registro'):
            pending_id = pending_match['id']
            cursor.execute("""
                UPDATE agenda_finanzas
                SET monto = ?, moneda = ?, tipo_consulta = ?, estado_pago = 'Paga',
                    control_uso = 'No consumida', cantidad_sesiones = ?,
                    referencia = ?, metodo_pago = ?, fecha_pago = ?
                WHERE id = ?
            """, (monto, moneda, tipo_consulta, cantidad_ses, referencia, metodo_pago, fecha_pago, pending_id))
            db.commit()
            auto_settle_patient_debts(db, paciente_id)
            
            try:
                from app import sync_patient_to_firebase
                import threading
                threading.Thread(target=sync_patient_to_firebase, args=(paciente_id,)).start()
            except Exception: pass
            
            return jsonify({'success': 'Pago asignado y vinculado a la cita agendada del consultante con éxito.'})

        # 2. Guardar nuevo registro financiero si no hay pendiente
        control_uso_val = data.get('control_uso') or 'No consumida'

        if 'paquete' in tipo_consulta.lower() and cantidad_ses <= 1:
            cursor.execute("SELECT sesiones_paquete_personalizado FROM pacientes WHERE id = ?", (paciente_id,))
            pac_pkg = cursor.fetchone()
            if pac_pkg and pac_pkg['sesiones_paquete_personalizado']:
                cantidad_ses = int(pac_pkg['sesiones_paquete_personalizado'])

        cursor.execute("""
            INSERT INTO agenda_finanzas (
                paciente_id, fecha, hora, tipo_consulta, monto, moneda,
                estado_pago, control_uso, cantidad_sesiones,
                referencia, metodo_pago, fecha_pago, confirmada
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
        """, (
            paciente_id, fecha, hora, tipo_consulta, monto, moneda,
            estado_pago, control_uso_val, cantidad_ses,
            referencia, metodo_pago, fecha_pago
        ))
        db.commit()
        auto_settle_patient_debts(db, paciente_id)
        
        try:
            from app import sync_patient_to_firebase
            import threading
            threading.Thread(target=sync_patient_to_firebase, args=(paciente_id,)).start()
        except Exception: pass

        # Registrar deuda en pagos parciales/fraccionados
        deuda_generada = data.get('deuda_generada', 0)
        if deuda_generada and float(deuda_generada) > 0:
            cursor.execute("""
                INSERT INTO agenda_finanzas (
                    paciente_id, fecha, hora, tipo_consulta, monto, moneda,
                    estado_pago, control_uso, cantidad_sesiones,
                    referencia, metodo_pago, fecha_pago, confirmada
                ) VALUES (?, ?, '00:00', ?, ?, ?, 'Pendiente', 'Pendiente', 0, ?, ?, ?, 1)
            """, (
                paciente_id, fecha,
                tipo_consulta + ' (Deuda Pago Fraccionado)',
                float(deuda_generada), moneda,
                'Saldo pendiente por pago parcial de paquete', '', fecha_pago
            ))
            db.commit()

        return jsonify({
            'success': 'Pago registrado con éxito.',
            'deuda': float(deuda_generada) if deuda_generada else 0
        })
    except Exception as e:
        return jsonify({'error': f'Error al registrar pago: {str(e)}'}), 500

@finanzas_bp.route('/api/patient-profile/<int:patient_id>', methods=['GET'])
@login_required
def get_patient_profile_rates(patient_id):
    """Retorna datos del paciente incluyendo honorarios personalizados."""
    db = get_db()
    cursor = db.cursor()
    psicologo_id = session.get('user_id')
    cursor.execute("""
        SELECT id, nombres, apellidos, cedula,
               costo_personalizado, moneda_personalizada,
               costo_paquete_personalizado, sesiones_paquete_personalizado
        FROM pacientes WHERE id = ? AND psicologo_id = ?
    """, (patient_id, psicologo_id))
    row = cursor.fetchone()
    if not row:
        return jsonify({'error': 'Paciente no encontrado.'}), 404
    return jsonify(dict(row))

@finanzas_bp.route('/api/patient-debts/<int:patient_id>', methods=['GET'])
@login_required
def get_patient_debts(patient_id):
    """Retorna las consultas pendientes de cobro de un paciente."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT id, fecha, hora, tipo_consulta, monto, moneda, estado_pago
        FROM agenda_finanzas
        WHERE paciente_id = ?
          AND estado_pago IN ('Pendiente', 'Debe')
        ORDER BY fecha DESC
    """, (patient_id,))
    rows = cursor.fetchall()
    return jsonify([dict(r) for r in rows])

@finanzas_bp.route('/api/mark-debts-paid', methods=['POST'])
@login_required
def mark_debts_paid():
    """Marca múltiples registros de agenda_finanzas como pagados."""
    data = request.json or {}
    debt_ids = data.get('debt_ids', [])
    metodo_pago = data.get('metodo_pago', '')
    referencia = data.get('referencia', '')
    fecha_pago = data.get('fecha_pago', '')

    if not debt_ids:
        return jsonify({'error': 'No se indicaron deudas a pagar.'}), 400

    db = get_db()
    cursor = db.cursor()
    psicologo_id = session.get('user_id')

    updated = 0
    for did in debt_ids:
        cursor.execute("""
            UPDATE agenda_finanzas SET
                estado_pago = 'Paga',
                metodo_pago = ?,
                referencia = ?,
                fecha_pago = ?
            WHERE id = ?
              AND paciente_id IN (
                  SELECT id FROM pacientes WHERE psicologo_id = ?
              )
        """, (metodo_pago, referencia, fecha_pago, did, psicologo_id))
        updated += cursor.rowcount

    db.commit()
    return jsonify({'success': f'{updated} consultas marcadas como pagadas.'})

VET_TZ = datetime.timezone(datetime.timedelta(hours=-4))

def get_now_vet():
    """Retorna datetime actual ajustado a la zona horaria de Venezuela (GMT-4)."""
    return datetime.datetime.now(VET_TZ)

def get_psicologo_id_filter():
    role = session.get('role')
    user_id = session.get('user_id')
    username = session.get('username', '')
    
    if (role in ['admin', 'superadmin']) and (username.lower() != 'pamoraro' and user_id != 1):
        return -1
        
    return user_id if user_id else 1

@finanzas_bp.route('/api/finance/balance', methods=['GET'])
@login_required
def get_monthly_balance():
    now = get_now_vet()
    month = request.args.get('month', now.strftime('%m'))
    year = request.args.get('year', now.strftime('%Y'))
    
    date_prefix = f"{year}-{month}%"
    db = get_db()
    cursor = db.cursor()
    psic_id = get_psicologo_id_filter()
    
    if psic_id is not None and psic_id != -1:
        cursor.execute("""
            SELECT af.moneda, af.tipo_consulta, SUM(af.monto) as total_monto
            FROM agenda_finanzas af
            JOIN pacientes p ON af.paciente_id = p.id
            WHERE (af.fecha LIKE ? OR af.fecha_liquidacion LIKE ?) 
              AND af.estado_pago IN ('Paga', 'Prepagada', 'Cancelada sin aviso - Paga')
              AND p.psicologo_id = ?
            GROUP BY af.moneda, af.tipo_consulta
        """, (date_prefix, date_prefix, psic_id))
        breakdown = [dict(row) for row in cursor.fetchall()]
        
        cursor.execute("""
            SELECT af.*, 
                   COALESCE(p.nombres, 'Consultante') as nombres, 
                   COALESCE(p.apellidos, '') as apellidos, 
                   p.cedula
            FROM agenda_finanzas af
            JOIN pacientes p ON af.paciente_id = p.id
            WHERE af.estado_pago IN ('Pendiente', 'Cancelada sin aviso')
              AND p.psicologo_id = ?
            ORDER BY af.fecha ASC
        """, (psic_id,))
        pending_list = [dict(row) for row in cursor.fetchall()]
        
        cursor.execute("""
            SELECT af.*, 
                   COALESCE(p.nombres, 'Consultante') as nombres, 
                   COALESCE(p.apellidos, '') as apellidos
            FROM agenda_finanzas af
            JOIN pacientes p ON af.paciente_id = p.id
            WHERE (af.fecha LIKE ? OR af.fecha_liquidacion LIKE ?) 
              AND af.estado_pago IN ('Paga', 'Prepagada', 'Cancelada sin aviso - Paga')
              AND af.monto > 0
              AND p.psicologo_id = ?
            ORDER BY af.fecha DESC
        """, (date_prefix, date_prefix, psic_id))
        income_list = [dict(row) for row in cursor.fetchall()]
        
        cursor.execute("SELECT COUNT(id) FROM pacientes WHERE psicologo_id = ?", (psic_id,))
        total_pacientes = cursor.fetchone()[0] or 0
        
        cursor.execute("""
            SELECT SUM(af.cantidad_sesiones) 
            FROM agenda_finanzas af
            JOIN pacientes p ON af.paciente_id = p.id
            WHERE af.estado_pago IN ('Paga', 'Prepagada', 'Cancelada sin aviso - Paga') 
              AND af.monto > 0
              AND (af.fecha LIKE ? OR af.fecha_liquidacion LIKE ?)
              AND p.psicologo_id = ?
        """, (date_prefix, date_prefix, psic_id))
        total_pagas = cursor.fetchone()[0] or 0
        
        cursor.execute("""
            SELECT SUM(af.cantidad_sesiones) 
            FROM agenda_finanzas af
            JOIN pacientes p ON af.paciente_id = p.id
            WHERE af.estado_pago IN ('Pendiente', 'Cancelada sin aviso')
              AND p.psicologo_id = ?
        """, (psic_id,))
        total_pendientes = cursor.fetchone()[0] or 0
        
        cursor.execute("""
            SELECT s.modalidad, s.estado, COUNT(s.id) as cantidad
            FROM sesiones s
            JOIN pacientes p ON s.paciente_id = p.id
            WHERE s.fecha LIKE ? AND p.psicologo_id = ?
            GROUP BY s.modalidad, s.estado
        """, (date_prefix, psic_id))
        session_stats = [dict(row) for row in cursor.fetchall()]
        
        cursor.execute("""
            SELECT s.modalidad, COUNT(s.id)
            FROM sesiones s
            JOIN pacientes p ON s.paciente_id = p.id
            WHERE s.fecha LIKE ? AND p.psicologo_id = ?
              AND (s.estado IS NULL OR (s.estado != 'Cancelada' AND s.estado NOT LIKE 'Cancelada%'))
            GROUP BY s.modalidad
        """, (date_prefix, psic_id))
        ses_counts = {row[0]: row[1] for row in cursor.fetchall() if row[0]}

        cursor.execute("""
            SELECT af.tipo_consulta, COUNT(af.id)
            FROM agenda_finanzas af
            JOIN pacientes p ON af.paciente_id = p.id
            WHERE af.fecha LIKE ? AND p.psicologo_id = ?
              AND (af.estado_pago IS NULL OR (af.estado_pago NOT LIKE 'Cancelada%' AND af.estado_pago != 'Reprogramada'))
            GROUP BY af.tipo_consulta
        """, (date_prefix, psic_id))
        af_counts = {row[0]: row[1] for row in cursor.fetchall() if row[0]}

        all_keys = set(ses_counts.keys()).union(set(af_counts.keys()))
        modality_counts = {}
        for k in all_keys:
            if k in ['Prepago', 'Paquete Prepagado', 'Paquete Prepagado (Deuda Pago Fraccionado)']:
                continue
            modality_counts[k] = max(ses_counts.get(k, 0), af_counts.get(k, 0))
    else:
        cursor.execute("""
            SELECT moneda, tipo_consulta, SUM(monto) as total_monto
            FROM agenda_finanzas
            WHERE (fecha LIKE ? OR fecha_liquidacion LIKE ?) AND estado_pago IN ('Paga', 'Prepagada', 'Cancelada sin aviso - Paga')
            GROUP BY moneda, tipo_consulta
        """, (date_prefix, date_prefix))
        breakdown = [dict(row) for row in cursor.fetchall()]
        
        cursor.execute("""
            SELECT af.*, 
                   COALESCE(p.nombres, 'Consultante') as nombres, 
                   COALESCE(p.apellidos, '') as apellidos, 
                   p.cedula
            FROM agenda_finanzas af
            LEFT JOIN pacientes p ON af.paciente_id = p.id
            WHERE af.estado_pago IN ('Pendiente', 'Cancelada sin aviso')
            ORDER BY af.fecha ASC
        """)
        pending_list = [dict(row) for row in cursor.fetchall()]
        
        cursor.execute("""
            SELECT af.*, 
                   COALESCE(p.nombres, 'Consultante') as nombres, 
                   COALESCE(p.apellidos, '') as apellidos
            FROM agenda_finanzas af
            LEFT JOIN pacientes p ON af.paciente_id = p.id
            WHERE (fecha LIKE ? OR fecha_liquidacion LIKE ?) 
              AND af.estado_pago IN ('Paga', 'Prepagada', 'Cancelada sin aviso - Paga')
              AND af.monto > 0
            ORDER BY af.fecha DESC
        """, (date_prefix, date_prefix))
        income_list = [dict(row) for row in cursor.fetchall()]
        
        cursor.execute("SELECT COUNT(id) FROM pacientes")
        total_pacientes = cursor.fetchone()[0] or 0
        
        cursor.execute("""
            SELECT SUM(cantidad_sesiones) 
            FROM agenda_finanzas 
            WHERE estado_pago IN ('Paga', 'Prepagada', 'Cancelada sin aviso - Paga') 
              AND monto > 0
              AND (fecha LIKE ? OR fecha_liquidacion LIKE ?)
        """, (date_prefix, date_prefix))
        total_pagas = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT SUM(cantidad_sesiones) FROM agenda_finanzas WHERE estado_pago IN ('Pendiente', 'Cancelada sin aviso')")
        total_pendientes = cursor.fetchone()[0] or 0
        
        cursor.execute("""
            SELECT modalidad, estado, COUNT(id) as cantidad
            FROM sesiones
            WHERE fecha LIKE ?
            GROUP BY modalidad, estado
        """, (date_prefix,))
        session_stats = [dict(row) for row in cursor.fetchall()]
        
        cursor.execute("""
            SELECT modalidad, COUNT(id)
            FROM sesiones
            WHERE fecha LIKE ? AND (estado IS NULL OR (estado != 'Cancelada' AND estado NOT LIKE 'Cancelada%'))
            GROUP BY modalidad
        """, (date_prefix,))
        modality_counts = {row[0]: row[1] for row in cursor.fetchall()}
    
    active_modalities = ["Presencial", "Online"]
    if psic_id is not None and psic_id != -1:
        cursor.execute("SELECT configuracion_horarios_visual FROM usuarios WHERE id = ?", (psic_id,))
        u_row = cursor.fetchone()
        if u_row and u_row['configuracion_horarios_visual']:
            try:
                cfg = json.loads(u_row['configuracion_horarios_visual'])
                raw_perfiles = cfg.get('perfiles', [])
                custom_mods = []
                if isinstance(raw_perfiles, list):
                    for p in raw_perfiles:
                        if isinstance(p, dict) and (p.get('nombre') or p.get('modalidad')):
                            custom_mods.append(p.get('nombre') or p.get('modalidad'))
                elif isinstance(raw_perfiles, dict):
                    custom_mods = list(raw_perfiles.keys())
                if custom_mods:
                    active_modalities = custom_mods
            except Exception:
                pass

    def _mod_match(db_mod, profile_mod):
        if not db_mod or not profile_mod:
            return False
        d = db_mod.strip().lower()
        p = profile_mod.strip().lower()
        if d == p:
            return True
        ignore_words = {'horario', 'modalidad', 'consulta', 'atencion', 'servicio'}
        d_words = set(d.split()) - ignore_words
        p_words = set(p.split()) - ignore_words
        if not d_words or not p_words:
            return d == p or d in p or p in d
        if d_words == p_words:
            return True
        if d_words & p_words:
            return True
        return False

    month_modalities = {}
    for m in active_modalities:
        m_count = 0
        for k, v in modality_counts.items():
            if _mod_match(k, m):
                m_count += v
        month_modalities[m] = m_count

    return jsonify({
        'breakdown': breakdown,
        'pending_list': pending_list,
        'income_list': income_list,
        'session_stats': session_stats,
        'stats': {
            'total_pacientes': total_pacientes,
            'total_pagas': total_pagas,
            'total_pendientes': total_pendientes,
            'month_online': modality_counts.get('Online', 0),
            'month_presencial': modality_counts.get('Presencial', 0),
            'month_modalities': month_modalities
        }
    })

@finanzas_bp.route('/api/admin/patients-rates-list', methods=['GET'])
@login_required
def get_patients_rates_list():
    """Obtener lista de todos los pacientes con sus honorarios para la tabla unificada."""
    try:
        db = get_db()
        cursor = db.cursor()
        psicologo_id = session.get('user_id')
        cursor.execute("""
            SELECT id, nombres, apellidos, cedula, pais, ciudad,
                   costo_personalizado, moneda_personalizada,
                   costo_paquete_personalizado, sesiones_paquete_personalizado
            FROM pacientes
            WHERE psicologo_id = ?
            ORDER BY apellidos ASC, nombres ASC
        """, (psicologo_id,))
        patients = [dict(p) for p in cursor.fetchall()]
        return jsonify(patients)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@finanzas_bp.route('/api/admin/payments/notified', methods=['GET'])
@login_required
def get_admin_notified_payments():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT pn.id, pn.paciente_id, pn.monto, pn.moneda, pn.metodo, pn.referencia, pn.fecha, pn.estado, pn.fecha_registro,
               p.nombres, p.apellidos
        FROM pagos_notificados pn
        JOIN pacientes p ON pn.paciente_id = p.id
        WHERE pn.estado = 'Pendiente de verificación'
        ORDER BY pn.fecha_registro DESC
    """)
    rows = cursor.fetchall()
    return jsonify([dict(r) for r in rows])

@finanzas_bp.route('/api/admin/payments/verify/<int:payment_id>', methods=['POST'])
@login_required
def verify_admin_payment(payment_id):
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("SELECT * FROM pagos_notificados WHERE id = ?", (payment_id,))
        payment = cursor.fetchone()
        if not payment:
            return jsonify({'error': 'Pago notificado no encontrado.'}), 404

        paciente_id = payment['paciente_id']
        monto_pago = float(payment['monto']) if payment['monto'] else 0.0
        moneda_pago = payment['moneda'] or 'USD'
        metodo_pago = payment['metodo'] or ''
        referencia_pago = payment['referencia'] or ''
        fecha_pago = payment['fecha'] or datetime.datetime.now().strftime('%Y-%m-%d')

        cursor.execute("UPDATE pagos_notificados SET estado = 'Verificado' WHERE id = ?", (payment_id,))

        cursor.execute("""
            SELECT id, monto, estado_pago FROM agenda_finanzas
            WHERE paciente_id = ? AND moneda = ?
              AND estado_pago IN ('Pendiente', 'Cancelada sin aviso')
            ORDER BY fecha ASC, id ASC
        """, (paciente_id, moneda_pago))
        pending_rows = cursor.fetchall()

        remaining = monto_pago
        for row in pending_rows:
            if remaining <= 0:
                break
            row_monto = float(row['monto']) if row['monto'] else 0.0
            if row_monto <= 0:
                continue
            if remaining >= row_monto:
                new_estado = 'Cancelada sin aviso - Paga' if row['estado_pago'] == 'Cancelada sin aviso' else 'Paga'
                cursor.execute("""
                    UPDATE agenda_finanzas 
                    SET estado_pago = ?, control_uso = 'Consumida',
                        fecha_liquidacion = ?, metodo_pago = ?, referencia = ?, fecha_pago = ?
                    WHERE id = ?
                """, (new_estado, fecha_pago, metodo_pago, referencia_pago, fecha_pago, row['id']))
                remaining -= row_monto
            else:
                nuevo_saldo_deuda = row_monto - remaining
                cursor.execute("""
                    UPDATE agenda_finanzas 
                    SET monto = ? 
                    WHERE id = ?
                """, (nuevo_saldo_deuda, row['id']))
                
                cursor.execute("""
                    INSERT INTO agenda_finanzas (
                        paciente_id, fecha, hora, tipo_consulta, monto, moneda, estado_pago,
                        control_uso, fecha_liquidacion, cantidad_sesiones, referencia, metodo_pago, fecha_pago, confirmada
                    ) VALUES (?, ?, '00:00', ?, ?, ?, 'Paga', 'Consumida', ?, 0, ?, ?, ?, 1)
                """, (
                    paciente_id, fecha_pago, row['tipo_consulta'] or 'Abono a Deuda',
                    remaining, moneda_pago, fecha_pago,
                    f"Abono parcial a deuda. Ref: {referencia_pago}", metodo_pago, fecha_pago
                ))
                remaining = 0

        if remaining > 0:
            cursor.execute("SELECT costo_paquete_personalizado, sesiones_paquete_personalizado, psicologo_id FROM pacientes WHERE id = ?", (paciente_id,))
            pac = cursor.fetchone()
            num_sesiones = 1
            if pac and pac['sesiones_paquete_personalizado']:
                pkg_cost = float(pac['costo_paquete_personalizado'] or 0)
                pkg_count = int(pac['sesiones_paquete_personalizado'])
                if pkg_cost > 0 and abs(remaining - pkg_cost) < 0.01:
                    num_sesiones = pkg_count
                elif pkg_cost > 0 and remaining >= pkg_cost:
                    calc = int((remaining / pkg_cost) * pkg_count)
                    if calc > 0:
                        num_sesiones = calc

            cursor.execute("""
                INSERT INTO agenda_finanzas (
                    paciente_id, fecha, hora, tipo_consulta, monto, moneda, estado_pago,
                    control_uso, fecha_liquidacion, cantidad_sesiones, referencia, metodo_pago, fecha_pago
                ) VALUES (?, ?, '00:00', 'Online', ?, ?, 'Prepagada', 'No consumida', ?, ?, ?, ?, ?)
            """, (paciente_id, fecha_pago, remaining, moneda_pago, fecha_pago, num_sesiones, f"Saldo prepagado verificado ({num_sesiones} consultas). Ref: {referencia_pago}", metodo_pago, fecha_pago))

        db.commit()
        auto_settle_patient_debts(db, paciente_id)
        return jsonify({'success': 'Pago verificado y registrado con éxito.'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@finanzas_bp.route('/api/admin/payments/reject/<int:payment_id>', methods=['POST'])
@login_required
def reject_admin_payment(payment_id):
    data = request.json or {}
    note = data.get('nota_rechazo', '').strip()
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("""
            UPDATE pagos_notificados 
            SET estado = 'Requerir nuevos datos', motivo_rechazo = ? 
            WHERE id = ?
        """, (note, payment_id))
        db.commit()
        return jsonify({'success': 'Pago rechazado localmente con éxito.'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@finanzas_bp.route('/api/admin/payments/delete/<int:payment_id>', methods=['POST', 'DELETE'])
@login_required
def delete_admin_payment_notified(payment_id):
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("DELETE FROM pagos_notificados WHERE id = ?", (payment_id,))
        db.commit()
        return jsonify({'success': 'Notificación de pago eliminada correctamente.'})
    except Exception as e:
        return jsonify({'error': f'Error al eliminar notificación de pago: {str(e)}'}), 500


# --- RUTAS MIGRADAS AUTOMÁTICAMENTE DE AUDITORÍA ---

@finanzas_bp.route('/api/admin/country-rates', methods=['GET'])
@login_required
def get_country_rates():
    try:
        db = get_db()
        cursor = db.cursor()
        psicologo_id = session.get('user_id')
        cursor.execute("""
            SELECT id, pais, modalidad, costo_individual, costo_paquete, sesiones_paquete, moneda
            FROM tarifas_pais WHERE psicologo_id = ? ORDER BY pais, modalidad
        """, (psicologo_id,))
        rates = [dict(r) for r in cursor.fetchall()]
        return jsonify(rates)
    except Exception as e:
        return jsonify({'error': str(e)}), 500



@finanzas_bp.route('/api/admin/country-rates', methods=['POST'])
@login_required
def save_country_rate():
    try:
        data = request.json or {}
        db = get_db()
        cursor = db.cursor()
        psicologo_id = session.get('user_id')
        pais = data.get('pais', '').strip()
        modalidad = data.get('modalidad', '').strip()
        costo_individual = data.get('costo_individual')
        costo_paquete = data.get('costo_paquete')
        sesiones_paquete = data.get('sesiones_paquete')
        moneda = data.get('moneda', 'USD').strip()
        
        if not pais or not modalidad or costo_individual is None:
            return jsonify({'error': 'País, modalidad y costo individual son requeridos.'}), 400
        
        cursor.execute("""
            INSERT INTO tarifas_pais (psicologo_id, pais, modalidad, costo_individual, costo_paquete, sesiones_paquete, moneda)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(psicologo_id, pais, modalidad) DO UPDATE SET
                costo_individual = excluded.costo_individual,
                costo_paquete = excluded.costo_paquete,
                sesiones_paquete = excluded.sesiones_paquete,
                moneda = excluded.moneda
        """, (psicologo_id, pais, modalidad, costo_individual, costo_paquete, sesiones_paquete, moneda))
        db.commit()
        return jsonify({'success': 'Tarifa guardada con éxito.'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500



@finanzas_bp.route('/api/admin/country-rates/<int:rate_id>', methods=['DELETE'])
@login_required
def delete_country_rate(rate_id):
    try:
        db = get_db()
        cursor = db.cursor()
        psicologo_id = session.get('user_id')
        cursor.execute("DELETE FROM tarifas_pais WHERE id = ? AND psicologo_id = ?", (rate_id, psicologo_id))
        db.commit()
        return jsonify({'success': 'Tarifa eliminada.'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


