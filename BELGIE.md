# De Belgische laag

Wat zou een Belgische particuliere belegger overhouden als hij dezelfde trades
als StockWaakhond werkelijk uitvoerde? Dat is de enige vraag die dit document
beantwoordt.

**Dit is een indicatieve simulatie. Het is geen fiscale aangifte en geen
persoonlijk beleggingsadvies.**

Opgezet op 7 oktober 2026, bijgewerkt op 8 oktober 2026 na de controle van
auditronde 6. Per regel staat erbij waar ze vandaan komt en hoe zeker ze is.

De bedragen hieronder horen bij **inkomstenjaar 2026** en staan in regelversie
`BE_TAX_RULES_2026_V2`. De vrijstellingen worden elk jaar aangepast; een later
jaar krijgt dus een eigen regelversie.

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

**Dit kan niet verkeerd ingesteld worden.** De forward-test rekent zelf al een
transactiekost van 0,15 % (`basiskost_pct`), en die staat hier voorlopig op de
plaats van de brokerkosten. Zet iemand brokerkosten in zonder `basiskost_pct` op
`0.0` te zetten, dan **stopt het met een foutmelding**: zo'n configuratie bestaat
niet. Anders zou elk order twee keer betaald worden, en dat is aan de cijfers
niet te zien.

```python
# dit werkt niet meer, en dat hoort zo
be.met(regels, naam="...", broker_fixed_fee_per_order_eur=2.0)

# zo wel: de basiskost gaat in dezelfde beweging naar nul
be.met(regels, naam="...", broker_fixed_fee_per_order_eur=2.0, basiskost_pct=0.0)
```

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
| **Status** | **bevestigd** |
| **Bron** | FOD Financiën |
| **Nagekeken** | 8 oktober 2026 |

833 euro geldt voor **inkomstenjaar 2026**; dat is nagekeken bij de FOD
Financiën. Het bedrag van 859 euro dat op 7 oktober 2026 als mogelijk
alternatief genoemd werd, is dus niet van toepassing.

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
| **Vrijgestelde schijf** | **10.000 euro** per belastingplichtige, voor inkomstenjaar 2026 |
| **Status van de schijf** | **bevestigd** |
| **Bron van de schijf** | Kamer, dossier 56K1244 |
| **Nagekeken** | 8 oktober 2026 |

### Basisbedrag en effectief bedrag zijn niet hetzelfde

Twee bedragen die door elkaar gehaald kunnen worden:

| | |
|---|---|
| **basisbedrag in de wettekst** | 4.855 euro |
| **effectief vrijgesteld in 2026** | **10.000 euro** |

De parlementaire stukken bij de aangenomen wet bepalen dat het basisbedrag voor
inkomstenjaar 2026 zo wordt aangepast dat de vrijstelling **effectief 10.000
euro** bedraagt. Dat laatste is wat hier gerekend wordt.

Tot 8 oktober 2026 stond er 4.855 euro. Dat is niet stil rechtgezet: de oude
instelling blijft als `BE_TAX_RULES_2026_V1` bestaan, en wat er nu gerekend
wordt, heet `BE_TAX_RULES_2026_V2`. Zo is narekenbaar welk bedrag er wanneer
gebruikt is.

**Dit bedrag geldt alleen voor 2026.** Het wordt geïndexeerd, dus een later jaar
hoort een eigen regelversie te krijgen. Zolang die er niet is, rekent de raming
van dat jaar nog met het bedrag van 2026 — en dan zegt het dashboard dat er ook
bij. Stil doorrekenen gebeurt niet.

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
| **Status** | **bevestigd** |
| **Bron** | parlementaire toelichting bij de wet (Kamer, dossier 56K1244) |
| **Nagekeken** | 8 oktober 2026 |

De toelichting zegt het uitdrukkelijk: kosten bij aankoop of verkoop en
belastingen zoals de beurstaks hebben **geen invloed** op de berekening van de
meerwaarde. Ze gaan dus wel van de rekening af, maar niet van de belastbare
winst.

