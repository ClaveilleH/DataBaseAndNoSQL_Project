# Passation : mesures de la Partie II (état au 8 novembre 2026, 21 h)

Ce qui a été fait sur le poste de Mamadou, ce qui reste, et qui le fait. Les scripts sont dans `bench/`,
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

1. **Mesures (Mamadou, sur son PC, en cours le 8 novembre au soir)** : `bash bench/run_all.sh 4602` (≈ 2 h) enchaîne E3 Citus-2, E3 local,
   E1, le passage à 3 workers et E2 Citus-3, puis écrit `bench/results/tableaux.md`. Les résultats arriveront par une PR `results` vers `main`.
   Les données sont déjà chargées sur ce PC : **personne ne recharge rien**, et tous les temps viennent du même poste (comparables entre eux).
2. **Stevenson** :
   - **Rapport, Partie II** : marqueurs rouges `faire` de `docs/rapport/rapport.tex` (section « Partie II » et « Expériences »).
     Peut commencer tout de suite avec ce qui est déjà mesuré : déploiement, placement, panne, E2 local/Citus-2 et la cause de F3 (ci-dessus) ;
     E1, E3 et Citus-3 viendront de `tableaux.md`.
   - **Vérification indépendante de F4** (script dans `verify/` qui relit les fichiers NOAA, comme F2 et F3).
   - **E4 (bonus)** : déséquilibre entre workers (w2 porte 22 % de plus que w1 en Citus-2) ; pas de script.
   - Slides, démo de 5 min, préparation du défi en direct, relecture croisée.
3. **Hugo** : corriger D19 dans `docs/decisions.md` (Mamadou travaille sur la Partie II), ajouter les décisions du déploiement Citus, assembler le rapport.

## Écarts au protocole à écrire dans le rapport

- **E3** : 20 requêtes par série, 3 répétitions, parts de 0, 5, 25, 50 et 100 % de régionales, au lieu de 200 requêtes, 5 répétitions et 0/1/5/25/50/100 %
  prévus par `docs/e3_prediction.md`. Raison : F3 prend ~63 s sur Citus, une série à 100 % aurait duré près de 2 h par répétition.
  La part de 1 % n'est donc pas mesurée (5 % est le plus petit point).
- **E1** : tailles 10 %, 25 % et 100 % des stations (la plus grande = 21,46 M observations ≥ 10 M) ; 100 % = chargement initial mesuré seul (4 602 s).
- **E2 Citus-3** : 5 répétitions (7 pour local et Citus-2).
- **Poste** : ingestion 77 min (Docker 7,6 Go de RAM, disque à 95 %), pas les 19 min de Hugo ; plusieurs instances sur un seul poste se partagent
  CPU, mémoire et disque, ce n'est pas un cluster de machines.

## Pour relancer sur un autre poste (si besoin)

- Docker avec ≥ 8 Go de RAM, ≥ 30 Go de disque libre, `uv`. **Utiliser `127.0.0.1` et non `localhost`** (sinon ~200 s par connexion sous Windows).
- Chargements (non versionnés) : `ingest/download.py`, puis `ingest.load` sur le local (≈ 77 min) et sur Citus (`deploy/citus/init.sh`, ≈ 30 min), jamais en même temps.
- Refaire alors aussi E2 local et Citus-2 : les temps ne se comparent pas d'un poste à l'autre.
- Tout ce qui est `citus2` doit passer **avant** `deploy/citus/add_worker.sh` (passage à 3 workers définitif).
