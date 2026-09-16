# -*- coding: utf-8 -*-
"""
Script de Fusión Segura: Leonardo Cadenas
Fusiona el perfil duplicado (ID 178, cédula 306729199) en el perfil principal con todo el historial (ID 3).
Actualiza la cédula a 306729199, migra la cita de mañana (20:30) y elimina el duplicado.
"""

import os
import sys
import shutil
import sqlite3

BASE_DIR = r"c:\Users\paulo\Desktop\Programacion\Mi consultorio"
DB_PATH = os.path.join(BASE_DIR, 'clinica.db')

def merge_leonardo(db_path=DB_PATH):
    if not os.path.exists(db_path):
        print(f"[ERROR] No se encontró la base de datos en: {db_path}")
        return False

    # 1. Crear respaldo de seguridad
    backup_path = db_path + ".backup_pre_merge_leonardo"
    shutil.copy2(db_path, backup_path)
    print(f"[OK] Respaldo de seguridad creado en: {backup_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        # 2. Localizar perfiles
        cursor.execute("SELECT * FROM pacientes WHERE id = 3 OR cedula LIKE '170756419%'")
        perfil_principal = cursor.fetchone()

        cursor.execute("SELECT * FROM pacientes WHERE id = 178 OR (cedula LIKE '306729199%' AND id != 3)")
        perfil_duplicado = cursor.fetchone()

        if not perfil_principal:
            print("[ERROR] No se encontró el perfil principal de Leonardo Jesús (ID: 3 / Cédula: 170756419).")
            return False

        id_principal = perfil_principal['id']

        if not perfil_duplicado:
            print("[AVISO] No se encontró el perfil duplicado (306729199). Verificando si ya fue fusionado...")
            cursor.execute("SELECT id, nombres, apellidos, cedula FROM pacientes WHERE id = ?", (id_principal,))
            p = cursor.fetchone()
            print(f"[ESTADO ACTUAL] Paciente ID {p['id']}: {p['nombres']} {p['apellidos']} | Cédula: {p['cedula']}")
            conn.close()
            return True

        id_duplicado = perfil_duplicado['id']
        nueva_cedula = perfil_duplicado['cedula']

        print(f"\n--- INICIANDO FUSIÓN ---")
        print(f"Perfil Destino (Historial completo): ID {id_principal} - {perfil_principal['nombres']} {perfil_principal['apellidos']} (Cédula vieja: {perfil_principal['cedula']})")
        print(f"Perfil Origen (Duplicado a borrar): ID {id_duplicado} - {perfil_duplicado['nombres']} {perfil_duplicado['apellidos']} (Cédula nueva: {nueva_cedula})")

        # Iniciar transacción
        cursor.execute("BEGIN TRANSACTION")

        # 3. Migrar todas las tablas que apunten al perfil duplicado
        tablas_actualizadas = {}
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r['name'] for r in cursor.fetchall()]

        for t in tables:
            cursor.execute(f"PRAGMA table_info({t})")
            cols = [col['name'] for col in cursor.fetchall()]
            col_pid = None
            if 'paciente_id' in cols:
                col_pid = 'paciente_id'
            elif 'patient_id' in cols:
                col_pid = 'patient_id'

            if col_pid and t != 'pacientes':
                cursor.execute(f"SELECT COUNT(*) as cnt FROM {t} WHERE {col_pid} = ?", (id_duplicado,))
                cnt = cursor.fetchone()['cnt']
                if cnt > 0:
                    cursor.execute(f"UPDATE {t} SET {col_pid} = ? WHERE {col_pid} = ?", (id_principal, id_duplicado))
                    tablas_actualizadas[t] = cnt

        for t, cnt in tablas_actualizadas.items():
            print(f"[OK] Migrados {cnt} registros en tabla '{t}' hacia ID {id_principal}.")

        # 4. Eliminar perfil duplicado primero para liberar el UNIQUE constraint (cedula, psicologo_id)
        cursor.execute("DELETE FROM pacientes WHERE id = ?", (id_duplicado,))
        print(f"[OK] Perfil duplicado ID {id_duplicado} eliminado exitosamente.")

        # 5. Actualizar cédula y username en el perfil principal
        update_user = nueva_cedula if (perfil_principal['username'] == perfil_principal['cedula'] or not perfil_principal['username']) else perfil_principal['username']
        cursor.execute("""
            UPDATE pacientes 
            SET cedula = ?, username = ? 
            WHERE id = ?
        """, (nueva_cedula, update_user, id_principal))
        print(f"[OK] Cédula de paciente ID {id_principal} actualizada a '{nueva_cedula}' (Usuario portal: '{update_user}').")

        conn.commit()
        print("\n[ÉXITO] Fusión en SQLite completada de forma atómica.")

        # 6. Sincronizar con Firebase si el entorno lo soporta
        try:
            if BASE_DIR not in sys.path:
                sys.path.insert(0, BASE_DIR)
            from app import sync_patient_to_firebase, delete_patient_from_firebase
            print("[SINCRONIZACIÓN] Sincronizando datos con Firebase Realtime Database...")
            sync_patient_to_firebase(id_principal)
            delete_patient_from_firebase(id_duplicado, u_key=nueva_cedula)
            print("[OK] Firebase sincronizado correctamente.")
        except Exception as e_fb:
            print(f"[AVISO] Sincronización Firebase omitida o pendiente (no crítica): {e_fb}")

        # Verificación final
        cursor.execute("SELECT id, nombres, apellidos, cedula, telefono, email FROM pacientes WHERE id = ?", (id_principal,))
        p_final = cursor.fetchone()
        cursor.execute("SELECT COUNT(*) as cnt FROM agenda_finanzas WHERE paciente_id = ?", (id_principal,))
        citas_final = cursor.fetchone()['cnt']
        cursor.execute("SELECT COUNT(*) as cnt FROM sesiones WHERE paciente_id = ?", (id_principal,))
        ses_final = cursor.fetchone()['cnt']

        print("\n--- RESUMEN FINAL DEL CONSULTANTE FUSIONADO ---")
        print(f"ID: {p_final['id']}")
        print(f"Nombre: {p_final['nombres']} {p_final['apellidos']}")
        print(f"Cédula: {p_final['cedula']}")
        print(f"Teléfono: {p_final['telefono']}")
        print(f"Email: {p_final['email']}")
        print(f"Total Citas (incluyendo la de mañana): {citas_final}")
        print(f"Total Sesiones Clínicas preservadas: {ses_final}")

        conn.close()
        return True

    except Exception as e:
        conn.rollback()
        conn.close()
        print(f"[ERROR CRÍTICO] La fusión falló. Se realizó rollback completo: {e}")
        return False

if __name__ == '__main__':
    db_target = sys.argv[1] if len(sys.argv) > 1 else DB_PATH
    merge_leonardo(db_target)
