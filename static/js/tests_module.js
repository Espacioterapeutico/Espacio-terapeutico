// ==============================================================================
// MÓDULO INDEPENDIENTE: EVALUACIONES Y TESTS PSICOLÓGICOS
// ==============================================================================

let allTestPatientsCache = [];
let selectedTestCodeForApplication = null;
let currentCatalogCategory = 'TODAS';
let currentCatalogPage = 1;
const CATALOG_PER_PAGE = 10; // Vista cuadrícula 5x2 (10 por página)

// BASE DE DATOS DE EVALUACIONES PSICOMÉTRICAS CON METADATOS COMPLETOS
const testsCatalogDatabase = [
    { 
        code: 'AQ', 
        name: 'AQ — Cociente de Espectro Autista', 
        siglas: 'AQ-50', 
        cat: 'Neurodivergencia y Autismo', 
        desc: 'Evaluación estandarizada de 50 ítems desarrollada por Baron-Cohen et al. Mide rasgos del espectro autista en adultos.', 
        autor: 'Simon Baron-Cohen et al.', 
        poblacion: 'Adolescentes y Adultos (16+ años)', 
        validez: 'α = 0.82 | Punto de corte: ≥ 32', 
        itemsCount: 50 
    },
    { 
        code: 'RAADS-R', 
        name: 'RAADS-R — Escala Revisada para Diagnóstico de Autismo', 
        siglas: 'RAADS-R', 
        cat: 'Neurodivergencia y Autismo', 
        desc: 'Inventario clínico completo de 80 ítems para el diagnóstico del Espectro Autista / Asperger en población adulta.', 
        autor: 'Riva Ariella Ritvo et al.', 
        poblacion: 'Adultos (18+ años)', 
        validez: 'α = 0.92 | Umbral diagnóstico: ≥ 65', 
        itemsCount: 80 
    },
    { 
        code: 'CAT-Q', 
        name: 'CAT-Q — Cuestionario de Camuflaje Autista', 
        siglas: 'CAT-Q', 
        cat: 'Neurodivergencia y Autismo', 
        desc: 'Evaluación de 25 ítems desarrollada por Laura Hull et al. Mide estrategias de camuflaje y enmascaramiento social.', 
        autor: 'Laura Hull et al.', 
        poblacion: 'Adolescentes y Adultos (16+ años)', 
        validez: 'α = 0.90 | Medición de Camuflaje', 
        itemsCount: 25 
    },
    { 
        code: 'ASRS-ADHD', 
        name: 'ASRS v1.1 — Sintomatología TDAH en Adultos', 
        siglas: 'ASRS v1.1', 
        cat: 'Neurodivergencia y Autismo', 
        desc: 'Escala de tamizaje oficial de la OMS de 18 ítems para la detección de Trastorno por Déficit de Atención e Hiperactividad en adultos.', 
        autor: 'OMS / Adler et al.', 
        poblacion: 'Adultos (18+ años)', 
        validez: 'α = 0.87 | Criterios DSM / OMS', 
        itemsCount: 18 
    },
    { 
        code: 'BDI-II', 
        name: 'BDI-II — Inventario de Depresión de Beck', 
        siglas: 'BDI-II', 
        cat: 'Depresión y Ansiedad', 
        desc: 'Cuestionario de 21 ítems de autorreporte ampliamente utilizado para evaluar la severidad de los síntomas depresivos.', 
        autor: 'Aaron T. Beck et al.', 
        poblacion: 'Adolescentes y Adultos (13+ años)', 
        validez: 'α = 0.92 | Validez Clínica Estandarizada', 
        itemsCount: 21 
    },
    { 
        code: 'BAI', 
        name: 'BAI — Inventario de Ansiedad de Beck', 
        siglas: 'BAI', 
        cat: 'Depresión y Ansiedad', 
        desc: 'Evaluación de 21 ítems diseñada para discriminar y medir la intensidad de la sintomatología ansiosa somática y cognitiva.', 
        autor: 'Aaron T. Beck et al.', 
        poblacion: 'Adolescentes y Adultos (13+ años)', 
        validez: 'α = 0.92 | Alta Especificidad Ansiosa', 
        itemsCount: 21 
    },
    { 
        code: 'RAVEN', 
        name: 'RAVEN — Test de Matrices Progresivas de Raven', 
        siglas: 'RAVEN', 
        cat: 'Capacidad Intelectual', 
        desc: 'Prueba no verbal de 60 matrices estandarizadas para medir el factor g de inteligencia y la capacidad de razonamiento abstracto.', 
        autor: 'John C. Raven', 
        poblacion: 'Adolescentes y Adultos (12+ años)', 
        validez: 'α = 0.90 | Razonamiento No Verbal', 
        itemsCount: 60 
    },
    { 
        code: 'MCMI-II', 
        name: 'MCMI-II — Inventario Multiaxial Clínico de Millon', 
        siglas: 'MCMI-II', 
        cat: 'Personalidad', 
        desc: 'Instrumento multiaxial psicométrico de 175 ítems para la evaluación de patrones de personalidad clínica y síndromes severos.', 
        autor: 'Theodore Millon', 
        poblacion: 'Adultos (18+ años)', 
        validez: 'Estandarizado TB | 24 Escalones Clínicos', 
        itemsCount: 175 
    },
    { 
        code: 'HOLLAND', 
        name: 'HOLLAND — Test de Intereses Vocacionales (RIASEC)', 
        siglas: 'HOLLAND', 
        cat: 'Orientación Vocacional', 
        desc: 'Inventario vocacional basado en el modelo tipológico RIASEC para la identificación de perfil vocacional y profesional.', 
        autor: 'John L. Holland', 
        poblacion: 'Adolescentes y Adultos (14+ años)', 
        validez: 'α = 0.86 | Perfil Tipológico RIASEC', 
        itemsCount: 60 
    },
    { 
        code: 'TCS', 
        name: 'TCS — Escala de Congruencia Transgénero', 
        siglas: 'TCS', 
        cat: 'Identidad de Género', 
        desc: 'Escala de 12 ítems desarrollada por Kozee et al. para evaluar el nivel de confort y aceptación de la identidad de género.', 
        autor: 'Kozee, Reisner et al.', 
        poblacion: 'Jóvenes y Adultos (16+ años)', 
        validez: 'α = 0.89 | Afirmación e Identidad', 
        itemsCount: 12 
    },
    { 
        code: 'UGDS-GS', 
        name: 'UGDS-GS — Escala de Disforia de Utrecht', 
        siglas: 'UGDS-GS', 
        cat: 'Identidad de Género', 
        desc: 'Evaluación estandarizada de 18 ítems para la medición objetiva del grado de disforia de género clínica.', 
        autor: 'McGuire et al. / Utrecht', 
        poblacion: 'Adolescentes y Adultos (12+ años)', 
        validez: 'α = 0.91 | Medición de Disforia', 
        itemsCount: 18 
    }
];

