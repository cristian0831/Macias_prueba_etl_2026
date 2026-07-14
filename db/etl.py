# etl.py
# Transforma y carga partidos y candidatos desde los datos crudos del scraper.
# Responsabilidades:
#   1. Cargar catálogo de partidos desde el nomenclator (deduplicación cross-municipio)
#   2. Normalizar nombres de candidatos
#   3. Insertar partidos y candidatos con INSERT OR IGNORE
#   4. Reportar filas insertadas vs omitidas por tabla
#

import argparse
import json
import logging
import re
import sqlite3
import unicodedata
from pathlib import Path

import requests

BASE_URL     = "https://resultadospreccongreso2026.registraduria.gov.co"
DB_PATH      = Path(__file__).parent / "puestos_2026.db"
NOM_URL      = f"{BASE_URL}/json/nomenclator.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Normalización de nombres
# ---------------------------------------------------------------------------

def normalizar_nombre(texto: str | None) -> str:
    """
    Limpia y normaliza un nombre de candidato:
      - Elimina espacios al inicio/fin y espacios múltiples internos
      - Convierte a Title Case
      - Preserva tildes (no las elimina — son parte del nombre oficial)
    """
    if not texto:
        return ""
    # Colapsar espacios múltiples y strip
    limpio = re.sub(r"\s+", " ", texto.strip())
    # Title Case respetando tildes
    return limpio.title()


# ---------------------------------------------------------------------------
# Catálogo de partidos (nomenclator → partidos_catalogo)
# ---------------------------------------------------------------------------

def cargar_catalogo_partidos(conn: sqlite3.Connection,
                              nom_url: str | None = None,
                              nom_file: Path | None = None) -> dict[str, str]:
    """
    Descarga el nomenclator, extrae la lista de partidos y la inserta en
    partidos_catalogo con INSERT OR IGNORE (deduplicación cross-municipio).
    Retorna {codpar: nombre} para uso posterior.
    """
    log.info("Cargando catálogo de partidos desde nomenclator…")

    if nom_file:
        nom = json.loads(nom_file.read_text())
    else:
        url = nom_url or NOM_URL
        r   = requests.get(url, timeout=15)
        r.raise_for_status()
        nom = r.json()

    partidos_raw = nom.get("partidos", [])
    insertados = omitidos = 0

    for p in partidos_raw:
        codpar = str(p.get("codpar", "")).strip()
        nombre = normalizar_nombre(p.get("nombre"))
        color  = p.get("color", "")
        slug   = p.get("s", "")

        if not codpar:
            continue

        cur = conn.execute("""
            INSERT OR IGNORE INTO partidos_catalogo (codpar, nombre, color, slug)
            VALUES (?, ?, ?, ?)
        """, (codpar, nombre, color, slug))

        if cur.rowcount > 0:
            insertados += 1
        else:
            omitidos += 1

    conn.commit()
    log.info(f"  partidos_catalogo → insertados: {insertados}  omitidos: {omitidos}")

    catalogo = {
        str(p.get("codpar")): normalizar_nombre(p.get("nombre"))
        for p in partidos_raw
    }
    return catalogo


# ---------------------------------------------------------------------------
# Carga de partidos y candidatos desde raw_camaras
# ---------------------------------------------------------------------------

