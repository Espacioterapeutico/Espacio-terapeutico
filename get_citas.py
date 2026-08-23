
import sqlite3
import datetime

db_path = r"C:\Users\paulo\Downloads\clinica (5).db"
db = sqlite3.connect(db_path)
db.row_factory = sqlite3.Row
cursor = db.cursor()

now = datetime.datetime.now()
today_str = now.strftime("%Y-%m-%d")

cursor.execute("""
    SELECT a.id, a.fecha, a.hora, p.nombres, p.apellidos, a.confirmacion_enviada_wa, a.recordatorio_enviado_wa, a.confirmada
    FROM agenda_finanzas a
    JOIN pacientes p ON a.paciente_id = p.id
    WHERE a.fecha >= ? AND COALESCE(a.estado_pago, "") != "Cancelada"
    ORDER BY a.fecha ASC, a.hora ASC
""", (today_str,))
citas = cursor.fetchall()

print("=== TODAS LAS CITAS FUTURAS Y SU PROGRAMACION DE MENSAJES ===")
if not citas:
    print("  No hay citas futuras en la base de datos.")
else:
    for c in citas:
        print("\nCita #" + str(c[0]) + " | " + c[3] + " " + c[4] + " | Fecha: " + c[1] + " " + c[2])
        
        fecha_cita = datetime.datetime.strptime(c[1], "%Y-%m-%d").date()
        dia_previo = fecha_cita - datetime.timedelta(days=1)
        
        conf_status = "Ya enviado" if c[5] else "Pendiente"
        print("  - Confirmacion: Se envia el " + dia_previo.strftime("%Y-%m-%d") + " a las 8:00 AM (Estado: " + conf_status + ")")
        
        rec_status = "Ya enviado" if c[6] else "Pendiente"
        print("  - Recordatorio (si confirma): Se enviaria el " + c[1] + " (Mismo dia) (Estado: " + rec_status + ")")

