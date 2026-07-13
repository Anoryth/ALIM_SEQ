# Toolchain — construire les exécutables Windows

Ce document explique comment produire l'**installateur Windows signé** (`ALIM_SEQ-Setup.exe`)
et l'**exe portable** (`ALIM_SEQ.exe`) via la CI auto-hébergée, **sans PC Windows** :
la compilation se fait dans une VM Windows sur le serveur, pilotée par une forge
Forgejo (équivalent GitHub Actions, 100 % local).

> **Note** — Les adresses (`buildbox.lan`), l'utilisateur (`user`) et le port
> sont des **exemples** : ce dépôt public ne contient aucune adresse interne.
> Renseignez votre hôte réel dans un fichier **non versionné** `tools/lab.env`
> (voir *Prérequis* ci-dessous). GitHub-hosted ? Un workflow prêt à l'emploi
> existe déjà : [.github/workflows/windows-build.yml](../.github/workflows/windows-build.yml).

## En bref

```bash
# depuis le dépôt, sur ton poste :
tools/lab-build.sh v1.0.0
```

Cette unique commande : **allume la VM Windows**, déclenche le build du tag,
attend la fin, dépose `ALIM_SEQ-Setup.exe` + `ALIM_SEQ.exe` dans `./dist-lab/`,
puis **éteint la VM**. La VM n'est allumée **que** le temps du build.

## Architecture de la toolchain

```
Poste dev ──(git push tag v*)──▶ Forgejo (serveur, port 3000, toujours actif)
                                      │  déclenche .forgejo/workflows/build.yml
                                      ▼
                              VM Windows (dockur, ALLUMÉE À LA DEMANDE)
                              runner Forgejo (session Docker) :
                                pip → PyInstaller → Inno Setup
                                dépose les .exe dans \\host.lan\Data
                                        (= ~/winvm/shared côté serveur)
```

- **Serveur** : `user@buildbox.lan`, dossier `~/winvm` (docker compose).
  - `forgejo` : la forge + le serveur d'actions. **`restart: always`** → toujours
    disponible (léger).
  - `windows` (conteneur `alim-builder`) : la VM Windows 11 (dockur) qui exécute
    le build. **`restart: "no"`** → **éteinte par défaut**, démarrée à la demande.
- **Dépôt lab** : `http://buildbox.lan:3000/user/ALIM_SEQ.git` (remote git `lab`).
- **Workflow** : [.forgejo/workflows/build.yml](../.forgejo/workflows/build.yml),
  déclenché par tout tag `v*`.

## La VM « à la demande »

La VM Windows consomme CPU/RAM en continu si on la laisse tournée ; elle est donc
**arrêtée par défaut** (`restart: "no"` dans `docker-compose.yml`). Conséquences :

- un `git push lab v*` **sans VM allumée** met le build en file d'attente : il ne
  démarrera qu'une fois la VM en ligne ;
- `tools/lab-build.sh` gère l'allumage/extinction automatiquement — **c'est la
  voie recommandée** ;
- pour piloter à la main, voir « Méthode manuelle » ci-dessous.

Un helper serveur `~/winvm/ci.sh` encapsule les opérations (démarrage, attente du
runner, statut, arrêt) ; `tools/lab-build.sh` l'appelle par SSH.

## Prérequis (à faire une fois)

1. **Fichier de config local** `tools/lab.env` (non versionné, ignoré par git),
   renseignant l'hôte SSH réel de votre build-box :
   ```bash
   echo 'LAB_SSH=user@votre-hote' > tools/lab.env
   ```
   `tools/lab-build.sh` le lit automatiquement au démarrage.
2. **Accès SSH par clé** au serveur : `ssh $LAB_SSH` doit passer sans mot de passe.
3. **Remote git `lab`** :
   ```bash
   git remote add lab http://buildbox.lan:3000/user/ALIM_SEQ.git   # si absent
   ```
4. **Identifiants git en cache** pour pousser sans invite. Au choix :
   ```bash
   # option simple : store repo-local (déjà configuré sur ce poste)
   git config credential.helper 'store --file=.git/lab-credentials'
   # puis un premier push renseigne le mot de passe, ou pré-remplir le fichier :
   #   http://user:MOT_DE_PASSE@buildbox.lan:3000
   ```
   Le mot de passe est celui du compte Forgejo.

## Utilisation

```bash
tools/lab-build.sh v1.0.0            # build de HEAD taggé v1.0.0
LAB_SSH=user@autre-hote tools/lab-build.sh v1.0.1   # surcharge de l'hôte si besoin
```

Le tag est (re)posé sur `HEAD` puis poussé en force sur `lab` — pratique pour
re-déclencher un build. Résultat dans `./dist-lab/` (ignoré par git).

## Méthode manuelle (sans le script)

```bash
# 1. allumer la VM et attendre ~1–2 min qu'elle boote
ssh user@buildbox.lan 'cd ~/winvm && docker compose up -d windows'
ssh user@buildbox.lan 'bash winvm/ci.sh wait-runner'      # attend le runner

# 2. déclencher le build
git push lab v1.0.0                                   # (ou git tag + push)

# 3. suivre : http://buildbox.lan:3000/user/ALIM_SEQ/actions

# 4. récupérer les binaires (aussi dispo dans la VM sous \\host.lan\Data)
scp user@buildbox.lan:winvm/shared/ALIM_SEQ-Setup.exe .

# 5. éteindre la VM
ssh user@buildbox.lan 'cd ~/winvm && docker compose stop windows'
```

## Où sortent les binaires

- `./dist-lab/` sur le poste (via `tools/lab-build.sh`) ;
- **dans la VM** : `\\host.lan\Data` (= `~/winvm/shared` côté serveur), déposés
  automatiquement par le workflow — pratique pour **tester l'installateur dans la
  VM** (viewer web `http://buildbox.lan:8006`, dossier « Data » sur le bureau) ;
- **artefacts Forgejo** : onglet **Actions** du dépôt → le run → *Artifacts*
  (`ALIM_SEQ-Setup`, `ALIM_SEQ-portable`).

## Accès utiles

| Service | URL / commande |
|---|---|
| Forgejo (forge + Actions) | http://buildbox.lan:3000 (compte `user`) |
| Écran de la VM (viewer web) | http://buildbox.lan:8006 |
| RDP vers la VM (debug) | `buildbox.lan:3389` (utilisateur `Docker`) |
| Runners | Forgejo → *Administration du site → Actions → Runners* (`winbuilder`) |

## Dépannage

| Symptôme | Piste |
|---|---|
| Le build reste en file d'attente | La VM n'est pas allumée / le runner pas encore en ligne. Utiliser `tools/lab-build.sh` ou `docker compose up -d windows` puis `ci.sh wait-runner`. |
| `wait-runner` expire | La VM met plus longtemps à booter, ou le runner ne s'est pas relancé. Vérifier `http://buildbox.lan:8006` ; le runner démarre via le Démarrage commun de l'utilisateur `Docker`. |
| Le build échoue à la signature | La signature a été retirée du workflow ; si réintroduite, voir le secret `SIGN_PFX_PASSWORD` (Forgejo → dépôt → *Settings → Actions → Secrets*). |
| `git push lab` demande un mot de passe | Cache d'identifiants non configuré (voir Prérequis §4). |

Détails de conception (pourquoi runner en session `Docker`, cross-compilation du
runner, etc.) : voir la mémoire projet et l'historique git.
