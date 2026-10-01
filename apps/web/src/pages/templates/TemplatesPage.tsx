import { CopyOutlined, DeleteOutlined, EditOutlined, EyeOutlined, PlusOutlined, ThunderboltOutlined } from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { App, Button, Card, Col, Popconfirm, Row, Segmented, Space, Tabs, Tag, Typography } from 'antd'
import { useState } from 'react'
import { api, STRATEGY_LABELS, type Strategy, type Template } from '../../api'
import { ApiError } from '../../api/http'
import PageHeader from '../../components/PageHeader'
import GenerateModal from './GenerateModal'
import ScriptsPanel from './ScriptsPanel'
import TemplateDrawer from './TemplateDrawer'

function errorText(error: unknown) {
  return error instanceof ApiError ? error.message : '操作失敗'
}

export default function TemplatesPage() {
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const { data, isPending } = useQuery({ queryKey: ['templates'], queryFn: api.templates })
  const [tab, setTab] = useState<'templates' | 'scripts'>('templates')
  const [strategy, setStrategy] = useState<Strategy | 'all'>('all')
  const [viewing, setViewing] = useState<Template | 'new' | null>(null)
  const [generating, setGenerating] = useState<Template | null>(null)
  const [scriptTemplate, setScriptTemplate] = useState<string | undefined>()

  const refresh = () => queryClient.invalidateQueries({ queryKey: ['templates'] })
  const copy = useMutation({
    mutationFn: (id: string) => api.copyTemplate(id),
    onSuccess: (template) => {
      message.success('已複製為自訂模板，可以修改了')
      void refresh()
      setViewing(template)
    },
    onError: (e) => message.error(errorText(e)),
  })
  const remove = useMutation({
    mutationFn: (id: string) => api.deleteTemplate(id),
    onSuccess: () => {
      message.success('模板已刪除')
      void refresh()
    },
    onError: (e) => message.error(errorText(e)),
  })

  const templates = (data?.items ?? []).filter((t) => strategy === 'all' || t.strategy === strategy)

  return (
    <>
      <PageHeader
        title="模板文案"
        subtitle="選一個模板 + 帳號檔案，AI 依每個鏡頭寫好配音稿與畫面字幕，一次產生多個不重複的版本"
      />
      <Tabs
        activeKey={tab}
        onChange={(key) => setTab(key as 'templates' | 'scripts')}
        items={[
          {
            key: 'templates',
            label: '模板',
            children: (
              <>
                <div className="asset-filters section">
                  <Segmented
                    value={strategy}
                    onChange={(v) => setStrategy(v as Strategy | 'all')}
                    options={[
                      { value: 'all', label: '全部' },
                      ...(Object.keys(STRATEGY_LABELS) as Strategy[]).map((key) => ({
                        value: key,
                        label: STRATEGY_LABELS[key].label,
                      })),
                    ]}
                  />
                  <Button icon={<PlusOutlined />} onClick={() => setViewing('new')}>
                    自訂模板
                  </Button>
                </div>
                <Row gutter={[16, 16]}>
                  {templates.map((template) => (
                    <Col key={template.id} xs={24} md={12} xl={8}>
                      <Card
                        className="template-card"
                        title={template.name}
                        extra={
                          <Tag color={STRATEGY_LABELS[template.strategy].color}>
                            {STRATEGY_LABELS[template.strategy].label}
                          </Tag>
                        }
                        actions={[
                          <Button
                            key="gen"
                            type="link"
                            icon={<ThunderboltOutlined />}
                            onClick={() => setGenerating(template)}
                          >
                            產生文案
                          </Button>,
                          <Button
                            key="view"
                            type="link"
                            icon={template.builtin ? <EyeOutlined /> : <EditOutlined />}
                            onClick={() => setViewing(template)}
                          >
                            {template.builtin ? '查看' : '編輯'}
                          </Button>,
                          template.builtin ? (
                            <Button key="copy" type="link" icon={<CopyOutlined />} onClick={() => copy.mutate(template.id)}>
                              複製
                            </Button>
                          ) : (
                            <Popconfirm
                              key="del"
                              title="刪除這個模板？"
                              description="已產生的文案會保留。"
                              okText="刪除"
                              okButtonProps={{ danger: true }}
                              onConfirm={() => remove.mutate(template.id)}
                            >
                              <Button type="link" danger icon={<DeleteOutlined />}>
                                刪除
                              </Button>
                            </Popconfirm>
                          ),
                        ]}
                      >
                        <Typography.Paragraph type="secondary" ellipsis={{ rows: 2 }} className="template-desc">
                          {template.description || '（沒有說明）'}
                        </Typography.Paragraph>
                        <Space size={4} wrap>
                          {template.builtin ? <Tag>內建</Tag> : <Tag color="blue">自訂</Tag>}
                          <Tag>{template.shots.length} 個鏡頭</Tag>
                          <Tag>約 {Math.round(template.total_seconds)} 秒</Tag>
                          {template.script_count ? (
                            <Tag
                              color="green"
                              className="clickable"
                              onClick={() => {
                                setScriptTemplate(template.id)
                                setTab('scripts')
                              }}
                            >
                              {template.script_count} 份文案
                            </Tag>
                          ) : null}
                        </Space>
                      </Card>
                    </Col>
                  ))}
                  {isPending
                    ? Array.from({ length: 6 }, (_, i) => (
                        <Col key={i} xs={24} md={12} xl={8}>
                          <Card loading />
                        </Col>
                      ))
                    : null}
                </Row>
              </>
            ),
          },
          {
            key: 'scripts',
            label: '文案',
            children: (
              <ScriptsPanel
                templates={data?.items ?? []}
                templateId={scriptTemplate}
                onTemplateChange={setScriptTemplate}
              />
            ),
          },
        ]}
      />
      <TemplateDrawer
        target={viewing}
        onClose={() => setViewing(null)}
        onCopy={(t) => copy.mutate(t.id)}
        onGenerate={(t) => {
          setViewing(null)
          setGenerating(t)
        }}
      />
      <GenerateModal
        template={generating}
        onClose={() => setGenerating(null)}
        onStarted={(templateId) => {
          setGenerating(null)
          setScriptTemplate(templateId)
          setTab('scripts')
          void refresh()
        }}
      />
    </>
  )
}
