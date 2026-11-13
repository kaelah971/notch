// Wallet SDKs (near-api-js, Meteor, Nightly, Sender) use Node's Buffer/global. Must load before them.
import { Buffer } from 'buffer'

const g = globalThis as unknown as { Buffer?: typeof Buffer; global?: typeof globalThis }
g.Buffer ??= Buffer
g.global ??= globalThis
