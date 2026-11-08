#!/usr/bin/env bash
# Passe de Citus-2 à Citus-3 : démarre w3, l'enregistre, puis rééquilibre les shards
# (configuration distribuée alternative, même code et mêmes requêtes).
# Pour garder le même budget mémoire total, relancer avant avec WORKER_SHARED_BUFFERS=700MB
# (voir compose.yml) ; sinon w3 s'ajoute aux 2 Go déjà alloués.
set -euo pipefail

cd "$(dirname "$0")/../.."
COMPOSE="docker compose -f deploy/citus/compose.yml --profile citus3"
psql_coord() { $COMPOSE exec -T coordinator psql -v ON_ERROR_STOP=1 -U weatherscope -d weatherscope "$@"; }

$COMPOSE up -d w3
for node in coordinator w3; do
  until $COMPOSE exec -T "$node" psql -U weatherscope -d weatherscope -tAc "SELECT citus_version()" >/dev/null 2>&1; do sleep 2; done
done

psql_coord -tAc "SELECT citus_add_node('w3', 5432)
                 WHERE NOT EXISTS (SELECT 1 FROM pg_dist_node WHERE nodename = 'w3')" >/dev/null

echo "Répartition avant rééquilibrage :"
psql_coord -c "SELECT nodename, count(*) AS shards, pg_size_pretty(sum(shard_size)) AS taille
               FROM citus_shards GROUP BY nodename ORDER BY nodename"

# block_writes : observations_staging (table de chargement F5) n'a pas de clé primaire, donc pas de
# réplication logique ; le rééquilibrage se fait de toute façon hors charge, entre deux expériences.
psql_coord -c "SELECT citus_rebalance_start(shard_transfer_mode := 'block_writes')"
psql_coord -c "SELECT citus_rebalance_wait()"

echo "Répartition après rééquilibrage :"
psql_coord -c "SELECT nodename, count(*) AS shards, pg_size_pretty(sum(shard_size)) AS taille
               FROM citus_shards GROUP BY nodename ORDER BY nodename"
