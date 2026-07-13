# Note de conception — Abstraction des appareils par capacités

Statut : **phases 1 à 4 réalisées** — l'abstraction est posée et validée par les
relais (première capacité neuve, ajoutée sans toucher au cœur).
Objectif : cadrer *quoi* on change, *dans quel ordre*, et *ce qu'on ne casse pas*.

## 1. Problème

Aujourd'hui l'architecture matérielle repose sur **deux hiérarchies parallèles et
figées** :

- `psu.py` : `BasePSU` → `HMP4040`/… + `MockPSU`, agrégées par `PSUManager`
  (routage `label → (alim, canal)`).
- `daq.py` : `BaseDAQ` → `NIDaq` + `MockDAQ`.

Le contrôleur les câble en dur : `self._psu` (un `PSUManager`), `self._daq` (un
`BaseDAQ`), un verrou **par alimentation** (`_psu_locks`) + **un** verrou DAQ
(`_daq_lock`). La config a des sections dédiées `supplies` et `daq`.

Conséquence : **tout nouveau type d'appareil** (relais, charge électronique,
multimètre, capteur I²C…) exige une troisième hiérarchie + son câblage dans le
contrôleur + sa section de config. Ça ne « scale » pas et ça présage des catégories
d'appareils (« une alim », « un DAQ ») qu'on ne veut plus présager.

## 2. Idée directrice : capacité, pas catégorie

Un appareil n'**est** plus « une alim » ou « un DAQ » : il **déclare les capacités**
qu'il expose. Le contrôleur ne parle plus qu'aux capacités.

### Capacités (mixins/ABC **fins** — garde-fou anti sur-abstraction)

| Capacité | Méthodes (indexées par voie/point/label) | Portée aujourd'hui |
|---|---|---|
| `SourceTension` | `set_voltage`, `set_output`, `set_current` (limite) | alim (plus tard : charge en sink) |
| `MesureVI` | `measure_voltage`, `measure_current`, `measure_status` | alim, multimètre |
| `MesureTemperature` | `read_all() -> {point: °C}` (tension brute incluse) | module NI, capteur I²C |
| `Actionneur` | `set_state(label, on)`, `get_state(label)` | relais, GPIO |

Un HMP4040 implémente `SourceTension` **et** `MesureVI`. Un module NI implémente
`MesureTemperature`. Un relais implémente `Actionneur`. Rien n'empêche un futur
appareil de cumuler des capacités inédites.

Les capacités sont des **classes-marqueurs** (ABC minces). Le contrôleur découvre
« qui sait faire quoi » par `isinstance(instr, MesureTemperature)` — pas de registre
de capacités, pas d'« usine d'usines ».

### Cycle de vie commun

```python
class Instrument:
    name: str          # nom logique (clé de config, clé de verrou)
    model: str         # modèle réel ("HMP4040", "MockPSU"…)
    def connect(self) -> None: ...
    def close(self) -> None: ...
```

`PSUManager` disparaît en tant que classe centrale : le **routage par label**
(`VCC → (instrument, voie)`) devient une responsabilité du contrôleur, appliquée
uniformément à toutes les capacités adressables.

## 3. Registre unifié + fabrique

Généralise le pattern déjà éprouvé `PSU_MODELS` / `create_psu` :

```python
INSTRUMENTS: Dict[str, type] = {
    "HMP4040": HMP4040, "HMP4030": HMP4030, ...,   # sources
    "NI-DAQ": NIDaq,                                # températures
    # "USB-RELAY-8": Relay8, ...                    # actionneurs (§ROADMAP 4)
}

def create_instrument(driver, simulate, **params) -> Instrument: ...
```

`create_instrument` fabrique le **mock** correspondant en simulation (parité) et le
driver réel sinon — exactement comme `create_psu` aujourd'hui. `PSU_MODELS`/
`create_psu` restent comme **façade rétrocompatible** au-dessus (zéro rupture pour
`config.py` et les tests PSU existants).

## 4. Config : `instruments`, avec `supplies`/`daq` comme sucre rétrocompatible — ✅ **fait**

Section **canonique** unifiée (chaque entrée : un `driver` + ses paramètres) :

```json
"instruments": {
  "PSU_A":  {"driver": "HMP4040", "resource": "TCPIP0::…::INSTR"},
  "TEMP":   {"driver": "NI-DAQ",  "device": "Dev1"},
  "RELAYS": {"driver": "USB-RELAY-8", "resource": "ASRL3::INSTR"}
}
```

