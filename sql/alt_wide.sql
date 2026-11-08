-- Conception alternative (Partie I, décision D15) : une ligne par station et par jour,
-- une colonne par élément. Chargée à partir de observations pour comparer les deux
-- conceptions sur au moins deux requêtes (temps, taille). Pas utilisée par les services.

CREATE TABLE observations_wide (
    station  text NOT NULL REFERENCES stations (id),
    date     date NOT NULL,
    tmax     integer, tmax_mflag text, tmax_qflag text, tmax_sflag text,
    tmin     integer, tmin_mflag text, tmin_qflag text, tmin_sflag text,
    prcp     integer, prcp_mflag text, prcp_qflag text, prcp_sflag text,
    PRIMARY KEY (station, date)
);

INSERT INTO observations_wide
SELECT station, date,
       max(value) FILTER (WHERE element = 'TMAX'), max(mflag) FILTER (WHERE element = 'TMAX'),
       max(qflag) FILTER (WHERE element = 'TMAX'), max(sflag) FILTER (WHERE element = 'TMAX'),
       max(value) FILTER (WHERE element = 'TMIN'), max(mflag) FILTER (WHERE element = 'TMIN'),
       max(qflag) FILTER (WHERE element = 'TMIN'), max(sflag) FILTER (WHERE element = 'TMIN'),
       max(value) FILTER (WHERE element = 'PRCP'), max(mflag) FILTER (WHERE element = 'PRCP'),
       max(qflag) FILTER (WHERE element = 'PRCP'), max(sflag) FILTER (WHERE element = 'PRCP')
FROM observations
GROUP BY station, date;
