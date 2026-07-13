# Architecture — ALIM_SEQ

Document technique décrivant le fonctionnement interne de l'application. Public :
développeurs et mainteneurs. Pour l'usage, voir [MANUEL_UTILISATEUR.md](MANUEL_UTILISATEUR.md) ;
pour construire les exécutables, voir [TOOLCHAIN.md](TOOLCHAIN.md).

## 1. Vue d'ensemble

ALIM_SEQ séquence l'alimentation d'une carte électronique : il pilote des voies
d'alimentation (R&S HMP40xx/20xx en SCPI), mesure des températures (module NI),
exécute des séquences scriptées, et applique une **surveillance thermique de
sécurité**. Il fonctionne en **matériel réel** ou en **simulation** (mêmes chemins
de code, pilotes remplacés par des mocks).

Principes de conception :

- **Cœur découplé de l'IHM.** Toute la logique (pilotage, mesure, sécurité,
  séquences, rapports) vit dans le paquet `alim_seq/` et ne dépend pas de Qt.
  L'IHM Qt (`gui_qt/`) se branche dessus ; le cœur reste testable et scriptable
  sans elle.
- **Sécurité prioritaire.** Une boucle de sécurité rapide et indépendante peut
  désalimenter la carte à tout moment, y compris en écrasant la séquence en cours.
- **Matériel abstrait + simulable.** Les pilotes (`PSU`, `DAQ`) ont une interface
  commune et une implémentation mock fidèle (modèle thermique), pour tout tester
  sans banc.
- **Accès matériel sérialisé.** Tous les échanges instrument passent derrière un
  **unique verrou**, ce qui évite les entrelacements SCPI et les désynchronisations.

## 2. Cartographie des modules

```
main.py                  point d'entrée : arguments, choix IHM, chargement config
alim_seq/
  config.py              schéma (dataclasses) + load_config + validation
  instrument.py          abstraction par capacités (SourceTension/MesureVI/…),
                         registre INSTRUMENTS + fabrique create_instrument
  psu.py                 pilotes alimentation : BasePSU, HMP4040 & variantes,
                         MockPSU, registre PSU_MODELS, routage par label
  daq.py                 acquisition NI : NIDaq (nidaqmx) + MockDAQ (modèle thermique)
  relay.py               actionneurs (BaseRelay/MockRelay), sorties par label + safe_state
  temperature.py         convertisseurs tension→°C (table/poly/ntc/ptc/identity/tc)
  expressions.py         évaluateur d'expressions sûr (SETV/SETI)
  sequencer.py           analyse + exécution des séquences .seq (interruptible)
  controller.py          orchestration : boucles mesure & sécurité, trip, lifecycle
  controller_recording.py  RecordingMixin : enregistrement d'essai (start/stop, lignes CSV)
  controller_servo.py    ServoMixin : asservissement linéaire / adaptatif
  controller_simtune.py  SimTuneMixin : réglage à chaud du banc simulé (charges, couplages)
  essai.py               dossier d'essai autonome (CSV + artefacts)
  rapport.py             rapport d'essai : données + HTML (pur Python) → PDF (ReportLab) + graphes (matplotlib)
  gui_qt/                IHM Qt/PySide6 (unique interface)
    main_window.py       fenêtre, onglets, menus, barre de sécurité, aide (F1)
    config_tab.py        édition de config (formulaires + JSON avancé)
    config_wizard.py     assistant de configuration (proposé au 1er lancement)
    editor.py            éditeur de séquence (coloration, auto-complétion, lint en direct)
    plot.py              onglet Graphe (températures/courants/tensions)
    replay.py            relecture d'un essai enregistré + comparaison de deux essais
    sim_tab.py           onglet Simulation : réglage à chaud du banc virtuel (SimMixin)
    converter.py         assistant convertisseur de température (courbe live)
    workers.py           tâches matérielles en fil de fond (connexion, scan VISA)
    theme.py, widgets.py thème sombre, widgets bornés (saisies, armement 2 temps)
packaging/launcher.py    point d'entrée empaqueté : dossier de données + chdir
```

