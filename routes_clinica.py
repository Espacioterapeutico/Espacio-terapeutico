# -*- coding: utf-8 -*-
"""
Módulo Corporativo / Equipos de Trabajo (routes_clinica.py)
Encapsula la arquitectura multi-usuario, organizaciones, invitaciones con doble aceptación,
portal público de clínicas, agenda consolidada, finanzas de equipo y supervisión de casos.
"""

import os
import re
import uuid
import json
import sqlite3
import datetime
from flask import Blueprint, request, jsonify, session, g

clinica_bp = Blueprint('clinica', __name__)

def get_db():
    """Obtiene la conexión a la base de datos desde el contexto global g de Flask."""
    db = getattr(g, '_database', None)
    if db is None:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        db_path = os.path.join(base_dir, 'clinica.db')
        db = g._database = sqlite3.connect(db_path, timeout=30.0)
        db.row_factory = sqlite3.Row
    return db

def ensure_clinica_tables(db):
    """Garantiza la creación de las tablas corporativas y la migración de columnas en SQLite."""
    cursor = db.cursor()

    # 1. Tabla de Organizaciones / Clínicas
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS organizaciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            slug TEXT UNIQUE NOT NULL,
            logo TEXT,
            descripcion TEXT,
            admin_user_id INTEGER NOT NULL,
            codigo_clinica TEXT UNIQUE NOT NULL,
            modo_whatsapp TEXT DEFAULT 'centralizado',
            fecha_registro DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (admin_user_id) REFERENCES usuarios(id) ON DELETE CASCADE
        )
    """)

    # 2. Tabla de Solicitudes de Equipo (Double Opt-In)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS equipo_solicitudes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            organizacion_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            solicitante_id INTEGER NOT NULL,
            tipo_solicitud TEXT NOT NULL, -- 'invitacion' (Admin->User) o 'solicitud' (User->Admin)
            estado TEXT DEFAULT 'pendiente', -- 'pendiente', 'aceptada', 'rechazada'
            fecha_registro DATETIME DEFAULT CURRENT_TIMESTAMP,
            fecha_respuesta DATETIME,
            FOREIGN KEY (organizacion_id) REFERENCES organizaciones(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES usuarios(id) ON DELETE CASCADE,
            FOREIGN KEY (solicitante_id) REFERENCES usuarios(id) ON DELETE CASCADE
        )
    """)

    # 3. Migración de columnas en tabla `usuarios`
    cursor.execute("PRAGMA table_info(usuarios)")
    cols_usr = [r[1] for r in cursor.fetchall()]
    if cols_usr:
        if 'tipo_clinica' not in cols_usr:
            cursor.execute("ALTER TABLE usuarios ADD COLUMN tipo_clinica INTEGER DEFAULT 0") # 0=Indep, 1=Admin, 2=Miembro
        if 'organizacion_id' not in cols_usr:
            cursor.execute("ALTER TABLE usuarios ADD COLUMN organizacion_id INTEGER DEFAULT NULL")
        if 'codigo_clinica' not in cols_usr:
            cursor.execute("ALTER TABLE usuarios ADD COLUMN codigo_clinica TEXT DEFAULT NULL")
        if 'especialidades' not in cols_usr:
            cursor.execute("ALTER TABLE usuarios ADD COLUMN especialidades TEXT DEFAULT NULL")
        if 'biografia_corta' not in cols_usr:
            cursor.execute("ALTER TABLE usuarios ADD COLUMN biografia_corta TEXT DEFAULT NULL")

    # 4. Migración de columnas en `organizaciones`
    cursor.execute("PRAGMA table_info(organizaciones)")
    cols_org = [r[1] for r in cursor.fetchall()]
    if cols_org and 'espacios_fisicos' not in cols_org:
        cursor.execute("ALTER TABLE organizaciones ADD COLUMN espacios_fisicos TEXT DEFAULT 'Consultorio 1, Consultorio 2'")

    # 5. Migración de columna `notas_supervision` en `sesiones`
    cursor.execute("PRAGMA table_info(sesiones)")
    cols_ses = [r[1] for r in cursor.fetchall()]
    if cols_ses and 'notas_supervision' not in cols_ses:
        cursor.execute("ALTER TABLE sesiones ADD COLUMN notas_supervision TEXT DEFAULT NULL")

    # 6. Migración de columnas en `agenda_finanzas`
    cursor.execute("PRAGMA table_info(agenda_finanzas)")
    cols_ag = [r[1] for r in cursor.fetchall()]
    if cols_ag:
        if 'creado_por_user_id' not in cols_ag:
            cursor.execute("ALTER TABLE agenda_finanzas ADD COLUMN creado_por_user_id INTEGER DEFAULT NULL")
        if 'consultorio_nombre' not in cols_ag:
            cursor.execute("ALTER TABLE agenda_finanzas ADD COLUMN consultorio_nombre TEXT DEFAULT 'Consultorio 1'")
        if 'organizacion_id' not in cols_ag:
            cursor.execute("ALTER TABLE agenda_finanzas ADD COLUMN organizacion_id INTEGER DEFAULT NULL")

    # 7. Migración de columna `organizacion_id` en `pacientes`
    cursor.execute("PRAGMA table_info(pacientes)")
    cols_pac = [r[1] for r in cursor.fetchall()]
    if cols_pac and 'organizacion_id' not in cols_pac:
        cursor.execute("ALTER TABLE pacientes ADD COLUMN organizacion_id INTEGER DEFAULT NULL")

    db.commit()

