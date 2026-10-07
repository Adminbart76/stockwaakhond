# De Belgische laag: ontwerp en verantwoording

Opgedragen door Bart op 7 oktober 2026. Dit document legt vast wat er gebouwd is,
welke keuzes er gemaakt zijn en waarom. Het is bedoeld voor een externe
controleur en voor een volgende sessie. De fiscale regels zelf staan in
`BELGIE.md`; hier staat de architectuur.

**Niets van Strategie A is aangeraakt.** Het signaal van 5 oktober 2026, de
instap van 6 oktober 2026, `app.py`, `sw/strategy.py`, `forward_log/` en
`bewijs/` zijn niet gewijzigd. De hashes staan onderaan dit document.

---

## 1. De opdracht

Een aparte Belgische realistische laag bovenop StockWaakhond, die antwoordt op:
"wat zou er ongeveer overblijven als een Belgische particuliere belegger dezelfde
StockWaakhond-trades werkelijk uitvoerde?"

Met als harde grens: niets aan Strategie A wijzigen, geen vastgelegd signaal,
geen uitvoering, geen ledger, geen bewijs, geen strategiehash, en geen
herberekening van de historische officiële curve.

---

## 2. Drie gescheiden weergaven

| | |
|---|---|
| **A** | de officiële forward-test, bevroren en onaangeroerd |
| **B** | de realistische marktcurve (`sw/realistisch.py`), ongewijzigd |
| **C** | de Belgische simulatie (`sw/belgie.py`), nieuw |

C is afgeleid: ze wordt elke keer opnieuw gerekend uit de vastgelegde
uitvoeringen, de vastgelegde koersen, de tabel `dividends` en de wisselkoersen.

**C kan per constructie niet terugschrijven.** In `sw/belgie.py` zit geen enkele
schrijfweg — geen Supabase, geen bestand, geen hash. Hetzelfde principe als in
`sw/realistisch.py`. De controlegetallen van de Belgische stappen zijn met opzet
leesbare namen (`belgie-1`, `belgie-2`) en geen hashes: dit is geen
bewijsmateriaal en het hoort er ook niet op te lijken.

Op het dashboard staan de drie onder elkaar, met de officiële reeks als
doorlopende lijn en de Belgische als gestippelde.

---

## 3. De orders, en waarom er een lusje nodig is

De beurstaks wordt **per order** geheven, op het bedrag van dat order. Deze laag
kan dus niet met een gemiddeld kostenpercentage werken: ze moet weten welke
orders er werkelijk zijn.

Een order is het verschil tussen wat een positie moet worden en wat ze is:

- een aandeel dat eruit gaat, wordt volledig verkocht;
- een aandeel dat erbij komt, wordt volledig gekocht;
- een aandeel dat blijft staan, wordt alleen bijgesteld — en staat het al bijna
  op gewicht, dan is er geen order en dus geen taks;
- contant geld dat belegd wordt, zit in de koopkant en nergens anders.

Dat geeft een kringetje: de kosten bepalen hoeveel er te beleggen valt, dat
bepaalt de orders, en de orders bepalen de kosten. `_los_kosten_op()` rekent dat
door tot het stilstaat. Bij kosten van ongeveer een half procent is dat na drie
of vier rondes het geval; de uitkomst is voor iedereen hetzelfde.

**Waarom niet de aanpak van `sw/realistisch.py`.** Dat bestand bepaalt de
doelbedragen op de waarde VÓÓR de kosten. Daar kan dat, want daar hangt niets van
het exacte orderbedrag af. Hier wel: de beurstaks en de gerealiseerde meerwaarde
hangen er allebei van af, en de aandelen die overblijven moeten met die orders
kloppen.

### Twee details die in het lusje konden misgaan

1. **Een order dat in en uit de lijst springt.** Of een aandeel een order krijgt,
   wordt bepaald door een drempel van één eurocent. Zou die drempel bij elke
   ronde opnieuw toegepast worden, dan kan een aandeel dat bijna op gewicht staat
   er telkens in en uit vallen — de kost springt dan heen en weer en de
   berekening komt nooit tot rust. Daarom wordt WELKE aandelen een order krijgen
   één keer vooraf bepaald en daarna vastgehouden.

