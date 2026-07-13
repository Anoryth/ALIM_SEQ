# Guide d'intégration de drivers d'appareils

Ce guide s'adresse aux **contributeurs** qui veulent brancher un nouvel appareil
(alimentation, module de mesure, relais, ou tout autre instrument) sur ALIM_SEQ.
L'architecture est conçue pour que **le reste de l'application s'adapte
automatiquement** : config, IHM, séquenceur, simulation, validation.

Pour l'architecture d'ensemble, voir [ARCHITECTURE.md](ARCHITECTURE.md) ; pour la
conception du modèle par capacités, [DESIGN_INSTRUMENTS.md](DESIGN_INSTRUMENTS.md).

---

## 1. Le modèle mental : **capacités**, pas catégories

Un appareil n'est pas « une alim » ou « un DAQ ». C'est un
[`Instrument`](../alim_seq/instrument.py) (cycle de vie `connect`/`close` + identité)
qui **déclare les capacités** qu'il expose :

| Capacité | Ce qu'elle promet | Exemples |
|---|---|---|
| `SourceTension` | imposer une tension + limite de courant, couper | alim, charge en sink |
| `MesureVI` | mesurer V/I (+ mode CV/CC, défauts) | alim, multimètre |
| `MesureTemperature` | fournir des °C par point + tensions brutes | module NI, capteur I²C |
| `Actionneur` | ouvrir/fermer une sortie logique | relais, GPIO |

Une alimentation implémente **`SourceTension` + `MesureVI`**. Le contrôleur ne parle
qu'aux capacités (`isinstance(instr, MesureTemperature)`), jamais aux types concrets.
Un appareil peut cumuler des capacités inédites.

Chaque instrument est fabriqué par un **registre unifié** :
[`create_instrument(driver, simulate, name, **params)`](../alim_seq/instrument.py).

**Deux règles d'or, non négociables** (elles définissent l'identité du projet) :

1. **Parité simulation / réel.** Tout driver réel a un **mock** au comportement
   plausible. Le même code doit tourner en simulation (sans matériel) et en réel.
2. **Sûreté d'abord.** `close()` doit **couper les sorties** même si l'appareil est
   lent/mal en point ; une mesure non fiable doit se signaler en **défaut**, jamais
   renvoyer une valeur plausible fausse. Le driver **ne prend aucun verrou** : la
   sérialisation est faite par le contrôleur (un verrou par instrument).

---

## 2. Cas le plus fréquent : une nouvelle **alimentation**

### 2.1 Même famille SCPI que les R&S HMP

Si l'appareil parle le même dialecte que les HMP40xx (beaucoup d'alims R&S/HMC),
sous-classez [`HMP4040`](../alim_seq/psu.py) et ajustez ce qui diffère :

```python
# alim_seq/psu.py
class HMP2020(HMP4040):
    """R&S HMP2020 — même famille SCPI, 2 voies."""
    n_channels = 2
    model = "HMP2020"
    # Limites SOA par voie (datasheet) — servent à VALIDER la config :
    max_voltage = 32.0
    max_current = 10.0
    max_power = 80.0
```

### 2.2 Un dialecte différent (nouvelle marque)

Sous-classez directement [`BasePSU`](../alim_seq/psu.py) (qui est déjà
`Instrument + SourceTension + MesureVI`) et implémentez le contrat :

