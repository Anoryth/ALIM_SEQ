#!/usr/bin/env bash
# =====================================================================
#  Triggers a build of the ALIM_SEQ installer on the self-hosted Forgejo CI,
#  powering the Windows VM ON FOR THE BUILD then switching it off.
#
#  Usage:   tools/lab-build.sh <tag>            (e.g. tools/lab-build.sh v1.0.0)
#
#  What it does, hands-free:
#    1. starts the Windows VM (docker compose up -d windows);
#    2. waits for the runner to be online (Windows boot ~1–2 min);
#    3. sets/forces the tag on HEAD and pushes it to the 'lab' remote -> build;
#    4. follows the build to success/failure;
#    5. fetches ALIM_SEQ-Setup.exe / ALIM_SEQ.exe into ./dist-lab/;
#    6. switches off the Windows VM (Forgejo itself stays always available).
#
#  Prerequisites: key-based SSH access to the server, git remote 'lab' configured,
#  and cached git credentials for the push. Config: the real SSH host of the
#  build-box lives in an UNVERSIONED tools/lab.env file (e.g. LAB_SSH=user@host),
#  read automatically below; it can also be passed as an environment variable.
#  LAB_REMOTE: default 'lab'.
# =====================================================================
set -euo pipefail

# Unversioned local config (keeps any internal address out of the public repo).
SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
[ -f "$SELF_DIR/lab.env" ] && . "$SELF_DIR/lab.env"

TAG="${1:?Usage: tools/lab-build.sh <tag>   (e.g. tools/lab-build.sh v1.0.0)}"
SRV="${LAB_SSH:?Set LAB_SSH (e.g. in tools/lab.env -> LAB_SSH=user@host)}"
REMOTE="${LAB_REMOTE:-lab}"
CI=(ssh -o ConnectTimeout=10 -o ServerAliveInterval=15 -o ServerAliveCountMax=3 "$SRV" bash winvm/ci.sh)

say(){ printf '\n\033[1;36m== %s ==\033[0m\n' "$*"; }
cleanup_stop(){ say "Switching off the Windows VM"; "${CI[@]}" stop || true; }
# Tolerant queries: an SSH blip / transient DB lock must NEVER bring down the
# script (otherwise the trap would switch off the VM mid-build).
ci(){ "${CI[@]}" "$@" 2>/dev/null || true; }

say "1/6  Starting the Windows VM"
"${CI[@]}" start

# From here on, we switch off the VM whatever happens (success, failure, Ctrl-C).
trap cleanup_stop EXIT

say "2/6  Waiting for the runner online (Windows boot ~1–2 min)"
# CLIENT-SIDE polling (small, short and tolerant SSH calls): a VPN drop only
# affects one iteration, not the whole wait.
online=0
for _ in $(seq 1 90); do
  age=$(ci runner-age); age=${age:-999999}
  if [ "$age" -le 60 ] 2>/dev/null; then online=1; echo "  runner online"; break; fi
  sleep 8
done
[ "$online" = 1 ] || { echo "!! Runner not detected in time — aborting."; exit 1; }

prev=$(ci last-run); prev=${prev:-0}

say "3/6  Pushing tag $TAG (triggers the build)"
git tag -f "$TAG" >/dev/null
git push -f "$REMOTE" "$TAG"

say "4/6  Waiting for the build to be created"
cur="$prev"
for _ in $(seq 1 20); do
  cur=$(ci last-run); cur=${cur:-0}
  [ "$cur" -gt "$prev" ] && break
  sleep 3
done
[ "$cur" -gt "$prev" ] || { echo "!! Build not created (no workflow for this tag?)"; exit 1; }

say "5/6  Build #$cur in progress"
ok=0
while :; do
  st=$(ci run-status "$cur")            # may be empty (lock/ssh) -> we loop again
  case "$st" in
    1)     echo "  ✅ build succeeded"; ok=1; break ;;   # 1 = success
    2|3|7) echo "  ❌ build failed (status=$st)"; ok=0; break ;;  # 2 fail / 3 cancel / 7 blocked
    *)     printf '.'; sleep 15 ;;                    # empty / 5 waiting / 6 running
  esac
done

if [ "$ok" = 1 ]; then
  say "6/6  Fetching the installer -> ./dist-lab/"
  mkdir -p dist-lab
  scp "$SRV:winvm/shared/ALIM_SEQ-Setup.exe" "$SRV:winvm/shared/ALIM_SEQ-portable.zip" dist-lab/
  ls -lh dist-lab/ALIM_SEQ-Setup.exe dist-lab/ALIM_SEQ-portable.zip
fi

# the EXIT trap switches off the VM
[ "$ok" = 1 ]
