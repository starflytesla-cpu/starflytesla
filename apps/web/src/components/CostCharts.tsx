import { Card, Col, Empty, Row } from 'antd'
import { BarChart, PieChart } from 'echarts/charts'
import { AriaComponent, GraphicComponent, GridComponent, TooltipComponent } from 'echarts/components'
import { init, use as registerCharts, type EChartsCoreOption } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { useEffect, useRef } from 'react'
import { formatUsd } from '../api'

registerCharts([BarChart, PieChart, GraphicComponent, GridComponent, TooltipComponent, AriaComponent, CanvasRenderer])
export type ModelCost = {
  provider: string
  model_key: string
  calls: number
  input_tokens: number
  output_tokens: number
  cost_usd: number
}
const COLORS = ['#2f6bff', '#8b6ee8', '#31a7a0', '#e7a349', '#64829e']

function Chart({ option, label }: { option: EChartsCoreOption; label: string }) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const element = ref.current!
    let chart: ReturnType<typeof init> | undefined
    const resize = () => {
      if (!element.clientWidth || !element.clientHeight) return
      if (!chart) {
        chart = init(element)
        chart.setOption({ ...option, aria: { enabled: true, label: { description: label } } })
      } else chart.resize()
    }
    const observer = new ResizeObserver(resize)
    observer.observe(element)
    resize()
    return () => {
      observer.disconnect()
      chart?.dispose()
    }
  }, [option, label])
  return <div className="cost-chart" ref={ref} role="img" aria-label={label} />
}

export default function CostCharts({ models }: { models: ModelCost[] }) {
  const totals = new Map<string, number>()
  for (const model of models) totals.set(model.provider, (totals.get(model.provider) ?? 0) + model.cost_usd)
  const providers = [...totals].filter(([, cost]) => cost > 0).sort((a, b) => b[1] - a[1])
  const ranked = [...models]
    .filter((m) => m.cost_usd > 0)
    .sort((a, b) => b.cost_usd - a.cost_usd)
    .slice(0, 5)
    .reverse()
  const total = providers.reduce((sum, [, cost]) => sum + cost, 0)
  const donut: EChartsCoreOption = {
    animation: false,
    color: COLORS,
    aria: { enabled: true },
    tooltip: {
      trigger: 'item',
      valueFormatter: (v: unknown) => formatUsd(Number(v)),
    },
    series: [
      {
        type: 'pie',
        radius: ['58%', '80%'],
        center: ['50%', '50%'],
        label: { show: false },
        data: providers.map(([name, value]) => ({ name, value })),
      },
    ],
    graphic: {
      type: 'text',
      left: 'center',
      top: 'middle',
      style: {
        text: formatUsd(total),
        font: '600 24px sans-serif',
        fill: '#202b40',
      },
    },
  }
  const bars: EChartsCoreOption = {
    animation: false,
    color: COLORS,
    aria: { enabled: true },
    tooltip: {
      trigger: 'axis',
      valueFormatter: (v: unknown) => formatUsd(Number(v)),
    },
    grid: { left: 12, right: 72, top: 16, bottom: 8, containLabel: true },
    xAxis: { type: 'value', show: false },
    yAxis: {
      type: 'category',
      data: ranked.map((m) => m.model_key),
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { width: 170, overflow: 'truncate', color: '#626e82' },
    },
    series: [
      {
        type: 'bar',
        data: ranked.map((m) => m.cost_usd),
        barMaxWidth: 24,
        itemStyle: { borderRadius: [0, 5, 5, 0] },
        label: {
          show: true,
          position: 'right',
          formatter: ({ value }: { value: unknown }) => formatUsd(Number(value)),
        },
      },
    ],
  }
  return (
    <Row gutter={[16, 16]} className="section">
      <Col xs={24} lg={10}>
        <Card title="服務商花費分布" className="full-height">
          {total > 0 ? (
            <>
              <Chart option={donut} label={`已知花費 ${formatUsd(total)}，服務商分布`} />
              <div className="chart-legend">
                {providers.map(([name, cost], i) => (
                  <div key={name}>
                    <span className="legend-dot" style={{ background: COLORS[i % COLORS.length] }} />
                    <span>{name}</span>
                    <strong>{formatUsd(cost)}</strong>
                    <span>{((cost / total) * 100).toFixed(1)}%</span>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <Empty description="本月尚無已知花費" />
          )}
          <p className="small muted">只計入已知價格；未定價呼叫不列入分布。</p>
        </Card>
      </Col>
      <Col xs={24} lg={14}>
        <Card title="模型花費排行 · 前 5 名" className="full-height">
          {ranked.length ? (
            <Chart option={bars} label="模型已知花費排行，完整數值見下方表格" />
          ) : (
            <Empty description="本月尚無已知花費" />
          )}
          <p className="small muted">依已知花費排序，可在下方核對所有模型。</p>
        </Card>
      </Col>
    </Row>
  )
}
