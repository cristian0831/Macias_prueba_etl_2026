# scatter.py
# Genera viz/scatter_ca_se.png
# Cada punto = una zona geográfica (mapagan), color por municipio
# Línea de regresión OLS, r de Pearson anotado
# Imprime: r=X.XXX | pendiente=X.XXX | n_mesas=NNN
# Uso: python3 scatter.py [--db registraduria.db]

import argparse
import json
import sqlite3
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy import stats

DB_PATH  = Path(__file__).parent.parent / "db" / "puestos_2026.db"
OUT_DIR  = Path(__file__).parent
OUT_FILE = OUT_DIR / "scatter_ca_se.png"

MUNICIPIOS = ["TUNJA", "SOGAMOSO", "DUITAMA", "PAIPA"]

MUN_COLORS = {
    "TUNJA":    "#63b3ed",
    "SOGAMOSO": "#68d391",
    "DUITAMA":  "#f6ad55",
    "PAIPA":    "#fc8181",
}


def extraer_mapagan(db_path: Path) -> dict:
    """
    Extrae votantes por zona geográfica (mapagan) de raw_camaras.
    Usa cam='1' para CA y cam='0' para SE (circunscripciones principales).
    Retorna {(municipio, amb): {sigla: votant}}
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        "SELECT municipio, sigla, raw_camaras FROM resultados"
    ).fetchall()
    conn.close()

    # Cámaras objetivo por sigla
    cam_target = {"CA": "1", "SE": "0"}

    zona_data: dict = defaultdict(dict)

    for r in rows:
        sigla   = r["sigla"]
        target  = cam_target.get(sigla)
        camaras = json.loads(r["raw_camaras"])

        for camara in camaras:
            if str(camara.get("cam")) != target:
                continue
            for zona in camara.get("mapagan", []):
                amb    = zona.get("amb")
                votant = zona.get("votant", "0") or "0"
                if amb:
                    key = (r["municipio"], amb)
                    zona_data[key][sigla] = int(votant)

    return zona_data


def main(db_path: Path):
    OUT_DIR.mkdir(exist_ok=True)

    zona_data = extraer_mapagan(db_path)

    # Filtrar zonas con datos CA y SE
    x_vals, y_vals, colors, municipios_pts = [], [], [], []

    for (municipio, amb), siglas in zona_data.items():
        if "CA" in siglas and "SE" in siglas and siglas["CA"] > 0 and siglas["SE"] > 0:
            x_vals.append(siglas["CA"])
            y_vals.append(siglas["SE"])
            colors.append(MUN_COLORS.get(municipio, "#888"))
            municipios_pts.append(municipio)

    x = np.array(x_vals)
    y = np.array(y_vals)
    n = len(x)

    # Regresión OLS
    slope, intercept, r_value, p_value, std_err = stats.linregress(x, y)

    # Output requerido por la prueba
    print(f"r={r_value:.3f} | pendiente={slope:.3f} | n_mesas={n}")

    # Línea de regresión
    x_line = np.linspace(x.min(), x.max(), 300)
    y_line  = slope * x_line + intercept

    # ----------------------------------------------------------------
    # Plot
    # ----------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(11, 8))
    fig.patch.set_facecolor("#0f1117")
    ax.set_facecolor("#1a1f2e")

    # Scatter por municipio (para leyenda individual)
    for mun in MUNICIPIOS:
        idx = [i for i, m in enumerate(municipios_pts) if m == mun]
        if not idx:
            continue
        ax.scatter(
            [x_vals[i] for i in idx],
            [y_vals[i] for i in idx],
            c=MUN_COLORS[mun],
            label=mun.title(),
            alpha=0.70,
            s=55,
            edgecolors="none",
            zorder=3,
        )

    # Línea OLS
    ax.plot(x_line, y_line,
            color="#f6e05e", linewidth=2, linestyle="--",
            label=f"OLS  y = {slope:.3f}x + {intercept:.0f}",
            zorder=4)

    # Anotación r de Pearson
    ax.text(
        0.97, 0.05,
        f"r = {r_value:.3f}\npendiente = {slope:.3f}\nn = {n}",
        transform=ax.transAxes,
        ha="right", va="bottom",
        fontsize=11, color="#f7fafc",
        bbox=dict(boxstyle="round,pad=0.5", facecolor="#2d3748",
                  edgecolor="#4a5568", alpha=0.9),
        zorder=5,
    )

    # Ejes
    ax.set_xlabel("Votantes CA por zona geográfica", fontsize=12, color="#90a0b7")
    ax.set_ylabel("Votantes SE por zona geográfica", fontsize=12, color="#90a0b7")
    ax.tick_params(colors="#90a0b7")
    ax.xaxis.label.set_color("#90a0b7")
    for spine in ax.spines.values():
        spine.set_edgecolor("#2d3748")
    ax.grid(color="#2d3748", linestyle="--", linewidth=0.6, alpha=0.7)
    ax.tick_params(axis="both", colors="#718096")

    # Título
    ax.set_title(
        "Participación CA vs SE por zona geográfica\nBoyacá · Congreso 2026",
        fontsize=13, fontweight="bold", color="#f7fafc", pad=14
    )

    # Leyenda
    legend = ax.legend(
        fontsize=10, facecolor="#1a1f2e",
        edgecolor="#2d3748", labelcolor="#e2e8f0",
        loc="upper left"
    )

    plt.tight_layout()
    plt.savefig(OUT_FILE, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    print(f"Scatter guardado en: {OUT_FILE}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Scatter CA vs SE votantes por zona geográfica"
    )
    parser.add_argument("--db", type=Path, default=DB_PATH,
                        help=f"Base de datos SQLite (default: {DB_PATH})")
    args = parser.parse_args()
    main(args.db)
