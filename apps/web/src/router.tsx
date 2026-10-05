import { createBrowserRouter, Navigate } from 'react-router'
import { AdminOnly, RequireAuth } from './auth'
import AppLayout from './layouts/AppLayout'
import { WORK_ITEMS } from './navigation'
import ChannelsPage from './pages/ChannelsPage'
import PublishChannelsPage from './pages/PublishChannelsPage'
import PublishAccountsPage from './pages/PublishAccountsPage'
import PublishTasksPage from './pages/PublishTasksPage'
import CommentsPage from './pages/CommentsPage'
import ComingSoonPage from './pages/ComingSoonPage'
import DashboardPage from './pages/DashboardPage'
import LoginPage from './pages/LoginPage'
import UsagePage from './pages/UsagePage'
import AssetsPage from './pages/assets/AssetsPage'
import ProfilesPage from './pages/ProfilesPage'
import TemplatesPage from './pages/templates/TemplatesPage'
import VoicesPage from './pages/VoicesPage'
import EditorPage from './pages/EditorPage'
import MusicPage from './pages/MusicPage'
import TasksPage from './pages/TasksPage'
import WorksPage from './pages/works/WorksPage'
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
        path: 'editor',
        element: (
          <AdminOnly>
            <EditorPage />
          </AdminOnly>
        ),
      },
      {
        path: 'works',
        element: (
          <AdminOnly>
            <WorksPage />
          </AdminOnly>
        ),
      },
      {
        path: 'tasks',
        element: (
          <AdminOnly>
            <TasksPage />
          </AdminOnly>
        ),
      },
      {
        path: 'music',
        element: (
          <AdminOnly>
            <MusicPage />
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
      { path: 'publish-accounts', element: <AdminOnly><PublishAccountsPage /></AdminOnly> },
      { path: 'publish-tasks', element: <AdminOnly><PublishTasksPage /></AdminOnly> },
      { path: 'comments', element: <AdminOnly><CommentsPage /></AdminOnly> },
      {
        path: 'settings/channels',
        element: (
          <AdminOnly>
            <ChannelsPage />
          </AdminOnly>
        ),
      },
      {
        path: 'settings/publish-channels',
        element: (
          <AdminOnly>
            <PublishChannelsPage />
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
