-- Additive extension for approved sandbox commerce writes.
-- Apply only to the dedicated sale-support-sandbox database. This does not
-- replace execute_support_write or alter its existing four actions.

alter table public.approval_records alter column ticket_id drop not null;
alter table public.approval_records add column if not exists operation_id text;
alter table public.approval_records add column if not exists customer_id text references public.clients(customer_id);
alter table public.approval_records add column if not exists run_id text;
alter table public.approval_records add column if not exists approved_payload jsonb;
alter table public.approval_records add column if not exists approved_recipient text;
create unique index if not exists approval_action_operation_unique
    on public.approval_records(action_type, operation_id) where operation_id is not null;

alter table public.orders add column if not exists operation_id text;
alter table public.orders add column if not exists source_snapshot jsonb;
alter table public.orders add column if not exists approval_id text;
create unique index if not exists orders_operation_id_unique
    on public.orders(operation_id) where operation_id is not null;

create table if not exists public.notification_outbox (
    notification_id uuid primary key default gen_random_uuid(),
    -- Soft IDs avoid adding FK ordering requirements to the existing reset RPC.
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

revoke all on public.notification_outbox from anon, authenticated;
grant all on public.notification_outbox to service_role;

-- Approval creation is deliberately not exposed as an agent tool. The
-- authenticated operator application calls this after authenticating the
-- human approver and canonicalizing the exact action payload.
create or replace function public.record_commerce_approval(
    p_approval_id text,
    p_action_type text,
    p_operation_id text,
    p_run_id text,
    p_approved_by text,
    p_payload jsonb,
    p_expires_at timestamptz
) returns jsonb
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
    v_ticket_id text;
    v_approved_recipient text;
    v_customer_id text;
begin
    if auth.role() is distinct from 'service_role' then
        raise exception 'service_role_required';
    end if;
    if p_approval_id is null or length(p_approval_id) not between 1 and 128
       or p_action_type is null or p_action_type not in ('create_customer_order','send_support_notification','update_ticket_database')
       or p_operation_id is null or p_operation_id !~ '^[A-Za-z0-9_-]{8,100}(:notification|:ticket)?$'
       or p_run_id is null or length(p_run_id) not between 1 and 128
       or p_approved_by is null or length(p_approved_by) not between 1 and 128
       or p_payload is null or jsonb_typeof(p_payload) <> 'object'
       or p_expires_at is null
       or p_expires_at <= clock_timestamp()
       or p_expires_at > clock_timestamp() + interval '1 hour' then
        raise exception 'invalid_approval_record';
    end if;
    v_ticket_id := p_payload->>'ticket_id';
    v_customer_id := p_payload->>'customer_id';
    if p_action_type = 'create_customer_order' then
        if v_customer_id is null or not exists (
            select 1 from public.clients where customer_id = v_customer_id
        ) or v_ticket_id is not null then
            raise exception 'invalid_approval_record';
        end if;
    elsif p_action_type = 'update_ticket_database' then
        if v_ticket_id is null or not exists (
            select 1 from public.tickets where ticket_id = v_ticket_id
        ) or v_customer_id is not null then
            raise exception 'invalid_approval_record';
        end if;
    else
        if ((v_ticket_id is null) = (v_customer_id is null)) then
            raise exception 'invalid_approval_record';
        end if;
        if p_action_type = 'send_support_notification' then
            if v_ticket_id is not null then
                select c.customer_id, c.email
                  into v_customer_id, v_approved_recipient
                  from public.tickets t
                  join public.clients c on c.customer_id = t.customer_id
                 where t.ticket_id = v_ticket_id;
            else
                select c.email into v_approved_recipient
                  from public.clients c where c.customer_id = v_customer_id;
            end if;
            if not found or v_approved_recipient is null or btrim(v_approved_recipient) = '' then
                raise exception 'customer_not_found';
            end if;
        else
            if v_ticket_id is null or not exists (
                select 1 from public.tickets where ticket_id = v_ticket_id
            ) then
                raise exception 'ticket_not_found';
            end if;
        end if;
    end if;
    insert into public.approval_records(
        approval_id, action_type, operation_id, ticket_id, customer_id, run_id,
        approved_payload, approved_recipient, approved_by, status, expires_at
    ) values (
        p_approval_id, p_action_type, p_operation_id, v_ticket_id, v_customer_id, p_run_id,
        p_payload, v_approved_recipient, p_approved_by, 'approved', p_expires_at
    );
    return jsonb_build_object('success', true, 'approval_id', p_approval_id);
end;
$$;

revoke all on public.approval_records from anon, authenticated;
grant all on public.approval_records to service_role;
revoke all on function public.record_commerce_approval(text,text,text,text,text,jsonb,timestamptz) from public, anon, authenticated;
grant execute on function public.record_commerce_approval(text,text,text,text,text,jsonb,timestamptz) to service_role;

create or replace function public.execute_approved_commerce_write(
    p_action_type text,
    p_operation_id text,
    p_approval_id text,
    p_run_id text,
    p_payload jsonb
) returns jsonb
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
    v_approval public.approval_records%rowtype;
    v_existing public.idempotency_keys%rowtype;
    v_request_hash text;
    v_result jsonb;
    v_customer_id text;
    v_order_id text;
    v_item jsonb;
    v_items_snapshot jsonb := '[]'::jsonb;
    v_item_count integer;
    v_evidence_count integer;
    v_quantity integer;
    v_unit_price numeric(12,2);
    v_line_total numeric(14,2);
    v_total numeric(14,2) := 0;
    v_item_summary text;
    v_ticket_id text;
    v_channel text;
    v_recipient text;
    v_subject text;
    v_message text;
    v_notification_id uuid;
begin
    if auth.role() is distinct from 'service_role' then
        raise exception 'service_role_required';
    end if;
    if p_action_type is null or p_action_type not in ('create_customer_order', 'send_support_notification') then
        raise exception 'invalid_action_type';
    end if;
    if p_operation_id is null or length(p_operation_id) not between 8 and 100
       or p_operation_id !~ '^[A-Za-z0-9_-]{8,100}(:notification|:ticket)?$' then
        raise exception 'invalid_operation_id';
    end if;
    if p_approval_id is null or p_run_id is null or p_payload is null
       or jsonb_typeof(p_payload) <> 'object' then
        raise exception 'invalid_write_payload';
    end if;

    perform pg_advisory_xact_lock(hashtextextended(p_action_type || ':' || p_operation_id, 0));
    v_request_hash := p_payload::text;
    select * into v_existing
      from public.idempotency_keys
     where action_type = p_action_type and operation_id = p_operation_id;
    if found then
        if v_existing.request_hash <> v_request_hash then
            raise exception 'operation_conflict';
        end if;
        if v_existing.result is null then
            raise exception 'sandbox_database_failed';
        end if;
        return v_existing.result;
    end if;

    select * into v_approval
      from public.approval_records
     where approval_id = p_approval_id
       and action_type = p_action_type
       and operation_id = p_operation_id
       and run_id = p_run_id
       and approved_payload = p_payload
       and status = 'approved'
       and expires_at > clock_timestamp()
     for update;
    if not found then
        raise exception 'approval_payload_mismatch';
    end if;

    if p_action_type = 'create_customer_order' then
        if not (p_payload ?& array['customer_id','items','total_tnd','source_evidence_ids'])
           or (p_payload - array['customer_id','items','total_tnd','source_evidence_ids']) <> '{}'::jsonb
           or jsonb_typeof(p_payload->'items') <> 'array'
           or jsonb_typeof(p_payload->'source_evidence_ids') <> 'array'
           or jsonb_typeof(p_payload->'total_tnd') not in ('number','string')
           or jsonb_array_length(p_payload->'items') not between 1 and 20 then
            raise exception 'invalid_order_payload';
        end if;
        v_customer_id := p_payload->>'customer_id';
        if v_customer_id is null or not exists (
            select 1 from public.clients where customer_id = v_customer_id
        ) then
            raise exception 'customer_not_found';
        end if;

        select count(*), count(distinct item->>'product_id')
          into v_item_count, v_evidence_count
          from jsonb_array_elements(p_payload->'items') as entries(item);
        if v_item_count <> v_evidence_count then
            raise exception 'duplicate_product_id';
        end if;
        if jsonb_array_length(p_payload->'source_evidence_ids') <> v_item_count then
            raise exception 'order_evidence_mismatch';
        end if;

        for v_item in select item from jsonb_array_elements(p_payload->'items') as entries(item) loop
            if jsonb_typeof(v_item) <> 'object'
               or not (v_item ?& array['product_id','name','quantity','unit_price_tnd','source_url'])
               or jsonb_typeof(v_item->'product_id') <> 'string'
               or jsonb_typeof(v_item->'name') <> 'string'
               or jsonb_typeof(v_item->'quantity') <> 'number'
               or jsonb_typeof(v_item->'unit_price_tnd') not in ('number','string')
               or jsonb_typeof(v_item->'source_url') <> 'string'
               or (v_item - array['product_id','name','quantity','unit_price_tnd','source_url','line_total_tnd']) <> '{}'::jsonb
               or length(v_item->>'product_id') not between 1 and 128
               or length(v_item->>'name') not between 1 and 300
               or (v_item->>'source_url') !~ '^https://(www\.)?mytek\.tn/'
               or (v_item->>'unit_price_tnd') !~ '^\d{1,10}(\.\d{1,2})?$' then
                raise exception 'invalid_order_item';
            end if;
            if (v_item->>'quantity')::numeric <> trunc((v_item->>'quantity')::numeric) then
                raise exception 'invalid_order_item';
            end if;
            v_quantity := (v_item->>'quantity')::integer;
            v_unit_price := (v_item->>'unit_price_tnd')::numeric;
            if v_quantity not between 1 and 10 or v_unit_price < 0 then
                raise exception 'invalid_order_item';
            end if;
            v_line_total := round(v_unit_price * v_quantity, 2);
            if v_item ? 'line_total_tnd' then
                if jsonb_typeof(v_item->'line_total_tnd') not in ('number','string')
                   or (v_item->>'line_total_tnd') !~ '^\d{1,12}(\.\d{1,2})?$'
                   or (v_item->>'line_total_tnd')::numeric <> v_line_total then
                    raise exception 'order_total_mismatch';
                end if;
            end if;
            v_total := v_total + v_line_total;
            v_items_snapshot := v_items_snapshot || jsonb_build_array(jsonb_build_object(
                'product_id', v_item->>'product_id',
                'name', v_item->>'name',
                'source_url', v_item->>'source_url',
                'quantity', v_quantity,
                'unit_price_tnd', v_unit_price,
                'line_total_tnd', v_line_total
            ));
        end loop;
        v_total := round(v_total, 2);
        if (p_payload->>'total_tnd') is null
           or (p_payload->>'total_tnd') !~ '^\d{1,12}(\.\d{1,2})?$'
           or v_total > 9999999999.99
           or (p_payload->>'total_tnd')::numeric <> v_total then
            raise exception 'order_total_mismatch';
        end if;
        if exists (
            select 1 from jsonb_array_elements_text(p_payload->'source_evidence_ids') as evidence(id)
             where evidence.id not in (
                 select item->>'product_id' from jsonb_array_elements(p_payload->'items') as items(item)
             )
        ) then
            raise exception 'order_evidence_mismatch';
        end if;
        if (select count(distinct id) from jsonb_array_elements_text(p_payload->'source_evidence_ids') as evidence(id)) <> v_item_count then
            raise exception 'order_evidence_mismatch';
        end if;

        select string_agg((entry->>'name') || ' x' || (entry->>'quantity'), ', ' order by ord)
          into v_item_summary
          from jsonb_array_elements(v_items_snapshot) with ordinality as rows(entry, ord);
        v_order_id := 'S-' || replace(gen_random_uuid()::text, '-', '');
        insert into public.orders (
            order_id, customer_id, order_status, item_summary, total_amount,
            currency, shipment_status, ordered_at, operation_id, source_snapshot,
            approval_id
        ) values (
            v_order_id, v_customer_id, 'pending', v_item_summary, v_total,
            'TND', 'not_shipped', now(), p_operation_id,
            jsonb_build_object('items', v_items_snapshot,
                               'source_evidence_ids', p_payload->'source_evidence_ids',
                               'run_id', p_run_id),
            p_approval_id
        );
        v_result := jsonb_build_object(
            'success', true,
            'operation_id', p_operation_id,
            'data', jsonb_build_object('order_id', v_order_id,
                'customer_id', v_customer_id, 'items', v_items_snapshot,
                'total_tnd', to_char(v_total, 'FM999999999990.00'),
                'currency', 'TND', 'sandbox_only', true)
        );
    else
        if not (p_payload ?& array['channel','message'])
           or (p_payload - array['ticket_id','customer_id','channel','subject','message']) <> '{}'::jsonb
           or ((p_payload->>'ticket_id' is null) = (p_payload->>'customer_id' is null)) then
            raise exception 'invalid_notification_payload';
        end if;
        v_ticket_id := p_payload->>'ticket_id';
        v_customer_id := p_payload->>'customer_id';
        if v_ticket_id is not null then
            select c.customer_id, c.email into v_customer_id, v_recipient
              from public.tickets t join public.clients c on c.customer_id = t.customer_id
             where t.ticket_id = v_ticket_id
             for update of c;
        else
            select c.email into v_recipient from public.clients c
             where c.customer_id = v_customer_id
             for update;
        end if;
        if not found then
            raise exception 'customer_not_found';
        end if;
        if v_approval.approved_recipient is null
           or v_recipient is distinct from v_approval.approved_recipient then
            raise exception 'approval_payload_mismatch';
        end if;
        v_channel := p_payload->>'channel';
        v_subject := p_payload->>'subject';
        v_message := p_payload->>'message';
        if v_channel is null or v_channel not in ('email','phone','chat','sandbox_outbox')
           or length(coalesce(v_recipient,'')) not between 1 and 254
           or length(coalesce(v_message,'')) not between 1 and 5000
           or (v_subject is not null and length(v_subject) > 200) then
            raise exception 'invalid_notification_payload';
        end if;
        insert into public.notification_outbox (
            ticket_id, customer_id, operation_id, approval_id, run_id,
            channel, recipient, subject, message, status
        ) values (
            v_ticket_id, v_customer_id, p_operation_id, p_approval_id, p_run_id,
            v_channel, v_recipient, v_subject, v_message, 'queued'
        ) returning notification_id into v_notification_id;
        v_result := jsonb_build_object(
            'success', true,
            'operation_id', p_operation_id,
            'data', jsonb_build_object('notification_id', v_notification_id,
                'status', 'queued', 'sandbox_only', true)
        );
    end if;

    update public.approval_records
       set status = 'consumed'
     where approval_id = p_approval_id;
    insert into public.idempotency_keys(action_type, operation_id, request_hash, result)
    values (p_action_type, p_operation_id, v_request_hash, v_result);
    return v_result;
end;
$$;

revoke all on function public.execute_approved_commerce_write(text,text,text,text,jsonb) from public, anon, authenticated;
grant execute on function public.execute_approved_commerce_write(text,text,text,text,jsonb) to service_role;

-- Called after the existing fixture reset RPC. It removes only records created
-- by the new Person 2 commerce actions and leaves the ten seeded orders intact.
create or replace function public.reset_approved_commerce_state()
returns jsonb
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
    v_notifications integer;
    v_orders integer;
    v_operations integer;
    v_approvals integer;
begin
    if auth.role() is distinct from 'service_role' then
        raise exception 'service_role_required';
    end if;
    delete from public.notification_outbox;
    get diagnostics v_notifications = row_count;
    delete from public.orders where operation_id is not null;
    get diagnostics v_orders = row_count;
    delete from public.idempotency_keys
     where action_type in ('create_customer_order','send_support_notification');
    get diagnostics v_operations = row_count;
    delete from public.approval_records
     where action_type in ('create_customer_order','send_support_notification');
    get diagnostics v_approvals = row_count;
    return jsonb_build_object(
        'success', true,
        'notifications_cleared', v_notifications,
        'sandbox_orders_cleared', v_orders,
        'operation_history_cleared', v_operations,
        'approvals_cleared', v_approvals
    );
end;
$$;

revoke all on function public.reset_approved_commerce_state() from public, anon, authenticated;
grant execute on function public.reset_approved_commerce_state() to service_role;
