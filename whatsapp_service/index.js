const express = require('express');
const cors = require('cors');
const QRCode = require('qrcode');
const axios = require('axios');
const path = require('path');
const fs = require('fs');

const {
    default: makeWASocket,
    useMultiFileAuthState,
    DisconnectReason,
    fetchLatestBaileysVersion
} = require('@whiskeysockets/baileys');

const app = express();
app.use(cors());
app.use(express.json());

const PORT = process.env.PORT || 3001;
const FLASK_WEBHOOK_URL = process.env.FLASK_WEBHOOK_URL || 'http://127.0.0.1:5000/api/whatsapp/webhook';
const AUTH_DIR = path.join(__dirname, 'auth_info_baileys');

let sock = null;
let currentQR = null;
let connectionStatus = 'disconnected'; // 'disconnected' | 'qr_ready' | 'connecting' | 'connected'
let connectedPhone = null;

async function backupAuthSession() {
    try {
        if (!fs.existsSync(AUTH_DIR)) return;
        const files = fs.readdirSync(AUTH_DIR);
        const sessionData = {};
        for (const file of files) {
            if (file.endsWith('.json')) {
                const filePath = path.join(AUTH_DIR, file);
                sessionData[file] = fs.readFileSync(filePath, 'utf8');
            }
        }
        if (Object.keys(sessionData).length > 0) {
            const syncUrl = FLASK_WEBHOOK_URL.replace(/\/webhook$/, '/sync-session');
            await axios.post(syncUrl, sessionData, { timeout: 8000 }).catch(() => {});
        }
    } catch (e) {
        console.error("Error realizando backup de sesión de WA:", e.message);
    }
}

async function restoreAuthSession() {
    try {
        if (!fs.existsSync(AUTH_DIR)) {
            fs.mkdirSync(AUTH_DIR, { recursive: true });
        }
        const existingFiles = fs.readdirSync(AUTH_DIR);
        if (existingFiles.length === 0) {
            console.log("Intentando restaurar credenciales de sesión desde Flask backend...");
            const syncUrl = FLASK_WEBHOOK_URL.replace(/\/webhook$/, '/sync-session');
            let res = null;
            for (let i = 0; i < 3; i++) {
                res = await axios.get(syncUrl, { timeout: 8000 }).catch(() => null);
                if (res && res.data && typeof res.data === 'object' && Object.keys(res.data).length > 0) break;
                await new Promise(r => setTimeout(r, 2000));
            }
            if (res && res.data && typeof res.data === 'object' && Object.keys(res.data).length > 0) {
                for (const [fileName, fileContent] of Object.entries(res.data)) {
                    if (fileName.endsWith('.json') && typeof fileContent === 'string') {
                        fs.writeFileSync(path.join(AUTH_DIR, fileName), fileContent, 'utf8');
                    }
                }
                console.log("✅ Sesión de WhatsApp restaurada con éxito desde backend.");
            }
        }
    } catch (e) {
        console.error("Error restaurando credenciales de sesión de WA:", e.message);
    }
}

