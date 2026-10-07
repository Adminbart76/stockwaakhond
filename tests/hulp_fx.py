"""Een kloppend wisselkoersbewijs voor een testwissel.

Sinds auditronde 5 (7 oktober 2026) kan een wissel niet meer gebouwd worden
zonder het bewijs van de wisselkoers: de minuutbalk van de slotbel en het
ECB-controlegetal. Dat is met opzet zo, want zonder dat bewijs kan een latere
lezer de koers niet narekenen - Yahoo bewaart minuutgegevens ongeveer dertig
dagen.

Elke test die een wissel bouwt, heeft dus zo'n bewijs nodig. Het wordt hier
opgebouwd uit de slotbel van die dag, en niet met vaste tijdstempels: dan blijft
het ook in de wintertijd kloppen, want de slotbel verschuift mee met de
tijdzone van New York.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Optional

import pandas as pd

from sw import fx as fxr


def bewijs_voor(
    datum,
    fx_rate: float,
    controle: Optional[float] = None,
    seconden_voor_slotbel: int = 0,
) -> dict:
    """Een volledig en kloppend bewijs voor die uitvoeringsdag.

    `seconden_voor_slotbel` schuift de balk naar achteren, voor de tests die de
    terugval van maximaal vijf minuten nakijken. Nul is de normale balk van
    15:59 tot 16:00.
    """
    slotbel = fxr.slotbel_op(datum)
    eind = slotbel - timedelta(seconds=seconden_voor_slotbel)
    begin = eind - timedelta(minutes=1)

    if controle is None:
        # Een realistisch verschil: de ECB stelt haar koers zes uur eerder vast
        # in Frankfurt, dus een tiende procent verschil is gewoon de dag.
        controle = round(float(fx_rate) * 0.999, 10)

    return {
        "fx_bar_start": begin.isoformat(),
        "fx_bar_end": eind.isoformat(),
        "fx_bar_normaal": eind == slotbel,
        "fx_control_source": fxr.ECB_BRON,
        "fx_control_date": str(pd.Timestamp(datum).date()),
        "fx_control_rate": controle,
        "fx_control_same_day": True,
        "fx_control_deviation_pct": fxr.vergelijk(
            float(fx_rate), float(controle))["afwijking_pct"],
    }
