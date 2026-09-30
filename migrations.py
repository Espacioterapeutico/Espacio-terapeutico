"""
Módulo de Migraciones y Motor de Sincronización de Reglas Retroactivas.
----------------------------------------------------------------------
Este módulo gestiona:
1. Migraciones de esquema y datos versionadas (se ejecutan una sola vez en producción/Render).
2. Inicialización automática de herramientas y tests para pacientes ya registrados.
3. Propagación retroactiva de reglas de agenda y cancelación a citas ya creadas.
"""

import json
import secrets
from datetime import datetime, timezone, timedelta

def init_migrations_table(cursor):
    """Crea la tabla de control de migraciones si no existe."""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            migration_id TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL,
            description TEXT
        )
    """)

def sync_psychologist_rules_to_appointments(cursor, db, psicologo_id, config_dict=None):
    """
    HOOK / REGLA RETROACTIVA:
    Sincroniza las citas futuras/activas de un psicólogo con su configuración actual de reglas.
    
    1. Asegura que creado_por_user_id sea el ID numérico del psicólogo.
    2. Asegura que todas las citas activas tengan su token_confirmacion generado.
    3. Si alguna cita futura fue auto-cancelada pero según la nueva regla aún está vigente,
       la restaura a 'Agendada' y elimina el bloqueo de citas_canceladas_log.
    4. Garantiza que todos los pacientes de ese psicólogo tengan su psicologo_id numérico.
    """
    if not psicologo_id:
        return 0

    try:
        psic_id = int(psicologo_id)
    except (ValueError, TypeError):
        return 0

    if config_dict is None:
        cursor.execute("SELECT configuracion_horarios_visual FROM usuarios WHERE id = ?", (psic_id,))
        row = cursor.fetchone()
        if row and row[0]:
            try:
                config_dict = json.loads(row[0])
            except:
                config_dict = {}
        else:
            config_dict = {}

    rule_type = config_dict.get('limite_auto_cancelacion_tipo') or config_dict.get('limite_cancelacion_tipo', 'horas')
    rule_value = config_dict.get('limite_auto_cancelacion_valor') if config_dict.get('limite_auto_cancelacion_valor') is not None else config_dict.get('limite_cancelacion_valor', 24)

    try:
        import zoneinfo
        tz = zoneinfo.ZoneInfo("America/Caracas")
        now_dt = datetime.now(tz).replace(tzinfo=None)
    except Exception:
        now_dt = datetime.now(timezone(timedelta(hours=-4))).replace(tzinfo=None)

    today_str = now_dt.strftime("%Y-%m-%d")

    # 1. Asegurar normalización de pacientes del psicólogo
    cursor.execute("""
        UPDATE pacientes 
        SET psicologo_id = ? 
        WHERE (psicologo_id = ? OR CAST(psicologo_id AS TEXT) = ?)
    """, (psic_id, psic_id, str(psic_id)))

    # 2. Buscar todas las citas a partir de hoy asignadas a este psicólogo
    cursor.execute("""
        SELECT af.id, af.paciente_id, af.fecha, af.hora, af.estado_pago, af.confirmada, 
               af.token_confirmacion, af.referencia, af.google_event_id, p.nombres, p.apellidos, af.tipo_consulta
        FROM agenda_finanzas af
        JOIN pacientes p ON af.paciente_id = p.id
        WHERE (p.psicologo_id = ? OR af.creado_por_user_id = ? OR CAST(af.creado_por_user_id AS TEXT) = ?)
          AND af.fecha >= ?
    """, (psic_id, psic_id, str(psic_id), today_str))

    appointments = cursor.fetchall()
    updated_count = 0

    from routes_pacientes import get_deadline_datetime

    for appt in appointments:
        appt_id = appt['id'] if hasattr(appt, 'keys') else appt[0]
        pac_id = appt['paciente_id'] if hasattr(appt, 'keys') else appt[1]
        fecha_cita = appt['fecha'] if hasattr(appt, 'keys') else appt[2]
        hora_cita = appt['hora'] if hasattr(appt, 'keys') else appt[3]
        estado_pago = appt['estado_pago'] if hasattr(appt, 'keys') else appt[4]
        token_conf = appt['token_confirmacion'] if hasattr(appt, 'keys') else appt[6]
        gev_id = appt['google_event_id'] if hasattr(appt, 'keys') else appt[8]
        p_nombres = appt['nombres'] if hasattr(appt, 'keys') else ""
        p_apellidos = appt['apellidos'] if hasattr(appt, 'keys') else ""
        tipo_cons = appt['tipo_consulta'] if hasattr(appt, 'keys') else None

        # Asegurar token de confirmación si no tenía
        if not token_conf or len(str(token_conf).strip()) < 8:
            new_token = secrets.token_urlsafe(16)
            cursor.execute("UPDATE agenda_finanzas SET token_confirmacion = ? WHERE id = ?", (new_token, appt_id))
            updated_count += 1

        # Asegurar que creado_por_user_id sea numérico
        cursor.execute("UPDATE agenda_finanzas SET creado_por_user_id = ? WHERE id = ? AND (creado_por_user_id IS NULL OR creado_por_user_id != ?)", (psic_id, appt_id, psic_id))

        # Evaluar plazo de cancelación según la regla actual
        if hora_cita and hora_cita != '00:00':
            deadline_dt = get_deadline_datetime(fecha_cita, hora_cita, rule_type, rule_value)

            # Si la cita fue cancelada automáticamente por el sistema pero aún NO vence el plazo según la nueva regla:
            # ¡Se restaura automáticamente!
            if estado_pago == 'Cancelada con aviso' and now_dt < deadline_dt:
                cursor.execute("""
                    UPDATE agenda_finanzas 
                    SET estado_pago = 'Agendada', confirmada = 0,
                        referencia = CASE 
                            WHEN referencia LIKE '%Cancelada automáticamente por falta de confirmación%'
                            THEN REPLACE(referencia, ' | Cancelada automáticamente por falta de confirmación', '')
                            ELSE referencia
                        END
                    WHERE id = ?
                """, (appt_id,))
                
                cursor.execute("DELETE FROM citas_canceladas_log WHERE agenda_id = ?", (appt_id,))
                cursor.execute("DELETE FROM sesiones WHERE agenda_id = ? AND resumen LIKE '%cancelada automáticamente%'", (appt_id,))
                
                if gev_id:
                    try:
                        from routes_admin import get_calendar_service, update_calendar_event_status
                        serv = get_calendar_service(psic_id)
                        if serv:
                            update_calendar_event_status(serv, gev_id, 'pendiente', paciente_nombre=f"{p_nombres} {p_apellidos}", tipo_consulta=tipo_cons)
                    except Exception as ge:
                        print(f"[RULES_SYNC] Error reactivando evento Calendar {gev_id}: {ge}")

                updated_count += 1

    if db and updated_count > 0:
        db.commit()

    return updated_count


# ==============================================================================
# DEFINICIÓN DE MIGRACIONES VERSIONADAS (Se ejecutan una única vez)
# ==============================================================================

def m_0001_heal_slugs_and_times(cursor, db):
    """Cura registros con slugs de texto y normaliza horas históricas a formato 24h."""
    from app import heal_orphaned_slug_records
    heal_orphaned_slug_records(cursor, db)

    cursor.execute("SELECT id, hora FROM agenda_finanzas WHERE hora IS NOT NULL AND hora != '' AND hora != '00:00'")
    rows = cursor.fetchall()
    from routes_agenda import normalize_time_str
    for r in rows:
        old_h = str(r[1]).strip()
        norm_h = normalize_time_str(old_h)
        if old_h != norm_h and norm_h != '00:00':
            cursor.execute("UPDATE agenda_finanzas SET hora = ? WHERE id = ?", (norm_h, r[0]))

def m_0002_ensure_clinical_tools_and_existing_patients(cursor, db):
    """
    Asegura las tablas de herramientas clínicas, recordatorios y tests psicológicos,
    garantizando que todos los pacientes ya registrados tengan sus valores base consistentes.
    """
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cola_recordatorios_herramientas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            psicologo_id INTEGER NOT NULL,
            paciente_id INTEGER NOT NULL,
            herramienta_tipo TEXT NOT NULL,
            fecha_programada DATE NOT NULL,
            hora_programada TEXT DEFAULT '20:00',
            estado TEXT DEFAULT 'programado',
            enviado INTEGER DEFAULT 0,
            fecha_envio DATETIME NULL,
            token_id INTEGER NULL,
            pausado INTEGER DEFAULT 0,
            fecha_registro DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(paciente_id, herramienta_tipo, fecha_programada)
        )
    """)

    # Columnas en tokens_herramientas
    cursor.execute("PRAGMA table_info(tokens_herramientas)")
    th_cols = [r[1] for r in cursor.fetchall()]
    if 'fecha_completado' not in th_cols:
        cursor.execute("ALTER TABLE tokens_herramientas ADD COLUMN fecha_completado DATETIME NULL")
    if 'fecha_registro' not in th_cols:
        cursor.execute("ALTER TABLE tokens_herramientas ADD COLUMN fecha_registro DATETIME NULL")

    # Valores por defecto para pacientes existentes
    cursor.execute("UPDATE pacientes SET terminos_aceptados = 0 WHERE terminos_aceptados IS NULL")
    cursor.execute("UPDATE pacientes SET psicologo_id = 1 WHERE psicologo_id IS NULL")

