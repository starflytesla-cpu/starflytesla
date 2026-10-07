import { LockOutlined, MailOutlined } from '@ant-design/icons'
import { useQueryClient } from '@tanstack/react-query'
import { Alert, Button, Card, Form, Input } from 'antd'
import { useState } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router'
import { api } from '../api'
import { ApiError } from '../api/http'
import { useMe } from '../useMe'

export default function LoginPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const queryClient = useQueryClient()
  const { data: me } = useMe()
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const from = (location.state as { from?: string } | null)?.from ?? '/'

  if (me) return <Navigate to={from} replace />

  const submit = async (values: { email: string; password: string }) => {
    setLoading(true)
    setError('')
    try {
      const user = await api.login(values.email.trim(), values.password)
      queryClient.setQueryData(['me'], user)
      navigate(from, { replace: true })
    } catch (e) {
      setError(e instanceof ApiError ? e.message : '登入失敗')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-page">
      <Card className="login-card">
        <div className="login-brand">
          <div className="brand-logo large">SF</div>
          <h1>Starfly 混剪矩陣</h1>
          <p>工廠短影音自動化平台</p>
        </div>
        {error ? <Alert type="error" title={error} showIcon className="login-alert" /> : null}
        <Form layout="vertical" onFinish={submit} requiredMark={false} size="large">
          <Form.Item name="email" rules={[{ required: true, type: 'email', message: '請輸入正確的 Email' }]}>
            <Input
              aria-label="Email"
              prefix={<MailOutlined />}
              placeholder="Email"
              autoComplete="username"
              inputMode="email"
            />
          </Form.Item>
          <Form.Item name="password" rules={[{ required: true, message: '請輸入密碼' }]}>
            <Input.Password
              aria-label="密碼"
              prefix={<LockOutlined />}
              placeholder="密碼"
              autoComplete="current-password"
            />
          </Form.Item>
          <Button type="primary" htmlType="submit" block loading={loading}>
            登入
          </Button>
        </Form>
      </Card>
    </div>
  )
}
