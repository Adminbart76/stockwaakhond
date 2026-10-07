-- ===========================================================================
-- StockWaakhond V7.1 - 05: het wisselkoersbewijs is verplicht bij een wissel
-- ===========================================================================
-- Hoort NA 01_schema.sql, 02_hardening.sql, 03_smalle_deur.sql en
-- 04_dividend_en_fx.sql te draaien. Dit bestand voegt alleen toe: een eigen
-- wachter, een constraint op de dagkoersen en een nieuwere statusmelding. Het
-- vervangt geen enkele functie uit 02, 03 of 04. Opnieuw draaien is veilig en
-- verandert geen bestaande rij.
--
-- Waarom dit nodig is (auditronde 5, 7 oktober 2026)
-- ==================================================
-- 04 rekent de minuutbalk en het ECB-controlegetal na ZODRA het record die
-- velden zelf meebrengt:
--
--     if inhoud ? 'fx_bar_end' then ... end if;
--
-- Dat is te zwak. Een record dat de velden gewoon weglaat, komt nergens langs
-- die controles en mag er dan in. De wachter bewaakt in die vorm alleen wie
-- eerlijk is over wat hij meebrengt.
--
-- Vanaf hier geldt: elke uitvoering die naar een voorganger verwijst
-- (prev_exec_hash is niet leeg) MOET de acht bewijsvelden meebrengen, en ze
-- worden allemaal nagerekend. Ontbreekt er een, dan komt het record er niet in.
--
-- De instap van 6 oktober 2026 blijft expliciet buiten deze regel
-- ===============================================================
-- Die uitvoering is de eerste schakel, heeft geen voorganger en kende de regel
-- van de minuutbalk nog niet: haar wisselkoers is de dagslotkoers van
-- EURUSD=X. Ze is vastgelegd, onaantastbaar en mag nooit wijzigen. De wachter
-- hieronder doet daarom niets bij een record zonder prev_exec_hash - en hij
-- draait alleen bij een INSERT, dus hij komt langs bestaande rijen niet eens.
--
-- Waarom een APARTE wachter en geen nieuwe versie van 04
-- ======================================================
-- Zelfde reden als in 04 zelf: zo hoeft 04 niet opnieuw te draaien na dit
-- bestand, en kan de volgorde van de bestanden geen stille regressie geven.
-- Alleen hardening_status() wordt vervangen (deur_versie 5). Draait 04 er
-- daarna nog eens over, dan staat er weer 4 en slaat
-- scripts/controleer_slot.py alarm.


-- ===========================================================================
-- A. DE WACHTER OP HET BEWIJS VAN EEN WISSEL
-- ===========================================================================
-- Wat er nagerekend wordt, en waarom het alle acht moet zijn:
--
--   fx_bar_start / fx_bar_end   het interval waar de koers bij hoort. Eindigt
--                               op of voor de slotbel in New York, hoogstens
--                               vijf minuten ervoor, en duurt precies een
--                               minuut. Een balk na de bel bevat handel die de
--                               slotkoersen niet kennen; een langer interval is
--                               een andere koers.
--   fx_bar_normaal              zegt of het de gewone balk van 15:59-16:00 was.
--                               Moet kloppen met het interval zelf, anders
--                               beweert het record twee dingen tegelijk.
--   fx_control_source           waar het controlegetal vandaan komt. Zonder
--                               bron kan niemand het opnieuw opvragen.
--   fx_control_date             de dag van het controlegetal. Nooit na de
--                               uitvoeringsdag: een koers van later kan de
--                               koers van die dag niet controleren.
--   fx_control_same_day         zegt of het controlegetal van dezelfde dag is.
--                               Moet kloppen met fx_control_date.
--   fx_control_rate             het controlegetal zelf, groter dan nul.
--   fx_control_deviation_pct    de afwijking tussen de twee koersen. Wordt hier
--                               opnieuw uitgerekend; staat er iets anders, dan
--                               is het getal niet uit deze twee koersen gekomen.
--
-- Yahoo bewaart minuutgegevens ongeveer dertig dagen. Wat op de avond van de
-- wissel niet in de gehashte tekst staat, is een jaar later niet meer te
-- reconstrueren. Daarom is dit geen vormvereiste maar het bewijs zelf.

create or replace function public.controleer_fx_bewijs_verplicht()
returns trigger
language plpgsql
as $$
declare
  inhoud      jsonb := new.canonical_payload::jsonb;
  verplicht   text[] := array[
                 'fx_bar_start', 'fx_bar_end', 'fx_bar_normaal',
                 'fx_control_source', 'fx_control_date', 'fx_control_rate',
                 'fx_control_same_day', 'fx_control_deviation_pct'];
  veld        text;
  mist        text[] := array[]::text[];
  slotbel     timestamptz;
  begin_balk  timestamptz;
  eind_balk   timestamptz;
  normaal     boolean;
  bron        text;
  controle    numeric;
  controledag date;
  zelfde_dag  boolean;
  opgeslagen  numeric;
  opnieuw     numeric;
