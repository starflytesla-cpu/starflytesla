import { http } from './http'

export type Role = 'admin' | 'shooter'
export type Capability = 'text' | 'vision' | 'tts' | 'music' | 'embedding'
export type Provider = 'deepseek' | 'byteplus' | 'volcengine' | 'openrouter' | 'kie' | 'custom'

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

export interface PublishChannel {
  id: string
  name: string
  provider: 'uploadpost'
  base_url: string
  has_api_key: boolean
  api_key_last4: string
  enabled: boolean
  check_status: 'untested' | 'succeeded' | 'failed'
  check_error: string
  plan: string
  checked_at: string | null
  created_at: string
}

export interface PublishChannelInput {
  name: string
  base_url: string
  api_key?: string
  enabled?: boolean
  clear_api_key?: boolean
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
  /** 配音模型的測試音檔 */
  audio_url?: string
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

// ---------------------------------------------------------------- 帳號檔案、模板、文案、音色
export type Strategy = 'persona' | 'traffic' | 'conversion'
export type ScriptStatus = 'generating' | 'draft' | 'approved' | 'failed'

export interface Profile {
  id: string
  name: string
  industry: string
  audience: string
  selling_points: string[]
  product_details: string
  tone: string
  target_language: string
  call_to_action: string
  hashtags: string[]
  banned_words: string[]
  voice_id: string
  voice_name: string
  voice_speed: number
  script_count: number | null
  created_at: string
  updated_at: string
}

export type ProfileInput = Partial<
  Omit<Profile, 'id' | 'voice_name' | 'script_count' | 'created_at' | 'updated_at'>
>

export interface TemplateShot {
  brief: string
  scene: string
  seconds: number
}

export interface Template {
  id: string
  builtin: boolean
  name: string
  strategy: Strategy
  description: string
  shots: TemplateShot[]
  total_seconds: number
  is_active: boolean
  script_count: number | null
  updated_at: string
}

export type TemplateInput = Partial<Pick<Template, 'name' | 'strategy' | 'description' | 'shots' | 'is_active'>>

export interface ScriptShot extends TemplateShot {
  voiceover: string
  caption: string
}

export interface Script {
  id: string
  batch_id: string
  variant: number
  template_id: string | null
  template_name: string
  profile_id: string | null
  profile_name: string
  language: string
  status: ScriptStatus
  title: string
  hook: string
  shots: ScriptShot[]
  post_caption: string
  hashtags: string[]
  error: string
  total_seconds: number
  created_at: string
  updated_at: string
}

export interface ScriptQuery {
  limit: number
  offset: number
  template_id?: string
  profile_id?: string
  status?: ScriptStatus
}

export type ScriptInput = Partial<{
  title: string
  hook: string
  shots: { voiceover: string; caption: string }[]
  post_caption: string
  hashtags: string[]
  status: 'draft' | 'approved'
}>

export type VoiceEngine = 'gemini' | 'elevenlabs'

export interface Voice {
  id: string
  name: string
  description: string
  recommended: boolean
  engine: VoiceEngine
  /** ElevenLabs 有官方免費試聽檔；Gemini 沒有，要呼叫 voiceSample 產生 */
  preview_url: string | null
}

export interface AudioResult {
  audio_url: string
  cost_usd: number | null
}

// ---------------------------------------------------------------- 成片、任務
export type VideoStatus = 'queued' | 'rendering' | 'pending_review' | 'approved' | 'rejected' | 'failed'

export interface Video {
  id: string
  batch_id: string
  script_id: string | null
  profile_id: string | null
  title: string
  template_name: string
  profile_name: string
  language: string
  status: VideoStatus
  stage: string
  error: string
  style: string
  duration: number | null
  render_seconds: number | null
  review_note: string
  reviewed_at: string | null
  created_at: string
  rendered_at: string | null
  video_url: string | null
  poster_url: string | null
}

export interface VideoSegment {
  clip_id: string
  duration: number
  thumb_url: string | null
  scene: string
  description: string
  filename: string
}

export interface VideoShot {
  index: number
  brief: string
  scene: string
  caption: string
  voiceover: string
  start: number
  duration: number
  segments: VideoSegment[]
}

export interface VideoDetail extends Video {
  shots: VideoShot[]
  bgm_title: string | null
  voice_id: string | null
  ambience: number | null
}

export interface ClipCandidate {
  clip_id: string
  kind: 'video' | 'image'
  length: number | null
  quality: Quality
  scene_match: boolean
  thumb_url: string
  scene: string
  description: string
  filename: string
}

export interface MusicTrack {
  id: string
  title: string
  source: 'upload' | 'ai'
  style: string
  status: 'generating' | 'ready' | 'failed'
  error: string
  duration: number | null
  size_bytes: number
  is_active: boolean
  audio_url: string | null
  created_at: string
}

export interface Coverage {
  total_clips: number
  tts_ready: boolean
  scripts: { id: string; shots: { scene: string; clips: number }[] }[]
}

export type TaskStatus = 'queued' | 'running' | 'succeeded' | 'failed'

export interface TaskItem {
  id: string
  type: string
  type_label: string
  target: string
  label: string
  status: TaskStatus
  attempts: number
  max_attempts: number
  error: string
  created_at: string
  started_at: string | null
  finished_at: string | null
  run_after: string
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
  publishChannels: () => http.get<PublishChannel[]>('/publish-channels'),
  createPublishChannel: (body: PublishChannelInput) =>
    http.post<PublishChannel>('/publish-channels', body),
  updatePublishChannel: (id: string, body: Partial<PublishChannelInput>) =>
    http.patch<PublishChannel>(`/publish-channels/${id}`, body),
  testPublishChannel: (id: string) =>
    http.post<{ plan: string; duration_ms: number; cost_usd: number }>(`/publish-channels/${id}/test`),
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

