-- ===========================================================================
-- StockWaakhond V7.1 - verstevigingen voor de toekomst
-- ===========================================================================
--
-- Plak dit volledige bestand in de Supabase SQL Editor en klik op Run.
-- Het mag meerdere keren uitgevoerd worden en verandert geen enkele
-- bestaande rij: alles hieronder zijn regels die gelden bij het TOEVOEGEN
-- van iets nieuws.
--
-- Draai eerst sql/01_schema.sql. Dit bestand bouwt daarop verder.
--
-- Waarom dit nodig is
-- ===================
-- Na 01_schema.sql kon de database al drie dingen:
--   * narekenen of het controlegetal bij de inhoud hoort
--   * wijzigen en wissen volledig weigeren
--   * dubbele volgnummers en dubbele datums weigeren
--
-- Wat ze nog niet kon, is nagaan of een nieuw signaal werkelijk het volgende
-- schakeltje in DEZE keten is. Een vervalst signaal met een kloppend
-- controlegetal, een eigen volgnummer en een eigen datum kwam er dus in.
-- Het viel daarna wel op bij de controle in de app, maar het stond er al, en
-- weghalen kan niet meer. Daarom moet de deur zelf dichtzitten.
--
-- Wat dit bestand toevoegt
-- ========================
--   A. De ketenregels bij een nieuw signaal (volgnummer, voorganger,
--      wachttijd van 28 dagen, geen datum in de toekomst, de formule die
--      werkelijk bij de strategie hoort).
--   B. Twee velden van een uitvoering die nog niet nagerekend werden
--      (fx_source en fx_asof), plus een venster waarin de wisselkoers mag
--      horen bij de dag waarop ingestapt is.
--   C. Een smalle schrijfdeur voor de dagelijkse taak op GitHub, zodat de
--      geheime sleutel daar niet meer hoeft te staan.
--   D. Een leesfunctie waarmee het aanvalsscript kan controleren dat dit
--      bestand werkelijk is uitgevoerd.
-- ===========================================================================


-- ===========================================================================
-- A. DE KETENREGELS BIJ EEN NIEUW SIGNAAL
-- ===========================================================================
-- Vijf dingen worden hier afgedwongen. Niet in de app, maar in de database,
-- want de app kan omzeild worden en de database niet.
--
--   1. het eerste signaal is seq 1 en verwijst naar 'GENESIS'
--   2. elk volgend signaal is exact het vorige volgnummer plus een
--   3. het verwijst naar het controlegetal van het huidige laatste signaal
--   4. er zitten minstens 28 kalenderdagen tussen twee signaaldatums
--   5. de signaaldatum ligt niet in de toekomst
--
-- En twee dingen die moesten kloppen maar niet nagekeken werden:
--
--   6. created_at_utc in de kolom is hetzelfde moment als in de gehashte tekst
--   7. formule en versie horen bij de strategie waarnaar verwezen wordt
--
-- Over twee tegelijk: de keten wordt onder slot gelezen. Zonder dat slot
-- kunnen twee gelijktijdige pogingen allebei hetzelfde laatste signaal zien
-- en allebei een geldig volgend schakeltje bouwen. Dan staan er twee ketens
-- naast elkaar en is geen van beide nog het bewijs.

create or replace function public.controleer_keten()
returns trigger
language plpgsql
as $$
declare
  tip_seq      bigint;
  tip_hash     text;
  tip_datum    date;
  heeft_tip    boolean := false;
  spec_db      jsonb;
  versie_db    text;
  vandaag_ny   date := (now() at time zone 'America/New_York')::date;
