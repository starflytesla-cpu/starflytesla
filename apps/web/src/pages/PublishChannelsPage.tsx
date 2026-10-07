import { EditOutlined, ExperimentOutlined, PlusOutlined } from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert,
  App,
  Button,
  Card,
  Collapse,
  Descriptions,
  Empty,
  Form,
  Input,
  Modal,
  Popconfirm,
  Space,
  Switch,
  Tag,
  Typography,
} from 'antd'
import { useState } from 'react'
import { api, type PublishChannel, type PublishChannelInput } from '../api'
import { ApiError } from '../api/http'
import PageHeader from '../components/PageHeader'

function errorText(error: unknown) {
  return error instanceof ApiError ? error.message : '操作失敗，請稍後再試'
}

const CHECK_LABELS = {
  untested: '尚未檢查',
  succeeded: '檢查通過',
  failed: '檢查失敗',
}

export default function PublishChannelsPage() {
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const channels = useQuery({
    queryKey: ['publish-channels'],
    queryFn: api.publishChannels,
  })
  const [editing, setEditing] = useState<PublishChannel | 'new' | null>(null)
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ['publish-channels'] })
    void queryClient.invalidateQueries({ queryKey: ['usage'] })
    void queryClient.invalidateQueries({ queryKey: ['dashboard'] })
  }
  const update = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Partial<PublishChannelInput> }) =>
      api.updatePublishChannel(id, body),
    onSuccess: () => {
      message.success('已更新')
      refresh()
    },
    onError: (e) => message.error(errorText(e)),
  })
  const test = useMutation({
    mutationFn: api.testPublishChannel,
    onSuccess: (result) => message.success(`連線檢查通過，方案：${result.plan}`),
    onError: (e) => message.error(errorText(e), 6),
    onSettled: refresh,
  })

  return (
    <>
      <PageHeader
        title="發佈渠道"
        subtitle="設定 Upload-Post API Key。金鑰加密保存；連線檢查只查詢帳號方案，不會發佈內容。"
        extra={
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setEditing('new')}>
            新增渠道
          </Button>
        }
      />
      <Alert
        className="section"
        type="info"
        showIcon
        title="尚未準備帳號時，可以先儲存渠道，之後再填入 API Key。"
        description="到 Upload-Post 註冊並建立 API Key，再回到此頁設定。成片與回覆仍需人工確認後才可發出。"
      />
      {channels.isError ? (
        <Alert
          type="error"
          showIcon
          title={errorText(channels.error)}
          action={<Button onClick={() => channels.refetch()}>重試</Button>}
        />
      ) : null}
      {channels.isPending ? <Card loading /> : null}
      {channels.data?.length === 0 ? (
        <Card>
          <Empty description="尚未設定發佈渠道">
            <Button onClick={() => setEditing('new')}>新增 Upload-Post 渠道</Button>
          </Empty>
        </Card>
      ) : null}
      <Space orientation="vertical" size={16} className="full-width">
        {channels.data?.map((channel) => (
          <Card
            key={channel.id}
            title={
              <Space wrap>
                <span>{channel.name}</span>
                <Tag>Upload-Post</Tag>
                <Tag
                  color={
                    channel.check_status === 'succeeded'
                      ? 'green'
                      : channel.check_status === 'failed'
                        ? 'red'
                        : 'default'
                  }
                >
                  {CHECK_LABELS[channel.check_status]}
                </Tag>
              </Space>
            }
          >
            <p className="small muted">
              {channel.enabled ? '已啟用' : '已停用'} · {channel.has_api_key ? '金鑰已設定' : '待設定金鑰'} ·{' '}
              {channel.plan || '方案未確認'}
            </p>
            <Collapse
              className="section"
              items={[
                {
                  key: 'details',
                  label: '連線與金鑰詳情',
                  children: (
                    <Descriptions
                      size="small"
                      column={1}
                      items={[
                        {
                          key: 'url',
                          label: 'Base URL',
                          children: (
                            <Typography.Text style={{ overflowWrap: 'anywhere' }}>{channel.base_url}</Typography.Text>
                          ),
                        },
                        {
                          key: 'key',
                          label: 'API Key',
                          children: channel.has_api_key ? `已設定（末 4 碼：${channel.api_key_last4}）` : '尚未設定',
                        },
                        {
                          key: 'plan',
                          label: '方案',
                          children: channel.plan || '尚未確認',
                        },
                        {
                          key: 'time',
                          label: '上次檢查',
                          children: channel.checked_at ? new Date(channel.checked_at).toLocaleString() : '尚未檢查',
                        },
                      ]}
                    />
                  ),
                },
              ]}
            />
            {channel.check_error ? (
              <Alert className="section" type="error" showIcon title={channel.check_error} />
            ) : null}
            <Space wrap className="section">
              <Switch
                checked={channel.enabled}
                checkedChildren="已啟用"
                unCheckedChildren="已停用"
                loading={update.isPending && update.variables?.id === channel.id}
                aria-label={`啟用 ${channel.name}`}
                onChange={(enabled) => update.mutate({ id: channel.id, body: { enabled } })}
              />
              <Button icon={<EditOutlined />} onClick={() => setEditing(channel)}>
                編輯
              </Button>
              <Button
                icon={<ExperimentOutlined />}
                disabled={!channel.enabled || !channel.has_api_key || test.isPending}
                loading={test.isPending && test.variables === channel.id}
                onClick={() => test.mutate(channel.id)}
              >
                檢查連線
              </Button>
              {channel.has_api_key ? (
                <Popconfirm
                  title="清除這個渠道的 API Key？"
                  description="清除後需要重新填入才能使用。"
                  onConfirm={() =>
                    update.mutateAsync({
                      id: channel.id,
                      body: { clear_api_key: true },
                    })
                  }
                >
                  <Button danger disabled={update.isPending}>
                    清除金鑰
                  </Button>
                </Popconfirm>
              ) : null}
            </Space>
          </Card>
        ))}
      </Space>
      {editing !== null ? (
        <ChannelForm
          key={editing === 'new' ? 'new' : editing.id}
          channel={editing === 'new' ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null)
            refresh()
          }}
        />
      ) : null}
    </>
  )
}

