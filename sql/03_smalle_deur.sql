-- ===========================================================================
-- StockWaakhond V7.1 - ronde 3: een smallere deur en een doorlopende keten
-- ===========================================================================
--
-- Plak dit volledige bestand in de Supabase SQL Editor en klik op Run.
-- Het mag meerdere keren uitgevoerd worden en verandert geen enkele bestaande
-- rij: alles hieronder zijn regels die gelden bij het TOEVOEGEN van iets
-- nieuws, plus kolommen die voor bestaande rijen leeg blijven.
--
-- Draai eerst sql/01_schema.sql en sql/02_hardening.sql.
--
-- LET OP, DE VOLGORDE DOET ERTOE
-- ==============================
-- Dit bestand vervangt twee functies uit 02_hardening.sql door een strengere
-- versie. Voer je 02 ooit opnieuw uit, voer dan daarna ook dit bestand weer
-- uit. Je ziet het meteen: hardening_status() geeft dan geen deur_versie 3
-- meer terug en scripts/controleer_slot.py slaat alarm.
--
-- Wat dit bestand toevoegt
-- ========================
--   A. De keten van uitvoeringen. Tot nu toe kon er per signaal een instap
--      vastgelegd worden, maar niets verbond die instappen met elkaar. Een
--      doorlopende portefeuille van 1.000 euro heeft precies dat nodig: elke
--      wissel hangt aan de vorige, en er kan er maar een aan hangen.
--   B. Een veel smallere schrijfdeur voor de dagelijkse taak op GitHub:
--      alleen de afgesloten beursdag van vandaag, alleen de aandelen die NU in
--      de portefeuille zitten, allemaal samen of geen enkele, en met de
--      wisselkoers erbij zolang die opgehaald kan worden.
--   C. Een leesbare vraag vooraf: mag deze dag, met deze lijst, nu?
--   D. Een statuscontrole die ook kijkt of de wachters AANSTAAN, en die
--      eerlijk vertelt wat ze niet kunnen.
-- ===========================================================================


-- ===========================================================================
-- A. DE KETEN VAN UITVOERINGEN
-- ===========================================================================
-- Er wordt een keer 1.000 euro ingelegd. Daarna verandert alleen de verdeling.
-- Dat betekent dat elke uitvoering de vorige nodig heeft: zonder die schakel
-- zou elke maand opnieuw met vers geld begonnen worden, en dan meet de reeks
-- niets meer.
--
-- De velden hieronder zijn leeg voor de instap van 6 oktober 2026. Dat hoort
-- zo: die is de eerste schakel en heeft geen voorganger.

alter table public.executions
  add column if not exists record_type     text,
  add column if not exists prev_exec_hash  text,
  add column if not exists turnover        numeric,
  add column if not exists cost_usd        numeric,
  add column if not exists invested_usd    numeric,
  add column if not exists cash_usd        numeric,
  add column if not exists opening         jsonb;

comment on column public.executions.prev_exec_hash is
  'Het controlegetal van de vorige uitvoering. Leeg bij de eerste instap.';
comment on column public.executions.opening is
  'De portefeuille vlak voor de wissel: aantallen, slotkoersen, contant geld.';
comment on column public.executions.turnover is
  'Hoeveel van de portefeuille van hand verwisselde (1,0 = alles).';

-- Een voorganger kan maar een opvolger hebben. Dit is de regel die een tweede
-- keten naast de echte onmogelijk maakt, en ze staat in de index zelf en niet
-- in een functie die iemand kan vervangen.
create unique index if not exists executions_een_opvolger
  on public.executions (prev_exec_hash)
  where prev_exec_hash is not null;


create or replace function public.controleer_uitvoering()
returns trigger
language plpgsql
as $$
declare
  inhoud        jsonb := new.canonical_payload::jsonb;
  signaaldatum  date;
  slotbel       timestamptz;
  punt_hash     text;
  punt_datum    date;
  heeft_punt    boolean := false;
  laatste_seq   bigint;
  signaal_seq   bigint;
