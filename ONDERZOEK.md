# StockWaakhond — Onderzoekslogboek

**Status:** actief onderzoeksdossier  
**Doel:** wetenschappelijk en praktisch onderbouwen welke strategieën StockWaakhond wel en niet moet testen.  
**Belangrijk:** dit dossier verandert niets aan de bestaande bevroren forward-test van Strategie A.

## 1. Onderzoeksregels

1. Strategie A blijft bevroren.
2. Nieuwe strategieën krijgen een eigen versie en eigen startdatum.
3. Geen winnaar achteraf ontwerpen door tientallen varianten te testen en alleen de mooiste te behouden.
4. Backtests vormen hypotheses; de echte toets is out-of-sample/forward.
5. We beoordelen rendement én drawdown, volatiliteit, turnover, kosten, robuustheid, eenvoud en uitvoerbaarheid.
6. Academische long-short resultaten mogen niet één-op-één op onze long-only Top-5 worden geprojecteerd.

## 2. Huidige referentie: Strategie A

Versie: `SW_SCORE_V3_FROZEN_2026-10-06`

Kern:
- long-only;
- Top-5;
- maandelijkse selectie;
- geen short;
- geen leverage;
- momentum/relative-strength georiënteerd;
- eerste officiële forward-signaal reeds vastgelegd;
- virtuele portefeuille start met €1.000.

Nieuwe onderzoeksinzichten mogen Strategie A niet achteraf wijzigen.

### Belgische fiscale simulatie: een uitvoeringslaag, geen strategie

Sinds 7 oktober 2026 staat er naast de officiële curve een Belgische simulatie
(`sw/belgie.py`, beschreven in `BELGIE.md`): dezelfde trades, met de Belgische
beurstaks, brokerkosten, wisselkosten en belasting op dividend en meerwaarde.

Dat is **geen nieuwe beleggingsstrategie** en telt hier niet als challenger. Ze
kiest niets, verandert niets aan de selectie, de weging of het moment van
handelen, en krijgt dus geen strategieversie, geen eigen signaal en geen eigen
logboek. Ze is een afgeleide weergave van Strategie A: alleen de netto-uitkomst
voor een particulier in één land verschilt.

De officiële curve blijft de primaire wetenschappelijke reeks.

## 3. Jegadeesh & Titman (1993)

**Titel:** *Returns to Buying Winners and Selling Losers: Implications for Stock Market Efficiency*  
**DOI:** https://doi.org/10.1111/j.1540-6261.1993.tb04702.x

Zij vonden dat strategieën die recente winnaars kopen en recente verliezers verkopen/shorten significant positieve rendementen konden genereren over ongeveer 3 tot 12 maanden.

**Relevantie:** ondersteunt de kernhypothese achter momentum.  
**Beperking:** academische long-short portefeuille, niet onze long-only Top-5.

## 4. Jegadeesh & Titman (2001)

**Titel:** *Profitability of Momentum Strategies: An Evaluation of Alternative Explanations*  
**DOI:** https://doi.org/10.1111/0022-1082.00342

Momentumwinsten bleven ook in de jaren negentig zichtbaar, wat de kans verkleint dat het oorspronkelijke resultaat puur data-snooping was.

## 5. Rouwenhorst (1998)

**Titel:** *International Momentum Strategies*  
**DOI:** https://doi.org/10.1111/0022-1082.95722

In twaalf Europese landen werd medium-term return continuation gevonden. De internationale winner-portefeuille presteerde na risicoaanpassing meer dan 1 procentpunt per maand beter dan de loser-portefeuille; het effect hield gemiddeld ongeveer een jaar aan.

**Relevantie:** momentum bleek niet uitsluitend Amerikaans.

## 6. Lesmond, Schill & Zhou (2004) — transactiekosten

**Titel:** *The illusory nature of momentum profits*  
**DOI:** https://doi.org/10.1016/S0304-405X(03)00206-X

Hun analyse waarschuwt dat momentumstrategieën vaak veel handelen in aandelen met hoge transactiekosten, waardoor theoretische winst in de praktijk sterk kan afnemen.

**Les voor StockWaakhond:** turnover en uitvoeringskosten zijn kernvariabelen, geen detail.

## 7. Daniel & Moskowitz (2016) — momentumcrashes

**Titel:** *Momentum Crashes*  
**DOI:** https://doi.org/10.1016/j.jfineco.2015.12.002

Momentumcrashes treden vooral op na sterke marktdalingen, bij hoge volatiliteit en tijdens krachtige marktoplevingen.

**Belangrijke nuance:** de klassieke crash wordt sterk gedreven door de shortkant. StockWaakhond short niets, dus heeft niet hetzelfde extreme mechanisme.

**Relevante vraag voor ons:** kan risicobeheer de drawdown van een geconcentreerde long-only momentumportefeuille verminderen zonder te veel rendement op te offeren?

## 8. Barroso & Santa-Clara (2015) — volatility management

**Titel:** *Momentum Has Its Moments*  
**DOI:** https://doi.org/10.1016/j.jfineco.2014.11.010

Zij pasten de blootstelling van een long-short momentumfactor aan op basis van recente gerealiseerde volatiliteit. Hun risk-managed variant verhoogde in de studie de Sharpe-ratio ongeveer van 0,53 naar 0,97 en verminderde crashrisico sterk.

