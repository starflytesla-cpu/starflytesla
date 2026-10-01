import { DeleteOutlined, DownloadOutlined, EditOutlined, ReloadOutlined } from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert,
  App,
  Button,
  Descriptions,
  Drawer,
  Empty,
  Form,
  Grid,
  Input,
  Modal,
  Popconfirm,
  Radio,
  Select,
  Skeleton,
  Space,
  Switch,
  Tag,
  Typography,
} from 'antd'
import dayjs from 'dayjs'
import { useRef, useState } from 'react'
import {
  api,
  ASSET_STATUS,
  formatBytes,
  formatDuration,
  isBusy,
  QUALITY_LABELS,
  SCENE_LABELS,
  type AssetDetail,
  type Clip,
  type ClipInput,
} from '../../api'
import { ApiError } from '../../api/http'
import { useMe } from '../../useMe'

const SCENE_OPTIONS = Object.entries(SCENE_LABELS).map(([value, label]) => ({ value, label }))

function errorText(error: unknown) {
  return error instanceof ApiError ? error.message : '操作失敗'
}

export default function AssetDrawer({ assetId, onClose }: { assetId: string | null; onClose: () => void }) {
  const screens = Grid.useBreakpoint()
  const { data: me } = useMe()
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const videoRef = useRef<HTMLVideoElement>(null)
  const [editingClip, setEditingClip] = useState<Clip | null>(null)
  const isAdmin = me?.role === 'admin'

  const { data: asset, isPending } = useQuery({
    queryKey: ['asset', assetId],
    queryFn: () => api.asset(assetId!),
    enabled: !!assetId,
    refetchInterval: (query) => (query.state.data && isBusy(query.state.data.status) ? 3000 : false),
  })

  const refreshLists = () => {
    void queryClient.invalidateQueries({ queryKey: ['assets'] })
    void queryClient.invalidateQueries({ queryKey: ['asset-stats'] })
  }
  const onSaved = (data: AssetDetail, text = '已儲存') => {
    queryClient.setQueryData(['asset', data.id], data)
    refreshLists()
    message.success(text)
  }

  const update = useMutation({
    mutationFn: (body: Parameters<typeof api.updateAsset>[1]) => api.updateAsset(assetId!, body),
    onSuccess: (data) => onSaved(data),
    onError: (e) => message.error(errorText(e)),
  })
  const reanalyze = useMutation({
    mutationFn: () => api.reanalyzeAsset(assetId!),
    onSuccess: (data) => onSaved(data, '已排入重新分析'),
    onError: (e) => message.error(errorText(e)),
  })
  const remove = useMutation({
    mutationFn: () => api.deleteAsset(assetId!),
    onSuccess: () => {
      refreshLists()
      message.success('已刪除')
      onClose()
    },
    onError: (e) => message.error(errorText(e)),
  })
  const updateClip = useMutation({
    mutationFn: ({ id, body }: { id: string; body: ClipInput }) => api.updateClip(id, body),
    onSuccess: (data) => {
      onSaved(data)
      setEditingClip(null)
    },
    onError: (e) => message.error(errorText(e)),
  })

  const seek = (clip: Clip) => {
    const video = videoRef.current
    if (!video) return
    video.currentTime = clip.start
    void video.play().catch(() => undefined)
    video.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }

  const canDelete = isAdmin || (asset && asset.uploaded_by === me?.id)

  return (
    <Drawer
      open={!!assetId}
      onClose={onClose}
      size={screens.md ? 720 : '100%'}
      title={asset ? <Typography.Text ellipsis>{asset.original_filename}</Typography.Text> : '素材'}
      destroyOnHidden
      extra={
        asset ? (
          <Space>
            {isAdmin && !isBusy(asset.status) && asset.status !== 'duplicate' ? (
              <Button icon={<ReloadOutlined />} loading={reanalyze.isPending} onClick={() => reanalyze.mutate()}>
                重新分析
              </Button>
            ) : null}
            {canDelete ? (
              <Popconfirm
                title="刪除這個素材？"
                description="原始檔與所有鏡頭都會刪除，無法復原。"
                okText="刪除"
                okButtonProps={{ danger: true }}
                onConfirm={() => remove.mutate()}
              >
                <Button danger icon={<DeleteOutlined />} loading={remove.isPending} aria-label="刪除" />
              </Popconfirm>
            ) : null}
          </Space>
        ) : null
      }
    >
      {isPending || !asset ? (
        <Skeleton active />
      ) : (
        <>
          <div className="asset-player section">
            {asset.proxy_url ? (
              <video ref={videoRef} src={asset.proxy_url} poster={asset.poster_url ?? undefined} controls playsInline preload="metadata" />
            ) : asset.poster_url ? (
              <img src={asset.poster_url} alt={asset.original_filename} />
            ) : (
              <Empty description={isBusy(asset.status) ? '分析完成後即可預覽' : '沒有預覽'} />
            )}
          </div>

          {isBusy(asset.status) ? (
            <Alert className="section" type="info" showIcon title={`${ASSET_STATUS[asset.status].label}：${asset.stage || '排隊中'}`} />
          ) : null}
          {asset.status === 'failed' ? (
            <Alert
              className="section"
              type="error"
              showIcon
              title={`分析失敗：${asset.error}`}
              description={asset.stage || (isAdmin ? '可以按「重新分析」再試一次' : undefined)}
            />
          ) : null}
          {asset.status === 'duplicate' ? (
            <Alert
              className="section"
              type="warning"
              showIcon
              title="與既有素材完全相同，已自動略過"
              description={`相同的素材：${asset.duplicate_of_filename || '（已刪除）'}。這筆記錄可以直接刪除。`}
            />
          ) : null}
          {asset.status === 'ready' && asset.stage ? (
            <Alert className="section" type="warning" showIcon title={asset.stage} />
          ) : null}

          <Descriptions size="small" column={screens.md ? 2 : 1} className="section" bordered>
            <Descriptions.Item label="狀態">
              <Tag color={ASSET_STATUS[asset.status].color}>{ASSET_STATUS[asset.status].label}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="分類">
              {isAdmin ? (
                <Select
                  size="small"
                  className="category-select"
                  value={asset.category || undefined}
                  placeholder="未分類"
                  options={SCENE_OPTIONS}
                  onChange={(category: string) => update.mutate({ category })}
                />
              ) : (
                SCENE_LABELS[asset.category] ?? '未分類'
              )}
            </Descriptions.Item>
            {asset.duration ? <Descriptions.Item label="長度">{formatDuration(asset.duration)}</Descriptions.Item> : null}
            {asset.width ? (
              <Descriptions.Item label="解析度">
                {asset.width}×{asset.height}
                {asset.fps ? ` · ${Math.round(asset.fps)}fps` : ''}
                {asset.kind === 'video' && !asset.has_audio ? ' · 無聲' : ''}
              </Descriptions.Item>
            ) : null}
            <Descriptions.Item label="大小">{formatBytes(asset.size_bytes)}</Descriptions.Item>
            <Descriptions.Item label="上傳">
              {asset.uploaded_by_name || '—'} · {dayjs(asset.created_at).format('MM/DD HH:mm')}
            </Descriptions.Item>
            {isAdmin ? (
              <Descriptions.Item label="停用" span={screens.md ? 2 : 1}>
                <Space>
                  <Switch
                    size="small"
                    checked={asset.is_disabled}
                    onChange={(is_disabled) => update.mutate({ is_disabled })}
                  />
                  <Typography.Text type="secondary" className="small">
                    停用後混剪不會挑選這個素材
                  </Typography.Text>
                </Space>
              </Descriptions.Item>
            ) : null}
            <Descriptions.Item label="備註" span={screens.md ? 2 : 1}>
              {isAdmin ? (
                <Typography.Paragraph
                  className="note-edit"
                  editable={{
                    onChange: (note) => note !== asset.note && update.mutate({ note }),
                    maxLength: 500,
                    text: asset.note,
                  }}
                >
                  {asset.note || <Typography.Text type="secondary">例如產品型號、拍攝地點，AI 標註時會參考</Typography.Text>}
                </Typography.Paragraph>
              ) : (
                asset.note || '—'
              )}
            </Descriptions.Item>
          </Descriptions>

          {asset.original_url ? (
            <Button className="section" icon={<DownloadOutlined />} href={asset.original_url} download={asset.original_filename}>
              下載原始檔
            </Button>
          ) : null}

          {asset.clips.length > 0 ? (
            <>
              <Typography.Title level={5}>鏡頭（{asset.clips.length}）</Typography.Title>
              <div className="clip-list">
                {asset.clips.map((clip) => (
                  <ClipRow
                    key={clip.id}
                    clip={clip}
                    isVideo={asset.kind === 'video'}
                    isAdmin={isAdmin}
                    onSeek={() => seek(clip)}
                    onEdit={() => setEditingClip(clip)}
                  />
                ))}
              </div>
            </>
          ) : null}

          <ClipEditModal
            clip={editingClip}
            saving={updateClip.isPending}
            onCancel={() => setEditingClip(null)}
            onSave={(body) => editingClip && updateClip.mutate({ id: editingClip.id, body })}
          />
        </>
      )}
    </Drawer>
  )
}

