// ==============================================================================
// MÓDULO INDEPENDIENTE: EVALUACIONES Y TESTS PSICOLÓGICOS
// ==============================================================================

var allTestPatientsCache = [];
var selectedTestCodeForApplication = null;
var currentCatalogCategory = 'TODAS';
var currentCatalogPage = 1;
var CATALOG_PER_PAGE = 10; // Vista cuadrícula 5x2 (10 por página)

// BASE DE DATOS DE EVALUACIONES PSICOMÉTRICAS CON METADATOS COMPLETOS
var testsCatalogDatabase = [
    // --- NUEVAS EVALUACIONES DE VIOLENCIA Y PSICOSIS ---
    { 
        code: 'CUVINO', 
        name: 'CUVINO  Cuestionario de Violencia entre Novios', 
        siglas: 'CUVINO', 
        cat: 'Violencia y Abuso', 
        desc: 'Evala de forma multidimensional la violencia recibida en la relacin (castigo emocional, desapego, humillacin, coercin).', 
        autor: 'Plantilla Estndar', 
        poblacion: 'Adolescentes y Adultos', 
        validez: 'Uso Clnico', 
        itemsCount: 15,
        isPhysical: false,
        instrucciones: 'Lea cada afirmacin y seleccione con qu frecuencia ha experimentado esto en su relacin.'
    },
    { 
        code: 'ABUSO-COERCITIVO', 
        name: 'EAPC  Escala de Abuso Psicolgico y Control Coercitivo', 
        siglas: 'EAPC', 
        cat: 'Violencia y Abuso', 
        desc: 'Instrumento basado en la Rueda de Poder y Control. Identifica tcticas de aislamiento, control de rutinas y limitacin de la movilidad.', 
        autor: 'Plantilla Estndar', 
        poblacion: 'Adultos', 
        validez: 'Uso Clnico', 
        itemsCount: 10,
        isPhysical: false,
        instrucciones: 'Indique con qu frecuencia su pareja ha realizado las siguientes acciones.'
    },
    { 
        code: 'VIOLENCIA-ECON', 
        name: 'IVEP  Inventario de Violencia Econmica y Patrimonial', 
        siglas: 'IVEP', 
        cat: 'Violencia y Abuso', 
        desc: 'Mide la restriccin de acceso al dinero, prohibicin de trabajar/estudiar y dependencia financiera forzada.', 
        autor: 'Plantilla Estndar', 
        poblacion: 'Adultos', 
        validez: 'Uso Clnico', 
        itemsCount: 10,
        isPhysical: false,
        instrucciones: 'Responda con qu frecuencia ocurren las siguientes situaciones en su entorno financiero/patrimonial.'
    },
    { 
        code: 'BPRS', 
        name: 'BPRS  Escala Breve de Psiquiatra', 
        siglas: 'BPRS', 
        cat: 'Psicopatologa y Clnica', 
        desc: 'Evala la gravedad de sntomas psicopatolgicos generales (aislamiento, suspicacia, alteracin del pensamiento). APLICACIN POR EL CLNICO.', 
        autor: 'Overall & Gorham', 
        poblacion: 'Adultos', 
        validez: 'Uso Clnico Evaluador', 
        itemsCount: 18,
        isPhysical: false,
        instrucciones: 'EXCLUSIVO DEL TERAPEUTA: Evale del 1 al 7 la gravedad del sntoma observado durante la consulta.'
    },
    { 
        code: 'PANSS-POS', 
        name: 'PANSS  Subescala Positiva', 
        siglas: 'PANSS-P', 
        cat: 'Psicopatologa y Clnica', 
        desc: 'Valora la presencia focalizada de ideas delirantes, suspicacia o distorsiones severas de la realidad. APLICACIN POR EL CLNICO.', 
        autor: 'Kay et al.', 
        poblacion: 'Adultos', 
        validez: 'Uso Clnico Evaluador', 
        itemsCount: 7,
        isPhysical: false,
        instrucciones: 'EXCLUSIVO DEL TERAPEUTA: Evale del 1 al 7 la gravedad de los sntomas positivos.'
    },
    { 
        code: 'JUICIO-REALIDAD', 
        name: 'IPRJC  Inventario de Percepcin de Realidad y Juicio Clnico', 
        siglas: 'IPRJC', 
        cat: 'Psicopatologa y Clnica', 
        desc: 'Explora la congruencia entre los hechos percibidos y el entorno observable a travs de comprobacin de realidad. APLICACIN POR EL CLNICO.', 
        autor: 'Plantilla Clnica', 
        poblacion: 'Adultos', 
        validez: 'Uso Clnico Evaluador', 
        itemsCount: 10,
        isPhysical: false,
        instrucciones: 'EXCLUSIVO DEL TERAPEUTA: Valore la percepcin de la realidad del consultante.'
    },

    // 1. NEURODIVERGENCIA Y AUTISMO
    { 
        code: 'AQ', 
        name: 'AQ — Cociente de Espectro Autista', 
        siglas: 'AQ-50', 
        cat: 'Neurodesarrollo y Neuropsicología', 
        desc: 'Evaluación estandarizada de 50 ítems desarrollada por Baron-Cohen et al. Mide rasgos del espectro autista en adultos.', 
        autor: 'Simon Baron-Cohen et al.', 
        poblacion: 'Adolescentes y Adultos (16+ años)', 
        validez: 'α = 0.82 | Punto de corte: ≥ 32', 
        itemsCount: 50,
        isPhysical: false,
        instrucciones: 'El consultante debe leer cada afirmación y seleccionar el grado de acuerdo. Tiempo estimado: 10-15 minutos.'
    },
    { 
        code: 'RAADS-R', 
        name: 'RAADS-R — Escala Revisada para Diagnóstico de Autismo', 
        siglas: 'RAADS-R', 
        cat: 'Neurodesarrollo y Neuropsicología', 
        desc: 'Inventario clínico completo de 80 ítems para el diagnóstico del Espectro Autista / Asperger en población adulta.', 
        autor: 'Riva Ariella Ritvo et al.', 
        poblacion: 'Adultos (18+ años)', 
        validez: 'α = 0.92 | Umbral diagnóstico: ≥ 65', 
        itemsCount: 80,
        isPhysical: false,
        instrucciones: 'Cuestionario autoaplicado. Seleccionar la frecuencia con la que se presenta cada comportamiento a lo largo de su vida. Tiempo estimado: 20-30 minutos.'
    },
    { 
        code: 'CAT-Q', 
        name: 'CAT-Q — Cuestionario de Camuflaje Autista', 
        siglas: 'CAT-Q', 
        cat: 'Neurodesarrollo y Neuropsicología', 
        desc: 'Evaluación de 25 ítems desarrollada por Laura Hull et al. Mide estrategias de camuflaje y enmascaramiento social.', 
        autor: 'Laura Hull et al.', 
        poblacion: 'Adolescentes y Adultos (16+ años)', 
        validez: 'α = 0.90 | Medición de Camuflaje', 
        itemsCount: 25,
        isPhysical: false,
        instrucciones: 'Responder considerando cómo se comporta en situaciones sociales. Marcar la opción que mejor describa sus acciones. Tiempo estimado: 10 minutos.'
    },
    { 
        code: 'ASRS-ADHD', 
        name: 'ASRS v1.1 — Sintomatología TDAH en Adultos', 
        siglas: 'ASRS v1.1', 
        cat: 'Neurodesarrollo y Neuropsicología', 
        desc: 'Escala de tamizaje oficial de la OMS de 18 ítems para la detección de Trastorno por Déficit de Atención e Hiperactividad en adultos.', 
        autor: 'OMS / Adler et al.', 
        poblacion: 'Adultos (18+ años)', 
        validez: 'α = 0.87 | Criterios DSM / OMS', 
        itemsCount: 18,
        isPhysical: false,
        instrucciones: 'Evaluar la frecuencia de cada síntoma en los últimos 6 meses. Útil para screening. Tiempo estimado: 5-10 minutos.'
    },
    {
        code: 'ADOS-2',
        name: 'ADOS-2 — Escala de Observación para el Diagnóstico del Autismo',
        siglas: 'ADOS-2',
        cat: 'Neurodesarrollo y Neuropsicología',
        desc: 'Protocolo estandarizado de observación clínica y algoritmo de afecto social (AS) y conductas repetitivas (CRR).',
        autor: 'Catherine Lord et al. (2012)',
        poblacion: 'Niños y Adultos (Módulos T, 1, 2, 3, 4)',
        validez: 'Sensibilidad 91% | Estándar de Oro Diagnóstico TEA',
        itemsCount: 14,
        isPhysical: true,
        downloadUrl: '/static/test_materials/ados2_protocolo_observacion.pdf',
        instrucciones: 'Aplicación estructurada presencial por profesional clínico. Requiere materiales específicos según el módulo. Grabar sesión si es posible.'
    },

    // 2. DEPRESIÓN Y ANSIEDAD
    { 
        code: 'BDI-II', 
        name: 'BDI-II — Inventario de Depresión de Beck', 
        siglas: 'BDI-II', 
        cat: 'Afectividad, Depresión y Ansiedad', 
        desc: 'Cuestionario de 21 ítems de autorreporte ampliamente utilizado para evaluar la severidad de los síntomas depresivos.', 
        autor: 'Aaron T. Beck et al.', 
        poblacion: 'Adolescentes y Adultos (13+ años)', 
        validez: 'α = 0.92 | Validez Clínica Estandarizada', 
        itemsCount: 21,
        isPhysical: false,
        instrucciones: 'Se entrega al consultante el cuestionario de 21 ítems. Se le pide que lea cada grupo de afirmaciones y seleccione la que mejor describe cómo se ha sentido durante las últimas dos semanas. No hay respuestas correctas ni incorrectas. Tiempo estimado: 5-10 minutos.'
    },
    { 
        code: 'BAI', 
        name: 'BAI — Inventario de Ansiedad de Beck', 
        siglas: 'BAI', 
        cat: 'Afectividad, Depresión y Ansiedad', 
        desc: 'Evaluación de 21 ítems diseñada para discriminar y medir la intensidad de la sintomatología ansiosa somática y cognitiva.', 
        autor: 'Aaron T. Beck et al.', 
        poblacion: 'Adolescentes y Adultos (13+ años)', 
        validez: 'α = 0.92 | Alta Especificidad Ansiosa', 
        itemsCount: 21,
        isPhysical: false,
        instrucciones: 'Pedir al consultante que indique cuánto le ha molestado cada síntoma durante la última semana en una escala de 0 a 3. Tiempo estimado: 5-10 minutos.'
    },
    {
        code: 'ZUNG-SDS',
        name: 'ZUNG-SDS — Escala Autoaplicada de Depresión de Zung',
        siglas: 'ZUNG-SDS',
        cat: 'Afectividad, Depresión y Ansiedad',
        desc: 'Evaluación cuantitativa de 20 reactivos orientada a cuantificar los síntomas afectivos, fisiológicos y psicológicos de la depresión.',
        autor: 'William W.K. Zung',
        poblacion: 'Adolescentes y Adultos (15+ años)',
        validez: 'α = 0.88 | Índice de Depresión',
        itemsCount: 20,
        isPhysical: false,
        downloadUrl: '/static/test_materials/zung_depresion_escala.pdf',
        instrucciones: 'Responder según cómo se ha sentido en los últimos días marcando una de las cuatro opciones. Tiempo estimado: 10 minutos.'
    },
    {
        code: 'HAMILTON-D',
        name: 'HAMILTON-D — Escala de Depresión de Hamilton (HDRS)',
        siglas: 'HAM-D',
        cat: 'Afectividad, Depresión y Ansiedad',
        desc: 'Escala heteroaplicada de 17 ítems para la evaluación cuantitativa de la severidad del cuadro depresivo y respuesta terapéutica.',
        autor: 'Max Hamilton',
        poblacion: 'Adultos (18+ años)',
        validez: 'α = 0.90 | Estándar Clínico Heteroaplicado',
        itemsCount: 17,
        isPhysical: false,
        downloadUrl: '/static/test_materials/hamilton_depresion_cuestionario.pdf',
        instrucciones: 'Aplicado mediante entrevista estructurada por un profesional clínico. Evaluar síntomas en la última semana.'
    },
    {
        code: 'IDARE-STAI',
        name: 'IDARE / STAI — Inventario de Ansiedad Rasgo-Estado',
        siglas: 'IDARE',
        cat: 'Afectividad, Depresión y Ansiedad',
        desc: 'Evaluación dual de 40 reactivos que distingue la ansiedad transitoria (Estado) de la predisposición ansiosa permanente (Rasgo).',
        autor: 'Spielberger, Gorsuch y Lushene',
        poblacion: 'Adolescentes y Adultos (15+ años)',
        validez: 'α = 0.91 | Evaluación Rasgo / Estado',
        itemsCount: 40,
        isPhysical: false,
        downloadUrl: '/static/test_materials/idare_stai_instrumento.pdf',
        instrucciones: 'Contiene dos partes (Estado y Rasgo). Leer instrucciones previas a cada sección. Tiempo estimado: 15-20 minutos.'
    },
    {
        code: 'BECK-BHS',
        name: 'BHS — Escala de Desesperanza de Beck',
        siglas: 'BHS',
        cat: 'Afectividad, Depresión y Ansiedad',
        desc: 'Inventario de 20 frases Verdadero/Falso diseñado para evaluar las actitudes negativas y desesperanza hacia el futuro (indicador de riesgo).',
        autor: 'Aaron T. Beck et al.',
        poblacion: 'Adolescentes y Adultos (13+ años)',
        validez: 'α = 0.93 | Factor de Riesgo Clínico',
        itemsCount: 20,
        isPhysical: false,
        downloadUrl: '/static/test_materials/beck_desesperanza.pdf',
        instrucciones: 'Indicar verdadero o falso para cada afirmación pensando en la última semana. Evaluar riesgo suicida según puntaje.'
    },

    // 3. PSICOPATOLOGÍA Y SÍNTOMAS GENERALES
    {
        code: 'SCL-90-R',
        name: 'SCL-90-R — Cuestionario de 90 Síntomas Revisado',
        siglas: 'SCL-90-R',
        cat: 'Personalidad y Psicopatología',
        desc: 'Evaluación autoadministrada de 90 ítems en escala Likert que explora 9 dimensiones sintomáticas de malestar psicológico.',
        autor: 'Leonard R. Derogatis',
        poblacion: 'Adolescentes y Adultos (13+ años)',
        validez: 'α = 0.95 | Perfil Sintomático 9 Dimensiones',
        itemsCount: 90,
        isPhysical: false,
        downloadUrl: '/static/test_materials/scl90r_cuestionario.pdf',
        instrucciones: 'Responder en base al malestar sentido en los últimos 7 días. Escala de 0 (nada) a 4 (mucho). Tiempo estimado: 15-20 minutos.'
    },
    { 
        code: 'MCMI-II', 
        name: 'MCMI-II — Inventario Multiaxial Clínico de Millon', 
        siglas: 'MCMI-II', 
        cat: 'Personalidad y Psicopatología', 
        desc: 'Instrumento multiaxial psicométrico de 175 ítems para la evaluación de patrones de personalidad clínica y síndromes severos.', 
        autor: 'Theodore Millon', 
        poblacion: 'Adultos (18+ años)', 
        validez: 'Estandarizado TB | 24 Escalones Clínicos', 
        itemsCount: 175,
        isPhysical: false,
        instrucciones: 'Responder verdadero o falso a las afirmaciones. Requiere alta comprensión lectora. Tiempo estimado: 45-60 minutos.'
    },
    {
        code: 'MMPI-2',
        name: 'MMPI-2 — Inventario Multifásico de Personalidad de Minnesota',
        siglas: 'MMPI-2',
        cat: 'Personalidad y Psicopatología',
        desc: 'Inventario clínico de 567 reactivos V/F para evaluación multiaxial de personalidad, validez y psicopatología.',
        autor: 'Hathaway & McKinley',
        poblacion: 'Adultos (18+ años)',
        validez: '10 Escalas Clínicas | L, F, K',
        itemsCount: 567,
        isPhysical: false,
        downloadUrl: '/static/test_materials/mmpi-2_cuadernillo.pdf',
        instrucciones: 'Cuestionario extenso de verdadero o falso. Aplicar en ambiente tranquilo sin interrupciones. Imprimir hojas de respuesta o cuadernillo. Tiempo estimado: 60-90 minutos.'
    },

    // 4. CAPACIDAD INTELECTUAL Y NEUROPSICOLOGÍA
    { 
        code: 'RAVEN', 
        name: 'RAVEN — Test de Matrices Progresivas de Raven', 
        siglas: 'RAVEN', 
        cat: 'Cognición y Capacidad Intelectual', 
        desc: 'Prueba no verbal de 60 matrices estandarizadas para medir el factor g de inteligencia y la capacidad de razonamiento abstracto.', 
        autor: 'John C. Raven', 
        poblacion: 'Adolescentes y Adultos (12+ años)', 
        validez: 'α = 0.90 | Razonamiento No Verbal', 
        itemsCount: 60,
        isPhysical: false,
        instrucciones: 'Presentar las matrices progresivas una a una. El consultante debe identificar la pieza que completa cada patrón. No hay límite de tiempo estricto. Tiempo promedio: 30-45 minutos.'
    },
    {
        code: 'MMSE',
        name: 'MMSE — Mini-Mental State Examination (Folstein)',
        siglas: 'MMSE',
        cat: 'Cognición y Capacidad Intelectual',
        desc: 'Prueba neuropsicológica de 30 puntos ampliamente utilizada para el tamizaje de deterioro cognitivo y memoria.',
        autor: 'Folstein, Folstein & McHugh',
        poblacion: 'Adultos Mayores (18+ años)',
        validez: 'Sensibilidad 87% | Tamizaje Cognitivo',
        itemsCount: 30,
        isPhysical: true,
        downloadUrl: '/static/test_materials/minimental_hoja_respuesta.pdf',
        instrucciones: 'Administración individual presencial. Seguir estrictamente las consignas verbales y mostrar materiales gráficos cuando corresponda.'
    },
    {
        code: 'MOCA-TEST',
        name: 'MoCA — Montreal Cognitive Assessment',
        siglas: 'MoCA',
        cat: 'Cognición y Capacidad Intelectual',
        desc: 'Evaluación cognitiva breve de 30 puntos diseñada para la detección precoz de Deterioro Cognitivo Leve (DCL).',
        autor: 'Ziad Nasreddine et al.',
        poblacion: 'Adultos y Adultos Mayores (55+ años)',
        validez: 'Sensibilidad 90% para DCL',
        itemsCount: 30,
        isPhysical: true,
        downloadUrl: '/static/test_materials/moca_test_espanol.pdf',
        instrucciones: 'Administración guiada presencial. Usar la hoja impresa y seguir las pautas de puntuación estandarizadas.'
    },
    {
        code: 'INECO-IFS',
        name: 'INECO — Frontal Screening (Versión Venezuela)',
        siglas: 'INECO',
        cat: 'Cognición y Capacidad Intelectual',
        desc: 'Batería neuropsicológica breve validada con baremos de Venezuela para la evaluación de funciones ejecutivas frontales.',
        autor: 'Teresa Torralva et al.',
        poblacion: 'Adultos (18+ años)',
        validez: 'Baremos Venezuela | Funciones Ejecutivas',
        itemsCount: 8,
        isPhysical: true,
        downloadUrl: '/static/test_materials/ineco_venezuela_protocolo.pdf',
        instrucciones: 'Administración presencial por un clínico entrenado. Entregar consignas paso a paso. Requiere cronómetro y láminas impresas.'
    },
    {
        code: 'TMT-AB',
        name: 'TMT — Trail Making Test (Partes A y B)',
        siglas: 'TMT A/B',
        cat: 'Cognición y Capacidad Intelectual',
        desc: 'Prueba papel y lápiz de atención dividida, velocidad de procesamiento motor y flexibilidad cognitiva.',
        autor: 'Army Individual Test Battery',
        poblacion: 'Adolescentes y Adultos (15+ años)',
        validez: 'Estandarizado | Funciones Ejecutivas',
        itemsCount: 2,
        isPhysical: true,
        downloadUrl: '/static/test_materials/trail_making_test_tmt.pdf',
        instrucciones: 'El consultante debe unir los puntos lo más rápido posible sin levantar el lápiz. Medir tiempo de ejecución con cronómetro. Requiere hoja impresa.'
    },

    // 5. MATERIALES PROYECTIVOS Y GRÁFICOS (DESCARGABLES / IMPRIMIBLES)
    {
        code: 'HTP-TEST',
        name: 'HTP — Test de Dibujo Casa-Árbol-Persona',
        siglas: 'HTP',
        cat: 'Pruebas Proyectivas',
        desc: 'Técnica proyectiva gráfica de dibujo libre para la evaluación de la personalidad, autoimagen y mecanismos de defensa.',
        autor: 'John N. Buck',
        poblacion: 'Niños, Adolescentes y Adultos',
        validez: 'Técnica Proyectiva Cualitativa',
        itemsCount: 3,
        isPhysical: true,
        downloadUrl: '/static/test_materials/htp_manual_protocolo.pdf',
        instrucciones: 'Entregar hojas en blanco y lápiz. Solicitar dibujo de casa, árbol y persona. Observar secuencia, borraduras y comentarios espontáneos.'
    },
    {
        code: 'WARTEGG-TEST',
        name: 'WARTEGG — Test de Dibujo de 8/16 Campos',
        siglas: 'WARTEGG',
        cat: 'Pruebas Proyectivas',
        desc: 'Prueba proyectiva de dibujo sobre cuadros de estímulos para la evaluación de la estructura de personalidad e integración del Yo.',
        autor: 'Ehrig Wartegg',
        poblacion: 'Adolescentes y Adultos',
        validez: 'Técnica Proyectiva Estructurada',
        itemsCount: 8,
        isPhysical: true,
        downloadUrl: '/static/test_materials/wartegg_protocolo.pdf',
        instrucciones: 'Entregar la hoja de 8/16 campos impresa. Pedir que complete cada dibujo y luego asigne un título y orden. Observar ejecución.'
    },
    {
        code: 'SACKS-TEST',
        name: 'SACKS — Test de Frases Incompletas para Adultos',
        siglas: 'SACKS',
        cat: 'Pruebas Proyectivas',
        desc: 'Inventario proyectivo verbal de 60 frases incompletas que explora 4 áreas del sujeto: familia, sexo, relaciones y concepto de sí mismo.',
        autor: 'Joseph M. Sacks',
        poblacion: 'Adultos (18+ años)',
        validez: 'Análisis Cualitativo de Actitudes',
        itemsCount: 60,
        isPhysical: true,
        downloadUrl: '/static/test_materials/sacks_adultos_protocolo.doc',
        instrucciones: 'Pedir que complete cada frase con lo primero que se le venga a la mente. Se puede aplicar por escrito u oral. Entregar impreso.'
    },
    {
        code: 'TAT-TEST',
        name: 'TAT — Test de Apercepción Temática (Manual Corto)',
        siglas: 'TAT',
        cat: 'Pruebas Proyectivas',
        desc: 'Técnica proyectiva narrativa a través de láminas estructuradas para el análisis de necesidades, presiones y conflictos inconscientes.',
        autor: 'Henry A. Murray',
        poblacion: 'Adolescentes y Adultos',
        validez: 'Análisis Dinámico de la Personalidad',
        itemsCount: 20,
        isPhysical: true,
        downloadUrl: '/static/test_materials/tat_manual_protocolo.doc',
        instrucciones: 'Mostrar las láminas impresas una a una. Pedir que narre una historia con pasado, presente y futuro para cada una. Registrar verbatim.'
    },
    {
        code: 'REY-OSTERRIETH',
        name: 'REY-O — Figura Compleja de Rey-Osterrieth',
        siglas: 'REY-O',
        cat: 'Cognición y Capacidad Intelectual',
        desc: 'Prueba viso-constructiva de copia y reproducción de memoria para evaluar organización perceptual y memoria visual.',
        autor: 'André Rey & Paul-Alexandre Osterrieth',
        poblacion: 'Niños (8+) y Adultos',
        validez: 'Estandarizada | Evaluación Neuropsicológica',
        itemsCount: 18,
        isPhysical: true,
        downloadUrl: '/static/test_materials/figura_rey_osterrieth.pdf',
        instrucciones: 'Fase 1: Copia de la figura impresa. Fase 2: Reproducción de memoria. Entregar colores distintos para medir proceso de copia.'
    },

    // 6. ORIENTACIÓN VOCACIONAL E IDENTIDAD DE GÉNERO
    { 
        code: 'HOLLAND', 
        name: 'HOLLAND — Test de Intereses Vocacionales (RIASEC)', 
        siglas: 'HOLLAND', 
        cat: 'Cognición y Capacidad Intelectual', 
        desc: 'Inventario vocacional basado en el modelo tipológico RIASEC para la identificación de perfil vocacional y profesional.', 
        autor: 'John L. Holland', 
        poblacion: 'Adolescentes y Adultos (14+ años)', 
        validez: 'α = 0.86 | Perfil Tipológico RIASEC', 
        itemsCount: 60,
        isPhysical: false,
        instrucciones: 'El consultante debe seleccionar las actividades y ocupaciones de su interés. Tiempo estimado: 20 minutos.'
    },
    { 
        code: 'TCS', 
        name: 'TCS — Escala de Congruencia Transgénero', 
        siglas: 'TCS', 
        cat: 'Sexología y Salud Sexual', 
        desc: 'Escala de 12 ítems desarrollada por Kozee et al. para evaluar el nivel de confort y aceptación de la identidad de género.', 
        autor: 'Kozee, Reisner et al.', 
        poblacion: 'Jóvenes y Adultos (16+ años)', 
        validez: 'α = 0.89 | Afirmación e Identidad', 
        itemsCount: 12,
        isPhysical: false,
        instrucciones: 'Responder según su grado de acuerdo con las afirmaciones. Tiempo estimado: 5-10 minutos.'
    },
    { 
        code: 'UGDS-GS', 
        name: 'UGDS-GS — Escala de Disforia de Utrecht', 
        siglas: 'UGDS-GS', 
        cat: 'Sexología y Salud Sexual', 
        desc: 'Evaluación estandarizada de 18 ítems para la medición objetiva del grado de disforia de género clínica.', 
        autor: 'McGuire et al. / Utrecht', 
        poblacion: 'Adolescentes y Adultos (12+ años)', 
        validez: 'α = 0.91 | Medición de Disforia', 
        itemsCount: 18,
        isPhysical: false,
        instrucciones: 'Responder la frecuencia de sentimientos relacionados al género. Tiempo estimado: 10 minutos.'
    },

    // 7. PRUEBAS CLÍNICAS, SALUD SEXUAL Y AFRONTAMIENTO (VALIDADAS EN POBLACIÓN HISPANA)
    {
        code: 'RCMAS-2',
        name: 'RCMAS-2 — Escala de Ansiedad Manifiesta en Niños Revisada',
        siglas: 'RCMAS-2',
        cat: 'Test Infanto-Juvenil',
        desc: 'Evaluación estandarizada de 49 ítems para detectar niveles de ansiedad fisiológica, inquietud, hipersensibilidad y defensividad en niños y adolescentes.',
        autor: 'Cecil R. Reynolds & Bert O. Richmond (TEA Ediciones)',
        poblacion: 'Niños y Adolescentes (6 a 19 años)',
        validez: 'Validez Clínica Estandarizada Hispana (Baremos T)',
        itemsCount: 49,
        isPhysical: false,
        instrucciones: 'Cuestionario infantil. Responder "Sí" o "No". Si hay dificultad lectora, el clínico puede leer los ítems en voz alta.'
    },
    {
        code: 'CDS-CTI',
        name: 'CDS / CTI — Cuestionario de Distorsiones Cognitivas',
        siglas: 'CDS',
        cat: 'Cognición y Capacidad Intelectual',
        desc: 'Evaluación autoadministrada de pensamientos automáticos y errores del procesamiento cognitivo (Catastrofización, Filtro Mental, Lectura de Mente, etc.).',
        autor: 'Yurica & DiTomasso / Adaptación Hispana',
        poblacion: 'Adolescentes y Adultos (14+ años)',
        validez: 'Terapia Cognitivo-Conductual (TCC)',
        itemsCount: 20,
        isPhysical: false,
        instrucciones: 'Responder considerando los pensamientos más frecuentes en situaciones estresantes recientes. Tiempo estimado: 10 minutos.'
    },
    {
        code: 'CSI',
        name: 'CSI — Cuestionario de Estrategias de Afrontamiento',
        siglas: 'CSI',
        cat: 'Cognición y Capacidad Intelectual',
        desc: 'Evaluación de 40 ítems Likert para cuantificar 8 estilos de afrontamiento (Solución de Problemas, Apoyo Social, Reestructuración Cognitiva, Evitación, Autocrítica, etc.).',
        autor: 'Tobin et al. / Adaptación de Cano, Rodríguez y García',
        poblacion: 'Adolescentes y Adultos (15+ años)',
        validez: 'α = 0.89 | Adaptación Iberoamericana',
        itemsCount: 40,
        isPhysical: false,
        instrucciones: 'Responder cada ítem basándose en una situación estresante reciente y cómo se afrontó. Tiempo estimado: 15-20 minutos.'
    },
    {
        code: 'DVQ-R',
        name: 'DVQ-R — Cuestionario de Violencia en el Noviazgo',
        siglas: 'DVQ-R',
        cat: 'Afectividad, Depresión y Ansiedad',
        desc: 'Evaluación estandarizada de 20 ítems para detectar conductas de abuso físico, verbal, coercitivo, sexual y desapego en relaciones de pareja.',
        autor: 'Rodríguez-Franco et al.',
        poblacion: 'Adolescentes y Jóvenes (14 a 30 años)',
        validez: 'Validado en Población Hispana y Latina',
        itemsCount: 20,
        isPhysical: false,
        instrucciones: 'Responder la frecuencia de las situaciones experimentadas en la relación actual o más reciente. Confidencialidad es clave.'
    },
    {
        code: 'EAQ',
        name: 'EAQ — Cuestionario de Conciencia Emocional Infanto-Juvenil',
        siglas: 'EAQ',
        cat: 'Test Infanto-Juvenil',
        desc: 'Evaluación de 30 ítems para identificar diferenciación de emociones, atención a señales emocionales, análisis y ocultación emocional.',
        autor: 'Rieffe et al. / Adaptación de Gómez-Ortiz et al.',
        poblacion: 'Niños y Adolescentes (8 a 16 años)',
        validez: 'Evaluación de Inteligencia Emocional y Auto-conciencia',
        itemsCount: 30,
        isPhysical: false,
        instrucciones: 'Cuestionario autoaplicado para niños/adolescentes. Explicar claramente que no hay respuestas incorrectas.'
    },
    {
        code: 'CUSES-SAS',
        name: 'CUSES / SAS — Autoeficacia y Asertividad Sexual',
        siglas: 'CUSES',
        cat: 'Sexología y Salud Sexual',
        desc: 'Evaluación de autoeficacia en salud sexual, prevención de ITS y capacidad de negociación/asertividad en la conducta sexual.',
        autor: 'López-Rosales et al. / Sierra et al.',
        poblacion: 'Adolescentes y Adultos (15+ años)',
        validez: 'Validación en Psicología de la Salud y Sexología',
        itemsCount: 20,
        isPhysical: false,
        instrucciones: 'Responder de forma honesta basándose en experiencias pasadas o hipotéticas de relaciones íntimas. Tiempo estimado: 10 minutos.'
    },

    // 8. BIENESTAR Y SATISFACCIÓN
    {
        code: 'SWLS',
        name: 'SwLS — Escala de Satisfacción con la Vida (Diener)',
        siglas: 'SwLS',
        cat: 'Afectividad, Depresión y Ansiedad',
        desc: 'Evaluación psicométrica cuantitativa de 5 reactivos para medir el juicio cognitivo global sobre la satisfacción con la propia vida.',
        autor: 'Ed Diener et al. / Vázquez et al.',
        poblacion: 'Adolescentes y Adultos (12+ años)',
        validez: 'α = 0.78 | Estándar Internacional de Bienestar Subjetivo',
        itemsCount: 5,
        isPhysical: false,
        instrucciones: 'Leer cada afirmación e indicar el grado de acuerdo en escala de 1 a 7. No hay respuestas correctas ni incorrectas. Tiempo estimado: 2-3 minutos.'
    },

    // 9. SEXOLOGÍA Y SALUD SEXUAL (ADICIONALES)
    {
        code: 'SHIM',
        name: 'SHIM / IIEF-5 — Inventario de Salud Sexual para Hombres (Disfunción Eréctil)',
        siglas: 'SHIM',
        cat: 'Sexología y Salud Sexual',
        desc: 'Herramienta clínica abreviada de 5 reactivos para la evaluación y estadificación de la función eréctil y salud sexual masculina. Clasifica severidad: grave, moderada, leve o sin disfunción.',
        autor: 'Rosen et al. (IIEF-5)',
        poblacion: 'Hombres Adultos (18+ años)',
        validez: 'Validación Clínica Internacional',
        itemsCount: 5,
        isPhysical: false,
        instrucciones: 'Responder las 5 preguntas sobre función sexual de los últimos 6 meses. Garantizar privacidad y confidencialidad. Tiempo estimado: 3-5 minutos.'
    },
    {
        code: 'NSSS-S',
        name: 'NSSS-S — Nueva Escala de Satisfacción Sexual (Forma Corta)',
        siglas: 'NSSS-S',
        cat: 'Sexología y Salud Sexual',
        desc: 'Evaluación psicométrica de 12 ítems Likert para medir la satisfacción sexual en dimensiones egocéntrica y centrada en la pareja.',
        autor: 'Štulhofer et al.',
        poblacion: 'Adultos (18+ años)',
        validez: 'α = 0.94 | Subescalas Egocéntrica y Pareja',
        itemsCount: 12,
        isPhysical: false,
        instrucciones: 'Responder cada ítem indicando el nivel de satisfacción en la vida sexual reciente. Asegurar ambiente privado y confidencial. Tiempo estimado: 5-8 minutos.'
    },
    {
        code: 'FSFI',
        name: 'FSFI — Índice de Función Sexual Femenina (Disfunción Sexual)',
        siglas: 'FSFI',
        cat: 'Sexología y Salud Sexual',
        desc: 'Cuestionario clínico multidimensional de 19 ítems estándar de oro que evalúa 6 dominios: deseo, excitación, lubricación, orgasmo, satisfacción y dolor femenino.',
        autor: 'Rosen et al. / Blümel et al.',
        poblacion: 'Mujeres Adultas (18+ años)',
        validez: 'Estándar de Oro en Sexología Femenina',
        itemsCount: 19,
        isPhysical: false,
        instrucciones: 'Responder considerando la actividad sexual de las últimas 4 semanas. Explicar que incluye actividad con o sin pareja. Ambiente privado. Tiempo estimado: 10-15 minutos.'
    },
    {
        code: 'BSSC',
        name: 'BSSC — Lista de Chequeo Breve de Síntomas Sexuales',
        siglas: 'BSSC',
        cat: 'Sexología y Salud Sexual',
        desc: 'Herramienta de cribado clínico ultra-rápido de 4 preguntas para la identificación temprana de inquietudes o síntomas sexuales.',
        autor: 'Hatzichristou et al. / Medicina Sexual',
        poblacion: 'Adultos (18+ años)',
        validez: 'Tamizaje Rápido de 4 Preguntas',
        itemsCount: 4,
        isPhysical: false,
        instrucciones: 'Responder las 4 preguntas de forma breve. Ideal como cribado inicial en consulta. Tiempo estimado: 1-2 minutos.'
    },

    // 10. ADULTO MAYOR / PSICOGERONTOLOGÍA
    {
        code: 'AtAS',
        name: 'AtAS — Escala de Adaptación al Envejecimiento',
        siglas: 'AtAS',
        cat: 'Adulto Mayor',
        desc: 'Evaluación psicométrica de 10 reactivos Likert para medir propósito, adaptación emocional, salud y apoyo social en adultos mayores.',
        autor: 'dos Santos et al.',
        poblacion: 'Adultos Mayores (50+ años)',
        validez: 'α = 0.891 | Adaptación al Envejecimiento Activo',
        itemsCount: 10,
        isPhysical: false,
        instrucciones: 'Responder cada afirmación indicando el grado de acuerdo. Puede leerse en voz alta si hay dificultad de lectura. Tiempo estimado: 5-8 minutos.'
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

    // Show full test details
    const infoContainer = document.getElementById('container-selected-test-info');
    if (infoContainer) {
        const testObj = testsCatalogDatabase.find(t => t.code === testCode);
        if (testObj) {
            infoContainer.innerHTML = `
                <div style="background: #f8fafc; border: 1.5px solid #e2e8f0; border-radius: 14px; padding: 1.1rem;">
                    <div style="display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 10px;">
                        <span style="font-size: 0.72rem; font-weight: 800; color: #702e5e; background: #fdf4ff; border: 1px solid #f5d0fe; padding: 2px 8px; border-radius: 8px;">${testObj.cat}</span>
                        <span style="font-size: 0.72rem; font-weight: 800; color: #0284c7; background: #e0f2fe; padding: 2px 8px; border-radius: 8px;">${testObj.itemsCount} ítems</span>
                        <span style="font-size: 0.72rem; font-weight: 800; color: ${testObj.isPhysical ? '#d97706' : '#16a34a'}; background: ${testObj.isPhysical ? '#fef3c7' : '#dcfce7'}; padding: 2px 8px; border-radius: 8px;">${testObj.isPhysical ? '📄 Material Físico' : '⚡ Digital'}</span>
                    </div>
                    <h4 style="margin: 0 0 6px 0; font-size: 1rem; font-weight: 800; color: #0f172a;">📋 Descripción Completa</h4>
                    <p style="margin: 0 0 12px 0; font-size: 0.88rem; color: #334155; line-height: 1.5;">${testObj.desc}</p>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 12px;">
                        <div style="font-size: 0.82rem; color: #475569;"><strong>👨⚕️ Autor:</strong> ${testObj.autor}</div>
                        <div style="font-size: 0.82rem; color: #475569;"><strong>👥 Población:</strong> ${testObj.poblacion}</div>
                        <div style="font-size: 0.82rem; color: #475569;"><strong>📊 Validez:</strong> ${testObj.validez}</div>
                    </div>
                    ${testObj.instrucciones ? `
                        <div style="background: #fffbeb; border: 1px solid #fde68a; border-radius: 10px; padding: 0.85rem; margin-top: 8px;">
                            <h5 style="margin: 0 0 6px 0; font-size: 0.9rem; font-weight: 800; color: #92400e;">📝 Instrucciones de Aplicación</h5>
                            <p style="margin: 0; font-size: 0.82rem; color: #78350f; line-height: 1.5; white-space: pre-line;">${testObj.instrucciones}</p>
                        </div>
                    ` : ''}
                </div>
            `;
        } else {
            infoContainer.innerHTML = '';
        }
    }

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
    if (window.isApplyingTestInFlight) return;

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

    // Deshabilitar botones para prevenir doble clic
    window.isApplyingTestInFlight = true;
    const applyButtons = document.querySelectorAll("#panel-apply-selected-test button");
    applyButtons.forEach(btn => {
        btn.disabled = true;
        btn.style.opacity = '0.6';
        btn.style.pointerEvents = 'none';
    });

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

        // Actualizar historial inmediatamente
        if (typeof loadAllAppliedTestsHistory === 'function') {
            loadAllAppliedTestsHistory();
        }

        const successPanel = document.getElementById('panel-apply-success-result');
        const successDetails = document.getElementById('text-apply-success-details') || document.getElementById('panel-apply-success-details');
        const successActions = document.getElementById('container-apply-success-actions') || document.getElementById('panel-apply-success-actions');

        if (successPanel) {
            successPanel.classList.remove('hide');
            successPanel.style.display = 'block';
            successPanel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }

        const testUrl = data.url_test || `${window.location.origin}/evaluacion/${data.token}`;
        const whatsappUrl = data.whatsapp_url || '';
        const modoLabelHtml = modo === 'presencial' ? '💻 Presencial' : (modo === 'online' ? '📲 Portal del Paciente' : '🔗 Enlace / WhatsApp');

        let statusNoticeHtml = '';
        if (data.whatsapp_sent) {
            statusNoticeHtml = '<div style="margin-top: 6px; font-size: 0.84rem; color: #16a34a; font-weight: 700;">✅ Notificación enviada por WhatsApp al consultante de forma automática.</div>';
        } else if (modo === 'online') {
            statusNoticeHtml = '<div style="margin-top: 6px; font-size: 0.84rem; color: #0284c7; font-weight: 700;">📲 La prueba ha sido asignada al portal del paciente y estará visible al iniciar sesión en su app.</div>';
        } else {
            statusNoticeHtml = '<div style="margin-top: 6px; font-size: 0.84rem; color: #702e5e; font-weight: 700;">🔗 Enlace generado y listo para compartir.</div>';
        }

        if (successDetails) {
            successDetails.innerHTML = `
                <div style="background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px; padding: 0.6rem 0.85rem; margin-bottom: 0.75rem; color: #166534; font-weight: 700; font-size: 0.86rem;">
                    ✓ ¡Solicitud registrada y guardada con éxito en el historial!
                </div>
                <div style="margin-top: 0.35rem;"><strong>Token ID:</strong> <code style="background: #f1f5f9; padding: 2px 6px; border-radius: 4px;">${data.token || ''}</code></div>
                <div style="margin-top: 0.35rem;"><strong>Modo de Aplicación:</strong> <span style="font-weight:800; color:#702e5e;">${modoLabelHtml}</span></div>
                <div style="margin-top: 0.35rem;"><strong>Enlace generado:</strong> <a href="${testUrl}" target="_blank" style="color: #702e5e; word-break: break-all; font-weight: 700;">${testUrl}</a></div>
                ${statusNoticeHtml}
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

    } catch (e) {
        console.error("Error al asignar test:", e);
        alert("Error al asignar la evaluación.");
    } finally {
        window.isApplyingTestInFlight = false;
        applyButtons.forEach(btn => {
            btn.disabled = false;
            btn.style.opacity = '1';
            btn.style.pointerEvents = 'auto';
        });
    }
}

function resetTestApplicationModule() {
    selectedTestCodeForApplication = null;

    if (typeof loadAllAppliedTestsHistory === 'function') {
        loadAllAppliedTestsHistory();
    }

    const panelApply = document.getElementById('panel-apply-selected-test');
    if (panelApply) {
        panelApply.classList.add('hide');
        panelApply.style.display = 'none';
    }

    const successPanel = document.getElementById('panel-apply-success-result');
    if (successPanel) {
        successPanel.classList.add('hide');
        successPanel.style.display = 'none';
    }

    document.querySelectorAll('[id^="card-test-choice-"]').forEach(card => {
        card.style.border = '2.5px solid #e2e8f0';
        card.style.background = '#ffffff';
        const checkSpan = card.querySelector('.test-card-check');
        if (checkSpan) checkSpan.style.display = 'none';
    });

    const successDetails = document.getElementById('text-apply-success-details') || document.getElementById('panel-apply-success-details');
    const successActions = document.getElementById('container-apply-success-actions') || document.getElementById('panel-apply-success-actions');
    if (successDetails) successDetails.innerHTML = '';
    if (successActions) successActions.innerHTML = '';

    const topContainer = document.getElementById('container-tests-catalog') || document.getElementById('select-test-main-patient');
    if (topContainer) {
        topContainer.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    if (typeof showToast === 'function') {
        showToast('✅ Evaluación guardada en el historial. Listo para iniciar nueva solicitud.', 'success');
    }
}
window.resetTestApplicationModule = resetTestApplicationModule;

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
            const tCode = (t.code || '').toLowerCase();
            return tCat.includes(catNorm) || catNorm.includes(tCat) || tCode.includes(catNorm);
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

        const typeBadge = test.isPhysical
            ? `<span style="font-size: 0.65rem; font-weight: 800; color: #d97706; background: #fef3c7; border: 1px solid #fde68a; padding: 2px 7px; border-radius: 8px; white-space: nowrap;">📄 Material Físico</span>`
            : `<span style="font-size: 0.65rem; font-weight: 800; color: #16a34a; background: #dcfce7; border: 1px solid #bbf7d0; padding: 2px 7px; border-radius: 8px; white-space: nowrap;">⚡ Digital</span>`;

        const matFileName = test.downloadUrl ? test.downloadUrl.replace(/^.*[\\\/]/, '') : '';
        const downloadBtn = test.downloadUrl
            ? `<a href="/api/tests/materials/${matFileName}" target="_blank" onclick="event.stopPropagation();" title="Descargar material/protocolo para imprimir" style="background: #fff7ed; border: 1px solid #ffedd5; color: #c2410c; font-size: 0.72rem; font-weight: 800; padding: 3px 8px; border-radius: 8px; text-decoration: none; display: inline-flex; align-items: center; gap: 3px; margin-right: 4px;">
                📥 Descargar
               </a>`
            : '';

        html += `
            <div id="card-test-choice-${test.code}" onclick="selectTestForApplication('${test.code}')" 
                 style="background: ${bgStyle}; border: ${borderStyle}; border-radius: 14px; padding: 0.8rem 0.9rem; cursor: pointer; transition: all 0.2s ease; display: flex; flex-direction: column; justify-content: space-between; position: relative; box-shadow: ${boxShadow}; box-sizing: border-box;"
                 onmouseover="if(selectedTestCodeForApplication !== '${test.code}') { this.style.borderColor='#702e5e'; this.style.transform='translateY(-2px)'; }"
                 onmouseout="if(selectedTestCodeForApplication !== '${test.code}') { this.style.borderColor='#e2e8f0'; this.style.transform='none'; }">
                
                <span class="test-card-check" style="display: ${checkDisplay}; position: absolute; top: 10px; right: 12px; font-weight: 900; color: #702e5e; font-size: 1.1rem;">✓</span>

                <div>
                    <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 4px; margin-bottom: 6px; flex-wrap: wrap;">
                        <span style="font-size: 0.65rem; font-weight: 800; text-transform: uppercase; color: #702e5e; background: #fdf4ff; border: 1px solid #f5d0fe; padding: 2px 7px; border-radius: 10px;">${test.siglas}</span>
                        <div style="display: flex; align-items: center; gap: 4px;">
                            <span style="font-size: 0.68rem; font-weight: 800; color: #0284c7; background: #e0f2fe; padding: 2px 7px; border-radius: 8px;">${test.itemsCount} ítems</span>
                            ${typeBadge}
                        </div>
                    </div>

                    <h4 style="margin: 0 0 4px 0; font-size: 0.88rem; font-weight: 800; color: #0f172a; line-height: 1.3;">${test.name}</h4>
                    <p style="margin: 0 0 8px 0; font-size: 0.74rem; color: #64748b; line-height: 1.35; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;">
                        ${test.desc}
                    </p>
                </div>

                <div>
                    <div style="background: #f8fafc; border-radius: 8px; padding: 6px 8px; margin-bottom: 6px; font-size: 0.68rem; color: #475569; display: flex; flex-direction: column; gap: 2px;">
                        <div><strong>👨‍⚕️ Autor:</strong> ${test.autor}</div>
                        <div><strong>👥 Población:</strong> ${test.poblacion}</div>
                        <div><strong>📊 Validez:</strong> ${test.validez}</div>
                    </div>

                    <div style="display: flex; justify-content: space-between; align-items: center; border-top: 1px dashed #cbd5e1; padding-top: 6px;">
                        <span style="font-size: 0.68rem; font-weight: 800; color: #702e5e;">${test.cat}</span>
                        <div style="display: flex; align-items: center;">
                            ${downloadBtn}
                            <span style="font-size: 0.78rem; font-weight: 900; color: #702e5e;">${test.isPhysical ? 'Registrar ➔' : 'Seleccionar ➔'}</span>
                        </div>
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

    if (topCtrl) topCtrl.innerHTML = '';
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
    const container = document.getElementById('main-tests-history-container') || document.getElementById('container-applied-tests-history') || document.getElementById('tests-history-container') || document.getElementById('patient-tests-history-container');
    if (!container) return;

    container.innerHTML = '<div style="padding: 2rem; text-align: center; color: #64748b; font-weight: 700;">🔄 Cargando historial de evaluaciones aplicadas...</div>';

    try {
        const resp = await fetch('/api/tests/historial');
        if (!resp.ok) {
            container.innerHTML = '<div style="padding: 2rem; text-align: center; color: #dc2626; font-weight: 700;">⚠️ Error al cargar el historial.</div>';
            return;
        }

        const data = await resp.json();
        const tests = data.asignaciones || data.tests || (Array.isArray(data) ? data : []);

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
            <div style="overflow-x: auto; -webkit-overflow-scrolling: touch; width: 100%; background: white; border-radius: 16px; border: 1.5px solid #e2e8f0; box-shadow: 0 4px 15px rgba(0,0,0,0.03);">
                <table style="width: 100%; min-width: 720px; border-collapse: collapse; text-align: left; font-size: 0.88rem;">
                    <thead>
                        <tr style="background: #f8fafc; border-bottom: 2px solid #e2e8f0; color: #475569; font-weight: 800; font-size: 0.75rem; text-transform: uppercase; white-space: nowrap;">
                            <th style="padding: 14px 16px; white-space: nowrap; width: 130px;">Fecha</th>
                            <th style="padding: 14px 16px; min-width: 140px;">Consultante</th>
                            <th style="padding: 14px 16px; min-width: 200px;">Evaluación</th>
                            <th style="padding: 14px 16px; white-space: nowrap; width: 120px;">Modo</th>
                            <th style="padding: 14px 16px; white-space: nowrap; width: 110px;">Estado</th>
                            <th style="padding: 14px 16px; text-align: center; white-space: nowrap; min-width: 220px;">Acciones</th>
                        </tr>
                    </thead>
                    <tbody>
        `;

        tests.forEach(t => {
            const dateStr = t.fecha_asignacion ? new Date(t.fecha_asignacion).toLocaleDateString('es-ES', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—';
            const patientName = `${t.patient_nombres || ''} ${t.patient_apellidos || ''}`.trim() || 'Consultante';
            const ciStr = t.patient_cedula ? ` (${t.patient_cedula})` : '';
            const testUrl = t.url_test || (t.uuid_token ? `/evaluacion/${t.uuid_token}` : '');
            
            const isCompleted = t.estado === 'completado';
            const statusBadge = isCompleted 
                ? '<span style="display: inline-block; white-space: nowrap; background: #dcfce7; color: #15803d; border: 1px solid #86efac; padding: 4px 12px; border-radius: 14px; font-size: 0.75rem; font-weight: 800;">✓ Completado</span>'
                : '<span style="display: inline-block; white-space: nowrap; background: #fdf4ff; color: #702e5e; border: 1px solid #f5d0fe; padding: 4px 12px; border-radius: 14px; font-size: 0.75rem; font-weight: 800;">⏳ Pendiente</span>';

            const modoBadge = t.modo_aplicacion === 'presencial' ? '💻 Presencial' : (t.modo_aplicacion === 'online' ? '📲 App Online' : '🔗 Enlace / Link');

            html += `
                <tr style="border-bottom: 1px solid #f1f5f9; transition: background 0.15s;" onmouseover="this.style.background='#faf5ff'" onmouseout="this.style.background='white'">
                    <td style="padding: 14px 16px; font-weight: 700; color: #64748b; font-size: 0.82rem; white-space: nowrap;">${dateStr}</td>
                    <td style="padding: 14px 16px; font-weight: 800; color: #0f172a; min-width: 140px;">
                        <div>${patientName}</div>
                        ${ciStr ? `<div style="font-size: 0.78rem; color: #64748b; font-weight: 600; margin-top: 2px;">${ciStr}</div>` : ''}
                    </td>
                    <td style="padding: 14px 16px; min-width: 200px;">
                        <div style="font-weight: 800; color: #702e5e;">${t.test_siglas || t.test_code}</div>
                        ${t.test_nombre ? `<div style="font-size: 0.8rem; color: #475569; font-weight: 600; margin-top: 2px; line-height: 1.35;">${t.test_nombre}</div>` : ''}
                    </td>
                    <td style="padding: 14px 16px; font-weight: 700; color: #475569; font-size: 0.82rem; white-space: nowrap;">${modoBadge}</td>
                    <td style="padding: 14px 16px; white-space: nowrap;">${statusBadge}</td>
                    <td style="padding: 14px 16px; text-align: center; white-space: nowrap;">
                        <div style="display: flex; gap: 6px; justify-content: center; align-items: center;">
                            ${testUrl ? `
                                <a href="${testUrl}" target="_blank" title="Abrir Evaluación en nueva pestaña" style="display: inline-flex; align-items: center; gap: 4px; background: #702e5e; color: white; border: none; padding: 6px 12px; border-radius: 8px; font-size: 0.8rem; font-weight: 800; text-decoration: none; box-shadow: 0 2px 6px rgba(112,46,94,0.25);">
                                    🚀 Abrir
                                </a>
                                <button type="button" onclick="copyTestLink('${testUrl}')" title="Copiar Enlace al Portapapeles" style="display: inline-flex; align-items: center; gap: 4px; background: #f1f5f9; border: 1.5px solid #cbd5e1; padding: 6px 10px; border-radius: 8px; cursor: pointer; font-size: 0.8rem; font-weight: 700; color: #334155;">
                                    📋 Link
                                </button>
                            ` : ''}
                            ${isCompleted ? `<button type="button" onclick="window.open('/api/tests/asignacion/${t.id}/export/pdf', '_blank')" title="Descargar Informe PDF" style="display: inline-flex; align-items: center; gap: 4px; background: #15803d; color: white; border: none; padding: 6px 10px; border-radius: 8px; cursor: pointer; font-size: 0.8rem; font-weight: 800; box-shadow: 0 2px 6px rgba(21,128,61,0.25);">📄 PDF</button>` : ''}
                            <button type="button" onclick="deleteTestAssignment('${t.id}')" title="Eliminar Asignación" style="display: inline-flex; align-items: center; justify-content: center; background: #fef2f2; color: #dc2626; border: 1px solid #fecaca; padding: 6px 9px; border-radius: 8px; cursor: pointer; font-size: 0.8rem; font-weight: 800;">🗑️</button>
                        </div>
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
