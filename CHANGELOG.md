# Journal des modifications

Toutes les modifications notables d'ALIM_SEQ sont consignées ici.
Format inspiré de [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/) ;
versionnage [SemVer](https://semver.org/lang/fr/).

## [1.3.0] — 2026-07-13

### Ajouté
- **Configuration et séquences de démonstration** livrées par défaut : un scénario de
  simulation complet (rails, groupe série, capteur thermique, couplage grille→drain
  pour le SERVO, relais) et plusieurs séquences (`demo.seq`, `servo_bias.seq`,
  `balayage_polarisation.seq`, `arret.seq` — coupure ordonnée) pour découvrir l'outil
  immédiatement.
- **Assistant de configuration** (au premier lancement, ou *Fichier → Assistant de
  configuration…*) : voie **simulation** (config sans matériel), **scan VISA**
  (USB-TMC / LAN VXI-11) ou **saisie d'une adresse manuelle** — indispensable pour le
  **mode socket LAN** (`::5025::SOCKET`) qu'un scan ne peut pas découvrir : l'adresse
  est testée (`*IDN?`) puis ajoutée. Génère `supplies` + voies pré-remplies, chargées
  dans l'éditeur pour revue avant application. Nouveau `psu.probe_instrument`.
- **Relecture d'essai** (*Fichier → Rouvrir un essai*) : fenêtre rejouant les courbes
  d'un dossier `logs/essais/…` — bascule Températures/Courants/Tensions, **curseur de
  lecture** des valeurs, **repères d'événements** numérotés (marqueurs 📌, alertes,
  sécurité), export PNG et génération du rapport PDF. L'application devient un outil
  d'**analyse**, plus seulement un enregistreur.
- **Comparaison de deux essais** (*Fichier → Comparer deux essais*) : superpose les
  courbes de deux dossiers (recalées sur t=0, séries `A·`/`B·`, une couleur par série)
  pour visualiser une **dérive avant/après** modification de la carte.
- **Allumage en deux temps (matériel réel)** : en mode réel, le 1ᵉʳ clic sur ON
  affiche « ⚠ Armer ? », un 2ᵉ clic (sous 3 s) allume — filet contre le clic
  malheureux. Direct en simulation ; `Maj+clic` force l'allumage immédiat.
- **Indicateur d'état périmé** : quand l'instrument d'une voie ne répond plus (liaison
  figée), ses V/I mesurés sont **grisés** et le mode affiche « ⏱ figé » — plus d'« OFF
  fantôme » ni de mesure figée passant pour vivante (complète le correctif de la boucle
  V/I à verrou timeouté).
- **Marqueur opérateur (📌 / Ctrl+M)** : pose une note horodatée au journal, reprise
  comme repère vertical sur le graphe temps réel **et** comme badge numéroté dans le
  rapport d'essai (« c'est ici que… »).
- **Lint en direct de l'éditeur de séquence** : validation au fil de la frappe
  (debounce 300 ms), statut ✓/✗ et **soulignage rouge de la ligne fautive**, sans
  attendre le bouton « Vérifier ».
- **Smokes IHM** (`tests/test_gui_smoke.py`) : filet de test offscreen sur la
  construction, les onglets, le rafraîchissement et les interactions clés de l'IHM.

### Changé (technique)
- **Décomposition de `controller.py`** (objet-dieu, 1830 → 1479 lignes) par **mixins**,
  **cœur sûreté intact** : extraction de l'enregistrement CSV/dossier d'essai
  (`controller_recording.py`), de l'asservissement (`controller_servo.py`) et des
  couplages simulés + réglage à chaud (`controller_simtune.py`). Pur déplacement de
  code (même état `self`), zéro changement de comportement.

### Corrigé / sûreté
- Note de **sécurité réseau** au manuel (SCPI/TCPIP sans authentification → banc isolé).
- `stop_polling` ne joint que les threads réellement démarrés (garde `t.ident`) —
  robustesse si un `start()` échoue.

## [1.2.1] — 2026-07-12

