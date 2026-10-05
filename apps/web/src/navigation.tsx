import {
  ApiOutlined,
  AppstoreOutlined,
  AudioOutlined,
  CommentOutlined,
  CustomerServiceOutlined,
  DashboardOutlined,
  FileTextOutlined,
  FolderOpenOutlined,
  IdcardOutlined,
  ScissorOutlined,
  ScheduleOutlined,
  SendOutlined,
  TeamOutlined,
  UnorderedListOutlined,
  WalletOutlined,
} from '@ant-design/icons'
import type { ReactNode } from 'react'

export interface NavItem {
  path: string
  label: string
  icon: ReactNode
  /** 尚未開發的功能標示在哪個 Phase 上線 */
  phase?: number
  description?: string
  adminOnly?: boolean
}

export const WORK_ITEMS: NavItem[] = [
  { path: '/', label: '儀表板', icon: <DashboardOutlined /> },
  {
    path: '/profiles',
    label: '帳號檔案',
    icon: <IdcardOutlined />,
    adminOnly: true,
    description: '品牌、行業、受眾、賣點與口吻，AI 改寫文案和挑素材都會參考這份人設。',
  },
  {
    path: '/assets',
    label: '素材中心',
    icon: <FolderOpenOutlined />,
    description: '手機拍攝直接上傳，系統自動切鏡頭、打標籤、分類，並偵測重複素材。',
  },
  {
    path: '/templates',
    label: '模板文案',
    icon: <FileTextOutlined />,
    adminOnly: true,
    description: '內建海外常見影片模板，AI 依帳號檔案為每個鏡頭寫配音稿與字幕，一次產生多個版本。',
  },
  {
    path: '/editor',
    label: '鏡頭剪輯',
    icon: <ScissorOutlined />,
    adminOnly: true,
    description: '選擇已核准的文案，自動挑素材、配音、上字幕並批量產生直式成片。',
  },
  {
    path: '/music',
    label: '背景音樂',
    icon: <CustomerServiceOutlined />,
    adminOnly: true,
    description: '上傳或用 AI 產生背景音樂，成片時整支統一使用並自動避開人聲。',
  },
  {
    path: '/voices',
    label: '音色管理',
    icon: <AudioOutlined />,
    adminOnly: true,
    description: '試聽 ElevenLabs 多語系音色，並綁定到帳號檔案。',
  },
  {
    path: '/tasks',
    label: '任務中心',
    icon: <UnorderedListOutlined />,
    adminOnly: true,
    description: '查看素材分析、文案生成、渲染等背景任務的進度與錯誤。',
  },
  {
    path: '/works',
    label: '作品庫',
    icon: <AppstoreOutlined />,
    adminOnly: true,
    description: '成片待審區：預覽、通過或退回，可單獨替換某個鏡頭後重新渲染。',
  },
  {
    path: '/publish-accounts',
    label: '發佈帳號',
    icon: <SendOutlined />,
    adminOnly: true,
    description: '綁定帳號群的 TikTok、Instagram、YouTube、Facebook 帳號（透過 Upload-Post）。',
  },
  {
    path: '/publish-tasks',
    label: '發佈任務',
    icon: <ScheduleOutlined />,
    adminOnly: true,
    description: '審核通過的成片自動產生各平台標題與 hashtag，排程發佈並回填貼文網址。',
  },
  {
    path: '/comments',
    label: '評論管理',
    icon: <CommentOutlined />,
    adminOnly: true,
    description: '自動拉取評論並分類（詢價 / 好評 / 問題 / 垃圾），AI 產生建議回覆，人工確認後送出。',
  },
]

export const SETTINGS_ITEMS: NavItem[] = [
  { path: '/settings/channels', label: '模型渠道', icon: <ApiOutlined />, adminOnly: true },
  { path: '/settings/publish-channels', label: '發佈渠道', icon: <SendOutlined />, adminOnly: true },
  { path: '/settings/usage', label: '用量與成本', icon: <WalletOutlined />, adminOnly: true },
  { path: '/settings/users', label: '帳號管理', icon: <TeamOutlined />, adminOnly: true },
]
