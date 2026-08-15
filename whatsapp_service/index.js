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
const FLASK_BASE_URL = FLASK_WEBHOOK_URL.replace('/api/whatsapp/webhook', '');
const AUTH_BASE_DIR = path.join(__dirname, 'auth_info_baileys');

// Mapa de sesiones activas por user_id: key = string(user_id) -> { userId, sock, connectionStatus, currentQR, connectedPhone }
const sessions = new Map();

function getSessionObj(userId) {
    const key = String(userId || 1);
    if (!sessions.has(key)) {
        sessions.set(key, {
            userId: key,
            sock: null,
            connectionStatus: 'disconnected', // 'disconnected' | 'qr_ready' | 'connecting' | 'connected'
            currentQR: null,
            connectedPhone: null
        });
    }
    return sessions.get(key);
}

function getUserAuthDir(userId) {
    const key = String(userId || 1);
    const userDir = path.join(AUTH_BASE_DIR, `user_${key}`);
    if (!fs.existsSync(userDir)) {
        fs.mkdirSync(userDir, { recursive: true });
    }
    return userDir;
}

// Persistencia remota en BD Flask para sobrevivir a reinicios/despliegues de servidores efímeros
async function syncSessionToFlask(userId, userAuthDir) {
    try {
        if (!fs.existsSync(userAuthDir)) return;
        const fileNames = fs.readdirSync(userAuthDir);
        const filesMap = {};
        for (const f of fileNames) {
            const fullPath = path.join(userAuthDir, f);
            if (fs.statSync(fullPath).isFile()) {
                filesMap[f] = fs.readFileSync(fullPath, 'utf8');
            }
        }
        if (Object.keys(filesMap).length > 0) {
            const syncUrl = `${FLASK_BASE_URL}/api/whatsapp/sync-session`;
            await axios.post(syncUrl, { user_id: userId, files: filesMap }, { timeout: 8000 }).catch(() => {});
        }
    } catch(e) {
        // Silencioso
    }
}

async function restoreSessionFromFlask(userId, userAuthDir) {
    try {
        if (!fs.existsSync(userAuthDir)) {
            fs.mkdirSync(userAuthDir, { recursive: true });
        }
        const existing = fs.readdirSync(userAuthDir);
        if (existing.length > 0) return; // Ya existen credenciales locales

        const syncUrl = `${FLASK_BASE_URL}/api/whatsapp/sync-session?user_id=${userId}`;
        const res = await axios.get(syncUrl, { timeout: 8000 }).catch(() => null);
        if (res && res.data && res.data.files && Object.keys(res.data.files).length > 0) {
            for (const [filename, content] of Object.entries(res.data.files)) {
                fs.writeFileSync(path.join(userAuthDir, filename), content, 'utf8');
            }
            console.log(`[User ${userId}] 🔄 Credenciales de WhatsApp restauradas exitosamente desde la BD.`);
        }
    } catch(e) {
        console.error(`[User ${userId}] Error al intentar restaurar credenciales de BD:`, e.message);
    }
}

async function clearSessionFromFlask(userId) {
    try {
        const syncUrl = `${FLASK_BASE_URL}/api/whatsapp/sync-session?user_id=${userId}`;
        await axios.delete(syncUrl, { timeout: 5000 }).catch(() => {});
    } catch(e) {}
}

