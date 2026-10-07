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

from sw import herbalans as hb
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


def eur_verschil(bedrag: float) -> str:
    """Een bedrag met het teken vooraan: -€ 1,34 of +€ 1,34.

    Het teken moet vooraan staan, anders leest Streamlit het bedrag als
    positief en zet het een groene pijl omhoog boven een verlies.
    """
    teken = "-" if bedrag < 0 else "+"
    return teken + "€ " + _komma(f"{abs(bedrag):,.2f}")


def dollar(bedrag: float) -> str:
    return "$ " + _komma(f"{bedrag:,.2f}")


def getal(waarde: float, decimalen: int = 2) -> str:
    return _komma(f"{waarde:,.{decimalen}f}")


def pct(waarde: float, met_teken: bool = True) -> str:
    # Afgerond op twee cijfers is een heel klein verlies gewoon nul. Dan hoort
    # er geen minteken voor te staan: "-0,00 %" leest als een fout.
    if round(waarde, 2) == 0:
        waarde = 0.0
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
    """Slotkoersen per dag voor de grafiek.

    Eerst uit onze eigen database, want die koersen liggen vast en schuiven
    niet meer. Pas als daar te weinig in staat, halen we ze bij Yahoo. Dat
    scheelt niet alleen wachttijd: Yahoo weigert geregeld verzoeken van
    gedeelde servers, en dan moet het dashboard het zonder kunnen stellen.
    """
    db = Supabase.lezer(CFG)

    koersen = pd.DataFrame()
    fx = pd.Series(dtype=float)

    try:
        rijen = db.select(
            "price_snapshots",
            f"select=snapshot_date,ticker,close_raw&snapshot_date=gte.{vanaf}"
            "&order=snapshot_date.asc&limit=5000")
        if rijen:
            ruw = pd.DataFrame(rijen)
            ruw["snapshot_date"] = pd.to_datetime(ruw["snapshot_date"])
            koersen = ruw.pivot(index="snapshot_date", columns="ticker", values="close_raw")
            koersen = koersen.astype(float).sort_index()
            koersen.index.name = None

        fx_rijen = db.select(
            "fx_snapshots",
            f"select=snapshot_date,rate&pair=eq.EURUSD&snapshot_date=gte.{vanaf}"
            "&order=snapshot_date.asc&limit=5000")
        if fx_rijen:
            fx = pd.Series(
                [float(r["rate"]) for r in fx_rijen],
                index=pd.to_datetime([r["snapshot_date"] for r in fx_rijen]),
            ).sort_index()
    except Exception:
        pass

    compleet = (
        not koersen.empty
        and len(fx) >= len(koersen)
        and all(t in koersen.columns for t in tickers)
    )
    if compleet:
        return koersen, fx, "eigen database"

    echt, _ = pr.haal_koersen(list(tickers), start=vanaf)
    fx_yahoo = pr.haal_wisselkoers(start=vanaf)
    return echt, fx_yahoo, "Yahoo Finance"


@st.cache_data(ttl=120, show_spinner=False)
def haal_actuele_koersen(tickers: tuple):
    koersen, tijdstip = pr.laatste_koersen(list(tickers))
    fx = pr.haal_wisselkoers(start=str((pd.Timestamp.today() - pd.Timedelta(days=10)).date()))
    return koersen, tijdstip, (float(fx.iloc[-1]) if len(fx) else None)


def laatst_vastgelegd(frame: pd.DataFrame):
    """Per aandeel de laatste slotkoers die we hebben, en van welke dag die is.

    Dit is de terugvaloptie als de koers van nu niet op te halen is. Het is een
    echte koers van een echte dag - alleen niet van vandaag, en dat hoort het
    scherm er dan ook bij te zeggen.
    """
    koersen, dagen = {}, {}
    if frame is None or len(frame) == 0:
        return koersen, dagen
    for kolom in frame.columns:
        reeks = frame[kolom].dropna()
        reeks = reeks[reeks > 0]
        if len(reeks):
            koersen[str(kolom)] = float(reeks.iloc[-1])
            dagen[str(kolom)] = pd.Timestamp(reeks.index[-1])
    return koersen, dagen


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
nieuwe_keuze = [s["ticker"] for s in signaal["selected"]]

