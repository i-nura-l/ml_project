create extension if not exists pgcrypto;

create table if not exists public.allergy_assessments (
    id uuid primary key default gen_random_uuid(),
    created_at timestamptz not null default now(),
    birth_year integer not null,
    gender_factor text not null,
    race_factor text not null,
    ethnicity_factor text not null default 'E0 - Non-Hispanic',
    has_asthma boolean not null default false,
    has_eczema boolean not null default false,
    raw_input jsonb not null,
    predicted_risks jsonb not null,
    model_version text not null default 'allergy_predictor_v1'
);

alter table public.allergy_assessments enable row level security;

drop policy if exists "Allow anon insert" on public.allergy_assessments;
create policy "Allow anon insert"
on public.allergy_assessments
for insert
to anon
with check (true);

drop policy if exists "Allow anon read" on public.allergy_assessments;
create policy "Allow anon read"
on public.allergy_assessments
for select
to anon
using (true);