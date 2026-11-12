import './polyfills' // first: ES imports evaluate in order
export { actionCreators, setupWalletSelector } from '@near-wallet-selector/core'
export { setupModal } from '@near-wallet-selector/modal-ui'
export { setupMyNearWallet } from '@near-wallet-selector/my-near-wallet'
export { setupMeteorWallet } from '@near-wallet-selector/meteor-wallet'
import '@near-wallet-selector/modal-ui/styles.css'
