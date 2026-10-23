-- Money Tracker — schema
-- Run this in the Supabase SQL editor (or via `supabase db push`).
-- All money is stored as exact decimals (numeric), never floating point.

create extension if not exists "pgcrypto";   -- for gen_random_uuid()

-- Accounts: cash, bank, card, wallet -----------------------------------------
create table if not exists public.accounts (
    id              uuid primary key default gen_random_uuid(),
    user_id         uuid not null default auth.uid() references auth.users (id) on delete cascade,
    name            text not null,
    type            text not null check (type in ('cash', 'bank', 'card', 'wallet')),
    opening_balance numeric(14, 2) not null default 0,
    created_at      timestamptz not null default now()
);
create index if not exists accounts_user_idx on public.accounts (user_id);

-- Categories: each belongs to a user and is income or expense ----------------
create table if not exists public.categories (
    id      uuid primary key default gen_random_uuid(),
    user_id uuid not null default auth.uid() references auth.users (id) on delete cascade,
    name    text not null,
    kind    text not null check (kind in ('income', 'expense')),
    unique (user_id, name, kind)
);
create index if not exists categories_user_idx on public.categories (user_id);

-- Transactions ---------------------------------------------------------------
-- income  : money into account_id, needs a category
-- expense : money out of account_id, needs a category
-- transfer: account_id -> to_account_id, no category (not counted as spending)
create table if not exists public.transactions (
    id             uuid primary key default gen_random_uuid(),
    user_id        uuid not null default auth.uid() references auth.users (id) on delete cascade,
    occurred_on    date not null default current_date,
    amount         numeric(14, 2) not null check (amount > 0),
    type           text not null check (type in ('income', 'expense', 'transfer')),
    account_id     uuid not null references public.accounts (id) on delete cascade,
    to_account_id  uuid references public.accounts (id) on delete cascade,
    category_id    uuid references public.categories (id) on delete set null,
    note           text not null default '',
    created_at     timestamptz not null default now(),

    -- a transfer needs a destination account and no category;
    -- income/expense needs a category and no destination account
    constraint transaction_shape check (
        (type = 'transfer'
            and to_account_id is not null
            and to_account_id <> account_id
            and category_id is null)
        or
        (type in ('income', 'expense')
            and to_account_id is null
            and category_id is not null)
    )
);
create index if not exists transactions_user_idx  on public.transactions (user_id);
create index if not exists transactions_month_idx on public.transactions (user_id, occurred_on);

-- Budgets: one monthly limit per expense category, repeats every month -------
create table if not exists public.budgets (
    id            uuid primary key default gen_random_uuid(),
    user_id       uuid not null default auth.uid() references auth.users (id) on delete cascade,
    category_id   uuid not null references public.categories (id) on delete cascade,
    monthly_limit numeric(14, 2) not null check (monthly_limit > 0),
    unique (user_id, category_id)
);
create index if not exists budgets_user_idx on public.budgets (user_id);