### Sécurité
- **Thermocouples : détection de défaut.** Une emf hors de la plage de validité du
  polynôme NIST (entrée flottante, rail, ampli saturé) retourne désormais **NaN →
  DÉFAUT** au lieu d'une température extravagante mais « numérique ». La validation
  **exige** `valid_min`/`valid_max` pour un thermocouple (seul filet logiciel contre
  un TC débranché — un TC ouvert lisant ~0 V reste indétectable en logiciel :
  limitation documentée, préférer un module avec *open-TC detect*).
- **Arrêt d'urgence : relais mis à l'état de sécurité APRÈS l'armement du trip** —
  une fermeture de relais concurrente ne peut plus se glisser entre l'isolement et
  le verrouillage ; `set_relay` re-vérifie aussi le trip sous le verrou instrument.

### Corrigé
- **Validation : les convertisseurs de température sont construits dès le chargement**
  de la configuration — un paramètre aberrant (`alpha=0`, `beta=0`, clé manquante,
  table vide…) est refusé à la validation au lieu de provoquer une erreur (jusqu'à
  une `ZeroDivisionError`) à la **première mesure**, dans la boucle de sécurité.
- **Dossiers d'essai : anti-collision.** Deux essais démarrés dans la même seconde
  (stop/start rapide) partageaient le même dossier et le second **écrasait**
  `mesures.csv`. Suffixe `_2`, `_3`… + création atomique.
- **Boucle de mesure V/I : plus de blocage silencieux.** Le verrou de chaque alim est
  acquis **avec timeout** : une liaison VISA figée (socket mort) ne bloque plus la
  lecture des autres alims ni la boucle entière — l'alim indisponible est sautée
  (dernières valeurs conservées, pas de faux 0 V au CSV) et l'anomalie journalisée.
- **Reconnexion sérialisée** : le chien de garde (`auto_reconnect`) et le bouton
  « Reconnecter » pouvaient reconstruire les instruments **en même temps** ; la
  seconde demande est désormais refusée proprement.
- **Séquences : opérateur `!=` accepté** (`WAIT_CURRENT`/`WAIT_TEMP`) — l'aide de
  l'éditeur l'annonçait mais la validation le refusait ; `==` documenté partout.
- **IHM relais : plus d'« OFF fantôme »** — l'affichage ressert la dernière lecture
  réussie quand le verrou instrument est momentanément occupé.
- **Éditeur de config : une sortie « fermée à l'arrêt » absente de la colonne
  Sorties** est ajoutée aux sorties au lieu d'être ignorée en silence.

## [1.2.0] — 2026-07-12

### Ajouté
- **IHM — onglet Simulation (réglage à chaud).** En mode simulation, un onglet
  **🧪 Simulation** permet de régler **en direct** les charges résistives par voie,
  le modèle thermique (ambiante, gain °C/W, constante de temps, bruit) et les
  couplages grille→drain (gm, vth, imax), avec effet immédiat visible dans l'onglet
  *Contrôle*. Primitives contrôleur `sim_params`/`sim_set_load`/`sim_set_thermal`/
  `sim_set_couplings` (appliquées aux mocks et à `cfg.simulation`, donc conservées au
  reconnect ; sans effet hors simulation). Objectif : reproduire fidèlement le
  comportement d'un montage sans matériel.