def generate_unique_clinic_code(db, name):
    """Genera un código único alfanumérico para la clínica (ej: MSANA-8921)."""
    cursor = db.cursor()
    clean_name = re.sub(r'[^A-Za-z0-9]', '', name).upper()
    prefix = clean_name[:5] if len(clean_name) >= 3 else "CLINIC"
    for _ in range(50):
        rand_num = str(uuid.uuid4().int)[:4]
        code = f"{prefix}-{rand_num}"
        cursor.execute("SELECT id FROM organizaciones WHERE codigo_clinica = ?", (code,))
        if not cursor.fetchone():
            return code
    return f"CLINIC-{uuid.uuid4().hex[:6].upper()}"

def generate_unique_slug(db, name):
    """Genera un slug web único para la URL pública de la clínica."""
    cursor = db.cursor()
    base_slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
    if not base_slug:
        base_slug = "centro-terapeutico"
    slug = base_slug
    counter = 1
    while True:
        cursor.execute("SELECT id FROM organizaciones WHERE slug = ?", (slug,))
        if not cursor.fetchone():
            return slug
        slug = f"{base_slug}-{counter}"
        counter += 1


# ==============================================================================
# ENDPOINTS DE GESTIÓN Y REGISTRO CORPORATIVO
# ==============================================================================