```python
class NGP804(BasePSU):
    """Exemple : R&S NGP804 (4 voies). Adaptez à VOTRE appareil."""
    n_channels = 4
    model = "NGP804"
    max_voltage, max_current, max_power = 64.0, 20.0, 200.0   # SOA / voie

    def __init__(self, resource, visa_backend="", use_cc_status=False,
                 query_delay_s=0.0, log=None, **_):
        self.resource = resource
        self.visa_backend = visa_backend
        self._log = log or (lambda _m: None)
        self._inst = None

    # --- cycle de vie ----------------------------------------------------
    def connect(self):
        import pyvisa                                   # import PARESSEUX
        rm = pyvisa.ResourceManager(self.visa_backend) if self.visa_backend \
            else pyvisa.ResourceManager()
        self._inst = rm.open_resource(self.resource)
        self._inst.read_termination = self._inst.write_termination = "\n"
        self.idn = str(self._inst.query("*IDN?")).strip()   # échec RAPIDE si muet

    def close(self):
        # IMPÉRATIF : couper les sorties, sans se bloquer si l'appareil ne répond
        # plus (timeout court), puis fermer la session quoi qu'il arrive.
        if self._inst is None:
            return
        try:
            self.all_outputs_off()
        except Exception:
            pass
        finally:
            try:
                self._inst.close()
            finally:
                self._inst = None

    # --- capacité SourceTension -----------------------------------------
    def set_voltage(self, channel, voltage):
        self._inst.write(f"INST:NSEL {channel}"); self._inst.write(f"VOLT {voltage:.4f}")

    def set_current(self, channel, current):
        self._inst.write(f"INST:NSEL {channel}"); self._inst.write(f"CURR {current:.4f}")

    def set_output(self, channel, on):
        self._inst.write(f"INST:NSEL {channel}"); self._inst.write(f"OUTP {int(on)}")

    # --- capacité MesureVI ----------------------------------------------
    def measure_voltage(self, channel):
        self._inst.write(f"INST:NSEL {channel}"); return float(self._inst.query("MEAS:VOLT?"))

    def measure_current(self, channel):
        self._inst.write(f"INST:NSEL {channel}"); return float(self._inst.query("MEAS:CURR?"))

    def measure_status(self, channel):
        """Retourne {'mode': 'CV'|'CC'|None, 'faults': [...]}. Si l'appareil ne sait
        pas dire, renvoyez {'mode': None, 'faults': []} : le contrôleur infère le
        mode depuis V/I. 'faults' peut contenir 'OVP', 'FUSE', 'OTP'."""
        return {"mode": None, "faults": []}
```

> `set_voltage` reçoit une **magnitude positive** : le logiciel gère la polarité des
> rails négatifs (les alims ne sortent que du positif). Ne réinventez pas le signe.

### 2.3 Enregistrer le modèle

Ajoutez la classe au registre — **c'est tout** :

```python
# alim_seq/psu.py, en bas
PSU_MODELS = {..., "NGP804": NGP804}
```

`create_psu` fabrique alors un `MockPSU` (bon nombre de voies) en simulation et votre
driver en réel ; la validation de config accepte le modèle et vérifie voies/limites ;
l'IHM le propose dans le menu déroulant et l'assistant de configuration.

**La simulation est déjà couverte** : `MockPSU` (charge résistive + bruit, nombre de
voies paramétrable) sert de mock pour *tout* modèle de source. Vous n'avez rien à
écrire pour la parité.

---

## 3. Autres capacités

### 3.1 Module de mesure de température

Sous-classez [`BaseDAQ`](../alim_seq/daq.py) (`Instrument + MesureTemperature`) :

```python
class MonDAQ(BaseDAQ):
    def __init__(self, device, sensors): ...
    def connect(self): ...
    def close(self): ...
    def read_temperatures(self) -> dict:   # {nom_capteur: °C}
        ...
    def read_voltages(self) -> dict:       # {nom_capteur: V bruts}  (filet de sécurité)
        ...
```

**Détection de défaut obligatoire** : une mesure non fiable (capteur débranché,
entrée collée à un rail) doit produire `float("nan")` — le contrôleur la classe en
`FAULT` et l'exclut de la sécurité. Ne renvoyez **jamais** une température plausible
inventée (voir la logique des convertisseurs dans
[temperature.py](../alim_seq/temperature.py), qui renvoient `NaN` en défaut).

Enregistrement (branche température de `create_instrument`) : ajoutez un alias dans
`_NIDAQ_ALIASES` (ou une clé de driver dédiée) et instanciez votre classe dans la
branche correspondante d'[instrument.py](../alim_seq/instrument.py). Fournissez un
mock (modèle simple) pour la simulation, comme `MockDAQ`.

### 3.2 Relais / actionneur

Sous-classez [`BaseRelay`](../alim_seq/relay.py) (`Instrument + Actionneur`) :

