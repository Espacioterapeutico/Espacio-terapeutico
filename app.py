import os
import sys
import re
import sqlite3
import datetime
import shutil
import json
from flask import Flask, request, jsonify, session, send_file, redirect, url_for, g
from werkzeug.security import generate_password_hash, check_password_hash
import docx
from docx.shared import Inches, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH

# Google Calendar API imports
try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import Flow
    from googleapiclient.discovery import build
    from google.auth.transport.requests import Request
    GOOGLE_CALENDAR_AVAILABLE = True
except ImportError:
    GOOGLE_CALENDAR_AVAILABLE = False

def get_resource_path(relative_path):
    """ Obtener ruta absoluta del recurso, funciona para dev, WSGI y PyInstaller """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

app = Flask(
    __name__,
    static_folder=get_resource_path('static'),
    template_folder=get_resource_path('templates')
)
app.secret_key = os.environ.get('SECRET_KEY', 'espacio_terapeutico_secret_key_2026_prod_fixed')
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = datetime.timedelta(days=30)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, 'clinica.db')
SCHEMA_FILE = get_resource_path('schema.sql')
CLIENT_SECRETS_FILE = os.path.join(BASE_DIR, "credentials.json")
SCOPES = ['https://www.googleapis.com/auth/calendar']

# Deshabilitar HTTPS obligatorio para OAuth en entorno local de desarrollo
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

MASTER_KEY_SECRET = os.environ.get('SECRET_KEY', 'espacio_terapeutico_master_key_2026')
_kdf = PBKDF2HMAC(
    algorithm=hashes.SHA256(),
    length=32,
    salt=b'espacio_terapeutico_salt',
    iterations=100000,
)
FERNET_KEY = base64.urlsafe_b64encode(_kdf.derive(MASTER_KEY_SECRET.encode()))
fernet_cipher = Fernet(FERNET_KEY)

def encrypt_clinical_text(text):
    if not text:
        return ""
    text_str = str(text)
    if text_str.startswith("enc:"):
        return text_str
    try:
        encrypted_bytes = fernet_cipher.encrypt(text_str.encode('utf-8'))
        return f"enc:{encrypted_bytes.decode('utf-8')}"
    except Exception as e:
        print(f"Error encrypting: {e}")
        return text_str

def decrypt_clinical_text(cipher_text):
    if not cipher_text or not isinstance(cipher_text, str):
        return cipher_text
    current = cipher_text
    while isinstance(current, str) and current.startswith("enc:"):
        try:
            raw_cipher = current[4:].encode('utf-8')
            decrypted_bytes = fernet_cipher.decrypt(raw_cipher)
            current = decrypted_bytes.decode('utf-8')
        except Exception as e:
            print(f"Error decrypting: {e}")
            break
    return current
def get_vapid_keys(cursor):
    cursor.execute("SELECT clave, valor FROM configuracion WHERE clave IN ('vapid_public_key', 'vapid_private_key')")
    cfg = dict(cursor.fetchall())
    if 'vapid_public_key' not in cfg or 'vapid_private_key' not in cfg:
        try:
            from cryptography.hazmat.primitives.asymmetric import ec
            import base64
            pk = ec.generate_private_key(ec.SECP256R1())
            priv_bytes = pk.private_numbers().private_value.to_bytes(32, 'big')
            pub_numbers = pk.public_key().public_numbers()
            pub_bytes = b'\x04' + pub_numbers.x.to_bytes(32, 'big') + pub_numbers.y.to_bytes(32, 'big')
            pub_key = base64.urlsafe_b64encode(pub_bytes).decode('utf-8').rstrip('=')
            priv_key = base64.urlsafe_b64encode(priv_bytes).decode('utf-8').rstrip('=')
            cursor.execute("INSERT OR REPLACE INTO configuracion (clave, valor) VALUES ('vapid_public_key', ?)", (pub_key,))
            cursor.execute("INSERT OR REPLACE INTO configuracion (clave, valor) VALUES ('vapid_private_key', ?)", (priv_key,))
            cfg = {'vapid_public_key': pub_key, 'vapid_private_key': priv_key}
        except Exception as e:
            print("Error generando VAPID keys:", e)
            cfg = {'vapid_public_key': '', 'vapid_private_key': ''}
    return cfg

def send_fcm_notification(user_id=None, patient_id=None, title="Mi Consultorio", body="Tienes una nueva notificación.", url="/"):
    if not os.path.exists(FIREBASE_SA_FILE):
        return
        
    try:
        import json
        import urllib.request
        from google.oauth2 import service_account
        import google.auth.transport.requests
        
        # 1. Obtener tokens de FCM para el usuario/paciente
        db = get_db()
        cursor = db.cursor()
        tokens = []
        if user_id:
            cursor.execute("SELECT token FROM fcm_subscriptions WHERE user_id = ? OR user_id IS NULL", (user_id,))
            tokens = [row['token'] for row in cursor.fetchall()]
        elif patient_id:
            cursor.execute("SELECT token FROM fcm_subscriptions WHERE patient_id = ?", (patient_id,))
            tokens = [row['token'] for row in cursor.fetchall()]
        else:
            cursor.execute("SELECT token FROM fcm_subscriptions")
            tokens = [row['token'] for row in cursor.fetchall()]

        # Deduplicar manteniendo orden
        tokens = list(dict.fromkeys(tokens))
        if not tokens:
            return
            
        # 2. Obtener project_id y access_token del service account JSON
        with open(FIREBASE_SA_FILE, 'r', encoding='utf-8') as f:
            sa_info = json.load(f)
            project_id = sa_info.get('project_id')
            
        if not project_id:
            return
            
        scopes = ["https://www.googleapis.com/auth/firebase.messaging"]
        creds = service_account.Credentials.from_service_account_file(
            FIREBASE_SA_FILE, scopes=scopes
        )
        auth_req = google.auth.transport.requests.Request()
        creds.refresh(auth_req)
        access_token = creds.token
        
        # 3. Enviar por FCM a cada token
        fcm_url = f"https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; UTF-8"
        }
        
        try:
            from flask import request
            base_url = request.host_url.rstrip('/') if request else ""
        except:
            base_url = ""

        icon_url = f"{base_url}/static/logo.png" if base_url else "/static/logo.png"
        badge_url = f"{base_url}/static/badge.png" if base_url else "/static/badge.png"

        import hashlib
        tag_id = f"notif-{hashlib.md5((title + body).encode('utf-8')).hexdigest()[:10]}"

        for token in tokens:
            payload = {
                "message": {
                    "token": token,
                    "notification": {
                        "title": title,
                        "body": body
                    },
                    "data": {
                        "url": url,
                        "title": title,
                        "body": body,
                        "icon": icon_url,
                        "badge": badge_url,
                        "tag": tag_id,
                        "click_action": url
                    },
                    "webpush": {
                        "notification": {
                            "title": title,
                            "body": body,
                            "icon": icon_url,
                            "badge": badge_url,
                            "tag": tag_id,
                            "renotify": True,
                            "vibrate": [200, 100, 200]
                        },
                        "fcm_options": {
                            "link": url
                        }
                    },
                    "android": {
                        "notification": {
                            "sound": "default",
                            "tag": tag_id
                        }
                    },
                    "apns": {
                        "payload": {
                            "aps": {
                                "sound": "default"
                            }
                        }
                    }
                }
            }
            req = urllib.request.Request(
                fcm_url,
                data=json.dumps(payload).encode('utf-8'),
                headers=headers,
                method='POST'
            )
            try:
                with urllib.request.urlopen(req) as response:
                    response.read()
            except Exception as fcm_ex:
                print("Error de envío a token FCM individual:", fcm_ex)
    except Exception as e:
        print("Error global en send_fcm_notification:", e)

def send_webpush_notification(user_id=None, patient_id=None, title="Mi Consultorio", body="Tienes una nueva notificación.", url="/"):
    # Usa exclusivamente FCM (Firebase Cloud Messaging) para evitar duplicados.
    # El envío VAPID (pywebpush) fue desactivado porque generaba notificaciones duplicadas:
    # FCM usa firebase-messaging-sw.js y VAPID usa sw.js — son Service Workers distintos
    # que no pueden deduplicarse entre sí mediante 'tag'.
    try:
        send_fcm_notification(user_id=user_id, patient_id=patient_id, title=title, body=body, url=url)
    except Exception as fcm_err:
        print("Error al disparar FCM en send_webpush_notification:", fcm_err)

def clean_digits_only(s):
    if not s:
        return ""
    return re.sub(r'\D', '', str(s))

def normalize_date_str(d_str):
    if not d_str:
        return ""
    d_str = str(d_str).strip()
    try:
        dt = datetime.strptime(d_str, "%Y-%m-%d")
        return dt.strftime("%Y-%m-%d")
    except:
        pass
    try:
        dt = datetime.strptime(d_str, "%d/%m/%Y")
        return dt.strftime("%Y-%m-%d")
    except:
        pass
    try:
        parts = d_str.split('-')
        if len(parts) == 3 and len(parts[0]) == 4:
            return f"{parts[0]}-{parts[1].zfill(2)}-{parts[2].zfill(2)}"
    except:
        pass
    return d_str

def normalize_time_str(t_str):
    if not t_str:
        return "00:00"
    t_str = str(t_str).strip().lower()
    is_pm = 'pm' in t_str
    is_am = 'am' in t_str
    clean_t = re.sub(r'[^\d:]', '', t_str)
    parts = clean_t.split(':')
    if not parts or not parts[0]:
        return "00:00"
    try:
        h = int(parts[0])
        m = int(parts[1]) if len(parts) > 1 and parts[1] else 0
        if is_pm and h < 12:
            h += 12
        elif is_am and h == 12:
            h = 0
        return f"{h:02d}:{m:02d}"
    except:
        return t_str[:5]

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    db = sqlite3.connect(DATABASE)
    cursor = db.cursor()
    # Verificar si la tabla principal 'usuarios' existe en sqlite_master
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='usuarios'")
    exists = cursor.fetchone()
    
    if not exists:
        with open(SCHEMA_FILE, 'r', encoding='utf-8') as f:
            db.executescript(f.read())
        db.commit()
    else:
        # Migración automática de sesiones si la tabla existe
        cursor.execute("PRAGMA table_info(sesiones)")
        columns = [row[1] for row in cursor.fetchall()]
        if columns:
            if 'estado' not in columns:
                cursor.execute("ALTER TABLE sesiones ADD COLUMN estado TEXT DEFAULT 'Realizada'")
            if 'agenda_id' not in columns:
                cursor.execute("ALTER TABLE sesiones ADD COLUMN agenda_id INTEGER")
            if 'diagnostico' not in columns:
                cursor.execute("ALTER TABLE sesiones ADD COLUMN diagnostico TEXT")
            if 'test_aplicados' not in columns:
                cursor.execute("ALTER TABLE sesiones ADD COLUMN test_aplicados TEXT")
            if 'archivo_adjunto' not in columns:
                cursor.execute("ALTER TABLE sesiones ADD COLUMN archivo_adjunto TEXT")
            if 'resumen_paciente' not in columns:
                cursor.execute("ALTER TABLE sesiones ADD COLUMN resumen_paciente TEXT")
            db.commit()
            
        # Migración automática de usuarios (psicólogos)
        cursor.execute("PRAGMA table_info(usuarios)")
        cols_usr = [row[1] for row in cursor.fetchall()]
        if cols_usr:
            if 'nombres' not in cols_usr:
                cursor.execute("ALTER TABLE usuarios ADD COLUMN nombres TEXT")
            if 'apellidos' not in cols_usr:
                cursor.execute("ALTER TABLE usuarios ADD COLUMN apellidos TEXT")
            if 'estudios' not in cols_usr:
                cursor.execute("ALTER TABLE usuarios ADD COLUMN estudios TEXT")
            if 'federacion' not in cols_usr:
                cursor.execute("ALTER TABLE usuarios ADD COLUMN federacion TEXT")
            if 'foto_titulo' not in cols_usr:
                cursor.execute("ALTER TABLE usuarios ADD COLUMN foto_titulo TEXT")
            if 'foto_documento' not in cols_usr:
                cursor.execute("ALTER TABLE usuarios ADD COLUMN foto_documento TEXT")
            if 'activo' not in cols_usr:
                cursor.execute("ALTER TABLE usuarios ADD COLUMN activo INTEGER DEFAULT 1")
            if 'role' not in cols_usr:
                cursor.execute("ALTER TABLE usuarios ADD COLUMN role TEXT DEFAULT 'psicologo'")
            if 'metodos_pago' not in cols_usr:
                cursor.execute("ALTER TABLE usuarios ADD COLUMN metodos_pago TEXT")
            if 'disponibilidad_horarios' not in cols_usr:
                cursor.execute("ALTER TABLE usuarios ADD COLUMN disponibilidad_horarios TEXT")
            if 'configuracion_horarios_visual' not in cols_usr:
                cursor.execute("ALTER TABLE usuarios ADD COLUMN configuracion_horarios_visual TEXT")
            if 'bloqueo_registro' not in cols_usr:
                cursor.execute("ALTER TABLE usuarios ADD COLUMN bloqueo_registro INTEGER DEFAULT 0")
            if 'bloqueo_evoluciones' not in cols_usr:
                cursor.execute("ALTER TABLE usuarios ADD COLUMN bloqueo_evoluciones INTEGER DEFAULT 0")
            if 'bloqueo_finanzas' not in cols_usr:
                cursor.execute("ALTER TABLE usuarios ADD COLUMN bloqueo_finanzas INTEGER DEFAULT 0")
            if 'bloqueo_agenda' not in cols_usr:
                cursor.execute("ALTER TABLE usuarios ADD COLUMN bloqueo_agenda INTEGER DEFAULT 0")
            if 'bloqueo_mensajes' not in cols_usr:
                cursor.execute("ALTER TABLE usuarios ADD COLUMN bloqueo_mensajes INTEGER DEFAULT 0")
            if 'bloqueo_pizarra' not in cols_usr:
                cursor.execute("ALTER TABLE usuarios ADD COLUMN bloqueo_pizarra INTEGER DEFAULT 0")
            if 'aviso_pago' not in cols_usr:
                cursor.execute("ALTER TABLE usuarios ADD COLUMN aviso_pago INTEGER DEFAULT 0")
            if 'terminos_condiciones' not in cols_usr:
                cursor.execute("ALTER TABLE usuarios ADD COLUMN terminos_condiciones TEXT")
            db.commit()
            
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fcm_subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                patient_id INTEGER,
                token TEXT UNIQUE
            )
        """)
        db.commit()
            
        # Migración automática de usuarios (slug)
        cursor.execute("PRAGMA table_info(usuarios)")
        cols_usr = [row[1] for row in cursor.fetchall()]
        if 'slug' not in cols_usr:
            cursor.execute("ALTER TABLE usuarios ADD COLUMN slug TEXT")
        try:
            cursor.execute("ALTER TABLE usuarios ADD COLUMN primer_inicio INTEGER DEFAULT 1")
            cursor.execute("ALTER TABLE usuarios ADD COLUMN fecha_registro TEXT")
            cursor.execute("ALTER TABLE usuarios ADD COLUMN fecha_expiracion_prueba TEXT")
            cursor.execute("ALTER TABLE usuarios ADD COLUMN suscripcion_paga INTEGER DEFAULT 0")
        except:
            pass
        db.commit()

        cursor.execute("SELECT id, nombres, apellidos, username FROM usuarios WHERE slug IS NULL OR slug = ''")
        unslugged = cursor.fetchall()
        for u_row in unslugged:
            u_id = u_row[0]
            u_nom = u_row[1] or ""
            u_ape = u_row[2] or ""
            u_user = u_row[3] or ""
            raw_n = f"psic.{u_nom}{u_ape}".lower().replace(" ", "").replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u").replace("ñ", "n")
            if not raw_n or raw_n == "psic.":
                raw_n = f"psic.{u_user}".lower()
            cursor.execute("UPDATE usuarios SET slug = ? WHERE id = ?", (raw_n, u_id))
        db.commit()


        # Migración automática de pacientes
        cursor.execute("PRAGMA table_info(pacientes)")
        cols_pac = [row[1] for row in cursor.fetchall()]
        if cols_pac:
            if 'telefono' not in cols_pac:
                cursor.execute("ALTER TABLE pacientes ADD COLUMN telefono TEXT")
            if 'email' not in cols_pac:
                cursor.execute("ALTER TABLE pacientes ADD COLUMN email TEXT")
            if 'username' not in cols_pac:
                cursor.execute("ALTER TABLE pacientes ADD COLUMN username TEXT")
            if 'password_hash' not in cols_pac:
                cursor.execute("ALTER TABLE pacientes ADD COLUMN password_hash TEXT")
            if 'pregunta_seguridad_1' not in cols_pac:
                cursor.execute("ALTER TABLE pacientes ADD COLUMN pregunta_seguridad_1 TEXT")
            if 'respuesta_seguridad_1_hash' not in cols_pac:
                cursor.execute("ALTER TABLE pacientes ADD COLUMN respuesta_seguridad_1_hash TEXT")
            if 'pregunta_seguridad_2' not in cols_pac:
                cursor.execute("ALTER TABLE pacientes ADD COLUMN pregunta_seguridad_2 TEXT")
            if 'respuesta_seguridad_2_hash' not in cols_pac:
                cursor.execute("ALTER TABLE pacientes ADD COLUMN respuesta_seguridad_2_hash TEXT")
            if 'psicologo_id' not in cols_pac:
                cursor.execute("ALTER TABLE pacientes ADD COLUMN psicologo_id INTEGER")
            if 'costo_personalizado' not in cols_pac:
                cursor.execute("ALTER TABLE pacientes ADD COLUMN costo_personalizado REAL")
            if 'moneda_personalizada' not in cols_pac:
                cursor.execute("ALTER TABLE pacientes ADD COLUMN moneda_personalizada TEXT")
            if 'costo_paquete_personalizado' not in cols_pac:
                cursor.execute("ALTER TABLE pacientes ADD COLUMN costo_paquete_personalizado REAL")
            if 'sesiones_paquete_personalizado' not in cols_pac:
                cursor.execute("ALTER TABLE pacientes ADD COLUMN sesiones_paquete_personalizado INTEGER")
            if 'pais' not in cols_pac:
                cursor.execute("ALTER TABLE pacientes ADD COLUMN pais TEXT")
            if 'ciudad' not in cols_pac:
                cursor.execute("ALTER TABLE pacientes ADD COLUMN ciudad TEXT")
            if 'terminos_aceptados' not in cols_pac:
                cursor.execute("ALTER TABLE pacientes ADD COLUMN terminos_aceptados INTEGER DEFAULT 0")
            if 'fecha_aceptacion_terminos' not in cols_pac:
                cursor.execute("ALTER TABLE pacientes ADD COLUMN fecha_aceptacion_terminos TEXT")
            
            # Asegurar que todos los consultantes antiguos tengan terminos_aceptados = 0 y psicologo_id por defecto si son NULL
            cursor.execute("UPDATE pacientes SET terminos_aceptados = 0 WHERE terminos_aceptados IS NULL")
            cursor.execute("UPDATE pacientes SET psicologo_id = 1 WHERE psicologo_id IS NULL")
            
            # Normalizar fechas con barras en agenda_finanzas a formato ISO YYYY-MM-DD
            cursor.execute("SELECT id, fecha FROM agenda_finanzas WHERE fecha LIKE '%/%'")
            slash_rows = cursor.fetchall()
            for r_slash in slash_rows:
                norm_f = normalize_date_str(r_slash['fecha'])
                cursor.execute("UPDATE agenda_finanzas SET fecha = ? WHERE id = ?", (norm_f, r_slash['id']))
            db.commit()

        # Migración automática de pizarra_terapeutica
        cursor.execute("PRAGMA table_info(pizarra_terapeutica)")
        cols_piz = [row[1] for row in cursor.fetchall()]
        if cols_piz:
            if 'estado_animo' not in cols_piz:
                cursor.execute("ALTER TABLE pizarra_terapeutica ADD COLUMN estado_animo TEXT")
            if 'comentario_animo' not in cols_piz:
                cursor.execute("ALTER TABLE pizarra_terapeutica ADD COLUMN comentario_animo TEXT")
            if 'emoji_animo' not in cols_piz:
                cursor.execute("ALTER TABLE pizarra_terapeutica ADD COLUMN emoji_animo TEXT")
            db.commit()
            
        # Migración automática de agenda_finanzas
        cursor.execute("PRAGMA table_info(agenda_finanzas)")
        cols_fin = [row[1] for row in cursor.fetchall()]
        if cols_fin:
            if 'cantidad_sesiones' not in cols_fin:
                cursor.execute("ALTER TABLE agenda_finanzas ADD COLUMN cantidad_sesiones INTEGER DEFAULT 1")
            if 'referencia' not in cols_fin:
                cursor.execute("ALTER TABLE agenda_finanzas ADD COLUMN referencia TEXT")
            if 'metodo_pago' not in cols_fin:
                cursor.execute("ALTER TABLE agenda_finanzas ADD COLUMN metodo_pago TEXT")
            if 'fecha_pago' not in cols_fin:
                cursor.execute("ALTER TABLE agenda_finanzas ADD COLUMN fecha_pago TEXT")
            if 'confirmada' not in cols_fin:
                cursor.execute("ALTER TABLE agenda_finanzas ADD COLUMN confirmada INTEGER DEFAULT 0")
            db.commit()
            
        # Crear tabla de tarifas por país
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tarifas_pais (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                psicologo_id INTEGER NOT NULL,
                pais TEXT NOT NULL,
                modalidad TEXT NOT NULL,
                costo_individual REAL NOT NULL,
                costo_paquete REAL,
                sesiones_paquete INTEGER,
                moneda TEXT NOT NULL,
                FOREIGN KEY (psicologo_id) REFERENCES usuarios(id) ON DELETE CASCADE,
                UNIQUE(psicologo_id, pais, modalidad)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS web_push_subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                patient_id INTEGER,
                endpoint TEXT UNIQUE,
                p256dh TEXT,
                auth TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        db.commit()
            
        # Sincronización automática de sesiones huérfanas sin fila de finanzas
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sesiones'")
        if cursor.fetchone():
            cursor.execute("""
                SELECT s.id, s.paciente_id, s.fecha, s.modalidad, s.estado
                FROM sesiones s
                LEFT JOIN agenda_finanzas af ON s.agenda_id = af.id
                WHERE s.agenda_id IS NULL OR af.id IS NULL
            """)
            missing = cursor.fetchall()
            if missing:
                for row in missing:
                    session_id = row[0]
                    patient_id = row[1]
                    fecha = row[2]
                    modalidad = row[3]
                    estado = row[4]
                    
                    estado_pago = 'Paga' if modalidad == 'Uptaeb' else 'Pendiente'
                    metodo_pago = 'Exonerado' if modalidad == 'Uptaeb' else ''
                    referencia = 'Exonerada / Registro histórico' if modalidad == 'Uptaeb' else ''
                    
                    cursor.execute("""
                        INSERT INTO agenda_finanzas (
                            paciente_id, fecha, hora, tipo_consulta, monto, moneda, estado_pago,
                            control_uso, fecha_liquidacion, cantidad_sesiones, referencia, metodo_pago, fecha_pago
                        ) VALUES (?, ?, '00:00', ?, 0.0, 'USD', ?, 'No consumida', ?, 1, ?, ?, ?)
                    """, (patient_id, fecha, modalidad, estado_pago, fecha, referencia, metodo_pago, fecha))
                    agenda_id = cursor.lastrowid
                    cursor.execute("UPDATE sesiones SET agenda_id = ? WHERE id = ?", (agenda_id, session_id))
                db.commit()
                
        # Inicializar disponibilidad horaria predeterminada si no existe
        cursor.execute("SELECT valor FROM configuracion WHERE clave = 'disponibilidad_horarios'")
        if not cursor.fetchone():
            default_avail = """[
              {"dia": 1, "nombre": "Lunes", "activo": true, "horas": ["08:00", "09:00", "10:00", "11:00", "13:00", "14:00", "15:00", "16:00"]},
              {"dia": 2, "nombre": "Martes", "activo": true, "horas": ["08:00", "09:00", "10:00", "11:00", "13:00", "14:00", "15:00", "16:00"]},
              {"dia": 3, "nombre": "Miércoles", "activo": true, "horas": ["08:00", "09:00", "10:00", "11:00", "13:00", "14:00", "15:00", "16:00"]},
              {"dia": 4, "nombre": "Jueves", "activo": true, "horas": ["08:00", "09:00", "10:00", "11:00", "13:00", "14:00", "15:00", "16:00"]},
              {"dia": 5, "nombre": "Viernes", "activo": true, "horas": ["08:00", "09:00", "10:00", "11:00", "13:00", "14:00", "15:00", "16:00"]},
              {"dia": 6, "nombre": "Sábado", "activo": false, "horas": []},
              {"dia": 0, "nombre": "Domingo", "activo": false, "horas": []}
            ]"""
            cursor.execute("INSERT OR REPLACE INTO configuracion (clave, valor) VALUES ('disponibilidad_horarios', ?)", (default_avail,))
        # Asegurar existencia de la tabla pizarra_terapeutica
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pizarra_terapeutica (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                paciente_id INTEGER NOT NULL,
                fecha TEXT NOT NULL,
                contenido TEXT NOT NULL,
                archivo_adjunto TEXT,
                FOREIGN KEY (paciente_id) REFERENCES pacientes(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("PRAGMA table_info(pizarra_terapeutica)")
        cols_piz = [row[1] for row in cursor.fetchall()]
        if cols_piz:
            if 'archivo_adjunto' not in cols_piz:
                cursor.execute("ALTER TABLE pizarra_terapeutica ADD COLUMN archivo_adjunto TEXT")
            if 'estado_animo' not in cols_piz:
                cursor.execute("ALTER TABLE pizarra_terapeutica ADD COLUMN estado_animo TEXT")
            if 'comentario_animo' not in cols_piz:
                cursor.execute("ALTER TABLE pizarra_terapeutica ADD COLUMN comentario_animo TEXT")
            if 'emoji_animo' not in cols_piz:
                cursor.execute("ALTER TABLE pizarra_terapeutica ADD COLUMN emoji_animo TEXT")
        db.commit()
        # Asegurar existencia de la tabla notificaciones
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS notificaciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                tipo TEXT NOT NULL,
                titulo TEXT NOT NULL,
                mensaje TEXT NOT NULL,
                fecha TEXT NOT NULL,
                leida INTEGER DEFAULT 0,
                link TEXT NOT NULL
            )
        """)
        cursor.execute("PRAGMA table_info(notificaciones)")
        cols_notif = [row[1] for row in cursor.fetchall()]
        if 'user_id' not in cols_notif:
            cursor.execute("ALTER TABLE notificaciones ADD COLUMN user_id INTEGER")
        db.commit()
        # Asegurar existencia de la tabla soporte
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS soporte (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario_id INTEGER,
                rol_remitente TEXT,
                nombre_remitente TEXT,
                email_remitente TEXT,
                mensaje TEXT NOT NULL,
                fecha TEXT NOT NULL,
                leido INTEGER DEFAULT 0
            )
        """)
        # Asegurar existencia de la tabla pagos_notificados
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pagos_notificados (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                paciente_id INTEGER NOT NULL,
                monto REAL NOT NULL,
                moneda TEXT NOT NULL,
                metodo TEXT NOT NULL,
                referencia TEXT,
                fecha TEXT NOT NULL,
                estado TEXT DEFAULT 'Pendiente de verificación',
                motivo_rechazo TEXT,
                fecha_registro TEXT NOT NULL,
                FOREIGN KEY (paciente_id) REFERENCES pacientes(id) ON DELETE CASCADE
            )
        """)
        # Inicializar plantillas de mensaje si no existen
        cursor.execute("SELECT valor FROM configuracion WHERE clave = 'msg_confirmacion'")
        if not cursor.fetchone():
            cursor.execute("INSERT INTO configuracion (clave, valor) VALUES ('msg_confirmacion', ?)",
                           ("Hola {nombre}, espero te encuentres muy bien. Te escribo para confirmar nuestra próxima sesión el día {fecha} a las {hora} ({modalidad}).",))
                           
        cursor.execute("SELECT valor FROM configuracion WHERE clave = 'msg_recordatorio'")
        if not cursor.fetchone():
            cursor.execute("INSERT INTO configuracion (clave, valor) VALUES ('msg_recordatorio', ?)",
                           ("Hola {nombre}, te recuerdo que hoy tenemos nuestra sesión programada a las {hora} ({modalidad}). ¡Te espero!",))
                           
        cursor.execute("SELECT valor FROM configuracion WHERE clave = 'msg_cierre'")
        if not cursor.fetchone():
            cursor.execute("INSERT INTO configuracion (clave, valor) VALUES ('msg_cierre', ?)",
                           ("Hola {nombre}, gracias por compartir el espacio terapéutico hoy. Recuerda realizar las tareas asignadas. Si deseas agendar o reprogramar tu próxima sesión, puedes hacerlo desde tu portal.",))
        
        # Asegurar existencia de la tabla historial_reprogramaciones
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS historial_reprogramaciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                paciente_id INTEGER NOT NULL,
                agenda_id INTEGER,
                fecha_anterior TEXT NOT NULL,
                hora_anterior TEXT NOT NULL,
                fecha_nueva TEXT NOT NULL,
                hora_nueva TEXT NOT NULL,
                modificado_por TEXT DEFAULT 'Paciente',
                motivo TEXT,
                fecha_registro TEXT NOT NULL,
                FOREIGN KEY (paciente_id) REFERENCES pacientes(id) ON DELETE CASCADE
            )
        """)
        
        # Índices de aceleración para consultas financieras y de agenda
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_agenda_paciente_estado ON agenda_finanzas(paciente_id, estado_pago)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_agenda_fecha ON agenda_finanzas(fecha)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_agenda_fecha_liq ON agenda_finanzas(fecha_liquidacion)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sesiones_paciente ON sesiones(paciente_id, fecha)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_historial_reprog_paciente ON historial_reprogramaciones(paciente_id)")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS web_push_subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                patient_id INTEGER,
                endpoint TEXT NOT NULL,
                p256dh TEXT NOT NULL,
                auth TEXT NOT NULL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fcm_subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                patient_id INTEGER,
                token TEXT UNIQUE
            )
        """)

        # Pre-cargar configuracion por defecto de Firebase FCM
        _def_cfg = json.dumps({
            "apiKey": "AIzaSyDRQlUEv1SToy5ZdQqUuYZDIhejeJ81zM",
            "authDomain": "espacio-terapeutico.firebaseapp.com",
            "databaseURL": "https://espacio-terapeutico-default-rtdb.firebaseio.com",
            "projectId": "espacio-terapeutico",
            "storageBucket": "espacio-terapeutico.firebasestorage.app",
            "messagingSenderId": "437385369836",
            "appId": "1:437385369836:web:f3745dc8d65d7ca418edc9",
            "measurementId": "G-M04FWL2963"
        })
        _def_vapid = "BIexDrYPs7iSYmxpkfgQwzatXm_o5pRa1ZAZUvzeF40nAc8N61RFlHqlZ153VNamBelgsKhB4nnowPJm_7Y-Qjc"
        cursor.execute("INSERT OR IGNORE INTO configuracion (clave, valor) VALUES ('firebase_config', ?)", (_def_cfg,))
        cursor.execute("INSERT OR IGNORE INTO configuracion (clave, valor) VALUES ('firebase_vapid_key', ?)", (_def_vapid,))

        db.commit()
            
    db.close()

# Auto-inicializar base de datos al arrancar el módulo (para WSGI)
try:
    init_db()
except Exception as _db_err:
    print(f"Advertencia al inicializar BD: {_db_err}")

FIREBASE_DB_URL = "https://espacio-terapeutico-default-rtdb.firebaseio.com"

def create_auto_cancellation_session(db, paciente_id, agenda_id, fecha, modalidad, estado, resumen_motivo):
    """
    Crea o actualiza automáticamente una nota de evolución ('sesiones') para una cita cancelada.
    """
    if not paciente_id:
        return
    cursor = db.cursor()
    try:
        if agenda_id:
            cursor.execute("SELECT id FROM sesiones WHERE agenda_id = ?", (agenda_id,))
            existing = cursor.fetchone()
            if existing:
                cursor.execute("""
                    UPDATE sesiones 
                    SET fecha = ?, modalidad = ?, resumen = ?, estado = ?
                    WHERE id = ?
                """, (fecha, modalidad or 'Online', resumen_motivo, estado, existing['id']))
                return
        
        cursor.execute("""
            INSERT INTO sesiones (
                paciente_id, agenda_id, fecha, modalidad, resumen,
                diagnostico, test_aplicados, tareas_asignadas, recursos_entregados,
                anotaciones_proxima, compromisos_psicologo, estado
            ) VALUES (?, ?, ?, ?, ?, '', '', '', '', '', '', ?)
        """, (paciente_id, agenda_id, fecha, modalidad or 'Online', resumen_motivo, estado))
    except Exception as e:
        print("Error al crear evolución automática de cancelación:", e)

def auto_cancel_unconfirmed_sessions(db):
    cursor = db.cursor()
    try:
        from datetime import datetime
        import threading
        import requests
        today_str = datetime.now().strftime("%Y-%m-%d")
        
        # Obtener citas no confirmadas del día de hoy o anteriores en estado 'Agendada'
        cursor.execute("""
            SELECT af.id, af.paciente_id, af.fecha, af.hora, af.tipo_consulta, af.google_event_id, p.nombres, p.apellidos
            FROM agenda_finanzas af
            JOIN pacientes p ON af.paciente_id = p.id
            WHERE af.confirmada = 0 
              AND af.estado_pago = 'Agendada' 
              AND (af.hora != '00:00' AND af.hora != '' AND af.hora IS NOT NULL)
              AND af.fecha <= ?
        """, (today_str,))
        
        unconfirmed = cursor.fetchall()
        if not unconfirmed:
            return
            
        for appt in unconfirmed:
            appt_id = appt['id']
            patient_id = appt['paciente_id']
            fecha_cita = appt['fecha']
            hora_cita = appt['hora']
            pac_nombre = f"{appt['nombres']} {appt['apellidos']}"
            google_event_id = appt['google_event_id']
            
            # 1. Eliminar de Google Calendar
            if google_event_id:
                try:
                    service = get_calendar_service()
                    if service:
                        service.events().delete(calendarId='primary', eventId=google_event_id).execute()
                except Exception as ge:
                    print("Error al borrar evento de Google Calendar al auto-cancelar:", ge)
            
            # 2. Cancelar la cita en SQLite
            cursor.execute("""
                UPDATE agenda_finanzas
                SET estado_pago = 'Cancelada con aviso', monto = 0.0, google_event_id = NULL
                WHERE id = ?
            """, (appt_id,))
            
            # Auto-generar evolución clínica
            create_auto_cancellation_session(
                db, patient_id, appt_id, fecha_cita, appt['tipo_consulta'],
                'Cancelada con aviso',
                f"Consulta cancelada automáticamente por el sistema al no confirmarse a tiempo ({fecha_cita} a las {hora_cita})."
            )
            
            # 3. Notificación al psicólogo
            fecha_notif = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("""
                INSERT INTO notificaciones (tipo, titulo, mensaje, fecha, leida, link)
                VALUES (?, ?, ?, ?, 0, ?)
            """, (
                'cita', 
                'Cita Auto-Cancelada por Falta de Confirmación', 
                f"La consulta de {pac_nombre} para el {fecha_cita} a las {hora_cita} fue cancelada automáticamente por no confirmarse a tiempo.",
                fecha_notif,
                'agenda'
            ))
            
            # 4. Notificación al paciente en Firebase
            try:
                firebase_payload = {
                    "id": int(datetime.now().timestamp() * 1000),
                    "tipo": "cita",
                    "titulo": "Consulta Cancelada por Falta de Confirmación",
                    "mensaje": f"Tu consulta programada para el {fecha_cita} a las {hora_cita} fue cancelada automáticamente por no confirmarse a tiempo.",
                    "fecha": fecha_notif,
                    "leida": False
                }
                requests.post(f"{FIREBASE_DB_URL}/pacientes/{patient_id}/notificaciones.json", json=firebase_payload, timeout=2.0)
            except Exception as fe:
                print("Error al notificar al paciente en Firebase:", fe)
                
            # Sincronizar paciente en segundo plano
            threading.Thread(target=sync_patient_to_firebase, args=(patient_id,)).start()
            
        db.commit()
        print(f"[OK] Auto-canceladas {len(unconfirmed)} citas no confirmadas.")
    except Exception as e:
        print("Error en auto_cancel_unconfirmed_sessions:", e)

def auto_send_appointment_reminders(db):
    """
    Envia notificaciones automaticas de recordatorio de citas del dia
    tanto al psicologo como al paciente (Firebase + SQLite).
    """
    cursor = db.cursor()
    try:
        from datetime import datetime
        import requests
        
        now_dt = datetime.now()
        today_str = now_dt.strftime("%Y-%m-%d")
        
        # Buscar citas agendadas para el día de hoy no canceladas
        cursor.execute("""
            SELECT af.id, af.paciente_id, af.fecha, af.hora, af.tipo_consulta, p.nombres, p.apellidos
            FROM agenda_finanzas af
            JOIN pacientes p ON af.paciente_id = p.id
            WHERE af.fecha = ?
              AND af.confirmada = 1
              AND af.estado_pago NOT LIKE 'Cancelada%'
              AND af.estado_pago != 'Reprogramada'
        """, (today_str,))
        
        today_appts = cursor.fetchall()
        if not today_appts:
            return
            
        now_str = now_dt.strftime("%Y-%m-%d %H:%M:%S")
        for appt in today_appts:
            appt_id = appt['id']
            patient_id = appt['paciente_id']
            pac_nombre = f"{appt['nombres']} {appt['apellidos']}"
            hora_cita = appt['hora']
            notif_link = f"remind_{appt_id}_{today_str}"
            
            # Evitar enviar más de 1 recordatorio al día por la misma cita
            cursor.execute("SELECT id FROM notificaciones WHERE link = ?", (notif_link,))
            if cursor.fetchone():
                continue
                
            # 1. Notificación al psicólogo
            cursor.execute("""
                INSERT INTO notificaciones (tipo, titulo, mensaje, fecha, leida, link)
                VALUES ('cita', '⏰ Recordatorio de Consulta Hoy', ?, ?, 0, ?)
            """, (
                f"Tienes consulta programada hoy con {pac_nombre} a las {hora_cita} ({appt['tipo_consulta']}).",
                now_str,
                notif_link
            ))
            
            # 2. Notificación al paciente en Firebase
            try:
                fb_payload = {
                    "id": int(now_dt.timestamp() * 1000),
                    "tipo": "cita",
                    "titulo": "⏰ Recordatorio de Consulta Hoy",
                    "mensaje": f"Hola {appt['nombres']}, te recordamos tu consulta programada para hoy a las {hora_cita}.",
                    "fecha": now_str,
                    "leida": False
                }
                requests.post(f"{FIREBASE_DB_URL}/pacientes/{patient_id}/notificaciones.json", json=fb_payload, timeout=2.0)
            except Exception as fe:
                pass
                
        db.commit()
    except Exception as e:
        print("Error en auto_send_appointment_reminders:", e)

def auto_send_confirmation_requests(db):
    """
    Notifica al paciente cuando su cita entra dentro de la ventana de horas
    configurada por el psicólogo (alerta_confirmacion, ej: 24h antes) y aún no está confirmada.
    """
    cursor = db.cursor()
    try:
        from datetime import datetime
        import requests, json

        now_dt = datetime.now()
        now_str = now_dt.strftime("%Y-%m-%d %H:%M:%S")
        today_str = now_dt.strftime("%Y-%m-%d")

        # Buscar citas no confirmadas en estado 'Agendada' desde hoy en adelante
        cursor.execute("""
            SELECT af.id, af.paciente_id, af.fecha, af.hora, af.tipo_consulta, p.nombres, p.psicologo_id
            FROM agenda_finanzas af
            JOIN pacientes p ON af.paciente_id = p.id
            WHERE af.confirmada = 0
              AND af.estado_pago = 'Agendada'
              AND af.fecha >= ?
        """, (today_str,))

        unconfirmed_appts = cursor.fetchall()
        for appt in unconfirmed_appts:
            appt_id = appt['id']
            patient_id = appt['paciente_id']
            psicologo_id = appt['psicologo_id']
            fecha_cita = appt['fecha']
            hora_cita = appt['hora']

            # Obtener alerta_confirmacion del psicólogo
            alerta_confirmacion = 24
            if psicologo_id:
                cursor.execute("SELECT configuracion_horarios_visual FROM usuarios WHERE id = ?", (psicologo_id,))
                u_row = cursor.fetchone()
                if u_row and u_row[0]:
                    try:
                        config = json.loads(u_row[0])
                        alerta_confirmacion = int(config.get('alerta_confirmacion', 24))
                    except:
                        pass

            # Calcular horas restantes
            try:
                session_dt = datetime.strptime(f"{fecha_cita} {hora_cita}", "%Y-%m-%d %H:%M")
                diff_hours = (session_dt - now_dt).total_seconds() / 3600.0
            except:
                continue

            # Si ya entró en el rango de confirmación (ej: <= 24h antes) y no ha pasado la cita
            if 0 < diff_hours <= alerta_confirmacion:
                notif_key = f"req_conf_{appt_id}"
                
                # Evitar enviar la notificación repetidamente
                try:
                    res_check = requests.get(f"{FIREBASE_DB_URL}/pacientes/{patient_id}/notificaciones.json", timeout=2.0)
                    if res_check.ok and res_check.json():
                        existing_notifs = res_check.json()
                        already_sent = any(
                            n.get('notif_key') == notif_key for n in existing_notifs.values() if isinstance(n, dict)
                        )
                        if already_sent:
                            continue
                except:
                    pass

                # Enviar notificación a Firebase para el paciente
                try:
                    fb_payload = {
                        "id": int(now_dt.timestamp() * 1000),
                        "notif_key": notif_key,
                        "tipo": "cita",
                        "titulo": "⚠️ Por favor confirma tu consulta",
                        "mensaje": f"Tu consulta del {fecha_cita} a las {hora_cita} ya está disponible para confirmar. ¡Por favor confirma tu asistencia!",
                        "fecha": now_str,
                        "leida": False
                    }
                    requests.post(f"{FIREBASE_DB_URL}/pacientes/{patient_id}/notificaciones.json", json=fb_payload, timeout=2.0)
                except Exception as fe:
                    print("Error enviando notif confirmacion a Firebase:", fe)

        db.commit()
    except Exception as e:
        print("Error en auto_send_confirmation_requests:", e)

@app.before_request
def before_request_cleanup():
    # Evitar ejecutar en llamadas de archivos estáticos
    if request.path.startswith('/static/'):
        return
    db = get_db()
    auto_cancel_unconfirmed_sessions(db)
    auto_send_appointment_reminders(db)
    auto_send_confirmation_requests(db)

def auto_settle_patient_debts(db, patient_id):
    if not patient_id:
        return
    cursor = db.cursor()
    
    cursor.execute("""
        SELECT id, estado_pago, monto, tipo_consulta, referencia 
        FROM agenda_finanzas 
        WHERE paciente_id = ? AND estado_pago IN ('Pendiente', 'Cancelada sin aviso')
          AND (tipo_consulta IS NULL OR tipo_consulta NOT LIKE '%Fraccionad%')
          AND (referencia IS NULL OR referencia NOT LIKE '%pago parcial%')
        ORDER BY fecha ASC, id ASC
    """, (patient_id,))
    debts = cursor.fetchall()
    
    if not debts:
        return
        
    for debt in debts:
        cursor.execute("""
            SELECT id, cantidad_sesiones 
            FROM agenda_finanzas 
            WHERE paciente_id = ? AND estado_pago = 'Prepagada' AND control_uso = 'No consumida'
            ORDER BY fecha ASC, id ASC LIMIT 1
        """, (patient_id,))
        pkg = cursor.fetchone()
        if not pkg:
            break
            
        debt_id = debt['id']
        debt_status = debt['estado_pago']
        new_status = 'Cancelada sin aviso - Paga' if debt_status == 'Cancelada sin aviso' else 'Paga'
        
        pkg_id = pkg['id']
        pkg_cant = pkg['cantidad_sesiones']
        if pkg_cant > 1:
            cursor.execute("UPDATE agenda_finanzas SET cantidad_sesiones = ? WHERE id = ?", (pkg_cant - 1, pkg_id))
        else:
            cursor.execute("UPDATE agenda_finanzas SET control_uso = 'Consumida' WHERE id = ?", (pkg_id,))
            
        cursor.execute("""
            UPDATE agenda_finanzas 
            SET estado_pago = ?, control_uso = 'Consumida', monto = 0.0,
                metodo_pago = 'Descontado de Prepago', referencia = 'Prepago',
                fecha_liquidacion = datetime('now', 'localtime')
            WHERE id = ?
        """, (new_status, debt_id))
        
    db.commit()

def sync_patient_to_firebase(patient_id):
    try:
        import requests
        # Usar sqlite3 directo para evitar depender del contexto g si se corre fuera de una petición
        conn = sqlite3.connect('clinica.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM pacientes WHERE id = ?", (patient_id,))
        patient = cursor.fetchone()
        if not patient:
            conn.close()
            return False
            
        # Obtener el nombre del psicólogo y sus métodos de pago
        psic_nombre = "Psic. Paulo Mora"
        metodos_pago = ""
        if patient["psicologo_id"]:
            cursor.execute("SELECT nombres, apellidos, metodos_pago FROM usuarios WHERE id = ?", (patient["psicologo_id"],))
            psic = cursor.fetchone()
            if psic:
                psic_nombre = f"Psic. {psic['nombres']} {psic['apellidos']}"
                metodos_pago = psic['metodos_pago'] or ""

        patient_data = {
            "id": patient["id"],
            "nombres": patient["nombres"],
            "apellidos": patient["apellidos"],
            "cedula": patient["cedula"],
            "username": patient["username"] or patient["cedula"],
            "password_hash": patient["password_hash"],
            "pregunta_seguridad_1": patient["pregunta_seguridad_1"],
            "respuesta_seguridad_1_hash": patient["respuesta_seguridad_1_hash"],
            "pregunta_seguridad_2": patient["pregunta_seguridad_2"],
            "respuesta_seguridad_2_hash": patient["respuesta_seguridad_2_hash"],
            "email": patient["email"],
            "telefono": patient["telefono"],
            "psicologo_asignado": psic_nombre,
            "metodos_pago": metodos_pago
        }
        
        # Conciliar automáticamente deudas pendientes si el consultante tiene consultas prepagadas
        auto_settle_patient_debts(conn, patient_id)
        
        # 1. Consultas disponibles (prepagadas)
        cursor.execute("""
            SELECT SUM(cantidad_sesiones) FROM agenda_finanzas 
            WHERE paciente_id = ? AND estado_pago = 'Prepagada' AND control_uso = 'No consumida'
        """, (patient_id,))
        prepagadas = cursor.fetchone()[0] or 0
        
        # 2. Deuda agrupada por moneda (incluye Pendiente y Cancelada sin aviso)
        cursor.execute("""
            SELECT moneda, SUM(monto) FROM agenda_finanzas
            WHERE paciente_id = ? AND estado_pago IN ('Pendiente', 'Cancelada sin aviso')
            GROUP BY moneda
        """, (patient_id,))
        deudas = {row[0]: row[1] or 0.0 for row in cursor.fetchall()}
        for currency in ['USD', 'EUR', 'BSD']:
            if currency not in deudas:
                deudas[currency] = 0.0
                
        # 3. Datos clínicos compartidos de la última evolución
        cursor.execute("""
            SELECT anotaciones_proxima, tareas_asignadas, recursos_entregados
            FROM sesiones
            WHERE paciente_id = ?
            ORDER BY fecha DESC, id DESC LIMIT 1
        """, (patient_id,))
        last_session = cursor.fetchone()
        
        compartido = {
            "temas_proxima_sesion": last_session["anotaciones_proxima"] if last_session else "",
            "tareas_asignadas": last_session["tareas_asignadas"] if last_session else "",
            "recursos_entregados": last_session["recursos_entregados"] if last_session else ""
        }
        
        # Obtener próxima cita agendada a partir de hoy que no haya sido evolucionada
        from datetime import datetime
        today_str = datetime.now().strftime("%Y-%m-%d")
        now_time_str = datetime.now().strftime("%H:%M")
        cursor.execute("""
            SELECT fecha, hora, tipo_consulta FROM agenda_finanzas
            WHERE paciente_id = ? 
              AND id NOT IN (SELECT DISTINCT agenda_id FROM sesiones WHERE agenda_id IS NOT NULL)
              AND estado_pago NOT IN ('Cancelada', 'Cancelada con aviso', 'Cancelada sin aviso', 'Cancelada sin aviso - Paga', 'Reprogramada')
              AND (fecha > ? OR (fecha = ? AND hora >= ?))
            ORDER BY fecha ASC, hora ASC LIMIT 1
        """, (patient_id, today_str, today_str, now_time_str))
        next_session_row = cursor.fetchone()
        
        proxima_cita = {
            "fecha": next_session_row["fecha"] if next_session_row else None,
            "hora": next_session_row["hora"] if next_session_row else None,
            "tipo_consulta": next_session_row["tipo_consulta"] if next_session_row else None
        }
        
        conn.close()
        
        # 1. Guardar en /usuarios_pacientes/<username> para inicio de sesión rápido
        username_key = patient_data["username"].replace(".", "_").replace("$", "_").replace("[", "_").replace("]", "_").replace("#", "_").lower()
        requests.put(f"{FIREBASE_DB_URL}/usuarios_pacientes/{username_key}.json", json=patient_data)
        
        # 2. Guardar perfil completo en /pacientes/<id>/perfil
        requests.put(f"{FIREBASE_DB_URL}/pacientes/{patient_id}/perfil.json", json=patient_data)
        
        # 3. Guardar resumen financiero en /pacientes/<id>/finanzas
        requests.put(f"{FIREBASE_DB_URL}/pacientes/{patient_id}/finanzas.json", json={
            "prepagadas": prepagadas,
            "deuda": deudas
        })
        
        # 4. Guardar seguimiento clínico compartido en /pacientes/<id>/compartido
        requests.put(f"{FIREBASE_DB_URL}/pacientes/{patient_id}/compartido.json", json=compartido)
        
        # 5. Guardar próxima cita en /pacientes/<id>/proxima_cita
        requests.put(f"{FIREBASE_DB_URL}/pacientes/{patient_id}/proxima_cita.json", json=proxima_cita)
        
        return True
    except Exception as e:
        print(f"Error syncing to Firebase: {e}")
        return False


# Decorador para requerir inicio de sesión
def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'No autorizado. Debe iniciar sesión.'}), 401
        return f(*args, **kwargs)
    return decorated_function

# Carpeta para archivos adjuntos de evoluciones (ubicación persistente junto al ejecutable/script)
import sys
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'archivos_adjuntos')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.route('/api/upload', methods=['POST'])
def upload_file():
    if 'user_id' not in session and 'patient_id' not in session:
        return jsonify({'error': 'No autorizado. Debe iniciar sesión.'}), 401
        
    if 'file' not in request.files:
        return jsonify({'error': 'No se cargó ningún archivo.'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Nombre de archivo vacío.'}), 400
    
    try:
        import uuid
        ext = os.path.splitext(file.filename)[1]
        unique_name = f"{uuid.uuid4().hex}{ext}"
        filepath = os.path.join(UPLOAD_FOLDER, unique_name)
        file.save(filepath)
        return jsonify({
            'success': 'Archivo subido con éxito.',
            'filename': unique_name,
            'original_name': file.filename
        })
    except Exception as e:
        return jsonify({'error': f'Error al guardar archivo: {str(e)}'}), 500

@app.route('/api/files/<filename>', methods=['GET'])
def get_uploaded_file(filename):
    if 'user_id' not in session and 'patient_id' not in session:
        return jsonify({'error': 'No autorizado.'}), 401
        
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    if not os.path.exists(filepath):
        return jsonify({'error': 'Archivo no encontrado.'}), 404
    return send_file(filepath)

# ==========================================
# RUTAS DE AUTENTICACIÓN
# ==========================================

@app.route('/api/admin-exists', methods=['GET'])
def admin_exists():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT id FROM usuarios LIMIT 1")
    user = cursor.fetchone()
    return jsonify({'exists': user is not None})

@app.route('/api/register/check-cedula', methods=['GET'])
def check_register_cedula():
    cedula = request.args.get('cedula', '').strip()
    if not cedula:
        return jsonify({'error': 'Cédula es requerida.'}), 400
        
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT id, username, nombres, apellidos, cedula, pregunta_seguridad_1, respuesta_seguridad_1_hash FROM pacientes")
    rows = cursor.fetchall()
    
    cleaned_input = ''.join(c for c in cedula if c.isdigit())
    row = None
    for r in rows:
        db_cedula = r['cedula'] or ''
        if db_cedula.strip() == cedula:
            row = r
            break
        if cleaned_input and ''.join(c for c in db_cedula if c.isdigit()) == cleaned_input:
            row = r
            break
            
    if row:
        if row['pregunta_seguridad_1'] and row['respuesta_seguridad_1_hash']:
            return jsonify({'status': 'registered'})
        else:
            return jsonify({
                'status': 'pre_registered', 
                'nombres': row['nombres'], 
                'apellidos': row['apellidos']
            })
            
    return jsonify({'status': 'new_patient'})

@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    tipo_usuario = data.get('tipo_usuario') # 'psicologo' o 'paciente'
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password or not tipo_usuario:
        return jsonify({'error': 'Usuario, contraseña y tipo de usuario son requeridos.'}), 400
        
    db = get_db()
    cursor = db.cursor()
    
    # Verificar si el usuario ya existe en alguna de las dos tablas
    cursor.execute("SELECT id FROM usuarios WHERE LOWER(username) = ?", (username.lower(),))
    if cursor.fetchone():
        return jsonify({'error': 'El nombre de usuario ya está registrado.'}), 400
        
    cursor.execute("SELECT id FROM pacientes WHERE LOWER(username) = ?", (username.lower(),))
    if cursor.fetchone():
        return jsonify({'error': 'El nombre de usuario ya está registrado.'}), 400

    password_hash = generate_password_hash(password)
    
    try:
        if tipo_usuario == 'psicologo':
            nombres = data.get('nombres')
            apellidos = data.get('apellidos')
            estudios = data.get('estudios')
            federacion = data.get('federacion')
            foto_titulo = data.get('foto_titulo', '')
            foto_documento = data.get('foto_documento', '')
            
            import datetime
            now_dt = datetime.datetime.now()
            expiry_dt = now_dt + datetime.timedelta(days=3)
            now_str = now_dt.strftime("%Y-%m-%d %H:%M:%S")
            expiry_str = expiry_dt.strftime("%Y-%m-%d %H:%M:%S")

            import unicodedata
            clean_name = f"psic.{(nombres or '').strip()}{(apellidos or '').strip()}".lower().replace(" ", "")
            if len(clean_name) <= 5:
                clean_name = f"psic.{username.lower()}"
            clean_slug = re.sub(r'[^a-z0-9\.]', '', unicodedata.normalize('NFD', clean_name))

            default_visual_cfg = json.dumps({
                "duracion": 60,
                "costo_online": 30.0,
                "costo_presencial": 35.0,
                "moneda": "USD",
                "alerta_confirmacion": 2,
                "perfiles": [
                    {
                        "nombre": "Horario Estándar",
                        "activo": True,
                        "dias": [
                            {"dia": 1, "nombre": "Lunes", "activo": True, "rangos": [{"inicio": "08:00", "fin": "12:00"}, {"inicio": "14:00", "fin": "18:00"}]},
                            {"dia": 2, "nombre": "Martes", "activo": True, "rangos": [{"inicio": "08:00", "fin": "12:00"}, {"inicio": "14:00", "fin": "18:00"}]},
                            {"dia": 3, "nombre": "Miércoles", "activo": True, "rangos": [{"inicio": "08:00", "fin": "12:00"}, {"inicio": "14:00", "fin": "18:00"}]},
                            {"dia": 4, "nombre": "Jueves", "activo": True, "rangos": [{"inicio": "08:00", "fin": "12:00"}, {"inicio": "14:00", "fin": "18:00"}]},
                            {"dia": 5, "nombre": "Viernes", "activo": True, "rangos": [{"inicio": "08:00", "fin": "12:00"}, {"inicio": "14:00", "fin": "18:00"}]}
                        ]
                    }
                ]
            })

            default_pm_str = "Pago Móvil / Transferencia Bancaria\nZelle / PayPal disponible"

            cursor.execute("""
                INSERT INTO usuarios (username, password_hash, nombres, apellidos, estudios, federacion, foto_titulo, foto_documento, role, activo, fecha_registro, fecha_expiracion_prueba, suscripcion_paga, slug, configuracion_horarios_visual, metodos_pago, primer_inicio)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'psicologo', 1, ?, ?, 0, ?, ?, ?, 1)
            """, (username, password_hash, nombres, apellidos, estudios, federacion, foto_titulo, foto_documento, now_str, expiry_str, clean_slug, default_visual_cfg, default_pm_str))
            db.commit()
            return jsonify({'success': 'Cuenta de psicólogo creada con éxito. Tienes 3 días de prueba gratuita.'})
            
        elif tipo_usuario == 'paciente':
            nombres = data.get('nombres')
            apellidos = data.get('apellidos')
            cedula = data.get('cedula')
            telefono = data.get('telefono')
            email = data.get('email')
            pronombre = data.get('pronombre')
            genero = data.get('genero')
            edad = data.get('edad')
            lugar_nacimiento = data.get('lugar_nacimiento')
            fecha_nacimiento = data.get('fecha_nacimiento')
            residencia_actual = data.get('residencia_actual')
            pais = data.get('pais')
            ciudad = data.get('ciudad')
            con_quien_reside = data.get('con_quien_reside')
            nivel_academico = data.get('nivel_academico')
            ocupacion = data.get('ocupacion')
            estado_civil = data.get('estado_civil')
            contacto_emergencia_nombre = data.get('contacto_emergencia_nombre')
            contacto_emergencia_parentesco = data.get('contacto_emergencia_parentesco')
            motivo_consulta = data.get('motivo_consulta')
            expectativas = data.get('expectativas')
            farmacologia = data.get('farmacologia')
            pregunta_1 = data.get('pregunta_seguridad_1')
            resp_1 = data.get('respuesta_seguridad_1')
            pregunta_2 = data.get('pregunta_seguridad_2')
            resp_2 = data.get('respuesta_seguridad_2')
            psicologo_id = data.get('psicologo_id')
            
            # Verificar si la cédula ya existe (comparación flexible)
            cursor.execute("SELECT id, username, cedula, nombres, apellidos, psicologo_id, pregunta_seguridad_1, respuesta_seguridad_1_hash FROM pacientes")
            all_patients = cursor.fetchall()
            cleaned_input = ''.join(c for c in cedula if c.isdigit()) if cedula else ''
            existing_patient = None
            for p in all_patients:
                db_cedula = p['cedula'] or ''
                if cedula and db_cedula.strip() == cedula:
                    existing_patient = p
                    break
                if cleaned_input and ''.join(c for c in db_cedula if c.isdigit()) == cleaned_input:
                    existing_patient = p
                    break
            
            resp_1_hash = generate_password_hash(resp_1) if resp_1 else None
            resp_2_hash = generate_password_hash(resp_2) if resp_2 else None
            
            if existing_patient:
                if existing_patient['pregunta_seguridad_1'] and existing_patient['respuesta_seguridad_1_hash']:
                    return jsonify({'error': 'La cédula ya está registrada con una cuenta activa.'}), 400
                
                # Paciente pre-registrado: actualizar credenciales de acceso y campos mínimos
                cursor.execute("""
                    UPDATE pacientes
                    SET username = ?, password_hash = ?,
                        pregunta_seguridad_1 = ?, respuesta_seguridad_1_hash = ?,
                        pregunta_seguridad_2 = ?, respuesta_seguridad_2_hash = ?,
                        telefono = COALESCE(?, telefono),
                        email = COALESCE(?, email)
                    WHERE id = ?
                """, (
                    username, password_hash, 
                    pregunta_1, resp_1_hash, 
                    pregunta_2, resp_2_hash,
                    telefono, email,
                    existing_patient['id']
                ))
                patient_id = existing_patient['id']
                target_psic = existing_patient['psicologo_id'] or psicologo_id or 1
                ex_nom = existing_patient['nombres'] if existing_patient['nombres'] else ''
                ex_ape = existing_patient['apellidos'] if existing_patient['apellidos'] else ''
                pat_name = f"{data.get('nombres') or ex_nom} {data.get('apellidos') or ex_ape}".strip() or username
                notif_msg = f"El consultante {pat_name} ha completado la creación de su cuenta de acceso."
            else:
                cursor.execute("""
                    INSERT INTO pacientes (
                        nombres, apellidos, cedula, telefono, email, pronombre, genero, edad,
                        lugar_nacimiento, fecha_nacimiento, residencia_actual, pais, ciudad, con_quien_reside,
                        nivel_academico, ocupacion, estado_civil, contacto_emergencia_nombre,
                        contacto_emergencia_parentesco, motivo_consulta, expectativas, farmacologia,
                        username, password_hash, pregunta_seguridad_1, respuesta_seguridad_1_hash,
                        pregunta_seguridad_2, respuesta_seguridad_2_hash, psicologo_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    nombres, apellidos, cedula, telefono, email, pronombre, genero, edad,
                    lugar_nacimiento, fecha_nacimiento, residencia_actual, pais, ciudad, con_quien_reside,
                    nivel_academico, ocupacion, estado_civil, contacto_emergencia_nombre,
                    contacto_emergencia_parentesco, motivo_consulta, expectativas, farmacologia,
                    username, password_hash, pregunta_1, resp_1_hash, pregunta_2, resp_2_hash, psicologo_id
                ))
                patient_id = cursor.lastrowid
                target_psic = psicologo_id or 1
                pat_name = f"{nombres} {apellidos}".strip() or username
                notif_msg = f"El consultante {pat_name} se ha registrado en la plataforma."

            # Generar notificación interna y push al psicólogo asignado
            from datetime import datetime
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("""
                INSERT INTO notificaciones (user_id, tipo, titulo, mensaje, fecha, leida, link)
                VALUES (?, 'nuevo_paciente', '👤 Nuevo Registro de Consultante', ?, ?, 0, '/#pacientes')
            """, (target_psic, notif_msg, now_str))
            
            send_fcm_notification(user_id=target_psic, title="👤 Nuevo Registro de Consultante", body=notif_msg, url="/#pacientes")
            send_webpush_notification(user_id=target_psic, title="👤 Nuevo Registro de Consultante", body=notif_msg, url="/#pacientes")

            db.commit()
            
            # Sincronización en segundo plano con Firebase
            import threading
            threading.Thread(target=sync_patient_to_firebase, args=(patient_id,)).start()
            
            return jsonify({'success': 'Cuenta de consultante creada con éxito.'})
            
        else:
            return jsonify({'error': 'Tipo de usuario no válido.'}), 400
            
    except Exception as e:
        db.rollback()
        return jsonify({'error': f'Error al registrar: {str(e)}'}), 500

@app.route('/api/active-psychologists', methods=['GET'])
def get_active_psychologists():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT id, nombres, apellidos
        FROM usuarios
        WHERE role = 'psicologo' AND activo = 1
        ORDER BY nombres ASC, apellidos ASC
    """)
    rows = cursor.fetchall()
    return jsonify([{'id': r['id'], 'nombres': r['nombres'], 'apellidos': r['apellidos']} for r in rows])

def get_psychologist_by_id_or_slug(cursor, identifier):
    if not identifier:
        return None
    ident_str = str(identifier).strip().lower()
    
    if ident_str.isdigit():
        cursor.execute("SELECT * FROM usuarios WHERE id = ?", (int(ident_str),))
        r = cursor.fetchone()
        if r:
            return r

    cursor.execute("SELECT * FROM usuarios WHERE LOWER(slug) = ? OR LOWER(username) = ?", (ident_str, ident_str))
    r = cursor.fetchone()
    if r:
        return r

    clean_id = ident_str.replace("psic.", "").replace("psic-", "").strip()
    cursor.execute("SELECT * FROM usuarios WHERE LOWER(slug) LIKE ? OR LOWER(username) LIKE ?", (f"%{clean_id}%", f"%{clean_id}%"))
    return cursor.fetchone()

@app.route('/agendar/<identifier>', methods=['GET'])
def vanity_fast_booking(identifier):
    db = get_db()
    cursor = db.cursor()
    psych = get_psychologist_by_id_or_slug(cursor, identifier)
    psic_id = psych['id'] if psych else 1
    return redirect(f"/?fast_booking={psic_id}")

@app.route('/registro/<identifier>', methods=['GET'])
def vanity_registration(identifier):
    db = get_db()
    cursor = db.cursor()
    psych = get_psychologist_by_id_or_slug(cursor, identifier)
    psic_id = psych['id'] if psych else 1
    return redirect(f"/?ref_psicologo={psic_id}")

@app.route('/api/psychologists/<identifier>/modalities', methods=['GET'])
def get_psychologist_modalities(identifier):
    db = get_db()
    cursor = db.cursor()
    psych = get_psychologist_by_id_or_slug(cursor, identifier)
    psic_id = psych['id'] if psych else 1
    cursor.execute("SELECT configuracion_horarios_visual FROM usuarios WHERE id = ?", (psic_id,))
    u_row = cursor.fetchone()
    modalities = ["Online", "Presencial"] # Default fallback
    if u_row and u_row[0]:
        try:
            import json
            config = json.loads(u_row[0])
            raw_perfiles = config.get('perfiles', [])
            if isinstance(raw_perfiles, dict):
                m_names = list(raw_perfiles.keys())
                if m_names:
                    modalities = m_names
            elif isinstance(raw_perfiles, list):
                m_names = [p.get('nombre') or p.get('modalidad') for p in raw_perfiles if (p.get('nombre') or p.get('modalidad'))]
                if m_names:
                    modalities = list(set(m_names))
        except:
            pass
    return jsonify(modalities)

@app.route('/api/agenda/disponibilidad', methods=['GET'])
def get_agenda_disponibilidad():
    psicologo_id = request.args.get('psicologo_id')
    fecha_str = request.args.get('fecha')
    modalidad = request.args.get('modalidad', 'all')
    
    db = get_db()
    cursor = db.cursor()
    
    if psicologo_id:
        psych = get_psychologist_by_id_or_slug(cursor, psicologo_id)
        if psych:
            psicologo_id = psych['id']
    if not psicologo_id and 'patient_id' in session:
        cursor.execute("SELECT psicologo_id FROM pacientes WHERE id = ?", (session['patient_id'],))
        p_row = cursor.fetchone()
        if p_row and p_row['psicologo_id']:
            psicologo_id = p_row['psicologo_id']
    if not psicologo_id and 'user_id' in session:
        psicologo_id = session['user_id']
    if not psicologo_id:
        cursor.execute("SELECT id FROM usuarios WHERE role != 'superadmin' AND activo = 1 ORDER BY id ASC LIMIT 1")
        first_u = cursor.fetchone()
        psicologo_id = first_u[0] if first_u else 1
        
    cursor.execute("SELECT configuracion_horarios_visual FROM usuarios WHERE id = ?", (psicologo_id,))
    u_row = cursor.fetchone()
    modalidades_list = ["Online", "Presencial"]
    if u_row and u_row[0]:
        try:
            import json
            config = json.loads(u_row[0])
            raw_perfiles = config.get('perfiles', [])
            if isinstance(raw_perfiles, dict):
                modalidades_list = list(raw_perfiles.keys())
            elif isinstance(raw_perfiles, list):
                m_found = [p.get('nombre') or p.get('modalidad') for p in raw_perfiles if (p.get('nombre') or p.get('modalidad'))]
                if m_found:
                    modalidades_list = list(set(m_found))
        except:
            pass
            
    horas_disponibles = []
    slots = []
    if fecha_str:
        slots = generate_dynamic_slots(cursor, psicologo_id, fecha_str, modalidad)
        horas_disponibles = [s['hora_literal'] for s in slots]
        
    return jsonify({
        "modalidades": modalidades_list,
        "horas_disponibles": horas_disponibles,
        "slots": slots,
        "psicologo_timezone": "America/Caracas"
    })

@app.route('/api/fast-booking/book', methods=['POST'])
def fast_booking_book():
    data = request.json
    psicologo_id = data.get('psicologo_id')
    fecha = data.get('fecha')
    hora = data.get('hora')
    modalidad = data.get('modalidad', 'Online')
    cedula = data.get('cedula', '').strip()
    nombres = data.get('nombres', '').strip()
    apellidos = data.get('apellidos', '').strip()
    telefono = data.get('telefono', '').strip()
    
    if not psicologo_id or not fecha or not hora or not cedula or not nombres:
        return jsonify({'error': 'Faltan campos requeridos para agendar.'}), 400
        
    db = get_db()
    cursor = db.cursor()

    psych = get_psychologist_by_id_or_slug(cursor, psicologo_id)
    if psych:
        psicologo_id = psych['id']

    fecha_norm = normalize_date_str(fecha)
    hora_norm = normalize_time_str(hora)
    alt_fecha = fecha_norm
    try:
        dt_tmp = datetime.strptime(fecha_norm, "%Y-%m-%d")
        alt_fecha = dt_tmp.strftime("%d/%m/%Y")
    except:
        pass

    # 0. Verificar si el horario seleccionado ya está reservado por cualquier consultante en ese psicólogo
    cursor.execute("""
        SELECT af.id FROM agenda_finanzas af
        LEFT JOIN pacientes p ON af.paciente_id = p.id
        WHERE (af.fecha = ? OR af.fecha = ?) 
          AND (af.hora = ? OR af.hora LIKE ?)
          AND (p.psicologo_id = ? OR p.psicologo_id IS NULL OR ? IS NULL)
          AND (af.estado_pago IS NULL OR (af.estado_pago NOT LIKE 'Cancelada%' AND af.estado_pago != 'Reprogramada'))
    """, (fecha_norm, alt_fecha, hora_norm, f"{hora_norm}%", psicologo_id, psicologo_id))
    if cursor.fetchone():
        return jsonify({'error': 'El horario seleccionado ya fue reservado. Por favor elige otro horario.'}), 400
    
    # 1. Verificar si el paciente existe por cédula limpia (dígitos), usuario o teléfono
    clean_cedula = cedula.strip()
    digits_cedula = clean_digits_only(clean_cedula)
    digits_telefono = clean_digits_only(telefono)

    cursor.execute("""
        SELECT id, nombres, apellidos, telefono, email 
        FROM pacientes 
        WHERE (LOWER(REPLACE(REPLACE(REPLACE(REPLACE(cedula, 'V-', ''), 'E-', ''), '.', ''), ' ', '')) = ? AND ? != '')
           OR (LOWER(REPLACE(REPLACE(REPLACE(cedula, '.', ''), '-', ''), ' ', '')) = LOWER(REPLACE(REPLACE(REPLACE(?, '.', ''), '-', ''), ' ', '')))
           OR (LOWER(username) = LOWER(?) AND username != '')
    """, (digits_cedula, digits_cedula, clean_cedula, clean_cedula.lower()))
    patient = cursor.fetchone()
    
    is_new_patient = False
    if not patient:
        is_new_patient = True
        try:
            cursor.execute("""
                INSERT INTO pacientes (nombres, apellidos, cedula, telefono, psicologo_id)
                VALUES (?, ?, ?, ?, ?)
            """, (nombres, apellidos, cedula, telefono, psicologo_id))
            patient_id = cursor.lastrowid
            pac_nombre = f"{nombres} {apellidos}"
        except Exception as ex:
            return jsonify({'error': f'Error al registrar paciente automáticamente: {str(ex)}'}), 500
    else:
        patient_id = patient['id']
        pac_nombre = f"{patient['nombres']} {patient['apellidos']}"
        
    try:
        google_event_id = None
        service = get_calendar_service(psicologo_id)
        if service:
            start_datetime = f"{fecha}T{hora}:00-04:00"
            end_hour = str(int(hora.split(':')[0]) + 1).zfill(2)
            end_datetime = f"{fecha}T{end_hour}:{hora.split(':')[1]}:00-04:00"
            
            # Obtener datos del psicólogo
            cursor.execute("SELECT nombres FROM usuarios WHERE id = ?", (psicologo_id,))
            u_row = cursor.fetchone()
            therapist_name = u_row['nombres'] if u_row else "Paulo Mora"
            
            event_body = {
                'summary': f"Consulta Psicológica - {pac_nombre}",
                'description': f"Modalidad: {modalidad}\nPsicólogo: Psic. {therapist_name}",
                'start': {'dateTime': start_datetime, 'timeZone': 'America/Caracas'},
                'end': {'dateTime': end_datetime, 'timeZone': 'America/Caracas'},
                'guestsCanInviteOthers': False,
                'reminders': {
                    'useDefault': False,
                    'overrides': [
                        { 'method': 'email', 'minutes': 1440 },
                        { 'method': 'popup', 'minutes': 60 }
                    ]
                }
            }
            # Si el paciente no es nuevo y tiene correo, lo agregamos como asistente
            email_paciente = None
            if not is_new_patient and patient and patient['email']:
                email_paciente = patient['email']
            
            if email_paciente:
                event_body['attendees'] = [
                    {
                        'email': email_paciente,
                        'displayName': pac_nombre
                    }
                ]
            try:
                g_event = service.events().insert(calendarId='primary', body=event_body, sendUpdates='all').execute()
                google_event_id = g_event.get('id')
            except Exception as ge:
                print("Error creando evento en Google Calendar desde fast-booking:", ge)
                
        monto, moneda = get_appointment_fee(cursor, patient_id, psicologo_id, modalidad)
        
        cursor.execute("""
            INSERT INTO agenda_finanzas (
                paciente_id, fecha, hora, tipo_consulta, monto, moneda, 
                estado_pago, control_uso, google_event_id, cantidad_sesiones, referencia
            ) VALUES (?, ?, ?, ?, ?, ?, 'Agendada', 'No consumida', ?, 1, ?)
        """, (patient_id, fecha, hora, modalidad, monto, moneda, google_event_id, f"Auto-agendada rápida por paciente. Cédula: {cedula}"))
        
        # Enviar notificación al psicólogo en SQLite
        from datetime import datetime
        fecha_notif = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
            INSERT INTO notificaciones (tipo, titulo, mensaje, fecha, leida, link)
            VALUES (?, ?, ?, ?, 0, ?)
        """, ('cita', 'Nueva Cita Agendada (Rápida)', f"{pac_nombre} ha auto-agendado una consulta para el {fecha} a las {hora}.", fecha_notif, 'agenda'))
        
        db.commit()

        # Enviar notificación WebPush al psicólogo
        try:
            send_webpush_notification(
                user_id=psicologo_id,
                title="Nueva Cita Auto-Agendada",
                body=f"{pac_nombre} ha reservado una consulta para el {fecha} a las {hora}.",
                url="/?view=agenda"
            )
        except Exception as wp_ex:
            print("Error al enviar WebPush de auto-agendamiento:", wp_ex)
        
        # Sincronización en Firebase
        import threading
        threading.Thread(target=sync_patient_to_firebase, args=(patient_id,)).start()
        
        return jsonify({'success': 'Tu consulta ha sido agendada con éxito automáticamente.', 'google_synced': google_event_id is not None})
    except Exception as e:
        db.rollback()
        return jsonify({'error': f'Error al agendar consulta: {str(e)}'}), 500

@app.route('/api/superadmin/therapists', methods=['GET'])
@login_required
def superadmin_get_therapists():
    if session.get('role') != 'superadmin':
        return jsonify({'error': 'Acceso denegado. Se requieren permisos de superadministrador.'}), 403
        
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT id, username, nombres, apellidos, estudios, federacion, foto_titulo, foto_documento, activo, fecha_registro, fecha_expiracion_prueba, suscripcion_paga,
               bloqueo_registro, bloqueo_evoluciones, bloqueo_finanzas, bloqueo_agenda, bloqueo_mensajes, bloqueo_pizarra, aviso_pago
        FROM usuarios
        WHERE role = 'psicologo'
        ORDER BY id DESC
    """)
    rows = cursor.fetchall()
    return jsonify([dict(r) for r in rows])

@app.route('/api/superadmin/create-psychologist', methods=['POST'])
@login_required
def superadmin_create_psychologist():
    if session.get('role') != 'superadmin':
        return jsonify({'error': 'Acceso denegado. Se requieren permisos de superadministrador.'}), 403
        
    data = request.json
    nombres = data.get('nombres')
    apellidos = data.get('apellidos')
    username = data.get('username')
    password = data.get('password')
    estudios = data.get('estudios')
    federacion = data.get('federacion')
    foto_titulo = data.get('foto_titulo', '')
    foto_documento = data.get('foto_documento', '')
    
    if not username or not password or not nombres or not apellidos:
        return jsonify({'error': 'Todos los campos requeridos deben ser completados.'}), 400
        
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute("SELECT id FROM usuarios WHERE LOWER(username) = ?", (username.lower(),))
    if cursor.fetchone():
        return jsonify({'error': 'El nombre de usuario ya existe.'}), 400
        
    password_hash = generate_password_hash(password)
    
    try:
        import datetime
        now_dt = datetime.datetime.now()
        expiry_dt = now_dt + datetime.timedelta(days=3)
        now_str = now_dt.strftime("%Y-%m-%d %H:%M:%S")
        expiry_str = expiry_dt.strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute("""
            INSERT INTO usuarios (username, password_hash, nombres, apellidos, estudios, federacion, foto_titulo, foto_documento, role, activo, fecha_registro, fecha_expiracion_prueba, suscripcion_paga)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'psicologo', 1, ?, ?, 0)
        """, (username, password_hash, nombres, apellidos, estudios, federacion, foto_titulo, foto_documento, now_str, expiry_str))
        db.commit()
        return jsonify({'success': 'Psicólogo registrado con éxito (Modo Prueba 3 Días activo).'})
    except Exception as e:
        db.rollback()
        return jsonify({'error': f'Error al registrar psicólogo: {str(e)}'}), 500

@app.route('/api/superadmin/therapists/<int:user_id>/toggle-active', methods=['POST'])
@login_required
def superadmin_toggle_active(user_id):
    if session.get('role') != 'superadmin':
        return jsonify({'error': 'Acceso denegado. Se requieren permisos de superadministrador.'}), 403
        
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT activo FROM usuarios WHERE id = ? AND role = 'psicologo'", (user_id,))
    row = cursor.fetchone()
    if not row:
        return jsonify({'error': 'Psicólogo no encontrado.'}), 404
        
    new_status = 0 if row['activo'] == 1 else 1
    cursor.execute("UPDATE usuarios SET activo = ? WHERE id = ?", (new_status, user_id))
    db.commit()
    return jsonify({'success': 'Estado de suscripción actualizado.', 'activo': new_status})

@app.route('/api/superadmin/therapists/<int:user_id>/toggle-feature', methods=['POST'])
@login_required
def superadmin_toggle_feature(user_id):
    if session.get('role') != 'superadmin':
        return jsonify({'error': 'Acceso denegado. Se requieren permisos de superadministrador.'}), 403
        
    data = request.json or {}
    feature = data.get('feature')
    status = data.get('status')
    
    if feature not in ['registro', 'evoluciones', 'finanzas', 'agenda', 'mensajes', 'pizarra']:
        return jsonify({'error': 'Función no válida.'}), 400
        
    if status not in [0, 1]:
        return jsonify({'error': 'Estado de bloqueo no válido.'}), 400
        
    db = get_db()
    cursor = db.cursor()
    column = f"bloqueo_{feature}"
    cursor.execute(f"UPDATE usuarios SET {column} = ? WHERE id = ? AND role = 'psicologo'", (status, user_id))
    db.commit()
    
    return jsonify({'success': f'Función {feature} actualizada con éxito.', 'feature': feature, 'status': status})

@app.route('/api/superadmin/therapists/<int:user_id>/toggle-aviso-pago', methods=['POST'])
@login_required
def superadmin_toggle_aviso_pago(user_id):
    if session.get('role') != 'superadmin':
        return jsonify({'error': 'Acceso denegado. Se requieren permisos de superadministrador.'}), 403
        
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT aviso_pago FROM usuarios WHERE id = ? AND role = 'psicologo'", (user_id,))
    row = cursor.fetchone()
    if not row:
        return jsonify({'error': 'Psicólogo no encontrado.'}), 404
        
    new_status = 0 if row['aviso_pago'] == 1 else 1
    cursor.execute("UPDATE usuarios SET aviso_pago = ? WHERE id = ?", (new_status, user_id))
    db.commit()
    return jsonify({'success': 'Estado de aviso de pago actualizado.', 'aviso_pago': new_status})

@app.route('/api/support/send', methods=['POST'])
def send_support_ticket():
    data = request.json or {}
    mensaje = data.get('mensaje', '').strip()
    if not mensaje:
        return jsonify({'error': 'El mensaje no puede estar vacío.'}), 400
        
    db = get_db()
    cursor = db.cursor()
    
    usuario_id = None
    rol_remitente = 'anonimo'
    nombre_remitente = data.get('nombre', 'Anónimo').strip()
    email_remitente = data.get('email', '').strip()
    
    # Identificar si está logueado como psicólogo
    if 'user_id' in session:
        usuario_id = session['user_id']
        cursor.execute("SELECT nombres, apellidos, username, role FROM usuarios WHERE id = ?", (usuario_id,))
        usr = cursor.fetchone()
        if usr:
            rol_remitente = usr['role'] # 'psicologo' o 'superadmin'
            nombre_remitente = f"{usr['nombres']} {usr['apellidos']}"
            email_remitente = usr['username']
            
    # Identificar si está logueado como paciente
    elif 'patient_id' in session:
        usuario_id = session['patient_id']
        cursor.execute("SELECT nombres, apellidos, email FROM pacientes WHERE id = ?", (usuario_id,))
        pac = cursor.fetchone()
        if pac:
            rol_remitente = 'paciente'
            nombre_remitente = f"{pac['nombres']} {pac['apellidos']}"
            email_remitente = pac['email'] or ''
            
    fecha = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
        INSERT INTO soporte (usuario_id, rol_remitente, nombre_remitente, email_remitente, mensaje, fecha)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (usuario_id, rol_remitente, nombre_remitente, email_remitente, mensaje, fecha))
    db.commit()
    
    return jsonify({'success': 'Mensaje de soporte enviado con éxito.'})

@app.route('/api/superadmin/support', methods=['GET'])
@login_required
def superadmin_get_support_tickets():
    if session.get('role') != 'superadmin':
        return jsonify({'error': 'Acceso denegado.'}), 403
        
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT id, usuario_id, rol_remitente, nombre_remitente, email_remitente, mensaje, fecha, leido FROM soporte ORDER BY id DESC")
    rows = cursor.fetchall()
    return jsonify([dict(r) for r in rows])

@app.route('/api/superadmin/support/<int:ticket_id>/mark-read', methods=['POST'])
@login_required
def superadmin_mark_ticket_read(ticket_id):
    if session.get('role') != 'superadmin':
        return jsonify({'error': 'Acceso denegado.'}), 403
        
    db = get_db()
    cursor = db.cursor()
    cursor.execute("UPDATE soporte SET leido = 1 WHERE id = ?", (ticket_id,))
    db.commit()
    return jsonify({'success': 'Ticket marcado como leído.'})

@app.route('/api/superadmin/support/<int:ticket_id>', methods=['DELETE'])
@login_required
def superadmin_delete_ticket(ticket_id):
    if session.get('role') != 'superadmin':
        return jsonify({'error': 'Acceso denegado.'}), 403
        
    db = get_db()
    cursor = db.cursor()
    cursor.execute("DELETE FROM soporte WHERE id = ?", (ticket_id,))
    db.commit()
    return jsonify({'success': 'Ticket eliminado.'})

@app.route('/api/register-admin', methods=['POST'])
def register_admin():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({'error': 'Usuario y contraseña son requeridos.'}), 400
        
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute("SELECT id FROM usuarios WHERE LOWER(username) = ?", (username.lower(),))
    if cursor.fetchone():
        return jsonify({'error': 'El nombre de usuario ya está registrado.'}), 400
        
    password_hash = generate_password_hash(password)
    
    cursor.execute("SELECT COUNT(id) FROM usuarios")
    user_count = cursor.fetchone()[0] or 0
    user_role = 'superadmin' if user_count == 0 else 'psicologo'
    
    try:
        cursor.execute("""
            INSERT INTO usuarios (username, password_hash, nombres, apellidos, role, activo)
            VALUES (?, ?, 'Administrador', 'General', ?, 1)
        """, (username, password_hash, user_role))
        db.commit()
        return jsonify({'success': f'Usuario {user_role} creado con éxito.'})
    except Exception as e:
        db.rollback()
        return jsonify({'error': f'Error al registrar administrador: {str(e)}'}), 500

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({'error': 'Usuario y contraseña son requeridos.'}), 400
        
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE LOWER(username) = ?", (username.lower(),))
    user = cursor.fetchone()
    
    if user and check_password_hash(user['password_hash'], password):
        import datetime
        u_dict = dict(user)
        
        # Verificar vencimiento de prueba gratis de 3 días para psicólogos no pagados
        if user['role'] == 'psicologo' and u_dict.get('suscripcion_paga', 0) != 1:
            expiry_str = u_dict.get('fecha_expiracion_prueba')
            if expiry_str:
                try:
                    expiry_dt = datetime.datetime.strptime(expiry_str, "%Y-%m-%d %H:%M:%S")
                    if datetime.datetime.now() > expiry_dt:
                        cursor.execute("UPDATE usuarios SET activo = 0 WHERE id = ?", (user['id'],))
                        db.commit()
                        return jsonify({'error': 'Tu periodo de prueba gratis de 3 días ha vencido. Contacta al administrador para activar tu suscripción.'}), 403
                except Exception:
                    pass
                    
        session.permanent = True
        session['user_id'] = user['id']
        session['username'] = user['username']
        session['role'] = user['role']
        session['activo'] = user['activo']
        u_dict = dict(user)
        return jsonify({
            'success': 'Inicio de sesión correcto.',
            'username': username,
            'role': user['role'],
            'activo': user['activo'],
            'aviso_pago': u_dict.get('aviso_pago', 0),
            'user_id': user['id'],
            'primer_inicio': u_dict.get('primer_inicio', 1) if u_dict.get('primer_inicio') is not None else 1,
            'suscripcion_paga': u_dict.get('suscripcion_paga', 0),
            'fecha_expiracion_prueba': u_dict.get('fecha_expiracion_prueba', ''),
            'bloqueos': {
                'registro': u_dict.get('bloqueo_registro', 0),
                'evoluciones': u_dict.get('bloqueo_evoluciones', 0),
                'finanzas': u_dict.get('bloqueo_finanzas', 0),
                'agenda': u_dict.get('bloqueo_agenda', 0),
                'mensajes': u_dict.get('bloqueo_mensajes', 0),
                'pizarra': u_dict.get('bloqueo_pizarra', 0)
            }
        })
    
    return jsonify({'error': 'Credenciales inválidas.'}), 401

@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'success': 'Sesión cerrada.'})

@app.route('/api/check-username-role', methods=['GET'])
def check_username_role():
    username = request.args.get('username', '').strip()
    if not username:
        return jsonify({'error': 'Nombre de usuario requerido.'}), 400
        
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute("SELECT id FROM usuarios WHERE LOWER(username) = ?", (username.lower(),))
    if cursor.fetchone():
        return jsonify({'role': 'psicologo'})
        
    cursor.execute("SELECT id FROM pacientes WHERE LOWER(username) = ? OR cedula = ?", (username.lower(), username))
    if cursor.fetchone():
        return jsonify({'role': 'paciente'})
        
    return jsonify({'error': 'Usuario no encontrado.'}), 404

@app.route('/api/check-session', methods=['GET'])
def check_session():
    if 'user_id' in session:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("""
            SELECT role, activo, aviso_pago, bloqueo_registro, bloqueo_evoluciones, bloqueo_finanzas, bloqueo_agenda, bloqueo_mensajes, bloqueo_pizarra, primer_inicio, suscripcion_paga, fecha_expiracion_prueba 
            FROM usuarios WHERE id = ?
        """, (session['user_id'],))
        row = cursor.fetchone()
        role = row['role'] if row else 'psicologo'
        activo = row['activo'] if row else 1
        aviso_pago = row['aviso_pago'] if row else 0
        p_inicio = row['primer_inicio'] if row and row['primer_inicio'] is not None else 1
        s_paga = row['suscripcion_paga'] if row and row['suscripcion_paga'] is not None else 0
        f_exp = row['fecha_expiracion_prueba'] if row and row['fecha_expiracion_prueba'] else ''
        return jsonify({
            'logged_in': True,
            'role': role,
            'activo': activo,
            'aviso_pago': aviso_pago,
            'primer_inicio': p_inicio,
            'suscripcion_paga': s_paga,
            'fecha_expiracion_prueba': f_exp,
            'username': session['username'],
            'user_id': session['user_id'],
            'bloqueos': {
                'registro': row['bloqueo_registro'] if row else 0,
                'evoluciones': row['bloqueo_evoluciones'] if row else 0,
                'finanzas': row['bloqueo_finanzas'] if row else 0,
                'agenda': row['bloqueo_agenda'] if row else 0,
                'mensajes': row['bloqueo_mensajes'] if row else 0,
                'pizarra': row['bloqueo_pizarra'] if row else 0
            }
        })
    elif 'patient_id' in session:
        return jsonify({
            'logged_in': True,
            'role': 'paciente',
            'username': session['patient_username'],
            'patient_id': session['patient_id']
        })
    return jsonify({'logged_in': False})

# Decorador para requerir inicio de sesión de paciente
def patient_login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'patient_id' not in session:
            return jsonify({'error': 'No autorizado. Debe iniciar sesión como paciente.'}), 401
        return f(*args, **kwargs)
    return decorated_function

# Endpoints de autenticación y seguridad de pacientes (PWA)
@app.route('/api/patient/login', methods=['POST'])
def patient_login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({'error': 'Usuario y contraseña son requeridos.'}), 400
        
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM pacientes WHERE LOWER(username) = ?", (username.lower(),))
    patient = cursor.fetchone()
    
    if not patient:
        cursor.execute("SELECT * FROM pacientes WHERE cedula = ?", (username,))
        patient = cursor.fetchone()
        
    if not patient:
        digits_user = clean_digits_only(username)
        if digits_user:
            cursor.execute("""
                SELECT * FROM pacientes 
                WHERE REPLACE(REPLACE(REPLACE(REPLACE(cedula, 'V-', ''), 'E-', ''), '.', ''), ' ', '') = ?
            """, (digits_user,))
            patient = cursor.fetchone()
        
    if not patient:
        return jsonify({'error': 'Usuario no registrado.'}), 401
        
    is_default = False
    if not patient['password_hash']:
        clean_pwd = clean_digits_only(password)
        clean_ced = clean_digits_only(patient['cedula'])
        is_default = (password == patient['cedula']) or (clean_pwd != '' and clean_pwd == clean_ced)
    else:
        is_default = check_password_hash(patient['password_hash'], password)
        
    if not is_default:
        return jsonify({'error': 'Contraseña incorrecta.'}), 401
        
    needs_setup = (patient['pregunta_seguridad_1'] is None or patient['respuesta_seguridad_1_hash'] is None)
    
    if needs_setup:
        return jsonify({
            'success': 'Primer acceso detectado. Requiere configuración.',
            'first_login': True,
            'patient_id': patient['id'],
            'username': patient['username'] or patient['cedula']
        })
        
    session.permanent = True
    session['patient_id'] = patient['id']
    session['patient_username'] = patient['username']
    session['role'] = 'paciente'
    
    return jsonify({
        'success': 'Inicio de sesión correcto.',
        'role': 'paciente',
        'patient_id': patient['id'],
        'nombres': patient['nombres'],
        'apellidos': patient['apellidos']
    })

@app.route('/api/patient/setup-first-login', methods=['POST'])
def patient_setup_first_login():
    data = request.json
    patient_id = data.get('patient_id')
    username = data.get('username')
    new_password = data.get('new_password')
    pregunta_1 = data.get('pregunta_1')
    respuesta_1 = data.get('respuesta_1')
    pregunta_2 = data.get('pregunta_2')
    respuesta_2 = data.get('respuesta_2')
    
    if not patient_id or not username or not new_password or not pregunta_1 or not respuesta_1 or not pregunta_2 or not respuesta_2:
        return jsonify({'error': 'Todos los campos son obligatorios.'}), 400
        
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute("SELECT id FROM pacientes WHERE LOWER(username) = ? AND id != ?", (username.lower(), patient_id))
    if cursor.fetchone() is not None:
        return jsonify({'error': 'El nombre de usuario ya está en uso por otro paciente.'}), 400
        
    password_hash = generate_password_hash(new_password)
    resp_1_hash = generate_password_hash(respuesta_1.strip().lower())
    resp_2_hash = generate_password_hash(respuesta_2.strip().lower())
    
    try:
        cursor.execute("""
            UPDATE pacientes 
            SET username = ?, password_hash = ?, 
                pregunta_seguridad_1 = ?, respuesta_seguridad_1_hash = ?,
                pregunta_seguridad_2 = ?, respuesta_seguridad_2_hash = ?,
                pronombre = ?, genero = ?, edad = ?, lugar_nacimiento = ?, fecha_nacimiento = ?, 
                residencia_actual = ?, pais = ?, ciudad = ?, con_quien_reside = ?, nivel_academico = ?, ocupacion = ?, estado_civil = ?,
                telefono = ?, email = ?,
                antecedentes_medicos_familiares = ?, antecedentes_medicos_personales = ?,
                antecedentes_psicologicos_familiares = ?, antecedentes_psicologicos_personales = ?,
                asistencia_previa_psicologo = ?, motivo_consulta = ?, expectativas = ?, farmacologia = ?,
                contacto_emergencia_nombre = ?, contacto_emergencia_parentesco = ?
            WHERE id = ?
        """, (
            username, password_hash, pregunta_1, resp_1_hash, pregunta_2, resp_2_hash,
            data.get('pronombre'), data.get('genero'), data.get('edad'), data.get('lugar_nacimiento'), data.get('fecha_nacimiento'),
            data.get('residencia_actual'), data.get('pais'), data.get('ciudad'), data.get('con_quien_reside'), data.get('nivel_academico'), data.get('ocupacion'), data.get('estado_civil'),
            data.get('telefono'), data.get('email'),
            data.get('antecedentes_medicos_familiares'), data.get('antecedentes_medicos_personales'),
            data.get('antecedentes_psicologicos_familiares'), data.get('antecedentes_psicologicos_personales'),
            data.get('asistencia_previa_psicologo'), data.get('motivo_consulta'), data.get('expectativas'), data.get('farmacologia'),
            data.get('contacto_emergencia_nombre'), data.get('contacto_emergencia_parentesco'),
            patient_id
        ))
        db.commit()
        
        session['patient_id'] = patient_id
        session['patient_username'] = username
        session['role'] = 'paciente'
        
        import threading
        threading.Thread(target=sync_patient_to_firebase, args=(patient_id,)).start()
        
        return jsonify({'success': 'Perfil e historia clínica configurados con éxito. Sesión iniciada.'})
    except Exception as e:
        return jsonify({'error': f'Error al configurar perfil: {str(e)}'}), 500

@app.route('/api/patient/recovery-questions', methods=['POST'])
def patient_recovery_questions():
    data = request.json
    username = data.get('username')
    
    if not username:
        return jsonify({'error': 'Usuario es requerido.'}), 400
        
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT pregunta_seguridad_1, pregunta_seguridad_2 FROM pacientes WHERE LOWER(username) = ? OR cedula = ?", (username.lower(), username))
    patient = cursor.fetchone()
    
    if not patient or not patient['pregunta_seguridad_1'] or not patient['pregunta_seguridad_2']:
        return jsonify({'error': 'El usuario no tiene configuradas preguntas de seguridad o no existe.'}), 404
        
    return jsonify({
        'pregunta_1': patient['pregunta_seguridad_1'],
        'pregunta_2': patient['pregunta_seguridad_2']
    })

@app.route('/api/patient/reset-password', methods=['POST'])
def patient_reset_password():
    data = request.json
    username = data.get('username')
    respuesta_1 = data.get('respuesta_1')
    respuesta_2 = data.get('respuesta_2')
    new_password = data.get('new_password')
    
    if not username or not respuesta_1 or not respuesta_2 or not new_password:
        return jsonify({'error': 'Todos los campos son obligatorios.'}), 400
        
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT id, respuesta_seguridad_1_hash, respuesta_seguridad_2_hash FROM pacientes WHERE LOWER(username) = ? OR cedula = ?", (username.lower(), username))
    patient = cursor.fetchone()
    
    if not patient:
        return jsonify({'error': 'El usuario no existe.'}), 404
        
    match_1 = check_password_hash(patient['respuesta_seguridad_1_hash'], respuesta_1.strip().lower())
    match_2 = check_password_hash(patient['respuesta_seguridad_2_hash'], respuesta_2.strip().lower())
    
    if not match_1 or not match_2:
        return jsonify({'error': 'Respuestas a preguntas de seguridad incorrectas.'}), 401
        
    password_hash = generate_password_hash(new_password)
    try:
        cursor.execute("UPDATE pacientes SET password_hash = ? WHERE id = ?", (password_hash, patient['id']))
        db.commit()
        
        import threading
        threading.Thread(target=sync_patient_to_firebase, args=(patient['id'],)).start()
        
        return jsonify({'success': 'Contraseña restablecida con éxito. Ya puedes iniciar sesión.'})
    except Exception as e:
        return jsonify({'error': f'Error al actualizar contraseña: {str(e)}'}), 500

@app.route('/api/patient/change-password', methods=['POST'])
@patient_login_required
def patient_change_password():
    data = request.json or {}
    current_password = data.get('current_password')
    new_password = data.get('new_password')
    confirm_password = data.get('confirm_password')
    
    if not current_password or not new_password:
        return jsonify({'error': 'Ambas contraseñas son obligatorias.'}), 400

    if confirm_password and new_password != confirm_password:
        return jsonify({'error': 'La nueva contraseña y su confirmación no coinciden.'}), 400

    if len(new_password) < 6:
        return jsonify({'error': 'La nueva contraseña debe tener al menos 6 caracteres.'}), 400
        
    patient_id = session['patient_id']
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT password_hash FROM pacientes WHERE id = ?", (patient_id,))
    patient = cursor.fetchone()
    
    if not patient or not check_password_hash(patient['password_hash'], current_password):
        return jsonify({'error': 'La contraseña actual es incorrecta.'}), 401
        
    password_hash = generate_password_hash(new_password)
    try:
        cursor.execute("UPDATE pacientes SET password_hash = ? WHERE id = ?", (password_hash, patient_id))
        db.commit()
        
        import threading
        threading.Thread(target=sync_patient_to_firebase, args=(patient_id,)).start()
        
        return jsonify({'success': 'Contraseña actualizada con éxito.'})
    except Exception as e:
        db.rollback()
        return jsonify({'error': f'Error al actualizar contraseña: {str(e)}'}), 500

@app.route('/api/user/change-password', methods=['POST'])
@login_required
def user_change_password():
    data = request.json or {}
    current_password = data.get('current_password')
    new_password = data.get('new_password')
    confirm_password = data.get('confirm_password')
    
    if not current_password or not new_password or not confirm_password:
        return jsonify({'error': 'Todos los campos son obligatorios.'}), 400

    if new_password != confirm_password:
        return jsonify({'error': 'La nueva contraseña y su confirmación no coinciden.'}), 400

    if len(new_password) < 6:
        return jsonify({'error': 'La nueva contraseña debe tener al menos 6 caracteres.'}), 400

    user_id = session['user_id']
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT password_hash FROM usuarios WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    
    if not user or not check_password_hash(user['password_hash'], current_password):
        return jsonify({'error': 'La contraseña actual es incorrecta.'}), 401
        
    password_hash = generate_password_hash(new_password)
    try:
        cursor.execute("UPDATE usuarios SET password_hash = ? WHERE id = ?", (password_hash, user_id))
        db.commit()
        return jsonify({'success': 'Contraseña actualizada con éxito.'})
    except Exception as e:
        db.rollback()
        return jsonify({'error': f'Error al actualizar contraseña: {str(e)}'}), 500

@app.route('/api/patient/appointments', methods=['GET'])
@patient_login_required
def patient_appointments():
    patient_id = session['patient_id']
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT af.id, af.fecha, af.hora, af.tipo_consulta, af.estado_pago, af.referencia,
               (CASE WHEN s.id IS NOT NULL THEN 1 ELSE 0 END) as evolucionada
        FROM agenda_finanzas af
        LEFT JOIN sesiones s ON af.id = s.agenda_id
        WHERE af.paciente_id = ?
        ORDER BY af.fecha DESC, af.hora DESC
    """, (patient_id,))
    rows = cursor.fetchall()
    return jsonify([dict(r) for r in rows])

def modality_matches(req_mod, slot_mods):
    if not req_mod or req_mod == 'all' or not slot_mods:
        return True
    req_clean = req_mod.lower().replace('horario', '').strip()
    for sm in slot_mods:
        sm_clean = sm.lower().replace('horario', '').strip()
        if req_clean in sm_clean or sm_clean in req_clean:
            return True
    return False

def generate_dynamic_slots(cursor, psicologo_id, target_date_str, requested_modality='all', exclude_appt_id=None):
    """
    Genera dinámicamente los slots de disponibilidad a partir de configuracion_horarios_visual.
    Aplica de forma transparente:
    1. Bloques por día y modalidad.
    2. División en intervalos fijos de sesión (duracion + receso).
    3. Regla de Cierre (slot_inicio + duracion <= hora_fin_bloque).
    4. Descarte de horas ocupadas en agenda_finanzas.
    5. Descarte de horas dentro del límite de antelación.
    6. Formateo ISO con offset UTC-4.
    """
    import json
    from datetime import datetime, timedelta

    cursor.execute("SELECT configuracion_horarios_visual FROM usuarios WHERE id = ?", (psicologo_id,))
    u_row = cursor.fetchone()
    
    config = {}
    if u_row and u_row['configuracion_horarios_visual']:
        try:
            config = json.loads(u_row['configuracion_horarios_visual'])
        except:
            pass

    if not config:
        cursor.execute("SELECT valor FROM configuracion WHERE clave = 'configuracion_horarios_visual'")
        row = cursor.fetchone()
        if row and row['valor']:
            try:
                config = json.loads(row['valor'])
            except:
                pass

    duracion = int(config.get('duracion', 60))
    receso = int(config.get('receso', 0))
    antelacion = int(config.get('antelacion', 24))
    raw_perfiles = config.get('perfiles', [])
    perfiles = []
    if isinstance(raw_perfiles, dict):
        for k, v in raw_perfiles.items():
            if isinstance(v, dict):
                v_copy = dict(v)
                if 'nombre' not in v_copy:
                    v_copy['nombre'] = k
                perfiles.append(v_copy)
    elif isinstance(raw_perfiles, list):
        perfiles = raw_perfiles

    try:
        target_dt = datetime.strptime(target_date_str, "%Y-%m-%d")
    except:
        return []

    # Python weekday: 0=Mon, 6=Sun. Nuestra app usa: 1=Mon, ..., 6=Sat, 0=Sun
    day_num = (target_dt.weekday() + 1) % 7

    candidate_slots = []
    seen_hours = set()

    req_mod_clean = str(requested_modality or 'all').strip().lower()

    for perf in perfiles:
        perf_modalidad = str(perf.get('modalidad') or perf.get('nombre') or '').strip()
        perf_nombre = str(perf.get('nombre') or perf.get('modalidad') or '').strip()
        perf_mod_clean = perf_modalidad.lower()
        perf_nom_clean = perf_nombre.lower()

        # Filtrar por modalidad requerida (soporta nombre de perfil como 'Horario Uptaeb', 'Horario online', etc.)
        if req_mod_clean != 'all':
            if req_mod_clean not in perf_mod_clean and perf_mod_clean not in req_mod_clean and \
               req_mod_clean not in perf_nom_clean and perf_nom_clean not in req_mod_clean:
                if not ('online' in req_mod_clean and 'online' in perf_mod_clean) and \
                   not ('presencial' in req_mod_clean and 'presencial' in perf_mod_clean):
                    continue

        dias_list = perf.get('dias', [])
        for d in dias_list:
            if int(d.get('dia')) == day_num and d.get('activo', False):
                rangos = d.get('rangos', [])
                for r in rangos:
                    inicio_str = r.get('inicio')
                    fin_str = r.get('fin')
                    if not inicio_str or not fin_str:
                        continue
                    try:
                        start_time = datetime.strptime(inicio_str, "%H:%M")
                        end_time = datetime.strptime(fin_str, "%H:%M")

                        # Auto-corrección si viene en formato 12h (ej. 02:00 a 06:00 -> 14:00 a 18:00)
                        if start_time.hour < 7 and end_time.hour <= 12 and start_time.hour < end_time.hour:
                            start_time = start_time.replace(hour=start_time.hour + 12)
                            if end_time.hour < 12:
                                end_time = end_time.replace(hour=end_time.hour + 12)

                        curr = start_time
                        duration_td = timedelta(minutes=duracion)
                        recess_td = timedelta(minutes=receso)

                        # Regla de cierre: el slot finaliza antes o igual a la hora fin
                        while curr + duration_td <= end_time:
                            h_str = curr.strftime("%H:%M")
                            mod_label = perf_nombre or perf_modalidad or 'Online'
                            if h_str not in seen_hours:
                                seen_hours.add(h_str)
                                candidate_slots.append({
                                    "hora": h_str,
                                    "modalidades": [mod_label]
                                })
                            else:
                                for c in candidate_slots:
                                    if c["hora"] == h_str:
                                        if mod_label and mod_label not in c["modalidades"]:
                                            c["modalidades"].append(mod_label)
                            curr += duration_td + recess_td
                    except Exception as ex_r:
                        pass

    candidate_slots.sort(key=lambda x: x["hora"])

    if not candidate_slots:
        return []

    target_date_norm = normalize_date_str(target_date_str)
    alt_date_str = target_date_norm
    try:
        dt_tmp = datetime.strptime(target_date_norm, "%Y-%m-%d")
        alt_date_str = dt_tmp.strftime("%d/%m/%Y")
    except:
        pass

    # Filtrar slots ocupados en agenda_finanzas para ese psicólogo en CUALQUIER modalidad
    query = """
        SELECT af.hora FROM agenda_finanzas af
        LEFT JOIN pacientes p ON af.paciente_id = p.id
        WHERE (af.fecha = ? OR af.fecha = ?)
          AND (p.psicologo_id = ? OR p.psicologo_id IS NULL OR ? IS NULL)
          AND (af.estado_pago IS NULL OR (af.estado_pago NOT LIKE 'Cancelada%' AND af.estado_pago != 'Reprogramada'))
    """
    params = [target_date_norm, alt_date_str, psicologo_id, psicologo_id]
    if exclude_appt_id:
        query += " AND af.id != ?"
        params.append(exclude_appt_id)

    cursor.execute(query, params)
    booked_rows = cursor.fetchall()
    booked_hours = set(normalize_time_str(row['hora']) for row in booked_rows if row['hora'])

    # Validar horas de antelación
    limit_dt = datetime.now() + timedelta(hours=antelacion)

    valid_slots = []
    for slot_obj in candidate_slots:
        h = normalize_time_str(slot_obj["hora"])
        if h in booked_hours or slot_obj["hora"] in booked_hours:
            continue

        try:
            slot_dt = datetime.strptime(f"{target_date_norm} {h}", "%Y-%m-%d %H:%M")
            if slot_dt < limit_dt:
                continue
        except:
            pass

        iso_str = f"{target_date_norm}T{h}:00-04:00"
        valid_slots.append({
            "iso": iso_str,
            "hora_literal": h,
            "modalidades": slot_obj["modalidades"]
        })

    return valid_slots


@app.route('/api/patient/available-dates', methods=['GET'])
def get_available_dates():
    year = request.args.get('year')
    month = request.args.get('month')
    modalidad = request.args.get('modalidad', 'all')
    exclude_appt_id = request.args.get('exclude_appt_id')
    
    if not year or not month:
        return jsonify({'error': 'Año y mes son requeridos.'}), 400
        
    try:
        import calendar as pycalendar
        year = int(year)
        month = int(month)
        
        db = get_db()
        cursor = db.cursor()
        
        psic_param = request.args.get('psicologo_id')
        psicologo_id = None
        if psic_param:
            psych = get_psychologist_by_id_or_slug(cursor, psic_param)
            if psych:
                psicologo_id = psych['id']
        if not psicologo_id and 'patient_id' in session:
            cursor.execute("SELECT psicologo_id FROM pacientes WHERE id = ?", (session['patient_id'],))
            p_row = cursor.fetchone()
            if p_row:
                psicologo_id = p_row['psicologo_id']
        if not psicologo_id and 'user_id' in session:
            psicologo_id = session['user_id']
        if not psicologo_id:
            cursor.execute("SELECT id FROM usuarios WHERE role = 'psicologo' ORDER BY id ASC LIMIT 1")
            first_u = cursor.fetchone()
            if first_u:
                psicologo_id = first_u[0]
            else:
                psicologo_id = 1

        num_days = pycalendar.monthrange(year, month)[1]
        available_dates = []

        for day in range(1, num_days + 1):
            date_str = f"{year}-{month:02d}-{day:02d}"
            slots = generate_dynamic_slots(cursor, psicologo_id, date_str, modalidad, exclude_appt_id)
            if len(slots) > 0:
                available_dates.append(date_str)
                
        return jsonify({'dates': available_dates})
    except Exception as e:
        return jsonify({'error': f'Error al obtener fechas disponibles: {str(e)}'}), 500


@app.route('/api/patient/available-slots', methods=['GET'])
def get_available_slots():
    date_str = request.args.get('date')
    modalidad = request.args.get('modalidad', 'all')
    exclude_appt_id = request.args.get('exclude_appt_id')
    
    if not date_str:
        return jsonify({'error': 'Fecha es requerida.'}), 400
        
    try:
        db = get_db()
        cursor = db.cursor()
        
        psic_param = request.args.get('psicologo_id')
        psicologo_id = None
        if psic_param:
            psych = get_psychologist_by_id_or_slug(cursor, psic_param)
            if psych:
                psicologo_id = psych['id']
        if not psicologo_id and 'patient_id' in session:
            cursor.execute("SELECT psicologo_id FROM pacientes WHERE id = ?", (session['patient_id'],))
            p_row = cursor.fetchone()
            if p_row:
                psicologo_id = p_row['psicologo_id']
        if not psicologo_id and 'user_id' in session:
            psicologo_id = session['user_id']
        if not psicologo_id:
            cursor.execute("SELECT id FROM usuarios WHERE role = 'psicologo' ORDER BY id ASC LIMIT 1")
            first_u = cursor.fetchone()
            if first_u:
                psicologo_id = first_u[0]
            else:
                psicologo_id = 1

        slots = generate_dynamic_slots(cursor, psicologo_id, date_str, modalidad, exclude_appt_id)
        return jsonify({'slots': slots})
    except Exception as e:
        return jsonify({'error': f'Error al obtener disponibilidad: {str(e)}'}), 500

def get_deadline_datetime(session_date_str, session_time_str, rule_type, rule_value):
    from datetime import datetime, timedelta
    session_dt = datetime.strptime(f"{session_date_str} {session_time_str}", "%Y-%m-%d %H:%M")
    if rule_type == 'horas':
        try:
            hours = float(rule_value)
        except:
            hours = 24.0
        return session_dt - timedelta(hours=hours)
    elif rule_type == 'previo':
        session_date = datetime.strptime(session_date_str, "%Y-%m-%d")
        prev_date = session_date - timedelta(days=1)
        try:
            h, m = map(int, rule_value.split(':'))
        except:
            h, m = 8, 0
        return datetime(prev_date.year, prev_date.month, prev_date.day, h, m)
    elif rule_type == 'mismo_dia':
        session_date = datetime.strptime(session_date_str, "%Y-%m-%d")
        try:
            h, m = map(int, rule_value.split(':'))
        except:
            h, m = 7, 0
        return datetime(session_date.year, session_date.month, session_date.day, h, m)
    else:
        try:
            hours = float(rule_value)
        except:
            hours = 24.0
        return session_dt - timedelta(hours=hours)

def get_rule_description(rule_type, rule_value):
    if rule_type == 'horas':
        return f"{rule_value} horas antes"
    elif rule_type == 'previo':
        return f"el día previo a las {rule_value}"
    elif rule_type == 'mismo_dia':
        return f"el mismo día a las {rule_value}"
    return f"{rule_value} horas antes"

def get_appointment_fee(cursor, patient_id, psicologo_id, tipo_consulta):
    # 1. Buscar costo personalizado y moneda del paciente
    cursor.execute("SELECT costo_personalizado, moneda_personalizada FROM pacientes WHERE id = ?", (patient_id,))
    pac_row = cursor.fetchone()
    if pac_row and pac_row['costo_personalizado'] is not None:
        return float(pac_row['costo_personalizado']), pac_row['moneda_personalizada'] or 'USD'
        
    # 2. Buscar costo por defecto de la modalidad en la configuración del psicólogo
    if psicologo_id:
        cursor.execute("SELECT configuracion_horarios_visual FROM usuarios WHERE id = ?", (psicologo_id,))
        u_row = cursor.fetchone()
        if u_row and u_row[0]:
            try:
                import json
                config = json.loads(u_row[0])
                tarifas = config.get('tarifas', {})
                if tipo_consulta in tarifas:
                    costo_info = tarifas[tipo_consulta]
                    return float(costo_info.get('costo', 0.0)), costo_info.get('moneda', 'USD')
            except Exception as e:
                print("Error al leer tarifas del psicologo:", e)
                
    # 3. Fallback
    return 0.0, 'USD'

@app.route('/api/patient/appointment', methods=['POST'])
@patient_login_required
def patient_add_appointment():
    data = request.json
    db = get_db()
    cursor = db.cursor()
    
    patient_id = session['patient_id']
    fecha = data.get('fecha')
    hora = data.get('hora')
    tipo_consulta = data.get('modalidad') # 'Presencial', 'Online'
    nota = data.get('nota', '').strip()
    
    if not fecha or not hora or not tipo_consulta:
        return jsonify({'error': 'Fecha, Hora y Modalidad son obligatorios.'}), 400
        
    try:
        fecha_norm = normalize_date_str(fecha)
        hora_norm = normalize_time_str(hora)
        alt_fecha = fecha_norm
        try:
            dt_tmp = datetime.strptime(fecha_norm, "%Y-%m-%d")
            alt_fecha = dt_tmp.strftime("%d/%m/%Y")
        except:
            pass

        cursor.execute("SELECT nombres, apellidos, cedula, psicologo_id FROM pacientes WHERE id = ?", (patient_id,))
        paciente = cursor.fetchone()
        psicologo_id = paciente['psicologo_id'] if paciente else 1

        # Verificar si el horario ya está reservado por otro consultante
        cursor.execute("""
            SELECT af.id FROM agenda_finanzas af
            LEFT JOIN pacientes p ON af.paciente_id = p.id
            WHERE (af.fecha = ? OR af.fecha = ?) 
              AND (af.hora = ? OR af.hora LIKE ?)
              AND (p.psicologo_id = ? OR p.psicologo_id IS NULL OR ? IS NULL)
              AND (af.estado_pago IS NULL OR (af.estado_pago NOT LIKE 'Cancelada%' AND af.estado_pago != 'Reprogramada'))
        """, (fecha_norm, alt_fecha, hora_norm, f"{hora_norm}%", psicologo_id, psicologo_id))
        if cursor.fetchone():
            return jsonify({'error': 'El horario seleccionado ya ha sido reservado. Por favor elige otro horario.'}), 400

        google_event_id = None
        service = get_calendar_service(psicologo_id)
        
        if service:
            start_datetime = f"{fecha_norm}T{hora_norm}:00-04:00"
            end_hour = str(int(hora_norm.split(':')[0]) + 1).zfill(2)
            end_datetime = f"{fecha_norm}T{end_hour}:{hora_norm.split(':')[1]}:00-04:00"
            
            event_body = {
                'summary': f"Consulta Auto-agendada: {paciente['nombres']} {paciente['apellidos']}",
                'description': f"Modalidad: {tipo_consulta}\nPaciente: {paciente['nombres']} {paciente['apellidos']}\nCédula: {paciente['cedula']}\nNota: {nota}",
                'start': {'dateTime': start_datetime, 'timeZone': 'America/Caracas'},
                'end': {'dateTime': end_datetime, 'timeZone': 'America/Caracas'},
            }
            try:
                g_event = service.events().insert(calendarId='primary', body=event_body).execute()
                google_event_id = g_event.get('id')
            except Exception as ge:
                print("Error creando evento en Google Calendar desde portal del paciente:", ge)
        
        monto, moneda = get_appointment_fee(cursor, patient_id, psicologo_id, tipo_consulta)
        
        cursor.execute("""
            INSERT INTO agenda_finanzas (
                paciente_id, fecha, hora, tipo_consulta, monto, moneda, 
                estado_pago, control_uso, google_event_id, cantidad_sesiones, referencia
            ) VALUES (?, ?, ?, ?, ?, ?, 'Agendada', 'No consumida', ?, 1, ?)
        """, (patient_id, fecha_norm, hora_norm, tipo_consulta, monto, moneda, google_event_id, f"Auto-agendada por paciente. Nota: {nota}"))
        
        pac_nombre = f"{paciente['nombres']} {paciente['apellidos']}"
        
        from datetime import datetime
        fecha_notif = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
            INSERT INTO notificaciones (tipo, titulo, mensaje, fecha, leida, link)
            VALUES (?, ?, ?, ?, 0, ?)
        """, ('cita', 'Nueva Cita Agendada', f"{pac_nombre} ha agendado una consulta para el {fecha} a las {hora}.", fecha_notif, 'agenda'))
        
        db.commit()

        # Enviar notificación Push al psicólogo
        try:
            send_webpush_notification(
                user_id=psicologo_id,
                title="📅 Nueva Cita Auto-Agendada",
                body=f"{pac_nombre} ha reservado una consulta para el {fecha} a las {hora}.",
                url="/?view=agenda"
            )
        except Exception as wp_ex:
            print("Error al enviar Push de auto-agendamiento por paciente:", wp_ex)

        import threading
        threading.Thread(target=sync_patient_to_firebase, args=(patient_id,)).start()
        
        return jsonify({'success': 'Tu consulta ha sido agendada automáticamente con éxito.', 'google_synced': google_event_id is not None})
    except Exception as e:
        return jsonify({'error': f'Error al agendar consulta automáticamente: {str(e)}'}), 500

@app.route('/api/patient/cancel-appointment', methods=['POST'])
@patient_login_required
def patient_cancel_appointment():
    patient_id = session['patient_id']
    db = get_db()
    cursor = db.cursor()
    
    try:
        from datetime import datetime
        import json
        today_str = datetime.now().strftime("%Y-%m-%d")
        now_time_str = datetime.now().strftime("%H:%M")
        
        req_data = request.json or {}
        appt_id = req_data.get('appt_id')
        
        if appt_id:
            cursor.execute("""
                SELECT id, fecha, hora, tipo_consulta, google_event_id, estado_pago, control_uso, monto, moneda, confirmada
                FROM agenda_finanzas
                WHERE id = ? AND paciente_id = ?
            """, (appt_id, patient_id))
        else:
            cursor.execute("""
                SELECT id, fecha, hora, tipo_consulta, google_event_id, estado_pago, control_uso, monto, moneda, confirmada
                FROM agenda_finanzas
                WHERE paciente_id = ? 
                  AND (fecha > ? OR (fecha = ? AND hora >= ?))
                  AND estado_pago NOT LIKE 'Cancelada%' AND estado_pago != 'Reprogramada'
                ORDER BY fecha ASC, hora ASC LIMIT 1
            """, (patient_id, today_str, today_str, now_time_str))
        
        appt = cursor.fetchone()
        if not appt:
            return jsonify({'error': 'No se encontró la cita especificada o no está activa.'}), 400
            
        appt_dict = dict(appt)
        appt_id = appt_dict['id']
        fecha_cita = appt_dict['fecha']
        hora_cita = appt_dict['hora']
        tipo_consulta = appt_dict.get('tipo_consulta', 'Online')
        google_event_id = appt_dict['google_event_id']
        
        cursor.execute("SELECT nombres, apellidos, psicologo_id FROM pacientes WHERE id = ?", (patient_id,))
        pac = cursor.fetchone()
        pac_nombre = f"{pac['nombres']} {pac['apellidos']}"
        psicologo_id = pac['psicologo_id']
        
        # Obtener límite de cancelación configurado por el psicólogo
        cursor.execute("SELECT configuracion_horarios_visual FROM usuarios WHERE id = ?", (psicologo_id,))
        u_row = cursor.fetchone()
        rule_type = 'horas'
        rule_value = 24
        if u_row and u_row[0]:
            try:
                config = json.loads(u_row[0])
                rule_type = config.get('limite_cancelacion_tipo', 'horas')
                rule_value = config.get('limite_cancelacion_valor', 24)
            except:
                pass
                
        deadline_dt = get_deadline_datetime(fecha_cita, hora_cita, rule_type, rule_value)
        fuera_de_tiempo = datetime.now() > deadline_dt
        
        # Solo se cobra si está fuera de tiempo Y el paciente había confirmado la cita previamente.
        es_late_charge = fuera_de_tiempo and (appt_dict['confirmada'] == 1)
        
        force = req_data.get('force', False)
        
        if es_late_charge and not force:
            desc = get_rule_description(rule_type, rule_value)
            return jsonify({
                'requires_confirmation': True,
                'message': f'Estás cancelando después del límite permitido ({desc}). Esta consulta se cobrará igualmente como cancelada sin aviso. ¿Estás seguro de que deseas proceder?'
            })
            
        if google_event_id:
            service = get_calendar_service()
            if service:
                try:
                    service.events().delete(calendarId='primary', eventId=google_event_id).execute()
                except Exception as ge:
                    print("Error al borrar evento de Google Calendar al cancelar paciente:", ge)
                    
        if es_late_charge:
            # Cancelación tardía cobrada: Se cobra o se descuenta de prepago si existe
            if appt_dict['estado_pago'] in ['Paga', 'Prepagada']:
                cursor.execute("""
                    UPDATE agenda_finanzas
                    SET estado_pago = 'Cancelada sin aviso - Paga', control_uso = 'Consumida', google_event_id = NULL,
                        fecha_liquidacion = datetime('now', 'localtime')
                    WHERE id = ?
                """, (appt_id,))
            else:
                cursor.execute("""
                    SELECT id, cantidad_sesiones 
                    FROM agenda_finanzas 
                    WHERE paciente_id = ? AND estado_pago = 'Prepagada' AND control_uso = 'No consumida'
                    ORDER BY fecha ASC, id ASC LIMIT 1
                """, (patient_id,))
                pkg = cursor.fetchone()
                if pkg:
                    pkg_id = pkg['id']
                    pkg_cant = pkg['cantidad_sesiones']
                    if pkg_cant > 1:
                        cursor.execute("UPDATE agenda_finanzas SET cantidad_sesiones = ? WHERE id = ?", (pkg_cant - 1, pkg_id))
                    else:
                        cursor.execute("UPDATE agenda_finanzas SET control_uso = 'Consumida' WHERE id = ?", (pkg_id,))
                        
                    cursor.execute("""
                        UPDATE agenda_finanzas
                        SET estado_pago = 'Cancelada sin aviso - Paga', control_uso = 'Consumida', monto = 0.0, google_event_id = NULL,
                            metodo_pago = 'Descontado de Prepago', referencia = 'Prepago', fecha_liquidacion = datetime('now', 'localtime')
                        WHERE id = ?
                    """, (appt_id,))
                else:
                    if appt_dict['monto'] == 0.0:
                        costo_real, moneda_real = get_appointment_fee(cursor, patient_id, psicologo_id, tipo_consulta)
                    else:
                        costo_real, moneda_real = appt_dict['monto'], appt_dict['moneda']
                    cursor.execute("""
                        UPDATE agenda_finanzas
                        SET estado_pago = 'Cancelada sin aviso', google_event_id = NULL, monto = ?, moneda = ?, referencia = ?
                        WHERE id = ?
                    """, (costo_real, moneda_real, f"Cancelación tardía de consulta del {fecha_cita} a las {hora_cita}.", appt_id))
            
            create_auto_cancellation_session(
                db, patient_id, appt_id, fecha_cita, tipo_consulta,
                'Cancelada sin aviso',
                f"Consulta cancelada por el consultante fuera del límite de tiempo ({fecha_cita} a las {hora_cita}). Registrada para cobro."
            )
            notif_title = 'Cita Cancelada FUERA DE TIEMPO por Paciente'
            notif_msg = f"{pac_nombre} ha cancelado su consulta para el {fecha_cita} a las {hora_cita} fuera del límite de tiempo (Cita Confirmada). Se registrará para cobro."
        else:
            # Cancelación a tiempo (o no confirmada): No se cobra, se libera el prepago
            cursor.execute("""
                UPDATE agenda_finanzas
                SET estado_pago = 'Cancelada con aviso', control_uso = 'No consumida', monto = 0.0, google_event_id = NULL
                WHERE id = ?
            """, (appt_id,))
            
            create_auto_cancellation_session(
                db, patient_id, appt_id, fecha_cita, tipo_consulta,
                'Cancelada con aviso',
                f"Consulta cancelada por el consultante a tiempo ({fecha_cita} a las {hora_cita})."
            )
            notif_title = 'Cita Cancelada por Paciente'
            if fuera_de_tiempo and appt_dict['confirmada'] == 0:
                notif_msg = f"{pac_nombre} ha cancelado su consulta para el {fecha_cita} a las {hora_cita} fuera de tiempo pero sin confirmar, por lo que se procesa sin cargo."
            else:
                notif_msg = f"{pac_nombre} ha cancelado su consulta programada para el {fecha_cita} a las {hora_cita} a tiempo."
            
        fecha_notif = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
            INSERT INTO notificaciones (tipo, titulo, mensaje, fecha, leida, link)
            VALUES (?, ?, ?, ?, 0, ?)
        """, ('cita', notif_title, notif_msg, fecha_notif, 'agenda'))
        
        db.commit()

        # Notificar al psicólogo por Push
        try:
            send_webpush_notification(
                user_id=psicologo_id,
                title=notif_title,
                body=notif_msg,
                url="/?view=agenda"
            )
        except Exception as wp_ex:
            print("Error al enviar WebPush de cancelación por paciente:", wp_ex)

        import threading
        threading.Thread(target=sync_patient_to_firebase, args=(patient_id,)).start()

        return jsonify({'success': 'Cita cancelada con éxito.'})
    except Exception as e:
        return jsonify({'error': f'Error al cancelar cita: {str(e)}'}), 500

@app.route('/api/patient/confirm-appointment', methods=['POST'])
@patient_login_required
def patient_confirm_appointment():
    patient_id = session['patient_id']
    db = get_db()
    cursor = db.cursor()
    try:
        from datetime import datetime
        import json
        today_str = datetime.now().strftime("%Y-%m-%d")
        now_time_str = datetime.now().strftime("%H:%M")
        
        req_data = request.json or {}
        appt_id = req_data.get('appt_id')
        
        if appt_id:
            cursor.execute("""
                SELECT id, fecha, hora
                FROM agenda_finanzas
                WHERE id = ? AND paciente_id = ? AND confirmada = 0
            """, (appt_id, patient_id))
        else:
            cursor.execute("""
                SELECT id, fecha, hora
                FROM agenda_finanzas
                WHERE paciente_id = ? 
                  AND (fecha > ? OR (fecha = ? AND hora >= ?))
                  AND estado_pago NOT LIKE 'Cancelada%' AND estado_pago != 'Reprogramada'
                  AND confirmada = 0
                ORDER BY fecha ASC, hora ASC LIMIT 1
            """, (patient_id, today_str, today_str, now_time_str))
        
        appt = cursor.fetchone()
        if not appt:
            return jsonify({'error': 'No se encontró la cita especificada para confirmar o ya está confirmada.'}), 400
            
        cursor.execute("SELECT psicologo_id FROM pacientes WHERE id = ?", (patient_id,))
        pac = cursor.fetchone()
        psicologo_id = pac['psicologo_id']
        
        cursor.execute("SELECT configuracion_horarios_visual FROM usuarios WHERE id = ?", (psicologo_id,))
        u_row = cursor.fetchone()
        alerta_confirmacion = 24
        if u_row and u_row[0]:
            try:
                config = json.loads(u_row[0])
                alerta_confirmacion = int(config.get('alerta_confirmacion', 24))
            except:
                pass
                
        session_dt = datetime.strptime(f"{appt['fecha']} {appt['hora']}", "%Y-%m-%d %H:%M")
        diff_hours = (session_dt - datetime.now()).total_seconds() / 3600.0
        
        if diff_hours > alerta_confirmacion:
            return jsonify({'error': f'Aún no puedes confirmar esta cita. Estará disponible {alerta_confirmacion} horas antes de la sesión.'}), 400
            
        cursor.execute("UPDATE agenda_finanzas SET confirmada = 1 WHERE id = ?", (appt['id'],))
        
        # Notificar al psicólogo y al paciente
        cursor.execute("SELECT nombres, apellidos FROM pacientes WHERE id = ?", (patient_id,))
        p_info = cursor.fetchone()
        pac_nombre = f"{p_info['nombres']} {p_info['apellidos']}" if p_info else "El consultante"
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        cursor.execute("""
            INSERT INTO notificaciones (tipo, titulo, mensaje, fecha, leida, link)
            VALUES ('cita', '✅ Cita Confirmada', ?, ?, 0, 'agenda')
        """, (f"{pac_nombre} ha confirmado su asistencia a la consulta del {appt['fecha']} a las {appt['hora']}.", now_str))
        
        try:
            fb_payload = {
                "id": int(datetime.now().timestamp() * 1000),
                "tipo": "cita",
                "titulo": "✅ Cita Confirmada",
                "mensaje": f"Has confirmado exitosamente tu consulta para el {appt['fecha']} a las {appt['hora']}.",
                "fecha": now_str,
                "leida": False
            }
            requests.post(f"{FIREBASE_DB_URL}/pacientes/{patient_id}/notificaciones.json", json=fb_payload, timeout=2.0)
        except Exception as fe:
            pass

        db.commit()
        
        import threading
        threading.Thread(target=sync_patient_to_firebase, args=(patient_id,)).start()
        
        return jsonify({'success': 'Cita confirmada con éxito.'})
    except Exception as e:
        return jsonify({'error': f'Error al confirmar cita: {str(e)}'}), 500

@app.route('/api/patient/reschedule-appointment', methods=['POST'])
def patient_reschedule_appointment():
    patient_id = session.get('patient_id')
    user_id = session.get('user_id')
    if not patient_id and not user_id:
        return jsonify({'error': 'Debe iniciar sesión para reprogramar.'}), 401
        
    db = get_db()
    cursor = db.cursor()
    data = request.json or {}
    new_date = data.get('fecha')
    new_hour = data.get('hora')
    appt_id = data.get('appt_id')
    
    if not new_date or not new_hour:
        return jsonify({'error': 'Fecha y hora requeridas.'}), 400
        
    try:
        from datetime import datetime, timedelta
        import json
        today_str = datetime.now().strftime("%Y-%m-%d")
        now_time_str = datetime.now().strftime("%H:%M")
        
        if appt_id:
            cursor.execute("""
                SELECT id, fecha, hora, google_event_id, paciente_id
                FROM agenda_finanzas
                WHERE id = ?
            """, (appt_id,))
        elif patient_id:
            cursor.execute("""
                SELECT id, fecha, hora, google_event_id, paciente_id
                FROM agenda_finanzas
                WHERE paciente_id = ? 
                  AND (fecha > ? OR (fecha = ? AND hora >= ?))
                  AND estado_pago NOT LIKE 'Cancelada%' AND estado_pago != 'Reprogramada'
                ORDER BY fecha ASC, hora ASC LIMIT 1
            """, (patient_id, today_str, today_str, now_time_str))
        else:
            return jsonify({'error': 'Cita no especificada.'}), 400
        
        appt = cursor.fetchone()
        if not appt:
            return jsonify({'error': 'No se encontró la cita especificada para reprogramar.'}), 400
            
        patient_id = appt['paciente_id']
        appt_id = appt['id']
        old_fecha = appt['fecha']
        old_hora = appt['hora']
        google_event_id = appt['google_event_id']
        
        cursor.execute("SELECT psicologo_id FROM pacientes WHERE id = ?", (patient_id,))
        pac = cursor.fetchone()
        psicologo_id = pac['psicologo_id'] if pac else user_id
        
        cursor.execute("SELECT configuracion_horarios_visual FROM usuarios WHERE id = ?", (psicologo_id,))
        u_row = cursor.fetchone()
        limite_cancelacion = 24
        if u_row and u_row[0]:
            try:
                config = json.loads(u_row[0])
                limite_cancelacion = int(config.get('limite_cancelacion', 24))
            except:
                pass
                
        session_dt = datetime.strptime(f"{old_fecha} {old_hora}", "%Y-%m-%d %H:%M")
        diff_hours = (session_dt - datetime.now()).total_seconds() / 3600.0
        
        if not user_id and diff_hours <= limite_cancelacion:
            return jsonify({'error': f'No puedes reprogramar esta cita. Has superado el límite de {limite_cancelacion} horas antes de la sesión.'}), 400
            
        cursor.execute("""
            SELECT af.id FROM agenda_finanzas af
            JOIN pacientes p ON af.paciente_id = p.id
            WHERE af.fecha = ? AND af.hora = ? AND p.psicologo_id = ?
              AND af.estado_pago NOT LIKE 'Cancelada%' AND af.estado_pago != 'Reprogramada'
        """, (new_date, new_hour, psicologo_id))
        if cursor.fetchone():
            return jsonify({'error': 'El horario seleccionado ya está reservado.'}), 400
            
        if google_event_id:
            service = get_calendar_service(psicologo_id)
            if service:
                try:
                    cursor.execute("SELECT configuracion_horarios_visual FROM usuarios WHERE id = ?", (psicologo_id,))
                    u_row2 = cursor.fetchone()
                    duration = 60
                    if u_row2 and u_row2[0]:
                        try:
                            config2 = json.loads(u_row2[0])
                            duration = int(config2.get('duracion', 60))
                        except:
                            pass
                    start_dt = datetime.strptime(f"{new_date} {new_hour}", "%Y-%m-%d %H:%M")
                    start_iso = f"{new_date}T{new_hour}:00-04:00"
                    end_dt = start_dt + timedelta(minutes=duration)
                    end_iso = end_dt.strftime("%Y-%m-%dT%H:%M:%S-04:00")
                    
                    cursor.execute("SELECT nombres, apellidos, email FROM pacientes WHERE id = ?", (patient_id,))
                    pac_row = cursor.fetchone()
                    pac_email = pac_row['email'] if pac_row else None
                    pac_name = f"{pac_row['nombres']} {pac_row['apellidos']}" if pac_row else ""
                    
                    cursor.execute("SELECT nombres FROM usuarios WHERE id = ?", (psicologo_id,))
                    u_row3 = cursor.fetchone()
                    therapist_name = u_row3['nombres'] if u_row3 else "Paulo Mora"
                    
                    event_body = service.events().get(calendarId='primary', eventId=google_event_id).execute()
                    event_body['summary'] = f"Consulta Psicológica - {pac_name}"
                    event_body['description'] = f"Modalidad: {event_body.get('description', '').split('Modalidad:')[-1].splitlines()[0] if 'Modalidad:' in event_body.get('description', '') else 'Online'}\nPsicólogo: Psic. {therapist_name}\n[Reprogramada]"
                    event_body['start'] = {'dateTime': start_iso, 'timeZone': 'America/Caracas'}
                    event_body['end'] = {'dateTime': end_iso, 'timeZone': 'America/Caracas'}
                    event_body['guestsCanInviteOthers'] = False
                    
                    if pac_email:
                        event_body['attendees'] = [
                            {
                                'email': pac_email,
                                'displayName': pac_name
                            }
                        ]
                    service.events().update(calendarId='primary', eventId=google_event_id, body=event_body, sendUpdates='all').execute()
                except Exception as ge:
                    print("Error updating Google Calendar event during reschedule:", ge)
                    
        cursor.execute("""
            UPDATE agenda_finanzas
            SET fecha = ?, hora = ?, confirmada = 0
            WHERE id = ?
        """, (new_date, new_hour, appt_id))
        
        mod_por = 'Psicólogo' if user_id else 'Paciente'
        fecha_reg = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
            INSERT INTO historial_reprogramaciones (
                paciente_id, agenda_id, fecha_anterior, hora_anterior,
                fecha_nueva, hora_nueva, modificado_por, motivo, fecha_registro
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (patient_id, appt_id, old_fecha, old_hora, new_date, new_hour, mod_por, f"Reprogramado del {old_fecha} {old_hora} al {new_date} {new_hour}", fecha_reg))
        
        cursor.execute("SELECT nombres, apellidos FROM pacientes WHERE id = ?", (patient_id,))
        pac = cursor.fetchone()
        pac_nombre = f"{pac['nombres']} {pac['apellidos']}"
        
        fecha_notif = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
            INSERT INTO notificaciones (tipo, titulo, mensaje, fecha, leida, link)
            VALUES (?, ?, ?, ?, 0, ?)
        """, ('cita', 'Cita Reprogramada por Paciente', f"{pac_nombre} ha reprogramado su consulta del {old_fecha} a las {old_hora} para la nueva fecha: {new_date} a las {new_hour}.", fecha_notif, 'agenda'))
        
        db.commit()

        # Notificar al psicólogo por Push si fue el paciente quien reprogramó
        if not user_id:
            try:
                send_webpush_notification(
                    user_id=psicologo_id,
                    title="📆 Cita Reprogramada por Paciente",
                    body=f"{pac_nombre} ha reprogramado su consulta del {old_fecha} a las {old_hora} para el {new_date} a las {new_hour}.",
                    url="/?view=agenda"
                )
            except Exception as wp_ex:
                print("Error al enviar WebPush de reprogramación por paciente:", wp_ex)

        import threading
        threading.Thread(target=sync_patient_to_firebase, args=(patient_id,)).start()

        return jsonify({'success': 'Cita reprogramada con éxito.'})
    except Exception as e:
        return jsonify({'error': f'Error al reprogramar cita: {str(e)}'}), 500

@app.route('/api/patient/payment', methods=['POST'])
@patient_login_required
def patient_add_payment_report():
    patient_id = session['patient_id']
    data = request.json
    
    monto = data.get('monto')
    moneda = data.get('moneda')
    metodo = data.get('metodo')
    referencia = data.get('referencia')
    fecha = data.get('fecha')
    
    if not monto or not moneda or not metodo or not fecha:
        return jsonify({'error': 'Monto, moneda, método y fecha son obligatorios.'}), 400
        
    try:
        import requests
        from datetime import datetime
        fecha_registro = datetime.now().isoformat()
        
        payment_payload = {
            'monto': monto,
            'moneda': moneda,
            'metodo': metodo,
            'referencia': referencia,
            'fecha': fecha,
            'estado': 'Pendiente de verificación',
            'fecha_registro': fecha_registro
        }
        
        db = get_db()
        cursor = db.cursor()
        
        cursor.execute("""
            INSERT INTO pagos_notificados (paciente_id, monto, moneda, metodo, referencia, fecha, estado, fecha_registro)
            VALUES (?, ?, ?, ?, ?, ?, 'Pendiente de verificación', ?)
        """, (patient_id, monto, moneda, metodo, referencia, fecha, fecha_registro))
        
        # Sincronización secundaria a Firebase (en segundo plano / opcional)
        try:
            fb_res = requests.post(f"{FIREBASE_DB_URL}/pacientes/{patient_id}/pagos_notificados.json", json=payment_payload, timeout=5)
        except Exception as fe:
            print("Error secundario al guardar pago en Firebase:", fe)
            
        cursor.execute("SELECT nombres, apellidos, psicologo_id FROM pacientes WHERE id = ?", (patient_id,))
        pac = cursor.fetchone()
        pac_nombre = f"{pac['nombres']} {pac['apellidos']}"
        psicologo_id = pac['psicologo_id'] or 1
        
        fecha_notif = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
            INSERT INTO notificaciones (tipo, titulo, mensaje, fecha, leida, link)
            VALUES (?, ?, ?, ?, 0, ?)
        """, ('pago', 'Nuevo Pago Notificado', f"{pac_nombre} notificó un pago de {monto} {moneda}.", fecha_notif, 'finance'))
        db.commit()

        # Enviar notificación WebPush al psicólogo
        try:
            send_webpush_notification(
                user_id=psicologo_id,
                title="Nuevo Pago Notificado",
                body=f"El paciente {pac_nombre} ha reportado un pago de {monto} {moneda} para su verificación.",
                url="/?view=finanzas"
            )
        except Exception as wp_ex:
            print("Error al enviar WebPush de pago notificado:", wp_ex)
        
        return jsonify({'success': 'Pago notificado con éxito. Su psicólogo lo verificará pronto.'})
    except Exception as e:
        return jsonify({'error': f'Error al notificar pago: {str(e)}'}), 500

@app.route('/api/patient/pizarra', methods=['GET', 'POST'])
@patient_login_required
def patient_pizarra():
    patient_id = session['patient_id']
    db = get_db()
    cursor = db.cursor()
    
    if request.method == 'POST':
        data = request.json
        contenido = data.get('contenido', '').strip()
        archivo_adjunto = data.get('archivo_adjunto', None)
        estado_animo = data.get('estado_animo', '').strip()
        comentario_animo = data.get('comentario_animo', '').strip()
        emoji_animo = data.get('emoji_animo', '').strip()
        
        if estado_animo and not contenido:
            contenido = f"Estado de ánimo: {emoji_animo} {estado_animo}"
            if comentario_animo:
                contenido += f" — \"{comentario_animo}\""
        
        if not contenido and not archivo_adjunto:
            return jsonify({'error': 'El contenido o archivo adjunto es requerido.'}), 400
            
        from datetime import datetime
        fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        try:
            cursor.execute("""
                INSERT INTO pizarra_terapeutica (paciente_id, fecha, contenido, archivo_adjunto, estado_animo, comentario_animo, emoji_animo)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (patient_id, fecha_actual, contenido, archivo_adjunto, estado_animo, comentario_animo, emoji_animo))
            
            cursor.execute("SELECT nombres, apellidos, psicologo_id FROM pacientes WHERE id = ?", (patient_id,))
            pac = cursor.fetchone()
            pac_nombre = f"{pac['nombres']} {pac['apellidos']}"
            psicologo_id = pac['psicologo_id'] or 1
            
            titulo_notif = "Registro de Estado de Ánimo" if estado_animo else "Actualización de Pizarra"
            mensaje_notif = f"{pac_nombre} registró su estado de ánimo: {emoji_animo} {estado_animo}." if estado_animo else f"{pac_nombre} escribió una reflexión en su pizarra terapéutica."

            cursor.execute("""
                INSERT INTO notificaciones (tipo, titulo, mensaje, fecha, leida, link)
                VALUES (?, ?, ?, ?, 0, ?)
            """, ('pizarra', titulo_notif, mensaje_notif, fecha_actual, 'pizarra-visual'))
            
            db.commit()

            # Enviar notificación WebPush al psicólogo
            try:
                send_webpush_notification(
                    user_id=psicologo_id,
                    title=titulo_notif,
                    body=mensaje_notif,
                    url="/?view=pizarra-visual"
                )
            except Exception as wp_ex:
                print("Error al enviar WebPush de actualización de pizarra:", wp_ex)
            
            try:
                import requests
                firebase_payload = {
                    'fecha': fecha_actual,
                    'contenido': contenido,
                    'archivo_adjunto': archivo_adjunto,
                    'estado_animo': estado_animo,
                    'comentario_animo': comentario_animo,
                    'emoji_animo': emoji_animo
                }
                requests.post(f"{FIREBASE_DB_URL}/pizarra_terapeutica/{patient_id}.json", json=firebase_payload, timeout=2.0)
            except Exception as fb_ex:
                print("Error al sincronizar pizarra con Firebase:", fb_ex)
            
            return jsonify({'success': 'Actualización agregada a tu pizarra con éxito.', 'fecha': fecha_actual})
        except Exception as e:
            return jsonify({'error': f'Error al guardar en pizarra: {str(e)}'}), 500
            
    elif request.method == 'GET':
        try:
            cursor.execute("""
                SELECT fecha, contenido, archivo_adjunto, estado_animo, comentario_animo, emoji_animo FROM pizarra_terapeutica
                WHERE paciente_id = ?
                ORDER BY fecha DESC
            """, (patient_id,))
            rows = cursor.fetchall()
            updates = [{
                'fecha': r['fecha'],
                'contenido': r['contenido'],
                'archivo_adjunto': r['archivo_adjunto'],
                'estado_animo': r['estado_animo'] if 'estado_animo' in r.keys() else None,
                'comentario_animo': r['comentario_animo'] if 'comentario_animo' in r.keys() else None,
                'emoji_animo': r['emoji_animo'] if 'emoji_animo' in r.keys() else None
            } for r in rows]
            return jsonify({'updates': updates})
        except Exception as e:
            return jsonify({'error': f'Error al obtener pizarra: {str(e)}'}), 500
@app.route('/api/patient/portal-data', methods=['GET'])
@patient_login_required
def get_patient_portal_data():
    patient_id = session['patient_id']
    try:
        data = get_patient_portal_data_dict(patient_id)
        if not data:
            return jsonify({'error': 'Paciente no encontrado'}), 404
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': f'Error al obtener datos: {str(e)}'}), 500

DEFAULT_TERMS_TEXT = """Términos y Condiciones del Encuadre Terapéutico
Estimado/a consultante:

A continuación se presentan las condiciones operativas que rigen nuestro proceso terapéutico. Este marco tiene como objetivo proteger el tiempo de ambos, garantizar el compromiso mutuo y brindar una estructura clara a nuestras sesiones.

1. Duración de la Sesión
Cada sesión tiene una duración estimada de entre 45 minutos y 1 hora.

2. Gestión del Tiempo y Tardanzas
Retrasos por parte del consultante:
- Si llegas con retraso a la cita, el tiempo extra se otorgará únicamente si la agenda del terapeuta lo permite.
- Si el terapeuta tiene consultas posteriores, la sesión finalizará a la hora programada originalmente para no afectar el espacio de otros consultantes, aprovechando únicamente los minutos restantes.
- Tolerancia máxima: Pasados 15 minutos de retraso sin notificación, la consulta se considerará como consulta perdida (asistencia fallida) y deberá ser abonada en su totalidad (o descontada del paquete activo).

Retrasos por parte del terapeuta:
- En caso de que el terapeuta inicie la sesión con retraso, se garantizará el cumplimiento del tiempo total asignado (45 a 60 minutos), adaptando la agenda para no perjudicar al consultante.

3. Confirmación, Cancelación y Tiempo de Gracia
Confirmación de la cita:
- Toda sesión requiere confirmación previa. Si llega el día de la cita y esta no ha sido confirmada, el espacio no se reservará y la consulta se registrará automáticamente como cancelada con previo aviso.

Regla de cancelación y tiempo de gracia:
- Una vez confirmada la consulta, dispones de un tiempo de gracia de hasta 3 horas antes de la hora agendada para realizar cualquier cambio o cancelación sin costo alguno (cancelación con aviso).
- Pasado dicho límite (menos de 3 horas antes de la sesión), si cancelas o no te presentas, la sesión se computará como realizada y deberá ser abonada en su totalidad.

4. Paquetes de Sesiones
En caso de contar con un paquete de sesiones prepagado, cualquier inasistencia o cancelación fuera del tiempo de gracia permitido se descontará automáticamente del saldo de sesiones disponibles.

5. Cancelaciones por Parte del Terapeuta
Si el terapeuta debiera cancelar una sesión sin el debido aviso previo, asume el compromiso de reprogramar la consulta en la fecha disponible más próxima, habilitando de ser necesario fines de semana o días feriados para garantizar la atención oportuna.

Al agendar y confirmar tus sesiones a través de la plataforma, declaras haber leído y aceptado estos Términos y Condiciones para el desarrollo del proceso terapéutico."""

@app.route('/api/patient/accept-terms', methods=['POST'])
@patient_login_required
def accept_patient_terms():
    patient_id = session['patient_id']
    db = get_db()
    cursor = db.cursor()
    from datetime import datetime
    now_str = datetime.now().strftime("%d/%m/%Y %H:%M")
    try:
        try:
            cursor.execute("PRAGMA table_info(notificaciones)")
            cols_notif = [row[1] for row in cursor.fetchall()]
            if 'user_id' not in cols_notif:
                cursor.execute("ALTER TABLE notificaciones ADD COLUMN user_id INTEGER")
                db.commit()
        except Exception:
            pass

        cursor.execute("UPDATE pacientes SET terminos_aceptados = 1, fecha_aceptacion_terminos = ? WHERE id = ?", (now_str, patient_id))
        cursor.execute("SELECT nombres, apellidos, psicologo_id FROM pacientes WHERE id = ?", (patient_id,))
        p_row = cursor.fetchone()
        if p_row:
            nombres = p_row[0] if isinstance(p_row, (tuple, list)) else p_row['nombres']
            apellidos = p_row[1] if isinstance(p_row, (tuple, list)) else p_row['apellidos']
            psic_id = (p_row[2] if isinstance(p_row, (tuple, list)) else p_row['psicologo_id']) or 1
            pat_name = f"{nombres} {apellidos}".strip()
            notif_msg = f"El consultante {pat_name} ha aceptado los Términos y Condiciones del Encuadre Terapéutico."
            cursor.execute("""
                INSERT INTO notificaciones (user_id, tipo, titulo, mensaje, fecha, leida, link)
                VALUES (?, 'terminos_aceptados', '📜 Términos Aceptados', ?, ?, 0, '/#pacientes')
            """, (psic_id, notif_msg, now_str))
            send_fcm_notification(user_id=psic_id, title="📜 Términos Aceptados", body=notif_msg, url="/#pacientes")
        db.commit()
        return jsonify({'success': 'Términos y condiciones aceptados.', 'fecha': now_str})
    except Exception as e:
        print("Error en accept_patient_terms:", e)
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/terms', methods=['GET', 'POST'])
@login_required
def admin_terms():
    user_id = session['user_id']
    db = get_db()
    cursor = db.cursor()
    if request.method == 'GET':
        cursor.execute("SELECT terminos_condiciones FROM usuarios WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        terms = (row['terminos_condiciones'] if row and row['terminos_condiciones'] else '').strip()
        if not terms:
            terms = DEFAULT_TERMS_TEXT
        return jsonify({'terms': terms})
    elif request.method == 'POST':
        terms = request.json.get('terms', '').strip()
        cursor.execute("UPDATE usuarios SET terminos_condiciones = ? WHERE id = ?", (terms, user_id))
        db.commit()
        return jsonify({'success': 'Términos y condiciones actualizados correctamente.'})

def get_patient_portal_data_dict(patient_id):
    import sqlite3
    import json
    conn = sqlite3.connect('clinica.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM pacientes WHERE id = ?", (patient_id,))
    patient = cursor.fetchone()
    if not patient:
        conn.close()
        return None
        
    psic_nombre = "Psic. Terapeuta"
    metodos_pago = ""
    terms_text = DEFAULT_TERMS_TEXT
    psic_id = patient["psicologo_id"]
    if not psic_id:
        cursor.execute("SELECT id FROM usuarios WHERE role != 'superadmin' AND activo = 1 ORDER BY id ASC LIMIT 1")
        p_first = cursor.fetchone()
        if p_first:
            psic_id = p_first['id']

    if psic_id:
        cursor.execute("SELECT nombres, apellidos, metodos_pago, terminos_condiciones FROM usuarios WHERE id = ?", (psic_id,))
        psic = cursor.fetchone()
        if psic:
            psic_nombre = f"Psic. {psic['nombres']} {psic['apellidos']}".strip()
            metodos_pago = psic['metodos_pago'] or ""
            if psic['terminos_condiciones'] and psic['terminos_condiciones'].strip():
                terms_text = psic['terminos_condiciones'].strip()

    patient_dict = dict(patient)
    terminos_aceptados = patient_dict.get("terminos_aceptados", 0) or 0

    patient_data = {
        "id": patient["id"],
        "nombres": patient["nombres"],
        "apellidos": patient["apellidos"],
        "cedula": patient["cedula"],
        "username": patient["username"] or patient["cedula"],
        "email": patient["email"],
        "telefono": patient["telefono"],
        "costo_personalizado": patient["costo_personalizado"],
        "costo_paquete_personalizado": patient["costo_paquete_personalizado"],
        "sesiones_paquete_personalizado": patient["sesiones_paquete_personalizado"],
        "moneda_personalizada": patient["moneda_personalizada"] or 'USD',
        "psicologo_asignado": psic_nombre,
        "metodos_pago": metodos_pago,
        "terminos_aceptados": terminos_aceptados
    }
    
    cursor.execute("""
        SELECT SUM(cantidad_sesiones) FROM agenda_finanzas 
        WHERE paciente_id = ? AND estado_pago = 'Prepagada' AND control_uso = 'No consumida'
    """, (patient_id,))
    prepagadas = cursor.fetchone()[0] or 0
    
    cursor.execute("""
        SELECT moneda, SUM(monto) FROM agenda_finanzas
        WHERE paciente_id = ? AND estado_pago IN ('Pendiente', 'Cancelada sin aviso')
        GROUP BY moneda
    """, (patient_id,))
    deudas = {row[0]: row[1] or 0.0 for row in cursor.fetchall()}
    for currency in ['USD', 'EUR', 'BSD']:
        if currency not in deudas:
            deudas[currency] = 0.0

    cursor.execute("""
        SELECT af.id, af.fecha, af.hora, af.tipo_consulta, af.monto, af.moneda, af.estado_pago, af.referencia, af.metodo_pago
        FROM agenda_finanzas af
        WHERE af.paciente_id = ? AND af.estado_pago IN ('Pendiente', 'Cancelada sin aviso')
        ORDER BY af.fecha ASC
    """, (patient_id,))
    deudas_detalle = [dict(r) for r in cursor.fetchall()]
            
    cursor.execute("""
        SELECT resumen_paciente, anotaciones_proxima, tareas_asignadas, recursos_entregados
        FROM sesiones
        WHERE paciente_id = ?
        ORDER BY fecha DESC, id DESC LIMIT 1
    """, (patient_id,))
    last_session = cursor.fetchone()
    
    res_pac_dec = decrypt_clinical_text(last_session["resumen_paciente"]) if (last_session and last_session["resumen_paciente"]) else ""
    temas_prox_dec = decrypt_clinical_text(last_session["anotaciones_proxima"]) if (last_session and last_session["anotaciones_proxima"]) else ""

    compartido = {
        "resumen_sesion": res_pac_dec,
        "temas_proxima_sesion": temas_prox_dec,
        "tareas_asignadas": last_session["tareas_asignadas"] if last_session else "",
        "recursos_entregados": last_session["recursos_entregados"] if last_session else ""
    }
    
    from datetime import datetime, timedelta
    now_dt = datetime.now()
    
    psicologo_id = patient["psicologo_id"] or psic_id
    alerta_confirmacion = 24
    limite_cancelacion = 24
    modalidades = ["Online", "Presencial"]
    metodos_pago = ""
    
    if psicologo_id:
        cursor.execute("SELECT configuracion_horarios_visual, metodos_pago FROM usuarios WHERE id = ?", (psicologo_id,))
        u_row = cursor.fetchone()
        if u_row:
            metodos_pago = u_row['metodos_pago'] or ""
            if u_row['configuracion_horarios_visual']:
                try:
                    config = json.loads(u_row['configuracion_horarios_visual'])
                    alerta_confirmacion = int(config.get('alerta_confirmacion', 24))
                    limite_cancelacion = int(config.get('limite_cancelacion', 24))
                    perfiles = config.get('perfiles', [])
                    if isinstance(perfiles, dict):
                        m_list = list(perfiles.keys())
                        if m_list:
                            modalidades = m_list
                    elif isinstance(perfiles, list):
                        m_list = [p.get('nombre') or p.get('modalidad') for p in perfiles if (isinstance(p, dict) and (p.get('nombre') or p.get('modalidad')))]
                        if m_list:
                            modalidades = m_list
                except:
                    pass

    # Obtener todos los IDs de paciente pertenecientes a la misma persona (por ID, cédula o teléfono)
    pat_cedula_clean = clean_digits_only(patient["cedula"])
    pat_telefono_clean = clean_digits_only(patient["telefono"])

    cursor.execute("""
        SELECT id FROM pacientes
        WHERE id = ?
           OR (REPLACE(REPLACE(REPLACE(REPLACE(cedula, 'V-', ''), 'E-', ''), '.', ''), ' ', '') = ? AND ? != '')
           OR (telefono != '' AND ? != '' AND REPLACE(REPLACE(REPLACE(telefono, '-', ''), ' ', ''), '+', '') LIKE ?)
    """, (patient_id, pat_cedula_clean, pat_cedula_clean, pat_telefono_clean, f"%{pat_telefono_clean}%"))
    all_pat_ids = [r[0] for r in cursor.fetchall()]
    if not all_pat_ids:
        all_pat_ids = [patient_id]

    placeholders = ','.join('?' for _ in all_pat_ids)

    # Citas agendadas del paciente que NO hayan sido evolucionadas (Realizada) ni canceladas
    cursor.execute(f"""
        SELECT id, fecha, hora, tipo_consulta, confirmada, estado_pago, monto, moneda
        FROM agenda_finanzas
        WHERE paciente_id IN ({placeholders})
          AND (hora != '00:00' AND hora != '' AND hora IS NOT NULL)
          AND (estado_pago IS NULL OR (estado_pago NOT LIKE 'Cancelada%' AND estado_pago != 'Reprogramada'))
          AND (
              id NOT IN (
                  SELECT agenda_id FROM sesiones 
                  WHERE agenda_id IS NOT NULL AND (estado = 'Realizada' OR estado LIKE 'Realizada%')
              )
          )
        ORDER BY fecha ASC, hora ASC
    """, all_pat_ids)
    
    candidate_rows = cursor.fetchall()
    proximas_citas = []

    for row in candidate_rows:
        fecha_raw = row["fecha"]
        fecha_str = normalize_date_str(fecha_raw)
        hora_str = normalize_time_str(row["hora"])
        
        try:
            session_dt = datetime.strptime(f"{fecha_str} {hora_str}", "%Y-%m-%d %H:%M")
            diff_hours = (session_dt - now_dt).total_seconds() / 3600.0
        except Exception:
            diff_hours = 0.0

        # Mantener sesiones futuras o de hoy en adelante (no concluidas hace más de 12 horas)
        if diff_hours < -12.0:
            continue

        proximas_citas.append({
            "id": row["id"],
            "fecha": fecha_str,
            "hora": hora_str,
            "tipo_consulta": row["tipo_consulta"],
            "confirmada": row["confirmada"],
            "estado_pago": row["estado_pago"],
            "alerta_confirmacion": alerta_confirmacion,
            "limite_cancelacion": limite_cancelacion,
            "tiempo_restante_horas": diff_hours
        })

    proximas_citas.sort(key=lambda x: (x["fecha"], x["hora"]))
    proxima_cita = proximas_citas[0] if proximas_citas else None
    
    return {
        "perfil": patient_data,
        "finanzas": {
            "prepagadas": prepagadas,
            "deuda": deudas,
            "deudas_detalle": deudas_detalle
        },
        "compartido": compartido,
        "proxima_cita": proxima_cita,
        "proximas_citas": proximas_citas,
        "modalidades": list(set(modalidades)),
        "metodos_pago": metodos_pago,
        "terminos_texto": terms_text,
        "terminos_requeridos": (terminos_aceptados == 0),
        "fecha_aceptacion_terminos": patient_data.get("fecha_aceptacion_terminos")
    }

@app.route('/api/push/public-key', methods=['GET'])
def get_push_public_key():
    db = get_db()
    cursor = db.cursor()
    vapid_keys = get_vapid_keys(cursor)
    db.commit()
    return jsonify({'public_key': vapid_keys['vapid_public_key']})

@app.route('/api/push/subscribe', methods=['POST'])
def subscribe_push():
    data = request.json or {}
    endpoint = data.get('endpoint')
    keys = data.get('keys') or {}
    p256dh = keys.get('p256dh')
    auth = keys.get('auth')

    if not endpoint or not p256dh or not auth:
        return jsonify({'error': 'Suscripción inválida.'}), 400

    user_id = session.get('user_id')
    patient_id = session.get('patient_id')

    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO web_push_subscriptions (user_id, patient_id, endpoint, p256dh, auth)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, patient_id, endpoint, p256dh, auth))
    db.commit()
    return jsonify({'success': 'Suscrito exitosamente a notificaciones Push en segundo plano.'})

@app.route('/api/admin/payments/notified', methods=['GET'])
@login_required
def get_admin_notified_payments():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT pn.id, pn.paciente_id, pn.monto, pn.moneda, pn.metodo, pn.referencia, pn.fecha, pn.estado, pn.fecha_registro,
               p.nombres, p.apellidos
        FROM pagos_notificados pn
        JOIN pacientes p ON pn.paciente_id = p.id
        WHERE pn.estado = 'Pendiente de verificación'
        ORDER BY pn.fecha_registro DESC
    """)
    rows = cursor.fetchall()
    return jsonify([dict(r) for r in rows])

@app.route('/api/admin/payments/verify/<int:payment_id>', methods=['POST'])
@login_required
def verify_admin_payment(payment_id):
    db = get_db()
    cursor = db.cursor()
    try:
        # Obtener datos del pago notificado
        cursor.execute("SELECT * FROM pagos_notificados WHERE id = ?", (payment_id,))
        payment = cursor.fetchone()
        if not payment:
            return jsonify({'error': 'Pago notificado no encontrado.'}), 404

        paciente_id = payment['paciente_id']
        monto_pago = float(payment['monto']) if payment['monto'] else 0.0
        moneda_pago = payment['moneda'] or 'USD'
        metodo_pago = payment['metodo'] or ''
        referencia_pago = payment['referencia'] or ''
        fecha_pago = payment['fecha'] or datetime.datetime.now().strftime('%Y-%m-%d')

        # Marcar el pago notificado como verificado
        cursor.execute("UPDATE pagos_notificados SET estado = 'Verificado' WHERE id = ?", (payment_id,))

        # Buscar citas pendientes de este paciente (en la misma moneda) para liquidarlas
        cursor.execute("""
            SELECT id, monto, estado_pago FROM agenda_finanzas
            WHERE paciente_id = ? AND moneda = ?
              AND estado_pago IN ('Pendiente', 'Cancelada sin aviso')
            ORDER BY fecha ASC, id ASC
        """, (paciente_id, moneda_pago))
        pending_rows = cursor.fetchall()

        remaining = monto_pago
        for row in pending_rows:
            if remaining <= 0:
                break
            row_monto = float(row['monto']) if row['monto'] else 0.0
            if row_monto <= 0:
                continue
            if remaining >= row_monto:
                # Pago cubre toda esta deuda
                new_estado = 'Cancelada sin aviso - Paga' if row['estado_pago'] == 'Cancelada sin aviso' else 'Paga'
                cursor.execute("""
                    UPDATE agenda_finanzas 
                    SET estado_pago = ?, control_uso = 'Consumida',
                        fecha_liquidacion = ?, metodo_pago = ?, referencia = ?, fecha_pago = ?
                    WHERE id = ?
                """, (new_estado, fecha_pago, metodo_pago, referencia_pago, fecha_pago, row['id']))
                remaining -= row_monto
            else:
                # Pago parcial de deuda: reducir la deuda existente al saldo restante y registrar el abono
                nuevo_saldo_deuda = row_monto - remaining
                cursor.execute("""
                    UPDATE agenda_finanzas 
                    SET monto = ? 
                    WHERE id = ?
                """, (nuevo_saldo_deuda, row['id']))
                
                # Registrar el abono recibido
                cursor.execute("""
                    INSERT INTO agenda_finanzas (
                        paciente_id, fecha, hora, tipo_consulta, monto, moneda, estado_pago,
                        control_uso, fecha_liquidacion, cantidad_sesiones, referencia, metodo_pago, fecha_pago, confirmada
                    ) VALUES (?, ?, '00:00', ?, ?, ?, 'Paga', 'Consumida', ?, 0, ?, ?, ?, 1)
                """, (
                    paciente_id, fecha_pago, row['tipo_consulta'] or 'Abono a Deuda',
                    remaining, moneda_pago, fecha_pago,
                    f"Abono parcial a deuda. Ref: {referencia_pago}", metodo_pago, fecha_pago
                ))
                remaining = 0

        if remaining > 0:
            cursor.execute("SELECT costo_paquete_personalizado, sesiones_paquete_personalizado, psicologo_id FROM pacientes WHERE id = ?", (paciente_id,))
            pac = cursor.fetchone()
            num_sesiones = 1
            if pac and pac['sesiones_paquete_personalizado']:
                pkg_cost = float(pac['costo_paquete_personalizado'] or 0)
                pkg_count = int(pac['sesiones_paquete_personalizado'])
                if pkg_cost > 0 and abs(remaining - pkg_cost) < 0.01:
                    num_sesiones = pkg_count
                elif pkg_cost > 0 and remaining >= pkg_cost:
                    calc = int((remaining / pkg_cost) * pkg_count)
                    if calc > 0:
                        num_sesiones = calc

            cursor.execute("""
                INSERT INTO agenda_finanzas (
                    paciente_id, fecha, hora, tipo_consulta, monto, moneda, estado_pago,
                    control_uso, fecha_liquidacion, cantidad_sesiones, referencia, metodo_pago, fecha_pago
                ) VALUES (?, ?, '00:00', 'Online', ?, ?, 'Prepagada', 'No consumida', ?, ?, ?, ?, ?)
            """, (paciente_id, fecha_pago, remaining, moneda_pago, fecha_pago, num_sesiones, f"Saldo prepagado verificado ({num_sesiones} consultas). Ref: {referencia_pago}", metodo_pago, fecha_pago))

        db.commit()
        auto_settle_patient_debts(db, paciente_id)

        # Notificación Push al paciente de Pago Verificado
        try:
            fb_payload = {
                "id": int(datetime.datetime.now().timestamp() * 1000),
                "tipo": "pago",
                "titulo": "💵 Pago Verificado con Éxito",
                "mensaje": f"Tu pago de {monto_pago} {moneda_pago} (Ref: {referencia_pago}) ha sido verificado con éxito.",
                "fecha": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "leida": False
            }
            requests.post(f"{FIREBASE_DB_URL}/pacientes/{paciente_id}/notificaciones.json", json=fb_payload, timeout=2.0)
        except Exception as fe:
            print("Error al notificar verificación de pago al paciente:", fe)

        # Enviar notificación WebPush al paciente
        try:
            send_webpush_notification(
                patient_id=paciente_id,
                title="💵 Pago Verificado con Éxito",
                body=f"Tu pago de {monto_pago} {moneda_pago} (Ref: {referencia_pago}) ha sido verificado con éxito.",
                url="/?view=patient-payments"
            )
        except Exception as wp_ex:
            print("Error al enviar WebPush de pago verificado:", wp_ex)

        # Sincronizar con Firebase
        try:
            import threading
            threading.Thread(target=sync_patient_to_firebase, args=(paciente_id,)).start()
        except:
            pass

        return jsonify({'success': 'Pago verificado y deudas actualizadas con éxito.'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/reset-test-data', methods=['POST'])
@login_required
def reset_test_data():
    db = get_db()
    cursor = db.cursor()
    try:
        tables_to_clear = [
            'agenda_finanzas',
            'sesiones',
            'pizarra_terapeutica',
            'notificaciones',
            'soporte',
            'pagos_notificados'
        ]
        for table in tables_to_clear:
            cursor.execute(f"DELETE FROM {table}")
            cursor.execute(f"DELETE FROM sqlite_sequence WHERE name='{table}'")
            
        cursor.execute("UPDATE pacientes SET psicologo_id = 1 WHERE cedula IN ('26540973', '84586641')")
        db.commit()
        
        # Sincronizar Firebase si corresponde
        try:
            sync_patient_to_firebase(3) # Leo
            sync_patient_to_firebase(7) # Eulogio
        except:
            pass
            
        return jsonify({'success': 'Datos de consultas, evoluciones y pagos restablecidos a cero con éxito.'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/payments/reject/<int:payment_id>', methods=['POST'])
@login_required
def reject_admin_payment(payment_id):
    data = request.json
    note = data.get('nota_rechazo', '').strip()
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("""
            UPDATE pagos_notificados 
            SET estado = 'Requerir nuevos datos', motivo_rechazo = ? 
            WHERE id = ?
        """, (note, payment_id))
        db.commit()
        return jsonify({'success': 'Pago rechazado localmente con éxito.'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/patient/payments/notified', methods=['GET'])
@patient_login_required
def get_patient_notified_payments_history():
    patient_id = session['patient_id']
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT id, monto, moneda, metodo, referencia, fecha, estado, motivo_rechazo, fecha_registro
        FROM pagos_notificados
        WHERE paciente_id = ?
        ORDER BY fecha_registro DESC
    """, (patient_id,))
    rows = cursor.fetchall()
    return jsonify([dict(r) for r in rows])

@app.route('/api/patient/sessions', methods=['GET'])
@patient_login_required
def get_patient_session_history():
    patient_id = session['patient_id']
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT id, fecha, modalidad, resumen_paciente, tareas_asignadas, recursos_entregados, anotaciones_proxima, archivo_adjunto
        FROM sesiones
        WHERE paciente_id = ? AND estado = 'Realizada'
        ORDER BY fecha DESC, id DESC
    """, (patient_id,))
    rows = cursor.fetchall()
    results = []
    for r in rows:
        d = dict(r)
        d['resumen_paciente'] = decrypt_clinical_text(d.get('resumen_paciente')) or ''
        results.append(d)
    return jsonify(results)

@app.route('/api/admin/pizarra', methods=['GET'])
@login_required
def admin_pizarra():
    patient_id = request.args.get('patient_id')
    db = get_db()
    cursor = db.cursor()
    psic_id = get_psicologo_id_filter()
    
    try:
        if patient_id:
            if psic_id is not None:
                cursor.execute("""
                    SELECT p.id, p.paciente_id, p.fecha, p.contenido, p.archivo_adjunto, pac.nombres, pac.apellidos
                    FROM pizarra_terapeutica p
                    JOIN pacientes pac ON p.paciente_id = pac.id
                    WHERE p.paciente_id = ? AND pac.psicologo_id = ?
                    ORDER BY p.fecha DESC
                """, (patient_id, psic_id))
            else:
                cursor.execute("""
                    SELECT p.id, p.paciente_id, p.fecha, p.contenido, p.archivo_adjunto, pac.nombres, pac.apellidos
                    FROM pizarra_terapeutica p
                    JOIN pacientes pac ON p.paciente_id = pac.id
                    WHERE p.paciente_id = ?
                    ORDER BY p.fecha DESC
                """, (patient_id,))
        else:
            if psic_id is not None:
                cursor.execute("""
                    SELECT p.id, p.paciente_id, p.fecha, p.contenido, p.archivo_adjunto, pac.nombres, pac.apellidos
                    FROM pizarra_terapeutica p
                    JOIN pacientes pac ON p.paciente_id = pac.id
                    WHERE pac.psicologo_id = ?
                    ORDER BY p.fecha DESC
                """, (psic_id,))
            else:
                cursor.execute("""
                    SELECT p.id, p.paciente_id, p.fecha, p.contenido, p.archivo_adjunto, pac.nombres, pac.apellidos
                    FROM pizarra_terapeutica p
                    JOIN pacientes pac ON p.paciente_id = pac.id
                    ORDER BY p.fecha DESC
                """)
            
        rows = cursor.fetchall()
        updates = [{
            'id': r['id'],
            'paciente_id': r['paciente_id'],
            'fecha': r['fecha'],
            'contenido': r['contenido'],
            'archivo_adjunto': r['archivo_adjunto'],
            'paciente_nombre': f"{r['nombres']} {r['apellidos']}"
        } for r in rows]
        
        return jsonify({'updates': updates})
    except Exception as e:
        return jsonify({'error': f'Error al obtener pizarra para el administrador: {str(e)}'}), 500

@app.route('/api/admin/notifications', methods=['GET'])
@login_required
def admin_notifications():
    db = get_db()
    cursor = db.cursor()
    psic_id = get_psicologo_id_filter()
    try:
        if psic_id is not None:
            cursor.execute("""
                SELECT id, tipo, titulo, mensaje, fecha, leida, link
                FROM notificaciones
                WHERE user_id = ? OR user_id IS NULL
                ORDER BY fecha DESC, id DESC LIMIT 25
            """, (psic_id,))
            rows = cursor.fetchall()
            
            cursor.execute("SELECT COUNT(id) FROM notificaciones WHERE (user_id = ? OR user_id IS NULL) AND leida = 0", (psic_id,))
            unread_count = cursor.fetchone()[0] or 0
        else:
            cursor.execute("""
                SELECT id, tipo, titulo, mensaje, fecha, leida, link
                FROM notificaciones
                ORDER BY fecha DESC, id DESC LIMIT 25
            """)
            rows = cursor.fetchall()
            cursor.execute("SELECT COUNT(id) FROM notificaciones WHERE leida = 0")
            unread_count = cursor.fetchone()[0] or 0
        
        list_notif = [{
            'id': r['id'],
            'tipo': r['tipo'],
            'titulo': r['titulo'],
            'mensaje': r['mensaje'],
            'fecha': r['fecha'],
            'leida': bool(r['leida']),
            'link': r['link']
        } for r in rows]
        
        return jsonify({
            'notifications': list_notif,
            'unread_count': unread_count
        })
    except Exception as e:
        return jsonify({'error': f'Error al obtener notificaciones: {str(e)}'}), 500

@app.route('/api/admin/notifications/mark-read', methods=['POST'])
@login_required
def admin_notifications_mark_read():
    data = request.json or {}
    notification_id = data.get('notification_id')
    db = get_db()
    cursor = db.cursor()
    psic_id = get_psicologo_id_filter()
    try:
        if notification_id:
            if psic_id is not None:
                cursor.execute("UPDATE notificaciones SET leida = 1 WHERE id = ? AND (user_id = ? OR user_id IS NULL)", (notification_id, psic_id))
            else:
                cursor.execute("UPDATE notificaciones SET leida = 1 WHERE id = ?", (notification_id,))
        else:
            if psic_id is not None:
                cursor.execute("UPDATE notificaciones SET leida = 1 WHERE user_id = ? OR user_id IS NULL", (psic_id,))
            else:
                cursor.execute("UPDATE notificaciones SET leida = 1")
        db.commit()
        return jsonify({'success': 'Notificación marcada como leída.'})
    except Exception as e:
        return jsonify({'error': f'Error al marcar notificaciones: {str(e)}'}), 500

@app.route('/api/admin/message-templates', methods=['GET', 'POST'])
@login_required
def admin_message_templates():
    db = get_db()
    cursor = db.cursor()
    
    if request.method == 'GET':
        templates = {}
        for key in ['msg_confirmacion', 'msg_recordatorio', 'msg_cierre']:
            cursor.execute("SELECT valor FROM configuracion WHERE clave = ?", (key,))
            row = cursor.fetchone()
            templates[key] = row['valor'] if row else ""
        return jsonify(templates)
        
    data = request.json
    try:
        for key in ['msg_confirmacion', 'msg_recordatorio', 'msg_cierre']:
            if key in data:
                cursor.execute("INSERT OR REPLACE INTO configuracion (clave, valor) VALUES (?, ?)", (key, data[key]))
        db.commit()
        return jsonify({'success': 'Plantillas de mensajes actualizadas con éxito.'})
    except Exception as e:
        return jsonify({'error': f'Error al actualizar plantillas: {str(e)}'}), 500

@app.route('/api/admin/payment-methods', methods=['GET', 'POST'])
@login_required
def admin_payment_methods():
    db = get_db()
    cursor = db.cursor()
    user_id = session.get('user_id')
    
    if request.method == 'GET':
        cursor.execute("SELECT metodos_pago FROM usuarios WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        return jsonify({'metodos_pago': row['metodos_pago'] if row else ""})
        
    data = request.json
    metodos = data.get('metodos_pago', '').strip()
    try:
        cursor.execute("UPDATE usuarios SET metodos_pago = ? WHERE id = ?", (metodos, user_id))
        db.commit()
        return jsonify({'success': 'Métodos de pago actualizados con éxito.'})
    except Exception as e:
        db.rollback()
        return jsonify({'error': f'Error al actualizar métodos de pago: {str(e)}'}), 500

@app.route('/api/admin/message-templates/render', methods=['GET'])
@login_required
def admin_message_templates_render():
    appt_id = request.args.get('appointment_id')
    template_type = request.args.get('template_type')
    
    if not appt_id or not template_type:
        return jsonify({'error': 'appointment_id y template_type son requeridos.'}), 400
        
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("""
            SELECT a.id, a.fecha, a.hora, a.tipo_consulta, p.nombres, p.apellidos, p.telefono
            FROM agenda_finanzas a
            JOIN pacientes p ON a.paciente_id = p.id
            WHERE a.id = ?
        """, (appt_id,))
        appt = cursor.fetchone()
        if not appt:
            return jsonify({'error': 'Cita no encontrada.'}), 404
            
        key = f"msg_{template_type}"
        cursor.execute("SELECT valor FROM configuracion WHERE clave = ?", (key,))
        row = cursor.fetchone()
        template = row['valor'] if row else ""
        
        nombre = f"{appt['nombres']} {appt['apellidos']}"
        fecha = appt['fecha']
        hora = appt['hora']
        modalidad = appt['tipo_consulta']
        
        try:
            from datetime import datetime
            date_obj = datetime.strptime(fecha, "%Y-%m-%d")
            fecha_amigable = date_obj.strftime("%d/%m/%Y")
        except:
            fecha_amigable = fecha
            
        try:
            h, m = map(int, hora.split(':'))
            ampm = "PM" if h >= 12 else "AM"
            h_12 = h - 12 if h > 12 else (12 if h == 0 else h)
            hora_amigable = f"{str(h_12).zfill(2)}:{str(m).zfill(2)} {ampm}"
        except:
            hora_amigable = hora
            
        link_conexion = "https://meet.google.com/abc-defg-hij"
        
        rendered_message = template.replace("{nombre}", nombre)\
                                   .replace("{fecha}", fecha_amigable)\
                                   .replace("{hora}", hora_amigable)\
                                   .replace("{modalidad}", modalidad)\
                                   .replace("{link_conexion}", link_conexion)
                                   
        phone_cleaned = "".join([c for c in appt['telefono'] or "" if c.isdigit()])
        if phone_cleaned and not phone_cleaned.startswith("58") and len(phone_cleaned) == 10:
            phone_cleaned = "58" + phone_cleaned
            
        import urllib.parse
        encoded_message = urllib.parse.quote(rendered_message)
        wa_url = f"https://wa.me/{phone_cleaned}?text={encoded_message}"
        
        return jsonify({
            'message': rendered_message,
            'phone': phone_cleaned,
            'wa_url': wa_url
        })
    except Exception as e:
        return jsonify({'error': f'Error al renderizar mensaje: {str(e)}'}), 500

def get_psicologo_antelacion_horas(psicologo_id, cursor):
    import json
    if not psicologo_id:
        return 24
    cursor.execute("SELECT configuracion_horarios_visual FROM usuarios WHERE id = ?", (psicologo_id,))
    row = cursor.fetchone()
    if row and row[0]:
        try:
            config = json.loads(row[0])
            return int(config.get('antelacion', 24))
        except:
            pass
    return 24

@app.route('/api/admin/availability', methods=['GET', 'POST'])
@login_required
def admin_availability():
    db = get_db()
    cursor = db.cursor()
    import json
    
    default_visual = {
        "duracion": 60,
        "receso": 15,
        "antelacion": 24,
        "alerta_confirmacion": 24,
        "alerta_recordatorio": 2,
        "alerta_cierre": 2,
        "limite_cancelacion_tipo": "horas",
        "limite_cancelacion_valor": 24,
        "perfiles": [
            {
                "id": "default_online",
                "nombre": "Horario Online",
                "modalidad": "Online",
                "dias": [
                    {"dia": 1, "nombre": "Lunes", "activo": True, "rangos": [{"inicio": "12:00", "fin": "16:00"}, {"inicio": "18:00", "fin": "22:00"}]},
                    {"dia": 2, "nombre": "Martes", "activo": True, "rangos": [{"inicio": "18:00", "fin": "22:00"}]},
                    {"dia": 3, "nombre": "Miércoles", "activo": False, "rangos": []},
                    {"dia": 4, "nombre": "Jueves", "activo": False, "rangos": []},
                    {"dia": 5, "nombre": "Viernes", "activo": False, "rangos": []},
                    {"dia": 6, "nombre": "Sábado", "activo": False, "rangos": []},
                    {"dia": 0, "nombre": "Domingo", "activo": False, "rangos": []}
                ]
            },
            {
                "id": "default_presencial",
                "nombre": "Horario Presencial",
                "modalidad": "Presencial",
                "dias": [
                    {"dia": 1, "nombre": "Lunes", "activo": False, "rangos": []},
                    {"dia": 2, "nombre": "Martes", "activo": False, "rangos": []},
                    {"dia": 3, "nombre": "Miércoles", "activo": True, "rangos": [{"inicio": "08:00", "fin": "12:00"}]},
                    {"dia": 4, "nombre": "Jueves", "activo": True, "rangos": [{"inicio": "08:00", "fin": "12:00"}]},
                    {"dia": 5, "nombre": "Viernes", "activo": True, "rangos": [{"inicio": "08:00", "fin": "12:00"}]},
                    {"dia": 6, "nombre": "Sábado", "activo": False, "rangos": []},
                    {"dia": 0, "nombre": "Domingo", "activo": False, "rangos": []}
                ]
            }
        ]
    }

    if request.method == 'GET':
        cursor.execute("SELECT configuracion_horarios_visual FROM usuarios WHERE id = ?", (session.get('user_id'),))
        u_row = cursor.fetchone()
        if u_row and u_row['configuracion_horarios_visual']:
            try:
                config = json.loads(u_row['configuracion_horarios_visual'])
                if isinstance(config, dict):
                    if 'perfiles' not in config or not isinstance(config['perfiles'], list) or len(config['perfiles']) == 0:
                        config['perfiles'] = default_visual['perfiles']
                    if 'antelacion' not in config: config['antelacion'] = 24
                    if 'alerta_confirmacion' not in config: config['alerta_confirmacion'] = 24
                    if 'alerta_recordatorio' not in config: config['alerta_recordatorio'] = 2
                    if 'alerta_cierre' not in config: config['alerta_cierre'] = 2
                    return jsonify(config)
            except:
                pass
        return jsonify(default_visual)
            
    elif request.method == 'POST':
        data = request.json
        duracion = int(data.get('duracion', 60))
        receso = int(data.get('receso', 15))
        perfiles = data.get('perfiles', [])
        
        from datetime import datetime, timedelta
        
        days_map = {d: {"dia": d, "nombre": "", "activo": False, "slots_dict": {}} for d in range(7)}
        
        days_names = {1: "Lunes", 2: "Martes", 3: "Miércoles", 4: "Jueves", 5: "Viernes", 6: "Sábado", 0: "Domingo"}
        for d_id, name in days_names.items():
            days_map[d_id]["nombre"] = name
            
        for perf in perfiles:
            modalidad = perf.get('modalidad', 'Online')
            dias_list = perf.get('dias', [])
            
            for d in dias_list:
                dia_id = int(d.get('dia'))
                activo = d.get('activo', False)
                rangos = d.get('rangos', [])
                
                if activo:
                    days_map[dia_id]["activo"] = True
                    slots_dict = days_map[dia_id]["slots_dict"]
                    
                    for r in rangos:
                        inicio_str = r.get('inicio')
                        fin_str = r.get('fin')
                        if inicio_str and fin_str:
                            try:
                                start_time = datetime.strptime(inicio_str, "%H:%M")
                                end_time = datetime.strptime(fin_str, "%H:%M")
                                
                                # Auto-corrección inteligente para bloques de tarde (ej. 02:00 a 06:00 -> 14:00 a 18:00)
                                if start_time.hour < 7 and end_time.hour <= 12 and start_time.hour < end_time.hour:
                                    start_time = start_time.replace(hour=start_time.hour + 12)
                                    if end_time.hour < 12:
                                        end_time = end_time.replace(hour=end_time.hour + 12)
                                
                                current = start_time
                                duration_td = timedelta(minutes=duracion)
                                recess_td = timedelta(minutes=receso)
                                
                                while current + duration_td <= end_time:
                                    hour_str = current.strftime("%H:%M")
                                    if hour_str not in slots_dict:
                                        slots_dict[hour_str] = set()
                                    slots_dict[hour_str].add(modalidad)
                                    current += duration_td + recess_td
                            except Exception as e:
                                pass
                                
        availability_flat = []
        for d_id in [1, 2, 3, 4, 5, 6, 0]:
            d_data = days_map[d_id]
            slots_list = []
            
            sorted_hours = sorted(d_data["slots_dict"].keys())
            for h in sorted_hours:
                slots_list.append({
                    "hora": h,
                    "modalidades": list(d_data["slots_dict"][h])
                })
                
            availability_flat.append({
                "dia": d_id,
                "nombre": d_data["nombre"],
                "activo": d_data["activo"],
                "slots": slots_list
            })
            
        try:
            cursor.execute("""
                UPDATE usuarios 
                SET configuracion_horarios_visual = ?, disponibilidad_horarios = ? 
                WHERE id = ?
            """, (json.dumps(data), json.dumps(availability_flat), session.get('user_id')))
            db.commit()
            return jsonify({'success': 'Perfiles de horario y bloques guardados con éxito.'})
        except Exception as e:
            return jsonify({'error': f'Error al guardar horarios: {str(e)}'}), 500

@app.route('/api/admin/profile-slug', methods=['GET', 'POST'])
@login_required
def admin_profile_slug():
    db = get_db()
    cursor = db.cursor()
    user_id = session['user_id']
    if request.method == 'GET':
        cursor.execute("SELECT id, nombres, apellidos, username, slug FROM usuarios WHERE id = ?", (user_id,))
        u = cursor.fetchone()
        if not u:
            return jsonify({'error': 'Usuario no encontrado.'}), 404
        
        current_slug = generate_default_slug_for_user(u)
        if not u['slug']:
            try:
                cursor.execute("UPDATE usuarios SET slug = ? WHERE id = ?", (current_slug, user_id))
                db.commit()
            except Exception:
                pass

        return jsonify({
            'id': u['id'],
            'username': u['username'],
            'slug': current_slug,
            'fast_booking_url': f"/agendar/{current_slug}",
            'registration_url': f"/registro/{current_slug}"
        })
    else:
        data = request.json or {}
        new_slug = str(data.get('slug', '')).strip().lower().replace(" ", "-")
        new_slug = re.sub(r'[^a-z0-9\.\-_]', '', new_slug)
        if not new_slug:
            return jsonify({'error': 'El identificador personalizado (slug) no puede estar vacío.'}), 400
        
        cursor.execute("SELECT id FROM usuarios WHERE (LOWER(slug) = ? OR LOWER(username) = ?) AND id != ?", (new_slug, new_slug, user_id))
        if cursor.fetchone():
            return jsonify({'error': 'El enlace personalizado ya está en uso por otro profesional.'}), 400
            
        cursor.execute("UPDATE usuarios SET slug = ? WHERE id = ?", (new_slug, user_id))
        db.commit()
        return jsonify({
            'success': 'Enlace personalizado actualizado con éxito.',
            'slug': new_slug,
            'fast_booking_url': f"/agendar/{new_slug}",
            'registration_url': f"/registro/{new_slug}"
        })

@app.route('/api/admin/rates', methods=['POST'])
@login_required
def admin_rates():
    data = request.json
    db = get_db()
    cursor = db.cursor()
    import json
    
    # Obtener configuración actual
    cursor.execute("SELECT configuracion_horarios_visual FROM usuarios WHERE id = ?", (session.get('user_id'),))
    u_row = cursor.fetchone()
    config = {}
    if u_row and u_row[0]:
        try:
            config = json.loads(u_row[0])
        except:
            pass
            
    config['tarifas'] = data.get('tarifas', {})
    config['paquetes'] = data.get('paquetes', {})
    
    try:
        cursor.execute("UPDATE usuarios SET configuracion_horarios_visual = ? WHERE id = ?", (json.dumps(config), session.get('user_id')))
        db.commit()
        return jsonify({'success': 'Tarifas y honorarios actualizados con éxito.'})
    except Exception as e:
        db.rollback()
        return jsonify({'error': f'Error al actualizar tarifas: {str(e)}'}), 500

# ==========================================
# GESTIÓN DE PACIENTES
# ==========================================

def get_psicologo_id_filter():
    """
    Retorna el ID del psicólogo para filtrar consultas.
    Si el rol es superadmin o admin, retorna None (sin filtro global).
    De lo contrario, retorna session['user_id'] (o 1 por defecto).
    """
    role = session.get('role')
    user_id = session.get('user_id')
    if role in ['admin', 'superadmin']:
        req_id = request.args.get('psicologo_id')
        if req_id and req_id.isdigit():
            return int(req_id)
        return None
    return user_id if user_id else 1

@app.route('/api/pacientes/buscar_cedula/<cedula>', methods=['GET'])
@login_required
def buscar_paciente_por_cedula(cedula):
    cedula_clean = cedula.strip()
    if not cedula_clean:
        return jsonify({'found': False}), 404
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT nombres, apellidos, cedula, pronombre, genero, edad, lugar_nacimiento, fecha_nacimiento,
               residencia_actual, con_quien_reside, nivel_academico, ocupacion, estado_civil, telefono, email, pais, ciudad
        FROM pacientes
        WHERE cedula = ?
        ORDER BY id DESC LIMIT 1
    """, (cedula_clean,))
    row = cursor.fetchone()
    if not row:
        return jsonify({'found': False}), 404
    return jsonify({
        'found': True,
        'paciente': dict(row)
    })

@app.route('/api/patients', methods=['GET'])
@login_required
def get_patients():
    search = request.args.get('search', '').strip()
    db = get_db()
    cursor = db.cursor()
    psic_id = get_psicologo_id_filter()
    
    if search:
        query = "%" + search + "%"
        if psic_id is not None:
            cursor.execute("""
                SELECT id, nombres, apellidos, cedula, edad, genero, residencia_actual, pais, ciudad 
                FROM pacientes 
                WHERE psicologo_id = ? AND (nombres LIKE ? OR apellidos LIKE ? OR cedula LIKE ?)
                ORDER BY nombres ASC, apellidos ASC
            """, (psic_id, query, query, query))
        else:
            cursor.execute("""
                SELECT id, nombres, apellidos, cedula, edad, genero, residencia_actual, pais, ciudad 
                FROM pacientes 
                WHERE nombres LIKE ? OR apellidos LIKE ? OR cedula LIKE ?
                ORDER BY nombres ASC, apellidos ASC
            """, (query, query, query))
    else:
        if psic_id is not None:
            cursor.execute("SELECT id, nombres, apellidos, cedula, edad, genero, residencia_actual, pais, ciudad FROM pacientes WHERE psicologo_id = ? ORDER BY nombres ASC, apellidos ASC", (psic_id,))
        else:
            cursor.execute("SELECT id, nombres, apellidos, cedula, edad, genero, residencia_actual, pais, ciudad FROM pacientes ORDER BY nombres ASC, apellidos ASC")
        
    patients = [dict(row) for row in cursor.fetchall()]
    return jsonify(patients)

@app.route('/api/patients/<int:patient_id>', methods=['GET'])
@login_required
def get_patient(patient_id):
    db = get_db()
    cursor = db.cursor()
    psic_id = get_psicologo_id_filter()
    if psic_id is not None:
        cursor.execute("SELECT * FROM pacientes WHERE id = ? AND psicologo_id = ?", (patient_id, psic_id))
    else:
        cursor.execute("SELECT * FROM pacientes WHERE id = ?", (patient_id,))
    row = cursor.fetchone()
    if row is None:
        return jsonify({'error': 'Paciente no encontrado.'}), 404
    p_dict = dict(row)
    for k in ['diagnostico', 'antecedentes_medicos_personales', 'antecedentes_psicologicos_personales', 'historia_clinica']:
        if k in p_dict and p_dict[k]:
            p_dict[k] = decrypt_clinical_text(p_dict[k])
    return jsonify(p_dict)

@app.route('/api/patients', methods=['POST'])
@login_required
def create_patient():
    data = request.json
    db = get_db()
    cursor = db.cursor()
    
    # Validaciones obligatorias
    nombres = data.get('nombres')
    apellidos = data.get('apellidos')
    cedula = data.get('cedula')
    if not nombres or not apellidos or not cedula:
        return jsonify({'error': 'Nombres, Apellidos y Cédula son campos obligatorios.'}), 400
        
    # Verificar cédula única para el psicólogo actual
    psic_id = session.get('user_id', 1)
    cursor.execute("SELECT id FROM pacientes WHERE cedula = ? AND psicologo_id = ?", (cedula, psic_id))
    if cursor.fetchone() is not None:
        return jsonify({'error': f'Ya tienes un paciente registrado con la cédula {cedula}.'}), 400

    costo_personalizado = data.get('costo_personalizado')
    if costo_personalizado == '' or costo_personalizado is None:
        costo_personalizado = None
    else:
        try:
            costo_personalizado = float(costo_personalizado)
        except:
            costo_personalizado = None
    moneda_personalizada = data.get('moneda_personalizada', 'USD') or 'USD'
        
    costo_paquete_personalizado = data.get('costo_paquete_personalizado')
    if costo_paquete_personalizado == '' or costo_paquete_personalizado is None:
        costo_paquete_personalizado = None
    else:
        try:
            costo_paquete_personalizado = float(costo_paquete_personalizado)
        except:
            costo_paquete_personalizado = None

    sesiones_paquete_personalizado = data.get('sesiones_paquete_personalizado')
    if sesiones_paquete_personalizado == '' or sesiones_paquete_personalizado is None:
        sesiones_paquete_personalizado = None
    else:
        try:
            sesiones_paquete_personalizado = int(sesiones_paquete_personalizado)
        except:
            sesiones_paquete_personalizado = None

    try:
        psic_id = session.get('user_id', 1)
        base_username = cedula
        cursor.execute("SELECT id FROM pacientes WHERE username = ?", (base_username,))
        if cursor.fetchone() is not None:
            base_username = f"{cedula}_{psic_id}"
        username = base_username
        password_hash = generate_password_hash(cedula)
        
        cursor.execute("""
            INSERT INTO pacientes (
                nombres, apellidos, cedula, pronombre, genero, edad, lugar_nacimiento, fecha_nacimiento,
                residencia_actual, pais, ciudad, con_quien_reside, nivel_academico, ocupacion, estado_civil,
                telefono, email,
                antecedentes_medicos_familiares, antecedentes_medicos_personales,
                antecedentes_psicologicos_familiares, antecedentes_psicologicos_personales,
                asistencia_previa_psicologo, motivo_consulta, expectativas, farmacologia,
                contacto_emergencia_nombre, contacto_emergencia_parentesco, diagnostico,
                username, password_hash, psicologo_id, costo_personalizado, moneda_personalizada,
                costo_paquete_personalizado, sesiones_paquete_personalizado
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            nombres, apellidos, cedula, data.get('pronombre'), data.get('genero'), data.get('edad'),
            data.get('lugar_nacimiento'), data.get('fecha_nacimiento'), data.get('residencia_actual'),
            data.get('pais'), data.get('ciudad'),
            data.get('con_quien_reside'), data.get('nivel_academico'), data.get('ocupacion'), data.get('estado_civil'),
            data.get('telefono'), data.get('email'),
            data.get('antecedentes_medicos_familiares'), data.get('antecedentes_medicos_personales'),
            data.get('antecedentes_psicologicos_familiares'), data.get('antecedentes_psicologicos_personales'),
            data.get('asistencia_previa_psicologo'), data.get('motivo_consulta'), data.get('expectativas'),
            data.get('farmacologia'), data.get('contacto_emergencia_nombre'), data.get('contacto_emergencia_parentesco'),
            data.get('diagnostico'), username, password_hash, session.get('user_id'), costo_personalizado, moneda_personalizada,
            costo_paquete_personalizado, sesiones_paquete_personalizado
        ))
        db.commit()
        patient_id = cursor.lastrowid
        
        # Sincronización en segundo plano con Firebase
        import threading
        threading.Thread(target=sync_patient_to_firebase, args=(patient_id,)).start()
        
        return jsonify({'success': 'Paciente registrado con éxito.', 'id': patient_id})
    except Exception as e:
        return jsonify({'error': f'Error al registrar paciente: {str(e)}'}), 500

@app.route('/api/patients/<int:patient_id>', methods=['PUT'])
@login_required
def update_patient(patient_id):
    data = request.json
    db = get_db()
    cursor = db.cursor()
    
    nombres = data.get('nombres')
    apellidos = data.get('apellidos')
    cedula = data.get('cedula')
    if not nombres or not apellidos or not cedula:
        return jsonify({'error': 'Nombres, Apellidos y Cédula son obligatorios.'}), 400
        
    # Verificar cédula única para el psicólogo actual omitiendo al paciente actual
    psic_id = session.get('user_id', 1)
    cursor.execute("SELECT id FROM pacientes WHERE cedula = ? AND psicologo_id = ? AND id != ?", (cedula, psic_id, patient_id))
    if cursor.fetchone() is not None:
        return jsonify({'error': f'Ya tienes otro paciente registrado con la cédula {cedula}.'}), 400
        
    costo_personalizado = data.get('costo_personalizado')
    if costo_personalizado == '' or costo_personalizado is None:
        costo_personalizado = None
    else:
        try:
            costo_personalizado = float(costo_personalizado)
        except:
            costo_personalizado = None
    moneda_personalizada = data.get('moneda_personalizada', 'USD') or 'USD'

    costo_paquete_personalizado = data.get('costo_paquete_personalizado')
    if costo_paquete_personalizado == '' or costo_paquete_personalizado is None:
        costo_paquete_personalizado = None
    else:
        try:
            costo_paquete_personalizado = float(costo_paquete_personalizado)
        except:
            costo_paquete_personalizado = None

    sesiones_paquete_personalizado = data.get('sesiones_paquete_personalizado')
    if sesiones_paquete_personalizado == '' or sesiones_paquete_personalizado is None:
        sesiones_paquete_personalizado = None
    else:
        try:
            sesiones_paquete_personalizado = int(sesiones_paquete_personalizado)
        except:
            sesiones_paquete_personalizado = None

    try:
        cursor.execute("""
            UPDATE pacientes SET 
                nombres = ?, apellidos = ?, cedula = ?, pronombre = ?, genero = ?, edad = ?,
                lugar_nacimiento = ?, fecha_nacimiento = ?, residencia_actual = ?, pais = ?, ciudad = ?,
                con_quien_reside = ?, nivel_academico = ?, ocupacion = ?, estado_civil = ?,
                telefono = ?, email = ?,
                antecedentes_medicos_familiares = ?, antecedentes_medicos_personales = ?,
                antecedentes_psicologicos_familiares = ?, antecedentes_psicologicos_personales = ?,
                asistencia_previa_psicologo = ?, motivo_consulta = ?, expectativas = ?, farmacologia = ?,
                contacto_emergencia_nombre = ?, contacto_emergencia_parentesco = ?, diagnostico = ?,
                costo_personalizado = ?, moneda_personalizada = ?,
                costo_paquete_personalizado = ?, sesiones_paquete_personalizado = ?
            WHERE id = ?
        """, (
            nombres, apellidos, cedula, data.get('pronombre'), data.get('genero'), data.get('edad'),
            data.get('lugar_nacimiento'), data.get('fecha_nacimiento'), data.get('residencia_actual'),
            data.get('pais'), data.get('ciudad'),
            data.get('con_quien_reside'), data.get('nivel_academico'), data.get('ocupacion'), data.get('estado_civil'),
            data.get('telefono'), data.get('email'),
            data.get('antecedentes_medicos_familiares'), data.get('antecedentes_medicos_personales'),
            data.get('antecedentes_psicologicos_familiares'), data.get('antecedentes_psicologicos_personales'),
            data.get('asistencia_previa_psicologo'), data.get('motivo_consulta'), data.get('expectativas'),
            data.get('farmacologia'), data.get('contacto_emergencia_nombre'), data.get('contacto_emergencia_parentesco'),
            data.get('diagnostico'), costo_personalizado, moneda_personalizada,
            costo_paquete_personalizado, sesiones_paquete_personalizado, patient_id
        ))
        db.commit()
        
        # Sincronización en segundo plano con Firebase
        import threading
        threading.Thread(target=sync_patient_to_firebase, args=(patient_id,)).start()
        
        return jsonify({'success': 'Expediente actualizado con éxito.'})
    except Exception as e:
        return jsonify({'error': f'Error al actualizar expediente: {str(e)}'}), 500

@app.route('/api/patients/<int:patient_id>', methods=['DELETE'])
@login_required
def delete_patient(patient_id):
    db = get_db()
    cursor = db.cursor()
    psic_id = get_psicologo_id_filter()
    if psic_id is not None:
        cursor.execute("SELECT id FROM pacientes WHERE id = ? AND psicologo_id = ?", (patient_id, psic_id))
        if not cursor.fetchone():
            return jsonify({'error': 'No tienes permisos para eliminar este paciente.'}), 403
    try:
        cursor.execute("DELETE FROM agenda_finanzas WHERE paciente_id = ?", (patient_id,))
        cursor.execute("DELETE FROM sesiones WHERE paciente_id = ?", (patient_id,))
        cursor.execute("DELETE FROM pizarra_terapeutica WHERE paciente_id = ?", (patient_id,))
        cursor.execute("DELETE FROM pagos_notificados WHERE paciente_id = ?", (patient_id,))
        cursor.execute("DELETE FROM pacientes WHERE id = ?", (patient_id,))
        db.commit()
        return jsonify({'success': 'Paciente y todos sus registros clínicos/financieros fueron eliminados con éxito.'})
    except Exception as e:
        return jsonify({'error': f'Error al eliminar paciente: {str(e)}'}), 500

# ==========================================
# FICHA RESUMEN DEL CONSULTANTE
# ==========================================

@app.route('/api/patients/<int:patient_id>/summary', methods=['GET'])
@login_required
def get_patient_summary(patient_id):
    db = get_db()
    cursor = db.cursor()
    psic_id = get_psicologo_id_filter()
    
    # 1. Datos personales básicos
    if psic_id is not None:
        cursor.execute("""
            SELECT id, nombres, apellidos, cedula, edad, genero, residencia_actual, pais, ciudad, diagnostico,
                   fecha_nacimiento, con_quien_reside, antecedentes_medicos_personales, antecedentes_psicologicos_personales
            FROM pacientes WHERE id = ? AND psicologo_id = ?
        """, (patient_id, psic_id))
    else:
        cursor.execute("""
            SELECT id, nombres, apellidos, cedula, edad, genero, residencia_actual, pais, ciudad, diagnostico,
                   fecha_nacimiento, con_quien_reside, antecedentes_medicos_personales, antecedentes_psicologicos_personales
            FROM pacientes WHERE id = ?
        """, (patient_id,))
    patient = cursor.fetchone()
    if not patient:
        return jsonify({'error': 'Paciente no encontrado'}), 404
        
    auto_settle_patient_debts(db, patient_id)
        
    # 2. Última sesión anotada
    cursor.execute("""
        SELECT fecha, modalidad, resumen, tareas_asignadas, anotaciones_proxima 
        FROM sesiones 
        WHERE paciente_id = ? 
        ORDER BY fecha DESC, id DESC LIMIT 1
    """, (patient_id,))
    last_session = cursor.fetchone()
    
    # 3. Datos financieros: Sesiones pagas, pendientes, saldo prepagado y desglose de deudas
    cursor.execute("""
        SELECT 
            SUM(CASE WHEN estado_pago IN ('Paga', 'Cancelada sin aviso - Paga') THEN cantidad_sesiones ELSE 0 END) as pagas,
            SUM(CASE WHEN estado_pago IN ('Pendiente', 'Cancelada sin aviso') THEN cantidad_sesiones ELSE 0 END) as pendientes,
            SUM(CASE WHEN estado_pago = 'Prepagada' AND control_uso = 'No consumida' THEN cantidad_sesiones ELSE 0 END) as prepagadas_no_consumidas,
            SUM(CASE WHEN estado_pago = 'Prepagada' AND control_uso = 'Consumida' THEN cantidad_sesiones ELSE 0 END) as prepagadas_consumidas
        FROM agenda_finanzas 
        WHERE paciente_id = ?
    """, (patient_id,))
    finance_stats = cursor.fetchone()
    
    cursor.execute("""
        SELECT moneda, SUM(monto) as total
        FROM agenda_finanzas
        WHERE paciente_id = ? AND estado_pago IN ('Pendiente', 'Cancelada sin aviso')
        GROUP BY moneda
    """, (patient_id,))
    deuda_monto_rows = cursor.fetchall()
    deuda_monto_str = ""
    for r in deuda_monto_rows:
        if r['total'] and r['total'] > 0:
            deuda_monto_str += f"{r['total']:.2f} {r['moneda']} | "
    if deuda_monto_str.endswith(' | '):
        deuda_monto_str = deuda_monto_str[:-3]
    if not deuda_monto_str:
        deuda_monto_str = "0.00 USD"

    cursor.execute("""
        SELECT id, fecha, hora, tipo_consulta, monto, moneda, estado_pago, referencia
        FROM agenda_finanzas
        WHERE paciente_id = ? AND estado_pago IN ('Pendiente', 'Cancelada sin aviso')
        ORDER BY fecha ASC
    """, (patient_id,))
    deudas_detalle = [dict(r) for r in cursor.fetchall()]
    
    # 4. Conteo de sesiones por estado para el paciente
    cursor.execute("""
        SELECT estado, COUNT(id) as cantidad
        FROM sesiones
        WHERE paciente_id = ?
        GROUP BY estado
    """, (patient_id,))
    session_counts_rows = cursor.fetchall()
    
    session_counts = {'Realizada': 0, 'Cancelada': 0, 'Reprogramada': 0}
    for row in session_counts_rows:
        estado_name = row['estado'] if row['estado'] in session_counts else 'Realizada'
        session_counts[estado_name] = row['cantidad']

    patient_dict = dict(patient)
    for k in ['diagnostico', 'antecedentes_medicos_personales', 'antecedentes_psicologicos_personales', 'historia_clinica']:
        if k in patient_dict and patient_dict[k]:
            patient_dict[k] = decrypt_clinical_text(patient_dict[k])
            
    last_session_dict = dict(last_session) if last_session else None
    if last_session_dict:
        for k in ['resumen', 'tareas_asignadas', 'anotaciones_proxima', 'recursos_entregados', 'compromisos_psicologo']:
            if k in last_session_dict and last_session_dict[k]:
                last_session_dict[k] = decrypt_clinical_text(last_session_dict[k])

    summary = {
        'patient': patient_dict,
        'last_session': last_session_dict,
        'finance': {
            'pagas': finance_stats['pagas'] or 0,
            'pendientes': finance_stats['pendientes'] or 0,
            'prepagadas_no_consumidas': finance_stats['prepagadas_no_consumidas'] or 0,
            'prepagadas_consumidas': finance_stats['prepagadas_consumidas'] or 0,
            'deuda_monto_str': deuda_monto_str,
            'deudas_detalle': deudas_detalle
        },
        'session_counts': session_counts
    }
    return jsonify(summary)

@app.route('/api/patients/<int:patient_id>/print', methods=['GET'])
@login_required
def print_patient_card(patient_id):
    db = get_db()
    cursor = db.cursor()
    
    # 1. Obtener datos del paciente
    cursor.execute("SELECT * FROM pacientes WHERE id = ?", (patient_id,))
    patient = cursor.fetchone()
    if not patient:
        return "Paciente no encontrado", 404
        
    # 2. Obtener sesiones en orden cronológico
    cursor.execute("""
        SELECT fecha, modalidad, resumen, test_aplicados 
        FROM sesiones 
        WHERE paciente_id = ? AND estado = 'Realizada'
        ORDER BY fecha ASC, id ASC
    """, (patient_id,))
    sessions = cursor.fetchall()
    
    html_template = """
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <title>Ficha Clínica - {{ patient.nombres }} {{ patient.apellidos }}</title>
        <style>
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                color: #333;
                line-height: 1.6;
                margin: 0;
                padding: 0;
                background-color: #fff;
            }
            .container {
                width: 100%;
                max-width: 800px;
                margin: 0 auto;
                padding: 20px;
            }
            .header {
                border-bottom: 2px solid #5d3a6f;
                padding-bottom: 15px;
                margin-bottom: 30px;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }
            .header h1 {
                margin: 0;
                color: #5d3a6f;
                font-size: 24px;
            }
            .section-title {
                color: #5d3a6f;
                border-bottom: 1px solid #ddd;
                padding-bottom: 5px;
                margin-top: 30px;
                margin-bottom: 15px;
                font-size: 18px;
                font-weight: 700;
            }
            .grid-2 {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 15px 30px;
                margin-bottom: 20px;
            }
            .info-item {
                font-size: 14px;
            }
            .info-item strong {
                color: #555;
                display: block;
                margin-bottom: 2px;
                font-size: 12px;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }
            .diagnostic-box {
                background-color: #f9f9f9;
                border-left: 4px solid #5d3a6f;
                padding: 15px;
                border-radius: 4px;
                font-style: italic;
                font-size: 14px;
                margin-bottom: 20px;
            }
            .session-card {
                border: 1px solid #eee;
                border-radius: 6px;
                padding: 15px;
                margin-bottom: 15px;
                page-break-inside: avoid;
            }
            .session-header {
                display: flex;
                justify-content: space-between;
                border-bottom: 1px dashed #eee;
                padding-bottom: 8px;
                margin-bottom: 10px;
            }
            .session-title-num {
                font-weight: 700;
                color: #5d3a6f;
            }
            .session-date {
                color: #666;
                font-size: 13px;
            }
            .session-body {
                font-size: 14px;
                margin-bottom: 10px;
            }
            .session-tests {
                background-color: #f4f0f6;
                padding: 8px 12px;
                border-radius: 4px;
                font-size: 13px;
                margin-top: 5px;
            }
            .no-print-btn {
                padding: 8px 16px;
                background-color: #5d3a6f;
                color: white;
                border: none;
                border-radius: 4px;
                cursor: pointer;
                font-weight: bold;
                font-size: 14px;
            }
            @media print {
                body {
                    background: white;
                    color: black;
                }
                .container {
                    width: 100%;
                    max-width: 100%;
                    padding: 0;
                }
                .no-print {
                    display: none;
                }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Ficha Clínica Individual</h1>
                <div class="no-print">
                    <button class="no-print-btn" onclick="window.print()">Imprimir Ficha / PDF</button>
                </div>
            </div>

            <div class="section-title">Datos Personales</div>
            <div class="grid-2">
                <div class="info-item"><strong>Nombre Completo</strong>{{ patient.nombres }} {{ patient.apellidos }}</div>
                <div class="info-item"><strong>Cédula de Identidad</strong>{{ patient.cedula }}</div>
                <div class="info-item"><strong>Edad</strong>{{ patient.edad or 'No especificado' }} años</div>
                <div class="info-item"><strong>Género</strong>{{ patient.genero or 'No especificado' }}</div>
                <div class="info-item"><strong>Fecha de Nacimiento</strong>{{ patient.fecha_nacimiento or 'No especificado' }}</div>
                <div class="info-item"><strong>Residencia Actual</strong>{{ patient.residencia_actual or 'No especificado' }}</div>
            </div>

            <div class="section-title">Impresión Diagnóstica</div>
            <div class="diagnostic-box">
                {{ patient.diagnostico or 'Sin impresión diagnóstica registrada en la historia clínica.' }}
            </div>

            <div class="section-title">Historial de Sesiones y Evolución</div>
            {% if sessions %}
                {% for s in sessions %}
                    <div class="session-card">
                        <div class="session-header">
                            <span class="session-title-num">Sesión #{{ loop.index }}</span>
                            <span class="session-date">{{ s.fecha }} ({{ s.modalidad }})</span>
                        </div>
                        <div class="session-body">
                            <strong>Temas Abordados:</strong>
                            <div style="margin-top: 5px; white-space: pre-wrap;">{{ s.resumen or 'No especificado' }}</div>
                        </div>
                        {% if s.test_aplicados %}
                            <div class="session-tests">
                                <strong>Pruebas Aplicadas:</strong> {{ s.test_aplicados }}
                            </div>
                        {% endif %}
                    </div>
                {% endfor %}
            {% else %}
                <p style="color: #666; font-style: italic;">No se han registrado sesiones para este consultante.</p>
            {% endif %}
        </div>
        <script>
            window.onload = function() {
                setTimeout(function() {
                    window.print();
                }, 500);
            }
        </script>
    </body>
    </html>
    """
    return render_template_string(html_template, patient=dict(patient), sessions=[dict(s) for s in sessions])


# ==========================================
# SEGUIMIENTO DE SESIÓN (EVOLUCIÓN)
# ==========================================

@app.route('/api/sessions', methods=['GET'])
@login_required
def get_sessions():
    patient_id = request.args.get('patient_id')
    db = get_db()
    cursor = db.cursor()
    psic_id = get_psicologo_id_filter()
    
    if patient_id:
        if psic_id is not None:
            cursor.execute("""
                SELECT s.* 
                FROM sesiones s 
                JOIN pacientes p ON s.paciente_id = p.id 
                WHERE s.paciente_id = ? AND p.psicologo_id = ? 
                ORDER BY s.fecha DESC, s.id DESC
            """, (patient_id, psic_id))
        else:
            cursor.execute("SELECT * FROM sesiones WHERE paciente_id = ? ORDER BY fecha DESC, id DESC", (patient_id,))
    else:
        if psic_id is not None:
            cursor.execute("""
                SELECT s.*, p.nombres, p.apellidos 
                FROM sesiones s 
                JOIN pacientes p ON s.paciente_id = p.id 
                WHERE p.psicologo_id = ?
                ORDER BY s.fecha DESC, s.id DESC
            """, (psic_id,))
        else:
            cursor.execute("""
                SELECT s.*, p.nombres, p.apellidos 
                FROM sesiones s 
                JOIN pacientes p ON s.paciente_id = p.id 
                ORDER BY s.fecha DESC, s.id DESC
            """)
        
    raw_sessions = [dict(row) for row in cursor.fetchall()]
    sessions = []
    for s in raw_sessions:
        s['resumen'] = decrypt_clinical_text(s.get('resumen'))
        s['resumen_paciente'] = decrypt_clinical_text(s.get('resumen_paciente'))
        s['anotaciones_proxima'] = decrypt_clinical_text(s.get('anotaciones_proxima'))
        s['compromisos_psicologo'] = decrypt_clinical_text(s.get('compromisos_psicologo'))
        s['diagnostico'] = decrypt_clinical_text(s.get('diagnostico'))
        s['test_aplicados'] = decrypt_clinical_text(s.get('test_aplicados'))
        sessions.append(s)
    return jsonify(sessions)

@app.route('/api/sessions', methods=['POST'])
@login_required
def create_session():
    data = request.json
    db = get_db()
    cursor = db.cursor()
    
    patient_id = data.get('paciente_id')
    agenda_id = data.get('agenda_id')
    fecha = data.get('fecha')
    modalidad = data.get('modalidad')
    estado = data.get('estado', 'Realizada') # 'Realizada', 'Cancelada con aviso', 'Cancelada sin aviso', 'Reprogramada'
    
    if not patient_id or not fecha or not modalidad:
        return jsonify({'error': 'Paciente, Fecha y Modalidad son obligatorios.'}), 400
        
    try:
        resumen_enc = encrypt_clinical_text(data.get('resumen'))
        resumen_paciente_enc = encrypt_clinical_text(data.get('resumen_paciente'))
        anot_prox_enc = encrypt_clinical_text(data.get('anotaciones_proxima'))
        comp_enc = encrypt_clinical_text(data.get('compromisos_psicologo'))
        diag_enc = encrypt_clinical_text(data.get('diagnostico'))
        tests_enc = encrypt_clinical_text(data.get('test_aplicados'))
        
        # Insertar evolución clínica
        cursor.execute("""
            INSERT INTO sesiones (
                paciente_id, agenda_id, fecha, modalidad, estado, resumen, resumen_paciente, tareas_asignadas, 
                recursos_entregados, anotaciones_proxima, compromisos_psicologo,
                diagnostico, test_aplicados, archivo_adjunto
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            patient_id, agenda_id, fecha, modalidad, estado, resumen_enc, resumen_paciente_enc, data.get('tareas_asignadas'),
            data.get('recursos_entregados'), anot_prox_enc, comp_enc,
            diag_enc, tests_enc, data.get('archivo_adjunto')
        ))
        session_id = cursor.lastrowid
        
        # Si no hay cita de agenda asociada, la creamos al vuelo para que queden guardados los datos de pago/deuda en finanzas!
        if not agenda_id:
            estado_pago = 'Paga' if modalidad == 'Uptaeb' else 'Agendada'
            metodo_pago = 'Exonerado' if modalidad == 'Uptaeb' else ''
            referencia = 'Exonerada / Registro histórico' if modalidad == 'Uptaeb' else ''
            
            cursor.execute("""
                INSERT INTO agenda_finanzas (
                    paciente_id, fecha, hora, tipo_consulta, monto, moneda, estado_pago,
                    control_uso, fecha_liquidacion, cantidad_sesiones, referencia, metodo_pago, fecha_pago
                ) VALUES (?, ?, '00:00', ?, 0.0, 'USD', ?, 'No consumida', ?, 1, ?, ?, ?)
            """, (patient_id, fecha, modalidad, estado_pago, fecha, referencia, metodo_pago, fecha))
            agenda_id = cursor.lastrowid
            cursor.execute("UPDATE sesiones SET agenda_id = ? WHERE id = ?", (agenda_id, session_id))
            
        # Si está vinculado a una cita de la agenda, liquidamos el pago correspondientemente
        if agenda_id:
            tipo_liquidacion = data.get('tipo_liquidacion')
            monto = float(data.get('monto', 0.0) or 0.0)
            moneda = data.get('moneda', 'USD')
            metodo_pago = data.get('metodo_pago')
            referencia = data.get('referencia')
            fecha_pago = data.get('fecha_pago')

            # Si monto no se especificó manualmente, obtener costo de consulta personalizado del paciente
            if monto <= 0.0 and tipo_liquidacion in ('Cobrar ahora', 'Dejar pendiente'):
                fee_val, fee_curr = get_appointment_fee(cursor, patient_id, None, modalidad)
                monto = fee_val
                if fee_curr:
                    moneda = fee_curr
            
            if estado in ('Cancelada con aviso', 'Reprogramada'):
                # No se cobra, queda como "Paga" con monto 0.0 para cerrarla
                cursor.execute("""
                    UPDATE agenda_finanzas 
                    SET estado_pago = 'Paga', monto = 0.0, moneda = ?, metodo_pago = 'Cancelada/Reprog', referencia = ?
                    WHERE id = ?
                """, (moneda, estado, agenda_id))
            else:
                # Se cobra (Realizada o Cancelada sin aviso)
                if tipo_liquidacion == 'Descontar prepago':
                    # Buscar el paquete disponible más antiguo
                    cursor.execute("""
                        SELECT id, cantidad_sesiones, control_uso 
                        FROM agenda_finanzas 
                        WHERE paciente_id = ? AND estado_pago = 'Prepagada' AND control_uso = 'No consumida'
                        ORDER BY fecha ASC, id ASC LIMIT 1
                    """, (patient_id,))
                    pkg = cursor.fetchone()
                    if not pkg:
                        db.rollback()
                        return jsonify({'error': 'El consultante no tiene sesiones prepagadas disponibles.'}), 400
                        
                    pkg_id = pkg['id']
                    pkg_cant = pkg['cantidad_sesiones']
                    if pkg_cant > 1:
                        cursor.execute("UPDATE agenda_finanzas SET cantidad_sesiones = ? WHERE id = ?", (pkg_cant - 1, pkg_id))
                    else:
                        cursor.execute("UPDATE agenda_finanzas SET control_uso = 'Consumida' WHERE id = ?", (pkg_id,))
                        
                    cursor.execute("""
                        UPDATE agenda_finanzas 
                        SET estado_pago = 'Paga', monto = 0.0, moneda = ?, metodo_pago = 'Descontado de Prepago', referencia = 'Prepago'
                        WHERE id = ?
                    """, (moneda, agenda_id))
                elif tipo_liquidacion == 'Vincular paquete fraccionado':
                    cursor.execute("""
                        UPDATE agenda_finanzas 
                        SET estado_pago = 'Paga', monto = 0.0, moneda = ?, metodo_pago = 'Paquete Fraccionado', referencia = 'Cubierto por Paquete Fraccionado'
                        WHERE id = ?
                    """, (moneda, agenda_id))
                elif tipo_liquidacion == 'Cobrar ahora':
                    cursor.execute("""
                        UPDATE agenda_finanzas 
                        SET estado_pago = 'Paga', monto = ?, moneda = ?, metodo_pago = ?, referencia = ?, fecha_pago = ?
                        WHERE id = ?
                    """, (monto, moneda, metodo_pago, referencia, fecha_pago, agenda_id))
                elif tipo_liquidacion == 'Exonerar':
                    cursor.execute("""
                        UPDATE agenda_finanzas 
                        SET estado_pago = 'Paga', monto = 0.0, moneda = ?, metodo_pago = 'Exonerado', referencia = 'Exonerada / Registro histórico', fecha_pago = ?
                        WHERE id = ?
                    """, (moneda, fecha_pago or fecha, agenda_id))
                else: # Dejar pendiente
                    cursor.execute("""
                        UPDATE agenda_finanzas 
                        SET estado_pago = 'Pendiente', monto = ?, moneda = ?, metodo_pago = NULL, referencia = NULL, fecha_pago = NULL
                        WHERE id = ?
                    """, (monto, moneda, agenda_id))
                    
        db.commit()
        
        # Sincronización en segundo plano con Firebase
        # Enviar notificación al paciente en Firebase
        from datetime import datetime
        firebase_payload = {
            "tipo": "clinico",
            "titulo": "Seguimiento Actualizado",
            "mensaje": "Tu terapeuta ha cargado el resumen y las tareas asignadas para tu próxima sesión.",
            "fecha": datetime.now().isoformat(),
            "leida": False
        }
        import requests
        try:
            requests.post(f"{FIREBASE_DB_URL}/pacientes/{patient_id}/notificaciones.json", json=firebase_payload)
        except Exception as fe:
            print("Error al notificar al paciente en Firebase:", fe)

        import threading
        threading.Thread(target=sync_patient_to_firebase, args=(patient_id,)).start()
        
        return jsonify({'success': 'Evolución de sesión registrada con éxito.'})
    except Exception as e:
        db.rollback()
        return jsonify({'error': f'Error al registrar sesión: {str(e)}'}), 500

@app.route('/api/sessions/<int:session_id>', methods=['GET', 'PUT'])
@login_required
def update_session_detail(session_id):
    db = get_db()
    cursor = db.cursor()
    
    if request.method == 'GET':
        cursor.execute("SELECT * FROM sesiones WHERE id = ?", (session_id,))
        ses = cursor.fetchone()
        if not ses:
            return jsonify({'error': 'Evolución no encontrada.'}), 404
        s_dict = dict(ses)
        s_dict['resumen'] = decrypt_clinical_text(s_dict.get('resumen'))
        s_dict['resumen_paciente'] = decrypt_clinical_text(s_dict.get('resumen_paciente'))
        s_dict['anotaciones_proxima'] = decrypt_clinical_text(s_dict.get('anotaciones_proxima'))
        s_dict['compromisos_psicologo'] = decrypt_clinical_text(s_dict.get('compromisos_psicologo'))
        s_dict['diagnostico'] = decrypt_clinical_text(s_dict.get('diagnostico'))
        s_dict['test_aplicados'] = decrypt_clinical_text(s_dict.get('test_aplicados'))
        return jsonify(s_dict)
        
    data = request.json
    try:
        cursor.execute("SELECT * FROM sesiones WHERE id = ?", (session_id,))
        ses = cursor.fetchone()
        if not ses:
            return jsonify({'error': 'Evolución no encontrada.'}), 404
            
        agenda_id = ses['agenda_id']
        estado = data.get('estado', ses['estado'])
        resumen = encrypt_clinical_text(data.get('resumen')) if 'resumen' in data else ses['resumen']
        resumen_paciente = encrypt_clinical_text(data.get('resumen_paciente')) if 'resumen_paciente' in data else ses['resumen_paciente']
        tareas_asignadas = data.get('tareas_asignadas') if 'tareas_asignadas' in data else ses['tareas_asignadas']
        recursos_entregados = data.get('recursos_entregados') if 'recursos_entregados' in data else ses['recursos_entregados']
        anotaciones_proxima = encrypt_clinical_text(data.get('anotaciones_proxima')) if 'anotaciones_proxima' in data else ses['anotaciones_proxima']
        compromisos_psicologo = encrypt_clinical_text(data.get('compromisos_psicologo')) if 'compromisos_psicologo' in data else ses['compromisos_psicologo']
        diagnostico = encrypt_clinical_text(data.get('diagnostico')) if 'diagnostico' in data else ses['diagnostico']
        test_aplicados = encrypt_clinical_text(data.get('test_aplicados')) if 'test_aplicados' in data else ses['test_aplicados']
        archivo_adjunto = data.get('archivo_adjunto') if 'archivo_adjunto' in data else ses['archivo_adjunto']
        
        modalidad = data.get('modalidad', ses['modalidad'])
        fecha = data.get('fecha', ses['fecha'])
        patient_id = data.get('paciente_id', ses['paciente_id'])
        
        cursor.execute("""
            UPDATE sesiones 
            SET estado = ?, resumen = ?, resumen_paciente = ?, tareas_asignadas = ?, recursos_entregados = ?, anotaciones_proxima = ?, compromisos_psicologo = ?,
                diagnostico = ?, test_aplicados = ?, archivo_adjunto = ?, modalidad = ?, fecha = ?, paciente_id = ?
            WHERE id = ?
        """, (estado, resumen, resumen_paciente, tareas_asignadas, recursos_entregados, anotaciones_proxima, compromisos_psicologo, diagnostico, test_aplicados, archivo_adjunto, modalidad, fecha, patient_id, session_id))
        
        # Si no tiene agenda_id asociado, la creamos al vuelo
        if not agenda_id:
            estado_pago = 'Paga' if modalidad == 'Uptaeb' else 'Agendada'
            metodo_pago = 'Exonerado' if modalidad == 'Uptaeb' else ''
            referencia = 'Exonerada / Registro histórico' if modalidad == 'Uptaeb' else ''
            
            cursor.execute("""
                INSERT INTO agenda_finanzas (
                    paciente_id, fecha, hora, tipo_consulta, monto, moneda, estado_pago,
                    control_uso, fecha_liquidacion, cantidad_sesiones, referencia, metodo_pago, fecha_pago
                ) VALUES (?, ?, '00:00', ?, 0.0, 'USD', ?, 'No consumida', ?, 1, ?, ?, ?)
            """, (patient_id, fecha, modalidad, estado_pago, fecha, referencia, metodo_pago, fecha))
            agenda_id = cursor.lastrowid
            cursor.execute("UPDATE sesiones SET agenda_id = ? WHERE id = ?", (agenda_id, session_id))
        else:
            # Propagar cambios de consultante, modalidad y fecha al evento financiero existente
            cursor.execute("""
                UPDATE agenda_finanzas
                SET paciente_id = ?, fecha = ?, tipo_consulta = ?
                WHERE id = ?
            """, (patient_id, fecha, modalidad, agenda_id))
            
        # Si tiene una cita vinculada, actualizamos también el estado financiero si cambió
        if agenda_id and 'tipo_liquidacion' in data:
            tipo_liquidacion = data.get('tipo_liquidacion')
            monto = float(data.get('monto', 0.0) or 0.0)
            moneda = data.get('moneda', 'USD')
            metodo_pago = data.get('metodo_pago')
            referencia = data.get('referencia')
            fecha_pago = data.get('fecha_pago')
            
            cursor.execute("SELECT estado_pago, metodo_pago, paciente_id FROM agenda_finanzas WHERE id = ?", (agenda_id,))
            appointment = cursor.fetchone()
            was_prepay = (appointment['estado_pago'] == 'Paga' and appointment['metodo_pago'] == 'Descontado de Prepago')
            
            # Rollback del prepago anterior si cambia de tipo
            if was_prepay and tipo_liquidacion != 'Descontar prepago':
                cursor.execute("""
                    SELECT id, cantidad_sesiones, control_uso 
                    FROM agenda_finanzas 
                    WHERE paciente_id = ? AND estado_pago = 'Prepagada' AND control_uso = 'Consumida'
                    ORDER BY fecha DESC, id DESC LIMIT 1
                """, (ses['paciente_id'],))
                pkg = cursor.fetchone()
                if pkg:
                    cursor.execute("UPDATE agenda_finanzas SET control_uso = 'No consumida' WHERE id = ?", (pkg['id'],))
                else:
                    cursor.execute("""
                        SELECT id, cantidad_sesiones 
                        FROM agenda_finanzas 
                        WHERE paciente_id = ? AND estado_pago = 'Prepagada' AND control_uso = 'No consumida'
                        ORDER BY fecha DESC, id DESC LIMIT 1
                    """, (ses['paciente_id'],))
                    pkg2 = cursor.fetchone()
                    if pkg2:
                        cursor.execute("UPDATE agenda_finanzas SET cantidad_sesiones = cantidad_sesiones + 1 WHERE id = ?", (pkg2['id'],))

            # Aplicar nueva liquidación
            if estado in ('Cancelada con aviso', 'Reprogramada'):
                cursor.execute("""
                    UPDATE agenda_finanzas 
                    SET estado_pago = 'Paga', monto = 0.0, moneda = ?, metodo_pago = 'Cancelada/Reprog', referencia = ?
                    WHERE id = ?
                """, (moneda, estado, agenda_id))
            else:
                if tipo_liquidacion == 'Descontar prepago':
                    if not was_prepay:
                        cursor.execute("""
                            SELECT id, cantidad_sesiones, control_uso 
                            FROM agenda_finanzas 
                            WHERE paciente_id = ? AND estado_pago = 'Prepagada' AND control_uso = 'No consumida'
                            ORDER BY fecha ASC, id ASC LIMIT 1
                        """, (ses['paciente_id'],))
                        pkg = cursor.fetchone()
                        if not pkg:
                            db.rollback()
                            return jsonify({'error': 'El consultante no tiene sesiones prepagadas disponibles.'}), 400
                        pkg_id = pkg['id']
                        pkg_cant = pkg['cantidad_sesiones']
                        if pkg_cant > 1:
                            cursor.execute("UPDATE agenda_finanzas SET cantidad_sesiones = ? WHERE id = ?", (pkg_cant - 1, pkg_id))
                        else:
                            cursor.execute("UPDATE agenda_finanzas SET control_uso = 'Consumida' WHERE id = ?", (pkg_id,))
                    
                    cursor.execute("""
                        UPDATE agenda_finanzas 
                        SET estado_pago = 'Paga', monto = 0.0, moneda = ?, metodo_pago = 'Descontado de Prepago', referencia = 'Prepago'
                        WHERE id = ?
                    """, (moneda, agenda_id))
                elif tipo_liquidacion == 'Vincular paquete fraccionado':
                    cursor.execute("""
                        UPDATE agenda_finanzas 
                        SET estado_pago = 'Paga', monto = 0.0, moneda = ?, metodo_pago = 'Paquete Fraccionado', referencia = 'Cubierto por Paquete Fraccionado'
                        WHERE id = ?
                    """, (moneda, agenda_id))
                elif tipo_liquidacion == 'Cobrar ahora':
                    cursor.execute("""
                        UPDATE agenda_finanzas 
                        SET estado_pago = 'Paga', monto = ?, moneda = ?, metodo_pago = ?, referencia = ?, fecha_pago = ?
                        WHERE id = ?
                    """, (monto, moneda, metodo_pago, referencia, fecha_pago, agenda_id))
                elif tipo_liquidacion == 'Exonerar':
                    cursor.execute("""
                        UPDATE agenda_finanzas 
                        SET estado_pago = 'Paga', monto = 0.0, moneda = ?, metodo_pago = 'Exonerado', referencia = 'Exonerada / Registro histórico', fecha_pago = ?
                        WHERE id = ?
                    """, (moneda, fecha_pago or ses['fecha'], agenda_id))
                else: # Dejar pendiente
                    cursor.execute("""
                        UPDATE agenda_finanzas 
                        SET estado_pago = 'Pendiente', monto = ?, moneda = ?, metodo_pago = NULL, referencia = NULL, fecha_pago = NULL
                        WHERE id = ?
                    """, (monto, moneda, agenda_id))
                    
        db.commit()
        
        # Sincronización en segundo plano con Firebase
        # Enviar notificación al paciente en Firebase
        from datetime import datetime
        firebase_payload = {
            "tipo": "clinico",
            "titulo": "Seguimiento Actualizado",
            "mensaje": "Tu terapeuta ha actualizado el resumen o las tareas de tu sesión.",
            "fecha": datetime.now().isoformat(),
            "leida": False
        }
        import requests
        try:
            requests.post(f"{FIREBASE_DB_URL}/pacientes/{patient_id}/notificaciones.json", json=firebase_payload)
        except Exception as fe:
            print("Error al notificar actualización al paciente en Firebase:", fe)

        import threading
        threading.Thread(target=sync_patient_to_firebase, args=(patient_id,)).start()
        
        return jsonify({'success': 'Evolución actualizada con éxito.'})
    except Exception as e:
        db.rollback()
        return jsonify({'error': f'Error al actualizar evolución: {str(e)}'}), 500

@app.route('/api/sessions/<int:session_id>', methods=['DELETE'])
@login_required
def delete_session_detail(session_id):
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("SELECT * FROM sesiones WHERE id = ?", (session_id,))
        ses = cursor.fetchone()
        if not ses:
            return jsonify({'error': 'Evolución no encontrada.'}), 404
            
        agenda_id = ses['agenda_id']
        patient_id = ses['paciente_id']
        
        # Rollback del prepago si correspondía
        if agenda_id:
            cursor.execute("SELECT estado_pago, metodo_pago FROM agenda_finanzas WHERE id = ?", (agenda_id,))
            appointment = cursor.fetchone()
            if appointment and appointment['estado_pago'] == 'Paga' and appointment['metodo_pago'] == 'Descontado de Prepago':
                cursor.execute("""
                    SELECT id, cantidad_sesiones, control_uso 
                    FROM agenda_finanzas 
                    WHERE paciente_id = ? AND estado_pago = 'Prepagada' AND control_uso = 'Consumida'
                    ORDER BY fecha DESC, id DESC LIMIT 1
                """, (patient_id,))
                pkg = cursor.fetchone()
                if pkg:
                    cursor.execute("UPDATE agenda_finanzas SET control_uso = 'No consumida' WHERE id = ?", (pkg['id'],))
                else:
                    cursor.execute("""
                        SELECT id, cantidad_sesiones 
                        FROM agenda_finanzas 
                        WHERE paciente_id = ? AND estado_pago = 'Prepagada' AND control_uso = 'No consumida'
                        ORDER BY fecha DESC, id DESC LIMIT 1
                    """, (patient_id,))
                    pkg2 = cursor.fetchone()
                    if pkg2:
                        cursor.execute("UPDATE agenda_finanzas SET cantidad_sesiones = cantidad_sesiones + 1 WHERE id = ?", (pkg2['id'],))
            
            # Restaurar la cita a estado inicial 'Agendada'
            cursor.execute("""
                UPDATE agenda_finanzas 
                SET estado_pago = 'Agendada', monto = 0.0, metodo_pago = NULL, referencia = NULL, fecha_pago = NULL
                WHERE id = ?
            """, (agenda_id,))
            
        cursor.execute("DELETE FROM sesiones WHERE id = ?", (session_id,))
        db.commit()
        
        # Sincronización en segundo plano con Firebase
        try:
            import threading
            threading.Thread(target=sync_patient_to_firebase, args=(patient_id,)).start()
        except Exception as sync_ex:
            print("Error al sincronizar paciente tras eliminar sesión:", sync_ex)
        
        return jsonify({'success': 'Evolución eliminada y cita restaurada a agendada.'})
    except Exception as e:
        db.rollback()
        return jsonify({'error': f'Error al eliminar evolución: {str(e)}'}), 500

@app.route('/api/sessions/<int:session_id>/remove-attachment', methods=['POST'])
@login_required
def remove_session_attachment(session_id):
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("UPDATE sesiones SET archivo_adjunto = NULL WHERE id = ?", (session_id,))
        db.commit()
        return jsonify({'success': 'Archivo adjunto eliminado con éxito de la evolución.'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ==========================================
# CONTROL FINANCIERO Y BALANCE MENSUAL
# ==========================================

# ==========================================
# TARIFAS POR PAÍS Y TABLA RÁPIDA DE HONORARIOS
# ==========================================

@app.route('/api/admin/country-rates', methods=['GET'])
@login_required
def get_country_rates():
    try:
        db = get_db()
        cursor = db.cursor()
        psicologo_id = session.get('user_id')
        cursor.execute("""
            SELECT id, pais, modalidad, costo_individual, costo_paquete, sesiones_paquete, moneda
            FROM tarifas_pais WHERE psicologo_id = ? ORDER BY pais, modalidad
        """, (psicologo_id,))
        rates = [dict(r) for r in cursor.fetchall()]
        return jsonify(rates)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/country-rates', methods=['POST'])
@login_required
def save_country_rate():
    try:
        data = request.json or {}
        db = get_db()
        cursor = db.cursor()
        psicologo_id = session.get('user_id')
        pais = data.get('pais', '').strip()
        modalidad = data.get('modalidad', '').strip()
        costo_individual = data.get('costo_individual')
        costo_paquete = data.get('costo_paquete')
        sesiones_paquete = data.get('sesiones_paquete')
        moneda = data.get('moneda', 'USD').strip()
        
        if not pais or not modalidad or costo_individual is None:
            return jsonify({'error': 'País, modalidad y costo individual son requeridos.'}), 400
        
        cursor.execute("""
            INSERT INTO tarifas_pais (psicologo_id, pais, modalidad, costo_individual, costo_paquete, sesiones_paquete, moneda)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(psicologo_id, pais, modalidad) DO UPDATE SET
                costo_individual = excluded.costo_individual,
                costo_paquete = excluded.costo_paquete,
                sesiones_paquete = excluded.sesiones_paquete,
                moneda = excluded.moneda
        """, (psicologo_id, pais, modalidad, costo_individual, costo_paquete, sesiones_paquete, moneda))
        db.commit()
        return jsonify({'success': 'Tarifa guardada con éxito.'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/country-rates/<int:rate_id>', methods=['DELETE'])
@login_required
def delete_country_rate(rate_id):
    try:
        db = get_db()
        cursor = db.cursor()
        psicologo_id = session.get('user_id')
        cursor.execute("DELETE FROM tarifas_pais WHERE id = ? AND psicologo_id = ?", (rate_id, psicologo_id))
        db.commit()
        return jsonify({'success': 'Tarifa eliminada.'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/patients/<int:patient_id>/rates', methods=['PUT'])
@login_required
def update_patient_rates_quick(patient_id):
    try:
        data = request.json or {}
        db = get_db()
        cursor = db.cursor()
        psicologo_id = session.get('user_id')
        
        # Verificar que el paciente pertenece a este psicólogo
        cursor.execute("SELECT id FROM pacientes WHERE id = ? AND psicologo_id = ?", (patient_id, psicologo_id))
        if not cursor.fetchone():
            return jsonify({'error': 'Paciente no encontrado o sin acceso.'}), 404
        
        costo_personalizado = data.get('costo_personalizado')
        moneda_personalizada = data.get('moneda_personalizada')
        costo_paquete_personalizado = data.get('costo_paquete_personalizado')
        sesiones_paquete_personalizado = data.get('sesiones_paquete_personalizado')
        
        # Convertir vacíos a None
        if costo_personalizado == '' or costo_personalizado is None:
            costo_personalizado = None
        if costo_paquete_personalizado == '' or costo_paquete_personalizado is None:
            costo_paquete_personalizado = None
        if sesiones_paquete_personalizado == '' or sesiones_paquete_personalizado is None:
            sesiones_paquete_personalizado = None
        
        cursor.execute("""
            UPDATE pacientes SET
                costo_personalizado = ?,
                moneda_personalizada = ?,
                costo_paquete_personalizado = ?,
                sesiones_paquete_personalizado = ?
            WHERE id = ?
        """, (costo_personalizado, moneda_personalizada, costo_paquete_personalizado, sesiones_paquete_personalizado, patient_id))
        db.commit()
        
        import threading
        threading.Thread(target=sync_patient_to_firebase, args=(patient_id,)).start()
        
        return jsonify({'success': 'Honorarios actualizados con éxito.'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/patients-rates-list', methods=['GET'])
@login_required
def get_patients_rates_list():
    """Obtener lista de todos los pacientes con sus honorarios para la tabla unificada."""
    try:
        db = get_db()
        cursor = db.cursor()
        psicologo_id = session.get('user_id')
        cursor.execute("""
            SELECT id, nombres, apellidos, pais, ciudad,
                   costo_personalizado, moneda_personalizada,
                   costo_paquete_personalizado, sesiones_paquete_personalizado
            FROM pacientes
            WHERE psicologo_id = ?
            ORDER BY apellidos ASC, nombres ASC
        """, (psicologo_id,))
        patients = [dict(p) for p in cursor.fetchall()]
        return jsonify(patients)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/finance/balance', methods=['GET'])
@login_required
def get_monthly_balance():
    now = datetime.datetime.now()
    month = request.args.get('month', now.strftime('%m'))
    year = request.args.get('year', now.strftime('%Y'))
    
    date_prefix = f"{year}-{month}%"
    db = get_db()
    cursor = db.cursor()
    psic_id = get_psicologo_id_filter()
    
    if psic_id is not None:
        cursor.execute("""
            SELECT af.moneda, af.tipo_consulta, SUM(af.monto) as total_monto
            FROM agenda_finanzas af
            JOIN pacientes p ON af.paciente_id = p.id
            WHERE (af.fecha LIKE ? OR af.fecha_liquidacion LIKE ?) 
              AND af.estado_pago IN ('Paga', 'Prepagada', 'Cancelada sin aviso - Paga')
              AND p.psicologo_id = ?
            GROUP BY af.moneda, af.tipo_consulta
        """, (date_prefix, date_prefix, psic_id))
        breakdown = [dict(row) for row in cursor.fetchall()]
        
        cursor.execute("""
            SELECT af.*, 
                   COALESCE(p.nombres, 'Consultante') as nombres, 
                   COALESCE(p.apellidos, '') as apellidos, 
                   p.cedula
            FROM agenda_finanzas af
            JOIN pacientes p ON af.paciente_id = p.id
            WHERE af.estado_pago IN ('Pendiente', 'Cancelada sin aviso')
              AND p.psicologo_id = ?
            ORDER BY af.fecha ASC
        """, (psic_id,))
        pending_list = [dict(row) for row in cursor.fetchall()]
        
        cursor.execute("""
            SELECT af.*, 
                   COALESCE(p.nombres, 'Consultante') as nombres, 
                   COALESCE(p.apellidos, '') as apellidos
            FROM agenda_finanzas af
            JOIN pacientes p ON af.paciente_id = p.id
            WHERE (af.fecha LIKE ? OR af.fecha_liquidacion LIKE ?) 
              AND af.estado_pago IN ('Paga', 'Prepagada', 'Cancelada sin aviso - Paga')
              AND p.psicologo_id = ?
            ORDER BY af.fecha DESC
        """, (date_prefix, date_prefix, psic_id))
        income_list = [dict(row) for row in cursor.fetchall()]
        
        cursor.execute("SELECT COUNT(id) FROM pacientes WHERE psicologo_id = ?", (psic_id,))
        total_pacientes = cursor.fetchone()[0] or 0
        
        cursor.execute("""
            SELECT SUM(af.cantidad_sesiones) 
            FROM agenda_finanzas af
            JOIN pacientes p ON af.paciente_id = p.id
            WHERE af.estado_pago IN ('Paga', 'Prepagada', 'Cancelada sin aviso - Paga') 
              AND (af.fecha LIKE ? OR af.fecha_liquidacion LIKE ?)
              AND p.psicologo_id = ?
        """, (date_prefix, date_prefix, psic_id))
        total_pagas = cursor.fetchone()[0] or 0
        
        cursor.execute("""
            SELECT SUM(af.cantidad_sesiones) 
            FROM agenda_finanzas af
            JOIN pacientes p ON af.paciente_id = p.id
            WHERE af.estado_pago IN ('Pendiente', 'Cancelada sin aviso')
              AND p.psicologo_id = ?
        """, (psic_id,))
        total_pendientes = cursor.fetchone()[0] or 0
        
        cursor.execute("""
            SELECT s.modalidad, s.estado, COUNT(s.id) as cantidad
            FROM sesiones s
            JOIN pacientes p ON s.paciente_id = p.id
            WHERE s.fecha LIKE ? AND p.psicologo_id = ?
            GROUP BY s.modalidad, s.estado
        """, (date_prefix, psic_id))
        session_stats = [dict(row) for row in cursor.fetchall()]
        
        cursor.execute("""
            SELECT s.modalidad, COUNT(s.id)
            FROM sesiones s
            JOIN pacientes p ON s.paciente_id = p.id
            WHERE s.fecha LIKE ? AND p.psicologo_id = ?
            GROUP BY s.modalidad
        """, (date_prefix, psic_id))
        modality_counts = {row[0]: row[1] for row in cursor.fetchall()}
    else:
        cursor.execute("""
            SELECT moneda, tipo_consulta, SUM(monto) as total_monto
            FROM agenda_finanzas
            WHERE (fecha LIKE ? OR fecha_liquidacion LIKE ?) AND estado_pago IN ('Paga', 'Prepagada', 'Cancelada sin aviso - Paga')
            GROUP BY moneda, tipo_consulta
        """, (date_prefix, date_prefix))
        breakdown = [dict(row) for row in cursor.fetchall()]
        
        cursor.execute("""
            SELECT af.*, 
                   COALESCE(p.nombres, 'Consultante') as nombres, 
                   COALESCE(p.apellidos, '') as apellidos, 
                   p.cedula
            FROM agenda_finanzas af
            LEFT JOIN pacientes p ON af.paciente_id = p.id
            WHERE af.estado_pago IN ('Pendiente', 'Cancelada sin aviso')
            ORDER BY af.fecha ASC
        """)
        pending_list = [dict(row) for row in cursor.fetchall()]
        
        cursor.execute("""
            SELECT af.*, 
                   COALESCE(p.nombres, 'Consultante') as nombres, 
                   COALESCE(p.apellidos, '') as apellidos
            FROM agenda_finanzas af
            LEFT JOIN pacientes p ON af.paciente_id = p.id
            WHERE (af.fecha LIKE ? OR af.fecha_liquidacion LIKE ?) AND af.estado_pago IN ('Paga', 'Prepagada', 'Cancelada sin aviso - Paga')
            ORDER BY af.fecha DESC
        """, (date_prefix, date_prefix))
        income_list = [dict(row) for row in cursor.fetchall()]
        
        cursor.execute("SELECT COUNT(id) FROM pacientes")
        total_pacientes = cursor.fetchone()[0] or 0
        
        cursor.execute("""
            SELECT SUM(cantidad_sesiones) 
            FROM agenda_finanzas 
            WHERE estado_pago IN ('Paga', 'Prepagada', 'Cancelada sin aviso - Paga') 
              AND (fecha LIKE ? OR fecha_liquidacion LIKE ?)
        """, (date_prefix, date_prefix))
        total_pagas = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT SUM(cantidad_sesiones) FROM agenda_finanzas WHERE estado_pago IN ('Pendiente', 'Cancelada sin aviso')")
        total_pendientes = cursor.fetchone()[0] or 0
        
        cursor.execute("""
            SELECT modalidad, estado, COUNT(id) as cantidad
            FROM sesiones
            WHERE fecha LIKE ?
            GROUP BY modalidad, estado
        """, (date_prefix,))
        session_stats = [dict(row) for row in cursor.fetchall()]
        
        cursor.execute("""
            SELECT modalidad, COUNT(id)
            FROM sesiones
            WHERE fecha LIKE ?
            GROUP BY modalidad
        """, (date_prefix,))
        modality_counts = {row[0]: row[1] for row in cursor.fetchall()}
    
    total_online = modality_counts.get('Online', 0)
    total_presencial = modality_counts.get('Presencial', 0)
    total_uptaeb = modality_counts.get('Uptaeb', 0)

    return jsonify({
        'breakdown': breakdown,
        'pending_list': pending_list,
        'income_list': income_list,
        'session_stats': session_stats,
        'stats': {
            'total_pacientes': total_pacientes,
            'total_pagas': total_pagas,
            'total_pendientes': total_pendientes,
            'month_online': total_online,
            'month_presencial': total_presencial,
            'month_uptaeb': total_uptaeb
        }
    })

@app.route('/api/finance/transactions', methods=['POST'])
@login_required
def add_transaction():
    data = request.json
    db = get_db()
    cursor = db.cursor()
    
    paciente_id = data.get('paciente_id')
    fecha = data.get('fecha')
    hora = data.get('hora')
    tipo_consulta = data.get('tipo_consulta') # 'Presencial', 'Online'
    monto = data.get('monto', 0.0)
    moneda = data.get('moneda') # 'USD', 'EUR', 'BSD'
    estado_pago = data.get('estado_pago') # 'Paga', 'Pendiente', 'Prepagada'
    control_uso = data.get('control_uso', 'Consumida') # 'Consumida', 'No consumida'
    fecha_liquidacion = data.get('fecha_liquidacion')
    
    cantidad_sesiones = int(data.get('cantidad_sesiones', 1) or 1)
    referencia = data.get('referencia')
    metodo_pago = data.get('metodo_pago')
    fecha_pago = data.get('fecha_pago')
    
    if (estado_pago == 'Prepagada' or 'paquete' in (tipo_consulta or '').lower()) and cantidad_sesiones <= 1:
        cursor.execute("SELECT costo_paquete_personalizado, sesiones_paquete_personalizado FROM pacientes WHERE id = ?", (paciente_id,))
        pac = cursor.fetchone()
        if pac and pac['sesiones_paquete_personalizado']:
            cantidad_sesiones = int(pac['sesiones_paquete_personalizado'])
    
    if not paciente_id or not fecha or not tipo_consulta or not moneda or not estado_pago:
        return jsonify({'error': 'Faltan campos requeridos para la transacción.'}), 400
        
    try:
        cursor.execute("""
            INSERT INTO agenda_finanzas (
                paciente_id, fecha, hora, tipo_consulta, monto, moneda, 
                estado_pago, control_uso, fecha_liquidacion, cantidad_sesiones,
                referencia, metodo_pago, fecha_pago
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            paciente_id, fecha, hora, tipo_consulta, monto, moneda,
            estado_pago, control_uso, fecha_liquidacion, cantidad_sesiones,
            referencia, metodo_pago, fecha_pago
        ))
        db.commit()
        auto_settle_patient_debts(db, paciente_id)
        
        # Sincronización en segundo plano con Firebase
        import threading
        threading.Thread(target=sync_patient_to_firebase, args=(paciente_id,)).start()
        
        return jsonify({'success': 'Transacción agregada con éxito.'})
    except Exception as e:
        return jsonify({'error': f'Error al agregar transacción: {str(e)}'}), 500

@app.route('/api/finance/export-csv', methods=['GET'])
@login_required
def export_finance_csv():
    try:
        import io
        import csv
        from flask import Response
        
        month = request.args.get('month')
        year = request.args.get('year')
        
        if not month or not year:
            now = datetime.now()
            month = f"{now.month:02d}"
            year = str(now.year)
        else:
            month = f"{int(month):02d}"
            year = str(year)
            
        date_prefix = f"{year}-{month}%"
        
        db = get_db()
        cursor = db.cursor()
        
        cursor.execute("""
            SELECT af.id, af.fecha, af.hora, p.nombres, p.apellidos, p.cedula,
                   af.tipo_consulta, af.monto, af.moneda, af.estado_pago,
                   af.control_uso, af.metodo_pago, af.referencia, af.fecha_liquidacion
            FROM agenda_finanzas af
            LEFT JOIN pacientes p ON af.paciente_id = p.id
            WHERE af.fecha LIKE ? OR af.fecha_liquidacion LIKE ?
            ORDER BY af.fecha DESC, af.hora DESC
        """, (date_prefix, date_prefix))
        
        rows = cursor.fetchall()
        
        output = io.StringIO()
        writer = csv.writer(output, delimiter=';')
        
        writer.writerow(['ID', 'Fecha Cita', 'Hora Cita', 'Consultante', 'Cedula', 'Modalidad', 'Monto', 'Moneda', 'Estado de Pago', 'Control Uso', 'Metodo Pago', 'Referencia', 'Fecha Liquidacion'])
        
        for r in rows:
            nombre_paciente = f"{r['nombres']} {r['apellidos']}" if r['nombres'] else "Consultante Desconocido"
            writer.writerow([
                r['id'],
                r['fecha'] or '',
                r['hora'] or '',
                nombre_paciente,
                r['cedula'] or '',
                r['tipo_consulta'] or '',
                f"{float(r['monto'] or 0):.2f}",
                r['moneda'] or 'USD',
                r['estado_pago'] or '',
                r['control_uso'] or '',
                r['metodo_pago'] or '',
                r['referencia'] or '',
                r['fecha_liquidacion'] or ''
            ])
            
        csv_data = output.getvalue()
        output.close()
        
        filename = f"Reporte_Financiero_{year}_{month}.csv"
        return Response(
            csv_data,
            mimetype="text/csv",
            headers={"Content-disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        return jsonify({'error': f'Error al exportar CSV: {str(e)}'}), 500

@app.route('/api/patients/<int:patient_id>/reschedule-history', methods=['GET'])
@login_required
def get_patient_reschedule_history(patient_id):
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("""
            SELECT id, agenda_id, fecha_anterior, hora_anterior, fecha_nueva, hora_nueva,
                   modificado_por, motivo, fecha_registro
            FROM historial_reprogramaciones
            WHERE paciente_id = ?
            ORDER BY fecha_registro DESC
        """, (patient_id,))
        rows = cursor.fetchall()
        return jsonify([dict(r) for r in rows])
    except Exception as e:
        return jsonify({'error': f'Error al consultar historial de reprogramaciones: {str(e)}'}), 500

@app.route('/api/admin/consultation-history', methods=['GET'])
@login_required
def get_admin_consultation_history():
    try:
        user_id = session.get('user_id')
        month = request.args.get('month')
        year = request.args.get('year')
        
        if not month or not year:
            now = datetime.now()
            month = f"{now.month:02d}"
            year = str(now.year)
        else:
            month = f"{int(month):02d}"
            year = str(year)
            
        date_prefix = f"{year}-{month}%"
        
        db = get_db()
        cursor = db.cursor()
        
        cursor.execute("""
            SELECT af.id, af.fecha, af.hora, af.tipo_consulta, af.monto, af.moneda,
                   af.estado_pago, af.control_uso, af.metodo_pago, af.referencia, af.fecha_liquidacion,
                   p.id as paciente_id, p.nombres, p.apellidos, p.cedula, p.telefono
            FROM agenda_finanzas af
            JOIN pacientes p ON af.paciente_id = p.id
            WHERE p.psicologo_id = ? AND (af.fecha LIKE ? OR af.fecha_liquidacion LIKE ?)
            ORDER BY af.fecha DESC, af.hora DESC
        """, (user_id, date_prefix, date_prefix))
        
        rows = [dict(r) for r in cursor.fetchall()]
        return jsonify(rows)
    except Exception as e:
        return jsonify({'error': f'Error al obtener historial de consultas: {str(e)}'}), 500

@app.route('/api/admin/consultation-history/<int:event_id>', methods=['DELETE'])
@login_required
def delete_admin_consultation_history_event(event_id):
    try:
        user_id = session.get('user_id')
        db = get_db()
        cursor = db.cursor()

        cursor.execute("""
            SELECT af.id, af.google_event_id, af.paciente_id 
            FROM agenda_finanzas af
            JOIN pacientes p ON af.paciente_id = p.id
            WHERE af.id = ? AND p.psicologo_id = ?
        """, (event_id, user_id))
        row = cursor.fetchone()

        if not row:
            return jsonify({'error': 'Consulta no encontrada o sin permiso para eliminar.'}), 404

        google_event_id = row['google_event_id']
        paciente_id = row['paciente_id']

        if google_event_id:
            service = get_calendar_service()
            if service:
                try:
                    service.events().delete(calendarId='primary', eventId=google_event_id).execute()
                except Exception as ge:
                    print("Error al eliminar evento en Google Calendar:", ge)

        cursor.execute("DELETE FROM sesiones WHERE agenda_id = ?", (event_id,))
        cursor.execute("DELETE FROM agenda_finanzas WHERE id = ?", (event_id,))
        db.commit()

        if paciente_id:
            import threading
            threading.Thread(target=sync_patient_to_firebase, args=(paciente_id,)).start()

        return jsonify({'success': 'Consulta de prueba eliminada con éxito.'})
    except Exception as e:
        return jsonify({'error': f'Error al eliminar consulta: {str(e)}'}), 500

@app.route('/api/patient/agenda-history', methods=['GET'])
@patient_login_required
def get_patient_agenda_history():
    try:
        patient_id = session.get('patient_id')
        if not patient_id:
            return jsonify({'error': 'No ha iniciado sesión como paciente'}), 401
            
        db = get_db()
        cursor = db.cursor()
        
        # Conciliar deudas automáticamente si tiene prepagos
        auto_settle_patient_debts(db, patient_id)
        
        cursor.execute("""
            SELECT af.id, af.fecha, af.hora, af.tipo_consulta, af.estado_pago, af.control_uso, af.confirmada,
                   af.monto, af.moneda, af.fecha_liquidacion
            FROM agenda_finanzas af
            WHERE af.paciente_id = ?
            ORDER BY af.fecha DESC, af.hora DESC
        """, (patient_id,))
        
        rows = cursor.fetchall()
        result = []
        
        for r in rows:
            row_dict = dict(r)
            est = row_dict['estado_pago']
            
            if est == 'Paga' or est == 'Prepagada' or est == 'Cancelada sin aviso - Paga':
                accion = 'Realizada / Paga'
            elif est == 'Cancelada con aviso':
                accion = 'Cancelada a tiempo'
            elif est == 'Cancelada sin aviso':
                accion = 'Cancelada tardía (sin aviso)'
            elif est == 'Reprogramada':
                accion = 'Reprogramada'
            else:
                if row_dict['confirmada'] == 1:
                    accion = 'Agendada (Confirmada)'
                else:
                    accion = 'Agendada (Pendiente por confirmar)'
                    
            row_dict['accion'] = accion
            result.append(row_dict)
            
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': f'Error al obtener historial de agenda del paciente: {str(e)}'}), 500

@app.route('/api/finance/transactions/<int:trans_id>', methods=['GET'])
@login_required
def get_transaction(trans_id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM agenda_finanzas WHERE id = ?", (trans_id,))
    row = cursor.fetchone()
    if not row:
        return jsonify({'error': 'Transacción no encontrada.'}), 404
    return jsonify(dict(row))

@app.route('/api/finance/transactions/<int:trans_id>', methods=['PUT'])
@login_required
def update_transaction(trans_id):
    data = request.json
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("SELECT * FROM agenda_finanzas WHERE id = ?", (trans_id,))
        row = cursor.fetchone()
        if not row:
            return jsonify({'error': 'Transacción no encontrada.'}), 404
            
        original_estado_pago = row['estado_pago']
        estado_pago = data.get('estado_pago') if 'estado_pago' in data else row['estado_pago']
        if original_estado_pago == 'Cancelada sin aviso' and estado_pago == 'Paga':
            estado_pago = 'Cancelada sin aviso - Paga'
        control_uso = data.get('control_uso') if 'control_uso' in data else row['control_uso']
        fecha_liquidacion = data.get('fecha_liquidacion') if 'fecha_liquidacion' in data else row['fecha_liquidacion']
        monto = data.get('monto') if 'monto' in data else row['monto']
        moneda = data.get('moneda') if 'moneda' in data else row['moneda']
        cantidad_sesiones = data.get('cantidad_sesiones') if 'cantidad_sesiones' in data else row['cantidad_sesiones']
        referencia = data.get('referencia') if 'referencia' in data else row['referencia']
        metodo_pago = data.get('metodo_pago') if 'metodo_pago' in data else row['metodo_pago']
        fecha_pago = data.get('fecha_pago') if 'fecha_pago' in data else row['fecha_pago']
        fecha = data.get('fecha') if 'fecha' in data else row['fecha']
        hora = data.get('hora') if 'hora' in data else row['hora']
        tipo_consulta = data.get('tipo_consulta') if 'tipo_consulta' in data else row['tipo_consulta']
        
        if estado_pago == 'ConsumirPrepago':
            cursor.execute("""
                SELECT id, cantidad_sesiones, control_uso 
                FROM agenda_finanzas 
                WHERE paciente_id = ? AND estado_pago = 'Prepagada' AND control_uso = 'No consumida'
                ORDER BY fecha ASC, id ASC LIMIT 1
            """, (row['paciente_id'],))
            pkg = cursor.fetchone()
            if not pkg:
                return jsonify({'error': 'El consultante no tiene sesiones prepagadas disponibles.'}), 400
                
            pkg_id = pkg['id']
            pkg_cant = pkg['cantidad_sesiones']
            if pkg_cant > 1:
                cursor.execute("UPDATE agenda_finanzas SET cantidad_sesiones = ? WHERE id = ?", (pkg_cant - 1, pkg_id))
            else:
                cursor.execute("UPDATE agenda_finanzas SET control_uso = 'Consumida' WHERE id = ?", (pkg_id,))
                
            estado_pago = 'Paga'
            monto = 0.0
            cantidad_sesiones = 1
            control_uso = 'Consumida'
        
        # Sincronizar actualización con Google Calendar si está enlazado
        google_event_id = row['google_event_id']
        if google_event_id:
            service = get_calendar_service()
            if service:
                start_datetime = f"{fecha}T{hora}:00"
                end_hour = str(int(hora.split(':')[0]) + 1).zfill(2)
                end_datetime = f"{fecha}T{end_hour}:{hora.split(':')[1]}:00"
                try:
                    g_event = service.events().get(calendarId='primary', eventId=google_event_id).execute()
                    g_event['start'] = {'dateTime': start_datetime, 'timeZone': 'America/Caracas'}
                    g_event['end'] = {'dateTime': end_datetime, 'timeZone': 'America/Caracas'}
                    # Obtener paciente para rellenar la descripción
                    cursor.execute("SELECT nombres, apellidos, cedula FROM pacientes WHERE id = ?", (row['paciente_id'],))
                    pac = cursor.fetchone()
                    g_event['description'] = f"Cédula: {pac['cedula'] if pac else ''}\nModalidad: {tipo_consulta}\nEstado: {estado_pago}"
                    service.events().update(calendarId='primary', eventId=google_event_id, body=g_event).execute()
                except Exception as ge:
                    print("Error al sincronizar cambio con Google Calendar:", ge)
        
        confirmada = data.get('confirmada') if 'confirmada' in data else row['confirmada']
        
        cursor.execute("""
            UPDATE agenda_finanzas SET
                estado_pago = ?,
                control_uso = ?,
                fecha_liquidacion = ?,
                monto = ?,
                moneda = ?,
                cantidad_sesiones = ?,
                referencia = ?,
                metodo_pago = ?,
                fecha_pago = ?,
                fecha = ?,
                hora = ?,
                tipo_consulta = ?,
                confirmada = ?
            WHERE id = ?
        """, (
            estado_pago,
            control_uso,
            fecha_liquidacion,
            monto,
            moneda,
            cantidad_sesiones,
            referencia,
            metodo_pago,
            fecha_pago,
            fecha,
            hora,
            tipo_consulta,
            confirmada,
            trans_id
        ))
        db.commit()
        
        # Sincronización en segundo plano con Firebase
        import threading
        threading.Thread(target=sync_patient_to_firebase, args=(row['paciente_id'],)).start()
        
        return jsonify({'success': 'Transacción actualizada con éxito.'})
    except Exception as e:
        return jsonify({'error': f'Error al actualizar transacción: {str(e)}'}), 500


# ==========================================
# AGENDA Y GOOGLE CALENDAR
# ==========================================

@app.route('/api/agenda', methods=['GET'])
@login_required
def get_agenda():
    db = get_db()
    cursor = db.cursor()
    psic_id = get_psicologo_id_filter()
    if psic_id is not None:
        cursor.execute("""
            SELECT af.*, p.nombres, p.apellidos, p.cedula,
                   (CASE WHEN s.id IS NOT NULL THEN 1 ELSE 0 END) as has_session
            FROM agenda_finanzas af
            JOIN pacientes p ON af.paciente_id = p.id
            LEFT JOIN sesiones s ON s.agenda_id = af.id
            WHERE (af.hora != '00:00' AND af.hora != '' AND af.hora IS NOT NULL)
              AND p.psicologo_id = ?
            ORDER BY af.fecha ASC, af.hora ASC
        """, (psic_id,))
    else:
        cursor.execute("""
            SELECT af.*, p.nombres, p.apellidos, p.cedula,
                   (CASE WHEN s.id IS NOT NULL THEN 1 ELSE 0 END) as has_session
            FROM agenda_finanzas af
            JOIN pacientes p ON af.paciente_id = p.id
            LEFT JOIN sesiones s ON s.agenda_id = af.id
            WHERE (af.hora != '00:00' AND af.hora != '' AND af.hora IS NOT NULL)
            ORDER BY af.fecha ASC, af.hora ASC
        """)
    events = [dict(row) for row in cursor.fetchall()]
    return jsonify(events)

@app.route('/api/agenda', methods=['POST'])
@login_required
def add_agenda_event():
    data = request.json
    db = get_db()
    cursor = db.cursor()
    
    paciente_id = data.get('paciente_id')
    fecha = data.get('fecha')
    hora = data.get('hora')
    tipo_consulta = data.get('tipo_consulta') # 'Presencial', 'Online'
    
    if not paciente_id or not fecha or not hora or not tipo_consulta:
        return jsonify({'error': 'Paciente, Fecha, Hora y Tipo de consulta son obligatorios.'}), 400
        
    estado_pago = data.get('estado_pago', 'Agendada')
    monto = float(data.get('monto', 0.0) or 0.0)
    moneda = data.get('moneda', 'USD')
    control_uso = data.get('control_uso', 'Consumida')
    cantidad_sesiones = int(data.get('cantidad_sesiones', 1) or 1)
    referencia = data.get('referencia')
    metodo_pago = data.get('metodo_pago')
    fecha_pago = data.get('fecha_pago')
        
    try:
        # Intentar registrar en Google Calendar primero si está configurado
        google_event_id = None
        user_id = session.get('user_id')
        service = get_calendar_service(user_id)
        if service:
            # Obtener datos del paciente
            cursor.execute("SELECT nombres, apellidos, cedula, email FROM pacientes WHERE id = ?", (paciente_id,))
            paciente = cursor.fetchone()
            
            # Formatear fecha y hora para Google RFC3339 con offset de Caracas (-04:00)
            start_datetime = f"{fecha}T{hora}:00-04:00"
            # Asumimos 1 hora de consulta
            end_hour = str(int(hora.split(':')[0]) + 1).zfill(2)
            end_datetime = f"{fecha}T{end_hour}:{hora.split(':')[1]}:00-04:00"
            
            therapist_name = session.get('user_name', 'Paulo Mora')
            
            event_body = {
                'summary': f"Consulta Psicológica - {paciente['nombres']} {paciente['apellidos']}",
                'description': f"Modalidad: {tipo_consulta}\nPsicólogo: Psic. {therapist_name}",
                'start': {'dateTime': start_datetime, 'timeZone': 'America/Caracas'},
                'end': {'dateTime': end_datetime, 'timeZone': 'America/Caracas'},
                'guestsCanInviteOthers': False,
                'reminders': {
                    'useDefault': False,
                    'overrides': [
                        { 'method': 'email', 'minutes': 1440 },
                        { 'method': 'popup', 'minutes': 60 }
                    ]
                }
            }
            if paciente and paciente.get('email'):
                event_body['attendees'] = [
                    {
                        'email': paciente['email'],
                        'displayName': f"{paciente['nombres']} {paciente['apellidos']}"
                    }
                ]
            try:
                g_event = service.events().insert(calendarId='primary', body=event_body, sendUpdates='all').execute()
                google_event_id = g_event.get('id')
            except Exception as ge:
                print("Error creando evento en Google Calendar:", ge)
                
        confirmada = int(data.get('confirmada', 0) or 0)
        
        cursor.execute("""
            INSERT INTO agenda_finanzas (
                paciente_id, fecha, hora, tipo_consulta, monto, moneda, 
                estado_pago, control_uso, google_event_id, cantidad_sesiones,
                referencia, metodo_pago, fecha_pago, confirmada
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            paciente_id, fecha, hora, tipo_consulta, monto, moneda,
            estado_pago, control_uso, google_event_id, cantidad_sesiones,
            referencia, metodo_pago, fecha_pago, confirmada
        ))
        db.commit()
        
        # Notificación Push al paciente sobre nueva cita agendada por el psicólogo
        try:
            from datetime import datetime
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("SELECT nombres FROM usuarios WHERE id = ?", (session.get('user_id'),))
            u_row = cursor.fetchone()
            therapist_name = u_row['nombres'] if u_row else "Paulo Mora"
            
            fb_payload = {
                "id": int(datetime.now().timestamp() * 1000),
                "tipo": "cita",
                "titulo": "📅 Nueva Cita Programada",
                "mensaje": f"El Psic. {therapist_name} ha agendado una nueva cita para el {fecha} a las {hora}.",
                "fecha": now_str,
                "leida": False
            }
            import requests
            requests.post(f"{FIREBASE_DB_URL}/pacientes/{paciente_id}/notificaciones.json", json=fb_payload, timeout=2.0)
            
            # Enviar notificación WebPush al paciente
            try:
                send_webpush_notification(
                    patient_id=paciente_id,
                    title="📅 Nueva Cita Programada",
                    body=f"El Psic. {therapist_name} ha agendado una nueva cita para el {fecha} a las {hora}.",
                    url="/"
                )
            except Exception as wp_ex:
                print("Error al enviar WebPush de nueva cita:", wp_ex)
                
        except Exception as fe:
            print("Error al notificar nueva cita al paciente:", fe)

        # Sincronización en segundo plano con Firebase
        import threading
        threading.Thread(target=sync_patient_to_firebase, args=(paciente_id,)).start()
        
        return jsonify({'success': 'Cita agendada con éxito.', 'google_synced': google_event_id is not None})
    except Exception as e:
        return jsonify({'error': f'Error al agendar cita: {str(e)}'}), 500

@app.route('/api/agenda/quick-pay', methods=['POST'])
@login_required
def agenda_quick_pay():
    """Registra un pago directo sin necesidad de agendar cita."""
    data = request.json
    db = get_db()
    cursor = db.cursor()

    paciente_id = data.get('paciente_id')
    if not paciente_id:
        return jsonify({'error': 'Paciente requerido.'}), 400

    monto           = float(data.get('monto', 0.0) or 0.0)
    moneda          = data.get('moneda', 'USD')
    tipo_consulta   = data.get('tipo_consulta', 'Individual')
    estado_pago     = data.get('estado_pago', 'Paga')
    cantidad_ses    = int(data.get('cantidad_sesiones', 1) or 1)
    referencia      = data.get('referencia', '')
    metodo_pago     = data.get('metodo_pago', 'Efectivo')
    fecha           = data.get('fecha') or datetime.datetime.now().strftime('%Y-%m-%d')
    fecha_pago      = data.get('fecha_pago') or fecha
    hora            = data.get('hora', '00:00')

    try:
        # Determinar control_uso: Si es paquete o prepagada, asignar 'No consumida' para que las sesiones queden disponibles
        control_uso_val = data.get('control_uso')
        if not control_uso_val:
            if cantidad_ses > 1 or estado_pago == 'Prepagada' or 'paquete' in tipo_consulta.lower():
                control_uso_val = 'No consumida'
                if estado_pago == 'Paga':
                    estado_pago = 'Prepagada'
            else:
                control_uso_val = 'Consumida'

        if 'paquete' in tipo_consulta.lower() and cantidad_ses <= 1:
            cursor.execute("SELECT sesiones_paquete_personalizado FROM pacientes WHERE id = ?", (paciente_id,))
            pac_pkg = cursor.fetchone()
            if pac_pkg and pac_pkg['sesiones_paquete_personalizado']:
                cantidad_ses = int(pac_pkg['sesiones_paquete_personalizado'])

        cursor.execute("""
            INSERT INTO agenda_finanzas (
                paciente_id, fecha, hora, tipo_consulta, monto, moneda,
                estado_pago, control_uso, cantidad_sesiones,
                referencia, metodo_pago, fecha_pago, confirmada
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
        """, (
            paciente_id, fecha, hora, tipo_consulta, monto, moneda,
            estado_pago, control_uso_val, cantidad_ses,
            referencia, metodo_pago, fecha_pago
        ))
        db.commit()
        import threading
        threading.Thread(target=sync_patient_to_firebase, args=(paciente_id,)).start()

        # Calcular deuda si el pago es fraccionado
        deuda_generada = data.get('deuda_generada', 0)
        if deuda_generada and float(deuda_generada) > 0:
            cursor.execute("""
                INSERT INTO agenda_finanzas (
                    paciente_id, fecha, hora, tipo_consulta, monto, moneda,
                    estado_pago, control_uso, cantidad_sesiones,
                    referencia, metodo_pago, fecha_pago, confirmada
                ) VALUES (?, ?, '00:00', ?, ?, ?, 'Pendiente', 'Pendiente', 0, ?, ?, ?, 1)
            """, (
                paciente_id, fecha,
                tipo_consulta + ' (Deuda Pago Fraccionado)',
                float(deuda_generada), moneda,
                'Saldo pendiente por pago parcial de paquete', '', fecha_pago
            ))
            db.commit()

        return jsonify({
            'success': 'Pago registrado con éxito.',
            'deuda': float(deuda_generada) if deuda_generada else 0
        })
    except Exception as e:
        return jsonify({'error': f'Error al registrar pago: {str(e)}'}), 500


@app.route('/api/patient-profile/<int:patient_id>', methods=['GET'])
@login_required
def get_patient_profile_rates(patient_id):
    """Retorna datos del paciente incluyendo honorarios personalizados."""
    db = get_db()
    cursor = db.cursor()
    psicologo_id = session.get('user_id')
    cursor.execute("""
        SELECT id, nombres, apellidos, cedula,
               costo_personalizado, moneda_personalizada,
               costo_paquete_personalizado, sesiones_paquete_personalizado
        FROM pacientes WHERE id = ? AND psicologo_id = ?
    """, (patient_id, psicologo_id))
    row = cursor.fetchone()
    if not row:
        return jsonify({'error': 'Paciente no encontrado.'}), 404
    return jsonify(dict(row))


@app.route('/api/patient-debts/<int:patient_id>', methods=['GET'])
@login_required
def get_patient_debts(patient_id):
    """Retorna las consultas pendientes de cobro de un paciente."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT id, fecha, hora, tipo_consulta, monto, moneda, estado_pago
        FROM agenda_finanzas
        WHERE paciente_id = ?
          AND estado_pago IN ('Pendiente', 'Debe')
        ORDER BY fecha DESC
    """, (patient_id,))
    rows = cursor.fetchall()
    return jsonify([dict(r) for r in rows])


@app.route('/api/mark-debts-paid', methods=['POST'])
@login_required
def mark_debts_paid():
    """Marca múltiples registros de agenda_finanzas como pagados."""
    data = request.json or {}
    debt_ids = data.get('debt_ids', [])
    metodo_pago = data.get('metodo_pago', '')
    referencia = data.get('referencia', '')
    fecha_pago = data.get('fecha_pago', '')

    if not debt_ids:
        return jsonify({'error': 'No se indicaron deudas a pagar.'}), 400

    db = get_db()
    cursor = db.cursor()
    psicologo_id = session.get('user_id')

    updated = 0
    for did in debt_ids:
        # Verificar que el registro pertenece a un paciente del psicólogo
        cursor.execute("""
            UPDATE agenda_finanzas SET
                estado_pago = 'Paga',
                metodo_pago = ?,
                referencia = ?,
                fecha_pago = ?
            WHERE id = ?
              AND paciente_id IN (
                  SELECT id FROM pacientes WHERE psicologo_id = ?
              )
        """, (metodo_pago, referencia, fecha_pago, did, psicologo_id))
        updated += cursor.rowcount

    db.commit()
    return jsonify({'success': f'{updated} consultas marcadas como pagadas.'})


@app.route('/api/admin/clear-all-data', methods=['POST'])
@login_required
def clear_all_data():
    """Borra todos los datos del psicólogo previa confirmación explícita escribiendo CONFIRMAR."""
    data = request.json or {}
    confirmation = str(data.get('confirmation', '')).strip().upper()
    
    if confirmation != 'CONFIRMAR':
        return jsonify({'error': 'Debes escribir "CONFIRMAR" para autorizar esta acción.'}), 400

    db = get_db()
    cursor = db.cursor()
    psicologo_id = session.get('user_id')

    try:
        # Obtener IDs de pacientes del psicólogo
        cursor.execute("SELECT id FROM pacientes WHERE psicologo_id = ?", (psicologo_id,))
        patient_ids = [r[0] for r in cursor.fetchall()]

        if patient_ids:
            placeholders = ','.join('?' for _ in patient_ids)
            cursor.execute(f"DELETE FROM sesiones WHERE paciente_id IN ({placeholders})", patient_ids)
            cursor.execute(f"DELETE FROM agenda_finanzas WHERE paciente_id IN ({placeholders})", patient_ids)
            cursor.execute(f"DELETE FROM pacientes WHERE id IN ({placeholders})", patient_ids)

        cursor.execute("DELETE FROM pizarra_visual WHERE psicologo_id = ?", (psicologo_id,))
        cursor.execute("DELETE FROM notificaciones")

        db.commit()

        return jsonify({'success': 'Todos los datos de tu consultorio han sido eliminados con éxito.'})
    except Exception as e:
        db.rollback()
        return jsonify({'error': f'Error al eliminar datos: {str(e)}'}), 500


@app.route('/api/agenda/<int:event_id>', methods=['PUT'])
@login_required
def update_agenda_event(event_id):
    data = request.json
    db = get_db()
    cursor = db.cursor()
    
    fecha = data.get('fecha')
    hora = data.get('hora')
    tipo_consulta = data.get('tipo_consulta')
    estado_pago = data.get('estado_pago')
    
    try:
        cursor.execute("SELECT * FROM agenda_finanzas WHERE id = ?", (event_id,))
        local_event = cursor.fetchone()
        if not local_event:
            return jsonify({'error': 'Evento no encontrado.'}), 404
            
        google_event_id = local_event['google_event_id']
        paciente_id = local_event['paciente_id']
        
        # Obtener datos del paciente
        cursor.execute("SELECT nombres, apellidos, email FROM pacientes WHERE id = ?", (paciente_id,))
        paciente = cursor.fetchone()
        
        # Sincronizar actualización con Google Calendar
        if google_event_id:
            user_id = session.get('user_id')
            service = get_calendar_service(user_id)
            if service:
                start_datetime = f"{fecha}T{hora}:00-04:00"
                end_hour = str(int(hora.split(':')[0]) + 1).zfill(2)
                end_datetime = f"{fecha}T{end_hour}:{hora.split(':')[1]}:00-04:00"
                
                therapist_name = session.get('user_name', 'Paulo Mora')
                
                try:
                    # Traemos el evento original para mantener campos
                    g_event = service.events().get(calendarId='primary', eventId=google_event_id).execute()
                    g_event['summary'] = f"Consulta Psicológica - {paciente['nombres']} {paciente['apellidos']}" if paciente else g_event.get('summary')
                    g_event['description'] = f"Modalidad: {tipo_consulta}\nPsicólogo: Psic. {therapist_name}\n[Actualizado: {estado_pago}]"
                    g_event['start'] = {'dateTime': start_datetime, 'timeZone': 'America/Caracas'}
                    g_event['end'] = {'dateTime': end_datetime, 'timeZone': 'America/Caracas'}
                    g_event['guestsCanInviteOthers'] = False
                    g_event['reminders'] = {
                        'useDefault': False,
                        'overrides': [
                            { 'method': 'email', 'minutes': 1440 },
                            { 'method': 'popup', 'minutes': 60 }
                        ]
                    }
                    if paciente and paciente.get('email'):
                        g_event['attendees'] = [
                            {
                                'email': paciente['email'],
                                'displayName': f"{paciente['nombres']} {paciente['apellidos']}"
                            }
                        ]
                    service.events().update(calendarId='primary', eventId=google_event_id, body=g_event, sendUpdates='all').execute()
                except Exception as ge:
                    print("Error al actualizar evento de Google Calendar:", ge)
                    
        confirmada = data.get('confirmada') if 'confirmada' in data else local_event['confirmada']
        
        cursor.execute("""
            UPDATE agenda_finanzas SET 
                fecha = ?, hora = ?, tipo_consulta = ?, estado_pago = ?, monto = ?, moneda = ?, confirmada = ?
            WHERE id = ?
        """, (
            fecha, hora, tipo_consulta, estado_pago, data.get('monto'), data.get('moneda'), confirmada, event_id
        ))
        cursor.execute("SELECT paciente_id FROM agenda_finanzas WHERE id = ?", (event_id,))
        row = cursor.fetchone()
        paciente_id = row[0] if row else None
        
        db.commit()

        # Enviar notificación WebPush al paciente
        if paciente_id:
            try:
                send_webpush_notification(
                    patient_id=paciente_id,
                    title="🔄 Cita Modificada / Reprogramada",
                    body=f"Tu cita ha sido reprogramada para el {fecha} a las {hora}.",
                    url="/"
                )
            except Exception as wp_ex:
                print("Error al enviar WebPush de reprogramación de cita:", wp_ex)
        
        # Sincronización en segundo plano con Firebase
        if paciente_id:
            import threading
            threading.Thread(target=sync_patient_to_firebase, args=(paciente_id,)).start()
            
        return jsonify({'success': 'Cita actualizada con éxito.'})
    except Exception as e:
        return jsonify({'error': f'Error al actualizar cita: {str(e)}'}), 500

@app.route('/api/agenda/<int:event_id>', methods=['DELETE'])
@login_required
def delete_agenda_event(event_id):
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("SELECT google_event_id, paciente_id FROM agenda_finanzas WHERE id = ?", (event_id,))
        event = cursor.fetchone()
        paciente_id = event['paciente_id'] if event else None
        
        if event and event['google_event_id']:
            service = get_calendar_service()
            if service:
                try:
                    service.events().delete(calendarId='primary', eventId=event['google_event_id']).execute()
                except Exception as ge:
                    print("Error al eliminar evento en Google Calendar:", ge)
                    
        cursor.execute("DELETE FROM agenda_finanzas WHERE id = ?", (event_id,))
        db.commit()

        # Enviar notificación WebPush al paciente
        if paciente_id:
            try:
                send_webpush_notification(
                    patient_id=paciente_id,
                    title="❌ Cita Cancelada",
                    body="Tu cita programada ha sido cancelada por tu terapeuta.",
                    url="/"
                )
            except Exception as wp_ex:
                print("Error al enviar WebPush de cancelación de cita:", wp_ex)
        
        # Sincronización en segundo plano con Firebase
        if paciente_id:
            import threading
            threading.Thread(target=sync_patient_to_firebase, args=(paciente_id,)).start()
            
        return jsonify({'success': 'Cita cancelada con éxito.'})
    except Exception as e:
        return jsonify({'error': f'Error al cancelar cita: {str(e)}'}), 500


# ==========================================
# CONFIGURACIÓN FIREBASE CLOUD MESSAGING (FCM)
# ==========================================

FIREBASE_SA_FILE = os.path.join(BASE_DIR, "firebase_service_account.json")

@app.route('/api/firebase/config', methods=['GET'])
def get_firebase_config():
    _def_cfg = json.dumps({
        "apiKey": "AIzaSyDRQlUEv1SToy5ZdQQyUuYZDIhejeJ81zM",
        "authDomain": "espacio-terapeutico.firebaseapp.com",
        "databaseURL": "https://espacio-terapeutico-default-rtdb.firebaseio.com",
        "projectId": "espacio-terapeutico",
        "storageBucket": "espacio-terapeutico.firebasestorage.app",
        "messagingSenderId": "437385369836",
        "appId": "1:437385369836:web:f3745dc8d65d7ca418edc9",
        "measurementId": "G-M04FWL2963"
    })
    _def_vapid = "BIexDrYPs7iSYmxpkfgQwzatXm_o5pRa1ZAZUvzeF40nAc8N61RFlHqlZ153VNamBelgsKhB4nnowPJm_7Y-Qjc"

    cfg_val = _def_cfg
    vapid_val = _def_vapid

    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT valor FROM configuracion WHERE clave = 'firebase_config'")
        row_cfg = cursor.fetchone()
        cursor.execute("SELECT valor FROM configuracion WHERE clave = 'firebase_vapid_key'")
        row_vapid = cursor.fetchone()
        if row_cfg and row_cfg[0]:
            cfg_val = row_cfg[0]
        if row_vapid and row_vapid[0]:
            vapid_val = row_vapid[0]
    except Exception as e:
        print("Error leyendo configuracion DB:", e)

    try:
        parsed_cfg = json.loads(cfg_val)
    except Exception:
        parsed_cfg = json.loads(_def_cfg)

    # Asegurar que el apiKey coincida con el apiKey oficial de Firebase Console
    parsed_cfg["apiKey"] = "AIzaSyDRQlUEv1SToy5ZdQQyUuYZDIhejeJ81zM"
    cfg_val = json.dumps(parsed_cfg)

    return jsonify({
        "config": cfg_val,
        "vapid_key": vapid_val,
        "vapidKey": vapid_val,
        "apiKey": parsed_cfg.get("apiKey", ""),
        "authDomain": parsed_cfg.get("authDomain", ""),
        "databaseURL": parsed_cfg.get("databaseURL", ""),
        "projectId": parsed_cfg.get("projectId", ""),
        "storageBucket": parsed_cfg.get("storageBucket", ""),
        "messagingSenderId": parsed_cfg.get("messagingSenderId", ""),
        "appId": parsed_cfg.get("appId", "")
    }), 200

@app.route('/api/firebase/config', methods=['POST'])
@login_required
def save_firebase_config():
    data = request.json or {}
    config_json = data.get('config')
    vapid_key = data.get('vapid_key')
    sa_json = data.get('sa_json')
    
    if config_json and vapid_key:
        try:
            import json
            json.loads(config_json) # Validar que sea JSON válido
            db = get_db()
            cursor = db.cursor()
            cursor.execute("INSERT OR REPLACE INTO configuracion (clave, valor) VALUES ('firebase_config', ?)", (config_json,))
            cursor.execute("INSERT OR REPLACE INTO configuracion (clave, valor) VALUES ('firebase_vapid_key', ?)", (vapid_key,))
            db.commit()
        except Exception as e:
            return jsonify({'error': f'Configuración SDK de Firebase Web no es un JSON válido: {str(e)}'}), 400

    if sa_json and sa_json.strip():
        try:
            import json
            config_data = json.loads(sa_json.strip())
            if 'private_key' in config_data and 'client_email' in config_data:
                with open(FIREBASE_SA_FILE, 'w', encoding='utf-8') as f:
                    json.dump(config_data, f, indent=4)
            else:
                return jsonify({'error': 'El JSON pegado no corresponde a una cuenta de servicio válida.'}), 400
        except Exception as e:
            return jsonify({'error': f'JSON de cuenta de servicio inválido: {str(e)}'}), 400

    return jsonify({'success': 'Configuración de Firebase guardada con éxito.'})

@app.route('/api/firebase/upload-sa', methods=['POST'])
@login_required
def upload_firebase_sa():
    if 'file' not in request.files:
        return jsonify({'error': 'No se proporcionó ningún archivo.'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Nombre de archivo vacío.'}), 400
    if not file.filename.endswith('.json'):
        return jsonify({'error': 'El archivo debe ser en formato JSON.'}), 400
    try:
        import json
        content = file.read().decode('utf-8')
        config_data = json.loads(content)
        # Validar estructura de cuenta de servicio de Firebase / Google Cloud
        if 'private_key' not in config_data or 'client_email' not in config_data:
            return jsonify({'error': 'El archivo no es una cuenta de servicio de Firebase válida.'}), 400
        
        with open(FIREBASE_SA_FILE, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=4)
            
        return jsonify({'success': 'Cuenta de servicio de Firebase subida e instalada con éxito.'})
    except Exception as e:
        return jsonify({'error': f'Error al procesar el archivo: {str(e)}'}), 500

@app.route('/api/firebase/save-sa-text', methods=['POST'])
@login_required
def save_firebase_sa_text():
    data = request.json or {}
    sa_text = data.get('sa_json')
    if not sa_text:
        return jsonify({'error': 'El contenido del JSON es requerido.'}), 400
    try:
        import json
        config_data = json.loads(sa_text)
        if 'private_key' not in config_data or 'client_email' not in config_data:
            return jsonify({'error': 'El texto ingresado no corresponde a una cuenta de servicio de Firebase válida.'}), 400
            
        with open(FIREBASE_SA_FILE, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=4)
            
        return jsonify({'success': 'Cuenta de servicio de Firebase guardada con éxito.'})
    except Exception as e:
        return jsonify({'error': f'JSON inválido: {str(e)}'}), 500

@app.route('/api/firebase/status', methods=['GET'])
@login_required
def get_firebase_status():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT valor FROM configuracion WHERE clave = 'firebase_config'")
    has_config = cursor.fetchone() is not None
    has_sa = os.path.exists(FIREBASE_SA_FILE)
    return jsonify({
        'configured': has_config,
        'has_service_account': has_sa
    })

@app.route('/api/firebase/subscribe', methods=['POST'])
def subscribe_firebase():
    data = request.json or {}
    token = data.get('token')
    if not token:
        return jsonify({'error': 'Token FCM requerido.'}), 400

    user_id = session.get('user_id')
    patient_id = session.get('patient_id')

    db = get_db()
    cursor = db.cursor()

    if user_id:
        # Actualizar cualquier token anónimo existente (NULL) o insertar con user_id
        cursor.execute("UPDATE fcm_subscriptions SET user_id = ? WHERE token = ?", (user_id, token))
        if cursor.rowcount == 0:
            cursor.execute("""
                INSERT OR REPLACE INTO fcm_subscriptions (user_id, patient_id, token)
                VALUES (?, NULL, ?)
            """, (user_id, token))
    elif patient_id:
        # Actualizar o insertar con patient_id
        cursor.execute("UPDATE fcm_subscriptions SET patient_id = ? WHERE token = ?", (patient_id, token))
        if cursor.rowcount == 0:
            cursor.execute("""
                INSERT OR REPLACE INTO fcm_subscriptions (user_id, patient_id, token)
                VALUES (NULL, ?, ?)
            """, (patient_id, token))
    else:
        # Sin sesión activa: guardar como anónimo (se actualizará al hacer login)
        cursor.execute("""
            INSERT OR REPLACE INTO fcm_subscriptions (user_id, patient_id, token)
            VALUES (NULL, NULL, ?)
        """, (token,))

    db.commit()
    return jsonify({'success': 'Suscrito a notificaciones FCM con éxito.'})

@app.route('/firebase-messaging-sw.js')
def serve_firebase_messaging_sw():
    # Configuración oficial de Firebase (siempre válida)
    valid_cfg = {
        "apiKey": "AIzaSyDRQlUEv1SToy5ZdQQyUuYZDIhejeJ81zM",
        "authDomain": "espacio-terapeutico.firebaseapp.com",
        "databaseURL": "https://espacio-terapeutico-default-rtdb.firebaseio.com",
        "projectId": "espacio-terapeutico",
        "storageBucket": "espacio-terapeutico.firebasestorage.app",
        "messagingSenderId": "437385369836",
        "appId": "1:437385369836:web:f3745dc8d65d7ca418edc9",
        "measurementId": "G-M04FWL2963"
    }
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT valor FROM configuracion WHERE clave = 'firebase_config'")
        row = cursor.fetchone()
        if row and row[0]:
            saved = json.loads(row[0])
            # Forzar siempre el apiKey correcto
            saved["apiKey"] = valid_cfg["apiKey"]
            config_dict_str = json.dumps(saved)
        else:
            config_dict_str = json.dumps(valid_cfg)
    except Exception:
        config_dict_str = json.dumps(valid_cfg)

    # Renderizar el Service Worker dinámicamente inyectando la configuración
    sw_code = f"""
importScripts('https://www.gstatic.com/firebasejs/10.7.1/firebase-app-compat.js');
importScripts('https://www.gstatic.com/firebasejs/10.7.1/firebase-messaging-compat.js');

firebase.initializeApp({config_dict_str});

const messaging = firebase.messaging();

function showBackgroundNotification(title, body, url, icon, badge, tag) {{
  const notificationOptions = {{
    body: body || 'Tienes una nueva actualización.',
    icon: icon || '/static/logo.png',
    badge: badge || '/static/badge.png',
    sound: '/static/notification.wav',
    vibrate: [200, 100, 200],
    tag: tag || 'espacio-terapeutico-notif',
    renotify: true,
    data: {{ url: url || '/' }},
    actions: [
      {{ action: 'open_app', title: 'Ver en App' }}
    ]
  }};
  return self.registration.showNotification(title || 'Espacio Terapéutico', notificationOptions);
}}

// Handler de notificaciones en SEGUNDO PLANO via FCM SDK (Único responsable para evitar duplicados y "undefined")
messaging.onBackgroundMessage((payload) => {{
  console.log('[firebase-messaging-sw.js] Evento FCM recibido en segundo plano:', payload);

  const title = payload.notification?.title || payload.data?.title || 'Espacio Terapéutico';
  const body = payload.notification?.body || payload.data?.body || 'Tienes una nueva actualización.';
  const url = payload.data?.url || payload.data?.click_action || payload.fcmOptions?.link || '/';
  const icon = payload.data?.icon || payload.notification?.icon || '/static/logo.png';
  const badge = payload.data?.badge || payload.notification?.badge || '/static/badge.png';
  const tag = payload.data?.tag || 'espacio-terapeutico-notif';

  if (title === 'undefined' || body === 'undefined') return;

  return showBackgroundNotification(title, body, url, icon, badge, tag);
}});

// Manejo del clic en la notificación para abrir/enfocar la app
self.addEventListener('notificationclick', (event) => {{
  event.notification.close();
  const targetUrl = event.notification.data ? event.notification.data.url : '/';
  
  event.waitUntil(
    clients.matchAll({{ type: 'window', includeUncontrolled: true }}).then((windowClients) => {{
      for (let client of windowClients) {{
        if (client.url.includes(targetUrl) && 'focus' in client) {{
          return client.focus();
        }}
      }}
      if (clients.openWindow) {{
        return clients.openWindow(targetUrl);
      }}
    }})
  );
}});
"""
    return Response(sw_code, mimetype='application/javascript')

# ==========================================
# CONFIGURACIÓN GOOGLE OAUTH
# ==========================================

def get_calendar_service(user_id=None):
    if not GOOGLE_CALENDAR_AVAILABLE:
        return None
    db = get_db()
    cursor = db.cursor()
    
    if not user_id:
        try:
            user_id = session.get('user_id')
        except RuntimeError:
            user_id = None
            
    if not user_id:
        try:
            cursor.execute("SELECT id FROM usuarios ORDER BY id ASC LIMIT 1")
            row = cursor.fetchone()
            if row:
                user_id = row[0]
        except Exception as e:
            print("Error al obtener primer usuario para Google Calendar:", e)
            
    token_key = f'google_token_{user_id}' if user_id else 'google_token'
    cursor.execute("SELECT valor FROM configuracion WHERE clave = ?", (token_key,))
    row = cursor.fetchone()
    
    # Si no tiene token específico, intentar con el token global anterior 'google_token'
    if not row:
        cursor.execute("SELECT valor FROM configuracion WHERE clave = 'google_token'")
        row = cursor.fetchone()
        if not row:
            return None
        
    try:
        # El token está guardado como JSON
        import json
        creds_data = json.loads(row['valor'])
        creds = Credentials.from_authorized_user_info(creds_data, SCOPES)
        
        # Validar y refrescar token si es necesario
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            # Actualizar en BD
            cursor.execute("INSERT OR REPLACE INTO configuracion (clave, valor) VALUES (?, ?)", 
                           (token_key, creds.to_json()))
            db.commit()
            
        return build('calendar', 'v3', credentials=creds)
    except Exception as e:
        print("Error al inicializar servicio de Google Calendar:", e)
        return None

@app.route('/api/google/status', methods=['GET'])
@login_required
def google_status():
    import traceback
    try:
        has_credentials_json = os.path.exists(CLIENT_SECRETS_FILE)
        service = get_calendar_service()
        return jsonify({
            'configured': service is not None,
            'has_credentials_json': has_credentials_json
        })
    except Exception as e:
        print("Error en google_status:", traceback.format_exc())
        return jsonify({
            'configured': False,
            'has_credentials_json': os.path.exists(CLIENT_SECRETS_FILE),
            'error': str(e)
        }), 200

@app.route('/api/google/upload-credentials', methods=['POST'])
@login_required
def upload_google_credentials():
    if 'file' not in request.files:
        return jsonify({'error': 'No se proporcionó ningún archivo.'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Nombre de archivo vacío.'}), 400
    if not file.filename.endswith('.json'):
        return jsonify({'error': 'El archivo debe ser en formato JSON.'}), 400
    try:
        import json
        content = file.read().decode('utf-8')
        config_data = json.loads(content)
        # Validar estructura básica de Google OAuth JSON
        if 'web' not in config_data and 'installed' not in config_data:
            return jsonify({'error': 'El archivo no es un JSON de credenciales de Google válido.'}), 400
        
        with open(CLIENT_SECRETS_FILE, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=4)
            
        return jsonify({'success': 'Credenciales subidas e instaladas con éxito.'})
    except Exception as e:
        return jsonify({'error': f'Error al procesar el archivo: {str(e)}'}), 500


@app.route('/api/google/authorize')
@login_required
def google_authorize():
    import traceback
    try:
        if not GOOGLE_CALENDAR_AVAILABLE:
            return jsonify({
                'error': 'Fallo al iniciar flujo con Google Calendar',
                'detalle': 'Las librerías de Google Calendar no están instaladas en PythonAnywhere. Ejecuta pip install google-auth-oauthlib google-api-python-client en la consola.'
            }), 500

        if not os.path.exists(CLIENT_SECRETS_FILE):
            return "Error: Falta el archivo credentials.json en el servidor.", 400
            
        redirect_uri = url_for('google_callback', _external=True)
        if not redirect_uri.startswith('https://') and 'localhost' not in redirect_uri and '127.0.0.1' not in redirect_uri:
            redirect_uri = redirect_uri.replace('http://', 'https://')
            
        flow = Flow.from_client_secrets_file(
            CLIENT_SECRETS_FILE,
            scopes=SCOPES,
            redirect_uri=redirect_uri
        )
        
        authorization_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent'
        )
        
        session['state'] = state
        return redirect(authorization_url)
    except Exception as e:
        print("Error en google_authorize:", traceback.format_exc())
        return jsonify({
            'error': 'Fallo al iniciar flujo con Google Calendar',
            'detalle': str(e)
        }), 500

@app.route('/api/google/callback')
def google_callback():
    import traceback
    try:
        if not GOOGLE_CALENDAR_AVAILABLE:
            return "Error: Librerías de Google no instaladas.", 500

        state = session.get('state')
        
        redirect_uri = url_for('google_callback', _external=True)
        if not redirect_uri.startswith('https://') and 'localhost' not in redirect_uri and '127.0.0.1' not in redirect_uri:
            redirect_uri = redirect_uri.replace('http://', 'https://')
            
        flow = Flow.from_client_secrets_file(
            CLIENT_SECRETS_FILE,
            scopes=SCOPES,
            state=state,
            redirect_uri=redirect_uri
        )
        
        req_url = request.url
        if not req_url.startswith('https://') and 'localhost' not in req_url and '127.0.0.1' not in req_url:
            req_url = req_url.replace('http://', 'https://')
            
        # Habilitar transporte inseguro por seguridad en proxies locales/remotos
        os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
        
        flow.fetch_token(authorization_response=req_url)
        creds = flow.credentials
        
        # Guardar en base de datos local
        db = get_db()
        cursor = db.cursor()
        user_id = session.get('user_id')
        token_key = f'google_token_{user_id}' if user_id else 'google_token'
        cursor.execute("INSERT OR REPLACE INTO configuracion (clave, valor) VALUES (?, ?)", 
                       (token_key, creds.to_json()))
        db.commit()
        
        # Redirigir de regreso a la interfaz principal (SPA)
        return """
        <html>
            <body onload="window.close();">
                <h3>Conexión con Google Calendar exitosa. Esta ventana se cerrará automáticamente.</h3>
                <script>
                    if (window.opener) {
                        window.opener.location.reload();
                    }
                </script>
            </body>
        </html>
        """
    except Exception as e:
        print("Error en google_callback:", traceback.format_exc())
        return f"""
        <html>
            <body>
                <h3>Fallo al completar la autorización con Google Calendar</h3>
                <p>Detalle del error: {str(e)}</p>
                <button onclick="window.close();">Cerrar Ventana</button>
            </body>
        </html>
        """, 500

@app.route('/api/google/sync', methods=['POST'])
@login_required
def sync_google_calendar():
    import traceback
    try:
        service = get_calendar_service()
        if not service:
            return jsonify({'error': 'Google Calendar no está configurado o autorizado.'}), 400
        # 1. Traer eventos futuros de Google Calendar
        now = datetime.datetime.utcnow().isoformat() + 'Z' # 'Z' indica UTC
        events_result = service.events().list(
            calendarId='primary', timeMin=now,
            maxResults=100, singleEvents=True,
            orderBy='startTime'
        ).execute()
        g_events = events_result.get('items', [])
        
        db = get_db()
        cursor = db.cursor()
        
        synced_count = 0
        for ge in g_events:
            g_id = ge['id']
            summary = ge.get('summary', '')
            desc = ge.get('description', '')
            
            # Buscar si el evento ya está sincronizado localmente
            cursor.execute("SELECT id FROM agenda_finanzas WHERE google_event_id = ?", (g_id,))
            local_event = cursor.fetchone()
            
            if local_event:
                # Ya existe localmente. Actualizamos fecha/hora si cambió
                # Google retorna fecha/hora en formato RFC3339 (e.g. 2026-07-06T15:30:00-04:00)
                start = ge['start'].get('dateTime') or ge['start'].get('date')
                if start and 'T' in start:
                    fecha_g = start.split('T')[0]
                    hora_g = start.split('T')[1][:5]
                    
                    cursor.execute("""
                        UPDATE agenda_finanzas 
                        SET fecha = ?, hora = ? 
                        WHERE google_event_id = ?
                    """, (fecha_g, hora_g, g_id))
                synced_count += 1
            else:
                # Es nuevo desde Google Calendar. Intentamos enlazarlo a un paciente por nombre en el summary
                # El summary suele ser "Consulta: Juan Perez"
                paciente_id = None
                if "Consulta:" in summary:
                    nombre_buscado = summary.replace("Consulta:", "").strip()
                    # Buscar paciente que coincida por nombre y apellido
                    cursor.execute("""
                        SELECT id FROM pacientes 
                        WHERE (nombres || ' ' || apellidos) LIKE ? 
                        LIMIT 1
                    """, (f"%{nombre_buscado}%",))
                    pac_row = cursor.fetchone()
                    if pac_row:
                        paciente_id = pac_row['id']
                
                # Si no encontramos paciente, no creamos la cita local para evitar inconsistencias de llave foránea,
                # o podemos dejarla en espera. En este flujo, solo importamos si el paciente existe en la BD local.
                if paciente_id:
                    start = ge['start'].get('dateTime') or ge['start'].get('date')
                    if start and 'T' in start:
                        fecha_g = start.split('T')[0]
                        hora_g = start.split('T')[1][:5]
                        
                        modalidad = 'Online'
                        if 'Presencial' in desc or 'presencial' in summary.lower():
                            modalidad = 'Presencial'
                            
                        cursor.execute("""
                            INSERT INTO agenda_finanzas (
                                paciente_id, fecha, hora, tipo_consulta, monto, moneda, 
                                estado_pago, control_uso, google_event_id
                            ) VALUES (?, ?, ?, ?, 0.0, 'USD', 'Pendiente', 'Consumida', ?)
                        """, (paciente_id, fecha_g, hora_g, modalidad, g_id))
                        synced_count += 1
                        
        db.commit()
        return jsonify({'success': f'Sincronización completada. {synced_count} eventos actualizados/importados.'})
        
    except Exception as e:
        return jsonify({'error': f'Error durante la sincronización: {str(e)}'}), 500


# ==========================================
# EXPORTACIÓN A WORD (.DOCX)
# ==========================================

@app.route('/api/export/word/<int:patient_id>', methods=['GET'])
@login_required
def export_word(patient_id):
    db = get_db()
    cursor = db.cursor()
    
    # 1. Obtener datos del paciente
    cursor.execute("SELECT * FROM pacientes WHERE id = ?", (patient_id,))
    pac = cursor.fetchone()
    if not pac:
        return jsonify({'error': 'Paciente no encontrado'}), 404
        
    # 2. Obtener sesiones
    cursor.execute("SELECT * FROM sesiones WHERE paciente_id = ? ORDER BY fecha ASC", (patient_id,))
    sessions = cursor.fetchall()
    
    # 3. Obtener balance financiero
    cursor.execute("SELECT * FROM agenda_finanzas WHERE paciente_id = ? ORDER BY fecha ASC", (patient_id,))
    finance_events = cursor.fetchall()
    
    # Crear documento Word
    doc = docx.Document()
    
    # Estilo y Título Principal
    title = doc.add_paragraph()
    title_run = title.add_run("HISTORIA CLÍNICA Y EXPEDIENTE PSICOLÓGICO")
    title_run.bold = True
    title_run.font.size = Pt(18)
    title_run.font.color.rgb = docx.shared.RGBColor(0x3D, 0x1E, 0x3F) # Berenjena Oscuro
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    subtitle = doc.add_paragraph()
    sub_run = subtitle.add_run(f"Consultante: {pac['nombres']} {pac['apellidos']} | Cédula: {pac['cedula']}")
    sub_run.italic = True
    sub_run.font.size = Pt(12)
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    # Margen horizontal
    doc.add_paragraph("__________________________________________________________________")
    
    # Sección 1: Datos Personales
    h1 = doc.add_heading(level=1)
    h1_run = h1.add_run("1. Datos Personales y Filiación")
    h1_run.font.color.rgb = docx.shared.RGBColor(0x3D, 0x1E, 0x3F)
    
    table_data = [
        ("Nombres y Apellidos", f"{pac['nombres']} {pac['apellidos']}"),
        ("Cédula de Identidad", pac['cedula']),
        ("Pronombre / Género", f"{pac['pronombre'] or 'N/A'} / {pac['genero'] or 'N/A'}"),
        ("Edad", str(pac['edad']) if pac['edad'] else "N/A"),
        ("Lugar y Fecha de Nacimiento", f"{pac['lugar_nacimiento'] or 'N/A'} ({pac['fecha_nacimiento'] or 'N/A'})"),
        ("Residencia Actual", ", ".join(filter(None, [pac.get('residencia_actual') or pac.get('ciudad'), pac.get('pais')])) or "N/A"),
        ("Reside con", pac['con_quien_reside'] or "N/A"),
        ("Nivel Académico / Ocupación", f"{pac['nivel_academico'] or 'N/A'} / {pac['ocupacion'] or 'N/A'}"),
        ("Estado Civil / Relacional", pac['estado_civil'] or "N/A"),
    ]
    
    table = doc.add_table(rows=0, cols=2)
    table.style = 'Light Shading Accent 1'
    for label, val in table_data:
        row_cells = table.add_row().cells
        row_cells[0].text = label
        row_cells[1].text = val
        
    doc.add_paragraph() # Espacio
    
    # Sección 2: Antecedentes e Impresión Diagnóstica
    h2 = doc.add_heading(level=1)
    h2_run = h2.add_run("2. Antecedentes e Impresión Diagnóstica")
    h2_run.font.color.rgb = docx.shared.RGBColor(0x3D, 0x1E, 0x3F)
    
    doc.add_paragraph().add_run("Antecedentes Médicos:").bold = True
    doc.add_paragraph(f"- Personales: {pac['antecedentes_medicos_personales'] or 'Sin registrar'}")
    doc.add_paragraph(f"- Familiares: {pac['antecedentes_medicos_familiares'] or 'Sin registrar'}")
    
    doc.add_paragraph().add_run("Antecedentes Psicológicos y Psiquiátricos:").bold = True
    doc.add_paragraph(f"- Personales: {pac['antecedentes_psicologicos_personales'] or 'Sin registrar'}")
    doc.add_paragraph(f"- Familiares: {pac['antecedentes_psicologicos_familiares'] or 'Sin registrar'}")
    
    doc.add_paragraph().add_run("Motivo de Consulta y Expectativas:").bold = True
    doc.add_paragraph(f"- Asistencia previa al psicólogo: {pac['asistencia_previa_psicologo'] or 'Sin registrar'}")
    doc.add_paragraph(f"- Motivo de consulta actual: {pac['motivo_consulta'] or 'Sin registrar'}")
    doc.add_paragraph(f"- Expectativas del proceso: {pac['expectativas'] or 'Sin registrar'}")
    
    doc.add_paragraph().add_run("Tratamiento Farmacológico Activo:").bold = True
    doc.add_paragraph(pac['farmacologia'] or "Ninguno")
    
    doc.add_paragraph().add_run("Contacto de Emergencia:").bold = True
    doc.add_paragraph(f"{pac['contacto_emergencia_nombre'] or 'N/A'} ({pac['contacto_emergencia_parentesco'] or 'N/A'})")
    
    doc.add_paragraph().add_run("Impresión Diagnóstica Evolutiva:").bold = True
    doc.add_paragraph(pac['diagnostico'] or "Sin impresión diagnóstica anotada.")
    
    doc.add_page_break()
    
    # Sección 3: Evolución Cronológica (Sesiones)
    h3 = doc.add_heading(level=1)
    h3_run = h3.add_run("3. Registro de Sesiones (Evolución)")
    h3_run.font.color.rgb = docx.shared.RGBColor(0x3D, 0x1E, 0x3F)
    
    if not sessions:
        doc.add_paragraph("No hay sesiones de evolución registradas para este consultante.")
    else:
        for idx, s in enumerate(sessions, 1):
            p_ses = doc.add_paragraph()
            p_ses.add_run(f"Sesión N° {idx} — Fecha: {s['fecha']} | Modalidad: {s['modalidad']}").bold = True
            doc.add_paragraph().add_run("Resumen abordado:").bold = True
            doc.add_paragraph(s['resumen'] or "Sin resumen.")
            doc.add_paragraph().add_run("Tareas asignadas al consultante:").bold = True
            doc.add_paragraph(s['tareas_asignadas'] or "Ninguna.")
            doc.add_paragraph().add_run("Recursos entregados:").bold = True
            doc.add_paragraph(s['recursos_entregados'] or "Ninguno.")
            doc.add_paragraph().add_run("Anotaciones próxima consulta:").bold = True
            doc.add_paragraph(s['anotaciones_proxima'] or "Ninguna.")
            doc.add_paragraph().add_run("Compromisos del psicólogo:").bold = True
            doc.add_paragraph(s['compromisos_psicologo'] or "Ninguno.")
            doc.add_paragraph("____________________________________________________")
            
    doc.add_page_break()
    
    # Sección 4: Historial de Citas y Finanzas
    h4 = doc.add_heading(level=1)
    h4_run = h4.add_run("4. Historial de Citas y Estado de Cuentas")
    h4_run.font.color.rgb = docx.shared.RGBColor(0x3D, 0x1E, 0x3F)
    
    if not finance_events:
        doc.add_paragraph("No hay registro de citas o transacciones financieras asociadas.")
    else:
        table_f = doc.add_table(rows=1, cols=6)
        table_f.style = 'Light Shading Accent 1'
        hdr_cells = table_f.rows[0].cells
        hdr_cells[0].text = 'Fecha'
        hdr_cells[1].text = 'Hora'
        hdr_cells[2].text = 'Modalidad'
        hdr_cells[3].text = 'Monto'
        hdr_cells[4].text = 'Estado Pago'
        hdr_cells[5].text = 'Control Uso'
        
        for fe in finance_events:
            row_cells = table_f.add_row().cells
            row_cells[0].text = fe['fecha']
            row_cells[1].text = fe['hora']
            row_cells[2].text = fe['tipo_consulta']
            row_cells[3].text = f"{fe['monto']} {fe['moneda']}"
            row_cells[4].text = fe['estado_pago']
            row_cells[5].text = fe['control_uso']
            
    # Guardar en archivo temporal
    filename = f"expediente_{pac['cedula']}.docx"
    filepath = os.path.join(os.getcwd(), filename)
    doc.save(filepath)
    
    # Enviar archivo
    return send_file(filepath, as_attachment=True, download_name=filename)


# ==========================================
# COPIAS DE SEGURIDAD / RESPALDO
# ==========================================

@app.route('/api/backup', methods=['GET'])
@login_required
def create_backup():
    """Descarga la base de datos .db directamente al navegador."""
    if not os.path.exists(DATABASE):
        return jsonify({'error': 'La base de datos aún no se ha inicializado.'}), 400
        
    dt = datetime.datetime.now()
    now_str = dt.strftime("%Y-%m-%d_%H-%M")
    backup_filename = f"copia_seguridad_clinica_{now_str}.db"
    
    try:
        db = getattr(g, '_database', None)
        if db is not None:
            db.close()
            
        return send_file(
            DATABASE,
            as_attachment=True,
            download_name=backup_filename,
            mimetype='application/x-sqlite3'
        )
    except Exception as e:
        return jsonify({'error': f'Error al descargar copia de seguridad: {str(e)}'}), 500

@app.route('/api/restore', methods=['POST'])
@login_required
def restore_backup():
    if 'file' not in request.files:
        return jsonify({'error': 'No se cargó ningún archivo.'}), 400
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Nombre de archivo vacío.'}), 400
        
    if not file.filename.endswith('.db'):
        return jsonify({'error': 'El archivo de respaldo debe tener extensión .db'}), 400

    import tempfile, sqlite3 as _sqlite3

    # Guardar el archivo subido en temporal
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
    file.save(tmp.name)
    tmp.close()

    stats = {'pacientes': 0, 'agenda': 0, 'sesiones': 0, 'omitidos': 0, 'errores': []}

    try:
        conn_b = _sqlite3.connect(tmp.name)
        conn_b.row_factory = _sqlite3.Row
        cur_b = conn_b.cursor()

        # Obtener tablas disponibles en el respaldo
        cur_b.execute("SELECT name FROM sqlite_master WHERE type='table'")
        backup_tables = {r[0] for r in cur_b.fetchall()}

        # Obtener psicólogo actual (el que hace la restauración)
        db_target = get_db()
        cur_t = db_target.cursor()
        cur_t.execute("SELECT id FROM usuarios WHERE id = ?", (session.get('user_id', 1),))
        psic_row = cur_t.fetchone()
        psic_id = psic_row['id'] if psic_row else 1

        # Helper: obtener columnas de una tabla en el respaldo
        def backup_cols(table_name):
            try:
                cur_b.execute(f"PRAGMA table_info(`{table_name}`)")
                return {r['name'] for r in cur_b.fetchall()}
            except:
                return set()

        # ─── MIGRAR PACIENTES ────────────────────────────────────────────
        if 'pacientes' in backup_tables:
            cols_b = backup_cols('pacientes')
            cur_b.execute("SELECT * FROM pacientes")
            for p in cur_b.fetchall():
                p = dict(p)
                # Verificar duplicado por id o cédula
                cedula = p.get('cedula') or ''
                cur_t.execute(
                    "SELECT id FROM pacientes WHERE id=? OR (cedula!='' AND cedula=?)",
                    (p['id'], cedula)
                )
                if cur_t.fetchone():
                    stats['omitidos'] += 1
                    continue
                try:
                    cur_t.execute("""
                        INSERT INTO pacientes (
                            id, nombres, apellidos, cedula, pronombre, genero, edad,
                            lugar_nacimiento, fecha_nacimiento, residencia_actual,
                            con_quien_reside, nivel_academico, ocupacion, estado_civil,
                            antecedentes_medicos_familiares, antecedentes_medicos_personales,
                            antecedentes_psicologicos_familiares, antecedentes_psicologicos_personales,
                            asistencia_previa_psicologo, motivo_consulta, expectativas,
                            farmacologia, contacto_emergencia_nombre, contacto_emergencia_parentesco,
                            diagnostico, fecha_registro, telefono, email, psicologo_id
                        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (
                        p['id'],
                        p.get('nombres', ''),
                        p.get('apellidos', ''),
                        p.get('cedula', ''),
                        p.get('pronombre', ''),
                        p.get('genero', ''),
                        p.get('edad', ''),
                        p.get('lugar_nacimiento', ''),
                        p.get('fecha_nacimiento', ''),
                        p.get('residencia_actual', ''),
                        p.get('con_quien_reside', ''),
                        p.get('nivel_academico', ''),
                        p.get('ocupacion', ''),
                        p.get('estado_civil', ''),
                        p.get('antecedentes_medicos_familiares', ''),
                        p.get('antecedentes_medicos_personales', ''),
                        p.get('antecedentes_psicologicos_familiares', ''),
                        p.get('antecedentes_psicologicos_personales', ''),
                        p.get('asistencia_previa_psicologo', ''),
                        p.get('motivo_consulta', ''),
                        p.get('expectativas', ''),
                        p.get('farmacologia', ''),
                        p.get('contacto_emergencia_nombre', ''),
                        p.get('contacto_emergencia_parentesco', ''),
                        p.get('diagnostico', ''),
                        p.get('fecha_registro', ''),
                        p.get('telefono', ''),
                        p.get('email', ''),
                        p.get('psicologo_id', psic_id)
                    ))
                    stats['pacientes'] += 1
                except Exception as e:
                    stats['errores'].append(f"Paciente {p.get('nombres','?')}: {str(e)[:60]}")

        # ─── MIGRAR AGENDA/FINANZAS ──────────────────────────────────────
        if 'agenda_finanzas' in backup_tables:
            cur_b.execute("SELECT * FROM agenda_finanzas")
            for a in cur_b.fetchall():
                a = dict(a)
                cur_t.execute("SELECT id FROM agenda_finanzas WHERE id=?", (a['id'],))
                if cur_t.fetchone():
                    stats['omitidos'] += 1
                    continue
                try:
                    cur_t.execute("""
                        INSERT INTO agenda_finanzas (
                            id, paciente_id, fecha, hora, google_event_id, tipo_consulta,
                            monto, moneda, estado_pago, control_uso, fecha_liquidacion,
                            cantidad_sesiones, referencia, metodo_pago, fecha_pago, confirmada
                        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (
                        a['id'], a.get('paciente_id'), a.get('fecha',''),
                        a.get('hora',''), a.get('google_event_id',''),
                        a.get('tipo_consulta','Individual'),
                        a.get('monto', 0), a.get('moneda','USD'),
                        a.get('estado_pago','Pendiente'),
                        a.get('control_uso', 0), a.get('fecha_liquidacion',''),
                        a.get('cantidad_sesiones', 1), a.get('referencia',''),
                        a.get('metodo_pago',''), a.get('fecha_pago',''),
                        a.get('confirmada', 1)
                    ))
                    stats['agenda'] += 1
                except Exception as e:
                    stats['errores'].append(f"Agenda id={a.get('id')}: {str(e)[:60]}")

        # ─── MIGRAR SESIONES (respetando cifrado existente) ──────────────
        if 'sesiones' in backup_tables:
            cur_b.execute("SELECT * FROM sesiones")
            for s in cur_b.fetchall():
                s = dict(s)
                cur_t.execute("SELECT id FROM sesiones WHERE id=?", (s['id'],))
                if cur_t.fetchone():
                    stats['omitidos'] += 1
                    continue

                def _safe_enc(val):
                    """Cifra solo si no está ya cifrado."""
                    if not val:
                        return ''
                    v = str(val)
                    if v.startswith('enc:'):
                        return v  # ya cifrado, no tocar
                    return encrypt_clinical_text(v)

                try:
                    cur_t.execute("""
                        INSERT INTO sesiones (
                            id, paciente_id, agenda_id, fecha, modalidad, estado,
                            resumen, tareas_asignadas, recursos_entregados,
                            anotaciones_proxima, compromisos_psicologo,
                            diagnostico, test_aplicados, archivo_adjunto
                        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (
                        s['id'], s.get('paciente_id'), s.get('agenda_id'),
                        s.get('fecha',''), s.get('modalidad','Online'),
                        s.get('estado','Realizada'),
                        _safe_enc(s.get('resumen')),
                        s.get('tareas_asignadas',''),
                        s.get('recursos_entregados',''),
                        _safe_enc(s.get('anotaciones_proxima')),
                        _safe_enc(s.get('compromisos_psicologo')),
                        _safe_enc(s.get('diagnostico')),
                        _safe_enc(s.get('test_aplicados')),
                        s.get('archivo_adjunto','')
                    ))
                    stats['sesiones'] += 1
                except Exception as e:
                    stats['errores'].append(f"Sesión id={s.get('id')}: {str(e)[:60]}")

        db_target.commit()
        conn_b.close()
        os.unlink(tmp.name)

        msg = (f"Restauración completada: "
               f"{stats['pacientes']} pacientes, "
               f"{stats['agenda']} registros financieros, "
               f"{stats['sesiones']} sesiones importadas. "
               f"{stats['omitidos']} registros ya existían (omitidos).")
        if stats['errores']:
            msg += f" Advertencias: {'; '.join(stats['errores'][:3])}"

        return jsonify({'success': msg, 'stats': stats})

    except Exception as e:
        try:
            os.unlink(tmp.name)
        except:
            pass
        return jsonify({'error': f'Error al restaurar: {str(e)}'}), 500



# ==========================================
@app.after_request
def add_header(r):
    r.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    r.headers["Pragma"] = "no-cache"
    r.headers["Expires"] = "0"
    return r

@app.route('/')
def index():
    return send_file(get_resource_path('templates/index.html'))

@app.route('/manifest.json')
def serve_manifest():
    return send_file(get_resource_path('static/manifest.json'), mimetype='application/manifest+json')

@app.route('/sw.js')
def serve_sw():
    try:
        sw_path = get_resource_path('static/sw.js')
        with open(sw_path, 'r', encoding='utf-8') as f:
            sw_content = f.read()
    except Exception as e:
        sw_content = ""
        
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT valor FROM configuracion WHERE clave = 'firebase_config'")
    row = cursor.fetchone()
    
    if row and row[0]:
        config_dict_str = row[0]
        firebase_sw_code = f"""
// === FIREBASE CLOUD MESSAGING INTEGRATION ===
importScripts('https://www.gstatic.com/firebasejs/10.7.1/firebase-app-compat.js');
importScripts('https://www.gstatic.com/firebasejs/10.7.1/firebase-messaging-compat.js');

try {{
  firebase.initializeApp({config_dict_str});
  const messaging = firebase.messaging();
  
  messaging.onBackgroundMessage((payload) => {{
    console.log('[sw.js FCM] Mensaje en segundo plano:', payload);
    const title = payload.notification?.title || payload.data?.title || 'Mi Consultorio';
    const body = payload.notification?.body || payload.data?.body || 'Tienes una nueva notificación.';
    const url = payload.data?.url || '/';
    
    self.registration.showNotification(title, {{
      body: body,
      icon: '/static/logo.png',
      badge: '/static/badge.png',
      sound: '/static/notification.wav',
      vibrate: [200, 100, 200],
      data: {{ url: url }}
    }});
  }});
}} catch(err) {{
  console.error("Fallo al inicializar Firebase en el Service Worker:", err);
}}
"""
        sw_content += firebase_sw_code
        
    response = Response(sw_content, mimetype='application/javascript')
    response.headers['Service-Worker-Allowed'] = '/'
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

if __name__ == '__main__':
    # Cerrar la pantalla de carga nativa si está disponible
    try:
        import pyi_splash
        pyi_splash.update_text("Iniciando base de datos...")
        init_db()
        pyi_splash.update_text("Cargando interfaz...")
        pyi_splash.close()
    except ImportError:
        init_db()

    import threading
    import webview

    def run_flask():
        # Ejecutar Flask en modo producción (debug=False)
        app.run(host='127.0.0.1', port=5001, debug=False)

    # Lanzar servidor en segundo plano
    t = threading.Thread(target=run_flask)
    t.daemon = True
    t.start()

    # Abrir ventana nativa de escritorio
    import time
    webview.create_window(
        "Espacio Terapéutico",
        f"http://127.0.0.1:5001?t={int(time.time())}",
        width=1280,
        height=850,
        min_size=(1024, 768)
    )
    webview.start()

@app.route('/api/onboarding/complete', methods=['POST'])
@login_required
def complete_onboarding():
    data = request.json or {}
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Sesión no válida.'}), 401
        
    db = get_db()
    cursor = db.cursor()
    import json
    
    nombres = data.get('nombres')
    apellidos = data.get('apellidos')
    estudios = data.get('estudios', '')
    federacion = data.get('federacion', '')
    raw_slug = data.get('slug') or f"psic.{nombres}{apellidos}"
    cleaned_slug = raw_slug.strip().lower().replace(" ", "").replace("/", "").replace(".", "")
    if not cleaned_slug.startswith("psic"):
        cleaned_slug = "psic." + cleaned_slug
    else:
        cleaned_slug = "psic." + cleaned_slug[4:]
        
    duracion = int(data.get('duracion', 60))
    receso = int(data.get('receso', 15))
    perfiles = data.get('perfiles', [])
    metodos_pago = data.get('metodos_pago', {})
    
    if not nombres or not apellidos:
        return jsonify({'error': 'Nombres y Apellidos son obligatorios.'}), 400
        
    cursor.execute("SELECT id FROM usuarios WHERE slug = ? AND id != ?", (cleaned_slug, user_id))
    if cursor.fetchone():
        cleaned_slug = f"{cleaned_slug}{user_id}"

    default_visual = {
        "duracion": duracion,
        "receso": receso,
        "antelacion": 24,
        "alerta_confirmacion": 24,
        "alerta_recordatorio": 2,
        "alerta_cierre": 2,
        "limite_cancelacion_tipo": "horas",
        "limite_cancelacion_valor": 24,
        "perfiles": perfiles if perfiles else [
            {
                "id": "default_online",
                "nombre": "Horario Online",
                "modalidad": "Online",
                "dias": [
                    {"dia": 1, "nombre": "Lunes", "activo": True, "rangos": [{"inicio": "12:00", "fin": "16:00"}, {"inicio": "18:00", "fin": "22:00"}]},
                    {"dia": 2, "nombre": "Martes", "activo": True, "rangos": [{"inicio": "18:00", "fin": "22:00"}]},
                    {"dia": 3, "nombre": "Miércoles", "activo": False, "rangos": []},
                    {"dia": 4, "nombre": "Jueves", "activo": False, "rangos": []},
                    {"dia": 5, "nombre": "Viernes", "activo": False, "rangos": []},
                    {"dia": 6, "nombre": "Sábado", "activo": False, "rangos": []},
                    {"dia": 0, "nombre": "Domingo", "activo": False, "rangos": []}
                ]
            },
            {
                "id": "default_presencial",
                "nombre": "Horario Presencial",
                "modalidad": "Presencial",
                "dias": [
                    {"dia": 1, "nombre": "Lunes", "activo": False, "rangos": []},
                    {"dia": 2, "nombre": "Martes", "activo": False, "rangos": []},
                    {"dia": 3, "nombre": "Miércoles", "activo": True, "rangos": [{"inicio": "08:00", "fin": "12:00"}]},
                    {"dia": 4, "nombre": "Jueves", "activo": True, "rangos": [{"inicio": "08:00", "fin": "12:00"}]},
                    {"dia": 5, "nombre": "Viernes", "activo": True, "rangos": [{"inicio": "08:00", "fin": "12:00"}]},
                    {"dia": 6, "nombre": "Sábado", "activo": False, "rangos": []},
                    {"dia": 0, "nombre": "Domingo", "activo": False, "rangos": []}
                ]
            }
        ]
    }
    
    cfg_visual_str = json.dumps(default_visual)
    metodos_pago_str = json.dumps(metodos_pago) if metodos_pago else json.dumps({})

    try:
        cursor.execute("""
            UPDATE usuarios
            SET nombres = ?, apellidos = ?, estudios = ?, federacion = ?,
                slug = ?, configuracion_horarios_visual = ?, metodos_pago = ?,
                primer_inicio = 0
            WHERE id = ?
        """, (nombres, apellidos, estudios, federacion, cleaned_slug, cfg_visual_str, metodos_pago_str, user_id))
        db.commit()
        return jsonify({'success': '¡Bienvenido a tu consultorio! Configuración inicial completada.', 'slug': cleaned_slug})
    except Exception as e:
        return jsonify({'error': f'Error al guardar configuración inicial: {str(e)}'}), 500

@app.route('/api/superadmin/therapists/<int:user_id>', methods=['DELETE'])
@login_required
def superadmin_delete_therapist(user_id):
    if session.get('role') != 'superadmin':
        return jsonify({'error': 'Acceso denegado. Se requieren permisos de superadministrador.'}), 403
        
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT id, username, nombres, apellidos FROM usuarios WHERE id = ? AND role = 'psicologo'", (user_id,))
    row = cursor.fetchone()
    if not row:
        return jsonify({'error': 'Psicólogo no encontrado.'}), 404
        
    try:
        # Cascade cleanup of all psychologist data
        cursor.execute("DELETE FROM pizarra_terapeutica WHERE paciente_id IN (SELECT id FROM pacientes WHERE psicologo_id = ?)", (user_id,))
        cursor.execute("DELETE FROM agenda_finanzas WHERE paciente_id IN (SELECT id FROM pacientes WHERE psicologo_id = ?)", (user_id,))
        cursor.execute("DELETE FROM sesiones WHERE paciente_id IN (SELECT id FROM pacientes WHERE psicologo_id = ?)", (user_id,))
        cursor.execute("DELETE FROM pacientes WHERE psicologo_id = ?", (user_id,))
        cursor.execute("DELETE FROM notificaciones WHERE user_id = ?", (user_id,))
        cursor.execute("DELETE FROM fcm_subscriptions WHERE user_id = ?", (user_id,))
        cursor.execute("DELETE FROM usuarios WHERE id = ?", (user_id,))
        db.commit()
        return jsonify({'success': f"Psicólogo '{row['nombres']} {row['apellidos']}' (@{row['username']}) y toda su información fueron eliminados con éxito."})
    except Exception as e:
        db.rollback()
        return jsonify({'error': f'Error al eliminar psicólogo: {str(e)}'}), 500

@app.route('/api/superadmin/therapists/<int:user_id>/toggle-subscription', methods=['POST'])
@login_required
def superadmin_toggle_subscription(user_id):
    if session.get('role') != 'superadmin':
        return jsonify({'error': 'Acceso denegado. Se requieren permisos de superadministrador.'}), 403
        
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT suscripcion_paga, nombres, apellidos FROM usuarios WHERE id = ? AND role = 'psicologo'", (user_id,))
    row = cursor.fetchone()
    if not row:
        return jsonify({'error': 'Psicólogo no encontrado.'}), 404
        
    new_sub = 1 if row['suscripcion_paga'] != 1 else 0
    # Al activar suscripción paga, activar también el usuario
    new_activo = 1 if new_sub == 1 else 1
    cursor.execute("UPDATE usuarios SET suscripcion_paga = ?, activo = ? WHERE id = ?", (new_sub, new_activo, user_id))
    db.commit()
    
    status_str = "Suscripción Paga Activada (Acceso Ilimitado)" if new_sub == 1 else "Cambiado a Modo Prueba (3 Días)"
    return jsonify({'success': f"Estado de {row['nombres']} {row['apellidos']} actualizado: {status_str}.", 'suscripcion_paga': new_sub})

def generate_default_slug_for_user(u):
    if not u:
        return ""
    if u['slug'] and u['slug'].strip():
        return u['slug'].strip()
    
    nom = (u['nombres'] or '').strip()
    ape = (u['apellidos'] or '').strip()
    uname = (u['username'] or '').strip()
    
    if nom or ape:
        combo = f"psic.{nom}{ape}"
    else:
        combo = f"psic.{uname}"
        
    import unicodedata, re
    normalized = unicodedata.normalize('NFD', combo)
    slug = re.sub(r'[\u0300-\u036f]', '', normalized).lower()
    slug = re.sub(r'[^a-z0-9\.]', '', slug)
    return slug or f"psic.{uname.lower()}"
