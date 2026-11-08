# Journal des décisions — WeatherScope

Chaque choix du projet est noté ici au moment où il est fait : ce qu'on a décidé, pourquoi, et ce qu'on a écarté.
Ce journal sert de base aux justifications du rapport (le sujet demande de justifier la technologie, le périmètre,
le modèle de données, le placement et le traitement des données).

Statuts : **adoptée** (validée par l'équipe), **proposée** (à valider), **remplacée** (voir la décision qui la remplace).

| N° | Date | Décision | Statut |
| --- | --- | --- | --- |
| D1 | 2026-11-07 | MongoDB comme base de données, en local puis shardé | Remplacée par D13 |
| D2 | 2026-11-07 | Périmètre : Allemagne + Espagne | Adoptée |
| D3 | 2026-11-07 | Périodes : étude 2015–2024, référence 1991–2020 | Adoptée |
| D4 | 2026-11-07 | Règle de sélection des stations | Adoptée |
| D5 | 2026-11-07 | Versionnement des données NOAA et provenance | Adoptée |
| D6 | 2026-11-07 | Environnement : Docker + Python 3.12 géré par uv | Proposée |
| D7 | 2026-11-07 | Modèle de données : un document par observation | Remplacée par D13 puis D15 |
| D8 | 2026-11-07 | Distribution : clé de shard hachée sur la station, alternative à 3 shards | Remplacée par D13 puis D14 |
| D9 | 2026-11-07 | Règles de qualité des données | Proposée |
| D10 | 2026-11-07 | Politique de mise à jour F5 : écraser et historiser | Adoptée |
| D11 | 2026-11-07 | Réductions de périmètre liées au délai | Adoptée |
| D12 | 2026-11-07 | Organisation de l'équipe à trois | Adoptée |
| D13 | 2026-11-07 | PostgreSQL en local, PostgreSQL + Citus en distribué | Adoptée |
| D14 | 2026-11-08 | Distribution Citus : répartition par station, `stations` en table de référence | Adoptée |
| D15 | 2026-11-08 | Modèle de données relationnel : une ligne par mesure, valeurs entières | Adoptée |
| D16 | 2026-11-08 | Données chargées : 1991–2024, un seul chemin d'import pour le chargement initial et F5 | Adoptée |
| D17 | 2026-11-08 | Définitions de F2 et F3, arrondi, vérification indépendante | Adoptée |
| D18 | 2026-11-08 | E3 : local contre Citus-2, charges et prédiction | Adoptée |
| D19 | 2026-11-08 | Réorganisation : Hugo reprend les services, Stevenson et Mamadou gardent distribué et expériences | Adoptée |
| D20 | 2026-11-08 | Pluie : T compté 0 mm valide, P traité comme manquant | Adoptée |
| D21 | 2026-11-08 | F5 : tout extrait NOAA réel, nouvelles stations ajoutées, lot contradictoire refusé | Adoptée |
| D22 | 2026-11-08 | Services F1 et F4, interface en ligne de commande, échec explicite | Adoptée |
| D23 | 2026-11-08 | Longitudes de signe inversé : documentées, pas corrigées | Adoptée |
| D24 | 2026-11-08 | Rapport : strict minimum, sections du sujet, parties distribuées à compléter | Adoptée |

---

## D1 — MongoDB comme base de données

- **Statut :** remplacée par D13 le 2026-11-07, après discussion de l'équipe.
- **Décision :** MongoDB 8.0. Partie I : un serveur `mongod`. Partie II : cluster shardé (config server, routeur `mongos`, shards).
- **Pourquoi :**
  - l'équipe a déjà déployé un cluster MongoDB shardé au TP5 ;
  - le cours porte sur le NoSQL, le choix est cohérent avec son contenu ;
  - chaque exigence de la Partie II a un mécanisme direct : `mongos` donne l'interface unique, `explain()` montre quels shards sont contactés, la clé de shard définit le placement ;
  - les agrégations nécessaires à F2–F4 existent (`$setWindowFields`, `$group`).
- **Alternatives écartées :**
  - PostgreSQL + Citus : F2–F4 plus simples en SQL, mais hors programme et jamais pratiqué ;
  - Cassandra / ScyllaDB : pas d'agrégation multi-stations, F3/F4 auraient dû être calculés en Python ;
  - ClickHouse : très rapide en analyse, mais hors programme et dédoublonnage F5 délicat.
- **Conséquence :** F2–F4 s'écrivent en pipelines d'agrégation, plus verbeux que du SQL ; on les met au point d'abord en local.

## D2 — Périmètre : Allemagne + Espagne

- **Statut :** adoptée, 2026-11-07.
- **Décision :** deux zones définies par pays, d'après le préfixe de l'identifiant de station NOAA : `GM` (Allemagne) et `SP` (Espagne).
- **Pourquoi :**
  - les autres groupes travaillent sur les États-Unis et l'Afrique, on prend l'Europe pour ne pas les chevaucher ;
  - c'est la paire européenne avec le plus de stations exploitables (comptage sur `ghcnd-inventory.txt`, 2026-11-07) : 558 stations en Allemagne et 176 en Espagne couvrent toute la période 2015–2024 ;
  - deux climats très différents (tempéré / méditerranéen), ce qui rend F3 et F4 intéressants ;
  - densité de stations très inégale (dense en Allemagne, faible en Espagne) : c'est le cas que F4 demande de traiter ;
  - deux événements connus pour tester et démontrer les services : crues de juillet 2021 en Allemagne, pluies extrêmes de Valence fin octobre 2024.
- **Zone = pays :** la définition est simple, vérifiable par le jury et sans ambiguïté (le préfixe fait partie de l'identifiant).
- **Alternatives écartées :**
  - Suède + Espagne : bon contraste nord/sud, mais 225 stations avec TMAX en Suède contre 452 en Allemagne ;
  - France + Espagne : seulement 78 stations françaises actives sur la période ;
  - Pays-Bas : 358 stations mais seulement 45 avec des températures.

## D3 — Périodes d'étude et de référence

- **Statut :** adoptée, 2026-11-07.
- **Décision :** période d'étude 2015-01-01 → 2024-12-31 (10 années civiles) ; période de référence 1991-01-01 → 2020-12-31.
- **Pourquoi :**
  - 10 ans dépasse le minimum de 8 années consécutives demandé ;
  - 2024 est la dernière année complète et stable dans l'archive ;
  - 1991–2020 est la normale climatologique officielle de 30 ans : on évite la discussion statistique qu'imposerait une référence plus courte ;
  - 320 stations allemandes et 98 espagnoles ont des températures maximales sur toute la référence ;
  - la référence apporte assez d'observations pour atteindre les 10 millions exigés par E1.
- **Conséquence :** les observations de référence sont chargées par le même pipeline et comptées séparément dans le rapport, comme le sujet l'exige.

## D4 — Règle de sélection des stations

- **Statut :** adoptée, 2026-11-07.
- **Décision :** une station est retenue si au moins un élément parmi TMAX, TMIN et PRCP est actif pendant la période d'étude, d'après les années de début et de fin de l'inventaire. Résultat : 774 stations (589 GM, 185 SP), listées dans `data/stations_selected.csv`.
- **Pourquoi :** les stations qui commencent ou s'arrêtent en cours de période sont réelles et font partie des anomalies à documenter ; les exclure biaiserait la couverture. La colonne `full_study` permet de ne garder que les stations complètes quand un calcul l'exige, et `baseline_tmax` repère celles utilisables pour la référence.
- **Limite connue :** l'inventaire ne donne que la première et la dernière année ; les trous à l'intérieur seront mesurés sur les fichiers d'observations.

## D5 — Versionnement des données NOAA et provenance

- **Statut :** adoptée, 2026-11-07.
- **Décision :**
  - les trois fichiers de métadonnées NOAA (`ghcnd-stations.txt`, `ghcnd-inventory.txt`, `ghcnd-countries.txt`, environ 47 Mo) sont commités dans `data/raw/` ;
  - le manifeste `data/manifest/metadata.json` donne pour chacun l'URL, la date de récupération et le SHA-256 ;
  - les fichiers d'observations et les bases (`data/db/`) ne sont pas versionnés.
- **Pourquoi :** l'archive NOAA est révisée en continu ; garder les fichiers exacts utilisés pour choisir le périmètre rend la sélection vérifiable. Les fichiers d'observations sont trop volumineux pour Git : on garde leur manifeste, qui suffit à vérifier qu'on retélécharge les mêmes.
- **Reproductibilité :** `python ingest/select_stations.py` régénère la sélection, en n'utilisant que la bibliothèque standard Python.

## D6 — Environnement : Docker + Python 3.12 géré par uv

- **Statut :** proposée, 2026-11-07 (non commitée).
- **Décision :** PostgreSQL lancé par Docker Compose (images `postgres:17.2` en local et `citusdata/citus:13.0` en distribué, même version de PostgreSQL) ; code en Python 3.12 avec des versions figées par `uv.lock`. Bibliothèques principales : psycopg 3, polars (lecture rapide des CSV NOAA), typer (CLI), numpy/scipy (statistiques des mesures), matplotlib (figures).
- **Pourquoi :** les trois membres obtiennent le même environnement avec `uv sync` et `docker compose up` ; Docker permet de lancer plusieurs instances PostgreSQL isolées sur un seul poste, ce que demande la Partie II.
- **Points d'attention :** la mémoire de PostgreSQL (`shared_buffers`) est fixée par instance pour comparer local et distribué à budget comparable. Le port 5440 est utilisé car 5432 et 5433 sont déjà pris sur le poste d'Hugo.

## D7 — Modèle de données : un document par observation

- **Statut :** remplacée par D13 le 2026-11-07 (modèle propre à MongoDB ; le modèle relationnel reste à décider).
- **Décision :** collection `observations` avec un document par ligne NOAA, identifié par `_id = "station|date|élément"` ; valeur convertie (°C, mm) et valeur brute conservées avec les trois flags. Collections annexes : `stations`, `observations_history`, `batches`.
- **Pourquoi :** l'identifiant donne directement l'identité d'une observation exigée par F5 (dédoublonnage par simple upsert) ; chaque résultat peut lister ses observations sources (traçabilité) ; les flags restent consultables.
- **Alternative à mesurer (exigée par la Partie I) :** modèle *bucket*, un document par station et par mois contenant les jours. Il réduit le nombre de documents et la taille des index, mais complique F5 et la traçabilité. On le compare sur F1 et F3.

## D8 — Distribution : clé de shard hachée sur la station

- **Statut :** remplacée par D13 le 2026-11-07 (placement propre à MongoDB ; le placement Citus reste à décider).
- **Décision :** configuration 1 = 2 shards avec la clé `{station: "hashed"}` ; configuration alternative = 3 shards avec la même clé.
- **Pourquoi :** le hachage équilibre les données ; une requête sur une station (F1) ne contacte qu'un shard ; comme `_id` contient la station, un même `_id` tombe toujours sur le même shard, ce qui garde F5 sans doublon. Faire varier le nombre de shards ne demande qu'un service de plus dans le même fichier Compose.
- **Alternative écartée pour l'instant :** zone sharding (une zone par shard), plus intéressant pour F4 mais déséquilibré et plus long à mettre en place. À reprendre en E4 s'il reste du temps.

## D9 — Règles de qualité des données

- **Statut :** proposée, 2026-11-07.
- **Décision :**
  - une observation avec un `qflag` non vide est stockée et comptée, mais exclue des calculs ;
  - une précipitation avec `mflag` P (manquante présumée nulle) ou T (trace) n'est jamais traitée comme un zéro ordinaire ;
  - dans F2, un jour manquant ou invalide coupe un épisode ; les épisodes sont calculés sur des dates continues, donc un épisode décembre–janvier reste un seul épisode.
- **Pourquoi :** le sujet interdit de créer ou prolonger un épisode silencieusement et de traiter P/T comme des zéros sans justification ; garder les observations signalées permet de les compter et de documenter les anomalies.

## D10 — Politique de mise à jour F5 : écraser et historiser

- **Statut :** adoptée, 2026-11-08 (proposée le 2026-11-07). Mise en œuvre : voir D15.
- **Décision :** si une observation importée existe déjà avec la même valeur et les mêmes flags, rien ne change ; si la valeur ou un flag diffère, la nouvelle version remplace l'ancienne, qui est copiée dans une table d'historique avec le lot responsable.
- **Pourquoi :** les services travaillent toujours sur la version la plus récente de la NOAA, sans perdre la trace de l'ancienne ; importer deux fois le même lot laisse l'archive inchangée, comme le sujet l'exige.

## D11 — Réductions de périmètre liées au délai

- **Statut :** adoptée, 2026-11-07.
- **Décision :** rendu le 8 novembre 2026, donc on ne fait pas d'API web (CLI seule), E4 n'est fait que s'il reste du temps, et F3/F4 utilisent des méthodes simples mais justifiées.
- **Ce qui ne se coupe pas :** les 5 services, la traçabilité, la comparaison local/distribué, la perte d'instance, E1–E3, la vérification indépendante, les 5 anomalies et le README.

## D12 — Organisation de l'équipe à trois

- **Statut :** adoptée, 2026-11-07.
- **Décision :** découpage par couche, chacun propriétaire de ses dossiers : Hugo (données, `ingest/`, `verify/`), Stevenson (services F1–F4, `weatherscope/services/`), Mamadou (distribution et mesures, `deploy/`, `bench/`, `tests/`). Une branche par membre, PR courtes vers `main`.
- **Pourquoi :** trois sessions Claude Code travaillent en parallèle sans conflit Git ; le seul point commun (schéma et connexion) est figé au départ. Le sujet est prévu pour deux personnes, mais le groupe en compte trois.

## D13 — PostgreSQL en local, PostgreSQL + Citus en distribué

- **Statut :** adoptée, 2026-11-07. Remplace D1.
- **Décision :** Partie I : un serveur PostgreSQL 17.2. Partie II : Citus 13.0 (PostgreSQL 17.2), un coordinateur et des workers ; la table des observations est distribuée entre les workers.
- **Pourquoi :**
  - nos données sont tabulaires et de forme fixe (station, date, élément, valeur, trois flags) : la souplesse d'un modèle document n'apporte rien ;
  - F2–F4 sont des requêtes analytiques : suites de jours consécutifs, écarts à une moyenne de référence, croisement de stations sur les mêmes dates. Les fonctions de fenêtre SQL les expriment en quelques lignes, lisibles et faciles à expliquer en soutenance ;
  - le même SQL tourne en local et en distribué, ce qui facilite la garantie de résultats identiques exigée par la Partie II ;
  - `EXPLAIN` montre quels workers sont contactés et comment les résultats partiels sont combinés ;
  - si un worker est arrêté, une requête qui en a besoin échoue explicitement : le sujet interdit de présenter une réponse partielle comme complète ;
  - la configuration alternative (un worker de plus, ou une autre répartition) se fait en quelques commandes (`citus_add_node`, rééquilibrage) ;
  - tout le monde connaît SQL ; Citus ajoute peu de notions (table distribuée, table de référence, colonne de distribution).
- **Vérifié le 2026-11-07 :** PostgreSQL 17.2 local démarre (port 5440) ; un cluster d'essai Citus (1 coordinateur + 2 workers) répartit une table distribuée en 16 morceaux par worker et répond correctement à une agrégation.
- **Alternatives écartées :**
  - MongoDB shardé (D1) : lien plus fort avec le cours et pratiqué au TP5, mais F2–F4 en pipelines d'agrégation longs et difficiles à mettre au point en 1,5 jour, et résultats partiels non signalés à gérer nous-mêmes ;
  - Cassandra et ClickHouse : jamais pratiqués, trop risqués vu le délai.
- **Risque assumé :** le cours porte sur le NoSQL. Le sujet demande seulement de justifier la technologie ; le rapport devra expliquer pourquoi un moteur relationnel distribué convient mieux à ces données et à ces requêtes.
- **Conséquences :** le modèle de données (D7) et le placement distribué (D8) sont à redéfinir pour PostgreSQL / Citus.

## D14 — Distribution Citus : répartition par station

- **Statut :** adoptée, 2026-11-08. Remplace D8.
- **Décision :**
  - `observations` est distribuée par hachage sur `station` (32 shards, 16 par worker avec 2 workers) ;
  - `observations_history`, `monthly_stats` et la table de chargement de F5 sont distribuées sur la même colonne et colocalisées avec `observations` ;
  - `stations` (774 lignes de métadonnées) est une table de référence, copiée sur chaque worker ;
  - configuration principale : 1 coordinateur + 2 workers ; configuration alternative : 3 workers (`citus_add_node` puis `citus_rebalance_start()`), même code ;
  - pas de réplication des shards : un worker arrêté rend ses stations indisponibles, et l'application le signale explicitement.
- **Pourquoi :**
  - toutes les mesures d'une station sont sur un seul worker : F1 ne contacte qu'un worker, et les épisodes de F2 (fenêtres `PARTITION BY station`) se calculent entièrement sur chaque worker ;
  - la colocalisation permet à F5 (comparaison, historique, mise à jour) et au calcul des statistiques mensuelles de se faire sur place, sans échange entre workers ;
  - F3 et F4 se décomposent en sommes et comptes partiels par worker, fusionnés par le coordinateur ; avec des valeurs entières, le résultat est exactement celui du local ;
  - copier `stations` ne contredit pas le sujet, qui interdit de copier les observations, pas les métadonnées ;
  - `EXPLAIN` montre le nombre de tâches et les workers contactés, ce que demande la Partie II.
- **Conséquences :**
  - les clés primaires et contraintes d'unicité doivent contenir `station` ;
  - les calculs non décomposables (médiane, percentiles) se font station par station ;
  - le volume par worker peut être déséquilibré, car les stations n'ont pas toutes autant de mesures : à mesurer avec `citus_shards` (piste pour E4).
- **Alternatives écartées :** répartition par date (F1 et F2 contacteraient tous les workers, F2 devrait recoller des épisodes coupés entre workers) ; répartition par zone (2 valeurs seulement, très déséquilibrée, gardée comme idée de comparaison pour E4).

## D15 — Modèle de données relationnel

- **Statut :** adoptée, 2026-11-08. Remplace D7. Schéma : `sql/schema.sql` (commun), `sql/distribute.sql` (Citus), `sql/alt_wide.sql` (alternative).
- **Décision :**
  - `observations` : une ligne par mesure NOAA (station, élément, date, valeur, mflag, qflag, sflag, heure, lot). Clé primaire (station, élément, date) ;
  - valeurs stockées telles que la NOAA les donne : entiers en dixièmes de °C ou de mm. La vue `observations_si` convertit en °C et mm, pour l'affichage seulement ;
  - flags vides stockés en NULL ; une observation avec `qflag` est stockée mais exclue des calculs ;
  - `stations` : métadonnées des 774 stations, avec la maille de 0,5° (`cell_lat`, `cell_lon`) pour mesurer la densité de stations dans F4 ;
  - `batches` : un lot par import (initial ou mise à jour), avec ses fichiers (URL, taille, SHA-256) et ses comptes. Chaque observation garde l'identifiant du lot qui l'a écrite ;
  - F5 : le lot est copié (`COPY`) dans `observations_staging`, les lignes dont la valeur ou un flag change sont copiées dans `observations_history`, puis `INSERT … ON CONFLICT DO UPDATE … WHERE` ne modifie que ces lignes. Pas de triggers ;
  - `monthly_stats` : par station, élément et mois, nombre de lignes, de valides, d'invalides, de PRCP P/T, somme, min et max des valeurs valides. Recalculée par F5 pour les mois touchés ; F3 en tire les moyennes et les normales 1991–2020 ;
  - des seuils journaliers précalculés pour F4 ne seront ajoutés que si F4 en a besoin.
- **Pourquoi :**
  - une ligne par mesure reprend exactement le format NOAA : chaque mesure a ses propres flags, et la traçabilité vers les observations sources est directe ;
  - l'identité (station, élément, date) est la clé de F5 et contient la colonne de distribution Citus (D14) ;
  - des entiers donnent des sommes identiques quel que soit l'ordre d'addition, donc les mêmes résultats en local et en distribué ;
  - SQL explicite plutôt que triggers : chaque étape de F5 se lit et s'explique en soutenance, et se comporte de la même façon sous Citus ;
  - `monthly_stats` évite de relire 30 ans de mesures journalières pour chaque calcul de F3.
- **Vérifié le 2026-11-08 :** le schéma se charge sur PostgreSQL 17.2 local et sur un cluster Citus de test (1 coordinateur + 2 workers). Les 4 tables de mesures sont colocalisées (même groupe, 32 shards), `stations` et `batches` sont des tables de référence, la vue est recréée par Citus. Un F5 miniature écrase la valeur modifiée, l'archive avec son lot et laisse l'autre ligne inchangée. Une requête sur une station ne contacte qu'un worker (`Task Count: 1`).
- **Alternative mesurée (Partie I) :** `observations_wide`, une ligne par station et par jour avec une colonne par élément, construite à partir de `observations`. Elle a moins de lignes et rend les comparaisons TMAX/TMIN du même jour plus simples, mais les flags sont répétés par colonne et F5 devient plus compliqué. Les deux conceptions seront comparées sur au moins deux requêtes.
- **Alternatives écartées :** valeurs converties stockées en `numeric` (exact aussi, mais on s'éloigne de la donnée source) ; triggers pour l'historique (moins lisibles, comportement à vérifier sous Citus) ; aucun agrégat précalculé (F3 trop lent sur la période de référence).

## D16 — Données chargées et chemin d'import

- **Statut :** adoptée, 2026-11-08.
- **Décision :**
  - source : un fichier NOAA `by_station/<id>.csv.gz` par station retenue (774 fichiers, 237 Mo, téléchargés le 2026-11-08 par `ingest/download.py`, manifeste avec SHA-256 dans `data/manifest/by_station.json`) ;
  - on charge TMAX, TMIN et PRCP de 1991 à 2024 : référence 1991–2020 et étude 2015–2024 dans un seul ensemble ;
  - volume compté dans les fichiers : 7,14 M observations sur 2015–2024 (Allemagne 5,34 M, Espagne 1,81 M) et 21,46 M sur 1991–2024 ;
  - `ingest/load.py` fait le chargement initial et les mises à jour F5 avec le même code : paquets de 50 stations, une transaction par paquet (COPY dans la table de chargement, historique, `ON CONFLICT … WHERE` si changement, recalcul de `monthly_stats` pour les mois touchés) ;
  - chaque exécution crée une ligne dans `batches` avec ses comptes (lues, nouvelles, modifiées, inchangées), même si rien ne change ; une erreur y est notée.
- **Pourquoi :**
  - la période d'étude seule (7,1 M) ne suffit pas pour E1 (au moins 10 M) ; ajouter la période de référence, déjà nécessaire pour F3, donne 21,5 M sans charger de données inutiles ;
  - un seul chemin d'import : F5 est testé à chaque chargement, et il n'y a qu'un code à expliquer ;
  - des transactions par paquet limitent la taille de la table de chargement ; comme l'import est idempotent, un import interrompu se relance sans risque ;
  - garder une ligne de lot même sans changement trace l'exécution sans modifier l'archive.
- **Vérifié le 2026-11-08 :** sur 3 stations (101 396 lignes), un réimport identique donne 0 nouvelle et 0 modifiée ; un lot avec une valeur changée et un `qflag` ajouté donne 2 modifiées, les anciennes valeurs sont archivées avec leur lot d'origine, et `monthly_stats` est recalculée (somme et comptes vérifiés à la main) ; réimporter ce lot ne change plus rien. Chargement complet : 21 460 068 observations en 19 min ; réimport complet des mêmes fichiers en 5 min : 0 nouvelle, 0 modifiée, historique vide, `monthly_stats` inchangée.
- **Alternatives écartées :** charger tout l'historique (44 M lignes : plus lourd sans servir aucun service) ; un chargeur rapide séparé de F5 (deux codes à maintenir et à expliquer).

## D17 — Définitions de F2 et F3, vérification indépendante

- **Statut :** adoptée, 2026-11-08 (proposée le même jour ; implémentée dans `weatherscope/services/`, voir D22). Référence exécutable : `verify/f2_episodes.py`, `verify/f3_anomalies.py`.
- **F2 (épisodes) :**
  - critère choisi par l'utilisateur : élément, seuil en dixièmes (valeur >= seuil), durée minimale ;
  - un jour compte s'il a une observation sans `qflag` qui dépasse le seuil ; tout jour absent, invalide ou sous le seuil coupe l'épisode ;
  - les épisodes sont calculés sur des dates continues : un épisode du 30 décembre au 2 janvier est un seul épisode ; seuls les jours de la période demandée sont pris en compte ;
  - intensité : dépassement moyen au-dessus du seuil et valeur maximale ; tri canonique : station puis date de début.
- **F3 (mois anormaux, TMAX ou TMIN) :**
  - un mois-station est éligible si au moins 80 % de ses jours ont une observation valide ;
  - la normale d'une station pour un mois calendaire est la moyenne de ses mois éligibles sur 1991–2020, si au moins 24 années sur 30 le sont (80 %) ;
  - l'anomalie d'une zone est la moyenne des anomalies par maille de 0,5°, puis la moyenne des mailles : les régions denses en stations ne pèsent pas plus que les autres ;
  - un mois n'est classé que s'il couvre au moins 5 mailles ; classement par valeur absolue décroissante, puis année et mois.
- **Arrondi :** les calculs restent exacts (entiers en SQL, fractions en Python) et ne sont arrondis qu'à la sortie, à 0,01, « moitié loin de zéro » comme `round(numeric, 2)` de PostgreSQL. Le `round()` de Python arrondit au pair et part d'un flottant : il donnait 13,12 au lieu de 13,13 sur 3 épisodes.
- **Pourquoi :** des définitions fixées tôt permettent d'écrire les services et leur vérification en parallèle ; 80 % de jours et 80 % d'années sont des seuils simples, proches des pratiques climatologiques (normales sur 30 ans) ; moyenner par maille répond à l'exigence du sujet sur la densité de stations non uniforme.
- **Vérifié le 2026-11-08 (scripts sur les fichiers NOAA, comparés à des requêtes SQL sur la base locale) :**
  - F2, Espagne, TMAX >= 40,0 °C pendant au moins 3 jours, 2015–2024 : 220 épisodes, identiques en SQL. Le plus long : SPE00120503, du 7 au 17 juillet 2022 (11 jours) ;
  - F2, Allemagne, PRCP >= 5,0 mm pendant au moins 3 jours : 17 340 épisodes, dont 114 à cheval sur deux années, chacun compté une seule fois (par ex. GM000004155, du 29 décembre 2018 au 14 janvier 2019) ;
  - F3, Allemagne, TMAX, 2015–2024 : 120 mois classés, les 8 premiers identiques en SQL sur `monthly_stats` (décembre 2015 +5,16 °C, septembre 2023 +4,79 °C, février 2024 +4,72 °C, juin 2019 +4,64 °C…).
- **Complété le 2026-11-08 :** F3 accepte PRCP (moyenne journalière, mm/jour, voir D20) ; `verify/compare.py` compare automatiquement services et scripts (voir D22).

## D18 — E3 : configurations, charges et prédiction

- **Statut :** adoptée, 2026-11-08. Prédiction complète : `docs/e3_prediction.md`, écrite avant toute mesure et à envoyer à l'enseignante avant les mesures.
- **Décision :**
  - configurations comparées : local (PostgreSQL seul) et Citus-2 (1 coordinateur + 2 workers) ;
  - charge « routine » : F1 sur une station au hasard et une fenêtre de 30 jours ; charge « régionale » : F2 et F3 sur un pays entier, 2015–2024 ;
  - séries de 200 requêtes avec graine fixe et une part de régionales de 0, 1, 5, 25, 50 et 100 % ; 5 répétitions après échauffement.
- **Prédiction :** le local gagne sur la routine seule (surcoût fixe du coordinateur) ; Citus-2 gagne sur les études régionales grâce à F2 ; dans un mélange, le basculement se fait vers 1 à 5 % de régionales, car elles dominent le temps total.
- **Pourquoi ces deux configurations :** ce sont celles où l'écart attendu est le plus net et le plus facile à expliquer ; la configuration à 3 workers sur le même poste ajoute surtout de la concurrence pour le processeur et la mémoire, et sera mesurée dans E2.

## D19 — Réorganisation de l'équipe

- **Statut :** adoptée, 2026-11-08. Modifie D12.
- **Décision :** Stevenson et Mamadou ne répondent pas le jour du rendu. Hugo reprend les services F1–F4, l'interface et la traçabilité, en plus des données et de F5. Le prototype distribué (`deploy/citus/`) et les expériences E1–E4 (`bench/`) restent à Stevenson et Mamadou.
- **Pourquoi :** les services bloquent tout le reste (comparaison local/distribué, mesures, démonstration) ; ils dépendent directement du modèle et des définitions déjà fixés par Hugo.

## D20 — Pluie : traces (T) et manquantes présumées nulles (P)

- **Statut :** adoptée, 2026-11-08. Précise D9.
- **Constat (base locale, 1991–2024) :** aucune pluie marquée P ; 267 marquées T, toutes en Espagne, toutes à 0. Les autres marqueurs présents sont B (18 638 lignes, cumul de deux relevés de 12 h) et D (12 692 lignes, cumul de quatre relevés de 6 h), qui sont de vraies mesures.
- **Décision :**
  - T (trace, moins de 0,1 mm mesurable) : observation valide, comptée 0 mm, et comptée à part (`n_trace`) ;
  - P (manquante, présumée nulle) : traitée comme manquante, jamais comme un zéro mesuré ; comptée à part (`n_presumed`) ;
  - B et D : valeurs valides ordinaires ;
  - observation valide = `qflag` vide et `mflag` différent de P ; c'est la même règle dans les services, `monthly_stats` et la vérification indépendante.
- **Pourquoi :** une trace est une observation réelle d'une pluie négligeable, donc 0 mm est la valeur la plus juste ; P n'est pas une mesure, la compter comme 0 ferait baisser les moyennes et pourrait couper ou créer des épisodes à tort. Le sujet interdit d'utiliser P ou T comme des zéros ordinaires sans justification.
- **Changement de schéma :** `monthly_stats.n_pt` est remplacée par `n_presumed` et `n_trace` (base locale modifiée par `ALTER TABLE`, sans recalcul puisqu'il n'y a aucune P).

## D21 — F5 : extraits NOAA quelconques, nouvelles stations, lots contradictoires

- **Statut :** adoptée, 2026-11-08. Complète D10 et D16.
- **Décision :** `ingest/load.py` (et la commande `import`) accepte tout fichier CSV GHCN-Daily réel, `by_station` ou `by_year`, compressé ou non :
  - seules les lignes TMAX/TMIN/PRCP des stations GM et SP sont retenues, les autres pays sont comptés et ignorés ;
  - une station GM/SP absente de la base est ajoutée d'après `ghcnd-stations.txt` (le sujet cite « un ensemble de stations exclues du chargement initial ») ;
  - sans fichier : chargement initial 1991–2024 ; avec des fichiers : toutes les années (pour importer 2025, par exemple), sauf option `--years` ;
  - un doublon exact dans un lot est écrit une fois ; deux versions différentes d'une même observation dans un lot font échouer le paquet, l'erreur est notée dans `batches` et la base reste inchangée ;
  - les mois touchés pour `monthly_stats` sont déduits des lignes écrites, et plus du nom des fichiers (un fichier `by_year` contient toutes les stations).
- **Pourquoi :** à la soutenance, le jury peut fournir un extrait NOAA à importer ; il doit passer quel que soit son format ou ses stations.
- **Vérifié le 2026-11-08 (base jetable) :** fichier `by_year` 2025 complet (166 Mo, 19,6 M lignes, tous pays) : 697 993 lignes GM/SP importées en 35 s, 18,9 M ignorées ; réimport : 0 nouvelle, 0 modifiée. Station hors sélection GM000002698 (Karlsruhe, 1876–2008) : ajoutée avec ses 144 883 observations. Lot contradictoire : refusé, valeur existante intacte.

## D22 — Services F1 et F4, interface, échec explicite

- **Statut :** adoptée, 2026-11-08. Code : `weatherscope/services/`, `weatherscope/cli.py`.
- **Interface :** ligne de commande (`uv run python -m weatherscope.cli`) : `stations`, `station` (F1), `episodes` (F2), `anomalies` (F3), `events` (F4), `trace`, `import` (F5). Option `--json` (résultat complet, ordre canonique) et `--explain` (plan d'exécution, qui montre en distribué les tâches et les workers contactés).
- **F1 :** recherche par zone ou rectangle et par nom ; pour une station et un intervalle, résumé mensuel par élément : jours attendus, présents, valides, invalides, traces, présumées nulles, disponibilité, moyenne (températures) ou cumul (pluie), min, max.
- **F4 :**
  - jour inhabituel pour une station : valeur valide au-dessus de son quantile 95 % pour ce mois calendaire sur 1991–2020 (au moins 80 % des jours de référence) ;
  - on compte des mailles de 0,5° et non des stations, car la densité n'est pas uniforme ; jour régional : au moins 3 mailles touchées et au moins 25 % des mailles qui rapportent ce jour-là ;
  - les jours régionaux consécutifs forment un événement ; sévérité = somme des parts de mailles touchées ; extrême isolé = une seule maille touchée ;
  - preuves : chaque observation inhabituelle (station, date, valeur, seuil, maille).
- **Traçabilité :** chaque résultat porte un champ `sources` utilisable avec `trace` ; F4 contient directement ses preuves.
- **Échec explicite :** si la base ou un worker ne répond pas, la commande affiche « ÉCHEC », la cause, et aucun résultat partiel (code de sortie 2).
- **Vérifié le 2026-11-08 (base locale complète) :** F1 0,5 s ; F2 (Espagne, 10 ans) 0,8 s ; F3 (2 pays) 1 s ; F4 (Allemagne, 10 ans) 29 s, dont l'essentiel pour calculer les quantiles de référence. `verify/compare.py` : 4 cas (F2 TMAX Espagne, F2 PRCP Allemagne avec 16 126 épisodes, F3 TMAX Allemagne, F3 PRCP Espagne) identiques aux scripts indépendants, classements compris.
- **Exemples :** F4 Allemagne 2015–2024 : 166 événements ; le plus sévère du 1er au 12 novembre 2015 (pic le 8, 98 % des mailles) ; 185 jours d'extrême isolé, souvent à GM000004155 (Zugspitze, 2 964 m).
- **Piste (E4) :** F4 recalcule les quantiles de référence à chaque requête ; une table de seuils tenue à jour par F5 les rendrait instantanés.

## D23 — Longitudes de signe inversé dans les métadonnées NOAA

- **Statut :** adoptée, 2026-11-08.
- **Constat :** 9 stations espagnoles retenues ont une longitude positive alors qu'elles sont à l'ouest de Greenwich : SPE00120008 et SPE00119999 (Castellón), SPE00120161 (Huesca), SP000008416 et SPE00120584 (Valence), SPE00101043 et SPE00101035 (Alicante), SP000007038 (Torrevieja), SPE00120341 (Murcie/San Javier). Pour 3 d'entre elles, la même station existe sous un autre identifiant avec le bon signe (par ex. SPE00101035 à +0,5706 et SPM00008360 à −0,558 pour l'aéroport d'Alicante).
- **Décision :** garder les métadonnées NOAA telles quelles et documenter l'anomalie (annexe du rapport, limites).
- **Pourquoi :** corriger à la main reviendrait à modifier la source sans pouvoir le vérifier pour toutes les stations ; l'effet se limite à l'affectation de 9 stations à une maille de 0,5° voisine (F3, F4) et aux recherches par rectangle (F1).
- **Alternative écartée :** table de corrections manuelles (risque d'erreur, non vérifiable par le correcteur dans les fichiers NOAA).

## D24 — Rapport

- **Statut :** adoptée, 2026-11-08.
- **Décision :** rapport LaTeX (`docs/rapport/`) réduit au strict minimum : ce que le sujet demande et nos choix, sans table des matières ni chapitres (chaque chapitre ouvrirait une page). Les parties distribuées et les mesures sont marquées en rouge « À compléter » pour Stevenson et Mamadou.
- **Pourquoi :** 10 pages au maximum hors annexes ; demande d'Hugo.
