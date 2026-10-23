-- Money Tracker — reporting functions
-- These run with the caller's permissions (security invoker), so Row Level
-- Security still applies: each function only ever sees the caller's own rows.
-- The browser calls these with supabase.rpc('name', { ... }).

-- Current balance of every account:
--   opening balance
--   + income into it            + transfers into it
--   - expense out of it         - transfers out of it
create or replace function public.account_balances()
returns table (id uuid, name text, type text, balance numeric)
language sql stable security invoker
as $$
    select a.id, a.name, a.type,
        a.opening_balance
        + coalesce((select sum(t.amount) from public.transactions t
                    where t.account_id = a.id and t.type = 'income'), 0)
        - coalesce((select sum(t.amount) from public.transactions t
                    where t.account_id = a.id and t.type = 'expense'), 0)
        - coalesce((select sum(t.amount) from public.transactions t
                    where t.account_id = a.id and t.type = 'transfer'), 0)
        + coalesce((select sum(t.amount) from public.transactions t
                    where t.to_account_id = a.id and t.type = 'transfer'), 0)
        as balance
    from public.accounts a
    order by a.name;
$$;

-- Totals for the dashboard for a given month ('YYYY-MM').
create or replace function public.dashboard_summary(p_month text)
returns table (total_balance numeric, month_income numeric, month_expense numeric)
language sql stable security invoker
as $$
    select
        coalesce((select sum(b.balance) from public.account_balances() b), 0),
        coalesce((select sum(amount) from public.transactions
                  where type = 'income'  and to_char(occurred_on, 'YYYY-MM') = p_month), 0),
        coalesce((select sum(amount) from public.transactions
                  where type = 'expense' and to_char(occurred_on, 'YYYY-MM') = p_month), 0);
$$;

-- Expense total per category for a month, biggest first.
create or replace function public.spending_by_category(p_month text)
returns table (category text, total numeric)
language sql stable security invoker
as $$
    select c.name, sum(t.amount) as total
    from public.transactions t
    join public.categories c on c.id = t.category_id
    where t.type = 'expense' and to_char(t.occurred_on, 'YYYY-MM') = p_month
    group by c.name
    order by total desc;
$$;

-- Budget vs. actual spending for a month.
create or replace function public.budget_status(p_month text)
returns table (category text, monthly_limit numeric, spent numeric)
language sql stable security invoker
as $$
    select c.name, b.monthly_limit,
        coalesce((select sum(t.amount) from public.transactions t
                  where t.category_id = b.category_id
                    and t.type = 'expense'
                    and to_char(t.occurred_on, 'YYYY-MM') = p_month), 0) as spent
    from public.budgets b
    join public.categories c on c.id = b.category_id
    order by c.name;
$$;

-- Income and expense totals for the last 12 months (oldest first).
create or replace function public.monthly_totals()
returns table (month text, income numeric, expense numeric)
language sql stable security invoker
as $$
    with months as (
        select to_char(date_trunc('month', current_date) - (n || ' months')::interval,
                       'YYYY-MM') as m
        from generate_series(0, 11) as n
    )
    select m,
        coalesce((select sum(amount) from public.transactions
                  where type = 'income'  and to_char(occurred_on, 'YYYY-MM') = m), 0),
        coalesce((select sum(amount) from public.transactions
                  where type = 'expense' and to_char(occurred_on, 'YYYY-MM') = m), 0)
    from months
    order by m;
$$;
