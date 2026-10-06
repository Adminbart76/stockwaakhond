# StockWaakhond V7.1 — projectcontext

Bart is geen ontwikkelaar. Neem technisch werk uit handen en geef hem alleen
stappen die hij werkelijk zelf moet doen.

## Waar het project staat

| | |
|---|---|
| Werkmap | `I:\Mijn Drive\02 – Eigen projecten\stockwaakhond` |
| Starten | typ `stock` in de terminal (`C:\Users\bartr\.local\bin\stock.cmd`) |
| GitHub | `Adminbart76/stockwaakhond`, **publiek** sinds 6 oktober 2026 |
| Supabase | project `StockWaakhond`, `ibdscndklmgvseksgrkb`, EU West (Ierland), gratis plan |
| Dashboard online | **https://stockwaakhond.streamlit.app** — draait sinds 6 oktober 2026 |
| Tests | 90, groen op 7 oktober 2026 (`python -m pytest`) |

De repo moest publiek omdat Streamlit Community Cloud op het gratis plan geen
privé-repo's leest. Nagekeken vóór het omzetten: geen sleutel en geen wachtwoord
in welke commit dan ook. Dat de code en het logboek openbaar staan is voor een
forward-test eerder sterk dan zwak — iedereen kan narekenen dat de keuze vooraf
vastlag.

Het dashboard draait op Python 3.12 met de secrets in de Streamlit-instellingen:
alleen `SUPABASE_URL`, `SUPABASE_ANON_KEY` en `ADMIN_WACHTWOORD`. De geheime
schrijfsleutel staat daar met opzet niet: de app leest alleen.

De sleutels staan in `SLEUTELS_INVULLEN.txt`, buiten Git gehouden door
`.gitignore`. Het beheerderswachtwoord is op 6 oktober 2026 ingevuld en werkt
op het online dashboard.

### Let op: er staat een oude kopie op C:

