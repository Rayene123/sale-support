
-- Person 2: Sale Support Sandbox
-- PostgreSQL schema for the dedicated Supabase sandbox.
-- Never apply this schema to a production database.

create table if not exists clients (
    customer_id text primary key,
    email text not null,
    display_name text not null,
    contact_channel text not null
        check (contact_channel in ('email', 'phone', 'chat')),
    account_status text not null
        check (account_status in ('active', 'suspended', 'closed')),
    relevant_notes text not null default '',
    created_at timestamptz not null default now()
);

create unique index if not exists clients_email_lower_unique
    on clients (lower(email));


create table if not exists orders (
    order_id text primary key,
    customer_id text not null references clients(customer_id),
    order_status text not null
        check (order_status in (
            'pending', 'confirmed', 'processing',
            'shipped', 'delivered', 'cancelled'
        )),
    item_summary text not null,
    total_amount numeric(12, 2) not null check (total_amount >= 0),
    currency text not null default 'TND',
    shipment_status text not null
        check (shipment_status in (
            'not_shipped', 'in_transit', 'delayed',
            'delivered', 'cancelled', 'returned'
        )),
    ordered_at timestamptz not null,
    shipped_at timestamptz,
    delivered_at timestamptz,
    -- Populated only for internally approved sandbox proposals. Fixture rows
    -- retain their existing legacy order representation.
    operation_id text,
    source_snapshot jsonb,
    approval_id text,
    created_at timestamptz not null default now()
);

create unique index if not exists orders_operation_id_unique
    on orders(operation_id) where operation_id is not null;


create table if not exists tickets (
    ticket_id text primary key,

    -- Intentionally not foreign keys:
    -- fixtures must support missing customer/order references.
    customer_id text,
    order_id text,

    body text not null,
    labels text[] not null default '{}',
    status text not null default 'open'
    check (status in (
        'open', 'in_progress', 'pending',
        'resolved', 'closed', 'delivered',
        'delayed', 'cancelled', 'refund_requested'
    )),
    response_history jsonb not null default '[]'::jsonb,
    created_at timestamptz not null
);


create table if not exists refund_requests (
    refund_id uuid primary key default gen_random_uuid(),
    ticket_id text not null references tickets(ticket_id),
    order_id text not null references orders(order_id),
    operation_id text not null,
    amount numeric(12, 2) not null check (amount > 0),
    reason text not null,
    status text not null default 'pending'
        check (status in ('pending', 'approved', 'rejected', 'cancelled')),
    created_at timestamptz not null default now(),
    unique (operation_id)
);


create table if not exists escalation_tasks (
    escalation_id uuid primary key default gen_random_uuid(),
    ticket_id text not null references tickets(ticket_id),
    operation_id text not null unique,
    team text not null
        check (team in ('billing', 'shipping', 'technical', 'general')),
    priority text not null
        check (priority in ('low', 'medium', 'high', 'urgent')),
    reason text not null,
    due_at timestamptz not null,
    status text not null default 'pending'
        check (status in ('pending', 'in_progress', 'completed', 'cancelled')),
    created_at timestamptz not null default now()
);


create table if not exists notification_outbox (
    notification_id uuid primary key default gen_random_uuid(),
    -- Deliberately soft references: the legacy reset RPC predates this table.
    -- The write function validates IDs before insertion, and reset cleanup can
    -- run after fixture rows have been replaced without FK ordering changes.
    ticket_id text,
    customer_id text,
    operation_id text not null unique,
    approval_id text not null,
    run_id text not null,
    channel text not null check (channel in ('email', 'phone', 'chat', 'sandbox_outbox')),
    recipient text not null,
    subject text,
    message text not null,
    status text not null default 'queued' check (status = 'queued'),
    created_at timestamptz not null default now(),
    check ((ticket_id is null) <> (customer_id is null))
);

-- Legacy name retained as a compatibility artifact for existing inspection
-- scripts. New writes must use notification_outbox; this table never sends.
create table if not exists email_outbox (
    email_id uuid primary key default gen_random_uuid(),
    ticket_id text not null references tickets(ticket_id),
    operation_id text not null unique,
    recipient text not null,
    subject text not null,
    body text not null,
    status text not null default 'queued' check (status in ('queued', 'sent', 'failed')),
    created_at timestamptz not null default now()
);


create table if not exists idempotency_keys (
    action_type text not null,
    operation_id text not null,
    request_hash text not null,
    result jsonb,
    created_at timestamptz not null default now(),
    primary key (action_type, operation_id)
);


-- Trusted approvals are created by the application/operator,
-- not by the language model.
create table if not exists approval_records (
    approval_id text primary key,
    action_type text not null,
    operation_id text,
    ticket_id text references tickets(ticket_id),
    customer_id text references clients(customer_id),
    run_id text,
    approved_payload jsonb,
    -- Private server-resolved destination for an approved notification.
    approved_recipient text,
    approved_by text not null,
    status text not null default 'approved'
        check (status in ('approved', 'consumed', 'revoked')),
    expires_at timestamptz not null,
    created_at timestamptz not null default now()
);

create unique index if not exists approval_action_operation_unique
    on approval_records(action_type, operation_id) where operation_id is not null;


create index if not exists tickets_customer_id_idx
    on tickets(customer_id);

create index if not exists tickets_order_id_idx
    on tickets(order_id);

create index if not exists orders_customer_id_idx
    on orders(customer_id);

create index if not exists refund_requests_ticket_id_idx
    on refund_requests(ticket_id);

create index if not exists escalation_tasks_ticket_id_idx
    on escalation_tasks(ticket_id);
