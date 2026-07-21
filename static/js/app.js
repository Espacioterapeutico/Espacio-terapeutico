// --- LÓGICA PWA E INSTALACIÓN DE APLICACIÓN ---
let deferredPwaPrompt = null;

if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
        navigator.serviceWorker.register('/sw.js')
            .then(reg => console.log('PWA Service Worker registrado:', reg.scope))
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

async function requestNotificationPermission() {
    if (!('Notification' in window)) return false;
    if (Notification.permission === 'granted') return true;
    if (Notification.permission !== 'denied') {
        try {
            const permission = await Notification.requestPermission();
            if (permission === 'granted') return true;
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
    } else if (viewId === 'pizarra-visual') {
        loadPizarraPatients();
        loadPizarraVisual();
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
                showAppLayout(data.username, data.role, data.activo, data.bloqueos, data.user_id, data.aviso_pago);
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
            // 1. Intentar como Psicólogo (Admin)
            const resAdmin = await fetch('/api/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password })
            });
            const dataAdmin = await resAdmin.json();
            
            if (resAdmin.ok) {
                showAppLayout(dataAdmin.username, dataAdmin.role, dataAdmin.activo, dataAdmin.bloqueos, dataAdmin.user_id, dataAdmin.aviso_pago);
                return;
            }
            
            // 2. Si no es admin o contraseña incorrecta para admin, intentar como Paciente
            const resPatient = await fetch('/api/patient/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password })
            });
            const dataPatient = await resPatient.json();
            
            if (resPatient.ok) {
                if (dataPatient.first_login) {
                    showPatientWizard(dataPatient.patient_id, dataPatient.username);
                } else {
                    showPatientLayout(dataPatient.username, dataPatient.patient_id);
                }
                return;
            }
            
            // Si ambos fallaron, mostrar el error más descriptivo
            errorMsg.textContent = dataAdmin.error && dataAdmin.error !== 'Credenciales inválidas.' 
                ? dataAdmin.error 
                : (dataPatient.error || 'Credenciales incorrectas.');
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
        showAuthScreen();
    } catch (err) {
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

function showAppLayout(username, role, activo, bloqueos, userId, avisoPago) {
    document.body.classList.remove('is-patient');
    document.getElementById('auth-screen').classList.add('hide');
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
    
    if (role === 'superadmin') {
        document.querySelector('.user-name').textContent = `Admin: ${username}`;
        document.querySelectorAll('.nav-item').forEach(link => {
            if (link.getAttribute('data-view') !== 'superadmin-dashboard') {
                link.classList.add('hide');
            } else {
                link.classList.remove('hide');
            }
        });
        switchView('superadmin-dashboard');
        loadSuperadminData();
        return;
    }
    
    document.querySelector('.user-name').textContent = `Psic. ${username}`;
    
    const saTab = document.querySelector('[data-view="superadmin-dashboard"]');
    if (saTab) saTab.classList.add('hide');
    
    document.querySelectorAll('.nav-item').forEach(link => {
        if (link.getAttribute('data-view') !== 'superadmin-dashboard') {
            link.classList.remove('hide');
        }
    });
    
    if (activo === 0) {
        alert("Atención: Tu suscripción está inactiva. Tus funciones han sido suspendidas.");
        document.querySelectorAll('.nav-item').forEach(link => {
            const v = link.getAttribute('data-view');
            if (v !== 'settings' && v !== 'superadmin-dashboard') {
                link.classList.add('hide');
            }
        });
        switchView('settings');
        switchSettingsTab('backup');
        return;
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
    const modality = modalitySelect ? modalitySelect.value : 'Online';
    
    let availableDates = [];
    try {
        const monthForApi = bookingMonth + 1;
        const res = await fetch(`/api/patient/available-dates?year=${bookingYear}&month=${monthForApi}&modalidad=${modality}`);
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
        const res = await fetch(`/api/patient/available-slots?date=${dateStr}`);
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
        if (viewName === 'patient-home') {
            switchPatientHomeSubView('next');
        } else if (viewName === 'patient-diary') {
            loadPizarraHistory();
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
        const res = await fetch(`/api/patient/portal-data`);
        if (!res.ok) return;
        const data = await res.json();
        if (!data) return;
        
        if (data.perfil) {
            window.patientProfile = data.perfil;
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
            
            const headerTherapist = document.getElementById('pat-header-therapist-name');
            if (headerTherapist) headerTherapist.textContent = therapistName;
            
            const menuTherapist = document.getElementById('pat-menu-therapist-name');
            if (menuTherapist) {
                menuTherapist.innerHTML = `
                    <span style="display: inline-block; width: 6px; height: 6px; background-color: var(--primary-color); border-radius: 50%;"></span>
                    <span>Terapeuta: ${therapistName}</span>
                `;
            }
        }
        
        if (data.modalidades) {
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
                if (data.modalidades.includes(currentVal)) {
                    selectElement.value = currentVal;
                }
            }
        }

        if (data.metodos_pago !== undefined) {
            const instrDiv = document.getElementById('pat-pay-instructions');
            if (instrDiv) {
                instrDiv.textContent = data.metodos_pago || 'No se han definido datos de pago aún.';
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
                    
                    const dateParts = cita.fecha.split('-');
                    const yearObj = parseInt(dateParts[0], 10);
                    const monthObj = parseInt(dateParts[1], 10) - 1;
                    const dayObj = parseInt(dateParts[2], 10);
                    const d = new Date(yearObj, monthObj, dayObj);
                    
                    const options = { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' };
                    let dateFormatted = d.toLocaleDateString('es-ES', options);
                    dateFormatted = dateFormatted.charAt(0).toUpperCase() + dateFormatted.slice(1);
                    
                    const timeFormatted = format12h(cita.hora);
                    const modalityText = cita.tipo_consulta || 'Online';
                    
                    const h4 = document.createElement('h4');
                    h4.className = 'mb-2';
                    h4.style.fontWeight = '700';
                    h4.style.fontSize = '1.1rem';
                    h4.style.color = 'var(--text-dark)';
                    h4.textContent = dateFormatted;
                    box.appendChild(h4);
                    
                    const p = document.createElement('p');
                    p.className = 'text-secondary mb-2';
                    p.style.fontSize = '0.9rem';
                    p.textContent = `${timeFormatted} — Modalidad ${modalityText}`;
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
                const card = document.createElement('div');
                card.style.border = '1px solid var(--border-color)';
                card.style.borderRadius = 'var(--radius-sm)';
                card.style.padding = '0.85rem';
                card.style.backgroundColor = 'var(--card-bg)';
                card.style.boxShadow = '0 1px 3px rgba(0,0,0,0.01)';
                card.style.display = 'flex';
                card.style.flexDirection = 'column';
                card.style.gap = '0.5rem';
                
                const meta = document.createElement('div');
                meta.style.display = 'flex';
                meta.style.justifyContent = 'space-between';
                meta.style.alignItems = 'center';
                meta.style.fontSize = '0.8rem';
                meta.style.color = 'var(--text-muted)';
                meta.style.borderBottom = '1px solid rgba(0,0,0,0.03)';
                meta.style.paddingBottom = '0.25rem';
                
                const dateObj = new Date(upd.fecha.replace(/-/g, '/'));
                const dateStr = dateObj.toLocaleDateString([], {day: '2-digit', month: '2-digit', year: 'numeric'});
                const timeStr = dateObj.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'});
                
                meta.innerHTML = `
                    <span style="font-weight: 600; color: var(--primary-color);">📝 Actualización</span>
                    <span>${dateStr} a las ${timeStr}</span>
                `;
                
                const content = document.createElement('div');
                content.style.fontSize = '0.9rem';
                content.style.lineHeight = '1.4';
                content.style.whiteSpace = 'pre-wrap';
                content.style.color = 'var(--text-dark)';
                content.textContent = upd.contenido;
                
                card.appendChild(meta);
                if (upd.contenido) {
                    card.appendChild(content);
                }
                
                if (upd.archivo_adjunto) {
                    const fileDiv = document.createElement('div');
                    fileDiv.style.marginTop = '0.25rem';
                    fileDiv.style.fontSize = '0.8rem';
                    fileDiv.style.padding = '0.35rem 0.5rem';
                    fileDiv.style.borderRadius = '4px';
                    fileDiv.style.backgroundColor = 'var(--bg-light)';
                    fileDiv.style.display = 'inline-flex';
                    fileDiv.style.alignItems = 'center';
                    fileDiv.style.gap = '0.35rem';
                    fileDiv.style.alignSelf = 'flex-start';
                    fileDiv.style.border = '1px solid var(--border-color)';
                    
                    const isImage = /\.(jpg|jpeg|png|gif|webp)$/i.test(upd.archivo_adjunto);
                    if (isImage) {
                        fileDiv.innerHTML = `
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width: 14px; height: 14px; color: var(--primary-color);"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>
                            <a href="#" onclick="openFilePreview('${upd.archivo_adjunto}'); return false;" style="color: var(--primary-color); text-decoration: none; font-weight: 600;">Ver Imagen Adjunta</a>
                        `;
                    } else {
                        fileDiv.innerHTML = `
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width: 14px; height: 14px; color: var(--primary-color);"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                            <a href="#" onclick="openFilePreview('${upd.archivo_adjunto}'); return false;" style="color: var(--primary-color); text-decoration: none; font-weight: 600;">Ver Documento Adjunto</a>
                        `;
                    }
                    card.appendChild(fileDiv);
                }
                
                historyList.appendChild(card);
            });
        } else {
            historyList.innerHTML = '<span class="text-secondary text-sm" style="font-style: italic;">No tienes actualizaciones registradas en tu pizarra terapéutica aún.</span>';
        }
    } catch (err) {
        historyList.innerHTML = '<span class="text-secondary text-sm" style="color: red;">Error al conectar con la pizarra terapéutica.</span>';
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
        
        grid.innerHTML = '';
        
        if (data.updates && data.updates.length > 0) {
            data.updates.forEach((upd, index) => {
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
                const dateStr = dateObj.toLocaleDateString([], {day: '2-digit', month: '2-digit', year: 'numeric'});
                const timeStr = dateObj.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'});
                
                const timeSpan = document.createElement('span');
                timeSpan.style.fontSize = '0.75rem';
                timeSpan.style.color = 'var(--text-muted)';
                timeSpan.textContent = `${dateStr} ${timeStr}`;
                
                header.appendChild(userPart);
                header.appendChild(timeSpan);
                
                const body = document.createElement('div');
                body.style.fontSize = '0.9rem';
                body.style.lineHeight = '1.5';
                body.style.whiteSpace = 'pre-wrap';
                body.style.color = 'var(--text-dark)';
                body.textContent = upd.contenido;
                
                card.appendChild(header);
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
                
                // Formulario de respuesta del terapeuta
                const replyContainer = document.createElement('div');
                replyContainer.style.marginTop = '1rem';
                replyContainer.style.borderTop = '1px dashed rgba(0,0,0,0.06)';
                replyContainer.style.paddingTop = '0.75rem';
                
                replyContainer.innerHTML = `
                    <div style="display: flex; gap: 0.5rem; align-items: center;">
                        <input type="text" placeholder="Escribe un comentario o respuesta..." style="flex: 1; padding: 0.4rem 0.6rem; border-radius: var(--radius-sm); border: 1.5px solid var(--border-color); font-size: 0.8rem; background-color: var(--card-bg);" id="reply-input-${upd.id}">
                        <button type="button" class="btn btn-primary btn-sm" style="padding: 0.4rem 0.8rem; font-size: 0.8rem; cursor: pointer; border-radius: var(--radius-sm);" onclick="submitPizarraReply(${upd.paciente_id}, ${upd.id})">Enviar</button>
                    </div>
                `;
                card.appendChild(replyContainer);
                
                grid.appendChild(card);
            });
        } else {
            grid.innerHTML = `
                <div style="grid-column: 1 / -1; text-align: center; padding: 3rem; background: var(--bg-light); border-radius: var(--radius-md); border: 1.5px dashed var(--border-color);">
                    <p class="text-secondary" style="font-style: italic;">No hay actualizaciones registradas en la pizarra terapéutica para los criterios seleccionados.</p>
                </div>
            `;
        }
    } catch (err) {
        grid.innerHTML = '<span class="text-secondary text-sm" style="color: red;">Error de conexión al cargar la pizarra visual.</span>';
    }
}

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
    
    try {
        const res = await fetch('/api/patient/change-password', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ current_password, new_password })
        });
        const data = await res.json();
        
        if (res.ok) {
            statusMsg.textContent = 'Contraseña actualizada con éxito.';
            statusMsg.className = 'status-msg success-msg';
            statusMsg.classList.remove('hide');
            document.getElementById('pat-change-pw-form').reset();
        } else {
            statusMsg.textContent = data.error || 'Error al actualizar contraseña.';
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

function renderPatientsTable(list) {
    const tbody = document.getElementById('patients-table-body');
    tbody.innerHTML = '';
    
    if (list.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="text-center">No hay pacientes registrados.</td></tr>';
        return;
    }
    
    list.forEach(p => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td><strong>${p.cedula}</strong></td>
            <td>${p.nombres} ${p.apellidos}</td>
            <td>${p.edad || 'N/A'}</td>
            <td>${p.genero || 'N/A'}</td>
            <td>${p.residencia_actual || 'N/A'}</td>
            <td class="actions-cell">
                <button class="btn btn-secondary btn-sm" onclick="openSummaryModal(${p.id})">Ficha Resumen</button>
                <button class="btn btn-primary btn-sm" onclick="openEditPatientModal(${p.id})">Editar</button>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

function openNewPatientModal() {
    document.getElementById('patient-form').reset();
    document.getElementById('patient-form-id').value = '';
    document.getElementById('p-ofrecer-paquete-personalizado').checked = false;
    document.getElementById('p-costo-paquete-personalizado').value = '';
    document.getElementById('p-sesiones-paquete-personalizado').value = '';
    togglePatientPkgInputs();
    document.getElementById('patient-modal-title').textContent = "Nueva Historia Clínica";
    switchFormTab(null, 'tab-personal');
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
                        <li><strong>Residencia:</strong> ${p.residencia_actual || 'N/A'}</li>
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
                            <span class="sum-fin-num text-secondary">${fin.prepagadas_no_consumidas}</span>
                            <span class="sum-fin-label">Prepago (Por Usar)</span>
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

function applySessionsFilters() {
    const timeline = document.getElementById('sessions-timeline');
    const modalityFilter = document.getElementById('session-filter-modalidad').value;
    const searchInput = document.getElementById('session-search-patient');
    const searchQuery = searchInput ? searchInput.value.toLowerCase().trim() : '';
    const countLabel = document.getElementById('session-filter-count');
    
    timeline.innerHTML = '';
    
    let filteredList = currentSessionsList;
    
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
    
    // 3. Actualizar conteo (por ejemplo: "3 de 10 consultas")
    if (countLabel) {
        countLabel.textContent = `${filteredList.length} de ${currentSessionsList.length} consultas`;
    }
    
    if (filteredList.length === 0) {
        timeline.innerHTML = '<div class="empty-state"><p>No se encontraron registros de evoluciones clínicas para los filtros aplicados.</p></div>';
        return;
    }
    
    filteredList.forEach(s => {
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
}

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
        
        document.getElementById('stat-total-patients').textContent = data.stats.total_pacientes;
        document.getElementById('stat-paid-sessions').textContent = data.stats.total_pagas;
        document.getElementById('stat-pending-sessions').textContent = data.stats.total_pendientes;
        
        const presVal = document.getElementById('stat-month-presencial');
        if (presVal) presVal.textContent = data.stats.month_presencial || 0;
        const onlineVal = document.getElementById('stat-month-online');
        if (onlineVal) onlineVal.textContent = data.stats.month_online || 0;
        const uptaebVal = document.getElementById('stat-month-uptaeb');
        if (uptaebVal) uptaebVal.textContent = data.stats.month_uptaeb || 0;
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
        
        // Sumar balances por moneda independientemente
        let usdTotal = 0;
        let eurTotal = 0;
        let bsdTotal = 0;
        
        // Objeto para agrupar modalidad
        const modalities = {};
        
        if (data.breakdown) {
            data.breakdown.forEach(item => {
                const val = item.total_monto || 0;
                if (item.moneda === 'USD') usdTotal += val;
                if (item.moneda === 'EUR') eurTotal += val;
                if (item.moneda === 'BSD') bsdTotal += val;
                
                const key = `${item.tipo_consulta} (${item.moneda})`;
                modalities[key] = (modalities[key] || 0) + val;
            });
        }
        
        // Actualizar tarjetas de balance en UI
        const usdEl = document.getElementById('fin-total-usd');
        const eurEl = document.getElementById('fin-total-eur');
        const bsdEl = document.getElementById('fin-total-bsd');
        if (usdEl) usdEl.textContent = `$ ${usdTotal.toFixed(2)}`;
        if (eurEl) eurEl.textContent = `€ ${eurTotal.toFixed(2)}`;
        if (bsdEl) bsdEl.textContent = `Bs. ${bsdTotal.toFixed(2)}`;
        
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
        const res = await fetch('/api/agenda');
        const list = await res.json();
        
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
            events: events,
            eventClick: function(info) {
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
        const res = await fetch('/api/agenda');
        const list = await res.json();
        
        tbody.innerHTML = '';
        
        if (list.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="text-center text-secondary">No hay citas en agenda.</td></tr>';
            return;
        }
        
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

async function openNewEventModal(defaultPaid = false) {
    document.getElementById('event-form').reset();
    document.getElementById('event-form-id').value = '';
    
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
    
    document.getElementById('e-fecha').value = new Date().toISOString().split('T')[0];
    
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
        document.getElementById('event-modal-title').textContent = "Registrar Cita en Agenda";
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
    
    document.getElementById('e-control-uso-row').classList.add('hide');
    document.getElementById('e-confirmada').checked = false;
    document.getElementById('e-confirmada').disabled = true;
    document.getElementById('e-confirmada-disabled-msg').textContent = '(Se habilita al editar una cita agendada)';
    openModal('event-modal');
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

        // Verificar prepagos para el paciente
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

async function handleEventSubmit(e) {
    e.preventDefault();
    
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
    daysList.style.display = 'none'; // colapsado por defecto
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
    toggleBtn.style.transform = 'rotate(-90deg)'; // rotado por defecto
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
    
    profileData.dias.forEach(day => {
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
        
        data.perfiles.forEach(perf => {
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
                    <button class="btn btn-secondary btn-block" disabled>
                        Falta credentials.json
                    </button>
                `;
            }
        }
    } catch (err) {
        console.error("Error al obtener estado de Google:", err);
    }
}

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
    document.getElementById(modalId).classList.remove('hide');
}

function closeModal(modalId) {
    document.getElementById(modalId).classList.add('hide');
}

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
    const optConsumir = document.getElementById('s-opt-descontar-prepago');
    const alertsDiv = document.getElementById('s-paciente-alerts');
    const montoInput = document.getElementById('s-monto');
    const monedaSelect = document.getElementById('s-moneda');
    const selectLiq = document.getElementById('s-tipo-liq');
    
    if (!patientId) {
        if (optConsumir) optConsumir.style.display = 'none';
        if (alertsDiv) {
            alertsDiv.classList.add('hide');
            alertsDiv.innerHTML = '';
        }
        return;
    }
    
    try {
        // 1. Obtener la tarifa personalizada asignada al paciente
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
        
        // 2. Obtener resumen de prepagos y deudas del paciente
        const resSummary = await fetch(`/api/patients/${patientId}/summary`);
        if (!resSummary.ok) return;
        const summary = await resSummary.json();
        
        const prepagas = summary.finance.prepagadas_no_consumidas || 0;
        const pendientes = summary.finance.pendientes || 0;
        
        let alertHTML = '';
        
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
                selectLiq.value = 'Dejar pendiente';
                toggleSessionFinanceInputs('Dejar pendiente');
            }
        }
        
        if (pendientes > 0) {
            alertHTML += `
                <div style="background-color: rgba(220, 53, 69, 0.1); color: #bd2130; padding: 0.5rem 0.75rem; border-radius: 6px; border: 1px solid rgba(220, 53, 69, 0.2);">
                    ⚠️ <strong>Atención:</strong> El consultante tiene <strong>${pendientes}</strong> citas o cargos anteriores pendientes por cobrar.
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

function togglePrepaymentCheckbox(checked) {
    const select = document.getElementById('s-tipo-liq');
    if (select) {
        select.value = checked ? 'Descontar prepago' : 'Dejar pendiente';
        toggleSessionFinanceInputs(select.value);
    }
}

function applySessionPrepaymentDiscount() {
    const chk = document.getElementById('s-chk-prepago');
    if (chk) {
        chk.checked = true;
        togglePrepaymentCheckbox(true);
    } else {
        const select = document.getElementById('s-tipo-liq');
        if (select) {
            select.value = 'Descontar prepago';
            toggleSessionFinanceInputs('Descontar prepago');
        }
    }
}

function toggleSessionFinanceFields(status) {
    const financeSection = document.getElementById('s-finance-section');
    if (!financeSection) return;
    if (status === 'Realizada' || status === 'Cancelada sin aviso') {
        financeSection.style.display = 'block';
    } else {
        financeSection.style.display = 'none';
    }
}

function toggleSessionFinanceInputs(tipo) {
    const isPrepay = (tipo === 'Descontar prepago');
    const isPending = (tipo === 'Dejar pendiente');
    const isExonerated = (tipo === 'Exonerar');
    
    const montoInput = document.getElementById('s-monto');
    const pagoDetallesRow = document.getElementById('s-pago-detalles-row');
    const pagoFechaRow = document.getElementById('s-pago-fecha-row');
    
    if (isPrepay) {
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
    const options = select.options;
    const lowerQuery = query.toLowerCase();
    
    let firstVisibleMatch = null;
    
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
        const residenciaActualText = p.residencia_actual ? `Residencia actual: ${p.residencia_actual}` : 'Residencia actual: N/A';
        
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
            if (!n.leida) unreadCount++;
            notifList.push({
                key,
                ...n
            });
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
        }
        
        // Ordenar por fecha desc
        notifList.sort((a, b) => new Date(b.fecha) - new Date(a.fecha));
        
        notifList.forEach(n => {
            // Disparar notificación nativa si no ha sido leída
            if (!n.leida) {
                triggerNativeNotification(n.titulo || 'Espacio Terapéutico', n.mensaje || '', `pat_${n.key}`, '');
            }

            const item = document.createElement('div');
            item.style.padding = '0.65rem 0.85rem';
            item.style.borderBottom = '1px solid var(--border-color)';
            item.style.cursor = 'pointer';
            item.style.transition = 'background-color 0.2s';
            item.style.backgroundColor = n.leida ? 'transparent' : 'rgba(169, 89, 147, 0.03)';
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
                            ${!n.leida ? '<span style="width: 5px; height: 5px; background-color: #ef4444; border-radius: 50%; display: inline-block;"></span>' : ''}
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
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ leida: true })
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
        const res = await fetch(`https://espacio-terapeutico-default-rtdb.firebaseio.com/pacientes/${patientId}/notificaciones.json`);
        if (!res.ok) return;
        const data = await res.json();
        
        if (data) {
            const updates = {};
            Object.keys(data).forEach(key => {
                updates[`${key}/leida`] = true;
            });
            
            await fetch(`https://espacio-terapeutico-default-rtdb.firebaseio.com/pacientes/${patientId}/notificaciones.json`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(updates)
            });
            
            loadPatientNotifications(patientId);
        }
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
        const payload = {
            tipo: "pizarra",
            titulo: "Comentario en Pizarra",
            mensaje: `Tu terapeuta comentó en tu pizarra: "${comment}"`,
            fecha: new Date().toISOString(),
            leida: false
        };
        
        const res = await fetch(`https://espacio-terapeutico-default-rtdb.firebaseio.com/pacientes/${patientId}/notificaciones.json`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        
        if (res.ok) {
            alert('Comentario enviado al paciente con éxito.');
            input.value = '';
        } else {
            alert('Error al enviar el comentario.');
        }
    } catch (err) {
        console.error("Error al enviar comentario de pizarra:", err);
        alert('Error de conexión.');
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

function switchSettingsTab(tabId) {
    const ids = ['backup', 'google', 'whatsapp', 'horarios', 'pagos', 'enlaces', 'soporte'];
    ids.forEach(id => {
        const card = document.getElementById(`set-card-${id}`);
        const tabBtn = document.getElementById(`set-tab-${id}`);
        
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
    
    if (tabId === 'pagos') {
        loadPaymentMethods();
    } else if (tabId === 'enlaces') {
        loadPatientLinks();
    }
}

function loadPatientLinks() {
    const userId = sessionStorage.getItem('user_id');
    if (!userId) return;
    
    const baseUrl = `${window.location.protocol}//${window.location.host}`;
    const regLink = `${baseUrl}/?ref_psicologo=${userId}`;
    const agendaLink = `${baseUrl}/?fast_booking=${userId}`;
    
    document.getElementById('link-registro-paciente').value = regLink;
    document.getElementById('link-agenda-rapida').value = agendaLink;
}

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
            select.innerHTML = '<option value="" disabled selected>Selecciona tu psicólogo...</option>';
            regPsychologists.forEach(p => {
                select.innerHTML += `<option value="${p.id}">Psic. ${p.nombres} ${p.apellidos}</option>`;
            });
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

async function submitRegister(e) {
    e.preventDefault();
    const errorMsg = document.getElementById('reg-error-msg');
    errorMsg.classList.add('hide');
    
    const tipo_usuario = document.getElementById('reg-tipo-usuario').value;
    const nombres = document.getElementById('reg-nombres').value.trim();
    const apellidos = document.getElementById('reg-apellidos').value.trim();
    const username = document.getElementById('reg-username').value.trim();
    const password = document.getElementById('reg-password').value;
    const cedula = document.getElementById('reg-cedula').value.trim();
    const telefono = document.getElementById('reg-telefono').value.trim();
    const email = document.getElementById('reg-email').value.trim();
    
    // Validaciones básicas con mensajes claros
    if (!nombres || !apellidos) {
        const msg = "Por favor, ingresa tu nombre y apellido.";
        errorMsg.textContent = msg; errorMsg.classList.remove('hide'); alert(msg); return;
    }
    if (!username) {
        const msg = "Por favor, elige un nombre de usuario.";
        errorMsg.textContent = msg; errorMsg.classList.remove('hide'); alert(msg); return;
    }
    if (!password || password.length < 4) {
        const msg = "La contraseña es requerida y debe tener al menos 4 caracteres.";
        errorMsg.textContent = msg; errorMsg.classList.remove('hide'); alert(msg); return;
    }
    if (!cedula) {
        const msg = "La cédula de identidad es requerida.";
        errorMsg.textContent = msg; errorMsg.classList.remove('hide'); alert(msg); return;
    }
    if (!tipo_usuario) {
        const msg = "Por favor, selecciona el tipo de cuenta (Psicólogo o Paciente).";
        errorMsg.textContent = msg; errorMsg.classList.remove('hide'); alert(msg); return;
    }
    
    const payload = {
        tipo_usuario, nombres, apellidos, username, password, cedula, telefono, email
    };
    
    if (tipo_usuario === 'psicologo') {
        payload.estudios = document.getElementById('reg-estudios').value;
        payload.federacion = document.getElementById('reg-federacion').value;
        payload.foto_titulo = document.getElementById('reg-foto-titulo').value || 'titulo.jpg';
        payload.foto_documento = document.getElementById('reg-foto-documento').value || 'cedula.jpg';
        
        if (!payload.estudios || !payload.federacion) {
            const msg = "Por favor, completa los campos de estudios y federación para psicólogo.";
            errorMsg.textContent = msg; errorMsg.classList.remove('hide'); alert(msg); return;
        }
    } else if (tipo_usuario === 'paciente') {
        payload.pregunta_seguridad_1 = document.getElementById('reg-pregunta-1').value;
        payload.respuesta_seguridad_1 = document.getElementById('reg-respuesta-1').value;
        payload.pregunta_seguridad_2 = document.getElementById('reg-pregunta-2').value;
        payload.respuesta_seguridad_2 = document.getElementById('reg-respuesta-2').value;
        
        if (isPreRegisteredPatient) {
            if (!payload.respuesta_seguridad_1 || !payload.respuesta_seguridad_2) {
                const msg = "Por favor, completa las respuestas de seguridad para activar tu cuenta.";
                errorMsg.textContent = msg; errorMsg.classList.remove('hide'); alert(msg); return;
            }
        } else {
            payload.psicologo_id = parseInt(document.getElementById('reg-psicologo-id').value);
            payload.pronombre = document.getElementById('reg-pronombre').value;
            payload.genero = document.getElementById('reg-genero').value;
            payload.edad = parseInt(document.getElementById('reg-edad').value);
            payload.lugar_nacimiento = document.getElementById('reg-lugar-nac').value;
            payload.fecha_nacimiento = document.getElementById('reg-fecha-nac').value;
            payload.residencia_actual = document.getElementById('reg-residencia').value;
            payload.con_quien_reside = document.getElementById('reg-con-quien').value;
            payload.nivel_academico = document.getElementById('reg-academico').value;
            payload.ocupacion = document.getElementById('reg-ocupacion').value;
            payload.estado_civil = document.getElementById('reg-estado-civil').value;
            payload.contacto_emergencia_nombre = document.getElementById('reg-contacto-emergencia').value;
            payload.contacto_emergencia_parentesco = document.getElementById('reg-contacto-parentesco').value;
            payload.motivo_consulta = document.getElementById('reg-motivo-consulta').value;
            payload.expectativas = document.getElementById('reg-expectativas').value;
            payload.farmacologia = document.getElementById('reg-farmacologia').value;
            
            if (!payload.psicologo_id) {
                const msg = "Por favor, selecciona un psicólogo asignado.";
                errorMsg.textContent = msg; errorMsg.classList.remove('hide'); alert(msg); return;
            }
            if (!payload.edad || payload.edad < 1) {
                const msg = "Por favor, ingresa tu edad.";
                errorMsg.textContent = msg; errorMsg.classList.remove('hide'); alert(msg); return;
            }
            if (!payload.contacto_emergencia_nombre || !payload.contacto_emergencia_parentesco) {
                const msg = "El contacto de emergencia (nombre y parentesco) es requerido.";
                errorMsg.textContent = msg; errorMsg.classList.remove('hide'); alert(msg); return;
            }
            if (!payload.motivo_consulta) {
                const msg = "El motivo de consulta es requerido para completar tu historia clínica.";
                errorMsg.textContent = msg; errorMsg.classList.remove('hide'); alert(msg); return;
            }
            if (!payload.respuesta_seguridad_1 || !payload.respuesta_seguridad_2) {
                const msg = "Las respuestas de seguridad son requeridas para proteger tu cuenta.";
                errorMsg.textContent = msg; errorMsg.classList.remove('hide'); alert(msg); return;
            }
        }
    }
    
    try {
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
            errorMsg.textContent = errText;
            errorMsg.classList.remove('hide');
            alert("Error de registro: " + errText);
        }
    } catch (err) {
        const errText = "Error de conexión con el servidor. Verifica tu conexión a internet e intenta de nuevo.";
        errorMsg.textContent = errText;
        errorMsg.classList.remove('hide');
        alert(errText);
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
            const tituloBtn = p.foto_titulo ? `<button type="button" class="btn btn-sm btn-outline-primary" style="padding:2px 6px; font-size:0.75rem; margin-right:4px;" onclick="viewDocumentPreview(\`${p.foto_titulo}\`, 'Título de ${escName}')">📄 Título</button>` : '';
            const docBtn = p.foto_documento ? `<button type="button" class="btn btn-sm btn-outline-secondary" style="padding:2px 6px; font-size:0.75rem;" onclick="viewDocumentPreview(\`${p.foto_documento}\`, 'Documento de ${escName}')">🪪 Cédula</button>` : '';
            const docCell = (tituloBtn || docBtn) ? `${tituloBtn}${docBtn}` : '<span style="font-size:0.75rem; color:var(--text-muted);">Sin adjuntos</span>';

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
                        <label style="display:flex; align-items:center; gap:0.25rem; cursor:pointer; color: #b91c1c; font-weight: 700; grid-column: 1 / 3; border-top: 1px dashed var(--border-color); padding-top: 0.35rem; margin-top: 0.25rem;">
                            <input type="checkbox" ${p.aviso_pago === 1 ? 'checked' : ''} onchange="toggleTherapistAvisoPago(${p.id})"> Activar Aviso de Pago (No Solvente)
                        </label>
                    </div>
                </td>
                <td style="padding: 0.75rem; border-bottom: 1px solid var(--border-color); text-align: center;">
                    <span class="badge ${activeClass}" style="margin-right: 0.5rem; padding: 4px 8px; border-radius: 4px; font-size: 0.75rem; display: inline-block; width: 65px;">${activeLabel}</span>
                    <button class="btn btn-sm ${buttonClass}" style="padding: 2px 8px; font-size: 0.75rem;" onclick="toggleTherapistActive(${p.id})">${buttonText}</button>
                </td>
            `;
            tbody.appendChild(tr);
        });
    } catch (err) {
        tbody.innerHTML = '<tr><td colspan="5" class="text-center text-danger">Error al cargar datos.</td></tr>';
    }
}

async function toggleTherapistActive(userId) {
    if (!confirm("¿Estás seguro de cambiar el estado de suscripción de este psicólogo?")) return;
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

// ==========================================
// AUTO-AGENDA RÁPIDA (FAST BOOKING)
// ==========================================
let fastBookingMonth = new Date().getMonth();
let fastBookingYear = new Date().getFullYear();
let fastBookingTherapistId = null;

async function checkFastBookingQuery() {
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.has('fast_booking')) {
        fastBookingTherapistId = parseInt(urlParams.get('fast_booking'));
        if (isNaN(fastBookingTherapistId)) return false;
        
        const loginScreen = document.getElementById('auth-screen');
        if (loginScreen) loginScreen.classList.add('hide');
        
        const fastScreen = document.getElementById('fast-booking-screen');
        if (fastScreen) fastScreen.classList.remove('hide');
        
        try {
            const res = await fetch(`/api/active-psychologists`);
            if (res.ok) {
                const psychologists = await res.json();
                const matched = psychologists.find(p => p.id === fastBookingTherapistId);
                if (matched) {
                    document.getElementById('fast-booking-therapist-name').textContent = `Con Psic. ${matched.nombres} ${matched.apellidos}`;
                } else {
                    document.getElementById('fast-booking-therapist-name').textContent = `Psicólogo ID: ${fastBookingTherapistId}`;
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
        
        renderFastCalendar();
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
    renderFastCalendar();
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
        const res = await fetch(`/api/patient/available-slots?date=${dateStr}&psicologo_id=${fastBookingTherapistId}`);
        const data = await res.json();
        
        hoursGrid.innerHTML = '';
        
        const localSlots = [];
        if (data.slots && data.slots.length > 0) {
            data.slots.forEach(slotObj => {
                const hourStr = slotObj.hora_literal || slotObj.iso.substring(11, 16);
                const therapistDate = slotObj.iso.substring(0, 10);
                
                localSlots.push({
                    displayTime: hourStr,
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
                btn.textContent = format12h(slot.displayTime);
                
                btn.style.padding = '0.5rem 1rem';
                btn.style.border = '1.5px solid #10b981';
                btn.style.borderRadius = '20px';
                btn.style.backgroundColor = '#ecfdf5';
                btn.style.color = '#047857';
                btn.style.fontWeight = '600';
                btn.style.cursor = 'pointer';
                
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
    
    if (!fecha || !hora || !cedula || !nombres || !apellidos || !telefono) {
        alert("Por favor completa los datos requeridos.");
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
                telefono
            })
        });
        
        const data = await res.json();
        
        if (res.ok) {
            statusMsg.textContent = "¡Cita agendada con éxito! Su psicólogo ha sido notificado.";
            statusMsg.className = "status-msg success-msg";
            statusMsg.classList.remove('hide');
            document.getElementById('fast-booking-form').reset();
            document.getElementById('fast-hours-container').classList.add('hide');
            document.getElementById('fast-patient-details').classList.add('hide');
            renderFastCalendar();
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
            
            const dateObj = new Date(t.fecha.replace(/-/g, '/'));
            const dateStr = dateObj.toLocaleDateString([], {day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit'});
            
            const badgeClass = t.leido ? 'badge-success' : 'badge-danger';
            const badgeText = t.leido ? 'Leído' : 'Pendiente';
            
            let actionBtn = '';
            if (!t.leido) {
                actionBtn = `<button class="btn btn-secondary btn-sm" onclick="markSupportTicketRead(${t.id})" style="padding: 0.25rem 0.5rem; font-size: 0.75rem; margin-right: 0.25rem;">Leído</button>`;
            }
            
            tr.innerHTML = `
                <td>${dateStr}</td>
                <td><strong>${t.remitente_nombre || 'N/A'}</strong></td>
                <td><span class="badge badge-info" style="text-transform: capitalize;">${t.rol}</span></td>
                <td>${t.email || t.telefono || 'N/A'}</td>
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

function viewDocumentPreview(fileData, titleStr) {
    const modal = document.getElementById('preview-modal');
    const title = document.getElementById('preview-modal-title');
    const body = document.getElementById('preview-modal-body');
    if (!modal || !body) return;
    
    if (title) title.textContent = titleStr || 'Vista Previa del Documento';
    
    if (!fileData) {
        body.innerHTML = '<p class="text-secondary">Sin documento adjunto.</p>';
    } else if (fileData.startsWith('data:image/')) {
        body.innerHTML = `<img src="${fileData}" style="max-width: 100%; max-height: 60vh; border-radius: 8px; box-shadow: var(--shadow-md); object-fit: contain;">`;
    } else if (fileData.startsWith('data:application/pdf')) {
        body.innerHTML = `<object data="${fileData}" type="application/pdf" style="width:100%; height:60vh;"><p>Tu navegador no admite PDF integrado. <a href="${fileData}" download="documento.pdf" class="btn btn-primary btn-sm">Descargar PDF</a></p></object>`;
    } else if (fileData.startsWith('http') || fileData.startsWith('/')) {
        openFilePreview(fileData);
        return;
    } else {
        body.innerHTML = `<p class="text-secondary">Documento guardado: <strong>${fileData}</strong></p>`;
    }
    modal.classList.remove('hide');
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
                        <strong style="font-size: 0.85rem; color: var(--text-dark); display: block; margin-bottom: 0.25rem;">Resumen de la sesión:</strong>
                        <p class="text-secondary" style="font-size: 0.9rem; margin: 0; white-space: pre-wrap; line-height: 1.45;">${s.resumen || 'No hay anotaciones registradas en el resumen clínico.'}</p>
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

const MONEDAS_DISPONIBLES = ['USD', 'DOP', 'VES', 'EUR', 'COP', 'CLP', 'ARS', 'PEN', 'MXN'];

async function loadPatientRatesTable() {
    const tbody = document.getElementById('patient-rates-table-body');
    if (!tbody) return;
    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:1.5rem;color:var(--text-muted);">Cargando pacientes...</td></tr>';
    try {
        const res = await fetch('/api/admin/patients-rates-list');
        const patients = await res.json();
        if (!Array.isArray(patients) || patients.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:1.5rem;color:var(--text-muted);">No hay pacientes registrados.</td></tr>';
            return;
        }
        tbody.innerHTML = patients.map(p => {
            const monedasOptions = MONEDAS_DISPONIBLES.map(m => `<option value="${m}" ${m === (p.moneda_personalizada || 'USD') ? 'selected' : ''}>${m}</option>`).join('');
            const costoIndStr = p.costo_personalizado != null ? Number(p.costo_personalizado).toFixed(2) : '—';
            const costoPaqStr = p.costo_paquete_personalizado != null ? Number(p.costo_paquete_personalizado).toFixed(2) : '—';
            const sesionesStr = p.sesiones_paquete_personalizado != null ? p.sesiones_paquete_personalizado : '—';
            return `
            <tr id="prt-row-${p.id}" style="border-bottom: 1px solid var(--border-color);">
                <td style="padding: 0.65rem 0.75rem; font-weight: 600;">${p.nombres || ''} ${p.apellidos || ''}</td>
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
    } catch (err) {
        console.error('Error loading patient rates:', err);
        tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--danger);">Error al cargar pacientes.</td></tr>';
    }
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
                        `<label style="display:flex;align-items:center;gap:0.5rem;cursor:pointer;">
                            <input type="checkbox" value="${d.id}" data-monto="${d.monto}" data-moneda="${d.moneda}" style="accent-color:var(--primary-color);">
                            ${d.fecha} — ${d.monto} ${d.moneda} (${d.tipo_consulta || 'Consulta'})
                        </label>`
                    ).join('');
                    if (montoEl) montoEl.value = '';
                } else {
                    debtList.innerHTML = '<span style="color:var(--text-muted);">No hay deudas pendientes.</span>';
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

