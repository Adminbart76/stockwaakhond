# Vier beslissingen uitgevoerd: dividend, SPY, wisselkoers, kosten

Opgedragen door Bart op 7 oktober 2026, na auditronde 3. Dit document legt vast
wat er beslist is, waarom, en wat er in de code veranderd is. Het is bedoeld voor
een externe controleur en voor een volgende sessie.

**Niets historisch is herrekend.** Het signaal van 5 oktober 2026, de instap van
6 oktober 2026, `app.py`, `forward_log/` en `bewijs/` zijn niet aangeraakt. De
hashes staan onderaan dit document, zodat dat na te rekenen is.

---

## 1. Dividend is bruto, en kent twee datums

### Wat er beslist is

De officiële forward-test rekent **bruto** dividend: het volledige uitgekeerde
bedrag, voor belasting, aan beide kanten. Er valt bij een wissel niets meer te
kiezen; de vlag `--dividend=bruto|netto` bestaat niet meer.

Daarnaast wordt het verschil tussen twee datums nu overal gemaakt:

| | |
|---|---|
| `ex_date` | de dag waarop het RECHT ontstaat |
| `pay_date` | de dag waarop het GELD beschikbaar is |

- Het recht wordt bepaald met het aantal aandelen dat we **vóór de ex-dag**
  hadden — ook als dat aandeel vóór de betaaldag uit de portefeuille verdwijnt.
- Het geld telt pas mee **vanaf de betaaldag**, en gaat dus mee in de eerste
  wissel ná die dag.

### Waarom

Netto hangt af van woonplaats, broker, belastingverdrag en van regels die tijdens
een forward-test veranderen. Een curve die daarvan afhangt, meet niet meer de
strategie. Bruto is aan beide kanten hetzelfde en voor iedereen narekenbaar.

Tussen ex-datum en betaaldatum zitten twee tot zes weken. Daar zitten twee
fouten in verstopt die allebei stil zijn:

- rekenen op de ex-datum laat de portefeuille geld beleggen dat ze nog niet
  heeft — bij een stijgende markt rekent ze zich daarmee rijk;
- het recht bepalen op de betaaldatum laat het dividend verdwijnen van een
  aandeel dat er tussendoor uit ging — dan bestelen we de strategie.

Waarom "vóór de ex-dag" en niet "op de ex-dag": wie een aandeel op de ex-dag
koopt, krijgt dat dividend niet. Onze wissels gebeuren tegen de slotkoers van de
uitvoeringsdag, dus op een ex-dag die samenvalt met een uitvoeringsdag was het
oude mandje in bezit.

### Wat er gebouwd is

| | |
|---|---|
| `sw/dividend.py` | de hele regel, zonder internet en zonder database |
| `sql/04_dividend_en_fx.sql` | kolom `pay_date`, verplicht, met `pay_date >= ex_date` |
| `scripts/leg_dividend_vast.py` | een uitkering vastleggen: bedrag uit Yahoo, betaaldatum met de hand, met bron |
| `tests/test_dividend.py` | 17 tests, waaronder alle gevallen uit de opdracht |

Yahoo kent de ex-datum en het bedrag, maar **niet** de betaaldatum. Die wordt
daarom met de hand ingevuld, met vermelding van de bron. Verzinnen is geen optie:
dat zou een wissel met een verkeerd bedrag voor altijd vastleggen.

### De blokkade die ervoor in de plaats komt

Tot nu toe stopte `scripts/leg_herbalans_vast.py` als er dividend was zonder dat
de conventie vastlag. Die blokkade verviel met deze beslissing, maar het gevaar
niet: een uitkering die Yahoo kent en onze tabel niet, zou de wissel met te
weinig geld vastleggen.

Daarom stopt de wissel nu als Yahoo een uitkering meldt die niet in `dividends`
staat, met de melding wat er vastgelegd moet worden. Bewaakt door
`tests/test_werkwijze.py`.

---

## 2. SPY krijgt bruto dividend en herbelegt het

### Wat er beslist is

SPY krijgt hetzelfde bruto dividend. Het geld komt op de **betaaldag**
beschikbaar en wordt dan herbelegd in SPY zelf, tegen de **eerstvolgende geldige
slotkoers op of na die dag**, zonder kosten. Het aantal SPY-aandelen groeit
daardoor.

In documentatie heet dit:

> **SPY buy-and-hold met bruto dividendherbelegging op betaaldatum.**