2. **Die lijst mag niet op de waarde vóór de kosten gebaseerd worden.** Een
   aandeel dat dan precies op gewicht staat, krijgt door de kosten alsnog een
   klein order. Zou het daardoor buiten de lijst vallen, dan wordt er meer belegd
   dan er is. De lijst wordt daarom bepaald na een proefronde die de kosten
   schat. `tests/test_belgie.py` dekt allebei.

---

## 4. Wat er meteen van de rekening gaat, en wat niet

| gaat er meteen af | is een jaarlijkse raming |
|---|---|
| beurstaks (TOB) | belasting op winst bij verkoop |
| brokerkosten | |
| wisselkosten | |
| ingehouden belasting op dividend | |

De meerwaardebelasting wordt met opzet **niet** per verkoop uit de portefeuille
gehaald. Geen enkele broker houdt ze in; ze wordt achteraf aangegeven en betaald.
Zou ze hier toch per trade afgaan, dan toont de curve een verloop dat nooit op
iemands rekening heeft gestaan.

Het dashboard toont daarom **portefeuillewaarde** en **waarde na fiscale
reserve** naast elkaar, en zegt erbij dat op winst die nog in de portefeuille zit
nog geen belasting staat.

---

## 5. Dividend

De officiële curve blijft bruto (beslissing 20). De Belgische laag rekent netto,
in twee stappen die niet op hetzelfde bedrag mogen staan:

    1. het bronland houdt zijn deel in       (VS: 15 %, een aanname)
    2. België heft 30 % op WAT ER OVERBLIJFT (het netto grensbedrag)

Zou stap 2 op het brutobedrag gerekend worden, dan wordt de buitenlandse heffing
een tweede keer belast. Van 100 euro bruto blijft er zo ongeveer 59,50 over.

**Het recht wordt bepaald met de EIGEN aantallen van deze laag.** De Belgische
portefeuille heeft na de kosten minder aandelen dan de officiële, dus ook minder
dividend. Het bedrag per aandeel komt uit de tabel `dividends` en is voor alle
drie de curves hetzelfde. De ex-datum bepaalt het recht, de betaaldatum het geld —
exact dezelfde regel als in `sw/dividend.py`.

**De vrijstelling is een terugvordering, geen inhouding.** Ze werkt niet aan de
bron: de voorheffing wordt altijd ingehouden en je vraagt ze terug met je
aangifte. Daarom staat ze apart en zit ze **niet** in de portefeuillewaarde. Wat
er teruggevraagd kan worden, is de voorheffing die op het vrijgestelde deel
geheven is — niet 30 % van bruto, want op een buitenlands dividend is er minder
dan dat ingehouden.

De vrijstelling geldt over alle gewone dividenden van de belastingplichtige. Wat
er elders al van gebruikt is, komt binnen via
`external_dividend_exemption_used_eur`.

---

## 6. Meerwaarde

- 10 % op wat er na de vrijstelling overblijft;
- gerealiseerde minderwaarden van **hetzelfde kalenderjaar** gaan eerst van de
  meerwaarden af;
- een verlies gaat niet over naar een volgend jaar;
- FIFO per aandeel;
- kostprijs en opbrengst in **euro**, tegen de koers van die dag, zodat het
  wisselkoerseffect in de meerwaarde zit.

De persoonlijke vrijstelling geldt ook buiten StockWaakhond; dat komt binnen via
`external_capital_gain_exemption_used_eur`.

### De vrijgestelde schijf staat open

De opdracht gaf **4.855 euro**. Publieke bronnen die op 7 oktober 2026 zijn
nagekeken, noemen **10.000 euro per jaar per persoon, jaarlijks geïndexeerd**.

Dat verschil is niet stil opgelost. Het bedrag staat op 4.855 zoals opgedragen,
en het is op drie plaatsen zichtbaar gemarkeerd als *te bevestigen*: in
`HERKOMST` in `sw/belgie.py`, in de tabel op het dashboard, en in `BELGIE.md`.
Zolang dat niet uitgeklaard is, kan de geraamde belasting te hoog staan.

