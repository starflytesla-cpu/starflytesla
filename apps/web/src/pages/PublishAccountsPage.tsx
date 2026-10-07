import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, App, Button, Card, Checkbox, Drawer, Empty, Form, Select, Space, Switch, Tag, Typography } from 'antd'
import dayjs from 'dayjs'
import { useState } from 'react'
import { Link } from 'react-router'
import { api, PLATFORM_LABELS, type SocialPlatform } from '../api'
import { errorText } from '../api/http'
import PageHeader from '../components/PageHeader'

const AUTH_LABELS: Record<string, string> = {
  connected: '已授權',
  reauth_required: '授權過期，需重新綁定',
  disconnected: '已解除綁定',
  destination_changed: '目的帳號已更換，需核對',
  unknown: '待檢查',
}
type BindInput = {
  channel_id: string
  profile_id: string
  remote_profile: string
  platforms: SocialPlatform[]
}

export default function PublishAccountsPage() {
  const { message } = App.useApp()
  const qc = useQueryClient()
  const [open, setOpen] = useState(false)
  const [form] = Form.useForm<BindInput>()
  const channelId = Form.useWatch('channel_id', form)
  const remoteName = Form.useWatch('remote_profile', form)
  const list = useQuery({
    queryKey: ['social-accounts'],
    queryFn: api.socialAccounts,
  })
  const channels = useQuery({
    queryKey: ['publish-channels'],
    queryFn: api.publishChannels,
  })
  const profiles = useQuery({ queryKey: ['profiles'], queryFn: api.profiles })
  const remote = useQuery({
    queryKey: ['remote-profiles', channelId],
    queryFn: () => api.remoteProfiles(channelId),
    enabled: open && !!channelId,
    retry: false,
  })
  const selected = remote.data?.find((p) => p.username === remoteName)
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ['social-accounts'] })
  }
  const bind = useMutation({
    mutationFn: api.bindSocialAccounts,
    onSuccess: () => {
      message.success('帳號已綁定')
      setOpen(false)
      refresh()
    },
    onError: (e) => message.error(errorText(e)),
  })
  const toggle = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) => api.updateSocialAccount(id, enabled),
    onSuccess: refresh,
    onError: (e) => message.error(errorText(e)),
  })
  const check = useMutation({
    mutationFn: api.checkSocialAccount,
    onSuccess: (row) => {
      refresh()
      message.info(AUTH_LABELS[row.auth_status] ?? row.auth_status)
    },
    onError: (e) => message.error(errorText(e)),
  })
  const auto = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) => api.setAutoSuggestions(id, enabled),
    onSuccess: refresh,
    onError: (e) => message.error(errorText(e)),
  })
  return (
    <>
      <PageHeader
        title="發佈帳號"
        subtitle="在 Upload-Post 綁定社媒，再將目的帳號對應到帳號檔案。發佈前會再次檢查授權與帳號識別碼。"
        extra={
          <Button
            type="primary"
            onClick={() => {
              form.resetFields()
              setOpen(true)
            }}
          >
            綁定帳號
          </Button>
        }
      />
      <Alert
        type="info"
        showIcon
        className="section"
        title={
          <span>
            先到 <Link to="/settings/publish-channels">發佈渠道</Link>填入 API Key，再到{' '}
            <a href="https://app.upload-post.com/manage-users" target="_blank" rel="noopener noreferrer">
              Upload-Post 綁定社媒帳號
            </a>
            。Facebook 請確認已選定目的 Page。
          </span>
        }
      />
      {list.isError || channels.isError || profiles.isError ? (
        <Alert
          type="error"
          showIcon
          title="無法讀取帳號設定"
          description={errorText(list.error ?? channels.error ?? profiles.error)}
          action={
            <Button
              onClick={() => {
                void list.refetch()
                void channels.refetch()
                void profiles.refetch()
              }}
            >
              重試
            </Button>
          }
        />
      ) : null}
      <div className="account-grid">
        {list.data?.map((a) => (
          <Card
            key={a.id}
            title={
              <Space wrap>
                <span>{a.display_name || a.handle || a.remote_profile}</span>
                <Tag>{PLATFORM_LABELS[a.platform]}</Tag>
              </Space>
            }
            extra={
              <Switch
                aria-label={`啟用 ${a.display_name || a.remote_profile}`}
                checked={a.enabled}
                loading={toggle.isPending}
                onChange={(enabled) => toggle.mutate({ id: a.id, enabled })}
              />
            }
          >
            <Space orientation="vertical">
              <Typography.Text>
                帳號群：
                {profiles.data
                  ? (profiles.data.items.find((p) => p.id === a.profile_id)?.name ?? '原帳號檔案已刪除')
                  : '帳號檔案尚未載入'}
              </Typography.Text>
              <Typography.Text>
                Upload-Post profile：{a.remote_profile} · {a.handle || a.external_account_id}
              </Typography.Text>
              <Space wrap>
                <Tag color={a.auth_status === 'connected' ? 'green' : 'orange'}>
                  {AUTH_LABELS[a.auth_status] ?? a.auth_status}
                </Tag>
                <Typography.Text type="secondary">
                  上次檢查：
                  {a.checked_at ? dayjs(a.checked_at).format('YYYY-MM-DD HH:mm') : '尚未檢查'}
                </Typography.Text>
                <Button loading={check.isPending && check.variables === a.id} onClick={() => check.mutate(a.id)}>
                  檢查授權
                </Button>
              </Space>
              {a.platform === 'tiktok' && !a.capabilities.includes('comments') ? (
                <Typography.Text type="warning">此 TikTok 連線尚無評論權限，請重新綁定以取得權限。</Typography.Text>
              ) : null}
              <Space wrap>
                <Checkbox
                  checked={a.auto_suggest_enabled}
                  disabled={auto.isPending}
                  onChange={(e) => auto.mutate({ id: a.id, enabled: e.target.checked })}
                >
                  自動分類新評論並產生 AI 建議（會計入模型費用）
                </Checkbox>
                <Typography.Text type="secondary">回覆仍需逐則人工確認；預設關閉。</Typography.Text>
              </Space>
            </Space>
          </Card>
        ))}
        {!list.isPending && !list.isError && list.data?.length === 0 ? <Empty description="尚未綁定發佈帳號" /> : null}
      </div>
      <Drawer open={open} title="綁定 Upload-Post 帳號" onClose={() => setOpen(false)} size={480} destroyOnHidden>
        <Form form={form} layout="vertical" onFinish={(v) => bind.mutate(v)}>
          <Typography.Title level={5}>1. 選擇渠道與品牌</Typography.Title>
          <Form.Item name="channel_id" label="發佈渠道" rules={[{ required: true }]}>
            <Select
              placeholder="選擇已設定 Key 的渠道"
              options={channels.data
                ?.filter((c) => c.enabled && c.has_api_key)
                .map((c) => ({ value: c.id, label: c.name }))}
              onChange={() =>
                form.setFieldsValue({
                  remote_profile: undefined,
                  platforms: [],
                })
              }
            />
          </Form.Item>
          {remote.isError ? (
            <Alert
              type="error"
              title={errorText(remote.error)}
              action={
                <Button
                  onClick={() => {
                    void remote.refetch()
                  }}
                >
                  重試
                </Button>
              }
              className="section"
            />
          ) : null}
          <Form.Item name="profile_id" label="平台內的帳號檔案 / 帳號群" rules={[{ required: true }]}>
            <Select
              options={profiles.data?.items.map((p) => ({
                value: p.id,
                label: p.name,
              }))}
            />
          </Form.Item>
          <Typography.Title level={5}>2. 核對社媒目的帳號</Typography.Title>
          <Form.Item name="remote_profile" label="Upload-Post profile" rules={[{ required: true }]}>
            <Select
              loading={remote.isFetching}
              options={remote.data?.map((p) => ({
                value: p.username,
                label: p.username,
              }))}
              onChange={() => form.setFieldValue('platforms', [])}
            />
          </Form.Item>
          <Form.Item name="platforms" label="目的平台" rules={[{ required: true, message: '請選擇已授權的平台' }]}>
            <Checkbox.Group
              options={Object.entries(selected?.accounts ?? {}).map(([value, a]) => ({
                value,
                label: `${PLATFORM_LABELS[value as SocialPlatform]} · ${a.display_name || a.handle || a.external_account_id}`,
                disabled: a.auth_status !== 'connected',
              }))}
            />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={bind.isPending} disabled={!selected}>
            確認綁定
          </Button>
        </Form>
      </Drawer>
    </>
  )
}
