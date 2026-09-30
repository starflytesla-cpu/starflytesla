import { useQuery } from '@tanstack/react-query'
import { Card, Col, Row, Segmented, Statistic, Table, Tag, Tooltip, Typography } from 'antd'
import dayjs from 'dayjs'
import { useState } from 'react'
import { api, formatUsd, type UsageItem } from '../api'
import PageHeader from '../components/PageHeader'

const SOURCE_LABELS: Record<string, string> = {
  channel_test: '渠道測試',
}

const PAGE_SIZE = 20

export default function UsagePage() {
  const [page, setPage] = useState(1)
  const [status, setStatus] = useState<'all' | 'succeeded' | 'failed'>('all')
  const summary = useQuery({ queryKey: ['usage', 'summary'], queryFn: api.usageSummary })
  const list = useQuery({
    queryKey: ['usage', 'list', page, status],
    queryFn: () =>
      api.usage({ limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE, status: status === 'all' ? undefined : status }),
  })
  const month = summary.data?.month

  return (
    <>
      <PageHeader
        title="用量與成本"
        subtitle="每一次 AI 呼叫都會記錄 token 與估算成本。試營運只記錄不扣費，之後用來訂定積分價格。"
      />
      <Row gutter={[16, 16]} className="section">
        <Col xs={12} md={6}>
          <Card loading={summary.isPending}>
            <Statistic title="本月花費（估算）" value={formatUsd(month?.cost_usd ?? 0)} />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card loading={summary.isPending}>
            <Statistic title="本月呼叫次數" value={month?.calls ?? 0} />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card loading={summary.isPending}>
            <Statistic title="失敗次數" value={month?.failed ?? 0} />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card loading={summary.isPending}>
            <Statistic title="未設定價格的呼叫" value={month?.unpriced ?? 0} />
          </Card>
        </Col>
      </Row>

      <Card title="本月各模型花費" className="section">
        <Table
          size="small"
          rowKey={(r) => `${r.provider}/${r.model_key}`}
          loading={summary.isPending}
          dataSource={summary.data?.by_model ?? []}
          pagination={false}
          scroll={{ x: 600 }}
          locale={{ emptyText: '本月還沒有任何呼叫' }}
          columns={[
            { title: '服務商', dataIndex: 'provider' },
            { title: '模型', dataIndex: 'model_key', render: (v: string) => <span className="mono">{v}</span> },
            { title: '次數', dataIndex: 'calls' },
            { title: '輸入 token', dataIndex: 'input_tokens' },
            { title: '輸出 token', dataIndex: 'output_tokens' },
            { title: '花費', dataIndex: 'cost_usd', render: (v: number) => formatUsd(v) },
          ]}
        />
      </Card>

      <Card
        title="呼叫記錄"
        extra={
          <Segmented
            value={status}
            onChange={(v) => {
              setStatus(v as typeof status)
              setPage(1)
            }}
            options={[
              { label: '全部', value: 'all' },
              { label: '成功', value: 'succeeded' },
              { label: '失敗', value: 'failed' },
            ]}
          />
        }
      >
        <Table<UsageItem>
          size="small"
          rowKey="id"
          loading={list.isPending}
          dataSource={list.data?.items ?? []}
          scroll={{ x: 900 }}
          pagination={{
            current: page,
            pageSize: PAGE_SIZE,
            total: list.data?.total ?? 0,
            onChange: setPage,
            showSizeChanger: false,
          }}
          columns={[
            { title: '時間', dataIndex: 'created_at', render: (v: string) => dayjs(v).format('MM-DD HH:mm:ss') },
            { title: '來源', dataIndex: 'source', render: (v: string) => SOURCE_LABELS[v] ?? v },
            {
              title: '模型',
              render: (_, r) => (
                <div>
                  <div className="mono small">{r.model_key}</div>
                  <Typography.Text type="secondary" className="small">
                    {r.channel_name}
                  </Typography.Text>
                </div>
              ),
            },
            {
              title: '結果',
              dataIndex: 'status',
              render: (v: string, r) =>
                v === 'succeeded' ? (
                  <Tag color="green">成功</Tag>
                ) : (
                  <Tooltip title={r.error}>
                    <Tag color="red">失敗</Tag>
                  </Tooltip>
                ),
            },
            { title: 'Token（入 / 出）', render: (_, r) => `${r.input_tokens} / ${r.output_tokens}` },
            { title: '耗時', dataIndex: 'duration_ms', render: (v: number) => `${(v / 1000).toFixed(1)} 秒` },
            { title: '成本', dataIndex: 'cost_usd', render: (v: number | null) => formatUsd(v) },
            { title: '操作人', dataIndex: 'user_name' },
          ]}
        />
      </Card>
    </>
  )
}
