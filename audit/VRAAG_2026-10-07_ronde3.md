# Vraag aan de controleur — ronde 3, 7 oktober 2026

Dit pakket is de volledige broncode van StockWaakhond V7.1. Het bevat geen
sleutels en geen wachtwoorden: alleen wat in de openbare GitHub-map staat
(`Adminbart76/stockwaakhond`). Het commitnummer en de datum staan in
`audit/PAKKET.txt`.

Ronde 1 (6 oktober) gaf zeven hardeningpunten; die zijn gebouwd en in ronde 2
nagekeken. Ronde 2 (7 oktober) gaf zes nieuwe punten. **Deze vraag gaat over
die zes: klopt wat er nu staat, en is het ook werkelijk waterdicht?**

Zeg het hard als iets zwakker is dan hieronder beweerd wordt. Een punt dat je
niet kunt controleren met wat er in dit pakket zit, hoor je ook te noemen.
Hieronder staan de plekken waar ik zelf het eerst zou aanvallen; dat is geen
uitnodiging om daar te stoppen.

---

## 1. De grens die niet overschreden mocht worden

Nog steeds dezelfde, en nog steeds het eerste wat je zou moeten nakijken:

| wat | hoort te zijn |
|---|---|
| `strategy_hash` in `forward_log/ledger.jsonl` | `a399aecc207510c77450cd015f4f23e2b3639fc642eb9bcc29e95cbe2b84cc18` |
| `entry_hash` van het enige signaal | `0426e47ccd6e0b4f7fcecd772ce21dc5778db862e359f5eb4d239f5ce8bd5d15` |
| `exec_hash` in `forward_log/executions.jsonl` | `3468930ea4971945c8e8dad57b2cc797f9c825508368eff6bef5038090d3dae7` |
| `app.py` | byte-identiek aan `bewijs/app.py.bevroren-2026-10-06` |
| `forward_log/ledger.jsonl` | byte-identiek aan `bewijs/ledger.jsonl` |

`sw/portfolio.py` is in deze ronde wél gewijzigd: `waardeer()` telt nu contant
geld mee (`cash_usd`, ook in het benchmarkblok). Controleer dat die wijziging
niets verandert aan een record dat dat veld niet heeft — de bestaande instap
heeft het niet.

## 2. Wat er per punt gebouwd is, en wat je zou kunnen aanvallen

### Punt 1 — één doorlopende portefeuille (het zwaarste punt)

`sw/herbalans.py`, ontworpen in
`audit/ONTWERP_doorlopende_portefeuille_2026-10-07.md`, getest in
`tests/test_herbalans.py` (30 tests).

De regel: er wordt één keer €1.000 ingelegd. Bij een nieuw signaal wordt de dan
geldende waarde (posities tegen de slotkoers van de uitvoeringsdag, plus
contant geld) herverdeeld over de nieuwe Top-5. De omzet is letterlijk de
formule van de bevroren `simulate_forward()` in `app.py`:
`0,5 × (som van de gewichtsverschillen + contant)`, maal 0,15 %. Elke
uitvoering hangt met `prev_exec_hash` aan de vorige.

*Te onderzoeken:*

- Klopt de bewering dat de instap van 6 oktober uit deze formule ongewijzigd
  terugkomt? (lege portefeuille, alles contant → omzet 1,0 → €1,50 op €1.000)
- Is er een pad waarbij er tóch geld bijkomt of verdwijnt? Let op de
  afrondingen: bedragen op 8 decimalen, aantallen op 10. Bij welke
  portefeuillewaarde begint dat te schuiven, en in welke richting?
- `bouw_verloop_keten()` laat het nieuwe mandje gelden vanaf de wisseldag zelf.
  Is dat juist, gegeven dat er tegen de slotkoers van die dag gewisseld wordt?
  Kan er een dag dubbel of helemaal niet geteld worden?
- Contant geld zit op twee plaatsen: `cash_usd` in het record (het moment van
  dat record) en de dividendreeks (alles daarna). Is dubbeltellen uitgesloten?
