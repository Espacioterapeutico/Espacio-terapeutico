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
        if 'configuracion_horarios_visual' not in cols_usr:
            cursor.execute("ALTER TABLE usuarios ADD COLUMN configuracion_horarios_visual TEXT DEFAULT NULL")

    # 4. Migración de columnas en `organizaciones`
    cursor.execute("PRAGMA table_info(organizaciones)")
    cols_org = [r[1] for r in cursor.fetchall()]
    if cols_org:
        if 'espacios_fisicos' not in cols_org:
            cursor.execute("ALTER TABLE organizaciones ADD COLUMN espacios_fisicos TEXT DEFAULT 'Consultorio 1, Consultorio 2'")
        if 'direccion' not in cols_org:
            cursor.execute("ALTER TABLE organizaciones ADD COLUMN direccion TEXT DEFAULT NULL")
        if 'telefono' not in cols_org:
            cursor.execute("ALTER TABLE organizaciones ADD COLUMN telefono TEXT DEFAULT NULL")
        if 'email' not in cols_org:
            cursor.execute("ALTER TABLE organizaciones ADD COLUMN email TEXT DEFAULT NULL")
        if 'redes_sociales_json' not in cols_org:
            cursor.execute("ALTER TABLE organizaciones ADD COLUMN redes_sociales_json TEXT DEFAULT NULL")
        if 'mision' not in cols_org:
            cursor.execute("ALTER TABLE organizaciones ADD COLUMN mision TEXT DEFAULT NULL")
        if 'pais' not in cols_org:
            cursor.execute("ALTER TABLE organizaciones ADD COLUMN pais TEXT DEFAULT NULL")
        if 'instagram' not in cols_org:
            cursor.execute("ALTER TABLE organizaciones ADD COLUMN instagram TEXT DEFAULT NULL")

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

