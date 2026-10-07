# De Belgische laag

Wat zou een Belgische particuliere belegger overhouden als hij dezelfde trades
als StockWaakhond werkelijk uitvoerde? Dat is de enige vraag die dit document
beantwoordt.

**Dit is een indicatieve simulatie. Het is geen fiscale aangifte en geen
persoonlijk beleggingsadvies.**

Opgezet op 7 oktober 2026. Alle regels hieronder zijn op die dag nagekeken; per
regel staat erbij waar ze vandaan komt en hoe zeker ze is.

---

## 1. Waar deze laag staat tussen de andere twee

Er zijn drie berekeningen, en ze meten elk iets anders.

| | Wat het meet | Waar het staat |
|---|---|---|
| **A. De officiële forward-test** | de bevroren Strategie A, zoals vastgelegd | `app.py`, `sw/strategy.py`, `sw/herbalans.py` |
| **B. De realistische marktcurve** | dezelfde trades, met de transactiekost over alles wat werkelijk verhandeld is | `sw/realistisch.py` |
| **C. De Belgische simulatie** | dezelfde trades, plus de Belgische beurstaks, brokerkosten, wisselkosten en belasting | `sw/belgie.py` |

**A blijft de primaire wetenschappelijke curve.** C beantwoordt een andere vraag
en vervangt A nooit.

C kan A en B ook niet veranderen. Dat is niet alleen een afspraak: in
`sw/belgie.py` zit geen enkele schrijfweg. De Belgische keten wordt elke keer
opnieuw gerekend uit de vastgelegde uitvoeringen, de vastgelegde koersen, de
tabel `dividends` en de wisselkoersen. Er komt niets van terecht in `executions`,
in `forward_log/`, in `bewijs/` of in welke hash dan ook.

---

## 2. Wat gaat er meteen van de rekening, en wat niet

Dit onderscheid is de kern.

**Gaat er meteen af** — dit zit dus in de Belgische curve:

- de beurstaks (TOB) op elke aankoop en elke verkoop;
- de brokerkosten;
- de wisselkosten van de broker;
- de belasting die bij een dividenduitkering wordt ingehouden.

**Gaat er NIET meteen af** — dit staat apart, als jaarlijkse raming:

- de belasting op winst bij verkoop (meerwaardebelasting).

Waarom dat onderscheid: geen enkele broker houdt de meerwaardebelasting per trade
in. Je geeft ze zelf aan en betaalt ze achteraf. Zou ze hier toch per verkoop van
de portefeuille gaan, dan toont de curve een verloop dat nooit op iemands
rekening heeft gestaan.

Daarom staan er op het dashboard twee bedragen naast elkaar:

- **portefeuillewaarde** — wat er op de rekening staat;
- **waarde na fiscale reserve** — datzelfde bedrag min de geraamde belasting op
  de winst die al gerealiseerd is.

Op winst die nog in de portefeuille zit, staat nog geen belasting. Die ontstaat
pas op de dag dat er verkocht wordt.

---

## 3. De beurstaks (TOB)

| | |
|---|---|
| **Wat** | 0,35 % op elke aankoop én elke verkoop van gewone aandelen |
| **Maximum** | 1.600 euro per verrichting |
| **Status** | **exact** |
| **Bron** | FOD Financiën, circulaire 2026/C/42 (FAQ taks op de beursverrichtingen) |
| **Nagekeken** | 7 oktober 2026 |

**0,35 % is in deze simulatie de conventie voor gewone aandelen.** Andere
instrumenten hebben een ander tarief, en dat is ook zo ingebouwd: het tarief
staat per instrumenttype in de configuratie.

| instrumenttype | tarief | maximum |
|---|---|---|
| `aandeel` | 0,35 % | 1.600 euro |
| `obligatie` | 0,12 % | 1.300 euro |
| `fonds_distributie` | 0,12 % | 1.300 euro |
| `fonds_kapitalisatie_be` | 1,32 % | 4.000 euro |

Alle StockWaakhond-posities staan op `aandeel`. Staat er ooit een ander
instrument in, dan krijgt het zijn eigen type mee; een onbekend type geeft een
foutmelding in plaats van een geraden tarief.