Niet "een total-return index": die reeksen herbeleggen vaak op de ex-datum of met
een andere belastingconventie, en dan zou de naam iets beloven wat hier niet
gebeurt.

### Waarom

Aan onze kant wordt contant dividend bij de volgende wissel meebelegd — dat volgt
uit de doorlopende portefeuille. Zou SPY zijn dividend voor altijd contant
houden, dan is dat een systematisch verschil in ons voordeel. Nu laten beide
kanten hun uitkeringen op dezelfde manier doorwerken.

### Hoe dubbeltellen onmogelijk is gemaakt

Een uitkering zit **in de aandelen óf in het contante geld**, nooit in beide.
`sw/dividend.spy_stand_op()` rekent dat vanaf het begin van de keten uit, en
`sw/herbalans.bereken_herbalans()` rekent bij elke wissel na dat het geld klopt:

    contant na = contant voor + betaald − herbelegd

Is dat negatief, dan zou er meer herbelegd zijn dan er ooit betaald is, en stopt
de berekening. Bovendien moeten het herbelegde bedrag en de bijgekochte aandelen
samen meekomen: met maar één van de twee is niet na te rekenen tegen welke koers
er herbelegd is.

Beslissing 15 blijft overeind, iets preciezer geformuleerd: SPY wisselt niet mee
en betaalt dus nooit mee aan de rotatie van StockWaakhond. Het enige wat groeit,
is zijn aantal aandelen door zijn eigen dividend.

---

## 3. De wisselkoers: de minuutbalk van de slotbel

### Wat er beslist is

De wisselkoers van een uitvoeringsdag is de koers uit de **laatste volledig
afgesloten 1-minuutbalk van `EURUSD=X` waarvan het interval eindigt op of vóór
16:00:00 America/New_York**. Normaal is dat de balk van 15:59 tot 16:00.

| | |
|---|---|
| ontbreekt die balk | de laatste afgesloten balk daarvoor, tot maximaal vijf minuten eerder |
| nooit | een balk die ná 16:00:00 eindigt |
| ontbreekt alles | stoppen, en een mens kijkt ernaar |

Bewaard worden: de gebruikte koers, het tijdstempel van de balk (begin én einde),
het moment van lezen, en de bron. Daarnaast wordt de **ECB-referentiekoers** van
die dag vastgelegd als onafhankelijk controlegetal. Wijken de twee meer dan
**1 procent** af, dan stopt het.

### Waarom

De oude regel las de dagbalk van `EURUSD=X` op het moment van klikken. Die balk
klikt nooit vast: zolang de valutadag loopt volgt hij de koers van nu (gemeten op
6 oktober 2026: 22.54 → 1,126253, twee uur later → 1,126380), en daarna
rapporteert Yahoo voor diezelfde datum een ander getal (0,3 % verschil). Twee
mensen die dezelfde avond hetzelfde deden, kregen dus een ander getal.

Een afgesloten minuutbalk verandert niet meer. En hij hoort bij dezelfde minuut
als de slotkoersen waarmee hij in hetzelfde record staat.

### Twee tijdstempels, want ze zeggen iets anders

| veld | betekenis |
|---|---|
| `fx_bar_end` | het moment waar de koers BIJ HOORT (16:00:00 in New York) |
| `fx_asof` | het moment waarop wij hem GELEZEN hebben |

`fx_asof` blijft dus wat het was, en blijft binnen het venster dat de database
afdwingt (vanaf de slotbel tot acht uur erna). Dat is geen rekenregel maar een
spoor: zo is te zien dat er niet dagen later een gunstig getal is opgezocht.

Het leesvenster is daarmee ruimer dan vroeger: de oude regel moest vóór
middernacht in Londen gelezen zijn, omdat het getál anders veranderde. Dat
probleem bestaat niet meer. Dat is meteen de oplossing voor de taak van
7 oktober 2026 die rood werd omdat GitHub pas om 00:57 UTC startte.

### Waarom het interval moet eindigen op of vóór 16:00

Yahoo zet op een minuutbalk het tijdstempel van het **begin** van de minuut. De
balk met tijdstempel 15:59 dekt 15:59:00–16:00:00 en is de laatste minuut vóór de
slotbel. De balk met tijdstempel 16:00 dekt 16:00:00–16:01:00 en bevat handel ná
de slotbel: die mag niet, want dan zou de wisselkoers informatie bevatten die de
slotkoersen niet hebben.

### Wat er gebouwd is