def crear_notificacion_interna_clinica(db, target_user_id, tipo, titulo, mensaje, link='#equipo'):
    """Registra una notificación en la base de datos para la campanita del usuario."""
    try:
        c = db.cursor()
        c.execute("""
            INSERT INTO notificaciones (user_id, tipo, titulo, mensaje, fecha, leida, link)
            VALUES (?, ?, ?, ?, datetime('now', 'localtime'), 0, ?)
        """, (target_user_id, tipo, titulo, mensaje, link))
    except Exception as e:
        print(f"Error al crear notificación interna de clínica para user #{target_user_id}: {e}")


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
    mision = (data.get('mision') or '').strip()
    pais = (data.get('pais') or '').strip()
    instagram = (data.get('instagram') or '').strip()
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
            INSERT INTO organizaciones (nombre, slug, logo, descripcion, mision, pais, instagram, admin_user_id, codigo_clinica)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (nombre, slug, logo, descripcion, mision, pais, instagram, user_id, code))
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
        SELECT id, nombres, apellidos, cedula, username, foto_titulo, nomenclatura, especialidades, biografia_corta, tipo_clinica, activo, slug
        FROM usuarios
        WHERE organizacion_id = ?
        ORDER BY tipo_clinica ASC, nombres ASC
    """, (org_id,))
    miembros = []
    for r in cursor.fetchall():
        m = dict(r)
        m['perfil_url'] = f"/directorio/psicologo/{m['slug']}" if m.get('slug') else f"/perfil/{m['id']}"
        miembros.append(m)
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

    clean_busqueda = busqueda.replace('.', '').replace('-', '').replace(' ', '').lower()
    clean_busqueda_num = clean_busqueda[1:] if (clean_busqueda.startswith('v') or clean_busqueda.startswith('e') or clean_busqueda.startswith('j')) else clean_busqueda

    # Buscar usuario por Cédula, ID, username o email
    cursor.execute("""
        SELECT * FROM usuarios
        WHERE id = ? 
           OR LOWER(cedula) = LOWER(?)
           OR REPLACE(REPLACE(REPLACE(LOWER(cedula), '.', ''), '-', ''), ' ', '') = ?
           OR REPLACE(REPLACE(REPLACE(LOWER(cedula), '.', ''), '-', ''), ' ', '') = ?
           OR REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LOWER(cedula), 'v-', ''), 'e-', ''), '.', ''), '-', ''), ' ', '') = ?
           OR LOWER(username) = LOWER(?)
           OR LOWER(email) = LOWER(?)
    """, (busqueda, busqueda, clean_busqueda, clean_busqueda_num, clean_busqueda_num, busqueda, busqueda))
    target_usr = cursor.fetchone()

    if not target_usr:
        return jsonify({'error': f'No se encontró ningún psicólogo registrado con la Cédula/ID "{busqueda}". El profesional debe haberse registrado previamente en la plataforma. También puedes invitarlo usando el "Enlace de Registro Dirigido".'}), 404

    target_id = target_usr['id']
    if target_id == user_id:
        return jsonify({'error': f'¡La Cédula/ID "{busqueda}" pertenece a tu propio usuario ({target_usr["nombres"]} {target_usr["apellidos"]})! Ya eres la Directora Administradora de esta clínica.'}), 400

    if target_usr['organizacion_id'] == admin_usr['organizacion_id']:
        return jsonify({'error': f'El Psic. {target_usr["nombres"]} {target_usr["apellidos"]} (#${target_id}) ya es parte de tu equipo de clínica.'}), 400

    # Verificar si ya existe una solicitud pendiente
    cursor.execute("""
        SELECT id, estado FROM equipo_solicitudes
        WHERE organizacion_id = ? AND user_id = ? AND estado = 'pendiente'
    """, (admin_usr['organizacion_id'], target_id))
    sol_exist = cursor.fetchone()
    if sol_exist:
        return jsonify({'error': f'Ya existe una invitación pendiente enviada a {target_usr["nombres"]} {target_usr["apellidos"]}.'}), 400

    cursor.execute("""
        INSERT INTO equipo_solicitudes (organizacion_id, user_id, solicitante_id, tipo_solicitud, estado)
        VALUES (?, ?, ?, 'invitacion', 'pendiente')
    """, (admin_usr['organizacion_id'], target_id, user_id))
    
    crear_notificacion_interna_clinica(
        db, target_id, 'invitacion_clinica', '🏢 Invitación a Clínica',
        f"El Psic. {admin_usr['nombres']} {admin_usr['apellidos']} te ha invitado a unirte a su equipo de clínica. Revisa Ajustes -> Equipo de Trabajo para responder.",
        '#equipo'
    )
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

    if org and org['admin_user_id']:
        crear_notificacion_interna_clinica(
            db, org['admin_user_id'], 'solicitud_clinica', '📩 Solicitud de Ingreso a Clínica',
            f"Un terapeuta ha ingresado tu código para solicitar unirse a tu clínica '{org['nombre']}'. Revisa Ajustes -> Equipo de Trabajo para responder.",
            '#equipo'
        )
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

        if sol['tipo_solicitud'] == 'invitacion':
            admin_id = org['admin_user_id']
            if admin_id:
                crear_notificacion_interna_clinica(
                    db, admin_id, 'respuesta_clinica',
                    f"{'🎉 Invitación Aceptada' if accion == 'aceptar' else '❌ Invitación Rechazada'}",
                    f"El terapeuta ha {accion}do tu invitación para unirse a '{org['nombre']}'.",
                    '#equipo'
                )
        else:
            solicitante_id = sol['user_id']
            if solicitante_id:
                crear_notificacion_interna_clinica(
                    db, solicitante_id, 'respuesta_clinica',
                    f"{'🎉 Solicitud Aprobada' if accion == 'aceptar' else '❌ Solicitud Rechazada'}",
                    f"La clínica '{org['nombre']}' ha {accion}do tu solicitud de ingreso.",
                    '#equipo'
                )

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
    """Permite al Administrador actualizar nombre, descripción, logo, dirección, teléfono, email y modo_whatsapp de la clínica."""
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
    mision = (data.get('mision') or '').strip()
    pais = (data.get('pais') or '').strip()
    direccion = (data.get('direccion') or '').strip()
    telefono = (data.get('telefono') or '').strip()
    email = (data.get('email') or '').strip()
    instagram = (data.get('instagram') or '').strip()
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
            mision = ?,
            pais = ?,
            direccion = ?,
            telefono = ?,
            email = ?,
            instagram = ?,
            logo = ?,
            modo_whatsapp = ?
        WHERE id = ?
    """, (nombre, descripcion, mision, pais, direccion, telefono, email, instagram, logo, modo_wa, usr['organizacion_id']))
    db.commit()

    return jsonify({'success': 'Ajustes de la clínica actualizados exitosamente.'})


