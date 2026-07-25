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

async function connectToWhatsApp() {
    try {
        const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
        const { version } = await fetchLatestBaileysVersion();

        sock = makeWASocket({
            version,
            auth: state,
            printQRInTerminal: true,
            browser: ['Mi Consultorio', 'Chrome', '1.0.0']
        });

        sock.ev.on('creds.update', saveCreds);

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
                connectedPhone = sock.user ? sock.user.id.split(':')[0] : 'Conectado';
                console.log('✅ WhatsApp Web Conectado Exitosamente:', connectedPhone);
            }

            if (connection === 'close') {
                const statusCode = lastDisconnect?.error?.output?.statusCode;
                const shouldReconnect = statusCode !== DisconnectReason.loggedOut;
                console.log(`⚠️ Conexión cerrada. Razón: ${lastDisconnect?.error}. Reconectando: ${shouldReconnect}`);
                
                connectionStatus = 'disconnected';
                connectedPhone = null;
                currentQR = null;

                if (shouldReconnect) {
                    setTimeout(connectToWhatsApp, 3000);
                } else {
                    console.log('Sesión cerrada por el usuario. Limpiando credenciales...');
                    if (fs.existsSync(AUTH_DIR)) {
                        fs.rmSync(AUTH_DIR, { recursive: true, force: true });
                    }
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

// Iniciar cliente WhatsApp al arrancar
connectToWhatsApp();

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

app.listen(PORT, () => {
    console.log(`🚀 Microservicio WhatsApp Mi Consultorio corriendo en el puerto ${PORT}`);
});
