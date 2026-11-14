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

test('funding flow requires review before a Base live quote and returns to prediction markets', () => {
  const source = readFileSync(new URL('../src/pages/Funding.tsx', import.meta.url), 'utf8')
  assert.match(source, /dry: true/)
  assert.match(source, /dry: false/)
  assert.match(source, /confirm_live_quote: true/)
  assert.match(source, /confirm_testnet: true/)
  assert.match(source, /source_chain: activeAsset\.blockchain/)
  assert.match(source, /refund_to: refundTo\.trim\(\)/)
  assert.match(source, /Submit transaction hash to Tidepool/)
  assert.match(source, /\/app\/markets\?f=open/)
  assert.doesNotMatch(source, /signAndSend|private key|seed phrase|unlimited allowance/i)
})

test('public funding API separates dry and confirmed live quote boundaries', () => {
  const api = readFileSync(new URL('../src/api/client.ts', import.meta.url), 'utf8')
  assert.match(api, /fundingLiveQuote/)
  assert.match(api, /fundingDeposit/)
  assert.doesNotMatch(api, /signAndSend|privateKey|seedPhrase/i)
})