@clinica_bp.route('/api/clinica/miembro/<int:target_user_id>/remover', methods=['POST'])
def api_remover_miembro_clinica(target_user_id):
    """Permite al Psicólogo Administrador remover a un psicólogo afiliado del equipo."""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'No autorizado.'}), 401

    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT tipo_clinica, organizacion_id FROM usuarios WHERE id = ?", (user_id,))
    admin_usr = cursor.fetchone()
    if not admin_usr or admin_usr['tipo_clinica'] != 1 or not admin_usr['organizacion_id']:
        return jsonify({'error': 'Solo el Director Administrador puede desvincular miembros.'}), 403

    if target_user_id == user_id:
        return jsonify({'error': 'No puedes eliminarte a ti mismo. Para desmantelar la clínica usa la opción Eliminar Clínica.'}), 400

    cursor.execute("SELECT id, nombres, apellidos, organizacion_id FROM usuarios WHERE id = ?", (target_user_id,))
    target_usr = cursor.fetchone()
    if not target_usr or target_usr['organizacion_id'] != admin_usr['organizacion_id']:
        return jsonify({'error': 'El terapeuta no pertenece a esta clínica.'}), 404

    cursor.execute("""
        UPDATE usuarios SET
            tipo_clinica = 0,
            organizacion_id = NULL,
            codigo_clinica = NULL
        WHERE id = ?
    """, (target_user_id,))
    db.commit()

    return jsonify({'success': f"Psicólogo '{target_usr['nombres']} {target_usr['apellidos']}' ha sido desvinculado de la clínica."})



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


@clinica_bp.route('/api/clinica/espacios-fisicos/agregar', methods=['POST'])
def api_espacios_fisicos_agregar():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'No autorizado.'}), 401

    db = get_db()
    ensure_clinica_tables(db)
    cursor = db.cursor()

    cursor.execute("SELECT * FROM usuarios WHERE id = ?", (user_id,))
    usr = cursor.fetchone()
    if not usr or usr['tipo_clinica'] != 1 or not usr['organizacion_id']:
        return jsonify({'error': 'Solo el Director Administrador puede modificar los espacios físicos.'}), 403

    org_id = usr['organizacion_id']
    data = request.json or {}
    nuevo_nombre = (data.get('nombre') or '').strip()
    if not nuevo_nombre:
        return jsonify({'error': 'Ingrese el nombre del nuevo consultorio.'}), 400

    cursor.execute("SELECT espacios_fisicos FROM organizaciones WHERE id = ?", (org_id,))
    org = cursor.fetchone()
    raw_espacios = (org['espacios_fisicos'] if org and org['espacios_fisicos'] else '')
    espacios = [e.strip() for e in raw_espacios.split(',') if e.strip()]

    if nuevo_nombre in espacios:
        return jsonify({'error': f'El consultorio "{nuevo_nombre}" ya existe.'}), 400

    espacios.append(nuevo_nombre)
    espacios_str = ", ".join(espacios)
    cursor.execute("UPDATE organizaciones SET espacios_fisicos = ? WHERE id = ?", (espacios_str, org_id))
    db.commit()

    return jsonify({'success': f'Consultorio "{nuevo_nombre}" agregado exitosamente.', 'espacios_fisicos': espacios})