**De taks wordt per order gerekend, op het bedrag van dat order.** Dus: 200 euro
verkopen en 200 euro kopen is twee keer de taks op 200 euro, en niet één keer de
taks op de hele portefeuille. Blijft een aandeel in de Top-5 staan en is het
bedrag al bijna goed, dan is er geen order en dus geen taks.

---

## 4. Brokerkosten en wisselkosten

**Er is nog geen broker gekozen. Daarom staat hier niets ingesteld, en dat zegt
het dashboard er ook bij.** Er worden geen brokerkosten verzonnen.

| parameter | waarde nu | status |
|---|---|---|
| `broker_fixed_fee_per_order_eur` | 0 | nog niet ingesteld |
| `broker_variable_fee_pct` | 0 | nog niet ingesteld |
| `broker_minimum_fee_eur` | 0 | nog niet ingesteld |
| `fx_conversion_fee_pct` | 0 | nog niet ingesteld |

Zodra er een broker gekozen is, kunnen die vier ingevuld worden zonder dat er
iets aan de opbouw verandert. De kost per order is dan:

    vast bedrag + percentage van het orderbedrag, met een minimum

**Let op bij het invullen:** de forward-test rekent zelf al een transactiekost van
0,15 %, en die staat hier voorlopig op de plaats van de brokerkosten. Komt er een
echte brokerconfiguratie, dan hoort `basiskost_pct` op `0.0` te gaan — anders
wordt dezelfde kost twee keer gerekend.

**Wisselkosten.** De portefeuille wisselt één keer van euro naar dollar, bij de
instap. De rotaties daarna zijn dollar naar dollar, dus daar wisselt er niets.
Houdt de broker wél bij elk order om, zet dan `fx_conversie_bij_elke_order` aan;
dan komt de wisselkost ook op elk order.

---

## 5. Dividend

### Hoe het gerekend wordt

Een Amerikaans dividend komt in twee stappen binnen:

1. **De Verenigde Staten houden 15 % in** aan de bron.
2. **België heft 30 % op wat er overblijft** (het netto grensbedrag).

Van 100 euro bruto blijft er zo ongeveer **59,50 euro** over.

Die volgorde is belangrijk: de Belgische voorheffing wordt op 85 euro gerekend en
niet op 100. Anders zou de Amerikaanse heffing een tweede keer belast worden.

### De vrijstelling

| | |
|---|---|
| **Wat** | de eerste schijf gewone dividenden per belastingplichtige per jaar is vrijgesteld |
| **Bedrag** | 833 euro |
| **Status** | **te bevestigen** |
| **Bron** | doorgegeven door Bart op 7 oktober 2026 |
| **Nagekeken** | 7 oktober 2026 |

833 euro is het bedrag voor **inkomstenjaar 2025** (aanslagjaar 2026). Voor
inkomstenjaar 2026 noemen publieke bronnen **859 euro**. Dat moet nog bevestigd
worden bij een officiële bron. Het staat hier op 833 zoals opgedragen; wijzigen
hoort te gebeuren met een nieuwe regelversie.

**De vrijstelling werkt niet aan de bron.** De voorheffing wordt altijd eerst
ingehouden; je vraagt ze daarna terug met je belastingaangifte. Daarom staat dat
bedrag op het dashboard apart als "nog terug te vragen" en zit het **niet** in de
portefeuillewaarde.

Wat er teruggevraagd kan worden, is de Belgische voorheffing die op het
vrijgestelde deel geheven is — niet 30 % van het brutobedrag. Op een buitenlands
dividend is de voorheffing immers op het netto grensbedrag geheven, dus minder
dan 30 % van bruto. Meer terugvragen dan er ingehouden is, kan niet.

**De vrijstelling geldt over ALLE gewone dividenden van de belastingplichtige**,
niet alleen die van StockWaakhond. Wat er elders al van gebruikt is, komt binnen
via `external_dividend_exemption_used_eur` (nu 0).

### De buitenlandse bronheffing

| | |
|---|---|
| **Wat** | 15 % voor Amerikaanse gewone aandelen |
| **Status** | **aanname** |
| **Bron** | verdragstarief België-VS |
| **Nagekeken** | 7 oktober 2026 |

