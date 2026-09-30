import { EditOutlined, PlusOutlined } from '@ant-design/icons'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { App, Button, Card, Form, Input, Modal, Select, Switch, Table, Tag } from 'antd'
import dayjs from 'dayjs'
import { useState } from 'react'
import { api, type Role, type User } from '../api'
import { ApiError } from '../api/http'
import { useMe } from '../useMe'
import PageHeader from '../components/PageHeader'

const ROLE_OPTIONS = [
  { value: 'admin', label: '管理員（全部功能）' },
  { value: 'shooter', label: '拍攝員（只能上傳素材）' },
]

interface FormValues {
  email: string
  display_name: string
  password?: string
  role: Role
}

export default function UsersPage() {
  const { data: me } = useMe()
  const queryClient = useQueryClient()
  const { message } = App.useApp()
  const { data, isPending } = useQuery({ queryKey: ['users'], queryFn: api.users })
  const [target, setTarget] = useState<User | 'new' | null>(null)
  const [form] = Form.useForm<FormValues>()
  const [saving, setSaving] = useState(false)

  const refresh = () => queryClient.invalidateQueries({ queryKey: ['users'] })

  const toggleActive = async (user: User, is_active: boolean) => {
    try {
      await api.updateUser(user.id, { is_active })
      message.success(is_active ? '帳號已啟用' : '帳號已停用，該帳號會立即被登出')
      refresh()
    } catch (error) {
      message.error(error instanceof ApiError ? error.message : '操作失敗')
    }
  }

  const submit = async () => {
    const values = await form.validateFields()
    setSaving(true)
    try {
      if (target === 'new') {
        await api.createUser({ ...values, password: values.password ?? '' })
        message.success('帳號已建立，請把 Email 和密碼交給使用者')
      } else if (target) {
        await api.updateUser(target.id, {
          display_name: values.display_name,
          role: values.role,
          ...(values.password ? { password: values.password } : {}),
        })
        message.success('已更新')
      }
      refresh()
      setTarget(null)
    } catch (error) {
      message.error(error instanceof ApiError ? error.message : '儲存失敗')
    } finally {
      setSaving(false)
    }
  }

  const isNew = target === 'new'

  return (
    <>
      <PageHeader
        title="帳號管理"
        subtitle="建立工廠拍攝員的帳號，讓他們用手機登入上傳素材。"
        extra={
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setTarget('new')}>
            新增帳號
          </Button>
        }
      />
      <Card>
        <Table<User>
          rowKey="id"
          loading={isPending}
          dataSource={data ?? []}
          pagination={false}
          scroll={{ x: 720 }}
          columns={[
            { title: '名稱', dataIndex: 'display_name' },
            { title: 'Email', dataIndex: 'email' },
            {
              title: '角色',
              dataIndex: 'role',
              render: (role: Role) => (role === 'admin' ? <Tag color="blue">管理員</Tag> : <Tag>拍攝員</Tag>),
            },
            {
              title: '最後登入',
              dataIndex: 'last_login_at',
              render: (v: string | null) => (v ? dayjs(v).format('YYYY-MM-DD HH:mm') : '從未登入'),
            },
            {
              title: '啟用',
              render: (_, u) => (
                <Switch checked={u.is_active} disabled={u.id === me?.id} onChange={(v) => toggleActive(u, v)} />
              ),
            },
            {
              title: '操作',
              render: (_, u) => (
                <Button size="small" icon={<EditOutlined />} onClick={() => setTarget(u)}>
                  編輯
                </Button>
              ),
            },
          ]}
        />
      </Card>
      <Modal
        title={isNew ? '新增帳號' : '編輯帳號'}
        open={!!target}
        onCancel={() => setTarget(null)}
        onOk={submit}
        okText="儲存"
        confirmLoading={saving}
        destroyOnHidden
      >
        {target ? (
          <Form
            form={form}
            layout="vertical"
            requiredMark={false}
            initialValues={isNew ? { role: 'shooter' } : { email: target.email, display_name: target.display_name, role: target.role }}
          >
            <Form.Item name="email" label="Email（登入帳號）" rules={[{ required: true, type: 'email', message: '請輸入正確的 Email' }]}>
              <Input disabled={!isNew} autoComplete="off" />
            </Form.Item>
            <Form.Item name="display_name" label="名稱" rules={[{ required: true, message: '請輸入名稱' }]}>
              <Input placeholder="例如：王師傅" />
            </Form.Item>
            <Form.Item name="role" label="角色">
              <Select options={ROLE_OPTIONS} />
            </Form.Item>
            <Form.Item
              name="password"
              label={isNew ? '密碼' : '重設密碼'}
              extra={isNew ? '至少 8 個字元' : '留空代表不修改；重設後該帳號會被登出'}
              rules={isNew ? [{ required: true, min: 8, message: '密碼至少 8 個字元' }] : [{ min: 8, message: '密碼至少 8 個字元' }]}
            >
              <Input.Password autoComplete="new-password" />
            </Form.Item>
          </Form>
        ) : null}
      </Modal>
    </>
  )
}
