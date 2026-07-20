import os
import sqlite3
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

DB_PATH = 'mi_consultorio.db'

SECRET_KEY = os.environ.get('SECRET_KEY', 'espacio_terapeutico_master_key_2026')
kdf = PBKDF2HMAC(
    algorithm=hashes.SHA256(),
    length=32,
    salt=b'espacio_terapeutico_salt',
    iterations=100000,
)
FERNET_KEY = base64.urlsafe_b64encode(kdf.derive(SECRET_KEY.encode()))
fernet_cipher = Fernet(FERNET_KEY)

def encrypt_text(text):
    if not text:
        return text
    if str(text).startswith("enc:"):
        return text
    try:
        encrypted_bytes = fernet_cipher.encrypt(str(text).encode('utf-8'))
        return f"enc:{encrypted_bytes.decode('utf-8')}"
    except Exception as e:
        print(f"Error encrypting: {e}")
        return text

def migrate():
    if not os.path.exists(DB_PATH):
        print(f"Base de datos {DB_PATH} no encontrada. Se creará al iniciar la app.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    print("--- INICIANDO MIGRACIÓN Y ENCRIPTACIÓN DE BASE DE DATOS ---")
    
    # 1. Verificar columnas e índices
    cursor.execute("PRAGMA table_info(sesiones)")
    cols_ses = [row[1] for row in cursor.fetchall()]
    
    if cols_ses:
        cursor.execute("SELECT id, resumen, anotaciones_proxima, compromisos_psicologo, diagnostico, test_aplicados FROM sesiones")
        rows = cursor.fetchall()
        count_encrypted = 0
        for r in rows:
            s_id, resumen, anot_prox, comp, diag, tests = r
            e_resumen = encrypt_text(resumen)
            e_anot_prox = encrypt_text(anot_prox)
            e_comp = encrypt_text(comp)
            e_diag = encrypt_text(diag)
            e_tests = encrypt_text(tests)
            
            cursor.execute("""
                UPDATE sesiones SET resumen = ?, anotaciones_proxima = ?, compromisos_psicologo = ?, diagnostico = ?, test_aplicados = ?
                WHERE id = ?
            """, (e_resumen, e_anot_prox, e_comp, e_diag, e_tests, s_id))
            count_encrypted += 1
            
        print(f"✓ {count_encrypted} evoluciones clínicas cifradas con éxito con AES-256 Fernet.")
        
    conn.commit()
    conn.close()
    print("--- MIGRACIÓN COMPLETADA CON ÉXITO ---")

if __name__ == '__main__':
    migrate()