Couches (de bas en haut) : **pilotes** (`psu`, `daq`) → **domaine**
(`config`, `temperature`, `expressions`, `sequencer`) → **orchestration**
(`controller`) → **IHM** (`gui`, `gui_qt`) + **sorties** (`essai`, `rapport`).

## 3. Modèle de threads et flux de données

L'application est multi-thread ; l'IHM ne bloque jamais sur le matériel.

- **Thread IHM (principal)** — Qt. N'appelle jamais le matériel
  directement pour une opération longue.
- **Boucle de mesure** (thread du `Controller`) — lit V/I des alimentations à la
  cadence `safety.poll_interval` (SCPI, plus lent), pousse les échantillons vers
  l'IHM (signaux/callbacks) et le CSV.
- **Boucle de sécurité** — lit les températures à `safety.temp_poll_interval`
  (rapide, 0,2 s) **indépendamment** de la mesure V/I : la protection reste
  réactive même si les alimentations répondent lentement.
- **Thread séquenceur** — exécute une séquence action par action, interruptible à
  tout instant (pause, stop, arrêt d'urgence).
- **Workers matériels** (`gui_qt/workers.py`) — connexion, reconnexion, scan et
  test VISA s'exécutent en fond ; un timeout matériel ne gèle pas la fenêtre, et
  l'arrêt d'urgence reste cliquable.

Tous les accès instrument (mesure, séquence, sécurité, IHM) convergent vers le
`Controller` et sont **sérialisés par un verrou par instrument**. Le flux nominal :

```
config.json → load_config → Controller ── crée ─▶ instruments (par capacité)
                                                     · sources (alim réelle/mock)
                                                     · température (NI/mock)
Controller.boucle_mesure  → V/I → IHM + CSV        (instruments MesureVI)
Controller.boucle_secu    → °C  → seuils → désalim (instruments MesureTemperature)
sequencer                 → actions → Controller (SET/ON/RAMP/SERVO…) → sources
```

## 4. Le Controller

`controller.py` est le chef d'orchestre. Il :

- construit les pilotes selon `simulate` (réels ou mocks) et les **connexions
  tolérantes aux pannes** (l'IHM s'ouvre même si un instrument est absent, avec un
  bouton *Reconnecter*) ;
- fait tourner les deux boucles (mesure V/I, sécurité thermique) ;
- expose les primitives de pilotage appelées par l'IHM **et** le séquenceur :
  réglage tension/courant, ON/OFF, rampes, **asservissement** (servo) ;
- tient l'**état de sécurité** (normal / alerte / critique / défaut / trip) et
  déclenche les désalimentations ;
- journalise (`enable_file_logging` → `logs/alim_seq.log`, rotation) et alimente
  l'enregistrement d'essai.

**Décomposition en mixins.** Le cœur sûreté (boucles mesure/sécurité, verrous,
lifecycle connect/reconnect, escalade, `emergency_stop`, `snapshot`) reste dans
`controller.py`. La périphérie cohésive est extraite en **mixins** partageant le
même `self` — donc sans changement de comportement (`class Controller(RecordingMixin,
ServoMixin, SimTuneMixin)`) : `RecordingMixin` (enregistrement d'essai),
`ServoMixin` (asservissement) et `SimTuneMixin` (réglage à chaud du banc simulé).

**Asservissement (servo).** Monte/descend la tension d'une voie *réglée* jusqu'à
obtenir un courant cible sur une voie *mesurée*. Deux stratégies : `SERVO_LIN`
(pas fixe) et `SERVO_ADAPT` (pas adaptatif type sécante/Newton — grand pas loin de
la cible, fin près, avec amortissement). Le servo connaît la **polarité** des
rails négatifs et le sens d'action (option `invert`).

**Lecture d'état HMP.** Le CV/CC et les défauts (OVP, fusible électronique,
surchauffe) sont lus sur le **registre d'état** du HMP
(`STAT:QUES:INST:ISUM<n>:COND?`) quand `cc_status` est actif, avec repli sur une
inférence V/I (hystérésis) si le firmware ne répond pas.

## 5. Pilotes matériel et simulation

**`instrument.py`** — abstraction **par capacités** : un `Instrument` déclare ce
qu'il sait faire (`SourceTension`, `MesureVI`, `MesureTemperature`, `Actionneur`)
au lieu d'être catégorisé. Registre unifié `INSTRUMENTS` / fabrique
`create_instrument`. Le `Controller` pilote *par capacité* et route chaque **label**
de voie vers `(instrument, canal)` physique. Pour **intégrer un nouvel appareil**,
voir [GUIDE_DRIVERS.md](GUIDE_DRIVERS.md).

`psu.py` — interface commune `BasePSU` (capacités `SourceTension`+`MesureVI`) ;
`HMP4040` (et sous-classes `HMP4030` / `HMP2030` / `HMP2020` : mêmes commandes SCPI,
nombre de voies différent). Durcissements SCPI : terminaisons `\n` explicites (socket brut), purge
du buffer à la connexion, `*OPC?` après chaque réglage (E/S équilibrées),
`visa_query_delay` optionnel contre les *input protocol violation*.

`daq.py` — `NIDaq` (via `nidaqmx`, entrées analogiques `ai0…`, calibre ±10 V par
défaut) ; `MockDAQ` en simulation.

`relay.py` — actionneurs (capacité `Actionneur`) : `BaseRelay`/`MockRelay`, sorties
adressées par **label**. Un relais se déclare dans `instruments` (driver
`MOCK-RELAY`) avec ses `outputs` ; chaque sortie porte un `safe_state` (défaut
OFF/ouvert) appliqué à l'arrêt d'urgence et en fin de désalimentation ordonnée. Piloté
par `RELAY <sortie> ON|OFF` (séquence) et `Controller.set_relay`. Aucun modèle matériel
réel n'est encore intégré (le `MockRelay` fait office de relais « virtuel »).

**Simulation.** `MockPSU` modélise une **charge par voie** (`simulation.loads`,
`I = V/R`, passage en CC si `V/R` dépasse la limite) et, optionnellement, des
**couplages grille→drain** (`simulation.couplings`, transconductance `Id = gm·(Vg−vth)`)
pour faire converger un servo sans banc. `MockDAQ` applique un **modèle thermique**
(la carte chauffe avec la puissance dissipée : gain, constante de temps, bruit),
ce qui permet de **valider le déclenchement de la sécurité**.

## 6. Le séquenceur

`sequencer.py` — une séquence est un fichier texte, **une action par ligne**.

- `parse_sequence(text, valid_labels, valid_sensors) -> List[Action]` : analyse et
  **valide** (syntaxe, existence des voies/capteurs, validité numérique des
  arguments, clés `clé=valeur` en liste blanche par commande, `RAMP` à nb de pas
  entier ≥ 2). Une séquence vérifiée ne s'arrête pas en cours pour une faute
  d'écriture.
- Boucles `REPEAT n … END` (imbrication possible) développées à l'analyse.
- `estimate_duration(actions)` : durée estimée (affichée à la vérification).
- Exécution **interruptible** dans le thread séquenceur : `WAIT` gelable
  (pause/reprise), mode **pas-à-pas**, **stop** propre.
- Consignes calculées `SETV`/`SETI` : délèguent à `expressions.py`, un évaluateur
  **restreint** (noms de voies = consigne de tension ; fonctions `V/Vmeas/Iset/I` ;
  opérateurs arithmétiques ; **aucun** code arbitraire). Résultat borné par les
  `max_voltage`/`max_current`.

Commandes : `SET/VOLTAGE/CURRENT`, `SETV/SETI`, `ON/OFF`, `WAIT`, `RAMP`,
`SERVO_LIN/SERVO_ADAPT`, `WAIT_CURRENT`, `WAIT_TEMP`, `RELAY`, `LOG`, `ALL_OFF`,
`SHUTDOWN`, `REPEAT/END`. Référence complète : Annexe A du manuel (et menu Aide de
l'app).

## 7. Configuration

`config.py` — `load_config(path)` lit le JSON vers des **dataclasses** typées
(`AppConfig`, `ChannelConfig`, `GroupConfig`, `TempSensorConfig`) puis
`_validate()` contrôle la **cohérence** : modèle d'alimentation connu, canal dans
la plage du modèle, unicité voie↔canal physique, seuils `critical > warning`,
membres de groupe existants et non partagés (≥ 2, série uniquement), garde-fous
capteurs (bande de plausibilité ou `fault_margin`), `ref_channel` résolu. La
validation **refuse** une configuration incohérente (références orphelines,
limites hors modèle…).

Sections : `simulate`, `instruments`, `channels`, `groups`, `temperatures`,
`safety`, `simulation`, plus `visa_backend`, `visa_query_delay`, `cc_status`.

**Section unifiée `instruments`** (canonique) — décrit la chaîne d'appareils sans
présager de catégorie : chaque entrée est `"<nom>": {"driver": "…", …params}`
(ex. `{"driver": "HMP4040", "resource": "…"}`, `{"driver": "NI-DAQ", "device": "Dev1"}`).
Le contrôleur classe chaque instrument **par capacité** via son `driver`. Les
sections historiques **`supplies`** (alims) et **`daq`** (module NI) restent
acceptées comme **sucre rétrocompatible** : `AppConfig.__post_init__` maintient les
deux vues cohérentes (`instruments` fait foi). `config_to_dict()` fait le chemin
inverse (archivage) et émet les deux. La config **par défaut livrée** est neutre
(1 HMP4040, voies `CH1`/`CH2`, `simulate: true`).

## 8. Températures et convertisseurs

`temperature.py` — chaque capteur convertit une **tension NI** en °C selon
`converter.type` : `identity`, `polynomial`, `table` (interpolation), `ntc`
(équation β / Steinhart-Hart), `ptc`/`rtd` (linéaire, PT100/PT1000),
`thermocouple`. Pour `ntc`/`ptc`, une tension **collée à un rail** (capteur
débranché / court-circuit) est détectée → **DÉFAUT** (jamais une température
extrême faussement plausible). Un capteur peut être **conditionné à des voies**
(`requires`) : « en attente » (exclu de la sécurité) tant que ces voies ne sont
pas ON. Contrôle optionnel de la **tension de référence** du pont (`ref_channel`).

## 9. Sécurité — machine à états

État global : **OK → ALERTE → CRITIQUE**, plus **DÉFAUT capteur** et **TRIP**
(verrouillé). Sur dépassement **critique** (ou perte de température/comm selon
config) :

1. **Désalimentation ordonnée** — exécute `sequences/shutdown.seq` s'il existe (ou
   `safety.shutdown_sequence`), sinon une extinction voie par voie dans l'ordre
   inverse de la config (`shutdown_delay` entre voies). **Prioritaire et non
   interruptible** : elle écrase la séquence utilisateur (après
   `shutdown_takeover_wait_s`) et ignore *Stop*.
2. **Coupure dure** de dernier recours — si la température atteint
   `critique + hard_margin_c`, ou si la désalimentation dépasse `shutdown_timeout`,
   ou sur perte de communication alimentation : toutes les sorties tombent
   immédiatement.

Après incident → état **TRIP** : tout rallumage est refusé jusqu'à un
**Réarmement** volontaire (après correction). L'enregistrement en cours **ne se
ferme pas** : il capte la désalimentation (précieux pour l'analyse) et marque
l'issue. Défauts matériels HMP (OVP/fusible/surchauffe) et défauts capteur
peuvent, en option, déclencher la désalimentation (`shutdown_on_*`).

## 10. Enregistrement : dossier d'essai et rapport

`essai.py` — chaque enregistrement crée un **dossier autonome**
`logs/essais/AAAAMMJJ_HHMMSS[_<nom>]/` contenant `mesures.csv` (une ligne par
cycle, flushée en direct : horodatage, °C + tension NI brute par capteur, Vset/
Iset/Vmeas/Imeas/out par voie, état sécurité), une **copie de la config active**
(+ empreinte), la `sequence.seq` exécutée, `journal.log`, et `essai.json`
(métadonnées + **issue** : `termine` / `arret_utilisateur` /
`declenchement_securite` / `en_cours`).

`rapport.py` — trois couches sans dépendance à Qt : (1) **données** (`stats_*`,
`evenements`, `trip_info`, pur Python, testables) ; (2) **graphiques** tracés par
**matplotlib** (backend Agg) depuis `mesures.csv` ; (3) **rendus** partageant les
données — `construire_html` (aperçu navigateur) et `exporter_pdf` **via ReportLab**
(pur Python : une page par partie, tableaux à en-têtes colorés, pied de page
paginé). Atout : le rapport se **régénère depuis le seul dossier d'essai**, sans
état vivant, même longtemps après. Sans matplotlib, le rapport est produit sans les
graphiques.

## 11. IHM

L'IHM **Qt/PySide6** (`gui_qt/`) est l'unique interface, branchée sur le
`Controller` : onglets Contrôle / Configuration / Éditeur de séquence / Graphe /
**Simulation** (ce dernier en mode simulé) ; **barre de sécurité permanente** (Arrêt
d'urgence, Séquentiel d'arrêt, Réarmer, Tout OFF, badge de mode) ; saisies **bornées**
par la config (jaune = non appliqué) ; **armement en deux temps** du ON sur matériel
réel (1ᵉʳ clic = armer, 2ᵉ = allumer ; contourné par Maj) ; configuration éditable par
**formulaires + JSON avancé** synchronisés ; **assistant convertisseur** (courbe live) ;
graphe commutable °C/A/V avec curseur de lecture, seuils, repères d'événements et
**marqueur opérateur** (`Ctrl+M`) ; workers en fond ; aide intégrée (**F1** → manuel,
référence des commandes, raccourcis).

- **Éditeur de séquence** — coloration, auto-complétion, palette cliquable et **lint
  en direct** (vérification à la frappe, ligne fautive soulignée, statut ✓/✗).
- **Relecture et comparaison d'essais** (menu *Fichier*) — rouvre un dossier d'essai
  enregistré et **rejoue ses courbes** (`replay.py`, réutilisant le curseur du graphe),
  avec régénération du rapport PDF ; ou **superpose deux essais** recalés.
- **Assistant de configuration** (`config_wizard.py`) — proposé **au tout premier
  lancement** (une seule fois) et disponible dans le menu *Fichier* : simulation, scan
  VISA ou saisie d'adresse manuelle.

## 12. Empaquetage et données utilisateur

- **`packaging/launcher.py`** (point d'entrée de l'exe) : force l'IHM Qt, résout le
  **dossier de données inscriptible** — celui choisi à l'installation
  (registre `HKCU/HKLM\Software\ALIM_SEQ\DataDir`), sinon `Documents\ALIM_SEQ` —,
  y **dépose** au premier lancement `config.json` + `sequences/`, puis **`chdir`**
  dedans. Ainsi tous les chemins relatifs (`config.json`, `logs/…`) tombent dans ce
  dossier, même avec une installation en lecture seule.
- **PyInstaller** (`packaging/ALIM_SEQ.spec`) : exe **un seul fichier**, embarque
  PySide6 (modules Qt lourds exclus), pyvisa/pyvisa-py + backends, nidaqmx (+
  métadonnées), matplotlib (backend Agg), et les données (`config.json`,
  `sequences/`, `docs/MANUEL_UTILISATEUR.*`). Le **runner Forgejo** n'ayant pas de
  binaire Windows officiel, il est cross-compilé (voir TOOLCHAIN).
- **Inno Setup** (`packaging/ALIM_SEQ.iss`) : installateur avec choix admin/sans
  admin, logo dans l'assistant, et **page de choix du dossier de données** (écrit
  la clé de registre lue par le launcher). Le driver **NI-DAQmx** reste à installer
  séparément sur la machine cible pour l'acquisition réelle.

## 13. Toolchain (build)

La production des exécutables Windows se fait par CI auto-hébergée (Forgejo + VM
Windows à la demande). Un `git push` de tag `v*` — ou `tools/lab-build.sh <tag>` —
déclenche `pip → PyInstaller → Inno Setup`. Détails : [TOOLCHAIN.md](TOOLCHAIN.md).
