import * as tus from 'tus-js-client'

/**
 * 素材上傳（tus 斷點續傳）。這是唯一不經過 http.ts 的 API：tus-js-client 自己管理分段請求。
 * - 每段 8 MB，網路中斷會自動重試；重新整理頁面後選同一個檔案，會從已上傳的位置繼續
 * - 伺服器回傳的錯誤訊息（例如格式不支援）會原樣顯示
 */
export interface UploadCallbacks {
  onProgress: (sent: number, total: number) => void
  onSuccess: (assetId: string | null) => void
  onError: (message: string) => void
}

const CHUNK_SIZE = 8 * 1024 * 1024

function errorMessage(error: Error | tus.DetailedError): string {
  if (error instanceof tus.DetailedError && error.originalResponse) {
    try {
      const body = JSON.parse(error.originalResponse.getBody()) as { msg?: string }
      if (body.msg) return body.msg
    } catch {
      // 不是 JSON（例如 Caddy 或網路設備回應），使用下面的通用訊息
    }
    const status = error.originalResponse.getStatus()
    if (status === 401) return '登入已失效，請重新登入後再上傳'
    if (status === 413) return '檔案太大'
    return `上傳失敗（HTTP ${status}）`
  }
  return '網路中斷，上傳失敗，請稍後按「重試」'
}

/** purpose：asset 素材（預設）／ music 背景音樂 */
export function createUpload(file: File, callbacks: UploadCallbacks, purpose: 'asset' | 'music' = 'asset'): tus.Upload {
  return new tus.Upload(file, {
    endpoint: '/api/uploads',
    chunkSize: CHUNK_SIZE,
    retryDelays: [0, 1000, 3000, 5000, 10000, 20000, 30000],
    removeFingerprintOnSuccess: true,
    metadata: { filename: file.name, filetype: file.type, purpose },
    onProgress: callbacks.onProgress,
    onSuccess: ({ lastResponse }) => callbacks.onSuccess(lastResponse.getHeader('Starfly-Asset-Id') ?? null),
    onError: (error) => callbacks.onError(errorMessage(error)),
  })
}

/** 有之前沒傳完的紀錄就接著傳，否則從頭開始 */
export async function startOrResume(upload: tus.Upload): Promise<void> {
  try {
    const previous = await upload.findPreviousUploads()
    if (previous.length > 0) upload.resumeFromPreviousUpload(previous[0])
  } catch {
    // 讀不到瀏覽器儲存（例如無痕模式）就從頭上傳
  }
  upload.start()
}
