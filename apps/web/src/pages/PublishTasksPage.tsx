import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, App, Button, Checkbox, DatePicker, Drawer, Form, Input, Popconfirm, Select, Space, Table, Tag, Typography } from 'antd'
import dayjs, { type Dayjs } from 'dayjs'
import { useState } from 'react'
import { api, PLATFORM_LABELS, type PostCopy, type PostItem } from '../api'
import { errorText } from '../api/http'
import PageHeader from '../components/PageHeader'

const STATUS: Record<string, { text: string; color: string }> = { queued: { text: '已排程', color: 'blue' }, submitting: { text: '傳送中', color: 'processing' }, processing: { text: '平台處理中', color: 'processing' }, published: { text: '已公開', color: 'green' }, failed: { text: '失敗', color: 'red' }, uncertain: { text: '回執待核對', color: 'orange' }, canceled: { text: '已取消', color: 'default' }, draft_delivery: { text: '草稿匣，需人工完成', color: 'orange' } }
type Draft = PostCopy & { video_id: string; account_id: string; schedule_at: Dayjs; confirmed: boolean; is_ai_generated: boolean }

export default function PublishTasksPage() {
  const { message } = App.useApp()
  const qc = useQueryClient()
  const [page, setPage] = useState(1)
  const [key, setKey] = useState<string | null>(null)
  const [opening, setOpening] = useState(false)
  const [form] = Form.useForm<Draft>()
  const accountId = Form.useWatch('account_id', form)
  const videoId = Form.useWatch('video_id', form)
  const list = useQuery({ queryKey: ['posts', page], queryFn: () => api.posts({ limit: 20, offset: (page - 1) * 20 }), refetchInterval: 15000 })
  const accounts = useQuery({ queryKey: ['social-accounts'], queryFn: api.socialAccounts })
  const videos = useQuery({ queryKey: ['videos', 'publish-ready'], queryFn: () => api.videos({ limit: 100, offset: 0, status: 'approved' }), enabled: !!key })
  const account = accounts.data?.find((a) => a.id === accountId)
  const refresh = () => { void qc.invalidateQueries({ queryKey: ['posts'] }); void qc.invalidateQueries({ queryKey: ['usage'] }) }
  const save = useMutation({ mutationFn: (v: Draft) => api.schedulePost({ ...v, request_key: key!, schedule_at: v.schedule_at.toISOString(), confirmed: true }), onSuccess: () => { message.success('已保存人工確認並排入發佈'); setKey(null); refresh() }, onError: (e) => message.error(errorText(e)) })
  const copy = useMutation({ mutationFn: () => api.postCopy(videoId, account!.platform), onSuccess: (data) => { form.setFieldsValue({ ...data, confirmed: false }); message.success('草稿已產生，請閱讀並確認') }, onError: (e) => message.error(errorText(e)) })
  const action = useMutation({ mutationFn: async ({ id, kind }: { id: string; kind: 'cancel' | 'reconcile' | 'comments' }) => { if (kind === 'cancel') await api.cancelPost(id); else if (kind === 'reconcile') await api.reconcilePost(id); else await api.syncPostComments(id) }, onSuccess: () => { refresh(); void qc.invalidateQueries({ queryKey: ['comments'] }); message.success('操作完成，請查看實際狀態') }, onError: (e) => { refresh(); message.error(errorText(e)) } })
  const open = async () => {
    setOpening(true)
    try { const data = await api.postRequestKey(); form.resetFields(); setKey(data.request_key) } catch (e) { message.error(errorText(e)) } finally { setOpening(false) }
  }
  return <>
    <PageHeader title="發佈任務" subtitle="只有人工通過的成片可以排程。平台處理中或回執不明時會持續核對原請求，避免重複發佈。" extra={<Button type="primary" loading={opening} onClick={() => { void open() }}>新增發佈</Button>} />
    <Alert type="info" showIcon title="時間以目前裝置的時區顯示。Upload-Post 單筆價格未提供時，成本帳本保留「未知」。" className="section" />
    {list.isError || accounts.isError ? <Alert type="error" title={errorText(list.error ?? accounts.error)} action={<Button onClick={() => { void list.refetch(); void accounts.refetch() }}>重試</Button>} /> : null}
    <Table<PostItem> rowKey="id" loading={list.isPending} dataSource={list.data?.items ?? []} scroll={{ x: 950 }} pagination={{ current: page, pageSize: 20, total: list.data?.total, showSizeChanger: false, onChange: setPage }} columns={[
      { title: '貼文', render: (_, p) => <Space orientation="vertical"><Typography.Text strong>{p.title}</Typography.Text><Typography.Text type="secondary">{PLATFORM_LABELS[p.platform]} · {p.remote_profile}</Typography.Text><Typography.Paragraph ellipsis={{ rows: 2, expandable: true }} style={{ maxWidth: 260, marginBottom: 0 }}>{p.description} {p.hashtags.join(' ')}</Typography.Paragraph></Space> },
      { title: '排程時間', dataIndex: 'schedule_at', render: (v: string) => dayjs(v).format('YYYY-MM-DD HH:mm') },
      { title: '狀態', render: (_, p) => <Space orientation="vertical"><Tag color={STATUS[p.status]?.color}>{STATUS[p.status]?.text ?? p.status}</Tag>{p.error ? <Typography.Text type="warning" style={{ maxWidth: 240 }}>{p.error}</Typography.Text> : null}{p.url ? <a href={p.url} target="_blank" rel="noopener noreferrer">開啟貼文</a> : null}</Space> },
      { title: '操作', render: (_, p) => <Space orientation="vertical">{p.status === 'queued' ? <Popconfirm title="取消尚未送出的排程？" onConfirm={() => action.mutate({ id: p.id, kind: 'cancel' })}><Button loading={action.isPending}>取消排程</Button></Popconfirm> : null}{['submitting', 'processing', 'uncertain'].includes(p.status) ? <Button loading={action.isPending} onClick={() => action.mutate({ id: p.id, kind: 'reconcile' })}>查詢原回執</Button> : null}{p.status === 'published' ? <><Button loading={action.isPending} onClick={() => action.mutate({ id: p.id, kind: 'comments' })}>同步評論</Button><Typography.Text type="secondary">{p.comments_checked_at ? dayjs(p.comments_checked_at).format('MM-DD HH:mm') : '尚未同步'}</Typography.Text>{p.comments_error ? <Typography.Text type="warning">{p.comments_error}</Typography.Text> : null}</> : null}</Space> },
    ]} />
    <Drawer open={!!key} title="確認成片與發佈內容" size={560} destroyOnHidden onClose={() => { if (!save.isPending) setKey(null) }}>
      <Form form={form} layout="vertical" initialValues={{ schedule_at: dayjs().add(10, 'minute'), hashtags: [], is_ai_generated: true, confirmed: false }} onValuesChange={(changed) => { if (!('confirmed' in changed)) form.setFieldValue('confirmed', false) }} onFinish={(v) => { if (v.confirmed) save.mutate(v) }}>
        {videos.isError ? <Alert type="error" title={errorText(videos.error)} action={<Button onClick={() => { void videos.refetch() }}>重試</Button>} /> : null}
        <Form.Item name="account_id" label="發佈帳號" rules={[{ required: true }]}><Select options={accounts.data?.filter((a) => a.enabled && a.auth_status === 'connected').map((a) => ({ value: a.id, label: `${PLATFORM_LABELS[a.platform]} · ${a.display_name || a.remote_profile}` }))} onChange={() => form.setFieldValue('video_id', undefined)} /></Form.Item>
        <Form.Item name="video_id" label="最近 100 支已通過的成片（同一帳號群）" rules={[{ required: true }]}><Select loading={videos.isFetching} options={videos.data?.items.filter((v) => v.video_url && v.profile_id === account?.profile_id).map((v) => ({ value: v.id, label: v.title }))} /></Form.Item>
        {videos.data?.items.find((v) => v.id === videoId)?.video_url ? <video controls playsInline preload="metadata" src={videos.data.items.find((v) => v.id === videoId)!.video_url!} style={{ width: '100%', maxHeight: 280, marginBottom: 16 }} /> : null}
        <Button className="section" disabled={!videoId || !account} loading={copy.isPending} onClick={() => copy.mutate()}>AI 產生此平台的貼文草稿</Button>
        <Form.Item name="title" label="標題" rules={[{ required: true, whitespace: true }]}><Input maxLength={100} showCount /></Form.Item>
        <Form.Item name="description" label="描述"><Input.TextArea maxLength={2000} showCount autoSize={{ minRows: 3, maxRows: 8 }} /></Form.Item>
        <Form.Item name="hashtags" label="Hashtag（#word，最多 10 個）"><Select mode="tags" open={false} tokenSeparators={[' ']} maxCount={10} /></Form.Item>
        <Form.Item name="schedule_at" label="發佈時間" rules={[{ required: true }]}><DatePicker showTime format="YYYY-MM-DD HH:mm" className="full-width" /></Form.Item>
        <Form.Item name="is_ai_generated" valuePropName="checked"><Checkbox>標示 AI 生成內容</Checkbox></Form.Item>
        <Form.Item name="confirmed" valuePropName="checked" rules={[{ validator: (_, v) => v === true ? Promise.resolve() : Promise.reject(new Error('請先預覽成片並確認所有發佈資料')) }]}><Checkbox>我已預覽成片，確認目的帳號、文字及時間，授權按此內容發佈</Checkbox></Form.Item>
        <Button type="primary" htmlType="submit" loading={save.isPending} disabled={copy.isPending}>確認並排程發佈</Button>
      </Form>
    </Drawer>
  </>
}
