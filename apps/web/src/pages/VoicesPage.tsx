import { SoundOutlined } from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, App, Button, Card, Col, Empty, Form, Input, Modal, Row, Segmented, Select, Slider, Space, Tag, Typography } from 'antd'
import { useMemo, useState } from 'react'
import { api, formatUsd, VOICE_ENGINES, type Voice, type VoiceEngine } from '../api'
import { ApiError } from '../api/http'
import { playAudio } from '../audio'
import VoicePlayButton from '../components/VoicePlayButton'
import PageHeader from '../components/PageHeader'

const SAMPLE_TEXT =
  "Welcome to our factory! Every part is machined, inspected and packed right here. Send us a message and we'll get back to you within 24 hours."

export default function VoicesPage() {
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const { data: voiceData, isPending } = useQuery({ queryKey: ['voices'], queryFn: api.voices })
  const voices = voiceData?.items
  const active = voiceData?.active_engine ?? null
  const [engine, setEngine] = useState<VoiceEngine | null>(null)
  const currentEngine: VoiceEngine = engine ?? active ?? 'gemini'
  const { data: profileData } = useQuery({ queryKey: ['profiles'], queryFn: api.profiles })
  const [scope, setScope] = useState<'recommended' | 'all'>('recommended')
  const [keyword, setKeyword] = useState('')
  const [trying, setTrying] = useState<Voice | null>(null)

  const profiles = profileData?.items ?? []
  const shown = useMemo(() => {
    const q = keyword.trim().toLowerCase()
    return (voices ?? []).filter(
      (v) =>
        v.engine === currentEngine &&
        (scope === 'all' || v.recommended) &&
        (!q || v.name.toLowerCase().includes(q) || v.description.toLowerCase().includes(q)),
    )
  }, [voices, scope, keyword, currentEngine])

  const bind = useMutation({
    mutationFn: ({ profileId, voiceId }: { profileId: string; voiceId: string }) =>
      api.updateProfile(profileId, { voice_id: voiceId }),
    onSuccess: (profile) => {
      message.success(`「${profile.name}」改用 ${profile.voice_name}`)
      void queryClient.invalidateQueries({ queryKey: ['profiles'] })
    },
    onError: (e) => message.error(e instanceof ApiError ? e.message : '操作失敗'),
  })

  return (
    <>
      <PageHeader
        title="音色管理"
        subtitle="試聽音色並綁定到帳號檔案。ElevenLabs 試聽免費；Gemini 第一次試聽會產生一段樣本（約 US$0.001）；自訂文字試聽會扣 kie.ai 點數"
      />
      {active ? (
        <Alert
          className="section"
          type="info"
          showIcon
          title={`目前成片配音使用 ${VOICE_ENGINES[active]} 音色`}
          description="帳號檔案綁定的音色如果不是這個引擎，產生成片時會自動改用該引擎的預設音色（Gemini：Kore）。要切換引擎，請到「模型渠道」把想用的配音模型設為預設（星號）。"
        />
      ) : (
        <Alert className="section" type="warning" showIcon title="尚未設定配音模型，請到「模型渠道」新增 kie.ai 渠道" />
      )}
      <div className="asset-filters section">
        <Segmented
          value={currentEngine}
          onChange={(v) => setEngine(v as VoiceEngine)}
          options={(Object.keys(VOICE_ENGINES) as VoiceEngine[]).map((key) => ({
            value: key,
            label: key === active ? `${VOICE_ENGINES[key]}（使用中）` : VOICE_ENGINES[key],
          }))}
        />
        <Segmented
          value={scope}
          onChange={(v) => setScope(v as 'recommended' | 'all')}
          options={[
            { value: 'recommended', label: '推薦旁白' },
            { value: 'all', label: `全部（${(voices ?? []).filter((v) => v.engine === currentEngine).length}）` },
          ]}
        />
        <Input.Search placeholder="搜尋名稱或風格，例如 warm" allowClear onSearch={setKeyword} className="asset-search" />
      </div>

      {shown.length === 0 && !isPending ? <Empty description="沒有符合的音色" /> : null}
      <Row gutter={[12, 12]}>
        {shown.map((voice) => {
          const bound = profiles.filter((p) => p.voice_id === voice.id)
          return (
            <Col key={voice.id} xs={24} sm={12} lg={8} xl={6}>
              <Card size="small" className="voice-card">
                <div className="voice-head">
                  <VoicePlayButton voice={voice} shape="circle" type="primary" />
                  <div className="voice-meta">
                    <Typography.Text strong>{voice.name}</Typography.Text>
                    <Typography.Text type="secondary" className="small">
                      {voice.description}
                    </Typography.Text>
                  </div>
                </div>
                <div className="voice-tags">
                  {bound.map((p) => (
                    <Tag key={p.id} color="blue">
                      {p.name}
                    </Tag>
                  ))}
                </div>
                <Space wrap>
                  <Button size="small" icon={<SoundOutlined />} onClick={() => setTrying(voice)}>
                    自訂文字試聽
                  </Button>
                  {profiles.length ? (
                    <Select
                      size="small"
                      placeholder="綁定到帳號檔案"
                      value={null}
                      className="voice-bind"
                      options={profiles
                        .filter((p) => p.voice_id !== voice.id)
                        .map((p) => ({ value: p.id, label: p.name }))}
                      onChange={(profileId: string) => bind.mutate({ profileId, voiceId: voice.id })}
                    />
                  ) : null}
                </Space>
              </Card>
            </Col>
          )
        })}
        {isPending
          ? Array.from({ length: 8 }, (_, i) => (
              <Col key={i} xs={24} sm={12} lg={8} xl={6}>
                <Card size="small" loading />
              </Col>
            ))
          : null}
      </Row>

      <TryVoiceModal voice={trying} onClose={() => setTrying(null)} />
    </>
  )
}