async function connectToWhatsAppUser(userId, forceNew = false) {
    const key = String(userId || 1);
    const session = getSessionObj(key);
    const userAuthDir = getUserAuthDir(key);

    try {
        if (session.sock) {
            try { session.sock.ev.removeAllListeners(); } catch(e) {}
            try { session.sock.ws.close(); } catch(e) {}
            try { session.sock.end(); } catch(e) {}
            session.sock = null;
        }

        if (forceNew) {
            try {
                if (fs.existsSync(userAuthDir)) {
                    fs.rmSync(userAuthDir, { recursive: true, force: true });
                    fs.mkdirSync(userAuthDir, { recursive: true });
                }
                await clearSessionFromFlask(key);
            } catch(e) {
                console.error(`[User ${key}] Error al limpiar authDir:`, e.message);
            }
        } else {
            // Intentar restaurar sesión guardada en BD por si el servidor/plataforma se reinició
            await restoreSessionFromFlask(key, userAuthDir);
        }

        const { state, saveCreds } = await useMultiFileAuthState(userAuthDir);
        const { version } = await fetchLatestBaileysVersion();

        session.sock = makeWASocket({
            version,
            auth: state,
            printQRInTerminal: false,
            browser: [`Espacio Terapeutico (User ${key})`, 'Chrome', '1.0.0'],
            keepAliveIntervalMs: 30000,     // Enviar pings WebSocket cada 30 segundos para prevenir desconexiones
            connectTimeoutMs: 60000,        // Timeout de conexión 60s
            defaultQueryTimeoutMs: 60000,   // Timeout de peticiones 60s
            retryRequestDelayMs: 2500,      // Reintento de solicitudes tras fallo
            maxMsgRetryCount: 5
        });

        session.sock.ev.on('creds.update', async () => {
            await saveCreds();
            syncSessionToFlask(key, userAuthDir);
        });

        session.sock.ev.on('connection.update', async (update) => {
            const { connection, lastDisconnect, qr } = update;

            if (qr) {
                session.currentQR = await QRCode.toDataURL(qr);
                session.connectionStatus = 'qr_ready';
                console.log(`[User ${key}] Nuevo Código QR de WhatsApp generado.`);
            }

            if (connection === 'connecting') {
                session.connectionStatus = 'connecting';
            }

            if (connection === 'open') {
                session.connectionStatus = 'connected';
                session.currentQR = null;
                const rawId = session.sock.user ? (session.sock.user.id || session.sock.user.jid || '') : '';
                session.connectedPhone = rawId ? rawId.split(':')[0].replace(/@.*/, '') : 'Conectado';
                console.log(`[User ${key}] ✅ WhatsApp Web Conectado Exitosamente: ${session.connectedPhone}`);
                // Sincronizar credenciales recién logueadas a la BD
                syncSessionToFlask(key, userAuthDir);
            }

            if (connection === 'close') {
                const statusCode = lastDisconnect?.error?.output?.statusCode;
                // Solo desconectar definitivamente si es un logout explícito (DisconnectReason.loggedOut = 401)
                const isExplicitLogout = statusCode === DisconnectReason.loggedOut;
                console.log(`[User ${key}] ⚠️ Conexión cerrada. Código: ${statusCode}. Reconectando: ${!isExplicitLogout}`);
                
                if (isExplicitLogout) {
                    session.connectionStatus = 'disconnected';
                    session.connectedPhone = null;
                    session.currentQR = null;
                    if (fs.existsSync(userAuthDir)) {
                        try { fs.rmSync(userAuthDir, { recursive: true, force: true }); } catch(e) {}
                    }
                    await clearSessionFromFlask(key);
                } else {
                    session.connectionStatus = 'connecting';
                    session.currentQR = null;
                    // Intentar reconectar automáticamente tras 2 segundos
                    setTimeout(() => connectToWhatsAppUser(key, false), 2000);
                }
            }
        });

        // Escuchar mensajes entrantes de pacientes para este psicólogo específico
        session.sock.ev.on('messages.upsert', async (m) => {
            if (m.type !== 'notify') return;

            for (const msg of m.messages) {
                if (!msg.message || msg.key.fromMe) continue;

                const remoteJid = msg.key.remoteJid;
                if (!remoteJid || (!remoteJid.endsWith('@s.whatsapp.net') && !remoteJid.includes('@s.whatsapp.net'))) continue;

                const phone = remoteJid.split('@')[0].split(':')[0].replace(/[^0-9]/g, '');

                // Desempaquetar cualquier tipo de mensaje (efímero, viewOnce, respuesta a botones, texto normal)
                let innerMsg = msg.message.ephemeralMessage?.message ||
                               msg.message.viewOnceMessage?.message ||
                               msg.message.viewOnceMessageV2?.message ||
                               msg.message;

                const text = innerMsg.conversation ||
                             innerMsg.extendedTextMessage?.text ||
                             innerMsg.buttonsResponseMessage?.selectedButtonId ||
                             innerMsg.buttonsResponseMessage?.selectedDisplayText ||
                             innerMsg.listResponseMessage?.singleSelectReply?.selectedRowId ||
                             innerMsg.templateButtonReplyMessage?.selectedId ||
                             innerMsg.templateButtonReplyMessage?.selectedDisplayText ||
                             innerMsg.interactiveResponseMessage?.body?.text ||
                             '';

                if (!text || !text.trim()) continue;

                console.log(`📩 [User ${key}] Mensaje recibido de ${phone}: "${text}"`);

                const payload = {
                    user_id: parseInt(key, 10),
                    phone: phone,
                    text: text.trim(),
                    pushName: msg.pushName || ''
                };

                try {
                    await axios.post(FLASK_WEBHOOK_URL, payload, { timeout: 6000 });
                } catch (err) {
                    console.error(`[User ${key}] Error enviando Webhook a ${FLASK_WEBHOOK_URL}:`, err.message);
                    if (FLASK_WEBHOOK_URL.includes('127.0.0.1') || FLASK_WEBHOOK_URL.includes('localhost')) {
                        try {
                            const prodUrl = 'https://espacioterapeutico.net/api/whatsapp/webhook';
                            await axios.post(prodUrl, payload, { timeout: 6000 });
                            console.log(`[User ${key}] Webhook enviado exitosamente a producción (${prodUrl})`);
                        } catch (e2) {
                            console.error(`[User ${key}] Error enviando fallback webhook a producción:`, e2.message);
                        }
                    }
                }
            }
        });

    } catch (err) {
        console.error(`[User ${key}] Error iniciando cliente Baileys:`, err);
        session.connectionStatus = 'disconnected';
    }
}

// API Endpoints Multitenant (Aceptan user_id por query, headers o body)
app.get('/status', (req, res) => {
    const userId = req.query.user_id || req.headers['x-user-id'] || '1';
    const session = getSessionObj(userId);
    res.json({
        user_id: userId,
        status: session.connectionStatus,
        phone: session.connectedPhone,
        has_qr: !!session.currentQR
    });
});

