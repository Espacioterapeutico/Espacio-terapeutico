import time
import urllib.request
import ssl

URL = "https://espacioterapeutico.pythonanywhere.com/api/whatsapp/cron-send-reminders?key=espacioterapeutico_cron_2024"

print("[ALWAYS-ON] Iniciando servicio continuo de monitoreo y envío de WhatsApp (24/7)...", flush=True)

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

while True:
    try:
        req = urllib.request.Request(
            URL, 
            headers={'User-Agent': 'PythonAnywhere-AlwaysOn-Worker/1.0'}
        )
        with urllib.request.urlopen(req, timeout=30, context=ctx) as response:
            status = response.getcode()
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Check ejecutado exitosamente. Status Code: {status}", flush=True)
    except Exception as err:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Error en chequeo continuo: {err}", flush=True)
    
    # Chequear cada 15 minutos (900 segundos)
    time.sleep(900)
