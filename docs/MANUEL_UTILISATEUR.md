---
title: "ALIM_SEQ — Manuel utilisateur"
subtitle: "Séquenceur d'alimentation R&S HMP4040 avec surveillance thermique"
lang: fr-FR
---

## 1. Présentation

ALIM_SEQ pilote une ou plusieurs alimentations de laboratoire Rohde & Schwarz
(HMP4040, HMP4030, HMP2030, HMP2020) et surveille en continu des températures
mesurées par un module d'acquisition National Instruments. Il permet :

- le **pilotage manuel** des voies (tension, limite de courant, marche/arrêt) ;
- l'exécution de **séquences automatiques** écrites dans un langage simple
  (rampes, asservissements en courant, attentes conditionnelles, boucles) ;
- une **surveillance thermique de sécurité** : en cas de dépassement d'un seuil
  critique, l'application désalimente la carte sous test de façon ordonnée, avec
  une coupure brutale en dernier recours ;
- l'**enregistrement** des mesures (tensions, courants, températures) au format CSV,
  et la génération d'un **rapport d'essai PDF**.

L'application fonctionne dans deux modes, signalés en permanence par un badge :

| Badge | Signification |
|---|---|
| **SIMULATION** (bleu) | Aucun matériel n'est piloté. Les alimentations et les capteurs sont simulés (avec un modèle thermique). Mode recommandé pour se former, mettre au point les séquences et la configuration. |
| **MATÉRIEL RÉEL** (orange) | Les ordres sont envoyés aux vraies alimentations.|

Le mode est déterminé par la clé `simulate` du fichier de configuration (§9).
**À l'installation, l'application démarre en simulation** : aucun matériel n'est
requis pour la découvrir.

## 2. Consignes de sécurité

> ⚠ **À lire avant toute utilisation sur matériel réel.**

- **Vérifier la configuration avant chaque campagne d'essai** : limites de tension et
  de courant de chaque voie (`V max`, `I max`), seuils d'alerte et critiques des
  capteurs. L'application refuse toute consigne au-delà de ces limites, mais c'est
  la configuration qui fait autorité — une limite mal renseignée ne protège rien.
- **Le bouton ARRÊT D'URGENCE** est visible en permanence, sur tous les onglets.
  Il coupe **immédiatement et brutalement** toutes les voies, sans confirmation, y
  compris pendant une séquence. Raccourci : `Ctrl+Maj+X`.
- **La désalimentation de sécurité n'est pas interruptible.** Si un seuil critique
  est atteint, la séquence de désalimentation s'exécute jusqu'au bout ; le bouton
  « Stop séquence » est ignoré pendant cette phase.
- Après tout incident de sécurité, l'application passe en état **verrouillé
  (« trip »)** : aucune voie ne peut être rallumée avant un **Réarmement**
  volontaire (§8.3). Identifier et corriger la cause avant de réarmer.
- L'application est une aide, pas une protection certifiée : elle ne remplace ni les
  protections matérielles (OVP/fusibles des alimentations), ni la surveillance
  humaine d'un essai à risque.

## 3. Installation et lancement

### 3.1 Version installée (Windows)

Installer ALIM_SEQ avec `ALIM_SEQ-Setup.exe`, puis lancer l'application depuis le
menu Démarrer ou le raccourci créé. Au premier lancement, l'application crée son
**dossier de données** — celui que vous avez choisi pendant l'installation
(par défaut `Documents\ALIM_SEQ`) — et y dépose une configuration et une séquence
d'exemple. **C'est dans ce dossier** que se trouvent :

```
<dossier de données choisi à l'installation>\
├── config.json     # la configuration (éditable depuis l'appli)
├── sequences\       # vos séquences .seq
└── logs\            # journal applicatif et dossiers d'essai (mesures, rapports)
```

Ainsi la configuration éditée, les journaux et les essais **persistent** même si
l'application est installée en lecture seule (Program Files). Une version
**portable** (`ALIM_SEQ.exe`, sans installation) existe aussi ; elle range ses
données dans `Documents\ALIM_SEQ`.

### 3.2 Depuis les sources (Python)

Prérequis : Python 3.10+, puis `pip install pyvisa PySide6` (et `nidaqmx` pour
l'acquisition NI en mode réel ; inutile en simulation).

```
python main.py [options]

  --config CHEMIN   Fichier de configuration (défaut : config.json)
```

Exemples :

```
python main.py
python main.py --config banc_A.json
```

L'interface est **Qt** (PySide6) ; c'est l'unique IHM de l'application.

### 3.3 Raccordement des instruments (mode réel)

- **Alimentation HMP — liaison recommandée : LAN en mode socket**, adresse VISA de
  la forme `TCPIP0::192.168.0.11::5025::SOCKET` (robuste et rapide).
- **USB : régler l'alimentation en mode TMC, jamais CDC** (menu de l'alimentation).
  Le mode CDC/port série virtuel est très lent et provoque des désynchronisations.
  Adresse de la forme `USB0::0x0AAD::0x…::<numéro de série>::INSTR`.