@clinica_bp.route('/api/clinica/registrar', methods=['POST'])
def api_registrar_clinica():
    """Registra una nueva Organización / Clínica y promueve al usuario a tipo_clinica = 1 (Admin)."""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'No autorizado.'}), 401

    db = get_db()
    ensure_clinica_tables(db)
    cursor = db.cursor()

    data = request.json or {}
    nombre = (data.get('nombre') or '').strip()
    descripcion = (data.get('descripcion') or '').strip()
    logo = (data.get('logo') or '').strip()

    if not nombre:
        return jsonify({'error': 'El nombre de la clínica u organización es obligatorio.'}), 400

    cursor.execute("SELECT organizacion_id, tipo_clinica FROM usuarios WHERE id = ?", (user_id,))
    usr = cursor.fetchone()
    if usr and usr['organizacion_id']:
        return jsonify({'error': 'Tu usuario ya pertenece o administra una clínica registrada.'}), 400

    code = generate_unique_clinic_code(db, nombre)
    slug = generate_unique_slug(db, nombre)

    try:
        cursor.execute("""
            INSERT INTO organizaciones (nombre, slug, logo, descripcion, admin_user_id, codigo_clinica)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (nombre, slug, logo, descripcion, user_id, code))
        org_id = cursor.lastrowid

        cursor.execute("""
            UPDATE usuarios SET
                tipo_clinica = 1,
                organizacion_id = ?,
                codigo_clinica = ?
            WHERE id = ?
        """, (org_id, code, user_id))
        db.commit()

        return jsonify({
            'success': 'Clínica registrada exitosamente.',
            'organizacion_id': org_id,
            'nombre': nombre,
            'slug': slug,
            'codigo_clinica': code,
            'url_publica': f"/clinica/{slug}"
        })
    except Exception as e:
        db.rollback()
        return jsonify({'error': f'Error al registrar clínica: {str(e)}'}), 500


@clinica_bp.route('/api/clinica/mi-equipo', methods=['GET'])
def api_get_mi_equipo():
    """Retorna los datos de la clínica del usuario activo y el listado de terapeutas vinculados."""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'No autorizado.'}), 401

    db = get_db()
    ensure_clinica_tables(db)
    cursor = db.cursor()

    cursor.execute("SELECT * FROM usuarios WHERE id = ?", (user_id,))
    usr = cursor.fetchone()
    if not usr or not usr['organizacion_id']:
        return jsonify({'pertenece': False, 'miembros': []})

    org_id = usr['organizacion_id']
    cursor.execute("SELECT * FROM organizaciones WHERE id = ?", (org_id,))
    org = cursor.fetchone()
    if not org:
        return jsonify({'pertenece': False, 'miembros': []})

    org_dict = dict(org)
    org_dict['pertenece'] = True
    org_dict['es_admin'] = (usr['tipo_clinica'] == 1 or org_dict['admin_user_id'] == user_id)

    # Miembros activos del equipo (tipo_clinica 1 y 2)
    cursor.execute("""
        SELECT id, nombres, apellidos, cedula, username, foto_titulo, nomenclatura, especialidades, biografia_corta, tipo_clinica, activo
        FROM usuarios
        WHERE organizacion_id = ?
        ORDER BY tipo_clinica ASC, nombres ASC
    """, (org_id,))
    miembros = [dict(r) for r in cursor.fetchall()]
    org_dict['miembros'] = miembros

    return jsonify(org_dict)


@clinica_bp.route('/api/clinica/vincular-miembro', methods=['POST'])
def api_vincular_miembro():
    """El Psicólogo Administrador invita a un terapeuta ingresando su Cédula o ID de Psicólogo."""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'No autorizado.'}), 401

    db = get_db()
    ensure_clinica_tables(db)
    cursor = db.cursor()

    cursor.execute("SELECT * FROM usuarios WHERE id = ?", (user_id,))
    admin_usr = cursor.fetchone()
    if not admin_usr or admin_usr['tipo_clinica'] != 1 or not admin_usr['organizacion_id']:
        return jsonify({'error': 'Solo el Psicólogo Administrador de la clínica puede invitar miembros.'}), 403

    data = request.json or {}
    busqueda = (data.get('busqueda') or '').strip()
    if not busqueda:
        return jsonify({'error': 'Por favor ingrese la Cédula o el ID de Psicólogo a invitar.'}), 400

    # Buscar usuario por Cédula, ID o username
    cursor.execute("""
        SELECT * FROM usuarios
        WHERE id = ? OR LOWER(cedula) = LOWER(?) OR LOWER(username) = LOWER(?)
    """, (busqueda, busqueda, busqueda))
    target_usr = cursor.fetchone()

    if not target_usr:
        return jsonify({'error': f'No se encontró ningún psicólogo registrado con la Cédula/ID "{busqueda}".'}), 404

    target_id = target_usr['id']
    if target_id == user_id:
        return jsonify({'error': 'No puedes invitarte a ti mismo.'}), 400

    if target_usr['organizacion_id'] == admin_usr['organizacion_id']:
        return jsonify({'error': 'Este psicólogo ya pertenece a tu equipo.'}), 400

    # Verificar si ya existe una solicitud pendiente
    cursor.execute("""
        SELECT id, estado FROM equipo_solicitudes
        WHERE organizacion_id = ? AND user_id = ? AND estado = 'pendiente'
    """, (admin_usr['organizacion_id'], target_id))
    sol_exist = cursor.fetchone()
    if sol_exist:
        return jsonify({'error': 'Ya existe una invitación pendiente enviada a este psicólogo.'}), 400

    cursor.execute("""
        INSERT INTO equipo_solicitudes (organizacion_id, user_id, solicitante_id, tipo_solicitud, estado)
        VALUES (?, ?, ?, 'invitacion', 'pendiente')
    """, (admin_usr['organizacion_id'], target_id, user_id))
    db.commit()

    return jsonify({
        'success': f"Invitación enviada exitosamente al Psic. {target_usr['nombres']} {target_usr['apellidos']}. El profesional debe aceptarla en su sección de Ajustes.",
        'target_nombre': f"{target_usr['nombres']} {target_usr['apellidos']}".strip()
    })


@clinica_bp.route('/api/clinica/solicitar-ingreso', methods=['POST'])
def api_solicitar_ingreso():
    """Un psicólogo ingresa el Código de Clínica para solicitar su ingreso al equipo."""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'No autorizado.'}), 401

    db = get_db()
    ensure_clinica_tables(db)
    cursor = db.cursor()

    data = request.json or {}
    code = (data.get('codigo_clinica') or '').strip().upper()
    if not code:
        return jsonify({'error': 'Por favor ingrese el Código de la Clínica.'}), 400

    cursor.execute("SELECT * FROM organizaciones WHERE UPPER(codigo_clinica) = ?", (code,))
    org = cursor.fetchone()
    if not org:
        return jsonify({'error': f'No se encontró ninguna clínica con el código "{code}".'}), 404

    cursor.execute("SELECT organizacion_id FROM usuarios WHERE id = ?", (user_id,))
    usr = cursor.fetchone()
    if usr and usr['organizacion_id'] == org['id']:
        return jsonify({'error': 'Ya perteneces a esta clínica.'}), 400

    cursor.execute("""
        SELECT id FROM equipo_solicitudes
        WHERE organizacion_id = ? AND user_id = ? AND estado = 'pendiente'
    """, (org['id'], user_id))
    if cursor.fetchone():
        return jsonify({'error': 'Ya tienes una solicitud pendiente para esta clínica.'}), 400

    cursor.execute("""
        INSERT INTO equipo_solicitudes (organizacion_id, user_id, solicitante_id, tipo_solicitud, estado)
        VALUES (?, ?, ?, 'solicitud', 'pendiente')
    """, (org['id'], user_id, user_id))
    db.commit()

    return jsonify({'success': f"Solicitud enviada a la clínica '{org['nombre']}'. El Director Administrador debe aprobar tu ingreso."})


@clinica_bp.route('/api/clinica/mis-solicitudes', methods=['GET'])
def api_mis_solicitudes():
    """Retorna las solicitudes pendientes recibidas por el usuario (como terapeuta o como admin)."""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'No autorizado.'}), 401

    db = get_db()
    ensure_clinica_tables(db)
    cursor = db.cursor()

    cursor.execute("SELECT tipo_clinica, organizacion_id FROM usuarios WHERE id = ?", (user_id,))
    usr = cursor.fetchone()
    org_id = usr['organizacion_id'] if usr else None
    es_admin = (usr and usr['tipo_clinica'] == 1)

    # 1. Invitaciones recibidas por el usuario como terapeuta
    cursor.execute("""
        SELECT s.id, s.tipo_solicitud, s.estado, s.fecha_registro, o.nombre as organizacion_nombre, o.codigo_clinica,
               u.nombres as admin_nombres, u.apellidos as admin_apellidos
        FROM equipo_solicitudes s
        JOIN organizaciones o ON s.organizacion_id = o.id
        JOIN usuarios u ON s.solicitante_id = u.id
        WHERE s.user_id = ? AND s.estado = 'pendiente' AND s.tipo_solicitud = 'invitacion'
    """, (user_id,))
    invitaciones = [dict(r) for r in cursor.fetchall()]

    # 2. Solicitudes de ingreso recibidas por el Admin para su clínica
    solicitudes_admin = []
    if es_admin and org_id:
        cursor.execute("""
            SELECT s.id, s.tipo_solicitud, s.estado, s.fecha_registro,
                   u.nombres as solicitante_nombres, u.apellidos as solicitante_apellidos, u.cedula as solicitante_cedula, u.username as solicitante_username
            FROM equipo_solicitudes s
            JOIN usuarios u ON s.user_id = u.id
            WHERE s.organizacion_id = ? AND s.estado = 'pendiente' AND s.tipo_solicitud = 'solicitud'
        """, (org_id,))
        solicitudes_admin = [dict(r) for r in cursor.fetchall()]

    return jsonify({
        'invitaciones_recibidas': invitaciones,
        'solicitudes_para_admin': solicitudes_admin
    })


@clinica_bp.route('/api/clinica/solicitud/responder', methods=['POST'])
def api_responder_solicitud():
    """Acepta o rechaza una solicitud de vinculación (Double Opt-In)."""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'No autorizado.'}), 401

    db = get_db()
    ensure_clinica_tables(db)
    cursor = db.cursor()

    data = request.json or {}
    solicitud_id = data.get('solicitud_id')
    accion = (data.get('accion') or '').strip().lower() # 'aceptar' o 'rechazar'

    if not solicitud_id or accion not in ['aceptar', 'rechazar']:
        return jsonify({'error': 'Parámetros inválidos.'}), 400

    cursor.execute("SELECT * FROM equipo_solicitudes WHERE id = ?", (solicitud_id,))
    sol = cursor.fetchone()
    if not sol or sol['estado'] != 'pendiente':
        return jsonify({'error': 'Solicitud no encontrada o procesada previamente.'}), 404

    org_id = sol['organizacion_id']
    cursor.execute("SELECT * FROM organizaciones WHERE id = ?", (org_id,))
    org = cursor.fetchone()
    if not org:
        return jsonify({'error': 'Organización no encontrada.'}), 404

    # Verificar que el usuario tenga derecho a responder
    if sol['tipo_solicitud'] == 'invitacion' and sol['user_id'] != user_id:
        return jsonify({'error': 'No tienes permiso para responder esta invitación.'}), 403
    elif sol['tipo_solicitud'] == 'solicitud' and org['admin_user_id'] != user_id:
        return jsonify({'error': 'Solo el Director Administrador puede responder esta solicitud.'}), 403

    nuevo_estado = 'aceptada' if accion == 'aceptar' else 'rechazada'

    try:
        cursor.execute("""
            UPDATE equipo_solicitudes SET
                estado = ?,
                fecha_respuesta = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (nuevo_estado, solicitud_id))

        if accion == 'aceptar':
            target_user_id = sol['user_id']
            cursor.execute("""
                UPDATE usuarios SET
                    tipo_clinica = 2,
                    organizacion_id = ?,
                    codigo_clinica = ?
                WHERE id = ?
            """, (org_id, org['codigo_clinica'], target_user_id))

        db.commit()
        msg = f"Vinculación aceptada exitosamente con la clínica '{org['nombre']}'." if accion == 'aceptar' else "Solicitud rechazada."
        return jsonify({'success': msg, 'accion': accion})
    except Exception as e:
        db.rollback()
        return jsonify({'error': f'Error al procesar respuesta: {str(e)}'}), 500


