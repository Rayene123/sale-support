import { readFile } from 'node:fs/promises';
import { createInterface } from 'node:readline';

const { PGlite } = await import(process.env.PGLITE_MODULE || '@electric-sql/pglite');
const db = new PGlite(process.argv[2]);
const migrations = ['schema.sql', 'seed.sql', 'migrations/002_approved_commerce_writes.sql',
  'migrations/003_tunisianet_order_sources.sql', 'migrations/004_replay_and_bootstrap.sql',
  'migrations/005_specialist_receipts.sql'];

if (!(await db.query("select to_regclass('public.clients') as clients")).rows[0].clients) {
  await db.exec('begin');
  try {
    await db.exec(`create role anon; create role authenticated; create role service_role;
      create schema auth;
      create function auth.role() returns text language sql as
      $$ select current_setting('request.jwt.claim.role', true) $$;`);
    for (const file of migrations) {
      await db.exec(await readFile(new URL(`../../sandbox/${file}`, import.meta.url), 'utf8'));
    }
    await db.exec('commit');
  } catch (error) {
    await db.exec('rollback');
    throw error;
  }
}
await db.query("select set_config('request.jwt.claim.role', 'service_role', false)");

const approvalArgs = ['p_action_type', 'p_operation_id', 'p_run_id', 'p_payload'];
const methods = new Map([
  ['read_specialist_receipt', approvalArgs],
  ['resolve_action_approval', approvalArgs],
  ['record_commerce_approval', ['p_action_type', 'p_operation_id', 'p_run_id',
    'p_approval_id', 'p_approved_by', 'p_payload', 'p_expires_at']],
  ['execute_approved_commerce_write', ['p_action_type', 'p_operation_id',
    'p_approval_id', 'p_run_id', 'p_payload']],
  ['reset_sale_support_sandbox', []],
]);

console.log(JSON.stringify({ ready: true }));
try {
  for await (const line of createInterface({ input: process.stdin })) {
    try {
      const { method, params } = JSON.parse(line);
      const keys = methods.get(method);
      if (!keys || keys.length !== Object.keys(params).length || keys.some(key => !Object.hasOwn(params, key))) {
        throw new Error('Unsupported sandbox RPC arguments');
      }
      const args = keys.map((key, i) => `${key} => $${i + 1}`).join(', ');
      const values = keys.map(key => key === 'p_payload' ? JSON.stringify(params[key]) : params[key]);
      const { rows } = await db.query(`select public.${method}(${args}) as result`, values);
      console.log(JSON.stringify({ data: rows[0].result }));
    } catch {
      console.log(JSON.stringify({ error: 'Local sandbox RPC failed' }));
    }
  }
} finally {
  await db.close();
}
