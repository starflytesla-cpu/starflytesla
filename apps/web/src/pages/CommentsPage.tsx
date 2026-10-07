import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert,
  App,
  Button,
  Card,
  Checkbox,
  Drawer,
  Empty,
  Grid,
  Input,
  Modal,
  Pagination,
  Skeleton,
  Space,
  Switch,
  Tag,
  Typography,
} from 'antd'
import dayjs from 'dayjs'
import { useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { api, type SocialComment } from '../api'
import { errorText } from '../api/http'
import PageHeader from '../components/PageHeader'
import QueryFeedback from '../components/QueryFeedback'
const INTENT: Record<string, string> = {
  unknown: '未分類',
  enquiry: '詢價',
  positive: '好評',
  complaint: '投訴 / 負面',
  spam: '垃圾',
  question: '問題',
}
const REPLY: Record<string, string> = {
  unreplied: '未回覆',
  failed: '送出失敗',
  sending: '請求已送出，待回執',
  uncertain: '回執待核對，禁止重送',
  replied: '已回覆',
}
function Status({ comment: c }: { comment: SocialComment }) {
  return (
    <Space wrap>
      <Tag color={c.intent === 'complaint' ? 'orange' : c.intent === 'enquiry' ? 'blue' : 'default'}>
        {INTENT[c.intent] ?? c.intent}
      </Tag>
      <Tag
        color={
          c.reply_status === 'replied'
            ? 'green'
            : ['uncertain', 'sending', 'failed'].includes(c.reply_status)
              ? 'orange'
              : 'default'
        }
      >
        {REPLY[c.reply_status] ?? c.reply_status}
      </Tag>
    </Space>
  )
}
export default function CommentsPage() {
  const { message } = App.useApp()
  const screens = Grid.useBreakpoint()
  const [params] = useSearchParams()
  const qc = useQueryClient()
  const [page, setPage] = useState(1)
  const [unreplied, setUnreplied] = useState(params.get('unreplied') === 'true')
  const [negative, setNegative] = useState(false)
  const [activeId, setActiveId] = useState<string | null>(null)
  const [target, setTarget] = useState<SocialComment | null>(null)
  const [text, setText] = useState('')
  const [confirmed, setConfirmed] = useState(false)
  const list = useQuery({
    queryKey: ['comments', page, unreplied, negative],
    queryFn: () => api.comments({ limit: 20, offset: (page - 1) * 20, unreplied, negative }),
  })
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ['comments'] })
    void qc.invalidateQueries({ queryKey: ['usage'] })
  }
  const suggest = useMutation({
    mutationFn: api.suggestComment,
    onSuccess: () => {
      refresh()
      message.success('AI 建議已保存，尚未送出')
    },
    onError: (e) => message.error(errorText(e)),
  })
  const reply = useMutation({
    mutationFn: () => api.replyComment(target!.id, text, target!.version),
    onSuccess: () => {
      refresh()
      setTarget(null)
      message.success('已取得平台回覆回執')
    },
    onError: (e) => {
      refresh()
      message.error(errorText(e))
      setTarget(null)
    },
  })
  const active = list.data?.items.find((c) => c.id === activeId) ?? (screens.md ? list.data?.items[0] : undefined)
  const detail = (c: SocialComment) => (
    <Card title={c.author || '匿名評論者'} className="comment-detail">
      <Status comment={c} />
      <Typography.Title level={5}>原評論</Typography.Title>
      <p className="comment-original">{c.text}</p>
      <p className="small muted">同步於 {dayjs(c.created_at).format('YYYY-MM-DD HH:mm')}</p>
      <Typography.Title level={5}>AI 建議（尚未送出）</Typography.Title>
      {c.suggested_reply ? (
        <Alert type="info" description={c.suggested_reply} title="建議草稿" />
      ) : (
        <p className="muted">
          {['unreplied', 'failed'].includes(c.reply_status) ? '尚無建議，可手動撰寫回覆。' : '尚無 AI 建議。'}
        </p>
      )}
      {['pending', 'generating'].includes(c.ai_status) ? (
        <p className="muted">AI 建議產生中，請稍後重新整理。</p>
      ) : null}
      {c.ai_error ? <Alert className="section" type="warning" title={c.ai_error} /> : null}
      {c.reply_text ? (
        <>
          <Typography.Title level={5}>人工確認的回覆</Typography.Title>
          <Typography.Paragraph style={{ whiteSpace: 'pre-wrap' }}>{c.reply_text}</Typography.Paragraph>
        </>
      ) : null}
      {c.error ? (
        <Alert className="section" type="warning" showIcon title="回覆 / 回執資訊" description={c.error} />
      ) : null}
      {['unreplied', 'failed'].includes(c.reply_status) ? (
        <Space wrap style={{ marginTop: 20 }}>
          <Button
            disabled={['pending', 'generating', 'uncertain'].includes(c.ai_status)}
            loading={suggest.isPending && suggest.variables === c.id}
            onClick={() => suggest.mutate(c.id)}
          >
            AI 分類與建議（計費）
          </Button>
          <Button
            type="primary"
            onClick={() => {
              setTarget(c)
              setText(c.suggested_reply)
              setConfirmed(false)
            }}
          >
            編輯並確認回覆
          </Button>
        </Space>
      ) : null}
    </Card>
  )
  return (
    <>
      <PageHeader
        title="評論收件匣"
        subtitle="閱讀原評論、檢查 AI 草稿，再逐則確認公開回覆。"
        extra={
          <Button
            onClick={() => {
              void list.refetch()
            }}
          >
            重新整理
          </Button>
        }
      />
      <Alert
        type="info"
        showIcon
        className="section"
        title={
          <span>
            可到 <Link to="/publish-tasks">發佈任務</Link> 手動同步。回執不明時，先到原平台核對。
          </span>
        }
      />
      <div className="asset-filters section">
        <Space>
          <Switch
            checked={unreplied}
            onChange={(v) => {
              setUnreplied(v)
              setPage(1)
              setActiveId(null)
            }}
            aria-label="只看未回覆"
          />
          <span>未回覆 / 送出失敗</span>
        </Space>
        <Space>
          <Switch
            checked={negative}
            onChange={(v) => {
              setNegative(v)
              setPage(1)
              setActiveId(null)
            }}
            aria-label="只看負面評論"
          />
          <span>負面評論（經 AI 分類）</span>
        </Space>
        <span className="small muted">符合條件 {list.data?.total ?? '—'} 則</span>
      </div>
      <QueryFeedback error={list.error} retry={list.refetch} stale={!!list.data} />
      <div className="comments-layout">
        <div className="record-list">
          {list.isPending ? <Skeleton active /> : null}
          {list.data?.items.map((c) => (
            <button
              key={c.id}
              className={`compact-record record-button${active?.id === c.id ? ' is-selected' : ''}`}
              onClick={() => setActiveId(c.id)}
            >
              <div className="record-pair">
                <strong>{c.author || '匿名評論者'}</strong>
                <span className="small muted">{dayjs(c.created_at).format('MM-DD')}</span>
              </div>
              <Status comment={c} />
              <Typography.Paragraph ellipsis={{ rows: 3 }} style={{ margin: 0 }}>
                {c.text}
              </Typography.Paragraph>
            </button>
          ))}
          {!list.isPending && !list.isError && !list.data?.items.length ? (
            <Empty description="目前沒有符合條件的評論" />
          ) : null}
          <Pagination
            current={page}
            pageSize={20}
            total={list.data?.total}
            showSizeChanger={false}
            onChange={(p) => {
              setPage(p)
              setActiveId(null)
            }}
          />
        </div>
        {screens.md && active ? detail(active) : null}
      </div>
      {!screens.md ? (
        <Drawer open={!!active} title="評論詳情" size="100%" onClose={() => setActiveId(null)}>
          {active ? detail(active) : null}
        </Drawer>
      ) : null}
      <Modal
        open={!!target}
        title="確認公開回覆"
        onCancel={() => {
          if (!reply.isPending) setTarget(null)
        }}
        onOk={() => {
          if (confirmed && text.trim()) reply.mutate()
        }}
        okText="確認並送出公開回覆"
        confirmLoading={reply.isPending}
        okButtonProps={{ disabled: !confirmed || !text.trim() }}
      >
        <p className="comment-original">{target?.text}</p>
        <label htmlFor="comment-reply">公開回覆內容</label>
        <Input.TextArea
          id="comment-reply"
          value={text}
          maxLength={2000}
          showCount
          rows={5}
          onChange={(e) => {
            setText(e.target.value)
            setConfirmed(false)
          }}
          style={{ marginTop: 8, marginBottom: 28 }}
        />
        <Checkbox checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)}>
          我已閱讀原評論與回覆內容，授權公開送出此回覆
        </Checkbox>
      </Modal>
    </>
  )
}
