import axios, { AxiosError, type AxiosRequestConfig } from 'axios'

/** 後端統一回應格式：成功 code 為 0；失敗時 reason 是機器可讀原因，msg 可直接顯示。 */
interface Envelope<T> {
  code: number
  data: T
  msg: string
  reason?: string
}

export class ApiError extends Error {
  readonly status: number
  readonly reason: string

  constructor(message: string, status: number, reason: string) {
    super(message)
    this.status = status
    this.reason = reason
  }
}

const client = axios.create({ baseURL: '/api', withCredentials: true, timeout: 90_000 })

function toApiError(error: unknown): ApiError {
  if (error instanceof AxiosError) {
    const body = error.response?.data as Partial<Envelope<unknown>> | undefined
    if (body && typeof body.msg === 'string') {
      return new ApiError(body.msg, error.response?.status ?? 0, body.reason ?? 'unknown')
    }
    if (error.code === 'ECONNABORTED' || error.code === 'ETIMEDOUT') {
      return new ApiError('伺服器沒有回應，請檢查網路或稍後再試', 0, 'timeout')
    }
    return new ApiError('無法連線到伺服器，請檢查網路', error.response?.status ?? 0, 'network')
  }
  return new ApiError('發生未預期的錯誤', 0, 'unknown')
}

async function unwrap<T>(promise: Promise<{ data: Envelope<T> }>): Promise<T> {
  try {
    const { data } = await promise
    if (data.code !== 0) throw new ApiError(data.msg, 200, data.reason ?? 'unknown')
    return data.data
  } catch (error) {
    if (error instanceof ApiError) throw error
    throw toApiError(error)
  }
}

export const http = {
  get: <T>(url: string, params?: object) => unwrap<T>(client.get(url, { params })),
  post: <T>(url: string, body?: unknown, config?: AxiosRequestConfig) =>
    unwrap<T>(client.post(url, body ?? {}, config)),
  patch: <T>(url: string, body?: unknown) => unwrap<T>(client.patch(url, body ?? {})),
  delete: <T>(url: string) => unwrap<T>(client.delete(url)),
}