- De kost wordt in dollar gerekend over de waarde in dollar. Een percentage is
  schaalvrij, dus dat zou niet mogen uitmaken — klopt dat hier ook werkelijk?
- `sql/03_smalle_deur.sql` rekent in de database na dat
  `opening.total_usd − cost_usd = invested_usd`, met een marge van 0,01. Die
  marge is absoluut, niet relatief. Waar gaat dat mis?

### Punt 2 — de smalle schrijfdeur

`sql/03_smalle_deur.sql`, functie `leg_dagkoersen_vast()`. De volgorde van de
controles is bewust: schrijfteken → de dag is vandaag in New York → geen
weekend → na de slotbel plus 20 minuten → geen vreemd aandeel → de dag is
compleet → pas dan schrijven.

*Te onderzoeken:*

- Is die volgorde werkelijk veilig? Een aanval die een regel test moet op die
  regel stranden, niet op een eerdere - anders bewijst een geslaagde test niets.
- `actieve_tickers()` neemt de punt van de ketting: de uitvoering waar niets
  naar verwijst, `order by execution_date desc limit 1`. Kunnen er ooit twee
  punten zijn? De unieke index `executions_een_opvolger` verbiedt twee
  opvolgers, maar twee *beginnen* (beide zonder `prev_exec_hash`) worden alleen
  door de trigger geweigerd. Is dat genoeg?
- De terugval "nog geen uitvoering → het laatste signaal plus SPY" is een
  bredere deur. Kan iemand die toestand kunstmatig bereiken?
- De wisselkoers is verplicht zolang het venster open staat (tot middernacht in
  Londen) en daarna juist verboden. Is er een moment waarop die twee regels
  elkaar tegenspreken, of een tijdzonegeval (zomertijd die in Londen en New
  York op een andere dag omslaat) waarin het misloopt?
- De band 0,5–2,0 dollar voor een euro: te ruim, te smal, of op de verkeerde
  plek?

### Punt 3 — een dag is compleet of hij bestaat niet

`scripts/dagelijkse_snapshot.py`. Ontbreekt één koers van een actieve positie
of van SPY, dan wordt er niets vastgelegd en faalt de taak. Ontbreekt de
wisselkoers terwijl hij bij die dag hoort, idem.

Dit is op 7 oktober meteen gebeurd: Yahoo liet MRNA weg uit een verzoek om zes
tickers tegelijk. Daarom wordt wie ontbreekt nu nog één keer apart gevraagd.

*Te onderzoeken:*

- Is "liever niets dan een halve dag" hier de juiste afweging? Een ontbrekende
  dag moet met de hand hersteld worden (`scripts/herstel_dagkoers.py`), een
  halve dag kon later aangevuld worden. Welke van de twee is erger?
- De taak draait nu drie keer per avond. Kan een latere ronde iets stuk maken
  wat een eerdere goed deed?
- Is er nog een echte fout die als "niets te doen" (exitcode 0) wegvalt?

### Punt 4 — dividend

De rekenkern kan het voor beide kanten, maar er is bewust niets aangesloten
zolang de fiscale conventie niet vastligt. Het dashboard zegt nu expliciet dat
dit alleen de koersen zijn. `bereken_herbalans()` weigert dividendgeld zonder
conventie, en `scripts/leg_herbalans_vast.py` stopt als er in de periode een
ex-dividenddatum valt zonder dat `--dividend=bruto|netto` meegegeven is.

*Te onderzoeken:*

- Is er nog een plek waar een bedrag getoond wordt dat zonder dividend
  misleidend is zonder dat de lezer het ziet?
- Aan onze kant wordt dividendgeld bij de volgende wissel meebelegd; SPY houdt
  het contant. Dat is een klein systematisch voordeel voor de strategie. Het
  voorstel is SPY te laten herbeleggen tegen de slotkoers van de ex-datum,
  zonder kost. Is dat de juiste conventie, of is er een betere?