begin
  -- Eerst het slot, dan pas kijken. De sleutel is een vast getal: elke
  -- poging om een signaal toe te voegen wacht op dezelfde sleutel.
  perform pg_advisory_xact_lock(7701202610051);

  select s.seq, s.entry_hash, s.signal_market_date
    into tip_seq, tip_hash, tip_datum
  from public.signals s
  order by s.seq desc
  limit 1;

  heeft_tip := found;

  if not heeft_tip then
    if new.seq <> 1 then
      raise exception 'Het eerste signaal moet volgnummer 1 hebben, niet %.', new.seq
        using hint = 'De keten begint bij een. Er staat nog geen enkel signaal.';
    end if;
    if new.previous_hash <> 'GENESIS' then
      raise exception 'Het eerste signaal moet naar GENESIS verwijzen.'
        using hint = 'Er is geen voorganger, dus hoort er GENESIS te staan.';
    end if;
  else
    if new.seq <> tip_seq + 1 then
      raise exception 'Volgnummer % sluit niet aan: na % hoort %.',
        new.seq, tip_seq, tip_seq + 1
        using hint = 'De keten mag geen gat en geen zijtak hebben.';
    end if;

    if new.previous_hash <> tip_hash then
      raise exception 'Dit signaal verwijst niet naar het huidige laatste signaal.'
        using detail = format('verwacht: %s, opgegeven: %s', tip_hash, new.previous_hash),
              hint = 'Alleen de echte keten mag verlengd worden, geen tweede keten ernaast.';
    end if;

    if new.signal_market_date < tip_datum + 28 then
      raise exception 'Te vroeg: het vorige signaal is van %, een nieuw signaal mag pas vanaf %.',
        tip_datum, tip_datum + 28
        using hint = 'De wachttijd van 28 dagen hoort bij de bevroren opzet.';
    end if;
  end if;

  if new.signal_market_date > vandaag_ny then
    raise exception 'De signaaldatum % ligt in de toekomst (in New York is het %).',
      new.signal_market_date, vandaag_ny
      using hint = 'Een keuze kan niet gemaakt zijn op een beursdag die nog moet komen.';
  end if;

  -- Het moment van vastleggen staat in de gehashte tekst. De kolom moet
  -- dat moment zijn en niets anders, anders kan een record zich jonger of
  -- ouder voordoen dan wat er bewezen is.
  if (new.canonical_payload::jsonb->>'created_at_utc')::timestamptz
     is distinct from new.created_at_utc
  then
    raise exception 'created_at_utc in de kolom komt niet overeen met de gehashte inhoud.'
      using hint = 'Alleen de gehashte tekst telt als bewijs.';
  end if;

  -- De formule mag niet afwijken van de strategie waarnaar het record
  -- verwijst. Anders draagt een signaal een andere formule bij zich dan de
  -- strategie waar de hash van is gemaakt.
  select st.formula_spec, st.strategy_version
    into spec_db, versie_db
  from public.strategies st
  where st.strategy_hash = new.strategy_hash;

  if not found then
    raise exception 'Onbekende strategie %.', new.strategy_hash
      using hint = 'Leg eerst de strategie vast in de tabel strategies.';
  end if;

  if new.formula_spec is distinct from spec_db then
    raise exception 'De formule in dit signaal is niet de formule van strategie %.',
      new.strategy_hash
      using hint = 'Een afwijkende formule is per definitie een andere strategie.';
  end if;

  if new.strategy_version is distinct from versie_db then
    raise exception 'De strategieversie in dit signaal (%) hoort niet bij strategie %.',
      new.strategy_version, new.strategy_hash
      using hint = 'Versie en hash horen onlosmakelijk bij elkaar.';
  end if;

  return new;
end;
$$;

comment on function public.controleer_keten() is
  'Laat alleen een echt volgend schakeltje in de bestaande keten toe.';

drop trigger if exists keten_moet_kloppen on public.signals;
create trigger keten_moet_kloppen
  before insert on public.signals
  for each row execute function public.controleer_keten();


-- ===========================================================================
-- B. DE UITVOERING: TWEE VELDEN MEER NAREKENEN
-- ===========================================================================
-- De hashcontrole uit 01_schema.sql keek al naar fx_rate en fx_pair, maar
-- niet naar fx_source en fx_asof. Juist die twee zeggen WAAR de wisselkoers
-- vandaan komt en BIJ WELK MOMENT hij hoort. Zonder controle kon de kolom
-- iets anders beweren dan de gehashte tekst.
--
-- Daarbij nog twee regels:
--   * er wordt ingestapt NA de signaaldag, nooit op de dag zelf
--   * fx_asof is het moment waarop de wisselkoers gelezen is, en dat moet op
--     de instapdag zelf liggen, na de slotbel. Het venster loopt van de
--     slotbel (16:00 in New York) tot acht uur daarna.
--
--     Waarom dat venster: de dagbalk van EURUSD=X bij Yahoo klikt niet vast
--     op een slotkoers. Zolang de valutadag loopt, volgt hij de koers van dit
--     moment; daarna rapporteert Yahoo voor diezelfde datum een ander getal
--     dat bij een ander moment hoort (gemeten op 6 oktober 2026: 0,3 procent
--     verschil). Alleen binnen dit venster hoort de gelezen koers dus bij de
--     slotkoersen waarmee ze in hetzelfde record staat.