begin
  -- ---------------------------------------------------------------- 02: fx
  if inhoud->>'fx_source' is distinct from new.fx_source
     or (inhoud->>'fx_asof')::timestamptz is distinct from new.fx_asof
  then
    raise exception 'fx_source of fx_asof in de kolommen komt niet overeen met de gehashte inhoud.'
      using hint = 'Alleen de gehashte tekst telt als bewijs.';
  end if;

  select s.signal_market_date into signaaldatum
  from public.signals s where s.entry_hash = new.entry_hash;

  if found then
    if new.execution_date <= signaaldatum then
      raise exception 'Er wordt ingestapt na de signaaldag: % is niet later dan %.',
        new.execution_date, signaaldatum
        using hint =
          'Instappen tegen een koers die bij het kiezen al bekend was, is '
          'jezelf rijk rekenen met informatie die je toen niet had.';
    end if;
  end if;

  slotbel := (new.execution_date::text || ' 16:00')::timestamp
             at time zone 'America/New_York';

  if new.fx_asof < slotbel or new.fx_asof >= slotbel + interval '8 hours' then
    raise exception 'fx_asof (%) hoort niet bij de slotbel van % (%).',
      new.fx_asof, new.execution_date, slotbel
      using hint =
        'Een wisselkoers wordt vastgelegd op de instapdag zelf, na de slotbel '
        'in New York. Daarbuiten rapporteert Yahoo voor die datum een ander getal.';
  end if;

  -- ------------------------------------------------------- 03: de keten
  -- Onder slot, net als bij de signalen: zonder dat kunnen twee gelijktijdige
  -- pogingen allebei dezelfde voorganger zien en twee ketens bouwen.
  perform pg_advisory_xact_lock(7701202610052);

  select e.exec_hash, e.execution_date into punt_hash, punt_datum
  from public.executions e
  where not exists (
    select 1 from public.executions x where x.prev_exec_hash = e.exec_hash)
  order by e.execution_date desc
  limit 1;
  heeft_punt := found;

  if new.prev_exec_hash is null then
    if heeft_punt then
      raise exception 'Er staat al een uitvoering; deze hoort naar de vorige te verwijzen.'
        using hint =
          'Er wordt een keer 1.000 euro ingelegd. Een tweede uitvoering zonder '
          'voorganger zou opnieuw met vers geld beginnen.';
    end if;
  else
    if not heeft_punt then
      raise exception 'Deze uitvoering verwijst naar een voorganger, maar er staat er geen.';
    end if;
    if new.prev_exec_hash is distinct from punt_hash then
      raise exception 'Deze uitvoering verwijst niet naar de laatste uitvoering.'
        using detail = format('verwacht: %s, opgegeven: %s', punt_hash, new.prev_exec_hash),
              hint = 'Alleen de echte keten mag verlengd worden, geen tweede keten ernaast.';
    end if;
    if new.execution_date <= punt_datum then
      raise exception 'De wissel van % ligt niet na de vorige uitvoering van %.',
        new.execution_date, punt_datum;
    end if;

    -- Een wissel hoort bij het nieuwste signaal. Anders zou een oude selectie
    -- maanden later nog uitgevoerd kunnen worden.
    select max(s.seq) into laatste_seq from public.signals s;
    select s.seq into signaal_seq from public.signals s where s.entry_hash = new.entry_hash;
    if signaal_seq is null or signaal_seq is distinct from laatste_seq then
      raise exception 'Een wissel hoort bij het laatste signaal (volgnummer %), niet bij %.',
        laatste_seq, coalesce(signaal_seq, -1);
    end if;
  end if;

  -- De nieuwe kolommen moeten zeggen wat er in de gehashte tekst staat. Zonder
  -- deze controle kon de kolom iets anders beweren dan het bewijs.
  if inhoud ? 'prev_exec_hash' or new.prev_exec_hash is not null then
    if inhoud->>'prev_exec_hash'            is distinct from new.prev_exec_hash
       or inhoud->>'record_type'            is distinct from new.record_type
       or (inhoud->>'turnover')::numeric    is distinct from new.turnover
       or (inhoud->>'cost_usd')::numeric    is distinct from new.cost_usd
       or (inhoud->>'invested_usd')::numeric is distinct from new.invested_usd
       or (inhoud->>'cash_usd')::numeric    is distinct from new.cash_usd
       or inhoud->'opening'                 is distinct from new.opening
    then
      raise exception 'De kolommen van deze wissel komen niet overeen met de gehashte inhoud.'
        using hint = 'Alleen de gehashte tekst telt als bewijs.';
    end if;

    -- Narekenen dat er geen geld is bijgekomen: wat erin gaat is wat er was,
    -- min de kost. Een cent verschil is al een ander verhaal.
    if abs((new.opening->>'total_usd')::numeric - new.cost_usd - new.invested_usd) > 0.01
    then
      raise exception 'De waarde voor de wissel (%) min de kost (%) is niet het belegde bedrag (%).',
        new.opening->>'total_usd', new.cost_usd, new.invested_usd
        using hint = 'Er mag bij een wissel geen geld bijkomen of verdwijnen.';
    end if;
  end if;

  return new;