begin
  -- De eerste schakel (de instap van 6 oktober 2026) heeft geen voorganger en
  -- valt buiten deze regel. Alles wat daarna komt, valt eronder. De kolom en de
  -- gehashte tekst worden allebei gelezen; dat ze hetzelfde zeggen, rekent de
  -- wachter uit 03 al na.
  if coalesce(new.prev_exec_hash, inhoud->>'prev_exec_hash') is null then
    return new;
  end if;

  foreach veld in array verplicht loop
    if not (inhoud ? veld) or inhoud->>veld is null or inhoud->>veld = '' then
      mist := mist || veld;
    end if;
  end loop;

  if array_length(mist, 1) > 0 then
    raise exception
      'Deze wissel draagt haar wisselkoersbewijs niet mee. Ontbreekt: %.',
      array_to_string(mist, ', ')
      using hint =
        'Elke wissel hoort de minuutbalk van de slotbel en het '
        'ECB-controlegetal in de gehashte tekst te hebben. Yahoo bewaart '
        'minuutgegevens ongeveer dertig dagen; wat er nu niet in staat, is '
        'later niet meer na te rekenen.';
  end if;

  slotbel := (new.execution_date::text || ' 16:00')::timestamp
             at time zone 'America/New_York';
  begin_balk := (inhoud->>'fx_bar_start')::timestamptz;
  eind_balk  := (inhoud->>'fx_bar_end')::timestamptz;

  if eind_balk <= begin_balk then
    raise exception 'De minuutbalk loopt van % tot %; het einde ligt niet na het begin.',
      begin_balk, eind_balk;
  end if;

  if eind_balk - begin_balk <> interval '1 minute' then
    raise exception 'De balk van % tot % duurt geen minuut.',
      begin_balk, eind_balk
      using hint =
        'De regel gaat over 1-minuutbalken; een langer interval is een andere koers.';
  end if;

  if eind_balk > slotbel then
    raise exception 'De minuutbalk eindigt om % en dat is na de slotbel van % (%).',
      eind_balk, new.execution_date, slotbel
      using hint =
        'Een balk na de slotbel bevat handel die de slotkoersen niet kennen.';
  end if;

  if eind_balk < slotbel - interval '5 minutes' then
    raise exception 'De minuutbalk eindigt om %, meer dan vijf minuten voor de slotbel (%).',
      eind_balk, slotbel
      using hint =
        'De regel laat hoogstens vijf minuten terugval toe; daarbuiten hoort '
        'een mens ernaar te kijken.';
  end if;

  normaal := (inhoud->>'fx_bar_normaal')::boolean;
  if normaal is distinct from (eind_balk = slotbel) then
    raise exception
      'fx_bar_normaal zegt %, terwijl de balk om % eindigt en de slotbel om % klinkt.',
      normaal, eind_balk, slotbel
      using hint =
        'Het ene zegt dat het de normale balk van 15:59-16:00 was en het andere niet.';
  end if;

  bron := btrim(coalesce(inhoud->>'fx_control_source', ''));
  if bron = '' then
    raise exception 'Er staat geen bron bij het controlegetal van de wisselkoers.'
      using hint = 'Zonder bron kan een latere lezer het niet opnieuw opvragen.';
  end if;

  controle := (inhoud->>'fx_control_rate')::numeric;
  if controle is null or controle <= 0 then
    raise exception 'Het controlegetal van de wisselkoers is geen koers (%).', controle;
  end if;

  controledag := (inhoud->>'fx_control_date')::date;
  if controledag > new.execution_date then
    raise exception 'Het controlegetal is van % en dat is na de uitvoeringsdag %.',
      controledag, new.execution_date
      using hint =
        'Een koers van later kan de koers van die dag niet controleren.';
  end if;

  zelfde_dag := (inhoud->>'fx_control_same_day')::boolean;
  if zelfde_dag is distinct from (controledag = new.execution_date) then
    raise exception
      'fx_control_same_day zegt %, terwijl het controlegetal van % is en de uitvoering van %.',
      zelfde_dag, controledag, new.execution_date;
  end if;

  -- De afwijking opnieuw uitrekenen uit de twee koersen die in hetzelfde
  -- record staan. Staat er een ander getal, dan komt het daar niet uit.
  opgeslagen := (inhoud->>'fx_control_deviation_pct')::numeric;
  opnieuw := round((new.fx_rate / controle - 1) * 100, 6);
  if abs(opgeslagen - opnieuw) > 0.00001 then
    raise exception
      'Er staat % procent afwijking in het bewijs, maar % tegen % geeft % procent.',
      opgeslagen, new.fx_rate, controle, opnieuw
      using hint =
        'Het opgeslagen getal klopt niet met de twee koersen waar het tussen staat.';
  end if;

  if abs(opnieuw) > 1 then
    raise exception
      'De wisselkoers (%) wijkt % procent af van het controlegetal (%).',
      new.fx_rate, opnieuw, controle
      using hint =
        'Meer dan een procent verschil met de ECB-referentiekoers is geen '
        'dagbeweging maar een fout in de gegevens.';
  end if;

  return new;
