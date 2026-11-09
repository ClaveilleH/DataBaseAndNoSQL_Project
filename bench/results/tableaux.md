## E1 : volume croissant (PostgreSQL local)

Serveur : PostgreSQL 17.2 (Debian 17.2-1.pgdg120+1), shared_buffers 2GB, Docker 8 CPU / 7.6 Go.

| Part des stations | Stations | Observations | dont référence | Ingestion (s) | lignes/s | Base (Mo) | Table observations (Mo) | Cache hit |
|---|---|---|---|---|---|---|---|---|
| 10 % | 78 | 2,164,681 | 1,457,740 | 208.1 | 10,402 | 267 | 250 | None |
| 25 % | 194 | 5,593,881 | 3,766,990 | 1221.3 | 4,580 | 669 | 638 | None |
| 100 % | 774 | 21,460,068 | 14,316,083 | 4602.0 | 4,663 | 2538 | 2439 | None |

| Requête (médiane, s) | 10 % | 25 % | 100 % |
|---|---|---|---|
| étroite : F1, une station, un an | 0.007 (IQR 0.0043) | 0.004 (IQR 0.0004) | 0.0106 (IQR 0.0025) |
| agrégation longue : TMAX annuel par zone, 1991-2024 | 0.4412 (IQR 0.0188) | 0.9779 (IQR 0.0531) | 9.0891 (IQR 0.4047) |
| multi-stations : F2, Allemagne, TMAX >= 30 °C, 10 ans | 0.2075 (IQR 0.0225) | 0.4412 (IQR 0.0301) | 7.5084 (IQR 0.4043) |
| multi-stations : F2, Espagne, TMAX >= 35 °C, 10 ans | 0.1874 (IQR 0.1197) | 0.3594 (IQR 0.21) | 0.2904 (IQR 0.0113) |
| anomalies : F3, deux pays, TMAX | 0.0899 (IQR 0.0048) | 0.3983 (IQR 0.0086) | 1.323 (IQR 0.1002) |

## E2 : local contre distribué

- local : 21,460,068 observations, PostgreSQL 17.2 (Debian 17.2-1.pgdg120+1), shared_buffers 2GB
- citus2 : 21,460,068 observations, PostgreSQL 17.2 (Debian 17.2-1.pgdg120+1), shared_buffers 256MB, workers ['w1', 'w2']
- citus3 : 21,460,068 observations, PostgreSQL 17.2 (Debian 17.2-1.pgdg120+1), shared_buffers 256MB, workers ['w1', 'w2', 'w3']

| Requête (médiane s, IQR) | local | citus2 | citus3 |
|---|---|---|---|
| étroite : F1, une station, un an | 0.0091 (IQR 0.0007) | 0.013 (IQR 0.0008) | 0.0161 (IQR 0.001) |
| agrégation longue : TMAX annuel par zone, 1991-2024 | 12.3928 (IQR 1.6316) | 4.6933 (IQR 0.2024) | 4.7323 (IQR 0.1891) |
| multi-stations : F2, Allemagne, TMAX >= 30 °C, 10 ans | 10.0379 (IQR 0.5466) | 2.4024 (IQR 0.3584) | 1.6757 (IQR 0.0767) |
| multi-stations : F2, Espagne, TMAX >= 35 °C, 10 ans | 0.3175 (IQR 0.0105) | 1.8294 (IQR 0.1996) | 2.1045 (IQR 0.1945) |
| anomalies : F3, deux pays, TMAX | 1.5012 (IQR 0.1277) | 63.2263 (IQR 3.3272) | 58.7392 (IQR 3.343) |
| multi-stations : F4, Espagne, PRCP, 10 ans | 26.1701 (IQR 1.3312) | 106.1222 (IQR 9.2969) | 95.5899 (IQR 2.4466) |