end;
$$;

comment on function public.controleer_uitvoering() is
  'Rekent de wisselkoers, de instapdag en de keten van een uitvoering na.';

drop trigger if exists velden_moeten_kloppen on public.executions;
create trigger velden_moeten_kloppen
  before insert on public.executions
  for each row execute function public.controleer_uitvoering();


-- ===========================================================================
-- B. WELKE AANDELEN ZITTEN ER NU IN DE PORTEFEUILLE?
-- ===========================================================================
-- Tot nu toe mocht de dagelijkse taak koersen bijschrijven van alles wat ooit
-- gekozen was. Dat wordt elke maand een langere lijst, en een aandeel dat
-- vorige maand verkocht is, hoort niets meer te mogen.
--
-- Deze functie kijkt naar de ACTUELE uitvoering: de posities die er nu zijn,
-- plus de maatstaf. Staat er nog geen enkele uitvoering, dan is er ook nog
-- geen portefeuille, en wordt teruggevallen op het laatste signaal plus SPY,
-- zodat de eerste dagen al koersen kunnen worden vastgelegd.

create or replace function public.actieve_tickers()
returns text[]
language plpgsql
stable
security definer
set search_path = public, pg_temp
as $$
declare
  punt    record;
  lijst   text[] := array[]::text[];
begin
  select e.positions, e.benchmark into punt
  from public.executions e
  where not exists (
    select 1 from public.executions x where x.prev_exec_hash = e.exec_hash)
  order by e.execution_date desc
  limit 1;

  if found then
    select array_agg(distinct p.ticker order by p.ticker) into lijst
    from jsonb_to_recordset(punt.positions) as p(ticker text);
    lijst := coalesce(lijst, array[]::text[]);
    if punt.benchmark->>'ticker' is not null
       and not (punt.benchmark->>'ticker' = any(lijst)) then
      lijst := lijst || array[punt.benchmark->>'ticker'];
    end if;
    return lijst;
  end if;

  select array_agg(distinct x.ticker order by x.ticker) into lijst
  from (select s.selected from public.signals s order by s.seq desc limit 1) laatste,
       jsonb_to_recordset(laatste.selected) as x(ticker text);
  lijst := coalesce(lijst, array[]::text[]);
  if not ('SPY' = any(lijst)) then
    lijst := lijst || array['SPY'];
  end if;
  return lijst;
end;
$$;

comment on function public.actieve_tickers() is
  'De aandelen die nu in de portefeuille zitten, plus de maatstaf.';

