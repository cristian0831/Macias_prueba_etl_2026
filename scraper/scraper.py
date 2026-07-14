# scraper.py

import argparse
import json
import logging
import sqlite3
import time
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

BASE_URL = "https://resultadospreccongreso2026.registraduria.gov.co"
DB_PATH  = Path(__file__).parent.parent / "db" / "puestos_2026.db"

MUNICIPIOS_DEFAULT = ["TUNJA", "DUITAMA", "PAIPA", "SOGAMOSO"]
SIGLAS_DEFAULT     = ["SE", "CA"]   # Senado, Cámara

# Retry / backoff
MAX_RETRIES  = 3
BACKOFF_BASE = 2   # segundos (2, 4, 8…)
TIMEOUT      = 15  # segundos por request

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# HTTP — fetch con retry/backoff
# ---------------------------------------------------------------------------
def fetch(url: str) -> dict:
    """Lanza RuntimeError si falla todo."""
    for intento in range(1, MAX_RETRIES + 1):
        try:
            log.debug(f"  GET {url}  (intento {intento}/{MAX_RETRIES})")
            r = requests.get(url, timeout=TIMEOUT)
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError) as e:
            if intento == MAX_RETRIES:
                raise RuntimeError(f"Falló tras {MAX_RETRIES} intentos: {url} — {e}")
            espera = BACKOFF_BASE ** intento
            log.warning(f"  Error en intento {intento}: {e}. Reintentando en {espera}s…")
            time.sleep(espera)
 
def fetch_local(path: str) -> dict:
    """Lee un archivo JSON local."""
    with open(path) as f:
        return json.load(f)
 
 
def get_data(source: str) -> dict:
    """Acepta URL o ruta local."""
    if source.startswith("http"):
        return fetch(source)
    return fetch_local(source)

# ---------------------------------------------------------------------------
# Nomenclator — obtener scopeCodes de los municipios objetivo
# ---------------------------------------------------------------------------
 
def cargar_nomenclator() -> dict:
    """Descarga el nomenclator y retorna {NOMBRE: scopeCode}."""
    url = f"{BASE_URL}/json/nomenclator.json"
    log.info("Cargando nomenclator…")
    nom = get_data(url)
 
    # Usar ámbitos de Cámara (elec=2) como referencia — los scopeCodes
    # son los mismos para Senado y Cámara en el nivel municipio
    cam_ambitos = next(x for x in nom["amb"] if x["elec"] == 2)["ambitos"]
 
    codigos = {a["n"]: a["c"] for a in cam_ambitos}
    log.info(f"  Nomenclator cargado: {len(codigos)} ámbitos geográficos")
    return codigos
 
 
def resolver_municipios(nombres: list[str], codigos: dict) -> dict:
    """Valida los municipios pedidos y retorna {NOMBRE: scopeCode}."""
    resultado = {}
    for nombre in nombres:
        nombre_upper = nombre.upper()
        if nombre_upper not in codigos:
            log.warning(f"  Municipio no encontrado en nomenclator: '{nombre}'")
            continue
        resultado[nombre_upper] = codigos[nombre_upper]
        log.info(f"  {nombre_upper} → {codigos[nombre_upper]}")
    return resultado
 
# ---------------------------------------------------------------------------
# Base de datos — esquema y helpers
# ---------------------------------------------------------------------------
 
SCHEMA_PATH = Path(__file__).parent.parent / "db" / "schema.sql"
 
def init_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA_PATH.read_text())
    conn.commit()
    log.info(f"Base de datos lista: {db_path}")
    return conn
 
# ---------------------------------------------------------------------------
# Parser — extrae campos del JSON y guarda en SQLite
# ---------------------------------------------------------------------------
 
