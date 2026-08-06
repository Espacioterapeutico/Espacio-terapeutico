import time
import urllib.request
import ssl

URLS = [
    "https://espacioterapeutico.pythonanywhere.com/api/whatsapp/cron-send-reminders?key=espacioterapeutico_cron_2024",
    "https://www.espacioterapeutico.net/api/whatsapp/cron-send-reminders?key=espacioterapeutico_cron_2024"
]

print("[ALWAYS-ON] Iniciando servicio continuo de monitoreo y envío de WhatsApp (24/7)...", flush=True)

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

while True:
    success = False
    for url in URLS:
        try:
            req = urllib.request.Request(
                url, 
                headers={'User-Agent': 'PythonAnywhere-AlwaysOn-Worker/1.0'}
            )
            with urllib.request.urlopen(req, timeout=30, context=ctx) as response:
                status = response.getcode()
                if status == 200:
                    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Check exitoso en {url}. Status: {status}", flush=True)
                    success = True
                    break
                else:
                    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Status {status} en {url}", flush=True)
        except Exception as err:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Error en {url}: {err}", flush=True)
    
    # Chequear automáticamente cada 3 minutos (180 segundos)
    time.sleep(180)