- Si l'alimentation renvoie des erreurs « input protocol violation », renseigner
  `visa_query_delay: 0.02` à la racine du fichier de configuration.
- Le bouton **Scanner** de l'onglet Configuration liste les instruments VISA
  détectés et leur identification ; **Tester la connexion** valide une adresse.

> **⚠ Sécurité réseau — banc isolé obligatoire.** Le protocole SCPI/TCPIP est
> **sans authentification** : n'importe quel hôte du réseau peut ouvrir une session
> et **piloter les alimentations en parallèle** de l'application (changer une
> consigne, allumer une voie), ce qui invalide les hypothèses de sûreté du logiciel.
> Raccorder les instruments sur un **réseau de banc isolé** (VLAN ou segment dédié,
> sans passerelle vers le réseau bureautique/Internet). Ne jamais exposer une
> alimentation de puissance sur un réseau ouvert.

## 4. Découverte de l'interface

De haut en bas :

1. **Bannière de sécurité** — état global en couleur : OK (vert), ALERTE (jaune),
   CRITIQUE (rouge), DÉFAUT capteur (violet). Affiche le capteur en cause et
   l'action en cours (désalimentation…).
2. **Barre de commandes vitales** — visible sur tous les onglets :
   **ARRÊT D'URGENCE**, **Séquentiel d'arrêt** (désalimentation ordonnée
   manuelle), **Réarmer**, **Tout OFF**, et le **badge de mode**
   SIMULATION / MATÉRIEL RÉEL. Le bouton Réarmer devient orange lorsqu'un
   réarmement est nécessaire.
3. **Onglets** :
   - **Contrôle** — pilotage manuel, températures, lancement de séquence,
     enregistrement ;
   - **Configuration** — édition du fichier de configuration (§9) ;
   - **Éditeur de séquence** — écriture, vérification et exécution des `.seq` ;
   - **Graphe** — courbes de températures, courants et tensions.
4. **Barre d'état** — pastille de connexion, fichier de configuration courant,
   cadence de mesure réelle, puissance totale débitée, indicateur REC pendant
   un enregistrement.

## 5. Prise en main rapide

*En simulation (`"simulate": true`), aucun matériel requis. La configuration
livrée par défaut définit deux voies génériques `CH1` et `CH2`.*

1. Lancer l'application (ou `python main.py`). Vérifier le badge
   **SIMULATION** (bleu).
2. Onglet **Contrôle** : sur la voie `CH1`, saisir une tension dans le champ
   « V consigne » (la molette est volontairement inactive — saisir au clavier ou
   avec les flèches). Le champ prend un fond jaune : la consigne saisie n'est pas
   encore appliquée.
3. Cliquer **Appliquer** (ou appuyer sur `Entrée` dans le champ). Le fond jaune
   disparaît.
4. Cliquer **OFF** — le bouton passe à **ON** (vert) : la voie débite. Les colonnes
   « V mesurée / I mesurée » s'animent.