Instelbaar met `kosten_in_meerwaardebasis`. Staat op `False` en dat is geen
aanname meer.

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

De hele configuratie heeft een versienaam. Er zijn er nu twee:

| versie | wat erin staat | wordt ermee gerekend? |
|---|---|---|
| `BE_TAX_RULES_2026_V1` | de vrijstelling op meerwaarde op het wettelijke basisbedrag van 4.855 euro | nee, historisch spoor |
| `BE_TAX_RULES_2026_V2` | diezelfde vrijstelling op de 10.000 euro die in 2026 effectief geldt | **ja** |

V1 is op 8 oktober 2026 niet bijgewerkt maar bewaard. Zo blijft narekenbaar met
welk bedrag er vóór die dag gerekend werd.

Verandert er iets aan de wet of wordt een bedrag geïndexeerd, dan komt er een
nieuwe versie **naast** deze, met een eigen naam. Zo kan een wijziging in 2027
nooit stil de cijfers van 2026 veranderen. Dezelfde regel als voor de strategie
zelf: een wijziging is een nieuwe versie, nooit een stille aanpassing.

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
| `geldig_voor_inkomstenjaar` | het jaar waar deze bedragen bij horen |

Een parameter wijzigen doe je met `be.met(regels, naam="...", ...)`. Dat maakt een
kopie; de standaardregels blijven staan zoals ze zijn.

### Waarom de kosten in een lusje berekend worden

De kosten bepalen hoeveel er te beleggen valt, en wat er te beleggen valt bepaalt
de orders, en de orders bepalen de kosten. Dat kringetje wordt doorgerekend tot
het stilstaat (`_los_kosten_op`).

Er moeten **twee** dingen tegelijk kloppen:

1. de **hoogte** van de kosten;
2. **welke** aandelen een order krijgen. Dat hangt er ook van af: een aandeel
   dat zonder kosten precies op gewicht staat, krijgt er met kosten alsnog een
   klein order bij.

Daarom staan er twee lussen in elkaar. De binnenste zoekt de kosten bij een
vaste lijst orders; de buitenste kijkt daarna of de uitkomst werkelijk precies
die lijst oplevert, en rekent opnieuw als dat niet zo is. Pas als beide stil
staan is het antwoord zelfconsistent: de orders in de lijst zijn precies de
orders die er zijn.

Blijft de lijst heen en weer springen — met een minimumkost per order kan een
order dat net boven de eurocent uitkomt zichzelf er weer onder duwen — dan is er
geen antwoord waarin alles klopt. **Dan stopt het met een foutmelding.** Een van
de twee kiezen zou een getal geven dat van de rekenrichting afhangt, en dat is
niet narekenbaar.

Dat moet hier, en in `sw/realistisch.py` niet: de beurstaks en de gerealiseerde
winst hangen allebei af van het exacte orderbedrag, een gemiddeld
kostenpercentage volstaat dus niet.

---

## 11. Wat er nog moet gebeuren

1. **Een broker kiezen** en de vier kostenparameters invullen. `basiskost_pct`
   moet dan in dezelfde stap op 0 — anders weigert de configuratie zichzelf.
2. **Een Belgische praktijkbenchmark kiezen**: een UCITS-instrument, met zijn
   eigen kosten en dividendbeleid. SPY komt daar niet voor in aanmerking.
3. **Een regelversie voor 2027 maken** zodra de geïndexeerde bedragen van dat
   jaar bekend zijn. Tot dan rekent een raming over 2027 nog met de bedragen van
   2026, en zegt het dashboard dat erbij.

Afgehandeld op 8 oktober 2026, na auditronde 6: de vrijgestelde schijf van de
meerwaardebelasting (10.000 euro, hoofdstuk 6), de dividendvrijstelling (833
euro, hoofdstuk 5) en de vraag of transactiekosten in de meerwaardebasis mogen
(nee, hoofdstuk 6).