Dit is nadrukkelijk **geen universele waarheid**. Het verdragstarief van 15 %
geldt alleen als de broker de juiste documenten heeft ingediend (het formulier
W-8BEN). Zonder dat is het 30 %. Het percentage staat daarom per land in de
configuratie (`foreign_withholding_pct`), en een ticker kan een eigen land
meekrijgen (`land_per_ticker`). Een onbekend land geeft een foutmelding in plaats
van een geraden percentage.

### De officiële curve blijft bruto

De officiële forward-test rekent het volledige uitgekeerde bedrag, voor
belasting, aan beide kanten. Dat blijft zo (beslissing 20 in `CLAUDE.md`). Alleen
de Belgische laag rekent netto.

---

## 6. De belasting op winst bij verkoop (meerwaardebelasting)

| | |
|---|---|
| **Tarief** | 10 % |
| **Status van het tarief** | **exact** |
| **Vrijgestelde schijf** | 4.855 euro per belastingplichtige per jaar |
| **Status van de schijf** | **te bevestigen** |
| **Bron van de schijf** | doorgegeven door Bart op 7 oktober 2026 |
| **Nagekeken** | 7 oktober 2026 |

> **Let op.** Publieke bronnen noemen voor deze vrijstelling **10.000 euro per
> jaar per persoon, jaarlijks geïndexeerd**, en niet 4.855 euro. Dat verschil is
> op 7 oktober 2026 gemeld en nog niet uitgeklaard. Zolang dat niet gebeurd is,
> is de geraamde belasting op het dashboard mogelijk te hoog. Het bedrag staat op
> 4.855 zoals opgedragen; een wijziging hoort een nieuwe regelversie te krijgen.

### De rekenregels

1. Winst en verlies van **hetzelfde kalenderjaar** gaan tegen elkaar af.
2. Een verlies gaat **niet** over naar een volgend jaar.
3. Van wat er overblijft is de eerste schijf vrijgesteld.
4. Op de rest komt 10 %.

### FIFO

Verkopen gebeurt met FIFO: wat het eerst gekocht is, gaat het eerst weg. Dat
maakt pas verschil zodra een aandeel in de Top-5 blijft staan en er alleen
bijgesteld wordt — dan liggen er meerdere pakketjes met een verschillende
aankoopprijs.

### In euro, niet in dollar

Aankoopprijs en verkoopprijs worden in **euro** bewaard, tegen de wisselkoers van
die dag. Het wisselkoerseffect zit dus in de winst. Dat is ook wat een Belgische
aangifte doet: de meerwaarde van een Amerikaans aandeel is het verschil tussen
twee eurobedragen.

### Transactiekosten in de basis?

| | |
|---|---|
| **Wat** | de winst wordt gerekend op de orderbedragen, zonder de kosten erbij |
| **Status** | **aanname**, nog na te gaan |

Instelbaar met `kosten_in_meerwaardebasis`. Staat nu op `False`.

### Geen posities van vóór 2026

StockWaakhond start in oktober 2026, dus er zijn geen posities van vóór
1 januari 2026 in deze portefeuille. De overgangsregels daarvoor zijn hier niet
ingebouwd en zijn ook niet nodig.

### De persoonlijke vrijstelling geldt ook elders

Net als bij dividend geldt de vrijstelling per belastingplichtige, dus ook voor
beleggingen buiten StockWaakhond. Wat daar al van gebruikt is, komt binnen via
`external_capital_gain_exemption_used_eur` (nu 0).

---

## 7. SPY is hier geen benchmark

**SPY blijft de maatstaf van het onderzoek** en blijft daar onaangeroerd staan.

In de Belgische laag komt SPY met opzet **niet** voor als praktijkbenchmark. Een
Amerikaanse ETF heeft voor een Europese particulier meestal geen KID — de
informatiefiche die de PRIIPs-regels eisen — waardoor hij er bij veel brokers
niet rechtstreeks in kan. SPY een "Belgische praktijkbenchmark" noemen zou dus
een vergelijking zijn met iets wat je niet kunt kopen.

De Belgische curve toont daarom geen maatstaflijn. In de code is de kolom
`spy_eur` er bewust uit gehaald, zodat niemand ze alsnog zo kan lezen.

**Er is nog geen Belgische praktijkbenchmark gekozen.** Dat wordt later een
UCITS-instrument, en het wordt pas gekozen als broker en instrument onderzocht
zijn. De plaats ervoor staat klaar (`PraktijkBenchmark` in `sw/belgie.py`, nu
`None`), met ruimte voor zijn eigen beurstaks, kosten, dividendbeleid, valuta en
brokerkosten.

