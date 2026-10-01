import { useSyncExternalStore } from 'react'
import type { Upload } from 'tus-js-client'
import { createUpload, startOrResume } from '../../api/upload'

/**
 * 上傳佇列放在頁面元件之外：切換到其他頁面時上傳繼續進行，回到素材中心仍看得到進度。
 */
export type UploadState = 'uploading' | 'paused' | 'done' | 'error'

export interface UploadItem {
  key: string
  name: string
  size: number
  sent: number
  state: UploadState
  error?: string
}

let items: UploadItem[] = []
const uploads = new Map<string, Upload>()
const listeners = new Set<() => void>()
let onFinished: (() => void) | null = null

function emit(next: UploadItem[]) {
  items = next
  listeners.forEach((listener) => listener())
  syncUnloadWarning()
}

function patch(key: string, change: Partial<UploadItem>) {
  emit(items.map((item) => (item.key === key ? { ...item, ...change } : item)))
}

// 上傳中關閉或重新整理頁面前提醒
const warnUnload = (event: BeforeUnloadEvent) => event.preventDefault()
let warning = false
function syncUnloadWarning() {
  const uploading = items.some((item) => item.state === 'uploading')
  if (uploading && !warning) window.addEventListener('beforeunload', warnUnload)
  if (!uploading && warning) window.removeEventListener('beforeunload', warnUnload)
  warning = uploading
}

export const uploadStore = {
  subscribe(listener: () => void) {
    listeners.add(listener)
    return () => listeners.delete(listener)
  },
  /** 每個檔案上傳完成時呼叫（用來重新整理素材列表） */
  setOnFinished(callback: () => void) {
    onFinished = callback
  },
  add(file: File) {
    const key = `${Date.now()}-${Math.random().toString(36).slice(2)}`
    const upload = createUpload(file, {
      onProgress: (sent) => patch(key, { sent }),
      onSuccess: () => {
        patch(key, { state: 'done', sent: file.size })
        onFinished?.()
      },
      onError: (error) => patch(key, { state: 'error', error }),
    })
    uploads.set(key, upload)
    emit([{ key, name: file.name, size: file.size, sent: 0, state: 'uploading' }, ...items])
    void startOrResume(upload)
  },
  pause(key: string) {
    void uploads.get(key)?.abort()
    patch(key, { state: 'paused' })
  },
  resume(key: string) {
    const upload = uploads.get(key)
    if (!upload) return
    patch(key, { state: 'uploading', error: undefined })
    void startOrResume(upload)
  },
  remove(key: string) {
    const item = items.find((i) => i.key === key)
    const upload = uploads.get(key)
    // 未完成的上傳一併通知伺服器刪除暫存檔
    if (upload && item && item.state !== 'done') void upload.abort(true).catch(() => undefined)
    uploads.delete(key)
    emit(items.filter((i) => i.key !== key))
  },
  clearDone() {
    for (const item of items) if (item.state === 'done') uploads.delete(item.key)
    emit(items.filter((item) => item.state !== 'done'))
  },
}

export function useUploads(): UploadItem[] {
  return useSyncExternalStore(uploadStore.subscribe, () => items)
}
