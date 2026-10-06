"""Het online dashboard van StockWaakhond.

Dit scherm leest alleen. Het kan de forward-test niet wijzigen: de leessleutel
die hier gebruikt wordt heeft geen schrijfrechten, en de database weigert
wijzigingen sowieso.

Twee rollen:
  kijker    - ziet alles, kan niets vastleggen
  beheerder - kan na het beheerderswachtwoord beheerinformatie zien; de
              maandelijkse scan draait met opzet niet op dit scherm
"""

from __future__ import annotations

import hmac
import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import altair as alt
import pandas as pd
import streamlit as st

from sw import ledger as led
from sw import portfolio as pf
from sw import prices as pr
from sw.strategy import STRATEGY_HASH, sha256_text
from sw.supabase_io import Supabase, lees_instellingen

# De twee series van elke grafiek. Nagerekend op kleurenblindheid en op
# contrast met de achtergrond, in lichte en donkere weergave.
KLEUR_SW = "#2a78d6"    # blauw
KLEUR_SPY = "#eb6834"   # oranje
BEURS = ZoneInfo("America/New_York")
HIER = ZoneInfo("Europe/Brussels")

st.set_page_config(page_title="StockWaakhond", page_icon="dog", layout="wide")


# ---------------------------------------------------------------- instellingen
def instellingen() -> dict:
    cfg = {}
    try:
        for sleutel in ("SUPABASE_URL", "SUPABASE_ANON_KEY", "ADMIN_WACHTWOORD"):
            if sleutel in st.secrets:
                cfg[sleutel] = st.secrets[sleutel]
    except Exception:
        pass
    for naam, waarde in lees_instellingen().items():
        cfg.setdefault(naam, waarde)
    return cfg


CFG = instellingen()


# -------------------------------------------------------------- schrijfwijze
DAGEN = ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag"]
MAANDEN = ["januari", "februari", "maart", "april", "mei", "juni",
           "juli", "augustus", "september", "oktober", "november", "december"]


def _komma(tekst: str) -> str:
    return tekst.replace(",", "X").replace(".", ",").replace("X", ".")


def eur(bedrag: float) -> str:
    return "€ " + _komma(f"{bedrag:,.2f}")


def dollar(bedrag: float) -> str:
    return "$ " + _komma(f"{bedrag:,.2f}")


def getal(waarde: float, decimalen: int = 2) -> str:
    return _komma(f"{waarde:,.{decimalen}f}")


def pct(waarde: float, met_teken: bool = True) -> str:
    teken = "+" if (met_teken and waarde > 0) else ""
    return f"{teken}{waarde:.2f}".replace(".", ",") + " %"


def datum_nl(datum, met_dag: bool = True) -> str:
    """Een datum zoals je hem in België opschrijft: maandag 5 oktober 2026."""
    d = pd.Timestamp(datum)
    stuk = f"{d.day} {MAANDEN[d.month - 1]} {d.year}"
    return f"{DAGEN[d.weekday()]} {stuk}" if met_dag else stuk


# ------------------------------------------------------------------- gegevens
@st.cache_data(ttl=300, show_spinner=False)
def haal_vaste_gegevens() -> dict:
    db = Supabase.lezer(CFG)
    return {
        "signalen": db.select("signals", "select=*&order=seq.asc"),
        "uitvoeringen": db.select("executions", "select=*"),
    }


@st.cache_data(ttl=3600, show_spinner=False)
def haal_dagkoersen(tickers: tuple, vanaf: str):
    echt, _ = pr.haal_koersen(list(tickers), start=vanaf)
    fx = pr.haal_wisselkoers(start=vanaf)
    return echt, fx


@st.cache_data(ttl=120, show_spinner=False)
def haal_actuele_koersen(tickers: tuple):
    koersen, tijdstip = pr.laatste_koersen(list(tickers))
    fx = pr.haal_wisselkoers(start=str((pd.Timestamp.today() - pd.Timedelta(days=10)).date()))
    return koersen, tijdstip, (float(fx.iloc[-1]) if len(fx) else None)


def beurs_status():
    nu = datetime.now(timezone.utc).astimezone(BEURS)
    if nu.weekday() >= 5:
        return False, "De beurs in New York is dicht: het is daar weekend."
    if (nu.hour, nu.minute) >= (9, 30) and nu.hour < 16:
        return True, f"De beurs in New York is open. Daar is het nu {nu.strftime('%H.%M')} uur."
    return False, f"De beurs in New York is gesloten. Daar is het nu {nu.strftime('%H.%M')} uur."


