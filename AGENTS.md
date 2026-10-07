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
| Tests | 195, groen op 7 oktober 2026 (`python -m pytest`) |

De repo moest publiek omdat Streamlit Community Cloud op het gratis plan geen
privé-repo's leest. Nagekeken vóór het omzetten: geen sleutel en geen wachtwoord
in welke commit dan ook. Dat de code en het logboek openbaar staan is voor een
forward-test eerder sterk dan zwak — iedereen kan narekenen dat de keuze vooraf
vastlag.

Het dashboard draait op Python 3.12 met de secrets in de Streamlit-instellingen:
alleen `SUPABASE_URL`, `SUPABASE_ANON_KEY` en `ADMIN_WACHTWOORD`. De geheime
schrijfsleutel staat daar met opzet niet: de app leest alleen.

**Na een push die iets in `sw/` wijzigt: de app opnieuw opstarten.** Streamlit
Community Cloud haalt de nieuwe code wel op ("Updated app!"), maar start het
Python-proces niet opnieuw. Modules die al ingeladen zijn, blijven de oude.
Daardoor draaide het dashboard van 6 oktober 16:49 UTC tot 7 oktober 01:10 UTC
nog op de `sw/portfolio.py` van vóór de hardening, en crashte het op de nieuwe
import. Opnieuw opstarten: rechtsonder **Manage app**, dan het menu met de drie
puntjes, **Reboot app**. Daarna de pagina openen en kijken of ze er staat - een
app die stuk is, toont een rode foutmelding aan iedereen met de link.

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

Daar kwamen op 7 oktober 2026 deze bij, na auditronde 2:

13. **Er is één doorlopende portefeuille.** Eén keer €1.000, en daarna alleen
    nog wisselen: bij een nieuw signaal wordt de dan geldende waarde
    herverdeeld over de nieuwe Top-5. Winst, verlies en contant geld gaan mee.
    Er komt nooit geld bij. De regels staan in
    `audit/ONTWERP_doorlopende_portefeuille_2026-10-07.md`, de rekenkern in
    `sw/herbalans.py`.
14. **De omzetformule is letterlijk die van de bevroren simulatie**
    (`simulate_forward()` in `app.py`): omzet = 0,5 × (som van de
    gewichtsverschillen + contant geld), kost = omzet × 0,15 %. Daardoor komt de
    instap van 6 oktober er ongewijzigd uit, en blijft het openstaande
    kostenpunt hieronder open in plaats van stilletjes beslist.
    `tests/test_herbalans.py` bewaakt dat de twee niet uit elkaar lopen.
15. **SPY wordt bij een wissel letterlijk overgenomen.** Zelfde aantal
    aandelen, zelfde aankoopkoers, geen kost. De maatstaf kan dus per
    constructie niet meebetalen aan de rotatie van StockWaakhond en wordt nooit
    teruggezet naar €1.000.
16. **Een dag is compleet of hij bestaat niet.** Ontbreekt één koers van een
    actieve positie of van SPY, dan wordt er niets vastgelegd en faalt de taak.
    Een halve dag is niet te herstellen en geeft een gat dat niemand ziet.
17. **De automatische deur kent alleen vandaag en alleen de huidige
    portefeuille.** `leg_dagkoersen_vast()` weigert elke andere datum, elk
    moment voor de slotbel, elk weekend en elk aandeel dat niet in de actuele
    uitvoering zit. Een oude dag bijschrijven is een aparte beheershandeling met
    de geheime sleutel: `scripts/herstel_dagkoers.py`, met reden en
    beheerslogboek.
18. **Het dashboard zegt wat er wel en niet in zit.** Dividend telt sinds
    7 oktober 2026 aan beide kanten mee (bruto), en zolang er nog niets is
    uitgekeerd staat dat er ook: "er is nog geen dividend uitgekeerd; zodra dat
    gebeurt telt het bij beide kanten mee". Zonder die zin leest iemand de
    cijfers als "dividend zit er niet in". De beurstaks zit er niet in, en ook
    dat staat er.
19. **De database is nooit het enige controlespoor.** Wie eigenaar is van de
    database kan triggers en functies wijzigen, uitzetten of weghalen - ook de
    functie die vertelt dat ze aanstaan. Daarom blijft het spoor erbuiten
    nodig: de openbare Git-geschiedenis, de hash-keten in `forward_log/` en de
    bestanden in `bewijs/`. Wijkt de database daarvan af, dan is de database
    fout. Dat staat zo in `sql/03_smalle_deur.sql` en in de uitvoer van
    `scripts/controleer_slot.py`.

