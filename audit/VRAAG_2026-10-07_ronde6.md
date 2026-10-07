# Vraag aan de controleur — ronde 6, 7 oktober 2026

> **Beantwoord op 8 oktober 2026.** De controleur heeft dit pakket zelf
> gedraaid: 279 van de 279 tests slaagden, `app.py` en `ledger.jsonl` waren
> byte-identiek aan het bewijs, de bestaande hashes waren onaangeroerd en de
> Belgische laag bleek werkelijk afgeleid en zonder schrijfweg. Er kwamen zes
> gerichte correcties uit; ze zijn diezelfde dag uitgevoerd. Wat er veranderd
> is, staat in `CLAUDE.md` onder "Auditronde 6" en in `BELGIE.md`. De tekst
> hieronder blijft staan zoals ze voorgelegd is — alleen de status van ronde 5
> is bijgewerkt, want die klopte niet meer. Lees de vragen hieronder dus als de
> stand van 7 oktober, niet als de stand van nu.

Dit pakket is de volledige broncode van StockWaakhond V7.1. Het bevat geen
sleutels en geen wachtwoorden: alleen wat in de openbare GitHub-map staat
(`Adminbart76/stockwaakhond`). Het commitnummer en de datum staan in
`audit/PAKKET.txt`.

**Deze ronde gaat over één nieuw onderdeel: de Belgische laag.** Dat is een
afgeleide simulatie die naast de forward-test staat en die vraagt wat een
Belgische particulier zou overhouden als hij dezelfde trades werkelijk uitvoerde.
Ze rekent de beurstaks, de brokerkosten, de wisselkosten en de Belgische
belasting op dividend en op winst bij verkoop.

**Ronde 5 is intussen afgerond en groen bevonden** (bijgewerkt op 8 oktober
2026; bij het schrijven van deze vraag stond ze nog open). De controleur heeft
het pakket van ronde 5 zelf gedraaid: 232 van de 232 tests slaagden, de correctie
op het SPY-dividend op de ex-datum zat erin, en het verplichte wisselkoersbewijs
voor toekomstige herbalansen ook. Er zijn geen nieuwe bevindingen uit gekomen en
er is niets aan die code gewijzigd. De Belgische laag hieronder raakt geen van
beide onderwerpen: ze is nieuw, ze schrijft nergens en ze gebruikt de bestaande
dividend- en wisselkoersregels zoals ze zijn.

De vorige vragen (`audit/VRAAG_2026-10-07.md`, `..._ronde3.md`, `..._ronde4.md`,
`..._ronde5.md`) zijn niet gewijzigd.

Zeg het hard als iets zwakker is dan hieronder beweerd wordt. En lees paragraaf 6
voor je begint: **het grootste deel van deze laag is nog nooit op echte gegevens
gedraaid**, en dat is geen detail.

---

## 1. De grens die niet overschreden mocht worden

| wat | hoort te zijn |
|---|---|
| `strategy_hash` in `forward_log/ledger.jsonl` | `a399aecc207510c77450cd015f4f23e2b3639fc642eb9bcc29e95cbe2b84cc18` |
| `entry_hash` van het enige signaal | `0426e47ccd6e0b4f7fcecd772ce21dc5778db862e359f5eb4d239f5ce8bd5d15` |
| `universe_hash` | `3114cc28ea6cb1aa0b1025f7ee01fffa9c697244cf64ca20cf013a1c8f9e813b` |
| `exec_hash` in `forward_log/executions.jsonl` | `3468930ea4971945c8e8dad57b2cc797f9c825508368eff6bef5038090d3dae7` |
| `app.py` | byte-identiek aan `bewijs/app.py.bevroren-2026-10-06` |
| `forward_log/ledger.jsonl` | byte-identiek aan `bewijs/ledger.jsonl` |

In deze ronde zijn **niet aangeraakt**: `app.py`, `sw/strategy.py`,
`sw/herbalans.py`, `sw/portfolio.py`, `sw/dividend.py`, `sw/fx.py`,
`sw/realistisch.py`, `forward_log/`, `bewijs/`, alle vijf de `sql/`-bestanden,
alle bestaande tests, en alle scripts.

Nieuw: `sw/belgie.py`, `tests/test_belgie.py`, `BELGIE.md`,
`audit/ONTWERP_belgische_laag_2026-10-07.md`.
Gewijzigd: `streamlit_app.py` (een blok erbij, en twee opmaakfuncties die
"-€ 0,00" nu als nul tonen), `sw/__init__.py` (één regel in de opsomming),
`CLAUDE.md`, `AGENTS.md`, `README.md`, `ONDERZOEK.md`.

**Er is geen enkel record van vorm veranderd.** De Belgische laag raakt
`bereken_instap()` en `bereken_herbalans()` niet aan; ze leest hun uitkomst en
rekent er iets naast. Er is dus ook niets dat daardoor van hash kan veranderen.

