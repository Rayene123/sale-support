-- Read a receipt without replaying its potentially mutating action.
create or replace function public.read_specialist_receipt(
    p_action_type text, p_operation_id text, p_run_id text, p_payload jsonb
) returns jsonb
language plpgsql security definer
set search_path = public, pg_temp
as $$
declare
    receipt public.idempotency_keys%rowtype;
begin
    if auth.role() is distinct from 'service_role' then
        raise exception 'service_role_required';
    end if;
    select * into receipt from public.idempotency_keys
        where action_type = p_action_type and operation_id = p_operation_id;
    if not found then
        return null;
    end if;
    if receipt.request_hash is distinct from p_payload::text or receipt.result is null
       or public.resolve_action_approval(p_action_type, p_operation_id, p_run_id, p_payload) is null then
        raise exception 'approval_payload_mismatch';
    end if;
    return receipt.result;
end;
$$;
revoke all on function public.read_specialist_receipt(text,text,text,jsonb) from public, anon, authenticated;
grant execute on function public.read_specialist_receipt(text,text,text,jsonb) to service_role;