Daar kwamen op 7 oktober 2026 deze bij, na auditronde 3. Ze stonden tot dan toe
als open punt; dat zijn ze niet meer. Het volledige ontwerp met de redenering
staat in `audit/ONTWERP_dividend_fx_kosten_2026-10-07.md`.

20. **Dividend is bruto, aan beide kanten.** Het volledige uitgekeerde bedrag,
    voor belasting. Er valt bij een wissel niets meer te kiezen; de vlag
    `--dividend=` bestaat niet meer. Reden: netto hangt af van woonplaats,
    broker en belastingregels die tijdens een forward-test veranderen, en dan
    meet de curve niet meer de strategie.
21. **De ex-datum bepaalt het recht, de betaaldatum het geld.** Het recht wordt
    gerekend met het aantal aandelen dat we hadden vóór de ex-dag - ook van een
    aandeel dat vóór de betaaldag verkocht is. Het geld telt pas mee vanaf de
    betaaldag en gaat dus mee in de eerste wissel daarna. Rekenen op de ex-datum
    zou geld beleggen dat er nog niet is; het recht bepalen op de betaaldatum
    zou een dividend laten verdwijnen dat we wel degelijk krijgen.
22. **SPY herbelegt zijn bruto dividend op de betaaldag**, tegen de
    eerstvolgende geldige slotkoers, zonder kosten. Het aantal SPY-aandelen
    groeit daardoor; de aankoopkoers van de eerste aankoop blijft staan. Noem
    dat "SPY buy-and-hold met bruto dividendherbelegging op betaaldatum" en niet
    "total return index": die reeksen herbeleggen vaak op de ex-datum of met een
    andere belastingconventie. Dit vervangt het "SPY koopt nooit bij" uit
    beslissing 15; de rest daarvan blijft: SPY wisselt niet mee en betaalt dus
    nooit mee aan de rotatie.
23. **De wisselkoers van een uitvoeringsdag is de laatste afgesloten
    1-minuutbalk van `EURUSD=X` die eindigt op of vóór 16:00:00 in New York**
    (normaal 15:59-16:00), met als terugval hoogstens vijf minuten eerder, nooit
    een balk daarna, en anders stoppen. De ECB-referentiekoers van die dag gaat
    mee als onafhankelijk controlegetal; meer dan 1 % verschil stopt de
    handeling. Dit vervangt de dagbalk uit beslissing 3 voor uitvoeringsdagen -
    de dagelijkse grafiekreeks blijft wel de dagbalk. `fx_asof` blijft het
    moment van LEZEN (beslissing 11); het moment waar de koers bij hoort staat
    nu apart in `fx_bar_end`. De uitvoering van 6 oktober 2026 blijft exact zoals
    ze is.
24. **De kosten krijgen twee curves.** De officiële curve houdt de eenzijdige
    omzet van de bevroren simulatie en wordt nooit herrekend. Daarnaast staat een
    realistische papieren curve die 0,15 % rekent over de werkelijk verhandelde
    notional: de som van de absolute bedragen van alle echte orders. Dus géén
    `omzet_factor = 2` - dat klopt bij een volledige wissel en is fout zodra er
    posities blijven staan of alleen contant geld belegd wordt. De papieren curve
    staat in `sw/realistisch.py`, heeft geen enkele schrijfweg, en wordt elke
    keer opnieuw uit de officiële records gerekend.

## Wat bewust open blijft

**Belgische beurstaks.** Ordegrootte 0,35 % per richting kan bij maandelijkse
rotatie het verschil maken tussen winst en verlies. Zit nu in geen van beide
curves. Hoort bij de realistische tweede curve; nog niet toegevoegd.

**Dividendbelasting is GEEN open punt meer.** De conventie is bruto (zie
beslissing 20 hierboven). Het veld `net_per_share_usd` blijft in de tabel staan
als informatie, maar het wordt nergens gebruikt om te rekenen. Zou er ooit een
nettocurve komen, dan is dat een nieuwe reeks naast de officiële - nooit een
wijziging van deze.

**Wie het dividend binnenbrengt.** Yahoo kent de ex-datum en het bedrag, maar
niet de betaaldatum. Die zoekt Bart op (investor relations van het bedrijf, of
nasdaq.com) en vult hij in met `scripts/leg_dividend_vast.py --betaald=... --bron=...`.
Gebeurt dat niet, dan **stopt de eerstvolgende wissel**: `leg_herbalans_vast.py`
vergelijkt onze tabel met wat Yahoo kent en weigert te rekenen met een uitkering
die hij mist. Eerste dividend van MPC en VLO rond november 2026, HPE en SPY rond
december.

