#!/usr/bin/env bash
# Enchaîne les mesures restantes, dans l'ordre imposé (voir docs/passation_mesures.md) :
#   1. E3 sur Citus-2, puis sur le local ;  2. E1 ;  3. passage à 3 workers (IRRÉVERSIBLE) ;  4. E2 sur Citus-3.
# Prérequis : local et Citus chargés (21 460 068 observations chacun), E2 local et citus2 déjà faits sur CE poste.
# Durée : environ 4 h. Les paramètres d'E3 sont réduits (F3 prend ~63 s sur Citus, voir la note de passation).
# Usage : bash bench/run_all.sh [durée d'ingestion du chargement local complet, en secondes]
set -euo pipefail
cd "$(dirname "$0")/.."
FULL_INGEST_S="${1:?indiquer la durée mesurée du chargement local complet (secondes), ex. 4602}"
RUN="python -m uv run python -u -m"

$RUN bench.e3 --config citus2 --n 50 --reps 3 --shares 0 2 10 50 100
$RUN bench.e3 --config local  --n 50 --reps 3 --shares 0 2 10 50 100
$RUN bench.e1 --sizes 25 50 100 --full-ingest-seconds "$FULL_INGEST_S"
bash deploy/citus/add_worker.sh            # après cette étape, Citus-2 n'existe plus : tout ce qui est citus2 doit être fait avant
$RUN bench.e2 --config citus3
$RUN bench.report
