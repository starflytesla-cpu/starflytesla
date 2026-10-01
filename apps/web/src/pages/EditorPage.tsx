import { VideoCameraAddOutlined, WarningOutlined } from '@ant-design/icons'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Alert, App, Button, Card, Col, Empty, Form, Row, Select, Slider, Space, Table, Tag, Tooltip, Typography } from 'antd'
import { useState } from 'react'
import { useNavigate } from 'react-router'
import { api, SCENE_LABELS, type Script } from '../api'
import { ApiError } from '../api/http'
import PageHeader from '../components/PageHeader'

interface Options {
  per_script: number
  style: string
  ambience: number
  bgm: string
  bgm_volume: number
}

export default function EditorPage() {
  const { message } = App.useApp()
  const navigate = useNavigate()
  const [selected, setSelected] = useState<string[]>([])
  const [form] = Form.useForm<Options>()
  const perScript = Form.useWatch('per_script', form) ?? 2

  const { data, isPending } = useQuery({
    queryKey: ['scripts', 'approved-all'],
    queryFn: () => api.scripts({ status: 'approved', limit: 100, offset: 0 }),
  })
  const { data: styles } = useQuery({ queryKey: ['video-styles'], queryFn: api.videoStyles, staleTime: Infinity })
  const { data: musicData } = useQuery({ queryKey: ['music'], queryFn: api.music })
  const readyMusic = (musicData?.items ?? []).filter((t) => t.status === 'ready')
  const bgm = Form.useWatch('bgm', form) ?? 'auto'
  const { data: coverage } = useQuery({
    queryKey: ['coverage', selected],
    queryFn: () => api.videoCoverage(selected),
  })

  const generate = useMutation({
    mutationFn: (values: Options) => api.generateVideos({ script_ids: selected, ...values }),
    onSuccess: (videos) => {
      message.success(`已排入 ${videos.length} 支成片，完成後會出現在作品庫的「待審」`)
      navigate('/works')
    },
    onError: (e) => message.error(e instanceof ApiError ? e.message : '無法開始產生'),
  })

  const missing = (script: Script) => {
    const info = coverage?.scripts.find((s) => s.id === script.id)
    return (info?.shots ?? []).map((s, i) => ({ ...s, index: i + 1 })).filter((s) => s.scene && s.clips === 0)
  }

  return (
    <>
      <PageHeader
        title="鏡頭剪輯"
        subtitle="選擇已核准的文案，系統自動挑素材、配音、上字幕，批量產生 1080×1920 直式成片，完成後到作品庫審核"
      />
      {coverage && !coverage.tts_ready ? (
        <Alert
          className="section"
          type="warning"
          showIcon
          title="尚未設定配音模型"
          description="請到「模型渠道」確認 kie.ai 渠道有 ElevenLabs 配音模型並已啟用。"
        />
      ) : null}
      {coverage && coverage.total_clips === 0 ? (
        <Alert
          className="section"
          type="warning"
          showIcon
          title="素材庫還沒有可用的鏡頭"
          description="請先到「素材中心」上傳影片，等分析完成後再產生成片。"
          action={<Button onClick={() => navigate('/assets')}>前往素材中心</Button>}
        />
      ) : null}

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={16}>
          <Card title="1. 選擇文案（只列出已核准的）" className="section">
            {data && data.items.length === 0 ? (
              <Empty description="還沒有已核准的文案。到「模板文案」產生文案並按「核准」。">
                <Button onClick={() => navigate('/templates')}>前往模板文案</Button>
              </Empty>
            ) : (
              <Table<Script>
                rowKey="id"
                size="small"
                loading={isPending}
                dataSource={data?.items ?? []}
                pagination={false}
                scroll={{ x: 640 }}
                rowSelection={{ selectedRowKeys: selected, onChange: (keys) => setSelected(keys as string[]) }}
                columns={[
                  {
                    title: '文案',
                    render: (_, s) => (
                      <Space orientation="vertical" size={0}>
                        <Typography.Text strong>{s.title || `版本 ${s.variant}`}</Typography.Text>
                        <Typography.Text type="secondary" className="small" ellipsis>
                          {s.hook}
                        </Typography.Text>
                      </Space>
                    ),
                  },
                  { title: '模板', dataIndex: 'template_name', width: 180 },
                  { title: '帳號檔案', dataIndex: 'profile_name', width: 140 },
                  { title: '語言', dataIndex: 'language', width: 70 },
                  {
                    title: '素材',
                    width: 90,
                    render: (_, s) => {
                      if (!selected.includes(s.id) || !coverage) return null
                      const lacks = missing(s)
                      return lacks.length ? (
                        <Tooltip
                          title={`這些鏡頭找不到同類型素材，會用其他畫面代替：${lacks
                            .map((m) => `鏡頭 ${m.index}（${SCENE_LABELS[m.scene] ?? m.scene}）`)
                            .join('、')}`}
                        >
                          <Tag color="orange" icon={<WarningOutlined />}>
                            缺 {lacks.length}
                          </Tag>
                        </Tooltip>
                      ) : (
                        <Tag color="green">充足</Tag>
                      )
                    },
                  },
                ]}
              />
            )}
          </Card>
        </Col>
        <Col xs={24} xl={8}>
          <Card title="2. 產生設定">
            <Form
              form={form}
              layout="vertical"
              initialValues={{ per_script: 2, style: 'random', ambience: 0, bgm: 'auto', bgm_volume: 0.22 }}
              onFinish={(values) => generate.mutate(values)}
            >
              <Form.Item name="per_script" label="每份文案產生幾支" extra="同一份文案的多支成片，會挑不同素材、字幕樣式，適合分給不同帳號">
                <Slider min={1} max={5} marks={{ 1: '1', 3: '3', 5: '5' }} />
              </Form.Item>
              <Form.Item name="style" label="字幕樣式">
                <Select
                  options={[
                    { value: 'random', label: '每支隨機（建議，避免矩陣號重複）' },
                    ...Object.entries(styles ?? {}).map(([value, label]) => ({ value, label })),
                  ]}
                />
              </Form.Item>
              <Form.Item
                name="bgm"
                label="背景音樂"
                extra={
                  readyMusic.length === 0 ? (
                    <span>
                      音樂庫是空的，成片會沒有背景音樂。<a onClick={() => navigate('/music')}>前往新增音樂</a>
                    </span>
                  ) : (
                    '整支成片使用同一首，配音時自動壓低'
                  )
                }
              >
                <Select
                  options={[
                    { value: 'auto', label: '每支自動隨機（建議）' },
                    { value: 'none', label: '不使用背景音樂' },
                    ...readyMusic.map((t) => ({ value: t.id, label: `固定：${t.title}` })),
                  ]}
                />
              </Form.Item>
              {bgm !== 'none' ? (
                <Form.Item name="bgm_volume" label="背景音樂音量">
                  <Slider min={0.05} max={0.5} step={0.01} marks={{ 0.05: '小', 0.22: '建議', 0.5: '大' }} />
                </Form.Item>
              ) : null}
              <Form.Item
                name="ambience"
                label="素材現場原聲"
                extra="各段影片的現場聲音大小不一，建議保持 0；想保留一點機台聲可以調到 0.05～0.1"
              >
                <Slider min={0} max={0.3} step={0.01} marks={{ 0: '關閉', 0.1: '小', 0.3: '大' }} />
              </Form.Item>
              <Button
                type="primary"
                size="large"
                block
                icon={<VideoCameraAddOutlined />}
                disabled={selected.length === 0}
                loading={generate.isPending}
                onClick={() => form.submit()}
              >
                {selected.length ? `產生 ${selected.length * perScript} 支成片` : '請先選擇文案'}
              </Button>
              <Typography.Paragraph type="secondary" className="small editor-note">
                每支約 1～3 分鐘。配音會使用 kie.ai 點數（同樣的文案與音色只扣一次）；渲染在自己的伺服器上，不另外收費。
              </Typography.Paragraph>
            </Form>
          </Card>
        </Col>
      </Row>
    </>
  )
}
