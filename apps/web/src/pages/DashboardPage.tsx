import { CheckCircleFilled, ClockCircleOutlined } from '@ant-design/icons'
import { useQuery } from '@tanstack/react-query'
import { Alert, Button, Card, Col, Row, Statistic, Steps, Tag } from 'antd'
import { useNavigate } from 'react-router'
import { api, CAPABILITY_LABELS, formatUsd, type Capability } from '../api'
import { useMe } from '../useMe'
import PageHeader from '../components/PageHeader'

const PHASES = [
  { title: 'Phase 0 基礎建設', content: '登入、帳號、模型渠道、成本記錄' },
  { title: 'Phase 1 素材中心', content: '手機上傳、自動切鏡頭與打標籤' },
  { title: 'Phase 2 帳號檔案與文案', content: '品牌人設、模板、AI 改寫、音色' },
  { title: 'Phase 3 混剪引擎', content: '自動挑素材、配音字幕、批量成片、待審' },
  { title: 'Phase 4 發佈與評論', content: 'Upload-Post 排程發佈、評論管理' },
]

const NEEDED: { capability: Capability; phase: string }[] = [
  { capability: 'text', phase: '寫文案' },
  { capability: 'vision', phase: '素材打標籤' },
  { capability: 'tts', phase: '配音' },
]

export default function DashboardPage() {
  const { data: me } = useMe()
  const navigate = useNavigate()
  const { data, isPending } = useQuery({ queryKey: ['dashboard'], queryFn: api.dashboard })
  const isAdmin = me?.role === 'admin'
  const missing = NEEDED.filter((n) => !data?.ready_capabilities.includes(n.capability))

  return (
    <>
      <PageHeader title={`你好，${me?.display_name ?? ''}`} subtitle="平台目前的狀態與開發進度" />

      {isAdmin && data && missing.length > 0 ? (
        <Alert
          type="info"
          showIcon
          className="section"
          title="還需要設定 AI 模型"
          description={
            <>
              {missing.map((m) => (
                <div key={m.capability}>
                  尚未設定可用的「{CAPABILITY_LABELS[m.capability]}」模型（{m.phase}會用到）
                </div>
              ))}
            </>
          }
          action={
            <Button type="primary" onClick={() => navigate('/settings/channels')}>
              前往設定
            </Button>
          }
        />
      ) : null}

      {isAdmin ? (
        <Row gutter={[16, 16]} className="section">
          <Col xs={12} md={6}>
            <Card loading={isPending}>
              <Statistic title="本月 AI 花費（估算）" value={formatUsd(data?.month?.cost_usd ?? 0)} />
            </Card>
          </Col>
          <Col xs={12} md={6}>
            <Card loading={isPending}>
              <Statistic title="本月 AI 呼叫次數" value={data?.month?.calls ?? 0} />
            </Card>
          </Col>
          <Col xs={12} md={6}>
            <Card loading={isPending}>
              <Statistic title="模型渠道" value={data?.channels ?? 0} />
            </Card>
          </Col>
          <Col xs={12} md={6}>
            <Card loading={isPending}>
              <Statistic title="帳號數" value={data?.users ?? 0} />
            </Card>
          </Col>
        </Row>
      ) : null}

      <Row gutter={[16, 16]} className="section">
        <Col xs={12} md={6}>
          <Card loading={isPending} hoverable onClick={() => navigate('/assets')}>
            <Statistic title="素材" value={data?.assets.total ?? 0} />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card loading={isPending} hoverable onClick={() => navigate('/assets')}>
            <Statistic title="可用鏡頭" value={data?.assets.clips ?? 0} />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card loading={isPending} hoverable onClick={() => navigate('/assets')}>
            <Statistic
              title="分析中"
              value={(data?.assets.by_status.uploaded ?? 0) + (data?.assets.by_status.processing ?? 0)}
            />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card loading={isPending} hoverable onClick={() => navigate('/assets')}>
            <Statistic title="分析失敗" value={data?.assets.by_status.failed ?? 0} />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={14}>
          <Card title="開發進度">
            <Steps orientation="vertical" size="small" current={3} items={PHASES} />
          </Card>
        </Col>
        <Col xs={24} lg={10}>
          <Card title="AI 能力狀態">
            {(Object.keys(CAPABILITY_LABELS) as Capability[]).map((cap) => {
              const ready = data?.ready_capabilities.includes(cap)
              return (
                <div key={cap} className="capability-row">
                  <span>
                    {ready ? (
                      <CheckCircleFilled className="ok-icon" />
                    ) : (
                      <ClockCircleOutlined className="muted-icon" />
                    )}{' '}
                    {CAPABILITY_LABELS[cap]}
                  </span>
                  <Tag color={ready ? 'green' : 'default'}>{ready ? '已就緒' : '未設定'}</Tag>
                </div>
              )
            })}
          </Card>
        </Col>
      </Row>
    </>
  )
}
