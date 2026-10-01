import { PauseCircleOutlined, PlayCircleOutlined } from '@ant-design/icons'
import { Button, type ButtonProps } from 'antd'
import { useSyncExternalStore } from 'react'
import { pauseAudio, playAudio, playingUrl, subscribeAudio } from '../audio'

/** 播放 / 暫停音檔的按鈕 */
export default function AudioButton({ url, label, ...props }: { url: string; label?: string } & ButtonProps) {
  const playing = useSyncExternalStore(subscribeAudio, playingUrl)
  const isPlaying = playing === new URL(url, window.location.href).href
  return (
    <Button
      icon={isPlaying ? <PauseCircleOutlined /> : <PlayCircleOutlined />}
      onClick={(event) => {
        event.stopPropagation()
        if (isPlaying) pauseAudio()
        else playAudio(url)
      }}
      aria-label={isPlaying ? '暫停' : '試聽'}
      {...props}
    >
      {label}
    </Button>
  )
}