**Privé-apps op Streamlit Community Cloud** blijken op het gratis plan niet te
bestaan: het heet er letterlijk "deploy a public app", afschermen zit bij de
betaalde Snowflake-variant. Zie het open punt hieronder.

**Python-versies.** Lokaal draait 3.14.3 (de `.venv`, zie boven), het dashboard
en de GitHub-workflows draaien op 3.12. De gepinde versies installeren en slagen
op allebei; getest door de workflow op 6 oktober 2026. De 195 tests draaien ook
groen op de losse Python 3.14.4 die standaard in de terminal staat.

**De wisselkoers in de grafiek is niet die van het record.** Het record van een
uitvoering draagt zijn eigen minuutbalk van 16:00 in New York; de grafiek rekent
met de dagreeks uit `fx_snapshots`, die de dagelijkse taak 's avonds wegschrijft.
Op een uitvoeringsdag kunnen die een fractie van een procent verschillen. Het
record is het bewijs, de grafiek is weergave. Bewust zo gelaten; voorgelegd aan
de controleur in ronde 4.

## Hoe het in elkaar zit

```
de kluis              de scanner            de etalage
Supabase       <--    lokaal bij Bart  -->  Streamlit online
alleen bijschrijven   doet de maandscan     leest alleen
```

- `sw/` is de rekenkern zonder schermcode: `strategy.py` (bevroren formule),
  `ledger.py` (lezen, controleren, bijschrijven — met opzet geen enkele functie
  die iets wist), `portfolio.py` (de instap), `herbalans.py` (elke wissel
  daarna, plus de keten van uitvoeringen), `prices.py`, `supabase_io.py`, en
  sinds 7 oktober 2026 `beurskalender.py`: alle klokregels op één plek, zonder
  internet, met een `nu` die je in een test kunt meegeven.
- Daar kwamen na auditronde 3 drie bestanden bij, elk met één onderwerp:
  `dividend.py` (bruto, ex-datum voor het recht, betaaldatum voor het geld, en
  de herbelegging van SPY), `fx.py` (de minuutbalk van de slotbel plus het
  ECB-controlegetal; de keuze zelf is te testen zonder internet) en
  `realistisch.py` (de tweede curve, zonder enige schrijfweg).
- `streamlit_app.py` is het dashboard. Het leest alleen, en het toont altijd de
  laatste uitvoering uit de keten — niet de uitvoering van het laatste signaal.
  Tussen een nieuw signaal en de wissel de avond erna blijft de oude
  portefeuille immers gewoon de portefeuille.
- `sql/01_schema.sql` tot en met `sql/04_dividend_en_fx.sql` zijn alle vier
  idempotent; opnieuw draaien is veilig en verandert geen bestaande rij.
  **De volgorde telt**: 03 vervangt twee functies uit 02 door een strengere
  versie, en 04 vervangt `hardening_status()` uit 03. Draai je een eerder
  bestand opnieuw, draai dan daarna ook de latere. Dat valt meteen op:
  `hardening_status()` geeft dan geen `deur_versie` 4 meer terug en
  `scripts/controleer_slot.py` slaat alarm. 04 zet met opzet een APARTE trigger
  op `executions` in plaats van die van 03 te vervangen, zodat de valkuil van
  de volgorde niet dieper wordt.
- `scripts/leg_instap_vast.py` is de eerste keer, `scripts/leg_herbalans_vast.py`
  elke keer daarna (`LEG WISSEL VAST (na 22u20).bat`). Allebei lokaal, nooit
  vanuit GitHub.
- `scripts/leg_dividend_vast.py` legt een uitkering vast: het bedrag en de
  ex-datum komen van Yahoo en worden nagerekend, de betaaldatum vult Bart in met
  de bron erbij. Eerst in `forward_log/dividends.jsonl`, dan in de database.
  `--toon` laat zien wat Yahoo kent en wij missen. Dat moet gebeuren vóór de
  eerstvolgende wissel: die weigert te rekenen met een dividend dat Yahoo wel
  kent en onze tabel niet.
- `scripts/herstel_dagkoers.py` is de enige manier om een gemiste dag bij te
  schrijven: met de geheime sleutel, met een reden, met een bevestiging, en met
  een regel in het beheerslogboek. Een wisselkoers van een oude dag haalt het
  niet bij Yahoo maar vraagt hij aan jou, met bron.