app.get('/qr', (req, res) => {
    const userId = req.query.user_id || req.headers['x-user-id'] || '1';
    const session = getSessionObj(userId);
    
    // Si la sesión no ha arrancado, arrancarla
    if (session.connectionStatus === 'disconnected' && !session.sock) {
        connectToWhatsAppUser(userId, false);
    }

    res.json({
        user_id: userId,
        status: session.connectionStatus,
        qr: session.currentQR,
        phone: session.connectedPhone
    });
});

app.post('/force-qr', async (req, res) => {
    const userId = req.body?.user_id || req.query.user_id || req.headers['x-user-id'] || '1';
    console.log(`⚠️ [User ${userId}] Petición para forzar generación de nuevo Código QR...`);
    try {
        await connectToWhatsAppUser(userId, true);
        res.json({ success: true, message: `Generando nuevo QR para el usuario ${userId}...` });
    } catch(err) {
        console.error(`Error en /force-qr para usuario ${userId}:`, err);
        res.status(500).json({ error: err.message });
    }
});

app.post('/send', async (req, res) => {
    const { phone, text, user_id } = req.body || {};
    const userId = user_id || req.query.user_id || req.headers['x-user-id'] || '1';
    
    if (!phone || !text) {
        return res.status(400).json({ error: 'Faltan parámetros phone o text' });
    }

    const session = getSessionObj(userId);
    if (session.connectionStatus !== 'connected' || !session.sock) {
        return res.status(400).json({ error: `El WhatsApp del psicólogo (ID ${userId}) no está conectado` });
    }

    try {
        let cleanPhone = phone.toString().replace(/\D/g, '');
        if (cleanPhone.startsWith('04') && cleanPhone.length === 11) {
            cleanPhone = '58' + cleanPhone.substring(1);
        } else if (cleanPhone.startsWith('4') && cleanPhone.length === 10) {
            cleanPhone = '58' + cleanPhone;
        }

        if (cleanPhone.length < 10) {
            return res.status(400).json({ error: `El número '${phone}' es inválido` });
        }

        let targetJid = cleanPhone.endsWith('@s.whatsapp.net') ? cleanPhone : `${cleanPhone}@s.whatsapp.net`;
        const rawNum = cleanPhone.replace('@s.whatsapp.net', '');
        
        try {
            const onWa = await session.sock.onWhatsApp(rawNum);
            if (Array.isArray(onWa) && onWa.length > 0 && onWa[0].exists) {
                targetJid = onWa[0].jid;
            } else {
                return res.status(400).json({ error: `El número ${phone} (+${rawNum}) no está registrado en WhatsApp.` });
            }
        } catch (eWa) {
            console.warn(`[User ${userId}] ADVERTENCIA en onWhatsApp check:`, eWa.message);
        }

        await session.sock.sendMessage(targetJid, { text: text });
        res.json({ success: true, message: `Mensaje enviado a ${phone} (${targetJid}) desde cuenta de usuario ${userId}` });
    } catch (err) {
        console.error(`[User ${userId}] Error enviando mensaje por WhatsApp:`, err);
        res.status(500).json({ error: `Error al enviar mensaje: ${err.message}` });
    }
});

app.post('/logout', async (req, res) => {
    const userId = req.body?.user_id || req.query.user_id || req.headers['x-user-id'] || '1';
    const session = getSessionObj(userId);
    try {
        if (session.sock) {
            try { await session.sock.logout(); } catch(e) {}
        }
        const userAuthDir = getUserAuthDir(userId);
        if (fs.existsSync(userAuthDir)) {
            try { fs.rmSync(userAuthDir, { recursive: true, force: true }); } catch(e) {}
        }
        await clearSessionFromFlask(userId);
        session.connectionStatus = 'disconnected';
        session.connectedPhone = null;
        session.currentQR = null;
        session.sock = null;
        res.json({ success: true, message: `Sesión de WhatsApp del usuario ${userId} cerrada exitosamente.` });
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

// Manejadores globales de errores
process.on('uncaughtException', (err) => {
    console.error('❌ Error no capturado en proceso WhatsApp:', err);
});

process.on('unhandledRejection', (reason, promise) => {
    console.error('❌ Promesa rechazada no manejada:', reason);
});

app.listen(PORT, () => {
    console.log(`🚀 Microservicio WhatsApp Multi-Tenant corriendo en puerto ${PORT}`);
    // Conectar sesiones existentes en disco
    try {
        if (fs.existsSync(AUTH_BASE_DIR)) {
            const dirs = fs.readdirSync(AUTH_BASE_DIR);
            for (const d of dirs) {
                if (d.startsWith('user_')) {
                    const uId = d.replace('user_', '');
                    if (uId) connectToWhatsAppUser(uId, false);
                }
            }
        }
    } catch(e) {}
    // Garantizar que la sesión 1 siempre inicie
    connectToWhatsAppUser('1', false);
});
