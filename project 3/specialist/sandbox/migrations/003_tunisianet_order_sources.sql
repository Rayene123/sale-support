-- Replaces the approved-order RPC so it accepts the newly approved demo catalog source.
-- Existing validation and approval behavior are unchanged; only the HTTPS source allowlist includes Tunisianet.

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
               or (v_item->>'source_url') !~ '^https://(www\.)?(mytek\.tn|tunisianet\.com\.tn)/'
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