@clinica_bp.route('/api/clinica/salir', methods=['POST'])
def api_salir_clinica():
    """Permite a un psicólogo desvincularse voluntariamente de una clínica y retornar a tipo_clinica = 0."""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'No autorizado.'}), 401

    db = get_db()
    ensure_clinica_tables(db)
    cursor = db.cursor()

    cursor.execute("SELECT tipo_clinica FROM usuarios WHERE id = ?", (user_id,))
    usr = cursor.fetchone()
    if usr and usr['tipo_clinica'] == 1:
        return jsonify({'error': 'El Psicólogo Administrador no puede abandonar la clínica directamente. Debe transferir o eliminar la clínica.'}), 400

    cursor.execute("""
        UPDATE usuarios SET
            tipo_clinica = 0,
            organizacion_id = NULL,
            codigo_clinica = NULL
        WHERE id = ?
    """, (user_id,))
    db.commit()

    return jsonify({'success': 'Te has desvinculado exitosamente de la clínica. Tu perfil ha vuelto a ser Psicólogo Independiente.'})


@clinica_bp.route('/api/clinica/ajustes', methods=['PUT'])
def api_actualizar_ajustes_clinica():
    """Permite al Administrador actualizar nombre, descripción, logo y modo_whatsapp de la clínica."""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'No autorizado.'}), 401

    db = get_db()
    ensure_clinica_tables(db)
    cursor = db.cursor()

    cursor.execute("SELECT * FROM usuarios WHERE id = ?", (user_id,))
    usr = cursor.fetchone()
    if not usr or usr['tipo_clinica'] != 1 or not usr['organizacion_id']:
        return jsonify({'error': 'Acceso restringido al Psicólogo Administrador.'}), 403

    data = request.json or {}
    nombre = (data.get('nombre') or '').strip()
    descripcion = (data.get('descripcion') or '').strip()
    logo = (data.get('logo') or '').strip()
    modo_wa = (data.get('modo_whatsapp') or 'centralizado').strip().lower()

    if modo_wa not in ['centralizado', 'independiente']:
        modo_wa = 'centralizado'

    if not nombre:
        return jsonify({'error': 'El nombre de la clínica no puede estar vacío.'}), 400

    cursor.execute("""
        UPDATE organizaciones SET
            nombre = ?,
            descripcion = ?,
            logo = ?,
            modo_whatsapp = ?
        WHERE id = ?
    """, (nombre, descripcion, logo, modo_wa, usr['organizacion_id']))
    db.commit()

    return jsonify({'success': 'Ajustes de la clínica actualizados exitosamente.'})


