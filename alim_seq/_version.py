# Version de référence, suivie par git (source de vérité pour les exécutions
# depuis les sources et le repli d'__init__.py). En CI, un build de TAG réécrit ce
# fichier depuis le tag git (workflows GitHub et Forgejo) ; un build manuel
# conserve cette valeur. À bumper à chaque release.
__version__ = "1.3.2"