def cargar_partidos_candidatos(conn: sqlite3.Connection) -> dict:
    """
    Lee raw_camaras de cada resultado pendiente (sin partidos aún),
    normaliza nombres de candidatos e inserta en partidos y candidatos.
    Retorna conteos {partidos: {ins, omit}, candidatos: {ins, omit}}.
    """
    conteos = {
        "partidos":   {"insertados": 0, "omitidos": 0},
        "candidatos": {"insertados": 0, "omitidos": 0},
    }

    # Resultados que tienen raw_camaras pero aún no tienen partidos cargados
    pendientes = conn.execute("""
        SELECT r.id, r.municipio, r.sigla, r.raw_camaras
        FROM resultados r
        WHERE r.raw_camaras IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM partidos p WHERE p.resultado_id = r.id
          )
    """).fetchall()

    if not pendientes:
        log.info("  No hay resultados pendientes de procesar.")
        return conteos

    log.info(f"  Procesando {len(pendientes)} resultado(s) pendiente(s)…")

    for resultado_id, municipio, sigla, raw in pendientes:
        camaras = json.loads(raw)
        p_ins = p_omit = c_ins = c_omit = 0

        for camara in camaras:
            cam = camara.get("cam")

            for entrada in camara.get("partotabla", []):
                act    = entrada.get("act", {})
                codpar = act.get("codpar")

                cur = conn.execute("""
                    INSERT OR IGNORE INTO partidos
                        (resultado_id, cam, codpar, vot, pvot, carg, cargElectos)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    resultado_id, cam, codpar,
                    act.get("vot"), act.get("pvot"),
                    act.get("carg"), act.get("cargElectos"),
                ))

                if cur.rowcount > 0:
                    partido_id = cur.lastrowid
                    p_ins += 1
                else:
                    row = conn.execute(
                        "SELECT id FROM partidos WHERE resultado_id=? AND cam=? AND codpar=?",
                        (resultado_id, cam, codpar)
                    ).fetchone()
                    partido_id = row[0] if row else None
                    p_omit += 1

                if partido_id is None:
                    continue

                for cand in act.get("cantotabla", []):
                    nom  = normalizar_nombre(cand.get("nomcan"))
                    ape  = normalizar_nombre(cand.get("apecan"))
                    nom2 = normalizar_nombre(cand.get("nomcan2"))
                    ape2 = normalizar_nombre(cand.get("apecan2"))

                    cur2 = conn.execute("""
                        INSERT OR IGNORE INTO candidatos
                            (partido_id, amb, codcan, cedula,
                             nomcan, apecan, nomcan2, apecan2,
                             vot, pvot, carg, pref, empate)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        partido_id,
                        cand.get("amb"), cand.get("codcan"), cand.get("cedula"),
                        nom, ape, nom2, ape2,
                        cand.get("vot"),  cand.get("pvot"), cand.get("carg"),
                        cand.get("pref"), cand.get("empate"),
                    ))

                    if cur2.rowcount > 0:
                        c_ins += 1
                    else:
                        c_omit += 1

        conn.commit()
        log.info(
            f"  [{municipio}·{sigla}]  "
            f"partidos → ins:{p_ins} omit:{p_omit}  |  "
            f"candidatos → ins:{c_ins} omit:{c_omit}"
        )

        conteos["partidos"]["insertados"]   += p_ins
        conteos["partidos"]["omitidos"]     += p_omit
        conteos["candidatos"]["insertados"] += c_ins
        conteos["candidatos"]["omitidos"]   += c_omit

    return conteos


# ---------------------------------------------------------------------------
# Pipeline ETL
# ---------------------------------------------------------------------------

def run(db_path: Path, nom_url: str | None = None, nom_file: Path | None = None):
    if not db_path.exists():
        log.error(f"Base de datos no encontrada: {db_path}. Ejecuta scraper.py primero.")
        return

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")

    log.info("=== ETL — inicio ===\n")

    # 1. Catálogo de partidos
    try:
        cargar_catalogo_partidos(conn, nom_url=nom_url, nom_file=nom_file)
    except Exception as e:
        log.warning(f"  No se pudo cargar el catálogo de partidos: {e}")

    # 2. Partidos y candidatos normalizados
    log.info("")
    log.info("Cargando partidos y candidatos…")
    conteos = cargar_partidos_candidatos(conn)

    # 3. Resumen
    log.info("")
    log.info("=== Resumen ETL ===")
    for tabla, vals in conteos.items():
        log.info(f"  {tabla:<12} insertados={vals['insertados']}  omitidos={vals['omitidos']}")

    conn.close()
    log.info("=== ETL — completado ===")


# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="ETL: normaliza y carga partidos/candidatos en la base de datos"
    )
    parser.add_argument("--db", type=Path, default=DB_PATH,
                        help=f"Base de datos SQLite (default: {DB_PATH})")
    parser.add_argument("--nomenclator-url", default=None,
                        help="URL del nomenclator (default: API Registraduría)")
    parser.add_argument("--nomenclator-file", type=Path, default=None,
                        help="Archivo JSON local del nomenclator (fallback offline)")
    args = parser.parse_args()

    run(
        db_path=args.db,
        nom_url=args.nomenclator_url,
        nom_file=args.nomenclator_file,
    )


if __name__ == "__main__":
    main()
