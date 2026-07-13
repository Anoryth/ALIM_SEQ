# Guide du développeur — ALIM_SEQ

Ce document aide un **nouveau développeur** à reprendre le projet : installation,
tests, conventions, et surtout des **recettes pas-à-pas** pour les évolutions
courantes. Pour *comprendre* le système (threads, sécurité, flux de données), lire
d'abord [ARCHITECTURE.md](ARCHITECTURE.md) ; pour *l'utiliser*, voir
[MANUEL_UTILISATEUR.md](MANUEL_UTILISATEUR.md) ; pour *construire les exécutables*,
voir [TOOLCHAIN.md](TOOLCHAIN.md).

---

## 1. Prise en main en 2 minutes

Les **tests** ne requièrent aucune IHM (ils pilotent le `Controller` directement) :
Python 3.9+ suffit. **Lancer l'application** requiert en revanche l'IHM Qt.

```bash
pip install -r requirements-dev.txt   # = pytest, pdoc
python -m pytest                      # toute la suite (mode simulation, sans matériel)
python -m pytest tests/test_controller.py -v   # un seul fichier, verbeux
```

Pour lancer l'IHM (Qt) — requise dans tous les cas, et le matériel réel :

```bash
pip install -r requirements-qt.txt    # PySide6 + matplotlib + reportlab (IHM, graphes, PDF)
python3 main.py                       # simulation par défaut ("simulate": true)

pip install -r requirements.txt       # pyvisa/nidaqmx (matériel réel)
python3 main.py --config config.json  # 'simulate': false dans le JSON
```

**Le même code tourne en simulation et en réel** : seuls les pilotes changent
(`MockPSU`/`MockDAQ` ↔ `HMP40xx`/`NIDaq`). Développe et teste en simulation ;
n'utilise le matériel que pour la validation finale.

---

## 2. Carte du code : où trouver quoi

| Besoin | Fichier |
|---|---|
| Ajouter/valider un champ de config | [alim_seq/config.py](../alim_seq/config.py) |
| Capacités d'appareil + registre unifié | [alim_seq/instrument.py](../alim_seq/instrument.py) |
| Pilote d'alimentation, registre des modèles | [alim_seq/psu.py](../alim_seq/psu.py) |
| Acquisition température (NI / mock thermique) | [alim_seq/daq.py](../alim_seq/daq.py) |
| Relais / actionneurs (capacité Actionneur) | [alim_seq/relay.py](../alim_seq/relay.py) |
| Conversion tension→°C (NTC, PT100, table…) | [alim_seq/temperature.py](../alim_seq/temperature.py) |
| Langage de séquence (parser + exécuteur) | [alim_seq/sequencer.py](../alim_seq/sequencer.py) |
| Orchestration, boucles, sécurité (cœur) | [alim_seq/controller.py](../alim_seq/controller.py) |
| Enregistrement CSV / dossier d'essai (mixin) | [alim_seq/controller_recording.py](../alim_seq/controller_recording.py) |
| Asservissement (mixin) | [alim_seq/controller_servo.py](../alim_seq/controller_servo.py) |
| Couplages simulés + réglage à chaud (mixin) | [alim_seq/controller_simtune.py](../alim_seq/controller_simtune.py) |
| Évaluateur d'expressions `SETV`/`SETI` | [alim_seq/expressions.py](../alim_seq/expressions.py) |
| Dossier d'essai (CSV + artefacts) | [alim_seq/essai.py](../alim_seq/essai.py) |
| Rapport d'essai (données, HTML, PDF ReportLab) | [alim_seq/rapport.py](../alim_seq/rapport.py) |
| IHM Qt (unique interface) | [alim_seq/gui_qt/](../alim_seq/gui_qt/) |
| Fixtures de test | [tests/conftest.py](../tests/conftest.py) |

Couches (bas → haut) : **pilotes** (`psu`, `daq`) → **domaine** (`config`,
`temperature`, `expressions`, `sequencer`) → **orchestration** (`controller`) →
**IHM** + **sorties** (`essai`, `rapport`). Une couche basse n'importe jamais une
couche haute. Le cœur (`alim_seq/`) **ne dépend pas de Qt** (testable et scriptable
sans IHM).

---

## 3. Conventions

- **Langue.** Application, IHM et docs en **français**. Les noms de code et
  commentaires mêlent français/anglais ; les **clés de configuration sont en
  anglais**. Respecte le style du fichier que tu modifies.
- **Docstrings = le *pourquoi*.** La signature dit déjà le *quoi*. Une docstring
  utile explique le contrat, les effets de bord (verrous pris, threads), et les
  décisions non évidentes. Ne documente pas un getter trivial ou un stub
  d'interface (`...`) : ce serait du bruit.
- **Sécurité prioritaire.** Toute modification touchant l'alimentation doit
  préserver l'invariant : *on ne laisse jamais la carte alimentée en cas de
  problème*. En cas de doute, on coupe.