---

## 2. Wat deze laag is, en vooral wat ze niet is

Er zijn nu drie berekeningen:

| | wat het meet | waar |
|---|---|---|
| **A** | de bevroren forward-test, zoals vastgelegd | `app.py`, `sw/strategy.py`, `sw/herbalans.py` |
| **B** | dezelfde trades, kost over de werkelijk verhandelde notional | `sw/realistisch.py` |
| **C** | dezelfde trades, plus Belgische taks, kosten en belasting | `sw/belgie.py` |

A blijft de primaire reeks en wordt nooit herrekend. C is afgeleid en wordt elke
keer opnieuw uit de vastgelegde gegevens gerekend.

**De bewering is dat C per constructie niet kan terugschrijven.** In
`sw/belgie.py` staat geen import van `supabase_io`, geen `open()`, geen
`sha256_text`. De stappen heten `belgie-1`, `belgie-2` — leesbare namen en geen
hashes, zodat ze niet op bewijsmateriaal lijken.

*Te onderzoeken:* klopt dat ook werkelijk? Grep op `import`, op `write`, op
`insert`. En: `tests/test_belgie.py::test_de_belgische_laag_verandert_de_officiele_records_niet`
en `..._de_officiele_curve_niet` beweren het, maar ze controleren alleen de
hashes, de canonieke tekst en het verloop-dataframe. Is er een weg waarlangs C
tóch iets aan A kan veranderen — een dict die gedeeld wordt in plaats van
gekopieerd, bijvoorbeeld? `_stap_record()` doet `dict(uitvoering["benchmark"])`,
maar dat is een ondiepe kopie.

---

## 3. Waar ik zelf zou aanvallen: het lusje dat de kosten zoekt

Dit is het enige echt ongewone stuk code in deze laag, en het verdient de meeste
aandacht.

**Waarom het er is.** De beurstaks wordt per order geheven, op het bedrag van
dat order. Deze laag kan dus niet met een gemiddeld kostenpercentage werken; ze
moet de werkelijke orders kennen. Maar de kosten bepalen hoeveel er te beleggen
valt, dat bepaalt de doelbedragen, die bepalen de orders, en de orders bepalen de
kosten. `_los_kosten_op()` rekent dat kringetje door tot het stilstaat.

**Wat eraan gesleuteld is om het te laten convergeren**, en dat zijn precies de
plekken waar een fout kan zitten:

1. **De lijst van aandelen die een order krijgen, wordt één keer vooraf bepaald
   en daarna vastgehouden.** Zonder dat springt een aandeel dat bijna op gewicht
   staat bij elke ronde over de drempel van één eurocent heen en weer, verandert
   de kost met een sprongetje, en komt de berekening nooit tot rust. Dat is geen
   theorie: het gebeurde, en het gaf een harde fout.

2. **Die lijst wordt bepaald ná een proefronde die de kosten schat**, niet op de
   waarde vóór de kosten. Een aandeel dat vóór de kosten precies op gewicht staat,
   krijgt door de kosten alsnog een order van ongeveer een vijfde van de kosten.
   Viel het daardoor buiten de lijst, dan werd er meer belegd dan er was. Ook dat
   gebeurde eerst, en het gaf een tekort van 1,09 dollar op 1.094 dollar.

3. **De marge op het stilstaan is 1e-6 dollar en niet kleiner.** De bedragen
   worden op acht cijfers afgerond, dus met 1e-9 kan de laatste ronde eeuwig een
   honderdmiljoenste heen en weer springen. Ook dat gebeurde.

*Te onderzoeken:*

- **Convergeert dit altijd?** De gedachte: met de orderlijst vastgezet is de kost
  een continue, stuksgewijs lineaire functie van K met een hellingsgetal van
  hoogstens het totale kostenpercentage (ongeveer 0,005), dus is het een
  samentrekking en convergeert het meetkundig. Klopt die redenering ook als het
  maximum per verrichting (1.600 euro) bijt, of als er een vaste brokerkost per
  order staat? Een vaste kost is een constante in K, dus zou niets aan de helling
  mogen doen — maar reken het na. `MAX_RONDES = 50` en daarna een harde fout.
- **Is de proefronde uit punt 2 altijd goed genoeg?** De lijst wordt bepaald met
  een kostenschatting K₀ die zelf uit K = 0 komt. Is er een geval waarin een
  order bij K₀ net onder de cent valt en bij de echte K er duidelijk boven ligt?
  Het verschil tussen K₀ en K is van de orde K maal het kostenpercentage, dus
  enkele duizendsten van een cent — maar dat is een redenering, geen test.