revoke all on function public.actieve_tickers() from public;
grant execute on function public.actieve_tickers() to anon, authenticated;


-- ===========================================================================
-- C. MAG DEZE DAG, MET DEZE LIJST, NU?
-- ===========================================================================
-- Dezelfde regels als de schrijfdeur hieronder, maar leesbaar en zonder iets
-- te schrijven. Zo kan het aanvalsscript de deur op elk moment bevragen, ook
-- voor een tijdstip dat nu niet is - en dat is de enige manier om de regel
-- "nooit voor de slotbel" te testen zonder op de klok te wachten.
--
-- p_nu bestaat alleen hier. De schrijfdeur gebruikt altijd de echte klok.

-- p_tickers en p_fx mogen leeg blijven. Geef je ze mee, dan vertelt de functie
-- er ook over: zou deze lijst compleet genoeg zijn, en is deze wisselkoers een
-- koers? Dat is nodig omdat die twee regels in de schrijfdeur alleen bereikt
-- worden als al het andere klopt - en dan zou een aanvalstest die per ongeluk
-- slaagt een echte dag met verzonnen cijfers achterlaten. Dit is dezelfde vraag
-- stellen zonder dat risico.

create or replace function public.mag_dagkoers_vastleggen(
  p_datum   date,
  p_nu      timestamptz default now(),
  p_tickers text[] default null,
  p_fx      numeric default null
)
returns jsonb
language plpgsql
stable
security definer
set search_path = public, pg_temp
as $$
declare
  beursdag      date        := (p_nu at time zone 'America/New_York')::date;
  slotbel       timestamptz := (p_datum::text || ' 16:00')::timestamp
                               at time zone 'America/New_York';
  vrijgave      timestamptz := slotbel + interval '20 minutes';
  londen_morgen timestamptz := ((p_datum + 1)::text || ' 00:00')::timestamp
                               at time zone 'Europe/London';
  is_vandaag    boolean := p_datum = beursdag;
  na_slot       boolean := p_nu >= vrijgave;
  is_weekdag    boolean := extract(isodow from p_datum) between 1 and 5;
  toegestaan    text[]  := public.actieve_tickers();
  ontbreekt     text[];
begin
  if p_tickers is not null then
    select coalesce(array_agg(t), array[]::text[]) into ontbreekt
    from unnest(toegestaan) as t
    where not (t = any(p_tickers));
  end if;

  return jsonb_build_object(
    'datum', p_datum,
    'beursdag_in_new_york', beursdag,
    'is_de_dag_van_nu', is_vandaag,
    'na_de_slotbel_plus_marge', na_slot,
    'vrijgave', vrijgave,
    'is_een_weekdag', is_weekdag,
    'wisselkoers_venster_open', p_nu < londen_morgen,
    'toegestane_tickers', to_jsonb(toegestaan),
    'bron_van_de_lijst', case
      when exists (select 1 from public.executions) then 'de actuele uitvoering'
      else 'het laatste signaal, want er is nog geen uitvoering' end,
    'lijst_is_compleet', case
      when p_tickers is null then null
      else array_length(ontbreekt, 1) is null end,
    'ontbreekt_in_de_lijst', case
      when p_tickers is null then null
      else to_jsonb(coalesce(ontbreekt, array[]::text[])) end,
    'wisselkoers_bruikbaar', case
      when p_fx is null then null
      else p_fx > 0.5 and p_fx < 2.0 end,
    'mag', (is_vandaag and na_slot and is_weekdag)
  );
end;
$$;

comment on function public.mag_dagkoers_vastleggen(date, timestamptz, text[], numeric) is
  'Vertelt of de smalle schrijfdeur deze dag nu zou toelaten. Schrijft niets.';

revoke all on function public.mag_dagkoers_vastleggen(date, timestamptz, text[], numeric)
  from public;
