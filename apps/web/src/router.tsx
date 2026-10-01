import { createBrowserRouter, Navigate } from 'react-router'
import { AdminOnly, RequireAuth } from './auth'
import AppLayout from './layouts/AppLayout'
import { WORK_ITEMS } from './navigation'
import ChannelsPage from './pages/ChannelsPage'
import ComingSoonPage from './pages/ComingSoonPage'
import DashboardPage from './pages/DashboardPage'
import LoginPage from './pages/LoginPage'
import UsagePage from './pages/UsagePage'
import AssetsPage from './pages/assets/AssetsPage'
import ProfilesPage from './pages/ProfilesPage'
import TemplatesPage from './pages/templates/TemplatesPage'
import VoicesPage from './pages/VoicesPage'
import UsersPage from './pages/UsersPage'

const comingSoon = WORK_ITEMS.filter((item) => item.phase).map((item) => ({
  path: item.path.slice(1),
  element: item.adminOnly ? (
    <AdminOnly>
      <ComingSoonPage item={item} />
    </AdminOnly>
  ) : (
    <ComingSoonPage item={item} />
  ),
}))

export const router = createBrowserRouter([
  { path: '/login', element: <LoginPage /> },
  {
    path: '/',
    element: (
      <RequireAuth>
        <AppLayout />
      </RequireAuth>
    ),
    children: [
      { index: true, element: <DashboardPage /> },
      { path: 'assets', element: <AssetsPage /> },
      {
        path: 'profiles',
        element: (
          <AdminOnly>
            <ProfilesPage />
          </AdminOnly>
        ),
      },
      {
        path: 'templates',
        element: (
          <AdminOnly>
            <TemplatesPage />
          </AdminOnly>
        ),
      },
      {
        path: 'voices',
        element: (
          <AdminOnly>
            <VoicesPage />
          </AdminOnly>
        ),
      },
      ...comingSoon,
      {
        path: 'settings/channels',
        element: (
          <AdminOnly>
            <ChannelsPage />
          </AdminOnly>
        ),
      },
      {
        path: 'settings/usage',
        element: (
          <AdminOnly>
            <UsagePage />
          </AdminOnly>
        ),
      },
      {
        path: 'settings/users',
        element: (
          <AdminOnly>
            <UsersPage />
          </AdminOnly>
        ),
      },
      { path: '*', element: <Navigate to="/" replace /> },
    ],
  },
])