// 1. POBLACIÓN Y CARGA DE PACIENTES DESDE LA BASE DE DATOS
async function populateMainViewPatientSelect() {
    const select = document.getElementById('select-test-main-patient');
    if (!select) return;

    // Buscar en memoria global o caché previa
    const existingPatients = (window.patients && Array.isArray(window.patients) && window.patients.length > 0)
        ? window.patients
        : ((allTestPatientsCache && allTestPatientsCache.length > 0) ? allTestPatientsCache : null);

    if (existingPatients && existingPatients.length > 0) {
        allTestPatientsCache = existingPatients;
        renderTestPatientsOptions(allTestPatientsCache);
    }

    try {
        const resp = await fetch('/api/patients');
        if (!resp.ok) {
            if (!allTestPatientsCache || allTestPatientsCache.length === 0) {
                select.innerHTML = '<option value="">⚠️ Error al conectar con la base de datos de pacientes</option>';
            }
            return;
        }
        const data = await resp.json();
        const patientsArr = Array.isArray(data) ? data : (data.pacientes || []);
        allTestPatientsCache = patientsArr;
        window.patients = patientsArr;
        renderTestPatientsOptions(allTestPatientsCache);
    } catch (e) {
        console.error("Error al poblar selector de pacientes para tests:", e);
        if (!allTestPatientsCache || allTestPatientsCache.length === 0) {
            select.innerHTML = '<option value="">⚠️ Error al conectar con la base de datos de pacientes</option>';
        }
    }
}

function renderTestPatientsOptions(patientsList) {
    const select = document.getElementById('select-test-main-patient');
    if (!select) return;

    const currentVal = select.value;
    const pool = patientsList || [];
    let html = '';
    if (pool.length === 0) {
        html = '<option value="">⚠️ No hay consultantes registrados en tu cuenta (0 disponibles)</option>';
    } else {
        html = `<option value="">-- Seleccionar Consultante (${pool.length} disponibles) --</option>`;
        pool.forEach(p => {
            const nameStr = `${p.nombres || ''} ${p.apellidos || ''}`.trim() || 'Sin Nombre';
            const ciStr = p.cedula ? ` (CI: ${p.cedula})` : '';
            html += `<option value="${p.id}">${nameStr}${ciStr}</option>`;
        });
    }
    select.innerHTML = html;
    if (currentVal && select.querySelector("option[value='" + currentVal + "']")) {
        select.value = currentVal;
    }
}

async function onTestPatientInputFocus() {
    if (!allTestPatientsCache || allTestPatientsCache.length === 0) {
        await populateMainViewPatientSelect();
    }
}