function ChannelForm({
  channel,
  onClose,
  onSaved,
}: {
  channel: PublishChannel | null
  onClose: () => void
  onSaved: () => void
}) {
  const { message } = App.useApp()
  const [form] = Form.useForm<PublishChannelInput>()
  const save = useMutation({
    mutationFn: (values: PublishChannelInput) =>
      channel ? api.updatePublishChannel(channel.id, values) : api.createPublishChannel(values),
    onSuccess: () => {
      form.resetFields()
      message.success('發佈渠道已儲存')
      onSaved()
    },
    onError: (e) => message.error(errorText(e)),
  })
  return (
    <Modal
      open
      title={channel ? '編輯發佈渠道' : '新增發佈渠道'}
      onCancel={onClose}
      okText="儲存"
      confirmLoading={save.isPending}
      onOk={() => form.submit()}
    >
      <Form
        form={form}
        layout="vertical"
        requiredMark={false}
        initialValues={{
          name: channel?.name ?? 'Upload-Post',
          base_url: channel?.base_url ?? 'https://api.upload-post.com/api',
        }}
        onFinish={(values) =>
          save.mutate({
            ...values,
            name: values.name.trim(),
            base_url: values.base_url.trim(),
            api_key: values.api_key?.trim() || undefined,
          })
        }
      >
        <Form.Item
          name="name"
          label="名稱"
          rules={[
            {
              required: true,
              whitespace: true,
              max: 80,
              message: '請輸入渠道名稱（最多 80 字）',
            },
          ]}
        >
          <Input maxLength={80} />
        </Form.Item>
        <Form.Item
          name="base_url"
          label="Base URL"
          rules={[{ required: true, type: 'url', message: '請輸入有效網址' }]}
          extra="一般使用預設網址，不需要修改。"
        >
          <Input maxLength={500} />
        </Form.Item>
        <Form.Item
          name="api_key"
          label={channel ? '更換 API Key' : 'API Key（可稍後設定）'}
          extra={channel ? '留空代表保留目前金鑰。' : '金鑰只填在這裡，不要貼到 Linear、GitHub 或聊天。'}
        >
          <Input.Password
            autoComplete="new-password"
            maxLength={500}
            placeholder={channel?.has_api_key ? `目前末 4 碼：${channel.api_key_last4}` : '貼上 Upload-Post API Key'}
          />
        </Form.Item>
      </Form>
    </Modal>
  )
}
