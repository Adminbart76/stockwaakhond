# Eén doorlopende portefeuille van €1.000

Ontwerp van 7 oktober 2026, naar aanleiding van punt 1 van auditronde 2.
Geschreven vóór de code, zodat de regels na te rekenen zijn zonder de code te
lezen.

## Wat er mis was

`bereken_instap()` begint altijd met €1.000. Dat is juist voor het eerste
signaal en fout voor elk signaal daarna: dan zou er elke maand nieuw geld
bijkomen, zou winst en verlies van de vorige maand verdwijnen, en zou de
transactiekost over een vers bedrag gerekend worden in plaats van over wat er
werkelijk van hand verwisselt.

## De regel in één zin

Er wordt één keer €1.000 ingelegd. Daarna verandert alleen de verdeling: bij
elk nieuw signaal wordt de dan geldende waarde van de portefeuille herverdeeld
over de nieuwe Top-5, en de kost wordt gerekend over wat er werkelijk omgaat.

## De keten

| | |
|---|---|
| uitvoering 1 | de instap van 6 oktober 2026. Blijft exact zoals ze is. |
| uitvoering 2, 3, … | een wissel. Verwijst naar de vorige met `prev_exec_hash`. |

Elke uitvoering hangt met een controlegetal aan de vorige, net zoals de
signalen aan elkaar hangen. Eén uitvoering per signaal, niet meer (`entry_hash`
is uniek in de tabel `executions`).

De laatste uitvoering in de keten beschrijft de volledige huidige toestand:
welke aandelen, hoeveel stuks, hoeveel contant geld, en de onveranderde
SPY-positie. Het dashboard en de dagelijkse taak hebben niets anders nodig dan
die ene regel.

## Hoe een wissel gerekend wordt

Op de eerste beursdag na het signaal, tegen de slotkoersen van die dag
(de echte koersen, niet de voor dividend herrekende).

1. **Waarde vóór de wissel**, alles in dollar:
   `V = som(aantal x slotkoers) + contant geld`
   Contant geld is dividend dat sinds de vorige uitvoering is uitgekeerd.
   Ontbreekt de slotkoers van één gehouden aandeel, dan stopt het hier. Er
   wordt geen koers geschat (beslissing 9).
2. **Huidige gewichten**: elk aandeel zijn waarde gedeeld door `V`, en het
   contante geld ook als gewicht.
3. **Doelgewichten**: gelijk verdeeld over de nieuwe Top-5, dus 20 % elk.
4. **Omzet** — exact de formule van de bevroren simulatie in `app.py`:
   `omzet = 0,5 x (som van alle |doel - huidig| + |gewicht contant geld|)`
5. **Kost**: `omzet x 0,15 %` van `V`.
6. **Opnieuw verdelen**: `(V - kost)` gelijk over de vijf nieuwe aandelen,
   tegen de slotkoers van die dag. Daarna is er geen contant geld meer.

Wat die formule automatisch goed doet: een aandeel dat in beide Top-5's staat,
wordt alleen voor het verschil bijgesteld. Blijven alle vijf staan, dan is de
omzet bijna nul en de kost bijna nul.

### Twee controles die deze formule doorstaat

| situatie | omzet | kost |
|---|---|---|
| de eerste instap (alles contant) | 1,00 | 0,15 % van €1.000 = €1,50 |
| volledige wissel van vijf aandelen | 1,00 | 0,15 % van de waarde |
| alle vijf blijven staan | ~0,01 | ~0,0015 % |

De eerste regel is precies wat er op 6 oktober 2026 gebeurd is. De bestaande
uitvoering komt er dus ongewijzigd uit.

### De kostenconventie blijft open

Bij een volledige wissel gaat er €2.000 over de toonbank (verkopen én kopen),
en rekent deze formule 0,15 % in plaats van 0,30 %. Dat is de conventie van de
bevroren simulatie en die wordt hier bewust niet gewijzigd: dat is het
openstaande punt uit `CLAUDE.md`, en het hoort bij de bevroren opzet.

De code heeft daarvoor één parameter (`omzet_factor`, standaard 1,0). Die staat
er voor de realistische tweede curve die later naast de bevroren curve komt.
Een vastgelegde wissel gebruikt altijd de bevroren conventie.

## SPY, de maatstaf

| | |
|---|---|
| start | één keer €1.000 op 6 oktober 2026, dezelfde dag, dezelfde kost |
| daarna | niets. Het aantal aandelen verandert nooit meer. |
| maandelijks terugzetten naar €1.000 | nee |
| meebetalen aan de wisselkosten van StockWaakhond | nee |
| dividend | wel meegeteld, met dezelfde conventie als de andere kant |

Bij elke wissel wordt het SPY-blok letterlijk overgenomen uit de vorige
uitvoering. Daar kan dus per constructie niets aan verschuiven.

## Dividend

De rekenkern kan het, maar er is nog niets aangesloten: de fiscale conventie
(bruto of netto, en welke percentages) is een beslissing die nog niet genomen
is. Zolang die er niet is:

- staat er op het dashboard expliciet dat de vergelijking **alleen koerswinst**
  is, bij beide kanten;
- geeft `bereken_herbalans()` het contante dividendgeld als een getal dat de
  aanroeper moet meegeven. Er wordt niets verzonnen;
- **stopt** `scripts/leg_herbalans_vast.py` wanneer er in de periode dividend
  is uitgekeerd terwijl de conventie niet meegegeven is. Dat is met opzet een
  harde stop: een wissel die stil 0 euro dividend meeneemt, is een wissel met
  een verkeerd bedrag, en die ligt daarna voor altijd vast.

Wat nog beslist moet worden staat in `CLAUDE.md` onder de openstaande punten.

## Wat reproduceerbaar blijft

Elke vastgelegde wissel bewaart in het gehashte deel:

- de aandelen met aantal en slotkoers waarmee de waarde vóór de wissel berekend
  is, plus die waarde zelf;
- het contante geld en waar het van kwam;
- de omzet, de kost en het bedrag dat opnieuw verdeeld is;
- de nieuwe posities met aantal en koers;
- de koers en waarde van SPY op diezelfde dag;
- de wisselkoers, de bron en het moment waarop die gelezen is.

Daarmee kan iemand die alleen de keten en onze vastgelegde dagkoersen heeft,
elke stap narekenen zonder ons te geloven.