async function filterTestPatientSelect() {
    const searchInput = document.getElementById('input-search-test-patient');
    const select = document.getElementById('select-test-main-patient');
    const clearBtn = document.getElementById('btn-clear-test-patient');
    if (!select) return;

    if (!allTestPatientsCache || allTestPatientsCache.length === 0) {
        await populateMainViewPatientSelect();
    }

    const pool = (allTestPatientsCache && allTestPatientsCache.length > 0) 
        ? allTestPatientsCache 
        : (window.patients || []);

    const query = searchInput ? searchInput.value.toLowerCase().trim() : '';

    if (!query) {
        if (clearBtn) clearBtn.style.display = 'none';
        renderTestPatientsOptions(pool);
        if (!select.value) {
            updateSelectedPatientLabel();
        }
        return;
    }

    if (clearBtn) clearBtn.style.display = 'inline-flex';

    const filtered = pool.filter(p => {
        const fullStr = `${p.nombres || ''} ${p.apellidos || ''} ${p.cedula || ''}`.toLowerCase();
        return fullStr.includes(query);
    });

    if (filtered.length === 0) {
        let html = `<option value="">⚠️ No hay coincidencias para "${query}"</option>`;
        html += `<option value="">-- Ver todos los consultantes (${pool.length}) --</option>`;
        pool.forEach(p => {
            const nameStr = `${p.nombres || ''} ${p.apellidos || ''}`.trim() || 'Sin Nombre';
            const ciStr = p.cedula ? ` (CI: ${p.cedula})` : '';
            html += `<option value="${p.id}">${nameStr}${ciStr}</option>`;
        });
        select.innerHTML = html;
        select.value = '';
    } else {
        let html = `<option value="">-- ${filtered.length} coincidencia(s) encontrada(s) --</option>`;
        filtered.forEach(p => {
            const nameStr = `${p.nombres || ''} ${p.apellidos || ''}`.trim() || 'Sin Nombre';
            const ciStr = p.cedula ? ` (CI: ${p.cedula})` : '';
            html += `<option value="${p.id}">${nameStr}${ciStr}</option>`;
        });
        select.innerHTML = html;
        select.value = String(filtered[0].id);
    }

    updateSelectedPatientLabel();
}

function clearTestPatientSelection() {
    const select = document.getElementById('select-test-main-patient');
    const searchInput = document.getElementById('input-search-test-patient');
    const clearBtn = document.getElementById('btn-clear-test-patient');

    if (select) {
        renderTestPatientsOptions(allTestPatientsCache || window.patients || []);
        select.value = '';
    }
    if (searchInput) searchInput.value = '';
    if (clearBtn) clearBtn.style.display = 'none';

    updateSelectedPatientLabel();
}

