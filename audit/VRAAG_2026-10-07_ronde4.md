# Vraag aan de controleur — ronde 4, 7 oktober 2026

Dit pakket is de volledige broncode van StockWaakhond V7.1. Het bevat geen
sleutels en geen wachtwoorden: alleen wat in de openbare GitHub-map staat
(`Adminbart76/stockwaakhond`). Het commitnummer en de datum staan in
`audit/PAKKET.txt`.

Ronde 1 gaf zeven hardeningpunten, ronde 2 gaf er zes, en ronde 3 keek die na.
**Deze ronde gaat over vier beslissingen die Bart daarna genomen heeft en die nu
gebouwd zijn.** Ze stonden in eerdere rondes nog als open punt; dat zijn ze niet
meer.

## Wat je NIET meer hoeft te vragen

Deze vier zijn beslist. Of de uitvoering klopt, is de vraag; of de keuze juist
is, niet.

| beslist | wat het is |
|---|---|
| dividendconventie | **bruto**, aan beide kanten, zonder keuze bij een wissel |
| SPY-dividend | bruto, beschikbaar op de betaaldatum, herbelegd in SPY |
| wisselkoers | de afgesloten 1-minuutbalk die eindigt op of vóór 16:00 New York, met de ECB-koers als controlegetal |
| kosten | de officiële curve blijft eenzijdig; er komt een tweede, realistische curve naast |

Het volledige ontwerp met de redenering staat in
`audit/ONTWERP_dividend_fx_kosten_2026-10-07.md`. De eerdere vragen staan in
`audit/VRAAG_2026-10-07.md` (ronde 1 en 2) en
`audit/VRAAG_2026-10-07_ronde3.md`; die zijn niet gewijzigd.

Zeg het hard als iets zwakker is dan hieronder beweerd wordt. Een punt dat je
niet kunt controleren met wat er in dit pakket zit, hoor je ook te noemen.
Hieronder staan de plekken waar ik zelf het eerst zou aanvallen; dat is geen
uitnodiging om daar te stoppen.

---

## 1. De grens die niet overschreden mocht worden

Nog steeds het eerste wat je zou moeten nakijken:

| wat | hoort te zijn |
|---|---|
| `strategy_hash` in `forward_log/ledger.jsonl` | `a399aecc207510c77450cd015f4f23e2b3639fc642eb9bcc29e95cbe2b84cc18` |
| `entry_hash` van het enige signaal | `0426e47ccd6e0b4f7fcecd772ce21dc5778db862e359f5eb4d239f5ce8bd5d15` |
| `exec_hash` in `forward_log/executions.jsonl` | `3468930ea4971945c8e8dad57b2cc797f9c825508368eff6bef5038090d3dae7` |
| `app.py` | byte-identiek aan `bewijs/app.py.bevroren-2026-10-06` |
| `forward_log/ledger.jsonl` | byte-identiek aan `bewijs/ledger.jsonl` |

In deze ronde zijn `sw/portfolio.py` en `sw/herbalans.py` wél gewijzigd. Beide
kregen een optionele parameter `fx_bewijs` die velden aan de gehashte tekst
toevoegt. Wat dat betekent voor de twee soorten records, zo precies mogelijk:

- **`bereken_instap()` geeft zonder die parameter exact dezelfde canonieke tekst
  en dezelfde hash als voorheen.** Nagerekend tegen de vorige commit; vastgezet
  in `tests/test_portefeuille.py` (de toegestane veldenlijst staat er letterlijk
  in). Dat moest, want de instap van 6 oktober 2026 is vastgelegd voordat deze
  regel bestond.
- **`bereken_herbalans()` geeft een ANDERE hash dan voorheen**, ook zonder
  dividend. Het `opening`-blok heeft vijf beschrijvende velden erbij
  (`benchmark_shares`, `dividend_detail`, `benchmark_dividend_detail`,
  `benchmark_dividend_betaald_usd`, `benchmark_dividend_herbelegd_usd`). De
  bedragen, de posities en het benchmarkblok zijn identiek — nagerekend tegen de
  vorige commit. Dat mag, want er is nog geen enkele wissel vastgelegd. Zodra er
  één is, mag dit niet meer gebeuren.

