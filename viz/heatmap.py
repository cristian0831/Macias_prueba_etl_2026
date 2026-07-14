# heatmap.py
# Genera viz/heatmap_municipios.png
# Filas = top 8 candidatos CA, columnas = 4 municipios, valores = % del total por municipio
# Uso: python3 heatmap.py [--db registraduria.db]

import argparse
import sqlite3
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

DB_PATH  = Path(__file__).parent.parent / "db" / "puestos_2026.db"
OUT_DIR  = Path(__file__).parent
OUT_FILE = OUT_DIR / "heatmap_municipios.png"

MUNICIPIOS = ["TUNJA", "SOGAMOSO", "DUITAMA", "PAIPA"]

PARTY_COLORS = {
    "Partido Conservador Colombiano": "#E07B00",
    "2":  "#E07B00",
    "5":  "#007C34",
    "10": "#1E477D",
    "57": "#007C34",
    "87": "#7B2D8B",
    "92": "#7B2D8B",
}

def get_party_color(partido: str) -> str:
    if partido in PARTY_COLORS:
        return PARTY_COLORS[partido]
    p = partido.lower()
    if "conserv" in p:      return "#E07B00"
    if "verde"  in p or "alianza" in p: return "#007C34"
    if "pacto"  in p:       return "#7B2D8B"
    if "centro" in p:       return "#1E477D"
    return "#6b7280"

def short_name(name: str) -> str:
    parts = name.strip().split()
    if len(parts) >= 2:
        return f"{parts[0].title()} {parts[-1].title()}"
    return name.title()


def main(db_path: Path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Votos por candidato y municipio (CA, excluyendo "solo por lista")
    rows = conn.execute("""
        SELECT
            r.municipio,
            c.nomcan || ' ' || c.apecan  AS candidato,
            p.codpar,
            CAST(c.vot AS INTEGER)       AS vot
        FROM candidatos c
        JOIN partidos  p ON c.partido_id   = p.id
        JOIN resultados r ON p.resultado_id = r.id
        WHERE r.sigla    = 'CA'
          AND c.codcan  != '0'
          AND CAST(c.vot AS INTEGER) > 0
    """).fetchall()

    # {candidato: {municipio: vot}}
    data = defaultdict(lambda: defaultdict(int))
    partido_map = {}
    for row in rows:
        cand = row["candidato"]
        data[cand][row["municipio"]] = row["vot"]
        partido_map[cand] = row["codpar"]

    # Total votantes CA por municipio (denominador para %)
    totales = {}
    for mun in MUNICIPIOS:
        r = conn.execute(
            "SELECT CAST(votant AS INTEGER) AS v FROM resultados WHERE municipio=? AND sigla='CA'",
            (mun,)
        ).fetchone()
        totales[mun] = r["v"] if r else 1

    conn.close()

    # Top 8 por suma de votos en todos los municipios
    totales_cand = {c: sum(v.values()) for c, v in data.items()}
    top8 = sorted(totales_cand, key=lambda x: totales_cand[x], reverse=True)[:8]

    # Matriz 8×4 con porcentajes
    matrix = np.zeros((8, 4))
    for i, cand in enumerate(top8):
        for j, mun in enumerate(MUNICIPIOS):
            vot = data[cand].get(mun, 0)
            matrix[i][j] = round(vot / totales[mun] * 100, 2)

    # Etiquetas de filas (nombre corto)
    row_labels = [short_name(c) for c in top8]
    col_labels  = [m.title() for m in MUNICIPIOS]

    # Color de fila según partido
    row_colors = [get_party_color(partido_map.get(c, "")) for c in top8]

    # ----------------------------------------------------------------
    # Plot
    # ----------------------------------------------------------------
    OUT_DIR.mkdir(exist_ok=True)

    fig, ax = plt.subplots(figsize=(11, 7))
    fig.patch.set_facecolor("#0f1117")
    ax.set_facecolor("#0f1117")

    cmap = plt.cm.YlOrRd
    im = ax.imshow(matrix, cmap=cmap, aspect="auto", vmin=0, vmax=matrix.max())

    # Anotaciones en cada celda
    for i in range(8):
        for j in range(4):
            val = matrix[i][j]
            text_color = "black" if val > matrix.max() * 0.5 else "white"
            ax.text(j, i, f"{val:.2f}%",
                    ha="center", va="center",
                    fontsize=10, fontweight="bold", color=text_color)

    # Ejes
    ax.set_xticks(range(4))
    ax.set_xticklabels(col_labels, fontsize=12, color="#e2e8f0")
    ax.set_yticks(range(8))
    ax.set_yticklabels(row_labels, fontsize=11, color="#e2e8f0")

    # Color de etiqueta de fila según partido
    for tick, color in zip(ax.get_yticklabels(), row_colors):
        tick.set_color(color)

    # Colorbar
    cbar = fig.colorbar(im, ax=ax, pad=0.02)
    cbar.set_label("% del total de votantes CA", color="#90a0b7", fontsize=10)
    cbar.ax.yaxis.set_tick_params(color="#90a0b7")
    plt.setp(cbar.ax.yaxis.get_ticklabels(), color="#90a0b7")
    cbar.outline.set_edgecolor("#2d3748")

    # Títulos
    ax.set_title(
        "Top 8 candidatos Cámara — % de votos por municipio\nBoyacá · Congreso 2026",
        fontsize=13, fontweight="bold", color="#f7fafc", pad=14
    )

    # Leyenda partidos
    legend_items = [
        ("Alianza Verde",      "#007C34"),
        ("Pacto Histórico",    "#7B2D8B"),
        ("Centro Democrático", "#1E477D"),
        ("Conservador",        "#E07B00"),
        ("Otro",               "#6b7280"),
    ]
    from matplotlib.patches import Patch
    handles = [Patch(facecolor=c, label=l) for l, c in legend_items]
    ax.legend(handles=handles, loc="lower right", bbox_to_anchor=(1.32, 0),
              fontsize=9, facecolor="#1a1f2e", edgecolor="#2d3748",
              labelcolor="#e2e8f0", title="Partido", title_fontsize=9)

    # Grid entre celdas
    ax.set_xticks(np.arange(-0.5, 4, 1), minor=True)
    ax.set_yticks(np.arange(-0.5, 8, 1), minor=True)
    ax.grid(which="minor", color="#0f1117", linewidth=2)
    ax.tick_params(which="minor", bottom=False, left=False)

    plt.tight_layout()
    plt.savefig(OUT_FILE, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    print(f"Heatmap guardado en: {OUT_FILE}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Heatmap top 8 candidatos CA × 4 municipios")
    parser.add_argument("--db", type=Path, default=DB_PATH,
                        help=f"Base de datos SQLite (default: {DB_PATH})")
    args = parser.parse_args()
    main(args.db)