function selectTestForApplication(testCode) {
    if (selectedTestCodeForApplication === testCode) {
        selectedTestCodeForApplication = null;
        const panel = document.getElementById('panel-apply-selected-test');
        if (panel) {
            panel.classList.add('hide');
            panel.style.display = 'none';
        }
        document.querySelectorAll('[id^="card-test-choice-"]').forEach(card => {
            card.style.border = '2.5px solid #e2e8f0';
            card.style.background = '#ffffff';
            const checkSpan = card.querySelector('.test-card-check');
            if (checkSpan) checkSpan.style.display = 'none';
        });
        return;
    }

    selectedTestCodeForApplication = testCode;

    document.querySelectorAll('[id^="card-test-choice-"]').forEach(card => {
        const cardCode = card.id.replace('card-test-choice-', '');
        const checkSpan = card.querySelector('.test-card-check');
        if (cardCode === testCode) {
            card.style.border = '2.5px solid #702e5e';
            card.style.background = '#fdf4ff';
            if (checkSpan) checkSpan.style.display = 'inline';
        } else {
            card.style.border = '2.5px solid #e2e8f0';
            card.style.background = '#ffffff';
            if (checkSpan) checkSpan.style.display = 'none';
        }
    });

    const panel = document.getElementById('panel-apply-selected-test');
    if (panel) {
        panel.classList.remove('hide');
        panel.style.display = 'block';
    }

    const testNamesMap = {
        'AQ': 'AQ — Cociente de Espectro Autista (50 ítems - Baron-Cohen)',
        'RAADS-R': 'RAADS-R — Escala Revisada para Diagnóstico de Autismo y Asperger (80 ítems)',
        'CAT-Q': 'CAT-Q — Cuestionario de Camuflaje de Rasgos Autistas (25 ítems - Hull et al.)',
        'ASRS-ADHD': 'ASRS v1.1 — Inventario de Síntomas de TDAH en Adultos (OMS)',
        'RAVEN': 'RAVEN — Test de Matrices Progresivas de Raven (60 matrices)',
        'MCMI-II': 'MCMI-II — Inventario Multiaxial Clínico de Millon (175 ítems)',
        'HOLLAND': 'HOLLAND — Test de Intereses Vocacionales (Modelo RIASEC)',
        'BDI-II': 'BDI-II — Inventario de Depresión de Beck (21 ítems)',
        'BAI': 'BAI — Inventario de Ansiedad de Beck (21 ítems)',
        'TCS': 'TCS — Escala de Congruencia Transgénero (12 ítems)',
        'UGDS-GS': 'UGDS-GS — Escala de Disforia de Utrecht (18 ítems)'
    };

    const labelTest = document.getElementById('label-selected-test-name');
    if (labelTest) labelTest.textContent = testNamesMap[testCode] || testCode;

    updateSelectedPatientLabel();

    if (panel) {
        panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
}

function updateSelectedPatientLabel() {
    const select = document.getElementById('select-test-main-patient');
    const badge = document.getElementById('badge-patient-selected-status');
    const label = document.getElementById('label-selected-patient-name');
    const searchInput = document.getElementById('input-search-test-patient');

    if (select && select.value) {
        const selectedOpt = select.options[select.selectedIndex];
        const textVal = selectedOpt ? selectedOpt.textContent.replace(/^--.*?--\s*/, '') : 'Consultante Seleccionado';
        
        if (badge) {
            badge.innerHTML = `✓ Consultante Activo: <strong style="color:#15803d;">${textVal}</strong>`;
            badge.style.background = '#dcfce7';
            badge.style.color = '#15803d';
            badge.style.borderColor = '#86efac';
        }
        if (label) {
            label.textContent = textVal;
            label.style.color = '#15803d';
        }
        if (searchInput) {
            searchInput.style.borderColor = '#15803d';
            searchInput.style.boxShadow = '0 0 0 3px rgba(21, 128, 61, 0.1)';
        }
    } else {
        if (badge) {
            badge.innerHTML = '⚠️ Ningún consultante seleccionado';
            badge.style.background = '#fdf4ff';
            badge.style.color = '#702e5e';
            badge.style.borderColor = '#f5d0fe';
        }
        if (label) {
            label.textContent = '-- Seleccionar Paciente arriba --';
            label.style.color = '#702e5e';
        }
        if (searchInput) {
            searchInput.style.borderColor = '#702e5e';
            searchInput.style.boxShadow = 'none';
        }
    }
}

function onSelectMainPatientChange() {
    const select = document.getElementById('select-test-main-patient');
    const searchInput = document.getElementById('input-search-test-patient');
    const clearBtn = document.getElementById('btn-clear-test-patient');
    if (!select) return;

    if (!select.value) {
        clearTestPatientSelection();
        return;
    }

    const selectedOpt = select.options[select.selectedIndex];
    if (selectedOpt && selectedOpt.value && searchInput) {
        const rawTxt = selectedOpt.textContent.replace(/\s*\(CI:.*?\)/i, '').trim();
        searchInput.value = rawTxt;
        if (clearBtn) clearBtn.style.display = 'inline-flex';
    }

    updateSelectedPatientLabel();
}

async function executeMainApplyTest(modoParam) {
    const select = document.getElementById('select-test-main-patient');
    if (!select || !select.value) {
        alert("Por favor busque o seleccione un paciente primero en la barra superior.");
        if (select) select.focus();
        return;
    }

    if (!selectedTestCodeForApplication) {
        alert("Por favor haga clic sobre una de las baterías psicológicas disponibles para seleccionarla.");
        return;
    }

    const patientId = select.value;
    const testCode = selectedTestCodeForApplication;
    const modo = modoParam || 'link';

    try {
        const res = await fetch('/api/tests/asignar', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                patient_id: patientId,
                test_code: testCode,
                modo_aplicacion: modo
            })
        });

        const data = await res.json();
        if (!res.ok || data.error) {
            alert(data.error || "No se pudo asignar el test.");
            return;
        }

        const successPanel = document.getElementById('panel-apply-success-result');
        const successDetails = document.getElementById('text-apply-success-details') || document.getElementById('panel-apply-success-details');
        const successActions = document.getElementById('container-apply-success-actions') || document.getElementById('panel-apply-success-actions');

        if (successPanel) {
            successPanel.classList.remove('hide');
            successPanel.style.display = 'block';
        }

        const testUrl = data.url_test || `${window.location.origin}/evaluacion/${data.token}`;
        const whatsappUrl = data.whatsapp_url || '';
        const modoLabelHtml = modo === 'presencial' ? '💻 Presencial' : (modo === 'online' ? '📲 Portal del Paciente' : '🔗 Enlace / WhatsApp');

        if (successDetails) {
            successDetails.innerHTML = `
                <div><strong>Token ID:</strong> <code>${data.token || ''}</code></div>
                <div><strong>Modo de Aplicación:</strong> <span style="font-weight:800; color:#702e5e;">${modoLabelHtml}</span></div>
                <div><strong>Enlace generado:</strong> <a href="${testUrl}" target="_blank" style="color: #702e5e; word-break: break-all; font-weight: 700;">${testUrl}</a></div>
                ${modo === 'online' ? '<div style="margin-top: 6px; font-size: 0.84rem; color: #0284c7; font-weight: 700;">📲 La prueba ha sido asignada a la cuenta del paciente y estará visible al iniciar sesión en su app.</div>' : ''}
            `;
        }

        if (successActions) {
            let actionsHtml = `
                <button type="button" class="btn btn-sm" style="background: #702e5e; color: white; font-weight: 800; border-radius: 8px; padding: 0.55rem 1.1rem; border: none; cursor: pointer;" onclick="copyTestLink('${testUrl}')">
                    📋 Copiar Link del Test
                </button>
                <button type="button" class="btn btn-sm" style="background: #15803d; color: white; font-weight: 800; border-radius: 8px; padding: 0.55rem 1.1rem; border: none; cursor: pointer;" onclick="openTestPresencialWindow('${testUrl}')">
                    💻 Responder Presencial Ahora
                </button>
            `;

            if (whatsappUrl) {
                actionsHtml += `
                    <a href="${whatsappUrl}" target="_blank" class="btn btn-sm" style="background: #25d366; color: white; font-weight: 800; border-radius: 8px; padding: 0.55rem 1.1rem; border: none; text-decoration: none; display: inline-flex; align-items: center; gap: 4px;">
                        💬 Enviar por WhatsApp
                    </a>
                `;
            }

            successActions.innerHTML = actionsHtml;
        }

        if (successPanel) {
            successPanel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }

    } catch (e) {
        console.error("Error al asignar test:", e);
        alert("Error al asignar la evaluación.");
    }
}

