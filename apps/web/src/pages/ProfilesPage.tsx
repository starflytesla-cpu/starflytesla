import { DeleteOutlined, EditOutlined, PlusOutlined } from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  App,
  AutoComplete,
  Button,
  Card,
  Col,
  Drawer,
  Empty,
  Form,
  Grid,
  Input,
  Popconfirm,
  Row,
  Select,
  Slider,
  Space,
  Tag,
  Typography,
} from 'antd'
import { useState } from 'react'
import { api, VOICE_ENGINES, type Profile, type ProfileInput, type VoiceEngine } from '../api'
import { ApiError } from '../api/http'
import VoicePlayButton from '../components/VoicePlayButton'
import QueryFeedback from '../components/QueryFeedback'
import PageHeader from '../components/PageHeader'

const TONE_SUGGESTIONS = ['專業可靠', '親切熱情', '幽默輕鬆', '自信直接', '溫暖有人情味'].map((value) => ({ value }))

function errorText(error: unknown) {
  return error instanceof ApiError ? error.message : '操作失敗'
}

export default function ProfilesPage() {
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const { data, isPending, error, refetch } = useQuery({
    queryKey: ['profiles'],
    queryFn: api.profiles,
  })
  const [editing, setEditing] = useState<Profile | 'new' | null>(null)
  const languages = data?.languages ?? {}

  const remove = useMutation({
    mutationFn: (id: string) => api.deleteProfile(id),
    onSuccess: () => {
      message.success('已刪除')
      void queryClient.invalidateQueries({ queryKey: ['profiles'] })
    },
    onError: (e) => message.error(errorText(e)),
  })

  return (
    <>
      <PageHeader
        title="帳號檔案"
        subtitle="品牌人設：AI 寫文案、挑素材、配音都會參考這份資料。一個帳號群對應一份。"
        extra={
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setEditing('new')}>
            新增帳號檔案
          </Button>
        }
      />
      <QueryFeedback error={error} retry={refetch} />
      {data && data.items.length === 0 ? (
        <Card>
          <Empty description="還沒有帳號檔案。先建立一份，寫文案時才知道品牌、賣點和語言。">
            <Button type="primary" onClick={() => setEditing('new')}>
              建立第一份
            </Button>
          </Empty>
        </Card>
      ) : null}
      <Row gutter={[16, 16]}>
        {(data?.items ?? []).map((profile) => (
          <Col key={profile.id} xs={24} md={12} xl={8}>
            <Card
              className="full-height"
              title={profile.name}
              extra={
                <Space>
                  <Button type="text" icon={<EditOutlined />} onClick={() => setEditing(profile)} aria-label="編輯" />
                  <Popconfirm
                    title="刪除這份帳號檔案？"
                    description="已產生的文案會保留。"
                    okText="刪除"
                    okButtonProps={{ danger: true }}
                    onConfirm={() => remove.mutate(profile.id)}
                  >
                    <Button type="text" danger icon={<DeleteOutlined />} aria-label="刪除" />
                  </Popconfirm>
                </Space>
              }
            >
              <div className="profile-tags">
                <Tag color="blue">{languages[profile.target_language] ?? profile.target_language}</Tag>
                {profile.industry ? <Tag>{profile.industry}</Tag> : null}
                {profile.voice_name ? <Tag color="purple">音色：{profile.voice_name}</Tag> : <Tag>未選音色</Tag>}
              </div>
              {profile.audience ? (
                <Typography.Paragraph type="secondary" ellipsis={{ rows: 2 }} className="profile-line">
                  受眾：{profile.audience}
                </Typography.Paragraph>
              ) : null}
              {profile.selling_points.length ? (
                <Typography.Paragraph ellipsis={{ rows: 2 }} className="profile-line">
                  賣點：{profile.selling_points.join('、')}
                </Typography.Paragraph>
              ) : null}
              <Typography.Text type="secondary" className="small">
                已產生 {profile.script_count ?? '—'} 份文案
              </Typography.Text>
            </Card>
          </Col>
        ))}
        {isPending ? (
          <Col xs={24} md={12} xl={8}>
            <Card loading />
          </Col>
        ) : null}
      </Row>
      <ProfileDrawer target={editing} languages={languages} onClose={() => setEditing(null)} />
    </>
  )
}

