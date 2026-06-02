-- supabase/migrations/20260602000001_initial.sql

create table if not exists users (
  id bigint primary key,           -- Telegram user ID
  username text,                    -- Telegram @handle (without @)
  created_at timestamptz default now()
);

create table if not exists binders (
  id uuid primary key default gen_random_uuid(),
  user_id bigint not null references users(id) on delete cascade,
  url text not null,
  last_scraped_at timestamptz,
  created_at timestamptz default now(),
  unique(user_id, url)
);

create table if not exists binder_cards (
  id uuid primary key default gen_random_uuid(),
  binder_id uuid not null references binders(id) on delete cascade,
  card_name text not null,         -- stored lowercase + trimmed
  quantity int not null default 1,
  updated_at timestamptz default now()
);

create index if not exists binder_cards_card_name_idx
  on binder_cards using gin(to_tsvector('simple', card_name));

-- Also a plain btree for ILIKE queries
create index if not exists binder_cards_card_name_btree
  on binder_cards (card_name text_pattern_ops);
