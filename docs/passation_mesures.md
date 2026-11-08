# Passation : mesures de la Partie II (état au 8 novembre 2026, 20 h 30)

Ce qui a été fait sur le poste de Mamadou, ce qui reste, et comment le reprendre. Les scripts sont dans `bench/`,
le déploiement dans `deploy/citus/`, les résultats bruts dans `bench/results/`.

## Fait (et commité sur la branche `deploy`)

- **Déploiement Citus** (`deploy/citus/`) : coordinateur + `w1`, `w2` (+ `w3` en profil `citus3`), `init.sh`, `add_worker.sh`.
  Pas de réplication (facteur 1) ; budget de tampons ≈ 2 Go partout (local 2 Go, Citus-2 2 × 1 Go, Citus-3 3 × 700 Mo).
- **Chargements** : 21 460 068 observations (774 stations, 1991-2024) sur le local **et** sur Citus, mêmes totaux que Hugo.
  Ingestion locale mesurée seule : **4 602 s (77 min)** ; Citus ≈ 30 min (chargé en même temps qu'une autre charge, donc pas comparable).
- **Test local/distribué** (`tests/test_local_vs_citus.py`) : **14 tests sur 14** (F1 sur des stations de chaque worker, F2 dont un épisode
  à cheval sur deux années, F3, F4, `trace`, F5 idempotent). Résultats identiques.
- **Perte d'une instance** (`bench/results/panne.json`) : `w2` arrêté → F1 sur une station de `w2` et F3 échouent explicitement
  (code 2, « ÉCHEC », aucun résultat partiel) ; F1 sur un autre worker répond ; après redémarrage les sorties sont identiques à celles d'avant.
  replication_factor = 1 : un système répliqué pourrait répondre depuis une copie, pas notre prototype.
- **E2 local et Citus-2** (`e2_local.json`, `e2_citus2.json`) : mêmes résultats (empreintes SHA-256 identiques) pour les 6 requêtes.

| Requête (médiane, s) | Local | Citus-2 |
|---|---|---|
| F1, une station, un an | 0,009 | 0,013 |
| TMAX annuel par zone, 1991-2024 | 12,39 | 4,69 |
| F2 Allemagne, TMAX ≥ 30 °C | 10,04 | 2,40 |
| F2 Espagne, TMAX ≥ 35 °C | 0,32 | 1,83 |
| F3, deux pays | 1,50 | **63,23** |
| F4 Espagne, PRCP | 26,17 | **106,12** |

  Répartition des mesures sur Citus-2 : `w1` 1 196 Mo, `w2` 1 457 Mo (w2 porte 22 % de plus que w1) ; F1 = 1 tâche (un seul worker contacté).
  **Cause de F3 lent sur Citus** : `EXPLAIN` montre que le CTE `ms` (agrégats mensuels) devient un « Distributed Subplan » : toutes les lignes sont
  rapatriées au coordinateur, qui fait seul les tris et les jointures. Pour F4 (106 s contre 26 s), la même cause est probable mais le plan n'a pas été examiné : à vérifier avec `EXPLAIN`. Notre prédiction E3 (« F3 proche, léger avantage au local »)
  était donc fausse d'un facteur ~40 : à expliquer dans le rapport (une prédiction fausse mais bien expliquée est valorisée).
  Remarque : le champ `shared_buffers` des résultats Citus est celui du **coordinateur** (256 Mo) ; les workers ont 1 Go (Citus-2) ou 700 Mo (Citus-3).

## Reste à faire (rien de cela n'a de résultat)

1. **E3** local et Citus-2 : commencé sur Citus-2 (parts 0, 2 et 10 % faites, non commitées), arrêté. À refaire en entier.
2. **E1** : tailles 25 % et 50 % (bases dédiées, ingestion mesurée), 100 % réutilise le chargement initial (`--full-ingest-seconds`).
3. **Passage à 3 workers** puis **E2 sur Citus-3**.
4. **E4 (bonus)** : déséquilibre entre workers (le script n'existe pas ; les lignes par worker, les shards et les stations les plus lourdes sont à mesurer).
5. **Rapport, Partie II** : marqueurs rouges `\afaire` de `docs/rapport/rapport.tex` (lignes 240 à 298), puis `bench.report` pour les tableaux.
6. **Vérification indépendante de F4**, slides, démo, défi en direct, relecture croisée.

## Comment reprendre sur un autre poste

- **Prérequis** : Docker avec ≥ 8 Go de RAM, ≥ 30 Go de disque libre, `uv`. **Utiliser `127.0.0.1` et non `localhost`** (sinon ~200 s par connexion sous Windows).
- **Chargements** (les données de `data/db/` ne sont pas dans Git) : `uv run python ingest/download.py`, puis `ingest.load` sur le local (≈ 77 min seul)
  et sur Citus (`deploy/citus/init.sh` puis `DATABASE_URL=...5441 ... ingest.load`, ≈ 30 min). **Ne pas charger les deux en même temps** : le disque sature.
- **Les temps ne se comparent pas d'un poste à l'autre** : refaire aussi `bench.e2 --config local` et `--config citus2` sur le nouveau poste
  pour avoir un jeu cohérent (≈ 40 min), et noter le matériel (`environment` est enregistré dans chaque JSON). Les fichiers `e2_*` de ce dossier sont ceux de Mamadou.
- **Ordre à respecter** : tout ce qui est `citus2` (E2, E3, panne) **avant** `deploy/citus/add_worker.sh`, qui rend le passage à 3 workers définitif.
- **Lancer la suite** : `bash bench/run_all.sh <secondes d'ingestion locale>` (≈ 4 h). Paramètres d'E3 réduits à 50 requêtes par série, 3 répétitions et des parts
  de 0, 2, 10, 50 et 100 % (la prédiction écrite prévoyait 200 requêtes, 5 répétitions, 0/1/5/25/50/100 % : irréalisable, car 50 F3 à 63 s prennent ~53 min par répétition) ;
  cet écart doit figurer dans le rapport.
- **Rapport** : donner les chiffres d'ingestion de ce poste (77 min, Docker 7,6 Go de RAM, disque à 95 %) et pas les 19 min de Hugo ; mentionner que plusieurs instances sur un
  seul poste se partagent CPU, mémoire et disque, et que ce n'est pas un cluster de machines.
