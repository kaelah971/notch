// Original Notch topic collectibles: hand-built dimensional SVGs in /public/collectibles
// (gradient tile, rim light, inner shade, specular sheen, shadowed illustration).
// Topics mirror Radar categories: AI & Tech, Markets/Crypto, Sports, Music & Culture.

export interface Collectible {
  id: string
  src: string
  alt: string
  /** Glow/trail colour sampled from the render. */
  glow: string
}

export const collectibles: Collectible[] = [
  { id: 'ai', src: '/collectibles/ai.svg', alt: 'AI & Tech collectible', glow: 'rgba(252, 235, 83, .9)' },
  { id: 'music', src: '/collectibles/music.svg', alt: 'Music & Culture collectible', glow: 'rgba(59, 130, 246, .9)' },
  { id: 'coin', src: '/collectibles/coin.svg', alt: 'Markets collectible', glow: 'rgba(255, 122, 61, .9)' },
  { id: 'trophy', src: '/collectibles/trophy.svg', alt: 'Sports collectible', glow: 'rgba(52, 199, 154, .9)' },
]