async function connectToWhatsApp(forceNew = false) {
    try {
        if (sock) {
            try { sock.ev.removeAllListeners(); } catch(e) {}
            try { sock.ws.close(); } catch(e) {}
            try { sock.end(); } catch(e) {}
            sock = null;
        }

        if (!forceNew) {
            await restoreAuthSession();
        }
        const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
        const { version } = await fetchLatestBaileysVersion();

        sock = makeWASocket({
            version,
            auth: state,
            printQRInTerminal: true,
            browser: ['Mi Consultorio', 'Chrome', '1.0.0']
        });

        sock.ev.on('creds.update', async () => {
            await saveCreds();
            backupAuthSession();
        });

        sock.ev.on('connection.update', async (update) => {
            const { connection, lastDisconnect, qr } = update;

            if (qr) {
                currentQR = await QRCode.toDataURL(qr);
                connectionStatus = 'qr_ready';
                console.log('Nuevo Código QR de WhatsApp generado.');
            }

            if (connection === 'connecting') {
                connectionStatus = 'connecting';
            }

            if (connection === 'open') {
                connectionStatus = 'connected';
                currentQR = null;
                const rawId = sock.user ? (sock.user.id || sock.user.jid || '') : '';
                connectedPhone = rawId ? rawId.split(':')[0].replace(/@.*/, '') : 'Conectado';
                console.log('✅ WhatsApp Web Conectado Exitosamente:', connectedPhone);
                backupAuthSession();
            }

            if (connection === 'close') {
                const statusCode = lastDisconnect?.error?.output?.statusCode;
                // Solo borrar sesión si el usuario cerró sesión explícitamente desde WhatsApp en su teléfono (401 / LoggedOut)
                const isExplicitLogout = statusCode === DisconnectReason.loggedOut || statusCode === 401;
                console.log(`⚠️ Conexión cerrada. Código: ${statusCode}. Razón: ${lastDisconnect?.error}. Reconectando: ${!isExplicitLogout}`);
                
                if (isExplicitLogout) {
                    connectionStatus = 'disconnected';
                    connectedPhone = null;
                    currentQR = null;
                    console.log('Sesión cerrada explícitamente desde el teléfono. Limpiando credenciales...');
                    if (fs.existsSync(AUTH_DIR)) {
                        try { fs.rmSync(AUTH_DIR, { recursive: true, force: true }); } catch(e) {}
                    }
                } else {
                    // Tras escanear el QR, Baileys cierra el socket para reiniciar con llaves cifradas (código 515 restartRequired).
                    // Mantenemos el estado en 'connecting' en lugar de 'disconnected' para que la UI no parpadee ni se reinicie.
                    connectionStatus = 'connecting';
                    currentQR = null;
                    setTimeout(() => connectToWhatsApp(false), 1000);
                }
            }
        });

        // Escuchar mensajes entrantes de pacientes
        sock.ev.on('messages.upsert', async (m) => {
            if (m.type !== 'notify') return;

            for (const msg of m.messages) {
                if (!msg.message || msg.key.fromMe) continue;

                const remoteJid = msg.key.remoteJid;
                if (!remoteJid || !remoteJid.endsWith('@s.whatsapp.net')) continue;

                const phone = remoteJid.replace('@s.whatsapp.net', '');
                const text = msg.message.conversation ||
                             msg.message.extendedTextMessage?.text || '';

                if (!text.trim()) continue;

                console.log(`📩 Mensaje recibido de ${phone}: "${text}"`);

                // Enviar Webhook a Flask backend
                try {
                    await axios.post(FLASK_WEBHOOK_URL, {
                        phone: phone,
                        text: text,
                        pushName: msg.pushName || ''
                    }, { timeout: 5000 });
                } catch (err) {
                    console.error('Error al enviar Webhook a Flask:', err.message);
                }
            }
        });

    } catch (err) {
        console.error('Error iniciando cliente Baileys WhatsApp:', err);
        connectionStatus = 'disconnected';
    }
}

// API Endpoints
app.get('/status', (req, res) => {
    res.json({
        status: connectionStatus,
        phone: connectedPhone,
        has_qr: !!currentQR
    });
});

app.get('/qr', (req, res) => {
    res.json({
        status: connectionStatus,
        qr: currentQR,
        phone: connectedPhone
    });
});

