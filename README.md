# MACIAS — Prueba Técnica UTL Senado 2026

## Candidato

| Campo | Valor |
|---|---|
| Nombre | Cristian Fabian Macias Acevedo |
| Email | cristianfma3108@gmail.com |
| Repositorio | https://github.com/cristian0831/Macias_prueba_etl_2026 |

## Instalación

```bash
pip install -r requirements.txt
```


## Pipeline de ejecución

```bash
# 1. Extrae resultados de la API y crea la base de datos
python3 scraper/scraper.py

# 2. Carga partidos y candidatos desde los JSON crudos
python3 db/etl.py

# 3. Inyecta datos frescos en el dashboard
python3 dashboard/export_data.py

# 4. Genera las visualizaciones
python3 viz/heatmap.py
python3 viz/scatter.py

# 5. Valida conteos y genera el manifest de evaluación
python3 outputs/generar_manifest.py
```

Abre `dashboard/index.html` directamente en Chrome o Firefox (no requiere servidor).

## API

**Base URL:** `https://resultadospreccongreso2026.registraduria.gov.co`

**Patrón de URL:**
```
GET /json/ACT/{sigla}/{scopeCode}.json
```

Ejemplo real:
```
GET /json/ACT/SE/0700001.json   ← Senado, Tunja
GET /json/ACT/CA/0700277.json   ← Cámara, Sogamoso
```

**Siglas disponibles:** `SE` (Senado), `CA` (Cámara de Representantes).

**Cabeceras HTTP necesarias:** ninguna especial. La API es pública y responde sin autenticación ni token. El scraper usa `requests.get(url, timeout=15)` sin cabeceras adicionales.

**Campos principales del JSON de respuesta** (extraídos de `totales.act`):

| Campo | Tipo | Descripción |
|---|---|---|
| `mdhm` | string | Timestamp del avance en formato `MMDDHHMM` |
| `elec` | string | Tipo de elección (`1`=Senado, `2`=Cámara) |
| `dept` | string | Código de departamento |
| `totales.act.centota` | string | Censo electoral total |
| `totales.act.votant` | string | Total de votantes |
| `totales.act.pvotant` | string | Porcentaje de participación |
| `totales.act.absten` | string | Votos en blanco + abstención |
| `totales.act.votnul` | string | Votos nulos |
| `totales.act.votblan` | string | Votos en blanco |
| `totales.act.votval` | string | Votos válidos |
| `totales.act.metota` | string | Total de mesas |
| `totales.act.mesesc` | string | Mesas escrutadas |
| `camaras[]` | array | Resultados por partido y candidatos (incluye `mapagan[]` con datos por zona geográfica) |

**Nomenclator — cómo obtenerlo:**
```
GET /json/nomenclator.json
```
Retorna todos los ámbitos geográficos con sus `scopeCode`. Se filtra por `elec=2` (Cámara) para extraer los códigos municipales; son idénticos para Senado y Cámara a nivel municipio.

```python
nom = requests.get(f"{BASE_URL}/json/nomenclator.json").json()
cam_ambitos = next(x for x in nom["amb"] if x["elec"] == 2)["ambitos"]
codigos = {a["n"]: a["c"] for a in cam_ambitos}  # {"TUNJA": "0700001", ...}
```

## Municipios en la BD

| Municipio | scopeCode | Mesas | Votantes CA | Censo CA |
|---|---|---|---|---|
| Tunja | 0700001 | 424 | 81.357 | 141.698 |
| Sogamoso | 0700277 | 301 | 56.396 | 101.449 |
| Duitama | 0700079 | 287 | 52.854 | 97.678 |
| Paipa | 0700181 | 95 | 18.137 | 30.521 |

Todos los municipios al **100% escrutado** (8/8 resultados OK).

## Hallazgos principales

**Partido líder Senado por municipio** — Pacto Histórico (codpar 92) domina en Tunja, Sogamoso y Duitama; Alianza Verde (codpar 57) lidera únicamente en Paipa.

**Arrastre Verde CA→SE** — Duitama muestra el arrastre más alto (ratio 1.29): el partido capturó un 29% más de votos en Senado que en Cámara. Paipa es el único municipio con arrastre negativo (ratio 0.58), indicando que la lista territorial de Cámara superó a la nacional de Senado.

| Municipio | Votos SE | Votos CA | Ratio |
|---|---|---|---|
| Duitama | 8.371 | 6.507 | **1.2865** |
| Sogamoso | 8.195 | 8.086 | 1.0135 |
| Tunja | 16.296 | 15.836 | 1.0290 |
| Paipa | 4.161 | 7.171 | **0.5803** |

**Top 5 atribución determinística SE** — candidatos con mayor proyección de votos al Senado en función de su desempeño en Cámara:

1. Hector David Chaparro Chaparro (Sogamoso) — A = 2890
2. Eduar Alexis Triana Rincon (Tunja) — A = 2373
3. Hector David Chaparro Chaparro (Tunja) — A = 2084
4. Oscar Leonardo Avila Romero (Tunja) — A = 1940
5. Hector David Chaparro Chaparro (Duitama) — A = 1806

**Candidato más votado por municipio en Cámara:** Yamit Hurtado Neira (AICO) en Paipa con 4.756 votos (27.4% del municipio); Hector Chaparro (Conservador) lidera en Sogamoso, Duitama; Ramiro Barragán (AICO) en Tunja.

**Scatter CA vs SE por zona geográfica:** correlación r = 1.000 sobre 492 zonas mapagan (pendiente OLS = 1.014), confirmando que los resultados de Cámara predicen casi perfectamente los de Senado a nivel de zona.

## Bonus implementados

**2.1 — Índices SQLite con justificación** (`db/schema.sql`):

- `idx_partidos_resultado` en `partidos(resultado_id)`: acelera los JOINs `partidos→resultados` presentes en las tres queries analíticas (tarea 3.1, 3.2, 3.3). Sin él, SQLite haría full-scan de la tabla `partidos` en cada JOIN.
- `idx_partidos_codpar` en `partidos(codpar)`: acelera el filtro `codpar = '5'/'57'` en tarea 3.1 y el JOIN de homologación por código en tarea 3.3.
- `idx_candidatos_partido` en `candidatos(partido_id)`: acelera el JOIN `candidatos→partidos` en tarea 3.2 (dominancia extrema) y 3.3 (atribución), que recorren todos los candidatos de cada partido por municipio.
