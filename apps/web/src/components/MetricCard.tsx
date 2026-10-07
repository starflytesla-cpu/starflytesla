import { Card, Statistic } from 'antd'
import type { ReactNode } from 'react'

export default function MetricCard({
  title,
  value,
  note,
  loading,
  onClick,
  danger,
}: {
  title: string
  value: string | number | undefined
  note?: ReactNode
  loading?: boolean
  onClick?: () => void
  danger?: boolean
}) {
  return (
    <Card loading={loading} className="metric-card">
      {onClick ? (
        <button type="button" className="metric-link" onClick={onClick}>
          <Statistic
            title={title}
            value={value ?? '—'}
            styles={danger ? { content: { color: '#cf1322' } } : undefined}
          />
        </button>
      ) : (
        <Statistic title={title} value={value ?? '—'} styles={danger ? { content: { color: '#cf1322' } } : undefined} />
      )}
      {note ? <div className="metric-note">{note}</div> : null}
    </Card>
  )
}