- **De marge op het geld.** Een aandeel zonder order blijft staan waar het staat
  en komt dus niet precies op zijn doelbedrag; dat verschil komt als contant geld
  terug. De controle laat daarom een tekort toe van
  `(aantal overgeslagen aandelen + 1) × 1 cent`. In ronde 6 is die marge
  aangescherpt — ze stond eerst op alle orders, en dan was ze bij een volledige
  wissel ruim genoeg om een echte rekenfout van tien cent te verbergen. Is de
  nieuwe vorm strak genoeg, en is er een wissel waarbij ze onterecht toeslaat?
- **De drempel van één eurocent zelf.** Ze bestaat om te voorkomen dat een vaste
  brokerkost op een order van niets komt te staan. Zolang er geen broker is, is
  ze alleen maar een bron van kleine afwijkingen. Is dat de juiste afweging, of
  hoort de drempel pas te bestaan zodra er een vaste kost is?

---

## 4. Twee bedragen die ik niet kan bevestigen, en graag door jou gecontroleerd zie

Dit is geen rhetorische vraag. **Ik denk dat één van de twee fout is.**

**De vrijgestelde schijf van de meerwaardebelasting.** De opdracht gaf
**4.855 euro** per belastingplichtige per jaar. Publieke bronnen die op
7 oktober 2026 zijn nagekeken, noemen **10.000 euro per jaar per persoon,
jaarlijks geïndexeerd**, met voor gehuwden en wettelijk samenwonenden het
dubbele. Het bedrag staat op 4.855 zoals opgedragen, met de status *te
bevestigen* in `HERKOMST` in `sw/belgie.py`, in de tabel op het dashboard en in
`BELGIE.md`. Staat het te laag, dan staat de geraamde belasting te hoog.

**De dividendvrijstelling.** De opdracht gaf **833 euro**. Dat is het bedrag voor
inkomstenjaar 2025 (aanslagjaar 2026); voor inkomstenjaar 2026 noemen bronnen
**859 euro**. De forward-test loopt in inkomstenjaar 2026.

*Te onderzoeken:* wat zijn de juiste bedragen voor inkomstenjaar 2026, met een
bron die een lezer zelf kan narekenen? En: is er iets aan de opbouw dat het lastig
maakt om ze te wijzigen? De bedoeling is dat een correctie een nieuwe
regelversie krijgt (`BE_TAX_RULES_2026_V2`) in plaats van een stille aanpassing
van `BE_TAX_RULES_2026_V1` — zodat een cijfer dat vandaag getoond is, morgen niet
stilletjes iets anders betekent.

---

## 5. Keuzes die verdedigbaar zijn maar niet de enige lezing

Noem het als je vindt dat een van deze anders hoort.

**De volgorde van de twee heffingen op dividend.** De Verenigde Staten houden
15 % in; België heft 30 % op wat overblijft (het netto grensbedrag), niet op het
brutobedrag. Van 100 euro blijft zo 59,50 over. Zou stap 2 op bruto staan, dan
werd de Amerikaanse heffing een tweede keer belast.

**Hoeveel van de dividendvrijstelling er teruggevraagd kan worden.** De schijf
wordt opgebruikt door het **bruto** dividend, en wat er terugkomt is de Belgische
voorheffing die op het vrijgestelde deel geheven is — dus
`voorheffing × (vrijgesteld deel / bruto)`, en niet 30 % van de schijf. Reden: op
een buitenlands dividend is er minder dan 30 % van bruto ingehouden, en meer
terugvragen dan er ingehouden is, kan niet. Een andere lezing is dat de schijf
door het netto grensbedrag opgebruikt wordt. Welke klopt?

**Dat de terugvordering niet in de portefeuillewaarde zit.** De vrijstelling
werkt niet aan de bron: de voorheffing wordt altijd ingehouden en je vraagt ze
terug met je aangifte. Ze staat daarom apart op het scherm als "nog terug te
vragen".

**De meerwaarde wordt in euro gerekend**, met kostprijs en opbrengst tegen de
wisselkoers van hun eigen dag, zodat het wisselkoerseffect in de meerwaarde zit.

**Twee verschillende wisselkoersen binnen dezelfde laag.** Een order gebruikt de
`fx_rate` van het uitvoeringsrecord zelf (die staat in de gehashte tekst). Een
dividend gebruikt de dagreeks uit `fx_snapshots` op de betaaldag, met als terugval
de `fx_rate` van de uitvoering die op die dag gold. Dat is met opzet — een
betaaldag valt zelden op een uitvoeringsdag — maar het zijn wel twee bronnen in
één berekening.

**De transactiekost van 0,15 % blijft meelopen** en staat op de plaats van de
brokerkosten zolang er geen broker gekozen is. Wordt er later een broker
ingevuld, dan hoort `basiskost_pct` op 0 te gaan, anders wordt dezelfde kost twee
keer gerekend. Dat staat in `BELGIE.md` en in de uitleg bij de parameter, maar er
is **geen test en geen wachter** die het afdwingt. Hoort die er te zijn?

