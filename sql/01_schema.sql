-- ===========================================================================
-- StockWaakhond V7.1 - databasestructuur
-- ===========================================================================
--
-- Plak dit volledige bestand in de Supabase SQL Editor en klik op Run.
-- Het mag meerdere keren uitgevoerd worden: bestaande tabellen blijven staan
-- en er gaat niets verloren.
--
-- De opzet kent twee soorten tabellen:
--
--   A. ONAANTASTBAAR - de officiele forward-test.
--      Hier mag alleen iets bijkomen. Wijzigen en wissen is onmogelijk
--      gemaakt, ook voor de beheerder en ook vanuit deze SQL Editor.
--
--   B. AFGELEID - alles wat opnieuw berekend kan worden.
--      Mag overschreven worden, mag weg, is geen bewijsmateriaal.
--
-- De scheiding is bewust streng. Een forward-test die achteraf bijgesteld kan
-- worden, bewijst niets.
-- ===========================================================================


-- ===========================================================================
-- HULPMIDDEL: hash berekenen in de database zelf
-- ===========================================================================
-- Hiermee kan de database een aangeleverd record narekenen in plaats van het
-- op ons woord te geloven. sha256 zit standaard in PostgreSQL, er is geen
-- extensie voor nodig.

create or replace function public.sha256_hex(invoer text)
returns text
language sql
immutable
as $$
  select encode(sha256(convert_to(invoer, 'UTF8')), 'hex')
$$;

comment on function public.sha256_hex(text) is
  'Berekent het sha256-controlegetal van een stuk tekst, zoals de app dat ook doet.';


-- ===========================================================================
-- A1. STRATEGIEEN
-- ===========================================================================
-- Elke strategieversie staat hier een keer. De hash is de sleutel: dezelfde
-- formule geeft altijd dezelfde sleutel, een gewijzigde formule is per
-- definitie een nieuwe rij. Overschrijven kan dus niet.
--
-- canonical_spec is de exacte tekst waarover de hash berekend is. Die bewaren
-- we omdat je anders de hash nooit meer kunt narekenen: de volgorde waarin
-- JSON wordt opgeschreven bepaalt mee de uitkomst.

create table if not exists public.strategies (
  strategy_hash     text primary key,
  strategy_version  text not null unique,
  formula_spec      jsonb not null,
  canonical_spec    text not null,
  created_at        timestamptz not null default now()
);

comment on table public.strategies is
  'A - onaantastbaar. De bevroren scoreformules, met hun hash als sleutel.';


-- ===========================================================================
-- A2. OFFICIELE FORWARD-SIGNALEN
-- ===========================================================================
-- Dit is het hart. Een rij hier is een keuze die vooraf is vastgelegd en
-- daarna nooit meer verandert.
--
-- Drie dingen maken het onwrikbaar:
--   previous_hash is uniek  -> er kan nooit een tweede keten naast ontstaan
--   de hashcontrole bij invoer -> de database rekent het zelf na
--   het slot verderop       -> wijzigen en wissen is geblokkeerd
--
-- ledger_line bewaart de oorspronkelijke regel uit ledger.jsonl letter voor
-- letter, zodat database en lokaal bestand exact vergeleken kunnen worden.

create table if not exists public.signals (
  entry_hash          text primary key,
  seq                 bigint not null unique,
  previous_hash       text not null unique,
  record_type         text not null default 'signal',
  schema_version      integer not null,

  strategy_hash       text not null references public.strategies(strategy_hash),
  strategy_version    text not null,

  signal_market_date  date not null unique,
  created_at_utc      timestamptz not null,

  universe_source     text not null,
  universe_hash       text not null,
  universe_count      integer not null,
  eligible_count      integer not null,
  coverage_pct        numeric not null,

  spy_signal_close    numeric not null,
  selected            jsonb not null,
  formula_spec        jsonb not null,

  canonical_payload   text not null,
  ledger_line         text not null,
  imported_at         timestamptz not null default now(),

  constraint signals_volgnummer_vanaf_een
    check (seq >= 1),
  constraint signals_dekking_tussen_0_en_100
    check (coverage_pct >= 0 and coverage_pct <= 100),
  constraint signals_aantallen_kloppen
    check (eligible_count >= 0 and eligible_count <= universe_count),
  constraint signals_spy_koers_positief
    check (spy_signal_close > 0)
);

