/**
 * 全站共用一個 Audio：按下新的試聽會停掉正在播放的。
 */
let player: HTMLAudioElement | null = null
const listeners = new Set<() => void>()

function ensurePlayer(): HTMLAudioElement {
  if (!player) {
    player = new Audio()
    for (const event of ['play', 'pause', 'ended'] as const) {
      player.addEventListener(event, () => listeners.forEach((l) => l()))
    }
  }
  return player
}

/** 正在播放的網址（絕對網址），沒有播放時為空字串 */
export function playingUrl(): string {
  return player && !player.paused ? player.src : ''
}

export function playAudio(url: string) {
  const audio = ensurePlayer()
  audio.src = url
  void audio.play().catch(() => undefined)
}

export function pauseAudio() {
  player?.pause()
}

export function subscribeAudio(listener: () => void): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}
