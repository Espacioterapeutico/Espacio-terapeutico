// -*- coding: utf-8 -*-
/**
 * MÓDULO DE RECURSOS TERAPÉUTICOS (static/js/recursos_module.js)
 * Pizarras interactivas de trabajo psicoterapéutico homologadas al sistema:
 * - Pros y Contras (cálculo ponderado automático)
 * - Cuestionando Creencias (diálogo socrático paso a paso con 1 pregunta)
 * - Diversificando el Pensamiento (6 sombreros / lentes cognitivos)
 * - Pensamientos Negativos (Real vs. Imaginario)
 * - Segmentación de Objetivos (Corto, mediano y largo plazo)
 * - Sobrepensamiento (Embudo de 4 fases a micro-acción semanal)
 * 
 * Soporta edición colaborativa en vivo (psicólogo ↔ consultante),
 * autoguardado inteligente, portal de pacientes, historial y exportación a Word (.docx).
 */

(function () {
    'use strict';

    window.currentRecursosCatalogo = [];
    window.activeRecursoPizarra = null;
    window.recursoAutoSaveTimer = null;
    window.recursoLiveSyncInterval = null;
    window.lastSyncedTimestamp = null;
    window.selectedRecursoPatientId = null;

    // =========================================================================
    // 1. INICIALIZACIÓN Y NAVEGACIÓN (TERAPEUTA)
    // =========================================================================

    async function initRecursosView() {
        switchRecursosTab('catalogo');
        await loadRecursosCatalogo();
        await populateRecursosPatientSelector();
    }
    window.initRecursosView = initRecursosView;

    function switchRecursosTab(tab) {
        const btnCat = document.getElementById('rec-tab-btn-catalogo');
        const btnPiz = document.getElementById('rec-tab-btn-pizarras');
        const subCat = document.getElementById('rec-subview-catalogo');
        const subPiz = document.getElementById('rec-subview-pizarras');

        if (!btnCat || !btnPiz || !subCat || !subPiz) return;

        if (tab === 'catalogo') {
            btnCat.classList.add('active');
            btnCat.style.background = 'var(--primary-color)';
            btnCat.style.color = '#ffffff';
            btnCat.style.border = 'none';

            btnPiz.classList.remove('active');
            btnPiz.style.background = '#ffffff';
            btnPiz.style.color = 'var(--text-dark)';
            btnPiz.style.border = '1.5px solid var(--border-color)';

            subCat.classList.remove('hide');
            subPiz.classList.add('hide');
        } else {
            btnPiz.classList.add('active');
            btnPiz.style.background = 'var(--primary-color)';
            btnPiz.style.color = '#ffffff';
            btnPiz.style.border = 'none';

            btnCat.classList.remove('active');
            btnCat.style.background = '#ffffff';
            btnCat.style.color = 'var(--text-dark)';
            btnCat.style.border = '1.5px solid var(--border-color)';

            subPiz.classList.remove('hide');
            subCat.classList.add('hide');

            // Si hay un paciente previamente seleccionado, recargar sus pizarras
            const select = document.getElementById('rec-patient-filter-select');
            if (select && select.value) {
                onRecursoPatientSelected(select.value);
            }
        }
    }
    window.switchRecursosTab = switchRecursosTab;

    async function loadRecursosCatalogo() {
        const grid = document.getElementById('recursos-catalogo-grid');
        if (!grid) return;
        try {
            const res = await fetch('/api/recursos/catalogo');
            if (!res.ok) throw new Error('Error al cargar catálogo');
            const catalogo = await res.json();
            window.currentRecursosCatalogo = catalogo;
            renderRecursosCatalogo(catalogo);
        } catch (e) {
            console.error(e);
            grid.innerHTML = '<p class="text-danger text-center py-4">Error al conectar con el catálogo de recursos.</p>';
        }
    }
    window.loadRecursosCatalogo = loadRecursosCatalogo;

    function renderRecursosCatalogo(catalogo) {
        const grid = document.getElementById('recursos-catalogo-grid');
        if (!grid) return;

        let html = '';
        catalogo.forEach(item => {
            html += `
            <div class="card" style="background: #ffffff; border-radius: 16px; border: 1.5px solid #e2e8f0; padding: 1.25rem; display: flex; flex-direction: column; justify-content: space-between; box-shadow: 0 4px 15px rgba(0,0,0,0.03); transition: transform 0.2s, box-shadow 0.2s;">
                <div>
                    <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.75rem;">
                        <span style="font-size: 2.2rem; line-height: 1; padding: 0.5rem; background: ${item.color_bg || '#f3e8ff'}; border-radius: 12px;">
                            ${item.icono}
                        </span>
                        <span style="font-size: 0.72rem; font-weight: 700; color: ${item.color || '#7e22ce'}; background: ${item.color_bg || '#f3e8ff'}; padding: 0.2rem 0.6rem; border-radius: 12px; border: 1px solid ${item.color}33;">
                            ${item.categoria}
                        </span>
                    </div>
                    <h3 style="margin: 0 0 0.4rem 0; font-size: 1.1rem; font-weight: 800; color: #1e293b;">
                        ${item.titulo}
                    </h3>
                    <p style="margin: 0 0 0.85rem 0; font-size: 0.84rem; color: #64748b; line-height: 1.45;">
                        ${item.descripcion}
                    </p>
                </div>
                <div style="border-top: 1px solid #f1f5f9; padding-top: 0.85rem; display: flex; justify-content: space-between; align-items: center; gap: 0.5rem;">
                    <span style="font-size: 0.75rem; color: #94a3b8; font-weight: 600;">
                        ⏱️ ${item.tiempo_estimado}
                    </span>
                    <button type="button" class="btn btn-sm btn-primary" onclick="openAsignarRecursoModal('${item.id}')" style="font-weight: 700; font-size: 0.82rem; padding: 0.4rem 0.85rem; border-radius: 8px; background: ${item.color || 'var(--primary-color)'}; border: none;">
                        ➕ Asignar / Abrir
                    </button>
                </div>
            </div>`;
        });

        grid.innerHTML = html;
    }

    async function populateRecursosPatientSelector() {
        let pacientes = [];
        if (typeof patients !== 'undefined' && Array.isArray(patients) && patients.length > 0) {
            pacientes = patients;
        } else if (window.patients && Array.isArray(window.patients) && window.patients.length > 0) {
            pacientes = window.patients;
        } else {
            try {
                const res = await fetch('/api/patients');
                if (res.ok) {
                    pacientes = await res.json();
                }
            } catch (e) {
                console.error("Error al cargar pacientes para recursos:", e);
            }
        }
        window._recursosPatientsCache = pacientes;
    }
    window.populateRecursosPatientSelector = populateRecursosPatientSelector;

    function getRecursosPatientsCache() {
        if (typeof patients !== 'undefined' && Array.isArray(patients) && patients.length > 0) {
            return patients;
        }
        if (window.patients && Array.isArray(window.patients) && window.patients.length > 0) {
            return window.patients;
        }
        return window._recursosPatientsCache || [];
    }

    function searchPatientsCombined(query) {
        const list = getRecursosPatientsCache();
        if (!query || !query.trim()) return list;

        const normalizedTokens = query.toLowerCase()
            .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
            .split(/\s+/)
            .filter(Boolean);

        return list.filter(p => {
            const combinedText = `${p.cedula || ''} ${p.nombres || ''} ${p.apellidos || ''} ${p.telefono || ''} ${p.email || ''}`
                .toLowerCase()
                .normalize('NFD').replace(/[\u0300-\u036f]/g, '');
            return normalizedTokens.every(tok => combinedText.includes(tok));
        });
    }

    // -------------------------------------------------------------------------
    // BÚSQUEDA COMBINADA EN MODAL NUEVA PIZARRA (#modal-asignar-recurso)
    // -------------------------------------------------------------------------

    function onRecursoPatientSearchFocus() {
        const input = document.getElementById('asig-rec-paciente-search');
        onRecursoPatientSearchInput(input ? input.value : '');
    }
    window.onRecursoPatientSearchFocus = onRecursoPatientSearchFocus;

    function onRecursoPatientSearchInput(query) {
        const dropdown = document.getElementById('asig-rec-patient-dropdown');
        const clearBtn = document.getElementById('asig-rec-clear-patient-btn');
        if (!dropdown) return;

        if (clearBtn) {
            if (query && query.trim()) clearBtn.classList.remove('hide');
            else clearBtn.classList.add('hide');
        }

        const matches = searchPatientsCombined(query);

        if (matches.length === 0) {
            dropdown.innerHTML = `
            <div style="padding: 0.85rem 1rem; color: #94a3b8; font-size: 0.88rem; text-align: center;">
                No se encontraron consultantes con "${escapeHtml(query)}"
            </div>`;
            dropdown.classList.remove('hide');
            return;
        }

        let html = '';
        matches.slice(0, 30).forEach(p => {
            const nombreCompleto = `${p.nombres || ''} ${p.apellidos || ''}`.trim() || p.nombre || 'Consultante';
            const cedulaTxt = p.cedula ? `C.I. ${p.cedula}` : 'Sin cédula';
            const telTxt = p.telefono ? ` • 📞 ${p.telefono}` : '';
            html += `
            <div onclick="selectRecursoPatient(${p.id})" 
                 style="padding: 0.65rem 0.9rem; cursor: pointer; border-bottom: 1px solid #f1f5f9; display: flex; justify-content: space-between; align-items: center; transition: background 0.15s ease;" 
                 onmouseover="this.style.background='#fdf4ff'" 
                 onmouseout="this.style.background='#ffffff'">
                <div>
                    <strong style="color: #1e293b; font-size: 0.88rem; display: block;">${nombreCompleto}</strong>
                    <span style="font-size: 0.76rem; color: #64748b;">${cedulaTxt}${telTxt}</span>
                </div>
                <span style="font-size: 0.75rem; font-weight: 700; color: #702e5e; background: #fdf4ff; border: 1px solid #f0abfc; padding: 0.2rem 0.55rem; border-radius: 8px;">
                    Seleccionar ➔
                </span>
            </div>`;
        });

        dropdown.innerHTML = html;
        dropdown.classList.remove('hide');
    }
    window.onRecursoPatientSearchInput = onRecursoPatientSearchInput;

    function selectRecursoPatient(patientId) {
        const patientsList = getRecursosPatientsCache();
        const p = patientsList.find(x => x.id === parseInt(patientId));
        if (!p) return;

        const hiddenInput = document.getElementById('asig-rec-paciente');
        const searchInput = document.getElementById('asig-rec-paciente-search');
        const dropdown = document.getElementById('asig-rec-patient-dropdown');
        const badge = document.getElementById('asig-rec-selected-badge');
        const badgeName = document.getElementById('asig-rec-badge-name');
        const badgeCedula = document.getElementById('asig-rec-badge-cedula');
        const clearBtn = document.getElementById('asig-rec-clear-patient-btn');

        const nombreCompleto = `${p.nombres || ''} ${p.apellidos || ''}`.trim() || p.nombre || 'Consultante';
        const cedulaTxt = p.cedula ? `(C.I. ${p.cedula})` : '';

        if (hiddenInput) hiddenInput.value = p.id;
        if (searchInput) {
            searchInput.value = `${nombreCompleto} ${cedulaTxt}`.trim();
        }
        if (dropdown) dropdown.classList.add('hide');
        if (clearBtn) clearBtn.classList.remove('hide');

        if (badge && badgeName) {
            badgeName.textContent = nombreCompleto;
            if (badgeCedula) badgeCedula.textContent = cedulaTxt;
            badge.classList.remove('hide');
        }
    }
    window.selectRecursoPatient = selectRecursoPatient;

    function clearRecursoSelectedPatient() {
        const hiddenInput = document.getElementById('asig-rec-paciente');
        const searchInput = document.getElementById('asig-rec-paciente-search');
        const dropdown = document.getElementById('asig-rec-patient-dropdown');
        const badge = document.getElementById('asig-rec-selected-badge');
        const clearBtn = document.getElementById('asig-rec-clear-patient-btn');

        if (hiddenInput) hiddenInput.value = '';
        if (searchInput) {
            searchInput.value = '';
        }
        if (dropdown) dropdown.classList.add('hide');
        if (clearBtn) clearBtn.classList.add('hide');
        if (badge) badge.classList.add('hide');
    }
    window.clearRecursoSelectedPatient = clearRecursoSelectedPatient;

    // -------------------------------------------------------------------------
    // BÚSQUEDA COMBINADA EN PESTAÑA PIZARRAS POR CONSULTANTE
    // -------------------------------------------------------------------------

    function onRecursoFilterSearchFocus() {
        const input = document.getElementById('rec-patient-filter-search');
        onRecursoFilterSearchInput(input ? input.value : '');
    }
    window.onRecursoFilterSearchFocus = onRecursoFilterSearchFocus;

    function onRecursoFilterSearchInput(query) {
        const dropdown = document.getElementById('rec-patient-filter-dropdown');
        const clearBtn = document.getElementById('rec-filter-clear-patient-btn');
        if (!dropdown) return;

        if (clearBtn) {
            if (query && query.trim()) clearBtn.classList.remove('hide');
            else clearBtn.classList.add('hide');
        }

        const matches = searchPatientsCombined(query);

        if (matches.length === 0) {
            dropdown.innerHTML = `
            <div style="padding: 0.85rem 1rem; color: #94a3b8; font-size: 0.88rem; text-align: center;">
                No se encontraron consultantes con "${escapeHtml(query)}"
            </div>`;
            dropdown.classList.remove('hide');
            return;
        }

        let html = '';
        matches.slice(0, 30).forEach(p => {
            const nombreCompleto = `${p.nombres || ''} ${p.apellidos || ''}`.trim() || p.nombre || 'Consultante';
            const cedulaTxt = p.cedula ? `C.I. ${p.cedula}` : 'Sin cédula';
            const telTxt = p.telefono ? ` • 📞 ${p.telefono}` : '';
            html += `
            <div onclick="selectRecursoFilterPatient(${p.id})" 
                 style="padding: 0.65rem 0.9rem; cursor: pointer; border-bottom: 1px solid #f1f5f9; display: flex; justify-content: space-between; align-items: center; transition: background 0.15s ease;" 
                 onmouseover="this.style.background='#fdf4ff'" 
                 onmouseout="this.style.background='#ffffff'">
                <div>
                    <strong style="color: #1e293b; font-size: 0.88rem; display: block;">${nombreCompleto}</strong>
                    <span style="font-size: 0.76rem; color: #64748b;">${cedulaTxt}${telTxt}</span>
                </div>
                <span style="font-size: 0.75rem; font-weight: 700; color: #702e5e; background: #fdf4ff; border: 1px solid #f0abfc; padding: 0.2rem 0.55rem; border-radius: 8px;">
                    Ver Pizarras ➔
                </span>
            </div>`;
        });

        dropdown.innerHTML = html;
        dropdown.classList.remove('hide');
    }
    window.onRecursoFilterSearchInput = onRecursoFilterSearchInput;

    function selectRecursoFilterPatient(patientId) {
        const patientsList = getRecursosPatientsCache();
        const p = patientsList.find(x => x.id === parseInt(patientId));
        if (!p) return;

        const hiddenSelect = document.getElementById('rec-patient-filter-select');
        const searchInput = document.getElementById('rec-patient-filter-search');
        const dropdown = document.getElementById('rec-patient-filter-dropdown');
        const badge = document.getElementById('rec-filter-selected-badge');
        const badgeName = document.getElementById('rec-filter-badge-name');
        const badgeCedula = document.getElementById('rec-filter-badge-cedula');
        const clearBtn = document.getElementById('rec-filter-clear-patient-btn');

        const nombreCompleto = `${p.nombres || ''} ${p.apellidos || ''}`.trim() || p.nombre || 'Consultante';
        const cedulaTxt = p.cedula ? `(C.I. ${p.cedula})` : '';

        if (hiddenSelect) hiddenSelect.value = p.id;
        if (searchInput) {
            searchInput.value = `${nombreCompleto} ${cedulaTxt}`.trim();
        }
        if (dropdown) dropdown.classList.add('hide');
        if (clearBtn) clearBtn.classList.remove('hide');

        if (badge && badgeName) {
            badgeName.textContent = nombreCompleto;
            if (badgeCedula) badgeCedula.textContent = cedulaTxt;
            badge.classList.remove('hide');
        }

        onRecursoPatientSelected(p.id);
    }
    window.selectRecursoFilterPatient = selectRecursoFilterPatient;

    function clearRecursoFilterPatient() {
        const hiddenSelect = document.getElementById('rec-patient-filter-select');
        const searchInput = document.getElementById('rec-patient-filter-search');
        const dropdown = document.getElementById('rec-patient-filter-dropdown');
        const badge = document.getElementById('rec-filter-selected-badge');
        const clearBtn = document.getElementById('rec-filter-clear-patient-btn');

        if (hiddenSelect) hiddenSelect.value = '';
        if (searchInput) {
            searchInput.value = '';
        }
        if (dropdown) dropdown.classList.add('hide');
        if (clearBtn) clearBtn.classList.add('hide');
        if (badge) badge.classList.add('hide');

        onRecursoPatientSelected('');
    }
    window.clearRecursoFilterPatient = clearRecursoFilterPatient;

    // Cierre de dropdowns al hacer clic fuera
    document.addEventListener('click', (e) => {
        const modalDropdown = document.getElementById('asig-rec-patient-dropdown');
        const modalInput = document.getElementById('asig-rec-paciente-search');
        if (modalDropdown && modalInput && !modalInput.contains(e.target) && !modalDropdown.contains(e.target)) {
            modalDropdown.classList.add('hide');
        }

        const filterDropdown = document.getElementById('rec-patient-filter-dropdown');
        const filterInput = document.getElementById('rec-patient-filter-search');
        if (filterDropdown && filterInput && !filterInput.contains(e.target) && !filterDropdown.contains(e.target)) {
            filterDropdown.classList.add('hide');
        }
    });

    async function onRecursoPatientSelected(patientId) {
        window.selectedRecursoPatientId = patientId;
        const container = document.getElementById('rec-patient-pizarras-container');
        if (!container) return;

        if (!patientId) {
            container.innerHTML = `
            <div style="text-align: center; padding: 2.5rem 1rem; color: var(--text-muted);">
                <span style="font-size: 2.5rem; display: block; margin-bottom: 0.5rem;">📁</span>
                <p style="margin: 0; font-size: 0.95rem;">Busca y selecciona un consultante para ver sus pizarras interactivas de recursos o crear una nueva.</p>
            </div>`;
            return;
        }

        container.innerHTML = '<p class="text-muted text-center py-4">Cargando pizarras del consultante...</p>';

        try {
            const res = await fetch(`/api/recursos/paciente/${patientId}`);
            if (!res.ok) throw new Error('Error al cargar recursos');
            const recursos = await res.json();
            renderPatientPizarrasTable(recursos, container, false);
        } catch (e) {
            console.error(e);
            container.innerHTML = '<p class="text-danger text-center py-4">Error al cargar las pizarras de este consultante.</p>';
        }
    }
    window.onRecursoPatientSelected = onRecursoPatientSelected;

    function renderPatientPizarrasTable(recursos, container, isPatientPortal) {
        if (!recursos || recursos.length === 0) {
            container.innerHTML = `
            <div style="text-align: center; padding: 2.5rem 1rem; background: #ffffff; border-radius: 12px; border: 1.5px dashed #cbd5e1;">
                <span style="font-size: 2.2rem; display: block; margin-bottom: 0.5rem;">📝</span>
                <h4 style="margin: 0 0 0.35rem 0; color: #1e293b;">No hay pizarras creadas aún</h4>
                <p style="margin: 0 0 1rem 0; font-size: 0.85rem; color: #64748b;">
                    ${isPatientPortal ? 'Tu terapeuta aún no te ha asignado un recurso interactivo.' : 'Crea la primera pizarra de recurso para este consultante.'}
                </p>
                ${!isPatientPortal ? `<button type="button" class="btn btn-sm btn-primary" onclick="openAsignarRecursoModal()" style="font-weight: 700; border-radius: 8px;">➕ Crear Nueva Pizarra</button>` : ''}
            </div>`;
            return;
        }

        let html = `<div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 1rem;">`;
        recursos.forEach(r => {
            const meta = r.meta || {};
            const icon = meta.icono || '📚';
            const color = meta.color || '#7e22ce';
            const colorBg = meta.color_bg || '#f3e8ff';
            const ultimaEdicion = r.fecha_ultima_edicion ? r.fecha_ultima_edicion.substring(0, 16).replace('T', ' ') : 'Reciente';
            const editadoPor = r.ultima_edicion_por === 'paciente' ? '👤 Consultante' : '🩺 Terapeuta';

            html += `
            <div class="card" style="background: #ffffff; border-radius: 14px; border: 1.5px solid #e2e8f0; padding: 1.15rem; display: flex; flex-direction: column; justify-content: space-between; box-shadow: 0 2px 10px rgba(0,0,0,0.02);">
                <div>
                    <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.6rem;">
                        <span style="font-size: 1.6rem; padding: 0.35rem 0.5rem; background: ${colorBg}; border-radius: 10px;">
                            ${icon}
                        </span>
                        <span style="font-size: 0.72rem; font-weight: 700; color: ${color}; background: ${colorBg}; padding: 0.15rem 0.55rem; border-radius: 10px;">
                            ${meta.titulo ? meta.titulo.split('(')[0].trim() : 'Recurso'}
                        </span>
                    </div>
                    <h4 style="margin: 0 0 0.35rem 0; font-size: 1.02rem; font-weight: 800; color: #0f172a;">
                        ${r.titulo}
                    </h4>
                    <div style="display: flex; flex-wrap: wrap; gap: 0.5rem; margin-bottom: 0.75rem; font-size: 0.76rem; color: #64748b;">
                        <span>📅 ${ultimaEdicion}</span>
                        <span style="font-weight: 600; color: ${r.ultima_edicion_por === 'paciente' ? '#2563eb' : '#7e22ce'};">
                            ${editadoPor}
                        </span>
                    </div>
                </div>

                <div style="border-top: 1px solid #f1f5f9; padding-top: 0.75rem; display: flex; justify-content: space-between; align-items: center; gap: 0.4rem; flex-wrap: wrap;">
                    <button type="button" class="btn btn-sm btn-primary" onclick="openRecursoPizarra(${r.id})" style="font-weight: 700; font-size: 0.8rem; padding: 0.35rem 0.85rem; border-radius: 6px; background: ${color}; border: none; flex: 1;">
                        ✏️ Abrir Pizarra
                    </button>
                    <button type="button" class="btn btn-sm btn-secondary" onclick="exportRecursoWordById(${r.id})" title="Descargar Word (.docx)" style="font-size: 0.8rem; padding: 0.35rem 0.55rem; border-radius: 6px; background: white; border: 1.5px solid #cbd5e1;">
                        📥
                    </button>
                    ${!isPatientPortal ? `
                    <button type="button" class="btn btn-sm" onclick="shareRecursoWhatsAppById(${r.id})" title="Enviar por WhatsApp" style="font-size: 0.8rem; padding: 0.35rem 0.55rem; border-radius: 6px; background: #dcfce7; color: #16a34a; border: 1px solid #86efac;">
                        📲
                    </button>
                    <button type="button" class="btn btn-sm" onclick="deleteRecursoPizarra(${r.id})" title="Eliminar Pizarra" style="font-size: 0.8rem; padding: 0.35rem 0.55rem; border-radius: 6px; background: #fee2e2; color: #dc2626; border: none;">
                        🗑️
                    </button>` : ''}
                </div>
            </div>`;
        });
        html += `</div>`;
        container.innerHTML = html;
    }

    // =========================================================================
    // 2. MODAL ASIGNAR RECURSO
    // =========================================================================

    async function openAsignarRecursoModal(preselectedTipo) {
        await populateRecursosPatientSelector();

        if (preselectedTipo) {
            const selectTipo = document.getElementById('asig-rec-tipo');
            if (selectTipo) selectTipo.value = preselectedTipo;
        }

        // Si ya hay un consultante seleccionado en la pestaña, autoseleccionarlo
        if (window.selectedRecursoPatientId) {
            selectRecursoPatient(window.selectedRecursoPatientId);
        } else {
            clearRecursoSelectedPatient();
        }

        const inputTit = document.getElementById('asig-rec-titulo');
        if (inputTit) inputTit.value = '';

        if (typeof openModal === 'function') {
            openModal('modal-asignar-recurso');
        } else {
            const modal = document.getElementById('modal-asignar-recurso');
            if (modal) {
                modal.classList.remove('hide');
                modal.style.setProperty('display', 'flex', 'important');
            }
        }
    }
    window.openAsignarRecursoModal = openAsignarRecursoModal;

    function onAsigRecTipoChange(tipo) {
        // Puede autogenerar sugerencia de título si está vacío
    }
    window.onAsigRecTipoChange = onAsigRecTipoChange;

    async function handleCrearRecursoSubmit(e) {
        e.preventDefault();
        const pacienteId = document.getElementById('asig-rec-paciente')?.value;
        const recursoTipo = document.getElementById('asig-rec-tipo')?.value;
        const titulo = document.getElementById('asig-rec-titulo')?.value;
        const btn = document.getElementById('btn-crear-pizarra-submit');

        if (!pacienteId || !recursoTipo) {
            alert("Por favor busca y selecciona un consultante registrado.");
            return;
        }

        if (btn) {
            btn.disabled = true;
            btn.textContent = 'Creando pizarra...';
        }

        try {
            const res = await fetch('/api/recursos/asignar', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    paciente_id: parseInt(pacienteId),
                    recurso_tipo: recursoTipo,
                    titulo: titulo
                })
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.error || 'Error al crear recurso');

            closeModal('modal-asignar-recurso');

            // Actualizar vista de pizarras del paciente
            selectRecursoFilterPatient(pacienteId);

            // Abrir de inmediato la pizarra creada para trabajar
            openRecursoPizarra(data.recurso_id);
        } catch (err) {
            alert(err.message);
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.textContent = '🚀 Crear y Abrir Pizarra';
            }
        }
    }
    window.handleCrearRecursoSubmit = handleCrearRecursoSubmit;

    // =========================================================================
    // 3. PIZARRA INTERACTIVA COLABORATIVA (MODAL & REAL-TIME)
    // =========================================================================

    async function openRecursoPizarra(recursoId) {
        const modal = document.getElementById('modal-recurso-pizarra');
        const dynamicContent = document.getElementById('recurso-pizarra-dynamic-content');
        if (!modal || !dynamicContent) return;

        dynamicContent.innerHTML = '<p class="text-muted text-center py-5">Cargando pizarra colaborativa...</p>';
        if (typeof openModal === 'function') {
            openModal('modal-recurso-pizarra');
        } else {
            modal.classList.remove('hide');
            modal.style.setProperty('display', 'flex', 'important');
        }

        try {
            const res = await fetch(`/api/recursos/pizarra/${recursoId}`);
            if (!res.ok) throw new Error('No se pudo abrir la pizarra.');
            const data = await res.json();

            window.activeRecursoPizarra = data;
            window.lastSyncedTimestamp = data.fecha_ultima_edicion;

            // Encabezado
            const meta = data.meta || {};
            const iconEl = document.getElementById('pizarra-rec-icon');
            if (iconEl) iconEl.textContent = meta.icono || '📚';

            const titleEl = document.getElementById('pizarra-rec-title');
            if (titleEl) titleEl.textContent = data.titulo || meta.titulo;

            const pacBadge = document.getElementById('pizarra-rec-patient-badge');
            if (pacBadge) pacBadge.textContent = `Consultante: ${data.pac_nombres || ''} ${data.pac_apellidos || ''}`.trim();

            const lastEdText = document.getElementById('pizarra-last-edited-text');
            if (lastEdText) {
                const edBy = data.ultima_edicion_por === 'paciente' ? 'Consultante' : 'Terapeuta';
                const fecha = (data.fecha_ultima_edicion || '').substring(0, 16).replace('T', ' ');
                lastEdText.textContent = `Última edición: ${fecha} (${edBy})`;
            }

            updateSaveStatusBadge('synced');

            // Renderizar la herramienta interactiva específica
            renderSpecificInteractiveTool(data);

            // Iniciar polling de sincronización colaborativa
            startPizarraLiveSync(recursoId);

        } catch (e) {
            console.error(e);
            dynamicContent.innerHTML = `<p class="text-danger text-center py-5">${e.message}</p>`;
        }
    }
    window.openRecursoPizarra = openRecursoPizarra;

    function renderSpecificInteractiveTool(data) {
        const container = document.getElementById('recurso-pizarra-dynamic-content');
        if (!container) return;

        const type = data.recurso_tipo;
        const content = data.contenido || {};
        const meta = data.meta || {};

        switch (type) {
            case 'pros_contras':
                container.innerHTML = getProsContrasHTML(content);
                recalculateProsContras();
                break;
            case 'cuestionando_creencias':
                container.innerHTML = getCuestionandoCreenciasHTML(content, meta);
                break;
            case 'diversificando_pensamiento':
                container.innerHTML = getDiversificandoPensamientoHTML(content, meta);
                break;
            case 'pensamientos_negativos':
                container.innerHTML = getPensamientosNegativosHTML(content);
                break;
            case 'segmentacion_objetivos':
                container.innerHTML = getSegmentacionObjetivosHTML(content);
                break;
            case 'sobrepensamiento':
                container.innerHTML = getSobrepensamientoHTML(content);
                break;
            default:
                container.innerHTML = '<p class="text-muted">Tipo de recurso no reconocido.</p>';
        }
    }

    // =========================================================================
    // 4. PLANTILLAS INTERACTIVAS (HOMOLOGACIÓN CLINICA)
    // =========================================================================

    // --- A. PROS Y CONTRAS (SUMAS Y RESTAS AUTOMÁTICAS) ---
    function getProsContrasHTML(c) {
        const altA = c.alternativa_a || 'Alternativa A (Ej: Cambiar de trabajo)';
        const altB = c.alternativa_b || 'Alternativa B (Ej: Quedarme en el trabajo actual)';
        const prosA = c.pros_a && c.pros_a.length ? c.pros_a : [{ texto: '', pts: 0 }];
        const contrasA = c.contras_a && c.contras_a.length ? c.contras_a : [{ texto: '', pts: 0 }];
        const prosB = c.pros_b && c.pros_b.length ? c.pros_b : [{ texto: '', pts: 0 }];
        const contrasB = c.contras_b && c.contras_b.length ? c.contras_b : [{ texto: '', pts: 0 }];

        return `
        <div style="display: flex; flex-direction: column; gap: 1.25rem;">
            <!-- Aviso Psicoeducativo -->
            <div style="background: #faf5ff; border: 1.5px solid #d8b4fe; border-radius: 12px; padding: 0.85rem 1rem; color: #581c87; font-size: 0.85rem; line-height: 1.45;">
                ⚖️ <strong>Regla de Decisión:</strong> Califica cada pro y contra del <strong>1 al 5</strong> según su impacto real en tu vida (1 = Bajo impacto, 5 = Impacto determinante). 
                El sistema calculará automáticamente: <em>Balance = Suma de Pros - Suma de Contras</em>. Toda decisión tiene renuncias inevitables.
            </div>

            <!-- Definición de Alternativas -->
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem;">
                <div style="background: #ffffff; border: 2px solid #7e22ce; border-radius: 12px; padding: 0.85rem;">
                    <label style="font-weight: 800; font-size: 0.82rem; color: #7e22ce; display: block; margin-bottom: 0.3rem;">
                        OPCIÓN / ALTERNATIVA A:
                    </label>
                    <input type="text" id="pc-alt-a" value="${escapeHtml(altA)}" oninput="triggerRecursoAutoSave(); syncOptionTitles();" placeholder="Nombre de la Alternativa A..." style="width: 100%; padding: 0.5rem 0.75rem; border-radius: 8px; border: 1.5px solid #cbd5e1; font-weight: 700; font-size: 0.95rem;">
                </div>
                <div style="background: #ffffff; border: 2px solid #2563eb; border-radius: 12px; padding: 0.85rem;">
                    <label style="font-weight: 800; font-size: 0.82rem; color: #2563eb; display: block; margin-bottom: 0.3rem;">
                        OPCIÓN / ALTERNATIVA B:
                    </label>
                    <input type="text" id="pc-alt-b" value="${escapeHtml(altB)}" oninput="triggerRecursoAutoSave(); syncOptionTitles();" placeholder="Nombre de la Alternativa B..." style="width: 100%; padding: 0.5rem 0.75rem; border-radius: 8px; border: 1.5px solid #cbd5e1; font-weight: 700; font-size: 0.95rem;">
                </div>
            </div>

            <!-- TABLERO COMPARATIVO DE DOS COLUMNAS -->
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 1.25rem;">
                
                <!-- COLUMNA ALTERNATIVA A -->
                <div style="background: #ffffff; border: 1.5px solid #e2e8f0; border-radius: 14px; padding: 1rem; display: flex; flex-direction: column; gap: 1rem;">
                    <h4 id="pc-lbl-col-a" style="margin: 0; color: #7e22ce; font-weight: 800; font-size: 1rem; border-bottom: 2px solid #f3e8ff; padding-bottom: 0.4rem;">
                        ${escapeHtml(altA)}
                    </h4>

                    <!-- PROS A -->
                    <div>
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.4rem;">
                            <span style="font-weight: 700; font-size: 0.82rem; color: #15803d;">➕ PROS (Impacto Positivo 1-5):</span>
                            <button type="button" class="btn btn-sm" onclick="addProsContrasRow('pros_a')" style="font-size: 0.75rem; padding: 0.2rem 0.5rem; background: #dcfce7; color: #166534; border: none; border-radius: 6px; font-weight: 700; cursor: pointer;">+ Añadir Pro</button>
                        </div>
                        <div id="pc-rows-pros-a" style="display: flex; flex-direction: column; gap: 0.4rem;">
                            ${renderProsContrasRowList('pros_a', prosA)}
                        </div>
                        <div style="text-align: right; margin-top: 0.4rem; font-size: 0.8rem; font-weight: 700; color: #15803d;">
                            Subtotal Pros A: <span id="pc-sub-pros-a">0</span> pts
                        </div>
                    </div>

                    <!-- CONTRAS A -->
                    <div style="border-top: 1px dashed #e2e8f0; padding-top: 0.75rem;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.4rem;">
                            <span style="font-weight: 700; font-size: 0.82rem; color: #b91c1c;">➖ CONTRAS (Impacto Negativo 1-5):</span>
                            <button type="button" class="btn btn-sm" onclick="addProsContrasRow('contras_a')" style="font-size: 0.75rem; padding: 0.2rem 0.5rem; background: #fee2e2; color: #991b1b; border: none; border-radius: 6px; font-weight: 700; cursor: pointer;">+ Añadir Contra</button>
                        </div>
                        <div id="pc-rows-contras-a" style="display: flex; flex-direction: column; gap: 0.4rem;">
                            ${renderProsContrasRowList('contras_a', contrasA)}
                        </div>
                        <div style="text-align: right; margin-top: 0.4rem; font-size: 0.8rem; font-weight: 700; color: #b91c1c;">
                            Subtotal Contras A: <span id="pc-sub-contras-a">0</span> pts
                        </div>
                    </div>

                    <!-- BALANCE FINAL A -->
                    <div style="background: #faf5ff; border: 1.5px solid #d8b4fe; border-radius: 10px; padding: 0.75rem; display: flex; justify-content: space-between; align-items: center; margin-top: auto;">
                        <span style="font-weight: 800; font-size: 0.88rem; color: #581c87;">BALANCE TOTAL (A):</span>
                        <span id="pc-balance-a" style="font-size: 1.25rem; font-weight: 900; color: #7e22ce;">0</span>
                    </div>
                </div>

                <!-- COLUMNA ALTERNATIVA B -->
                <div style="background: #ffffff; border: 1.5px solid #e2e8f0; border-radius: 14px; padding: 1rem; display: flex; flex-direction: column; gap: 1rem;">
                    <h4 id="pc-lbl-col-b" style="margin: 0; color: #2563eb; font-weight: 800; font-size: 1rem; border-bottom: 2px solid #dbeafe; padding-bottom: 0.4rem;">
                        ${escapeHtml(altB)}
                    </h4>

                    <!-- PROS B -->
                    <div>
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.4rem;">
                            <span style="font-weight: 700; font-size: 0.82rem; color: #15803d;">➕ PROS (Impacto Positivo 1-5):</span>
                            <button type="button" class="btn btn-sm" onclick="addProsContrasRow('pros_b')" style="font-size: 0.75rem; padding: 0.2rem 0.5rem; background: #dcfce7; color: #166534; border: none; border-radius: 6px; font-weight: 700; cursor: pointer;">+ Añadir Pro</button>
                        </div>
                        <div id="pc-rows-pros-b" style="display: flex; flex-direction: column; gap: 0.4rem;">
                            ${renderProsContrasRowList('pros_b', prosB)}
                        </div>
                        <div style="text-align: right; margin-top: 0.4rem; font-size: 0.8rem; font-weight: 700; color: #15803d;">
                            Subtotal Pros B: <span id="pc-sub-pros-b">0</span> pts
                        </div>
                    </div>

                    <!-- CONTRAS B -->
                    <div style="border-top: 1px dashed #e2e8f0; padding-top: 0.75rem;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.4rem;">
                            <span style="font-weight: 700; font-size: 0.82rem; color: #b91c1c;">➖ CONTRAS (Impacto Negativo 1-5):</span>
                            <button type="button" class="btn btn-sm" onclick="addProsContrasRow('contras_b')" style="font-size: 0.75rem; padding: 0.2rem 0.5rem; background: #fee2e2; color: #991b1b; border: none; border-radius: 6px; font-weight: 700; cursor: pointer;">+ Añadir Contra</button>
                        </div>
                        <div id="pc-rows-contras-b" style="display: flex; flex-direction: column; gap: 0.4rem;">
                            ${renderProsContrasRowList('contras_b', contrasB)}
                        </div>
                        <div style="text-align: right; margin-top: 0.4rem; font-size: 0.8rem; font-weight: 700; color: #b91c1c;">
                            Subtotal Contras B: <span id="pc-sub-contras-b">0</span> pts
                        </div>
                    </div>

                    <!-- BALANCE FINAL B -->
                    <div style="background: #eff6ff; border: 1.5px solid #bfdbfe; border-radius: 10px; padding: 0.75rem; display: flex; justify-content: space-between; align-items: center; margin-top: auto;">
                        <span style="font-weight: 800; font-size: 0.88rem; color: #1e40af;">BALANCE TOTAL (B):</span>
                        <span id="pc-balance-b" style="font-size: 1.25rem; font-weight: 900; color: #2563eb;">0</span>
                    </div>
                </div>
            </div>

            <!-- VEREDICTO NUMÉRICO Y REFLEXIÓN EMOCIONAL -->
            <div style="background: #ffffff; border: 1.5px solid #e2e8f0; border-radius: 14px; padding: 1.15rem; display: flex; flex-direction: column; gap: 0.85rem;">
                <div id="pc-verdict-banner" style="background: #f8fafc; border: 1.5px solid #cbd5e1; border-radius: 8px; padding: 0.65rem 0.85rem; font-weight: 700; font-size: 0.88rem; color: #334155; text-align: center;">
                    ⚖️ Completa las puntuaciones para ver el resultado cuantitativo.
                </div>

                <div>
                    <label style="font-weight: 700; font-size: 0.82rem; color: #475569; display: block; margin-bottom: 0.25rem;">
                        ¿Cómo te hace sentir este resultado? (Validación emocional de la decisión):
                    </label>
                    <textarea id="pc-reflexion-emocional" rows="2" oninput="triggerRecursoAutoSave()" placeholder="A veces la opción con más puntos produce miedo o alivio. ¿Qué sientes al ver los números?..." style="width: 100%; padding: 0.5rem; border-radius: 8px; border: 1.5px solid #cbd5e1; font-size: 0.85rem; font-family: inherit;">${escapeHtml(c.reflexion_emocional || '')}</textarea>
                </div>

                <div>
                    <label style="font-weight: 700; font-size: 0.82rem; color: #475569; display: block; margin-bottom: 0.25rem;">
                        Decisión o Camino a Seguir Acordado:
                    </label>
                    <input type="text" id="pc-decision-final" value="${escapeHtml(c.decision_final || '')}" oninput="triggerRecursoAutoSave()" placeholder="Ej: Avanzar con la opción B dando un primer paso este viernes..." style="width: 100%; padding: 0.5rem; border-radius: 8px; border: 1.5px solid #cbd5e1; font-size: 0.88rem; font-weight: 600;">
                </div>
            </div>
        </div>`;
    }

    function renderProsContrasRowList(listKey, rows) {
        let html = '';
        rows.forEach((r, idx) => {
            html += `
            <div class="pc-row-item" data-key="${listKey}" style="display: flex; gap: 0.4rem; align-items: center;">
                <input type="text" class="pc-row-text" value="${escapeHtml(r.texto || '')}" oninput="triggerRecursoAutoSave()" placeholder="Escribe un punto..." style="flex: 1; padding: 0.35rem 0.55rem; border-radius: 6px; border: 1px solid #cbd5e1; font-size: 0.82rem;">
                <select class="pc-row-pts" onchange="recalculateProsContras(); triggerRecursoAutoSave();" style="width: 68px; padding: 0.35rem 0.25rem; border-radius: 6px; border: 1px solid #cbd5e1; font-weight: 700; font-size: 0.82rem; background: white; cursor: pointer;">
                    <option value="0" ${Number(r.pts) === 0 ? 'selected' : ''}>0 pts</option>
                    <option value="1" ${Number(r.pts) === 1 ? 'selected' : ''}>1 pt</option>
                    <option value="2" ${Number(r.pts) === 2 ? 'selected' : ''}>2 pts</option>
                    <option value="3" ${Number(r.pts) === 3 ? 'selected' : ''}>3 pts</option>
                    <option value="4" ${Number(r.pts) === 4 ? 'selected' : ''}>4 pts</option>
                    <option value="5" ${Number(r.pts) === 5 ? 'selected' : ''}>5 pts</option>
                </select>
                <button type="button" onclick="removeProsContrasRow('${listKey}', this)" style="background: none; border: none; color: #94a3b8; font-weight: 700; cursor: pointer; padding: 0 4px; font-size: 0.9rem;" title="Eliminar fila">✕</button>
            </div>`;
        });
        return html;
    }

    function addProsContrasRow(listKey) {
        const containerMap = {
            'pros_a': 'pc-rows-pros-a',
            'contras_a': 'pc-rows-contras-a',
            'pros_b': 'pc-rows-pros-b',
            'contras_b': 'pc-rows-contras-b'
        };
        const container = document.getElementById(containerMap[listKey]);
        if (!container) return;

        const div = document.createElement('div');
        div.className = 'pc-row-item';
        div.dataset.key = listKey;
        div.style.cssText = 'display: flex; gap: 0.4rem; align-items: center;';
        div.innerHTML = `
            <input type="text" class="pc-row-text" value="" oninput="triggerRecursoAutoSave()" placeholder="Escribe un punto..." style="flex: 1; padding: 0.35rem 0.55rem; border-radius: 6px; border: 1px solid #cbd5e1; font-size: 0.82rem;">
            <select class="pc-row-pts" onchange="recalculateProsContras(); triggerRecursoAutoSave();" style="width: 68px; padding: 0.35rem 0.25rem; border-radius: 6px; border: 1px solid #cbd5e1; font-weight: 700; font-size: 0.82rem; background: white; cursor: pointer;">
                <option value="0">0 pts</option>
                <option value="1">1 pt</option>
                <option value="2">2 pts</option>
                <option value="3" selected>3 pts</option>
                <option value="4">4 pts</option>
                <option value="5">5 pts</option>
            </select>
            <button type="button" onclick="removeProsContrasRow('${listKey}', this)" style="background: none; border: none; color: #94a3b8; font-weight: 700; cursor: pointer; padding: 0 4px; font-size: 0.9rem;" title="Eliminar fila">✕</button>
        `;
        container.appendChild(div);
        div.querySelector('input').focus();
        recalculateProsContras();
        triggerRecursoAutoSave();
    }
    window.addProsContrasRow = addProsContrasRow;

    function removeProsContrasRow(listKey, btn) {
        const row = btn.closest('.pc-row-item');
        if (row) {
            row.remove();
            recalculateProsContras();
            triggerRecursoAutoSave();
        }
    }
    window.removeProsContrasRow = removeProsContrasRow;

    function syncOptionTitles() {
        const aVal = document.getElementById('pc-alt-a')?.value.trim() || 'Alternativa A';
        const bVal = document.getElementById('pc-alt-b')?.value.trim() || 'Alternativa B';
        const lblA = document.getElementById('pc-lbl-col-a');
        const lblB = document.getElementById('pc-lbl-col-b');
        if (lblA) lblA.textContent = aVal;
        if (lblB) lblB.textContent = bVal;
    }
    window.syncOptionTitles = syncOptionTitles;

    function recalculateProsContras() {
        const getSum = (containerId) => {
            const container = document.getElementById(containerId);
            if (!container) return 0;
            let sum = 0;
            container.querySelectorAll('.pc-row-pts').forEach(sel => {
                sum += parseInt(sel.value) || 0;
            });
            return sum;
        };

        const sumProsA = getSum('pc-rows-pros-a');
        const sumContrasA = getSum('pc-rows-contras-a');
        const balA = sumProsA - sumContrasA;

        const sumProsB = getSum('pc-rows-pros-b');
        const sumContrasB = getSum('pc-rows-contras-b');
        const balB = sumProsB - sumContrasB;

        const elSubProsA = document.getElementById('pc-sub-pros-a');
        const elSubContrasA = document.getElementById('pc-sub-contras-a');
        const elBalA = document.getElementById('pc-balance-a');

        const elSubProsB = document.getElementById('pc-sub-pros-b');
        const elSubContrasB = document.getElementById('pc-sub-contras-b');
        const elBalB = document.getElementById('pc-balance-b');

        if (elSubProsA) elSubProsA.textContent = sumProsA;
        if (elSubContrasA) elSubContrasA.textContent = sumContrasA;
        if (elBalA) {
            elBalA.textContent = (balA > 0 ? `+${balA}` : balA);
            elBalA.style.color = balA >= 0 ? '#15803d' : '#b91c1c';
        }

        if (elSubProsB) elSubProsB.textContent = sumProsB;
        if (elSubContrasB) elSubContrasB.textContent = sumContrasB;
        if (elBalB) {
            elBalB.textContent = (balB > 0 ? `+${balB}` : balB);
            elBalB.style.color = balB >= 0 ? '#15803d' : '#b91c1c';
        }

        const banner = document.getElementById('pc-verdict-banner');
        if (banner) {
            const nameA = document.getElementById('pc-alt-a')?.value.trim() || 'Alternativa A';
            const nameB = document.getElementById('pc-alt-b')?.value.trim() || 'Alternativa B';

            if (balA === 0 && balB === 0 && sumProsA === 0 && sumProsB === 0) {
                banner.innerHTML = `⚖️ Completa las puntuaciones para ver el resultado cuantitativo.`;
                banner.style.background = '#f8fafc';
                banner.style.borderColor = '#cbd5e1';
                banner.style.color = '#334155';
            } else if (balA > balB) {
                banner.innerHTML = `🏆 <strong>Opción con mayor puntuación neta:</strong> ${escapeHtml(nameA)} (+${balA} vs ${balB > 0 ? '+' : ''}${balB})`;
                banner.style.background = '#f3e8ff';
                banner.style.borderColor = '#d8b4fe';
                banner.style.color = '#6b21a8';
            } else if (balB > balA) {
                banner.innerHTML = `🏆 <strong>Opción con mayor puntuación neta:</strong> ${escapeHtml(nameB)} (+${balB} vs ${balA > 0 ? '+' : ''}${balA})`;
                banner.style.background = '#eff6ff';
                banner.style.borderColor = '#bfdbfe';
                banner.style.color = '#1e40af';
            } else {
                banner.innerHTML = `🤝 <strong>Empate exacto:</strong> Ambas alternativas tienen el mismo balance neto (${balA} pts). Es momento de priorizar los valores personales y la intuición.`;
                banner.style.background = '#fefce8';
                banner.style.borderColor = '#fef08a';
                banner.style.color = '#854d0e';
            }
        }
    }
    window.recalculateProsContras = recalculateProsContras;

    // --- B. CUESTIONANDO CREENCIAS (1 PREGUNTA A LA VEZ) ---
    function getCuestionandoCreenciasHTML(c, meta) {
        const banco = meta.preguntas_banco || [];
        const apertura = c.tipo_apertura || 'Tengo el pensamiento de que:';
        const pensamiento = c.pensamiento_central || '';
        const respuestas = c.respuestas || {};
        const preguntasSelec = c.preguntas_seleccionadas && c.preguntas_seleccionadas.length ? c.preguntas_seleccionadas : (Object.keys(respuestas).length ? Object.keys(respuestas) : ['p1']);
        const activeQId = preguntasSelec[0] || 'p1';

        let optionsQuestions = '';
        banco.forEach(q => {
            optionsQuestions += `<option value="${q.id}" ${q.id === activeQId ? 'selected' : ''}>[${q.categoria}] ${q.texto}</option>`;
        });

        return `
        <div style="display: flex; flex-direction: column; gap: 1.25rem;">
            <!-- Aviso Psicoeducativo -->
            <div style="background: #eff6ff; border: 1.5px solid #bfdbfe; border-radius: 12px; padding: 0.85rem 1rem; color: #1e40af; font-size: 0.85rem; line-height: 1.45;">
                🔍 <strong>Diálogo Socrático Enfocado:</strong> Para evitar el agobio mental, no responderás todas las preguntas a la vez. 
                Primero identifica el pensamiento automático y luego escoge <strong>1 sola pregunta</strong> para profundizar con calma.
            </div>

            <!-- PASO 1: IDENTIFICACIÓN DEL PENSAMIENTO -->
            <div class="card" style="background: #ffffff; border: 1.5px solid #e2e8f0; border-radius: 14px; padding: 1.15rem;">
                <h4 style="margin: 0 0 0.5rem 0; font-size: 0.95rem; font-weight: 800; color: #1e293b; display: flex; align-items: center; gap: 6px;">
                    <span>1️⃣</span> Identifica el Pensamiento o Creencia que genera malestar
                </h4>
                <div style="display: flex; gap: 0.65rem; flex-wrap: wrap; align-items: center; margin-bottom: 0.5rem;">
                    <select id="cc-tipo-apertura" onchange="triggerRecursoAutoSave()" style="padding: 0.5rem 0.75rem; border-radius: 8px; border: 1.5px solid #cbd5e1; font-weight: 700; font-size: 0.88rem; background: #f8fafc; color: #2563eb;">
                        <option value="Tengo el pensamiento de que:" ${apertura === 'Tengo el pensamiento de que:' ? 'selected' : ''}>Tengo el pensamiento de que:</option>
                        <option value="Yo creo que:" ${apertura === 'Yo creo que:' ? 'selected' : ''}>Yo creo que:</option>
                        <option value="Tengo la creencia de que:" ${apertura === 'Tengo la creencia de que:' ? 'selected' : ''}>Tengo la creencia de que:</option>
                        <option value="Tengo la idea de que:" ${apertura === 'Tengo la idea de que:' ? 'selected' : ''}>Tengo la idea de que:</option>
                    </select>
                </div>
                <textarea id="cc-pensamiento-central" rows="2" oninput="triggerRecursoAutoSave()" placeholder="Escribe aquí el pensamiento exacto (Ej: 'Si voy a esa reunión voy a hacer el ridículo y todos me juzgarán')..." style="width: 100%; padding: 0.6rem; border-radius: 8px; border: 1.5px solid #cbd5e1; font-size: 0.95rem; font-weight: 600; font-family: inherit;">${escapeHtml(pensamiento)}</textarea>
            </div>

            <!-- PASO 2: SELECCIÓN DE 1 PREGUNTA Y REFLEXIÓN PROFUNDA -->
            <div class="card" style="background: #ffffff; border: 2px solid #2563eb; border-radius: 14px; padding: 1.25rem;">
                <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.5rem; margin-bottom: 0.85rem;">
                    <h4 style="margin: 0; font-size: 0.95rem; font-weight: 800; color: #1e40af; display: flex; align-items: center; gap: 6px;">
                        <span>2️⃣</span> Elige 1 Pregunta para Debatir este Pensamiento
                    </h4>
                    <span style="font-size: 0.76rem; font-weight: 700; background: #dbeafe; color: #1e40af; padding: 0.2rem 0.6rem; border-radius: 10px;">
                        1 pregunta activa
                    </span>
                </div>

                <div style="margin-bottom: 1rem;">
                    <label style="font-weight: 700; font-size: 0.82rem; color: #475569; display: block; margin-bottom: 0.35rem;">
                        Selecciona el ángulo de cuestionamiento:
                    </label>
                    <select id="cc-pregunta-select" onchange="onSelectCuestionandoPregunta(this.value)" style="width: 100%; padding: 0.6rem 0.85rem; border-radius: 8px; border: 1.5px solid #93c5fd; font-weight: 700; font-size: 0.9rem; background: #f0f7ff; color: #1e40af;">
                        ${optionsQuestions}
                    </select>
                </div>

                <!-- CONTENEDOR DE LA PREGUNTA ACTIVA -->
                <div id="cc-workspace-pregunta" style="background: #fafafa; border: 1.5px solid #e2e8f0; border-radius: 10px; padding: 1rem;">
                    ${renderCuestionandoPreguntaWorkspace(activeQId, banco, respuestas[activeQId] || '')}
                </div>

                <!-- PREGUNTAS ADICIONALES (SI SE QUIERE AGREGAR MÁS) -->
                <div id="cc-preguntas-adicionales-container" style="margin-top: 1rem; display: flex; flex-direction: column; gap: 0.85rem;">
                    ${renderPreguntasAdicionalesList(preguntasSelec.slice(1), banco, respuestas)}
                </div>

                <div style="margin-top: 1rem; display: flex; justify-content: flex-end;">
                    <button type="button" class="btn btn-sm" onclick="addAnotherCuestionandoPregunta()" style="font-weight: 700; font-size: 0.8rem; padding: 0.35rem 0.85rem; background: #eff6ff; color: #2563eb; border: 1.5px solid #bfdbfe; border-radius: 8px; cursor: pointer;">
                        ➕ Trabajar con otra pregunta adicional
                    </button>
                </div>
            </div>

            <!-- PASO 3: PENSAMIENTO ALTERNATIVO Y CONCLUSIÓN -->
            <div class="card" style="background: #ffffff; border: 1.5px solid #16a34a; border-radius: 14px; padding: 1.15rem;">
                <h4 style="margin: 0 0 0.5rem 0; font-size: 0.95rem; font-weight: 800; color: #166534; display: flex; align-items: center; gap: 6px;">
                    <span>3️⃣</span> Conclusión / Pensamiento Alternativo Más Realista
                </h4>
                <p style="margin: 0 0 0.5rem 0; font-size: 0.82rem; color: #64748b;">
                    A la luz de tu reflexión, ¿cómo formularías ahora esta idea de forma más justa y adaptativa?
                </p>
                <textarea id="cc-conclusion-realista" rows="2" oninput="triggerRecursoAutoSave()" placeholder="Ej: 'Es normal sentirme nervioso, pero ya me he preparado y la gente suele estar enfocada en sus propios asuntos, no en juzgarme'..." style="width: 100%; padding: 0.6rem; border-radius: 8px; border: 1.5px solid #86efac; font-size: 0.92rem; font-weight: 600; font-family: inherit; background: #f0fdf4;">${escapeHtml(c.conclusion_realista || '')}</textarea>
            </div>
        </div>`;
    }

    function renderCuestionandoPreguntaWorkspace(qId, banco, respuestaTexto) {
        const item = banco.find(b => b.id === qId) || banco[0] || { id: 'p1', texto: '¿Qué pruebas tienes?' };
        return `
        <div class="cc-q-block" data-qid="${item.id}">
            <div style="display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.45rem;">
                <span style="font-size: 1.1rem;">💬</span>
                <strong style="color: #1e3a8a; font-size: 0.95rem;">${escapeHtml(item.texto)}</strong>
            </div>
            <textarea class="cc-q-answer" oninput="triggerRecursoAutoSave()" rows="3" placeholder="Redacta aquí tu análisis honesto y reflexivo..." style="width: 100%; padding: 0.6rem; border-radius: 8px; border: 1.5px solid #cbd5e1; font-size: 0.88rem; font-family: inherit; background: #ffffff;">${escapeHtml(respuestaTexto)}</textarea>
        </div>`;
    }

    function renderPreguntasAdicionalesList(qIds, banco, respuestas) {
        if (!qIds || qIds.length === 0) return '';
        let html = '';
        qIds.forEach(id => {
            const item = banco.find(b => b.id === id);
            if (item) {
                html += `
                <div class="cc-q-block" data-qid="${item.id}" style="background: #fafafa; border: 1.5px solid #e2e8f0; border-radius: 10px; padding: 1rem; position: relative;">
                    <button type="button" onclick="this.closest('.cc-q-block').remove(); triggerRecursoAutoSave();" style="position: absolute; right: 8px; top: 8px; background: none; border: none; color: #94a3b8; font-weight: 700; cursor: pointer;">✕</button>
                    <div style="display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.45rem;">
                        <span style="font-size: 1.1rem;">💬</span>
                        <strong style="color: #1e3a8a; font-size: 0.92rem;">${escapeHtml(item.texto)}</strong>
                    </div>
                    <textarea class="cc-q-answer" oninput="triggerRecursoAutoSave()" rows="3" placeholder="Redacta tu análisis..." style="width: 100%; padding: 0.6rem; border-radius: 8px; border: 1.5px solid #cbd5e1; font-size: 0.88rem; font-family: inherit; background: #ffffff;">${escapeHtml(respuestas[item.id] || '')}</textarea>
                </div>`;
            }
        });
        return html;
    }

    function onSelectCuestionandoPregunta(newQId) {
        const workspace = document.getElementById('cc-workspace-pregunta');
        if (!workspace) return;
        const meta = window.activeRecursoPizarra?.meta || {};
        const banco = meta.preguntas_banco || [];
        const prevText = workspace.querySelector('.cc-q-answer')?.value || '';

        // Si ya había texto en el recurso guardado, rescatarlo
        const respuestas = window.activeRecursoPizarra?.contenido?.respuestas || {};
        const textToUse = respuestas[newQId] || prevText;

        workspace.innerHTML = renderCuestionandoPreguntaWorkspace(newQId, banco, textToUse);
        triggerRecursoAutoSave();
    }
    window.onSelectCuestionandoPregunta = onSelectCuestionandoPregunta;

    function addAnotherCuestionandoPregunta() {
        const container = document.getElementById('cc-preguntas-adicionales-container');
        if (!container) return;

        const meta = window.activeRecursoPizarra?.meta || {};
        const banco = meta.preguntas_banco || [];

        // Encontrar una pregunta que no esté seleccionada
        const currentSelected = Array.from(document.querySelectorAll('.cc-q-block')).map(b => b.dataset.qid);
        const nextQ = banco.find(b => !currentSelected.includes(b.id)) || banco[0];

        const div = document.createElement('div');
        div.className = 'cc-q-block';
        div.dataset.qid = nextQ.id;
        div.style.cssText = 'background: #fafafa; border: 1.5px solid #e2e8f0; border-radius: 10px; padding: 1rem; position: relative;';
        div.innerHTML = `
            <button type="button" onclick="this.closest('.cc-q-block').remove(); triggerRecursoAutoSave();" style="position: absolute; right: 8px; top: 8px; background: none; border: none; color: #94a3b8; font-weight: 700; cursor: pointer;">✕</button>
            <div style="display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.45rem;">
                <span style="font-size: 1.1rem;">💬</span>
                <strong style="color: #1e3a8a; font-size: 0.92rem;">${escapeHtml(nextQ.texto)}</strong>
            </div>
            <textarea class="cc-q-answer" oninput="triggerRecursoAutoSave()" rows="3" placeholder="Redacta tu análisis..." style="width: 100%; padding: 0.6rem; border-radius: 8px; border: 1.5px solid #cbd5e1; font-size: 0.88rem; font-family: inherit; background: #ffffff;"></textarea>
        `;
        container.appendChild(div);
        div.querySelector('textarea').focus();
        triggerRecursoAutoSave();
    }
    window.addAnotherCuestionandoPregunta = addAnotherCuestionandoPregunta;

    // --- C. DIVERSIFICANDO EL PENSAMIENTO (6 SOMBREROS) ---
    function getDiversificandoPensamientoHTML(c, meta) {
        return `
        <div style="display: flex; flex-direction: column; gap: 1.25rem;">
            <!-- Aviso Psicoeducativo + Toggle Ejemplo -->
            <div style="background: #f0fdfa; border: 1.5px solid #99f6e4; border-radius: 12px; padding: 0.85rem 1rem; color: #115e59; font-size: 0.85rem; line-height: 1.45; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.5rem;">
                <div>
                    🧠 <strong>Técnica de los 6 Lentes:</strong> Pon a prueba un pensamiento rígido evaluándolo desde 6 ópticas diferentes para romper el sesgo de confirmación.
                </div>
                <button type="button" class="btn btn-sm" onclick="toggleDiversificandoEjemplo()" style="background: #ccfbf1; color: #0f766e; border: 1px solid #5eead4; font-weight: 700; border-radius: 6px; font-size: 0.78rem;">
                    👁️ Ver Caso de Ejemplo
                </button>
            </div>

            <!-- Caso clínico de ejemplo plegable -->
            <div id="dp-ejemplo-box" class="hide" style="background: #ffffff; border: 1.5px solid #cbd5e1; border-radius: 12px; padding: 1rem; font-size: 0.84rem; color: #334155;">
                <h5 style="margin: 0 0 0.4rem 0; font-size: 0.9rem; font-weight: 800; color: #0d9488;">Caso Clínico Modelado: 'Temor a volver a la universidad presencial por personas del pasado'</h5>
                <ul style="margin: 0; padding-left: 1.2rem; line-height: 1.5;">
                    <li><strong>Racional:</strong> La universidad tiene miles de personas; el título es un requisito, pero no el único.</li>
                    <li><strong>Emocional:</strong> Temo la ansiedad de un encuentro inesperado; me agobia volver a sentirme vulnerable.</li>
                    <li><strong>Crítico:</strong> Si huyo, pierdo tiempo y dinero, y refuerzo la idea de que esas personas aún controlan mis decisiones.</li>
                    <li><strong>Optimista:</strong> Enfrentar el entorno me demostrará cuánto he madurado y me devolverá mi espacio.</li>
                    <li><strong>Creativo:</strong> Diseñar una ruta segura o una respuesta ensayada (ej. 'Hola, voy tarde a clase, ¡éxito!').</li>
                    <li><strong>Organizado:</strong> El problema no es la carrera, sino el miedo al contacto. Dejar la carrera es una solución permanente para un problema transitorio.</li>
                </ul>
            </div>

            <!-- Pensamiento Central -->
            <div class="card" style="background: #ffffff; border: 1.5px solid #e2e8f0; border-radius: 14px; padding: 1rem;">
                <label style="font-weight: 800; font-size: 0.85rem; color: #0f766e; display: block; margin-bottom: 0.35rem;">
                    Pensamiento o Dilema Central:
                </label>
                <input type="text" id="dp-pensamiento-central" value="${escapeHtml(c.pensamiento_central || '')}" oninput="triggerRecursoAutoSave()" placeholder="Ej: 'No soporto la idea de regresar a mi trabajo presencial'..." style="width: 100%; padding: 0.55rem; border-radius: 8px; border: 1.5px solid #cbd5e1; font-size: 0.92rem; font-weight: 600;">
            </div>

            <!-- Cuadrícula de 6 Lentes -->
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(310px, 1fr)); gap: 1rem;">
                ${renderLenteCard('racional', 'Pensamiento Racional', '⚪', '#475569', '#f8fafc', 'Neutralidad y hechos objetivos, centrado en datos verificables.', c.racional)}
                ${renderLenteCard('emocional', 'Pensamiento Emocional', '🔴', '#dc2626', '#fef2f2', 'Intuición, sentimientos y temores sin necesidad de justificación.', c.emocional)}
                ${renderLenteCard('critico', 'Pensamiento Crítico', '⚫', '#1e293b', '#f1f5f9', 'Juicio cauteloso, pesimismo lógico y riesgos potenciales.', c.critico)}
                ${renderLenteCard('optimista', 'Pensamiento Optimista', '🟡', '#d97706', '#fffbeb', 'Búsqueda de beneficios, valor personal y viabilidad positiva.', c.optimista)}
                ${renderLenteCard('creativo', 'Pensamiento Creativo', '🟢', '#16a34a', '#f0fdf4', 'Alternativas novedosas, pensamiento lateral y soluciones laterales.', c.creativo)}
                ${renderLenteCard('organizado', 'Pensamiento Organizado', '🔵', '#2563eb', '#eff6ff', 'Gestión del proceso, visión panorámica y plan de acción.', c.organizado)}
            </div>

            <!-- Síntesis Global -->
            <div class="card" style="background: #ffffff; border: 1.5px solid #0d9488; border-radius: 14px; padding: 1rem;">
                <label style="font-weight: 800; font-size: 0.85rem; color: #0f766e; display: block; margin-bottom: 0.35rem;">
                    Síntesis Global (Visión equilibrada integrada):
                </label>
                <textarea id="dp-sintesis" rows="2" oninput="triggerRecursoAutoSave()" placeholder="¿Cuál es la conclusión integrando los 6 lentes?..." style="width: 100%; padding: 0.55rem; border-radius: 8px; border: 1.5px solid #99f6e4; font-size: 0.88rem; font-family: inherit;">${escapeHtml(c.sintesis || '')}</textarea>
            </div>
        </div>`;
    }

    function renderLenteCard(key, title, icon, color, bg, guia, val) {
        return `
        <div style="background: #ffffff; border: 1.5px solid ${color}44; border-radius: 12px; padding: 0.85rem; display: flex; flex-direction: column;">
            <div style="display: flex; align-items: center; gap: 0.4rem; margin-bottom: 0.25rem;">
                <span>${icon}</span>
                <strong style="color: ${color}; font-size: 0.88rem;">${title}</strong>
            </div>
            <p style="margin: 0 0 0.45rem 0; font-size: 0.74rem; color: #64748b;">${guia}</p>
            <textarea id="dp-lente-${key}" rows="2" oninput="triggerRecursoAutoSave()" placeholder="Tus reflexiones..." style="width: 100%; padding: 0.45rem; border-radius: 6px; border: 1px solid #cbd5e1; font-size: 0.82rem; font-family: inherit; background: ${bg}; flex: 1;">${escapeHtml(val || '')}</textarea>
        </div>`;
    }

    function toggleDiversificandoEjemplo() {
        const box = document.getElementById('dp-ejemplo-box');
        if (box) box.classList.toggle('hide');
    }
    window.toggleDiversificandoEjemplo = toggleDiversificandoEjemplo;

    // --- D. PENSAMIENTOS NEGATIVOS (REAL VS IMAGINARIO) ---
    function getPensamientosNegativosHTML(c) {
        const reales = c.situaciones_reales && c.situaciones_reales.length ? c.situaciones_reales : [''];
        const imag = c.situaciones_imaginarias && c.situaciones_imaginarias.length ? c.situaciones_imaginarias : [''];

        return `
        <div style="display: flex; flex-direction: column; gap: 1.25rem;">
            <div style="background: #fff7ed; border: 1.5px solid #fed7aa; border-radius: 12px; padding: 0.85rem 1rem; color: #9a3412; font-size: 0.85rem; line-height: 1.45;">
                🛡️ <strong>Discriminación de Realidad:</strong> Separa las situaciones que están ocurriendo con pruebas fácticas de aquellas que son suposiciones, lecturas de mente o temores no comprobados.
            </div>

            <!-- Malestar actual -->
            <div class="card" style="background: #ffffff; border: 1.5px solid #e2e8f0; border-radius: 14px; padding: 1rem;">
                <label style="font-weight: 800; font-size: 0.85rem; color: #ea580c; display: block; margin-bottom: 0.35rem;">
                    ¿Qué estás pensando? (Ideas que generan malestar ahora mismo):
                </label>
                <textarea id="pn-malestar" rows="2" oninput="triggerRecursoAutoSave()" placeholder="Escribe las ideas que están generando ansiedad o rumiación..." style="width: 100%; padding: 0.55rem; border-radius: 8px; border: 1.5px solid #cbd5e1; font-size: 0.9rem; font-family: inherit;">${escapeHtml(c.malestar_actual || '')}</textarea>
            </div>

            <!-- Dos Columnas -->
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem;">
                <!-- Reales -->
                <div style="background: #ffffff; border: 1.5px solid #16a34a; border-radius: 12px; padding: 1rem;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.4rem;">
                        <strong style="color: #15803d; font-size: 0.88rem;">SITUACIONES REALES</strong>
                        <button type="button" class="btn btn-sm" onclick="addNegativoItem('reales')" style="font-size: 0.72rem; padding: 0.15rem 0.45rem; background: #dcfce7; color: #166534; border: none; border-radius: 4px;">+ Añadir</button>
                    </div>
                    <p style="margin: 0 0 0.5rem 0; font-size: 0.73rem; color: #64748b;">Hechos observables, palabras explícitas, cosas que ya pasaron.</p>
                    <div id="pn-list-reales" style="display: flex; flex-direction: column; gap: 0.4rem;">
                        ${renderNegativosList('reales', reales)}
                    </div>
                </div>

                <!-- Imaginarias -->
                <div style="background: #ffffff; border: 1.5px solid #ea580c; border-radius: 12px; padding: 1rem;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.4rem;">
                        <strong style="color: #c2410c; font-size: 0.88rem;">SITUACIONES IMAGINARIAS</strong>
                        <button type="button" class="btn btn-sm" onclick="addNegativoItem('imaginarias')" style="font-size: 0.72rem; padding: 0.15rem 0.45rem; background: #ffedd5; color: #9a3412; border: none; border-radius: 4px;">+ Añadir</button>
                    </div>
                    <p style="margin: 0 0 0.5rem 0; font-size: 0.73rem; color: #64748b;">Suposiciones, lecturas entre líneas, cosas que nunca han sucedido.</p>
                    <div id="pn-list-imaginarias" style="display: flex; flex-direction: column; gap: 0.4rem;">
                        ${renderNegativosList('imaginarias', imag)}
                    </div>
                </div>
            </div>

            <!-- Conclusión -->
            <div class="card" style="background: #ffffff; border: 1.5px solid #ea580c; border-radius: 14px; padding: 1rem;">
                <label style="font-weight: 800; font-size: 0.85rem; color: #c2410c; display: block; margin-bottom: 0.35rem;">
                    Conclusión Discriminativa:
                </label>
                <textarea id="pn-conclusion" rows="2" oninput="triggerRecursoAutoSave()" placeholder="¿Cuánto de mi malestar viene de hechos y cuánto de hipótesis creadas por mi mente?..." style="width: 100%; padding: 0.55rem; border-radius: 8px; border: 1.5px solid #cbd5e1; font-size: 0.88rem; font-family: inherit;">${escapeHtml(c.conclusion_discriminativa || '')}</textarea>
            </div>
        </div>`;
    }

    function renderNegativosList(key, items) {
        let html = '';
        items.forEach((txt, idx) => {
            html += `
            <div class="pn-item" data-key="${key}" style="display: flex; gap: 0.35rem; align-items: center;">
                <input type="text" class="pn-input" value="${escapeHtml(txt)}" oninput="triggerRecursoAutoSave()" placeholder="• Describir..." style="flex: 1; padding: 0.35rem 0.5rem; border-radius: 6px; border: 1px solid #cbd5e1; font-size: 0.82rem;">
                <button type="button" onclick="this.closest('.pn-item').remove(); triggerRecursoAutoSave();" style="background: none; border: none; color: #94a3b8; font-weight: 700; cursor: pointer;">✕</button>
            </div>`;
        });
        return html;
    }

    function addNegativoItem(key) {
        const container = document.getElementById(key === 'reales' ? 'pn-list-reales' : 'pn-list-imaginarias');
        if (!container) return;
        const div = document.createElement('div');
        div.className = 'pn-item';
        div.dataset.key = key;
        div.style.cssText = 'display: flex; gap: 0.35rem; align-items: center;';
        div.innerHTML = `
            <input type="text" class="pn-input" value="" oninput="triggerRecursoAutoSave()" placeholder="• Describir..." style="flex: 1; padding: 0.35rem 0.5rem; border-radius: 6px; border: 1px solid #cbd5e1; font-size: 0.82rem;">
            <button type="button" onclick="this.closest('.pn-item').remove(); triggerRecursoAutoSave();" style="background: none; border: none; color: #94a3b8; font-weight: 700; cursor: pointer;">✕</button>
        `;
        container.appendChild(div);
        div.querySelector('input').focus();
        triggerRecursoAutoSave();
    }
    window.addNegativoItem = addNegativoItem;

    // --- E. SEGMENTACIÓN DE OBJETIVOS (CORTO, MEDIANO, LARGO PLAZO) ---
    function getSegmentacionObjetivosHTML(c) {
        const cpItems = (c.corto_plazo && c.corto_plazo.items) ? c.corto_plazo.items : [''];
        const mpItems = (c.mediano_plazo && c.mediano_plazo.items) ? c.mediano_plazo.items : [''];
        const lpItems = (c.largo_plazo && c.largo_plazo.items) ? c.largo_plazo.items : [''];

        return `
        <div style="display: flex; flex-direction: column; gap: 1.25rem;">
            <div style="background: #f0fdf4; border: 1.5px solid #bbf7d0; border-radius: 12px; padding: 0.85rem 1rem; color: #166534; font-size: 0.85rem; line-height: 1.45;">
                🎯 <strong>Gradiente de Aproximación:</strong> No intentes resolver todo al mismo tiempo. 
                Fija una meta mayor y segméntala en micro-pasos alcanzables según los recursos que ya tienes hoy.
            </div>

            <!-- Meta Global -->
            <div class="card" style="background: #ffffff; border: 1.5px solid #e2e8f0; border-radius: 14px; padding: 1rem;">
                <label style="font-weight: 800; font-size: 0.85rem; color: #16a34a; display: block; margin-bottom: 0.35rem;">
                    Meta Global o Proyecto Vital del Consultante:
                </label>
                <input type="text" id="so-meta-global" value="${escapeHtml(c.meta_global || '')}" oninput="triggerRecursoAutoSave()" placeholder="Ej: 'Conseguir empleo estable en mi área profesional'..." style="width: 100%; padding: 0.55rem; border-radius: 8px; border: 1.5px solid #cbd5e1; font-size: 0.92rem; font-weight: 600;">
            </div>

            <!-- 3 Columnas por Etapas -->
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 1rem;">
                
                <!-- Corto Plazo -->
                <div style="background: #ffffff; border: 1.5px solid #22c55e; border-radius: 12px; padding: 1rem; display: flex; flex-direction: column;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.3rem;">
                        <strong style="color: #15803d; font-size: 0.9rem;">1. CORTO PLAZO</strong>
                        <button type="button" class="btn btn-sm" onclick="addObjetivoItem('corto')" style="font-size: 0.72rem; padding: 0.15rem 0.45rem; background: #dcfce7; color: #166534; border: none; border-radius: 4px;">+ Añadir</button>
                    </div>
                    <p style="margin: 0 0 0.55rem 0; font-size: 0.75rem; color: #64748b;">¿Qué puedo ejecutar hoy con los recursos que YA tengo? (Ej: actualizar CV, enviar 3 correos).</p>
                    <div id="so-list-corto" style="display: flex; flex-direction: column; gap: 0.4rem; flex: 1;">
                        ${renderObjetivoItemList('corto', cpItems)}
                    </div>
                </div>

                <!-- Mediano Plazo -->
                <div style="background: #ffffff; border: 1.5px solid #3b82f6; border-radius: 12px; padding: 1rem; display: flex; flex-direction: column;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.3rem;">
                        <strong style="color: #1d4ed8; font-size: 0.9rem;">2. MEDIANO PLAZO</strong>
                        <button type="button" class="btn btn-sm" onclick="addObjetivoItem('mediano')" style="font-size: 0.72rem; padding: 0.15rem 0.45rem; background: #dbeafe; color: #1e40af; border: none; border-radius: 4px;">+ Añadir</button>
                    </div>
                    <p style="margin: 0 0 0.55rem 0; font-size: 0.75rem; color: #64748b;">¿Qué recursos necesito conseguir y cómo? (Ej: hacer un curso, trabajar la autoconfianza).</p>
                    <div id="so-list-mediano" style="display: flex; flex-direction: column; gap: 0.4rem; flex: 1;">
                        ${renderObjetivoItemList('mediano', mpItems)}
                    </div>
                </div>

                <!-- Largo Plazo -->
                <div style="background: #ffffff; border: 1.5px solid #9333ea; border-radius: 12px; padding: 1rem; display: flex; flex-direction: column;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.3rem;">
                        <strong style="color: #7e22ce; font-size: 0.9rem;">3. LARGO PLAZO</strong>
                        <button type="button" class="btn btn-sm" onclick="addObjetivoItem('largo')" style="font-size: 0.72rem; padding: 0.15rem 0.45rem; background: #f3e8ff; color: #6b21a8; border: none; border-radius: 4px;">+ Añadir</button>
                    </div>
                    <p style="margin: 0 0 0.55rem 0; font-size: 0.75rem; color: #64748b;">¿Qué haré con los recursos consolidados? (Ej: estudiar un posgrado, abrir mi consultora).</p>
                    <div id="so-list-largo" style="display: flex; flex-direction: column; gap: 0.4rem; flex: 1;">
                        ${renderObjetivoItemList('largo', lpItems)}
                    </div>
                </div>
            </div>
        </div>`;
    }

    function renderObjetivoItemList(stage, items) {
        let html = '';
        items.forEach(txt => {
            html += `
            <div class="so-item" data-stage="${stage}" style="display: flex; gap: 0.35rem; align-items: center;">
                <input type="text" class="so-input" value="${escapeHtml(txt)}" oninput="triggerRecursoAutoSave()" placeholder="✓ Acción específica..." style="flex: 1; padding: 0.35rem 0.5rem; border-radius: 6px; border: 1px solid #cbd5e1; font-size: 0.82rem;">
                <button type="button" onclick="this.closest('.so-item').remove(); triggerRecursoAutoSave();" style="background: none; border: none; color: #94a3b8; font-weight: 700; cursor: pointer;">✕</button>
            </div>`;
        });
        return html;
    }

    function addObjetivoItem(stage) {
        const containerMap = {
            'corto': 'so-list-corto',
            'mediano': 'so-list-mediano',
            'largo': 'so-list-largo'
        };
        const container = document.getElementById(containerMap[stage]);
        if (!container) return;

        const div = document.createElement('div');
        div.className = 'so-item';
        div.dataset.stage = stage;
        div.style.cssText = 'display: flex; gap: 0.35rem; align-items: center;';
        div.innerHTML = `
            <input type="text" class="so-input" value="" oninput="triggerRecursoAutoSave()" placeholder="✓ Acción específica..." style="flex: 1; padding: 0.35rem 0.5rem; border-radius: 6px; border: 1px solid #cbd5e1; font-size: 0.82rem;">
            <button type="button" onclick="this.closest('.so-item').remove(); triggerRecursoAutoSave();" style="background: none; border: none; color: #94a3b8; font-weight: 700; cursor: pointer;">✕</button>
        `;
        container.appendChild(div);
        div.querySelector('input').focus();
        triggerRecursoAutoSave();
    }
    window.addObjetivoItem = addObjetivoItem;

    // --- F. SOBRE-PENSAMIENTO (EMBUDO DE 4 FASES) ---
    function getSobrepensamientoHTML(c) {
        return `
        <div style="display: flex; flex-direction: column; gap: 1.25rem;">
            <div style="background: #faf5ff; border: 1.5px solid #d8b4fe; border-radius: 12px; padding: 0.85rem 1rem; color: #581c87; font-size: 0.85rem; line-height: 1.45;">
                🚀 <strong>Embudo de Activación:</strong> Corta el sobrepensamiento transformando la rumiación pasiva en una acción ejecutable esta semana.
            </div>

            <!-- FASE 1 -->
            <div class="card" style="background: #ffffff; border: 1.5px solid #e2e8f0; border-radius: 12px; padding: 1rem;">
                <label style="font-weight: 800; font-size: 0.88rem; color: #6b21a8; display: block; margin-bottom: 0.3rem;">
                    1. Situación (Volcado mental):
                </label>
                <p style="margin: 0 0 0.45rem 0; font-size: 0.76rem; color: #64748b;">Escribe libremente todas las situaciones que dan vueltas en tu cabeza.</p>
                <textarea id="sp-situaciones" rows="3" oninput="triggerRecursoAutoSave()" placeholder="Descarga aquí las ideas..." style="width: 100%; padding: 0.55rem; border-radius: 8px; border: 1.5px solid #cbd5e1; font-size: 0.88rem; font-family: inherit;">${escapeHtml(c.situaciones_cabeza || '')}</textarea>
            </div>

            <!-- FASE 2 -->
            <div class="card" style="background: #ffffff; border: 1.5px solid #e2e8f0; border-radius: 12px; padding: 1rem;">
                <label style="font-weight: 800; font-size: 0.88rem; color: #b91c1c; display: block; margin-bottom: 0.3rem;">
                    2. Limitaciones (Lo que escapa de tu control hoy):
                </label>
                <p style="margin: 0 0 0.45rem 0; font-size: 0.76rem; color: #64748b;">¿Qué recursos te faltan o qué aspectos de la situación no dependen de ti?</p>
                <textarea id="sp-limitaciones" rows="2" oninput="triggerRecursoAutoSave()" placeholder="Lo que no puedo cambiar ahora..." style="width: 100%; padding: 0.55rem; border-radius: 8px; border: 1.5px solid #cbd5e1; font-size: 0.88rem; font-family: inherit;">${escapeHtml(c.limitaciones || '')}</textarea>
            </div>

            <!-- FASE 3 -->
            <div class="card" style="background: #ffffff; border: 1.5px solid #e2e8f0; border-radius: 12px; padding: 1rem;">
                <label style="font-weight: 800; font-size: 0.88rem; color: #15803d; display: block; margin-bottom: 0.3rem;">
                    3. Ventajas y Recursos Presentes:
                </label>
                <p style="margin: 0 0 0.45rem 0; font-size: 0.76rem; color: #64748b;">¿Qué recursos, apoyos o fortalezas sí tienes a mano en este momento?</p>
                <textarea id="sp-ventajas" rows="2" oninput="triggerRecursoAutoSave()" placeholder="Lo que sí tengo hoy..." style="width: 100%; padding: 0.55rem; border-radius: 8px; border: 1.5px solid #cbd5e1; font-size: 0.88rem; font-family: inherit;">${escapeHtml(c.ventajas_recursos || '')}</textarea>
            </div>

            <!-- FASE 4 -->
            <div class="card" style="background: #ffffff; border: 2px solid #9333ea; border-radius: 12px; padding: 1rem;">
                <label style="font-weight: 800; font-size: 0.88rem; color: #7e22ce; display: block; margin-bottom: 0.3rem;">
                    4. Micro-acción Concreta para esta Semana:
                </label>
                <p style="margin: 0 0 0.45rem 0; font-size: 0.76rem; color: #64748b;">Define 1 acción específica con lo que tienes hoy, que no resolverá todo, pero cortará la parálisis.</p>
                <input type="text" id="sp-accion-semana" value="${escapeHtml(c.accion_concreta_semana || '')}" oninput="triggerRecursoAutoSave()" placeholder="¿Qué vas a hacer hoy o esta semana?..." style="width: 100%; padding: 0.6rem; border-radius: 8px; border: 1.5px solid #cbd5e1; font-size: 0.92rem; font-weight: 700;">
            </div>
        </div>`;
    }

    // =========================================================================
    // 5. AUTOGUARDADO INTELIGENTE Y SINCRONIZACIÓN EN VIVO
    // =========================================================================

    function triggerRecursoAutoSave() {
        updateSaveStatusBadge('saving');
        if (window.recursoAutoSaveTimer) {
            clearTimeout(window.recursoAutoSaveTimer);
        }
        window.recursoAutoSaveTimer = setTimeout(() => {
            saveRecursoPizarra(true);
        }, 1200);
    }
    window.triggerRecursoAutoSave = triggerRecursoAutoSave;

    function forceSaveRecursoPizarra() {
        if (window.recursoAutoSaveTimer) clearTimeout(window.recursoAutoSaveTimer);
        saveRecursoPizarra(false);
    }
    window.forceSaveRecursoPizarra = forceSaveRecursoPizarra;

    async function saveRecursoPizarra(silent) {
        const board = window.activeRecursoPizarra;
        if (!board || !board.id) return;

        const payloadContent = gatherCurrentPizarraPayload(board.recurso_tipo);

        try {
            const res = await fetch(`/api/recursos/pizarra/${board.id}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    contenido: payloadContent
                })
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.error || 'Error al guardar');

            board.contenido = payloadContent;
            window.lastSyncedTimestamp = data.fecha_ultima_edicion;

            updateSaveStatusBadge('synced');
            if (!silent) {
                alert("✅ Pizarra guardada correctamente.");
            }
        } catch (e) {
            console.error(e);
            updateSaveStatusBadge('error');
        }
    }

    function gatherCurrentPizarraPayload(type) {
        switch (type) {
            case 'pros_contras': {
                const getRowData = (key) => {
                    const list = [];
                    document.querySelectorAll(`.pc-row-item[data-key="${key}"]`).forEach(row => {
                        const txt = row.querySelector('.pc-row-text')?.value || '';
                        const pts = parseInt(row.querySelector('.pc-row-pts')?.value) || 0;
                        if (txt || pts) list.push({ texto: txt, pts: pts });
                    });
                    return list;
                };
                return {
                    alternativa_a: document.getElementById('pc-alt-a')?.value || '',
                    alternativa_b: document.getElementById('pc-alt-b')?.value || '',
                    pros_a: getRowData('pros_a'),
                    contras_a: getRowData('contras_a'),
                    pros_b: getRowData('pros_b'),
                    contras_b: getRowData('contras_b'),
                    reflexion_emocional: document.getElementById('pc-reflexion-emocional')?.value || '',
                    decision_final: document.getElementById('pc-decision-final')?.value || ''
                };
            }
            case 'cuestionando_creencias': {
                const respuestas = {};
                const qBlocks = document.querySelectorAll('.cc-q-block');
                const selectedQIds = [];
                qBlocks.forEach(b => {
                    const qid = b.dataset.qid;
                    const ans = b.querySelector('.cc-q-answer')?.value || '';
                    selectedQIds.push(qid);
                    respuestas[qid] = ans;
                });
                return {
                    tipo_apertura: document.getElementById('cc-tipo-apertura')?.value || '',
                    pensamiento_central: document.getElementById('cc-pensamiento-central')?.value || '',
                    preguntas_seleccionadas: selectedQIds,
                    respuestas: respuestas,
                    conclusion_realista: document.getElementById('cc-conclusion-realista')?.value || ''
                };
            }
            case 'diversificando_pensamiento': {
                return {
                    pensamiento_central: document.getElementById('dp-pensamiento-central')?.value || '',
                    racional: document.getElementById('dp-lente-racional')?.value || '',
                    emocional: document.getElementById('dp-lente-emocional')?.value || '',
                    critico: document.getElementById('dp-lente-critico')?.value || '',
                    optimista: document.getElementById('dp-lente-optimista')?.value || '',
                    creativo: document.getElementById('dp-lente-creativo')?.value || '',
                    organizado: document.getElementById('dp-lente-organizado')?.value || '',
                    sintesis: document.getElementById('dp-sintesis')?.value || ''
                };
            }
            case 'pensamientos_negativos': {
                const getItems = (key) => {
                    const arr = [];
                    document.querySelectorAll(`.pn-item[data-key="${key}"] .pn-input`).forEach(inp => {
                        if (inp.value) arr.push(inp.value);
                    });
                    return arr;
                };
                return {
                    malestar_actual: document.getElementById('pn-malestar')?.value || '',
                    situaciones_reales: getItems('reales'),
                    situaciones_imaginarias: getItems('imaginarias'),
                    conclusion_discriminativa: document.getElementById('pn-conclusion')?.value || ''
                };
            }
            case 'segmentacion_objetivos': {
                const getItems = (stage) => {
                    const arr = [];
                    document.querySelectorAll(`.so-item[data-stage="${stage}"] .so-input`).forEach(inp => {
                        if (inp.value) arr.push(inp.value);
                    });
                    return arr;
                };
                return {
                    meta_global: document.getElementById('so-meta-global')?.value || '',
                    corto_plazo: { items: getItems('corto') },
                    mediano_plazo: { items: getItems('mediano') },
                    largo_plazo: { items: getItems('largo') }
                };
            }
            case 'sobrepensamiento': {
                return {
                    situaciones_cabeza: document.getElementById('sp-situaciones')?.value || '',
                    limitaciones: document.getElementById('sp-limitaciones')?.value || '',
                    ventajas_recursos: document.getElementById('sp-ventajas')?.value || '',
                    accion_concreta_semana: document.getElementById('sp-accion-semana')?.value || ''
                };
            }
            default:
                return {};
        }
    }

    function updateSaveStatusBadge(status) {
        const badge = document.getElementById('pizarra-save-status-badge');
        if (!badge) return;

        if (status === 'saving') {
            badge.textContent = '⏳ Guardando...';
            badge.style.color = '#d97706';
            badge.style.background = '#fef3c7';
        } else if (status === 'synced') {
            badge.textContent = '✓ Guardado y Sincronizado';
            badge.style.color = '#16a34a';
            badge.style.background = '#dcfce7';
        } else if (status === 'error') {
            badge.textContent = '⚠️ Error al guardar';
            badge.style.color = '#dc2626';
            badge.style.background = '#fee2e2';
        }
    }

    function startPizarraLiveSync(recursoId) {
        stopPizarraLiveSync();
        window.recursoLiveSyncInterval = setInterval(async () => {
            const modal = document.getElementById('modal-recurso-pizarra');
            if (!modal || modal.classList.contains('hide')) {
                stopPizarraLiveSync();
                return;
            }

            try {
                const res = await fetch(`/api/recursos/pizarra/${recursoId}`);
                if (!res.ok) return;
                const freshData = await res.json();

                // Si la fecha de edición cambió en el servidor y fue editada por la otra persona
                if (window.lastSyncedTimestamp && freshData.fecha_ultima_edicion !== window.lastSyncedTimestamp) {
                    const isOtherUser = (freshData.ultima_edicion_por === 'paciente' && !sessionStorage.getItem('patient_id')) ||
                                        (freshData.ultima_edicion_por === 'psicologo' && sessionStorage.getItem('patient_id'));

                    if (isOtherUser) {
                        window.activeRecursoPizarra = freshData;
                        window.lastSyncedTimestamp = freshData.fecha_ultima_edicion;

                        // Solo sincronizar campos si el usuario no está activamente tecleando en ellos
                        const activeEl = document.activeElement;
                        const isTyping = activeEl && (activeEl.tagName === 'INPUT' || activeEl.tagName === 'TEXTAREA');

                        if (!isTyping) {
                            renderSpecificInteractiveTool(freshData);
                            flashSyncNotification(freshData.ultima_edicion_por);
                        }
                    }
                }
            } catch (e) {}
        }, 5000);
    }

    function stopPizarraLiveSync() {
        if (window.recursoLiveSyncInterval) {
            clearInterval(window.recursoLiveSyncInterval);
            window.recursoLiveSyncInterval = null;
        }
    }

    function flashSyncNotification(editor) {
        const lastEdText = document.getElementById('pizarra-last-edited-text');
        if (lastEdText) {
            const who = editor === 'paciente' ? 'el consultante' : 'el terapeuta';
            lastEdText.innerHTML = `<span style="color: #16a34a; font-weight: 700;">🔄 ¡Actualizado en vivo por ${who}!</span>`;
            setTimeout(() => {
                if (window.activeRecursoPizarra) {
                    const edBy = window.activeRecursoPizarra.ultima_edicion_por === 'paciente' ? 'Consultante' : 'Terapeuta';
                    const fecha = (window.activeRecursoPizarra.fecha_ultima_edicion || '').substring(0, 16).replace('T', ' ');
                    lastEdText.textContent = `Última edición: ${fecha} (${edBy})`;
                }
            }, 4000);
        }
    }

    // =========================================================================
    // 6. PORTAL DEL CONSULTANTE (PACIENTE)
    // =========================================================================

    async function loadPatientPortalRecursos() {
        const container = document.getElementById('patient-recursos-container');
        if (!container) return;

        container.innerHTML = '<p class="text-muted text-center py-4">Cargando tus recursos asignados...</p>';

        try {
            const res = await fetch('/api/patient/recursos');
            if (!res.ok) throw new Error('Error al cargar recursos');
            const recursos = await res.json();
            renderPatientPizarrasTable(recursos, container, true);
        } catch (e) {
            console.error(e);
            container.innerHTML = '<p class="text-danger text-center py-4">Error al conectar con tus recursos terapéuticos.</p>';
        }
    }
    window.loadPatientPortalRecursos = loadPatientPortalRecursos;

    // =========================================================================
    // 7. EXPORTACIÓN Y ACCIONES COMPLEMENTARIAS
    // =========================================================================

    function exportRecursoWord() {
        if (!window.activeRecursoPizarra || !window.activeRecursoPizarra.id) return;
        exportRecursoWordById(window.activeRecursoPizarra.id);
    }
    window.exportRecursoWord = exportRecursoWord;

    function exportRecursoWordById(recursoId) {
        window.open(`/api/recursos/pizarra/${recursoId}/export-word`, '_blank');
    }
    window.exportRecursoWordById = exportRecursoWordById;

    function shareRecursoWhatsApp() {
        if (!window.activeRecursoPizarra) return;
        shareRecursoWhatsAppById(window.activeRecursoPizarra.id);
    }
    window.shareRecursoWhatsApp = shareRecursoWhatsApp;

    function shareRecursoWhatsAppById(recursoId) {
        const r = window.activeRecursoPizarra;
        const pacNombre = (r && r.pac_nombres) ? r.pac_nombres : 'Hola';
        const pacTelefono = (r && r.pac_telefono) ? r.pac_telefono.replace(/[^0-9]/g, '') : '';
        const titulo = (r && r.titulo) ? r.titulo : 'Recurso Terapéutico';

        const mensaje = `Hola *${pacNombre}* 👋\n\nTe comparto tu pizarra de trabajo interactivo: *${titulo}*.\n\nPuedes entrar a revisarla, editarla y reflexionar en ella directamente desde tu Portal del Consultante en la sección *"Recursos"*.\n\nNos vemos en nuestra próxima sesión.`;
        const encoded = encodeURIComponent(mensaje);
        const url = pacTelefono ? `https://wa.me/${pacTelefono}?text=${encoded}` : `https://api.whatsapp.com/send?text=${encoded}`;
        window.open(url, '_blank');
    }
    window.shareRecursoWhatsAppById = shareRecursoWhatsAppById;

    async function openRecursoHistorialModal() {
        const board = window.activeRecursoPizarra;
        if (!board || !board.id) return;

        const modal = document.getElementById('modal-recurso-historial');
        const list = document.getElementById('recurso-historial-list');
        if (!modal || !list) return;

        list.innerHTML = '<p class="text-muted text-center py-4">Cargando versiones...</p>';
        if (typeof openModal === 'function') {
            openModal('modal-recurso-historial');
        } else {
            modal.classList.remove('hide');
            modal.style.setProperty('display', 'flex', 'important');
        }

        try {
            const res = await fetch(`/api/recursos/pizarra/${board.id}/historial`);
            if (!res.ok) throw new Error('Error al cargar historial');
            const data = await res.json();

            if (!data || data.length === 0) {
                list.innerHTML = '<p class="text-muted text-center py-3">No hay versiones registradas aún.</p>';
                return;
            }

            let html = '';
            data.forEach((h, idx) => {
                const fecha = (h.fecha_registro || '').substring(0, 19).replace('T', ' ');
                const by = h.editado_por === 'paciente' ? '👤 Consultante' : '🩺 Terapeuta';
                html += `
                <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 0.65rem 0.85rem; display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <strong style="color: #334155; font-size: 0.85rem;">Versión #${data.length - idx}</strong>
                        <div style="font-size: 0.75rem; color: #64748b; margin-top: 2px;">
                            ${fecha} • Editado por: ${by}
                        </div>
                    </div>
                    <span style="font-size: 0.72rem; color: #16a34a; font-weight: 700; background: #dcfce7; padding: 0.15rem 0.45rem; border-radius: 8px;">
                        ✓ Guardado
                    </span>
                </div>`;
            });
            list.innerHTML = html;
        } catch (e) {
            list.innerHTML = `<p class="text-danger text-center py-3">${e.message}</p>`;
        }
    }
    window.openRecursoHistorialModal = openRecursoHistorialModal;

    function closeRecursoPizarra() {
        stopPizarraLiveSync();
        if (typeof closeModal === 'function') {
            closeModal('modal-recurso-pizarra');
        } else {
            const modal = document.getElementById('modal-recurso-pizarra');
            if (modal) {
                modal.classList.add('hide');
                modal.style.removeProperty('display');
            }
        }
    }
    window.closeRecursoPizarra = closeRecursoPizarra;

    async function deleteRecursoPizarra(recursoId) {
        if (!confirm("¿Estás seguro de que deseas eliminar esta pizarra de recurso?")) return;
        try {
            const res = await fetch(`/api/recursos/pizarra/${recursoId}`, { method: 'DELETE' });
            if (!res.ok) throw new Error('Error al eliminar');
            alert("Pizarra eliminada correctamente.");
            if (window.selectedRecursoPatientId) {
                onRecursoPatientSelected(window.selectedRecursoPatientId);
            }
        } catch (e) {
            alert(e.message);
        }
    }
    window.deleteRecursoPizarra = deleteRecursoPizarra;

    // Helper para escapar strings HTML
    function escapeHtml(text) {
        if (text === null || text === undefined) return '';
        return String(text)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

})();
