import os
import sys
import re
import sqlite3
import datetime
import shutil
import json
from flask import Flask, request, jsonify, session, send_file, redirect, url_for, g, render_template, render_template_string, Response
from werkzeug.security import generate_password_hash, check_password_hash
try:
    import docx
    from docx.shared import Inches, Pt
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False

# Google Calendar API imports
try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import Flow
    from googleapiclient.discovery import build
    from google.auth.transport.requests import Request
    GOOGLE_CALENDAR_AVAILABLE = True
except ImportError:
    GOOGLE_CALENDAR_AVAILABLE = False

VET_TZ = datetime.timezone(datetime.timedelta(hours=-4))

def get_now_vet():
    """Retorna datetime actual ajustado a la zona horaria de Venezuela (GMT-4)."""
    return datetime.datetime.now(VET_TZ)

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
IS_PA = os.path.exists('/home/Espacioterapeutico') or 'PYTHONANYWHERE_SITE' in os.environ
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SECURE'] = True if IS_PA else False
app.config['PERMANENT_SESSION_LIFETIME'] = datetime.timedelta(days=30)

# Registrar Blueprint del Módulo Corporativo / Clínicas
try:
    from routes_clinica import clinica_bp, ensure_clinica_tables
    app.register_blueprint(clinica_bp)
except Exception as _e:
    print("Aviso al registrar Blueprint de Clínicas:", _e)

import gzip

@app.after_request
def add_static_cache_and_gzip(response):
    if request.path.startswith('/static/'):
        response.headers['Cache-Control'] = 'public, max-age=86400'
    
    # Compresión Gzip automática para respuestas HTML, JS, CSS y JSON > 500 bytes
    accept_encoding = request.headers.get('Accept-Encoding', '')
    if (
        'gzip' in accept_encoding.lower()
        and response.status_code == 200
        and not response.direct_passthrough
        and 'Content-Encoding' not in response.headers
        and response.mimetype in ('text/html', 'text/css', 'text/javascript', 'application/javascript', 'application/json')
    ):
        try:
            data = response.get_data()
            if len(data) > 500:
                compressed_data = gzip.compress(data)
                response.set_data(compressed_data)
                response.headers['Content-Encoding'] = 'gzip'
                response.headers['Content-Length'] = str(len(compressed_data))
                response.headers['Vary'] = 'Accept-Encoding'
        except Exception:
            pass

    return response
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, 'clinica.db')
SCHEMA_FILE = get_resource_path('schema.sql')
CLIENT_SECRETS_FILE = os.path.join(BASE_DIR, "credentials.json")
SCOPES = ['https://www.googleapis.com/auth/calendar']

# Deshabilitar HTTPS obligatorio para OAuth en entorno local de desarrollo
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

import base64
_fernet_cipher_cache = None

def get_fernet_cipher():
    global _fernet_cipher_cache
    if _fernet_cipher_cache is None:
        try:
            import base64
            from cryptography.fernet import Fernet
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
            master_key = os.environ.get('SECRET_KEY', 'espacio_terapeutico_master_key_2026')
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=b'espacio_terapeutico_salt',
                iterations=100000,
            )
            fernet_key = base64.urlsafe_b64encode(kdf.derive(master_key.encode()))
            _fernet_cipher_cache = Fernet(fernet_key)
        except Exception as e:
            print(f"Error initializing Fernet: {e}")
            _fernet_cipher_cache = False
    return _fernet_cipher_cache if _fernet_cipher_cache else None

def encrypt_clinical_text(text):
    cipher = get_fernet_cipher()
    if not text or not cipher:
        return text or ""
    text_str = str(text)
    if text_str.startswith("enc:"):
        return text_str
    try:
        encrypted_bytes = cipher.encrypt(text_str.encode('utf-8'))
        return f"enc:{encrypted_bytes.decode('utf-8')}"
    except Exception as e:
        print(f"Error encrypting: {e}")
        return text_str

def decrypt_clinical_text(cipher_text):
    cipher = get_fernet_cipher()
    if not cipher_text or not isinstance(cipher_text, str) or not cipher:
        return cipher_text
    current = cipher_text
    while isinstance(current, str) and current.startswith("enc:"):
        try:
            raw_cipher = current[4:].encode('utf-8')
            decrypted_bytes = cipher.decrypt(raw_cipher)
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
            cursor.execute("SELECT token FROM fcm_subscriptions WHERE user_id = ?", (user_id,))
            tokens = [row['token'] for row in cursor.fetchall()]
        elif patient_id:
            cursor.execute("SELECT token FROM fcm_subscriptions WHERE patient_id = ?", (patient_id,))
            tokens = [row['token'] for row in cursor.fetchall()]
        else:
            return

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
                            "renotify": False,
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
        db = g._database = sqlite3.connect(DATABASE, timeout=30.0)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

CURRENT_SCHEMA_VER = "14"

def init_db():
    db = sqlite3.connect(DATABASE, timeout=30.0)
    cursor = db.cursor()
    
    # Always ensure demo user is seeded
    try:
        ensure_demo_user(db)
    except Exception as _e:
        print("Aviso al verificar usuario demo:", _e)

    try:
        from routes_clinica import ensure_clinica_tables
        ensure_clinica_tables(db)
    except Exception as _e:
        print("Aviso al asegurar tablas de clínica:", _e)

    # Verificar si la tabla principal 'usuarios' existe
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='usuarios'")
    exists = cursor.fetchone()
    
    if not exists:
        with open(SCHEMA_FILE, 'r', encoding='utf-8') as f:
            db.executescript(f.read())
        db.commit()
    else:
        # Si ya existe usuarios y la versión de esquema está actualizada, saltar migraciones pesadas
        try:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='configuracion'")
            if cursor.fetchone():
                cursor.execute("SELECT valor FROM configuracion WHERE clave = 'schema_version'")
                ver_row = cursor.fetchone()
                if ver_row and ver_row[0] == CURRENT_SCHEMA_VER:
                    db.close()
                    return
        except Exception:
            pass
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
        if 'bloqueo_herramientas' not in cols_usr:
            cursor.execute("ALTER TABLE usuarios ADD COLUMN bloqueo_herramientas INTEGER DEFAULT 1")
        if 'bloqueo_confirmaciones' not in cols_usr:
            cursor.execute("ALTER TABLE usuarios ADD COLUMN bloqueo_confirmaciones INTEGER DEFAULT 1")
        if 'bloqueo_examen_mental' not in cols_usr:
            cursor.execute("ALTER TABLE usuarios ADD COLUMN bloqueo_examen_mental INTEGER DEFAULT 0")
        if 'bloqueo_tests' not in cols_usr:
            cursor.execute("ALTER TABLE usuarios ADD COLUMN bloqueo_tests INTEGER DEFAULT 0")
        
        cursor.execute("UPDATE usuarios SET bloqueo_tests = 0 WHERE bloqueo_tests IS NULL OR bloqueo_tests = 1")
        cursor.execute("UPDATE usuarios SET bloqueo_examen_mental = 0 WHERE bloqueo_examen_mental IS NULL OR bloqueo_examen_mental = 1")
        if 'terminos_condiciones' not in cols_usr:
            cursor.execute("ALTER TABLE usuarios ADD COLUMN terminos_condiciones TEXT")
        if 'nomenclatura' not in cols_usr:
            cursor.execute("ALTER TABLE usuarios ADD COLUMN nomenclatura TEXT DEFAULT 'Psicólogo Clínico'")
        if 'descripcion_biografia' not in cols_usr:
            cursor.execute("ALTER TABLE usuarios ADD COLUMN descripcion_biografia TEXT DEFAULT ''")
        if 'modalidades_json' not in cols_usr:
            cursor.execute("ALTER TABLE usuarios ADD COLUMN modalidades_json TEXT DEFAULT '[\"Online\", \"Presencial\"]'")
        if 'whatsapp_publico' not in cols_usr:
            cursor.execute("ALTER TABLE usuarios ADD COLUMN whatsapp_publico TEXT DEFAULT ''")
        if 'email_publico' not in cols_usr:
            cursor.execute("ALTER TABLE usuarios ADD COLUMN email_publico TEXT DEFAULT ''")
        if 'redes_sociales_json' not in cols_usr:
            cursor.execute("ALTER TABLE usuarios ADD COLUMN redes_sociales_json TEXT DEFAULT '{}'")
        if 'pregunta_seguridad_1' not in cols_usr:
            cursor.execute("ALTER TABLE usuarios ADD COLUMN pregunta_seguridad_1 TEXT")
        if 'respuesta_seguridad_1_hash' not in cols_usr:
            cursor.execute("ALTER TABLE usuarios ADD COLUMN respuesta_seguridad_1_hash TEXT")
        if 'pregunta_seguridad_2' not in cols_usr:
            cursor.execute("ALTER TABLE usuarios ADD COLUMN pregunta_seguridad_2 TEXT")
        if 'respuesta_seguridad_2_hash' not in cols_usr:
            cursor.execute("ALTER TABLE usuarios ADD COLUMN respuesta_seguridad_2_hash TEXT")
        if 'especialidades' not in cols_usr:
            cursor.execute("ALTER TABLE usuarios ADD COLUMN especialidades TEXT DEFAULT ''")
        if 'poblaciones_json' not in cols_usr:
            cursor.execute("ALTER TABLE usuarios ADD COLUMN poblaciones_json TEXT DEFAULT '[\"Adultos\", \"Adolescentes\"]'")
        if 'pais_ubicacion' not in cols_usr:
            cursor.execute("ALTER TABLE usuarios ADD COLUMN pais_ubicacion TEXT DEFAULT ''")
        if 'clinica_id' not in cols_usr:
            cursor.execute("ALTER TABLE usuarios ADD COLUMN clinica_id INTEGER")
        if 'tipo_clinica' not in cols_usr:
            cursor.execute("ALTER TABLE usuarios ADD COLUMN tipo_clinica INTEGER DEFAULT 0")
        db.commit()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS clinicas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            slug TEXT UNIQUE NOT NULL,
            codigo_clinica TEXT UNIQUE NOT NULL,
            logo TEXT,
            descripcion TEXT,
            admin_id INTEGER NOT NULL,
            modo_whatsapp TEXT DEFAULT 'centralizado',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS solicitudes_clinica (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            clinica_id INTEGER NOT NULL,
            usuario_id INTEGER NOT NULL,
            tipo_solicitud TEXT NOT NULL, -- 'invitacion' o 'solicitud'
            estado TEXT DEFAULT 'pendiente', -- 'pendiente', 'aceptado', 'rechazado'
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
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
        
    # Migración de columnas en pacientes
    cursor.execute("PRAGMA table_info(pacientes)")
    cols_pac = [row[1] for row in cursor.fetchall()]
    if 'metodos_pago' not in cols_pac:
        try:
            cursor.execute("ALTER TABLE pacientes ADD COLUMN metodos_pago TEXT DEFAULT '[]'")
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
    # Sincronización de clave para Pamoraro si no coincide con Psicodrama.26
    try:
        cursor.execute("SELECT id, password_hash FROM usuarios WHERE LOWER(username) = 'pamoraro'")
        pam_u = cursor.fetchone()
        if pam_u and pam_u['password_hash']:
            if not check_password_hash(pam_u['password_hash'], 'Psicodrama.26'):
                cursor.execute("UPDATE usuarios SET password_hash = ? WHERE id = ?", (generate_password_hash('Psicodrama.26'), pam_u['id']))
                db.commit()
    except Exception:
        pass

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
        if 'zona_horaria' not in cols_pac:
            cursor.execute("ALTER TABLE pacientes ADD COLUMN zona_horaria TEXT DEFAULT 'America/Caracas'")
        if 'utc_offset' not in cols_pac:
            cursor.execute("ALTER TABLE pacientes ADD COLUMN utc_offset INTEGER DEFAULT 240")
        
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
        if 'confirmacion_enviada_wa' not in cols_fin:
            cursor.execute("ALTER TABLE agenda_finanzas ADD COLUMN confirmacion_enviada_wa INTEGER DEFAULT 0")
        if 'recordatorio_enviado_wa' not in cols_fin:
            cursor.execute("ALTER TABLE agenda_finanzas ADD COLUMN recordatorio_enviado_wa INTEGER DEFAULT 0")
        if 'reagendamiento_enviado_wa' not in cols_fin:
            cursor.execute("ALTER TABLE agenda_finanzas ADD COLUMN reagendamiento_enviado_wa INTEGER DEFAULT 0")
        if 'cierre_enviado_wa' not in cols_fin:
            cursor.execute("ALTER TABLE agenda_finanzas ADD COLUMN cierre_enviado_wa INTEGER DEFAULT 0")
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
    # Migración automática de citas (recordatorio_enviado_wa y confirmacion_enviada_wa)
    cursor.execute("PRAGMA table_info(citas)")
    cols_citas = [row[1] for row in cursor.fetchall()]
    if cols_citas:
        if 'recordatorio_enviado_wa' not in cols_citas:
            cursor.execute("ALTER TABLE citas ADD COLUMN recordatorio_enviado_wa INTEGER DEFAULT 0")
        if 'confirmacion_enviada_wa' not in cols_citas:
            cursor.execute("ALTER TABLE citas ADD COLUMN confirmacion_enviada_wa INTEGER DEFAULT 0")
        if 'reagendamiento_enviado_wa' not in cols_citas:
            cursor.execute("ALTER TABLE citas ADD COLUMN reagendamiento_enviado_wa INTEGER DEFAULT 0")
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
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS registro_consumo_pantalla (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id INTEGER NOT NULL,
            fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            dispositivos TEXT,
            tiempo_uso TEXT,
            aplicaciones TEXT,
            tipo_contenido TEXT,
            estado_emocional_posterior TEXT,
            interferencia_actividad TEXT,
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
        if 'respuesta_psicologo' not in cols_piz:
            cursor.execute("ALTER TABLE pizarra_terapeutica ADD COLUMN respuesta_psicologo TEXT")
        if 'fecha_respuesta' not in cols_piz:
            cursor.execute("ALTER TABLE pizarra_terapeutica ADD COLUMN fecha_respuesta TEXT")
    db.commit()

    # Tabla de Bloqueos de Agenda Específicos (Eventos Personales / Convocatorias)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bloqueos_agenda_especificos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            psicologo_id INTEGER NOT NULL,
            fecha TEXT NOT NULL,
            hora_inicio TEXT,
            hora_fin TEXT,
            motivo TEXT,
            todo_el_dia INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (psicologo_id) REFERENCES usuarios(id) ON DELETE CASCADE
        )
    """)
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
    cursor.execute("UPDATE notificaciones SET user_id = 1 WHERE user_id IS NULL")
    try:
        cursor.execute("DELETE FROM notificaciones WHERE tipo = 'cumpleanos_wa'")
    except Exception:
        pass
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

    # Tablas para Módulos Terapéuticos Personalizados (Sueño, Ansiedad, Sobriedad)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS modulos_terapeuticos_paciente (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id INTEGER NOT NULL,
            modulo_clave TEXT NOT NULL,
            activo INTEGER DEFAULT 1,
            configuracion_json TEXT,
            fecha_asignacion DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (paciente_id) REFERENCES pacientes(id) ON DELETE CASCADE,
            UNIQUE(paciente_id, modulo_clave)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS registros_sueno (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id INTEGER NOT NULL,
            fecha TEXT NOT NULL,
            situaciones_dia TEXT,
            emociones_dia TEXT,
            proceso_dormir TEXT,
            hora_dormi TEXT,
            desperto_noche INTEGER DEFAULT 0,
            cant_despertares INTEGER DEFAULT 0,
            hora_desperto TEXT,
            senti_descanso INTEGER DEFAULT 1,
            somnolencia_dia INTEGER DEFAULT 0,
            pesadez_dia INTEGER DEFAULT 0,
            agotamiento_dia INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (paciente_id) REFERENCES pacientes(id) ON DELETE CASCADE,
            UNIQUE(paciente_id, fecha)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS registros_ansiedad (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id INTEGER NOT NULL,
            fecha TEXT NOT NULL,
            nivel_ansiedad INTEGER NOT NULL,
            sintomas_json TEXT,
            situacion_desencadenante TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (paciente_id) REFERENCES pacientes(id) ON DELETE CASCADE,
            UNIQUE(paciente_id, fecha)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS registros_sobriedad (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id INTEGER NOT NULL,
            fecha TEXT NOT NULL,
            sobrio INTEGER NOT NULL,
            nivel_ansiedad INTEGER,
            disparador_emocional TEXT,
            notas TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (paciente_id) REFERENCES pacientes(id) ON DELETE CASCADE,
            UNIQUE(paciente_id, fecha)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS adherencia_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id INTEGER NOT NULL,
            nombre_medicamento TEXT NOT NULL,
            dosis TEXT,
            hora_prescrita TEXT,
            activo INTEGER DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (paciente_id) REFERENCES pacientes(id) ON DELETE CASCADE
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS adherencia_registros (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id INTEGER NOT NULL,
            medicamento_id INTEGER NOT NULL,
            fecha TEXT NOT NULL,
            tomado INTEGER NOT NULL,
            hora_tomado TEXT,
            notas TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (paciente_id) REFERENCES pacientes(id) ON DELETE CASCADE,
            FOREIGN KEY (medicamento_id) REFERENCES adherencia_medicamentos(id) ON DELETE CASCADE,
            UNIQUE(paciente_id, medicamento_id, fecha)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS activacion_actividades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id INTEGER NOT NULL,
            psicologo_id INTEGER,
            categoria TEXT NOT NULL,
            nombre_actividad TEXT NOT NULL,
            activa INTEGER DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (paciente_id) REFERENCES pacientes(id) ON DELETE CASCADE
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS activacion_registros (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id INTEGER NOT NULL,
            actividad_id INTEGER NOT NULL,
            fecha TEXT NOT NULL,
            completada INTEGER NOT NULL,
            notas TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (paciente_id) REFERENCES pacientes(id) ON DELETE CASCADE,
            FOREIGN KEY (actividad_id) REFERENCES activacion_actividades(id) ON DELETE CASCADE,
            UNIQUE(paciente_id, actividad_id, fecha)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS registros_ingesta (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id INTEGER NOT NULL,
            fecha TEXT NOT NULL,
            tipo_comida TEXT NOT NULL,
            descripcion_plato TEXT,
            apetito_previo INTEGER DEFAULT 5,
            saciedad INTEGER DEFAULT 5,
            contexto TEXT,
            afectividad TEXT,
            pensamiento TEXT,
            conductas_json TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (paciente_id) REFERENCES pacientes(id) ON DELETE CASCADE
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS registros_cognitivos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id INTEGER NOT NULL,
            fecha TEXT NOT NULL,
            situacion TEXT NOT NULL,
            pensamiento TEXT NOT NULL,
            emocion_sensacion TEXT,
            conducta TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (paciente_id) REFERENCES pacientes(id) ON DELETE CASCADE
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS configuracion (
            clave TEXT PRIMARY KEY,
            valor TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS examenes_mentales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            psicologo_id INTEGER NOT NULL,
            paciente_id INTEGER NOT NULL,
            fecha_evaluacion TEXT NOT NULL,
            medio_evaluacion TEXT NOT NULL,
            datos_evaluacion_json TEXT NOT NULL,
            observaciones_generales TEXT,
            fecha_registro DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (psicologo_id) REFERENCES usuarios(id) ON DELETE CASCADE,
            FOREIGN KEY (paciente_id) REFERENCES pacientes(id) ON DELETE CASCADE
        )
    """)
    
    # Parche automático de migración y normalización de datos para bases de datos viejas o restauradas
    try:
        cursor.execute("""
            UPDATE agenda_finanzas 
            SET control_uso = 'Consumida' 
            WHERE estado_pago = 'Paga' 
              AND (tipo_consulta IS NULL OR (tipo_consulta NOT LIKE '%Prepago%' AND tipo_consulta NOT LIKE '%Paquete%'))
        """)
        cursor.execute("UPDATE pacientes SET terminos_aceptados = 0 WHERE terminos_aceptados IS NULL")
        cursor.execute("UPDATE pacientes SET psicologo_id = 1 WHERE psicologo_id IS NULL")
        ensure_usuarios_columns(db)
        ensure_tests_tables(db)

        def_landing_defaults = [
            ('landing_hero_title', 'Espacio Terapéutico'),
            ('landing_hero_subtitle', 'Red Profesional de Salud Mental y Gestión Clínica Integrada'),
            ('landing_quienes_somos', 'Somos una red de profesionales de la psicología enfocados en brindar acompañamiento terapéutico humano, ético y accesible. Nuestra plataforma integra tecnología avanzada para garantizar privacidad, agendamiento en vivo 24/7 y seguimiento personalizado en cada etapa del proceso.'),
            ('landing_mision', 'Promover el bienestar emocional y la salud mental ofreciendo espacios terapéuticos seguros, accesibles y profesionales, apoyados en herramientas clínicas digitales de vanguardia.'),
            ('landing_vision', 'Consolidarnos como la red de salud mental de referencia, conectando a consultantes con terapeutas altamente calificados a través de un ecosistema clínico seguro, transparente y accesible.'),
            ('landing_footer_text', 'Espacio Terapéutico — Todos los derechos reservados.')
        ]
        for key_d, val_d in def_landing_defaults:
            cursor.execute("INSERT OR IGNORE INTO configuracion (clave, valor) VALUES (?, ?)", (key_d, val_d))
        
        ensure_demo_user(db)
    except Exception as _patch_err:
        print(f"Aviso en parche de datos automático: {_patch_err}")

    cursor.execute("INSERT OR REPLACE INTO configuracion (clave, valor) VALUES ('schema_version', ?)", (CURRENT_SCHEMA_VER,))
    db.commit()
        
    db.close()

def ensure_demo_user(db):
    try:
        cursor = db.cursor()
        cursor.execute("SELECT id FROM usuarios WHERE username = 'psicologa.valeria'")
        row = cursor.fetchone()
        if row:
            return
        
        from werkzeug.security import generate_password_hash
        from datetime import datetime, timedelta
        
        psychologist_username = "psicologa.valeria"
        psychologist_pass = "Prueba2026!"
        psychologist_pass_hash = generate_password_hash(psychologist_pass)

        disponibilidad_json = json.dumps({
            "Lunes": ["08:00", "09:00", "10:00", "11:00", "14:00", "15:00", "16:00"],
            "Miércoles": ["08:00", "09:00", "10:00", "11:00", "14:00", "15:00", "16:00"],
            "Viernes": ["08:00", "09:00", "10:00", "11:00", "14:00", "15:00"]
        }, ensure_ascii=False)

        visual_cfg_json = json.dumps({
            "dias_laborables": ["Lunes", "Miércoles", "Viernes"],
            "hora_inicio": "08:00",
            "hora_fin": "17:00",
            "duracion_sesion": 50,
            "descanso": 10
        }, ensure_ascii=False)

        metodos_pago_json = json.dumps([
            {"tipo": "Pago Móvil", "banco": "Banco de Venezuela (0102)", "cedula": "V-18492019", "telefono": "0414-1234567"},
            {"tipo": "Zelle", "email": "valeria.mendoza.psico@gmail.com", "titular": "Valeria Mendoza"}
        ], ensure_ascii=False)

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        expiry_str = (datetime.now() + timedelta(days=365)).strftime("%Y-%m-%d %H:%M:%S")
        avatar_rel_url = "/static/uploads/psicologo_prueba_avatar.jpg"

        cursor.execute("""
            INSERT INTO usuarios (
                username, password_hash, nombres, apellidos, estudios, federacion,
                foto_titulo, role, activo, fecha_registro, fecha_expiracion_prueba,
                suscripcion_paga, slug, disponibilidad_horarios, configuracion_horarios_visual, metodos_pago
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'psicologo', 1, ?, ?, 1, 'psicologa-valeria-mendoza', ?, ?, ?)
        """, (
            psychologist_username,
            psychologist_pass_hash,
            "Valeria Sofía",
            "Mendoza Rivas",
            "Psicóloga Clínica - Especialista en Terapia Cognitivo-Conductual (TCC), Manejo de Ansiedad y Regulación Emocional",
            "FPV-18492",
            avatar_rel_url,
            now_str,
            expiry_str,
            disponibilidad_json,
            visual_cfg_json,
            metodos_pago_json
        ))
        psych_id = cursor.lastrowid

        patient_username = "camila.perez"
        patient_pass = "Paciente2026!"
        patient_pass_hash = generate_password_hash(patient_pass)

        cursor.execute("""
            INSERT INTO pacientes (
                nombres, apellidos, cedula, pronombre, genero, edad, lugar_nacimiento, fecha_nacimiento,
                residencia_actual, con_quien_reside, nivel_academico, ocupacion, estado_civil, telefono, email,
                antecedentes_medicos_familiares, antecedentes_medicos_personales, antecedentes_psicologicos_familiares,
                antecedentes_psicologicos_personales, asistencia_previa_psicologo, motivo_consulta, expectativas,
                farmacologia, contacto_emergencia_nombre, contacto_emergencia_parentesco, diagnostico,
                username, password_hash, fecha_registro, psicologo_id
            ) VALUES (
                'Camila Andrea', 'Pérez Castillo', 'V-24891023', 'Ella', 'Femenino', 26, 'Caracas', '1999-11-14',
                'Caracas, Venezuela', 'Pareja', 'Licenciatura', 'Diseñadora Gráfica Freelance', 'En relación', '0424-9876543', 'camila.perez.prueba@gmail.com',
                'Hipertensión arterial en rama materna.', 'Sin patologías crónicas. Cuadros migrañosos ocasionales.', 'Madre con antecedentes de ansiedad y somatización.',
                'Estrés académico moderado en 2022 durante entrega de tesis.', 'Sí, 4 sesiones en 2022 por orientación vocacional.', 'Siento episodios de angustia intensa y síntomas físicos de ansiedad (taquicardia, opresión en el pecho) ante entregas de proyectos bajo presión con clientes. Dificultad para conciliar el sueño por pensamientos rumiantes sobre el rendimiento.', 'Aprender técnicas efectivas de autorregulación emocional, reestructurar pensamientos de autoexigencia y mejorar la calidad del descanso.',
                'Ninguna en la actualidad.', 'Carlos Eduardo Pérez', 'Hermano', 'Trastorno de Ansiedad Generalizada (TAG) leve con rasgos de perfeccionismo disfuncional (CIE-10: F41.1)',
                ?, ?, ?, ?
            )
        """, (patient_username, patient_pass_hash, now_str, psych_id))
        patient_id = cursor.lastrowid

        past_date = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
        cursor.execute("""
            INSERT INTO sesiones (
                paciente_id, fecha, modalidad, estado, resumen, tareas_asignadas,
                recursos_entregados, anotaciones_proxima, compromisos_psicologo, diagnostico
            ) VALUES (?, ?, 'Online', 'Realizada', ?, ?, ?, ?, ?, ?)
        """, (
            patient_id,
            past_date,
            "Evaluación inicial y psicoeducación sobre la curva de ansiedad. La consultante expresa elevada autoexigencia ante plazos de entrega. Se aplicó escala HAD-A (puntaje 11/21 - Ansiedad Leve/Moderada). Se identifican pensamientos automáticos distorsionados de tipo 'todo o nada'.",
            "1) Registro diario de pensamientos automáticos en el módulo cognitivo. 2) Respiración diafragmática 4-7-8 durante 5 minutos antes de dormir.",
            "Guía PDF en Higiene del Sueño y Plantilla de Reestructuración Cognitiva.",
            "Revisar registros de ansiedad y sueño, profundizar en creencias nucleares de perfeccionismo.",
            "Enviar recordatorio de la guía de sueño por la plataforma.",
            "Trastorno de Ansiedad Generalizada (TAG) leve (F41.1)"
        ))

        next_date = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")
        cursor.execute("""
            INSERT INTO agenda_finanzas (
                paciente_id, fecha, hora, tipo_consulta, monto, moneda, estado_pago, confirmada, metodo_pago
            ) VALUES (?, ?, '10:00 AM', 'Terapia Individual Online', 35.00, 'USD', 'Pagado', 1, 'Zelle')
        """, (patient_id, next_date))

        for tool_clave in ['sueno', 'ansiedad', 'pantalla']:
            cursor.execute("""
                INSERT INTO modulos_terapeuticos_paciente (paciente_id, modulo_clave, activo, fecha_asignacion)
                VALUES (?, ?, 1, ?)
            """, (patient_id, tool_clave, now_str))

        db.commit()
    except Exception as _demo_err:
        print(f"Aviso en ensure_demo_user: {_demo_err}")

_db_initialized_flag = False

@app.before_request
def ensure_db_initialized():
    global _db_initialized_flag
    if not _db_initialized_flag:
        _db_initialized_flag = True
        import threading
        def _async_init():
            try:
                init_db()
                restore_patients_from_firebase()
                # Sincronizar automáticamente los IDs de las sesiones ya existentes hacia Firebase
                sync_all_psychologist_patients_to_firebase(1)
            except Exception as _db_err:
                print(f"Advertencia al inicializar BD: {_db_err}")
        threading.Thread(target=_async_init, daemon=True).start()

FIREBASE_DB_URL = "https://espacio-terapeutico-default-rtdb.firebaseio.com"

def notify_patient_firebase(patient_id, titulo, mensaje, link='#', icon='🔔'):
    """Envía una notificación en tiempo real al portal del consultante vía Firebase Realtime DB."""
    def _send():
        try:
            import requests
            from datetime import datetime
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            fb_payload = {
                'titulo': titulo,
                'mensaje': mensaje,
                'fecha': now_str,
                'leida': False,
                'link': link,
                'icon': icon
            }
            requests.post(f"{FIREBASE_DB_URL}/pacientes/{patient_id}/notificaciones.json", json=fb_payload, timeout=3.0)
        except Exception as e:
            print(f"Error en notify_patient_firebase (paciente #{patient_id}): {e}")
    import threading
    threading.Thread(target=_send, daemon=True).start()

def restore_patients_from_firebase():
    """Restaura y sincroniza consultantes desde Firebase Realtime Database a SQLite."""
    try:
        import urllib.request
        import json
        req = urllib.request.Request(f"{FIREBASE_DB_URL}/pacientes.json")
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            fb_data = json.loads(resp.read().decode('utf-8'))
        if not fb_data or not isinstance(fb_data, dict):
            return
            
        conn = sqlite3.connect(DATABASE, timeout=30.0)
        c = conn.cursor()
        for pid_str, pinfo in fb_data.items():
            if pid_str == 'undefined' or not isinstance(pinfo, dict):
                continue
            try:
                pid = int(pid_str)
            except:
                continue
            
            perfil = pinfo.get('perfil', {})
            if not perfil:
                continue
                
            nombres = perfil.get('nombres', '')
            apellidos = perfil.get('apellidos', '')
            cedula = perfil.get('cedula', '')
            username = perfil.get('username', '')
            password_hash = perfil.get('password_hash', None)
            p1 = perfil.get('pregunta_seguridad_1', None)
            r1 = perfil.get('respuesta_seguridad_1_hash', None)
            p2 = perfil.get('pregunta_seguridad_2', None)
            r2 = perfil.get('respuesta_seguridad_2_hash', None)
            telefono = perfil.get('telefono', None)
            email = perfil.get('email', None)
            
            c.execute("SELECT id FROM pacientes WHERE id = ?", (pid,))
            row = c.fetchone()
            if not row:
                c.execute("""
                    INSERT INTO pacientes (
                        id, nombres, apellidos, cedula, username, password_hash,
                        pregunta_seguridad_1, respuesta_seguridad_1_hash,
                        pregunta_seguridad_2, respuesta_seguridad_2_hash,
                        telefono, email, psicologo_id, fecha_registro
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, CURRENT_TIMESTAMP)
                """, (pid, nombres, apellidos, cedula, username, password_hash, p1, r1, p2, r2, telefono, email))
            else:
                c.execute("""
                    UPDATE pacientes SET 
                        psicologo_id = COALESCE(psicologo_id, 1),
                        nombres = CASE WHEN ? != '' THEN ? ELSE nombres END,
                        apellidos = CASE WHEN ? != '' THEN ? ELSE apellidos END,
                        username = CASE WHEN ? != '' THEN ? ELSE username END,
                        password_hash = COALESCE(password_hash, ?),
                        pregunta_seguridad_1 = COALESCE(pregunta_seguridad_1, ?),
                        respuesta_seguridad_1_hash = COALESCE(respuesta_seguridad_1_hash, ?),
                        pregunta_seguridad_2 = COALESCE(pregunta_seguridad_2, ?),
                        respuesta_seguridad_2_hash = COALESCE(respuesta_seguridad_2_hash, ?)
                    WHERE id = ?
                """, (nombres, nombres, apellidos, apellidos, username, username, password_hash, p1, r1, p2, r2, pid))
            # Reconciliar citas completadas desde Firebase si se restauró una base de datos antigua
            citas_completadas = pinfo.get('citas_completadas', [])
            if isinstance(citas_completadas, list) and len(citas_completadas) > 0:
                for ag_id in citas_completadas:
                    if isinstance(ag_id, int):
                        c.execute("SELECT id FROM sesiones WHERE agenda_id = ?", (ag_id,))
                        if not c.fetchone():
                            c.execute("SELECT paciente_id, fecha, modalidad FROM agenda_finanzas WHERE id = ?", (ag_id,))
                            ag_row = c.fetchone()
                            if ag_row:
                                c.execute("""
                                    INSERT INTO sesiones (paciente_id, agenda_id, fecha, modalidad, resumen, estado)
                                    VALUES (?, ?, ?, ?, 'Sesión realizada (Reconciliada automáticamente desde respaldo Firebase)', 'Realizada')
                                """, (ag_row[0], ag_id, ag_row[1], ag_row[2] or 'Online'))

        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error restaurando consultantes desde Firebase: {e}")

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
            SELECT af.id, af.paciente_id, af.fecha, af.hora, af.tipo_consulta, af.google_event_id, p.nombres, p.apellidos, p.psicologo_id
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
            target_psic = appt['psicologo_id'] or 1
            
            # 1. Eliminar de Google Calendar
            if google_event_id:
                try:
                    service = get_calendar_service(target_psic)
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
                INSERT INTO notificaciones (user_id, tipo, titulo, mensaje, fecha, leida, link)
                VALUES (?, ?, ?, ?, ?, 0, ?)
            """, (
                target_psic,
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
    No se ejecutan fuera del horario laboral (10:00 PM a 7:59 AM).
    """
    from datetime import datetime, timezone, timedelta
    try:
        import zoneinfo
        tz = zoneinfo.ZoneInfo("America/Caracas")
        now_dt = datetime.now(tz)
    except Exception:
        tz = timezone(timedelta(hours=-4))
        now_dt = datetime.now(tz)

    if now_dt.hour < 8 or now_dt.hour >= 22:
        return

    cursor = db.cursor()
    try:
        import requests
        today_str = now_dt.strftime("%Y-%m-%d")
        
        # Buscar citas agendadas para el día de hoy no canceladas
        cursor.execute("""
            SELECT af.id, af.paciente_id, af.fecha, af.hora, af.tipo_consulta, p.nombres, p.apellidos, p.psicologo_id
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
            target_psic = appt['psicologo_id'] or 1
            
            # Evitar enviar más de 1 recordatorio al día por la misma cita
            cursor.execute("SELECT id FROM notificaciones WHERE link = ?", (notif_link,))
            if cursor.fetchone():
                continue
                
            # 1. Notificación al psicólogo
            cursor.execute("""
                INSERT INTO notificaciones (user_id, tipo, titulo, mensaje, fecha, leida, link)
                VALUES (?, 'cita', '⏰ Recordatorio de Consulta Hoy', ?, ?, 0, ?)
            """, (
                target_psic,
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
    No se ejecutan fuera del horario laboral (10:00 PM a 7:59 AM).
    """
    from datetime import datetime, timezone, timedelta
    try:
        import zoneinfo
        tz = zoneinfo.ZoneInfo("America/Caracas")
        now_dt = datetime.now(tz)
    except Exception:
        tz = timezone(timedelta(hours=-4))
        now_dt = datetime.now(tz)

    if now_dt.hour < 8 or now_dt.hour >= 22:
        return

    cursor = db.cursor()
    try:
        import requests, json
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

def auto_check_patient_birthdays(db, force=False, target_patient_id=None):
    """
    Verifica si algún consultante cumple años el día de hoy y genera
    una notificación en el panel del psicólogo asignado y mensaje por WhatsApp.
    """
    cursor = db.cursor()
    try:
        from datetime import datetime, timezone, timedelta
        try:
            import zoneinfo
            tz = zoneinfo.ZoneInfo("America/Caracas")
            now_dt = datetime.now(tz)
        except Exception:
            tz = timezone(timedelta(hours=-4))
            now_dt = datetime.now(tz)

        today_md = now_dt.strftime("%m-%d")
        today_str = now_dt.strftime("%Y-%m-%d")
        now_str = now_dt.strftime("%Y-%m-%d %H:%M:%S")

        if force:
            if target_patient_id:
                cursor.execute("""
                    DELETE FROM notificaciones
                    WHERE tipo IN ('cumpleanos', 'cumpleanos_wa')
                    AND (fecha LIKE ? OR fecha IS NULL)
                    AND (mensaje LIKE ? OR mensaje LIKE '%Venuska%')
                """, (f"{today_str}%", f"%ID: {target_patient_id}%"))
            else:
                cursor.execute("""
                    DELETE FROM notificaciones
                    WHERE tipo IN ('cumpleanos', 'cumpleanos_wa')
                    AND (fecha LIKE ? OR fecha IS NULL)
                """, (f"{today_str}%",))
            db.commit()

        cursor.execute("SELECT clave, valor FROM configuracion WHERE clave IN ('msg_cumpleanos', 'auto_cumpleanos_activo')")
        cfg_rows = {r['clave']: r['valor'] for r in cursor.fetchall()}
        auto_cumple_activo = cfg_rows.get('auto_cumpleanos_activo', '1') == '1'
        tmpl_cumple_default = cfg_rows.get('msg_cumpleanos') or "¡Feliz cumpleaños, *{nombre}*! 🎉 🎂\n\nTe deseo un excelente día lleno de bienestar, paz y alegría."

        cursor.execute("""
            SELECT id, nombres, apellidos, fecha_nacimiento, telefono, psicologo_id
            FROM pacientes
            WHERE fecha_nacimiento IS NOT NULL AND fecha_nacimiento != ''
        """)
        patients = cursor.fetchall()
        for p in patients:
            dob_str = str(p['fecha_nacimiento']).strip()
            if not dob_str:
                continue
            dob_norm = normalize_date_str(dob_str)
            if len(dob_norm) >= 10 and dob_norm[5:10] == today_md:
                psic_id = p['psicologo_id'] or 1
                pac_id = p['id']
                pac_nombre = f"{p['nombres']} {p['apellidos']}".strip()
                first_name = p['nombres'].strip().split()[0] if p['nombres'] else 'Consultante'
                notif_msg = f"¡Hoy es el cumpleaños de {pac_nombre}! Deséale un feliz día."

                # 1. Notificación interna
                cursor.execute("""
                    SELECT id FROM notificaciones
                    WHERE user_id = ? AND tipo = 'cumpleanos' AND mensaje LIKE ? AND fecha LIKE ?
                """, (psic_id, f"%{pac_nombre}%", f"{today_str}%"))

                if not cursor.fetchone():
                    cursor.execute("""
                        INSERT INTO notificaciones (user_id, tipo, titulo, mensaje, fecha, leida, link)
                        VALUES (?, 'cumpleanos', '🎉 Cumpleaños de Consultante', ?, ?, 0, '/#agenda')
                    """, (psic_id, notif_msg, now_str))
                    db.commit()

                    try:
                        send_webpush_notification(
                            user_id=psic_id,
                            title="🎉 Cumpleaños de Consultante",
                            body=notif_msg,
                            url="/#agenda"
                        )
                    except Exception:
                        pass

                # 2. Envío de WhatsApp automático de Feliz Cumpleaños (si el interruptor está activo)
                if auto_cumple_activo and p['telefono']:
                    cursor.execute("""
                        SELECT id FROM notificaciones
                        WHERE user_id = ? AND tipo = 'cumpleanos_wa' AND mensaje LIKE ? AND fecha LIKE ?
                    """, (psic_id, f"%ID: {pac_id}%", f"{today_str}%"))
                    
                    if not cursor.fetchone():
                        msg_wa = tmpl_cumple_default.replace('{nombre}', first_name).replace('{nombre_completo}', pac_nombre)
                        try:
                            res = make_wa_http_request('POST', '/send', json_data={'phone': p['telefono'], 'text': msg_wa, 'user_id': psic_id}, timeout=15, user_id=psic_id)
                            if res and res.status_code == 200:
                                wa_log_msg = f"Mensaje de cumpleaños enviado por WhatsApp a {pac_nombre} (ID: {pac_id})"
                                cursor.execute("""
                                    INSERT INTO notificaciones (user_id, tipo, titulo, mensaje, fecha, leida, link)
                                    VALUES (?, 'cumpleanos_wa', '🎂 WhatsApp de Cumpleaños Enviado', ?, ?, 1, '')
                                """, (psic_id, wa_log_msg, now_str))
                                db.commit()
                        except Exception as ex_wa:
                            print(f"Error al enviar WhatsApp de cumpleaños a {pac_nombre}:", ex_wa)
    except Exception as e:
        print("Error en auto_check_patient_birthdays:", e)

# ==========================================
# ENVÍO DE CORREOS ELECTRÓNICOS SMTP (@espacioterapeutico.net)
# ==========================================
def send_email_async(to_email, subject, html_content, text_content=None):
    """
    Envía un correo electrónico de forma asíncrona mediante SMTP configurado en BD.
    No bloquea la ejecución principal del servidor.
    """
    if not to_email or '@' not in str(to_email):
        return

    def _worker():
        try:
            with app.app_context():
                db = get_db()
                cursor = db.cursor()
                cursor.execute("""
                    SELECT clave, valor FROM configuracion 
                    WHERE clave IN ('smtp_host', 'smtp_port', 'smtp_user', 'smtp_password', 'smtp_from_email')
                """)
                cfg = {r['clave']: r['valor'] for r in cursor.fetchall()}

                smtp_host = cfg.get('smtp_host', '').strip() or 'smtp.gmail.com'
                smtp_port_raw = cfg.get('smtp_port', '587').strip()
                smtp_port = int(smtp_port_raw) if smtp_port_raw.isdigit() else 587
                smtp_user = cfg.get('smtp_user', '').strip() or 'espacioterapeuticoapp@gmail.com'
                smtp_pass = cfg.get('smtp_password', '').strip() or 'kinygwxtkovrtsjp'
                smtp_from = cfg.get('smtp_from_email', '').strip() or f"Espacio Terapéutico <{smtp_user}>"

                if not smtp_host or not smtp_user or not smtp_pass:
                    print(f"[SMTP] Configuración SMTP incompleta para enviar correo a {to_email}.")
                    return

                import smtplib
                from email.mime.multipart import MIMEMultipart
                from email.mime.text import MIMEText

                msg = MIMEMultipart('alternative')
                msg['Subject'] = subject
                msg['From'] = smtp_from
                msg['To'] = to_email

                if text_content:
                    msg.attach(MIMEText(text_content, 'plain', 'utf-8'))
                msg.attach(MIMEText(html_content, 'html', 'utf-8'))

                if smtp_port == 465:
                    server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=15)
                else:
                    server = smtplib.SMTP(smtp_host, smtp_port, timeout=15)
                    server.starttls()

                server.login(smtp_user, smtp_pass)
                server.sendmail(smtp_user, [to_email], msg.as_string())
                server.quit()
                print(f"[SMTP] Correo enviado exitosamente a {to_email}")
        except Exception as e:
            print(f"[SMTP ERROR] Falló el envío de correo a {to_email}: {e}")

    import threading
    threading.Thread(target=_worker, daemon=True).start()


def send_welcome_credentials_email(user_type, email, full_name, username, raw_password, p1=None, r1=None, p2=None, r2=None, login_url=None):
    """
    Construye y envía el correo HTML estilizado con credenciales y preguntas de seguridad.
    """
    if not email or '@' not in str(email):
        return

    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT valor FROM configuracion WHERE clave = 'auto_welcome_email_active'")
        row = cursor.fetchone()
        if row and row['valor'] == '0':
            print("[SMTP] Los correos automáticos de bienvenida están desactivados por configuración.")
            return
    except Exception:
        pass

    site_url = login_url or "https://www.espacioterapeutico.net"
    portal_label = "Plataforma de Consultorio Psicológico" if user_type == 'psicologo' else "Portal del Consultante"
    subject = f"🌿 Tus Credenciales de Acceso - Espacio Terapéutico ({full_name})"

    p1_text = p1 or "No especificada"
    r1_text = r1 or "No especificada"
    p2_text = p2 or "No especificada"
    r2_text = r2 or "No especificada"

    support_email = "espacioterapeuticoapp@gmail.com"

    html_content = f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: 'Segoe UI', system-ui, -apple-system, sans-serif; background-color: #f8fafc; margin: 0; padding: 24px 12px; color: #334155; }}
            .card {{ max-width: 580px; margin: 0 auto; background: #ffffff; border-radius: 16px; overflow: hidden; box-shadow: 0 10px 25px -5px rgba(15,23,42,0.08); border: 1px solid #e2e8f0; }}
            .header {{ background: linear-gradient(135deg, #0d9488 0%, #0f766e 100%); padding: 32px 24px; text-align: center; color: #ffffff; }}
            .header h1 {{ margin: 0; font-size: 24px; font-weight: 800; letter-spacing: -0.5px; }}
            .header p {{ margin: 6px 0 0 0; opacity: 0.92; font-size: 14px; font-weight: 500; }}
            .content {{ padding: 32px 28px; }}
            .greeting {{ font-size: 18px; font-weight: 700; color: #0f172a; margin-bottom: 12px; }}
            .intro {{ font-size: 14px; line-height: 1.6; color: #475569; margin-bottom: 24px; }}
            .box {{ background: #f8fafc; border: 1.5px solid #cbd5e1; border-radius: 12px; padding: 20px; margin-bottom: 20px; }}
            .box-title {{ font-size: 13px; font-weight: 800; text-transform: uppercase; color: #0d9488; letter-spacing: 0.5px; margin-bottom: 14px; border-bottom: 1px dashed #cbd5e1; padding-bottom: 6px; }}
            .field {{ margin-bottom: 10px; font-size: 14px; color: #334155; }}
            .field strong {{ color: #0f172a; width: 140px; display: inline-block; font-weight: 600; }}
            .field span {{ font-family: monospace; font-size: 15px; font-weight: 700; color: #0f766e; background: #ccfbf1; padding: 3px 10px; border-radius: 6px; border: 1px solid #99f6e4; }}
            .btn-wrap {{ text-align: center; margin: 30px 0 10px 0; }}
            .btn {{ background: #0d9488; color: #ffffff !important; padding: 14px 32px; border-radius: 10px; text-decoration: none; font-weight: 700; font-size: 15px; display: inline-block; box-shadow: 0 4px 12px rgba(13,148,136,0.3); }}
            .footer {{ background: #f1f5f9; padding: 20px; text-align: center; font-size: 12px; color: #64748b; border-top: 1px solid #e2e8f0; line-height: 1.5; }}
        </style>
    </head>
    <body>
        <div class="card">
            <div class="header">
                <h1>🌿 Espacio Terapéutico</h1>
                <p>{portal_label}</p>
            </div>
            <div class="content">
                <div class="greeting">¡Hola, {full_name}! 👋</div>
                <div class="intro">
                    Te damos la bienvenida oficial a <strong>Espacio Terapéutico</strong>. Tu cuenta ha sido registrada exitosamente. A continuación encontrarás tus credenciales de acceso e información de seguridad guardada.
                </div>

                <div class="box">
                    <div class="box-title">🔐 Credenciales de Ingreso</div>
                    <div class="field"><strong>Usuario / Correo:</strong> <span>{username}</span></div>
                    <div class="field"><strong>Contraseña:</strong> <span>{raw_password}</span></div>
                    <div class="field"><strong>Enlace de Acceso:</strong> <a href="{site_url}" style="color:#0d9488; font-weight: 600;">{site_url}</a></div>
                </div>

                <div class="box" style="background:#f0fdf4; border-color:#bbf7d0;">
                    <div class="box-title" style="color:#047857;">🛡️ Preguntas de Seguridad</div>
                    <div class="field"><strong>Pregunta 1:</strong> {p1_text}</div>
                    <div class="field"><strong>Respuesta 1:</strong> <span>{r1_text}</span></div>
                    <div style="height: 8px;"></div>
                    <div class="field"><strong>Pregunta 2:</strong> {p2_text}</div>
                    <div class="field"><strong>Respuesta 2:</strong> <span>{r2_text}</span></div>
                </div>

                <div class="btn-wrap">
                    <a href="{site_url}" class="btn">🚀 Iniciar Sesión en la Plataforma</a>
                </div>
            </div>
            <div class="footer">
                Este es un correo automático generado por Espacio Terapéutico.<br>
                Si tienes alguna consulta, puedes escribirnos directamente a <a href="mailto:{support_email}" style="color:#0d9488;">{support_email}</a>.
            </div>
        </div>
    </body>
    </html>
    """
    send_email_async(email, subject, html_content)


def send_subscription_renewed_email(user_email, full_name, new_exp_str):
    """
    Envía un correo cuando la suscripción es activada o renovada por el superadministrador.
    """
    if not user_email or '@' not in str(user_email):
        return

    subject = f"🎉 ¡Tu Suscripción ha sido Activada/Renovada! - Espacio Terapéutico"
    site_url = "https://www.espacioterapeutico.net"

    html_content = f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: 'Segoe UI', system-ui, -apple-system, sans-serif; background-color: #f8fafc; margin: 0; padding: 24px 12px; color: #334155; }}
            .card {{ max-width: 580px; margin: 0 auto; background: #ffffff; border-radius: 16px; overflow: hidden; box-shadow: 0 10px 25px -5px rgba(15,23,42,0.08); border: 1px solid #e2e8f0; }}
            .header {{ background: linear-gradient(135deg, #10b981 0%, #059669 100%); padding: 32px 24px; text-align: center; color: #ffffff; }}
            .header h1 {{ margin: 0; font-size: 24px; font-weight: 800; letter-spacing: -0.5px; }}
            .header p {{ margin: 6px 0 0 0; opacity: 0.95; font-size: 14px; font-weight: 600; }}
            .content {{ padding: 32px 28px; }}
            .greeting {{ font-size: 18px; font-weight: 700; color: #0f172a; margin-bottom: 12px; }}
            .intro {{ font-size: 14px; line-height: 1.6; color: #475569; margin-bottom: 24px; }}
            .box {{ background: #f0fdf4; border: 1.5px solid #bbf7d0; border-radius: 12px; padding: 20px; margin-bottom: 20px; }}
            .box-title {{ font-size: 13px; font-weight: 800; text-transform: uppercase; color: #166534; letter-spacing: 0.5px; margin-bottom: 10px; }}
            .field {{ margin-bottom: 8px; font-size: 14px; color: #166534; }}
            .field strong {{ color: #0f172a; font-weight: 700; }}
            .btn-wrap {{ text-align: center; margin: 30px 0 10px 0; }}
            .btn {{ background: #10b981; color: #ffffff !important; padding: 14px 32px; border-radius: 10px; text-decoration: none; font-weight: 700; font-size: 15px; display: inline-block; box-shadow: 0 4px 12px rgba(16,185,129,0.3); }}
            .footer {{ background: #f1f5f9; padding: 20px; text-align: center; font-size: 12px; color: #64748b; border-top: 1px solid #e2e8f0; line-height: 1.5; }}
        </style>
    </head>
    <body>
        <div class="card">
            <div class="header">
                <h1>🌿 Espacio Terapéutico</h1>
                <p>Suscripción Activada Exitosamente</p>
            </div>
            <div class="content">
                <div class="greeting">¡Hola, {full_name}! 👋</div>
                <div class="intro">
                    Nos complace informarte que tu suscripción en <strong>Espacio Terapéutico</strong> ha sido activada/renovada exitosamente. Tienes acceso completo a todas tus herramientas de consultorio, pacientes, evoluciones, agenda y finanzas.
                </div>
                
                <div class="box">
                    <div class="box-title">📋 Detalles de tu Membresía</div>
                    <div class="field"><strong>Estado:</strong> 🟢 Suscripción Activa / Solvente</div>
                    <div class="field"><strong>Válida hasta el:</strong> <span style="font-weight:700; background:#dcfce7; padding:2px 8px; border-radius:4px; color:#15803d;">{new_exp_str}</span></div>
                </div>

                <div class="btn-wrap">
                    <a href="{site_url}" class="btn">🌿 Ingresar a Mi Consultorio</a>
                </div>
            </div>
            <div class="footer">
                Espacio Terapéutico — Tu plataforma de gestión clínica.<br>
                Si tienes preguntas sobre tu plan o pagos, puedes escribirnos a soporte.
            </div>
        </div>
    </body>
    </html>
    """
    send_email_async(user_email, subject, html_content)


def send_subscription_expiring_soon_email(user_email, full_name, days_left, exp_date_str):
    """
    Envía un correo recordatorio cuando la membresía está por vencer en 3 días o menos.
    """
    if not user_email or '@' not in str(user_email):
        return

    subject = f"⏳ Recordatorio: Tu membresía en Espacio Terapéutico vence en {days_left} días"
    site_url = "https://www.espacioterapeutico.net"

    html_content = f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: 'Segoe UI', system-ui, -apple-system, sans-serif; background-color: #f8fafc; margin: 0; padding: 24px 12px; color: #334155; }}
            .card {{ max-width: 580px; margin: 0 auto; background: #ffffff; border-radius: 16px; overflow: hidden; box-shadow: 0 10px 25px -5px rgba(15,23,42,0.08); border: 1px solid #e2e8f0; }}
            .header {{ background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%); padding: 32px 24px; text-align: center; color: #ffffff; }}
            .header h1 {{ margin: 0; font-size: 24px; font-weight: 800; letter-spacing: -0.5px; }}
            .header p {{ margin: 6px 0 0 0; opacity: 0.95; font-size: 14px; font-weight: 600; }}
            .content {{ padding: 32px 28px; }}
            .greeting {{ font-size: 18px; font-weight: 700; color: #0f172a; margin-bottom: 12px; }}
            .intro {{ font-size: 14px; line-height: 1.6; color: #475569; margin-bottom: 24px; }}
            .box {{ background: #fffbeb; border: 1.5px solid #fde68a; border-radius: 12px; padding: 20px; margin-bottom: 20px; }}
            .box-title {{ font-size: 13px; font-weight: 800; text-transform: uppercase; color: #b45309; letter-spacing: 0.5px; margin-bottom: 10px; }}
            .field {{ margin-bottom: 8px; font-size: 14px; color: #92400e; }}
            .field strong {{ color: #0f172a; font-weight: 700; }}
            .btn-wrap {{ text-align: center; margin: 30px 0 10px 0; }}
            .btn {{ background: #0d9488; color: #ffffff !important; padding: 14px 32px; border-radius: 10px; text-decoration: none; font-weight: 700; font-size: 15px; display: inline-block; box-shadow: 0 4px 12px rgba(13,148,136,0.3); }}
            .footer {{ background: #f1f5f9; padding: 20px; text-align: center; font-size: 12px; color: #64748b; border-top: 1px solid #e2e8f0; line-height: 1.5; }}
        </style>
    </head>
    <body>
        <div class="card">
            <div class="header">
                <h1>🌿 Espacio Terapéutico</h1>
                <p>Aviso de Próximo Vencimiento de Membresía</p>
            </div>
            <div class="content">
                <div class="greeting">¡Hola, {full_name}! 👋</div>
                <div class="intro">
                    Te escribimos para recordarte que tu membresía / período de prueba en <strong>Espacio Terapéutico</strong> está por vencer en <strong>{days_left} días</strong> ({exp_date_str}).
                </div>
                
                <div class="box">
                    <div class="box-title">⏳ Estado de tu Membresía</div>
                    <div class="field"><strong>Fecha de Vencimiento:</strong> <span style="font-weight:700; background:#fef3c7; padding:2px 8px; border-radius:4px; color:#b45309;">{exp_date_str}</span></div>
                    <div class="field"><strong>Días Restantes:</strong> {days_left} días</div>
                </div>

                <div class="intro" style="margin-top: 16px;">
                    Para mantener tu acceso ininterrumpido a tus historias clínicas, agenda y herramientas, comunícate con la administración para renovar tu plan.
                </div>

                <div class="btn-wrap">
                    <a href="{site_url}" class="btn">🌿 Ingresar a Mi Consultorio</a>
                </div>
            </div>
            <div class="footer">
                Espacio Terapéutico — Tu plataforma de gestión clínica.<br>
                Si ya realizaste tu pago o renovación, por favor ignora este mensaje.
            </div>
        </div>
    </body>
    </html>
    """
    send_email_async(user_email, subject, html_content)


def auto_check_subscription_expiration_reminders(db):
    """
    Verifica automáticamente psicólogos cuya membresía venza en 3 días o menos
    y les envía una notificación por correo (máximo una vez cada 6 horas).
    """
    try:
        ensure_usuarios_columns(db)
        cursor = db.cursor()
        
        # Verificar última ejecución en tabla configuracion (máximo 1 vez cada 6 horas)
        cursor.execute("SELECT valor FROM configuracion WHERE clave = 'last_sub_exp_check'")
        row = cursor.fetchone()
        now_dt = datetime.datetime.now()
        
        if row and row['valor']:
            try:
                last_run = datetime.datetime.fromisoformat(row['valor'])
                if (now_dt - last_run).total_seconds() < 21600:
                    return
            except Exception:
                pass

        cursor.execute("INSERT OR REPLACE INTO configuracion (clave, valor) VALUES ('last_sub_exp_check', ?)", (now_dt.isoformat(),))
        db.commit()

        cursor.execute("""
            SELECT id, nombres, apellidos, username, email, email_publico, fecha_expiracion_prueba, recordatorio_expiracion_enviado
            FROM usuarios 
            WHERE role != 'superadmin' AND fecha_expiracion_prueba IS NOT NULL AND fecha_expiracion_prueba != ''
        """)
        users = cursor.fetchall()
        
        for u in users:
            u_dict = dict(u)
            user_id = u_dict['id']
            email = (u_dict.get('email') or u_dict.get('email_publico') or '').strip()
            exp_str = u_dict.get('fecha_expiracion_prueba') or ''
            already_sent_exp = u_dict.get('recordatorio_expiracion_enviado') or ''
            
            if not email or '@' not in email or not exp_str:
                continue

            try:
                if 'T' in exp_str:
                    exp_date = datetime.datetime.fromisoformat(exp_str)
                else:
                    exp_date = datetime.datetime.strptime(exp_str[:10], '%Y-%m-%d')

                diff = exp_date - now_dt
                days_left = math.ceil(diff.total_seconds() / 86400)
                
                # Si faltan 3 días o menos (1 <= days_left <= 3) y no se ha enviado recordatorio para esta fecha
                if 1 <= days_left <= 3 and already_sent_exp != exp_str[:10]:
                    full_name = f"{u_dict.get('nombres') or ''} {u_dict.get('apellidos') or ''}".strip() or u_dict.get('username')
                    exp_formatted = exp_date.strftime('%d/%m/%Y')
                    send_subscription_expiring_soon_email(email, full_name, days_left, exp_formatted)
                    
                    cursor.execute("UPDATE usuarios SET recordatorio_expiracion_enviado = ? WHERE id = ?", (exp_str[:10], user_id))
                    db.commit()
            except Exception as ex_u:
                print(f"Error procesando recordatorio de suscripción para usuario {user_id}:", ex_u)
    except Exception as e:
        print("Error en auto_check_subscription_expiration_reminders:", e)


def send_hourly_patient_tool_reminders(db=None):
    """
    Revisa la hora local (8:00 PM / 20:00) de cada paciente que tenga herramientas
    terapéuticas activas en modulos_terapeuticos_paciente y les envía el recordatorio diario.
    """
    if db is None:
        db = get_db()
    cursor = db.cursor()

    TOOL_NAME_MAP = {
        'sobriedad': 'Registro de Sobriedad / Consumo',
        'sueno': 'Registro de Sueño',
        'ansiedad': 'Registro de Ansiedad',
        'medicamentos': 'Adherencia a Medicamentos',
        'actividades': 'Registro de Actividades',
        'cognitivos': 'Registro de Pensamientos Cognitivos',
        'ingesta': 'Registro de Ingesta Alimentaria'
    }

    now_utc = datetime.datetime.now(datetime.timezone.utc)
    today_str = now_utc.strftime("%Y-%m-%d")

    try:
        cursor.execute("""
            SELECT DISTINCT p.id, p.nombres, p.apellidos, p.cedula, p.username, p.zona_horaria, p.utc_offset
            FROM pacientes p
            JOIN modulos_terapeuticos_paciente mt ON p.id = mt.paciente_id
            WHERE mt.activo = 1
        """)
        patients_with_tools = cursor.fetchall()
    except Exception:
        return 0

    reminders_sent = 0

    for p in patients_with_tools:
        p_id = p['id']
        offset_min = p['utc_offset'] if (p['utc_offset'] is not None) else 240
        
        # Calcular hora local del paciente a partir de UTC
        patient_local = now_utc - datetime.timedelta(minutes=offset_min)
        current_hour = patient_local.hour

        # Verificar si en el reloj local del paciente son las 8:00 PM (hora 20)
        if current_hour == 20:
            unique_link = f"/#herramientas-paciente?daily_reminder={p_id}_{today_str}"
            cursor.execute("SELECT id FROM notificaciones WHERE link = ?", (unique_link,))
            if cursor.fetchone():
                continue # Ya enviado hoy

            cursor.execute("SELECT modulo_clave FROM modulos_terapeuticos_paciente WHERE paciente_id = ? AND activo = 1", (p_id,))
            active_modules = [r['modulo_clave'] for r in cursor.fetchall()]
            
            tool_names = [TOOL_NAME_MAP.get(m, m) for m in active_modules if m in TOOL_NAME_MAP]
            if not tool_names:
                continue

            if len(tool_names) == 1:
                tools_str = tool_names[0]
            elif len(tool_names) == 2:
                tools_str = f"{tool_names[0]} y {tool_names[1]}"
            else:
                tools_str = ", ".join(tool_names[:-1]) + f" y {tool_names[-1]}"

            first_name = (p['nombres'] or '').strip().split()[0] if p['nombres'] else 'Consultante'

            notif_title = "🧠 Recordatorio Terapéutico Diario"
            notif_body = f"{first_name}, recuerda actualizar tu estatus de {tools_str}"
            now_str = patient_local.strftime("%Y-%m-%d %H:%M:%S")

            cursor.execute("""
                INSERT INTO notificaciones (user_id, tipo, titulo, mensaje, fecha, leida, link)
                VALUES (0, 'herramienta_paciente', ?, ?, ?, 0, ?)
            """, (notif_title, notif_body, now_str, unique_link))
            db.commit()

            try:
                if FIREBASE_DB_URL:
                    fb_payload = {
                        'titulo': notif_title,
                        'mensaje': notif_body,
                        'fecha': now_str,
                        'leida': False,
                        'tipo': 'herramienta_paciente',
                        'link': '/#herramientas-paciente'
                    }
                    requests.post(f"{FIREBASE_DB_URL}/pacientes/{p_id}/notificaciones.json", json=fb_payload, timeout=2.0)
            except Exception:
                pass

            try:
                send_fcm_notification(patient_id=p_id, title=notif_title, body=notif_body, url="/#herramientas-paciente")
            except Exception:
                pass

            reminders_sent += 1

    return reminders_sent

@app.before_request
def before_request_cleanup():
    # Evitar ejecutar en llamadas de archivos estáticos
    if request.path.startswith('/static/'):
        return
    db = get_db()
    auto_cancel_unconfirmed_sessions(db)
    auto_send_appointment_reminders(db)
    auto_send_confirmation_requests(db)
    auto_check_patient_birthdays(db)
    send_hourly_patient_tool_reminders(db)
    auto_check_subscription_expiration_reminders(db)

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
            WHERE paciente_id = ? AND estado_pago IN ('Prepagada', 'Paga') AND control_uso = 'No consumida'
              AND id != ?
            ORDER BY fecha ASC, id ASC LIMIT 1
        """, (patient_id, debt['id']))
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
            SET estado_pago = ?, control_uso = 'No consumida', monto = 0.0,
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
        requests.put(f"{FIREBASE_DB_URL}/usuarios_pacientes/{username_key}.json", json=patient_data, timeout=3.0)
        
        # 2. Guardar perfil completo en /pacientes/<id>/perfil
        requests.put(f"{FIREBASE_DB_URL}/pacientes/{patient_id}/perfil.json", json=patient_data, timeout=3.0)
        
        # 3. Guardar resumen financiero en /pacientes/<id>/finanzas
        requests.put(f"{FIREBASE_DB_URL}/pacientes/{patient_id}/finanzas.json", json={
            "prepagadas": prepagadas,
            "deuda": deudas
        }, timeout=3.0)
        
        # 4. Guardar seguimiento clínico compartido en /pacientes/<id>/compartido
        requests.put(f"{FIREBASE_DB_URL}/pacientes/{patient_id}/compartido.json", json=compartido, timeout=3.0)
        
        # 5. Guardar próxima cita en /pacientes/<id>/proxima_cita
        requests.put(f"{FIREBASE_DB_URL}/pacientes/{patient_id}/proxima_cita.json", json=proxima_cita, timeout=3.0)
        
        # 6. Sincronizar mapa ligero de IDs de citas evolucionadas/completadas para conciliar en restauraciones de respaldos
        cursor.execute("SELECT DISTINCT agenda_id FROM sesiones WHERE paciente_id = ? AND agenda_id IS NOT NULL", (patient_id,))
        completed_agenda_ids = [row[0] for row in cursor.fetchall()]
        requests.put(f"{FIREBASE_DB_URL}/pacientes/{patient_id}/citas_completadas.json", json=completed_agenda_ids, timeout=3.0)

        return True
    except Exception as e:
        print(f"Error syncing to Firebase: {e}")
        return False

def delete_patient_from_firebase(patient_id, u_key=None):
    """Elimina síncronamente los datos del paciente de Firebase Realtime Database para evitar reapariciones."""
    try:
        import requests
        key_to_delete = u_key
        if not key_to_delete:
            conn = sqlite3.connect('clinica.db')
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("SELECT username, cedula FROM pacientes WHERE id = ?", (patient_id,))
            p = c.fetchone()
            conn.close()
            if p:
                key_to_delete = (p['username'] or p['cedula'] or '').strip()

        if key_to_delete:
            clean_key = key_to_delete.replace(".", "_").replace("$", "_").replace("[", "_").replace("]", "_").replace("#", "_").lower()
            requests.delete(f"{FIREBASE_DB_URL}/usuarios_pacientes/{clean_key}.json", timeout=4.0)
        
        requests.delete(f"{FIREBASE_DB_URL}/pacientes/{patient_id}.json", timeout=4.0)
    except Exception as e:
        print(f"Error deleting patient {patient_id} from Firebase: {e}")

def sync_all_psychologist_patients_to_firebase(psych_id):
    """Vuelve a sincronizar todos los pacientes de un psicólogo en Firebase (útil al cambiar métodos de pago)."""
    def _async_sync():
        try:
            conn = sqlite3.connect('clinica.db')
            c = conn.cursor()
            c.execute("SELECT id FROM pacientes WHERE psicologo_id = ?", (psych_id,))
            p_ids = [r[0] for r in c.fetchall()]
            conn.close()
            for pid in p_ids:
                sync_patient_to_firebase(pid)
        except Exception as e:
            print(f"Error syncing psychologist {psych_id} patients to Firebase: {e}")
    import threading
    threading.Thread(target=_async_sync).start()


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
@app.route('/uploads/<filename>', methods=['GET'])
def get_uploaded_file(filename):
    clean_filename = os.path.basename(filename)
    filepath = os.path.join(UPLOAD_FOLDER, clean_filename)
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
            expiry_dt = now_dt + datetime.timedelta(days=30)
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

            p1 = data.get('pregunta_seguridad_1')
            r1 = (data.get('respuesta_seguridad_1') or '').strip().lower()
            p2 = data.get('pregunta_seguridad_2')
            r2 = (data.get('respuesta_seguridad_2') or '').strip().lower()
            r1_hash = generate_password_hash(r1) if r1 else None
            r2_hash = generate_password_hash(r2) if r2 else None

            cursor.execute("""
                INSERT INTO usuarios (username, password_hash, nombres, apellidos, estudios, federacion, foto_titulo, foto_documento, role, activo, fecha_registro, fecha_expiracion_prueba, suscripcion_paga, slug, configuracion_horarios_visual, metodos_pago, primer_inicio, pregunta_seguridad_1, respuesta_seguridad_1_hash, pregunta_seguridad_2, respuesta_seguridad_2_hash, mostrar_en_directorio, bloqueo_herramientas, bloqueo_confirmaciones, bloqueo_examen_mental, bloqueo_tests)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'psicologo', 1, ?, ?, 0, ?, ?, ?, 1, ?, ?, ?, ?, 1, 0, 0, 1, 1)
            """, (username, password_hash, nombres, apellidos, estudios, federacion, foto_titulo, foto_documento, now_str, expiry_str, clean_slug, default_visual_cfg, default_pm_str, p1, r1_hash, p2, r2_hash))
            new_user_id = cursor.lastrowid

            nombre_clinica = data.get('nombre_clinica')
            if nombre_clinica:
                import random, string
                code_rnd = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
                prefix = re.sub(r'[^A-Z]', '', unicodedata.normalize('NFD', nombre_clinica.upper()))[:5] or 'CLIN'
                codigo_clinica = f"{prefix}-{code_rnd}"
                slug_clinica = re.sub(r'[^a-z0-9\-]', '', unicodedata.normalize('NFD', nombre_clinica.lower().replace(" ", "-")))
                if not slug_clinica:
                    slug_clinica = f"clinica-{new_user_id}"

                cursor.execute("""
                    INSERT INTO clinicas (nombre, slug, codigo_clinica, admin_id, modo_whatsapp)
                    VALUES (?, ?, ?, ?, 'centralizado')
                """, (nombre_clinica, slug_clinica, codigo_clinica, new_user_id))
                new_clinica_id = cursor.lastrowid

                cursor.execute("UPDATE usuarios SET clinica_id = ?, tipo_clinica = 1 WHERE id = ?", (new_clinica_id, new_user_id))

            db.commit()
            
            # Enviar correo de bienvenida con credenciales y preguntas de seguridad
            email_target = username if '@' in username else data.get('email')
            if email_target:
                full_name_psic = f"Psic. {nombres} {apellidos}".strip()
                send_welcome_credentials_email('psicologo', email_target, full_name_psic, username, password, p1, r1, p2, r2)

            return jsonify({'success': 'Cuenta de psicólogo creada con éxito.' + (' ¡Tu clínica ha sido registrada!' if nombre_clinica else '')})
            
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
                target_psic = psicologo_id or existing_patient['psicologo_id'] or 1
                if psicologo_id and not existing_patient['psicologo_id']:
                    cursor.execute("UPDATE pacientes SET psicologo_id = ? WHERE id = ?", (psicologo_id, patient_id))
                ex_nom = existing_patient['nombres'] if existing_patient['nombres'] else ''
                ex_ape = existing_patient['apellidos'] if existing_patient['apellidos'] else ''
                pat_name = f"{data.get('nombres') or ex_nom} {data.get('apellidos') or ex_ape}".strip() or username
                notif_msg = f"El consultante {pat_name} ha completado la creación de su cuenta de acceso."
            else:
                target_psic = psicologo_id or 1
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
                    username, password_hash, pregunta_1, resp_1_hash, pregunta_2, resp_2_hash, target_psic
                ))
                patient_id = cursor.lastrowid
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
            
            # Enviar correo de bienvenida con credenciales y preguntas de seguridad al consultante
            if email:
                full_name_pac = pat_name
                send_welcome_credentials_email(
                    'paciente', email, full_name_pac, username, password, 
                    pregunta_1, resp_1, pregunta_2, resp_2, 
                    login_url="https://www.espacioterapeutico.net/portal"
                )
            
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
        SELECT id, nombres, apellidos, username, slug, role, es_psicologo
        FROM usuarios
        WHERE (role IN ('psicologo', 'admin', 'superadmin', 'psicologo_admin') OR es_psicologo = 1) AND activo = 1
        ORDER BY id ASC
    """)
    raw_rows = cursor.fetchall()
    result = []
    for r in raw_rows:
        r_dict = dict(r)
        slug = r_dict.get('slug') or generate_default_slug_for_user(r_dict)
        result.append({
            'id': r_dict['id'],
            'nombres': r_dict['nombres'],
            'apellidos': r_dict['apellidos'],
            'username': r_dict.get('username') or '',
            'slug': slug
        })
    return jsonify(result)

def get_psychologist_by_id_or_slug(cursor, identifier):
    cursor.execute("SELECT * FROM usuarios ORDER BY id ASC")
    raw_rows = cursor.fetchall()
    if not raw_rows:
        return None

    rows = [dict(r) for r in raw_rows]
    users = [u for u in rows if str(u.get('role', '')).lower() in ('psicologo', 'superadmin', 'admin', 'psicologo_admin') or u.get('es_psicologo')]
    if not users:
        users = rows

    if not identifier:
        return users[0]

    ident_str = str(identifier).strip().lower()
    clean_id = ident_str.replace("psic.", "").replace("psic-", "").replace("/", "").strip().lower()
    with_prefix = f"psic.{clean_id}"

    # 1. Si es ID numérico
    if clean_id.isdigit():
        for u in users:
            if u.get('id') == int(clean_id):
                return u

    # 2. Coincidencia exacta por slug (almacenado o generado), username, o id limpio
    for u in users:
        u_slug = str(u.get('slug') or '').strip().lower()
        u_uname = str(u.get('username') or '').strip().lower()
        computed_slug = generate_default_slug_for_user(u).lower()
        
        if (u_slug and u_slug in (ident_str, with_prefix, clean_id)) or \
           (u_uname and u_uname in (ident_str, clean_id)) or \
           (computed_slug and computed_slug in (ident_str, with_prefix, clean_id)):
            return u

    # 3. Coincidencia por nombre o apellido
    if clean_id:
        for u in users:
            u_nom = str(u.get('nombres') or '').strip().lower()
            u_ape = str(u.get('apellidos') or '').strip().lower()
            full_name = f"{u_nom} {u_ape}".strip()
            combo_name = f"{u_nom}{u_ape}".strip()
            u_slug = str(u.get('slug') or '').strip().lower()
            u_uname = str(u.get('username') or '').strip().lower()
            computed_slug = generate_default_slug_for_user(u).lower()
            
            if clean_id in full_name or clean_id in combo_name or \
               (u_slug and clean_id in u_slug) or (u_uname and clean_id in u_uname) or \
               (computed_slug and clean_id in computed_slug):
                return u

    # 4. Fallback absoluto: retornar el primer usuario disponible
    return users[0]

@app.route('/agendar/<identifier>', methods=['GET'])
def vanity_fast_booking(identifier):
    return render_template('index.html')

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
    email = data.get('email', '').strip() or data.get('correo', '').strip()
    
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
                INSERT INTO pacientes (nombres, apellidos, cedula, telefono, email, psicologo_id)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (nombres, apellidos, cedula, telefono, email, psicologo_id))
            patient_id = cursor.lastrowid
            pac_nombre = f"{nombres} {apellidos}"
        except Exception as ex:
            return jsonify({'error': f'Error al registrar paciente automáticamente: {str(ex)}'}), 500
    else:
        patient_id = patient['id']
        pac_nombre = f"{patient['nombres']} {patient['apellidos']}"
        if email and not patient['email']:
            cursor.execute("UPDATE pacientes SET email = ? WHERE id = ?", (email, patient_id))
        
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
            # Agregar al paciente como invitado en Google Calendar para enviar invitación por correo
            email_paciente = data.get('email', '').strip() or data.get('correo', '').strip()
            if not email_paciente and patient:
                try:
                    email_paciente = patient['email'] if isinstance(patient, dict) and 'email' in patient else (patient[14] if len(patient) > 14 else None)
                except:
                    pass
            
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
            INSERT INTO notificaciones (user_id, tipo, titulo, mensaje, fecha, leida, link)
            VALUES (?, ?, ?, ?, ?, 0, ?)
        """, (psicologo_id, 'cita', 'Nueva Cita Agendada (Rápida)', f"{pac_nombre} ha auto-agendado una consulta para el {fecha} a las {hora}.", fecha_notif, 'agenda'))
        
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

@app.route('/api/superadmin/seed-demo-user', methods=['GET', 'POST'])
def superadmin_seed_demo_user():
    try:
        db = get_db()
        ensure_demo_user(db)
        return jsonify({'success': True, 'message': 'Usuario demo psicologa.valeria y paciente camila.perez procesados con éxito.'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def check_is_superadmin():
    user_id = session.get('user_id')
    if not user_id:
        return False
    role = session.get('role')
    if role in ('superadmin', 'admin') or user_id == 1:
        return True
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT role, username FROM usuarios WHERE id = ?", (user_id,))
        u = cursor.fetchone()
        if u:
            r = (u['role'] or '').lower()
            un = (u['username'] or '').lower()
            if r in ('superadmin', 'admin') or un in ('admin', 'superadmin', 'pamoraro') or user_id == 1:
                session['role'] = u['role'] if u['role'] else 'superadmin'
                return True
    except Exception:
        pass
    return False

def ensure_usuarios_columns(db=None):
    close_at_end = False
    if db is None:
        db = get_db()
        close_at_end = True
    cursor = db.cursor()
    columns = [
        ('mostrar_en_directorio', 'INTEGER DEFAULT 0'),
        ('aviso_pago', 'INTEGER DEFAULT 0'),
        ('bloqueo_registro', 'INTEGER DEFAULT 0'),
        ('bloqueo_evoluciones', 'INTEGER DEFAULT 0'),
        ('bloqueo_finanzas', 'INTEGER DEFAULT 0'),
        ('bloqueo_agenda', 'INTEGER DEFAULT 0'),
        ('bloqueo_mensajes', 'INTEGER DEFAULT 0'),
        ('bloqueo_pizarra', 'INTEGER DEFAULT 0'),
        ('bloqueo_herramientas', 'INTEGER DEFAULT 1'),
        ('bloqueo_confirmaciones', 'INTEGER DEFAULT 1'),
        ('bloqueo_examen_mental', 'INTEGER DEFAULT 0'),
        ('bloqueo_tests', 'INTEGER DEFAULT 0'),
        ('cedula', 'TEXT DEFAULT \'\''),
        ('email', 'TEXT DEFAULT \'\''),
        ('nomenclatura', 'TEXT'),
        ('descripcion_biografia', 'TEXT'),
        ('modalidades_json', 'TEXT'),
        ('whatsapp_publico', 'TEXT'),
        ('email_publico', 'TEXT'),
        ('redes_sociales_json', 'TEXT'),
        ('especialidades', 'TEXT DEFAULT \'\''),
        ('poblaciones_json', 'TEXT DEFAULT \'["Adultos", "Adolescentes"]\''),
        ('pais_ubicacion', 'TEXT DEFAULT \'\''),
        ('recordatorio_expiracion_enviado', 'TEXT DEFAULT \'\'')
    ]
    for col_name, col_type in columns:
        try:
            cursor.execute(f"ALTER TABLE usuarios ADD COLUMN {col_name} {col_type}")
        except Exception:
            pass
    try:
        # El usuario de sistema 'admin' se oculta por defecto del directorio público
        cursor.execute("UPDATE usuarios SET mostrar_en_directorio = 0 WHERE LOWER(username) IN ('admin', 'superadmin') AND (nombres LIKE '%Administrador%' OR nombres = '')")
        # Asegurar permisos de superadmin para Paulo
        cursor.execute("UPDATE usuarios SET role = 'superadmin' WHERE LOWER(username) = 'pamoraro' OR id = 1")
        
        # Poblar slugs vacíos para usuarios existentes
        cursor.execute("SELECT id, nombres, apellidos, username, slug FROM usuarios")
        all_u = cursor.fetchall()
        for u in all_u:
            u_dict = dict(u)
            if not u_dict.get('slug'):
                def_slug = generate_default_slug_for_user(u_dict)
                if def_slug:
                    cursor.execute("UPDATE usuarios SET slug = ? WHERE id = ?", (def_slug, u_dict['id']))
    except Exception:
        pass
    db.commit()
    if close_at_end:
        db.close()

@app.route('/api/superadmin/therapists', methods=['GET'])
@login_required
def superadmin_get_therapists():
    if not check_is_superadmin():
        return jsonify({'error': 'Acceso denegado. Se requieren permisos de superadministrador.'}), 403
        
    db = get_db()
    ensure_usuarios_columns(db)
    try:
        cursor = db.cursor()
        cursor.execute("PRAGMA table_info(usuarios)")
        existing_cols = {row[1] for row in cursor.fetchall()}

        email_expr = "COALESCE(email, '') as email" if 'email' in existing_cols else "'' as email"
        email_pub_expr = "COALESCE(email_publico, '') as email_publico" if 'email_publico' in existing_cols else "'' as email_publico"
        cedula_expr = "COALESCE(cedula, '') as cedula" if 'cedula' in existing_cols else "'' as cedula"
        whatsapp_expr = "COALESCE(whatsapp_publico, '') as whatsapp_publico" if 'whatsapp_publico' in existing_cols else "'' as whatsapp_publico"
        bio_expr = "COALESCE(descripcion_biografia, '') as descripcion_biografia" if 'descripcion_biografia' in existing_cols else "'' as descripcion_biografia"

        cursor.execute(f"""
            SELECT id, username, nombres, apellidos, estudios, federacion, foto_titulo, foto_documento, 
                   {email_expr}, {email_pub_expr}, {cedula_expr}, {whatsapp_expr}, {bio_expr},
                   COALESCE(activo, 1) as activo, fecha_registro, fecha_expiracion_prueba, COALESCE(suscripcion_paga, 0) as suscripcion_paga,
                   COALESCE(bloqueo_registro, 0) as bloqueo_registro, COALESCE(bloqueo_evoluciones, 0) as bloqueo_evoluciones, 
                   COALESCE(bloqueo_finanzas, 0) as bloqueo_finanzas, COALESCE(bloqueo_agenda, 0) as bloqueo_agenda, 
                   COALESCE(bloqueo_mensajes, 0) as bloqueo_mensajes, COALESCE(bloqueo_pizarra, 0) as bloqueo_pizarra, 
                   COALESCE(bloqueo_herramientas, 0) as bloqueo_herramientas, COALESCE(bloqueo_confirmaciones, 0) as bloqueo_confirmaciones,
                   COALESCE(bloqueo_examen_mental, 0) as bloqueo_examen_mental, COALESCE(bloqueo_tests, 0) as bloqueo_tests, COALESCE(aviso_pago, 0) as aviso_pago,
                   COALESCE(mostrar_en_directorio, 0) as mostrar_en_directorio
            FROM usuarios
            WHERE (role IS NULL OR role = '' OR role = 'psicologo' OR role = 'admin')
              AND id != ?
            ORDER BY id DESC
        """, (session.get('user_id'),))
        rows = cursor.fetchall()
        return jsonify([dict(r) for r in rows])
    except Exception as e:
        print(f"Error en superadmin_get_therapists: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Error al obtener lista de psicólogos: {str(e)}'}), 500

@app.route('/api/superadmin/stats', methods=['GET'])
@login_required
def superadmin_get_stats():
    if not check_is_superadmin():
        return jsonify({'error': 'Acceso denegado.'}), 403
        
    db = get_db()
    cursor = db.cursor()
    
    try:
        import datetime
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute("SELECT COUNT(id) FROM pacientes")
        total_pacientes = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT COUNT(id) FROM usuarios WHERE role = 'psicologo'")
        total_psicologos = cursor.fetchone()[0] or 0
        
        cursor.execute("""
            SELECT COUNT(id) FROM usuarios 
            WHERE role = 'psicologo' 
              AND COALESCE(activo, 1) = 1 
              AND (COALESCE(suscripcion_paga, 0) = 1 OR (fecha_expiracion_prueba IS NOT NULL AND fecha_expiracion_prueba > ?))
        """, (now_str,))
        psicologos_activos = cursor.fetchone()[0] or 0
        
        cursor.execute("""
            SELECT COUNT(id) FROM usuarios 
            WHERE role = 'psicologo' 
              AND (
                COALESCE(activo, 1) = 0 
                OR (COALESCE(suscripcion_paga, 0) = 0 AND (fecha_expiracion_prueba IS NULL OR fecha_expiracion_prueba <= ?))
              )
        """, (now_str,))
        psicologos_deudores = cursor.fetchone()[0] or 0
        
        return jsonify({
            'total_pacientes': total_pacientes,
            'total_psicologos': total_psicologos,
            'psicologos_activos': psicologos_activos,
            'psicologos_deudores': psicologos_deudores
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/superadmin/create-psychologist', methods=['POST'])
@login_required
def superadmin_create_psychologist():
    if not check_is_superadmin():
        return jsonify({'error': 'Acceso denegado. Se requieren permisos de superadministrador.'}), 403
        
    data = request.json
    nombres = data.get('nombres')
    apellidos = data.get('apellidos')
    username = data.get('username')
    password = data.get('password')
    estudios = data.get('estudios')
    cedula = data.get('cedula', '')
    federacion = data.get('federacion')
    foto_titulo = data.get('foto_titulo', '')
    foto_documento = data.get('foto_documento', '')
    
    if not username or not password or not nombres or not apellidos:
        return jsonify({'error': 'Todos los campos requeridos deben ser completados.'}), 400
        
    db = get_db()
    ensure_usuarios_columns(db)
    cursor = db.cursor()
    
    cursor.execute("SELECT id FROM usuarios WHERE LOWER(username) = ?", (username.lower(),))
    if cursor.fetchone():
        return jsonify({'error': 'El nombre de usuario ya existe.'}), 400
        
    password_hash = generate_password_hash(password)
    
    try:
        import datetime
        now_dt = datetime.datetime.now()
        expiry_dt = now_dt + datetime.timedelta(days=30)
        now_str = now_dt.strftime("%Y-%m-%d %H:%M:%S")
        expiry_str = expiry_dt.strftime("%Y-%m-%d %H:%M:%S")

        clean_name = f"psic.{(nombres or '').strip()}{(apellidos or '').strip()}".lower().replace(" ", "")
        if not clean_name or clean_name == "psic.":
            clean_slug = f"psic.{username.lower()}"
        else:
            import unicodedata, re
            clean_slug = re.sub(r'[^a-z0-9\.]', '', unicodedata.normalize('NFD', clean_name))

        cursor.execute("""
            INSERT INTO usuarios (username, password_hash, nombres, apellidos, cedula, estudios, federacion, foto_titulo, foto_documento, role, activo, fecha_registro, fecha_expiracion_prueba, suscripcion_paga, slug, mostrar_en_directorio, bloqueo_herramientas, bloqueo_confirmaciones)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'psicologo', 1, ?, ?, 0, ?, 0, 1, 1)
        """, (username, password_hash, nombres, apellidos, cedula, estudios, federacion, foto_titulo, foto_documento, now_str, expiry_str, clean_slug))
        db.commit()
        return jsonify({'success': 'Psicólogo registrado con éxito (Modo Prueba 1 Mes / 30 Días activo).'})
    except Exception as e:
        db.rollback()
        return jsonify({'error': f'Error al registrar psicólogo: {str(e)}'}), 500

@app.route('/api/superadmin/therapists/<int:user_id>/toggle-active', methods=['POST'])
@login_required
def superadmin_toggle_active(user_id):
    if not check_is_superadmin():
        return jsonify({'error': 'Acceso denegado. Se requieren permisos de superadministrador.'}), 403
        
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT activo FROM usuarios WHERE id = ? AND role = 'psicologo'", (user_id,))
    row = cursor.fetchone()
    if not row:
        return jsonify({'error': 'Psicólogo no encontrado.'}), 404
        
    new_status = 0 if row['activo'] == 1 else 1
    if new_status == 1:
        import datetime
        now_dt = datetime.datetime.now()
        expiry_dt = now_dt + datetime.timedelta(days=30)
        now_str = now_dt.strftime("%Y-%m-%d %H:%M:%S")
        expiry_str = expiry_dt.strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("UPDATE usuarios SET activo = 1, fecha_registro = COALESCE(fecha_registro, ?), fecha_expiracion_prueba = ? WHERE id = ?", (now_str, expiry_str, user_id))
    else:
        cursor.execute("UPDATE usuarios SET activo = 0 WHERE id = ?", (user_id,))
    db.commit()
    return jsonify({'success': 'Estado de suscripción actualizado.', 'activo': new_status})

@app.route('/api/superadmin/therapists/<int:user_id>/toggle-subscription', methods=['POST'])
@login_required
def superadmin_toggle_subscription(user_id):
    if not check_is_superadmin():
        return jsonify({'error': 'Acceso denegado. Se requieren permisos de superadministrador.'}), 403
        
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT suscripcion_paga FROM usuarios WHERE id = ? AND role = 'psicologo'", (user_id,))
    row = cursor.fetchone()
    if not row:
        return jsonify({'error': 'Psicólogo no encontrado.'}), 404
        
    new_status = 0 if row['suscripcion_paga'] == 1 else 1
    cursor.execute("UPDATE usuarios SET suscripcion_paga = ? WHERE id = ?", (new_status, user_id))
    db.commit()
    return jsonify({'success': 'Estado de suscripción paga actualizado.', 'suscripcion_paga': new_status})

@app.route('/api/superadmin/therapists/<int:user_id>/set-expiration', methods=['POST'])
@login_required
def superadmin_set_therapist_expiration(user_id):
    if not check_is_superadmin():
        return jsonify({'error': 'Acceso denegado. Se requieren permisos de superadministrador.'}), 403
        
    data = request.json or {}
    fecha_exp = data.get('fecha_expiracion') or data.get('fecha_expiracion_prueba')
    suscripcion_paga = 1 if data.get('suscripcion_paga') else 0
    
    if suscripcion_paga == 0:
        # Si se desactiva, forzar fecha de expiración a ayer a las 23:59:59
        yesterday_dt = datetime.datetime.now() - datetime.timedelta(days=1)
        fecha_exp = yesterday_dt.strftime('%Y-%m-%d 23:59:59')
    elif not fecha_exp:
        return jsonify({'error': 'Fecha de expiración/renovación es requerida.'}), 400
        
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT id FROM usuarios WHERE id = ?", (user_id,))
    if not cursor.fetchone():
        return jsonify({'error': 'Psicólogo no encontrado.'}), 404
        
    if len(str(fecha_exp)) == 10:
        fecha_exp = f"{fecha_exp} 23:59:59"
        
    cursor.execute("""
        UPDATE usuarios 
        SET fecha_expiracion_prueba = ?, suscripcion_paga = ? 
        WHERE id = ?
    """, (fecha_exp, suscripcion_paga, user_id))
    db.commit()

    email_status_msg = ""
    # Enviar correo de notificación de activación/renovación solo si la suscripción se marca como activa
    if suscripcion_paga == 1:
        try:
            cursor.execute("SELECT nombres, apellidos, username, email, email_publico FROM usuarios WHERE id = ?", (user_id,))
            usr = cursor.fetchone()
            if usr:
                u_dict = dict(usr)
                target_email = (u_dict.get('email') or u_dict.get('email_publico') or '').strip()
                if target_email:
                    full_name = f"{u_dict.get('nombres') or ''} {u_dict.get('apellidos') or ''}".strip() or u_dict.get('username')
                    try:
                        exp_dt = datetime.datetime.strptime(str(fecha_exp)[:10], '%Y-%m-%d')
                        exp_formatted = exp_dt.strftime('%d/%m/%Y')
                    except Exception:
                        exp_formatted = str(fecha_exp)[:10]
                    send_subscription_renewed_email(target_email, full_name, exp_formatted)
                    email_status_msg = f"📧 Correo de renovación enviado a {target_email}"
                else:
                    email_status_msg = "⚠️ El psicólogo no tiene correo electrónico guardado. Usa '📋 Ficha' para agregarlo."
        except Exception as ex_mail:
            print("[SMTP] Error enviando correo de renovación:", ex_mail)
            email_status_msg = f"⚠️ Ocurrió una duda al enviar correo: {ex_mail}"

    res_text = '⛔ Suscripción desactivada inmediatamente.' if suscripcion_paga == 0 else 'Fecha de expiración / renovación actualizada con éxito.'
    return jsonify({'success': res_text, 'email_status': email_status_msg})

@app.route('/api/superadmin/therapists/<int:user_id>/update-profile', methods=['POST'])
@login_required
def superadmin_update_therapist_profile(user_id):
    if not check_is_superadmin():
        return jsonify({'error': 'Acceso denegado.'}), 403
        
    try:
        data = request.json or {}
        db = get_db()
        ensure_usuarios_columns(db)
        cursor = db.cursor()
        
        cursor.execute("SELECT id FROM usuarios WHERE id = ?", (user_id,))
        if not cursor.fetchone():
            return jsonify({'error': 'Psicólogo no encontrado.'}), 404
            
        nombres = (data.get('nombres') or '').strip()
        apellidos = (data.get('apellidos') or '').strip()
        username = (data.get('username') or '').strip()
        email = (data.get('email') or '').strip()
        email_publico = (data.get('email_publico') or '').strip()
        cedula = (data.get('cedula') or '').strip()
        whatsapp = (data.get('whatsapp_publico') or '').strip()
        bio = (data.get('descripcion_biografia') or '').strip()

        if username:
            cursor.execute("SELECT id FROM usuarios WHERE LOWER(username) = LOWER(?) AND id != ?", (username, user_id))
            if cursor.fetchone():
                return jsonify({'error': f"El nombre de usuario '@{username}' ya está registrado en la plataforma."}), 400

        cursor.execute("PRAGMA table_info(usuarios)")
        existing_cols = {row[1] for row in cursor.fetchall()}

        fields_to_update = {}
        if 'nombres' in existing_cols: fields_to_update['nombres'] = nombres
        if 'apellidos' in existing_cols: fields_to_update['apellidos'] = apellidos
        if 'username' in existing_cols and username: fields_to_update['username'] = username
        if 'email' in existing_cols: fields_to_update['email'] = email
        if 'email_publico' in existing_cols: fields_to_update['email_publico'] = email_publico
        if 'cedula' in existing_cols: fields_to_update['cedula'] = cedula
        if 'whatsapp_publico' in existing_cols: fields_to_update['whatsapp_publico'] = whatsapp
        if 'telefono' in existing_cols and 'whatsapp_publico' not in existing_cols: fields_to_update['telefono'] = whatsapp
        if 'descripcion_biografia' in existing_cols: fields_to_update['descripcion_biografia'] = bio
        if 'slug' in existing_cols and username: fields_to_update['slug'] = f"psic.{username.lower()}"

        if fields_to_update:
            set_clause = ", ".join([f"{col} = ?" for col in fields_to_update.keys()])
            params = list(fields_to_update.values()) + [user_id]
            cursor.execute(f"UPDATE usuarios SET {set_clause} WHERE id = ?", params)
            db.commit()

        return jsonify({'success': 'Ficha del psicólogo actualizada con éxito.'})
    except Exception as ex:
        print("[SUPERADMIN] Error actualizando ficha de psicólogo:", ex)
        import traceback
        traceback.print_exc()
        return jsonify({'error': f"Error en base de datos: {str(ex)}"}), 500

@app.route('/api/superadmin/therapists/<int:user_id>/save-settings', methods=['POST'])
@login_required
def superadmin_save_therapist_settings(user_id):
    if not check_is_superadmin():
        return jsonify({'error': 'Acceso denegado.'}), 403
        
    data = request.json or {}
    db = get_db()
    ensure_usuarios_columns(db)
    cursor = db.cursor()
    
    mostrar_en_directorio = 1 if data.get('mostrar_en_directorio') else 0
    aviso_pago = 1 if data.get('aviso_pago') else 0
    bloqueo_registro = 1 if data.get('bloqueo_registro') else 0
    bloqueo_evoluciones = 1 if data.get('bloqueo_evoluciones') else 0
    bloqueo_finanzas = 1 if data.get('bloqueo_finanzas') else 0
    bloqueo_agenda = 1 if data.get('bloqueo_agenda') else 0
    bloqueo_mensajes = 1 if data.get('bloqueo_mensajes') else 0
    bloqueo_pizarra = 1 if data.get('bloqueo_pizarra') else 0
    bloqueo_herramientas = 1 if data.get('bloqueo_herramientas') else 0
    bloqueo_confirmaciones = 1 if data.get('bloqueo_confirmaciones') else 0
    bloqueo_examen_mental = 1 if data.get('bloqueo_examen_mental') else 0
    bloqueo_tests = 1 if data.get('bloqueo_tests') else 0
    
    cursor.execute("""
        UPDATE usuarios 
        SET mostrar_en_directorio = ?, aviso_pago = ?,
            bloqueo_registro = ?, bloqueo_evoluciones = ?, bloqueo_finanzas = ?,
            bloqueo_agenda = ?, bloqueo_mensajes = ?, bloqueo_pizarra = ?, bloqueo_herramientas = ?, bloqueo_confirmaciones = ?,
            bloqueo_examen_mental = ?, bloqueo_tests = ?
        WHERE id = ?
    """, (mostrar_en_directorio, aviso_pago, bloqueo_registro, bloqueo_evoluciones, bloqueo_finanzas,
          bloqueo_agenda, bloqueo_mensajes, bloqueo_pizarra, bloqueo_herramientas, bloqueo_confirmaciones,
          bloqueo_examen_mental, bloqueo_tests, user_id))
    db.commit()
    return jsonify({'success': '¡Cambios guardados con éxito en la base de datos!'})

@app.route('/api/superadmin/therapists/<int:user_id>/toggle-feature', methods=['POST'])
@login_required
def superadmin_toggle_feature(user_id):
    if not check_is_superadmin():
        return jsonify({'error': 'Acceso denegado. Se requieren permisos de superadministrador.'}), 403
        
    data = request.json or {}
    feature = data.get('feature')
    status = data.get('status')
    
    if feature not in ['registro', 'evoluciones', 'finanzas', 'agenda', 'mensajes', 'pizarra', 'herramientas', 'confirmaciones', 'examen_mental', 'tests']:
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
    if not check_is_superadmin():
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
    return jsonify({'success': True, 'aviso_pago': new_status})

@app.route('/api/superadmin/therapists/<int:user_id>/toggle-directorio', methods=['POST'])
@login_required
def superadmin_toggle_directorio(user_id):
    if not check_is_superadmin():
        return jsonify({'error': 'Acceso denegado.'}), 403
        
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT COALESCE(mostrar_en_directorio, 1) as mostrar_en_directorio FROM usuarios WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    if not row:
        return jsonify({'error': 'Psicólogo no encontrado.'}), 404
        
    new_val = 0 if row['mostrar_en_directorio'] == 1 else 1
    cursor.execute("UPDATE usuarios SET mostrar_en_directorio = ? WHERE id = ?", (new_val, user_id))
    db.commit()
    return jsonify({'success': 'Visibilidad en directorio actualizada.', 'mostrar_en_directorio': new_val})

@app.route('/api/superadmin/therapists/<int:user_id>/update-documents', methods=['POST'])
@login_required
def superadmin_update_therapist_documents(user_id):
    if not check_is_superadmin():
        return jsonify({'error': 'Acceso denegado. Se requieren permisos de superadministrador.'}), 403
        
    data = request.json or {}
    foto_titulo = data.get('foto_titulo')
    foto_documento = data.get('foto_documento')
    
    db = get_db()
    cursor = db.cursor()
    if foto_titulo is not None:
        cursor.execute("UPDATE usuarios SET foto_titulo = ? WHERE id = ?", (foto_titulo, user_id))
    if foto_documento is not None:
        cursor.execute("UPDATE usuarios SET foto_documento = ? WHERE id = ?", (foto_documento, user_id))
    db.commit()
    return jsonify({'success': 'Documento actualizado con éxito.'})

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
    if not check_is_superadmin():
        return jsonify({'error': 'Acceso denegado.'}), 403
        
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT id, usuario_id, rol_remitente, nombre_remitente, email_remitente, mensaje, fecha, leido FROM soporte ORDER BY id DESC")
    rows = cursor.fetchall()
    return jsonify([dict(r) for r in rows])

@app.route('/api/superadmin/support/<int:ticket_id>/mark-read', methods=['POST'])
@login_required
def superadmin_mark_ticket_read(ticket_id):
    if not check_is_superadmin():
        return jsonify({'error': 'Acceso denegado.'}), 403
        
    db = get_db()
    cursor = db.cursor()
    cursor.execute("UPDATE soporte SET leido = 1 WHERE id = ?", (ticket_id,))
    db.commit()
    return jsonify({'success': 'Ticket marcado como leído.'})

@app.route('/api/superadmin/support/<int:ticket_id>', methods=['DELETE'])
@login_required
def superadmin_delete_ticket(ticket_id):
    if not check_is_superadmin():
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
    user_activo = 1 if user_role == 'superadmin' else 0
    
    try:
        cursor.execute("""
            INSERT INTO usuarios (username, password_hash, nombres, apellidos, role, activo)
            VALUES (?, ?, 'Administrador', 'General', ?, ?)
        """, (username, password_hash, user_role, user_activo))
        db.commit()
        return jsonify({'success': f'Usuario {user_role} creado con éxito.'})
    except Exception as e:
        db.rollback()
        return jsonify({'error': f'Error al registrar administrador: {str(e)}'}), 500

@app.route('/api/login', methods=['POST'])
def login():
    try:
        data = request.json or {}
        username = (data.get('username') or '').strip()
        password = (data.get('password') or '').strip()
        
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
                            return jsonify({'error': 'Tu periodo de prueba gratis ha vencido. Contacta al administrador para activar tu suscripción.'}), 403
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
                'nombres': u_dict.get('nombres') or '',
                'apellidos': u_dict.get('apellidos') or '',
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
                    'pizarra': u_dict.get('bloqueo_pizarra', 0),
                    'herramientas': u_dict.get('bloqueo_herramientas', 1),
                    'confirmaciones': u_dict.get('bloqueo_confirmaciones', 1),
                    'examen_mental': u_dict.get('bloqueo_examen_mental', 1),
                    'tests': u_dict.get('bloqueo_tests', 1)
                }
            })
        
        return jsonify({'error': 'Credenciales inválidas.'}), 401
    except Exception as e:
        return jsonify({'error': f'Error en el servidor al iniciar sesión: {str(e)}'}), 500

def create_automatic_backup():
    try:
        backup_dir = os.path.join(BASE_DIR, 'backups')
        if not os.path.exists(backup_dir):
            os.makedirs(backup_dir)
        stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        backup_path = os.path.join(backup_dir, f"copia_seguridad_clinica_{stamp}.db")
        db = get_db()
        backup_conn = sqlite3.connect(backup_path)
        db.backup(backup_conn)
        backup_conn.close()
        
        # Limpieza inteligente: mantener solo los últimos 30 respaldos automáticos
        import glob
        b_files = sorted(glob.glob(os.path.join(backup_dir, "copia_seguridad_clinica_*.db")))
        if len(b_files) > 30:
            for old_f in b_files[:-30]:
                try:
                    os.remove(old_f)
                except Exception:
                    pass
        return backup_path
    except Exception as e:
        print(f"Error creando backup automático: {e}")
        return None

@app.route('/logout', methods=['GET', 'POST'])
@app.route('/api/logout', methods=['GET', 'POST'])
def logout():
    try:
        create_automatic_backup()
    except Exception as e:
        print(f"Error en backup de logout: {e}")
    session.clear()
    session.modified = True
    if request.method == 'GET':
        return redirect('/login')
    return jsonify({'success': 'Sesión cerrada y copia de seguridad creada automáticamente.'})

@app.route('/api/sync/auto-backup', methods=['POST', 'GET'])
def auto_backup():
    path = create_automatic_backup()
    return jsonify({'success': True, 'backup': path})

@app.route('/api/cron/hourly-tool-reminders', methods=['GET', 'POST'])
def cron_hourly_tool_reminders():
    try:
        count = send_hourly_patient_tool_reminders()
        return jsonify({'success': True, 'reminders_sent': count})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

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
            SELECT * FROM usuarios WHERE id = ?
        """, (session['user_id'],))
        row = cursor.fetchone()
        
        if row:
            r_dict = dict(row)
        else:
            r_dict = {}

        role = r_dict.get('role', 'psicologo')
        activo = r_dict.get('activo', 1)
        aviso_pago = r_dict.get('aviso_pago', 0)
        p_inicio = r_dict.get('primer_inicio', 1) if r_dict.get('primer_inicio') is not None else 1
        s_paga = r_dict.get('suscripcion_paga', 0) if r_dict.get('suscripcion_paga') is not None else 0
        f_exp = r_dict.get('fecha_expiracion_prueba', '')
        nombres = r_dict.get('nombres', '')
        apellidos = r_dict.get('apellidos', '')
        
        return jsonify({
            'logged_in': True,
            'role': role,
            'activo': activo,
            'aviso_pago': aviso_pago,
            'primer_inicio': p_inicio,
            'suscripcion_paga': s_paga,
            'fecha_expiracion_prueba': f_exp,
            'username': session['username'],
            'nombres': nombres,
            'apellidos': apellidos,
            'user_id': session['user_id'],
            'bloqueos': {
                'registro': r_dict.get('bloqueo_registro', 0),
                'evoluciones': r_dict.get('bloqueo_evoluciones', 0),
                'finanzas': r_dict.get('bloqueo_finanzas', 0),
                'agenda': r_dict.get('bloqueo_agenda', 0),
                'mensajes': r_dict.get('bloqueo_mensajes', 0),
                'pizarra': r_dict.get('bloqueo_pizarra', 0),
                'herramientas': r_dict.get('bloqueo_herramientas', 0),
                'confirmaciones': r_dict.get('bloqueo_confirmaciones', 0)
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

@app.route('/api/patient/update-timezone', methods=['POST'])
@patient_login_required
def update_patient_timezone():
    data = request.json or {}
    tz_name = data.get('timezone', 'America/Caracas').strip()
    offset_min = data.get('utc_offset', 240)
    try:
        offset_min = int(offset_min)
    except Exception:
        offset_min = 240

    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        UPDATE pacientes SET zona_horaria = ?, utc_offset = ? WHERE id = ?
    """, (tz_name, offset_min, session['patient_id']))
    db.commit()
    return jsonify({'success': 'Zona horaria de paciente actualizada.'})

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
        pwd_lower = (password or '').strip().lower()
        ced_lower = (patient['cedula'] or '').strip().lower()
        usr_lower = (patient['username'] or '').strip().lower()
        clean_pwd = clean_digits_only(password)
        clean_ced = clean_digits_only(patient['cedula'])
        clean_usr = clean_digits_only(patient['username'])
        
        is_default = (
            pwd_lower == ced_lower or 
            pwd_lower == usr_lower or 
            (clean_pwd != '' and clean_pwd == clean_ced) or 
            (clean_pwd != '' and clean_pwd == clean_usr)
        )
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
        
        try:
            sync_patient_to_firebase(patient_id)
        except Exception as _sync_err:
            print(f"Error en sync_patient_to_firebase: {_sync_err}")
        
        return jsonify({'success': 'Perfil e historia clínica configurados con éxito. Sesión iniciada.'})
    except Exception as e:
        return jsonify({'error': f'Error al configurar perfil: {str(e)}'}), 500

@app.route('/api/auth/get-security-questions', methods=['POST'])
def get_security_questions():
    data = request.json or {}
    username = (data.get('username') or '').strip()
    
    if not username:
        return jsonify({'error': 'Usuario es requerido.'}), 400
        
    db = get_db()
    cursor = db.cursor()

    # 1. Buscar en usuarios (psicólogos/admin)
    cursor.execute("""
        SELECT pregunta_seguridad_1, pregunta_seguridad_2 
        FROM usuarios 
        WHERE LOWER(username) = ?
    """, (username.lower(),))
    user_row = cursor.fetchone()

    if user_row and user_row['pregunta_seguridad_1'] and user_row['pregunta_seguridad_2']:
        return jsonify({
            'found': True,
            'pregunta_1': user_row['pregunta_seguridad_1'],
            'pregunta_2': user_row['pregunta_seguridad_2']
        })

    # 2. Buscar en pacientes
    cursor.execute("""
        SELECT pregunta_seguridad_1, pregunta_seguridad_2 
        FROM pacientes 
        WHERE LOWER(username) = ? OR cedula = ?
    """, (username.lower(), username))
    patient_row = cursor.fetchone()

    if patient_row and patient_row['pregunta_seguridad_1'] and patient_row['pregunta_seguridad_2']:
        return jsonify({
            'found': True,
            'pregunta_1': patient_row['pregunta_seguridad_1'],
            'pregunta_2': patient_row['pregunta_seguridad_2']
        })

    return jsonify({'error': 'El usuario no tiene configuradas preguntas de seguridad o no existe.'}), 404

@app.route('/api/auth/reset-password', methods=['POST'])
def auth_reset_password():
    data = request.json or {}
    username = (data.get('username') or '').strip()
    respuesta_1 = (data.get('respuesta_1') or '').strip().lower()
    respuesta_2 = (data.get('respuesta_2') or '').strip().lower()
    new_password = (data.get('new_password') or '').strip()
    send_via_email = bool(data.get('send_via_email'))
    
    if not username or not respuesta_1 or not respuesta_2:
        return jsonify({'error': 'Todos los campos de preguntas de seguridad son obligatorios.'}), 400

    if not send_via_email and (not new_password or len(new_password) < 6):
        return jsonify({'error': 'La nueva contraseña debe tener al menos 6 caracteres.'}), 400

    db = get_db()
    cursor = db.cursor()

    # 1. Intentar en usuarios (psicólogos/admin)
    cursor.execute("""
        SELECT id, username, nombres, apellidos, email, email_publico, respuesta_seguridad_1_hash, respuesta_seguridad_2_hash 
        FROM usuarios 
        WHERE LOWER(username) = ?
    """, (username.lower(),))
    user_row = cursor.fetchone()

    if user_row and user_row['respuesta_seguridad_1_hash'] and user_row['respuesta_seguridad_2_hash']:
        match_1 = check_password_hash(user_row['respuesta_seguridad_1_hash'], respuesta_1)
        match_2 = check_password_hash(user_row['respuesta_seguridad_2_hash'], respuesta_2)
        if match_1 and match_2:
            target_email = user_row['email'] or user_row['email_publico'] or (user_row['username'] if '@' in user_row['username'] else None)
            
            if send_via_email:
                if not target_email:
                    return jsonify({'error': 'Este usuario no tiene un correo electrónico registrado en su perfil para enviar las credenciales. Utiliza la opción de Restablecer Contraseña.'}), 400
                import random
                rand_num = random.randint(1000, 9999)
                final_pass = f"Espacio#{rand_num}"
                new_hash = generate_password_hash(final_pass)
                cursor.execute("UPDATE usuarios SET password_hash = ? WHERE id = ?", (new_hash, user_row['id']))
                db.commit()
                
                nom_comp = f"{user_row['nombres'] or ''} {user_row['apellidos'] or ''}".strip() or user_row['username']
                app_url = request.host_url.rstrip('/')
                html_msg = f"""
                <div style="font-family: Arial, sans-serif; max-width: 520px; margin: 0 auto; border: 1px solid #e2e8f0; border-radius: 16px; padding: 25px; background: #ffffff; box-shadow: 0 10px 25px rgba(0,0,0,0.05);">
                    <div style="text-align: center; margin-bottom: 20px; border-bottom: 2px solid #f1f5f9; padding-bottom: 15px;">
                        <h2 style="color: #702e5e; margin: 0; font-size: 1.4rem;">Espacio Terapéutico</h2>
                        <p style="color: #64748b; font-size: 0.85rem; margin: 4px 0 0 0;">Recuperación de Credenciales de Acceso</p>
                    </div>
                    <p style="color: #334155; font-size: 0.95rem;">Hola <strong>{nom_comp}</strong>,</p>
                    <p style="color: #475569; font-size: 0.9rem; line-height: 1.5;">Hemos procesado tu solicitud de recuperación de accesos mediante la verificación de tus preguntas de seguridad.</p>
                    
                    <div style="background: #fdf4ff; border-left: 4px solid #702e5e; padding: 16px; border-radius: 10px; margin: 20px 0;">
                        <div style="margin-bottom: 8px; font-size: 0.92rem; color: #334155;">👤 <strong>Usuario:</strong> <code style="font-size: 1rem; color: #702e5e; font-weight: 700;">{user_row['username']}</code></div>
                        <div style="font-size: 0.92rem; color: #334155;">🔑 <strong>Nueva Contraseña:</strong> <code style="font-size: 1.05rem; color: #059669; font-weight: 800;">{final_pass}</code></div>
                    </div>
                    
                    <p style="font-size: 0.82rem; color: #64748b; margin-top: 15px;">Te sugerimos iniciar sesión y actualizar tu contraseña desde la sección de ajustes de tu cuenta por una de tu preferencia.</p>
                    
                    <div style="text-align: center; margin-top: 25px;">
                        <a href="{app_url}/login" style="background: linear-gradient(135deg, #702e5e 0%, #58224a 100%); color: #ffffff; padding: 12px 24px; border-radius: 10px; text-decoration: none; font-weight: 700; display: inline-block; font-size: 0.9rem;">🔑 Iniciar Sesión Ahora</a>
                    </div>
                </div>
                """
                send_email_async(target_email, "🔑 Tus Credenciales de Acceso - Espacio Terapéutico", html_msg)
                
                parts = target_email.split('@')
                masked = parts[0][0] + '***' + parts[0][-1] + '@' + parts[1] if len(parts[0]) > 2 else target_email
                return jsonify({'success': f'¡Credenciales enviadas con éxito a tu correo ({masked})! Revisa tu bandeja de entrada o spam.'})
            else:
                new_hash = generate_password_hash(new_password)
                cursor.execute("UPDATE usuarios SET password_hash = ? WHERE id = ?", (new_hash, user_row['id']))
                db.commit()
                return jsonify({'success': 'Contraseña restablecida con éxito. Ya puedes iniciar sesión.'})
        else:
            return jsonify({'error': 'Respuestas a preguntas de seguridad incorrectas.'}), 401

    # 2. Intentar en pacientes
    cursor.execute("""
        SELECT id, username, nombres, apellidos, email, respuesta_seguridad_1_hash, respuesta_seguridad_2_hash 
        FROM pacientes 
        WHERE LOWER(username) = ? OR cedula = ?
    """, (username.lower(), username))
    patient_row = cursor.fetchone()

    if patient_row and patient_row['respuesta_seguridad_1_hash'] and patient_row['respuesta_seguridad_2_hash']:
        match_1 = check_password_hash(patient_row['respuesta_seguridad_1_hash'], respuesta_1)
        match_2 = check_password_hash(patient_row['respuesta_seguridad_2_hash'], respuesta_2)
        if match_1 and match_2:
            target_email = patient_row['email'] or (patient_row['username'] if '@' in (patient_row['username'] or '') else None)
            
            if send_via_email:
                if not target_email:
                    return jsonify({'error': 'No tienes un correo electrónico registrado en tu perfil de consultante para enviar las credenciales. Utiliza la opción de Restablecer Contraseña.'}), 400
                import random
                rand_num = random.randint(1000, 9999)
                final_pass = f"Espacio#{rand_num}"
                new_hash = generate_password_hash(final_pass)
                cursor.execute("UPDATE pacientes SET password_hash = ? WHERE id = ?", (new_hash, patient_row['id']))
                db.commit()
                try:
                    import threading
                    threading.Thread(target=sync_patient_to_firebase, args=(patient_row['id'],)).start()
                except Exception:
                    pass

                nom_comp = f"{patient_row['nombres'] or ''} {patient_row['apellidos'] or ''}".strip() or patient_row['username']
                app_url = request.host_url.rstrip('/')
                html_msg = f"""
                <div style="font-family: Arial, sans-serif; max-width: 520px; margin: 0 auto; border: 1px solid #e2e8f0; border-radius: 16px; padding: 25px; background: #ffffff; box-shadow: 0 10px 25px rgba(0,0,0,0.05);">
                    <div style="text-align: center; margin-bottom: 20px; border-bottom: 2px solid #f1f5f9; padding-bottom: 15px;">
                        <h2 style="color: #702e5e; margin: 0; font-size: 1.4rem;">Espacio Terapéutico</h2>
                        <p style="color: #64748b; font-size: 0.85rem; margin: 4px 0 0 0;">Recuperación de Credenciales de Acceso (Consultante)</p>
                    </div>
                    <p style="color: #334155; font-size: 0.95rem;">Hola <strong>{nom_comp}</strong>,</p>
                    <p style="color: #475569; font-size: 0.9rem; line-height: 1.5;">Hemos procesado tu solicitud de recuperación de accesos a tu portal mediante tus preguntas de seguridad.</p>
                    
                    <div style="background: #fdf4ff; border-left: 4px solid #702e5e; padding: 16px; border-radius: 10px; margin: 20px 0;">
                        <div style="margin-bottom: 8px; font-size: 0.92rem; color: #334155;">👤 <strong>Usuario / Cédula:</strong> <code style="font-size: 1rem; color: #702e5e; font-weight: 700;">{patient_row['username']}</code></div>
                        <div style="font-size: 0.92rem; color: #334155;">🔑 <strong>Nueva Contraseña:</strong> <code style="font-size: 1.05rem; color: #059669; font-weight: 800;">{final_pass}</code></div>
                    </div>
                    
                    <p style="font-size: 0.82rem; color: #64748b; margin-top: 15px;">Te sugerimos iniciar sesión y actualizar esta contraseña desde tu perfil.</p>
                    
                    <div style="text-align: center; margin-top: 25px;">
                        <a href="{app_url}/login" style="background: linear-gradient(135deg, #702e5e 0%, #58224a 100%); color: #ffffff; padding: 12px 24px; border-radius: 10px; text-decoration: none; font-weight: 700; display: inline-block; font-size: 0.9rem;">🔑 Iniciar Sesión en mi Portal</a>
                    </div>
                </div>
                """
                send_email_async(target_email, "🔑 Tus Credenciales de Acceso - Espacio Terapéutico", html_msg)

                parts = target_email.split('@')
                masked = parts[0][0] + '***' + parts[0][-1] + '@' + parts[1] if len(parts[0]) > 2 else target_email
                return jsonify({'success': f'¡Credenciales enviadas con éxito a tu correo ({masked})! Revisa tu bandeja de entrada o spam.'})
            else:
                new_hash = generate_password_hash(new_password)
                cursor.execute("UPDATE pacientes SET password_hash = ? WHERE id = ?", (new_hash, patient_row['id']))
                db.commit()
                try:
                    import threading
                    threading.Thread(target=sync_patient_to_firebase, args=(patient_row['id'],)).start()
                except Exception:
                    pass
                return jsonify({'success': 'Contraseña restablecida con éxito. Ya puedes iniciar sesión.'})
        else:
            return jsonify({'error': 'Respuestas a preguntas de seguridad incorrectas.'}), 401

    return jsonify({'error': 'El usuario no existe o no tiene preguntas de seguridad configuradas.'}), 404

@app.route('/api/admin/security-questions', methods=['GET', 'POST'])
@login_required
def admin_security_questions():
    db = get_db()
    cursor = db.cursor()
    user_id = session['user_id']

    if request.method == 'GET':
        cursor.execute("SELECT pregunta_seguridad_1, pregunta_seguridad_2 FROM usuarios WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        return jsonify({
            'pregunta_seguridad_1': row['pregunta_seguridad_1'] if row else None,
            'pregunta_seguridad_2': row['pregunta_seguridad_2'] if row else None
        })

    data = request.json or {}
    p1 = (data.get('pregunta_seguridad_1') or '').strip()
    r1 = (data.get('respuesta_seguridad_1') or '').strip().lower()
    p2 = (data.get('pregunta_seguridad_2') or '').strip()
    r2 = (data.get('respuesta_seguridad_2') or '').strip().lower()

    if not p1 or not r1 or not p2 or not r2:
        return jsonify({'error': 'Las dos preguntas y respuestas son obligatorias.'}), 400

    r1_hash = generate_password_hash(r1)
    r2_hash = generate_password_hash(r2)

    cursor.execute("""
        UPDATE usuarios 
        SET pregunta_seguridad_1 = ?, respuesta_seguridad_1_hash = ?,
            pregunta_seguridad_2 = ?, respuesta_seguridad_2_hash = ?
        WHERE id = ?
    """, (p1, r1_hash, p2, r2_hash, user_id))
    db.commit()

    return jsonify({'success': 'Preguntas de seguridad de terapeuta guardadas con éxito.'})

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

        # Filtrar por modalidad requerida (soporta nombres como 'Horario Estándar', 'Horario Online', etc.)
        if req_mod_clean not in ('all', ''):
            is_match = False
            # 1. Coincidencia exacta de substring
            if (req_mod_clean in perf_mod_clean or perf_mod_clean in req_mod_clean or
                req_mod_clean in perf_nom_clean or perf_nom_clean in req_mod_clean):
                is_match = True
            # 2. Coincidencia de tipo Online / Presencial
            elif 'online' in req_mod_clean and ('online' in perf_mod_clean or 'online' in perf_nom_clean):
                is_match = True
            elif 'presencial' in req_mod_clean and ('presencial' in perf_mod_clean or 'presencial' in perf_nom_clean):
                is_match = True
            # 3. Horarios genéricos/estándar (sin etiqueta restrictiva específica): Aplican para cualquier modalidad
            elif not any(restrictive in perf_nom_clean or restrictive in perf_mod_clean for restrictive in ['online', 'presencial', 'uptaeb']):
                is_match = True
            
            if not is_match:
                continue

        dias_list = perf.get('dias', [])
        for d in dias_list:
            d_num = int(d.get('dia', -1))
            is_today = (d_num == day_num) or (d_num in (0, 7) and day_num in (0, 7))
            if is_today and d.get('activo', False):
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

    # Filtrar bloqueos de agenda específicos (Eventos Personales / Convocatorias)
    cursor.execute("""
        SELECT hora_inicio, hora_fin, todo_el_dia 
        FROM bloqueos_agenda_especificos 
        WHERE (fecha = ? OR fecha = ?) AND psicologo_id = ?
    """, (target_date_norm, alt_date_str, psicologo_id))
    blocks_rows = cursor.fetchall()

    if any(b['todo_el_dia'] == 1 for b in blocks_rows):
        return []

    # Validar horas de antelación
    limit_dt = datetime.now() + timedelta(hours=antelacion)

    valid_slots = []
    for slot_obj in candidate_slots:
        h = normalize_time_str(slot_obj["hora"])
        if h in booked_hours or slot_obj["hora"] in booked_hours:
            continue

        # Verificar si la hora cae dentro de un rango bloqueado
        slot_blocked = False
        for b in blocks_rows:
            if b['todo_el_dia'] == 1:
                slot_blocked = True
                break
            h_init = normalize_time_str(b['hora_inicio'])
            h_end = normalize_time_str(b['hora_fin'])
            if h_init and h_end and h_init <= h < h_end:
                slot_blocked = True
                break
        if slot_blocked:
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
            INSERT INTO notificaciones (user_id, tipo, titulo, mensaje, fecha, leida, link)
            VALUES (?, ?, ?, ?, ?, 0, ?)
        """, (psicologo_id, 'cita', 'Nueva Cita Agendada', f"{pac_nombre} ha agendado una consulta para el {fecha} a las {hora}.", fecha_notif, 'agenda'))
        
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
            INSERT INTO notificaciones (user_id, tipo, titulo, mensaje, fecha, leida, link)
            VALUES (?, ?, ?, ?, ?, 0, ?)
        """, (psicologo_id, 'cita', notif_title, notif_msg, fecha_notif, 'agenda'))
        
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
        cursor.execute("SELECT nombres, apellidos, psicologo_id FROM pacientes WHERE id = ?", (patient_id,))
        p_info = cursor.fetchone()
        pac_nombre = f"{p_info['nombres']} {p_info['apellidos']}" if p_info else "El consultante"
        psic_id = (p_info['psicologo_id'] if p_info and p_info['psicologo_id'] else 1)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        cursor.execute("""
            INSERT INTO notificaciones (user_id, tipo, titulo, mensaje, fecha, leida, link)
            VALUES (?, 'cita', '✅ Cita Confirmada', ?, ?, 0, 'agenda')
        """, (psic_id, f"{pac_nombre} ha confirmado su asistencia a la consulta del {appt['fecha']} a las {appt['hora']}.", now_str))
        
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
        
        cursor.execute("SELECT nombres, apellidos, psicologo_id FROM pacientes WHERE id = ?", (patient_id,))
        pac = cursor.fetchone()
        pac_nombre = f"{pac['nombres']} {pac['apellidos']}"
        psic_id = (pac['psicologo_id'] if pac and pac['psicologo_id'] else (psicologo_id or 1))
        
        fecha_notif = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
            INSERT INTO notificaciones (user_id, tipo, titulo, mensaje, fecha, leida, link)
            VALUES (?, ?, ?, ?, ?, 0, ?)
        """, (psic_id, 'cita', 'Cita Reprogramada por Paciente', f"{pac_nombre} ha reprogramado su consulta del {old_fecha} a las {old_hora} para la nueva fecha: {new_date} a las {new_hour}.", fecha_notif, 'agenda'))
        
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
        
        db = get_db()
        cursor = db.cursor()
        
        # Anti-duplicados: Evitar registros repetidos si se presiona varias veces o por reintentos de red
        if referencia and str(referencia).strip():
            cursor.execute("""
                SELECT id FROM pagos_notificados 
                WHERE paciente_id = ? AND referencia = ? AND estado = 'Pendiente de verificación'
            """, (patient_id, str(referencia).strip()))
            if cursor.fetchone():
                return jsonify({'success': 'El reporte de pago ya fue registrado anteriormente.', 'duplicate': True})
        else:
            cursor.execute("""
                SELECT id FROM pagos_notificados 
                WHERE paciente_id = ? AND monto = ? AND moneda = ? AND fecha = ? AND estado = 'Pendiente de verificación'
            """, (patient_id, monto, moneda, fecha))
            if cursor.fetchone():
                return jsonify({'success': 'El reporte de pago ya fue registrado anteriormente.', 'duplicate': True})

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
            INSERT INTO notificaciones (user_id, tipo, titulo, mensaje, fecha, leida, link)
            VALUES (?, ?, ?, ?, ?, 0, ?)
        """, (psicologo_id, 'pago', 'Nuevo Pago Notificado', f"{pac_nombre} notificó un pago de {monto} {moneda}.", fecha_notif, 'finance'))
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

def _ensure_pizarra_columns(cursor):
    try:
        cursor.execute("PRAGMA table_info(pizarra_terapeutica)")
        cols = [r[1] for r in cursor.fetchall()]
        if cols:
            if 'archivo_adjunto' not in cols:
                cursor.execute("ALTER TABLE pizarra_terapeutica ADD COLUMN archivo_adjunto TEXT")
            if 'estado_animo' not in cols:
                cursor.execute("ALTER TABLE pizarra_terapeutica ADD COLUMN estado_animo TEXT")
            if 'comentario_animo' not in cols:
                cursor.execute("ALTER TABLE pizarra_terapeutica ADD COLUMN comentario_animo TEXT")
            if 'emoji_animo' not in cols:
                cursor.execute("ALTER TABLE pizarra_terapeutica ADD COLUMN emoji_animo TEXT")
            if 'respuesta_psicologo' not in cols:
                cursor.execute("ALTER TABLE pizarra_terapeutica ADD COLUMN respuesta_psicologo TEXT")
            if 'fecha_respuesta' not in cols:
                cursor.execute("ALTER TABLE pizarra_terapeutica ADD COLUMN fecha_respuesta TEXT")
    except Exception as _e:
        print("Error al asegurar columnas de pizarra:", _e)

@app.route('/api/patient/pizarra', methods=['GET', 'POST'])
@patient_login_required
def patient_pizarra():
    patient_id = session['patient_id']
    db = get_db()
    cursor = db.cursor()
    _ensure_pizarra_columns(cursor)
    
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
            pac_nombre = f"{pac['nombres']} {pac['apellidos']}".strip() if pac else "Consultante"
            psicologo_id = (pac['psicologo_id'] if pac and pac['psicologo_id'] else 1)
            
            titulo_notif = "Registro de Estado de Ánimo" if estado_animo else "Actualización de Pizarra"
            mensaje_notif = f"{pac_nombre} registró su estado de ánimo: {emoji_animo} {estado_animo}." if estado_animo else f"{pac_nombre} escribió una reflexión en su pizarra terapéutica."

            cursor.execute("""
                INSERT INTO notificaciones (user_id, tipo, titulo, mensaje, fecha, leida, link)
                VALUES (?, ?, ?, ?, ?, 0, ?)
            """, (psicologo_id, 'pizarra', titulo_notif, mensaje_notif, fecha_actual, 'pizarra-visual'))
            
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
                SELECT id, fecha, contenido, archivo_adjunto, estado_animo, comentario_animo, emoji_animo, respuesta_psicologo, fecha_respuesta FROM pizarra_terapeutica
                WHERE paciente_id = ?
                ORDER BY fecha DESC
            """, (patient_id,))
            rows = cursor.fetchall()
            updates = []
            for r in rows:
                r_keys = r.keys() if hasattr(r, 'keys') else []
                updates.append({
                    'id': r['id'],
                    'fecha': r['fecha'],
                    'contenido': r['contenido'],
                    'archivo_adjunto': r['archivo_adjunto'] if 'archivo_adjunto' in r_keys else None,
                    'estado_animo': r['estado_animo'] if 'estado_animo' in r_keys else None,
                    'comentario_animo': r['comentario_animo'] if 'comentario_animo' in r_keys else None,
                    'emoji_animo': r['emoji_animo'] if 'emoji_animo' in r_keys else None,
                    'respuesta_psicologo': r['respuesta_psicologo'] if 'respuesta_psicologo' in r_keys else None,
                    'fecha_respuesta': r['fecha_respuesta'] if 'fecha_respuesta' in r_keys else None
                })
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
        "psicologo_id": patient["psicologo_id"] or 1,
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

    cursor.execute(f"""
        SELECT resumen_paciente, anotaciones_proxima, tareas_asignadas, recursos_entregados, archivo_adjunto
        FROM sesiones
        WHERE paciente_id IN ({placeholders})
        ORDER BY fecha DESC, id DESC LIMIT 1
    """, all_pat_ids)
    last_session = cursor.fetchone()
    
    res_pac_dec = decrypt_clinical_text(last_session["resumen_paciente"]) if (last_session and last_session["resumen_paciente"]) else ""
    temas_prox_dec = decrypt_clinical_text(last_session["anotaciones_proxima"]) if (last_session and last_session["anotaciones_proxima"]) else ""

    compartido = {
        "resumen_sesion": res_pac_dec,
        "temas_proxima_sesion": temas_prox_dec,
        "tareas_asignadas": last_session["tareas_asignadas"] if last_session and last_session["tareas_asignadas"] else "",
        "recursos_entregados": last_session["recursos_entregados"] if last_session and last_session["recursos_entregados"] else "",
        "archivo_adjunto": last_session["archivo_adjunto"] if last_session and last_session["archivo_adjunto"] else ""
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
    try:
        db = get_db()
        cursor = db.cursor()
        vapid_keys = get_vapid_keys(cursor)
        return jsonify({'public_key': vapid_keys.get('vapid_public_key', '')})
    except Exception as e:
        print(f"Error fetching public key: {e}")
        return jsonify({'public_key': ''})

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

@app.route('/api/admin/payments/delete/<int:payment_id>', methods=['POST', 'DELETE'])
@login_required
def delete_admin_payment_notified(payment_id):
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("DELETE FROM pagos_notificados WHERE id = ?", (payment_id,))
        db.commit()
        return jsonify({'success': 'Notificación de pago eliminada correctamente.'})
    except Exception as e:
        return jsonify({'error': f'Error al eliminar notificación de pago: {str(e)}'}), 500

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
    _ensure_pizarra_columns(cursor)
    psic_id = get_psicologo_id_filter()
    
    try:
        if patient_id:
            if psic_id is not None:
                cursor.execute("""
                    SELECT p.id, p.paciente_id, p.fecha, p.contenido, p.archivo_adjunto, p.estado_animo, p.comentario_animo, p.emoji_animo, p.respuesta_psicologo, p.fecha_respuesta, pac.nombres, pac.apellidos
                    FROM pizarra_terapeutica p
                    JOIN pacientes pac ON p.paciente_id = pac.id
                    WHERE p.paciente_id = ? AND pac.psicologo_id = ?
                    ORDER BY p.fecha DESC
                """, (patient_id, psic_id))
            else:
                cursor.execute("""
                    SELECT p.id, p.paciente_id, p.fecha, p.contenido, p.archivo_adjunto, p.estado_animo, p.comentario_animo, p.emoji_animo, p.respuesta_psicologo, p.fecha_respuesta, pac.nombres, pac.apellidos
                    FROM pizarra_terapeutica p
                    JOIN pacientes pac ON p.paciente_id = pac.id
                    WHERE p.paciente_id = ?
                    ORDER BY p.fecha DESC
                """, (patient_id,))
        else:
            if psic_id is not None:
                cursor.execute("""
                    SELECT p.id, p.paciente_id, p.fecha, p.contenido, p.archivo_adjunto, p.estado_animo, p.comentario_animo, p.emoji_animo, p.respuesta_psicologo, p.fecha_respuesta, pac.nombres, pac.apellidos
                    FROM pizarra_terapeutica p
                    JOIN pacientes pac ON p.paciente_id = pac.id
                    WHERE pac.psicologo_id = ?
                    ORDER BY p.fecha DESC
                """, (psic_id,))
            else:
                cursor.execute("""
                    SELECT p.id, p.paciente_id, p.fecha, p.contenido, p.archivo_adjunto, p.estado_animo, p.comentario_animo, p.emoji_animo, p.respuesta_psicologo, p.fecha_respuesta, pac.nombres, pac.apellidos
                    FROM pizarra_terapeutica p
                    JOIN pacientes pac ON p.paciente_id = pac.id
                    ORDER BY p.fecha DESC
                """)
            
        rows = cursor.fetchall()
        updates = []
        for r in rows:
            r_keys = r.keys() if hasattr(r, 'keys') else []
            updates.append({
                'id': r['id'],
                'paciente_id': r['paciente_id'],
                'fecha': r['fecha'],
                'contenido': r['contenido'],
                'archivo_adjunto': r['archivo_adjunto'] if 'archivo_adjunto' in r_keys else None,
                'estado_animo': r['estado_animo'] if 'estado_animo' in r_keys else None,
                'comentario_animo': r['comentario_animo'] if 'comentario_animo' in r_keys else None,
                'emoji_animo': r['emoji_animo'] if 'emoji_animo' in r_keys else None,
                'respuesta_psicologo': r['respuesta_psicologo'] if 'respuesta_psicologo' in r_keys else None,
                'fecha_respuesta': r['fecha_respuesta'] if 'fecha_respuesta' in r_keys else None,
                'paciente_nombre': f"{r['nombres']} {r['apellidos']}"
            })
        
        return jsonify({'updates': updates})
    except Exception as e:
        return jsonify({'error': f'Error al obtener pizarra para el administrador: {str(e)}'}), 500

@app.route('/api/admin/pizarra/reply', methods=['POST'])
@login_required
def admin_pizarra_reply():
    data = request.json or {}
    update_id = data.get('update_id')
    respuesta = data.get('respuesta', '').strip()
    
    if not update_id or not respuesta:
        return jsonify({'error': 'Faltan parámetros requeridos (update_id, respuesta).'}), 400
        
    db = get_db()
    cursor = db.cursor()
    _ensure_pizarra_columns(cursor)
    
    from datetime import datetime
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    try:
        cursor.execute("""
            UPDATE pizarra_terapeutica
            SET respuesta_psicologo = ?, fecha_respuesta = ?
            WHERE id = ?
        """, (respuesta, fecha_actual, update_id))
        
        cursor.execute("SELECT paciente_id FROM pizarra_terapeutica WHERE id = ?", (update_id,))
        row = cursor.fetchone()
        if row:
            patient_id = row['paciente_id']
            cursor.execute("""
                INSERT INTO notificaciones (user_id, tipo, titulo, mensaje, fecha, leida, link)
                VALUES (?, ?, ?, ?, ?, 0, ?)
            """, (patient_id, 'pizarra', '💬 Tu Psicólogo/a respondió en tu Pizarra Terapéutica', f'Tu psicólogo/a ha respondido a tu apunte: "{respuesta[:60]}..."', fecha_actual, 'pizarra-terapeutica'))
            
        db.commit()
        return jsonify({'success': 'Respuesta registrada con éxito.', 'fecha_respuesta': fecha_actual, 'respuesta_psicologo': respuesta})
    except Exception as e:
        return jsonify({'error': f'Error al guardar respuesta: {str(e)}'}), 500

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
                WHERE tipo NOT IN ('herramienta_paciente', 'recordatorio_cita_paciente')
                  AND (user_id = ? OR (user_id IS NULL AND ? = 1)) AND leida = 0
                ORDER BY fecha DESC, id DESC LIMIT 25
            """, (psic_id, psic_id))
            rows = cursor.fetchall()
            
            cursor.execute("""
                SELECT COUNT(id) FROM notificaciones 
                WHERE tipo NOT IN ('herramienta_paciente', 'recordatorio_cita_paciente')
                  AND (user_id = ? OR (user_id IS NULL AND ? = 1)) AND leida = 0
            """, (psic_id, psic_id))
            unread_count = cursor.fetchone()[0] or 0
        else:
            cursor.execute("""
                SELECT id, tipo, titulo, mensaje, fecha, leida, link
                FROM notificaciones
                WHERE tipo NOT IN ('herramienta_paciente', 'recordatorio_cita_paciente') AND leida = 0
                ORDER BY fecha DESC, id DESC LIMIT 25
            """)
            rows = cursor.fetchall()
            cursor.execute("SELECT COUNT(id) FROM notificaciones WHERE tipo NOT IN ('herramienta_paciente', 'recordatorio_cita_paciente') AND leida = 0")
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
            cursor.execute("UPDATE notificaciones SET leida = 1 WHERE id = ?", (notification_id,))
        else:
            if psic_id is not None:
                cursor.execute("""
                    UPDATE notificaciones SET leida = 1 
                    WHERE tipo NOT IN ('herramienta_paciente', 'recordatorio_cita_paciente') 
                      AND (user_id = ? OR (user_id IS NULL AND ? = 1))
                """, (psic_id, psic_id))
            else:
                cursor.execute("UPDATE notificaciones SET leida = 1 WHERE tipo NOT IN ('herramienta_paciente', 'recordatorio_cita_paciente')")
        db.commit()
        return jsonify({'success': 'Notificación marcada como leída.'})
    except Exception as e:
        return jsonify({'error': f'Error al marcar notificaciones: {str(e)}'}), 500

@app.route('/api/admin/message-templates', methods=['GET', 'POST'])
@login_required
def admin_message_templates():
    db = get_db()
    cursor = db.cursor()
    
    keys = ['msg_confirmacion', 'msg_confirmacion_ok', 'msg_cancelacion_ok', 'msg_recordatorio', 'msg_reagendamiento', 'msg_cierre', 'auto_reagendamiento_activo', 'msg_cumpleanos', 'auto_cumpleanos_activo']
    
    if request.method == 'GET':
        templates = {}
        for key in keys:
            cursor.execute("SELECT valor FROM configuracion WHERE clave = ?", (key,))
            row = cursor.fetchone()
            templates[key] = row['valor'] if row else ""
        return jsonify(templates)
        
    data = request.json
    try:
        for key in keys:
            if key in data:
                cursor.execute("INSERT OR REPLACE INTO configuracion (clave, valor) VALUES (?, ?)", (key, data[key]))
        db.commit()
        return jsonify({'success': 'Plantillas de mensajes actualizadas con éxito.'})
    except Exception as e:
        return jsonify({'error': f'Error al actualizar plantillas: {str(e)}'}), 500

@app.route('/api/admin/smtp-settings', methods=['GET', 'POST'])
@login_required
def admin_smtp_settings():
    db = get_db()
    cursor = db.cursor()
    
    keys = ['smtp_host', 'smtp_port', 'smtp_user', 'smtp_password', 'smtp_from_email', 'auto_welcome_email_active']
    
    if request.method == 'GET':
        settings = {}
        for key in keys:
            cursor.execute("SELECT valor FROM configuracion WHERE clave = ?", (key,))
            row = cursor.fetchone()
            settings[key] = row['valor'] if row else ""
        if not settings.get('smtp_host'):
            settings['smtp_host'] = 'smtp.gmail.com'
        if not settings.get('smtp_port'):
            settings['smtp_port'] = '587'
        if not settings.get('smtp_user'):
            settings['smtp_user'] = 'espacioterapeuticoapp@gmail.com'
        if not settings.get('smtp_password'):
            settings['smtp_password'] = 'kinygwxtkovrtsjp'
        if not settings.get('smtp_from_email'):
            settings['smtp_from_email'] = 'Espacio Terapéutico <espacioterapeuticoapp@gmail.com>'
        if not settings.get('auto_welcome_email_active'):
            settings['auto_welcome_email_active'] = '1'
        return jsonify(settings)
        
    data = request.json or {}
    try:
        for key in keys:
            if key in data:
                cursor.execute("INSERT OR REPLACE INTO configuracion (clave, valor) VALUES (?, ?)", (key, str(data[key]).strip()))
        db.commit()
        return jsonify({'success': 'Configuración de servidor SMTP actualizada con éxito.'})
    except Exception as e:
        return jsonify({'error': f'Error al guardar configuración SMTP: {str(e)}'}), 500

@app.route('/api/admin/smtp-test', methods=['POST'])
@login_required
def admin_smtp_test():
    data = request.json or {}
    test_email = data.get('test_email', '').strip()
    if not test_email or '@' not in test_email:
        return jsonify({'error': 'Proporciona una dirección de correo válida para la prueba.'}), 400

    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT clave, valor FROM configuracion 
        WHERE clave IN ('smtp_host', 'smtp_port', 'smtp_user', 'smtp_password', 'smtp_from_email')
    """)
    cfg = {r['clave']: r['valor'] for r in cursor.fetchall()}
    
    smtp_host = data.get('smtp_host') or cfg.get('smtp_host', '').strip()
    smtp_port_raw = str(data.get('smtp_port') or cfg.get('smtp_port', '587')).strip()
    smtp_port = int(smtp_port_raw) if smtp_port_raw.isdigit() else 587
    smtp_user = data.get('smtp_user') or cfg.get('smtp_user', '').strip()
    smtp_pass = data.get('smtp_password') or cfg.get('smtp_password', '').strip()
    smtp_from = data.get('smtp_from_email') or cfg.get('smtp_from_email', '').strip() or f"Espacio Terapéutico <{smtp_user}>"

    if not smtp_host or not smtp_user or not smtp_pass:
        return jsonify({'error': 'Incompleto. Servidor Host, Usuario y Contraseña SMTP son requeridos.'}), 400

    try:
        import smtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        msg = MIMEMultipart('alternative')
        msg['Subject'] = "🧪 Prueba de Conexión SMTP - Espacio Terapéutico"
        msg['From'] = smtp_from
        msg['To'] = test_email

        html_body = f"""
        <div style="font-family: Arial, sans-serif; padding: 20px; background: #f4f6f9;">
            <div style="max-width: 500px; margin: 0 auto; background: #fff; padding: 24px; border-radius: 12px; border: 1px solid #10b981;">
                <h2 style="color: #10b981; margin-top: 0;">✅ Servidor de Correo Operativo</h2>
                <p>¡Hola! Este es un correo de prueba enviado exitosamente desde <strong>Espacio Terapéutico</strong>.</p>
                <p><strong>Configuración Verificada:</strong></p>
                <ul>
                    <li>Servidor: <code>{smtp_host}:{smtp_port}</code></li>
                    <li>Usuario Remitente: <code>{smtp_user}</code></li>
                </ul>
                <p style="font-size: 12px; color: #64748b;">Tu plataforma ya está lista para enviar credenciales y notificaciones a psicólogos y consultantes.</p>
            </div>
        </div>
        """
        msg.attach(MIMEText(html_body, 'html', 'utf-8'))

        if smtp_port == 465:
            server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=12)
        else:
            server = smtplib.SMTP(smtp_host, smtp_port, timeout=12)
            server.starttls()

        server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_user, [test_email], msg.as_string())
        server.quit()

        return jsonify({'success': f'¡Correo de prueba enviado con éxito a {test_email}!'})
    except Exception as e:
        return jsonify({'error': f'Falló la conexión SMTP: {str(e)}'}), 500

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
        
        # Sincronizar actualización de métodos de pago en todos sus consultantes en Firebase
        sync_all_psychologist_patients_to_firebase(user_id)
        
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

@app.route('/api/public/landing-content', methods=['GET'])
def get_public_landing_content():
    """Obtiene el contenido editable de la portada principal y el directorio público de psicólogos."""
    db = get_db()
    ensure_usuarios_columns(db)
    cursor = db.cursor()
    
    # 1. Textos institucionales editables por el Superadmin
    cursor.execute("SELECT clave, valor FROM configuracion WHERE clave LIKE 'landing_%'")
    cfg_rows = cursor.fetchall()
    content = {r['clave']: r['valor'] for r in cfg_rows}
    
    # 2. Directorio de psicólogos activos (excluye cuenta de sistema 'admin')
    cursor.execute("""
        SELECT id, nombres, apellidos, username, slug, estudios, foto_titulo, foto_documento,
               nomenclatura, descripcion_biografia, modalidades_json, whatsapp_publico, email_publico, redes_sociales_json,
               especialidades, poblaciones_json, pais_ubicacion
        FROM usuarios 
        WHERE (COALESCE(activo, 1) = 1) 
          AND (COALESCE(mostrar_en_directorio, 1) = 1) 
          AND (COALESCE(suscripcion_paga, 0) = 1 OR role = 'superadmin')
          AND (role IS NULL OR role = '' OR role = 'psicologo' OR role = 'admin' OR role = 'superadmin')
          AND LOWER(username) NOT IN ('admin', 'superadmin')
        ORDER BY id ASC
    """)
    therapists_rows = cursor.fetchall()
    therapists = []
    for t in therapists_rows:
        slug = generate_default_slug_for_user(t)
        modalidades = json.loads(t['modalidades_json']) if t['modalidades_json'] else ["Online", "Presencial"]
        redes = json.loads(t['redes_sociales_json']) if t['redes_sociales_json'] else {}
        
        poblaciones = ["Adultos", "Adolescentes"]
        if t['poblaciones_json']:
            try:
                poblaciones = json.loads(t['poblaciones_json'])
            except Exception:
                pass

        therapists.append({
            'id': t['id'],
            'nombres': t['nombres'] or 'Psicólogo',
            'apellidos': t['apellidos'] or '',
            'nombre_completo': f"Psic. {t['nombres'] or ''} {t['apellidos'] or ''}".strip(),
            'slug': slug,
            'nomenclatura': t['nomenclatura'] or t['estudios'] or 'Psicólogo Clínico',
            'descripcion': t['descripcion_biografia'] or '',
            'foto': t['foto_titulo'] or '/static/logo.png',
            'modalidades': modalidades,
            'especialidades': t['especialidades'] or '',
            'poblaciones': poblaciones,
            'pais': t['pais_ubicacion'] or '',
            'whatsapp': t['whatsapp_publico'] or '',
            'email': t['email_publico'] or '',
            'redes': redes,
            'url_perfil': f"/psic.{slug.replace('psic.', '') if slug.startswith('psic.') else slug}",
            'url_agendar': f"/agendar/{slug}",
            'url_registro': f"/registro/{slug}"
        })
        
    resp = jsonify({
        'content': content,
        'therapists': therapists
    })
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    return resp

@app.route('/api/public/therapist/<path:slug>', methods=['GET'])
def get_public_therapist_profile(slug):
    db = get_db()
    ensure_usuarios_columns(db)
    cursor = db.cursor()
    psych = get_psychologist_by_id_or_slug(cursor, slug)
    if not psych:
        return jsonify({'error': 'Psicólogo no encontrado.'}), 404

    psych = dict(psych) if not isinstance(psych, dict) else psych

    modalidades_raw = psych.get('modalidades_json')
    modalidades_data = {}
    modalidades_list = []
    
    if modalidades_raw:
        try:
            parsed = json.loads(modalidades_raw)
            if isinstance(parsed, dict):
                modalidades_data = parsed
                if parsed.get('online'): modalidades_list.append("Online")
                if parsed.get('presencial'): modalidades_list.append("Presencial")
                if parsed.get('domicilio'): modalidades_list.append("Domicilio")
            elif isinstance(parsed, list):
                modalidades_list = parsed
                for m in parsed:
                    modalidades_data[str(m).lower()] = True
        except Exception:
            modalidades_list = ["Online", "Presencial"]
            modalidades_data = {'online': True, 'presencial': True}
    else:
        modalidades_list = ["Online", "Presencial"]
        modalidades_data = {'online': True, 'presencial': True}

    try:
        redes_raw = psych.get('redes_sociales_json')
        redes = json.loads(redes_raw) if redes_raw else {}
    except Exception:
        redes = {}
        
    clean_slug = psych.get('slug') or generate_default_slug_for_user(psych)
    foto_url = psych.get('foto_perfil') or psych.get('foto_titulo') or '/static/logo.png'
    
    poblaciones = ["Adultos", "Adolescentes"]
    if psych.get('poblaciones_json'):
        try:
            poblaciones = json.loads(psych.get('poblaciones_json'))
        except Exception:
            pass

    resp = jsonify({
        'id': psych.get('id'),
        'nombres': psych.get('nombres') or '',
        'apellidos': psych.get('apellidos') or '',
        'nombre_completo': f"Psic. {psych.get('nombres') or ''} {psych.get('apellidos') or ''}".strip(),
        'slug': clean_slug,
        'nomenclatura': psych.get('nomenclatura') or psych.get('estudios') or 'Psicólogo Clínico',
        'descripcion_biografia': psych.get('descripcion_biografia') or '',
        'foto': foto_url,
        'modalidades': modalidades_list,
        'modalidades_data': modalidades_data,
        'especialidades': psych.get('especialidades') or '',
        'poblaciones': poblaciones,
        'pais': psych.get('pais_ubicacion') or '',
        'whatsapp_publico': psych.get('whatsapp_publico') or '',
        'email_publico': psych.get('email_publico') or '',
        'redes_sociales': redes,
        'url_agendar': f"/agendar/{clean_slug}",
        'url_registro': f"/registro/{clean_slug}"
    })
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    return resp

@app.route('/api/admin/landing-content', methods=['POST'])
@login_required
def update_admin_landing_content():
    """Permite al Superadmin actualizar los textos dinámicos de la portada web."""
    if not check_is_superadmin():
        return jsonify({'error': 'No tienes permisos para modificar la portada web.'}), 403
        
    data = request.json or {}
    db = get_db()
    cursor = db.cursor()
    
    allowed_keys = [
        'landing_hero_title', 'landing_hero_subtitle',
        'landing_quienes_somos', 'landing_mision', 'landing_vision',
        'landing_footer_text'
    ]
    
    try:
        for k in allowed_keys:
            if k in data:
                cursor.execute("INSERT OR REPLACE INTO configuracion (clave, valor) VALUES (?, ?)", (k, str(data[k])))
        db.commit()
        return jsonify({'success': 'Contenidos de la portada web actualizados exitosamente.'})
    except Exception as e:
        return jsonify({'error': f'Error al actualizar contenidos: {str(e)}'}), 500

@app.route('/api/admin/profile-public', methods=['GET', 'POST'])
@login_required
def admin_profile_public():
    """Permite a cada psicólogo personalizar su perfil público (foto, biografía, modalidades, WhatsApp, redes, especialidades, poblaciones, país)."""
    db = get_db()
    ensure_usuarios_columns(db)
    cursor = db.cursor()
    user_id = session['user_id']
    
    if request.method == 'GET':
        cursor.execute("""
            SELECT id, nombres, apellidos, username, slug, estudios, foto_titulo,
                   nomenclatura, descripcion_biografia, modalidades_json, whatsapp_publico, email_publico, redes_sociales_json,
                   especialidades, poblaciones_json, pais_ubicacion
            FROM usuarios WHERE id = ?
        """, (user_id,))
        u = cursor.fetchone()
        if not u:
            return jsonify({'error': 'Usuario no encontrado.'}), 404
            
        modalidades_raw = u['modalidades_json']
        modalidades_data = {}
        modalidades_list = []
        if modalidades_raw:
            try:
                parsed = json.loads(modalidades_raw)
                if isinstance(parsed, dict):
                    modalidades_data = parsed
                    if parsed.get('online'): modalidades_list.append("Online")
                    if parsed.get('presencial'): modalidades_list.append("Presencial")
                    if parsed.get('domicilio'): modalidades_list.append("Domicilio")
                elif isinstance(parsed, list):
                    modalidades_list = parsed
                    modalidades_data = {
                        'online': 'Online' in parsed,
                        'online_titulo': 'Consulta Online',
                        'online_detalle': '',
                        'presencial': 'Presencial' in parsed,
                        'presencial_titulo': 'Consulta Presencial',
                        'presencial_detalle': '',
                        'domicilio': 'Domicilio' in parsed,
                        'domicilio_titulo': 'Atención a Domicilio',
                        'domicilio_detalle': ''
                    }
            except Exception:
                modalidades_list = ["Online", "Presencial"]
                modalidades_data = {'online': True, 'online_titulo': 'Consulta Online', 'presencial': True, 'presencial_titulo': 'Consulta Presencial'}
        else:
            modalidades_list = ["Online", "Presencial"]
            modalidades_data = {'online': True, 'online_titulo': 'Consulta Online', 'presencial': True, 'presencial_titulo': 'Consulta Presencial'}

        redes = json.loads(u['redes_sociales_json']) if u['redes_sociales_json'] else {}
        
        poblaciones = ["Adultos", "Adolescentes"]
        if u['poblaciones_json']:
            try:
                poblaciones = json.loads(u['poblaciones_json'])
            except Exception:
                pass

        slug = u['slug'] or generate_default_slug_for_user(u)
        clean_slug = slug.replace('psic.', '') if slug.startswith('psic.') else slug

        return jsonify({
            'slug': slug,
            'clean_slug': clean_slug,
            'full_profile_url': f"/psic.{clean_slug}",
            'registration_url': f"/registro/psic.{clean_slug}",
            'fast_booking_url': f"/agendar/psic.{clean_slug}",
            'nomenclatura': u['nomenclatura'] or u['estudios'] or 'Psicólogo Clínico',
            'descripcion_biografia': u['descripcion_biografia'] or '',
            'modalidades': modalidades_list,
            'modalidades_data': modalidades_data,
            'especialidades': u['especialidades'] or '',
            'poblaciones': poblaciones,
            'pais_ubicacion': u['pais_ubicacion'] or '',
            'whatsapp_publico': u['whatsapp_publico'] or '',
            'email_publico': u['email_publico'] or '',
            'redes_sociales': redes,
            'foto': u['foto_titulo'] or '/static/logo.png'
        })
    else:
        data = request.json or {}
        nomenclatura = data.get('nomenclatura', '').strip()
        descripcion = data.get('descripcion_biografia', '').strip()
        
        mods_data = data.get('modalidades_data')
        if not mods_data:
            mods_data = data.get('modalidades', ["Online", "Presencial"])

        whatsapp = data.get('whatsapp_publico', '').strip()
        email = data.get('email_publico', '').strip()
        redes = data.get('redes_sociales', {})
        foto = data.get('foto', '')

        especialidades = data.get('especialidades', '').strip()
        poblaciones = data.get('poblaciones', ["Adultos", "Adolescentes"])
        pais_ubicacion = data.get('pais_ubicacion', '').strip()
        
        try:
            cursor.execute("""
                UPDATE usuarios SET 
                    nomenclatura = ?,
                    descripcion_biografia = ?,
                    modalidades_json = ?,
                    whatsapp_publico = ?,
                    email_publico = ?,
                    redes_sociales_json = ?,
                    especialidades = ?,
                    poblaciones_json = ?,
                    pais_ubicacion = ?,
                    foto_titulo = CASE WHEN ? != '' THEN ? ELSE foto_titulo END
                WHERE id = ?
            """, (nomenclatura, descripcion, json.dumps(mods_data), whatsapp, email, json.dumps(redes),
                  especialidades, json.dumps(poblaciones), pais_ubicacion, foto, foto, user_id))
            db.commit()
            return jsonify({'success': 'Perfil público actualizado exitosamente.'})
        except Exception as e:
            db.rollback()
            return jsonify({'error': f'Error al actualizar perfil: {str(e)}'}), 500

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
    Si la cuenta es superadmin puro (admin / AG), retorna -1 para garantizar que no tenga acceso a ningún paciente.
    De lo contrario, retorna session['user_id'] (o 1 por defecto).
    """
    role = session.get('role')
    user_id = session.get('user_id')
    username = session.get('username', '')
    
    if (role in ['admin', 'superadmin']) and (username.lower() != 'pamoraro' and user_id != 1):
        return -1
        
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
    
    role = session.get('role', '')
    user_id = session.get('user_id')
    psic_id = get_psicologo_id_filter()
    
    # Si el filtro retorna -1 para admins o no hay id, asegurar que traiga los pacientes
    if psic_id == -1 or psic_id is None:
        if role in ['admin', 'superadmin']:
            psic_id = None # Los administradores ven todos los pacientes del sistema
        else:
            psic_id = user_id if user_id else 1
    
    if search:
        query = "%" + search + "%"
        if psic_id is not None:
            cursor.execute("""
                SELECT id, nombres, apellidos, cedula, edad, genero, residencia_actual, pais, ciudad 
                FROM pacientes 
                WHERE (psicologo_id = ? OR psicologo_id IS NULL) AND (nombres LIKE ? OR apellidos LIKE ? OR cedula LIKE ?)
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
            cursor.execute("SELECT id, nombres, apellidos, cedula, edad, genero, residencia_actual, pais, ciudad FROM pacientes WHERE (psicologo_id = ? OR psicologo_id IS NULL) ORDER BY nombres ASC, apellidos ASC", (psic_id,))
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
    
    cursor.execute("SELECT username, cedula, psicologo_id FROM pacientes WHERE id = ?", (patient_id,))
    pac_info = cursor.fetchone()
    if not pac_info:
        return jsonify({'error': 'Paciente no encontrado.'}), 404
        
    if psic_id is not None and pac_info['psicologo_id'] != psic_id:
        return jsonify({'error': 'No tienes permisos para eliminar este paciente.'}), 403
        
    username_key = (pac_info['username'] or pac_info['cedula'] or '').strip()
    
    try:
        cursor.execute("DELETE FROM agenda_finanzas WHERE paciente_id = ?", (patient_id,))
        cursor.execute("DELETE FROM sesiones WHERE paciente_id = ?", (patient_id,))
        cursor.execute("DELETE FROM pizarra_terapeutica WHERE paciente_id = ?", (patient_id,))
        cursor.execute("DELETE FROM pagos_notificados WHERE paciente_id = ?", (patient_id,))
        cursor.execute("DELETE FROM pacientes WHERE id = ?", (patient_id,))
        db.commit()
        
        # Eliminar también de Firebase Realtime Database
        delete_patient_from_firebase(patient_id, username_key)
        
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
            SUM(CASE WHEN (estado_pago = 'Prepagada' AND control_uso = 'Consumida') OR (estado_pago = 'Paga' AND control_uso = 'Consumida') THEN cantidad_sesiones ELSE 0 END) as prepagadas_consumidas
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
            if deuda_monto_str:
                deuda_monto_str += " + "
            deuda_monto_str += f"{r['total']:,.2f} {r['moneda'] or 'USD'}"
    if not deuda_monto_str:
        deuda_monto_str = "0.00 USD"

    cursor.execute("""
        SELECT id, fecha, tipo_consulta, monto, moneda, estado_pago
        FROM agenda_finanzas
        WHERE paciente_id = ? AND estado_pago IN ('Pendiente', 'Cancelada sin aviso')
        ORDER BY fecha DESC, id DESC
    """, (patient_id,))
    deudas_detalle = [dict(row) for row in cursor.fetchall()]
    
    # 4. Conteo de sesiones por estado
    cursor.execute("""
        SELECT estado, COUNT(id) as cnt
        FROM sesiones
        WHERE paciente_id = ?
        GROUP BY estado
    """, (patient_id,))
    session_counts_raw = cursor.fetchall()
    session_counts = {'Realizada': 0, 'Cancelada': 0, 'Reprogramada': 0, 'Agendada': 0}
    for row in session_counts_raw:
        if row['estado'] in session_counts:
            session_counts[row['estado']] = row['cnt']

    patient_dict = dict(patient)
    for k in ['diagnostico', 'antecedentes_medicos_personales', 'antecedentes_psicologicos_personales']:
        if k in patient_dict and patient_dict[k]:
            patient_dict[k] = decrypt_clinical_text(patient_dict[k])
            
    last_session_dict = dict(last_session) if last_session else None
    if last_session_dict:
        for k in ['resumen', 'tareas_asignadas', 'anotaciones_proxima']:
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

@app.route('/api/patients/<int:patient_id>/adjust-prepay-balance', methods=['POST'])
@login_required
def adjust_patient_prepay_balance(patient_id):
    db = get_db()
    cursor = db.cursor()
    psic_id = get_psicologo_id_filter()
    
    if psic_id is not None:
        cursor.execute("SELECT id FROM pacientes WHERE id = ? AND psicologo_id = ?", (patient_id, psic_id))
    else:
        cursor.execute("SELECT id FROM pacientes WHERE id = ?", (patient_id,))
    if not cursor.fetchone():
        return jsonify({'error': 'Paciente no encontrado'}), 404
        
    data = request.json or {}
    nueva_cantidad = data.get('cantidad_disponible')
    if nueva_cantidad is None or not isinstance(nueva_cantidad, int) or nueva_cantidad < 0:
        return jsonify({'error': 'Debes ingresar un número entero válido (>= 0)'}), 400

    cursor.execute("""
        SELECT SUM(cantidad_sesiones) FROM agenda_finanzas 
        WHERE paciente_id = ? AND estado_pago = 'Prepagada' AND control_uso = 'No consumida'
    """, (patient_id,))
    actual_sum = cursor.fetchone()[0] or 0

    if nueva_cantidad == actual_sum:
        return jsonify({'success': True, 'nueva_cantidad': nueva_cantidad, 'message': 'El saldo ya es igual al valor indicado.'})

    if nueva_cantidad < actual_sum:
        diff = actual_sum - nueva_cantidad
        cursor.execute("""
            SELECT id, cantidad_sesiones, control_uso FROM agenda_finanzas
            WHERE paciente_id = ? AND estado_pago = 'Prepagada' AND control_uso = 'No consumida'
            ORDER BY id ASC
        """, (patient_id,))
        rows = cursor.fetchall()
        for r in rows:
            if diff <= 0:
                break
            r_cant = r['cantidad_sesiones'] or 1
            if r_cant <= diff:
                cursor.execute("UPDATE agenda_finanzas SET control_uso = 'Consumida' WHERE id = ?", (r['id'],))
                diff -= r_cant
            else:
                nuevas_ses = r_cant - diff
                cursor.execute("UPDATE agenda_finanzas SET cantidad_sesiones = ? WHERE id = ?", (nuevas_ses, r['id']))
                diff = 0
    else:
        diff = nueva_cantidad - actual_sum
        cursor.execute("""
            SELECT id, cantidad_sesiones FROM agenda_finanzas
            WHERE paciente_id = ? AND estado_pago = 'Prepagada' AND control_uso = 'No consumida'
            ORDER BY id DESC LIMIT 1
        """, (patient_id,))
        last_prep = cursor.fetchone()
        if last_prep:
            cursor.execute("UPDATE agenda_finanzas SET cantidad_sesiones = cantidad_sesiones + ? WHERE id = ?", (diff, last_prep['id']))
        else:
            from datetime import datetime
            now_date = datetime.now().strftime('%Y-%m-%d')
            cursor.execute("""
                INSERT INTO agenda_finanzas (paciente_id, fecha, hora, tipo_consulta, monto, estado_pago, control_uso, cantidad_sesiones, uso_sesiones_detalle)
                VALUES (?, ?, '00:00', 'Prepago', 0.0, 'Prepagada', 'No consumida', ?, 'Ajuste manual de saldo')
            """, (patient_id, now_date, diff))

    db.commit()
    try:
        sync_patient_to_firebase(patient_id)
    except Exception as s_err:
        print(f"Error sincronizando prepago a Firebase: {s_err}")
    return jsonify({'success': True, 'nueva_cantidad': nueva_cantidad, 'message': f'Saldo de consultas prepagadas ajustado exitosamente a {nueva_cantidad}.'})

@app.route('/api/patients/<int:patient_id>/print', methods=['GET'])
@login_required
def print_patient_card(patient_id):
    db = get_db()
    cursor = db.cursor()
    
    # 1. Obtener datos del paciente
    cursor.execute("SELECT * FROM pacientes WHERE id = ?", (patient_id,))
    patient_row = cursor.fetchone()
    if not patient_row:
        return "Paciente no encontrado", 404
        
    patient = dict(patient_row)
    if patient.get('diagnostico'):
        patient['diagnostico'] = decrypt_clinical_text(patient['diagnostico'])
        
    # 2. Obtener sesiones en orden cronológico
    cursor.execute("""
        SELECT fecha, modalidad, resumen, test_aplicados 
        FROM sesiones 
        WHERE paciente_id = ? AND estado = 'Realizada'
        ORDER BY fecha ASC, id ASC
    """, (patient_id,))
    raw_sessions = cursor.fetchall()
    sessions = []
    for s in raw_sessions:
        s_dict = dict(s)
        s_dict['resumen'] = decrypt_clinical_text(s_dict.get('resumen')) or ''
        s_dict['test_aplicados'] = decrypt_clinical_text(s_dict.get('test_aplicados')) or ''
        sessions.append(s_dict)
    
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
                    <button class="no-print-btn" onclick="window.print()">Imprimir Ficha / Guardar como PDF</button>
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
    return render_template_string(html_template, patient=patient, sessions=sessions)


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
                        fee_val, fee_curr = get_appointment_fee(cursor, patient_id, None, modalidad)
                        if fee_val > 0:
                            cursor.execute("""
                                UPDATE agenda_finanzas 
                                SET estado_pago = 'Pendiente', monto = ?, moneda = ?, metodo_pago = NULL, referencia = 'Sin saldo prepago'
                                WHERE id = ?
                            """, (fee_val, fee_curr or moneda, agenda_id))
                        else:
                            cursor.execute("""
                                UPDATE agenda_finanzas 
                                SET estado_pago = 'Paga', monto = 0.0, moneda = ?, metodo_pago = 'Exonerado', referencia = 'Sin saldo prepago'
                                WHERE id = ?
                            """, (moneda, agenda_id))
                    else:
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
            requests.post(f"{FIREBASE_DB_URL}/pacientes/{patient_id}/notificaciones.json", json=firebase_payload, timeout=2.0)
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
            requests.post(f"{FIREBASE_DB_URL}/pacientes/{patient_id}/notificaciones.json", json=firebase_payload, timeout=2.0)
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
            SELECT id, nombres, apellidos, cedula, pais, ciudad,
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
    now = get_now_vet()
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
        
        # Contar sesiones por modalidad desde la tabla de sesiones
        cursor.execute("""
            SELECT s.modalidad, COUNT(s.id)
            FROM sesiones s
            JOIN pacientes p ON s.paciente_id = p.id
            WHERE s.fecha LIKE ? AND p.psicologo_id = ?
            GROUP BY s.modalidad
        """, (date_prefix, psic_id))
        ses_counts = {row[0]: row[1] for row in cursor.fetchall() if row[0]}

        # Contar consultas por modalidad desde la tabla agenda_finanzas
        cursor.execute("""
            SELECT af.tipo_consulta, COUNT(af.id)
            FROM agenda_finanzas af
            JOIN pacientes p ON af.paciente_id = p.id
            WHERE af.fecha LIKE ? AND p.psicologo_id = ? AND af.estado_pago != 'Cancelada'
            GROUP BY af.tipo_consulta
        """, (date_prefix, psic_id))
        af_counts = {row[0]: row[1] for row in cursor.fetchall() if row[0]}

        # Combinar ambos conteos sin perder registros
        all_keys = set(ses_counts.keys()).union(set(af_counts.keys()))
        modality_counts = {}
        for k in all_keys:
            if k in ['Prepago', 'Paquete Prepagado', 'Paquete Prepagado (Deuda Pago Fraccionado)']:
                continue
            modality_counts[k] = max(ses_counts.get(k, 0), af_counts.get(k, 0))
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
            WHERE (fecha LIKE ? OR fecha_liquidacion LIKE ?) AND af.estado_pago IN ('Paga', 'Prepagada', 'Cancelada sin aviso - Paga')
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
    
    active_modalities = ["Presencial", "Online"]
    if psic_id is not None:
        cursor.execute("SELECT configuracion_horarios_visual FROM usuarios WHERE id = ?", (psic_id,))
        u_row = cursor.fetchone()
        if u_row and u_row['configuracion_horarios_visual']:
            try:
                import json
                cfg = json.loads(u_row['configuracion_horarios_visual'])
                raw_perfiles = cfg.get('perfiles', [])
                custom_mods = []
                if isinstance(raw_perfiles, list):
                    for p in raw_perfiles:
                        if isinstance(p, dict) and (p.get('nombre') or p.get('modalidad')):
                            custom_mods.append(p.get('nombre') or p.get('modalidad'))
                elif isinstance(raw_perfiles, dict):
                    custom_mods = list(raw_perfiles.keys())
                if custom_mods:
                    active_modalities = custom_mods
            except Exception:
                pass

    def _mod_match(db_mod, profile_mod):
        if not db_mod or not profile_mod:
            return False
        d = db_mod.strip().lower()
        p = profile_mod.strip().lower()
        if d == p:
            return True
        ignore_words = {'horario', 'modalidad', 'consulta', 'atencion', 'servicio'}
        d_words = set(d.split()) - ignore_words
        p_words = set(p.split()) - ignore_words
        if not d_words or not p_words:
            return d == p or d in p or p in d
        if d_words == p_words:
            return True
        if d_words & p_words:
            return True
        return False

    month_modalities = {}
    for m in active_modalities:
        m_count = 0
        for k, v in modality_counts.items():
            if _mod_match(k, m):
                m_count += v
        month_modalities[m] = m_count

    return jsonify({
        'breakdown': breakdown,
        'pending_list': pending_list,
        'income_list': income_list,
        'session_stats': session_stats,
        'stats': {
            'total_pacientes': total_pacientes,
            'total_pagas': total_pagas,
            'total_pendientes': total_pendientes,
            'month_online': modality_counts.get('Online', 0),
            'month_presencial': modality_counts.get('Presencial', 0),
            'month_modalities': month_modalities
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
            now = get_now_vet()
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
            now = get_now_vet()
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
        
        if estado_pago in ['Pagado', 'Paga', 'Completado'] and row['estado_pago'] not in ['Pagado', 'Paga', 'Completado']:
            notify_patient_firebase(
                row['paciente_id'],
                "💰 Pago Confirmado",
                f"Tu psicólogo ha verificado y validado tu pago correspondiente a la consulta del {fecha}.",
                icon="💰"
            )
        elif estado_pago == 'Cancelada' and row['estado_pago'] != 'Cancelada':
            notify_patient_firebase(
                row['paciente_id'],
                "❌ Cita Cancelada",
                f"Tu cita agendada para el {fecha} a las {hora} fue cancelada por tu profesional.",
                icon="❌"
            )

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
            SELECT af.*, p.nombres, p.apellidos, p.cedula, p.telefono, p.telefono as paciente_telefono,
                   (CASE WHEN s.id IS NOT NULL THEN 1 ELSE 0 END) as has_session
            FROM agenda_finanzas af
            JOIN pacientes p ON af.paciente_id = p.id
            LEFT JOIN sesiones s ON (s.agenda_id = af.id OR (s.paciente_id = af.paciente_id AND s.fecha = af.fecha))
            WHERE (af.hora != '00:00' AND af.hora != '' AND af.hora IS NOT NULL)
              AND p.psicologo_id = ?
            ORDER BY af.fecha ASC, af.hora ASC
        """, (psic_id,))
    else:
        cursor.execute("""
            SELECT af.*, p.nombres, p.apellidos, p.cedula, p.telefono, p.telefono as paciente_telefono,
                   (CASE WHEN s.id IS NOT NULL THEN 1 ELSE 0 END) as has_session
            FROM agenda_finanzas af
            JOIN pacientes p ON af.paciente_id = p.id
            LEFT JOIN sesiones s ON (s.agenda_id = af.id OR (s.paciente_id = af.paciente_id AND s.fecha = af.fecha))
            WHERE (af.hora != '00:00' AND af.hora != '' AND af.hora IS NOT NULL)
            ORDER BY af.fecha ASC, af.hora ASC
        """)
    events = [dict(row) for row in cursor.fetchall()]
    return jsonify(events)

@app.route('/api/agenda/blocks', methods=['GET', 'POST'])
@login_required
def manage_agenda_blocks():
    db = get_db()
    cursor = db.cursor()
    psic_id = get_psicologo_id_filter()
    user_id = session.get('user_id')
    target_psic_id = psic_id if psic_id is not None else user_id

    if request.method == 'POST':
        data = request.json or {}
        fecha = (data.get('fecha') or '').strip()
        hora_inicio = (data.get('hora_inicio') or '').strip()
        hora_fin = (data.get('hora_fin') or '').strip()
        motivo = (data.get('motivo') or 'Evento Personal / Bloqueo').strip()
        todo_el_dia = 1 if data.get('todo_el_dia') else 0

        if not fecha:
            return jsonify({'error': 'La fecha es obligatoria para agendar un evento personal / bloqueo.'}), 400

        cursor.execute("""
            INSERT INTO bloqueos_agenda_especificos (psicologo_id, fecha, hora_inicio, hora_fin, motivo, todo_el_dia)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (target_psic_id, fecha, hora_inicio, hora_fin, motivo, todo_el_dia))
        db.commit()
        block_id = cursor.lastrowid
        return jsonify({
            'success': True,
            'message': 'Evento personal / bloqueo registrado correctamente.',
            'block': {
                'id': block_id,
                'psicologo_id': target_psic_id,
                'fecha': fecha,
                'hora_inicio': hora_inicio,
                'hora_fin': hora_fin,
                'motivo': motivo,
                'todo_el_dia': todo_el_dia
            }
        })

    cursor.execute("""
        SELECT * FROM bloqueos_agenda_especificos
        WHERE psicologo_id = ?
        ORDER BY fecha ASC, hora_inicio ASC
    """, (target_psic_id,))
    rows = [dict(r) for r in cursor.fetchall()]
    return jsonify(rows)

@app.route('/api/agenda/blocks/<int:block_id>', methods=['DELETE'])
@login_required
def delete_agenda_block(block_id):
    db = get_db()
    cursor = db.cursor()
    psic_id = get_psicologo_id_filter()
    user_id = session.get('user_id')
    target_psic_id = psic_id if psic_id is not None else user_id

    cursor.execute("DELETE FROM bloqueos_agenda_especificos WHERE id = ? AND psicologo_id = ?", (block_id, target_psic_id))
    db.commit()
    return jsonify({'success': True, 'message': 'Bloqueo eliminado correctamente.'})

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
            p_email = paciente['email'] if (paciente and 'email' in paciente.keys()) else None
            if p_email:
                event_body['attendees'] = [
                    {
                        'email': p_email,
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
        # 1. Si el paciente tiene una cita agendada pendiente, actualizar dicha cita directamente
        cursor.execute("""
            SELECT id FROM agenda_finanzas
            WHERE paciente_id = ? AND estado_pago = 'Pendiente'
            ORDER BY ABS(JULIANDAY(fecha) - JULIANDAY(?)) ASC, id ASC LIMIT 1
        """, (paciente_id, fecha))
        pending_match = cursor.fetchone()

        if pending_match and not data.get('forzar_nuevo_registro'):
            pending_id = pending_match['id']
            cursor.execute("""
                UPDATE agenda_finanzas
                SET monto = ?, moneda = ?, tipo_consulta = ?, estado_pago = 'Paga',
                    control_uso = 'No consumida', cantidad_sesiones = ?,
                    referencia = ?, metodo_pago = ?, fecha_pago = ?
                WHERE id = ?
            """, (monto, moneda, tipo_consulta, cantidad_ses, referencia, metodo_pago, fecha_pago, pending_id))
            db.commit()
            auto_settle_patient_debts(db, paciente_id)
            import threading
            threading.Thread(target=sync_patient_to_firebase, args=(paciente_id,)).start()
            return jsonify({'success': 'Pago asignado y vinculado a la cita agendada del consultante con éxito.'})

        # 2. Si no hay cita pendiente o es un abono/paquete nuevo, guardar registro con control_uso = 'No consumida'
        control_uso_val = data.get('control_uso') or 'No consumida'

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
        auto_settle_patient_debts(db, paciente_id)
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
    data = request.json or {}
    db = get_db()
    cursor = db.cursor()
    
    try:
        cursor.execute("SELECT * FROM agenda_finanzas WHERE id = ?", (event_id,))
        local_event = cursor.fetchone()
        if not local_event:
            return jsonify({'error': 'Evento no encontrado.'}), 404

        fecha = data.get('fecha') or local_event['fecha']
        hora = data.get('hora') or local_event['hora']
        tipo_consulta = data.get('tipo_consulta') or local_event['tipo_consulta']
        estado_pago = data.get('estado_pago') or local_event['estado_pago']
        monto = data.get('monto') if 'monto' in data and data.get('monto') is not None else local_event['monto']
        moneda = data.get('moneda') if 'moneda' in data and data.get('moneda') is not None else local_event['moneda']
        
        if 'confirmada' in data:
            confirmada = int(data.get('confirmada'))
        elif data.get('estado') == 'Confirmada':
            confirmada = 1
        elif data.get('estado') == 'Cancelada':
            confirmada = 0
            estado_pago = 'Cancelada'
        else:
            confirmada = local_event['confirmada']
            
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
                    p_email = paciente['email'] if (paciente and 'email' in paciente.keys()) else None
                    if p_email:
                        g_event['attendees'] = [
                            {
                                'email': p_email,
                                'displayName': f"{paciente['nombres']} {paciente['apellidos']}"
                            }
                        ]
                    service.events().update(calendarId='primary', eventId=google_event_id, body=g_event, sendUpdates='all').execute()
                except Exception as ge:
                    print("Error al actualizar evento de Google Calendar:", ge)
                    
        monto = data.get('monto') if ('monto' in data and data.get('monto') is not None) else (local_event['monto'] if (local_event and local_event['monto'] is not None) else 0.0)
        moneda = data.get('moneda') if ('moneda' in data and data.get('moneda') is not None) else (local_event['moneda'] if (local_event and local_event['moneda']) else 'USD')
        
        cursor.execute("""
            UPDATE agenda_finanzas SET 
                fecha = ?, hora = ?, tipo_consulta = ?, estado_pago = ?, monto = ?, moneda = ?, confirmada = ?
            WHERE id = ?
        """, (
            fecha, hora, tipo_consulta, estado_pago, monto, moneda, confirmada, event_id
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
        return None
            
    token_key = f'google_token_{user_id}'
    cursor.execute("SELECT valor FROM configuracion WHERE clave = ?", (token_key,))
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
        if getattr(flow, 'code_verifier', None):
            session['code_verifier'] = flow.code_verifier

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

        state = session.get('state') or request.args.get('state')
        
        redirect_uri = url_for('google_callback', _external=True)
        if not redirect_uri.startswith('https://') and 'localhost' not in redirect_uri and '127.0.0.1' not in redirect_uri:
            redirect_uri = redirect_uri.replace('http://', 'https://')
            
        flow = Flow.from_client_secrets_file(
            CLIENT_SECRETS_FILE,
            scopes=SCOPES,
            state=state,
            redirect_uri=redirect_uri
        )
        
        if 'code_verifier' in session and session['code_verifier']:
            flow.code_verifier = session['code_verifier']
        else:
            flow.code_verifier = None

        req_url = request.url
        if not req_url.startswith('https://') and 'localhost' not in req_url and '127.0.0.1' not in req_url:
            req_url = req_url.replace('http://', 'https://')
            
        os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
        os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'
        
        try:
            flow.fetch_token(authorization_response=req_url)
        except Exception as token_err:
            err_str = str(token_err)
            if 'mismatching_state' in err_str or 'State not equal' in err_str or 'Missing code verifier' in err_str or 'invalid_grant' in err_str:
                url_state = request.args.get('state')
                flow = Flow.from_client_secrets_file(
                    CLIENT_SECRETS_FILE,
                    scopes=SCOPES,
                    state=url_state,
                    redirect_uri=redirect_uri
                )
                flow.code_verifier = None
                auth_code = request.args.get('code')
                if auth_code:
                    flow.fetch_token(code=auth_code)
                else:
                    raise token_err
            else:
                raise token_err
                
        creds = flow.credentials
        
        # Guardar en base de datos local
        db = get_db()
        cursor = db.cursor()
        user_id = session.get('user_id')
        token_key = f'google_token_{user_id}' if user_id else 'google_token'
        cursor.execute("INSERT OR REPLACE INTO configuracion (clave, valor) VALUES (?, ?)", 
                       (token_key, creds.to_json()))
        db.commit()
        
        return """
        <html>
            <body style="font-family: sans-serif; text-align: center; padding: 2rem;">
                <h2 style="color: #059669;">✓ Conexión con Google Calendar exitosa</h2>
                <p>Tu cuenta de Google ha sido vinculada correctamente. Esta ventana se cerrará en breve.</p>
                <script>
                    if (window.opener) {
                        try { window.opener.location.reload(); } catch(e) {}
                    }
                    setTimeout(() => window.close(), 2000);
                </script>
            </body>
        </html>
        """
    except Exception as e:
        print("Error en google_callback:", traceback.format_exc())
        return f"""
        <html>
            <body style="font-family: sans-serif; text-align: center; padding: 2rem;">
                <h3 style="color: #dc2626;">Fallo al completar la autorización con Google Calendar</h3>
                <p>Detalle del error: {str(e)}</p>
                <button onclick="window.close()" style="padding: 0.5rem 1rem; border-radius: 6px; background: #374151; color: white; border: none; cursor: pointer;">Cerrar Ventana</button>
            </body>
        </html>
        """, 500

@app.route('/api/google/sync', methods=['POST'])
@login_required
def sync_google_calendar():
    import traceback
    try:
        user_id = session.get('user_id')
        service = get_calendar_service(user_id)
        if not service:
            return jsonify({'error': 'Google Calendar no está configurado o autorizado.'}), 400
            
        db = get_db()
        cursor = db.cursor()
        
        # 1. Traer eventos futuros de Google Calendar
        now = datetime.datetime.utcnow().isoformat() + 'Z' # 'Z' indica UTC
        events_result = service.events().list(
            calendarId='primary', timeMin=now,
            maxResults=100, singleEvents=True,
            orderBy='startTime'
        ).execute()
        g_events = events_result.get('items', [])
        
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
                # Es nuevo desde Google Calendar. Intentamos enlazarlo a un paciente por nombre
                paciente_id = None
                if "Consulta:" in summary or "Consulta Psicológica -" in summary:
                    nombre_buscado = summary.replace("Consulta Psicológica -", "").replace("Consulta:", "").strip()
                    cursor.execute("""
                        SELECT id FROM pacientes 
                        WHERE (nombres || ' ' || apellidos) LIKE ? 
                        LIMIT 1
                    """, (f"%{nombre_buscado}%",))
                    pac_row = cursor.fetchone()
                    if pac_row:
                        paciente_id = pac_row['id']
                
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

        # 2. Exportar citas futuras locales que no tengan google_event_id hacia Google Calendar
        today_str = datetime.datetime.now().strftime("%Y-%m-%d")
        cursor.execute("""
            SELECT af.id, af.fecha, af.hora, af.tipo_consulta, p.nombres, p.apellidos, p.email
            FROM agenda_finanzas af
            JOIN pacientes p ON af.paciente_id = p.id
            WHERE af.google_event_id IS NULL
              AND af.fecha >= ?
              AND (af.estado_pago IS NULL OR (af.estado_pago NOT LIKE 'Cancelada%' AND af.estado_pago != 'Reprogramada'))
              AND (p.psicologo_id = ? OR ? IS NULL)
        """, (today_str, user_id, user_id))
        local_pending = cursor.fetchall()
        
        pushed_count = 0
        for lp in local_pending:
            try:
                pac_nombre = f"{lp['nombres']} {lp['apellidos']}"
                start_dt = f"{lp['fecha']}T{lp['hora']}:00-04:00"
                end_h = str(int(lp['hora'].split(':')[0]) + 1).zfill(2)
                end_dt = f"{lp['fecha']}T{end_h}:{lp['hora'].split(':')[1]}:00-04:00"
                
                event_b = {
                    'summary': f"Consulta Psicológica - {pac_nombre}",
                    'description': f"Modalidad: {lp['tipo_consulta']}",
                    'start': {'dateTime': start_dt, 'timeZone': 'America/Caracas'},
                    'end': {'dateTime': end_dt, 'timeZone': 'America/Caracas'}
                }
                if lp['email']:
                    event_b['attendees'] = [{'email': lp['email'], 'displayName': pac_nombre}]
                    
                g_ev = service.events().insert(calendarId='primary', body=event_b, sendUpdates='all').execute()
                if g_ev.get('id'):
                    cursor.execute("UPDATE agenda_finanzas SET google_event_id = ? WHERE id = ?", (g_ev['id'], lp['id']))
                    pushed_count += 1
            except Exception as pe:
                print("Error enviando cita local a Google Calendar:", pe)

        db.commit()
        
        msg = f"✓ Sincronización completada exitosamente."
        if pushed_count > 0:
            msg += f" {pushed_count} cita(s) enviada(s) a Google Calendar."
        if synced_count > 0:
            msg += f" {synced_count} evento(s) actualizado(s)/importado(s)."
        if pushed_count == 0 and synced_count == 0:
            msg += " Tu agenda ya estaba 100% al día."
            
        return jsonify({'success': msg})
        
    except Exception as e:
        print("Error durante la sincronización de Google Calendar:", traceback.format_exc())
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
    
    # Decodificar datos cifrados del paciente
    pac_dict = dict(pac)
    for field in ['antecedentes_medicos_personales', 'antecedentes_medicos_familiares', 
                  'antecedentes_psicologicos_personales', 'antecedentes_psicologicos_familiares',
                  'asistencia_previa_psicologo', 'motivo_consulta', 'expectativas', 
                  'farmacologia', 'diagnostico']:
        if pac_dict.get(field):
            pac_dict[field] = decrypt_clinical_text(pac_dict[field])
            
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
    sub_run = subtitle.add_run(f"Consultante: {pac_dict['nombres']} {pac_dict['apellidos']} | Cédula: {pac_dict['cedula']}")
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
        ("Nombres y Apellidos", f"{pac_dict['nombres']} {pac_dict['apellidos']}"),
        ("Cédula de Identidad", pac_dict['cedula']),
        ("Pronombre / Género", f"{pac_dict['pronombre'] or 'N/A'} / {pac_dict['genero'] or 'N/A'}"),
        ("Edad", str(pac_dict['edad']) if pac_dict['edad'] else "N/A"),
        ("Lugar y Fecha de Nacimiento", f"{pac_dict['lugar_nacimiento'] or 'N/A'} ({pac_dict['fecha_nacimiento'] or 'N/A'})"),
        ("Residencia Actual", ", ".join(filter(None, [pac_dict['residencia_actual'] if 'residencia_actual' in pac_dict.keys() else (pac_dict['ciudad'] if 'ciudad' in pac_dict.keys() else None), pac_dict['pais'] if 'pais' in pac_dict.keys() else None])) or "N/A"),
        ("Reside con", pac_dict['con_quien_reside'] or "N/A"),
        ("Nivel Académico / Ocupación", f"{pac_dict['nivel_academico'] or 'N/A'} / {pac_dict['ocupacion'] or 'N/A'}"),
        ("Estado Civil / Relacional", pac_dict['estado_civil'] or "N/A"),
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
    doc.add_paragraph(f"- Personales: {pac_dict['antecedentes_medicos_personales'] or 'Sin registrar'}")
    doc.add_paragraph(f"- Familiares: {pac_dict['antecedentes_medicos_familiares'] or 'Sin registrar'}")
    
    doc.add_paragraph().add_run("Antecedentes Psicológicos y Psiquiátricos:").bold = True
    doc.add_paragraph(f"- Personales: {pac_dict['antecedentes_psicologicos_personales'] or 'Sin registrar'}")
    doc.add_paragraph(f"- Familiares: {pac_dict['antecedentes_psicologicos_familiares'] or 'Sin registrar'}")
    
    doc.add_paragraph().add_run("Motivo de Consulta y Expectativas:").bold = True
    doc.add_paragraph(f"- Asistencia previa al psicólogo: {pac_dict['asistencia_previa_psicologo'] or 'Sin registrar'}")
    doc.add_paragraph(f"- Motivo de consulta actual: {pac_dict['motivo_consulta'] or 'Sin registrar'}")
    doc.add_paragraph(f"- Expectativas del proceso: {pac_dict['expectativas'] or 'Sin registrar'}")
    
    doc.add_paragraph().add_run("Tratamiento Farmacológico Activo:").bold = True
    doc.add_paragraph(pac_dict['farmacologia'] or "Ninguno")
    
    doc.add_paragraph().add_run("Contacto de Emergencia:").bold = True
    doc.add_paragraph(f"{pac_dict['contacto_emergencia_nombre'] or 'N/A'} ({pac_dict['contacto_emergencia_parentesco'] or 'N/A'})")
    
    doc.add_paragraph().add_run("Impresión Diagnóstica Evolutiva:").bold = True
    doc.add_paragraph(pac_dict['diagnostico'] or "Sin impresión diagnóstica anotada.")
    
    doc.add_page_break()
    
    # Sección 3: Evolución Cronológica (Sesiones)
    h3 = doc.add_heading(level=1)
    h3_run = h3.add_run("3. Registro de Sesiones (Evolución)")
    h3_run.font.color.rgb = docx.shared.RGBColor(0x3D, 0x1E, 0x3F)
    
    if not sessions:
        doc.add_paragraph("No hay sesiones de evolución registradas para este consultante.")
    else:
        for idx, s in enumerate(sessions, 1):
            s_resumen = decrypt_clinical_text(s['resumen']) or "Sin resumen."
            s_tareas = decrypt_clinical_text(s['tareas_asignadas']) or "Ninguna."
            s_recursos = decrypt_clinical_text(s['recursos_entregados']) or "Ninguno."
            s_anotaciones = decrypt_clinical_text(s['anotaciones_proxima']) or "Ninguna."
            s_compromisos = decrypt_clinical_text(s['compromisos_psicologo']) or "Ninguno."
            
            p_ses = doc.add_paragraph()
            p_ses.add_run(f"Sesión N° {idx} — Fecha: {s['fecha']} | Modalidad: {s['modalidad']}").bold = True
            doc.add_paragraph().add_run("Resumen abordado:").bold = True
            doc.add_paragraph(s_resumen)
            doc.add_paragraph().add_run("Tareas asignadas al consultante:").bold = True
            doc.add_paragraph(s_tareas)
            doc.add_paragraph().add_run("Recursos entregados:").bold = True
            doc.add_paragraph(s_recursos)
            doc.add_paragraph().add_run("Anotaciones próxima consulta:").bold = True
            doc.add_paragraph(s_anotaciones)
            doc.add_paragraph().add_run("Compromisos del psicólogo:").bold = True
            doc.add_paragraph(s_compromisos)
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

@app.route('/api/admin/backup/export-patients-word-zip', methods=['GET'])
@login_required
def export_patients_word_zip():
    user_id = session.get('user_id')
    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT nombres, apellidos FROM usuarios WHERE id = ?", (user_id,))
    psych = cursor.fetchone()
    psych_name = f"Psic. {psych['nombres']} {psych['apellidos']}" if psych else "Espacio Terapéutico"

    cursor.execute("""
        SELECT * FROM pacientes 
        WHERE (psicologo_id = ? OR psicologo_id IS NULL OR ? = 1)
        ORDER BY apellidos ASC, nombres ASC
    """, (user_id, user_id))
    patients = cursor.fetchall()

    if not patients:
        return jsonify({'error': 'No se encontraron pacientes para exportar.'}), 404

    import io, zipfile, docx, re
    from docx.shared import Inches, Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    def set_cell_bg(cell, hex_color):
        tcPr = cell._tc.get_or_add_tcPr()
        shd = OxmlElement('w:shd')
        shd.set(qn('w:val'), 'clear')
        shd.set(qn('w:color'), 'auto')
        shd.set(qn('w:fill'), hex_color)
        tcPr.append(shd)

    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for p_row in patients:
            p = dict(p_row)
            patient_id = p['id']

            cursor.execute("SELECT * FROM sesiones WHERE paciente_id = ? ORDER BY fecha ASC", (patient_id,))
            sessions_list = [dict(s) for s in cursor.fetchall()]

            cursor.execute("SELECT * FROM agenda_finanzas WHERE paciente_id = ? ORDER BY fecha ASC", (patient_id,))
            agenda_list = [dict(a) for a in cursor.fetchall()]

            tools_data = {}
            tool_tables = [
                ('registros_ansiedad', 'Registro de Ansiedad'),
                ('registros_sueno', 'Registro de Sueño'),
                ('registros_sobriedad', 'Registro de Sobriedad / Consumo'),
                ('adherencia_registros', 'Adherencia a Medicamentos'),
                ('activacion_registros', 'Registro de Actividades'),
                ('registros_cognitivos', 'Pensamientos Cognitivos TCC'),
                ('registros_ingesta', 'Registro de Ingesta Alimentaria')
            ]
            for tool_table, tool_name in tool_tables:
                try:
                    cursor.execute(f"SELECT * FROM {tool_table} WHERE paciente_id = ? ORDER BY id DESC LIMIT 50", (patient_id,))
                    t_rows = [dict(r) for r in cursor.fetchall()]
                    if t_rows:
                        cleaned = [{k: v for k, v in r.items() if k not in ('id', 'paciente_id')} for r in t_rows]
                        tools_data[tool_name] = cleaned
                except Exception:
                    pass

            doc = docx.Document()

            for section in doc.sections:
                section.top_margin = Inches(0.8)
                section.bottom_margin = Inches(0.8)
                section.left_margin = Inches(0.8)
                section.right_margin = Inches(0.8)

            p_title = doc.add_paragraph()
            p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run_title = p_title.add_run("EXPEDIENTE CLÍNICO Y TERAPÉUTICO")
            run_title.font.name = 'Calibri'
            run_title.font.size = Pt(22)
            run_title.font.bold = True
            run_title.font.color.rgb = RGBColor(91, 33, 182)

            p_sub = doc.add_paragraph()
            p_sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run_sub = p_sub.add_run(f"Plataforma Espacio Terapéutico • Terapeuta: {psych_name}\nConsultante: {p.get('nombres', '')} {p.get('apellidos', '')}")
            run_sub.font.name = 'Calibri'
            run_sub.font.size = Pt(10)
            run_sub.font.italic = True
            run_sub.font.color.rgb = RGBColor(100, 116, 139)

            doc.add_paragraph().paragraph_format.space_after = Pt(6)

            h1 = doc.add_heading(level=1)
            r1 = h1.add_run("1. Ficha General del Consultante")
            r1.font.name = 'Calibri'
            r1.font.color.rgb = RGBColor(91, 33, 182)

            table_p = doc.add_table(rows=0, cols=2)
            table_p.alignment = WD_TABLE_ALIGNMENT.CENTER

            fields = [
                ("Nombres y Apellidos:", f"{p.get('nombres', '')} {p.get('apellidos', '')}"),
                ("Cédula / Documento:", str(p.get('cedula', 'N/A'))),
                ("Fecha de Nacimiento:", str(p.get('fecha_nacimiento', 'N/A'))),
                ("Teléfono / WhatsApp:", str(p.get('telefono', 'N/A'))),
                ("Correo Electrónico:", str(p.get('email', 'N/A'))),
                ("País / Ciudad:", f"{p.get('pais', 'N/A')} / {p.get('ciudad', 'N/A')}"),
                ("Ocupación:", str(p.get('ocupacion', 'N/A'))),
                ("Estado Civil:", str(p.get('estado_civil', 'N/A'))),
                ("Contacto de Emergencia:", str(p.get('contacto_emergencia', 'N/A'))),
                ("Diagnóstico / Motivo Inicial:", str(p.get('diagnostico', 'En evaluación'))),
                ("Fecha de Registro:", str(p.get('fecha_registro', 'N/A'))),
            ]

            for label, val in fields:
                row = table_p.add_row()
                cell_lbl, cell_val = row.cells[0], row.cells[1]
                cell_lbl.width = Inches(2.2)
                cell_val.width = Inches(4.5)
                set_cell_bg(cell_lbl, "F3E8FF")
                set_cell_bg(cell_val, "FAF5FF")
                
                p_l = cell_lbl.paragraphs[0]
                r_l = p_l.add_run(label)
                r_l.bold = True
                r_l.font.size = Pt(10)
                r_l.font.name = 'Calibri'
                
                p_v = cell_val.paragraphs[0]
                r_v = p_v.add_run(val or "N/A")
                r_v.font.size = Pt(10)
                r_v.font.name = 'Calibri'

            doc.add_paragraph().paragraph_format.space_after = Pt(12)

            h2 = doc.add_heading(level=1)
            r2 = h2.add_run("2. Historia Clínica y Anamnesis")
            r2.font.name = 'Calibri'
            r2.font.color.rgb = RGBColor(91, 33, 182)

            anamnesis_text = p.get('anamnesis') or p.get('historia_clinica') or "Sin historia clínica detallada registrada aún."
            p_a = doc.add_paragraph()
            r_a = p_a.add_run(anamnesis_text)
            r_a.font.name = 'Calibri'
            r_a.font.size = Pt(10.5)

            doc.add_paragraph().paragraph_format.space_after = Pt(12)

            h3 = doc.add_heading(level=1)
            r3 = h3.add_run(f"3. Historial de Evoluciones Clínicas ({len(sessions_list)} Sesiones Registradas)")
            r3.font.name = 'Calibri'
            r3.font.color.rgb = RGBColor(91, 33, 182)

            if not sessions_list:
                p_nos = doc.add_paragraph()
                r_nos = p_nos.add_run("No se encuentran notas de evolución registradas para este consultante.")
                r_nos.font.italic = True
                r_nos.font.color.rgb = RGBColor(148, 163, 184)
            else:
                for idx, s in enumerate(sessions_list, 1):
                    h_s = doc.add_heading(level=2)
                    r_hs = h_s.add_run(f"Sesión #{s.get('numero_sesion', idx)} — Fecha: {s.get('fecha', 'N/A')}")
                    r_hs.font.name = 'Calibri'
                    r_hs.font.size = Pt(12)
                    r_hs.font.color.rgb = RGBColor(126, 34, 206)

                    table_s = doc.add_table(rows=0, cols=2)
                    table_s.alignment = WD_TABLE_ALIGNMENT.CENTER
                    
                    s_fields = [
                        ("Modalidad / Cita:", f"{s.get('tipo_consulta', 'Sesión Individual')}"),
                        ("Diagnóstico / Enfoque:", s.get('diagnostico', 'N/A')),
                        ("Evolución Clínica:", s.get('resumen') or s.get('evolucion') or 'Sin resumen'),
                        ("Objetivos Trabajados:", s.get('objetivos', 'N/A')),
                        ("Tareas / Asignaciones:", s.get('tareas', 'N/A')),
                        ("Observaciones:", s.get('observaciones', 'N/A')),
                    ]

                    for s_lbl, s_val in s_fields:
                        if not s_val or s_val == 'N/A':
                            continue
                        row = table_s.add_row()
                        c_lbl, c_val = row.cells[0], row.cells[1]
                        c_lbl.width = Inches(2.0)
                        c_val.width = Inches(4.7)
                        set_cell_bg(c_lbl, "F1F5F9")
                        set_cell_bg(c_val, "FFFFFF")

                        p_sl = c_lbl.paragraphs[0]
                        r_sl = p_sl.add_run(s_lbl)
                        r_sl.bold = True
                        r_sl.font.size = Pt(9.5)
                        r_sl.font.name = 'Calibri'

                        p_sv = c_val.paragraphs[0]
                        r_sv = p_sv.add_run(str(s_val))
                        r_sv.font.size = Pt(9.5)
                        r_sv.font.name = 'Calibri'

                    doc.add_paragraph().paragraph_format.space_after = Pt(8)

            h4 = doc.add_heading(level=1)
            r4 = h4.add_run("4. Registros en Herramientas Terapéuticas")
            r4.font.name = 'Calibri'
            r4.font.color.rgb = RGBColor(91, 33, 182)

            has_tools = False
            for tool_name, tool_rows in tools_data.items():
                if not tool_rows:
                    continue
                has_tools = True
                h_t = doc.add_heading(level=2)
                r_ht = h_t.add_run(f"• {tool_name} ({len(tool_rows)} registros)")
                r_ht.font.name = 'Calibri'
                r_ht.font.size = Pt(11)
                r_ht.font.color.rgb = RGBColor(16, 185, 129)

                table_t = doc.add_table(rows=1, cols=len(tool_rows[0].keys()))
                table_t.alignment = WD_TABLE_ALIGNMENT.CENTER
                
                hdr_cells = table_t.rows[0].cells
                for col_idx, col_name in enumerate(tool_rows[0].keys()):
                    set_cell_bg(hdr_cells[col_idx], "059669")
                    p_h = hdr_cells[col_idx].paragraphs[0]
                    r_h = p_h.add_run(col_name.replace('_', ' ').title())
                    r_h.bold = True
                    r_h.font.color.rgb = RGBColor(255, 255, 255)
                    r_h.font.size = Pt(9)

                for row_data in tool_rows[:50]:
                    row_cells = table_t.add_row().cells
                    for col_idx, col_val in enumerate(row_data.values()):
                        set_cell_bg(row_cells[col_idx], "F0FDF4")
                        p_c = row_cells[col_idx].paragraphs[0]
                        r_c = p_c.add_run(str(col_val or ''))
                        r_c.font.size = Pt(8.5)

                doc.add_paragraph().paragraph_format.space_after = Pt(8)

            if not has_tools:
                p_not = doc.add_paragraph()
                r_not = p_not.add_run("El consultante no registra entradas recientes en las herramientas terapéuticas interactivas.")
                r_not.font.italic = True
                r_not.font.color.rgb = RGBColor(148, 163, 184)

            doc_stream = io.BytesIO()
            doc.save(doc_stream)
            doc_stream.seek(0)

            raw_filename = f"Expediente_{p.get('cedula', 'ID')}_{p.get('nombres', '')}_{p.get('apellidos', '')}.docx"
            safe_filename = re.sub(r'[\\/*?:"<>|]', '_', raw_filename).replace(' ', '_')
            zip_file.writestr(safe_filename, doc_stream.getvalue())

    zip_buffer.seek(0)
    today_str = datetime.date.today().strftime('%Y-%m-%d')
    return send_file(
        zip_buffer,
        mimetype='application/zip',
        as_attachment=True,
        download_name=f'Expedientes_Pacientes_EspacioTerapeutico_{today_str}.zip'
    )

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

@app.context_processor
def inject_asset_version():
    import time
    return {'asset_v': int(time.time())}

@app.route('/')
@app.route('/inicio')
@app.route('/login')
@app.route('/para-psicologos')
@app.route('/psic.<path:slug>')
@app.route('/agendar/<path:slug>')
@app.route('/registro/<path:slug>')
def index(slug=None):
    path = request.path.strip('/')
    db = get_db()
    cursor = db.cursor()
    
    host_url = request.host_url.rstrip('/')
    
    # Meta tags por defecto para la portada principal de la plataforma
    og_title = "Espacio Terapéutico | Consultorio Digital"
    og_description = "Plataforma integral de gestión clínica y auto-agendamiento para psicólogos y profesionales de la salud mental."
    og_image = f"{host_url}/static/logo.png"
    og_url = request.url

    # Identificar si la ruta corresponde a un psicólogo específico (agendar, perfil o registro)
    identifier = None
    if path.startswith('agendar/'):
        identifier = path.replace('agendar/', '').strip()
    elif path.startswith('psic.'):
        identifier = path.strip()
    elif path.startswith('registro/'):
        identifier = path.replace('registro/', '').strip()
    elif request.args.get('fast_booking'):
        identifier = request.args.get('fast_booking').strip()

    if identifier:
        try:
            psych = get_psychologist_by_id_or_slug(cursor, identifier)
            if psych:
                nom_comp = f"Psic. {psych.get('nombres') or ''} {psych.get('apellidos') or ''}".strip()
                og_title = f"{nom_comp} | Reserva tu Cita en Espacio Terapéutico"
                og_description = f"Agenda tu consulta psicológica online o presencial con {nom_comp} de forma rápida y segura."
                
                # Buscar foto de perfil / título del psicólogo
                foto_usr = psych.get('foto_perfil') or psych.get('foto_titulo')
                if foto_usr:
                    if foto_usr.startswith('http://') or foto_usr.startswith('https://'):
                        og_image = foto_usr
                    elif foto_usr.startswith('/'):
                        og_image = f"{host_url}{foto_usr}"
                    elif not foto_usr.startswith('data:'):
                        og_image = f"{host_url}/static/{foto_usr}"
        except Exception:
            pass

    return render_template('index.html', 
                           og_title=og_title, 
                           og_description=og_description, 
                           og_image=og_image, 
                           og_url=og_url)

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

def push_all_data_to_firebase():
    """
    Sincroniza y guarda FORZOSAMENTE todos los consultantes, citas (agenda_finanzas)
    y evoluciones (sesiones) de SQLite en Firebase Realtime Database.
    Además genera un respaldo local comprimido de seguridad en backups/.
    """
    import urllib.request
    import json
    import requests

    db = get_db()
    cursor = db.cursor()

    # 1. Crear snapshot local de respaldo en backups/
    try:
        backup_dir = os.path.join(BASE_DIR, 'backups')
        if not os.path.exists(backup_dir):
            os.makedirs(backup_dir)
        stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        backup_path = os.path.join(backup_dir, f"copia_seguridad_clinica_{stamp}.db")
        backup_conn = sqlite3.connect(backup_path)
        db.backup(backup_conn)
        backup_conn.close()
    except Exception as b_err:
        print(f"Advertencia al crear backup local: {b_err}")

    # 2. Sincronizar pacientes hacia Firebase
    cursor.execute("SELECT * FROM pacientes")
    pacientes = [dict(row) for row in cursor.fetchall()]

    total_p = len(pacientes)
    total_a = 0
    total_s = 0

    for p in pacientes:
        p_id = p['id']
        p_username = (p.get('username') or '').strip().lower()

        # Datos de perfil
        perfil_payload = {
            'nombres': p.get('nombres') or '',
            'apellidos': p.get('apellidos') or '',
            'cedula': p.get('cedula') or '',
            'username': p.get('username') or '',
            'metodos_pago': p.get('metodos_pago') or '',
            'telefono': p.get('telefono') or '',
            'email': p.get('email') or '',
            'genero': p.get('genero') or '',
            'edad': p.get('edad') or '',
            'residencia_actual': p.get('residencia_actual') or ''
        }

        try:
            requests.put(f"{FIREBASE_DB_URL}/pacientes/{p_id}/perfil.json", json=perfil_payload, timeout=4.0)
            if p_username:
                requests.put(f"{FIREBASE_DB_URL}/usuarios_pacientes/{p_username}.json", json=perfil_payload, timeout=4.0)
        except Exception:
            pass

        # Sincronizar Citas/Agenda
        cursor.execute("SELECT * FROM agenda_finanzas WHERE paciente_id = ?", (p_id,))
        citas = [dict(row) for row in cursor.fetchall()]
        total_a += len(citas)
        citas_dict = {}
        for c in citas:
            c_id = str(c['id'])
            citas_dict[c_id] = {
                'codigo_cita': f"CITA-#{str(c['id']).zfill(4)}",
                'fecha': c.get('fecha'),
                'hora': c.get('hora'),
                'modalidad': c.get('modalidad', 'Online'),
                'monto': c.get('monto', 0.0),
                'estado_pago': c.get('estado_pago', 'Pendiente'),
                'metodo_pago': c.get('metodo_pago', ''),
                'fecha_registro': c.get('fecha_registro', '')
            }
        try:
            requests.put(f"{FIREBASE_DB_URL}/pacientes/{p_id}/citas_solicitadas.json", json=citas_dict, timeout=4.0)
        except Exception:
            pass

        # Sincronizar Evoluciones / Sesiones
        cursor.execute("SELECT * FROM sesiones WHERE paciente_id = ?", (p_id,))
        sesiones = [dict(row) for row in cursor.fetchall()]
        total_s += len(sesiones)
        diario_dict = {}
        for s in sesiones:
            s_id = str(s['id'])
            diario_dict[s_id] = {
                'agenda_id': s.get('agenda_id'),
                'fecha': s.get('fecha'),
                'modalidad': s.get('modalidad'),
                'estado': s.get('estado', 'Realizada'),
                'resumen': s.get('resumen', ''),
                'tareas_asignadas': s.get('tareas_asignadas', ''),
                'recursos_entregados': s.get('recursos_entregados', ''),
                'anotaciones_proxima': s.get('anotaciones_proxima', '')
            }
        try:
            requests.put(f"{FIREBASE_DB_URL}/pacientes/{p_id}/diario.json", json=diario_dict, timeout=4.0)
        except Exception:
            pass

    return {
        'total_pacientes': total_p,
        'total_citas': total_a,
        'total_evoluciones': total_s,
        'timestamp': datetime.datetime.now().isoformat()
    }

@app.route('/api/sync/force-firebase', methods=['POST', 'GET'])
def force_sync_firebase():
    try:
        # 1. Guardar y subir todos los datos a Firebase
        stats = push_all_data_to_firebase()
        # 2. Restaurar/combinar datos nuevos que vengan de Firebase
        restore_patients_from_firebase()
        return jsonify({
            'success': 'Todos los datos (consultantes, citas y evoluciones) fueron guardados y respaldados exitosamente en la nube.',
            'total_pacientes': stats['total_pacientes'],
            'total_citas': stats['total_citas'],
            'total_evoluciones': stats['total_evoluciones'],
            'timestamp': stats['timestamp']
        })
    except Exception as e:
        print(f"Error en guardado forzado a Firebase: {e}")
        return jsonify({'error': f'Error al guardar en nube: {str(e)}'}), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT COUNT(*) FROM pacientes")
        total_p = cursor.fetchone()[0]
        return jsonify({
            'status': 'ok',
            'database': 'connected',
            'total_pacientes': total_p,
            'schema_version': CURRENT_SCHEMA_VER,
            'timestamp': datetime.datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'status': 'error', 'details': str(e)}), 500

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
    if not check_is_superadmin():
        return jsonify({'error': 'Acceso denegado. Se requieren permisos de superadministrador.'}), 403
        
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT id, username, nombres, apellidos FROM usuarios WHERE id = ? AND role = 'psicologo'", (user_id,))
    row = cursor.fetchone()
    if not row:
        return jsonify({'error': 'Psicólogo no encontrado.'}), 404
        
    try:
        # Obtener pacientes del psicólogo antes de eliminar para limpiar Firebase
        cursor.execute("SELECT id, username, cedula FROM pacientes WHERE psicologo_id = ?", (user_id,))
        pats_to_delete = cursor.fetchall()
        
        # Cascade cleanup of all psychologist data
        cursor.execute("DELETE FROM pizarra_terapeutica WHERE paciente_id IN (SELECT id FROM pacientes WHERE psicologo_id = ?)", (user_id,))
        cursor.execute("DELETE FROM agenda_finanzas WHERE paciente_id IN (SELECT id FROM pacientes WHERE psicologo_id = ?)", (user_id,))
        cursor.execute("DELETE FROM sesiones WHERE paciente_id IN (SELECT id FROM pacientes WHERE psicologo_id = ?)", (user_id,))
        cursor.execute("DELETE FROM pacientes WHERE psicologo_id = ?", (user_id,))
        cursor.execute("DELETE FROM notificaciones WHERE user_id = ?", (user_id,))
        cursor.execute("DELETE FROM fcm_subscriptions WHERE user_id = ?", (user_id,))
        cursor.execute("DELETE FROM usuarios WHERE id = ?", (user_id,))
        db.commit()
        
        # Limpiar pacientes de Firebase Realtime Database
        for pt in pats_to_delete:
            delete_patient_from_firebase(pt['id'], (pt['username'] or pt['cedula'] or '').strip())
            
        return jsonify({'success': f"Psicólogo '{row['nombres']} {row['apellidos']}' (@{row['username']}) y toda su información fueron eliminados con éxito."})
    except Exception as e:
        db.rollback()
        return jsonify({'error': f'Error al eliminar psicólogo: {str(e)}'}), 500


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

# ==========================================
# RUTAS DE INTEGRACIÓN WHATSAPP WEB (QR)
# ==========================================
WHATSAPP_SERVICE_URL = os.environ.get('WHATSAPP_SERVICE_URL', 'https://espacio-terapeutico-whatsapp.onrender.com')

def make_wa_http_request(method, endpoint, json_data=None, timeout=5, user_id=None):
    import requests
    url = f"{WHATSAPP_SERVICE_URL.rstrip('/')}/{endpoint.lstrip('/')}"
    
    if not user_id:
        try:
            from flask import session
            user_id = session.get('user_id')
        except RuntimeError:
            user_id = 1
            
    if not user_id:
        user_id = 1

    headers = {'X-User-ID': str(user_id)}
    params = {'user_id': str(user_id)}
    
    if json_data is not None and isinstance(json_data, dict):
        if 'user_id' not in json_data:
            json_data['user_id'] = user_id

    try:
        s = requests.Session()
        s.trust_env = False
        if method.upper() == 'GET':
            return s.get(url, params=params, headers=headers, timeout=timeout)
        else:
            return s.post(url, json=json_data, params=params, headers=headers, timeout=timeout)
    except Exception:
        if method.upper() == 'GET':
            return requests.get(url, params=params, headers=headers, timeout=timeout)
        else:
            return requests.post(url, json=json_data, params=params, headers=headers, timeout=timeout)

def send_whatsapp_message_async(phone, text, user_id=1):
    def _worker():
        try:
            make_wa_http_request('POST', '/send', json_data={'phone': phone, 'text': text, 'user_id': user_id}, timeout=15, user_id=user_id)
        except Exception as ex:
            print(f"Error enviando WhatsApp asíncrono a {phone}:", ex)
    import threading
    t = threading.Thread(target=_worker)
    t.daemon = True
    t.start()

@app.route('/api/whatsapp/status', methods=['GET'])
@login_required
def get_whatsapp_status():
    try:
        user_id = session.get('user_id')
        r = make_wa_http_request('GET', '/status', timeout=3, user_id=user_id)
        return jsonify(r.json())
    except Exception as e:
        return jsonify({'status': 'disconnected', 'error': 'Microservicio de WhatsApp no disponible', 'details': str(e)})

@app.route('/api/whatsapp/qr', methods=['GET'])
@login_required
def get_whatsapp_qr():
    try:
        user_id = session.get('user_id')
        r = make_wa_http_request('GET', '/qr', timeout=12, user_id=user_id)
        return jsonify(r.json())
    except Exception as e:
        return jsonify({'status': 'disconnected', 'qr': None, 'error': str(e)})

@app.route('/api/whatsapp/force-qr', methods=['POST'])
@login_required
def force_whatsapp_qr():
    try:
        user_id = session.get('user_id')
        r = make_wa_http_request('POST', '/force-qr', timeout=10, user_id=user_id)
        return jsonify(r.json())
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/whatsapp/send', methods=['POST'])
@login_required
def send_whatsapp_message():
    data = request.json or {}
    phone = data.get('phone')
    text = data.get('text')
    user_id = session.get('user_id')
    if not phone or not text:
        return jsonify({'error': 'Teléfono y texto son requeridos'}), 400
    try:
        r = make_wa_http_request('POST', '/send', json_data={'phone': phone, 'text': text, 'user_id': user_id}, timeout=15, user_id=user_id)
        return jsonify(r.json()), r.status_code
    except Exception as e:
        return jsonify({'error': f'Error al comunicarse con el microservicio WhatsApp: {str(e)}'}), 500

@app.route('/api/whatsapp/trigger-birthdays', methods=['POST'])
@login_required
def trigger_birthday_messages_route():
    try:
        db = get_db()
        patient_id = None
        if request.is_json and request.json:
            patient_id = request.json.get('patient_id')
        elif request.args.get('patient_id'):
            patient_id = request.args.get('patient_id')
            
        auto_check_patient_birthdays(db, force=True, target_patient_id=patient_id)
        return jsonify({'success': 'Revisión y envío de notificaciones de cumpleaños ejecutada correctamente.'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/whatsapp/logout', methods=['POST'])
@login_required
def logout_whatsapp():
    try:
        user_id = session.get('user_id')
        r = make_wa_http_request('POST', '/logout', timeout=10, user_id=user_id)
        return jsonify(r.json())
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/whatsapp/webhook', methods=['POST'])
def whatsapp_webhook():
    data = request.json or {}
    raw_user_id = data.get('user_id')
    raw_phone = str(data.get('phone', '')).strip()
    text = str(data.get('text', '')).strip()
    
    if not raw_phone or not text:
        return jsonify({'error': 'Payload incompleto'}), 400

    db = get_db()
    cursor = db.cursor()

    clean_digits = ''.join(filter(str.isdigit, raw_phone))
    if not clean_digits:
        return jsonify({'status': 'ignored', 'message': 'Número no válido'}), 400

    # 1. Búsqueda de paciente ultra flexible por coincidencia de dígitos telefónicos
    if raw_user_id:
        cursor.execute("SELECT id, nombres, apellidos, telefono, psicologo_id FROM pacientes WHERE psicologo_id = ? ORDER BY id DESC", (raw_user_id,))
    else:
        cursor.execute("SELECT id, nombres, apellidos, telefono, psicologo_id FROM pacientes ORDER BY id DESC")
    candidates = cursor.fetchall()

    patient = None
    for cand in candidates:
        cand_digits = ''.join(filter(str.isdigit, str(cand['telefono'] or '')))
        if not cand_digits:
            continue
        if (clean_digits.endswith(cand_digits) or 
            cand_digits.endswith(clean_digits) or 
            (len(clean_digits) >= 7 and len(cand_digits) >= 7 and clean_digits[-7:] == cand_digits[-7:])):
            patient = cand
            break

    if not patient and raw_user_id:
        cursor.execute("SELECT id, nombres, apellidos, telefono, psicologo_id FROM pacientes ORDER BY id DESC")
        all_cands = cursor.fetchall()
        for cand in all_cands:
            cand_digits = ''.join(filter(str.isdigit, str(cand['telefono'] or '')))
            if not cand_digits:
                continue
            if (clean_digits.endswith(cand_digits) or 
                cand_digits.endswith(clean_digits) or 
                (len(clean_digits) >= 7 and len(cand_digits) >= 7 and clean_digits[-7:] == cand_digits[-7:])):
                patient = cand
                break

    if not patient:
        return jsonify({'status': 'ignored', 'message': f'Teléfono {raw_phone} no asociado a ningún paciente.'})

    patient_id = patient['id']
    patient_name = f"{patient['nombres']} {patient['apellidos']}".strip()
    psic_id = patient['psicologo_id']
    
    import unicodedata, re
    text_lower = text.lower().strip()
    text_norm = unicodedata.normalize('NFD', text_lower)
    text_clean = ''.join(c for c in text_norm if unicodedata.category(c) != 'Mn')
    text_clean = re.sub(r'[^a-z0-9\s👍]', ' ', text_clean).strip()
    
    # Normalizar letras repetidas (ej. 'siiiiii' -> 'si', 'siii' -> 'si')
    text_dedup = re.sub(r'i+', 'i', text_clean)
    words_set = set(text_clean.split()) | set(text_dedup.split())

    confirm_keywords = {
        'si', 'sip', 'sii', 'siii', 'siiii', 'siiiii', 'confirmo', 'confirmar', 'confirmado', 'confirmada',
        'asistire', 'ok', 'listo', '1', 's', 'voy', 'asisto', 'seguro', 'perfecto',
        'excelente', 'correcto', 'claro', 'dale', 'ahi', 'estare', 'allí', 'estaré', '👍'
    }

    cancel_keywords = {
        'no', 'nop', 'cancelo', 'cancelar', 'cancelado', 'cancelada', 'imposible',
        'podre', 'asisto', '2'
    }

    is_confirm = any(w in words_set for w in confirm_keywords) or ('si' in text_dedup.split()) or any(k in text_clean for k in ['si', 'confirmo', 'asistire', 'ahi estare', 'allí estaré', '👍'])
    is_cancel = ('no' in words_set and 'si' not in words_set and 'sii' not in words_set and 'siii' not in words_set) or any(k in text_clean for k in ['cancelo', 'cancelar', 'no podre', 'no asisto'])

    if not is_confirm and not is_cancel:
        return jsonify({'status': 'text_received_no_action', 'message': f'Mensaje "{text}" recibido pero no requiere acción de confirmación.'})

    # 2. Buscar cita pendiente sin confirmar para este paciente (priorizando fecha de hoy o futura)
    cursor.execute("""
        SELECT id, fecha, hora, confirmada, tipo_consulta 
        FROM agenda_finanzas 
        WHERE paciente_id = ? AND (confirmada IS NULL OR confirmada = 0) AND (estado_pago IS NULL OR estado_pago != 'Cancelada') AND fecha >= date('now', '-1 day')
        ORDER BY fecha ASC, hora ASC LIMIT 1
    """, (patient_id,))
    next_cita = cursor.fetchone()

    if not next_cita:
        cursor.execute("""
            SELECT id, fecha, hora, confirmada, tipo_consulta 
            FROM agenda_finanzas 
            WHERE paciente_id = ? AND (confirmada IS NULL OR confirmada = 0) AND (estado_pago IS NULL OR estado_pago != 'Cancelada')
            ORDER BY fecha DESC, hora DESC LIMIT 1
        """, (patient_id,))
        next_cita = cursor.fetchone()

    if not next_cita:
        cursor.execute("""
            SELECT id, fecha, hora, confirmada, tipo_consulta 
            FROM agenda_finanzas 
            WHERE paciente_id = ? AND (estado_pago IS NULL OR estado_pago != 'Cancelada')
            ORDER BY fecha DESC, hora DESC LIMIT 1
        """, (patient_id,))
        next_cita = cursor.fetchone()

    if not next_cita:
        cursor.execute("""
            SELECT id, fecha, hora, confirmada, tipo_consulta 
            FROM agenda_finanzas 
            WHERE paciente_id = ? AND (estado_pago IS NULL OR estado_pago != 'Cancelada')
            ORDER BY fecha DESC, hora DESC LIMIT 1
        """, (patient_id,))
        next_cita = cursor.fetchone()

    if not next_cita:
        return jsonify({'status': 'no_upcoming_appointment', 'message': f'No hay citas registradas para {patient_name}'})

    cita_id = next_cita['id']
    cita_fecha = next_cita['fecha']
    cita_hora = next_cita['hora']

    # Configuración de plantilla
    antelacion_horas = 24
    plantilla_encuadre = (
        "¡Gracias por confirmar tu sesión, *{paciente}*! 🌿\n\n"
        "📍 *Detalles de tu cita:*\n"
        "📅 *Fecha:* {fecha}\n"
        "⏰ *Hora:* {hora}\n\n"
        "💡 *Encuadre Terapéutico:*\n"
        "• Recuerda habilitar un espacio tranquilo, cómodo y privado para ti.\n"
        "• Realizar el pago correspondiente de la sesión.\n"
        "• Conectarte o asistir puntualmente a la hora acordada.\n\n"
        "⚠️ *Política de cancelación:* Si necesitas cancelar o reprogramar tu sesión, por favor avísanos con al menos *{horas_antelacion} horas* de anticipación."
    )

    try:
        cursor.execute("SELECT configuracion_horarios_visual FROM usuarios WHERE id = ?", (psic_id,))
        u_row = cursor.fetchone()
        if u_row and u_row['configuracion_horarios_visual']:
            import json
            cfg_json = json.loads(u_row['configuracion_horarios_visual'])
            antelacion_horas = cfg_json.get('limite_cancelacion_valor') or cfg_json.get('limite_cancelacion') or 24
            if cfg_json.get('plantilla_encuadre'):
                plantilla_encuadre = cfg_json.get('plantilla_encuadre')
    except Exception:
        pass

    from datetime import datetime
    now_formatted = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    if is_confirm:
        cursor.execute("UPDATE agenda_finanzas SET confirmada = 1, confirmacion_enviada_wa = 1 WHERE id = ?", (cita_id,))
        try:
            cursor.execute("UPDATE citas SET confirmada = 1 WHERE paciente_id = ? AND fecha = ?", (patient_id, cita_fecha))
        except Exception:
            pass

        notif_msg = f"📱 WhatsApp: {patient_name} CONFIRMÓ su cita del {cita_fecha} a las {cita_hora}."
        cursor.execute("""
            INSERT INTO notificaciones (user_id, tipo, titulo, mensaje, fecha, leida, link)
            VALUES (?, 'whatsapp_confirmation', 'Cita Confirmada por WhatsApp', ?, ?, 0, '#agenda')
        """, (psic_id, notif_msg, now_formatted))
        db.commit()

        cursor.execute("SELECT valor FROM configuracion WHERE clave = 'msg_confirmacion_ok'")
        cfg_ok = cursor.fetchone()
        tmpl_ok = cfg_ok['valor'] if cfg_ok and cfg_ok['valor'] else plantilla_encuadre

        psicologo_data = {'nombres': '', 'apellidos': ''}
        cursor.execute("SELECT nombres, apellidos FROM usuarios WHERE id = ?", (psic_id,))
        u_p = cursor.fetchone()
        if u_p: psicologo_data = dict(u_p)

        cita_dict = {'nombre': patient_name, 'fecha': cita_fecha, 'hora': cita_hora, 'modalidad': next_cita['tipo_consulta'] or 'Presencial'}
        patient_dict = {'nombres': patient['nombres'], 'apellidos': patient['apellidos']}
        
        try:
            reply_text = format_whatsapp_message(tmpl_ok, patient_dict, cita_dict, psicologo_data)
        except Exception:
            reply_text = (
                f"¡Gracias por confirmar tu sesión, *{patient['nombres']}*! 🌿\n\n"
                f"📅 *Fecha:* {cita_fecha}\n"
                f"⏰ *Hora:* {cita_hora}\n\n"
                f"Recuerda habilitar tu espacio privado, realizar el pago y llegar a tiempo."
            )

        try:
            make_wa_http_request('POST', '/send', json_data={'phone': raw_phone, 'text': reply_text}, timeout=10)
        except Exception as wa_err:
            print(f"⚠️ No se pudo responder automáticamente por WhatsApp: {wa_err}")

        return jsonify({'status': 'confirmed', 'message': f'Cita #{cita_id} confirmada para {patient_name}'})

    elif is_cancel:
        cursor.execute("UPDATE agenda_finanzas SET confirmada = 0, estado_pago = 'Cancelada' WHERE id = ?", (cita_id,))
        try:
            cursor.execute("UPDATE citas SET confirmada = 0 WHERE paciente_id = ? AND fecha = ?", (patient_id, cita_fecha))
        except Exception:
            pass

        notif_msg = f"⚠️ WhatsApp: {patient_name} CANCELÓ su cita del {cita_fecha} a las {cita_hora}."
        cursor.execute("""
            INSERT INTO notificaciones (user_id, tipo, titulo, mensaje, fecha, leida, link)
            VALUES (?, 'whatsapp_cancellation', 'Cita Cancelada por WhatsApp', ?, ?, 0, '#agenda')
        """, (psic_id, notif_msg, now_formatted))
        db.commit()

        cursor.execute("SELECT valor FROM configuracion WHERE clave = 'msg_cancelacion_ok'")
        cfg_cancel = cursor.fetchone()
        tmpl_cancel = cfg_cancel['valor'] if cfg_cancel and cfg_cancel['valor'] else (
            "Entendido, *{nombre}*. Hemos registrado la cancelación de tu sesión del *{fecha}* a las *{hora}*.\n\nSi deseas reprogramar en otro momento, no dudes en escribirnos o agendar desde tu portal."
        )

        psicologo_data = {'nombres': '', 'apellidos': ''}
        cursor.execute("SELECT nombres, apellidos FROM usuarios WHERE id = ?", (psic_id,))
        u_p = cursor.fetchone()
        if u_p: psicologo_data = dict(u_p)

        cita_dict = {'nombre': patient_name, 'fecha': cita_fecha, 'hora': cita_hora, 'modalidad': next_cita['tipo_consulta'] or 'Presencial'}
        patient_dict = {'nombres': patient['nombres'], 'apellidos': patient['apellidos']}
        cancel_reply = format_whatsapp_message(tmpl_cancel, patient_dict, cita_dict, psicologo_data)

        try:
            make_wa_http_request('POST', '/send', json_data={'phone': raw_phone, 'text': cancel_reply}, timeout=10)
        except Exception as wa_err:
            print(f"⚠️ No se pudo enviar mensaje de cancelación por WhatsApp: {wa_err}")

        return jsonify({'status': 'cancelled', 'message': f'Cita #{cita_id} cancelada para {patient_name}'})

def get_time_in_patient_timezone(hora_str, pat_pais):
    """
    Convierte la hora de la cita (agendada en hora local de Venezuela / America/Caracas)
    a la hora local del país de residencia del paciente.
    """
    if not hora_str or not isinstance(hora_str, str) or ':' not in hora_str:
        return hora_str
        
    COUNTRY_TIMEZONES = {
        'venezuela': ('America/Caracas', 'Vzla'),
        'chile': ('America/Santiago', 'Chile'),
        'argentina': ('America/Argentina/Buenos_Aires', 'Arg'),
        'colombia': ('America/Bogota', 'Col'),
        'peru': ('America/Lima', 'Perú'),
        'perú': ('America/Lima', 'Perú'),
        'ecuador': ('America/Guayaquil', 'Ecuador'),
        'méxico': ('America/Mexico_City', 'Méx'),
        'mexico': ('America/Mexico_City', 'Méx'),
        'españa': ('Europe/Madrid', 'Esp'),
        'espana': ('Europe/Madrid', 'Esp'),
        'estados unidos': ('America/New_York', 'EST'),
        'eeuu': ('America/New_York', 'EST'),
        'usa': ('America/New_York', 'EST'),
        'panama': ('America/Panama', 'Panamá'),
        'panamá': ('America/Panama', 'Panamá'),
        'uruguay': ('America/Montevideo', 'Uruguay'),
        'costa rica': ('America/Costa_Rica', 'CR'),
        'república dominicana': ('America/Santo_Domingo', 'RD'),
        'dominicana': ('America/Santo_Domingo', 'RD'),
    }

    pais_clean = (pat_pais or '').strip().lower()
    tz_info = COUNTRY_TIMEZONES.get(pais_clean)
    
    if not tz_info:
        # Si el país no está registrado o es Venezuela, mantener la hora original
        return hora_str

    try:
        from datetime import datetime
        import zoneinfo
        
        parts = hora_str.strip().split(':')
        hh, mm = int(parts[0]), int(parts[1][:2])
        
        # Hora agendada en hora base (Venezuela America/Caracas)
        now = datetime.now()
        base_tz = zoneinfo.ZoneInfo("America/Caracas")
        target_tz = zoneinfo.ZoneInfo(tz_info[0])
        
        dt_base = datetime(now.year, now.month, now.day, hh, mm, tzinfo=base_tz)
        dt_target = dt_base.astimezone(target_tz)
        
        time_converted = dt_target.strftime('%H:%M')
        return f"{time_converted} (Hora {tz_info[1]})"
    except Exception as e:
        print("Error convirtiendo zona horaria de paciente:", e)
        return hora_str


def format_whatsapp_message(template_str, patient, cita, psicologo):
    if not template_str:
        template_str = "Hola {nombre}, te recordamos tu cita agendada para el {fecha} a las {hora} en modalidad {modalidad}. ¿Nos confirmas tu asistencia por favor?"
    
    # Extraer primer nombre — soporta tanto clave 'nombres' como 'nombre' (nombre completo)
    if isinstance(patient, dict) or hasattr(patient, 'get'):
        pat_nombres = patient.get('nombres', '') or patient.get('nombre', '')
        pat_pais = patient.get('pais', '')
    else:
        try:
            pat_nombres = patient['nombres']
            pat_pais = patient['pais'] if 'pais' in patient.keys() else ''
        except:
            pat_nombres = ''
            pat_pais = ''
            
    pat_name = pat_nombres.strip().split()[0] if pat_nombres and pat_nombres.strip() else "Consultante"
    
    # Extraer datos de la cita — soporta dict con clave 'modalidad' o 'tipo_consulta'
    if isinstance(cita, dict) or hasattr(cita, 'get'):
        c_fecha = cita.get('fecha', '')
        c_hora = cita.get('hora', '')
        c_tipo = cita.get('modalidad', '') or cita.get('tipo_consulta', 'Online')
        c_link = cita.get('link_conexion', '')
    else:
        c_fecha = cita['fecha']
        c_hora = cita['hora']
        c_tipo = cita['tipo_consulta'] if 'tipo_consulta' in cita.keys() else 'Online'
        c_link = cita['link_conexion'] if 'link_conexion' in cita.keys() else ''
    
    # Convertir hora a la zona horaria del paciente si aplica
    c_hora_paciente = get_time_in_patient_timezone(c_hora, pat_pais)
    
    psic_nom = f"Psic. {psicologo['nombres']} {psicologo['apellidos']}" if psicologo else "Tu Terapeuta"
    
    msg = template_str.replace('{nombre}', pat_name)
    msg = msg.replace('{nombre_paciente}', pat_name)
    msg = msg.replace('{fecha}', c_fecha)
    msg = msg.replace('{hora}', c_hora_paciente)
    msg = msg.replace('{modalidad}', c_tipo)
    msg = msg.replace('{link_conexion}', c_link or "Consultorio Presencial")
    msg = msg.replace('{psicologo}', psic_nom)
    msg = msg.replace('{nombre_psicologo}', psic_nom)
    return msg


@app.route('/api/whatsapp/sync-session', methods=['GET', 'POST', 'DELETE'])
def sync_whatsapp_session():
    import json
    db = get_db()
    cursor = db.cursor()
    user_id = str(request.args.get('user_id') or (request.json or {}).get('user_id') or '1')
    key_name = f'wa_auth_session_{user_id}'

    if request.method == 'DELETE':
        cursor.execute("DELETE FROM configuracion WHERE clave IN (?, 'wa_auth_session')", (key_name,))
        db.commit()
        return jsonify({'status': 'cleared'})
    elif request.method == 'POST':
        data = request.json or {}
        session_json = json.dumps(data)
        cursor.execute("INSERT OR REPLACE INTO configuracion (clave, valor) VALUES (?, ?)", (key_name, session_json))
        db.commit()
        return jsonify({'status': 'saved'})
    else:
        cursor.execute("SELECT valor FROM configuracion WHERE clave IN (?, 'wa_auth_session') ORDER BY clave DESC LIMIT 1", (key_name,))
        row = cursor.fetchone()
        if row and row['valor']:
            try:
                return jsonify(json.loads(row['valor']))
            except:
                return jsonify({})
        return jsonify({})

@app.route('/api/whatsapp/send-reminder/<int:cita_id>', methods=['POST'])
@login_required
def send_manual_whatsapp_reminder(cita_id):
    user_id = session.get('user_id')
    db = get_db()
    cursor = db.cursor()

    cursor.execute("""
        SELECT af.*, p.nombres as pat_nombres, p.apellidos as pat_apellidos, p.telefono as pat_telefono, p.pais as pat_pais
        FROM agenda_finanzas af
        JOIN pacientes p ON af.paciente_id = p.id
        WHERE af.id = ? AND p.psicologo_id = ?
    """, (cita_id, user_id))
    cita = cursor.fetchone()

    if not cita:
        return jsonify({'error': 'Cita o paciente no encontrado.'}), 404

    phone = cita['pat_telefono']
    if not phone or not phone.strip():
        return jsonify({'error': 'El paciente no tiene un número de teléfono registrado.'}), 400

    cursor.execute("SELECT nombres, apellidos FROM usuarios WHERE id = ?", (user_id,))
    psicologo = cursor.fetchone()

    cursor.execute("SELECT valor FROM configuracion WHERE clave = 'msg_recordatorio'")
    cfg_row = cursor.fetchone()
    template = cfg_row['valor'] if cfg_row and cfg_row['valor'] else None

    cita_dict = {
        'nombre': f"{cita['pat_nombres']} {cita['pat_apellidos']}",
        'fecha': cita['fecha'],
        'hora': cita['hora'],
        'modalidad': cita['tipo_consulta'] or 'Presencial'
    }
    mensaje_texto = format_whatsapp_message(template, cita_dict, cita_dict, psicologo)

    try:
        r = make_wa_http_request('POST', '/send', json_data={'phone': phone, 'text': mensaje_texto}, timeout=15)
        if r and r.status_code == 200:
            cursor.execute("UPDATE agenda_finanzas SET recordatorio_enviado_wa = 1 WHERE id = ?", (cita_id,))
            db.commit()
            return jsonify({'success': f'Recordatorio de WhatsApp enviado con éxito a {phone}.', 'phone': phone})
        else:
            res_data = r.json() if r else {}
            return jsonify({'error': res_data.get('error', 'Error al enviar mensaje por WhatsApp.')}), r.status_code if r else 500
    except Exception as e:
        return jsonify({'error': f'Error conectando con microservicio de WhatsApp: {str(e)}'}), 500

@app.route('/api/whatsapp/cron-send-reminders', methods=['GET', 'POST'])
def cron_send_whatsapp_reminders():
    import os
    from flask import has_request_context, jsonify
    CRON_SECRET = os.environ.get('CRON_SECRET', 'espacioterapeutico_cron_2024')
    if has_request_context():
        provided = request.args.get('key') or request.headers.get('X-Cron-Key', '')
        if provided != CRON_SECRET:
            return jsonify({'error': 'No autorizado'}), 401

    from datetime import datetime, timedelta
    try:
        import zoneinfo
        tz = zoneinfo.ZoneInfo("America/Caracas")
        now_local = datetime.now(tz)
    except Exception:
        # Fallback a UTC - 4 horas (hora Venezuela)
        now_local = datetime.utcnow() - timedelta(hours=4)

    current_hour = now_local.hour
    # Delimitar horario de envíos automáticos: NO enviar entre las 10:00 PM (22:00) y las 7:59 AM (07:59)
    if current_hour < 8 or current_hour >= 22:
        return jsonify({
            'status': 'skipped',
            'message': f'Filtro de horario laboral activo (10:00 PM - 7:59 AM). Hora actual: {current_hour:02d}:00. Los envíos automáticos están pausados hasta las 8:00 AM.',
            'confirmaciones_enviadas': 0,
            'recordatorios_enviados': 0
        })

    today_str = now_local.strftime('%Y-%m-%d')
    tomorrow_str = (now_local + timedelta(days=1)).strftime('%Y-%m-%d')
    current_time_str = now_local.strftime('%H:%M')
    
    db = get_db()
    cursor = db.cursor()

    # 0. VERIFICAR QUE EL BOT DE WHATSAPP ESTÉ CONECTADO
    wa_is_connected = False
    try:
        r_status = make_wa_http_request('GET', '/status', timeout=8)
        if r_status and r_status.status_code == 200:
            st_data = r_status.json() or {}
            if st_data.get('status') == 'connected':
                wa_is_connected = True
    except Exception as e_wa_st:
        print(f"⚠️ Error al verificar estado de WhatsApp en cron: {e_wa_st}")

    if not wa_is_connected:
        return jsonify({
            'status': 'paused_whatsapp_disconnected',
            'message': 'El servicio de WhatsApp está desconectado o requiere escaneo de QR. Envíos pausados automáticamente hasta reconexión.',
            'confirmaciones_enviadas': 0,
            'recordatorios_enviados': 0,
            'reagendamientos_enviados': 0,
            'cierres_enviados': 0
        })

    # Actualizar o asegurar plantilla con SI/NO si la existente es muy antigua o genérica
    cursor.execute("SELECT clave, valor FROM configuracion WHERE clave IN ('msg_confirmacion', 'msg_recordatorio', 'msg_reagendamiento', 'msg_cierre', 'auto_reagendamiento_activo')")
    cfg_rows = {r['clave']: r['valor'] for r in cursor.fetchall()}
    
    tmpl_conf_default = "Hola {nombre}, te escribimos para confirmar tu próxima sesión agendada para el *{fecha}* a las *{hora}* en modalidad *{modalidad}*.\n\nPor favor responde:\n✅ *SI* para confirmar tu asistencia\n❌ *NO* para cancelar\n\n¡Gracias!"
    
    msg_conf_db = cfg_rows.get('msg_confirmacion', '')
    if not msg_conf_db or ('SI' not in msg_conf_db and 'Sí' not in msg_conf_db and 'si' not in msg_conf_db):
        cursor.execute("INSERT OR REPLACE INTO configuracion (clave, valor) VALUES ('msg_confirmacion', ?)", (tmpl_conf_default,))
        db.commit()
        msg_conf_db = tmpl_conf_default

    tmpl_rec_default = cfg_rows.get('msg_recordatorio') or "Hola {nombre}, te recordamos que HOY tienes tu cita agendada a las {hora} en modalidad {modalidad}. ¡Nos vemos pronto!"

    enviados_confirmaciones = []
    enviados_recordatorios = []
    enviados_reagendamientos = []
    enviados_cierres = []
    errores = []

    # 1. ENVIAR CONFIRMACIONES PARA MAÑANA (Citas no confirmadas de mañana)
    cursor.execute("""
        SELECT af.*, p.nombres as pat_nombres, p.apellidos as pat_apellidos, p.telefono as pat_telefono, p.pais as pat_pais, p.psicologo_id,
               COALESCE(u.nombres, 'Paulo') as psic_nombres, COALESCE(u.apellidos, 'Mora') as psic_apellidos
        FROM agenda_finanzas af
        JOIN pacientes p ON af.paciente_id = p.id
        LEFT JOIN usuarios u ON (p.psicologo_id = u.id OR (p.psicologo_id IS NULL AND u.id = 1))
        WHERE af.fecha = ? AND COALESCE(af.confirmada, 0) = 0 AND COALESCE(af.estado_pago, '') != 'Cancelada' AND COALESCE(af.confirmacion_enviada_wa, 0) = 0
    """, (tomorrow_str,))
    citas_confirmar = cursor.fetchall()

    for cita in citas_confirmar:
        phone = cita['pat_telefono']
        if not phone or not phone.strip():
            continue
        psicologo_data = {'nombres': cita['psic_nombres'], 'apellidos': cita['psic_apellidos']}
        cita_dict = {
            'nombre': f"{cita['pat_nombres']} {cita['pat_apellidos']}",
            'fecha': cita['fecha'],
            'hora': cita['hora'],
            'modalidad': cita['tipo_consulta'] or 'Presencial'
        }
        patient_dict = {
            'nombres': cita['pat_nombres'],
            'apellidos': cita['pat_apellidos'],
            'pais': cita['pat_pais'] or ''
        }
        mensaje_texto = format_whatsapp_message(msg_conf_db, patient_dict, cita_dict, psicologo_data)
        psych_id = cita['psicologo_id'] or 1

        cursor.execute("UPDATE agenda_finanzas SET confirmacion_enviada_wa = 1 WHERE id = ?", (cita['id'],))
        db.commit()

        try:
            r = make_wa_http_request('POST', '/send', json_data={'phone': phone, 'text': mensaje_texto}, timeout=15, user_id=psych_id)
            if r and r.status_code == 200:
                enviados_confirmaciones.append({'cita_id': cita['id'], 'paciente': f"{cita['pat_nombres']} {cita['pat_apellidos']}", 'phone': phone, 'tipo': 'confirmacion'})
            else:
                err_msg = 'Timeout de microservicio'
                if r:
                    try: err_msg = r.json().get('error', r.text)
                    except: err_msg = r.text
                errores.append({'cita_id': cita['id'], 'paciente': f"{cita['pat_nombres']} {cita['pat_apellidos']}", 'phone': phone, 'error': err_msg})
        except Exception as e:
            errores.append({'cita_id': cita['id'], 'paciente': f"{cita['pat_nombres']} {cita['pat_apellidos']}", 'phone': phone, 'error': str(e)})

    # 2. ENVIAR RECORDATORIOS DEL DÍA (Citas de Hoy CONFIRMADAS)
    cursor.execute("""
        SELECT af.*, p.nombres as pat_nombres, p.apellidos as pat_apellidos, p.telefono as pat_telefono, p.pais as pat_pais, p.psicologo_id,
               COALESCE(u.nombres, 'Paulo') as psic_nombres, COALESCE(u.apellidos, 'Mora') as psic_apellidos
        FROM agenda_finanzas af
        JOIN pacientes p ON af.paciente_id = p.id
        LEFT JOIN usuarios u ON (p.psicologo_id = u.id OR (p.psicologo_id IS NULL AND u.id = 1))
        WHERE af.fecha = ? AND COALESCE(af.confirmada, 0) = 1 AND COALESCE(af.estado_pago, '') != 'Cancelada' AND COALESCE(af.recordatorio_enviado_wa, 0) = 0
    """, (today_str,))
    citas_recordar = cursor.fetchall()

    for cita in citas_recordar:
        phone = cita['pat_telefono']
        if not phone or not phone.strip():
            continue
        psicologo_data = {'nombres': cita['psic_nombres'], 'apellidos': cita['psic_apellidos']}
        cita_dict = {
            'nombre': f"{cita['pat_nombres']} {cita['pat_apellidos']}",
            'fecha': cita['fecha'],
            'hora': cita['hora'],
            'modalidad': cita['tipo_consulta'] or 'Presencial'
        }
        patient_dict = {
            'nombres': cita['pat_nombres'],
            'apellidos': cita['pat_apellidos'],
            'pais': cita['pat_pais'] or ''
        }
        mensaje_texto = format_whatsapp_message(tmpl_rec_default, patient_dict, cita_dict, psicologo_data)
        psych_id = cita['psicologo_id'] or 1

        cursor.execute("UPDATE agenda_finanzas SET recordatorio_enviado_wa = 1 WHERE id = ?", (cita['id'],))
        db.commit()

        try:
            r = make_wa_http_request('POST', '/send', json_data={'phone': phone, 'text': mensaje_texto}, timeout=15, user_id=psych_id)
            if r and r.status_code == 200:
                enviados_recordatorios.append({'cita_id': cita['id'], 'paciente': f"{cita['pat_nombres']} {cita['pat_apellidos']}", 'phone': phone, 'tipo': 'recordatorio'})
            else:
                err_msg = 'Timeout de microservicio'
                if r:
                    try: err_msg = r.json().get('error', r.text)
                    except: err_msg = r.text
                errores.append({'cita_id': cita['id'], 'paciente': f"{cita['pat_nombres']} {cita['pat_apellidos']}", 'phone': phone, 'error': err_msg})
        except Exception as e:
            errores.append({'cita_id': cita['id'], 'paciente': f"{cita['pat_nombres']} {cita['pat_apellidos']}", 'phone': phone, 'error': str(e)})

    # 3. ENVIAR MENSAJES DE CIERRE O REENGANCHE (POST-SESIÓN)
    tmpl_cierre_default = cfg_rows.get('msg_cierre') or "Hola {nombre}, gracias por compartir el espacio terapéutico hoy. Recuerda realizar las tareas asignadas. Si deseas agendar o reprogramar tu próxima sesión, puedes hacerlo desde tu portal."

    # Buscar citas de hoy cuyo horario ya transcurrió O citas pasadas sin cita futura agendada
    past_7_days_str = (now_local - timedelta(days=7)).strftime('%Y-%m-%d')
    cursor.execute("""
        SELECT af.*, p.nombres as pat_nombres, p.apellidos as pat_apellidos, p.telefono as pat_telefono, p.pais as pat_pais, p.psicologo_id,
               COALESCE(u.nombres, 'Paulo') as psic_nombres, COALESCE(u.apellidos, 'Mora') as psic_apellidos
        FROM agenda_finanzas af
        JOIN pacientes p ON af.paciente_id = p.id
        LEFT JOIN usuarios u ON (p.psicologo_id = u.id OR (p.psicologo_id IS NULL AND u.id = 1))
        WHERE (
                (af.fecha = ? AND af.hora <= ?)
                OR
                (af.fecha < ? AND af.fecha >= ?)
              )
          AND COALESCE(af.confirmada, 0) = 1
          AND COALESCE(af.estado_pago, '') != 'Cancelada'
          AND COALESCE(af.cierre_enviado_wa, 0) = 0
          AND NOT EXISTS (
              SELECT 1 FROM agenda_finanzas af_future 
              WHERE af_future.paciente_id = af.paciente_id AND af_future.fecha > af.fecha
          )
        ORDER BY af.fecha ASC, af.hora ASC
    """, (today_str, current_time_str, today_str, past_7_days_str))
    citas_cierre = cursor.fetchall()

    for cita in citas_cierre:
        phone = cita['pat_telefono']
        if not phone or not phone.strip():
            continue
        psicologo_data = {'nombres': cita['psic_nombres'], 'apellidos': cita['psic_apellidos']}
        cita_dict = {
            'nombre': f"{cita['pat_nombres']} {cita['pat_apellidos']}",
            'fecha': cita['fecha'],
            'hora': cita['hora'],
            'modalidad': cita['tipo_consulta'] or 'Presencial'
        }
        patient_dict = {
            'nombres': cita['pat_nombres'],
            'apellidos': cita['pat_apellidos'],
            'pais': cita['pat_pais'] or ''
        }
        mensaje_texto = format_whatsapp_message(tmpl_cierre_default, patient_dict, cita_dict, psicologo_data)
        psych_id = cita['psicologo_id'] or 1

        cursor.execute("UPDATE agenda_finanzas SET cierre_enviado_wa = 1 WHERE id = ?", (cita['id'],))
        db.commit()

        try:
            r = make_wa_http_request('POST', '/send', json_data={'phone': phone, 'text': mensaje_texto}, timeout=15, user_id=psych_id)
            if r and r.status_code == 200:
                enviados_cierres.append({'cita_id': cita['id'], 'paciente': f"{cita['pat_nombres']} {cita['pat_apellidos']}", 'phone': phone, 'tipo': 'cierre'})
        except Exception as e:
            pass

    # 4. ENVIAR REAGENDAMIENTO AL FINAL DEL HORARIO LABORAL (18:00 a 21:59)
    if current_hour >= 18 and current_hour < 22:
        auto_reag_activo = (cfg_rows.get('auto_reagendamiento_activo') == '1')
        
        if auto_reag_activo:
            tmpl_reag_default = cfg_rows.get('msg_reagendamiento') or "Hola {nombre}, notamos que no pudimos realizar tu sesión agendada para el *{fecha}*. Te invitamos a agendar un nuevo espacio ingresando a nuestra plataforma o respondiendo a este mensaje. ¡Estamos para acompañarte!"

            cursor.execute("""
                SELECT af.*, p.nombres as pat_nombres, p.apellidos as pat_apellidos, p.telefono as pat_telefono, p.pais as pat_pais, p.psicologo_id,
                       COALESCE(u.nombres, 'Paulo') as psic_nombres, COALESCE(u.apellidos, 'Mora') as psic_apellidos
                FROM agenda_finanzas af
                JOIN pacientes p ON af.paciente_id = p.id
                LEFT JOIN usuarios u ON (p.psicologo_id = u.id OR (p.psicologo_id IS NULL AND u.id = 1))
                WHERE (af.fecha = ? OR af.fecha = ?) 
                  AND COALESCE(af.confirmada, 0) = 0 
                  AND COALESCE(af.reagendamiento_enviado_wa, 0) = 0
                  AND COALESCE(af.estado_pago, '') NOT IN ('Cancelada', 'Pagado', 'Paga', 'Completada')
                  AND NOT EXISTS (
                      SELECT 1 FROM agenda_finanzas af_future 
                      WHERE af_future.paciente_id = af.paciente_id AND af_future.fecha > af.fecha
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM sesiones s 
                      WHERE s.paciente_id = af.paciente_id AND s.fecha >= af.fecha
                  )
            """, (today_str, (now_local - timedelta(days=1)).strftime('%Y-%m-%d')))
            citas_reagendar = cursor.fetchall()

            for cita in citas_reagendar:
                phone = cita['pat_telefono']
                if not phone or not phone.strip():
                    continue
                psicologo_data = {'nombres': cita['psic_nombres'], 'apellidos': cita['psic_apellidos']}
                cita_dict = {
                    'nombre': f"{cita['pat_nombres']} {cita['pat_apellidos']}",
                    'fecha': cita['fecha'],
                    'hora': cita['hora'],
                    'modalidad': cita['tipo_consulta'] or 'Presencial'
                }
                patient_dict = {
                    'nombres': cita['pat_nombres'],
                    'apellidos': cita['pat_apellidos'],
                    'pais': cita['pat_pais'] or ''
                }
                mensaje_texto = format_whatsapp_message(tmpl_reag_default, patient_dict, cita_dict, psicologo_data)
                psych_id = cita['psicologo_id'] or 1

                cursor.execute("UPDATE agenda_finanzas SET reagendamiento_enviado_wa = 1 WHERE id = ?", (cita['id'],))
                db.commit()

                try:
                    r = make_wa_http_request('POST', '/send', json_data={'phone': phone, 'text': mensaje_texto}, timeout=15, user_id=psych_id)
                    if r and r.status_code == 200:
                        enviados_reagendamientos.append({'cita_id': cita['id'], 'paciente': f"{cita['pat_nombres']} {cita['pat_apellidos']}", 'phone': phone, 'tipo': 'reagendamiento'})
                except Exception as e:
                    pass

    # 5. RECORDATORIO NOCTURNO A PACIENTES (20:00 - 21:00 hrs) PARA ACTUALIZAR HERRAMIENTAS TERAPÉUTICAS
    if current_hour == 20:
        try:
            cursor.execute("""
                SELECT DISTINCT p.id, p.nombres, p.telefono, p.psicologo_id 
                FROM pacientes p
                JOIN modulos_terapeuticos_paciente m ON p.id = m.paciente_id
                WHERE m.activo = 1 AND COALESCE(p.activo, 1) = 1
            """)
            patients_with_tools = cursor.fetchall()
            for p_row in patients_with_tools:
                pid = p_row['id']
                p_phone = p_row['telefono']
                p_name = p_row['nombres']
                
                # Notificar en Firebase Portal
                notify_patient_firebase(
                    pid, 
                    "🌙 Recordatorio Diarios & Herramientas", 
                    f"Hola {p_name}, recuerda ingresar hoy a tu portal para registrar tu avance en tus herramientas terapéuticas asignadas.", 
                    icon="🌙"
                )
                
                # Notificar vía WhatsApp si el bot está conectado y se tiene número
                if p_phone and p_phone.strip():
                    try:
                        msg_wa = f"Hola *{p_name}* 🌿, te recordamos ingresar hoy a tu portal para actualizar tus avances en las herramientas terapéuticas asignadas. ¡Que tengas feliz noche!"
                        make_wa_http_request('POST', '/send', json_data={'phone': p_phone, 'text': msg_wa}, timeout=10, user_id=p_row['psicologo_id'] or 1)
                    except Exception:
                        pass
        except Exception as _e_rem:
            print("Error en recordatorio nocturno de herramientas:", _e_rem)

    db.commit()

    return jsonify({
        'success': True,
        'confirmaciones_enviadas': len(enviados_confirmaciones),
        'recordatorios_enviados': len(enviados_recordatorios),
        'reagendamientos_enviados': len(enviados_reagendamientos),
        'cierres_enviados': len(enviados_cierres),
        'detalles': {
            'confirmaciones': enviados_confirmaciones,
            'recordatorios': enviados_recordatorios,
            'reagendamientos': enviados_reagendamientos,
            'cierres': enviados_cierres,
            'errores': errores
        },
        'summary': {
            'confirmaciones': enviados_confirmaciones,
            'recordatorios': enviados_recordatorios,
            'reagendamientos': enviados_reagendamientos,
            'cierres': enviados_cierres,
            'errores': errores
        }
    })

@app.route('/api/whatsapp/queue-status', methods=['GET'])
@login_required
def get_whatsapp_queue_status():
    psic_id = get_psicologo_id_filter()
    db = get_db()
    cursor = db.cursor()

    # Garantizar creación automática de columnas en SQLite
    try:
        cursor.execute("PRAGMA table_info(agenda_finanzas)")
        cols_fin = [r[1] for r in cursor.fetchall()]
        if 'reagendamiento_enviado_wa' not in cols_fin:
            cursor.execute("ALTER TABLE agenda_finanzas ADD COLUMN reagendamiento_enviado_wa INTEGER DEFAULT 0")
        if 'confirmacion_enviada_wa' not in cols_fin:
            cursor.execute("ALTER TABLE agenda_finanzas ADD COLUMN confirmacion_enviada_wa INTEGER DEFAULT 0")
        if 'recordatorio_enviado_wa' not in cols_fin:
            cursor.execute("ALTER TABLE agenda_finanzas ADD COLUMN recordatorio_enviado_wa INTEGER DEFAULT 0")
        if 'cierre_enviado_wa' not in cols_fin:
            cursor.execute("ALTER TABLE agenda_finanzas ADD COLUMN cierre_enviado_wa INTEGER DEFAULT 0")

        cursor.execute("PRAGMA table_info(citas)")
        cols_citas = [r[1] for r in cursor.fetchall()]
        if 'reagendamiento_enviado_wa' not in cols_citas:
            cursor.execute("ALTER TABLE citas ADD COLUMN reagendamiento_enviado_wa INTEGER DEFAULT 0")
        if 'confirmacion_enviada_wa' not in cols_citas:
            cursor.execute("ALTER TABLE citas ADD COLUMN confirmacion_enviada_wa INTEGER DEFAULT 0")
        if 'recordatorio_enviado_wa' not in cols_citas:
            cursor.execute("ALTER TABLE citas ADD COLUMN recordatorio_enviado_wa INTEGER DEFAULT 0")
        if 'cierre_enviado_wa' not in cols_citas:
            cursor.execute("ALTER TABLE citas ADD COLUMN cierre_enviado_wa INTEGER DEFAULT 0")
        db.commit()
    except Exception as ex_col:
        print("Aviso al migrar columnas de cola de WhatsApp:", ex_col)

    from datetime import datetime, timedelta
    try:
        import zoneinfo
        tz = zoneinfo.ZoneInfo("America/Caracas")
        now_local = datetime.now(tz)
    except Exception:
        now_local = datetime.utcnow() - timedelta(hours=4)

    today_str = now_local.strftime('%Y-%m-%d')
    yesterday_str = (now_local - timedelta(days=1)).strftime('%Y-%m-%d')
    current_time_str = now_local.strftime('%H:%M')

    queue = []
    try:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='citas'")
        has_citas_table = cursor.fetchone() is not None
        if has_citas_table:
            join_clause = "LEFT JOIN citas c ON c.paciente_id = p.id AND c.fecha = af.fecha"
            estado_col = "COALESCE(c.estado, 'Agendada') as estado_cita"
        else:
            join_clause = ""
            estado_col = "'Agendada' as estado_cita"

        user_id = session.get('user_id', 1)
        
        # --- 1. MENSAJES DE CITAS (CONFIRMACIONES, RECORDATORIOS, CIERRE Y REAGENDAMIENTOS) ---
        if user_id == 1:
            sql = f"""
                SELECT af.id, af.fecha, af.hora, af.tipo_consulta, af.confirmada,
                       COALESCE(af.confirmacion_enviada_wa, 0) as confirmacion_enviada,
                       COALESCE(af.recordatorio_enviado_wa, 0) as recordatorio_enviado,
                       COALESCE(af.reagendamiento_enviado_wa, 0) as reagendamiento_enviado,
                       COALESCE(af.cierre_enviado_wa, 0) as cierre_enviado,
                       {estado_col},
                       p.id as paciente_id, p.nombres as pat_nombres, p.apellidos as pat_apellidos, p.telefono as pat_telefono
                FROM agenda_finanzas af
                JOIN pacientes p ON af.paciente_id = p.id
                {join_clause}
                WHERE (p.psicologo_id = 1 OR p.psicologo_id IS NULL) AND af.fecha >= ?
                ORDER BY af.fecha ASC, af.hora ASC
                LIMIT 50
            """
            cursor.execute(sql, (yesterday_str,))
        else:
            sql = f"""
                SELECT af.id, af.fecha, af.hora, af.tipo_consulta, af.confirmada,
                       COALESCE(af.confirmacion_enviada_wa, 0) as confirmacion_enviada,
                       COALESCE(af.recordatorio_enviado_wa, 0) as recordatorio_enviado,
                       COALESCE(af.reagendamiento_enviado_wa, 0) as reagendamiento_enviado,
                       COALESCE(af.cierre_enviado_wa, 0) as cierre_enviado,
                       {estado_col},
                       p.id as paciente_id, p.nombres as pat_nombres, p.apellidos as pat_apellidos, p.telefono as pat_telefono
                FROM agenda_finanzas af
                JOIN pacientes p ON af.paciente_id = p.id
                {join_clause}
                WHERE p.psicologo_id = ? AND af.fecha >= ?
                ORDER BY af.fecha ASC, af.hora ASC
                LIMIT 50
            """
            cursor.execute(sql, (user_id, yesterday_str))
        
        rows = cursor.fetchall()

        for r in rows:
            fecha_cita = r['fecha']
            hora_cita = r['hora']
            pat_name = f"{r['pat_nombres']} {r['pat_apellidos']}"
            phone = r['pat_telefono'] or ''
            estado_c = r['estado_cita']
            is_confirmada = (r['confirmada'] == 1 or estado_c == 'Confirmada')
            is_cancelada = (estado_c == 'Cancelada')

            tomorrow_str = (now_local + timedelta(days=1)).strftime('%Y-%m-%d')

            if fecha_cita == tomorrow_str:
                if r['confirmacion_enviada'] == 1:
                    if is_confirmada:
                        pipeline_status = 'confirmado'
                        pipeline_label = '✅ Confirmado por Paciente'
                        priority = 4
                    elif is_cancelada:
                        pipeline_status = 'cancelado'
                        pipeline_label = '❌ Cancelado por Paciente'
                        priority = 5
                    else:
                        pipeline_status = 'enviado_conf'
                        pipeline_label = '🚀 Confirmación Enviada (Esperando Respuesta)'
                        priority = 3
                else:
                    pipeline_status = 'en_cola_conf'
                    pipeline_label = '📥 En Cola (Confirmación 24h)'
                    priority = 1
            elif fecha_cita > tomorrow_str:
                if r['confirmacion_enviada'] == 1:
                    pipeline_status = 'enviado_conf'
                    pipeline_label = '🚀 Confirmación Enviada'
                    priority = 3
                else:
                    pipeline_status = 'esperando_fecha'
                    pipeline_label = '⏳ Programado en Cola'
                    priority = 2
            elif fecha_cita == today_str:
                if is_confirmada:
                    if r['cierre_enviado'] == 1:
                        pipeline_status = 'enviado_cierre'
                        pipeline_label = '🚀 Mensaje de Cierre Enviado'
                        priority = 4
                    elif r['recordatorio_enviado'] == 1:
                        if hora_cita <= current_time_str:
                            pipeline_status = 'en_cola_cierre'
                            pipeline_label = '📥 En Cola (Mensaje de Cierre)'
                            priority = 1
                        else:
                            pipeline_status = 'enviado_rec'
                            pipeline_label = '🚀 Recordatorio Enviado Hoy'
                            priority = 4
                    else:
                        pipeline_status = 'en_cola'
                        pipeline_label = '📥 En Cola (Recordatorio Hoy)'
                        priority = 1
                elif is_cancelada:
                    pipeline_status = 'cancelado'
                    pipeline_label = '❌ Cancelado por Paciente'
                    priority = 5
                else:
                    if r['reagendamiento_enviado'] == 1:
                        pipeline_status = 'reagendar_enviado'
                        pipeline_label = '🔄 Reagendamiento Enviado'
                        priority = 4
                    else:
                        pipeline_status = 'en_cola_reagendar'
                        pipeline_label = '📥 En Cola (Reagendamiento Fin de Día)'
                        priority = 1
            else:
                if r['cierre_enviado'] == 1:
                    pipeline_status = 'enviado_cierre'
                    pipeline_label = '🚀 Mensaje de Cierre Enviado'
                    priority = 4
                elif r['reagendamiento_enviado'] == 1:
                    pipeline_status = 'reagendar_enviado'
                    pipeline_label = '🔄 Reagendamiento Enviado'
                    priority = 4
                elif is_confirmada:
                    pipeline_status = 'en_cola_cierre'
                    pipeline_label = '📥 En Cola (Mensaje de Cierre Pendiente)'
                    priority = 1
                else:
                    pipeline_status = 'pendiente_reagendar'
                    pipeline_label = '📥 Pendiente Reagendar'
                    priority = 4

            queue.append({
                'cita_id': r['id'],
                'paciente_nombre': pat_name,
                'telefono': phone,
                'fecha': fecha_cita,
                'hora': hora_cita,
                'tipo_consulta': r['tipo_consulta'] or 'Presencial',
                'pipeline_status': pipeline_status,
                'pipeline_label': pipeline_label,
                'priority': priority
            })

        # --- 2. MENSAJES DE CUMPLEAEÑOS EN PROGRAMACIÓN / COLA ---
        if user_id == 1:
            sql_dob = """
                SELECT id, nombres, apellidos, fecha_nacimiento, telefono
                FROM pacientes
                WHERE fecha_nacimiento IS NOT NULL AND fecha_nacimiento != '' AND (psicologo_id = 1 OR psicologo_id IS NULL)
            """
            cursor.execute(sql_dob)
        else:
            sql_dob = """
                SELECT id, nombres, apellidos, fecha_nacimiento, telefono
                FROM pacientes
                WHERE fecha_nacimiento IS NOT NULL AND fecha_nacimiento != '' AND psicologo_id = ?
            """
            cursor.execute(sql_dob, (user_id,))
        
        dob_patients = cursor.fetchall()
        for p_dob in dob_patients:
            dob_raw = str(p_dob['fecha_nacimiento']).strip()
            dob_norm = normalize_date_str(dob_raw)
            if len(dob_norm) >= 10:
                m_str, d_str = dob_norm[5:7], dob_norm[8:10]
                try:
                    m_int, d_int = int(m_str), int(d_str)
                    target_bday = datetime(now_local.year, m_int, d_int).date()
                    today_date = now_local.date()
                    delta_days = (target_bday - today_date).days

                    # Si el cumpleaños fue a principios de año y faltan muchos meses, ignorar para cola próxima
                    if 0 <= delta_days <= 7:
                        pat_dob_name = f"{p_dob['nombres']} {p_dob['apellidos']}".strip()
                        pat_phone = p_dob['telefono'] or ''
                        
                        if delta_days == 0:
                            # Verificar si fue enviado hoy en notificaciones
                            cursor.execute("""
                                SELECT id FROM notificaciones
                                WHERE user_id = ? AND tipo = 'cumpleanos_wa' AND mensaje LIKE ? AND fecha LIKE ?
                            """, (user_id, f"%ID: {p_dob['id']}%", f"{today_str}%"))
                            already_sent = cursor.fetchone() is not None
                            
                            queue.append({
                                'cita_id': f"dob_{p_dob['id']}",
                                'paciente_nombre': pat_dob_name,
                                'telefono': pat_phone,
                                'fecha': today_str,
                                'hora': '09:00 AM',
                                'tipo_consulta': '🎉 Cumpleaños',
                                'pipeline_status': 'enviado_cumpleanos' if already_sent else 'en_cola_cumpleanos',
                                'pipeline_label': '🎂 Felicitación de Cumpleaños Enviada' if already_sent else '🎉 En Cola (Felicitación de Cumpleaños Hoy)',
                                'priority': 4 if already_sent else 1
                            })
                        else:
                            bday_str = target_bday.strftime('%Y-%m-%d')
                            queue.append({
                                'cita_id': f"dob_{p_dob['id']}",
                                'paciente_nombre': pat_dob_name,
                                'telefono': pat_phone,
                                'fecha': bday_str,
                                'hora': '09:00 AM',
                                'tipo_consulta': '🎉 Cumpleaños',
                                'pipeline_status': 'esperando_cumpleanos',
                                'pipeline_label': f'🎂 Programado (Cumpleaños en {delta_days} días)',
                                'priority': 2
                            })
                except Exception:
                    pass

        # Ordenar cola: Primero los pendientes/en cola (prioridad 1 y 2), al final los enviados y realizados
        queue.sort(key=lambda x: (x['priority'], x['fecha'], x['hora']))
    except Exception as e_q:
        import traceback
        print("Error en consulta de cola de WhatsApp:", e_q)
        traceback.print_exc()
        return jsonify({'queue': queue, 'debug_error': str(e_q)})

    return jsonify({'queue': queue})

# --- SCHEDULER DE WHATSAPP EN SEGUNDO PLANO (AUTOMÁTICO) ---
_wa_cron_thread_started = False

def start_whatsapp_cron_scheduler():
    global _wa_cron_thread_started
    if _wa_cron_thread_started:
        return
    _wa_cron_thread_started = True

    import threading
    import time

    def _scheduler_loop():
        time.sleep(10)
        while True:
            try:
                # 1. Heartbeat a Render para mantener despierto el microservicio 24/7
                try:
                    make_wa_http_request('GET', '/status', timeout=10)
                except Exception:
                    pass

                # 2. Ejecutar chequeo de envio de recordatorios y confirmaciones
                with app.app_context():
                    cron_send_whatsapp_reminders()

            except Exception as e:
                print(f"[WARN] Error en scheduler background de WhatsApp: {e}")
            
            time.sleep(180)  # Chequear cada 3 minutos (180s)

    t = threading.Thread(target=_scheduler_loop, daemon=True)
    t.start()

try:
    start_whatsapp_cron_scheduler()
except Exception as _st_err:
    print("[WARN] Error iniciando scheduler de WhatsApp:", _st_err)

# ==========================================
# RUTAS DE MÓDULOS TERAPÉUTICOS PERSONALIZADOS
# (Sueño, Ansiedad, Sobriedad)
# ==========================================

@app.route('/api/patients/<int:patient_id>/modules', methods=['GET'])
@login_required
def get_patient_modules(patient_id):
    user_id = session.get('user_id')
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute("SELECT id, nombres, apellidos FROM pacientes WHERE id = ? AND psicologo_id = ?", (patient_id, user_id))
    patient = cursor.fetchone()
    if not patient:
        return jsonify({'error': 'Paciente no encontrado o sin permisos.'}), 404
        
    cursor.execute("SELECT modulo_clave, activo FROM modulos_terapeuticos_paciente WHERE paciente_id = ?", (patient_id,))
    rows = cursor.fetchall()
    active_map = {r['modulo_clave']: r['activo'] for r in rows}
    
    catalog = [
        {'clave': 'sueno', 'nombre': 'Higiene del Sueño', 'activo': active_map.get('sueno', 0)},
        {'clave': 'ansiedad', 'nombre': 'Diario de Ansiedad (Checklist)', 'activo': active_map.get('ansiedad', 0)},
        {'clave': 'sobriedad', 'nombre': 'Registro de Consumo (Días Consecutivos)', 'activo': active_map.get('sobriedad', 0)},
        {'clave': 'pantalla', 'nombre': 'Registro de Consumo de Pantallas (Uso Digital)', 'activo': active_map.get('pantalla', 0)},
        {'clave': 'adherencia', 'nombre': 'Adherencia al Tratamiento (Medicación)', 'activo': active_map.get('adherencia', 0)},
        {'clave': 'activacion', 'nombre': 'Activación Conductual (Tareas Diarias)', 'activo': active_map.get('activacion', 0)},
        {'clave': 'ingesta', 'nombre': 'Ingesta de Alimentos y Apetito', 'activo': active_map.get('ingesta', 0)},
        {'clave': 'cognitivo', 'nombre': 'Registro Cognitivo (TCC)', 'activo': active_map.get('cognitivo', 0)}
    ]
    return jsonify({'patient': dict(patient), 'modules': catalog})

@app.route('/api/patients/<int:patient_id>/modules/toggle', methods=['POST'])
@login_required
def toggle_patient_module(patient_id):
    user_id = session.get('user_id')
    data = request.json or {}
    modulo_clave = data.get('modulo_clave')
    activo = int(data.get('activo', 0))
    
    if not modulo_clave:
        return jsonify({'error': 'Clave de módulo requerida.'}), 400
        
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT id FROM pacientes WHERE id = ? AND psicologo_id = ?", (patient_id, user_id))
    if not cursor.fetchone():
        return jsonify({'error': 'Paciente no encontrado o sin permisos.'}), 404
        
    cursor.execute("""
        INSERT INTO modulos_terapeuticos_paciente (paciente_id, modulo_clave, activo)
        VALUES (?, ?, ?)
        ON CONFLICT(paciente_id, modulo_clave) DO UPDATE SET activo = excluded.activo
    """, (patient_id, modulo_clave, activo))
    db.commit()
    
    import threading
    threading.Thread(target=sync_patient_to_firebase, args=(patient_id,)).start()
    
    if activo == 1:
        mod_nombres = {
            'sueno': 'Registro de Higiene del Sueño',
            'ansiedad': 'Diario de Ansiedad',
            'sobriedad': 'Registro de Consumo y Sobriedad',
            'adherencia': 'Adherencia a Medicación',
            'activacion': 'Activación Conductual',
            'ingesta': 'Ingesta y Apetito',
            'cognitivo': 'Registro Cognitivo',
            'pantalla': 'Tracker de Pantalla'
        }
        mod_nombre = mod_nombres.get(modulo_clave, modulo_clave.capitalize())
        notify_patient_firebase(
            patient_id,
            "🛠️ Nueva Herramienta Asignada",
            f"Tu psicólogo te ha asignado la herramienta '{mod_nombre}' en tu portal.",
            icon="🛠️"
        )
    
    return jsonify({'success': True, 'modulo_clave': modulo_clave, 'activo': activo})

@app.route('/api/therapist/modules/catalog', methods=['GET'])
@login_required
def get_therapist_modules_catalog():
    user_id = session.get('user_id')
    db = get_db()
    cursor = db.cursor()
    
    modules_info = [
        {
            'clave': 'sueno',
            'nombre': 'Registro de Higiene del Sueño',
            'descripcion': 'Cuestionario de 8 ítems diarios para seguimiento del descanso, despertares nocturnos y síntomas de agotamiento.',
            'icono': '🌙'
        },
        {
            'clave': 'ansiedad',
            'nombre': 'Diario de Ansiedad & Síntomas',
            'descripcion': 'Registro en calendario con escala 1-10 y checklist de 11 síntomas físicos y cognitivos.',
            'icono': '⚡'
        },
        {
            'clave': 'sobriedad',
            'nombre': 'Registro de Consumo',
            'descripcion': 'Tracker de seguimiento con contador de días consecutivos sin consumo, medalla de logro y registro de eventos.',
            'icono': '🏅'
        },
        {
            'clave': 'adherencia',
            'nombre': 'Adherencia al Tratamiento (Medicación)',
            'descripcion': 'Seguimiento de dosis y horarios de medicamentos prescritos con checklist y calendario diario.',
            'icono': '💊'
        },
        {
            'clave': 'activacion',
            'nombre': 'Activación Conductual',
            'descripcion': 'Checklist diario de actividades Necesarias, de Disfrute/Placer y Cotidianas/Rutina asignadas por el psicólogo.',
            'icono': '🏃‍♂️'
        },
        {
            'clave': 'ingesta',
            'nombre': 'Ingesta de Alimentos y Apetito',
            'descripcion': 'Registro de comidas (desayuno, almuerzo, merienda, cena), escalas de apetito y saciedad (0-10), contexto, afectividad y conductas.',
            'icono': '🥗'
        },
        {
            'clave': 'cognitivo',
            'nombre': 'Registro Cognitivo',
            'descripcion': 'Reestructuración cognitiva TCC: registro de situación desencadenante, pensamientos automáticos, emoción/sensación (0-10) y conducta realizada.',
            'icono': '🧠'
        },
        {
            'clave': 'pantalla',
            'nombre': 'Tracker de Consumo de Pantalla',
            'descripcion': 'Cuestionario interactivo por chips para monitoreo de tiempo de uso, dispositivos, aplicaciones, contenido, impacto emocional e interferencia.',
            'icono': '📱'
        }
    ]
    
    catalog = []
    
    for mod in modules_info:
        clave = mod['clave']
        try:
            # Buscar pacientes activos para este módulo
            cursor.execute("""
                SELECT mt.paciente_id, p.nombres, p.apellidos, p.cedula
                FROM modulos_terapeuticos_paciente mt
                JOIN pacientes p ON mt.paciente_id = p.id
                WHERE p.psicologo_id = ? AND mt.modulo_clave = ? AND mt.activo = 1
                ORDER BY p.apellidos ASC, p.nombres ASC
            """, (user_id, clave))
            patients_rows = cursor.fetchall()
            
            patients_list = []
            for p_row in patients_rows:
                pid = p_row['paciente_id']
                p_name = f"{p_row['nombres'] or ''} {p_row['apellidos'] or ''}".strip() or f"Consultante #{pid}"
                p_cedula = p_row['cedula'] or ''
                
                metric_text = "Sin registros recientes"
                
                # Obtener la métrica más reciente según la herramienta
                if clave == 'sueno':
                    cursor.execute("""
                        SELECT hora_dormi, hora_desperto, senti_descanso, fecha
                        FROM registros_sueno
                        WHERE paciente_id = ?
                        ORDER BY fecha DESC, id DESC LIMIT 1
                    """, (pid,))
                    r = cursor.fetchone()
                    if r:
                        desc_str = "Reparador" if r['senti_descanso'] == 1 else "No reparador"
                        horario = f"{r['hora_dormi'] or ''} - {r['hora_desperto'] or ''}".strip(' -')
                        metric_text = f"🌙 Último descanso: {horario or desc_str} ({desc_str})"
                
                elif clave == 'ansiedad':
                    cursor.execute("""
                        SELECT nivel_ansiedad, sintomas_json, fecha
                        FROM registros_ansiedad
                        WHERE paciente_id = ?
                        ORDER BY fecha DESC, id DESC LIMIT 1
                    """, (pid,))
                    r = cursor.fetchone()
                    if r:
                        import json
                        sintomas_count = 0
                        try:
                            sintomas_count = len(json.loads(r['sintomas_json'] or '[]'))
                        except Exception:
                            pass
                        metric_text = f"📊 Última Ansiedad: {r['nivel_ansiedad']}/10 | ⚠️ Síntomas: {sintomas_count}"
                
                elif clave == 'sobriedad':
                    cursor.execute("""
                        SELECT sobrio, nivel_ansiedad, fecha
                        FROM registros_sobriedad
                        WHERE paciente_id = ?
                        ORDER BY fecha DESC, id DESC LIMIT 1
                    """, (pid,))
                    r = cursor.fetchone()
                    if r:
                        estado = "Sobrio 🟢" if r['sobrio'] == 1 else "Recaída/Evento ⚠️"
                        craving = f" | 📈 Craving: {r['nivel_ansiedad']}/10" if r['nivel_ansiedad'] is not None else ""
                        metric_text = f"🏅 Estado: {estado}{craving}"
                
                elif clave == 'adherencia':
                    cursor.execute("""
                        SELECT ar.tomado, ar.fecha, am.nombre_medicamento
                        FROM adherencia_registros ar
                        JOIN adherencia_medicamentos am ON ar.medicamento_id = am.id
                        WHERE ar.paciente_id = ?
                        ORDER BY ar.fecha DESC, ar.id DESC LIMIT 1
                    """, (pid,))
                    r = cursor.fetchone()
                    if r:
                        tomado_str = "Tomado 🟢" if r['tomado'] == 1 else "Pendiente/No tomado 🔴"
                        metric_text = f"⏰ Última Toma: {r['nombre_medicamento']} - {tomado_str}"
                
                elif clave == 'activacion':
                    cursor.execute("""
                        SELECT COUNT(*) as total FROM activacion_actividades WHERE paciente_id = ? AND activa = 1
                    """, (pid,))
                    total_act = cursor.fetchone()['total']
                    cursor.execute("""
                        SELECT COUNT(*) as completadas FROM activacion_registros WHERE paciente_id = ? AND completada = 1
                    """, (pid,))
                    comp_act = cursor.fetchone()['completadas']
                    metric_text = f"✅ Actividades: {comp_act} completadas (Total activas: {total_act})"
                
                elif clave == 'ingesta':
                    cursor.execute("""
                        SELECT tipo_comida, apetito_previo, saciedad, fecha
                        FROM registros_ingesta
                        WHERE paciente_id = ?
                        ORDER BY fecha DESC, id DESC LIMIT 1
                    """, (pid,))
                    r = cursor.fetchone()
                    if r:
                        metric_text = f"🥗 Última Comida: {r['tipo_comida']} | Apetito: {r['apetito_previo'] or 0}/10 | Saciedad: {r['saciedad'] or 0}/10"

                elif clave == 'cognitivo':
                    cursor.execute("""
                        SELECT pensamiento, emocion_sensacion, intensidad_emocion, fecha
                        FROM registros_cognitivos
                        WHERE paciente_id = ?
                        ORDER BY fecha DESC, id DESC LIMIT 1
                    """, (pid,))
                    r = cursor.fetchone()
                    if r:
                        pens = (r['pensamiento'] or '')[:30]
                        metric_text = f"🧠 Último Registro: \"{pens}...\" | Emoción: {r['emocion_sensacion'] or 'N/A'} ({r['intensidad_emocion'] or 0}/10)"

                patients_list.append({
                    'patient_id': pid,
                    'nombre_paciente': p_name,
                    'cedula': p_cedula,
                    'metric_text': metric_text
                })
            
            catalog.append({
                'clave': clave,
                'nombre': mod['nombre'],
                'descripcion': mod['descripcion'],
                'icono': mod['icono'],
                'activos': len(patients_list),
                'pacientes': patients_list
            })
            
        except Exception as e:
            print(f"[WARN] Error loading accordion for module {clave}: {e}")
            catalog.append({
                'clave': clave,
                'nombre': mod['nombre'],
                'descripcion': mod['descripcion'],
                'icono': mod['icono'],
                'activos': 0,
                'pacientes': []
            })
            
    return jsonify(catalog)

@app.route('/api/therapist/modules/report/<string:modulo_clave>', methods=['GET'])
@login_required
def get_therapist_module_report(modulo_clave):
    user_id = session.get('user_id')
    db = get_db()
    cursor = db.cursor()
    
    if modulo_clave in ('consumo', 'sobriedad'):
        modulo_clave = 'sobriedad'
    elif modulo_clave in ('medicacion', 'adherencia'):
        modulo_clave = 'adherencia'

    try:
        if modulo_clave == 'sueno':
            cursor.execute("""
                SELECT rs.*, p.nombres, p.apellidos, p.cedula
                FROM registros_sueno rs
                JOIN pacientes p ON rs.paciente_id = p.id
                WHERE p.psicologo_id = ?
                ORDER BY rs.fecha DESC LIMIT 100
            """, (user_id,))
        elif modulo_clave == 'ansiedad':
            cursor.execute("""
                SELECT ra.*, p.nombres, p.apellidos, p.cedula
                FROM registros_ansiedad ra
                JOIN pacientes p ON ra.paciente_id = p.id
                WHERE p.psicologo_id = ?
                ORDER BY ra.fecha DESC LIMIT 100
            """, (user_id,))
        elif modulo_clave == 'sobriedad':
            cursor.execute("""
                SELECT rsob.*, p.nombres, p.apellidos, p.cedula
                FROM registros_sobriedad rsob
                JOIN pacientes p ON rsob.paciente_id = p.id
                WHERE p.psicologo_id = ?
                ORDER BY rsob.fecha DESC LIMIT 100
            """, (user_id,))
        elif modulo_clave == 'adherencia':
            cursor.execute("""
                SELECT ar.*, am.nombre_medicamento, am.dosis, am.hora_prescrita, p.nombres, p.apellidos, p.cedula
                FROM adherencia_registros ar
                JOIN adherencia_medicamentos am ON ar.medicamento_id = am.id
                JOIN pacientes p ON ar.paciente_id = p.id
                WHERE p.psicologo_id = ?
                ORDER BY ar.fecha DESC LIMIT 100
            """, (user_id,))
        elif modulo_clave == 'activacion':
            cursor.execute("""
                SELECT actr.*, aa.categoria, aa.nombre_actividad, p.nombres, p.apellidos, p.cedula
                FROM activacion_registros actr
                JOIN activacion_actividades aa ON actr.actividad_id = aa.id
                JOIN pacientes p ON actr.paciente_id = p.id
                WHERE p.psicologo_id = ?
                ORDER BY actr.fecha DESC LIMIT 100
            """, (user_id,))
        elif modulo_clave == 'ingesta':
            cursor.execute("""
                SELECT ring.*, p.nombres, p.apellidos, p.cedula
                FROM registros_ingesta ring
                JOIN pacientes p ON ring.paciente_id = p.id
                WHERE p.psicologo_id = ?
                ORDER BY ring.fecha DESC LIMIT 100
            """, (user_id,))
        elif modulo_clave == 'cognitivo':
            cursor.execute("""
                SELECT rcog.*, p.nombres, p.apellidos, p.cedula
                FROM registros_cognitivos rcog
                JOIN pacientes p ON rcog.paciente_id = p.id
                WHERE p.psicologo_id = ?
                ORDER BY rcog.fecha DESC LIMIT 100
            """, (user_id,))
        elif modulo_clave == 'pantalla':
            cursor.execute("""
                SELECT cp.*, p.nombres, p.apellidos, p.cedula
                FROM registro_consumo_pantalla cp
                JOIN pacientes p ON cp.paciente_id = p.id
                WHERE p.psicologo_id = ?
                ORDER BY cp.fecha_registro DESC LIMIT 100
            """, (user_id,))
        else:
            return jsonify({'error': 'Módulo desconocido'}), 400
        
        rows = [dict(r) for r in cursor.fetchall()]
        return jsonify(rows)
    except Exception as e:
        # Tables may not exist yet - return empty array gracefully
        print(f"[WARN] Error fetching report for {modulo_clave}: {e}")
        return jsonify([])

# --- ENDPOINTS ADHERENCIA AL TRATAMIENTO ---

@app.route('/api/patient/adherence/medications', methods=['GET', 'POST'])
@patient_login_required
def patient_adherence_medications():
    patient_id = session.get('patient_id')
    db = get_db()
    cursor = db.cursor()
    
    if request.method == 'POST':
        data = request.json or {}
        nombre_medicamento = (data.get('nombre_medicamento') or '').strip()
        dosis = (data.get('dosis') or '').strip()
        hora_prescrita = (data.get('hora_prescrita') or '').strip()
        
        if not nombre_medicamento:
            return jsonify({'error': 'El nombre del medicamento es obligatorio.'}), 400
            
        cursor.execute("""
            INSERT INTO adherencia_medicamentos (paciente_id, nombre_medicamento, dosis, hora_prescrita, activo)
            VALUES (?, ?, ?, ?, 1)
        """, (patient_id, nombre_medicamento, dosis, hora_prescrita))
        db.commit()
        med_id = cursor.lastrowid
        return jsonify({'success': True, 'medication': {'id': med_id, 'nombre_medicamento': nombre_medicamento, 'dosis': dosis, 'hora_prescrita': hora_prescrita, 'activo': 1}})
        
    cursor.execute("SELECT * FROM adherencia_medicamentos WHERE paciente_id = ? AND activo = 1 ORDER BY hora_prescrita ASC, id ASC", (patient_id,))
    rows = [dict(r) for r in cursor.fetchall()]
    return jsonify(rows)

@app.route('/api/patient/adherence/medications/<int:med_id>', methods=['DELETE'])
@patient_login_required
def delete_patient_adherence_medication(med_id):
    patient_id = session.get('patient_id')
    db = get_db()
    cursor = db.cursor()
    cursor.execute("UPDATE adherencia_medicamentos SET activo = 0 WHERE id = ? AND paciente_id = ?", (med_id, patient_id))
    db.commit()
    return jsonify({'success': True})

@app.route('/api/patient/adherence/log', methods=['POST'])
@patient_login_required
def log_patient_adherence():
    patient_id = session.get('patient_id')
    data = request.json or {}
    fecha = data.get('fecha') or datetime.now().strftime('%Y-%m-%d')
    registros = data.get('registros', [])
    
    db = get_db()
    cursor = db.cursor()
    
    for item in registros:
        med_id = item.get('medicamento_id')
        tomado = 1 if item.get('tomado') else 0
        hora_tomado = item.get('hora_tomado', '')
        notas = item.get('notas', '')
        
        if not med_id:
            continue
            
        cursor.execute("""
            INSERT INTO adherencia_registros (paciente_id, medicamento_id, fecha, tomado, hora_tomado, notas)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(paciente_id, medicamento_id, fecha) DO UPDATE SET
                tomado = excluded.tomado,
                hora_tomado = excluded.hora_tomado,
                notas = excluded.notas
        """, (patient_id, med_id, fecha, tomado, hora_tomado, notas))
    db.commit()
    
    try:
        cursor.execute("SELECT nombres, apellidos, psicologo_id FROM pacientes WHERE id = ?", (patient_id,))
        pac = cursor.fetchone()
        if pac:
            pac_nombre = f"{pac['nombres']} {pac['apellidos']}".strip()
            psic_id = pac['psicologo_id'] or 1
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            notif_title = "💊 Adherencia al Tratamiento Registrada"
            notif_msg = f"El consultante {pac_nombre} registró la toma de medicamentos para la fecha {fecha}."
            cursor.execute("""
                INSERT INTO notificaciones (user_id, tipo, titulo, mensaje, fecha, leida, link)
                VALUES (?, 'herramienta_terapeutica', ?, ?, ?, 0, '/#therapist-tools')
            """, (psic_id, notif_title, notif_msg, now_str))
            db.commit()
            try:
                send_webpush_notification(user_id=psic_id, title=notif_title, body=notif_msg, url="/#therapist-tools")
            except Exception:
                pass
    except Exception as _e:
        print("Error notif adherencia:", _e)
        
    return jsonify({'success': True, 'message': 'Registro de adherencia a medicación guardado.'})

@app.route('/api/patient/adherence/history', methods=['GET'])
@patient_login_required
def get_patient_adherence_history():
    patient_id = session.get('patient_id')
    fecha_req = request.args.get('fecha')
    db = get_db()
    cursor = db.cursor()
    
    if fecha_req:
        cursor.execute("""
            SELECT ar.*, am.nombre_medicamento, am.dosis, am.hora_prescrita
            FROM adherencia_registros ar
            JOIN adherencia_medicamentos am ON ar.medicamento_id = am.id
            WHERE ar.paciente_id = ? AND ar.fecha = ?
        """, (patient_id, fecha_req))
    else:
        cursor.execute("""
            SELECT ar.*, am.nombre_medicamento, am.dosis, am.hora_prescrita
            FROM adherencia_registros ar
            JOIN adherencia_medicamentos am ON ar.medicamento_id = am.id
            WHERE ar.paciente_id = ?
            ORDER BY ar.fecha DESC, am.hora_prescrita ASC LIMIT 100
        """, (patient_id,))
    rows = [dict(r) for r in cursor.fetchall()]
    return jsonify(rows)

# --- ENDPOINTS ACTIVACIÓN CONDUCTUAL ---

@app.route('/api/patient/activation/activities', methods=['GET'])
@patient_login_required
def patient_activation_activities():
    patient_id = session.get('patient_id')
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM activacion_actividades WHERE paciente_id = ? AND activa = 1 ORDER BY categoria ASC, id ASC", (patient_id,))
    rows = [dict(r) for r in cursor.fetchall()]
    return jsonify(rows)

@app.route('/api/therapist/patients/<int:patient_id>/activation/activities', methods=['GET', 'POST'])
@login_required
def therapist_patient_activation_activities(patient_id):
    user_id = session.get('user_id')
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute("SELECT id FROM pacientes WHERE id = ? AND psicologo_id = ?", (patient_id, user_id))
    if not cursor.fetchone():
        return jsonify({'error': 'Paciente no encontrado o sin permisos.'}), 404
        
    if request.method == 'POST':
        data = request.json or {}
        categoria = data.get('categoria', 'necesaria')
        nombre_actividad = (data.get('nombre_actividad') or '').strip()
        activa = 1 if data.get('activa', True) else 0
        
        if not nombre_actividad:
            return jsonify({'error': 'Nombre de actividad es requerido.'}), 400
            
        cursor.execute("""
            INSERT INTO activacion_actividades (paciente_id, psicologo_id, categoria, nombre_actividad, activa)
            VALUES (?, ?, ?, ?, ?)
        """, (patient_id, user_id, categoria, nombre_actividad, activa))
        db.commit()
        act_id = cursor.lastrowid
        return jsonify({'success': True, 'activity': {'id': act_id, 'categoria': categoria, 'nombre_actividad': nombre_actividad, 'activa': activa}})
        
    cursor.execute("SELECT * FROM activacion_actividades WHERE paciente_id = ? ORDER BY categoria ASC, id ASC", (patient_id,))
    rows = [dict(r) for r in cursor.fetchall()]
    return jsonify(rows)

@app.route('/api/therapist/activation/activities/<int:act_id>/toggle', methods=['POST'])
@login_required
def toggle_activation_activity(act_id):
    data = request.json or {}
    activa = 1 if data.get('activa') else 0
    db = get_db()
    cursor = db.cursor()
    cursor.execute("UPDATE activacion_actividades SET activa = ? WHERE id = ?", (activa, act_id))
    db.commit()
    return jsonify({'success': True, 'activa': activa})

@app.route('/api/patient/activation/log', methods=['POST'])
@patient_login_required
def log_patient_activation():
    patient_id = session.get('patient_id')
    data = request.json or {}
    fecha = data.get('fecha') or datetime.now().strftime('%Y-%m-%d')
    registros = data.get('registros', [])
    
    db = get_db()
    cursor = db.cursor()
    
    for item in registros:
        act_id = item.get('actividad_id')
        completada = 1 if item.get('completada') else 0
        notas = item.get('notas', '')
        
        if not act_id:
            continue
            
        cursor.execute("""
            INSERT INTO activacion_registros (paciente_id, actividad_id, fecha, completada, notas)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(paciente_id, actividad_id, fecha) DO UPDATE SET
                completada = excluded.completada,
                notas = excluded.notas
        """, (patient_id, act_id, fecha, completada, notas))
    db.commit()
    
    try:
        cursor.execute("SELECT nombres, apellidos, psicologo_id FROM pacientes WHERE id = ?", (patient_id,))
        pac = cursor.fetchone()
        if pac:
            pac_nombre = f"{pac['nombres']} {pac['apellidos']}".strip()
            psic_id = pac['psicologo_id'] or 1
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            notif_title = "🏃‍♂️ Activación Conductual Registrada"
            notif_msg = f"El consultante {pac_nombre} completó su checklist diario de activación conductual para el {fecha}."
            cursor.execute("""
                INSERT INTO notificaciones (user_id, tipo, titulo, mensaje, fecha, leida, link)
                VALUES (?, 'herramienta_terapeutica', ?, ?, ?, 0, '/#therapist-tools')
            """, (psic_id, notif_title, notif_msg, now_str))
            db.commit()
            try:
                send_webpush_notification(user_id=psic_id, title=notif_title, body=notif_msg, url="/#therapist-tools")
            except Exception:
                pass
    except Exception as _e:
        print("Error notif activacion:", _e)
        
    return jsonify({'success': True, 'message': 'Registro de activación conductual guardado.'})

@app.route('/api/patient/activation/history', methods=['GET'])
@patient_login_required
def get_patient_activation_history():
    patient_id = session.get('patient_id')
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT ar.*, aa.categoria, aa.nombre_actividad
        FROM activacion_registros ar
        JOIN activacion_actividades aa ON ar.actividad_id = aa.id
        WHERE ar.paciente_id = ?
        ORDER BY ar.fecha DESC, aa.categoria ASC
    """, (patient_id,))
    rows = [dict(r) for r in cursor.fetchall()]
    return jsonify(rows)

# --- RUTAS PORTAL DEL PACIENTE ---

@app.route('/api/patient/active-modules', methods=['GET'])
@patient_login_required
def get_patient_active_modules():
    patient_id = session.get('patient_id')
    if not patient_id:
        return jsonify({'error': 'No autenticado'}), 401
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT modulo_clave FROM modulos_terapeuticos_paciente WHERE paciente_id = ? AND activo = 1", (patient_id,))
    active_keys = [r['modulo_clave'] for r in cursor.fetchall()]
    return jsonify({'active_modules': active_keys})

@app.route('/api/patient/sleep/log', methods=['POST'])
@patient_login_required
def log_patient_sleep():
    patient_id = session.get('patient_id')
    data = request.json or {}
    fecha = data.get('fecha') or datetime.now().strftime('%Y-%m-%d')
    
    situaciones_dia = data.get('situaciones_dia', '')
    emociones_dia = data.get('emociones_dia', '')
    proceso_dormir = data.get('proceso_dormir', '')
    hora_dormi = data.get('hora_dormi', '')
    desperto_noche = 1 if data.get('desperto_noche') else 0
    cant_despertares = int(data.get('cant_despertares', 0) or 0)
    hora_desperto = data.get('hora_desperto', '')
    senti_descanso = 1 if data.get('senti_descanso') else 0
    somnolencia_dia = 1 if data.get('somnolencia_dia') else 0
    pesadez_dia = 1 if data.get('pesadez_dia') else 0
    agotamiento_dia = 1 if data.get('agotamiento_dia') else 0
    
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        INSERT INTO registros_sueno (
            paciente_id, fecha, situaciones_dia, emociones_dia, proceso_dormir,
            hora_dormi, desperto_noche, cant_despertares, hora_desperto,
            senti_descanso, somnolencia_dia, pesadez_dia, agotamiento_dia
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(paciente_id, fecha) DO UPDATE SET
            situaciones_dia=excluded.situaciones_dia,
            emociones_dia=excluded.emociones_dia,
            proceso_dormir=excluded.proceso_dormir,
            hora_dormi=excluded.hora_dormi,
            desperto_noche=excluded.desperto_noche,
            cant_despertares=excluded.cant_despertares,
            hora_desperto=excluded.hora_desperto,
            senti_descanso=excluded.senti_descanso,
            somnolencia_dia=excluded.somnolencia_dia,
            pesadez_dia=excluded.pesadez_dia,
            agotamiento_dia=excluded.agotamiento_dia
    """, (
        patient_id, fecha, situaciones_dia, emociones_dia, proceso_dormir,
        hora_dormi, desperto_noche, cant_despertares, hora_desperto,
        senti_descanso, somnolencia_dia, pesadez_dia, agotamiento_dia
    ))
    db.commit()

    # Notificar al psicólogo asignado
    try:
        cursor.execute("SELECT nombres, apellidos, psicologo_id FROM pacientes WHERE id = ?", (patient_id,))
        pac = cursor.fetchone()
        if pac:
            pac_nombre = f"{pac['nombres']} {pac['apellidos']}".strip()
            psic_id = pac['psicologo_id'] or 1
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            notif_title = "🌙 Registro de Higiene del Sueño"
            notif_msg = f"El consultante {pac_nombre} completó su registro diario de higiene del sueño para el {fecha}."
            cursor.execute("""
                INSERT INTO notificaciones (user_id, tipo, titulo, mensaje, fecha, leida, link)
                VALUES (?, 'herramienta_terapeutica', ?, ?, ?, 0, '/#therapist-tools')
            """, (psic_id, notif_title, notif_msg, now_str))
            db.commit()
            try:
                send_webpush_notification(user_id=psic_id, title=notif_title, body=notif_msg, url="/#therapist-tools")
            except Exception:
                pass
    except Exception as _ne:
        print("Error al notificar registro de sueño:", _ne)

    return jsonify({'success': True, 'message': 'Registro de sueño guardado exitosamente.'})

@app.route('/api/patient/sleep/history', methods=['GET'])
@patient_login_required
def get_patient_sleep_history():
    patient_id = session.get('patient_id')
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM registros_sueno WHERE paciente_id = ? ORDER BY fecha DESC LIMIT 30", (patient_id,))
    rows = [dict(r) for r in cursor.fetchall()]
    return jsonify(rows)

@app.route('/api/patient/anxiety/log', methods=['POST'])
@patient_login_required
def log_patient_anxiety():
    patient_id = session.get('patient_id')
    data = request.json or {}
    fecha = data.get('fecha') or datetime.now().strftime('%Y-%m-%d')
    nivel_ansiedad = int(data.get('nivel_ansiedad', 1) or 1)
    sintomas = data.get('sintomas', [])
    situacion = data.get('situacion_desencadenante', '')
    
    import json
    sintomas_json = json.dumps(sintomas)
    
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        INSERT INTO registros_ansiedad (paciente_id, fecha, nivel_ansiedad, sintomas_json, situacion_desencadenante)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(paciente_id, fecha) DO UPDATE SET
            nivel_ansiedad=excluded.nivel_ansiedad,
            sintomas_json=excluded.sintomas_json,
            situacion_desencadenante=excluded.situacion_desencadenante
    """, (patient_id, fecha, nivel_ansiedad, sintomas_json, situacion))
    db.commit()

    # Notificar al psicólogo asignado
    try:
        cursor.execute("SELECT nombres, apellidos, psicologo_id FROM pacientes WHERE id = ?", (patient_id,))
        pac = cursor.fetchone()
        if pac:
            pac_nombre = f"{pac['nombres']} {pac['apellidos']}".strip()
            psic_id = pac['psicologo_id'] or 1
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            notif_title = "⚡ Diario de Ansiedad Actualizado"
            notif_msg = f"El consultante {pac_nombre} registró su nivel de ansiedad ({nivel_ansiedad}/10) para el {fecha}."
            cursor.execute("""
                INSERT INTO notificaciones (user_id, tipo, titulo, mensaje, fecha, leida, link)
                VALUES (?, 'herramienta_terapeutica', ?, ?, ?, 0, '/#therapist-tools')
            """, (psic_id, notif_title, notif_msg, now_str))
            db.commit()
            try:
                send_webpush_notification(user_id=psic_id, title=notif_title, body=notif_msg, url="/#therapist-tools")
            except Exception:
                pass
    except Exception as _ne:
        print("Error al notificar registro de ansiedad:", _ne)

    return jsonify({'success': True, 'message': 'Registro de ansiedad guardado exitosamente.'})

@app.route('/api/patient/anxiety/history', methods=['GET'])
@patient_login_required
def get_patient_anxiety_history():
    patient_id = session.get('patient_id')
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM registros_ansiedad WHERE paciente_id = ? ORDER BY fecha DESC LIMIT 30", (patient_id,))
    rows = [dict(r) for r in cursor.fetchall()]
    return jsonify(rows)

@app.route('/api/patient/sobriety/checkin', methods=['POST'])
@patient_login_required
def log_patient_sobriety():
    patient_id = session.get('patient_id')
    data = request.json or {}
    fecha = data.get('fecha') or datetime.now().strftime('%Y-%m-%d')
    sobrio = 1 if data.get('sobrio') else 0
    nivel_ansiedad = int(data.get('nivel_ansiedad', 1) or 1)
    disparador = data.get('disparador_emocional', '')
    notas = data.get('notas', '')
    
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        INSERT INTO registros_sobriedad (paciente_id, fecha, sobrio, nivel_ansiedad, disparador_emocional, notas)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(paciente_id, fecha) DO UPDATE SET
            sobrio=excluded.sobrio,
            nivel_ansiedad=excluded.nivel_ansiedad,
            disparador_emocional=excluded.disparador_emocional,
            notas=excluded.notas
    """, (patient_id, fecha, sobrio, nivel_ansiedad, disparador, notas))
    db.commit()
    
    cursor.execute("SELECT fecha, sobrio FROM registros_sobriedad WHERE paciente_id = ? ORDER BY fecha DESC", (patient_id,))
    all_logs = cursor.fetchall()
    streak = 0
    for l in all_logs:
        if l['sobrio'] == 1:
            streak += 1
        else:
            break

    # Notificar al psicólogo asignado
    try:
        cursor.execute("SELECT nombres, apellidos, psicologo_id FROM pacientes WHERE id = ?", (patient_id,))
        pac = cursor.fetchone()
        if pac:
            pac_nombre = f"{pac['nombres']} {pac['apellidos']}".strip()
            psic_id = pac['psicologo_id'] or 1
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            status_text = f"Sobrio (Racha: {streak} días)" if sobrio == 1 else "Reporte de recaída / consumo"
            notif_title = "🏅 Tracker de Consumo / Sobriedad"
            notif_msg = f"El consultante {pac_nombre} realizó su check-in: {status_text}."
            cursor.execute("""
                INSERT INTO notificaciones (user_id, tipo, titulo, mensaje, fecha, leida, link)
                VALUES (?, 'herramienta_terapeutica', ?, ?, ?, 0, '/#therapist-tools')
            """, (psic_id, notif_title, notif_msg, now_str))
            db.commit()
            try:
                send_webpush_notification(user_id=psic_id, title=notif_title, body=notif_msg, url="/#therapist-tools")
            except Exception:
                pass
    except Exception as _ne:
        print("Error al notificar registro de sobriedad:", _ne)

    return jsonify({'success': True, 'sobrio': sobrio, 'streak': streak, 'message': 'Check-in de sobriedad guardado.'})

@app.route('/api/patient/sobriety/history', methods=['GET'])
@patient_login_required
def get_patient_sobriety_history():
    patient_id = session.get('patient_id')
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM registros_sobriedad WHERE paciente_id = ? ORDER BY fecha DESC", (patient_id,))
    all_logs = [dict(r) for r in cursor.fetchall()]
    
    streak = 0
    for l in all_logs:
        if l['sobrio'] == 1:
            streak += 1
        else:
            break
            
    return jsonify({'history': all_logs, 'streak': streak})


# --- ENDPOINTS INGESTA DE ALIMENTOS Y APETITO ---

@app.route('/api/patient/food-intake/log', methods=['POST'])
@patient_login_required
def log_patient_food_intake():
    patient_id = session.get('patient_id')
    data = request.json or {}
    fecha = (data.get('fecha') or '').strip() or datetime.now().strftime('%Y-%m-%d %H:%M')
    tipo_comida = (data.get('tipo_comida') or 'Almuerzo').strip()
    descripcion_plato = (data.get('descripcion_plato') or '').strip()
    apetito_previo = int(data.get('apetito_previo', 5))
    saciedad = int(data.get('saciedad', 5))
    contexto = (data.get('contexto') or '').strip()
    afectividad = (data.get('afectividad') or '').strip()
    pensamiento = (data.get('pensamiento') or '').strip()
    import json
    conductas_json = json.dumps(data.get('conductas', []), ensure_ascii=False)

    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        INSERT INTO registros_ingesta (
            paciente_id, fecha, tipo_comida, descripcion_plato,
            apetito_previo, saciedad, contexto, afectividad, pensamiento, conductas_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (patient_id, fecha, tipo_comida, descripcion_plato, apetito_previo, saciedad, contexto, afectividad, pensamiento, conductas_json))
    db.commit()

    # Notificar al psicólogo
    try:
        cursor.execute("SELECT nombres, apellidos, psicologo_id FROM pacientes WHERE id = ?", (patient_id,))
        pac = cursor.fetchone()
        if pac:
            pac_nombre = f"{pac['nombres']} {pac['apellidos']}".strip()
            psic_id = pac['psicologo_id'] or 1
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            notif_title = "🥗 Registro de Ingesta y Apetito"
            notif_msg = f"El consultante {pac_nombre} registró una ingesta ({tipo_comida}) para el {fecha}."
            cursor.execute("""
                INSERT INTO notificaciones (user_id, tipo, titulo, mensaje, fecha, leida, link)
                VALUES (?, 'herramienta_terapeutica', ?, ?, ?, 0, '/#therapist-tools')
            """, (psic_id, notif_title, notif_msg, now_str))
            db.commit()
            try:
                send_webpush_notification(user_id=psic_id, title=notif_title, body=notif_msg, url="/#therapist-tools")
            except Exception:
                pass
    except Exception as _ne:
        print("Error al notificar registro de ingesta:", _ne)

    return jsonify({'success': True, 'message': 'Registro de ingesta guardado exitosamente.'})

@app.route('/api/patient/food-intake/history', methods=['GET'])
@patient_login_required
def get_patient_food_intake_history():
    patient_id = session.get('patient_id')
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM registros_ingesta WHERE paciente_id = ? ORDER BY fecha DESC LIMIT 50", (patient_id,))
    rows = [dict(r) for r in cursor.fetchall()]
    return jsonify(rows)


# --- ENDPOINTS REGISTRO COGNITIVO ---

@app.route('/api/patient/cognitive-record/log', methods=['POST'])
@patient_login_required
def log_patient_cognitive_record():
    patient_id = session.get('patient_id')
    data = request.json or {}
    fecha = (data.get('fecha') or '').strip() or datetime.now().strftime('%Y-%m-%d %H:%M')
    situacion = (data.get('situacion') or '').strip()
    pensamiento = (data.get('pensamiento') or '').strip()
    emocion_sensacion = (data.get('emocion_sensacion') or '').strip()
    intensidad_emocion = int(data.get('intensidad_emocion', 5))
    conducta = (data.get('conducta') or '').strip()

    if not situacion or not pensamiento:
        return jsonify({'error': 'La situación y el pensamiento son requeridos.'}), 400

    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        INSERT INTO registros_cognitivos (
            paciente_id, fecha, situacion, pensamiento, emocion_sensacion, intensidad_emocion, conducta
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (patient_id, fecha, situacion, pensamiento, emocion_sensacion, intensidad_emocion, conducta))
    db.commit()

    # Notificar al psicólogo
    try:
        cursor.execute("SELECT nombres, apellidos, psicologo_id FROM pacientes WHERE id = ?", (patient_id,))
        pac = cursor.fetchone()
        if pac:
            pac_nombre = f"{pac['nombres']} {pac['apellidos']}".strip()
            psic_id = pac['psicologo_id'] or 1
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            notif_title = "🧠 Registro Cognitivo (TCC)"
            notif_msg = f"El consultante {pac_nombre} completó un nuevo registro cognitivo para el {fecha}."
            cursor.execute("""
                INSERT INTO notificaciones (user_id, tipo, titulo, mensaje, fecha, leida, link)
                VALUES (?, 'herramienta_terapeutica', ?, ?, ?, 0, '/#therapist-tools')
            """, (psic_id, notif_title, notif_msg, now_str))
            db.commit()
            try:
                send_webpush_notification(user_id=psic_id, title=notif_title, body=notif_msg, url="/#therapist-tools")
            except Exception:
                pass
    except Exception as _ne:
        print("Error al notificar registro cognitivo:", _ne)

    return jsonify({'success': True, 'message': 'Registro cognitivo guardado exitosamente.'})

@app.route('/api/patient/cognitive-record/history', methods=['GET'])
@patient_login_required
def get_patient_cognitive_record_history():
    patient_id = session.get('patient_id')
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM registros_cognitivos WHERE paciente_id = ? ORDER BY fecha DESC LIMIT 50", (patient_id,))
    rows = [dict(r) for r in cursor.fetchall()]
    return jsonify(rows)


# --- ENDPOINTS CONSUMO DE PANTALLA ---

@app.route('/api/patient/screen-time/log', methods=['POST'])
@patient_login_required
def log_patient_screen_time():
    patient_id = session.get('patient_id')
    data = request.json or {}
    dispositivos = (data.get('dispositivos') or '').strip()
    tiempo_uso = (data.get('tiempo_uso') or '').strip()
    aplicaciones = (data.get('aplicaciones') or '').strip()
    tipo_contenido = (data.get('tipo_contenido') or '').strip()
    estado_emocional = (data.get('estado_emocional_posterior') or '').strip()
    interferencia = (data.get('interferencia_actividad') or '').strip()

    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        INSERT INTO registro_consumo_pantalla (
            paciente_id, dispositivos, tiempo_uso, aplicaciones, tipo_contenido,
            estado_emocional_posterior, interferencia_actividad
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (patient_id, dispositivos, tiempo_uso, aplicaciones, tipo_contenido, estado_emocional, interferencia))
    db.commit()

    # Notificar al psicólogo asignado
    try:
        cursor.execute("SELECT nombres, apellidos, psicologo_id FROM pacientes WHERE id = ?", (patient_id,))
        pac = cursor.fetchone()
        if pac:
            pac_nombre = f"{pac['nombres']} {pac['apellidos']}".strip()
            psic_id = pac['psicologo_id'] or 1
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            notif_title = "📱 Tracker de Consumo de Pantalla"
            notif_msg = f"El consultante {pac_nombre} registró su monitoreo diario de uso de pantalla."
            cursor.execute("""
                INSERT INTO notificaciones (user_id, tipo, titulo, mensaje, fecha, leida, link)
                VALUES (?, 'herramienta_terapeutica', ?, ?, ?, 0, '/#therapist-tools')
            """, (psic_id, notif_title, notif_msg, now_str))
            db.commit()
            try:
                send_webpush_notification(user_id=psic_id, title=notif_title, body=notif_msg, url="/#therapist-tools")
            except Exception:
                pass
    except Exception as _ne:
        print("Error al notificar registro de pantalla:", _ne)

    return jsonify({'success': True, 'message': 'Registro de tiempo de pantalla guardado exitosamente.'})

@app.route('/api/patient/screen-time/history', methods=['GET'])
@patient_login_required
def get_patient_screen_time_history():
    patient_id = session.get('patient_id')
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM registro_consumo_pantalla WHERE paciente_id = ? ORDER BY fecha_registro DESC LIMIT 50", (patient_id,))
    rows = [dict(r) for r in cursor.fetchall()]
    return jsonify(rows)


# =========================================================================
# RUTAS DE BACKEND: EXAMEN MENTAL ESTRUCTURADO (MSE) & EXPORTACIÓN
# =========================================================================

def _ensure_examenes_mentales_table(cursor):
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS examenes_mentales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                psicologo_id INTEGER NOT NULL,
                paciente_id INTEGER NOT NULL,
                fecha_evaluacion TEXT NOT NULL,
                medio_evaluacion TEXT NOT NULL,
                datos_evaluacion_json TEXT NOT NULL,
                observaciones_generales TEXT,
                fecha_registro DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (psicologo_id) REFERENCES usuarios(id) ON DELETE CASCADE,
                FOREIGN KEY (paciente_id) REFERENCES pacientes(id) ON DELETE CASCADE
            )
        """)
    except Exception as _e:
        print("Error en _ensure_examenes_mentales_table:", _e)


@app.route('/api/examen-mental', methods=['POST'])
@login_required
def save_examen_mental():
    user_id = session.get('user_id')
    db = get_db()
    cursor = db.cursor()
    
    if session.get('role') != 'superadmin':
        cursor.execute("SELECT COALESCE(bloqueo_examen_mental, 1) FROM usuarios WHERE id = ?", (user_id,))
        b_row = cursor.fetchone()
        if b_row and b_row[0] == 1:
            return jsonify({'error': 'La función de Examen Mental está inhabilitada para tu cuenta. Contacta a administración.'}), 403
    _ensure_examenes_mentales_table(cursor)
    
    data = request.json or {}
    paciente_id = data.get('paciente_id')
    fecha_evaluacion = data.get('fecha_evaluacion')
    medio_evaluacion = data.get('medio_evaluacion', 'Presencial')
    datos_evaluacion = data.get('datos_evaluacion_json', {})
    observaciones_generales = data.get('observaciones_generales', '').strip()
    
    if not paciente_id or not fecha_evaluacion:
        return jsonify({'error': 'El paciente y la fecha de evaluación son requeridos.'}), 400
        
    try:
        import json
        datos_json_str = json.dumps(datos_evaluacion, ensure_ascii=False)
        
        cursor.execute("""
            INSERT INTO examenes_mentales (psicologo_id, paciente_id, fecha_evaluacion, medio_evaluacion, datos_evaluacion_json, observaciones_generales)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, paciente_id, fecha_evaluacion, medio_evaluacion, datos_json_str, observaciones_generales))
        
        exam_id = cursor.lastrowid
        db.commit()
        
        return jsonify({'success': 'Examen mental guardado con éxito e integrado a la historia clínica.', 'id': exam_id})
    except Exception as e:
        db.rollback()
        return jsonify({'error': f'Error al guardar el examen mental: {str(e)}'}), 500


@app.route('/api/examen-mental/historial', methods=['GET'])
@login_required
def get_examen_mental_historial():
    user_id = session.get('user_id')
    search = request.args.get('search', '').strip()
    paciente_id_param = request.args.get('paciente_id')
    
    db = get_db()
    cursor = db.cursor()
    _ensure_examenes_mentales_table(cursor)
    
    query = """
        SELECT e.id, e.psicologo_id, e.paciente_id, e.fecha_evaluacion, e.medio_evaluacion,
               e.datos_evaluacion_json, e.observaciones_generales, e.fecha_registro,
               p.nombres as pac_nombres, p.apellidos as pac_apellidos, p.cedula as pac_cedula,
               p.genero as pac_genero, p.fecha_nacimiento as pac_fecha_nacimiento
        FROM examenes_mentales e
        JOIN pacientes p ON e.paciente_id = p.id
        WHERE e.psicologo_id = ?
    """
    params = [user_id]
    
    if paciente_id_param:
        query += " AND e.paciente_id = ?"
        params.append(paciente_id_param)
        
    if search:
        query += " AND (p.nombres LIKE ? OR p.apellidos LIKE ? OR p.cedula LIKE ?)"
        s_term = f"%{search}%"
        params.extend([s_term, s_term, s_term])
        
    query += " ORDER BY e.fecha_registro DESC, e.id DESC"
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    
    result = []
    import json
    for r in rows:
        r_dict = dict(r)
        try:
            r_dict['datos_evaluacion'] = json.loads(r_dict['datos_evaluacion_json']) if r_dict['datos_evaluacion_json'] else {}
        except:
            r_dict['datos_evaluacion'] = {}
        result.append(r_dict)
        
    return jsonify(result)


@app.route('/api/examen-mental/<int:exam_id>', methods=['GET'])
@login_required
def get_examen_mental_detail(exam_id):
    user_id = session.get('user_id')
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute("""
        SELECT e.*, p.nombres as pac_nombres, p.apellidos as pac_apellidos, p.cedula as pac_cedula,
               p.genero as pac_genero, p.fecha_nacimiento as pac_fecha_nacimiento, p.email as pac_email
        FROM examenes_mentales e
        JOIN pacientes p ON e.paciente_id = p.id
        WHERE e.id = ? AND e.psicologo_id = ?
    """, (exam_id, user_id))
    
    r = cursor.fetchone()
    if not r:
        return jsonify({'error': 'Examen mental no encontrado.'}), 404
        
    r_dict = dict(r)
    import json
    try:
        r_dict['datos_evaluacion'] = json.loads(r_dict['datos_evaluacion_json']) if r_dict['datos_evaluacion_json'] else {}
    except:
        r_dict['datos_evaluacion'] = {}
        
    return jsonify(r_dict)


def _calculate_age_str(fecha_nac):
    if not fecha_nac:
        return "N/E"
    try:
        from datetime import datetime
        born = datetime.strptime(str(fecha_nac).strip(), "%Y-%m-%d")
        today = datetime.today()
        age = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
        return f"{age}"
    except:
        return "N/E"


def _build_mse_narrative(datos_eval, pac_genero="no especificado", pac_edad="N/E", modalidad="Presencial"):
    def get_val(key, default_str=""):
        val_obj = datos_eval.get(key, {})
        if isinstance(val_obj, dict):
            selecciones = val_obj.get('selecciones', [])
            obs = val_obj.get('observacion', '').strip()
            res = []
            if selecciones:
                res.append(", ".join(selecciones))
            if obs:
                res.append(f"({obs})")
            return " ".join(res).strip() if res else default_str
        elif isinstance(val_obj, str) and val_obj.strip():
            return val_obj.strip()
        return default_str

    genero_str = (pac_genero or "no especificado").lower()
    edad_str = str(pac_edad or "N/E")
    modalidad_str = (modalidad or "Presencial").lower()

    apariencia = get_val('apariencia', 'adecuada y aliñada')
    actitud = get_val('actitud', 'colaboradora y receptiva')
    conciencia = get_val('conciencia', 'vigil y alerta')
    orientacion = get_val('orientacion', 'orientado autopsíquica y alopsíquicamente')
    memoria = get_val('memoria', 'conservada sin alteraciones')
    atencion = get_val('atencion', 'euproséxica (conservada)')
    lenguaje = get_val('lenguaje', 'normofluido y coherente')
    pensamiento = get_val('pensamiento', 'curso normopsíquico y contenido coherente')
    afecto = get_val('afecto', 'eutímico')
    percepcion = get_val('percepcion', 'sin alteraciones perceptivas')
    juicio = get_val('juicio', 'juicio de realidad conservado')
    introspeccion = get_val('introspeccion', 'adecuada (conciencia de malestar/enfermedad)')

    text = (
        f"Paciente de género {genero_str}, de {edad_str} años de edad, asiste a consulta en modalidad {modalidad_str} "
        f"con una apariencia y porte {apariencia}, mostrando una actitud {actitud} hacia el evaluador. "
        f"Se encuentra en nivel de conciencia {conciencia}, {orientacion}. "
        f"En el área de memoria {memoria}, atención y concentración {atencion}. "
        f"Presenta un lenguaje {lenguaje}, con pensamiento de {pensamiento}. "
        f"En el estado de ánimo y afecto {afecto}, percepción {percepcion}. "
        f"Mantiene un juicio de realidad {juicio} e introspección {introspeccion}."
    )
    return text


@app.route('/api/examen-mental/<int:exam_id>/export/pdf', methods=['GET'])
@login_required
def export_examen_mental_pdf(exam_id):
    user_id = session.get('user_id')
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute("SELECT * FROM usuarios WHERE id = ?", (user_id,))
    psic = cursor.fetchone()
    if not psic:
        return "Error: Usuario no encontrado", 404
        
    cursor.execute("""
        SELECT e.*, p.nombres as pac_nombres, p.apellidos as pac_apellidos, p.cedula as pac_cedula,
               p.genero as pac_genero, p.fecha_nacimiento as pac_fecha_nacimiento
        FROM examenes_mentales e
        JOIN pacientes p ON e.paciente_id = p.id
        WHERE e.id = ? AND e.psicologo_id = ?
    """, (exam_id, user_id))
    
    exam = cursor.fetchone()
    if not exam:
        return "Error: Examen mental no encontrado", 404
        
    import json
    datos_eval = {}
    try:
        datos_eval = json.loads(exam['datos_evaluacion_json']) if exam['datos_evaluacion_json'] else {}
    except:
        pass
        
    psic_nombre = f"Psic. {psic['nombres'] or ''} {psic['apellidos'] or ''}".strip()
    psic_titulo = psic['nomenclatura'] or psic['estudios'] or "Psicólogo Clínico"
    psic_fed = psic['federacion'] or "N/R"
    
    pac_nombre = f"{exam['pac_nombres'] or ''} {exam['pac_apellidos'] or ''}".strip()
    pac_cedula = exam['pac_cedula'] or "N/A"
    pac_genero = exam['pac_genero'] or "No especificado"
    pac_edad = _calculate_age_str(exam['pac_fecha_nacimiento'])
    
    # Formatear la fecha
    try:
        f_parts = exam['fecha_evaluacion'].split('-')
        fecha_fmt = f"{f_parts[2]}/{f_parts[1]}/{f_parts[0]}"
    except:
        fecha_fmt = exam['fecha_evaluacion']

    narrative_text = _build_mse_narrative(datos_eval, pac_genero=pac_genero, pac_edad=pac_edad, modalidad=exam['medio_evaluacion'])

    area_titles = {
        "apariencia": "Apariencia y Porte",
        "actitud": "Actitud hacia el Evaluador",
        "conciencia": "Nivel de Conciencia",
        "orientacion": "Orientación",
        "memoria": "Memoria",
        "atencion": "Atención y Concentración",
        "lenguaje": "Lenguaje y Comunicación",
        "pensamiento": "Pensamiento (Curso y Contenido)",
        "afecto": "Afecto y Estado de Ánimo",
        "percepcion": "Percepción",
        "juicio": "Juicio de Realidad",
        "introspeccion": "Introspección (Insight)"
    }
    
    area_rows_html = ""
    for area_key, area_name in area_titles.items():
        val_obj = datos_eval.get(area_key, {})
        selecciones = val_obj.get('selecciones', [])
        observacion = val_obj.get('observacion', '').strip()
        
        txt_parts = []
        if selecciones:
            txt_parts.append(", ".join(selecciones))
        if observacion:
            txt_parts.append(f"<em>Obs:</em> {observacion}")
            
        final_txt = " — ".join(txt_parts) if txt_parts else "Sin hallazgos significativos reportados."
        
        area_rows_html += f"""
        <tr>
            <td style="padding: 8px 12px; font-weight: 700; color: #3D1E3F; border-bottom: 1px solid #e2e8f0; width: 32%; background: #faf5f9;">{area_name}</td>
            <td style="padding: 8px 12px; color: #334155; border-bottom: 1px solid #e2e8f0; line-height: 1.5;">{final_txt}</td>
        </tr>
        """

    html_content = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>Examen Mental - {pac_nombre}</title>
    <style>
        body {{
            font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
            color: #1e293b;
            background: #ffffff;
            margin: 0;
            padding: 40px;
            font-size: 13px;
        }}
        .header {{
            border-bottom: 2.5px solid #A95993;
            padding-bottom: 15px;
            margin-bottom: 25px;
            display: flex;
            justify-content: space-between;
            align-items: flex-end;
        }}
        .header-title {{
            font-size: 20px;
            font-weight: 800;
            color: #A95993;
            margin: 0;
            letter-spacing: 0.5px;
        }}
        .header-sub {{
            font-size: 12px;
            color: #64748b;
            margin-top: 4px;
        }}
        .psic-info {{
            text-align: right;
            font-size: 11px;
            color: #475569;
        }}
        .section-title {{
            font-size: 13px;
            font-weight: 700;
            color: #A95993;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            border-bottom: 1.5px solid #e2e8f0;
            padding-bottom: 4px;
            margin-top: 20px;
            margin-bottom: 12px;
        }}
        .meta-grid {{
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 10px;
            background: #f8fafc;
            border: 1px solid #cbd5e1;
            border-radius: 8px;
            padding: 12px 16px;
            margin-bottom: 20px;
        }}
        .meta-item {{
            font-size: 12px;
        }}
        .meta-label {{
            font-weight: 700;
            color: #475569;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 25px;
        }}
        .obs-box {{
            background: #f8fafc;
            border-left: 4px solid #A95993;
            padding: 12px 16px;
            border-radius: 4px;
            font-size: 12px;
            line-height: 1.6;
            color: #334155;
            margin-bottom: 25px;
        }}
        .signature-block {{
            margin-top: 60px;
            text-align: center;
            display: flex;
            flex-direction: column;
            align-items: center;
        }}
        .signature-line {{
            width: 250px;
            border-top: 1.5px solid #475569;
            margin-bottom: 8px;
        }}
        @media print {{
            body {{ padding: 20px; }}
            .no-print {{ display: none; }}
        }}
    </style>
</head>
<body>
    <div class="no-print" style="margin-bottom: 20px; text-align: right;">
        <button onclick="window.print()" style="background: #A95993; color: white; border: none; padding: 8px 18px; border-radius: 6px; font-weight: 700; cursor: pointer;">🖨️ Imprimir / Guardar en PDF</button>
    </div>

    <div class="header">
        <div>
            <h1 class="header-title">INFORME DE EXAMEN MENTAL</h1>
            <div class="header-sub">Evaluación Clínica del Estado Mental (MSE)</div>
        </div>
        <div class="psic-info">
            <strong style="font-size: 13px; color: #3D1E3F;">{psic_nombre}</strong><br>
            {psic_titulo}<br>
            N° Federación / Colegiado: {psic_fed}
        </div>
    </div>

    <div class="section-title">1. DATOS DEL CONSULTANTE</div>
    <div class="meta-grid">
        <div class="meta-item"><span class="meta-label">Paciente:</span> {pac_nombre}</div>
        <div class="meta-item"><span class="meta-label">Identificación / Cédula:</span> {pac_cedula}</div>
        <div class="meta-item"><span class="meta-label">Edad / Género:</span> {pac_edad} años ({pac_genero})</div>
        <div class="meta-item"><span class="meta-label">Fecha / Modalidad:</span> {fecha_fmt} ({exam['medio_evaluacion']})</div>
    </div>

    <div class="section-title">2. REDACCIÓN CLÍNICA DEL EXAMEN MENTAL (TEXTO CORRIDO)</div>
    <div class="obs-box" style="text-align: justify; font-size: 12.5px; line-height: 1.7; border-left: 4.5px solid #A95993; background: #fdfafc;">
        <strong style="color: #A95993;">Redacción Clínica Continua:</strong><br>
        {narrative_text}
    </div>

    <div style="font-size: 11px; font-weight: 700; color: #64748b; margin-bottom: 8px; text-transform: uppercase;">Cuadrícula Resumen por Área Clínica:</div>
    <table>
        <tbody>
            {area_rows_html}
        </tbody>
    </table>

    <div class="section-title">3. IMPRESIÓN DIAGNÓSTICA Y OBSERVACIONES GENERALES</div>
    <div class="obs-box">
        {exam['observaciones_generales'] or 'Sin observaciones adicionales registradas por el profesional.'}
    </div>

    <div class="signature-block">
        <div class="signature-line"></div>
        <strong style="font-size: 13px; color: #3D1E3F;">{psic_nombre}</strong>
        <div style="font-size: 11px; color: #64748b; margin-top: 2px;">{psic_titulo} — N° Fed: {psic_fed}</div>
        <div style="font-size: 10px; color: #94a3b8; margin-top: 4px;">Firma y Sello Profesional</div>
    </div>
</body>
</html>"""

    return html_content


@app.route('/api/examen-mental/<int:exam_id>/export/word', methods=['GET'])
@login_required
def export_examen_mental_word(exam_id):
    user_id = session.get('user_id')
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute("SELECT * FROM usuarios WHERE id = ?", (user_id,))
    psic = cursor.fetchone()
    if not psic:
        return "Error: Usuario no encontrado", 404
        
    cursor.execute("""
        SELECT e.*, p.nombres as pac_nombres, p.apellidos as pac_apellidos, p.cedula as pac_cedula,
               p.genero as pac_genero, p.fecha_nacimiento as pac_fecha_nacimiento
        FROM examenes_mentales e
        JOIN pacientes p ON e.paciente_id = p.id
        WHERE e.id = ? AND e.psicologo_id = ?
    """, (exam_id, user_id))
    
    exam = cursor.fetchone()
    if not exam:
        return "Error: Examen mental no encontrado", 404
        
    import json
    datos_eval = {}
    try:
        datos_eval = json.loads(exam['datos_evaluacion_json']) if exam['datos_evaluacion_json'] else {}
    except:
        pass
        
    psic_nombre = f"Psic. {psic['nombres'] or ''} {psic['apellidos'] or ''}".strip()
    psic_titulo = psic['nomenclatura'] or psic['estudios'] or "Psicólogo Clínico"
    psic_fed = psic['federacion'] or "N/R"
    
    pac_nombre = f"{exam['pac_nombres'] or ''} {exam['pac_apellidos'] or ''}".strip()
    pac_cedula = exam['pac_cedula'] or "N/A"
    pac_genero = exam['pac_genero'] or "No especificado"
    pac_edad = _calculate_age_str(exam['pac_fecha_nacimiento'])
    
    try:
        f_parts = exam['fecha_evaluacion'].split('-')
        fecha_fmt = f"{f_parts[2]}/{f_parts[1]}/{f_parts[0]}"
    except:
        fecha_fmt = exam['fecha_evaluacion']

    import io
    import docx
    from docx.shared import Inches, Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    doc = docx.Document()
    
    # Configurar márgenes
    sections = doc.sections
    for section in sections:
        section.top_margin = Inches(0.8)
        section.bottom_margin = Inches(0.8)
        section.left_margin = Inches(0.85)
        section.right_margin = Inches(0.85)

    # Título principal
    p_header = doc.add_paragraph()
    p_header.alignment = WD_ALIGN_PARAGRAPH.LEFT
    r_title = p_header.add_run("INFORME DE EXAMEN MENTAL (MSE)\n")
    r_title.bold = True
    r_title.font.size = Pt(16)
    r_title.font.color.rgb = RGBColor(0xA9, 0x59, 0x93)

    r_psic = p_header.add_run(f"{psic_nombre} — {psic_titulo} (N° Fed: {psic_fed})\n")
    r_psic.font.size = Pt(10)
    r_psic.font.color.rgb = RGBColor(0x47, 0x55, 0x69)

    doc.add_paragraph().paragraph_format.space_after = Pt(6)

    # 1. DATOS DEL CONSULTANTE
    p_s1 = doc.add_paragraph()
    r_s1 = p_s1.add_run("1. DATOS DEL CONSULTANTE")
    r_s1.bold = True
    r_s1.font.size = Pt(12)
    r_s1.font.color.rgb = RGBColor(0xA9, 0x59, 0x93)

    p_info = doc.add_paragraph()
    p_info.add_run(f"• Paciente: ").bold = True
    p_info.add_run(f"{pac_nombre}\n")
    p_info.add_run(f"• Identificación / Cédula: ").bold = True
    p_info.add_run(f"{pac_cedula}\n")
    p_info.add_run(f"• Edad / Género: ").bold = True
    p_info.add_run(f"{pac_edad} años ({pac_genero})\n")
    p_info.add_run(f"• Fecha / Modalidad de Evaluación: ").bold = True
    p_info.add_run(f"{fecha_fmt} ({exam['medio_evaluacion']})")

    doc.add_paragraph().paragraph_format.space_after = Pt(6)

    # 2. REDACCIÓN CLÍNICA Y HALLAZGOS POR ÁREAS
    p_s2 = doc.add_paragraph()
    r_s2 = p_s2.add_run("2. REDACCIÓN CLÍNICA DEL EXAMEN MENTAL (TEXTO CORRIDO)")
    r_s2.bold = True
    r_s2.font.size = Pt(12)
    r_s2.font.color.rgb = RGBColor(0xA9, 0x59, 0x93)

    narrative_text = _build_mse_narrative(datos_eval, pac_genero=pac_genero, pac_edad=pac_edad, modalidad=exam['medio_evaluacion'])

    p_nar = doc.add_paragraph()
    p_nar.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    r_nar_lbl = p_nar.add_run("Redacción Clínica Continua:\n")
    r_nar_lbl.bold = True
    r_nar_lbl.font.size = Pt(11)
    r_nar_lbl.font.color.rgb = RGBColor(0xA9, 0x59, 0x93)
    
    r_nar_txt = p_nar.add_run(narrative_text)
    r_nar_txt.font.size = Pt(10.5)
    r_nar_txt.font.color.rgb = RGBColor(0x1E, 0x29, 0x3B)
    
    doc.add_paragraph().paragraph_format.space_after = Pt(6)

    p_tbl_h = doc.add_paragraph()
    r_tbl_h = p_tbl_h.add_run("Cuadrícula Resumen por Área Clínica:")
    r_tbl_h.bold = True
    r_tbl_h.font.size = Pt(10)
    r_tbl_h.font.color.rgb = RGBColor(0x64, 0x74, 0x8B)

    area_titles = {
        "apariencia": "Apariencia y Porte",
        "actitud": "Actitud hacia el Evaluador",
        "conciencia": "Nivel de Conciencia",
        "orientacion": "Orientación",
        "memoria": "Memoria",
        "atencion": "Atención y Concentración",
        "lenguaje": "Lenguaje y Comunicación",
        "pensamiento": "Pensamiento (Curso y Contenido)",
        "afecto": "Afecto y Estado de Ánimo",
        "percepcion": "Percepción",
        "juicio": "Juicio de Realidad",
        "introspeccion": "Introspección (Insight)"
    }

    table = doc.add_table(rows=1, cols=2)
    table.style = 'Table Grid'
    hdr_cells = table.rows[0].cells
    hdr_cells[0].text = "Área Clínica"
    hdr_cells[1].text = "Hallazgos / Observaciones"
    hdr_cells[0].paragraphs[0].runs[0].font.bold = True
    hdr_cells[1].paragraphs[0].runs[0].font.bold = True

    for area_key, area_name in area_titles.items():
        val_obj = datos_eval.get(area_key, {})
        selecciones = val_obj.get('selecciones', [])
        observacion = val_obj.get('observacion', '').strip()
        
        txt_parts = []
        if selecciones:
            txt_parts.append(", ".join(selecciones))
        if observacion:
            txt_parts.append(f"Obs: {observacion}")
            
        final_txt = " — ".join(txt_parts) if txt_parts else "Sin hallazgos significativos reportados."
        
        row_cells = table.add_row().cells
        row_cells[0].text = area_name
        row_cells[0].paragraphs[0].runs[0].font.bold = True
        row_cells[1].text = final_txt

    doc.add_paragraph().paragraph_format.space_after = Pt(12)

    # 3. IMPRESIÓN DIAGNÓSTICA
    p_s3 = doc.add_paragraph()
    r_s3 = p_s3.add_run("3. IMPRESIÓN DIAGNÓSTICA Y OBSERVACIONES GENERALES")
    r_s3.bold = True
    r_s3.font.size = Pt(12)
    r_s3.font.color.rgb = RGBColor(0xA9, 0x59, 0x93)

    p_obs = doc.add_paragraph()
    p_obs.add_run(exam['observaciones_generales'] or 'Sin observaciones adicionales registradas por el profesional.')

    doc.add_paragraph().paragraph_format.space_after = Pt(30)

    # Firma
    p_sig = doc.add_paragraph()
    p_sig.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_sig.add_run("___________________________________________\n").bold = True
    p_sig.add_run(f"{psic_nombre}\n").bold = True
    p_sig.add_run(f"{psic_titulo} — N° Fed: {psic_fed}\n")
    p_sig.add_run("Firma y Sello Profesional").font.color.rgb = RGBColor(0x94, 0xA3, 0xB8)

    mem_file = io.BytesIO()
    doc.save(mem_file)
    mem_file.seek(0)
    
    clean_cedula = pac_cedula.replace(" ", "_")
    filename = f"Examen_Mental_{clean_cedula}_{exam['fecha_evaluacion']}.docx"
    
    return Response(
        mem_file.getvalue(),
        mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'}
    )


# ==============================================================================
# MÓDULO DE TESTS PSICOLÓGICOS (BDI-II, BAI, TCS, UGDS-GS)
# ==============================================================================

import uuid

def ensure_tests_tables(db):
    cursor = db.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tests_definiciones (
            code TEXT PRIMARY KEY,
            nombre TEXT NOT NULL,
            siglas TEXT NOT NULL,
            categoria TEXT,
            descripcion TEXT,
            instrucciones TEXT,
            escala_opciones_json TEXT,
            items_json TEXT NOT NULL,
            reglas_correccion_json TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS test_asignaciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid_token TEXT UNIQUE NOT NULL,
            patient_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            test_code TEXT NOT NULL,
            estado TEXT DEFAULT 'pendiente',
            modo_aplicacion TEXT DEFAULT 'link',
            fecha_asignacion DATETIME DEFAULT CURRENT_TIMESTAMP,
            fecha_completado DATETIME,
            respuestas_json TEXT,
            puntaje_total REAL,
            subescalas_json TEXT,
            clasificacion_resultado TEXT,
            interpretacion_clinica TEXT,
            notas_terapeuta TEXT,
            FOREIGN KEY (user_id) REFERENCES usuarios(id) ON DELETE CASCADE,
            FOREIGN KEY (patient_id) REFERENCES pacientes(id) ON DELETE CASCADE
        )
    """)
    cursor.execute("PRAGMA table_info(test_asignaciones)")
    ta_cols = [r[1] for r in cursor.fetchall()]
    if ta_cols:
        if 'modo_aplicacion' not in ta_cols:
            cursor.execute("ALTER TABLE test_asignaciones ADD COLUMN modo_aplicacion TEXT DEFAULT 'link'")
        if 'subescalas_json' not in ta_cols:
            cursor.execute("ALTER TABLE test_asignaciones ADD COLUMN subescalas_json TEXT")
        if 'clasificacion_resultado' not in ta_cols:
            cursor.execute("ALTER TABLE test_asignaciones ADD COLUMN clasificacion_resultado TEXT")
        if 'interpretacion_clinica' not in ta_cols:
            cursor.execute("ALTER TABLE test_asignaciones ADD COLUMN interpretacion_clinica TEXT")
        if 'notas_terapeuta' not in ta_cols:
            cursor.execute("ALTER TABLE test_asignaciones ADD COLUMN notas_terapeuta TEXT")
    db.commit()

    # Asegurar que todas las definiciones del catálogo de tests existan o se actualicen
    seed_tests = [
        (
            "BDI-II",
            "Inventario de Depresión de Beck - Segunda Edición",
            "BDI-II",
            "Evaluación Emocional / Depresión",
            "Instrumento clínico autoadministrado de 21 ítems para medir la gravedad de la depresión en adultos y adolescentes.",
            "Por favor, lea con atención cada grupo de afirmaciones y elija la que mejor describa cómo se ha sentido durante las últimas dos semanas, incluyendo el día de hoy.",
            json.dumps([]),
            json.dumps([
                {"num": 1, "titulo": "1. Tristeza", "opciones": [{"val": 0, "txt": "No me siento triste."}, {"val": 1, "txt": "Me siento triste gran parte del tiempo."}, {"val": 2, "txt": "Estoy triste todo el tiempo."}, {"val": 3, "txt": "Estoy tan triste o desdichado que no puedo soportarlo."}]},
                {"num": 2, "titulo": "2. Pesimismo", "opciones": [{"val": 0, "txt": "No estoy desalentado respecto a mi futuro."}, {"val": 1, "txt": "Me siento más desalentado respecto a mi futuro que antes."}, {"val": 2, "txt": "No espero que las cosas me salgan bien."}, {"val": 3, "txt": "Siento que mi futuro es desesperanzador y que las cosas solo empeorarán."}]},
                {"num": 3, "titulo": "3. Fracaso", "opciones": [{"val": 0, "txt": "No me siento como un fracasado."}, {"val": 1, "txt": "He fracasado más de lo que debería."}, {"val": 2, "txt": "Cuando miro hacia atrás, veo muchos fracasos."}, {"val": 3, "txt": "Siento que como persona soy un fracaso total."}]},
                {"num": 4, "titulo": "4. Pérdida de placer", "opciones": [{"val": 0, "txt": "Obtengo el mismo placer de siempre de las cosas que me gustan."}, {"val": 1, "txt": "No disfruto de las cosas tanto como antes."}, {"val": 2, "txt": "Obtengo muy poco placer de las cosas que solía disfrutar."}, {"val": 3, "txt": "No puedo obtener ningún placer de las cosas que solía disfrutar."}]},
                {"num": 5, "titulo": "5. Sentimiento de culpa", "opciones": [{"val": 0, "txt": "No me siento particularmente culpable."}, {"val": 1, "txt": "Me siento culpable por muchas cosas que he hecho o debería haber hecho."}, {"val": 2, "txt": "Me siento bastante culpable la mayor parte del tiempo."}, {"val": 3, "txt": "Me siento continuamente culpable."}]},
                {"num": 6, "titulo": "6. Sentimiento de castigo", "opciones": [{"val": 0, "txt": "No siento que esté siendo castigado."}, {"val": 1, "txt": "Siento que tal vez pueda ser castigado."}, {"val": 2, "txt": "Espero ser castigado."}, {"val": 3, "txt": "Siento que estoy siendo castigado."}]},
                {"num": 7, "titulo": "7. Disconformidad con uno mismo", "opciones": [{"val": 0, "txt": "Siento lo mismo que siempre respecto a mí mismo."}, {"val": 1, "txt": "He perdido la confianza en mí mismo."}, {"val": 2, "txt": "Estoy decepcionado de mí mismo."}, {"val": 3, "txt": "Me detesto a mí mismo."}]},
                {"num": 8, "titulo": "8. Autocrítica", "opciones": [{"val": 0, "txt": "No me critico ni me culpo más de lo habitual."}, {"val": 1, "txt": "Estoy más crítico conmigo mismo de lo que solía estar."}, {"val": 2, "txt": "Me critico por todas mis faltas."}, {"val": 3, "txt": "Me culpo por todo lo malo que sucede."}]},
                {"num": 9, "titulo": "9. Pensamientos o deseos suicidas", "opciones": [{"val": 0, "txt": "No tengo ningún pensamiento de matarme."}, {"val": 1, "txt": "Tengo pensamientos de matarme, pero no los llevaría a cabo."}, {"val": 2, "txt": "Desearía matarme."}, {"val": 3, "txt": "Me mataría si tuviera la oportunidad."}]},
                {"num": 10, "titulo": "10. Llanto", "opciones": [{"val": 0, "txt": "No lloro más de lo que solía hacerlo."}, {"val": 1, "txt": "Lloro más de lo que solía hacerlo."}, {"val": 2, "txt": "Lloro por cualquier pequeñez."}, {"val": 3, "txt": "Siento ganas de llorar, pero no puedo."}]},
                {"num": 11, "titulo": "11. Agitación / Inquietud", "opciones": [{"val": 0, "txt": "No me siento más inquieto o agitado que de costumbre."}, {"val": 1, "txt": "Me siento más inquieto o agitado de lo habitual."}, {"val": 2, "txt": "Estoy tan inquieto que me cuesta quedarme quieto."}, {"val": 3, "txt": "Estoy tan agitado que tengo que estar en constante movimiento."}]},
                {"num": 12, "titulo": "12. Pérdida de interés", "opciones": [{"val": 0, "txt": "No he perdido el interés en otras personas o actividades."}, {"val": 1, "txt": "Estoy menos interesado en los demás o en las cosas que antes."}, {"val": 2, "txt": "He perdido casi todo el interés en los demás o en las cosas."}, {"val": 3, "txt": "Me cuesta mucho interesarme por algo."}]},
                {"num": 13, "titulo": "13. Indecisión", "opciones": [{"val": 0, "txt": "Tomo decisiones tan bien como siempre."}, {"val": 1, "txt": "Me resulta más difícil tomar decisiones que de costumbre."}, {"val": 2, "txt": "Tengo mucha más dificultad para tomar decisiones que antes."}, {"val": 3, "txt": "Tengo problemas para tomar cualquier decisión."}]},
                {"num": 14, "titulo": "14. Inutilidad", "opciones": [{"val": 0, "txt": "No me siento inútil."}, {"val": 1, "txt": "No me considero tan útil o valioso como solía ser."}, {"val": 2, "txt": "Me siento más inútil en comparación con otras personas."}, {"val": 3, "txt": "Me siento completamente inútil."}]},
                {"num": 15, "titulo": "15. Pérdida de energía", "opciones": [{"val": 0, "txt": "Tengo tanta energía como siempre."}, {"val": 1, "txt": "Tengo menos energía de la que solía tener."}, {"val": 2, "txt": "No tengo suficiente energía para hacer casi nada."}, {"val": 3, "txt": "No tengo energía para hacer nada."}]},
                {"num": 16, "titulo": "16. Cambios en el patrón de sueño", "opciones": [
                    {"val": 0, "txt": "No he experimentado ningún cambio en mis hábitos de sueño."},
                    {"val": 1, "txt": "Duermo algo más de lo habitual."},
                    {"val": 1, "txt": "Duermo algo menos de lo habitual."},
                    {"val": 2, "txt": "Duermo mucho más de lo habitual."},
                    {"val": 2, "txt": "Duermo mucho menos de lo habitual."},
                    {"val": 3, "txt": "Duermo casi todo el día."},
                    {"val": 3, "txt": "Me despierto 1-2 horas antes y no puedo volver a dormirme."}
                ]},
                {"num": 17, "titulo": "17. Irritabilidad", "opciones": [{"val": 0, "txt": "No estoy más irritable de lo habitual."}, {"val": 1, "txt": "Estoy más irritable de lo habitual."}, {"val": 2, "txt": "Estoy mucho más irritable de lo habitual."}, {"val": 3, "txt": "Estoy irritable todo el tiempo."}]},
                {"num": 18, "titulo": "18. Cambios en el apetito", "opciones": [
                    {"val": 0, "txt": "No he experimentado ningún cambio en mi apetito."},
                    {"val": 1, "txt": "Mi apetito es algo menor que de costumbre."},
                    {"val": 1, "txt": "Mi apetito es algo mayor que de costumbre."},
                    {"val": 2, "txt": "Mi apetito es mucho menor que antes."},
                    {"val": 2, "txt": "Mi apetito es mucho mayor que antes."},
                    {"val": 3, "txt": "No tengo ningún apetito en absoluto."},
                    {"val": 3, "txt": "Tengo ganas de comer todo el tiempo."}
                ]},
                {"num": 19, "titulo": "19. Dificultad de concentración", "opciones": [{"val": 0, "txt": "Puedo concentrarme tan bien como siempre."}, {"val": 1, "txt": "No puedo concentrarme tan bien como habitualmente."}, {"val": 2, "txt": "Me cuesta mantener la mente en algo por mucho tiempo."}, {"val": 3, "txt": "Encuentro que no puedo concentrarme en nada."}]},
                {"num": 20, "titulo": "20. Cansancio o fatiga", "opciones": [{"val": 0, "txt": "No estoy más cansado o fatigado que de costumbre."}, {"val": 1, "txt": "Me canso o me fatigo más fácilmente que antes."}, {"val": 2, "txt": "Estoy demasiado cansado o fatigado para hacer muchas cosas que solía hacer."}, {"val": 3, "txt": "Estoy demasiado cansado o fatigado para hacer la mayoría de las cosas."}]},
                {"num": 21, "titulo": "21. Pérdida de interés por el sexo", "opciones": [{"val": 0, "txt": "No he notado ningún cambio reciente en mi interés por el sexo."}, {"val": 1, "txt": "Estoy menos interesado en el sexo de lo que solía estar."}, {"val": 2, "txt": "Estoy mucho menos interesado en el sexo ahora."}, {"val": 3, "txt": "He perdido completamente el interés en el sexo."}]}
            ]),
            json.dumps({"max": 63, "cortes": [13, 19, 28]})
        ),
        (
            "BAI",
            "Inventario de Ansiedad de Beck",
            "BAI",
            "Evaluación Emocional / Ansiedad",
            "Instrumento autoadministrado de 21 síntomas para discriminar la gravedad de la ansiedad clínica.",
            "A continuación se presenta una lista de síntomas comunes de la ansiedad. Lea cada uno atentamente e indique cuánto le ha molestado cada síntoma durante la última semana, incluyendo el día de hoy.",
            json.dumps([
                {"val": 0, "txt": "0 = En absoluto"},
                {"val": 1, "txt": "1 = Levemente (no me molestó mucho)"},
                {"val": 2, "txt": "2 = Moderadamente (fue muy desagradable pero pude soportarlo)"},
                {"val": 3, "txt": "3 = Severamente (casi no pude soportarlo)"}
            ]),
            json.dumps([
                {"num": 1, "txt": "1. Entumecimiento o hormigueo"},
                {"num": 2, "txt": "2. Sensación de calor / Sofocos"},
                {"num": 3, "txt": "3. Temblor en las piernas"},
                {"num": 4, "txt": "4. Incapacidad para relajarse"},
                {"num": 5, "txt": "5. Temor a que ocurra lo peor"},
                {"num": 6, "txt": "6. Mareo o aturdimiento"},
                {"num": 7, "txt": "7. Palpitaciones o ritmo cardíaco acelerado"},
                {"num": 8, "txt": "8. Inestabilidad o sensación de desmayo"},
                {"num": 9, "txt": "9. Terror, miedo o pánico"},
                {"num": 10, "txt": "10. Nerviosismo"},
                {"num": 11, "txt": "11. Sensación de ahogo o sofocación"},
                {"num": 12, "txt": "12. Temblor en las manos"},
                {"num": 13, "txt": "13. Inquietud / Tembloroso"},
                {"num": 14, "txt": "14. Miedo a perder el control"},
                {"num": 15, "txt": "15. Dificultad para respirar"},
                {"num": 16, "txt": "16. Miedo a morir"},
                {"num": 17, "txt": "17. Sobresalto / Asustadizo"},
                {"num": 18, "txt": "18. Indigestión o malestar en el estómago"},
                {"num": 19, "txt": "19. Sensación de desvanecimiento"},
                {"num": 20, "txt": "20. Enrojecimiento facial"},
                {"num": 21, "txt": "21. Sudoración (no debida al calor)"}
            ]),
            json.dumps({"max": 63, "cortes": [7, 15, 25]})
        ),
        (
            "TCS",
            "Escala de Congruencia Transgénero",
            "TCS",
            "Identidad de Género / Afirmación",
            "Evalúa el grado de autoaceptación y congruencia de la apariencia corporal respecto a la identidad de género felt/sentida.",
            "Por favor, lee atentamente cada una de las siguientes afirmaciones y marca la opción que mejor describa cómo te sientes.",
            json.dumps([
                {"val": 1, "txt": "1 = Totalmente en desacuerdo"},
                {"val": 2, "txt": "2 = En desacuerdo"},
                {"val": 3, "txt": "3 = Ni de acuerdo ni en desacuerdo"},
                {"val": 4, "txt": "4 = De acuerdo"},
                {"val": 5, "txt": "5 = Totalmente de acuerdo"}
            ]),
            json.dumps([
                {"num": 1, "txt": "1. Siento que mi apariencia física expresa adecuadamente mi identidad de género."},
                {"num": 2, "txt": "2. Mi apariencia física exterior es incongruente con mi identidad de género. (Inverso)"},
                {"num": 3, "txt": "3. Acepto mi identidad de género."},
                {"num": 4, "txt": "4. Siento que la forma en que los demás ven mi género coincide con mi identidad de género."},
                {"num": 5, "txt": "5. Me alegra tener la identidad de género que tengo."},
                {"num": 6, "txt": "6. Desearía que mi cuerpo representara con mayor precisión mi identidad de género. (Inverso)"},
                {"num": 7, "txt": "7. Me siento cómodo/a/e con mi identidad de género."},
                {"num": 8, "txt": "8. Siento que mi cuerpo no representa mi identidad de género. (Inverso)"},
                {"num": 9, "txt": "9. He aceptado completamente mi identidad de género."},
                {"num": 10, "txt": "10. Mi apariencia física exterior representa con precisión mi identidad de género."},
                {"num": 11, "txt": "11. Siento que mi identidad de género es una parte hermosa de lo que soy."},
                {"num": 12, "txt": "12. Siento que mi cuerpo y mi identidad de género están en sintonía."}
            ]),
            json.dumps({"inversos": [2, 6, 8]})
        ),
        (
            "UGDS-GS",
            "Escala de Disforia de Género de Utrecht - Espectro de Género",
            "UGDS-GS",
            "Identidad de Género / Disforia",
            "Mide el malestar o distrés derivado de la incongruencia entre el sexo asignado al nacer y la identidad de género sentida.",
            "Responde a las siguientes afirmaciones indicando qué tan de acuerdo estás con cada una de ellas de acuerdo a tu experiencia reciente.",
            json.dumps([
                {"val": 1, "txt": "1 = Totalmente en desacuerdo"},
                {"val": 2, "txt": "2 = En desacuerdo"},
                {"val": 3, "txt": "3 = Neutral / A veces"},
                {"val": 4, "txt": "4 = De acuerdo"},
                {"val": 5, "txt": "5 = Totalmente de acuerdo"}
            ]),
            json.dumps([
                {"num": 1, "txt": "1. Me siento incómodo/a/e cuando veo mi cuerpo desnudo en el espejo debido a mis características sexuales."},
                {"num": 2, "txt": "2. Me siento feliz con las partes de mi cuerpo que corresponden a mi sexo asignado al nacer. (Inverso)"},
                {"num": 3, "txt": "3. Evito que otras personas vean o toquen ciertas partes de mi cuerpo por malestar con mi sexo asignado."},
                {"num": 4, "txt": "4. Siento que las expectativas sociales asociadas a mi sexo asignado al nacer me asfixian o limitan."},
                {"num": 5, "txt": "5. Me genera mucho malestar que la gente se refiera a mí con términos asociados a mi sexo asignado al nacer."},
                {"num": 6, "txt": "6. Experimento una sensación de alivio y felicidad cuando las personas me reconocen con mi género sentido. (Inverso)"},
                {"num": 7, "txt": "7. Desearía haber nacido con las características corporales de mi género sentido."},
                {"num": 8, "txt": "8. Siento que mi cuerpo actual no encaja en lo absoluto con quién soy internamente."},
                {"num": 9, "txt": "9. Me resulta doloroso o incómodo participar en interacciones sociales bajo las expectativas de mi sexo asignado."},
                {"num": 10, "txt": "10. Me siento cómodo/a/e interpretando el rol social correspondiente al género con el que me identifico. (Inverso)"},
                {"num": 11, "txt": "11. La idea de vivir el resto de mi vida siendo tratado/a/e según mi sexo asignado al nacer me resulta insoportable."},
                {"num": 12, "txt": "12. Constantemente busco formas de modificar o camuflar mis características sexuales secundarias (pecho, vello, voz, etc.)."},
                {"num": 13, "txt": "13. Siento envidia cuando veo a personas que expresan y viven libremente el género con el que me identifico."},
                {"num": 14, "txt": "14. He llegado a sentir un profundo rechazo hacia mis propios genitales."},
                {"num": 15, "txt": "15. Me siento orgulloso/a/e del camino que estoy tomando para afirmar mi identidad de género. (Inverso)"},
                {"num": 16, "txt": "16. Socializar en mi género sentido me hace sentir una persona más auténtica y completa. (Inverso)"},
                {"num": 17, "txt": "17. Siento que la incongruencia entre mi mente y mi cuerpo me genera un desgaste emocional muy alto en el día a día."},
                {"num": 18, "txt": "18. El reconocimiento legal de mi identidad de género (documentos, nombres) es fundamental para mi bienestar."}
            ]),
            json.dumps({"inversos": [2, 6, 10, 15, 16], "cortes": [40, 60]})
        )
    ]
    cursor.executemany("""
        INSERT INTO tests_definiciones 
        (code, nombre, siglas, categoria, descripcion, instrucciones, escala_opciones_json, items_json, reglas_correccion_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(code) DO UPDATE SET
            nombre=excluded.nombre,
            siglas=excluded.siglas,
            categoria=excluded.categoria,
            descripcion=excluded.descripcion,
            instrucciones=excluded.instrucciones,
            escala_opciones_json=excluded.escala_opciones_json,
            items_json=excluded.items_json,
            reglas_correccion_json=excluded.reglas_correccion_json
    """, seed_tests)
    db.commit()

    # Actualizar BDI-II en la base de datos para asegurar las 7 opciones textuales en ítems 16 y 18
    bdi_updated_items = json.dumps([
        {"num": 1, "titulo": "1. Tristeza", "opciones": [{"val": 0, "txt": "No me siento triste."}, {"val": 1, "txt": "Me siento triste gran parte del tiempo."}, {"val": 2, "txt": "Estoy triste todo el tiempo."}, {"val": 3, "txt": "Estoy tan triste o desdichado que no puedo soportarlo."}]},
        {"num": 2, "titulo": "2. Pesimismo", "opciones": [{"val": 0, "txt": "No estoy desalentado respecto a mi futuro."}, {"val": 1, "txt": "Me siento más desalentado respecto a mi futuro que antes."}, {"val": 2, "txt": "No espero que las cosas me salgan bien."}, {"val": 3, "txt": "Siento que mi futuro es desesperanzador y que las cosas solo empeorarán."}]},
        {"num": 3, "titulo": "3. Fracaso", "opciones": [{"val": 0, "txt": "No me siento como un fracasado."}, {"val": 1, "txt": "He fracasado más de lo que debería."}, {"val": 2, "txt": "Cuando miro hacia atrás, veo muchos fracasos."}, {"val": 3, "txt": "Siento que como persona soy un fracaso total."}]},
        {"num": 4, "titulo": "4. Pérdida de placer", "opciones": [{"val": 0, "txt": "Obtengo el mismo placer de siempre de las cosas que me gustan."}, {"val": 1, "txt": "No disfruto de las cosas tanto como antes."}, {"val": 2, "txt": "Obtengo muy poco placer de las cosas que solía disfrutar."}, {"val": 3, "txt": "No puedo obtener ningún placer de las cosas que solía disfrutar."}]},
        {"num": 5, "titulo": "5. Sentimiento de culpa", "opciones": [{"val": 0, "txt": "No me siento particularmente culpable."}, {"val": 1, "txt": "Me siento culpable por muchas cosas que he hecho o debería haber hecho."}, {"val": 2, "txt": "Me siento bastante culpable la mayor parte del tiempo."}, {"val": 3, "txt": "Me siento continuamente culpable."}]},
        {"num": 6, "titulo": "6. Sentimiento de castigo", "opciones": [{"val": 0, "txt": "No siento que esté siendo castigado."}, {"val": 1, "txt": "Siento que tal vez pueda ser castigado."}, {"val": 2, "txt": "Espero ser castigado."}, {"val": 3, "txt": "Siento que estoy siendo castigado."}]},
        {"num": 7, "titulo": "7. Disconformidad con uno mismo", "opciones": [{"val": 0, "txt": "Siento lo mismo que siempre respecto a mí mismo."}, {"val": 1, "txt": "He perdido la confianza en mí mismo."}, {"val": 2, "txt": "Estoy decepcionado de mí mismo."}, {"val": 3, "txt": "Me detesto a mí mismo."}]},
        {"num": 8, "titulo": "8. Autocrítica", "opciones": [{"val": 0, "txt": "No me critico ni me culpo más de lo habitual."}, {"val": 1, "txt": "Estoy más crítico conmigo mismo de lo que solía estar."}, {"val": 2, "txt": "Me critico por todas mis faltas."}, {"val": 3, "txt": "Me culpo por todo lo malo que sucede."}]},
        {"num": 9, "titulo": "9. Pensamientos o deseos suicidas", "opciones": [{"val": 0, "txt": "No tengo ningún pensamiento de matarme."}, {"val": 1, "txt": "Tengo pensamientos de matarme, pero no los llevaría a cabo."}, {"val": 2, "txt": "Desearía matarme."}, {"val": 3, "txt": "Me mataría si tuviera la oportunidad."}]},
        {"num": 10, "titulo": "10. Llanto", "opciones": [{"val": 0, "txt": "No lloro más de lo que solía hacerlo."}, {"val": 1, "txt": "Lloro más de lo que solía hacerlo."}, {"val": 2, "txt": "Lloro por cualquier pequeñez."}, {"val": 3, "txt": "Siento ganas de llorar, pero no puedo."}]},
        {"num": 11, "titulo": "11. Agitación / Inquietud", "opciones": [{"val": 0, "txt": "No me siento más inquieto o agitado que de costumbre."}, {"val": 1, "txt": "Me siento más inquieto o agitado de lo habitual."}, {"val": 2, "txt": "Estoy tan inquieto que me cuesta quedarme quieto."}, {"val": 3, "txt": "Estoy tan agitado que tengo que estar en constante movimiento."}]},
        {"num": 12, "titulo": "12. Pérdida de interés", "opciones": [{"val": 0, "txt": "No he perdido el interés en otras personas o actividades."}, {"val": 1, "txt": "Estoy menos interesado en los demás o en las cosas que antes."}, {"val": 2, "txt": "He perdido casi todo el interés en los demás o en las cosas."}, {"val": 3, "txt": "Me cuesta mucho interesarme por algo."}]},
        {"num": 13, "titulo": "13. Indecisión", "opciones": [{"val": 0, "txt": "Tomo decisiones tan bien como siempre."}, {"val": 1, "txt": "Me resulta más difícil tomar decisiones que de costumbre."}, {"val": 2, "txt": "Tengo mucha más dificultad para tomar decisiones que antes."}, {"val": 3, "txt": "Tengo problemas para tomar cualquier decisión."}]},
        {"num": 14, "titulo": "14. Inutilidad", "opciones": [{"val": 0, "txt": "No me siento inútil."}, {"val": 1, "txt": "No me considero tan útil o valioso como solía ser."}, {"val": 2, "txt": "Me siento más inútil en comparación con otras personas."}, {"val": 3, "txt": "Me siento completamente inútil."}]},
        {"num": 15, "titulo": "15. Pérdida de energía", "opciones": [{"val": 0, "txt": "Tengo tanta energía como siempre."}, {"val": 1, "txt": "Tengo menos energía de la que solía tener."}, {"val": 2, "txt": "No tengo suficiente energía para hacer casi nada."}, {"val": 3, "txt": "No tengo energía para hacer nada."}]},
        {"num": 16, "titulo": "16. Cambios en el patrón de sueño", "opciones": [
            {"val": 0, "txt": "No he experimentado ningún cambio en mis hábitos de sueño."},
            {"val": 1, "txt": "Duermo algo más de lo habitual."},
            {"val": 1, "txt": "Duermo algo menos de lo habitual."},
            {"val": 2, "txt": "Duermo mucho más de lo habitual."},
            {"val": 2, "txt": "Duermo mucho menos de lo habitual."},
            {"val": 3, "txt": "Duermo casi todo el día."},
            {"val": 3, "txt": "Me despierto 1-2 horas antes y no puedo volver a dormirme."}
        ]},
        {"num": 17, "titulo": "17. Irritabilidad", "opciones": [{"val": 0, "txt": "No estoy más irritable de lo habitual."}, {"val": 1, "txt": "Estoy más irritable de lo habitual."}, {"val": 2, "txt": "Estoy mucho más irritable de lo habitual."}, {"val": 3, "txt": "Estoy irritable todo el tiempo."}]},
        {"num": 18, "titulo": "18. Cambios en el apetito", "opciones": [
            {"val": 0, "txt": "No he experimentado ningún cambio en mi apetito."},
            {"val": 1, "txt": "Mi apetito es algo menor que de costumbre."},
            {"val": 1, "txt": "Mi apetito es algo mayor que de costumbre."},
            {"val": 2, "txt": "Mi apetito es mucho menor que antes."},
            {"val": 2, "txt": "Mi apetito es mucho mayor que antes."},
            {"val": 3, "txt": "No tengo ningún apetito en absoluto."},
            {"val": 3, "txt": "Tengo ganas de comer todo el tiempo."}
        ]},
        {"num": 19, "titulo": "19. Dificultad de concentración", "opciones": [{"val": 0, "txt": "Puedo concentrarme tan bien como siempre."}, {"val": 1, "txt": "No puedo concentrarme tan bien como habitualmente."}, {"val": 2, "txt": "Me cuesta mantener la mente en algo por mucho tiempo."}, {"val": 3, "txt": "Encuentro que no puedo concentrarme en nada."}]},
        {"num": 20, "titulo": "20. Cansancio o fatiga", "opciones": [{"val": 0, "txt": "No estoy más cansado o fatigado que de costumbre."}, {"val": 1, "txt": "Me canso o me fatigo más fácilmente que antes."}, {"val": 2, "txt": "Estoy demasiado cansado o fatigado para hacer muchas cosas que solía hacer."}, {"val": 3, "txt": "Estoy demasiado cansado o fatigado para hacer la mayoría de las cosas."}]},
        {"num": 21, "titulo": "21. Pérdida de interés por el sexo", "opciones": [{"val": 0, "txt": "No he notado ningún cambio reciente en mi interés por el sexo."}, {"val": 1, "txt": "Estoy menos interesado en el sexo de lo que solía estar."}, {"val": 2, "txt": "Estoy mucho menos interesado en el sexo ahora."}, {"val": 3, "txt": "He sentido una pérdida completa de interés en el sexo."}]}
    ])
    cursor.execute("UPDATE tests_definiciones SET items_json = ? WHERE code = 'BDI-II'", (bdi_updated_items,))

    # Asegurar inserción/actualización incondicional de HOLLAND y MCMI-II
    holland_def = (
        "HOLLAND",
        "Test de Intereses Vocacionales de Holland (RIASEC)",
        "HOLLAND",
        "Orientación Vocacional / Intereses",
        "Evaluación estandarizada basada en la teoría tipológica de Holland para identificar el código vocacional de 2 letras (RIASEC) e interpretar carreras compatibles.",
        "Lea atentamente las afirmaciones sobre actividades, habilidades y carreras. Indique Sí (1) o No (0) según sus gustos y preferencias.",
        json.dumps([{"val": 1, "txt": "Sí (Me gusta / Habilidad)"}, {"val": 0, "txt": "No (No me gusta)"}]),
        "[{\"num\": 1, \"sec\": \"2. Habilidades\", \"cat\": \"R\", \"txt\": \"1. Componer  cosas  el\u00e9ctricas\"}, {\"num\": 2, \"sec\": \"2. Habilidades\", \"cat\": \"R\", \"txt\": \"2. Reparar  una  bicicleta,  auto  o  motocicleta\"}, {\"num\": 3, \"sec\": \"2. Habilidades\", \"cat\": \"R\", \"txt\": \"3. Componer  cosas  mec\u00e1nicas\"}, {\"num\": 4, \"sec\": \"2. Habilidades\", \"cat\": \"R\", \"txt\": \"4. Usar  herramientas  para  trabajar  con  metales  o  maquinaria\"}, {\"num\": 5, \"sec\": \"2. Habilidades\", \"cat\": \"R\", \"txt\": \"5. Trabajar  con  un  gran  mec\u00e1nico  o  t\u00e9cnico\"}, {\"num\": 6, \"sec\": \"2. Habilidades\", \"cat\": \"R\", \"txt\": \"6. Instalar  o  reparar  un  tel\u00e9fono\"}, {\"num\": 7, \"sec\": \"2. Habilidades\", \"cat\": \"R\", \"txt\": \"7. Construir  cosas  con  madera\"}, {\"num\": 8, \"sec\": \"2. Habilidades\", \"cat\": \"R\", \"txt\": \"8. Tomar  una  clase  de  educaci\u00f3n  tecnol\u00f3gica  (como  antes  industriales  o  taller  automotriz)\"}, {\"num\": 9, \"sec\": \"2. Habilidades\", \"cat\": \"R\", \"txt\": \"9. Trabajar  en  exteriores\"}, {\"num\": 10, \"sec\": \"2. Habilidades\", \"cat\": \"R\", \"txt\": \"10. Trabajar  con  equipo  electr\u00f3nico\"}, {\"num\": 11, \"sec\": \"2. Habilidades\", \"cat\": \"R\", \"txt\": \"11. Ir  de  visita  por  una  ferreter\u00eda\"}, {\"num\": 12, \"sec\": \"2. Habilidades\", \"cat\": \"R\", \"txt\": \"12. N\u00famero  Total  de  Letras  S\"}, {\"num\": 13, \"sec\": \"2. Habilidades\", \"cat\": \"I\", \"txt\": \"13. Escribir  un  reporte  cient\u00edfico\"}, {\"num\": 14, \"sec\": \"2. Habilidades\", \"cat\": \"I\", \"txt\": \"14. Aprender  acerca  de  la  f\u00edsica\"}, {\"num\": 15, \"sec\": \"2. Habilidades\", \"cat\": \"I\", \"txt\": \"15. Estudiar  qu\u00edmica\"}, {\"num\": 16, \"sec\": \"2. Habilidades\", \"cat\": \"I\", \"txt\": \"16. Tomar  una  clase  de  biolog\u00eda\"}, {\"num\": 17, \"sec\": \"2. Habilidades\", \"cat\": \"I\", \"txt\": \"17. Leer  libros  o  revistas  cient\u00edficos\"}, {\"num\": 18, \"sec\": \"2. Habilidades\", \"cat\": \"I\", \"txt\": \"18. Trabajar  en  un  proyecto  de  investigaci\u00f3n\"}, {\"num\": 19, \"sec\": \"2. Habilidades\", \"cat\": \"I\", \"txt\": \"19. Estudiar  una  teor\u00eda  cient\u00edfica\"}, {\"num\": 20, \"sec\": \"2. Habilidades\", \"cat\": \"I\", \"txt\": \"20. Analizar  informaci\u00f3n\"}, {\"num\": 21, \"sec\": \"2. Habilidades\", \"cat\": \"I\", \"txt\": \"21. Estudiar  astronom\u00eda\"}, {\"num\": 22, \"sec\": \"2. Habilidades\", \"cat\": \"I\", \"txt\": \"22. Visitar  un  museo  de  ciencias\"}, {\"num\": 23, \"sec\": \"2. Habilidades\", \"cat\": \"I\", \"txt\": \"23. Estudiar  el  cerebro\"}, {\"num\": 24, \"sec\": \"2. Habilidades\", \"cat\": \"I\", \"txt\": \"24. N\u00famero  Total  de  Letras  S\"}, {\"num\": 25, \"sec\": \"2. Habilidades\", \"cat\": \"A\", \"txt\": \"25. Hacer  bocetos,  dibujar  o  pintar\"}, {\"num\": 26, \"sec\": \"2. Habilidades\", \"cat\": \"A\", \"txt\": \"26. Tomar  fotograf\u00edas\"}, {\"num\": 27, \"sec\": \"2. Habilidades\", \"cat\": \"A\", \"txt\": \"27. Escribir  para  una  revista  o  peri\u00f3dico\"}, {\"num\": 28, \"sec\": \"2. Habilidades\", \"cat\": \"A\", \"txt\": \"28. Pintar  retratos\"}, {\"num\": 29, \"sec\": \"2. Habilidades\", \"cat\": \"A\", \"txt\": \"29. Leer  o  escribir  poes\u00eda\"}, {\"num\": 30, \"sec\": \"2. Habilidades\", \"cat\": \"A\", \"txt\": \"30. Tomar  una  clase  de  arte\"}, {\"num\": 31, \"sec\": \"2. Habilidades\", \"cat\": \"A\", \"txt\": \"31. Estudiar  con  un  artista  pl\u00e1stico,  m\u00fasico  o  escritor  talentoso\"}, {\"num\": 32, \"sec\": \"2. Habilidades\", \"cat\": \"A\", \"txt\": \"32. Tocar  un  instrumento  musical\"}, {\"num\": 33, \"sec\": \"2. Habilidades\", \"cat\": \"A\", \"txt\": \"33. Pertenecer  a  una  orquesta,  banda  o  grupo  musical\"}, {\"num\": 34, \"sec\": \"2. Habilidades\", \"cat\": \"A\", \"txt\": \"34. Escribir  novelas  u  obras  de  teatro\"}, {\"num\": 35, \"sec\": \"2. Habilidades\", \"cat\": \"A\", \"txt\": \"35. Leer  acerca  de  arte,  literatura  o  m\u00fasica\"}, {\"num\": 36, \"sec\": \"2. Habilidades\", \"cat\": \"A\", \"txt\": \"36. N\u00famero  Total  de  Letras  S\"}, {\"num\": 37, \"sec\": \"2. Habilidades\", \"cat\": \"S\", \"txt\": \"37. Dar  clases  en  una  escuela\"}, {\"num\": 38, \"sec\": \"2. Habilidades\", \"cat\": \"S\", \"txt\": \"38. Ayudar  a  ni\u00f1os  discapacitados\"}, {\"num\": 39, \"sec\": \"2. Habilidades\", \"cat\": \"S\", \"txt\": \"39. Conocer  a  educadores  o  terapeutas  importantes\"}, {\"num\": 40, \"sec\": \"2. Habilidades\", \"cat\": \"S\", \"txt\": \"40. Leer  libros  o  art\u00edculos  de  psicolog\u00eda\"}, {\"num\": 41, \"sec\": \"2. Habilidades\", \"cat\": \"S\", \"txt\": \"41. Tomar  una  clase  de  relaciones  humanas\"}, {\"num\": 42, \"sec\": \"2. Habilidades\", \"cat\": \"S\", \"txt\": \"42. Tomar  una  clase  de  superaci\u00f3n  personal\"}, {\"num\": 43, \"sec\": \"2. Habilidades\", \"cat\": \"S\", \"txt\": \"43. Resolver  conflictos  entre  otras  personas\"}, {\"num\": 44, \"sec\": \"2. Habilidades\", \"cat\": \"S\", \"txt\": \"44. Escribirle  cartas  a  los  amigos\"}, {\"num\": 45, \"sec\": \"2. Habilidades\", \"cat\": \"S\", \"txt\": \"45. Ayudar  a  la  gente  cuando  est\u00e1  enferma\"}, {\"num\": 46, \"sec\": \"2. Habilidades\", \"cat\": \"S\", \"txt\": \"46. Trabajar  para  una  l\u00ednea  telef\u00f3nica  de  urgencia  para  suicidas  o  j\u00f3venes  que  huyen  del  hogar\"}, {\"num\": 47, \"sec\": \"2. Habilidades\", \"cat\": \"S\", \"txt\": \"47. Ayudar  a  otros  a  que  resuelvan  sus  problemas\"}, {\"num\": 48, \"sec\": \"2. Habilidades\", \"cat\": \"S\", \"txt\": \"48. N\u00famero  Total  de  Letras  S\"}, {\"num\": 49, \"sec\": \"2. Habilidades\", \"cat\": \"E\", \"txt\": \"49. Ser  jefe  de  un  proyecto\"}, {\"num\": 50, \"sec\": \"2. Habilidades\", \"cat\": \"E\", \"txt\": \"50. Fungir  como  funcionario  de  un  grupo\"}, {\"num\": 51, \"sec\": \"2. Habilidades\", \"cat\": \"E\", \"txt\": \"51. Aprender  a  ser  exitoso  en  los  negocios\"}, {\"num\": 52, \"sec\": \"2. Habilidades\", \"cat\": \"E\", \"txt\": \"52. Tomar  una  clase  breve  sobre  liderazgo\"}, {\"num\": 53, \"sec\": \"2. Habilidades\", \"cat\": \"E\", \"txt\": \"53. Supervisar  el  trabajo  de  otros\"}, {\"num\": 54, \"sec\": \"2. Habilidades\", \"cat\": \"E\", \"txt\": \"54. Conducir  a  un  grupo  a  obtener  su  meta\"}, {\"num\": 55, \"sec\": \"2. Habilidades\", \"cat\": \"E\", \"txt\": \"55. Conocer  a  ejecutivos  y  lideres  importantes\"}, {\"num\": 56, \"sec\": \"2. Habilidades\", \"cat\": \"E\", \"txt\": \"56. Participar  en  una  campa\u00f1a  pol\u00edtica\"}, {\"num\": 57, \"sec\": \"2. Habilidades\", \"cat\": \"E\", \"txt\": \"57. Dirigir  el  trabajo  de  otros\"}, {\"num\": 58, \"sec\": \"2. Habilidades\", \"cat\": \"E\", \"txt\": \"58. Operar  mi  propio  negocio\"}, {\"num\": 59, \"sec\": \"2. Habilidades\", \"cat\": \"E\", \"txt\": \"59. Vender  espacios  publicitarios  en  anuario  escolar\"}, {\"num\": 60, \"sec\": \"2. Habilidades\", \"cat\": \"E\", \"txt\": \"60. N\u00famero  Total  de  Letras  S\"}, {\"num\": 61, \"sec\": \"2. Habilidades\", \"cat\": \"C\", \"txt\": \"61. Sumar,  restar,  multiplicar  y  dividir  n\u00fameros  en  un  negocio  o  en  contadur\u00eda\"}, {\"num\": 62, \"sec\": \"2. Habilidades\", \"cat\": \"C\", \"txt\": \"62. Llevar  un  registro  de  gastos\"}, {\"num\": 63, \"sec\": \"2. Habilidades\", \"cat\": \"C\", \"txt\": \"63. Tomar  una  clase  de  c\u00e1lculo  mercantil\"}, {\"num\": 64, \"sec\": \"2. Habilidades\", \"cat\": \"C\", \"txt\": \"64. Examinar  documentos  o  productos  para  encontrar  errores  o  fallas\"}, {\"num\": 65, \"sec\": \"2. Habilidades\", \"cat\": \"C\", \"txt\": \"65. Revisar  registros  financieros  para  encontrar  errores\"}, {\"num\": 66, \"sec\": \"2. Habilidades\", \"cat\": \"C\", \"txt\": \"66. Cuadrar  las  cuentas  en  una  chequera\"}, {\"num\": 67, \"sec\": \"2. Habilidades\", \"cat\": \"C\", \"txt\": \"67. Llevar  registros\"}, {\"num\": 68, \"sec\": \"2. Habilidades\", \"cat\": \"C\", \"txt\": \"68. Operar  maquinaria  de  oficina  (no  leo  bien)\"}, {\"num\": 69, \"sec\": \"2. Habilidades\", \"cat\": \"C\", \"txt\": \"69. Tomar  una  clase  de  contabilidad\"}, {\"num\": 70, \"sec\": \"2. Habilidades\", \"cat\": \"C\", \"txt\": \"70. Hacer  un  inventario  de  suministros  o  productos\"}, {\"num\": 71, \"sec\": \"2. Habilidades\", \"cat\": \"C\", \"txt\": \"71. Establecer  un  sistema  de  registro\"}, {\"num\": 72, \"sec\": \"2. Habilidades\", \"cat\": \"C\", \"txt\": \"72. N\u00famero  Total  de  Letras  S\"}, {\"num\": 73, \"sec\": \"2. Habilidades\", \"cat\": \"R\", \"txt\": \"73. Cambiar  una  llanta\"}, {\"num\": 74, \"sec\": \"2. Habilidades\", \"cat\": \"R\", \"txt\": \"74. Operar  herramientas  el\u00e9ctricas  como  un  taladro  o  una  m\u00e1quina  de  coser\"}, {\"num\": 75, \"sec\": \"2. Habilidades\", \"cat\": \"R\", \"txt\": \"75. Interpretar  un  plano\"}, {\"num\": 76, \"sec\": \"2. Habilidades\", \"cat\": \"R\", \"txt\": \"76. Hacer  reparaciones  el\u00e9ctricas  sencillas\"}, {\"num\": 77, \"sec\": \"2. Habilidades\", \"cat\": \"R\", \"txt\": \"77. Reparar  muebles\"}, {\"num\": 78, \"sec\": \"2. Habilidades\", \"cat\": \"R\", \"txt\": \"78. Usar  la  mayor\u00eda  de  las  herramientas  de  un  carpintero\"}, {\"num\": 79, \"sec\": \"2. Habilidades\", \"cat\": \"R\", \"txt\": \"79. Usar  equipos  de  soldadura\"}, {\"num\": 80, \"sec\": \"2. Habilidades\", \"cat\": \"R\", \"txt\": \"80. Cazar  o  pescar\"}, {\"num\": 81, \"sec\": \"2. Habilidades\", \"cat\": \"R\", \"txt\": \"81. Hacer  dibujos  mec\u00e1nicos\"}, {\"num\": 82, \"sec\": \"2. Habilidades\", \"cat\": \"R\", \"txt\": \"82. Construir  cosas  sencillas  de  madera\"}, {\"num\": 83, \"sec\": \"2. Habilidades\", \"cat\": \"R\", \"txt\": \"83. Componer  un  grifo  que  tiene  una  fuga\"}, {\"num\": 84, \"sec\": \"2. Habilidades\", \"cat\": \"R\", \"txt\": \"84. N\u00famero  Total  de  Letras  S\"}, {\"num\": 85, \"sec\": \"2. Habilidades\", \"cat\": \"I\", \"txt\": \"85. Entender  la  vida  media  de  un  elemento  radioactivo\"}, {\"num\": 86, \"sec\": \"2. Habilidades\", \"cat\": \"I\", \"txt\": \"86. Describir  la  funci\u00f3n  de  los  gl\u00f3bulos  blancos\"}, {\"num\": 87, \"sec\": \"2. Habilidades\", \"cat\": \"I\", \"txt\": \"87. Escribir  un  reporte  cient\u00edfico  o  de  gran  erudici\u00f3n\"}, {\"num\": 88, \"sec\": \"2. Habilidades\", \"cat\": \"I\", \"txt\": \"88. Interpretar  formulas  qu\u00edmicas  sencillas\"}, {\"num\": 89, \"sec\": \"2. Habilidades\", \"cat\": \"I\", \"txt\": \"89. Usar  una  computadora  para  analizar  datos\"}, {\"num\": 90, \"sec\": \"2. Habilidades\", \"cat\": \"I\", \"txt\": \"90. Entender  por  qu\u00e9  no  caen  a  la  tierra  los  sat\u00e9lites  artificiales\"}, {\"num\": 91, \"sec\": \"2. Habilidades\", \"cat\": \"I\", \"txt\": \"91. Llevar  a  cabo  un  experimento  cient\u00edfico\"}, {\"num\": 92, \"sec\": \"2. Habilidades\", \"cat\": \"I\", \"txt\": \"92. Explicar  c\u00f3mo  funciona  una  computadora\"}, {\"num\": 93, \"sec\": \"2. Habilidades\", \"cat\": \"I\", \"txt\": \"93. Usar  un  microscopio\"}, {\"num\": 94, \"sec\": \"2. Habilidades\", \"cat\": \"I\", \"txt\": \"94. Entender  la  tabla  peri\u00f3dica  de  los  elementos\"}, {\"num\": 95, \"sec\": \"2. Habilidades\", \"cat\": \"I\", \"txt\": \"95. Explicar  porque  algunos  jabones  flotan  y  otros  se  hunden\"}, {\"num\": 96, \"sec\": \"2. Habilidades\", \"cat\": \"I\", \"txt\": \"96. N\u00famero  Total  de  Letras  S\"}, {\"num\": 97, \"sec\": \"2. Habilidades\", \"cat\": \"A\", \"txt\": \"97. Tocar  un  instrumento  musical\"}, {\"num\": 98, \"sec\": \"2. Habilidades\", \"cat\": \"A\", \"txt\": \"98. Participar  en  un  canto  coral  de  dos  o  cuatro  voces\"}, {\"num\": 99, \"sec\": \"2. Habilidades\", \"cat\": \"A\", \"txt\": \"99. Hacer  una  pintura,  una  acuarela  o  una  escultura\"}, {\"num\": 100, \"sec\": \"2. Habilidades\", \"cat\": \"A\", \"txt\": \"100. Hacer  arreglos  o  composiciones  musicales\"}, {\"num\": 101, \"sec\": \"2. Habilidades\", \"cat\": \"A\", \"txt\": \"101. Dise\u00f1ar  ropa,  carteles  o  muebles\"}, {\"num\": 102, \"sec\": \"2. Habilidades\", \"cat\": \"A\", \"txt\": \"102. Crear  la  representaci\u00f3n  art\u00edstica  de  un  concepto  o  idea\"}, {\"num\": 103, \"sec\": \"2. Habilidades\", \"cat\": \"A\", \"txt\": \"103. Escribir  bien  cuentos  o  poemas\"}, {\"num\": 104, \"sec\": \"2. Habilidades\", \"cat\": \"A\", \"txt\": \"104. Presentarme  como  solista  musical\"}, {\"num\": 105, \"sec\": \"2. Habilidades\", \"cat\": \"A\", \"txt\": \"105. Dar  una  pl\u00e1tica  entretenida\"}, {\"num\": 106, \"sec\": \"2. Habilidades\", \"cat\": \"A\", \"txt\": \"106. Publicar  un  cuento,  poema  o  ensayo  en  el  peri\u00f3dico  escolar  o  en  alguna  otra  publicaci\u00f3n\"}, {\"num\": 107, \"sec\": \"2. Habilidades\", \"cat\": \"A\", \"txt\": \"107. Estar  en  una  banda  de  m\u00fasica,  orquesta  o  coro\"}, {\"num\": 108, \"sec\": \"2. Habilidades\", \"cat\": \"S\", \"txt\": \"108. Ayudar  a  personas  que  est\u00e9n  alteradas  o  afligidas\"}, {\"num\": 109, \"sec\": \"2. Habilidades\", \"cat\": \"S\", \"txt\": \"109. Ense\u00f1ar  con  facilidad  a  los  ni\u00f1os\"}, {\"num\": 110, \"sec\": \"2. Habilidades\", \"cat\": \"S\", \"txt\": \"110. Cooperar  y  trabajar  bien  con  los  dem\u00e1s\"}, {\"num\": 111, \"sec\": \"2. Habilidades\", \"cat\": \"S\", \"txt\": \"111. Reconocer  las  fortalezas  y  debilidades  de  las  personas\"}, {\"num\": 112, \"sec\": \"2. Habilidades\", \"cat\": \"S\", \"txt\": \"112. Calmar  a  la  gente  cuando  est\u00e1  alterada\"}, {\"num\": 113, \"sec\": \"2. Habilidades\", \"cat\": \"S\", \"txt\": \"113. Trabajar  con  otros  en  un  proyecto  de  equipo\"}, {\"num\": 114, \"sec\": \"2. Habilidades\", \"cat\": \"S\", \"txt\": \"114. Hacer  sentir  c\u00f3moda  a  la  gente\"}, {\"num\": 115, \"sec\": \"2. Habilidades\", \"cat\": \"S\", \"txt\": \"115. Dar  clases  a  otros\"}, {\"num\": 116, \"sec\": \"2. Habilidades\", \"cat\": \"S\", \"txt\": \"116. Tener  una  buena  comprensi\u00f3n  de  las  relaciones  sociales\"}, {\"num\": 117, \"sec\": \"2. Habilidades\", \"cat\": \"S\", \"txt\": \"117. Escuchar  a  la  gente\"}, {\"num\": 118, \"sec\": \"2. Habilidades\", \"cat\": \"S\", \"txt\": \"118. Hacer  que  la  gente  me  busque  para  contarme  sus  problemas\"}, {\"num\": 119, \"sec\": \"2. Habilidades\", \"cat\": \"S\", \"txt\": \"119. N\u00famero  Total  de  Letras  S\"}, {\"num\": 120, \"sec\": \"2. Habilidades\", \"cat\": \"E\", \"txt\": \"120. Ser  un  buen  vendedor\"}, {\"num\": 121, \"sec\": \"2. Habilidades\", \"cat\": \"E\", \"txt\": \"121. Planear  una  estrategia  para  lograr  una  meta\"}, {\"num\": 122, \"sec\": \"2. Habilidades\", \"cat\": \"E\", \"txt\": \"122. Ser  un  l\u00edder  exitoso\"}, {\"num\": 123, \"sec\": \"2. Habilidades\", \"cat\": \"E\", \"txt\": \"123. Ser  un  buen  orador\"}, {\"num\": 124, \"sec\": \"2. Habilidades\", \"cat\": \"E\", \"txt\": \"124. Administrar  una  campa\u00f1a  de  ventas\"}, {\"num\": 125, \"sec\": \"2. Habilidades\", \"cat\": \"E\", \"txt\": \"125. Organizar  el  trabajo  de  otros\"}, {\"num\": 126, \"sec\": \"2. Habilidades\", \"cat\": \"E\", \"txt\": \"126. Ser  bueno  en  los  debates\"}, {\"num\": 127, \"sec\": \"2. Habilidades\", \"cat\": \"E\", \"txt\": \"127. Supervisar  el  trabajo  de  otros\"}, {\"num\": 128, \"sec\": \"2. Habilidades\", \"cat\": \"E\", \"txt\": \"128. Empezar  mi  propio  negocio\"}, {\"num\": 129, \"sec\": \"2. Habilidades\", \"cat\": \"E\", \"txt\": \"129. Ser  el  vocero  de  un  sal\u00f3n  de  clases  o  grupo\"}, {\"num\": 130, \"sec\": \"2. Habilidades\", \"cat\": \"E\", \"txt\": \"130. Ser  una  persona  ambiciosa\"}, {\"num\": 131, \"sec\": \"2. Habilidades\", \"cat\": \"E\", \"txt\": \"131. N\u00famero  Total  de  Letras  S\"}, {\"num\": 132, \"sec\": \"2. Habilidades\", \"cat\": \"C\", \"txt\": \"132. Usar  una  copiadora\"}, {\"num\": 133, \"sec\": \"2. Habilidades\", \"cat\": \"C\", \"txt\": \"133. Archivar  correspondencia  y  otros  documentos\"}, {\"num\": 134, \"sec\": \"2. Habilidades\", \"cat\": \"C\", \"txt\": \"134. Hacer  mucho  papeleo  en  un  tiempo  corto\"}, {\"num\": 135, \"sec\": \"2. Habilidades\", \"cat\": \"C\", \"txt\": \"135. Llevar  registro  precisos  de  pagos  y  ventas\"}, {\"num\": 136, \"sec\": \"2. Habilidades\", \"cat\": \"C\", \"txt\": \"136. Transcribir  de  un  dict\u00e1fono\"}, {\"num\": 137, \"sec\": \"2. Habilidades\", \"cat\": \"C\", \"txt\": \"137. Obtener  informaci\u00f3n  por  tel\u00e9fono\"}, {\"num\": 138, \"sec\": \"2. Habilidades\", \"cat\": \"C\", \"txt\": \"138. Utilizar  un  procesador  de  textos\"}, {\"num\": 139, \"sec\": \"2. Habilidades\", \"cat\": \"C\", \"txt\": \"139. Tener  un  empleo  de  oficina\"}, {\"num\": 140, \"sec\": \"2. Habilidades\", \"cat\": \"C\", \"txt\": \"140. Usar  una  computadora  para  analizar  datos  empresariales\"}, {\"num\": 141, \"sec\": \"2. Habilidades\", \"cat\": \"C\", \"txt\": \"141. Dar  el  cambio  correcto  de  manera  r\u00e1pida\"}, {\"num\": 142, \"sec\": \"2. Habilidades\", \"cat\": \"C\", \"txt\": \"142. Encontrar  errores  en  el  trabajo  de  los  dem\u00e1s\"}, {\"num\": 143, \"sec\": \"2. Habilidades\", \"cat\": \"C\", \"txt\": \"143. N\u00famero  Total  de  Letras  S\"}, {\"num\": 144, \"sec\": \"3. Ocupaciones\", \"cat\": \"R\", \"txt\": \"144. Mec\u00e1nico  automotriz  \u2013  arregla  autom\u00f3viles\"}, {\"num\": 145, \"sec\": \"3. Ocupaciones\", \"cat\": \"R\", \"txt\": \"145. Carpintero  \u2013  construye  cosas  con  madera\"}, {\"num\": 146, \"sec\": \"3. Ocupaciones\", \"cat\": \"R\", \"txt\": \"146. Inspector  de  construcciones  \u2013  inspecciona  edificios  nuevos  para  ver  si  est\u00e1n  bien  construidos\"}, {\"num\": 147, \"sec\": \"3. Ocupaciones\", \"cat\": \"R\", \"txt\": \"147. Radiooperador  \u2013  manda  y  recibe  mensajes  de  radio\"}, {\"num\": 148, \"sec\": \"3. Ocupaciones\", \"cat\": \"R\", \"txt\": \"148. Agricultor  \u2013  levanta  cosechas\"}, {\"num\": 149, \"sec\": \"3. Ocupaciones\", \"cat\": \"R\", \"txt\": \"149. Mec\u00e1nico  aeron\u00e1utico  \u2013  arregla  aviones\"}, {\"num\": 150, \"sec\": \"3. Ocupaciones\", \"cat\": \"R\", \"txt\": \"150. Bombero  \u2013  extingue  y  ayuda  a  prevenir  incendios\"}, {\"num\": 151, \"sec\": \"3. Ocupaciones\", \"cat\": \"R\", \"txt\": \"151. Conductor  de  camiones  en  distancias  largas  \u2013  manejar  una  ruta  de  autobuses  o  tr\u00e1ileres\"}, {\"num\": 152, \"sec\": \"3. Ocupaciones\", \"cat\": \"R\", \"txt\": \"152. Mec\u00e1nico  \u2013  construye,  repara  o  trabaja  con  maquinaria\"}, {\"num\": 153, \"sec\": \"3. Ocupaciones\", \"cat\": \"R\", \"txt\": \"153. Electricista  \u2013  arregla  el  cableado  el\u00e9ctrico  en  edificios  o  maquinas\"}, {\"num\": 154, \"sec\": \"3. Ocupaciones\", \"cat\": \"R\", \"txt\": \"154. T\u00e9cnico  en  electr\u00f3nico  \u2013  construye,  prueba  y  arregla  equipos  electr\u00f3nicos\"}, {\"num\": 155, \"sec\": \"3. Ocupaciones\", \"cat\": \"R\", \"txt\": \"155. Carpintero  \u2013  construye  muebles  para  casas  o  edificios\"}, {\"num\": 156, \"sec\": \"3. Ocupaciones\", \"cat\": \"R\", \"txt\": \"156. N\u00famero  Total  de  Letras  S\"}, {\"num\": 157, \"sec\": \"3. Ocupaciones\", \"cat\": \"I\", \"txt\": \"157. Bi\u00f3logo  \u2013  estudia  plantas  y  animales\"}, {\"num\": 158, \"sec\": \"3. Ocupaciones\", \"cat\": \"I\", \"txt\": \"158. T\u00e9cnico  laboratorista  medico  \u2013  trabaja  con  equipos  m\u00e9dicos\"}, {\"num\": 159, \"sec\": \"3. Ocupaciones\", \"cat\": \"I\", \"txt\": \"159. Antrop\u00f3logo  \u2013  estudia  culturas  diversas\"}, {\"num\": 160, \"sec\": \"3. Ocupaciones\", \"cat\": \"I\", \"txt\": \"160. Qu\u00edmico  \u2013  estudia  y  hace  sustancias  qu\u00edmicas\"}, {\"num\": 161, \"sec\": \"3. Ocupaciones\", \"cat\": \"I\", \"txt\": \"161. Investigador  cient\u00edfico  \u2013  ayuda  a  encontrar  las  respuestas  a  preguntas  cient\u00edficas\"}, {\"num\": 162, \"sec\": \"3. Ocupaciones\", \"cat\": \"I\", \"txt\": \"162. Cirujano  \u2013  realiza  operaciones  medicas\"}, {\"num\": 163, \"sec\": \"3. Ocupaciones\", \"cat\": \"I\", \"txt\": \"163. Investigador  en  ciencias  sociales  \u2013  estudia  problemas  sociales\"}, {\"num\": 164, \"sec\": \"3. Ocupaciones\", \"cat\": \"I\", \"txt\": \"164. F\u00edsico  \u2013  estudia  las  leyes  de  la  naturaleza,  como  la  ley  de  la  gravedad\"}, {\"num\": 165, \"sec\": \"3. Ocupaciones\", \"cat\": \"I\", \"txt\": \"165. Meteor\u00f3logo  \u2013  estudia  el  clima\"}, {\"num\": 166, \"sec\": \"3. Ocupaciones\", \"cat\": \"I\", \"txt\": \"166. Astr\u00f3nomo  \u2013  estudia  el  sistema  solar\"}, {\"num\": 167, \"sec\": \"3. Ocupaciones\", \"cat\": \"I\", \"txt\": \"167. Zo\u00f3logo  \u2013  estudia  la  historia  de  los  animales\"}, {\"num\": 168, \"sec\": \"3. Ocupaciones\", \"cat\": \"I\", \"txt\": \"168. Ge\u00f3logo  \u2013  estudia  la  historia  del  planeta  tierra\"}, {\"num\": 169, \"sec\": \"3. Ocupaciones\", \"cat\": \"I\", \"txt\": \"169. N\u00famero  Total  de  Letras  S\"}, {\"num\": 170, \"sec\": \"3. Ocupaciones\", \"cat\": \"A\", \"txt\": \"170. Poeta  -   escribe  poemas\"}, {\"num\": 171, \"sec\": \"3. Ocupaciones\", \"cat\": \"A\", \"txt\": \"171. Artista  pl\u00e1stico  \u2013  crea  pinturas,   dibujos  y  otros  tipos  de  artes\"}, {\"num\": 172, \"sec\": \"3. Ocupaciones\", \"cat\": \"A\", \"txt\": \"172. Dramaturgo  \u2013  escribe  obras  de  teatro\"}, {\"num\": 173, \"sec\": \"3. Ocupaciones\", \"cat\": \"A\", \"txt\": \"173. M\u00fasico  \u2013  toca  un  instrumento  musical\"}, {\"num\": 174, \"sec\": \"3. Ocupaciones\", \"cat\": \"A\", \"txt\": \"174. Actor  \u2013  trabaja  en  una  obra  de  teatro,  espect\u00e1culo  o  pel\u00edcula\"}, {\"num\": 175, \"sec\": \"3. Ocupaciones\", \"cat\": \"A\", \"txt\": \"175. Cantante  \u2013  canta  frente  al  publico\"}, {\"num\": 176, \"sec\": \"3. Ocupaciones\", \"cat\": \"A\", \"txt\": \"176. Compositor  \u2013  escribe  canciones  o  musicales\"}, {\"num\": 177, \"sec\": \"3. Ocupaciones\", \"cat\": \"A\", \"txt\": \"177. Escultor  \u2013  crea  esculturas  o  estatuas\"}, {\"num\": 178, \"sec\": \"3. Ocupaciones\", \"cat\": \"A\", \"txt\": \"178. Artista  de  espect\u00e1culos  -   canta,  baila,  cuenta  chistes\"}, {\"num\": 179, \"sec\": \"3. Ocupaciones\", \"cat\": \"A\", \"txt\": \"179. Escritor  \u2013  escribe  libros,  art\u00edculos  o  cuentos\"}, {\"num\": 180, \"sec\": \"3. Ocupaciones\", \"cat\": \"A\", \"txt\": \"180. Maestro  de  teatro  \u2013  ense\u00f1a  t\u00e9cnicas  de  actuaci\u00f3n  a  actores\"}, {\"num\": 181, \"sec\": \"3. Ocupaciones\", \"cat\": \"A\", \"txt\": \"181. Fot\u00f3grafo  \u2013  toma  fotograf\u00edas\"}, {\"num\": 182, \"sec\": \"3. Ocupaciones\", \"cat\": \"A\", \"txt\": \"182. N\u00famero  Total  de  Letras  S\"}, {\"num\": 183, \"sec\": \"3. Ocupaciones\", \"cat\": \"S\", \"txt\": \"183. Consejero  matrimonial  \u2013  ayuda  a  las  parejas  con  sus  problemas\"}, {\"num\": 184, \"sec\": \"3. Ocupaciones\", \"cat\": \"S\", \"txt\": \"184. Director  de  una  agencia  de  beneficencia  \u2013  supervisa  a  trabajadores  que  ayudan  a  la  gente  necesitada\"}, {\"num\": 185, \"sec\": \"3. Ocupaciones\", \"cat\": \"S\", \"txt\": \"185. Director  de  campamento  juvenil  \u2013  supervisa  los  programas  y  trabajadores  de  un  campamento\"}, {\"num\": 186, \"sec\": \"3. Ocupaciones\", \"cat\": \"S\", \"txt\": \"186. Orientador  en  abuso  de  sustancias  \u2013  ayuda  a  las  personas  que  tienen  problemas  con  drogas  o  alcohol\"}, {\"num\": 187, \"sec\": \"3. Ocupaciones\", \"cat\": \"S\", \"txt\": \"187. Director  de  actividades  de  recreo  \u2013  organiza  actividades  recreacionales\"}, {\"num\": 188, \"sec\": \"3. Ocupaciones\", \"cat\": \"S\", \"txt\": \"188. Psic\u00f3logo  cl\u00ednico  \u2013  ayuda  a  gente  que  tiene  problemas  con  sus  sentimientos,  pensamientos  o  conductas\"}, {\"num\": 189, \"sec\": \"3. Ocupaciones\", \"cat\": \"S\", \"txt\": \"189. Trabajador  social  \u2013  ayuda  a  gente  con  problemas  en  su  familia,  trabajo  o  amigos\"}, {\"num\": 190, \"sec\": \"3. Ocupaciones\", \"cat\": \"S\", \"txt\": \"190. Auxiliar  de  enfermer\u00eda  \u2013  ayuda  en  el  cuidado  de  pacientes\"}, {\"num\": 191, \"sec\": \"3. Ocupaciones\", \"cat\": \"S\", \"txt\": \"191. Maestro  \u2013  da  clases  en  una  escuela\"}, {\"num\": 192, \"sec\": \"3. Ocupaciones\", \"cat\": \"S\", \"txt\": \"192. Asistente  social  de  libertad  condicional  \u2013  ayuda  a  las  personas  que  han  tenido  problemas  con  la  ley\"}, {\"num\": 193, \"sec\": \"3. Ocupaciones\", \"cat\": \"S\", \"txt\": \"193. Orientador  escolar  \u2013  ayuda  a  alumnos  con  problemas\"}, {\"num\": 194, \"sec\": \"3. Ocupaciones\", \"cat\": \"S\", \"txt\": \"194. Asistente  m\u00e9dico  \u2013  examina  pacientes  en  un  consultorio  medico\"}, {\"num\": 195, \"sec\": \"3. Ocupaciones\", \"cat\": \"S\", \"txt\": \"195. N\u00famero  Total  de  Letras  S\"}, {\"num\": 196, \"sec\": \"3. Ocupaciones\", \"cat\": \"E\", \"txt\": \"196. Inversionista  \u2013  invierte  dinero  en  tratos  de  negocios\"}, {\"num\": 197, \"sec\": \"3. Ocupaciones\", \"cat\": \"E\", \"txt\": \"197. Vendedor  \u2013  vende  bienes  o  servicios\"}, {\"num\": 198, \"sec\": \"3. Ocupaciones\", \"cat\": \"E\", \"txt\": \"198. Gerente  de  ventas  \u2013  supervise  un  equipo  de  vendedores\"}, {\"num\": 199, \"sec\": \"3. Ocupaciones\", \"cat\": \"E\", \"txt\": \"199. Director  de  mercadotecnia  \u2013  planea  programas  de  comercializaci\u00f3n\"}, {\"num\": 200, \"sec\": \"3. Ocupaciones\", \"cat\": \"E\", \"txt\": \"200. Representante  de  ventas  \u2013  vende  productos  a  otras  empresas\"}, {\"num\": 201, \"sec\": \"3. Ocupaciones\", \"cat\": \"E\", \"txt\": \"201. Comprador  \u2013  decide  que  productos  va  a  vender  un  almac\u00e9n\"}, {\"num\": 202, \"sec\": \"3. Ocupaciones\", \"cat\": \"E\", \"txt\": \"202. Agente  de  bienes  ra\u00edces  \u2013  vende  casas  y  terrenos\"}, {\"num\": 203, \"sec\": \"3. Ocupaciones\", \"cat\": \"E\", \"txt\": \"203. Gerente  de  estaci\u00f3n  televisiva  \u2013  dirige  una  estaci\u00f3n  de  televisi\u00f3n\"}, {\"num\": 204, \"sec\": \"3. Ocupaciones\", \"cat\": \"E\", \"txt\": \"204. Corredor  de  bolsas  \u2013  compra  y  vende  acciones  y  bonos\"}, {\"num\": 205, \"sec\": \"3. Ocupaciones\", \"cat\": \"E\", \"txt\": \"205. Ejecutivo  empresarial  \u2013  supervise  a  mucha  gente  en  una  empresa\"}, {\"num\": 206, \"sec\": \"3. Ocupaciones\", \"cat\": \"E\", \"txt\": \"206. Funcionario  gubernamental  \u2013  detenta  un  cargo  p\u00fablico\"}, {\"num\": 207, \"sec\": \"3. Ocupaciones\", \"cat\": \"E\", \"txt\": \"207. Gerente  \u2013  supervise  un  grupo  de  trabajadores\"}, {\"num\": 208, \"sec\": \"3. Ocupaciones\", \"cat\": \"E\", \"txt\": \"208. N\u00famero  Total  de  Letras  S\"}, {\"num\": 209, \"sec\": \"3. Ocupaciones\", \"cat\": \"C\", \"txt\": \"209. T\u00e9cnico  en  contabilidad  \u2013  lleva  cuenta  del  dinero  en  un  negocio\"}, {\"num\": 210, \"sec\": \"3. Ocupaciones\", \"cat\": \"C\", \"txt\": \"210. Revisor  presupuestal  \u2013  ayuda  a  una  empresa  a  decidir  c\u00f3mo  gastar  y  ahorrar  dinero\"}, {\"num\": 211, \"sec\": \"3. Ocupaciones\", \"cat\": \"C\", \"txt\": \"211. Contador  p\u00fablico  \u2013  lleva  cuenta  de  transacciones  financieras\"}, {\"num\": 212, \"sec\": \"3. Ocupaciones\", \"cat\": \"C\", \"txt\": \"212. Jefe  de  almac\u00e9n  \u2013  lleva  inventario  de  suministros  o  mercanc\u00eda\"}, {\"num\": 213, \"sec\": \"3. Ocupaciones\", \"cat\": \"C\", \"txt\": \"213. Capturista  \u2013  ingresa  informaci\u00f3n  en  una  computadora\"}, {\"num\": 214, \"sec\": \"3. Ocupaciones\", \"cat\": \"C\", \"txt\": \"214. Administrador  de  nominas  \u2013  se  asegura  que  los  trabajadores  reciban  sus  sueldos  por  la  cantidad  correcta\"}, {\"num\": 215, \"sec\": \"3. Ocupaciones\", \"cat\": \"S\", \"txt\": \"215. N  Examinador  bancario  \u2013  revisa  registros  bancarios  para  detectar  errores\"}, {\"num\": 216, \"sec\": \"3. Ocupaciones\", \"cat\": \"S\", \"txt\": \"216. Secretario  \u2013  ayuda  a  su  jefe  con  el  trabajo  de  oficina\"}, {\"num\": 217, \"sec\": \"3. Ocupaciones\", \"cat\": \"S\", \"txt\": \"217. Asesor  fiscal  \u2013  calcula  la  cantidad  de  impuestos  que  se  deben\"}, {\"num\": 218, \"sec\": \"3. Ocupaciones\", \"cat\": \"S\", \"txt\": \"218. Analista  financiero  \u2013  ayuda  a  una  empresa  a  invertir  dinero\"}, {\"num\": 219, \"sec\": \"3. Ocupaciones\", \"cat\": \"S\", \"txt\": \"219. Corrector  de  estilo  \u2013  revisa  material  escrito  para  detectar  errores\"}, {\"num\": 220, \"sec\": \"3. Ocupaciones\", \"cat\": \"S\", \"txt\": \"220. Cajero  bancario  \u2013  ayuda  los  clientes  del  banco\"}, {\"num\": 221, \"sec\": \"3. Ocupaciones\", \"cat\": \"S\", \"txt\": \"221. N\u00famero  Total  de  Letras  S\"}]",
        json.dumps({"dimensiones": ["R", "I", "A", "S", "E", "C"]})
    )
    cursor.execute("""
        INSERT INTO tests_definiciones 
        (code, nombre, siglas, categoria, descripcion, instrucciones, escala_opciones_json, items_json, reglas_correccion_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(code) DO UPDATE SET
            nombre=excluded.nombre,
            descripcion=excluded.descripcion,
            instrucciones=excluded.instrucciones,
            escala_opciones_json=excluded.escala_opciones_json,
            items_json=excluded.items_json,
            reglas_correccion_json=excluded.reglas_correccion_json
    """, holland_def)
    db.commit()

    # Asegurar la definición e inserción del RAVEN
    raven_def = (
        "RAVEN",
        "Test de Matrices Progresivas de Raven (Escala General)",
        "RAVEN",
        "Capacidad Intelectual / Razonamiento No Verbal",
        "Evaluación psicométrica estandarizada de razonamiento analógico y capacidad intelectual no verbal de 60 matrices divididas en 5 series (A, B, C, D, E).",
        "Observe atentamente cada matriz superior y elija la opción numérica (1-6 o 1-8) que complete correctamente el patrón gráfico.",
        json.dumps([]),
        "[{\"num\": 1, \"code\": \"A1\", \"serie\": \"A\", \"img\": \"/static/img/raven/A1.png\", \"txt\": \"Matriz A1\", \"opciones_count\": 6}, {\"num\": 2, \"code\": \"A2\", \"serie\": \"A\", \"img\": \"/static/img/raven/A2.png\", \"txt\": \"Matriz A2\", \"opciones_count\": 6}, {\"num\": 3, \"code\": \"A3\", \"serie\": \"A\", \"img\": \"/static/img/raven/A3.png\", \"txt\": \"Matriz A3\", \"opciones_count\": 6}, {\"num\": 4, \"code\": \"A4\", \"serie\": \"A\", \"img\": \"/static/img/raven/A4.png\", \"txt\": \"Matriz A4\", \"opciones_count\": 6}, {\"num\": 5, \"code\": \"A5\", \"serie\": \"A\", \"img\": \"/static/img/raven/A5.png\", \"txt\": \"Matriz A5\", \"opciones_count\": 6}, {\"num\": 6, \"code\": \"A6\", \"serie\": \"A\", \"img\": \"/static/img/raven/A6.png\", \"txt\": \"Matriz A6\", \"opciones_count\": 6}, {\"num\": 7, \"code\": \"A7\", \"serie\": \"A\", \"img\": \"/static/img/raven/A7.png\", \"txt\": \"Matriz A7\", \"opciones_count\": 6}, {\"num\": 8, \"code\": \"A8\", \"serie\": \"A\", \"img\": \"/static/img/raven/A8.png\", \"txt\": \"Matriz A8\", \"opciones_count\": 6}, {\"num\": 9, \"code\": \"A9\", \"serie\": \"A\", \"img\": \"/static/img/raven/A9.png\", \"txt\": \"Matriz A9\", \"opciones_count\": 6}, {\"num\": 10, \"code\": \"A10\", \"serie\": \"A\", \"img\": \"/static/img/raven/A10.png\", \"txt\": \"Matriz A10\", \"opciones_count\": 6}, {\"num\": 11, \"code\": \"A11\", \"serie\": \"A\", \"img\": \"/static/img/raven/A11.png\", \"txt\": \"Matriz A11\", \"opciones_count\": 6}, {\"num\": 12, \"code\": \"A12\", \"serie\": \"A\", \"img\": \"/static/img/raven/A12.png\", \"txt\": \"Matriz A12\", \"opciones_count\": 6}, {\"num\": 13, \"code\": \"B1\", \"serie\": \"B\", \"img\": \"/static/img/raven/B1.png\", \"txt\": \"Matriz B1\", \"opciones_count\": 6}, {\"num\": 14, \"code\": \"B2\", \"serie\": \"B\", \"img\": \"/static/img/raven/B2.png\", \"txt\": \"Matriz B2\", \"opciones_count\": 6}, {\"num\": 15, \"code\": \"B3\", \"serie\": \"B\", \"img\": \"/static/img/raven/B3.png\", \"txt\": \"Matriz B3\", \"opciones_count\": 6}, {\"num\": 16, \"code\": \"B4\", \"serie\": \"B\", \"img\": \"/static/img/raven/B4.png\", \"txt\": \"Matriz B4\", \"opciones_count\": 6}, {\"num\": 17, \"code\": \"B5\", \"serie\": \"B\", \"img\": \"/static/img/raven/B5.png\", \"txt\": \"Matriz B5\", \"opciones_count\": 6}, {\"num\": 18, \"code\": \"B6\", \"serie\": \"B\", \"img\": \"/static/img/raven/B6.png\", \"txt\": \"Matriz B6\", \"opciones_count\": 6}, {\"num\": 19, \"code\": \"B7\", \"serie\": \"B\", \"img\": \"/static/img/raven/B7.png\", \"txt\": \"Matriz B7\", \"opciones_count\": 6}, {\"num\": 20, \"code\": \"B8\", \"serie\": \"B\", \"img\": \"/static/img/raven/B8.png\", \"txt\": \"Matriz B8\", \"opciones_count\": 6}, {\"num\": 21, \"code\": \"B9\", \"serie\": \"B\", \"img\": \"/static/img/raven/B9.png\", \"txt\": \"Matriz B9\", \"opciones_count\": 6}, {\"num\": 22, \"code\": \"B10\", \"serie\": \"B\", \"img\": \"/static/img/raven/B10.png\", \"txt\": \"Matriz B10\", \"opciones_count\": 6}, {\"num\": 23, \"code\": \"B11\", \"serie\": \"B\", \"img\": \"/static/img/raven/B11.png\", \"txt\": \"Matriz B11\", \"opciones_count\": 6}, {\"num\": 24, \"code\": \"B12\", \"serie\": \"B\", \"img\": \"/static/img/raven/B12.png\", \"txt\": \"Matriz B12\", \"opciones_count\": 6}, {\"num\": 25, \"code\": \"C1\", \"serie\": \"C\", \"img\": \"/static/img/raven/C1.png\", \"txt\": \"Matriz C1\", \"opciones_count\": 8}, {\"num\": 26, \"code\": \"C2\", \"serie\": \"C\", \"img\": \"/static/img/raven/C2.png\", \"txt\": \"Matriz C2\", \"opciones_count\": 8}, {\"num\": 27, \"code\": \"C3\", \"serie\": \"C\", \"img\": \"/static/img/raven/C3.png\", \"txt\": \"Matriz C3\", \"opciones_count\": 8}, {\"num\": 28, \"code\": \"C4\", \"serie\": \"C\", \"img\": \"/static/img/raven/C4.png\", \"txt\": \"Matriz C4\", \"opciones_count\": 8}, {\"num\": 29, \"code\": \"C5\", \"serie\": \"C\", \"img\": \"/static/img/raven/C5.png\", \"txt\": \"Matriz C5\", \"opciones_count\": 8}, {\"num\": 30, \"code\": \"C6\", \"serie\": \"C\", \"img\": \"/static/img/raven/C6.png\", \"txt\": \"Matriz C6\", \"opciones_count\": 8}, {\"num\": 31, \"code\": \"C7\", \"serie\": \"C\", \"img\": \"/static/img/raven/C7.png\", \"txt\": \"Matriz C7\", \"opciones_count\": 8}, {\"num\": 32, \"code\": \"C8\", \"serie\": \"C\", \"img\": \"/static/img/raven/C8.png\", \"txt\": \"Matriz C8\", \"opciones_count\": 8}, {\"num\": 33, \"code\": \"C9\", \"serie\": \"C\", \"img\": \"/static/img/raven/C9.png\", \"txt\": \"Matriz C9\", \"opciones_count\": 8}, {\"num\": 34, \"code\": \"C10\", \"serie\": \"C\", \"img\": \"/static/img/raven/C10.png\", \"txt\": \"Matriz C10\", \"opciones_count\": 8}, {\"num\": 35, \"code\": \"C11\", \"serie\": \"C\", \"img\": \"/static/img/raven/C11.png\", \"txt\": \"Matriz C11\", \"opciones_count\": 8}, {\"num\": 36, \"code\": \"C12\", \"serie\": \"C\", \"img\": \"/static/img/raven/C12.png\", \"txt\": \"Matriz C12\", \"opciones_count\": 8}, {\"num\": 37, \"code\": \"D1\", \"serie\": \"D\", \"img\": \"/static/img/raven/D1.png\", \"txt\": \"Matriz D1\", \"opciones_count\": 8}, {\"num\": 38, \"code\": \"D2\", \"serie\": \"D\", \"img\": \"/static/img/raven/D2.png\", \"txt\": \"Matriz D2\", \"opciones_count\": 8}, {\"num\": 39, \"code\": \"D3\", \"serie\": \"D\", \"img\": \"/static/img/raven/D3.png\", \"txt\": \"Matriz D3\", \"opciones_count\": 8}, {\"num\": 40, \"code\": \"D4\", \"serie\": \"D\", \"img\": \"/static/img/raven/D4.png\", \"txt\": \"Matriz D4\", \"opciones_count\": 8}, {\"num\": 41, \"code\": \"D5\", \"serie\": \"D\", \"img\": \"/static/img/raven/D5.png\", \"txt\": \"Matriz D5\", \"opciones_count\": 8}, {\"num\": 42, \"code\": \"D6\", \"serie\": \"D\", \"img\": \"/static/img/raven/D6.png\", \"txt\": \"Matriz D6\", \"opciones_count\": 8}, {\"num\": 43, \"code\": \"D7\", \"serie\": \"D\", \"img\": \"/static/img/raven/D7.png\", \"txt\": \"Matriz D7\", \"opciones_count\": 8}, {\"num\": 44, \"code\": \"D8\", \"serie\": \"D\", \"img\": \"/static/img/raven/D8.png\", \"txt\": \"Matriz D8\", \"opciones_count\": 8}, {\"num\": 45, \"code\": \"D9\", \"serie\": \"D\", \"img\": \"/static/img/raven/D9.png\", \"txt\": \"Matriz D9\", \"opciones_count\": 8}, {\"num\": 46, \"code\": \"D10\", \"serie\": \"D\", \"img\": \"/static/img/raven/D10.png\", \"txt\": \"Matriz D10\", \"opciones_count\": 8}, {\"num\": 47, \"code\": \"D11\", \"serie\": \"D\", \"img\": \"/static/img/raven/D11.png\", \"txt\": \"Matriz D11\", \"opciones_count\": 8}, {\"num\": 48, \"code\": \"D12\", \"serie\": \"D\", \"img\": \"/static/img/raven/D12.png\", \"txt\": \"Matriz D12\", \"opciones_count\": 8}, {\"num\": 49, \"code\": \"E1\", \"serie\": \"E\", \"img\": \"/static/img/raven/E1.png\", \"txt\": \"Matriz E1\", \"opciones_count\": 8}, {\"num\": 50, \"code\": \"E2\", \"serie\": \"E\", \"img\": \"/static/img/raven/E2.png\", \"txt\": \"Matriz E2\", \"opciones_count\": 8}, {\"num\": 51, \"code\": \"E3\", \"serie\": \"E\", \"img\": \"/static/img/raven/E3.png\", \"txt\": \"Matriz E3\", \"opciones_count\": 8}, {\"num\": 52, \"code\": \"E4\", \"serie\": \"E\", \"img\": \"/static/img/raven/E4.png\", \"txt\": \"Matriz E4\", \"opciones_count\": 8}, {\"num\": 53, \"code\": \"E5\", \"serie\": \"E\", \"img\": \"/static/img/raven/E5.png\", \"txt\": \"Matriz E5\", \"opciones_count\": 8}, {\"num\": 54, \"code\": \"E6\", \"serie\": \"E\", \"img\": \"/static/img/raven/E6.png\", \"txt\": \"Matriz E6\", \"opciones_count\": 8}, {\"num\": 55, \"code\": \"E7\", \"serie\": \"E\", \"img\": \"/static/img/raven/E7.png\", \"txt\": \"Matriz E7\", \"opciones_count\": 8}, {\"num\": 56, \"code\": \"E8\", \"serie\": \"E\", \"img\": \"/static/img/raven/E8.png\", \"txt\": \"Matriz E8\", \"opciones_count\": 8}, {\"num\": 57, \"code\": \"E9\", \"serie\": \"E\", \"img\": \"/static/img/raven/E9.png\", \"txt\": \"Matriz E9\", \"opciones_count\": 8}, {\"num\": 58, \"code\": \"E10\", \"serie\": \"E\", \"img\": \"/static/img/raven/E10.png\", \"txt\": \"Matriz E10\", \"opciones_count\": 8}, {\"num\": 59, \"code\": \"E11\", \"serie\": \"E\", \"img\": \"/static/img/raven/E11.png\", \"txt\": \"Matriz E11\", \"opciones_count\": 8}, {\"num\": 60, \"code\": \"E12\", \"serie\": \"E\", \"img\": \"/static/img/raven/E12.png\", \"txt\": \"Matriz E12\", \"opciones_count\": 8}]",
        json.dumps({"series": ["A", "B", "C", "D", "E"], "total_items": 60})
    )
    cursor.execute("""
        INSERT INTO tests_definiciones 
        (code, nombre, siglas, categoria, descripcion, instrucciones, escala_opciones_json, items_json, reglas_correccion_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(code) DO UPDATE SET
            nombre=excluded.nombre,
            descripcion=excluded.descripcion,
            instrucciones=excluded.instrucciones,
            escala_opciones_json=excluded.escala_opciones_json,
            items_json=excluded.items_json,
            reglas_correccion_json=excluded.reglas_correccion_json
    """, raven_def)
    db.commit()

    # Asegurar la definición e inserción del ASRS-ADHD
    adhd_def = (
        "ASRS-ADHD",
        "Inventario de Síntomas de TDAH en Adultos (ASRS v1.1 OMS)",
        "ASRS-ADHD",
        "Neurodesarrollo / TDAH Adulto",
        "Escala de Autoinforme de TDAH en Adultos de la OMS (18 ítems) para medir la severidad de síntomas de inatención e hiperactividad/impulsividad.",
        "Responda a las siguientes preguntas indicando con qué frecuencia ha experimentado cada síntoma durante los últimos 6 meses.",
        json.dumps([
            {"val": 0, "txt": "0 = Nunca"},
            {"val": 1, "txt": "1 = Raramente"},
            {"val": 2, "txt": "2 = Algunas veces"},
            {"val": 3, "txt": "3 = A menudo"},
            {"val": 4, "txt": "4 = Muy a menudo"}
        ]),
        "[{\"num\": 1, \"sec\": \"Parte A - Inatenci\u00f3n\", \"txt\": \"1. \u00bfCon qu\u00e9 frecuencia comete errores cuando tiene que trabajar en un proyecto aburrido o dif\u00edcil?\"}, {\"num\": 2, \"sec\": \"Parte A - Inatenci\u00f3n\", \"txt\": \"2. \u00bfCon qu\u00e9 frecuencia tiene dificultades para mantener su atenci\u00f3n cuando est\u00e1 aburrido o con un trabajo repetitivo?\"}, {\"num\": 3, \"sec\": \"Parte A - Inatenci\u00f3n\", \"txt\": \"3. \u00bfCon qu\u00e9 frecuencia tiene dificultades para concentrarse en cuestiones que otras personas le comunican aun cuando se dirijan directamente a usted?\"}, {\"num\": 4, \"sec\": \"Parte A - Inatenci\u00f3n\", \"txt\": \"4. \u00bfCon qu\u00e9 frecuencia tiene dificultades para concretar los detalles de un proyecto una vez que las partes m\u00e1s dif\u00edciles se han conseguido?\"}, {\"num\": 5, \"sec\": \"Parte A - Inatenci\u00f3n\", \"txt\": \"5. \u00bfCon qu\u00e9 frecuencia tiene dificultades en ordenar las cosas en una tarea que requiere organizaci\u00f3n?\"}, {\"num\": 6, \"sec\": \"Parte A - Inatenci\u00f3n\", \"txt\": \"6. Cuando tiene una tarea que requiere mucha reflexi\u00f3n, \u00bfcon qu\u00e9 frecuencia la evita o demora en iniciarla?\"}, {\"num\": 7, \"sec\": \"Parte A - Inatenci\u00f3n\", \"txt\": \"7. \u00bfCon qu\u00e9 frecuencia extrav\u00eda cosas o tiene dificultades para encontrarlas en su casa o en el trabajo?\"}, {\"num\": 8, \"sec\": \"Parte A - Inatenci\u00f3n\", \"txt\": \"8. \u00bfCon qu\u00e9 frecuencia se distrae por actividad o ruido a su alrededor?\"}, {\"num\": 9, \"sec\": \"Parte A - Inatenci\u00f3n\", \"txt\": \"9. \u00bfCon qu\u00e9 frecuencia tiene dificultades para recordar citas u obligaciones?\"}, {\"num\": 10, \"sec\": \"Parte B - Hiperactividad / Impulsividad\", \"txt\": \"10. \u00bfCon qu\u00e9 frecuencia se inquieta o mueve sus manos o pies cuando tiene que permanecer sentado durante largo tiempo?\"}, {\"num\": 11, \"sec\": \"Parte B - Hiperactividad / Impulsividad\", \"txt\": \"11. \u00bfCon qu\u00e9 frecuencia abandona su asiento en reuniones o en otras situaciones en las cuales debe permanecer sentado?\"}, {\"num\": 12, \"sec\": \"Parte B - Hiperactividad / Impulsividad\", \"txt\": \"12. \u00bfCon qu\u00e9 frecuencia tiene sensaci\u00f3n de inquietud?\"}, {\"num\": 13, \"sec\": \"Parte B - Hiperactividad / Impulsividad\", \"txt\": \"13. \u00bfCon qu\u00e9 frecuencia tiene dificultades para relajarse durante el tiempo libre?\"}, {\"num\": 14, \"sec\": \"Parte B - Hiperactividad / Impulsividad\", \"txt\": \"14. \u00bfCon qu\u00e9 frecuencia se nota forzado en realizar actividades, como impulsado por un motor?\"}, {\"num\": 15, \"sec\": \"Parte B - Hiperactividad / Impulsividad\", \"txt\": \"15. \u00bfCon qu\u00e9 frecuencia habla demasiado en ambientes sociales?\"}, {\"num\": 16, \"sec\": \"Parte B - Hiperactividad / Impulsividad\", \"txt\": \"16. Cuando mantiene una conversaci\u00f3n, \u00bfcon qu\u00e9 frecuencia interrumpe o termina la frase de las personas antes de que ellas concluyan?\"}, {\"num\": 17, \"sec\": \"Parte B - Hiperactividad / Impulsividad\", \"txt\": \"17. \u00bfCon qu\u00e9 frecuencia tiene dificultad para esperar su turno en situaciones que requieran una espera?\"}, {\"num\": 18, \"sec\": \"Parte B - Hiperactividad / Impulsividad\", \"txt\": \"18. \u00bfCon qu\u00e9 frecuencia interrumpe a los dem\u00e1s mientras est\u00e1n ocupados?\"}]",
        json.dumps({"partes": ["Parte A - Inatención", "Parte B - Hiperactividad / Impulsividad"], "cortes": [17, 24]})
    )
    cursor.execute("""
        INSERT INTO tests_definiciones 
        (code, nombre, siglas, categoria, descripcion, instrucciones, escala_opciones_json, items_json, reglas_correccion_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(code) DO UPDATE SET
            nombre=excluded.nombre,
            descripcion=excluded.descripcion,
            instrucciones=excluded.instrucciones,
            escala_opciones_json=excluded.escala_opciones_json,
            items_json=excluded.items_json,
            reglas_correccion_json=excluded.reglas_correccion_json
    """, adhd_def)
    db.commit()

    # Asegurar definiciones de AQ, RAADS-R y CAT-Q (Batería de Autismo/Neurodivergencia)
    aq_def = (
        "AQ",
        "Cociente de Espectro Autista (AQ - Baron-Cohen)",
        "AQ",
        "Neurodivergencia / TEA Adultos",
        "Cuestionario estandarizado de autoinforme de 50 ítems para medir rasgos autistas en adultos en 5 dimensiones clínicas.",
        "Responda a cada afirmación según su grado de acuerdo o desacuerdo general.",
        json.dumps([
            {"val": 1, "txt": "Totalmente de acuerdo"},
            {"val": 2, "txt": "Parcialmente de acuerdo"},
            {"val": 3, "txt": "Parcialmente en desacuerdo"},
            {"val": 4, "txt": "Totalmente en desacuerdo"}
        ]),
        "[{\"num\": 1, \"txt\": \"1. Prefiero hacer cosas con otras personas en lugar de hacerlas solo/a.\"}, {\"num\": 2, \"txt\": \"2. Prefiero hacer las cosas de la misma manera una y otra vez.\"}, {\"num\": 3, \"txt\": \"3. Si intento imaginar algo, me resulta muy f\u00e1cil construir una imagen mental.\"}, {\"num\": 4, \"txt\": \"4. Frecuentemente me fascina o absorbe tanto una actividad que pierdo de vista todo lo dem\u00e1s.\"}, {\"num\": 5, \"txt\": \"5. A menudo me fijo en peque\u00f1os sonidos que los dem\u00e1s no perciben.\"}, {\"num\": 6, \"txt\": \"6. Sol\u00eda prestar atenci\u00f3n a los n\u00fameros de las matr\u00edculas de los coches u otro tipo de informaci\u00f3n similar.\"}, {\"num\": 7, \"txt\": \"7. A menudo la gente me dice que lo que he dicho es maleducado, aunque a m\u00ed no me lo parezca.\"}, {\"num\": 8, \"txt\": \"8. Cuando leo una novela, me resulta f\u00e1cil imaginar el aspecto o la personalidad de los personajes.\"}, {\"num\": 9, \"txt\": \"9. Me fascinan las fechas y las efem\u00e9rides.\"}, {\"num\": 10, \"txt\": \"10. En un grupo social, puedo seguir f\u00e1cilmente las conversaciones de varias personas al mismo tiempo.\"}, {\"num\": 11, \"txt\": \"11. Me resulta f\u00e1cil desenvolverme en situaciones sociales.\"}, {\"num\": 12, \"txt\": \"12. Tiendo a notar detalles que otras personas no perciben.\"}, {\"num\": 13, \"txt\": \"13. Prefiero ir a una biblioteca antes que a una fiesta.\"}, {\"num\": 14, \"txt\": \"14. Me resulta f\u00e1cil inventarme historias o cuentos.\"}, {\"num\": 15, \"txt\": \"15. Me siento m\u00e1s atra\u00eddo/a por las personas que por las cosas u objetos.\"}, {\"num\": 16, \"txt\": \"16. Tiendo a tener intereses muy intensos y me molesto si no puedo dedicarme a ellos.\"}, {\"num\": 17, \"txt\": \"17. Disfruto de la charla social superficial (charla casual).\"}, {\"num\": 18, \"txt\": \"18. Cuando hablo, no siempre es f\u00e1cil para los dem\u00e1s tomar la palabra.\"}, {\"num\": 19, \"txt\": \"19. Me fascinan los n\u00fameros y patrones.\"}, {\"num\": 20, \"txt\": \"20. Cuando leo un libro, me cuesta entender las intenciones de los personajes.\"}, {\"num\": 21, \"txt\": \"21. No suelo disfrutar leyendo novelas de ficci\u00f3n.\"}, {\"num\": 22, \"txt\": \"22. Me resulta dif\u00edcil hacer nuevos amigos.\"}, {\"num\": 23, \"txt\": \"23. Noto patrones en las cosas todo el tiempo.\"}, {\"num\": 24, \"txt\": \"24. Prefiero ir al teatro o a un museo antes que a un evento deportivo.\"}, {\"num\": 25, \"txt\": \"25. No me molesta si mi rutina diaria se interrumpe.\"}, {\"num\": 26, \"txt\": \"26. A menudo me doy cuenta de que no s\u00e9 c\u00f3mo mantener una conversaci\u00f3n.\"}, {\"num\": 27, \"txt\": \"27. Me resulta f\u00e1cil 'leer entre l\u00edneas' cuando alguien me habla.\"}, {\"num\": 28, \"txt\": \"28. Suelo concentrarme m\u00e1s en la totalidad de un dibujo o imagen que en los peque\u00f1os detalles.\"}, {\"num\": 29, \"txt\": \"29. No se me da muy bien recordar n\u00fameros de tel\u00e9fono.\"}, {\"num\": 30, \"txt\": \"30. No suelo notar peque\u00f1os cambios en una habitaci\u00f3n o en el aspecto de alguien.\"}, {\"num\": 31, \"txt\": \"31. S\u00e9 c\u00f3mo darme cuenta si alguien que me escucha se est\u00e1 aburriendo.\"}, {\"num\": 32, \"txt\": \"32. Me resulta f\u00e1cil hacer m\u00e1s de una cosa a la vez.\"}, {\"num\": 33, \"txt\": \"33. Cuando hablo por tel\u00e9fono, no estoy seguro/a de cu\u00e1ndo es mi turno de hablar.\"}, {\"num\": 34, \"txt\": \"34. Me gusta hacer las cosas de forma espont\u00e1nea.\"}, {\"num\": 35, \"txt\": \"35. A menudo soy el \u00faltimo/a en entender el chiste o el punto humor\u00edstico de una historia.\"}, {\"num\": 36, \"txt\": \"36. Me resulta f\u00e1cil deducir lo que alguien est\u00e1 pensando o sintiendo solo mirando su rostro.\"}, {\"num\": 37, \"txt\": \"37. Si hay una interrupci\u00f3n, puedo volver a lo que estaba haciendo muy r\u00e1pidamente.\"}, {\"num\": 38, \"txt\": \"38. Se me da bien la charla social informal.\"}, {\"num\": 39, \"txt\": \"39. La gente a menudo me dice que sigo hablando una y otra vez del mismo tema.\"}, {\"num\": 40, \"txt\": \"40. Cuando era ni\u00f1o/a, me gustaba jugar a juegos de simulaci\u00f3n o representaci\u00f3n con otros ni\u00f1os.\"}, {\"num\": 41, \"txt\": \"41. Me gusta coleccionar informaci\u00f3n sobre categor\u00edas de cosas (ej. tipos de plantas, coches, trenes).\"}, {\"num\": 42, \"txt\": \"42. Me resulta dif\u00edcil imaginar c\u00f3mo ser\u00eda ser otra persona.\"}, {\"num\": 43, \"txt\": \"43. Me gusta planificar cuidadosamente cualquier actividad en la que participe.\"}, {\"num\": 44, \"txt\": \"44. Disfruto de los eventos o reuniones sociales.\"}, {\"num\": 45, \"txt\": \"45. Me resulta dif\u00edcil descifrar las intenciones de otras personas.\"}, {\"num\": 46, \"txt\": \"46. Las situaciones nuevas me provocan ansiedad o malestar.\"}, {\"num\": 47, \"txt\": \"47. Disfruto conociendo gente nueva.\"}, {\"num\": 48, \"txt\": \"48. Soy una persona muy diplom\u00e1tica y con buen tacto social.\"}, {\"num\": 49, \"txt\": \"49. No se me da bien recordar las fechas de cumplea\u00f1os de las personas.\"}, {\"num\": 50, \"txt\": \"50. Me resulta muy f\u00e1cil jugar a juegos de simulaci\u00f3n o fantas\u00eda con ni\u00f1os.\"}]",
        json.dumps({"corte_clinico": 32, "subescalas": ["Habilidades Sociales", "Cambio de Atención / Flexibilidad", "Atención a los Detalles", "Comunicación", "Imaginación"]})
    )
    cursor.execute("""
        INSERT INTO tests_definiciones 
        (code, nombre, siglas, categoria, descripcion, instrucciones, escala_opciones_json, items_json, reglas_correccion_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(code) DO UPDATE SET
            nombre=excluded.nombre,
            descripcion=excluded.descripcion,
            instrucciones=excluded.instrucciones,
            escala_opciones_json=excluded.escala_opciones_json,
            items_json=excluded.items_json,
            reglas_correccion_json=excluded.reglas_correccion_json
    """, aq_def)

    raads_r_def = (
        "RAADS-R",
        "Escala Revisada para Diagnóstico de Autismo y Asperger (RAADS-R)",
        "RAADS-R",
        "Neurodivergencia / TEA Adultos",
        "Escala clínica diagnóstica de 80 ítems para adultos que evalúa relaciones sociales, lenguaje, intereses sensoriomotores y circunscritos.",
        "Seleccione la opción que mejor describa su experiencia actual y durante la infancia.",
        json.dumps([
            {"val": 3, "txt": "3 = Verdadero ahora y cuando era joven"},
            {"val": 2, "txt": "2 = Verdadero solo ahora"},
            {"val": 1, "txt": "1 = Verdadero solo cuando tenía menos de 16 años"},
            {"val": 0, "txt": "0 = Nunca fue verdadero"}
        ]),
        "[{\"num\": 1, \"sec\": \"Relaciones Sociales\", \"txt\": \"1. Es dif\u00edcil para m\u00ed hacer amigos/as.\"}, {\"num\": 2, \"sec\": \"Lenguaje / Comunicaci\u00f3n\", \"txt\": \"2. A menudo tomo literalmente lo que la gente me dice.\"}, {\"num\": 3, \"sec\": \"Intereses Circunscritos\", \"txt\": \"3. Prefiero hacer las cosas con otras personas en vez de solo. (Inverso)\"}, {\"num\": 4, \"sec\": \"Intereses Sensoriomotores\", \"txt\": \"4. Me molestan mucho ciertas texturas o etiquetas de la ropa.\"}, {\"num\": 5, \"sec\": \"Intereses Sensoriomotores\", \"txt\": \"5. A menudo me siento abrumado/a por luces brillantes o ruidos intensos.\"}, {\"num\": 6, \"sec\": \"Relaciones Sociales\", \"txt\": \"6. S\u00e9 c\u00f3mo actuar adecuadamente en situaciones sociales. (Inverso)\"}, {\"num\": 7, \"sec\": \"Lenguaje / Comunicaci\u00f3n\", \"txt\": \"7. Me resulta dif\u00edcil entender la iron\u00eda, el sarcasmo o el doble sentido.\"}, {\"num\": 8, \"sec\": \"Relaciones Sociales\", \"txt\": \"8. Me resulta dif\u00edcil conversar de forma casual sobre temas triviales.\"}, {\"num\": 9, \"sec\": \"Intereses Sensoriomotores\", \"txt\": \"9. A menudo hago movimientos repetitivos con mis manos, dedos o cuerpo.\"}, {\"num\": 10, \"sec\": \"Intereses Circunscritos\", \"txt\": \"10. Me concentro tan intensamente en mis temas de inter\u00e9s que olvido todo lo dem\u00e1s.\"}, {\"num\": 11, \"sec\": \"Relaciones Sociales\", \"txt\": \"11. Me resulta f\u00e1cil comprender los sentimientos e intenciones de los dem\u00e1s. (Inverso)\"}, {\"num\": 12, \"sec\": \"Intereses Sensoriomotores\", \"txt\": \"12. Me molestan profundamente ciertos sonidos espec\u00edficos que otros parecen ignorar.\"}, {\"num\": 13, \"sec\": \"Intereses Sensoriomotores\", \"txt\": \"13. Suelo reaccionar de forma inusualmente fuerte a los olores, saboreos o texturas.\"}, {\"num\": 14, \"sec\": \"Relaciones Sociales\", \"txt\": \"14. A menudo me dicen que hablo demasiado o que doy demasiada informaci\u00f3n sobre temas espec\u00edficos.\"}, {\"num\": 15, \"sec\": \"Lenguaje / Comunicaci\u00f3n\", \"txt\": \"15. A veces no s\u00e9 qu\u00e9 responder cuando alguien me hace una pregunta personal espont\u00e1nea.\"}, {\"num\": 16, \"sec\": \"Intereses Sensoriomotores\", \"txt\": \"16. Me siento muy inc\u00f3modo/a con el contacto f\u00edsico de personas no muy cercanas.\"}, {\"num\": 17, \"sec\": \"Relaciones Sociales\", \"txt\": \"17. Me cuesta trabajo saber si la persona con la que hablo est\u00e1 interesada o aburrida.\"}, {\"num\": 18, \"sec\": \"Relaciones Sociales\", \"txt\": \"18. Me resulta f\u00e1cil mantener contacto visual durante una conversaci\u00f3n. (Inverso)\"}, {\"num\": 19, \"sec\": \"Intereses Sensoriomotores\", \"txt\": \"19. Tengo una sensibilidad inusualmente alta a ruidos, luces o toques f\u00edsicos.\"}, {\"num\": 20, \"sec\": \"Relaciones Sociales\", \"txt\": \"20. Me cuesta mucho integrarme en conversaciones de grupo con tres o m\u00e1s personas.\"}, {\"num\": 21, \"sec\": \"Relaciones Sociales\", \"txt\": \"21. Suelo malinterpretar lo que la gente intenta decirme en interacciones cotidianas.\"}, {\"num\": 22, \"sec\": \"Intereses Circunscritos\", \"txt\": \"22. Colecciono o acumulo datos detallados sobre temas muy particulares.\"}, {\"num\": 23, \"sec\": \"Relaciones Sociales\", \"txt\": \"23. Disfruto mucho participar en fiestas y reuniones sociales populosas. (Inverso)\"}, {\"num\": 24, \"sec\": \"Intereses Circunscritos\", \"txt\": \"24. Me molesta profundamente que cambien mis rutinas o planes previstos.\"}, {\"num\": 25, \"sec\": \"Intereses Circunscritos\", \"txt\": \"25. Tengo un pasatiempo o tema de inter\u00e9s en el que dedico la mayor parte de mi tiempo libre.\"}, {\"num\": 26, \"sec\": \"Relaciones Sociales\", \"txt\": \"26. Me han dicho que mi lenguaje corporal, voz o postura son inusuales o r\u00edgidos.\"}, {\"num\": 27, \"sec\": \"Lenguaje / Comunicaci\u00f3n\", \"txt\": \"27. Entiendo con facilidad el significado de los modismos o dichos populares. (Inverso)\"}, {\"num\": 28, \"sec\": \"Relaciones Sociales\", \"txt\": \"28. Siento que pertenezco a un 'mundo diferente' al de las dem\u00e1s personas.\"}, {\"num\": 29, \"sec\": \"Intereses Sensoriomotores\", \"txt\": \"29. Suelo tararear, balancearme o mover las piernas para autorregularme.\"}, {\"num\": 30, \"sec\": \"Intereses Sensoriomotores\", \"txt\": \"30. Ciertas comidas o texturas me causan una aversi\u00f3n sensorial extrema.\"}, {\"num\": 31, \"sec\": \"Relaciones Sociales\", \"txt\": \"31. Me resulta dif\u00edcil empatizar de forma autom\u00e1tica con las expresiones faciales ajenas.\"}, {\"num\": 32, \"sec\": \"Intereses Sensoriomotores\", \"txt\": \"32. Me resulta dif\u00edcil soportar etiquetas de ropa, costuras o materiales sint\u00e9ticos.\"}, {\"num\": 33, \"sec\": \"Relaciones Sociales\", \"txt\": \"33. Tengo amistades estables con las que me comunico de forma fluida y natural. (Inverso)\"}, {\"num\": 34, \"sec\": \"Intereses Sensoriomotores\", \"txt\": \"34. A menudo me siento agotado/a despu\u00e9s de estar en entornos muy ruidosos o concurridos.\"}, {\"num\": 35, \"sec\": \"Lenguaje / Comunicaci\u00f3n\", \"txt\": \"35. Mi voz a menudo suena mon\u00f3tona, plana o con una entonaci\u00f3n poco habitual.\"}, {\"num\": 36, \"sec\": \"Intereses Sensoriomotores\", \"txt\": \"36. Noto peque\u00f1os detalles o sonidos que pasan desapercibidos para los dem\u00e1s.\"}, {\"num\": 37, \"sec\": \"Relaciones Sociales\", \"txt\": \"37. S\u00e9 de forma intuitiva cu\u00e1ndo es mi turno de hablar en una conversaci\u00f3n. (Inverso)\"}, {\"num\": 38, \"sec\": \"Relaciones Sociales\", \"txt\": \"38. Siento que tengo que 'aprender intelectualmente' c\u00f3mo comportarme socialmente.\"}, {\"num\": 39, \"sec\": \"Relaciones Sociales\", \"txt\": \"39. Me molesta que las personas utilicen indirectas en lugar de decir las cosas claramente.\"}, {\"num\": 40, \"sec\": \"Relaciones Sociales\", \"txt\": \"40. Me cuesta mucho adaptar mi comportamento a distintos grupos o entornos sociales.\"}, {\"num\": 41, \"sec\": \"Intereses Sensoriomotores\", \"txt\": \"41. Experimento una sobrecarga sensorial cuando hay demasiados est\u00edmulos simult\u00e1neos.\"}, {\"num\": 42, \"sec\": \"Relaciones Sociales\", \"txt\": \"42. A menudo me resulta dif\u00edcil entender por qu\u00e9 la gente se siente ofendida por mis comentarios.\"}, {\"num\": 43, \"sec\": \"Relaciones Sociales\", \"txt\": \"43. Me resulta f\u00e1cil interpretar las miradas y gestos de las personas. (Inverso)\"}, {\"num\": 44, \"sec\": \"Relaciones Sociales\", \"txt\": \"44. Me siento m\u00e1s c\u00f3modo/a interactuando con personas que comparten mis mismos intereses espec\u00edficos.\"}, {\"num\": 45, \"sec\": \"Intereses Circunscritos\", \"txt\": \"45. Organizo minuciosamente mis objetos, libros o archivos seg\u00fan categor\u00edas precisas.\"}, {\"num\": 46, \"sec\": \"Intereses Sensoriomotores\", \"txt\": \"46. Disfruto de la sensaci\u00f3n t\u00e1ctil de ciertos objetos o materiales concretos.\"}, {\"num\": 47, \"sec\": \"Relaciones Sociales\", \"txt\": \"47. Disfruto mucho de las din\u00e1micas y juegos grupales con otras personas. (Inverso)\"}, {\"num\": 48, \"sec\": \"Relaciones Sociales\", \"txt\": \"48. Me resulta dif\u00edcil iniciar conversaciones espont\u00e1neas con personas desconocidas.\"}, {\"num\": 49, \"sec\": \"Intereses Sensoriomotores\", \"txt\": \"49. Suelo tocar compulsivamente ciertos patrones o texturas cuando estoy estresado/a.\"}, {\"num\": 50, \"sec\": \"Intereses Circunscritos\", \"txt\": \"50. Acumulo un conocimiento muy profundo sobre temas espec\u00edficos que apasionan.\"}, {\"num\": 51, \"sec\": \"Relaciones Sociales\", \"txt\": \"51. Me resulta confuso entender los l\u00edmites en las interacciones personales.\"}, {\"num\": 52, \"sec\": \"Intereses Circunscritos\", \"txt\": \"52. Me gusta cambiar constantemente de pasatiempos y probar temas diferentes. (Inverso)\"}, {\"num\": 53, \"sec\": \"Relaciones Sociales\", \"txt\": \"53. Me dicen que hablo demasiado r\u00e1pido, despacio o con t\u00e9rminos demasiado formales.\"}, {\"num\": 54, \"sec\": \"Intereses Sensoriomotores\", \"txt\": \"54. Me molestan los cambios bruscos de temperatura o la luz solar directa.\"}, {\"num\": 55, \"sec\": \"Relaciones Sociales\", \"txt\": \"55. A menudo me siento desconectado/a o 'afuera' de los grupos de personas.\"}, {\"num\": 56, \"sec\": \"Intereses Sensoriomotores\", \"txt\": \"56. Tengo movimientos de autorregulaci\u00f3n o aleteo cuando estoy muy emocionado/a o ansioso/a.\"}, {\"num\": 57, \"sec\": \"Intereses Sensoriomotores\", \"txt\": \"57. Siento incomodidad f\u00edsica ante ruidos repentinos como alarmas o bocinas.\"}, {\"num\": 58, \"sec\": \"Lenguaje / Comunicaci\u00f3n\", \"txt\": \"58. Entiendo f\u00e1cilmente las bromas, juegos de palabras y humor sutil. (Inverso)\"}, {\"num\": 59, \"sec\": \"Intereses Circunscritos\", \"txt\": \"59. Sigo horarios y secuencias de actividades de forma estricta.\"}, {\"num\": 60, \"sec\": \"Relaciones Sociales\", \"txt\": \"60. Siento que las expectativas sociales habituales son complicadas e il\u00f3gicas.\"}, {\"num\": 61, \"sec\": \"Relaciones Sociales\", \"txt\": \"61. Me cuesta mantener amistades a largo plazo debido a la desconexi\u00f3n comunicativa.\"}, {\"num\": 62, \"sec\": \"Relaciones Sociales\", \"txt\": \"62. Me cuesta saber si le caigo bien o mal a alguien salvo que me lo diga expl\u00edcitamente.\"}, {\"num\": 63, \"sec\": \"Intereses Sensoriomotores\", \"txt\": \"63. Me resulta placentero estar en lugares con muchas luces de colores y m\u00fasica alta. (Inverso)\"}, {\"num\": 64, \"sec\": \"Relaciones Sociales\", \"txt\": \"64. Me resulta agotador sostener conversaciones sociales durante varias horas.\"}, {\"num\": 65, \"sec\": \"Relaciones Sociales\", \"txt\": \"65. Prefiero escribir mis pensamientos antes que comunicarlos de forma verbal.\"}, {\"num\": 66, \"sec\": \"Lenguaje / Comunicaci\u00f3n\", \"txt\": \"66. Tiendo a interpretar las preguntas de forma hiperprecisa e inusual.\"}, {\"num\": 67, \"sec\": \"Intereses Sensoriomotores\", \"txt\": \"67. Me agradan los abrazos y aperturas f\u00edsicas imprevistas de otras personas. (Inverso)\"}, {\"num\": 68, \"sec\": \"Relaciones Sociales\", \"txt\": \"68. Me han descrito como una persona retra\u00edda, reservada o distante.\"}, {\"num\": 69, \"sec\": \"Relaciones Sociales\", \"txt\": \"69. Me resulta dif\u00edcil compartir mis experiencias emocionales con los dem\u00e1s.\"}, {\"num\": 70, \"sec\": \"Intereses Circunscritos\", \"txt\": \"70. Memorizo f\u00e1cilmente listados, calendarios, estad\u00edsticas o datos num\u00e9ricos.\"}, {\"num\": 71, \"sec\": \"Intereses Circunscritos\", \"txt\": \"71. Me causa un gran malestar que muevan mis pertenencias de lugar sin mi permiso.\"}, {\"num\": 72, \"sec\": \"Relaciones Sociales\", \"txt\": \"72. Comprendo sin problemas las normas no escritas de la etiqueta social. (Inverso)\"}, {\"num\": 73, \"sec\": \"Intereses Circunscritos\", \"txt\": \"73. Me resulta placentero repetir patrones o secuencias de movimientos o palabras.\"}, {\"num\": 74, \"sec\": \"Relaciones Sociales\", \"txt\": \"74. Me cuesta entender los motivos por los que las personas act\u00faan en conflictos interpersonales.\"}, {\"num\": 75, \"sec\": \"Relaciones Sociales\", \"txt\": \"75. Me siento m\u00e1s c\u00f3modo/a comunic\u00e1ndome en entornos virtuales que presenciales.\"}, {\"num\": 76, \"sec\": \"Intereses Circunscritos\", \"txt\": \"76. Dedico tiempo considerable a perfeccionar o pulir detalles en mis proyectos personales.\"}, {\"num\": 77, \"sec\": \"Relaciones Sociales\", \"txt\": \"77. Me resulta natural hacer cumplidos y comentarios sociales corteses. (Inverso)\"}, {\"num\": 78, \"sec\": \"Intereses Circunscritos\", \"txt\": \"78. Disfruto sumergi\u00e9ndome por completo en mis pasiones sin interrupciones.\"}, {\"num\": 79, \"sec\": \"Relaciones Sociales\", \"txt\": \"79. Siento que las conversaciones cotidianas est\u00e1n llenas de c\u00f3digos que debo descifrar.\"}, {\"num\": 80, \"sec\": \"Relaciones Sociales\", \"txt\": \"80. Me resulta f\u00e1cil comprender los estados de \u00e1nimo de las personas a mi alrededor. (Inverso)\"}]",
        json.dumps({"umbral_diagnostico": 65, "subescalas": ["Relaciones Sociales", "Lenguaje / Comunicación", "Intereses Sensoriomotores", "Intereses Circunscritos"]})
    )
    cursor.execute("""
        INSERT INTO tests_definiciones 
        (code, nombre, siglas, categoria, descripcion, instrucciones, escala_opciones_json, items_json, reglas_correccion_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(code) DO UPDATE SET
            nombre=excluded.nombre,
            descripcion=excluded.descripcion,
            instrucciones=excluded.instrucciones,
            escala_opciones_json=excluded.escala_opciones_json,
            items_json=excluded.items_json,
            reglas_correccion_json=excluded.reglas_correccion_json
    """, raads_r_def)

    cat_q_def = (
        "CAT-Q",
        "Cuestionario de Camuflaje de Rasgos Autistas (CAT-Q)",
        "CAT-Q",
        "Neurodivergencia / TEA Adultos",
        "Instrumento psicométrico de 25 ítems para medir el nivel de enmascaramiento social (masking), compensación y asimilación.",
        "Indique su grado de acuerdo de 1 (Totalmente en desacuerdo) a 7 (Totalmente de acuerdo) con cada afirmación.",
        json.dumps([
            {"val": 1, "txt": "1 = Totalmente en desacuerdo"},
            {"val": 2, "txt": "2 = En desacuerdo"},
            {"val": 3, "txt": "3 = Algo en desacuerdo"},
            {"val": 4, "txt": "4 = Neutral / Ni acuerdo ni desacuerdo"},
            {"val": 5, "txt": "5 = Algo de acuerdo"},
            {"val": 6, "txt": "6 = De acuerdo"},
            {"val": 7, "txt": "7 = Totalmente de acuerdo"}
        ]),
        "[{\"num\": 1, \"sec\": \"Compensaci\u00f3n\", \"txt\": \"1. He practicado expresiones faciales o la entonaci\u00f3n de la voz frente al espejo para mejorar mis habilidades sociales.\"}, {\"num\": 2, \"sec\": \"Enmascaramiento\", \"txt\": \"2. Monitoreo constantemente mi lenguaje corporal (gestos, postura) cuando estoy en interacci\u00f3n con otras personas.\"}, {\"num\": 3, \"sec\": \"Asimilaci\u00f3n\", \"txt\": \"3. En situaciones sociales, siento que puedo ser completamente yo mismo/a de forma espont\u00e1nea. (Inverso)\"}, {\"num\": 4, \"sec\": \"Compensaci\u00f3n\", \"txt\": \"4. He aprendido reglas sobre c\u00f3mo entablar y mantener una conversaci\u00f3n observando a otras personas.\"}, {\"num\": 5, \"sec\": \"Compensaci\u00f3n\", \"txt\": \"5. Utilizo un guion mental preconcebido cuando tengo que hablar con gente poco conocida o en llamadas telef\u00f3nicas.\"}, {\"num\": 6, \"sec\": \"Enmascaramiento\", \"txt\": \"6. Hago un esfuerzo consciente por hacer contacto visual con las personas aunque me resulte inc\u00f3modo o agotador.\"}, {\"num\": 7, \"sec\": \"Asimilaci\u00f3n\", \"txt\": \"7. Siento la necesidad de 'actuar' o 'interpretar un personaje' para encajar en grupos sociales.\"}, {\"num\": 8, \"sec\": \"Compensaci\u00f3n\", \"txt\": \"8. Investigo de forma previa temas de conversaci\u00f3n populares para asegurarme de tener algo que decir.\"}, {\"num\": 9, \"sec\": \"Enmascaramiento\", \"txt\": \"9. Reprimo deliberadamente mis movimientos corporales o gestos repetitivos (estimulaciones / stimming) cuando estoy en p\u00fablico.\"}, {\"num\": 10, \"sec\": \"Asimilaci\u00f3n\", \"txt\": \"10. Trato de copiar los comportamientos y la vestimenta de personas que parecen socialmente exitosas.\"}, {\"num\": 11, \"sec\": \"Compensaci\u00f3n\", \"txt\": \"11. Utilizo preguntas estructuradas para mantener a la otra persona hablando y evitar quedarme en silencio.\"}, {\"num\": 12, \"sec\": \"Enmascaramiento\", \"txt\": \"12. Muestro de forma natural mis verdaderas emociones y reacciones corporales en p\u00fablico. (Inverso)\"}, {\"num\": 13, \"sec\": \"Asimilaci\u00f3n\", \"txt\": \"13. Me siento obligado/a a sonre\u00edr o asentir para parecer amable, incluso si no me siento interesado/a.\"}, {\"num\": 14, \"sec\": \"Compensaci\u00f3n\", \"txt\": \"14. Leo libros o art\u00edculos sobre psicolog\u00eda e interacci\u00f3n social para aprender c\u00f3mo comportarme.\"}, {\"num\": 15, \"sec\": \"Enmascaramiento\", \"txt\": \"15. Controlo cuidadosamente la intensidad de mi voz para que no suene demasiado alta, mon\u00f3tona o inusual.\"}, {\"num\": 16, \"sec\": \"Asimilaci\u00f3n\", \"txt\": \"16. Siento que el resto de las personas no conocen mi verdadera personalidad porque siempre me estoy adaptando.\"}, {\"num\": 17, \"sec\": \"Compensaci\u00f3n\", \"txt\": \"17. Ensayo con antelaci\u00f3n las posibles respuestas a preguntas que alguien podr\u00eda hacerme.\"}, {\"num\": 18, \"sec\": \"Enmascaramiento\", \"txt\": \"18. Me obligo a re\u00edr cuando otros r\u00eden, aunque no haya comprendido el chiste.\"}, {\"num\": 19, \"sec\": \"Asimilaci\u00f3n\", \"txt\": \"19. Me resulta f\u00e1cil integrarme de manera natural a conversaciones de grupo sin tener que planearlo. (Inverso)\"}, {\"num\": 20, \"sec\": \"Compensaci\u00f3n\", \"txt\": \"20. Utilizo expresiones o modismos copiados de pel\u00edculas, series o libros en mi lenguaje cotidiano.\"}, {\"num\": 21, \"sec\": \"Enmascaramiento\", \"txt\": \"21. Suprimo mis intereses intensos o pasiones para no parecer extra\u00f1o/a o abrumador/a frente a los dem\u00e1s.\"}, {\"num\": 22, \"sec\": \"Asimilaci\u00f3n\", \"txt\": \"22. Me siento c\u00f3modo/a siendo el centro de atenci\u00f3n tal como soy. (Inverso)\"}, {\"num\": 23, \"sec\": \"Compensaci\u00f3n\", \"txt\": \"23. Adapto meticulosamente mi tono de voz y vocabulario seg\u00fan la persona con la que est\u00e9 hablando.\"}, {\"num\": 24, \"sec\": \"Enmascaramiento\", \"txt\": \"24. En reuniones o fiestas, me siento relajado/a y actu\u00f3 espont\u00e1neamente. (Inverso)\"}, {\"num\": 25, \"sec\": \"Asimilaci\u00f3n\", \"txt\": \"25. Termino exhausto/a emocional y f\u00edsicamente despu\u00e9s de haber socializado por haber estado camuflando mis rasgos.\"}]",
        json.dumps({"corte_camuflaje": 100, "subescalas": ["Compensación", "Enmascaramiento", "Asimilación"]})
    )
    cursor.execute("""
        INSERT INTO tests_definiciones 
        (code, nombre, siglas, categoria, descripcion, instrucciones, escala_opciones_json, items_json, reglas_correccion_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(code) DO UPDATE SET
            nombre=excluded.nombre,
            descripcion=excluded.descripcion,
            instrucciones=excluded.instrucciones,
            escala_opciones_json=excluded.escala_opciones_json,
            items_json=excluded.items_json,
            reglas_correccion_json=excluded.reglas_correccion_json
    """, cat_q_def)
    db.commit()



    db.commit()

    # Asegurar la definición e inserción del MCMI-II
    mcmi_def = (
        "MCMI-II",
        "Inventario Multiaxial Clínico de Millon - II",
        "MCMI-II",
        "Evaluación de Personalidad y Psicopatología",
        "Instrumento clínico de 175 ítems (Verdadero/Falso) para la evaluación de patrones clínicos de personalidad, patologías graves de personalidad y síndromes clínicos.",
        "Responda a las siguientes afirmaciones marcando V (Verdadero) o F (Falso) según describan su forma de ser o sentir habitualmente.",
        json.dumps([{"val": 1, "txt": "V (Verdadero)"}, {"val": 2, "txt": "F (Falso)"}]),
        "[{\"num\": 1, \"txt\": \"1. Act\u00fao siempre seg\u00fan mis propias ideas en vez de hacer lo que otros esperan que haga.\"}, {\"num\": 2, \"txt\": \"2. He encontrado siempre m\u00e1s c\u00f3modo hacer las cosas solo, tranquilamente, que hacerlas con otros.\"}, {\"num\": 3, \"txt\": \"3. Hablar con la gente ha sido casi siempre dif\u00edcil y desagradable para m\u00ed.\"}, {\"num\": 4, \"txt\": \"4. Creo que tengo que ser en\u00e9rgico y decidido en todo lo que hago.\"}, {\"num\": 5, \"txt\": \"5. Desde hace algunas semanas me pongo a llorar incluso cuando la menor cosa me sale mal.\"}, {\"num\": 6, \"txt\": \"6. Algunas personas piensan que soy vanidoso o egoc\u00e9ntrico.\"}, {\"num\": 7, \"txt\": \"7. Cuando era adolescente tuve muchos problemas por mi mal comportamiento en el colegio.\"}, {\"num\": 8, \"txt\": \"8. Tengo siempre la impresi\u00f3n de no ser aceptado en un grupo.\"}, {\"num\": 9, \"txt\": \"9. Frecuentemente critico a la gente que me molesta.\"}, {\"num\": 10, \"txt\": \"10. Me encuentro m\u00e1s a gusto siguiendo a los dem\u00e1s.\"}, {\"num\": 11, \"txt\": \"11. Me gusta hacer tantas cosas diferentes que no s\u00e9 por d\u00f3nde empezar.\"}, {\"num\": 12, \"txt\": \"12. Algunas veces puedo ser bastante duro o mezquino con mi familia.\"}, {\"num\": 13, \"txt\": \"13. Tengo poco inter\u00e9s en hacer amigos.\"}, {\"num\": 14, \"txt\": \"14. Me considero una persona muy sociable o extravertida.\"}, {\"num\": 15, \"txt\": \"15. S\u00e9 que soy una persona superior a los dem\u00e1s y por eso no me preocupa lo que piensen.\"}, {\"num\": 16, \"txt\": \"16. La gente nunca ha apreciado suficientemente las cosas que he hecho.\"}, {\"num\": 17, \"txt\": \"17. Tengo problemas con la bebida que he intentado solucionar sin \u00e9xito.\"}, {\"num\": 18, \"txt\": \"18. \u00daltimamente siento un nudo en el est\u00f3mago y me invade un sudor fr\u00edo.\"}, {\"num\": 19, \"txt\": \"19. Siempre he querido permanecer en segundo plano en las actividades sociales.\"}, {\"num\": 20, \"txt\": \"20. A menudo hago cosas sin ninguna raz\u00f3n, s\u00f3lo porque pueden ser divertidas.\"}, {\"num\": 21, \"txt\": \"21. Me molesta mucho la gente que no es capaz de hacer las cosas bien.\"}, {\"num\": 22, \"txt\": \"22. Si mi familia me obliga o presiona, es probable que me enfade y me resista a hacer lo que ellos quieren.\"}, {\"num\": 23, \"txt\": \"23. Muchas veces pienso que me deber\u00edan de castigar por lo que he hecho.\"}, {\"num\": 24, \"txt\": \"24. La gente se r\u00ede de m\u00ed a mis espaldas, hablando de lo que hago o parezco.\"}, {\"num\": 25, \"txt\": \"25. Los dem\u00e1s parecen m\u00e1s seguros que yo sobre lo que son y lo que quieren.\"}, {\"num\": 26, \"txt\": \"26. Soy propenso a tener explosiones de llanto o c\u00f3lera sin tener motivo.\"}, {\"num\": 27, \"txt\": \"27. Desde hace uno o dos a\u00f1os he comenzado a sentirme solo y vac\u00edo.\"}, {\"num\": 28, \"txt\": \"28. Tengo habilidad para \\\"dramatizar\\\" las cosas.\"}, {\"num\": 29, \"txt\": \"29. Me resulta dif\u00edcil mantener el equilibrio cuando camino.\"}, {\"num\": 30, \"txt\": \"30. Disfruto en situaciones de intensa competitividad.\"}, {\"num\": 31, \"txt\": \"31. Cuando entro en crisis busco enseguida alguien que me ayude.\"}, {\"num\": 32, \"txt\": \"32. Me protejo de los problemas no dejando que la gente sepa mucho sobre m\u00ed.\"}, {\"num\": 33, \"txt\": \"33. Casi siempre me siento d\u00e9bil y cansado.\"}, {\"num\": 34, \"txt\": \"34. Otras personas se enfadan mucho m\u00e1s que yo por las cosas molestas.\"}, {\"num\": 35, \"txt\": \"35. A menudo, mi adicci\u00f3n a las drogas me ha causado en el pasado bastantes problemas.\"}, {\"num\": 36, \"txt\": \"36. \u00daltimamente me encuentro llorando sin ning\u00fan motivo.\"}, {\"num\": 37, \"txt\": \"37. Creo que soy una persona especial, que necesita que los dem\u00e1s me presten una atenci\u00f3n especial.\"}, {\"num\": 38, \"txt\": \"38. Nunca me dejo enga\u00f1ar por gente que dice necesitar ayuda.\"}, {\"num\": 39, \"txt\": \"39. Una buena forma de conseguir un mundo en paz es fomentar los valores morales de la gente.\"}, {\"num\": 40, \"txt\": \"40. En el pasado he mantenido relaciones sexuales con muchas personas que no significaban nada especial para m\u00ed. POR FAVOR, NO SE DETENGA. CONTINUE EN LA P\u00c1GINA SIGUIENTE\"}, {\"num\": 41, \"txt\": \"41. Me resulta dif\u00edcil simpatizar con la gente que se siente siempre insegura con todo.\"}, {\"num\": 42, \"txt\": \"42. Soy una persona muy agradable y d\u00f3cil.\"}, {\"num\": 43, \"txt\": \"43. La principal causa de mis problemas ha sido mi \\\"mal car\u00e1cter\\\".\"}, {\"num\": 44, \"txt\": \"44. No tengo inconveniente en forzar a los dem\u00e1s a hacer lo que yo quiero.\"}, {\"num\": 45, \"txt\": \"45. En los \u00faltimos a\u00f1os, incluso las cosas sin importancia perecen deprimirme.\"}, {\"num\": 46, \"txt\": \"46. Mi deseo de hacer las cosas lo m\u00e1s perfectamente posible muchas veces enlentece mi trabajo.\"}, {\"num\": 47, \"txt\": \"47. Soy tan callado y retra\u00eddo que la mayor\u00eda de la gente no sabe ni que existo.\"}, {\"num\": 48, \"txt\": \"48. Me gusta coquetear con las personas del otro sexo.\"}, {\"num\": 49, \"txt\": \"49. Soy una persona tranquila y temerosa.\"}, {\"num\": 50, \"txt\": \"50. Soy muy variable y cambio de opiniones y sentimientos continuamente.\"}, {\"num\": 51, \"txt\": \"51. Me pongo muy nervioso cuando pienso en los acontecimientos del d\u00eda.\"}, {\"num\": 52, \"txt\": \"52. Beber alcohol nunca me ha causado verdaderos problemas en mi trabajo.\"}, {\"num\": 53, \"txt\": \"53. \u00daltimamente me siento sin fuerzas, incluso por la ma\u00f1ana.\"}, {\"num\": 54, \"txt\": \"54. Hace algunos a\u00f1os que he comenzado a sentirme un fracasado.\"}, {\"num\": 55, \"txt\": \"55. No soporto a las personas \\\"sabihondas\\\", que lo saben todo y piensan que pueden hacer cualquier cosa mejor que yo.\"}, {\"num\": 56, \"txt\": \"56. He tenido siempre miedo a perder el afecto de las personas que m\u00e1s necesito.\"}, {\"num\": 57, \"txt\": \"57. Parece que me aparto de mis objetivos dejando que otros me adelanten.\"}, {\"num\": 58, \"txt\": \"58. \u00daltimamente he comenzado a sentir deseos de tirar y romper cosas.\"}, {\"num\": 59, \"txt\": \"59. Recientemente he pensado muy en serio en quitarme de en medio.\"}, {\"num\": 60, \"txt\": \"60. Siempre estoy buscando hacer nuevos amigos y conocer gente nueva.\"}, {\"num\": 61, \"txt\": \"61. Controlo muy bien mi dinero para estar preparado en caso de necesidad.\"}, {\"num\": 62, \"txt\": \"62. El a\u00f1o pasado aparec\u00ed en la portada de varias revistas.\"}, {\"num\": 63, \"txt\": \"63. Le gusto a muy poca gente.\"}, {\"num\": 64, \"txt\": \"64. Si alguien me criticase por cometer un error, r\u00e1pidamente le reprochar\u00eda sus propios errores.\"}, {\"num\": 65, \"txt\": \"65. Algunas personas dicen que disfruto sufriendo.\"}, {\"num\": 66, \"txt\": \"66. Muchas veces expreso mi rabia y mal humor, y luego me siento terriblemente culpable por ello.\"}, {\"num\": 67, \"txt\": \"67. \u00daltimamente me siento nervioso y bajo una terrible tensi\u00f3n sin saber por qu\u00e9.\"}, {\"num\": 68, \"txt\": \"68. Muy a menudo pierdo mi capacidad para percibir sensaciones en partes de mi cuerpo.\"}, {\"num\": 69, \"txt\": \"69. Creo que hay personas que utilizan la telepat\u00eda para influir en mi vida.\"}, {\"num\": 70, \"txt\": \"70. Tomar la llamadas drogas \\\"ilegales\\\" puede ser indeseable o nocivo, pero reconozco que en el pasado las he necesitado.\"}, {\"num\": 71, \"txt\": \"71. Me siento continuamente muy cansado.\"}, {\"num\": 72, \"txt\": \"72. No puedo dormirme, y me levanto tan cansado como al acostarme.\"}, {\"num\": 73, \"txt\": \"73. He hecho impulsivamente muchas cosas est\u00fapidas que han llegado a causarme grandes problemas.\"}, {\"num\": 74, \"txt\": \"74. Nunca perdono un insulto ni olvido una situaci\u00f3n molesta que alguien me haya provocado.\"}, {\"num\": 75, \"txt\": \"75. Debemos respetar a nuestros mayores y no creer que sabemos m\u00e1s que ellos.\"}, {\"num\": 76, \"txt\": \"76. Me siento muy triste y deprimido la mayor parte del tiempo.\"}, {\"num\": 77, \"txt\": \"77. Soy la t\u00edpica persona de la que otros se aprovechan.\"}, {\"num\": 78, \"txt\": \"78. Siempre hago lo posible por complacer a los dem\u00e1s, incluso si ellos no me gustan.\"}, {\"num\": 79, \"txt\": \"79. Durante muchos a\u00f1os he pensado seriamente en suicidarme.\"}, {\"num\": 80, \"txt\": \"80. Me doy cuenta enseguida cuando la gente intenta crearme problemas. POR FAVOR, NO SE DETENGA. CONTINUE EN LA P\u00c1GINA SIGUIENTE\"}, {\"num\": 81, \"txt\": \"81. Siempre he tenido menos inter\u00e9s en el sexo que la mayor\u00eda de la gente.\"}, {\"num\": 82, \"txt\": \"82. No comprendo por qu\u00e9, pero parece que disfruto haciendo sufrir a los que quiero.\"}, {\"num\": 83, \"txt\": \"83. Hace mucho tiempo decid\u00ed que lo mejor es tener poco que ver con la gente.\"}, {\"num\": 84, \"txt\": \"84. Estoy dispuesto a luchar hasta el final antes de que nadie obstruya mis intereses y objetivos.\"}, {\"num\": 85, \"txt\": \"85. Desde ni\u00f1o siempre he tenido que tener cuidado con la gente que intentaba enga\u00f1arme.\"}, {\"num\": 86, \"txt\": \"86. Cuando las cosas son aburridas me gusta provocar algo interesante.\"}, {\"num\": 87, \"txt\": \"87. Tengo un problema con el alcohol que nos ha creado dificultades a m\u00ed y mi familia.\"}, {\"num\": 88, \"txt\": \"88. Si alguien necesita hacer algo que requiera mucha paciencia, deber\u00eda contar conmigo.\"}, {\"num\": 89, \"txt\": \"89. Probablemente tengo las ideas m\u00e1s creativas de entre la gente que conozco.\"}, {\"num\": 90, \"txt\": \"90. No he visto ning\u00fan coche en los \u00faltimos diez a\u00f1os.\"}, {\"num\": 91, \"txt\": \"91. No veo nada incorrecto en utilizar a la gente para conseguir lo que quiero\"}, {\"num\": 92, \"txt\": \"92. El que me castiguen nunca me ha frenado de hacer lo que he querido.\"}, {\"num\": 93, \"txt\": \"93. Muchas veces me siento muy alegre y animado, sin ning\u00fan motivo.\"}, {\"num\": 94, \"txt\": \"94. Siendo adolescente, me fugu\u00e9 de casa por lo menos una vez.\"}, {\"num\": 95, \"txt\": \"95. Muy a menudo digo cosas sin pensarlas y luego me arrepiento de haberlas dicho.\"}, {\"num\": 96, \"txt\": \"96. En las \u00faltimas semanas me he sentido exhausto, agotado, sin un motivo especial.\"}, {\"num\": 97, \"txt\": \"97. \u00daltimamente me he sentido muy culpable porque ya no soy capaz de hacer nada bien.\"}, {\"num\": 98, \"txt\": \"98. Algunas ideas me dan vueltas en la cabeza una y otra vez, y no consigo olvidarlas.\"}, {\"num\": 99, \"txt\": \"99. En los dos \u00faltimos a\u00f1os me he vuelto muy desanimado y triste sobre la vida.\"}, {\"num\": 100, \"txt\": \"100. Mucha gente ha estado espiando mi vida privada durante a\u00f1os.\"}, {\"num\": 101, \"txt\": \"101. No s\u00e9 por qu\u00e9, pero a veces digo cosas crueles para hacer sufrir a los dem\u00e1s.\"}, {\"num\": 102, \"txt\": \"102. Odio o tengo miedo de la mayor parte de la gente.\"}, {\"num\": 103, \"txt\": \"103. Expreso mi opini\u00f3n sobre las cosas sin que me importe lo que otros puedan pensar.\"}, {\"num\": 104, \"txt\": \"104. Cuando alguien con autoridad insiste en que haga algo, es probable que lo eluda o bien que lo haga mal.\"}, {\"num\": 105, \"txt\": \"105. En el pasado el h\u00e1bito de abusar de las drogas me ha hecho no acudir al trabajo.\"}, {\"num\": 106, \"txt\": \"106. Estoy siempre dispuesto a ceder ante los otros para evitar disputas.\"}, {\"num\": 107, \"txt\": \"107. Con frecuencia estoy irritable y de mal humor.\"}, {\"num\": 108, \"txt\": \"108. \u00daltimamente ya no tengo fuerzas para luchar ni para defenderme.\"}, {\"num\": 109, \"txt\": \"109. \u00daltimamente tengo que pensar las cosas una y otra vez sin ning\u00fan motivo.\"}, {\"num\": 110, \"txt\": \"110. Muchas veces pienso que no merezco las cosas buenas que me suceden.\"}, {\"num\": 111, \"txt\": \"111. Utilizo mi atractivo para conseguir la atenci\u00f3n de los dem\u00e1s.\"}, {\"num\": 112, \"txt\": \"112. Cuando estoy solo, a menudo noto la fuerte presencia de alguien cercano que no puede ser visto.\"}, {\"num\": 113, \"txt\": \"113. Me siento desorientado, sin objetivos, y no s\u00e9 hacia d\u00f3nde voy a ir en la vida.\"}, {\"num\": 114, \"txt\": \"114. \u00daltimamente he sudado mucho y me he sentido muy tenso.\"}, {\"num\": 115, \"txt\": \"115. A veces siento como si necesitase hacer algo para hacerme da\u00f1o a m\u00ed mismo o a otros.\"}, {\"num\": 116, \"txt\": \"116. La ley me ha castigado injustamente por delitos que nunca he cometido.\"}, {\"num\": 117, \"txt\": \"117. Me he vuelto muy sobresaltado y nervioso en las \u00faltimas semanas.\"}, {\"num\": 118, \"txt\": \"118. Sigo teniendo extra\u00f1os pensamientos de los que desear\u00eda poder librarme.\"}, {\"num\": 119, \"txt\": \"119. Tengo muchas dificultades para controlar el impulso de beber en exceso.\"}, {\"num\": 120, \"txt\": \"120. Mucha gente piensa que no sirvo para nada. POR FAVOR, NO SE DETENGA. CONTINUE EN LA P\u00c1GINA SIGUIENTE\"}, {\"num\": 121, \"txt\": \"121. Puedo llegar a estar muy excitado sexualmente cuando discuto o peleo con alguien a quien amo.\"}, {\"num\": 122, \"txt\": \"122. Durante a\u00f1os he conseguido mantener en el m\u00ednimo mi consumo de alcohol.\"}, {\"num\": 123, \"txt\": \"123. Siempre pongo a prueba a la gente para saber hasta d\u00f3nde son de confianza.\"}, {\"num\": 124, \"txt\": \"124. Incluso cuando estoy despierto parece que no me doy cuenta de la gente que est\u00e1 cerca de m\u00ed.\"}, {\"num\": 125, \"txt\": \"125. Me resulta f\u00e1cil hacer muchos amigos.\"}, {\"num\": 126, \"txt\": \"126. Me aseguro siempre de que mi trabajo est\u00e9 bien planeado y organizado.\"}, {\"num\": 127, \"txt\": \"127. Con mucha frecuencia oigo cosas con tanta claridad que me molesta.\"}, {\"num\": 128, \"txt\": \"128. Mis estados de \u00e1nimo parecen cambiar de un dia para otro.\"}, {\"num\": 129, \"txt\": \"129. No culpo a quien se aprovecha de alguien que se lo permite.\"}, {\"num\": 130, \"txt\": \"130. He cambiado de trabajo por lo menos m\u00e1s de tres veces en los \u00faltimos dos a\u00f1os.\"}, {\"num\": 131, \"txt\": \"131. Tengo muchas ideas muy avanzadas para los tiempos actuales.\"}, {\"num\": 132, \"txt\": \"132. Me siento muy triste y melanc\u00f3lico \u00faltimamente y parece que no puedo superarlo.\"}, {\"num\": 133, \"txt\": \"133. Creo que siempre es mejor buscar ayuda para lo que hago.\"}, {\"num\": 134, \"txt\": \"134. Muchas veces me enfado con la gente que hace las cosas lentamente.\"}, {\"num\": 135, \"txt\": \"135. Realmente me molesta la gente que espera que haga lo que yo no quiero hacer.\"}, {\"num\": 136, \"txt\": \"136. En estos \u00faltimos a\u00f1os me he sentido tan culpable que puedo hacer algo terrible contra m\u00ed.\"}, {\"num\": 137, \"txt\": \"137. Cuando estoy en una fiesta o reuni\u00f3n nunca me quedo al margen.\"}, {\"num\": 138, \"txt\": \"138. La gente me dice que soy una persona muy \u00edntegra y moral.\"}, {\"num\": 139, \"txt\": \"139. Algunas veces me siento confuso y preocupado cuando la gente es amable conmigo.\"}, {\"num\": 140, \"txt\": \"140. El problema de usar drogas \\\"ilegales\\\" me ha causado discusiones con mi familia.\"}, {\"num\": 141, \"txt\": \"141. Me siento muy inc\u00f3modo con personas del otro sexo.\"}, {\"num\": 142, \"txt\": \"142. Algunos miembros de mi familia dicen que soy ego\u00edsta y que s\u00f3lo pienso en m\u00ed mismo.\"}, {\"num\": 143, \"txt\": \"143. No me importa que la gente no se interese por m\u00ed.\"}, {\"num\": 144, \"txt\": \"144. Francamente, miento con mucha frecuencia para salir de dificultades o problemas.\"}, {\"num\": 145, \"txt\": \"145. La gente puede hacerme cambiar de ideas f\u00e1cilmente, incluso cuando pienso que ya hab\u00eda tomado una decisi\u00f3n.\"}, {\"num\": 146, \"txt\": \"146. Algunos han tratado de dominarme, pero he tenido fuerza de voluntad para superarlo.\"}, {\"num\": 147, \"txt\": \"147. Mis padres me dec\u00edan con frecuencia que no era bueno.\"}, {\"num\": 148, \"txt\": \"148. A menudo la gente se irrita conmigo cuando les doy \u00f3rdenes.\"}, {\"num\": 149, \"txt\": \"149. Tengo mucho respeto por los que tienen autoridad sobre m\u00ed.\"}, {\"num\": 150, \"txt\": \"150. No tengo casi ning\u00fan lazo \u00edntimo con los dem\u00e1s.\"}, {\"num\": 151, \"txt\": \"151. En el pasado la gente dec\u00eda que yo estaba muy interesado y que me apasionaba por demasiadas cosas.\"}, {\"num\": 152, \"txt\": \"152. En el \u00faltimo a\u00f1o he cruzado el Atl\u00e1ntico m\u00e1s de treinta veces.\"}, {\"num\": 153, \"txt\": \"153. Estoy de acuerdo con el refr\u00e1n:\\\"Al que madruga Dios le ayuda\\\".\"}, {\"num\": 154, \"txt\": \"154. Me merezco el sufrimiento que he padecido a lo largo de mi vida.\"}, {\"num\": 155, \"txt\": \"155. Mis sentimientos hacia las personas importantes de mi vida, muchas veces han oscilado entre amarlas y odiarlas.\"}, {\"num\": 156, \"txt\": \"156. Mis padres nunca se pon\u00edan de acuerdo entre ellos.\"}, {\"num\": 157, \"txt\": \"157. En alguna ocasi\u00f3n he bebido diez copas o m\u00e1s sin llegar a emborracharme.\"}, {\"num\": 158, \"txt\": \"158. Cuando estoy en una reuni\u00f3n social, en grupo, casi siempre me siento tenso y controlado.\"}, {\"num\": 159, \"txt\": \"159. Tengo en alta estima las normas y reglas porque son una buena gu\u00eda a seguir.\"}, {\"num\": 160, \"txt\": \"160. Desde que era ni\u00f1o he ido perdiendo contacto con la realidad. POR FAVOR, NO SE DETENGA. CONTINUE EN LA P\u00c1GINA SIGUIENTE\"}, {\"num\": 161, \"txt\": \"161. Rara vez me emociono mucho con algo.\"}, {\"num\": 162, \"txt\": \"162. Habitualmente he sido un andariego inquieto, vagando de un sitio a otro sin tener idea de d\u00f3nde terminar\u00eda.\"}, {\"num\": 163, \"txt\": \"163. No soporto a las personas que llegan tarde a las citas.\"}, {\"num\": 164, \"txt\": \"164. Gente sin escr\u00fapulos intenta con frecuencia aprovecharse de lo que yo he realizado o ideado.\"}, {\"num\": 165, \"txt\": \"165. Me irrita mucho que alguien me pida que haga las cosas a su modo en vez de al m\u00edo.\"}, {\"num\": 166, \"txt\": \"166. Tengo habilidad para tener \u00e9xito en casi todo lo que hago.\"}, {\"num\": 167, \"txt\": \"167. \u00daltimamente me siento completamente destrozado.\"}, {\"num\": 168, \"txt\": \"168. A la gente que quiero, parece que la animo a que me hiera.\"}, {\"num\": 169, \"txt\": \"169. Nunca he tenido pelo, ni en mi cabeza ni en mi cuerpo.\"}, {\"num\": 170, \"txt\": \"170. Cuando estoy con otras personas me gusta ser el centro de atenci\u00f3n.\"}, {\"num\": 171, \"txt\": \"171. Personas que en un principio he admirado grandemente, m\u00e1s tarde me han defraudado al conocer la realidad.\"}, {\"num\": 172, \"txt\": \"172. Soy el tipo de persona que puede abordar a cualquiera y echarle una bronca.\"}, {\"num\": 173, \"txt\": \"173. Prefiero estar con gente que me proteger\u00e1.\"}, {\"num\": 174, \"txt\": \"174. He tenido muchos per\u00edodos en mi vida que he estado tan animado y con energ\u00eda que luego he estado bajo de \u00e1nimo.\"}, {\"num\": 175, \"txt\": \"175. En el pasado he tenido dificultades para abandonar el abuso de drogas y alcohol.\"}]",
        json.dumps({"escalas": 24, "validez": ["V", "X", "Y", "Z"]})
    )
    cursor.execute("""
        INSERT INTO tests_definiciones 
        (code, nombre, siglas, categoria, descripcion, instrucciones, escala_opciones_json, items_json, reglas_correccion_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(code) DO UPDATE SET
            nombre=excluded.nombre,
            descripcion=excluded.descripcion,
            instrucciones=excluded.instrucciones,
            escala_opciones_json=excluded.escala_opciones_json,
            items_json=excluded.items_json,
            reglas_correccion_json=excluded.reglas_correccion_json
    """, mcmi_def)
    db.commit()




MCMI_II_MATRIX = {"1": [["5", 1, 3], ["6A", 1, 2], ["6B", 1, 2], ["8A", 1, 1], ["T", 1, 2]], "2": [["1", 1, 3], ["2", 1, 1], ["5", 1, 1], ["S", 1, 2]], "3": [["Z", 1, 1], ["2", 1, 3], ["4", 2, 1], ["S", 1, 2], ["SS", 1, 1]], "4": [["Y", 1, 1], ["3", 2, 2], ["5", 1, 2], ["6B", 1, 3], ["7", 1, 1], ["8A", 1, 1]], "5": [["Z", 1, 1], ["C", 1, 2], ["H", 1, 1], ["D", 1, 2], ["CC", 1, 3]], "6": [["5", 1, 3], ["P", 1, 1], ["T", 1, 1]], "7": [["3", 2, 1], ["4", 1, 1], ["6A", 1, 3], ["6B", 1, 1], ["7", 2, 1], ["C", 1, 1], ["T", 1, 2]], "8": [["Z", 1, 1], ["2", 1, 3], ["5", 2, 1], ["8B", 1, 1], ["S", 1, 2], ["A", 1, 1], ["D", 1, 2], ["B", 2, 1], ["SS", 1, 1]], "9": [["4", 1, 2], ["6B", 1, 3], ["8A", 1, 2], ["T", 1, 2]], "10": [["1", 1, 2], ["3", 1, 3], ["8B", 1, 2], ["S", 1, 1]], "11": [["N", 1, 3]], "12": [["3", 2, 1], ["5", 1, 1], ["6A", 1, 2], ["6B", 1, 3], ["8A", 1, 1], ["P", 1, 1], ["T", 1, 1]], "13": [["1", 1, 3], ["S", 1, 1], ["SS", 1, 1]], "14": [["Y", 1, 1], ["1", 2, 1], ["2", 2, 1], ["4", 1, 3], ["5", 1, 2], ["S", 2, 1], ["N", 1, 2], ["T", 1, 1]], "15": [["5", 1, 3], ["6A", 1, 1], ["P", 1, 2], ["PP", 1, 1]], "16": [["1", 1, 1], ["5", 1, 2], ["8A", 1, 2], ["8B", 1, 2], ["P", 1, 3], ["A", 1, 1], ["PP", 1, 2]], "17": [["N", 1, 1], ["B", 1, 3]], "18": [["Z", 1, 1], ["8B", 1, 1], ["A", 1, 3], ["H", 1, 2], ["B", 1, 2]], "19": [["1", 1, 3], ["2", 1, 2], ["4", 2, 1], ["S", 1, 1], ["N", 2, 1], ["SS", 1, 1], ["CC", 1, 1]], "20": [["1", 2, 2], ["4", 1, 3], ["6A", 1, 2], ["7", 2, 2], ["N", 1, 2], ["T", 1, 2]], "21": [["2", 2, 1], ["3", 2, 1], ["6B", 1, 2], ["7", 1, 3], ["8A", 1, 1], ["P", 1, 1]], "22": [["1", 1, 1], ["5", 1, 1], ["6A", 1, 2], ["8A", 1, 3], ["C", 1, 2], ["P", 1, 1], ["B", 1, 1], ["T", 1, 2]], "23": [["Z", 1, 1], ["2", 1, 2], ["8A", 1, 1], ["8B", 1, 3], ["S", 1, 1], ["C", 1, 2], ["B", 1, 1], ["SS", 1, 1]], "24": [["Z", 1, 1], ["S", 1, 3], ["P", 1, 2], ["SS", 1, 1], ["PP", 1, 2]], "25": [["Z", 1, 1], ["1", 1, 1], ["2", 1, 2], ["8A", 1, 1], ["8B", 1, 1], ["S", 1, 1], ["C", 1, 3], ["D", 1, 1], ["B", 1, 1]], "26": [["Z", 1, 1], ["C", 1, 2], ["A", 1, 1], ["H", 1, 1], ["D", 1, 2], ["CC", 1, 3]], "27": [["Z", 1, 1], ["2", 1, 2], ["C", 1, 2], ["D", 1, 3], ["B", 1, 1]], "28": [["1", 2, 1], ["2", 2, 1], ["3", 2, 1], ["4", 1, 3], ["5", 1, 1], ["8A", 1, 2], ["8B", 1, 2], ["N", 1, 2]], "29": [["A", 1, 2], ["H", 1, 3], ["SS", 1, 1]], "30": [["6B", 1, 3], ["P", 1, 1], ["T", 1, 1]], "31": [["3", 1, 3], ["5", 2, 1], ["6B", 2, 1], ["8B", 1, 1], ["S", 1, 2], ["H", 1, 1], ["SS", 1, 1]], "32": [["2", 1, 2], ["5", 1, 1], ["6A", 1, 2], ["6B", 1, 1], ["7", 1, 1], ["P", 1, 3], ["T", 1, 1], ["PP", 1, 1]], "33": [["Z", 1, 1], ["1", 1, 2], ["A", 1, 2], ["H", 1, 3], ["CC", 1, 2]], "34": [["Y", 1, 1], ["1", 1, 3], ["2", 1, 1], ["3", 1, 2], ["6A", 2, 1]], "35": [["C", 1, 2], ["B", 1, 1], ["T", 1, 3]], "36": [["Z", 1, 1], ["C", 1, 1], ["A", 1, 1], ["H", 1, 1], ["D", 1, 2], ["CC", 1, 3]], "37": [["4", 1, 1], ["5", 1, 3], ["P", 1, 2], ["N", 1, 1]], "38": [["6A", 1, 2], ["6B", 1, 1], ["S", 1, 2], ["P", 1, 3], ["SS", 1, 2], ["PP", 1, 2]], "39": [["Y", 1, 1], ["4", 2, 1], ["7", 1, 3], ["P", 1, 1], ["PP", 1, 1]], "40": [["3", 2, 1], ["4", 1, 1], ["6A", 1, 3], ["6B", 1, 1], ["7", 2, 1], ["C", 1, 1], ["N", 1, 1], ["B", 1, 1], ["T", 1, 2]], "41": [["3", 2, 1], ["4", 1, 1], ["5", 1, 2], ["6B", 1, 3], ["P", 1, 1], ["H", 2, 1], ["D", 2, 1]], "42": [["3", 1, 3], ["4", 1, 2], ["5", 2, 2], ["6A", 2, 2], ["6B", 2, 2], ["8B", 1, 2], ["H", 1, 1], ["N", 2, 1]], "43": [["Z", 1, 1], ["3", 2, 1], ["4", 1, 2], ["5", 1, 1], ["6A", 1, 2], ["6B", 1, 1], ["7", 2, 1], ["8A", 1, 2], ["C", 1, 3], ["P", 1, 1], ["T", 1, 2]], "44": [["6A", 1, 1], ["6B", 1, 3], ["C", 1, 1], ["P", 1, 1], ["T", 1, 1]], "45": [["Z", 1, 1], ["2", 1, 1], ["5", 2, 1], ["8B", 1, 2], ["D", 1, 3], ["CC", 1, 2]], "46": [["1", 1, 1], ["7", 1, 3], ["P", 1, 2], ["D", 1, 1], ["B", 1, 1]], "47": [["1", 1, 2], ["2", 1, 2], ["S", 1, 3], ["CC", 1, 2]], "48": [["1", 2, 2], ["4", 1, 3], ["6A", 1, 1], ["7", 2, 2], ["S", 2, 1]], "49": [["Z", 1, 1], ["2", 1, 3], ["3", 1, 1], ["S", 1, 2]], "50": [["Z", 1, 1], ["7", 2, 1], ["8A", 1, 3], ["C", 1, 2], ["H", 1, 1], ["N", 1, 2], ["T", 1, 1], ["CC", 1, 2]], "51": [["Z", 1, 1], ["4", 2, 1], ["5", 2, 1], ["8A", 1, 1], ["8B", 1, 2], ["C", 1, 1], ["A", 1, 3], ["H", 1, 2], ["D", 1, 2], ["CC", 1, 1]], "52": [["B", 2, 2]], "53": [["Z", 1, 1], ["1", 1, 1], ["S", 1, 1], ["C", 1, 1], ["A", 1, 2], ["H", 1, 2], ["D", 1, 2], ["CC", 1, 3]], "54": [["Z", 1, 1], ["3", 1, 1], ["8B", 1, 2], ["C", 1, 1], ["A", 1, 1], ["D", 1, 3], ["B", 1, 2], ["CC", 1, 1]], "55": [["5", 1, 1], ["6A", 1, 2], ["8A", 1, 3], ["P", 1, 1], ["T", 1, 1]], "56": [["2", 1, 2], ["4", 1, 1], ["8B", 1, 2], ["C", 1, 3], ["H", 1, 1], ["D", 1, 1], ["CC", 1, 2]], "57": [["2", 1, 2], ["3", 1, 2], ["8B", 1, 3], ["C", 1, 1], ["CC", 1, 1]], "58": [["Z", 1, 1], ["6B", 1, 1], ["8A", 1, 1], ["C", 1, 3], ["N", 1, 1], ["T", 1, 2], ["CC", 1, 1]], "59": [["Z", 1, 1], ["C", 1, 2], ["D", 1, 2], ["CC", 1, 3]], "60": [["Y", 1, 1], ["1", 2, 1], ["3", 1, 2], ["4", 1, 3], ["5", 1, 1], ["7", 2, 1], ["S", 2, 1], ["H", 1, 1], ["N", 1, 2], ["T", 1, 1]], "61": [["Y", 1, 1], ["4", 2, 2], ["7", 1, 3], ["8A", 2, 1], ["P", 1, 1], ["T", 2, 1]], "62": [["V", 1, 1]], "63": [["Z", 1, 1], ["2", 1, 3], ["8B", 1, 1], ["S", 1, 2], ["P", 1, 1]], "64": [["6A", 1, 1], ["6B", 1, 2], ["7", 1, 2], ["8A", 1, 2], ["P", 1, 3]], "65": [["8B", 1, 3], ["C", 1, 1], ["D", 1, 2], ["B", 1, 1], ["CC", 1, 1]], "66": [["Z", 1, 1], ["4", 1, 2], ["6B", 1, 1], ["7", 2, 1], ["8A", 1, 3], ["C", 1, 2], ["H", 1, 1], ["N", 1, 1], ["T", 1, 1]], "67": [["Z", 1, 1], ["C", 1, 1], ["A", 1, 3], ["H", 1, 2], ["N", 1, 1], ["CC", 1, 1]], "68": [["Z", 1, 1], ["P", 1, 1], ["H", 1, 3], ["SS", 1, 2]], "69": [["S", 1, 3], ["SS", 1, 2], ["PP", 1, 2]], "70": [["B", 1, 1], ["T", 1, 3]], "71": [["Z", 1, 1], ["6B", 2, 1], ["8B", 1, 1], ["A", 1, 2], ["H", 1, 3], ["D", 1, 2]], "72": [["Z", 1, 1], ["C", 1, 1], ["H", 1, 3], ["D", 1, 2], ["CC", 1, 2]], "73": [["6A", 1, 2], ["8A", 1, 2], ["8B", 1, 1], ["C", 1, 3], ["N", 1, 1], ["B", 1, 2], ["T", 1, 2]], "74": [["3", 2, 1], ["6A", 1, 2], ["6B", 1, 2], ["7", 1, 1], ["8A", 1, 2], ["8B", 2, 1], ["C", 1, 1], ["P", 1, 3], ["SS", 1, 1], ["PP", 1, 1]], "75": [["Y", 1, 1], ["3", 1, 1], ["7", 1, 3], ["P", 1, 1]], "76": [["Z", 1, 1], ["D", 1, 2], ["CC", 1, 3]], "77": [["2", 1, 3], ["3", 1, 2], ["4", 2, 1], ["6A", 2, 1], ["6B", 2, 2], ["7", 2, 1], ["8A", 1, 2], ["8B", 1, 2], ["S", 1, 2], ["C", 1, 1], ["SS", 1, 2]], "78": [["Y", 1, 1], ["1", 2, 1], ["3", 1, 3], ["5", 2, 1], ["6A", 2, 2], ["6B", 2, 2], ["7", 1, 1], ["C", 1, 1], ["A", 1, 1], ["H", 1, 1]], "79": [["Z", 1, 1], ["C", 1, 2], ["D", 1, 3], ["CC", 1, 2]], "80": [["5", 1, 1], ["6A", 1, 2], ["6B", 1, 1], ["P", 1, 2], ["B", 1, 1], ["T", 1, 2], ["SS", 1, 2], ["PP", 1, 3]], "81": [["1", 1, 3], ["2", 1, 1], ["3", 1, 2], ["6A", 2, 2], ["7", 1, 1], ["8B", 1, 1], ["CC", 1, 1]], "82": [["Z", 1, 1], ["6B", 1, 2], ["8A", 1, 2], ["8B", 1, 1], ["C", 1, 3], ["T", 1, 2], ["SS", 1, 1], ["CC", 1, 1]], "83": [["1", 1, 2], ["2", 1, 2], ["S", 1, 3], ["D", 1, 2], ["SS", 1, 2]], "84": [["6B", 1, 2], ["P", 1, 3], ["PP", 1, 2]], "85": [["1", 1, 1], ["2", 1, 1], ["5", 1, 1], ["6A", 1, 1], ["S", 1, 2], ["P", 1, 3], ["SS", 1, 2], ["PP", 1, 2]], "86": [["Y", 1, 1], ["4", 1, 3], ["5", 1, 2], ["6A", 1, 2], ["6B", 1, 1], ["7", 2, 2], ["8A", 1, 2], ["N", 1, 2], ["D", 2, 1], ["T", 1, 2]], "87": [["6A", 1, 2], ["B", 1, 3]], "88": [["Y", 1, 1], ["7", 1, 3]], "89": [["Y", 1, 1], ["4", 1, 1], ["5", 1, 3], ["P", 1, 2], ["N", 1, 1], ["T", 1, 1], ["PP", 1, 1]], "90": [["V", 1, 1]], "91": [["3", 2, 1], ["4", 1, 1], ["5", 1, 3], ["6A", 1, 2], ["6B", 1, 2], ["C", 1, 2], ["T", 1, 2]], "92": [["3", 2, 1], ["6A", 1, 3], ["7", 2, 1], ["T", 1, 2]], "93": [["Y", 1, 1], ["N", 1, 3], ["B", 1, 1], ["T", 1, 1]], "94": [["6A", 1, 3], ["C", 1, 1], ["T", 1, 1]], "95": [["1", 2, 1], ["4", 1, 1], ["6B", 1, 1], ["7", 2, 1], ["8A", 1, 3], ["C", 1, 2], ["N", 1, 1], ["B", 1, 2], ["T", 1, 2], ["CC", 1, 1]], "96": [["Z", 1, 1], ["A", 1, 2], ["H", 1, 3], ["D", 1, 2], ["B", 1, 1], ["CC", 1, 2]], "97": [["Z", 1, 1], ["3", 1, 2], ["C", 1, 2], ["A", 1, 2], ["D", 1, 3], ["B", 1, 2]], "98": [["P", 1, 1], ["H", 1, 2], ["N", 1, 1], ["SS", 1, 3], ["PP", 1, 2]], "99": [["Z", 1, 1], ["8B", 1, 1], ["C", 1, 1], ["A", 1, 1], ["D", 1, 3], ["CC", 1, 1]], "100": [["Z", 1, 1], ["S", 1, 2], ["P", 1, 2], ["PP", 1, 3]], "101": [["3", 2, 1], ["6A", 1, 1], ["6B", 1, 3], ["8A", 1, 2], ["C", 1, 2], ["N", 1, 1], ["T", 1, 1]], "102": [["Z", 1, 1], ["2", 1, 2], ["S", 1, 3], ["H", 1, 1], ["SS", 1, 2]], "103": [["Y", 1, 1], ["1", 2, 1], ["4", 1, 2], ["5", 1, 2], ["6A", 1, 3], ["7", 2, 1], ["C", 1, 1], ["P", 1, 2], ["N", 1, 2], ["B", 1, 1], ["T", 1, 2]], "104": [["6A", 1, 1], ["8A", 1, 3], ["C", 1, 1], ["B", 1, 1], ["T", 1, 1]], "105": [["B", 1, 2], ["T", 1, 3]], "106": [["Y", 1, 1], ["1", 1, 2], ["2", 1, 1], ["3", 1, 3], ["5", 2, 1], ["6B", 2, 1], ["8B", 1, 2]], "107": [["6B", 1, 2], ["8A", 1, 3], ["D", 1, 1]], "108": [["Z", 1, 1], ["1", 1, 1], ["S", 1, 1], ["C", 1, 1], ["A", 1, 1], ["D", 1, 3], ["B", 1, 1], ["CC", 1, 2]], "109": [["2", 1, 1], ["A", 1, 2], ["H", 1, 1], ["D", 1, 2], ["B", 1, 2], ["SS", 1, 3], ["CC", 1, 2]], "110": [["Z", 1, 1], ["2", 1, 2], ["3", 1, 1], ["8A", 1, 1], ["8B", 1, 3], ["C", 1, 1], ["D", 1, 1], ["CC", 1, 1]], "111": [["1", 2, 1], ["4", 1, 3], ["5", 1, 2], ["6A", 1, 1], ["7", 2, 1], ["N", 1, 1], ["B", 1, 1], ["T", 1, 1]], "112": [["S", 1, 3], ["SS", 1, 2], ["PP", 1, 1]], "113": [["2", 1, 1], ["6A", 1, 1], ["S", 1, 2], ["C", 1, 3], ["T", 1, 1]], "114": [["Z", 1, 1], ["A", 1, 3], ["H", 1, 2], ["B", 1, 1], ["T", 1, 1]], "115": [["Z", 1, 1], ["2", 1, 2], ["6B", 1, 2], ["8A", 1, 2], ["8B", 1, 2], ["C", 1, 3], ["T", 1, 2], ["SS", 1, 2]], "116": [["6A", 1, 3], ["T", 1, 1]], "117": [["Z", 1, 1], ["A", 1, 3], ["H", 1, 1], ["B", 1, 1], ["T", 1, 2], ["CC", 1, 1]], "118": [["Z", 1, 1], ["2", 1, 2], ["S", 1, 3], ["H", 1, 1]], "119": [["B", 1, 3]], "120": [["Z", 1, 1], ["2", 1, 3], ["8A", 1, 1], ["8B", 1, 2], ["S", 1, 2], ["T", 1, 1], ["SS", 1, 2]], "121": [["6B", 1, 2], ["8B", 1, 3], ["N", 1, 1]], "122": [["Y", 1, 1], ["B", 2, 2]], "123": [["8A", 1, 2], ["S", 1, 2], ["P", 1, 2], ["T", 1, 1], ["PP", 1, 3]], "124": [["1", 1, 2], ["S", 1, 2], ["SS", 1, 3]], "125": [["Y", 1, 1], ["1", 2, 1], ["2", 2, 1], ["3", 1, 1], ["4", 1, 3], ["5", 1, 2], ["N", 1, 2], ["B", 1, 1], ["T", 1, 1]], "126": [["Y", 1, 1], ["4", 2, 1], ["5", 1, 1], ["7", 1, 3], ["P", 1, 2], ["PP", 1, 1]], "127": [["P", 1, 1], ["N", 1, 1], ["SS", 1, 3]], "128": [["Z", 1, 1], ["4", 1, 1], ["7", 2, 1], ["8A", 1, 2], ["8B", 1, 1], ["C", 1, 3], ["N", 1, 2], ["B", 1, 1], ["T", 1, 1]], "129": [["5", 1, 3], ["6A", 1, 2], ["6B", 1, 2], ["8A", 1, 1], ["C", 1, 2], ["P", 1, 2], ["T", 1, 2]], "130": [["4", 1, 1], ["5", 1, 1], ["6A", 1, 3], ["S", 1, 1], ["C", 1, 1], ["B", 1, 1], ["T", 1, 1]], "131": [["5", 1, 3], ["P", 1, 2], ["N", 1, 1], ["PP", 1, 2]], "132": [["Z", 1, 1], ["8B", 1, 2], ["C", 1, 1], ["A", 1, 1], ["D", 1, 3]], "133": [["2", 1, 1], ["3", 1, 3], ["4", 1, 2], ["8B", 1, 1], ["S", 1, 2]], "134": [["5", 1, 1], ["6B", 1, 3], ["7", 1, 2], ["N", 1, 2]], "135": [["5", 1, 1], ["6B", 1, 1], ["8A", 1, 3], ["C", 1, 1], ["P", 1, 1], ["B", 1, 1]], "136": [["Z", 1, 1], ["S", 1, 1], ["C", 1, 2], ["D", 1, 2], ["CC", 1, 3]], "137": [["Y", 1, 1], ["4", 1, 3], ["5", 1, 2], ["H", 1, 1], ["N", 1, 2], ["B", 1, 1], ["T", 1, 1]], "138": [["Y", 1, 1], ["7", 1, 3], ["P", 1, 1], ["PP", 1, 1]], "139": [["2", 1, 1], ["8A", 1, 1], ["8B", 1, 3], ["C", 1, 1], ["D", 1, 1]], "140": [["6A", 1, 1], ["C", 1, 2], ["B", 1, 1], ["T", 1, 3]], "141": [["1", 1, 1], ["2", 1, 3], ["8B", 1, 1], ["S", 1, 2], ["SS", 1, 1]], "142": [["1", 1, 1], ["4", 1, 1], ["5", 1, 3], ["6A", 1, 2], ["6B", 1, 1], ["C", 1, 2]], "143": [["1", 1, 3], ["5", 1, 1], ["P", 1, 1], ["PP", 1, 1]], "144": [["6A", 1, 2], ["C", 1, 1], ["B", 1, 2], ["T", 1, 3]], "145": [["3", 1, 3], ["6B", 2, 1], ["7", 2, 2], ["8B", 1, 2], ["A", 1, 1], ["H", 1, 1]], "146": [["5", 1, 1], ["6B", 1, 1], ["P", 1, 3], ["T", 1, 1], ["SS", 1, 2], ["PP", 1, 2]], "147": [["2", 1, 1], ["3", 2, 1], ["6A", 1, 3], ["6B", 1, 1], ["S", 1, 1], ["C", 1, 1], ["SS", 1, 1]], "148": [["6B", 1, 3], ["7", 1, 2]], "149": [["Y", 1, 1], ["3", 1, 1], ["5", 2, 2], ["7", 1, 3], ["8A", 2, 2], ["B", 1, 1]], "150": [["1", 1, 2], ["2", 1, 2], ["S", 1, 3]], "151": [["N", 1, 3]], "152": [["V", 1, 1]], "153": [["Y", 1, 1], ["7", 1, 3], ["A", 1, 1]], "154": [["8B", 1, 3], ["C", 1, 1], ["D", 1, 2], ["CC", 1, 1]], "155": [["2", 1, 2], ["6B", 1, 2], ["7", 2, 1], ["8A", 1, 2], ["8B", 1, 2], ["C", 1, 3], ["D", 1, 1], ["B", 1, 1], ["T", 1, 1]], "156": [["8A", 1, 3], ["C", 1, 2], ["SS", 1, 1]], "157": [["6A", 1, 1], ["B", 1, 3]], "158": [["Z", 1, 1], ["2", 1, 3], ["4", 2, 2], ["5", 2, 2], ["S", 1, 2], ["N", 2, 1]], "159": [["Y", 1, 1], ["1", 1, 1], ["3", 1, 3], ["7", 1, 2], ["8A", 2, 2], ["B", 1, 1]], "160": [["1", 1, 1], ["2", 1, 1], ["S", 1, 1], ["SS", 1, 3]], "161": [["1", 1, 3], ["7", 1, 2], ["S", 1, 1], ["N", 2, 1], ["SS", 1, 1]], "162": [["3", 2, 1], ["4", 1, 1], ["6A", 1, 3], ["S", 1, 1], ["C", 1, 1], ["B", 1, 1], ["T", 1, 2]], "163": [["2", 2, 1], ["3", 2, 1], ["5", 1, 1], ["6B", 1, 3], ["7", 1, 2], ["P", 1, 1]], "164": [["S", 1, 2], ["P", 1, 3], ["SS", 1, 2], ["PP", 1, 2]], "165": [["5", 1, 2], ["6A", 1, 2], ["6B", 1, 1], ["8A", 1, 3], ["S", 1, 1], ["C", 1, 1], ["P", 1, 1], ["B", 1, 1], ["T", 1, 1]], "166": [["Y", 1, 1], ["4", 1, 2], ["5", 1, 3], ["6B", 1, 2], ["S", 2, 2], ["A", 2, 1], ["N", 1, 1], ["D", 2, 2], ["T", 1, 1]], "167": [["Z", 1, 1], ["8B", 1, 1], ["C", 1, 1], ["A", 1, 2], ["D", 1, 1], ["SS", 1, 3]], "168": [["3", 1, 1], ["8B", 1, 3], ["C", 1, 1], ["D", 1, 1]], "169": [["V", 1, 1]], "170": [["4", 1, 3], ["5", 1, 2], ["H", 1, 1], ["N", 1, 2]], "171": [["2", 1, 2], ["4", 1, 1], ["5", 1, 2], ["6A", 1, 1], ["8A", 1, 1], ["8B", 1, 1], ["C", 1, 3], ["P", 1, 1], ["B", 1, 1], ["T", 1, 1]], "172": [["4", 1, 1], ["5", 1, 2], ["6A", 1, 3], ["P", 1, 1], ["N", 1, 1], ["T", 1, 1]], "173": [["3", 1, 3], ["4", 1, 1], ["8B", 1, 1], ["C", 1, 1], ["H", 1, 1]], "174": [["N", 1, 3]], "175": [["B", 1, 2], ["T", 1, 3]]}
MCMI_II_TB_TABLES = {"V": {}, "Y": {"0": 0, "1": 5, "2": 10, "3": 15, "4": 20, "5": 25, "6": 30, "7": 34, "8": 39, "9": 43, "10": 46, "11": 50, "12": 56, "13": 62, "14": 67, "15": 72, "16": 75, "17": 78, "18": 82, "19": 85, "20": 90, "21": 95, "22": 100, "23": 100, "24": 100, "25": 100, "26": 100, "27": 100, "28": 100, "29": 100, "30": 100, "31": 100, "32": 100, "33": 100, "34": 100, "35": 100, "36": 100, "37": 100, "38": 100, "39": 100, "40": 100, "41": 100, "42": 100, "43": 100, "44": 100, "45": 100, "46": 100, "47": 100, "48": 100, "49": 100, "50": 100, "51": 100, "52": 100, "53": 100, "54": 100, "55": 100, "56": 100, "57": 100, "58": 100, "59": 100, "60": 100, "61": 100, "62": 100, "63": 100, "64": 100, "65": 100, "66": 100, "67": 100, "68": 100, "69": 100, "70": 100, "71": 100, "72": 100, "73": 100, "74": 100, "75": 100, "76": 100, "77": 100, "78": 100, "79": 100, "80": 100, "81": 100, "82": 100, "83": 100, "84": 100, "85": 100, "86": 100, "87": 100, "88": 100, "89": 100, "90": 100, "91": 100, "92": 100, "93": 100, "94": 100, "95": 100, "96": 100, "97": 100, "98": 100, "99": 100}, "Z": {"0": 12, "1": 24, "2": 35, "3": 38, "4": 42, "5": 45, "6": 48, "7": 52, "8": 55, "9": 57, "10": 59, "11": 61, "12": 63, "13": 65, "14": 67, "15": 69, "16": 70, "17": 71, "18": 73, "19": 75, "20": 76, "21": 77, "22": 78, "23": 79, "24": 80, "25": 82, "26": 84, "27": 85, "28": 87, "29": 89, "30": 91, "31": 93, "32": 95, "33": 97, "34": 100, "35": 100, "36": 100, "37": 100, "38": 100, "39": 100, "40": 100, "41": 100, "42": 100, "43": 100, "44": 100, "45": 100, "46": 100, "47": 100, "48": 100, "49": 100, "50": 100, "51": 100, "52": 100, "53": 100, "54": 100, "55": 100, "56": 100, "57": 100, "58": 100, "59": 100, "60": 100, "61": 100, "62": 100, "63": 100, "64": 100, "65": 100, "66": 100, "67": 100, "68": 100, "69": 100, "70": 100, "71": 100, "72": 100, "73": 100, "74": 100, "75": 100, "76": 100, "77": 100, "78": 100, "79": 100, "80": 100, "81": 100, "82": 100, "83": 100, "84": 100, "85": 100, "86": 100, "87": 100, "88": 100, "89": 100, "90": 100, "91": 100, "92": 100, "93": 100, "94": 100, "95": 100, "96": 100, "97": 100, "98": 100, "99": 100}, "1": {"0": 0, "1": 0, "2": 0, "3": 0, "4": 0, "5": 0, "6": 0, "7": 13, "8": 18, "9": 23, "10": 28, "11": 33, "12": 38, "13": 43, "14": 48, "15": 53, "16": 58, "17": 63, "18": 66, "19": 67, "20": 69, "21": 70, "22": 71, "23": 71, "24": 73, "25": 74, "26": 76, "27": 78, "28": 81, "29": 83, "30": 86, "31": 88, "32": 91, "33": 96, "34": 101, "35": 106, "36": 108, "37": 109, "38": 111, "39": 116, "40": 121, "41": 121, "42": 121, "43": 121, "44": 121, "45": 121, "46": 121, "47": 121, "48": 121, "49": 121, "50": 121, "51": 121, "52": 121, "53": 121, "54": 121, "55": 121, "56": 121, "57": 121, "58": 121, "59": 121, "60": 121, "61": 121, "62": 121, "63": 121, "64": 121, "65": 121, "66": 121, "67": 121, "68": 121, "69": 121, "70": 121, "71": 121, "72": 121, "73": 121, "74": 121, "75": 121, "76": 121, "77": 121, "78": 121, "79": 121, "80": 121, "81": 121, "82": 121, "83": 121, "84": 121, "85": 121, "86": 121, "87": 121, "88": 121, "89": 121, "90": 121, "91": 121, "92": 121, "93": 121, "94": 121, "95": 121, "96": 121, "97": 121, "98": 121, "99": 121}, "2": {"0": 6, "1": 6, "2": 6, "3": 6, "4": 6, "5": 6, "6": 6, "7": 16, "8": 26, "9": 41, "10": 44, "11": 47, "12": 50, "13": 53, "14": 57, "15": 61, "16": 66, "17": 66, "18": 67, "19": 68, "20": 68, "21": 69, "22": 71, "23": 74, "24": 76, "25": 78, "26": 81, "27": 82, "28": 83, "29": 84, "30": 86, "31": 88, "32": 90, "33": 94, "34": 97, "35": 100, "36": 101, "37": 103, "38": 105, "39": 106, "40": 108, "41": 110, "42": 112, "43": 114, "44": 116, "45": 118, "46": 121, "47": 121, "48": 121, "49": 121, "50": 121, "51": 121, "52": 121, "53": 121, "54": 121, "55": 121, "56": 121, "57": 121, "58": 121, "59": 121, "60": 121, "61": 121, "62": 121, "63": 121, "64": 121, "65": 121, "66": 121, "67": 121, "68": 121, "69": 121, "70": 121, "71": 121, "72": 121, "73": 121, "74": 121, "75": 121, "76": 121, "77": 121, "78": 121, "79": 121, "80": 121, "81": 121, "82": 121, "83": 121, "84": 121, "85": 121, "86": 121, "87": 121, "88": 121, "89": 121, "90": 121, "91": 121, "92": 121, "93": 121, "94": 121, "95": 121, "96": 121, "97": 121, "98": 121, "99": 121}, "3": {"0": 0, "1": 0, "2": 0, "3": 0, "4": 0, "5": 0, "6": 0, "7": 0, "8": 0, "9": 0, "10": 0, "11": 0, "12": 0, "13": 0, "14": 0, "15": 0, "16": 0, "17": 5, "18": 10, "19": 23, "20": 34, "21": 40, "22": 42, "23": 50, "24": 59, "25": 66, "26": 66, "27": 66, "28": 69, "29": 71, "30": 72, "31": 74, "32": 77, "33": 78, "34": 80, "35": 81, "36": 85, "37": 89, "38": 91, "39": 93, "40": 94, "41": 94, "42": 94, "43": 95, "44": 96, "45": 98, "46": 100, "47": 102, "48": 106, "49": 111, "50": 116, "51": 121, "52": 121, "53": 121, "54": 121, "55": 121, "56": 121, "57": 121, "58": 121, "59": 121, "60": 121, "61": 121, "62": 121, "63": 121, "64": 121, "65": 121, "66": 121, "67": 121, "68": 121, "69": 121, "70": 121, "71": 121, "72": 121, "73": 121, "74": 121, "75": 121, "76": 121, "77": 121, "78": 121, "79": 121, "80": 121, "81": 121, "82": 121, "83": 121, "84": 121, "85": 121, "86": 121, "87": 121, "88": 121, "89": 121, "90": 121, "91": 121, "92": 121, "93": 121, "94": 121, "95": 121, "96": 121, "97": 121, "98": 121, "99": 121}, "4": {"0": 6, "1": 6, "2": 6, "3": 6, "4": 6, "5": 6, "6": 6, "7": 6, "8": 6, "9": 6, "10": 6, "11": 6, "12": 6, "13": 6, "14": 11, "15": 13, "16": 16, "17": 18, "18": 26, "19": 36, "20": 41, "21": 44, "22": 47, "23": 50, "24": 53, "25": 55, "26": 57, "27": 59, "28": 61, "29": 63, "30": 66, "31": 67, "32": 68, "33": 69, "34": 70, "35": 71, "36": 73, "37": 74, "38": 76, "39": 78, "40": 79, "41": 80, "42": 81, "43": 82, "44": 83, "45": 85, "46": 87, "47": 89, "48": 90, "49": 91, "50": 94, "51": 96, "52": 99, "53": 103, "54": 108, "55": 112, "56": 116, "57": 118, "58": 121, "59": 121, "60": 121, "61": 121, "62": 121, "63": 121, "64": 121, "65": 121, "66": 121, "67": 121, "68": 121, "69": 121, "70": 121, "71": 121, "72": 121, "73": 121, "74": 121, "75": 121, "76": 121, "77": 121, "78": 121, "79": 121, "80": 121, "81": 121, "82": 121, "83": 121, "84": 121, "85": 121, "86": 121, "87": 121, "88": 121, "89": 121, "90": 121, "91": 121, "92": 121, "93": 121, "94": 121, "95": 121, "96": 121, "97": 121, "98": 121, "99": 121}, "5": {"0": 0, "1": 0, "2": 0, "3": 0, "4": 0, "5": 0, "6": 0, "7": 0, "8": 0, "9": 0, "10": 0, "11": 0, "12": 0, "13": 0, "14": 0, "15": 0, "16": 5, "17": 12, "18": 19, "19": 23, "20": 27, "21": 32, "22": 35, "23": 38, "24": 41, "25": 44, "26": 47, "27": 49, "28": 51, "29": 52, "30": 55, "31": 61, "32": 66, "33": 67, "34": 69, "35": 70, "36": 72, "37": 73, "38": 75, "39": 77, "40": 80, "41": 81, "42": 83, "43": 86, "44": 88, "45": 90, "46": 92, "47": 93, "48": 96, "49": 98, "50": 100, "51": 101, "52": 101, "53": 102, "54": 103, "55": 104, "56": 104, "57": 105, "58": 106, "59": 108, "60": 110, "61": 112, "62": 114, "63": 116, "64": 118, "65": 119, "66": 120, "67": 121, "68": 121, "69": 121, "70": 121, "71": 121, "72": 121, "73": 121, "74": 121, "75": 121, "76": 121, "77": 121, "78": 121, "79": 121, "80": 121, "81": 121, "82": 121, "83": 121, "84": 121, "85": 121, "86": 121, "87": 121, "88": 121, "89": 121, "90": 121, "91": 121, "92": 121, "93": 121, "94": 121, "95": 121, "96": 121, "97": 121, "98": 121, "99": 121}, "6A": {"0": 0, "1": 0, "2": 0, "3": 0, "4": 0, "5": 0, "6": 0, "7": 0, "8": 9, "9": 13, "10": 17, "11": 22, "12": 27, "13": 32, "14": 37, "15": 42, "16": 44, "17": 47, "18": 49, "19": 52, "20": 54, "21": 57, "22": 59, "23": 62, "24": 64, "25": 66, "26": 67, "27": 68, "28": 69, "29": 70, "30": 71, "31": 72, "32": 73, "33": 74, "34": 75, "35": 77, "36": 79, "37": 81, "38": 83, "39": 85, "40": 87, "41": 88, "42": 91, "43": 94, "44": 98, "45": 101, "46": 104, "47": 106, "48": 108, "49": 110, "50": 112, "51": 114, "52": 116, "53": 118, "54": 121, "55": 121, "56": 121, "57": 121, "58": 121, "59": 121, "60": 121, "61": 121, "62": 121, "63": 121, "64": 121, "65": 121, "66": 121, "67": 121, "68": 121, "69": 121, "70": 121, "71": 121, "72": 121, "73": 121, "74": 121, "75": 121, "76": 121, "77": 121, "78": 121, "79": 121, "80": 121, "81": 121, "82": 121, "83": 121, "84": 121, "85": 121, "86": 121, "87": 121, "88": 121, "89": 121, "90": 121, "91": 121, "92": 121, "93": 121, "94": 121, "95": 121, "96": 121, "97": 121, "98": 121, "99": 121}, "6B": {"0": 0, "1": 0, "2": 0, "3": 0, "4": 0, "5": 0, "6": 0, "7": 0, "8": 0, "9": 0, "10": 0, "11": 0, "12": 8, "13": 15, "14": 25, "15": 35, "16": 37, "17": 39, "18": 41, "19": 43, "20": 45, "21": 47, "22": 49, "23": 50, "24": 52, "25": 54, "26": 56, "27": 62, "28": 66, "29": 67, "30": 68, "31": 70, "32": 73, "33": 75, "34": 78, "35": 79, "36": 80, "37": 83, "38": 86, "39": 88, "40": 89, "41": 93, "42": 96, "43": 98, "44": 100, "45": 102, "46": 104, "47": 105, "48": 106, "49": 114, "50": 116, "51": 118, "52": 119, "53": 121, "54": 121, "55": 121, "56": 121, "57": 121, "58": 121, "59": 121, "60": 121, "61": 121, "62": 121, "63": 121, "64": 121, "65": 121, "66": 121, "67": 121, "68": 121, "69": 121, "70": 121, "71": 121, "72": 121, "73": 121, "74": 121, "75": 121, "76": 121, "77": 121, "78": 121, "79": 121, "80": 121, "81": 121, "82": 121, "83": 121, "84": 121, "85": 121, "86": 121, "87": 121, "88": 121, "89": 121, "90": 121, "91": 121, "92": 121, "93": 121, "94": 121, "95": 121, "96": 121, "97": 121, "98": 121, "99": 121}, "7": {"0": 6, "1": 6, "2": 6, "3": 6, "4": 6, "5": 6, "6": 6, "7": 6, "8": 6, "9": 6, "10": 6, "11": 6, "12": 6, "13": 6, "14": 6, "15": 6, "16": 6, "17": 6, "18": 11, "19": 14, "20": 18, "21": 23, "22": 26, "23": 31, "24": 34, "25": 36, "26": 39, "27": 41, "28": 46, "29": 54, "30": 59, "31": 61, "32": 61, "33": 61, "34": 61, "35": 61, "36": 62, "37": 63, "38": 64, "39": 65, "40": 67, "41": 71, "42": 75, "43": 78, "44": 80, "45": 83, "46": 86, "47": 90, "48": 93, "49": 94, "50": 95, "51": 96, "52": 97, "53": 98, "54": 102, "55": 106, "56": 108, "57": 110, "58": 113, "59": 116, "60": 118, "61": 121, "62": 121, "63": 121, "64": 121, "65": 121, "66": 121, "67": 121, "68": 121, "69": 121, "70": 121, "71": 121, "72": 121, "73": 121, "74": 121, "75": 121, "76": 121, "77": 121, "78": 121, "79": 121, "80": 121, "81": 121, "82": 121, "83": 121, "84": 121, "85": 121, "86": 121, "87": 121, "88": 121, "89": 121, "90": 121, "91": 121, "92": 121, "93": 121, "94": 121, "95": 121, "96": 121, "97": 121, "98": 121, "99": 121}, "8A": {"0": 0, "1": 0, "2": 0, "3": 0, "4": 0, "5": 0, "6": 0, "7": 2, "8": 7, "9": 12, "10": 17, "11": 22, "12": 27, "13": 32, "14": 34, "15": 36, "16": 38, "17": 40, "18": 42, "19": 44, "20": 47, "21": 49, "22": 51, "23": 55, "24": 62, "25": 66, "26": 67, "27": 68, "28": 69, "29": 70, "30": 71, "31": 74, "32": 76, "33": 78, "34": 81, "35": 85, "36": 88, "37": 90, "38": 94, "39": 98, "40": 102, "41": 105, "42": 107, "43": 108, "44": 110, "45": 111, "46": 111, "47": 112, "48": 113, "49": 114, "50": 116, "51": 117, "52": 118, "53": 119, "54": 120, "55": 121, "56": 121, "57": 121, "58": 121, "59": 121, "60": 121, "61": 121, "62": 121, "63": 121, "64": 121, "65": 121, "66": 121, "67": 121, "68": 121, "69": 121, "70": 121, "71": 121, "72": 121, "73": 121, "74": 121, "75": 121, "76": 121, "77": 121, "78": 121, "79": 121, "80": 121, "81": 121, "82": 121, "83": 121, "84": 121, "85": 121, "86": 121, "87": 121, "88": 121, "89": 121, "90": 121, "91": 121, "92": 121, "93": 121, "94": 121, "95": 121, "96": 121, "97": 121, "98": 121, "99": 121}, "8B": {"0": 0, "1": 0, "2": 0, "3": 10, "4": 20, "5": 30, "6": 35, "7": 38, "8": 41, "9": 44, "10": 47, "11": 50, "12": 55, "13": 60, "14": 61, "15": 66, "16": 67, "17": 68, "18": 69, "19": 70, "20": 71, "21": 72, "22": 73, "23": 74, "24": 74, "25": 74, "26": 75, "27": 76, "28": 76, "29": 77, "30": 78, "31": 79, "32": 81, "33": 83, "34": 89, "35": 93, "36": 98, "37": 104, "38": 111, "39": 116, "40": 119, "41": 120, "42": 120, "43": 121, "44": 121, "45": 121, "46": 121, "47": 121, "48": 121, "49": 121, "50": 121, "51": 121, "52": 121, "53": 121, "54": 121, "55": 121, "56": 121, "57": 121, "58": 121, "59": 121, "60": 121, "61": 121, "62": 121, "63": 121, "64": 121, "65": 121, "66": 121, "67": 121, "68": 121, "69": 121, "70": 121, "71": 121, "72": 121, "73": 121, "74": 121, "75": 121, "76": 121, "77": 121, "78": 121, "79": 121, "80": 121, "81": 121, "82": 121, "83": 121, "84": 121, "85": 121, "86": 121, "87": 121, "88": 121, "89": 121, "90": 121, "91": 121, "92": 121, "93": 121, "94": 121, "95": 121, "96": 121, "97": 121, "98": 121, "99": 121}, "S": {"0": 6, "1": 6, "2": 6, "3": 16, "4": 26, "5": 36, "6": 41, "7": 43, "8": 46, "9": 48, "10": 51, "11": 53, "12": 56, "13": 58, "14": 61, "15": 63, "16": 64, "17": 64, "18": 65, "19": 65, "20": 66, "21": 66, "22": 67, "23": 67, "24": 68, "25": 68, "26": 69, "27": 69, "28": 70, "29": 70, "30": 71, "31": 71, "32": 72, "33": 72, "34": 73, "35": 73, "36": 74, "37": 75, "38": 77, "39": 81, "40": 84, "41": 87, "42": 90, "43": 97, "44": 105, "45": 110, "46": 116, "47": 119, "48": 121, "49": 121, "50": 121, "51": 121, "52": 121, "53": 121, "54": 121, "55": 121, "56": 121, "57": 121, "58": 121, "59": 121, "60": 121, "61": 121, "62": 121, "63": 121, "64": 121, "65": 121, "66": 121, "67": 121, "68": 121, "69": 121, "70": 121, "71": 121, "72": 121, "73": 121, "74": 121, "75": 121, "76": 121, "77": 121, "78": 121, "79": 121, "80": 121, "81": 121, "82": 121, "83": 121, "84": 121, "85": 121, "86": 121, "87": 121, "88": 121, "89": 121, "90": 121, "91": 121, "92": 121, "93": 121, "94": 121, "95": 121, "96": 121, "97": 121, "98": 121, "99": 121}, "C": {"0": 0, "1": 0, "2": 0, "3": 0, "4": 0, "5": 11, "6": 16, "7": 21, "8": 26, "9": 31, "10": 36, "11": 41, "12": 42, "13": 43, "14": 44, "15": 45, "16": 46, "17": 48, "18": 50, "19": 53, "20": 56, "21": 58, "22": 59, "23": 61, "24": 63, "25": 66, "26": 66, "27": 66, "28": 66, "29": 66, "30": 66, "31": 67, "32": 68, "33": 69, "34": 70, "35": 71, "36": 72, "37": 73, "38": 73, "39": 73, "40": 74, "41": 74, "42": 75, "43": 75, "44": 75, "45": 75, "46": 76, "47": 76, "48": 77, "49": 80, "50": 84, "51": 87, "52": 92, "53": 95, "54": 97, "55": 100, "56": 104, "57": 108, "58": 110, "59": 112, "60": 114, "61": 116, "62": 118, "63": 119, "64": 121, "65": 121, "66": 121, "67": 121, "68": 121, "69": 121, "70": 121, "71": 121, "72": 121, "73": 121, "74": 121, "75": 121, "76": 121, "77": 121, "78": 121, "79": 121, "80": 121, "81": 121, "82": 121, "83": 121, "84": 121, "85": 121, "86": 121, "87": 121, "88": 121, "89": 121, "90": 121, "91": 121, "92": 121, "93": 121, "94": 121, "95": 121, "96": 121, "97": 121, "98": 121, "99": 121}, "P": {"0": 0, "1": 0, "2": 0, "3": 0, "4": 0, "5": 0, "6": 12, "7": 15, "8": 17, "9": 19, "10": 27, "11": 37, "12": 42, "13": 45, "14": 49, "15": 52, "16": 53, "17": 54, "18": 55, "19": 56, "20": 57, "21": 58, "22": 59, "23": 60, "24": 61, "25": 62, "26": 63, "27": 64, "28": 65, "29": 65, "30": 66, "31": 66, "32": 67, "33": 68, "34": 69, "35": 69, "36": 70, "37": 70, "38": 71, "39": 72, "40": 72, "41": 73, "42": 73, "43": 74, "44": 75, "45": 77, "46": 80, "47": 82, "48": 85, "49": 88, "50": 92, "51": 95, "52": 98, "53": 100, "54": 102, "55": 104, "56": 107, "57": 109, "58": 111, "59": 113, "60": 117, "61": 120, "62": 121, "63": 121, "64": 121, "65": 121, "66": 121, "67": 121, "68": 121, "69": 121, "70": 121, "71": 121, "72": 121, "73": 121, "74": 121, "75": 121, "76": 121, "77": 121, "78": 121, "79": 121, "80": 121, "81": 121, "82": 121, "83": 121, "84": 121, "85": 121, "86": 121, "87": 121, "88": 121, "89": 121, "90": 121, "91": 121, "92": 121, "93": 121, "94": 121, "95": 121, "96": 121, "97": 121, "98": 121, "99": 121}, "A": {"0": 0, "1": 0, "2": 0, "3": 20, "4": 30, "5": 40, "6": 50, "7": 60, "8": 62, "9": 64, "10": 66, "11": 70, "12": 72, "13": 75, "14": 77, "15": 79, "16": 81, "17": 83, "18": 85, "19": 86, "20": 87, "21": 88, "22": 89, "23": 90, "24": 90, "25": 90, "26": 91, "27": 93, "28": 95, "29": 96, "30": 98, "31": 100, "32": 102, "33": 105, "34": 109, "35": 113, "36": 115, "37": 115, "38": 115, "39": 115, "40": 115, "41": 115, "42": 115, "43": 115, "44": 115, "45": 115, "46": 115, "47": 115, "48": 115, "49": 115, "50": 115, "51": 115, "52": 115, "53": 115, "54": 115, "55": 115, "56": 115, "57": 115, "58": 115, "59": 115, "60": 115, "61": 115, "62": 115, "63": 115, "64": 115, "65": 115, "66": 115, "67": 115, "68": 115, "69": 115, "70": 115, "71": 115, "72": 115, "73": 115, "74": 115, "75": 115, "76": 115, "77": 115, "78": 115, "79": 115, "80": 115, "81": 115, "82": 115, "83": 115, "84": 115, "85": 115, "86": 115, "87": 115, "88": 115, "89": 115, "90": 115, "91": 115, "92": 115, "93": 115, "94": 115, "95": 115, "96": 115, "97": 115, "98": 115, "99": 115}, "H": {"0": 0, "1": 0, "2": 0, "3": 15, "4": 30, "5": 40, "6": 48, "7": 55, "8": 57, "9": 58, "10": 59, "11": 59, "12": 60, "13": 60, "14": 61, "15": 61, "16": 62, "17": 62, "18": 63, "19": 63, "20": 64, "21": 64, "22": 65, "23": 65, "24": 66, "25": 66, "26": 67, "27": 67, "28": 67, "29": 68, "30": 68, "31": 68, "32": 69, "33": 70, "34": 72, "35": 75, "36": 83, "37": 87, "38": 92, "39": 96, "40": 100, "41": 105, "42": 110, "43": 115, "44": 115, "45": 115, "46": 115, "47": 115, "48": 115, "49": 115, "50": 115, "51": 115, "52": 115, "53": 115, "54": 115, "55": 115, "56": 115, "57": 115, "58": 115, "59": 115, "60": 115, "61": 115, "62": 115, "63": 115, "64": 115, "65": 115, "66": 115, "67": 115, "68": 115, "69": 115, "70": 115, "71": 115, "72": 115, "73": 115, "74": 115, "75": 115, "76": 115, "77": 115, "78": 115, "79": 115, "80": 115, "81": 115, "82": 115, "83": 115, "84": 115, "85": 115, "86": 115, "87": 115, "88": 115, "89": 115, "90": 115, "91": 115, "92": 115, "93": 115, "94": 115, "95": 115, "96": 115, "97": 115, "98": 115, "99": 115}, "N": {"0": 0, "1": 0, "2": 0, "3": 0, "4": 0, "5": 0, "6": 2, "7": 5, "8": 10, "9": 12, "10": 20, "11": 30, "12": 35, "13": 37, "14": 39, "15": 41, "16": 44, "17": 47, "18": 50, "19": 53, "20": 57, "21": 60, "22": 60, "23": 60, "24": 60, "25": 60, "26": 60, "27": 60, "28": 61, "29": 62, "30": 63, "31": 64, "32": 65, "33": 67, "34": 69, "35": 71, "36": 73, "37": 75, "38": 79, "39": 82, "40": 85, "41": 90, "42": 95, "43": 110, "44": 115, "45": 115, "46": 115, "47": 115, "48": 115, "49": 115, "50": 115, "51": 115, "52": 115, "53": 115, "54": 115, "55": 115, "56": 115, "57": 115, "58": 115, "59": 115, "60": 115, "61": 115, "62": 115, "63": 115, "64": 115, "65": 115, "66": 115, "67": 115, "68": 115, "69": 115, "70": 115, "71": 115, "72": 115, "73": 115, "74": 115, "75": 115, "76": 115, "77": 115, "78": 115, "79": 115, "80": 115, "81": 115, "82": 115, "83": 115, "84": 115, "85": 115, "86": 115, "87": 115, "88": 115, "89": 115, "90": 115, "91": 115, "92": 115, "93": 115, "94": 115, "95": 115, "96": 115, "97": 115, "98": 115, "99": 115}, "D": {"0": 0, "1": 0, "2": 0, "3": 0, "4": 10, "5": 15, "6": 18, "7": 21, "8": 25, "9": 27, "10": 30, "11": 32, "12": 35, "13": 42, "14": 49, "15": 55, "16": 58, "17": 59, "18": 61, "19": 63, "20": 71, "21": 73, "22": 74, "23": 76, "24": 80, "25": 85, "26": 87, "27": 88, "28": 89, "29": 90, "30": 90, "31": 90, "32": 91, "33": 91, "34": 92, "35": 92, "36": 93, "37": 93, "38": 93, "39": 94, "40": 94, "41": 95, "42": 96, "43": 96, "44": 97, "45": 98, "46": 98, "47": 99, "48": 99, "49": 100, "50": 100, "51": 104, "52": 107, "53": 110, "54": 112, "55": 114, "56": 115, "57": 115, "58": 115, "59": 115, "60": 115, "61": 115, "62": 115, "63": 115, "64": 115, "65": 115, "66": 115, "67": 115, "68": 115, "69": 115, "70": 115, "71": 115, "72": 115, "73": 115, "74": 115, "75": 115, "76": 115, "77": 115, "78": 115, "79": 115, "80": 115, "81": 115, "82": 115, "83": 115, "84": 115, "85": 115, "86": 115, "87": 115, "88": 115, "89": 115, "90": 115, "91": 115, "92": 115, "93": 115, "94": 115, "95": 115, "96": 115, "97": 115, "98": 115, "99": 115}, "B": {"0": 0, "1": 0, "2": 0, "3": 0, "4": 0, "5": 0, "6": 0, "7": 0, "8": 15, "9": 25, "10": 35, "11": 38, "12": 41, "13": 45, "14": 48, "15": 51, "16": 55, "17": 60, "18": 61, "19": 62, "20": 63, "21": 64, "22": 65, "23": 67, "24": 69, "25": 71, "26": 73, "27": 75, "28": 77, "29": 79, "30": 81, "31": 83, "32": 85, "33": 86, "34": 88, "35": 89, "36": 90, "37": 92, "38": 93, "39": 94, "40": 95, "41": 97, "42": 98, "43": 99, "44": 100, "45": 101, "46": 103, "47": 105, "48": 108, "49": 111, "50": 113, "51": 115, "52": 115, "53": 115, "54": 115, "55": 115, "56": 115, "57": 115, "58": 115, "59": 115, "60": 115, "61": 115, "62": 115, "63": 115, "64": 115, "65": 115, "66": 115, "67": 115, "68": 115, "69": 115, "70": 115, "71": 115, "72": 115, "73": 115, "74": 115, "75": 115, "76": 115, "77": 115, "78": 115, "79": 115, "80": 115, "81": 115, "82": 115, "83": 115, "84": 115, "85": 115, "86": 115, "87": 115, "88": 115, "89": 115, "90": 115, "91": 115, "92": 115, "93": 115, "94": 115, "95": 115, "96": 115, "97": 115, "98": 115, "99": 115}, "T": {"0": 0, "1": 0, "2": 0, "3": 0, "4": 0, "5": 0, "6": 0, "7": 5, "8": 10, "9": 15, "10": 20, "11": 25, "12": 30, "13": 35, "14": 37, "15": 39, "16": 41, "17": 44, "18": 48, "19": 51, "20": 54, "21": 57, "22": 60, "23": 60, "24": 60, "25": 61, "26": 61, "27": 62, "28": 63, "29": 64, "30": 65, "31": 66, "32": 68, "33": 69, "34": 70, "35": 71, "36": 72, "37": 73, "38": 75, "39": 77, "40": 79, "41": 81, "42": 83, "43": 85, "44": 86, "45": 87, "46": 89, "47": 90, "48": 91, "49": 92, "50": 94, "51": 95, "52": 97, "53": 98, "54": 99, "55": 100, "56": 103, "57": 106, "58": 109, "59": 112, "60": 115, "61": 115, "62": 115, "63": 115, "64": 115, "65": 115, "66": 115, "67": 115, "68": 115, "69": 115, "70": 115, "71": 115, "72": 115, "73": 115, "74": 115, "75": 115, "76": 115, "77": 115, "78": 115, "79": 115, "80": 115, "81": 115, "82": 115, "83": 115, "84": 115, "85": 115, "86": 115, "87": 115, "88": 115, "89": 115, "90": 115, "91": 115, "92": 115, "93": 115, "94": 115, "95": 115, "96": 115, "97": 115, "98": 115, "99": 115}, "SS": {"0": 0, "1": 0, "2": 0, "3": 35, "4": 40, "5": 44, "6": 50, "7": 55, "8": 60, "9": 60, "10": 60, "11": 60, "12": 60, "13": 61, "14": 61, "15": 62, "16": 62, "17": 63, "18": 65, "19": 67, "20": 67, "21": 68, "22": 68, "23": 69, "24": 70, "25": 70, "26": 71, "27": 72, "28": 73, "29": 75, "30": 77, "31": 79, "32": 80, "33": 82, "34": 85, "35": 90, "36": 95, "37": 100, "38": 110, "39": 115, "40": 115, "41": 115, "42": 115, "43": 115, "44": 115, "45": 115, "46": 115, "47": 115, "48": 115, "49": 115, "50": 115, "51": 115, "52": 115, "53": 115, "54": 115, "55": 115, "56": 115, "57": 115, "58": 115, "59": 115, "60": 115, "61": 115, "62": 115, "63": 115, "64": 115, "65": 115, "66": 115, "67": 115, "68": 115, "69": 115, "70": 115, "71": 115, "72": 115, "73": 115, "74": 115, "75": 115, "76": 115, "77": 115, "78": 115, "79": 115, "80": 115, "81": 115, "82": 115, "83": 115, "84": 115, "85": 115, "86": 115, "87": 115, "88": 115, "89": 115, "90": 115, "91": 115, "92": 115, "93": 115, "94": 115, "95": 115, "96": 115, "97": 115, "98": 115, "99": 115}, "CC": {"0": 0, "1": 35, "2": 38, "3": 41, "4": 44, "5": 47, "6": 50, "7": 55, "8": 60, "9": 60, "10": 60, "11": 60, "12": 60, "13": 60, "14": 60, "15": 60, "16": 60, "17": 60, "18": 61, "19": 62, "20": 63, "21": 64, "22": 65, "23": 65, "24": 66, "25": 67, "26": 68, "27": 69, "28": 70, "29": 71, "30": 72, "31": 73, "32": 74, "33": 75, "34": 75, "35": 76, "36": 77, "37": 78, "38": 79, "39": 80, "40": 83, "41": 85, "42": 90, "43": 95, "44": 100, "45": 110, "46": 115, "47": 115, "48": 115, "49": 115, "50": 115, "51": 115, "52": 115, "53": 115, "54": 115, "55": 115, "56": 115, "57": 115, "58": 115, "59": 115, "60": 115, "61": 115, "62": 115, "63": 115, "64": 115, "65": 115, "66": 115, "67": 115, "68": 115, "69": 115, "70": 115, "71": 115, "72": 115, "73": 115, "74": 115, "75": 115, "76": 115, "77": 115, "78": 115, "79": 115, "80": 115, "81": 115, "82": 115, "83": 115, "84": 115, "85": 115, "86": 115, "87": 115, "88": 115, "89": 115, "90": 115, "91": 115, "92": 115, "93": 115, "94": 115, "95": 115, "96": 115, "97": 115, "98": 115, "99": 115}, "PP": {"0": 0, "1": 0, "2": 0, "3": 10, "4": 25, "5": 35, "6": 38, "7": 41, "8": 44, "9": 47, "10": 51, "11": 53, "12": 55, "13": 57, "14": 60, "15": 60, "16": 60, "17": 61, "18": 63, "19": 64, "20": 65, "21": 67, "22": 69, "23": 71, "24": 72, "25": 73, "26": 75, "27": 80, "28": 85, "29": 88, "30": 91, "31": 94, "32": 97, "33": 100, "34": 105, "35": 110, "36": 115, "37": 115, "38": 115, "39": 115, "40": 115, "41": 115, "42": 115, "43": 115, "44": 115, "45": 115, "46": 115, "47": 115, "48": 115, "49": 115, "50": 115, "51": 115, "52": 115, "53": 115, "54": 115, "55": 115, "56": 115, "57": 115, "58": 115, "59": 115, "60": 115, "61": 115, "62": 115, "63": 115, "64": 115, "65": 115, "66": 115, "67": 115, "68": 115, "69": 115, "70": 115, "71": 115, "72": 115, "73": 115, "74": 115, "75": 115, "76": 115, "77": 115, "78": 115, "79": 115, "80": 115, "81": 115, "82": 115, "83": 115, "84": 115, "85": 115, "86": 115, "87": 115, "88": 115, "89": 115, "90": 115, "91": 115, "92": 115, "93": 115, "94": 115, "95": 115, "96": 115, "97": 115, "98": 115, "99": 115}, "X": {}}


# ==============================================================================
# MOTOR DE CÁLCULO Y MANUAL DE OCUPACIONES HOLLAND (RIASEC)
# ==============================================================================
HOLLAND_ITEMS = [{"num": 1, "sec": "2. Habilidades", "cat": "R", "txt": "1. Componer  cosas  eléctricas"}, {"num": 2, "sec": "2. Habilidades", "cat": "R", "txt": "2. Reparar  una  bicicleta,  auto  o  motocicleta"}, {"num": 3, "sec": "2. Habilidades", "cat": "R", "txt": "3. Componer  cosas  mecánicas"}, {"num": 4, "sec": "2. Habilidades", "cat": "R", "txt": "4. Usar  herramientas  para  trabajar  con  metales  o  maquinaria"}, {"num": 5, "sec": "2. Habilidades", "cat": "R", "txt": "5. Trabajar  con  un  gran  mecánico  o  técnico"}, {"num": 6, "sec": "2. Habilidades", "cat": "R", "txt": "6. Instalar  o  reparar  un  teléfono"}, {"num": 7, "sec": "2. Habilidades", "cat": "R", "txt": "7. Construir  cosas  con  madera"}, {"num": 8, "sec": "2. Habilidades", "cat": "R", "txt": "8. Tomar  una  clase  de  educación  tecnológica  (como  antes  industriales  o  taller  automotriz)"}, {"num": 9, "sec": "2. Habilidades", "cat": "R", "txt": "9. Trabajar  en  exteriores"}, {"num": 10, "sec": "2. Habilidades", "cat": "R", "txt": "10. Trabajar  con  equipo  electrónico"}, {"num": 11, "sec": "2. Habilidades", "cat": "R", "txt": "11. Ir  de  visita  por  una  ferretería"}, {"num": 12, "sec": "2. Habilidades", "cat": "R", "txt": "12. Número  Total  de  Letras  S"}, {"num": 13, "sec": "2. Habilidades", "cat": "I", "txt": "13. Escribir  un  reporte  científico"}, {"num": 14, "sec": "2. Habilidades", "cat": "I", "txt": "14. Aprender  acerca  de  la  física"}, {"num": 15, "sec": "2. Habilidades", "cat": "I", "txt": "15. Estudiar  química"}, {"num": 16, "sec": "2. Habilidades", "cat": "I", "txt": "16. Tomar  una  clase  de  biología"}, {"num": 17, "sec": "2. Habilidades", "cat": "I", "txt": "17. Leer  libros  o  revistas  científicos"}, {"num": 18, "sec": "2. Habilidades", "cat": "I", "txt": "18. Trabajar  en  un  proyecto  de  investigación"}, {"num": 19, "sec": "2. Habilidades", "cat": "I", "txt": "19. Estudiar  una  teoría  científica"}, {"num": 20, "sec": "2. Habilidades", "cat": "I", "txt": "20. Analizar  información"}, {"num": 21, "sec": "2. Habilidades", "cat": "I", "txt": "21. Estudiar  astronomía"}, {"num": 22, "sec": "2. Habilidades", "cat": "I", "txt": "22. Visitar  un  museo  de  ciencias"}, {"num": 23, "sec": "2. Habilidades", "cat": "I", "txt": "23. Estudiar  el  cerebro"}, {"num": 24, "sec": "2. Habilidades", "cat": "I", "txt": "24. Número  Total  de  Letras  S"}, {"num": 25, "sec": "2. Habilidades", "cat": "A", "txt": "25. Hacer  bocetos,  dibujar  o  pintar"}, {"num": 26, "sec": "2. Habilidades", "cat": "A", "txt": "26. Tomar  fotografías"}, {"num": 27, "sec": "2. Habilidades", "cat": "A", "txt": "27. Escribir  para  una  revista  o  periódico"}, {"num": 28, "sec": "2. Habilidades", "cat": "A", "txt": "28. Pintar  retratos"}, {"num": 29, "sec": "2. Habilidades", "cat": "A", "txt": "29. Leer  o  escribir  poesía"}, {"num": 30, "sec": "2. Habilidades", "cat": "A", "txt": "30. Tomar  una  clase  de  arte"}, {"num": 31, "sec": "2. Habilidades", "cat": "A", "txt": "31. Estudiar  con  un  artista  plástico,  músico  o  escritor  talentoso"}, {"num": 32, "sec": "2. Habilidades", "cat": "A", "txt": "32. Tocar  un  instrumento  musical"}, {"num": 33, "sec": "2. Habilidades", "cat": "A", "txt": "33. Pertenecer  a  una  orquesta,  banda  o  grupo  musical"}, {"num": 34, "sec": "2. Habilidades", "cat": "A", "txt": "34. Escribir  novelas  u  obras  de  teatro"}, {"num": 35, "sec": "2. Habilidades", "cat": "A", "txt": "35. Leer  acerca  de  arte,  literatura  o  música"}, {"num": 36, "sec": "2. Habilidades", "cat": "A", "txt": "36. Número  Total  de  Letras  S"}, {"num": 37, "sec": "2. Habilidades", "cat": "S", "txt": "37. Dar  clases  en  una  escuela"}, {"num": 38, "sec": "2. Habilidades", "cat": "S", "txt": "38. Ayudar  a  niños  discapacitados"}, {"num": 39, "sec": "2. Habilidades", "cat": "S", "txt": "39. Conocer  a  educadores  o  terapeutas  importantes"}, {"num": 40, "sec": "2. Habilidades", "cat": "S", "txt": "40. Leer  libros  o  artículos  de  psicología"}, {"num": 41, "sec": "2. Habilidades", "cat": "S", "txt": "41. Tomar  una  clase  de  relaciones  humanas"}, {"num": 42, "sec": "2. Habilidades", "cat": "S", "txt": "42. Tomar  una  clase  de  superación  personal"}, {"num": 43, "sec": "2. Habilidades", "cat": "S", "txt": "43. Resolver  conflictos  entre  otras  personas"}, {"num": 44, "sec": "2. Habilidades", "cat": "S", "txt": "44. Escribirle  cartas  a  los  amigos"}, {"num": 45, "sec": "2. Habilidades", "cat": "S", "txt": "45. Ayudar  a  la  gente  cuando  está  enferma"}, {"num": 46, "sec": "2. Habilidades", "cat": "S", "txt": "46. Trabajar  para  una  línea  telefónica  de  urgencia  para  suicidas  o  jóvenes  que  huyen  del  hogar"}, {"num": 47, "sec": "2. Habilidades", "cat": "S", "txt": "47. Ayudar  a  otros  a  que  resuelvan  sus  problemas"}, {"num": 48, "sec": "2. Habilidades", "cat": "S", "txt": "48. Número  Total  de  Letras  S"}, {"num": 49, "sec": "2. Habilidades", "cat": "E", "txt": "49. Ser  jefe  de  un  proyecto"}, {"num": 50, "sec": "2. Habilidades", "cat": "E", "txt": "50. Fungir  como  funcionario  de  un  grupo"}, {"num": 51, "sec": "2. Habilidades", "cat": "E", "txt": "51. Aprender  a  ser  exitoso  en  los  negocios"}, {"num": 52, "sec": "2. Habilidades", "cat": "E", "txt": "52. Tomar  una  clase  breve  sobre  liderazgo"}, {"num": 53, "sec": "2. Habilidades", "cat": "E", "txt": "53. Supervisar  el  trabajo  de  otros"}, {"num": 54, "sec": "2. Habilidades", "cat": "E", "txt": "54. Conducir  a  un  grupo  a  obtener  su  meta"}, {"num": 55, "sec": "2. Habilidades", "cat": "E", "txt": "55. Conocer  a  ejecutivos  y  lideres  importantes"}, {"num": 56, "sec": "2. Habilidades", "cat": "E", "txt": "56. Participar  en  una  campaña  política"}, {"num": 57, "sec": "2. Habilidades", "cat": "E", "txt": "57. Dirigir  el  trabajo  de  otros"}, {"num": 58, "sec": "2. Habilidades", "cat": "E", "txt": "58. Operar  mi  propio  negocio"}, {"num": 59, "sec": "2. Habilidades", "cat": "E", "txt": "59. Vender  espacios  publicitarios  en  anuario  escolar"}, {"num": 60, "sec": "2. Habilidades", "cat": "E", "txt": "60. Número  Total  de  Letras  S"}, {"num": 61, "sec": "2. Habilidades", "cat": "C", "txt": "61. Sumar,  restar,  multiplicar  y  dividir  números  en  un  negocio  o  en  contaduría"}, {"num": 62, "sec": "2. Habilidades", "cat": "C", "txt": "62. Llevar  un  registro  de  gastos"}, {"num": 63, "sec": "2. Habilidades", "cat": "C", "txt": "63. Tomar  una  clase  de  cálculo  mercantil"}, {"num": 64, "sec": "2. Habilidades", "cat": "C", "txt": "64. Examinar  documentos  o  productos  para  encontrar  errores  o  fallas"}, {"num": 65, "sec": "2. Habilidades", "cat": "C", "txt": "65. Revisar  registros  financieros  para  encontrar  errores"}, {"num": 66, "sec": "2. Habilidades", "cat": "C", "txt": "66. Cuadrar  las  cuentas  en  una  chequera"}, {"num": 67, "sec": "2. Habilidades", "cat": "C", "txt": "67. Llevar  registros"}, {"num": 68, "sec": "2. Habilidades", "cat": "C", "txt": "68. Operar  maquinaria  de  oficina  (no  leo  bien)"}, {"num": 69, "sec": "2. Habilidades", "cat": "C", "txt": "69. Tomar  una  clase  de  contabilidad"}, {"num": 70, "sec": "2. Habilidades", "cat": "C", "txt": "70. Hacer  un  inventario  de  suministros  o  productos"}, {"num": 71, "sec": "2. Habilidades", "cat": "C", "txt": "71. Establecer  un  sistema  de  registro"}, {"num": 72, "sec": "2. Habilidades", "cat": "C", "txt": "72. Número  Total  de  Letras  S"}, {"num": 73, "sec": "2. Habilidades", "cat": "R", "txt": "73. Cambiar  una  llanta"}, {"num": 74, "sec": "2. Habilidades", "cat": "R", "txt": "74. Operar  herramientas  eléctricas  como  un  taladro  o  una  máquina  de  coser"}, {"num": 75, "sec": "2. Habilidades", "cat": "R", "txt": "75. Interpretar  un  plano"}, {"num": 76, "sec": "2. Habilidades", "cat": "R", "txt": "76. Hacer  reparaciones  eléctricas  sencillas"}, {"num": 77, "sec": "2. Habilidades", "cat": "R", "txt": "77. Reparar  muebles"}, {"num": 78, "sec": "2. Habilidades", "cat": "R", "txt": "78. Usar  la  mayoría  de  las  herramientas  de  un  carpintero"}, {"num": 79, "sec": "2. Habilidades", "cat": "R", "txt": "79. Usar  equipos  de  soldadura"}, {"num": 80, "sec": "2. Habilidades", "cat": "R", "txt": "80. Cazar  o  pescar"}, {"num": 81, "sec": "2. Habilidades", "cat": "R", "txt": "81. Hacer  dibujos  mecánicos"}, {"num": 82, "sec": "2. Habilidades", "cat": "R", "txt": "82. Construir  cosas  sencillas  de  madera"}, {"num": 83, "sec": "2. Habilidades", "cat": "R", "txt": "83. Componer  un  grifo  que  tiene  una  fuga"}, {"num": 84, "sec": "2. Habilidades", "cat": "R", "txt": "84. Número  Total  de  Letras  S"}, {"num": 85, "sec": "2. Habilidades", "cat": "I", "txt": "85. Entender  la  vida  media  de  un  elemento  radioactivo"}, {"num": 86, "sec": "2. Habilidades", "cat": "I", "txt": "86. Describir  la  función  de  los  glóbulos  blancos"}, {"num": 87, "sec": "2. Habilidades", "cat": "I", "txt": "87. Escribir  un  reporte  científico  o  de  gran  erudición"}, {"num": 88, "sec": "2. Habilidades", "cat": "I", "txt": "88. Interpretar  formulas  químicas  sencillas"}, {"num": 89, "sec": "2. Habilidades", "cat": "I", "txt": "89. Usar  una  computadora  para  analizar  datos"}, {"num": 90, "sec": "2. Habilidades", "cat": "I", "txt": "90. Entender  por  qué  no  caen  a  la  tierra  los  satélites  artificiales"}, {"num": 91, "sec": "2. Habilidades", "cat": "I", "txt": "91. Llevar  a  cabo  un  experimento  científico"}, {"num": 92, "sec": "2. Habilidades", "cat": "I", "txt": "92. Explicar  cómo  funciona  una  computadora"}, {"num": 93, "sec": "2. Habilidades", "cat": "I", "txt": "93. Usar  un  microscopio"}, {"num": 94, "sec": "2. Habilidades", "cat": "I", "txt": "94. Entender  la  tabla  periódica  de  los  elementos"}, {"num": 95, "sec": "2. Habilidades", "cat": "I", "txt": "95. Explicar  porque  algunos  jabones  flotan  y  otros  se  hunden"}, {"num": 96, "sec": "2. Habilidades", "cat": "I", "txt": "96. Número  Total  de  Letras  S"}, {"num": 97, "sec": "2. Habilidades", "cat": "A", "txt": "97. Tocar  un  instrumento  musical"}, {"num": 98, "sec": "2. Habilidades", "cat": "A", "txt": "98. Participar  en  un  canto  coral  de  dos  o  cuatro  voces"}, {"num": 99, "sec": "2. Habilidades", "cat": "A", "txt": "99. Hacer  una  pintura,  una  acuarela  o  una  escultura"}, {"num": 100, "sec": "2. Habilidades", "cat": "A", "txt": "100. Hacer  arreglos  o  composiciones  musicales"}, {"num": 101, "sec": "2. Habilidades", "cat": "A", "txt": "101. Diseñar  ropa,  carteles  o  muebles"}, {"num": 102, "sec": "2. Habilidades", "cat": "A", "txt": "102. Crear  la  representación  artística  de  un  concepto  o  idea"}, {"num": 103, "sec": "2. Habilidades", "cat": "A", "txt": "103. Escribir  bien  cuentos  o  poemas"}, {"num": 104, "sec": "2. Habilidades", "cat": "A", "txt": "104. Presentarme  como  solista  musical"}, {"num": 105, "sec": "2. Habilidades", "cat": "A", "txt": "105. Dar  una  plática  entretenida"}, {"num": 106, "sec": "2. Habilidades", "cat": "A", "txt": "106. Publicar  un  cuento,  poema  o  ensayo  en  el  periódico  escolar  o  en  alguna  otra  publicación"}, {"num": 107, "sec": "2. Habilidades", "cat": "A", "txt": "107. Estar  en  una  banda  de  música,  orquesta  o  coro"}, {"num": 108, "sec": "2. Habilidades", "cat": "S", "txt": "108. Ayudar  a  personas  que  estén  alteradas  o  afligidas"}, {"num": 109, "sec": "2. Habilidades", "cat": "S", "txt": "109. Enseñar  con  facilidad  a  los  niños"}, {"num": 110, "sec": "2. Habilidades", "cat": "S", "txt": "110. Cooperar  y  trabajar  bien  con  los  demás"}, {"num": 111, "sec": "2. Habilidades", "cat": "S", "txt": "111. Reconocer  las  fortalezas  y  debilidades  de  las  personas"}, {"num": 112, "sec": "2. Habilidades", "cat": "S", "txt": "112. Calmar  a  la  gente  cuando  está  alterada"}, {"num": 113, "sec": "2. Habilidades", "cat": "S", "txt": "113. Trabajar  con  otros  en  un  proyecto  de  equipo"}, {"num": 114, "sec": "2. Habilidades", "cat": "S", "txt": "114. Hacer  sentir  cómoda  a  la  gente"}, {"num": 115, "sec": "2. Habilidades", "cat": "S", "txt": "115. Dar  clases  a  otros"}, {"num": 116, "sec": "2. Habilidades", "cat": "S", "txt": "116. Tener  una  buena  comprensión  de  las  relaciones  sociales"}, {"num": 117, "sec": "2. Habilidades", "cat": "S", "txt": "117. Escuchar  a  la  gente"}, {"num": 118, "sec": "2. Habilidades", "cat": "S", "txt": "118. Hacer  que  la  gente  me  busque  para  contarme  sus  problemas"}, {"num": 119, "sec": "2. Habilidades", "cat": "S", "txt": "119. Número  Total  de  Letras  S"}, {"num": 120, "sec": "2. Habilidades", "cat": "E", "txt": "120. Ser  un  buen  vendedor"}, {"num": 121, "sec": "2. Habilidades", "cat": "E", "txt": "121. Planear  una  estrategia  para  lograr  una  meta"}, {"num": 122, "sec": "2. Habilidades", "cat": "E", "txt": "122. Ser  un  líder  exitoso"}, {"num": 123, "sec": "2. Habilidades", "cat": "E", "txt": "123. Ser  un  buen  orador"}, {"num": 124, "sec": "2. Habilidades", "cat": "E", "txt": "124. Administrar  una  campaña  de  ventas"}, {"num": 125, "sec": "2. Habilidades", "cat": "E", "txt": "125. Organizar  el  trabajo  de  otros"}, {"num": 126, "sec": "2. Habilidades", "cat": "E", "txt": "126. Ser  bueno  en  los  debates"}, {"num": 127, "sec": "2. Habilidades", "cat": "E", "txt": "127. Supervisar  el  trabajo  de  otros"}, {"num": 128, "sec": "2. Habilidades", "cat": "E", "txt": "128. Empezar  mi  propio  negocio"}, {"num": 129, "sec": "2. Habilidades", "cat": "E", "txt": "129. Ser  el  vocero  de  un  salón  de  clases  o  grupo"}, {"num": 130, "sec": "2. Habilidades", "cat": "E", "txt": "130. Ser  una  persona  ambiciosa"}, {"num": 131, "sec": "2. Habilidades", "cat": "E", "txt": "131. Número  Total  de  Letras  S"}, {"num": 132, "sec": "2. Habilidades", "cat": "C", "txt": "132. Usar  una  copiadora"}, {"num": 133, "sec": "2. Habilidades", "cat": "C", "txt": "133. Archivar  correspondencia  y  otros  documentos"}, {"num": 134, "sec": "2. Habilidades", "cat": "C", "txt": "134. Hacer  mucho  papeleo  en  un  tiempo  corto"}, {"num": 135, "sec": "2. Habilidades", "cat": "C", "txt": "135. Llevar  registro  precisos  de  pagos  y  ventas"}, {"num": 136, "sec": "2. Habilidades", "cat": "C", "txt": "136. Transcribir  de  un  dictáfono"}, {"num": 137, "sec": "2. Habilidades", "cat": "C", "txt": "137. Obtener  información  por  teléfono"}, {"num": 138, "sec": "2. Habilidades", "cat": "C", "txt": "138. Utilizar  un  procesador  de  textos"}, {"num": 139, "sec": "2. Habilidades", "cat": "C", "txt": "139. Tener  un  empleo  de  oficina"}, {"num": 140, "sec": "2. Habilidades", "cat": "C", "txt": "140. Usar  una  computadora  para  analizar  datos  empresariales"}, {"num": 141, "sec": "2. Habilidades", "cat": "C", "txt": "141. Dar  el  cambio  correcto  de  manera  rápida"}, {"num": 142, "sec": "2. Habilidades", "cat": "C", "txt": "142. Encontrar  errores  en  el  trabajo  de  los  demás"}, {"num": 143, "sec": "2. Habilidades", "cat": "C", "txt": "143. Número  Total  de  Letras  S"}, {"num": 144, "sec": "3. Ocupaciones", "cat": "R", "txt": "144. Mecánico  automotriz  –  arregla  automóviles"}, {"num": 145, "sec": "3. Ocupaciones", "cat": "R", "txt": "145. Carpintero  –  construye  cosas  con  madera"}, {"num": 146, "sec": "3. Ocupaciones", "cat": "R", "txt": "146. Inspector  de  construcciones  –  inspecciona  edificios  nuevos  para  ver  si  están  bien  construidos"}, {"num": 147, "sec": "3. Ocupaciones", "cat": "R", "txt": "147. Radiooperador  –  manda  y  recibe  mensajes  de  radio"}, {"num": 148, "sec": "3. Ocupaciones", "cat": "R", "txt": "148. Agricultor  –  levanta  cosechas"}, {"num": 149, "sec": "3. Ocupaciones", "cat": "R", "txt": "149. Mecánico  aeronáutico  –  arregla  aviones"}, {"num": 150, "sec": "3. Ocupaciones", "cat": "R", "txt": "150. Bombero  –  extingue  y  ayuda  a  prevenir  incendios"}, {"num": 151, "sec": "3. Ocupaciones", "cat": "R", "txt": "151. Conductor  de  camiones  en  distancias  largas  –  manejar  una  ruta  de  autobuses  o  tráileres"}, {"num": 152, "sec": "3. Ocupaciones", "cat": "R", "txt": "152. Mecánico  –  construye,  repara  o  trabaja  con  maquinaria"}, {"num": 153, "sec": "3. Ocupaciones", "cat": "R", "txt": "153. Electricista  –  arregla  el  cableado  eléctrico  en  edificios  o  maquinas"}, {"num": 154, "sec": "3. Ocupaciones", "cat": "R", "txt": "154. Técnico  en  electrónico  –  construye,  prueba  y  arregla  equipos  electrónicos"}, {"num": 155, "sec": "3. Ocupaciones", "cat": "R", "txt": "155. Carpintero  –  construye  muebles  para  casas  o  edificios"}, {"num": 156, "sec": "3. Ocupaciones", "cat": "R", "txt": "156. Número  Total  de  Letras  S"}, {"num": 157, "sec": "3. Ocupaciones", "cat": "I", "txt": "157. Biólogo  –  estudia  plantas  y  animales"}, {"num": 158, "sec": "3. Ocupaciones", "cat": "I", "txt": "158. Técnico  laboratorista  medico  –  trabaja  con  equipos  médicos"}, {"num": 159, "sec": "3. Ocupaciones", "cat": "I", "txt": "159. Antropólogo  –  estudia  culturas  diversas"}, {"num": 160, "sec": "3. Ocupaciones", "cat": "I", "txt": "160. Químico  –  estudia  y  hace  sustancias  químicas"}, {"num": 161, "sec": "3. Ocupaciones", "cat": "I", "txt": "161. Investigador  científico  –  ayuda  a  encontrar  las  respuestas  a  preguntas  científicas"}, {"num": 162, "sec": "3. Ocupaciones", "cat": "I", "txt": "162. Cirujano  –  realiza  operaciones  medicas"}, {"num": 163, "sec": "3. Ocupaciones", "cat": "I", "txt": "163. Investigador  en  ciencias  sociales  –  estudia  problemas  sociales"}, {"num": 164, "sec": "3. Ocupaciones", "cat": "I", "txt": "164. Físico  –  estudia  las  leyes  de  la  naturaleza,  como  la  ley  de  la  gravedad"}, {"num": 165, "sec": "3. Ocupaciones", "cat": "I", "txt": "165. Meteorólogo  –  estudia  el  clima"}, {"num": 166, "sec": "3. Ocupaciones", "cat": "I", "txt": "166. Astrónomo  –  estudia  el  sistema  solar"}, {"num": 167, "sec": "3. Ocupaciones", "cat": "I", "txt": "167. Zoólogo  –  estudia  la  historia  de  los  animales"}, {"num": 168, "sec": "3. Ocupaciones", "cat": "I", "txt": "168. Geólogo  –  estudia  la  historia  del  planeta  tierra"}, {"num": 169, "sec": "3. Ocupaciones", "cat": "I", "txt": "169. Número  Total  de  Letras  S"}, {"num": 170, "sec": "3. Ocupaciones", "cat": "A", "txt": "170. Poeta  -   escribe  poemas"}, {"num": 171, "sec": "3. Ocupaciones", "cat": "A", "txt": "171. Artista  plástico  –  crea  pinturas,   dibujos  y  otros  tipos  de  artes"}, {"num": 172, "sec": "3. Ocupaciones", "cat": "A", "txt": "172. Dramaturgo  –  escribe  obras  de  teatro"}, {"num": 173, "sec": "3. Ocupaciones", "cat": "A", "txt": "173. Músico  –  toca  un  instrumento  musical"}, {"num": 174, "sec": "3. Ocupaciones", "cat": "A", "txt": "174. Actor  –  trabaja  en  una  obra  de  teatro,  espectáculo  o  película"}, {"num": 175, "sec": "3. Ocupaciones", "cat": "A", "txt": "175. Cantante  –  canta  frente  al  publico"}, {"num": 176, "sec": "3. Ocupaciones", "cat": "A", "txt": "176. Compositor  –  escribe  canciones  o  musicales"}, {"num": 177, "sec": "3. Ocupaciones", "cat": "A", "txt": "177. Escultor  –  crea  esculturas  o  estatuas"}, {"num": 178, "sec": "3. Ocupaciones", "cat": "A", "txt": "178. Artista  de  espectáculos  -   canta,  baila,  cuenta  chistes"}, {"num": 179, "sec": "3. Ocupaciones", "cat": "A", "txt": "179. Escritor  –  escribe  libros,  artículos  o  cuentos"}, {"num": 180, "sec": "3. Ocupaciones", "cat": "A", "txt": "180. Maestro  de  teatro  –  enseña  técnicas  de  actuación  a  actores"}, {"num": 181, "sec": "3. Ocupaciones", "cat": "A", "txt": "181. Fotógrafo  –  toma  fotografías"}, {"num": 182, "sec": "3. Ocupaciones", "cat": "A", "txt": "182. Número  Total  de  Letras  S"}, {"num": 183, "sec": "3. Ocupaciones", "cat": "S", "txt": "183. Consejero  matrimonial  –  ayuda  a  las  parejas  con  sus  problemas"}, {"num": 184, "sec": "3. Ocupaciones", "cat": "S", "txt": "184. Director  de  una  agencia  de  beneficencia  –  supervisa  a  trabajadores  que  ayudan  a  la  gente  necesitada"}, {"num": 185, "sec": "3. Ocupaciones", "cat": "S", "txt": "185. Director  de  campamento  juvenil  –  supervisa  los  programas  y  trabajadores  de  un  campamento"}, {"num": 186, "sec": "3. Ocupaciones", "cat": "S", "txt": "186. Orientador  en  abuso  de  sustancias  –  ayuda  a  las  personas  que  tienen  problemas  con  drogas  o  alcohol"}, {"num": 187, "sec": "3. Ocupaciones", "cat": "S", "txt": "187. Director  de  actividades  de  recreo  –  organiza  actividades  recreacionales"}, {"num": 188, "sec": "3. Ocupaciones", "cat": "S", "txt": "188. Psicólogo  clínico  –  ayuda  a  gente  que  tiene  problemas  con  sus  sentimientos,  pensamientos  o  conductas"}, {"num": 189, "sec": "3. Ocupaciones", "cat": "S", "txt": "189. Trabajador  social  –  ayuda  a  gente  con  problemas  en  su  familia,  trabajo  o  amigos"}, {"num": 190, "sec": "3. Ocupaciones", "cat": "S", "txt": "190. Auxiliar  de  enfermería  –  ayuda  en  el  cuidado  de  pacientes"}, {"num": 191, "sec": "3. Ocupaciones", "cat": "S", "txt": "191. Maestro  –  da  clases  en  una  escuela"}, {"num": 192, "sec": "3. Ocupaciones", "cat": "S", "txt": "192. Asistente  social  de  libertad  condicional  –  ayuda  a  las  personas  que  han  tenido  problemas  con  la  ley"}, {"num": 193, "sec": "3. Ocupaciones", "cat": "S", "txt": "193. Orientador  escolar  –  ayuda  a  alumnos  con  problemas"}, {"num": 194, "sec": "3. Ocupaciones", "cat": "S", "txt": "194. Asistente  médico  –  examina  pacientes  en  un  consultorio  medico"}, {"num": 195, "sec": "3. Ocupaciones", "cat": "S", "txt": "195. Número  Total  de  Letras  S"}, {"num": 196, "sec": "3. Ocupaciones", "cat": "E", "txt": "196. Inversionista  –  invierte  dinero  en  tratos  de  negocios"}, {"num": 197, "sec": "3. Ocupaciones", "cat": "E", "txt": "197. Vendedor  –  vende  bienes  o  servicios"}, {"num": 198, "sec": "3. Ocupaciones", "cat": "E", "txt": "198. Gerente  de  ventas  –  supervise  un  equipo  de  vendedores"}, {"num": 199, "sec": "3. Ocupaciones", "cat": "E", "txt": "199. Director  de  mercadotecnia  –  planea  programas  de  comercialización"}, {"num": 200, "sec": "3. Ocupaciones", "cat": "E", "txt": "200. Representante  de  ventas  –  vende  productos  a  otras  empresas"}, {"num": 201, "sec": "3. Ocupaciones", "cat": "E", "txt": "201. Comprador  –  decide  que  productos  va  a  vender  un  almacén"}, {"num": 202, "sec": "3. Ocupaciones", "cat": "E", "txt": "202. Agente  de  bienes  raíces  –  vende  casas  y  terrenos"}, {"num": 203, "sec": "3. Ocupaciones", "cat": "E", "txt": "203. Gerente  de  estación  televisiva  –  dirige  una  estación  de  televisión"}, {"num": 204, "sec": "3. Ocupaciones", "cat": "E", "txt": "204. Corredor  de  bolsas  –  compra  y  vende  acciones  y  bonos"}, {"num": 205, "sec": "3. Ocupaciones", "cat": "E", "txt": "205. Ejecutivo  empresarial  –  supervise  a  mucha  gente  en  una  empresa"}, {"num": 206, "sec": "3. Ocupaciones", "cat": "E", "txt": "206. Funcionario  gubernamental  –  detenta  un  cargo  público"}, {"num": 207, "sec": "3. Ocupaciones", "cat": "E", "txt": "207. Gerente  –  supervise  un  grupo  de  trabajadores"}, {"num": 208, "sec": "3. Ocupaciones", "cat": "E", "txt": "208. Número  Total  de  Letras  S"}, {"num": 209, "sec": "3. Ocupaciones", "cat": "C", "txt": "209. Técnico  en  contabilidad  –  lleva  cuenta  del  dinero  en  un  negocio"}, {"num": 210, "sec": "3. Ocupaciones", "cat": "C", "txt": "210. Revisor  presupuestal  –  ayuda  a  una  empresa  a  decidir  cómo  gastar  y  ahorrar  dinero"}, {"num": 211, "sec": "3. Ocupaciones", "cat": "C", "txt": "211. Contador  público  –  lleva  cuenta  de  transacciones  financieras"}, {"num": 212, "sec": "3. Ocupaciones", "cat": "C", "txt": "212. Jefe  de  almacén  –  lleva  inventario  de  suministros  o  mercancía"}, {"num": 213, "sec": "3. Ocupaciones", "cat": "C", "txt": "213. Capturista  –  ingresa  información  en  una  computadora"}, {"num": 214, "sec": "3. Ocupaciones", "cat": "C", "txt": "214. Administrador  de  nominas  –  se  asegura  que  los  trabajadores  reciban  sus  sueldos  por  la  cantidad  correcta"}, {"num": 215, "sec": "3. Ocupaciones", "cat": "S", "txt": "215. N  Examinador  bancario  –  revisa  registros  bancarios  para  detectar  errores"}, {"num": 216, "sec": "3. Ocupaciones", "cat": "S", "txt": "216. Secretario  –  ayuda  a  su  jefe  con  el  trabajo  de  oficina"}, {"num": 217, "sec": "3. Ocupaciones", "cat": "S", "txt": "217. Asesor  fiscal  –  calcula  la  cantidad  de  impuestos  que  se  deben"}, {"num": 218, "sec": "3. Ocupaciones", "cat": "S", "txt": "218. Analista  financiero  –  ayuda  a  una  empresa  a  invertir  dinero"}, {"num": 219, "sec": "3. Ocupaciones", "cat": "S", "txt": "219. Corrector  de  estilo  –  revisa  material  escrito  para  detectar  errores"}, {"num": 220, "sec": "3. Ocupaciones", "cat": "S", "txt": "220. Cajero  bancario  –  ayuda  los  clientes  del  banco"}, {"num": 221, "sec": "3. Ocupaciones", "cat": "S", "txt": "221. Número  Total  de  Letras  S"}]
HOLLAND_MANUAL = {"code_careers": {"RI": [{"carrera": "Decorador de aparadores comerciales", "ed": "4"}, {"carrera": "Agricultor general", "ed": "7"}, {"carrera": "Técnico artesano! con textiles", "ed": "3"}, {"carrera": "Analista (evaluador) de control de calidad", "ed": "4"}, {"carrera": "Técnico de efectos de sonido", "ed": "6"}, {"carrera": "Asistente farmacéutico", "ed": "6"}, {"carrera": "(También véanse las ocupaciones bajo AR, RI y RS)", "ed": "Chofer de taxi"}], "RC": [{"carrera": "Electricista", "ed": "2"}, {"carrera": "Asistente de electricista", "ed": "2"}, {"carrera": "Encargado de establos", "ed": "2"}, {"carrera": "Carpintero", "ed": "2"}, {"carrera": "Geólogo", "ed": "7"}, {"carrera": "Chofer de tráiler", "ed": "Guardabosques"}, {"carrera": "Dibujante arquitectónico", "ed": "4"}, {"carrera": "Ingeniero de sistemas", "ed": "7"}, {"carrera": "Empleado de laboratorio (clínico)", "ed": "4"}, {"carrera": "Ingeniero mecánico", "ed": "7"}, {"carrera": "Enmarcador de cuadros", "ed": "2"}, {"carrera": "Jardinero paisajista", "ed": "6"}, {"carrera": "Hojalatero", "ed": "3"}, {"carrera": "Maquinista", "ed": "2"}, {"carrera": "Inspector de seguridad", "ed": "8"}, {"carrera": "Operador de estación de radio", "ed": "7"}, {"carrera": "Mecánico automotriz", "ed": "3"}, {"carrera": "Piloto de avión comercial", "ed": "6"}, {"carrera": "Mezclador de sonido", "ed": "6"}, {"carrera": "Reparador de aparatos electrodomésticos", "ed": "4"}, {"carrera": "Operador de tractor", "ed": "Soldador de arco"}, {"carrera": "Reparador de instrumentos", "ed": "3"}, {"carrera": "Técnico de laboratorio clínico", "ed": "4"}, {"carrera": "Técnico de electrocardiograma", "ed": "5"}, {"carrera": "Técnico de sonido", "ed": "6"}, {"carrera": "Técnico de electroencefalograma", "ed": "5"}, {"carrera": "Técnico de televisión", "ed": "3"}, {"carrera": "Técnico de equipo audiovisual", "ed": "4"}, {"carrera": "Técnico en telecomunicaciones", "ed": "6"}, {"carrera": "Técnico de laboratorio de películas", "ed": "6"}, {"carrera": "Tecnólogo en terapia de radiación", "ed": "6"}, {"carrera": "Técnico en diseño asistido por computadora", "ed": "4"}, {"carrera": "(También véanse las ocupaciones bajo IR y RA.)", "ed": ""}, {"carrera": "Técnico zootecnista", "ed": "6"}], "RS": [{"carrera": "(También véanse las ocupaciones bajo CR, CI y CE)", "ed": "Agente de control de vida silvestre"}], "RE": [{"carrera": "Albañil (construcción)", "ed": "2"}, {"carrera": "Agente de embarques", "ed": "8"}, {"carrera": "Analista de telecomunicaciones", "ed": "7"}, {"carrera": "Bombero", "ed": "Asistente ortopédico"}, {"carrera": "Buzo (Ciencias marinas)", "ed": "8"}, {"carrera": "Carnicero", "ed": ""}, {"carrera": "Cerrajero", "ed": "Chofer de ambulancias"}, {"carrera": "Cocinero, Jefe de cocina", "ed": "4"}, {"carrera": "Empleado de correos", "ed": ""}, {"carrera": "Conductor de autobús", "ed": "Ganadero"}, {"carrera": "Encargado de oficina de abastos", "ed": "4"}, {"carrera": "Inspector de inmigración", "ed": "8"}, {"carrera": "Entrenador de animales", "ed": "Inspector de puentes"}, {"carrera": "Exterminador de plagas (Fumigador)", "ed": "7"}, {"carrera": "Modista", "ed": "6"}, {"carrera": "Guardián de caza y pesca", "ed": "8"}, {"carrera": "Oficial de policía estatal de carreteras", "ed": "6"}, {"carrera": "Horticultor", "ed": "7"}, {"carrera": "Operador de conmutador", "ed": "4"}, {"carrera": "Ingeniero de vuelos", "ed": "7"}, {"carrera": "Panadero (hotel y restaurante)", "ed": "4"}, {"carrera": "Inspector de mantenimiento", "ed": "7"}, {"carrera": "Peluquero de perros", "ed": ""}, {"carrera": "Joyero", "ed": "3"}, {"carrera": "Reparador de bicicletas", "ed": ""}, {"carrera": "Maletero", "ed": "Sastre"}, {"carrera": "Operador de excavadora (bulldozer)", "ed": "4"}, {"carrera": "Técnico de ultrasonido", "ed": "4"}, {"carrera": "Piloto de barco (Timonel)", "ed": "Técnico de urgencias médicas"}, {"carrera": "Plomero (construcción)", "ed": "2"}, {"carrera": "Técnico electrónico", "ed": "4"}, {"carrera": "Profesor de artes industriales", "ed": "6"}, {"carrera": "(También véanse las ocupaciones bajo SR, RE y RA.)", "ed": ""}, {"carrera": "Reparador de botes", "ed": "2"}, {"carrera": "Representante de conservación de energía", "ed": "8"}, {"carrera": "Rotulador", "ed": "2"}, {"carrera": "Topógrafo marino", "ed": "7"}, {"carrera": "(También véanse las ocupaciones bajo ER, RS y RC.)", "ed": ""}], "IA": [{"carrera": "Arquitecto marino", "ed": "8"}, {"carrera": "Biólogo", "ed": "7"}, {"carrera": "Astrónomo", "ed": "8"}, {"carrera": "Economista", "ed": "7"}, {"carrera": "Cirujano", "ed": "8"}, {"carrera": "Psicólogo experimental", "ed": "7"}, {"carrera": "Dibujante aeronáutico", "ed": "4"}, {"carrera": "Valuador-tasador de obras de arte", "ed": "8"}, {"carrera": "Estadístico, aplicación", "ed": "8"}, {"carrera": "(También véanse las ocupaciones bajo IR, is, AI, AR y AS.)", "ed": "Físico"}], "IC": [{"carrera": "Geógrafo", "ed": "7"}, {"carrera": "Analista de diseños en ingeniería", "ed": "7"}, {"carrera": "Ginecólogo", "ed": "8"}, {"carrera": "Analista empresarial", "ed": "8"}, {"carrera": "Ingeniero agrícola", "ed": "7"}, {"carrera": "Auditor interno", "ed": "7"}, {"carrera": "Ingeniero biomédico", "ed": "7"}, {"carrera": "Cito-tecnólogo (analista de cambios en células)", "ed": "8"}, {"carrera": "Ingeniero civil", "ed": "7"}, {"carrera": "Dibujante en jefe", "ed": "4"}, {"carrera": "Ingeniero en electrónica médica", "ed": "7"}, {"carrera": "navegante (Marinero, Ciencias navales)", "ed": "7"}, {"carrera": "Ingeniero químico", "ed": "7"}, {"carrera": "(También véanse las ocupaciones bajo CL IR, DE e IS.)", "ed": "Médico del deporte"}], "IE": [{"carrera": "Médico militar", "ed": "7"}, {"carrera": "Analista de sistemas", "ed": "7"}, {"carrera": "Médico naval", "ed": "7"}, {"carrera": "Consultor de internet", "ed": "4"}, {"carrera": "Meteorólogo", "ed": "7"}, {"carrera": "Director de recursos informativos", "ed": "7"}, {"carrera": "Programador de computadoras", "ed": "4"}, {"carrera": "Farmacéutico", "ed": "7"}, {"carrera": "Programador de juegos", "ed": "7"}, {"carrera": "Gerente de seguridad", "ed": "7"}, {"carrera": "Promotor de proyectos de comercio electrónico", "ed": "8"}, {"carrera": "Inspector de tierras", "ed": "7"}, {"carrera": "Químico", "ed": "7"}, {"carrera": "Jefe de laboratorio químico", "ed": "7"}, {"carrera": "Radiólogo", "ed": "8"}, {"carrera": "Matemático", "ed": "7"}, {"carrera": "Técnico de laboratorio químico", "ed": "4"}, {"carrera": "Médico aeroespacial", "ed": "8"}, {"carrera": "Veterinario", "ed": "7"}, {"carrera": "Oficial de servicios de salud pública", "ed": "6"}, {"carrera": "(También véanse las ocupaciones bajo RI.)", "ed": ""}, {"carrera": "Primer maquinista", "ed": "4"}], "IS": [{"carrera": "Psicólogo educativo", "ed": "7"}, {"carrera": "Actuario (modelos matemáticos)", "ed": "7"}, {"carrera": "Psicólogo Industrial", "ed": "7"}, {"carrera": "Alergólogo", "ed": "8"}, {"carrera": "Psicólogo organizacional", "ed": "7"}, {"carrera": "Asistente de investigaciones", "ed": "8"}, {"carrera": "Sociólogo", "ed": "7"}, {"carrera": "Audíólogo (Especialista en audición)", "ed": "8"}, {"carrera": "Supervisor de sistemas de aguas y alcantarillado", "ed": "8"}, {"carrera": "Criminólogo", "ed": "8"}, {"carrera": "(También véanse las ocupaciones bajo EI, IS e IC.)", "ed": "Dentista"}], "IR": [{"carrera": "Ingeniero aeroportuario", "ed": "7"}, {"carrera": "Administrador de bases de datos", "ed": "4"}, {"carrera": "Inmunólogo", "ed": "8"}, {"carrera": "Administrador de internet/intranet", "ed": "4"}, {"carrera": "Médico de consulta general(servicios médicos)", "ed": "7"}, {"carrera": "Administrador de recursos naturales", "ed": "7"}, {"carrera": "Mercadólogo", "ed": "7"}, {"carrera": "Analista de sistemas de cómputo", "ed": "7"}, {"carrera": "Optometrista", "ed": "4"}, {"carrera": "Anestesiólogo", "ed": "8"}, {"carrera": "Psiquiatra", "ed": "8"}, {"carrera": "Arqueólogo", "ed": "7"}, {"carrera": "Quiropráctico (Medicina física y rehabilitación)", "ed": "6"}, {"carrera": "Técnico cirujano", "ed": "7"}, {"carrera": "Tecnólogo médico", "ed": "7"}, {"carrera": "Traductor", "ed": "7"}, {"carrera": "(También Véanse las ocupaciones bajo SI, IA e IB.)", "ed": ""}], "AI": [{"carrera": "Coordinador de sitios en la red", "ed": "Analista de textos en clave (Criptoanalista)"}, {"carrera": "(especialista en desarrollo de la red)", "ed": "7"}, {"carrera": "Qrafólogo (experto/analista de la escritura)", "ed": "4"}, {"carrera": "Arquitecto", "ed": ""}, {"carrera": "Organista", "ed": "6"}, {"carrera": "Bailarín de danza clásica", "ed": "6"}, {"carrera": "(También véanse las ocupaciones bajo CA, AR, AS y AE.)", "ed": "Escenógrafo cinematográfico"}], "AE": [{"carrera": "Escritor (prosa, ficción y no ficción)", "ed": "7"}, {"carrera": "Actor", "ed": "6"}, {"carrera": "Ilustrador médico y científico", "ed": "6"}, {"carrera": "Artista de maquillaje de cuerpo", "ed": "4"}, {"carrera": "Restaurador de papeles e impresos", "ed": "7"}, {"carrera": "Artista de modas", "ed": "4"}, {"carrera": "(También véanse las ocupaciones bajo IA, AR, AS y AE.)", "ed": ""}, {"carrera": "Bailarín", "ed": "3"}], "AR": [{"carrera": "Camarógrafo (TV o cine)", "ed": "6"}, {"carrera": "Acomodador de mercancías", "ed": "3"}, {"carrera": "Cantante", "ed": "6"}, {"carrera": "Alfarero", "ed": "2"}, {"carrera": "Caricaturista", "ed": "7"}, {"carrera": "Constructor de maquetas", "ed": "4"}, {"carrera": "Columnista", "ed": "7"}, {"carrera": "Decorador de bizcochos o pasteles", "ed": "2"}, {"carrera": "Comediante", "ed": "6"}, {"carrera": "Diseñador de arreglos florales", "ed": "2"}, {"carrera": "Comentarista", "ed": "7"}, {"carrera": "Fotógrafo (estática)", "ed": "4"}, {"carrera": "Coreógrafo", "ed": "6"}, {"carrera": "Técnico artesanal con esmaltes", "ed": "3"}, {"carrera": "Crítico (de teatro, de literatura)", "ed": "6"}, {"carrera": "Técnico de escenografía", "ed": "6"}, {"carrera": "Decorador", "ed": "4"}, {"carrera": "(También véanse las ocupaciones bajo RA, AC y AI.)", "ed": ""}, {"carrera": "Director artístico", "ed": "6"}], "AS": [{"carrera": "Director coral", "ed": "6"}, {"carrera": "Bailarín de danza folclórica", "ed": "6"}, {"carrera": "Director de escenarios", "ed": "6"}, {"carrera": "Compositor", "ed": "6"}, {"carrera": "Director de orquesta", "ed": "6"}, {"carrera": "Diseñador de ropa o de modas", "ed": "7"}, {"carrera": "Diseñador de interiores", "ed": "6"}, {"carrera": "Dramaturgo", "ed": "7"}, {"carrera": "Diseñador de muebles", "ed": "6"}, {"carrera": "Instructor de danza clásica", "ed": "7"}, {"carrera": "Editor de libros (novelas, ensayos)", "ed": "7"}, {"carrera": "Instructor de modelaje", "ed": "4"}, {"carrera": "Ejecutivo de cuentas", "ed": "7"}, {"carrera": "Músico instrumental", "ed": "6"}, {"carrera": "Escultor", "ed": "6"}, {"carrera": "Profesor de arte", "ed": "7"}, {"carrera": "Especialista en investigación de inteligencia", "ed": "8"}, {"carrera": "Profesor de drama (teatro)", "ed": "7"}, {"carrera": "Especialista en planeación de bodas", "ed": "4"}, {"carrera": "Profesor de lengua inglesa", "ed": "8"}, {"carrera": "Especialista en producciones audiovisuales", "ed": "7"}, {"carrera": "Reportero", "ed": "7"}, {"carrera": "Guitarrista", "ed": "6"}, {"carrera": "Supervisor de operación", "ed": ""}, {"carrera": "Percusionista", "ed": "3"}, {"carrera": "de presentaciones de espectáculos", "ed": "6"}, {"carrera": "Pianista", "ed": "6"}, {"carrera": "(También véanse las ocupaciones bajo SA y AE.)", "ed": ""}, {"carrera": "Poeta", "ed": "7"}, {"carrera": "Supervisor de taller de letreros y anuncios", "ed": "2"}, {"carrera": "Violinista", "ed": "6"}, {"carrera": "(También véanse las ocupaciones bajo EA, AS y AC.)", "ed": ""}], "SA": [{"carrera": "Gerente de almacenaje", "ed": "7"}, {"carrera": "Asistente dental", "ed": "7"}, {"carrera": "Gerente de operaciones de cómputo", "ed": "7"}, {"carrera": "Bibliotecario", "ed": "7"}, {"carrera": "Gerente de servicios de comida rápida", "ed": "7"}, {"carrera": "Enfermera práctica con licencia", "ed": "Historiador"}, {"carrera": "(Comadrona)", "ed": "Jefe de servicios municipales"}, {"carrera": "Inspector de alimentos", "ed": "7"}, {"carrera": "Oficial de policía", "ed": "3"}, {"carrera": "Maestro de guardería", "ed": "4"}, {"carrera": "Presidente de institución financiera", "ed": "8"}, {"carrera": "Maestro de preescolar, jardín infantil o Kinder", "ed": "7"}, {"carrera": "Profesor de educación para adultos", "ed": "7"}, {"carrera": "Ministro/Sacerdote/Rabino", "ed": "8"}, {"carrera": "Profesor universitario", "ed": "8"}, {"carrera": "Orientador vocacional", "ed": "8"}, {"carrera": "Socorrista", "ed": "5"}, {"carrera": "Profesor de escuela primaria", "ed": "7"}, {"carrera": "Supervisor de educación especial", "ed": "7"}, {"carrera": "Puericulturista", "ed": "4"}, {"carrera": "Supervisor de laboratorio dental", "ed": "4"}, {"carrera": "Terapeuta del lenguaje", "ed": "8"}, {"carrera": "Supervisor de reparación de carrocería", "ed": ""}, {"carrera": "(También véanse las ocupaciones bajo AS, SI, SE y SR.)", "ed": "de automóviles"}], "SC": [{"carrera": "Técnico dentista", "ed": "4"}, {"carrera": "Asistente educativo", "ed": "6"}, {"carrera": "Terapeuta recreacional", "ed": "7"}, {"carrera": "Asistente médico", "ed": "7"}, {"carrera": "Trabajador social de rehabilitación familiar", "ed": "8"}, {"carrera": "Doble cinematográfico", "ed": "(También véanse las ocupaciones bajo ES y SC)"}, {"carrera": "Empleado de biblioteca, libros", "ed": "SI"}], "ED": [{"carrera": "en cintas de audio", "ed": "4"}, {"carrera": "Abogado civil", "ed": "8"}, {"carrera": "Empleado de servicios de comida rápida", "ed": "2"}, {"carrera": "Abogado penalista", "ed": "8"}, {"carrera": "Encargado de salón de juegos", "ed": "Administrador de archivos médicos"}, {"carrera": "Intérprete para sordos", "ed": "7"}, {"carrera": "Dietista clínico", "ed": "8"}, {"carrera": "Proyeccionista en Jefe (cine)", "ed": "6"}, {"carrera": "Enfermero militar", "ed": "4"}, {"carrera": "Técnico de consejería vocacional", "ed": "7"}, {"carrera": "Enfermero naval", "ed": "4"}, {"carrera": "Valuador-tasador de bienes raíces", "ed": "8"}, {"carrera": "Enfermero, instructor", "ed": "5"}, {"carrera": "(También véanse las ocupaciones bajo CS, SE y SR.)", "ed": "Fisioterapeuta"}], "SE": [{"carrera": "Pediatra (especialista en enfermedades de los pies)", "ed": "3"}, {"carrera": "Administrador de redes de cómputo", "ed": "4"}, {"carrera": "Psicólogo clínico", "ed": "7"}, {"carrera": "Administrador hospitalario", "ed": "8"}, {"carrera": "Psicólogo social", "ed": "7"}, {"carrera": "Ama de casa", "ed": "Supervisor de distrito"}, {"carrera": "Asistente legal", "ed": "7"}, {"carrera": "(También véanse las ocupaciones bajo IS, SR y SA.)", "ed": ""}, {"carrera": "Científico en ciencias políticas", "ed": "8"}], "SR": [{"carrera": "Consejero de rehabilitación vocacional", "ed": "7"}, {"carrera": "Atleta profesional", "ed": ""}, {"carrera": "Cosmetóiogo", "ed": "2"}, {"carrera": "Camillero", "ed": ""}, {"carrera": "Detective", "ed": "7"}, {"carrera": "Entrenador de atletas profesionales", "ed": ""}, {"carrera": "Director Atlético", "ed": "7"}, {"carrera": "Gerente de criadero de perros", "ed": ""}, {"carrera": "Director de biblioteca", "ed": "7"}, {"carrera": "Guardia fronterizo", "ed": ""}, {"carrera": "Director de educación especial", "ed": "7"}, {"carrera": "Instructor de vuelo", "ed": ""}, {"carrera": "Director de escuela", "ed": "8"}, {"carrera": "Supervisor de cosméticos", "ed": ""}, {"carrera": "Director de institución correccional", "ed": "8"}, {"carrera": "Supervisor de planta industrial", "ed": ""}, {"carrera": "Enfermero,supervisor", "ed": "5"}, {"carrera": "Supervisor de revelado de película fotográfica", "ed": ""}, {"carrera": "Especialista en relaciones laborales", "ed": "7"}, {"carrera": "Terapeuta ocupacional", "ed": ""}, {"carrera": "Estilista de peinado", "ed": "2"}, {"carrera": "(También véanse las ocupaciones bajo RS, SI y SA.)", "ed": ""}], "EA": [{"carrera": "Gerente de producción", "ed": "7"}, {"carrera": "Coordinador de modas", "ed": "7"}, {"carrera": "Jefe de bomberos", "ed": ""}, {"carrera": "Gerente de análisis de archivos", "ed": "7"}, {"carrera": "Jefe de mantenimiento aeroportuario", "ed": "3"}, {"carrera": "Gerente de locaciones (cine, TV)", "ed": "6"}, {"carrera": "Piloto del servicio de patrulla de caminos", "ed": "7"}, {"carrera": "Modelo de fotógrafos", "ed": "Representante de ventas, sistemas"}, {"carrera": "Subastador (encargado de subastas)", "ed": "de seguridad"}, {"carrera": "Supervisor de música", "ed": "7"}, {"carrera": "Supervisor de parques", "ed": "4"}, {"carrera": "(También véanse las ocupaciones bajo AE,ES,EI y ER)", "ed": "Supervisor de siderúrgica (preparación"}], "EC": [{"carrera": "de minerales, fundición y refinamiento)", "ed": "8"}, {"carrera": "Administrador ejecutivo de propiedades", "ed": "7"}, {"carrera": "Supervisor de vivero forestal", "ed": "7"}, {"carrera": "Agente de viajes", "ed": "7"}, {"carrera": "(También véanse las ocupaciones bajo RC, EC y EI)", "ed": ""}, {"carrera": "Auxiliar de oficina", "ed": "2"}], "ES": [{"carrera": "Conductor de flete terrestre", "ed": "Abogado"}, {"carrera": "Contador fiscal", "ed": "8"}, {"carrera": "Administrador de asistencia social", "ed": "8"}, {"carrera": "Despachador de servicio (servicios públicos)", "ed": "Administrador de finca"}, {"carrera": "Gerente de club de golf", "ed": "7"}, {"carrera": "Agente de bienes raíces", "ed": "4"}, {"carrera": "Gerente de sucursal de almacén", "ed": "7"}, {"carrera": "Ajustador de seguros", "ed": "6"}, {"carrera": "Inspector de seguridad y salud ocupacional", "ed": "8"}, {"carrera": "Analista ambiental (servicios", "ed": ""}, {"carrera": "Mesero", "ed": "4"}, {"carrera": "gubernamentales)", "ed": "7"}, {"carrera": "Secretario municipal (encargado de la oficina de", "ed": "Arbitro"}, {"carrera": "Registros Nacimiento, muerte, etc", "ed": "7"}, {"carrera": "Asesor bibliotecario", "ed": "7"}, {"carrera": "Superintendente de suministro de energía eléctrica", "ed": "7"}, {"carrera": "Asistente administrativo", "ed": "7"}, {"carrera": "Supervisor de aislamiento térmico", "ed": "Ayudante de terapia física"}, {"carrera": "De edificios", "ed": "7"}, {"carrera": "Barbero", "ed": "2"}, {"carrera": "Supervisor de distribución", "ed": "8"}, {"carrera": "Comprador (de bolsa, de mercancías)", "ed": "7"}, {"carrera": "Supervisor de telecomunicaciones", "ed": "7"}, {"carrera": "Conductor de ruta de ventas", "ed": "4"}, {"carrera": "(también véanse las ocupaciones bajo CE y ER)", "ed": "Consejero de seguridad"}], "EI": [{"carrera": "Corredor (financiero)", "ed": "7"}, {"carrera": "Controlador", "ed": "8"}, {"carrera": "Chef", "ed": "6"}, {"carrera": "Contratista", "ed": "7"}, {"carrera": "Director de deportes", "ed": "7"}, {"carrera": "Corredor de divisas extranjeras", "ed": "8"}, {"carrera": "Director de Investigación institucional", "ed": ""}, {"carrera": "Director de servicios alimentarios", "ed": "7"}, {"carrera": "En escuela", "ed": "8"}, {"carrera": "Gerente de educación y capacitación", "ed": "8"}, {"carrera": "Director de jardín Infantil", "ed": "8"}, {"carrera": "Ingeniero industrial", "ed": "7"}, {"carrera": "Director de museo", "ed": "8"}, {"carrera": "Investigador de servicios públicos", "ed": "8"}, {"carrera": "Director de zoológico", "ed": "7"}, {"carrera": "Supervisor de laboratorio (profesional y afín)", "ed": "4"}, {"carrera": "Evaluador de licencias para conducir", "ed": ""}, {"carrera": "Supervisor de mantenimiento", "ed": "Gerente de aeropuerto"}, {"carrera": "(servicios Públicos)", "ed": "3"}, {"carrera": "Gerente de agencia de viajes", "ed": "7"}, {"carrera": "(también véanse las ocupaciones bajo IE,ER y EA)", "ed": "Gerente de banco"}], "ER": [{"carrera": "Gerente de empleo", "ed": "7"}, {"carrera": "Agente especial (servicios gubernamentales)", "ed": "8"}, {"carrera": "Gerente de escenario (radio, TV, teatro)", "ed": "7"}, {"carrera": "Asesor en bienes muebles", "ed": "8"}, {"carrera": "Gerente de estación (radio y televisión)", "ed": "7"}, {"carrera": "Asistente de vestuario", "ed": "3"}, {"carrera": "Gerente de hotel o Motel", "ed": "7"}, {"carrera": "Botones", "ed": "Gerente mercantil de comercio electrónico"}, {"carrera": "Director de investigación y desarrollo", "ed": "8"}, {"carrera": "Guardia de cruce peatonal escolar", "ed": ""}, {"carrera": "Gerente de gasolinera", "ed": "4"}, {"carrera": "Guía de turistas", "ed": "4"}, {"carrera": "Gerente de muelles marítimos", "ed": "4"}, {"carrera": "Intérprete", "ed": "8"}, {"carrera": "Investigador privado", "ed": "7"}, {"carrera": "Jefe de departamento (colegio o universidad)", "ed": "8"}, {"carrera": "Jefe de redacción de un periódico", "ed": "7"}, {"carrera": "Juez", "ed": "8"}, {"carrera": "ES Continuación", "ed": "ED"}, {"carrera": "Productor ejecutivo, promociones", "ed": "4"}, {"carrera": "locutor de noticias Político", "ed": "4"}, {"carrera": "Sobrecargo (Asistente de vuelo)", "ed": "4"}, {"carrera": "Maestro de ciencias empresa ríales", "ed": "8"}, {"carrera": "supervisor de almacenaje (Jefe de almacén)", "ed": ""}, {"carrera": "Manicurista", "ed": "2"}, {"carrera": "supervisor de de operación de computadoras", "ed": "3"}, {"carrera": "Oficial de servicio diplomático", "ed": "7"}, {"carrera": "Vendedor de aparatos electrónicos", "ed": "4"}, {"carrera": "Planificador financiero", "ed": "8"}, {"carrera": "Vendedor de automóviles", "ed": "4"}, {"carrera": "Politico", "ed": "8"}, {"carrera": "Vendedor de productos farmacéuticos", "ed": "6"}, {"carrera": "Presidente (cualquier industria)", "ed": "8"}, {"carrera": "(También véanse las ocupaciones bajo SE y CA.)", "ed": ""}], "CA": [{"carrera": "(Véanse las carreras u ocupaciones con los códigos  AC, CR, Cl, CS y CE.)", "ed": "Empleado de oficina"}], "CE": [{"carrera": "Empleado de producciones de televisión", "ed": "6"}, {"carrera": "Agente de reservaciones (transporte aéreo]", "ed": "7"}, {"carrera": "Empleado de la oficina de hipotecas", "ed": "8"}, {"carrera": "Analista de presupuesto", "ed": "7"}, {"carrera": "Ensamblador de Instrumentos musicales", "ed": "2"}, {"carrera": "Asistente de congresista", "ed": "8"}, {"carrera": "Ensamblador de Juguetes", "ed": "2"}, {"carrera": "Encargado de barra de cafetería", "ed": "4"}, {"carrera": "Ensamblador de muebles", "ed": "2"}, {"carrera": "Especialista en operaciones de vuelo", "ed": "6"}, {"carrera": "Ensamblador de piezas electrónicas", "ed": "3"}, {"carrera": "Inspector de aduanas", "ed": "8"}, {"carrera": "Inspector de línea de ensamblaje", "ed": "4"}, {"carrera": "Inspector de Incendios", "ed": "7"}, {"carrera": "Operador de procesador de textos", "ed": "3"}, {"carrera": "Operador de Información telefónica", "ed": "3"}, {"carrera": "Operador de radio-aeronave", "ed": "6"}, {"carrera": "Pintor de dibujos animados", "ed": "4"}, {"carrera": "Programador de tripulación/ grupo de trabajo", "ed": "7"}, {"carrera": "Preparador de Impuestos", "ed": "8"}, {"carrera": "Recepcionista", "ed": "2"}, {"carrera": "Registrador de museo", "ed": "7"}, {"carrera": "Representante de seguridad de aerolínea", "ed": ""}, {"carrera": "Representante de servicios al cliente", "ed": "7"}, {"carrera": "(También véanse las ocupaciones bajo KC y CL)", "ed": ""}, {"carrera": "Secretarlo médico", "ed": "4"}], "CS": [{"carrera": "Secretario social", "ed": "2"}, {"carrera": "Agente de seguros", "ed": "8"}, {"carrera": "Supervisor de procesador de palabras", "ed": "3"}, {"carrera": "Analista de apoyo al usuario (analista", "ed": ""}, {"carrera": "(También véanse las ocupaciones bajo BC y CS.)", "ed": "de ventanilla de información)"}], "CI": [{"carrera": "Asistente de producción (explosivos)", "ed": "6"}, {"carrera": "Asistente editorial", "ed": "7"}, {"carrera": "Auxiliar bibliotecario", "ed": "7"}, {"carrera": "Contador de costos", "ed": "7"}, {"carrera": "Cajero de banco", "ed": "6"}, {"carrera": "Editor de sitios en la red", "ed": "4"}, {"carrera": "Capturista de datos", "ed": "4"}, {"carrera": "Especialista en seguridad de computadoras", "ed": "8"}, {"carrera": "Contador", "ed": "7"}, {"carrera": "Inspector de obras", "ed": "7"}, {"carrera": "Contador de sistemas", "ed": "4"}, {"carrera": "Técnico en expedientes médicos", "ed": "4"}, {"carrera": "Corrector de estilo en textos", "ed": "6"}, {"carrera": "(También véanse las ocupaciones bajo IQ CR, CS y CE)", "ed": "Despachador por radio"}], "CR": [{"carrera": "Ebanista", "ed": "3"}, {"carrera": "Analista de crédito", "ed": "8"}, {"carrera": "Empleado de contabilidad", "ed": "4"}, {"carrera": "Camarista (hotel)", "ed": "2"}, {"carrera": "Lector de medidor de servidos públicos", "ed": ""}, {"carrera": "Cartero", "ed": "Operador de teléfonos (Telefonista)"}, {"carrera": "Secretario", "ed": "2"}, {"carrera": "Secretario de juzgados", "ed": "7"}, {"carrera": "Taquillera", "ed": ""}, {"carrera": "(También véanse las ocupaciones bajo SC y CE.)", "ed": ""}]}, "riasec_profiles": {"R": {"nombre": "Realista", "actividades": "Trabajar con máquinas, herramientas, objetos o animales en entornos prácticos.", "carreras": []}, "I": {"nombre": "Investigador", "actividades": "Analizar, investigar, resolver problemas científicos o matemáticos.", "carreras": []}, "A": {"nombre": "Artístico", "actividades": "Crear, diseñar, expresar emociones mediante música, arte o literatura.", "carreras": []}, "S": {"nombre": "Social", "actividades": "Ayudar, enseñar, curar, orientar y brindar apoyo a los demás.", "carreras": []}, "E": {"nombre": "Emprendedor", "actividades": "Liderar, persuadir, dirigir proyectos, negocios o ventas.", "carreras": []}, "C": {"nombre": "Convencional", "actividades": "Organizar datos, seguir procedimientos metódicos, contabilidad y administración.", "carreras": []}}}


# ==============================================================================
# MOTOR DE CÁLCULO Y BAREMOS DE RAVEN (MATRICES PROGRESIVAS - ESCALA GENERAL)
# ==============================================================================
RAVEN_ANSWER_KEY = {
    "A1": 4, "A2": 5, "A3": 1, "A4": 2, "A5": 6, "A6": 3, "A7": 6, "A8": 2, "A9": 1, "A10": 3, "A11": 4, "A12": 5,
    "B1": 2, "B2": 6, "B3": 1, "B4": 2, "B5": 1, "B6": 3, "B7": 5, "B8": 6, "B9": 4, "B10": 3, "B11": 4, "B12": 5,
    "C1": 8, "C2": 2, "C3": 3, "C4": 8, "C5": 7, "C6": 4, "C7": 5, "C8": 1, "C9": 7, "C10": 6, "C11": 1, "C12": 2,
    "D1": 3, "D2": 4, "D3": 3, "D4": 7, "D5": 8, "D6": 6, "D7": 5, "D8": 4, "D9": 1, "D10": 2, "D11": 5, "D12": 6,
    "E1": 7, "E2": 6, "E3": 8, "E4": 2, "E5": 1, "E6": 5, "E7": 1, "E8": 6, "E9": 3, "E10": 2, "E11": 4, "E12": 5
}

RAVEN_PERCENTILES_TABLE = {
    '12':    {99: 53, 90: 47, 75: 43, 50: 39, 25: 33, 10: 24, 1: 14},
    '13-14': {99: 54, 90: 49, 75: 45, 50: 40, 25: 34, 10: 27, 1: 17},
    '15-16': {99: 55, 90: 50, 75: 46, 50: 41, 25: 35, 10: 29, 1: 19},
    '17':    {99: 56, 90: 52, 75: 49, 50: 45, 25: 39, 10: 35, 1: 28},
    '18':    {99: 57, 90: 53, 75: 50, 50: 46, 25: 42, 10: 36, 1: 29},
    '19':    {99: 57, 90: 54, 75: 51, 50: 47, 25: 42, 10: 37, 1: 30},
    '20-21': {99: 58, 90: 54, 75: 51, 50: 47, 25: 43, 10: 37, 1: 30},
    '22-65': {99: 59, 95: 58, 90: 55, 75: 52, 50: 48, 25: 44, 10: 38, 1: 31}
}

def get_raven_age_bracket(age):
    try: age = int(age)
    except: age = 25
    if age <= 12: return '12'
    elif 13 <= age <= 14: return '13-14'
    elif 15 <= age <= 16: return '15-16'
    elif age == 17: return '17'
    elif age == 18: return '18'
    elif age == 19: return '19'
    elif 20 <= age <= 21: return '20-21'
    else: return '22-65'

def calculate_raven_percentile(score, age):
    bracket = get_raven_age_bracket(age)
    p_map = RAVEN_PERCENTILES_TABLE.get(bracket, RAVEN_PERCENTILES_TABLE['22-65'])
    for p in [99, 95, 90, 75, 50, 25, 10, 1]:
        if p in p_map and score >= p_map[p]:
            return p
    return 1

def calculate_raven_diagnosis(percentile, score, age):
    bracket = get_raven_age_bracket(age)
    p50_score = RAVEN_PERCENTILES_TABLE[bracket].get(50, 48)
    
    if percentile >= 95 or score >= 58:
        return "I", "SUPERIOR", "Capacidad intelectual superior a la media de su grupo normativo."
    elif percentile >= 90:
        return "II+", "SUPERIOR AL TÉRMINO MEDIO", "Capacidad intelectual superior al término medio."
    elif percentile >= 75:
        return "II", "SUPERIOR AL TÉRMINO MEDIO", "Capacidad intelectual ligeramente por encima del promedio."
    elif score > p50_score:
        return "III+", "TÉRMINO MEDIO", "Capacidad intelectual en el término medio alto."
    elif score == p50_score:
        return "III", "TÉRMINO MEDIO", "Capacidad intelectual en el término medio exacto."
    elif percentile > 25:
        return "III-", "TÉRMINO MEDIO", "Capacidad intelectual en el término medio bajo."
    elif percentile >= 25:
        return "IV+", "INFERIOR AL TÉRMINO MEDIO", "Capacidad intelectual moderadamente por debajo del término medio."
    elif percentile >= 10:
        return "IV", "INFERIOR AL TÉRMINO MEDIO", "Capacidad intelectual en el rango inferior al promedio."
    else:
        return "V", "DEFICIENTE MENTAL", "Capacidad intelectual en el rango deficiente respecto a su grupo normativo."


# ==============================================================================
# MOTOR DE CÁLCULO ASRS V1.1 TDAH EN ADULTOS (OMS / VALDIZÁN ET AL.)
# ==============================================================================
ASRS_ADHD_ITEMS = [{"num": 1, "sec": "Parte A - Inatención", "txt": "1. ¿Con qué frecuencia comete errores cuando tiene que trabajar en un proyecto aburrido o difícil?"}, {"num": 2, "sec": "Parte A - Inatención", "txt": "2. ¿Con qué frecuencia tiene dificultades para mantener su atención cuando está aburrido o con un trabajo repetitivo?"}, {"num": 3, "sec": "Parte A - Inatención", "txt": "3. ¿Con qué frecuencia tiene dificultades para concentrarse en cuestiones que otras personas le comunican aun cuando se dirijan directamente a usted?"}, {"num": 4, "sec": "Parte A - Inatención", "txt": "4. ¿Con qué frecuencia tiene dificultades para concretar los detalles de un proyecto una vez que las partes más difíciles se han conseguido?"}, {"num": 5, "sec": "Parte A - Inatención", "txt": "5. ¿Con qué frecuencia tiene dificultades en ordenar las cosas en una tarea que requiere organización?"}, {"num": 6, "sec": "Parte A - Inatención", "txt": "6. Cuando tiene una tarea que requiere mucha reflexión, ¿con qué frecuencia la evita o demora en iniciarla?"}, {"num": 7, "sec": "Parte A - Inatención", "txt": "7. ¿Con qué frecuencia extravía cosas o tiene dificultades para encontrarlas en su casa o en el trabajo?"}, {"num": 8, "sec": "Parte A - Inatención", "txt": "8. ¿Con qué frecuencia se distrae por actividad o ruido a su alrededor?"}, {"num": 9, "sec": "Parte A - Inatención", "txt": "9. ¿Con qué frecuencia tiene dificultades para recordar citas u obligaciones?"}, {"num": 10, "sec": "Parte B - Hiperactividad / Impulsividad", "txt": "10. ¿Con qué frecuencia se inquieta o mueve sus manos o pies cuando tiene que permanecer sentado durante largo tiempo?"}, {"num": 11, "sec": "Parte B - Hiperactividad / Impulsividad", "txt": "11. ¿Con qué frecuencia abandona su asiento en reuniones o en otras situaciones en las cuales debe permanecer sentado?"}, {"num": 12, "sec": "Parte B - Hiperactividad / Impulsividad", "txt": "12. ¿Con qué frecuencia tiene sensación de inquietud?"}, {"num": 13, "sec": "Parte B - Hiperactividad / Impulsividad", "txt": "13. ¿Con qué frecuencia tiene dificultades para relajarse durante el tiempo libre?"}, {"num": 14, "sec": "Parte B - Hiperactividad / Impulsividad", "txt": "14. ¿Con qué frecuencia se nota forzado en realizar actividades, como impulsado por un motor?"}, {"num": 15, "sec": "Parte B - Hiperactividad / Impulsividad", "txt": "15. ¿Con qué frecuencia habla demasiado en ambientes sociales?"}, {"num": 16, "sec": "Parte B - Hiperactividad / Impulsividad", "txt": "16. Cuando mantiene una conversación, ¿con qué frecuencia interrumpe o termina la frase de las personas antes de que ellas concluyan?"}, {"num": 17, "sec": "Parte B - Hiperactividad / Impulsividad", "txt": "17. ¿Con qué frecuencia tiene dificultad para esperar su turno en situaciones que requieran una espera?"}, {"num": 18, "sec": "Parte B - Hiperactividad / Impulsividad", "txt": "18. ¿Con qué frecuencia interrumpe a los demás mientras están ocupados?"}]


# ==============================================================================
# MOTORES DE CÁLCULO DE AUTISMO / NEURODIVERGENCIA (AQ, RAADS-R, CAT-Q)
# ==============================================================================
AQ_ITEMS = [{"num": 1, "txt": "1. Prefiero hacer cosas con otras personas en lugar de hacerlas solo/a."}, {"num": 2, "txt": "2. Prefiero hacer las cosas de la misma manera una y otra vez."}, {"num": 3, "txt": "3. Si intento imaginar algo, me resulta muy fácil construir una imagen mental."}, {"num": 4, "txt": "4. Frecuentemente me fascina o absorbe tanto una actividad que pierdo de vista todo lo demás."}, {"num": 5, "txt": "5. A menudo me fijo en pequeños sonidos que los demás no perciben."}, {"num": 6, "txt": "6. Solía prestar atención a los números de las matrículas de los coches u otro tipo de información similar."}, {"num": 7, "txt": "7. A menudo la gente me dice que lo que he dicho es maleducado, aunque a mí no me lo parezca."}, {"num": 8, "txt": "8. Cuando leo una novela, me resulta fácil imaginar el aspecto o la personalidad de los personajes."}, {"num": 9, "txt": "9. Me fascinan las fechas y las efemérides."}, {"num": 10, "txt": "10. En un grupo social, puedo seguir fácilmente las conversaciones de varias personas al mismo tiempo."}, {"num": 11, "txt": "11. Me resulta fácil desenvolverme en situaciones sociales."}, {"num": 12, "txt": "12. Tiendo a notar detalles que otras personas no perciben."}, {"num": 13, "txt": "13. Prefiero ir a una biblioteca antes que a una fiesta."}, {"num": 14, "txt": "14. Me resulta fácil inventarme historias o cuentos."}, {"num": 15, "txt": "15. Me siento más atraído/a por las personas que por las cosas u objetos."}, {"num": 16, "txt": "16. Tiendo a tener intereses muy intensos y me molesto si no puedo dedicarme a ellos."}, {"num": 17, "txt": "17. Disfruto de la charla social superficial (charla casual)."}, {"num": 18, "txt": "18. Cuando hablo, no siempre es fácil para los demás tomar la palabra."}, {"num": 19, "txt": "19. Me fascinan los números y patrones."}, {"num": 20, "txt": "20. Cuando leo un libro, me cuesta entender las intenciones de los personajes."}, {"num": 21, "txt": "21. No suelo disfrutar leyendo novelas de ficción."}, {"num": 22, "txt": "22. Me resulta difícil hacer nuevos amigos."}, {"num": 23, "txt": "23. Noto patrones en las cosas todo el tiempo."}, {"num": 24, "txt": "24. Prefiero ir al teatro o a un museo antes que a un evento deportivo."}, {"num": 25, "txt": "25. No me molesta si mi rutina diaria se interrumpe."}, {"num": 26, "txt": "26. A menudo me doy cuenta de que no sé cómo mantener una conversación."}, {"num": 27, "txt": "27. Me resulta fácil 'leer entre líneas' cuando alguien me habla."}, {"num": 28, "txt": "28. Suelo concentrarme más en la totalidad de un dibujo o imagen que en los pequeños detalles."}, {"num": 29, "txt": "29. No se me da muy bien recordar números de teléfono."}, {"num": 30, "txt": "30. No suelo notar pequeños cambios en una habitación o en el aspecto de alguien."}, {"num": 31, "txt": "31. Sé cómo darme cuenta si alguien que me escucha se está aburriendo."}, {"num": 32, "txt": "32. Me resulta fácil hacer más de una cosa a la vez."}, {"num": 33, "txt": "33. Cuando hablo por teléfono, no estoy seguro/a de cuándo es mi turno de hablar."}, {"num": 34, "txt": "34. Me gusta hacer las cosas de forma espontánea."}, {"num": 35, "txt": "35. A menudo soy el último/a en entender el chiste o el punto humorístico de una historia."}, {"num": 36, "txt": "36. Me resulta fácil deducir lo que alguien está pensando o sintiendo solo mirando su rostro."}, {"num": 37, "txt": "37. Si hay una interrupción, puedo volver a lo que estaba haciendo muy rápidamente."}, {"num": 38, "txt": "38. Se me da bien la charla social informal."}, {"num": 39, "txt": "39. La gente a menudo me dice que sigo hablando una y otra vez del mismo tema."}, {"num": 40, "txt": "40. Cuando era niño/a, me gustaba jugar a juegos de simulación o representación con otros niños."}, {"num": 41, "txt": "41. Me gusta coleccionar información sobre categorías de cosas (ej. tipos de plantas, coches, trenes)."}, {"num": 42, "txt": "42. Me resulta difícil imaginar cómo sería ser otra persona."}, {"num": 43, "txt": "43. Me gusta planificar cuidadosamente cualquier actividad en la que participe."}, {"num": 44, "txt": "44. Disfruto de los eventos o reuniones sociales."}, {"num": 45, "txt": "45. Me resulta difícil descifrar las intenciones de otras personas."}, {"num": 46, "txt": "46. Las situaciones nuevas me provocan ansiedad o malestar."}, {"num": 47, "txt": "47. Disfruto conociendo gente nueva."}, {"num": 48, "txt": "48. Soy una persona muy diplomática y con buen tacto social."}, {"num": 49, "txt": "49. No se me da bien recordar las fechas de cumpleaños de las personas."}, {"num": 50, "txt": "50. Me resulta muy fácil jugar a juegos de simulación o fantasía con niños."}]
RAADS_R_ITEMS = [{"num": 1, "sec": "Relaciones Sociales", "txt": "1. Es difícil para mí hacer amigos/as."}, {"num": 2, "sec": "Lenguaje / Comunicación", "txt": "2. A menudo tomo literalmente lo que la gente me dice."}, {"num": 3, "sec": "Intereses Circunscritos", "txt": "3. Prefiero hacer las cosas con otras personas en vez de solo. (Inverso)"}, {"num": 4, "sec": "Intereses Sensoriomotores", "txt": "4. Me molestan mucho ciertas texturas o etiquetas de la ropa."}, {"num": 5, "sec": "Intereses Sensoriomotores", "txt": "5. A menudo me siento abrumado/a por luces brillantes o ruidos intensos."}, {"num": 6, "sec": "Relaciones Sociales", "txt": "6. Sé cómo actuar adecuadamente en situaciones sociales. (Inverso)"}, {"num": 7, "sec": "Lenguaje / Comunicación", "txt": "7. Me resulta difícil entender la ironía, el sarcasmo o el doble sentido."}, {"num": 8, "sec": "Relaciones Sociales", "txt": "8. Me resulta difícil conversar de forma casual sobre temas triviales."}, {"num": 9, "sec": "Intereses Sensoriomotores", "txt": "9. A menudo hago movimientos repetitivos con mis manos, dedos o cuerpo."}, {"num": 10, "sec": "Intereses Circunscritos", "txt": "10. Me concentro tan intensamente en mis temas de interés que olvido todo lo demás."}, {"num": 11, "sec": "Relaciones Sociales", "txt": "11. Me resulta fácil comprender los sentimientos e intenciones de los demás. (Inverso)"}, {"num": 12, "sec": "Intereses Sensoriomotores", "txt": "12. Me molestan profundamente ciertos sonidos específicos que otros parecen ignorar."}, {"num": 13, "sec": "Intereses Sensoriomotores", "txt": "13. Suelo reaccionar de forma inusualmente fuerte a los olores, saboreos o texturas."}, {"num": 14, "sec": "Relaciones Sociales", "txt": "14. A menudo me dicen que hablo demasiado o que doy demasiada información sobre temas específicos."}, {"num": 15, "sec": "Lenguaje / Comunicación", "txt": "15. A veces no sé qué responder cuando alguien me hace una pregunta personal espontánea."}, {"num": 16, "sec": "Intereses Sensoriomotores", "txt": "16. Me siento muy incómodo/a con el contacto físico de personas no muy cercanas."}, {"num": 17, "sec": "Relaciones Sociales", "txt": "17. Me cuesta trabajo saber si la persona con la que hablo está interesada o aburrida."}, {"num": 18, "sec": "Relaciones Sociales", "txt": "18. Me resulta fácil mantener contacto visual durante una conversación. (Inverso)"}, {"num": 19, "sec": "Intereses Sensoriomotores", "txt": "19. Tengo una sensibilidad inusualmente alta a ruidos, luces o toques físicos."}, {"num": 20, "sec": "Relaciones Sociales", "txt": "20. Me cuesta mucho integrarme en conversaciones de grupo con tres o más personas."}, {"num": 21, "sec": "Relaciones Sociales", "txt": "21. Suelo malinterpretar lo que la gente intenta decirme en interacciones cotidianas."}, {"num": 22, "sec": "Intereses Circunscritos", "txt": "22. Colecciono o acumulo datos detallados sobre temas muy particulares."}, {"num": 23, "sec": "Relaciones Sociales", "txt": "23. Disfruto mucho participar en fiestas y reuniones sociales populosas. (Inverso)"}, {"num": 24, "sec": "Intereses Circunscritos", "txt": "24. Me molesta profundamente que cambien mis rutinas o planes previstos."}, {"num": 25, "sec": "Intereses Circunscritos", "txt": "25. Tengo un pasatiempo o tema de interés en el que dedico la mayor parte de mi tiempo libre."}, {"num": 26, "sec": "Relaciones Sociales", "txt": "26. Me han dicho que mi lenguaje corporal, voz o postura son inusuales o rígidos."}, {"num": 27, "sec": "Lenguaje / Comunicación", "txt": "27. Entiendo con facilidad el significado de los modismos o dichos populares. (Inverso)"}, {"num": 28, "sec": "Relaciones Sociales", "txt": "28. Siento que pertenezco a un 'mundo diferente' al de las demás personas."}, {"num": 29, "sec": "Intereses Sensoriomotores", "txt": "29. Suelo tararear, balancearme o mover las piernas para autorregularme."}, {"num": 30, "sec": "Intereses Sensoriomotores", "txt": "30. Ciertas comidas o texturas me causan una aversión sensorial extrema."}, {"num": 31, "sec": "Relaciones Sociales", "txt": "31. Me resulta difícil empatizar de forma automática con las expresiones faciales ajenas."}, {"num": 32, "sec": "Intereses Sensoriomotores", "txt": "32. Me resulta difícil soportar etiquetas de ropa, costuras o materiales sintéticos."}, {"num": 33, "sec": "Relaciones Sociales", "txt": "33. Tengo amistades estables con las que me comunico de forma fluida y natural. (Inverso)"}, {"num": 34, "sec": "Intereses Sensoriomotores", "txt": "34. A menudo me siento agotado/a después de estar en entornos muy ruidosos o concurridos."}, {"num": 35, "sec": "Lenguaje / Comunicación", "txt": "35. Mi voz a menudo suena monótona, plana o con una entonación poco habitual."}, {"num": 36, "sec": "Intereses Sensoriomotores", "txt": "36. Noto pequeños detalles o sonidos que pasan desapercibidos para los demás."}, {"num": 37, "sec": "Relaciones Sociales", "txt": "37. Sé de forma intuitiva cuándo es mi turno de hablar en una conversación. (Inverso)"}, {"num": 38, "sec": "Relaciones Sociales", "txt": "38. Siento que tengo que 'aprender intelectualmente' cómo comportarme socialmente."}, {"num": 39, "sec": "Relaciones Sociales", "txt": "39. Me molesta que las personas utilicen indirectas en lugar de decir las cosas claramente."}, {"num": 40, "sec": "Relaciones Sociales", "txt": "40. Me cuesta mucho adaptar mi comportamento a distintos grupos o entornos sociales."}, {"num": 41, "sec": "Intereses Sensoriomotores", "txt": "41. Experimento una sobrecarga sensorial cuando hay demasiados estímulos simultáneos."}, {"num": 42, "sec": "Relaciones Sociales", "txt": "42. A menudo me resulta difícil entender por qué la gente se siente ofendida por mis comentarios."}, {"num": 43, "sec": "Relaciones Sociales", "txt": "43. Me resulta fácil interpretar las miradas y gestos de las personas. (Inverso)"}, {"num": 44, "sec": "Relaciones Sociales", "txt": "44. Me siento más cómodo/a interactuando con personas que comparten mis mismos intereses específicos."}, {"num": 45, "sec": "Intereses Circunscritos", "txt": "45. Organizo minuciosamente mis objetos, libros o archivos según categorías precisas."}, {"num": 46, "sec": "Intereses Sensoriomotores", "txt": "46. Disfruto de la sensación táctil de ciertos objetos o materiales concretos."}, {"num": 47, "sec": "Relaciones Sociales", "txt": "47. Disfruto mucho de las dinámicas y juegos grupales con otras personas. (Inverso)"}, {"num": 48, "sec": "Relaciones Sociales", "txt": "48. Me resulta difícil iniciar conversaciones espontáneas con personas desconocidas."}, {"num": 49, "sec": "Intereses Sensoriomotores", "txt": "49. Suelo tocar compulsivamente ciertos patrones o texturas cuando estoy estresado/a."}, {"num": 50, "sec": "Intereses Circunscritos", "txt": "50. Acumulo un conocimiento muy profundo sobre temas específicos que apasionan."}, {"num": 51, "sec": "Relaciones Sociales", "txt": "51. Me resulta confuso entender los límites en las interacciones personales."}, {"num": 52, "sec": "Intereses Circunscritos", "txt": "52. Me gusta cambiar constantemente de pasatiempos y probar temas diferentes. (Inverso)"}, {"num": 53, "sec": "Relaciones Sociales", "txt": "53. Me dicen que hablo demasiado rápido, despacio o con términos demasiado formales."}, {"num": 54, "sec": "Intereses Sensoriomotores", "txt": "54. Me molestan los cambios bruscos de temperatura o la luz solar directa."}, {"num": 55, "sec": "Relaciones Sociales", "txt": "55. A menudo me siento desconectado/a o 'afuera' de los grupos de personas."}, {"num": 56, "sec": "Intereses Sensoriomotores", "txt": "56. Tengo movimientos de autorregulación o aleteo cuando estoy muy emocionado/a o ansioso/a."}, {"num": 57, "sec": "Intereses Sensoriomotores", "txt": "57. Siento incomodidad física ante ruidos repentinos como alarmas o bocinas."}, {"num": 58, "sec": "Lenguaje / Comunicación", "txt": "58. Entiendo fácilmente las bromas, juegos de palabras y humor sutil. (Inverso)"}, {"num": 59, "sec": "Intereses Circunscritos", "txt": "59. Sigo horarios y secuencias de actividades de forma estricta."}, {"num": 60, "sec": "Relaciones Sociales", "txt": "60. Siento que las expectativas sociales habituales son complicadas e ilógicas."}, {"num": 61, "sec": "Relaciones Sociales", "txt": "61. Me cuesta mantener amistades a largo plazo debido a la desconexión comunicativa."}, {"num": 62, "sec": "Relaciones Sociales", "txt": "62. Me cuesta saber si le caigo bien o mal a alguien salvo que me lo diga explícitamente."}, {"num": 63, "sec": "Intereses Sensoriomotores", "txt": "63. Me resulta placentero estar en lugares con muchas luces de colores y música alta. (Inverso)"}, {"num": 64, "sec": "Relaciones Sociales", "txt": "64. Me resulta agotador sostener conversaciones sociales durante varias horas."}, {"num": 65, "sec": "Relaciones Sociales", "txt": "65. Prefiero escribir mis pensamientos antes que comunicarlos de forma verbal."}, {"num": 66, "sec": "Lenguaje / Comunicación", "txt": "66. Tiendo a interpretar las preguntas de forma hiperprecisa e inusual."}, {"num": 67, "sec": "Intereses Sensoriomotores", "txt": "67. Me agradan los abrazos y aperturas físicas imprevistas de otras personas. (Inverso)"}, {"num": 68, "sec": "Relaciones Sociales", "txt": "68. Me han descrito como una persona retraída, reservada o distante."}, {"num": 69, "sec": "Relaciones Sociales", "txt": "69. Me resulta difícil compartir mis experiencias emocionales con los demás."}, {"num": 70, "sec": "Intereses Circunscritos", "txt": "70. Memorizo fácilmente listados, calendarios, estadísticas o datos numéricos."}, {"num": 71, "sec": "Intereses Circunscritos", "txt": "71. Me causa un gran malestar que muevan mis pertenencias de lugar sin mi permiso."}, {"num": 72, "sec": "Relaciones Sociales", "txt": "72. Comprendo sin problemas las normas no escritas de la etiqueta social. (Inverso)"}, {"num": 73, "sec": "Intereses Circunscritos", "txt": "73. Me resulta placentero repetir patrones o secuencias de movimientos o palabras."}, {"num": 74, "sec": "Relaciones Sociales", "txt": "74. Me cuesta entender los motivos por los que las personas actúan en conflictos interpersonales."}, {"num": 75, "sec": "Relaciones Sociales", "txt": "75. Me siento más cómodo/a comunicándome en entornos virtuales que presenciales."}, {"num": 76, "sec": "Intereses Circunscritos", "txt": "76. Dedico tiempo considerable a perfeccionar o pulir detalles en mis proyectos personales."}, {"num": 77, "sec": "Relaciones Sociales", "txt": "77. Me resulta natural hacer cumplidos y comentarios sociales corteses. (Inverso)"}, {"num": 78, "sec": "Intereses Circunscritos", "txt": "78. Disfruto sumergiéndome por completo en mis pasiones sin interrupciones."}, {"num": 79, "sec": "Relaciones Sociales", "txt": "79. Siento que las conversaciones cotidianas están llenas de códigos que debo descifrar."}, {"num": 80, "sec": "Relaciones Sociales", "txt": "80. Me resulta fácil comprender los estados de ánimo de las personas a mi alrededor. (Inverso)"}]
CAT_Q_ITEMS = [{"num": 1, "sec": "Compensación", "txt": "1. He practicado expresiones faciales o la entonación de la voz frente al espejo para mejorar mis habilidades sociales."}, {"num": 2, "sec": "Enmascaramiento", "txt": "2. Monitoreo constantemente mi lenguaje corporal (gestos, postura) cuando estoy en interacción con otras personas."}, {"num": 3, "sec": "Asimilación", "txt": "3. En situaciones sociales, siento que puedo ser completamente yo mismo/a de forma espontánea. (Inverso)"}, {"num": 4, "sec": "Compensación", "txt": "4. He aprendido reglas sobre cómo entablar y mantener una conversación observando a otras personas."}, {"num": 5, "sec": "Compensación", "txt": "5. Utilizo un guion mental preconcebido cuando tengo que hablar con gente poco conocida o en llamadas telefónicas."}, {"num": 6, "sec": "Enmascaramiento", "txt": "6. Hago un esfuerzo consciente por hacer contacto visual con las personas aunque me resulte incómodo o agotador."}, {"num": 7, "sec": "Asimilación", "txt": "7. Siento la necesidad de 'actuar' o 'interpretar un personaje' para encajar en grupos sociales."}, {"num": 8, "sec": "Compensación", "txt": "8. Investigo de forma previa temas de conversación populares para asegurarme de tener algo que decir."}, {"num": 9, "sec": "Enmascaramiento", "txt": "9. Reprimo deliberadamente mis movimientos corporales o gestos repetitivos (estimulaciones / stimming) cuando estoy en público."}, {"num": 10, "sec": "Asimilación", "txt": "10. Trato de copiar los comportamientos y la vestimenta de personas que parecen socialmente exitosas."}, {"num": 11, "sec": "Compensación", "txt": "11. Utilizo preguntas estructuradas para mantener a la otra persona hablando y evitar quedarme en silencio."}, {"num": 12, "sec": "Enmascaramiento", "txt": "12. Muestro de forma natural mis verdaderas emociones y reacciones corporales en público. (Inverso)"}, {"num": 13, "sec": "Asimilación", "txt": "13. Me siento obligado/a a sonreír o asentir para parecer amable, incluso si no me siento interesado/a."}, {"num": 14, "sec": "Compensación", "txt": "14. Leo libros o artículos sobre psicología e interacción social para aprender cómo comportarme."}, {"num": 15, "sec": "Enmascaramiento", "txt": "15. Controlo cuidadosamente la intensidad de mi voz para que no suene demasiado alta, monótona o inusual."}, {"num": 16, "sec": "Asimilación", "txt": "16. Siento que el resto de las personas no conocen mi verdadera personalidad porque siempre me estoy adaptando."}, {"num": 17, "sec": "Compensación", "txt": "17. Ensayo con antelación las posibles respuestas a preguntas que alguien podría hacerme."}, {"num": 18, "sec": "Enmascaramiento", "txt": "18. Me obligo a reír cuando otros ríen, aunque no haya comprendido el chiste."}, {"num": 19, "sec": "Asimilación", "txt": "19. Me resulta fácil integrarme de manera natural a conversaciones de grupo sin tener que planearlo. (Inverso)"}, {"num": 20, "sec": "Compensación", "txt": "20. Utilizo expresiones o modismos copiados de películas, series o libros en mi lenguaje cotidiano."}, {"num": 21, "sec": "Enmascaramiento", "txt": "21. Suprimo mis intereses intensos o pasiones para no parecer extraño/a o abrumador/a frente a los demás."}, {"num": 22, "sec": "Asimilación", "txt": "22. Me siento cómodo/a siendo el centro de atención tal como soy. (Inverso)"}, {"num": 23, "sec": "Compensación", "txt": "23. Adapto meticulosamente mi tono de voz y vocabulario según la persona con la que esté hablando."}, {"num": 24, "sec": "Enmascaramiento", "txt": "24. En reuniones o fiestas, me siento relajado/a y actuó espontáneamente. (Inverso)"}, {"num": 25, "sec": "Asimilación", "txt": "25. Termino exhausto/a emocional y físicamente después de haber socializado por haber estado camuflando mis rasgos."}]

AQ_AGREE_ITEMS = {1, 2, 4, 5, 6, 7, 9, 12, 13, 16, 18, 19, 20, 21, 22, 23, 26, 33, 35, 39, 41, 42, 43, 45, 46}
AQ_DISAGREE_ITEMS = {3, 8, 10, 11, 14, 15, 17, 24, 25, 27, 28, 29, 30, 31, 32, 34, 36, 37, 38, 40, 44, 47, 48, 49, 50}
AQ_SUBSCALES_MAP = {
    "Habilidades Sociales": {1, 11, 13, 15, 22, 36, 44, 45, 47, 48},
    "Cambio de Atención / Flexibilidad": {2, 4, 10, 16, 25, 32, 34, 37, 43, 46},
    "Atención a los Detalles": {5, 6, 9, 12, 19, 23, 28, 29, 30, 49},
    "Comunicación": {7, 17, 27, 31, 33, 35, 38, 39, 40, 50},
    "Imaginación": {3, 8, 14, 18, 20, 21, 24, 26, 41, 42}
}

def process_aq_scoring(answers):
    scores_by_subscale = {k: 0 for k in AQ_SUBSCALES_MAP.keys()}
    total_score = 0
    for item in AQ_ITEMS:
        num = item['num']
        ans = answers.get(str(num), answers.get(num, 0))
        try: val = int(ans)
        except: val = 0
        is_autistic_point = False
        if num in AQ_AGREE_ITEMS and val in [1, 2]: is_autistic_point = True
        elif num in AQ_DISAGREE_ITEMS and val in [3, 4]: is_autistic_point = True
        if is_autistic_point:
            total_score += 1
            for sub_name, num_set in AQ_SUBSCALES_MAP.items():
                if num in num_set: scores_by_subscale[sub_name] += 1

    if total_score >= 32:
        classification = "Indicativo Elevado de Rasgos Autistas (AQ >= 32)"
        interpretation = (
            f"Puntuación Total AQ: {total_score} / 50 pts (Punto de Corte >= 32 pts).\n"
            "El resultado supera significativamente el punto de corte clínico del Cociente de Espectro Autista.\n"
            "El 80% de los adultos diagnosticados con autismo/Asperger obtienen una puntuación de 32 o superior.\n"
            "Se sugiere profundizar en una evaluación clínica diagnóstica."
        )
    elif total_score >= 26:
        classification = "Rasgos Autistas Moderados (AQ 26-31)"
        interpretation = (
            f"Puntuación Total AQ: {total_score} / 50 pts.\n"
            "El resultado se encuentra en el rango moderado de rasgos del espectro autista.\n"
            "Indica la presencia de características asociadas a la neurodivergencia que pueden requerir atención clínica."
        )
    else:
        classification = "Rasgos Autistas Dentro de la Norma (AQ < 26)"
        interpretation = (
            f"Puntuación Total AQ: {total_score} / 50 pts.\n"
            "El resultado se encuentra dentro del rango habitual o neurotípico de la población general."
        )

    subscales_dict = {k: {"puntuacion": v, "max": 10} for k, v in scores_by_subscale.items()}
    subscales_dict["Puntuación Total AQ"] = {"puntuacion": total_score, "max": 50}
    return total_score, subscales_dict, classification, interpretation


RAADS_R_INVERTED_ITEMS = {6, 11, 18, 23, 27, 33, 37, 43, 47, 52, 58, 63, 67, 72, 77, 80}

def process_raads_r_scoring(answers):
    scores_by_subscale = {"Relaciones Sociales": 0, "Lenguaje / Comunicación": 0, "Intereses Sensoriomotores": 0, "Intereses Circunscritos": 0}
    total_score = 0
    for item in RAADS_R_ITEMS:
        num = item['num']
        sec = item['sec']
        ans = answers.get(str(num), answers.get(num, 0))
        try: val = int(ans)
        except: val = 0
        item_score = (3 - val) if num in RAADS_R_INVERTED_ITEMS else val
        total_score += item_score
        if sec in scores_by_subscale: scores_by_subscale[sec] += item_score

    cutoffs = {
        "Relaciones Sociales": (scores_by_subscale["Relaciones Sociales"] >= 31, 31, 117),
        "Lenguaje / Comunicación": (scores_by_subscale["Lenguaje / Comunicación"] >= 4, 4, 21),
        "Intereses Sensoriomotores": (scores_by_subscale["Intereses Sensoriomotores"] >= 16, 16, 60),
        "Intereses Circunscritos": (scores_by_subscale["Intereses Circunscritos"] >= 15, 15, 42)
    }

    if total_score >= 65:
        classification = "Indicativo Clínico Compatible con TEA (RAADS-R >= 65)"
        interpretation = (
            f"Puntuación Total RAADS-R: {total_score} / 240 pts (Umbral Clínico Diagnóstico >= 65 pts).\n"
            "El resultado supera holgadamente el punto de corte validado de la escala RAADS-R para el diagnóstico de autismo en adultos.\n"
            "Desglose por Subescalas e Indicadores de Umbral:\n"
        )
        for s_name, (is_above, cut, max_p) in cutoffs.items():
            status_str = "SUPERADO ✓" if is_above else "Por debajo"
            interpretation += f"• {s_name}: {scores_by_subscale[s_name]} / {max_p} pts (Umbral {cut} pts - {status_str})\n"
    else:
        classification = "Por Debajo del Umbral Clínico (RAADS-R < 65)"
        interpretation = (
            f"Puntuación Total RAADS-R: {total_score} / 240 pts (Umbral Clínico >= 65 pts).\n"
            "La puntuación global se sitúa por debajo del umbral clínico diagnóstico validado de autismo en adultos."
        )

    subscales_dict = {
        "Relaciones Sociales": {"puntuacion": scores_by_subscale["Relaciones Sociales"], "max": 117},
        "Lenguaje / Comunicación": {"puntuacion": scores_by_subscale["Lenguaje / Comunicación"], "max": 21},
        "Intereses Sensoriomotores": {"puntuacion": scores_by_subscale["Intereses Sensoriomotores"], "max": 60},
        "Intereses Circunscritos": {"puntuacion": scores_by_subscale["Intereses Circunscritos"], "max": 42},
        "Puntuación Total RAADS-R": {"puntuacion": total_score, "max": 240}
    }
    return total_score, subscales_dict, classification, interpretation


CAT_Q_INVERTED_ITEMS = {3, 12, 19, 22, 24}

def process_cat_q_scoring(answers):
    scores_by_subscale = {"Compensación": 0, "Enmascaramiento": 0, "Asimilación": 0}
    total_score = 0
    for item in CAT_Q_ITEMS:
        num = item['num']
        sec = item['sec']
        ans = answers.get(str(num), answers.get(num, 1))
        try: val = int(ans)
        except: val = 1
        item_score = (8 - val) if num in CAT_Q_INVERTED_ITEMS else val
        total_score += item_score
        if sec in scores_by_subscale: scores_by_subscale[sec] += item_score

    if total_score >= 100:
        classification = "Camuflaje / Enmascaramiento Social Alto (CAT-Q >= 100)"
        interpretation = (
            f"Puntuación Total CAT-Q: {total_score} / 175 pts (Corte >= 100 pts).\n"
            "El resultado indica un nivel elevado de camuflaje y enmascaramiento social (masking).\n"
            "El paciente realiza un esfuerzo consciente/subconsciente significativo para ocultar sus rasgos autistas y asimilarse.\n"
            "Este perfil se asocia frecuentemente a agotamiento social (autistic burnout) y diagnóstico tardío."
        )
    else:
        classification = "Camuflaje / Enmascaramiento Social Moderado o Bajo (CAT-Q < 100)"
        interpretation = (
            f"Puntuación Total CAT-Q: {total_score} / 175 pts.\n"
            "El nivel de camuflaje o enmascaramiento social se encuentra en el rango esperable o bajo."
        )

    subscales_dict = {
        "Compensación": {"puntuacion": scores_by_subscale["Compensación"], "max": 63},
        "Enmascaramiento": {"puntuacion": scores_by_subscale["Enmascaramiento"], "max": 56},
        "Asimilación": {"puntuacion": scores_by_subscale["Asimilación"], "max": 56},
        "Puntuación Total CAT-Q": {"puntuacion": total_score, "max": 175}
    }
    return total_score, subscales_dict, classification, interpretation


def process_asrs_adhd_scoring(answers):
    score_a = 0
    score_b = 0
    
    for item in ASRS_ADHD_ITEMS:
        num = item['num']
        ans = answers.get(str(num), answers.get(num, 0))
        try: val = int(ans)
        except: val = 0
        
        if num <= 9:
            score_a += val
        else:
            score_b += val

    max_subscore = max(score_a, score_b)
    total_score = score_a + score_b

    if max_subscore >= 24 or total_score >= 40:
        classification = "Muy Probable TDAH del Adulto"
        interpretation = (
            "Resultado Altamente Significativo (Puntuación >= 24 pts en Inatención o Hiperactividad/Impulsividad).\n"
            "Es MUY PROBABLE que el consultante presente síntomas compatibles con Trastorno por Déficit de Atención e Hiperactividad (TDAH en el Adulto).\n"
            "Se recomienda evaluación neuropsicológica complementaria e indagación de sintomatología previa a los 7 años de edad."
        )
    elif max_subscore >= 17 or total_score >= 28:
        classification = "Probable TDAH del Adulto"
        interpretation = (
            "Resultado Moderado (Puntuación entre 17 y 23 pts).\n"
            "Es PROBABLE que el consultante presente sintomatología clínica de TDAH del Adulto en nivel moderado.\n"
            "Se sugiere evaluar el impacto funcional en la esfera laboral, académica y personal."
        )
    else:
        classification = "Poco Probable TDAH del Adulto"
        interpretation = (
            "Resultado Leve o Negativo (Puntuación de 0 a 16 pts).\n"
            "Es POCO PROBABLE que el consultante presente TDAH del Adulto significativo según el inventario de autoinforme ASRS."
        )

    subscales_dict = {
        "Parte A: Inatención": {"puntuacion": score_a, "max": 36},
        "Parte B: Hiperactividad / Impulsividad": {"puntuacion": score_b, "max": 36},
        "Puntuación Total ASRS": {"puntuacion": total_score, "max": 72}
    }

    return total_score, subscales_dict, classification, interpretation


def process_raven_scoring(answers, duration_seconds=0, age=25):
    series_scores = {"A": 0, "B": 0, "C": 0, "D": 0, "E": 0}
    total_score = 0
    
    item_keys = []
    for s in ["A", "B", "C", "D", "E"]:
        for i in range(1, 13):
            item_keys.append(f"{s}{i}")

    for idx, code in enumerate(item_keys):
        ans_val = answers.get(code, answers.get(str(idx+1), answers.get(idx+1, 0)))
        try: ans_val = int(ans_val)
        except: ans_val = 0
        
        correct_val = RAVEN_ANSWER_KEY.get(code, 0)
        if ans_val == correct_val:
            series_code = code[0]
            series_scores[series_code] += 1
            total_score += 1

    percentile = calculate_raven_percentile(total_score, age)
    rango, diag, desc = calculate_raven_diagnosis(percentile, total_score, age)
    
    try: dur_num = float(duration_seconds)
    except: dur_num = 0
    mins = int(dur_num // 60)
    secs = int(dur_num % 60)
    time_str = f"{mins} min {secs} seg" if dur_num > 0 else "No registrado"

    classification = f"Raven Rango {rango} — {diag} (Percentil {percentile})"

    subscales_dict = {
        "Serie A": {"puntuacion": series_scores["A"], "max": 12},
        "Serie B": {"puntuacion": series_scores["B"], "max": 12},
        "Serie C": {"puntuacion": series_scores["C"], "max": 12},
        "Serie D": {"puntuacion": series_scores["D"], "max": 12},
        "Serie E": {"puntuacion": series_scores["E"], "max": 12},
        "Tiempo de Resolución": {"puntuacion": time_str}
    }

    interp = f"Prueba de Matrices Progresivas de Raven (Escala General)\n"
    interp += f"Puntuación Directa Total (PD): {total_score} / 60 aciertos.\n"
    interp += f"Tiempo Transcurrido de Resolución: {time_str}.\n"
    interp += f"Percentil Normativo (Edad {age} años): Percentil {percentile}.\n"
    interp += f"Rango Diagnóstico: Rango {rango} — {diag}.\n"
    interp += f"Interpretación Diagnóstica: {desc}\n\n"
    interp += f"Desglose por Series:\n"
    for s in ["A", "B", "C", "D", "E"]:
        interp += f"• Serie {s}: {series_scores[s]} / 12 aciertos\n"

    return total_score, subscales_dict, classification, interp


def process_holland_scoring(answers):
    scores = {'R': 0, 'I': 0, 'A': 0, 'S': 0, 'E': 0, 'C': 0}
    code_careers = HOLLAND_MANUAL.get('code_careers', {})
    riasec_profiles = HOLLAND_MANUAL.get('riasec_profiles', {})

    for item in HOLLAND_ITEMS:
        num_str = str(item['num'])
        cat = item.get('cat', 'R')
        ans = answers.get(num_str, answers.get(item['num'], 0))
        try: val = int(ans)
        except: val = 0
        if val > 0:
            scores[cat] += val

    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    top_2_code = ''.join([k for k, v in sorted_scores[:2]])
    primary_letter = sorted_scores[0][0]

    careers_list = code_careers.get(top_2_code) or code_careers.get(primary_letter) or []

    subscales_dict = {}
    label_map = {
        'R': 'Realista (Práctico / Mecánico)',
        'I': 'Investigador (Científico / Analítico)',
        'A': 'Artístico (Creativo / Expresivo)',
        'S': 'Social (Servicio / Ayuda)',
        'E': 'Emprendedor (Liderazgo / Ventas)',
        'C': 'Convencional (Organizado / Administración)'
    }

    for letter, pts in sorted_scores:
        subscales_dict[letter] = {
            'nombre': label_map.get(letter, letter),
            'puntuacion': pts
        }

    classification = f"Código Holland: {top_2_code}"
    
    prof_info = riasec_profiles.get(primary_letter, {})
    prof_name = prof_info.get('nombre', primary_letter)
    prof_desc = prof_info.get('actividades', '')

    interp = f"Código Vocacional Holland Dominante (2 Letras): {top_2_code}.\n"
    interp += f"Perfil Primario: {primary_letter} — {prof_name}.\n"
    interp += f"Características Principales: {prof_desc}\n\n"
    
    if careers_list:
        interp += "Carreras u Ocupaciones Recomendadas según el Manual de Holland:\n"
        added_count = 0
        for car in careers_list:
            c_name = car.get('carrera', '')
            ed_level = car.get('ed', '')
            if c_name and not c_name.startswith('('):
                ed_str = f" (Nivel ED: {ed_level})" if ed_level else ""
                interp += f"• {c_name}{ed_str}\n"
                added_count += 1
                if added_count >= 15:
                    break

    max_pts = sorted_scores[0][1]
    return max_pts, subscales_dict, classification, interp


def process_mcmi_scoring(answers):
    pd_scores = {k: 0 for k in MCMI_II_TB_TABLES.keys()}
    for item_str, rules in MCMI_II_MATRIX.items():
        ans = answers.get(str(item_str), answers.get(int(item_str), 0))
        try: ans = int(ans)
        except: ans = 0
        if ans in (1, 2):
            for r in rules:
                if ans == r[1]:
                    pd_scores[r[0]] += r[2]

    tb_scores = {}
    for scale, pd_val in pd_scores.items():
        tbl = MCMI_II_TB_TABLES.get(scale, {})
        tb_scores[scale] = tbl.get(str(pd_val), tbl.get(pd_val, 0))

    pd_x = pd_scores.get('X', 0)
    pd_v = pd_scores.get('V', 0)

    is_valid = True
    val_reasons = []
    if pd_v >= 1:
        is_valid = False
        val_reasons.append(f"Escala V = {pd_v} (Respuestas inconsistentes/no válidas).")
    if pd_x < 145 or pd_x > 590:
        is_valid = False
        val_reasons.append(f"Escala X = {pd_x} (Fuera de rango 145-590).")

    adj_x = 0
    if 145 <= pd_x <= 149: adj_x = 11
    elif 150 <= pd_x <= 159: adj_x = 10
    elif 160 <= pd_x <= 169: adj_x = 9
    elif 170 <= pd_x <= 179: adj_x = 8
    elif 180 <= pd_x <= 189: adj_x = 7
    elif 190 <= pd_x <= 199: adj_x = 6
    elif 200 <= pd_x <= 209: adj_x = 5
    elif 210 <= pd_x <= 219: adj_x = 4
    elif 220 <= pd_x <= 229: adj_x = 3
    elif 230 <= pd_x <= 239: adj_x = 2
    elif 240 <= pd_x <= 249: adj_x = 1
    elif 250 <= pd_x <= 400: adj_x = 0
    elif 401 <= pd_x <= 416: adj_x = -1
    elif 417 <= pd_x <= 432: adj_x = -2
    elif 433 <= pd_x <= 448: adj_x = -3
    elif 449 <= pd_x <= 464: adj_x = -4
    elif 465 <= pd_x <= 480: adj_x = -5
    elif 481 <= pd_x <= 496: adj_x = -6
    elif 497 <= pd_x <= 512: adj_x = -7
    elif 513 <= pd_x <= 528: adj_x = -8
    elif 529 <= pd_x <= 544: adj_x = -9
    elif 545 <= pd_x <= 560: adj_x = -10
    elif 561 <= pd_x <= 576: adj_x = -11
    elif 577 <= pd_x <= 590: adj_x = -12

    adj_half_x = 0
    if 145 <= pd_x <= 159: adj_half_x = 5
    elif 160 <= pd_x <= 179: adj_half_x = 4
    elif 180 <= pd_x <= 199: adj_half_x = 3
    elif 200 <= pd_x <= 229: adj_half_x = 2
    elif 230 <= pd_x <= 249: adj_half_x = 1
    elif 250 <= pd_x <= 416: adj_half_x = 0
    elif 417 <= pd_x <= 448: adj_half_x = -1
    elif 449 <= pd_x <= 480: adj_half_x = -2
    elif 481 <= pd_x <= 512: adj_half_x = -3
    elif 513 <= pd_x <= 544: adj_half_x = -4
    elif 545 <= pd_x <= 560: adj_half_x = -5
    elif 577 <= pd_x <= 590: adj_half_x = -6

    final_tb = {}
    half_x_scales = {'S', 'C', 'P', 'SS', 'CC', 'PP'}
    no_adj_scales = {'V', 'Y', 'Z', 'X'}

    for scale, base_val in tb_scores.items():
        if scale in no_adj_scales:
            final_tb[scale] = base_val
        else:
            delta = adj_half_x if scale in half_x_scales else adj_x
            final_tb[scale] = max(0, min(115, base_val + delta))

    scale_labels = {
        "V": "Validez", "X": "Sinceridad", "Y": "Deseabilidad social", "Z": "Alteración / Autodevaluación",
        "1": "Esquizoide", "2": "Evitativa", "3": "Dependiente", "4": "Histriónica", "5": "Narcisista",
        "6A": "Antisocial", "6B": "Agresivo-Sádica", "7": "Compulsiva", "8A": "Pasivo-Agresiva", "8B": "Autodestructiva",
        "S": "Esquizotípica", "C": "Límite (Borderline)", "P": "Paranoide",
        "A": "Ansiedad", "H": "Somatomorfo", "N": "Hipomanía", "D": "Distimia", "B": "Abuso de alcohol", "T": "Abuso de drogas",
        "SS": "Pensamiento psicótico", "CC": "Depresión mayor", "PP": "Trastorno delirante"
    }

    subscales_dict = {}
    elevated_75 = []
    elevated_85 = []

    for sc, tb_val in final_tb.items():
        label = scale_labels.get(sc, sc)
        pd_val = pd_scores.get(sc, 0)
        subscales_dict[sc] = {"nombre": label, "pd": pd_val, "tb": tb_val}
        if sc not in no_adj_scales:
            if tb_val >= 85:
                elevated_85.append(f"{sc} ({label}: TB {tb_val})")
            elif tb_val >= 75:
                elevated_75.append(f"{sc} ({label}: TB {tb_val})")

    clinical_tbs = [v for k, v in final_tb.items() if k not in no_adj_scales]
    max_tb = max(clinical_tbs) if clinical_tbs else 0.0

    if not is_valid:
        classification = "Test Inválido / No Interpretable"
        interpretation = "El protocolo del MCMI-II no cumple con los criterios de validez. " + " ".join(val_reasons)
    else:
        if elevated_85:
            classification = "Elevación Clínica Severa (TB >= 85)"
            interpretation = "Escalas con significación clínica alta (TB >= 85): " + ", ".join(elevated_85) + "."
            if elevated_75:
                interpretation += " Escalas sugestivas (TB 75-84): " + ", ".join(elevated_75) + "."
        elif elevated_75:
            classification = "Rasgos / Sintomatología Sugestiva (TB 75-84)"
            interpretation = "Escalas con presencia de rasgos o sintomatología moderada (TB 75-84): " + ", ".join(elevated_75) + "."
        else:
            classification = "Perfil Clínico Dentro de Límites Normales"
            interpretation = "Todas las escalas clínicas se encuentran por debajo del punto de corte de Tasa Base 75 (TB < 75)."

    return max_tb, subscales_dict, classification, interpretation


def process_test_scoring(test_code, answers):
    """
    answers es un diccionario {"1": val, "2": val, ...}
    retorna (total_score, subscales_dict, classification_str, interpretation_str)
    """
    total_score = 0.0
    subscales = {}
    classification = ""
    interpretation = ""

    if test_code == "AQ":
        return process_aq_scoring(answers)
    elif test_code == "RAADS-R":
        return process_raads_r_scoring(answers)
    elif test_code == "CAT-Q":
        return process_cat_q_scoring(answers)
    elif test_code == "ASRS-ADHD":
        return process_asrs_adhd_scoring(answers)
    elif test_code == "RAVEN":
        patient_age = 25
        if assignment and assignment.get("patient_id"):
            cur = db.cursor()
            cur.execute("SELECT fecha_nacimiento FROM pacientes WHERE id = ?", (assignment["patient_id"],))
            p_row = cur.fetchone()
            if p_row and p_row[0]:
                try:
                    from datetime import datetime
                    dob = datetime.strptime(str(p_row[0])[:10], "%Y-%m-%d")
                    patient_age = (datetime.now() - dob).days // 365
                except: pass
        dur_sec = request_data.get("duration_seconds", 0) if isinstance(request_data, dict) else 0
        return process_raven_scoring(answers, duration_seconds=dur_sec, age=patient_age)
    elif test_code == "HOLLAND":
        return process_holland_scoring(answers)
    elif test_code == "MCMI-II":
        return process_mcmi_scoring(answers)
    elif test_code == "BDI-II":
        for k, v in answers.items():
            try: total_score += float(v)
            except: pass

        if total_score <= 13:
            classification = "Depresión Mínima"
            interpretation = "Puntuación entre 0 y 13. Muestra una vivencia emocional estable sin indicadores clínicos significativos de depresión."
        elif total_score <= 19:
            classification = "Depresión Leve"
            interpretation = "Puntuación entre 14 y 19. Presencia de sintomatología depresiva leve. Se sugiere monitorear fluctuaciones del estado de ánimo."
        elif total_score <= 28:
            classification = "Depresión Moderada"
            interpretation = "Puntuación entre 20 y 28. Presencia de clínica depresiva moderada. Se recomienda abordaje focalizado y evaluación de factores estresantes."
        else:
            classification = "Depresión Grave"
            interpretation = "Puntuación entre 29 y 63. Sintomatología depresiva severa. Requiere intervención prioritaria y plan de acompañamiento intensivo."

    elif test_code == "BAI":
        for k, v in answers.items():
            try: total_score += float(v)
            except: pass

        if total_score <= 7:
            classification = "Ansiedad Mínima"
            interpretation = "Puntuación entre 0 y 7. Niveles basales normales de ansiedad sin interferencia significativa."
        elif total_score <= 15:
            classification = "Ansiedad Leve"
            interpretation = "Puntuación entre 8 y 15. Sintomatología ansiosa leve, principalmente manifestada de forma intermitente."
        elif total_score <= 25:
            classification = "Ansiedad Moderada"
            interpretation = "Puntuación entre 16 y 25. Ansiedad clínica moderada con activación somática u objetiva relevante."
        else:
            classification = "Ansiedad Grave"
            interpretation = "Puntuación entre 26 y 63. Niveles elevados y severos de ansiedad. Justifica abordaje terapéutico prioritario."

    elif test_code == "TCS":
        processed_answers = {}
        for num in range(1, 13):
            val = float(answers.get(str(num), answers.get(num, 3)))
            if num in [2, 6, 8]:
                val = 6.0 - val
            processed_answers[num] = val

        aceptacion = sum(processed_answers[n] for n in [3, 5, 7, 9, 11])
        congruencia = sum(processed_answers[n] for n in [1, 2, 4, 6, 8, 10, 12])
        total_score = aceptacion + congruencia

        subscales = {
            "Aceptación de la Identidad": round(aceptacion, 1),
            "Congruencia de la Apariencia": round(congruencia, 1)
        }
        classification = f"Aceptación: {int(aceptacion)}/25 | Congruencia: {int(congruencia)}/35"
        interpretation = (
            f"Subescala Aceptación de la Identidad: {int(aceptacion)} pts (Rango 5-25). "
            f"Subescala Congruencia de la Apariencia: {int(congruencia)} pts (Rango 7-35). "
            "Puntuaciones más altas en Aceptación reflejan consolidación del orgullo identitario y autoaceptación afectiva."
        )

    elif test_code == "UGDS-GS":
        processed_answers = {}
        for num in range(1, 19):
            val = float(answers.get(str(num), answers.get(num, 3)))
            if num in [2, 6, 10, 15, 16]:
                val = 6.0 - val
            processed_answers[num] = val

        distres = sum(processed_answers[n] for n in [1, 3, 4, 5, 7, 8, 9, 11, 12, 13, 14, 17, 18])
        afirmacion = sum(processed_answers[n] for n in [2, 6, 10, 15, 16])
        total_score = sum(processed_answers.values())

        subscales = {
            "Distrés por Incongruencia": round(distres, 1),
            "Resiliencia y Afirmación": round(afirmacion, 1)
        }

        if total_score <= 40:
            classification = "Disforia Mínima o Nula"
            interpretation = f"Puntuación Total: {int(total_score)}/90. Niveles mínimos o nulos de distrés o disforia por incongruencia de género."
        elif total_score <= 60:
            classification = "Disforia Moderada / Malestar Intermitente"
            interpretation = f"Puntuación Total: {int(total_score)}/90. Malestar intermitente. Característico de transiciones avanzadas o identidades no binarias."
        else:
            classification = "Disforia de Género Clínicamente Significativa"
            interpretation = f"Puntuación Total: {int(total_score)}/90. Disforia de género elevada. Justifica acompañamiento de afirmación de género prioritario."

    return total_score, subscales, classification, interpretation


@app.route('/evaluacion/<token>', methods=['GET'])
def render_public_test_page(token):
    return render_template('index.html')


@app.route('/api/tests/catalogo', methods=['GET'])
def api_get_tests_catalogo():
    db = get_db()
    ensure_tests_tables(db)
    cursor = db.cursor()
    cursor.execute("SELECT code, nombre, siglas, categoria, descripcion FROM tests_definiciones")
    rows = cursor.fetchall()
    return jsonify({'tests': [dict(r) for r in rows]})


@app.route('/api/tests/asignar', methods=['POST'])
def api_asignar_test():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'No autorizado.'}), 401

    try:
        db = get_db()
        ensure_usuarios_columns(db)
        ensure_tests_tables(db)
        cursor = db.cursor()

        role = session.get('role', '')
        is_admin = role in ['admin', 'superadmin'] or user_id == 1

        cursor.execute("SELECT bloqueo_tests, role FROM usuarios WHERE id = ?", (user_id,))
        usr = cursor.fetchone()
        if usr:
            usr_dict = dict(usr)
            if usr_dict.get('role') in ['admin', 'superadmin']:
                is_admin = True
            if usr_dict.get('bloqueo_tests') == 1 and not is_admin:
                return jsonify({'error': 'El módulo de Tests Psicológicos se encuentra restringido para tu usuario.'}), 403

        data = request.json or {}
        patient_id = data.get('patient_id')
        test_code = data.get('test_code')
        modo = data.get('modo_aplicacion', 'link')

        if not patient_id or not test_code:
            return jsonify({'error': 'Faltan datos obligatorios.'}), 400

        if is_admin:
            cursor.execute("SELECT id, nombres, apellidos, telefono FROM pacientes WHERE id = ?", (patient_id,))
        else:
            cursor.execute("SELECT id, nombres, apellidos, telefono FROM pacientes WHERE id = ? AND (psicologo_id = ? OR psicologo_id IS NULL)", (patient_id, user_id))
        pac = cursor.fetchone()
        if not pac:
            return jsonify({'error': 'Acceso denegado: El consultante no pertenece a tu consulta activa.'}), 404

        token = uuid.uuid4().hex
        cursor.execute("""
            INSERT INTO test_asignaciones (uuid_token, patient_id, user_id, test_code, estado, modo_aplicacion)
            VALUES (?, ?, ?, ?, 'pendiente', ?)
        """, (token, patient_id, user_id, test_code, modo))
        db.commit()

        url_test = f"{request.host_url.rstrip('/')}/evaluacion/{token}"
        clean_phone = (pac['telefono'] or '').replace(' ', '').replace('-', '').replace('+', '')

        notify_patient_firebase(
            patient_id,
            "🧪 Nuevo Test Psicológico Asignado",
            f"Tu psicólogo te ha asignado una evaluación psicológica ({test_code}) para responder.",
            link=url_test,
            icon="🧪"
        )

        whatsapp_url = None
        if clean_phone:
            import urllib.parse
            msg_text = f"Hola {pac['nombres']}, te comparto el enlace para responder tu evaluación psicológica: {url_test}"
            whatsapp_url = f"https://api.whatsapp.com/send?phone={clean_phone}&text={urllib.parse.quote(msg_text)}"

        return jsonify({
            'success': 'Test asignado exitosamente.',
            'assignment_id': cursor.lastrowid,
            'token': token,
            'url': url_test,
            'url_test': url_test,
            'whatsapp_phone': clean_phone,
            'whatsapp_url': whatsapp_url,
            'paciente_nombre': f"{pac['nombres']} {pac['apellidos']}".strip()
        })
    except Exception as e:
        import traceback
        print("ERROR EN API_ASIGNAR_TEST:", traceback.format_exc())
        return jsonify({'error': f'Error al asignar test: {str(e)}'}), 500


@app.route('/api/public/evaluacion/<token>', methods=['GET'])
def api_get_public_evaluacion(token):
    db = get_db()
    ensure_tests_tables(db)
    cursor = db.cursor()

    cursor.execute("""
        SELECT a.*, p.nombres as pac_nombres, p.apellidos as pac_apellidos,
               u.nombres as psic_nombres, u.apellidos as psic_apellidos, u.nomenclatura as psic_titulo, u.foto_titulo as psic_foto
        FROM test_asignaciones a
        JOIN pacientes p ON a.patient_id = p.id
        JOIN usuarios u ON a.user_id = u.id
        WHERE a.uuid_token = ?
    """, (token,))
    row = cursor.fetchone()
    if not row:
        return jsonify({'error': 'Evaluación no encontrada o token inválido.'}), 404

    assign = dict(row)
    tcode = (assign.get('test_code') or '').strip()

    # Búsqueda inteligente por código exacto, siglas o patrón
    cursor.execute("SELECT * FROM tests_definiciones WHERE LOWER(code) = LOWER(?) OR LOWER(siglas) = LOWER(?)", (tcode, tcode))
    test_def_row = cursor.fetchone()
    if not test_def_row:
        cursor.execute("SELECT * FROM tests_definiciones WHERE LOWER(code) LIKE LOWER(?) OR LOWER(siglas) LIKE LOWER(?)", (f"%{tcode}%", f"%{tcode}%"))
        test_def_row = cursor.fetchone()

    if test_def_row:
        test_def = dict(test_def_row)
        try: test_def['escala_opciones'] = json.loads(test_def['escala_opciones_json'])
        except: test_def['escala_opciones'] = []

        try: test_def['items'] = json.loads(test_def['items_json'])
        except: test_def['items'] = []
    else:
        # Fallback dinámico automático para asegurar que NINGUNA evaluación falle jamás al cargar
        test_def = {
            'code': tcode,
            'nombre': f"Evaluación Psicológica ({tcode})",
            'siglas': tcode,
            'categoria': 'Evaluación Clínica',
            'descripcion': 'Instrumento de evaluación psicológica estandarizado.',
            'instrucciones': 'Lea con atención cada afirmación e indique la opción que mejor describa su vivencia o estado actual.',
            'escala_opciones': [
                {'val': 0, 'txt': '0 = En absoluto / Nunca'},
                {'val': 1, 'txt': '1 = Levemente / A veces'},
                {'val': 2, 'txt': '2 = Moderadamente / Frecuentemente'},
                {'val': 3, 'txt': '3 = Severamente / Casi siempre'}
            ],
            'items': [{'num': i, 'txt': f'Ítem {i}'} for i in range(1, 21)]
        }

    return jsonify({
        'assignment': {
            'id': assign['id'],
            'token': assign['uuid_token'],
            'estado': assign['estado'],
            'fecha_asignacion': assign['fecha_asignacion'],
            'fecha_completado': assign['fecha_completado'],
            'test_code': assign['test_code'],
            'paciente_nombre': f"{assign['pac_nombres']} {assign['pac_apellidos']}".strip(),
            'psicologo_nombre': f"Psic. {assign['psic_nombres']} {assign['psic_apellidos']}".strip(),
            'psicologo_titulo': assign['psic_titulo'] or 'Psicólogo Clínico',
            'psicologo_foto': assign['psic_foto'] or '/static/logo.png',
            'puntaje_total': assign['puntaje_total'],
            'clasificacion_resultado': assign['clasificacion_resultado'],
            'interpretacion_clinica': assign['interpretacion_clinica'],
            'subescalas': json.loads(assign['subescalas_json']) if assign.get('subescalas_json') else {}
        },
        'test_definition': test_def
    })


@app.route('/api/public/evaluacion/<token>/responder', methods=['POST'])
def api_responder_public_evaluacion(token):
    db = get_db()
    ensure_tests_tables(db)
    cursor = db.cursor()

    cursor.execute("SELECT * FROM test_asignaciones WHERE uuid_token = ?", (token,))
    row = cursor.fetchone()
    if not row:
        return jsonify({'error': 'Evaluación no encontrada.'}), 404

    assign = dict(row)
    if assign['estado'] == 'completado':
        return jsonify({'error': 'Esta evaluación ya fue completada previamente.', 'already_completed': True}), 400

    data = request.json or {}
    answers = data.get('respuestas', {})
    if not answers:
        return jsonify({'error': 'Debe enviar las respuestas del test.'}), 400

    total_score, subscales, classification, interpretation = process_test_scoring(assign['test_code'], answers)

    try:
        cursor.execute("""
            UPDATE test_asignaciones SET
                estado = 'completado',
                fecha_completado = CURRENT_TIMESTAMP,
                respuestas_json = ?,
                puntaje_total = ?,
                subescalas_json = ?,
                clasificacion_resultado = ?,
                interpretacion_clinica = ?
            WHERE uuid_token = ?
        """, (json.dumps(answers), total_score, json.dumps(subscales), classification, interpretation, token))
        db.commit()

        return jsonify({
            'success': 'Evaluación completada exitosamente.',
            'puntaje_total': total_score,
            'subescalas': subscales,
            'clasificacion': classification,
            'interpretacion': interpretation
        })
    except Exception as e:
        db.rollback()
        return jsonify({'error': f'Error al guardar respuestas: {str(e)}'}), 500


@app.route('/api/tests/historial', methods=['GET'])
def api_get_all_tests_historial():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'No autorizado.'}), 401

    try:
        db = get_db()
        ensure_tests_tables(db)
        cursor = db.cursor()

        role = session.get('role', '')
        is_admin = role in ['admin', 'superadmin'] or user_id == 1

        patient_id = request.args.get('patient_id')

        if patient_id:
            if is_admin:
                cursor.execute("""
                    SELECT a.*, 
                           COALESCE(td.nombre, 'Prueba Psicológica') as test_nombre, 
                           COALESCE(td.siglas, a.test_code) as test_siglas, 
                           COALESCE(td.categoria, 'Evaluación') as test_categoria,
                           p.nombres as patient_nombres, p.apellidos as patient_apellidos, p.cedula as patient_cedula, p.telefono as patient_telefono
                    FROM test_asignaciones a
                    LEFT JOIN tests_definiciones td ON a.test_code = td.code
                    LEFT JOIN pacientes p ON a.patient_id = p.id
                    WHERE a.patient_id = ?
                    ORDER BY a.fecha_asignacion DESC
                """, (patient_id,))
            else:
                cursor.execute("""
                    SELECT a.*, 
                           COALESCE(td.nombre, 'Prueba Psicológica') as test_nombre, 
                           COALESCE(td.siglas, a.test_code) as test_siglas, 
                           COALESCE(td.categoria, 'Evaluación') as test_categoria,
                           p.nombres as patient_nombres, p.apellidos as patient_apellidos, p.cedula as patient_cedula, p.telefono as patient_telefono
                    FROM test_asignaciones a
                    LEFT JOIN tests_definiciones td ON a.test_code = td.code
                    LEFT JOIN pacientes p ON a.patient_id = p.id
                    WHERE a.patient_id = ? AND (a.user_id = ? OR p.psicologo_id = ?)
                    ORDER BY a.fecha_asignacion DESC
                """, (patient_id, user_id, user_id))
        else:
            if is_admin:
                cursor.execute("""
                    SELECT a.*, 
                           COALESCE(td.nombre, 'Prueba Psicológica') as test_nombre, 
                           COALESCE(td.siglas, a.test_code) as test_siglas, 
                           COALESCE(td.categoria, 'Evaluación') as test_categoria,
                           p.nombres as patient_nombres, p.apellidos as patient_apellidos, p.cedula as patient_cedula, p.telefono as patient_telefono
                    FROM test_asignaciones a
                    LEFT JOIN tests_definiciones td ON a.test_code = td.code
                    LEFT JOIN pacientes p ON a.patient_id = p.id
                    ORDER BY a.fecha_asignacion DESC
                """)
            else:
                cursor.execute("""
                    SELECT a.*, 
                           COALESCE(td.nombre, 'Prueba Psicológica') as test_nombre, 
                           COALESCE(td.siglas, a.test_code) as test_siglas, 
                           COALESCE(td.categoria, 'Evaluación') as test_categoria,
                           p.nombres as patient_nombres, p.apellidos as patient_apellidos, p.cedula as patient_cedula, p.telefono as patient_telefono
                    FROM test_asignaciones a
                    LEFT JOIN tests_definiciones td ON a.test_code = td.code
                    LEFT JOIN pacientes p ON a.patient_id = p.id
                    WHERE a.user_id = ? OR p.psicologo_id = ?
                    ORDER BY a.fecha_asignacion DESC
                """, (user_id, user_id))

        rows = cursor.fetchall()
        results = []
        for r in rows:
            d = dict(r)
            try: d['subescalas'] = json.loads(d['subescalas_json']) if d.get('subescalas_json') else {}
            except: d['subescalas'] = {}
            try: d['respuestas'] = json.loads(d['respuestas_json']) if d.get('respuestas_json') else {}
            except: d['respuestas'] = {}
            d['url_test'] = f"{request.host_url.rstrip('/')}/evaluacion/{d.get('uuid_token', '')}"
            results.append(d)

        return jsonify({'tests': results})
    except Exception as e:
        import traceback
        print(f"Error en api_get_all_tests_historial: {e}")
        traceback.print_exc()
        return jsonify({'tests': [], 'error': str(e)}), 500




@app.route('/api/tests/paciente/<int:patient_id>', methods=['GET'])
def api_get_tests_paciente(patient_id):
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'No autorizado.'}), 401

    try:
        db = get_db()
        ensure_tests_tables(db)
        cursor = db.cursor()

        cursor.execute("""
            SELECT a.*, 
                   COALESCE(td.nombre, 'Prueba Psicológica') as test_nombre, 
                   COALESCE(td.siglas, a.test_code) as test_siglas, 
                   COALESCE(td.categoria, 'Evaluación') as test_categoria
            FROM test_asignaciones a
            LEFT JOIN tests_definiciones td ON a.test_code = td.code
            WHERE a.patient_id = ? AND a.user_id = ?
            ORDER BY a.fecha_asignacion DESC
        """, (patient_id, user_id))

        rows = cursor.fetchall()
        results = []
        for r in rows:
            d = dict(r)
            try: d['subescalas'] = json.loads(d['subescalas_json']) if d.get('subescalas_json') else {}
            except: d['subescalas'] = {}
            try: d['respuestas'] = json.loads(d['respuestas_json']) if d.get('respuestas_json') else {}
            except: d['respuestas'] = {}
            d['url_test'] = f"{request.host_url.rstrip('/')}/evaluacion/{d.get('uuid_token', '')}"
            results.append(d)

        return jsonify({'tests': results})
    except Exception as e:
        import traceback
        print(f"Error en api_get_tests_paciente: {e}")
        traceback.print_exc()
        return jsonify({'tests': [], 'error': str(e)}), 500



@app.route('/api/tests/asignacion/<int:assignment_id>/export/word', methods=['GET'])
def api_export_test_word(assignment_id):
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'No autorizado.'}), 401

    db = get_db()
    cursor = db.cursor()

    cursor.execute("""
        SELECT a.*, td.nombre as test_nombre, td.siglas as test_siglas, td.categoria as test_categoria, td.preguntas_json,
               p.nombres as patient_nombres, p.apellidos as patient_apellidos, p.cedula as patient_cedula
        FROM test_asignaciones a
        JOIN tests_definiciones td ON a.test_code = td.code
        JOIN pacientes p ON a.patient_id = p.id
        WHERE a.id = ? AND a.user_id = ?
    """, (assignment_id, user_id))

    row = cursor.fetchone()
    if not row:
        return jsonify({'error': 'Evaluación no encontrada.'}), 404

    data = dict(row)
    patient_name = f"{data['patient_nombres']} {data['patient_apellidos']}"
    test_title = f"{data['test_siglas']} — {data['test_nombre']}"

    import io
    from docx import Document
    from docx.shared import Inches, Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.table import WD_TABLE_ALIGNMENT

    doc = Document()

    title_p = doc.add_paragraph()
    title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run_title = title_p.add_run("INFORME DE EVALUACIÓN PSICOLÓGICA")
    run_title.font.name = 'Arial'
    run_title.font.size = Pt(16)
    run_title.font.bold = True
    run_title.font.color.rgb = RGBColor(112, 46, 94)

    sub_p = doc.add_paragraph()
    sub_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run_sub = sub_p.add_run("Espacio Terapéutico — Reporte Psicométrico Estandarizado")
    run_sub.font.name = 'Arial'
    run_sub.font.size = Pt(10)
    run_sub.font.italic = True
    run_sub.font.color.rgb = RGBColor(100, 116, 139)

    doc.add_paragraph().paragraph_format.space_after = Pt(12)

    table_info = doc.add_table(rows=4, cols=2)
    table_info.alignment = WD_TABLE_ALIGNMENT.CENTER
    table_info.style = 'Table Grid'

    info_data = [
        ("Consultante:", patient_name),
        ("Cédula (CI):", data.get('patient_cedula') or 'Sin información'),
        ("Evaluación Aplicada:", test_title),
        ("Fecha de Aplicación:", str(data.get('fecha_respuesta') or data.get('fecha_asignacion') or ''))
    ]

    for idx, (label, val) in enumerate(info_data):
        row_cells = table_info.rows[idx].cells
        p0 = row_cells[0].paragraphs[0]
        r0 = p0.add_run(label)
        r0.font.bold = True
        r0.font.size = Pt(9.5)
        
        p1 = row_cells[1].paragraphs[0]
        r1 = p1.add_run(val)
        r1.font.size = Pt(9.5)

    doc.add_paragraph().paragraph_format.space_after = Pt(12)

    heading_res = doc.add_heading("1. Resultado y Clasificación Clínica", level=2)
    heading_res.runs[0].font.color.rgb = RGBColor(112, 46, 94)

    p_res = doc.add_paragraph()
    r_diag_lbl = p_res.add_run("Diagnóstico / Clasificación: ")
    r_diag_lbl.font.bold = True
    r_diag_val = p_res.add_run(data.get('clasificacion_resultado') or 'Completado')
    r_diag_val.font.bold = True
    r_diag_val.font.size = Pt(12)
    r_diag_val.font.color.rgb = RGBColor(112, 46, 94)

    p_score = doc.add_paragraph()
    r_score_lbl = p_score.add_run("Puntuación Total Obtenida: ")
    r_score_lbl.font.bold = True
    r_score_val = p_score.add_run(f"{data.get('puntaje_total', 0)} pts")
    r_score_val.font.bold = True

    sub_json = data.get('subescalas_json')
    if sub_json:
        try:
            sub_dict = json.loads(sub_json)
            if sub_dict:
                p_sub = doc.add_paragraph()
                p_sub.add_run("Desglose por Subescalas:").font.bold = True
                for s_name, s_val in sub_dict.items():
                    doc.add_paragraph(f"  • {s_name}: {s_val} pts", style='List Bullet')
        except: pass

    if data.get('interpretacion_clinica'):
        doc.add_heading("2. Interpretación Diagnóstica para Historia Clínica", level=2).runs[0].font.color.rgb = RGBColor(112, 46, 94)
        p_inter = doc.add_paragraph(data['interpretacion_clinica'])
        p_inter.paragraph_format.line_spacing = 1.25

    doc.add_heading("3. Ficha de Respuestas Ítem por Ítem", level=2).runs[0].font.color.rgb = RGBColor(112, 46, 94)
    
    resp_json = data.get('respuestas_json')
    questions = []
    try: questions = json.loads(data['preguntas_json']) if data.get('preguntas_json') else []
    except: pass
    
    answers = {}
    try: answers = json.loads(resp_json) if resp_json else {}
    except: pass

    if questions:
        table_resp = doc.add_table(rows=1, cols=3)
        table_resp.style = 'Table Grid'
        hdr_cells = table_resp.rows[0].cells
        hdr_cells[0].paragraphs[0].add_run("Ítem").font.bold = True
        hdr_cells[1].paragraphs[0].add_run("Pregunta / Reactivo").font.bold = True
        hdr_cells[2].paragraphs[0].add_run("Valor / Opción Seleccionada").font.bold = True

        for q in questions:
            q_num = str(q.get('numero', ''))
            ans_val = answers.get(q_num, 'S/R')
            ans_text = str(ans_val)
            for opt in q.get('opciones', []):
                if str(opt.get('valor')) == str(ans_val):
                    ans_text = f"{ans_val} — {opt.get('texto', '')}"
                    break

            row_cells = table_resp.add_row().cells
            row_cells[0].paragraphs[0].add_run(f"Item {q_num}")
            row_cells[1].paragraphs[0].add_run(q.get('titulo') or q.get('pregunta') or '')
            row_cells[2].paragraphs[0].add_run(ans_text)

    doc.add_paragraph().paragraph_format.space_before = Pt(24)
    p_sign = doc.add_paragraph()
    p_sign.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    p_sign.add_run("_________________________________________\nFirma y Sello Profesional").font.size = Pt(9.5)

    file_stream = io.BytesIO()
    doc.save(file_stream)
    file_stream.seek(0)

    clean_filename = f"Informe_{data['test_siglas']}_{data['patient_nombres']}_{data['patient_apellidos']}.docx".replace(" ", "_")
    return send_file(
        file_stream,
        as_attachment=True,
        download_name=clean_filename,
        mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    )


@app.route('/api/tests/asignacion/<int:assignment_id>/export/pdf', methods=['GET'])
def api_export_test_pdf(assignment_id):
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'No autorizado.'}), 401

    db = get_db()
    cursor = db.cursor()

    cursor.execute("""
        SELECT a.*, td.nombre as test_nombre, td.siglas as test_siglas, td.categoria as test_categoria, td.preguntas_json,
               p.nombres as patient_nombres, p.apellidos as patient_apellidos, p.cedula as patient_cedula
        FROM test_asignaciones a
        JOIN tests_definiciones td ON a.test_code = td.code
        JOIN pacientes p ON a.patient_id = p.id
        WHERE a.id = ? AND a.user_id = ?
    """, (assignment_id, user_id))

    row = cursor.fetchone()
    if not row:
        return jsonify({'error': 'Evaluación no encontrada.'}), 404

    data = dict(row)
    patient_name = f"{data['patient_nombres']} {data['patient_apellidos']}"
    test_title = f"{data['test_siglas']} — {data['test_nombre']}"

    questions = []
    try: questions = json.loads(data['preguntas_json']) if data.get('preguntas_json') else []
    except: pass

    answers = {}
    try: answers = json.loads(data['respuestas_json']) if data.get('respuestas_json') else {}
    except: pass

    subscales = {}
    try: subscales = json.loads(data['subescalas_json']) if data.get('subescalas_json') else {}
    except: pass

    items_rows_html = ""
    for q in questions:
        q_num = str(q.get('numero', ''))
        ans_val = answers.get(q_num, 'N/A')
        ans_text = str(ans_val)
        for opt in q.get('opciones', []):
            if str(opt.get('valor')) == str(ans_val):
                ans_text = f"<strong>({ans_val})</strong> {opt.get('texto', '')}"
                break

        items_rows_html += f"""
        <tr>
            <td style="padding: 8px 12px; border-bottom: 1px solid #e2e8f0; font-weight: 700; color: #702e5e;">Ítem {q_num}</td>
            <td style="padding: 8px 12px; border-bottom: 1px solid #e2e8f0; color: #1e293b;">{q.get('titulo') or q.get('pregunta') or ''}</td>
            <td style="padding: 8px 12px; border-bottom: 1px solid #e2e8f0; color: #0f172a;">{ans_text}</td>
        </tr>
        """

    subscales_html = ""
    if subscales:
        subscales_html = "<div style='margin-top: 1rem; background: #f8fafc; padding: 12px; border-radius: 8px; border: 1px solid #cbd5e1;'><strong style='color:#334155;'>Subescalas:</strong><ul style='margin: 4px 0 0 0; padding-left: 20px;'>"
        for k, v in subscales.items():
            subscales_html += f"<li><strong>{k}:</strong> {v} pts</li>"
        subscales_html += "</ul></div>"

    html_content = f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <title>Informe Psicológico - {patient_name}</title>
        <style>
            body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #f8fafc; color: #0f172a; margin: 0; padding: 20px; }}
            .report-card {{ max-width: 850px; margin: 0 auto; background: white; border-radius: 16px; padding: 2.5rem; box-shadow: 0 10px 30px rgba(0,0,0,0.08); }}
            .header {{ text-align: center; border-bottom: 2px solid #702e5e; padding-bottom: 1rem; margin-bottom: 1.5rem; }}
            .header h1 {{ margin: 0; font-size: 1.6rem; color: #702e5e; font-weight: 800; }}
            .header p {{ margin: 4px 0 0 0; font-size: 0.9rem; color: #64748b; font-weight: 600; }}
            .info-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; background: #fdf4ff; border: 1.5px solid #f0abfc; padding: 1rem; border-radius: 12px; margin-bottom: 1.5rem; }}
            .info-item {{ font-size: 0.9rem; color: #334155; }}
            .info-item strong {{ color: #702e5e; }}
            .result-box {{ background: linear-gradient(135deg, #702e5e 0%, #a855f7 100%); color: white; border-radius: 12px; padding: 1.25rem; text-align: center; margin-bottom: 1.5rem; }}
            .result-box h2 {{ margin: 0; font-size: 1.5rem; }}
            .result-box p {{ margin: 4px 0 0 0; font-size: 1.1rem; opacity: 0.95; font-weight: 700; }}
            .narrative {{ background: #ffffff; border: 1px solid #cbd5e1; border-radius: 10px; padding: 1.25rem; font-size: 0.95rem; line-height: 1.6; margin-bottom: 1.5rem; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 1rem; font-size: 0.88rem; }}
            th {{ background: #f1f5f9; color: #334155; text-align: left; padding: 10px 12px; border-bottom: 2px solid #cbd5e1; }}
            .no-print {{ text-align: center; margin-bottom: 20px; }}
            .btn-print {{ background: #702e5e; color: white; border: none; padding: 12px 24px; border-radius: 10px; font-weight: 800; font-size: 1rem; cursor: pointer; box-shadow: 0 4px 12px rgba(112,46,94,0.3); }}
            @media print {{
                .no-print {{ display: none; }}
                body {{ background: white; padding: 0; }}
                .report-card {{ box-shadow: none; padding: 0; }}
            }}
        </style>
    </head>
    <body>
        <div class="no-print">
            <button onclick="window.print()" class="btn-print">🖨️ Imprimir / Guardar como PDF</button>
        </div>

        <div class="report-card">
            <div class="header">
                <h1>INFORME DE EVALUACIÓN PSICOLÓGICA</h1>
                <p>Espacio Terapéutico — Diagnóstico Psicométrico Estandarizado</p>
            </div>

            <div class="info-grid">
                <div class="info-item"><strong>Consultante:</strong> {patient_name}</div>
                <div class="info-item"><strong>Cédula (CI):</strong> {data.get('patient_cedula') or 'Sin información'}</div>
                <div class="info-item"><strong>Instrumento:</strong> {test_title}</div>
                <div class="info-item"><strong>Fecha de Aplicación:</strong> {str(data.get('fecha_respuesta') or data.get('fecha_asignacion') or '')}</div>
            </div>

            <div class="result-box">
                <h2>{data.get('clasificacion_resultado') or 'Completado'}</h2>
                <p>Puntuación Total Obtenida: {data.get('puntaje_total', 0)} pts</p>
            </div>

            {subscales_html}

            <h3 style="color:#0f172a; margin-top: 1.5rem;">Interpretación Diagnóstica</h3>
            <div class="narrative">
                {data.get('interpretacion_clinica') or 'Sin interpretación clínica generada.'}
            </div>

            <h3 style="color:#0f172a; margin-top: 1.5rem;">Ficha de Respuestas del Paciente</h3>
            <table>
                <thead>
                    <tr>
                        <th>Ítem</th>
                        <th>Pregunta / Enunciado</th>
                        <th>Respuesta Seleccionada</th>
                    </tr>
                </thead>
                <tbody>
                    {items_rows_html}
                </tbody>
            </table>

            <div style="margin-top: 3rem; text-align: right; font-size: 0.85rem; color: #64748b;">
                <p>_________________________________________<br>Firma y Sello del Profesional Tratante</p>
            </div>
        </div>
    </body>
    </html>
    """

    return render_template_string(html_content)


@app.route('/api/tests/asignacion/<int:assignment_id>', methods=['DELETE'])
def api_eliminar_test_asignacion(assignment_id):
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'No autorizado.'}), 401

    db = get_db()
    ensure_tests_tables(db)
    cursor = db.cursor()

    try:
        cursor.execute("DELETE FROM test_asignaciones WHERE id = ? AND user_id = ?", (assignment_id, user_id))
        db.commit()
        return jsonify({'success': 'Asignación eliminada correctamente.'})
    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/api/patient-portal/tests', methods=['GET'])
def api_patient_portal_tests():
    patient_id = session.get('patient_id')
    if not patient_id:
        return jsonify({'error': 'No autorizado.'}), 401

    db = get_db()
    ensure_tests_tables(db)
    cursor = db.cursor()

    cursor.execute("""
        SELECT a.*, td.nombre as test_nombre, td.siglas as test_siglas, td.categoria as test_categoria,
               u.nombres as psic_nombres, u.apellidos as psic_apellidos
        FROM test_asignaciones a
        JOIN tests_definiciones td ON a.test_code = td.code
        JOIN usuarios u ON a.user_id = u.id
        WHERE a.patient_id = ?
        ORDER BY a.fecha_asignacion DESC
    """, (patient_id,))

    rows = cursor.fetchall()
    tests_list = []
    for r in rows:
        d = dict(r)
        d['psicologo_nombre'] = f"Psic. {d['psic_nombres']} {d['psic_apellidos']}".strip()
        d['url_evaluacion'] = f"/evaluacion/{d['uuid_token']}"
        tests_list.append(d)

    return jsonify({'tests': tests_list})


# ==========================================
# ENDPOINTS Y RUTAS DEL MÓDULO CORPORATIVO / CLÍNICAS
# ==========================================

@app.route('/clinica/<slug>', methods=['GET'])
def clinica_publica(slug):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM clinicas WHERE slug = ?", (slug,))
    clinica_row = cursor.fetchone()
    if not clinica_row:
        return "Clínica u Organización no encontrada", 404
    
    clinica = dict(clinica_row)
    
    # Obtener psicólogos integrantes de la clínica
    cursor.execute("""
        SELECT id, nombres, apellidos, nomenclatura, especialidades, foto_titulo, foto_documento,
               descripcion_biografia, modalidades_json, email_publico, whatsapp_publico, slug
        FROM usuarios
        WHERE clinica_id = ? AND role = 'psicologo' AND (activo = 1 OR activo IS NULL)
        ORDER BY tipo_clinica DESC, apellidos ASC
    """, (clinica['id'],))
    
    psicologos_rows = cursor.fetchall()
    psicologos = []
    for p in psicologos_rows:
        p_dict = dict(p)
        psicologos.append(p_dict)
        
    return render_template('clinica_publica.html', clinica=clinica, psicologos=psicologos)


@app.route('/api/clinica/mi-equipo', methods=['GET'])
def api_clinica_mi_equipo():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'No autorizado.'}), 401

    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT id, clinica_id, tipo_clinica FROM usuarios WHERE id = ?", (user_id,))
    u_row = cursor.fetchone()
    if not u_row:
        return jsonify({'error': 'Usuario no encontrado.'}), 404

    c_id = u_row['clinica_id']
    tipo_clinica = u_row['tipo_clinica'] or 0

    if not c_id:
        return jsonify({'pertenece_clinica': False, 'tipo_clinica': 0})

    cursor.execute("SELECT * FROM clinicas WHERE id = ?", (c_id,))
    c_row = cursor.fetchone()
    if not c_row:
        return jsonify({'pertenece_clinica': False, 'tipo_clinica': 0})

    clinica = dict(c_row)
    es_admin = (clinica['admin_id'] == user_id)

    # Miembros de la clínica
    cursor.execute("""
        SELECT id, nombres, apellidos, nomenclatura, username, cedula, telefono, tipo_clinica, especialidades, foto_titulo
        FROM usuarios WHERE clinica_id = ? ORDER BY tipo_clinica DESC, apellidos ASC
    """, (c_id,))
    miembros = [dict(m) for m in cursor.fetchall()]

    # Solicitudes pendientes
    solicitudes = []
    if es_admin:
        cursor.execute("""
            SELECT s.id, s.tipo_solicitud, s.estado, s.created_at,
                   u.id as usuario_id, u.nombres, u.apellidos, u.username, u.cedula, u.especialidades
            FROM solicitudes_clinica s
            JOIN usuarios u ON s.usuario_id = u.id
            WHERE s.clinica_id = ? AND s.estado = 'pendiente' AND s.tipo_solicitud = 'solicitud'
            ORDER BY s.created_at DESC
        """, (c_id,))
        solicitudes = [dict(sol) for sol in cursor.fetchall()]

    return jsonify({
        'pertenece_clinica': True,
        'es_admin': es_admin,
        'tipo_clinica': tipo_clinica,
        'clinica': clinica,
        'miembros': miembros,
        'solicitudes': solicitudes
    })


@app.route('/api/clinica/registrar', methods=['POST'])
def api_clinica_registrar():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'No autorizado.'}), 401

    data = request.json or {}
    nombre = (data.get('nombre') or '').strip()
    descripcion = (data.get('descripcion') or '').strip()

    if not nombre:
        return jsonify({'error': 'El nombre de la clínica es obligatorio.'}), 400

    db = get_db()
    cursor = db.cursor()

    # Generar código y slug único
    import random, string, unicodedata
    code_rnd = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    prefix = re.sub(r'[^A-Z]', '', unicodedata.normalize('NFD', nombre.upper()))[:5] or 'CLIN'
    codigo_clinica = f"{prefix}-{code_rnd}"
    
    slug_base = re.sub(r'[^a-z0-9\-]', '', unicodedata.normalize('NFD', nombre.lower().replace(" ", "-")))
    if not slug_base:
        slug_base = f"clinica-{user_id}"

    cursor.execute("SELECT id FROM clinicas WHERE slug = ?", (slug_base,))
    if cursor.fetchone():
        slug_base = f"{slug_base}-{code_rnd.lower()}"

    cursor.execute("""
        INSERT INTO clinicas (nombre, slug, codigo_clinica, descripcion, admin_id, modo_whatsapp)
        VALUES (?, ?, ?, ?, ?, 'centralizado')
    """, (nombre, slug_base, codigo_clinica, descripcion, user_id))
    clinica_id = cursor.lastrowid

    cursor.execute("UPDATE usuarios SET clinica_id = ?, tipo_clinica = 1 WHERE id = ?", (clinica_id, user_id))
    db.commit()

    return jsonify({
        'success': 'Clínica registrada exitosamente.',
        'codigo_clinica': codigo_clinica,
        'slug': slug_base
    })


@app.route('/api/clinica/vincular-miembro', methods=['POST'])
def api_clinica_vincular_miembro():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'No autorizado.'}), 401

    data = request.json or {}
    identificador = (data.get('identificador') or '').strip() # Cédula o ID de psicólogo

    if not identificador:
        return jsonify({'error': 'Por favor ingresa la Cédula o ID del terapeuta.'}), 400

    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT id, clinica_id FROM usuarios WHERE id = ?", (user_id,))
    u_row = cursor.fetchone()
    if not u_row or not u_row['clinica_id']:
        return jsonify({'error': 'No posees una clínica registrada.'}), 400

    c_id = u_row['clinica_id']
    cursor.execute("SELECT admin_id FROM clinicas WHERE id = ?", (c_id,))
    c_row = cursor.fetchone()
    if not c_row or c_row['admin_id'] != user_id:
        return jsonify({'error': 'Solo el Director de la clínica puede invitar miembros.'}), 403

    # Buscar al usuario por cédula o id
    cursor.execute("SELECT id, nombres, apellidos, clinica_id FROM usuarios WHERE (cedula = ? OR id = ?) AND role = 'psicologo'", (identificador, identificador))
    target_user = cursor.fetchone()
    if not target_user:
        return jsonify({'error': 'No se encontró ningún psicólogo registrado con esa Cédula o ID.'}), 444

    if target_user['clinica_id'] == c_id:
        return jsonify({'error': 'El profesional ya pertenece a esta clínica.'}), 400

    # Crear invitación o vincular
    cursor.execute("""
        INSERT INTO solicitudes_clinica (clinica_id, usuario_id, tipo_solicitud, estado)
        VALUES (?, ?, 'invitacion', 'pendiente')
    """, (c_id, target_user['id']))
    db.commit()

    return jsonify({'success': f"Invitación enviada a {target_user['nombres']} {target_user['apellidos']}."})


@app.route('/api/clinica/solicitar-ingreso', methods=['POST'])
def api_clinica_solicitar_ingreso():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'No autorizado.'}), 401

    data = request.json or {}
    codigo_clinica = (data.get('codigo_clinica') or '').strip().upper()

    if not codigo_clinica:
        return jsonify({'error': 'Ingresa el código de la clínica.'}), 400

    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT id, nombre FROM clinicas WHERE codigo_clinica = ?", (codigo_clinica,))
    c_row = cursor.fetchone()
    if not c_row:
        return jsonify({'error': 'Código de clínica no válido.'}), 404

    c_id = c_row['id']

    # Verificar si ya existe solicitud
    cursor.execute("SELECT id FROM solicitudes_clinica WHERE clinica_id = ? AND usuario_id = ? AND estado = 'pendiente'", (c_id, user_id))
    if cursor.fetchone():
        return jsonify({'error': 'Ya posees una solicitud pendiente para esta clínica.'}), 400

    cursor.execute("""
        INSERT INTO solicitudes_clinica (clinica_id, usuario_id, tipo_solicitud, estado)
        VALUES (?, ?, 'solicitud', 'pendiente')
    """, (c_id, user_id))
    db.commit()

    return jsonify({'success': f"Solicitud de ingreso a '{c_row['nombre']}' enviada con éxito."})


@app.route('/api/clinica/mis-solicitudes', methods=['GET'])
def api_clinica_mis_solicitudes():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'No autorizado.'}), 401

    db = get_db()
    cursor = db.cursor()

    cursor.execute("""
        SELECT s.id, s.tipo_solicitud, s.estado, s.created_at, c.nombre as clinica_nombre, c.codigo_clinica
        FROM solicitudes_clinica s
        JOIN clinicas c ON s.clinica_id = c.id
        WHERE s.usuario_id = ? AND s.estado = 'pendiente' AND s.tipo_solicitud = 'invitacion'
        ORDER BY s.created_at DESC
    """, (user_id,))
    
    solicitudes = [dict(sol) for sol in cursor.fetchall()]
    return jsonify({'invitaciones': solicitudes})


@app.route('/api/clinica/solicitud/responder', methods=['POST'])
def api_clinica_solicitud_responder():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'No autorizado.'}), 401

    data = request.json or {}
    solicitud_id = data.get('solicitud_id')
    accion = data.get('accion') # 'aceptar' o 'rechazar'

    if not solicitud_id or accion not in ('aceptar', 'rechazar'):
        return jsonify({'error': 'Datos incompletos.'}), 400

    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT * FROM solicitudes_clinica WHERE id = ?", (solicitud_id,))
    sol_row = cursor.fetchone()
    if not sol_row:
        return jsonify({'error': 'Solicitud no encontrada.'}), 404

    sol = dict(sol_row)
    c_id = sol['clinica_id']
    u_target_id = sol['usuario_id']

    cursor.execute("SELECT admin_id FROM clinicas WHERE id = ?", (c_id,))
    c_row = cursor.fetchone()
    es_admin = (c_row and c_row['admin_id'] == user_id)

    # Validar permisos
    if sol['tipo_solicitud'] == 'solicitud' and not es_admin:
        return jsonify({'error': 'Solo el administrador puede responder a solicitudes de ingreso.'}), 403
    if sol['tipo_solicitud'] == 'invitacion' and u_target_id != user_id:
        return jsonify({'error': 'No estás autorizado para responder esta invitación.'}), 403

    nuevo_estado = 'aceptado' if accion == 'aceptar' else 'rechazado'
    cursor.execute("UPDATE solicitudes_clinica SET estado = ? WHERE id = ?", (nuevo_estado, solicitud_id))

    if accion == 'aceptar':
        # Asignar usuario a clínica como Terapeuta (tipo_clinica = 2)
        cursor.execute("UPDATE usuarios SET clinica_id = ?, tipo_clinica = 2 WHERE id = ?", (c_id, u_target_id))

    db.commit()
    return jsonify({'success': f"Solicitud {nuevo_estado} correctamente."})


@app.route('/api/clinica/salir', methods=['POST'])
def api_clinica_salir():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'No autorizado.'}), 401

    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT clinica_id, tipo_clinica FROM usuarios WHERE id = ?", (user_id,))
    u_row = cursor.fetchone()
    if not u_row or not u_row['clinica_id']:
        return jsonify({'error': 'No perteneces a ninguna clínica.'}), 400

    if u_row['tipo_clinica'] == 1:
        return jsonify({'error': 'El Director Administrador no puede desvincularse sin transferir el mando.'}), 400

    cursor.execute("UPDATE usuarios SET clinica_id = NULL, tipo_clinica = 0 WHERE id = ?", (user_id,))
    db.commit()

    return jsonify({'success': 'Te has desvinculado de la clínica exitosamente.'})


@app.route('/api/clinica/ajustes', methods=['PUT', 'POST'])
def api_clinica_ajustes():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'No autorizado.'}), 401

    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT clinica_id FROM usuarios WHERE id = ?", (user_id,))
    u_row = cursor.fetchone()
    if not u_row or not u_row['clinica_id']:
        return jsonify({'error': 'No perteneces a ninguna clínica.'}), 400

    c_id = u_row['clinica_id']
    cursor.execute("SELECT admin_id FROM clinicas WHERE id = ?", (c_id,))
    c_row = cursor.fetchone()
    if not c_row or c_row['admin_id'] != user_id:
        return jsonify({'error': 'Solo el Director Administrador puede modificar los ajustes.'}), 403

    data = request.json or {}
    modo_wa = data.get('modo_whatsapp')
    nombre = data.get('nombre')
    descripcion = data.get('descripcion')

    if modo_wa in ('centralizado', 'independiente'):
        cursor.execute("UPDATE clinicas SET modo_whatsapp = ? WHERE id = ?", (modo_wa, c_id))

    if nombre:
        cursor.execute("UPDATE clinicas SET nombre = ? WHERE id = ?", (nombre, c_id))

    if descripcion is not None:
        cursor.execute("UPDATE clinicas SET descripcion = ? WHERE id = ?", (descripcion, c_id))

    db.commit()
    return jsonify({'success': 'Ajustes de la clínica actualizados correctamente.'})