comment on table public.signals is
  'A - onaantastbaar. De officiele forward-signalen met hun hash-keten.';


-- ===========================================================================
-- A3. HET UNIVERSUM PER SIGNAAL
-- ===========================================================================
-- De aandelen waaruit op dat moment gekozen mocht worden. Het logboek bewaarde
-- daar alleen een controlegetal van, niet de lijst zelf. Daardoor was de
-- universe_hash niet na te rekenen zodra Wikipedia veranderde. Met deze tabel
-- kan dat voortaan wel.

create table if not exists public.signal_universe (
  entry_hash  text not null references public.signals(entry_hash),
  symbol      text not null,
  primary key (entry_hash, symbol)
);

comment on table public.signal_universe is
  'A - onaantastbaar. De volledige symbolenlijst per signaal, zodat universe_hash naneembaar blijft.';


-- ===========================================================================
-- A4. UITVOERING VAN DE VIRTUELE PORTEFEUILLE
-- ===========================================================================
-- Hier staat wat er met de 1.000 euro gebeurd is: tegen welke koers er is
-- ingestapt, tegen welke wisselkoers, en hoeveel aandelen dat opleverde.
--
-- Dit moet net zo onaantastbaar zijn als het signaal zelf. Zou je het elke
-- keer opnieuw berekenen, dan zou de aankoopkoers meeschuiven zodra Yahoo
-- oude koersen aanpast na een dividend, en dan zou het rendement achteraf
-- veranderen. Een keer vastleggen lost dat definitief op.

create table if not exists public.executions (
  exec_hash           text primary key,
  entry_hash          text not null unique references public.signals(entry_hash),

  execution_date      date not null,
  fx_pair             text not null default 'EURUSD',
  fx_rate             numeric not null,
  fx_source           text not null,
  fx_asof             timestamptz not null,

  start_capital_eur   numeric not null,
  cost_pct            numeric not null,
  cost_eur            numeric not null,
  invested_eur        numeric not null,

  positions           jsonb not null,
  benchmark           jsonb not null,

  canonical_payload   text not null,
  created_at          timestamptz not null default now(),

  constraint executions_wisselkoers_positief check (fx_rate > 0),
  constraint executions_kapitaal_positief    check (start_capital_eur > 0)
);

comment on table public.executions is
  'A - onaantastbaar. De vastgelegde instap van de virtuele portefeuille.';


-- ===========================================================================
-- A5. DAGELIJKSE SLOTKOERSEN
-- ===========================================================================
-- Na de slotbel leggen we de koers van die dag vast. Daarna verandert de
-- grafiek niet meer met terugwerkende kracht.
--
-- Waarom dat nodig is: Yahoo verlaagt oude koersen zodra er dividend wordt
-- uitgekeerd. Van de vijf gekozen aandelen keren MPC, VLO en HPE dividend uit,
-- en SPY ook. Zonder deze tabel zou het verleden blijven schuiven.
--
--   close_raw      = de koers zoals hij die dag op het scherm stond
--   close_adjusted = dezelfde koers herrekend voor dividend en splitsingen
--
-- Allebei bewaren, want ze dienen elk een ander doel: de eerste voor wat de
-- portefeuille waard is, de tweede voor het totaalrendement.

create table if not exists public.price_snapshots (
  snapshot_date   date not null,
  ticker          text not null,
  close_raw       numeric,
  close_adjusted  numeric,
  source          text not null,
  captured_at     timestamptz not null default now(),
  primary key (snapshot_date, ticker)
);

create index if not exists snapshots_op_ticker
  on public.price_snapshots (ticker, snapshot_date);

comment on table public.price_snapshots is
  'A - onaantastbaar. Dagelijkse slotkoersen, zodat de grafiek niet achteraf verschuift.';


-- ===========================================================================
-- A6. WISSELKOERSEN
-- ===========================================================================
-- Dezelfde redenering als bij de koersen: een keer per dag vastleggen.

