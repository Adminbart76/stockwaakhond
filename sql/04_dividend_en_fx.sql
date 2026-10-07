-- ===========================================================================
-- StockWaakhond V7.1 - 04: de betaaldatum van een dividend en het spoor van
--                          de wisselkoers
-- ===========================================================================
-- Hoort NA 01_schema.sql, 02_hardening.sql en 03_smalle_deur.sql te draaien.
-- Dit bestand voegt alleen toe: een kolom, een paar kolommen, een extra
-- wachter en een nieuwere statusmelding. Het vervangt geen enkele functie uit
-- 03, zodat de volgorde 02-03 niet opnieuw een valkuil wordt. Opnieuw draaien
-- is veilig en verandert geen bestaande rij.
--
-- Waarom dit nodig is (beslissingen van 7 oktober 2026)
-- =====================================================
-- A. Een dividend heeft TWEE datums die niet door elkaar mogen:
--
--      ex_date    de dag waarop het recht ontstaat. Wie het aandeel voor die
--                 dag bezat, krijgt het dividend - ook als hij het daarna
--                 verkoopt.
--      pay_date   de dag waarop het geld er werkelijk is.
--
--    Daar zitten twee tot zes weken tussen. Zou het geld op de ex-dag als
--    contant geld meegerekend worden, dan belegt de portefeuille bij een
--    wissel geld dat ze nog niet heeft. En zou het recht op de betaaldag
--    bepaald worden, dan verdwijnt het dividend van een aandeel dat tussen de
--    twee datums verkocht is.
--
--    Daarom is de betaaldatum verplicht. Zonder die datum is niet bekend bij
--    welke wissel het geld meegaat, en dan wordt er niets geschat.
--
-- B. De wisselkoers van een uitvoeringsdag is sinds 7 oktober 2026 de laatste
--    volledig afgesloten 1-minuutbalk van EURUSD=X waarvan het interval
--    eindigt op of voor 16:00:00 in New York, met de ECB-referentiekoers van
--    die dag als onafhankelijk controlegetal. Die twee horen bewaard te
--    worden: Yahoo bewaart minuutgegevens ongeveer dertig dagen, de ECB
--    bewaart haar reeks voor altijd.
--
--    De kolom fx_asof blijft wat ze was: het moment waarop WIJ de koers
--    gelezen hebben, met het venster uit 02/03 eromheen. Het moment waar de
--    koers BIJ HOORT is iets anders en krijgt zijn eigen kolommen.


-- ===========================================================================
-- A. DE BETAALDATUM VAN EEN DIVIDEND
-- ===========================================================================

alter table public.dividends
  add column if not exists pay_date date;

comment on column public.dividends.pay_date is
  'De dag waarop het geld beschikbaar is. Het recht ontstaat op ex_date.';

comment on column public.dividends.net_per_share_usd is
  'Informatie, geen rekenbasis: de officiele curve rekent sinds 7 oktober 2026 bruto.';

-- De betaaldatum kan niet voor de ex-datum liggen. Een van de twee is dan
-- verkeerd ingevuld, en dat hoort op te vallen voor er een wissel op rust.
do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conname = 'dividend_betaaldag_na_exdag'
      and conrelid = 'public.dividends'::regclass
  ) then
    alter table public.dividends
      add constraint dividend_betaaldag_na_exdag
      check (pay_date is null or pay_date >= ex_date);
  end if;
end
$$;

-- De kolom verplicht maken kan alleen als er geen rij zonder betaaldatum
-- staat. Is die er wel, dan hoort hier niets stilletjes gevuld te worden: dan
-- moet iemand opzoeken wanneer dat dividend betaald is.
do $$
declare
  zonder integer;
begin
  select count(*) into zonder from public.dividends where pay_date is null;

  if zonder = 0 then
    begin
      alter table public.dividends alter column pay_date set not null;
    exception when others then
      raise notice 'pay_date kon niet verplicht gemaakt worden: %', sqlerrm;
    end;
  else
    raise notice
      'Er staan % dividendrijen zonder betaaldatum. Vul die eerst in met '
      'scripts/leg_dividend_vast.py; daarna maakt dit bestand de kolom '
      'verplicht.', zonder;
  end if;
end
$$;


-- ===========================================================================
-- B. HET SPOOR VAN DE WISSELKOERS
-- ===========================================================================
-- Vier kolommen bij de dagelijkse wisselkoers, en vier bij het controlegetal.
-- Allemaal optioneel: de dagkoersen die de dagelijkse taak wegschrijft hebben
-- geen minuutbalk nodig, alleen een uitvoeringsdag heeft dat.

alter table public.fx_snapshots
  add column if not exists bar_start             timestamptz,
  add column if not exists bar_end               timestamptz,
  add column if not exists control_source        text,
  add column if not exists control_date          date,
  add column if not exists control_rate          numeric,
  add column if not exists control_deviation_pct numeric;

