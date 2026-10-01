import { PlayCircleOutlined } from '@ant-design/icons'
import { useQueryClient } from '@tanstack/react-query'
import { App, Button, type ButtonProps } from 'antd'
import { useState } from 'react'
import { api, type Voice } from '../api'
import { ApiError } from '../api/http'
import { playAudio } from '../audio'
import AudioButton from './AudioButton'

/**
 * 音色試聽按鈕：ElevenLabs 直接播官方試聽檔；Gemini 第一次按會請伺服器產生樣本（之後重用），再播放。
 */
export default function VoicePlayButton({ voice, ...props }: { voice: Voice } & ButtonProps) {
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const [loading, setLoading] = useState(false)
  const cached = queryClient.getQueryData<string>(['voice-sample', voice.id])
  const url = voice.preview_url ?? cached

  if (url) return <AudioButton url={url} {...props} />
  return (
    <Button
      icon={<PlayCircleOutlined />}
      loading={loading}
      aria-label="試聽"
      onClick={async (event) => {
        event.stopPropagation()
        setLoading(true)
        try {
          const result = await queryClient.fetchQuery({
            queryKey: ['voice-sample', voice.id],
            queryFn: async () => (await api.voiceSample(voice.id)).audio_url,
            staleTime: Infinity,
          })
          playAudio(result)
        } catch (error) {
          message.error(error instanceof ApiError ? error.message : '試聽失敗')
        } finally {
          setLoading(false)
        }
      }}
      {...props}
    />
  )
}
