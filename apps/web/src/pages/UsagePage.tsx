import { ReloadOutlined } from '@ant-design/icons'
import { useQueries, useQuery } from '@tanstack/react-query'
import {
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
  Drawer,
  Grid,
  Pagination,
  Row,
  Segmented,
  Skeleton,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
} from 'antd'
import dayjs from 'dayjs'
import { lazy, Suspense, useState } from 'react'
import { api, formatUsd, type UsageItem } from '../api'
import { failureRate, highFailure, USAGE_STATUS } from '../api/usageMetrics'
import MetricCard from '../components/MetricCard'
import PageHeader from '../components/PageHeader'
import QueryFeedback from '../components/QueryFeedback'

const CostCharts = lazy(() => import('../components/CostCharts'))
const SOURCES: Record<string, string> = {
  channel_test: '渠道測試',
  publish_channel_test: '發佈渠道檢查',
  publish_post: '發佈貼文',
  post_copy: '貼文草稿',
  comment_suggest: '評論建議',
  comment_reply: '人工回覆',
}
const STATUSES = Object.keys(USAGE_STATUS) as UsageItem['status'][]
const PAGE_SIZE = 20
const number = (value: number) => value.toLocaleString('zh-TW')
function Cost({ value }: { value: number | null }) {
  return (
    <Tooltip title={value == null ? '供應商未提供價格，未計入已知花費' : `原始金額：US$ ${value}`}>
      <span className="numeric">{formatUsd(value)}</span>
    </Tooltip>
  )
}
function Result({ status }: { status: UsageItem['status'] }) {
  return <Tag color={USAGE_STATUS[status].color}>{USAGE_STATUS[status].label}</Tag>
}