# ----------------------------------------------------------------------- kop
st.title("StockWaakhond")
st.caption(
    "Een beleggingsstrategie die vooraf is vastgelegd. We meten wat ze in de "
    "praktijk doet, en stellen haar achteraf nooit bij."
)

try:
    gegevens = haal_vaste_gegevens()
except Exception as fout:
    st.error(
        "De gegevens konden niet geladen worden. Probeer het over een paar "
        "minuten opnieuw.\n\nTechnische melding: " + str(fout)
    )
    st.stop()

signalen = gegevens["signalen"]
if not signalen:
    st.warning("Er is nog geen selectie vastgelegd.")
    st.stop()

signaal = signalen[-1]
tickers = [s["ticker"] for s in signaal["selected"]]
uitvoering = next(
    (u for u in gegevens["uitvoeringen"] if u["entry_hash"] == signaal["entry_hash"]), None)
open_nu, beurs_uitleg = beurs_status()


# ======================================================== DEEL 1: portefeuille
if uitvoering is None:
    st.header("De portefeuille is nog niet ingestapt")

    nu_hier = datetime.now(timezone.utc).astimezone(HIER)
    st.info(
        f"De vijf aandelen zijn gekozen op **{datum_nl(signaal['signal_market_date'])}**. "
        "De virtuele €1.000 stapt in tegen de slotkoers van de eerste beursdag "
        "daarna.\n\n"
        "Die koers was op het moment van kiezen nog niet bekend, en dat is met "
        "opzet. Zou de strategie instappen tegen een koers die ze al kende, dan "
        "reken je jezelf rijk met informatie die je toen niet had."
    )

    if open_nu:
        st.warning(
            f"**Kom vanavond na 22.20 uur terug.** De beurs in New York sluit om "
            f"22.00 uur bij ons. Pas dan ligt de slotkoers vast en kan de "
            f"portefeuille instappen. Nu is het {nu_hier.strftime('%H.%M')} uur."
        )
    else:
        st.warning(
            beurs_uitleg + " Zodra de instap is vastgelegd, verschijnen hier de "
            "waarde van de portefeuille, de vergelijking met de beursindex SPY "
            "en het verloop per dag."
        )