function TryVoiceModal({ voice, onClose }: { voice: Voice | null; onClose: () => void }) {
  const [form] = Form.useForm<{ text: string; speed: number }>()
  const [result, setResult] = useState<{ url: string; cost: number | null } | null>(null)
  const preview = useMutation({
    mutationFn: (values: { text: string; speed: number }) => api.voicePreview({ voice_id: voice!.id, ...values }),
    onSuccess: (data) => {
      setResult({ url: data.audio_url, cost: data.cost_usd })
      playAudio(data.audio_url)
    },
  })

  return (
    <Modal
      open={!!voice}
      title={voice ? `用自訂文字試聽：${voice.name}` : ''}
      onCancel={() => {
        setResult(null)
        preview.reset()
        onClose()
      }}
      okText="產生配音"
      confirmLoading={preview.isPending}
      onOk={() => form.submit()}
      destroyOnHidden
    >
      <Form form={form} layout="vertical" initialValues={{ text: SAMPLE_TEXT, speed: 1 }} onFinish={(v) => preview.mutate(v)}>
        <Form.Item name="text" label="文字（任何語言都可以）" rules={[{ required: true, message: '請輸入文字' }]}>
          <Input.TextArea maxLength={1500} showCount autoSize={{ minRows: 3, maxRows: 8 }} />
        </Form.Item>
        <Form.Item name="speed" label="語速">
          <Slider min={0.7} max={1.2} step={0.05} marks={{ 0.7: '慢', 1: '正常', 1.2: '快' }} />
        </Form.Item>
      </Form>
      {preview.isPending ? <Alert type="info" showIcon title="配音產生中，約 5～30 秒…" /> : null}
      {preview.error ? (
        <Alert type="error" showIcon title={preview.error instanceof ApiError ? preview.error.message : '配音失敗'} />
      ) : null}
      {result ? (
        <>
          <audio src={result.url} controls className="full-width section" />
          <Typography.Text type="secondary" className="small">
            這次花費：{formatUsd(result.cost)}
          </Typography.Text>
        </>
      ) : null}
    </Modal>
  )
}