**Waarom interessant:** selectie en risicoblootstelling kunnen los van elkaar worden onderzocht.  
**Waarom niet rechtstreeks kopiëren:** hun strategie is long-short en kan leverage impliceren; StockWaakhond wil voorlopig geen leverage.

**Mogelijke hypothese voor Strategie B:** dezelfde selectie als A, maar variabele blootstelling en de rest cash.

Nog niet goedgekeurd of gespecificeerd.

## 9. Moreira & Muir (2017)

**Titel:** *Volatility-Managed Portfolios*  
**DOI:** https://doi.org/10.1111/jofi.12513

Dit ondersteunt breder het principe van minder blootstelling bij hogere volatiliteit, maar bewijst niet dat dezelfde regel optimaal is voor onze long-only Top-5.

## 10. Cederburg et al. (2020) — belangrijke tegenstem

**Titel:** *On the Performance of Volatility-Managed Portfolios*  
**DOI:** https://doi.org/10.1016/j.jfineco.2020.04.015

Op 103 equitystrategieën bleken volatility-managed varianten niet systematisch beter te presteren voor realistische out-of-sample beleggers.

**Conclusie:** volatility management is geen bewezen wondermiddel. Juist daarom is een aparte forward-test interessant.

## 11. Raju & Chandrasekaran — long-only momentum

**Titel:** *Implementing a Systematic Long-only Momentum Strategy: Evidence From India*  
**SSRN:** https://ssrn.com/abstract=3510433

Opzet:
- long-only;
- top-deciel momentum;
- NIFTY100;
- maandelijkse herbalancering;
- liquide grote aandelen.

Volgens de auteurs:
- beter dan NIFTY100;
- gemiddelde maandelijkse turnover circa 32,1%;
- hogere volatiliteit;
- incidentele momentumcrashes;
- “time in the market” bleek belangrijker dan markt proberen timen.

**Waarom belangrijk:** dit ligt veel dichter bij onze opzet en vormt een serieuze tegenhypothese tegen te agressief uitstappen naar cash.

## 12. Huidige onderzoekshypothesen

### Hypothese A — altijd belegd blijven
Momentum werkt vooral door blootgesteld te blijven aan relatieve winnaars. Te veel timing kan het voordeel beschadigen.

### Hypothese B — blootstelling verlagen bij hoog risico
Momentum kent periodes waarin het risicoprofiel sterk verslechtert. Een eenvoudige vooraf vastgelegde risicoregel kan drawdowns mogelijk beperken.

Beide zijn plausibel; beide hebben ondersteuning én kritiek.

## 13. Wat nog NIET beslist is

Nog niet vastleggen:
- welke volatiliteitsmaatstaf B gebruikt;
- marktvolatiliteit versus Top-5/strategievolatiliteit;
- grenswaarden;
- cashpercentages;
- markttrendfilter;
- sectorinformatie;
- value/quality;
- welke strategie “beste” is.

## 14. Regels voor toekomstige strategieën B/C/D

Elke challenger krijgt vóór de start:
- unieke naam/versie;
- exacte formule;
- universum;
- data;
- rankingregels;
- rebalance-moment;
- kostenregel;
- FX-regel;
- dividendregel;
- benchmark;
- startdatum;
- strategiehash;
- eigen append-only log.

Een wijziging wordt een nieuwe strategieversie, nooit een stille aanpassing.

## 15. Volgende onderzoeksstap

Raju & Chandrasekaran verder uitspitten:

1. Welke exacte momentummaatstaf?
2. Welke ranking- en holdingperiode?
3. Hoe onderbouwen zij “time in the market”?
4. Welke drawdowns/crashperiodes?
5. Wat blijft over na kosten?
6. Gevoeligheid voor parameterkeuzes?
7. Wat is overdraagbaar naar grote Amerikaanse aandelen?
8. Wat is India-specifiek?

Daarna pas beslissen of Strategie B een volatility-managed variant moet worden of dat we eerst een eenvoudiger long-only momentumchallenger testen.

## 16. Bronnen

- Jegadeesh & Titman (1993): https://doi.org/10.1111/j.1540-6261.1993.tb04702.x
- Jegadeesh & Titman (2001): https://doi.org/10.1111/0022-1082.00342
- Rouwenhorst (1998): https://doi.org/10.1111/0022-1082.95722
- Lesmond, Schill & Zhou (2004): https://doi.org/10.1016/S0304-405X(03)00206-X
- Daniel & Moskowitz (2016): https://doi.org/10.1016/j.jfineco.2015.12.002
- Barroso & Santa-Clara (2015): https://doi.org/10.1016/j.jfineco.2014.11.010
- Moreira & Muir (2017): https://doi.org/10.1111/jofi.12513
- Cederburg et al. (2020): https://doi.org/10.1016/j.jfineco.2020.04.015
- Raju & Chandrasekaran: https://ssrn.com/abstract=3510433

---

**Laatste bijgewerkt:** 7 oktober 2026  
**Onderzoeksstatus:** momentumonderzoek loopt nog.  
**Implementatiestatus:** geen nieuwe challengerstrategie goedgekeurd.