grant execute on function public.mag_dagkoers_vastleggen(date, timestamptz, text[], numeric)
  to anon, authenticated;


-- ===========================================================================
-- D. DE SMALLE SCHRIJFDEUR, NU VEEL SMALLER
-- ===========================================================================
-- Wat er veranderd is tegenover 02_hardening.sql:
--
--   was                                   wordt
--   ------------------------------------  ------------------------------------
--   elke datum tot en met vandaag         alleen de beursdag van nu
--   ook voor de slotbel                   pas 20 minuten na de slotbel
--   ook in het weekend                    alleen maandag tot vrijdag
--   alles wat ooit gekozen is             alleen de huidige portefeuille
--   een of meer koersen                   alle actieve aandelen, of geen enkele
--   wisselkoers optioneel                 verplicht zolang hij op te halen is
--
-- Waarom "alles of niets": een dag met vier van de zes koersen is niet meer
-- te herstellen (toevoegen kan wel, maar de dag is dan al als gedaan geboekt)
-- en levert een grafiek met een gat die niemand opmerkt.
--
-- Waarom de wisselkoers verplicht is zolang het venster open staat: zonder
-- wisselkoers is er voor die dag geen bedrag in euro. Is het venster voorbij
-- (na middernacht in Londen), dan geeft Yahoo voor die datum een ander getal
-- terug en mag de koers juist NIET meer vastgelegd worden; dan komen de
-- slotkoersen er wel in en slaat de taak zelf alarm.
--
-- Een historische dag herstellen kan hiermee dus niet meer, en dat is de
-- bedoeling. Daarvoor is er een aparte beheerdersprocedure met de geheime
-- sleutel: scripts/herstel_dagkoers.py. Die staat niet in GitHub.

create or replace function public.leg_dagkoersen_vast(
  p_token   text,
  p_datum   date,
  p_koersen jsonb,
  p_fx      jsonb default null,
  p_live    jsonb default null
)
returns jsonb
language plpgsql
security definer
set search_path = public, privaat, pg_temp
as $$
declare
  toegestaan    text[];
  aangeleverd   text[];
  ontbreekt     text[];
  onbekend      text[];
  rec           jsonb;
  nieuw         integer := 0;
  overgeslagen  integer := 0;
  fx_nieuw      integer := 0;
  live_bij      integer := 0;
  nu            timestamptz := now();
  beursdag      date := (nu at time zone 'America/New_York')::date;
  slotbel       timestamptz;
  londen_morgen timestamptz;