- **IHM — prise en charge des relais.** Onglet *Contrôle* : cadre **Relais** avec
  l'état de chaque sortie et un bouton ON/OFF (mêmes garde-fous que les voies : fermeture
  refusée sous sécurité armée, commandes gelées pendant une (re)connexion). Onglet
  *Configuration* : sous-onglet **Relais** pour déclarer les instruments relais et
  leurs sorties (dont l'état de sécurité). Aide/complétion de la commande `RELAY` dans
  l'éditeur de séquence.
- **Configuration — fusion `instruments` + `supplies`/`daq`.** Une config peut
  combiner des sources décrites en `supplies` (legacy) ET des instruments en
  `instruments` (ex. relais) sans que les unes masquent les autres : les deux sont
  fusionnées (`AppConfig.__post_init__`), les entrées `instruments` explicites primant.
- **Pilotage de relais / actionneurs** (capacité `Actionneur`, ROADMAP §4). Nouveau
  driver `alim_seq/relay.py` (`BaseRelay`/`MockRelay`). Un relais se déclare comme un
  instrument de la section `instruments` (driver `MOCK-RELAY`) avec ses `outputs` ;
  chaque sortie a un `safe_state` (défaut OFF/ouvert). Nouvelle commande de séquence
  **`RELAY <sortie> ON|OFF`** ; primitives contrôleur `set_relay`/`relay_state` et
  états exposés dans le `snapshot`. Les relais **participent à la désalimentation de
  sécurité** : ils sont ramenés à leur `safe_state` à l'arrêt d'urgence et en fin de
  désalimentation ordonnée (ouvrir un relais isole la carte). Le `MockRelay` sert la
  simulation et de relais « virtuel » tant qu'aucun modèle matériel n'est câblé.
- **Configuration : section unifiée `instruments`.** La chaîne d'appareils peut
  désormais se décrire dans une seule section `instruments` (chaque entrée : un
  `driver` + ses paramètres), sans présager de catégories. Les sections historiques
  `supplies`/`daq` restent acceptées (**sucre rétrocompatible**) : `instruments` fait
  foi et les deux vues sont maintenues cohérentes (`AppConfig.__post_init__`). Les
  `config.json` et configs d'essai existants se rechargent sans modification.

### Changé (technique)
- **Abstraction des appareils par capacités — phases 1 à 3** (structurant, sans
  changement de comportement). Nouveau module `alim_seq/instrument.py` : un
  `Instrument` (cycle de vie `connect`/`close` + identité) déclare les **capacités**
  qu'il expose — `SourceTension` (tension + limite de courant), `MesureVI`,
  `MesureTemperature`, `Actionneur` — au lieu d'être figé en « alim » ou « DAQ ».
  Les drivers existants adoptent ces capacités (`BasePSU` → `SourceTension`+`MesureVI`,
  `BaseDAQ` → `MesureTemperature`) et un **registre unifié** `INSTRUMENTS` /
  `create_instrument` généralise `PSU_MODELS`/`create_psu`. Le **contrôleur** est
  généralisé : un **verrou par instrument** (`_instr_locks`, remplace
  `_psu_locks`+`_daq_lock`, ordre invariant élargi à l'ordre alphabétique des noms),
  pilotage et boucles **par capacité**, routage label→(instrument, voie) centralisé ;
  `PSUManager` est **supprimé**. Le contrôleur construit désormais ses instruments
  depuis la section `instruments` (chaque entrée classée par capacité via son
  `driver`), ce qui permettra d'ajouter les relais sans toucher au cœur. Prépare la
  modularité de la chaîne d'appareils (voir `docs/DESIGN_INSTRUMENTS.md`).

### Changé
- **Suppression de l'IHM Tkinter.** L'interface **Qt (PySide6)** devient l'unique
  IHM : `alim_seq/gui.py` est retiré et l'option `--gui` disparaît (l'application
  lance toujours Qt). Conséquence : PySide6 est désormais requis pour lancer
  l'application, y compris en simulation — les **tests**, eux, ne requièrent aucune
  IHM (ils pilotent le `Controller` directement). Objectif : supprimer l'entropie
  de maintenance de deux interfaces et préparer la modularisation des appareils
 .

## [1.1.2] — 2026-07-11

### Modifié
- **Rapport d'essai — refonte de la lisibilité et de la mise en page.**
  - **Graphiques** : palette catégorielle fixe et validée (une voie = une couleur
    sur les cadrans V et I), couleurs de statut réservées pour les seuils
    (alerte/critique) et le déclenchement, et surtout **bandeau d'événements à
    badges numérotés anti-collision** remplaçant les étiquettes qui se
    chevauchaient et rendaient le graphe illisible. Titre renommé
    « Mesures pendant l'essai ».
  - **Mise en page PDF** : **une page par partie**, tableaux centrés pleine
    largeur à en-têtes colorés et zébrures, pied de page paginé « page X / N »,
    en-tête courant (nom d'essai), notes de légende sous les tableaux. Colonne
    « Excursions » clarifiée en « Dépassements ».

### Changé (technique)
- **Génération du PDF : passage de Qt (`QTextDocument`/`QPdfWriter`) à
  ReportLab** (pur Python). Le rapport ne dépend plus de PySide6 : la couche
  données reste testable sans dépendance, `construire_html` demeure pour l'aperçu
  navigateur, et les graphiques restent tracés par matplotlib (backend Agg).
  Nouvelle dépendance `reportlab` (embarquée au build PyInstaller).

## [1.1.1] — 2026-07-06

### Corrigé
- **Rapport : polices matplotlib manquantes sur le build installé.** Le
  dégraissage `mpl-data` ne conservait que la police DejaVu Sans, ce qui cassait
  le rendu des graphiques du rapport (« il manque des polices »). **Toutes** les
  polices `fonts/ttf/` sont désormais embarquées (le gain de ~2 Mo ne justifiait
  pas la régression). Validé sur matériel réel.

## [1.1.0] — 2026-07-05

### Ajouté
- **Rapport d'essai enrichi** (`rapport.py`) :
  - événements du journal (messages `LOG` de séquence, alertes, événements de
    sécurité) **matérialisés sur les courbes** V/I et températures, recalés sur
    l'axe des temps du CSV ;
  - **graphique de zoom sur le déclenchement** de sécurité (fenêtre ±30 s autour
    du trip, capteur en cause en trait épais, seuils alerte/critique, zone
    critique ombrée) ;
  - **statistiques enrichies** : temps en limitation de courant (CC) par voie
    (en s et %), consignes début/fin ; excursions de température (nombre de
    passages en alerte, durées cumulées au-dessus de l'alerte et du critique) ;
    ligne de synthèse (points, cadence effective, taille du CSV) ;
  - **mise en page** : logo en en-tête, **pied de page paginé**, zone de visa
    opérateur, annexe configuration lisible (tableaux voies/capteurs avant le
    JSON brut), nombres au **format français**.
- **Toolchain de build** : construction des exécutables via CI auto-hébergée
  (Forgejo + VM Windows **à la demande**), commande unique `tools/lab-build.sh
  <tag>`, documentation `docs/TOOLCHAIN.md` et `docs/ARCHITECTURE.md`.
- **Aide intégrée** : manuel utilisateur consultable dans l'application (touche
  **F1**) et fourni en `.md`/`.docx`/`.pdf` (`docs/`).

### Modifié
- **Build allégé** (`packaging/ALIM_SEQ.spec`) : passage en **onedir** et
  exclusions ciblées — matplotlib **backend Agg** seul, pas de tkinter ni
  d'OpenGL logiciel, traductions et plugins Qt inutiles retirés, `mpl-data`
  filtré (police DejaVu Sans conservée). **≈ −23 %** (180,7 → 139,2 Mio),
  installateur ≈ 46 Mo. Détails et check-list de validation :
  `packaging/OPTIMISATION.md`.
- Configuration livrée **neutre** (voies génériques `CH1`/`CH2`, démarrage en
  **simulation**), séquence d'exemple unique.

## [1.0.0] — 2026-07-05

Première version complète.

### Sécurité
- Surveillance thermique découplée (boucle rapide) : **désalimentation ordonnée
  non interruptible** au seuil critique, **coupure dure** de dernier recours
  (`critique + marge`, ou budget de temps dépassé), **verrous par périphérique**
  sérialisant les accès instrument, état **« trip »** verrouillé et **réarmement**
  volontaire.
- Détection de capteur débranché (tension collée à un rail → DÉFAUT), défauts
  matériels HMP (OVP / fusible / surchauffe), pertes de communication.

### IHM Qt
- Barre de sécurité permanente (arrêt d'urgence, séquentiel d'arrêt, réarmer,
  tout OFF), **badge de mode** SIMULATION / MATÉRIEL RÉEL, thèmes clair/sombre,
  saisies **bornées** par la configuration, **workers matériel en tâche de fond**
  (pas de gel de l'IHM), éditeur de séquence avec vérification et auto-complétion,
  onglet graphe (températures / courants / tensions).

### Traçabilité
- **Dossiers d'essai autonomes** (`logs/essais/…` : `mesures.csv`, copie de
  configuration, séquence, journal, métadonnées + issue de l'essai) et **rapport
  d'essai HTML/PDF régénérable** depuis le seul dossier.
