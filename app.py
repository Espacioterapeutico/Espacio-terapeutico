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

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FIREBASE_SA_FILE = os.path.join(BASE_DIR, 'firebase-service-account.json')

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

# Registrar Blueprint de Pizarra Terapéutica
try:
    from routes_pizarra import pizarra_bp
    app.register_blueprint(pizarra_bp)
except Exception as _e:
    print("Aviso al registrar Blueprint de Pizarra:", _e)

# Registrar Blueprint de Tests Psicológicos
try:
    from routes_tests import tests_bp, ensure_tests_tables
    app.register_blueprint(tests_bp)
except Exception as _e:
    print("Aviso al registrar Blueprint de Tests:", _e)

# Registrar Blueprint de Examen Mental Estructurado (MSE)
try:
    from routes_examen_mental import examen_mental_bp
    app.register_blueprint(examen_mental_bp)
except Exception as _e:
    print("Aviso al registrar Blueprint de Examen Mental:", _e)

# Registrar Blueprint de Herramientas Terapéuticas
try:
    from routes_herramientas import herramientas_bp
    app.register_blueprint(herramientas_bp)
except Exception as _e:
    print("Aviso al registrar Blueprint de Herramientas:", _e)

# Registrar Blueprint de Agenda y Citas
try:
    from routes_agenda import agenda_bp
    app.register_blueprint(agenda_bp)
except Exception as _e:
    print("Aviso al registrar Blueprint de Agenda:", _e)

# Registrar Blueprint de Finanzas y Honorarios
try:
    from routes_finanzas import finanzas_bp, auto_settle_patient_debts
    app.register_blueprint(finanzas_bp)
except Exception as _e:
    print("Aviso al registrar Blueprint de Finanzas:", _e)

# Registrar Blueprint de Evoluciones e Historia Clínica
try:
    from routes_evoluciones import evoluciones_bp
    app.register_blueprint(evoluciones_bp)
except Exception as _e:
    print("Aviso al registrar Blueprint de Evoluciones:", _e)

# Registrar Blueprint de Notificaciones y Comunicaciones Push
try:
    from routes_notificaciones import notificaciones_bp
    app.register_blueprint(notificaciones_bp)
except Exception as _e:
    print("Aviso al registrar Blueprint de Notificaciones:", _e)

# Registrar Blueprint de Gestión de Expedientes de Pacientes
try:
    from routes_pacientes import pacientes_bp
    app.register_blueprint(pacientes_bp)
except Exception as _e:
    print("Aviso al registrar Blueprint de Pacientes:", _e)

# Registrar Blueprint de Autenticación, Seguridad y Administración
try:
    from routes_admin import admin_bp
    app.register_blueprint(admin_bp)
except Exception as _e:
    print("Aviso al registrar Blueprint de Administración:", _e)

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

def get_psychologist_by_id_or_slug(cursor, identifier):
    """
    Busca un psicólogo en la tabla usuarios por ID (int) o por slug / username.
    """
    if not identifier:
        return None
    ident_str = str(identifier).strip()
    if ident_str.isdigit():
        cursor.execute("SELECT * FROM usuarios WHERE id = ?", (int(ident_str),))
        row = cursor.fetchone()
        if row:
            return dict(row)
    clean_slug = ident_str.lower().replace('psic.', '').replace('psic-', '').strip()
    cursor.execute("SELECT * FROM usuarios")
    rows = cursor.fetchall()
    for r in rows:
        r_dict = dict(r)
        uid = str(r_dict.get('id', ''))
        u_slug = str(r_dict.get('slug') or '').lower().replace('psic.', '').replace('psic-', '').strip()
        u_user = str(r_dict.get('username') or '').lower().replace('psic.', '').replace('psic-', '').strip()
        if ident_str == uid or clean_slug == u_slug or clean_slug == u_user:
            return r_dict
    for r in rows:
        r_dict = dict(r)
        u_slug = str(r_dict.get('slug') or '').lower()
        u_user = str(r_dict.get('username') or '').lower()
        if clean_slug and (clean_slug in u_slug or clean_slug in u_user or u_slug in clean_slug):
            return r_dict
    return None

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