function copyTestLink(linkUrl) {
    if (!linkUrl) return;
    navigator.clipboard.writeText(linkUrl).then(() => {
        alert("Enlace copiado al portapapeles con éxito.");
    }).catch(err => {
        console.error("Error al copiar link:", err);
    });
}

function openTestPresencialWindow(linkUrl) {
    if (!linkUrl) return;
    window.open(linkUrl, '_blank', 'width=900,height=750,scrollbars=yes,resizable=yes');
}

function switchTestsTab(tab) {
    const btnApply = document.getElementById('tab-btn-apply-test');
    const btnHistory = document.getElementById('tab-btn-history-test');
    const contentApply = document.getElementById('tests-tab-content-apply');
    const contentHistory = document.getElementById('tests-tab-content-history');

    if (tab === 'apply') {
        if (btnApply) { btnApply.style.background = '#ffffff'; btnApply.style.color = '#702e5e'; btnApply.style.boxShadow = '0 2px 8px rgba(0,0,0,0.08)'; }
        if (btnHistory) { btnHistory.style.background = 'transparent'; btnHistory.style.color = '#64748b'; btnHistory.style.boxShadow = 'none'; }
        if (contentApply) { contentApply.classList.remove('hide'); contentApply.style.display = 'block'; }
        if (contentHistory) { contentHistory.classList.add('hide'); contentHistory.style.display = 'none'; }
    } else {
        if (btnHistory) { btnHistory.style.background = '#ffffff'; btnHistory.style.color = '#702e5e'; btnHistory.style.boxShadow = '0 2px 8px rgba(0,0,0,0.08)'; }
        if (btnApply) { btnApply.style.background = 'transparent'; btnApply.style.color = '#64748b'; btnApply.style.boxShadow = 'none'; }
        if (contentHistory) { contentHistory.classList.remove('hide'); contentHistory.style.display = 'block'; }
        if (contentApply) { contentApply.classList.add('hide'); contentApply.style.display = 'none'; }
        loadAllAppliedTestsHistory();
    }
}

// 2. FILTRADO Y PAGINACIÓN 5x2 DEL CATÁLOGO DE TESTS
function filterTestsByCategory(catName) {
    currentCatalogCategory = catName || 'TODAS';
    currentCatalogPage = 1;

    document.querySelectorAll('#container-tests-category-filters button').forEach(btn => {
        const btnTxt = btn.textContent.trim();
        if (btnTxt.toLowerCase() === catName.toLowerCase() || (catName === 'TODAS' && btnTxt === 'Todas')) {
            btn.style.background = '#702e5e';
            btn.style.color = '#ffffff';
            btn.style.border = 'none';
        } else {
            btn.style.background = '#ffffff';
            btn.style.color = '#475569';
            btn.style.border = '1px solid #cbd5e1';
        }
    });

    renderCatalogViewWithFiltersAndPagination();
}

function filterTestsCatalogByCategory(catName) {
    filterTestsByCategory(catName);
}

