"""T3 : découplage des verrous matériels.

On vérifie que :
  - _lock_for résout un label vers la/les bonne(s) alim(s) et, pour un groupe à
    cheval sur deux alims, verrouille TOUTES ses alims ;
  - une alim figée (verrou tenu, VISA bloqué) ne retarde ni la boucle thermique,
    ni la coupure d'urgence des AUTRES alims (critère d'acceptation n°2).
"""

import time

import pytest


def test_lock_for_single_channel(ctrl):
    # Une voie -> une seule alim (celle qui la porte).
    assert ctrl._supply_names_for("D1") == ["PSU1"]
    assert ctrl._supply_names_for("AUX") == ["PSU2"]


def test_lock_for_group_spanning_two_supplies(ctrl):
    # Groupe SPAN = [D1(PSU1), AUX(PSU2)] -> les deux alims, triées.
    assert ctrl._supply_names_for("SPAN") == ["PSU1", "PSU2"]
    # Et _lock_for prend effectivement les deux verrous (réentrant : on peut set).
    with ctrl._lock_for("SPAN"):
        assert ctrl._instr_locks["PSU1"].acquire(blocking=False)
        ctrl._instr_locks["PSU1"].release()
        assert ctrl._instr_locks["PSU2"].acquire(blocking=False)
        ctrl._instr_locks["PSU2"].release()


def test_lock_for_group_intragroup(ctrl):
    # DRAIN = [D1, D2] tous deux sur PSU1 -> une seule alim, pas de doublon.
    assert ctrl._supply_names_for("DRAIN") == ["PSU1"]


def test_frozen_supply_does_not_block_temp_loop(ctrl):
    # PSU2 « figée » : son verrou est tenu par un tiers. La boucle thermique ne
    # dépend que de _instr_locks[ctrl._daq_name] -> elle ne doit PAS être retardée.
    ctrl._instr_locks["PSU2"].acquire()
    try:
        t0 = time.monotonic()
        ctrl._temp_cycle()          # ne doit pas bloquer sur PSU2
        assert time.monotonic() - t0 < 0.2
    finally:
        ctrl._instr_locks["PSU2"].release()


def test_frozen_supply_does_not_block_emergency_of_others(ctrl):
    # PSU1 figée (verrou tenu ailleurs) : emergency_stop doit quand même couper,
    # sans attendre plus de ~0.2s (acquisition en non bloquant).
    ctrl.set_output("AUX", True)     # sur PSU2
    ctrl._instr_locks["PSU1"].acquire()
    try:
        t0 = time.monotonic()
        ctrl.emergency_stop("test alim figée")
        elapsed = time.monotonic() - t0
    finally:
        ctrl._instr_locks["PSU1"].release()
    assert elapsed < 0.2
    assert ctrl.get_setpoint("AUX").output is False   # PSU2 coupée malgré PSU1 figée
    assert ctrl.tripped is True


def test_meas_cycle_isolates_supplies(ctrl):
    # _meas_cycle mesure alim par alim : on vérifie qu'il tourne sans deadlock et
    # met à jour l'état de voies portées par DEUX alims différentes.
    ctrl.set_current("D1", 1.0)
    ctrl.set_voltage("D1", 5.0)
    ctrl.set_output("D1", True)     # PSU1
    ctrl.set_output("AUX", True)    # PSU2
    ctrl._meas_cycle()
    assert isinstance(ctrl.get_setpoint("D1").meas_current, float)
    assert isinstance(ctrl.get_setpoint("AUX").meas_current, float)