**Transactiekosten tellen niet mee in de meerwaardebasis**
(`kosten_in_meerwaardebasis = False`). Aanname, nog na te gaan.

**SPY betaalt in deze laag niets en krijgt niets.** Hij zit niet in de Belgische
portefeuille: een Belgische particulier belegt de 1.000 euro in de vijf aandelen,
niet in de maatstaf. De Belgische curve laat de maatstafkolommen daarom helemaal
weg (`spy_eur`, `spy_resultaat_pct`, `voorsprong_pct`), zodat niemand ze alsnog
als benchmark leest. Reden: een Amerikaanse ETF heeft voor een Europese
particulier meestal geen KID, waardoor hij er bij veel brokers niet rechtstreeks
in kan. SPY blijft onveranderd de maatstaf van het ONDERZOEK.

*Te onderzoeken:* is dat weglaten de juiste keuze, of verliest de Belgische curve
daardoor juist haar ijkpunt? En klopt de PRIIPs-redenering, of is ze te stellig?

---

## 6. Eerlijk gezegd: bijna niets hiervan is op echte gegevens gedraaid

Dit is het zwakste punt van deze ronde, en het hoort vooraan te staan.

Er is **één** uitvoering (de instap van 6 oktober 2026), **geen** wissel en
**geen** dividend. Wat er dus werkelijk met echte gegevens gerekend wordt, is
alleen dit:

```
1.000 euro / 1,005 = 995,0249 belegd
beurstaks  0,35 % x 995,0249 = 3,4826
basiskost  0,15 % x 995,0249 = 1,4925
samen                           4,9751
```

Dat is met de hand na te rekenen en staat zo op het dashboard.

**Al de rest — de rotatie, de orders per aandeel, FIFO, de gerealiseerde winst,
de dividendbelasting, de vrijstellingen — bestaat op dit moment alleen in
`tests/test_belgie.py`.** Dat zijn 47 tests, waarvan de fiscale regels los
getest worden met bedragen die groot genoeg zijn om de vrijstellingen te raken
(met 1.000 euro kom je nooit aan een meerwaarde van 4.855 euro).

Het dashboard is wel in een nagebootste toestand bekeken — een tweede wissel met
koersverloop en twee dividenden — maar dat was een visuele controle, geen bewijs.

*Te onderzoeken:* dekken die tests de gevallen die er werkelijk toe doen? Bij
het schrijven van deze vraag bleken er vier te ontbreken; die zijn toegevoegd
voor het pakket de deur uitging, en ze slaagden alle vier meteen:

| test | wat het geval is |
|---|---|
| `test_fifo_over_twee_pakketjes_binnen_de_keten` | een aandeel blijft staan, wordt bijgekocht tegen een andere prijs en gaat er later uit; de verkoop raakt allebei de pakketjes, het oudste eerst |
| `test_een_verlies_van_het_ene_jaar_verrekent_niet_met_winst_van_het_andere` | een wissel in december en een in januari; het verlies van 2027 mag de winst van 2026 niet verlagen |
| `test_dividendgeld_dat_meebelegd_wordt_betaalt_maar_een_keer_beurstaks` | contant dividend gaat alleen in de koopkant, dus betaalt het niet twee keer taks |
| `test_dividend_van_een_verkocht_aandeel_komt_toch_binnen` | ex-datum vóór de wissel, betaaldatum erna, aandeel intussen verkocht |

Dat ze meteen slaagden is geen bewijs dat ze overbodig waren: zonder die tests
kon elk van die vier gevallen stilletjes kapot gaan bij een volgende wijziging.
Maar het zegt ook iets anders — zoek liever naar het geval dat ik **niet**
bedacht heb.

---

## 7. Hoe je dit pakket kunt narekenen

```
python -m pytest              # 279 tests
```

De vier hashes uit paragraaf 1 zijn na te rekenen uit `forward_log/` zelf.

De Belgische laag heeft geen database nodig en geen internet: geef
`belgische_keten()` een lijst uitvoeringen, eventueel dividendrijen en eventueel
een wisselkoersreeks, en ze rekent alles opnieuw. Er is geen staat die
meeschuift; `tests/test_belgie.py::test_de_belgische_keten_is_elke_keer_hetzelfde`
legt dat vast.

De uitleg van de regels, met per regel de bron en of het exact is, een aanname,
nog te bevestigen of nog niet ingesteld, staat in `BELGIE.md`. De architectuur en
de redenering staan in `audit/ONTWERP_belgische_laag_2026-10-07.md`.

Aan de database is in deze ronde niets veranderd, dus
`scripts/controleer_slot.py` geeft onveranderd 61 van 61 goed met
`deur_versie 5`; die uitvoer staat in `audit/aanvalstest_2026-10-07_ronde5.txt`.
