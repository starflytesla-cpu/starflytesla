import { ReloadOutlined } from '@ant-design/icons'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { App, Button, Card, Descriptions, Drawer, Grid, Pagination, Select, Space, Table, Tag, Typography } from 'antd'
import dayjs from 'dayjs'
import { useState } from 'react'
import { api, TASK_STATUS, type TaskItem, type TaskStatus } from '../api'
import { errorText } from '../api/http'
import PageHeader from '../components/PageHeader'
import QueryFeedback from '../components/QueryFeedback'
const PAGE_SIZE = 30
function elapsed(t: TaskItem) {
  if (!t.started_at) return '尚未開始'
  const seconds = (t.finished_at ? dayjs(t.finished_at) : dayjs()).diff(dayjs(t.started_at), 'second')
  return seconds >= 60 ? `${Math.floor(seconds / 60)} 分 ${seconds % 60} 秒` : `${seconds} 秒`
}
export default function TasksPage() {
  const { message } = App.useApp()
  const screens = Grid.useBreakpoint()
  const qc = useQueryClient()
  const [status, setStatus] = useState<TaskStatus | undefined>()
  const [type, setType] = useState<string | undefined>()
  const [page, setPage] = useState(1)
  const [selected, setSelected] = useState<string | null>(null)
  const list = useQuery({
    queryKey: ['tasks', status, type, page],
    queryFn: () =>
      api.tasks({
        status,
        type,
        limit: PAGE_SIZE,
        offset: (page - 1) * PAGE_SIZE,
      }),
    placeholderData: keepPreviousData,
    refetchInterval: (q) =>
      q.state.data && (q.state.data.counts.queued ?? 0) + (q.state.data.counts.running ?? 0) > 0 ? 3000 : false,
  })
  const retry = useMutation({
    mutationFn: api.retryTask,
    onSuccess: () => {
      message.success('已重新排入佇列')
      void qc.invalidateQueries({ queryKey: ['tasks'] })
    },
    onError: (e) => message.error(errorText(e)),
  })
  const task = list.data?.items.find((t) => t.id === selected)
  const pagination = {
    current: page,
    pageSize: PAGE_SIZE,
    total: list.data?.total,
    showSizeChanger: false,
    onChange: setPage,
  }
  const result = (t: TaskItem) => <Tag color={TASK_STATUS[t.status].color}>{TASK_STATUS[t.status].label}</Tag>
  return (
    <>
      <PageHeader
        title="任務中心"
        subtitle="查看排隊、執行進度與失敗詳情。只對已失敗的任務提供手動重試。"
        extra={
          <Button
            icon={<ReloadOutlined />}
            onClick={() => {
              void list.refetch()
            }}
          >
            重新整理
          </Button>
        }
      />
      <div className="asset-filters section">
        <Space wrap>
          {(Object.keys(TASK_STATUS) as TaskStatus[]).map((s) => (
            <Button
              key={s}
              type={status === s ? 'primary' : 'default'}
              onClick={() => {
                setStatus(status === s ? undefined : s)
                setPage(1)
              }}
            >
              {TASK_STATUS[s].label} {list.data?.counts[s] ?? '—'}
            </Button>
          ))}
        </Space>
        <Select
          placeholder="全部類型"
          allowClear
          className="asset-filter"
          value={type}
          onChange={(v) => {
            setType(v)
            setPage(1)
          }}
          options={Object.entries(list.data?.types ?? {}).map(([value, label]) => ({ value, label }))}
        />
        {status || type ? (
          <Button
            type="link"
            onClick={() => {
              setStatus(undefined)
              setType(undefined)
              setPage(1)
            }}
          >
            清除篩選
          </Button>
        ) : null}
      </div>
      <QueryFeedback error={list.error} retry={list.refetch} stale={!!list.data} />
      {screens.md ? (
        <Card>
          <Table<TaskItem>
            size="middle"
            rowKey="id"
            loading={list.isPending}
            dataSource={list.data?.items ?? []}
            scroll={{ x: 760 }}
            pagination={pagination}
            columns={[
              {
                title: '任務 / 對象',
                render: (_, t) => (
                  <>
                    <strong>{t.label}</strong>
                    <div className="small muted">{t.type_label}</div>
                  </>
                ),
              },
              { title: '狀態', render: (_, t) => result(t) },
              {
                title: '嘗試',
                align: 'right',
                render: (_, t) => `${t.attempts}/${t.max_attempts}`,
              },
              {
                title: '建立時間',
                render: (_, t) => dayjs(t.created_at).format('MM/DD HH:mm:ss'),
              },
              { title: '耗時', render: (_, t) => elapsed(t) },
              {
                title: '錯誤摘要',
                render: (_, t) =>
                  t.error ? (
                    <Typography.Paragraph ellipsis={{ rows: 2 }} type="danger" style={{ maxWidth: 280, margin: 0 }}>
                      {t.error}
                    </Typography.Paragraph>
                  ) : (
                    '—'
                  ),
              },
              {
                title: '操作',
                render: (_, t) => <Button onClick={() => setSelected(t.id)}>詳情</Button>,
              },
            ]}
          />
        </Card>
      ) : (
        <>
          <div className="record-list">
            {list.data?.items.map((t) => (
              <button key={t.id} className="compact-record record-button" onClick={() => setSelected(t.id)}>
                <div className="record-pair">
                  <strong>{t.label}</strong>
                  {result(t)}
                </div>
                <span>
                  {t.type_label} · {elapsed(t)}
                </span>
                <span className="small muted">
                  {dayjs(t.created_at).format('MM/DD HH:mm:ss')} · 嘗試 {t.attempts}/{t.max_attempts}
                </span>
                {t.error ? (
                  <Typography.Paragraph ellipsis={{ rows: 2 }} type="danger">
                    {t.error}
                  </Typography.Paragraph>
                ) : null}
                <span className="small">查看完整詳情 →</span>
              </button>
            ))}
          </div>
          <Pagination {...pagination} className="asset-pagination" />
        </>
      )}
      {!list.isPending && !list.isError && !list.data?.items.length ? (
        <p className="muted">沒有符合條件的任務</p>
      ) : null}
      <Drawer
        open={!!task}
        title="任務詳情"
        size={screens.md ? 560 : '100%'}
        onClose={() => setSelected(null)}
        footer={
          task?.status === 'failed' ? (
            <Button
              icon={<ReloadOutlined />}
              type="primary"
              loading={retry.isPending}
              onClick={() => retry.mutate(task.id)}
            >
              重新排入佇列
            </Button>
          ) : null
        }
      >
        {task ? (
          <>
            {result(task)}
            <Typography.Title level={4}>{task.label}</Typography.Title>
            <Descriptions
              bordered
              column={1}
              items={[
                { key: 'type', label: '類型', children: task.type_label },
                {
                  key: 'attempts',
                  label: '嘗試 / 上限',
                  children: `${task.attempts} / ${task.max_attempts}`,
                },
                {
                  key: 'created',
                  label: '建立',
                  children: dayjs(task.created_at).format('YYYY-MM-DD HH:mm:ss'),
                },
                {
                  key: 'run',
                  label: '最早執行',
                  children: dayjs(task.run_after).format('YYYY-MM-DD HH:mm:ss'),
                },
                { key: 'elapsed', label: '耗時', children: elapsed(task) },
                {
                  key: 'target',
                  label: '對象',
                  children: <span className="mono small">{task.target}</span>,
                },
                {
                  key: 'id',
                  label: '任務 ID',
                  children: <span className="mono small">{task.id}</span>,
                },
              ]}
            />
            {task.error ? (
              <div className="detail-error">
                <Typography.Title level={5}>完整錯誤</Typography.Title>
                <Typography.Paragraph copyable className="error-body">
                  {task.error}
                </Typography.Paragraph>
              </div>
            ) : null}
          </>
        ) : null}
      </Drawer>
    </>
  )
}
