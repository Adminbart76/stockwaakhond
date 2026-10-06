# StockWaakhond V7.1 — projectcontext

Bart is geen ontwikkelaar. Neem technisch werk uit handen en geef hem alleen
stappen die hij werkelijk zelf moet doen.

## Waar het project staat

| | |
|---|---|
| Werkmap | `I:\Mijn Drive\02 – Eigen projecten\stockwaakhond` |
| GitHub | `Adminbart76/stockwaakhond`, **publiek** sinds 6 oktober 2026 |
| Supabase | project `StockWaakhond`, `ibdscndklmgvseksgrkb`, EU West (Ierland), gratis plan |
| Dashboard online | **https://stockwaakhond.streamlit.app** — draait sinds 6 oktober 2026 |
| Tests | 41, groen op 6 oktober 2026 (`python -m pytest`) |
| Oorspronkelijke map | `C:\Users\bartr\Downloads\StockWaakhond_V7_forward_test\` — onaangeroerd gelaten |

De repo moest publiek omdat Streamlit Community Cloud op het gratis plan geen
privé-repo's leest. Nagekeken vóór het omzetten: geen sleutel en geen wachtwoord
in welke commit dan ook. Dat de code en het logboek openbaar staan is voor een
forward-test eerder sterk dan zwak — iedereen kan narekenen dat de keuze vooraf
vastlag.

Het dashboard draait op Python 3.12 met de secrets in de Streamlit-instellingen:
alleen `SUPABASE_URL`, `SUPABASE_ANON_KEY` en `ADMIN_WACHTWOORD`. De geheime
schrijfsleutel staat daar met opzet niet: de app leest alleen.

De sleutels staan in `SLEUTELS_INVULLEN.txt`, buiten Git gehouden door
`.gitignore`. Het beheerderswachtwoord daarin is op 6 oktober 2026 nog leeg.

## De forward-test is heilig

Eén signaal vastgelegd, en dat blijft zoals het is:

| | |
|---|---|
| Strategie | `SW_SCORE_V3_FROZEN_2026-10-06` |
| Signaaldatum | maandag 5 oktober 2026 |
| Vastgelegd | dinsdag 6 oktober 2026, 12:49 UTC |
| Top-5 | MRNA, ILMN, MPC, HPE, VLO |
| `entry_hash` | `0426e47ccd6e0b4f7fcecd772ce21dc5778db862e359f5eb4d239f5ce8bd5d15` |
| `strategy_hash` | `a399aecc207510c77450cd015f4f23e2b3639fc642eb9bcc29e95cbe2b84cc18` |
| `universe_hash` | `3114cc28ea6cb1aa0b1025f7ee01fffa9c697244cf64ca20cf013a1c8f9e813b` |

De volledige verificatie van 6 oktober 2026 staat in
`bewijs/verificatie_2026-10-06.txt`. De 503 universumsymbolen zijn die dag uit
Wikipedia gereproduceerd met exact dezelfde `universe_hash` en liggen nu vast in
`bewijs/`; ze waren nergens bewaard en dat was vluchtig bewijs.

**Nooit doen:** de scoreformule aanpassen, een vastgelegd signaal wijzigen of
verwijderen, of een functie schrijven die dat mogelijk maakt. Een nieuwe
strategie is een nieuwe strategieversie met een eigen logboek, nooit een
aanpassing van deze.

`tests/test_bevroren_strategie.py` faalt bij de kleinste wijziging aan de
formule. Faalt die test, dan is dat geen testprobleem maar een alarm.

## Wat vastligt als beslissing

Genomen op 6 oktober 2026, met de reden erbij:

1. **Fracties van aandelen zijn toegestaan.** Met €200 koop je geen heel ILMN,
   MPC of VLO; zonder fracties kan €1.000 niet gelijk over vijf verdeeld worden.
2. **Echte koersen voor de portefeuille, dividend apart als geld.** De voor
   dividend herrekende koersen dalen met terugwerkende kracht, waardoor het
   rendement maanden later nog zou verschuiven. Die twee nooit mengen: dan telt
   het dividend dubbel.
3. **Wisselkoers: Yahoo `EURUSD=X` dagslotkoers.** Valuta handelt door tot na de
   Amerikaanse slotbel, dus die koers sluit aan bij de aandelenkoers van
   dezelfde dag. De ECB-referentiekoers ligt zes uur eerder en past slechter.
4. **Alles in dollar optellen, pas op het einde één keer omzetten.** Zo kan het
   wisselkoerseffect niet dubbel tellen. De uitsplitsing op het scherm is
   weergave, geen tweede berekening.
5. **Pakketversies vastgepind** in `requirements.txt`. De formule was gehasht,
   de uitvoering niet; een andere pandas-versie kan in theorie een andere Top-5
   geven.
6. **`verify_ledger` toetst elk record aan zijn eigen formule**, niet aan de
   formule die toevallig in de code staat. Strenger (het vangt nu ook een
   formule die niet bij de opgeslagen hash past) en het blokkeert geen
   toekomstige tweede strategie.
7. **Het lokale bestand is de bron van waarheid, Supabase is de spiegel.** Bij
   het kleinste verschil: stoppen en melden, niets rechttrekken.
8. **De maandscan draait niet in de webapp.** 503 aandelen ophalen vanaf een
   gedeeld IP-adres wordt door Yahoo geblokkeerd en duurt te lang voor een
   webpagina.

## Wat bewust open blijft

**De kostenconventie bij een wissel — beslissen vóór 3 november 2026.**
Bij de eerste instap rekent de code 0,15 % op €1.000, en dat klopt. Bij een
volledige wissel van vijf aandelen verkoop je én koopt je, dus €2.000
verhandeld, maar de code rekent nog steeds 0,15 % in plaats van 0,30 %. Dat is
geen programmeerfout (het volgt de gangbare conventie van eenzijdige omzet) maar
wel een definitiekwestie. Dit speelt pas vanaf het tweede signaal.
**Niet eenzijdig wijzigen: het hoort bij de bevroren opzet.** Het voorstel is de
bevroren curve ongemoeid te laten en er een tweede, realistische curve naast te
zetten.

**Belgische beurstaks.** Ordegrootte 0,35 % per richting kan bij maandelijkse
rotatie het verschil maken tussen winst en verlies. Nu niet toevoegen; hoort bij
de realistische tweede curve.

**Dividendbelasting.** De tabel `dividends` heeft een veld voor netto, maar de
percentages zijn nog niet vastgelegd. Eerste dividend van MPC en VLO wordt
rond november 2026 verwacht, HPE en SPY rond december.

**Grenzen van privé-apps op Streamlit Community Cloud** zijn nog niet nagekeken.
Lokaal draait Python 3.14.3; dat is mogelijk nieuwer dan wat Community Cloud
aanbiedt, dus de gepinde versies moeten daar getest worden.

## Hoe het in elkaar zit

```
de kluis              de scanner            de etalage
Supabase       <--    lokaal bij Bart  -->  Streamlit online
alleen bijschrijven   doet de maandscan     leest alleen
```

- `sw/` is de rekenkern zonder schermcode: `strategy.py` (bevroren formule),
  `ledger.py` (lezen, controleren, bijschrijven — met opzet geen enkele functie
  die iets wist), `portfolio.py`, `prices.py`, `supabase_io.py`.
- `streamlit_app.py` is het dashboard. Het leest alleen.
- `sql/01_schema.sql` is idempotent; opnieuw draaien is veilig.
- `scripts/controleer_slot.py` valt de database aan met de geheime sleutel erbij.
  Draai dat na elke wijziging aan het schema. Stand 6 oktober 2026: 23 van 23 goed.

Zeven tabellen zijn onaantastbaar gemaakt met een trigger die update en delete
weigert. Dat is de echte beveiliging: row level security wordt omzeild door de
geheime sleutel, een trigger niet.

## Wat nu open staat

1. **De instap van de €1.000 vastleggen.** De uitvoeringsdag is de eerste
   beursdag na het signaal, dus dinsdag 6 oktober 2026. Kan pas na 22.20 uur
   Belgische tijd: `scripts/leg_instap_vast.py`, of het bestand
   `LEG INSTAP VAST (na 22u20).bat`. Het script weigert zolang de beurs open is,
   want een voorlopige koers mag nooit voor altijd vastgelegd worden.
2. **De drie sleutels als secrets in GitHub zetten**, anders kunnen de
   workflows niet bij Supabase. Dat is `gh secret set SUPABASE_URL` enzovoort;
   die handeling werd op 6 oktober geweigerd omdat het om geheimen gaat en moet
   met Barts toestemming opnieuw. Zonder dit draait de dagelijkse taak wel maar
   schrijft hij niets weg, en moet de instap met de hand gebeuren.
3. **Wie het dashboard mag zien.** Op het gratis plan van Streamlit heet het
   "deploy a public app": iedereen met de link kan kijken. Nog na te gaan of er
   in de app-instellingen onder Sharing alsnog een beperking tot genodigden
   mogelijk is. Zo niet, dan is dat een bewuste aanvaarding: lezen kan iedereen,
   wijzigen niemand. Het e-mailadres van Barts broer is nog niet doorgegeven.

Wat je er níet mee moet doen: de bevroren curve herrekenen met andere kosten,
de scan in de webapp zetten, of het openstaande kostenpunt zelf beslissen.