- **Threads et verrous.** Voir §6 — c'est le piège n°1. Ne jamais inverser l'ordre
  d'acquisition des verrous.
- **Pas de dépendance nouvelle sans raison.** Le mode simulation doit rester
  installable-free. Une dépendance lourde (Qt, matplotlib) reste **optionnelle** et
  importée paresseusement.

---

## 4. Recettes « comment ajouter… »

### 4.1 Un nouveau modèle d'alimentation

Tout passe par le **registre** de [psu.py](../alim_seq/psu.py). Le reste de l'appli
(config, IHM, validation, simulation) s'adapte automatiquement.

1. Écrire une sous-classe de `BasePSU` (ou de `HMP4040` si même famille SCPI).
   Implémenter `set_voltage/current/output`, `measure_voltage/current`, et de
   préférence `measure_status` (mode CV/CC + défauts). Définir `n_channels`,
   `model`, et les limites SOA `max_voltage/max_current/max_power`.
2. L'enregistrer dans `PSU_MODELS` :
   ```python
   PSU_MODELS = {..., "NGP804": NGP804}
   ```
3. C'est tout. `create_psu` fabrique un `MockPSU` (bon nombre de voies) en
   simulation et le vrai pilote en réel ; la validation de config accepte le
   nouveau modèle et vérifie les canaux/limites.
4. Ajouter un test dans [tests/test_psu.py](../tests/test_psu.py).

### 4.2 Un nouveau convertisseur de température

Dans [temperature.py](../alim_seq/temperature.py) :

1. Sous-classer `TemperatureConverter`, implémenter `to_celsius(voltage) -> float`.
   **Convention de défaut** : si la mesure n'est pas fiable (capteur débranché,
   tension collée à un rail), retourner `float("nan")` — le contrôleur le classe en
   `FAULT` et l'exclut de la sécurité (jamais une fausse valeur plausible).
2. L'enregistrer dans `_CONVERTERS` (factory lambda lisant le dict de config) :
   ```python
   _CONVERTERS["mon_type"] = lambda c: MonConverter(param=c["param"])
   ```
3. Si des garde-fous de config sont nécessaires (ex. bande de plausibilité
   obligatoire), les ajouter dans `_validate` de [config.py](../alim_seq/config.py).
4. Tester dans [tests/test_temperature.py](../tests/test_temperature.py).

### 4.3 Une nouvelle commande de séquence

Dans [sequencer.py](../alim_seq/sequencer.py), une commande vit à **trois** endroits :

1. **Validation** — ajouter un cas dans `_validate_action` (nombre d'arguments via
   `_need`, labels via `_check_label`, nombres via `_num`, clés `clé=valeur` via
   `_check_kwargs` avec une liste blanche). *Une séquence validée ne doit jamais
   échouer en cours pour une faute de syntaxe.*
2. **Exécution** — ajouter un cas dans `SequenceRunner._execute`, qui route vers une
   primitive du `Controller`. Retourner `True` (succès, on enchaîne) ou `False`
   (échec/interruption). Pour toute attente, utiliser `self._sleep()` (interruptible)
   et vérifier `self._aborted()`.
3. **Documentation** — mettre à jour la docstring d'en-tête du module (grammaire),
   l'Annexe A du manuel, et l'aide intégrée de l'IHM.

### 4.4 Un nouveau modèle de relais (ou tout nouvel actionneur)

L'abstraction **par capacités** ([instrument.py](../alim_seq/instrument.py)) rend
l'ajout local : le cœur (verrous, boucles, sécurité) n'est pas touché.

1. Sous-classer `BaseRelay` dans [relay.py](../alim_seq/relay.py) : implémenter
   `connect/close`, `set_state(label, on)`, `get_state(label)`. Régler `model`.
2. L'enregistrer côté registre : ajouter le nom de driver à `_RELAY_DRIVERS` et le
   construire dans `create_instrument` (branche actionneur) de
   [instrument.py](../alim_seq/instrument.py) — mock en simulation, vrai pilote en réel
   (parité). L'ajouter aussi à `available_instruments()` et au dict `INSTRUMENTS`.
