import './polyfills' // first: ES imports evaluate in order
export { actionCreators, setupWalletSelector } from '@near-wallet-selector/core'
export { setupModal } from '@near-wallet-selector/modal-ui'
export { setupMeteorWallet } from '@near-wallet-selector/meteor-wallet'
export { setupNightly } from '@near-wallet-selector/nightly'
export { setupSender } from '@near-wallet-selector/sender'
import '@near-wallet-selector/modal-ui/styles.css'