def m_0003_restore_aiverson_and_cancelled_log(cursor, db):
    """Restauración puntual y segura de la cita de Aiverson si fue auto-cancelada indebidamente."""
    cursor.execute("""
        SELECT af.id, af.google_event_id, p.id as pac_id, p.nombres, p.apellidos, af.tipo_consulta
        FROM agenda_finanzas af
        JOIN pacientes p ON af.paciente_id = p.id
        WHERE (af.id = 269 OR LOWER(p.nombres) LIKE '%aiverson%' OR p.cedula IN ('30590594', '30.590.594', 'V-30590594', 'V-30.590.594'))
          AND af.fecha = '2026-10-01'
          AND af.estado_pago = 'Cancelada con aviso'
    """)
    to_restore = cursor.fetchall()
    for r in to_restore:
        appt_id = r['id'] if hasattr(r, 'keys') else r[0]
        gev_id = r['google_event_id'] if hasattr(r, 'keys') else r[1]
        p_nom = f"{r['nombres']} {r['apellidos']}" if hasattr(r, 'keys') else ""
        t_cons = r['tipo_consulta'] if hasattr(r, 'keys') else None

        cursor.execute("""
            UPDATE agenda_finanzas 
            SET estado_pago = 'Agendada', confirmada = 0,
                referencia = CASE 
                    WHEN referencia LIKE '%Cancelada automáticamente por falta de confirmación%'
                    THEN REPLACE(referencia, ' | Cancelada automáticamente por falta de confirmación', '')
                    ELSE referencia
                END
            WHERE id = ?
        """, (appt_id,))

        cursor.execute("DELETE FROM citas_canceladas_log WHERE agenda_id = ?", (appt_id,))
        cursor.execute("DELETE FROM sesiones WHERE agenda_id = ? AND resumen LIKE '%cancelada automáticamente%'", (appt_id,))

        if gev_id:
            try:
                from routes_admin import get_calendar_service, update_calendar_event_status
                serv = get_calendar_service(1)
                if serv:
                    update_calendar_event_status(serv, gev_id, 'pendiente', paciente_nombre=p_nom, tipo_consulta=t_cons)
            except Exception as _ge:
                print(f"[MIGRATION_0003] Error Calendar: {_ge}")

