import { ReloadOutlined } from '@ant-design/icons'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { App, Button, Card, Select, Space, Table, Tag, Typography } from 'antd'
import dayjs from 'dayjs'
import { useState } from 'react'
import { api, TASK_STATUS, type TaskItem, type TaskStatus } from '../api'
import { ApiError } from '../api/http'
import PageHeader from '../components/PageHeader'

const PAGE_SIZE = 30

function elapsed(task: TaskItem) {
  if (!task.started_at) return ''
  const end = task.finished_at ? dayjs(task.finished_at) : dayjs()
  const seconds = end.diff(dayjs(task.started_at), 'second')
  return seconds >= 60 ? `${Math.floor(seconds / 60)} 分 ${seconds % 60} 秒` : `${seconds} 秒`
}

export default function TasksPage() {
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const [status, setStatus] = useState<TaskStatus | undefined>()
  const [type, setType] = useState<string | undefined>()
  const [page, setPage] = useState(1)

  const { data, isPending } = useQuery({
    queryKey: ['tasks', status, type, page],
    queryFn: () => api.tasks({ status, type, limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE }),
    placeholderData: keepPreviousData,
    refetchInterval: (q) => {
      const counts = q.state.data?.counts
      return counts && (counts.queued ?? 0) + (counts.running ?? 0) > 0 ? 3000 : false
    },
  })

  const retry = useMutation({
    mutationFn: (id: string) => api.retryTask(id),
    onSuccess: () => {
      message.success('已重新排入佇列')
      void queryClient.invalidateQueries({ queryKey: ['tasks'] })
    },
    onError: (e) => message.error(e instanceof ApiError ? e.message : '重試失敗'),
  })

  const counts = data?.counts ?? {}

  return (
    <>
      <PageHeader title="任務中心" subtitle="素材分析、文案產生、成片渲染等背景任務的進度與錯誤；失敗的任務可以手動重試" />
      <div className="asset-filters section">
        <Space wrap>
          {(Object.keys(TASK_STATUS) as TaskStatus[]).map((key) => (
            <Tag key={key} color={TASK_STATUS[key].color}>
              {TASK_STATUS[key].label} {counts[key] ?? 0}
            </Tag>
          ))}
        </Space>
        <Select
          placeholder="全部狀態"
          allowClear
          className="asset-filter"
          value={status}
          onChange={(v?: TaskStatus) => {
            setStatus(v)
            setPage(1)
          }}
          options={Object.entries(TASK_STATUS).map(([value, s]) => ({ value, label: s.label }))}
        />
        <Select
          placeholder="全部類型"
          allowClear
          className="asset-filter"
          value={type}
          onChange={(v?: string) => {
            setType(v)
            setPage(1)
          }}
          options={Object.entries(data?.types ?? {}).map(([value, label]) => ({ value, label }))}
        />
      </div>
      <Card>
        <Table<TaskItem>
          rowKey="id"
          size="small"
          loading={isPending}
          dataSource={data?.items ?? []}
          scroll={{ x: 820 }}
          pagination={{
            current: page,
            pageSize: PAGE_SIZE,
            total: data?.total ?? 0,
            showSizeChanger: false,
            onChange: setPage,
          }}
          columns={[
            { title: '類型', dataIndex: 'type_label', width: 100 },
            {
              title: '對象',
              render: (_, t) => (
                <Typography.Text ellipsis className="task-label">
                  {t.label}
                </Typography.Text>
              ),
            },
            {
              title: '狀態',
              width: 90,
              render: (_, t) => <Tag color={TASK_STATUS[t.status].color}>{TASK_STATUS[t.status].label}</Tag>,
            },
            {
              title: '嘗試',
              width: 70,
              render: (_, t) => `${t.attempts}/${t.max_attempts}`,
            },
            { title: '建立時間', width: 120, render: (_, t) => dayjs(t.created_at).format('MM/DD HH:mm:ss') },
            { title: '耗時', width: 90, render: (_, t) => elapsed(t) },
            {
              title: '錯誤',
              render: (_, t) =>
                t.error ? (
                  <Typography.Text type={t.status === 'failed' ? 'danger' : 'warning'} className="small">
                    {t.error}
                  </Typography.Text>
                ) : null,
            },
            {
              title: '',
              width: 80,
              render: (_, t) =>
                t.status === 'failed' ? (
                  <Button size="small" icon={<ReloadOutlined />} loading={retry.isPending && retry.variables === t.id} onClick={() => retry.mutate(t.id)}>
                    重試
                  </Button>
                ) : null,
            },
          ]}
        />
      </Card>
    </>
  )
}
