import { readFile } from 'node:fs/promises';

const schemaFiles = [
  'schema.sql',
  'seed.sql',
  'migrations/002_approved_commerce_writes.sql',
  'migrations/003_tunisianet_order_sources.sql',
  'migrations/004_replay_and_bootstrap.sql',
  'migrations/005_specialist_receipts.sql',
];

async function initialize(db) {
  const { rows: [row] } = await db.query("select to_regclass('public.clients') as clients");
  if (row.clients) return;

  await db.exec('begin');
  try {
    await db.exec(`create role anon; create role authenticated; create role service_role;
      create schema auth;
      create function auth.role() returns text language sql as
      $$ select current_setting('request.jwt.claim.role', true) $$;`);
    for (const file of schemaFiles) {
      const sql = await readFile(new URL('../' + file, import.meta.url), 'utf8');
      await db.exec(sql);
    }
    await db.exec('commit');
  } catch (error) {
    await db.exec('rollback');
    throw error;
  }
}

export async function openSandbox(directory) {
  const { PGlite } = await import(process.env.PGLITE_MODULE || '@electric-sql/pglite');
  const db = new PGlite(directory);
  try {
    await initialize(db);
    await db.query("select set_config('request.jwt.claim.role', 'service_role', false)");
    return db;
  } catch (error) {
    await db.close();
    throw error;
  }
}