create table if not exists public.fx_snapshots (
  snapshot_date  date not null,
  pair           text not null default 'EURUSD',
  rate           numeric not null,
  source         text not null,
  captured_at    timestamptz not null default now(),
  primary key (snapshot_date, pair),
  constraint fx_koers_positief check (rate > 0)
);

comment on table public.fx_snapshots is
  'A - onaantastbaar. Dagelijkse wisselkoers euro-dollar.';


-- ===========================================================================
-- A7. DIVIDENDEN
-- ===========================================================================
-- Wat er aan dividend is uitgekeerd op de aandelen in portefeuille.
-- Bruto is wat het bedrijf betaalt, netto is wat er voor een Belgische
-- belegger overblijft na Amerikaanse bronheffing en roerende voorheffing.

create table if not exists public.dividends (
  ticker               text not null,
  ex_date              date not null,
  gross_per_share_usd  numeric not null,
  net_per_share_usd    numeric,
  tax_note             text,
  source               text not null,
  captured_at          timestamptz not null default now(),
  primary key (ticker, ex_date)
);

comment on table public.dividends is
  'A - onaantastbaar. Uitgekeerde dividenden, bruto en netto.';


-- ===========================================================================
-- B1. ACTUELE KOERSEN - mag overschreven worden
-- ===========================================================================
-- Alleen voor het scherm. Dit is geen bewijsmateriaal en mag altijd weg.

create table if not exists public.live_quotes (
  ticker      text primary key,
  price_usd   numeric,
  as_of       timestamptz,
  source      text,
  updated_at  timestamptz not null default now()
);

comment on table public.live_quotes is
  'B - afgeleid. Laatst opgehaalde koers, puur voor weergave. Mag overschreven worden.';


-- ===========================================================================
-- B2. SCANVOORSTELLEN - nooit vanzelf officieel
-- ===========================================================================
-- Een automatische maandscan mag hier een voorstel neerleggen. Het wordt pas
-- een officieel signaal als er een mens op de knop drukt. Zo kan automatisering
-- nooit uit zichzelf de forward-test beinvloeden.

create table if not exists public.signal_proposals (
  id                  bigint generated always as identity primary key,
  proposed_at         timestamptz not null default now(),
  signal_market_date  date,
  payload             jsonb not null,
  note                text,
  consumed            boolean not null default false
);

comment on table public.signal_proposals is
  'B - afgeleid. Voorstellen van de automatische scan. Nooit vanzelf officieel.';


-- ===========================================================================
-- B3. LOGBOEK VAN BEHEERSHANDELINGEN
-- ===========================================================================

create table if not exists public.audit_log (
  id      bigint generated always as identity primary key,
  at      timestamptz not null default now(),
  actor   text,
  action  text not null,
  detail  jsonb
);

comment on table public.audit_log is
  'B - afgeleid. Wie deed wat wanneer.';


-- ===========================================================================
-- CONTROLE BIJ INVOER: klopt het controlegetal?
-- ===========================================================================
-- De database rekent zelf na of de hash bij de inhoud hoort. Een record met
-- een verkeerde hash komt er niet in, ook niet met de geheime sleutel.

create or replace function public.controleer_hash()
returns trigger
language plpgsql
as $$
declare
  berekend text;
  opgegeven text;
  inhoud jsonb;