  profiles: () => http.get<{ items: Profile[]; languages: Record<string, string> }>('/profiles'),
  createProfile: (body: ProfileInput) => http.post<Profile>('/profiles', body),
  updateProfile: (id: string, body: ProfileInput) => http.patch<Profile>(`/profiles/${id}`, body),
  deleteProfile: (id: string) => http.delete<null>(`/profiles/${id}`),

  templates: () => http.get<{ items: Template[]; strategies: Record<Strategy, string> }>('/templates'),
  createTemplate: (body: TemplateInput) => http.post<Template>('/templates', body),
  copyTemplate: (id: string) => http.post<Template>(`/templates/${id}/copy`),
  updateTemplate: (id: string, body: TemplateInput) => http.patch<Template>(`/templates/${id}`, body),
  deleteTemplate: (id: string) => http.delete<null>(`/templates/${id}`),

  scripts: (params: ScriptQuery) => http.get<{ items: Script[]; total: number }>('/scripts', params),
  generateScripts: (body: { template_id: string; profile_id: string; variants: number }) =>
    http.post<Script[]>('/scripts/generate', body),
  updateScript: (id: string, body: ScriptInput) => http.patch<Script>(`/scripts/${id}`, body),
  regenerateScript: (id: string) => http.post<Script>(`/scripts/${id}/regenerate`),
  deleteScript: (id: string) => http.delete<null>(`/scripts/${id}`),
  // 配音要等上游產生，最多約 3 分鐘
  scriptAudio: (id: string) => http.post<AudioResult>(`/scripts/${id}/preview-audio`, {}, { timeout: 200_000 }),

  voices: () => http.get<{ active_engine: VoiceEngine | null; items: Voice[] }>('/voices'),
  // Gemini 音色第一次試聽要產生樣本，約 5～30 秒
  voiceSample: (id: string) => http.post<AudioResult>(`/voices/${id}/sample`, {}, { timeout: 200_000 }),
  voicePreview: (body: { voice_id: string; text: string; speed: number }) =>
    http.post<AudioResult>('/voices/preview', body, { timeout: 200_000 }),