# De portefeuille loopt door. Er wordt een keer 1.000 euro ingelegd en daarna
# alleen gewisseld, dus wat er NU in zit staat in de laatste uitvoering - niet
# per se in de uitvoering van het laatste signaal. Tussen een nieuwe selectie en
# de wissel de avond erna blijft de oude portefeuille gewoon de portefeuille.
uitvoeringen = gegevens["uitvoeringen"]
uitvoering, keten_fout = None, None
try:
    keten_ok_nu, keten_bericht = hb.verify_keten(uitvoeringen)
    if keten_ok_nu:
        uitvoering = hb.laatste_uitvoering(uitvoeringen)
    else:
        keten_fout = keten_bericht
except Exception as fout:
    keten_fout = str(fout)

if keten_fout:
    st.error(
        "**De gegevens van de portefeuille spreken elkaar tegen, dus er wordt "
        "hier niets getoond.**\n\n"
        "De opeenvolgende wissels horen een sluitende reeks te vormen. Dat is "
        "nu niet zo, en dan is elk bedrag dat we hier zouden tonen een gok. "
        "Dit hoort nagekeken te worden voor er verder iets mee gedaan wordt.\n\n"
        "Technische melding: " + keten_fout
    )
    st.stop()

tickers = (
    [p["ticker"] for p in uitvoering["positions"]] if uitvoering else nieuwe_keuze)
