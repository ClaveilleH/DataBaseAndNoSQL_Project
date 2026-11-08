#!/usr/bin/env bash
# Enchaîne les mesures restantes, dans l'ordre imposé (voir docs/passation_mesures.md) :
#   1. E3 sur Citus-2, puis sur le local ;  2. E1 ;  3. passage à 3 workers (IRRÉVERSIBLE) ;  4. E2 sur Citus-3.
# Prérequis : local et Citus chargés (21 460 068 observations chacun), E2 local et citus2 déjà faits sur CE poste.
# Durée : environ 2 h. Les paramètres d'E3 sont réduits (F3 prend ~63 s sur Citus, voir la note de passation).
# Usage : bash bench/run_all.sh [durée d'ingestion du chargement local complet, en secondes]
set -euo pipefail
cd "$(dirname "$0")/.."
FULL_INGEST_S="${1:?indiquer la durée mesurée du chargement local complet (secondes), ex. 4602}"
RUN="python -m uv run python -u -m"

$RUN bench.e3 --config citus2 --n 20 --reps 3 --shares 0 5 25 50 100
$RUN bench.e3 --config local  --n 20 --reps 3 --shares 0 5 25 50 100
$RUN bench.e1 --sizes 10 25 100 --full-ingest-seconds "$FULL_INGEST_S"
# E1 laisse le local actif : on le coupe et on redémarre Citus-2 avant d'ajouter w3.
docker compose -f deploy/local/compose.yml stop
docker compose -f deploy/citus/compose.yml up -d coordinator w1 w2
bash deploy/citus/add_worker.sh            # après cette étape, Citus-2 n'existe plus : tout ce qui est citus2 doit être fait avant
$RUN bench.e2 --config citus3 --runs 5
$RUN bench.report > bench/results/tableaux.md
echo "Mesures terminées : bench/results/ (tableaux.md pour le rapport)"
