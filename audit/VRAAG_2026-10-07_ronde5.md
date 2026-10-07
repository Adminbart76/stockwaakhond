# Vraag aan de controleur — ronde 5, 7 oktober 2026

Dit pakket is de volledige broncode van StockWaakhond V7.1. Het bevat geen
sleutels en geen wachtwoorden: alleen wat in de openbare GitHub-map staat
(`Adminbart76/stockwaakhond`). Het commitnummer en de datum staan in
`audit/PAKKET.txt`.

Ronde 4 keek de vier beslissingen van 7 oktober 2026 na en keurde ze grotendeels
goed: alle tests slaagden, signaal, logboek, uitvoering en `app.py` waren intact,
en de vier beslissingen bleken werkelijk gebouwd. Er kwamen **twee gerichte
correcties** uit. **Deze ronde gaat over die twee en over niets anders.**

De vorige vragen staan in `audit/VRAAG_2026-10-07.md` (ronde 1 en 2),
`audit/VRAAG_2026-10-07_ronde3.md` en `audit/VRAAG_2026-10-07_ronde4.md`. Die
zijn niet gewijzigd.

Zeg het hard als iets zwakker is dan hieronder beweerd wordt. Een punt dat je
niet kunt controleren met wat er in dit pakket zit, hoor je ook te noemen.

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

In deze ronde zijn `forward_log/`, `bewijs/`, `app.py` en `sw/strategy.py` niet
aangeraakt, en ook `sql/01` tot en met `sql/04` niet. Gewijzigd zijn:
`sw/dividend.py`, `sw/fx.py`, `sw/herbalans.py`, `sw/portfolio.py`,
`scripts/controleer_slot.py`, vijf testbestanden, plus drie nieuwe bestanden
(`sql/05_fx_bewijs_verplicht.sql`, `tests/test_fx_bewijs.py`,
`tests/hulp_fx.py`).

**Wat dat doet met de twee soorten records, zo precies mogelijk:**

- `bereken_instap()` geeft zonder `fx_bewijs` nog exact dezelfde canonieke tekst
  en dezelfde hash. De controle die erbij kwam, draait alleen als er een bewijs
  meegegeven wordt, en voegt geen veld toe.
- `bereken_herbalans()` geeft dezelfde canonieke tekst als in ronde 4 bij
  hetzelfde, volledige bewijs. Wat veranderde is dat het bewijs nu **verplicht**
  is: zonder bewijs komt er geen record meer uit, in plaats van een record
  zonder bewijs. Er is nog geen enkele wissel vastgelegd, dus er is niets dat
  daardoor van hash verandert.

---

## 2. Correctie 1 — SPY-dividend op dezelfde ex-datum

**De bevinding.** `spy_dividenden()` in `sw/dividend.py` telde eerdere
herbeleggingen mee zolang `herbeleg_datum <= ex_date`. Dat is te ruim: aandelen
die pas op de ex-datum zelf tegen de slotkoers gekocht worden, hebben geen recht
op het dividend van diezelfde ex-datum.

**Wat er gebeurd is.** Die ene vergelijking is `<` geworden. Verder niets: de
grens voor onze eigen vijf lag al goed (`uitvoering_voor()` kijkt naar de
laatste uitvoering strikt vóór de ex-dag), en `spy_stand_op()` houdt bewust
`<=`, want die vraag is "is de herbelegging op deze dag al gebeurd" en niet
"wie heeft recht".

**Hoe groot was het.** In het testgeval (twee uitkeringen van 2 dollar per
aandeel, SPY op 800 dollar) kreeg SPY voor de tweede uitkering 1,4470407777
aandelen toegekend in plaats van 1,4434321972 — 0,25 % te veel, en dus 0,25 %
te veel dividend op die uitkering. Dat telt in het voordeel van de maatstaf, dus
tegen StockWaakhond, en alleen bij een samenloop van een betaaldag met een
ex-datum. Er was nog niets vastgelegd dat ermee gerekend heeft: de eerste
uitkeringen worden rond november en december 2026 verwacht.

*Te onderzoeken:*

