import time
import requests

URL = "https://espacioterapeutico.pythonanywhere.com/api/whatsapp/cron-send-reminders?key=espacioterapeutico_cron_2024"

print("[ALWAYS-ON] Iniciando servicio continuo de monitoreo y envío de WhatsApp (24/7)...")

while True:
    try:
        response = requests.get(URL, timeout=30)
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Check ejecutado exitosamente. Status Code: {response.status_code}")
    except Exception as err:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Error en chequeo continuo: {err}")
    
    # Chequear cada 15 minutos (900 segundos)
    time.sleep(900)
