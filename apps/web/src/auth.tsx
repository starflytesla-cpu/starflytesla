import { Spin } from 'antd'
import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router'
import { useMe } from './useMe'

export function RequireAuth({ children }: { children: ReactNode }) {
  const { data, isPending, error } = useMe()
  const location = useLocation()
  if (isPending) {
    return (
      <div className="center-screen">
        <Spin size="large" />
      </div>
    )
  }
  if (error || !data) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }
  return children
}

export function AdminOnly({ children }: { children: ReactNode }) {
  const { data } = useMe()
  if (data?.role !== 'admin') return <Navigate to="/" replace />
  return children
}