  videos: (params: { limit: number; offset: number; status?: VideoStatus; script_id?: string }) =>
    http.get<{ items: Video[]; total: number }>('/videos', params),
  videoStats: () => http.get<Record<VideoStatus, number>>('/videos/stats'),
  videoStyles: () => http.get<Record<string, string>>('/videos/styles'),
  videoCoverage: (script_ids: string[]) => http.post<Coverage>('/videos/coverage', { script_ids }),
  generateVideos: (body: {
    script_ids: string[]
    per_script: number
    style: string
    ambience: number
    bgm: string
    bgm_volume: number
  }) =>
    http.post<Video[]>('/videos/generate', body),
  video: (id: string) => http.get<VideoDetail>(`/videos/${id}`),
  reviewVideo: (id: string, action: 'approve' | 'reject', note = '') =>
    http.post<VideoDetail>(`/videos/${id}/review`, { action, note }),
  videoCandidates: (id: string, shot: number) => http.get<ClipCandidate[]>(`/videos/${id}/candidates`, { shot }),
  replaceVideoClip: (id: string, shot_index: number, clip_id: string) =>
    http.post<VideoDetail>(`/videos/${id}/replace`, { shot_index, clip_id }),
  rerenderVideo: (id: string, reshuffle: boolean) => http.post<VideoDetail>(`/videos/${id}/rerender`, { reshuffle }),
  deleteVideo: (id: string) => http.delete<null>(`/videos/${id}`),

  music: () => http.get<{ items: MusicTrack[]; presets: string[] }>('/music'),
  generateMusic: (body: { preset: string; extra?: string; title?: string }) => http.post<MusicTrack>('/music/generate', body),
  updateMusic: (id: string, body: Partial<{ title: string; is_active: boolean }>) => http.patch<MusicTrack>(`/music/${id}`, body),
  deleteMusic: (id: string) => http.delete<null>(`/music/${id}`),

  tasks: (params: { limit: number; offset: number; status?: TaskStatus; type?: string }) =>
    http.get<{ items: TaskItem[]; total: number; counts: Partial<Record<TaskStatus, number>>; types: Record<string, string> }>(
      '/tasks',
      params,
    ),
  retryTask: (id: string) => http.post<TaskItem>(`/tasks/${id}/retry`),

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
  music: '背景音樂',
  embedding: '向量',
}

/** 背景音樂 AI 產生的風格；與後端 app/services/music.py 的 STYLE_PRESETS 同步 */
export const MUSIC_PRESETS: Record<string, string> = {
  corporate: '企業形象（輕快、正面）',
  industrial: '工業節奏（電子、有力）',
  inspiring: '激勵感人（鋼琴、弦樂）',
  chill: '輕鬆 Lo-fi',
  energetic: '活潑流行（適合短影音）',
}

export const STRATEGY_LABELS: Record<Strategy, { label: string; color: string }> = {
  persona: { label: '人設型', color: 'purple' },
  traffic: { label: '流量型', color: 'orange' },
  conversion: { label: '成交型', color: 'green' },
}

export const SCRIPT_STATUS: Record<ScriptStatus, { label: string; color: string }> = {
  generating: { label: '產生中', color: 'processing' },
  draft: { label: '草稿', color: 'default' },
  approved: { label: '已核准', color: 'success' },
  failed: { label: '失敗', color: 'error' },
}

export const VOICE_ENGINES: Record<VoiceEngine, string> = {
  gemini: 'Gemini 3.8',
  elevenlabs: 'ElevenLabs',
}

export const VIDEO_STATUS: Record<VideoStatus, { label: string; color: string }> = {
  queued: { label: '排隊中', color: 'default' },
  rendering: { label: '渲染中', color: 'processing' },
  pending_review: { label: '待審', color: 'gold' },
  approved: { label: '已通過', color: 'success' },
  rejected: { label: '已退回', color: 'red' },
  failed: { label: '失敗', color: 'error' },
}

export const TASK_STATUS: Record<TaskStatus, { label: string; color: string }> = {
  queued: { label: '排隊中', color: 'default' },
  running: { label: '執行中', color: 'processing' },
  succeeded: { label: '完成', color: 'success' },
  failed: { label: '失敗', color: 'error' },
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
