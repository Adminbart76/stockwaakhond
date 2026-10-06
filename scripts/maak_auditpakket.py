"""Bouwt het ZIP-bestand dat een externe controleur krijgt, en kijkt het na.

Waarom dit een script is en geen handeling
==========================================
Een auditpakket met de hand samenstellen gaat een keer goed en de tweede keer
mis: een bestand vergeten, of erger, een sleutelbestand meegestuurd. Daarom
komt de inhoud hier uit Git. Alles wat Git kent zit erin, en wat Git niet kent
(SLEUTELS_INVULLEN.txt, de secrets van Streamlit, de .venv) kan er per
definitie niet in belanden.

Daarna wordt het pakket uitgepakt in een tijdelijke map en worden de tests
erin gedraaid. Een pakket dat zelf niet groen is, hoort de deur niet uit.

Gebruik:
    python scripts/maak_auditpakket.py
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
DOEL = PROJECT / "stockwaakhond-voor-audit.zip"

# Deze horen er niet in: ze zeggen niets over de code en maken het pakket zwaar.
OVERSLAAN = {".gitignore"}


def kop(tekst: str) -> None:
    print("\n" + tekst)
    print("-" * len(tekst))


def git(*args: str) -> str:
    r = subprocess.run(["git", *args], cwd=PROJECT, capture_output=True, text=True)
    if r.returncode != 0:
        print("GESTOPT: git " + " ".join(args) + " mislukte:\n" + r.stderr)
        sys.exit(1)
    return r.stdout


kop("1. Wat zit er in het pakket?")

commit = git("rev-parse", "HEAD").strip()
vuil = git("status", "--porcelain").strip()
bestanden = [b for b in git("ls-files").splitlines() if b and b not in OVERSLAAN]

print(f"   commit        : {commit}")
print(f"   bestanden     : {len(bestanden)}")
if vuil:
    print("   LET OP: er staan nog niet-vastgelegde wijzigingen in de map.")
    print("   Het pakket bevat de bestanden zoals ze nu op schijf staan, niet")
    print("   zoals ze in de commit hierboven staan. Leg eerst vast:")
    for regel in vuil.splitlines()[:10]:
        print("      " + regel)


kop("2. Staat de bevroren forward-test er onaangeroerd in?")

ledger = json.loads(
    (PROJECT / "forward_log" / "ledger.jsonl").read_text(encoding="utf-8").splitlines()[0])
uitvoering = json.loads(
    (PROJECT / "forward_log" / "executions.jsonl").read_text(encoding="utf-8").splitlines()[0])

VERWACHT = {
    "entry_hash": "0426e47ccd6e0b4f7fcecd772ce21dc5778db862e359f5eb4d239f5ce8bd5d15",
    "strategy_hash": "a399aecc207510c77450cd015f4f23e2b3639fc642eb9bcc29e95cbe2b84cc18",
    "exec_hash": "3468930ea4971945c8e8dad57b2cc797f9c825508368eff6bef5038090d3dae7",
}
gevonden = {
    "entry_hash": ledger["entry_hash"],
    "strategy_hash": ledger["strategy_hash"],
    "exec_hash": uitvoering["exec_hash"],
}
for naam, waarde in VERWACHT.items():
    goed = gevonden[naam] == waarde
    print(f"   {'OK  ' if goed else 'FOUT'}  {naam}: {gevonden[naam][:24]}...")
    if not goed:
        print("   Het pakket wordt niet gemaakt. Zoek dit eerst uit.")
        sys.exit(1)


def sha(pad: Path) -> str:
    return hashlib.sha256(pad.read_bytes()).hexdigest()


paren = [
    ("app.py", "bewijs/app.py.bevroren-2026-10-06"),
    ("forward_log/ledger.jsonl", "bewijs/ledger.jsonl"),
]
for a, b in paren:
    goed = sha(PROJECT / a) == sha(PROJECT / b)
    print(f"   {'OK  ' if goed else 'FOUT'}  {a} is identiek aan {b}")
    if not goed:
        sys.exit(1)


kop("3. Pakket maken")

if DOEL.exists():
    DOEL.unlink()

with zipfile.ZipFile(DOEL, "w", zipfile.ZIP_DEFLATED) as z:
    for naam in bestanden:
        pad = PROJECT / naam
        if pad.exists():
            z.write(pad, naam)

print(f"   {DOEL.name}  ({DOEL.stat().st_size // 1024} kB, {len(bestanden)} bestanden)")

# Dubbelcheck: er mag niets geheims in zitten, ook niet per ongeluk.
with zipfile.ZipFile(DOEL) as z:
    namen = z.namelist()
verdacht = [n for n in namen
            if "SLEUTEL" in n.upper() or "SECRET" in n.upper() or n.endswith(".env")]
if verdacht:
    print("   GESTOPT: er zit iets in dat er niet in hoort: " + ", ".join(verdacht))
    DOEL.unlink()
    sys.exit(1)
print("   nagekeken : geen sleutelbestanden in het pakket")


kop("4. Werkt het pakket op zichzelf?")

with tempfile.TemporaryDirectory() as tijdelijk:
    map_ = Path(tijdelijk)
    with zipfile.ZipFile(DOEL) as z:
        z.extractall(map_)

    r = subprocess.run([sys.executable, "-m", "pytest"],
                       cwd=map_, capture_output=True, text=True)
    regels = [l.strip() for l in r.stdout.splitlines() if "passed" in l or "failed" in l]
    uitslag = regels[-1] if regels else "geen uitslag gevonden"
    print("   " + uitslag)
    if r.returncode != 0:
        print("   GESTOPT: de tests in het uitgepakte pakket slagen niet.")
        print(r.stdout[-2000:])
        sys.exit(1)

shutil.rmtree(PROJECT / ".pytest_cache", ignore_errors=True)


kop("5. Briefje erbij over wat dit pakket is")

briefje = (
    "AUDITPAKKET STOCKWAAKHOND V7.1\n"
    "==============================\n\n"
    f"gemaakt op  : {datetime.now(timezone.utc).isoformat(timespec='seconds')}\n"
    f"commit      : {commit}\n"
    f"bestanden   : {len(bestanden)}\n"
    f"tests       : {uitslag} (gedraaid in dit uitgepakte pakket)\n\n"
    "Dit is alles wat in de openbare GitHub-map staat: geen sleutels, geen\n"
    "wachtwoorden, geen database. De inhoud komt rechtstreeks uit Git.\n\n"
    "Begin bij audit/VRAAG_2026-10-07.md. Daarin staat per punt wat er\n"
    "gebouwd is, wat je kunt narekenen en waar je zou moeten aanvallen.\n"
)
with zipfile.ZipFile(DOEL, "a", zipfile.ZIP_DEFLATED) as z:
    z.writestr("audit/PAKKET.txt", briefje)
print("   audit/PAKKET.txt toegevoegd")

print("\n" + "=" * 70)
print("KLAAR - het pakket is te versturen.")
print(f"  {DOEL.name}  (in de projectmap)")
print(f"  commit {commit[:12]}")
print("Begin bij audit/VRAAG_2026-10-07.md: daarin staat wat er nagekeken moet worden.")
print("=" * 70)