wacht_op_wissel = bool(
    uitvoering is not None and uitvoering["entry_hash"] != signaal["entry_hash"])
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
    # De laatste uitvoering beschrijft de huidige toestand: welke aandelen,
    # hoeveel stuks, hoeveel contant geld, en de onveranderde SPY-positie.
    instap = {
        "start_capital_eur": float(uitvoering["start_capital_eur"]),
        "invested_eur": float(uitvoering["invested_eur"]),
        "cost_eur": float(uitvoering["cost_eur"]),
        "execution_date": uitvoering["execution_date"],
        "cash_usd": float(uitvoering.get("cash_usd") or 0.0),
        "positions": uitvoering["positions"],
        "benchmark": uitvoering["benchmark"],
    }

    nodig = sorted(set(tickers) | {"SPY"})
    # Voor de grafiek is ook het verleden nodig: wat er vroeger in de
    # portefeuille zat, hoort nog bij het verloop van toen.
    eerste = hb.sorteer_keten(uitvoeringen)[0]
    alles_nodig = sorted(set(hb.tickers_in_keten(uitvoeringen)) | set(nodig))

    # De vastgelegde dagkoersen uit onze eigen database. Die hebben we toch al
    # nodig voor de grafiek, en ze zijn tegelijk de terugvaloptie voor
    # hieronder: een echte slotkoers van een echte dag.
    dagkoersen, fx_reeks, koersbron, dagkoersen_fout = (
        pd.DataFrame(), pd.Series(dtype=float), None, None)
    try:
        dagkoersen, fx_reeks, koersbron = haal_dagkoersen(
            tuple(alles_nodig), eerste["execution_date"])
    except Exception as fout:
        dagkoersen_fout = str(fout)

    try:
        live, tijdstip, fx_live = haal_actuele_koersen(tuple(nodig))
    except Exception:
        live, tijdstip, fx_live = {}, None, None

    # De rangorde: eerst de koers van nu, anders de laatst vastgelegde
    # slotkoers (en dan zegt het scherm van welke dag die is), en is er geen
    # van beide, dan wordt er geen bedrag getoond. Een bedrag dat eruitziet als
    # "nu waard" terwijl het de aankoopkoers is, is erger dan geen bedrag.
    vastgelegd, vastgelegd_op = laatst_vastgelegd(dagkoersen)
    koersen_nu, koers_van = {}, {}
    for t in nodig:
        if live.get(t) and float(live[t]) > 0:
            koersen_nu[t] = float(live[t])
            koers_van[t] = None
        elif vastgelegd.get(t):
            koersen_nu[t] = vastgelegd[t]
            koers_van[t] = vastgelegd_op[t]
    ontbreekt = [t for t in nodig if t not in koersen_nu]

    if fx_live:
        fx_nu, fx_van = float(fx_live), None
    elif len(fx_reeks):
        fx_nu, fx_van = float(fx_reeks.iloc[-1]), pd.Timestamp(fx_reeks.index[-1])
    else:
        fx_nu, fx_van = None, None

    verouderd = [t for t in nodig if koers_van.get(t) is not None]
    verse_koersen = not verouderd and not ontbreekt

    st.header("Hoe staat de virtuele portefeuille ervoor?")

    if wacht_op_wissel:
        st.info(
            f"**Er is een nieuwe selectie vastgelegd op "
            f"{datum_nl(signaal['signal_market_date'])}: "
            f"{', '.join(nieuwe_keuze)}.**\n\n"
            "Hieronder staat nog de portefeuille zoals ze nu is. Ze wisselt "
            "tegen de slotkoers van de eerste beursdag na die keuze; dat "
            "gebeurt met de hand, na de slotbel. Er komt geen geld bij: wat de "
            "portefeuille op dat moment waard is, wordt opnieuw over vijf "
            "aandelen verdeeld."
        )

    waardering = None
    if ontbreekt or fx_nu is None:
        if not ontbreekt:
            zin = ("Er is op dit moment geen betrouwbare wisselkoers: niet van "
                   "nu en ook geen eerder vastgelegde")
        elif len(ontbreekt) == len(nodig):
            zin = ("Er is op dit moment voor geen enkel aandeel een betrouwbare "
                   "koers: niet van nu en ook geen eerder vastgelegde slotkoers")
        else:
            zin = (f"Voor {', '.join(ontbreekt)} is er op dit moment geen "
                   "betrouwbare koers: niet van nu en ook geen eerder "
                   "vastgelegde slotkoers")
        st.warning(
            "**We kunnen nu niet zeggen wat de portefeuille waard is.**\n\n"
            f"{zin}. Er wordt dan met opzet "
            "geen bedrag berekend. Een cijfer dat eruitziet als de waarde van nu "
            "terwijl het op een oude of verzonnen koers rust, zou erger zijn dan "
            "geen cijfer.\n\n"
            "De vastgelegde selectie en de controles onderaan deze pagina "
            "kloppen onverminderd. Probeer het over een paar minuten opnieuw."
        )
    else:
        waardering = pf.waardeer(
            instap, koersen_nu, fx_nu,
            datum=str(pd.Timestamp.today().date()),
            spy_koers_usd=koersen_nu["SPY"],
        )

