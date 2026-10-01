import { LoadingOutlined, VideoCameraOutlined } from '@ant-design/icons'
import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button, Card, Col, Empty, Pagination, Row, Segmented, Tag, Typography } from 'antd'
import dayjs from 'dayjs'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router'
import { api, formatDuration, VIDEO_STATUS, type Video, type VideoStatus } from '../../api'
import PageHeader from '../../components/PageHeader'
import VideoDrawer from './VideoDrawer'

const PAGE_SIZE = 24
const TABS: (VideoStatus | 'all')[] = ['pending_review', 'all', 'rendering', 'approved', 'rejected', 'failed']

function isRendering(status: VideoStatus) {
  return status === 'queued' || status === 'rendering'
}

export default function WorksPage() {
  const navigate = useNavigate()
  const [tab, setTab] = useState<VideoStatus | 'all'>('pending_review')
  const [page, setPage] = useState(1)
  const [selected, setSelected] = useState<string | null>(null)

  const queryClient = useQueryClient()
  const { data: stats } = useQuery({
    queryKey: ['video-stats'],
    queryFn: api.videoStats,
    refetchInterval: (q) => (q.state.data && q.state.data.queued + q.state.data.rendering > 0 ? 3000 : false),
  })
  // 有成片在渲染時，任何分頁都定時更新；渲染數量變化（例如剛完成）時立即重新整理列表
  const busy = stats ? stats.queued + stats.rendering : 0
  useEffect(() => {
    void queryClient.invalidateQueries({ queryKey: ['videos'] })
  }, [busy, queryClient])
  // 「渲染中」分頁同時顯示排隊與渲染中的成片
  const status = tab === 'all' || tab === 'rendering' ? undefined : tab
  const { data, isPending } = useQuery({
    queryKey: ['videos', tab, page],
    queryFn: async () => {
      if (tab !== 'rendering') return api.videos({ status, limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE })
      const [rendering, queued] = await Promise.all([
        api.videos({ status: 'rendering', limit: 100, offset: 0 }),
        api.videos({ status: 'queued', limit: 100, offset: 0 }),
      ])
      return { items: [...rendering.items, ...queued.items], total: rendering.total + queued.total }
    },
    placeholderData: keepPreviousData,
    refetchInterval: (q) => (busy > 0 || q.state.data?.items.some((v) => isRendering(v.status)) ? 3000 : false),
  })

  const count = (key: VideoStatus | 'all') => {
    if (!stats) return ''
    if (key === 'all') return Object.values(stats).reduce((a, b) => a + b, 0)
    if (key === 'rendering') return stats.rendering + stats.queued
    return stats[key]
  }
  const label = (key: VideoStatus | 'all') => (key === 'all' ? '全部' : key === 'rendering' ? '產生中' : VIDEO_STATUS[key].label)

  return (
    <>
      <PageHeader
        title="作品庫"
        subtitle="成片待審區：預覽後通過或退回；不滿意的鏡頭可以單獨換素材，再重新渲染"
        extra={
          <Button type="primary" icon={<VideoCameraOutlined />} onClick={() => navigate('/editor')}>
            產生成片
          </Button>
        }
      />
      <div className="section works-tabs">
        <Segmented
          value={tab}
          onChange={(v) => {
            setTab(v as VideoStatus | 'all')
            setPage(1)
          }}
          options={TABS.map((key) => ({ value: key, label: `${label(key)} ${count(key)}` }))}
        />
      </div>

      {data && data.items.length === 0 ? (
        <Card>
          <Empty description={tab === 'pending_review' ? '目前沒有待審的成片' : '沒有成片'}>
            <Button onClick={() => navigate('/editor')}>去產生成片</Button>
          </Empty>
        </Card>
      ) : null}
      <Row gutter={[12, 12]}>
        {(data?.items ?? []).map((video) => (
          <Col key={video.id} xs={12} sm={8} md={6} xl={4}>
            <VideoCard video={video} onOpen={() => setSelected(video.id)} />
          </Col>
        ))}
        {isPending
          ? Array.from({ length: 6 }, (_, i) => (
              <Col key={i} xs={12} sm={8} md={6} xl={4}>
                <Card loading />
              </Col>
            ))
          : null}
      </Row>
      {data && tab !== 'rendering' && data.total > PAGE_SIZE ? (
        <Pagination
          className="asset-pagination"
          current={page}
          pageSize={PAGE_SIZE}
          total={data.total}
          showSizeChanger={false}
          onChange={setPage}
        />
      ) : null}
      <VideoDrawer videoId={selected} onClose={() => setSelected(null)} />
    </>
  )
}

function VideoCard({ video, onOpen }: { video: Video; onOpen: () => void }) {
  const status = VIDEO_STATUS[video.status]
  return (
    <Card
      hoverable
      size="small"
      className="asset-card"
      onClick={onOpen}
      cover={
        <div className="asset-cover video-cover">
          {video.poster_url && !isRendering(video.status) ? (
            <img src={video.poster_url} alt={video.title} loading="lazy" />
          ) : (
            <div className="asset-cover-placeholder">
              {isRendering(video.status) ? <LoadingOutlined /> : <VideoCameraOutlined />}
              <span>{isRendering(video.status) ? video.stage || '排隊中' : video.error || '沒有預覽'}</span>
            </div>
          )}
          <Tag className="asset-status" color={status.color}>
            {status.label}
          </Tag>
          {video.duration ? <span className="asset-duration">{formatDuration(video.duration)}</span> : null}
        </div>
      }
    >
      <Typography.Text ellipsis className="asset-name" title={video.title}>
        {video.title}
      </Typography.Text>
      <Typography.Text type="secondary" className="small">
        {video.profile_name} · {dayjs(video.created_at).format('MM/DD HH:mm')}
      </Typography.Text>
    </Card>
  )
}
