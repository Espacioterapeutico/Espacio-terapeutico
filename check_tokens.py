
# -*- coding: utf-8 -*-
import sqlite3
import datetime

db_path = r"C:\Users\paulo\Downloads\clinica (5).db"
db = sqlite3.connect(db_path)
db.row_factory = sqlite3.Row
cursor = db.cursor()

now = datetime.datetime.now()
today_str = now.strftime("%Y-%m-%d")
tomorrow = now + datetime.timedelta(days=1)
day_after_tomorrow = now + datetime.timedelta(days=2)
in_three_days = now + datetime.timedelta(days=3)

print("=== PROXIMOS MENSAJES DE WHATSAPP (SEGUN CRON) ===")

# Confirmaciones
cursor.execute("""
    SELECT a.id, a.fecha, a.hora, p.nombres, p.apellidos 
    FROM agenda_finanzas a
    JOIN pacientes p ON a.paciente_id = p.id
    WHERE a.fecha IN (?, ?, ?) 
      AND COALESCE(a.confirmacion_enviada_wa, 0) = 0
      AND COALESCE(a.estado_pago, "") != "Cancelada"
      AND COALESCE(a.confirmada, 0) = 0
    ORDER BY a.fecha, a.hora
""", (tomorrow.strftime("%Y-%m-%d"), day_after_tomorrow.strftime("%Y-%m-%d"), in_three_days.strftime("%Y-%m-%d")))
confirmaciones = cursor.fetchall()
print("\n[1] Confirmaciones Pendientes (Citas entre manana y los proximos 3 dias):")
if not confirmaciones:
    print("  Ninguna.")
for c in confirmaciones:
    print(f"  - Cita #{c[0]} | {c[3]} {c[4]} | {c[1]} {c[2]}")

# Recordatorios mismo dia
cursor.execute("""
    SELECT a.id, a.fecha, a.hora, p.nombres, p.apellidos 
    FROM agenda_finanzas a
    JOIN pacientes p ON a.paciente_id = p.id
    WHERE a.fecha = ? 
      AND COALESCE(a.recordatorio_enviado_wa, 0) = 0
      AND COALESCE(a.estado_pago, "") != "Cancelada"
      AND COALESCE(a.confirmada, 0) = 1
    ORDER BY a.hora
""", (today_str,))
recordatorios = cursor.fetchall()
print("\n[2] Recordatorios (Citas HOY confirmadas que no han recibido recordatorio):")
if not recordatorios:
    print("  Ninguno.")
for c in recordatorios:
    print(f"  - Cita #{c[0]} | {c[3]} {c[4]} | {c[1]} {c[2]}")

# Herramientas (Tokens)
try:
    cursor.execute("""
        SELECT c.id, c.fecha_programada, c.estado, p.nombres, p.apellidos, t.herramienta_id 
        FROM cola_recordatorios_herramientas c
        JOIN pacientes p ON c.paciente_id = p.id
        LEFT JOIN tokens_herramientas t ON c.paciente_id = t.paciente_id AND c.fecha_programada = t.fecha_programada
        WHERE c.estado = "pendiente" 
          AND c.fecha_programada <= ?
        ORDER BY c.fecha_programada
    """, (today_str,))
    herramientas = cursor.fetchall()
    print("\n[3] Envios de Herramientas/Tests (Tokens pendientes programados para hoy o antes):")
    if not herramientas:
        print("  Ninguno.")
    for c in herramientas:
        test = f"Test ID {c[5]}" if c[5] else "Link al portal"
        print(f"  - Cola #{c[0]} | {c[3]} {c[4]} | Fecha Prog: {c[1]} | {test}")
except Exception as e:
    print(f"\n[3] Envios de Herramientas: Error: {e}")