| | |
|---|---|
| `sw/fx.py` | de keuze van de balk (zonder internet, dus testbaar), het ECB-controlegetal, en het ophalen |
| `sw/beurskalender.py` | `leesvenster()`: mag er nu gelezen worden? |
| `sql/04_dividend_en_fx.sql` | een aparte wachter op `executions` plus zes kolommen bij `fx_snapshots` |
| `tests/test_fx_regel.py` | 23 tests, met zomertijd/wintertijd, ontbrekende 15:59-balk en een balk ná 16:00 |

De uitvoering van 6 oktober 2026 kent deze velden niet en blijft precies zoals ze
is. De databasewachter kijkt alleen naar records die ze zelf meebrengen.

---

## 4. Twee curves: de officiële en de realistische

### Wat er beslist is

**De officiële curve blijft exact zoals ze is.** Eenzijdige omzet, de formule van
`simulate_forward()` in `app.py`, niets herrekend.

**Daarnaast komt een realistische papieren curve**: 0,15 % over de **werkelijk
verhandelde notional** — de som van de absolute dollarbedragen van alle echte
koop- en verkooporders.

### Waarom geen `omzet_factor = 2`

Omdat dat alleen klopt bij een volledige wissel:

| situatie | werkelijk verhandeld | twee keer de eenzijdige omzet |
|---|---|---|
| volledige wissel van vijf naar vijf andere | ~200 % (≈ 0,30 % kost) | ~200 % — klopt |
| 5 % contant dat bestaande posities bijkoopt | 5 % | 10 % — **fout** |
| dezelfde vijf, alleen drift | het verschil | het dubbele — **fout** |

Er wordt in die tweede situatie niets verkocht, dus er valt ook niets dubbel te
rekenen. `tests/test_realistisch.py` rekent alle vijf de gevallen uit de opdracht
na.

### Hoe de officiële curve beschermd is

Niet alleen met een afspraak, maar met de bouw: `sw/realistisch.py` heeft **geen
enkele schrijfweg**. De papieren keten wordt elke keer opnieuw gerekend uit de
officiële records (de koersen staan in die records zelf), komt nergens in
`executions`, `forward_log/` of een hash terecht, en draagt leesbare namen
(`papier-1`) in plaats van controlegetallen.

De twee curves zijn bij de instap van 6 oktober 2026 **identiek**: alles stond
contant, er werd alleen gekocht, en dan geven beide formules 1,50 euro op 1.000
euro. Ze lopen dus pas uiteen bij de eerste echte wissel. Nagerekend in
`tests/test_realistisch.py`.

Dividend in de papieren curve wordt met de **eigen** aantallen gerekend: die
portefeuille heeft na een wissel minder aandelen en dus minder dividend. Daarvoor
staat in elk wisselrecord een uitsplitsing per aandeel (`opening.dividend_detail`
met bedrag per aandeel). Ontbreekt die terwijl er wel dividend meegerekend is,
dan stopt de papieren curve in plaats van te schatten.

### Op het dashboard

Onder de gewone grafiek staat "En met de volle kosten gerekend?", met beide
bedragen naast elkaar en één grafiek met twee lijnen: de officiële doorlopend, de
realistische gestippeld. Die sectie verschijnt pas na de eerste wissel, omdat de
twee tot dan toe hetzelfde zijn.

De Belgische beurstaks zit in geen van beide; dat staat er ook bij.

---

## Wat er NIET veranderd is

| | hash |
|---|---|
| `entry_hash` (signaal 5 oktober 2026) | `0426e47ccd6e0b4f7fcecd772ce21dc5778db862e359f5eb4d239f5ce8bd5d15` |
| `strategy_hash` | `a399aecc207510c77450cd015f4f23e2b3639fc642eb9bcc29e95cbe2b84cc18` |
| `exec_hash` (instap 6 oktober 2026) | `3468930ea4971945c8e8dad57b2cc797f9c825508368eff6bef5038090d3dae7` |

`app.py` is byte-identiek aan `bewijs/app.py.bevroren-2026-10-06`, en
`forward_log/ledger.jsonl` aan `bewijs/ledger.jsonl`. Dat wordt bij elk
auditpakket opnieuw nagerekend door `scripts/maak_auditpakket.py`, dat stopt
zodra één van de drie hashes niet meer klopt.

## Wat er in de database moet gebeuren

`sql/04_dividend_en_fx.sql` uitvoeren in de SQL Editor van Supabase, ná 01, 02 en
03. Daarna geeft `select public.hardening_status();` **deur_versie 4** en slaat
`python scripts/controleer_slot.py` geen alarm.
