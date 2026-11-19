-- FingerForest 사용자 채팅(친구·대화방·쪽지). Supabase SQL Editor에서 한 번 실행.
-- 서버만(service role) 읽고 쓴다: RLS를 켜고 공개 정책은 만들지 않는다.
create table if not exists public.fruit_friends (
  owner text not null,
  friend text not null,
  friend_name text,
  status text not null check (status in ('pending', 'accepted', 'blocked')),
  requested_by text,
  updated_at timestamptz not null default now(),
  primary key (owner, friend)
);

create table if not exists public.fruit_rooms (
  id bigserial primary key,
  kind text not null check (kind in ('dm', 'group')),
  title text,
  dm_key text unique,
  created_by text,
  created_at timestamptz not null default now(),
  last_message_at timestamptz not null default now()
);

create table if not exists public.fruit_room_members (
  room_id bigint not null references public.fruit_rooms (id) on delete cascade,
  member text not null,
  member_name text,
  last_read_id bigint not null default 0,
  joined_at timestamptz not null default now(),
  primary key (room_id, member)
);
create index if not exists fruit_room_members_member_idx on public.fruit_room_members (member);

create table if not exists public.fruit_messages (
  id bigserial primary key,
  room_id bigint not null references public.fruit_rooms (id) on delete cascade,
  sender text not null,
  sender_name text,
  body text not null check (char_length(body) between 1 and 2000),
  created_at timestamptz not null default now()
);
create index if not exists fruit_messages_room_id_idx on public.fruit_messages (room_id, id);

create table if not exists public.fruit_notes (
  id bigserial primary key,
  sender text not null,
  sender_name text,
  recipient text not null,
  recipient_name text,
  body text not null check (char_length(body) between 1 and 2000),
  read_at timestamptz,
  created_at timestamptz not null default now()
);
create index if not exists fruit_notes_recipient_idx on public.fruit_notes (recipient, id desc);
create index if not exists fruit_notes_sender_idx on public.fruit_notes (sender, id desc);

alter table public.fruit_friends enable row level security;
alter table public.fruit_rooms enable row level security;
alter table public.fruit_room_members enable row level security;
alter table public.fruit_messages enable row level security;
alter table public.fruit_notes enable row level security;
