create schema if not exists tenancy;

create table if not exists tenancy.tenants (
    tenant_id text primary key,
    name text not null,
    region text
);

create table if not exists tenancy.users (
    user_id text primary key,
    tenant_id text not null references tenancy.tenants (tenant_id),
    display_name text not null,
    role text not null check (role in ('pharmacist', 'procurement', 'clinician', 'executive'))
);

create table if not exists tenancy.formulary (
    tenant_id text not null references tenancy.tenants (tenant_id),
    drug_rxcui text not null,
    drug_name text not null,
    on_hand_units int not null,
    avg_daily_units numeric not null,
    primary key (tenant_id, drug_rxcui)
);

create table if not exists tenancy.contracts (
    tenant_id text not null references tenancy.tenants (tenant_id),
    drug_rxcui text not null,
    supplier text not null,
    unit_price numeric(10, 2) not null,
    contract_end date not null,
    primary key (tenant_id, drug_rxcui)
);

create table if not exists tenancy.audit_log (
    audit_id bigint generated always as identity primary key,
    occurred_at timestamptz not null default now(),
    tenant_id text not null,
    user_id text not null,
    role text not null,
    action text not null,
    question text,
    resources jsonb,
    outcome text
);

create or replace function tenancy.session_tenant() returns text
language sql stable security definer set search_path = tenancy as $$
    select tenant_id from tenancy.users where user_id = current_setting('app.user_id', true)
$$;

create or replace function tenancy.session_role() returns text
language sql stable security definer set search_path = tenancy as $$
    select role from tenancy.users where user_id = current_setting('app.user_id', true)
$$;

revoke all on function tenancy.session_tenant(), tenancy.session_role() from public;
grant execute on function tenancy.session_tenant(), tenancy.session_role() to rxshield_app;

alter table tenancy.tenants enable row level security;
drop policy if exists tenant_isolation on tenancy.tenants;
create policy tenant_isolation on tenancy.tenants
    using (tenant_id = tenancy.session_tenant());

alter table tenancy.users enable row level security;
drop policy if exists tenant_isolation on tenancy.users;
create policy tenant_isolation on tenancy.users
    using (tenant_id = tenancy.session_tenant());

alter table tenancy.formulary enable row level security;
drop policy if exists formulary_read on tenancy.formulary;
create policy formulary_read on tenancy.formulary for select
    using (tenant_id = tenancy.session_tenant()
           and tenancy.session_role() in ('pharmacist', 'procurement', 'executive'));

alter table tenancy.contracts enable row level security;
drop policy if exists contracts_read on tenancy.contracts;
create policy contracts_read on tenancy.contracts for select
    using (tenant_id = tenancy.session_tenant()
           and tenancy.session_role() in ('procurement', 'executive'));

alter table tenancy.audit_log enable row level security;
drop policy if exists audit_insert on tenancy.audit_log;
create policy audit_insert on tenancy.audit_log for insert
    with check (tenant_id = tenancy.session_tenant()
                and user_id = current_setting('app.user_id', true)
                and role = tenancy.session_role());
drop policy if exists audit_read on tenancy.audit_log;
create policy audit_read on tenancy.audit_log for select
    using (tenant_id = tenancy.session_tenant() and tenancy.session_role() = 'executive');

grant usage on schema tenancy, analytics, rag, extensions to rxshield_app;
grant select on tenancy.tenants, tenancy.users, tenancy.formulary, tenancy.contracts to rxshield_app;
grant select, insert on tenancy.audit_log to rxshield_app;
grant usage on all sequences in schema tenancy to rxshield_app;
grant select on all tables in schema analytics, rag to rxshield_app;
alter default privileges in schema analytics grant select on tables to rxshield_app;
alter default privileges in schema rag grant select on tables to rxshield_app;

create table if not exists rag.answer_cache (
    cache_id bigint generated always as identity primary key,
    scope_tenant text not null references tenancy.tenants (tenant_id),
    scope_role text not null,
    signature text not null,
    question text not null,
    embedding extensions.vector(384) not null,
    answer jsonb not null,
    data_version text not null,
    created_at timestamptz not null default now()
);
create index if not exists answer_cache_lookup on rag.answer_cache (signature, data_version);

alter table rag.answer_cache enable row level security;
drop policy if exists cache_read on rag.answer_cache;
create policy cache_read on rag.answer_cache for select
    using (scope_tenant = tenancy.session_tenant() and scope_role = tenancy.session_role());
drop policy if exists cache_write on rag.answer_cache;
create policy cache_write on rag.answer_cache for insert
    with check (scope_tenant = tenancy.session_tenant() and scope_role = tenancy.session_role());

grant select, insert on rag.answer_cache to rxshield_app;
grant usage on all sequences in schema rag to rxshield_app;