`pf.dividend_reeks()` is verdwenen (vervangen door `sw/dividend.py`); ga na dat
die functie nergens meer in een rekenpad zit. De reden staat in het ontwerp: ze
stond op de ex-datum en kon netto rekenen, en allebei is nu fout.

## 2. Dividend: ex-datum voor het recht, betaaldatum voor het geld

`sw/dividend.py`, getest in `tests/test_dividend.py` (18 tests).

De regel: het recht wordt bepaald met het aantal aandelen dat we hadden vóór de
ex-dag (dus de laatste uitvoering met een datum strikt vóór die dag); het geld
telt pas mee vanaf de betaaldag. Bruto, aan beide kanten.

*Te onderzoeken:*

- Klopt de behandeling van een ex-dag die samenvalt met een uitvoeringsdag? De
  code zegt: het oude mandje had recht, het nieuwe niet. Is dat juist, gegeven
  dat er tegen de slotkoers van die dag gewisseld wordt?
- `betaald_tussen()` is exclusief aan de linkerkant en inclusief aan de rechter.
  Kan een uitkering daardoor tussen twee wissels verdwijnen of twee keer
  meetellen? Let op het geval betaaldag = vorige uitvoeringsdag.
- Het eerste record van een keten: een ex-datum op of vóór de instapdag geeft
  geen recht. Klopt dat voor onze vijf aandelen én voor SPY?
- Een dividendrij zonder betaaldatum wordt geweigerd — in Python én in de
  database (`sql/04`). Is er een pad waarlangs er tóch zonder gerekend wordt?

## 3. SPY herbelegt zijn dividend

`sw/dividend.spy_dividenden()` en `spy_stand_op()`, plus de controle in
`sw/herbalans.bereken_herbalans()`.

De regel: op de betaaldag komt het geld beschikbaar, en het wordt omgezet in SPY
tegen de eerstvolgende geldige slotkoers op of na die dag, zonder kosten. Tot dat
moment staat het contant. Het aantal SPY-aandelen groeit; de aankoopkoers van de
eerste aankoop blijft staan.

*Te onderzoeken:*

- **Kan hetzelfde dividend twee keer meetellen?** Dat is hier het echte gevaar:
  een keer contant en een keer in aandelen. De bewering is dat
  `contant na = contant voor + betaald − herbelegd` dat afdwingt. Klopt dat ook
  als er twee uitkeringen tussen twee wissels vallen, of als er één nog niet
  herbelegd kon worden?
- `bouw_verloop_keten()` rekent het aantal SPY-aandelen van de GRAFIEK uit de
  gebeurtenissen, vanaf het begin van de keten — niet uit het aantal dat in het
  laatste wisselrecord staat. Kunnen die twee uit elkaar lopen, en zo ja: valt
  dat op?
- Het samengestelde effect: een tweede uitkering rekent met de aandelen die bij
  de eerste zijn bijgekocht. Is dat juist, en kan het ergens dubbel tellen?
- Is "SPY buy-and-hold met bruto dividendherbelegging op betaaldatum" een
  eerlijke beschrijving van wat de code doet?

## 4. De wisselkoers van een uitvoeringsdag

`sw/fx.py` (de keuze, zonder internet) en `sw/beurskalender.leesvenster()` (het
venster waarin gelezen mag worden), getest in `tests/test_fx_regel.py`
(23 tests).

De regel: de laatste volledig afgesloten 1-minuutbalk van `EURUSD=X` waarvan het
interval eindigt op of vóór 16:00:00 America/New_York; bij ontbreken tot vijf
minuten eerder; nooit een balk daarna; anders stoppen. Daarnaast de
ECB-referentiekoers als controlegetal, met een grens van 1 procent.

*Te onderzoeken:*

- Yahoo zet op een minuutbalk het tijdstempel van het BEGIN. De code neemt
  daarom balken met tijdstempel ≤ 15:59. **Klopt die aanname over Yahoo?** Als
  Yahoo het einde zou stempelen, pakt de code een minuut te vroeg. Hoe zou je
  dat aan de gegevens zelf kunnen zien?
- De zomertijdwissel: 16:00 in New York is in oktober 20:00 UTC en in november
  21:00 UTC. Is er een pad waarbij de code met de verkeerde klok rekent? Let op
  balken zonder tijdzone.
