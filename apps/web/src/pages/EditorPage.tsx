import { VideoCameraAddOutlined, WarningOutlined } from '@ant-design/icons'
import { useMutation, useQuery } from '@tanstack/react-query'
import {
  Alert,
  App,
  Button,
  Card,
  Checkbox,
  Col,
  Collapse,
  Empty,
  Form,
  Grid,
  Row,
  Select,
  Slider,
  Space,
  Statistic,
  Steps,
  Table,
  Tag,
  Tooltip,
  Typography,
} from 'antd'
import { useState } from 'react'
import { useNavigate } from 'react-router'
import { api, SCENE_LABELS, type Script } from '../api'
import { ApiError } from '../api/http'
import PageHeader from '../components/PageHeader'
import QueryFeedback from '../components/QueryFeedback'

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
  const screens = Grid.useBreakpoint()
  const [selected, setSelected] = useState<string[]>([])
  const [form] = Form.useForm<Options>()
  const perScript = Form.useWatch('per_script', form) ?? 2

  const { data, isPending, error, refetch } = useQuery({
    queryKey: ['scripts', 'approved-all'],
    queryFn: () => api.scripts({ status: 'approved', limit: 100, offset: 0 }),
  })
  const {
    data: styles,
    error: stylesError,
    refetch: refetchStyles,
  } = useQuery({
    queryKey: ['video-styles'],
    queryFn: api.videoStyles,
    staleTime: Infinity,
  })
  const {
    data: musicData,
    error: musicError,
    refetch: refetchMusic,
  } = useQuery({ queryKey: ['music'], queryFn: api.music })
  const readyMusic = (musicData?.items ?? []).filter((t) => t.status === 'ready')
  const bgm = Form.useWatch('bgm', form) ?? 'auto'
  const {
    data: coverage,
    error: coverageError,
    refetch: refetchCoverage,
  } = useQuery({
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
      {screens.md ? (
        <Steps
          className="section"
          size="small"
          current={selected.length ? 1 : 0}
          items={[{ title: '選擇文案' }, { title: '檢查素材' }, { title: '字幕與聲音' }, { title: '確認批次' }]}
        />
      ) : (
        <div className="scope-bar section">
          <Tag color="blue">步驟 {selected.length ? 2 : 1} / 4</Tag>
          <span>{selected.length ? '檢查素材 → 設定 → 確認批次' : '選文案 → 素材 → 設定 → 確認'}</span>
        </div>
      )}
      <QueryFeedback
        error={error || coverageError || stylesError || musicError}
        retry={() => Promise.all([refetch(), refetchCoverage(), refetchStyles(), refetchMusic()])}
      />
      {coverage && !coverage.tts_ready ? (
        <Alert
          className="section"
          type="warning"
          showIcon
          title="尚未設定配音模型"
          description="請到「模型渠道」確認預設配音模型已啟用。"
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
          <Card
            title="1. 選擇已核准文案"
            extra={<span className="small muted">最近 100 份 · 已選 {selected.length}</span>}
            className="section"
          >
            {data && data.items.length === 0 ? (
              <Empty description="還沒有已核准的文案。到「模板文案」產生文案並按「核准」。">
                <Button onClick={() => navigate('/templates')}>前往模板文案</Button>
              </Empty>
            ) : !screens.md ? (
              <div className="record-list">
                {data?.items.map((script) => (
                  <div key={script.id} className="compact-record">
                    <Checkbox
                      checked={selected.includes(script.id)}
                      onChange={(e) =>
                        setSelected((ids) =>
                          e.target.checked ? [...ids, script.id] : ids.filter((id) => id !== script.id),
                        )
                      }
                    >
                      {script.title || `版本 ${script.variant}`}
                    </Checkbox>
                    <span className="small muted">
                      {script.profile_name} · {script.language} · {script.template_name}
                    </span>
                    <span>{script.hook}</span>
                  </div>
                ))}
              </div>
            ) : (
              <Table<Script>
                rowKey="id"
                size="small"
                loading={isPending}
                dataSource={data?.items ?? []}
                pagination={false}
                scroll={{ x: 640 }}
                rowSelection={{
                  selectedRowKeys: selected,
                  onChange: (keys) => setSelected(keys as string[]),
                }}
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
          <Card title="2. 檢查素材覆蓋">
            {!selected.length ? (
              <p className="muted">選取文案後，逐鏡頭核對可用素材。</p>
            ) : (
              data?.items
                .filter((script) => selected.includes(script.id))
                .map((script) => (
                  <div key={script.id} className="section">
                    <strong>{script.title}</strong>
                    {coverage?.scripts.find((item) => item.id === script.id) ? (
                      <div className="profile-tags" style={{ marginTop: 8 }}>
                        {coverage.scripts
                          .find((item) => item.id === script.id)!
                          .shots.map((shot, i) => (
                            <Tag key={i} color={shot.clips ? 'green' : 'orange'}>
                              鏡頭 {i + 1} · {SCENE_LABELS[shot.scene] ?? shot.scene} · {shot.clips} 段
                            </Tag>
                          ))}
                      </div>
                    ) : (
                      <p className="muted">尚未取得覆蓋資料</p>
                    )}
                    {missing(script).length ? (
                      <Alert type="warning" showIcon title="缺少同類型素材，會使用其他畫面代替" />
                    ) : null}
                  </div>
                ))
            )}
          </Card>
        </Col>
        <Col xs={24} xl={8}>
          <Card title="3. 字幕與聲音" className="editor-summary">
            <Form
              form={form}
              layout="vertical"
              initialValues={{
                per_script: 2,
                style: 'random',
                ambience: 0,
                bgm: 'auto',
                bgm_volume: 0.22,
              }}
              onFinish={(values) => generate.mutate(values)}
            >
              <Form.Item
                name="per_script"
                label="每份文案產生幾支"
                extra="同一份文案的多支成片，會挑不同素材、字幕樣式，適合分給不同帳號"
              >
                <Slider min={1} max={5} marks={{ 1: '1', 3: '3', 5: '5' }} />
              </Form.Item>
              <Form.Item name="style" label="字幕樣式">
                <Select
                  options={[
                    {
                      value: 'random',
                      label: '每支隨機（建議，避免矩陣號重複）',
                    },
                    ...Object.entries(styles ?? {}).map(([value, label]) => ({
                      value,
                      label,
                    })),
                  ]}
                />
              </Form.Item>
              <Form.Item
                name="bgm"
                label="背景音樂"
                extra={
                  readyMusic.length === 0 ? (
                    <span>
                      音樂庫是空的，成片會沒有背景音樂。
                      <a onClick={() => navigate('/music')}>前往新增音樂</a>
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
                    ...readyMusic.map((t) => ({
                      value: t.id,
                      label: `固定：${t.title}`,
                    })),
                  ]}
                />
              </Form.Item>
              {bgm !== 'none' ? (
                <Form.Item name="bgm_volume" label="背景音樂音量">
                  <Slider min={0.05} max={0.5} step={0.01} marks={{ 0.05: '小', 0.22: '建議', 0.5: '大' }} />
                </Form.Item>
              ) : null}
              <Collapse
                className="section"
                items={[
                  {
                    key: 'ambience',
                    label: '進階：素材現場原聲',
                    forceRender: true,
                    children: (
                      <Form.Item
                        name="ambience"
                        label="素材現場原聲"
                        extra="各段影片的現場聲音大小不一，建議保持 0；想保留一點機台聲可以調到 0.05～0.1"
                      >
                        <Slider min={0} max={0.3} step={0.01} marks={{ 0: '關閉', 0.1: '小', 0.3: '大' }} />
                      </Form.Item>
                    ),
                  },
                ]}
              />
              <div className="publish-summary">
                <Typography.Title level={5}>4. 確認批次</Typography.Title>
                <Statistic title="本次預計成片" value={selected.length * perScript} suffix="支" />
                <p>
                  {selected.length} 份文案 × 每份 {perScript} 支版本
                </p>
                <p className="small muted">提交後開始配音與渲染，完成後仍需人工審核。</p>
              </div>
              {generate.error ? (
                <Alert
                  className="section"
                  type="error"
                  showIcon
                  title={generate.error instanceof ApiError ? generate.error.message : '無法開始產生'}
                />
              ) : null}
              <Button
                type="primary"
                size="large"
                block
                icon={<VideoCameraAddOutlined />}
                disabled={
                  selected.length === 0 || !coverage || !!coverageError || !!error || !!musicError || !!stylesError
                }
                loading={generate.isPending}
                onClick={() => form.submit()}
              >
                {selected.length ? `確認並產生 ${selected.length * perScript} 支成片` : '請先選擇文案'}
              </Button>
              <Typography.Paragraph type="secondary" className="small editor-note">
                每支約 1～3 分鐘。配音依模型渠道計費（相同文案與音色沿用快取）；渲染在自己的伺服器上。
              </Typography.Paragraph>
            </Form>
          </Card>
        </Col>
      </Row>
    </>
  )
}
