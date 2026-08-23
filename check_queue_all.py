
import sqlite3
db_path = r"C:\Users\paulo\Downloads\clinica (5).db"
db = sqlite3.connect(db_path)
db.row_factory = sqlite3.Row
cursor = db.cursor()

try:
    cursor.execute("""
        SELECT c.id, c.fecha_programada, c.estado, p.nombres, p.apellidos, c.herramienta_tipo
        FROM cola_recordatorios_herramientas c
        JOIN pacientes p ON c.paciente_id = p.id
    """)
    rows = cursor.fetchall()
    if not rows:
        print("La cola esta 100% vacia.")
    else:
        for r in rows:
            print("[" + str(r[2]) + "] " + str(r[3]) + " " + str(r[4]) + " | Herramienta: " + str(r[5]) + " | Fecha: " + str(r[1]))
except Exception as e:
    print("Error: " + str(e))

