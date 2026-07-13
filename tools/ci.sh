#!/usr/bin/env bash
# Helper CI côté serveur — VM Windows "à la demande".
# Appelé par tools/lab-build.sh (dépôt) via ssh. Voir docs/TOOLCHAIN.md.
set -euo pipefail
cd "$(dirname "$0")"                       # ~/winvm
DB='/data/gitea/gitea.db'
# busy-timeout : Forgejo écrit dans la base pendant les builds ; on ATTEND le
# verrou (jusqu'à 8 s) au lieu d'échouer sur "database is locked". || true : une
# requête ratée renvoie du vide sans faire tomber le script (le polling continue).
q(){ docker exec forgejo sqlite3 -cmd '.timeout 8000' "$DB" "$1" 2>/dev/null || true; }

case "${1:-}" in
  start)  docker compose up -d windows >/dev/null; echo started ;;
  stop)   docker compose stop windows  >/dev/null; echo stopped ;;
  status) docker inspect -f '{{.State.Running}}' alim-builder 2>/dev/null || echo false ;;
  wait-runner)                            # attend le runner en ligne (< 60 s de heartbeat)
    for _ in $(seq 1 60); do
      lo=$(q "SELECT COALESCE(last_online,0) FROM action_runner WHERE name='winbuilder';")
      now=$(date +%s)
      if [ "${lo:-0}" -gt 0 ] 2>/dev/null && [ $((now-lo)) -le 60 ]; then echo online; exit 0; fi
      sleep 10
    done
    echo timeout; exit 1 ;;
  runner-age) # âge (s) du dernier heartbeat ; grand nombre si runner absent. Un
    # appel COURT (le polling long se fait côté client, robuste aux coupures SSH).
    lo=$(q "SELECT COALESCE(last_online,0) FROM action_runner WHERE name='winbuilder';")
    if [ "${lo:-0}" -gt 0 ] 2>/dev/null; then echo $(( $(date +%s) - lo )); else echo 999999; fi ;;
  last-run)   r=$(q "SELECT COALESCE(MAX(id),0) FROM action_run;"); echo "${r:-0}" ;;
  run-status) r=$(q "SELECT COALESCE(status,0) FROM action_run WHERE id=${2:?id manquant};"); echo "${r:-}" ;;
  *) echo "usage: ci.sh {start|stop|status|wait-runner|last-run|run-status <id>}" >&2; exit 2 ;;
esac