function renderCatalogViewWithFiltersAndPagination() {
    const container = document.getElementById('container-tests-catalog-cards');
    const topCtrl = document.getElementById('catalog-pagination-top-controls');
    const btmCtrl = document.getElementById('catalog-pagination-bottom-controls');
    if (!container) return;

    let filtered = testsCatalogDatabase;
    if (currentCatalogCategory && currentCatalogCategory !== 'TODAS' && currentCatalogCategory !== 'todas') {
        const catNorm = currentCatalogCategory.toLowerCase();
        filtered = testsCatalogDatabase.filter(t => {
            const tCat = (t.cat || '').toLowerCase();
            if (catNorm.includes('depresión') || catNorm.includes('ansiedad')) {
                return tCat.includes('depresión') || tCat.includes('ansiedad') || t.code === 'BDI-II' || t.code === 'BAI';
            } else if (catNorm.includes('neurodivergencia') || catNorm.includes('autismo')) {
                return tCat.includes('neurodivergencia') || tCat.includes('autismo') || tCat.includes('tdah') || ['AQ', 'RAADS-R', 'CAT-Q', 'ASRS-ADHD'].includes(t.code);
            } else if (catNorm.includes('personalidad')) {
                return tCat.includes('personalidad') || t.code === 'MCMI-II';
            } else if (catNorm.includes('intelectual') || catNorm.includes('inteligencia')) {
                return tCat.includes('intelectual') || t.code === 'RAVEN';
            } else if (catNorm.includes('vocacional')) {
                return tCat.includes('vocacional') || t.code === 'HOLLAND';
            } else if (catNorm.includes('identidad') || catNorm.includes('género')) {
                return tCat.includes('identidad') || tCat.includes('género') || t.code === 'TCS' || t.code === 'UGDS-GS';
            }
            return true;
        });
    }

    const totalPages = Math.ceil(filtered.length / CATALOG_PER_PAGE) || 1;
    if (currentCatalogPage < 1) currentCatalogPage = 1;
    if (currentCatalogPage > totalPages) currentCatalogPage = totalPages;

    const startIdx = (currentCatalogPage - 1) * CATALOG_PER_PAGE;
    const pageItems = filtered.slice(startIdx, startIdx + CATALOG_PER_PAGE);

    let html = '';
    pageItems.forEach(test => {
        const isSelected = selectedTestCodeForApplication === test.code;
        const borderStyle = isSelected ? '2.5px solid #702e5e' : '2.5px solid #e2e8f0';
        const bgStyle = isSelected ? '#fdf4ff' : '#ffffff';
        const checkDisplay = isSelected ? 'inline' : 'none';
        const boxShadow = isSelected ? '0 8px 25px rgba(112, 46, 94, 0.15)' : '0 2px 8px rgba(0,0,0,0.03)';

        html += `
            <div id="card-test-choice-${test.code}" onclick="selectTestForApplication('${test.code}')" 
                 style="background: ${bgStyle}; border: ${borderStyle}; border-radius: 16px; padding: 1.15rem; cursor: pointer; transition: all 0.2s ease; display: flex; flex-direction: column; justify-content: space-between; position: relative; box-shadow: ${boxShadow};"
                 onmouseover="if(selectedTestCodeForApplication !== '${test.code}') { this.style.borderColor='#702e5e'; this.style.transform='translateY(-2px)'; }"
                 onmouseout="if(selectedTestCodeForApplication !== '${test.code}') { this.style.borderColor='#e2e8f0'; this.style.transform='none'; }">
                
                <span class="test-card-check" style="display: ${checkDisplay}; position: absolute; top: 12px; right: 14px; font-weight: 900; color: #702e5e; font-size: 1.2rem;">✓</span>

                <div>
                    <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 6px; margin-bottom: 8px;">
                        <span style="font-size: 0.7rem; font-weight: 800; text-transform: uppercase; color: #702e5e; background: #fdf4ff; border: 1px solid #f5d0fe; padding: 3px 10px; border-radius: 12px;">${test.siglas}</span>
                        <span style="font-size: 0.72rem; font-weight: 800; color: #0284c7; background: #e0f2fe; padding: 3px 8px; border-radius: 10px;">${test.itemsCount} ítems</span>
                    </div>

                    <h4 style="margin: 0 0 6px 0; font-size: 0.98rem; font-weight: 800; color: #0f172a; line-height: 1.35;">${test.name}</h4>
                    <p style="margin: 0 0 10px 0; font-size: 0.8rem; color: #64748b; line-height: 1.45; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden;">
                        ${test.desc}
                    </p>
                </div>

                <div>
                    <div style="background: #f8fafc; border-radius: 10px; padding: 8px 10px; margin-bottom: 10px; font-size: 0.73rem; color: #475569; display: flex; flex-direction: column; gap: 3px;">
                        <div><strong>👨‍⚕️ Autor:</strong> ${test.autor}</div>
                        <div><strong>👥 Población:</strong> ${test.poblacion}</div>
                        <div><strong>📊 Validez/Confiabilidad:</strong> ${test.validez}</div>
                    </div>

                    <div style="display: flex; justify-content: space-between; align-items: center; border-top: 1px dashed #cbd5e1; padding-top: 8px;">
                        <span style="font-size: 0.73rem; font-weight: 800; color: #702e5e;">${test.cat}</span>
                        <span style="font-size: 0.82rem; font-weight: 900; color: #702e5e;">Seleccionar ➔</span>
                    </div>
                </div>
            </div>
        `;
    });

    container.innerHTML = html;

    const prevDisabled = currentCatalogPage <= 1 ? 'disabled' : '';
    const nextDisabled = currentCatalogPage >= totalPages ? 'disabled' : '';

    const controlsHtml = `
        <button type="button" onclick="changeCatalogPage(-1)" ${prevDisabled} style="background: white; border: 1.5px solid #cbd5e1; border-radius: 8px; padding: 4px 12px; font-size: 0.8rem; font-weight: 700; color: #334155; cursor: pointer; opacity: ${prevDisabled ? 0.5 : 1};">
            ← Anterior
        </button>
        <span style="font-size: 0.82rem; font-weight: 800; color: #702e5e; padding: 0 4px;">
            Página ${currentCatalogPage} de ${totalPages}
        </span>
        <button type="button" onclick="changeCatalogPage(1)" ${nextDisabled} style="background: white; border: 1.5px solid #cbd5e1; border-radius: 8px; padding: 4px 12px; font-size: 0.8rem; font-weight: 700; color: #334155; cursor: pointer; opacity: ${nextDisabled ? 0.5 : 1};">
            Siguiente →
        </button>
    `;

    if (topCtrl) topCtrl.innerHTML = controlsHtml;
    if (btmCtrl) btmCtrl.innerHTML = controlsHtml;
}