app.post('/force-qr', async (req, res) => {
    try {
        console.log("⚠️ Petición manual para forzar generación de nuevo Código QR...");
        
        // 1. Cerrar completamente el socket de Baileys para liberar los archivos
        if (sock) {
            try { sock.ev.removeAllListeners(); } catch(e) {}
            try { sock.ws.close(); } catch(e) {}
            try { await sock.logout(); } catch(e) {}
            try { sock.end(); } catch(e) {}
            sock = null;
        }

        // 2. Esperar a que los file handles se liberen
        await new Promise(r => setTimeout(r, 1000));

        // 3. Borrar carpeta de credenciales (con retry si está bloqueada)
        for (let i = 0; i < 3; i++) {
            try {
                if (fs.existsSync(AUTH_DIR)) {
                    // Intentar borrar archivos individuales primero
                    const files = fs.readdirSync(AUTH_DIR);
                    for (const f of files) {
                        try { fs.unlinkSync(path.join(AUTH_DIR, f)); } catch(e) {}
                    }
                    // Luego intentar borrar la carpeta
                    try { fs.rmSync(AUTH_DIR, { recursive: true, force: true }); } catch(e) {}
                }
                break;
            } catch(e) {
                console.log(`Intento ${i+1}/3 de limpiar auth_info falló: ${e.message}`);
                await new Promise(r => setTimeout(r, 500));
            }
        }

        // 4. Notificar al backend para borrar la copia guardada en SQLite
        try {
            const syncUrl = FLASK_WEBHOOK_URL.replace(/\/webhook$/, '/sync-session');
            await axios.delete(syncUrl, { timeout: 4000 }).catch(() => {});
        } catch(e) {}

        connectionStatus = 'disconnected';
        connectedPhone = null;
        currentQR = null;

        // 5. Reconectar Baileys (sin restaurar sesión vieja)
        connectToWhatsApp(true);

        res.json({ success: true, message: 'Reiniciando motor de WhatsApp para generar nuevo QR...' });
    } catch(err) {
        console.error("Error en /force-qr:", err);
        res.status(500).json({ error: err.message });
    }
});

app.post('/send', async (req, res) => {
    const { phone, text } = req.body || {};
    if (!phone || !text) {
        return res.status(400).json({ error: 'Faltan parámetros phone o text' });
    }

    if (connectionStatus !== 'connected' || !sock) {
        return res.status(400).json({ error: 'WhatsApp Web no está conectado' });
    }

    try {
        let cleanPhone = phone.toString().replace(/\D/g, '');
        if (cleanPhone.startsWith('04') && cleanPhone.length === 11) {
            cleanPhone = '58' + cleanPhone.substring(1);
        } else if (cleanPhone.startsWith('4') && cleanPhone.length === 10) {
            cleanPhone = '58' + cleanPhone;
        }

        if (cleanPhone.length < 10) {
            return res.status(400).json({ error: `El número '${phone}' es inválido (requiere código de país o min. 10 dígitos)` });
        }

        if (!cleanPhone.endsWith('@s.whatsapp.net')) {
            cleanPhone = `${cleanPhone}@s.whatsapp.net`;
        }

        await sock.sendMessage(cleanPhone, { text: text });
        res.json({ success: true, message: `Mensaje enviado a ${phone}` });
    } catch (err) {
        console.error('Error enviando mensaje por WhatsApp:', err);
        res.status(500).json({ error: `Error al enviar mensaje: ${err.message}` });
    }
});

app.post('/logout', async (req, res) => {
    try {
        if (sock) {
            await sock.logout();
        }
        if (fs.existsSync(AUTH_DIR)) {
            fs.rmSync(AUTH_DIR, { recursive: true, force: true });
        }
        connectionStatus = 'disconnected';
        connectedPhone = null;
        currentQR = null;
        setTimeout(connectToWhatsApp, 2000);
        res.json({ success: true, message: 'Sesión de WhatsApp cerrada exitosamente.' });
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

// Manejadores de fallos no capturados para evitar que el contenedor de Railway colapse (Deploy Crashed)
process.on('uncaughtException', (err) => {
    console.error('❌ Error no capturado en proceso WhatsApp:', err);
});

process.on('unhandledRejection', (reason, promise) => {
    console.error('❌ Promesa rechazada no manejada:', reason);
});

app.listen(PORT, () => {
    console.log(`🚀 Microservicio WhatsApp Mi Consultorio corriendo en el puerto ${PORT}`);
    connectToWhatsApp();
});
