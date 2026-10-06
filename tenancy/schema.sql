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

create schema if not exists ops;

create table if not exists ops.llm_calls (
    call_id bigint generated always as identity primary key,
    occurred_at timestamptz not null default now(),
    caller text not null,
    model text not null,
    prompt_tokens int not null,
    completion_tokens int not null,
    latency_ms int not null,
    finish_reason text,
    attempts int not null,
    succeeded boolean not null
);

grant usage on schema ops to rxshield_app;
grant insert on ops.llm_calls to rxshield_app;
grant usage on all sequences in schema ops to rxshield_app;

create index if not exists audit_log_tenant_time on tenancy.audit_log (tenant_id, occurred_at);

create or replace function tenancy.recent_answer_counts(window_seconds int)
returns table (user_requests bigint, tenant_requests bigint)
language sql stable security definer set search_path = tenancy as $$
    select count(*) filter (where user_id = current_setting('app.user_id', true)),
           count(*)
    from tenancy.audit_log
    where tenant_id = tenancy.session_tenant()
      and action = 'answer'
      and occurred_at > now() - make_interval(secs => window_seconds)
$$;
revoke all on function tenancy.recent_answer_counts(int) from public;
grant execute on function tenancy.recent_answer_counts(int) to rxshield_app;

create schema if not exists ml;
grant usage on schema ml to rxshield_app;
grant select on all tables in schema ml to rxshield_app;
alter default privileges in schema ml grant select on tables to rxshield_app;

create table if not exists tenancy.agent_actions (
    action_id bigint generated always as identity primary key,
    tenant_id text not null references tenancy.tenants (tenant_id),
    created_by text not null,
    action_type text not null,
    subject text not null,
    draft text not null,
    evidence jsonb,
    status text not null default 'pending_approval'
        check (status in ('pending_approval', 'approved', 'rejected')),
    reviewed_by text,
    review_note text,
    created_at timestamptz not null default now(),
    reviewed_at timestamptz
);

alter table tenancy.agent_actions enable row level security;

drop policy if exists actions_read on tenancy.agent_actions;
create policy actions_read on tenancy.agent_actions for select
    using (tenant_id = tenancy.session_tenant()
           and tenancy.session_role() in ('pharmacist', 'procurement', 'executive'));

drop policy if exists actions_create on tenancy.agent_actions;
create policy actions_create on tenancy.agent_actions for insert
    with check (tenant_id = tenancy.session_tenant()
                and created_by = current_setting('app.user_id', true)
                and status = 'pending_approval'
                and tenancy.session_role() in ('pharmacist', 'procurement', 'executive'));

drop policy if exists actions_review on tenancy.agent_actions;
create policy actions_review on tenancy.agent_actions for update
    using (tenant_id = tenancy.session_tenant()
           and status = 'pending_approval'
           and tenancy.session_role() in ('pharmacist', 'executive'))
    with check (tenant_id = tenancy.session_tenant()
                and status in ('approved', 'rejected')
                and reviewed_by = current_setting('app.user_id', true)
                and reviewed_by <> created_by);

grant select, insert on tenancy.agent_actions to rxshield_app;
grant update (status, reviewed_by, review_note, reviewed_at) on tenancy.agent_actions to rxshield_app;