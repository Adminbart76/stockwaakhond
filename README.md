# StockWaakhond V7 — bevroren forward-test

V7 is geen nieuwe historische backtest.

Het doel is vanaf nu vooraf vastleggen wat StockWaakhond kiest en daarna meten wat werkelijk gebeurt.

## Bevroren strategie

De scoreformule is exact dezelfde als in V5/V6:

- 12m momentum: 25
- 6m momentum: 20
- 3m momentum: 15
- relatieve 6m sterkte versus SPY: 15
- koers boven MA200: 10
- MA50 boven MA200: 5
- lagere 3m volatiliteit: 5
- kleinere 3m drawdown: 5

Top-5.
Transactiekost: 0,15% per echte turnover.

De formule wordt als JSON geserialiseerd en met SHA-256 gehasht.
Elke forward-record bevat dezelfde strategiehash.

## Append-only ledger

Bij iedere selectie schrijft V7 een nieuwe regel naar:

    forward_log/ledger.jsonl

Elke regel bevat:
- UTC timestamp;
- signaaldatum;
- volledige Top-5;
- score per aandeel;
- signaalkoers;
- universum-hash;
- strategiehash;
- hash van de vorige regel;
- hash van de huidige regel.

Bij opstart controleert V7 de volledige hash-keten.
Als een oude regel handmatig is gewijzigd, weigert de app nieuwe records toe te voegen.

## Geen dagelijkse rebalancing

De Top-5 wordt gelijkgewogen bij een nieuwe selectie.
Daarna mogen de gewichten natuurlijk verschuiven.
Pas bij een volgend forward-signaal wordt opnieuw gelijkgewogen.

## Geen same-bar look-ahead

Het signaal gebruikt de laatste voltooide slotkoers.
Voor performance geldt pas de eerstvolgende beschikbare handelsdag als uitvoeringsdatum.

## Frequentie

Na een vastgelegd signaal staat een nieuwe selectie minstens 28 dagen op slot.
Dit is bewust eenvoudig en voorkomt dat we na enkele slechte dagen onmiddellijk een andere Top-5 kiezen.

## Actueel universum

V7 haalt bij iedere nieuwe scan de actuele S&P 500-samenstelling op van Wikipedia en bewaart een hash van dat universum in het forward-record.

## Starten

Open PowerShell in de uitgepakte map:

    py -m venv .venv
    .\.venv\Scripts\Activate.ps1
    python -m pip install -r requirements.txt
    python -m streamlit run app.py

## Belangrijk

Maak een backup van de map `forward_log`.
Dat is vanaf nu het bewijs van de forward-test.

V7 plaatst geen echte beursorders.
