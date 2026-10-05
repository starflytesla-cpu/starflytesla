import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, App, Button, Card, Checkbox, Empty, Input, Modal, Pagination, Space, Switch, Tag, Typography } from 'antd'
import dayjs from 'dayjs'
import { useState } from 'react'
import { Link } from 'react-router'
import { api, type SocialComment } from '../api'
import { errorText } from '../api/http'
import PageHeader from '../components/PageHeader'

const INTENT: Record<string, string> = { unknown: '未分類', enquiry: '詢價', positive: '好評', complaint: '投訴 / 負面', spam: '垃圾', question: '問題' }
const REPLY: Record<string, string> = { unreplied: '未回覆', failed: '送出失敗', sending: '請求已送出，待回執', uncertain: '回執待核對，禁止重送', replied: '已回覆' }

export default function CommentsPage() {
  const { message } = App.useApp()
  const qc = useQueryClient()
  const [page, setPage] = useState(1)
  const [unreplied, setUnreplied] = useState(false)
  const [negative, setNegative] = useState(false)
  const [target, setTarget] = useState<SocialComment | null>(null)
  const [text, setText] = useState('')
  const [confirmed, setConfirmed] = useState(false)
  const list = useQuery({ queryKey: ['comments', page, unreplied, negative], queryFn: () => api.comments({ limit: 20, offset: (page - 1) * 20, unreplied, negative }) })
  const refresh = () => { void qc.invalidateQueries({ queryKey: ['comments'] }); void qc.invalidateQueries({ queryKey: ['usage'] }) }
  const suggest = useMutation({ mutationFn: api.suggestComment, onSuccess: () => { refresh(); message.success('AI 建議已保存，尚未送出') }, onError: (e) => message.error(errorText(e)) })
  const reply = useMutation({ mutationFn: () => api.replyComment(target!.id, text, target!.version), onSuccess: () => { refresh(); setTarget(null); message.success('已取得平台回覆回執') }, onError: (e) => { refresh(); message.error(errorText(e)); setTarget(null) } })
  return <>
    <PageHeader title="評論收件匣" subtitle="近期貼文每 10 分鐘同步。AI 只產生建議；每則回覆需閱讀原評論、修改內容並人工確認。" extra={<Button onClick={() => { void list.refetch() }}>重新整理</Button>} />
    <Alert type="info" showIcon className="section" title={<span>可到<Link to="/publish-tasks">發佈任務</Link>手動同步評論。TikTok 需重新綁定以取得評論權限；回執不明時請先到原平台核對。</span>} />
    <Space wrap className="section"><Switch checked={unreplied} onChange={(v) => { setUnreplied(v); setPage(1) }} aria-label="只看未回覆" /><span>只看未回覆</span><Switch checked={negative} onChange={(v) => { setNegative(v); setPage(1) }} aria-label="只看負面評論" /><span>只看負面評論（經 AI 分類）</span></Space>
    {list.isError ? <Alert type="error" title={errorText(list.error)} action={<Button onClick={() => { void list.refetch() }}>重試</Button>} /> : null}
    <Space orientation="vertical" size="middle" className="full-width">
      {list.data?.items.map((c) => <Card key={c.id} title={<Space wrap><span>{c.author || '匿名評論者'}</span><Tag color={c.intent === 'complaint' ? 'orange' : c.intent === 'enquiry' ? 'blue' : 'default'}>{INTENT[c.intent] ?? c.intent}</Tag><Tag color={c.reply_status === 'replied' ? 'green' : ['uncertain', 'sending', 'failed'].includes(c.reply_status) ? 'orange' : 'default'}>{REPLY[c.reply_status] ?? c.reply_status}</Tag></Space>}>
        <Typography.Paragraph style={{ whiteSpace: 'pre-wrap' }}>{c.text}</Typography.Paragraph>
        <Typography.Text type="secondary">同步於 {dayjs(c.created_at).format('YYYY-MM-DD HH:mm')}</Typography.Text>
        {c.suggested_reply ? <Alert type="info" title="AI 建議（尚未送出）" description={c.suggested_reply} style={{ marginTop: 12 }} /> : null}
        {['pending', 'generating'].includes(c.ai_status) ? <Typography.Paragraph type="secondary">AI 建議產生中，請稍後重新整理。</Typography.Paragraph> : null}
        {c.ai_error ? <Alert type="warning" title={c.ai_error} style={{ marginTop: 12 }} /> : null}
        {c.reply_text ? <Typography.Paragraph style={{ marginTop: 12, whiteSpace: 'pre-wrap' }}>人工確認的回覆：{c.reply_text}</Typography.Paragraph> : null}
        {c.error ? <Alert type="warning" title={c.error} style={{ marginTop: 12 }} /> : null}
        {['unreplied', 'failed'].includes(c.reply_status) ? <Space wrap style={{ marginTop: 12 }}><Button disabled={['pending', 'generating', 'uncertain'].includes(c.ai_status)} loading={suggest.isPending && suggest.variables === c.id} onClick={() => suggest.mutate(c.id)}>AI 分類與建議回覆</Button><Button type="primary" onClick={() => { setTarget(c); setText(c.suggested_reply); setConfirmed(false) }}>編輯並確認回覆</Button></Space> : null}
      </Card>)}
      {!list.isPending && !list.isError && list.data?.items.length === 0 ? <Empty description="目前沒有符合條件的評論" /> : null}
      <Pagination current={page} pageSize={20} total={list.data?.total ?? 0} showSizeChanger={false} onChange={setPage} />
    </Space>
    <Modal open={!!target} title="確認公開回覆" onCancel={() => { if (!reply.isPending) setTarget(null) }} onOk={() => { if (confirmed && text.trim()) reply.mutate() }} okText="確認並送出公開回覆" confirmLoading={reply.isPending} okButtonProps={{ disabled: !confirmed || !text.trim() }}>
      <Typography.Paragraph style={{ whiteSpace: 'pre-wrap' }}>原評論：{target?.text}</Typography.Paragraph>
      <label htmlFor="comment-reply">公開回覆內容</label>
      <Input.TextArea id="comment-reply" value={text} maxLength={2000} showCount rows={5} onChange={(e) => { setText(e.target.value); setConfirmed(false) }} style={{ marginTop: 8, marginBottom: 28 }} />
      <Checkbox checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)}>我已閱讀原評論與回覆內容，授權公開送出此回覆</Checkbox>
    </Modal>
  </>
}