else:
    instap = {
        "start_capital_eur": float(uitvoering["start_capital_eur"]),
        "invested_eur": float(uitvoering["invested_eur"]),
        "cost_eur": float(uitvoering["cost_eur"]),
        "execution_date": uitvoering["execution_date"],
        "positions": uitvoering["positions"],
        "benchmark": uitvoering["benchmark"],
    }

    try:
        koersen_nu, tijdstip, fx_nu = haal_actuele_koersen(tuple(tickers + ["SPY"]))
    except Exception:
        koersen_nu, tijdstip, fx_nu = {}, None, None

    verse_koersen = bool(koersen_nu)
    if not fx_nu:
        fx_nu = float(uitvoering["fx_rate"])
    if not koersen_nu:
        koersen_nu = {p["ticker"]: p["buy_price_usd"] for p in instap["positions"]}
        koersen_nu["SPY"] = instap["benchmark"]["buy_price_usd"]

    waardering = pf.waardeer(
        instap, koersen_nu, fx_nu,
        datum=str(pd.Timestamp.today().date()),
        spy_koers_usd=koersen_nu.get("SPY"),
    )

    st.header("Hoe staat de virtuele portefeuille ervoor?")

    k1, k2, k3 = st.columns(3)
    k1.metric("Ingelegd", eur(waardering.inleg_eur),
              help="Het virtuele startbedrag. Er is nooit echt geld belegd.")
    k2.metric("Nu waard", eur(waardering.totaal_eur),
              delta=f"{eur(waardering.resultaat_eur)}  ({pct(waardering.resultaat_pct)})")
    k3.metric("Dezelfde €1.000 in SPY", eur(waardering.spy_waarde_eur),
              delta=f"{eur(waardering.spy_resultaat_eur)}  ({pct(waardering.spy_resultaat_pct)})",
              help="SPY is een fonds dat de 500 grootste Amerikaanse "
                   "beursbedrijven volgt. Het is de maatstaf: haalt de "
                   "strategie meer dan dit, dan was het kiezen de moeite waard.")

    voor = waardering.voorsprong_pct
    st.markdown(
        f"### {'Voorsprong' if voor >= 0 else 'Achterstand'} op SPY: {pct(voor)}\n"
        f"StockWaakhond staat op {pct(waardering.resultaat_pct)}, SPY op "
        f"{pct(waardering.spy_resultaat_pct)}. "
        + ("De strategie doet het dus beter dan de markt."
           if voor >= 0 else "De strategie doet het dus minder goed dan de markt.")
    )

    if verse_koersen and tijdstip:
        gemeten = pd.Timestamp(tijdstip)
        if gemeten.tzinfo is None:
            gemeten = gemeten.tz_localize("UTC")
        gemeten = gemeten.tz_convert(HIER)
        st.caption(
            f"Koersen van {datum_nl(gemeten, met_dag=False)} om "
            f"{gemeten.strftime('%H.%M')} uur. Dit zijn vertraagde koersen van "
            f"Yahoo Finance, geen koersen van dit moment. {beurs_uitleg}"
        )
    else:
        st.caption(
            "De koersen van nu konden niet opgehaald worden. Hierboven staan de "
            f"koersen van bij de instap. {beurs_uitleg}"
        )

    st.caption(
        f"Wisselkoers nu: 1 euro = {getal(fx_nu, 4)} dollar. Bij de instap was "
        f"dat {getal(float(uitvoering['fx_rate']), 4)} dollar."
    )

    # ------------------------------------------------------------ grafieken
    st.header("Verloop sinds de start")

    try:
        echt, fx_reeks = haal_dagkoersen(tuple(tickers + ["SPY"]), instap["execution_date"])
        verloop = pf.bouw_verloop(instap, echt, fx_reeks)
    except Exception as fout:
        verloop = pd.DataFrame()
        st.warning("Het verloop kon niet berekend worden: " + str(fout))

    if len(verloop) >= 2:
        lang = pd.concat([
            pd.DataFrame({"datum": verloop.index, "waarde": verloop["portefeuille_eur"],
                          "reeks": "StockWaakhond"}),
            pd.DataFrame({"datum": verloop.index, "waarde": verloop["spy_eur"],
                          "reeks": "SPY"}),
        ])
        schaal = alt.Scale(domain=["StockWaakhond", "SPY"], range=[KLEUR_SW, KLEUR_SPY])

        lijnen = alt.Chart(lang).mark_line(strokeWidth=2).encode(
            x=alt.X("datum:T", title=None, axis=alt.Axis(format="%d/%m", grid=False)),
            y=alt.Y("waarde:Q", title="waarde in euro", scale=alt.Scale(zero=False),
                    axis=alt.Axis(format=",.0f")),
            color=alt.Color("reeks:N", title=None, scale=schaal,
                            legend=alt.Legend(orient="top", direction="horizontal")),
            tooltip=[
                alt.Tooltip("datum:T", title="datum", format="%d/%m/%Y"),
                alt.Tooltip("reeks:N", title=""),
                alt.Tooltip("waarde:Q", title="waarde in euro", format=",.2f"),
            ],
        )

        # Het laatste punt van elke lijn krijgt zijn naam ernaast, zodat de twee
        # lijnen ook zonder kleur uit elkaar te houden zijn.
        laatste = lang.sort_values("datum").groupby("reeks").tail(1)
        namen = alt.Chart(laatste).mark_text(
            align="left", dx=8, fontSize=12, fontWeight="bold"
        ).encode(
            x="datum:T", y="waarde:Q", text="reeks:N",
            color=alt.Color("reeks:N", legend=None, scale=schaal),
        )

        st.altair_chart((lijnen + namen).properties(height=360), use_container_width=True)
        st.caption(
            "Allebei gestart met €1.000 op dezelfde dag, met dezelfde "
            "transactiekost en dezelfde wisselkoers. Zo meet je het verschil "
            "tussen de twee beleggingen, en niet tussen twee rekenwijzen."
        )

        with st.expander("Deze grafiek als tabel"):
            tabel = verloop.reset_index()[
                ["datum", "portefeuille_eur", "spy_eur", "resultaat_pct",
                 "spy_resultaat_pct", "fx_eurusd"]].copy()
            tabel["datum"] = tabel["datum"].dt.strftime("%d/%m/%Y")
            tabel.columns = ["Datum", "StockWaakhond (€)", "SPY (€)",
                             "StockWaakhond (%)", "SPY (%)", "Euro in dollar"]
            st.dataframe(tabel.round(2), hide_index=True, width="stretch")

        d1, d2 = st.columns(2)
        d1.metric("Diepste terugval StockWaakhond",
                  pct(pf.max_daling(verloop["portefeuille_eur"]), met_teken=False),
                  help="De diepste val vanaf een eerder hoogtepunt, tot nu toe.")
        d2.metric("Diepste terugval SPY",
                  pct(pf.max_daling(verloop["spy_eur"]), met_teken=False))

    elif len(verloop) == 1:
        st.info(
            "De portefeuille is net ingestapt. Vanaf de volgende beursdag "
            "verschijnt hier het verloop per dag."
        )

    # ------------------------------------------------------------- posities
    st.header("De vijf posities")

    st.dataframe(pd.DataFrame([{
        "Aandeel": p["ticker"],
        "Aantal": getal(p["aandelen"], 4),
        "Gekocht aan": dollar(p["aankoopkoers_usd"]),
        "Koers nu": dollar(p["koers_usd"]),
        "Koers in dollar": pct(p["koersrendement_pct"]),
        "Ingelegd": eur(p["inzet_eur"]),
        "Nu waard": eur(p["waarde_eur"]),
        "Resultaat": f"{eur(p['resultaat_eur'])}  ({pct(p['resultaat_pct'])})",
        "Deel van de portefeuille": pct(p["aandeel_pct"], met_teken=False),
    } for p in waardering.posities]), hide_index=True, width="stretch")

    st.caption(
        "**Koers in dollar** is de beweging van het aandeel zelf. **Resultaat** "
        "is wat dat in euro oplevert, dus inclusief de wisselkoers. Die twee "
        "verschillen zodra de dollar beweegt."
    )

    fx_start = float(uitvoering["fx_rate"])
    usd_nu = sum(p["aandelen"] * p["koers_usd"] for p in waardering.posities)
    usd_start = sum(float(p["invested_usd"]) for p in instap["positions"])
    splitsing = pf.splits_resultaat(
        (usd_nu / usd_start - 1.0) if usd_start else 0.0, fx_start, fx_nu)

    with st.expander("Hoeveel komt er van de koersen en hoeveel van de dollar?"):
        st.markdown(
            f"- De aandelen zelf: **{pct(splitsing['koersdeel_pct'])}**\n"
            f"- De wisselkoers: **{pct(splitsing['valutadeel_pct'])}**\n"
            f"- Samen: **{pct(splitsing['totaal_pct'])}**\n\n"
            "Deze twee tellen altijd precies op tot het totaal. Zo kan het "
            "wisselkoerseffect nooit dubbel meegerekend worden.\n\n"
            f"Bij de instap kreeg je {getal(fx_start, 4)} dollar voor een euro, "
            f"nu {getal(fx_nu, 4)}. "
            + ("De dollar is sterker geworden. Dat is in jouw voordeel: je "
               "Amerikaanse aandelen zijn meer euro's waard."
               if fx_nu < fx_start else
               "De dollar is zwakker geworden. Dat kost rendement: je "
               "Amerikaanse aandelen zijn minder euro's waard.")
        )


