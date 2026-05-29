import fs from 'node:fs/promises';
import path from 'node:path';

const projectRef = process.env.SUPABASE_PROJECT_REF || 'hyovtguangyykehxwnvp';
const accessToken = process.env.SUPABASE_ACCESS_TOKEN;
const schemaPath = process.argv[2] || path.join('supabase', 'apply_schema.sql');

if (!accessToken) {
  console.error('SUPABASE_ACCESS_TOKEN is required to create tables through the Supabase Management API.');
  process.exit(1);
}

const query = await fs.readFile(schemaPath, 'utf8');
const response = await fetch(`https://api.supabase.com/v1/projects/${projectRef}/database/query`, {
  method: 'POST',
  headers: {
    authorization: `Bearer ${accessToken}`,
    'content-type': 'application/json',
  },
  body: JSON.stringify({ query }),
});

const body = await response.text();

if (!response.ok) {
  console.error(`Supabase schema apply failed: ${response.status} ${response.statusText}`);
  console.error(body);
  process.exit(1);
}

console.log('Supabase schema applied.');
console.log(body);
