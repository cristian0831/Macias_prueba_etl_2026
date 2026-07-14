# generar_manifest.py
# Valida conteos de mesas y filas extraídas, y genera manifest.json
# Uso: python3 generar_manifest.py [--db registraduria.db] [--out manifest.json]

import argparse
import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

DB_PATH  = Path(__file__).parent.parent / "db" / "puestos_2026.db"
OUT_PATH = Path(__file__).parent / "evaluation_manifest.json"


# ---------------------------------------------------------------------------
# Validaciones
# ---------------------------------------------------------------------------

def validar_mesas(metota: str, mesesc: str) -> dict:
    """
    Compara mesas totales vs escrutadas.
    Retorna {'ok': bool, 'metota': int, 'mesesc': int, 'faltantes': int}
    """
    total = int(metota or 0)
    esc   = int(mesesc or 0)
    return {
        "ok":        esc >= total,
        "metota":    total,
        "mesesc":    esc,
        "faltantes": max(0, total - esc),
    }


def contar_filas(conn: sqlite3.Connection, resultado_id: int) -> dict:
    """Cuenta filas relacionadas en partidos, candidatos e histórico."""
    partidos = conn.execute(
        "SELECT COUNT(*) FROM partidos WHERE resultado_id = ?", (resultado_id,)
    ).fetchone()[0]

    candidatos = conn.execute(
        """SELECT COUNT(*) FROM candidatos c
           JOIN partidos p ON c.partido_id = p.id
           WHERE p.resultado_id = ?""", (resultado_id,)
    ).fetchone()[0]

    historico = conn.execute(
        "SELECT COUNT(*) FROM historico WHERE resultado_id = ?", (resultado_id,)
    ).fetchone()[0]

    return {
        "partidos":   partidos,
        "candidatos": candidatos,
        "historico":  historico,
    }


# ---------------------------------------------------------------------------
# Reto 3 — Queries analíticas (leídas desde archivos .sql)
# ---------------------------------------------------------------------------

SQL_DIR = Path(__file__).parent.parent / "sql"

def ejecutar_sql(conn: sqlite3.Connection, archivo: str) -> list:
    """Lee un archivo .sql y ejecuta su contenido. Retorna lista de dicts."""
    sql = (SQL_DIR / archivo).read_text()
    filas = conn.execute(sql).fetchall()
    return [dict(f) for f in filas]


# ---------------------------------------------------------------------------
# Generación del manifest
# ---------------------------------------------------------------------------