Hetzelfde geldt voor de dividendvrijstelling: 833 euro hoort bij inkomstenjaar
2025; voor 2026 noemen bronnen 859 euro.

---

## 7. SPY is in deze laag geen benchmark

SPY blijft de maatstaf van het onderzoek en blijft daar onaangeroerd. In de
Belgische laag komt hij **niet** voor als praktijkbenchmark: een Amerikaanse ETF
heeft voor een Europese particulier meestal geen KID, waardoor hij er bij veel
brokers niet rechtstreeks in kan.

De Belgische curve laat de maatstafkolommen dan ook weg (`spy_eur`,
`spy_resultaat_pct`, `voorsprong_pct`). Dat is geen opsmuk: een kolom die er
staat, wordt vroeg of laat gelezen als een benchmark.

Er is **geen** UCITS-instrument gekozen. De plaats ervoor staat klaar
(`PraktijkBenchmark`, nu `None`), met ruimte voor eigen beurstaks, kosten,
dividendbeleid, valuta en brokerkosten.

---

## 8. Versienummering van de regels

De configuratie heet `BE_TAX_RULES_2026_V1`. Een wetswijziging hoort een nieuwe
versie **naast** deze te krijgen, zodat een wijziging in 2027 nooit stil de
cijfers van 2026 verandert. Dezelfde regel als voor de strategie zelf.

`be.met(regels, naam="...", ...)` maakt een kopie met andere parameters; de
standaardregels blijven staan. Dat is ook hoe de tests een brokerconfiguratie
nabootsen zonder de echte regels aan te raken.

---

## 9. Wat er gebouwd is

| | |
|---|---|
| `sw/belgie.py` | de hele laag, zonder internet en zonder database |
| `tests/test_belgie.py` | 43 wachters |
| `streamlit_app.py` | het blok "Wat zou je hier in België van overhouden?" |
| `BELGIE.md` | de fiscale regels, hun bron, en wat exact is en wat niet |
| `sw/__init__.py` | `belgie` toegevoegd aan de opsomming |

De fiscale rekenregels worden op twee niveaus getest: los, met bedragen die groot
genoeg zijn om de vrijstellingen te raken (met 1.000 euro kom je nooit aan een
meerwaarde van 4.855 euro), en als hele keten met de bedragen die er werkelijk
zijn.

---

## 10. Zelf nagekeken, los van de opdracht

Het dashboard is in twee toestanden gedraaid en met de ogen van een lezer
bekeken: de toestand van vandaag (alleen de instap), en een nagebootste tweede
wissel met koersverloop en twee dividenden. Daar kwamen deze dingen uit, allemaal
meteen hersteld:

- een vlagemoji in de titel werd door de browser als de letters "BE" getekend, en
  dan stond er "BE Wat zou je hier in België..." — dat leest als een typfout;
- "-€ 0,00" en "€ -0,00" stonden op het scherm bij bedragen die afgerond nul
  zijn. `eur()` en `eur_verschil()` maken daar nu nul van, net zoals `pct()` dat
  al deed;
- de tabel met de regels toonde de namen uit de code (`roerende_voorheffing_pct`)
  in plaats van gewone taal;
- "Dat is -€ 12,32 tegenover de officiële reeks" als titel: nu "Dat is € 12,32
  minder dan de officiële reeks";
- de kolom "Samen" in de fiscale tabel zei niet wat ze optelde: nu "Winst min
  verlies".

---

## 11. De hashes, na afloop nagerekend

| | |
|---|---|
| `strategy_hash` | `a399aecc207510c77450cd015f4f23e2b3639fc642eb9bcc29e95cbe2b84cc18` |
| `entry_hash` (signaal 5 oktober 2026) | `0426e47ccd6e0b4f7fcecd772ce21dc5778db862e359f5eb4d239f5ce8bd5d15` |
| `universe_hash` | `3114cc28ea6cb1aa0b1025f7ee01fffa9c697244cf64ca20cf013a1c8f9e813b` |
| `exec_hash` (instap 6 oktober 2026) | `3468930ea4971945c8e8dad57b2cc797f9c825508368eff6bef5038090d3dae7` |

Alle vier ongewijzigd.
