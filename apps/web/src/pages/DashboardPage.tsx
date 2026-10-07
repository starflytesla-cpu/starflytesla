import { CheckCircleFilled, ClockCircleOutlined, ArrowRightOutlined } from '@ant-design/icons'
import { useQuery } from '@tanstack/react-query'
import { Alert, Button, Card, Col, Row, Space, Tag } from 'antd'
import { useNavigate } from 'react-router'
import { api, CAPABILITY_LABELS, formatUsd, type Capability } from '../api'
import { useMe } from '../useMe'
import MetricCard from '../components/MetricCard'
import PageHeader from '../components/PageHeader'
import QueryFeedback from '../components/QueryFeedback'

const FLOW = [
  { title: '整理素材', text: '上傳工廠畫面，檢查鏡頭與分類', path: '/assets' },
  { title: '核准文案', text: '選擇模板，確認配音稿與字幕', path: '/templates' },
  { title: '批量製作', text: '檢查素材覆蓋，產生直式成片', path: '/editor' },
  { title: '審核與發佈', text: '逐支預覽，再安排公開發佈', path: '/works' },
]
const NEEDED: Capability[] = ['text', 'vision', 'tts']
export default function DashboardPage() {
  const { data: me } = useMe()
  const navigate = useNavigate()
  const dashboard = useQuery({
    queryKey: ['dashboard'],
    queryFn: api.dashboard,
  })
  const isAdmin = me?.role === 'admin'
  const videos = useQuery({
    queryKey: ['video-stats'],
    queryFn: api.videoStats,
    enabled: isAdmin,
  })
  const tasks = useQuery({
    queryKey: ['tasks', 'dashboard'],
    queryFn: () => api.tasks({ limit: 1, offset: 0 }),
    enabled: isAdmin,
  })
  const comments = useQuery({
    queryKey: ['comments', 'dashboard'],
    queryFn: () => api.comments({ limit: 1, offset: 0, unreplied: true }),
    enabled: isAdmin,
  })
  const data = dashboard.data
  const missing = data ? NEEDED.filter((cap) => !data.ready_capabilities.includes(cap)) : []
  return (
    <>
      <PageHeader
        title={`你好，${me?.display_name ?? ''}`}
        subtitle="先處理待辦，再開始今天的內容製作。"
        extra={
          <Button type="primary" onClick={() => navigate('/assets')}>
            上傳素材
          </Button>
        }
      />
      <QueryFeedback error={dashboard.error} retry={dashboard.refetch} stale={!!data} />
      {isAdmin ? (
        <>
          <Row gutter={[16, 16]} className="section">
            <Col xs={12} lg={6}>
              <MetricCard
                title="成片待審"
                value={videos.data?.pending_review}
                loading={videos.isPending}
                note="前往預覽與人工審核 →"
                onClick={() => navigate('/works')}
              />
            </Col>
            <Col xs={12} lg={6}>
              <MetricCard
                title="素材分析失敗"
                value={data?.assets.by_status.failed}
                loading={dashboard.isPending}
                note="檢查錯誤與來源素材 →"
                onClick={() => navigate('/assets?status=failed')}
              />
            </Col>
            <Col xs={12} lg={6}>
              <MetricCard
                title="排隊 / 執行中任務"
                value={tasks.data ? (tasks.data.counts.queued ?? 0) + (tasks.data.counts.running ?? 0) : undefined}
                loading={tasks.isPending}
                note="查看背景任務進度 →"
                onClick={() => navigate('/tasks')}
              />
            </Col>
            <Col xs={12} lg={6}>
              <MetricCard
                title="未回覆 / 回覆失敗"
                value={comments.data?.total}
                loading={comments.isPending}
                note="閱讀評論並確認回覆 →"
                onClick={() => navigate('/comments?unreplied=true')}
              />
            </Col>
          </Row>
          <QueryFeedback
            error={videos.error || tasks.error || comments.error}
            retry={() => Promise.all([videos.refetch(), tasks.refetch(), comments.refetch()])}
          />
          {missing.length ? (
            <Alert
              showIcon
              type="warning"
              className="section"
              title={`尚缺 ${missing.map((cap) => CAPABILITY_LABELS[cap]).join('、')} 模型`}
              description="設定預設模型後，才能完成對應的製作步驟。"
              action={<Button onClick={() => navigate('/settings/channels')}>前往設定</Button>}
            />
          ) : null}
          <Row gutter={[16, 16]} className="section">
            {FLOW.map((flow, i) => (
              <Col xs={24} md={12} xl={6} key={flow.path}>
                <Card className="workflow-card full-height">
                  <span className="workflow-index">0{i + 1}</span>
                  <h2>{flow.title}</h2>
                  <p className="muted">{flow.text}</p>
                  <Button onClick={() => navigate(flow.path)} icon={<ArrowRightOutlined />}>
                    前往{flow.title}
                  </Button>
                </Card>
              </Col>
            ))}
          </Row>
        </>
      ) : null}
      <Row gutter={[16, 16]}>
        <Col xs={24} lg={isAdmin ? 14 : 24}>
          <Card title="素材與用量概覽">
            <Row gutter={[16, 24]}>
              <Col xs={12}>
                <MetricCard title="素材總數" value={data?.assets.total} loading={dashboard.isPending} />
              </Col>
              <Col xs={12}>
                <MetricCard title="可用鏡頭" value={data?.assets.clips} loading={dashboard.isPending} />
              </Col>
              {isAdmin ? (
                <>
                  <Col xs={12}>
                    <MetricCard
                      title="本月已知花費（估算）"
                      value={data?.month ? formatUsd(data.month.cost_usd) : undefined}
                      note="USD · UTC 月份"
                      onClick={() => navigate('/settings/usage')}
                    />
                  </Col>
                  <Col xs={12}>
                    <MetricCard
                      title="本月呼叫次數"
                      value={data?.month?.calls}
                      note="前往成本與記錄 →"
                      onClick={() => navigate('/settings/usage')}
                    />
                  </Col>
                </>
              ) : null}
            </Row>
          </Card>
        </Col>
        {isAdmin ? (
          <Col xs={24} lg={10}>
            <Card title="AI 能力狀態" loading={dashboard.isPending}>
              {data ? (
                (Object.keys(CAPABILITY_LABELS) as Capability[]).map((cap) => (
                  <div key={cap} className="capability-row">
                    <Space>
                      {data.ready_capabilities.includes(cap) ? (
                        <CheckCircleFilled className="ok-icon" />
                      ) : (
                        <ClockCircleOutlined className="muted-icon" />
                      )}
                      {CAPABILITY_LABELS[cap]}
                    </Space>
                    <Tag color={data.ready_capabilities.includes(cap) ? 'green' : 'default'}>
                      {data.ready_capabilities.includes(cap) ? '已就緒' : '未設定'}
                    </Tag>
                  </div>
                ))
              ) : (
                <span className="muted">狀態尚未取得</span>
              )}
            </Card>
          </Col>
        ) : null}
      </Row>
    </>
  )
}
