-- tarea_3_3.sql
-- Atribución determinística — Top 5 candidatos por atribución SE consolidada
-- Fórmula: A_ij = (votos_cand_CA / votos_partido_CA) × votos_SE_partido

SELECT
    c.nomcan || ' ' || c.apecan            AS candidato,
    r_ca.municipio,
    COALESCE(pc.nombre, p_ca.codpar)       AS partido,
    ROUND(
        CAST(c.vot AS FLOAT) /
        NULLIF(CAST(p_ca.vot AS FLOAT), 0)
        * CAST(p_se.vot AS FLOAT),
        0
    )                                      AS atribucion_se
FROM candidatos c
JOIN partidos p_ca    ON c.partido_id      = p_ca.id
JOIN resultados r_ca  ON p_ca.resultado_id = r_ca.id
                      AND r_ca.sigla        = 'CA'
JOIN resultados r_se  ON r_se.municipio    = r_ca.municipio
                      AND r_se.sigla         = 'SE'
JOIN partidos p_se    ON p_se.resultado_id = r_se.id
                      AND p_se.codpar        = p_ca.codpar
LEFT JOIN partidos_catalogo pc ON p_ca.codpar = pc.codpar
WHERE CAST(p_ca.vot AS INTEGER) > 0
  AND c.codcan != '0'
ORDER BY atribucion_se DESC
LIMIT 5;
