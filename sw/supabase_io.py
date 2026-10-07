"""Praten met Supabase.

Twee sleutels, twee rollen:
  leessleutel   - mag alleen lezen, mag in de webapp staan
  schrijfsleutel - mag toevoegen, hoort alleen lokaal en in GitHub Actions

Wissen en wijzigen kan met geen van beide: dat is in de database zelf
geblokkeerd. Deze module biedt er dan ook geen functie voor.

Er is nog een derde manier naar binnen, met opzet heel smal: een
databasefunctie die alleen de dagkoersen van vandaag mag toevoegen, van de
aandelen die nu in de portefeuille zitten, allemaal samen of geen enkele. Ze
vraagt om een eigen schrijfteken. Daarmee kan de dagelijkse taak op GitHub haar
werk doen zonder dat de geheime sleutel daar ooit moet staan. Zie rpc() en
sql/03_smalle_deur.sql.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

STANDAARD_SLEUTELBESTAND = Path(
    "I:/Mijn Drive/02 \u2013 Eigen projecten/stockwaakhond/SLEUTELS_INVULLEN.txt"
)


def lees_instellingen(pad: Optional[Path] = None) -> Dict[str, str]:
    """Haalt de instellingen op uit omgevingsvariabelen of uit het sleutelbestand.

    Volgorde: eerst de omgeving (zo werkt het in GitHub Actions en op
    Streamlit), dan pas het lokale bestand.
    """
    cfg = {}
    for sleutel in ("SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_KEY",
                    "SNAPSHOT_WRITE_TOKEN", "ADMIN_WACHTWOORD"):
        waarde = os.environ.get(sleutel)
        if waarde:
            cfg[sleutel] = waarde

    bestand = pad or STANDAARD_SLEUTELBESTAND
    if bestand.exists():
        tekst = bestand.read_text(encoding="utf-8")
        for naam, waarde in re.findall(r'^\s*([A-Z_]+)\s*=\s*"(.*)"\s*$', tekst, re.MULTILINE):
            if waarde and not waarde.startswith("<"):
                cfg.setdefault(naam, waarde)

    return cfg


class Supabase:
    """Een dunne laag over de Supabase REST-koppeling."""

    def __init__(self, url: str, key: str, mag_schrijven: bool = False):
        self.url = url.rstrip("/")
        self.key = key
        self.mag_schrijven = mag_schrijven

    @classmethod
    def lezer(cls, cfg: Optional[Dict[str, str]] = None) -> "Supabase":
        cfg = cfg or lees_instellingen()
        return cls(cfg["SUPABASE_URL"], cfg["SUPABASE_ANON_KEY"], mag_schrijven=False)

    @classmethod
    def schrijver(cls, cfg: Optional[Dict[str, str]] = None) -> "Supabase":
        cfg = cfg or lees_instellingen()
        return cls(cfg["SUPABASE_URL"], cfg["SUPABASE_SERVICE_KEY"], mag_schrijven=True)

    def _headers(self, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        h = {
            "apikey": self.key,
            "Authorization": "Bearer " + self.key,
            "Content-Type": "application/json",
        }
        if extra:
            h.update(extra)
        return h

    # ---------------------------------------------------------------- lezen
    def select(self, tabel: str, query: str = "select=*", timeout: int = 30) -> List[dict]:
        r = requests.get(
            f"{self.url}/rest/v1/{tabel}?{query}",
            headers=self._headers(),
            timeout=timeout,
        )
        if r.status_code != 200:
            raise RuntimeError(f"Lezen van {tabel} mislukte: HTTP {r.status_code} {r.text[:300]}")
        return r.json()

    def telling(self, tabel: str) -> int:
        r = requests.get(
            f"{self.url}/rest/v1/{tabel}?select=*",
            headers=self._headers({"Prefer": "count=exact", "Range": "0-0"}),
            timeout=30,
        )
        bereik = r.headers.get("content-range", "")
        if "/" in bereik:
            staart = bereik.split("/")[-1]
            return int(staart) if staart.isdigit() else 0
        return 0

    # -------------------------------------------------------------- toevoegen
    def insert(self, tabel: str, rijen: Any, negeer_dubbel: bool = False,
               timeout: int = 60) -> List[dict]:
        """Voegt rijen toe. Wijzigen bestaat hier bewust niet."""
        if not self.mag_schrijven:
            raise PermissionError(
                "Deze verbinding is alleen om te lezen. Gebruik Supabase.schrijver()."
            )

        voorkeur = ["return=representation"]
        if negeer_dubbel:
            voorkeur.append("resolution=ignore-duplicates")

        r = requests.post(
            f"{self.url}/rest/v1/{tabel}",
            headers=self._headers({"Prefer": ",".join(voorkeur)}),
            data=json.dumps(rijen),
            timeout=timeout,
        )
        if r.status_code not in (200, 201):
            raise RuntimeError(
                f"Toevoegen aan {tabel} mislukte: HTTP {r.status_code} {r.text[:600]}"
            )
        try:
            return r.json()
        except ValueError:
            return []

    def upsert(self, tabel: str, rijen: Any, timeout: int = 60) -> List[dict]:
        """Alleen voor afgeleide tabellen zoals live_quotes, nooit voor bewijsmateriaal."""
        if not self.mag_schrijven:
            raise PermissionError("Deze verbinding is alleen om te lezen.")
        if tabel not in ("live_quotes", "signal_proposals", "audit_log"):
            raise PermissionError(
                f"Overschrijven van '{tabel}' is niet toegestaan. "
                "Alleen afgeleide tabellen mogen bijgewerkt worden."
            )
        r = requests.post(
            f"{self.url}/rest/v1/{tabel}",
            headers=self._headers({"Prefer": "resolution=merge-duplicates,return=representation"}),
            data=json.dumps(rijen),
            timeout=timeout,
        )
        if r.status_code not in (200, 201):
            raise RuntimeError(
                f"Bijwerken van {tabel} mislukte: HTTP {r.status_code} {r.text[:600]}"
            )
        try:
            return r.json()
        except ValueError:
            return []

    # ------------------------------------------------------------- functies
    def rpc(self, functie: str, argumenten: Dict[str, Any], timeout: int = 60) -> Any:
        """Roept een databasefunctie aan.

        Hiermee kan de dagelijkse taak koersen wegschrijven zonder de geheime
        sleutel. De functie in de database bepaalt zelf wat er mag: alleen
        koersen en wisselkoersen toevoegen, nooit een signaal of een uitvoering
        aanraken. De leessleutel mag dit dus aanroepen - de grens zit in de
        database, niet in de sleutel.
        """
        r = requests.post(
            f"{self.url}/rest/v1/rpc/{functie}",
            headers=self._headers(),
            data=json.dumps(argumenten),
            timeout=timeout,
        )
        if r.status_code not in (200, 201, 204):
            raise RuntimeError(
                f"Aanroepen van {functie} mislukte: HTTP {r.status_code} {r.text[:600]}"
            )
        if not r.content:
            return None
        try:
            return r.json()
        except ValueError:
            return None

    def tabellen_bestaan(self, namen: List[str]) -> Dict[str, bool]:
        resultaat = {}
        for naam in namen:
            r = requests.get(
                f"{self.url}/rest/v1/{naam}?select=*&limit=0",
                headers=self._headers(),
                timeout=20,
            )
            resultaat[naam] = r.status_code == 200
        return resultaat
