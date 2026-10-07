/** USD 顯示保留小額成本；缺少價格與真實 0 分開處理。 */
export function formatUsd(value: number | null | undefined): string {
  if (value == null) return '未設定價格'
  if (value === 0) return '$0.00'
  if (value > 0 && value < 0.0001) return '<$0.0001'
  return `$${value.toFixed(Math.abs(value) < 0.01 ? 4 : 2)}`
}

export const USAGE_STATUS = {
  succeeded: { label: '成功', color: 'green' },
  failed: { label: '失敗', color: 'red' },
  pending: { label: '處理中', color: 'blue' },
  uncertain: { label: '回執待核對', color: 'orange' },
} as const

export function failureRate(calls: number, failed: number): number | null {
  return calls > 0 ? (failed / calls) * 100 : null
}

export function highFailure(calls: number, failed: number): boolean {
  return calls >= 20 && failed / calls >= 0.2
}
