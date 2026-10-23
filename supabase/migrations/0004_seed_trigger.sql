-- Money Tracker — seed defaults for each new user
-- When someone signs up, give them a starter set of categories and a Cash
-- account so the app is usable immediately. Runs as a trigger on auth.users.
-- SECURITY DEFINER so it can write rows on the new user's behalf at signup.

create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
    insert into public.categories (user_id, name, kind) values
        (new.id, 'Salary',        'income'),
        (new.id, 'Freelance',     'income'),
        (new.id, 'Gift',          'income'),
        (new.id, 'Investment',    'income'),
        (new.id, 'Food',          'expense'),
        (new.id, 'Rent',          'expense'),
        (new.id, 'Transport',     'expense'),
        (new.id, 'Bills',         'expense'),
        (new.id, 'Shopping',      'expense'),
        (new.id, 'Health',        'expense'),
        (new.id, 'Entertainment', 'expense'),
        (new.id, 'Other',         'expense');

    insert into public.accounts (user_id, name, type, opening_balance) values
        (new.id, 'Cash', 'cash', 0);

    return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
    after insert on auth.users
    for each row execute function public.handle_new_user();