begin
  -- 1. Het schrijfteken
  if p_token is null or length(p_token) < 32 then
    raise exception 'Geen geldig schrijfteken meegegeven.'
      using hint = 'Zet SNAPSHOT_WRITE_TOKEN in de omgeving van de taak.';
  end if;

  if not exists (
    select 1 from privaat.snapshot_sleutels
    where actief and token_hash = public.sha256_hex(p_token)
  ) then
    raise exception 'Het schrijfteken voor dagkoersen klopt niet.'
      using hint = 'Dit teken geeft alleen recht op koersen, en dit is het niet.';
  end if;

  -- 2. De dag: alleen de beursdag die nu in New York loopt, en pas als die
  --    echt afgesloten is. Een oudere dag bijschrijven kan hier niet meer.
  if p_datum is null then
    raise exception 'Geef de dag mee waarvoor de koersen gelden.';
  end if;

  if p_datum <> beursdag then
    raise exception 'Alleen de beursdag van nu mag vastgelegd worden: % (opgegeven: %).',
      beursdag, p_datum
      using hint =
        'Deze deur is er voor de dagelijkse taak. Een oudere dag herstellen is '
        'een beheerdershandeling met de geheime sleutel, niet iets wat vanuit '
        'GitHub kan gebeuren.';
  end if;

  if extract(isodow from p_datum) > 5 then
    raise exception 'Op % (een weekenddag) is er geen slotkoers.', p_datum;
  end if;

  slotbel := (p_datum::text || ' 16:00')::timestamp at time zone 'America/New_York';
  if nu < slotbel + interval '20 minutes' then
    raise exception 'Te vroeg: de beurs van % sluit om % en de koers is pas 20 minuten later definitief.',
      p_datum, slotbel
      using hint =
        'Zolang er gehandeld wordt geeft Yahoo een voorlopige koers, en wat hier '
        'vastgelegd wordt kan nooit meer gewijzigd worden.';
  end if;

  -- 3. Welke aandelen mogen: de huidige portefeuille, niet de geschiedenis.
  toegestaan := public.actieve_tickers();
  if array_length(toegestaan, 1) is null then
    raise exception 'Er is nog geen portefeuille en nog geen signaal.';
  end if;

  select coalesce(array_agg(distinct x.ticker), array[]::text[]) into aangeleverd
  from jsonb_to_recordset(coalesce(p_koersen, '[]'::jsonb)) as x(ticker text);

  -- 4. Eerst: zit er niets bij dat er niet hoort? Deze vraag komt met opzet
  --    vóór de volgende, zodat een aandeel dat niet in de portefeuille zit
  --    altijd op zijn eigen reden strandt en nooit stilletjes meeglipt.
  select coalesce(array_agg(t), array[]::text[]) into onbekend
  from unnest(aangeleverd) as t
  where not (t = any(toegestaan));

  if array_length(onbekend, 1) is not null then
    raise exception 'Aandeel % zit niet in de huidige portefeuille.',
      array_to_string(onbekend, ', ')
      using hint =
        'Deze deur mag alleen koersen van de actieve posities en de maatstaf '
        'vastleggen, niet van alles wat ooit gekozen is.';
  end if;

  -- 5. En dan: alles of niets. Elke actieve ticker hoort erbij te zitten.
  select coalesce(array_agg(t), array[]::text[]) into ontbreekt
  from unnest(toegestaan) as t
  where not (t = any(aangeleverd));

  if array_length(ontbreekt, 1) is not null then
    raise exception 'Deze dag is niet compleet: % ontbreekt.', array_to_string(ontbreekt, ', ')
      using hint =
        'Een halve dag vastleggen geeft een gat in de geschiedenis dat niemand '
        'ziet. Liever niets, en de taak laten falen.';
  end if;

  -- 6. De slotkoersen. Bestaat er al een, dan blijft die staan.
  for rec in select * from jsonb_array_elements(coalesce(p_koersen, '[]'::jsonb))
  loop
    if not (rec->>'ticker' = any(toegestaan)) then
      raise exception 'Aandeel % zit niet in de huidige portefeuille.', rec->>'ticker'
        using hint =
          'Deze deur mag alleen koersen van de actieve posities en de maatstaf '
          'vastleggen, niet van alles wat ooit gekozen is.';
    end if;
    if rec->>'close_raw' is null or (rec->>'close_raw')::numeric <= 0 then
      raise exception 'Geen bruikbare slotkoers voor %.', rec->>'ticker';
    end if;

    insert into public.price_snapshots
      (snapshot_date, ticker, close_raw, close_adjusted, source)
    values
      (p_datum, rec->>'ticker',
       (rec->>'close_raw')::numeric,
       nullif(rec->>'close_adjusted', '')::numeric,
       coalesce(rec->>'source', 'Yahoo Finance dagslotkoers'))
    on conflict (snapshot_date, ticker) do nothing;

    if found then
      nieuw := nieuw + 1;
    else
      overgeslagen := overgeslagen + 1;
    end if;
  end loop;

  -- 7. De wisselkoers. Verplicht zolang hij bij deze handelsdag hoort.
  londen_morgen := ((p_datum + 1)::text || ' 00:00')::timestamp
                   at time zone 'Europe/London';

  if p_fx is null or p_fx->>'rate' is null then
    if nu < londen_morgen then
      raise exception 'De wisselkoers van % hoort erbij en ontbreekt.', p_datum
        using hint =
          'Zonder wisselkoers is er voor die dag geen bedrag in euro. Probeer '
          'het binnen hetzelfde venster opnieuw.';
    end if;
  else
    if coalesce(p_fx->>'pair', 'EURUSD') <> 'EURUSD' then
      raise exception 'Alleen de wisselkoers EURUSD hoort hier.';
    end if;
    if (p_fx->>'rate')::numeric <= 0 then
      raise exception 'Geen bruikbare wisselkoers.';
    end if;
    -- Een euro is sinds 1999 nooit minder dan 0,80 of meer dan 1,60 dollar
    -- geweest. Buiten die band is het geen koers maar een fout.
    if (p_fx->>'rate')::numeric < 0.5 or (p_fx->>'rate')::numeric > 2.0 then
      raise exception 'Een wisselkoers van % dollar voor een euro is geen koers.',
        p_fx->>'rate';
    end if;

    insert into public.fx_snapshots (snapshot_date, pair, rate, source)
    values (p_datum, 'EURUSD', (p_fx->>'rate')::numeric,
            coalesce(p_fx->>'source', 'Yahoo Finance EURUSD=X dagslotkoers'))
    on conflict (snapshot_date, pair) do nothing;

    if found then fx_nieuw := 1; end if;
  end if;

  -- 8. De koersen voor het scherm. Geen bewijsmateriaal, mag overschreven.
  for rec in select * from jsonb_array_elements(coalesce(p_live, '[]'::jsonb))
  loop
    if not (rec->>'ticker' = any(toegestaan)) then
      raise exception 'Aandeel % zit niet in de huidige portefeuille.', rec->>'ticker';
    end if;

    insert into public.live_quotes (ticker, price_usd, as_of, source)
    values (rec->>'ticker',
            nullif(rec->>'price_usd', '')::numeric,
            nullif(rec->>'as_of', '')::timestamptz,
            coalesce(rec->>'source', 'Yahoo Finance, vertraagd'))
    on conflict (ticker) do update
      set price_usd = excluded.price_usd,
          as_of     = excluded.as_of,
          source    = excluded.source,
          updated_at = now();
    live_bij := live_bij + 1;
  end loop;

  insert into public.audit_log (actor, action, detail)
  values ('leg_dagkoersen_vast', 'dagsnapshot via schrijfteken',
          jsonb_build_object('datum', p_datum, 'nieuw', nieuw,
                             'overgeslagen', overgeslagen,
                             'fx', fx_nieuw, 'live', live_bij,
                             'tickers', to_jsonb(toegestaan)));

  return jsonb_build_object(
    'datum', p_datum,
    'koersen_nieuw', nieuw,
    'koersen_stonden_er_al', overgeslagen,
    'wisselkoers_nieuw', fx_nieuw,
    'schermkoersen_bijgewerkt', live_bij,
    'actieve_tickers', to_jsonb(toegestaan)
  );
