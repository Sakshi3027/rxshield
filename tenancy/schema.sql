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

alter table tenancy.tenants enable row level security;
drop policy if exists tenant_isolation on tenancy.tenants;
create policy tenant_isolation on tenancy.tenants
    using (tenant_id = current_setting('app.tenant_id', true));

alter table tenancy.users enable row level security;
drop policy if exists tenant_isolation on tenancy.users;
create policy tenant_isolation on tenancy.users
    using (tenant_id = current_setting('app.tenant_id', true));

alter table tenancy.audit_log enable row level security;
drop policy if exists audit_insert on tenancy.audit_log;
create policy audit_insert on tenancy.audit_log for insert
    with check (tenant_id = current_setting('app.tenant_id', true));
drop policy if exists audit_read on tenancy.audit_log;
create policy audit_read on tenancy.audit_log for select
    using (tenant_id = current_setting('app.tenant_id', true));

grant usage on schema tenancy, analytics, rag, extensions to rxshield_app;
grant select on tenancy.tenants, tenancy.users to rxshield_app;
grant select, insert on tenancy.audit_log to rxshield_app;
grant usage on all sequences in schema tenancy to rxshield_app;
grant select on all tables in schema analytics, rag to rxshield_app;
alter default privileges in schema analytics grant select on tables to rxshield_app;
alter default privileges in schema rag grant select on tables to rxshield_app;