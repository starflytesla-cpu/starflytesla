import {
  DeleteOutlined,
  EditOutlined,
  ExperimentOutlined,
  PlusOutlined,
  StarFilled,
  StarOutlined,
} from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert,
  App,
  Button,
  Card,
  Collapse,
  Descriptions,
  Grid,
  Empty,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Radio,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Tooltip,
  Typography,
} from 'antd'
import { useState } from 'react'
import {
  api,
  CAPABILITY_LABELS,
  formatUsd,
  type Capability,
  type Channel,
  type ChannelModel,
  type Provider,
  type TestResult,
} from '../api'
import { ApiError } from '../api/http'
import QueryFeedback from '../components/QueryFeedback'
import PageHeader from '../components/PageHeader'

// 可以在後台按「測試」的模型：文字 / 看圖回覆一句話，配音產生一段試聽音檔
const CHAT_CAPS: Capability[] = ['text', 'vision', 'tts']

function errorText(error: unknown) {
  return error instanceof ApiError ? error.message : '操作失敗'
}

export default function ChannelsPage() {
  const queryClient = useQueryClient()
  const screens = Grid.useBreakpoint()
  const { message } = App.useApp()
  const { data: channels, isPending, error, refetch } = useQuery({ queryKey: ['channels'], queryFn: api.channels })
  const { data: presetData } = useQuery({
    queryKey: ['presets'],
    queryFn: api.presets,
    staleTime: Infinity,
  })

  const [addOpen, setAddOpen] = useState(false)
  const [editing, setEditing] = useState<Channel | null>(null)
  const [modelTarget, setModelTarget] = useState<{
    channel: Channel
    model?: ChannelModel
  } | null>(null)
  const [testResult, setTestResult] = useState<{
    model: ChannelModel
    result: TestResult
  } | null>(null)
  const [testingId, setTestingId] = useState<string | null>(null)

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ['channels'] })
    queryClient.invalidateQueries({ queryKey: ['dashboard'] })
  }

  const run = async (action: () => Promise<unknown>, success?: string) => {
    try {
      await action()
      if (success) message.success(success)
      refresh()
    } catch (error) {
      message.error(errorText(error))
    }
  }

  const test = useMutation({
    mutationFn: (model: ChannelModel) => api.testModel(model.id),
    onMutate: (model) => setTestingId(model.id),
    onSuccess: (result, model) => {
      setTestResult({ model, result })
      queryClient.invalidateQueries({ queryKey: ['usage'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
    onError: (error) => message.error(errorText(error), 6),
    onSettled: () => setTestingId(null),
  })

  return (
    <>
      <PageHeader
        title="模型渠道"
        subtitle="設定 AI 服務商的 API Key 與模型。API Key 加密後存放在伺服器，設定後不會再顯示完整內容。"
        extra={
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setAddOpen(true)}>
            新增渠道
          </Button>
        }
      />

      <QueryFeedback error={error} retry={refetch} />
      {!isPending && channels?.length === 0 ? (
        <Card>
          <Empty description="還沒有任何渠道。建議先新增 DeepSeek（文字）和豆包（看圖）。">
            <Button type="primary" onClick={() => setAddOpen(true)}>
              新增第一個渠道
            </Button>
          </Empty>
        </Card>
      ) : null}

      <Space orientation="vertical" size={16} className="full-width">
        {channels?.map((channel) => (
          <Card
            key={channel.id}
            loading={isPending}
            title={
              <Space wrap>
                <span>{channel.name}</span>
                <Tag>{channel.provider}</Tag>
                {!channel.enabled ? <Tag color="default">已停用</Tag> : null}
              </Space>
            }
            extra={
              <Space wrap>
                <Tooltip title={channel.enabled ? '停用這個渠道' : '啟用這個渠道'}>
                  <Switch
                    aria-label={`啟用渠道 ${channel.name}`}
                    checked={channel.enabled}
                    onChange={(enabled) => run(() => api.updateChannel(channel.id, { enabled }))}
                  />
                </Tooltip>
                <Button icon={<EditOutlined />} onClick={() => setEditing(channel)}>
                  編輯
                </Button>
                <Popconfirm
                  title="刪除這個渠道？"
                  description="渠道下的模型會一起刪除，過去的成本記錄會保留。"
                  okText="刪除"
                  okButtonProps={{ danger: true }}
                  onConfirm={() => run(() => api.deleteChannel(channel.id), '渠道已刪除')}
                >
                  <Button danger icon={<DeleteOutlined />} aria-label="刪除渠道" />
                </Popconfirm>
              </Space>
            }
          >
            <Space wrap className="section">
              {[...new Set(channel.models.filter((m) => m.enabled).map((m) => m.capability))].map((cap) => (
                <Tag color="blue" key={cap}>
                  {CAPABILITY_LABELS[cap]}
                </Tag>
              ))}
              <span className="small muted">{channel.models.filter((m) => m.enabled).length} 個啟用模型</span>
              {channel.models
                .filter((m) => m.enabled && m.is_default)
                .map((m) => (
                  <Tag color="green" key={m.id}>
                    預設：{m.display_name || m.model_key}
                  </Tag>
                ))}
            </Space>
            <Collapse
              className="section"
              items={[
                {
                  key: 'connection',
                  label: '連線與金鑰詳情',
                  children: (
                    <Descriptions size="small" column={{ xs: 1, md: 2 }} className="section">
                      <Descriptions.Item label="Base URL">
                        <Typography.Text copyable className="mono">
                          {channel.base_url}
                        </Typography.Text>
                      </Descriptions.Item>
                      <Descriptions.Item label="API Key">
                        {channel.has_api_key ? (
                          <Tag color="green">已設定（末 4 碼 {channel.api_key_last4}）</Tag>
                        ) : (
                          <Tag color="orange">未設定</Tag>
                        )}
                      </Descriptions.Item>
                    </Descriptions>
                  ),
                },
              ]}
            />

            {screens.md ? (
              <Table<ChannelModel>
                size="small"
                rowKey="id"
                dataSource={channel.models}
                pagination={false}
                scroll={{ x: 720 }}
                locale={{ emptyText: '還沒有模型，按下方「新增模型」加入' }}
                columns={[
                  {
                    title: '模型',
                    render: (_, m) => (
                      <div>
                        <div>{m.display_name}</div>
                        <Typography.Text type="secondary" className="mono small">
                          {m.model_key}
                        </Typography.Text>
                      </div>
                    ),
                  },
                  {
                    title: '用途',
                    dataIndex: 'capability',
                    render: (cap: Capability) => <Tag color="blue">{CAPABILITY_LABELS[cap]}</Tag>,
                  },
                  {
                    title: '價格（每百萬 token）',
                    render: (_, m) =>
                      m.input_price_per_m === null || m.output_price_per_m === null ? (
                        <Typography.Text type="secondary">未設定</Typography.Text>
                      ) : (
                        <span className="small">
                          輸入 {formatUsd(m.input_price_per_m)} / 輸出 {formatUsd(m.output_price_per_m)}
                        </span>
                      ),
                  },
                  {
                    title: '預設',
                    render: (_, m) =>
                      m.is_default ? (
                        <Tooltip title={`「${CAPABILITY_LABELS[m.capability]}」任務預設使用這個模型`}>
                          <StarFilled className="star-on" />
                        </Tooltip>
                      ) : (
                        <Tooltip title="設為預設">
                          <Button
                            type="text"
                            size="small"
                            aria-label={`設 ${m.display_name} 為預設`}
                            icon={<StarOutlined />}
                            onClick={() => run(() => api.updateModel(m.id, { is_default: true }), '已設為預設')}
                          />
                        </Tooltip>
                      ),
                  },
                  {
                    title: '啟用',
                    render: (_, m) => (
                      <Switch
                        size="small"
                        aria-label={`啟用模型 ${m.display_name}`}
                        checked={m.enabled}
                        onChange={(enabled) => run(() => api.updateModel(m.id, { enabled }))}
                      />
                    ),
                  },
                  {
                    title: '操作',
                    render: (_, m) => (
                      <Space>
                        {CHAT_CAPS.includes(m.capability) ? (
                          <Button
                            size="small"
                            icon={<ExperimentOutlined />}
                            loading={testingId === m.id}
                            disabled={!channel.has_api_key}
                            onClick={() => test.mutate(m)}
                          >
                            測試（計費）
                          </Button>
                        ) : (
                          <Tooltip title="配音與向量模型會在對應階段串接">
                            <Button size="small" disabled>
                              測試
                            </Button>
                          </Tooltip>
                        )}
                        <Button
                          size="small"
                          icon={<EditOutlined />}
                          aria-label="編輯模型"
                          onClick={() => setModelTarget({ channel, model: m })}
                        />
                        <Popconfirm
                          title="刪除這個模型？"
                          okText="刪除"
                          okButtonProps={{ danger: true }}
                          onConfirm={() => run(() => api.deleteModel(m.id), '模型已刪除')}
                        >
                          <Button size="small" danger icon={<DeleteOutlined />} aria-label="刪除模型" />
                        </Popconfirm>
                      </Space>
                    ),
                  },
                ]}
              />
            ) : (
              <div className="record-list">
                {channel.models.map((m) => (
                  <div className="compact-record" key={m.id}>
                    <strong>{m.display_name || m.model_key}</strong>
                    <span className="mono small break-word">{m.model_key}</span>
                    <Space wrap>
                      <Tag>{CAPABILITY_LABELS[m.capability]}</Tag>
                      {m.is_default ? (
                        <Tag color="green">預設</Tag>
                      ) : (
                        <Button onClick={() => run(() => api.updateModel(m.id, { is_default: true }), '已設為預設')}>
                          設為預設
                        </Button>
                      )}
                      <Switch
                        aria-label={`啟用模型 ${m.display_name}`}
                        checked={m.enabled}
                        onChange={(enabled) => run(() => api.updateModel(m.id, { enabled }))}
                      />
                    </Space>
                    <p className="small muted">
                      每百萬 token · 輸入 {formatUsd(m.input_price_per_m)} / 輸出 {formatUsd(m.output_price_per_m)}
                    </p>
                    <Space wrap>
                      <Button
                        disabled={!channel.has_api_key || !CHAT_CAPS.includes(m.capability)}
                        loading={testingId === m.id}
                        onClick={() => test.mutate(m)}
                      >
                        測試（計費）
                      </Button>
                      <Button onClick={() => setModelTarget({ channel, model: m })}>編輯</Button>
                      <Popconfirm
                        title="刪除這個模型？"
                        onConfirm={() => run(() => api.deleteModel(m.id), '模型已刪除')}
                      >
                        <Button danger>刪除</Button>
                      </Popconfirm>
                    </Space>
                  </div>
                ))}
              </div>
            )}
            <Button
              type="dashed"
              icon={<PlusOutlined />}
              className="add-model"
              onClick={() => setModelTarget({ channel })}
            >
              新增模型
            </Button>
          </Card>
        ))}
      </Space>

      <AddChannelModal
        open={addOpen}
        presets={presetData?.presets ?? []}
        onClose={() => setAddOpen(false)}
        onCreated={() => {
          setAddOpen(false)
          refresh()
        }}
      />
      <EditChannelModal channel={editing} onClose={() => setEditing(null)} onSaved={refresh} />
      <ModelModal target={modelTarget} onClose={() => setModelTarget(null)} onSaved={refresh} />
      <Modal
        title="測試成功"
        open={!!testResult}
        onCancel={() => setTestResult(null)}
        footer={<Button onClick={() => setTestResult(null)}>關閉</Button>}
      >
        {testResult ? (
          <>
            <Alert
              type="success"
              showIcon
              title={testResult.result.reply || '（模型沒有回傳文字）'}
              className="section"
            />
            {testResult.result.audio_url ? (
              <audio src={testResult.result.audio_url} controls autoPlay className="full-width section" />
            ) : null}
            <Descriptions size="small" column={1} bordered>
              <Descriptions.Item label="模型">{testResult.model.display_name}</Descriptions.Item>
              <Descriptions.Item label={testResult.result.audio_url ? '字元數' : 'Token'}>
                {testResult.result.audio_url
                  ? testResult.result.input_tokens
                  : `輸入 ${testResult.result.input_tokens} / 輸出 ${testResult.result.output_tokens}`}
              </Descriptions.Item>
              <Descriptions.Item label="耗時">{(testResult.result.duration_ms / 1000).toFixed(1)} 秒</Descriptions.Item>
              <Descriptions.Item label="估算成本">{formatUsd(testResult.result.cost_usd)}</Descriptions.Item>
            </Descriptions>
          </>
        ) : null}
      </Modal>
    </>
  )
}

function AddChannelModal({
  open,
  presets,
  onClose,
  onCreated,
}: {
  open: boolean
  presets: {
    provider: Provider
    name: string
    base_url: string
    api_key_help: string
    models: string[]
  }[]
  onClose: () => void
  onCreated: () => void
}) {
  const [form] = Form.useForm<{
    provider: Provider
    name?: string
    base_url?: string
    api_key: string
  }>()
  const provider = Form.useWatch('provider', form) ?? 'deepseek'
  const preset = presets.find((p) => p.provider === provider)
  const [saving, setSaving] = useState(false)
  const { message } = App.useApp()

  const submit = async () => {
    const values = await form.validateFields()
    setSaving(true)
    try {
      await api.createChannel({
        ...values,
        name: values.name || undefined,
        base_url: values.base_url || undefined,
      })
      message.success('渠道已新增，可以按「測試」確認 API Key 是否可用')
      form.resetFields()
      onCreated()
    } catch (error) {
      message.error(errorText(error))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      title="新增渠道"
      open={open}
      onCancel={onClose}
      onOk={submit}
      okText="新增"
      confirmLoading={saving}
      destroyOnHidden
      width={560}
    >
      <Form form={form} layout="vertical" initialValues={{ provider: 'deepseek' }} requiredMark={false}>
        <Form.Item name="provider" label="服務商">
          <Radio.Group optionType="button" buttonStyle="solid" className="provider-radio">
            {presets.map((p) => (
              <Radio.Button key={p.provider} value={p.provider}>
                {p.name}
              </Radio.Button>
            ))}
          </Radio.Group>
        </Form.Item>
        {preset ? (
          <Alert
            type="info"
            className="section"
            title={preset.api_key_help}
            description={
              preset.models.length ? `會自動加入模型：${preset.models.join('、')}` : '新增後請手動加入要使用的模型'
            }
          />
        ) : null}
        <Form.Item name="name" label="名稱（選填）">
          <Input placeholder={preset?.name} />
        </Form.Item>
        <Form.Item
          name="base_url"
          label="Base URL"
          rules={provider === 'custom' ? [{ required: true, message: '自訂渠道需要填寫 Base URL' }] : []}
          extra={provider === 'custom' ? '必須是 https:// 開頭的 OpenAI 相容網址' : '一般不需要修改'}
        >
          <Input placeholder={preset?.base_url || 'https://'} />
        </Form.Item>
        <Form.Item name="api_key" label="API Key" rules={[{ required: true, message: '請貼上 API Key' }]}>
          <Input.Password placeholder="貼上 API Key" autoComplete="off" />
        </Form.Item>
      </Form>
    </Modal>
  )
}

function EditChannelModal({
  channel,
  onClose,
  onSaved,
}: {
  channel: Channel | null
  onClose: () => void
  onSaved: () => void
}) {
  const [form] = Form.useForm<{
    name: string
    base_url: string
    api_key?: string
  }>()
  const [saving, setSaving] = useState(false)
  const { message } = App.useApp()

  const submit = async () => {
    if (!channel) return
    const values = await form.validateFields()
    setSaving(true)
    try {
      await api.updateChannel(channel.id, {
        name: values.name,
        base_url: values.base_url,
        ...(values.api_key ? { api_key: values.api_key } : {}),
      })
      message.success('已更新')
      onSaved()
      onClose()
    } catch (error) {
      message.error(errorText(error))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      title="編輯渠道"
      open={!!channel}
      onCancel={onClose}
      onOk={submit}
      okText="儲存"
      confirmLoading={saving}
      destroyOnHidden
    >
      {channel ? (
        <Form
          form={form}
          layout="vertical"
          initialValues={{ name: channel.name, base_url: channel.base_url }}
          requiredMark={false}
        >
          <Form.Item name="name" label="名稱" rules={[{ required: true, message: '請輸入名稱' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="base_url" label="Base URL" rules={[{ required: true, message: '請輸入 Base URL' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="api_key" label="更換 API Key" extra="留空代表不修改">
            <Input.Password
              placeholder={channel.has_api_key ? `目前末 4 碼：${channel.api_key_last4}` : '尚未設定'}
              autoComplete="off"
            />
          </Form.Item>
        </Form>
      ) : null}
    </Modal>
  )
}

function ModelModal({
  target,
  onClose,
  onSaved,
}: {
  target: { channel: Channel; model?: ChannelModel } | null
  onClose: () => void
  onSaved: () => void
}) {
  const [form] = Form.useForm<{
    model_key: string
    display_name?: string
    capability: Capability
    input_price_per_m?: number | null
    output_price_per_m?: number | null
  }>()
  const [saving, setSaving] = useState(false)
  const { message } = App.useApp()
  const editing = target?.model

  const submit = async () => {
    if (!target) return
    const values = await form.validateFields()
    const prices = {
      input_price_per_m: values.input_price_per_m ?? null,
      output_price_per_m: values.output_price_per_m ?? null,
    }
    setSaving(true)
    try {
      if (editing) {
        await api.updateModel(editing.id, {
          display_name: values.display_name,
          capability: values.capability,
          ...prices,
        })
      } else {
        await api.addModel(target.channel.id, { ...values, ...prices })
      }
      message.success(editing ? '已更新' : '模型已新增')
      onSaved()
      onClose()
    } catch (error) {
      message.error(errorText(error))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      title={editing ? '編輯模型' : `新增模型到「${target?.channel.name ?? ''}」`}
      open={!!target}
      onCancel={onClose}
      onOk={submit}
      okText="儲存"
      confirmLoading={saving}
      destroyOnHidden
    >
      {target ? (
        <Form
          form={form}
          layout="vertical"
          requiredMark={false}
          initialValues={
            editing
              ? {
                  model_key: editing.model_key,
                  display_name: editing.display_name,
                  capability: editing.capability,
                  input_price_per_m: editing.input_price_per_m,
                  output_price_per_m: editing.output_price_per_m,
                }
              : { capability: 'text' }
          }
        >
          <Form.Item
            name="model_key"
            label="模型名稱（API 使用的 model 參數）"
            rules={[{ required: true, message: '請輸入模型名稱' }]}
          >
            <Input disabled={!!editing} placeholder="例如 deepseek-flash" className="mono" />
          </Form.Item>
          <Form.Item name="display_name" label="顯示名稱（選填）">
            <Input />
          </Form.Item>
          <Form.Item name="capability" label="用途">
            <Select
              options={(Object.keys(CAPABILITY_LABELS) as Capability[]).map((c) => ({
                value: c,
                label: CAPABILITY_LABELS[c],
              }))}
            />
          </Form.Item>
          <Space wrap>
            <Form.Item name="input_price_per_m" label="輸入價格（USD / 百萬 token）">
              <InputNumber min={0} step={0.01} placeholder="未知可留空" />
            </Form.Item>
            <Form.Item name="output_price_per_m" label="輸出價格（USD / 百萬 token）">
              <InputNumber min={0} step={0.01} placeholder="未知可留空" />
            </Form.Item>
          </Space>
          <Typography.Text type="secondary" className="small">
            價格只用來估算成本，請以服務商官網為準。留空時成本記錄會標示「未設定價格」。
          </Typography.Text>
        </Form>
      ) : null}
    </Modal>
  )
}