- `scripts/controleer_slot.py` valt de database aan met de geheime sleutel erbij.
  Draai dat na elke wijziging aan het schema. Stand 7 oktober 2026, nadat
  `sql/03_smalle_deur.sql` erin stond: 55 van 55 goed tegen de echte database,
  met `deur_versie 3`. (Met alleen 01 en 02 waren het 42 controles; de
  13 nieuwe horen bij de smalle deur.) De volledige uitvoer van beide rondes
  staat in `audit/aanvalstest_2026-10-07.txt` en
  `audit/aanvalstest_2026-10-07_ronde3.txt`. Sinds
  `sql/04_dividend_en_fx.sql` op 7 oktober 2026 in Supabase staat, zijn het er
  59 van 59 goed met `deur_versie 4`; die uitvoer staat in
  `audit/aanvalstest_2026-10-07_ronde4.txt`. De vier nieuwe controles gaan over
  de verplichte betaaldatum van een dividend en over het wisselkoersbewijs.
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
secrets staan in GitHub en `scripts/controleer_slot.py` gaf toen 42 van 42 goed
tegen de echte database (na de smalle deur van auditronde 2 zijn het er 55).
De harde grens eromheen, letterlijk van Bart: wijzig nooit het bestaande
ledger-record, de bestaande
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

## Auditronde 2, uitgevoerd op 7 oktober 2026

ChatGPT keek de hardening na en vond zes punten. Alle zes afgehandeld; twee
ervan eindigen bewust in een beslissing voor Bart in plaats van in code.

1. **De €1.000 is één doorlopende portefeuille geworden.** Dat was de ernstige:
   `bereken_instap()` begon elke keer opnieuw met €1.000, en vanaf signaal 2
   zou dat elke maand vers geld in de reeks gestopt hebben. Ontwerp eerst
   opgeschreven (`audit/ONTWERP_doorlopende_portefeuille_2026-10-07.md`), daarna
   gebouwd in `sw/herbalans.py` met 30 tests.
2. **De automatische deur is veel smaller** (`sql/03_smalle_deur.sql`): alleen
   de afgesloten beursdag van nu, alleen de huidige posities plus SPY,
   compleet of niets, en de wisselkoers verplicht zolang die bij die dag hoort.
3. **De dagtaak faalt nu waar ze vroeger iets oversloeg**: een ontbrekende
   koers of een ontbrekende wisselkoers binnen het venster maakt de taak rood.
4. **Het dashboard zei dat dividend nergens meetelde.** Dat klopte toen; sinds
   de beslissing van bruto (hieronder) telt het wel mee en zegt het scherm dat.
5. **De wisselkoersregel voor volgende wissels was een voorstel**
   (`audit/VOORSTEL_FX_2026-10-07.md`). Dat voorstel is intussen goedgekeurd en
   uitgevoerd; zie hieronder. De regel die er nu staat wijkt op één punt af van
   het voorstel: `fx_asof` blijft het moment van lezen, en het moment van de
   balk staat apart in `fx_bar_end`.
6. **`hardening_status()` kijkt nu ook of de wachters aanstaan** (`tgenabled`),
   en zegt er eerlijk bij wat een databasebeheerder alsnog kan. Zie beslissing
   19 hierboven.

Onderweg gevonden en meteen hersteld, los van de audit: de grafiek op het
dashboard crashte zodra er een tweede dag bij kwam (`'datum' is both an index
level and a column label`). Dat zou dus op 8 oktober 2026 zichtbaar geworden
zijn. Gevonden door het dashboard met een nagebootste tweede wissel te draaien
en er zelf naar te kijken.

## De vier beslissingen van 7 oktober 2026

Na ronde 3 heeft Bart vier punten beslist die tot dan toe openstonden. Alle vier
gebouwd en getest; de redenering staat per punt in
`audit/ONTWERP_dividend_fx_kosten_2026-10-07.md`, de vraag aan de volgende
controleur in `audit/VRAAG_2026-10-07_ronde4.md`. In het kort:

1. **Dividend is bruto**, aan beide kanten, zonder keuze bij een wissel
   (`sw/dividend.py`). De ex-datum bepaalt wie recht heeft, de betaaldatum
   wanneer het geld er is. `sql/04_dividend_en_fx.sql` maakt de betaaldatum
   verplicht in de database; `scripts/leg_dividend_vast.py` brengt een uitkering
   binnen, met de betaaldatum uit een bron die een mens opzoekt.
2. **SPY herbelegt zijn dividend** op de betaaldag, tegen de eerstvolgende
   slotkoers, zonder kost. Het aantal SPY-aandelen groeit daardoor. Een
   uitkering zit in de aandelen óf contant, nooit in beide: `bereken_herbalans()`
   rekent dat bij elke wissel na.