- `tests/test_dividend.py::test_herbelegd_op_de_exdag_geeft_geen_recht_op_dat_dividend`
  is precies het geval uit de bevinding: dividend A wordt op 20 oktober
  herbelegd, dividend B heeft 20 oktober als ex-datum, en de nieuwe aandelen
  mogen niet meetellen. Er staat een test naast die bewijst dat de grens op de
  juiste dag ligt en niet dat herbelegde aandelen voortaan nooit meer meetellen
  (`..._de_dag_voor_de_exdag_geeft_wel_recht`). Dekt dat tweetal het af?
- Blijft de regel aan de twee kanten nu werkelijk dezelfde? De bewering is dat
  onze vijf en SPY beide "in bezit strikt vóór de ex-dag" gebruiken, maar langs
  een andere weg: de keten van uitvoeringen bij ons, de lijst herbeleggingen bij
  SPY.
- Is er een rangschikking van uitkeringen waarbij de lus zichzelf voor de voeten
  loopt? De som leest `uit`, de lijst die hij zelf aan het vullen is. De
  uitkeringen zijn gesorteerd op ex-datum, maar een herbelegging hoort bij een
  betaaldatum, en die loopt niet in dezelfde orde.

---

## 3. Correctie 2 — het FX-bewijs moet verplicht zijn

**De bevinding.** `sql/04_dividend_en_fx.sql` rekende de minuutbalk en het
controlegetal alleen na als het record die velden zelf meebracht:

```sql
if inhoud ? 'fx_bar_end' then ... end if;
if inhoud ? 'fx_control_rate' then ... end if;
```

Een toekomstige herbalans die de velden gewoon wegliet, kwam dus nergens langs
die controles. De wachter bewaakte in die vorm alleen wie eerlijk was over wat
hij meebracht.

**Wat er gebouwd is.** Twee lagen met dezelfde grenzen, en met opzet op twee
plaatsen:

| laag | waar | wanneer |
|---|---|---|
| in de code | `sw.fx.controleer_bewijs()`, aangeroepen door `bereken_herbalans()` en door `verify_keten()` | bij het bouwen van de wissel, op de computer van Bart |
| in de database | `sql/05_fx_bewijs_verplicht.sql`, trigger `fx_bewijs_verplicht` | bij het wegschrijven |

Dat de code het óók doet, is geen dubbelop: het lokale bestand is de bron van
waarheid en de database de spiegel (beslissing 7). Een record dat lokaal wel
weggeschreven wordt en in de database niet, is niet meer te herstellen.

**Verplicht zodra `prev_exec_hash` niet leeg is**, en alle acht:
`fx_bar_start`, `fx_bar_end`, `fx_bar_normaal`, `fx_control_source`,
`fx_control_date`, `fx_control_rate`, `fx_control_same_day`,
`fx_control_deviation_pct`.

**Wat er daarnaast nagerekend wordt**, in beide lagen:

| regel | waarom |
|---|---|
| `bar_end > bar_start` | anders is het geen interval |
| `bar_end - bar_start = 1 minuut` | 04 liet een balk van een uur door voor een minuutbalk |
| `bar_end <= slotbel`, en hoogstens 5 minuten ervoor | een balk na de bel bevat handel die de slotkoersen niet kennen |
| `fx_bar_normaal = (bar_end = slotbel)` | anders beweert het record twee dingen tegelijk |
| `control_date <= execution_date` | een koers van later kan die van die dag niet controleren |
| `fx_control_same_day = (control_date = execution_date)` | idem |
| de opgeslagen afwijking = de opnieuw berekende | anders is het getal niet uit die twee koersen gekomen |
| de afwijking blijft binnen 1 % | stond al in 04, blijft |

**De instap van 6 oktober 2026 valt er expliciet buiten.** Die is de eerste
schakel, heeft geen `prev_exec_hash` — ook niet als sleutel in de gehashte tekst
— en kende de regel van de minuutbalk nog niet; haar wisselkoers is de
dagslotkoers. De wachter in `sql/05` keert meteen terug zodra
`coalesce(new.prev_exec_hash, inhoud->>'prev_exec_hash')` leeg is, en hij staat
alleen op `before insert`, dus hij komt langs bestaande rijen niet eens.
`tests/test_fx_bewijs.py` en `tests/test_werkwijze.py` zetten beide grenzen vast.

*Te onderzoeken:*