comment on column public.fx_snapshots.bar_end is
  'Einde van de 1-minuutbalk: het moment waar deze koers bij hoort (16:00 New York).';
comment on column public.fx_snapshots.control_rate is
  'ECB-referentiekoers van die dag: onafhankelijk controlegetal, geen rekenbasis.';

do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conname = 'fx_balk_eindigt_na_begin'
      and conrelid = 'public.fx_snapshots'::regclass
  ) then
    alter table public.fx_snapshots
      add constraint fx_balk_eindigt_na_begin
      check (bar_start is null or bar_end is null or bar_end > bar_start);
  end if;

  if not exists (
    select 1 from pg_constraint
    where conname = 'fx_controlegetal_positief'
      and conrelid = 'public.fx_snapshots'::regclass
  ) then
    alter table public.fx_snapshots
      add constraint fx_controlegetal_positief
      check (control_rate is null or control_rate > 0);
  end if;
end
$$;


-- ===========================================================================
-- C. EEN EXTRA WACHTER OP DE UITVOERING
-- ===========================================================================
-- Met opzet een APARTE trigger en geen nieuwe versie van
-- controleer_uitvoering(): zo hoeft 03 niet opnieuw te draaien na dit bestand,
-- en kan de volgorde van de bestanden geen stille regressie geven.
--
-- Wat hier nagerekend wordt, en alleen als het record het zelf beweert (de
-- uitvoering van 6 oktober 2026 kent deze velden niet en blijft dus precies
-- zoals ze is):
--
--   1. de minuutbalk eindigt op of voor de slotbel, en hoogstens vijf minuten
--      ervoor. Een balk na de slotbel bevat handel die de slotkoersen niet
--      kennen; een balk van een halfuur eerder is geen slotkoers meer.
--   2. het controlegetal van de ECB wijkt niet meer dan 1 procent af. Zo groot
--      is geen dagbeweging tussen Frankfurt en New York; dat is een fout in de
--      gegevens.

create or replace function public.controleer_wisselkoersbewijs()
returns trigger
language plpgsql
as $$
declare
  inhoud   jsonb := new.canonical_payload::jsonb;
  slotbel  timestamptz;
  eind     timestamptz;
  controle numeric;
  afwijking numeric;
begin
  slotbel := (new.execution_date::text || ' 16:00')::timestamp
             at time zone 'America/New_York';

  if inhoud ? 'fx_bar_end' then
    eind := (inhoud->>'fx_bar_end')::timestamptz;

    if eind > slotbel then
      raise exception 'De minuutbalk eindigt om % en dat is na de slotbel van % (%).',
        eind, new.execution_date, slotbel
        using hint =
          'Een balk na de slotbel bevat handel die de slotkoersen niet kennen.';
    end if;

    if eind < slotbel - interval '5 minutes' then
      raise exception 'De minuutbalk eindigt om %, meer dan vijf minuten voor de slotbel (%).',
        eind, slotbel
        using hint =
          'De regel laat hoogstens vijf minuten terugval toe; daarbuiten hoort '
          'een mens ernaar te kijken.';
    end if;
  end if;

  if inhoud ? 'fx_control_rate' then
    controle := (inhoud->>'fx_control_rate')::numeric;
    if controle is null or controle <= 0 then
      raise exception 'Het controlegetal van de wisselkoers is geen koers (%).', controle;
    end if;

    afwijking := abs(new.fx_rate / controle - 1) * 100;
    if afwijking > 1 then
      raise exception
        'De wisselkoers (%) wijkt % procent af van het controlegetal (%).',
        new.fx_rate, round(afwijking, 3), controle
        using hint =
          'Meer dan een procent verschil met de ECB-referentiekoers is geen '
          'dagbeweging maar een fout in de gegevens.';
    end if;
  end if;

  return new;
end;
$$;

comment on function public.controleer_wisselkoersbewijs() is
  'Rekent de minuutbalk en het ECB-controlegetal van een uitvoering na.';

drop trigger if exists wisselkoersbewijs_moet_kloppen on public.executions;
create trigger wisselkoersbewijs_moet_kloppen
  before insert on public.executions
  for each row execute function public.controleer_wisselkoersbewijs();


-- ===========================================================================
-- D. DE STATUSMELDING
-- ===========================================================================
-- deur_versie 4. Staat er 3, dan is dit bestand niet gedraaid; staat er 3
-- terwijl dit bestand er wel was, dan is 03 er daarna nog eens over gegaan.
-- scripts/controleer_slot.py slaat in beide gevallen alarm.

create or replace function public.hardening_status()
returns jsonb
language sql
security definer
set search_path = public, privaat, pg_temp
as $$
  select jsonb_build_object(
    'deur_versie', 4,
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
--   select public.hardening_status();        -> deur_versie 4
--   python scripts/controleer_slot.py        -> alle controles goed
