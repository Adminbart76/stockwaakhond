"""Legt een uitgekeerd dividend vast: bruto bedrag, ex-datum en betaaldatum.

Waarom dit een eigen handeling is
=================================
Yahoo kent van een dividend alleen de EX-DATUM en het bedrag. De BETAALDATUM
staat er niet in, en juist die bepaalt wanneer het geld beschikbaar is en dus bij
welke wissel het meegaat. Die datum komt van de bron van het bedrijf zelf (de
investor-relations-pagina, Nasdaq, de broker) en wordt hier met de hand ingevuld,
met vermelding van waar hij gevonden is.

Zelf een betaaldatum verzinnen - bijvoorbeeld "de ex-datum" of "twee weken later"
- zou een wissel met een verkeerd bedrag voor altijd vastleggen. Daarom vraagt dit
script erom in plaats van te raden.

De conventie is bruto en staat vast
===================================
De officiële forward-test rekent het volledige uitgekeerde bedrag, voor
belasting, aan beide kanten. Een nettobedrag mag erbij, maar het wordt niet
gebruikt om te rekenen; het is informatie. Zie sw/dividend.py.

Hetzelfde patroon als de andere handelingen
===========================================
Eerst lokaal in forward_log/dividends.jsonl (de bron van waarheid, en meteen
openbaar in Git), dan in de database. De tabel `dividends` is onaantastbaar: er
kan alleen bij komen, nooit iets gewijzigd of weg. Een verkeerd ingevulde rij is
dus niet te herstellen - vandaar de bevestiging.

Gebruik:
    python scripts/leg_dividend_vast.py --toon
    python scripts/leg_dividend_vast.py --ticker=MPC --ex=2026-11-16 \\
        --bedrag=0.9100 --betaald=2026-12-04 \\
        --bron="nasdaq.com dividend history, opgezocht op 2026-11-17"
    ... --netto=0.6400 --fiscaal="15% US bronheffing, 30% RV"   (optioneel)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

from sw import dividend as div                           # noqa: E402
from sw import herbalans as hb                           # noqa: E402
from sw import prices as pr                              # noqa: E402
from sw.supabase_io import Supabase, lees_instellingen   # noqa: E402

UITVOERINGEN = PROJECT / "forward_log" / "executions.jsonl"
DIVIDENDEN = PROJECT / "forward_log" / "dividends.jsonl"


def stop(bericht: str) -> None:
    print("\n" + "=" * 74)
    print("GESTOPT: " + bericht)
    print("Er is niets vastgelegd.")
    print("=" * 74)
    sys.exit(1)


def klaar(bericht: str) -> None:
    print("\n" + "=" * 74)
    print("NIETS TE DOEN: " + bericht)
    print("=" * 74)
    sys.exit(0)


def kop(tekst: str) -> None:
    print("\n" + tekst)
    print("-" * len(tekst))


def argument(naam: str):
    for arg in sys.argv[1:]:
        if arg.startswith(f"--{naam}="):
            return arg.split("=", 1)[1].strip()
    return None


ALLEEN_TONEN = "--toon" in sys.argv


# ------------------------------------------------- de keten en wat erin zat
if not UITVOERINGEN.exists():
    stop("er staat nog geen uitvoering; dan is er ook nog geen portefeuille.")

uitvoeringen = [
    json.loads(l) for l in
    UITVOERINGEN.read_text(encoding="utf-8").splitlines() if l.strip()
]
ok, bericht = hb.verify_keten(uitvoeringen)
if not ok:
    stop("de keten van uitvoeringen klopt niet: " + bericht)

keten = hb.sorteer_keten(uitvoeringen)
begin = keten[0]["execution_date"]
van_belang = hb.tickers_in_keten(uitvoeringen)

cfg = lees_instellingen()
lezer = Supabase.lezer(cfg)
try:
    in_db = lezer.select("dividends", "select=*&order=ex_date.asc")
except Exception as fout:
    stop("de dividendtabel kon niet gelezen worden: " + str(fout))

bekend = {(r["ticker"], str(r["ex_date"])) for r in in_db}


# --------------------------------------------------------------- alleen tonen
if ALLEEN_TONEN or not argument("ticker"):
    kop("Wat staat er al vast?")
    if not in_db:
        print("   nog geen enkel dividend")
    for r in in_db:
        betaald = r.get("pay_date") or "GEEN BETAALDATUM"
        print(f"   {r['ticker']:<6} ex {r['ex_date']}  betaald {betaald}  "
              f"bruto {float(r['gross_per_share_usd']):.4f} USD")

    kop("Wat kent Yahoo, en missen wij?")
    print("   (Yahoo kent de ex-datum en het bedrag, niet de betaaldatum)")
    try:
        van_yahoo = pr.haal_dividenden(van_belang, start=begin)
    except Exception as fout:
        print("   Yahoo kon niet gelezen worden: " + str(fout))
        van_yahoo = {}

    ontbreekt = []
    for ticker, rijen in sorted(van_yahoo.items()):
        for ex, bedrag in sorted(rijen.items()):
            staat_erin = (ticker, ex) in bekend
            print(f"   {'staat erin' if staat_erin else 'ONTBREEKT '}  "
                  f"{ticker:<6} ex {ex}  bruto {bedrag:.4f} USD")
            if not staat_erin:
                ontbreekt.append((ticker, ex, bedrag))

    zonder_betaaldag = [r for r in in_db if not r.get("pay_date")]
    if zonder_betaaldag:
        kop("Deze rijen hebben geen betaaldatum")
        for r in zonder_betaaldag:
            print(f"   {r['ticker']:<6} ex {r['ex_date']}")
        print("\n   Zonder betaaldatum kan er niet met dit dividend gerekend")
        print("   worden. De tabel is onaantastbaar, dus een bestaande rij is")
        print("   niet bij te werken: dit hoort een beheershandeling te zijn.")

    if ontbreekt:
        kop("Zo leg je de eerste ontbrekende vast")
        ticker, ex, bedrag = ontbreekt[0]
        print(f"   python scripts/leg_dividend_vast.py --ticker={ticker} \\")
        print(f"       --ex={ex} --bedrag={bedrag:.4f} \\")
        print(f"       --betaald=JJJJ-MM-DD \\")
        print(f"       --bron=\"waar je de betaaldatum gevonden hebt\"")
        print()
        print("   De betaaldatum staat op de investor-relations-pagina van het")
        print("   bedrijf, of op nasdaq.com bij de dividendgeschiedenis.")
    else:
        print("\n   Er ontbreekt niets.")
    sys.exit(0)


# ------------------------------------------------------- de opgegeven gegevens
kop("1. Wat er vastgelegd gaat worden")

ticker = (argument("ticker") or "").upper()
ex = argument("ex")
betaald = argument("betaald")
bedrag = argument("bedrag")
netto = argument("netto")
bron = argument("bron")
fiscaal = argument("fiscaal")

if not ex or not betaald or not bedrag:
    stop(
        "geef --ticker, --ex, --bedrag en --betaald mee.\n"
        "Zonder betaaldatum is niet bekend wanneer het geld beschikbaar is, en\n"
        "dus bij welke wissel het meegaat. Die datum wordt niet verzonnen."
    )
if not bron:
    stop(
        "geef met --bron mee waar de betaaldatum gevonden is.\n"
        "Een datum zonder herkomst is in een forward-test niets waard: een\n"
        "latere lezer moet kunnen narekenen waar die vandaan komt."
    )

rij = {
    "ticker": ticker,
    "ex_date": str(pd.Timestamp(ex).date()),
    "pay_date": str(pd.Timestamp(betaald).date()),
    "gross_per_share_usd": float(bedrag),
    "net_per_share_usd": float(netto) if netto else None,
    "tax_note": fiscaal,
    "source": bron,
}

# Door dezelfde lezer als de rekenkern, zodat een rij die hier doorkomt ook
# werkelijk bruikbaar is.
gelezen = div.lees_rij(rij)

if ticker not in van_belang:
    stop(
        f"{ticker} heeft nooit in de portefeuille gezeten. Dan levert dit\n"
        "dividend ons niets op en hoort het hier niet vastgelegd te worden."
    )
if (rij["ticker"], rij["ex_date"]) in bekend:
    klaar(
        f"het dividend van {ticker} met ex-datum {rij['ex_date']} staat er al.\n"
        "De tabel is onaantastbaar; eenzelfde rij komt er maar een keer in."
    )

bezit = hb.uitvoering_voor(uitvoeringen, gelezen["ex_date"])
stuks = 0.0
if bezit is not None:
    if ticker == bezit["benchmark"]["ticker"]:
        stuks = float(bezit["benchmark"]["shares"])
    else:
        stuks = {p["ticker"]: float(p["shares"])
                 for p in bezit["positions"]}.get(ticker, 0.0)

print(f"   aandeel        : {ticker}")
print(f"   ex-datum       : {gelezen['ex_date'].date()}  (bepaalt het recht)")
print(f"   betaaldatum    : {gelezen['pay_date'].date()}  (dan is het geld er)")
print(f"   bruto          : {gelezen['per_share_usd']:.4f} USD per aandeel")
if netto:
    print(f"   netto          : {float(netto):.4f} USD   (informatie, geen rekenbasis)")
print(f"   bron           : {bron}")
print(f"   conventie      : {div.CONVENTIE_TEKST}")
print()
if stuks > 0:
    print(f"   wij hadden op de ex-datum {stuks:.6f} aandelen {ticker}")
    print(f"   dat is {stuks * gelezen['per_share_usd']:.2f} USD, beschikbaar op "
          f"{gelezen['pay_date'].date()}")
else:
    print(f"   LET OP: op {gelezen['ex_date'].date()} hadden wij geen {ticker}.")
    print("   Deze uitkering levert ons dus niets op. Vastleggen mag, maar ze")
    print("   verandert niets aan de portefeuille.")

# Narekenen tegen Yahoo: het bedrag hoort te kloppen met wat de markt zegt.
try:
    van_yahoo = pr.haal_dividenden([ticker], start=begin).get(ticker, {})
except Exception as fout:
    van_yahoo = {}
    print("\n   (Yahoo kon niet gelezen worden om het bedrag na te kijken: "
          + str(fout) + ")")
if van_yahoo:
    yahoo_bedrag = van_yahoo.get(rij["ex_date"])
    if yahoo_bedrag is None:
        print(f"\n   LET OP: Yahoo kent geen uitkering van {ticker} op "
              f"{rij['ex_date']}.")
        print("   Kijk de ex-datum na voor je dit vastlegt.")
    elif abs(yahoo_bedrag - gelezen["per_share_usd"]) > 0.0001:
        stop(
            f"Yahoo meldt {yahoo_bedrag:.4f} USD per aandeel en hier staat "
            f"{gelezen['per_share_usd']:.4f}.\n"
            "Een van de twee is verkeerd. Zoek dat eerst uit."
        )
    else:
        print(f"\n   nagekeken      : Yahoo meldt hetzelfde bedrag "
              f"({yahoo_bedrag:.4f} USD)")


# ------------------------------------------------------------ 2. bevestigen
kop("2. Bevestigen")
print("   Deze rij kan daarna niet meer gewijzigd of verwijderd worden.")
antwoord = input("   Typ JA om vast te leggen: ").strip()
if antwoord != "JA":
    stop("niet bevestigd.")


# ------------------------------------------------------------ 3. vastleggen
kop("3. Vastleggen")

DIVIDENDEN.parent.mkdir(parents=True, exist_ok=True)
with DIVIDENDEN.open("a", encoding="utf-8", newline="\n") as f:
    f.write(json.dumps(rij, sort_keys=True, ensure_ascii=False) + "\n")
print(f"   lokaal   : forward_log/{DIVIDENDEN.name}")

db = Supabase.schrijver(cfg)
try:
    db.insert("dividends", [rij])
except Exception as fout:
    print("\n" + "=" * 74)
    print("HALF KLAAR: de database weigerde de rij.")
    print("Technische melding: " + str(fout))
    print()
    print(f"De rij staat wel in forward_log/{DIVIDENDEN.name}, en dat bestand is")
    print("de bron van waarheid. Zoek eerst uit waarom de database weigert; vul")
    print("daarna niets met de hand in.")
    print("=" * 74)
    sys.exit(1)
print("   database : dividends")

db.insert("audit_log", [{
    "actor": "scripts/leg_dividend_vast.py",
    "action": "dividend vastgelegd",
    "detail": rij,
}])

terug = lezer.select(
    "dividends",
    f"select=*&ticker=eq.{ticker}&ex_date=eq.{rij['ex_date']}")
if len(terug) != 1:
    stop("de rij staat niet terug te vinden in de database.")
if str(terug[0].get("pay_date")) != rij["pay_date"]:
    stop("de betaaldatum in de database wijkt af van wat er is opgegeven.")

print("   terug gelezen: betaaldatum klopt")
print("\n" + "=" * 74)
print("VASTGELEGD")
print(f"{ticker}: {gelezen['per_share_usd']:.4f} USD per aandeel, recht op "
      f"{gelezen['ex_date'].date()},")
print(f"geld beschikbaar op {gelezen['pay_date'].date()}. Bruto, aan beide kanten.")
print("=" * 74)
