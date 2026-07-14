-- schema.sql

-- ---------------------------------------------------------------------------
-- Tabla principal: un registro por municipio × elección × avance
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS resultados (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Identificación del ámbito
    municipio   TEXT    NOT NULL,                   -- nombre del municipio (TUNJA, etc.)
    scope_code  TEXT    NOT NULL,                   -- código geográfico (0700001)
    sigla       TEXT    NOT NULL CHECK (sigla IN ('SE','CA','CN','CT')),
    elec        TEXT    NOT NULL,                   -- tipo de elección 
    dept        TEXT    NOT NULL,                   -- código de departamento 

    -- Control de avance
    mdhm        TEXT    NOT NULL,                   -- timestamp MMDDHHMM del avance
    numact      TEXT,
    numdep      TEXT,

    -- Mesas
    metota      TEXT    NOT NULL,                   -- total mesas
    mesesc      TEXT    NOT NULL,                   -- mesas escrutadas
    pmesesc     TEXT,

    -- Totales electorales
    centota     TEXT    NOT NULL,                   -- censo electoral
    votant      TEXT    NOT NULL,                   -- total votantes
    pvotant     TEXT,
    absten      TEXT,
    votnul      TEXT,
    votblan     TEXT,
    votval      TEXT,

    -- JSON crudo de camaras[] para procesamiento ETL posterior
    raw_camaras TEXT,

    -- Control de carga
    scraped_at  TEXT    NOT NULL DEFAULT (datetime('now')),

    -- Idempotencia: mismo municipio+elección+avance no se duplica
    UNIQUE (scope_code, sigla, mdhm)
);

-- ---------------------------------------------------------------------------
-- Resultados por partido dentro de cada circunscripción
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS partidos (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    resultado_id INTEGER NOT NULL REFERENCES resultados(id) ON DELETE CASCADE,

    cam          TEXT    NOT NULL,                  -- circunscripción: 0=Nacional, 1=Territorial, 4=Indígenas, 5=Afro
    codpar       TEXT    NOT NULL,                  -- código del partido (cruzar con nomenclator)
    vot          TEXT,                              -- votos obtenidos
    pvot         TEXT,                              -- % de votos
    carg         TEXT,                              -- curules obtenidas
    cargElectos  TEXT,

    UNIQUE (resultado_id, cam, codpar),
    FOREIGN KEY (resultado_id) REFERENCES resultados(id) ON DELETE CASCADE
);

-- ---------------------------------------------------------------------------
-- Candidatos por partido
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS candidatos (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    partido_id   INTEGER NOT NULL REFERENCES partidos(id) ON DELETE CASCADE,

    amb          TEXT    NOT NULL,                  -- scopeCode del ámbito del candidato
    codcan       TEXT    NOT NULL,                  -- código del candidato (0 = solo por lista)
    cedula       TEXT,
    nomcan       TEXT,
    apecan       TEXT,
    nomcan2      TEXT,
    apecan2      TEXT,
    vot          TEXT,
    pvot         TEXT,
    carg         TEXT,
    pref         TEXT    NOT NULL DEFAULT '0',      -- 0=lista cerrada, 1=preferencial
    empate       TEXT    NOT NULL DEFAULT '0',

    UNIQUE (partido_id, codcan),
    FOREIGN KEY (partido_id) REFERENCES partidos(id) ON DELETE CASCADE
);

-- ---------------------------------------------------------------------------
-- Snapshots históricos de avances anteriores
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS historico (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    resultado_id INTEGER NOT NULL REFERENCES resultados(id) ON DELETE CASCADE,

    mdhm         TEXT    NOT NULL,                  -- timestamp del avance histórico
    numact       TEXT,
    numdep       TEXT,
    mesesc       TEXT,
    mesfalt      TEXT,

    UNIQUE (resultado_id, mdhm),
    FOREIGN KEY (resultado_id) REFERENCES resultados(id) ON DELETE CASCADE
);

-- ---------------------------------------------------------------------------
-- Catálogo de partidos (fuente: nomenclator.json → partidos[])
-- Una sola fila por partido a nivel nacional — deduplicación cross-municipio
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS partidos_catalogo (
    codpar      TEXT    PRIMARY KEY,                -- código único del partido
    nombre      TEXT    NOT NULL,                   -- nombre oficial normalizado
    color       TEXT,                               -- color hex (#RRGGBB)
    slug        TEXT                                -- versión URL-friendly del nombre
);

-- ---------------------------------------------------------------------------
-- Índices de optimización
-- ---------------------------------------------------------------------------

-- idx_partidos_resultado: acelera los JOINs partidos→resultados que aparecen en
-- tarea_3_1 (arrastre verde), tarea_3_2 (dominancia extrema) y tarea_3_3
-- (atribución SE). Sin este índice SQLite hace full-scan de partidos en cada JOIN.
CREATE INDEX IF NOT EXISTS idx_partidos_resultado
    ON partidos (resultado_id);

-- idx_partidos_codpar: acelera el filtro AND p.codpar = '5'/'57' en tarea_3_1
-- y el JOIN ON p_se.codpar = p_ca.codpar en tarea_3_3 cuando se busca
-- el partido homólogo entre Senado y Cámara por código.
CREATE INDEX IF NOT EXISTS idx_partidos_codpar
    ON partidos (codpar);

-- idx_candidatos_partido: acelera el JOIN candidatos→partidos en tarea_3_2
-- (dominancia extrema) y tarea_3_3 (atribución), que recorren todos los
-- candidatos de cada partido en cada municipio.
CREATE INDEX IF NOT EXISTS idx_candidatos_partido
    ON candidatos (partido_id);

-- ---------------------------------------------------------------------------
-- Log de cada ejecución del scraper (fase 2)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS carga_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    iniciado_en     TEXT    NOT NULL DEFAULT (datetime('now')),
    finalizado_en   TEXT,
    municipios      TEXT    NOT NULL,               -- lista JSON de municipios procesados
    siglas          TEXT    NOT NULL,               -- lista JSON de siglas procesadas
    fuente          TEXT    NOT NULL DEFAULT 'api', -- 'api' o 'sample_data'
    resultados_nuevos  INTEGER NOT NULL DEFAULT 0,
    resultados_omitidos INTEGER NOT NULL DEFAULT 0,
    errores         INTEGER NOT NULL DEFAULT 0,
    estado          TEXT    NOT NULL DEFAULT 'EN_CURSO'
                            CHECK (estado IN ('EN_CURSO','OK','ERROR'))
);