| Première exécution (s) | local | citus2 | citus3 |
|---|---|---|---|
| étroite : F1, une station, un an | 0.2249 | 0.1924 | 0.1033 |
| agrégation longue : TMAX annuel par zone, 1991-2024 | 11.9105 | 4.9243 | 6.1556 |
| multi-stations : F2, Allemagne, TMAX >= 30 °C, 10 ans | 9.8743 | 2.6597 | 1.7792 |
| multi-stations : F2, Espagne, TMAX >= 35 °C, 10 ans | 5.6882 | 2.0477 | 1.4844 |
| anomalies : F3, deux pays, TMAX | 2.2441 | 65.4471 | 62.0874 |
| multi-stations : F4, Espagne, PRCP, 10 ans | 33.3813 | 99.6643 | 99.9581 |

Résultats identiques entre configurations (empreinte SHA-256) : OUI pour toutes les requêtes 

- citus2 : F1 (une station) = 1 tâche(s) ; répartition [{'worker': 'w1', 'shards': 16, 'observations_mb': '1196.4'}, {'worker': 'w2', 'shards': 16, 'observations_mb': '1457.0'}]
- citus3 : F1 (une station) = 1 tâche(s) ; répartition [{'worker': 'w1', 'shards': 12, 'observations_mb': '822.9'}, {'worker': 'w2', 'shards': 11, 'observations_mb': '894.3'}, {'worker': 'w3', 'shards': 9, 'observations_mb': '850.5'}]

## E3 : charge variable (temps total d'une série, médiane de 3 répétitions, 20 requêtes)

| Part régionale | Local (s) | Citus-2 (s) | Citus-2 / local | Plus rapide | F1 médiane local / Citus-2 (s) | F2-F3 médiane local / Citus-2 (s) |
|---|---|---|---|---|---|---|
| 0 % | 0.1142 (IQR 0.4922) | 0.1732 (IQR 0.4377) | 1.52 | local | 0.0061 / 0.00857 | - / - |
| 5 % | 13.2732 (IQR 1.8142) | 2.2164 (IQR 7.5569) | 0.17 | Citus-2 | 0.00801 / 0.00968 | 13.1211 / 2.0214 |
| 25 % | 23.8382 (IQR 13.2344) | 70.0365 (IQR 8.1313) | 2.94 | local | 0.00726 / 0.01161 | 0.8937 / 2.7805 |
| 50 % | 7.129 (IQR 0.0589) | 163.5244 (IQR 4.0782) | 22.94 | local | 0.00683 / 0.00987 | 0.7843 / 6.7309 |
| 100 % | 12.7919 (IQR 0.8647) | 380.8165 (IQR 38.7485) | 29.77 | local | - / - | 0.6035 / 8.7157 |

Prédiction (docs/e3_prediction.md) : local meilleur à 0 %, Citus-2 meilleur à 100 %, basculement vers 1 à 5 %.
Mesuré : premier point où Citus-2 gagne = 5 %.

## Perte d'une instance (w2 arrêté)

**avant_panne**

| Commande | Code | Durée (s) | Message |
|---|---|---|---|
| F1 station du worker arrêté | 0 | 2.32 | (résultat complet affiché) |
| F1 autre station | 0 | 1.47 | (résultat complet affiché) |
| F3 | 0 | 66.89 | (résultat complet affiché) |

**worker_arrete**

| Commande | Code | Durée (s) | Message |
|---|---|---|---|
| F1 station du worker arrêté | 2 | 5.02 | ÉCHEC : la base ou une de ses instances est indisponible ; la requête n'a pas été exécutée en entier. Détail : connection to the remote node |
| F1 autre station | 0 | 0.91 | (résultat complet affiché) |
| F3 | 2 | 4.9 | ÉCHEC : la base ou une de ses instances est indisponible ; la requête n'a pas été exécutée en entier. Détail : connection to the remote node |

**apres_redemarrage**

| Commande | Code | Durée (s) | Message |
|---|---|---|---|
| F1 station du worker arrêté | 0 | 2.19 | (résultat complet affiché) |
| F1 autre station | 0 | 1.61 | (résultat complet affiché) |
| F3 | 0 | 64.65 | (résultat complet affiché) |

- OK : F1 sur le worker arrêté échoue explicitement (code 2)
- OK : F1 sur un autre worker répond normalement
- OK : F3 échoue explicitement (code 2)
- OK : aucun résultat partiel pour F1 et F3 pendant la panne
- OK : après redémarrage, F1 et F3 identiques à avant la panne

