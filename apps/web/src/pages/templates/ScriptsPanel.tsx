import { CheckOutlined, DeleteOutlined, ReloadOutlined, SoundOutlined } from '@ant-design/icons'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert,
  App,
  Button,
  Card,
  Col,
  Drawer,
  Empty,
  Form,
  Grid,
  Input,
  Pagination,
  Popconfirm,
  Row,
  Select,
  Space,
  Tag,
  Typography,
} from 'antd'
import dayjs from 'dayjs'
import { useState } from 'react'
import { api, SCENE_LABELS, SCRIPT_STATUS, type Script, type ScriptStatus, type Template } from '../../api'
import { ApiError } from '../../api/http'
import { playAudio } from '../../audio'

const PAGE_SIZE = 12

function errorText(error: unknown) {
  return error instanceof ApiError ? error.message : '操作失敗'
}

export default function ScriptsPanel({
  templates,
  templateId,
  onTemplateChange,
}: {
  templates: Template[]
  templateId?: string
  onTemplateChange: (id?: string) => void
}) {
  const [status, setStatus] = useState<ScriptStatus | undefined>()
  const [profileId, setProfileId] = useState<string | undefined>()
  const [page, setPage] = useState(1)
  const [selected, setSelected] = useState<string | null>(null)
  const { data: profileData } = useQuery({ queryKey: ['profiles'], queryFn: api.profiles })

  const { data, isPending } = useQuery({
    queryKey: ['scripts', { templateId, status, profileId, page }],
    queryFn: () =>
      api.scripts({
        template_id: templateId,
        status,
        profile_id: profileId,
        limit: PAGE_SIZE,
        offset: (page - 1) * PAGE_SIZE,
      }),
    placeholderData: keepPreviousData,
    refetchInterval: (query) => (query.state.data?.items.some((s) => s.status === 'generating') ? 3000 : false),
  })
  const scripts = data?.items ?? []
  const current = scripts.find((s) => s.id === selected) ?? null

  return (
    <>
      <div className="asset-filters section">
        <Select
          placeholder="全部模板"
          allowClear
          className="asset-filter"
          value={templateId}
          onChange={(v?: string) => {
            onTemplateChange(v)
            setPage(1)
          }}
          options={templates.map((t) => ({ value: t.id, label: t.name }))}
        />
        <Select
          placeholder="全部帳號檔案"
          allowClear
          className="asset-filter"
          value={profileId}
          onChange={(v?: string) => {
            setProfileId(v)
            setPage(1)
          }}
          options={(profileData?.items ?? []).map((p) => ({ value: p.id, label: p.name }))}
        />
        <Select
          placeholder="全部狀態"
          allowClear
          className="asset-filter"
          value={status}
          onChange={(v?: ScriptStatus) => {
            setStatus(v)
            setPage(1)
          }}
          options={Object.entries(SCRIPT_STATUS).map(([value, s]) => ({ value, label: s.label }))}
        />
      </div>

      {data && scripts.length === 0 ? (
        <Card>
          <Empty description="還沒有文案。到「模板」分頁選一個模板，按「產生文案」。" />
        </Card>
      ) : null}
      <Row gutter={[16, 16]}>
        {scripts.map((script) => (
          <Col key={script.id} xs={24} md={12} xl={8}>
            <Card hoverable size="small" onClick={() => setSelected(script.id)} className="script-card">
              <div className="script-card-head">
                <Tag color={SCRIPT_STATUS[script.status].color}>{SCRIPT_STATUS[script.status].label}</Tag>
                <Typography.Text strong ellipsis className="script-title">
                  {script.title || `版本 ${script.variant}`}
                </Typography.Text>
              </div>
              <Typography.Paragraph ellipsis={{ rows: 2 }} className="script-hook">
                {script.status === 'generating' ? 'AI 正在撰寫…' : script.hook || script.error || '—'}
              </Typography.Paragraph>
              <Typography.Text type="secondary" className="small">
                {script.template_name} · {script.profile_name} · {script.language} · 約 {Math.round(script.total_seconds)} 秒 ·{' '}
                {dayjs(script.created_at).format('MM/DD HH:mm')}
              </Typography.Text>
              {script.error && script.status !== 'generating' ? (
                <div>
                  <Tag color={script.status === 'failed' ? 'red' : 'orange'} className="script-warn">
                    {script.status === 'failed' ? '失敗' : '需檢查'}
                  </Tag>
                </div>
              ) : null}
            </Card>
          </Col>
        ))}
        {isPending
          ? Array.from({ length: 3 }, (_, i) => (
              <Col key={i} xs={24} md={12} xl={8}>
                <Card loading size="small" />
              </Col>
            ))
          : null}
      </Row>
      {data && data.total > PAGE_SIZE ? (
        <Pagination
          className="asset-pagination"
          current={page}
          pageSize={PAGE_SIZE}
          total={data.total}
          showSizeChanger={false}
          onChange={setPage}
        />
      ) : null}
      <ScriptDrawer script={current} onClose={() => setSelected(null)} />
    </>
  )
}

interface ScriptForm {
  title: string
  hook: string
  shots: { voiceover: string; caption: string }[]
  post_caption: string
  hashtags: string[]
}