if uitvoering is not None and waardering is not None:
    k1, k2, k3 = st.columns(3)
    k1.metric("Ingelegd", eur(waardering.inleg_eur),
              help="Het virtuele startbedrag. Er is nooit echt geld belegd.")
    k2.metric("Laatst bekende waarde" if verouderd else "Nu waard",
              eur(waardering.totaal_eur),
              delta=f"{eur_verschil(waardering.resultaat_eur)}  "
                    f"({pct(waardering.resultaat_pct)})")
    k3.metric("Dezelfde €1.000 in SPY", eur(waardering.spy_waarde_eur),
              delta=f"{eur_verschil(waardering.spy_resultaat_eur)}  "
                    f"({pct(waardering.spy_resultaat_pct)})",
              help="SPY is een fonds dat de 500 grootste Amerikaanse "
                   "beursbedrijven volgt. Het is de maatstaf: haalt de "
                   "strategie meer dan dit, dan was het kiezen de moeite waard.")

    # Zeggen wat er NIET in zit. "Beide kanten missen evenveel" is waar, maar
    # wie dat niet weet, leest deze bedragen als het volledige rendement.
    st.caption(
        "Dit zijn alleen de koersen. Uitgekeerd dividend telt bij geen van de "
        "twee mee: niet bij de vijf aandelen en niet bij SPY. Allebei de "
        "bedragen zouden er dus iets hoger uitkomen."
    )

    # Een verschil van enkele honderdsten van een procent is ruis, geen
    # voorsprong. Dat zo noemen zou een leek een conclusie laten trekken die
    # de cijfers niet dragen.
    voor = waardering.voorsprong_pct
    if abs(voor) < 0.10:
        st.markdown(
            f"### StockWaakhond en SPY gaan vrijwel gelijk op\n"
            f"StockWaakhond staat op {pct(waardering.resultaat_pct)}, SPY op "
            f"{pct(waardering.spy_resultaat_pct)}. Het verschil is {pct(voor)}, "
            "en dat is te klein om iets te betekenen."
        )
    else:
        st.markdown(
            f"### {'Voorsprong' if voor > 0 else 'Achterstand'} op SPY: {pct(voor)}\n"
            f"StockWaakhond staat op {pct(waardering.resultaat_pct)}, SPY op "
            f"{pct(waardering.spy_resultaat_pct)}. "
            + ("De strategie doet het dus beter dan de markt."
               if voor > 0 else "De strategie doet het dus minder goed dan de markt.")
        )

    if verouderd:
        dagen = sorted({koers_van[t] for t in verouderd})
        wanneer = " en ".join(datum_nl(d) for d in dagen)
        welke = ("alle koersen hierboven zijn de laatst vastgelegde slotkoersen"
                 if len(verouderd) == len(nodig) else
                 f"voor {', '.join(verouderd)} staat hierboven de laatst "
                 f"vastgelegde slotkoers")
        st.warning(
            f"**Deze bedragen zijn niet van nu.** De koersen van dit moment "
            f"konden niet opgehaald worden: {welke}, van {wanneer}. Alles wat "
            f"de beurs daarna gedaan heeft, zit er niet in. {beurs_uitleg}"
        )
    elif tijdstip:
        gemeten = pd.Timestamp(tijdstip)
        if gemeten.tzinfo is None:
            gemeten = gemeten.tz_localize("UTC")
        gemeten = gemeten.tz_convert(HIER)
        st.caption(
            f"Koersen van {datum_nl(gemeten, met_dag=False)} om "
            f"{gemeten.strftime('%H.%M')} uur. Dit zijn vertraagde koersen van "
            f"Yahoo Finance, geen koersen van dit moment. {beurs_uitleg}"
        )

    st.caption(
        (f"Wisselkoers van {datum_nl(fx_van, met_dag=False)}"
         if fx_van is not None else "Wisselkoers nu")
        + f": 1 euro = {getal(fx_nu, 4)} dollar. "
        + f"Bij de instap was dat {getal(float(uitvoering['fx_rate']), 4)} dollar."
    )