export default function UsagePage() {
  const screens = Grid.useBreakpoint()
  const [page, setPage] = useState(1)
  const [period, setPeriod] = useState(() => new Date().toISOString().slice(0, 7))
  const [status, setStatus] = useState<'all' | UsageItem['status']>('all')
  const [selected, setSelected] = useState<UsageItem | null>(null)
  const summary = useQuery({
    queryKey: ['usage', 'summary'],
    queryFn: api.usageSummary,
  })
  const counts = useQueries({
    queries: STATUSES.map((s) => ({
      queryKey: ['usage', 'count', s],
      queryFn: () => api.usage({ limit: 1, offset: 0, status: s }),
    })),
  })
  const list = useQuery({
    queryKey: ['usage', 'list', page, status],
    queryFn: () =>
      api.usage({
        limit: PAGE_SIZE,
        offset: (page - 1) * PAGE_SIZE,
        status: status === 'all' ? undefined : status,
      }),
  })
  const month = summary.data?.month
  const rate = month ? failureRate(month.calls, month.failed) : null
  const historyTotal = counts.every((q) => q.data) ? counts.reduce((sum, q) => sum + q.data!.total, 0) : undefined
  const refresh = () => {
    setPeriod(new Date().toISOString().slice(0, 7))
    return Promise.all([summary.refetch(), list.refetch(), ...counts.map((q) => q.refetch())])
  }
  const pagination = {
    current: page,
    pageSize: PAGE_SIZE,
    total: list.data?.total,
    onChange: setPage,
    showSizeChanger: false,
  }
  return (
    <>
      <PageHeader
        title="用量與成本"
        subtitle="查看已知花費、模型用量，以及需要處理的失敗或不明回執。"
        extra={
          <Button
            icon={<ReloadOutlined />}
            loading={summary.isFetching || list.isFetching}
            onClick={() => {
              void refresh()
            }}
          >
            重新整理
          </Button>
        }
      />
      <div className="scope-bar section">
        <Tag color="blue">{period} · UTC 月份</Tag>
        <span>摘要與圖表：本月累計</span>
        <span className="muted">
          {summary.dataUpdatedAt ? `更新於 ${dayjs(summary.dataUpdatedAt).format('HH:mm:ss')}（裝置時間）` : '等待資料'}
        </span>
      </div>
      <QueryFeedback error={summary.error} retry={summary.refetch} stale={!!summary.data} />
      <Row gutter={[16, 16]} className="section">
        <Col xs={12} lg={6}>
          <MetricCard
            title="本月花費（估算）"
            value={month ? formatUsd(month.cost_usd) : undefined}
            note="USD · 只計已知價格"
            loading={summary.isPending}
          />
        </Col>
        <Col xs={12} lg={6}>
          <MetricCard title="本月呼叫次數" value={month?.calls} note="包含各種結果狀態" loading={summary.isPending} />
        </Col>
        <Col xs={12} lg={6}>
          <MetricCard
            title="本月失敗次數"
            value={month?.failed}
            danger={!!month && highFailure(month.calls, month.failed)}
            note={rate == null ? '占全部呼叫：—' : `占全部呼叫 ${rate.toFixed(1)}%`}
            loading={summary.isPending}
          />
        </Col>
        <Col xs={12} lg={6}>
          <MetricCard
            title="本月未定價呼叫"
            value={month?.unpriced}
            note="金額未知，待補價格"
            loading={summary.isPending}
          />
        </Col>
      </Row>
      {month && highFailure(month.calls, month.failed) ? (
        <Alert
          className="section"
          showIcon
          type="error"
          title={`本月失敗占全部呼叫 ${rate!.toFixed(1)}%`}
          description="呼叫至少 20 次且失敗占比達 20%。請檢查渠道連線與失敗詳情；處理中與待核對不視為成功。"
          action={
            <Button
              onClick={() => {
                setStatus('failed')
                setPage(1)
              }}
            >
              查看失敗記錄
            </Button>
          }
        />
      ) : null}
      {summary.data ? (
        <Suspense
          fallback={
            <Card className="section">
              <Skeleton active />
            </Card>
          }
        >
          <CostCharts models={summary.data.by_model} />
        </Suspense>
      ) : null}
      <Card title="本月模型明細" className="section" extra={<span className="small muted">USD · UTC 月份</span>}>
        {screens.md ? (
          <Table
            size="middle"
            rowKey={(r) => `${r.provider}/${r.model_key}`}
            loading={summary.isPending}
            dataSource={summary.data?.by_model ?? []}
            pagination={false}
            scroll={{ x: 660 }}
            locale={{
              emptyText: summary.isError ? '讀取失敗，請重試' : '本月還沒有呼叫',
            }}
            columns={[
              {
                title: '服務商 / 模型',
                render: (_, r) => (
                  <>
                    <Tag>{r.provider}</Tag>
                    <div className="mono small">{r.model_key}</div>
                  </>
                ),
              },
              {
                title: '次數',
                dataIndex: 'calls',
                align: 'right',
                render: number,
              },
              {
                title: '輸入 / 輸出 token',
                align: 'right',
                render: (_, r) => `${number(r.input_tokens)} / ${number(r.output_tokens)}`,
              },
              {
                title: '已知花費',
                dataIndex: 'cost_usd',
                align: 'right',
                render: (v: number) => <Cost value={v} />,
              },
              {
                title: '花費占比',
                align: 'right',
                render: (_, r) =>
                  month && month.cost_usd > 0 ? `${((r.cost_usd / month.cost_usd) * 100).toFixed(1)}%` : '—',
              },
            ]}
          />
        ) : (
          <div className="record-list">
            {summary.data?.by_model.map((m) => (
              <div className="compact-record" key={`${m.provider}/${m.model_key}`}>
                <Tag>{m.provider}</Tag>
                <strong className="break-word">{m.model_key}</strong>
                <div className="record-pair">
                  <span>{number(m.calls)} 次</span>
                  <Cost value={m.cost_usd} />
                </div>
                <div className="small muted">
                  Token {number(m.input_tokens)} / {number(m.output_tokens)}
                </div>
              </div>
            ))}
            {summary.isPending ? <Skeleton active /> : null}
          </div>
        )}
      </Card>
      <Card title="呼叫記錄" extra={<span className="small muted">全部歷史 · 裝置時間</span>}>
        <div className="scroll-tabs section">
          <Segmented
            value={status}
            onChange={(v) => {
              setStatus(v as typeof status)
              setPage(1)
            }}
            options={[
              { value: 'all', label: `全部 ${historyTotal ?? '—'}` },
              ...STATUSES.map((s, i) => ({
                value: s,
                label: `${USAGE_STATUS[s].label} ${counts[i].data?.total ?? '—'}`,
              })),
            ]}
          />
        </div>
        <QueryFeedback error={list.error || counts.find((q) => q.error)?.error} retry={refresh} stale={!!list.data} />
        {screens.md ? (
          <Table<UsageItem>
            size="middle"
            rowKey="id"
            loading={list.isPending}
            dataSource={list.data?.items ?? []}
            scroll={{ x: 920 }}
            pagination={pagination}
            locale={{
              emptyText: list.isError ? '讀取失敗，請重試' : '沒有符合條件的呼叫',
            }}
            columns={[
              {
                title: '時間 / 來源',
                render: (_, r) => (
                  <>
                    <div>{dayjs(r.created_at).format('MM-DD HH:mm:ss')}</div>
                    <span className="small muted">{SOURCES[r.source] ?? r.source}</span>
                  </>
                ),
              },
              {
                title: '模型 / 渠道',
                render: (_, r) => (
                  <>
                    <div className="mono small">{r.model_key}</div>
                    <span className="small muted">{r.channel_name}</span>
                  </>
                ),
              },
              { title: '結果', render: (_, r) => <Result status={r.status} /> },
              {
                title: 'Token（入 / 出）',
                align: 'right',
                render: (_, r) => `${number(r.input_tokens)} / ${number(r.output_tokens)}`,
              },
              {
                title: '耗時',
                align: 'right',
                render: (_, r) => `${(r.duration_ms / 1000).toFixed(1)} 秒`,
              },
              {
                title: '成本',
                dataIndex: 'cost_usd',
                align: 'right',
                render: (v: number | null) => <Cost value={v} />,
              },
              {
                title: '操作',
                render: (_, r) => (
                  <Button size="small" onClick={() => setSelected(r)}>
                    詳情
                  </Button>
                ),
              },
            ]}
          />
        ) : (
          <>
            <div className="record-list">
              {list.data?.items.map((r) => (
                <button className="compact-record record-button" key={r.id} onClick={() => setSelected(r)}>
                  <div className="record-pair">
                    <Result status={r.status} />
                    <Cost value={r.cost_usd} />
                  </div>
                  <strong className="break-word">{r.model_key}</strong>
                  <div className="small muted">
                    {SOURCES[r.source] ?? r.source} · {dayjs(r.created_at).format('MM-DD HH:mm:ss')}
                  </div>
                  <span className="small">查看完整詳情 →</span>
                </button>
              ))}
              {list.isPending ? <Skeleton active /> : null}
              {!list.isPending && !list.isError && !list.data?.items.length ? (
                <p className="muted">沒有符合條件的呼叫</p>
              ) : null}
            </div>
            <Pagination {...pagination} className="asset-pagination" />
          </>
        )}
      </Card>
      <Drawer open={!!selected} title="呼叫詳情" size={screens.md ? 560 : '100%'} onClose={() => setSelected(null)}>
        {selected ? (
          <>
            <Space className="section" wrap>
              <Result status={selected.status} />
              <Tag>{selected.provider}</Tag>
            </Space>
            <Descriptions
              column={1}
              bordered
              size="small"
              items={[
                {
                  key: 'time',
                  label: '時間',
                  children: dayjs(selected.created_at).format('YYYY-MM-DD HH:mm:ss'),
                },
                {
                  key: 'source',
                  label: '來源 / 操作',
                  children: `${SOURCES[selected.source] ?? selected.source} / ${selected.action}`,
                },
                { key: 'model', label: '模型', children: selected.model_key },
                {
                  key: 'channel',
                  label: '渠道',
                  children: selected.channel_name,
                },
                {
                  key: 'tokens',
                  label: '輸入 / 輸出 token',
                  children: `${number(selected.input_tokens)} / ${number(selected.output_tokens)}`,
                },
                {
                  key: 'duration',
                  label: '耗時',
                  children: `${selected.duration_ms} ms`,
                },
                {
                  key: 'cost',
                  label: '成本',
                  children: (
                    <>
                      <Cost value={selected.cost_usd} />
                      {selected.cost_usd != null ? (
                        <div className="small muted">原始金額 US$ {selected.cost_usd}</div>
                      ) : null}
                    </>
                  ),
                },
                {
                  key: 'user',
                  label: '操作人',
                  children: selected.user_name || '系統',
                },
                {
                  key: 'id',
                  label: '記錄 ID',
                  children: <span className="mono small break-word">{selected.id}</span>,
                },
              ]}
            />
            {selected.error ? (
              <Alert
                className="section detail-error"
                type={selected.status === 'failed' ? 'error' : 'warning'}
                showIcon
                title="完整錯誤 / 回執資訊"
                description={
                  <Typography.Paragraph copyable className="error-body">
                    {selected.error}
                  </Typography.Paragraph>
                }
              />
            ) : null}
          </>
        ) : null}
      </Drawer>
    </>
  )
}
