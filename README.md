# StockWaakhond V7.1

Een beleggingsstrategie die vooraf is vastgelegd. We meten wat ze in de praktijk
doet, en stellen haar achteraf nooit bij.

Dit is geen nieuwe analyse van het verleden. Het idee is juist het omgekeerde:
eerst opschrijven wat de strategie kiest, en daarna pas kijken wat de beurs
doet. Zo valt er achteraf niets goed te praten.

> Proef met virtueel geld. Er worden geen echte orders geplaatst en dit is geen
> beleggingsadvies.

## De bevroren strategie

Elk aandeel uit de S&P 500 krijgt een score van 0 tot 100:

| Punten | Waarvoor |
|---|---|
| 25 | rendement over 12 maanden |
| 20 | rendement over 6 maanden |
| 15 | rendement over 3 maanden |
| 15 | hoe het aandeel het deed tegenover SPY, over 6 maanden |
| 10 | koers boven het 200-daags gemiddelde |
| 5 | 50-daags gemiddelde boven het 200-daags |
| 5 | rustiger koersverloop over 3 maanden |
| 5 | kleinere terugval over 3 maanden |

De vijf hoogste scores komen in de portefeuille, gelijk verdeeld. Bij een
gelijke stand wint de alfabetisch eerste, zodat er geen willekeur in zit.
Transactiekost: 0,15 % per omzet. Een nieuwe selectie mag pas 28 dagen na de
vorige.

Deze formule staat vast en wordt niet bijgesteld. Hij wordt als tekst gehasht,
en die hash staat in elk vastgelegd signaal. Wijzigt er iets, dan klopt de hash
niet meer en faalt `tests/test_bevroren_strategie.py` onmiddellijk.

## Het logboek

Elke selectie wordt bijgeschreven in `forward_log/ledger.jsonl`, met de datum,
de vijf aandelen, hun scores en koersen, de bron van de aandelenlijst, en een
controlegetal dat verwijst naar het vorige record. Samen vormen ze een ketting
die je niet kunt wijzigen zonder dat het opvalt.

Er bestaat geen functie om een vastgelegd signaal te wijzigen, te verwijderen of
opnieuw te berekenen. Dat is geen vergetelheid: zonder die mogelijkheid bewijst
de test iets, mét die mogelijkheid niet.

Dezelfde gegevens staan in Supabase, waar zeven tabellen met een trigger
beschermd zijn tegen wijzigen en wissen — ook met de geheime sleutel, ook vanuit
de SQL-editor.

Het signaal gebruikt altijd de laatste afgesloten slotkoers: een beursdag die
nog loopt kan geen signaaldag worden, ook niet als Yahoo er al een voorlopige
rij voor levert. De portefeuille stapt pas in op de eerstvolgende beursdag,
zodat er nooit gehandeld wordt tegen een koers die bij het kiezen al bekend was.

De database bewaakt dat zelf ook. `sql/02_hardening.sql` laat alleen een echt
volgend schakeltje in de keten toe: het juiste volgnummer, het controlegetal van
de voorganger, minstens 28 dagen later, en een formule die werkelijk bij de
strategie hoort. Een vervalst signaal met een kloppend controlegetal komt er dus
niet meer in - en dat is belangrijker dan het achteraf opmerken, want weghalen
kan niet.

## De virtuele portefeuille

€1.000, gelijk verdeeld over de vijf aandelen.

Aankoopkoers, aantal aandelen en wisselkoers worden één keer vastgelegd en
daarna nooit herberekend. Zo verschuift het rendement niet maanden later,
wanneer Yahoo oude koersen verlaagt na een dividenduitkering.

De benchmark SPY krijgt exact dezelfde inleg, kosten, wisselkoers, startdag en
dividendbehandeling. Alles wordt in dollar opgeteld en pas op het einde één keer
omgezet naar euro, zodat het wisselkoerseffect niet dubbel kan tellen.

Dividend telt bij allebei mee, bruto: het volledige uitgekeerde bedrag, voor
belasting. Het recht ontstaat op de ex-datum, het geld komt op de betaaldatum.
Aan onze kant blijft het als geld staan tot de volgende wissel; SPY koopt er op
de betaaldag meer SPY mee.

Ontbreekt er een koers, dan toont het dashboard geen bedrag. Liever geen cijfer
dan een cijfer dat eruitziet als de waarde van nu terwijl het op een oude koers
rust.

## Drie weergaven, en wat ze elk meten

| | |
|---|---|
| de officiële forward-test | de bevroren strategie, zoals vastgelegd. Dit is de uitkomst van de proef. |
| de realistische marktcurve | dezelfde trades, met de transactiekost over alles wat werkelijk verhandeld is |
| de Belgische simulatie | dezelfde trades, plus de beurstaks, de brokerkosten, de wisselkosten en de Belgische belasting op dividend en op winst bij verkoop |

De eerste blijft de officiële reeks en wordt nooit herrekend. De andere twee
staan ernaast en worden elke keer opnieuw uit de vastgelegde gegevens berekend;
ze kunnen niets wijzigen. De Belgische simulatie is indicatief en staat uitgelegd
in `BELGIE.md`: ze is geen fiscale aangifte en geen beleggingsadvies.

## Gebruiken

Dubbelklik op `BEKIJK DASHBOARD.bat` om het dashboard te openen.

Of met de hand:

```
python -m pip install -r requirements.txt
python -m streamlit run streamlit_app.py
```

Controleren of alles nog klopt:

```
python -m pytest                     # 275 wachters op formule, logboek en rekenwerk
python scripts/controleer_slot.py    # valt de database aan en controleert dat het mislukt
python scripts/importeer_ledger.py   # vergelijkt de database met het lokale bestand
```

## Mappen

| | |
|---|---|
| `bewijs/` | het bewijsmateriaal. Nooit wijzigen. Begin bij `LEESMIJ.txt`. |
| `forward_log/` | het werkende logboek |
| `sw/` | de rekenkern, zonder schermcode |
| `sql/` | wat er in Supabase draait, in deze volgorde: `01_schema.sql`, `02_hardening.sql`, `03_smalle_deur.sql`, `04_dividend_en_fx.sql`, `05_fx_bewijs_verplicht.sql` |
| `scripts/` | onderhoud en controle |
| `tests/` | de wachters |

`BELGIE.md` legt uit welke Belgische regels de simulatie gebruikt, waar ze
vandaan komen, en wat exact is en wat nog een aanname.

`CLAUDE.md` bevat de stand van zaken, de genomen beslissingen en wat er nog open
staat.