# ------------------------------------------------------------------ grafieken
if uitvoering is not None:
    st.header("Verloop sinds de start")

    verloop = pd.DataFrame()
    if dagkoersen_fout:
        st.warning(
            "Het verloop kon op dit moment niet berekend worden."
            "\n\nTechnische melding: " + dagkoersen_fout
        )
    else:
        try:
            # Over de hele keten: op elke wisseldag neemt het nieuwe mandje het
            # over van het oude, met dezelfde 1.000 euro als meetlat.
            verloop = hb.bouw_verloop_keten(uitvoeringen, dagkoersen, fx_reeks)
        except Exception as fout:
            st.warning(
                "Het verloop kon op dit moment niet berekend worden."
                "\n\nTechnische melding: " + str(fout)
            )

    if len(verloop) >= 2:
        # reset_index is hier geen opsmuk: zonder dat heet de index van `lang`
        # ook "datum", net als de kolom, en dan weet sort_values hieronder niet
        # welke van de twee bedoeld wordt. Dat valt pas op zodra er meer dan
        # een dag in de grafiek staat.
        lang = pd.concat([
            pd.DataFrame({"datum": verloop.index, "waarde": verloop["portefeuille_eur"],
                          "reeks": "StockWaakhond"}),
            pd.DataFrame({"datum": verloop.index, "waarde": verloop["spy_eur"],
                          "reeks": "SPY"}),
        ]).reset_index(drop=True)
        schaal = alt.Scale(domain=["StockWaakhond", "SPY"], range=[KLEUR_SW, KLEUR_SPY])

        # Bij weinig dagen zet Altair uit zichzelf meerdere streepjes binnen
        # dezelfde dag, en dan staat er acht keer "06/10" onder de grafiek.
        # Een streepje per dag is dan het enige dat klopt.
        as_datum = alt.Axis(format="%d/%m", grid=False)
        if len(verloop) <= 10:
            as_datum = alt.Axis(format="%d/%m", grid=False,
                                tickCount={"interval": "day", "step": 1})

        lijnen = alt.Chart(lang).mark_line(strokeWidth=2).encode(
            x=alt.X("datum:T", title=None, axis=as_datum),
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
            + ("  \nEr is één keer €1.000 ingelegd. Bij een nieuwe selectie "
               "wordt die portefeuille herverdeeld; er komt nooit geld bij. "
               "SPY blijft gewoon liggen en betaalt dus ook niets voor die "
               "wissels."
               if len(uitvoeringen) > 1 else "")
            + "  \nDividend is bij geen van de twee meegerekend: dit zijn de "
              "koersen."
            + ("  \nDe slotkoersen in deze grafiek liggen vast in onze eigen "
               "database en veranderen niet meer achteraf."
               if koersbron == "eigen database" else
               "  \nDe slotkoersen komen rechtstreeks van Yahoo Finance.")
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


# ------------------------------------------------------------------- posities
if uitvoering is not None and waardering is not None:
    st.header("De vijf posities")

    if len(uitvoeringen) > 1:
        st.caption(
            f"Gekocht bij de wissel van "
            f"{datum_nl(uitvoering['execution_date'])}. Het resultaat per "
            f"aandeel hieronder loopt dus vanaf die dag; het totaal bovenaan "
            f"loopt vanaf de start."
        )

    rijen = []
    for p in waardering.posities:
        rij = {
            "Aandeel": p["ticker"],
            "Aantal": getal(p["aandelen"], 4),
            "Gekocht aan": dollar(p["aankoopkoers_usd"]),
            # Zolang alles van nu is, hoort er "nu" boven. Zodra er een oudere
            # koers tussen zit, zou die kop tegenspreken wat de kolom ernaast zegt.
            ("Koers" if verouderd else "Koers nu"): dollar(p["koers_usd"]),
        }
        if verouderd:
            van = koers_van.get(p["ticker"])
            rij["Koers van"] = "nu" if van is None else pd.Timestamp(van).strftime("%d/%m")
        rij.update({
            "Koers in dollar": pct(p["koersrendement_pct"]),
            "Ingelegd": eur(p["inzet_eur"]),
            ("Waard" if verouderd else "Nu waard"): eur(p["waarde_eur"]),
            "Resultaat": f"{eur_verschil(p['resultaat_eur'])}  ({pct(p['resultaat_pct'])})",
            "Deel van de portefeuille": pct(p["aandeel_pct"], met_teken=False),
        })
        rijen.append(rij)

    st.dataframe(pd.DataFrame(rijen), hide_index=True, width="stretch")

    st.caption(
        "**Koers in dollar** is de beweging van het aandeel zelf. **Resultaat** "
        "is wat dat in euro oplevert, dus inclusief de wisselkoers. Die twee "
        "verschillen zodra de dollar beweegt."
        + ("  \n**Koers van** zegt van welke dag de koers is. Staat er een datum "
           "in plaats van \"nu\", dan is dat de laatst vastgelegde slotkoers."
           if verouderd else "")
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
