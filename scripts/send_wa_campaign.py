import sqlite3
import random
import string
import time
import requests
from werkzeug.security import generate_password_hash

DB_PATH = 'clinica.db'
WA_URL = 'https://espacio-terapeutico-whatsapp.onrender.com/send-message'

def get_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db

def generate_random_password(length=8):
    characters = string.ascii_letters + string.digits
    return ''.join(random.choice(characters) for i in range(length))

def send_wa(number, message):
    try:
        resp = requests.post(
            WA_URL, 
            json={'number': number, 'message': message}, 
            headers={'X-User-ID': '1'}, 
            params={'user_id': '1'},
            timeout=10
        )
        return resp.status_code == 200
    except Exception as e:
        print(f"Error enviando WA a {number}: {e}")
        return False

def main():
    db = get_db()
    cursor = db.cursor()
    
    # Obtener pacientes con teléfono
    cursor.execute("SELECT id, nombres, apellidos, telefono, cedula, email, username, password_hash, psicologo_id FROM pacientes WHERE telefono IS NOT NULL AND telefono != ''")
    pacientes = cursor.fetchall()
    
    print(f"Encontrados {len(pacientes)} pacientes con teléfono.")
    
    for p in pacientes:
        p_dict = dict(p)
        paciente_id = p_dict['id']
        nombres = p_dict['nombres'] or ''
        nombre = nombres.split()[0] if nombres else 'Consultante'
        telefono = p_dict['telefono']
        username = p_dict['username'] or p_dict['cedula'] or p_dict['email']
        is_registered = bool(p_dict['password_hash'])
        
        # Limpiar teléfono
        clean_phone = ''.join(c for c in telefono if c.isdigit())
        if not clean_phone:
            continue
            
        if is_registered:
            msg = f"""¡Hola {nombre}! 🌟 Pasaba por aquí para recordarte que tienes a tu disposición el *Portal del Consultante* de Espacio Terapéutico. 

Desde tu portal privado puedes:
🗓️ Agendar o reprogramar tus próximas sesiones.
📝 Responder tus registros clínicos y herramientas terapéuticas (como las de sueño, ansiedad o consumo).
💳 Ver tus estados de cuenta y pagos.

Puedes entrar en cualquier momento desde tu celular o computadora aquí: https://www.espacioterapeutico.net/login

¡Nos vemos en tu próxima sesión!"""
            print(f"Enviando RECORDATORIO a {nombre} ({clean_phone})...")
            send_wa(clean_phone, msg)
            
        else:
            if not username:
                print(f"Saltando a {nombre} porque no tiene cédula ni correo para usar como usuario.")
                continue
                
            temp_pass = generate_random_password()
            pass_hash = generate_password_hash(temp_pass)
            
            # Actualizar en BD
            cursor.execute("UPDATE pacientes SET username = ?, password_hash = ? WHERE id = ?", (username, pass_hash, paciente_id))
            db.commit()
            
            msg = f"""¡Hola {nombre}! 🌟 Quería invitarte oficialmente a usar el nuevo *Portal del Consultante* de Espacio Terapéutico.

Es una app privada diseñada para ti, donde podrás:
🗓️ Agendar tus próximas sesiones.
📝 Llenar tus registros clínicos y tareas desde el celular.
💳 Llevar el control de tus sesiones y pagos.

Ya te creé una cuenta. Para entrar por primera vez, ingresa a https://www.espacioterapeutico.net/login 
*Usuario:* {username}
*Contraseña temporal:* {temp_pass}
_(El sistema te pedirá cambiar la contraseña apenas entres por seguridad)._

¡Espero que le saques mucho provecho!"""
            print(f"Enviando INVITACIÓN a {nombre} ({clean_phone}) con usuario {username}...")
            send_wa(clean_phone, msg)
            
        # Esperar un poco para no saturar la API
        time.sleep(2)
        
    print("Campaña de WhatsApp finalizada exitosamente.")

if __name__ == '__main__':
    main()