5. Onglet **Éditeur de séquence** : ouvrir `sequences/exemple.seq`, cliquer
   **Vérifier** (contrôle complet de la syntaxe, des voies et des valeurs), puis
   **Exécuter**. Suivre la progression (barre de progression, ligne courante
   surlignée dans l'éditeur).
6. Tester le bouton **ARRÊT D'URGENCE** : toutes les voies tombent, l'état passe
   en « trip ». Cliquer **Réarmer** pour rendre la main.

## 6. Pilotage manuel des voies

### 6.1 Tableau des voies

Chaque ligne présente : le libellé de la voie, la consigne de tension, la limite de
courant, le bouton **Appliquer**, le bouton de sortie **ON/OFF**, les mesures
(V, I) et le **mode** de régulation :

- **CV** (vert) : régulation en tension — fonctionnement normal ;
- **CC** (rouge) : la voie est en **limitation de courant** — la charge demande plus
  que la limite fixée. Vérifier le montage ou la limite ;
- une mention violette signale un défaut matériel de l'alimentation
  (OVP, fusible, surchauffe).

Les champs de consigne sont **bornés par la configuration** : il est impossible de
saisir une valeur au-delà de `V max` / `I max` de la voie. La virgule et le point
décimal sont acceptés.

**Fond jaune = consigne saisie mais non appliquée.** L'application n'écrase jamais
une saisie en cours ; cliquer **Appliquer** (ou `Entrée`) pour transmettre.

**Allumage en deux temps (matériel réel).** Pour éviter un allumage accidentel, en
mode réel le **1ᵉʳ clic** sur ON affiche **« ⚠ Armer ? »** ; un **2ᵉ clic** (sous
3 s) allume réellement. En simulation l'allumage est direct. `Maj+clic` force
l'allumage immédiat même en réel. L'extinction est toujours immédiate.

**⏱ figé = mesure périmée.** Si l'instrument d'une voie ne répond plus (liaison
figée), ses **V/I mesurés sont grisés** et le mode affiche **« ⏱ figé »** : la valeur
montrée n'est plus rafraîchie (voir aussi la bannière en cas de perte de communication).

### 6.2 Voies en série (groupes)

Un **groupe** associe plusieurs voies câblées en **série** : la tension du groupe
est la somme des tensions des membres, le courant est commun. Câblage : borne « − »
de la première voie vers la borne « + » de la suivante ; la charge se branche entre
le « + » de la première et le « − » de la dernière (les sorties HMP sont isolées,
ce montage est autorisé).

Un groupe se pilote comme une voie, par son nom (dans l'IHM comme dans les
séquences). La répartition de la tension entre membres est configurable :
**équilibrée** (`equal`) ou **remplissage** (`fill`, la première voie à fond puis
la suivante). La colonne de droite rappelle la composition (ex. `= VD1 + VD2`).

*(La configuration livrée par défaut ne définit aucun groupe ; ils se déclarent au
besoin dans l'onglet Configuration, §9.4.)*

### 6.3 Températures

La zone Températures affiche chaque capteur avec sa valeur, colorée selon l'état :
vert (OK), jaune (≥ seuil d'alerte), rouge (≥ seuil critique), violet (**DÉFAUT** :
mesure hors plage plausible ou capteur débranché), gris (« en attente » : le capteur
n'est surveillé que lorsque ses voies associées sont allumées, voir `Voies
requises`, §9.5).

### 6.4 Relais

Si la configuration déclare des relais (§9.6), un cadre **Relais** apparaît : chaque
sortie affiche son état (ouvert/fermé) et un bouton **ON/OFF** pour la piloter à la
main. Les relais sont aussi pilotables en séquence (`RELAY <sortie> ON|OFF`, §7) et
sont ramenés à leur état de sécurité lors d'un arrêt. Fermer un relais est refusé
tant que la sécurité est armée.

### 6.5 Onglet Simulation (mode simulation uniquement)

En mode simulation, un onglet **🧪 Simulation** permet de régler **en direct** le
comportement du banc virtuel, pour reproduire fidèlement ton montage sans matériel.
L'effet est immédiat dans l'onglet *Contrôle* :

- **Charges résistives** par voie (Ω) : fixent la relation I = V/R (donc le courant
  mesuré, et le passage en limitation de courant).
- **Modèle thermique** : température ambiante, gain (°C par watt dissipé), constante
  de temps τ (rapidité de montée) et bruit de mesure — pour éprouver la surveillance
  et les seuils de sécurité.
- **Couplages entre voies (grille → drain)** : ajoute/retire des couplages où la
  tension d'une voie *grille* pilote le courant tiré sur des voies *drain*
  (`Id = gm·(Vg − vth)`, borné à `imax`) — pour tester l'asservissement (SERVO). Sans
  couplage, chaque voie est une simple charge résistive.

Ces réglages ne concernent que la simulation et sont appliqués immédiatement ; ils
n'affectent jamais le matériel réel.

## 7. Séquences automatiques

### 7.1 Principe

Une séquence est un fichier texte `.seq` : **une action par ligne**, exécutée de
haut en bas. Lignes vides et commentaires (`#` ou `//`) ignorés. Les mots-clés sont
insensibles à la casse ; les noms de voies et de capteurs respectent la casse de la
configuration. La référence complète des commandes est en **Annexe A** (également
accessible dans l'application : menu Aide → Référence des commandes).

Exemple commenté (illustratif — adaptez les noms de voies/capteurs à votre
configuration) :

```
# Mise sous tension progressive
SET CH1 20 1.0           # consigne 20 V, limite 1 A
ON CH1
RAMP CH1 0 20 5 50       # rampe 0 → 20 V en 5 s, 50 pas
WAIT 1
SERVO_ADAPT CH2 CH1 0.500 step=0.5 tol=0.005 timeout=30
LOG Point de polarisation atteint
WAIT_TEMP T1 < 60 timeout=120
ALL_OFF
```

### 7.2 Éditeur intégré

L'onglet **Éditeur de séquence** offre : coloration syntaxique (les noms de voies
**inconnus restent neutres** — les fautes de frappe sautent aux yeux),
auto-complétion des commandes, voies et capteurs, aide-mémoire cliquable (insère la
commande au curseur), et affichage de la durée estimée au chargement.

**Toujours cliquer « Vérifier » avant d'exécuter** : la vérification contrôle la
syntaxe, l'existence des voies/capteurs, la validité **numérique** de tous les
arguments et les mots-clés des servos. Une séquence vérifiée ne s'arrêtera pas en
cours de route pour une erreur d'écriture.

### 7.3 Exécution, pause, pas-à-pas

- **Exécuter** lance la séquence dans un fil dédié : l'interface reste disponible
  (surveillance, graphe, arrêt d'urgence).
- La **progression** s'affiche dans l'onglet
  Contrôle ; la ligne en cours est surlignée dans l'éditeur.
- **Pause / Reprendre** suspend la séquence entre deux actions.
- **Mode pas-à-pas** : cocher « Pas-à-pas » puis utiliser « Étape suivante » pour
  exécuter la séquence action par action — précieux pour la mise au point sur
  matériel réel. (Ce mode est sans effet sur une désalimentation de sécurité.)
- **Stop** interrompt proprement la séquence (les voies restent dans leur état
  courant). Pour tout couper : **Tout OFF** ou l'arrêt d'urgence.
- L'enregistrement CSV peut être démarré automatiquement avec la séquence (case
  « Enregistrer pendant la séquence »).

### 7.4 Expressions (SETV / SETI)

`SETV` et `SETI` acceptent une formule arithmétique :

```
SETV CH2 = (CH1/2) + 0.6
SETI CH1 = I(CH2) * 10
```

Dans une expression : un **nom de voie** vaut sa **consigne de tension** ;
fonctions disponibles : `V(x)` consigne de tension, `Vmeas(x)` tension mesurée,
`Iset(x)` limite de courant, `I(x)` courant mesuré. Opérateurs `+ - * /`,
parenthèses, et fonctions usuelles (`min`, `max`, `abs`). Aucun autre code n'est
évalué (langage volontairement restreint).

## 8. Sécurité thermique et gestion des incidents

### 8.1 Surveillance

La boucle de sécurité lit les températures à cadence rapide
(`temp_poll_interval`, 0,2 s par défaut), indépendamment de la boucle de mesure
V/I. Chaque capteur possède un seuil d'**alerte** et un seuil **critique**.

### 8.2 Réaction en cas de dépassement critique

1. **Désalimentation ordonnée** : l'application exécute la séquence d'arrêt —
   `sequences/shutdown.seq` si un tel fichier existe (ou celui désigné par
   `safety.shutdown_sequence`), sinon une extinction voie par voie générée
   automatiquement (dans l'ordre inverse de la configuration, avec une
   temporisation `shutdown_delay` entre voies). Cette phase est **prioritaire et
   non interruptible** : elle prend le pas sur la séquence utilisateur en cours et
   ignore le bouton Stop.
2. **Coupure dure de dernier recours** : si la température continue de monter et
   atteint `critique + hard_margin_c` (15 °C par défaut), ou si la désalimentation
   ordonnée échoue ou dépasse son budget de temps, **toutes les sorties sont
   coupées brutalement**.

La même désalimentation ordonnée peut être déclenchée manuellement à tout moment
par le bouton **Séquentiel d'arrêt**.

### 8.3 État « trip » et réarmement

Après un incident (critique, arrêt d'urgence, perte de communication selon la
configuration), l'application est **verrouillée** : toute tentative d'allumage est
refusée. Le bouton **Réarmer** (mis en évidence en orange) déverrouille, après
correction de la cause. Le journal (bas de l'onglet Contrôle, et fichier
`logs/alim_seq.log`) détaille la chronologie de l'incident.

### 8.4 Pertes de communication et défauts

- **Perte de l'alimentation** (après `comm_fail_limit` échecs consécutifs) :
  coupure de sécurité, puis tentatives de reconnexion automatiques. Les sorties ne
  sont **pas** rétablies après reconnexion.
- **Perte de la mesure de température** alors que des voies débitent :
  désalimentation ordonnée (paramétrable, `shutdown_on_temp_lost`).
- **Capteur en DÉFAUT** (valeur hors plage plausible, capteur débranché — un
  circuit ouvert est détecté, il n'apparaît jamais comme une température
  faussement basse) : signalé en violet ; désalimentation optionnelle
  (`shutdown_on_sensor_fault`).
- **Défaut matériel HMP** (OVP, fusible, surchauffe interne) : signalé sur la
  voie ; désalimentation optionnelle (`shutdown_on_hw_fault`).

## 9. Configuration

### 9.0 Assistant de configuration (démarrage rapide)

Au **premier lancement**, l'application propose un **assistant** (aussi disponible via
*Fichier → Assistant de configuration…*). Deux voies :

- **Configuration de simulation** : génère une config sans matériel (une HMP4040,
  voies CH1/CH2) — idéal pour découvrir l'application.
- **Scanner le matériel VISA** : détecte les alimentations branchées (USB-TMC, LAN
  VXI-11), propose de cocher celles à inclure (nom et modèle éditables) et **génère
  `supplies` + voies** pré-remplies.
- **Ajouter une adresse manuelle** : ⚠ le scan **ne découvre pas** les alimentations
  en **mode socket LAN** (`TCPIP0::IP::5025::SOCKET`, pourtant recommandé §3.3) — il
  n'y a rien à énumérer sans connaître l'IP. Saisissez alors l'adresse directement :
  elle est **testée** (`*IDN?`) puis ajoutée (ou ajoutée sans test, sur confirmation,
  pour préparer une config hors ligne).

La configuration générée est **chargée dans l'éditeur** (§9.2) pour revue : ajustez
les noms/limites/capteurs, puis **✓ Appliquer**. L'assistant ne pilote jamais le
matériel directement.

### 9.1 Fichiers de configuration (profils)

L'application fonctionne sur le modèle « document » :

- le **fichier courant** est affiché dans la barre d'état et dans l'onglet
  Configuration ;
- menu **Fichier → Charger une configuration** : bascule sur le profil choisi
  (l'ancien fichier n'est pas modifié) et reconnecte le matériel ;
- **Enregistrer** (onglet Configuration) écrit dans le fichier courant ;
- **Fichier → Enregistrer la configuration sous…** : enregistre l'état courant dans
  un nouveau fichier, qui devient le fichier de travail ;
- option **Rouvrir le dernier profil au démarrage** (menu), désactivée par défaut ;
  un `--config` explicite en ligne de commande reste prioritaire.

Un cas d'usage typique : un profil par banc ou par carte sous test
(`banc_A.json`, `carte_proto2.json`…).

### 9.2 Onglet Alimentations

Une ligne par alimentation : **Nom** (libre), **Modèle** (HMP4040, HMP4030,
HMP2030, HMP2020), **Adresse VISA** (§3.3). Les boutons **Scanner** et **Tester la
connexion** aident à trouver et valider l'adresse.

### 9.3 Onglet Voies

| Colonne | Rôle |
|---|---|
| Libellé | Nom d'usage de la voie (utilisé partout : IHM, séquences, expressions) |
| Alimentation / Canal | Voie physique (alimentation + numéro de sortie) |
| Rail négatif | Cocher si la voie alimente un rail négatif (affichage et bornes inversés) |
| V initiale / I initiale | Consignes appliquées à la connexion (sorties **éteintes**) |
| V max / I max | **Limites de sécurité** : bornes des saisies et plafond de toute consigne |

### 9.4 Onglet Groupes

Déclaration des voies en série (§6.2) : nom, voies membres, répartition
(équilibrée / remplissage), limites du groupe (0 = automatique : somme des V max,
minimum des I max).

### 9.5 Onglet Températures

| Colonne | Rôle |
|---|---|
| Nom | Nom du capteur |
| Voie NI | Entrée analogique du module NI (ex. `ai0`) |
| Seuil alerte / Seuil critique (°C) | Seuils de la surveillance (§8) |
| Voies requises | Le capteur n'est surveillé que si ces voies sont allumées (évite les fausses alertes carte hors tension) |
| T plausible min/max (°C) | Plage de vraisemblance : au-delà → **DÉFAUT** |
| Convertisseur | Conversion tension → °C (Annexe C). Double-clic ou bouton « Convertisseur… » : assistant graphique avec courbe de réponse |
| Voie de référence / V réf. attendue / Tolérance | Contrôle optionnel d'une tension de référence du conditionnement (pont diviseur…) : hors tolérance → DÉFAUT |
| Entrée NI min/max (V) | Calibre de l'entrée analogique |

Pour utiliser l'application **sans aucune mesure de température** (et sans le module
NI), laisser la section Températures **vide** : pas de boucle thermique, le module
NI n'est ni connecté ni interrogé. C'est le cas de la configuration livrée par
défaut.

### 9.6 Onglet Relais

Déclare des **relais / actionneurs** : chaque instrument expose des **sorties**
pilotables individuellement (par label).

| Colonne | Rôle |
|---|---|
| Instrument | Nom de l'instrument relais |
| Driver | Pilote ; seul `MOCK-RELAY` (relais simulé) existe pour l'instant |
| Sorties | Labels des sorties, séparés par des virgules (ex. `K1, K2`) |
| Fermées à l'arrêt | Sorties laissées **fermées** à l'état de sécurité (les autres sont ouvertes). Vide = toutes ouvertes |

Les sorties déclarées apparaissent dans un cadre **Relais** de l'onglet *Contrôle*
(état + bouton ON/OFF) et sont pilotables en séquence par `RELAY <sortie> ON|OFF`.
À l'arrêt d'urgence et en fin de désalimentation ordonnée, chaque sortie est ramenée
à son état de sécurité (ouvrir un relais isole la carte). Fermer un relais est refusé
tant que la sécurité est armée.

### 9.7 Onglet Avancé (JSON)

Édition libre du fichier complet, synchronisée avec les formulaires (l'onglet où
la modification est faite fait foi à l'enregistrement). Réservé aux clés qui n'ont
pas de formulaire : `safety` (Annexe B), `daq` (périphérique NI, cadence),
`simulation` (modèle thermique du mode simulation), `visa_query_delay`.

Le bouton **Vérifier** valide l'ensemble ; **Appliquer** enregistre puis
reconnecte le matériel avec la nouvelle configuration (impossible pendant une
séquence).

## 10. Graphe et enregistrement des mesures

### 10.1 Graphe

L'onglet **Graphe** trace, sur une fenêtre glissante : les **températures**, les
**courants** ou les **tensions** (sélecteur « Grandeur »). Fonctions : légende
cliquable (masquer/afficher une courbe), **curseur de lecture** au survol (valeur
de chaque courbe à l'instant pointé), marqueurs des événements de séquence,
export de l'image et des données.

### 10.2 Enregistrement CSV et dossier d'essai

Le bouton **Enregistrer** (ou `Ctrl+R`, ou la case « Enregistrer pendant la
séquence ») démarre un enregistrement. Un petit dialogue facultatif demande le
**nom de l'essai** et l'**opérateur**. L'indicateur **REC** est affiché dans la
barre d'état pendant l'enregistrement.

Chaque enregistrement crée un **dossier d'essai autonome** :

```
logs\essais\AAAAMMJJ_HHMMSS[_<nom>]\
├── mesures.csv    # horodatage, consignes et mesures (V, I) par voie, températures, état sécurité
├── config.json    # copie exacte de la configuration active
├── sequence.seq   # séquence exécutée (absent si pilotage manuel)
├── journal.log    # événements du contrôleur pendant l'essai
├── essai.json     # métadonnées : mode, horodatages, issue de l'essai…
├── rapport.html   # rapport régénérable
└── rapport.pdf
```

L'intérêt : un tiers peut **régénérer le rapport PDF depuis ce seul dossier**, sans
l'application ouverte sur l'essai, y compris des mois plus tard. Le `mesures.csv`
(une ligne par cycle de mesure, flushé en direct) s'ouvre dans un tableur ou se
traite en Python/MATLAB.

### 10.3 Rapport d'essai

Le rapport reprend un en-tête, une **synthèse** (issue en clair et en couleur —
rouge pour un déclenchement de sécurité), la **conclusion de l'opérateur** (champ
libre facultatif, rééditable), des **graphiques** (V/I et températures avec seuils),
des **statistiques** par voie et par capteur, la **chronologie** des événements et
des **annexes** (séquence et configuration). Le rapport **n'émet aucun verdict de
conformité** : la conclusion est celle de l'opérateur.

- **Fin d'enregistrement** : si l'option *Affichage → Générer le rapport en fin
  d'essai* est cochée (par défaut), la conclusion est proposée puis le rapport est
  généré.
- **Déclenchement de sécurité** avec essai en cours : le rapport est généré
  **automatiquement** dès la fin de la désalimentation.
- **Régénération à la demande** : *Fichier → Générer un rapport d'essai…* liste les
  dossiers de `logs\essais\` et régénère avec saisie/édition de la conclusion.
  *Aide → Où sont mes fichiers ?* ouvre `logs\essais\` dans l'explorateur.

### 10.4 Relecture d'un essai

*Fichier → Rouvrir un essai (relecture)…* rejoue un essai enregistré dans une fenêtre
dédiée : **courbes** de tout l'essai (bascule Températures / Courants / Tensions),
**curseur** de lecture des valeurs au survol, **repères d'événements** numérotés
(marqueurs 📌, alertes, sécurité), **légende cliquable** (masquer/afficher une courbe),
**export PNG** et bouton **Générer le rapport PDF**. Pratique pour analyser un essai
*a posteriori*.

*Fichier → Comparer deux essais…* **superpose** les courbes de deux essais (recalées
sur t = 0, séries préfixées `A·`/`B·`, une couleur par série) dans une même vue : idéal
pour visualiser une **dérive avant/après** modification de la carte. Bascule de
grandeur et export PNG comme en relecture.

## 11. Raccourcis clavier

| Raccourci | Action |
|---|---|
| `Ctrl+Maj+X` | Arrêt d'urgence |
| `Ctrl+Entrée` | Charger et exécuter la séquence de l'éditeur |
| `Ctrl+S` | Enregistrer la séquence |
| `Ctrl+O` | Ouvrir une séquence |
| `Ctrl+R` | Démarrer / arrêter l'enregistrement CSV |
| `Ctrl+M` | Poser un marqueur opérateur (note horodatée) |

(Liste également disponible dans l'application : menu Aide → Raccourcis clavier.)

## 12. Dépannage

| Symptôme | Cause probable / remède |
|---|---|
| « Échec de connexion » au démarrage | Vérifier l'adresse VISA (Scanner / Tester la connexion), le câble, que l'alimentation est en mode **TMC** si USB. L'IHM reste utilisable pendant les tentatives ; bouton **Reconnecter** après correction. |
| Mesures incohérentes / « input protocol violation » | Liaison USB en mode CDC (passer en TMC) ou dialogue trop rapide : renseigner `visa_query_delay: 0.02`. |
| Voie affichée **CC** en rouge | La charge demande plus que la limite de courant : vérifier le montage, la consigne ou la limite. |
| Capteur affiché **DÉFAUT** (violet) | Mesure hors plage plausible : capteur débranché, câblage, tension de référence hors tolérance. Vérifier le conditionnement ; le détail est dans le journal. |
| Impossible d'allumer une voie | État « trip » après incident : corriger la cause puis **Réarmer**. |
| Le bouton Stop ne répond pas pendant une désalimentation | Comportement normal : la désalimentation de sécurité n'est pas interruptible (§8.2). |
| « Arrêter la séquence d'abord. » | Le réarmement, la reconnexion et le changement de configuration sont bloqués pendant une séquence : l'arrêter au préalable. |
| Consigne impossible à saisir | La valeur dépasse `V max` / `I max` de la voie : la borne est volontaire (configuration, §9.3). |
| Fenêtre lente au démarrage en mode réel | La connexion s'établit en arrière-plan ; les commandes matérielles sont grisées pendant ce temps, l'arrêt d'urgence reste actif. |

En cas de problème non répertorié, joindre `logs\alim_seq.log` et le fichier de
configuration à tout signalement.

---

## Annexe A — Référence des commandes de séquence

Une action par ligne. `#` et `//` introduisent un commentaire. Mots-clés
insensibles à la casse ; libellés de voies/capteurs sensibles à la casse.
`<voie>` désigne une voie **ou un groupe**.

| Commande | Effet |
|---|---|
| `SET <voie> <V> [A]` | Consigne de tension (et de limite de courant) |
| `VOLTAGE <voie> <V>` | Consigne de tension seule |
| `CURRENT <voie> <A>` | Limite de courant seule |
| `SETV <voie> = <expression>` | Tension calculée par une formule (§7.4) |
| `SETI <voie> = <expression>` | Limite de courant calculée |
| `ON <voie>` / `OFF <voie>` | Allume / éteint la voie |
| `WAIT <s>` | Pause (interruptible) |
| `RAMP <voie> <v_fin> <durée_s>` | Rampe depuis la valeur **actuelle** jusqu'à `v_fin` |
| `RAMP <voie> <v_déb> <v_fin> <durée_s> [nb_pas]` | Rampe à départ explicite. `nb_pas` = **nombre de pas** (entier ≥ 2), pas une taille de pas |
| `SERVO_LIN <réglée> <mesurée> <I_cible_A> [clé=val …]` | Asservit la tension de la voie *réglée* jusqu'à atteindre le courant cible sur la voie *mesurée*, à **pas fixe**. `SERVO` = alias |
| `SERVO_ADAPT <réglée> <mesurée> <I_cible_A> [clé=val …]` | Idem à **pas adaptatif** (grand pas loin de la cible, fin près) ; `step` devient un plafond |
| `WAIT_CURRENT <voie> <op> <A> [timeout=<s>]` | Attend que le courant mesuré vérifie la condition. `op` ∈ `<  <=  >  >=  ==  !=` |
| `WAIT_TEMP <capteur> <op> <°C> [timeout=<s>]` | Attend une condition de température |
| `LOG <message…>` | Écrit un message dans le journal (et le CSV) |
| `ALL_OFF` | Éteint toutes les voies |
| `RELAY <sortie> ON\|OFF` | Ferme (ON) / ouvre (OFF) une sortie de relais |
| `SHUTDOWN` | Exécute la désalimentation ordonnée (§8.2) |
| `REPEAT <n>` … `END` | Répète *n* fois le bloc (imbrication autorisée) |

**Mots-clés des servos** : `step` (pas, V), `min` / `max` (bornes de tension, V),
`tol` (tolérance sur le courant, A), `timeout` (s), `settle` (temps de
stabilisation entre pas, s), `invert=1` (sens d'action inversé : le courant
diminue quand la tension monte), et `damping` (amortissement, `SERVO_ADAPT`
uniquement, défaut 0,7).

## Annexe B — Paramètres de sécurité (`safety` du fichier de configuration)

| Clé | Défaut | Rôle |
|---|---|---|
| `poll_interval` | 0.5 s | Cadence de mesure V/I des alimentations |
| `temp_poll_interval` | 0.2 s | Cadence de la boucle de sécurité thermique |
| `auto_shutdown_on_critical` | `true` | Désalimentation ordonnée au seuil critique |
| `shutdown_sequence` | `null` | Chemin d'une séquence d'arrêt personnalisée ; `null` → `sequences/shutdown.seq` si présent, sinon extinction générée automatiquement |
| `shutdown_delay` | 0.5 s | Temporisation entre voies (extinction automatique) |
| `hard_margin_c` | 15 °C | Marge au-delà du seuil critique déclenchant la **coupure dure** |
| `shutdown_takeover_wait_s` | 3 s | Attente maximale de l'arrêt de la séquence utilisateur avant la désalimentation |
| `shutdown_timeout` | auto | Budget de temps de la désalimentation ordonnée ; dépassé → coupure dure |
| `comm_fail_limit` | 3 | Échecs consécutifs avant déclaration de perte d'instrument |
| `shutdown_on_temp_lost` | `true` | Désalimente si la mesure de température est perdue avec des voies allumées |
| `shutdown_on_sensor_fault` | `false` | Désalimente si un capteur passe en DÉFAUT |
| `shutdown_on_hw_fault` | `false` | Désalimente sur défaut matériel HMP (OVP, fusible, surchauffe) |

## Annexe C — Convertisseurs de température

Chaque capteur convertit la tension lue par le module NI en °C. Types
disponibles (assistant graphique intégré, avec tracé de la courbe de réponse) :

| Type | Usage |
|---|---|
| `identity` | La tension **est** la température (capteur conditionné, ex. 10 mV/°C avec gain externe) |
| `polynomial` | Polynôme `T = c0 + c1·V + c2·V² + …` (capteurs linéaires type LM35, ou étalonnage) |
| `table` | Interpolation linéaire entre points (V, °C) d'étalonnage |
| `ntc` | Thermistance NTC (modèle β ou Steinhart-Hart) dans un pont diviseur — paramètres : R nominale, β, R du pont, tension de référence, sens du pont |
| `ptc` | Sonde PTC/RTD (ex. PT100/PT1000 conditionnée) dans un pont diviseur |
| `thermocouple` | Thermocouple (types usuels) avec compensation de soudure froide approchée |

Pour `ntc` et `ptc`, une tension mesurée collée à un rail (capteur débranché,
court-circuit) est détectée et signalée en **DÉFAUT** — jamais interprétée comme
une température extrême. Renseigner de plus `T plausible min/max` (§9.5) par
ceinture et bretelles.

**⚠ Thermocouples — limite à connaître.** Une emf aberrante (entrée flottante,
rail, ampli saturé) est signalée en **DÉFAUT** (résultat hors de la plage de
validité du polynôme). En revanche, un thermocouple **coupé dont l'entrée lit
~0 V** est *indiscernable en logiciel* d'un objet à la température ambiante :
la détection fiable du TC ouvert est **matérielle** (module d'acquisition avec
*open-TC detect*). C'est pourquoi la configuration **exige** `T plausible
min/max` pour un thermocouple — et pour une surveillance critique, préférer un
module à détection d'ouverture ou doubler le capteur.

---
