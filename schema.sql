CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pacientes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombres TEXT NOT NULL,
    apellidos TEXT NOT NULL,
    cedula TEXT UNIQUE NOT NULL,
    pronombre TEXT,
    genero TEXT,
    edad INTEGER,
    lugar_nacimiento TEXT,
    fecha_nacimiento TEXT,
    residencia_actual TEXT,
    con_quien_reside TEXT,
    nivel_academico TEXT,
    ocupacion TEXT,
    estado_civil TEXT,
    telefono TEXT,
    email TEXT,
    
    -- Antecedentes
    antecedentes_medicos_familiares TEXT,
    antecedentes_medicos_personales TEXT,
    antecedentes_psicologicos_familiares TEXT,
    antecedentes_psicologicos_personales TEXT,
    asistencia_previa_psicologo TEXT,
    motivo_consulta TEXT,
    expectativas TEXT,
    farmacologia TEXT,
    
    -- Emergencia y Diagnóstico
    contacto_emergencia_nombre TEXT,
    contacto_emergencia_parentesco TEXT,
    diagnostico TEXT,
    
    -- Credenciales de Paciente (PWA)
    username TEXT UNIQUE,
    password_hash TEXT,
    pregunta_seguridad_1 TEXT,
    respuesta_seguridad_1_hash TEXT,
    pregunta_seguridad_2 TEXT,
    respuesta_seguridad_2_hash TEXT,
    
    fecha_registro DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sesiones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paciente_id INTEGER NOT NULL,
    agenda_id INTEGER,
    fecha TEXT NOT NULL,
    modalidad TEXT NOT NULL, -- 'Presencial', 'Online', 'Uptaeb'
    estado TEXT DEFAULT 'Realizada', -- 'Realizada', 'Cancelada', 'Reprogramada'
    resumen TEXT,
    resumen_paciente TEXT,
    tareas_asignadas TEXT,
    recursos_entregados TEXT,
    anotaciones_proxima TEXT,
    compromisos_psicologo TEXT,
    diagnostico TEXT,
    test_aplicados TEXT,
    archivo_adjunto TEXT,
    FOREIGN KEY (paciente_id) REFERENCES pacientes(id) ON DELETE CASCADE,
    FOREIGN KEY (agenda_id) REFERENCES agenda_finanzas(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS agenda_finanzas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paciente_id INTEGER NOT NULL,
    fecha TEXT NOT NULL,
    hora TEXT NOT NULL,
    google_event_id TEXT UNIQUE,
    tipo_consulta TEXT NOT NULL, -- 'Presencial', 'Online'
    monto REAL NOT NULL DEFAULT 0.0,
    moneda TEXT NOT NULL, -- 'USD', 'EUR', 'BSD'
    estado_pago TEXT NOT NULL, -- 'Paga', 'Pendiente', 'Prepagada'
    control_uso TEXT NOT NULL DEFAULT 'Consumida', -- 'Consumida', 'No consumida'
    fecha_liquidacion TEXT,
    confirmada INTEGER DEFAULT 0,
    FOREIGN KEY (paciente_id) REFERENCES pacientes(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS configuracion (
    clave TEXT PRIMARY KEY,
    valor TEXT
);

CREATE TABLE IF NOT EXISTS pizarra_terapeutica (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paciente_id INTEGER NOT NULL,
    fecha TEXT NOT NULL,
    contenido TEXT NOT NULL,
    FOREIGN KEY (paciente_id) REFERENCES pacientes(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS web_push_subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    patient_id INTEGER,
    endpoint TEXT NOT NULL,
    p256dh TEXT NOT NULL,
    auth TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fcm_subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    patient_id INTEGER,
    token TEXT UNIQUE
);

CREATE TABLE IF NOT EXISTS modulos_terapeuticos_paciente (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paciente_id INTEGER NOT NULL,
    modulo_clave TEXT NOT NULL,
    activo INTEGER DEFAULT 1,
    configuracion_json TEXT,
    fecha_asignacion DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (paciente_id) REFERENCES pacientes(id) ON DELETE CASCADE,
    UNIQUE(paciente_id, modulo_clave)
);

CREATE TABLE IF NOT EXISTS registros_sueno (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paciente_id INTEGER NOT NULL,
    fecha TEXT NOT NULL,
    situaciones_dia TEXT,
    emociones_dia TEXT,
    proceso_dormir TEXT,
    hora_dormi TEXT,
    desperto_noche INTEGER DEFAULT 0,
    cant_despertares INTEGER DEFAULT 0,
    hora_desperto TEXT,
    senti_descanso INTEGER DEFAULT 1,
    somnolencia_dia INTEGER DEFAULT 0,
    pesadez_dia INTEGER DEFAULT 0,
    agotamiento_dia INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (paciente_id) REFERENCES pacientes(id) ON DELETE CASCADE,
    UNIQUE(paciente_id, fecha)
);

CREATE TABLE IF NOT EXISTS registros_ansiedad (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paciente_id INTEGER NOT NULL,
    fecha TEXT NOT NULL,
    nivel_ansiedad INTEGER NOT NULL,
    sintomas_json TEXT,
    situacion_desencadenante TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (paciente_id) REFERENCES pacientes(id) ON DELETE CASCADE,
    UNIQUE(paciente_id, fecha)
);

CREATE TABLE IF NOT EXISTS registros_sobriedad (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paciente_id INTEGER NOT NULL,
    fecha TEXT NOT NULL,
    sobrio INTEGER NOT NULL,
    nivel_ansiedad INTEGER,
    disparador_emocional TEXT,
    notas TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (paciente_id) REFERENCES pacientes(id) ON DELETE CASCADE,
    UNIQUE(paciente_id, fecha)
);

CREATE TABLE IF NOT EXISTS adherencia_medicamentos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paciente_id INTEGER NOT NULL,
    nombre_medicamento TEXT NOT NULL,
    dosis TEXT,
    hora_prescrita TEXT,
    activo INTEGER DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (paciente_id) REFERENCES pacientes(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS adherencia_registros (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paciente_id INTEGER NOT NULL,
    medicamento_id INTEGER NOT NULL,
    fecha TEXT NOT NULL,
    tomado INTEGER NOT NULL,
    hora_tomado TEXT,
    notas TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (paciente_id) REFERENCES pacientes(id) ON DELETE CASCADE,
    FOREIGN KEY (medicamento_id) REFERENCES adherencia_medicamentos(id) ON DELETE CASCADE,
    UNIQUE(paciente_id, medicamento_id, fecha)
);

CREATE TABLE IF NOT EXISTS activacion_actividades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paciente_id INTEGER NOT NULL,
    psicologo_id INTEGER,
    categoria TEXT NOT NULL,
    nombre_actividad TEXT NOT NULL,
    activa INTEGER DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (paciente_id) REFERENCES pacientes(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS activacion_registros (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paciente_id INTEGER NOT NULL,
    actividad_id INTEGER NOT NULL,
    fecha TEXT NOT NULL,
    completada INTEGER NOT NULL,
    notas TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (paciente_id) REFERENCES pacientes(id) ON DELETE CASCADE,
    FOREIGN KEY (actividad_id) REFERENCES activacion_actividades(id) ON DELETE CASCADE,
    UNIQUE(paciente_id, actividad_id, fecha)
);

