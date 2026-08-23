
# -*- coding: utf-8 -*-
import sqlite3
db_path = r"C:\Users\paulo\Downloads\clinica (5).db"
db = sqlite3.connect(db_path)
db.row_factory = sqlite3.Row
cursor = db.cursor()

cursor.execute("""
    SELECT m.*, p.nombres, p.apellidos 
    FROM modulos_terapeuticos_paciente m
    JOIN pacientes p ON m.paciente_id = p.id
    WHERE (p.nombres LIKE "%Elizabeth%" OR p.nombres LIKE "%Leonardo%")
""")
mods = cursor.fetchall()
for m in mods:
    print(f"Paciente: {m[5]} {m[6]} | Modulo: {m[2]} | Activo: {m[3]}")

cursor.execute("""
    SELECT t.*, p.nombres, p.apellidos 
    FROM test_asignaciones t
    JOIN pacientes p ON t.paciente_id = p.id
    WHERE (p.nombres LIKE "%Elizabeth%" OR p.nombres LIKE "%Leonardo%")
""")
tests = cursor.fetchall()
for t in tests:
    print(f"Test Asignado: {t[-2]} {t[-1]} | Estado: {t[4]}")

