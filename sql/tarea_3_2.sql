-- tarea_3_2.sql
-- Dominancia extrema
-- Candidatos que concentran >60% de los votos de su partido por municipio

SELECT
    r.municipio,
    r.sigla,
    COALESCE(pc.nombre, p.codpar)          AS partido,
    c.nomcan || ' ' || c.apecan            AS candidato,
    c.vot                                  AS votos_cand,
    p.vot                                  AS votos_partido,
    ROUND(
        CAST(c.vot AS FLOAT) /
        NULLIF(CAST(p.vot AS FLOAT), 0) * 100,
        1
    )                                      AS pct_partido
FROM candidatos c
JOIN partidos p        ON c.partido_id    = p.id
JOIN resultados r      ON p.resultado_id  = r.id
LEFT JOIN partidos_catalogo pc ON p.codpar = pc.codpar
WHERE CAST(p.vot AS INTEGER) > 0
  AND c.codcan != '0'
  AND CAST(c.vot AS FLOAT) /
      NULLIF(CAST(p.vot AS FLOAT), 0) > 0.60
ORDER BY pct_partido DESC;