`channels`/`groups` référencent un instrument source par son nom (clé `supply`, qui
désigne désormais n'importe quel instrument source) ; `temperatures` reste rattaché à
l'unique instrument de température. **Les `outputs` de relais** seront une nouvelle
section adressable (§ROADMAP 4).

**Rétrocompatibilité garantie** (`AppConfig.__post_init__`) : `instruments` **fait
foi** ; s'il est absent, il est dérivé de `supplies`+`daq` ; s'il est présent,
`supplies`/`daq` en sont (re)dérivés — les deux vues restent cohérentes quel que soit
le format d'entrée. Les `config.json` existants et les configs archivées se
rechargent **à l'identique**. `config_to_dict` émet les deux et reste le miroir exact
(invariant §DEVELOPPEMENT 6). Validation : `driver` connu, au plus **un** instrument
de température (modèle actuel).

## 5. Contrôleur : généraliser ce qui existe déjà

Le contrôleur possède **déjà** l'essentiel de la mécanique ; il s'agit de la rendre
générique, pas de la réécrire :

- **Verrous** : `_psu_locks` + `_daq_lock` → un dict unique `_instr_locks[name]`,
  un `RLock` par instrument. **Invariant d'ordre préservé et généralisé** :
  acquisition **par ordre alphabétique du nom d'instrument**, puis `_state_lock`.
- **Boucle de mesure V/I** : itère les instruments `MesureVI` au lieu de `self._psu`.
- **Boucle de sécurité (température)** : itère les instruments `MesureTemperature`.
  ⚠️ **Elle ne prend AUCUN verrou de source** (invariant sûreté) — inchangé : elle ne
  verrouille que l'instrument température qu'elle interroge.
- **Désalimentation ordonnée** : agit sur tous les `SourceTension` (et demain les
  `Actionneur` participant à l'isolement — §ROADMAP 4).

Le point délicat est **l'ordre des verrous** : passer de « toutes les alims (alpha) →
daq → state » à « tous les instruments (alpha) → state » élargit l'ensemble trié mais
**conserve la propriété** (un ordre total unique, jamais inversé). La boucle sécurité
restant cantonnée à son seul instrument température, elle ne peut toujours pas être
retardée par une source figée.

## 6. Découpage en phases (chaque phase livrable et testée seule)

1. **Capacités + `Instrument`** (nouveau module `alim_seq/instrument.py`), sans rien
   débrancher : `HMP4040`/`MockPSU` héritent des mixins `SourceTension`+`MesureVI`,
   `NIDaq`/`MockDAQ` de `MesureTemperature`. `INSTRUMENTS`/`create_instrument`
   enveloppent `create_psu`. **Aucun changement de comportement**, tests verts. ✅ **fait**
2. **Contrôleur générique** : `_psu_locks`+`_daq_lock` → un `_instr_locks` unifié
   (verrou par instrument, ordre alphabétique), boucles par capacité, routage label
   centralisé (`_route`), `_build_instruments`/`create_instrument`. `PSUManager`
   **supprimé**. Aucun changement de comportement, 181 tests verts. ✅ **fait**
3. **Config `instruments`** + traduction rétrocompatible `supplies`/`daq`, contrôleur
   qui consomme `instruments`, validation, round-trip `load_config`↔`config_to_dict`
   sur les deux formats. 186 tests verts. ✅ **fait**
4. **`Actionneur` + relais** (bascule sur §ROADMAP 4) : première validation concrète
   du modèle — driver `relay.py` (`BaseRelay`/`MockRelay`), instrument déclaré dans
   `instruments` avec ses `outputs`, commande `RELAY <sortie> ON|OFF` au séquenceur,
   `set_relay`/`relay_state` au contrôleur, et **participation à la désalimentation**
   (état de sécurité `safe_state` par sortie, appliqué à l'arrêt d'urgence et en fin
   de désalimentation ordonnée). Le **cœur n'a pas été modifié structurellement** — la
   preuve que l'abstraction tient. 195 tests verts. ✅ **fait**

Phases 1–3 = le refactor structurant (pas de fonctionnalité visible nouvelle, risque
maîtrisé par la parité de tests). Phase 4 = la première capacité neuve qui *prouve*
que l'abstraction tient sans toucher au cœur.

## 7. Ce qu'on ne casse pas (contrats à préserver)

- Règle d'or sûreté : **jamais la carte alimentée en cas de problème** ; la boucle
  thermique reste indépendante et prioritaire, sans verrou de source.
- **Parité simulation/réel** : chaque driver réel a son mock.
- **Cœur sans Qt** : l'abstraction vit dans `alim_seq/`, testable sans IHM.
- **Rétrocompat config** : les `config.json` et dossiers d'essai existants se
  rechargent sans modification.
- Invariant `config_to_dict` = miroir de `load_config`.

## 8. Points ouverts — **arbitrés**

- **Granularité `SourceTension` vs `LimiteCourant`** → **fusionnées**. Une seule
  capacité `SourceTension` portant aussi la limite de courant (indissociable sur une
  alim de labo). On scindera plus tard si une charge en sink le justifie.
- **`PSUManager`** → **retiré du cœur**. Le routage label→(instrument, voie) est
  centralisé dans le contrôleur ; `PSUManager` est supprimé s'il n'est plus exercé
  directement par des tests.
- **Adressage** (encore ouvert) : voies numériques (alim, 1..N) vs points nommés
  (capteurs) vs labels (relais). Proposition retenue : chaque capacité définit sa clé
  d'adressage propre ; le routage label→(instrument, clé) du contrôleur reste le point
  d'entrée unique côté métier.
