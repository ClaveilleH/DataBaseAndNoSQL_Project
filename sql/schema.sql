-- WeatherScope : schéma commun (décisions D14 et D15 dans docs/decisions.md).
-- Le même fichier sert en local (PostgreSQL) et en distribué (coordinateur Citus) ;
-- la répartition Citus est appliquée ensuite par sql/distribute.sql.
-- Toutes les valeurs de mesure sont des entiers bruts NOAA : dixièmes de °C ou de mm.

-- Métadonnées des 774 stations retenues (data/stations_selected.csv).
-- Citus : table de référence, copiée sur chaque worker.
CREATE TABLE stations (
    id          text PRIMARY KEY,                -- identifiant NOAA, ex. GM000001474
    zone        text NOT NULL,                   -- GM ou SP (préfixe de l'identifiant)
    name        text NOT NULL,
    lat         numeric(7, 4) NOT NULL,
    lon         numeric(8, 4) NOT NULL,
    elevation   numeric(6, 1),                   -- NULL si inconnue (-999.9 chez NOAA)
    wmo_id      text,
    -- Maille de 0,5° contenant la station : sert à F4 (densité de stations par région).
    cell_lat    numeric(5, 1) GENERATED ALWAYS AS (floor(lat * 2) / 2) STORED,
    cell_lon    numeric(5, 1) GENERATED ALWAYS AS (floor(lon * 2) / 2) STORED
);

-- Lots importés (chargement initial ou mise à jour F5), avec leur provenance.
-- L'identifiant est attribué par le code d'import (max + 1), pas par une séquence,
-- pour rester simple avec Citus. Citus : table de référence.
CREATE TABLE batches (
    id            integer PRIMARY KEY,
    kind          text NOT NULL CHECK (kind IN ('initial', 'update')),
    retrieved_at  timestamptz NOT NULL,          -- date de récupération des fichiers NOAA
    loaded_at     timestamptz NOT NULL DEFAULT now(),
    files         jsonb NOT NULL,                -- [{url, path, size, sha256}, ...]
    counts        jsonb                          -- lignes lues, insérées, modifiées, inchangées
);

-- Une ligne par mesure NOAA. Identité = (station, élément, date).
-- Citus : distribuée par station.
CREATE TABLE observations (
    station   text NOT NULL REFERENCES stations (id),
    element   text NOT NULL CHECK (element IN ('TMAX', 'TMIN', 'PRCP')),
    date      date NOT NULL,
    value     integer NOT NULL,                  -- dixièmes de °C (TMAX, TMIN) ou de mm (PRCP)
    mflag     text,                              -- NULL si vide dans le fichier NOAA
    qflag     text,                              -- non NULL = observation invalide (exclue des calculs)
    sflag     text,
    obs_time  text,                              -- HHMM, souvent vide
    batch_id  integer NOT NULL REFERENCES batches (id),
    PRIMARY KEY (station, element, date)
);

-- Anciennes versions écrasées par F5. Citus : distribuée par station, colocalisée.
CREATE TABLE observations_history (
    station      text NOT NULL,
    element      text NOT NULL,
    date         date NOT NULL,
    value        integer NOT NULL,
    mflag        text,
    qflag        text,
    sflag        text,
    obs_time     text,
    batch_id     integer NOT NULL,               -- lot qui avait écrit cette version
    replaced_by  integer NOT NULL REFERENCES batches (id),  -- lot qui l'a remplacée
    replaced_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (station, element, date, replaced_by)
);

-- Table de chargement de F5 : le lot y est copié (COPY), comparé, puis vidé.
-- UNLOGGED : contenu jetable, chargement plus rapide. Citus : distribuée par station, colocalisée.
CREATE UNLOGGED TABLE observations_staging (
    station   text NOT NULL,
    element   text NOT NULL,
    date      date NOT NULL,
    value     integer NOT NULL,
    mflag     text,
    qflag     text,
    sflag     text,
    obs_time  text
);

-- Agrégats mensuels par station et élément, recalculés par F5 pour les mois touchés.
-- Sommes et comptes entiers : F3 en déduit des moyennes identiques en local et en distribué.
-- Citus : distribuée par station, colocalisée.
CREATE TABLE monthly_stats (
    station     text NOT NULL,
    element     text NOT NULL,
    year        smallint NOT NULL,
    month       smallint NOT NULL CHECK (month BETWEEN 1 AND 12),
    n_obs       integer NOT NULL,                -- lignes présentes, valides ou non
    n_valid     integer NOT NULL,                -- valides : qflag vide et mflag différent de P (D20)
    n_flagged   integer NOT NULL,                -- qflag non vide (exclues)
    n_presumed  integer NOT NULL,                -- PRCP mflag P (manquante présumée nulle) : traitées comme manquantes
    n_trace     integer NOT NULL,                -- PRCP mflag T (trace) : valides, 0 mm, comptées à part
    sum_value   bigint,                          -- somme des valeurs valides (NULL si n_valid = 0)
    min_value   integer,
    max_value   integer,
    PRIMARY KEY (station, element, year, month)
);

-- Vue en unités physiques, pour l'affichage uniquement (les calculs restent sur les entiers).
CREATE VIEW observations_si AS
SELECT station, element, date,
       (value / 10.0)::numeric(6, 1) AS value_si,  -- °C ou mm
       CASE WHEN element = 'PRCP' THEN 'mm' ELSE '°C' END AS unit,
       mflag, qflag, sflag, obs_time, batch_id
FROM observations;
