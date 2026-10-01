import {
  CheckOutlined,
  CloseOutlined,
  DeleteOutlined,
  DownloadOutlined,
  ReloadOutlined,
  SwapOutlined,
} from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert,
  App,
  Button,
  Descriptions,
  Drawer,
  Empty,
  Grid,
  Input,
  Modal,
  Popconfirm,
  Skeleton,
  Space,
  Spin,
  Tag,
  Typography,
} from 'antd'
import dayjs from 'dayjs'
import { useRef, useState } from 'react'
import { api, formatDuration, SCENE_LABELS, VIDEO_STATUS, type VideoDetail, type VideoShot } from '../../api'
import { ApiError } from '../../api/http'

function errorText(error: unknown) {
  return error instanceof ApiError ? error.message : '操作失敗'
}

const isBusy = (status?: string) => status === 'queued' || status === 'rendering'

export default function VideoDrawer({ videoId, onClose }: { videoId: string | null; onClose: () => void }) {
  const screens = Grid.useBreakpoint()
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const player = useRef<HTMLVideoElement>(null)
  const [rejecting, setRejecting] = useState(false)
  const [note, setNote] = useState('')
  const [swapShot, setSwapShot] = useState<VideoShot | null>(null)

  const { data: video, isPending } = useQuery({
    queryKey: ['video', videoId],
    queryFn: () => api.video(videoId!),
    enabled: !!videoId,
    refetchInterval: (q) => (isBusy(q.state.data?.status) ? 3000 : false),
  })

  const saved = (data: VideoDetail | null, text: string) => {
    if (data) queryClient.setQueryData(['video', data.id], data)
    void queryClient.invalidateQueries({ queryKey: ['videos'] })
    void queryClient.invalidateQueries({ queryKey: ['video-stats'] })
    message.success(text)
  }
  const review = useMutation({
    mutationFn: ({ action, note }: { action: 'approve' | 'reject'; note?: string }) => api.reviewVideo(videoId!, action, note),
    onSuccess: (data, vars) => {
      saved(data, vars.action === 'approve' ? '已通過，Phase 4 可以排程發佈' : '已退回')
      setRejecting(false)
      setNote('')
    },
    onError: (e) => message.error(errorText(e)),
  })
  const rerender = useMutation({
    mutationFn: (reshuffle: boolean) => api.rerenderVideo(videoId!, reshuffle),
    onSuccess: (data) => saved(data, '已排入重新渲染'),
    onError: (e) => message.error(errorText(e)),
  })
  const remove = useMutation({
    mutationFn: () => api.deleteVideo(videoId!),
    onSuccess: () => {
      saved(null, '已刪除')
      onClose()
    },
    onError: (e) => message.error(errorText(e)),
  })

  const seek = (shot: VideoShot) => {
    if (!player.current) return
    player.current.currentTime = shot.start + 0.05
    void player.current.play().catch(() => undefined)
  }

  const reviewable = video && ['pending_review', 'approved', 'rejected'].includes(video.status)

  return (
    <Drawer
      open={!!videoId}
      onClose={onClose}
      size={screens.md ? 860 : '100%'}
      title={video?.title ?? '成片'}
      destroyOnHidden
      extra={
        reviewable ? (
          <Space>
            <Button danger icon={<CloseOutlined />} onClick={() => setRejecting(true)} disabled={video.status === 'rejected'}>
              退回
            </Button>
            <Button
              type="primary"
              icon={<CheckOutlined />}
              loading={review.isPending && review.variables?.action === 'approve'}
              disabled={video.status === 'approved'}
              onClick={() => review.mutate({ action: 'approve' })}
            >
              通過
            </Button>
          </Space>
        ) : null
      }
    >
      {isPending || !video ? (
        <Skeleton active />
      ) : (
        <div className="video-layout">
          <div className="video-player-col">
            <div className="video-player">
              {video.video_url && !isBusy(video.status) ? (
                <video ref={player} src={video.video_url} poster={video.poster_url ?? undefined} controls playsInline preload="metadata" />
              ) : (
                <div className="video-player-empty">
                  {isBusy(video.status) ? <Spin /> : null}
                  <span>{isBusy(video.status) ? video.stage || '排隊中' : '沒有成片'}</span>
                </div>
              )}
            </div>
            <Space wrap className="section video-actions">
              {video.video_url ? (
                <Button icon={<DownloadOutlined />} href={video.video_url} download={`${video.title}.mp4`}>
                  下載
                </Button>
              ) : null}
              <Popconfirm
                title="重新挑素材並渲染？"
                description="會用新的隨機組合挑素材與字幕樣式，配音沿用。"
                onConfirm={() => rerender.mutate(true)}
                disabled={isBusy(video.status)}
              >
                <Button icon={<ReloadOutlined />} disabled={isBusy(video.status)} loading={rerender.isPending}>
                  重新挑素材
                </Button>
              </Popconfirm>
              <Popconfirm title="刪除這支成片？" okText="刪除" okButtonProps={{ danger: true }} onConfirm={() => remove.mutate()}>
                <Button danger icon={<DeleteOutlined />} disabled={video.status === 'rendering'} aria-label="刪除" />
              </Popconfirm>
            </Space>
          </div>

          <div className="video-info-col">
            {video.status === 'failed' ? <Alert className="section" type="error" showIcon title={`渲染失敗：${video.error}`} /> : null}
            {video.status === 'rejected' && video.review_note ? (
              <Alert className="section" type="warning" showIcon title={`退回原因：${video.review_note}`} />
            ) : null}
            <Descriptions size="small" column={1} bordered className="section">
              <Descriptions.Item label="狀態">
                <Tag color={VIDEO_STATUS[video.status].color}>{VIDEO_STATUS[video.status].label}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="來源">
                {video.template_name} · {video.profile_name} · {video.language}
              </Descriptions.Item>
              {video.duration ? (
                <Descriptions.Item label="長度">
                  {formatDuration(video.duration)}
                  {video.render_seconds ? `（渲染 ${Math.round(video.render_seconds)} 秒）` : ''}
                </Descriptions.Item>
              ) : null}
              <Descriptions.Item label="背景音樂">{video.bgm_title || '無'}</Descriptions.Item>
              <Descriptions.Item label="建立">{dayjs(video.created_at).format('MM/DD HH:mm')}</Descriptions.Item>
            </Descriptions>

            <Typography.Title level={5}>鏡頭（點縮圖跳到該段）</Typography.Title>
            {video.shots.length === 0 ? <Empty description="還沒有時間軸" /> : null}
            <div className="shot-list">
              {video.shots.map((shot) => (
                <div key={shot.index} className="shot-row">
                  <span className="shot-index">{shot.index + 1}</span>
                  <div className="shot-body">
                    <div className="video-segments">
                      {shot.segments.map((seg, i) => (
                        <button key={i} type="button" className="clip-thumb" onClick={() => seek(shot)} title={seg.description}>
                          {seg.thumb_url ? <img src={seg.thumb_url} alt="" loading="lazy" /> : null}
                          <span className="clip-time">{seg.duration.toFixed(1)}s</span>
                        </button>
                      ))}
                    </div>
                    {shot.caption ? <Typography.Text strong>{shot.caption}</Typography.Text> : null}
                    <Typography.Text type="secondary" className="small">
                      {formatDuration(shot.start)} · {shot.duration.toFixed(1)} 秒
                      {shot.scene ? ` · 期望：${SCENE_LABELS[shot.scene] ?? shot.scene}` : ''}
                    </Typography.Text>
                    {shot.voiceover ? <div className="small">{shot.voiceover}</div> : null}
                  </div>
                  <Button
                    size="small"
                    icon={<SwapOutlined />}
                    disabled={isBusy(video.status)}
                    onClick={() => setSwapShot(shot)}
                  >
                    換素材
                  </Button>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      <Modal
        open={rejecting}
        title="退回這支成片"
        okText="退回"
        okButtonProps={{ danger: true, disabled: !note.trim() }}
        confirmLoading={review.isPending}
        onOk={() => review.mutate({ action: 'reject', note })}
        onCancel={() => setRejecting(false)}
      >
        <Input.TextArea
          value={note}
          onChange={(e) => setNote(e.target.value)}
          maxLength={500}
          autoSize={{ minRows: 3 }}
          placeholder="寫下原因，例如：第 3 個鏡頭太暗、字幕擋到產品"
        />
      </Modal>
      {video && swapShot ? (
        <SwapModal
          videoId={video.id}
          shot={swapShot}
          onClose={() => setSwapShot(null)}
          onDone={(data) => {
            saved(data, '已換素材，重新渲染中')
            setSwapShot(null)
          }}
        />
      ) : null}
    </Drawer>
  )
}

function SwapModal({
  videoId,
  shot,
  onClose,
  onDone,
}: {
  videoId: string
  shot: VideoShot
  onClose: () => void
  onDone: (data: VideoDetail) => void
}) {
  const { message } = App.useApp()
  const { data, isPending } = useQuery({
    queryKey: ['candidates', videoId, shot.index],
    queryFn: () => api.videoCandidates(videoId, shot.index),
  })
  const replace = useMutation({
    mutationFn: (clipId: string) => api.replaceVideoClip(videoId, shot.index, clipId),
    onSuccess: onDone,
    onError: (e) => message.error(errorText(e)),
  })
  return (
    <Modal open title={`鏡頭 ${shot.index + 1} 換素材`} footer={null} onCancel={onClose} width={760}>
      <Typography.Paragraph type="secondary" className="small">
        {shot.brief}（需要 {shot.duration.toFixed(1)} 秒；同類型畫面排在前面，點一下就會換上並重新渲染）
      </Typography.Paragraph>
      {isPending ? <Skeleton active /> : null}
      {data && data.length === 0 ? <Empty description="沒有其他可用的素材" /> : null}
      <Spin spinning={replace.isPending}>
        <div className="candidate-grid">
          {(data ?? []).map((c) => (
            <button key={c.clip_id} type="button" className="candidate" onClick={() => replace.mutate(c.clip_id)}>
              <img src={c.thumb_url} alt="" loading="lazy" />
              <div className="candidate-meta">
                {c.scene_match ? <Tag color="green">同類型</Tag> : null}
                {c.scene ? <Tag>{SCENE_LABELS[c.scene] ?? c.scene}</Tag> : null}
                {c.length !== null ? <Tag>{c.length.toFixed(1)}s</Tag> : <Tag>照片</Tag>}
              </div>
              <div className="candidate-desc small">{c.description || c.filename}</div>
            </button>
          ))}
        </div>
      </Spin>
    </Modal>
  )
}
