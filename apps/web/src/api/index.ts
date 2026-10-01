import { http } from './http'

export type Role = 'admin' | 'shooter'
export type Capability = 'text' | 'vision' | 'tts' | 'embedding'
export type Provider = 'deepseek' | 'byteplus' | 'openrouter' | 'kie' | 'custom'

export interface User {
  id: string
  email: string
  display_name: string
  role: Role
  is_active: boolean
  last_login_at: string | null
  created_at: string
}

export interface ChannelModel {
  id: string
  channel_id: string
  model_key: string
  display_name: string
  capability: Capability
  input_price_per_m: number | null
  output_price_per_m: number | null
  is_default: boolean
  enabled: boolean
}

export interface Channel {
  id: string
  name: string
  provider: Provider
  base_url: string
  has_api_key: boolean
  api_key_last4: string
  enabled: boolean
  created_at: string
  models: ChannelModel[]
}

export interface Preset {
  provider: Provider
  name: string
  base_url: string
  api_key_help: string
  models: string[]
}

export interface MonthSummary {
  calls: number
  cost_usd: number
  failed: number
  unpriced: number
}

export interface UsageItem {
  id: string
  created_at: string
  action: string
  source: string
  channel_name: string
  provider: string
  model_key: string
  status: 'succeeded' | 'failed'
  input_tokens: number
  output_tokens: number
  duration_ms: number
  cost_usd: number | null
  error: string
  user_name: string
}

export interface TestResult {
  reply: string
  input_tokens: number
  output_tokens: number
  duration_ms: number
  cost_usd: number | null
}

export interface Dashboard {
  users: number
  channels: number
  ready_capabilities: Capability[]
  assets: AssetStats
  month: MonthSummary | null
}

// ---------------------------------------------------------------- 素材中心
export type AssetStatus = 'uploaded' | 'processing' | 'ready' | 'failed' | 'duplicate'
export type Quality = 'good' | 'ok' | 'poor' | ''

export interface Asset {
  id: string
  original_filename: string
  kind: 'video' | 'image'
  status: AssetStatus
  /** 分析進行中的步驟，或完成後的提醒 */
  stage: string
  error: string
  size_bytes: number
  duration: number | null
  width: number | null
  height: number | null
  fps: number | null
  has_audio: boolean
  category: string
  note: string
  is_disabled: boolean
  duplicate_of: string | null
  uploaded_by: string | null
  uploaded_by_name: string
  clip_count: number | null
  created_at: string
  analyzed_at: string | null
  poster_url: string | null
  proxy_url: string | null
  original_url: string | null
}

export interface Clip {
  id: string
  asset_id: string
  index: number
  start: number
  end: number
  duration: number
  scene: string
  subjects: string[]
  tags: string[]
  description: string
  quality: Quality
  is_dark: boolean
  is_disabled: boolean
  tagged_by: '' | 'ai' | 'manual'
  thumb_url: string
  duplicate_of: { clip_id: string; asset_id: string; filename: string; index: number } | null
}

export interface AssetDetail extends Asset {
  clips: Clip[]
  duplicate_of_filename?: string
}

export interface AssetStats {
  total: number
  by_status: Record<AssetStatus, number>
  by_category: Record<string, number>
  clips: number
}

export interface AssetQuery {
  limit: number
  offset: number
  status?: AssetStatus
  category?: string
  kind?: 'video' | 'image'
  q?: string
  mine?: boolean
}

export type ClipInput = Partial<{
  scene: string
  subjects: string[]
  tags: string[]
  description: string
  quality: Quality
  is_disabled: boolean
}>

export type ModelInput = {
  model_key: string
  display_name?: string
  capability: Capability
  input_price_per_m?: number | null
  output_price_per_m?: number | null
  is_default?: boolean
}

