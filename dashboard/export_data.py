# export_data.py
# Extrae datos del dashboard desde la base de datos.
# Genera data.json e inyecta los datos en index.html (autocontenido, sin servidor).
#
# Uso: python3 export_data.py [--db puestos_2026.db] [--html index.html]

import argparse
import json
import sqlite3
from collections import defaultdict
from pathlib import Path

DB_PATH   = Path(__file__).parent.parent / "db" / "puestos_2026.db"
HTML_PATH = Path(__file__).parent / "index.html"
JSON_PATH = Path(__file__).parent / "data.json"

PARTY_NAMES = {
    "2":  "Partido Conservador",
    "5":  "Alianza Verde",
    "10": "Centro Democrático",
    "57": "Alianza Verde",
    "87": "Pacto Histórico",
    "92": "Pacto Histórico",
}

# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

def votos_ca_totales(conn: sqlite3.Connection) -> dict:
    """Votantes y censo CA por municipio."""
    filas = conn.execute("""
        SELECT municipio,
               CAST(votant   AS INTEGER) AS votant,
               CAST(centota  AS INTEGER) AS censo
        FROM resultados
        WHERE sigla = 'CA'
        ORDER BY municipio
    """).fetchall()
    return {f["municipio"]: {"votant": f["votant"], "censo": f["censo"]} for f in filas}


def lider_se(conn: sqlite3.Connection) -> dict:
    """Partido líder Senado por municipio."""
    filas = conn.execute("""
        SELECT r.municipio, p.codpar, p.vot
        FROM partidos p
        JOIN resultados r ON p.resultado_id = r.id
        WHERE r.sigla = 'SE' AND p.cam = '0'
        ORDER BY r.municipio, CAST(p.vot AS INTEGER) DESC
    """).fetchall()

    lideres = {}
    for f in filas:
        mun = f["municipio"]
        if mun not in lideres:
            codpar = f["codpar"]
            lideres[mun] = {
                "codpar": codpar,
                "nombre": PARTY_NAMES.get(codpar, f"Partido {codpar}"),
                "vot":    int(f["vot"]),
            }
    return lideres


def arrastre_verde(conn: sqlite3.Connection) -> list:
    """Ratio SE/CA Alianza Verde por municipio (codpar CA=5, SE=57)."""
    filas = conn.execute(
        (Path(__file__).parent.parent / "sql" / "tarea_3_1.sql").read_text()
    ).fetchall()
    return [
        {
            "municipio": f["municipio"],
            "votos_SE":  int(f["votos_SE"]),
            "votos_CA":  int(f["votos_CA"]),
            "ratio":     round(float(f["ratio"]), 4),
        }
        for f in filas
    ]


def top10_ca(conn: sqlite3.Connection) -> dict:
    """Top 10 candidatos CA por municipio ordenados por votos."""
    filas = conn.execute("""
        SELECT
            r.municipio,
            c.nomcan || ' ' || c.apecan        AS candidato,
            COALESCE(pc.nombre, p.codpar)      AS partido,
            CAST(c.vot AS INTEGER)             AS vot,
            c.pvot
        FROM candidatos c
        JOIN partidos p        ON c.partido_id   = p.id
        JOIN resultados r      ON p.resultado_id = r.id
        LEFT JOIN partidos_catalogo pc ON p.codpar = pc.codpar
        WHERE r.sigla   = 'CA'
          AND c.codcan != '0'
          AND CAST(c.vot AS INTEGER) > 0
        ORDER BY r.municipio, CAST(c.vot AS INTEGER) DESC
    """).fetchall()

    resultado = defaultdict(list)
    for f in filas:
        mun = f["municipio"]
        if len(resultado[mun]) < 10:
            resultado[mun].append({
                "candidato": f["candidato"],
                "partido":   f["partido"],
                "vot":       f["vot"],
                "pvot":      f["pvot"],
            })
    return dict(resultado)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def exportar(db_path: Path, html_path: Path, json_path: Path):
    if not db_path.exists():
        raise FileNotFoundError(f"Base de datos no encontrada: {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    data = {
        "votos_ca":   votos_ca_totales(conn),
        "lider_se":   lider_se(conn),
        "arrastre":   arrastre_verde(conn),
        "top10_ca":   top10_ca(conn),
    }

    conn.close()

    # 1. Escribir data.json
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    print(f"data.json generado: {json_path}")

    # 2. Inyectar en index.html (reemplaza el bloque entre los marcadores)
    if not html_path.exists():
        print(f"  AVISO: {html_path} no encontrado — solo se generó data.json")
        return

    html = html_path.read_text(encoding="utf-8")
    data_js = json.dumps(data, ensure_ascii=False, indent=2)

    inicio = "// __EXPORT_DATA_START__"
    fin    = "// __EXPORT_DATA_END__"

    if inicio not in html or fin not in html:
        print(f"  AVISO: marcadores no encontrados en {html_path} — index.html no actualizado")
        return

    bloque = f"{inicio}\nconst DATA = {data_js};\n{fin}"
    start_idx = html.index(inicio)
    end_idx   = html.index(fin) + len(fin)
    html = html[:start_idx] + bloque + html[end_idx:]

    html_path.write_text(html, encoding="utf-8")
    print(f"index.html actualizado con datos frescos: {html_path}")


# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Exporta datos del dashboard a data.json e index.html"
    )
    parser.add_argument("--db",   type=Path, default=DB_PATH,
                        help=f"Base de datos SQLite (default: {DB_PATH})")
    parser.add_argument("--html", type=Path, default=HTML_PATH,
                        help=f"Archivo HTML del dashboard (default: {HTML_PATH})")
    parser.add_argument("--json", type=Path, default=JSON_PATH,
                        help=f"Archivo JSON de salida (default: {JSON_PATH})")
    args = parser.parse_args()

    exportar(args.db, args.html, args.json)
