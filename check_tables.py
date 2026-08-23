
import sqlite3
db_path = r"C:\Users\paulo\Downloads\clinica (5).db"
db = sqlite3.connect(db_path)
cursor = db.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type=\"table\"")
tables = cursor.fetchall()
for t in tables:
    print(t[0])