end;
$$;

comment on function public.leg_dagkoersen_vast(text, date, jsonb, jsonb, jsonb) is
  'De enige schrijfdeur voor de dagelijkse taak: de afgesloten beursdag van nu, compleet, en niets anders.';

revoke all on function public.leg_dagkoersen_vast(text, date, jsonb, jsonb, jsonb) from public;
grant execute on function public.leg_dagkoersen_vast(text, date, jsonb, jsonb, jsonb)
  to anon, authenticated;


-- ===========================================================================
-- E. STAAN DE WACHTERS ER, EN STAAN ZE AAN?
-- ===========================================================================
-- De vorige versie keek alleen of er een trigger met die naam bestond. Een
-- trigger kan uitgezet worden (alter table ... disable trigger) en blijft dan
-- gewoon in de lijst staan. Daarom kijkt deze versie ook naar tgenabled:
-- 'D' betekent uitgeschakeld.
--
-- Wat deze functie NIET kan, en wat je dus elders moet controleren
-- ===============================================================
-- Wie eigenaar is van de database kan triggers en functies wijzigen,
-- uitzetten of weghalen - ook deze functie, en ook de melding die ze geeft.
-- Een statuscontrole die in dezelfde database staat, kan dat per definitie
-- niet uitsluiten.
--
-- Daarom is de database nooit het enige controlespoor. Wat buiten deze
-- database staat en niet door een databasebeheerder gewijzigd kan worden:
--
--   * de openbare Git-geschiedenis van github.com/Adminbart76/stockwaakhond,
--     met het tijdstip van elke commit;
--   * de hash-keten in forward_log/ledger.jsonl, die lokaal en in de database
--     byte voor byte hetzelfde moet zijn;
--   * de bewijsbestanden in bewijs/, inclusief de 503 universumsymbolen.
--
-- Wijkt de database af van die drie, dan is de database fout en niet het
-- bewijs. Dat is de reden waarom het lokale bestand de bron van waarheid is.

