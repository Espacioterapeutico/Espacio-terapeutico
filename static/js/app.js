
// ==========================================
// MÓDULO DE DERECCIÓN Y CONVERSIÓN DE ZONA HORARIA
// ==========================================
function getPatientUserTimeZone() {
    try {
        const detected = Intl.DateTimeFormat().resolvedOptions().timeZone;
        return detected || 'Europe/Madrid';
    } catch(e) {
        return 'Europe/Madrid';
    }
}

function initFastTimeZoneSelector() {
    const sel = document.getElementById('fast-tz-select');
    if (!sel) return;
    const userTz = getPatientUserTimeZone();
    let matchFound = false;
    for (let i = 0; i < sel.options.length; i++) {
        if (sel.options[i].value === userTz) {
            sel.selectedIndex = i;
            matchFound = true;
            break;
        }
    }
    if (!matchFound) {
        const opt = document.createElement('option');
        opt.value = userTz;
        opt.textContent = `Detectada (${userTz})`;
        opt.selected = true;
        sel.appendChild(opt);
    }
}

function onFastTimeZoneChange() {
    const dateInput = document.getElementById('fast-req-fecha');
    if (dateInput && dateInput.value) {
        fetchFastAvailableHours(dateInput.value);
    }
}

function convertTimeFromVETToZone(fechaStr, horaStr, targetZone) {
    if (!fechaStr || !horaStr) return { dateStr: fechaStr, timeStr: horaStr, displayTime: horaStr, dayOffsetStr: '' };
    try {
        const cleanDate = fechaStr.replace(/\//g, '-');
        const dateParts = cleanDate.split('-');
        const y = dateParts[0].padStart(4, '20');
        const m = dateParts[1].padStart(2, '0');
        const d = dateParts[2].padStart(2, '0');
        
        const cleanTime = horaStr.trim();
        const timeParts = cleanTime.split(':');
        const hh = timeParts[0].padStart(2, '0');
        const mm = (timeParts[1] || '00').padStart(2, '0');
        
        const isoVET = `${y}-${m}-${d}T${hh}:${mm}:00-04:00`;
        const dateObj = new Date(isoVET);
        
        if (isNaN(dateObj.getTime())) {
            return { dateStr: fechaStr, timeStr: horaStr, displayTime: horaStr, dayOffsetStr: '' };
        }
        
        const localTimeStr = dateObj.toLocaleTimeString('es-ES', {
            timeZone: targetZone,
            hour: '2-digit',
            minute: '2-digit',
            hour12: false
        });
        
        const localDateStr = dateObj.toLocaleDateString('sv-SE', {
            timeZone: targetZone
        }); // YYYY-MM-DD
        
        let dayOffsetStr = '';
        if (localDateStr > `${y}-${m}-${d}`) {
            dayOffsetStr = ' (+1 día)';
        } else if (localDateStr < `${y}-${m}-${d}`) {
            dayOffsetStr = ' (-1 día)';
        }
        
        return {
            dateStr: localDateStr,
            timeStr: localTimeStr,
            displayTime: `${localTimeStr}${dayOffsetStr}`,
            dayOffsetStr: dayOffsetStr
        };
    } catch(err) {
        console.error("Error convirtiendo zona horaria:", err);
        return { dateStr: fechaStr, timeStr: horaStr, displayTime: horaStr, dayOffsetStr: '' };
    }
}

function generateGoogleCalendarUrl(title, description, fechaStr, horaStr, durationMinutes = 60) {
    try {
        const cleanDate = fechaStr.replace(/\//g, '-');
        const dateParts = cleanDate.split('-');
        const y = dateParts[0].padStart(4, '20');
        const m = dateParts[1].padStart(2, '0');
        const d = dateParts[2].padStart(2, '0');
        
        const cleanTime = horaStr.trim();
        const timeParts = cleanTime.split(':');
        const hh = timeParts[0].padStart(2, '0');
        const mm = (timeParts[1] || '00').padStart(2, '0');
        
        const startDateObj = new Date(`${y}-${m}-${d}T${hh}:${mm}:00-04:00`);
        const endDateObj = new Date(startDateObj.getTime() + (durationMinutes * 60 * 1000));
        
        const startY = startDateObj.getUTCFullYear();
        const startM = String(startDateObj.getUTCMonth() + 1).padStart(2, '0');
        const startD = String(startDateObj.getUTCDate()).padStart(2, '0');
        const startHH = String(startDateObj.getUTCHours()).padStart(2, '0');
        const startMM = String(startDateObj.getUTCMinutes()).padStart(2, '0');
        
        const endY = endDateObj.getUTCFullYear();
        const endM = String(endDateObj.getUTCMonth() + 1).padStart(2, '0');
        const endD = String(endDateObj.getUTCDate()).padStart(2, '0');
        const endHH = String(endDateObj.getUTCHours()).padStart(2, '0');
        const endMM = String(endDateObj.getUTCMinutes()).padStart(2, '0');
        
        const datesParam = `${startY}${startM}${startD}T${startHH}${startMM}00Z/${endY}${endM}${endD}T${endHH}${endMM}00Z`;
        
        const baseUrl = "https://calendar.google.com/calendar/render";
        const params = new URLSearchParams({
            action: "TEMPLATE",
            text: title,
            details: description,
            dates: datesParam,
            ctz: "America/Caracas"
        });
        
        return `${baseUrl}?${params.toString()}`;
    } catch(e) {
        console.error("Error generando enlace Google Calendar:", e);
        return "#";
    }
}

// --- LÓGICA PWA E INSTALACIÓN DE APLICACIÓN ---
let deferredPwaPrompt = null;

if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
        navigator.serviceWorker.register('/sw.js')
            .then(reg => {
                console.log('PWA Service Worker registrado:', reg.scope);
                setTimeout(() => {
                    initFirebaseMessagingFlow(reg);
                }, 1000);
            })
            .catch(err => console.error('Error al registrar PWA Service Worker:', err));
    });
}

window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    deferredPwaPrompt = e;
    const installBtn = document.getElementById('pwa-install-btn');
    if (installBtn) {
        installBtn.classList.remove('hide');
    }
});

async function installPWA() {
    requestNotificationPermission();
    if (!deferredPwaPrompt) return;
    deferredPwaPrompt.prompt();
    const { outcome } = await deferredPwaPrompt.userChoice;
    console.log(`PWA choice: ${outcome}`);
    deferredPwaPrompt = null;
    const installBtn = document.getElementById('pwa-install-btn');
    if (installBtn) installBtn.classList.add('hide');
}

// ==========================================
// NOTIFICACIONES PWA NATIVAS (Barra de Tareas/Dispositivo)
// ==========================================
let _notifiedKeys = new Set(JSON.parse(localStorage.getItem('_pwa_notified_keys') || '[]'));

function saveNotifiedKeys() {
    try {
        localStorage.setItem('_pwa_notified_keys', JSON.stringify(Array.from(_notifiedKeys).slice(-100)));
    } catch(e) {}
}

function openNotificationGuideModal() {
    openModal('notification-guide-modal');
}
window.openNotificationGuideModal = openNotificationGuideModal;

function showOnboardingTutorialIfNeeded() {
    if (localStorage.getItem('tutorial_notificaciones_visto') !== 'true') {
        localStorage.setItem('tutorial_notificaciones_visto', 'true');
        setTimeout(() => {
            if (typeof openModal === 'function') {
                openModal('onboarding-notification-modal');
            } else {
                const modal = document.getElementById('onboarding-notification-modal');
                if (modal) modal.classList.remove('hide');
            }
        }, 800);
    }
    try { updateNotificationBannerVisibility(); } catch(e) {}
}
window.showOnboardingTutorialIfNeeded = showOnboardingTutorialIfNeeded;

function updateNotificationBannerVisibility() {
    const patBanner = document.getElementById('pat-notif-banner');
    const adminBanner = document.getElementById('admin-notif-banner');
    const isGranted = 'Notification' in window && Notification.permission === 'granted';
    
    if (patBanner) {
        patBanner.style.display = isGranted ? 'none' : 'flex';
    }
    if (adminBanner) {
        adminBanner.style.display = isGranted ? 'none' : 'flex';
    }
}
window.updateNotificationBannerVisibility = updateNotificationBannerVisibility;

async function requestNotificationPermission() {
    if (!('Notification' in window)) return false;
    if (Notification.permission === 'granted') {
        showOnboardingTutorialIfNeeded();
        try { updateNotificationBannerVisibility(); } catch(e) {}
        return true;
    }
    if (Notification.permission !== 'denied') {
        try {
            const permission = await Notification.requestPermission();
            if (permission === 'granted') {
                showOnboardingTutorialIfNeeded();
                try { updateNotificationBannerVisibility(); } catch(e) {}
                return true;
            }
            openNotificationGuideModal();
            return false;
        } catch(e) {
            openNotificationGuideModal();
            return false;
        }
    } else {
        openNotificationGuideModal();
    }
    return false;
}
window.requestNotificationPermission = requestNotificationPermission;

function playNotificationSound() {
    try {
        const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        const osc = audioCtx.createOscillator();
        const gain = audioCtx.createGain();
        osc.type = 'sine';
        osc.frequency.setValueAtTime(587.33, audioCtx.currentTime);
        osc.frequency.exponentialRampToValueAtTime(880, audioCtx.currentTime + 0.15);
        gain.gain.setValueAtTime(0.15, audioCtx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + 0.3);
        osc.connect(gain);
        gain.connect(audioCtx.destination);
        osc.start();
        osc.stop(audioCtx.currentTime + 0.3);
    } catch(e) {}
}
window.playNotificationSound = playNotificationSound;

function triggerNativeNotification(title, body, key, link) {
    if (!('Notification' in window) || Notification.permission !== 'granted') return;
    if (key && _notifiedKeys.has(String(key))) return; // Evitar duplicados

    if (key) {
        _notifiedKeys.add(String(key));
        saveNotifiedKeys();
    }

    playNotificationSound();

    try {
        if ('serviceWorker' in navigator && navigator.serviceWorker.controller) {
            navigator.serviceWorker.ready.then(reg => {
                reg.showNotification(title, {
                    body: body,
                    icon: '/static/logo.png',
                    badge: '/static/logo.png',
                    vibrate: [200, 100, 200],
                    data: { url: link || '/' }
                });
            });
        } else {
            new Notification(title, {
                body: body,
                icon: '/static/logo.png',
                data: { url: link || '/' }
            });
        }
    } catch(e) {
        console.warn('Error disparando notificación nativa:', e);
    }
}

function urlBase64ToUint8Array(base64String) {
    const padding = '='.repeat((4 - base64String.length % 4) % 4);
    const base64 = (base64String + padding).replace(/\-/g, '+').replace(/_/g, '/');
    const rawData = window.atob(base64);
    const outputArray = new Uint8Array(rawData.length);
    for (let i = 0; i < rawData.length; ++i) {
        outputArray[i] = rawData.charCodeAt(i);
    }
    return outputArray;
}

async function subscribeUserToVapidPush() {
    if (!('serviceWorker' in navigator) || !('PushManager' in window)) return;
    try {
        const hasPermission = await requestNotificationPermission();
        if (!hasPermission) return;

        const reg = await navigator.serviceWorker.ready;
        const res = await fetch('/api/push/public-key');
        const data = await res.json();
        if (!data.public_key) return;

        const applicationServerKey = urlBase64ToUint8Array(data.public_key);
        let sub = await reg.pushManager.getSubscription();

        if (!sub) {
            sub = await reg.pushManager.subscribe({
                userVisibleOnly: true,
                applicationServerKey: applicationServerKey
            });
        }

        await fetch('/api/push/subscribe', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(sub)
        });
        console.log('Suscripción WebPush VAPID registrada con éxito.');
    } catch (err) {
        console.error('Error al suscribir a VAPID Push:', err);
    }
}
window.subscribeUserToVapidPush = subscribeUserToVapidPush;

// ==========================================
// ESTADO GLOBAL DE LA APLICACIÓN
// ==========================================
let activeView = 'dashboard';
let patients = [];
let googleConfigured = false;
let currentYear = new Date().getFullYear();
let currentMonth = String(new Date().getMonth() + 1).padStart(2, '0');

// Al iniciar la ventana (Arranque Seguro Móvil y Escritorio)
document.addEventListener('DOMContentLoaded', () => {
    // Garantía absoluta de ocultar pantalla de carga en máximo 1.5s
    setTimeout(() => {
        hideLoadingScreen();
        subscribeUserToVapidPush();
        try { updateNotificationBannerVisibility(); } catch(e) {}
    }, 1500);

    try { checkAdminExists(); } catch(e) {}
    try {
        checkFastBookingQuery().then(isFast => {
            if (!isFast) {
                checkSession();
            } else {
                hideLoadingScreen();
            }
        }).catch(() => {
            checkSession();
        });
    } catch(e) { checkSession(); }
    try { initializeDateFilters(); } catch(e) {}

    // Detectar cambios de paciente en modal de citas para mostrar/ocultar prepagos
        const pCedulaInput = document.getElementById('p-cedula');
    if (pCedulaInput) {
        pCedulaInput.addEventListener('blur', checkCedulaAutoFill);
    }
    const ePaciente = document.getElementById('e-paciente');
    if (ePaciente) {
        ePaciente.addEventListener('change', (e) => {
            checkPatientPrepayments(e.target.value);
        });
    }
    
    // Detectar cambios de estado en modal de citas para deshabilitar montos
    const eEstado = document.getElementById('e-estado');
    if (eEstado) {
        eEstado.addEventListener('change', (e) => {
            if (e.target.value === 'ConsumirPrepago') {
                document.getElementById('e-monto').value = '0.00';
                document.getElementById('e-monto').disabled = true;
                document.getElementById('e-cant-sesiones').value = '1';
                document.getElementById('e-cant-sesiones').disabled = true;
            } else {
                document.getElementById('e-monto').disabled = false;
                document.getElementById('e-cant-sesiones').disabled = false;
            }
        });
    }

    // Solicitar permiso de notificaciones nativas suavemente
    setTimeout(() => {
        requestNotificationPermission();
    }, 2500);
});

// ==========================================
// CONTROL DE NAVEGACIÓN Y MENÚ
// ==========================================
function switchView(viewId) {
    const isPending = sessionStorage.getItem('cuenta_pendiente_aprobacion') === '1';
    const restrictedViews = ['agenda', 'register-patient', 'patient-list', 'sessions', 'pizarra-visual', 'therapist-tools', 'finance'];
    if (isPending && restrictedViews.includes(viewId)) {
        alert("⌛ Cuenta en Proceso de Verificación 🔒\n\nEstamos chequeando tu documentación. Esta herramienta se activará automáticamente en cuanto tu cuenta sea aprobada por la administración.");
        return;
    }

    // Verificación de bloqueos granulares
    if (viewId === 'register-patient' && isFeatureBlocked('registro')) {
        alert("La función de Registro de Pacientes está suspendida por administración.");
        return;
    }
    if (viewId === 'sessions' && isFeatureBlocked('evoluciones')) {
        alert("La función de Evoluciones Clínicas está suspendida por administración.");
        return;
    }
    if (viewId === 'finance' && isFeatureBlocked('finanzas')) {
        alert("La función de Finanzas y Pagos está suspendida por administración.");
        return;
    }
    if (viewId === 'pizarra-visual' && isFeatureBlocked('pizarra')) {
        alert("La función de Pizarra Terapéutica está suspendida por administración.");
        return;
    }
    if (viewId === 'agenda' && isFeatureBlocked('agenda')) {
        alert("La función de Agenda y Calendario está suspendida por administración.");
        return;
    }
    if (viewId === 'therapist-tools' && isFeatureBlocked('herramientas')) {
        alert("La función de Herramientas Terapéuticas está suspendida por administración.");
        return;
    }

    // Ocultar cualquier modal abierto al cambiar de vista
    document.querySelectorAll('.modal-overlay').forEach(m => {
        m.classList.add('hide');
        m.style.display = 'none';
    });

    // Ocultar todas las vistas
    document.querySelectorAll('.app-view').forEach(view => {
        view.classList.add('hide');
    });
    
    // Quitar active de los items de menú
    document.querySelectorAll('.nav-item').forEach(item => {
        item.classList.remove('active');
    });

    // Mostrar vista activa
    const targetView = document.getElementById(`view-${viewId}`);
    if (targetView) {
        targetView.classList.remove('hide');
    }

    // Activar item de menú correspondiente
    const activeItem = document.querySelector(`.nav-item[data-view="${viewId}"]`);
    if (activeItem) {
        activeItem.classList.add('active');
    }

    activeView = viewId;
    
    // Cerrar sidebar en móvil al cambiar vista
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('sidebar-overlay');
    sidebar.classList.remove('open');
    overlay.classList.add('hide');

    // Cargar datos dinámicos según vista
    if (viewId === 'dashboard') {
        loadDashboardStats();
        loadAgendaCompact();
    } else if (viewId === 'patient-list') {
        loadPatients();
    } else if (viewId === 'sessions') {
        loadPatientsDropdowns();
        loadSessions();
    } else if (viewId === 'finance') {
        loadFinanceData();
    } else if (viewId === 'agenda') {
        loadPatientsDropdowns();
        switchAgendaSubView('calendar');
    } else if (viewId === 'settings') {
        checkGoogleStatus();
        loadAdminAvailability();
        loadPatientLinks();
    } else if (viewId === 'pizarra-visual') {
        loadPizarraPatients();
        loadPizarraVisual();
    } else if (viewId === 'therapist-tools') {
        loadTherapistToolsCatalog();
    } else if (viewId === 'manual-confirmations') {
        renderManualConfirmationsView();
    }
}

function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('sidebar-overlay');
    sidebar.classList.toggle('open');
    overlay.classList.toggle('hide');
}

function initializeDateFilters() {
    const yearSelect = document.getElementById('finance-filter-year');
    const monthSelect = document.getElementById('finance-filter-month');
    
    // Llenar años (año actual +- 3 años)
    const thisYear = new Date().getFullYear();
    for (let y = thisYear - 3; y <= thisYear + 3; y++) {
        const option = document.createElement('option');
        option.value = y;
        option.textContent = y;
        if (y === thisYear) option.selected = true;
        yearSelect.appendChild(option);
    }
    
    // Llenar meses
    const meses = [
        "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
        "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
    ];
    meses.forEach((m, idx) => {
        const option = document.createElement('option');
        option.value = String(idx + 1).padStart(2, '0');
        option.textContent = m;
        if (idx === new Date().getMonth()) option.selected = true;
        monthSelect.appendChild(option);
    });

    // Actualizar fecha del Dashboard
    const options = { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' };
    document.getElementById('dashboard-date').textContent = new Date().toLocaleDateString('es-ES', options);
}

// ==========================================
// SEGURIDAD Y AUTENTICACIÓN LOCAL
// ==========================================
async function checkAdminExists() {
    try {
        const res = await fetch('/api/admin-exists');
        const data = await res.json();
        
        const title = document.getElementById('auth-title');
        const subtitle = document.getElementById('auth-subtitle');
        const btn = document.getElementById('auth-btn');
        const toggleBtn = document.getElementById('auth-toggle-btn');
        
        if (!data.exists) {
            title.textContent = "Registrar Terapeuta";
            subtitle.textContent = "Crea tu cuenta de acceso local única.";
            btn.textContent = "Crear Administrador";
            authFormMode = 'register';
            if (toggleBtn) toggleBtn.classList.add('hide');
        } else {
            title.textContent = "Iniciar Sesión";
            subtitle.textContent = "Acceso protegido. Base de datos local.";
            btn.textContent = "Iniciar Sesión";
            authFormMode = 'login';
            if (toggleBtn) toggleBtn.classList.remove('hide');
        }
    } catch (err) {
        console.error("Error checking admin status:", err);
    }
}

let authFormMode = 'login';

function toggleAuthMode(e) {
    if (e) e.preventDefault();
    const title = document.getElementById('auth-title');
    const subtitle = document.getElementById('auth-subtitle');
    const btnSubmit = document.getElementById('auth-btn');
    const btnToggle = document.getElementById('auth-toggle-btn');
    const errorMsg = document.getElementById('auth-error-msg');
    
    errorMsg.classList.add('hide');
    
    if (authFormMode === 'login') {
        authFormMode = 'register';
        title.textContent = "Registrar Terapeuta";
        subtitle.textContent = "Crea tu cuenta de terapeuta para este consultorio local.";
        btnSubmit.textContent = "Crear Cuenta";
        btnToggle.textContent = "Ya tengo cuenta / Iniciar Sesión";
    } else {
        authFormMode = 'login';
        title.textContent = "Espacio Terapéutico";
        subtitle.textContent = "Acceso protegido. Base de datos local.";
        btnSubmit.textContent = "Iniciar Sesión";
        btnToggle.textContent = "Crear una Cuenta Nueva (Psicólogo)";
    }
}

function showLoadingScreen(msg) {
    const loader = document.getElementById('loading-screen');
    if (loader) {
        loader.style.display = 'flex';
        loader.style.visibility = 'visible';
        loader.style.opacity = '1';
        const txt = loader.querySelector('p') || loader.querySelector('.loading-text');
        if (txt && msg) txt.textContent = msg;
    }
}

function hideLoadingScreen() {
    const loader = document.getElementById('loading-screen');
    if (loader) {
        loader.style.opacity = '0';
        loader.style.visibility = 'hidden';
        setTimeout(() => {
            loader.style.display = 'none';
        }, 350);
    }
}

async function checkSession() {
    try {
        const res = await fetch('/api/check-session');
        const data = await res.json();
        
        if (data.logged_in) {
            if (data.role === 'paciente') {
                showPatientLayout(data.username, data.patient_id);
            } else {
                showAppLayout(data.username, data.role, data.activo, data.bloqueos, data.user_id, data.aviso_pago, data.primer_inicio, data.suscripcion_paga, data.fecha_expiracion_prueba, data.nombres, data.apellidos);
            }
        } else {
            showAuthScreen();
        }
    } catch (err) {
        showAuthScreen();
    } finally {
        hideLoadingScreen();
    }
}

async function handleAuthSubmit(e) {
    e.preventDefault();
    const username = document.getElementById('auth-username').value;
    const password = document.getElementById('auth-password').value;
    const errorMsg = document.getElementById('auth-error-msg');
    
    errorMsg.classList.add('hide');
    
    if (authFormMode === 'register') {
        try {
            const res = await fetch('/api/register-admin', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password })
            });
            const data = await res.json();
            if (res.ok) {
                alert("Usuario administrador creado con éxito. Inicia sesión a continuación.");
                document.getElementById('auth-username').value = '';
                document.getElementById('auth-password').value = '';
                authFormMode = 'login';
                checkAdminExists();
            } else {
                errorMsg.textContent = data.error || 'Error al registrar administrador.';
                errorMsg.classList.remove('hide');
            }
        } catch (err) {
            errorMsg.textContent = 'Error de conexión con el servidor.';
            errorMsg.classList.remove('hide');
        }
    } else {
        // Modo Login: Identificación Automática de Rol
        try {
            let dataAdmin = null;
            let dataPatient = null;
            let networkError = false;

            try {
                const resAdmin = await fetch('/api/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username, password })
                });
                dataAdmin = await resAdmin.json();
                if (resAdmin.ok) {
                    showAppLayout(dataAdmin.username, dataAdmin.role, dataAdmin.activo, dataAdmin.bloqueos, dataAdmin.user_id, dataAdmin.aviso_pago, dataAdmin.primer_inicio, dataAdmin.suscripcion_paga, dataAdmin.fecha_expiracion_prueba, dataAdmin.nombres, dataAdmin.apellidos);
                    setTimeout(() => { try { initFirebaseMessagingFlow(); } catch(e) {} }, 1500);
                    return;
                }
            } catch (errAdmin) {
                console.warn("Fallo conexión login admin:", errAdmin);
                networkError = true;
            }
            
            // 2. Si no es admin o contraseña incorrecta para admin, intentar como Paciente
            try {
                const resPatient = await fetch('/api/patient/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username, password })
                });
                dataPatient = await resPatient.json();
                
                if (resPatient.ok) {
                    if (dataPatient.first_login) {
                        showPatientWizard(dataPatient.patient_id, dataPatient.username);
                    } else {
                        showPatientLayout(dataPatient.username, dataPatient.patient_id);
                    }
                    setTimeout(() => { try { initFirebaseMessagingFlow(); } catch(e) {} }, 1500);
                    return;
                }
            } catch (errPatient) {
                console.warn("Fallo conexión login paciente:", errPatient);
            }

            if (!dataAdmin && !dataPatient && networkError) {
                errorMsg.textContent = 'Error de conexión: El servidor no está iniciado o no responde.';
                errorMsg.classList.remove('hide');
                return;
            }
            
            // Si ambos respondieron pero con fallo de credenciales
            let finalError = 'Usuario o contraseña incorrectos.';
            if (dataAdmin && dataAdmin.error && dataAdmin.error !== 'Credenciales inválidas.') {
                finalError = dataAdmin.error;
            } else if (dataPatient && dataPatient.error && dataPatient.error !== 'Credenciales inválidas.') {
                finalError = dataPatient.error;
            }
            errorMsg.textContent = finalError;
            errorMsg.classList.remove('hide');
            
        } catch (err) {
            errorMsg.textContent = 'Error de conexión con el servidor.';
            errorMsg.classList.remove('hide');
        }
    }
}

async function handleLogout() {
    if (!confirm("¿Está seguro de que desea cerrar la sesión por seguridad?")) return;
    try {
        await fetch('/api/logout', { method: 'POST' });
    } catch (err) {
        console.warn("Error enviando petición de logout:", err);
    } finally {
        sessionStorage.clear();
        localStorage.clear();
        clearAllNotificationIntervals();
        showAuthScreen();
    }
}

function isFeatureBlocked(feature) {
    const blocksStr = sessionStorage.getItem('bloqueos');
    if (!blocksStr) return false;
    try {
        const blocks = JSON.parse(blocksStr);
        return blocks[feature] === 1;
    } catch(e) {
        return false;
    }
}

let notificationIntervalId = null;
let patientNotificationIntervalId = null;

function clearAllNotificationIntervals() {
    if (notificationIntervalId) { clearInterval(notificationIntervalId); notificationIntervalId = null; }
    if (patientNotificationIntervalId) { clearInterval(patientNotificationIntervalId); patientNotificationIntervalId = null; }
}

function getInitials(nombres, apellidos, username) {
    let first = '';
    let last = '';
    if (nombres && String(nombres).trim()) {
        const nParts = String(nombres).trim().split(/\s+/);
        first = nParts[0].charAt(0).toUpperCase();
    }
    if (apellidos && String(apellidos).trim()) {
        const aParts = String(apellidos).trim().split(/\s+/);
        last = aParts[0].charAt(0).toUpperCase();
    }
    if (first && last) {
        return first + last;
    }
    if (first && !last) {
        const nParts = String(nombres).trim().split(/\s+/);
        if (nParts.length > 1) {
            return (nParts[0].charAt(0) + nParts[1].charAt(0)).toUpperCase();
        }
        return nParts[0].substring(0, 2).toUpperCase();
    }
    if (username && String(username).trim()) {
        const u = String(username).trim().replace(/^psic\.?/i, '');
        if (u.length >= 2) {
            return u.substring(0, 2).toUpperCase();
        }
        return u.charAt(0).toUpperCase();
    }
    return 'ET';
}
window.getInitials = getInitials;

function showAppLayout(username, role, activo, bloqueos, userId, avisoPago, primerInicio, suscripcionPaga, fechaExpiracionPrueba, nombres, apellidos) {
    document.body.classList.remove('is-patient');
    document.getElementById('auth-screen').classList.add('hide');

    // Actualizar avatar e iniciales del psicólogo en la barra superior
    const avatarEl = document.getElementById('header-user-avatar') || document.querySelector('.user-avatar');
    const nameEl = document.getElementById('header-user-name') || document.querySelector('.user-name');
    const roleEl = document.getElementById('header-user-role') || document.querySelector('.user-role');

    let fullPersonName = `${nombres || ''} ${apellidos || ''}`.trim();
    if (!fullPersonName) fullPersonName = username || 'Psicólogo';

    const initials = getInitials(nombres, apellidos, username);
    if (avatarEl) avatarEl.textContent = initials;

    // Manejar Badge de Prueba Gratis de 3 días en la barra superior
    const trialBadge = document.getElementById('header-trial-badge');
    const trialText = document.getElementById('trial-badge-text');
    if (trialBadge && role === 'psicologo') {
        if (suscripcionPaga === 1) {
            trialBadge.classList.add('hide');
        } else if (fechaExpiracionPrueba) {
            const expDate = new Date(fechaExpiracionPrueba);
            const diffHours = (expDate - new Date()) / (1000 * 60 * 60);
            if (diffHours > 0) {
                const daysLeft = Math.ceil(diffHours / 24);
                if (trialText) trialText.textContent = `⏳ Prueba Gratis: Quedan ${daysLeft} día${daysLeft > 1 ? 's' : ''}`;
                trialBadge.classList.remove('hide');
            } else {
                trialBadge.classList.add('hide');
            }
        } else {
            trialBadge.classList.add('hide');
        }
    } else if (trialBadge) {
        trialBadge.classList.add('hide');
    }

    // Disparar Asistente de Configuración Inicial (Onboarding Wizard) si primerInicio === 1
    if (role === 'psicologo' && (primerInicio === 1 || primerInicio === true)) {
        setTimeout(() => {
            openPsychologistOnboardingWizard({ username, role, userId });
        }, 400);
    }
    document.getElementById('patient-header').classList.add('hide');
    document.getElementById('patient-menu').classList.add('hide');
    document.getElementById('patient-menu-overlay').classList.add('hide');
    document.getElementById('sidebar').classList.remove('hide');
    document.getElementById('app-layout').classList.remove('hide');
    
    // Controlar aviso de pago pendiente
    const avisoPagoBanner = document.getElementById('dashboard-aviso-pago');
    if (avisoPagoBanner) {
        if (avisoPago === 1) {
            avisoPagoBanner.classList.remove('hide');
        } else {
            avisoPagoBanner.classList.add('hide');
        }
    }
    
    if (userId) {
        sessionStorage.setItem('user_id', userId);
    } else {
        sessionStorage.removeItem('user_id');
    }
    
    const mcToggleCard = document.getElementById('card-toggle-manual-confirmations-module');
    if (mcToggleCard) {
        if (role === 'superadmin' || role === 'admin') {
            mcToggleCard.classList.remove('hide');
        } else {
            mcToggleCard.classList.add('hide');
        }
    }

    if (role === 'superadmin') {
        if (nameEl) nameEl.textContent = `Admin: ${fullPersonName}`;
        if (roleEl) roleEl.textContent = `Superadministrador`;
        document.querySelectorAll('.nav-item').forEach(link => {
            const v = link.getAttribute('data-view');
            if (v !== 'superadmin-dashboard' && v !== 'settings') {
                link.classList.add('hide');
            } else {
                link.classList.remove('hide');
            }
        });
        switchView('superadmin-dashboard');
        loadSuperadminData();
        return;
    }
    
    const formattedTitle = fullPersonName.toLowerCase().startsWith('psic') ? fullPersonName : `Psic. ${fullPersonName}`;
    if (nameEl) nameEl.textContent = formattedTitle;
    if (roleEl) roleEl.textContent = `Terapeuta`;
    
    const saTab = document.querySelector('[data-view="superadmin-dashboard"]');
    if (saTab) saTab.classList.add('hide');
    
    document.querySelectorAll('.nav-item').forEach(link => {
        if (link.getAttribute('data-view') !== 'superadmin-dashboard') {
            link.classList.remove('hide');
        }
    });
    
    if (activo === 0 && role === 'psicologo') {
        sessionStorage.setItem('cuenta_pendiente_aprobacion', '1');
        const pendingBanner = document.getElementById('dashboard-pending-approval-banner');
        if (pendingBanner) pendingBanner.classList.remove('hide');
        
        const restrictedViews = ['agenda', 'register-patient', 'patient-list', 'sessions', 'pizarra-visual', 'therapist-tools', 'finance'];
        document.querySelectorAll('.nav-item').forEach(link => {
            const v = link.getAttribute('data-view');
            if (restrictedViews.includes(v)) {
                link.style.opacity = '0.55';
                link.title = 'Función en espera de aprobación de cuenta 🔒';
                if (!link.querySelector('.lock-badge-icon')) {
                    const lockBadge = document.createElement('span');
                    lockBadge.className = 'lock-badge-icon';
                    lockBadge.style.cssText = 'margin-left: auto; font-size: 0.85rem; font-weight: bold; color: #d97706;';
                    lockBadge.textContent = '🔒';
                    link.appendChild(lockBadge);
                }
            }
        });
    } else {
        sessionStorage.removeItem('cuenta_pendiente_aprobacion');
        const pendingBanner = document.getElementById('dashboard-pending-approval-banner');
        if (pendingBanner) pendingBanner.classList.add('hide');
        
        document.querySelectorAll('.nav-item').forEach(link => {
            link.style.opacity = '1';
            link.removeAttribute('title');
            const lockBadge = link.querySelector('.lock-badge-icon');
            if (lockBadge) lockBadge.remove();
        });
    }
    
    // Guardar bloqueos en memoria para verificación dinámica
    if (bloqueos) {
        sessionStorage.setItem('bloqueos', JSON.stringify(bloqueos));
        // Ocultar items del menú según bloqueos
        if (bloqueos.registro === 1) {
            const link = document.querySelector('[data-view="register-patient"]');
            if (link) link.classList.add('hide');
        }
        if (bloqueos.evoluciones === 1) {
            const link = document.querySelector('[data-view="sessions"]');
            if (link) link.classList.add('hide');
        }
        if (bloqueos.finanzas === 1) {
            const link = document.querySelector('[data-view="finance"]');
            if (link) link.classList.add('hide');
        }
        if (bloqueos.pizarra === 1) {
            const link = document.querySelector('[data-view="pizarra-visual"]');
            if (link) link.classList.add('hide');
        }
        if (bloqueos.agenda === 1) {
            const link = document.querySelector('[data-view="agenda"]');
            if (link) link.classList.add('hide');
        }
        if (bloqueos.herramientas === 1) {
            const link = document.querySelector('[data-view="therapist-tools"]');
            if (link) link.classList.add('hide');
        }
    } else {
        sessionStorage.removeItem('bloqueos');
    }
    
    switchView('dashboard');
    clearAllNotificationIntervals();
    loadNotifications();
    notificationIntervalId = setInterval(loadNotifications, 30000);
    loadMessageTemplates();
    hideLoadingScreen();
}

function showPatientLayout(username, patientId) {
    sessionStorage.setItem('patient_id', patientId);
    sessionStorage.setItem('patient_username', username);
    sessionStorage.setItem('role', 'paciente');
    
    document.body.classList.add('is-patient');
    document.getElementById('auth-screen').classList.add('hide');
    document.getElementById('sidebar').classList.add('hide');
    document.getElementById('app-layout').classList.remove('hide');
    document.getElementById('patient-header').classList.remove('hide');
    document.getElementById('patient-menu').classList.remove('hide');
    
    // Inyección optimista e inmediata del nombre del consultante y terapeuta
    if (username) {
        const menuUserName = document.getElementById('pat-menu-user-name');
        if (menuUserName) {
            menuUserName.textContent = username;
        }
        const welcomeTitle = document.getElementById('pat-welcome-title');
        if (welcomeTitle) {
            welcomeTitle.textContent = `Hola, ${username} 👋`;
        }
    }
    
    const cachedTherapist = sessionStorage.getItem('patient_therapist_name') || 'Psic. Paulo Mora';
    const menuTherapist = document.getElementById('pat-menu-therapist-name');
    if (menuTherapist) {
        menuTherapist.innerHTML = `
            <span style="display: inline-block; width: 6px; height: 6px; background-color: var(--primary-color); border-radius: 50%;"></span>
            <span>Terapeuta: ${cachedTherapist}</span>
        `;
    }
    const headerTherapist = document.getElementById('pat-header-therapist-name');
    if (headerTherapist) {
        headerTherapist.textContent = cachedTherapist;
    }
    
    switchPatientView('patient-home');
    loadPatientPortalData(patientId);
    
    // Iniciar notificaciones de paciente
    clearAllNotificationIntervals();
    loadPatientNotifications(patientId);
    patientNotificationIntervalId = setInterval(() => loadPatientNotifications(patientId), 30000);
    hideLoadingScreen();
}

function showPatientWizard(patientId, username) {
    sessionStorage.setItem('patient_id', patientId);
    sessionStorage.setItem('patient_username', username);
    sessionStorage.setItem('role', 'paciente');
    
    document.body.classList.add('is-patient');
    document.getElementById('auth-screen').classList.add('hide');
    document.getElementById('sidebar').classList.add('hide');
    document.getElementById('patient-header').classList.add('hide'); // Ocultar cabecera durante registro
    document.getElementById('patient-menu').classList.add('hide');   // Ocultar menú durante registro
    document.getElementById('app-layout').classList.remove('hide');
    
    document.getElementById('wizard-patient-id').value = patientId;
    document.getElementById('wiz-username').value = username;
    
    // Ocultar todas las vistas y mostrar solo la de primer acceso
    document.querySelectorAll('.app-view').forEach(v => v.classList.add('hide'));
    document.getElementById('view-patient-first-setup').classList.remove('hide');
    goToWizardStep(1);
    hideLoadingScreen();
}

function showAuthScreen() {
    clearAllNotificationIntervals();
    sessionStorage.clear();
    document.body.classList.remove('is-patient');
    document.getElementById('app-layout').classList.add('hide');
    document.getElementById('patient-header').classList.add('hide');
    document.getElementById('patient-menu').classList.add('hide');
    document.getElementById('patient-menu-overlay').classList.add('hide');
    document.getElementById('sidebar').classList.remove('hide'); // Restaurar estado inicial
    document.getElementById('auth-screen').classList.remove('hide');
    document.getElementById('auth-username').value = '';
    document.getElementById('auth-password').value = '';
    checkAdminExists();
    hideLoadingScreen();
}

// Variables de estado del calendario del paciente
let bookingMonth = new Date().getMonth();
let bookingYear = new Date().getFullYear();

const monthNames = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"];

function initBookingCalendar() {
    bookingMonth = new Date().getMonth();
    bookingYear = new Date().getFullYear();
    renderBookingCalendar();
}

function changeBookingMonth(offset) {
    bookingMonth += offset;
    if (bookingMonth < 0) {
        bookingMonth = 11;
        bookingYear--;
    } else if (bookingMonth > 11) {
        bookingMonth = 0;
        bookingYear++;
    }
    renderBookingCalendar();
}

async function renderBookingCalendar() {
    const headerTitle = document.getElementById('pat-cal-month-year');
    if (!headerTitle) return;
    
    headerTitle.textContent = `${monthNames[bookingMonth]} ${bookingYear}`;
    
    const grid = document.getElementById('pat-cal-days-grid');
    grid.innerHTML = '<div style="grid-column: span 7; text-align: center; padding: 1rem;"><span class="text-secondary text-sm">Cargando disponibilidad...</span></div>';
    
    const modalitySelect = document.getElementById('pat-req-modalidad');
    let modality = modalitySelect ? modalitySelect.value : '';
    if (!modality && modalitySelect && modalitySelect.options.length > 0) {
        for (let opt of modalitySelect.options) {
            if (opt.value) {
                modality = opt.value;
                modalitySelect.value = modality;
                break;
            }
        }
    }
    if (!modality) modality = 'all';
    
    let availableDates = [];
    try {
        const monthForApi = bookingMonth + 1;
        const psicParam = (typeof currentPatientPsicologoId !== 'undefined' && currentPatientPsicologoId) ? `&psicologo_id=${currentPatientPsicologoId}` : (typeof fastBookingTherapistId !== 'undefined' && fastBookingTherapistId ? `&psicologo_id=${fastBookingTherapistId}` : '');
        const res = await fetch(`/api/patient/available-dates?year=${bookingYear}&month=${monthForApi}&modalidad=${encodeURIComponent(modality)}${psicParam}`);
        if (res.ok) {
            const data = await res.json();
            availableDates = data.dates || [];
        }
    } catch (e) {
        console.error("Error al obtener disponibilidad del calendario:", e);
    }
    
    grid.innerHTML = '';
    
    const firstDay = new Date(bookingYear, bookingMonth, 1).getDay();
    const totalDays = new Date(bookingYear, bookingMonth + 1, 0).getDate();
    
    for (let i = 0; i < firstDay; i++) {
        const spacer = document.createElement('div');
        grid.appendChild(spacer);
    }
    
    const today = new Date();
    today.setHours(0,0,0,0);
    
    for (let day = 1; day <= totalDays; day++) {
        const cell = document.createElement('div');
        cell.className = 'pat-cal-day-cell';
        cell.textContent = day;
        
        const cellMonthStr = String(bookingMonth + 1).zfill(2);
        const cellDayStr = String(day).zfill(2);
        const dateStr = `${bookingYear}-${cellMonthStr}-${cellDayStr}`;
        
        const cellDate = new Date(bookingYear, bookingMonth, day);
        cellDate.setHours(0,0,0,0);
        
        const isPast = cellDate < today;
        const isAvailable = availableDates.includes(dateStr);
        
        if (isPast || !isAvailable) {
            cell.classList.add('disabled');
            cell.style.color = '#ccc';
            cell.style.cursor = 'not-allowed';
            cell.style.display = 'inline-flex';
            cell.style.alignItems = 'center';
            cell.style.justifyContent = 'center';
            cell.style.margin = 'auto';
            cell.style.width = '32px';
            cell.style.height = '32px';
        } else {
            cell.classList.add('available');
            cell.style.cursor = 'pointer';
            cell.style.display = 'inline-flex';
            cell.style.alignItems = 'center';
            cell.style.justifyContent = 'center';
            cell.style.margin = 'auto';
            cell.style.width = '32px';
            cell.style.height = '32px';
            cell.style.borderRadius = '50%';
            cell.style.border = '2px solid #10b981';
            cell.style.fontWeight = '700';
            cell.style.color = '#047857';
            cell.style.backgroundColor = '#ecfdf5';
            
            cell.onclick = () => {
                document.querySelectorAll('.pat-cal-day-cell.selected').forEach(c => {
                    c.classList.remove('selected');
                    c.style.backgroundColor = '#ecfdf5';
                    c.style.color = '#047857';
                });
                
                cell.classList.add('selected');
                cell.style.backgroundColor = '#10b981';
                cell.style.color = 'white';
                
                document.getElementById('pat-req-fecha').value = dateStr;
                document.getElementById('pat-req-hora').value = '';
                document.getElementById('pat-submit-req-btn').disabled = true;
                
                fetchAvailableHours(dateStr);
            };
        }
        grid.appendChild(cell);
    }
}

String.prototype.zfill = function(size) {
    let s = this;
    while (s.length < size) s = "0" + s;
    return s;
};

async function fetchAvailableHours(dateStr) {
    const hoursGrid = document.getElementById('pat-hours-grid');
    const hoursContainer = document.getElementById('pat-hours-container');
    const hoursTitle = document.getElementById('pat-hours-title');
    
    hoursGrid.innerHTML = '<span class="text-secondary text-sm">Consultando horarios...</span>';
    hoursContainer.classList.remove('hide');
    hoursTitle.textContent = `Horas disponibles para el día ${dateStr.split('-').reverse().join('/')}:`;
    
    try {
        const modalitySelect = document.getElementById('pat-req-modalidad');
        const modality = modalitySelect ? modalitySelect.value : 'all';
        const psicParam = (typeof currentPatientPsicologoId !== 'undefined' && currentPatientPsicologoId) ? `&psicologo_id=${currentPatientPsicologoId}` : (typeof fastBookingTherapistId !== 'undefined' && fastBookingTherapistId ? `&psicologo_id=${fastBookingTherapistId}` : '');
        const res = await fetch(`/api/patient/available-slots?date=${dateStr}&modalidad=${encodeURIComponent(modality)}${psicParam}`);
        const data = await res.json();
        
        hoursGrid.innerHTML = '';
        
        // Filtrar y convertir cada slot a la zona horaria del dispositivo del paciente
        const localSlots = [];
        if (data.slots && data.slots.length > 0) {
            data.slots.forEach(slotObj => {
                const d = new Date(slotObj.iso);
                const yr = d.getFullYear();
                const mo = String(d.getMonth() + 1).padStart(2, '0');
                const dy = String(d.getDate()).padStart(2, '0');
                const localDateStr = `${yr}-${mo}-${dy}`;
                
                if (localDateStr === dateStr) {
                    const localTimeStr = d.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit', hour12: false});
                    
                    const therapistDate = slotObj.iso.substring(0, 10);
                    const therapistHour = slotObj.iso.substring(11, 16);
                    
                    localSlots.push({
                        displayTime: localTimeStr,
                        valFecha: therapistDate,
                        valHora: therapistHour,
                        modalidades: slotObj.modalidades || ['Online']
                    });
                }
            });
        }
        
        // Ordenar las horas locales cronológicamente
        localSlots.sort((a, b) => a.displayTime.localeCompare(b.displayTime));
        
        if (localSlots.length > 0) {
            localSlots.forEach(slot => {
                const btn = document.createElement('button');
                btn.type = 'button';
                btn.className = 'btn-slot-hour';
                btn.textContent = format12h(slot.displayTime);
                
                btn.style.padding = '0.5rem 1rem';
                btn.style.border = '1.5px solid #10b981';
                btn.style.borderRadius = '20px';
                btn.style.backgroundColor = '#ecfdf5';
                btn.style.color = '#047857';
                btn.style.fontWeight = '600';
                btn.style.cursor = 'pointer';
                btn.style.transition = 'all 0.2s';
                
                btn.onclick = () => {
                    document.querySelectorAll('.btn-slot-hour').forEach(b => {
                        b.style.backgroundColor = '#ecfdf5';
                        b.style.color = '#047857';
                    });
                    btn.style.backgroundColor = '#10b981';
                    btn.style.color = 'white';
                    
                    document.getElementById('pat-req-fecha').value = slot.valFecha;
                    document.getElementById('pat-req-hora').value = slot.valHora;
                    document.getElementById('pat-submit-req-btn').disabled = false;
                    
                    // Actualizar dinámicamente las opciones de modalidad permitidas para esta hora
                    const modSelect = document.getElementById('pat-req-modalidad');
                    modSelect.innerHTML = '';
                    slot.modalidades.forEach(m => {
                        const opt = document.createElement('option');
                        opt.value = m;
                        opt.textContent = m;
                        modSelect.appendChild(opt);
                    });
                };
                
                hoursGrid.appendChild(btn);
            });
        } else {
            hoursGrid.innerHTML = '<span class="text-secondary text-sm" style="color: #ef4444; font-weight: 500;">No hay bloques horarios disponibles definidos por el psicólogo para este día de la semana.</span>';
        }
    } catch (err) {
        hoursGrid.innerHTML = '<span class="text-secondary text-sm">Error de conexión al buscar horarios.</span>';
    }
}

async function handlePatientAppointmentRequest(e) {
    e.preventDefault();
    const patientId = sessionStorage.getItem('patient_id');
    const statusMsg = document.getElementById('pat-req-status-msg');
    statusMsg.classList.add('hide');
    
    const fecha = document.getElementById('pat-req-fecha').value;
    const hora = document.getElementById('pat-req-hora').value;
    const modalidad = document.getElementById('pat-req-modalidad').value;
    const nota = document.getElementById('pat-req-nota').value;
    
    try {
        const payload = {
            fecha,
            hora,
            modalidad,
            nota
        };
        
        const res = await fetch('/api/patient/appointment', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        
        const data = await res.json();
        
        if (res.ok) {
            statusMsg.textContent = '¡Tu consulta ha sido agendada automáticamente con éxito!';
            statusMsg.className = 'status-msg success-msg';
            statusMsg.classList.remove('hide');
            
            document.getElementById('pat-appointment-request-form').reset();
            document.getElementById('pat-hours-container').classList.add('hide');
            document.getElementById('pat-submit-req-btn').disabled = true;
            
            document.querySelectorAll('.pat-cal-day-cell.selected').forEach(c => {
                c.classList.remove('selected');
                c.style.backgroundColor = '#ecfdf5';
                c.style.color = '#047857';
            });
            
            // Recargar datos y calendario
            loadPatientPortalData(patientId);
            initBookingCalendar();
        } else {
            statusMsg.textContent = data.error || 'Error al agendar la consulta.';
            statusMsg.className = 'status-msg error-msg';
            statusMsg.classList.remove('hide');
        }
    } catch (err) {
        statusMsg.textContent = 'Error de red con el servidor.';
        statusMsg.className = 'status-msg error-msg';
        statusMsg.classList.remove('hide');
    }
}

// ==========================================
// CONTROLADOR DE VISTAS Y WIZARD DEL PACIENTE
// ==========================================
function togglePatientMenu() {
    const menu = document.getElementById('patient-menu');
    const overlay = document.getElementById('patient-menu-overlay');
    
    menu.classList.toggle('open');
    overlay.classList.toggle('hide');
}

function selectPatientMenuItem(viewName) {
    // Cerrar el menú lateral
    document.getElementById('patient-menu').classList.remove('open');
    document.getElementById('patient-menu-overlay').classList.add('hide');
    
    // Cambiar la vista
    switchPatientView(viewName);
}

function switchPatientView(viewName) {
    // Ocultar todas las secciones
    document.querySelectorAll('.app-view').forEach(view => view.classList.add('hide'));
    
    // Mostrar la seleccionada
    const target = document.getElementById(`view-${viewName}`);
    if (target) target.classList.remove('hide');
    
    // Actualizar menú lateral
    document.querySelectorAll('.pat-menu-item').forEach(item => {
        if (item.getAttribute('data-pat-view') === viewName) {
            item.classList.add('active');
        } else {
            item.classList.remove('active');
        }
    });
    
    // Recargar datos actualizados al cambiar de pestaña
    const patientId = sessionStorage.getItem('patient_id');
    if (patientId && viewName !== 'patient-first-setup') {
        loadPatientPortalData(patientId);
        checkPatientActiveModulesNav();
        if (viewName === 'patient-home') {
            switchPatientHomeSubView('next');
        } else if (viewName === 'patient-diary') {
            loadPizarraHistory();
        } else if (viewName === 'patient-sleep') {
            loadPatientSleepHistory();
        } else if (viewName === 'patient-anxiety') {
            loadPatientAnxietyHistory();
        } else if (viewName === 'patient-sobriety') {
            loadPatientSobrietyHistory();
        } else if (viewName === 'patient-adherence') {
            setDefaultToolDates();
            loadPatientMedications();
            const today = document.getElementById('adh-fecha')?.value || new Date().toISOString().split('T')[0];
            loadPatientAdherenceChecklist(today);
            loadPatientAdherenceHistory();
        } else if (viewName === 'patient-activation') {
            setDefaultToolDates();
            const today = document.getElementById('act-fecha')?.value || new Date().toISOString().split('T')[0];
            loadPatientActivationChecklist(today);
            loadPatientActivationHistory();
        } else if (viewName === 'patient-ingesta') {
            setDefaultToolDates();
            loadPatientFoodIntakeHistory();
        } else if (viewName === 'patient-cognitivo') {
            setDefaultToolDates();
            loadPatientCognitiveRecordHistory();
        }
    }
}

function goToWizardStep(stepNum) {
    document.querySelectorAll('.wizard-step').forEach(step => step.classList.add('hide'));
    document.getElementById(`wizard-step-${stepNum}`).classList.remove('hide');
    
    // Actualizar indicadores visuales
    for (let i = 1; i <= 4; i++) {
        const ind = document.getElementById(`step-ind-${i}`);
        if (i < stepNum) {
            ind.className = 'setup-step completed';
        } else if (i === stepNum) {
            ind.className = 'setup-step active';
        } else {
            ind.className = 'setup-step';
        }
    }
}

function wizCalculateAge() {
    const dobStr = document.getElementById('wiz-fecha-nac').value;
    if (!dobStr) return;
    const dob = new Date(dobStr);
    const diff = Date.now() - dob.getTime();
    const ageDate = new Date(diff);
    const age = Math.abs(ageDate.getUTCFullYear() - 1970);
    document.getElementById('wiz-edad').value = age;
}

async function handlePatientWizardSubmit(e) {
    e.preventDefault();
    const statusMsg = document.getElementById('wiz-status-msg');
    statusMsg.classList.add('hide');
    
    const patientId = document.getElementById('wizard-patient-id').value;
    const username = document.getElementById('wiz-username').value;
    const new_password = document.getElementById('wiz-password').value;
    const pregunta_1 = document.getElementById('wiz-pregunta-1').value;
    const respuesta_1 = document.getElementById('wiz-respuesta-1').value;
    const pregunta_2 = document.getElementById('wiz-pregunta-2').value;
    const respuesta_2 = document.getElementById('wiz-respuesta-2').value;
    
    const payload = {
        patient_id: parseInt(patientId),
        username,
        new_password,
        pregunta_1,
        respuesta_1,
        pregunta_2,
        respuesta_2,
        pronombre: document.getElementById('wiz-pronombre').value,
        genero: document.getElementById('wiz-genero').value,
        fecha_nacimiento: document.getElementById('wiz-fecha-nac').value,
        edad: parseInt(document.getElementById('wiz-edad').value) || 0,
        lugar_nacimiento: document.getElementById('wiz-lugar-nac').value,
        residencia_actual: document.getElementById('wiz-residencia').value,
        con_quien_reside: document.getElementById('wiz-con-quien-reside').value,
        nivel_academico: document.getElementById('wiz-nivel-acad').value,
        ocupacion: document.getElementById('wiz-ocupacion').value,
        estado_civil: document.getElementById('wiz-estado-civil').value,
        telefono: document.getElementById('wiz-telefono').value,
        email: document.getElementById('wiz-email').value,
        antecedentes_medicos_personales: document.getElementById('wiz-ant-med-pers').value,
        antecedentes_medicos_familiares: document.getElementById('wiz-ant-med-fam').value,
        antecedentes_psicologicos_personales: document.getElementById('wiz-ant-psic-pers').value,
        antecedentes_psicologicos_familiares: document.getElementById('wiz-ant-psic-fam').value,
        asistencia_previa_psicologo: document.getElementById('wiz-asistencia-previa').value,
        motivo_consulta: document.getElementById('wiz-motivo-consulta').value,
        expectativas: document.getElementById('wiz-expectativas').value,
        farmacologia: document.getElementById('wiz-farmacologia').value,
        contacto_emergencia_nombre: document.getElementById('wiz-emergencia-nombre').value,
        contacto_emergencia_parentesco: document.getElementById('wiz-emergencia-parentesco').value
    };
    
    try {
        const res = await fetch('/api/patient/setup-first-login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        
        if (res.ok) {
            alert("¡Felicidades! Registro completado y cuenta configurada correctamente.");
            showPatientLayout(username, patientId);
        } else {
            statusMsg.textContent = data.error || 'Error al completar el registro.';
            statusMsg.className = 'status-msg error-msg';
            statusMsg.classList.remove('hide');
        }
    } catch (err) {
        statusMsg.textContent = 'Error de conexión con el servidor.';
        statusMsg.className = 'status-msg error-msg';
        statusMsg.classList.remove('hide');
    }
}

// Sincronización en segundo plano con Firebase para el paciente
let patDiarySaveTimeout = null;

async function loadPatientPortalData(patientId) {
    try {
        checkPatientActiveModulesNav();
        const res = await fetch(`/api/patient/portal-data`);
        if (!res.ok) return;
        const data = await res.json();
        if (!data) return;
        
        if (data.perfil) {
            window.patientProfile = data.perfil;
            if (data.perfil.psicologo_id) {
                window.currentPatientPsicologoId = data.perfil.psicologo_id;
            }
            const patientFullName = `${data.perfil.nombres} ${data.perfil.apellidos}`;
            document.getElementById('pat-welcome-title').textContent = `Hola, ${data.perfil.nombres} 👋`;
            
            // Inyectar en cabecera móvil
            const headerUserName = document.getElementById('pat-header-user-name');
            if (headerUserName) headerUserName.textContent = patientFullName;
            
            // Inyectar en cajón de menú lateral
            const menuUserName = document.getElementById('pat-menu-user-name');
            if (menuUserName) menuUserName.textContent = patientFullName;
            
            // Inyectar nombre del terapeuta asignado
            const therapistName = data.perfil.psicologo_asignado || "Psic. Paulo Mora";
            sessionStorage.setItem('patient_therapist_name', therapistName);
            
            const headerTherapist = document.getElementById('pat-header-therapist-name');
            if (headerTherapist) headerTherapist.textContent = therapistName;
            
            const menuTherapist = document.getElementById('pat-menu-therapist-name');
            if (menuTherapist) {
                menuTherapist.innerHTML = `
                    <span style="display: inline-block; width: 6px; height: 6px; background-color: var(--primary-color); border-radius: 50%;"></span>
                    <span>Terapeuta: ${therapistName}</span>
                `;
            }
            
            // Inyectar moneda configurada del paciente en el formulario de notificar pago
            const patMonedaEl = document.getElementById('pat-pay-moneda');
            if (patMonedaEl && data.perfil.moneda_personalizada) {
                patMonedaEl.value = data.perfil.moneda_personalizada;
            }
        }
        
        if (data.modalidades && data.modalidades.length > 0) {
            const selectElement = document.getElementById('pat-req-modalidad');
            if (selectElement) {
                const currentVal = selectElement.value;
                selectElement.innerHTML = '';
                data.modalidades.forEach(m => {
                    const opt = document.createElement('option');
                    opt.value = m;
                    opt.textContent = m;
                    selectElement.appendChild(opt);
                });
                if (currentVal && data.modalidades.includes(currentVal)) {
                    selectElement.value = currentVal;
                } else {
                    selectElement.value = data.modalidades[0];
                }
                if (typeof renderBookingCalendar === 'function') {
                    renderBookingCalendar();
                }
            }
        }

        if (data.metodos_pago !== undefined) {
            const instrDiv = document.getElementById('pat-pay-instructions');
            if (instrDiv) {
                instrDiv.textContent = data.metodos_pago || 'No se han definido datos de pago aún.';
            }
        }
        
        const viewTextBox = document.getElementById('pat-view-terms-text-box');
        const viewStatusBanner = document.getElementById('pat-view-terms-banner');
        const viewAcceptBtn = document.getElementById('pat-view-accept-terms-btn');
        const termsBadge = document.getElementById('pat-menu-terms-badge');

        if (viewTextBox && data.terminos_texto) {
            viewTextBox.textContent = data.terminos_texto;
        }

        if (data.terminos_requeridos) {
            if (termsBadge) {
                termsBadge.style.display = 'inline-block';
                termsBadge.textContent = '⚠️ Pendiente';
                termsBadge.style.background = 'rgba(245, 158, 11, 0.15)';
                termsBadge.style.color = '#d97706';
                termsBadge.style.border = '1px solid rgba(245, 158, 11, 0.3)';
            }
            if (viewStatusBanner) {
                viewStatusBanner.style.background = 'rgba(245, 158, 11, 0.15)';
                viewStatusBanner.style.color = '#d97706';
                viewStatusBanner.style.border = '1px solid rgba(245, 158, 11, 0.3)';
                viewStatusBanner.innerHTML = '<span>⚠️ <strong>Pendiente de Aceptación:</strong> Lee los términos atentamente antes de aceptar.</span>';
                viewStatusBanner.style.display = 'flex';
            }
            if (viewAcceptBtn) {
                viewAcceptBtn.style.display = 'block';
                viewAcceptBtn.disabled = false;
                viewAcceptBtn.textContent = '✓ He leído y acepto los Términos y Condiciones';
                viewAcceptBtn.onclick = handleAcceptPatientTerms;
            }
            if (sessionStorage.getItem('terms_redirected') !== 'true') {
                sessionStorage.setItem('terms_redirected', 'true');
                switchPatientView('patient-terms');
            }
        } else {
            const fechaAcept = data.fecha_aceptacion_terminos || 'Fecha no registrada';
            if (termsBadge) {
                termsBadge.style.display = 'none';
            }
            if (viewStatusBanner) {
                viewStatusBanner.style.background = 'rgba(16, 185, 129, 0.15)';
                viewStatusBanner.style.color = '#059669';
                viewStatusBanner.style.border = '1px solid rgba(16, 185, 129, 0.3)';
                viewStatusBanner.innerHTML = `<span> <strong>Encuadre Aceptado</strong> el: <strong>${fechaAcept}</strong></span><span style="font-size:0.85rem; font-weight:normal; background:#10b981; color:white; padding:0.2rem 0.6rem; border-radius:12px;">Encuadre Vigente</span>`;
                viewStatusBanner.style.display = 'flex';
            }
            if (viewAcceptBtn) {
                viewAcceptBtn.style.display = 'none';
            }
        }
        
        const container = document.getElementById('pat-next-sessions-container');
        if (container) {
            container.innerHTML = '';
            
            if (data.proximas_citas && data.proximas_citas.length > 0) {
                data.proximas_citas.forEach(cita => {
                    const box = document.createElement('div');
                    box.className = 'next-session-info-box';
                    box.style.background = 'linear-gradient(135deg, rgba(169, 89, 147, 0.1) 0%, rgba(93, 58, 111, 0.1) 100%)';
                    box.style.padding = '1.5rem';
                    box.style.borderRadius = 'var(--radius-md)';
                    box.style.borderLeft = '5px solid var(--primary-color)';
                    box.style.marginBottom = '1rem';
                    
                    let dateFormatted = cita.fecha;
                    try {
                        let yearObj, monthObj, dayObj;
                        if (cita.fecha.includes('-')) {
                            const dateParts = cita.fecha.split('-');
                            yearObj = parseInt(dateParts[0], 10);
                            monthObj = parseInt(dateParts[1], 10) - 1;
                            dayObj = parseInt(dateParts[2], 10);
                        } else if (cita.fecha.includes('/')) {
                            const dateParts = cita.fecha.split('/');
                            dayObj = parseInt(dateParts[0], 10);
                            monthObj = parseInt(dateParts[1], 10) - 1;
                            yearObj = parseInt(dateParts[2], 10);
                        }
                        if (yearObj && !isNaN(monthObj) && dayObj) {
                            const d = new Date(yearObj, monthObj, dayObj);
                            const options = { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' };
                            dateFormatted = d.toLocaleDateString('es-ES', options);
                            dateFormatted = dateFormatted.charAt(0).toUpperCase() + dateFormatted.slice(1);
                        }
                    } catch (e) {
                        console.error("Error formateando fecha de cita:", e);
                    }
                    
                    const userTz = getPatientUserTimeZone();
                    const convertedCita = convertTimeFromVETToZone(cita.fecha, cita.hora, userTz);
                    const timeFormatted = format12h(convertedCita.timeStr);
                    const modalityText = cita.tipo_consulta || 'Online';
                    
                    const h4 = document.createElement('h4');
                    h4.className = 'mb-2';
                    h4.style.fontWeight = '700';
                    h4.style.fontSize = '1.1rem';
                    h4.style.color = 'var(--text-dark)';
                    h4.textContent = `${dateFormatted}${convertedCita.dayOffsetStr}`;
                    box.appendChild(h4);
                    
                    const p = document.createElement('p');
                    p.className = 'text-secondary mb-2';
                    p.style.fontSize = '0.9rem';
                    p.innerHTML = `<strong>${timeFormatted}</strong> (${userTz}) — <small style="opacity: 0.85;">(${format12h(cita.hora)} hora Venezuela)</small> — Modalidad ${modalityText}`;
                    box.appendChild(p);
                    
                    const actionsDiv = document.createElement('div');
                    actionsDiv.style.display = 'flex';
                    actionsDiv.style.gap = '0.5rem';
                    actionsDiv.style.marginTop = '0.75rem';
                    actionsDiv.style.flexWrap = 'wrap';
                    
                    // Botón Confirmar
                    if (cita.confirmada === 0) {
                        const confirmBtn = document.createElement('button');
                        confirmBtn.type = 'button';
                        confirmBtn.className = 'btn btn-primary btn-sm';
                        confirmBtn.style.padding = '0.35rem 0.75rem';
                        confirmBtn.style.fontSize = '0.8rem';
                        confirmBtn.style.cursor = 'pointer';
                        confirmBtn.style.borderRadius = 'var(--radius-sm)';
                        confirmBtn.textContent = 'Confirmar Cita';
                        confirmBtn.onclick = () => handlePatientConfirmAppointment(cita.id);
                        actionsDiv.appendChild(confirmBtn);
                    } else if (cita.confirmada === 1) {
                        const confirmedBadge = document.createElement('span');
                        confirmedBadge.className = 'badge bg-success';
                        confirmedBadge.style.fontSize = '0.8rem';
                        confirmedBadge.style.padding = '0.35rem 0.75rem';
                        confirmedBadge.style.backgroundColor = '#15803d';
                        confirmedBadge.style.color = 'white';
                        confirmedBadge.style.borderRadius = 'var(--radius-sm)';
                        confirmedBadge.style.fontWeight = 'bold';
                        confirmedBadge.textContent = '✓ Confirmada';
                        actionsDiv.appendChild(confirmedBadge);
                    }
                    
                    // Botón Google Calendar
                    const therapistName = sessionStorage.getItem('patient_therapist_name') || 'Psicólogo';
                    const gcalUrl = generateGoogleCalendarUrl(`Sesión de Terapia - ${therapistName}`, `Consulta Terapéutica (${modalityText})`, cita.fecha, cita.hora, 60);
                    const gcalBtn = document.createElement('a');
                    gcalBtn.href = gcalUrl;
                    gcalBtn.target = '_blank';
                    gcalBtn.rel = 'noopener';
                    gcalBtn.className = 'btn btn-sm';
                    gcalBtn.style.padding = '0.35rem 0.75rem';
                    gcalBtn.style.fontSize = '0.8rem';
                    gcalBtn.style.backgroundColor = '#4285f4';
                    gcalBtn.style.color = 'white';
                    gcalBtn.style.borderRadius = 'var(--radius-sm)';
                    gcalBtn.style.fontWeight = '700';
                    gcalBtn.style.textDecoration = 'none';
                    gcalBtn.style.display = 'inline-flex';
                    gcalBtn.style.alignItems = 'center';
                    gcalBtn.style.gap = '4px';
                    gcalBtn.textContent = '📅 Google Calendar';
                    actionsDiv.appendChild(gcalBtn);

                    // Botón Reprogramar
                    if (cita.tiempo_restante_horas > cita.limite_cancelacion) {
                        const reschedBtn = document.createElement('button');
                        reschedBtn.type = 'button';
                        reschedBtn.className = 'btn btn-secondary btn-sm';
                        reschedBtn.style.border = '1.5px solid var(--border-color)';
                        reschedBtn.style.background = 'white';
                        reschedBtn.style.padding = '0.35rem 0.75rem';
                        reschedBtn.style.fontSize = '0.8rem';
                        reschedBtn.style.cursor = 'pointer';
                        reschedBtn.style.borderRadius = 'var(--radius-sm)';
                        reschedBtn.style.marginRight = '0.5rem';
                        reschedBtn.textContent = 'Reprogramar';
                        reschedBtn.onclick = () => openPatientRescheduleModal(cita.id, cita.fecha, cita.hora);
                        actionsDiv.appendChild(reschedBtn);
                    }
                    
                    // Botón Cancelar
                    const cancelBtn = document.createElement('button');
                    cancelBtn.type = 'button';
                    cancelBtn.className = 'btn btn-secondary btn-sm text-danger';
                    cancelBtn.style.border = '1.5px solid rgba(239, 68, 68, 0.2)';
                    cancelBtn.style.background = 'white';
                    cancelBtn.style.padding = '0.35rem 0.75rem';
                    cancelBtn.style.fontSize = '0.8rem';
                    cancelBtn.style.cursor = 'pointer';
                    cancelBtn.style.borderRadius = 'var(--radius-sm)';
                    cancelBtn.textContent = 'Cancelar Cita';
                    cancelBtn.onclick = () => handlePatientCancelAppointment(cita.id, cita.tiempo_restante_horas, cita.limite_cancelacion);
                    actionsDiv.appendChild(cancelBtn);
                    
                    box.appendChild(actionsDiv);
                    container.appendChild(box);
                });
            } else {
                container.innerHTML = `
                    <div class="next-session-info-box" style="background: var(--bg-light); padding: 1.5rem; border-radius: var(--radius-md); border-left: 5px solid var(--text-muted);">
                        <h4 class="mb-2">No tienes citas agendadas</h4>
                        <p class="text-secondary">Si lo deseas, puedes agendar una cita a continuación.</p>
                    </div>
                `;
            }
        }
        
        if (data.compartido) {
            const lastSumEl = document.getElementById('pat-last-session-summary');
            if (lastSumEl) {
                lastSumEl.textContent = data.compartido.resumen_sesion || 'Aún no se ha registrado un resumen de tu última sesión.';
            }
            document.getElementById('pat-next-topics').textContent = data.compartido.temas_proxima_sesion || 'Aún no se han definido temas para la próxima sesión.';
            
            const tasksList = document.getElementById('pat-tasks-list');
            tasksList.innerHTML = '';
            
            const tasksString = data.compartido.tareas_asignadas || '';
            const tasks = tasksString.split('\n').map(t => t.trim()).filter(t => t !== '');
            
            if (tasks.length > 0) {
                tasks.forEach((taskText, idx) => {
                    const item = document.createElement('div');
                    item.className = 'pat-task-item';
                    
                    const storageKey = `task_checked_${patientId}_${idx}`;
                    const isChecked = localStorage.getItem(storageKey) === 'true';
                    if (isChecked) item.classList.add('completed');
                    
                    item.innerHTML = `
                        <input type="checkbox" id="pat-task-${idx}" ${isChecked ? 'checked' : ''} onchange="togglePatientTask(${patientId}, ${idx}, this)">
                        <label for="pat-task-${idx}" class="pat-task-text">${taskText}</label>
                    `;
                    tasksList.appendChild(item);
                });
            } else {
                tasksList.innerHTML = '<p class="text-muted">No tienes tareas asignadas pendientes.</p>';
            }
            
            const resList = document.getElementById('pat-resources-list');
            resList.innerHTML = '';
            const resString = data.compartido.recursos_entregados || '';
            const resources = resString.split('\n').map(r => r.trim()).filter(r => r !== '');
            
            if (resources.length > 0) {
                resources.forEach(resText => {
                    const link = document.createElement('a');
                    const urlMatch = resText.match(/https?:\/\/[^\s]+/);
                    link.href = urlMatch ? urlMatch[0] : '#';
                    link.target = '_blank';
                    link.className = 'btn btn-secondary text-sm flex items-center gap-2';
                    link.style.width = '100%';
                    link.innerHTML = `
                        <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>
                        <span>${resText}</span>
                    `;
                    resList.appendChild(link);
                });
            } else {
                resList.innerHTML = '<p class="text-muted text-sm">No se han adjuntado recursos en la última sesión.</p>';
            }
        }
        
        if (data.finanzas) {
            document.getElementById('pat-prepaid-count').textContent = data.finanzas.prepagadas || 0;
            
            let debtString = '';
            const debts = data.finanzas.deuda || {};
            for (const currency in debts) {
                if (debts[currency] > 0) {
                    debtString += `${debts[currency].toFixed(2)} ${currency} | `;
                }
            }
            if (debtString.endsWith(' | ')) debtString = debtString.slice(0, -3);
            document.getElementById('pat-debt-amount').textContent = debtString || '0.00 USD';
            
            // Cargar selector de deudas activas para el formulario de Notificar Pago
            const conceptoSelect = document.getElementById('pat-pay-concepto');
            window.patientActiveDebts = data.finanzas.deudas_detalle || [];
            
            if (conceptoSelect) {
                if (window.patientActiveDebts.length > 0) {
                    conceptoSelect.value = 'deuda';
                } else {
                    conceptoSelect.value = 'consulta';
                }
                handlePatientPaymentConceptChange(conceptoSelect.value);
            }
        }
        
        // Cargar historial de notificaciones de pago
        loadPatientNotifiedPayments(patientId);
        
    } catch (err) {
        console.error("Error al cargar datos del paciente desde Firebase:", err);
    }
}

function togglePatientTask(patientId, taskIdx, checkbox) {
    const parent = checkbox.closest('.pat-task-item');
    const storageKey = `task_checked_${patientId}_${taskIdx}`;
    if (checkbox.checked) {
        parent.classList.add('completed');
        localStorage.setItem(storageKey, 'true');
    } else {
        parent.classList.remove('completed');
        localStorage.removeItem(storageKey);
    }
}

async function loadPizarraHistory() {
    const historyList = document.getElementById('pat-pizarra-history-list');
    if (!historyList) return;
    
    try {
        const res = await fetch('/api/patient/pizarra');
        const data = await res.json();
        
        historyList.innerHTML = '';
        
        if (data.updates && data.updates.length > 0) {
            data.updates.forEach(upd => {
                const thread = document.createElement('div');
                thread.className = 'pizarra-msg-card';

                const dateObj = new Date(upd.fecha.replace(/-/g, '/'));
                const dateStr = dateObj.toLocaleDateString([], {day: '2-digit', month: '2-digit', year: 'numeric'});
                const timeStr = dateObj.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'});

                // 1. Burbuja del Paciente (Tú)
                const patientBubble = document.createElement('div');
                patientBubble.className = 'chat-bubble-patient';
                
                let animoHtml = '';
                if (upd.estado_animo || upd.emoji_animo) {
                    animoHtml = `
                        <div style="font-size:0.83rem; color:var(--text-muted); margin-bottom:0.35rem; display:flex; align-items:center; gap:0.35rem;">
                            <span style="font-size:1.1rem;">${upd.emoji_animo || '😊'}</span>
                            <span>Estado de ánimo: <strong>${upd.estado_animo || ''}</strong></span>
                            ${upd.comentario_animo ? `<span style="font-style:italic;">("${upd.comentario_animo}")</span>` : ''}
                        </div>
                    `;
                }

                let fileHtml = '';
                if (upd.archivo_adjunto) {
                    const isImage = /\.(jpg|jpeg|png|gif|webp)$/i.test(upd.archivo_adjunto);
                    fileHtml = `
                        <div style="margin-top: 0.5rem; font-size: 0.8rem; padding: 0.35rem 0.6rem; border-radius: 6px; background-color: rgba(255,255,255,0.85); display: inline-flex; align-items: center; gap: 0.35rem; border: 1px solid var(--border-color);">
                            ${isImage 
                                ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width: 14px; height: 14px; color: var(--primary-color);"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>'
                                : '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width: 14px; height: 14px; color: var(--primary-color);"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>'
                            }
                            <a href="#" onclick="openFilePreview('${upd.archivo_adjunto}'); return false;" style="color: var(--primary-color); text-decoration: none; font-weight: 700;">
                                ${isImage ? 'Ver Imagen Adjunta' : 'Ver Documento Adjunto'}
                            </a>
                        </div>
                    `;
                }

                patientBubble.innerHTML = `
                    <div class="chat-bubble-header">
                        <span class="chat-author-tag patient">👤 Tu Registro</span>
                        <span class="chat-time-tag">${dateStr} ${timeStr}</span>
                    </div>
                    ${animoHtml}
                    ${upd.contenido ? `<div class="chat-bubble-body">${upd.contenido}</div>` : ''}
                    ${fileHtml}
                `;
                thread.appendChild(patientBubble);

                // 2. Burbuja del Psicólogo/a (si ya existe respuesta)
                if (upd.respuesta_psicologo) {
                    const therapistBubble = document.createElement('div');
                    therapistBubble.className = 'chat-bubble-therapist';
                    therapistBubble.innerHTML = `
                        <div class="chat-bubble-header">
                            <span class="chat-author-tag therapist">🩺 Respuesta de tu Psicólogo/a</span>
                            <span class="chat-time-tag">${upd.fecha_respuesta || ''}</span>
                        </div>
                        <div class="chat-bubble-body">${upd.respuesta_psicologo}</div>
                    `;
                    thread.appendChild(therapistBubble);
                }

                historyList.appendChild(thread);
            });
        } else {
            historyList.innerHTML = '<span class="text-secondary text-sm" style="font-style: italic;">No tienes actualizaciones registradas en tu pizarra terapéutica aún.</span>';
        }
    } catch (err) {
        historyList.innerHTML = '<span class="text-secondary text-sm" style="color: red;">Error al conectar con la pizarra terapéutica.</span>';
    }
}

let selectedMoodState = { mood: '', emoji: '' };

function selectMoodItem(btnEl, mood, emoji) {
    document.querySelectorAll('.mood-item-btn').forEach(b => {
        b.style.borderColor = 'var(--border-color)';
        b.style.backgroundColor = 'white';
        b.style.transform = 'scale(1)';
    });
    
    btnEl.style.borderColor = 'var(--primary-color)';
    btnEl.style.backgroundColor = 'rgba(169, 89, 147, 0.1)';
    btnEl.style.transform = 'scale(1.05)';
    
    selectedMoodState = { mood, emoji };
    
    const label = document.getElementById('mood-selected-label');
    if (label) {
        label.textContent = `Agregar un comentario sobre sentirte ${emoji} ${mood} (Opcional):`;
    }
    const sec = document.getElementById('mood-comment-section');
    if (sec) {
        sec.classList.remove('hide');
    }
}

async function handleSaveMoodCheckin() {
    const statusMsg = document.getElementById('pat-mood-status-msg');
    const commentInput = document.getElementById('pat-mood-comment-input');
    if (!statusMsg) return;
    statusMsg.classList.add('hide');

    if (!selectedMoodState.mood) {
        statusMsg.textContent = 'Por favor selecciona un estado de ánimo primero.';
        statusMsg.className = 'status-msg error-msg';
        statusMsg.classList.remove('hide');
        return;
    }

    const comment = commentInput ? commentInput.value.trim() : '';

    try {
        const res = await fetch('/api/patient/pizarra', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                estado_animo: selectedMoodState.mood,
                emoji_animo: selectedMoodState.emoji,
                comentario_animo: comment
            })
        });
        const data = await res.json();
        if (res.ok) {
            statusMsg.textContent = data.success || '¡Estado de ánimo registrado con éxito!';
            statusMsg.style.background = 'rgba(16, 185, 129, 0.15)';
            statusMsg.style.color = '#059669';
            statusMsg.style.border = '1px solid rgba(16, 185, 129, 0.3)';
            statusMsg.style.padding = '0.6rem 0.85rem';
            statusMsg.style.borderRadius = '8px';
            statusMsg.className = 'status-msg success-msg';
            statusMsg.classList.remove('hide');
            if (commentInput) commentInput.value = '';
            
            // Reset mood selection
            document.querySelectorAll('.mood-item-btn').forEach(b => {
                b.style.borderColor = 'var(--border-color)';
                b.style.backgroundColor = 'white';
                b.style.transform = 'scale(1)';
            });
            selectedMoodState = { mood: '', emoji: '' };
            document.getElementById('mood-comment-section')?.classList.add('hide');

            loadPatientPizarraHistory();
        } else {
            statusMsg.textContent = data.error || 'Error al guardar el estado de ánimo.';
            statusMsg.style.background = 'rgba(239, 68, 68, 0.15)';
            statusMsg.style.color = '#dc2626';
            statusMsg.style.border = '1px solid rgba(239, 68, 68, 0.3)';
            statusMsg.style.padding = '0.6rem 0.85rem';
            statusMsg.style.borderRadius = '8px';
            statusMsg.className = 'status-msg error-msg';
            statusMsg.classList.remove('hide');
        }
    } catch (err) {
        statusMsg.textContent = `Error al registrar estado de ánimo: ${err.message || 'Error de conexión'}`;
        statusMsg.style.background = 'rgba(239, 68, 68, 0.15)';
        statusMsg.style.color = '#dc2626';
        statusMsg.style.border = '1px solid rgba(239, 68, 68, 0.3)';
        statusMsg.style.padding = '0.6rem 0.85rem';
        statusMsg.style.borderRadius = '8px';
        statusMsg.className = 'status-msg error-msg';
        statusMsg.classList.remove('hide');
    }
}

async function handleSavePizarraUpdate() {
    const inputArea = document.getElementById('pat-pizarra-input');
    const fileInput = document.getElementById('pat-pizarra-file');
    const statusMsg = document.getElementById('pat-pizarra-status-msg');
    if (!inputArea || !statusMsg) return;
    
    statusMsg.classList.add('hide');
    const text = inputArea.value.trim();
    
    if (!text && (!fileInput || fileInput.files.length === 0)) {
        statusMsg.textContent = 'Por favor, escribe algún contenido o adjunta un archivo antes de guardar.';
        statusMsg.className = 'status-msg error-msg';
        statusMsg.classList.remove('hide');
        return;
    }
    
    let uploadedFilename = null;
    
    try {
        // Si hay archivo seleccionado, subirlo primero
        if (fileInput && fileInput.files.length > 0) {
            statusMsg.textContent = 'Subiendo archivo adjunto...';
            statusMsg.className = 'status-msg info-msg';
            statusMsg.classList.remove('hide');
            
            const formData = new FormData();
            formData.append('file', fileInput.files[0]);
            
            const uploadRes = await fetch('/api/upload', {
                method: 'POST',
                body: formData
            });
            
            const uploadData = await uploadRes.json();
            if (!uploadRes.ok) {
                statusMsg.textContent = uploadData.error || 'Error al subir el archivo.';
                statusMsg.className = 'status-msg error-msg';
                statusMsg.classList.remove('hide');
                return;
            }
            uploadedFilename = uploadData.filename;
        }
        
        // Guardar apunte en la pizarra
        const res = await fetch('/api/patient/pizarra', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ contenido: text, archivo_adjunto: uploadedFilename })
        });
        
        const data = await res.json();
        if (res.ok) {
            inputArea.value = '';
            if (fileInput) fileInput.value = ''; // Limpiar selector
            statusMsg.textContent = '¡Apunte guardado con éxito y compartido en tiempo real!';
            statusMsg.className = 'status-msg success-msg';
            statusMsg.classList.remove('hide');
            
            loadPizarraHistory();
            
            setTimeout(() => {
                statusMsg.classList.add('hide');
            }, 3000);
        } else {
            statusMsg.textContent = data.error || 'Error al guardar la actualización.';
            statusMsg.className = 'status-msg error-msg';
            statusMsg.classList.remove('hide');
        }
    } catch (err) {
        statusMsg.textContent = 'Error de conexión con el servidor.';
        statusMsg.className = 'status-msg error-msg';
        statusMsg.classList.remove('hide');
    }
}

async function loadPizarraPatients() {
    const filterSelect = document.getElementById('pizarra-patient-filter');
    if (!filterSelect) return;
    
    try {
        const res = await fetch('/api/patients');
        const patients = await res.json();
        
        filterSelect.innerHTML = '<option value="">-- Todos los Pacientes --</option>';
        
        patients.forEach(pat => {
            const opt = document.createElement('option');
            opt.value = pat.id;
            opt.textContent = `${pat.nombres} ${pat.apellidos} (${pat.cedula})`;
            filterSelect.appendChild(opt);
        });
    } catch (err) {
        console.error("Error al cargar pacientes para filtro de pizarra:", err);
    }
}

let currentPizarraUpdates = [];
let currentPizarraPage = 1;
const PIZARRA_PER_PAGE = 6;

async function loadPizarraVisual() {
    const grid = document.getElementById('pizarra-updates-grid');
    if (!grid) return;
    
    grid.innerHTML = '<span class="text-secondary text-sm">Cargando pizarra visual...</span>';
    
    const filterSelect = document.getElementById('pizarra-patient-filter');
    const patientId = filterSelect ? filterSelect.value : '';
    
    try {
        const url = patientId ? `/api/admin/pizarra?patient_id=${patientId}` : '/api/admin/pizarra';
        const res = await fetch(url);
        const data = await res.json();
        
        currentPizarraUpdates = data.updates || [];
        currentPizarraPage = 1;
        renderPizarraVisual();
    } catch (err) {
        grid.innerHTML = '<span class="text-secondary text-sm" style="color: red;">Error de conexión al cargar la pizarra visual.</span>';
    }
}

function renderPizarraVisual() {
    const grid = document.getElementById('pizarra-updates-grid');
    if (!grid) return;

    grid.innerHTML = '';

    if (currentPizarraUpdates.length === 0) {
        grid.innerHTML = `
            <div style="grid-column: 1 / -1; text-align: center; padding: 3rem; background: var(--bg-light); border-radius: var(--radius-md); border: 1.5px dashed var(--border-color);">
                <p class="text-secondary" style="font-style: italic;">No hay actualizaciones registradas en la pizarra terapéutica para los criterios seleccionados.</p>
            </div>
        `;
        renderPizarraPaginationControls(0, 1);
        return;
    }

    const totalPages = Math.ceil(currentPizarraUpdates.length / PIZARRA_PER_PAGE);
    if (currentPizarraPage > totalPages) currentPizarraPage = totalPages;
    if (currentPizarraPage < 1) currentPizarraPage = 1;

    const start = (currentPizarraPage - 1) * PIZARRA_PER_PAGE;
    const pageRecords = currentPizarraUpdates.slice(start, start + PIZARRA_PER_PAGE);

    pageRecords.forEach((upd, index) => {
        const card = document.createElement('div');
        card.className = 'pizarra-update-card';
        card.style.border = '1px solid var(--border-color)';
        card.style.borderRadius = 'var(--radius-md)';
        card.style.padding = '1.25rem';
        card.style.backgroundColor = 'var(--card-bg)';
        card.style.boxShadow = '0 4px 15px rgba(0, 0, 0, 0.02)';
        card.style.position = 'relative';
        
        const colors = [
            'rgba(169, 89, 147, 0.04)',
            'rgba(16, 185, 129, 0.04)',
            'rgba(59, 130, 246, 0.04)',
            'rgba(245, 158, 11, 0.04)'
        ];
        card.style.borderLeft = `5px solid ${['var(--primary-color)', '#10b981', '#3b82f6', '#f59e0b'][index % 4]}`;
        card.style.backgroundColor = colors[index % 4];
        
        const header = document.createElement('div');
        header.style.display = 'flex';
        header.style.justifyContent = 'space-between';
        header.style.alignItems = 'flex-start';
        header.style.marginBottom = '0.75rem';
        header.style.borderBottom = '1px solid rgba(0,0,0,0.04)';
        header.style.paddingBottom = '0.5rem';
        
        const userPart = document.createElement('div');
        userPart.style.display = 'flex';
        userPart.style.flexDirection = 'column';
        
        const nameSpan = document.createElement('span');
        nameSpan.style.fontWeight = '700';
        nameSpan.style.color = 'var(--text-dark)';
        nameSpan.style.fontSize = '0.95rem';
        nameSpan.textContent = upd.paciente_nombre;
        
        const roleSpan = document.createElement('span');
        roleSpan.style.fontSize = '0.75rem';
        roleSpan.style.color = 'var(--text-muted)';
        roleSpan.textContent = 'Paciente';
        
        userPart.appendChild(nameSpan);
        userPart.appendChild(roleSpan);
        
        const dateObj = new Date(upd.fecha.replace(/-/g, '/'));
        const dateSpan = document.createElement('span');
        dateSpan.style.fontSize = '0.75rem';
        dateSpan.style.color = 'var(--text-muted)';
        dateSpan.textContent = isNaN(dateObj.getTime()) ? upd.fecha : dateObj.toLocaleString('es-ES', { dateStyle: 'short', timeStyle: 'short' });
        
        header.appendChild(userPart);
        header.appendChild(dateSpan);
        card.appendChild(header);
        
        const body = document.createElement('div');
        body.style.fontSize = '0.9rem';
        body.style.lineHeight = '1.5';
        body.style.color = 'var(--text-dark)';
        
        if (upd.tipo === 'emocion') {
            body.innerHTML = `<strong>Estado de ánimo:</strong> ${upd.contenido}`;
        } else {
            body.textContent = upd.contenido;
        }
        if (upd.contenido) {
            card.appendChild(body);
        }
        
        if (upd.archivo_adjunto) {
            const fileDiv = document.createElement('div');
            fileDiv.style.marginTop = '0.5rem';
            fileDiv.style.fontSize = '0.8rem';
            fileDiv.style.padding = '0.35rem 0.5rem';
            fileDiv.style.borderRadius = '4px';
            fileDiv.style.backgroundColor = 'rgba(255, 255, 255, 0.6)';
            fileDiv.style.display = 'inline-flex';
            fileDiv.style.alignItems = 'center';
            fileDiv.style.gap = '0.35rem';
            fileDiv.style.border = '1px solid var(--border-color)';
            
            const isImage = /\.(jpg|jpeg|png|gif|webp)$/i.test(upd.archivo_adjunto);
            if (isImage) {
                fileDiv.innerHTML = `
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width: 14px; height: 14px; color: var(--primary-color);"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>
                    <a href="#" onclick="openFilePreview('${upd.archivo_adjunto}'); return false;" style="color: var(--primary-color); text-decoration: none; font-weight: 700;">Ver Imagen Adjunta</a>
                `;
            } else {
                fileDiv.innerHTML = `
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width: 14px; height: 14px; color: var(--primary-color);"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                    <a href="#" onclick="openFilePreview('${upd.archivo_adjunto}'); return false;" style="color: var(--primary-color); text-decoration: none; font-weight: 700;">Ver Documento Adjunto</a>
                `;
            }
            card.appendChild(fileDiv);
        }

        if (upd.respuesta_psicologo) {
            const respDiv = document.createElement('div');
            respDiv.style.marginTop = '0.75rem';
            respDiv.style.padding = '0.65rem 0.85rem';
            respDiv.style.borderRadius = 'var(--radius-sm)';
            respDiv.style.backgroundColor = 'rgba(126, 34, 206, 0.06)';
            respDiv.style.borderLeft = '3px solid var(--primary-color)';
            respDiv.innerHTML = `
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.25rem;">
                    <strong style="font-size:0.82rem; color:var(--primary-color);">💬 Tu Respuesta:</strong>
                    <span style="font-size:0.72rem; color:var(--text-muted);">${upd.fecha_respuesta || ''}</span>
                </div>
                <div style="font-size:0.85rem; color:var(--text-dark); line-height:1.4;">${upd.respuesta_psicologo}</div>
            `;
            card.appendChild(respDiv);
        }
        
        const replyContainer = document.createElement('div');
        replyContainer.style.marginTop = '1rem';
        replyContainer.style.borderTop = '1px dashed rgba(0,0,0,0.06)';
        replyContainer.style.paddingTop = '0.75rem';
        
        replyContainer.innerHTML = `
            <div style="display: flex; gap: 0.5rem; align-items: center;">
                <input type="text" placeholder="${upd.respuesta_psicologo ? 'Enviar nueva respuesta...' : 'Escribe un comentario o respuesta...'}" style="flex: 1; padding: 0.4rem 0.6rem; border-radius: var(--radius-sm); border: 1.5px solid var(--border-color); font-size: 0.8rem; background-color: var(--card-bg);" id="reply-input-${upd.id}">
                <button type="button" class="btn btn-primary btn-sm" style="padding: 0.4rem 0.8rem; font-size: 0.8rem; cursor: pointer; border-radius: var(--radius-sm);" onclick="submitPizarraReply(${upd.paciente_id}, ${upd.id})">${upd.respuesta_psicologo ? 'Actualizar' : 'Enviar'}</button>
            </div>
        `;
        card.appendChild(replyContainer);
        
        grid.appendChild(card);
    });

    renderPizarraPaginationControls(currentPizarraUpdates.length, totalPages);
}

function renderPizarraPaginationControls(totalRecords, totalPages) {
    let container = document.getElementById('pizarra-pagination-controls');
    if (!container) return;

    if (totalRecords === 0 || totalPages <= 1) {
        container.innerHTML = '';
        return;
    }

    container.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: center; padding: 0.65rem 0.85rem; background: white; border: 1.5px solid var(--border-color); border-radius: 8px; margin-top: 0.75rem; flex-wrap: wrap; gap: 0.5rem;">
            <button type="button" class="btn btn-sm btn-outline-secondary" onclick="changePizarraPage(${currentPizarraPage - 1})" ${currentPizarraPage <= 1 ? 'disabled' : ''} style="font-weight: 700; padding: 0.3rem 0.75rem;">
                ◀️ Tarjetas Anteriores
            </button>
            <span style="font-size: 0.85rem; font-weight: 700; color: var(--text-dark);">
                Página ${currentPizarraPage} de ${totalPages} (${totalRecords} publicaciones)
            </span>
            <button type="button" class="btn btn-sm btn-outline-secondary" onclick="changePizarraPage(${currentPizarraPage + 1})" ${currentPizarraPage >= totalPages ? 'disabled' : ''} style="font-weight: 700; padding: 0.3rem 0.75rem;">
                Tarjetas Siguientes ▶️
            </button>
        </div>
    `;
}

function changePizarraPage(newPage) {
    currentPizarraPage = newPage;
    renderPizarraVisual();
}
window.changePizarraPage = changePizarraPage;

async function handlePatientPaymentSubmit(e) {
    e.preventDefault();
    const patientId = sessionStorage.getItem('patient_id');
    const statusMsg = document.getElementById('pat-pay-status-msg');
    statusMsg.classList.add('hide');
    
    const monto = parseFloat(document.getElementById('pat-pay-monto').value);
    const moneda = document.getElementById('pat-pay-moneda').value;
    const metodo = document.getElementById('pat-pay-metodo').value;
    const referencia = document.getElementById('pat-pay-referencia').value;
    const fecha = document.getElementById('pat-pay-fecha').value;
    
    try {
        const paymentPayload = {
            monto,
            moneda,
            metodo,
            referencia,
            fecha
        };
        
        const res = await fetch('/api/patient/payment', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(paymentPayload)
        });
        
        const data = await res.json();
        
        if (res.ok && !data.error) {
            statusMsg.textContent = '¡Pago notificado con éxito! Su psicólogo lo verificará pronto.';
            statusMsg.className = 'status-msg success-msg';
            statusMsg.classList.remove('hide');
            document.getElementById('pat-payment-form').reset();
            loadPatientPortalData(patientId);
        } else {
            statusMsg.textContent = data.error || 'Error al notificar el pago.';
            statusMsg.className = 'status-msg error-msg';
            statusMsg.classList.remove('hide');
        }
    } catch (err) {
        statusMsg.textContent = 'Error de conexión con el servidor.';
        statusMsg.className = 'status-msg error-msg';
        statusMsg.classList.remove('hide');
    }
}

async function handlePatientChangePwSubmit(e) {
    e.preventDefault();
    const statusMsg = document.getElementById('pat-pw-status-msg');
    statusMsg.classList.add('hide');
    
    const current_password = document.getElementById('pat-pw-current').value;
    const new_password = document.getElementById('pat-pw-new').value;
    const confirm_password = document.getElementById('pat-pw-confirm') ? document.getElementById('pat-pw-confirm').value : null;
    
    if (confirm_password && new_password !== confirm_password) {
        statusMsg.textContent = '❌ La nueva contraseña y la confirmación no coinciden.';
        statusMsg.className = 'status-msg error-msg';
        statusMsg.classList.remove('hide');
        return;
    }
    
    try {
        const res = await fetch('/api/patient/change-password', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ current_password, new_password, confirm_password })
        });
        const data = await res.json();
        
        if (res.ok) {
            statusMsg.textContent = '✅ Contraseña actualizada con éxito.';
            statusMsg.className = 'status-msg success-msg';
            statusMsg.classList.remove('hide');
            document.getElementById('pat-change-pw-form').reset();
        } else {
            statusMsg.textContent = '❌ ' + (data.error || 'Error al actualizar contraseña.');
            statusMsg.className = 'status-msg error-msg';
            statusMsg.classList.remove('hide');
        }
    } catch (err) {
        statusMsg.textContent = '❌ Error de red con el servidor.';
        statusMsg.className = 'status-msg error-msg';
        statusMsg.classList.remove('hide');
    }
}

// ==========================================
// GESTIÓN DE PACIENTES
// ==========================================
async function loadPatients() {
    try {
        const res = await fetch('/api/patients');
        patients = await res.json();
        renderPatientsTable(patients);
    } catch (err) {
        console.error("Error al cargar pacientes:", err);
    }
}

let currentPatientsPage = 1;
const PATIENTS_PER_PAGE = 6;

function renderPatientsTable(list) {
    const tbody = document.getElementById('patients-table-body');
    if (!tbody) return;
    tbody.innerHTML = '';
    
    const input = document.getElementById('patient-table-search-input');
    const query = input ? input.value.toLowerCase().trim() : '';

    const filtered = (list || []).filter(p => {
        if (!query) return true;
        const fullText = `${p.cedula || ''} ${p.nombres || ''} ${p.apellidos || ''} ${p.residencia_actual || ''}`.toLowerCase();
        return fullText.includes(query);
    });

    const counter = document.getElementById('patient-search-counter');
    if (counter) {
        counter.textContent = query ? `${filtered.length} coincidencia(s)` : `${filtered.length} consultantes`;
    }

    if (filtered.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="text-center py-3 text-secondary">No se encontraron consultantes.</td></tr>';
        renderPatientsPaginationControls(0, 1);
        return;
    }

    const totalPages = Math.ceil(filtered.length / PATIENTS_PER_PAGE);
    if (currentPatientsPage > totalPages) currentPatientsPage = totalPages;
    if (currentPatientsPage < 1) currentPatientsPage = 1;

    const start = (currentPatientsPage - 1) * PATIENTS_PER_PAGE;
    const pageRecords = filtered.slice(start, start + PATIENTS_PER_PAGE);

    pageRecords.forEach(p => {
        const tr = document.createElement('tr');
        const loc = typeof formatPatientLocation === 'function' ? formatPatientLocation(p) : (p.residencia_actual || 'N/A');
        tr.innerHTML = `
            <td><strong>${p.cedula || 'N/A'}</strong></td>
            <td>${p.nombres || ''} ${p.apellidos || ''}</td>
            <td>${p.edad || 'N/A'}</td>
            <td>${p.genero || 'N/A'}</td>
            <td>${loc}</td>
            <td class="actions-cell">
                <button class="btn btn-secondary btn-sm" onclick="openSummaryModal(${p.id})">Ficha Resumen</button>
                <button class="btn btn-primary btn-sm" onclick="openEditPatientModal(${p.id})">Editar</button>
            </td>
        `;
        tbody.appendChild(tr);
    });

    renderPatientsPaginationControls(filtered.length, totalPages);
}

function renderPatientsPaginationControls(totalRecords, totalPages) {
    let container = document.getElementById('patients-pagination-controls');
    if (!container) return;

    if (totalRecords === 0 || totalPages <= 1) {
        container.innerHTML = '';
        return;
    }

    container.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: center; padding: 0.65rem 0.85rem; background: white; border: 1.5px solid var(--border-color); border-radius: 8px; margin-top: 0.75rem; flex-wrap: wrap; gap: 0.5rem;">
            <button type="button" class="btn btn-sm btn-outline-secondary" onclick="changePatientsPage(${currentPatientsPage - 1})" ${currentPatientsPage <= 1 ? 'disabled' : ''} style="font-weight: 700; padding: 0.3rem 0.75rem;">
                ◀️ Anterior
            </button>
            <span style="font-size: 0.85rem; font-weight: 700; color: var(--text-dark);">
                Página ${currentPatientsPage} de ${totalPages} (${totalRecords} consultantes)
            </span>
            <button type="button" class="btn btn-sm btn-outline-secondary" onclick="changePatientsPage(${currentPatientsPage + 1})" ${currentPatientsPage >= totalPages ? 'disabled' : ''} style="font-weight: 700; padding: 0.3rem 0.75rem;">
                Siguiente ▶️
            </button>
        </div>
    `;
}

function changePatientsPage(newPage) {
    currentPatientsPage = newPage;
    renderPatientsTable(patients);
}

function filterPatientsTableByInput() {
    currentPatientsPage = 1;
    renderPatientsTable(patients);
}

window.changePatientsPage = changePatientsPage;

async function checkCedulaAutoFill() {
    const isNew = !document.getElementById('patient-form-id').value;
    if (!isNew) return;
    const cedulaInput = document.getElementById('p-cedula');
    if (!cedulaInput) return;
    const cedula = cedulaInput.value.trim();
    if (cedula.length < 4) return;
    
    try {
        const res = await fetch(`/api/pacientes/buscar_cedula/${encodeURIComponent(cedula)}`);
        if (!res.ok) return;
        const data = await res.json();
        if (data.found && data.paciente) {
            const p = data.paciente;
            if (!document.getElementById('p-nombres').value) document.getElementById('p-nombres').value = p.nombres || '';
            if (!document.getElementById('p-apellidos').value) document.getElementById('p-apellidos').value = p.apellidos || '';
            if (!document.getElementById('p-edad').value) document.getElementById('p-edad').value = p.edad || '';
            if (!document.getElementById('p-genero').value) document.getElementById('p-genero').value = p.genero || '';
            if (!document.getElementById('p-pronombre').value) document.getElementById('p-pronombre').value = p.pronombre || '';
            if (!document.getElementById('p-fecha-nac').value) document.getElementById('p-fecha-nac').value = p.fecha_nacimiento || '';
            if (!document.getElementById('p-lugar-nac').value) document.getElementById('p-lugar-nac').value = p.lugar_nacimiento || '';
            if (document.getElementById('p-pais') && !document.getElementById('p-pais').value) document.getElementById('p-pais').value = p.pais || '';
            if (document.getElementById('p-ciudad') && !document.getElementById('p-ciudad').value) document.getElementById('p-ciudad').value = p.ciudad || '';
            if (!document.getElementById('p-con-quien').value) document.getElementById('p-con-quien').value = p.con_quien_reside || '';
            if (!document.getElementById('p-telefono').value) document.getElementById('p-telefono').value = p.telefono || '';
            if (!document.getElementById('p-email').value) document.getElementById('p-email').value = p.email || '';
            if (!document.getElementById('p-academico').value) document.getElementById('p-academico').value = p.nivel_academico || '';
            if (!document.getElementById('p-ocupacion').value) document.getElementById('p-ocupacion').value = p.ocupacion || '';
            if (!document.getElementById('p-civil').value) document.getElementById('p-civil').value = p.estado_civil || '';
            
            if (window.Swal) {
                Swal.fire({
                    toast: true,
                    position: 'top-end',
                    icon: 'info',
                    title: 'Datos personales encontrados',
                    text: 'Se autocompletó la información personal desde el registro del sistema.',
                    showConfirmButton: false,
                    timer: 4000,
                    timerProgressBar: true
                });
            }
        }
    } catch(e) {
        console.error("Error al autocompletar datos por cédula:", e);
    }
}

function openNewPatientModal() {
    if (typeof isFeatureBlocked === 'function' && isFeatureBlocked('registro')) {
        alert("La función de Registro de Pacientes está suspendida por administración.");
        return;
    }

    // Actualizar destacado en menú lateral
    document.querySelectorAll('.nav-item').forEach(item => item.classList.remove('active'));
    const activeItem = document.querySelector('.nav-item[data-view="register-patient"]');
    if (activeItem) activeItem.classList.add('active');

    // Cerrar menú móvil si está abierto
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('sidebar-overlay');
    if (sidebar) sidebar.classList.remove('open');
    if (overlay) overlay.classList.add('hide');

    const form = document.getElementById('patient-form');
    if (form) form.reset();
    const formId = document.getElementById('patient-form-id');
    if (formId) formId.value = '';
    const pkgCheck = document.getElementById('p-ofrecer-paquete-personalizado');
    if (pkgCheck) pkgCheck.checked = false;
    const pkgCost = document.getElementById('p-costo-paquete-personalizado');
    if (pkgCost) pkgCost.value = '';
    const pkgSess = document.getElementById('p-sesiones-paquete-personalizado');
    if (pkgSess) pkgSess.value = '';
    
    if (typeof togglePatientPkgInputs === 'function') togglePatientPkgInputs();
    
    const title = document.getElementById('patient-modal-title');
    if (title) title.textContent = "Nueva Historia Clínica";
    
    if (typeof switchFormTab === 'function') switchFormTab(null, 'tab-personal');
    
    openModal('patient-modal');
}

async function openEditPatientModal(patientId) {
    try {
        const res = await fetch(`/api/patients/${patientId}`);
        if (!res.ok) throw new Error("Paciente no encontrado");
        const p = await res.json();
        
        document.getElementById('patient-form-id').value = p.id;
        document.getElementById('p-nombres').value = p.nombres;
        document.getElementById('p-apellidos').value = p.apellidos;
        document.getElementById('p-cedula').value = p.cedula;
        document.getElementById('p-edad').value = p.edad || '';
        document.getElementById('p-genero').value = p.genero || '';
        document.getElementById('p-pronombre').value = p.pronombre || '';
        document.getElementById('p-fecha-nac').value = p.fecha_nacimiento || '';
        document.getElementById('p-lugar-nac').value = p.lugar_nacimiento || '';
        if (document.getElementById('p-pais')) document.getElementById('p-pais').value = p.pais || '';
        if (document.getElementById('p-ciudad')) document.getElementById('p-ciudad').value = p.ciudad || '';
        document.getElementById('p-con-quien').value = p.con_quien_reside || '';
        document.getElementById('p-telefono').value = p.telefono || '';
        document.getElementById('p-email').value = p.email || '';
        document.getElementById('p-academico').value = p.nivel_academico || '';
        document.getElementById('p-ocupacion').value = p.ocupacion || '';
        document.getElementById('p-civil').value = p.estado_civil || '';
        
        document.getElementById('p-ant-med-pers').value = p.antecedentes_medicos_personales || '';
        document.getElementById('p-ant-med-fam').value = p.antecedentes_medicos_familiares || '';
        document.getElementById('p-ant-psic-pers').value = p.antecedentes_psicologicos_personales || '';
        document.getElementById('p-ant-psic-fam').value = p.antecedentes_psicologicos_familiares || '';
        document.getElementById('p-asistencia-prev').value = p.asistencia_previa_psicologo || '';
        document.getElementById('p-expectativas').value = p.expectativas || '';
        document.getElementById('p-motivo').value = p.motivo_consulta || '';
        document.getElementById('p-farmacologia').value = p.farmacologia || '';
        
        document.getElementById('p-emergencia-nom').value = p.contacto_emergencia_nombre || '';
        document.getElementById('p-emergencia-par').value = p.contacto_emergencia_parentesco || '';
        document.getElementById('p-diagnostico').value = p.diagnostico || '';
        
        document.getElementById('p-costo-personalizado').value = (p.costo_personalizado !== null && p.costo_personalizado !== undefined) ? p.costo_personalizado : '';
        document.getElementById('p-moneda-personalizada').value = p.moneda_personalizada || 'USD';
        
        const hasPkg = (p.costo_paquete_personalizado !== null && p.costo_paquete_personalizado !== undefined);
        document.getElementById('p-ofrecer-paquete-personalizado').checked = hasPkg;
        document.getElementById('p-costo-paquete-personalizado').value = hasPkg ? p.costo_paquete_personalizado : '';
        document.getElementById('p-sesiones-paquete-personalizado').value = hasPkg ? p.sesiones_paquete_personalizado : '';
        togglePatientPkgInputs();
        
        document.getElementById('patient-modal-title').textContent = "Editar Historia Clínica";
        closeModal('summary-modal');
        switchFormTab(null, 'tab-personal');
        openModal('patient-modal');
    } catch (err) {
        alert(err.message);
    }
}

async function handlePatientSubmit(e) {
    e.preventDefault();
    if (!confirm("¿Está seguro de guardar los cambios en esta Historia Clínica?")) {
        return;
    }
    const id = document.getElementById('patient-form-id').value;
    const payload = {
        nombres: document.getElementById('p-nombres').value,
        apellidos: document.getElementById('p-apellidos').value,
        cedula: document.getElementById('p-cedula').value,
        edad: document.getElementById('p-edad').value,
        genero: document.getElementById('p-genero').value,
        pronombre: document.getElementById('p-pronombre').value,
        fecha_nacimiento: document.getElementById('p-fecha-nac').value,
        lugar_nacimiento: document.getElementById('p-lugar-nac').value,
        pais: document.getElementById('p-pais')?.value || '',
        ciudad: document.getElementById('p-ciudad')?.value || '',
        con_quien_reside: document.getElementById('p-con-quien').value,
        telefono: document.getElementById('p-telefono').value,
        email: document.getElementById('p-email').value,
        nivel_academico: document.getElementById('p-academico').value,
        ocupacion: document.getElementById('p-ocupacion').value,
        estado_civil: document.getElementById('p-civil').value,
        
        antecedentes_medicos_personales: document.getElementById('p-ant-med-pers').value,
        antecedentes_medicos_familiares: document.getElementById('p-ant-med-fam').value,
        antecedentes_psicologicos_personales: document.getElementById('p-ant-psic-pers').value,
        antecedentes_psicologicos_familiares: document.getElementById('p-ant-psic-fam').value,
        asistencia_previa_psicologo: document.getElementById('p-asistencia-prev').value,
        expectativas: document.getElementById('p-expectativas').value,
        motivo_consulta: document.getElementById('p-motivo').value,
        farmacologia: document.getElementById('p-farmacologia').value,
        
        contacto_emergencia_nombre: document.getElementById('p-emergencia-nom').value,
        contacto_emergencia_parentesco: document.getElementById('p-emergencia-par').value,
        diagnostico: document.getElementById('p-diagnostico').value,
        
        costo_personalizado: document.getElementById('p-costo-personalizado').value,
        moneda_personalizada: document.getElementById('p-moneda-personalizada').value,
        costo_paquete_personalizado: document.getElementById('p-ofrecer-paquete-personalizado').checked ? document.getElementById('p-costo-paquete-personalizado').value : '',
        sesiones_paquete_personalizado: document.getElementById('p-ofrecer-paquete-personalizado').checked ? document.getElementById('p-sesiones-paquete-personalizado').value : ''
    };
    
    const method = id ? 'PUT' : 'POST';
    const endpoint = id ? `/api/patients/${id}` : '/api/patients';
    
    try {
        const res = await fetch(endpoint, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        
        if (res.ok) {
            alert(data.success);
            closeModal('patient-modal');
            loadPatients();
            if (activeView === 'dashboard') {
                loadDashboardStats();
            }
        } else {
            alert(data.error);
        }
    } catch (err) {
        alert("Error de conexión al guardar el expediente.");
    }
}

async function deletePatient(patientId) {
    if (!confirm("¿Está seguro de que desea eliminar permanentemente este paciente y toda su información clínica/evoluciones y registros de pago? Esta acción no se puede deshacer.")) return;
    
    try {
        const res = await fetch(`/api/patients/${patientId}`, { method: 'DELETE' });
        const data = await res.json();
        if (res.ok) {
            alert(data.success);
            closeModal('summary-modal');
            loadPatients();
            if (activeView === 'dashboard') {
                loadDashboardStats();
            }
        } else {
            alert(data.error);
        }
    } catch (err) {
        alert("Error al eliminar paciente.");
    }
}

function switchFormTab(e, tabId) {
    // Esconder contenidos de pestañas
    document.querySelectorAll('.form-tab-content').forEach(c => c.classList.add('hide'));
    // Desactivar botones de pestaña
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    
    // Mostrar pestaña seleccionada
    document.getElementById(tabId).classList.remove('hide');
    
    if (e) {
        e.target.classList.add('active');
    } else {
        // Encontrar por id
        const firstTab = document.querySelector(`.tab-btn[onclick*="${tabId}"]`);
        if (firstTab) firstTab.classList.add('active');
    }
}

// ==========================================
// BUSCADOR INSTANTÁNEO DE CONSULTANTES
// ==========================================
async function handleGlobalSearch(query) {
    const dropdown = document.getElementById('search-results-dropdown');
    if (!query.trim()) {
        dropdown.classList.add('hide');
        return;
    }
    
    try {
        const res = await fetch(`/api/patients?search=${encodeURIComponent(query)}`);
        const results = await res.json();
        
        dropdown.innerHTML = '';
        
        if (results.length === 0) {
            dropdown.innerHTML = '<div class="search-result-item" style="cursor:default;"><span class="text-secondary">Sin resultados</span></div>';
        } else {
            results.forEach(p => {
                const item = document.createElement('div');
                item.className = 'search-result-item';
                item.innerHTML = `
                    <div class="search-result-info">
                        <span class="search-result-name">${p.nombres} ${p.apellidos}</span>
                        <span class="search-result-cedula">Cédula: ${p.cedula}</span>
                    </div>
                    <span class="badge badge-secondary">${p.genero || 'N/A'}</span>
                `;
                item.onclick = () => {
                    dropdown.classList.add('hide');
                    document.getElementById('global-search').value = '';
                    openSummaryModal(p.id);
                };
                dropdown.appendChild(item);
            });
        }
        dropdown.classList.remove('hide');
    } catch (err) {
        console.error("Error en búsqueda:", err);
    }
}

// Cerrar el buscador al hacer click fuera
document.addEventListener('click', (e) => {
    const container = document.querySelector('.search-container');
    if (container && !container.contains(e.target)) {
        document.getElementById('search-results-dropdown').classList.add('hide');
    }
});

// ==========================================
// LA "FICHA RESUMEN" DEL PACIENTE
// ==========================================
async function openSummaryModal(patientId) {
    try {
        const res = await fetch(`/api/patients/${patientId}/summary`);
        if (!res.ok) throw new Error("Ficha de paciente no encontrada.");
        const summary = await res.json();
        
        const container = document.getElementById('summary-modal-content');
        const p = summary.patient;
        const lastSes = summary.last_session;
        const fin = summary.finance;
        
        container.innerHTML = `
            <div class="summary-grid-2">
                <!-- Columna Izquierda: Datos Personales -->
                <div>
                    <h4 class="summary-block-title">Datos Clínicos Básicos</h4>
                    <ul class="summary-details-list">
                        <li><strong>Código Consultante:</strong> #P-${p.id}</li>
                        <li><strong>Cédula:</strong> ${p.cedula}</li>
                        <li><strong>Nombre Completo:</strong> ${p.nombres} ${p.apellidos}</li>
                        <li><strong>Teléfono:</strong> ${p.telefono || 'N/A'} ${p.telefono ? `<a href="${getWhatsAppLink(p.telefono, `Hola ${p.nombres}, te escribimos de Mi Consultorio.`)}" target="_blank" style="margin-left:0.5rem; text-decoration:none; font-size:0.75rem; background:#25D366; color:white; padding:0.15rem 0.45rem; border-radius:4px; font-weight:600; display:inline-flex; align-items:center; gap:0.2rem;">💬 WhatsApp</a>` : ''}</li>
                        <li><strong>Correo:</strong> ${p.email || 'N/A'}</li>
                        <li><strong>Género / Pronombre:</strong> ${p.genero || 'N/A'} / ${p.pronombre || 'N/A'}</li>
                        <li><strong>Edad:</strong> ${p.edad || 'N/A'} años</li>
                        <li><strong>Residencia:</strong> ${formatPatientLocation(p)}</li>
                        <li style="border-top:1px dashed var(--border-color); padding-top:0.4rem; margin-top:0.4rem; color:var(--primary-color); display: flex; justify-content: space-between; align-items: center;">
                            <div>
                                <strong>Honorario Personalizado:</strong> ${p.costo_personalizado ? `${p.costo_personalizado} ${p.moneda_personalizada}` : 'Tarifa estándar'}
                            </div>
                            <button type="button" class="btn btn-secondary btn-sm" onclick="editPatientRates(${p.id})" style="padding: 0.15rem 0.4rem; font-size: 0.72rem; border-radius: var(--radius-sm); cursor: pointer; border: 1.5px solid var(--border-color); background: white;">✏️ Configurar</button>
                        </li>
                        <li style="color:var(--primary-color);"><strong>Paquete Personalizado:</strong> ${p.costo_paquete_personalizado ? `${p.costo_paquete_personalizado} ${p.moneda_personalizada} (${p.sesiones_paquete_personalizado} sesiones)` : 'Paquete estándar'}</li>
                    </ul>
                    
                    <h4 class="summary-block-title mt-6">Impresión Diagnóstica</h4>
                    <p class="text-secondary" style="font-size:0.9rem; line-height:1.4;">
                        ${p.diagnostico ? p.diagnostico.replace(/\n/g, '<br>') : '<em>Sin impresión diagnóstica registrada aún.</em>'}
                    </p>
                </div>
                
                <!-- Columna Derecha: Finanzas y Última Sesión -->
                <div>
                    <h4 class="summary-block-title">Saldo & Cuentas (Sesiones)</h4>
                    <div class="summary-finance-dashboard mb-3">
                        <div class="sum-fin-stat">
                            <span class="sum-fin-num text-success">${fin.pagas}</span>
                            <span class="sum-fin-label">Pagas</span>
                        </div>
                        <div class="sum-fin-stat payable">
                            <span class="sum-fin-num text-danger">${fin.pendientes}</span>
                            <span class="sum-fin-label">Pendientes</span>
                        </div>
                        <div class="sum-fin-stat">
                            <span class="sum-fin-num text-secondary" id="sum-fin-prepago-${p.id}">${fin.prepagadas_no_consumidas}</span>
                            <span class="sum-fin-label" style="display: flex; align-items: center; justify-content: center; gap: 4px;">
                                Prepago (Por Usar)
                                <button type="button" onclick="promptAdjustPrepayBalance(${p.id}, ${fin.prepagadas_no_consumidas}, '${(p.nombres || '').replace(/'/g, "\\'")}')" title="Ajustar manualmente las consultas prepagadas disponibles" style="background: none; border: none; cursor: pointer; font-size: 0.8rem; padding: 0; color: var(--primary-color);">✏️</button>
                            </span>
                        </div>
                    </div>
                    
                    <div style="background: rgba(220, 53, 69, 0.08); border: 1px solid rgba(220, 53, 69, 0.25); border-radius: 6px; padding: 0.6rem 0.85rem; margin-bottom: 0.85rem; display: flex; align-items: center; justify-content: space-between; font-size: 0.85rem;">
                        <span style="font-weight: 700; color: #dc2626;">Deuda Total por Cobrar:</span>
                        <strong style="font-size: 1rem; color: #dc2626;">${fin.deuda_monto_str || '0.00 USD'}</strong>
                    </div>

                    ${(fin.deudas_detalle && fin.deudas_detalle.length > 0) ? `
                        <div class="mb-3" style="background: rgba(220, 53, 69, 0.04); border: 1.5px dashed rgba(220, 53, 69, 0.3); border-radius: 8px; padding: 0.75rem;">
                            <h5 style="margin: 0 0 0.5rem 0; color: #dc2626; font-size: 0.85rem; font-weight: 700;">Deudas / Cancelaciones Sin Aviso Activas:</h5>
                            <div style="display: flex; flex-direction: column; gap: 0.45rem;">
                                ${fin.deudas_detalle.map(d => {
                                    const isLate = d.estado_pago === 'Cancelada sin aviso';
                                    const badge = isLate ? '⚠️ Cancelada sin aviso' : 'Pendiente';
                                    return `
                                        <div style="display: flex; align-items: center; justify-content: space-between; font-size: 0.82rem; background: white; padding: 0.45rem 0.65rem; border-radius: 6px; border: 1px solid var(--border-color); box-shadow: 0 1px 2px rgba(0,0,0,0.03);">
                                            <div>
                                                <strong>Cita del ${d.fecha}</strong> (${d.tipo_consulta || 'Online'})
                                                <span style="display: block; font-size: 0.76rem; color: ${isLate ? '#dc2626' : '#92400e'}; font-weight: 700;">${badge} — ${Number(d.monto || 0).toFixed(2)} ${d.moneda || 'USD'}</span>
                                            </div>
                                            <button type="button" class="btn btn-primary btn-sm" style="padding: 0.25rem 0.5rem; font-size: 0.75rem;" onclick="markTransactionAsPaid(${d.id})">✅ Marcar Pagado</button>
                                        </div>
                                    `;
                                }).join('')}
                            </div>
                        </div>
                    ` : ''}
                    
                    <h4 class="summary-block-title mt-4">Estadísticas del Proceso</h4>
                    <div class="summary-finance-dashboard mb-3">
                        <div class="sum-fin-stat">
                            <span class="sum-fin-num text-success">${summary.session_counts.Realizada}</span>
                            <span class="sum-fin-label">Realizadas</span>
                        </div>
                        <div class="sum-fin-stat payable">
                            <span class="sum-fin-num text-danger">${summary.session_counts.Cancelada}</span>
                            <span class="sum-fin-label">Canceladas</span>
                        </div>
                        <div class="sum-fin-stat">
                            <span class="sum-fin-num text-secondary" style="color: var(--primary-color) !important;">${summary.session_counts.Reprogramada}</span>
                            <span class="sum-fin-label">Reprog.</span>
                        </div>
                    </div>

                    <button class="btn btn-secondary btn-sm btn-block mb-4" onclick="openNewEventModalFromSummary(${p.id})">
                        + Registrar Pago / Cita
                    </button>
                    
                    <h4 class="summary-block-title">Notas de Última Sesión</h4>
                    <div class="summary-recap-box mb-3">
                        ${lastSes ? `
                            <p style="margin-bottom: 0.5rem;"><strong>Fecha:</strong> ${lastSes.fecha} (${lastSes.modalidad})</p>
                            <p><strong>Resumen:</strong> ${lastSes.resumen || 'Sin resumen'}</p>
                            ${lastSes.tareas_asignadas ? `<p style="margin-top:0.4rem;"><strong>Tareas:</strong> ${lastSes.tareas_asignadas}</p>` : ''}
                            ${lastSes.anotaciones_proxima ? `<p style="margin-top:0.4rem;"><strong>Prox. consulta:</strong> ${lastSes.anotaciones_proxima}</p>` : ''}
                        ` : '<p class="text-secondary"><em>No hay evoluciones anteriores registradas para este paciente.</em></p>'}
                    </div>

                    <h4 class="summary-block-title">Historial de Reprogramaciones</h4>
                    <div id="reschedule-history-container-${p.id}" class="summary-recap-box" style="max-height: 140px; overflow-y: auto;">
                        <span class="text-secondary text-xs">Cargando historial...</span>
                    </div>
                </div>
            </div>
        `;
        
        // Configurar botones de acción del modal
        document.getElementById('summary-delete-btn').onclick = () => deletePatient(p.id);
        document.getElementById('summary-edit-btn').onclick = () => openEditPatientModal(p.id);
        
        const wordBtn = document.getElementById('summary-export-word-btn');
        wordBtn.href = `/api/export/word/${p.id}`;
        
        document.getElementById('summary-print-pdf-btn').onclick = () => {
            window.open(`/api/patients/${p.id}/print`, '_blank');
        };
        
        loadPatientRescheduleHistory(p.id);
        openModal('summary-modal');
    } catch (err) {
        alert(err.message);
    }
}

async function promptAdjustPrepayBalance(patientId, currentCount, patientName) {
    const inputVal = prompt(`Ajustar consultas prepagadas disponibles para ${patientName}:\n\nIngresa el número total de consultas prepagadas disponibles que debe tener el paciente:`, currentCount);
    if (inputVal === null) return;
    const newCount = parseInt(inputVal.trim());
    if (isNaN(newCount) || newCount < 0) {
        alert('Por favor ingresa un número entero válido (igual o mayor a 0).');
        return;
    }
    try {
        const res = await fetch(`/api/patients/${patientId}/adjust-prepay-balance`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ cantidad_disponible: newCount })
        });
        const data = await res.json();
        if (res.ok && data.success) {
            alert(data.message || 'Saldo prepagado ajustado con éxito.');
            if (typeof openPatientDetailsModal === 'function') {
                openPatientDetailsModal(patientId);
            }
        } else {
            alert(data.error || 'Error al ajustar el saldo prepagado.');
        }
    } catch (e) {
        console.error("Error al ajustar saldo prepagado:", e);
        alert('Ocurrió un error al conectar con el servidor.');
    }
}

async function loadPatientRescheduleHistory(patientId) {
    const container = document.getElementById(`reschedule-history-container-${patientId}`);
    if (!container) return;
    try {
        const res = await fetch(`/api/patients/${patientId}/reschedule-history`);
        if (!res.ok) return;
        const history = await res.json();
        if (!history || history.length === 0) {
            container.innerHTML = '<p class="text-secondary text-xs" style="margin:0;"><em>Sin reprogramaciones registradas.</em></p>';
            return;
        }
        container.innerHTML = history.map(item => `
            <div style="background: white; border: 1px solid var(--border-color); border-radius: 6px; padding: 0.4rem 0.6rem; margin-bottom: 0.4rem; font-size: 0.8rem;">
                <div style="display: flex; justify-content: space-between; font-weight: 700; color: var(--primary-color);">
                    <span>🔄 ${item.fecha_anterior} (${item.hora_anterior}) ➔ ${item.fecha_nueva} (${item.hora_nueva})</span>
                    <span style="font-size: 0.7rem; color: var(--text-muted);">${item.fecha_registro}</span>
                </div>
                <div style="font-size: 0.75rem; color: var(--text-dark); margin-top: 0.15rem;">
                    <strong>Por:</strong> ${item.modificado_por || 'Sistema'} — <em>${item.motivo || ''}</em>
                </div>
            </div>
        `).join('');
    } catch (e) {
        console.error("Error al cargar historial de reprogramaciones:", e);
    }
}

// ==========================================
// GESTIÓN DE SESIONES (EVOLUCIONES)
// ==========================================
async function loadPatientsDropdowns() {
    try {
        const res = await fetch('/api/patients');
        patients = await res.json();
        
        const filterSelect = document.getElementById('session-filter-patient');
        const sessionFormSelect = document.getElementById('s-paciente');
        const eventFormSelect = document.getElementById('e-paciente');
        
        // Guardar valores seleccionados previamente
        const filterVal = filterSelect ? filterSelect.value : '';
        
        if (filterSelect) {
            filterSelect.innerHTML = '<option value="">Todos los pacientes</option>';
            patients.forEach(p => {
                filterSelect.innerHTML += `<option value="${p.id}">${p.nombres} ${p.apellidos} (${p.cedula})</option>`;
            });
            filterSelect.value = filterVal;
        }
        
        if (sessionFormSelect) {
            sessionFormSelect.innerHTML = '<option value="">Seleccione un paciente...</option>';
            patients.forEach(p => {
                sessionFormSelect.innerHTML += `<option value="${p.id}">${p.nombres} ${p.apellidos} (${p.cedula})</option>`;
            });
        }
        
        if (eventFormSelect) {
            eventFormSelect.innerHTML = '<option value="">Seleccione un paciente...</option>';
            patients.forEach(p => {
                eventFormSelect.innerHTML += `<option value="${p.id}">${p.nombres} ${p.apellidos} (${p.cedula})</option>`;
            });
        }
    } catch (err) {
        console.error("Error al cargar pacientes para dropdowns:", err);
    }
}

let currentSessionsList = [];

async function loadSessions(patientId = '') {
    const timeline = document.getElementById('sessions-timeline');
    timeline.innerHTML = '<p class="text-secondary">Cargando evoluciones...</p>';
    
    const url = patientId ? `/api/sessions?patient_id=${patientId}` : '/api/sessions';
    
    try {
        const res = await fetch(url);
        currentSessionsList = await res.json();
        applySessionsFilters();
    } catch (err) {
        timeline.innerHTML = '<p class="text-danger">Error al cargar evoluciones.</p>';
    }
}

let currentSessionsPage = 1;
const SESSIONS_PER_PAGE = 1;

function applySessionsFilters(resetPage = false) {
    if (resetPage) currentSessionsPage = 1;

    const timeline = document.getElementById('sessions-timeline');
    if (!timeline) return;
    const modalityFilter = document.getElementById('session-filter-modalidad')?.value || '';
    const searchInput = document.getElementById('session-search-patient');
    const searchQuery = searchInput ? searchInput.value.toLowerCase().trim() : '';
    const countLabel = document.getElementById('session-filter-count');
    
    timeline.innerHTML = '';
    
    let filteredList = [...currentSessionsList];
    
    // 1. Filtrar por búsqueda de texto (nombre, apellido, cédula)
    if (searchQuery) {
        filteredList = filteredList.filter(s => {
            const fullname = `${s.nombres || ''} ${s.apellidos || ''}`.toLowerCase();
            const cedula = (s.cedula || '').toLowerCase();
            return fullname.includes(searchQuery) || cedula.includes(searchQuery);
        });
    }
    
    // 2. Filtrar por modalidad
    if (modalityFilter) {
        filteredList = filteredList.filter(s => s.modalidad === modalityFilter);
    }
    
    // Ordenar por fecha descendente (la más reciente primero)
    filteredList.sort((a, b) => new Date(b.fecha) - new Date(a.fecha));

    if (countLabel) {
        countLabel.textContent = `${filteredList.length} de ${currentSessionsList.length} consultas`;
    }
    
    if (filteredList.length === 0) {
        timeline.innerHTML = '<div class="empty-state"><p>No se encontraron registros de evoluciones clínicas para los filtros aplicados.</p></div>';
        renderSessionsPaginationControls(0, 1);
        return;
    }

    const totalPages = Math.ceil(filteredList.length / SESSIONS_PER_PAGE);
    if (currentSessionsPage > totalPages) currentSessionsPage = totalPages;
    if (currentSessionsPage < 1) currentSessionsPage = 1;

    const start = (currentSessionsPage - 1) * SESSIONS_PER_PAGE;
    const pageRecords = filteredList.slice(start, start + SESSIONS_PER_PAGE);
    
    pageRecords.forEach(s => {
        const item = document.createElement('div');
        item.className = 'timeline-item';
        
        const pacName = s.nombres ? `<h4>${s.nombres} ${s.apellidos}</h4>` : '';
        const statusClass = s.estado === 'Realizada' ? 'badge-success' : (s.estado === 'Cancelada con aviso' || s.estado === 'Reprogramada' ? 'badge-info' : 'badge-danger');
        
        // Renderizado del adjunto
        let attachmentHtml = '';
        if (s.archivo_adjunto) {
            const isImage = s.archivo_adjunto.match(/\.(jpg|jpeg|png|gif|webp)$/i);
            const deleteBtnHtml = `<button onclick="deleteSessionAttachment(${s.id})" class="btn btn-secondary btn-sm text-danger" style="display: inline-flex; align-items: center; gap: 0.25rem; margin-top: 0.25rem; margin-left: 0.5rem; padding: 0.25rem 0.6rem; font-size: 0.78rem;">🗑️ Eliminar Documento</button>`;
            if (isImage) {
                attachmentHtml = `
                    <div style="margin-top: 0.75rem;">
                        <strong>Imagen Adjunta:</strong><br>
                        <div style="display: flex; align-items: flex-end; gap: 0.5rem; flex-wrap: wrap;">
                            <a href="#" onclick="openFilePreview('${s.archivo_adjunto}'); return false;">
                                <img src="/api/files/${s.archivo_adjunto}" style="max-width: 150px; max-height: 150px; border-radius: 6px; border: 1px solid var(--border-color); margin-top: 0.25rem; display: block; object-fit: cover;">
                            </a>
                            ${deleteBtnHtml}
                        </div>
                    </div>
                `;
            } else {
                attachmentHtml = `
                    <div style="margin-top: 0.75rem;">
                        <strong>Archivo Adjunto:</strong><br>
                        <div style="display: flex; align-items: center; gap: 0.5rem; margin-top: 0.25rem; flex-wrap: wrap;">
                            <a href="#" onclick="openFilePreview('${s.archivo_adjunto}'); return false;" class="btn btn-secondary btn-sm" style="display: inline-flex; align-items: center; gap: 0.25rem;">
                                <svg style="width:14px; height:14px;" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>
                                Ver Archivo
                            </a>
                            ${deleteBtnHtml}
                        </div>
                    </div>
                `;
            }
        }
        
        item.innerHTML = `
            <div class="timeline-dot"></div>
            <div class="timeline-card">
                <div class="timeline-header">
                    <div class="timeline-title-row">
                        ${pacName}
                        <span class="badge badge-info">${s.modalidad}</span>
                        <span class="badge ${statusClass}">${s.estado || 'Realizada'}</span>
                    </div>
                    <span class="timeline-date">${s.fecha}</span>
                </div>
                <div class="timeline-body">
                    <h5>Resumen Abordado:</h5>
                    <p>${s.resumen ? s.resumen.replace(/\n/g, '<br>') : '<em>Sin resumen</em>'}</p>
                    
                    ${s.diagnostico ? `
                        <h5>Diagnóstico (Sesión):</h5>
                        <p>${s.diagnostico}</p>
                    ` : ''}
                    
                    ${s.test_aplicados ? `
                        <h5>Tests Aplicados:</h5>
                        <p>${s.test_aplicados}</p>
                    ` : ''}
                    
                    ${attachmentHtml}
                    
                    ${s.tareas_asignadas ? `
                        <h5>Tareas del Consultante:</h5>
                        <p>${s.tareas_asignadas}</p>
                    ` : ''}
                    
                    ${s.recursos_entregados ? `
                        <h5>Recursos Entregados:</h5>
                        <p>${s.recursos_entregados}</p>
                    ` : ''}
                    
                    ${s.anotaciones_proxima ? `
                        <h5>Anotaciones para la Próxima Cita:</h5>
                        <p>${s.anotaciones_proxima}</p>
                    ` : ''}
                    
                    ${s.compromisos_psicologo ? `
                        <h5>Compromiso de Terapeuta:</h5>
                        <p><em>${s.compromisos_psicologo}</em></p>
                    ` : ''}
                </div>
                <div class="timeline-footer" style="display: flex; gap: 0.5rem; justify-content: flex-end; margin-top: 0.75rem; border-top: 1px solid var(--border-color); padding-top: 0.5rem;">
                    <button class="btn btn-secondary btn-sm" onclick="openEditSessionModal(${s.id})">Editar</button>
                    <button class="btn btn-secondary btn-sm text-danger" onclick="deleteSession(${s.id})">Eliminar</button>
                </div>
            </div>
        `;
        timeline.appendChild(item);
    });

    renderSessionsPaginationControls(filteredList.length, totalPages);
}

function renderSessionsPaginationControls(totalRecords, totalPages) {
    let container = document.getElementById('sessions-pagination-controls');
    if (!container) return;

    if (totalRecords === 0 || totalPages <= 1) {
        container.innerHTML = '';
        return;
    }

    container.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: center; padding: 0.65rem 0.85rem; background: white; border: 1.5px solid var(--border-color); border-radius: 8px; margin-top: 0.75rem; flex-wrap: wrap; gap: 0.5rem;">
            <button type="button" class="btn btn-sm btn-outline-secondary" onclick="changeSessionsPage(${currentSessionsPage - 1})" ${currentSessionsPage <= 1 ? 'disabled' : ''} style="font-weight: 700; padding: 0.3rem 0.75rem;">
                ◀️ Evolución Anterior
            </button>
            <span style="font-size: 0.85rem; font-weight: 700; color: var(--text-dark);">
                Evolución ${currentSessionsPage} de ${totalPages} ${currentSessionsPage === 1 ? '(Última Sesión)' : ''}
            </span>
            <button type="button" class="btn btn-sm btn-outline-secondary" onclick="changeSessionsPage(${currentSessionsPage + 1})" ${currentSessionsPage >= totalPages ? 'disabled' : ''} style="font-weight: 700; padding: 0.3rem 0.75rem;">
                Evolución Siguiente ▶️
            </button>
        </div>
    `;
}

function changeSessionsPage(newPage) {
    currentSessionsPage = newPage;
    applySessionsFilters(false);
}
window.changeSessionsPage = changeSessionsPage;

async function openNewSessionModal() {
    document.getElementById('session-form').reset();
    document.getElementById('session-form-id').value = '';
    document.getElementById('s-agenda-id').value = '';
    document.getElementById('session-modal-title').textContent = "Registrar Evolución de Consulta";
    document.getElementById('session-submit-btn').textContent = "Registrar Evolución";
    
    // Limpiar buscador en modal y campos adjuntos
    const searchInput = document.getElementById('s-paciente-search');
    if (searchInput) searchInput.value = '';
    
    const fileInput = document.getElementById('s-archivo-adjunto-input');
    if (fileInput) fileInput.value = '';
    const hiddenFile = document.getElementById('s-archivo-adjunto');
    if (hiddenFile) hiddenFile.value = '';
    const fileStatus = document.getElementById('s-archivo-adjunto-status');
    if (fileStatus) fileStatus.textContent = '';
    const fileDeleteBtn = document.getElementById('s-archivo-adjunto-delete');
    if (fileDeleteBtn) fileDeleteBtn.classList.add('hide');
    
    const resFile = document.getElementById('s-recursos-file');
    if (resFile) resFile.value = '';
    const resFileName = document.getElementById('s-recursos-file-name');
    if (resFileName) resFileName.textContent = '';
    
    await loadPatientsDropdowns();
    
    // Asegurar que todas las opciones estén visibles
    const select = document.getElementById('s-paciente');
    if (select) {
        for (let i = 0; i < select.options.length; i++) {
            select.options[i].style.display = '';
        }
    }
    
    document.getElementById('s-fecha').value = new Date().toISOString().split('T')[0];
    
    // Si estamos en la vista filtrada por un paciente, pre-seleccionar
    const filterSelect = document.getElementById('session-filter-patient');
    const filterVal = filterSelect ? filterSelect.value : '';
    if (filterVal) {
        document.getElementById('s-paciente').value = filterVal;
    }
    
    const currentPatientId = document.getElementById('s-paciente').value;
    if (currentPatientId) {
        await checkSessionPatientPrepayments(currentPatientId);
        await updateSessionPatientQuickInfo(currentPatientId);
    } else {
        const quickInfoDiv = document.getElementById('s-paciente-quick-info');
        if (quickInfoDiv) {
            quickInfoDiv.innerHTML = '';
            quickInfoDiv.classList.add('hide');
        }
        const optConsumir = document.getElementById('s-opt-descontar-prepago');
        if (optConsumir) optConsumir.style.display = 'none';
        const alertsDiv = document.getElementById('s-paciente-alerts');
        if (alertsDiv) alertsDiv.classList.add('hide');
    }
    // Mostrar campos de liquidación por defecto para el estado "Realizada" (por defecto Dejar pendiente)
    document.getElementById('s-estado').value = 'Realizada';
    toggleSessionFinanceFields('Realizada');
    document.getElementById('s-tipo-liq').value = 'Dejar pendiente';
    toggleSessionFinanceInputs('Dejar pendiente');
    
    openModal('session-modal');
}

async function openRegisterSessionFromEvent(eventId) {
    try {
        const res = await fetch(`/api/finance/transactions/${eventId}`);
        if (!res.ok) throw new Error("Cita no encontrada.");
        const e = await res.json();
        
        document.getElementById('session-form').reset();
        document.getElementById('session-form-id').value = '';
        document.getElementById('s-agenda-id').value = eventId;
        document.getElementById('session-modal-title').textContent = "Registrar Evolución y Liquidar Sesión";
        document.getElementById('session-submit-btn').textContent = "Registrar y Liquidar";
        
        const searchInput = document.getElementById('s-paciente-search');
        if (searchInput) searchInput.value = '';
        
        await loadPatientsDropdowns();
        
        const select = document.getElementById('s-paciente');
        if (select) {
            for (let i = 0; i < select.options.length; i++) {
                select.options[i].style.display = '';
            }
        }
        
        document.getElementById('s-paciente').value = e.paciente_id;
        document.getElementById('s-fecha').value = e.fecha;
        document.getElementById('s-modalidad').value = e.tipo_consulta;
        
        // Cargar alertas de prepagos y deudas y ficha rápida (esto autocompleta s-monto con los honorarios)
        await checkSessionPatientPrepayments(e.paciente_id);
        await updateSessionPatientQuickInfo(e.paciente_id);
        
        // Estado por defecto
        document.getElementById('s-estado').value = 'Realizada';
        toggleSessionFinanceFields('Realizada');
        
        // Forma de liquidación por defecto: Dejar pendiente
        if (e.monto > 0) {
            document.getElementById('s-monto').value = Number(e.monto).toFixed(2);
        }
        document.getElementById('s-tipo-liq').value = 'Dejar pendiente';
        toggleSessionFinanceInputs('Dejar pendiente');
        
        openModal('session-modal');
    } catch (err) {
        alert(err.message);
    }
}

async function handleSessionSubmit(e) {
    e.preventDefault();
    const id = document.getElementById('session-form-id').value;
    const agendaId = document.getElementById('s-agenda-id').value;
    
    if (!confirm("¿Está seguro de guardar esta evolución clínica?")) {
        return;
    }
    
    let recursosValue = document.getElementById('s-recursos').value;
    const fileInput = document.getElementById('s-recursos-file');
    
    if (fileInput && fileInput.files.length > 0) {
        const file = fileInput.files[0];
        const formData = new FormData();
        formData.append('file', file);
        
        try {
            const uploadRes = await fetch('/api/upload', {
                method: 'POST',
                body: formData
            });
            if (uploadRes.ok) {
                const uploadData = await uploadRes.json();
                const fileUrl = `${window.location.origin}/api/upload/${uploadData.filename}`;
                if (recursosValue.trim() === '') {
                    recursosValue = `${file.name}: ${fileUrl}`;
                } else {
                    recursosValue += `\n${file.name}: ${fileUrl}`;
                }
            } else {
                alert("Error al subir el recurso adjunto.");
                return;
            }
        } catch (uploadErr) {
            console.error("Error al subir recurso:", uploadErr);
            alert("Error al subir el recurso adjunto.");
            return;
        }
    }
    
    const estado = document.getElementById('s-estado').value;
    const payload = {
        paciente_id: document.getElementById('s-paciente').value,
        agenda_id: agendaId ? parseInt(agendaId) : null,
        fecha: document.getElementById('s-fecha').value,
        modalidad: document.getElementById('s-modalidad').value,
        estado: estado,
        resumen: document.getElementById('s-resumen').value,
        resumen_paciente: document.getElementById('s-resumen-paciente').value,
        tareas_asignadas: document.getElementById('s-tareas').value,
        recursos_entregados: recursosValue,
        anotaciones_proxima: document.getElementById('s-anotaciones').value,
        compromisos_psicologo: document.getElementById('s-compromisos').value,
        diagnostico: document.getElementById('s-diagnostico-clinico').value,
        test_aplicados: document.getElementById('s-test-aplicados').value,
        archivo_adjunto: document.getElementById('s-archivo-adjunto').value,
        
        // Campos financieros
        tipo_liquidacion: (estado === 'Realizada' || estado === 'Cancelada sin aviso') ? document.getElementById('s-tipo-liq').value : null,
        monto: parseFloat(document.getElementById('s-monto').value || 0.0),
        moneda: document.getElementById('s-moneda').value,
        metodo_pago: document.getElementById('s-metodo').value,
        referencia: document.getElementById('s-referencia').value,
        fecha_pago: document.getElementById('s-fecha-pago').value
    };
    
    const method = id ? 'PUT' : 'POST';
    const url = id ? `/api/sessions/${id}` : '/api/sessions';
    
    try {
        const res = await fetch(url, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        
        if (res.ok) {
            alert(data.success);
            closeModal('session-modal');
            
            // Recargar datos en las distintas vistas
            if (activeView === 'sessions') loadSessions('');
            if (activeView === 'agenda') loadAgenda();
            loadDashboardStats();
            loadFinanceData();
            if (activeView === 'dashboard') loadAgendaCompact();
        } else {
            alert(data.error);
        }
    } catch (err) {
        alert("Error de conexión al guardar evolución clínica.");
    }
}

async function openEditSessionModal(sessionId) {
    try {
        const res = await fetch(`/api/sessions/${sessionId}`);
        if (!res.ok) throw new Error("Evolución no encontrada.");
        const s = await res.json();
        
        document.getElementById('session-form').reset();
        document.getElementById('session-form-id').value = s.id;
        document.getElementById('s-agenda-id').value = s.agenda_id || '';
        document.getElementById('session-modal-title').textContent = "Editar Evolución Clínica";
        document.getElementById('session-submit-btn').textContent = "Guardar Cambios";
        
        const searchInput = document.getElementById('s-paciente-search');
        if (searchInput) searchInput.value = '';
        
        const resFile = document.getElementById('s-recursos-file');
        if (resFile) resFile.value = '';
        const resFileName = document.getElementById('s-recursos-file-name');
        if (resFileName) resFileName.textContent = '';

        await loadPatientsDropdowns();
        
        const select = document.getElementById('s-paciente');
        if (select) {
            for (let i = 0; i < select.options.length; i++) {
                select.options[i].style.display = '';
            }
        }
        
        document.getElementById('s-paciente').value = s.paciente_id;
        document.getElementById('s-fecha').value = s.fecha;
        document.getElementById('s-modalidad').value = s.modalidad;
        document.getElementById('s-estado').value = s.estado || 'Realizada';
        document.getElementById('s-resumen').value = s.resumen || '';
        const resPacEl = document.getElementById('s-resumen-paciente');
        if (resPacEl) resPacEl.value = s.resumen_paciente || '';
        document.getElementById('s-tareas').value = s.tareas_asignadas || '';
        document.getElementById('s-recursos').value = s.recursos_entregados || '';
        document.getElementById('s-anotaciones').value = s.anotaciones_proxima || '';
        document.getElementById('s-compromisos').value = s.compromisos_psicologo || '';
        
        document.getElementById('s-diagnostico-clinico').value = s.diagnostico || '';
        document.getElementById('s-test-aplicados').value = s.test_aplicados || '';
        
        const fileInput = document.getElementById('s-archivo-adjunto-input');
        if (fileInput) fileInput.value = '';
        const hiddenFile = document.getElementById('s-archivo-adjunto');
        if (hiddenFile) hiddenFile.value = s.archivo_adjunto || '';
        const fileStatus = document.getElementById('s-archivo-adjunto-status');
        const fileDeleteBtn = document.getElementById('s-archivo-adjunto-delete');
        if (s.archivo_adjunto) {
            if (fileStatus) fileStatus.textContent = 'Archivo adjunto guardado';
            if (fileDeleteBtn) fileDeleteBtn.classList.remove('hide');
        } else {
            if (fileStatus) fileStatus.textContent = '';
            if (fileDeleteBtn) fileDeleteBtn.classList.add('hide');
        }
        
        // Verificar y pre-rellenar datos financieros vinculados a la cita y ficha rápida
        await checkSessionPatientPrepayments(s.paciente_id);
        await updateSessionPatientQuickInfo(s.paciente_id);
        
        if (s.agenda_id) {
            const agendaRes = await fetch(`/api/finance/transactions/${s.agenda_id}`);
            if (agendaRes.ok) {
                const a = await agendaRes.json();
                
                toggleSessionFinanceFields(s.estado || 'Realizada');
                
                let tipoLiq = 'Cobrar ahora';
                if (a.estado_pago === 'Pendiente') {
                    tipoLiq = 'Dejar pendiente';
                } else if (a.estado_pago === 'Paga' && a.metodo_pago === 'Descontado de Prepago') {
                    tipoLiq = 'Descontar prepago';
                }
                
                document.getElementById('s-tipo-liq').value = tipoLiq;
                document.getElementById('s-monto').value = a.monto || '';
                document.getElementById('s-moneda').value = a.moneda || 'USD';
                document.getElementById('s-metodo').value = a.metodo_pago || '';
                document.getElementById('s-referencia').value = a.referencia || '';
                document.getElementById('s-fecha-pago').value = a.fecha_pago || '';
                
                toggleSessionFinanceInputs(tipoLiq);
            }
        } else {
            // Ocultar sección financiera si no está vinculada a agenda
            document.getElementById('s-finance-section').style.display = 'none';
        }
        
        openModal('session-modal');
    } catch (err) {
        alert(err.message);
    }
}

async function deleteSession(sessionId) {
    if (!confirm("¿Está seguro de eliminar esta evolución clínica? Si tiene una cita vinculada, se restaurará a estado 'Agendada' y se revertirán los abonos o descuentos de prepago.")) {
        return;
    }
    
    try {
        const res = await fetch(`/api/sessions/${sessionId}`, { method: 'DELETE' });
        const data = await res.json();
        
        if (res.ok) {
            alert(data.success);
            loadDashboardStats();
            loadFinanceData();
            if (activeView === 'sessions') loadSessions('');
            if (activeView === 'agenda') loadAgenda();
            if (activeView === 'dashboard') loadAgendaCompact();
        } else {
            alert(data.error);
        }
    } catch (err) {
        alert("Error de conexión al eliminar evolución.");
    }
}

// ==========================================
// DASHBOARD STATS & EVENTS
// ==========================================
async function loadDashboardStats() {
    try {
        const res = await fetch('/api/finance/balance');
        const data = await res.json();
        
        const totPat = document.getElementById('stat-total-patients');
        if (totPat) totPat.textContent = data.stats.total_pacientes || 0;
        const paidSess = document.getElementById('stat-paid-sessions');
        if (paidSess) paidSess.textContent = data.stats.total_pagas || 0;
        const pendSess = document.getElementById('stat-pending-sessions');
        if (pendSess) pendSess.textContent = data.stats.total_pendientes || 0;
        
        const container = document.getElementById('stat-month-modalities-container');
        if (container) {
            container.innerHTML = '';
            const mods = data.stats.month_modalities || {
                'Presencial': data.stats.month_presencial || 0,
                'Online': data.stats.month_online || 0
            };
            
            Object.keys(mods).forEach(modName => {
                const count = mods[modName] || 0;
                const item = document.createElement('div');
                item.innerHTML = `${modName}: <span style="font-weight: bold; color: var(--text-color);">${count}</span>`;
                container.appendChild(item);
            });
        }
    } catch (err) {
        console.error("Error al cargar estadísticas del dashboard:", err);
    }
}

async function loadAgendaCompact() {
    const listContainer = document.getElementById('pending-evolutions-list');
    const nextConsultation = document.getElementById('next-consultation-content');
    if (!listContainer || !nextConsultation) return;
    
    try {
        const res = await fetch('/api/agenda');
        const events = await res.json();
        
        listContainer.innerHTML = '';
        nextConsultation.innerHTML = '';
        
        const _nowDate = new Date();
        const todayStr = `${_nowDate.getFullYear()}-${String(_nowDate.getMonth() + 1).padStart(2, '0')}-${String(_nowDate.getDate()).padStart(2, '0')}`;
        
        // Buscar la próxima cita agendada desde hoy en adelante (no evolucionada)
        let upcomingEvents = events.filter(e => e.fecha >= todayStr && e.estado_pago !== 'Prepagada' && !e.has_session);
        upcomingEvents.sort((a, b) => a.fecha.localeCompare(b.fecha) || a.hora.localeCompare(b.hora));
        
        // 1. Mostrar Siguiente Consulta
        if (upcomingEvents.length > 0) {
            const nextE = upcomingEvents[0];
            const isToday = nextE.fecha === todayStr;
            const fechaText = isToday ? `Hoy a las <strong>${nextE.hora}</strong>` : `El <strong>${nextE.fecha}</strong> a las <strong>${nextE.hora}</strong>`;
            
            let lastSes = null;
            try {
                const summaryRes = await fetch(`/api/patients/${nextE.paciente_id}/summary`);
                if (summaryRes.ok) {
                    const summary = await summaryRes.json();
                    lastSes = summary.last_session;
                }
            } catch(e) {}
            
            const btnEvolucionar = !nextE.has_session 
                ? `<button class="btn btn-primary btn-sm" onclick="openRegisterSessionFromEvent(${nextE.id})">Evolucionar</button>` 
                : '';
            
            nextConsultation.innerHTML = `
                <div class="next-patient-card" style="display:flex; justify-content:space-between; align-items:center; flex-wrap: wrap; gap: 0.5rem;">
                    <div>
                        <h4 class="next-patient-title" style="margin: 0; font-size:1.05rem;">${nextE.nombres} ${nextE.apellidos}</h4>
                        <p class="text-secondary" style="margin: 0.25rem 0 0 0; font-size:0.85rem;">${fechaText} | Modalidad: <strong>${nextE.tipo_consulta}</strong></p>
                    </div>
                    <div style="display: flex; gap: 0.35rem; flex-wrap: wrap;">
                        ${btnEvolucionar}
                        <button class="btn btn-secondary btn-sm" onclick="openSummaryModal(${nextE.paciente_id})">Ver Ficha</button>
                    </div>
                </div>
                <div class="recap-box" style="margin-top: 0.85rem; padding: 0.75rem; background: rgba(0,0,0,0.02); border-radius: var(--radius-sm);">
                    <h5 style="margin: 0 0 0.4rem 0; font-size: 0.85rem; color: var(--primary-color);">Recapitulación de Sesión Anterior:</h5>
                    ${lastSes ? `
                        <p style="font-size:0.8rem; margin-bottom: 0.25rem;"><strong>Fecha:</strong> ${lastSes.fecha}</p>
                        <p style="font-size:0.8rem; margin-bottom: 0.25rem;"><strong>Resumen:</strong> ${lastSes.resumen}</p>
                        ${lastSes.tareas_asignadas ? `<p style="font-size:0.8rem; margin:0;"><strong>Tareas de paciente:</strong> ${lastSes.tareas_asignadas}</p>` : ''}
                    ` : '<p class="text-secondary" style="font-size:0.8rem; margin:0;">No hay evoluciones previas registradas.</p>'}
                </div>
            `;
        } else {
            nextConsultation.innerHTML = `
                <div class="empty-state">
                    <p>No tienes citas agendadas registradas.</p>
                </div>
            `;
        }
        
        // 2. Mostrar Evoluciones Clínicas Pendientes (Citas pasadas o de hoy que no tienen evolución cargada y no son prepagos de paquetes)
        const pendingEvolutions = events.filter(e => !e.has_session && e.estado_pago !== 'Prepagada' && e.fecha <= todayStr);
        if (pendingEvolutions.length === 0) {
            listContainer.innerHTML = `
                <div class="empty-state">
                    <p>🎉 ¡Al día! No tienes evoluciones pendientes por redactar.</p>
                </div>
            `;
            return;
        }
        
        // Ordenar de más antiguas a más nuevas
        pendingEvolutions.sort((a, b) => a.fecha.localeCompare(b.fecha) || a.hora.localeCompare(b.hora));
        
        pendingEvolutions.forEach(e => {
            const item = document.createElement('div');
            item.className = 'agenda-compact-item';
            
            const isToday = e.fecha === todayStr;
            const fechaLabel = isToday ? 'Hoy' : e.fecha;
            
            item.innerHTML = `
                <div class="agenda-compact-info">
                    <span class="agenda-compact-time">${fechaLabel} a las ${e.hora}</span>
                    <span class="agenda-compact-patient">${e.nombres} ${e.apellidos}</span>
                    <span class="agenda-compact-type" style="color: var(--danger-color); font-weight: 500;">Pendiente por Evolucionar</span>
                </div>
                <div style="display: flex; gap: 0.35rem;">
                    <button class="btn btn-primary btn-sm" onclick="openRegisterSessionFromEvent(${e.id})">Evolucionar</button>
                    <button class="btn btn-secondary btn-sm" onclick="openSummaryModal(${e.paciente_id})">Ficha</button>
                </div>
            `;
            listContainer.appendChild(item);
        });
    } catch (err) {
        listContainer.innerHTML = '<p class="text-danger">Error al cargar evoluciones pendientes.</p>';
    }
}

// ==========================================
// CONTROL FINANCIERO Y BALANCE MULTIMONEDA
// ==========================================
async function loadFinanceData() {
    const yearEl = document.getElementById('finance-filter-year');
    const monthEl = document.getElementById('finance-filter-month');
    const year = yearEl ? yearEl.value : new Date().getFullYear();
    const month = monthEl ? monthEl.value : String(new Date().getMonth() + 1).padStart(2, '0');
    
    const pendingTbody = document.getElementById('pending-finance-table-body');
    if (pendingTbody && (pendingTbody.children.length === 0 || pendingTbody.innerHTML.includes('<!-- Dinámico -->'))) {
        pendingTbody.innerHTML = '<tr><td colspan="6" class="text-center text-secondary">Cargando cuentas pendientes...</td></tr>';
    }
    
    try {
        const res = await fetch(`/api/finance/balance?month=${month}&year=${year}`);
        if (!res.ok) throw new Error("Error de respuesta al obtener balance");
        const data = await res.json();
        
        // Agrupar y sumar balances dinámicamente por tipo de moneda recibida en el mes
        const currencyTotals = {};
        
        if (data.breakdown && data.breakdown.length > 0) {
            data.breakdown.forEach(item => {
                const currency = (item.moneda || 'USD').toUpperCase();
                const val = parseFloat(item.total_monto || 0);
                if (val > 0) {
                    currencyTotals[currency] = (currencyTotals[currency] || 0) + val;
                }
            });
        }
        
        // Si no hay breakdown, acumular desde income_list
        if (Object.keys(currencyTotals).length === 0 && data.income_list && data.income_list.length > 0) {
            data.income_list.forEach(item => {
                const currency = (item.moneda || 'USD').toUpperCase();
                const val = parseFloat(item.monto || 0);
                if (val > 0) {
                    currencyTotals[currency] = (currencyTotals[currency] || 0) + val;
                }
            });
        }
        
        // Renderizar tarjetas dinámicas de balance por moneda en la UI
        const balancesGrid = document.getElementById('finance-balances-grid');
        if (balancesGrid) {
            balancesGrid.innerHTML = '';
            
            const currencyKeys = Object.keys(currencyTotals);
            
            if (currencyKeys.length === 0) {
                // Si no hay ingresos en el mes seleccionado, mostrar tarjeta base USD $0.00
                balancesGrid.innerHTML = `
                    <div class="finance-card usd" style="background: white; border: 1.5px solid rgba(16, 185, 129, 0.25); border-radius: var(--radius-md); padding: 0.6rem 0.4rem; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; gap: 0.15rem; box-shadow: var(--shadow-sm); width: 100%; box-sizing: border-box; min-width: 0;">
                        <div class="fin-badge" style="background: rgba(16, 185, 129, 0.12); color: #059669; font-weight: 700; padding: 0.12rem 0.4rem; border-radius: 4px; font-size: 0.68rem; line-height: 1; margin-bottom: 0.1rem;">USD</div>
                        <span class="fin-label" style="font-size: 0.72rem; color: var(--text-secondary); line-height: 1.1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; width: 100%;">Dólares ($)</span>
                        <h3 class="fin-amount" style="font-size: 0.95rem; font-weight: 800; color: var(--text-dark); margin: 0; line-height: 1.2;">$ 0,00</h3>
                    </div>
                `;
            } else {
                const CURRENCY_CONFIG = {
                    'USD': { name: 'Dólares', symbol: '$', badgeBg: 'rgba(16, 185, 129, 0.12)', badgeColor: '#059669', border: 'rgba(16, 185, 129, 0.25)' },
                    'EUR': { name: 'Euros', symbol: '€', badgeBg: 'rgba(99, 102, 241, 0.12)', badgeColor: '#4f46e5', border: 'rgba(99, 102, 241, 0.25)' },
                    'BSD': { name: 'Bolívares', symbol: 'Bs.', badgeBg: 'rgba(245, 158, 11, 0.12)', badgeColor: '#d97706', border: 'rgba(245, 158, 11, 0.25)' },
                    'ARS': { name: 'Pesos Arg.', symbol: '$', badgeBg: 'rgba(59, 130, 246, 0.12)', badgeColor: '#2563eb', border: 'rgba(59, 130, 246, 0.25)' },
                    'COP': { name: 'Pesos Col.', symbol: '$', badgeBg: 'rgba(236, 72, 153, 0.12)', badgeColor: '#db2777', border: 'rgba(236, 72, 153, 0.25)' },
                    'CLP': { name: 'Pesos Chi.', symbol: '$', badgeBg: 'rgba(139, 92, 246, 0.12)', badgeColor: '#7c3aed', border: 'rgba(139, 92, 246, 0.25)' },
                    'MXN': { name: 'Pesos Mex.', symbol: '$', badgeBg: 'rgba(20, 184, 166, 0.12)', badgeColor: '#0d9488', border: 'rgba(20, 184, 166, 0.25)' },
                    'DOP': { name: 'Pesos Dom.', symbol: 'RD$', badgeBg: 'rgba(249, 115, 22, 0.12)', badgeColor: '#ea580c', border: 'rgba(249, 115, 22, 0.25)' },
                    'PEN': { name: 'Soles Per.', symbol: 'S/', badgeBg: 'rgba(168, 85, 247, 0.12)', badgeColor: '#9333ea', border: 'rgba(168, 85, 247, 0.25)' },
                    'UYU': { name: 'Pesos Uru.', symbol: '$', badgeBg: 'rgba(14, 165, 233, 0.12)', badgeColor: '#0284c7', border: 'rgba(14, 165, 233, 0.25)' }
                };
                
                currencyKeys.forEach(curr => {
                    const total = currencyTotals[curr];
                    const cfg = CURRENCY_CONFIG[curr] || { name: curr, symbol: curr, badgeBg: 'rgba(107, 114, 128, 0.12)', badgeColor: '#4b5563', border: 'rgba(107, 114, 128, 0.25)' };
                    
                    const card = document.createElement('div');
                    card.className = `finance-card ${curr.toLowerCase()}`;
                    card.style.cssText = `background: white; border: 1.5px solid ${cfg.border}; border-radius: var(--radius-md); padding: 0.6rem 0.4rem; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; gap: 0.15rem; box-shadow: var(--shadow-sm); width: 100%; box-sizing: border-box; min-width: 0; transition: transform 0.2s ease;`;
                    
                    const formattedValue = total.toLocaleString('es-ES', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
                    
                    card.innerHTML = `
                        <div class="fin-badge" style="background: ${cfg.badgeBg}; color: ${cfg.badgeColor}; font-weight: 700; padding: 0.12rem 0.4rem; border-radius: 4px; font-size: 0.68rem; line-height: 1; margin-bottom: 0.1rem;">${curr}</div>
                        <span class="fin-label" style="font-size: 0.72rem; color: var(--text-secondary); line-height: 1.1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; width: 100%;">${cfg.name}</span>
                        <h3 class="fin-amount" style="font-size: 0.92rem; font-weight: 800; color: var(--text-dark); margin: 0; line-height: 1.2; word-break: break-word;">${cfg.symbol} ${formattedValue}</h3>
                    `;
                    balancesGrid.appendChild(card);
                });
            }
        }
        
        // Renderizar desglose de ingresos detallado
        const incomeBody = document.getElementById('finance-income-list-body');
        if (incomeBody) {
            incomeBody.innerHTML = '';
            if (!data.income_list || data.income_list.length === 0) {
                incomeBody.innerHTML = '<tr><td colspan="3" class="text-center text-secondary">Sin ingresos registrados este mes.</td></tr>';
            } else {
                data.income_list.forEach(item => {
                    const tr = document.createElement('tr');
                    tr.innerHTML = `
                        <td>${item.nombres || ''} ${item.apellidos || ''}</td>
                        <td class="text-success"><strong>${item.monto} ${item.moneda}</strong></td>
                        <td style="text-align: right; display: flex; gap: 0.35rem; justify-content: flex-end;">
                            <button class="btn btn-secondary btn-sm" onclick="openEditEventModal(${item.id})">Editar</button>
                            <button class="btn btn-secondary btn-sm text-danger" onclick="deleteFinancePayment(${item.id})">Eliminar</button>
                        </td>
                    `;
                    incomeBody.appendChild(tr);
                });
            }
        }
        
        // Renderizar Resumen de Consultas por mes
        const sessionStats = {
            'Presencial': { Realizada: 0, Cancelada: 0, Reprogramada: 0 },
            'Online': { Realizada: 0, Cancelada: 0, Reprogramada: 0 },
            'Uptaeb': { Realizada: 0, Cancelada: 0, Reprogramada: 0 }
        };
        
        if (data.session_stats) {
            data.session_stats.forEach(item => {
                const mod = item.modalidad;
                const est = item.estado || 'Realizada';
                if (sessionStats[mod] && sessionStats[mod][est] !== undefined) {
                    sessionStats[mod][est] = item.cantidad;
                }
            });
        }
        
        const statsBody = document.getElementById('finance-session-stats-body');
        if (statsBody) {
            statsBody.innerHTML = '';
            Object.keys(sessionStats).forEach(mod => {
                const row = sessionStats[mod];
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td><strong>${mod}</strong></td>
                    <td style="text-align:center;" class="text-success">${row.Realizada}</td>
                    <td style="text-align:center;" class="text-danger">${row.Cancelada}</td>
                    <td style="text-align:center;" class="text-secondary">${row.Reprogramada}</td>
                `;
                statsBody.appendChild(tr);
            });
        }
        
        // Renderizar Cuentas por Cobrar (Pendientes)
        if (pendingTbody) {
            pendingTbody.innerHTML = '';
            
            if (!data.pending_list || data.pending_list.length === 0) {
                pendingTbody.innerHTML = '<tr><td colspan="6" class="text-center text-secondary">No hay cuentas pendientes por cobrar.</td></tr>';
            } else {
                data.pending_list.forEach(p => {
                    const tr = document.createElement('tr');
                    const statusBadge = p.estado_pago === 'Cancelada sin aviso' 
                        ? '<span style="background:#fee2e2;color:#dc2626;padding:0.15rem 0.5rem;border-radius:4px;font-size:0.75rem;font-weight:700;">Cancelada sin aviso</span>'
                        : '<span style="background:#fef3c7;color:#92400e;padding:0.15rem 0.5rem;border-radius:4px;font-size:0.75rem;font-weight:700;">Pendiente</span>';
                    tr.innerHTML = `
                        <td style="font-weight:600;">${p.nombres || ''} ${p.apellidos || ''}</td>
                        <td>${p.fecha || ''} ${p.hora || ''}</td>
                        <td>${p.tipo_consulta || '—'}</td>
                        <td>${statusBadge}</td>
                        <td class="text-danger"><strong>${Number(p.monto || 0).toFixed(2)} ${p.moneda || 'USD'}</strong></td>
                        <td style="display: flex; gap: 0.35rem; flex-wrap: wrap;">
                            ${p.telefono ? `<a href="${getWhatsAppLink(p.telefono, `Hola ${p.nombres}, te escribimos para recordarte el saldo pendiente de ${Number(p.monto || 0).toFixed(2)} ${p.moneda || 'USD'} correspondiente a la consulta del ${p.fecha}. ¡Muchas gracias!`)}" target="_blank" class="btn btn-sm" style="background:#25D366; color:white; border:none; font-size:0.78rem; text-decoration:none; display:inline-flex; align-items:center; gap:0.2rem;">💬 WhatsApp</a>` : ''}
                            <button class="btn btn-primary btn-sm" style="font-size:0.78rem;" onclick="markTransactionAsPaid(${p.id})">✅ Marcar Pagado</button>
                            <button class="btn btn-secondary btn-sm" style="font-size:0.78rem;" onclick="openEditEventModal(${p.id})">Gestionar</button>
                            <button class="btn btn-secondary btn-sm text-danger" style="font-size:0.78rem;" onclick="deleteFinancePayment(${p.id})">Eliminar</button>
                        </td>
                    `;
                    pendingTbody.appendChild(tr);
                });
            }
        }
        
        // Cargar pagos reportados pendientes por verificar
        loadNotifiedPayments();
        
    } catch (err) {
        console.error("Error al cargar finanzas:", err);
        if (pendingTbody) {
            pendingTbody.innerHTML = '<tr><td colspan="6" class="text-center text-danger">Error de conexión al cargar cuentas por cobrar.</td></tr>';
        }
    }
}

async function markTransactionAsPaid(transId) {
    const today = new Date().toISOString().split('T')[0];
    
    // Obtener la transacción original para mantener los montos y actualizar
    try {
        const payload = {
            estado_pago: 'Paga',
            control_uso: 'Consumida',
            fecha_liquidacion: today
        };
        
        const res = await fetch(`/api/finance/transactions/${transId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        
        if (res.ok) {
            alert("Pago registrado con éxito.");
            loadDashboardStats();
            loadFinanceData();
        } else {
            const data = await res.json();
            alert(data.error);
        }
    } catch (err) {
        alert("Error de conexión al liquidar transacción.");
    }
}

let fullCalendarInstance = null;

function switchAgendaSubView(subView) {
    const tabCal = document.getElementById('agenda-tab-calendar');
    const tabList = document.getElementById('agenda-tab-list');
    const tabHist = document.getElementById('agenda-tab-history');
    
    const viewCal = document.getElementById('agenda-sub-view-calendar');
    const viewList = document.getElementById('agenda-sub-view-list');
    const viewHist = document.getElementById('agenda-sub-view-history');
    
    if (tabCal) tabCal.className = subView === 'calendar' ? 'btn btn-sm btn-primary' : 'btn btn-sm btn-secondary';
    if (tabList) tabList.className = subView === 'list' ? 'btn btn-sm btn-primary' : 'btn btn-sm btn-secondary';
    if (tabHist) tabHist.className = subView === 'history' ? 'btn btn-sm btn-primary' : 'btn btn-sm btn-secondary';
    
    if (viewCal) viewCal.classList.toggle('hide', subView !== 'calendar');
    if (viewList) viewList.classList.toggle('hide', subView !== 'list');
    if (viewHist) viewHist.classList.toggle('hide', subView !== 'history');
    
    if (subView === 'calendar') {
        renderFullCalendar();
    } else if (subView === 'list') {
        loadAgenda();
    } else if (subView === 'history') {
        initTherapistAgendaHistoryFilters();
        loadTherapistConsultationHistory();
    }
}

function initTherapistAgendaHistoryFilters() {
    const yearSelect = document.getElementById('agenda-history-filter-year');
    const monthSelect = document.getElementById('agenda-history-filter-month');
    
    if (yearSelect && yearSelect.children.length === 0) {
        const currentYear = new Date().getFullYear();
        for (let y = currentYear; y >= 2024; y--) {
            const opt = document.createElement('option');
            opt.value = y;
            opt.textContent = y;
            yearSelect.appendChild(opt);
        }
    }
    
    if (monthSelect && monthSelect.children.length === 0) {
        const currentMonth = new Date().getMonth() + 1;
        const meses = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'];
        meses.forEach((m, idx) => {
            const opt = document.createElement('option');
            opt.value = String(idx + 1).padStart(2, '0');
            opt.textContent = m;
            if (idx + 1 === currentMonth) opt.selected = true;
            monthSelect.appendChild(opt);
        });
    }
}

async function loadTherapistConsultationHistory() {
    const tbody = document.getElementById('agenda-history-table-body');
    if (!tbody) return;
    
    const year = document.getElementById('agenda-history-filter-year')?.value || new Date().getFullYear();
    const month = document.getElementById('agenda-history-filter-month')?.value || String(new Date().getMonth() + 1).padStart(2, '0');
    
    tbody.innerHTML = '<tr><td colspan="6" class="text-center text-secondary">Cargando historial de consultas...</td></tr>';
    
    try {
        const res = await fetch(`/api/admin/consultation-history?year=${year}&month=${month}`);
        if (!res.ok) throw new Error("Error al obtener historial");
        const list = await res.json();
        
        if (!list || list.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="text-center text-secondary">No hay consultas registradas para este mes.</td></tr>';
            return;
        }
        
        tbody.innerHTML = list.map(item => {
            const isPaid = item.estado_pago === 'Paga' || item.estado_pago === 'Prepagada' || item.estado_pago === 'Cancelada sin aviso - Paga';
            const isLate = item.estado_pago === 'Cancelada sin aviso';
            const statusBadge = isPaid
                ? '<span style="background:#d1fae5;color:#065f46;padding:0.15rem 0.5rem;border-radius:4px;font-size:0.75rem;font-weight:700;">✅ Paga</span>'
                : isLate
                    ? '<span style="background:#fee2e2;color:#dc2626;padding:0.15rem 0.5rem;border-radius:4px;font-size:0.75rem;font-weight:700;">⚠️ Cancelada sin aviso</span>'
                    : '<span style="background:#fef3c7;color:#92400e;padding:0.15rem 0.5rem;border-radius:4px;font-size:0.75rem;font-weight:700;">⏳ Pendiente</span>';
                    
            const waText = `Hola ${item.nombres}, te escribimos de Mi Consultorio sobre tu cita del ${item.fecha} a las ${item.hora}.`;
            const waUrl = getWhatsAppLink(item.telefono, waText);
            const waBtn = item.telefono ? `<a href="${waUrl}" target="_blank" class="btn btn-sm" style="background:#25D366; color:white; border:none; font-size:0.75rem; text-decoration:none; display:inline-flex; align-items:center; gap:0.2rem;">💬 WhatsApp</a>` : '';
            
            return `
                <tr>
                    <td><strong>${item.fecha || ''}</strong> <span class="text-secondary" style="font-size:0.85rem;">${item.hora || ''}</span></td>
                    <td style="font-weight:600;">${item.nombres || ''} ${item.apellidos || ''} <span class="text-secondary" style="font-size:0.78rem;">(#${item.cedula || ''})</span></td>
                    <td>${item.tipo_consulta || '—'}</td>
                    <td><strong>${Number(item.monto || 0).toFixed(2)} ${item.moneda || 'USD'}</strong></td>
                    <td>${statusBadge}</td>
                    <td style="display:flex; gap:0.35rem; flex-wrap:wrap; align-items:center;">
                        ${waBtn}
                        <button class="btn btn-secondary btn-sm" style="font-size:0.75rem;" onclick="openEditEventModal(${item.id})">Gestionar</button>
                        <button class="btn btn-sm" style="background:#fee2e2; color:#dc2626; border:1px solid #fca5a5; font-size:0.75rem; font-weight:700; cursor:pointer;" onclick="deleteConsultationFromHistory(${item.id})">🗑️ Eliminar</button>
                    </td>
                </tr>
            `;
        }).join('');
    } catch (err) {
        console.error(err);
        tbody.innerHTML = '<tr><td colspan="6" class="text-center text-danger">Error al cargar historial.</td></tr>';
    }
}

async function deleteConsultationFromHistory(eventId) {
    if (!confirm("¿Estás seguro de que deseas eliminar esta consulta del historial de pruebas? Esta acción borrará el registro y sus datos asociados.")) {
        return;
    }
    try {
        const res = await fetch(`/api/admin/consultation-history/${eventId}`, {
            method: 'DELETE'
        });
        const data = await res.json();
        if (res.ok) {
            alert(data.success || "Consulta eliminada con éxito.");
            loadAdminConsultationHistory();
            if (typeof loadAgenda === 'function') loadAgenda();
            if (typeof loadFinanceData === 'function') loadFinanceData();
        } else {
            alert(data.error || "Error al eliminar la consulta.");
        }
    } catch (err) {
        console.error("Error al eliminar consulta:", err);
        alert("Error de conexión al eliminar la consulta.");
    }
}
window.deleteConsultationFromHistory = deleteConsultationFromHistory;

async function renderFullCalendar() {
    const calendarEl = document.getElementById('full-calendar-agenda');
    if (!calendarEl) return;
    
    try {
        const [resEvents, resBlocks] = await Promise.all([
            fetch('/api/agenda'),
            fetch('/api/agenda/blocks')
        ]);
        const list = resEvents.ok ? await resEvents.json() : [];
        const blocksList = resBlocks.ok ? await resBlocks.json() : [];
        
        const events = list.map(e => {
            if (!e.fecha || !e.hora || e.estado_pago === 'Prepagada') return null;
            
            let color = '#4f46e5'; // Indigo (Pendiente / Agendada)
            if (e.has_session) {
                color = '#6b7280'; // Gris (Evolucionada)
            } else if (e.estado_pago.startsWith('Cancelada')) {
                color = '#ef4444'; // Rojo (Cancelada)
            } else if (e.confirmada === 1) {
                color = '#10b981'; // Verde (Confirmada)
            }
            
            const startStr = `${e.fecha}T${e.hora.substring(0, 5)}:00`;
            const startDt = new Date(startStr);
            if (isNaN(startDt.getTime())) return null;
            const endDt = new Date(startDt.getTime() + 60 * 60 * 1000);
            
            const confirmText = e.confirmada === 1 ? '✓ Confirmada' : '? Pendiente';
            
            return {
                id: e.id.toString(),
                title: `${e.nombres} ${e.apellidos} (${e.tipo_consulta}) - ${confirmText}`,
                start: startStr,
                end: endDt.toISOString(),
                backgroundColor: color,
                borderColor: color,
                textColor: '#ffffff',
                extendedProps: {
                    rawEvent: e
                }
            };
        }).filter(ev => ev !== null);

        // Mapear eventos personales / bloqueos de agenda
        const blockEvents = blocksList.map(b => {
            const startStr = b.todo_el_dia ? `${b.fecha}` : `${b.fecha}T${(b.hora_inicio || '08:00').substring(0, 5)}:00`;
            const endStr = b.todo_el_dia ? undefined : `${b.fecha}T${(b.hora_fin || '18:00').substring(0, 5)}:00`;
            return {
                id: `block_${b.id}`,
                title: `🔒 Bloqueo: ${b.motivo}`,
                start: startStr,
                ...(endStr ? { end: endStr } : {}),
                allDay: b.todo_el_dia === 1,
                backgroundColor: '#f59e0b',
                borderColor: '#d97706',
                textColor: '#ffffff',
                extendedProps: {
                    isBlock: true,
                    rawBlock: b
                }
            };
        });

        const allCalendarEvents = [...events, ...blockEvents];
        
        if (fullCalendarInstance) {
            fullCalendarInstance.destroy();
        }
        
        fullCalendarInstance = new FullCalendar.Calendar(calendarEl, {
            initialView: 'dayGridMonth',
            locale: 'es',
            headerToolbar: {
                left: 'prev,next today',
                center: 'title',
                right: 'dayGridMonth,timeGridWeek,timeGridDay'
            },
            buttonText: {
                today: 'Hoy',
                month: 'Mes',
                week: 'Semana',
                day: 'Día'
            },
            events: allCalendarEvents,
            eventClick: function(info) {
                if (info.event.extendedProps.isBlock) {
                    const b = info.event.extendedProps.rawBlock;
                    const horStr = b.todo_el_dia ? 'Todo el día' : `${b.hora_inicio} - ${b.hora_fin}`;
                    if (confirm(`🔒 Evento Personal / Bloqueo\n\nMotivo: ${b.motivo}\nFecha: ${b.fecha}\nHorario: ${horStr}\n\n¿Desea eliminar este bloqueo de la agenda?`)) {
                        deleteAgendaBlock(b.id);
                    }
                    return;
                }
                const raw = info.event.extendedProps.rawEvent;
                if (!raw.has_session && !raw.estado_pago.startsWith('Cancelada')) {
                    openRegisterSessionFromEvent(raw.id);
                } else {
                    alert(`Consulta de ${raw.nombres} ${raw.apellidos}\nFecha: ${raw.fecha} ${raw.hora}\nModalidad: ${raw.tipo_consulta}\nEstado Pago: ${raw.estado_pago}\nConfirmada: ${raw.confirmada === 1 ? 'Sí' : 'No'}`);
                }
            }
        });
        
        fullCalendarInstance.render();
    } catch (err) {
        console.error("Error al renderizar FullCalendar:", err);
    }
}

async function loadAdminRates() {
    const container = document.getElementById('rates-container');
    if (!container) return;
    container.innerHTML = '<span class="text-secondary text-sm">Cargando tarifas y honorarios...</span>';
    
    try {
        const res = await fetch('/api/admin/availability');
        if (!res.ok) return;
        const data = await res.json();
        
        const perfiles = data.perfiles || [];
        const tarifas = data.tarifas || {};
        const paquetes = data.paquetes || {};
        
        container.innerHTML = '';
        
        if (perfiles.length === 0) {
            container.innerHTML = '<span class="text-secondary text-sm">Crea perfiles de horario en la pestaña "Horarios de Atención" primero para asociarles costos.</span>';
            return;
        }
        
        perfiles.forEach(p => {
            const modName = p.nombre;
            const tVal = tarifas[modName] || { costo: 0.0, moneda: 'USD' };
            const pVal = paquetes[modName] || { ofrecer: false, sesiones: 4, costo: 0.0, moneda: 'USD' };
            
            const item = document.createElement('div');
            item.className = 'rate-modality-block';
            item.style.border = '1px solid var(--border-color)';
            item.style.borderRadius = 'var(--radius-md)';
            item.style.padding = '1.25rem';
            item.style.backgroundColor = 'var(--card-bg)';
            item.style.boxShadow = 'var(--shadow-sm)';
            item.style.marginBottom = '1.5rem';
            
            item.innerHTML = `
                <h4 class="mb-3" style="font-weight:700; color:var(--primary-color); border-bottom:1.5px solid var(--border-color); padding-bottom:0.4rem; margin:0 0 1rem 0;">${modName}</h4>
                
                <div class="form-row mb-3">
                    <div class="form-group col-6">
                        <label style="font-weight:600;">Costo de Consulta Individual *</label>
                        <input type="number" class="mod-rate-cost" data-mod="${modName}" step="0.01" min="0" value="${tVal.costo}" style="width:100%;">
                    </div>
                    <div class="form-group col-6">
                        <label style="font-weight:600;">Moneda *</label>
                        <select class="mod-rate-currency" data-mod="${modName}" style="width:100%; padding:0.65rem; border-radius:var(--radius-sm); border:1.5px solid var(--border-color); font-weight:600;">
                            <option value="USD" ${tVal.moneda === 'USD' ? 'selected' : ''}>USD ($)</option>
                            <option value="EUR" ${tVal.moneda === 'EUR' ? 'selected' : ''}>EUR (€)</option>
                            <option value="BSD" ${tVal.moneda === 'BSD' ? 'selected' : ''}>BSD (Bs.)</option>
                            <option value="ARS" ${tVal.moneda === 'ARS' ? 'selected' : ''}>ARS ($ ARS)</option>
                            <option value="COP" ${tVal.moneda === 'COP' ? 'selected' : ''}>COP ($ COP)</option>
                            <option value="CLP" ${tVal.moneda === 'CLP' ? 'selected' : ''}>CLP ($ CLP)</option>
                            <option value="MXN" ${tVal.moneda === 'MXN' ? 'selected' : ''}>MXN ($ MXN)</option>
                            <option value="DOP" ${tVal.moneda === 'DOP' ? 'selected' : ''}>DOP (RD$)</option>
                            <option value="PEN" ${tVal.moneda === 'PEN' ? 'selected' : ''}>PEN (S/)</option>
                            <option value="UYU" ${tVal.moneda === 'UYU' ? 'selected' : ''}>UYU ($ UYU)</option>
                        </select>
                    </div>
                </div>
                
                <div style="border-top: 1px dashed var(--border-color); padding-top:1rem; margin-top:1rem;">
                    <div style="display:flex; align-items:center; gap:0.5rem; margin-bottom:0.75rem;">
                        <input type="checkbox" class="mod-pkg-offer" data-mod="${modName}" id="pkg-offer-${modName}" ${pVal.ofrecer ? 'checked' : ''} onchange="togglePkgInputs('${modName}')" style="width:auto; cursor:pointer;">
                        <label for="pkg-offer-${modName}" style="font-weight:700; margin:0; cursor:pointer;">Ofrecer Paquete Prepagado</label>
                    </div>
                    
                    <div class="form-row mod-pkg-inputs-${modName} ${pVal.ofrecer ? '' : 'hide'}">
                        <div class="form-group col-4">
                            <label style="font-weight:600;">Cantidad de Sesiones</label>
                            <input type="number" class="mod-pkg-sessions" data-mod="${modName}" min="1" value="${pVal.sesiones || 4}" style="width:100%;">
                        </div>
                        <div class="form-group col-4">
                            <label style="font-weight:600;">Costo del Paquete</label>
                            <input type="number" class="mod-pkg-cost" data-mod="${modName}" step="0.01" min="0" value="${pVal.costo}" style="width:100%;">
                        </div>
                        <div class="form-group col-4">
                            <label style="font-weight:600;">Moneda del Paquete</label>
                            <select class="mod-pkg-currency" data-mod="${modName}" style="width:100%; padding:0.65rem; border-radius:var(--radius-sm); border:1.5px solid var(--border-color); font-weight:600;">
                                <option value="USD" ${pVal.moneda === 'USD' ? 'selected' : ''}>USD ($)</option>
                                <option value="EUR" ${pVal.moneda === 'EUR' ? 'selected' : ''}>EUR (€)</option>
                                <option value="BSD" ${pVal.moneda === 'BSD' ? 'selected' : ''}>BSD (Bs.)</option>
                                <option value="ARS" ${pVal.moneda === 'ARS' ? 'selected' : ''}>ARS ($ ARS)</option>
                                <option value="COP" ${pVal.moneda === 'COP' ? 'selected' : ''}>COP ($ COP)</option>
                                <option value="CLP" ${pVal.moneda === 'CLP' ? 'selected' : ''}>CLP ($ CLP)</option>
                                <option value="MXN" ${pVal.moneda === 'MXN' ? 'selected' : ''}>MXN ($ MXN)</option>
                                <option value="DOP" ${pVal.moneda === 'DOP' ? 'selected' : ''}>DOP (RD$)</option>
                                <option value="PEN" ${pVal.moneda === 'PEN' ? 'selected' : ''}>PEN (S/)</option>
                                <option value="UYU" ${pVal.moneda === 'UYU' ? 'selected' : ''}>UYU ($ UYU)</option>
                            </select>
                        </div>
                    </div>
                </div>
            `;
            container.appendChild(item);
        });
    } catch (e) {
        console.error("Error al cargar tarifas:", e);
    }
}

function togglePkgInputs(modName) {
    const checked = document.getElementById(`pkg-offer-${modName}`).checked;
    const inputs = document.querySelector(`.mod-pkg-inputs-${modName}`);
    if (inputs) {
        if (checked) {
            inputs.classList.remove('hide');
        } else {
            inputs.classList.add('hide');
        }
    }
}

async function handleSaveRates(e) {
    e.preventDefault();
    const statusMsg = document.getElementById('rates-status-msg');
    if (statusMsg) statusMsg.classList.add('hide');
    
    const tarifas = {};
    const paquetes = {};
    
    const costInputs = document.querySelectorAll('.mod-rate-cost');
    costInputs.forEach(input => {
        const mod = input.getAttribute('data-mod');
        const costo = parseFloat(input.value) || 0.0;
        const selectCur = document.querySelector(`.mod-rate-currency[data-mod="${mod}"]`);
        const moneda = selectCur ? selectCur.value : 'USD';
        tarifas[mod] = { costo, moneda };
    });
    
    const pkgChecks = document.querySelectorAll('.mod-pkg-offer');
    pkgChecks.forEach(check => {
        const mod = check.getAttribute('data-mod');
        const ofrecer = check.checked;
        const sessionsInput = document.querySelector(`.mod-pkg-sessions[data-mod="${mod}"]`);
        const costInput = document.querySelector(`.mod-pkg-cost[data-mod="${mod}"]`);
        const currencySelect = document.querySelector(`.mod-pkg-currency[data-mod="${mod}"]`);
        
        const sesiones = sessionsInput ? parseInt(sessionsInput.value) || 4 : 4;
        const costo = costInput ? parseFloat(costInput.value) || 0.0 : 0.0;
        const moneda = currencySelect ? currencySelect.value : 'USD';
        
        paquetes[mod] = { ofrecer, sesiones, costo, moneda };
    });
    
    try {
        const res = await fetch('/api/admin/rates', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ tarifas, paquetes })
        });
        const data = await res.json();
        
        if (res.ok && statusMsg) {
            statusMsg.textContent = '¡Tarifas y honorarios guardados con éxito!';
            statusMsg.className = 'status-msg success-msg';
            statusMsg.classList.remove('hide');
        } else if (statusMsg) {
            statusMsg.textContent = data.error || 'Error al guardar tarifas.';
            statusMsg.className = 'status-msg error-msg';
            statusMsg.classList.remove('hide');
        }
    } catch (err) {
        if (statusMsg) {
            statusMsg.textContent = 'Error de conexión con el servidor.';
            statusMsg.className = 'status-msg error-msg';
            statusMsg.classList.remove('hide');
        }
    }
}

// ==========================================
// AGENDA COMPLETA
// ==========================================
async function loadAgenda() {
    const tbody = document.getElementById('agenda-table-body');
    tbody.innerHTML = '<tr><td colspan="6" class="text-center text-secondary">Cargando cronograma...</td></tr>';
    
    try {
        const [resEvents, resBlocks] = await Promise.all([
            fetch('/api/agenda'),
            fetch('/api/agenda/blocks')
        ]);
        const list = resEvents.ok ? await resEvents.json() : [];
        const blocksList = resBlocks.ok ? await resBlocks.json() : [];
        
        tbody.innerHTML = '';
        
        if (list.length === 0 && blocksList.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="text-center text-secondary">No hay citas ni bloqueos en agenda.</td></tr>';
            return;
        }

        // Renderizar Bloqueos de Agenda primero si existen
        blocksList.forEach(b => {
            const tr = document.createElement('tr');
            const horStr = b.todo_el_dia ? 'Todo el día' : `${b.hora_inicio} - ${b.hora_fin}`;
            tr.innerHTML = `
                <td><strong>${b.fecha} (${horStr})</strong></td>
                <td><span style="color: #d97706; font-weight:600;">🔒 Evento Personal / Bloqueo</span></td>
                <td>${b.motivo}</td>
                <td>-</td>
                <td><span class="badge badge-warning" style="background-color:#f59e0b; color:white;">Bloqueado</span></td>
                <td class="actions-cell">
                    <button class="btn btn-secondary btn-sm text-danger" onclick="deleteAgendaBlock(${b.id})">Eliminar Bloqueo</button>
                </td>
            `;
            tbody.appendChild(tr);
        });
        
        list.forEach(e => {
            if (e.estado_pago === 'Prepagada') return; // Omitir paquetes prepagados en el calendario de citas
            if (e.has_session) return; // Omitir consultas ya atendidas (evolucionadas)
            
            const tr = document.createElement('tr');
            const paymentBadgeClass = e.estado_pago === 'Paga' ? 'badge-success' : (e.estado_pago === 'Pendiente' ? 'badge-danger' : 'badge-info');
            
            const btnEvolucionar = !e.has_session 
                ? `<button class="btn btn-primary btn-sm" onclick="openRegisterSessionFromEvent(${e.id})">Evolucionar</button>` 
                : '';
            const showMonto = e.estado_pago === 'Agendada' ? '-' : `${e.monto} ${e.moneda}`;
            const confirmBadge = e.confirmada === 1 
                ? ` <span class="badge bg-success" style="font-size: 0.65rem; padding: 0.15rem 0.35rem; color: white; border-radius: 4px; font-weight: bold; background-color: #15803d; margin-left: 0.35rem;">✓ Confirmada</span>`
                : '';
                
            tr.innerHTML = `
                <td><strong>${e.fecha} ${e.hora}</strong></td>
                <td>${e.nombres} ${e.apellidos}${confirmBadge}</td>
                <td>${e.tipo_consulta}</td>
                <td>${showMonto}</td>
                <td><span class="badge ${paymentBadgeClass}">${e.estado_pago}</span></td>
                <td class="actions-cell">
                    ${btnEvolucionar}
                    <button class="btn btn-secondary btn-sm" onclick="openEditEventModal(${e.id})">Editar</button>
                    <button class="btn btn-secondary btn-sm text-danger" onclick="cancelEvent(${e.id})">Cancelar</button>
                </td>
            `;
            tbody.appendChild(tr);
        });
    } catch (err) {
        tbody.innerHTML = '<tr><td colspan="6" class="text-center text-danger">Error de conexión al cargar agenda.</td></tr>';
    }
}

async function openNewEventModal(defaultPaid = false, initialType = 'consulta') {
    document.getElementById('event-form').reset();
    document.getElementById('event-form-id').value = '';
    
    const submitBtn = document.getElementById('event-submit-btn');
    if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.textContent = (initialType === 'bloqueo') ? 'Guardar Evento / Bloqueo' : 'Guardar en Agenda';
    }

    const tipoRegSelect = document.getElementById('e-tipo-registro');
    if (tipoRegSelect) {
        tipoRegSelect.value = initialType;
        if (typeof toggleEventTypeFields === 'function') toggleEventTypeFields(initialType);
    }
    
    const waActions = document.getElementById('event-whatsapp-actions');
    if (waActions) waActions.classList.add('hide');
    
    const searchInput = document.getElementById('e-paciente-search');
    if (searchInput) searchInput.value = '';
    
    await loadPatientsDropdowns(); // Garantizar carga de pacientes
    await loadModalityDropdownOptions();
    
    const select = document.getElementById('e-paciente');
    if (select) {
        for (let i = 0; i < select.options.length; i++) {
            select.options[i].style.display = '';
        }
    }
    
    const todayStr = new Date().toISOString().split('T')[0];
    document.getElementById('e-fecha').value = todayStr;
    const blockFechaEl = document.getElementById('e-block-fecha') || document.getElementById('e-fecha-bloqueo');
    if (blockFechaEl) blockFechaEl.value = todayStr;
    
    // Asignar hora actual aproximada
    const now = new Date();
    const hr = String(now.getHours()).padStart(2, '0');
    document.getElementById('e-hora').value = `${hr}:00`;
    
    if (defaultPaid) {
        document.getElementById('e-estado').value = 'Paga';
        toggleControlUsoField('Paga');
        document.getElementById('e-finance-fields').classList.remove('hide');
        document.getElementById('event-modal-title').textContent = "Registrar Cita / Pago";
    } else {
        document.getElementById('e-estado').value = 'Agendada';
        document.getElementById('e-finance-fields').classList.add('hide');
        document.getElementById('event-modal-title').textContent = (initialType === 'bloqueo') ? "Registrar Evento Personal / Bloqueo" : "Registrar Cita en Agenda";
    }
    
    document.getElementById('e-cant-sesiones').value = 1;
    document.getElementById('e-fecha-pago').value = '';
    document.getElementById('e-metodo').value = '';
    document.getElementById('e-referencia').value = '';
    
    document.getElementById('e-monto').disabled = false;
    document.getElementById('e-cant-sesiones').disabled = false;
    const optConsumir = document.getElementById('opt-consumir-prepago');
    if (optConsumir) optConsumir.style.display = 'none';
    
    const alertsDiv = document.getElementById('e-paciente-alerts');
    if (alertsDiv) {
        alertsDiv.classList.add('hide');
        alertsDiv.innerHTML = '';
    }
    
    if (tipoRegSelect) {
        tipoRegSelect.value = initialType;
        toggleEventTypeFields(initialType);
    }

    document.getElementById('e-control-uso-row').classList.add('hide');
    document.getElementById('e-confirmada').checked = false;
    document.getElementById('e-confirmada').disabled = true;
    document.getElementById('e-confirmada-disabled-msg').textContent = '(Se habilita al editar una cita agendada)';
    openModal('event-modal');
    setTimeout(updateEventTimezoneConversion, 100);
}

async function openEditEventModal(eventId) {
    try {
        const res = await fetch(`/api/finance/transactions/${eventId}`);
        if (!res.ok) throw new Error("Cita/transacción no encontrada.");
        const e = await res.json();
        
        const searchInput = document.getElementById('e-paciente-search');
        if (searchInput) searchInput.value = '';
        
        await loadPatientsDropdowns();
        await loadModalityDropdownOptions();
        
        const select = document.getElementById('e-paciente');
        if (select) {
            for (let i = 0; i < select.options.length; i++) {
                select.options[i].style.display = '';
            }
        }
        document.getElementById('e-finance-fields').classList.remove('hide');
        
        const waActions = document.getElementById('event-whatsapp-actions');
        if (waActions) waActions.classList.remove('hide');
        
        document.getElementById('event-form-id').value = e.id;
        document.getElementById('e-paciente').value = e.paciente_id;
        document.getElementById('e-fecha').value = e.fecha;
        document.getElementById('e-hora').value = e.hora;
        document.getElementById('e-tipo').value = e.tipo_consulta;
        document.getElementById('e-monto').value = e.monto;
        document.getElementById('e-moneda').value = e.moneda;
        document.getElementById('e-estado').value = e.estado_pago;
        document.getElementById('e-cant-sesiones').value = e.cantidad_sesiones || 1;
        document.getElementById('e-fecha-pago').value = e.fecha_pago || '';
        document.getElementById('e-metodo').value = e.metodo_pago || '';
        document.getElementById('e-referencia').value = e.referencia || '';
        
        // Validar antelación para el botón de confirmación
        try {
            const availRes = await fetch('/api/admin/availability');
            const availData = availRes.ok ? await availRes.json() : {};
            const alertaConfirmacionHoras = availData.alerta_confirmacion !== undefined ? parseInt(availData.alerta_confirmacion) : 24;
            
            document.getElementById('e-confirmada').checked = e.confirmada === 1;
            
            const sessionDateTime = new Date(`${e.fecha}T${e.hora}`);
            const now = new Date();
            const diffHours = (sessionDateTime - now) / (1000 * 60 * 60);
            
            if (diffHours <= alertaConfirmacionHoras) {
                document.getElementById('e-confirmada').disabled = false;
                document.getElementById('e-confirmada-disabled-msg').textContent = '¡Disponible para confirmar!';
                document.getElementById('e-confirmada-disabled-msg').style.color = '#15803d'; // Green
            } else {
                document.getElementById('e-confirmada').disabled = true;
                document.getElementById('e-confirmada-disabled-msg').textContent = `(Disponible ${alertaConfirmacionHoras}h antes de la cita)`;
                document.getElementById('e-confirmada-disabled-msg').style.color = '#b45309'; // Amber
            }
        } catch (confErr) {
            console.error("Error al validar alerta de confirmación:", confErr);
            document.getElementById('e-confirmada').disabled = true;
        }

        // Verificar prepagos y zona horaria para el paciente
        await checkPatientPrepayments(e.paciente_id);
        
        if (e.estado_pago === 'ConsumirPrepago' || (e.estado_pago === 'Paga' && e.monto === 0)) {
            document.getElementById('e-monto').disabled = true;
            document.getElementById('e-cant-sesiones').disabled = true;
        } else {
            document.getElementById('e-monto').disabled = false;
            document.getElementById('e-cant-sesiones').disabled = false;
        }
        
        if (e.estado_pago === 'Prepagada') {
            document.getElementById('e-control-uso-row').classList.remove('hide');
            document.getElementById('e-control-uso').value = e.control_uso || 'No consumida';
            document.getElementById('e-liquidacion').value = e.fecha_liquidacion || '';
        } else {
            document.getElementById('e-control-uso-row').classList.add('hide');
        }
        
        document.getElementById('event-modal-title').textContent = "Editar Cita / Transacción";
        openModal('event-modal');
        setTimeout(updateEventTimezoneConversion, 100);
    } catch (err) {
        alert(err.message);
    }
}

async function openNewEventModalFromSummary(patientId) {
    closeModal('summary-modal');
    await openNewEventModal(true);
    document.getElementById('e-paciente').value = patientId;
    await checkPatientPrepayments(patientId);
}

function toggleControlUsoField(status) {
    const row = document.getElementById('e-control-uso-row');
    const hourInput = document.getElementById('e-hora');
    const hourGroup = hourInput ? hourInput.parentElement : null;
    const tipoSelect = document.getElementById('e-tipo');
    
    if (status === 'Prepagada') {
        if (row) {
            row.classList.remove('hide');
            document.getElementById('e-control-uso').value = 'No consumida';
            document.getElementById('e-liquidacion').value = new Date().toISOString().split('T')[0];
        }
        
        if (tipoSelect) {
            if (![...tipoSelect.options].some(o => o.value === 'Prepago')) {
                const opt = document.createElement('option');
                opt.value = 'Prepago';
                opt.textContent = 'Prepago (Paquete)';
                tipoSelect.appendChild(opt);
            }
            tipoSelect.value = 'Prepago';
        }
        if (hourInput) hourInput.value = '00:00';
        if (hourGroup) hourGroup.style.display = 'none';
    } else {
        if (row) row.classList.add('hide');
        if (hourGroup) hourGroup.style.display = 'block';
        if (tipoSelect && tipoSelect.value === 'Prepago') {
            tipoSelect.value = 'Presencial';
        }
    }
}

// ==========================================
// CONVERTIDOR DE ZONA HORARIA (AGENDAR CITA)
// ==========================================

const COUNTRY_TIMEZONE_MAP = {
    'PORTUGAL': 'Europe/Lisbon',
    'ESPAÑA': 'Europe/Madrid',
    'SPAIN': 'Europe/Madrid',
    'ALEMANIA': 'Europe/Berlin',
    'GERMANY': 'Europe/Berlin',
    'FRANCIA': 'Europe/Paris',
    'FRANCE': 'Europe/Paris',
    'ITALIA': 'Europe/Rome',
    'ITALY': 'Europe/Rome',
    'REINO UNIDO': 'Europe/London',
    'UK': 'Europe/London',
    'SUIZA': 'Europe/Zurich',
    'SWITZERLAND': 'Europe/Zurich',
    'COLOMBIA': 'America/Bogota',
    'PERU': 'America/Lima',
    'PERÚ': 'America/Lima',
    'ECUADOR': 'America/Guayaquil',
    'ARGENTINA': 'America/Buenos_Aires',
    'CHILE': 'America/Santiago',
    'VENEZUELA': 'America/Caracas',
    'REPUBLICA DOMINICANA': 'America/Santo_Domingo',
    'REPÚBLICA DOMINICANA': 'America/Santo_Domingo',
    'DOMINICAN REPUBLIC': 'America/Santo_Domingo',
    'EEUU': 'America/New_York',
    'ESTADOS UNIDOS': 'America/New_York',
    'USA': 'America/New_York',
    'CANADÁ': 'America/Toronto',
    'CANADA': 'America/Toronto',
    'MEXICO': 'America/Mexico_City',
    'MÉXICO': 'America/Mexico_City',
    'PANAMA': 'America/Panama',
    'PANAMÁ': 'America/Panama',
    'COSTA RICA': 'America/Costa_Rica',
    'URUGUAY': 'America/Montevideo',
    'PARAGUAY': 'America/Asuncion',
    'BOLIVIA': 'America/La_Paz',
    'BRASIL': 'America/Sao_Paulo',
    'BRAZIL': 'America/Sao_Paulo',
    'GUATEMALA': 'America/Guatemala',
    'HONDURAS': 'America/Tegucigalpa',
    'EL SALVADOR': 'America/El_Salvador',
    'NICARAGUA': 'America/Managua',
    'PUERTO RICO': 'America/Puerto_Rico',
    'CUBA': 'America/Havana'
};

function toggleEventTimezoneOptions() {
    const opts = document.getElementById('e-tz-options-row');
    if (opts) opts.classList.toggle('hide');
}

function autoDetectPatientTimezone(countryOrResidence) {
    if (!countryOrResidence) return;
    const cleanStr = String(countryOrResidence).toUpperCase().trim();
    for (const [key, tz] of Object.entries(COUNTRY_TIMEZONE_MAP)) {
        if (cleanStr.includes(key)) {
            const patientTzSelect = document.getElementById('e-tz-patient');
            if (patientTzSelect) {
                patientTzSelect.value = tz;
                updateEventTimezoneConversion();
            }
            break;
        }
    }
}

function updateEventTimezoneConversion() {
    const fechaInp = document.getElementById('e-fecha');
    const horaInp = document.getElementById('e-hora');
    const thTzSelect = document.getElementById('e-tz-therapist');
    const paTzSelect = document.getElementById('e-tz-patient');
    const thDisplay = document.getElementById('e-tz-therapist-display');
    const paDisplay = document.getElementById('e-tz-patient-display');

    if (!fechaInp || !horaInp || !thDisplay || !paDisplay) return;

    const fecha = fechaInp.value;
    const hora = horaInp.value;

    if (!fecha || !hora) {
        thDisplay.textContent = '--:--';
        paDisplay.textContent = '--:--';
        return;
    }

    const thTz = thTzSelect ? thTzSelect.value : 'America/Caracas';
    const paTz = paTzSelect ? paTzSelect.value : 'Europe/Madrid';

    try {
        const dtStr = `${fecha}T${hora}:00`;
        const localDate = new Date(dtStr);

        const thTzName = thTz.split('/')[1] ? thTz.split('/')[1].replace('_', ' ') : thTz;
        thDisplay.textContent = `${hora} (${thTzName})`;

        const formatter = new Intl.DateTimeFormat('es-ES', {
            timeZone: paTz,
            hour: '2-digit',
            minute: '2-digit',
            hour12: true
        });

        const formattedTime = formatter.format(localDate);

        // Check if date changes
        const thDayNum = parseInt(fecha.split('-')[2], 10);
        const dayFormatter = new Intl.DateTimeFormat('es-ES', { timeZone: paTz, day: '2-digit' });
        const paDayNum = parseInt(dayFormatter.format(localDate), 10);

        let diffDayNotice = '';
        if (paDayNum > thDayNum || (thDayNum > 27 && paDayNum === 1)) {
            diffDayNotice = ' ☀️ (+1 día)';
        } else if (paDayNum < thDayNum || (thDayNum === 1 && paDayNum > 27)) {
            diffDayNotice = ' 🌙 (-1 día)';
        }

        const paTzName = paTz.split('/')[1] ? paTz.split('/')[1].replace('_', ' ') : paTz;
        paDisplay.textContent = `${formattedTime}${diffDayNotice} (${paTzName})`;
    } catch (err) {
        console.error('Error updating timezone conversion:', err);
        paDisplay.textContent = '--:--';
    }
}
window.toggleEventTimezoneOptions = toggleEventTimezoneOptions;
window.updateEventTimezoneConversion = updateEventTimezoneConversion;
window.autoDetectPatientTimezone = autoDetectPatientTimezone;

function toggleEventTypeFields(val) {
    const citaFields = document.getElementById('e-consultation-section') || document.getElementById('event-cita-fields');
    const bloqueoFields = document.getElementById('e-block-section') || document.getElementById('event-bloqueo-fields');
    const financeFields = document.getElementById('e-finance-fields');
    const submitBtn = document.getElementById('event-submit-btn');

    if (val === 'bloqueo') {
        if (citaFields) citaFields.classList.add('hide');
        if (bloqueoFields) bloqueoFields.classList.remove('hide');
        if (financeFields) financeFields.classList.add('hide');
        if (submitBtn) submitBtn.textContent = 'Guardar Evento / Bloqueo';
        
        const blockFecha = document.getElementById('e-block-fecha') || document.getElementById('e-fecha-bloqueo');
        if (blockFecha && !blockFecha.value) {
            blockFecha.value = new Date().toISOString().split('T')[0];
        }
    } else {
        if (citaFields) citaFields.classList.remove('hide');
        if (bloqueoFields) bloqueoFields.classList.add('hide');
        if (submitBtn) submitBtn.textContent = 'Guardar Cita';
    }
}

function toggleBlockTimeInputs(isAllDay) {
    const timeRow = document.getElementById('e-block-hours-row') || document.getElementById('e-bloqueo-horario-row');
    if (timeRow) {
        if (isAllDay) {
            timeRow.classList.add('hide');
        } else {
            timeRow.classList.remove('hide');
        }
    }
}

async function deleteAgendaBlock(blockId) {
    if (!confirm('¿Deseas eliminar este evento personal / bloqueo de agenda?')) return;
    try {
        const res = await fetch(`/api/agenda/blocks/${blockId}`, { method: 'DELETE' });
        const data = await res.json();
        if (res.ok) {
            alert(data.success);
            if (activeView === 'agenda') {
                renderFullCalendar();
                loadAgenda();
            }
        } else {
            alert(data.error || 'Error al eliminar bloqueo.');
        }
    } catch (err) {
        alert('Error de conexión al eliminar bloqueo.');
    }
}

window.toggleEventTypeFields = toggleEventTypeFields;
window.toggleBlockTimeInputs = toggleBlockTimeInputs;
window.deleteAgendaBlock = deleteAgendaBlock;

async function handleEventSubmit(e) {
    e.preventDefault();
    
    const tipoRegistro = document.getElementById('e-tipo-registro') ? document.getElementById('e-tipo-registro').value : 'cita';
    
    if (tipoRegistro === 'bloqueo') {
        const blockFechaEl = document.getElementById('e-block-fecha') || document.getElementById('e-fecha-bloqueo');
        const blockTodoDiaEl = document.getElementById('e-block-todo-dia') || document.getElementById('e-bloqueo-todo-dia');
        const blockHoraInicioEl = document.getElementById('e-block-hora-inicio') || document.getElementById('e-bloqueo-hora-inicio');
        const blockHoraFinEl = document.getElementById('e-block-hora-fin') || document.getElementById('e-bloqueo-hora-fin');
        const blockMotivoEl = document.getElementById('e-block-motivo') || document.getElementById('e-bloqueo-motivo');

        const payload = {
            fecha: blockFechaEl ? blockFechaEl.value : '',
            todo_el_dia: blockTodoDiaEl ? blockTodoDiaEl.checked : false,
            hora_inicio: blockHoraInicioEl ? blockHoraInicioEl.value : '08:00',
            hora_fin: blockHoraFinEl ? blockHoraFinEl.value : '18:00',
            motivo: blockMotivoEl ? blockMotivoEl.value : ''
        };
        
        try {
            const res = await fetch('/api/agenda/blocks', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            if (res.ok) {
                let msg = data.success;
                if (data.google_synced) {
                    msg += " (Sincronizado con Google Calendar)";
                }
                alert(msg);
                closeModal('event-modal');
                if (activeView === 'agenda') {
                    renderFullCalendar();
                    loadAgenda();
                }
            } else {
                alert(data.error || 'Error al guardar bloqueo.');
            }
        } catch (err) {
            alert('Error de conexión al guardar bloqueo.');
        }
        return;
    }

    const id = document.getElementById('event-form-id').value;
    
    const payload = {
        paciente_id: document.getElementById('e-paciente').value,
        fecha: document.getElementById('e-fecha').value,
        hora: document.getElementById('e-hora').value,
        tipo_consulta: document.getElementById('e-tipo').value,
        monto: parseFloat(document.getElementById('e-monto').value || 0.0),
        moneda: document.getElementById('e-moneda').value,
        estado_pago: document.getElementById('e-estado').value,
        control_uso: document.getElementById('e-control-uso').value || 'Consumida',
        cantidad_sesiones: parseInt(document.getElementById('e-cant-sesiones').value || 1),
        fecha_pago: document.getElementById('e-fecha-pago').value,
        metodo_pago: document.getElementById('e-metodo').value,
        referencia: document.getElementById('e-referencia').value,
        confirmada: document.getElementById('e-confirmada').checked ? 1 : 0
    };
    
    const method = id ? 'PUT' : 'POST';
    const endpoint = id ? `/api/finance/transactions/${id}` : '/api/agenda';
    
    try {
        const res = await fetch(endpoint, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        
        if (res.ok) {
            let msg = data.success;
            if (data.google_synced) {
                msg += " (Sincronizado con Google Calendar)";
            }
            alert(msg);
            closeModal('event-modal');
            
            loadDashboardStats();
            loadFinanceData();
            if (activeView === 'agenda') {
                renderFullCalendar();
                loadAgenda();
            }
            if (activeView === 'dashboard') loadAgendaCompact();
        } else {
            alert(data.error);
        }
    } catch (err) {
        alert("Error de conexión al guardar cita/pago.");
    }
}

async function cancelEvent(eventId) {
    if (!confirm("¿Está seguro de que desea cancelar y eliminar esta cita de la agenda? Si fue sincronizada, se eliminará del calendario de Google.")) return;
    
    try {
        const res = await fetch(`/api/agenda/${eventId}`, { method: 'DELETE' });
        const data = await res.json();
        if (res.ok) {
            alert(data.success);
            loadAgenda();
        } else {
            alert(data.error);
        }
    } catch (err) {
        alert("Error al cancelar cita.");
    }
}

// ==========================================
// CONFIGURACIÓN DE DISPONIBILIDAD DEL PSICÓLOGO
// ==========================================
// Helper para crear fila de rango de horas
function createRangeRow(parentContainer, inicioVal = "", finVal = "") {
    const row = document.createElement('div');
    row.className = 'avail-range-row';
    row.style.display = 'flex';
    row.style.alignItems = 'center';
    row.style.gap = '0.5rem';
    row.style.marginTop = '0.25rem';
    
    const startInput = document.createElement('input');
    startInput.type = 'time';
    startInput.className = 'range-start';
    startInput.value = inicioVal || '08:00';
    startInput.required = true;
    startInput.style.padding = '0.25rem';
    startInput.style.borderRadius = 'var(--radius-sm)';
    startInput.style.border = '1px solid var(--border-color)';
    
    const labelTo = document.createElement('span');
    labelTo.textContent = 'a';
    labelTo.style.fontSize = '0.85rem';
    labelTo.style.color = 'var(--text-muted)';
    
    const endInput = document.createElement('input');
    endInput.type = 'time';
    endInput.className = 'range-end';
    endInput.value = finVal || '12:00';
    endInput.required = true;
    endInput.style.padding = '0.25rem';
    endInput.style.borderRadius = 'var(--radius-sm)';
    endInput.style.border = '1px solid var(--border-color)';
    
    const delBtn = document.createElement('button');
    delBtn.type = 'button';
    delBtn.textContent = '✕';
    delBtn.style.background = 'none';
    delBtn.style.border = 'none';
    delBtn.style.color = '#ef4444';
    delBtn.style.fontSize = '1rem';
    delBtn.style.cursor = 'pointer';
    delBtn.style.padding = '0.25rem';
    
    delBtn.onclick = () => {
        row.remove();
    };
    
    row.appendChild(startInput);
    row.appendChild(labelTo);
    row.appendChild(endInput);
    row.appendChild(delBtn);
    parentContainer.appendChild(row);
}

// Renderizar un perfil de horario en forma de tarjeta
function renderProfileBlock(container, profileData) {
    const card = document.createElement('div');
    card.className = 'avail-profile-card';
    card.setAttribute('data-id', profileData.id);
    card.style.border = '1.5px solid var(--border-color)';
    card.style.borderRadius = 'var(--radius-md)';
    card.style.padding = '1.25rem';
    card.style.marginBottom = '1.5rem';
    card.style.backgroundColor = 'var(--card-bg)';
    card.style.boxShadow = '0 2px 8px rgba(0,0,0,0.02)';
    
    // Grid de días de la semana
    const daysList = document.createElement('div');
    daysList.className = 'profile-days-list';
    daysList.style.display = 'flex'; // Desplegado por defecto para visualización clara
    daysList.style.flexDirection = 'column';
    daysList.style.gap = '0.75rem';
    daysList.style.marginTop = '0.75rem';
    
    // Cabecera del perfil
    const header = document.createElement('div');
    header.style.display = 'flex';
    header.style.justifyContent = 'space-between';
    header.style.alignItems = 'center';
    header.style.gap = '1rem';
    header.style.borderBottom = '1.5px solid var(--border-color)';
    header.style.paddingBottom = '0.75rem';
    
    const leftPart = document.createElement('div');
    leftPart.style.display = 'flex';
    leftPart.style.gap = '0.5rem';
    leftPart.style.alignItems = 'center';
    leftPart.style.flex = '1';
    
    // Botón de flecha desplegable
    const toggleBtn = document.createElement('button');
    toggleBtn.type = 'button';
    toggleBtn.innerHTML = '▼';
    toggleBtn.style.background = 'none';
    toggleBtn.style.border = 'none';
    toggleBtn.style.cursor = 'pointer';
    toggleBtn.style.padding = '0.25rem 0.5rem';
    toggleBtn.style.fontSize = '0.8rem';
    toggleBtn.style.color = 'var(--text-muted)';
    toggleBtn.style.transform = 'rotate(0deg)';
    toggleBtn.style.transition = 'transform 0.2s';
    
    toggleBtn.onclick = () => {
        if (daysList.style.display === 'none') {
            daysList.style.display = 'flex';
            toggleBtn.style.transform = 'rotate(0deg)';
        } else {
            daysList.style.display = 'none';
            toggleBtn.style.transform = 'rotate(-90deg)';
        }
    };
    
    // Input de Nombre
    const nameInput = document.createElement('input');
    nameInput.type = 'text';
    nameInput.className = 'profile-name';
    nameInput.value = profileData.nombre;
    nameInput.placeholder = 'Nombre del Horario';
    nameInput.required = true;
    nameInput.style.fontWeight = '700';
    nameInput.style.fontSize = '1.1rem';
    nameInput.style.padding = '0.2rem 0.4rem';
    nameInput.style.border = 'none';
    nameInput.style.borderBottom = '1.5px dashed transparent';
    nameInput.style.backgroundColor = 'transparent';
    nameInput.style.outline = 'none';
    nameInput.style.width = '170px';
    nameInput.style.color = 'var(--text-color)';
    nameInput.style.transition = 'border-color 0.2s';
    
    nameInput.onmouseover = () => { nameInput.style.borderBottomColor = 'var(--border-color)'; };
    nameInput.onmouseout = () => { if (document.activeElement !== nameInput) nameInput.style.borderBottomColor = 'transparent'; };
    nameInput.onfocus = () => { nameInput.style.borderBottomColor = 'var(--primary-color)'; };
    nameInput.onblur = () => { nameInput.style.borderBottomColor = 'transparent'; };
    
    // Icono de editar
    const editIcon = document.createElement('span');
    editIcon.innerHTML = '✏️';
    editIcon.style.cursor = 'pointer';
    editIcon.style.fontSize = '0.85rem';
    editIcon.style.opacity = '0.5';
    editIcon.style.marginRight = '0.5rem';
    editIcon.style.transition = 'opacity 0.2s';
    editIcon.onmouseover = () => { editIcon.style.opacity = '1'; };
    editIcon.onmouseout = () => { editIcon.style.opacity = '0.5'; };
    editIcon.onclick = () => { nameInput.focus(); };
    
    // Selector de Modalidad
    const modSelect = document.createElement('select');
    modSelect.className = 'profile-modalidad';
    modSelect.style.display = 'none';
    modSelect.style.padding = '0.35rem 0.5rem';
    modSelect.style.border = '1.5px solid var(--border-color)';
    modSelect.style.borderRadius = 'var(--radius-sm)';
    modSelect.style.fontWeight = '600';
    modSelect.style.fontSize = '0.9rem';
    
    const optOnline = document.createElement('option');
    optOnline.value = 'Online';
    optOnline.textContent = 'Online';
    if (profileData.modalidad === 'Online') optOnline.selected = true;
    
    const optPresencial = document.createElement('option');
    optPresencial.value = 'Presencial';
    optPresencial.textContent = 'Presencial';
    if (profileData.modalidad === 'Presencial') optPresencial.selected = true;
    
    modSelect.appendChild(optOnline);
    modSelect.appendChild(optPresencial);
    
    leftPart.appendChild(toggleBtn);
    leftPart.appendChild(nameInput);
    leftPart.appendChild(editIcon);
    leftPart.appendChild(modSelect);
    
    const delProfileBtn = document.createElement('button');
    delProfileBtn.type = 'button';
    delProfileBtn.className = 'btn text-xs';
    delProfileBtn.textContent = '✕ Eliminar Perfil';
    delProfileBtn.style.backgroundColor = 'rgba(239, 68, 68, 0.08)';
    delProfileBtn.style.color = '#ef4444';
    delProfileBtn.style.border = 'none';
    delProfileBtn.style.padding = '0.4rem 0.6rem';
    delProfileBtn.style.borderRadius = 'var(--radius-sm)';
    delProfileBtn.style.fontWeight = '700';
    delProfileBtn.style.cursor = 'pointer';
    delProfileBtn.onclick = () => {
        card.remove();
    };
    
    header.appendChild(leftPart);
    header.appendChild(delProfileBtn);
    card.appendChild(header);
    
    const diasList = (profileData && Array.isArray(profileData.dias)) ? profileData.dias : [
        {"dia": 1, "nombre": "Lunes", "activo": false, "rangos": []},
        {"dia": 2, "nombre": "Martes", "activo": false, "rangos": []},
        {"dia": 3, "nombre": "Miércoles", "activo": false, "rangos": []},
        {"dia": 4, "nombre": "Jueves", "activo": false, "rangos": []},
        {"dia": 5, "nombre": "Viernes", "activo": false, "rangos": []},
        {"dia": 6, "nombre": "Sábado", "activo": false, "rangos": []},
        {"dia": 0, "nombre": "Domingo", "activo": false, "rangos": []}
    ];
    diasList.forEach(day => {
        const dayRow = document.createElement('div');
        dayRow.className = 'profile-day-row';
        dayRow.setAttribute('data-dia', day.dia);
        dayRow.style.display = 'flex';
        dayRow.style.flexDirection = 'column';
        dayRow.style.gap = '0.4rem';
        dayRow.style.padding = '0.75rem';
        dayRow.style.borderRadius = 'var(--radius-sm)';
        dayRow.style.border = '1px solid var(--border-color)';
        dayRow.style.backgroundColor = day.activo ? 'rgba(16, 185, 129, 0.02)' : 'var(--bg-light)';
        
        const dayHeader = document.createElement('div');
        dayHeader.style.display = 'flex';
        dayHeader.style.justifyContent = 'space-between';
        dayHeader.style.alignItems = 'center';
        
        const dayLeft = document.createElement('div');
        dayLeft.style.display = 'flex';
        dayLeft.style.alignItems = 'center';
        dayLeft.style.gap = '0.5rem';
        
        const check = document.createElement('input');
        check.type = 'checkbox';
        check.className = 'day-check';
        check.checked = day.activo;
        check.id = `check-${profileData.id}-${day.dia}`;
        
        const label = document.createElement('label');
        label.htmlFor = `check-${profileData.id}-${day.dia}`;
        label.textContent = day.nombre;
        label.style.fontWeight = '700';
        label.style.fontSize = '0.9rem';
        label.style.cursor = 'pointer';
        label.style.margin = '0';
        
        dayLeft.appendChild(check);
        dayLeft.appendChild(label);
        dayHeader.appendChild(dayLeft);
        
        const dayRanges = document.createElement('div');
        dayRanges.className = 'day-ranges-container';
        dayRanges.style.display = day.activo ? 'flex' : 'none';
        dayRanges.style.flexDirection = 'column';
        dayRanges.style.gap = '0.4rem';
        
        const listRanges = document.createElement('div');
        listRanges.className = 'day-list-ranges';
        dayRanges.appendChild(listRanges);
        
        if (day.rangos && day.rangos.length > 0) {
            day.rangos.forEach(r => {
                createRangeRow(listRanges, r.inicio, r.fin);
            });
        } else {
            createRangeRow(listRanges, '08:00', '12:00');
        }
        
        const addRangeBtn = document.createElement('button');
        addRangeBtn.type = 'button';
        addRangeBtn.className = 'btn text-xs btn-secondary';
        addRangeBtn.style.alignSelf = 'flex-start';
        addRangeBtn.style.padding = '0.2rem 0.5rem';
        addRangeBtn.textContent = '+ Agregar Bloque';
        addRangeBtn.onclick = () => {
            const hasExisting = listRanges.children.length > 0;
            createRangeRow(listRanges, hasExisting ? '14:00' : '08:00', hasExisting ? '18:00' : '12:00');
        };
        dayRanges.appendChild(addRangeBtn);
        
        check.onchange = () => {
            if (check.checked) {
                dayRanges.style.display = 'flex';
                dayRow.style.backgroundColor = 'rgba(16, 185, 129, 0.02)';
            } else {
                dayRanges.style.display = 'none';
                dayRow.style.backgroundColor = 'var(--bg-light)';
            }
        };
        
        dayRow.appendChild(dayHeader);
        dayRow.appendChild(dayRanges);
        daysList.appendChild(dayRow);
    });
    
    card.appendChild(daysList);
    container.appendChild(card);
}

function toggleCancelRuleInputs() {
    const tipo = document.getElementById('avail-limite-cancelacion-tipo').value;
    const hoursGroup = document.getElementById('cancel-rule-value-hours-group');
    const timeGroup = document.getElementById('cancel-rule-value-time-group');
    
    if (tipo === 'horas') {
        hoursGroup.classList.remove('hide');
        timeGroup.classList.add('hide');
    } else {
        hoursGroup.classList.add('hide');
        timeGroup.classList.remove('hide');
    }
}

async function loadAdminAvailability() {
    const listContainer = document.getElementById('availability-days-list');
    if (!listContainer) return;
    
    listContainer.innerHTML = '<span class="text-secondary text-sm">Cargando disponibilidad...</span>';
    
    try {
        const res = await fetch('/api/admin/availability');
        const data = await res.json();
        
        document.getElementById('avail-duracion').value = data.duracion || 60;
        document.getElementById('avail-receso').value = data.receso || 15;
        document.getElementById('avail-antelacion').value = data.antelacion !== undefined ? data.antelacion : 24;
        document.getElementById('avail-tiempo-confirmacion').value = data.alerta_confirmacion !== undefined ? data.alerta_confirmacion : 24;
        document.getElementById('avail-tiempo-cierre').value = data.alerta_cierre !== undefined ? data.alerta_cierre : 2;
        
        const cTipo = data.limite_cancelacion_tipo || 'horas';
        const cVal = data.limite_cancelacion_valor !== undefined ? data.limite_cancelacion_valor : (data.limite_cancelacion !== undefined ? data.limite_cancelacion : 24);
        
        document.getElementById('avail-limite-cancelacion-tipo').value = cTipo;
        if (cTipo === 'horas') {
            document.getElementById('avail-limite-cancelacion').value = cVal;
        } else {
            document.getElementById('avail-limite-cancelacion-time').value = cVal;
        }
        toggleCancelRuleInputs();
        
        listContainer.innerHTML = '';
        
        const perfiles = (data && Array.isArray(data.perfiles)) ? data.perfiles : [];
        perfiles.forEach(perf => {
            renderProfileBlock(listContainer, perf);
        });
        
        // Agregar botón de "+ Crear Perfil de Horario" al final
        const addProfileBtn = document.createElement('button');
        addProfileBtn.type = 'button';
        addProfileBtn.className = 'btn';
        addProfileBtn.style.width = '100%';
        addProfileBtn.style.marginTop = '1rem';
        addProfileBtn.style.border = '2px dashed var(--primary-color)';
        addProfileBtn.style.color = 'var(--primary-color)';
        addProfileBtn.style.backgroundColor = 'transparent';
        addProfileBtn.style.fontWeight = '700';
        addProfileBtn.style.padding = '0.75rem';
        addProfileBtn.style.cursor = 'pointer';
        addProfileBtn.textContent = '+ Crear Perfil de Horario';
        
        addProfileBtn.onclick = () => {
            const newPerf = {
                id: 'perf_' + Date.now(),
                nombre: 'Nuevo Horario',
                modalidad: 'Online',
                dias: [
                    {"dia": 1, "nombre": "Lunes", "activo": false, "rangos": []},
                    {"dia": 2, "nombre": "Martes", "activo": false, "rangos": []},
                    {"dia": 3, "nombre": "Miércoles", "activo": false, "rangos": []},
                    {"dia": 4, "nombre": "Jueves", "activo": false, "rangos": []},
                    {"dia": 5, "nombre": "Viernes", "activo": false, "rangos": []},
                    {"dia": 6, "nombre": "Sábado", "activo": false, "rangos": []},
                    {"dia": 0, "nombre": "Domingo", "activo": false, "rangos": []}
                ]
            };
            renderProfileBlock(listContainer, newPerf);
            // Mover el botón al final de nuevo
            listContainer.appendChild(addProfileBtn);
        };
        
        listContainer.appendChild(addProfileBtn);
        
    } catch (err) {
        listContainer.innerHTML = '<span class="text-secondary text-sm" style="color:red;">Error al cargar disponibilidad.</span>';
    }
}

async function handleSaveAvailability(e) {
    e.preventDefault();
    const statusMsg = document.getElementById('availability-status-msg');
    statusMsg.classList.add('hide');
    
    const duracion = parseInt(document.getElementById('avail-duracion').value);
    const receso = parseInt(document.getElementById('avail-receso').value);
    const antelacion = parseInt(document.getElementById('avail-antelacion').value);
    const alerta_confirmacion = parseInt(document.getElementById('avail-tiempo-confirmacion').value);
    const alerta_recordatorio = parseInt(document.getElementById('avail-tiempo-recordatorio').value);
    const alerta_cierre = parseInt(document.getElementById('avail-tiempo-cierre').value);
    const limite_cancelacion_tipo = document.getElementById('avail-limite-cancelacion-tipo').value;
    const limite_cancelacion_valor = limite_cancelacion_tipo === 'horas' 
        ? parseInt(document.getElementById('avail-limite-cancelacion').value || 24)
        : document.getElementById('avail-limite-cancelacion-time').value;
    
    const profileCards = document.querySelectorAll('.avail-profile-card');
    const perfiles = [];
    
    profileCards.forEach(card => {
        const id = card.getAttribute('data-id');
        const nombre = card.querySelector('.profile-name').value;
        const modalidad = nombre; // El nombre del perfil corresponde automáticamente a la modalidad
        
        const dias = [];
        const dayRows = card.querySelectorAll('.profile-day-row');
        
        dayRows.forEach(row => {
            const dia = parseInt(row.getAttribute('data-dia'));
            const name = row.querySelector('label').textContent;
            const activo = row.querySelector('.day-check').checked;
            
            const rangos = [];
            if (activo) {
                const rangeRows = row.querySelectorAll('.avail-range-row');
                rangeRows.forEach(rRow => {
                    const inicio = rRow.querySelector('.range-start').value;
                    const fin = rRow.querySelector('.range-end').value;
                    if (inicio && fin) {
                        rangos.push({ inicio, fin });
                    }
                });
            }
            
            dias.push({
                dia,
                nombre: name,
                activo,
                rangos
            });
        });
        
        perfiles.push({
            id,
            nombre,
            modalidad,
            dias
        });
    });
    
    try {
        const res = await fetch('/api/admin/availability', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ duracion, receso, perfiles, antelacion, alerta_confirmacion, alerta_recordatorio, alerta_cierre, limite_cancelacion_tipo, limite_cancelacion_valor })
        });
        
        const data = await res.json();
        
        if (res.ok) {
            statusMsg.textContent = '¡Disponibilidad y bloques de perfiles calculados y guardados con éxito!';
            statusMsg.className = 'status-msg success-msg';
            statusMsg.classList.remove('hide');
            
            loadAdminAvailability();
        } else {
            statusMsg.textContent = data.error || 'Error al guardar disponibilidad.';
            statusMsg.className = 'status-msg error-msg';
            statusMsg.classList.remove('hide');
        }
    } catch (err) {
        statusMsg.textContent = 'Error de conexión con el servidor.';
        statusMsg.className = 'status-msg error-msg';
        statusMsg.classList.remove('hide');
    }
}

// ==========================================
// GOOGLE CALENDAR SYNC & STATUS
// ==========================================
async function checkGoogleStatus() {
    try {
        const res = await fetch('/api/google/status');
        const data = await res.json();
        
        const badge = document.getElementById('google-status-badge');
        const instr = document.getElementById('google-config-instructions');
        const btns = document.getElementById('google-action-buttons');
        
        btns.innerHTML = '';
        
        if (data.configured) {
            badge.textContent = "Conectado";
            badge.className = "badge badge-success";
            instr.classList.add('hide');
            
            btns.innerHTML = `
                <button class="btn btn-secondary btn-block" onclick="syncGoogleCalendar()">
                    Sincronizar Agenda Ahora
                </button>
            `;
        } else {
            badge.textContent = "No conectado";
            badge.className = "badge badge-danger";
            
            if (data.has_credentials_json) {
                instr.classList.add('hide');
                btns.innerHTML = `
                    <a href="/api/google/authorize" target="_blank" class="btn btn-primary btn-block text-center" style="display:inline-block; width:100%; box-sizing:border-box;">
                        Autorizar Cuenta de Google
                    </a>
                `;
            } else {
                instr.classList.remove('hide');
                btns.innerHTML = `
                    <div style="border: 2px dashed var(--border-color); padding: 1.25rem; border-radius: var(--radius-md); text-align: center; background: rgba(0,0,0,0.02); margin-top: 1rem;">
                        <p style="margin: 0 0 1rem 0; font-size: 0.85rem; font-weight: 700; color: var(--text-dark);">
                            Falta credentials.json en el servidor
                        </p>
                        <input type="file" id="google-json-upload" accept=".json" style="display:none;" onchange="handleGoogleJsonUpload(this)" />
                        <button type="button" class="btn btn-secondary btn-sm" onclick="document.getElementById('google-json-upload').click()" style="font-weight:700;">
                            📁 Subir credentials.json desde tu dispositivo
                        </button>
                    </div>
                `;
            }
        }
    } catch (err) {
        console.error("Error al obtener estado de Google:", err);
    }
}

async function handleGoogleJsonUpload(input) {
    if (!input.files || input.files.length === 0) return;
    const file = input.files[0];
    const formData = new FormData();
    formData.append('file', file);
    
    showLoadingScreen();
    try {
        const res = await fetch('/api/google/upload-credentials', {
            method: 'POST',
            body: formData
        });
        const data = await res.json();
        hideLoadingScreen();
        
        if (data.success) {
            alert("✅ ¡Archivo credentials.json instalado con éxito! Ahora puedes autorizar tu cuenta.");
            checkGoogleStatus();
        } else {
            alert("❌ Error: " + (data.error || "No se pudo subir el archivo."));
        }
    } catch(err) {
        hideLoadingScreen();
        alert("❌ Error al conectar con el servidor: " + err.message);
    }
}
window.handleGoogleJsonUpload = handleGoogleJsonUpload;

async function syncGoogleCalendar() {
    const btn = document.querySelector('[onclick="syncGoogleCalendar()"]');
    const oldText = btn ? btn.innerHTML : 'Sincronizar';
    
    if (btn) {
        btn.disabled = true;
        btn.textContent = "Sincronizando...";
    }
    
    try {
        const res = await fetch('/api/google/sync', { method: 'POST' });
        const data = await res.json();
        
        if (res.ok) {
            alert(data.success);
            if (activeView === 'agenda') loadAgenda();
            if (activeView === 'dashboard') loadAgendaCompact();
        } else {
            alert(data.error);
        }
    } catch (err) {
        alert("Error de conexión al sincronizar con Google Calendar.");
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = oldText;
        }
    }
}

// ==========================================
// BACKUP / RESPALDO Y RESTAURACIÓN
// ==========================================
async function handleRestoreSubmit(e) {
    e.preventDefault();
    const fileInput = document.getElementById('restore-file');
    const file = fileInput.files[0];
    const statusMsg = document.getElementById('restore-status-msg');
    
    if (!file) return;
    
    if (!confirm("ADVERTENCIA: Si restauras una copia de seguridad anterior, REEMPLAZARÁS por completo toda la base de datos actual con todos los registros actuales de pacientes, evoluciones y finanzas. ¿Quieres continuar?")) {
        return;
    }
    
    statusMsg.classList.add('hide');
    
    const formData = new FormData();
    formData.append('file', file);
    
    try {
        const res = await fetch('/api/restore', {
            method: 'POST',
            body: formData
        });
        const data = await res.json();
        
        if (res.ok) {
            statusMsg.textContent = data.success;
            statusMsg.className = "status-msg text-success";
            statusMsg.classList.remove('hide');
            alert(data.success);
            // Recargar app para re-cargar BD
            window.location.reload();
        } else {
            statusMsg.textContent = data.error;
            statusMsg.className = "status-msg text-danger";
            statusMsg.classList.remove('hide');
        }
    } catch (err) {
        statusMsg.textContent = "Error al conectar con el servidor.";
        statusMsg.className = "status-msg text-danger";
        statusMsg.classList.remove('hide');
    }
}

// ==========================================
// INTERACCIONES CON ELEMENTOS MODALES
// ==========================================
function openModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.remove('hide');
        modal.style.setProperty('display', 'flex', 'important');
    }
}
window.openModal = openModal;

function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.add('hide');
        modal.style.removeProperty('display');
        modal.style.display = 'none';
        document.body.style.overflow = '';
    }
}
window.closeModal = closeModal;

async function checkPatientPrepayments(patientId) {
    const optConsumir = document.getElementById('opt-consumir-prepago');
    const alertsDiv = document.getElementById('e-paciente-alerts');
    if (!optConsumir) return;
    
    if (!patientId) {
        optConsumir.style.display = 'none';
        if (alertsDiv) {
            alertsDiv.classList.add('hide');
            alertsDiv.innerHTML = '';
        }
        return;
    }
    
    try {
        const res = await fetch(`/api/patients/${patientId}/summary`);
        if (!res.ok) return;
        const summary = await res.json();
        
        if (summary && summary.patient) {
            autoDetectPatientTimezone(summary.patient.pais || summary.patient.residencia_actual);
        }
        
        // CORRECCIÓN: Usar la clave correcta 'finance'
        const prepagas = summary.finance.prepagadas_no_consumidas || 0;
        const pendientes = summary.finance.pendientes || 0;
        
        let alertHTML = '';
        
        if (prepagas > 0) {
            optConsumir.style.display = 'block';
            optConsumir.textContent = `Descontar de Prepago (${prepagas} disponibles)`;
            
            alertHTML += `
                <div style="background-color: rgba(40, 167, 69, 0.1); color: #1e7e34; padding: 0.5rem 0.75rem; border-radius: 6px; border: 1px solid rgba(40, 167, 69, 0.2); display: flex; align-items: center; justify-content: space-between;">
                    <span>El consultante tiene <strong>${prepagas}</strong> consultas prepagadas disponibles.</span>
                    <button type="button" class="btn btn-success btn-sm" style="padding: 2px 8px; font-size: 0.75rem;" onclick="applyPrepaymentDiscount()">Aplicar Prepago</button>
                </div>
            `;
        } else {
            optConsumir.style.display = 'none';
            if (document.getElementById('e-estado').value === 'ConsumirPrepago') {
                document.getElementById('e-estado').value = 'Pendiente';
                document.getElementById('e-monto').disabled = false;
                document.getElementById('e-cant-sesiones').disabled = false;
                toggleControlUsoField('Pendiente');
            }
        }
        
        if (pendientes > 0) {
            const mStr = summary.finance && summary.finance.deuda_monto_str ? ` (${summary.finance.deuda_monto_str})` : '';
            alertHTML += `
                <div style="background-color: rgba(220, 53, 69, 0.1); color: #bd2130; padding: 0.5rem 0.75rem; border-radius: 6px; border: 1px solid rgba(220, 53, 69, 0.2);">
                    ⚠️ <strong>Atención:</strong> El consultante tiene <strong>${pendientes}</strong> citas o cancelaciones tardías pendientes por cobrar<strong>${mStr}</strong>.
                </div>
            `;
        }
        
        if (alertsDiv) {
            if (alertHTML) {
                alertsDiv.innerHTML = alertHTML;
                alertsDiv.classList.remove('hide');
            } else {
                alertsDiv.classList.add('hide');
                alertsDiv.innerHTML = '';
            }
        }
        
        await updateEventModalFee();
    } catch (err) {
        console.error("Error al verificar prepagos y deudas:", err);
    }
}

async function updateEventModalFee() {
    const patientId = document.getElementById('e-paciente').value;
    if (!patientId) return;
    
    try {
        const res = await fetch(`/api/patients/${patientId}/summary`);
        if (!res.ok) return;
        const summary = await res.json();
        
        if (summary.profile && summary.profile.costo_personalizado !== null && summary.profile.costo_personalizado !== undefined) {
            document.getElementById('e-monto').value = summary.profile.costo_personalizado;
            document.getElementById('e-moneda').value = summary.profile.moneda_personalizada || 'USD';
        } else {
            const selectedMod = document.getElementById('e-tipo').value;
            const avRes = await fetch('/api/admin/availability');
            if (avRes.ok) {
                const avData = await avRes.json();
                const tarifas = avData.tarifas || {};
                if (tarifas[selectedMod]) {
                    document.getElementById('e-monto').value = tarifas[selectedMod].costo;
                    document.getElementById('e-moneda').value = tarifas[selectedMod].moneda;
                } else {
                    document.getElementById('e-monto').value = '0.00';
                }
            }
        }
    } catch (e) {
        console.error("Error al actualizar tarifa del modal:", e);
    }
}

function applyPrepaymentDiscount() {
    const eEstado = document.getElementById('e-estado');
    if (eEstado) {
        eEstado.value = 'ConsumirPrepago';
        // Desencadenar evento de cambio
        eEstado.dispatchEvent(new Event('change'));
    }
}

async function checkSessionPatientPrepayments(patientId) {
    return await checkPrepaymentsAndDebtsForSession(patientId);
}

async function checkPrepaymentsAndDebtsForSession(patientId) {
    const alertsDiv = document.getElementById('s-paciente-alerts');
    const optConsumir = document.getElementById('s-opt-descontar-prepago');
    const optFraccionado = document.getElementById('s-opt-vincular-fraccionado');
    const selectLiq = document.getElementById('s-tipo-liq');
    const montoInput = document.getElementById('s-monto');
    const monedaSelect = document.getElementById('s-moneda');
    
    if (!patientId) {
        if (alertsDiv) {
            alertsDiv.classList.add('hide');
            alertsDiv.innerHTML = '';
        }
        if (optConsumir) optConsumir.style.display = 'none';
        if (optFraccionado) optFraccionado.style.display = 'none';
        return;
    }
    
    try {
        // Cargar tarifa personalizada por defecto si existe
        const resPatient = await fetch(`/api/patients/${patientId}`);
        if (resPatient.ok) {
            const patient = await resPatient.json();
            if (montoInput && (patient.costo_personalizado !== null && patient.costo_personalizado !== undefined)) {
                montoInput.value = Number(patient.costo_personalizado).toFixed(2);
            }
            if (monedaSelect && patient.moneda_personalizada) {
                monedaSelect.value = patient.moneda_personalizada;
            }
        }
        const resSummary = await fetch(`/api/patients/${patientId}/summary`);
        if (!resSummary.ok) return;
        const summary = await resSummary.json();
        
        const prepagas = summary.finance.prepagadas_no_consumidas || 0;
        const pendientes = summary.finance.pendientes || 0;
        const deudasDetalle = summary.finance.deudas_detalle || [];
        const deudaMontoStr = summary.finance.deuda_monto_str || '0.00 USD';
        
        let alertHTML = '';
        
        // 1. Detectar si hay deudas por pagos fraccionados/parciales de paquetes
        const deudasFraccionadas = deudasDetalle.filter(d => 
            (d.tipo_consulta && d.tipo_consulta.toLowerCase().includes('fraccionad')) ||
            (d.referencia && (d.referencia.toLowerCase().includes('parcial') || d.referencia.toLowerCase().includes('fraccionad')))
        );
        
        if (deudasFraccionadas.length > 0) {
            if (optFraccionado) optFraccionado.style.display = 'block';
            const totalFrac = deudasFraccionadas.reduce((sum, d) => sum + (Number(d.monto) || 0), 0);
            const currFrac = deudasFraccionadas[0]?.moneda || 'USD';
            
            alertHTML += `
                <div style="background-color: rgba(245, 158, 11, 0.12); color: #b45309; padding: 0.65rem 0.85rem; border-radius: 6px; border: 1px solid rgba(245, 158, 11, 0.3); display: flex; align-items: center; justify-content: space-between; gap: 0.5rem; flex-wrap: wrap;">
                    <span>📦 <strong>Saldo Pendiente por Pago Fraccionado / Paquete:</strong> <strong>${totalFrac.toFixed(2)} ${currFrac}</strong></span>
                    <button type="button" onclick="selectFraccionadoOption()" style="background: #b45309; color: white; border: none; padding: 0.25rem 0.6rem; border-radius: 4px; font-weight: 600; font-size: 0.78rem; cursor: pointer;">
                        ✓ Vincular a Paquete Fraccionado
                    </button>
                </div>
            `;
        } else {
            if (optFraccionado) optFraccionado.style.display = 'none';
        }
        
        // 2. Prepagos 100% verificados
        if (prepagas > 0) {
            if (optConsumir) optConsumir.style.display = 'block';
            optConsumir.textContent = `Descontar de Prepago (${prepagas} disponibles)`;
            
            alertHTML += `
                <div style="background-color: rgba(40, 167, 69, 0.1); color: #1e7e34; padding: 0.65rem 0.85rem; border-radius: 6px; border: 1px solid rgba(40, 167, 69, 0.2); display: flex; align-items: center; justify-content: space-between; gap: 0.5rem; flex-wrap: wrap;">
                    <span>El consultante tiene <strong>${prepagas}</strong> consultas prepagadas (paquete).</span>
                    <label style="display: flex; align-items: center; gap: 0.35rem; font-weight: 700; cursor: pointer; background: white; padding: 0.25rem 0.5rem; border-radius: 4px; border: 1px solid #28a745; color: #1e7e34; font-size: 0.8rem;">
                        <input type="checkbox" id="s-chk-prepago" onchange="togglePrepaymentCheckbox(this.checked)">
                        Cobrar de consultas prepagadas
                    </label>
                </div>
            `;
        } else {
            if (optConsumir) optConsumir.style.display = 'none';
            if (selectLiq && selectLiq.value === 'Descontar prepago') {
                selectLiq.value = deudasFraccionadas.length > 0 ? 'Vincular paquete fraccionado' : 'Dejar pendiente';
                toggleSessionFinanceInputs(selectLiq.value);
            }
        }
        
        // 3. Deudas estándar
        if (pendientes > 0 && deudasFraccionadas.length === 0) {
            alertHTML += `
                <div style="background-color: rgba(220, 53, 69, 0.1); color: #bd2130; padding: 0.5rem 0.75rem; border-radius: 6px; border: 1px solid rgba(220, 53, 69, 0.2);">
                    ⚠️ <strong>Atención:</strong> El consultante tiene <strong>${pendientes}</strong> citas o cargos anteriores pendientes por cobrar (Monto total: <strong>${deudaMontoStr}</strong>).
                </div>
            `;
        }
        
        if (alertsDiv) {
            if (alertHTML) {
                alertsDiv.innerHTML = alertHTML;
                alertsDiv.classList.remove('hide');
            } else {
                alertsDiv.classList.add('hide');
                alertsDiv.innerHTML = '';
            }
        }
    } catch (err) {
        console.error("Error al verificar prepagos y deudas en sesión:", err);
    }
}

function selectFraccionadoOption() {
    const select = document.getElementById('s-tipo-liq');
    if (select) {
        select.value = 'Vincular paquete fraccionado';
        toggleSessionFinanceInputs('Vincular paquete fraccionado');
    }
}

function togglePrepaymentCheckbox(checked) {
    const select = document.getElementById('s-tipo-liq');
    if (select) {
        select.value = checked ? 'Descontar prepago' : 'Dejar pendiente';
        toggleSessionFinanceInputs(select.value);
    }
}

function toggleSessionFinanceFields(status) {
    const finSection = document.getElementById('s-finance-fields') || document.getElementById('session-finance-section');
    const selectLiq = document.getElementById('s-tipo-liq');
    if (status === 'Cancelada con aviso' || status === 'Reprogramada') {
        if (finSection) finSection.style.display = 'none';
    } else {
        if (finSection) finSection.style.display = 'block';
        if (selectLiq) toggleSessionFinanceInputs(selectLiq.value);
    }
}
window.toggleSessionFinanceFields = toggleSessionFinanceFields;
window.toggleSessionFinanceInputs = toggleSessionFinanceInputs;

function toggleSessionFinanceInputs(tipo) {
    const isPrepay = (tipo === 'Descontar prepago');
    const isFraccionado = (tipo === 'Vincular paquete fraccionado');
    const isPending = (tipo === 'Dejar pendiente');
    const isExonerated = (tipo === 'Exonerar');
    
    const montoInput = document.getElementById('s-monto');
    const pagoDetallesRow = document.getElementById('s-pago-detalles-row');
    const pagoFechaRow = document.getElementById('s-pago-fecha-row');
    
    if (isPrepay || isFraccionado) {
        montoInput.value = '0.00';
        montoInput.disabled = true;
        if (pagoDetallesRow) pagoDetallesRow.style.display = 'none';
        if (pagoFechaRow) pagoFechaRow.style.display = 'none';
    } else if (isPending) {
        montoInput.disabled = false;
        if (pagoDetallesRow) pagoDetallesRow.style.display = 'none';
        if (pagoFechaRow) pagoFechaRow.style.display = 'none';
    } else if (isExonerated) {
        montoInput.value = '0.00';
        montoInput.disabled = true;
        if (pagoDetallesRow) pagoDetallesRow.style.display = 'none';
        if (pagoFechaRow) pagoFechaRow.style.display = 'none';
    } else { // Cobrar ahora
        montoInput.disabled = false;
        if (pagoDetallesRow) pagoDetallesRow.style.display = 'flex';
        if (pagoFechaRow) pagoFechaRow.style.display = 'flex';
    }
}

function filterSessionsPatientDropdown(query) {
    const select = document.getElementById('session-filter-patient');
    if (!select) return;
    
    for (let i = 0; i < options.length; i++) {
        const option = options[i];
        if (option.value === "") continue; // Saltar 'Todos los pacientes'
        
        const text = option.textContent.toLowerCase();
        if (text.includes(lowerQuery)) {
            option.style.display = ""; // Mostrar coincidencia
            if (!firstVisibleMatch) firstVisibleMatch = option.value;
        } else {
            option.style.display = "none"; // Ocultar
        }
    }
    
    if (query.trim() !== "") {
        if (firstVisibleMatch) {
            select.value = firstVisibleMatch;
            loadSessions(firstVisibleMatch);
        }
    } else {
        select.value = "";
        for (let i = 0; i < options.length; i++) {
            options[i].style.display = "";
        }
        loadSessions("");
    }
}

async function deleteFinancePayment(eventId) {
    if (!confirm("¿Está seguro de que desea eliminar este registro de pago/transacción?")) return;
    
    try {
        const res = await fetch(`/api/agenda/${eventId}`, { method: 'DELETE' });
        const data = await res.json();
        if (res.ok) {
            alert("Registro de pago/transacción eliminado con éxito.");
            loadDashboardStats();
            loadFinanceData();
            if (activeView === 'agenda') loadAgenda();
            if (activeView === 'dashboard') loadAgendaCompact();
        } else {
            alert(data.error);
        }
    } catch (err) {
        alert("Error al eliminar pago.");
    }
}

function filterModalPatientSelect(query) {
    const select = document.getElementById('s-paciente');
    if (!select) return;
    const options = select.options;
    const lowerQuery = query.toLowerCase();
    
    let firstVisibleMatch = null;
    
    for (let i = 0; i < options.length; i++) {
        const option = options[i];
        if (option.value === "") continue;
        
        const text = option.textContent.toLowerCase();
        if (text.includes(lowerQuery)) {
            option.style.display = "";
            if (!firstVisibleMatch) firstVisibleMatch = option.value;
        } else {
            option.style.display = "none";
        }
    }
    
    if (query.trim() !== "") {
        if (firstVisibleMatch && select.value !== firstVisibleMatch) {
            select.value = firstVisibleMatch;
            checkSessionPatientPrepayments(firstVisibleMatch);
            updateSessionPatientQuickInfo(firstVisibleMatch);
        }
    } else {
        for (let i = 0; i < options.length; i++) {
            options[i].style.display = "";
        }
    }
}

function filterEventPatientSelect(query) {
    const select = document.getElementById('e-paciente');
    if (!select) return;
    const options = select.options;
    const lowerQuery = query.toLowerCase();
    
    let firstVisibleMatch = null;
    
    for (let i = 0; i < options.length; i++) {
        const option = options[i];
        if (option.value === "") continue;
        
        const text = option.textContent.toLowerCase();
        if (text.includes(lowerQuery)) {
            option.style.display = "";
            if (!firstVisibleMatch) firstVisibleMatch = option.value;
        } else {
            option.style.display = "none";
        }
    }
    
    if (query.trim() !== "") {
        if (firstVisibleMatch && select.value !== firstVisibleMatch) {
            select.value = firstVisibleMatch;
            checkPatientPrepayments(firstVisibleMatch);
        }
    } else {
        for (let i = 0; i < options.length; i++) {
            options[i].style.display = "";
        }
    }
}

function downloadBackup() {
    try {
        const link = document.createElement('a');
        link.href = '/api/backup';
        link.download = '';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    } catch (err) {
        window.location.href = '/api/backup';
    }
}

async function uploadSessionFile(input) {
    const file = input.files[0];
    if (!file) return;
    
    const statusLabel = document.getElementById('s-archivo-adjunto-status');
    const hiddenFile = document.getElementById('s-archivo-adjunto');
    const deleteBtn = document.getElementById('s-archivo-adjunto-delete');
    
    statusLabel.textContent = "Subiendo archivo...";
    statusLabel.style.color = "var(--text-secondary)";
    
    const formData = new FormData();
    formData.append('file', file);
    
    try {
        const res = await fetch('/api/upload', {
            method: 'POST',
            body: formData
        });
        const data = await res.json();
        if (res.ok) {
            hiddenFile.value = data.filename;
            statusLabel.textContent = "✓ Archivo subido";
            statusLabel.style.color = "var(--success-color)";
            deleteBtn.classList.remove('hide');
        } else {
            statusLabel.textContent = "✗ Error de subida";
            statusLabel.style.color = "var(--danger-color)";
            alert(data.error || "Error al subir el archivo.");
            input.value = '';
        }
    } catch (err) {
        statusLabel.textContent = "✗ Error de conexión";
        statusLabel.style.color = "var(--danger-color)";
        alert("Error de conexión al subir el archivo.");
        input.value = '';
    }
}

function clearUploadedSessionFile() {
    const input = document.getElementById('s-archivo-adjunto-input');
    const hiddenFile = document.getElementById('s-archivo-adjunto');
    const statusLabel = document.getElementById('s-archivo-adjunto-status');
    const deleteBtn = document.getElementById('s-archivo-adjunto-delete');
    
    if (input) input.value = '';
    if (hiddenFile) hiddenFile.value = '';
    if (statusLabel) statusLabel.textContent = '';
    if (deleteBtn) deleteBtn.classList.add('hide');
}

function calculateAgeFromBirthdate(birthdateVal, targetId = 'p-edad') {
    if (!birthdateVal) return;
    const birthDate = new Date(birthdateVal);
    if (isNaN(birthDate.getTime())) return;
    const today = new Date();
    let age = today.getFullYear() - birthDate.getFullYear();
    const monthDiff = today.getMonth() - birthDate.getMonth();
    if (monthDiff < 0 || (monthDiff === 0 && today.getDate() < birthDate.getDate())) {
        age--;
    }
    if (age >= 0) {
        const target = document.getElementById(targetId);
        if (target) target.value = age;
    }
}

async function updateSessionPatientQuickInfo(patientId) {
    const quickInfoDiv = document.getElementById('s-paciente-quick-info');
    if (!quickInfoDiv) return;
    
    if (!patientId) {
        quickInfoDiv.innerHTML = '';
        quickInfoDiv.classList.add('hide');
        return;
    }
    
    try {
        const res = await fetch(`/api/patients/${patientId}/summary`);
        if (!res.ok) throw new Error();
        const data = await res.json();
        const p = data.patient;
        const lastSes = data.last_session;
        
        const antecedentsText = p.antecedentes_psicologicos_personales || p.antecedentes_medicos_personales || 'Ninguno registrado';
        const residenciaText = p.con_quien_reside ? `Con quién reside: ${p.con_quien_reside}` : 'Con quién reside: N/A';
        const residenciaActualText = `Residencia actual: ${formatPatientLocation(p)}`;
        
        let lastSessionSummaryHtml = '<strong>Sesión Anterior:</strong> <em>No hay evoluciones previas registradas.</em>';
        if (lastSes) {
            lastSessionSummaryHtml = `<strong>Sesión Anterior (${lastSes.fecha}):</strong> ${lastSes.resumen || 'Sin resumen'}`;
        }
        
        quickInfoDiv.innerHTML = `
            <div style="font-weight: 600; color: var(--primary-color); margin-bottom: 0.35rem; border-bottom: 1px solid var(--border-color); padding-bottom: 0.25rem; font-size: 0.9rem;">
                Nota de Referencia Terapéutica
            </div>
            <p style="margin: 0 0 0.5rem 0; color: var(--text-color); font-size: 0.85rem; line-height: 1.45;">
                <strong>Edad:</strong> ${p.edad || 'N/A'} años. &nbsp;|&nbsp; 
                <strong>Fecha Nacimiento:</strong> ${p.fecha_nacimiento || 'N/A'}. &nbsp;|&nbsp; 
                <strong>${residenciaText}</strong>. &nbsp;|&nbsp; 
                <strong>${residenciaActualText}</strong>. <br>
                <strong>Antecedentes:</strong> ${antecedentsText}.
            </p>
            <div style="background-color: rgba(169, 89, 147, 0.04); padding: 0.6rem 0.8rem; border-radius: 6px; border-left: 3.5px solid var(--primary-color); font-size: 0.85rem; word-break: break-word; color: var(--text-color);">
                ${lastSessionSummaryHtml}
            </div>
        `;
        quickInfoDiv.classList.remove('hide');
    } catch (err) {
        quickInfoDiv.innerHTML = '<span class="text-danger">Error al cargar ficha de referencia.</span>';
        quickInfoDiv.classList.remove('hide');
    }
}

// Helper: Formatear hora de 24h a 12h con AM/PM
function format12h(time24) {
    if (!time24 || !time24.includes(':')) return time24;
    const parts = time24.split(':');
    let h = parseInt(parts[0], 10);
    const mStr = parts[1];
    const ampm = h >= 12 ? 'PM' : 'AM';
    h = h % 12;
    h = h ? h : 12;
    return `${String(h).padStart(2, '0')}:${mStr} ${ampm}`;
}

// Cargar y mostrar pagos notificados por los pacientes para verificación en el portal del psicólogo
async function loadNotifiedPayments() {
    const tbody = document.getElementById('notified-payments-table-body');
    if (!tbody) return;
    
    tbody.innerHTML = '<tr><td colspan="5" class="text-center text-secondary">Cargando notificaciones...</td></tr>';
    
    try {
        const res = await fetch('/api/admin/payments/notified');
        if (!res.ok) throw new Error("Error al conectar con el servidor.");
        const notifiedList = await res.json();
        
        tbody.innerHTML = '';
        
        if (notifiedList.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="text-center text-secondary">No hay notificaciones de pago por verificar.</td></tr>';
            return;
        }
        
        notifiedList.forEach(p => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td><strong>${p.nombres} ${p.apellidos}</strong></td>
                <td>${p.fecha}</td>
                <td><span class="text-success" style="font-weight: 700;">${p.monto} ${p.moneda}</span></td>
                <td>
                    <div style="font-size:0.8rem; color:var(--text-muted);">
                        <span>Método: ${p.metodo}</span><br>
                        <span>Ref: ${p.referencia || 'N/A'}</span>
                    </div>
                </td>
                <td>
                    <button class="btn btn-primary btn-sm" onclick="openVerifyPaymentModal(${p.paciente_id}, ${p.id}, ${p.monto}, '${p.moneda}', '${p.metodo}', '${p.referencia}', '${p.fecha}')">Verificar</button>
                </td>
            `;
            tbody.appendChild(tr);
        });
        
        const badge = document.getElementById('fin-verificaciones-badge');
        if (badge) {
            if (notifiedList.length > 0) {
                badge.textContent = notifiedList.length;
                badge.classList.remove('hide');
            } else {
                badge.classList.add('hide');
            }
        }
        return; // Termina la función aquí
    } catch (err) {
        tbody.innerHTML = '<tr><td colspan="5" class="text-center text-secondary" style="color:red;">Error de sincronización con el servidor.</td></tr>';
    }
}

// Marcador temporal para mantener la coherencia del resto de la función:
async function loadNotifiedPaymentsOld() {
        
        notifiedList.forEach(p => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td><strong>${p.patientName}</strong></td>
                <td>${p.fecha}</td>
                <td><span class="text-success" style="font-weight: 700;">${p.monto} ${p.moneda}</span></td>
                <td>
                    <div style="font-size:0.8rem; color:var(--text-muted);">
                        <span>Método: ${p.metodo}</span><br>
                        <span>Ref: ${p.referencia || 'N/A'}</span>
                    </div>
                </td>
                <td>
                    <button class="btn btn-primary btn-sm" onclick="openVerifyPaymentModal(${p.patientId}, '${p.notificationKey}', ${p.monto}, '${p.moneda}', '${p.metodo}', '${p.referencia}', '${p.fecha}')">Verificar</button>
                </td>
            `;
            tbody.appendChild(tr);
        });
        
        const badge = document.getElementById('fin-verificaciones-badge');
        if (badge) {
            if (notifiedList.length > 0) {
                badge.textContent = notifiedList.length;
                badge.classList.remove('hide');
            } else {
                badge.classList.add('hide');
            }
        }
}

// Abrir modal de verificación de pago reportado
async function openVerifyPaymentModal(patientId, notificationKey, monto, moneda, metodo, referencia, fecha) {
    document.getElementById('v-patient-id').value = patientId;
    document.getElementById('v-notification-key').value = notificationKey;
    
    const reportedDiv = document.getElementById('v-reported-summary');
    reportedDiv.innerHTML = `
        <strong>Monto:</strong> ${monto} ${moneda}<br>
        <strong>Método:</strong> ${metodo}<br>
        <strong>Referencia:</strong> ${referencia || 'N/A'}<br>
        <strong>Fecha Pago:</strong> ${fecha}
    `;
    
    document.getElementById('v-monto').value = monto;
    document.getElementById('v-moneda').value = moneda;
    document.getElementById('v-metodo').value = metodo;
    document.getElementById('v-referencia').value = referencia;
    document.getElementById('v-fecha').value = fecha;
    
    document.getElementById('v-rejection-note-group').classList.add('hide');
    document.getElementById('v-rejection-note').value = '';
    
    openModal('verify-payment-modal');
}

function toggleVerifyPaymentAction(actionType) {
    const pendingGroup = document.getElementById('v-pending-session-group');
    if (actionType === 'debt') {
        pendingGroup.classList.remove('hide');
    } else {
        pendingGroup.classList.add('hide');
    }
}

// Acción: Registrar y Confirmar (Aprobar)
async function submitVerifyPayment(e) {
    e.preventDefault();
    
    const patientId = document.getElementById('v-patient-id').value;
    const notificationKey = document.getElementById('v-notification-key').value;
    const monto = parseFloat(document.getElementById('v-monto').value);
    const moneda = document.getElementById('v-moneda').value;
    const metodo = document.getElementById('v-metodo').value;
    const referencia = document.getElementById('v-referencia').value;
    const fecha = document.getElementById('v-fecha').value;
    const actionType = document.getElementById('v-action-type').value;
    
    try {
        // Verificar el pago localmente en SQLite (El backend automatiza liquidación de deuda y/o abono de prepago)
        const localVerifyRes = await fetch(`/api/admin/payments/verify/${notificationKey}`, {
            method: 'POST'
        });
        if (!localVerifyRes.ok) {
            const errData = await localVerifyRes.json();
            throw new Error(errData.error || "Error al verificar el pago en el servidor local");
        }
        
        // Intentar actualizar Firebase secundariamente
        try {
            await fetch(`https://espacio-terapeutico-default-rtdb.firebaseio.com/pacientes/${patientId}/pagos_notificados/${notificationKey}.json`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ estado: 'Verificado', fecha_verificacion: new Date().toISOString() })
            });
            
            await fetch(`https://espacio-terapeutico-default-rtdb.firebaseio.com/pacientes/${patientId}/notificaciones.json`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    tipo: 'pago',
                    titulo: 'Pago Confirmado',
                    mensaje: `Tu pago de ${monto} ${moneda} del ${fecha} ha sido verificado con éxito.`,
                    fecha: new Date().toISOString(),
                    leida: false
                })
            });
        } catch (ne) {
            console.error("Error al actualizar Firebase secundariamente:", ne);
        }
        
        alert("¡Pago verificado y registrado con éxito!");
        closeModal('verify-payment-modal');
        loadFinanceData();
        
    } catch (err) {
        alert("Error: " + err.message);
    }
}

// Acción: Rechazar (Volver a solicitar datos)
async function rejectNotifiedPayment(e) {
    e.preventDefault();
    
    const rejectionGroup = document.getElementById('v-rejection-note-group');
    if (rejectionGroup.classList.contains('hide')) {
        rejectionGroup.classList.remove('hide');
        document.getElementById('v-rejection-note').focus();
        alert("Por favor, introduce el motivo del rechazo en el campo que se acaba de mostrar y vuelve a presionar 'Volver a Solicitar Datos'.");
        return;
    }
    
    const note = document.getElementById('v-rejection-note').value.trim();
    if (!note) {
        alert("Debes escribir una nota explicando la razón del rechazo.");
        return;
    }
    
    const patientId = document.getElementById('v-patient-id').value;
    const notificationKey = document.getElementById('v-notification-key').value;
    
    try {
        const localRejectRes = await fetch(`/api/admin/payments/reject/${notificationKey}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ nota_rechazo: note })
        });
        if (!localRejectRes.ok) {
            const errData = await localRejectRes.json();
            throw new Error(errData.error || "Error al rechazar el pago en el servidor local");
        }
        
        // Intentar actualizar Firebase secundariamente
        try {
            await fetch(`https://espacio-terapeutico-default-rtdb.firebaseio.com/pacientes/${patientId}/pagos_notificados/${notificationKey}.json`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    estado: 'Requerir nuevos datos', 
                    nota_rechazo: note,
                    fecha_rechazo: new Date().toISOString() 
                })
            });
            
            await fetch(`https://espacio-terapeutico-default-rtdb.firebaseio.com/pacientes/${patientId}/notificaciones.json`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    tipo: 'pago',
                    titulo: 'Corrección de Pago Requerida',
                    mensaje: `Se requiere corregir el pago reportado. Razón: "${note}"`,
                    fecha: new Date().toISOString(),
                    leida: false
                })
            });
        } catch (ne) {
            console.error("Error al actualizar Firebase secundariamente:", ne);
        }
        
        alert("Solicitud de corrección enviada con éxito.");
        closeModal('verify-payment-modal');
        loadFinanceData();
    } catch (err) {
        alert("Error de conexión: " + err.message);
    }
}

// Cargar y mostrar historial de pagos notificados en el portal del paciente
async function loadPatientNotifiedPayments(patientId) {
    const tbody = document.getElementById('pat-notified-payments-list');
    if (!tbody) return;
    
    try {
        const res = await fetch(`/api/patient/payments/notified`);
        if (!res.ok) return;
        const list = await res.json();
        
        tbody.innerHTML = '';
        
        if (list.length === 0) {
            tbody.innerHTML = '<tr><td colspan="3" class="text-center text-secondary">No hay pagos notificados aún.</td></tr>';
            return;
        }
        
        list.forEach(p => {
            const tr = document.createElement('tr');
            
            let badgeClass = 'bg-warning text-warning-dark';
            let statusText = p.estado;
            if (p.estado === 'Verificado') {
                badgeClass = 'bg-success text-success-dark';
            } else if (p.estado === 'Requerir nuevos datos') {
                badgeClass = 'bg-danger text-danger-dark';
                statusText = `Rechazado: ${p.motivo_rechazo || 'Verificar referencia'}`;
            }
            
            tr.innerHTML = `
                <td>${p.fecha}</td>
                <td><strong>${p.monto} ${p.moneda}</strong></td>
                <td>
                    <span class="badge ${badgeClass}" style="font-size:0.72rem; padding: 0.15rem 0.4rem; border-radius: var(--radius-sm); font-weight: 600; display: inline-block;">
                        ${statusText}
                    </span>
                </td>
            `;
            tbody.appendChild(tr);
        });
    } catch (err) {
        console.error("Error al cargar historial de pagos notificados:", err);
        tbody.innerHTML = '<tr><td colspan="3" class="text-center text-secondary" style="color:red;">Error de conexión.</td></tr>';
    }
}

// Cancelación de cita desde el portal del paciente
async function handlePatientCancelAppointment(apptId, tiempoRestante, limiteCancelacion) {
    let force = false;
    if (tiempoRestante <= limiteCancelacion) {
        if (!confirm(`Advertencia: Estás cancelando con menos de ${limiteCancelacion} horas de antelación. Esta consulta se cobrará igualmente como cancelada sin aviso. ¿Estás seguro de que deseas proceder?`)) {
            return;
        }
        force = true;
    } else {
        if (!confirm('¿Estás seguro de que deseas cancelar tu cita programada?')) {
            return;
        }
    }
    
    try {
        const res = await fetch('/api/patient/cancel-appointment', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ appt_id: apptId, force: force })
        });
        
        const data = await res.json();
        if (data.error) {
            alert(data.error);
        } else {
            alert(data.success || 'Cita cancelada con éxito.');
            const patientId = sessionStorage.getItem('patient_id');
            if (patientId) {
                loadPatientPortalData(patientId);
            }
        }
    } catch (err) {
        console.error("Error al cancelar cita:", err);
        alert('Error de conexión al intentar cancelar la cita.');
    }
}

// ==========================================
// SISTEMA DE NOTIFICACIONES EN TIEMPO REAL
// ==========================================

// --- Rol Psicólogo ---
function toggleNotificationsDropdown() {
    requestNotificationPermission();
    const dropdown = document.getElementById('notifications-dropdown');
    if (!dropdown) return;
    dropdown.classList.toggle('hide');
}

async function loadNotifications() {
    const badge = document.getElementById('notifications-badge');
    const list = document.getElementById('notifications-list');
    if (!list || !badge) return;
    
    try {
        const res = await fetch('/api/admin/notifications');
        if (res.status === 401) {
            clearAllNotificationIntervals();
            return;
        }
        if (!res.ok) return;
        const data = await res.json();
        
        // Actualizar contador
        const headerTitle = document.getElementById('notifications-header-title');
        if (data.unread_count > 0) {
            badge.textContent = data.unread_count;
            badge.classList.remove('hide');
            if (headerTitle) headerTitle.textContent = `Notificaciones (${data.unread_count} nuevas)`;
        } else {
            badge.classList.add('hide');
            if (headerTitle) headerTitle.textContent = 'Notificaciones';
        }
        
        list.innerHTML = '';
        if (data.notifications && data.notifications.length > 0) {
            data.notifications.forEach(n => {
                // Disparar notificación nativa en la barra del OS si no está leída
                if (!n.leida) {
                    triggerNativeNotification(n.titulo || 'Mi Consultorio', n.mensaje || '', `n_${n.id}`, n.link);
                }

                const item = document.createElement('div');
                item.style.padding = '0.75rem 1rem';
                item.style.borderBottom = '1px solid var(--border-color)';
                item.style.cursor = 'pointer';
                item.style.transition = 'background-color 0.2s';
                item.style.backgroundColor = n.leida ? 'transparent' : 'rgba(169, 89, 147, 0.03)';
                
                // Iconos por tipo
                let icon = '🔔';
                if (n.tipo === 'cita') icon = '📅';
                if (n.tipo === 'pizarra') icon = '✏️';
                if (n.tipo === 'pago') icon = '💵';
                if (n.tipo === 'paciente') icon = '👤';
                
                item.innerHTML = `
                    <div style="display: flex; gap: 0.75rem; align-items: flex-start;">
                        <span style="font-size: 1.25rem; margin-top: 0.15rem;">${icon}</span>
                        <div style="flex: 1;">
                            <div style="font-weight: 700; font-size: 0.85rem; color: var(--text-dark); margin-bottom: 0.15rem; display: flex; justify-content: space-between; align-items: center;">
                                <span>${n.titulo}</span>
                                ${!n.leida ? '<span style="width: 6px; height: 6px; background-color: #ef4444; border-radius: 50%; display: inline-block;"></span>' : ''}
                            </div>
                            <div style="font-size: 0.78rem; color: var(--text-muted); line-height: 1.3; margin-bottom: 0.25rem;">${n.mensaje}</div>
                            <div style="font-size: 0.7rem; color: var(--text-muted); font-style: italic;">${n.fecha}</div>
                        </div>
                    </div>
                `;
                
                item.onclick = () => {
                    markNotificationAsRead(n.id, n.link);
                };
                
                list.appendChild(item);
            });
        } else {
            list.innerHTML = `
                <div style="padding: 1.5rem; text-align: center; color: var(--text-muted); font-size: 0.85rem;">
                    No tienes notificaciones nuevas
                </div>
            `;
        }
    } catch (err) {
        console.error("Error al cargar notificaciones del psicólogo:", err);
    }
}

async function markNotificationAsRead(id, link) {
    try {
        await fetch('/api/admin/notifications/mark-read', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ notification_id: id })
        });
        
        // Cerrar dropdown y recargar
        const dropdown = document.getElementById('notifications-dropdown');
        if (dropdown) dropdown.classList.add('hide');
        
        loadNotifications();
        
        // Redireccionar
        if (link) {
            switchView(link);
        }
    } catch (err) {
        console.error("Error al marcar notificación:", err);
    }
}

async function markAllNotificationsAsRead() {
    try {
        await fetch('/api/admin/notifications/mark-read', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({})
        });
        loadNotifications();
    } catch (err) {
        console.error("Error al marcar todas las notificaciones:", err);
    }
}

// --- Rol Paciente ---
function togglePatientNotificationsDropdown() {
    requestNotificationPermission();
    const dropdown = document.getElementById('pat-notifications-dropdown');
    if (!dropdown) return;
    dropdown.classList.toggle('hide');
}

async function loadPatientNotifications(patientId) {
    const badge = document.getElementById('pat-notifications-badge');
    const list = document.getElementById('pat-notifications-list');
    if (!list || !badge) return;
    
    try {
        const res = await fetch(`https://espacio-terapeutico-default-rtdb.firebaseio.com/pacientes/${patientId}/notificaciones.json`);
        if (!res.ok) return;
        const data = await res.json();
        
        list.innerHTML = '';
        
        if (!data) {
            badge.classList.add('hide');
            list.innerHTML = `
                <div style="padding: 1.25rem; text-align: center; color: var(--text-muted); font-size: 0.8rem;">
                    No tienes notificaciones
                </div>
            `;
            return;
        }
        
        const notifList = [];
        let unreadCount = 0;
        Object.keys(data).forEach(key => {
            const n = data[key];
            if (!n.leida) {
                unreadCount++;
                notifList.push({
                    key,
                    ...n
                });
            }
        });
        
        // Actualizar badge
        const headerTitle = document.getElementById('pat-notifications-header-title');
        if (unreadCount > 0) {
            badge.textContent = unreadCount;
            badge.classList.remove('hide');
            if (headerTitle) headerTitle.textContent = `Notificaciones (${unreadCount} nuevas)`;
        } else {
            badge.classList.add('hide');
            if (headerTitle) headerTitle.textContent = 'Notificaciones';
            list.innerHTML = `
                <div style="padding: 1.25rem; text-align: center; color: var(--text-muted); font-size: 0.8rem;">
                    No tienes notificaciones
                </div>
            `;
            return;
        }
        
        // Ordenar por fecha desc
        notifList.sort((a, b) => new Date(b.fecha) - new Date(a.fecha));
        
        notifList.forEach(n => {
            // Disparar notificación nativa si no ha sido leída
            triggerNativeNotification(n.titulo || 'Espacio Terapéutico', n.mensaje || '', `pat_${n.key}`, '');

            const item = document.createElement('div');
            item.style.padding = '0.65rem 0.85rem';
            item.style.borderBottom = '1px solid var(--border-color)';
            item.style.cursor = 'pointer';
            item.style.transition = 'background-color 0.2s';
            item.style.backgroundColor = 'rgba(169, 89, 147, 0.03)';
            item.style.fontSize = '0.8rem';
            
            let icon = '🔔';
            if (n.tipo === 'clinico') icon = '📝';
            if (n.tipo === 'pago') icon = '💵';
            if (n.tipo === 'pizarra') icon = '✏️';
            
            const dateObj = new Date(n.fecha);
            const dateStr = dateObj.toLocaleDateString([], {day: '2-digit', month: '2-digit'});
            const timeStr = dateObj.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'});
            
            item.innerHTML = `
                <div style="display: flex; gap: 0.6rem; align-items: flex-start;">
                    <span style="font-size: 1.1rem; margin-top: 0.1rem;">${icon}</span>
                    <div style="flex: 1;">
                        <div style="font-weight: 700; color: var(--text-dark); margin-bottom: 0.1rem; display: flex; justify-content: space-between; align-items: center;">
                            <span>${n.titulo}</span>
                            <span style="width: 6px; height: 6px; background-color: #ef4444; border-radius: 50%; display: inline-block;"></span>
                        </div>
                        <div style="color: var(--text-muted); line-height: 1.25; margin-bottom: 0.2rem; font-size: 0.75rem;">${n.mensaje}</div>
                        <div style="color: var(--text-muted); font-size: 0.68rem; font-style: italic;">${dateStr} a las ${timeStr}</div>
                    </div>
                </div>
            `;
            
            item.onclick = async () => {
                await markPatientNotificationAsRead(patientId, n.key);
            };
            
            list.appendChild(item);
        });
    } catch (err) {
        console.error("Error al cargar notificaciones de paciente:", err);
    }
}

async function markPatientNotificationAsRead(patientId, key) {
    try {
        await fetch(`https://espacio-terapeutico-default-rtdb.firebaseio.com/pacientes/${patientId}/notificaciones/${key}.json`, {
            method: 'DELETE'
        });
        
        const dropdown = document.getElementById('pat-notifications-dropdown');
        if (dropdown) dropdown.classList.add('hide');
        
        loadPatientNotifications(patientId);
    } catch (err) {
        console.error("Error al marcar notificación de paciente:", err);
    }
}

async function markAllPatientNotificationsAsRead() {
    const patientId = sessionStorage.getItem('patient_id');
    if (!patientId) return;
    
    try {
        await fetch(`https://espacio-terapeutico-default-rtdb.firebaseio.com/pacientes/${patientId}/notificaciones.json`, {
            method: 'DELETE'
        });
        
        loadPatientNotifications(patientId);
    } catch (err) {
        console.error("Error al marcar todas las notificaciones del paciente:", err);
    }
}

// Cerrar dropdowns de notificaciones al hacer clic afuera
document.addEventListener('click', (e) => {
    const bellBtn = document.querySelector('.notifications-bell-btn');
    const dropdown = document.getElementById('notifications-dropdown');
    if (dropdown && !dropdown.classList.contains('hide') && bellBtn && !bellBtn.contains(e.target) && !dropdown.contains(e.target)) {
        dropdown.classList.add('hide');
    }
    
    const patBellBtn = document.querySelector('.pat-notifications-container button');
    const patDropdown = document.getElementById('pat-notifications-dropdown');
    if (patDropdown && !patDropdown.classList.contains('hide') && patBellBtn && !patBellBtn.contains(e.target) && !patDropdown.contains(e.target)) {
        patDropdown.classList.add('hide');
    }
});

async function submitPizarraReply(patientId, updateId) {
    const input = document.getElementById(`reply-input-${updateId}`);
    if (!input) return;
    const comment = input.value.trim();
    if (!comment) return;
    
    try {
        const res = await fetch('/api/admin/pizarra/reply', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ update_id: updateId, respuesta: comment })
        });
        const data = await res.json();
        
        if (res.ok && !data.error) {
            // Notificar también vía Firebase RTDB si está configurado
            try {
                await fetch(`https://espacio-terapeutico-default-rtdb.firebaseio.com/pacientes/${patientId}/notificaciones.json`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        tipo: "pizarra",
                        titulo: "Comentario en Pizarra",
                        mensaje: `Tu terapeuta comentó en tu pizarra: "${comment}"`,
                        fecha: new Date().toISOString(),
                        leida: false
                    })
                });
            } catch (fbErr) {
                console.warn("Aviso: Notificación Firebase RTDB no enviada:", fbErr);
            }

            alert('Respuesta enviada y registrada con éxito.');
            input.value = '';
            if (typeof loadPizarraVisual === 'function') {
                loadPizarraVisual();
            }
        } else {
            alert(data.error || 'Error al enviar el comentario.');
        }
    } catch (err) {
        console.error("Error al enviar comentario de pizarra:", err);
        alert('Error de conexión al enviar respuesta.');
    }
}

// --- Recuperación de Contraseña ---
async function handleForgotPassword(e) {
    e.preventDefault();
    const loginUser = document.getElementById('auth-username').value.trim();
    if (!loginUser) {
        alert("Por favor, escribe tu usuario o cédula en el campo de acceso antes de hacer clic en recuperar.");
        return;
    }
    
    try {
        const res = await fetch(`/api/check-username-role?username=${encodeURIComponent(loginUser)}`);
        const data = await res.json();
        
        if (!res.ok) {
            alert(data.error || "Usuario no encontrado.");
            return;
        }
        
        if (data.role === 'psicologo') {
            alert("Si eres Terapeuta, por favor ejecuta el script seguro en tu servidor o contacta con soporte para restablecer tus credenciales.");
        } else {
            // Mostrar Paso 1 con el nombre ya puesto y auto-consultar preguntas
            document.getElementById('recovery-step-1').classList.remove('hide');
            document.getElementById('recovery-step-2').classList.add('hide');
            document.getElementById('recovery-username').value = loginUser;
            openModal('recovery-modal');
            await fetchRecoveryQuestions();
        }
    } catch (err) {
        console.error("Error al verificar usuario de recuperación:", err);
        alert("Error de conexión con el servidor.");
    }
}

async function fetchRecoveryQuestions() {
    const username = document.getElementById('recovery-username').value.trim();
    if (!username) {
        alert("Introduce tu usuario o cédula.");
        return;
    }
    
    try {
        const res = await fetch('/api/patient/recovery-questions', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username })
        });
        const data = await res.json();
        
        if (res.ok) {
            document.getElementById('recovery-q1-label').textContent = data.pregunta_1;
            document.getElementById('recovery-q2-label').textContent = data.pregunta_2;
            document.getElementById('recovery-a1').value = '';
            document.getElementById('recovery-a2').value = '';
            document.getElementById('recovery-new-password').value = '';
            
            document.getElementById('recovery-step-1').classList.add('hide');
            document.getElementById('recovery-step-2').classList.remove('hide');
        } else {
            alert(data.error || "No se pudieron obtener las preguntas de seguridad.");
        }
    } catch (err) {
        console.error("Error al obtener preguntas:", err);
        alert("Error de conexión con el servidor.");
    }
}

async function submitPasswordReset() {
    const username = document.getElementById('recovery-username').value.trim();
    const resp1 = document.getElementById('recovery-a1').value.trim();
    const resp2 = document.getElementById('recovery-a2').value.trim();
    const newPassword = document.getElementById('recovery-new-password').value.trim();
    
    if (!resp1 || !resp2 || !newPassword) {
        alert("Por favor completa todos los campos.");
        return;
    }
    
    if (newPassword.length < 6) {
        alert("La nueva contraseña debe tener al menos 6 caracteres.");
        return;
    }
    
    try {
        const res = await fetch('/api/patient/reset-password', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                username,
                respuesta_1: resp1,
                respuesta_2: resp2,
                new_password: newPassword
            })
        });
        const data = await res.json();
        
        if (res.ok) {
            alert(data.success || "Contraseña restablecida con éxito. Inicia sesión a continuación.");
            closeModal('recovery-modal');
        } else {
            alert(data.error || "Error al restablecer la contraseña.");
        }
    } catch (err) {
        console.error("Error al restablecer contraseña:", err);
        alert("Error de conexión con el servidor.");
    }
}

// --- Plantillas de Mensajes WhatsApp ---
async function loadMessageTemplates() {
    try {
        const res = await fetch('/api/admin/message-templates');
        if (!res.ok) return;
        const data = await res.json();
        
        const c = document.getElementById('template-confirmacion');
        const r = document.getElementById('template-recordatorio');
        const ci = document.getElementById('template-cierre');
        
        if (c) c.value = data.msg_confirmacion || "";
        if (r) r.value = data.msg_recordatorio || "";
        if (ci) ci.value = data.msg_cierre || "";
    } catch (err) {
        console.error("Error al cargar plantillas de mensaje:", err);
    }
}

async function handleSaveMessageTemplates(e) {
    e.preventDefault();
    const msgConfirmacion = document.getElementById('template-confirmacion').value;
    const msgRecordatorio = document.getElementById('template-recordatorio').value;
    const msgCierre = document.getElementById('template-cierre').value;
    
    try {
        const res = await fetch('/api/admin/message-templates', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                msg_confirmacion: msgConfirmacion,
                msg_recordatorio: msgRecordatorio,
                msg_cierre: msgCierre
            })
        });
        const data = await res.json();
        if (res.ok) {
            alert(data.success || "Plantillas guardadas correctamente.");
        } else {
            alert(data.error || "Error al guardar plantillas.");
        }
    } catch (err) {
        console.error("Error al guardar plantillas:", err);
        alert("Error de conexión.");
    }
}

async function sendWhatsappTemplate(type) {
    const apptId = document.getElementById('event-form-id').value;
    if (!apptId) {
        alert("Cita no identificada.");
        return;
    }
    
    try {
        const res = await fetch(`/api/admin/message-templates/render?appointment_id=${apptId}&template_type=${type}`);
        const data = await res.json();
        
        if (res.ok) {
            window.open(data.wa_url, '_blank');
        } else {
            alert(data.error || "Error al renderizar el mensaje.");
        }
    } catch (err) {
        console.error("Error al enviar mensaje por WhatsApp:", err);
        alert("Error de conexión.");
    }
}

function getWhatsAppLink(phone, text) {
    if (!phone) return '#';
    let cleanPhone = String(phone).replace(/[^0-9]/g, '');
    if (cleanPhone.startsWith('0')) {
        cleanPhone = '58' + cleanPhone.substring(1);
    }
    const encodedText = encodeURIComponent(text || '');
    return `https://wa.me/${cleanPhone}?text=${encodedText}`;
}

function exportFinanceCSV() {
    const year = document.getElementById('finance-filter-year')?.value || new Date().getFullYear();
    const month = document.getElementById('finance-filter-month')?.value || (new Date().getMonth() + 1);
    window.location.href = `/api/finance/export-csv?year=${year}&month=${month}`;
}

// --- Navegación de Sub-Pestañas en Módulos ---
function switchFinanceTab(tabId) {
    const ids = ['ingresos', 'verificaciones', 'cobros', 'honorarios'];
    ids.forEach(id => {
        const card = document.getElementById(`fin-card-${id}`);
        const tabBtn = document.getElementById(`fin-tab-${id}`);
        
        if (card && tabBtn) {
            if (id === tabId) {
                card.classList.remove('hide');
                tabBtn.className = 'btn btn-sm btn-primary';
            } else {
                card.classList.add('hide');
                tabBtn.className = 'btn btn-sm btn-secondary';
            }
        }
    });
    
    if (tabId === 'verificaciones') {
        loadNotifiedPayments();
    } else if (tabId === 'honorarios') {
        loadPatientRatesTable();
    } else {
        loadFinanceData();
    }
}

const loadPatientsRatesList = loadPatientRatesTable;

// Note: switchSettingsTab is defined near line 10359 with full tab dispatching

async function loadAdminTerms() {
    const textarea = document.getElementById('admin-terms-textarea');
    if (!textarea) return;
    try {
        const res = await fetch('/api/admin/terms');
        if (res.ok) {
            const data = await res.json();
            textarea.value = data.terms || '';
        }
    } catch (err) {
        console.error("Error al cargar términos para administrador:", err);
    }
}

async function handleSaveAdminTerms(e) {
    e.preventDefault();
    const textarea = document.getElementById('admin-terms-textarea');
    const statusMsg = document.getElementById('admin-terms-status-msg');
    if (!textarea || !statusMsg) return;
    statusMsg.classList.add('hide');

    const terms = textarea.value.trim();

    try {
        const res = await fetch('/api/admin/terms', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ terms })
        });
        const data = await res.json();
        if (res.ok) {
            statusMsg.textContent = '¡Términos y condiciones guardados con éxito!';
            statusMsg.className = 'status-msg success-msg';
            statusMsg.classList.remove('hide');
        } else {
            statusMsg.textContent = data.error || 'Error al guardar los términos y condiciones.';
            statusMsg.className = 'status-msg error-msg';
            statusMsg.classList.remove('hide');
        }
    } catch (err) {
        statusMsg.textContent = 'Error de conexión al guardar los términos.';
        statusMsg.className = 'status-msg error-msg';
        statusMsg.classList.remove('hide');
    }
}

async function openPatientTermsModal(e) {
    if (e && e.preventDefault) e.preventDefault();
    const modal = document.getElementById('patient-terms-modal');
    if (modal) {
        modal.classList.remove('hide');
        modal.style.display = 'flex';
    }
    const drawer = document.getElementById('patient-drawer');
    const overlay = document.getElementById('patient-menu-overlay');
    if (drawer) drawer.classList.remove('active');
    if (overlay) overlay.classList.add('hide');

    const textBox = document.getElementById('patient-terms-text-box');
    const statusBanner = document.getElementById('patient-terms-status-banner');
    const acceptBtn = document.getElementById('accept-terms-btn');
    const closeBtn = document.getElementById('close-terms-btn');
    const termsBadge = document.getElementById('pat-menu-terms-badge');

    try {
        const res = await fetch('/api/patient/portal-data');
        if (res.ok) {
            const data = await res.json();
            if (textBox && data.terminos_texto) {
                textBox.textContent = data.terminos_texto;
            }
            if (data.terminos_requeridos) {
                if (termsBadge) {
                    termsBadge.style.display = 'inline-block';
                    termsBadge.textContent = '⚠️ Pendiente';
                }
                if (statusBanner) {
                    statusBanner.style.background = 'rgba(245, 158, 11, 0.15)';
                    statusBanner.style.color = '#d97706';
                    statusBanner.style.border = '1px solid rgba(245, 158, 11, 0.3)';
                    statusBanner.innerHTML = '⚠️ <strong>Pendiente de Aceptación:</strong> Lee los términos para continuar.';
                    statusBanner.style.display = 'block';
                }
                if (acceptBtn) {
                    acceptBtn.style.display = 'block';
                    acceptBtn.disabled = false;
                    acceptBtn.textContent = '✓ Aceptar Encuadre Terapéutico';
                    acceptBtn.onclick = handleAcceptPatientTerms;
                }
                if (closeBtn) closeBtn.style.display = 'none';
            } else {
                const fechaAcept = data.fecha_aceptacion_terminos || 'Fecha no registrada';
                if (termsBadge) termsBadge.style.display = 'none';
                if (statusBanner) {
                    statusBanner.style.background = 'rgba(16, 185, 129, 0.15)';
                    statusBanner.style.color = '#059669';
                    statusBanner.style.border = '1px solid rgba(16, 185, 129, 0.3)';
                    statusBanner.innerHTML = ` <strong>Encuadre Aceptado</strong> el ${fechaAcept}`;
                    statusBanner.style.display = 'block';
                }
                if (acceptBtn) acceptBtn.style.display = 'none';
                if (closeBtn) {
                    closeBtn.style.display = 'block';
                    closeBtn.textContent = 'Cerrar Ventana';
                    closeBtn.onclick = () => closeModal('patient-terms-modal');
                }
            }
        }
    } catch(err) {
        console.error('Error al cargar términos para modal:', err);
    }
}
window.openPatientTermsModal = openPatientTermsModal;

// Event delegation global para el botón de encuadre y términos
document.addEventListener('click', function(e) {
    const target = e.target.closest('#btn-open-patient-terms, [data-action="open-patient-terms"]');
    if (target) {
        openPatientTermsModal(e);
    }
});

async function handleAcceptPatientTerms() {
    const btn = document.getElementById('pat-view-accept-terms-btn') || document.getElementById('accept-terms-btn');
    if (btn) {
        btn.disabled = true;
        btn.textContent = 'Procesando...';
    }
    try {
        const res = await fetch('/api/patient/accept-terms', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        const data = await res.json();
        if (res.ok) {
            closeModal('patient-terms-modal');
            const fechaActual = data.fecha || new Date().toLocaleString();
            
            const termsBadge = document.getElementById('pat-menu-terms-badge');
            if (termsBadge) termsBadge.style.display = 'none';

            const viewStatusBanner = document.getElementById('pat-view-terms-banner');
            if (viewStatusBanner) {
                viewStatusBanner.style.background = 'rgba(16, 185, 129, 0.15)';
                viewStatusBanner.style.color = '#059669';
                viewStatusBanner.style.border = '1px solid rgba(16, 185, 129, 0.3)';
                viewStatusBanner.innerHTML = `<span> <strong>Encuadre Aceptado</strong> el: <strong>${fechaActual}</strong></span><span style="font-size:0.85rem; font-weight:normal; background:#10b981; color:white; padding:0.2rem 0.6rem; border-radius:12px;">Encuadre Vigente</span>`;
                viewStatusBanner.style.display = 'flex';
            }

            const viewAcceptBtn = document.getElementById('pat-view-accept-terms-btn');
            if (viewAcceptBtn) viewAcceptBtn.style.display = 'none';

            const patientId = sessionStorage.getItem('patient_id');
            if (patientId) {
                loadPatientPortalData(patientId);
            }

            alert('✓ Encuadre Terapéutico Aceptado con éxito');
        } else {
            alert(data.error || 'Ocurrió un error al registrar la aceptación de términos.');
            if (btn) {
                btn.disabled = false;
                btn.textContent = '✓ He leído y acepto los Términos y Condiciones';
            }
        }
    } catch (err) {
        console.error('Error al aceptar términos:', err);
        alert('Error de conexión al aceptar los términos.');
        if (btn) {
            btn.disabled = false;
            btn.textContent = '✓ He leído y acepto los Términos y Condiciones';
        }
    }
}

async function handleChangeUserPassword(e) {
    e.preventDefault();
    const currPass = document.getElementById('change-user-curr-pass').value;
    const newPass = document.getElementById('change-user-new-pass').value;
    const confirmPass = document.getElementById('change-user-confirm-pass').value;
    const statusMsg = document.getElementById('change-user-pass-status-msg');
    
    statusMsg.classList.add('hide');
    
    if (newPass !== confirmPass) {
        statusMsg.textContent = '❌ La nueva contraseña y la confirmación no coinciden.';
        statusMsg.className = 'status-msg error-msg';
        statusMsg.classList.remove('hide');
        return;
    }
    
    showLoadingScreen();
    try {
        const res = await fetch('/api/user/change-password', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                current_password: currPass,
                new_password: newPass,
                confirm_password: confirmPass
            })
        });
        const data = await res.json();
        hideLoadingScreen();
        
        if (res.ok && data.success) {
            statusMsg.textContent = '✅ ' + data.success;
            statusMsg.className = 'status-msg success-msg';
            statusMsg.classList.remove('hide');
            document.getElementById('change-user-curr-pass').value = '';
            document.getElementById('change-user-new-pass').value = '';
            document.getElementById('change-user-confirm-pass').value = '';
        } else {
            statusMsg.textContent = '❌ ' + (data.error || 'Error al actualizar contraseña.');
            statusMsg.className = 'status-msg error-msg';
            statusMsg.classList.remove('hide');
        }
    } catch (err) {
        hideLoadingScreen();
        statusMsg.textContent = '❌ Error al conectar con el servidor: ' + err.message;
        statusMsg.className = 'status-msg error-msg';
        statusMsg.classList.remove('hide');
    }
}
window.handleChangeUserPassword = handleChangeUserPassword;

async function loadPatientLinks() {
    const baseUrl = `${window.location.protocol}//${window.location.host}`;
    const regEl = document.getElementById('link-registro-paciente');
    const ageEl = document.getElementById('link-agenda-rapida');
    const slugInp = document.getElementById('psychologist-slug-input');
    
    try {
        const res = await fetch('/api/admin/profile-slug');
        if (res.ok) {
            const data = await res.json();
            const slug = data.slug || (data.username ? `psic.${data.username.toLowerCase().replace(/[^a-z0-9]/g, '')}` : '');
            if (slug) {
                const regUrl = data.registration_url ? (data.registration_url.startsWith('http') ? data.registration_url : `${baseUrl}${data.registration_url}`) : `${baseUrl}/registro/${slug}`;
                const ageUrl = data.fast_booking_url ? (data.fast_booking_url.startsWith('http') ? data.fast_booking_url : `${baseUrl}${data.fast_booking_url}`) : `${baseUrl}/agendar/${slug}`;
                
                if (regEl) regEl.value = regUrl;
                if (ageEl) ageEl.value = ageUrl;
                if (slugInp) slugInp.value = slug;
                return;
            }
        }
    } catch (err) {
        console.error("Error cargando enlaces personalizados:", err);
    }
}

async function savePsychologistSlug() {
    const slugInp = document.getElementById('psychologist-slug-input');
    const statusMsg = document.getElementById('slug-status-msg');
    if (!slugInp) return;
    const newSlug = slugInp.value.trim();
    if (!newSlug) {
        if (statusMsg) {
            statusMsg.textContent = '❌ Por favor ingresa un identificador válido.';
            statusMsg.className = 'status-msg error-msg';
            statusMsg.classList.remove('hide');
        }
        return;
    }
    try {
        showLoadingScreen('Guardando enlace personalizado...');
        const res = await fetch('/api/admin/profile-slug', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ slug: newSlug })
        });
        hideLoadingScreen();
        const data = await res.json();
        if (res.ok) {
            if (statusMsg) {
                statusMsg.textContent = '✓ ' + (data.success || 'Enlace personalizado actualizado.');
                statusMsg.className = 'status-msg success-msg';
                statusMsg.classList.remove('hide');
            }
            loadPatientLinks();
        } else {
            if (statusMsg) {
                statusMsg.textContent = '❌ ' + (data.error || 'Error al guardar enlace.');
                statusMsg.className = 'status-msg error-msg';
                statusMsg.classList.remove('hide');
            }
        }
    } catch(e) {
        hideLoadingScreen();
        if (statusMsg) {
            statusMsg.textContent = '❌ Error de conexión: ' + e.message;
            statusMsg.className = 'status-msg error-msg';
            statusMsg.classList.remove('hide');
        }
    }
}
window.savePsychologistSlug = savePsychologistSlug;

function copyToClipboard(inputId) {
    const input = document.getElementById(inputId);
    if (!input) return;
    
    input.select();
    input.setSelectionRange(0, 99999);
    
    try {
        navigator.clipboard.writeText(input.value);
        alert("¡Enlace copiado al portapapeles!");
    } catch (err) {
        document.execCommand('copy');
        alert("¡Enlace copiado al portapapeles!");
    }
}

async function initFirebaseMessagingFlow(registration) {
    try {
        const res = await fetch('/api/firebase/config');
        const data = await res.json();
        
        if (!data.config || !data.vapid_key) {
            console.log("Firebase FCM no configurado en este servidor.");
            return;
        }
        
        // Cargar librerías SDK compat de Firebase dinámicamente si no están en el DOM
        if (typeof firebase === 'undefined') {
            await new Promise((resolve, reject) => {
                const scriptApp = document.createElement('script');
                scriptApp.src = 'https://www.gstatic.com/firebasejs/10.7.1/firebase-app-compat.js';
                scriptApp.onload = resolve;
                scriptApp.onerror = reject;
                document.head.appendChild(scriptApp);
            });
            await new Promise((resolve, reject) => {
                const scriptMsg = document.createElement('script');
                scriptMsg.src = 'https://www.gstatic.com/firebasejs/10.7.1/firebase-messaging-compat.js';
                scriptMsg.onload = resolve;
                scriptMsg.onerror = reject;
                document.head.appendChild(scriptMsg);
            });
        }
        
        // Inicializar Firebase Web Client
        const config = JSON.parse(data.config);
        if (firebase.apps.length === 0) {
            firebase.initializeApp(config);
        }
        
        const messaging = firebase.messaging();
        
        // Solicitar permisos de notificación nativa
        const permission = await Notification.requestPermission();
        if (permission !== 'granted') {
            console.warn("Permiso de notificaciones push FCM no otorgado.");
            return;
        }
        
        let fcmReg = registration;
        if ('serviceWorker' in navigator) {
            try {
                fcmReg = await navigator.serviceWorker.register('/firebase-messaging-sw.js');
            } catch(e) {
                console.warn("FCM usando SW secundario:", e);
            }
        }
        
        // Obtener el token de registro de FCM
        const token = await messaging.getToken({
            vapidKey: data.vapid_key,
            serviceWorkerRegistration: fcmReg
        });
        
        if (token) {
            console.log("FCM Token generado con éxito:", token);
            // Enviar token al backend
            await fetch('/api/firebase/subscribe', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ token: token })
            });
            console.log("Suscripción FCM registrada en BD.");
        } else {
            console.warn("No se obtuvo token de FCM.");
        }
        
        // Interceptación en primer plano (Foreground)
        messaging.onMessage((payload) => {
            console.log("Mensaje FCM recibido en primer plano:", payload);
            const title = payload.notification?.title || payload.data?.title || 'Mi Consultorio';
            const body = payload.notification?.body || payload.data?.body || 'Tienes una nueva notificación.';
            
            if (typeof showCustomToast === 'function') {
                showCustomToast(title, body);
            } else {
                new Notification(title, {
                    body: body,
                    icon: '/static/logo.png',
                    badge: '/static/logo.png',
                    data: { url: payload.data?.url || '/' }
                });
            }
        });
    } catch (err) {
        console.error("Error al inicializar FCM Flow:", err);
    }
}
window.initFirebaseMessagingFlow = initFirebaseMessagingFlow;

async function loadFirebaseSettings() {
    const badge = document.getElementById('firebase-sa-status-badge');
    const defaultCfg = JSON.stringify({
        "apiKey": "AIzaSyDRQlUEv1SToy5ZdQQyUuYZDIhejeJ81zM",
        "authDomain": "espacio-terapeutico.firebaseapp.com",
        "databaseURL": "https://espacio-terapeutico-default-rtdb.firebaseio.com",
        "projectId": "espacio-terapeutico",
        "storageBucket": "espacio-terapeutico.firebasestorage.app",
        "messagingSenderId": "437385369836",
        "appId": "1:437385369836:web:f3745dc8d65d7ca418edc9",
        "measurementId": "G-M04FWL2963"
    }, null, 2);
    const defaultVapid = "BIexDrYPs7iSYmxpkfgQwzatXm_o5pRa1ZAZUvzeF40nAc8N61RFlHqlZ153VNamBelgsKhB4nnowPJm_7Y-Qjc";

    try {
        const cfgElem = document.getElementById('fcm-web-config');
        const vapidElem = document.getElementById('fcm-vapid-key');
        if (cfgElem && !cfgElem.value.trim()) cfgElem.value = defaultCfg;
        if (vapidElem && !vapidElem.value.trim()) vapidElem.value = defaultVapid;

        const res = await fetch('/api/firebase/config');
        if (res.ok) {
            const data = await res.json();
            if (cfgElem && data.config) cfgElem.value = data.config;
            if (vapidElem && data.vapid_key) vapidElem.value = data.vapid_key;
        }

        const statusRes = await fetch('/api/firebase/status');
        if (statusRes.ok) {
            const statusData = await statusRes.json();
            if (badge) {
                if (statusData.has_service_account) {
                    badge.textContent = "Cargada y Lista";
                    badge.className = "badge badge-success";
                } else {
                    badge.textContent = "Falta firebase_service_account.json";
                    badge.className = "badge badge-danger";
                }
            }
        } else if (badge) {
            badge.textContent = "Falta firebase_service_account.json";
            badge.className = "badge badge-danger";
        }
    } catch (err) {
        console.error("Error al cargar configuración de Firebase:", err);
        if (badge) {
            badge.textContent = "Falta firebase_service_account.json";
            badge.className = "badge badge-danger";
        }
    }
}
window.loadFirebaseSettings = loadFirebaseSettings;

function cleanAndParseFirebaseConfig(str) {
    if (!str || !str.trim()) return null;
    let s = str.trim();
    const firstBrace = s.indexOf('{');
    const lastBrace = s.lastIndexOf('}');
    if (firstBrace !== -1 && lastBrace !== -1 && lastBrace > firstBrace) {
        s = s.substring(firstBrace, lastBrace + 1);
    }
    try {
        return JSON.parse(s);
    } catch(e) {}
    try {
        const jsonLike = s
            .replace(/\/\/.*/g, '')
            .replace(/([{,]\s*)([a-zA-Z0-9_]+)\s*:/g, '$1"$2":')
            .replace(/'/g, '"')
            .replace(/,\s*}/g, '}');
        return JSON.parse(jsonLike);
    } catch(e) {}
    return null;
}

async function handleSaveFirebaseConfig(event) {
    event.preventDefault();
    const rawConfigVal = document.getElementById('fcm-web-config').value.trim();
    const vapidKeyVal = document.getElementById('fcm-vapid-key').value.trim();
    const saTextElem = document.getElementById('firebase-sa-text-input');
    const saTextVal = saTextElem ? saTextElem.value.trim() : '';
    const statusMsg = document.getElementById('fcm-config-status-msg');
    
    if (statusMsg) statusMsg.classList.add('hide');
    
    let configVal = rawConfigVal;
    if (rawConfigVal) {
        const parsed = cleanAndParseFirebaseConfig(rawConfigVal);
        if (!parsed) {
            alert("❌ Error: No se pudo interpretar la configuración pegada. Asegúrate de copiar las líneas entre corchetes { ... } de Firebase Console.");
            return;
        }
        configVal = JSON.stringify(parsed, null, 2);
        document.getElementById('fcm-web-config').value = configVal;
    }
    
    showLoadingScreen();
    try {
        const res = await fetch('/api/firebase/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ config: configVal, vapid_key: vapidKeyVal, sa_json: saTextVal })
        });
        const data = await res.json();
        hideLoadingScreen();
        
        if (res.ok && data.success) {
            alert("✅ ¡Configuración de Firebase guardada con éxito!");
            if (statusMsg) {
                statusMsg.textContent = "✅ Configuración de Firebase guardada con éxito.";
                statusMsg.className = "status-msg success-msg";
                statusMsg.classList.remove('hide');
            }
            loadFirebaseSettings();
            try { initFirebaseMessagingFlow(); } catch(e) {}
        } else {
            alert("❌ Error: " + (data.error || "No se pudo guardar la configuración."));
        }
    } catch (err) {
        hideLoadingScreen();
        alert("❌ Error al conectar con el servidor: " + err.message);
    }
}
window.handleSaveFirebaseConfig = handleSaveFirebaseConfig;

async function handleFirebaseSaUpload(input) {
    if (!input.files || input.files.length === 0) return;
    const file = input.files[0];
    const formData = new FormData();
    formData.append('file', file);
    
    showLoadingScreen();
    try {
        const res = await fetch('/api/firebase/upload-sa', {
            method: 'POST',
            body: formData
        });
        const data = await res.json();
        hideLoadingScreen();
        
        if (data.success) {
            alert("✅ ¡Cuenta de servicio de Firebase subida con éxito!");
            loadFirebaseSettings();
        } else {
            alert("❌ Error: " + (data.error || "No se pudo subir el archivo."));
        }
    } catch (err) {
        hideLoadingScreen();
        alert("❌ Error al conectar con el servidor: " + err.message);
    }
}
window.handleFirebaseSaUpload = handleFirebaseSaUpload;

async function handleSaveSaText() {
    const configVal = document.getElementById('fcm-web-config').value.trim();
    const vapidKeyVal = document.getElementById('fcm-vapid-key').value.trim();
    const saText = document.getElementById('firebase-sa-text-input').value.trim();
    
    if (!saText && !configVal) {
        alert("❌ Por favor ingresa los datos antes de guardar.");
        return;
    }
    
    showLoadingScreen();
    try {
        const res = await fetch('/api/firebase/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ config: configVal, vapid_key: vapidKeyVal, sa_json: saText })
        });
        const data = await res.json();
        hideLoadingScreen();
        
        if (res.ok && data.success) {
            alert("✅ ¡Configuración de Firebase guardada con éxito!");
            loadFirebaseSettings();
        } else {
            alert("❌ Error: " + (data.error || "No se pudo guardar la clave."));
        }
    } catch (err) {
        hideLoadingScreen();
        alert("❌ Error al conectar con el servidor: " + err.message);
    }
}
window.handleSaveSaText = handleSaveSaText;

// ==========================================
// REGISTRO Y AUTO-AGENDA RÁPIDA (PORTAL)
// ==========================================
let regPsychologists = [];

async function loadActivePsychologists() {
    try {
        const res = await fetch('/api/active-psychologists');
        if (!res.ok) return;
        regPsychologists = await res.json();
        
        const select = document.getElementById('reg-psicologo-id');
        if (select) {
            const urlParams = new URLSearchParams(window.location.search);
            let refId = urlParams.get('ref_psicologo');
            
            // Si refId es un slug o username, buscar el id numérico correspondiente
            if (refId && isNaN(parseInt(refId))) {
                const cleanRef = refId.toLowerCase().replace('psic.', '').replace('psic-', '');
                const found = regPsychologists.find(p => 
                    (p.slug && p.slug.toLowerCase().includes(cleanRef)) || 
                    (p.username && p.username.toLowerCase().includes(cleanRef))
                );
                if (found) refId = found.id;
            }

            const currentVal = select.value || refId;
            select.innerHTML = '<option value="" disabled selected>Selecciona tu psicólogo...</option>';
            regPsychologists.forEach(p => {
                const isSelected = currentVal && String(p.id) === String(currentVal);
                select.innerHTML += `<option value="${p.id}" ${isSelected ? 'selected' : ''}>Psic. ${p.nombres} ${p.apellidos}</option>`;
            });

            if (currentVal) {
                select.value = currentVal;
            }
        }
    } catch (err) {
        console.error("Error loading active psychologists:", err);
    }
}

let isPreRegisteredPatient = false;

function openRegisterModal(e) {
    if (e) e.preventDefault();
    document.getElementById('register-modal').classList.remove('hide');
    document.getElementById('register-form').reset();
    
    // Configurar visibilidad inicial de los pasos de registro
    document.getElementById('reg-step-cedula').classList.remove('hide');
    document.getElementById('reg-step-details').classList.add('hide');
    document.getElementById('reg-cedula-status-msg').classList.add('hide');
    document.getElementById('reg-error-msg').classList.add('hide');
    
    // Restablecer inputs deshabilitados
    document.getElementById('reg-nombres').disabled = false;
    document.getElementById('reg-apellidos').disabled = false;
    document.getElementById('reg-cedula').disabled = false;
    
    // Restablecer visibilidades de sub-campos del formulario
    document.getElementById('reg-tipo-usuario-group').classList.remove('hide');
    document.getElementById('reg-common-fields').classList.add('hide');
    document.getElementById('reg-paciente-fields').classList.add('hide');
    document.getElementById('reg-psicologo-fields').classList.add('hide');
    document.getElementById('reg-security-questions-fields').classList.add('hide');
    
    // Asegurar que el selector de psicólogo esté visible si no hay referral
    const psicologoSelect = document.getElementById('reg-psicologo-id');
    if (psicologoSelect) {
        const selectGroup = psicologoSelect.closest('.form-group');
        if (selectGroup) selectGroup.style.display = 'block';
    }
    
    isPreRegisteredPatient = false;
    loadActivePsychologists();
}

function closeRegisterModal() {
    document.getElementById('register-modal').classList.add('hide');
}

async function validateRegisterCedula() {
    const cedulaInput = document.getElementById('reg-verif-cedula');
    const cedula = cedulaInput.value.trim();
    const statusMsg = document.getElementById('reg-cedula-status-msg');
    
    if (!cedula) {
        alert("Por favor introduce una cédula de identidad.");
        return;
    }
    
    statusMsg.classList.add('hide');
    
    try {
        const res = await fetch(`/api/register/check-cedula?cedula=${encodeURIComponent(cedula)}`);
        const data = await res.json();
        
        if (data.status === 'registered') {
            statusMsg.textContent = "Esta cédula ya tiene una cuenta activa. Por favor inicia sesión.";
            statusMsg.className = "status-msg error-msg";
            statusMsg.classList.remove('hide');
        } else if (data.status === 'pre_registered') {
            isPreRegisteredPatient = true;
            
            // Llenar campos y deshabilitar
            document.getElementById('reg-tipo-usuario').value = 'paciente';
            document.getElementById('reg-nombres').value = data.nombres || '';
            document.getElementById('reg-nombres').disabled = true;
            document.getElementById('reg-apellidos').value = data.apellidos || '';
            document.getElementById('reg-apellidos').disabled = true;
            document.getElementById('reg-cedula').value = cedula;
            document.getElementById('reg-cedula').disabled = true;
            
            // Configurar modal
            document.getElementById('reg-step-cedula').classList.add('hide');
            document.getElementById('reg-step-details').classList.remove('hide');
            document.getElementById('reg-tipo-usuario-group').classList.add('hide');
            document.getElementById('reg-common-fields').classList.remove('hide');
            document.getElementById('reg-paciente-fields').classList.add('hide'); // Ocultar historia clínica
            document.getElementById('reg-psicologo-fields').classList.add('hide');
            document.getElementById('reg-security-questions-fields').classList.remove('hide'); // Mostrar preguntas de seguridad
            
            alert(`¡Hola ${data.nombres}! Ya estás registrado en el sistema. Crea tu usuario y contraseña de acceso.`);
        } else {
            isPreRegisteredPatient = false;
            
            // Llenar cédula y habilitar selector de rol
            document.getElementById('reg-cedula').value = cedula;
            document.getElementById('reg-nombres').value = '';
            document.getElementById('reg-apellidos').value = '';
            document.getElementById('reg-nombres').disabled = false;
            document.getElementById('reg-apellidos').disabled = false;
            document.getElementById('reg-cedula').disabled = false;
            
            // Ocultar sub-campos hasta que seleccionen rol
            document.getElementById('reg-common-fields').classList.add('hide');
            document.getElementById('reg-paciente-fields').classList.add('hide');
            document.getElementById('reg-psicologo-fields').classList.add('hide');
            document.getElementById('reg-security-questions-fields').classList.add('hide');
            
            const urlParams = new URLSearchParams(window.location.search);
            const refId = urlParams.get('ref_psicologo');
            if (refId) {
                document.getElementById('reg-tipo-usuario').value = 'paciente';
                document.getElementById('reg-tipo-usuario-group').classList.add('hide');
                toggleRegisterFields();
                document.getElementById('reg-psicologo-id').value = refId;
                const selectGroup = document.getElementById('reg-psicologo-id').closest('.form-group');
                if (selectGroup) selectGroup.style.display = 'none';
            } else {
                document.getElementById('reg-tipo-usuario').value = '';
                document.getElementById('reg-tipo-usuario-group').classList.remove('hide');
            }
            
            document.getElementById('reg-step-cedula').classList.add('hide');
            document.getElementById('reg-step-details').classList.remove('hide');
        }
    } catch (err) {
        statusMsg.textContent = "Error al verificar cédula. Intenta de nuevo.";
        statusMsg.className = "status-msg error-msg";
        statusMsg.classList.remove('hide');
    }
}

function toggleRegisterFields() {
    const role = document.getElementById('reg-tipo-usuario').value;
    const commonFields = document.getElementById('reg-common-fields');
    const psicologoFields = document.getElementById('reg-psicologo-fields');
    const pacienteFields = document.getElementById('reg-paciente-fields');
    
    // Si ya está pre-registrado, ignorar selector de rol y mantener historia oculta
    if (isPreRegisteredPatient) {
        commonFields.classList.remove('hide');
        psicologoFields.classList.add('hide');
        pacienteFields.classList.add('hide');
        document.getElementById('reg-security-questions-fields').classList.remove('hide');
        return;
    }
    
    if (role === 'psicologo') {
        commonFields.classList.remove('hide');
        psicologoFields.classList.remove('hide');
        pacienteFields.classList.add('hide');
        document.getElementById('reg-security-questions-fields').classList.add('hide');
    } else if (role === 'paciente') {
        commonFields.classList.remove('hide');
        psicologoFields.classList.add('hide');
        pacienteFields.classList.remove('hide');
        document.getElementById('reg-security-questions-fields').classList.remove('hide');
        
        // Restaurar display del selector de psicólogo asignado si no hay referral
        const urlParams = new URLSearchParams(window.location.search);
        const refId = urlParams.get('ref_psicologo');
        const selectGroup = document.getElementById('reg-psicologo-id').closest('.form-group');
        if (selectGroup) {
            if (refId) {
                selectGroup.style.display = 'none';
                document.getElementById('reg-psicologo-id').value = refId;
            } else {
                selectGroup.style.display = 'block';
            }
        }
    } else {
        commonFields.classList.add('hide');
        psicologoFields.classList.add('hide');
        pacienteFields.classList.add('hide');
    }
}

let isRegisterSubmitting = false;

async function submitRegister(e) {
    e.preventDefault();
    if (isRegisterSubmitting) return;
    
    const submitBtn = document.querySelector('#reg-form button[type="submit"]') || document.getElementById('reg-submit-btn');
    isRegisterSubmitting = true;
    if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.setAttribute('data-orig-text', submitBtn.textContent);
        submitBtn.textContent = 'Registrando...';
    }

    const errorMsg = document.getElementById('reg-error-msg');
    if (errorMsg) errorMsg.classList.add('hide');
    
    const getVal = (id) => {
        const el = document.getElementById(id);
        return el ? (el.value || '').trim() : '';
    };

    try {
        const tipo_usuario = getVal('reg-tipo-usuario');
        const nombres = getVal('reg-nombres');
        const apellidos = getVal('reg-apellidos');
        const username = getVal('reg-username');
        const password = getVal('reg-password');
        const cedula = getVal('reg-cedula');
        const telefono = getVal('reg-telefono');
        const email = getVal('reg-email');
        
        // Validaciones básicas con mensajes claros
        if (!nombres || !apellidos) {
            const msg = "Por favor, ingresa tu nombre y apellido.";
            if (errorMsg) { errorMsg.textContent = msg; errorMsg.classList.remove('hide'); }
            alert(msg);
            return;
        }
        if (!username) {
            const msg = "Por favor, elige un nombre de usuario.";
            if (errorMsg) { errorMsg.textContent = msg; errorMsg.classList.remove('hide'); }
            alert(msg);
            return;
        }
        if (!password || password.length < 4) {
            const msg = "La contraseña es requerida y debe tener al menos 4 caracteres.";
            if (errorMsg) { errorMsg.textContent = msg; errorMsg.classList.remove('hide'); }
            alert(msg);
            return;
        }
        if (!cedula) {
            const msg = "La cédula de identidad es requerida.";
            if (errorMsg) { errorMsg.textContent = msg; errorMsg.classList.remove('hide'); }
            alert(msg);
            return;
        }
        if (!tipo_usuario) {
            const msg = "Por favor, selecciona el tipo de cuenta (Psicólogo o Paciente).";
            if (errorMsg) { errorMsg.textContent = msg; errorMsg.classList.remove('hide'); }
            alert(msg);
            return;
        }
        
        const payload = {
            tipo_usuario, nombres, apellidos, username, password, cedula, telefono, email
        };
        
        if (tipo_usuario === 'psicologo') {
            payload.estudios = getVal('reg-estudios');
            payload.federacion = getVal('reg-federacion');
            payload.foto_titulo = await readFileAsBase64(document.getElementById('reg-foto-titulo'));
            payload.foto_documento = await readFileAsBase64(document.getElementById('reg-foto-documento'));
            
            if (!payload.estudios || !payload.federacion) {
                const msg = "Por favor, completa los campos de estudios y federación para psicólogo.";
                if (errorMsg) { errorMsg.textContent = msg; errorMsg.classList.remove('hide'); }
                alert(msg);
                return;
            }
        } else if (tipo_usuario === 'paciente') {
            payload.pregunta_seguridad_1 = getVal('reg-pregunta-1');
            payload.respuesta_seguridad_1 = getVal('reg-respuesta-1');
            payload.pregunta_seguridad_2 = getVal('reg-pregunta-2');
            payload.respuesta_seguridad_2 = getVal('reg-respuesta-2');
            
            if (isPreRegisteredPatient) {
                if (!payload.respuesta_seguridad_1 || !payload.respuesta_seguridad_2) {
                    const msg = "Por favor, completa las respuestas de seguridad para activar tu cuenta.";
                    if (errorMsg) { errorMsg.textContent = msg; errorMsg.classList.remove('hide'); }
                    alert(msg);
                    return;
                }
            } else {
                let targetPsicId = parseInt(getVal('reg-psicologo-id'));
                if (isNaN(targetPsicId) || !targetPsicId) {
                    const urlParams = new URLSearchParams(window.location.search);
                    const refId = urlParams.get('ref_psicologo');
                    if (refId) {
                        if (!isNaN(parseInt(refId))) {
                            targetPsicId = parseInt(refId);
                        } else if (typeof regPsychologists !== 'undefined' && regPsychologists && regPsychologists.length) {
                            const cleanRef = refId.toLowerCase().replace('psic.', '').replace('psic-', '');
                            const found = regPsychologists.find(p => 
                                (p.slug && p.slug.toLowerCase().includes(cleanRef)) || 
                                (p.username && p.username.toLowerCase().includes(cleanRef))
                            );
                            if (found) targetPsicId = found.id;
                        }
                    }
                }
                payload.psicologo_id = targetPsicId || 1;

                payload.pronombre = getVal('reg-pronombre');
                payload.genero = getVal('reg-genero');
                payload.edad = parseInt(getVal('reg-edad')) || 0;
                payload.lugar_nacimiento = getVal('reg-lugar-nac');
                payload.fecha_nacimiento = getVal('reg-fecha-nac');
                const ciudadVal = getVal('reg-ciudad');
                const paisVal = getVal('reg-pais');
                payload.pais = paisVal;
                payload.ciudad = ciudadVal;
                payload.residencia_actual = getVal('reg-residencia') || [ciudadVal, paisVal].filter(Boolean).join(', ');
                payload.con_quien_reside = getVal('reg-con-quien');
                payload.nivel_academico = getVal('reg-academico');
                payload.ocupacion = getVal('reg-ocupacion');
                payload.estado_civil = getVal('reg-estado-civil');
                payload.contacto_emergencia_nombre = getVal('reg-contacto-emergencia');
                payload.contacto_emergencia_parentesco = getVal('reg-contacto-parentesco');
                payload.motivo_consulta = getVal('reg-motivo-consulta');
                payload.expectativas = getVal('reg-expectativas');
                payload.farmacologia = getVal('reg-farmacologia');
                
                if (!payload.psicologo_id) {
                    const msg = "Por favor, selecciona un psicólogo asignado.";
                    if (errorMsg) { errorMsg.textContent = msg; errorMsg.classList.remove('hide'); }
                    alert(msg);
                    return;
                }
                if (!payload.edad || payload.edad < 1) {
                    const msg = "Por favor, ingresa tu edad.";
                    if (errorMsg) { errorMsg.textContent = msg; errorMsg.classList.remove('hide'); }
                    alert(msg);
                    return;
                }
                if (!payload.contacto_emergencia_nombre || !payload.contacto_emergencia_parentesco) {
                    const msg = "El contacto de emergencia (nombre y parentesco) es requerido.";
                    if (errorMsg) { errorMsg.textContent = msg; errorMsg.classList.remove('hide'); }
                    alert(msg);
                    return;
                }
                if (!payload.motivo_consulta) {
                    const msg = "El motivo de consulta es requerido para completar tu historia clínica.";
                    if (errorMsg) { errorMsg.textContent = msg; errorMsg.classList.remove('hide'); }
                    alert(msg);
                    return;
                }
                if (!payload.respuesta_seguridad_1 || !payload.respuesta_seguridad_2) {
                    const msg = "Las respuestas de seguridad son requeridas para proteger tu cuenta.";
                    if (errorMsg) { errorMsg.textContent = msg; errorMsg.classList.remove('hide'); }
                    alert(msg);
                    return;
                }
            }
        }
        
        const res = await fetch('/api/register', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        
        if (res.ok) {
            alert(data.success || "Cuenta registrada con éxito. Inicia sesión a continuación.");
            closeRegisterModal();
        } else {
            const errText = data.error || "Error al registrar la cuenta. Verifica los datos ingresados.";
            if (errorMsg) { errorMsg.textContent = errText; errorMsg.classList.remove('hide'); }
            alert("Error de registro: " + errText);
        }
    } catch (err) {
        console.error("Error submitRegister:", err);
        const errText = "Error al procesar el registro. Intenta de nuevo.";
        if (errorMsg) { errorMsg.textContent = errText; errorMsg.classList.remove('hide'); }
        alert(errText);
    } finally {
        isRegisterSubmitting = false;
        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.textContent = submitBtn.getAttribute('data-orig-text') || 'Registrar Cuenta';
        }
    }
}

// ==========================================
// MÉTODOS DE PAGO DEL PSICÓLOGO
// ==========================================
async function loadPaymentMethods() {
    try {
        const res = await fetch('/api/admin/payment-methods');
        if (!res.ok) return;
        const data = await res.json();
        document.getElementById('set-pagos-instrucciones').value = data.metodos_pago || '';
    } catch (err) {
        console.error("Error loading payment methods:", err);
    }
}

async function savePaymentMethods() {
    const statusMsg = document.getElementById('set-pagos-status-msg');
    statusMsg.classList.add('hide');
    const metodos = document.getElementById('set-pagos-instrucciones').value;
    
    try {
        const res = await fetch('/api/admin/payment-methods', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ metodos_pago: metodos })
        });
        const data = await res.json();
        
        if (res.ok) {
            statusMsg.textContent = data.success || "Métodos de pago guardados.";
            statusMsg.className = "status-msg success-msg";
            statusMsg.classList.remove('hide');
        } else {
            statusMsg.textContent = data.error || "Error al guardar.";
            statusMsg.className = "status-msg error-msg";
            statusMsg.classList.remove('hide');
        }
    } catch (err) {
        statusMsg.textContent = "Error de conexión.";
        statusMsg.className = "status-msg error-msg";
        statusMsg.classList.remove('hide');
    }
}

// ==========================================
// NAVEGACIÓN Y CARGAS EN PORTAL DE PACIENTES
// ==========================================
function switchPatientFinanceTab(tabId) {
    document.querySelectorAll('.patient-finance-tab-content').forEach(card => card.classList.add('hide'));
    document.querySelectorAll('[id^="pat-tab-"]').forEach(btn => {
        btn.classList.remove('btn-primary');
        btn.classList.add('btn-secondary');
    });
    
    const activeCard = document.getElementById(`pat-card-${tabId}`);
    if (activeCard) activeCard.classList.remove('hide');
    
    const activeBtn = document.getElementById(`pat-tab-${tabId}`);
    if (activeBtn) {
        activeBtn.classList.remove('btn-secondary');
        activeBtn.classList.add('btn-primary');
    }
    
    if (tabId === 'citas') {
        loadPatientAppointmentsList();
    }
}

async function loadPatientAppointmentsList() {
    const tbody = document.getElementById('pat-appointments-list-body');
    if (!tbody) return;
    tbody.innerHTML = '<tr><td colspan="5" class="text-center text-secondary">Cargando citas...</td></tr>';
    
    try {
        const res = await fetch('/api/patient/appointments');
        if (!res.ok) {
            tbody.innerHTML = '<tr><td colspan="5" class="text-center text-danger">Error al cargar citas.</td></tr>';
            return;
        }
        const list = await res.json();
        tbody.innerHTML = '';
        
        if (list.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="text-center text-secondary">No tienes consultas agendadas.</td></tr>';
            return;
        }
        
        list.forEach(e => {
            const tr = document.createElement('tr');
            
            let estadoCita = 'Agendada';
            let badgeCitaClass = 'badge-info';
            
            if (e.evolucionada === 1) {
                estadoCita = 'Realizada';
                badgeCitaClass = 'badge-success';
            } else if (e.estado_pago === 'Cancelada' || e.estado_pago === 'Cancelada con aviso') {
                estadoCita = 'Cancelada';
                badgeCitaClass = 'badge-danger';
            } else if (e.estado_pago === 'Reprogramada') {
                estadoCita = 'Reprogramada';
                badgeCitaClass = 'badge-warning';
            }
            
            const badgePagoClass = (e.estado_pago === 'Paga' || e.estado_pago === 'Prepagada') ? 'badge-success' : 
                                   ((e.estado_pago === 'Cancelada' || e.estado_pago === 'Cancelada con aviso' || e.estado_pago === 'Reprogramada') ? 'badge-secondary' : 'badge-danger');
            
            tr.innerHTML = `
                <td><strong>${e.fecha} ${format12h(e.hora)}</strong></td>
                <td>${e.tipo_consulta}</td>
                <td><span class="badge ${badgeCitaClass}">${estadoCita}</span></td>
                <td><span class="badge ${badgePagoClass}">${e.estado_pago}</span></td>
                <td style="font-size:0.75rem; color:var(--text-muted); max-width: 150px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${e.referencia || ''}">${e.referencia || '-'}</td>
            `;
            tbody.appendChild(tr);
        });
    } catch (err) {
        tbody.innerHTML = '<tr><td colspan="5" class="text-center text-danger">Error de conexión.</td></tr>';
    }
}

// ==========================================
// GESTIÓN DE SUPERADMINISTRADOR
// ==========================================
function formatPatientLocation(p) {
    if (!p) return 'N/A';
    const parts = [];
    const res = (p.residencia_actual || '').trim();
    const city = (p.ciudad || '').trim();
    const country = (p.pais || '').trim();
    
    if (res) {
        parts.push(res);
    } else if (city) {
        parts.push(city);
    }
    
    if (country && !parts.join(', ').toLowerCase().includes(country.toLowerCase())) {
        parts.push(country);
    }
    
    return parts.length > 0 ? parts.join(', ') : 'N/A';
}



async function loadSuperadminData() {
    const tbody = document.getElementById('superadmin-therapists-body');
    if (!tbody) return;
    tbody.innerHTML = '<tr><td colspan="5" class="text-center text-secondary">Cargando psicólogos...</td></tr>';
    
    try {
        const res = await fetch('/api/superadmin/therapists');
        if (!res.ok) {
            tbody.innerHTML = '<tr><td colspan="5" class="text-center text-danger">Error de autorización.</td></tr>';
            return;
        }
        const list = await res.json();
        tbody.innerHTML = '';
        
        if (list.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="text-center text-secondary">No hay psicólogos registrados.</td></tr>';
            return;
        }
        
        list.forEach(p => {
            const tr = document.createElement('tr');
            const activeLabel = p.activo === 1 ? 'Activo' : 'Inactivo';
            const activeClass = p.activo === 1 ? 'badge-success' : 'badge-danger';
            const buttonText = p.activo === 1 ? 'Desactivar' : 'Activar';
            const buttonClass = p.activo === 1 ? 'btn-danger' : 'btn-primary';
            
            const escName = (p.nombres || '').replace(/'/g, "\\'");
            const tituloBtn = p.foto_titulo ? `<button type="button" class="btn btn-sm btn-outline-primary" style="padding:2px 6px; font-size:0.75rem; margin-right:4px;" onclick="viewDocumentPreview(\`${p.foto_titulo}\`, 'Título de ${escName}', ${p.id}, 'titulo')">📄 Título</button>` : `<button type="button" class="btn btn-sm btn-outline-primary" style="padding:2px 6px; font-size:0.75rem; margin-right:4px;" onclick="viewDocumentPreview('', 'Título de ${escName}', ${p.id}, 'titulo')">➕ Título</button>`;
            const docBtn = p.foto_documento ? `<button type="button" class="btn btn-sm btn-outline-secondary" style="padding:2px 6px; font-size:0.75rem;" onclick="viewDocumentPreview(\`${p.foto_documento}\`, 'Documento de ${escName}', ${p.id}, 'documento')">🪪 Cédula</button>` : `<button type="button" class="btn btn-sm btn-outline-secondary" style="padding:2px 6px; font-size:0.75rem;" onclick="viewDocumentPreview('', 'Documento de ${escName}', ${p.id}, 'documento')">➕ Cédula</button>`;
            const docCell = `${tituloBtn}${docBtn}`;

            let trialBadge = '';
            let subBtnText = p.suscripcion_paga === 1 ? '⭐ Suscripción Paga' : '🚀 Activar Suscripción';
            let subBtnStyle = p.suscripcion_paga === 1 ? 'background: #10b981; color: #fff;' : 'background: #6366f1; color: #fff; font-weight: 700;';
            
            if (p.suscripcion_paga === 1) {
                trialBadge = '<span class="badge" style="background:#10b981; color:#fff; padding: 4px 8px; border-radius: 4px; font-size: 0.75rem; font-weight: 700;">✓ Suscripción Paga</span>';
            } else if (p.fecha_expiracion_prueba) {
                const expDate = new Date(p.fecha_expiracion_prueba);
                const regDate = p.fecha_registro ? new Date(p.fecha_registro) : null;
                const diffHours = (expDate - new Date()) / (1000 * 60 * 60);
                const regStr = regDate && !isNaN(regDate) ? regDate.toLocaleDateString('es-ES', { day: '2-digit', month: '2-digit', year: '2-digit' }) : '';
                const expStr = expDate && !isNaN(expDate) ? expDate.toLocaleDateString('es-ES', { day: '2-digit', month: '2-digit', year: '2-digit' }) : '';
                
                if (diffHours <= 0) {
                    trialBadge = `<div style="display:flex; flex-direction:column; align-items:center; gap:2px;">
                        <span class="badge" style="background:#ef4444; color:#fff; padding: 3px 6px; border-radius: 4px; font-size: 0.75rem; font-weight: 700;">⚠️ Prueba Expirada</span>
                        <span style="font-size:0.7rem; color:var(--text-muted);">Venció: ${expStr}</span>
                    </div>`;
                } else {
                    const daysLeft = Math.ceil(diffHours / 24);
                    const rangeText = regStr ? `${regStr} al ${expStr}` : `Vence: ${expStr}`;
                    trialBadge = `<div style="display:flex; flex-direction:column; align-items:center; gap:2px;">
                        <span class="badge" style="background:#f59e0b; color:#fff; padding: 3px 6px; border-radius: 4px; font-size: 0.75rem; font-weight: 700;">⏳ Prueba (${daysLeft} días disponibles)</span>
                        <span style="font-size:0.7rem; color:var(--text-muted); font-weight:600;">📅 ${rangeText}</span>
                    </div>`;
                }
            } else {
                trialBadge = '<span class="badge" style="background:#6b7280; color:#fff; padding: 3px 6px; border-radius: 4px; font-size: 0.75rem;">Sin Prueba</span>';
            }

            tr.innerHTML = `
                <td style="padding: 0.75rem; border-bottom: 1px solid var(--border-color); font-weight: 600;">${p.username}</td>
                <td style="padding: 0.75rem; border-bottom: 1px solid var(--border-color);">${p.nombres} ${p.apellidos}</td>
                <td style="padding: 0.75rem; border-bottom: 1px solid var(--border-color);">
                    ${docCell}
                </td>
                <td style="padding: 0.75rem; border-bottom: 1px solid var(--border-color); font-size: 0.8rem;">
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.35rem;">
                        <label style="display:flex; align-items:center; gap:0.25rem; cursor:pointer;"><input type="checkbox" ${p.bloqueo_registro === 1 ? 'checked' : ''} onchange="toggleTherapistFeature(${p.id}, 'registro', this.checked)"> Bloquear Registro</label>
                        <label style="display:flex; align-items:center; gap:0.25rem; cursor:pointer;"><input type="checkbox" ${p.bloqueo_evoluciones === 1 ? 'checked' : ''} onchange="toggleTherapistFeature(${p.id}, 'evoluciones', this.checked)"> Bloquear Evoluciones</label>
                        <label style="display:flex; align-items:center; gap:0.25rem; cursor:pointer;"><input type="checkbox" ${p.bloqueo_finanzas === 1 ? 'checked' : ''} onchange="toggleTherapistFeature(${p.id}, 'finanzas', this.checked)"> Bloquear Finanzas</label>
                        <label style="display:flex; align-items:center; gap:0.25rem; cursor:pointer;"><input type="checkbox" ${p.bloqueo_agenda === 1 ? 'checked' : ''} onchange="toggleTherapistFeature(${p.id}, 'agenda', this.checked)"> Bloquear Agenda</label>
                        <label style="display:flex; align-items:center; gap:0.25rem; cursor:pointer;"><input type="checkbox" ${p.bloqueo_mensajes === 1 ? 'checked' : ''} onchange="toggleTherapistFeature(${p.id}, 'mensajes', this.checked)"> Bloquear Recordatorios</label>
                        <label style="display:flex; align-items:center; gap:0.25rem; cursor:pointer;"><input type="checkbox" ${p.bloqueo_pizarra === 1 ? 'checked' : ''} onchange="toggleTherapistFeature(${p.id}, 'pizarra', this.checked)"> Bloquear Pizarra</label>
                        <label style="display:flex; align-items:center; gap:0.25rem; cursor:pointer;"><input type="checkbox" ${p.bloqueo_herramientas === 1 ? 'checked' : ''} onchange="toggleTherapistFeature(${p.id}, 'herramientas', this.checked)"> Bloquear Herramientas</label>
                        <label style="display:flex; align-items:center; gap:0.25rem; cursor:pointer; color: #b91c1c; font-weight: 700; grid-column: 1 / 3; border-top: 1px dashed var(--border-color); padding-top: 0.35rem; margin-top: 0.25rem;">
                            <input type="checkbox" ${p.aviso_pago === 1 ? 'checked' : ''} onchange="toggleTherapistAvisoPago(${p.id})"> Activar Aviso de Pago (No Solvente)
                        </label>
                    </div>
                </td>
                <td style="padding: 0.75rem; border-bottom: 1px solid var(--border-color); text-align: center;">
                    <div style="display: flex; flex-direction: column; gap: 0.35rem; align-items: center;">
                        <div style="margin-bottom: 0.2rem;">
                            ${trialBadge}
                        </div>
                        <div style="display: flex; gap: 0.35rem;">
                            <button class="btn btn-sm" style="padding: 2px 8px; font-size: 0.75rem; ${subBtnStyle}" onclick="toggleTherapistSubscription(${p.id})">${subBtnText}</button>
                            <button class="btn btn-sm ${buttonClass}" style="padding: 2px 8px; font-size: 0.75rem;" onclick="toggleTherapistActive(${p.id})">${buttonText}</button>
                        </div>
                        <button type="button" class="btn btn-sm" style="padding: 3px 8px; font-size: 0.75rem; background-color: #ef4444; color: #ffffff; border: none; border-radius: 4px; font-weight: 700; cursor: pointer; display: inline-flex; align-items: center; gap: 4px; margin-top: 0.2rem;" onclick="deleteTherapistAccount(${p.id}, \`${escName}\`)">🗑️ Eliminar</button>
                    </div>
                </td>
            `;
            tbody.appendChild(tr);
        });
    } catch (err) {
        tbody.innerHTML = '<tr><td colspan="5" class="text-center text-danger">Error al cargar datos.</td></tr>';
    }
}

async function toggleTherapistSubscription(userId) {
    if (!confirm("¿Estás seguro de cambiar el estado de Suscripción Paga de este psicólogo?")) return;
    try {
        const res = await fetch(`/api/superadmin/therapists/${userId}/toggle-subscription`, { method: 'POST' });
        if (res.ok) {
            loadSuperadminData();
        } else {
            alert("Error al cambiar estado de suscripción.");
        }
    } catch (err) {
        alert("Error de conexión.");
    }
}

async function toggleTherapistActive(userId) {
    if (!confirm("¿Estás seguro de cambiar el estado de acceso de este psicólogo?")) return;
    try {
        const res = await fetch(`/api/superadmin/therapists/${userId}/toggle-active`, { method: 'POST' });
        if (res.ok) {
            loadSuperadminData();
        } else {
            alert("Error al cambiar estado.");
        }
    } catch (err) {
        alert("Error de conexión.");
    }
}

async function toggleTherapistFeature(userId, feature, isChecked) {
    const status = isChecked ? 1 : 0;
    try {
        const res = await fetch(`/api/superadmin/therapists/${userId}/toggle-feature`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ feature, status })
        });
        if (!res.ok) {
            alert("Error al cambiar estado de función.");
            loadSuperadminData();
        }
    } catch (err) {
        alert("Error de conexión.");
        loadSuperadminData();
    }
}

async function toggleTherapistAvisoPago(userId) {
    try {
        const res = await fetch(`/api/superadmin/therapists/${userId}/toggle-aviso-pago`, {
            method: 'POST'
        });
        if (!res.ok) {
            alert("Error al cambiar estado de aviso de pago.");
            loadSuperadminData();
        }
    } catch (err) {
        alert("Error de conexión.");
        loadSuperadminData();
    }
}

// openModal and closeModal defined at line 5278 with window exports

function viewDocumentPreview(docSrc, title, therapistId, docType) {
    const titleEl = document.getElementById('doc-preview-title');
    const container = document.getElementById('doc-preview-container');
    const downloadBtn = document.getElementById('doc-preview-download-btn');
    
    if (titleEl) titleEl.textContent = title || 'Documento del Psicólogo';
    
    let srcStr = String(docSrc || '').trim();
    const isLegacyFakepath = !srcStr || srcStr === 'undefined' || srcStr === 'null' || srcStr.includes('fakepath') || srcStr === 'titulo.jpg' || srcStr === 'cedula.jpg';
    
    if (container) {
        container.innerHTML = '';
        if (isLegacyFakepath) {
            const fileNameDisplay = srcStr ? srcStr.replace(/^.*[\\\/]/, '') : 'Ninguno';
            container.innerHTML = `
                <div style="width:100%; text-align:center; padding:1.25rem; background:#fff8e6; border:1.5px solid #ffe58f; border-radius:10px;">
                    <div style="font-size:2.2rem; margin-bottom:0.5rem;">📄⚠️</div>
                    <h4 style="margin:0 0 0.5rem 0; color:#b78103; font-weight:700; font-size:1.05rem;">Documento registrado previamente en modo texto</h4>
                    <p style="font-size:0.85rem; color:#785a00; line-height:1.4; margin-bottom:1rem;">
                        Este psicólogo fue registrado en una versión previa que guardó el nombre de archivo local (<code>${fileNameDisplay}</code>) en lugar del archivo real.<br>Puedes adjuntar y guardar el archivo PDF o imagen oficial ahora mismo:
                    </p>
                    <div style="background:#ffffff; padding:1rem; border-radius:8px; border:1px solid #ffe58f; display:flex; flex-direction:column; gap:0.75rem; align-items:center;">
                        <label style="font-size:0.82rem; font-weight:600; color:#555;">Seleccionar PDF o Imagen:</label>
                        <input type="file" id="sa-reupload-doc-input" accept="image/*,.pdf" class="form-control" style="max-width:360px; font-size:0.82rem;">
                        <button type="button" class="btn btn-primary btn-sm" onclick="saveTherapistDocumentFromModal(${therapistId}, '${docType}')" style="font-weight:700; padding:0.4rem 1.25rem;">
                            💾 Subir y Guardar Documento Ahora
                        </button>
                    </div>
                </div>
            `;
            if (downloadBtn) downloadBtn.style.display = 'none';
        } else {
            if (downloadBtn) downloadBtn.style.display = 'inline-block';
            const isPdf = srcStr.startsWith('data:application/pdf') || srcStr.toLowerCase().includes('.pdf');
            if (isPdf) {
                container.innerHTML = `
                    <div style="width:100%;">
                        <iframe src="${srcStr}" style="width:100%; height:480px; border:none; border-radius:8px; background:#f9fafb;"></iframe>
                        <div style="margin-top:10px; display:flex; justify-content:center; gap:10px;">
                            <a href="${srcStr}" target="_blank" class="btn btn-sm btn-primary" style="font-weight:700;">🔗 Abrir / Descargar PDF en pestaña nueva</a>
                        </div>
                    </div>`;
            } else {
                container.innerHTML = `
                    <div style="width:100%;">
                        <img src="${srcStr}" style="max-width:100%; max-height:480px; border-radius:8px; object-fit:contain; box-shadow: 0 4px 14px rgba(0,0,0,0.18);" alt="Documento" onerror="this.onerror=null; this.parentElement.innerHTML='<div class=\\'text-center py-4\\'><p class=\\'text-muted\\'>📄 Documento adjunto: <strong>${srcStr.replace(/^.*[\\\/]/, '')}</strong></p><a href=\\'${srcStr}\\' target=\\'_blank\\' class=\\'btn btn-primary btn-sm mt-2\\'>📥 Abrir / Descargar Documento</a></div>';">
                    </div>`;
            }
            
            if (downloadBtn) {
                downloadBtn.onclick = function() {
                    const a = document.createElement('a');
                    a.href = srcStr;
                    a.target = '_blank';
                    let ext = '.png';
                    if (srcStr.startsWith('data:application/pdf') || srcStr.toLowerCase().includes('.pdf')) ext = '.pdf';
                    else if (srcStr.startsWith('data:image/jpeg') || srcStr.toLowerCase().includes('.jpg') || srcStr.toLowerCase().includes('.jpeg')) ext = '.jpg';
                    
                    const cleanTitle = (title || 'documento_adjunto').replace(/[^a-z0-9]/gi, '_').toLowerCase();
                    a.download = cleanTitle.endsWith(ext) ? cleanTitle : cleanTitle + ext;
                    document.body.appendChild(a);
                    a.click();
                    document.body.removeChild(a);
                };
            }
        }
    }
    
    openModal('doc-preview-modal');
}

async function saveTherapistDocumentFromModal(therapistId, docType) {
    const input = document.getElementById('sa-reupload-doc-input');
    if (!input || !input.files || !input.files[0]) {
        alert('Por favor selecciona un archivo PDF o imagen primero.');
        return;
    }
    const file = input.files[0];
    const reader = new FileReader();
    reader.onload = async function() {
        const base64Data = reader.result;
        try {
            const bodyPayload = {};
            if (docType === 'titulo') bodyPayload.foto_titulo = base64Data;
            else bodyPayload.foto_documento = base64Data;
            
            const res = await fetch(`/api/superadmin/therapists/${therapistId}/update-documents`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(bodyPayload)
            });
            const data = await res.json();
            if (res.ok) {
                alert('¡Documento guardado y actualizado con éxito!');
                closeModal('doc-preview-modal');
                if (typeof loadSuperadminData === 'function') loadSuperadminData();
            } else {
                alert('Error: ' + (data.error || 'No se pudo guardar el documento.'));
            }
        } catch(err) {
            alert('Error de conexión al guardar el documento.');
        }
    };
    reader.readAsDataURL(file);
}
window.saveTherapistDocumentFromModal = saveTherapistDocumentFromModal;
window.viewDocumentPreview = viewDocumentPreview;

// ==========================================
// AUTO-AGENDA RÁPIDA (FAST BOOKING)
// ==========================================
let fastBookingMonth = new Date().getMonth();
let fastBookingYear = new Date().getFullYear();
let fastBookingTherapistId = null;

async function checkFastBookingQuery() {
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.has('fast_booking')) {
        const paramVal = urlParams.get('fast_booking');
        if (!paramVal) return false;
        fastBookingTherapistId = paramVal;
        
        const loginScreen = document.getElementById('auth-screen');
        if (loginScreen) loginScreen.classList.add('hide');
        
        const fastScreen = document.getElementById('fast-booking-screen');
        if (fastScreen) fastScreen.classList.remove('hide');
        
        try {
            const res = await fetch(`/api/active-psychologists`);
            if (res.ok) {
                const psychologists = await res.json();
                const matched = psychologists.find(p => 
                    String(p.id) === String(fastBookingTherapistId) || 
                    (p.slug && p.slug.toLowerCase() === String(fastBookingTherapistId).toLowerCase()) ||
                    (p.username && p.username.toLowerCase() === String(fastBookingTherapistId).toLowerCase())
                );
                const titleEl = document.getElementById('fast-booking-therapist-name');
                if (titleEl) {
                    if (matched) {
                        titleEl.textContent = `Psic. ${matched.nombres} ${matched.apellidos}`;
                    } else if (psychologists.length > 0) {
                        titleEl.textContent = `Psic. ${psychologists[0].nombres} ${psychologists[0].apellidos}`;
                    } else {
                        titleEl.textContent = `Psic. Paulo Mora`;
                    }
                }
            }
        } catch (e) {
            console.error("Error al obtener nombre de terapeuta para auto-agenda:", e);
        }
        
        // Cargar modalidades del terapeuta asignado para auto-agenda rápida
        try {
            const mRes = await fetch(`/api/psychologists/${fastBookingTherapistId}/modalities`);
            if (mRes.ok) {
                const modalities = await mRes.json();
                const selectElement = document.getElementById('fast-modalidad');
                if (selectElement) {
                    selectElement.innerHTML = '';
                    modalities.forEach(m => {
                        const opt = document.createElement('option');
                        opt.value = m;
                        opt.textContent = m;
                        selectElement.appendChild(opt);
                    });
                }
            }
        } catch (e) {
            console.error("Error al obtener modalidades para auto-agenda:", e);
        }
        
        initFastTimeZoneSelector(); renderFastCalendar();
        return true;
    }
    
    if (urlParams.has('ref_psicologo')) {
        openRegisterModal();
        return true;
    }
    
    return false;
}

function changeFastBookingMonth(dir) {
    fastBookingMonth += dir;
    if (fastBookingMonth < 0) {
        fastBookingMonth = 11;
        fastBookingYear--;
    } else if (fastBookingMonth > 11) {
        fastBookingMonth = 0;
        fastBookingYear++;
    }
    initFastTimeZoneSelector(); renderFastCalendar();
}

async function renderFastCalendar() {
    const headerTitle = document.getElementById('fast-cal-month-year');
    if (!headerTitle) return;
    
    headerTitle.textContent = `${monthNames[fastBookingMonth]} ${fastBookingYear}`;
    
    const grid = document.getElementById('fast-cal-days-grid');
    grid.innerHTML = '<div style="grid-column: span 7; text-align: center; padding: 1rem;"><span class="text-secondary text-sm">Cargando disponibilidad...</span></div>';
    
    const modality = document.getElementById('fast-modalidad').value;
    
    let availableDates = [];
    try {
        const monthForApi = fastBookingMonth + 1;
        const res = await fetch(`/api/patient/available-dates?year=${fastBookingYear}&month=${monthForApi}&modalidad=${modality}&psicologo_id=${fastBookingTherapistId}`);
        if (res.ok) {
            const data = await res.json();
            availableDates = data.dates || [];
        }
    } catch (e) {
        console.error("Error al obtener disponibilidad del calendario rápido:", e);
    }
    
    grid.innerHTML = '';
    
    const firstDay = new Date(fastBookingYear, fastBookingMonth, 1).getDay();
    const totalDays = new Date(fastBookingYear, fastBookingMonth + 1, 0).getDate();
    
    for (let i = 0; i < firstDay; i++) {
        const spacer = document.createElement('div');
        grid.appendChild(spacer);
    }
    
    const today = new Date();
    today.setHours(0,0,0,0);
    
    for (let day = 1; day <= totalDays; day++) {
        const cell = document.createElement('div');
        cell.className = 'fast-cal-day-cell';
        cell.textContent = day;
        
        const cellMonthStr = String(fastBookingMonth + 1).padStart(2, '0');
        const cellDayStr = String(day).padStart(2, '0');
        const dateStr = `${fastBookingYear}-${cellMonthStr}-${cellDayStr}`;
        
        const cellDate = new Date(fastBookingYear, fastBookingMonth, day);
        cellDate.setHours(0,0,0,0);
        
        const isPast = cellDate < today;
        const isAvailable = availableDates.includes(dateStr);
        
        if (isPast || !isAvailable) {
            cell.className = 'pat-cal-day-cell disabled';
            cell.style.color = '#ccc';
            cell.style.cursor = 'not-allowed';
            cell.style.display = 'inline-flex';
            cell.style.alignItems = 'center';
            cell.style.justifyContent = 'center';
            cell.style.margin = 'auto';
            cell.style.width = '32px';
            cell.style.height = '32px';
        } else {
            cell.className = 'pat-cal-day-cell available';
            cell.style.cursor = 'pointer';
            cell.style.display = 'inline-flex';
            cell.style.alignItems = 'center';
            cell.style.justifyContent = 'center';
            cell.style.margin = 'auto';
            cell.style.width = '32px';
            cell.style.height = '32px';
            cell.style.borderRadius = '50%';
            cell.style.border = '2px solid #10b981';
            cell.style.fontWeight = '700';
            cell.style.color = '#047857';
            cell.style.backgroundColor = '#ecfdf5';
            
            cell.onclick = () => {
                document.querySelectorAll('.fast-cal-day-cell.selected').forEach(c => {
                    c.style.backgroundColor = '#ecfdf5';
                    c.style.color = '#047857';
                    c.classList.remove('selected');
                });
                
                cell.classList.add('selected');
                cell.style.backgroundColor = '#10b981';
                cell.style.color = 'white';
                
                document.getElementById('fast-req-fecha').value = dateStr;
                document.getElementById('fast-req-hora').value = '';
                document.getElementById('fast-patient-details').classList.add('hide');
                
                fetchFastAvailableHours(dateStr);
            };
        }
        grid.appendChild(cell);
    }
}

async function fetchFastAvailableHours(dateStr) {
    const hoursGrid = document.getElementById('fast-hours-grid');
    const hoursContainer = document.getElementById('fast-hours-container');
    const hoursTitle = document.getElementById('fast-hours-title');
    
    // Formatear la fecha para feedback visual
    try {
        const parts = dateStr.split('-');
        const dObj = new Date(parseInt(parts[0]), parseInt(parts[1])-1, parseInt(parts[2]));
        const options = { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' };
        let dateFormatted = dObj.toLocaleDateString('es-ES', options);
        dateFormatted = dateFormatted.charAt(0).toUpperCase() + dateFormatted.slice(1);
        if (hoursTitle) {
            hoursTitle.textContent = `Los espacios para el día ${dateFormatted} son:`;
        }
    } catch(e) {
        if (hoursTitle) {
            hoursTitle.textContent = `Los espacios para el día ${dateStr} son:`;
        }
    }
    
    hoursGrid.innerHTML = '<span class="text-secondary text-sm">Consultando horarios...</span>';
    hoursContainer.classList.remove('hide');
    
    try {
        const modality = document.getElementById('fast-modalidad') ? document.getElementById('fast-modalidad').value : 'all';
        const res = await fetch(`/api/patient/available-slots?date=${dateStr}&modalidad=${encodeURIComponent(modality)}&psicologo_id=${fastBookingTherapistId}`);
        const data = await res.json();
        
        hoursGrid.innerHTML = '';
        
        const localSlots = [];
        const targetTz = document.getElementById('fast-tz-select') ? document.getElementById('fast-tz-select').value : getPatientUserTimeZone();
        
        if (data.slots && data.slots.length > 0) {
            data.slots.forEach(slotObj => {
                const hourStr = slotObj.hora_literal || slotObj.iso.substring(11, 16);
                const therapistDate = slotObj.iso.substring(0, 10);
                
                const converted = convertTimeFromVETToZone(therapistDate, hourStr, targetTz);
                
                localSlots.push({
                    displayTime: converted.timeStr,
                    displayFull: `${format12h(converted.timeStr)}${converted.dayOffsetStr}`,
                    therapistTime: format12h(hourStr),
                    valFecha: therapistDate,
                    valHour: hourStr
                });
            });
        }
        
        localSlots.sort((a, b) => a.displayTime.localeCompare(b.displayTime));
        
        if (localSlots.length > 0) {
            localSlots.forEach(slot => {
                const btn = document.createElement('button');
                btn.type = 'button';
                btn.className = 'btn-fast-hour';
                btn.innerHTML = `<div style="font-weight: 700; font-size: 0.92rem;">${slot.displayFull}</div><div style="font-size: 0.68rem; opacity: 0.85; font-weight: 500; margin-top: 2px;">(${slot.therapistTime} Venezuela)</div>`;
                
                btn.style.padding = '0.45rem 0.85rem';
                btn.style.border = '1.5px solid #10b981';
                btn.style.borderRadius = '12px';
                btn.style.backgroundColor = '#ecfdf5';
                btn.style.color = '#047857';
                btn.style.cursor = 'pointer';
                btn.style.textAlign = 'center';
                btn.style.display = 'inline-flex';
                btn.style.flexDirection = 'column';
                btn.style.alignItems = 'center';
                
                btn.onclick = () => {
                    document.querySelectorAll('.btn-fast-hour').forEach(b => {
                        b.style.backgroundColor = '#ecfdf5';
                        b.style.color = '#047857';
                    });
                    btn.style.backgroundColor = '#10b981';
                    btn.style.color = 'white';
                    
                    document.getElementById('fast-req-fecha').value = slot.valFecha;
                    document.getElementById('fast-req-hora').value = slot.valHour;
                    
                    document.getElementById('fast-patient-details').classList.remove('hide');
                };
                hoursGrid.appendChild(btn);
            });
        } else {
            hoursGrid.innerHTML = '<span class="text-secondary text-sm">No hay horarios disponibles para este día.</span>';
        }
    } catch (e) {
        hoursGrid.innerHTML = '<span class="text-danger text-sm">Error al cargar horarios.</span>';
    }
}

let isSubmittingFastBooking = false;
async function submitFastBooking(e) {
    e.preventDefault();
    if (isSubmittingFastBooking) return;
    
    const statusMsg = document.getElementById('fast-booking-status-msg');
    statusMsg.classList.add('hide');
    
    const submitBtn = document.querySelector('#fast-booking-form button[type="submit"]');
    
    const fecha = document.getElementById('fast-req-fecha').value;
    const hora = document.getElementById('fast-req-hora').value;
    const modalidad = document.getElementById('fast-modalidad').value;
    const cedula = document.getElementById('fast-cedula').value.trim();
    const nombres = document.getElementById('fast-nombres').value.trim();
    const apellidos = document.getElementById('fast-apellidos').value.trim();
    const telefono = document.getElementById('fast-telefono').value.trim();
    const emailEl = document.getElementById('fast-email');
    const email = emailEl ? emailEl.value.trim() : '';
    
    if (!fecha || !hora || !cedula || !nombres || !apellidos || !telefono || !email) {
        alert("Por favor completa todos los datos requeridos (incluyendo correo).");
        return;
    }
    
    try {
        isSubmittingFastBooking = true;
        if (submitBtn) { submitBtn.disabled = true; submitBtn.textContent = "Agendando..."; }
        
        const res = await fetch('/api/fast-booking/book', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                psicologo_id: fastBookingTherapistId,
                fecha,
                hora,
                modalidad,
                cedula,
                nombres,
                apellidos,
                telefono,
                email
            })
        });
        
        const data = await res.json();
        
        if (res.ok) {
            const therapistTitle = document.getElementById('fast-booking-therapist-name') ? document.getElementById('fast-booking-therapist-name').textContent : "Psicólogo";
            const gcalUrl = generateGoogleCalendarUrl(`Sesión de Terapia - ${therapistTitle}`, `Consulta Terapéutica (${modalidad})`, fecha, hora, 60);
            const targetTz = document.getElementById('fast-tz-select') ? document.getElementById('fast-tz-select').value : getPatientUserTimeZone();
            const converted = convertTimeFromVETToZone(fecha, hora, targetTz);
            
            statusMsg.innerHTML = `
                <div style="padding: 0.5rem 0;">
                    <div style="font-weight: 800; font-size: 1rem; color: #065f46; margin-bottom: 0.35rem;">🎉 ¡Cita agendada con éxito!</div>
                    <div style="font-size: 0.85rem; color: #047857; margin-bottom: 0.25rem;">🕒 <strong>Tu hora local (${targetTz}):</strong> ${format12h(converted.timeStr)}${converted.dayOffsetStr} (${converted.dateStr})</div>
                    <div style="font-size: 0.82rem; color: #065f46; opacity: 0.9; margin-bottom: 0.75rem;">🇻🇪 <strong>Hora Terapeuta (Venezuela):</strong> ${format12h(hora)} (${fecha})</div>
                    <a href="${gcalUrl}" target="_blank" rel="noopener" style="display: inline-flex; align-items: center; gap: 6px; background: #4285f4; color: white; padding: 0.55rem 1.1rem; border-radius: 8px; font-weight: 700; text-decoration: none; font-size: 0.85rem; box-shadow: 0 2px 4px rgba(66,133,244,0.3);">
                        📅 Agregar a mi Google Calendar
                    </a>
                </div>
            `;
            statusMsg.className = "status-msg success-msg";
            statusMsg.classList.remove('hide');
            document.getElementById('fast-booking-form').reset();
            document.getElementById('fast-hours-container').classList.add('hide');
            document.getElementById('fast-patient-details').classList.add('hide');
            initFastTimeZoneSelector(); renderFastCalendar();
        } else {
            statusMsg.textContent = data.error || "Error al agendar la consulta.";
            statusMsg.className = "status-msg error-msg";
            statusMsg.classList.remove('hide');
        }
    } catch (err) {
        statusMsg.textContent = "Error de conexión al agendar la cita.";
        statusMsg.className = "status-msg error-msg";
        statusMsg.classList.remove('hide');
    } finally {
        isSubmittingFastBooking = false;
        if (submitBtn) { submitBtn.disabled = false; submitBtn.textContent = "Confirmar & Agendar Cita"; }
    }
}

// ==========================================
// MENSAJES DE SOPORTE TÉCNICO Y SUPERADMIN
// ==========================================
function switchSuperadminTab(tabId) {
    document.querySelectorAll('.superadmin-tab-content').forEach(card => card.classList.add('hide'));
    const targetCard = document.getElementById(`sa-card-${tabId}`);
    if (targetCard) targetCard.classList.remove('hide');
    
    const tabTherapists = document.getElementById('sa-tab-therapists');
    const tabSupport = document.getElementById('sa-tab-support');
    
    if (tabId === 'therapists') {
        if (tabTherapists) {
            tabTherapists.classList.remove('btn-secondary');
            tabTherapists.classList.add('btn-primary');
        }
        if (tabSupport) {
            tabSupport.classList.remove('btn-primary');
            tabSupport.classList.add('btn-secondary');
        }
        loadSuperadminData();
    } else {
        if (tabTherapists) {
            tabTherapists.classList.remove('btn-primary');
            tabTherapists.classList.add('btn-secondary');
        }
        if (tabSupport) {
            tabSupport.classList.remove('btn-secondary');
            tabSupport.classList.add('btn-primary');
        }
        loadSupportTickets();
    }
}

async function submitSupportTicket(event) {
    event.preventDefault();
    const form = event.target;
    const mensajeInput = form.querySelector('textarea');
    const statusMsg = form.parentElement.querySelector('.status-msg') || document.getElementById('sup-status-msg');
    if (!mensajeInput || !statusMsg) return;
    
    const mensaje = mensajeInput.value.trim();
    if (!mensaje) return;
    
    statusMsg.classList.add('hide');
    
    try {
        const res = await fetch('/api/support/send', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mensaje })
        });
        const data = await res.json();
        if (res.ok) {
            statusMsg.textContent = 'Mensaje de soporte enviado con éxito.';
            statusMsg.className = 'status-msg success-msg';
            statusMsg.classList.remove('hide');
            mensajeInput.value = '';
            setTimeout(() => statusMsg.classList.add('hide'), 5000);
        } else {
            statusMsg.textContent = data.error || 'Error al enviar el mensaje.';
            statusMsg.className = 'status-msg error-msg';
            statusMsg.classList.remove('hide');
        }
    } catch (err) {
        statusMsg.textContent = 'Error de conexión con el servidor.';
        statusMsg.className = 'status-msg error-msg';
        statusMsg.classList.remove('hide');
    }
}

async function loadSupportTickets() {
    const tbody = document.getElementById('superadmin-support-body');
    if (!tbody) return;
    
    tbody.innerHTML = '<tr><td colspan="6" class="text-center text-secondary">Cargando mensajes...</td></tr>';
    
    try {
        const res = await fetch('/api/superadmin/support');
        if (!res.ok) {
            tbody.innerHTML = '<tr><td colspan="6" class="text-center text-danger">Error al cargar mensajes.</td></tr>';
            return;
        }
        const data = await res.json();
        tbody.innerHTML = '';
        
        if (data.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="text-center text-secondary">No hay mensajes de soporte registrados.</td></tr>';
            return;
        }
        
        data.forEach(t => {
            const tr = document.createElement('tr');
            
            let dateStr = t.fecha || '';
            try {
                const dateObj = new Date(t.fecha.replace(/-/g, '/'));
                if (!isNaN(dateObj)) {
                    dateStr = dateObj.toLocaleDateString([], {day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit'});
                }
            } catch(e) {}
            
            const badgeClass = t.leido ? 'badge-success' : 'badge-danger';
            const badgeText = t.leido ? 'Leído' : 'Pendiente';
            
            const nombreRemitente = t.nombre_remitente || t.remitente_nombre || 'Anónimo';
            const rolRemitente = t.rol_remitente || t.rol || 'paciente';
            const contactoRemitente = t.email_remitente || t.email || t.telefono || 'N/A';
            
            let actionBtn = '';
            if (!t.leido) {
                actionBtn = `<button class="btn btn-secondary btn-sm" onclick="markSupportTicketRead(${t.id})" style="padding: 0.25rem 0.5rem; font-size: 0.75rem; margin-right: 0.25rem;">Leído</button>`;
            }
            
            tr.innerHTML = `
                <td>${dateStr}</td>
                <td><strong>${nombreRemitente}</strong></td>
                <td><span class="badge badge-info" style="text-transform: capitalize;">${rolRemitente}</span></td>
                <td>${contactoRemitente}</td>
                <td style="white-space: pre-wrap; font-size: 0.85rem;">${t.mensaje}</td>
                <td>
                    <span class="badge ${badgeClass}" style="display:inline-block; margin-bottom:0.5rem;">${badgeText}</span>
                    <div style="display:flex; gap:0.25rem;">
                        ${actionBtn}
                        <button class="btn btn-secondary btn-sm text-danger" onclick="deleteSupportTicket(${t.id})" style="padding: 0.25rem 0.5rem; font-size: 0.75rem;">Eliminar</button>
                    </div>
                </td>
            `;
            tbody.appendChild(tr);
        });
    } catch (err) {
        tbody.innerHTML = '<tr><td colspan="6" class="text-center text-danger">Error de red al cargar mensajes.</td></tr>';
    }
}

async function markSupportTicketRead(ticketId) {
    try {
        const res = await fetch(`/api/superadmin/support/${ticketId}/mark-read`, {
            method: 'POST'
        });
        if (res.ok) {
            loadSupportTickets();
        } else {
            alert('Error al marcar el ticket como leído.');
        }
    } catch (err) {
        console.error(err);
    }
}

async function deleteSupportTicket(ticketId) {
    if (!confirm('¿Estás seguro de que deseas eliminar este mensaje de soporte?')) return;
    try {
        const res = await fetch(`/api/superadmin/support/${ticketId}`, {
            method: 'DELETE'
        });
        if (res.ok) {
            loadSupportTickets();
        } else {
            alert('Error al eliminar el mensaje.');
        }
    } catch (err) {
        console.error(err);
    }
}

// Alternar sub-vistas dentro de Mi Sesión del paciente
function switchPatientHomeSubView(subViewId) {
    document.querySelectorAll('.patient-home-sub-content').forEach(el => el.classList.add('hide'));
    
    const tabNext = document.getElementById('pat-home-tab-next');
    const tabHist = document.getElementById('pat-home-tab-history');
    const tabBook = document.getElementById('pat-home-tab-book');
    
    if (tabNext) tabNext.className = subViewId === 'next' ? 'btn btn-sm btn-primary' : 'btn btn-sm btn-secondary';
    if (tabHist) tabHist.className = subViewId === 'history' ? 'btn btn-sm btn-primary' : 'btn btn-sm btn-secondary';
    if (tabBook) tabBook.className = subViewId === 'book' ? 'btn btn-sm btn-primary' : 'btn btn-sm btn-secondary';
    
    if (subViewId === 'next') {
        const nextContent = document.getElementById('pat-sub-view-next-session');
        if (nextContent) nextContent.classList.remove('hide');
    } else if (subViewId === 'history') {
        const histContent = document.getElementById('pat-sub-view-history');
        if (histContent) histContent.classList.remove('hide');
        loadPatientAgendaHistory();
    } else {
        const bookContent = document.getElementById('pat-sub-view-booking');
        if (bookContent) bookContent.classList.remove('hide');
        initBookingCalendar();
    }
}

async function loadPatientAgendaHistory() {
    const tbody = document.getElementById('patient-agenda-history-table-body');
    if (!tbody) return;
    
    tbody.innerHTML = '<tr><td colspan="3" class="text-center text-secondary">Cargando historial de citas...</td></tr>';
    
    try {
        const res = await fetch('/api/patient/agenda-history');
        if (!res.ok) throw new Error("Error al consultar historial");
        const list = await res.json();
        
        if (!list || list.length === 0) {
            tbody.innerHTML = '<tr><td colspan="3" class="text-center text-secondary">No tienes citas o consultas registradas en tu historial.</td></tr>';
            return;
        }
        
        tbody.innerHTML = list.map(item => {
            let badgeStyle = 'background:#fef3c7;color:#92400e;';
            if (item.accion.includes('Paga') || item.accion.includes('Confirmada')) {
                badgeStyle = 'background:#d1fae5;color:#065f46;';
            } else if (item.accion.includes('tardía') || item.accion.includes('Cancelada')) {
                badgeStyle = 'background:#fee2e2;color:#dc2626;';
            } else if (item.accion.includes('Reprogramada')) {
                badgeStyle = 'background:#e0e7ff;color:#3730a3;';
            }
            
            return `
                <tr>
                    <td><strong>${item.fecha || ''}</strong> <span class="text-secondary" style="font-size:0.85rem;">${item.hora || ''}</span></td>
                    <td><span style="${badgeStyle} padding: 0.2rem 0.55rem; border-radius: 4px; font-size: 0.78rem; font-weight: 700;">${item.accion}</span></td>
                    <td>${item.tipo_consulta || 'Online'}</td>
                </tr>
            `;
        }).join('');
    } catch (err) {
        console.error(err);
        tbody.innerHTML = '<tr><td colspan="3" class="text-center text-danger">Error al cargar historial.</td></tr>';
    }
}

// Vista previa de archivos adjuntos mediante modal para evitar bloqueos
function openFilePreview(filename) {
    const modal = document.getElementById('preview-modal');
    const title = document.getElementById('preview-modal-title');
    const body = document.getElementById('preview-modal-body');
    if (!modal || !body) return;
    
    const isImage = /\.(jpg|jpeg|png|gif|webp)$/i.test(filename);
    title.textContent = isImage ? 'Visualizar Imagen Adjunta' : 'Ver Documento Adjunto';
    
    if (isImage) {
        body.innerHTML = `<img src="/api/files/${filename}" style="max-width: 100%; max-height: 60vh; border-radius: 8px; box-shadow: var(--shadow-md); object-fit: contain;">`;
    } else {
        body.innerHTML = `
            <div class="text-center py-4" style="width: 100%;">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width: 54px; height: 54px; color: var(--primary-color); margin-bottom: 1rem; margin-left: auto; margin-right: auto;"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                <p class="mb-4 text-secondary" style="font-weight: 500;">Este documento no se puede previsualizar en pantalla directamente.</p>
                <a href="/api/files/${filename}" download class="btn btn-primary" style="text-decoration: none; display: inline-flex; align-items: center; justify-content: center; padding: 0.65rem 1.5rem; font-weight: 600;">Descargar Documento</a>
            </div>
        `;
    }
    
    modal.classList.remove('hide');
}

function closePreviewModal() {
    const modal = document.getElementById('preview-modal');
    if (modal) modal.classList.add('hide');
}


function readFileAsBase64(fileInput) {
    return new Promise((resolve) => {
        if (!fileInput || !fileInput.files || !fileInput.files[0]) {
            resolve('');
            return;
        }
        const file = fileInput.files[0];
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = () => resolve('');
        reader.readAsDataURL(file);
    });
}

function openCreatePsychologistModal() {
    const modal = document.getElementById('modal-create-psychologist');
    if (modal) {
        document.getElementById('form-create-psychologist')?.reset();
        const err = document.getElementById('sa-psic-error');
        if (err) err.classList.add('hide');
        modal.classList.remove('hide');
    }
}

function closeCreatePsychologistModal() {
    const modal = document.getElementById('modal-create-psychologist');
    if (modal) modal.classList.add('hide');
}

async function submitCreatePsychologist(e) {
    e.preventDefault();
    const nombres = document.getElementById('sa-psic-nombres').value;
    const apellidos = document.getElementById('sa-psic-apellidos').value;
    const username = document.getElementById('sa-psic-username').value;
    const password = document.getElementById('sa-psic-password').value;
    const estudios = document.getElementById('sa-psic-estudios').value;
    const federacion = document.getElementById('sa-psic-federacion').value;
    
    const fotoTituloInput = document.getElementById('sa-psic-foto-titulo');
    const fotoDocInput = document.getElementById('sa-psic-foto-documento');
    const errorMsg = document.getElementById('sa-psic-error');
    if (errorMsg) errorMsg.classList.add('hide');
    
    const foto_titulo = await readFileAsBase64(fotoTituloInput);
    const foto_documento = await readFileAsBase64(fotoDocInput);
    
    try {
        const res = await fetch('/api/superadmin/create-psychologist', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                nombres, apellidos, username, password, estudios, federacion,
                foto_titulo, foto_documento
            })
        });
        const data = await res.json();
        if (res.ok) {
            alert('Psicólogo registrado exitosamente.');
            closeCreatePsychologistModal();
            loadSuperadminData();
        } else {
            if (errorMsg) {
                errorMsg.textContent = data.error || 'Error al registrar psicólogo.';
                errorMsg.classList.remove('hide');
            }
        }
    } catch (err) {
        if (errorMsg) {
            errorMsg.textContent = 'Error de conexión con el servidor.';
            errorMsg.classList.remove('hide');
        }
    }
}

// Historial clínico de sesiones evolucionadas para consultantes
async function openPatientSessionHistoryModal() {
    const modal = document.getElementById('pat-history-modal');
    const body = document.getElementById('pat-history-modal-body');
    if (!modal || !body) return;
    
    body.innerHTML = '<div class="text-center py-4"><span class="text-secondary">Cargando historial de sesiones...</span></div>';
    modal.classList.remove('hide');
    
    try {
        const res = await fetch('/api/patient/sessions');
        if (!res.ok) {
            body.innerHTML = '<div class="text-center py-4"><span class="text-danger">Error al cargar el historial. Asegúrese de haber iniciado sesión.</span></div>';
            return;
        }
        const sessions = await res.json();
        
        if (sessions.length === 0) {
            body.innerHTML = '<div class="text-center py-4"><span class="text-secondary">No tienes sesiones registradas en tu historial aún.</span></div>';
            return;
        }
        
        body.innerHTML = '';
        sessions.forEach((s, idx) => {
            const card = document.createElement('div');
            card.className = 'card mb-4';
            card.style.border = '1px solid var(--border-color)';
            card.style.boxShadow = 'var(--shadow-sm)';
            card.style.borderRadius = 'var(--radius-md)';
            card.style.overflow = 'hidden';
            card.style.backgroundColor = 'var(--card-bg)';
            
            // Formatear fecha
            const dateParts = s.fecha.split('-');
            const yearObj = parseInt(dateParts[0], 10);
            const monthObj = parseInt(dateParts[1], 10) - 1;
            const dayObj = parseInt(dateParts[2], 10);
            const d = new Date(yearObj, monthObj, dayObj);
            const options = { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' };
            let dateFormatted = d.toLocaleDateString('es-ES', options);
            dateFormatted = dateFormatted.charAt(0).toUpperCase() + dateFormatted.slice(1);
            
            let attachmentHtml = '';
            if (s.archivo_adjunto) {
                const isImg = /\.(jpg|jpeg|png|gif|webp)$/i.test(s.archivo_adjunto);
                attachmentHtml = `
                    <div class="mt-3 pt-3" style="border-top: 1px dashed rgba(0,0,0,0.06);">
                        <strong style="font-size: 0.85rem; color: var(--text-dark);">Archivo adjunto en la sesión:</strong><br>
                        <a href="#" onclick="openFilePreview('${s.archivo_adjunto}'); return false;" class="btn btn-secondary btn-sm" style="display: inline-flex; align-items: center; gap: 0.25rem; margin-top: 0.25rem; font-size: 0.75rem; padding: 0.25rem 0.5rem;">
                            <svg style="width:12px; height:12px;" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>
                            ${isImg ? 'Ver Imagen' : 'Descargar Documento'}
                        </a>
                    </div>
                `;
            }
            
            card.innerHTML = `
                <div class="card-header" style="background-color: var(--bg-light); display: flex; justify-content: space-between; align-items: center; padding: 0.75rem 1rem; border-bottom: 1.5px solid var(--border-color);">
                    <h4 style="margin: 0; font-size: 0.95rem; font-weight: 700; color: var(--primary-color);">Sesión Nº ${sessions.length - idx}</h4>
                    <span style="font-size: 0.78rem; font-weight: 600; color: var(--text-muted); background: white; padding: 2px 8px; border-radius: 4px; border: 1px solid var(--border-color);">${dateFormatted} (${s.modalidad})</span>
                </div>
                <div class="card-body" style="padding: 1.25rem;">
                    <div class="mb-3">
                        <strong style="font-size: 0.85rem; color: var(--text-dark); display: block; margin-bottom: 0.25rem;">📝 Resumen de la sesión:</strong>
                        <p class="text-secondary" style="font-size: 0.9rem; margin: 0; white-space: pre-wrap; line-height: 1.45;">${s.resumen_paciente || 'Sin resumen registrado para esta sesión.'}</p>
                    </div>
                    ${s.tareas_asignadas ? `
                    <div class="mb-3 pt-3" style="border-top: 1px dashed rgba(0,0,0,0.06);">
                        <strong style="font-size: 0.85rem; color: var(--text-dark); display: block; margin-bottom: 0.25rem;">Compromisos (Tareas):</strong>
                        <p class="text-secondary" style="font-size: 0.9rem; margin: 0; white-space: pre-wrap; line-height: 1.45;">${s.tareas_asignadas}</p>
                    </div>` : ''}
                    ${s.recursos_entregados ? `
                    <div class="mb-3 pt-3" style="border-top: 1px dashed rgba(0,0,0,0.06);">
                        <strong style="font-size: 0.85rem; color: var(--text-dark); display: block; margin-bottom: 0.25rem;">Recursos entregados:</strong>
                        <p class="text-secondary" style="font-size: 0.9rem; margin: 0; white-space: pre-wrap; line-height: 1.45;">${s.recursos_entregados}</p>
                    </div>` : ''}
                    ${attachmentHtml}
                </div>
            `;
            body.appendChild(card);
        });
    } catch (err) {
        body.innerHTML = '<div class="text-center py-4"><span class="text-danger">Error de red al conectar con el servidor.</span></div>';
    }
}

function closePatientSessionHistoryModal() {
    const modal = document.getElementById('pat-history-modal');
    if (modal) modal.classList.add('hide');
}

function openSupportFromSidebar() {
    switchView('settings');
    switchSettingsTab('soporte');
    toggleSidebar();
}

// Confirmar cita desde el portal de paciente
async function handlePatientConfirmAppointment(apptId) {
    try {
        const res = await fetch('/api/patient/confirm-appointment', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ appt_id: apptId })
        });
        const data = await res.json();
        if (data.error) {
            alert(data.error);
        } else {
            alert(data.success || 'Cita confirmada con éxito.');
            const patientId = sessionStorage.getItem('patient_id');
            if (patientId) loadPatientPortalData(patientId);
        }
    } catch (err) {
        console.error("Error al confirmar cita:", err);
        alert("Error de conexión al intentar confirmar la cita.");
    }
}

// Reprogramar cita: Lógica de Calendario y Modal
let reschedMonth = new Date().getMonth();
let reschedYear = new Date().getFullYear();
let rescheduleApptId = null;

function openPatientRescheduleModal(apptId, oldFecha, oldHora) {
    rescheduleApptId = apptId;
    document.getElementById('resched-req-fecha').value = '';
    document.getElementById('resched-req-hora').value = '';
    document.getElementById('resched-submit-btn').disabled = true;
    document.getElementById('resched-hours-container').classList.add('hide');
    
    // Inicializar mes y año con la fecha actual o de la cita a reprogramar
    const today = new Date();
    reschedMonth = today.getMonth();
    reschedYear = today.getFullYear();
    
    const modal = document.getElementById('reschedule-modal');
    if (modal) modal.classList.remove('hide');
    renderRescheduleCalendar();
}

function closeRescheduleModal() {
    const modal = document.getElementById('reschedule-modal');
    if (modal) modal.classList.add('hide');
}

function changeRescheduleMonth(offset) {
    reschedMonth += offset;
    if (reschedMonth < 0) {
        reschedMonth = 11;
        reschedYear--;
    } else if (reschedMonth > 11) {
        reschedMonth = 0;
        reschedYear++;
    }
    renderRescheduleCalendar();
}

async function renderRescheduleCalendar() {
    const headerTitle = document.getElementById('resched-cal-month-year');
    if (!headerTitle) return;
    
    headerTitle.textContent = `${monthNames[reschedMonth]} ${reschedYear}`;
    
    const grid = document.getElementById('resched-cal-days-grid');
    grid.innerHTML = '<div style="grid-column: span 7; text-align: center; padding: 1rem;"><span class="text-secondary text-xs">Cargando disponibilidad...</span></div>';
    
    let availableDates = [];
    try {
        const monthForApi = reschedMonth + 1;
        const res = await fetch(`/api/patient/available-dates?year=${reschedYear}&month=${monthForApi}&modalidad=all&exclude_appt_id=${rescheduleApptId || ''}`);
        if (res.ok) {
            const data = await res.json();
            availableDates = data.dates || [];
        }
    } catch (e) {
        console.error("Error al obtener fechas disponibles:", e);
    }
    
    grid.innerHTML = '';
    
    const firstDay = new Date(reschedYear, reschedMonth, 1).getDay();
    const totalDays = new Date(reschedYear, reschedMonth + 1, 0).getDate();
    
    for (let i = 0; i < firstDay; i++) {
        const spacer = document.createElement('div');
        grid.appendChild(spacer);
    }
    
    const today = new Date();
    today.setHours(0,0,0,0);
    
    for (let day = 1; day <= totalDays; day++) {
        const cell = document.createElement('div');
        cell.className = 'pat-cal-day-cell';
        cell.textContent = day;
        
        const cellMonthStr = String(reschedMonth + 1).padStart(2, '0');
        const cellDayStr = String(day).padStart(2, '0');
        const dateStr = `${reschedYear}-${cellMonthStr}-${cellDayStr}`;
        
        const cellDate = new Date(reschedYear, reschedMonth, day);
        cellDate.setHours(0,0,0,0);
        
        const isPast = cellDate < today;
        const isAvailable = availableDates.includes(dateStr);
        
        if (isPast || !isAvailable) {
            cell.classList.add('disabled');
            cell.style.color = '#ccc';
            cell.style.cursor = 'not-allowed';
            cell.style.display = 'inline-flex';
            cell.style.alignItems = 'center';
            cell.style.justifyContent = 'center';
            cell.style.margin = 'auto';
            cell.style.width = '32px';
            cell.style.height = '32px';
        } else {
            cell.classList.add('available');
            cell.style.cursor = 'pointer';
            cell.style.display = 'inline-flex';
            cell.style.alignItems = 'center';
            cell.style.justifyContent = 'center';
            cell.style.margin = 'auto';
            cell.style.width = '32px';
            cell.style.height = '32px';
            cell.style.borderRadius = '50%';
            cell.style.border = '2px solid #10b981';
            cell.style.fontWeight = '700';
            cell.style.color = '#047857';
            cell.style.backgroundColor = '#ecfdf5';
            
            cell.onclick = () => {
                document.querySelectorAll('#resched-cal-days-grid .pat-cal-day-cell.selected').forEach(c => {
                    c.classList.remove('selected');
                    c.style.backgroundColor = '#ecfdf5';
                    c.style.color = '#047857';
                });
                
                cell.classList.add('selected');
                cell.style.backgroundColor = '#10b981';
                cell.style.color = 'white';
                
                document.getElementById('resched-req-fecha').value = dateStr;
                document.getElementById('resched-req-hora').value = '';
                document.getElementById('resched-submit-btn').disabled = true;
                
                fetchRescheduleAvailableHours(dateStr);
            };
        }
        grid.appendChild(cell);
    }
}

async function fetchRescheduleAvailableHours(dateStr) {
    const hoursGrid = document.getElementById('resched-hours-grid');
    const hoursContainer = document.getElementById('resched-hours-container');
    
    hoursGrid.innerHTML = '<span class="text-secondary text-xs">Consultando horarios...</span>';
    hoursContainer.classList.remove('hide');
    
    try {
        const res = await fetch(`/api/patient/available-slots?date=${dateStr}&modalidad=all&exclude_appt_id=${rescheduleApptId || ''}`);
        const data = await res.json();
        
        hoursGrid.innerHTML = '';
        const slots = data.slots || [];
        
        const localSlots = [];
        slots.forEach(slotObj => {
            const therapistDate = slotObj.iso.substring(0, 10);
            const therapistHour = slotObj.hora_literal || slotObj.iso.substring(11, 16);

            if (therapistDate === dateStr) {
                localSlots.push({
                    displayTime: therapistHour,
                    valFecha: therapistDate,
                    valHora: therapistHour
                });
            }
        });
        
        localSlots.sort((a, b) => a.displayTime.localeCompare(b.displayTime));
        
        if (localSlots.length === 0) {
            hoursGrid.innerHTML = '<span class="text-secondary text-xs">No hay horarios disponibles para este día.</span>';
            return;
        }
        
        localSlots.forEach(slot => {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'btn btn-secondary btn-sm';
            btn.style.padding = '0.4rem 0.75rem';
            btn.style.fontSize = '0.85rem';
            btn.style.fontWeight = '600';
            btn.style.cursor = 'pointer';
            btn.style.border = '1.5px solid var(--border-color)';
            btn.style.borderRadius = 'var(--radius-sm)';
            btn.style.background = 'white';
            btn.style.color = 'var(--text-dark)';
            btn.textContent = format12h(slot.displayTime);
            
            btn.onclick = () => {
                document.querySelectorAll('#resched-hours-grid button').forEach(b => {
                    b.style.backgroundColor = 'white';
                    b.style.color = 'var(--text-dark)';
                    b.style.borderColor = 'var(--border-color)';
                });
                btn.style.backgroundColor = 'var(--primary-color)';
                btn.style.color = 'white';
                btn.style.borderColor = 'var(--primary-color)';
                
                document.getElementById('resched-req-hora').value = slot.valHora;
                document.getElementById('resched-req-fecha').value = slot.valFecha;
                document.getElementById('resched-submit-btn').disabled = false;
            };
            hoursGrid.appendChild(btn);
        });
    } catch (err) {
        console.error("Error al obtener horarios para reprogramar:", err);
        hoursGrid.innerHTML = '<span class="text-danger text-xs">Error al cargar horarios.</span>';
    }
}

async function submitRescheduleAppointment() {
    const fecha = document.getElementById('resched-req-fecha').value;
    const hora = document.getElementById('resched-req-hora').value;
    
    if (!fecha || !hora) {
        alert("Por favor, selecciona una fecha y una hora.");
        return;
    }
    
    try {
        const res = await fetch('/api/patient/reschedule-appointment', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ appt_id: rescheduleApptId, fecha, hora })
        });
        const data = await res.json();
        
        if (data.error) {
            alert(data.error);
        } else {
            alert(data.success || 'Cita reprogramada con éxito.');
            closeRescheduleModal();
            const patientId = sessionStorage.getItem('patient_id');
            if (patientId) loadPatientPortalData(patientId);
            if (typeof loadAgenda === 'function') loadAgenda();
            if (typeof loadDashboardStats === 'function') loadDashboardStats();
            if (typeof loadAgendaCompact === 'function') loadAgendaCompact();
        }
    } catch (err) {
        console.error("Error al reprogramar cita:", err);
        alert("Error de conexión al intentar reprogramar la cita.");
    }
}

function refreshPatientPortal() {
    const patientId = sessionStorage.getItem('patient_id');
    if (patientId) {
        loadPatientPortalData(patientId);
    }
}

async function loadModalityDropdownOptions() {
    const select = document.getElementById('e-tipo');
    if (!select) return;
    try {
        const res = await fetch('/api/admin/availability');
        if (res.ok) {
            const data = await res.json();
            const perfiles = data.perfiles || [];
            if (perfiles.length > 0) {
                const currentVal = select.value;
                select.innerHTML = '';
                perfiles.forEach(p => {
                    const opt = document.createElement('option');
                    opt.value = p.nombre;
                    opt.textContent = p.nombre;
                    select.appendChild(opt);
                });
                const hasMatch = Array.from(select.options).some(opt => opt.value === currentVal);
                if (hasMatch) {
                    select.value = currentVal;
                }
            }
        }
    } catch (err) {
        console.error("Error al cargar modalidades dinámicas para el administrador:", err);
    }
}

function togglePatientPkgInputs() {
    const checked = document.getElementById('p-ofrecer-paquete-personalizado').checked;
    document.querySelectorAll('.p-pkg-inputs').forEach(el => {
        if (checked) {
            el.classList.remove('hide');
        } else {
            el.classList.add('hide');
        }
    });
}

window.handleResourceFileSelected = function() {
    const fileInput = document.getElementById('s-recursos-file');
    const nameSpan = document.getElementById('s-recursos-file-name');
    if (fileInput && fileInput.files.length > 0) {
        nameSpan.textContent = `Seleccionado: ${fileInput.files[0].name}`;
    } else {
        nameSpan.textContent = '';
    }
};

window.editPatientRates = async function(patientId) {
    closeModal('summary-modal');
    await openEditPatientModal(patientId);
    switchFormTab(null, 'tab-personal');
    setTimeout(() => {
        const el = document.getElementById('p-costo-personalizado');
        if (el) {
            el.focus();
            el.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
    }, 300);
};

window.resetTestData = async function() {
    if (!confirm("¿Está seguro de restablecer todos los datos de pruebas? Esto vaciará permanentemente todas las consultas agendadas, evoluciones y pagos, dejando solo a los pacientes Leo y Eulogio con saldo en cero.")) {
        return;
    }
    try {
        const res = await fetch('/api/admin/reset-test-data', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        const data = await res.json();
        if (res.ok) {
            alert(data.success);
            window.location.reload();
        } else {
            alert(data.error || "Error al restablecer los datos de prueba.");
        }
    } catch (err) {
        console.error("Error al resetear datos:", err);
        alert("Error de conexión al restablecer datos.");
    }
};

// ==========================================
// TABLA SIMPLIFICADA DE HONORARIOS POR PACIENTE
// ==========================================

const MONEDAS_DISPONIBLES = ['USD', 'EUR', 'BSD', 'ARS', 'COP', 'CLP', 'MXN', 'DOP', 'PEN', 'UYU', 'VES'];

let allPatientRatesData = [];

async function loadPatientRatesTable() {
    const tbody = document.getElementById('patient-rates-table-body');
    if (!tbody) return;
    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:1.5rem;color:var(--text-muted);">Cargando pacientes...</td></tr>';
    try {
        const res = await fetch('/api/admin/patients-rates-list');
        const patients = await res.json();
        allPatientRatesData = Array.isArray(patients) ? patients : [];
        renderPatientRatesTable();
    } catch (err) {
        console.error('Error loading patient rates:', err);
        tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--danger);">Error al cargar pacientes.</td></tr>';
    }
}

function filterPatientRatesTable() {
    renderPatientRatesTable();
}

function renderPatientRatesTable() {
    const tbody = document.getElementById('patient-rates-table-body');
    if (!tbody) return;
    
    const searchInput = document.getElementById('patient-rates-search');
    const query = searchInput ? searchInput.value.trim().toLowerCase() : '';
    
    if (!Array.isArray(allPatientRatesData) || allPatientRatesData.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:1.5rem;color:var(--text-muted);">No hay pacientes registrados.</td></tr>';
        return;
    }

    const filtered = allPatientRatesData.filter(p => {
        if (!query) return true;
        const nombreCompleto = `${p.nombres || ''} ${p.apellidos || ''}`.toLowerCase();
        const cedula = (p.cedula || '').toLowerCase();
        return nombreCompleto.includes(query) || cedula.includes(query);
    });

    if (filtered.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:1.5rem;color:var(--text-muted);">No se encontraron pacientes que coincidan con la búsqueda.</td></tr>';
        return;
    }

    tbody.innerHTML = filtered.map(p => {
        const monedasOptions = MONEDAS_DISPONIBLES.map(m => `<option value="${m}" ${m === (p.moneda_personalizada || 'USD') ? 'selected' : ''}>${m}</option>`).join('');
        const costoIndStr = p.costo_personalizado != null ? Number(p.costo_personalizado).toFixed(2) : '—';
        const costoPaqStr = p.costo_paquete_personalizado != null ? Number(p.costo_paquete_personalizado).toFixed(2) : '—';
        const sesionesStr = p.sesiones_paquete_personalizado != null ? p.sesiones_paquete_personalizado : '—';
        const cedulaStr = p.cedula ? `<span style="display:block; font-size:0.75rem; color:var(--text-muted); font-weight:normal;">C.I: ${p.cedula}</span>` : '';
        return `
        <tr id="prt-row-${p.id}" style="border-bottom: 1px solid var(--border-color);">
            <td style="padding: 0.65rem 0.75rem; font-weight: 600;">
                ${p.nombres || ''} ${p.apellidos || ''}
                ${cedulaStr}
            </td>
            <td style="padding: 0.65rem 0.75rem; text-align: right;">
                <span class="prt-view-${p.id}">${costoIndStr}</span>
                <input class="prt-edit-${p.id} hide prt-costo-ind-${p.id}" type="number" min="0" step="0.01" value="${p.costo_personalizado || ''}" style="width: 100px; padding: 0.3rem; border: 1.5px solid var(--border-color); border-radius: 4px; text-align: right;">
            </td>
            <td style="padding: 0.65rem 0.75rem; text-align: right;">
                <span class="prt-view-${p.id}">${costoPaqStr}</span>
                <input class="prt-edit-${p.id} hide prt-costo-paq-${p.id}" type="number" min="0" step="0.01" value="${p.costo_paquete_personalizado || ''}" style="width: 100px; padding: 0.3rem; border: 1.5px solid var(--border-color); border-radius: 4px; text-align: right;">
            </td>
            <td style="padding: 0.65rem 0.75rem; text-align: center;">
                <span class="prt-view-${p.id}">${sesionesStr}</span>
                <input class="prt-edit-${p.id} hide prt-sesiones-${p.id}" type="number" min="1" step="1" value="${p.sesiones_paquete_personalizado || ''}" style="width: 70px; padding: 0.3rem; border: 1.5px solid var(--border-color); border-radius: 4px; text-align: center;">
            </td>
            <td style="padding: 0.65rem 0.75rem; text-align: center;">
                <span class="prt-view-${p.id}" style="font-weight: 700;">${p.moneda_personalizada || '—'}</span>
                <select class="prt-edit-${p.id} hide prt-moneda-${p.id}" style="padding: 0.3rem; border: 1.5px solid var(--border-color); border-radius: 4px;">${monedasOptions}</select>
            </td>
            <td style="padding: 0.65rem 0.75rem; text-align: center; white-space: nowrap;">
                <button id="prt-btn-edit-${p.id}" class="btn btn-sm" style="background: var(--primary-light, #f3e8ff); color: var(--primary-color); border: none; padding: 0.3rem 0.7rem; border-radius: 4px; cursor: pointer; margin-right: 0.25rem; font-size: 0.8rem;" onclick="enablePatientRateEdit(${p.id})">✏️ Editar</button>
                <button id="prt-btn-save-${p.id}" class="btn btn-sm hide" style="background: #d1fae5; color: #065f46; border: none; padding: 0.3rem 0.7rem; border-radius: 4px; cursor: pointer; font-size: 0.8rem;" onclick="savePatientRateQuick(${p.id})">💾 Guardar</button>
            </td>
        </tr>`;
    }).join('');
}

function enablePatientRateEdit(patientId) {
    document.querySelectorAll(`.prt-view-${patientId}`).forEach(el => el.classList.add('hide'));
    document.querySelectorAll(`.prt-edit-${patientId}`).forEach(el => el.classList.remove('hide'));
    document.getElementById(`prt-btn-edit-${patientId}`)?.classList.add('hide');
    document.getElementById(`prt-btn-save-${patientId}`)?.classList.remove('hide');
}

async function savePatientRateQuick(patientId) {
    const costoIndEl = document.querySelector(`.prt-costo-ind-${patientId}`);
    const costoPaqEl = document.querySelector(`.prt-costo-paq-${patientId}`);
    const sesionesEl = document.querySelector(`.prt-sesiones-${patientId}`);
    const monedaEl = document.querySelector(`.prt-moneda-${patientId}`);

    const costoInd = costoIndEl && costoIndEl.value !== '' ? parseFloat(costoIndEl.value) : null;
    const costoPaq = costoPaqEl && costoPaqEl.value !== '' ? parseFloat(costoPaqEl.value) : null;
    const sesiones = sesionesEl && sesionesEl.value !== '' ? parseInt(sesionesEl.value) : null;
    const moneda = monedaEl ? monedaEl.value : 'USD';

    const statusEl = document.getElementById('patient-rates-status');

    try {
        const res = await fetch(`/api/admin/patients/${patientId}/rates`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                costo_personalizado: costoInd,
                costo_paquete_personalizado: costoPaq,
                sesiones_paquete_personalizado: sesiones,
                moneda_personalizada: moneda
            })
        });
        const data = await res.json();
        if (res.ok) {
            if (statusEl) {
                statusEl.textContent = '✅ Honorarios actualizados con éxito.';
                statusEl.className = 'status-msg success-msg';
                statusEl.classList.remove('hide');
                setTimeout(() => statusEl.classList.add('hide'), 3000);
            }
            loadPatientRatesTable();
        } else {
            alert(data.error || 'Error al guardar honorarios.');
        }
    } catch (err) {
        alert('Error de conexión al guardar honorarios.');
    }
}

window.enablePatientRateEdit = enablePatientRateEdit;
window.savePatientRateQuick = savePatientRateQuick;

async function deleteSessionAttachment(sessionId) {
    if (!confirm("¿Estás seguro de que deseas eliminar permanentemente este archivo adjunto de la evolución?")) return;
    try {
        const res = await fetch(`/api/sessions/${sessionId}/remove-attachment`, { method: 'POST' });
        const data = await res.json();
        if (res.ok) {
            alert(data.success || "Archivo eliminado con éxito.");
            if (typeof loadSessionsTimeline === 'function') loadSessionsTimeline();
        } else {
            alert(data.error || "Error al eliminar el archivo.");
        }
    } catch (err) {
        alert("Error de conexión al eliminar archivo.");
    }
}
window.deleteSessionAttachment = deleteSessionAttachment;

function deletePatientFromModal() {
    const patientId = document.getElementById('patient-form-id').value;
    if (patientId) {
        closeModal('patient-modal');
        deletePatient(patientId);
    } else {
        alert("No hay ningún paciente seleccionado para eliminar.");
    }
}
window.deletePatientFromModal = deletePatientFromModal;

function selectPatientDebtToPay(debtId) {
    if (!debtId || !window.patientActiveDebts) return;
    const debt = window.patientActiveDebts.find(d => String(d.id) === String(debtId));
    if (!debt) return;
    
    const montoEl = document.getElementById('pat-pay-monto');
    const monedaEl = document.getElementById('pat-pay-moneda');
    const refEl = document.getElementById('pat-pay-referencia');
    
    if (montoEl) montoEl.value = Number(debt.monto || 0).toFixed(2);
    if (monedaEl && debt.moneda) monedaEl.value = debt.moneda;
    if (refEl && !refEl.value) {
        refEl.placeholder = `Pago cita del ${debt.fecha} (${debt.tipo_consulta})`;
    }
}
window.selectPatientDebtToPay = selectPatientDebtToPay;

function renderPatientDebtCheckboxes() {
    const container = document.getElementById('pat-pay-debt-checkboxes');
    if (!container) return;
    
    const debts = window.patientActiveDebts || [];
    container.innerHTML = '';
    
    if (debts.length === 0) {
        container.innerHTML = '<p style="font-size: 0.8rem; color: #777; margin: 0;">No tienes deudas ni cargos pendientes registradas.</p>';
        return;
    }
    
    debts.forEach(d => {
        const itemDiv = document.createElement('div');
        itemDiv.style.cssText = 'display: flex; align-items: center; justify-content: space-between; background: white; padding: 0.45rem 0.65rem; border-radius: 6px; border: 1px solid var(--border-color); font-size: 0.82rem;';
        
        const isLate = d.estado_pago === 'Cancelada sin aviso';
        const stText = isLate ? '⚠️ Cancelación Tardía' : 'Consulta Pendiente';
        const stColor = isLate ? '#dc2626' : '#92400e';
        
        itemDiv.innerHTML = `
            <label style="display: flex; align-items: center; gap: 0.5rem; cursor: pointer; width: 100%; margin: 0;">
                <input type="checkbox" class="pat-debt-chk" data-id="${d.id}" data-monto="${d.monto || 0}" data-moneda="${d.moneda || 'USD'}" data-fecha="${d.fecha}" checked onchange="recalculateSelectedDebtsTotal()">
                <div>
                    <strong>Cita del ${d.fecha}</strong> (${d.tipo_consulta || 'Online'})
                    <span style="display: block; font-size: 0.75rem; color: ${stColor}; font-weight: 700;">${stText} — ${Number(d.monto || 0).toFixed(2)} ${d.moneda || 'USD'}</span>
                </div>
            </label>
        `;
        container.appendChild(itemDiv);
    });
    
    recalculateSelectedDebtsTotal();
}

function recalculateSelectedDebtsTotal() {
    const checkboxes = document.querySelectorAll('.pat-debt-chk:checked');
    let total = 0;
    let currency = 'USD';
    const dates = [];
    
    checkboxes.forEach(chk => {
        total += parseFloat(chk.getAttribute('data-monto') || 0);
        currency = chk.getAttribute('data-moneda') || 'USD';
        dates.push(chk.getAttribute('data-fecha'));
    });
    
    const montoEl = document.getElementById('pat-pay-monto');
    const monedaEl = document.getElementById('pat-pay-moneda');
    const refEl = document.getElementById('pat-pay-referencia');
    
    if (montoEl) montoEl.value = total.toFixed(2);
    if (monedaEl && currency) monedaEl.value = currency;
    if (refEl) {
        if (dates.length > 0) {
            refEl.placeholder = `Pago de ${dates.length} consulta(s) [${dates.slice(0, 2).join(', ')}${dates.length > 2 ? '...' : ''}]`;
        } else {
            refEl.placeholder = 'Selecciona al menos una consulta para pagar';
        }
    }
}
window.renderPatientDebtCheckboxes = renderPatientDebtCheckboxes;
window.recalculateSelectedDebtsTotal = recalculateSelectedDebtsTotal;

function handlePatientPaymentConceptChange(concept) {
    const debtContainer = document.getElementById('pat-pay-debt-select-container');
    const montoEl = document.getElementById('pat-pay-monto');
    const monedaEl = document.getElementById('pat-pay-moneda');
    const refEl = document.getElementById('pat-pay-referencia');
    const profile = window.patientProfile || {};
    
    if (concept === 'deuda') {
        if (window.patientActiveDebts && window.patientActiveDebts.length > 0) {
            if (debtContainer) debtContainer.classList.remove('hide');
            renderPatientDebtCheckboxes();
        } else {
            if (debtContainer) debtContainer.classList.add('hide');
            if (montoEl) montoEl.value = '0.00';
            if (refEl) refEl.placeholder = 'Sin deudas pendientes';
            alert("Actualmente no tienes deudas pendientes por liquidar. Puedes seleccionar 'Pagar Consulta Individual' o 'Comprar Paquete Prepagado'.");
        }
    } else if (concept === 'consulta') {
        if (debtContainer) debtContainer.classList.add('hide');
        const costVal = (profile.costo_personalizado !== null && profile.costo_personalizado !== undefined && profile.costo_personalizado !== '') 
            ? Number(profile.costo_personalizado).toFixed(2) 
            : '0.00';
        if (montoEl) montoEl.value = costVal;
        if (monedaEl && profile.moneda_personalizada) monedaEl.value = profile.moneda_personalizada;
        if (refEl) refEl.placeholder = 'Pago de consulta individual';
    } else if (concept === 'paquete') {
        if (debtContainer) debtContainer.classList.add('hide');
        const pkgVal = (profile.costo_paquete_personalizado !== null && profile.costo_paquete_personalizado !== undefined && profile.costo_paquete_personalizado !== '') 
            ? Number(profile.costo_paquete_personalizado).toFixed(2) 
            : '0.00';
        const pkgCount = profile.sesiones_paquete_personalizado || 1;
        if (montoEl) montoEl.value = pkgVal;
        if (monedaEl && profile.moneda_personalizada) monedaEl.value = profile.moneda_personalizada;
        if (refEl) refEl.placeholder = `Pago de paquete prepagado (${pkgCount} consultas)`;
    }
}
window.handlePatientPaymentConceptChange = handlePatientPaymentConceptChange;

// ================================================================
// QUICK PAY MODAL — Registrar Pago Rápido (Psicólogo)
// Mismo flujo que el paciente notifica, pero desde el panel del psicólogo
// ================================================================

let _qpPatients = [];
let _qpCurrentProfile = null;

async function openQuickPayModal() {
    const modal = document.getElementById('quick-pay-modal');
    if (!modal) return;

    // Reset
    document.getElementById('qp-paciente').value = '';
    document.getElementById('qp-concepto').value = '';
    document.getElementById('qp-debt-info').classList.add('hide');
    document.getElementById('qp-package-info').classList.add('hide');
    document.getElementById('qp-payment-fields').classList.add('hide');
    document.getElementById('qp-footer').style.display = 'none';
    document.getElementById('qp-status-msg').classList.add('hide');
    document.getElementById('qp-fecha').value = new Date().toISOString().split('T')[0];
    _qpCurrentProfile = null;

    // Cargar lista de pacientes
    try {
        const res = await fetch('/api/patients');
        const data = await res.json();
        _qpPatients = Array.isArray(data) ? data : [];
        const sel = document.getElementById('qp-paciente');
        sel.innerHTML = '<option value="">— Selecciona un consultante —</option>';
        _qpPatients.forEach(p => {
            const opt = document.createElement('option');
            opt.value = p.id;
            opt.textContent = `${p.nombres} ${p.apellidos}`;
            sel.appendChild(opt);
        });
    } catch(e) {
        console.error('Error cargando pacientes:', e);
    }

    modal.classList.remove('hide');
}
window.openQuickPayModal = openQuickPayModal;

function closeQuickPayModal() {
    const modal = document.getElementById('quick-pay-modal');
    if (modal) modal.classList.add('hide');
}
window.closeQuickPayModal = closeQuickPayModal;

async function handleQuickPayPatientChange(patientId) {
    document.getElementById('qp-concepto').value = '';
    document.getElementById('qp-debt-info').classList.add('hide');
    document.getElementById('qp-package-info').classList.add('hide');
    document.getElementById('qp-payment-fields').classList.add('hide');
    document.getElementById('qp-footer').style.display = 'none';
    _qpCurrentProfile = null;

    if (!patientId) return;

    try {
        const res = await fetch(`/api/patient-profile/${patientId}`);
        if (res.ok) {
            _qpCurrentProfile = await res.json();
            const monedaEl = document.getElementById('qp-moneda');
            if (monedaEl && _qpCurrentProfile && _qpCurrentProfile.moneda_personalizada) {
                monedaEl.value = _qpCurrentProfile.moneda_personalizada;
            }
        }
    } catch(e) { console.warn('No se pudo cargar perfil del paciente'); }
}
window.handleQuickPayPatientChange = handleQuickPayPatientChange;

async function handleQuickPayConceptChange(concept) {
    const debtInfo    = document.getElementById('qp-debt-info');
    const pkgInfo     = document.getElementById('qp-package-info');
    const fields      = document.getElementById('qp-payment-fields');
    const footer      = document.getElementById('qp-footer');
    const montoEl     = document.getElementById('qp-monto');
    const monedaEl    = document.getElementById('qp-moneda');
    const debtList    = document.getElementById('qp-debt-list');
    const pkgDesc     = document.getElementById('qp-package-desc');

    debtInfo.classList.add('hide');
    pkgInfo.classList.add('hide');
    fields.classList.add('hide');
    footer.style.display = 'none';

    if (!concept) return;

    const patientId = document.getElementById('qp-paciente').value;
    if (!patientId) {
        alert('Primero selecciona un consultante.');
        document.getElementById('qp-concepto').value = '';
        return;
    }

    const profile = _qpCurrentProfile;

    if (concept === 'deuda') {
        // Cargar deudas pendientes
        try {
            const res = await fetch(`/api/patient-debts/${patientId}`);
            if (res.ok) {
                const debts = await res.json();
                if (debts.length > 0) {
                    debtList.innerHTML = debts.map(d =>
                        `<label style="display:flex;align-items:center;gap:0.5rem;cursor:pointer;background:white;padding:0.4rem 0.6rem;border-radius:6px;border:1px solid var(--border-color);font-size:0.82rem;margin-bottom:0.35rem;">
                            <input type="checkbox" class="qp-debt-chk" value="${d.id}" data-monto="${d.monto}" data-moneda="${d.moneda}" checked onchange="updateQuickPayDebtTotal()" style="accent-color:var(--primary-color);">
                            <span>${d.fecha} — <strong>${Number(d.monto || 0).toFixed(2)} ${d.moneda || 'USD'}</strong> (${d.tipo_consulta || 'Deuda'})</span>
                        </label>`
                    ).join('');
                    updateQuickPayDebtTotal();
                } else {
                    debtList.innerHTML = '<span style="color:var(--text-muted);">No hay deudas pendientes.</span>';
                    if (montoEl) montoEl.value = '0.00';
                }
                debtInfo.classList.remove('hide');
            }
        } catch(e) { console.warn('Error cargando deudas'); }

    } else if (concept === 'consulta') {
        if (profile && profile.costo_personalizado != null) {
            if (montoEl) montoEl.value = Number(profile.costo_personalizado).toFixed(2);
            if (monedaEl && profile.moneda_personalizada) monedaEl.value = profile.moneda_personalizada;
        }
    } else if (concept === 'paquete') {
        if (profile) {
            const pkgMonto = profile.costo_paquete_personalizado != null ? Number(profile.costo_paquete_personalizado).toFixed(2) : '—';
            const pkgCount = profile.sesiones_paquete_personalizado || '?';
            pkgDesc.textContent = `${pkgCount} consultas por ${pkgMonto} ${profile.moneda_personalizada || 'USD'}`;
            if (montoEl && profile.costo_paquete_personalizado != null) montoEl.value = pkgMonto;
            if (monedaEl && profile.moneda_personalizada) monedaEl.value = profile.moneda_personalizada;
            pkgInfo.classList.remove('hide');
        }
    }

    fields.classList.remove('hide');
    footer.style.display = 'flex';
}
window.handleQuickPayConceptChange = handleQuickPayConceptChange;

function updateQuickPayDebtTotal() {
    const checkboxes = document.querySelectorAll('.qp-debt-chk:checked');
    let total = 0;
    let currency = 'USD';
    checkboxes.forEach(chk => {
        total += parseFloat(chk.getAttribute('data-monto') || 0);
        currency = chk.getAttribute('data-moneda') || 'USD';
    });
    const montoEl = document.getElementById('qp-monto');
    const monedaEl = document.getElementById('qp-moneda');
    if (montoEl) montoEl.value = total.toFixed(2);
    if (monedaEl && currency) monedaEl.value = currency;
}
window.updateQuickPayDebtTotal = updateQuickPayDebtTotal;

// Helper para mostrar mensajes dentro del modal de pago rápido
function showQuickPayStatus(type, msg) {
    const msgEl = document.getElementById('qp-status-msg');
    if (!msgEl) return;
    msgEl.classList.remove('hide', 'success-msg', 'error-msg');
    msgEl.classList.add(type === 'success' ? 'success-msg' : 'error-msg');
    msgEl.textContent = msg;
    msgEl.style.display = 'block';
    msgEl.style.padding = '0.5rem 0.75rem';
    msgEl.style.borderRadius = 'var(--radius-sm)';
    msgEl.style.marginTop = '0.75rem';
    msgEl.style.fontSize = '0.85rem';
    msgEl.style.fontWeight = '600';
    if (type === 'success') {
        msgEl.style.background = 'rgba(16, 185, 129, 0.1)';
        msgEl.style.color = '#059669';
        msgEl.style.border = '1px solid rgba(16, 185, 129, 0.3)';
    } else {
        msgEl.style.background = 'rgba(239, 68, 68, 0.1)';
        msgEl.style.color = '#dc2626';
        msgEl.style.border = '1px solid rgba(239, 68, 68, 0.3)';
    }
}

async function submitQuickPay() {
    const patientId  = document.getElementById('qp-paciente').value;
    const concept    = document.getElementById('qp-concepto').value;
    const montoVal   = parseFloat(document.getElementById('qp-monto').value || 0);
    const moneda     = document.getElementById('qp-moneda').value;
    const metodo     = document.getElementById('qp-metodo').value;
    const referencia = document.getElementById('qp-referencia').value;
    const fecha      = document.getElementById('qp-fecha').value;
    const submitBtn  = document.getElementById('qp-submit-btn');

    if (!patientId || !concept || !montoVal || !fecha) {
        showQuickPayStatus('error', 'Por favor completa todos los campos requeridos (Paciente, Concepto, Monto y Fecha).');
        return;
    }

    // Manejo del pago de deudas existentes
    if (concept === 'deuda') {
        const checks = document.querySelectorAll('#qp-debt-list input[type=checkbox]:checked');
        if (checks.length === 0) {
            showQuickPayStatus('error', 'Selecciona al menos una consulta pendiente a pagar.');
            return;
        }
        const debtIds = Array.from(checks).map(c => c.value);
        try {
            submitBtn.disabled = true;
            submitBtn.textContent = 'Procesando...';
            const res = await fetch('/api/mark-debts-paid', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ debt_ids: debtIds, metodo_pago: metodo, referencia, fecha_pago: fecha })
            });
            const data = await res.json();
            if (data.success) {
                showQuickPayStatus('success', '¡Consultas marcadas como pagadas correctamente!');
                setTimeout(() => {
                    closeQuickPayModal();
                    if (typeof loadFinanceData === 'function') loadFinanceData();
                    if (typeof loadDashboardStats === 'function') loadDashboardStats();
                }, 1500);
            } else {
                showQuickPayStatus('error', data.error || 'Error al registrar el pago.');
            }
        } catch(e) {
            showQuickPayStatus('error', 'Error de conexión al servidor.');
        } finally {
            submitBtn.disabled = false;
            submitBtn.textContent = 'Confirmar Pago';
        }
        return;
    }

    // Calcular costo esperado para detectar pago fraccionado (parcial)
    let cantidadSesiones = 1;
    let tipoConsulta = 'Individual';
    let estadoPago = 'Paga';
    let costoEsperado = 0;

    if (concept === 'paquete') {
        cantidadSesiones = (_qpCurrentProfile && _qpCurrentProfile.sesiones_paquete_personalizado) || 1;
        costoEsperado = (_qpCurrentProfile && _qpCurrentProfile.costo_paquete_personalizado != null) 
            ? parseFloat(_qpCurrentProfile.costo_paquete_personalizado) 
            : 0;
        tipoConsulta = 'Paquete Prepagado';
        estadoPago = 'Prepagada';
    } else if (concept === 'consulta') {
        costoEsperado = (_qpCurrentProfile && _qpCurrentProfile.costo_personalizado != null)
            ? parseFloat(_qpCurrentProfile.costo_personalizado)
            : 0;
        tipoConsulta = 'Individual';
        estadoPago = 'Paga';
    }

    // Cálculo de pago fraccionado (deuda por diferencia)
    let deudaGenerada = 0;
    if (costoEsperado > 0 && montoVal < costoEsperado) {
        deudaGenerada = costoEsperado - montoVal;
    }

    const payload = {
        paciente_id: patientId,
        fecha: fecha,
        hora: '00:00',
        tipo_consulta: tipoConsulta,
        monto: montoVal,
        moneda: moneda,
        estado_pago: estadoPago,
        cantidad_sesiones: cantidadSesiones,
        referencia: referencia,
        metodo_pago: metodo,
        fecha_pago: fecha,
        confirmada: 1,
        deuda_generada: deudaGenerada
    };

    try {
        submitBtn.disabled = true;
        submitBtn.textContent = 'Procesando...';
        const res = await fetch('/api/agenda/quick-pay', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (data.success) {
            let msg = '¡Pago registrado con éxito!';
            if (deudaGenerada > 0) {
                msg += ` (Pago parcial registrado. Se generó una deuda pendiente de ${deudaGenerada.toFixed(2)} ${moneda})`;
            }
            showQuickPayStatus('success', msg);
            setTimeout(() => {
                closeQuickPayModal();
                if (typeof loadFinanceData === 'function') loadFinanceData();
                if (typeof loadDashboardStats === 'function') loadDashboardStats();
            }, 2000);
        } else {
            showQuickPayStatus('error', data.error || 'Error al registrar el pago.');
        }
    } catch(e) {
        showQuickPayStatus('error', 'Error de conexión al servidor.');
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = 'Confirmar Pago';
    }
}
window.submitQuickPay = submitQuickPay;

// ==========================================
// BORRAR TODOS LOS DATOS (ZONA DE PELIGRO)
// ==========================================
function openClearDataModal() {
    const modal = document.getElementById('modal-clear-data');
    const input = document.getElementById('clear-data-confirm-input');
    const btn = document.getElementById('btn-submit-clear-data');
    const msg = document.getElementById('clear-data-status-msg');
    
    if (!modal) return;
    if (input) input.value = '';
    if (btn) {
        btn.disabled = true;
        btn.style.opacity = '0.5';
        btn.style.cursor = 'not-allowed';
    }
    if (msg) msg.classList.add('hide');
    modal.classList.remove('hide');
}

function closeClearDataModal() {
    const modal = document.getElementById('modal-clear-data');
    if (modal) modal.classList.add('hide');
}

function checkClearDataInput() {
    const input = document.getElementById('clear-data-confirm-input');
    const btn = document.getElementById('btn-submit-clear-data');
    if (!input || !btn) return;
    
    const val = input.value.trim().toUpperCase();
    if (val === 'CONFIRMAR') {
        btn.disabled = false;
        btn.style.opacity = '1';
        btn.style.cursor = 'pointer';
    } else {
        btn.disabled = true;
        btn.style.opacity = '0.5';
        btn.style.cursor = 'not-allowed';
    }
}

async function submitClearAllData() {
    const input = document.getElementById('clear-data-confirm-input');
    const btn = document.getElementById('btn-submit-clear-data');
    const msg = document.getElementById('clear-data-status-msg');
    
    if (!input || input.value.trim().toUpperCase() !== 'CONFIRMAR') return;
    
    try {
        btn.disabled = true;
        btn.textContent = 'Borrando datos...';
        
        const res = await fetch('/api/admin/clear-all-data', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ confirmation: 'CONFIRMAR' })
        });
        
        const data = await res.json();
        if (res.ok && data.success) {
            if (msg) {
                msg.className = 'status-msg success-msg mt-2';
                msg.textContent = '¡Todos los datos han sido borrados con éxito!';
                msg.classList.remove('hide');
            }
            setTimeout(() => {
                closeClearDataModal();
                loadDashboardStats();
                loadPatients();
                if (typeof loadFinanceData === 'function') loadFinanceData();
            }, 1800);
        } else {
            if (msg) {
                msg.className = 'status-msg error-msg mt-2';
                msg.textContent = data.error || 'Error al borrar los datos.';
                msg.classList.remove('hide');
            }
        }
    } catch (err) {
        if (msg) {
            msg.className = 'status-msg error-msg mt-2';
            msg.textContent = 'Error de conexión al servidor.';
            msg.classList.remove('hide');
        }
    } finally {
        btn.disabled = false;
        btn.textContent = '🗑️ Borrar Todos los Datos Definitivamente';
    }
}

window.openClearDataModal = openClearDataModal;
window.closeClearDataModal = closeClearDataModal;
window.checkClearDataInput = checkClearDataInput;
window.submitClearAllData = submitClearAllData;

function openNotificationGuideModal() {
    if (typeof openModal === 'function') {
        openModal('notification-guide-modal');
    } else {
        const modal = document.getElementById('notification-guide-modal');
        if (modal) {
            modal.classList.remove('hide');
            modal.style.display = 'block';
        }
    }
}
window.openNotificationGuideModal = openNotificationGuideModal;



// --- ONBOARDING WIZARD (ASISTENTE DE CONFIGURACIÓN INICIAL PSICÓLOGO) ---
let currentOnboardingStep = 1;

function openPsychologistOnboardingWizard(userData) {
    const modal = document.getElementById('psychologist-onboarding-modal');
    if (!modal) return;
    
    currentOnboardingStep = 1;
    updateOnboardingUI();
    
    const uName = userData ? (userData.username || '') : '';
    const cleanUser = uName.replace(/[^a-zA-Z0-9]/g, '').toLowerCase();
    
    document.getElementById('ob-nombres').value = userData ? (userData.nombres || uName) : '';
    document.getElementById('ob-apellidos').value = userData ? (userData.apellidos || '') : '';
    document.getElementById('ob-slug').value = cleanUser ? `psic.${cleanUser}` : 'psic.miperfil';
    
    modal.classList.remove('hide');
    modal.style.display = 'flex';
}

function updateOnboardingUI() {
    const totalSteps = 4;
    document.getElementById('onboarding-step-num').textContent = currentOnboardingStep;
    document.getElementById('onboarding-progress-bar').style.width = `${(currentOnboardingStep / totalSteps) * 100}%`;
    
    for (let i = 1; i <= totalSteps; i++) {
        const stepEl = document.getElementById(`ob-step-${i}`);
        if (stepEl) {
            if (i === currentOnboardingStep) {
                stepEl.classList.remove('hide');
            } else {
                stepEl.classList.add('hide');
            }
        }
    }
    
    const prevBtn = document.getElementById('ob-prev-btn');
    const nextBtn = document.getElementById('ob-next-btn');
    const submitBtn = document.getElementById('ob-submit-btn');
    
    if (currentOnboardingStep === 1) {
        prevBtn.classList.add('hide');
    } else {
        prevBtn.classList.remove('hide');
    }
    
    if (currentOnboardingStep === totalSteps) {
        nextBtn.classList.add('hide');
        submitBtn.classList.remove('hide');
    } else {
        nextBtn.classList.remove('hide');
        submitBtn.classList.add('hide');
    }
}

function nextOnboardingStep() {
    const errBox = document.getElementById('onboarding-error-msg');
    errBox.classList.add('hide');
    
    if (currentOnboardingStep === 1) {
        const nom = document.getElementById('ob-nombres').value.trim();
        const ape = document.getElementById('ob-apellidos').value.trim();
        if (!nom || !ape) {
            errBox.textContent = 'Por favor ingresa tus Nombres y Apellidos.';
            errBox.classList.remove('hide');
            return;
        }
    } else if (currentOnboardingStep === 2) {
        const slug = document.getElementById('ob-slug').value.trim();
        if (!slug) {
            errBox.textContent = 'Por favor ingresa un enlace único de perfil.';
            errBox.classList.remove('hide');
            return;
        }
    }
    
    if (currentOnboardingStep < 4) {
        currentOnboardingStep++;
        updateOnboardingUI();
    }
}

function prevOnboardingStep() {
    document.getElementById('onboarding-error-msg').classList.add('hide');
    if (currentOnboardingStep > 1) {
        currentOnboardingStep--;
        updateOnboardingUI();
    }
}

async function handleOnboardingSubmit(e) {
    e.preventDefault();
    const errBox = document.getElementById('onboarding-error-msg');
    errBox.classList.add('hide');
    
    const submitBtn = document.getElementById('ob-submit-btn');
    if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.textContent = 'Guardando configuración...';
    }
    
    const nombres = document.getElementById('ob-nombres').value.trim();
    const apellidos = document.getElementById('ob-apellidos').value.trim();
    const estudios = document.getElementById('ob-estudios').value.trim();
    const federacion = document.getElementById('ob-federacion').value.trim();
    const slug = document.getElementById('ob-slug').value.trim();
    const duracion = parseInt(document.getElementById('ob-duracion').value || 60);
    const receso = parseInt(document.getElementById('ob-receso').value || 15);
    
    const pm_banco = document.getElementById('ob-pm-banco').value.trim();
    const pm_cedula = document.getElementById('ob-pm-cedula').value.trim();
    const pm_telefono = document.getElementById('ob-pm-telefono').value.trim();
    const zelle_email = document.getElementById('ob-zelle-email').value.trim();
    
    const metodos_pago = {
        pago_movil: { banco: pm_banco, cedula: pm_cedula, telefono: pm_telefono },
        zelle: { email: zelle_email }
    };
    
    const onlineActivo = document.getElementById('ob-day-lunes').checked || document.getElementById('ob-day-martes').checked;
    const presencialActivo = document.getElementById('ob-day-miercoles').checked || document.getElementById('ob-day-jueves').checked || document.getElementById('ob-day-viernes').checked;
    
    const perfiles = [
        {
            id: "default_online",
            nombre: "Horario Online",
            modalidad: "Online",
            dias: [
                {"dia": 1, "nombre": "Lunes", "activo": document.getElementById('ob-day-lunes').checked, "rangos": [{"inicio": "12:00", "fin": "16:00"}, {"inicio": "18:00", "fin": "22:00"}]},
                {"dia": 2, "nombre": "Martes", "activo": document.getElementById('ob-day-martes').checked, "rangos": [{"inicio": "18:00", "fin": "22:00"}]},
                {"dia": 3, "nombre": "Miércoles", "activo": false, "rangos": []},
                {"dia": 4, "nombre": "Jueves", "activo": false, "rangos": []},
                {"dia": 5, "nombre": "Viernes", "activo": false, "rangos": []},
                {"dia": 6, "nombre": "Sábado", "activo": false, "rangos": []},
                {"dia": 0, "nombre": "Domingo", "activo": false, "rangos": []}
            ]
        },
        {
            id: "default_presencial",
            nombre: "Horario Presencial",
            modalidad: "Presencial",
            dias: [
                {"dia": 1, "nombre": "Lunes", "activo": false, "rangos": []},
                {"dia": 2, "nombre": "Martes", "activo": false, "rangos": []},
                {"dia": 3, "nombre": "Miércoles", "activo": document.getElementById('ob-day-miercoles').checked, "rangos": [{"inicio": "08:00", "fin": "12:00"}]},
                {"dia": 4, "nombre": "Jueves", "activo": document.getElementById('ob-day-jueves').checked, "rangos": [{"inicio": "08:00", "fin": "12:00"}]},
                {"dia": 5, "nombre": "Viernes", "activo": document.getElementById('ob-day-viernes').checked, "rangos": [{"inicio": "08:00", "fin": "12:00"}]},
                {"dia": 6, "nombre": "Sábado", "activo": false, "rangos": []},
                {"dia": 0, "nombre": "Domingo", "activo": false, "rangos": []}
            ]
        }
    ];

    try {
        const res = await fetch('/api/onboarding/complete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ nombres, apellidos, estudios, federacion, slug, duracion, receso, perfiles, metodos_pago })
        });
        
        const data = await res.json();
        if (res.ok) {
            alert(data.success || '¡Configuración inicial completada!');
            const modal = document.getElementById('psychologist-onboarding-modal');
            if (modal) {
                modal.classList.add('hide');
                modal.style.display = 'none';
            }
            // Recargar datos principales del consultorio
            if (typeof loadAdminAvailability === 'function') loadAdminAvailability();
            if (typeof switchView === 'function') switchView('dashboard');
        } else {
            errBox.textContent = data.error || 'Error al guardar la configuración inicial.';
            errBox.classList.remove('hide');
        }
    } catch (err) {
        errBox.textContent = 'Error de conexión al guardar la configuración.';
        errBox.classList.remove('hide');
    } finally {
        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.textContent = '✓ Finalizar e Ingresar';
        }
    }
}

async function deleteTherapistAccount(userId, therapistName) {
    const confirmMsg = `⚠️ ¿ESTÁS ABSOLUTAMENTE SEGURO de eliminar al psicólogo "${therapistName}"?\n\nEsta acción borrará PERMANENTEMENTE su cuenta, pacientes, historias clínicas, citas y finanzas de la plataforma. Esta acción no se puede deshacer.`;
    if (!confirm(confirmMsg)) return;

    try {
        const res = await fetch(`/api/superadmin/therapists/${userId}`, { method: 'DELETE' });
        const data = await res.json();
        if (res.ok) {
            alert(data.success || "Psicólogo eliminado con éxito.");
            loadSuperadminData();
        } else {
            alert("Error: " + (data.error || "No se pudo eliminar el psicólogo."));
        }
    } catch (err) {
        alert("Error de conexión al intentar eliminar.");
    }
}

async function toggleTherapistSubscription(userId) {
    try {
        const res = await fetch(`/api/superadmin/therapists/${userId}/toggle-subscription`, { method: 'POST' });
        const data = await res.json();
        if (res.ok) {
            alert(data.success || "Estado de suscripción actualizado.");
            loadSuperadminData();
        } else {
            alert("Error: " + (data.error || "No se pudo actualizar la suscripción."));
        }
    } catch (err) {
        alert("Error de conexión al cambiar suscripción.");
    }
}

const RENDER_WA_URL = 'https://espacio-terapeutico-production.up.railway.app';

async function fetchWithTimeout(resource, options = {}) {
    const { timeout = 4000 } = options;
    const controller = new AbortController();
    const id = setTimeout(() => controller.abort(), timeout);
    try {
        const response = await fetch(resource, {
            ...options,
            signal: controller.signal
        });
        clearTimeout(id);
        return response;
    } catch (err) {
        clearTimeout(id);
        throw err;
    }
}

async function checkWhatsAppQRStatus() {
    const badge = document.getElementById('wa-connection-status-badge');
    const loadingBox = document.getElementById('wa-qr-loading');
    const qrBox = document.getElementById('wa-qr-box');
    const qrImage = document.getElementById('wa-qr-image');
    const connectedBox = document.getElementById('wa-connected-box');
    const connectedPhone = document.getElementById('wa-connected-phone');

    if (!badge || !loadingBox || !qrBox || !connectedBox) return;

    try {
        let qrData = null;

        // Intento 1: Consulta directa a Railway (Cero latencia e independiente del servidor Flask)
        try {
            const resDirectQr = await fetchWithTimeout(`${RENDER_WA_URL}/qr`, { mode: 'cors', timeout: 10000 });
            if (resDirectQr.ok) {
                qrData = await resDirectQr.json();
            }
        } catch (e1) {
            console.warn("Consulta directa a Railway falló, intentando vía backend Flask:", e1);
        }

        // Intento 2: Backend Flask en PythonAnywhere
        if (!qrData) {
            try {
                const resBackendQr = await fetchWithTimeout('/api/whatsapp/qr', { timeout: 12000 });
                if (resBackendQr.ok) {
                    qrData = await resBackendQr.json();
                }
            } catch (e2) {}
        }

        // Si la cuenta YA ESTÁ CONECTADA
        if (qrData && qrData.status === 'connected') {
            badge.className = 'badge badge-success';
            badge.style.background = '#10b981';
            badge.style.color = '#ffffff';
            badge.textContent = 'Conectado ✅';
            
            loadingBox.classList.add('hide');
            qrBox.classList.add('hide');
            connectedBox.classList.remove('hide');
            if (connectedPhone) connectedPhone.textContent = qrData.phone || 'Cuenta vinculada';

            if (waPollInterval) {
                clearInterval(waPollInterval);
                waPollInterval = null;
            }
            return;
        } 
        // Si hay un Código QR listo para escanear
        else if (qrData && (qrData.qr || qrData.status === 'qr_ready')) {
            badge.className = 'badge badge-warning';
            badge.style.background = '#f59e0b';
            badge.style.color = '#ffffff';
            badge.textContent = 'Escanear QR 📷';

            loadingBox.classList.add('hide');
            connectedBox.classList.add('hide');
            qrBox.classList.remove('hide');
            if (qrImage && qrData.qr) {
                qrImage.src = qrData.qr;
            }

            if (!waPollInterval) {
                waPollInterval = setInterval(checkWhatsAppQRStatus, 4000);
            }
            return;
        }

        // Estado inicial de espera
        badge.className = 'badge badge-secondary';
        badge.style.background = '#6b7280';
        badge.style.color = '#ffffff';
        badge.textContent = 'Verificando... ⌛';

        loadingBox.classList.remove('hide');
        qrBox.classList.add('hide');
        connectedBox.classList.add('hide');

        if (!waPollInterval) {
            waPollInterval = setInterval(checkWhatsAppQRStatus, 4000);
        }
    } catch (err) {
        console.error("Error al obtener estado de WhatsApp QR:", err);
    }
}


async function handleLogoutWhatsApp() {
    if (!confirm('¿Deseas desconectar tu cuenta de WhatsApp Web? Tendrás que escanear el QR nuevamente.')) return;
    try {
        try {
            await fetch(`${RENDER_WA_URL}/logout`, { method: 'POST' });
        } catch (e) {
            await fetch('/api/whatsapp/logout', { method: 'POST' });
        }
        alert('Sesión de WhatsApp cerrada.');
        checkWhatsAppQRStatus();
    } catch (err) {
        alert('Error al desconectar WhatsApp.');
    }
}


function switchSettingsTab(tabName) {
    const isPsicologo = (window.currentUser && window.currentUser.rol === 'psicologo') || (sessionStorage.getItem('userRole') === 'psicologo');
    const fcmBtn = document.getElementById('set-tab-firebase');
    const fcmCard = document.getElementById('set-card-firebase');
    if (isPsicologo) {
        if (fcmBtn) fcmBtn.style.setProperty('display', 'none', 'important');
        if (fcmCard) fcmCard.style.setProperty('display', 'none', 'important');
        if (tabName === 'firebase') tabName = 'backup';
    } else if (fcmBtn) {
        fcmBtn.style.display = '';
    }

    if (tabName === 'contrasena') tabName = 'password';
    const tabs = ['backup', 'google', 'whatsapp', 'horarios', 'pagos', 'firebase', 'enlaces', 'password', 'contrasena', 'terminos', 'soporte'];
    tabs.forEach(t => {
        const btn = document.getElementById(`set-tab-${t}`);
        const card = document.getElementById(`set-card-${t}`);
        if (btn) btn.className = (t === tabName) ? 'btn btn-sm btn-primary' : 'btn btn-sm btn-secondary';
        if (card) {
            if (t === 'firebase' && isPsicologo) {
                card.style.setProperty('display', 'none', 'important');
            } else {
                card.classList.toggle('hide', t !== tabName);
            }
        }
    });
    if (tabName === 'whatsapp') {
        checkWhatsAppQRStatus();
    } else if (tabName === 'firebase') {
        if (typeof loadFirebaseSettings === 'function') {
            loadFirebaseSettings();
        }
    } else if (tabName === 'pagos') {
        if (typeof loadPaymentMethods === 'function') {
            loadPaymentMethods();
        }
    } else if (tabName === 'terminos') {
        if (typeof loadAdminTerms === 'function') {
            loadAdminTerms();
        }
    }
}
window.switchSettingsTab = switchSettingsTab;

async function sendManualWhatsAppReminder(citaId) {
    if (!confirm('¿Deseas enviar el recordatorio de WhatsApp a este consultante ahora mismo?')) return;
    try {
        const res = await fetch(`/api/whatsapp/send-reminder/${citaId}`, { method: 'POST' });
        const data = await res.json();
        if (res.ok) {
            alert(data.success || 'Recordatorio de WhatsApp enviado con éxito.');
        } else {
            alert('Error: ' + (data.error || 'No se pudo enviar el recordatorio.'));
        }
    } catch (err) {
        alert('Error de conexión al enviar recordatorio por WhatsApp.');
    }
}
window.sendManualWhatsAppReminder = sendManualWhatsAppReminder;

async function triggerManualCronReminders() {
    if (!confirm('¿Deseas procesar y enviar los recordatorios de WhatsApp pendientes ahora?')) return;
    try {
        const res = await fetch('/api/whatsapp/cron-send-reminders', { method: 'POST' });
        const data = await res.json();
        if (res.ok) {
            const totalConfirm = data.confirmaciones_enviadas || 0;
            const totalRemind = data.recordatorios_enviados || 0;
            const totalErr = (data.detalles && data.detalles.errores) ? data.detalles.errores.length : 0;
            
            let msg = `✅ Proceso de WhatsApp completado:\n• Confirmaciones enviadas: ${totalConfirm}\n• Recordatorios enviados: ${totalRemind}`;
            if (totalErr > 0) {
                msg += `\n⚠️ Hubo ${totalErr} error(es) de envío.`;
            }
            alert(msg);
        } else {
            alert('Error al ejecutar envío de recordatorios: ' + (data.error || 'Error desconocido'));
        }
    } catch (err) {
        alert('Error de conexión con el servidor al procesar los recordatorios.');
    }
}
window.triggerManualCronReminders = triggerManualCronReminders;

// ==========================================
// HERRAMIENTAS TERAPÉUTICAS Y MÓDULOS ESPECIALES
// ==========================================

function switchTherapistToolsTab(tab) {
    const viewAsignar = document.getElementById('tt-sub-view-asignar');
    const viewPlantillas = document.getElementById('tt-sub-view-plantillas');
    const tabAsignar = document.getElementById('tt-tab-asignar');
    const tabPlantillas = document.getElementById('tt-tab-plantillas');

    if (!viewAsignar || !viewPlantillas) return;

    if (tab === 'asignar') {
        viewAsignar.classList.remove('hide');
        viewPlantillas.classList.add('hide');
        
        if (tabAsignar) {
            tabAsignar.className = 'btn btn-sm btn-primary';
        }
        if (tabPlantillas) {
            tabPlantillas.className = 'btn btn-sm btn-secondary';
        }
    } else {
        viewAsignar.classList.add('hide');
        viewPlantillas.classList.remove('hide');

        if (tabAsignar) {
            tabAsignar.className = 'btn btn-sm btn-secondary';
        }
        if (tabPlantillas) {
            tabPlantillas.className = 'btn btn-sm btn-primary';
        }

        renderTherapistPreviewTemplates();
    }
}
window.switchTherapistToolsTab = switchTherapistToolsTab;

// ==========================================
// PLANTILLAS DE PREVISUALIZACIÓN VISTA PACIENTE (2 POR PÁGINA)
// ==========================================

let currentTtPreviewPage = 1;
const TT_PREVIEW_PER_PAGE = 2;

const therapistPreviewTemplates = [
    {
        clave: 'sueno',
        titulo: '🌙 Registro Diario de Higiene del Sueño',
        descripcion: 'Cuestionario de 8 ítems diarios para seguimiento de horas dormidas, despertares nocturnos y calidad percibida del descanso.',
        html: `
            <div style="background: white; border: 1.5px solid #d8b4fe; border-radius: var(--radius-md); padding: 1.25rem; box-shadow: var(--shadow-sm); height: 100%; box-sizing: border-box;">
                <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1.5px solid #f3e8ff; padding-bottom: 0.75rem; margin-bottom: 1rem;">
                    <h4 style="margin: 0; font-family: var(--font-title); font-weight: 700; color: #6b21a8; font-size: 1.05rem;">
                        🌙 Cuestionario Diario de Descanso (Vista del Consultante)
                    </h4>
                    <span class="badge" style="background: #f3e8ff; color: #6b21a8; font-weight: 700; border: 1px solid #d8b4fe; padding: 0.25rem 0.6rem;">
                        Formulario Completo Paciente
                    </span>
                </div>
                <div style="display: grid; gap: 0.85rem; width: 100%; background: #faf5ff; padding: 1rem; border-radius: 8px; border: 1px solid #e9d5ff; box-sizing: border-box;">
                    <div>
                        <label style="font-size: 0.82rem; font-weight: 700; color: var(--text-dark);">1. Fecha de Registro &amp; Horarios:</label>
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem; margin-top: 0.25rem;">
                            <div>
                                <span style="font-size: 0.75rem; color: var(--text-muted); display: block;">Me dormí a las:</span>
                                <input type="text" value="11:00 p. m." disabled style="width: 100%; padding: 0.35rem 0.5rem; border-radius: 6px; border: 1px solid var(--border-color); background: white; font-weight: 600;">
                            </div>
                            <div>
                                <span style="font-size: 0.75rem; color: var(--text-muted); display: block;">Me desperté a las:</span>
                                <input type="text" value="06:30 a. m." disabled style="width: 100%; padding: 0.35rem 0.5rem; border-radius: 6px; border: 1px solid var(--border-color); background: white; font-weight: 600;">
                            </div>
                        </div>
                    </div>
                    <div>
                        <label style="font-size: 0.82rem; font-weight: 700; color: var(--text-dark);">2. Situaciones relevantes durante el día:</label>
                        <input type="text" value="Jornada laboral intensa con reunión de proyecto en la tarde." disabled style="width: 100%; padding: 0.4rem; border-radius: 6px; border: 1px solid var(--border-color); background: white;">
                    </div>
                    <div>
                        <label style="font-size: 0.82rem; font-weight: 700; color: var(--text-dark);">3. Emociones relevantes durante el día:</label>
                        <input type="text" value="Algo inquieto por la tarde, más relajado tras cenar." disabled style="width: 100%; padding: 0.4rem; border-radius: 6px; border: 1px solid var(--border-color); background: white;">
                    </div>
                    <div>
                        <label style="font-size: 0.82rem; font-weight: 700; color: var(--text-dark);">4. ¿Cómo fue el proceso para conciliar el sueño?</label>
                        <input type="text" value="Conciliación rápida en 15-20 minutos tras leer un capítulo." disabled style="width: 100%; padding: 0.4rem; border-radius: 6px; border: 1px solid var(--border-color); background: white;">
                    </div>
                    <div>
                        <label style="font-size: 0.82rem; font-weight: 700; color: var(--text-dark);">5. ¿Te despertaste durante la noche?</label>
                        <input type="text" value="Sí, me desperté 1 vez a las 3:00 AM (tomó agua)." disabled style="width: 100%; padding: 0.4rem; border-radius: 6px; border: 1px solid var(--border-color); background: white;">
                    </div>
                    <div>
                        <label style="font-size: 0.82rem; font-weight: 700; color: var(--text-dark);">6. ¿Sentiste que descansaste al despertar?</label>
                        <div style="margin-top: 0.2rem;">
                            <span style="padding: 0.3rem 0.6rem; background: white; border-radius: 6px; border: 1.5px solid #d8b4fe; font-weight: 700; font-size: 0.82rem; color: #6b21a8;">Sí, me sentí descansado/a ⭐ 4/5</span>
                        </div>
                    </div>
                    <div>
                        <label style="font-size: 0.82rem; font-weight: 700; color: var(--text-dark);">7. Síntomas durante el día (Checklist):</label>
                        <div style="display: flex; gap: 0.35rem; flex-wrap: wrap; margin-top: 0.25rem;">
                            <span class="badge" style="background: white; color: #6b21a8; border: 1px solid #d8b4fe; padding: 0.25rem 0.5rem; font-size: 0.78rem; font-weight: 600;">☑️ 🥱 Somnolencia leve</span>
                            <span class="badge" style="background: white; color: var(--text-muted); border: 1px solid var(--border-color); padding: 0.25rem 0.5rem; font-size: 0.78rem;">☐ 🪨 Pesadez</span>
                            <span class="badge" style="background: white; color: var(--text-muted); border: 1px solid var(--border-color); padding: 0.25rem 0.5rem; font-size: 0.78rem;">☐ 🔋 Agotamiento</span>
                        </div>
                    </div>
                    <button type="button" disabled class="btn btn-primary btn-sm" style="width: 100%; opacity: 0.85; font-weight: 700; padding: 0.5rem; margin-top: 0.25rem;">💾 Guardar Registro de Sueño (Simulación)</button>
                </div>
            </div>
        `
    },
    {
        clave: 'ansiedad',
        titulo: '⚡ Diario de Ansiedad & Síntomas Físicos',
        descripcion: 'Registro interactivo para que el paciente identifique niveles de malestar (1 al 10), contexto desencadenante y sintomatología somática.',
        html: `
            <div style="background: white; border: 1.5px solid #fdba74; border-radius: var(--radius-md); padding: 1.25rem; box-shadow: var(--shadow-sm); height: 100%; box-sizing: border-box;">
                <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1.5px solid #ffedd5; padding-bottom: 0.75rem; margin-bottom: 1rem;">
                    <h4 style="margin: 0; font-family: var(--font-title); font-weight: 700; color: #c2410c; font-size: 1.05rem;">
                        ⚡ Diario de Ansiedad (Vista del Consultante)
                    </h4>
                    <span class="badge" style="background: #ffedd5; color: #c2410c; font-weight: 700; border: 1px solid #fdba74; padding: 0.25rem 0.6rem;">
                        Formulario Completo Paciente
                    </span>
                </div>
                <div style="display: grid; gap: 0.85rem; width: 100%; background: #fff7ed; padding: 1rem; border-radius: 8px; border: 1px solid #fed7aa; box-sizing: border-box;">
                    <div>
                        <label style="font-size: 0.82rem; font-weight: 700; color: var(--text-dark);">1. Nivel de Ansiedad percibido (1 a 10):</label>
                        <input type="text" value="7 / 10 (Ansiedad Moderada-Alta)" disabled style="width: 100%; padding: 0.4rem; border-radius: 6px; border: 1.5px solid #fdba74; background: white; font-weight: 700; color: #c2410c;">
                    </div>
                    <div>
                        <label style="font-size: 0.82rem; font-weight: 700; color: #9a3412;">2. Checklist de Síntomas Físicos:</label>
                        <div style="display: flex; gap: 0.35rem; flex-wrap: wrap; margin-top: 0.25rem;">
                            <span class="badge" style="background: white; color: #c2410c; border: 1px solid #fdba74; padding: 0.25rem 0.5rem; font-size: 0.78rem; font-weight: 600;">☑️ 💓 Taquicardia / Palpitaciones</span>
                            <span class="badge" style="background: white; color: #c2410c; border: 1px solid #fdba74; padding: 0.25rem 0.5rem; font-size: 0.78rem; font-weight: 600;">☑️ 🫁 Opresión en el pecho</span>
                            <span class="badge" style="background: white; color: #c2410c; border: 1px solid #fdba74; padding: 0.25rem 0.5rem; font-size: 0.78rem; font-weight: 600;">☑️ 💦 Sudoración excesiva</span>
                            <span class="badge" style="background: white; color: var(--text-muted); border: 1px solid #fed7aa; padding: 0.25rem 0.5rem; font-size: 0.78rem;">☐ 😮‍💨 Dificultad para respirar</span>
                            <span class="badge" style="background: white; color: var(--text-muted); border: 1px solid #fed7aa; padding: 0.25rem 0.5rem; font-size: 0.78rem;">☐ 🧠 Tensión muscular / Cefalea</span>
                            <span class="badge" style="background: white; color: var(--text-muted); border: 1px solid #fed7aa; padding: 0.25rem 0.5rem; font-size: 0.78rem;">☐ 💫 Mareos</span>
                            <span class="badge" style="background: white; color: var(--text-muted); border: 1px solid #fed7aa; padding: 0.25rem 0.5rem; font-size: 0.78rem;">☐ 🤢 Molestias estomacales</span>
                        </div>
                    </div>
                    <div>
                        <label style="font-size: 0.82rem; font-weight: 700; color: #9a3412;">3. Checklist de Síntomas Emocionales &amp; Cognitivos:</label>
                        <div style="display: flex; gap: 0.35rem; flex-wrap: wrap; margin-top: 0.25rem;">
                            <span class="badge" style="background: white; color: #c2410c; border: 1px solid #fdba74; padding: 0.25rem 0.5rem; font-size: 0.78rem; font-weight: 600;">☑️ ⚡ Pensamientos intrusivos</span>
                            <span class="badge" style="background: white; color: #c2410c; border: 1px solid #fdba74; padding: 0.25rem 0.5rem; font-size: 0.78rem; font-weight: 600;">☑️ ⚠️ Inquietud / Peligro</span>
                            <span class="badge" style="background: white; color: var(--text-muted); border: 1px solid #fed7aa; padding: 0.25rem 0.5rem; font-size: 0.78rem;">☐ 😵‍💫 Dificultad concentración</span>
                            <span class="badge" style="background: white; color: var(--text-muted); border: 1px solid #fed7aa; padding: 0.25rem 0.5rem; font-size: 0.78rem;">☐ 😤 Irritabilidad</span>
                        </div>
                    </div>
                    <div>
                        <label style="font-size: 0.82rem; font-weight: 700; color: var(--text-dark);">4. Situación Desencadenante o Notas Reflexivas:</label>
                        <input type="text" value="Reunión de trabajo presencial antes de realizar una presentación oral" disabled style="width: 100%; padding: 0.4rem; border-radius: 6px; border: 1px solid var(--border-color); background: white;">
                    </div>
                    <button type="button" disabled class="btn btn-primary btn-sm" style="width: 100%; opacity: 0.85; font-weight: 700; padding: 0.5rem; background: #c2410c; border-color: #c2410c; margin-top: 0.25rem;">💾 Guardar Registro de Ansiedad (Simulación)</button>
                </div>
            </div>
        `
    },
    {
        clave: 'sobriedad',
        titulo: '🏆 Contador & Registro de Sobriedad / Consumo',
        descripcion: 'Rastreador continuo de días en sobriedad, nivel de deseo/craving (1 a 5) y factores de protección.',
        html: `
            <div style="background: white; border: 1.5px solid #a7f3d0; border-radius: var(--radius-md); padding: 1.25rem; box-shadow: var(--shadow-sm); height: 100%; box-sizing: border-box;">
                <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1.5px solid #d1fae5; padding-bottom: 0.75rem; margin-bottom: 1rem;">
                    <h4 style="margin: 0; font-family: var(--font-title); font-weight: 700; color: #047857; font-size: 1.05rem;">
                        🏆 Registro de Sobriedad / Consumo (Vista del Consultante)
                    </h4>
                    <span class="badge" style="background: #d1fae5; color: #047857; font-weight: 700; border: 1px solid #a7f3d0; padding: 0.25rem 0.6rem;">
                        Formulario Completo Paciente
                    </span>
                </div>
                <div style="background: linear-gradient(135deg, #10b981 0%, #059669 100%); color: white; padding: 1rem; border-radius: 10px; text-align: center; margin-bottom: 0.85rem; box-shadow: 0 4px 15px rgba(16, 185, 129, 0.2);">
                    <div style="font-size: 2rem; font-weight: 800; line-height: 1;">14 Días</div>
                    <div style="font-size: 0.85rem; opacity: 0.95; margin-top: 0.2rem;">Continuos libre de consumo de sustancias</div>
                </div>
                <div style="display: grid; gap: 0.85rem; width: 100%; background: #ecfdf5; padding: 1rem; border-radius: 8px; border: 1px solid #a7f3d0; box-sizing: border-box;">
                    <div>
                        <label style="font-size: 0.82rem; font-weight: 700; color: var(--text-dark);">1. Deseo o Impulso de consumo hoy (Craving 1 a 5):</label>
                        <input type="text" value="2 / 5 (Craving bajo, completamente manejable)" disabled style="width: 100%; padding: 0.4rem; border-radius: 6px; border: 1px solid var(--border-color); background: white; font-weight: 700; color: #047857;">
                    </div>
                    <div>
                        <label style="font-size: 0.82rem; font-weight: 700; color: var(--text-dark);">2. Estrategia o factor de afrontamiento aplicado:</label>
                        <input type="text" value="Salió a ejercitarse y llamó a un familiar al sentir inquietud." disabled style="width: 100%; padding: 0.4rem; border-radius: 6px; border: 1px solid var(--border-color); background: white;">
                    </div>
                    <div>
                        <label style="font-size: 0.82rem; font-weight: 700; color: var(--text-dark);">3. Situaciones o desencadenantes de riesgo identificados:</label>
                        <input type="text" value="Reunión social nocturna el fin de semana, evitó la exposición al alcohol." disabled style="width: 100%; padding: 0.4rem; border-radius: 6px; border: 1px solid var(--border-color); background: white;">
                    </div>
                    <button type="button" disabled class="btn btn-primary btn-sm" style="width: 100%; opacity: 0.85; font-weight: 700; padding: 0.5rem; background: #10b981; border-color: #10b981; margin-top: 0.25rem;">💾 Registrar Día de Sobriedad (Simulación)</button>
                </div>
            </div>
        `
    },
    {
        clave: 'adherencia',
        titulo: '💊 Adherencia al Tratamiento Médico / Psiquiátrico',
        descripcion: 'Formulario de confirmación de tomas horarias de psicofármacos y reporte de efectos secundarios.',
        html: `
            <div style="background: white; border: 1.5px solid #bfdbfe; border-radius: var(--radius-md); padding: 1.25rem; box-shadow: var(--shadow-sm); height: 100%; box-sizing: border-box;">
                <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1.5px solid #dbeafe; padding-bottom: 0.75rem; margin-bottom: 1rem;">
                    <h4 style="margin: 0; font-family: var(--font-title); font-weight: 700; color: #1d4ed8; font-size: 1.05rem;">
                        💊 Adherencia a Medicación (Vista del Consultante)
                    </h4>
                    <span class="badge" style="background: #dbeafe; color: #1d4ed8; font-weight: 700; border: 1px solid #bfdbfe; padding: 0.25rem 0.6rem;">
                        Formulario Completo Paciente
                    </span>
                </div>
                <div style="display: flex; flex-direction: column; gap: 0.85rem; width: 100%; background: #eff6ff; padding: 1rem; border-radius: 8px; border: 1px solid #bfdbfe; box-sizing: border-box;">
                    <div>
                        <label style="font-size: 0.82rem; font-weight: 700; color: var(--text-dark);">1. Medicación Asignada &amp; Tomas del Día:</label>
                        <div style="display: flex; flex-direction: column; gap: 0.5rem; margin-top: 0.25rem;">
                            <div style="display: flex; justify-content: space-between; align-items: center; padding: 0.65rem 0.85rem; background: white; border-radius: 6px; border: 1.5px solid #bfdbfe;">
                                <div>
                                    <strong style="display: block; font-size: 0.88rem; color: #1e293b;">Sertralina 50mg</strong>
                                    <span style="font-size: 0.78rem; color: var(--text-muted);">Dosis Mañana (8:00 AM)</span>
                                </div>
                                <span class="badge badge-success" style="background: #10b981; color: white; padding: 0.3rem 0.6rem; font-size: 0.78rem; font-weight: 700;">Tomado a tiempo ✅</span>
                            </div>
                            <div style="display: flex; justify-content: space-between; align-items: center; padding: 0.65rem 0.85rem; background: white; border-radius: 6px; border: 1.5px solid #bfdbfe;">
                                <div>
                                    <strong style="display: block; font-size: 0.88rem; color: #1e293b;">Clonazepam 0.5mg</strong>
                                    <span style="font-size: 0.78rem; color: var(--text-muted);">Dosis Noche (9:30 PM)</span>
                                </div>
                                <button type="button" disabled class="btn btn-primary btn-sm" style="font-size: 0.78rem; font-weight: 700; padding: 0.3rem 0.65rem;">Marcar como Tomado</button>
                            </div>
                        </div>
                    </div>
                    <div>
                        <label style="font-size: 0.82rem; font-weight: 700; color: var(--text-dark);">2. Observaciones o efectos secundarios reportados:</label>
                        <input type="text" value="Boca levemente seca tras tomar la dosis matutina." disabled style="width: 100%; padding: 0.4rem; border-radius: 6px; border: 1px solid var(--border-color); background: white;">
                    </div>
                    <button type="button" disabled class="btn btn-primary btn-sm" style="width: 100%; opacity: 0.85; font-weight: 700; padding: 0.5rem; background: #1d4ed8; border-color: #1d4ed8; margin-top: 0.25rem;">💾 Guardar Adherencia (Simulación)</button>
                </div>
            </div>
        `
    },
    {
        clave: 'activacion',
        titulo: '🏃 Registro de Activación Conductual',
        descripcion: 'Formulario de programación y reporte de actividades placenteras, necesarias y cotidianas.',
        html: `
            <div style="background: white; border: 1.5px solid #c084fc; border-radius: var(--radius-md); padding: 1.25rem; box-shadow: var(--shadow-sm); height: 100%; box-sizing: border-box;">
                <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1.5px solid #f3e8ff; padding-bottom: 0.75rem; margin-bottom: 1rem;">
                    <h4 style="margin: 0; font-family: var(--font-title); font-weight: 700; color: #7e22ce; font-size: 1.05rem;">
                        🏃 Activación Conductual (Vista del Consultante)
                    </h4>
                    <span class="badge" style="background: #f3e8ff; color: #7e22ce; font-weight: 700; border: 1px solid #c084fc; padding: 0.25rem 0.6rem;">
                        Formulario Completo Paciente
                    </span>
                </div>
                <div style="display: flex; flex-direction: column; gap: 0.85rem; width: 100%; background: #faf5ff; padding: 1rem; border-radius: 8px; border: 1px solid #e9d5ff; box-sizing: border-box;">
                    <div>
                        <label style="font-size: 0.82rem; font-weight: 700; color: var(--text-dark);">1. Actividades Programadas y Nivel de Logro:</label>
                        <div style="display: flex; flex-direction: column; gap: 0.5rem; margin-top: 0.25rem;">
                            <div style="padding: 0.65rem 0.85rem; background: white; border-radius: 6px; border: 1.5px solid #e9d5ff;">
                                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.25rem;">
                                    <strong style="font-size: 0.88rem; color: var(--text-dark);">🚶‍♂️ Caminata al aire libre 20 min</strong>
                                    <span class="badge" style="background: #fdf4ff; color: #a21caf; border: 1px solid #f5d0fe; font-weight: 700; font-size: 0.75rem;">🎉 Placer / Disfrute</span>
                                </div>
                                <span style="font-size: 0.78rem; color: var(--text-muted); display: block;">Nivel de satisfacción logrado: <strong>8 / 10</strong></span>
                            </div>
                            <div style="padding: 0.65rem 0.85rem; background: white; border-radius: 6px; border: 1.5px solid #e9d5ff;">
                                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.25rem;">
                                    <strong style="font-size: 0.88rem; color: var(--text-dark);">🛏️ Ordenar la habitación y hacer la cama</strong>
                                    <span class="badge" style="background: #f0fdf4; color: #15803d; border: 1px solid #bbf7d0; font-weight: 700; font-size: 0.75rem;">🏠 Cotidiana</span>
                                </div>
                                <span style="font-size: 0.78rem; color: var(--text-muted); display: block;">Nivel de logro o dominio: <strong>9 / 10</strong></span>
                            </div>
                        </div>
                    </div>
                    <div>
                        <label style="font-size: 0.82rem; font-weight: 700; color: var(--text-dark);">2. Estado de Ánimo previo y posterior a la actividad:</label>
                        <input type="text" value="Antes: 4/10 (Apatía) ➔ Después: 8/10 (Energizado)" disabled style="width: 100%; padding: 0.4rem; border-radius: 6px; border: 1px solid var(--border-color); background: white;">
                    </div>
                    <button type="button" disabled class="btn btn-primary btn-sm" style="width: 100%; opacity: 0.85; font-weight: 700; padding: 0.5rem; background: #7e22ce; border-color: #7e22ce; margin-top: 0.25rem;">💾 Registrar Activación (Simulación)</button>
                </div>
            </div>
        `
    },
    {
        clave: 'ingesta',
        titulo: '🥗 Registro de Ingesta Emocional & Alimentación',
        descripcion: 'Formulario para registrar comidas, estados emocionales asociados previo a la ingesta y nivel de saciedad.',
        html: `
            <div style="background: white; border: 1.5px solid #fde047; border-radius: var(--radius-md); padding: 1.25rem; box-shadow: var(--shadow-sm); height: 100%; box-sizing: border-box;">
                <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1.5px solid #fef9c3; padding-bottom: 0.75rem; margin-bottom: 1rem;">
                    <h4 style="margin: 0; font-family: var(--font-title); font-weight: 700; color: #a16207; font-size: 1.05rem;">
                        🥗 Diario de Ingesta Emocional (Vista del Consultante)
                    </h4>
                    <span class="badge" style="background: #fef9c3; color: #a16207; font-weight: 700; border: 1px solid #fde047; padding: 0.25rem 0.6rem;">
                        Formulario Completo Paciente
                    </span>
                </div>
                <div style="display: grid; gap: 0.85rem; width: 100%; background: #fefce8; padding: 1rem; border-radius: 8px; border: 1px solid #fef08a; box-sizing: border-box;">
                    <div>
                        <label style="font-size: 0.82rem; font-weight: 700; color: var(--text-dark);">1. Tipo de Comida &amp; Descripción del Plato:</label>
                        <input type="text" value="Almuerzo: Pechuga a la plancha, ensalada de vegetales y 1 taza de arroz" disabled style="width: 100%; padding: 0.4rem; border-radius: 6px; border: 1px solid var(--border-color); background: white;">
                    </div>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem;">
                        <div>
                            <span style="font-size: 0.75rem; color: var(--text-muted); display: block; font-weight: 700;">Apetito Previo (0 a 10):</span>
                            <input type="text" value="6 / 10 (Hambre moderada)" disabled style="width: 100%; padding: 0.35rem; border-radius: 6px; border: 1px solid var(--border-color); background: white; font-weight: 700; color: #15803d;">
                        </div>
                        <div>
                            <span style="font-size: 0.75rem; color: var(--text-muted); display: block; font-weight: 700;">Escala de Saciedad (0 a 10):</span>
                            <input type="text" value="7 / 10 (Satisfecho adecuadamente)" disabled style="width: 100%; padding: 0.35rem; border-radius: 6px; border: 1px solid var(--border-color); background: white; font-weight: 700; color: #15803d;">
                        </div>
                    </div>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem;">
                        <div>
                            <span style="font-size: 0.75rem; color: var(--text-muted); display: block; font-weight: 700;">Contexto (¿Dónde comí?):</span>
                            <input type="text" value="En el comedor del trabajo" disabled style="width: 100%; padding: 0.35rem; border-radius: 6px; border: 1px solid var(--border-color); background: white;">
                        </div>
                        <div>
                            <span style="font-size: 0.75rem; color: var(--text-muted); display: block; font-weight: 700;">Afectividad (¿Cómo me sentí?):</span>
                            <input type="text" value="Tranquilo, sin prisa" disabled style="width: 100%; padding: 0.35rem; border-radius: 6px; border: 1px solid var(--border-color); background: white;">
                        </div>
                    </div>
                    <div>
                        <label style="font-size: 0.82rem; font-weight: 700; color: var(--text-dark);">2. Pensamiento negativo asociado:</label>
                        <input type="text" value="Sin pensamientos negativos durante la comida." disabled style="width: 100%; padding: 0.4rem; border-radius: 6px; border: 1px solid var(--border-color); background: white;">
                    </div>
                    <div>
                        <label style="font-size: 0.82rem; font-weight: 700; color: #15803d;">3. Checklist de Conductas Problema:</label>
                        <div style="display: flex; gap: 0.35rem; flex-wrap: wrap; margin-top: 0.25rem;">
                            <span class="badge" style="background: white; color: var(--text-muted); border: 1px solid #fef08a; padding: 0.25rem 0.5rem; font-size: 0.78rem;">☐ ⚠️ Atracón</span>
                            <span class="badge" style="background: white; color: var(--text-muted); border: 1px solid #fef08a; padding: 0.25rem 0.5rem; font-size: 0.78rem;">☐ 🚨 Conducta purgativa</span>
                            <span class="badge" style="background: white; color: var(--text-muted); border: 1px solid #fef08a; padding: 0.25rem 0.5rem; font-size: 0.78rem;">☐ 🚫 Restricción severa</span>
                            <span class="badge" style="background: white; color: var(--text-muted); border: 1px solid #fef08a; padding: 0.25rem 0.5rem; font-size: 0.78rem;">☐ 😔 Comer con culpa</span>
                            <span class="badge" style="background: white; color: var(--text-muted); border: 1px solid #fef08a; padding: 0.25rem 0.5rem; font-size: 0.78rem;">☐ ⚡ Comer por ansiedad</span>
                        </div>
                    </div>
                    <button type="button" disabled class="btn btn-primary btn-sm" style="width: 100%; opacity: 0.85; font-weight: 700; padding: 0.5rem; background: #ca8a04; border-color: #ca8a04; margin-top: 0.25rem;">💾 Registrar Comida (Simulación)</button>
                </div>
            </div>
        `
    },
    {
        clave: 'cognitivo',
        titulo: '🧠 Reestructuración Cognitiva & Registro de Pensamientos',
        descripcion: 'Formulario ABC/CBT para identificar pensamientos automáticos distorsionados y generar pensamientos alternativos adaptativos.',
        html: `
            <div style="background: white; border: 1.5px solid #94a3b8; border-radius: var(--radius-md); padding: 1.25rem; box-shadow: var(--shadow-sm); height: 100%; box-sizing: border-box;">
                <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1.5px solid #f1f5f9; padding-bottom: 0.75rem; margin-bottom: 1rem;">
                    <h4 style="margin: 0; font-family: var(--font-title); font-weight: 700; color: #334155; font-size: 1.05rem;">
                        🧠 Registro Cognitivo TCC (Vista del Consultante)
                    </h4>
                    <span class="badge" style="background: #f1f5f9; color: #334155; font-weight: 700; border: 1px solid #cbd5e1; padding: 0.25rem 0.6rem;">
                        Formulario Completo Paciente
                    </span>
                </div>
                <div style="display: grid; gap: 0.85rem; width: 100%; background: #f8fafc; padding: 1rem; border-radius: 8px; border: 1px solid #e2e8f0; box-sizing: border-box;">
                    <div>
                        <label style="font-size: 0.82rem; font-weight: 700; color: var(--text-dark);">1. Intensidad Emocional (0 a 10):</label>
                        <input type="text" value="7 / 10 (Intensidad Elevada)" disabled style="width: 100%; padding: 0.4rem; border-radius: 6px; border: 1.5px solid #94a3b8; background: white; font-weight: 700; color: #7e22ce;">
                    </div>
                    <div>
                        <label style="font-size: 0.82rem; font-weight: 700; color: var(--text-dark);">2. Situación (A: ¿Qué sucedió?):</label>
                        <input type="text" value="Enviar un mensaje de trabajo importante y no recibir respuesta inmediata." disabled style="width: 100%; padding: 0.4rem; border-radius: 6px; border: 1px solid var(--border-color); background: white;">
                    </div>
                    <div>
                        <label style="font-size: 0.82rem; font-weight: 700; color: var(--text-dark);">3. Pensamiento Automático (B: ¿Qué pasa por mi mente?):</label>
                        <input type="text" value="'Están molestos conmigo o cometí un error en mi informe.'" disabled style="width: 100%; padding: 0.4rem; border-radius: 6px; border: 1px solid var(--border-color); background: white; color: #b91c1c; font-weight: 700;">
                    </div>
                    <div>
                        <label style="font-size: 0.82rem; font-weight: 700; color: var(--text-dark);">4. Emoción o Sensación:</label>
                        <input type="text" value="Ansiedad y opresión en el pecho" disabled style="width: 100%; padding: 0.4rem; border-radius: 6px; border: 1px solid var(--border-color); background: white;">
                    </div>
                    <div>
                        <label style="font-size: 0.82rem; font-weight: 700; color: var(--text-dark);">5. Conducta (¿Qué hice?):</label>
                        <input type="text" value="Revisé el correo obsesivamente" disabled style="width: 100%; padding: 0.4rem; border-radius: 6px; border: 1px solid var(--border-color); background: white;">
                    </div>
                    <div>
                        <label style="font-size: 0.82rem; font-weight: 700; color: #047857;">6. Pensamiento Alternativo Racional (CBT):</label>
                        <input type="text" value="'Es muy probable que estén ocupados en una reunión. Mi informe está correcto.'" disabled style="width: 100%; padding: 0.4rem; border-radius: 6px; border: 1.5px solid #10b981; background: white; color: #047857; font-weight: 700;">
                    </div>
                    <button type="button" disabled class="btn btn-primary btn-sm" style="width: 100%; opacity: 0.85; font-weight: 700; padding: 0.5rem; background: #475569; border-color: #475569; margin-top: 0.25rem;">💾 Guardar Registro Cognitivo (Simulación)</button>
                </div>
            </div>
        `
    }
];

function renderTherapistPreviewTemplates() {
    const container = document.getElementById('tt-preview-templates-container');
    if (!container) return;

    const totalPages = Math.ceil(therapistPreviewTemplates.length / TT_PREVIEW_PER_PAGE);
    if (currentTtPreviewPage > totalPages) currentTtPreviewPage = totalPages;
    if (currentTtPreviewPage < 1) currentTtPreviewPage = 1;

    const start = (currentTtPreviewPage - 1) * TT_PREVIEW_PER_PAGE;
    const pageRecords = therapistPreviewTemplates.slice(start, start + TT_PREVIEW_PER_PAGE);

    container.innerHTML = pageRecords.map(tmpl => tmpl.html).join('');

    renderTtTemplatesPaginationControls(therapistPreviewTemplates.length, totalPages);
}

function renderTtTemplatesPaginationControls(totalRecords, totalPages) {
    let container = document.getElementById('tt-templates-pagination-controls');
    if (!container) return;

    if (totalRecords === 0 || totalPages <= 1) {
        container.innerHTML = '';
        return;
    }

    container.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: center; padding: 0.65rem 0.85rem; background: white; border: 1.5px solid var(--border-color); border-radius: 8px; margin-top: 0.75rem; flex-wrap: wrap; gap: 0.5rem;">
            <button type="button" class="btn btn-sm btn-outline-secondary" onclick="changeTtPreviewPage(${currentTtPreviewPage - 1})" ${currentTtPreviewPage <= 1 ? 'disabled' : ''} style="font-weight: 700; padding: 0.35rem 0.85rem;">
                ◀️ Plantillas Anteriores
            </button>
            <span style="font-size: 0.85rem; font-weight: 700; color: var(--text-dark);">
                Página ${currentTtPreviewPage} de ${totalPages} (${totalRecords} plantillas disponibles)
            </span>
            <button type="button" class="btn btn-sm btn-outline-secondary" onclick="changeTtPreviewPage(${currentTtPreviewPage + 1})" ${currentTtPreviewPage >= totalPages ? 'disabled' : ''} style="font-weight: 700; padding: 0.35rem 0.85rem;">
                Plantillas Siguientes ▶️
            </button>
        </div>
    `;
}

function changeTtPreviewPage(newPage) {
    currentTtPreviewPage = newPage;
    renderTherapistPreviewTemplates();
}
window.changeTtPreviewPage = changeTtPreviewPage;

const toolButtonLabels = {
    'sueno': '📊 Ver Registro de Sueño',
    'ansiedad': '📊 Ver Registro de Ansiedad',
    'sobriedad': '📊 Ver Registro de Consumo',
    'consumo': '📊 Ver Registro de Consumo',
    'adherencia': '📊 Ver Registro de Tratamiento',
    'medicacion': '📊 Ver Registro de Tratamiento',
    'activacion': '📊 Ver Registro de Activación Conductual'
};

const claveToToolMap = {
    'sueno': 'sueno',
    'ansiedad': 'ansiedad',
    'sobriedad': 'consumo',
    'consumo': 'consumo',
    'adherencia': 'medicacion',
    'medicacion': 'medicacion',
    'activacion': 'activacion'
};

let therapistToolsPatientsCatalog = [];

let currentToolsCatalogList = [];
let currentToolsCatalogPage = 1;
const TOOLS_CATALOG_PER_PAGE = 3;

async function loadTherapistToolsCatalog() {
    const container = document.getElementById('tt-modules-accordion') || document.getElementById('tt-modules-grid');
    if (!container) return;
    container.innerHTML = '<p class="text-muted">Cargando catálogo de herramientas y consultantes activos...</p>';
    try {
        const res = await fetch('/api/therapist/modules/catalog');
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Error al cargar catálogo');

        currentToolsCatalogList = data;
        renderTherapistToolsCatalog();
    } catch (err) {
        container.innerHTML = `<p class="text-danger">Error: ${err.message}</p>`;
    }
}

function renderTherapistToolsCatalog() {
    const container = document.getElementById('tt-modules-accordion') || document.getElementById('tt-modules-grid');
    if (!container) return;

    if (currentToolsCatalogList.length === 0) {
        container.innerHTML = '<p class="text-muted text-center py-3">No hay herramientas terapéuticas disponibles.</p>';
        renderToolsCatalogPaginationControls(0, 1);
        return;
    }

    const totalPages = Math.ceil(currentToolsCatalogList.length / TOOLS_CATALOG_PER_PAGE);
    if (currentToolsCatalogPage > totalPages) currentToolsCatalogPage = totalPages;
    if (currentToolsCatalogPage < 1) currentToolsCatalogPage = 1;

    const start = (currentToolsCatalogPage - 1) * TOOLS_CATALOG_PER_PAGE;
    const pageRecords = currentToolsCatalogList.slice(start, start + TOOLS_CATALOG_PER_PAGE);

    container.innerHTML = pageRecords.map(m => {
        const toolType = claveToToolMap[m.clave] || m.clave;
        const targetId = `acc-body-${m.clave}`;
        const activeCount = m.activos || 0;
        const patients = m.pacientes || [];

        let patientsHtml = '';
        if (patients.length === 0) {
            patientsHtml = `
                <div style="padding: 1rem; text-align: center; color: var(--text-muted); font-size: 0.88rem;">
                    📭 No hay consultantes con esta herramienta activa actualmente.
                </div>
            `;
        } else {
            patientsHtml = patients.map(p => {
                const inlineContainerId = `inline-history-acc-${p.patient_id}-${toolType}`;
                return `
                    <div style="display: flex; flex-direction: column; width: 100%;">
                        <div style="display: flex; align-items: center; justify-content: space-between; padding: 0.75rem 1rem; background: var(--bg-light); border-radius: var(--radius-sm); border: 1px solid var(--border-color); flex-wrap: wrap; gap: 0.6rem;">
                            <div style="flex: 1; min-width: 220px;">
                                <strong style="font-size: 0.92rem; color: var(--text-dark); display: block;">👤 ${p.nombre_paciente}</strong>
                                <span style="font-size: 0.8rem; color: var(--text-muted);">${p.cedula ? 'Cédula: ' + p.cedula + ' | ' : ''}${p.metric_text}</span>
                            </div>
                            <div>
                                <button type="button" class="btn btn-primary btn-sm btn-view-history" onclick="toggleInlinePatientHistory(${p.patient_id}, '${toolType}', '${inlineContainerId}')" style="font-weight: 600; padding: 0.35rem 0.75rem;">
                                    📋 Ver Historial
                                </button>
                            </div>
                        </div>
                        <div id="${inlineContainerId}" class="inline-patient-history hide" style="display: none; margin-top: 0.5rem; width: 100%;"></div>
                    </div>
                `;
            }).join('<div style="height: 0.5rem;"></div>');
        }

        return `
        <div class="card accordion-tool-card" style="background: white; border: 1.5px solid var(--border-color); border-radius: var(--radius-md); overflow: hidden; margin-bottom: 0.5rem; box-shadow: var(--shadow-sm);">
            <!-- CABECERA: Línea 1 (Ícono + Nombre Completo + Flecha + Previsualizar) / Línea 2 (Pacientes Activos) -->
            <div class="accordion-tool-header" data-target="${targetId}" style="padding: 0.55rem 0.85rem; background: white; cursor: pointer; display: flex; flex-direction: column; gap: 0.15rem; user-select: none; transition: background 0.2s;">
                <!-- LÍNEA 1: Ícono + Nombre Completo + Botón Previsualizar y Flecha -->
                <div style="display: flex; align-items: center; justify-content: space-between; gap: 0.5rem; width: 100%;">
                    <div style="display: flex; align-items: center; gap: 0.5rem; flex: 1; min-width: 0;">
                        <span style="font-size: 1.25rem; line-height: 1; flex-shrink: 0;">${m.icono}</span>
                        <h4 style="margin: 0; font-family: var(--font-title); font-weight: 700; color: var(--text-dark); font-size: 0.92rem; line-height: 1.2; word-break: break-word;">${m.nombre}</h4>
                    </div>
                    <div style="display: flex; align-items: center; gap: 0.4rem; flex-shrink: 0;">
                        <button type="button" id="btn-preview-tool-${m.clave}" class="btn btn-sm btn-outline-primary" onclick="event.stopPropagation(); toggleToolPreview('${m.clave}', '${m.nombre.replace(/'/g, "\\'")}')" style="padding: 0.15rem 0.5rem; font-size: 0.75rem; border-radius: 4px; display: inline-flex; align-items: center; gap: 0.25rem; font-weight: 600;">👁️ Previsualizar</button>
                        <button type="button" class="btn btn-sm btn-outline-secondary accordion-toggle-btn" style="padding: 0.15rem 0.45rem; font-size: 0.75rem; border-radius: 4px; display: flex; align-items: center; justify-content: center; border: 1px solid var(--border-color); background: #f9fafb;">
                            <span class="accordion-arrow" style="font-size: 0.85rem; transition: transform 0.25s ease;">🔽</span>
                        </button>
                    </div>
                </div>
                <!-- LÍNEA 2: Número de pacientes activos -->
                <div style="margin-left: 1.75rem; line-height: 1;">
                    <span class="badge" style="background: rgba(126, 34, 206, 0.1); color: #7e22ce; font-weight: 700; border: 1px solid rgba(126, 34, 206, 0.25); font-size: 0.72rem; padding: 0.12rem 0.4rem;">
                        ${activeCount} Paciente(s) Activos
                    </span>
                </div>
            </div>
            <!-- CONTENEDOR DE PREVISUALIZACIÓN INLINE -->
            <div id="inline-tool-preview-${m.clave}" class="inline-tool-preview hide" style="display: none; padding: 0.85rem 1rem; border-top: 1.5px solid #d8b4fe; background: #faf5ff;"></div>
            <!-- CUERPO DESPLEGABLE: Descripción + Lista de Consultantes -->
            <div id="${targetId}" class="accordion-tool-body hide" style="display: none; padding: 0.85rem 1rem; border-top: 1.5px solid var(--border-color); background: #fafafa;">
                <div style="display: flex; flex-direction: column; gap: 0.75rem;">
                    <p style="font-size: 0.83rem; color: var(--text-muted); margin: 0; line-height: 1.4; background: white; padding: 0.65rem 0.85rem; border-radius: 6px; border: 1px solid var(--border-color);">
                        ℹ️ <strong>Descripción:</strong> ${m.descripcion}
                    </p>
                    ${patientsHtml}
                </div>
            </div>
        </div>
        `;
    }).join('');

    renderToolsCatalogPaginationControls(currentToolsCatalogList.length, totalPages);
}

function renderToolsCatalogPaginationControls(totalRecords, totalPages) {
    let container = document.getElementById('tools-catalog-pagination-controls');
    if (!container) return;

    if (totalRecords === 0 || totalPages <= 1) {
        container.innerHTML = '';
        return;
    }

    container.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: center; padding: 0.65rem 0.85rem; background: white; border: 1.5px solid var(--border-color); border-radius: 8px; margin-top: 0.75rem; flex-wrap: wrap; gap: 0.5rem;">
            <button type="button" class="btn btn-sm btn-outline-secondary" onclick="changeToolsCatalogPage(${currentToolsCatalogPage - 1})" ${currentToolsCatalogPage <= 1 ? 'disabled' : ''} style="font-weight: 700; padding: 0.3rem 0.75rem;">
                ◀️ Módulos Anteriores
            </button>
            <span style="font-size: 0.85rem; font-weight: 700; color: var(--text-dark);">
                Página ${currentToolsCatalogPage} de ${totalPages} (${totalRecords} módulos)
            </span>
            <button type="button" class="btn btn-sm btn-outline-secondary" onclick="changeToolsCatalogPage(${currentToolsCatalogPage + 1})" ${currentToolsCatalogPage >= totalPages ? 'disabled' : ''} style="font-weight: 700; padding: 0.3rem 0.75rem;">
                Módulos Siguientes ▶️
            </button>
        </div>
    `;
}

function changeToolsCatalogPage(newPage) {
    currentToolsCatalogPage = newPage;
    renderTherapistToolsCatalog();
}
window.changeToolsCatalogPage = changeToolsCatalogPage;

// ==========================================
// ESTADO Y RENDERIZADO DE HISTORIAL DESPLEGABLE CON PAGINACIÓN (5 REGISTROS POR PÁGINA)
// ==========================================

const patientHistoryState = {};

async function toggleInlinePatientHistory(patientId, toolKey, containerId) {
    console.log('[DEBUG] toggleInlinePatientHistory called:', patientId, toolKey, containerId);
    
    const claveMap = {
        'sueno': 'sueno',
        'ansiedad': 'ansiedad',
        'sobriedad': 'sobriedad',
        'consumo': 'sobriedad',
        'adherencia': 'adherencia',
        'medicacion': 'adherencia',
        'activacion': 'activacion'
    };
    const normKey = claveMap[toolKey] || toolKey;
    const container = document.getElementById(containerId);

    // Alternar si ya está desplegado con contenido
    if (container && container.style.display !== 'none' && container.childElementCount > 0) {
        container.style.display = 'none';
        container.classList.add('hide');
        return;
    }

    if (container) {
        container.style.setProperty('display', 'block', 'important');
        container.classList.remove('hide');
        container.innerHTML = '<div style="padding: 0.75rem; color: var(--text-muted); font-size: 0.85rem; text-align: center;">⌛ Cargando registros de la herramienta...</div>';
    }

    try {
        const res = await fetch(`/api/therapist/modules/report/${normKey}`);
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Error al cargar historial');

        const patientRecords = (data || []).filter(r => r.paciente_id == patientId);

        if (patientRecords.length === 0) {
            if (container) {
                container.innerHTML = '<div style="padding: 0.85rem; background: #fff; border: 1px solid var(--border-color); border-radius: 6px; color: var(--text-muted); font-size: 0.85rem; text-align: center;">📭 El consultante aún no ha registrado datos en esta herramienta.</div>';
            }
            return;
        }

        const stateKey = `${patientId}_${normKey}_${containerId}`;
        patientHistoryState[stateKey] = {
            records: patientRecords,
            page: 1,
            clave: normKey,
            containerId: containerId
        };

        renderPaginatedHistoryTable(stateKey);

    } catch (err) {
        if (container) {
            container.innerHTML = `<div style="padding: 0.75rem; color: var(--color-danger); font-size: 0.85rem;">⚠️ Error: ${err.message}</div>`;
        }
    }
}

function renderPaginatedHistoryTable(stateKey) {
    const state = patientHistoryState[stateKey];
    if (!state || !state.records) return;

    const pageSize = 5;
    const totalRecords = state.records.length;
    const totalPages = Math.ceil(totalRecords / pageSize);
    const currentPage = Math.max(1, Math.min(state.page || 1, totalPages));
    state.page = currentPage;

    const startIndex = (currentPage - 1) * pageSize;
    const endIndex = Math.min(startIndex + pageSize, totalRecords);
    const pageRecords = state.records.slice(startIndex, endIndex);

    const moduloClave = state.clave;
    let cardsHtml = '';

    if (moduloClave === 'sobriedad') {
        cardsHtml = pageRecords.map(r => {
            const estadoBadge = r.sobrio ?
                `<span class="badge" style="background:#f0fdf4; color:#15803d; font-weight:700;">🟢 Libre de consumo</span>` :
                `<span class="badge" style="background:#fef2f2; color:#b91c1c; font-weight:700;">⚠️ Consumo / Recaída</span>`;
            const cravingText = (r.nivel_ansiedad !== null && r.nivel_ansiedad !== undefined) ?
                `<span class="badge" style="background:#fff7ed; color:#c2410c; font-weight:800;">${r.nivel_ansiedad} / 10</span>` : 'Sin registrar';
            
            return `
                <div style="background: white; border: 1.5px solid var(--border-color); border-radius: 8px; padding: 0.85rem 1rem; display: flex; flex-direction: column; gap: 0.4rem; box-shadow: var(--shadow-sm); margin-bottom: 0.6rem;">
                    <!-- Línea 1: Fecha / Estado -->
                    <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border-color); padding-bottom: 0.4rem; flex-wrap: wrap; gap: 0.4rem;">
                        <strong style="font-size: 0.9rem; color: var(--text-dark);">📅 Fecha: ${r.fecha}</strong>
                        <div>${estadoBadge}</div>
                    </div>
                    <!-- Línea 2: Deseo / Impulso de consumo (Craving) -->
                    <div style="font-size: 0.84rem; color: var(--text-dark);">
                        🧠 <strong>Deseo / Impulso de consumo (Craving):</strong> ${cravingText}
                    </div>
                    <!-- Línea 3: Disparador Emocional -->
                    <div style="font-size: 0.84rem; color: var(--text-dark);">
                        🎯 <strong>Disparador Emocional:</strong> ${r.disparador_emocional || 'Ninguno especificado'}
                    </div>
                    <!-- Línea 4: Notas -->
                    <div style="font-size: 0.84rem; color: var(--text-dark); background: #f9fafb; padding: 0.5rem 0.75rem; border-radius: 6px; border-left: 3px solid var(--primary-color);">
                        📝 <strong>Notas:</strong> ${r.notas || 'Sin notas adicionales'}
                    </div>
                </div>
            `;
        }).join('');
    } else if (moduloClave === 'sueno') {
        cardsHtml = pageRecords.map(r => {
            const descansoBadge = r.senti_descanso ?
                `<span class="badge" style="background:#f0fdf4; color:#15803d; font-weight:700;">🟢 Reparador</span>` :
                `<span class="badge" style="background:#fef2f2; color:#b91c1c; font-weight:700;">🔴 No reparador</span>`;
            const despertaresText = r.desperto_noche ? `Sí (${r.cant_despertares || 1} veces)` : 'No';
            const horarioText = `${r.hora_dormi || '--:--'} a ${r.hora_desperto || '--:--'}`;
            const sintomasList = [
                r.somnolencia_dia ? '🥱 Somnolencia' : null,
                r.pesadez_dia ? '🪨 Pesadez' : null,
                r.agotamiento_dia ? '🔋 Agotamiento' : null
            ].filter(Boolean).join(', ') || 'Ninguno';

            return `
                <div style="background: white; border: 1.5px solid var(--border-color); border-radius: 8px; padding: 0.85rem 1rem; display: flex; flex-direction: column; gap: 0.4rem; box-shadow: var(--shadow-sm); margin-bottom: 0.6rem;">
                    <!-- Línea 1: Fecha / Estado Descanso -->
                    <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border-color); padding-bottom: 0.4rem; flex-wrap: wrap; gap: 0.4rem;">
                        <strong style="font-size: 0.9rem; color: var(--text-dark);">📅 Fecha: ${r.fecha}</strong>
                        <div>${descansoBadge}</div>
                    </div>
                    <!-- Línea 2: Horario y Despertares -->
                    <div style="font-size: 0.84rem; color: var(--text-dark);">
                        ⏰ <strong>Horario de Sueño:</strong> ${horarioText} | 🥱 <strong>Despertares nocturnos:</strong> ${despertaresText}
                    </div>
                    <!-- Línea 3: Síntomas del día -->
                    <div style="font-size: 0.84rem; color: var(--text-dark);">
                        🔋 <strong>Síntomas en el día:</strong> ${sintomasList}
                    </div>
                    <!-- Línea 4: Conciliación / Situaciones -->
                    <div style="font-size: 0.84rem; color: var(--text-dark); background: #f9fafb; padding: 0.5rem 0.75rem; border-radius: 6px; border-left: 3px solid #7e22ce;">
                        💭 <strong>Conciliación / Situaciones del día:</strong> ${r.proceso_dormir || r.situaciones_dia || r.emociones_dia || 'Sin detalles adicionales'}
                    </div>
                </div>
            `;
        }).join('');
    } else if (moduloClave === 'adherencia') {
        cardsHtml = pageRecords.map(r => {
            const tomadoBadge = r.tomado ?
                `<span class="badge" style="background:#f0fdf4; color:#15803d; font-weight:700;">🟢 Tomado</span>` :
                `<span class="badge" style="background:#fef2f2; color:#b91c1c; font-weight:700;">🔴 No tomado</span>`;

            return `
                <div style="background: white; border: 1.5px solid var(--border-color); border-radius: 8px; padding: 0.85rem 1rem; display: flex; flex-direction: column; gap: 0.4rem; box-shadow: var(--shadow-sm); margin-bottom: 0.6rem;">
                    <!-- Línea 1: Fecha / Medicamento / Estado -->
                    <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border-color); padding-bottom: 0.4rem; flex-wrap: wrap; gap: 0.4rem;">
                        <strong style="font-size: 0.9rem; color: var(--text-dark);">📅 Fecha: ${r.fecha} - 💊 ${r.nombre_medicamento}</strong>
                        <div>${tomadoBadge}</div>
                    </div>
                    <!-- Línea 2: Prescripción y Hora Real -->
                    <div style="font-size: 0.84rem; color: var(--text-dark);">
                        ⏰ <strong>Prescripción:</strong> ${r.dosis || '-'} (${r.hora_prescrita || '-'}) | 🕒 <strong>Hora Real Toma:</strong> ${r.hora_tomado || '-'}
                    </div>
                    <!-- Línea 3: Notas -->
                    <div style="font-size: 0.84rem; color: var(--text-dark); background: #f9fafb; padding: 0.5rem 0.75rem; border-radius: 6px; border-left: 3px solid #15803d;">
                        📝 <strong>Notas:</strong> ${r.notas || 'Sin observaciones'}
                    </div>
                </div>
            `;
        }).join('');
    } else if (moduloClave === 'activacion') {
        cardsHtml = pageRecords.map(r => {
            const catLabel = r.categoria === 'necesaria' ? '📌 Necesaria' : (r.categoria === 'placer' ? '🎉 Disfrute/Placer' : '🏠 Cotidiana');
            const compBadge = r.completada ?
                `<span class="badge" style="background:#f0fdf4; color:#15803d; font-weight:700;">🟢 Completada</span>` :
                `<span class="badge" style="background:#f3f4f6; color:#6b7280; font-weight:700;">⚪ Pendiente</span>`;

            return `
                <div style="background: white; border: 1.5px solid var(--border-color); border-radius: 8px; padding: 0.85rem 1rem; display: flex; flex-direction: column; gap: 0.4rem; box-shadow: var(--shadow-sm); margin-bottom: 0.6rem;">
                    <!-- Línea 1: Fecha / Categoría / Estado -->
                    <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border-color); padding-bottom: 0.4rem; flex-wrap: wrap; gap: 0.4rem;">
                        <strong style="font-size: 0.9rem; color: var(--text-dark);">📅 Fecha: ${r.fecha} (${catLabel})</strong>
                        <div>${compBadge}</div>
                    </div>
                    <!-- Línea 2: Actividad -->
                    <div style="font-size: 0.84rem; color: var(--text-dark);">
                        🎯 <strong>Actividad:</strong> ${r.nombre_actividad}
                    </div>
                    <!-- Línea 3: Notas -->
                    <div style="font-size: 0.84rem; color: var(--text-dark); background: #f9fafb; padding: 0.5rem 0.75rem; border-radius: 6px; border-left: 3px solid #0284c7;">
                        📝 <strong>Notas:</strong> ${r.notas || 'Sin notas adicionales'}
                    </div>
                </div>
            `;
        }).join('');
    } else if (moduloClave === 'ansiedad') {
        cardsHtml = pageRecords.map(r => {
            let sints = [];
            try { sints = JSON.parse(r.sintomas_json || '[]'); } catch(e){}
            const sintsBadges = sints.length > 0 ? sints.map(s => `<span class="badge" style="background:#f3f4f6; color:#374151; margin:2px;">${s}</span>`).join(' ') : 'Sin síntomas marcados';

            return `
                <div style="background: white; border: 1.5px solid var(--border-color); border-radius: 8px; padding: 0.85rem 1rem; display: flex; flex-direction: column; gap: 0.4rem; box-shadow: var(--shadow-sm); margin-bottom: 0.6rem;">
                    <!-- Línea 1: Fecha / Nivel Ansiedad -->
                    <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border-color); padding-bottom: 0.4rem; flex-wrap: wrap; gap: 0.4rem;">
                        <strong style="font-size: 0.9rem; color: var(--text-dark);">📅 Fecha: ${r.fecha}</strong>
                        <div><span class="badge" style="background:#fff7ed; color:#c2410c; font-weight:800;">⚡ Nivel: ${r.nivel_ansiedad} / 10</span></div>
                    </div>
                    <!-- Línea 2: Síntomas registrados -->
                    <div style="font-size: 0.84rem; color: var(--text-dark);">
                        ⚠️ <strong>Síntomas Físicos / Cognitivos:</strong> ${sintsBadges}
                    </div>
                    <!-- Línea 3: Situación desencadenante -->
                    <div style="font-size: 0.84rem; color: var(--text-dark); background: #f9fafb; padding: 0.5rem 0.75rem; border-radius: 6px; border-left: 3px solid #c2410c;">
                        🎯 <strong>Situación Desencadenante:</strong> ${r.situacion_desencadenante || 'Sin situación registrada'}
                    </div>
                </div>
            `;
        }).join('');
    } else if (moduloClave === 'ingesta') {
        cardsHtml = pageRecords.map(r => {
            let conds = [];
            try { conds = JSON.parse(r.conductas_json || '[]'); } catch(e){}
            const condsBadges = conds.length > 0 ? conds.map(c => `<span class="badge" style="background:#fef2f2; color:#b91c1c; font-weight:700; margin:2px;">⚠️ ${c}</span>`).join(' ') : '<span class="badge" style="background:#f0fdf4; color:#15803d; font-weight:700;">🟢 Ninguna</span>';

            return `
                <div style="background: white; border: 1.5px solid var(--border-color); border-radius: 8px; padding: 0.85rem 1rem; display: flex; flex-direction: column; gap: 0.4rem; box-shadow: var(--shadow-sm); margin-bottom: 0.6rem;">
                    <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border-color); padding-bottom: 0.4rem; flex-wrap: wrap; gap: 0.4rem;">
                        <strong style="font-size: 0.9rem; color: var(--text-dark);">📅 Fecha: ${r.fecha} - 🥗 ${r.tipo_comida || 'Comida'}</strong>
                        <div><span class="badge" style="background:#f0fdf4; color:#15803d; font-weight:700;">Apetito: ${r.apetito_previo}/10 | Saciedad: ${r.saciedad}/10</span></div>
                    </div>
                    <div style="font-size: 0.84rem; color: var(--text-dark);">
                        🍽️ <strong>Plato / Cantidades:</strong> ${r.descripcion_plato || 'Sin descripción'}
                    </div>
                    <div style="font-size: 0.84rem; color: var(--text-dark);">
                        📍 <strong>Dónde:</strong> ${r.contexto || 'Sin especificar'} | 💭 <strong>Sentimiento:</strong> ${r.afectividad || 'Sin especificar'}
                    </div>
                    <div style="font-size: 0.84rem; color: var(--text-dark); background: #f9fafb; padding: 0.5rem 0.75rem; border-radius: 6px; border-left: 3px solid #16a34a;">
                        🚨 <strong>Conductas problema:</strong> ${condsBadges}
                        ${r.pensamiento ? `<div style="margin-top:0.25rem; font-style:italic;">💭 <strong>Pensamiento negativo:</strong> "${r.pensamiento}"</div>` : ''}
                    </div>
                </div>
            `;
        }).join('');
    } else if (moduloClave === 'cognitivo') {
        cardsHtml = pageRecords.map(r => {
            return `
                <div style="background: white; border: 1.5px solid var(--border-color); border-radius: 8px; padding: 0.85rem 1rem; display: flex; flex-direction: column; gap: 0.4rem; box-shadow: var(--shadow-sm); margin-bottom: 0.6rem;">
                    <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border-color); padding-bottom: 0.4rem; flex-wrap: wrap; gap: 0.4rem;">
                        <strong style="font-size: 0.9rem; color: var(--text-dark);">📅 Fecha: ${r.fecha}</strong>
                        <div><span class="badge" style="background:#faf5ff; color:#7e22ce; font-weight:800;">⚡ Intensidad: ${r.intensidad_emocion}/10</span></div>
                    </div>
                    <div style="font-size: 0.84rem; color: var(--text-dark);">
                        🎯 <strong>Situación:</strong> ${r.situacion}
                    </div>
                    <div style="font-size: 0.84rem; color: var(--text-dark); background: #faf5ff; padding: 0.5rem 0.75rem; border-radius: 6px; border-left: 3px solid #7e22ce;">
                        💭 <strong>Pensamiento Automático:</strong> "${r.pensamiento}"
                    </div>
                    <div style="font-size: 0.84rem; color: var(--text-dark);">
                        ❤️ <strong>Emoción/Sensación:</strong> ${r.emocion_sensacion || 'N/A'} | 🏃‍♂️ <strong>Conducta:</strong> ${r.conducta || 'N/A'}
                    </div>
                </div>
            `;
        }).join('');
    }

    const paginationControls = totalPages > 1 ? `
        <div style="display: flex; justify-content: space-between; align-items: center; padding: 0.65rem 0.85rem; background: white; border: 1px solid var(--border-color); border-radius: 8px; margin-top: 0.5rem; flex-wrap: wrap; gap: 0.5rem;">
            <button type="button" class="btn btn-sm btn-outline-secondary" onclick="changePatientHistoryPage('${stateKey}', ${currentPage - 1})" ${currentPage <= 1 ? 'disabled' : ''} style="font-weight: 700; padding: 0.3rem 0.75rem;">
                ◀️ Anterior
            </button>
            <span style="font-size: 0.82rem; font-weight: 700; color: var(--text-dark);">
                Página ${currentPage} de ${totalPages} (${totalRecords} registros)
            </span>
            <button type="button" class="btn btn-sm btn-outline-secondary" onclick="changePatientHistoryPage('${stateKey}', ${currentPage + 1})" ${currentPage >= totalPages ? 'disabled' : ''} style="font-weight: 700; padding: 0.3rem 0.75rem;">
                Siguiente ▶️
            </button>
        </div>
    ` : `
        <div style="text-align: right; padding: 0.4rem 0.85rem; font-size: 0.78rem; color: var(--text-muted);">
            Mostrando ${totalRecords} registro(s)
        </div>
    `;

    const fullContentHtml = `
        <div style="margin-top: 0.5rem;">
            ${cardsHtml}
            ${paginationControls}
        </div>
    `;

    const container = document.getElementById(state.containerId);
    if (container) container.innerHTML = fullContentHtml;
}

function changePatientHistoryPage(stateKey, newPage) {
    if (patientHistoryState[stateKey]) {
        patientHistoryState[stateKey].page = newPage;
        renderPaginatedHistoryTable(stateKey);
    }
}

function openPatientToolHistoryModal(patientId, toolType) {
    const inlineId = `inline-history-acc-${patientId}-${toolType}`;
    const el = document.getElementById(inlineId);
    if (el) {
        toggleInlinePatientHistory(patientId, toolType, inlineId);
    } else {
        openTherapistModuleReport(toolType, '', patientId);
    }
}

function openSleepReportModal(targetPatientId) {
    openPatientToolHistoryModal(targetPatientId, 'sueno');
}

function openAnxietyReportModal(targetPatientId) {
    openPatientToolHistoryModal(targetPatientId, 'ansiedad');
}

function openConsumpionReportModal(targetPatientId) {
    openPatientToolHistoryModal(targetPatientId, 'sobriedad');
}

function openMedicationReportModal(targetPatientId) {
    openPatientToolHistoryModal(targetPatientId, 'adherencia');
}

function openBehavioralReportModal(targetPatientId) {
    openPatientToolHistoryModal(targetPatientId, 'activacion');
}

// A. Control del Acordeón Desplegable
document.addEventListener('click', function(e) {
    const accordionHeader = e.target.closest('.accordion-tool-header');
    if (accordionHeader) {
        e.preventDefault();
        const targetId = accordionHeader.getAttribute('data-target');
        const targetBody = document.getElementById(targetId);
        if (targetBody) {
            const isHidden = targetBody.classList.contains('hide') || targetBody.style.display === 'none';
            if (isHidden) {
                targetBody.classList.remove('hide');
                targetBody.style.display = 'block';
            } else {
                targetBody.classList.add('hide');
                targetBody.style.display = 'none';
            }
            const arrow = accordionHeader.querySelector('.accordion-arrow');
            if (arrow) {
                arrow.style.transform = isHidden ? 'rotate(180deg)' : 'rotate(0deg)';
            }
        }
    }
});

// B. Control de Apertura de Historial por Paciente y Herramienta
document.addEventListener('click', function(e) {
    const btn = e.target.closest('.btn-view-history') || e.target.closest('.btn-tool-report');
    if (btn) {
        e.preventDefault();
        e.stopPropagation();
        const patientId = btn.getAttribute('data-patient-id');
        const toolType = btn.getAttribute('data-tool');
        
        if (toolType) {
            openPatientToolHistoryModal(patientId, toolType);
        }
    }
});

async function onTherapistToolPatientSearch(query) {
    const dropdown = document.getElementById('tt-patient-dropdown');
    if (!dropdown) return;
    if (!query || query.trim().length < 1) {
        dropdown.classList.add('hide');
        dropdown.style.display = 'none';
        return;
    }
    const q = query.trim().toLowerCase();
    try {
        const res = await fetch('/api/patients');
        const patients = await res.json();
        const filtered = patients.filter(p => {
            const fullName = `${p.nombres || ''} ${p.apellidos || ''}`.toLowerCase();
            const cedula = (p.cedula || '').toLowerCase();
            return fullName.includes(q) || cedula.includes(q);
        });

        if (filtered.length === 0) {
            dropdown.innerHTML = '<div style="padding:0.75rem 1rem; font-size:0.88rem; color:var(--text-muted); background: white;">No se encontraron consultantes.</div>';
        } else {
            dropdown.innerHTML = filtered.map(p => {
                const fullName = `${p.nombres || ''} ${p.apellidos || ''}`.trim();
                const safeFullName = fullName.replace(/'/g, "");
                const cedula = p.cedula || '';
                return `
                <div class="search-result-item" onclick="selectPatientForTherapistTools(${p.id}, '${safeFullName}', '${cedula}')" style="padding:0.75rem 1rem; font-size:0.88rem; cursor:pointer; border-bottom:1px solid var(--border-color); background: white; color: var(--text-dark);">
                    <strong style="display:block; color: var(--text-dark);">👤 ${fullName}</strong>
                    <span style="color:var(--text-muted); font-size:0.78rem;">${p.cedula ? 'Cédula: ' + p.cedula : 'Sin Cédula'}</span>
                </div>`;
            }).join('');
        }
        dropdown.classList.remove('hide');
        dropdown.style.setProperty('display', 'block', 'important');
    } catch (err) {
        console.error('Error en búsqueda de pacientes para herramientas:', err);
    }
}

async function selectPatientForTherapistTools(id, name, code) {
    const searchInput = document.getElementById('tt-patient-search');
    if (searchInput) searchInput.value = name;
    
    const dropdown = document.getElementById('tt-patient-dropdown');
    if (dropdown) {
        dropdown.classList.add('hide');
        dropdown.style.display = 'none';
    }
    
    const nameEl = document.getElementById('tt-selected-patient-name');
    if (nameEl) nameEl.innerText = name;
    
    const codeEl = document.getElementById('tt-selected-patient-code');
    if (codeEl) codeEl.innerText = code ? `Cédula: ${code}` : 'Sin Cédula';
    
    const panel = document.getElementById('tt-patient-toggle-panel') || document.getElementById('tt-patient-details-panel');
    const list = document.getElementById('tt-patient-switches-list') || document.getElementById('tt-patient-modules-list');
    
    if (list) list.innerHTML = '<p class="text-muted">Cargando módulos asignados...</p>';
    if (panel) {
        panel.classList.remove('hide');
        panel.style.setProperty('display', 'block', 'important');
    }

    try {
        const res = await fetch(`/api/patients/${id}/modules`);
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Error al cargar módulos');

        if (list) {
            list.innerHTML = data.modules.map(m => {
                const btnText = toolButtonLabels[m.clave] || `📊 Ver Registro de ${m.nombre}`;
                const safeName = (name || '').replace(/'/g, "");
                const safeModName = (m.nombre || '').replace(/'/g, "");
                const inlineId = `inline-history-sel-${id}-${m.clave}`;
                const actBtn = (m.clave === 'activacion') ? `<button type="button" class="btn btn-sm btn-secondary" onclick="openTherapistActivationModal(${id}, '${safeName}')" style="padding: 0.35rem 0.65rem; font-weight: 600;">⚙️ Configurar Actividades</button>` : '';
                return `
                <div style="display: flex; flex-direction: column; width: 100%;">
                    <div style="display: flex; align-items: center; justify-content: space-between; padding: 0.75rem 1rem; background: var(--bg-light); border-radius: 6px; border: 1px solid var(--border-color); flex-wrap: wrap; gap: 0.5rem;">
                        <div>
                            <strong style="font-size: 0.92rem; color: var(--text-dark);">${m.nombre}</strong>
                            <span style="display: block; font-size: 0.8rem; color: var(--text-muted); margin-top: 2px;">
                                ${m.activo ? '🟢 Activo en portal del paciente' : '🔴 Desactivado'}
                            </span>
                        </div>
                        <div style="display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap;">
                            <button type="button" class="btn btn-sm btn-info" onclick="toggleInlinePatientHistory(${id}, '${m.clave}', '${inlineId}')" style="padding: 0.35rem 0.65rem; font-weight: 600;">${btnText}</button>
                            ${actBtn}
                            <button type="button" class="btn btn-sm ${m.activo ? 'btn-secondary' : 'btn-primary'}" onclick="togglePatientModuleBackend(${id}, '${m.clave}', ${m.activo ? 0 : 1})" style="padding: 0.35rem 0.75rem; font-weight: 700;">
                                ${m.activo ? ' Desactivar' : ' Activar'}
                            </button>
                        </div>
                    </div>
                    <div id="${inlineId}" class="inline-patient-history hide" style="display: none; margin-top: 0.5rem; width: 100%;"></div>
                </div>
                `;
            }).join('<div style="height: 0.5rem;"></div>');
        }
    } catch (err) {
        if (list) list.innerHTML = `<p class="text-danger">Error: ${err.message}</p>`;
    }
}

async function togglePatientModuleBackend(patientId, moduloClave, activoState) {
    try {
        const res = await fetch(`/api/patients/${patientId}/modules/toggle`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ modulo_clave: moduloClave, activo: activoState })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Error al actualizar');
        
        const name = document.getElementById('tt-selected-patient-name').innerText;
        const code = document.getElementById('tt-selected-patient-code').innerText.replace('Cédula: ', '');
        selectPatientForTherapistTools(patientId, name, code);
        loadTherapistToolsCatalog();
    } catch (err) {
        alert(err.message);
    }
}

async function openTherapistModuleReport(moduloClave, moduloNombre, targetPatientId) {
    console.log('[DEBUG] openTherapistModuleReport called with:', moduloClave, moduloNombre, targetPatientId);
    
    // Normalizar clave del módulo
    const claveMap = {
        'sueno': 'sueno',
        'ansiedad': 'ansiedad',
        'sobriedad': 'sobriedad',
        'consumo': 'sobriedad',
        'adherencia': 'adherencia',
        'medicacion': 'adherencia',
        'activacion': 'activacion'
    };
    moduloClave = claveMap[moduloClave] || moduloClave;

    openModal('therapist-tool-report-modal');
    const namesMap = {
        'sueno': 'Higiene del Sueño',
        'ansiedad': 'Diario de Ansiedad',
        'sobriedad': 'Registro de Consumo',
        'adherencia': 'Adherencia al Tratamiento',
        'activacion': 'Activación Conductual'
    };
    const titleText = moduloNombre || namesMap[moduloClave] || moduloClave;
    const titleEl = document.getElementById('ttr-modal-title');
    if (titleEl) titleEl.innerText = `📊 Reporte e Historial: ${titleText}`;
    
    const container = document.getElementById('ttr-modal-body-content');
    if (container) container.innerHTML = '<p class="text-muted text-center py-4">Cargando registros de consultantes...</p>';
    
    const modalEl = document.getElementById('therapist-tool-report-modal');
    if (modalEl) {
        modalEl.classList.remove('hide');
        modalEl.style.setProperty('display', 'flex', 'important');
        document.body.style.overflow = 'hidden';
    }

    try {
        const res = await fetch(`/api/therapist/modules/report/${moduloClave}`);
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Error al cargar reporte');

        if (!container) return;

        if (!data || data.length === 0) {
            container.innerHTML = '<div class="text-muted text-center py-5"><h4>📭 Sin registros</h4><p>Aún no hay datos reportados para esta herramienta.</p></div>';
            return;
        }

        // Agrupar registros por paciente
        const patientsMap = {};
        data.forEach(r => {
            const pId = r.paciente_id;
            if (!patientsMap[pId]) {
                patientsMap[pId] = {
                    id: pId,
                    name: `${r.nombres || ''} ${r.apellidos || ''}`.trim() || `Consultante #${pId}`,
                    cedula: r.cedula || '',
                    records: []
                };
            }
            patientsMap[pId].records.push(r);
        });

        let patientsList = Object.values(patientsMap);

        // Si se especificó un paciente objetivo, filtrar para mostrar su historial
        if (targetPatientId) {
            const filtered = patientsList.filter(p => p.id == targetPatientId);
            if (filtered.length > 0) {
                patientsList = filtered;
            }
        }

        if (patientsList.length === 0) {
            container.innerHTML = '<div class="text-muted text-center py-5"><h4>📭 Sin registros</h4><p>El consultante seleccionado aún no ha registrado datos para esta herramienta.</p></div>';
            return;
        }

        let html = `<div style="display: flex; flex-direction: column; gap: 1rem;">`;

        patientsList.forEach((p, idx) => {
            const recs = p.records;
            let summaryBadgesHtml = '';

            if (moduloClave === 'sobriedad') {
                const totalSobrio = recs.filter(r => r.sobrio === 1).length;
                const recaidas = recs.filter(r => r.sobrio === 0).length;
                let streak = 0;
                for (let r of recs) {
                    if (r.sobrio === 1) streak++;
                    else break;
                }
                summaryBadgesHtml = `
                    <span class="badge" style="background:#e0f2fe; color:#0369a1; font-weight:700; padding:0.4rem 0.6rem;">🏅 Racha: ${streak} día(s) sobrio</span>
                    <span class="badge" style="background:#f0fdf4; color:#15803d; font-weight:600; padding:0.4rem 0.6rem;">🟢 Días Libre: ${totalSobrio}</span>
                    ${recaidas > 0 ? `<span class="badge" style="background:#fef2f2; color:#b91c1c; font-weight:700; padding:0.4rem 0.6rem;">⚠️ Recaídas/Eventos: ${recaidas}</span>` : ''}
                `;
            } else if (moduloClave === 'sueno') {
                const totalNoches = recs.length;
                const descansoRestful = recs.filter(r => r.senti_descanso === 1).length;
                const despertares = recs.filter(r => r.desperto_noche === 1).length;
                summaryBadgesHtml = `
                    <span class="badge" style="background:#f3e8ff; color:#6b21a8; font-weight:700; padding:0.4rem 0.6rem;">🌙 Descanso Reparador: ${descansoRestful} / ${totalNoches} noches</span>
                    <span class="badge" style="background:#eff6ff; color:#1d4ed8; font-weight:600; padding:0.4rem 0.6rem;">🥱 Noches con despertares: ${despertares}</span>
                `;
            } else if (moduloClave === 'adherencia') {
                const tomados = recs.filter(r => r.tomado === 1).length;
                const noTomados = recs.filter(r => r.tomado === 0).length;
                const pct = recs.length > 0 ? Math.round((tomados / recs.length) * 100) : 0;
                summaryBadgesHtml = `
                    <span class="badge" style="background:${pct >= 80 ? '#f0fdf4' : '#fff7ed'}; color:${pct >= 80 ? '#15803d' : '#c2410c'}; font-weight:800; padding:0.4rem 0.6rem;">💊 ${pct}% Adherencia</span>
                    <span class="badge" style="background:#f0fdf4; color:#15803d; font-weight:600; padding:0.4rem 0.6rem;">🟢 Tomados: ${tomados}</span>
                    ${noTomados > 0 ? `<span class="badge" style="background:#fef2f2; color:#b91c1c; font-weight:700; padding:0.4rem 0.6rem;">🔴 No Tomados: ${noTomados}</span>` : ''}
                `;
            } else if (moduloClave === 'activacion') {
                const necCount = recs.filter(r => r.categoria === 'necesaria' && r.completada === 1).length;
                const placCount = recs.filter(r => r.categoria === 'placer' && r.completada === 1).length;
                const cotCount = recs.filter(r => r.categoria === 'cotidiana' && r.completada === 1).length;
                summaryBadgesHtml = `
                    <span class="badge" style="background:#f0fdf4; color:#166534; font-weight:700; padding:0.4rem 0.6rem;">📌 Necesarias: ${necCount}</span>
                    <span class="badge" style="background:#fdf4ff; color:#86198f; font-weight:700; padding:0.4rem 0.6rem;">🎉 Placenteras: ${placCount}</span>
                    <span class="badge" style="background:#eff6ff; color:#1e40af; font-weight:700; padding:0.4rem 0.6rem;">🏠 Cotidiana: ${cotCount}</span>
                `;
            } else if (moduloClave === 'ansiedad') {
                const totalAns = recs.reduce((sum, r) => sum + (Number(r.nivel_ansiedad) || 0), 0);
                const avgAns = (totalAns / recs.length).toFixed(1);
                
                const symptomFreq = {};
                recs.forEach(r => {
                    let sints = [];
                    try { sints = JSON.parse(r.sintomas_json || '[]'); } catch(e){}
                    sints.forEach(s => { symptomFreq[s] = (symptomFreq[s] || 0) + 1; });
                });
                
                let topSymptom = '-';
                let maxF = 0;
                Object.keys(symptomFreq).forEach(s => {
                    if (symptomFreq[s] > maxF) {
                        maxF = symptomFreq[s];
                        topSymptom = s;
                    }
                });

                summaryBadgesHtml = `
                    <span class="badge" style="background:#fff7ed; color:#c2410c; font-weight:800; padding:0.4rem 0.6rem;">⚡ Promedio Ansiedad: ${avgAns} / 10</span>
                    ${maxF > 0 ? `<span class="badge" style="background:#fef2f2; color:#991b1b; font-weight:700; padding:0.4rem 0.6rem;">⚠️ Síntoma frecuente: ${topSymptom}</span>` : ''}
                `;
            }

            let detailHeaders = '';
            let detailTableRows = '';

            if (moduloClave === 'sobriedad') {
                detailHeaders = `<th>📅 Fecha</th><th>Estado</th><th>Craving (1-10)</th><th>Disparador Emocional</th><th>Notas</th>`;
                detailTableRows = recs.map(r => `
                    <tr style="border-bottom: 1px solid var(--border-color);">
                        <td style="padding: 0.6rem;"><strong>📅 ${r.fecha}</strong></td>
                        <td style="padding: 0.6rem;">${r.sobrio ? '🟢 Libre de consumo' : '⚠️ Consumo / Recaída'}</td>
                        <td style="padding: 0.6rem;">${r.nivel_ansiedad !== null && r.nivel_ansiedad !== undefined ? `<span class="badge" style="background:#fff7ed; color:#c2410c; font-weight:800;">${r.nivel_ansiedad} / 10</span>` : '-'}</td>
                        <td style="padding: 0.6rem;">${r.disparador_emocional || '-'}</td>
                        <td style="padding: 0.6rem;">${r.notas || '-'}</td>
                    </tr>
                `).join('');
            } else if (moduloClave === 'sueno') {
                detailHeaders = `<th>📅 Fecha</th><th>Horario Sueño</th><th>¿Descansó?</th><th>Despertares</th><th>Síntomas Día</th><th>Detalles Día & Conciliación</th>`;
                detailTableRows = recs.map(r => `
                    <tr style="border-bottom: 1px solid var(--border-color);">
                        <td style="padding: 0.6rem;"><strong>📅 ${r.fecha}</strong></td>
                        <td style="padding: 0.6rem;">${r.hora_dormi || ''} - ${r.hora_desperto || ''}</td>
                        <td style="padding: 0.6rem;">${r.senti_descanso ? '🟢 Reparador' : '🔴 No reparador'}</td>
                        <td style="padding: 0.6rem;">${r.desperto_noche ? `Sí (${r.cant_despertares || 1} veces)` : 'No'}</td>
                        <td style="padding: 0.6rem;">
                            ${r.somnolencia_dia ? '🥱 Somnolencia ' : ''}${r.pesadez_dia ? '🪨 Pesadez ' : ''}${r.agotamiento_dia ? '🔋 Agotamiento' : ''}
                        </td>
                        <td style="padding: 0.6rem; font-size: 0.8rem; max-width: 220px;">
                            ${r.proceso_dormir ? `<div><strong>Conciliación:</strong> ${r.proceso_dormir}</div>` : ''}
                            ${r.situaciones_dia ? `<div><strong>Situaciones:</strong> ${r.situaciones_dia}</div>` : ''}
                            ${r.emociones_dia ? `<div><strong>Emociones:</strong> ${r.emociones_dia}</div>` : ''}
                        </td>
                    </tr>
                `).join('');
            } else if (moduloClave === 'adherencia') {
                detailHeaders = `<th>📅 Fecha</th><th>Medicamento</th><th>Dosis / Prescripción</th><th>Estado Toma</th><th>Hora Real</th><th>Notas</th>`;
                detailTableRows = recs.map(r => `
                    <tr style="border-bottom: 1px solid var(--border-color);">
                        <td style="padding: 0.6rem;"><strong>📅 ${r.fecha}</strong></td>
                        <td style="padding: 0.6rem;"><strong>💊 ${r.nombre_medicamento}</strong></td>
                        <td style="padding: 0.6rem;">${r.dosis || '-'} (${r.hora_prescrita || '-'})</td>
                        <td style="padding: 0.6rem;">${r.tomado ? '🟢 Tomado' : '🔴 No tomado'}</td>
                        <td style="padding: 0.6rem;">${r.hora_tomado || '-'}</td>
                        <td style="padding: 0.6rem;">${r.notas || '-'}</td>
                    </tr>
                `).join('');
            } else if (moduloClave === 'activacion') {
                detailHeaders = `<th>📅 Fecha</th><th>Categoría</th><th>Actividad</th><th>Estado</th><th>Notas</th>`;
                detailTableRows = recs.map(r => {
                    let catLabel = r.categoria === 'necesaria' ? '📌 Necesaria' : (r.categoria === 'placer' ? '🎉 Disfrute/Placer' : '🏠 Cotidiana');
                    return `
                        <tr style="border-bottom: 1px solid var(--border-color);">
                            <td style="padding: 0.6rem;"><strong>📅 ${r.fecha}</strong></td>
                            <td style="padding: 0.6rem;">${catLabel}</td>
                            <td style="padding: 0.6rem;"><strong>${r.nombre_actividad}</strong></td>
                            <td style="padding: 0.6rem;">${r.completada ? '🟢 Completada' : '⚪ Pendiente'}</td>
                            <td style="padding: 0.6rem;">${r.notas || '-'}</td>
                        </tr>
                    `;
                }).join('');
            } else if (moduloClave === 'ansiedad') {
                detailHeaders = `<th>📅 Fecha</th><th>Nivel Ansiedad</th><th>Síntomas Registrados</th><th>Situación Desencadenante</th>`;
                detailTableRows = recs.map(r => {
                    let sints = [];
                    try { sints = JSON.parse(r.sintomas_json || '[]'); } catch(e){}
                    return `
                        <tr style="border-bottom: 1px solid var(--border-color);">
                            <td style="padding: 0.6rem;"><strong>📅 ${r.fecha}</strong></td>
                            <td style="padding: 0.6rem;"><span class="badge" style="background:#fff7ed; color:#c2410c; font-weight:800;">${r.nivel_ansiedad} / 10</span></td>
                            <td style="padding: 0.6rem; max-width: 250px;">${sints.length > 0 ? sints.map(s => `<span class="badge" style="background:#f3f4f6; color:#374151; margin:2px;">${s}</span>`).join(' ') : 'Sin síntomas marcados'}</td>
                            <td style="padding: 0.6rem;">${r.situacion_desencadenante || '-'}</td>
                        </tr>
                    `;
                }).join('');
            }

            // Desplegar siempre abierto el historial por consultante
            const isExpanded = true;

            html += `
                <div class="card" style="border: 1.5px solid var(--border-color); border-radius: 8px; overflow: hidden; background: white; margin-bottom: 1rem;">
                    <div style="padding: 1rem; background: var(--bg-light); display: flex; flex-direction: column; gap: 0.5rem; border-bottom: 1px solid var(--border-color);">
                        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.5rem;">
                            <div>
                                <h4 style="margin: 0; color: var(--text-dark); font-family: var(--font-title); font-size: 1.05rem;">
                                    👤 ${p.name} <span style="font-size: 0.82rem; color: var(--text-muted); font-weight: normal;">(${p.cedula ? 'Cédula: ' + p.cedula : 'Sin Cédula'})</span>
                                </h4>
                            </div>
                            <span class="badge" style="background: rgba(126, 34, 206, 0.1); color: #7e22ce; font-weight: 700;">
                                Total Registros: ${recs.length}
                            </span>
                        </div>
                        <div style="display: flex; gap: 0.4rem; flex-wrap: wrap; align-items: center; margin-top: 0.25rem;">
                            ${summaryBadgesHtml}
                        </div>
                    </div>
                    <div id="ttr-patient-body-${p.id}" style="padding: 0.75rem; display: block; overflow-x: auto;">
                        <table class="table" style="width: 100%; border-collapse: collapse; font-size: 0.85rem;">
                            <thead>
                                <tr style="border-bottom: 2px solid var(--border-color); text-align: left; background: #f9fafb;">
                                    ${detailHeaders}
                                </tr>
                            </thead>
                            <tbody>
                                ${detailTableRows}
                            </tbody>
                        </table>
                    </div>
                </div>
            `;
        });

        html += `</div>`;
        container.innerHTML = html;

    } catch (err) {
        if (container) container.innerHTML = `<p class="text-danger">Error al cargar reporte: ${err.message}</p>`;
    }
}

window.toggleTtrPatientDetails = function(patId) {
    const el = document.getElementById(`ttr-patient-body-${patId}`);
    const icon = document.getElementById(`ttr-patient-icon-${patId}`);
    if (el) {
        const isHidden = el.style.display === 'none' || el.classList.contains('hide');
        if (isHidden) {
            el.classList.remove('hide');
            el.style.display = 'block';
            if (icon) icon.innerText = '🔼';
        } else {
            el.classList.add('hide');
            el.style.display = 'none';
            if (icon) icon.innerText = '🔽';
        }
    }
};

window.openTherapistModuleReport = openTherapistModuleReport;
window.openPatientToolHistoryModal = openPatientToolHistoryModal;
window.openSleepReportModal = openSleepReportModal;
window.openAnxietyReportModal = openAnxietyReportModal;
window.openConsumpionReportModal = openConsumpionReportModal;
window.openConsumptionReportModal = openConsumpionReportModal;
window.openMedicationReportModal = openMedicationReportModal;
window.openBehavioralReportModal = openBehavioralReportModal;
window.loadTherapistToolsCatalog = loadTherapistToolsCatalog;
window.onTherapistToolPatientSearch = onTherapistToolPatientSearch;
window.selectPatientForTherapistTools = selectPatientForTherapistTools;
window.togglePatientModuleBackend = togglePatientModuleBackend;

// --- PORTAL PACIENTE HANDLERS ---

async function checkPatientActiveModulesNav() {
    try {
        const res = await fetch('/api/patient/active-modules');
        if (!res.ok) return;
        const data = await res.json();
        const activeKeys = data.active_modules || [];
        
        document.querySelectorAll('.pat-mod-item').forEach(el => {
            const modKey = el.getAttribute('data-mod-key');
            if (activeKeys.includes(modKey)) {
                el.classList.remove('hide');
            } else {
                el.classList.add('hide');
            }
        });
    } catch (err) {
        console.error(err);
    }
}

// 1. Sueño
async function submitPatientSleepLog(e) {
    e.preventDefault();
    const status = document.getElementById('patient-sleep-status');
    status.classList.add('hide');

    const payload = {
        fecha: document.getElementById('sleep-fecha').value,
        hora_dormi: document.getElementById('sleep-hora-dormi').value,
        hora_desperto: document.getElementById('sleep-hora-desperto').value,
        situaciones_dia: document.getElementById('sleep-situaciones').value,
        emociones_dia: document.getElementById('sleep-emociones').value,
        proceso_dormir: document.getElementById('sleep-proceso').value,
        desperto_noche: document.getElementById('sleep-desperto-noche').value === '1',
        cant_despertares: parseInt(document.getElementById('sleep-cant-despertares').value || '0'),
        senti_descanso: document.getElementById('sleep-senti-descanso').value === '1',
        somnolencia_dia: document.getElementById('sleep-somnolencia').checked,
        pesadez_dia: document.getElementById('sleep-pesadez').checked,
        agotamiento_dia: document.getElementById('sleep-agotamiento').checked
    };

    try {
        const res = await fetch('/api/patient/sleep/log', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Error al guardar');

        status.innerText = '✅ Registro de sueño guardado exitosamente.';
        status.className = 'status-msg success-msg mt-3';
        loadPatientSleepHistory();
    } catch (err) {
        status.innerText = `⚠️ ${err.message}`;
        status.className = 'status-msg error-msg mt-3';
    }
}

async function loadPatientSleepHistory() {
    const list = document.getElementById('patient-sleep-history-list');
    if (!list) return;
    try {
        const res = await fetch('/api/patient/sleep/history');
        const data = await res.json();
        if (data.length === 0) {
            list.innerHTML = '<p class="text-muted text-center py-3">No tienes registros de sueño guardados aún.</p>';
            return;
        }

        list.innerHTML = `
            <table class="table" style="width: 100%; border-collapse: collapse; font-size: 0.85rem;">
                <thead>
                    <tr style="border-bottom: 2px solid var(--border-color); text-align: left;">
                        <th style="padding: 0.5rem;">Fecha</th>
                        <th style="padding: 0.5rem;">Horario</th>
                        <th style="padding: 0.5rem;">Sensación Descanso</th>
                        <th style="padding: 0.5rem;">Despertares</th>
                    </tr>
                </thead>
                <tbody>
                    ${data.map(r => `
                        <tr style="border-bottom: 1px solid var(--border-color);">
                            <td style="padding: 0.5rem;"><strong>${r.fecha}</strong></td>
                            <td style="padding: 0.5rem;">${r.hora_dormi || ''} - ${r.hora_desperto || ''}</td>
                            <td style="padding: 0.5rem;">${r.senti_descanso ? '🟢 Descansado' : '🔴 Fatigado'}</td>
                            <td style="padding: 0.5rem;">${r.desperto_noche ? `Sí (${r.cant_despertares || 1})` : 'No'}</td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        `;
    } catch (err) {
        list.innerHTML = `<p class="text-danger">Error: ${err.message}</p>`;
    }
}

// 2. Ansiedad
async function submitPatientAnxietyLog(e) {
    e.preventDefault();
    const status = document.getElementById('patient-anxiety-status');
    status.classList.add('hide');

    const cbs = document.querySelectorAll('.anx-sintoma-cb:checked');
    const sintomas = Array.from(cbs).map(cb => cb.value);

    const payload = {
        fecha: document.getElementById('anx-fecha').value,
        nivel_ansiedad: parseInt(document.getElementById('anx-nivel').value),
        sintomas: sintomas,
        situacion_desencadenante: document.getElementById('anx-situacion').value
    };

    try {
        const res = await fetch('/api/patient/anxiety/log', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Error al guardar');

        status.innerText = '✅ Registro de ansiedad guardado exitosamente.';
        status.className = 'status-msg success-msg mt-3';
        loadPatientAnxietyHistory();
    } catch (err) {
        status.innerText = `⚠️ ${err.message}`;
        status.className = 'status-msg error-msg mt-3';
    }
}

async function loadPatientAnxietyHistory() {
    const list = document.getElementById('patient-anxiety-history-list');
    if (!list) return;
    try {
        const res = await fetch('/api/patient/anxiety/history');
        const data = await res.json();
        if (data.length === 0) {
            list.innerHTML = '<p class="text-muted text-center py-3">No tienes registros de ansiedad aún.</p>';
            return;
        }

        list.innerHTML = `
            <table class="table" style="width: 100%; border-collapse: collapse; font-size: 0.85rem;">
                <thead>
                    <tr style="border-bottom: 2px solid var(--border-color); text-align: left;">
                        <th style="padding: 0.5rem;">Fecha</th>
                        <th style="padding: 0.5rem;">Nivel (1-10)</th>
                        <th style="padding: 0.5rem;">Síntomas</th>
                        <th style="padding: 0.5rem;">Situación</th>
                    </tr>
                </thead>
                <tbody>
                    ${data.map(r => {
                        let sints = [];
                        try { sints = JSON.parse(r.sintomas_json || '[]'); } catch(e){}
                        return `
                            <tr style="border-bottom: 1px solid var(--border-color);">
                                <td style="padding: 0.5rem;"><strong>${r.fecha}</strong></td>
                                <td style="padding: 0.5rem;"><span class="badge" style="background:#fff7ed; color:#c2410c; font-weight:800;">${r.nivel_ansiedad}/10</span></td>
                                <td style="padding: 0.5rem; max-width: 250px;">${sints.join(', ') || 'Ninguno'}</td>
                                <td style="padding: 0.5rem;">${r.situacion_desencadenante || '-'}</td>
                            </tr>
                        `;
                    }).join('')}
                </tbody>
            </table>
        `;
    } catch (err) {
        list.innerHTML = `<p class="text-danger">Error: ${err.message}</p>`;
    }
}

// 3. Sobriedad / Consumo
async function submitPatientSobrietyLog(e) {
    e.preventDefault();
    const status = document.getElementById('patient-sobriety-status');
    status.classList.add('hide');

    const payload = {
        fecha: document.getElementById('sob-fecha').value,
        sobrio: document.getElementById('sob-estado').value === '1',
        disparador_emocional: document.getElementById('sob-disparador').value,
        notas: document.getElementById('sob-notas').value
    };

    try {
        const res = await fetch('/api/patient/sobriety/checkin', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Error al guardar');

        status.innerText = '✅ Check-in de consumo guardado.';
        status.className = 'status-msg success-msg mt-3';
        document.getElementById('sobriety-streak-count').innerText = `${data.streak} Días`;
        loadPatientSobrietyHistory();
    } catch (err) {
        status.innerText = `⚠️ ${err.message}`;
        status.className = 'status-msg error-msg mt-3';
    }
}

async function loadPatientSobrietyHistory() {
    const list = document.getElementById('patient-sobriety-history-list');
    if (!list) return;
    try {
        const res = await fetch('/api/patient/sobriety/history');
        const data = await res.json();
        
        document.getElementById('sobriety-streak-count').innerText = `${data.streak || 0} Días`;

        const history = data.history || [];
        if (history.length === 0) {
            list.innerHTML = '<p class="text-muted text-center py-3">No tienes registros de consumo aún.</p>';
            return;
        }

        list.innerHTML = `
            <table class="table" style="width: 100%; border-collapse: collapse; font-size: 0.85rem;">
                <thead>
                    <tr style="border-bottom: 2px solid var(--border-color); text-align: left;">
                        <th style="padding: 0.5rem;">Fecha</th>
                        <th style="padding: 0.5rem;">Estado</th>
                        <th style="padding: 0.5rem;">Disparador</th>
                        <th style="padding: 0.5rem;">Notas</th>
                    </tr>
                </thead>
                <tbody>
                    ${history.map(r => `
                        <tr style="border-bottom: 1px solid var(--border-color);">
                            <td style="padding: 0.5rem;"><strong>${r.fecha}</strong></td>
                            <td style="padding: 0.5rem;">${r.sobrio ? '✓ Libre de consumo' : '⚠️ Consumo registrado'}</td>
                            <td style="padding: 0.5rem;">${r.disparador_emocional || '-'}</td>
                            <td style="padding: 0.5rem;">${r.notas || '-'}</td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        `;
    } catch (err) {
        list.innerHTML = `<p class="text-danger">Error: ${err.message}</p>`;
    }
}

window.loadTherapistToolsCatalog = loadTherapistToolsCatalog;
window.onTherapistToolPatientSearch = onTherapistToolPatientSearch;
window.selectPatientForTherapistTools = selectPatientForTherapistTools;
window.togglePatientModuleBackend = togglePatientModuleBackend;
window.checkPatientActiveModulesNav = checkPatientActiveModulesNav;
window.submitPatientSleepLog = submitPatientSleepLog;
window.loadPatientSleepHistory = loadPatientSleepHistory;
window.submitPatientAnxietyLog = submitPatientAnxietyLog;
window.loadPatientAnxietyHistory = loadPatientAnxietyHistory;
window.submitPatientSobrietyLog = submitPatientSobrietyLog;
window.loadPatientSobrietyHistory = loadPatientSobrietyHistory;

// --- AUTO-SET TODAY'S DATE IN THERAPEUTIC TOOLS FORMS ---
function setDefaultToolDates() {
    const now = new Date();
    const today = now.toISOString().split('T')[0];
    const nowLocal = new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 16);

    ['sleep-fecha', 'anx-fecha', 'sob-fecha', 'adh-fecha', 'act-fecha'].forEach(id => {
        const input = document.getElementById(id);
        if (input && !input.value) {
            input.value = today;
        }
    });

    ['ingesta-fecha', 'cog-fecha'].forEach(id => {
        const input = document.getElementById(id);
        if (input && !input.value) {
            input.value = nowLocal;
        }
    });
}
window.setDefaultToolDates = setDefaultToolDates;

// ==========================================
// MÓDULO PACIENTE: ADHERENCIA AL TRATAMIENTO (MEDICACIÓN)
// ==========================================

function openAddMedicationModal() {
    document.getElementById('add-medication-form')?.reset();
    openModal('add-medication-modal');
}

async function submitAddMedication(e) {
    e.preventDefault();
    const nombre = document.getElementById('med-nombre').value;
    const dosis = document.getElementById('med-dosis').value;
    const hora = document.getElementById('med-hora').value;

    try {
        const res = await fetch('/api/patient/adherence/medications', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ nombre_medicamento: nombre, dosis: dosis, hora_prescrita: hora })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Error al guardar medicamento');

        closeModal('add-medication-modal');
        loadPatientMedications();
        const today = document.getElementById('adh-fecha')?.value || new Date().toISOString().split('T')[0];
        loadPatientAdherenceChecklist(today);
    } catch (err) {
        alert(err.message);
    }
}

async function deletePatientAdherenceMedication(medId) {
    if (!confirm('¿Deseas eliminar este medicamento de tus medicamentos registrados?')) return;
    try {
        const res = await fetch(`/api/patient/adherence/medications/${medId}`, { method: 'DELETE' });
        if (!res.ok) throw new Error('Error al eliminar medicamento');
        loadPatientMedications();
        const today = document.getElementById('adh-fecha')?.value || new Date().toISOString().split('T')[0];
        loadPatientAdherenceChecklist(today);
    } catch (err) {
        alert(err.message);
    }
}

async function loadPatientMedications() {
    const list = document.getElementById('patient-medications-list');
    if (!list) return;
    try {
        const res = await fetch('/api/patient/adherence/medications');
        const data = await res.json();
        if (data.length === 0) {
            list.innerHTML = '<p class="text-muted">No tienes medicamentos registrados aún. Haz clic en <strong>"+ Agregar otro medicamento"</strong> para empezar.</p>';
            return;
        }

        list.innerHTML = `
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 0.75rem;">
                ${data.map(m => `
                    <div style="background: #f8fafc; border: 1.5px solid var(--border-color); padding: 0.75rem; border-radius: 8px; display: flex; justify-content: space-between; align-items: center;">
                        <div>
                            <strong style="color: #0284c7; font-size: 0.95rem;">💊 ${m.nombre_medicamento}</strong>
                            <span style="display: block; font-size: 0.8rem; color: var(--text-muted);">
                                ${m.dosis ? `Dosis: ${m.dosis}` : ''} ${m.hora_prescrita ? `(${m.hora_prescrita} hs)` : ''}
                            </span>
                        </div>
                        <button type="button" class="btn btn-sm btn-secondary" onclick="deletePatientAdherenceMedication(${m.id})" style="color: #dc2626; border: none; font-weight: 700;">✕</button>
                    </div>
                `).join('')}
            </div>
        `;
    } catch (err) {
        list.innerHTML = `<p class="text-danger">Error: ${err.message}</p>`;
    }
}

async function loadPatientAdherenceChecklist(dateStr) {
    const container = document.getElementById('adh-checklist-container');
    if (!container) return;
    if (!dateStr) {
        dateStr = new Date().toISOString().split('T')[0];
        const fechaInput = document.getElementById('adh-fecha');
        if (fechaInput) fechaInput.value = dateStr;
    }

    try {
        const res = await fetch(`/api/patient/adherence/checklist?fecha=${dateStr}`);
        const data = await res.json();
        if (data.length === 0) {
            container.innerHTML = '<div class="alert alert-info" style="background: #f0f9ff; border-color: #bae6fd; color: #0369a1; padding: 0.85rem; border-radius: 8px;">No tienes medicamentos agregados en tu lista. Presiona "+ Agregar otro medicamento" arriba para añadirlos.</div>';
            return;
        }

        container.innerHTML = `
            <div style="display: flex; flex-direction: column; gap: 0.85rem;">
                ${data.map(m => `
                    <div style="background: #fafafa; border: 1.5px solid var(--border-color); border-radius: 8px; padding: 0.85rem;">
                        <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 0.5rem; margin-bottom: 0.5rem;">
                            <label style="display: flex; align-items: center; gap: 0.65rem; font-weight: 700; font-size: 0.95rem; cursor: pointer; color: #0f172a; margin: 0;">
                                <input type="checkbox" class="adh-item-cb" data-med-id="${m.id}" ${m.tomado ? 'checked' : ''} style="width: 20px; height: 20px; accent-color: #0284c7;">
                                <span>💊 ${m.nombre_medicamento} ${m.dosis ? `(${m.dosis})` : ''}</span>
                            </label>
                            <span style="font-size: 0.82rem; font-weight: 600; color: #0284c7; background: #e0f2fe; padding: 0.25rem 0.5rem; border-radius: 4px;">
                                Prescrito: ${m.hora_prescrita || 'Cualquier hora'}
                            </span>
                        </div>
                        <div style="display: flex; gap: 0.75rem; align-items: center; flex-wrap: wrap;">
                            <div style="font-size: 0.82rem; font-weight: 600; color: var(--text-muted);">
                                Hora real de toma:
                                <input type="time" class="adh-item-hora" data-med-id="${m.id}" value="${m.hora_tomado || ''}" style="padding: 0.25rem 0.4rem; border-radius: 4px; border: 1px solid var(--border-color); font-size: 0.82rem; margin-left: 0.35rem;">
                            </div>
                        </div>
                    </div>
                `).join('')}
            </div>
        `;
    } catch (err) {
        container.innerHTML = `<p class="text-danger">Error: ${err.message}</p>`;
    }
}

async function submitPatientAdherenceLog(e) {
    e.preventDefault();
    const status = document.getElementById('patient-adherence-status');
    if (status) status.classList.add('hide');

    const fecha = document.getElementById('adh-fecha').value;
    const cbs = document.querySelectorAll('.adh-item-cb');
    const items = Array.from(cbs).map(cb => {
        const medId = cb.getAttribute('data-med-id');
        const horaInput = document.querySelector(`.adh-item-hora[data-med-id="${medId}"]`);
        return {
            medicamento_id: parseInt(medId),
            tomado: cb.checked,
            hora_tomado: horaInput ? horaInput.value : ''
        };
    });

    try {
        const res = await fetch('/api/patient/adherence/log', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ fecha, registros: items })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Error al guardar registro');

        if (status) {
            status.innerText = '✅ Registro de adherencia a medicamentos guardado exitosamente.';
            status.className = 'status-msg success-msg mt-3';
        }
        loadPatientAdherenceHistory();
    } catch (err) {
        if (status) {
            status.innerText = `⚠️ ${err.message}`;
            status.className = 'status-msg error-msg mt-3';
        }
    }
}

async function loadPatientAdherenceHistory() {
    const list = document.getElementById('patient-adherence-history-list');
    if (!list) return;
    try {
        const res = await fetch('/api/patient/adherence/history');
        const data = await res.json();
        if (data.length === 0) {
            list.innerHTML = '<p class="text-muted text-center py-3">No tienes registros de medicación guardados aún.</p>';
            return;
        }

        list.innerHTML = `
            <table class="table" style="width: 100%; border-collapse: collapse; font-size: 0.85rem;">
                <thead>
                    <tr style="border-bottom: 2px solid var(--border-color); text-align: left;">
                        <th style="padding: 0.5rem;">Fecha</th>
                        <th style="padding: 0.5rem;">Medicamento</th>
                        <th style="padding: 0.5rem;">Estado</th>
                        <th style="padding: 0.5rem;">Hora Toma Real</th>
                    </tr>
                </thead>
                <tbody>
                    ${data.map(r => `
                        <tr style="border-bottom: 1px solid var(--border-color);">
                            <td style="padding: 0.5rem;"><strong>${r.fecha}</strong></td>
                            <td style="padding: 0.5rem;">💊 ${r.nombre_medicamento} ${r.dosis ? `(${r.dosis})` : ''}</td>
                            <td style="padding: 0.5rem;">${r.tomado ? '🟢 Tomado' : '🔴 No tomado'}</td>
                            <td style="padding: 0.5rem;">${r.hora_tomado || '-'}</td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        `;
    } catch (err) {
        list.innerHTML = `<p class="text-danger">Error: ${err.message}</p>`;
    }
}

function openPatientAdherenceView() {
    setDefaultToolDates();
    loadPatientMedications();
    const today = document.getElementById('adh-fecha')?.value || new Date().toISOString().split('T')[0];
    loadPatientAdherenceChecklist(today);
    loadPatientAdherenceHistory();
    switchPatientView('patient-adherence');
}

window.openAddMedicationModal = openAddMedicationModal;
window.submitAddMedication = submitAddMedication;
window.deletePatientAdherenceMedication = deletePatientAdherenceMedication;
window.loadPatientMedications = loadPatientMedications;
window.loadPatientAdherenceChecklist = loadPatientAdherenceChecklist;
window.submitPatientAdherenceLog = submitPatientAdherenceLog;
window.loadPatientAdherenceHistory = loadPatientAdherenceHistory;
window.openPatientAdherenceView = openPatientAdherenceView;

// ==========================================
// MÓDULO PACIENTE Y PSICÓLOGO: ACTIVACIÓN CONDUCTUAL
// ==========================================

function openTherapistActivationModal(patientId, patientName) {
    document.getElementById('tam-patient-id').value = patientId;
    document.getElementById('tam-title').innerText = `🏃‍♂️ Configurar Activación Conductual: ${patientName || ''}`;
    document.getElementById('tam-add-activity-form')?.reset();
    loadTherapistActivationActivities(patientId);
    openModal('therapist-activation-modal');
}

async function loadTherapistActivationActivities(patientId) {
    const list = document.getElementById('tam-assigned-activities-list');
    if (!list) return;
    list.innerHTML = '<p class="text-muted">Cargando actividades del consultante...</p>';
    try {
        const res = await fetch(`/api/therapist/activation/activities/${patientId}`);
        const data = await res.json();
        if (data.length === 0) {
            list.innerHTML = '<p class="text-muted text-center py-2">No hay actividades asignadas aún a este consultante.</p>';
            return;
        }

        list.innerHTML = data.map(act => {
            let catBadge = act.categoria === 'necesaria' ? '📌 Necesaria' : (act.categoria === 'placer' ? '🎉 Placer/Disfrute' : '🏠 Cotidiana');
            return `
                <div style="background: white; border: 1px solid var(--border-color); padding: 0.65rem 0.85rem; border-radius: 6px; display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <strong style="font-size: 0.9rem;">${act.nombre_actividad}</strong>
                        <span style="display: inline-block; margin-left: 0.5rem; font-size: 0.75rem; padding: 0.15rem 0.4rem; background: #f1f5f9; border-radius: 4px; font-weight: 600;">
                            ${catBadge}
                        </span>
                    </div>
                    <button type="button" class="btn btn-sm ${act.activa ? 'btn-secondary' : 'btn-primary'}" onclick="toggleActivationActivity(${act.id}, ${act.activa ? 0 : 1})" style="padding: 0.25rem 0.6rem; font-size: 0.8rem; font-weight: 700;">
                        ${act.activa ? 'Desactivar' : 'Activar'}
                    </button>
                </div>
            `;
        }).join('');
    } catch (err) {
        list.innerHTML = `<p class="text-danger">Error: ${err.message}</p>`;
    }
}

async function submitTherapistAddActivationActivity(e) {
    e.preventDefault();
    const patientId = document.getElementById('tam-patient-id').value;
    const categoria = document.getElementById('tam-categoria').value;
    const nombre = document.getElementById('tam-nombre').value;

    try {
        const res = await fetch('/api/therapist/activation/activities', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ paciente_id: patientId, categoria: categoria, nombre_actividad: nombre })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Error al agregar actividad');

        document.getElementById('tam-nombre').value = '';
        loadTherapistActivationActivities(patientId);
    } catch (err) {
        alert(err.message);
    }
}

async function addPresetActivity(categoria, nombre) {
    const patientId = document.getElementById('tam-patient-id').value;
    if (!patientId) return;
    try {
        const res = await fetch('/api/therapist/activation/activities', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ paciente_id: patientId, categoria: categoria, nombre_actividad: nombre })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Error al agregar sugerencia');
        loadTherapistActivationActivities(patientId);
    } catch (err) {
        alert(err.message);
    }
}

async function toggleActivationActivity(actId, activaState) {
    const patientId = document.getElementById('tam-patient-id').value;
    try {
        const res = await fetch(`/api/therapist/activation/activities/${actId}/toggle`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ activa: activaState })
        });
        if (!res.ok) throw new Error('Error al actualizar estado');
        loadTherapistActivationActivities(patientId);
    } catch (err) {
        alert(err.message);
    }
}

async function loadPatientActivationChecklist(dateStr) {
    const necList = document.getElementById('act-necesarias-list');
    const plaList = document.getElementById('act-placer-list');
    const cotList = document.getElementById('act-cotidiana-list');

    if (!dateStr) {
        dateStr = new Date().toISOString().split('T')[0];
        const fechaInput = document.getElementById('act-fecha');
        if (fechaInput) fechaInput.value = dateStr;
    }

    try {
        const res = await fetch(`/api/patient/activation/checklist?fecha=${dateStr}`);
        const data = await res.json();

        const nec = data.filter(a => a.categoria === 'necesaria');
        const pla = data.filter(a => a.categoria === 'placer');
        const cot = data.filter(a => a.categoria === 'cotidiana');

        const renderCat = (items) => {
            if (items.length === 0) return '<p class="text-muted" style="font-size: 0.85rem; margin: 0;">No hay actividades asignadas en esta categoría.</p>';
            return items.map(a => `
                <label style="display: flex; align-items: center; gap: 0.65rem; background: white; padding: 0.5rem 0.75rem; border-radius: 6px; border: 1px solid var(--border-color); cursor: pointer; font-size: 0.9rem; font-weight: 600;">
                    <input type="checkbox" class="act-item-cb" data-act-id="${a.id}" ${a.completada ? 'checked' : ''} style="width: 19px; height: 19px; accent-color: #d97706;">
                    <span>${a.nombre_actividad}</span>
                </label>
            `).join('');
        };

        if (necList) necList.innerHTML = renderCat(nec);
        if (plaList) plaList.innerHTML = renderCat(pla);
        if (cotList) cotList.innerHTML = renderCat(cot);
    } catch (err) {
        console.error(err);
    }
}

async function submitPatientActivationLog(e) {
    e.preventDefault();
    const status = document.getElementById('patient-activation-status');
    if (status) status.classList.add('hide');

    const fecha = document.getElementById('act-fecha').value;
    const cbs = document.querySelectorAll('.act-item-cb');
    const items = Array.from(cbs).map(cb => ({
        actividad_id: parseInt(cb.getAttribute('data-act-id')),
        completada: cb.checked
    }));

    try {
        const res = await fetch('/api/patient/activation/log', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ fecha, registros: items })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Error al guardar');

        if (status) {
            status.innerText = '✅ Registro diario de activación conductual guardado.';
            status.className = 'status-msg success-msg mt-3';
        }
        loadPatientActivationHistory();
    } catch (err) {
        if (status) {
            status.innerText = `⚠️ ${err.message}`;
            status.className = 'status-msg error-msg mt-3';
        }
    }
}

async function loadPatientActivationHistory() {
    const list = document.getElementById('patient-activation-history-list');
    if (!list) return;
    try {
        const res = await fetch('/api/patient/activation/history');
        const data = await res.json();
        if (data.length === 0) {
            list.innerHTML = '<p class="text-muted text-center py-3">No tienes registros de actividades guardados aún.</p>';
            return;
        }

        list.innerHTML = `
            <table class="table" style="width: 100%; border-collapse: collapse; font-size: 0.85rem;">
                <thead>
                    <tr style="border-bottom: 2px solid var(--border-color); text-align: left;">
                        <th style="padding: 0.5rem;">Fecha</th>
                        <th style="padding: 0.5rem;">Categoría</th>
                        <th style="padding: 0.5rem;">Actividad</th>
                        <th style="padding: 0.5rem;">Estado</th>
                    </tr>
                </thead>
                <tbody>
                    ${data.map(r => {
                        let catLabel = r.categoria === 'necesaria' ? '📌 Necesaria' : (r.categoria === 'placer' ? '🎉 Placer' : '🏠 Cotidiana');
                        return `
                            <tr style="border-bottom: 1px solid var(--border-color);">
                                <td style="padding: 0.5rem;"><strong>${r.fecha}</strong></td>
                                <td style="padding: 0.5rem;">${catLabel}</td>
                                <td style="padding: 0.5rem;">${r.nombre_actividad}</td>
                                <td style="padding: 0.5rem;">${r.completada ? '🟢 Completada' : '⚪ Pendiente'}</td>
                            </tr>
                        `;
                    }).join('')}
                </tbody>
            </table>
        `;
    } catch (err) {
        list.innerHTML = `<p class="text-danger">Error: ${err.message}</p>`;
    }
}

function openPatientActivationView() {
    setDefaultToolDates();
    const today = document.getElementById('act-fecha')?.value || new Date().toISOString().split('T')[0];
    loadPatientActivationChecklist(today);
    loadPatientActivationHistory();
    switchPatientView('patient-activation');
}

window.openTherapistActivationModal = openTherapistActivationModal;
window.loadTherapistActivationActivities = loadTherapistActivationActivities;
window.submitTherapistAddActivationActivity = submitTherapistAddActivationActivity;
window.addPresetActivity = addPresetActivity;
window.toggleActivationActivity = toggleActivationActivity;
window.loadPatientActivationChecklist = loadPatientActivationChecklist;
window.submitPatientActivationLog = submitPatientActivationLog;
window.loadPatientActivationHistory = loadPatientActivationHistory;
window.openPatientActivationView = openPatientActivationView;


// --- INGESTA DE ALIMENTOS Y APETITO ---

async function submitPatientFoodIntakeLog(e) {
    e.preventDefault();
    const status = document.getElementById('patient-ingesta-status');
    if (status) status.classList.add('hide');

    const conductas = Array.from(document.querySelectorAll('.ingesta-conducta-cb:checked')).map(cb => cb.value);

    const payload = {
        fecha: document.getElementById('ingesta-fecha').value,
        tipo_comida: document.getElementById('ingesta-tipo-comida').value,
        descripcion_plato: document.getElementById('ingesta-descripcion').value,
        apetito_previo: parseInt(document.getElementById('ingesta-apetito').value || '5'),
        saciedad: parseInt(document.getElementById('ingesta-saciedad').value || '5'),
        contexto: document.getElementById('ingesta-contexto').value,
        afectividad: document.getElementById('ingesta-afectividad').value,
        pensamiento: document.getElementById('ingesta-pensamiento').value,
        conductas: conductas
    };

    try {
        const res = await fetch('/api/patient/food-intake/log', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (res.ok) {
            status.textContent = '¡Registro de ingesta guardado con éxito!';
            status.className = 'status-msg success-msg mt-3';
            status.classList.remove('hide');
            
            // Limpiar formulario y recargar historial
            document.getElementById('ingesta-descripcion').value = '';
            document.getElementById('ingesta-contexto').value = '';
            document.getElementById('ingesta-afectividad').value = '';
            document.getElementById('ingesta-pensamiento').value = '';
            document.querySelectorAll('.ingesta-conducta-cb').forEach(cb => cb.checked = false);
            
            loadPatientFoodIntakeHistory();
        } else {
            status.textContent = data.error || 'Error al guardar el registro de ingesta.';
            status.className = 'status-msg error-msg mt-3';
            status.classList.remove('hide');
        }
    } catch (err) {
        status.textContent = 'Error de conexión al guardar el registro de ingesta.';
        status.className = 'status-msg error-msg mt-3';
        status.classList.remove('hide');
    }
}

async function loadPatientFoodIntakeHistory() {
    const list = document.getElementById('patient-ingesta-history-list');
    if (!list) return;
    try {
        const res = await fetch('/api/patient/food-intake/history');
        const data = await res.json();
        if (data.length === 0) {
            list.innerHTML = '<p class="text-muted text-center py-3">No tienes registros de ingesta guardados aún.</p>';
            return;
        }

        list.innerHTML = `
            <table class="table" style="width: 100%; border-collapse: collapse; font-size: 0.85rem;">
                <thead>
                    <tr style="border-bottom: 2px solid var(--border-color); text-align: left;">
                        <th style="padding: 0.5rem;">Fecha</th>
                        <th style="padding: 0.5rem;">Tipo</th>
                        <th style="padding: 0.5rem;">Apetito / Saciedad</th>
                        <th style="padding: 0.5rem;">Plato & Conductas</th>
                    </tr>
                </thead>
                <tbody>
                    ${data.map(r => {
                        let conds = [];
                        try { conds = JSON.parse(r.conductas_json || '[]'); } catch(e){}
                        const condsText = conds.length > 0 ? conds.map(c => `⚠️ ${c}`).join(', ') : '🟢 Sin conductas problema';
                        return `
                            <tr style="border-bottom: 1px solid var(--border-color);">
                                <td style="padding: 0.5rem;"><strong>${r.fecha}</strong></td>
                                <td style="padding: 0.5rem;">${r.tipo_comida}</td>
                                <td style="padding: 0.5rem;">Apetito: <strong>${r.apetito_previo}/10</strong><br><small>Saciedad: ${r.saciedad}/10</small></td>
                                <td style="padding: 0.5rem;">${r.descripcion_plato || 'Sin descripción'}<br><small style="color: var(--text-muted);">${condsText}</small></td>
                            </tr>
                        `;
                    }).join('')}
                </tbody>
            </table>
        `;
    } catch (err) {
        list.innerHTML = `<p class="text-danger">Error: ${err.message}</p>`;
    }
}


// --- REGISTRO COGNITIVO ---

async function submitPatientCognitiveRecordLog(e) {
    e.preventDefault();
    const status = document.getElementById('patient-cognitivo-status');
    if (status) status.classList.add('hide');

    const payload = {
        fecha: document.getElementById('cog-fecha').value,
        situacion: document.getElementById('cog-situacion').value,
        pensamiento: document.getElementById('cog-pensamiento').value,
        emocion_sensacion: document.getElementById('cog-emocion').value,
        intensidad_emocion: parseInt(document.getElementById('cog-intensidad').value || '5'),
        conducta: document.getElementById('cog-conducta').value
    };

    try {
        const res = await fetch('/api/patient/cognitive-record/log', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (res.ok) {
            status.textContent = '¡Registro cognitivo guardado con éxito!';
            status.className = 'status-msg success-msg mt-3';
            status.classList.remove('hide');

            // Limpiar formulario y recargar historial
            document.getElementById('cog-situacion').value = '';
            document.getElementById('cog-pensamiento').value = '';
            document.getElementById('cog-emocion').value = '';
            document.getElementById('cog-conducta').value = '';

            loadPatientCognitiveRecordHistory();
        } else {
            status.textContent = data.error || 'Error al guardar el registro cognitivo.';
            status.className = 'status-msg error-msg mt-3';
            status.classList.remove('hide');
        }
    } catch (err) {
        status.textContent = 'Error de conexión al guardar el registro cognitivo.';
        status.className = 'status-msg error-msg mt-3';
        status.classList.remove('hide');
    }
}

async function loadPatientCognitiveRecordHistory() {
    const list = document.getElementById('patient-cognitivo-history-list');
    if (!list) return;
    try {
        const res = await fetch('/api/patient/cognitive-record/history');
        const data = await res.json();
        if (data.length === 0) {
            list.innerHTML = '<p class="text-muted text-center py-3">No tienes registros cognitivos guardados aún.</p>';
            return;
        }

        list.innerHTML = `
            <table class="table" style="width: 100%; border-collapse: collapse; font-size: 0.85rem;">
                <thead>
                    <tr style="border-bottom: 2px solid var(--border-color); text-align: left;">
                        <th style="padding: 0.5rem;">Fecha</th>
                        <th style="padding: 0.5rem;">Situación</th>
                        <th style="padding: 0.5rem;">Pensamiento Automático</th>
                        <th style="padding: 0.5rem;">Emoción & Conducta</th>
                    </tr>
                </thead>
                <tbody>
                    ${data.map(r => `
                        <tr style="border-bottom: 1px solid var(--border-color);">
                            <td style="padding: 0.5rem;"><strong>${r.fecha}</strong></td>
                            <td style="padding: 0.5rem;">${r.situacion}</td>
                            <td style="padding: 0.5rem;">"${r.pensamiento}"</td>
                            <td style="padding: 0.5rem;">${r.emocion_sensacion || 'N/A'} (${r.intensidad_emocion}/10)<br><small style="color: var(--text-muted);">Conducta: ${r.conducta || 'N/A'}</small></td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        `;
    } catch (err) {
        list.innerHTML = `<p class="text-danger">Error: ${err.message}</p>`;
    }
}

window.submitPatientFoodIntakeLog = submitPatientFoodIntakeLog;
window.loadPatientFoodIntakeHistory = loadPatientFoodIntakeHistory;
window.submitPatientCognitiveRecordLog = submitPatientCognitiveRecordLog;
window.loadPatientCognitiveRecordHistory = loadPatientCognitiveRecordHistory;

// ==========================================
// MÓDULO: CENTRO DE CONFIRMACIONES Y RECORDATORIOS (1-CLIC WA.ME)
// ==========================================

let currentMcFilterRange = 'hoy';

function filterManualConfirmations(range) {
    currentMcFilterRange = range || 'hoy';
    
    const ranges = ['hoy', 'manana', 'semana', 'todas'];
    ranges.forEach(r => {
        const btn = document.getElementById(`mc-filter-${r}`);
        if (btn) {
            if (r === currentMcFilterRange) {
                btn.className = 'btn btn-primary btn-sm';
                btn.style.fontWeight = '700';
            } else {
                btn.className = 'btn btn-secondary btn-sm';
                btn.style.fontWeight = '600';
            }
        }
    });

    renderManualConfirmationsView();
}
window.filterManualConfirmations = filterManualConfirmations;

async function renderManualConfirmationsView() {
    const listContainer = document.getElementById('manual-confirmations-list');
    const statPendientes = document.getElementById('mc-stat-pendientes');
    const statConfirmadas = document.getElementById('mc-stat-confirmadas');

    if (!listContainer) return;

    listContainer.innerHTML = `
        <div style="text-align: center; padding: 2rem; background: white; border-radius: var(--radius-md); border: 1.5px solid var(--border-color);">
            <div style="width: 32px; height: 32px; border: 3px solid #bfdbfe; border-top-color: #2563eb; border-radius: 50%; animation: spin 1s linear infinite; margin: 0 auto 0.75rem auto;"></div>
            <p style="font-size: 0.88rem; color: var(--text-muted); font-weight: 600; margin: 0;">Obteniendo consultas de la agenda...</p>
        </div>
    `;

    try {
        const res = await fetch('/api/agenda');
        if (!res.ok) throw new Error("Error al obtener las citas de la agenda.");
        const appointments = await res.json();

        const todayStr = new Date().toISOString().split('T')[0];
        
        const tomorrowObj = new Date();
        tomorrowObj.setDate(tomorrowObj.getDate() + 1);
        const tomorrowStr = tomorrowObj.toISOString().split('T')[0];

        const next7DaysObj = new Date();
        next7DaysObj.setDate(next7DaysObj.getDate() + 7);
        const next7DaysStr = next7DaysObj.toISOString().split('T')[0];

        const isApptConfirmed = (a) => (a.confirmada === 1 || a.confirmada === '1' || (a.estado || '').toLowerCase() === 'confirmada' || (a.estado_pago || '').toLowerCase() === 'confirmada');

        let filtered = appointments.filter(a => {
            const status = (a.estado || a.estado_pago || '').toLowerCase();
            return status !== 'cancelada' && status !== 'realizada' && status !== 'completada';
        });

        if (currentMcFilterRange === 'hoy') {
            filtered = filtered.filter(a => a.fecha === todayStr);
        } else if (currentMcFilterRange === 'manana') {
            filtered = filtered.filter(a => a.fecha === tomorrowStr);
        } else if (currentMcFilterRange === 'semana') {
            filtered = filtered.filter(a => a.fecha >= todayStr && a.fecha <= next7DaysStr);
        }

        filtered.sort((a, b) => {
            const dtA = `${a.fecha}T${a.hora || '00:00'}`;
            const dtB = `${b.fecha}T${b.hora || '00:00'}`;
            return dtA.localeCompare(dtB);
        });

        const totalPendientes = appointments.filter(a => !isApptConfirmed(a) && (a.estado_pago || '').toLowerCase() !== 'cancelada').length;
        const totalConfirmadas = appointments.filter(a => isApptConfirmed(a)).length;

        if (statPendientes) statPendientes.textContent = totalPendientes;
        if (statConfirmadas) statConfirmadas.textContent = totalConfirmadas;

        if (filtered.length === 0) {
            listContainer.innerHTML = `
                <div style="text-align: center; padding: 2.5rem 1.5rem; background: white; border-radius: var(--radius-md); border: 1.5px solid var(--border-color);">
                    <div style="font-size: 3rem; margin-bottom: 0.5rem;">🎉</div>
                    <h3 style="font-family: var(--font-title); font-weight: 700; color: var(--text-dark); margin: 0 0 0.35rem 0;">¡No hay citas pendientes para este filtro!</h3>
                    <p style="font-size: 0.85rem; color: var(--text-muted); margin: 0;">Todas tus consultas para este rango están confirmadas o no hay citas agendadas.</p>
                </div>
            `;
            return;
        }

        listContainer.innerHTML = filtered.map(appt => {
            const isConfirmed = isApptConfirmed(appt);
            const isOnline = (appt.modalidad || appt.tipo_consulta || '').toLowerCase() === 'online';
            const patientName = `${appt.nombres || ''} ${appt.apellidos || ''}`.trim() || appt.paciente_nombre || 'Consultante';
            const phone = appt.paciente_telefono || appt.telefono || appt.cedula || '';
            const formattedDate = appt.fecha ? appt.fecha.split('-').reverse().join('/') : '';

            return `
                <div style="background: white; border: 1.5px solid ${isConfirmed ? '#a7f3d0' : '#bfdbfe'}; border-radius: var(--radius-md); padding: 1.15rem; box-shadow: var(--shadow-sm); display: flex; flex-direction: column; gap: 0.85rem;">
                    <div style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 0.5rem;">
                        <div>
                            <div style="display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap;">
                                <h3 style="margin: 0; font-family: var(--font-title); font-weight: 700; font-size: 1.1rem; color: var(--text-dark);">
                                    👤 ${patientName}
                                </h3>
                                <span class="badge ${isConfirmed ? 'badge-success' : 'badge-warning'}" style="font-size: 0.78rem; font-weight: 700; padding: 0.25rem 0.55rem; background: ${isConfirmed ? '#10b981' : '#f59e0b'}; color: white;">
                                    ${isConfirmed ? '✅ Confirmada' : '⏳ Pendiente'}
                                </span>
                                <span class="badge" style="font-size: 0.78rem; font-weight: 700; padding: 0.25rem 0.55rem; background: #eff6ff; color: #1d4ed8; border: 1px solid #bfdbfe;">
                                    ${isOnline ? '💻 Online' : '🏥 Presencial'}
                                </span>
                            </div>
                            <div style="font-size: 0.85rem; color: var(--text-muted); margin-top: 0.35rem; display: flex; gap: 1rem; flex-wrap: wrap;">
                                <span>📅 Fecha: <strong>${formattedDate}</strong></span>
                                <span>⏰ Hora: <strong>${appt.hora || 'Por acordar'}</strong></span>
                                <span>📞 WhatsApp: <strong>${phone || 'No registrado'}</strong></span>
                            </div>
                        </div>

                        <div style="display: flex; gap: 0.35rem;">
                            ${!isConfirmed ? `
                                <button type="button" class="btn btn-sm btn-success" onclick="quickMarkApptStatus(${appt.id}, 'Confirmada')" style="background: #10b981; border: none; font-weight: 700; font-size: 0.78rem; padding: 0.35rem 0.65rem;">
                                    ✅ Marcar Confirmada
                                </button>
                            ` : ''}
                            <button type="button" class="btn btn-sm btn-secondary" onclick="quickMarkApptStatus(${appt.id}, 'Cancelada')" style="border: 1px solid #fca5a5; color: #dc2626; font-size: 0.78rem; padding: 0.35rem 0.65rem; background: white;">
                                ❌ Cancelar
                            </button>
                        </div>
                    </div>

                    <!-- Enlaces Directos 1-Clic WhatsApp -->
                    <div style="background: #f8fafc; border-radius: 8px; border: 1px solid #e2e8f0; padding: 0.75rem; display: flex; flex-wrap: wrap; gap: 0.5rem; align-items: center;">
                        <span style="font-size: 0.78rem; font-weight: 700; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px;">Acciones WhatsApp (1-Clic):</span>
                        
                        <button type="button" class="btn btn-sm btn-primary" onclick="sendWhatsappTemplateFromMc(${appt.id}, 'confirmacion')" style="background: #2563eb; border-color: #2563eb; font-weight: 700; font-size: 0.8rem; padding: 0.4rem 0.75rem;">
                            📱 Enviar Confirmación
                        </button>
                        
                        <button type="button" class="btn btn-sm btn-primary" onclick="sendWhatsappTemplateFromMc(${appt.id}, 'recordatorio')" style="background: #059669; border-color: #059669; font-weight: 700; font-size: 0.8rem; padding: 0.4rem 0.75rem;">
                            📱 Enviar Recordatorio
                        </button>

                        <button type="button" class="btn btn-sm btn-secondary" onclick="sendWhatsappTemplateFromMc(${appt.id}, 'cierre')" style="font-weight: 600; font-size: 0.8rem; padding: 0.4rem 0.75rem;">
                            📱 Enviar Mensaje de Cierre
                        </button>
                    </div>
                </div>
            `;
        }).join('');
    } catch (err) {
        console.error("Error cargando confirmaciones manuales:", err);
        listContainer.innerHTML = `
            <div class="text-center py-6" style="background: white; border-radius: var(--radius-md); border: 1.5px solid #fca5a5; padding: 1.5rem;">
                <p style="color: #dc2626; font-weight: 700; margin: 0;">Error al cargar las citas para el Centro de Confirmaciones.</p>
            </div>
        `;
    }
}
window.renderManualConfirmationsView = renderManualConfirmationsView;

async function sendWhatsappTemplateFromMc(apptId, type) {
    try {
        const res = await fetch(`/api/admin/message-templates/render?appointment_id=${apptId}&template_type=${type}`);
        const data = await res.json();
        
        if (res.ok && data.wa_url) {
            window.open(data.wa_url, '_blank');
        } else {
            alert(data.error || "No se pudo generar el enlace de WhatsApp para esta cita.");
        }
    } catch (err) {
        console.error("Error abriendo enlace WhatsApp:", err);
        alert("Error de conexión al generar el mensaje.");
    }
}
window.sendWhatsappTemplateFromMc = sendWhatsappTemplateFromMc;

async function quickMarkApptStatus(apptId, newStatus) {
    if (!confirm(`¿Deseas cambiar el estado de esta cita a "${newStatus}"?`)) return;

    try {
        const payload = {
            estado: newStatus,
            confirmada: newStatus === 'Confirmada' ? 1 : 0
        };
        if (newStatus === 'Cancelada') {
            payload.estado_pago = 'Cancelada';
        }
        const res = await fetch(`/api/agenda/${apptId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (res.ok) {
            renderManualConfirmationsView();
        } else {
            const errData = await res.json().catch(() => ({}));
            alert("Error al actualizar el estado de la cita: " + (errData.error || "Desconocido"));
        }
    } catch (err) {
        alert("Error de conexión al actualizar la cita.");
    }
}
window.quickMarkApptStatus = quickMarkApptStatus;

function toggleManualConfirmationsModule(enabled) {
    const navItem = document.getElementById('nav-item-manual-confirmations');
    const lblToggle = document.getElementById('lbl-toggle-manual-confirmations');
    const chkToggle = document.getElementById('toggle-manual-confirmations-module');

    if (navItem) {
        if (enabled) {
            navItem.classList.remove('hide');
        } else {
            navItem.classList.add('hide');
        }
    }

    if (lblToggle) {
        lblToggle.textContent = enabled ? 'Módulo Activado ✅' : 'Módulo Desactivado 🚫';
    }

    if (chkToggle) {
        chkToggle.checked = !!enabled;
    }

    localStorage.setItem('module_manual_confirmations_enabled', enabled ? '1' : '0');
}
window.toggleManualConfirmationsModule = toggleManualConfirmationsModule;

document.addEventListener('DOMContentLoaded', () => {
    const pref = localStorage.getItem('module_manual_confirmations_enabled');
    if (pref === '0') {
        toggleManualConfirmationsModule(false);
    }
});