# ==============================================================================
# ENDPOINTS PÚBLICOS DE LA CLÍNICA (RESERVA PÚBLICA)
# ==============================================================================

@clinica_bp.route('/api/public/clinica/<slug>', methods=['GET'])
def api_get_public_clinica(slug):
    """Retorna la información pública de la clínica y la lista de terapeutas activos para el portal de reservas."""
    db = get_db()
    ensure_clinica_tables(db)
    cursor = db.cursor()

    cursor.execute("SELECT * FROM organizaciones WHERE slug = ? OR codigo_clinica = ?", (slug, slug))
    org = cursor.fetchone()
    if not org:
        return jsonify({'error': 'Clínica no encontrada.'}), 404

    org_dict = dict(org)

    # Miembros activos expuestos en el directorio público
    cursor.execute("""
        SELECT id, nombres, apellidos, foto_titulo, nomenclatura, especialidades, biografia_corta
        FROM usuarios
        WHERE organizacion_id = ? AND activo = 1
        ORDER BY tipo_clinica ASC, nombres ASC
    """, (org_dict['id'],))
    miembros = [dict(r) for r in cursor.fetchall()]

    return jsonify({
        'clinica': {
            'id': org_dict['id'],
            'nombre': org_dict['nombre'],
            'slug': org_dict['slug'],
            'logo': org_dict['logo'] or '/static/logo.png',
            'descripcion': org_dict['descripcion'] or 'Centro de atención y salud mental especializada.'
        },
        'terapeutas': miembros
    })


# ==============================================================================
# SUPERVISIÓN Y CONSOLA DE SUPERADMIN JERÁRQUICA
# ==============================================================================

@clinica_bp.route('/api/superadmin/organizaciones/jerarquia', methods=['GET'])
def api_superadmin_jerarquia():
    """Retorna el árbol jerárquico para el SuperAdmin: Clínicas -> Admin -> Subgrupo e Independientes."""
    user_id = session.get('user_id')
    role = session.get('role', '')
    if not user_id or (role not in ['admin', 'superadmin'] and user_id != 1):
        return jsonify({'error': 'No autorizado.'}), 403

    db = get_db()
    ensure_clinica_tables(db)
    cursor = db.cursor()

    # 1. Traer todas las organizaciones registradas
    cursor.execute("SELECT * FROM organizaciones ORDER BY fecha_registro DESC")
    orgs = [dict(o) for o in cursor.fetchall()]

    for org in orgs:
        cursor.execute("""
            SELECT id, nombres, apellidos, cedula, username, role, tipo_clinica, activo, fecha_registro
            FROM usuarios
            WHERE organizacion_id = ?
            ORDER BY tipo_clinica ASC, nombres ASC
        """, (org['id'],))
        miembros = [dict(m) for m in cursor.fetchall()]
        org['admin'] = next((m for m in miembros if m['tipo_clinica'] == 1), None)
        org['subgrupo'] = [m for m in miembros if m['tipo_clinica'] == 2]

    # 2. Traer psicólogos independientes (tipo_clinica 0 o NULL)
    cursor.execute("""
        SELECT id, nombres, apellidos, cedula, username, role, tipo_clinica, activo, fecha_registro
        FROM usuarios
        WHERE (tipo_clinica = 0 OR tipo_clinica IS NULL) AND role != 'superadmin' AND id != 1
        ORDER BY nombres ASC
    """)
    independientes = [dict(i) for i in cursor.fetchall()]

    return jsonify({
        'organizaciones': orgs,
        'psicologos_independientes': independientes
    })


