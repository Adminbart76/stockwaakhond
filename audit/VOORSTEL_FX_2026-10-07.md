# Voorstel: een wisselkoers die niet van de klik afhangt

Punt 5 van auditronde 2. **Dit is een voorstel. Er is niets geïmplementeerd en
niets gewijzigd.** De uitvoering van 6 oktober 2026 blijft hoe dan ook exact
zoals ze is.

## Het probleem

Vandaag leest `scripts/leg_instap_vast.py` de dagbalk van `EURUSD=X` op het
moment dat Bart op het BAT-bestand klikt. Binnen het toegestane venster
(22.20–01.00 bij ons) beweegt die balk gewoon mee met de markt: om 22.54 stond
er 1,126253, twee uur later 1,126380. Twee mensen die dezelfde avond dezelfde
handeling doen, krijgen dus een ander getal. Voor het eerste signaal is dat
vastgelegd en narekenbaar, maar als regel voor de toekomst is het te slap.

Waarom het niet simpelweg op te lossen is met "neem de slotkoers": die bestaat
niet bij deze bron. De dagbalk van `EURUSD=X` klikt nooit vast. Zolang de
valutadag loopt volgt hij de koers van nu; is die dag voorbij, dan rapporteert
Yahoo voor diezelfde datum een ander getal (gemeten: 0,3 % verschil).

## Voorstel

**De wisselkoers is de 1-minuutbalk van `EURUSD=X` van 16:00 in New York op de
uitvoeringsdag — exact de minuut van de slotbel.**

| | |
|---|---|
| bron | Yahoo Finance, `EURUSD=X`, interval 1 minuut |
| moment | de balk met tijdstempel 16:00 America/New_York |
| ontbreekt die balk | de eerste balk daarna, binnen 15 minuten |
| ontbreekt die ook | stoppen, en een mens kijkt ernaar |
| `fx_asof` | het tijdstempel van de balk zelf, niet het moment van lezen |
| `fx_source` | "Yahoo Finance EURUSD=X 1-minuutbalk 16:00 America/New_York" |

### Waarom dit werkt

- **Deterministisch.** De balk heeft een tijdstempel en verandert niet meer.
  Wie om 22.30 kijkt en wie om 00.30 kijkt, krijgt hetzelfde getal.
- **Hij hoort bij dezelfde seconde als de slotkoersen.** Dat was juist de reden
  om de ECB-koers af te wijzen: die ligt zes uur eerder.
- **Het past in het bestaande slot zonder één regel SQL te wijzigen.** De
  database eist dat `fx_asof` tussen de slotbel en acht uur erna ligt. Een balk
  van precies 16:00 ligt op de slotbel.
- **Elk record zegt zelf welke regel het gebruikte.** `fx_source` staat in de
  gehashte tekst. De uitvoering van 6 oktober blijft dus leesbaar als
  "dagbalk, gelezen om 20:54 UTC", en een latere uitvoering als "1-minuutbalk
  van de slotbel". Er wordt niets herschreven.

### De zwakke plek, eerlijk benoemd

Yahoo bewaart 1-minuutgegevens ongeveer dertig dagen. Een controleur die er een
jaar later naar kijkt, kan die balk niet meer ophalen. Daarom hoort er bij dit
voorstel:

1. de balk (tijdstempel én koers) gaat in het gehashte record en in
   `fx_snapshots`, dus wij bewaren hem wel;
2. dezelfde avond wordt een **tweede, onafhankelijke koers** vastgelegd als
   controlegetal: de ECB-referentiekoers van die dag (gratis, permanent
   opvraagbaar, door iedereen na te kijken);
3. wijken die twee meer dan 1 % af, dan stopt het script. Dat is geen normale
   marktbeweging maar een fout in de gegevens.

Zo is de koers deterministisch én blijft er voor altijd een onafhankelijk spoor
waarmee een buitenstaander kan controleren dat er geen gunstig getal gekozen is.

### Wat er niet voorgesteld wordt

- **De ECB-koers als hoofdkoers.** Zes uur verschil met de slotkoersen; dat is
  op een volatiele dag echt geld. Blijft de controle, niet de bron.
- **De dagbalk de volgende dag lezen.** Dat is óók deterministisch, maar het
  getal hoort dan bij het begin van de dag in plaats van bij de slotbel (0,3 %
  verschil, gemeten), en het haalt de hele handeling buiten het venster waarin
  de slotkoersen vastliggen.

## Wat er moet gebeuren als dit goedgekeurd wordt

1. `sw/prices.py` krijgt één functie die de minuutbalk ophaalt en weigert te
   raden.
2. `scripts/leg_herbalans_vast.py` en `scripts/leg_instap_vast.py` gebruiken
   die, en leggen de ECB-koers als controlegetal mee vast.
3. De afspraak komt in `CLAUDE.md` bij de vastliggende beslissingen, met de
   datum vanaf wanneer ze geldt.

Geschatte omvang: een halve avond, geen wijziging aan de database en geen
wijziging aan iets dat al vastligt.