`C:\Users\bartr\Downloads\StockWaakhond_V7_forward_test\` is de map waarin V7
ooit begon. Daar staat alleen nog de oorspronkelijke `app.py` met een logboek
van één regel: geen `sw/`, geen `sql/`, geen tests, geen workflows.

Die map is **geen werkmap meer** en wordt niet bijgewerkt. Op 6 oktober 2026
verwees een audit van ChatGPT naar bestanden in die map, waarna een sessie bijna
in de verkeerde kopie begon te werken. Begin daarom altijd met `stock`, of
controleer dat je in `I:\Mijn Drive\...` zit voor je iets wijzigt. Twee kopieën
met verschillende logica is het laatste wat een hash-keten kan verdragen.

Eén ding uit die map is wél in gebruik en mag dus niet weg: de Python-omgeving
`...\StockWaakhond_V7\.venv` (Python 3.14.3 met de gepinde versies uit
`requirements.txt`). Beide `.bat`-bestanden starten die. De Python die standaard
in de terminal staat, heeft `yfinance` niet.

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

Daar kwamen op 7 oktober 2026 deze bij, bij de hardening:

9. **Geen koers is geen bedrag.** Liever niets tonen dan een getal dat eruitziet
   als de waarde van nu terwijl het op de aankoopkoers rust. Een verkeerd cijfer
   dat geloofwaardig oogt, is erger dan een leeg vak.
10. **Dividend gaat bij beide kanten door dezelfde functie.** Zou alleen
    StockWaakhond zijn dividend meegeteld krijgen, dan wint de strategie elk
    jaar ongeveer een procent dat ze niet verdiend heeft.
11. **`fx_asof` is het moment van lezen, niet een verzonnen slotmoment**, plus
    een venster waarbinnen dat lezen moet gebeuren. Reden: de dagbalk van
    `EURUSD=X` klikt nooit vast. Zie "De bevinding die punt 5 veranderde".
12. **Uit GitHub kan nooit in `signals` of `executions` geschreven worden.** De
    dagelijkse taak heeft een schrijfteken dat alleen koersen mag toevoegen; de
    instap blijft een handeling van Bart zelf op zijn eigen computer.

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

**Privé-apps op Streamlit Community Cloud** blijken op het gratis plan niet te
bestaan: het heet er letterlijk "deploy a public app", afschermen zit bij de
betaalde Snowflake-variant. Zie het open punt hieronder.

**Python-versies.** Lokaal draait 3.14.3 (de `.venv`, zie boven), het dashboard
en de GitHub-workflows draaien op 3.12. De gepinde versies installeren en slagen
op allebei; getest door de workflow op 6 oktober 2026. De 89 tests draaien ook
groen op de losse Python 3.14.4 die standaard in de terminal staat.

**Dividend is gebouwd maar nog nergens aangesloten.** De rekenkern kan het voor
beide kanten, maar zolang de fiscale percentages niet vastliggen, komt er niets
uit de tabel `dividends` op het scherm. Dat is geen vergetelheid: zelf een
bronheffing invullen zou een beslissing zijn die hier niet thuishoort. Beide
kanten missen nu evenveel, dus de vergelijking blijft eerlijk.

## Hoe het in elkaar zit

```
de kluis              de scanner            de etalage
Supabase       <--    lokaal bij Bart  -->  Streamlit online
alleen bijschrijven   doet de maandscan     leest alleen
```

- `sw/` is de rekenkern zonder schermcode: `strategy.py` (bevroren formule),
  `ledger.py` (lezen, controleren, bijschrijven — met opzet geen enkele functie
  die iets wist), `portfolio.py`, `prices.py`, `supabase_io.py`, en sinds
  7 oktober 2026 `beurskalender.py`: alle klokregels op één plek, zonder
  internet, met een `nu` die je in een test kunt meegeven.
- `streamlit_app.py` is het dashboard. Het leest alleen.
- `sql/01_schema.sql` en `sql/02_hardening.sql` zijn allebei idempotent;
  opnieuw draaien is veilig en verandert geen bestaande rij.
- `scripts/controleer_slot.py` valt de database aan met de geheime sleutel erbij.
  Draai dat na elke wijziging aan het schema. Stand 7 oktober 2026: 42 van 42
  goed, tegen de echte database.
- `scripts/maak_auditpakket.py` bouwt `stockwaakhond-voor-audit.zip` voor een
  externe controleur. De inhoud komt uit `git ls-files`, zodat er geen
  sleutelbestand in kan belanden; daarna wordt het pakket uitgepakt en worden
  de tests erin gedraaid. De vraag aan de controleur staat in
  `audit/VRAAG_<datum>.md`: per punt wat er gebouwd is, wat hij kan narekenen
  en waar hij zou moeten aanvallen. Daar hoort elke nieuwe ronde een eigen
  bestand te krijgen, niet een wijziging van het vorige.

Zeven tabellen zijn onaantastbaar gemaakt met een trigger die update en delete
weigert. Dat is de echte beveiliging: row level security wordt omzeild door de
geheime sleutel, een trigger niet.

## De instap van de virtuele portefeuille

Vastgelegd op dinsdag 6 oktober 2026, na de slotbel. Ligt voorgoed vast.

| | |
|---|---|
| Uitvoeringsdag | 2026-10-06, de eerste beursdag na het signaal |
| Wisselkoers | 1 euro = 1,1262530088 dollar (Yahoo `EURUSD=X` dagslotkoers) |
| Belegd | €998,50 (€1.000 min €1,50 transactiekost), 5 × €199,70 |
| `exec_hash` | `3468930ea4971945c8e8dad57b2cc797f9c825508368eff6bef5038090d3dae7` |

Instapkoersen: MRNA 187,46 · ILMN 273,54 · MPC 432,36 · HPE 70,48 · VLO 419,22 ·
SPY 779,09 (dollar).

Waarom de uitvoeringsregel ertoe doet, met een concreet voorbeeld: MRNA stond
bij het signaal op 203,21 en sloot de dag erna op 187,46, bijna acht procent
lager. Was er ingestapt tegen de koers die bij het kiezen al bekend was, dan
had de portefeuille vanaf dag één een winst getoond die niemand had kunnen maken.

## De hardening van 7 oktober 2026

Opgedragen door Bart op 6 oktober 2026 na een audit van ChatGPT, uitgevoerd op
7 oktober 2026. Zeven punten, alle zeven gebouwd, en diezelfde nacht ook
uitgevoerd: de SQL draait in Supabase, het schrijfteken staat erin, de drie
secrets staan in GitHub en `scripts/controleer_slot.py` geeft 42 van 42 goed
tegen de echte database. De harde grens eromheen,
letterlijk van Bart: wijzig nooit het bestaande ledger-record, de bestaande
execution, de strategiehash, de formule of de historische bewijsbestanden. Dat
is nagekomen: `forward_log/`, `bewijs/` en `app.py` zijn niet aangeraakt, en
`sw/strategy.py` draagt nog exact dezelfde `STRATEGY_SPEC` en strategiehash.

**1. Geen look-ahead meer bij een nieuw signaal.** De signaaldatum is voortaan
de laatste beursdag die echt voorbij is. Een nog lopende dag - waarvan Yahoo al
een voorlopige rij levert - kan geen signaaldag worden. De klokregels staan nu
in `sw/beurskalender.py`, los van internet en dus testbaar met een meegegeven
moment. `tests/test_signaaldatum.py` bewijst het met een dagrij die de Top-5 zou
omgooien.

**2. De keten wordt in de database zelf afgedwongen** (`sql/02_hardening.sql`):
volgnummer precies een hoger, verwijzing naar het controlegetal van het huidige
laatste signaal, minstens 28 dagen ertussen, formule én versie die werkelijk bij
de strategie horen, `created_at_utc` die klopt met de gehashte tekst, en de
keten-punt die onder slot gelezen wordt (`pg_advisory_xact_lock`) zodat twee
gelijktijdige pogingen geen twee ketens kunnen maken. Als laatste, bewust
achteraan, een vangnet: een signaaldatum die nog moet komen wordt altijd
geweigerd. Daar bouwt `scripts/controleer_slot.py` zijn aanvallen op, zodat een
ontbrekende regel nooit een vals signaal kan achterlaten. Bij `executions`
worden nu ook `fx_source` en `fx_asof` nagerekend.

**3. De geheime sleutel is uit GitHub.** De dagelijkse taak schrijft via een
databasefunctie `leg_dagkoersen_vast()` die alleen koersen mag toevoegen, met
een eigen schrijfteken (`SNAPSHOT_WRITE_TOKEN`) waarvan server-side alleen het
controlegetal staat. De instapstap is uit de workflow gehaald: die schrijft in
`executions`, en daar mag vanuit GitHub niets bij komen. De instap blijft lokaal
met `LEG INSTAP VAST (na 22u20).bat`.

**4. Dividend telt aan beide kanten.** `waardeer()` en `bouw_verloop()` nemen nu
ook het dividend van de daadwerkelijk gehouden SPY-aandelen mee, en
`dividend_reeks()` rekent beide kanten met exact dezelfde conventie om. De
fiscale percentages liggen nog niet vast (zie hieronder), dus er is nog niets
aan het dashboard gekoppeld; zolang er niets is, missen beide kanten evenveel.

**5. De wisselkoers heeft een venster gekregen.** Zie de bevinding hieronder:
dit is niet opgelost zoals de opdracht voorstelde, omdat de aanname niet bleek
te kloppen.

**6. Ontbreekt een koers, dan komt er geen bedrag.** `waardeer()` geeft een
`KoersOntbreekt` in plaats van stilletjes de aankoopkoers aan te houden. Het
dashboard neemt de rangorde: koers van nu, anders de laatst vastgelegde
slotkoers mét de dag erbij en een duidelijke melding, en anders geen bedrag en
dat gewoon zeggen.

**7. De workflow verbergt geen fouten meer.** `|| true` is weg. De scripts
geven exitcode 0 voor de normale situaties waarin er niets te doen is (weekend,
feestdag, beurs nog open, instap al gebeurd) en exitcode 1 als er werkelijk iets
mis is. `tests/test_werkwijze.py` bewaakt dat onderscheid.

### De bevinding die punt 5 veranderde

De opdracht ging ervan uit dat de dagslotkoers van `EURUSD=X` op een bepaald
moment definitief wordt, en dat `fx_asof` dat moment hoort te zijn. Gemeten op
6 oktober 2026 klopt die aanname niet:

- zolang de valutadag loopt (Yahoo dateert die in de tijd van Londen), volgt de
  dagbalk gewoon de koers van dit moment: om 22.54 bij ons stond er 1,126253,
  twee uur later 1,126380;
- is die dag voorbij, dan rapporteert Yahoo voor diezelfde datum een heel ander
  getal. Voor 5 oktober 2026 stond er achteraf 1,125454, terwijl de koers aan
  het eind van die dag 1,12246 was - 0,3 procent verschil.

Er bestaat voor deze bron dus geen moment waarop de dagkoers vastklikt. Daarom
is `fx_asof` nu het moment waarop de koers **gelezen** is, en dwingt de code af
dat dat lezen binnen het enige venster gebeurt waarin die waarde bij die
handelsdag hoort: na de slotbel in New York en voor middernacht in Londen. Bij
ons is dat tussen 22.20 en 01.00. De database bewaakt hetzelfde grover (fx_asof
tussen de slotbel en acht uur daarna); `tests/test_beurskalender.py` bewijst dat
de twee elkaar niet tegenspreken.

Een verzonnen "slotmoment" zou een getal benoemen dat op dat tijdstip niet gold.
Wat er nu staat, kan een latere lezer narekenen.

De bestaande uitvoering van 6 oktober 2026 blijft exact zoals ze is. Haar
`fx_asof` (20:54 UTC, 54 minuten na de slotbel) valt binnen beide vensters.

## Wat nu open staat

1. **De eerste geplande dagtaak nakijken.** Alles staat erin en is handmatig
   bewezen, maar de taak van 21:30 UTC heeft nog niet uit zichzelf gedraaid.
   Kijk de eerstvolgende beursdag bij Actions of ze groen is en of er een
   wisselkoers bij staat. Draait ze ooit na middernacht in Londen, dan slaat ze
   de wisselkoers over en wordt ze rood: de slotkoersen staan dan wel vast, maar
   die dag mist een wisselkoers en dat hoort opgemerkt te worden.

2. **Wie het dashboard mag zien.** Op het gratis plan van Streamlit heet het
   "deploy a public app": iedereen met de link kan kijken. Nog na te gaan of er
   in de app-instellingen onder Sharing alsnog een beperking tot genodigden
   mogelijk is. Zo niet, dan is dat een bewuste aanvaarding: lezen kan iedereen,
   wijzigen niemand. Het e-mailadres van Barts broer is nog niet doorgegeven.

Wat je er níet mee moet doen: de bevroren curve herrekenen met andere kosten,
de scan in de webapp zetten, of het openstaande kostenpunt zelf beslissen.
