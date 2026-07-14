-- tarea_3_1.sql
-- Arrastre Verde CA→SE
-- Ratio votos_SE_Verde / votos_CA_Verde por municipio
-- Homologación: codpar_CA=5 → codpar_SE=57

SELECT
    r_se.municipio,
    p_se.vot            AS votos_SE,
    p_ca.vot            AS votos_CA,
    ROUND(
        CAST(p_se.vot AS FLOAT) / NULLIF(CAST(p_ca.vot AS FLOAT), 0),
        4
    )                   AS ratio
FROM partidos p_se
JOIN resultados r_se ON p_se.resultado_id = r_se.id
JOIN resultados r_ca ON r_ca.municipio = r_se.municipio
                     AND r_ca.sigla    = 'CA'
JOIN partidos p_ca   ON p_ca.resultado_id = r_ca.id
                     AND p_ca.codpar       = '5'
WHERE r_se.sigla   = 'SE'
  AND p_se.codpar  = '57'
ORDER BY r_se.municipio;