function ClipRow({
  clip,
  isVideo,
  isAdmin,
  onSeek,
  onEdit,
}: {
  clip: Clip
  isVideo: boolean
  isAdmin: boolean
  onSeek: () => void
  onEdit: () => void
}) {
  const quality = clip.quality ? QUALITY_LABELS[clip.quality] : null
  return (
    <div className={`clip-row${clip.is_disabled ? ' is-disabled' : ''}`}>
      <button type="button" className="clip-thumb" onClick={onSeek} disabled={!isVideo} title={isVideo ? '播放這個鏡頭' : undefined}>
        <img src={clip.thumb_url} alt={`鏡頭 ${clip.index + 1}`} loading="lazy" />
        {isVideo ? (
          <span className="clip-time">
            {formatDuration(clip.start)}–{formatDuration(clip.end)}
          </span>
        ) : null}
      </button>
      <div className="clip-info">
        <div className="clip-tags">
          {clip.scene ? <Tag color="blue">{SCENE_LABELS[clip.scene] ?? clip.scene}</Tag> : <Tag>未標註</Tag>}
          {quality ? <Tag color={quality.color}>{quality.label}</Tag> : null}
          {clip.is_dark ? <Tag color="default">過暗</Tag> : null}
          {clip.duplicate_of ? (
            <Tag color="orange" title={`與「${clip.duplicate_of.filename}」第 ${clip.duplicate_of.index + 1} 個鏡頭幾乎相同`}>
              疑似重複
            </Tag>
          ) : null}
          {clip.is_disabled ? <Tag color="red">已停用</Tag> : null}
          {clip.tagged_by === 'manual' ? <Tag>人工</Tag> : null}
        </div>
        {clip.description ? <div className="clip-desc">{clip.description}</div> : null}
        {clip.tags.length || clip.subjects.length ? (
          <Typography.Text type="secondary" className="small">
            {[...clip.subjects, ...clip.tags].map((t) => `#${t}`).join(' ')}
          </Typography.Text>
        ) : null}
      </div>
      {isAdmin ? <Button type="text" size="small" icon={<EditOutlined />} onClick={onEdit} aria-label="編輯鏡頭" /> : null}
    </div>
  )
}

