import { Alert, Button } from 'antd'
import { errorText } from '../api/http'

/** 查詢失敗留在頁面，已有資料時明確標示為上次結果。 */
export default function QueryFeedback({
  error,
  retry,
  stale = false,
}: {
  error: unknown
  retry: () => unknown
  stale?: boolean
}) {
  if (!error) return null
  return (
    <Alert
      className="section"
      type="error"
      showIcon
      title={stale ? '更新失敗，目前顯示上次資料' : '資料讀取失敗'}
      description={errorText(error)}
      action={
        <Button
          onClick={() => {
            void retry()
          }}
        >
          重試
        </Button>
      }
    />
  )
}
