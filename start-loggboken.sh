#!/usr/bin/env bash
# Tunn wrapper runt de docker-compose-kommandon som redan är dokumenterade i
# README.md ("Kom igång lokalt" / "Testa mot exempeldata") — samma steg, bara
# ett kommando istället för att komma ihåg ordningen.
set -euo pipefail

ACTION="${1:-}"
MODE="${2:-}"

usage() {
  cat >&2 <<EOF
Användning: $0 <up|down> [test]

  up        starta standardinstansen (produktionslik, tom, portar 8000/5173/5432)
  up test   starta en separat, isolerad testinstans (-p loggboken-test) och
            seeda den med exempeldata — kräver att standardinstansen är nedstängd
            först (samma fasta portar i docker-compose.yml)
  down      stäng ner standardinstansen (databasen ligger kvar i volymen)
  down test stäng ner testinstansen och ta bort dess volym (engångsdata, återseedas ändå vid nästa 'up test')
EOF
  exit 1
}

[[ "$ACTION" == "up" || "$ACTION" == "down" ]] || usage
[[ -z "$MODE" || "$MODE" == "test" ]] || usage

compose=(docker compose)
if [[ "$MODE" == "test" ]]; then
  compose=(docker compose -p loggboken-test)
fi

if [[ "$ACTION" == "down" ]]; then
  if [[ "$MODE" == "test" ]]; then
    "${compose[@]}" down -v
  else
    "${compose[@]}" down
  fi
  echo "Nedstängd."
  exit 0
fi

# up
[[ -f .env ]] || cp .env.example .env

"${compose[@]}" up -d --build
"${compose[@]}" exec app alembic upgrade head

if [[ "$MODE" == "test" ]]; then
  "${compose[@]}" exec app python -m scripts.seed
fi

echo
echo "Frontend: http://localhost:5173"
echo "API:      http://localhost:8000/api/v1/health"
