import time
import urllib.request
import ssl

URL_CRON = [
    "https://espacioterapeutico.pythonanywhere.com/api/whatsapp/cron-send-reminders?key=espacioterapeutico_cron_2024",
    "https://www.espacioterapeutico.net/api/whatsapp/cron-send-reminders?key=espacioterapeutico_cron_2024"
]
URL_RENDER = "https://espacio-terapeutico-whatsapp.onrender.com/status?user_id=1"

print("[ALWAYS-ON] Iniciando servicio continuo de monitoreo y envío de WhatsApp (24/7)...", flush=True)

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

while True:
    # 1. Ping Render para mantener despierto el contenedor Node.js de WhatsApp 24/7 (previene hibernación de 50+ seg)
    try:
        req_render = urllib.request.Request(
            URL_RENDER,
            headers={'User-Agent': 'PythonAnywhere-AlwaysOn-KeepAlive/1.0'}
        )
        with urllib.request.urlopen(req_render, timeout=25, context=ctx) as resp:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Render Keep-Alive OK. Status: {resp.getcode()}", flush=True)
    except Exception as err_render:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Render Keep-Alive Warning: {err_render}", flush=True)

    # 2. Trigger de recordatorios automáticos en Flask
    for url in URL_CRON:
        try:
            req = urllib.request.Request(
                url, 
                headers={'User-Agent': 'PythonAnywhere-AlwaysOn-Worker/1.0'}
            )
            with urllib.request.urlopen(req, timeout=30, context=ctx) as response:
                status = response.getcode()
                if status == 200:
                    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Cron reminders OK en {url}. Status: {status}", flush=True)
                    break
        except Exception as err:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Error en {url}: {err}", flush=True)
    
    # Chequear automáticamente cada 3 minutos (180 segundos)
    time.sleep(180)