@clinica_bp.route('/api/clinica/espacios-fisicos/renombrar', methods=['POST'])
def api_espacios_fisicos_renombrar():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'No autorizado.'}), 401

    db = get_db()
    ensure_clinica_tables(db)
    cursor = db.cursor()

    cursor.execute("SELECT * FROM usuarios WHERE id = ?", (user_id,))
    usr = cursor.fetchone()
    if not usr or usr['tipo_clinica'] != 1 or not usr['organizacion_id']:
        return jsonify({'error': 'Solo el Director Administrador puede modificar los espacios físicos.'}), 403

    org_id = usr['organizacion_id']
    data = request.json or {}
    nombre_anterior = (data.get('nombre_anterior') or '').strip()
    nombre_nuevo = (data.get('nombre_nuevo') or '').strip()

    if not nombre_anterior or not nombre_nuevo:
        return jsonify({'error': 'Debe especificar el nombre actual y el nuevo nombre.'}), 400

    cursor.execute("SELECT espacios_fisicos FROM organizaciones WHERE id = ?", (org_id,))
    org = cursor.fetchone()
    raw_espacios = (org['espacios_fisicos'] if org and org['espacios_fisicos'] else '')
    espacios = [e.strip() for e in raw_espacios.split(',') if e.strip()]

    if nombre_anterior not in espacios:
        return jsonify({'error': f'No se encontró el consultorio "{nombre_anterior}".'}), 404

    nuevos_espacios = [nombre_nuevo if e == nombre_anterior else e for e in espacios]
    espacios_str = ", ".join(nuevos_espacios)
    cursor.execute("UPDATE organizaciones SET espacios_fisicos = ? WHERE id = ?", (espacios_str, org_id))
    db.commit()

    return jsonify({'success': f'Consultorio renombrado de "{nombre_anterior}" a "{nombre_nuevo}".', 'espacios_fisicos': nuevos_espacios})


@clinica_bp.route('/api/clinica/espacios-fisicos/eliminar', methods=['POST'])
def api_espacios_fisicos_eliminar():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'No autorizado.'}), 401

    db = get_db()
    ensure_clinica_tables(db)
    cursor = db.cursor()

    cursor.execute("SELECT * FROM usuarios WHERE id = ?", (user_id,))
    usr = cursor.fetchone()
    if not usr or usr['tipo_clinica'] != 1 or not usr['organizacion_id']:
        return jsonify({'error': 'Solo el Director Administrador puede modificar los espacios físicos.'}), 403

    org_id = usr['organizacion_id']
    data = request.json or {}
    nombre = (data.get('nombre') or '').strip()
    if not nombre:
        return jsonify({'error': 'Debe especificar el consultorio a eliminar.'}), 400

    cursor.execute("SELECT espacios_fisicos FROM organizaciones WHERE id = ?", (org_id,))
    org = cursor.fetchone()
    raw_espacios = (org['espacios_fisicos'] if org and org['espacios_fisicos'] else '')
    espacios = [e.strip() for e in raw_espacios.split(',') if e.strip()]

    nuevos_espacios = [e for e in espacios if e != nombre]
    espacios_str = ", ".join(nuevos_espacios)
    cursor.execute("UPDATE organizaciones SET espacios_fisicos = ? WHERE id = ?", (espacios_str, org_id))
    db.commit()

    return jsonify({'success': f'Consultorio "{nombre}" eliminado exitosamente.', 'espacios_fisicos': nuevos_espacios})