def m_0004_propagate_all_psychologist_rules(cursor, db):
    """Propaga retroactivamente las reglas actuales de todos los psicólogos a sus citas vigentes."""
    cursor.execute("SELECT id, configuracion_horarios_visual FROM usuarios WHERE role IN ('psicologo', 'admin', 'psicologo_admin')")
    users = cursor.fetchall()
    for u in users:
        uid = u['id'] if hasattr(u, 'keys') else u[0]
        cfg_raw = u['configuracion_horarios_visual'] if hasattr(u, 'keys') else u[1]
        cfg = {}
        if cfg_raw:
            try:
                cfg = json.loads(cfg_raw)
            except:
                pass
        sync_psychologist_rules_to_appointments(cursor, db, uid, cfg)


# LISTA MAESTRA DE MIGRACIONES EN ORDEN CRONOLÓGICO
MIGRATIONS = [
    ("0001_heal_slugs_and_times", "Cura de slugs huérfanos y normalización de horarios 24h", m_0001_heal_slugs_and_times),
    ("0002_ensure_clinical_tools_and_patients", "Asegurar tablas de herramientas clínicas y consistencia en pacientes viejos", m_0002_ensure_clinical_tools_and_existing_patients),
    ("0003_restore_aiverson_appointment", "Restauración de cita y log de confirmación para Aiverson", m_0003_restore_aiverson_and_cancelled_log),
    ("0004_propagate_all_psychologist_rules", "Propagación retroactiva de reglas a todas las citas activas", m_0004_propagate_all_psychologist_rules),
]


def run_migrations(db):
    """
    Punto de entrada ejecutado en el arranque de la aplicación (init_db).
    Aplica únicamente las migraciones pendientes y las registra en schema_migrations.
    """
    cursor = db.cursor()
    init_migrations_table(cursor)
    db.commit()

    cursor.execute("SELECT migration_id FROM schema_migrations")
    applied = set(row[0] for row in cursor.fetchall())

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for mig_id, desc, mig_func in MIGRATIONS:
        if mig_id not in applied:
            print(f"[MIGRATION] Aplicando migración: {mig_id} ({desc})...")
            try:
                mig_func(cursor, db)
                cursor.execute("""
                    INSERT INTO schema_migrations (migration_id, applied_at, description)
                    VALUES (?, ?, ?)
                """, (mig_id, now_str, desc))
                db.commit()
                print(f"[MIGRATION] -> ÉXITO: {mig_id}")
            except Exception as e:
                db.rollback()
                print(f"[MIGRATION] -> ERROR en {mig_id}: {e}")
                # No detener el sistema completo si una migración falla, continuar registrando el log
