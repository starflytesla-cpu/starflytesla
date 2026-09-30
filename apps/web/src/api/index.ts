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
  month: MonthSummary | null
}

export type ModelInput = {
  model_key: string
  display_name?: string
  capability: Capability
  input_price_per_m?: number | null
  output_price_per_m?: number | null
  is_default?: boolean
}

export const api = {
  login: (email: string, password: string) => http.post<User>('/auth/login', { email, password }),
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

export function formatUsd(value: number | null | undefined): string {
  if (value === null || value === undefined) return '未設定價格'
  if (value === 0) return '$0'
  if (value < 0.01) return `$${value.toFixed(6).replace(/0+$/, '')}`
  return `$${value.toFixed(2)}`
}