- `fx_asof` blijft het moment van LEZEN en `fx_bar_end` het moment waar de koers
  bij hoort. Het leesvenster is daardoor ruimer geworden (tot acht uur na de
  slotbel, zoals de database al eiste). Verzwakt dat iets? De redenering is dat
  een afgesloten balk niet meer verandert, dus dat het leesmoment alleen nog
  een spoor is.
- `sql/04_dividend_en_fx.sql` zet een APARTE trigger op `executions` in plaats
  van `controleer_uitvoering()` uit 03 te vervangen. Bedoeling: 03 hoeft niet
  opnieuw te draaien na 04. Klopt dat, gegeven dat triggers op naam gesorteerd
  afgaan (`velden_moeten_kloppen` vóór `wisselkoersbewijs_moet_kloppen`)?
- **Eerlijk gezegd, zodat je er niet achter hoeft te komen:** het gedrag van die
  nieuwe trigger wordt door `scripts/controleer_slot.py` NIET met een echte
  poging getest, alleen zijn bestaan en of hij aanstaat (uit `pg_trigger`). Een
  poging die alleen op deze wachter stuit, zou bij een ontbrekende wachter een
  vals record in de echte keten achterlaten, en weghalen kan niet. Is er een
  veilige manier om dat tóch te beproeven?
- De ECB is een afhankelijkheid erbij: is die niet bereikbaar, dan wordt er niets
  vastgelegd. Is "stoppen" hier de juiste keuze, gezien het venster van die
  avond?

## 5. Twee curves

`sw/realistisch.py`, getest in `tests/test_realistisch.py` (15 tests).

De officiële curve blijft de eenzijdige omzet van `app.py`. De papieren curve
rekent 0,15 % over de som van de absolute dollarbedragen van alle echte orders.

*Te onderzoeken:*

- Klopt de bewering dat de twee bij de instap identiek zijn, en dat de papieren
  curve dus pas vanaf de eerste wissel afwijkt?
- De doelbedragen worden bepaald op de waarde VOOR de kosten, net als bij de
  officiële formule. Dat voorkomt rondrekenen (de kost bepaalt de doelen, de
  doelen bepalen de kost). Is dat verdedigbaar, of hoort het een vaste-puntje te
  zijn? Hoe groot is het verschil?
- De papieren curve haalt haar koersen uit de officiële records zelf
  (`opening.positions[].close_usd` en `positions[].buy_price_usd`). Is er een
  geval waarin een koers daar niet in staat?
- Dividend wordt in de papieren curve met de eigen aantallen gerekend, via
  `opening.dividend_detail`. Ontbreekt die uitsplitsing, dan stopt het. Kan een
  wissel ooit dividend meerekenen zonder die uitsplitsing te schrijven?
- Is er een pad waarlangs de papieren curve de officiële kan beïnvloeden? De
  bewering is dat dat per constructie niet kan, omdat `sw/realistisch.py` geen
  enkele schrijfweg heeft.

## 6. Wat bewust nog open staat

Noem het gerust als je vindt dat een van deze niet kan blijven wachten:

- **De Belgische beurstaks** (ordegrootte 0,35 % per richting) zit in geen van
  beide curves. Voorstel was: hoort bij de realistische curve. Nog niet gedaan.
- **De wisselkoers in de grafiek** komt uit `fx_snapshots` (de dagbalk van de
  dagelijkse taak), terwijl het uitvoeringsrecord zijn eigen minuutbalk draagt.
  Op de uitvoeringsdag kunnen die een fractie van een procent verschillen. Het
  record is het bewijs; de grafiek is weergave. Is dat houdbaar?
- **`net_per_share_usd`** blijft in de tabel staan maar wordt nergens gebruikt.
  Bewust: informatie, geen rekenbasis.

## 7. Hoe je dit pakket kunt narekenen

```
python -m pytest              # 195 tests
python -c "import json,hashlib,pathlib; ..."   # zie punt 1
```

De database zit niet in dit pakket. Wat daarin staat, is na te rekenen met
`sql/01_schema.sql` tot en met `sql/04_dividend_en_fx.sql` en met de uitvoer van
`scripts/controleer_slot.py` in `audit/aanvalstest_*.txt`. Die van deze ronde
staat in `audit/aanvalstest_2026-10-07_ronde4.txt`: 59 van 59 goed tegen de echte
database, met `deur_versie 4`, gedraaid op 7 oktober 2026 nadat `sql/04` erin
stond.
