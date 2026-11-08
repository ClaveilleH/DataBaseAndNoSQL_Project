#!/usr/bin/env bash
# Initialise le cluster Citus-2 : enregistre w1 et w2 sur le coordinateur, puis applique
# sql/schema.sql et sql/distribute.sql. À lancer une fois, après `docker compose ... up -d`.
# Relançable : les workers déjà enregistrés sont ignorés ; le schéma n'est appliqué que s'il est absent.
set -euo pipefail

cd "$(dirname "$0")/../.."
COMPOSE="docker compose -f deploy/citus/compose.yml"
psql_coord() { $COMPOSE exec -T coordinator psql -v ON_ERROR_STOP=1 -U weatherscope -d weatherscope "$@"; }

echo "Attente du coordinateur et des workers…"
for node in coordinator w1 w2; do
  # pg_isready répond déjà pendant l'initialisation temporaire de l'image : on attend Citus lui-même.
  until $COMPOSE exec -T "$node" psql -U weatherscope -d weatherscope -tAc "SELECT citus_version()" >/dev/null 2>&1; do sleep 2; done
done

for w in w1 w2; do
  psql_coord -tAc "SELECT citus_add_node('$w', 5432)
                   WHERE NOT EXISTS (SELECT 1 FROM pg_dist_node WHERE nodename = '$w')" >/dev/null
done
echo "Workers enregistrés :"
psql_coord -c "SELECT nodeid, nodename, nodeport, isactive FROM pg_dist_node ORDER BY nodeid"

if [ "$(psql_coord -tAc "SELECT to_regclass('public.observations') IS NOT NULL")" = "t" ]; then
  echo "Schéma déjà présent : sql/schema.sql et sql/distribute.sql ignorés."
else
  psql_coord < sql/schema.sql
  psql_coord < sql/distribute.sql
fi

echo "Tables réparties :"
psql_coord -c "SELECT table_name, citus_table_type, distribution_column, colocation_id, shard_count
               FROM citus_tables ORDER BY colocation_id, table_name::text"
echo "Coordinateur prêt : DATABASE_URL=postgresql://weatherscope:weatherscope@127.0.0.1:5441/weatherscope"