# ==============================================================================
# ESPACIOS FÍSICOS Y DASHBOARD CORPORATIVO
# ==============================================================================

@clinica_bp.route('/api/clinica/espacios-fisicos', methods=['GET', 'POST', 'PUT'])
def api_espacios_fisicos():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'No autorizado.'}), 401

    db = get_db()
    ensure_clinica_tables(db)
    cursor = db.cursor()

    cursor.execute("SELECT * FROM usuarios WHERE id = ?", (user_id,))
    usr = cursor.fetchone()
    if not usr or not usr['organizacion_id']:
        return jsonify({'error': 'No perteneces a ninguna clínica.'}), 400

    org_id = usr['organizacion_id']
    es_admin = (usr['tipo_clinica'] == 1)

    if request.method in ['POST', 'PUT']:
        if not es_admin:
            return jsonify({'error': 'Solo el Director Administrador puede modificar los espacios físicos.'}), 403

        data = request.json or {}
        espacios = data.get('espacios_fisicos', [])
        if isinstance(espacios, list):
            espacios_str = ", ".join([str(e).strip() for e in espacios if str(e).strip()])
        else:
            espacios_str = str(espacios).strip()

        if not espacios_str:
            espacios_str = "Consultorio 1, Consultorio 2"

        cursor.execute("UPDATE organizaciones SET espacios_fisicos = ? WHERE id = ?", (espacios_str, org_id))
        db.commit()
        return jsonify({'success': 'Espacios físicos actualizados exitosamente.', 'espacios_fisicos': [e.strip() for e in espacios_str.split(',') if e.strip()]})

    cursor.execute("SELECT espacios_fisicos FROM organizaciones WHERE id = ?", (org_id,))
    org = cursor.fetchone()
    raw_espacios = (org['espacios_fisicos'] if org and org['espacios_fisicos'] else 'Consultorio 1, Consultorio 2')
    espacios_list = [e.strip() for e in raw_espacios.split(',') if e.strip()]
    return jsonify({'espacios_fisicos': espacios_list, 'es_admin': es_admin})


@clinica_bp.route('/api/clinica/miembro/<int:miembro_id>/horarios', methods=['GET', 'POST'])
def api_miembro_horarios(miembro_id):
    """Permite al Director Administrador consultar o guardar la disponibilidad y asignación de consultorios de un terapeuta de su equipo."""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'No autorizado.'}), 401

    db = get_db()
    ensure_clinica_tables(db)
    cursor = db.cursor()

    cursor.execute("SELECT * FROM usuarios WHERE id = ?", (user_id,))
    usr = cursor.fetchone()
    if not usr or not usr['organizacion_id']:
        return jsonify({'error': 'No perteneces a ninguna clínica.'}), 400

    org_id = usr['organizacion_id']
    if usr['tipo_clinica'] != 1:
        return jsonify({'error': 'Solo el Director Administrador puede gestionar los horarios del equipo.'}), 403

    # Verificar que el miembro pertenece a la misma clínica
    cursor.execute("SELECT * FROM usuarios WHERE id = ? AND organizacion_id = ?", (miembro_id, org_id))
    m_usr = cursor.fetchone()
    if not m_usr:
        return jsonify({'error': 'El terapeuta especificado no pertenece a tu equipo de clínica.'}), 404

    cursor.execute("SELECT espacios_fisicos FROM organizaciones WHERE id = ?", (org_id,))
    org = cursor.fetchone()
    raw_espacios = (org['espacios_fisicos'] if org and org['espacios_fisicos'] else 'Consultorio 1, Consultorio 2')
    espacios_list = [e.strip() for e in raw_espacios.split(',') if e.strip()]

    if request.method == 'POST':
        import json
        data = request.json or {}
        vis_json = json.dumps(data)

        # Generar disponibilidad legacy si es necesario
        cursor.execute("UPDATE usuarios SET configuracion_horarios_visual = ? WHERE id = ?", (vis_json, miembro_id))
        db.commit()
        return jsonify({'success': 'Horarios del terapeuta actualizados exitosamente.'})

    # GET
    import json
    cfg = {}
    if m_usr['configuracion_horarios_visual']:
        try:
            cfg = json.loads(m_usr['configuracion_horarios_visual'])
        except:
            pass

    return jsonify({
        'miembro_id': miembro_id,
        'miembro_nombre': f"{m_usr['nombres']} {m_usr['apellidos']}".strip(),
        'configuracion': cfg,
        'espacios_fisicos': espacios_list
    })