@clinica_bp.route('/api/clinica/miembro/<int:miembro_id>/horarios', methods=['GET', 'POST'])
def api_miembro_horarios(miembro_id):
    """Permite al Director Administrador o al propio terapeuta consultar o guardar su disponibilidad y asignación de consultorios."""
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
        if not es_admin and user_id != miembro_id:
            return jsonify({'error': 'Solo el Director Administrador o el propio terapeuta pueden modificar este horario.'}), 403

        import json
        data = request.json or {}

        # Mapeo para generar perfil de disponibilidad autómata para la autoagenda
        DAY_MAP = [
            ('domingo', 0, 'Domingo'),
            ('lunes', 1, 'Lunes'),
            ('martes', 2, 'Martes'),
            ('miercoles', 3, 'Miércoles'),
            ('jueves', 4, 'Jueves'),
            ('viernes', 5, 'Viernes'),
            ('sabado', 6, 'Sábado')
        ]

        profile_dias = []
        for key, dia_num, dia_name in DAY_MAP:
            day_cfg = data.get(key, {})
            is_active = bool(day_cfg.get('activo', False))
            inicio = day_cfg.get('inicio', '08:00')
            fin = day_cfg.get('fin', '17:00')
            
            rangos = []
            if is_active and inicio and fin:
                rangos.append({'inicio': inicio, 'fin': fin})
                
            profile_dias.append({
                'dia': dia_num,
                'nombre': dia_name,
                'activo': is_active,
                'rangos': rangos
            })

        primary_consultorio = "Consultorio 1"
        for key in ['lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado', 'domingo']:
            if data.get(key, {}).get('activo'):
                primary_consultorio = data.get(key, {}).get('consultorio', 'Consultorio 1')
                break

        cursor.execute("SELECT nombre FROM organizaciones WHERE id = ?", (org_id,))
        org_row = cursor.fetchone()
        org_name = org_row['nombre'] if org_row and org_row['nombre'] else "Clínica"

        clinic_profile = {
            'id': 'perf_clinica_' + str(org_id),
            'nombre': f"Horario {org_name}",
            'modalidad': 'Presencial',
            'consultorio': primary_consultorio,
            'dias': profile_dias,
            'es_horario_clinica': True
        }

        # Preservar o actualizar la estructura combinada (días + perfiles)
        existing_other_perfiles = []
        if m_usr['configuracion_horarios_visual']:
            try:
                old_cfg = json.loads(m_usr['configuracion_horarios_visual'])
                if isinstance(old_cfg.get('perfiles'), list):
                    existing_other_perfiles = [p for p in old_cfg['perfiles'] if not p.get('es_horario_clinica') and p.get('id') != clinic_profile['id']]
            except Exception:
                pass

        if not existing_other_perfiles:
            existing_other_perfiles = [
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
                }
            ]

        final_config = {
            'lunes': data.get('lunes', {}),
            'martes': data.get('martes', {}),
            'miercoles': data.get('miercoles', {}),
            'jueves': data.get('jueves', {}),
            'viernes': data.get('viernes', {}),
            'sabado': data.get('sabado', {}),
            'domingo': data.get('domingo', {}),
            'perfiles': [clinic_profile] + existing_other_perfiles,
            'duracion': 60,
            'receso': 15
        }

        vis_json = json.dumps(final_config)

        cursor.execute("UPDATE usuarios SET configuracion_horarios_visual = ? WHERE id = ?", (vis_json, miembro_id))
        db.commit()
        return jsonify({'success': 'Horarios y consultorios del terapeuta actualizados exitosamente.'})

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


