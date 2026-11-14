import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const marketDetail = await readFile(new URL('../src/pages/MarketDetail.tsx', import.meta.url), 'utf8')
const client = await readFile(new URL('../src/api/client.ts', import.meta.url), 'utf8')

test('market research is an explicit read-only action, not a wallet flow', () => {
  const requestBlock = marketDetail.slice(marketDetail.indexOf('const requestResearch'), marketDetail.indexOf('const researchForMarket'))
  assert.match(requestBlock, /api\.marketResearch\(id\)/)
  assert.doesNotMatch(requestBlock, /signAndSend|entryIntent|wallet|connect/i)
  assert.match(client, /marketResearch:.*method: 'POST'/s)
  assert.match(client, /`\/api\/markets\/\$\{enc\(id\)\}\/research`/)
})

test('verification UI cannot claim a verified inference from an unavailable status', () => {
  assert.match(marketDetail, /verification\?\.status === 'verified'/)
  assert.match(marketDetail, /Inference verification unavailable/)
  assert.match(marketDetail, /No wallet or signing call is made\./)
})

test('research and council expose truthful inference status labels', () => {
  assert.match(marketDetail, /LIVE_AI_VERIFIED/)
  assert.match(marketDetail, /DETERMINISTIC_FALLBACK/)
  assert.match(marketDetail, /UNAVAILABLE/)
  assert.match(marketDetail, /one_shared_model_response/)
  assert.match(marketDetail, /not independent model calls/)
})
