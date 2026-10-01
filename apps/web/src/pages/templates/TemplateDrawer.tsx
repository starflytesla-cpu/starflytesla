import { ArrowDownOutlined, ArrowUpOutlined, CopyOutlined, DeleteOutlined, PlusOutlined, ThunderboltOutlined } from '@ant-design/icons'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Alert, App, Button, Drawer, Form, Grid, Input, InputNumber, Radio, Select, Space, Tag, Typography } from 'antd'
import { api, SCENE_LABELS, STRATEGY_LABELS, type Strategy, type Template, type TemplateInput } from '../../api'
import { ApiError } from '../../api/http'

const SCENE_OPTIONS = Object.entries(SCENE_LABELS).map(([value, label]) => ({ value, label }))

export default function TemplateDrawer({
  target,
  onClose,
  onCopy,
  onGenerate,
}: {
  target: Template | 'new' | null
  onClose: () => void
  onCopy: (template: Template) => void
  onGenerate: (template: Template) => void
}) {
  const screens = Grid.useBreakpoint()
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const [form] = Form.useForm<TemplateInput>()
  const template = target === 'new' ? null : target
  const readOnly = !!template?.builtin

  const save = useMutation({
    mutationFn: (values: TemplateInput) => (template ? api.updateTemplate(template.id, values) : api.createTemplate(values)),
    onSuccess: () => {
      message.success('已儲存')
      void queryClient.invalidateQueries({ queryKey: ['templates'] })
      onClose()
    },
    onError: (e) => message.error(e instanceof ApiError ? e.message : '儲存失敗'),
  })

  const initial: TemplateInput = template ?? {
    strategy: 'persona',
    shots: [{ brief: '開場鉤子：', scene: 'workshop', seconds: 3 }],
  }

  return (
    <Drawer
      open={!!target}
      onClose={onClose}
      size={screens.md ? 720 : '100%'}
      title={template ? template.name : '新增自訂模板'}
      destroyOnHidden
      extra={
        readOnly && template ? (
          <Space>
            <Button icon={<CopyOutlined />} onClick={() => onCopy(template)}>
              複製後修改
            </Button>
            <Button type="primary" icon={<ThunderboltOutlined />} onClick={() => onGenerate(template)}>
              產生文案
            </Button>
          </Space>
        ) : (
          <Button type="primary" loading={save.isPending} onClick={() => form.submit()}>
            儲存
          </Button>
        )
      }
    >
      {readOnly && template ? (
        <>
          <Alert className="section" type="info" showIcon title="內建模板不能直接修改，按「複製後修改」就能調整鏡頭。" />
          <Typography.Paragraph type="secondary">{template.description}</Typography.Paragraph>
          <div className="shot-list">
            {template.shots.map((shot, index) => (
              <div key={index} className="shot-row">
                <span className="shot-index">{index + 1}</span>
                <div className="shot-body">
                  <div>{shot.brief}</div>
                  <Space size={4}>
                    {shot.scene ? <Tag color="blue">{SCENE_LABELS[shot.scene] ?? shot.scene}</Tag> : null}
                    <Tag>{shot.seconds} 秒</Tag>
                  </Space>
                </div>
              </div>
            ))}
          </div>
        </>
      ) : (
        <Form form={form} layout="vertical" initialValues={initial} onFinish={(values) => save.mutate(values)}>
          <Form.Item name="name" label="模板名稱" rules={[{ required: true, message: '請填寫名稱' }]}>
            <Input maxLength={80} />
          </Form.Item>
          <Form.Item name="strategy" label="類型">
            <Radio.Group
              optionType="button"
              options={(Object.keys(STRATEGY_LABELS) as Strategy[]).map((key) => ({
                value: key,
                label: STRATEGY_LABELS[key].label,
              }))}
            />
          </Form.Item>
          <Form.Item name="description" label="說明">
            <Input.TextArea maxLength={500} autoSize={{ minRows: 2, maxRows: 4 }} />
          </Form.Item>
          <Typography.Title level={5}>鏡頭</Typography.Title>
          <Typography.Paragraph type="secondary" className="small">
            每個鏡頭寫下要拍什麼、要說什麼重點（中文即可，AI 會用帳號檔案的語言改寫）。畫面類型會在混剪時用來挑素材。
          </Typography.Paragraph>
          <Form.List name="shots">
            {(fields, { add, remove, move }) => (
              <div className="shot-list">
                {fields.map((field, index) => (
                  <div key={field.key} className="shot-row editable">
                    <span className="shot-index">{index + 1}</span>
                    <div className="shot-body">
                      <Form.Item name={[field.name, 'brief']} rules={[{ required: true, message: '請填寫鏡頭重點' }]} className="shot-field">
                        <Input.TextArea maxLength={300} autoSize={{ minRows: 1, maxRows: 4 }} placeholder="這個鏡頭要拍什麼、說什麼" />
                      </Form.Item>
                      <Space wrap>
                        <Form.Item name={[field.name, 'scene']} className="shot-field">
                          <Select options={SCENE_OPTIONS} placeholder="畫面類型" allowClear className="shot-scene" />
                        </Form.Item>
                        <Form.Item name={[field.name, 'seconds']} className="shot-field">
                          <InputNumber min={1} max={30} step={0.5} suffix="秒" className="shot-seconds" />
                        </Form.Item>
                        <Button size="small" icon={<ArrowUpOutlined />} disabled={index === 0} onClick={() => move(index, index - 1)} aria-label="上移" />
                        <Button
                          size="small"
                          icon={<ArrowDownOutlined />}
                          disabled={index === fields.length - 1}
                          onClick={() => move(index, index + 1)}
                          aria-label="下移"
                        />
                        <Button size="small" danger icon={<DeleteOutlined />} disabled={fields.length === 1} onClick={() => remove(index)} aria-label="刪除鏡頭" />
                      </Space>
                    </div>
                  </div>
                ))}
                {fields.length < 12 ? (
                  <Button type="dashed" icon={<PlusOutlined />} onClick={() => add({ brief: '', scene: 'workshop', seconds: 4 })}>
                    新增鏡頭
                  </Button>
                ) : null}
              </div>
            )}
          </Form.List>
        </Form>
      )}
    </Drawer>
  )
}
