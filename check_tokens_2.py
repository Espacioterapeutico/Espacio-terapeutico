
import sqlite3
import datetime

db_path = r"C:\Users\paulo\Downloads\clinica (5).db"
db = sqlite3.connect(db_path)
db.row_factory = sqlite3.Row
cursor = db.cursor()

try:
    cursor.execute("""
        SELECT c.id, c.fecha_programada, c.estado, p.nombres, p.apellidos
        FROM cola_recordatorios_herramientas c
        JOIN pacientes p ON c.paciente_id = p.id
        WHERE c.estado = "pendiente"
        ORDER BY c.fecha_programada
    """)
    herramientas = cursor.fetchall()
    print("\n[3] Envios de Herramientas en cola:")
    if not herramientas:
        print("  Ninguno.")
    for c in herramientas:
        print(f"  - Cola #{c[0]} | {c[3]} {c[4]} | Fecha Prog: {c[1]}")
except Exception as e:
    print(f"\n[3] Envios de Herramientas: Error: {e}")

