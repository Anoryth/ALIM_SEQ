#!/usr/bin/env bash
# Server-side CI helper — "on-demand" Windows VM.
# Called by tools/lab-build.sh (repo) over ssh. See the internal toolchain doc.
set -euo pipefail
cd "$(dirname "$0")"                       # ~/winvm
DB='/data/gitea/gitea.db'
# busy-timeout: Forgejo writes to the database during builds; we WAIT for the lock
# (up to 8 s) instead of failing on "database is locked". || true: a failed query
# returns empty without bringing down the script (polling continues).
q(){ docker exec forgejo sqlite3 -cmd '.timeout 8000' "$DB" "$1" 2>/dev/null || true; }

case "${1:-}" in
  start)  docker compose up -d windows >/dev/null; echo started ;;
  stop)   docker compose stop windows  >/dev/null; echo stopped ;;
  status) docker inspect -f '{{.State.Running}}' alim-builder 2>/dev/null || echo false ;;
  wait-runner)                            # wait for the runner online (< 60 s heartbeat)
    for _ in $(seq 1 60); do
      lo=$(q "SELECT COALESCE(last_online,0) FROM action_runner WHERE name='winbuilder';")
      now=$(date +%s)
      if [ "${lo:-0}" -gt 0 ] 2>/dev/null && [ $((now-lo)) -le 60 ]; then echo online; exit 0; fi
      sleep 10
    done
    echo timeout; exit 1 ;;
  runner-age) # age (s) of the last heartbeat; large number if the runner is absent. A
    # SHORT call (the long polling happens client-side, robust to SSH drops).
    lo=$(q "SELECT COALESCE(last_online,0) FROM action_runner WHERE name='winbuilder';")
    if [ "${lo:-0}" -gt 0 ] 2>/dev/null; then echo $(( $(date +%s) - lo )); else echo 999999; fi ;;
  last-run)   r=$(q "SELECT COALESCE(MAX(id),0) FROM action_run;"); echo "${r:-0}" ;;
  run-status) r=$(q "SELECT COALESCE(status,0) FROM action_run WHERE id=${2:?missing id};"); echo "${r:-}" ;;
  *) echo "usage: ci.sh {start|stop|status|wait-runner|last-run|run-status <id>}" >&2; exit 2 ;;
esac