end;
$$;

comment on function public.controleer_fx_bewijs_verplicht() is
  'Eist en rekent het volledige wisselkoersbewijs van elke wissel na (sql/05).';

drop trigger if exists fx_bewijs_verplicht on public.executions;
create trigger fx_bewijs_verplicht
  before insert on public.executions
  for each row execute function public.controleer_fx_bewijs_verplicht();


-- ===========================================================================
-- B. EEN MINUUT IS EEN MINUUT, OOK BIJ DE DAGKOERSEN
-- ===========================================================================
-- 04 eist al dat bar_end na bar_start ligt. Dat laat een interval van een uur
-- toe, en dat is geen 1-minuutbalk. Beide kolommen blijven leeg bij de
-- dagkoersen die de dagelijkse taak wegschrijft; alleen een uitvoeringsdag
-- vult ze.
--
-- De constraint wordt alleen gezet als er geen bestaande rij tegen ingaat. Zou
-- er wel zo'n rij staan, dan hoort een mens ernaar te kijken in plaats van dat
-- dit bestand faalt of iets stilletjes bijwerkt.

do $$
declare
  scheef integer;
begin
  if exists (
    select 1 from pg_constraint
    where conname = 'fx_balk_duurt_een_minuut'
      and conrelid = 'public.fx_snapshots'::regclass
  ) then
    return;
  end if;

  select count(*) into scheef
  from public.fx_snapshots
  where bar_start is not null and bar_end is not null
    and bar_end - bar_start <> interval '1 minute';

  if scheef = 0 then
    alter table public.fx_snapshots
      add constraint fx_balk_duurt_een_minuut
      check (bar_start is null or bar_end is null
             or bar_end - bar_start = interval '1 minute');
  else
    raise notice
      'Er staan % dagkoersen waarvan de balk geen minuut duurt. Kijk daar '
      'eerst naar; zolang die er staan, wordt deze regel niet gezet.', scheef;
  end if;
end
$$;


-- ===========================================================================
-- C. DE STATUSMELDING
-- ===========================================================================
-- deur_versie 5. Staat er 4, dan is dit bestand niet gedraaid; staat er 4
-- terwijl dit bestand er wel was, dan is 04 er daarna nog eens over gegaan.
-- scripts/controleer_slot.py slaat in beide gevallen alarm.

create or replace function public.hardening_status()
returns jsonb
language sql
security definer
set search_path = public, privaat, pg_temp
as $$
  select jsonb_build_object(
    'deur_versie', 5,
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
    'wisselkoersbewijs_moet_kloppen', exists (
      select 1 from pg_trigger
      where tgname = 'wisselkoersbewijs_moet_kloppen'
        and tgrelid = 'public.executions'::regclass and not tgisinternal),
    'wisselkoersbewijs_staat_aan', exists (
      select 1 from pg_trigger
      where tgname = 'wisselkoersbewijs_moet_kloppen'
        and tgrelid = 'public.executions'::regclass and not tgisinternal
        and tgenabled <> 'D'),
    'fx_bewijs_verplicht', exists (
      select 1 from pg_trigger
      where tgname = 'fx_bewijs_verplicht'
        and tgrelid = 'public.executions'::regclass and not tgisinternal),
    'fx_bewijs_verplicht_staat_aan', exists (
      select 1 from pg_trigger
      where tgname = 'fx_bewijs_verplicht'
        and tgrelid = 'public.executions'::regclass and not tgisinternal
        and tgenabled <> 'D'),
    'fx_balk_duurt_een_minuut', exists (
      select 1 from pg_constraint
      where conname = 'fx_balk_duurt_een_minuut'
        and conrelid = 'public.fx_snapshots'::regclass),
    'dividend_betaaldatum_verplicht', (
      select a.attnotnull from pg_attribute a
      where a.attrelid = 'public.dividends'::regclass
        and a.attname = 'pay_date' and a.attnum > 0),
    'dividend_betaaldag_na_exdag', exists (
      select 1 from pg_constraint
      where conname = 'dividend_betaaldag_na_exdag'
        and conrelid = 'public.dividends'::regclass),
    'fx_spoor_kolommen', (
      select count(*) = 6 from pg_attribute
      where attrelid = 'public.fx_snapshots'::regclass and attnum > 0
        and attname in ('bar_start', 'bar_end', 'control_source',
                        'control_date', 'control_rate', 'control_deviation_pct')),
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
-- KLAAR
-- ===========================================================================
-- Nakijken met:
--   select public.hardening_status();        -> deur_versie 5
--   python scripts/controleer_slot.py        -> alle controles goed
