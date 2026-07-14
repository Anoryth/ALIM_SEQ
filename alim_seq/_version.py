# Version de référence, suivie par git (source de vérité pour les exécutions
# depuis les sources et le repli d'__init__.py). En CI, ce fichier est réécrit
# depuis le tag git au build (voir .forgejo/workflows/build.yml) — même valeur
# pour un tag v1.1.0. À bumper à chaque release.
__version__ = "1.3.1"