# ================================================== DEEL 2: de officiële keuze
st.header("De officiële selectie")

vastgelegd = pd.Timestamp(signaal["created_at_utc"]).tz_convert(HIER)
volgende = pd.Timestamp(signaal["signal_market_date"]) + pd.Timedelta(days=28)
dagen_te_gaan = (volgende.normalize() - pd.Timestamp.today().normalize()).days

s1, s2 = st.columns([3, 2])

with s1:
    st.dataframe(pd.DataFrame([{
        "Plaats": s["rank"],
        "Aandeel": s["ticker"],
        "Score": getal(s["score"], 2),
        "Koers bij de keuze": dollar(s["signal_close"]),
    } for s in signaal["selected"]]), hide_index=True, width="stretch")
    st.caption(
        "De score loopt van 0 tot 100 en wordt berekend uit acht eigenschappen "
        "van het aandeel. De vijf hoogste scores komen in de portefeuille. Bij "
        "een gelijke stand wint de alfabetisch eerste, zodat er geen willekeur in zit."
    )

with s2:
    st.markdown(
        f"**Gekozen op**  \n{datum_nl(signaal['signal_market_date'])}  \n\n"
        f"**Vastgelegd op**  \n{datum_nl(vastgelegd)} om "
        f"{vastgelegd.strftime('%H.%M')} uur  \n\n"
        f"**Gekozen uit**  \n{signaal['universe_count']} aandelen, waarvan "
        f"{signaal['eligible_count']} bruikbaar "
        f"({getal(float(signaal['coverage_pct']), 1)} %)"
    )
    if dagen_te_gaan > 0:
        st.info(
            f"**Volgende selectie: {datum_nl(volgende)}**, over {dagen_te_gaan} "
            "dagen. Die wachttijd van 28 dagen voorkomt dat er na een paar "
            "slechte dagen meteen iets anders gekozen wordt."
        )
    else:
        st.success(
            f"Er mag een nieuwe selectie vastgelegd worden. De vorige dateert "
            f"van {datum_nl(signaal['signal_market_date'])}."
        )