create or replace function public.hardening_status()
returns jsonb
language sql
security definer
set search_path = public, privaat, pg_temp
as $$
  select jsonb_build_object(
    'deur_versie', 3,
    'keten_moet_kloppen', exists (
      select 1 from pg_trigger
      where tgname = 'keten_moet_kloppen'
        and tgrelid = 'public.signals'::regclass and not tgisinternal),
    'keten_moet_kloppen_staat_aan', exists (
      select 1 from pg_trigger
      where tgname = 'keten_moet_kloppen'
        and tgrelid = 'public.signals'::regclass and not tgisinternal
        and tgenabled <> 'D'),
    'velden_moeten_kloppen', exists (
      select 1 from pg_trigger
      where tgname = 'velden_moeten_kloppen'
        and tgrelid = 'public.executions'::regclass and not tgisinternal),
    'velden_moeten_kloppen_staat_aan', exists (
      select 1 from pg_trigger
      where tgname = 'velden_moeten_kloppen'
        and tgrelid = 'public.executions'::regclass and not tgisinternal
        and tgenabled <> 'D'),
    'hash_moet_kloppen_staat_aan', (
      select count(*) = 3 from pg_trigger
      where tgname = 'hash_moet_kloppen' and not tgisinternal
        and tgenabled <> 'D'
        and tgrelid in ('public.signals'::regclass, 'public.executions'::regclass,
                        'public.strategies'::regclass)),
    'sloten_staan_aan', (
      select count(*) = 7 from pg_trigger
      where tgname = 'geen_wijziging' and not tgisinternal and tgenabled <> 'D'),
    'sloten_gevonden', (
      select count(*) from pg_trigger
      where tgname = 'geen_wijziging' and not tgisinternal),
    'een_opvolger_per_uitvoering', exists (
      select 1 from pg_indexes
      where schemaname = 'public' and indexname = 'executions_een_opvolger'),
    'schrijfdeur_bestaat', exists (
      select 1 from pg_proc p join pg_namespace n on n.oid = p.pronamespace
      where n.nspname = 'public' and p.proname = 'leg_dagkoersen_vast'),
    'schrijfteken_ingesteld', exists (
      select 1 from privaat.snapshot_sleutels where actief),
    'eerlijk', 'Een eigenaar met DDL-rechten kan triggers en functies wijzigen, '
      || 'ook deze. Het controlespoor buiten deze database (Git-geschiedenis, '
      || 'hash-keten, bewijsbestanden) blijft dus nodig.'
  )
$$;

revoke all on function public.hardening_status() from public;
grant execute on function public.hardening_status() to anon, authenticated;


-- ===========================================================================
-- KLAAR - hieronder zie je wat er nu staat
-- ===========================================================================

select key as regel, value as stand
from jsonb_each_text(public.hardening_status())
order by key;
