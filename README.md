# WeatherScope

Observatoire météo historique sur les données NOAA GHCN-Daily, pour l'Allemagne et l'Espagne.
Projet M2 SLCD « Big Data and NoSQL » (sujet : `docs/Project1_WeatherScope.pdf`).

- **Données :** 774 stations (589 en Allemagne, 185 en Espagne), éléments TMAX, TMIN et PRCP, de 1991 à 2024, soit 21 460 068 observations.
  - Étude : 2015–2024.
  - Référence pour les normales : 1991–2020.
- **Base :** PostgreSQL 17.2 pour le prototype local (Partie I), et PostgreSQL + Citus 13.0 pour le prototype distribué (Partie II). Le code et le SQL sont les mêmes dans les deux cas.
- **Interface :** une ligne de commande qui expose les services F1 à F5 et la traçabilité.
- **Choix et justifications :** `docs/decisions.md`, décisions D1 à D22.

## Prérequis

- Docker (avec Compose) ;
- [uv](https://docs.astral.sh/uv/), qui installe Python 3.12 et les dépendances ;
- environ 4 Go de disque pour la base et 0,5 Go pour les fichiers NOAA.

## Installation et chargement (prototype local)

```bash
uv sync                                                   # dépendances Python
docker compose -f deploy/local/compose.yml up -d          # PostgreSQL 17.2, port 5440
docker exec -i weatherscope-local-postgres-1 psql -U weatherscope -d weatherscope < sql/schema.sql

uv run python ingest/select_stations.py   # (facultatif) régénère data/stations_selected.csv depuis les métadonnées NOAA
uv run python ingest/download.py          # 774 fichiers by_station (237 Mo, ~1 min) + manifeste SHA-256
uv run python -m ingest.load              # chargement 1991-2024 (~20 min, 21,46 M observations)
```

La base utilisée est celle de la variable `DATABASE_URL`. Par défaut, c'est `postgresql://weatherscope:weatherscope@localhost:5440/weatherscope`. Pour le prototype distribué, il suffit de la faire pointer vers le coordinateur Citus.

### Provenance

Ces fichiers sont versionnés :
- `data/manifest/metadata.json` et `data/manifest/by_station.json` : URL, date de récupération, taille et SHA-256 de chaque fichier source ;
- les trois fichiers de métadonnées NOAA, dans `data/raw/`.

Les mesures elles-mêmes ne sont pas versionnées : elles se retéléchargent avec la commande ci-dessus.

Chaque import crée une ligne dans la table `batches`, avec ses fichiers et ses comptes. Chaque observation garde l'identifiant du lot qui l'a écrite.

## Services

```bash
uv run python -m weatherscope.cli --help
```

| Commande | Service | Exemple |
| --- | --- | --- |
| `stations` | F1 : chercher des stations | `stations -z SP --name madrid` |
| `station` | F1 : résumé mensuel d'une station (disponibilité, qualité, moyennes, cumuls) | `station SP000003195 --start 2022-06-01 --end 2022-08-31` |
| `episodes` | F2 : épisodes de jours consécutifs au-dessus d'un seuil | `episodes -z SP --start 2015-01-01 --end 2024-12-31 --threshold 40` |
| `anomalies` | F3 : mois les plus éloignés de la normale 1991–2020 | `anomalies -z GM -z SP --element TMAX` |
| `events` | F4 : événements régionaux et extrêmes isolés | `events -z GM --start 2015-01-01 --end 2024-12-31` |
| `trace` | Observations sources d'un résultat | `trace --station SPE00120503 --element TMAX --start 2022-07-07 --end 2022-07-17` |
| `import` | F5 : importer un lot NOAA | `import data/raw/by_year/2025.csv.gz` |

Options communes :
- `--json` donne le résultat complet, dans un ordre canonique, pour la comparaison automatique.
- `--explain` affiche le plan d'exécution. En distribué, on y voit les tâches et les workers contactés.

Si la base ou un worker ne répond pas, la commande affiche « ÉCHEC » et ne montre aucun résultat partiel (code de sortie 2).

### Définitions (résumé ; détail dans D17, D20 et D22)

- **Observation valide :** pas de `qflag`, et pas de `mflag` P. Une trace de pluie (T) compte pour 0 mm et est comptée à part.
- **F2 :** suite maximale de jours consécutifs dont la valeur valide atteint le seuil. Un jour absent ou invalide coupe l'épisode ; un épisode à cheval sur deux années reste un seul épisode.
- **F3 :**
  - un mois-station est retenu s'il a au moins 80 % de jours valides ;
  - la normale d'une station pour un mois de l'année demande au moins 24 années sur 30 ;
  - l'anomalie d'une zone est la moyenne par maille de 0,5°, puis la moyenne des mailles, pour tenir compte de la densité des stations.
- **F4 :**
  - un jour est inhabituel pour une station s'il dépasse son quantile 95 % du même mois sur 1991–2020 ;
  - un jour est régional si au moins 3 mailles et 25 % des mailles qui rapportent sont touchées ;
  - les jours régionaux consécutifs forment un événement ;
  - un extrême isolé ne touche qu'une seule maille.
- **F5 :**
  - fichiers acceptés : `by_station` ou `by_year` ; seules les stations GM et SP sont retenues, et une station inconnue est ajoutée d'après `ghcnd-stations.txt` ;
  - une valeur ou un flag modifié écrase l'ancienne version, qui est archivée dans `observations_history` ;
  - réimporter le même lot ne change rien, et un lot contradictoire est refusé.

## Vérification indépendante

```bash
uv run python -m verify.compare      # F2 et F3 : services (base) contre scripts lisant les fichiers NOAA → « OK »
uv run python -m verify.f2_episodes --zone SP --start 2015-01-01 --end 2024-12-31 --threshold 400 --min-days 3
uv run python -m verify.f3_anomalies --zone GM --years 2015 2024
uv run python -m verify.data_report  # chiffres du jeu de données et anomalies → docs/data_report.md
```

Les scripts de `verify/` n'utilisent ni la base ni le code des services. Leurs résultats sont enregistrés dans `verify/results/`.

## Prototype distribué

Le schéma est réparti par `sql/distribute.sql`, à exécuter après `sql/schema.sql` sur le coordinateur, une fois les workers ajoutés :
- les tables de mesures sont réparties par hachage de la station en 32 shards ;
- `stations` et `batches` sont des tables de référence, copiées sur chaque worker.

Le déploiement Docker (`deploy/citus/`), la comparaison local/distribué, la perte d'une instance et les expériences E1–E4 (`bench/`) sont décrits dans leurs dossiers.

## Organisation du dépôt

| Dossier | Contenu |
| --- | --- |
| `ingest/` | Sélection des stations, téléchargement, import (chargement initial et F5) |
| `sql/` | Schéma (`schema.sql`), répartition Citus (`distribute.sql`), conception alternative (`alt_wide.sql`) |
| `weatherscope/` | Connexion (`db.py`), services F1–F4 et traçabilité (`services/`), interface (`cli.py`) |
| `verify/` | Vérification indépendante sur les fichiers NOAA, comparaison automatique, chiffres du jeu de données |
| `deploy/` | Docker : PostgreSQL local, cluster Citus |
| `bench/`, `tests/` | Mesures (E1–E4) et tests |
| `docs/` | Décisions, prédiction E3, chiffres du jeu de données, rapport LaTeX |