create or replace function public.controleer_uitvoering()
returns trigger
language plpgsql
as $$
declare
  inhoud       jsonb := new.canonical_payload::jsonb;
  signaaldatum date;
  slotbel      timestamptz;
begin
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

  return new;
end;
$$;

comment on function public.controleer_uitvoering() is
  'Rekent fx_source, fx_asof en de instapdag van een uitvoering na.';

drop trigger if exists velden_moeten_kloppen on public.executions;
create trigger velden_moeten_kloppen
  before insert on public.executions
  for each row execute function public.controleer_uitvoering();


-- ===========================================================================
-- C. EEN SMALLE SCHRIJFDEUR VOOR DE DAGELIJKSE TAAK
-- ===========================================================================
-- Tot nu toe had de dagelijkse taak op GitHub de geheime sleutel nodig om de
-- slotkoers van die dag weg te schrijven. Met die sleutel kan alles: elke
-- tabel, elke rij. Dat is veel te veel recht voor een taak die niets anders
-- doet dan zes koersen en een wisselkoers toevoegen.
--
-- In plaats daarvan: een functie die precies dat ene mag, en die om een eigen
-- schrijfteken vraagt. Van dat teken staat hier alleen het controlegetal, dus
-- wie in deze database kijkt, kan er niets mee.
--
-- Wat de functie NIET kan, en ook niet kan leren:
--   * in signals, strategies, executions of signal_universe schrijven
--   * iets wijzigen of verwijderen (dat blokkeert de trigger uit 01)
--   * een bestaande slotkoers overschrijven
--   * koersen van een aandeel dat niet in de portefeuille zit
--   * een datum in de toekomst

create schema if not exists privaat;
comment on schema privaat is
  'Niet via het web bereikbaar. Alleen voor geheimen die de database zelf nodig heeft.';

revoke all on schema privaat from anon, authenticated;

create table if not exists privaat.snapshot_sleutels (
  naam        text primary key,
  token_hash  text not null,
  actief      boolean not null default true,
  created_at  timestamptz not null default now()
);

revoke all on table privaat.snapshot_sleutels from anon, authenticated;

comment on table privaat.snapshot_sleutels is
  'Controlegetal van het schrijfteken voor dagkoersen. Het teken zelf staat hier niet.';


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
  toegestaan  text[];
  rec         jsonb;
  nieuw       integer := 0;
  overgeslagen integer := 0;
  fx_nieuw    integer := 0;
  live_bij    integer := 0;
  vandaag_ny  date := (now() at time zone 'America/New_York')::date;
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

  -- 2. De dag
  if p_datum is null then
    raise exception 'Geef de dag mee waarvoor de koersen gelden.';
  end if;
  if p_datum > vandaag_ny then
    raise exception 'Voor % bestaat nog geen slotkoers (in New York is het %).',
      p_datum, vandaag_ny;
  end if;

  -- 3. Welke aandelen mogen: wat er ooit gekozen is, plus de maatstaf SPY.
  select coalesce(array_agg(distinct x.ticker), array[]::text[]) into toegestaan
  from public.signals s,
       jsonb_to_recordset(s.selected) as x(ticker text);
  toegestaan := toegestaan || array['SPY'];

  -- 4. De slotkoersen. Bestaat er al een, dan blijft die staan.
  for rec in select * from jsonb_array_elements(coalesce(p_koersen, '[]'::jsonb))
  loop
    if not (rec->>'ticker' = any(toegestaan)) then
      raise exception 'Aandeel % hoort niet bij de portefeuille.', rec->>'ticker'
        using hint = 'Deze functie mag alleen koersen van de gevolgde aandelen vastleggen.';
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

  -- 5. De wisselkoers van die dag
  if p_fx is not null and p_fx->>'rate' is not null then
    if coalesce(p_fx->>'pair', 'EURUSD') <> 'EURUSD' then
      raise exception 'Alleen de wisselkoers EURUSD hoort hier.';
    end if;
    if (p_fx->>'rate')::numeric <= 0 then
      raise exception 'Geen bruikbare wisselkoers.';
    end if;

    insert into public.fx_snapshots (snapshot_date, pair, rate, source)
    values (p_datum, 'EURUSD', (p_fx->>'rate')::numeric,
            coalesce(p_fx->>'source', 'Yahoo Finance EURUSD=X dagslotkoers'))
    on conflict (snapshot_date, pair) do nothing;

    if found then fx_nieuw := 1; end if;
  end if;

  -- 6. De koersen voor het scherm. Dit is geen bewijsmateriaal en mag wel
  --    overschreven worden.
  for rec in select * from jsonb_array_elements(coalesce(p_live, '[]'::jsonb))
  loop
    if not (rec->>'ticker' = any(toegestaan)) then
      raise exception 'Aandeel % hoort niet bij de portefeuille.', rec->>'ticker';
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
                             'fx', fx_nieuw, 'live', live_bij));

  return jsonb_build_object(
    'datum', p_datum,
    'koersen_nieuw', nieuw,
    'koersen_stonden_er_al', overgeslagen,
    'wisselkoers_nieuw', fx_nieuw,
    'schermkoersen_bijgewerkt', live_bij
  );
