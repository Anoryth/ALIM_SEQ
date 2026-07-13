#!/usr/bin/env bash
# =====================================================================
#  Déclenche un build de l'installateur ALIM_SEQ sur la CI Forgejo auto-
#  hébergée, en allumant la VM Windows le TEMPS DU BUILD puis en l'éteignant.
#
#  Usage :   tools/lab-build.sh <tag>            (ex : tools/lab-build.sh v1.0.0)
#
#  Ce que ça fait, sans intervention :
#    1. démarre la VM Windows (docker compose up -d windows) ;
#    2. attend que le runner soit en ligne (boot Windows ~1–2 min) ;
#    3. pose/force le tag sur HEAD et le pousse sur le remote 'lab' -> build ;
#    4. suit le build jusqu'à succès/échec ;
#    5. récupère ALIM_SEQ-Setup.exe / ALIM_SEQ.exe dans ./dist-lab/ ;
#    6. éteint la VM Windows (Forgejo, lui, reste toujours disponible).
#
#  Prérequis : accès SSH par clé au serveur, remote git 'lab' configuré, et des
#  identifiants git en cache pour le push (voir docs/TOOLCHAIN.md).
#  Config : l'hôte SSH réel du build-box vit dans un fichier NON VERSIONNÉ
#  tools/lab.env (ex : LAB_SSH=user@host), lu automatiquement ci-dessous ; il peut
#  aussi être passé en variable d'environnement. LAB_REMOTE : défaut 'lab'.
# =====================================================================
set -euo pipefail

# Config locale non versionnée (garde toute adresse interne hors du dépôt public).
SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
[ -f "$SELF_DIR/lab.env" ] && . "$SELF_DIR/lab.env"

TAG="${1:?Usage: tools/lab-build.sh <tag>   (ex : tools/lab-build.sh v1.0.0)}"
SRV="${LAB_SSH:?Définir LAB_SSH (ex: dans tools/lab.env -> LAB_SSH=user@host)}"
REMOTE="${LAB_REMOTE:-lab}"
CI=(ssh -o ConnectTimeout=10 -o ServerAliveInterval=15 -o ServerAliveCountMax=3 "$SRV" bash winvm/ci.sh)

say(){ printf '\n\033[1;36m== %s ==\033[0m\n' "$*"; }
cleanup_stop(){ say "Extinction de la VM Windows"; "${CI[@]}" stop || true; }
# Interrogations tolérantes : un blip SSH / verrou DB transitoire ne doit JAMAIS
# faire tomber le script (sinon le trap éteindrait la VM en plein build).
ci(){ "${CI[@]}" "$@" 2>/dev/null || true; }

say "1/6  Démarrage de la VM Windows"
"${CI[@]}" start

# À partir d'ici, on éteint la VM quoi qu'il arrive (succès, échec, Ctrl-C).
trap cleanup_stop EXIT

say "2/6  Attente du runner en ligne (boot Windows ~1–2 min)"
# Polling CÔTÉ CLIENT (petits appels SSH courts + tolérants) : une coupure VPN
# n'affecte qu'une itération, pas toute l'attente.
online=0
for _ in $(seq 1 90); do
  age=$(ci runner-age); age=${age:-999999}
  if [ "$age" -le 60 ] 2>/dev/null; then online=1; echo "  runner en ligne"; break; fi
  sleep 8
done
[ "$online" = 1 ] || { echo "!! Runner non détecté à temps — arrêt."; exit 1; }

prev=$(ci last-run); prev=${prev:-0}

say "3/6  Poussée du tag $TAG (déclenche le build)"
git tag -f "$TAG" >/dev/null
git push -f "$REMOTE" "$TAG"

say "4/6  Attente de la création du build"
cur="$prev"
for _ in $(seq 1 20); do
  cur=$(ci last-run); cur=${cur:-0}
  [ "$cur" -gt "$prev" ] && break
  sleep 3
done
[ "$cur" -gt "$prev" ] || { echo "!! Build non créé (workflow absent pour ce tag ?)"; exit 1; }

say "5/6  Build #$cur en cours"
ok=0
while :; do
  st=$(ci run-status "$cur")            # peut être vide (verrou/ssh) -> on reboucle
  case "$st" in
    1)     echo "  ✅ build réussi"; ok=1; break ;;   # 1 = success
    2|3|7) echo "  ❌ build en échec (status=$st)"; ok=0; break ;;  # 2 fail / 3 cancel / 7 blocked
    *)     printf '.'; sleep 15 ;;                    # vide / 5 waiting / 6 running
  esac
done

if [ "$ok" = 1 ]; then
  say "6/6  Récupération de l'installateur -> ./dist-lab/"
  mkdir -p dist-lab
  scp "$SRV:winvm/shared/ALIM_SEQ-Setup.exe" "$SRV:winvm/shared/ALIM_SEQ-portable.zip" dist-lab/
  ls -lh dist-lab/ALIM_SEQ-Setup.exe dist-lab/ALIM_SEQ-portable.zip
fi

# le trap EXIT éteint la VM
[ "$ok" = 1 ]