def send_vapid_notification(user_id=None, patient_id=None, title="Mi Consultorio", body="Tienes una nueva notificación.", url="/"):
    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        return

    try:
        db = get_db()
        cursor = db.cursor()
        vapid_keys = get_vapid_keys(cursor)
        private_key = vapid_keys.get('vapid_private_key')
        if not private_key:
            return

        if user_id:
            cursor.execute("SELECT id, endpoint, p256dh, auth FROM web_push_subscriptions WHERE user_id = ?", (user_id,))
        elif patient_id:
            cursor.execute("SELECT id, endpoint, p256dh, auth FROM web_push_subscriptions WHERE patient_id = ?", (patient_id,))
        else:
            return

        subs = cursor.fetchall()
        if not subs:
            return

        payload_data = json.dumps({
            "title": title,
            "body": body,
            "url": url,
            "icon": "/static/logo.png",
            "badge": "/static/badge.png"
        })

        vapid_claims = {
            "sub": "mailto:soporte@espacioterapeutico.com"
        }

        for sub in subs:
            subscription_info = {
                "endpoint": sub['endpoint'],
                "keys": {
                    "p256dh": sub['p256dh'],
                    "auth": sub['auth']
                }
            }
            try:
                webpush(
                    subscription_info=subscription_info,
                    data=payload_data,
                    vapid_private_key=private_key,
                    vapid_claims=vapid_claims
                )
            except WebPushException as ex:
                if ex.response is not None and getattr(ex.response, 'status_code', None) in (404, 410):
                    cursor.execute("DELETE FROM web_push_subscriptions WHERE id = ?", (sub['id'],))
                    db.commit()
            except Exception as e:
                print("Error enviando VAPID webpush:", e)
    except Exception as err:
        print("Error general en send_vapid_notification:", err)

def send_webpush_notification(user_id=None, patient_id=None, title="Mi Consultorio", body="Tienes una nueva notificación.", url="/"):
    # 1. FCM (Firebase Cloud Messaging)
    try:
        send_fcm_notification(user_id=user_id, patient_id=patient_id, title=title, body=body, url=url)
    except Exception as fcm_err:
        print("Error al disparar FCM en send_webpush_notification:", fcm_err)

    # 2. VAPID Web Push
    try:
        send_vapid_notification(user_id=user_id, patient_id=patient_id, title=title, body=body, url=url)
    except Exception as vapid_err:
        print("Error al disparar VAPID en send_webpush_notification:", vapid_err)

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

CURRENT_SCHEMA_VER = "15"

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
        if 'bloqueo_herramientas' not in cols_usr:
            cursor.execute("ALTER TABLE usuarios ADD COLUMN bloqueo_herramientas INTEGER DEFAULT 0")
        if 'bloqueo_confirmaciones' not in cols_usr:
            cursor.execute("ALTER TABLE usuarios ADD COLUMN bloqueo_confirmaciones INTEGER DEFAULT 0")
        if 'bloqueo_examen_mental' not in cols_usr:
            cursor.execute("ALTER TABLE usuarios ADD COLUMN bloqueo_examen_mental INTEGER DEFAULT 0")
        if 'bloqueo_tests' not in cols_usr:
            cursor.execute("ALTER TABLE usuarios ADD COLUMN bloqueo_tests INTEGER DEFAULT 0")
        
        cursor.execute("UPDATE usuarios SET bloqueo_tests = 0 WHERE bloqueo_tests IS NULL OR bloqueo_tests = 1")
        cursor.execute("UPDATE usuarios SET bloqueo_examen_mental = 0 WHERE bloqueo_examen_mental IS NULL OR bloqueo_examen_mental = 1")
        cursor.execute("UPDATE usuarios SET bloqueo_herramientas = 0 WHERE bloqueo_herramientas IS NULL OR bloqueo_herramientas = 1")
        cursor.execute("UPDATE usuarios SET bloqueo_confirmaciones = 0 WHERE bloqueo_confirmaciones IS NULL OR bloqueo_confirmaciones = 1")
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
        if 'consultorios_nombres' not in cols_usr:
            cursor.execute("ALTER TABLE usuarios ADD COLUMN consultorios_nombres TEXT DEFAULT ''")
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
        if 'consultorio_nombre' not in cols_fin:
            cursor.execute("ALTER TABLE agenda_finanzas ADD COLUMN consultorio_nombre TEXT")
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
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tokens_herramientas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token TEXT UNIQUE NOT NULL,
            paciente_id INTEGER NOT NULL,
            psicologo_id INTEGER NOT NULL,
            herramienta_tipo TEXT NOT NULL,
            fecha_programada DATE DEFAULT CURRENT_DATE,
            fecha_expiracion DATETIME NOT NULL,
            usado INTEGER DEFAULT 0,
            fecha_completado DATETIME NULL,
            fecha_registro DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (paciente_id) REFERENCES pacientes(id) ON DELETE CASCADE,
            FOREIGN KEY (psicologo_id) REFERENCES usuarios(id) ON DELETE CASCADE
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cola_recordatorios_herramientas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            psicologo_id INTEGER NOT NULL,
            paciente_id INTEGER NOT NULL,
            herramienta_tipo TEXT NOT NULL,
            fecha_programada DATE NOT NULL,
            hora_programada TEXT DEFAULT '20:00',
            estado TEXT DEFAULT 'programado',
            enviado INTEGER DEFAULT 0,
            fecha_envio DATETIME NULL,
            token_id INTEGER NULL,
            pausado INTEGER DEFAULT 0,
            fecha_registro DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(paciente_id, herramienta_tipo, fecha_programada)
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
                    from routes_admin import get_calendar_service
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
            db.commit()
            
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