@clinica_bp.route('/api/clinica/asignar-paciente', methods=['POST'])
def api_asignar_paciente_clinica():
    """Permite al Director Administrador o Terapeuta derivar/asignar un paciente a un psicólogo activo del equipo."""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'No autorizado.'}), 401

    db = get_db()
    ensure_clinica_tables(db)
    cursor = db.cursor()

    cursor.execute("SELECT * FROM usuarios WHERE id = ?", (user_id,))
    usr = cursor.fetchone()
    if not usr or not usr['organizacion_id']:
        return jsonify({'error': 'No perteneces a ninguna clínica.'}), 400

    org_id = usr['organizacion_id']
    data = request.json or {}
    patient_id = data.get('patient_id')
    target_psychologist_id = data.get('target_psychologist_id')

    if not patient_id or not target_psychologist_id:
        return jsonify({'error': 'Faltan parámetros requeridos (patient_id, target_psychologist_id).'}), 400

    # Verificar que el psicólogo destino pertenezca a la misma clínica
    cursor.execute("SELECT * FROM usuarios WHERE id = ? AND organizacion_id = ?", (target_psychologist_id, org_id))
    target_usr = cursor.fetchone()
    if not target_usr:
        return jsonify({'error': 'El psicólogo seleccionado no pertenece a tu clínica.'}), 400

    # Verificar que el paciente exista
    cursor.execute("SELECT * FROM pacientes WHERE id = ?", (patient_id,))
    pac = cursor.fetchone()
    if not pac:
        return jsonify({'error': 'Paciente no encontrado.'}), 404

    # Actualizar paciente asignándolo al psicólogo y a la clínica
    cursor.execute("""
        UPDATE pacientes SET
            psicologo_id = ?,
            organizacion_id = ?
        WHERE id = ?
    """, (target_psychologist_id, org_id, patient_id))
    db.commit()

    nombre_target = f"Psic. {target_usr['nombres']} {target_usr['apellidos']}".strip()
    return jsonify({
        'success': f"Paciente asignado exitosamente al {nombre_target}. Aparecerá de inmediato en sus Expedientes Clínicos.",
        'target_psychologist_name': nombre_target
    })