3. C'est tout. La config le déclare dans `instruments` (`{"driver": "<NOM>",
   "outputs": {…}}`), le séquenceur (`RELAY`), le contrôleur (`set_relay`, état de
   sécurité) et le `snapshot` le prennent en charge automatiquement.
4. Tester dans [tests/test_relay.py](../tests/test_relay.py).

Pour une capacité **entièrement nouvelle** (ni source, ni température, ni actionneur),
définir un mixin fin dans `instrument.py`, l'exposer via `driver_role`, et faire
itérer le contrôleur `isinstance(instr, MaCapacité)` là où c'est pertinent — sans
casser l'invariant d'ordre des verrous (§6).

### 4.5 Un nouveau champ de configuration

Dans [config.py](../alim_seq/config.py) :

1. Ajouter le champ à la `@dataclass` concernée (avec une valeur par défaut → rétro-
   compatibilité des configs existantes).
2. Le lire dans `load_config` (`raw.get("...", defaut)`, avec conversion de type).
3. L'écrire dans `config_to_dict` (miroir exact : *ce que load lit, dict doit
   l'écrire*, pour que l'archivage d'essai recharge à l'identique).
4. Le valider dans `_validate` si des contraintes s'appliquent.
5. Test dans [tests/test_config.py](../tests/test_config.py).

---

## 5. Tests

- La suite tourne **exclusivement en simulation** (mocks) : ni matériel, ni réseau.
- Les fixtures sont dans [tests/conftest.py](../tests/conftest.py) : une config
  construite **en code** (indépendante de `config.json`) couvrant les cas délicats —
  voie négative, groupe série, groupe à cheval sur deux alims, couplage grille→drain,
  capteur conditionné à une voie.
- Le contrôleur des tests est connecté mais **polling arrêté** pour un déterminisme
  total (pas de threads de fond qui interfèrent).
- Config pytest : [pytest.ini](../pytest.ini).

Écris un test pour tout comportement métier ou correctif de sécurité. Reproduis le
style existant (fixtures partagées, un fichier par module).

---

## 6. Pièges à connaître (⚠️ lire avant de toucher au contrôleur)

- **Ordre des verrous — invariant.** Un `RLock` **par instrument** (`_instr_locks[nom]`,
  alims comme instrument de température) + un pour l'état. Ordre d'acquisition
  **toujours** : `verrou(s) instrument (ordre alphabétique du nom) → _state_lock`.
  L'inverser peut provoquer un interblocage. Pour un groupe/une action multi-alims,
  utiliser le context manager `_lock_for(label)` (verrouille toutes les alims triées) ;
  `_all_instr_locked()` verrouille tous les instruments (connect/reconnect/close).
- **La boucle de sécurité ne prend AUCUN verrou de source.** Elle ne verrouille que
  l'instrument de température, pour qu'un VISA figé sur une alim ne puisse jamais
  retarder une coupure.
- **Deux boucles indépendantes.** Température (rapide, sécurité) et V/I (lente,
  affichage) tournent séparément. Ne les fusionne pas.
- **La désalimentation de sécurité prime sur tout.** Elle s'exécute même verrou armé,
  ignore l'arrêt utilisateur et la pause. Ne « corrige » pas ce comportement.
- **Tension signée vs magnitude.** Le logiciel raisonne en tensions **signées**
  (rail négative = valeur négative) ; seule la **magnitude** est programmée sur le
  HMP (qui ne sort que du positif). Le clamp de `_clamp` respecte la polarité.
- **`config_to_dict` est le miroir de `load_config`.** Si tu ajoutes un champ à l'un,
  ajoute-le à l'autre, sinon l'archivage de config d'un essai diverge.

---

## 7. Documentation de l'API (pdoc)

Les docstrings du code génèrent une **doc HTML navigable** via
[pdoc](https://pdoc.dev) (léger, sans configuration) :

```bash
pip install -r requirements-dev.txt   # inclut pdoc
tools/build-apidoc.sh                  # -> docs/api/index.html
# ou directement :
python -m pdoc alim_seq -o docs/api
python -m pdoc alim_seq                # serveur live sur http://localhost:8080
```

`docs/api/` est un artefact régénérable (ignoré par git). Régénère-le après une
évolution notable de l'API.

**Manuel utilisateur.** La source unique est [MANUEL_UTILISATEUR.md](MANUEL_UTILISATEUR.md)
(qui sert aussi l'aide intégrée **F1**). Les formats `.pdf`/`.docx` sont des artefacts
**régénérables** (ignorés par git) produits par `tools/build-manual.sh` (pandoc). Le
build Windows embarque le `.pdf` s'il est présent : régénère-le avant un build pour
livrer un manuel à jour.

---

## 8. Construire les exécutables Windows

La production de l'installateur et de l'exe portable se fait par CI auto-hébergée
(Forgejo + VM Windows à la demande) : `tools/lab-build.sh <tag>`. Tous les détails
(prérequis, méthode manuelle, dépannage) sont dans [TOOLCHAIN.md](TOOLCHAIN.md).

---

## 9. Cycle de contribution

1. Développer et **tester en simulation** (`python -m pytest`).
2. Mettre à jour la doc concernée : docstrings, ce guide, ARCHITECTURE.md, le manuel
   et l'aide intégrée si le comportement visible change.
3. Valider sur **matériel réel** si la modification touche un pilote ou la sécurité.
4. Mettre à jour [CHANGELOG.md](../CHANGELOG.md).
5. Taguer `v*` pour déclencher un build (voir §8).
