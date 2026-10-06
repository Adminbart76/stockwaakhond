"""Het append-only forward-logboek: lezen, controleren, en alleen toevoegen.

In dit bestand bestaat met opzet geen functie om een bestaand signaal te
wijzigen, te verwijderen, te vervangen of opnieuw te berekenen. Dat is geen
vergetelheid maar de kern van de hele opzet. Voeg zo'n functie ook later niet
toe: zonder die mogelijkheid is de forward-test onweerlegbaar, met die
mogelijkheid is hij waardeloos.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Tuple

import pandas as pd

from .strategy import (
    STRATEGY_HASH,
    STRATEGY_VERSION,
    canonical_json,
    sha256_text,
    spec_hash,
)

MINIMUM_DAYS_BETWEEN_SIGNALS = 28


def read_ledger(ledger_file: Path) -> List[dict]:
    """Leest het logboek. Een bestand dat nog niet bestaat is gewoon leeg."""
    if not ledger_file.exists():
        return []

    rows = []
    with ledger_file.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def verify_ledger(entries: List[dict]) -> Tuple[bool, str]:
    """Controleert de volledige hash-keten.

    Drie controles per regel:
      1. verwijst deze regel naar de juiste voorganger?
      2. levert de inhoud nog steeds dezelfde entry_hash op?
      3. hoort de strategy_hash van de regel bij de formule in diezelfde regel?

    Controle 3 is strenger dan de oorspronkelijke versie, die elke oude regel
    vergeleek met de formule die op dat moment in de code stond. Daardoor zou
    een tweede, experimentele strategie het hele oude logboek ongeldig
    verklaren, terwijl er niets mis mee is. Elke regel draagt zijn eigen
    formule bij zich, dus die regel kan zichzelf bewijzen.
    """
    prev_hash = "GENESIS"
    for i, entry in enumerate(entries, start=1):
        stored_hash = entry.get("entry_hash")
        payload = dict(entry)
        payload.pop("entry_hash", None)

        if payload.get("previous_hash") != prev_hash:
            return False, f"Ketenbreuk bij regel {i}: previous_hash klopt niet."

        calculated = sha256_text(canonical_json(payload))
        if calculated != stored_hash:
            return False, f"Hashfout bij regel {i}: inhoud is gewijzigd."

        formula_spec = payload.get("formula_spec")
        if formula_spec is None:
            return False, f"Regel {i} mist de formule-omschrijving."

        if spec_hash(formula_spec) != payload.get("strategy_hash"):
            return False, (
                f"Regel {i}: de strategiehash hoort niet bij de formule in dezelfde regel."
            )

        prev_hash = stored_hash

    return True, f"Ledger intact ({len(entries)} record(s))."


def active_strategy_matches(entries: List[dict]) -> Tuple[bool, str]:
    """Hoort het laatste signaal bij de strategie die nu in de code staat?

    Dit mag het lezen van oude records nooit blokkeren. Het is alleen een
    waarschuwing voordat er een nieuw signaal bijkomt, zodat je niet per
    ongeluk een gewijzigde formule aan een lopende test vastplakt.
    """
    signals = [e for e in entries if e.get("record_type") == "signal"]
    if not signals:
        return True, "Nog geen signaal om mee te vergelijken."

    last = signals[-1]
    if last.get("strategy_hash") != STRATEGY_HASH:
        return False, (
            "De strategie in de code wijkt af van die van het laatste signaal. "
            "Een nieuw signaal zou dan bij een andere strategie horen. "
            f"Laatste signaal: {last.get('strategy_version')} ({last.get('strategy_hash', '')[:16]}...), "
            f"code nu: {STRATEGY_VERSION} ({STRATEGY_HASH[:16]}...)."
        )
    return True, "De code draait op dezelfde strategie als het laatste signaal."


def can_lock_new_signal(entries: List[dict], signal_date: pd.Timestamp) -> Tuple[bool, str]:
    """Mag er vandaag een nieuw officieel signaal bij?"""
    signals = [e for e in entries if e.get("record_type") == "signal"]
    if not signals:
        return True, "Eerste forward-signaal."

    last = max(pd.Timestamp(e["signal_market_date"]) for e in signals)
    delta = int((signal_date.normalize() - last.normalize()).days)

    if delta < MINIMUM_DAYS_BETWEEN_SIGNALS:
        return False, (
            f"Vorige signaal was {delta} dagen geleden. "
            f"Nieuwe selectie pas vanaf {MINIMUM_DAYS_BETWEEN_SIGNALS} dagen."
        )
    return True, f"{delta} dagen sinds het vorige signaal."


def next_allowed_signal_date(entries: List[dict]) -> pd.Timestamp | None:
    """De vroegste signaaldatum waarop een nieuwe selectie toegestaan is."""
    signals = [e for e in entries if e.get("record_type") == "signal"]
    if not signals:
        return None
    last = max(pd.Timestamp(e["signal_market_date"]) for e in signals)
    return last + pd.Timedelta(days=MINIMUM_DAYS_BETWEEN_SIGNALS)


def build_entry(entry_payload: dict, previous_hash: str) -> dict:
    """Maakt een compleet record met hash, zonder iets weg te schrijven.

    Apart gehouden van het schrijven zodat exact hetzelfde record berekend kan
    worden voor het logboekbestand en voor de database, zonder dat die twee
    uit elkaar kunnen lopen.
    """
    payload = dict(entry_payload)
    payload["previous_hash"] = previous_hash
    payload["strategy_hash"] = STRATEGY_HASH
    payload["strategy_version"] = STRATEGY_VERSION

    final = dict(payload)
    final["entry_hash"] = sha256_text(canonical_json(payload))
    return final


def append_signal_entry(ledger_file: Path, entry_payload: dict) -> dict:
    """Voegt een nieuw signaal toe. Weigert als het bestaande logboek niet klopt."""
    ledger_file.parent.mkdir(parents=True, exist_ok=True)
    entries = read_ledger(ledger_file)

    ok, message = verify_ledger(entries)
    if not ok:
        raise ValueError(
            "Bestaand forward-logboek faalt de integriteitscontrole. "
            "Er wordt niets toegevoegd. " + message
        )

    ok, message = active_strategy_matches(entries)
    if not ok:
        raise ValueError("Er wordt niets toegevoegd. " + message)

    previous_hash = entries[-1]["entry_hash"] if entries else "GENESIS"
    final = build_entry(entry_payload, previous_hash)

    with ledger_file.open("a", encoding="utf-8", newline="\n") as f:
        f.write(canonical_json(final) + "\n")

    return final


def ledger_lines(ledger_file: Path) -> List[str]:
    """De ruwe regels van het logboek, zoals ze op schijf staan.

    Nodig om de database later byte-voor-byte met het origineel te kunnen
    vergelijken in plaats van alleen veld voor veld.
    """
    if not ledger_file.exists():
        return []
    return [l for l in ledger_file.read_text(encoding="utf-8").splitlines() if l.strip()]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
