# WeatherScope — contexte commun

Projet M2 SLCD « Big Data and NoSQL » (sujet : `docs/Projet1_WeatherScope_FR.pdf`, la version anglaise fait foi).
Observatoire météo historique sur NOAA GHCN-Daily : services F1–F5, version locale puis distribuée, expériences E1–E4.
Équipe : Hugo (données), Stevenson (services), Mamadou (distribution et mesures). Rendu le 8 novembre 2026, soutenance le 10.

Toutes les décisions et leurs raisons : `docs/decisions.md`.

## Périmètre (figé)

- Zones = pays, d'après le préfixe de l'identifiant NOAA : `GM` (Allemagne) et `SP` (Espagne).
- Stations retenues : `data/stations_selected.csv` (774 stations, produit par `ingest/select_stations.py`).
- Période d'étude : 2015-01-01 → 2024-12-31.
- Période de référence (normales F3) : 1991-01-01 → 2020-12-31. Chargé en base : 1991-01-01 → 2024-12-31 (21,5 M observations, D16).
- Éléments : `TMAX`, `TMIN` (°C), `PRCP` (mm). Dans les fichiers NOAA, valeurs en dixièmes.

## Pile

- Local (Partie I) : PostgreSQL 17.2 sous Docker, `deploy/local/compose.yml`, port **5440** (5432 et 5433 sont pris sur le poste d'Hugo).
- Distribué (Partie II) : Citus 13.0 (image `citusdata/citus:13.0`, PostgreSQL 17.2), un coordinateur + des workers, dans `deploy/citus/`.
- Python 3.12 géré par uv. Toujours `uv run ...`, jamais pip.
- Connexion : `weatherscope.db.connect()` (psycopg 3), qui lit `DATABASE_URL`
  (défaut `postgresql://weatherscope:weatherscope@localhost:5440/weatherscope`).
  Le même code et le même SQL tournent en local et en distribué : seul `DATABASE_URL` change (pointer sur le coordinateur).

## Dossiers et propriétaires

Ne modifier que son dossier. Un besoin dans le dossier d'un autre = lui demander.
Toute modification de ce fichier, de `weatherscope/db.py` ou du schéma SQL (le contrat) passe par une PR relue par les deux autres.

| Dossier | Propriétaire | Contenu |
| --- | --- | --- |
| `ingest/` | Hugo | Téléchargement NOAA, manifeste (URL, date, SHA-256), parsing, chargement (`COPY`), F5 |
| `verify/` | Hugo | Vérification indépendante : relit les CSV NOAA, sans la base |
| `weatherscope/services/`, `weatherscope/cli.py` | Stevenson | F1–F4, traçabilité, CLI typer |
| `deploy/`, `bench/`, `tests/` | Mamadou | Docker, Citus, comparaison local/distribué, panne, E1–E4 |
| `weatherscope/db.py`, `sql/`, `CLAUDE.md` | Tous | Contrat commun |
| `docs/rapport/` | Tous (Hugo assemble) | Rapport LaTeX |

## Modèle de données (D14, D15)

Schéma : `sql/schema.sql` (local et distribué), puis `sql/distribute.sql` (Citus seulement). Alternative mesurée : `sql/alt_wide.sql`.
- `observations` : une ligne par mesure, clé (station, element, date), `value` entier brut NOAA (dixièmes), flags NULL si vides, `batch_id`.
- `stations` (774, maille 0,5° `cell_lat`/`cell_lon`) et `batches` (provenance des lots) : tables de référence Citus.
- `observations_history`, `observations_staging`, `monthly_stats` : distribuées par `station`, colocalisées avec `observations`.
- `observations_si` : vue en °C / mm pour l'affichage. Les calculs se font sur les entiers (sommes et comptes), jamais sur des flottants :
  l'ordre des additions change entre local et distribué.
- Toute clé primaire ou contrainte d'unicité contient `station` (exigence Citus).
- Calculs non décomposables (médiane, percentiles) : station par station.
- Définitions de F2 et F3 : D17, avec `verify/` comme référence exécutable. Arrondi à la sortie seulement, à 0,01, comme `round(numeric, 2)` de PostgreSQL.

## Règles de données (ne pas déroger sans le noter dans `docs/decisions.md`)

- Uniquement des observations NOAA réelles : ne rien fabriquer, ne rien dupliquer.
- `qflag` non vide = observation invalide : stockée et comptée, mais exclue des calculs.
- PRCP avec `mflag` `P` (manquante présumée nulle) ou `T` (trace) : jamais traitée comme un zéro ordinaire. Le choix fait est documenté.
- F2 : un jour manquant ou invalide coupe un épisode. Les épisodes sont calculés sur des dates continues : un épisode décembre–janvier reste un seul épisode.
- Traçabilité : chaque résultat de service renvoie de quoi lister ses observations sources (station, date, élément, valeur, flags).
- F5 : importer deux fois le même lot laisse l'archive inchangée. Une valeur ou un flag différent pour une observation existante écrase la valeur et archive l'ancienne dans une table d'historique.
- Pas de données de mesure ni de base dans Git : `data/raw/*` (sauf les 3 fichiers de métadonnées) et `data/db/` sont ignorés. Le manifeste des lots est commité.

## Commandes

```
uv sync                                           # dépendances
docker compose -f deploy/local/compose.yml up -d  # PostgreSQL local, port 5440
docker exec -i weatherscope-local-postgres-1 psql -U weatherscope -d weatherscope < sql/schema.sql  # schéma (base vide)
uv run python ingest/download.py                  # fichiers by_station des 774 stations -> data/raw/by_station/
uv run python -m ingest.load                      # import (initial ou F5), idempotent ; fichiers en argument possibles
uv run python -m verify.f2_episodes --zone SP --start 2015-01-01 --end 2024-12-31 --threshold 400 --min-days 3
uv run python -m verify.f3_anomalies --zone GM --years 2015 2024   # vérification indépendante (fichiers NOAA, sans base)
uv run pytest                                     # tests
cd docs/rapport && make                           # rapport PDF
```

## Façon de travailler

- Journal des décisions : `docs/decisions.md`. Chaque choix fait (technologie, données, modèle, placement, règle, coupe de périmètre…) y est ajouté au moment où il est pris : décision, pourquoi, alternatives écartées, statut. Une décision changée n'est pas effacée : elle passe en « remplacée » et renvoie à la nouvelle.
- Commits : aucune mention de Claude (pas de `Co-Authored-By`, pas de « Generated with Claude Code »).
- Une branche par membre (`data`, `services`, `deploy`), PR courtes vers `main`, plusieurs fois par jour.
- Proposer un plan avant d'écrire du code. Rester simple : le délai est très court.
- Chaque membre doit pouvoir expliquer n'importe quel fichier en soutenance : code lisible, commentaires courts.