function ScriptDrawer({ script, onClose }: { script: Script | null; onClose: () => void }) {
  const screens = Grid.useBreakpoint()
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const [form] = Form.useForm<ScriptForm>()
  const [audio, setAudio] = useState<string | null>(null)
  const busy = script?.status === 'generating'

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ['scripts'] })
    void queryClient.invalidateQueries({ queryKey: ['templates'] })
    void queryClient.invalidateQueries({ queryKey: ['profiles'] })
  }
  const save = useMutation({
    mutationFn: (extra: { status?: 'draft' | 'approved' }) =>
      api.updateScript(script!.id, { ...form.getFieldsValue(), ...extra }),
    onSuccess: (_, extra) => {
      message.success(extra.status === 'approved' ? '已核准，Phase 3 混剪會使用這份文案' : '已儲存')
      refresh()
    },
    onError: (e) => message.error(errorText(e)),
  })
  const regenerate = useMutation({
    mutationFn: () => api.regenerateScript(script!.id),
    onSuccess: () => {
      message.success('已重新排入產生')
      refresh()
    },
    onError: (e) => message.error(errorText(e)),
  })
  const remove = useMutation({
    mutationFn: () => api.deleteScript(script!.id),
    onSuccess: () => {
      message.success('已刪除')
      refresh()
      onClose()
    },
    onError: (e) => message.error(errorText(e)),
  })
  const listen = useMutation({
    mutationFn: () => api.scriptAudio(script!.id),
    onSuccess: (data) => {
      setAudio(data.audio_url)
      playAudio(data.audio_url)
    },
    onError: (e) => message.error(errorText(e)),
  })

  return (
    <Drawer
      open={!!script}
      onClose={() => {
        setAudio(null)
        onClose()
      }}
      size={screens.md ? 760 : '100%'}
      title={script ? `${script.template_name} · 版本 ${script.variant}` : ''}
      destroyOnHidden
      extra={
        script && !busy ? (
          <Space wrap>
            <Button onClick={() => save.mutate({})} loading={save.isPending && !save.variables?.status}>
              儲存
            </Button>
            {script.status === 'approved' ? (
              <Button onClick={() => save.mutate({ status: 'draft' })}>取消核准</Button>
            ) : (
              <Button
                type="primary"
                icon={<CheckOutlined />}
                disabled={script.status === 'failed'}
                loading={save.isPending && save.variables?.status === 'approved'}
                onClick={() => save.mutate({ status: 'approved' })}
              >
                核准
              </Button>
            )}
          </Space>
        ) : null
      }
    >
      {script ? (
        busy ? (
          <Alert type="info" showIcon title="AI 正在撰寫這份文案，完成後會自動顯示" description={script.error || undefined} />
        ) : (
          <>
            {script.error ? (
              <Alert className="section" type={script.status === 'failed' ? 'error' : 'warning'} showIcon title={script.error} />
            ) : null}
            <Space wrap className="section">
              <Button icon={<SoundOutlined />} loading={listen.isPending} onClick={() => listen.mutate()} disabled={script.status === 'failed'}>
                {listen.isPending ? '配音產生中…' : '試聽整段配音'}
              </Button>
              <Popconfirm title="重新產生這個版本？" description="目前的內容會被覆蓋。" onConfirm={() => regenerate.mutate()}>
                <Button icon={<ReloadOutlined />} loading={regenerate.isPending}>
                  重新產生
                </Button>
              </Popconfirm>
              <Popconfirm title="刪除這份文案？" okText="刪除" okButtonProps={{ danger: true }} onConfirm={() => remove.mutate()}>
                <Button danger icon={<DeleteOutlined />}>
                  刪除
                </Button>
              </Popconfirm>
            </Space>
            {audio ? <audio src={audio} controls className="full-width section" /> : null}
            <Form
              key={script.updated_at}
              form={form}
              layout="vertical"
              initialValues={{
                title: script.title,
                hook: script.hook,
                shots: script.shots.map((s) => ({ voiceover: s.voiceover, caption: s.caption })),
                post_caption: script.post_caption,
                hashtags: script.hashtags,
              }}
            >
              <Form.Item name="title" label="標題（內部辨識用）">
                <Input maxLength={200} />
              </Form.Item>
              <Form.Item name="hook" label="開場鉤子">
                <Input.TextArea maxLength={300} autoSize={{ minRows: 1, maxRows: 3 }} />
              </Form.Item>
              <Typography.Title level={5}>鏡頭</Typography.Title>
              <div className="shot-list section">
                {script.shots.map((shot, index) => (
                  <div key={index} className="shot-row">
                    <span className="shot-index">{index + 1}</span>
                    <div className="shot-body">
                      <Typography.Text type="secondary" className="small">
                        {shot.brief}
                        {shot.scene ? ` · ${SCENE_LABELS[shot.scene] ?? shot.scene}` : ''} · {shot.seconds} 秒
                      </Typography.Text>
                      <Form.Item name={['shots', index, 'voiceover']} label="配音稿" className="shot-field">
                        <Input.TextArea maxLength={600} autoSize={{ minRows: 1, maxRows: 4 }} />
                      </Form.Item>
                      <Form.Item name={['shots', index, 'caption']} label="畫面字幕" className="shot-field">
                        <Input maxLength={120} />
                      </Form.Item>
                    </div>
                  </div>
                ))}
              </div>
              <Form.Item name="post_caption" label="貼文說明（發佈時使用）">
                <Input.TextArea maxLength={2200} autoSize={{ minRows: 2, maxRows: 5 }} />
              </Form.Item>
              <Form.Item name="hashtags" label="Hashtag">
                <Select mode="tags" open={false} tokenSeparators={[',', '，', ' ']} />
              </Form.Item>
            </Form>
          </>
        )
      ) : null}
    </Drawer>
  )
}
