-- Money Tracker — schema, security and money-logic test.
--
-- This runs the real migrations against a local PostgreSQL, mocking the small
-- part of Supabase we depend on (the `auth` schema and `auth.uid()`), then
-- checks that:
--   * new users get seeded categories and a Cash account,
--   * Row Level Security isolates one user's data from another's,
--   * account balances, the dashboard summary and budgets compute correctly,
--   * the transaction shape constraints reject bad rows.
--
-- Run it with tests/run.sh (which starts a throwaway Postgres).

\set ON_ERROR_STOP on
\set A '11111111-1111-1111-1111-111111111111'
\set B '22222222-2222-2222-2222-222222222222'

-- ---- Mock the parts of Supabase we rely on --------------------------------
create schema if not exists auth;
create table if not exists auth.users (id uuid primary key default gen_random_uuid(), email text);
create or replace function auth.uid() returns uuid language sql stable as
$$ select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $$;

drop role if exists app_user;
create role app_user nologin;
grant usage on schema public, auth to app_user;
grant select on auth.users to app_user;

-- ---- The real migrations ---------------------------------------------------
\i migrations/0001_schema.sql
\i migrations/0002_rls.sql
\i migrations/0003_functions.sql
\i migrations/0004_seed_trigger.sql

grant select, insert, update, delete on all tables in schema public to app_user;
grant execute on all routines in schema public to app_user;

-- ---- Two users; the trigger seeds their categories + Cash account ----------
insert into auth.users (id, email) values (:'A', 'a@x.com'), (:'B', 'b@x.com');

do $$
declare n int;
begin
    select count(*) into n from public.categories
        where user_id = '11111111-1111-1111-1111-111111111111';
    assert n = 12, format('expected 12 seeded categories, got %s', n);
    select count(*) into n from public.accounts
        where user_id = '11111111-1111-1111-1111-111111111111';
    assert n = 1, format('expected 1 seeded account, got %s', n);
end $$;

-- ---- Act as user A, through RLS -------------------------------------------
set role app_user;
set request.jwt.claim.sub = :'A';

insert into public.accounts (name, type, opening_balance) values ('HDFC', 'bank', 5000);
insert into public.transactions (amount, type, account_id, category_id)
    select 60000, 'income', (select id from accounts where name='HDFC'),
           (select id from categories where name='Salary' and kind='income');
insert into public.transactions (amount, type, account_id, category_id)
    select 1500, 'expense', (select id from accounts where name='HDFC'),
           (select id from categories where name='Food' and kind='expense');
insert into public.transactions (amount, type, account_id, to_account_id)
    select 2000, 'transfer', (select id from accounts where name='HDFC'),
           (select id from accounts where name='Cash');

do $$
declare hdfc numeric; cash numeric; total numeric; inc numeric; exp numeric;
begin
    select balance into hdfc from public.account_balances() where name='HDFC';
    select balance into cash from public.account_balances() where name='Cash';
    assert hdfc = 61500, format('HDFC balance wrong: %s', hdfc);  -- 5000+60000-1500-2000
    assert cash = 2000,  format('Cash balance wrong: %s', cash);  -- 0+2000

    select total_balance, month_income, month_expense into total, inc, exp
        from public.dashboard_summary(to_char(current_date,'YYYY-MM'));
    assert total = 63500, format('total balance wrong: %s', total);
    assert inc = 60000,   format('income wrong: %s', inc);
    assert exp = 1500,    format('expense wrong: %s', exp);
end $$;

insert into public.budgets (category_id, monthly_limit)
    select id, 3000 from categories where name='Food' and kind='expense';

do $$
declare v_lim numeric; v_spent numeric;
begin
    select monthly_limit, spent into v_lim, v_spent
        from public.budget_status(to_char(current_date,'YYYY-MM')) where category='Food';
    assert v_lim = 3000,   format('budget limit wrong: %s', v_lim);
    assert v_spent = 1500, format('budget spent wrong: %s', v_spent);
end $$;

-- ---- User B must see none of A's data -------------------------------------
set request.jwt.claim.sub = :'B';
do $$
declare txs int; accs int;
begin
    select count(*) into txs from public.transactions;
    assert txs = 0, format('RLS leak: B sees %s of A''s transactions', txs);
    select count(*) into accs from public.accounts;
    assert accs = 1, format('RLS: B should see only own Cash, saw %s accounts', accs);
    assert (select name from public.accounts) = 'Cash', 'B sees an account that is not theirs';
end $$;

-- ---- Constraint checks (as A) ---------------------------------------------
set request.jwt.claim.sub = :'A';
do $$ begin
    insert into public.transactions(amount, type, account_id, category_id)
        select -5, 'expense', (select id from accounts where name='Cash'),
               (select id from categories where name='Food' limit 1);
    raise exception 'negative amount should have been rejected';
exception when check_violation then null; end $$;

do $$ begin
    insert into public.transactions(amount, type, account_id, to_account_id, category_id)
        select 10, 'transfer', (select id from accounts where name='Cash'),
               (select id from accounts where name='HDFC'),
               (select id from categories where name='Food' limit 1);
    raise exception 'transfer with a category should have been rejected';
exception when check_violation then null; end $$;

reset role;
\echo ''
\echo '================================'
\echo '  ALL TESTS PASSED'
\echo '================================'
