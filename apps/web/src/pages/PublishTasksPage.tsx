import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert,
  App,
  Button,
  Card,
  Checkbox,
  DatePicker,
  Drawer,
  Form,
  Grid,
  Input,
  Pagination,
  Popconfirm,
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd'
import dayjs, { type Dayjs } from 'dayjs'
import { useState } from 'react'
import { api, PLATFORM_LABELS, type PostCopy, type PostItem } from '../api'
import { errorText } from '../api/http'
import PageHeader from '../components/PageHeader'

const STATUS: Record<string, { text: string; color: string }> = {
  queued: { text: '已排程', color: 'blue' },
  submitting: { text: '傳送中', color: 'processing' },
  processing: { text: '平台處理中', color: 'processing' },
  published: { text: '已公開', color: 'green' },
  failed: { text: '失敗', color: 'red' },
  uncertain: { text: '回執待核對', color: 'orange' },
  canceled: { text: '已取消', color: 'default' },
  draft_delivery: { text: '草稿匣，需人工完成', color: 'orange' },
}
type Draft = PostCopy & {
  video_id: string
  account_id: string
  schedule_at: Dayjs
  confirmed: boolean
  is_ai_generated: boolean
}

export default function PublishTasksPage() {
  const { message } = App.useApp()
  const qc = useQueryClient()
  const screens = Grid.useBreakpoint()
  const [detailId, setDetailId] = useState<string | null>(null)
  const [page, setPage] = useState(1)
  const [key, setKey] = useState<string | null>(null)
  const [opening, setOpening] = useState(false)
  const [form] = Form.useForm<Draft>()
  const accountId = Form.useWatch('account_id', form)
  const videoId = Form.useWatch('video_id', form)
  const confirmed = Form.useWatch('confirmed', form)
  const list = useQuery({
    queryKey: ['posts', page],
    queryFn: () => api.posts({ limit: 20, offset: (page - 1) * 20 }),
    refetchInterval: 15000,
  })
  const accounts = useQuery({
    queryKey: ['social-accounts'],
    queryFn: api.socialAccounts,
  })
  const videos = useQuery({
    queryKey: ['videos', 'publish-ready'],
    queryFn: () => api.videos({ limit: 100, offset: 0, status: 'approved' }),
    enabled: !!key,
  })
  const account = accounts.data?.find((a) => a.id === accountId)
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ['posts'] })
    void qc.invalidateQueries({ queryKey: ['usage'] })
  }
  const save = useMutation({
    mutationFn: (v: Draft) =>
      api.schedulePost({
        ...v,
        request_key: key!,
        schedule_at: v.schedule_at.toISOString(),
        confirmed: true,
      }),
    onSuccess: () => {
      message.success('已保存人工確認並排入發佈')
      setKey(null)
      refresh()
    },
    onError: (e) => message.error(errorText(e)),
  })
  const copy = useMutation({
    mutationFn: () => api.postCopy(videoId, account!.platform),
    onSuccess: (data) => {
      form.setFieldsValue({ ...data, confirmed: false })
      message.success('草稿已產生，請閱讀並確認')
    },
    onError: (e) => message.error(errorText(e)),
  })
  const action = useMutation({
    mutationFn: async ({ id, kind }: { id: string; kind: 'cancel' | 'reconcile' | 'comments' }) => {
      if (kind === 'cancel') await api.cancelPost(id)
      else if (kind === 'reconcile') await api.reconcilePost(id)
      else await api.syncPostComments(id)
    },
    onSuccess: () => {
      refresh()
      void qc.invalidateQueries({ queryKey: ['comments'] })
      message.success('操作完成，請查看實際狀態')
    },
    onError: (e) => {
      refresh()
      message.error(errorText(e))
    },
  })
  const detail = list.data?.items.find((p) => p.id === detailId)
  const selectedVideo = videos.data?.items.find((v) => v.id === videoId)
  const scheduleAt = Form.useWatch('schedule_at', form)
  const postActions = (p: PostItem) => (
    <Space wrap>
      {p.status === 'queued' ? (
        <Popconfirm title="取消尚未送出的排程？" onConfirm={() => action.mutate({ id: p.id, kind: 'cancel' })}>
          <Button loading={action.isPending}>取消排程</Button>
        </Popconfirm>
      ) : null}
      {['submitting', 'processing', 'uncertain'].includes(p.status) ? (
        <Button loading={action.isPending} onClick={() => action.mutate({ id: p.id, kind: 'reconcile' })}>
          查詢原回執
        </Button>
      ) : null}
      {p.status === 'published' ? (
        <Button loading={action.isPending} onClick={() => action.mutate({ id: p.id, kind: 'comments' })}>
          同步評論
        </Button>
      ) : null}
      {p.url ? (
        <Button href={p.url} target="_blank" rel="noopener noreferrer">
          開啟貼文
        </Button>
      ) : null}
    </Space>
  )
  const open = async () => {
    setOpening(true)
    try {
      const data = await api.postRequestKey()
      form.resetFields()
      setKey(data.request_key)
    } catch (e) {
      message.error(errorText(e))
    } finally {
      setOpening(false)
    }
  }
  return (
    <>
      <PageHeader
        title="發佈任務"
        subtitle="只有人工通過的成片可以排程。平台處理中或回執不明時會持續核對原請求，避免重複發佈。"
        extra={
          <Button
            type="primary"
            loading={opening}
            onClick={() => {
              void open()
            }}
          >
            新增發佈
          </Button>
        }
      />
      <Alert
        type="info"
        showIcon
        title="時間以目前裝置的時區顯示。Upload-Post 單筆價格未提供時，成本帳本保留「未知」。"
        className="section"
      />
      {list.isError || accounts.isError ? (
        <Alert
          type="error"
          title={errorText(list.error ?? accounts.error)}
          action={
            <Button
              onClick={() => {
                void list.refetch()
                void accounts.refetch()
              }}
            >
              重試
            </Button>
          }
        />
      ) : null}
      <Card title="發佈記錄" extra={<span className="small muted">全部歷史 · 裝置時區</span>}>
        {screens.md ? (
          <Table<PostItem>
            rowKey="id"
            loading={list.isPending}
            dataSource={list.data?.items ?? []}
            scroll={{ x: 740 }}
            pagination={{
              current: page,
              pageSize: 20,
              total: list.data?.total,
              showSizeChanger: false,
              onChange: setPage,
            }}
            columns={[
              {
                title: '貼文 / 目的帳號',
                render: (_, p) => (
                  <>
                    <Typography.Text strong>{p.title}</Typography.Text>
                    <div className="small muted">
                      {PLATFORM_LABELS[p.platform]} · {p.remote_profile}
                    </div>
                  </>
                ),
              },
              {
                title: '排程時間',
                dataIndex: 'schedule_at',
                render: (v: string) => dayjs(v).format('YYYY-MM-DD HH:mm'),
              },
              {
                title: '狀態',
                render: (_, p) => (
                  <>
                    <Tag color={STATUS[p.status]?.color}>{STATUS[p.status]?.text ?? p.status}</Tag>
                    {p.error ? (
                      <Typography.Paragraph type="warning" ellipsis={{ rows: 2 }} style={{ maxWidth: 240, margin: 0 }}>
                        {p.error}
                      </Typography.Paragraph>
                    ) : null}
                  </>
                ),
              },
              {
                title: '操作',
                render: (_, p) => <Button onClick={() => setDetailId(p.id)}>查看詳情</Button>,
              },
            ]}
          />
        ) : (
          <>
            <div className="record-list">
              {list.data?.items.map((p) => (
                <button className="compact-record record-button" key={p.id} onClick={() => setDetailId(p.id)}>
                  <Tag color={STATUS[p.status]?.color}>{STATUS[p.status]?.text ?? p.status}</Tag>
                  <strong>{p.title}</strong>
                  <span className="small muted">
                    {PLATFORM_LABELS[p.platform]} · {p.remote_profile}
                  </span>
                  <span>{dayjs(p.schedule_at).format('YYYY-MM-DD HH:mm')}</span>
                  <span className="small">查看內容與回執 →</span>
                </button>
              ))}
            </div>
            {!list.isPending && !list.isError && !list.data?.items.length ? (
              <p className="muted">尚無發佈記錄</p>
            ) : null}
            <Pagination
              className="asset-pagination"
              current={page}
              pageSize={20}
              total={list.data?.total}
              showSizeChanger={false}
              onChange={setPage}
            />
          </>
        )}
      </Card>
      <Drawer
        open={!!detail}
        title="發佈詳情與回執"
        size={screens.md ? 620 : '100%'}
        onClose={() => setDetailId(null)}
        footer={detail ? postActions(detail) : null}
      >
        {detail ? (
          <>
            <Tag color={STATUS[detail.status]?.color}>{STATUS[detail.status]?.text ?? detail.status}</Tag>
            <Typography.Title level={4}>{detail.title}</Typography.Title>
            <p>
              {PLATFORM_LABELS[detail.platform]} · {detail.remote_profile}
            </p>
            <p className="muted">
              排程：{dayjs(detail.schedule_at).format('YYYY-MM-DD HH:mm')}
              （裝置時區）
            </p>
            <Typography.Title level={5}>人工確認的內容</Typography.Title>
            <Typography.Paragraph className="comment-original">{detail.description}</Typography.Paragraph>
            <p>{detail.hashtags.join(' ')}</p>
            {detail.error ? (
              <Alert
                type="warning"
                className="section"
                showIcon
                title="錯誤 / 回執資訊"
                description={
                  <Typography.Paragraph copyable className="error-body">
                    {detail.error}
                  </Typography.Paragraph>
                }
              />
            ) : null}
            {detail.status === 'draft_delivery' ? (
              <Alert type="warning" title="影片已送至草稿匣，請到原平台完成發佈" />
            ) : null}
            <p className="muted">
              評論同步：
              {detail.comments_checked_at ? dayjs(detail.comments_checked_at).format('YYYY-MM-DD HH:mm') : '尚未同步'}
            </p>
            {detail.comments_error ? <Alert type="warning" title={detail.comments_error} /> : null}
            <p className="mono small break-word">
              ID：{detail.id}
              <br />
              平台回執：{detail.remote_id || '尚未取得'}
            </p>
          </>
        ) : null}
      </Drawer>
      <Drawer
        open={!!key}
        title="確認成片與發佈內容"
        size={screens.md ? 720 : '100%'}
        destroyOnHidden
        onClose={() => {
          if (!save.isPending) setKey(null)
        }}
      >
        <Form
          form={form}
          layout="vertical"
          initialValues={{
            schedule_at: dayjs().add(10, 'minute'),
            hashtags: [],
            is_ai_generated: true,
            confirmed: false,
          }}
          onValuesChange={(changed) => {
            if (!('confirmed' in changed)) form.setFieldValue('confirmed', false)
          }}
          onFinish={(v) => {
            if (v.confirmed) save.mutate(v)
          }}
        >
          {videos.isError ? (
            <Alert
              type="error"
              title={errorText(videos.error)}
              action={
                <Button
                  onClick={() => {
                    void videos.refetch()
                  }}
                >
                  重試
                </Button>
              }
            />
          ) : null}
          <Typography.Title level={5}>1. 目的帳號與成片</Typography.Title>
          <Form.Item name="account_id" label="發佈帳號" rules={[{ required: true }]}>
            <Select
              options={accounts.data
                ?.filter((a) => a.enabled && a.auth_status === 'connected')
                .map((a) => ({
                  value: a.id,
                  label: `${PLATFORM_LABELS[a.platform]} · ${a.display_name || a.remote_profile}`,
                }))}
              onChange={() => form.setFieldValue('video_id', undefined)}
            />
          </Form.Item>
          <Form.Item name="video_id" label="最近 100 支已通過的成片（同一帳號群）" rules={[{ required: true }]}>
            <Select
              loading={videos.isFetching}
              options={videos.data?.items
                .filter((v) => v.video_url && v.profile_id === account?.profile_id)
                .map((v) => ({ value: v.id, label: v.title }))}
            />
          </Form.Item>
          {videos.data?.items.find((v) => v.id === videoId)?.video_url ? (
            <video
              controls
              playsInline
              preload="metadata"
              src={videos.data.items.find((v) => v.id === videoId)!.video_url!}
              style={{ width: '100%', maxHeight: 280, marginBottom: 16 }}
            />
          ) : null}
          <Button
            className="section"
            disabled={!videoId || !account}
            loading={copy.isPending}
            onClick={() => copy.mutate()}
          >
            AI 產生此平台的貼文草稿（計費）
          </Button>
          <Typography.Title level={5}>2. 平台文字</Typography.Title>
          <Form.Item name="title" label="標題" rules={[{ required: true, whitespace: true }]}>
            <Input maxLength={100} showCount />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea maxLength={2000} showCount autoSize={{ minRows: 3, maxRows: 8 }} />
          </Form.Item>
          <Form.Item name="hashtags" label="Hashtag（#word，最多 10 個）">
            <Select mode="tags" open={false} tokenSeparators={[' ']} maxCount={10} />
          </Form.Item>
          <Typography.Title level={5}>3. 時間與人工確認</Typography.Title>
          <Form.Item name="schedule_at" label="發佈時間" rules={[{ required: true }]}>
            <DatePicker showTime format="YYYY-MM-DD HH:mm" className="full-width" />
          </Form.Item>
          <Form.Item name="is_ai_generated" valuePropName="checked">
            <Checkbox>標示 AI 生成內容</Checkbox>
          </Form.Item>
          <div className="publish-summary">
            <strong>本次發佈摘要</strong>
            <p>
              {account
                ? `${PLATFORM_LABELS[account.platform]} · ${account.display_name || account.remote_profile}`
                : '尚未選擇帳號'}
            </p>
            <p>成片：{selectedVideo?.title ?? '尚未選擇'}</p>
            <p>
              時間：
              {scheduleAt ? scheduleAt.format('YYYY-MM-DD HH:mm') : '尚未設定'}
              （裝置時區）
            </p>
          </div>
          {save.error || copy.error ? (
            <Alert className="section" type="error" showIcon title={errorText(save.error || copy.error)} />
          ) : null}
          <Form.Item
            name="confirmed"
            valuePropName="checked"
            rules={[
              {
                validator: (_, v) =>
                  v === true ? Promise.resolve() : Promise.reject(new Error('請先預覽成片並確認所有發佈資料')),
              },
            ]}
          >
            <Checkbox>我已預覽成片，確認目的帳號、文字及時間，授權按此內容發佈</Checkbox>
          </Form.Item>
          <Button
            block
            size="large"
            type="primary"
            htmlType="submit"
            loading={save.isPending}
            disabled={copy.isPending || !confirmed || accounts.isError || videos.isError}
          >
            確認並排程發佈
          </Button>
        </Form>
      </Drawer>
    </>
  )
}