def generar(db_path: Path, out_path: Path) -> dict:
    if not db_path.exists():
        log.error(f"Base de datos no encontrada: {db_path}")
        raise FileNotFoundError(db_path)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    resultados = conn.execute(
        "SELECT * FROM resultados ORDER BY municipio, sigla"
    ).fetchall()

    if not resultados:
        log.warning("La base de datos no tiene resultados. Ejecuta scraper.py primero.")

    entradas     = []
    errores      = 0
    advertencias = 0

    for r in resultados:
        mesas = validar_mesas(r["metota"], r["mesesc"])
        filas = contar_filas(conn, r["id"])

        # Determinar estado
        if not mesas["ok"]:
            estado = "INCOMPLETO"
            advertencias += 1
        elif filas["partidos"] == 0:
            estado = "SIN_PARTIDOS"
            errores += 1
        else:
            estado = "OK"

        entrada = {
            "municipio":  r["municipio"],
            "scope_code": r["scope_code"],
            "sigla":      r["sigla"],
            "mdhm":       r["mdhm"],
            "scraped_at": r["scraped_at"],
            "mesas":      mesas,
            "filas":      filas,
            "estado":     estado,
        }
        entradas.append(entrada)

        # Log por fila
        icono = "✓" if estado == "OK" else ("⚠" if estado == "INCOMPLETO" else "✗")
        log.info(
            f"  {icono} {r['municipio']:<10} · {r['sigla']}  "
            f"mesas={mesas['mesesc']}/{mesas['metota']} "
            f"({'+' if mesas['ok'] else str(mesas['faltantes'])+' falt.'})  "
            f"partidos={filas['partidos']}  candidatos={filas['candidatos']}  "
            f"historico={filas['historico']}  [{estado}]"
        )

    # Reto 3 — queries analíticas (desde archivos .sql)
    arrastre_verde      = ejecutar_sql(conn, "tarea_3_1.sql")
    dominancia_extrema  = ejecutar_sql(conn, "tarea_3_2.sql")
    atribucion_top5     = ejecutar_sql(conn, "tarea_3_3.sql")

    conn.close()

    # Resumen global
    resumen = {
        "total_resultados": len(entradas),
        "ok":               sum(1 for e in entradas if e["estado"] == "OK"),
        "incompletos":      advertencias,
        "con_error":        errores,
        "total_partidos":   sum(e["filas"]["partidos"]   for e in entradas),
        "total_candidatos": sum(e["filas"]["candidatos"] for e in entradas),
        "total_historico":  sum(e["filas"]["historico"]  for e in entradas),
    }

    analisis = {
        "arrastre_verde_ca_se":      arrastre_verde,
        "dominancia_extrema":        dominancia_extrema,
        "atribucion_deterministica": atribucion_top5,
    }

    manifest = {
        "meta": {
            "autor":       "Cristian Fabian Macias Acevedo",
            "email":       "cristianfma3108@gmail.com",
            "repositorio": "https://github.com/cristian0831",
        },
        "generado_en": datetime.now(timezone.utc).isoformat(),
        "db":          str(db_path),
        "resumen":     resumen,
        "analisis":    analisis,
        "resultados":  entradas,
    }

    # Escribir manifest.json
    out_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))

    log.info("")
    log.info(f"{'='*55}")
    log.info(f"  Resultados:  {resumen['total_resultados']}")
    log.info(f"  OK:          {resumen['ok']}")
    log.info(f"  Incompletos: {resumen['incompletos']}")
    log.info(f"  Con error:   {resumen['con_error']}")
    log.info(f"  Partidos:    {resumen['total_partidos']}")
    log.info(f"  Candidatos:  {resumen['total_candidatos']}")
    log.info(f"  Histórico:   {resumen['total_historico']}")
    log.info(f"{'='*55}")
    log.info("  Reto 3.1 — Arrastre Verde (CA codpar=5 → SE codpar=57):")
    if arrastre_verde:
        for row in arrastre_verde:
            log.info(f"    {row['municipio']:<10}  CA={row['votos_CA']}  SE={row['votos_SE']}  ratio={row['ratio']}")
    else:
        log.info("    Sin datos (partido Verde no encontrado en ambas cámaras)")
    log.info(f"{'='*55}")
    log.info("  Reto 3.2 — Dominancia extrema (candidato >60% del partido):")
    if dominancia_extrema:
        for row in dominancia_extrema:
            log.info(f"    {row['municipio']:<10} · {row['sigla']}  {row['candidato']}  {row['pct_partido']}%")
    else:
        log.info("    Ningún candidato supera el 60%")
    log.info(f"{'='*55}")
    log.info("  Reto 3.3 — Top 5 atribución determinística SE:")
    for i, row in enumerate(atribucion_top5, 1):
        log.info(f"    {i}. {row['candidato']}  ({row['municipio']})  A={row['atribucion_se']}")
    log.info(f"{'='*55}")
    log.info(f"  Manifest guardado en: {out_path}")

    return manifest


# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Genera manifest.json con validación de conteos"
    )
    parser.add_argument("--db",  type=Path, default=DB_PATH,
                        help=f"Base de datos SQLite (default: {DB_PATH})")
    parser.add_argument("--out", type=Path, default=OUT_PATH,
                        help="Archivo de salida (default: outputs/evaluation_manifest.json)")
    args = parser.parse_args()

    generar(args.db, args.out)


if __name__ == "__main__":
    main()