def ensure_usuarios_columns(db=None):
    if db is None:
        db = get_db()
    cursor = db.cursor()
    columns = [
        ('mostrar_en_directorio', 'INTEGER DEFAULT 1'),
        ('aviso_pago', 'INTEGER DEFAULT 0'),
        ('bloqueo_registro', 'INTEGER DEFAULT 0'),
        ('bloqueo_evoluciones', 'INTEGER DEFAULT 0'),
        ('bloqueo_finanzas', 'INTEGER DEFAULT 0'),
        ('bloqueo_agenda', 'INTEGER DEFAULT 0'),
        ('bloqueo_mensajes', 'INTEGER DEFAULT 0'),
        ('bloqueo_pizarra', 'INTEGER DEFAULT 0'),
        ('bloqueo_herramientas', 'INTEGER DEFAULT 0'),
        ('bloqueo_confirmaciones', 'INTEGER DEFAULT 0'),
        ('cedula', 'TEXT DEFAULT \'\''),
        ('email', 'TEXT DEFAULT \'\''),
        ('nomenclatura', 'TEXT'),
        ('descripcion_biografia', 'TEXT'),
        ('modalidades_json', 'TEXT'),
        ('whatsapp_publico', 'TEXT'),
        ('email_publico', 'TEXT'),
        ('redes_sociales_json', 'TEXT'),
        ('recordatorio_expiracion_enviado', 'TEXT DEFAULT \'\'')
    ]
    for col_name, col_type in columns:
        try:
            cursor.execute(f"ALTER TABLE usuarios ADD COLUMN {col_name} {col_type}")
        except Exception:
            pass

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
    terapéuticas activas en modulos_terapeuticos_paciente y les envía el recordatorio diario por WhatsApp con Link Directo de 1 solo uso.
    """
    if db is None:
        db = get_db()
    cursor = db.cursor()

    TOOL_NAME_MAP = {
        'pantalla': 'Registro de Consumo de Pantallas',
        'cognitivo': 'Registro Cognitivo (TCC)',
        'ingesta': 'Registro de Ingesta Alimentaria',
        'activacion': 'Checklist de Activación Conductual',
        'adherencia': 'Control de Adherencia a Medicamentos',
        'pizarra': 'Diario / Pizarra Terapéutica',
        'sueno': 'Higiene del Sueño',
        'ansiedad': 'Diario de Ansiedad',
        'sobriedad': 'Registro de Consumo y Sobriedad'
    }

    now_utc = datetime.datetime.now(datetime.timezone.utc)
    today_str = now_utc.strftime("%Y-%m-%d")
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        cursor.execute("""
            SELECT DISTINCT p.id, p.nombres, p.apellidos, p.cedula, p.telefono, p.username, p.psicologo_id, p.zona_horaria, p.utc_offset
            FROM pacientes p
            JOIN modulos_terapeuticos_paciente mt ON p.id = mt.paciente_id
            WHERE mt.activo = 1
        """)
        patients_with_tools = cursor.fetchall()
    except Exception:
        return 0

    reminders_sent = 0

    # Verificar estado de WhatsApp globalmente
    wa_connected = False
    try:
        from routes_notificaciones import make_wa_http_request
        r_wa = make_wa_http_request('GET', '/status', timeout=5)
        if r_wa and r_wa.status_code == 200 and r_wa.json().get('status') == 'connected':
            wa_connected = True
    except Exception:
        wa_connected = False

    for p in patients_with_tools:
        p_id = p['id']
        psic_id = p['psicologo_id'] or 1
        offset_min = p['utc_offset'] if (p['utc_offset'] is not None) else 240
        
        # Calcular hora local del paciente a partir de UTC
        patient_local = now_utc - datetime.timedelta(minutes=offset_min)
        current_hour = patient_local.hour

        # Ejecutar únicamente cuando en el reloj local del paciente son las 8:00 PM (hora 20)
        if current_hour == 20:
            cursor.execute("SELECT modulo_clave FROM modulos_terapeuticos_paciente WHERE paciente_id = ? AND activo = 1", (p_id,))
            active_modules = [r['modulo_clave'] for r in cursor.fetchall()]
            
            for mod_clave in active_modules:
                # Comprobar si ya existe registro en la cola para hoy
                cursor.execute("""
                    SELECT id, estado, enviado, pausado FROM cola_recordatorios_herramientas
                    WHERE paciente_id = ? AND herramienta_tipo = ? AND fecha_programada = ?
                """, (p_id, mod_clave, today_str))
                queue_row = cursor.fetchone()
                
                if queue_row:
                    q_dict = dict(queue_row)
                    if q_dict.get('enviado') == 1 or q_dict.get('pausado') == 1:
                        continue # Ya enviado o pausado por el terapeuta
                else:
                    # Crear registro inicial en cola
                    cursor.execute("""
                        INSERT INTO cola_recordatorios_herramientas (
                            psicologo_id, paciente_id, herramienta_tipo, fecha_programada, hora_programada, estado, enviado, pausado
                        ) VALUES (?, ?, ?, ?, '20:00', 'programado', 0, 0)
                    """, (psic_id, p_id, mod_clave, today_str))
                    db.commit()

                # Si WhatsApp no está conectado, actualizar estado a 'esperando_wa' y omitir envío por ahora
                if not wa_connected:
                    cursor.execute("""
                        UPDATE cola_recordatorios_herramientas
                        SET estado = 'esperando_wa'
                        WHERE paciente_id = ? AND herramienta_tipo = ? AND fecha_programada = ?
                    """, (p_id, mod_clave, today_str))
                    db.commit()
                    continue

                # Si WhatsApp está conectado y no se ha enviado hoy, procesar envío
                if p['telefono']:
                    import secrets
                    token = secrets.token_urlsafe(32)
                    expiracion = now_utc + datetime.timedelta(days=3)
                    
                    cursor.execute("""
                        INSERT INTO tokens_herramientas (
                            token, paciente_id, psicologo_id, herramienta_tipo, fecha_programada, fecha_expiracion, usado
                        ) VALUES (?, ?, ?, ?, ?, ?, 0)
                    """, (token, p_id, psic_id, mod_clave, today_str, expiracion.strftime("%Y-%m-%d %H:%M:%S")))
                    token_id = cursor.lastrowid
                    
                    domain_host = os.environ.get('APP_URL', 'https://mi-consultorio.onrender.com').rstrip('/')
                    direct_link = f"{domain_host}/herramienta/directa?token={token}"
                    first_name = (p['nombres'] or '').strip().split()[0] if p['nombres'] else 'Consultante'
                    tool_title = TOOL_NAME_MAP.get(mod_clave, 'Herramienta Terapéutica')
                    
                    msg_wa = (
                        f"Hola *{first_name}* 👋 Espero te encuentres muy bien.\n\n"
                        f"Te recuerdo completar tu *{tool_title}* del día de hoy. "
                        f"Puedes llenarlo en 30 segundos haciendo clic en el siguiente enlace directo (sin iniciar sesión):\n"
                        f"👉 {direct_link}\n\n"
                        f"¡Gracias por tu constancia!"
                    )
                    
                    try:
                        from routes_notificaciones import make_wa_http_request
                        from routes_herramientas import clean_phone_number
                        clean_phone = clean_phone_number(p['telefono'])
                        res_wa = make_wa_http_request('POST', '/send', json_data={'phone': clean_phone, 'text': msg_wa, 'user_id': psic_id}, timeout=15, user_id=psic_id)
                        
                        if res_wa and res_wa.status_code == 200:
                            cursor.execute("""
                                UPDATE cola_recordatorios_herramientas
                                SET estado = 'enviado', enviado = 1, fecha_envio = ?, token_id = ?
                                WHERE paciente_id = ? AND herramienta_tipo = ? AND fecha_programada = ?
                            """, (now_str, token_id, p_id, mod_clave, today_str))
                            db.commit()
                            reminders_sent += 1
                    except Exception as _ex_wa:
                        print(f"Error enviando WhatsApp directo a paciente {p_id}:", _ex_wa)

    return reminders_sent

_last_cleanup_timestamp = 0

@app.before_request
def before_request_cleanup():
    global _last_cleanup_timestamp
    # Evitar ejecutar en llamadas de archivos estáticos
    if request.path.startswith('/static/'):
        return
    import time
    now_ts = time.time()
    if now_ts - _last_cleanup_timestamp < 60:
        return
    _last_cleanup_timestamp = now_ts

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
        
        # 6. Sincronizar mapa ligero de IDs de citas evolucionadas/completadas para conciliar en restauraciones de respaldos
        cursor.execute("SELECT DISTINCT agenda_id FROM sesiones WHERE paciente_id = ? AND agenda_id IS NOT NULL", (patient_id,))
        completed_agenda_ids = [row[0] for row in cursor.fetchall()]

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
@app.route('/psic/<path:slug>')
@app.route('/psicologo/<path:slug>')
@app.route('/agendar/<path:slug>')
@app.route('/<path:slug>/agendar')
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
    elif path.startswith('psicologo/'):
        identifier = path.replace('psicologo/', '').strip()
    elif path.startswith('psic/'):
        identifier = path.replace('psic/', '').strip()
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

