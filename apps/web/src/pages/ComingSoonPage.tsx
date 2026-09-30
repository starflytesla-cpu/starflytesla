import { RocketOutlined } from '@ant-design/icons'
import { Card, Result } from 'antd'
import PageHeader from '../components/PageHeader'
import type { NavItem } from '../navigation'

export default function ComingSoonPage({ item }: { item: NavItem }) {
  return (
    <>
      <PageHeader title={item.label} subtitle={item.description} />
      <Card>
        <Result
          icon={<RocketOutlined />}
          title={`Phase ${item.phase} 開發中`}
          subTitle="這個功能會在對應階段完成後上線，目前先把基礎建設打好。"
        />
      </Card>
    </>
  )
}
