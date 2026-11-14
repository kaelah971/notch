import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const vault = await readFile(new URL('../src/pages/PrivateVault.tsx', import.meta.url), 'utf8')
const client = await readFile(new URL('../src/api/client.ts', import.meta.url), 'utf8')
const marketDetail = await readFile(new URL('../src/pages/MarketDetail.tsx', import.meta.url), 'utf8')

test('private vault uses the existing wallet session and explicit owner-only actions', () => {
  assert.match(vault, /verifyCreatorOwnership/)
  assert.match(vault, /PRIVATE · owner-only/)
  assert.match(vault, /api\.vaultCreate/)
  assert.match(vault, /api\.vaultUpdate/)
  assert.match(vault, /api\.vaultDelete/)
  assert.match(vault, /window\.confirm\('Delete this private research permanently\?'/)
  assert.doesNotMatch(vault, /owner_account:/)
})

test('research experience offers an explicit private save handoff', () => {
  assert.match(marketDetail, /Save privately/)
  assert.match(marketDetail, /\/app\/vault/)
  assert.match(client, /\/api\/research\/vault/)
})
