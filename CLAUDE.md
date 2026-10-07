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
| Tests | 130, groen op 7 oktober 2026 (`python -m pytest`) |

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
18. **Het dashboard zegt wat er níet in zit.** Zolang dividend nergens is
    aangesloten, staat er bij de bedragen dat dit alleen de koersen zijn.
    "Beide kanten missen evenveel" is waar, maar wie dat niet weet, leest de
    cijfers als het volledige rendement.
19. **De database is nooit het enige controlespoor.** Wie eigenaar is van de
    database kan triggers en functies wijzigen, uitzetten of weghalen - ook de
    functie die vertelt dat ze aanstaan. Daarom blijft het spoor erbuiten
    nodig: de openbare Git-geschiedenis, de hash-keten in `forward_log/` en de
    bestanden in `bewijs/`. Wijkt de database daarvan af, dan is de database
    fout. Dat staat zo in `sql/03_smalle_deur.sql` en in de uitvoer van
    `scripts/controleer_slot.py`.

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

**Dividendbelasting — beslissen vóór het eerste dividend binnenkomt.**
De tabel `dividends` heeft een veld voor netto, maar de percentages zijn nog
niet vastgelegd. Eerste dividend van MPC en VLO wordt rond november 2026
verwacht, HPE en SPY rond december.

Dit is sinds 7 oktober 2026 een harde blokkade en geen detail meer: valt er
tussen twee wissels een ex-dividenddatum, dan **stopt**
`scripts/leg_herbalans_vast.py` tot de conventie gekozen is (draaien met
`--dividend=bruto` of `--dividend=netto`). Stil nul euro meerekenen zou een
wissel met een verkeerd bedrag voor altijd vastleggen. Te kiezen: bruto of
netto, en bij netto welke percentages (Amerikaanse bronheffing plus Belgische
roerende voorheffing).

**Herbelegt SPY zijn dividend?** Aan de kant van StockWaakhond wordt contant
dividend bij de volgende wissel meebelegd - dat volgt uit de doorlopende
portefeuille. SPY koopt niets bij en houdt het dus contant. Dat is een klein
maar systematisch verschil in het voordeel van StockWaakhond. Voorstel: SPY zijn
dividend laten herbeleggen tegen de slotkoers van de ex-datum, zonder kost,
zodat beide kanten hun uitkeringen op dezelfde manier laten doorwerken. Nog niet
beslist, en nog nergens aangesloten, dus het speelt pas bij het eerste dividend.

**De wisselkoers bij een volgende wissel.** Het huidige getal hangt af van het
moment waarop Bart binnen het avondvenster op het BAT-bestand klikt: binnen dat
venster beweegt de dagbalk van `EURUSD=X` gewoon mee. Voor signaal 2 hoort daar
een regel te staan waarbij twee mensen dezelfde avond hetzelfde getal krijgen.
Het voorstel staat in `audit/VOORSTEL_FX_2026-10-07.md` (de 1-minuutbalk van
16:00 in New York, met de ECB-koers als onafhankelijk controlegetal). **Er is
niets van geïmplementeerd**: dit wacht op een expliciet ja. De uitvoering van
6 oktober 2026 blijft hoe dan ook zoals ze is.

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
  die iets wist), `portfolio.py` (de instap), `herbalans.py` (elke wissel
  daarna, plus de keten van uitvoeringen), `prices.py`, `supabase_io.py`, en
  sinds 7 oktober 2026 `beurskalender.py`: alle klokregels op één plek, zonder
  internet, met een `nu` die je in een test kunt meegeven.
- `streamlit_app.py` is het dashboard. Het leest alleen, en het toont altijd de
  laatste uitvoering uit de keten — niet de uitvoering van het laatste signaal.
  Tussen een nieuw signaal en de wissel de avond erna blijft de oude
  portefeuille immers gewoon de portefeuille.
- `sql/01_schema.sql`, `sql/02_hardening.sql` en `sql/03_smalle_deur.sql` zijn
  alle drie idempotent; opnieuw draaien is veilig en verandert geen bestaande
  rij. **De volgorde telt**: 03 vervangt twee functies uit 02 door een
  strengere versie. Draai je 02 opnieuw, draai dan daarna ook 03. Dat valt
  meteen op: `hardening_status()` geeft dan geen `deur_versie` 3 meer terug en
  `scripts/controleer_slot.py` slaat alarm.
- `scripts/leg_instap_vast.py` is de eerste keer, `scripts/leg_herbalans_vast.py`
  elke keer daarna (`LEG WISSEL VAST (na 22u20).bat`). Allebei lokaal, nooit
  vanuit GitHub.
- `scripts/herstel_dagkoers.py` is de enige manier om een gemiste dag bij te
  schrijven: met de geheime sleutel, met een reden, met een bevestiging, en met
  een regel in het beheerslogboek. Een wisselkoers van een oude dag haalt het
  niet bij Yahoo maar vraagt hij aan jou, met bron.
- `scripts/controleer_slot.py` valt de database aan met de geheime sleutel erbij.
  Draai dat na elke wijziging aan het schema. Stand 7 oktober 2026, nadat
  `sql/03_smalle_deur.sql` erin stond: 55 van 55 goed tegen de echte database,
  met `deur_versie 3`. (Met alleen 01 en 02 waren het 42 controles; de
  13 nieuwe horen bij de smalle deur.)
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
4. **Het dashboard zegt dat dividend nergens meeteelt.** De rekenkern kan het
   wel, maar de fiscale conventie ligt niet vast; zie het open punt hierboven.
5. **De wisselkoersregel voor volgende wissels is een voorstel gebleven**
   (`audit/VOORSTEL_FX_2026-10-07.md`). Niets geïmplementeerd zonder akkoord.
6. **`hardening_status()` kijkt nu ook of de wachters aanstaan** (`tgenabled`),
   en zegt er eerlijk bij wat een databasebeheerder alsnog kan. Zie beslissing
   19 hierboven.

Onderweg gevonden en meteen hersteld, los van de audit: de grafiek op het
dashboard crashte zodra er een tweede dag bij kwam (`'datum' is both an index
level and a column label`). Dat zou dus op 8 oktober 2026 zichtbaar geworden
zijn. Gevonden door het dashboard met een nagebootste tweede wissel te draaien
en er zelf naar te kijken.

## Wat nu open staat

1. **De dagtaak van de eerstvolgende beursdag nakijken.** De eerste geplande
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

2. **Wie het dashboard mag zien.** Op het gratis plan van Streamlit heet het
   "deploy a public app": iedereen met de link kan kijken. Nog na te gaan of er
   in de app-instellingen onder Sharing alsnog een beperking tot genodigden
   mogelijk is. Zo niet, dan is dat een bewuste aanvaarding: lezen kan iedereen,
   wijzigen niemand. Het e-mailadres van Barts broer is nog niet doorgegeven.

Wat je er níet mee moet doen: de bevroren curve herrekenen met andere kosten,
de scan in de webapp zetten, het openstaande kostenpunt zelf beslissen, zelf een
dividendpercentage invullen, of de nieuwe wisselkoersregel invoeren zonder dat
Bart er ja op gezegd heeft.