3. **De wisselkoers van een uitvoeringsdag is de minuutbalk van de slotbel**
   (`sw/fx.py`), met de ECB-referentiekoers als controlegetal en een grens van
   1 procent. Omdat die balk niet meer verandert, is het leesvenster nu zo ruim
   als de database toelaat: tot acht uur na de slotbel. Dat lost meteen op
   waardoor de dagtaak van 7 oktober rood werd (GitHub startte pas om 00:57 UTC).
4. **Er zijn twee curves**: de officiële blijft eenzijdig en wordt nooit
   herrekend, de realistische (`sw/realistisch.py`) rekent over de werkelijk
   verhandelde bedragen. Op het dashboard staan ze onder elkaar, met de
   officiële als doorlopende lijn.

De grens eromheen is gehaald: `app.py`, `forward_log/`, `bewijs/` en
`sw/strategy.py` zijn niet aangeraakt, en de drie hashes van het signaal, de
strategie en de instap zijn ongewijzigd. `bereken_instap()` geeft zonder
wisselkoersbewijs nog exact dezelfde canonieke tekst als voorheen - nagerekend
tegen de vorige commit en vastgezet in `tests/test_portefeuille.py`. Het
`opening`-blok van een WISSEL heeft wel vijf beschrijvende velden erbij; dat mag,
want er is nog geen wissel vastgelegd, en de bedragen erin zijn identiek.

Zelf nagekeken, los van de opdracht: het dashboard is met een nagebootste tweede
wissel plus twee dividenden gedraaid en met de ogen van een lezer bekeken. Daar
kwamen twee dingen uit die meteen hersteld zijn — de tekst onder de bedragen
noemde alleen het contante dividend (waardoor het leek alsof SPY niets kreeg, en
niet dat het herbelegd was), en de officiële lijn stond gestippeld terwijl de
tweede berekening doorlopend was.

## Wat nu open staat

1. **Auditronde 4 ligt klaar.** De vraag staat in
   `audit/VRAAG_2026-10-07_ronde4.md` en gaat over de vier beslissingen van
   7 oktober 2026 (dividend bruto, SPY herbelegt, de minuutbalk, twee curves).
   Ze zegt er expliciet bij wat NIET meer gevraagd hoeft te worden, zodat de
   controleur geen beslissing opnieuw ter discussie stelt. Ronde 3 (commit
   `ee05594`, `audit/VRAAG_2026-10-07_ronde3.md`) staat nog uit; komt daar
   antwoord op, behandel het dan als ronde 1 en 2: eerst narekenen of de
   bevinding klopt, dan pas bouwen, en nooit het bestaande bewijs aanraken.

2. **De dagtaak van de eerstvolgende beursdag nakijken.** De eerste geplande
   ronde heeft gedraaid in de nacht van 6 op 7 oktober 2026 en is rood
   geworden, om twee redenen die allebei verholpen zijn:

   - GitHub startte de taak van 21:30 UTC pas om 00:57 UTC. Toen was het
     venster voor de wisselkoers (tot middernacht in Londen) dicht. De taak
     draait nu drie keer per avond (20:25, 21:25 en 22:25 UTC), en een ronde
     die alles al vastgelegd aantreft wordt niet meer rood.
   - Yahoo leverde in dat ene verzoek geen koers voor MRNA. Een ontbrekend
     aandeel wordt nu nog een keer apart gevraagd voor de taak faalt.

   Er is niets verkeerds vastgelegd: de koersen van 6 oktober stonden er al
   via de instap, en de dubbele poging schreef niets nieuws. Kijk bij Actions
   of de eerstvolgende beursdag groen is en of er een wisselkoers bij staat.

3. **Wie het dashboard mag zien.** Op het gratis plan van Streamlit heet het
   "deploy a public app": iedereen met de link kan kijken. Nog na te gaan of er
   in de app-instellingen onder Sharing alsnog een beperking tot genodigden
   mogelijk is. Zo niet, dan is dat een bewuste aanvaarding: lezen kan iedereen,
   wijzigen niemand. Het e-mailadres van Barts broer is nog niet doorgegeven.

Wat je er níet mee moet doen: de bevroren curve herrekenen met andere kosten,
de officiële curve vervangen door de realistische, de scan in de webapp zetten,
de beurstaks er zelf bij rekenen, een betaaldatum van een dividend verzinnen in
plaats van opzoeken, of een vastgelegde uitvoering aanraken.