def guardar_resultado(conn: sqlite3.Connection, municipio: str,
                      scope_code: str, sigla: str, data: dict) -> tuple[int, bool]:
    """
    INSERT OR IGNORE = idempotente.
    Retorna (id, es_nuevo): es_nuevo=False si el registro ya existía.
    """
    tot = data.get("totales", {}).get("act", {})
 
    cur = conn.execute("""
        INSERT OR IGNORE INTO resultados
            (municipio, scope_code, sigla, elec, mdhm, numact, numdep, dept,
             centota, votant, pvotant, absten, votnul, votblan, votval,
             metota, mesesc, pmesesc, raw_camaras)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        municipio, scope_code, sigla,
        data.get("elec"), data.get("mdhm"),
        data.get("numact"), data.get("numdep"), data.get("dept"),
        tot.get("centota"), tot.get("votant"), tot.get("pvotant"),
        tot.get("absten"),  tot.get("votnul"),  tot.get("votblan"),
        tot.get("votval"),  tot.get("metota"),  tot.get("mesesc"),
        tot.get("pmesesc"),
        json.dumps(data.get("camaras", []), ensure_ascii=False),  
    ))
    conn.commit()
 
    if cur.rowcount == 0:
        row = conn.execute(
            "SELECT id FROM resultados WHERE scope_code=? AND sigla=? AND mdhm=?",
            (scope_code, sigla, data.get("mdhm"))
        ).fetchone()
        return (row[0], False) if row else (None, False)
 
    return (cur.lastrowid, True)
 
 
def guardar_historico(conn: sqlite3.Connection, resultado_id: int, historico: list):
    for snap in historico:
        conn.execute("""
            INSERT OR IGNORE INTO historico
                (resultado_id, numact, numdep, mdhm, mesesc, mesfalt)
            VALUES (?,?,?,?,?,?)
        """, (
            resultado_id,
            snap.get("numact"), snap.get("numdep"), snap.get("mdhm"),
            snap.get("mesesc"), snap.get("mesfalt"),
        ))
    conn.commit()
 
# ---------------------------------------------------------------------------
# Pipeline principal
# ---------------------------------------------------------------------------
def procesar(municipio: str, scope_code: str, sigla: str,
             conn: sqlite3.Connection, sample_dir: Path | None = None):
    """Descarga, parsea y persiste un municipio+sigla."""
 
    # Fuente: API o archivo local
    if sample_dir:
        path = sample_dir / f"ACT_{sigla}_{scope_code}.json"
        if not path.exists():
            log.warning(f"  [{municipio}·{sigla}] Archivo local no encontrado: {path}")
            return
        source = str(path)
        log.info(f"  [{municipio}·{sigla}] Usando archivo local: {path.name}")
    else:
        source = f"{BASE_URL}/json/ACT/{sigla}/{scope_code}.json"
 
    try:
        data = get_data(source)
    except (RuntimeError, FileNotFoundError) as e:
        log.error(f"  [{municipio}·{sigla}] No se pudo obtener datos: {e}")
        return
 
    # Guardar resultado raíz
    resultado_id, es_nuevo = guardar_resultado(conn, municipio, scope_code, sigla, data)
    if resultado_id is None:
        log.warning(f"  [{municipio}·{sigla}] No se pudo obtener id — omitido")
        return
 
    tot = data.get("totales", {}).get("act", {})
    estado = " nuevo" if es_nuevo else " ya existía"
 
    log.info(
        f"  [{municipio}·{sigla}] {estado}  mdhm={data.get('mdhm')} | "
        f"mesas={tot.get('mesesc')}/{tot.get('metota')} ({tot.get('pmesesc')}) | "
        f"participación={tot.get('pvotant')}"
    )
 
    if not es_nuevo:
        return   # ya procesado — etl.py tampoco lo reprocesará

    guardar_historico(conn, resultado_id, data.get("historico", []))
 
 
def run(municipios: list[str], siglas: list[str],
        sample_dir: Path | None = None, db_path: Path = DB_PATH):
 
    conn = init_db(db_path)
 
    # 1. Nomenclator
    try:
        codigos = cargar_nomenclator()
    except RuntimeError as e:
        if sample_dir:
            log.warning(f"API no disponible ({e}). Usando sample_data para nomenclator.")
            path = sample_dir / "nomenclator.json"
            nom  = fetch_local(path)
            cam_ambitos = next(x for x in nom["amb"] if x["elec"] == 2)["ambitos"]
            codigos = {a["n"]: a["c"] for a in cam_ambitos}
        else:
            log.error(f"No se pudo cargar nomenclator y no hay --sample-dir: {e}")
            return
 
    # 2. Resolver nombres → scopeCodes
    municipios_map = resolver_municipios(municipios, codigos)
    if not municipios_map:
        log.error("Ningún municipio válido. Abortando.")
        return
 
    # 3. Iterar municipios × siglas
    total = len(municipios_map) * len(siglas)
    done  = 0
    log.info(f"\nIniciando extracción: {len(municipios_map)} municipio(s) × {len(siglas)} sigla(s) = {total} requests\n")
 
    for municipio, scope_code in municipios_map.items():
        for sigla in siglas:
            done += 1
            log.info(f"[{done}/{total}] {municipio} ({scope_code}) · {sigla}")
            procesar(municipio, scope_code, sigla, conn, sample_dir)
            time.sleep(0.5)   #
 
    log.info(f"\nExtracción completa. Datos en: {db_path}")
    conn.close()
 
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
 
def main():
    parser = argparse.ArgumentParser(
        description="Scraper electoral Registraduría 2026"
    )
    parser.add_argument(
        "--municipios", nargs="+", default=MUNICIPIOS_DEFAULT,
        metavar="NOMBRE",
        help=f"Lista de municipios (default: {' '.join(MUNICIPIOS_DEFAULT)})"
    )
    parser.add_argument(
        "--siglas", nargs="+", default=SIGLAS_DEFAULT,
        choices=["SE", "CA", "CN", "CT"],
        help="Tipos de elección: SE=Senado CA=Cámara CN=Consultas CT=CITREP"
    )
    parser.add_argument(
        "--sample-dir", type=Path, default=None,
        metavar="DIR",
        help="Directorio con JSONs locales (fallback si la API no responde)"
    )
    parser.add_argument(
        "--db", type=Path, default=DB_PATH,
        metavar="ARCHIVO",
        help=f"Ruta de la base de datos SQLite (default: {DB_PATH})"
    )
    args = parser.parse_args()
 
    run(
        municipios=args.municipios,
        siglas=args.siglas,
        sample_dir=args.sample_dir,
        db_path=args.db,
    )
 
 
if __name__ == "__main__":
    main()
 