import { App, Form, Input, Modal } from 'antd'
import { useState } from 'react'
import { api } from '../api'
import { ApiError } from '../api/http'

interface Values {
  old_password: string
  new_password: string
  confirm: string
}

export default function ChangePasswordModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [form] = Form.useForm<Values>()
  const [saving, setSaving] = useState(false)
  const { message } = App.useApp()

  const submit = async () => {
    const values = await form.validateFields()
    setSaving(true)
    try {
      await api.changePassword(values.old_password, values.new_password)
      message.success('密碼已更新，其他裝置需要重新登入')
      form.resetFields()
      onClose()
    } catch (error) {
      message.error(error instanceof ApiError ? error.message : '更新失敗')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal title="修改密碼" open={open} onCancel={onClose} onOk={submit} confirmLoading={saving} okText="儲存" destroyOnHidden>
      <Form form={form} layout="vertical" requiredMark={false}>
        <Form.Item name="old_password" label="目前的密碼" rules={[{ required: true, message: '請輸入目前的密碼' }]}>
          <Input.Password autoComplete="current-password" />
        </Form.Item>
        <Form.Item
          name="new_password"
          label="新密碼"
          rules={[{ required: true, min: 8, message: '新密碼至少 8 個字元' }]}
        >
          <Input.Password autoComplete="new-password" />
        </Form.Item>
        <Form.Item
          name="confirm"
          label="再輸入一次新密碼"
          dependencies={['new_password']}
          rules={[
            { required: true, message: '請再輸入一次' },
            ({ getFieldValue }) => ({
              validator: (_, value) =>
                !value || value === getFieldValue('new_password')
                  ? Promise.resolve()
                  : Promise.reject(new Error('兩次輸入的密碼不一致')),
            }),
          ]}
        >
          <Input.Password autoComplete="new-password" />
        </Form.Item>
      </Form>
    </Modal>
  )
}
