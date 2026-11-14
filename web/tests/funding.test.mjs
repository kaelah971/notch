import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { parseUnits } from '../src/api/format.ts'

test('funding input preserves exact source-token decimals', () => {
  assert.equal(parseUnits('1.25', 6), '1250000')
  assert.equal(parseUnits('0.000000001', 9), '1')
  assert.equal(parseUnits('1.0000001', 6), null)
  assert.equal(parseUnits('0', 6), '0')
})

test('funding surface is dry-quote only and returns to prediction markets', () => {
  const source = readFileSync(new URL('../src/pages/Funding.tsx', import.meta.url), 'utf8')
  assert.match(source, /dry: true/)
  assert.match(source, /source_chain: activeAsset\.blockchain/)
  assert.match(source, /refund_to: refundTo\.trim\(\)/)
  assert.match(source, /\/app\/markets\?f=open/)
  assert.doesNotMatch(source, /dry: false|signAndSend|fundingStatus|deposit-instructions|deposit_address.*sign/i)
})

test('public funding API is not a second wallet or entry signer', () => {
  const api = readFileSync(new URL('../src/api/client.ts', import.meta.url), 'utf8')
  assert.doesNotMatch(api, /signAndSend|fundingQuote[^\n]*dry:\s*false/i)
})
