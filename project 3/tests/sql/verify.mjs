// Real PostgreSQL SQL execution in an isolated, in-memory PGlite database.
// This tests transactions and replay, not multi-connection concurrency or Supabase auth.
import assert from 'node:assert/strict';
import { openSandbox } from '../../specialist/sandbox/sql/database.mjs';
const db = await openSandbox();
const query = (sql, params = []) => db.query(sql, params);
const scalar = async (sql, params = []) => Object.values((await query(sql, params)).rows[0])[0];
let checks = 0;
async function check(name, fn) { await fn(); checks++; console.log(`PASS ${name}`); }
try {
  console.log('PASS clean database bootstrap'); checks++;
  const customer = await scalar('select customer_id from clients order by customer_id limit 1');
  const ticket = await scalar('select ticket_id from tickets order by ticket_id limit 1');
  const order = {customer_id: customer, items: [{product_id:'P1', name:'Fixture',
    source_url:'https://www.tunisianet.com.tn/fixture.html', unit_price_tnd:'1.25',
    line_total_tnd:'2.50', quantity:2}], total_tnd:'2.50', source_evidence_ids:['P1']};
  const approve = (action, op, payload) => query(`select record_commerce_approval($1,$2,$3,'run-test','trusted-test', $4::jsonb,now()+interval '15 minutes')`, ['a-'+op, action, op, JSON.stringify(payload)]);
  const resolve = (action, op, payload, run='run-test') => scalar('select resolve_action_approval($1,$2,$3,$4::jsonb)', [action,op,run,JSON.stringify(payload)]);
  const execute = (action, op, payload, run='run-test') => scalar('select execute_approved_commerce_write($1,$2,$3,$4,$5::jsonb)', [action,op,'a-'+op,run,JSON.stringify(payload)]);
  await check('lost order response replays one persisted order, even after expiry', async () => {
    await approve('create_customer_order','order-test-001',order);
    const receipt = await execute('create_customer_order','order-test-001',order);
    await query("update approval_records set expires_at=now()-interval '1 hour' where operation_id='order-test-001'");
    assert.equal(await resolve('create_customer_order','order-test-001',order),'a-order-test-001');
    assert.deepEqual(await execute('create_customer_order','order-test-001',order),receipt);
    assert.equal(await scalar("select count(*)::int from orders where operation_id='order-test-001'"),1);
  });
  await check('receipt lookup is read-only and bound to the exact approved run and body', async () => {
    const read=(op,payload,run='run-test')=>scalar(
      'select read_specialist_receipt($1,$2,$3,$4::jsonb)',
      ['create_customer_order',op,run,JSON.stringify(payload)]);
    assert.equal(await read('no-order-yet',order),null);
    const receipt=await read('order-test-001',order);
    assert.equal(receipt.operation_id,'order-test-001');
    await assert.rejects(read('order-test-001',order,'another-run'),/approval_payload_mismatch/);
    await assert.rejects(read('order-test-001',{...order,total_tnd:'3.00'}),/approval_payload_mismatch/);
    assert.equal(await scalar("select count(*)::int from orders where operation_id='order-test-001'"),1);
  });
  await check('changed payload, wrong run and revoked approval cannot replay', async () => {
    assert.equal(await resolve('create_customer_order','order-test-001',{...order,total_tnd:'9.00'}),null);
    assert.equal(await resolve('create_customer_order','order-test-001',order,'another-run'),null);
    await assert.rejects(execute('create_customer_order','order-test-001',order,'another-run'), /approval_payload_mismatch/);
    await query("update approval_records set status='revoked' where operation_id='order-test-001'");
    await assert.rejects(execute('create_customer_order','order-test-001',order), /approval_payload_mismatch/);
  });
  await check('expired approval cannot create a new effect', async () => {
    await approve('create_customer_order','order-expired',order);
    await query("update approval_records set expires_at=now()-interval '1 hour' where operation_id='order-expired'");
    assert.equal(await resolve('create_customer_order','order-expired',order),null);
    await assert.rejects(execute('create_customer_order','order-expired',order), /approval/);
    assert.equal(await scalar("select count(*)::int from orders where operation_id='order-expired'"),0);
  });
  await check('invalid totals roll back without consuming approval', async () => {
    const invalid = {...order,total_tnd:'99.00'};
    await approve('create_customer_order','order-invalid',invalid);
    await assert.rejects(execute('create_customer_order','order-invalid',invalid));
    assert.equal(await scalar("select status from approval_records where operation_id='order-invalid'"),'approved');
    assert.equal(await scalar("select count(*)::int from orders where operation_id='order-invalid'"),0);
  });
  await check('notification replay creates one outbox row', async () => {
    const payload={customer_id:customer,ticket_id:null,channel:'sandbox_outbox',subject:null,message:'Approved message'};
    await approve('send_support_notification','notification-test',payload);
    const receipt=await execute('send_support_notification','notification-test',payload);
    assert.equal(await resolve('send_support_notification','notification-test',payload),'a-notification-test');
    assert.deepEqual(await execute('send_support_notification','notification-test',payload),receipt);
    assert.equal(await scalar("select count(*)::int from notification_outbox where operation_id='notification-test'"),1);
  });
  await check('ticket update replay appends exactly one history entry', async () => {
    const payload={ticket_id:ticket,status:'resolved',labels:['general'],response_text:'Approved response'};
    const before=await scalar('select jsonb_array_length(response_history) from tickets where ticket_id=$1',[ticket]);
    await approve('update_ticket_database','ticket-test-001',payload);
    const args=['ticket-test-001',JSON.stringify({...payload,approval_id:'a-ticket-test-001'})];
    const sql="select execute_support_write('update_ticket_database',$1,$2::jsonb)";
    const receipt=await scalar(sql,args);
    assert.equal(await resolve('update_ticket_database','ticket-test-001',payload),'a-ticket-test-001');
    assert.deepEqual(await scalar(sql,args),receipt);
    assert.equal(await scalar('select jsonb_array_length(response_history) from tickets where ticket_id=$1',[ticket]),before+1);
  });
  await check('null response cannot enter ticket history', async () => {
    const payload={ticket_id:ticket,status:'resolved',labels:['general'],response_text:null};
    await approve('update_ticket_database','ticket-null-test',payload);
    await assert.rejects(query("select execute_support_write('update_ticket_database',$1,$2::jsonb)",
      ['ticket-null-test',JSON.stringify({...payload,approval_id:'a-ticket-null-test'})]),/invalid_write_payload/);
  });
  await check('retained refund and escalation SQL creates pending records and replays', async () => {
    const orderId=await scalar('select order_id from tickets where ticket_id=$1',[ticket]);
    for (const [action,table,payload] of [
      ['create_refund_request','refund_requests',{ticket_id:ticket,order_id:orderId,amount:'1.00',reason:'Fixture refund'}],
      ['create_escalation_task','escalation_tasks',{ticket_id:ticket,team:'general',priority:'medium',reason:'Fixture escalation',due_at:'2030-01-01T00:00:00Z'}]
    ]) {
      // Legacy actions are outside the graph/approval helper. Seed a trusted approval directly.
      const op='legacy-'+table;
      await query(`insert into approval_records(approval_id,action_type,operation_id,run_id,approved_by,approved_payload,expires_at)
        values($1,$2,$3,'run-test','trusted-test',$4::jsonb,now()+interval '15 minutes')`,['a-'+op,action,op,JSON.stringify(payload)]);
      const args=[action,op,JSON.stringify({...payload,approval_id:'a-'+op})];
      const sql='select execute_support_write($1,$2,$3::jsonb)';
      const receipt=await scalar(sql,args);
      assert.equal(receipt.data.status,'pending');
      assert.deepEqual(await scalar(sql,args),receipt);
      assert.equal(await scalar(`select count(*)::int from ${table} where operation_id=$1`,[op]),1);
    }
  });
  await check('non-service caller rejected', async () => {
    await query("select set_config('request.jwt.claim.role','anon',false)");
    await assert.rejects(query('select reset_sale_support_sandbox()'),/service_role_required/);
    await query("select set_config('request.jwt.claim.role','service_role',false)");
  });
  await check('atomic reset is repeatable and clears effects', async () => {
    for (let i=0;i<2;i++) {
      const result=await scalar('select reset_sale_support_sandbox()');
      assert.equal(result.success,true);
      for (const [table,count] of [['clients',10],['orders',10],['tickets',12],['approval_records',0],['idempotency_keys',0],['notification_outbox',0]])
        assert.equal(await scalar(`select count(*)::int from ${table}`),count);
    }
  });
  console.log(`${checks} SQL integration checks passed`);
} catch (error) { console.error('FAIL', error.message, error.where || ''); process.exitCode=1; } finally { await db.close(); }