### Punt 5 — de wisselkoers bij toekomstige wissels

**Bewust niet geïmplementeerd.** Het voorstel staat in
`audit/VOORSTEL_FX_2026-10-07.md`: de 1-minuutbalk van `EURUSD=X` van 16:00 in
New York, met de ECB-referentiekoers van die dag als onafhankelijk
controlegetal en een afwijkingsgrens van 1 %.

*Te onderzoeken:* is dat werkelijk deterministisch? Hoe lang blijft die balk bij
Yahoo opvraagbaar, en wat betekent het voor een controleur over een jaar? Is er
een bron die én gratis, én permanent, én bij de slotbel hoort?

### Punt 6 — hardening_status

Kijkt nu ook naar `tgenabled`, en meldt eerlijk dat een eigenaar met
DDL-rechten triggers en functies kan wijzigen — ook deze functie zelf.

*Te onderzoeken:* is die eerlijkheid volledig? Welke andere bewering van deze
database over zichzelf is niet te vertrouwen, en welk spoor buiten de database
dekt dat af?

## 3. Wat je niet uit dit pakket kunt halen

De database zelf zit hier niet in. Wat erover te zeggen valt:

- `sql/01_schema.sql`, `02_hardening.sql` en `03_smalle_deur.sql` zijn alle drie
  uitgevoerd in Supabase. `hardening_status()` geeft `deur_versie 3`, zeven
  sloten, en alle wachters aan (`tgenabled`).
- `scripts/controleer_slot.py` valt daarna de echte database aan, met de geheime
  sleutel erbij. Uitslag: **55 van 55 geweigerd**. De volledige uitvoer staat in
  `audit/aanvalstest_2026-10-07_ronde3.txt` (die van ronde 2, met 42 controles,
  staat ernaast).
- Twee regels zijn bewust niet echt beproefd maar zonder te schrijven bevraagd
  via `mag_dagkoers_vastleggen()`: "de dag moet compleet zijn" en "dit is geen
  koers". Die regels worden pas bereikt als al het andere klopt; een poging die
  door een gat heen zou glippen, zou een dag met verzonnen cijfers achterlaten
  die niet meer weg te halen is.

*Te onderzoeken:* is dat een aanvaardbare reden om een regel niet echt te
beproeven, of is er een opzet waarin het wél veilig kan? En: welke aanval
ontbreekt er nog in die 55?

## 4. Hoe je het kunt narekenen

```
python -m pip install -r requirements.txt
python -m pytest          # 131 wachters, horen allemaal te slagen
```

De belangrijkste bestanden voor deze ronde:

| | |
|---|---|
| `sw/herbalans.py` | de doorlopende portefeuille en de keten van uitvoeringen |
| `tests/test_herbalans.py` | 30 tests, waaronder "er wordt niet opnieuw met €1.000 begonnen" |
| `sql/03_smalle_deur.sql` | de smalle deur, de ketenregels, de statuscontrole |
| `scripts/dagelijkse_snapshot.py` | compleet of niets |
| `scripts/leg_herbalans_vast.py` | de wissel vastleggen (lokaal, nooit vanuit GitHub) |
| `scripts/herstel_dagkoers.py` | de aparte beheershandeling voor een gemiste dag |
| `scripts/controleer_slot.py` | de aanvalstest |
| `audit/ONTWERP_doorlopende_portefeuille_2026-10-07.md` | de rebalanceregels in gewone taal |
| `audit/VOORSTEL_FX_2026-10-07.md` | het FX-voorstel, nog niet gebouwd |

`CLAUDE.md` bevat de volledige stand van zaken, de beslissingen met hun reden,
en wat er bewust open blijft. Vier dingen staan daar als nog te beslissen:
de dividendconventie, het herbeleggen van SPY-dividend, de wisselkoersregel, en
de kostenconventie bij een volledige wissel. Een aanbeveling daarover is
welkom, maar beslis ze niet namens ons.
