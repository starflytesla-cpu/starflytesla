import { KeyOutlined, LogoutOutlined, MenuOutlined, UserOutlined } from '@ant-design/icons'
import { useQueryClient } from '@tanstack/react-query'
import { App, Avatar, Button, Drawer, Dropdown, Grid, Layout, Menu, Tag } from 'antd'
import type { MenuProps } from 'antd'
import { useState } from 'react'
import { Outlet, useLocation, useNavigate } from 'react-router'
import { api } from '../api'
import { useMe } from '../useMe'
import ChangePasswordModal from '../components/ChangePasswordModal'
import { SETTINGS_ITEMS, WORK_ITEMS, type NavItem } from '../navigation'

const { Sider, Header, Content } = Layout

function toMenuItem(item: NavItem): Required<MenuProps>['items'][number] {
  return {
    key: item.path,
    icon: item.icon,
    label: (
      <span className="menu-label">
        {item.label}
        {item.phase ? <Tag className="phase-tag">P{item.phase}</Tag> : null}
      </span>
    ),
  }
}

export default function AppLayout() {
  const { data: me } = useMe()
  const navigate = useNavigate()
  const location = useLocation()
  const queryClient = useQueryClient()
  const { message } = App.useApp()
  const screens = Grid.useBreakpoint()
  const isMobile = !screens.lg
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [passwordOpen, setPasswordOpen] = useState(false)

  const isAdmin = me?.role === 'admin'
  const visible = (item: NavItem) => isAdmin || !item.adminOnly
  const items: MenuProps['items'] = [
    ...WORK_ITEMS.filter(visible).map(toMenuItem),
    ...(isAdmin
      ? [
          { type: 'divider' as const },
          {
            type: 'group' as const,
            label: '系統設定',
            children: SETTINGS_ITEMS.map(toMenuItem),
          },
        ]
      : []),
  ]

  const selected = [...WORK_ITEMS, ...SETTINGS_ITEMS]
    .map((i) => i.path)
    .filter((p) => (p === '/' ? location.pathname === '/' : location.pathname.startsWith(p)))

  const logout = async () => {
    await api.logout().catch(() => undefined)
    queryClient.clear()
    message.success('已登出')
    navigate('/login', { replace: true })
  }

  const menu = (
    <>
      <div className="brand">
        <div className="brand-logo">SF</div>
        <div>
          <div className="brand-name">Starfly 混剪矩陣</div>
          <div className="brand-sub">工廠短影音自動化平台</div>
        </div>
      </div>
      <Menu
        mode="inline"
        selectedKeys={selected}
        items={items}
        onClick={({ key }) => {
          navigate(key)
          setDrawerOpen(false)
        }}
        className="side-menu"
      />
    </>
  )

  return (
    <Layout className="app-shell">
      {isMobile ? (
        <Drawer
          placement="left"
          open={drawerOpen}
          onClose={() => setDrawerOpen(false)}
          size={260}
          styles={{ body: { padding: 0 } }}
          closable={false}
        >
          {menu}
        </Drawer>
      ) : (
        <Sider width={236} theme="light" className="app-sider">
          {menu}
        </Sider>
      )}
      <Layout>
        <Header className="app-header">
          {isMobile ? (
            <Button type="text" icon={<MenuOutlined />} onClick={() => setDrawerOpen(true)} aria-label="開啟選單" />
          ) : (
            <span />
          )}
          <Dropdown
            trigger={['click']}
            menu={{
              items: [
                { key: 'password', icon: <KeyOutlined />, label: '修改密碼' },
                { key: 'logout', icon: <LogoutOutlined />, label: '登出', danger: true },
              ],
              onClick: ({ key }) => (key === 'logout' ? logout() : setPasswordOpen(true)),
            }}
          >
            <Button type="text" className="user-button">
              <Avatar size="small" icon={<UserOutlined />} />
              <span>{me?.display_name}</span>
              <Tag color={isAdmin ? 'blue' : 'default'}>{isAdmin ? '管理員' : '拍攝員'}</Tag>
            </Button>
          </Dropdown>
        </Header>
        <Content className="app-content">
          <Outlet />
        </Content>
      </Layout>
      <ChangePasswordModal open={passwordOpen} onClose={() => setPasswordOpen(false)} />
    </Layout>
  )
}