- Is `coalesce(new.prev_exec_hash, inhoud->>'prev_exec_hash') is null` de juiste
  scheidslijn? Een record met `prev_exec_hash: null` in de gehashte tekst wordt
  zo als instap behandeld. De gedachte is dat `controleer_uitvoering()` uit 03
  dat alsnog weigert zodra er al een uitvoering staat — maar reken dat na.
- `sql/05` zet weer een APARTE trigger in plaats van die van 04 te vervangen.
  Triggers gaan op naam af: `fx_bewijs_verplicht` vóór `velden_moeten_kloppen`
  vóór `wisselkoersbewijs_moet_kloppen`. Geeft die volgorde een probleem? De
  bewering is van niet, omdat alle drie alleen lezen en weigeren.
- De afwijking wordt in Python met `float` en in Postgres met `numeric`
  uitgerekend, beide afgerond op zes decimalen, en vergeleken met een marge van
  `1e-5`. Is die marge zowel ruim genoeg om geen valse weigering te geven als
  strak genoeg om een verzonnen getal te vangen?
- `sql/05` zet ook een constraint `fx_balk_duurt_een_minuut` op `fx_snapshots`,
  maar alleen als geen bestaande rij ertegen ingaat; anders volgt een `notice`.
  Is dat de juiste keuze, of hoort het bestand dan te falen?
- **Eerlijk gezegd, zodat je er niet achter hoeft te komen:** het gedrag van
  `fx_bewijs_verplicht` wordt door `scripts/controleer_slot.py` nog steeds NIET
  met een echte poging getest — alleen zijn bestaan en of hij aanstaat, uit
  `pg_trigger`. Zelfde reden als in ronde 4: een poging die alleen op deze
  wachter stuit, zou bij een ontbrekende wachter een vals record in de echte
  keten achterlaten, en weghalen kan niet. Elke aanval op `executions` mikt
  bovendien op de `entry_hash` van de echte uitvoering, en die is uniek, dus zo
  een poging bewijst niets. Is er een veilige manier om het tóch te beproeven?
- De twee lagen kunnen in principe uit elkaar lopen. `tests/test_werkwijze.py`
  vergelijkt daarom de veldenlijst in `sw/fx.py` met de tekst van `sql/05` en
  zoekt de grenzen (`interval '1 minute'`, `interval '5 minutes'`, de
  herberekening) letterlijk in dat bestand. Is dat genoeg, of hoort hier een
  echte database in de lus?

---

## 4. Wat bewust nog open staat

Onveranderd sinds ronde 4; noem het gerust als je vindt dat een van deze niet
kan blijven wachten:

- **De Belgische beurstaks** (ordegrootte 0,35 % per richting) zit in geen van
  beide curves. Hoort bij de realistische curve. Nog niet gedaan.
- **De wisselkoers in de grafiek** komt uit `fx_snapshots` (de dagbalk van de
  dagelijkse taak), terwijl het uitvoeringsrecord zijn eigen minuutbalk draagt.
  Op de uitvoeringsdag kunnen die een fractie van een procent verschillen. Het
  record is het bewijs; de grafiek is weergave.
- **`net_per_share_usd`** blijft in de tabel staan maar wordt nergens gebruikt.
  Bewust: informatie, geen rekenbasis.

---

## 5. Hoe je dit pakket kunt narekenen

```
python -m pytest              # 232 tests
```

De vier hashes uit punt 1 zijn na te rekenen uit `forward_log/` zelf; de
strategiehash hoort ook uit te komen op `canonical_json(STRATEGY_SPEC)` van
`sw/strategy.py`.

De database zit niet in dit pakket. Wat daarin staat, is na te rekenen met
`sql/01_schema.sql` tot en met `sql/05_fx_bewijs_verplicht.sql` en met de
uitvoer van `scripts/controleer_slot.py` in `audit/aanvalstest_*.txt`. Die van
deze ronde staat in `audit/aanvalstest_2026-10-07_ronde5.txt`: **61 van 61 goed
tegen de echte database, met `deur_versie 5`**, gedraaid op 7 oktober 2026 nadat
`sql/05` erin stond.

Dat script test het GEDRAG van de nieuwe wachter niet — zie het punt daarover in
paragraaf 3. Wat het wél vaststelt, is dat de trigger bestaat, aanstaat, en dat
`hardening_status()` versie 5 meldt; en dat het signaal, het universum, de
uitvoering en de keten na alle aanvalspogingen onveranderd zijn.
