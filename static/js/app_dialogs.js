/* ==========================================================================
 * app_dialogs.js — Diálogos propios de Espacio Terapéutico
 * Reemplaza los diálogos nativos del navegador (alert / confirm / prompt)
 * por ventanas con el estilo de la app.
 *
 * Usa <dialog>.showModal(), que se dibuja en la "capa superior" del navegador:
 * siempre queda por encima de cualquier modal de la app (Evolucionar,
 * Registro rápido, Agenda rápida, etc.) sin depender de z-index.
 *
 * API (todas devuelven Promesas):
 *   await appAlert(mensaje, opciones?)                 -> undefined
 *   await appConfirm(mensaje, opciones?)               -> true | false
 *   await appPrompt(mensaje, valorInicial?, opciones?) -> string | null
 *
 * opciones: { title, okText, cancelText, danger, type, placeholder, inputType, multiline }
 * window.alert se redirige a appAlert (no bloqueante).
 * ========================================================================== */
(function () {
    'use strict';
    if (window.__appDialogsLoaded) return;
    window.__appDialogsLoaded = true;

    const nativeAlert = window.alert ? window.alert.bind(window) : null;
    const nativeConfirm = window.confirm ? window.confirm.bind(window) : null;
    const nativePrompt = window.prompt ? window.prompt.bind(window) : null;
    window.nativeAlert = nativeAlert;
    window.nativeConfirm = nativeConfirm;
    window.nativePrompt = nativePrompt;

    function escapeHtml(text) {
        if (text === null || text === undefined) return '';
        return String(text)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }
    window.escapeHtml = escapeHtml;

    const supportsDialog = typeof HTMLDialogElement === 'function' &&
        typeof HTMLDialogElement.prototype.showModal === 'function';

    const CSS = `
    .appdlg { padding: 0; border: none; background: transparent; max-width: none; max-height: none;
        width: 100%; height: 100%; margin: 0; display: flex; align-items: center; justify-content: center;
        overflow: auto; box-sizing: border-box; }
    .appdlg:not([open]) { display: none; }
    .appdlg::backdrop { background: rgba(15, 23, 42, 0.55); backdrop-filter: blur(3px); -webkit-backdrop-filter: blur(3px); }
    .appdlg.appdlg-fallback { position: fixed; inset: 0; z-index: 2147483000; background: rgba(15, 23, 42, 0.55); }
    .appdlg-card { background: var(--card-bg, #ffffff); color: var(--text-dark, #0f172a);
        width: min(92vw, 440px); border-radius: 18px; padding: 1.4rem 1.4rem 1.15rem;
        box-shadow: 0 25px 50px -12px rgba(0,0,0,0.35); border: 1px solid var(--border-color, #e2e8f0);
        font-family: inherit; box-sizing: border-box; margin: 1rem; animation: appdlgIn .18s ease-out; }
    @keyframes appdlgIn { from { opacity: 0; transform: translateY(10px) scale(.98); } to { opacity: 1; transform: none; } }
    .appdlg-head { display: flex; align-items: center; gap: .75rem; margin-bottom: .75rem; }
    .appdlg-icon { flex: 0 0 auto; width: 42px; height: 42px; border-radius: 12px; display: flex;
        align-items: center; justify-content: center; font-size: 1.3rem; }
    .appdlg-title { margin: 0; font-size: 1.05rem; font-weight: 800; line-height: 1.3; color: var(--text-dark, #0f172a); }
    .appdlg-msg { font-size: .9rem; line-height: 1.55; color: var(--text-secondary, #475569);
        white-space: pre-wrap; word-break: break-word; max-height: 55vh; overflow-y: auto; margin: 0 0 1rem; }
    .appdlg-input { width: 100%; box-sizing: border-box; padding: .6rem .8rem; border-radius: 10px;
        border: 1.5px solid var(--border-color, #cbd5e1); font: inherit; font-size: .92rem;
        background: var(--input-bg, var(--card-bg, #fff)); color: var(--text-dark, #0f172a); outline: none; margin-bottom: 1rem; }
    .appdlg-input:focus { border-color: var(--primary-color, #702e5e); box-shadow: 0 0 0 3px rgba(112,46,94,.15); }
    textarea.appdlg-input { resize: vertical; min-height: 84px; }
    .appdlg-actions { display: flex; justify-content: flex-end; gap: .6rem; flex-wrap: wrap; }
    .appdlg-btn { border: none; border-radius: 10px; padding: .6rem 1.25rem; font: inherit; font-size: .9rem;
        font-weight: 700; cursor: pointer; transition: filter .15s, background .15s; min-width: 96px; }
    .appdlg-btn:focus-visible { outline: 3px solid rgba(112,46,94,.35); outline-offset: 2px; }
    .appdlg-btn-sec { background: var(--bg-secondary, #f1f5f9); color: var(--text-secondary, #475569);
        border: 1px solid var(--border-color, #cbd5e1); }
    .appdlg-btn-sec:hover { filter: brightness(.96); }
    .appdlg-btn-pri { background: var(--primary-color, #702e5e); color: #fff; }
    .appdlg-btn-pri:hover { filter: brightness(1.08); }
    .appdlg-btn-danger { background: #dc2626; color: #fff; }
    .appdlg-btn-danger:hover { background: #b91c1c; }
    .appdlg-btn-ok { background: #059669; color: #fff; }
    .appdlg-btn-ok:hover { background: #047857; }
    .appdlg-t-info .appdlg-icon { background: rgba(112,46,94,.10); }
    .appdlg-t-success .appdlg-icon { background: #dcfce7; }
    .appdlg-t-error .appdlg-icon { background: #fee2e2; }
    .appdlg-t-warning .appdlg-icon { background: #fef3c7; }
    .appdlg-t-danger .appdlg-icon { background: #fee2e2; }
    .appdlg-t-question .appdlg-icon { background: rgba(112,46,94,.10); }
    html[data-theme="dark"] .appdlg-card { background: #1e293b; border-color: #334155; color: #f1f5f9; }
    html[data-theme="dark"] .appdlg-title { color: #f8fafc; }
    html[data-theme="dark"] .appdlg-msg { color: #cbd5e1; }
    html[data-theme="dark"] .appdlg-input { background: #0f172a; border-color: #475569; color: #f1f5f9; }
    html[data-theme="dark"] .appdlg-btn-sec { background: #334155; border-color: #475569; color: #e2e8f0; }
    @media (max-width: 480px) {
        .appdlg-card { padding: 1.2rem 1.1rem 1rem; border-radius: 16px; }
        .appdlg-actions { flex-direction: column-reverse; }
        .appdlg-btn { width: 100%; padding: .7rem 1rem; }
    }`;

    function injectCss() {
        if (document.getElementById('appdlg-styles')) return;
        const st = document.createElement('style');
        st.id = 'appdlg-styles';
        st.textContent = CSS;
        (document.head || document.documentElement).appendChild(st);
    }

    const ICONS = { info: 'ℹ️', success: '✅', error: '❌', warning: '⚠️', danger: '⚠️', question: '❓', copy: '🔗', input: '✏️' };
    const TITLES = {
        info: 'Aviso', success: 'Listo', error: 'Ocurrió un problema', warning: 'Atención',
        danger: 'Confirmar acción', question: 'Confirmar', copy: 'Copiar enlace', input: 'Ingresa la información'
    };

    function toText(msg) {
        if (msg === undefined || msg === null) return '';
        if (typeof msg === 'string') return msg;
        if (msg instanceof Error) return msg.message || String(msg);
        try { return typeof msg === 'object' ? JSON.stringify(msg) : String(msg); } catch (e) { return String(msg); }
    }

    function detectAlertType(t) {
        const s = t.toLowerCase();
        if (/❌|error|no se pudo|fall[óo]|inv[aá]lid|denegad|no autorizad|rechazad/.test(s)) return 'error';
        if (/✅|✓|exitosa|exitosamente|correctamente|con [ée]xito|guardad[oa]s?\b|enviad[oa]s?\b|registrad[oa]s?\b|actualizad[oa]s?\b|copiad[oa]|creado|eliminad[oa]s?\b/.test(s)) return 'success';
        if (/⚠️|⚠|atenci[óo]n|advertencia|por favor|debes|debe |selecciona|complet|requerid|obligatori|no hay/.test(s)) return 'warning';
        return 'info';
    }

    function detectDanger(t) {
        return /elimin|borrar|borrará|desvincul|disolver|suspend|reemplazar|descartar|vaciar|restablecer|cancelar tu cita|cancelando|desconectar|detener/i.test(t);
    }

    /** Separa un emoji/símbolo inicial del mensaje para usarlo como icono. */
    function splitLeadingIcon(t) {
        const m = t.match(/^\s*((?:\p{Extended_Pictographic}|[✓✔✗✘])(?:\uFE0F)?)\s*/u);
        if (m) return { icon: m[1], text: t.slice(m[0].length) };
        return { icon: null, text: t };
    }

    // Cola: un diálogo a la vez, en orden
    let chain = Promise.resolve();
    function enqueue(fn) {
        const p = chain.then(() => new Promise(fn));
        chain = p.catch(() => {});
        return p;
    }

    function whenBody() {
        if (document.body) return Promise.resolve();
        return new Promise(r => document.addEventListener('DOMContentLoaded', () => r(), { once: true }));
    }

    function buildAndShow(kind, message, defaultValue, opts, resolve) {
        injectCss();
        opts = opts || {};
        const raw = toText(message);
        const lead = splitLeadingIcon(raw);
        const isCopy = kind === 'prompt' && /^\s*copia\b/i.test(raw);

        let type = opts.type;
        if (!type) {
            if (kind === 'alert') type = detectAlertType(raw);
            else if (kind === 'confirm') type = (opts.danger !== undefined ? opts.danger : detectDanger(raw)) ? 'danger' : 'question';
            else type = isCopy ? 'copy' : 'input';
        }
        const danger = kind === 'confirm' && (opts.danger !== undefined ? !!opts.danger : type === 'danger');

        const dlg = document.createElement('dialog');
        dlg.className = 'appdlg appdlg-t-' + type + (supportsDialog ? '' : ' appdlg-fallback');
        dlg.setAttribute('aria-modal', 'true');
        dlg.setAttribute('role', kind === 'alert' ? 'alertdialog' : 'dialog');

        const card = document.createElement('div');
        card.className = 'appdlg-card';

        const head = document.createElement('div');
        head.className = 'appdlg-head';
        const icon = document.createElement('div');
        icon.className = 'appdlg-icon';
        icon.textContent = lead.icon || ICONS[type] || 'ℹ️';
        const title = document.createElement('h3');
        title.className = 'appdlg-title';
        title.textContent = opts.title || TITLES[type] || 'Aviso';
        head.appendChild(icon);
        head.appendChild(title);
        card.appendChild(head);

        const msgText = lead.text.trim();
        if (msgText) {
            const msg = document.createElement('div');
            msg.className = 'appdlg-msg';
            msg.textContent = msgText;
            card.appendChild(msg);
        }

        let input = null;
        if (kind === 'prompt') {
            const multiline = opts.multiline || (!isCopy && /mensaje|motivo|descripci|nota/i.test(raw));
            input = document.createElement(multiline ? 'textarea' : 'input');
            input.className = 'appdlg-input';
            if (!multiline) input.type = opts.inputType || 'text';
            if (opts.placeholder) input.placeholder = opts.placeholder;
            input.value = defaultValue !== undefined && defaultValue !== null ? String(defaultValue) : '';
            if (isCopy) input.readOnly = true;
            card.appendChild(input);
        }

        const actions = document.createElement('div');
        actions.className = 'appdlg-actions';
        let cancelBtn = null;
        if (kind !== 'alert') {
            cancelBtn = document.createElement('button');
            cancelBtn.type = 'button';
            cancelBtn.className = 'appdlg-btn appdlg-btn-sec';
            cancelBtn.textContent = opts.cancelText || (isCopy ? 'Cerrar' : 'Cancelar');
            actions.appendChild(cancelBtn);
        }
        const okBtn = document.createElement('button');
        okBtn.type = 'button';
        okBtn.className = 'appdlg-btn ' + (danger ? 'appdlg-btn-danger' : (type === 'success' ? 'appdlg-btn-ok' : 'appdlg-btn-pri'));
        okBtn.textContent = opts.okText || (isCopy ? '📋 Copiar' : (kind === 'alert' ? 'Entendido' : (danger ? 'Sí, continuar' : 'Aceptar')));
        actions.appendChild(okBtn);
        card.appendChild(actions);
        dlg.appendChild(card);

        let done = false;
        function finish(value) {
            if (done) return;
            done = true;
            try { if (supportsDialog && dlg.open) dlg.close(); } catch (e) {}
            dlg.remove();
            resolve(value);
        }
        const cancelValue = kind === 'confirm' ? false : (kind === 'prompt' ? null : undefined);

        okBtn.addEventListener('click', async () => {
            if (isCopy && input) {
                let copied = false;
                try { await navigator.clipboard.writeText(input.value); copied = true; } catch (e) {
                    try { input.removeAttribute('readonly'); input.select(); copied = document.execCommand('copy'); input.readOnly = true; } catch (e2) {}
                }
                okBtn.textContent = copied ? '✓ Copiado' : 'Selecciona y copia';
                if (copied) setTimeout(() => finish(input.value), 650);
                else { input.focus(); input.select(); }
                return;
            }
            if (kind === 'confirm') finish(true);
            else if (kind === 'prompt') finish(input.value);
            else finish(undefined);
        });
        if (cancelBtn) cancelBtn.addEventListener('click', () => finish(cancelValue));

        // Esc / botón Atrás del sistema
        dlg.addEventListener('cancel', (e) => { e.preventDefault(); finish(cancelValue); });
        // Clic fuera de la tarjeta: cierra solo avisos (confirm/prompt requieren decisión explícita)
        dlg.addEventListener('mousedown', (e) => { if (e.target === dlg && kind === 'alert') finish(undefined); });
        dlg.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && !supportsDialog) { e.preventDefault(); finish(cancelValue); }
            if (e.key === 'Enter' && input && input.tagName === 'INPUT' && !isCopy) { e.preventDefault(); finish(input.value); }
        });

        document.body.appendChild(dlg);
        if (supportsDialog) {
            try { dlg.showModal(); } catch (e) { dlg.setAttribute('open', ''); dlg.classList.add('appdlg-fallback'); }
        } else {
            dlg.setAttribute('open', '');
        }

        setTimeout(() => {
            if (input) { input.focus(); if (isCopy || input.value) input.select(); }
            else if (danger && cancelBtn) cancelBtn.focus();
            else okBtn.focus();
        }, 30);
    }

    function open(kind, message, defaultValue, opts) {
        return enqueue((resolve) => {
            whenBody().then(() => {
                try { buildAndShow(kind, message, defaultValue, opts, resolve); }
                catch (err) {
                    console.error('[appDialogs] error, usando diálogo nativo:', err);
                    if (kind === 'confirm') resolve(nativeConfirm ? nativeConfirm(toText(message)) : false);
                    else if (kind === 'prompt') resolve(nativePrompt ? nativePrompt(toText(message), defaultValue) : null);
                    else { if (nativeAlert) nativeAlert(toText(message)); resolve(); }
                }
            });
        });
    }

    function appAlert(message, opts) { return open('alert', message, undefined, opts); }
    function appConfirm(message, opts) { return open('confirm', message, undefined, opts); }
    function appPrompt(message, defaultValue, opts) {
        if (defaultValue && typeof defaultValue === 'object' && !opts) { opts = defaultValue; defaultValue = ''; }
        return open('prompt', message, defaultValue, opts);
    }

    window.appAlert = appAlert;
    window.appConfirm = appConfirm;
    window.appPrompt = appPrompt;

    // Redirigir alert() nativo al diálogo propio (no bloqueante)
    window.alert = function (message) { appAlert(message); };
})();
