import React from 'react'
import Plot from 'react-plotly.js'
import type { Data, Layout } from 'plotly.js'

interface ConfidenceGaugeProps {
  value: number // 0-1 or 0-100
  label?: string
  size?: number
  showPercent?: boolean
  isScore?: boolean // if true value is 0-100, else 0-1
}

export const ConfidenceGauge: React.FC<ConfidenceGaugeProps> = ({
  value,
  label = 'Confidence',
  size = 200,
  showPercent = true,
  isScore = false,
}) => {
  const displayValue = isScore ? value : value * 100
  const normalizedValue = isScore ? value : value * 100

  const getColor = (v: number): string => {
    if (v >= 75) return '#16A34A'
    if (v >= 50) return '#D97706'
    if (v >= 25) return '#EA580C'
    return '#DC2626'
  }

  const color = getColor(normalizedValue)

  const data: Data[] = [
    {
      type: 'indicator',
      mode: 'gauge+number',
      value: displayValue,
      number: {
        suffix: showPercent ? '%' : '',
        font: { size: size * 0.18, color: '#0D2137' },
        valueformat: '.0f',
      },
      gauge: {
        axis: {
          range: [0, 100],
          tickwidth: 1,
          tickcolor: '#CBD5E1',
          tickfont: { size: 9 },
          nticks: 5,
        },
        bar: { color, thickness: 0.25 },
        bgcolor: 'white',
        borderwidth: 1,
        bordercolor: '#E2E8F0',
        steps: [
          { range: [0, 25], color: '#FEE2E2' },
          { range: [25, 50], color: '#FEF3C7' },
          { range: [50, 75], color: '#D1FAE5' },
          { range: [75, 100], color: '#DCFCE7' },
        ],
        threshold: {
          line: { color: color, width: 3 },
          thickness: 0.75,
          value: normalizedValue,
        },
      },
      title: {
        text: label,
        font: { size: size * 0.08, color: '#475569' },
      },
    } as Data,
  ]

  const layout: Partial<Layout> = {
    paper_bgcolor: 'rgba(0,0,0,0)',
    margin: { t: size * 0.1, r: size * 0.05, b: size * 0.05, l: size * 0.05 },
    height: size,
    width: size,
  }

  return (
    <Plot
      data={data}
      layout={layout}
      config={{ displayModeBar: false, responsive: false }}
      style={{ width: size, height: size }}
    />
  )
}