# ================================================= DEEL 3: is er niet gesleuteld
st.header("Is er niets aan gesleuteld?")

uit_db = [json.loads(r["ledger_line"]) for r in signalen]
keten_ok, keten_bericht = led.verify_ledger(uit_db)
hash_ok = all(sha256_text(r["canonical_payload"]) == r["entry_hash"] for r in signalen)
strategie_ok = signaal["strategy_hash"] == STRATEGY_HASH

c1, c2, c3 = st.columns(3)
c1.metric("Logboek", "In orde" if keten_ok else "Niet in orde",
          help="Elke vastgelegde keuze verwijst naar de vorige. Samen vormen ze "
               "een ketting die je niet kunt wijzigen zonder dat het opvalt.")
c2.metric("Controlegetal", "Klopt" if hash_ok else "Klopt niet",
          help="Een lang getal dat hoort bij de exacte inhoud. Verandert er ook "
               "maar een cijfer, dan klopt dat getal niet meer.")
c3.metric("Strategie", "Onveranderd" if strategie_ok else "Gewijzigd",
          help="De rekenformule is nog dezelfde als bij de eerste keuze.")

if keten_ok and hash_ok and strategie_ok:
    st.success(
        "Alle drie de controles zijn goed. De keuze van "
        f"{datum_nl(signaal['signal_market_date'], met_dag=False)} is sinds het "
        "vastleggen niet gewijzigd."
    )
else:
    st.error(
        "Er klopt iets niet aan het logboek. Zolang dat niet uitgezocht is, "
        "zeggen de cijfers op dit scherm niets. " + keten_bericht
    )

with st.expander("De technische details"):
    st.markdown(
        f"**Strategieversie**  \n`{signaal['strategy_version']}`\n\n"
        f"**Controlegetal van de formule**  \n`{signaal['strategy_hash']}`\n\n"
        f"**Controlegetal van deze keuze**  \n`{signaal['entry_hash']}`\n\n"
        f"**Verwijst naar de vorige keuze**  \n`{signaal['previous_hash']}`\n\n"
        f"**Controlegetal van de aandelenlijst**  \n`{signaal['universe_hash']}`\n\n"
        f"**Bron van de aandelenlijst**  \n{signaal['universe_source']}"
    )
    st.markdown(
        "De formule telt op tot honderd punten: 25 voor het rendement over "
        "twaalf maanden, 20 over zes maanden, 15 over drie maanden, 15 voor hoe "
        "het aandeel het deed tegenover SPY, 10 als de koers boven het "
        "200-daags gemiddelde staat, 5 als het 50-daags gemiddelde boven het "
        "200-daags staat, 5 voor een rustiger koersverloop en 5 voor een "
        "kleinere terugval."
    )
    if uitvoering:
        st.markdown(
            f"**Ingestapt op**  \n{datum_nl(uitvoering['execution_date'])}\n\n"
            f"**Wisselkoers toen**  \n1 euro = "
            f"{getal(float(uitvoering['fx_rate']), 6)} dollar\n\n"
            f"**Bron van de wisselkoers**  \n{uitvoering['fx_source']}\n\n"
            f"**Controlegetal van de instap**  \n`{uitvoering['exec_hash']}`"
        )


# ------------------------------------------------------------------ beheer
with st.sidebar:
    st.header("Beheer")
    st.caption(
        "Kijken kan zonder wachtwoord. Dat is alleen nodig voor beheer."
    )

    wachtwoord = st.text_input("Beheerderswachtwoord", type="password")
    ingesteld = CFG.get("ADMIN_WACHTWOORD") or ""
    juist = bool(ingesteld) and hmac.compare_digest(wachtwoord, ingesteld)

    if wachtwoord and not juist:
        st.error("Dat wachtwoord klopt niet.")
    elif juist:
        st.success("Je bent aangemeld als beheerder.")
        if dagen_te_gaan > 0:
            st.info(
                f"Een nieuwe selectie mag pas over {dagen_te_gaan} dagen, "
                f"vanaf {datum_nl(volgende)}."
            )
        else:
            st.warning(
                "De maandelijkse scan gebeurt niet op dit scherm. Die draait "
                "apart, zodat een trage verbinding of een haperende pagina "
                "nooit een officiële keuze kan verstoren."
            )

    st.divider()
    st.caption(
        "Dit is een proef met virtueel geld. Er worden geen echte orders "
        "geplaatst en dit is geen beleggingsadvies."
    )