@clinica_bp.route('/api/clinica/dashboard-data', methods=['GET'])
def api_get_clinica_dashboard_data():
    """
    Retorna la información consolidada para el Dashboard Corporativo de la Clínica:
    - Agenda colectiva con consultorios (anonimizada para terapeutas, detallada para Director Admin)
    - Evoluciones y Tests (exclusivo para Director Admin)
    - Finanzas e Ingresos percibidos consolidados (exclusivo para Director Admin)
    """
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'No autorizado.'}), 401

    db = get_db()
    ensure_clinica_tables(db)
    cursor = db.cursor()

    cursor.execute("SELECT * FROM usuarios WHERE id = ?", (user_id,))
    usr = cursor.fetchone()
    if not usr or not usr['organizacion_id']:
        return jsonify({'error': 'No perteneces a ninguna clínica.'}), 400

    org_id = usr['organizacion_id']
    es_admin = (usr['tipo_clinica'] == 1)

    cursor.execute("SELECT * FROM organizaciones WHERE id = ?", (org_id,))
    org = cursor.fetchone()
    org_dict = dict(org) if org else {}

    raw_espacios = org_dict.get('espacios_fisicos') or 'Consultorio 1, Consultorio 2'
    espacios_list = [e.strip() for e in raw_espacios.split(',') if e.strip()]

    # 1. Obtener terapeutas de la clínica
    cursor.execute("""
        SELECT id, nombres, apellidos, cedula, username, foto_titulo, nomenclatura, especialidades, tipo_clinica, activo
        FROM usuarios
        WHERE organizacion_id = ? AND activo = 1
        ORDER BY tipo_clinica ASC, nombres ASC
    """, (org_id,))
    miembros = [dict(r) for r in cursor.fetchall()]
    miembros_ids = [m['id'] for m in miembros]

    # Map de nombres de psicólogos
    psych_names = {m['id']: f"{m.get('nomenclatura') or 'Psic.'} {m['nombres']} {m['apellidos']}".strip() for m in miembros}

    # 2. Agenda Colectiva (Eventos de la clínica o creados por sus miembros)
    if miembros_ids:
        placeholders = ','.join(['?'] * len(miembros_ids))
        cursor.execute(f"""
            SELECT a.*, p.nombres as paciente_nombres, p.apellidos as paciente_apellidos, p.cedula as paciente_cedula
            FROM agenda_finanzas a
            LEFT JOIN pacientes p ON a.paciente_id = p.id
            WHERE a.creado_por_user_id IN ({placeholders}) OR a.user_id IN ({placeholders}) OR a.organizacion_id = ?
            ORDER BY a.fecha ASC, a.hora ASC
        """, (*miembros_ids, *miembros_ids, org_id))
        agenda_raw = [dict(r) for r in cursor.fetchall()]
    else:
        agenda_raw = []

    agenda_colectiva = []
    for item in agenda_raw:
        creator_id = item.get('creado_por_user_id') or item.get('user_id')
        psych_name = psych_names.get(creator_id, 'Terapeuta de Equipo')
        consultorio = item.get('consultorio_nombre') or 'Consultorio 1'

        if es_admin or creator_id == user_id:
            # Director Admin o dueño de la cita ve detalle completo
            pac_nombre = f"{item.get('paciente_nombres') or ''} {item.get('paciente_apellidos') or ''}".strip() or item.get('concepto') or 'Consultante'
            agenda_colectiva.append({
                'id': item['id'],
                'fecha': item['fecha'],
                'hora': item['hora'],
                'psicologo_id': creator_id,
                'psicologo_nombre': psych_name,
                'consultorio': consultorio,
                'paciente_nombre': pac_nombre,
                'tipo_consulta': item.get('tipo_consulta') or 'Consulta',
                'estado_pago': item.get('estado_pago') or 'Pendiente',
                'monto': item.get('monto') or 0,
                'moneda': item.get('moneda') or 'USD',
                'es_propia': (creator_id == user_id)
            })
        else:
            # Integrante terapeuta ve slot anonimizado (Ocupado + Consultorio)
            agenda_colectiva.append({
                'id': item['id'],
                'fecha': item['fecha'],
                'hora': item['hora'],
                'psicologo_id': creator_id,
                'psicologo_nombre': psych_name,
                'consultorio': consultorio,
                'paciente_nombre': '🔒 Horario Ocupado',
                'tipo_consulta': 'Ocupado',
                'estado_pago': 'Reservado',
                'monto': 0,
                'moneda': 'USD',
                'es_propia': False
            })

    # 3. Datos exclusivos para el Director Administrador (Evoluciones Clínicas & Finanzas)
    evoluciones_clinicas = []
    finanzas_consolidadas = {
        'total_ingresos_percibidos': 0.0,
        'total_citas_realizadas': 0,
        'total_pendiente_cobro': 0.0,
        'ingresos_por_psicologo': {},
        'registros': []
    }

    if es_admin:
        # Importar descifrado clínico
        try:
            from app import decrypt_clinical_text
        except:
            def decrypt_clinical_text(txt): return txt or ''

        # Evoluciones Clínicas (Sesiones registradas por miembros de la clínica)
        if miembros_ids:
            placeholders = ','.join(['?'] * len(miembros_ids))
            cursor.execute(f"""
                SELECT s.*, p.nombres as paciente_nombres, p.apellidos as paciente_apellidos, u.nombres as psic_nombres, u.apellidos as psic_apellidos, u.nomenclatura as psic_nomenclatura
                FROM sesiones s
                JOIN pacientes p ON s.paciente_id = p.id
                JOIN usuarios u ON p.psicologo_id = u.id
                WHERE p.psicologo_id IN ({placeholders}) OR p.organizacion_id = ?
                ORDER BY s.fecha DESC
                LIMIT 50
            """, (*miembros_ids, org_id))
            sesiones_rows = cursor.fetchall()

            for s_row in sesiones_rows:
                s_dict = dict(s_row)
                resumen_dec = decrypt_clinical_text(s_dict.get('resumen'))
                diag_dec = decrypt_clinical_text(s_dict.get('diagnostico'))
                tests_dec = decrypt_clinical_text(s_dict.get('test_aplicados'))

                psych_title = f"{s_dict.get('psic_nomenclatura') or 'Psic.'} {s_dict.get('psic_nombres')} {s_dict.get('psic_apellidos')}".strip()
                pac_title = f"{s_dict.get('paciente_nombres')} {s_dict.get('paciente_apellidos')}".strip()

                evoluciones_clinicas.append({
                    'id': s_dict['id'],
                    'fecha': s_dict['fecha'],
                    'modalidad': s_dict.get('modalidad') or 'Presencial',
                    'estado': s_dict.get('estado') or 'Realizada',
                    'psicologo_nombre': psych_title,
                    'paciente_nombre': pac_title,
                    'resumen_tema': resumen_dec,
                    'diagnostico': diag_dec,
                    'tests_aplicados': tests_dec
                })

        # Finanzas consolidadas de la clínica
        for item in agenda_raw:
            creator_id = item.get('creado_por_user_id') or item.get('user_id')
            psych_name = psych_names.get(creator_id, 'Terapeuta de Equipo')
            monto = float(item.get('monto') or 0)
            estado = item.get('estado_pago') or 'Pendiente'
            pac_nombre = f"{item.get('paciente_nombres') or ''} {item.get('paciente_apellidos') or ''}".strip() or item.get('concepto') or 'Consultante'

            if estado in ['Pagado', 'Cobrado', 'Completado']:
                finanzas_consolidadas['total_ingresos_percibidos'] += monto
                finanzas_consolidadas['total_citas_realizadas'] += 1
                finanzas_consolidadas['ingresos_por_psicologo'][psych_name] = finanzas_consolidadas['ingresos_por_psicologo'].get(psych_name, 0.0) + monto
            else:
                finanzas_consolidadas['total_pendiente_cobro'] += monto

            finanzas_consolidadas['registros'].append({
                'fecha': item['fecha'],
                'psicologo_nombre': psych_name,
                'paciente_concepto': pac_nombre,
                'monto': monto,
                'moneda': item.get('moneda') or 'USD',
                'estado_pago': estado
            })

    return jsonify({
        'clinica': {
            'id': org_dict.get('id'),
            'nombre': org_dict.get('nombre'),
            'codigo_clinica': org_dict.get('codigo_clinica'),
            'slug': org_dict.get('slug'),
            'espacios_fisicos': espacios_list
        },
        'es_admin': es_admin,
        'miembros': miembros,
        'agenda_colectiva': agenda_colectiva,
        'evoluciones_clinicas': evoluciones_clinicas,
        'finanzas_consolidadas': finanzas_consolidadas
    })

