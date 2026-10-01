import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, App, Button, Form, Modal, Select, Slider, Typography } from 'antd'
import { useNavigate } from 'react-router'
import { api, type Template } from '../../api'
import { ApiError } from '../../api/http'

export default function GenerateModal({
  template,
  onClose,
  onStarted,
}: {
  template: Template | null
  onClose: () => void
  onStarted: (templateId: string) => void
}) {
  const { message } = App.useApp()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [form] = Form.useForm<{ profile_id: string; variants: number }>()
  const { data: profileData } = useQuery({ queryKey: ['profiles'], queryFn: api.profiles, enabled: !!template })
  const profiles = profileData?.items ?? []

  const generate = useMutation({
    mutationFn: (values: { profile_id: string; variants: number }) =>
      api.generateScripts({ template_id: template!.id, ...values }),
    onSuccess: () => {
      message.success('已開始產生，約 30 秒～1 分鐘，完成後會自動顯示')
      void queryClient.invalidateQueries({ queryKey: ['scripts'] })
      onStarted(template!.id)
    },
  })

  return (
    <Modal
      open={!!template}
      title={template ? `產生文案：${template.name}` : ''}
      okText="開始產生"
      confirmLoading={generate.isPending}
      onOk={() => form.submit()}
      okButtonProps={{ disabled: profiles.length === 0 }}
      onCancel={() => {
        generate.reset()
        onClose()
      }}
      destroyOnHidden
    >
      {profileData && profiles.length === 0 ? (
        <Alert
          type="warning"
          showIcon
          className="section"
          title="還沒有帳號檔案"
          description="AI 需要知道品牌、賣點和語言才能寫文案。"
          action={
            <Button size="small" onClick={() => navigate('/profiles')}>
              去建立
            </Button>
          }
        />
      ) : null}
      <Form
        form={form}
        layout="vertical"
        initialValues={{ variants: 3 }}
        onFinish={(values) => generate.mutate(values)}
      >
        <Form.Item name="profile_id" label="帳號檔案" rules={[{ required: true, message: '請選擇帳號檔案' }]}>
          <Select
            placeholder="選擇要用哪一份人設"
            options={profiles.map((p) => ({ value: p.id, label: `${p.name}（${p.target_language}）` }))}
          />
        </Form.Item>
        <Form.Item name="variants" label="產生幾個版本" extra="每個版本的開場、角度、用詞都不同，適合分給帳號群裡不同的帳號">
          <Slider min={1} max={5} marks={{ 1: '1', 3: '3', 5: '5' }} />
        </Form.Item>
      </Form>
      <Typography.Text type="secondary" className="small">
        使用「模型渠道」裡預設的文字模型（DeepSeek），每次約花費 US$0.001～0.005。
      </Typography.Text>
      {generate.error ? (
        <Alert
          className="section"
          type="error"
          showIcon
          title={generate.error instanceof ApiError ? generate.error.message : '無法開始產生'}
        />
      ) : null}
    </Modal>
  )
}
