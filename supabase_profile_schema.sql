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

create table if not exists public.fruit_chat_messages (
  id bigserial primary key,
  user_key text not null,
  name text,
  role text not null check (role in ('user', 'assistant')),
  content text not null,
  model text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists fruit_chat_messages_user_created_idx
  on public.fruit_chat_messages (user_key, created_at desc);

create index if not exists fruit_chat_messages_user_id_idx
  on public.fruit_chat_messages (user_key, id);

alter table public.fruit_chat_messages enable row level security;

do $$
begin
  if not exists (
    select 1 from pg_policies
    where schemaname = 'public'
      and tablename = 'fruit_chat_messages'
      and policyname = 'fruit chat messages service role only'
  ) then
    create policy "fruit chat messages service role only"
      on public.fruit_chat_messages
      for all
      using (auth.role() = 'service_role')
      with check (auth.role() = 'service_role');
  end if;
end $$;

create table if not exists public.fruit_chat_memories (
  user_key text primary key,
  name text,
  summary text not null default '',
  summarized_message_id bigint,
  updated_at timestamptz not null default now()
);

alter table public.fruit_chat_memories enable row level security;

do $$
begin
  if not exists (
    select 1 from pg_policies
    where schemaname = 'public'
      and tablename = 'fruit_chat_memories'
      and policyname = 'fruit chat memories service role only'
  ) then
    create policy "fruit chat memories service role only"
      on public.fruit_chat_memories
      for all
      using (auth.role() = 'service_role')
      with check (auth.role() = 'service_role');
  end if;
end $$;
