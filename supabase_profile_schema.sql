create table if not exists public.fruit_profiles (
  employee_id text primary key,
  name text,
  profile_image_path text,
  profile_image_url text,
  theme text not null default 'default',
  font text not null default 'pretendard',
  ui_settings jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

alter table public.fruit_profiles
  add column if not exists theme text not null default 'default',
  add column if not exists font text not null default 'pretendard',
  add column if not exists ui_settings jsonb not null default '{}'::jsonb;

alter table public.fruit_profiles enable row level security;

do $$
begin
  if not exists (
    select 1 from pg_policies
    where schemaname = 'public'
      and tablename = 'fruit_profiles'
      and policyname = 'fruit profiles are readable'
  ) then
    create policy "fruit profiles are readable"
      on public.fruit_profiles
      for select
      using (true);
  end if;
end $$;

insert into storage.buckets (id, name, public)
values ('profiles', 'profiles', true)
on conflict (id) do update set public = excluded.public;
