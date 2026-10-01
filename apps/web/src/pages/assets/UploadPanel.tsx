import {
  CameraOutlined,
  CheckCircleFilled,
  CloseOutlined,
  PauseOutlined,
  PictureOutlined,
  ReloadOutlined,
  CaretRightOutlined,
} from '@ant-design/icons'
import { useQueryClient } from '@tanstack/react-query'
import { App, Button, Card, Progress, Space, Typography } from 'antd'
import { useEffect, useRef, type ChangeEvent } from 'react'
import { formatBytes } from '../../api'
import { uploadStore, useUploads } from './uploadStore'

const ACCEPTED = /\.(mp4|mov|m4v|webm|mkv|avi|3gp|mts|jpe?g|png|webp)$/i

export default function UploadPanel() {
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const items = useUploads()
  const cameraInput = useRef<HTMLInputElement>(null)
  const fileInput = useRef<HTMLInputElement>(null)

  useEffect(() => {
    uploadStore.setOnFinished(() => {
      void queryClient.invalidateQueries({ queryKey: ['assets'] })
      void queryClient.invalidateQueries({ queryKey: ['asset-stats'] })
    })
  }, [queryClient])

  const onPick = (event: ChangeEvent<HTMLInputElement>) => {
    for (const file of Array.from(event.target.files ?? [])) {
      if (ACCEPTED.test(file.name)) uploadStore.add(file)
      else message.warning(`${file.name}：只支援影片（mp4、mov 等）與照片（jpg、png、webp）`)
    }
    event.target.value = '' // 允許再次選同一個檔案
  }

  const doneCount = items.filter((item) => item.state === 'done').length

  return (
    <Card className="section">
      <input ref={cameraInput} type="file" accept="video/*" capture="environment" hidden onChange={onPick} />
      <input
        ref={fileInput}
        type="file"
        accept="video/*,image/jpeg,image/png,image/webp"
        multiple
        hidden
        onChange={onPick}
      />
      <div className="upload-actions">
        <Button type="primary" size="large" icon={<CameraOutlined />} onClick={() => cameraInput.current?.click()}>
          拍攝影片
        </Button>
        <Button size="large" icon={<PictureOutlined />} onClick={() => fileInput.current?.click()}>
          從相簿 / 檔案選擇
        </Button>
        <Typography.Text type="secondary" className="small">
          可一次選多個檔案，單檔上限 2 GB。網路中斷會自動續傳；重新整理頁面後再選同一個檔案，會從中斷的地方繼續。
        </Typography.Text>
      </div>

      {items.length > 0 ? (
        <div className="upload-list">
          {items.map((item) => (
            <div key={item.key} className="upload-item">
              <div className="upload-item-head">
                <Typography.Text ellipsis className="upload-name">
                  {item.state === 'done' ? <CheckCircleFilled className="ok-icon" /> : null} {item.name}
                </Typography.Text>
                <Space size={4}>
                  {item.state === 'uploading' ? (
                    <Button size="small" type="text" icon={<PauseOutlined />} onClick={() => uploadStore.pause(item.key)} aria-label="暫停" />
                  ) : null}
                  {item.state === 'paused' ? (
                    <Button size="small" type="text" icon={<CaretRightOutlined />} onClick={() => uploadStore.resume(item.key)} aria-label="繼續" />
                  ) : null}
                  {item.state === 'error' ? (
                    <Button size="small" type="text" icon={<ReloadOutlined />} onClick={() => uploadStore.resume(item.key)}>
                      重試
                    </Button>
                  ) : null}
                  <Button size="small" type="text" icon={<CloseOutlined />} onClick={() => uploadStore.remove(item.key)} aria-label="移除" />
                </Space>
              </div>
              <Progress
                percent={item.size ? Math.floor((item.sent / item.size) * 100) : 0}
                size="small"
                status={item.state === 'error' ? 'exception' : item.state === 'done' ? 'success' : 'active'}
              />
              <Typography.Text type={item.state === 'error' ? 'danger' : 'secondary'} className="small">
                {item.state === 'error'
                  ? item.error
                  : item.state === 'done'
                    ? '上傳完成，系統正在分析'
                    : item.state === 'paused'
                      ? `已暫停（${formatBytes(item.sent)} / ${formatBytes(item.size)}）`
                      : `${formatBytes(item.sent)} / ${formatBytes(item.size)}`}
              </Typography.Text>
            </div>
          ))}
          {doneCount > 0 ? (
            <Button
              type="link"
              size="small"
              onClick={() => uploadStore.clearDone()}
            >
              清除已完成（{doneCount}）
            </Button>
          ) : null}
        </div>
      ) : null}
    </Card>
  )
}
