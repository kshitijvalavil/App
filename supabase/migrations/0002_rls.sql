-- Money Tracker — Row Level Security
-- Every table is locked down so each signed-in user can only read and write
-- their own rows. The database enforces this, not just the app.

alter table public.accounts     enable row level security;
alter table public.categories   enable row level security;
alter table public.transactions enable row level security;
alter table public.budgets      enable row level security;

-- Helper: one policy set per table. "auth.uid()" is the id of the signed-in
-- user; it is null for anonymous requests, so those match nothing.

-- accounts -------------------------------------------------------------------
create policy "own accounts - select" on public.accounts
    for select using (auth.uid() = user_id);
create policy "own accounts - insert" on public.accounts
    for insert with check (auth.uid() = user_id);
create policy "own accounts - update" on public.accounts
    for update using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "own accounts - delete" on public.accounts
    for delete using (auth.uid() = user_id);

-- categories -----------------------------------------------------------------
create policy "own categories - select" on public.categories
    for select using (auth.uid() = user_id);
create policy "own categories - insert" on public.categories
    for insert with check (auth.uid() = user_id);
create policy "own categories - update" on public.categories
    for update using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "own categories - delete" on public.categories
    for delete using (auth.uid() = user_id);

-- transactions ---------------------------------------------------------------
create policy "own transactions - select" on public.transactions
    for select using (auth.uid() = user_id);
create policy "own transactions - insert" on public.transactions
    for insert with check (auth.uid() = user_id);
create policy "own transactions - update" on public.transactions
    for update using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "own transactions - delete" on public.transactions
    for delete using (auth.uid() = user_id);

-- budgets --------------------------------------------------------------------
create policy "own budgets - select" on public.budgets
    for select using (auth.uid() = user_id);
create policy "own budgets - insert" on public.budgets
    for insert with check (auth.uid() = user_id);
create policy "own budgets - update" on public.budgets
    for update using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "own budgets - delete" on public.budgets
    for delete using (auth.uid() = user_id);