function changeCatalogPage(delta) {
    currentCatalogPage += delta;
    renderCatalogViewWithFiltersAndPagination();
}

function loadTestsCatalogCards() {
    renderCatalogViewWithFiltersAndPagination();
}

// 3. HISTORIAL DE EVALUACIONES APLICADAS
async function loadAllAppliedTestsHistory() {
    const container = document.getElementById('container-applied-tests-history');
    if (!container) return;

    container.innerHTML = '<div style="padding: 2rem; text-align: center; color: #64748b; font-weight: 700;">🔄 Cargando historial de evaluaciones aplicadas...</div>';

    try {
        const resp = await fetch('/api/tests/historial');
        if (!resp.ok) {
            container.innerHTML = '<div style="padding: 2rem; text-align: center; color: #dc2626; font-weight: 700;">⚠️ Error al cargar el historial.</div>';
            return;
        }

        const data = await resp.json();
        const tests = data.tests || (Array.isArray(data) ? data : []);

        if (tests.length === 0) {
            container.innerHTML = `
                <div style="padding: 3rem 1.5rem; text-align: center; background: white; border-radius: 16px; border: 1.5px solid #e2e8f0;">
                    <div style="font-size: 2.5rem; margin-bottom: 0.5rem;">📊</div>
                    <h4 style="margin: 0 0 0.25rem 0; font-weight: 800; color: #0f172a;">No hay evaluaciones asignadas</h4>
                    <p style="font-size: 0.85rem; color: #64748b; margin: 0;">Seleccione una prueba en la pestaña superior "Aplicar Evaluación" para comenzar.</p>
                </div>
            `;
            return;
        }

        let html = `
            <div style="overflow-x: auto; background: white; border-radius: 16px; border: 1.5px solid #e2e8f0; box-shadow: 0 4px 15px rgba(0,0,0,0.03);">
                <table style="width: 100%; border-collapse: collapse; text-align: left; font-size: 0.88rem;">
                    <thead>
                        <tr style="background: #f8fafc; border-bottom: 2px solid #e2e8f0; color: #475569; font-weight: 800; font-size: 0.75rem; text-transform: uppercase;">
                            <th style="padding: 12px 16px;">Fecha</th>
                            <th style="padding: 12px 16px;">Consultante</th>
                            <th style="padding: 12px 16px;">Evaluación</th>
                            <th style="padding: 12px 16px;">Modo</th>
                            <th style="padding: 12px 16px;">Estado</th>
                            <th style="padding: 12px 16px; text-align: right;">Acciones</th>
                        </tr>
                    </thead>
                    <tbody>
        `;

        tests.forEach(t => {
            const dateStr = t.fecha_asignacion ? new Date(t.fecha_asignacion).toLocaleDateString('es-ES', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—';
            const patientName = `${t.patient_nombres || ''} ${t.patient_apellidos || ''}`.trim() || 'Consultante';
            const ciStr = t.patient_cedula ? ` (${t.patient_cedula})` : '';
            
            const isCompleted = t.estado === 'completado';
            const statusBadge = isCompleted 
                ? '<span style="background: #dcfce7; color: #15803d; border: 1px solid #86efac; padding: 4px 10px; border-radius: 12px; font-size: 0.75rem; font-weight: 800;">✓ Completado</span>'
                : '<span style="background: #fdf4ff; color: #702e5e; border: 1px solid #f5d0fe; padding: 4px 10px; border-radius: 12px; font-size: 0.75rem; font-weight: 800;">⏳ Pendiente</span>';

            const modoBadge = t.modo_aplicacion === 'presencial' ? '💻 Presencial' : (t.modo_aplicacion === 'online' ? '📲 App Online' : '🔗 Enlace / Link');

            html += `
                <tr style="border-bottom: 1px solid #f1f5f9; transition: background 0.15s;" onmouseover="this.style.background='#faf5ff'" onmouseout="this.style.background='white'">
                    <td style="padding: 12px 16px; font-weight: 700; color: #64748b; font-size: 0.82rem;">${dateStr}</td>
                    <td style="padding: 12px 16px; font-weight: 800; color: #0f172a;">${patientName} <span style="font-size: 0.78rem; color: #64748b; font-weight: 600;">${ciStr}</span></td>
                    <td style="padding: 12px 16px; font-weight: 800; color: #702e5e;">${t.test_siglas || t.test_code} <span style="font-size: 0.78rem; color: #64748b; font-weight: 600;">- ${t.test_nombre || ''}</span></td>
                    <td style="padding: 12px 16px; font-weight: 700; color: #475569; font-size: 0.82rem;">${modoBadge}</td>
                    <td style="padding: 12px 16px;">${statusBadge}</td>
                    <td style="padding: 12px 16px; text-align: right;">
                        <button type="button" onclick="copyTestLink('${t.url_test}')" title="Copiar Enlace" style="background: #f1f5f9; border: none; padding: 6px 10px; border-radius: 8px; cursor: pointer; font-size: 0.8rem; font-weight: 700; color: #334155; margin-right: 4px;">📋 Link</button>
                        ${isCompleted ? `<button type="button" onclick="window.open('/api/tests/asignacion/${t.id}/export/pdf', '_blank')" title="Descargar PDF" style="background: #15803d; color: white; border: none; padding: 6px 10px; border-radius: 8px; cursor: pointer; font-size: 0.8rem; font-weight: 800; margin-right: 4px;">📄 PDF</button>` : ''}
                        <button type="button" onclick="deleteTestAssignment('${t.id}')" title="Eliminar Asignación" style="background: #fef2f2; color: #dc2626; border: 1px solid #fecaca; padding: 6px 10px; border-radius: 8px; cursor: pointer; font-size: 0.8rem; font-weight: 800;">🗑️</button>
                    </td>
                </tr>
            `;
        });

        html += `
                    </tbody>
                </table>
            </div>
        `;
        container.innerHTML = html;

    } catch (e) {
        console.error("Error al cargar historial de tests:", e);
        container.innerHTML = '<div style="padding: 2rem; text-align: center; color: #dc2626; font-weight: 700;">⚠️ Error al cargar el historial.</div>';
    }
}

async function deleteTestAssignment(assignmentId) {
    if (!confirm("¿Está seguro de que desea eliminar esta asignación de test?")) return;

    try {
        const res = await fetch(`/api/tests/asignacion/${assignmentId}`, { method: 'DELETE' });
        if (res.ok) {
            loadAllAppliedTestsHistory();
        } else {
            alert("No se pudo eliminar la asignación.");
        }
    } catch (e) {
        console.error("Error al eliminar asignación:", e);
    }
}

// EXPORTACIONES AL OBJETO GLOBAL WINDOW (INMEDIATAS)
window.populateMainViewPatientSelect = populateMainViewPatientSelect;
window.renderTestPatientsOptions = renderTestPatientsOptions;
window.onTestPatientInputFocus = onTestPatientInputFocus;
window.filterTestPatientSelect = filterTestPatientSelect;
window.clearTestPatientSelection = clearTestPatientSelection;
window.selectTestForApplication = selectTestForApplication;
window.updateSelectedPatientLabel = updateSelectedPatientLabel;
window.onSelectMainPatientChange = onSelectMainPatientChange;
window.executeMainApplyTest = executeMainApplyTest;
window.copyTestLink = copyTestLink;
window.openTestPresencialWindow = openTestPresencialWindow;
window.switchTestsTab = switchTestsTab;
window.filterTestsByCategory = filterTestsByCategory;
window.filterTestsCatalogByCategory = filterTestsCatalogByCategory;
window.renderCatalogViewWithFiltersAndPagination = renderCatalogViewWithFiltersAndPagination;
window.changeCatalogPage = changeCatalogPage;
window.loadTestsCatalogCards = loadTestsCatalogCards;
window.loadAllAppliedTestsHistory = loadAllAppliedTestsHistory;
window.deleteTestAssignment = deleteTestAssignment;

function initTestsModule() {
    renderCatalogViewWithFiltersAndPagination();
    populateMainViewPatientSelect();
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initTestsModule);
} else {
    initTestsModule();
}
