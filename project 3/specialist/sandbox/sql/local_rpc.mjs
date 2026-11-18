import { createInterface } from 'node:readline';

import { openSandbox } from './database.mjs';

const db = await openSandbox(process.argv[2]);

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