---

## 8. Wat er NIET in zit

- **Geen enkel brokertarief.** Er is nog geen broker gekozen.
- **Geen Belgische praktijkbenchmark.** Nog niet gekozen.
- **Geen fiscale optimalisatie.** Er wordt niets geoptimaliseerd, alleen geraamd.
- **Geen gemeentebelasting of aanvullende heffingen.**
- **Geen taks op effectenrekeningen.** Die begint pas ver boven deze bedragen.
- **Geen overgangsregels voor posities van vóór 2026.** Die zijn er niet.
- **Geen nettocurve voor dividend in de officiële reeks.** Die blijft bruto.

---

## 9. Een wetswijziging verandert nooit het verleden

De hele configuratie heeft een versienaam: **`BE_TAX_RULES_2026_V1`**.

Verandert er iets aan de wet, dan komt er een nieuwe versie **naast** deze, met
een eigen naam. Zo kan een wijziging in 2027 nooit stil de cijfers van 2026
veranderen. Dezelfde regel als voor de strategie zelf: een wijziging is een
nieuwe versie, nooit een stille aanpassing.

---

## 10. Voor wie in de code kijkt

| | |
|---|---|
| De laag zelf | `sw/belgie.py` |
| De wachters | `tests/test_belgie.py` |
| Op het dashboard | het blok "Wat zou je hier in België van overhouden?" |

De parameternamen in de configuratie, met de leesbare naam die op het dashboard
staat:

| parameter | op het scherm |
|---|---|
| `tob` | Beurstaks (TOB) op gewone aandelen |
| `roerende_voorheffing_pct` | Belgische belasting op dividend (roerende voorheffing) |
| `dividend_vrijstelling_eur` | Vrijstelling op dividend, per persoon per jaar |
| `external_dividend_exemption_used_eur` | wat er elders al van die vrijstelling gebruikt is |
| `foreign_withholding_pct` | Buitenlandse bronheffing op dividend |
| `meerwaarde_pct` | Tarief van de belasting op winst bij verkoop |
| `meerwaarde_vrijstelling_eur` | Vrijstelling op winst bij verkoop, per persoon per jaar |
| `external_capital_gain_exemption_used_eur` | wat er elders al van die vrijstelling gebruikt is |
| `broker_fixed_fee_per_order_eur` | Vaste brokerkost per order |
| `broker_variable_fee_pct` | Brokerkost in procent van het orderbedrag |
| `broker_minimum_fee_eur` | Laagste brokerkost per order |
| `fx_conversion_fee_pct` | Wisselkost van de broker |
| `basiskost_pct` | Transactiekost van de forward-test |
| `kosten_in_meerwaardebasis` | Tellen de kosten mee bij het berekenen van de winst? |

Een parameter wijzigen doe je met `be.met(regels, naam="...", ...)`. Dat maakt een
kopie; de standaardregels blijven staan zoals ze zijn.

### Waarom de kosten in een lusje berekend worden

De kosten bepalen hoeveel er te beleggen valt, en wat er te beleggen valt bepaalt
de orders, en de orders bepalen de kosten. Dat kringetje wordt doorgerekend tot
het stilstaat (`_los_kosten_op`). Bij kosten van een half procent is dat na drie
of vier rondes het geval, en het geeft voor iedereen hetzelfde getal.

Dat moet hier, en in `sw/realistisch.py` niet: de beurstaks en de gerealiseerde
winst hangen allebei af van het exacte orderbedrag, een gemiddeld
kostenpercentage volstaat dus niet.

---

## 11. Wat er nog moet gebeuren

1. **De vrijgestelde schijf van de meerwaardebelasting bevestigen.** 4.855 euro
   of 10.000 euro — zie hoofdstuk 6.
2. **De dividendvrijstelling bevestigen** voor inkomstenjaar 2026: 833 of 859
   euro.
3. **Een broker kiezen** en de vier kostenparameters invullen (en dan
   `basiskost_pct` op 0 zetten).
4. **Een Belgische praktijkbenchmark kiezen**: een UCITS-instrument, met zijn
   eigen kosten en dividendbeleid.
5. **Nagaan of transactiekosten in de meerwaardebasis mogen.**