function ProfileDrawer({
  target,
  languages,
  onClose,
}: {
  target: Profile | 'new' | null
  languages: Record<string, string>
  onClose: () => void
}) {
  const screens = Grid.useBreakpoint()
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const [form] = Form.useForm<ProfileInput>()
  const { data: voiceData } = useQuery({
    queryKey: ['voices'],
    queryFn: api.voices,
    enabled: !!target,
  })
  const voices = voiceData?.items
  const active = voiceData?.active_engine ?? 'gemini'
  const engines = (Object.keys(VOICE_ENGINES) as VoiceEngine[]).sort((a) => (a === active ? -1 : 1))
  const voiceId = Form.useWatch('voice_id', form)
  const selectedVoice = voices?.find((v) => v.id === voiceId)

  const save = useMutation({
    mutationFn: (values: ProfileInput) =>
      target === 'new' ? api.createProfile(values) : api.updateProfile((target as Profile).id, values),
    onSuccess: () => {
      message.success('已儲存')
      void queryClient.invalidateQueries({ queryKey: ['profiles'] })
      onClose()
    },
    onError: (e) => message.error(errorText(e)),
  })

  const initial: ProfileInput =
    target && target !== 'new'
      ? target
      : {
          target_language: 'en',
          voice_speed: 1,
          selling_points: [],
          hashtags: [],
          banned_words: [],
        }

  return (
    <Drawer
      open={!!target}
      onClose={onClose}
      size={screens.md ? 640 : '100%'}
      title={target === 'new' ? '新增帳號檔案' : '編輯帳號檔案'}
      destroyOnHidden
      extra={
        <Button type="primary" loading={save.isPending} onClick={() => form.submit()}>
          儲存
        </Button>
      }
    >
      <Form form={form} layout="vertical" initialValues={initial} onFinish={(values) => save.mutate(values)}>
        <h3 className="form-section-title">品牌與影片語言</h3>
        <Form.Item name="name" label="名稱（品牌 / 門店）" rules={[{ required: true, message: '請填寫名稱' }]}>
          <Input maxLength={80} placeholder="例如 Acme Precision Parts" />
        </Form.Item>
        <Row gutter={12}>
          <Col xs={24} sm={12}>
            <Form.Item name="industry" label="行業">
              <Input maxLength={120} placeholder="例如 CNC 精密加工、手工家具" />
            </Form.Item>
          </Col>
          <Col xs={24} sm={12}>
            <Form.Item name="target_language" label="影片語言" extra="文案與配音都用這個語言">
              <Select
                showSearch
                optionFilterProp="label"
                options={Object.entries(languages).map(([value, label]) => ({
                  value,
                  label,
                }))}
              />
            </Form.Item>
          </Col>
        </Row>
        <h3 className="form-section-title">受眾、賣點與產品事實</h3>
        <Form.Item name="audience" label="目標受眾">
          <Input.TextArea
            maxLength={500}
            autoSize={{ minRows: 2, maxRows: 4 }}
            placeholder="例如 美國、歐洲的五金品牌採購，重視品質與交期"
          />
        </Form.Item>
        <Form.Item name="selling_points" label="核心賣點" extra="輸入後按 Enter，可加多個；AI 只會使用這裡寫的事實">
          <Select
            mode="tags"
            open={false}
            tokenSeparators={[',', '，']}
            placeholder="例如 15 年經驗、ISO 9001、7 天打樣"
          />
        </Form.Item>
        <Form.Item name="product_details" label="產品詳情">
          <Input.TextArea
            maxLength={5000}
            autoSize={{ minRows: 3, maxRows: 8 }}
            placeholder="主力產品、材質、規格、起訂量、交期、可客製項目等"
          />
        </Form.Item>
        <Row gutter={12}>
          <Col xs={24} sm={12}>
            <Form.Item name="tone" label="說話口吻">
              <AutoComplete options={TONE_SUGGESTIONS} maxLength={200} placeholder="選擇或輸入，例如 專業可靠" />
            </Form.Item>
          </Col>
          <Col xs={24} sm={12}>
            <Form.Item name="call_to_action" label="行動呼籲（影片結尾）">
              <Input maxLength={200} placeholder="例如 DM us for a free quote" />
            </Form.Item>
          </Col>
        </Row>
        <Form.Item name="hashtags" label="常用 Hashtag">
          <Select mode="tags" open={false} tokenSeparators={[',', '，', ' ']} placeholder="例如 #cnc #madeintaiwan" />
        </Form.Item>
        <Form.Item
          name="banned_words"
          label="禁用詞"
          extra="例如沒有取得的認證、競品名稱、誇大用語；AI 文案出現時會提醒"
        >
          <Select mode="tags" open={false} tokenSeparators={[',', '，']} />
        </Form.Item>
        <h3 className="form-section-title">配音設定</h3>
        <Form.Item
          label="配音音色"
          htmlFor="profile-voice"
          extra="請選「目前使用中」引擎的音色；可以到「音色管理」試聽"
        >
          <Space.Compact className="full-width">
            <Form.Item name="voice_id" noStyle>
              <Select
                id="profile-voice"
                showSearch
                allowClear
                optionFilterProp="label"
                placeholder="選擇音色"
                options={engines.map((engine) => ({
                  label: `${VOICE_ENGINES[engine]}${engine === active ? '（目前使用中）' : ''}`,
                  options: (voices ?? [])
                    .filter((v) => v.engine === engine)
                    .sort((a, b) => Number(b.recommended) - Number(a.recommended))
                    .map((v) => ({
                      value: v.id,
                      label: `${v.name} · ${v.description}${v.recommended ? ' ★' : ''}`,
                    })),
                }))}
              />
            </Form.Item>
            {selectedVoice ? <VoicePlayButton voice={selectedVoice} /> : null}
          </Space.Compact>
        </Form.Item>
        <Form.Item name="voice_speed" label="配音語速">
          <Slider min={0.7} max={1.2} step={0.05} marks={{ 0.7: '慢', 1: '正常', 1.2: '快' }} />
        </Form.Item>
      </Form>
    </Drawer>
  )
}