function ClipEditModal({
  clip,
  saving,
  onCancel,
  onSave,
}: {
  clip: Clip | null
  saving: boolean
  onCancel: () => void
  onSave: (body: ClipInput) => void
}) {
  const [form] = Form.useForm<Required<ClipInput>>()
  return (
    <Modal
      open={!!clip}
      title={clip ? `編輯鏡頭 ${clip.index + 1}` : ''}
      okText="儲存"
      confirmLoading={saving}
      onCancel={onCancel}
      onOk={() => form.submit()}
      destroyOnHidden
      forceRender
    >
      {clip ? (
        <Form
          form={form}
          layout="vertical"
          initialValues={{
            scene: clip.scene || undefined,
            subjects: clip.subjects,
            tags: clip.tags,
            description: clip.description,
            quality: clip.quality,
            is_disabled: clip.is_disabled,
          }}
          onFinish={(values) => onSave({ ...values, scene: values.scene ?? '', description: values.description ?? '' })}
        >
          <Form.Item name="scene" label="場景">
            <Select options={SCENE_OPTIONS} placeholder="選擇場景" allowClear />
          </Form.Item>
          <Form.Item name="subjects" label="主體" extra="輸入後按 Enter，最多 12 個">
            <Select mode="tags" maxCount={12} tokenSeparators={[',', '，']} open={false} />
          </Form.Item>
          <Form.Item name="tags" label="標籤" extra="輸入後按 Enter，最多 12 個">
            <Select mode="tags" maxCount={12} tokenSeparators={[',', '，']} open={false} />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea maxLength={200} showCount autoSize={{ minRows: 2, maxRows: 4 }} />
          </Form.Item>
          <Form.Item name="quality" label="畫面品質">
            <Radio.Group
              optionType="button"
              options={[
                { value: 'good', label: '清楚' },
                { value: 'ok', label: '普通' },
                { value: 'poor', label: '不佳' },
                { value: '', label: '未評估' },
              ]}
            />
          </Form.Item>
          <Form.Item name="is_disabled" label="停用這個鏡頭" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      ) : null}
    </Modal>
  )
}