```python
class MonRelais(BaseRelay):
    def connect(self): ...
    def close(self): self.all_off()        # état de repos sûr
    def set_state(self, label, on): ...     # ferme/ouvre une sortie
    def get_state(self, label): ...         # relit l'état (ou None)
```

Enregistrement : ajoutez le nom de driver à `_RELAY_DRIVERS`, construisez la classe
dans la branche actionneur de `create_instrument`, et ajoutez-la au dict `INSTRUMENTS`
+ `available_instruments()`. Le mock `MockRelay` sert la simulation. Le reste (config
`instruments.<nom>.outputs`, commande de séquence `RELAY`, primitive contrôleur
`set_relay`, état de sécurité, affichage IHM) est **déjà branché**.

### 3.3 Une capacité entièrement nouvelle

Définissez un **mixin fin** dans [instrument.py](../alim_seq/instrument.py) (méthodes
en `...`, pas de sur-abstraction), faites-le hériter à votre driver, exposez-le via
`driver_role`, et faites itérer le contrôleur `isinstance(instr, MaCapacité)` là où
c'est pertinent — **sans casser l'invariant d'ordre des verrous** (voir
[DEVELOPPEMENT.md §6](DEVELOPPEMENT.md)).

---

## 4. Le contrat, en dur

Tout driver DOIT respecter :

- **`connect()`** : échouer **vite et clairement** si la liaison ne répond pas
  (sondez `*IDN?` tôt), avec un message actionnable. Imports matériels (`pyvisa`,
  `nidaqmx`) **paresseux** (pas requis en simulation).
- **`close()`** : **couper les sorties** puis fermer, sans se bloquer si l'appareil
  est muet (raccourcir le timeout). C'est un point de sûreté, pas une politesse.
- **Détection de défaut** : signaler (défaut / `NaN`) une mesure non fiable ; ne
  jamais renvoyer une valeur plausible fausse.
- **Limites SOA** (`max_voltage/current/power`) renseignées depuis la datasheet —
  elles servent à **rejeter** une config dangereuse à la validation.
- **Aucun verrouillage** dans le driver : le contrôleur sérialise (un verrou par
  instrument). Vos méthodes sont appelées sous ce verrou ; ne créez pas de threads.
- **Parité simulation** : fournir/réutiliser un mock. `MockPSU`/`MockDAQ`/`MockRelay`
  couvrent déjà les trois capacités existantes.

---

## 5. Tester

- Ajoutez un test dans le fichier du module (`tests/test_psu.py`,
  `tests/test_instrument.py`, `tests/test_relay.py`…). La suite tourne
  **exclusivement en simulation** (ni matériel, ni réseau).
- Vérifiez au minimum : les **capacités** exposées (`isinstance` / `capabilities_of`),
  la **fabrique** (`create_instrument("VOTRE-DRIVER", simulate=True)` renvoie le mock),
  et la **validation** de config (modèle connu, voies/limites cohérentes).
- Validez **sur matériel réel** avant de proposer le driver pour un usage critique —
  la simulation ne prouve pas le dialecte SCPI ni le comportement de sûreté réel.

```bash
python -m pytest tests/test_instrument.py -v
```

---

## 6. Récapitulatif : intégrer un driver en 4 pas

1. Écrire la classe (sous-classe de `BasePSU` / `BaseDAQ` / `BaseRelay` / nouvelle
   capacité), en respectant le **contrat §4**.
2. L'**enregistrer** (`PSU_MODELS` pour une source ; branche de `create_instrument`
   + `available_instruments()`/`INSTRUMENTS` pour les autres familles).
3. Assurer la **parité simulation** (réutiliser un mock existant, ou en écrire un).
4. **Tester** en simulation, puis valider sur matériel réel.

Le reste — config, IHM, séquenceur, assistant, rapport — s'adapte **tout seul**.

> Rugosité connue : enregistrer une **source** ne demande qu'une ligne dans
> `PSU_MODELS` ; une capacité **température/actionneur** demande encore d'éditer la
> branche correspondante de `create_instrument`. Uniformiser cela (un registre de
> familles piloté par métadonnées) est un chantier ouvert bienvenu — voir
> `DESIGN_INSTRUMENTS.md`.