begin
  if TG_TABLE_NAME = 'signals' then
    berekend := public.sha256_hex(new.canonical_payload);
    opgegeven := new.entry_hash;
  elsif TG_TABLE_NAME = 'executions' then
    berekend := public.sha256_hex(new.canonical_payload);
    opgegeven := new.exec_hash;
  elsif TG_TABLE_NAME = 'strategies' then
    berekend := public.sha256_hex(new.canonical_spec);
    opgegeven := new.strategy_hash;
  else
    return new;
  end if;

  if berekend is distinct from opgegeven then
    raise exception
      'Het controlegetal van dit record klopt niet met de inhoud.'
      using detail = format('berekend: %s, opgegeven: %s', berekend, opgegeven),
            hint = 'De inhoud is onderweg gewijzigd, of de hash is verkeerd berekend.';
  end if;

  -- Een kloppend controlegetal is niet genoeg. De losse kolommen moeten ook
  -- werkelijk zeggen wat er in de gehashte tekst staat. Zonder deze controle
  -- zou iemand een geldige hash kunnen combineren met afwijkende kolommen, en
  -- dan toont het dashboard iets anders dan wat er bewezen is.
  if TG_TABLE_NAME = 'signals' then
    inhoud := new.canonical_payload::jsonb;

    if (inhoud->>'signal_market_date')::date       is distinct from new.signal_market_date
       or inhoud->>'previous_hash'                 is distinct from new.previous_hash
       or inhoud->>'strategy_hash'                 is distinct from new.strategy_hash
       or inhoud->>'strategy_version'              is distinct from new.strategy_version
       or inhoud->>'universe_hash'                 is distinct from new.universe_hash
       or inhoud->>'universe_source'               is distinct from new.universe_source
       or (inhoud->>'universe_count')::integer     is distinct from new.universe_count
       or (inhoud->>'eligible_count')::integer     is distinct from new.eligible_count
       or (inhoud->>'coverage_pct')::numeric       is distinct from new.coverage_pct
       or (inhoud->>'spy_signal_close')::numeric   is distinct from new.spy_signal_close
       or (inhoud->>'schema_version')::integer     is distinct from new.schema_version
       or inhoud->>'record_type'                   is distinct from new.record_type
       or inhoud->'selected'                       is distinct from new.selected
       or inhoud->'formula_spec'                   is distinct from new.formula_spec
    then
      raise exception
        'De kolommen van dit record komen niet overeen met de gehashte inhoud.'
        using hint = 'Alleen de gehashte tekst telt als bewijs. De kolommen moeten die exact volgen.';
    end if;

    -- De bewaarde logboekregel moet dezelfde inhoud zijn, plus het controlegetal.
    if new.ledger_line::jsonb
       is distinct from (inhoud || jsonb_build_object('entry_hash', new.entry_hash))
    then
      raise exception
        'De bewaarde logboekregel komt niet overeen met de gehashte inhoud.'
        using hint = 'ledger_line hoort exact de gehashte inhoud te zijn plus entry_hash.';
    end if;

  elsif TG_TABLE_NAME = 'executions' then
    inhoud := new.canonical_payload::jsonb;

    if inhoud->>'entry_hash'                     is distinct from new.entry_hash
       or (inhoud->>'execution_date')::date      is distinct from new.execution_date
       or (inhoud->>'fx_rate')::numeric          is distinct from new.fx_rate
       or inhoud->>'fx_pair'                     is distinct from new.fx_pair
       or (inhoud->>'start_capital_eur')::numeric is distinct from new.start_capital_eur
       or (inhoud->>'cost_pct')::numeric         is distinct from new.cost_pct
       or (inhoud->>'cost_eur')::numeric         is distinct from new.cost_eur
       or (inhoud->>'invested_eur')::numeric     is distinct from new.invested_eur
       or inhoud->'positions'                    is distinct from new.positions
       or inhoud->'benchmark'                    is distinct from new.benchmark
    then
      raise exception
        'De kolommen van deze uitvoering komen niet overeen met de gehashte inhoud.'
        using hint = 'Alleen de gehashte tekst telt als bewijs.';
    end if;

  elsif TG_TABLE_NAME = 'strategies' then
    inhoud := new.canonical_spec::jsonb;

    if inhoud->>'version' is distinct from new.strategy_version
       or inhoud          is distinct from new.formula_spec
    then
      raise exception
        'De formule in de kolom komt niet overeen met de gehashte formule.';
    end if;
  end if;

  return new;
end;
$$;

do $$
declare
  t text;
begin
  foreach t in array array['strategies', 'signals', 'executions']
  loop
    execute format('drop trigger if exists hash_moet_kloppen on public.%I', t);
    execute format(
      'create trigger hash_moet_kloppen before insert on public.%I '
      'for each row execute function public.controleer_hash()', t);
  end loop;
end
$$;


-- ===========================================================================
-- HET SLOT: wijzigen en wissen onmogelijk maken
-- ===========================================================================
-- Dit is de belangrijkste beveiliging van het geheel.
--
-- De gewone Supabase-beveiliging (row level security) wordt omzeild door de
-- geheime sleutel. Een trigger niet: die geldt voor iedereen, ook voor de
-- geheime sleutel en ook voor jezelf in deze SQL Editor.
--
-- Wil je ooit echt iets wijzigen, dan moet je eerst bewust de trigger
-- weghalen. Dat is precies de drempel die we willen: geen ongeluk, geen
-- impuls na een slechte beursweek, maar een expliciete daad.

