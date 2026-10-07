import { FileImageOutlined, LoadingOutlined, VideoCameraOutlined } from '@ant-design/icons'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import {
  Button,
  Card,
  Col,
  Empty,
  Input,
  Pagination,
  Row,
  Select,
  Space,
  Statistic,
  Switch,
  Tag,
  Typography,
} from 'antd'
import dayjs from 'dayjs'
import { useState } from 'react'
import {
  api,
  ASSET_STATUS,
  formatDuration,
  isBusy,
  SCENE_LABELS,
  type Asset,
  type AssetQuery,
  type AssetStatus,
} from '../../api'
import PageHeader from '../../components/PageHeader'
import QueryFeedback from '../../components/QueryFeedback'
import { useSearchParams } from 'react-router'
import AssetDrawer from './AssetDrawer'
import UploadPanel from './UploadPanel'

const PAGE_SIZE = 24

type Filters = Omit<AssetQuery, 'limit' | 'offset'>

export default function AssetsPage() {
  const [params] = useSearchParams()
  const initialStatus = params.get('status')
  const [filters, setFilters] = useState<Filters>(() => ({
    status: initialStatus && initialStatus in ASSET_STATUS ? (initialStatus as AssetStatus) : undefined,
  }))
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [selected, setSelected] = useState<string | null>(null)

  const setFilter = (change: Filters) => {
    setFilters((prev) => ({ ...prev, ...change }))
    setPage(1)
  }

  const { data, isPending, error, refetch } = useQuery({
    queryKey: ['assets', filters, page],
    queryFn: () =>
      api.assets({
        ...filters,
        limit: PAGE_SIZE,
        offset: (page - 1) * PAGE_SIZE,
      }),
    placeholderData: keepPreviousData,
    // 有素材在分析中時每 3 秒更新一次
    refetchInterval: (query) => (query.state.data?.items.some((a) => isBusy(a.status)) ? 3000 : false),
  })
  const {
    data: stats,
    error: statsError,
    refetch: refetchStats,
  } = useQuery({
    queryKey: ['asset-stats'],
    queryFn: api.assetStats,
    refetchInterval: (query) => {
      const s = query.state.data?.by_status
      return s && s.uploaded + s.processing > 0 ? 5000 : false
    },
  })

  return (
    <>
      <PageHeader title="素材中心" subtitle="手機拍攝直接上傳，系統自動切鏡頭、打標籤、分類，並偵測重複素材" />

      <UploadPanel />
      <QueryFeedback
        error={error || statsError}
        retry={() => Promise.all([refetch(), refetchStats()])}
        stale={!!data}
      />

      {stats ? (
        <Row gutter={[12, 12]} className="section">
          <Col xs={8} md={6}>
            <Card size="small">
              <Statistic title="素材" value={stats.total} />
            </Card>
          </Col>
          <Col xs={8} md={6}>
            <Card size="small">
              <Statistic title="可用鏡頭" value={stats.clips} />
            </Card>
          </Col>
          <Col xs={8} md={6}>
            <Card size="small">
              <Statistic title="分析中" value={stats.by_status.uploaded + stats.by_status.processing} />
            </Card>
          </Col>
          <Col xs={8} md={6}>
            <Card size="small" className="metric-card">
              <button className="metric-link" onClick={() => setFilter({ status: 'failed' })}>
                <Statistic title="失敗 / 重複" value={`${stats.by_status.failed} / ${stats.by_status.duplicate}`} />
              </button>
            </Card>
          </Col>
        </Row>
      ) : null}

      <div className="asset-filters section">
        <Input.Search
          placeholder="搜尋檔名或備註"
          allowClear
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          onSearch={(q) => setFilter({ q: q || undefined })}
          className="asset-search"
        />
        <Select
          placeholder="全部分類"
          allowClear
          className="asset-filter"
          value={filters.category}
          onChange={(category?: string) => setFilter({ category })}
          options={Object.entries(SCENE_LABELS).map(([value, label]) => ({
            value,
            label: stats?.by_category[value] ? `${label}（${stats.by_category[value]}）` : label,
          }))}
        />
        <Select
          placeholder="全部狀態"
          allowClear
          className="asset-filter"
          value={filters.status}
          onChange={(status?: AssetStatus) => setFilter({ status })}
          options={Object.entries(ASSET_STATUS).map(([value, s]) => ({
            value,
            label: s.label,
          }))}
        />
        <Select
          placeholder="影片與照片"
          allowClear
          className="asset-filter"
          value={filters.kind}
          onChange={(kind?: 'video' | 'image') => setFilter({ kind })}
          options={[
            { value: 'video', label: '影片' },
            { value: 'image', label: '照片' },
          ]}
        />
        <Space>
          <Switch
            aria-label="只看我上傳的素材"
            size="small"
            checked={!!filters.mine}
            onChange={(mine) => setFilter({ mine: mine || undefined })}
          />
          <span className="small">只看我上傳的</span>
        </Space>
        {Object.values(filters).some((v) => v !== undefined) ? (
          <Button
            type="link"
            onClick={() => {
              setFilters({})
              setSearch('')
              setPage(1)
            }}
          >
            清除篩選
          </Button>
        ) : null}
      </div>
      <Space wrap className="section">
        {Object.entries(filters)
          .filter(([, v]) => v !== undefined)
          .map(([key, value]) => (
            <Tag
              key={key}
              closable
              onClose={() => {
                setFilter({ [key]: undefined })
                if (key === 'q') setSearch('')
              }}
            >
              {key === 'status'
                ? ASSET_STATUS[value as AssetStatus].label
                : key === 'category'
                  ? (SCENE_LABELS[String(value)] ?? value)
                  : key === 'mine'
                    ? '我上傳的'
                    : key === 'kind'
                      ? value === 'video'
                        ? '影片'
                        : '照片'
                      : `搜尋：${value}`}
            </Tag>
          ))}
      </Space>

      {data && data.items.length === 0 ? (
        <Card>
          <Empty
            description={
              Object.values(filters).some((v) => v !== undefined)
                ? '沒有符合條件的素材'
                : '還沒有素材，先拍一段影片上傳吧'
            }
          />
        </Card>
      ) : (
        <Row gutter={[12, 12]}>
          {(data?.items ?? []).map((asset) => (
            <Col key={asset.id} xs={12} sm={8} md={6} xl={4}>
              <AssetCard asset={asset} onOpen={() => setSelected(asset.id)} />
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
      )}

      {data && data.total > PAGE_SIZE ? (
        <Pagination
          className="asset-pagination"
          current={page}
          pageSize={PAGE_SIZE}
          total={data.total}
          showSizeChanger={false}
          onChange={setPage}
        />
      ) : null}

      <AssetDrawer assetId={selected} onClose={() => setSelected(null)} />
    </>
  )
}

function AssetCard({ asset, onOpen }: { asset: Asset; onOpen: () => void }) {
  const status = ASSET_STATUS[asset.status]
  return (
    <Card
      hoverable
      size="small"
      onClick={onOpen}
      role="button"
      tabIndex={0}
      aria-label={`查看素材 ${asset.original_filename}`}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onOpen()
        }
      }}
      className={`asset-card${asset.is_disabled ? ' is-disabled' : ''}`}
      cover={
        <div className="asset-cover">
          {asset.poster_url ? (
            <img src={asset.poster_url} alt={asset.original_filename} loading="lazy" />
          ) : isBusy(asset.status) ? (
            <div className="asset-cover-placeholder">
              <LoadingOutlined />
              <span>{asset.stage || '排隊中'}</span>
            </div>
          ) : (
            <div className="asset-cover-placeholder">
              {asset.kind === 'image' ? <FileImageOutlined /> : <VideoCameraOutlined />}
            </div>
          )}
          {asset.status !== 'ready' ? (
            <Tag className="asset-status" color={status.color}>
              {status.label}
            </Tag>
          ) : null}
          {asset.duration ? <span className="asset-duration">{formatDuration(asset.duration)}</span> : null}
        </div>
      }
    >
      <Typography.Text ellipsis className="asset-name" title={asset.original_filename}>
        {asset.original_filename}
      </Typography.Text>
      <div className="asset-meta">
        {asset.category ? <Tag color="blue">{SCENE_LABELS[asset.category] ?? asset.category}</Tag> : null}
        {asset.clip_count ? <span>{asset.clip_count} 個鏡頭</span> : null}
        {asset.is_disabled ? <Tag color="red">已停用</Tag> : null}
      </div>
      <Typography.Text type="secondary" className="small">
        {asset.uploaded_by_name} · {dayjs(asset.created_at).format('MM/DD HH:mm')}
      </Typography.Text>
    </Card>
  )
}