end;
$$;

comment on function public.leg_dagkoersen_vast(text, date, jsonb, jsonb, jsonb) is
  'De enige schrijfdeur voor de dagelijkse taak: koersen toevoegen, niets anders.';

revoke all on function public.leg_dagkoersen_vast(text, date, jsonb, jsonb, jsonb) from public;
grant execute on function public.leg_dagkoersen_vast(text, date, jsonb, jsonb, jsonb)
  to anon, authenticated;


-- ===========================================================================
-- D. IS DEZE VERSTEVIGING WERKELIJK UITGEVOERD?
-- ===========================================================================
-- Het aanvalsscript moet kunnen zien dat bovenstaande regels er echt staan.
-- Zonder dit zou een geslaagde aanvalstest ook kunnen betekenen dat een
-- andere laag de poging tegenhield en de nieuwe regel helemaal ontbreekt.

create or replace function public.hardening_status()
returns jsonb
language sql
security definer
set search_path = public, privaat, pg_temp
as $$
  select jsonb_build_object(
    'keten_moet_kloppen', exists (
      select 1 from pg_trigger
      where tgname = 'keten_moet_kloppen'
        and tgrelid = 'public.signals'::regclass and not tgisinternal),
    'velden_moeten_kloppen', exists (
      select 1 from pg_trigger
      where tgname = 'velden_moeten_kloppen'
        and tgrelid = 'public.executions'::regclass and not tgisinternal),
    'schrijfdeur_bestaat', exists (
      select 1 from pg_proc p join pg_namespace n on n.oid = p.pronamespace
      where n.nspname = 'public' and p.proname = 'leg_dagkoersen_vast'),
    'schrijfteken_ingesteld', exists (
      select 1 from privaat.snapshot_sleutels where actief)
  )
$$;

revoke all on function public.hardening_status() from public;
grant execute on function public.hardening_status() to anon, authenticated;


-- ===========================================================================
-- NOG EEN KEER MET DE HAND: HET SCHRIJFTEKEN
-- ===========================================================================
-- Het schrijfteken zelf staat niet in dit bestand, want dit bestand staat in
-- een openbare GitHub-map. De regel die je nog moet uitvoeren, staat in
-- SLEUTELS_INVULLEN.txt. Die map staat niet in GitHub.
--
-- Zolang je die regel niet uitvoert, geeft hardening_status() voor
-- "schrijfteken_ingesteld" false terug en kan de dagelijkse taak niets
-- wegschrijven. Er gaat dan niets stuk: de taak meldt het en stopt.


-- ===========================================================================
-- KLAAR - hieronder zie je wat er nu staat
-- ===========================================================================

select
  'keten_moet_kloppen (signals)' as regel,
  exists (select 1 from pg_trigger
          where tgname = 'keten_moet_kloppen'
            and tgrelid = 'public.signals'::regclass and not tgisinternal) as staat_erop
union all
select
  'velden_moeten_kloppen (executions)',
  exists (select 1 from pg_trigger
          where tgname = 'velden_moeten_kloppen'
            and tgrelid = 'public.executions'::regclass and not tgisinternal)
union all
select
  'schrijfdeur leg_dagkoersen_vast',
  exists (select 1 from pg_proc p join pg_namespace n on n.oid = p.pronamespace
          where n.nspname = 'public' and p.proname = 'leg_dagkoersen_vast')
union all
select
  'schrijfteken ingesteld (regel uit SLEUTELS_INVULLEN.txt)',
  exists (select 1 from privaat.snapshot_sleutels where actief);
