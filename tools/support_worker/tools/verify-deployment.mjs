// Read-only deployment gate. Never authenticates or submits a report.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFile, readdir} from 'node:fs/promises';

const root = new URL('../', import.meta.url);
const config = JSON.parse(await readFile(new URL('wrangler.jsonc', root), 'utf8'));
const origin = config.vars.PUBLIC_ORIGIN;
assert.equal(new URL(origin).protocol, 'https:');
const hash = data => createHash('sha256').update(data).digest('hex');
async function get(path) {
  return fetch(new URL(path, origin), {redirect:'error', cache:'no-store', signal:AbortSignal.timeout(15000)});
}
const results = [];
async function assets(relative = '') {
  for (const entry of await readdir(new URL('public/' + relative, root), {withFileTypes:true})) {
    const name = relative + entry.name;
    if (entry.isDirectory()) { await assets(name + '/'); continue; }
    assert(entry.isFile(), `Unexpected linked asset: ${name}`);
    const expected = hash(await readFile(new URL('public/' + name, root)));
    const route = ('/' + name.split('/').map(encodeURIComponent).join('/')).replace(/\/index\.html$/, '/').replace(/\.html$/, '');
    const response = await get(route);
    assert.equal(response.status, 200, name);
    assert.match(response.headers.get('cache-control') || '', /no-store/i);
    const actual = hash(Buffer.from(await response.arrayBuffer()));
    results.push({name, expected, actual, matched:expected === actual});
    assert.equal(actual, expected, `Deployed asset differs from this checkout: ${name}`);
  }
}
await assets();
const configuration = await get('/api/config');
assert.equal(configuration.status, 200);
const value = await configuration.json();
assert.equal(value.enabled, config.vars.DELIVERY_ENABLED === '1');
assert.equal(value.join_url, config.vars.DISCORD_JOIN_URL);
assert.equal(value.schema, 'kfps-support-report/1');
const session = await get('/api/session');
assert.equal(session.status, 200);
assert.deepEqual(await session.json(), {authenticated:false});
const status = await get('/api/reports/a987cb48-c013-41e5-a7a1-8e921bc94950');
assert.equal(status.status, 401, 'Report status must require authentication');
console.log(JSON.stringify({passed:true,origin,assets:results,deliveryEnabled:value.enabled,
  anonymousReadDenied:true,reportsSubmitted:0}, null, 2));
