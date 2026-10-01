import { CustomerServiceOutlined, DeleteOutlined, LoadingOutlined, UploadOutlined } from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert,
  App,
  Button,
  Card,
  Col,
  Empty,
  Form,
  Input,
  Popconfirm,
  Progress,
  Row,
  Select,
  Switch,
  Table,
  Tag,
  Typography,
} from 'antd'
import dayjs from 'dayjs'
import { useRef, useState, type ChangeEvent } from 'react'
import { api, formatDuration, MUSIC_PRESETS, type MusicTrack } from '../api'
import { ApiError } from '../api/http'
import { createUpload, startOrResume } from '../api/upload'
import AudioButton from '../components/AudioButton'
import PageHeader from '../components/PageHeader'

function errorText(error: unknown) {
  return error instanceof ApiError ? error.message : '操作失敗'
}

export default function MusicPage() {
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const fileInput = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState<{ name: string; percent: number } | null>(null)
  const [form] = Form.useForm<{ preset: string; extra: string; title: string }>()

  const { data, isPending } = useQuery({
    queryKey: ['music'],
    queryFn: api.music,
    refetchInterval: (q) => (q.state.data?.items.some((t) => t.status === 'generating') ? 5000 : false),
  })
  const refresh = () => queryClient.invalidateQueries({ queryKey: ['music'] })

  const generate = useMutation({
    mutationFn: (values: { preset: string; extra: string; title: string }) => api.generateMusic(values),
    onSuccess: () => {
      message.success('已開始產生，約 1～3 分鐘，完成後會出現 2 首')
      form.resetFields(['extra', 'title'])
      void refresh()
    },
    onError: (e) => message.error(errorText(e)),
  })
  const update = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Partial<{ title: string; is_active: boolean }> }) => api.updateMusic(id, body),
    onSuccess: () => void refresh(),
    onError: (e) => message.error(errorText(e)),
  })
  const remove = useMutation({
    mutationFn: (id: string) => api.deleteMusic(id),
    onSuccess: () => {
      message.success('已刪除')
      void refresh()
    },
    onError: (e) => message.error(errorText(e)),
  })

  const onPick = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    setUploading({ name: file.name, percent: 0 })
    const upload = createUpload(
      file,
      {
        onProgress: (sent, total) => setUploading({ name: file.name, percent: Math.floor((sent / total) * 100) }),
        onSuccess: () => {
          setUploading(null)
          message.success('音樂已加入')
          void refresh()
        },
        onError: (error) => {
          setUploading(null)
          message.error(error)
        },
      },
      'music',
    )
    void startOrResume(upload)
  }

  const tracks = data?.items ?? []
  const ready = tracks.filter((t) => t.status === 'ready' && t.is_active).length

  return (
    <>
      <PageHeader
        title="背景音樂"
        subtitle="成片從頭到尾使用同一首背景音樂，配音時自動壓低音量。可以上傳自己的音樂，或用 AI 產生免版權純音樂"
      />
      {data && ready === 0 ? (
        <Alert
          className="section"
          type="info"
          showIcon
          title="音樂庫還是空的"
          description="先上傳或用 AI 產生幾首背景音樂。產生成片時選「每支自動隨機」，同一批成片會用不同的音樂。"
        />
      ) : null}
      <Row gutter={[16, 16]} className="section">
        <Col xs={24} lg={10}>
          <Card title="上傳音樂" className="full-height">
            <input ref={fileInput} type="file" accept="audio/*,.mp3,.m4a,.wav,.aac,.ogg" hidden onChange={onPick} />
            <Typography.Paragraph type="secondary" className="small">
              支援 mp3、m4a、wav，單檔 50 MB 以內。請使用有授權的音樂（例如 YouTube 音效庫、自己購買的版權音樂），避免發佈後被平台靜音。
            </Typography.Paragraph>
            <Button type="primary" icon={<UploadOutlined />} onClick={() => fileInput.current?.click()} disabled={!!uploading}>
              選擇音樂檔
            </Button>
            {uploading ? (
              <div className="section music-progress">
                <Typography.Text ellipsis>{uploading.name}</Typography.Text>
                <Progress percent={uploading.percent} size="small" status="active" />
              </div>
            ) : null}
          </Card>
        </Col>
        <Col xs={24} lg={14}>
          <Card title="AI 產生純音樂（kie.ai Suno）">
            <Form
              form={form}
              layout="vertical"
              initialValues={{ preset: 'corporate', extra: '', title: '' }}
              onFinish={(values) => generate.mutate(values)}
            >
              <Row gutter={12}>
                <Col xs={24} sm={12}>
                  <Form.Item name="preset" label="風格">
                    <Select options={Object.entries(MUSIC_PRESETS).map(([value, label]) => ({ value, label }))} />
                  </Form.Item>
                </Col>
                <Col xs={24} sm={12}>
                  <Form.Item name="title" label="名稱（選填）">
                    <Input maxLength={120} placeholder="例如 工廠主打背景" />
                  </Form.Item>
                </Col>
              </Row>
              <Form.Item name="extra" label="補充描述（選填，英文效果較好）">
                <Input maxLength={300} placeholder="例如 120 bpm, guitar, uplifting" />
              </Form.Item>
              <Button type="primary" icon={<CustomerServiceOutlined />} loading={generate.isPending} onClick={() => form.submit()}>
                產生 2 首
              </Button>
              <Typography.Text type="secondary" className="small music-note">
                約 1～3 分鐘，使用 kie.ai 點數
              </Typography.Text>
            </Form>
          </Card>
        </Col>
      </Row>

      <Card title={`音樂庫（${tracks.length}）`}>
        {data && tracks.length === 0 ? <Empty description="還沒有音樂" /> : null}
        {tracks.length ? (
          <Table<MusicTrack>
            rowKey="id"
            size="small"
            loading={isPending}
            dataSource={tracks}
            pagination={false}
            scroll={{ x: 640 }}
            columns={[
              {
                title: '',
                width: 56,
                render: (_, t) =>
                  t.audio_url ? (
                    <AudioButton url={t.audio_url} shape="circle" type="primary" />
                  ) : t.status === 'generating' ? (
                    <LoadingOutlined />
                  ) : null,
              },
              {
                title: '名稱',
                render: (_, t) => (
                  <div>
                    <Typography.Text
                      editable={
                        t.status === 'ready'
                          ? { onChange: (title) => title !== t.title && update.mutate({ id: t.id, body: { title } }) }
                          : false
                      }
                    >
                      {t.title}
                    </Typography.Text>
                    {t.status === 'generating' ? <div className="small muted">AI 產生中…</div> : null}
                    {t.status === 'failed' || (t.error && t.status === 'generating') ? (
                      <div className="small">
                        <Typography.Text type={t.status === 'failed' ? 'danger' : 'warning'}>{t.error}</Typography.Text>
                      </div>
                    ) : null}
                  </div>
                ),
              },
              {
                title: '來源',
                width: 90,
                render: (_, t) => (t.source === 'ai' ? <Tag color="purple">AI</Tag> : <Tag>上傳</Tag>),
              },
              { title: '長度', width: 80, render: (_, t) => formatDuration(t.duration) },
              { title: '加入時間', width: 110, render: (_, t) => dayjs(t.created_at).format('MM/DD HH:mm') },
              {
                title: '自動挑選',
                width: 90,
                render: (_, t) => (
                  <Switch
                    size="small"
                    checked={t.is_active}
                    disabled={t.status !== 'ready'}
                    onChange={(is_active) => update.mutate({ id: t.id, body: { is_active } })}
                  />
                ),
              },
              {
                title: '',
                width: 56,
                render: (_, t) => (
                  <Popconfirm title="刪除這首音樂？" okText="刪除" okButtonProps={{ danger: true }} onConfirm={() => remove.mutate(t.id)}>
                    <Button type="text" danger icon={<DeleteOutlined />} aria-label="刪除" disabled={t.status === 'generating'} />
                  </Popconfirm>
                ),
              },
            ]}
          />
        ) : null}
      </Card>
    </>
  )
}