@clinica_bp.route('/api/clinica/horarios-equipo', methods=['GET'])
def api_horarios_equipo():
    """Retorna los horarios y consultorios asignados de todos los miembros del equipo de la clínica."""
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
    cursor.execute("""
        SELECT id, nombres, apellidos, nomenclatura, configuracion_horarios_visual
        FROM usuarios
        WHERE organizacion_id = ?
        ORDER BY nombres ASC
    """, (org_id,))
    
    import json
    resultado = []
    for r in cursor.fetchall():
        m = dict(r)
        cfg = {}
        if m['configuracion_horarios_visual']:
            try:
                cfg = json.loads(m['configuracion_horarios_visual'])
            except:
                pass
        m['configuracion'] = cfg
        resultado.append(m)

    return jsonify({'horarios_equipo': resultado})

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

    # 2. Agenda Colectiva (Eventos de la clínica o asignados a pacientes de la clínica)
    if miembros_ids:
        placeholders = ','.join(['?'] * len(miembros_ids))
        cursor.execute(f"""
            SELECT a.*, p.nombres as paciente_nombres, p.apellidos as paciente_apellidos, p.cedula as paciente_cedula
            FROM agenda_finanzas a
            LEFT JOIN pacientes p ON a.paciente_id = p.id
            WHERE a.organizacion_id = ? OR (p.organizacion_id = ? AND a.creado_por_user_id IN ({placeholders}))
            ORDER BY a.fecha ASC, a.hora ASC
        """, (org_id, org_id, *miembros_ids))
        agenda_raw = [dict(r) for r in cursor.fetchall()]
    else:
        agenda_raw = []

    agenda_colectiva = []
    for item in agenda_raw:
        creator_id = item.get('creado_por_user_id')
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

    # 3. Datos exclusivos para el Director Administrador (Evoluciones Clínicas, Pacientes Activos & Finanzas de la Clínica)
    evoluciones_clinicas = []
    pacientes_activos = []
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

        # Pacientes Activos de la Clínica (EXCLUSIVAMENTE pacientes cuya organizacion_id coincida con la clínica)
        cursor.execute("""
            SELECT p.id, p.nombres, p.apellidos, p.cedula, p.telefono, p.costo_personalizado, p.moneda_personalizada, p.psicologo_id,
                   u.nombres as psic_nombres, u.apellidos as psic_apellidos, u.nomenclatura as psic_nomenclatura
            FROM pacientes p
            LEFT JOIN usuarios u ON p.psicologo_id = u.id
            WHERE p.organizacion_id = ?
            ORDER BY p.nombres ASC, p.apellidos ASC
        """, (org_id,))
        pac_rows = cursor.fetchall()
        for pr in pac_rows:
            p_dict = dict(pr)
            pac_id = p_dict['id']
            psych_name = f"{p_dict.get('psic_nomenclatura') or 'Psic.'} {p_dict.get('psic_nombres') or ''} {p_dict.get('psic_apellidos') or ''}".strip()
            if not psych_name or psych_name == 'Psic.':
                psych_name = 'Sin Psicólogo Asignado'

            costo = float(p_dict.get('costo_personalizado') or 0)
            moneda = p_dict.get('moneda_personalizada') or 'USD'

            if costo == 0:
                cursor.execute("SELECT monto, moneda FROM agenda_finanzas WHERE paciente_id = ? AND monto > 0 ORDER BY fecha DESC LIMIT 1", (pac_id,))
                last_fee = cursor.fetchone()
                if last_fee:
                    costo = float(last_fee['monto'] or 0)
                    moneda = last_fee['moneda'] or 'USD'

            pacientes_activos.append({
                'id': pac_id,
                'nombre_completo': f"{p_dict['nombres']} {p_dict['apellidos']}".strip(),
                'cedula': p_dict.get('cedula') or 'Sin Cédula',
                'telefono': p_dict.get('telefono') or '',
                'psicologo_id': p_dict.get('psicologo_id'),
                'psicologo_asignado': psych_name,
                'costo_consulta': costo,
                'moneda': moneda
            })

        # Evoluciones Clínicas (Sesiones registradas EXCLUSIVAMENTE para pacientes de la clínica)
        if miembros_ids:
            cursor.execute("""
                SELECT s.*, p.nombres as paciente_nombres, p.apellidos as paciente_apellidos, u.nombres as psic_nombres, u.apellidos as psic_apellidos, u.nomenclatura as psic_nomenclatura
                FROM sesiones s
                JOIN pacientes p ON s.paciente_id = p.id
                JOIN usuarios u ON p.psicologo_id = u.id
                WHERE p.organizacion_id = ?
                ORDER BY s.fecha DESC
                LIMIT 50
            """, (org_id,))
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
        'pacientes_activos': pacientes_activos,
        'agenda_colectiva': agenda_colectiva,
        'evoluciones_clinicas': evoluciones_clinicas,
        'finanzas_consolidadas': finanzas_consolidadas
    })

