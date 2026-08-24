import sqlite3
db_path = r'C:\Users\paulo\Downloads\clinica (5).db'
db = sqlite3.connect(db_path)
cursor = db.cursor()
cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='agenda_finanzas'")
print(cursor.fetchone()[0])