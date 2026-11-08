# E3 — Prédiction déposée avant les mesures

Groupe WeatherScope (Hugo, Stevenson, Mamadou) — périmètre Allemagne (GM) + Espagne (SP).
Rédigée le 8 novembre 2026, avant toute mesure de performance. Aucune requête de service n'a encore été chronométrée.

## Configurations comparées

- **Local** : un serveur PostgreSQL 17.2 (conteneur Docker, `shared_buffers` = 2 Go, réglages de parallélisme par défaut : 2 processus parallèles par requête au plus).
- **Citus-2** : Citus 13.0 (PostgreSQL 17.2), 1 coordinateur + 2 workers, chacun dans son conteneur. Les observations sont réparties par hachage de la station en 32 shards (16 par worker).

Les deux contiennent les mêmes données : 21,46 M observations TMAX/TMIN/PRCP de 774 stations, 1991–2024 (environ 2,8 Go pour la table `observations` avec sa clé primaire, 86 Mo pour les agrégats mensuels).

Une seule configuration tourne à la fois, sur le même poste : processeur 8 cœurs / 16 threads, 13 Go de RAM (environ 4 Go libres en usage normal), SSD NVMe.

## Les deux charges

- **Routine (R)** : F1 sur une station tirée au hasard parmi les 774, sur une fenêtre de 30 jours tirée au hasard dans 2015–2024 (mesures et résumé de disponibilité et de qualité).
- **Étude régionale (G)** : alternativement F2 (épisodes de chaleur sur tout un pays, 2015–2024, à partir des mesures journalières) et F3 (mois anormaux sur tout un pays, 2015–2024, à partir des agrégats mensuels et des normales 1991–2020).

Chaque série comprend 200 requêtes tirées avec une graine fixe, envoyées une par une par un seul client. La part de G varie : 0 %, 1 %, 5 %, 25 %, 50 % et 100 %. On mesure le temps total de la série et le temps médian de chaque type de requête, sur 5 répétitions après une série d'échauffement (cache chaud).

## Prédiction

1. **Routine seule (0 % de G) : le local est meilleur.**
   Avec Citus, F1 ne touche qu'un shard, donc un seul worker. La requête passe quand même par le coordinateur : planification distribuée, connexion au worker, renvoi du résultat. Ce surcoût fixe, de l'ordre de 1 à 3 ms, pèse lourd face à une requête qui prend elle-même quelques millisecondes. Nous attendons un temps médian 1,3 à 2 fois plus long pour Citus-2.

2. **Étude régionale seule (100 % de G) : Citus-2 est meilleur, grâce à F2.**
   - **F2** lit les mesures journalières de centaines de stations sur 10 ans (environ 1,7 M lignes de TMAX pour l'Allemagne). En local, une requête utilise au plus 3 processus (le principal et 2 parallèles). Avec Citus, les 32 shards sont traités par des tâches qui tournent en même temps sur les 2 workers et occupent davantage des 16 threads. Le calcul des épisodes (fonctions de fenêtre découpées par station) se fait entièrement sur chaque worker, et le coordinateur n'a qu'à concaténer. Nous attendons Citus-2 1,5 à 3 fois plus rapide sur F2.
   - **F3** ne lit que les agrégats mensuels (86 Mo) : le calcul est court, et le surcoût de 32 tâches distribuées compense le gain du parallélisme. Nous attendons des temps proches, avec un léger avantage au local.
   - Sur l'ensemble de G, F2 domine, donc Citus-2 l'emporte.

3. **Mélange : le basculement arrive tôt, vers 1 à 5 % de G.**
   Une requête régionale coûte des centaines de fois plus qu'une requête de routine. Dès que quelques requêtes régionales sont présentes, elles représentent l'essentiel du temps total. Le local ne devrait donc l'emporter que pour une charge presque purement routinière. Au-delà de quelques pour cent de G, Citus-2 devrait finir la série plus vite, même si chaque requête de routine reste plus lente.

## Ce qui pourrait rendre la prédiction fausse

- **Mémoire.** Les 2 workers ont chacun leur cache et se partagent environ 4 Go libres. Si les données ne tiennent plus en cache, F2 devient limité par le disque partagé, et le parallélisme de Citus ne sert plus à rien.
- **Processeur partagé.** Tous les processus tournent sur les mêmes 8 cœurs. Le gain de Citus sur F2 suppose qu'il reste des cœurs libres, ce qui est vrai avec un seul client mais ne le serait plus avec plusieurs clients simultanés.
- **Plan d'exécution.** Si le planificateur local choisit un parcours d'index par station plutôt qu'un parcours séquentiel parallèle, l'écart sur F2 peut être plus faible que prévu, ou dans l'autre sens.
- **Un seul poste.** Plusieurs processus sur une même machine ne valent pas un vrai cluster de machines indépendantes : les résultats ne disent rien des performances de Citus sur plusieurs serveurs.