export const api = {
  // 登入不該等太久：20 秒沒回應就顯示錯誤，而不是一直轉圈
  login: (email: string, password: string) =>
    http.post<User>('/auth/login', { email, password }, { timeout: 20_000 }),
  logout: () => http.post<null>('/auth/logout'),
  me: () => http.get<User>('/auth/me'),
  changePassword: (old_password: string, new_password: string) =>
    http.post<null>('/auth/password', { old_password, new_password }),

  dashboard: () => http.get<Dashboard>('/dashboard'),

  users: () => http.get<User[]>('/users'),
  createUser: (body: { email: string; display_name: string; password: string; role: Role }) =>
    http.post<User>('/users', body),
  updateUser: (
    id: string,
    body: Partial<{ display_name: string; role: Role; is_active: boolean; password: string }>,
  ) => http.patch<User>(`/users/${id}`, body),

  presets: () =>
    http.get<{ presets: Preset[]; capabilities: Record<Capability, string> }>('/channel-presets'),
  channels: () => http.get<Channel[]>('/channels'),
  createChannel: (body: { provider: Provider; name?: string; base_url?: string; api_key: string }) =>
    http.post<Channel>('/channels', body),
  updateChannel: (
    id: string,
    body: Partial<{ name: string; base_url: string; api_key: string; enabled: boolean }>,
  ) => http.patch<Channel>(`/channels/${id}`, body),
  deleteChannel: (id: string) => http.delete<null>(`/channels/${id}`),
  addModel: (channelId: string, body: ModelInput) =>
    http.post<ChannelModel>(`/channels/${channelId}/models`, body),
  updateModel: (id: string, body: Partial<ModelInput & { enabled: boolean }>) =>
    http.patch<ChannelModel>(`/channel-models/${id}`, body),
  deleteModel: (id: string) => http.delete<null>(`/channel-models/${id}`),
  testModel: (id: string, prompt?: string) =>
    http.post<TestResult>(`/channel-models/${id}/test`, prompt ? { prompt } : {}),

  assets: (params: AssetQuery) => http.get<{ items: Asset[]; total: number }>('/assets', params),
  assetStats: () => http.get<AssetStats>('/assets/stats'),
  asset: (id: string) => http.get<AssetDetail>(`/assets/${id}`),
  updateAsset: (id: string, body: Partial<{ category: string; note: string; is_disabled: boolean }>) =>
    http.patch<AssetDetail>(`/assets/${id}`, body),
  deleteAsset: (id: string) => http.delete<null>(`/assets/${id}`),
  reanalyzeAsset: (id: string) => http.post<AssetDetail>(`/assets/${id}/reanalyze`),
  updateClip: (id: string, body: ClipInput) => http.patch<AssetDetail>(`/clips/${id}`, body),

  usage: (params: { limit: number; offset: number; status?: string }) =>
    http.get<{ items: UsageItem[]; total: number }>('/usage', params),
  usageSummary: () =>
    http.get<{
      month: MonthSummary
      by_model: {
        provider: string
        model_key: string
        calls: number
        input_tokens: number
        output_tokens: number
        cost_usd: number
      }[]
    }>('/usage/summary'),
}

export const CAPABILITY_LABELS: Record<Capability, string> = {
  text: '文字',
  vision: '看圖',
  tts: '配音',
  embedding: '向量',
}

/** 場景分類；與後端 app/services/asset_analyzer.py 的 SCENES 同步 */
export const SCENE_LABELS: Record<string, string> = {
  workshop: '工廠車間',
  production: '生產過程',
  product_closeup: '產品特寫',
  packing: '包裝出貨',
  warehouse: '倉庫庫存',
  talking_head: '人物口播',
  storefront: '門店環境',
  team: '團隊人物',
  outdoor: '戶外環境',
  other: '其他',
}

export const ASSET_STATUS: Record<AssetStatus, { label: string; color: string }> = {
  uploaded: { label: '等待分析', color: 'default' },
  processing: { label: '分析中', color: 'processing' },
  ready: { label: '可用', color: 'success' },
  failed: { label: '失敗', color: 'error' },
  duplicate: { label: '重複', color: 'warning' },
}

export const QUALITY_LABELS: Record<Exclude<Quality, ''>, { label: string; color: string }> = {
  good: { label: '清楚', color: 'green' },
  ok: { label: '普通', color: 'blue' },
  poor: { label: '不佳', color: 'red' },
}

/** 素材還在排隊或分析中 */
export function isBusy(status: AssetStatus): boolean {
  return status === 'uploaded' || status === 'processing'
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return ''
  const total = Math.round(seconds)
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`
}

export function formatBytes(bytes: number): string {
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(2)} GB`
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(1)} MB`
  return `${Math.max(1, Math.round(bytes / 1024))} KB`
}

export function formatUsd(value: number | null | undefined): string {
  if (value === null || value === undefined) return '未設定價格'
  if (value === 0) return '$0'
  if (value < 0.01) return `$${value.toFixed(6).replace(/0+$/, '')}`
  return `$${value.toFixed(2)}`
}