create or replace function public.weiger_wijziging()
returns trigger
language plpgsql
as $$
begin
  raise exception
    'Tabel % is append-only: % is niet toegestaan.', TG_TABLE_NAME, TG_OP
    using hint =
      'Een vastgelegd forward-signaal mag nooit gewijzigd of verwijderd worden. '
      'Dat is de hele reden waarom deze test iets bewijst.';
  return null;
end;
$$;

do $$
declare
  t text;
begin
  foreach t in array array[
    'strategies', 'signals', 'signal_universe', 'executions',
    'price_snapshots', 'fx_snapshots', 'dividends'
  ]
  loop
    execute format('drop trigger if exists geen_wijziging on public.%I', t);
    execute format(
      'create trigger geen_wijziging before update or delete on public.%I '
      'for each statement execute function public.weiger_wijziging()', t);
  end loop;
end
$$;


-- ===========================================================================
-- LEESRECHTEN
-- ===========================================================================
-- Kijkers mogen alles lezen en niets schrijven. Er bestaat geen schrijfregel,
-- dus schrijven kan alleen met de geheime sleutel, die nooit in de webapp komt.

grant usage on schema public to anon, authenticated;

alter table public.strategies       enable row level security;
alter table public.signals          enable row level security;
alter table public.signal_universe  enable row level security;
alter table public.executions       enable row level security;
alter table public.price_snapshots  enable row level security;
alter table public.fx_snapshots     enable row level security;
alter table public.dividends        enable row level security;
alter table public.live_quotes      enable row level security;
alter table public.signal_proposals enable row level security;
alter table public.audit_log        enable row level security;

do $$
declare
  t text;
begin
  foreach t in array array[
    'strategies', 'signals', 'signal_universe', 'executions',
    'price_snapshots', 'fx_snapshots', 'dividends', 'live_quotes'
  ]
  loop
    execute format('drop policy if exists lezen_mag on public.%I', t);
    execute format(
      'create policy lezen_mag on public.%I for select to anon, authenticated using (true)', t);
    execute format('grant select on public.%I to anon, authenticated', t);
    execute format('revoke insert, update, delete on public.%I from anon, authenticated', t);
  end loop;
end
$$;

-- Scanvoorstellen en het beheerslogboek blijven afgeschermd: daar heeft een
-- kijker niets te zoeken en er kan verwarrende informatie in staan.
revoke all on public.signal_proposals from anon, authenticated;
revoke all on public.audit_log        from anon, authenticated;


-- ===========================================================================
-- OVERZICHT VOOR HET DASHBOARD
-- ===========================================================================

create or replace view public.laatste_signaal
with (security_invoker = true) as
  select
    s.entry_hash,
    s.seq,
    s.signal_market_date,
    s.created_at_utc,
    s.strategy_version,
    s.strategy_hash,
    s.universe_hash,
    s.universe_count,
    s.eligible_count,
    s.coverage_pct,
    s.spy_signal_close,
    s.selected,
    (s.signal_market_date + 28) as vroegste_nieuwe_selectie
  from public.signals s
  order by s.seq desc
  limit 1;

grant select on public.laatste_signaal to anon, authenticated;


-- ===========================================================================
-- KLAAR - controleer hieronder of alles er staat
-- ===========================================================================
-- Je hoort tien tabellen te zien: zeven onaantastbare en drie afgeleide.

select
  t.table_name as tabel,
  case
    when t.table_name in ('strategies','signals','signal_universe','executions',
                          'price_snapshots','fx_snapshots','dividends')
      then 'A - onaantastbaar'
    else 'B - afgeleid'
  end as soort,
  (select count(*) from information_schema.triggers g
    where g.event_object_table = t.table_name
      and g.trigger_name = 'geen_wijziging') > 0 as slot_staat_erop
from information_schema.tables t
where t.table_schema = 'public' and t.table_type = 'BASE TABLE'
order by soort, tabel;
