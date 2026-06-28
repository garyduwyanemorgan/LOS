import React, { useMemo } from 'react'
import Plot from 'react-plotly.js'
import type { Data, Layout } from 'plotly.js'
import type { TimeSeriesPoint } from '@/types'

interface Series {
  name: string
  data: TimeSeriesPoint[]
  unit: string
  color?: string
  showConfidence?: boolean
  yAxis?: 'y' | 'y2'
}

interface TimeSeriesChartProps {
  series: Series[]
  title?: string
  height?: number
  showRangeSelector?: boolean
  thresholds?: Array<{ value: number; label: string; color: string; yAxis?: 'y' | 'y2' }>
}

const DEFAULT_COLORS = ['#0891B2', '#16A34A', '#D97706', '#DC2626', '#7C3AED', '#EC4899']

export const TimeSeriesChart: React.FC<TimeSeriesChartProps> = ({
  series,
  title,
  height = 350,
  showRangeSelector = true,
  thresholds = [],
}) => {
  const traces = useMemo<Data[]>(() => {
    const allTraces: Data[] = []

    series.forEach((s, i) => {
      const color = s.color ?? DEFAULT_COLORS[i % DEFAULT_COLORS.length]
      const timestamps = s.data.map((d) => d.timestamp)
      const values = s.data.map((d) => d.value)

      // Main line
      allTraces.push({
        type: 'scatter',
        mode: 'lines+markers',
        name: `${s.name} (${s.unit})`,
        x: timestamps,
        y: values,
        line: { color, width: 2 },
        marker: { size: 4, color },
        yaxis: s.yAxis ?? 'y',
        hovertemplate: `<b>${s.name}</b><br>%{x}<br>%{y:.3f} ${s.unit}<extra></extra>`,
      } as Data)

      // Confidence envelope if available
      if (s.showConfidence && s.data.some((d) => d.confidence !== undefined)) {
        const lowerBound = s.data.map((d) =>
          d.confidence !== undefined ? d.value * (2 - d.confidence) - d.value * (1 - d.confidence) : d.value
        )
        const upperBound = s.data.map((d) =>
          d.confidence !== undefined ? d.value + d.value * (1 - d.confidence) * 0.1 : d.value
        )

        allTraces.push({
          type: 'scatter',
          mode: 'lines',
          name: `${s.name} upper`,
          x: timestamps,
          y: upperBound,
          line: { width: 0 },
          showlegend: false,
          yaxis: s.yAxis ?? 'y',
          hoverinfo: 'skip',
        } as Data)

        allTraces.push({
          type: 'scatter',
          mode: 'lines',
          name: `${s.name} confidence`,
          x: timestamps,
          y: lowerBound,
          fill: 'tonexty',
          fillcolor: `${color}22`,
          line: { width: 0 },
          showlegend: false,
          yaxis: s.yAxis ?? 'y',
          hoverinfo: 'skip',
        } as Data)
      }
    })

    // Threshold lines
    thresholds.forEach((t) => {
      allTraces.push({
        type: 'scatter',
        mode: 'lines',
        name: t.label,
        x: series[0]?.data.map((d) => d.timestamp) ?? [],
        y: series[0]?.data.map(() => t.value) ?? [],
        line: { color: t.color, width: 1.5, dash: 'dash' },
        yaxis: t.yAxis ?? 'y',
        hovertemplate: `<b>${t.label}</b>: ${t.value}<extra></extra>`,
      } as Data)
    })

    return allTraces
  }, [series, thresholds])

  const layout = useMemo<Partial<Layout>>(() => {
    const hasY2 = series.some((s) => s.yAxis === 'y2')
    return {
      title: title
        ? { text: title, font: { size: 14, color: '#0D2137' } }
        : undefined,
      paper_bgcolor: 'rgba(0,0,0,0)',
      plot_bgcolor: 'rgba(0,0,0,0)',
      margin: { t: title ? 40 : 20, r: hasY2 ? 60 : 20, b: 60, l: 60 },
      height,
      xaxis: {
        type: 'date',
        showgrid: true,
        gridcolor: '#E2E8F0',
        tickfont: { size: 11 },
        rangeselector: showRangeSelector
          ? {
              buttons: [
                { count: 1, label: '1d', step: 'day', stepmode: 'backward' },
                { count: 7, label: '7d', step: 'day', stepmode: 'backward' },
                { count: 30, label: '30d', step: 'day', stepmode: 'backward' },
                { step: 'all', label: 'All' },
              ],
              bgcolor: '#F8FAFC',
              activecolor: '#0891B2',
            }
          : undefined,
      },
      yaxis: {
        showgrid: true,
        gridcolor: '#E2E8F0',
        tickfont: { size: 11 },
        title: series[0] ? { text: series[0].unit, font: { size: 11 } } : undefined,
      },
      yaxis2: hasY2
        ? {
            overlaying: 'y',
            side: 'right',
            showgrid: false,
            tickfont: { size: 11 },
            title: series.find((s) => s.yAxis === 'y2')
              ? { text: series.find((s) => s.yAxis === 'y2')!.unit, font: { size: 11 } }
              : undefined,
          }
        : undefined,
      legend: { orientation: 'h', y: -0.2, x: 0 },
      hovermode: 'x unified',
    }
  }, [series, title, height, showRangeSelector])

  if (!series.length || series.every((s) => !s.data.length)) {
    return (
      <div
        className="flex items-center justify-center text-slate-400 text-sm"
        style={{ height }}
      >
        No data available
      </div>
    )
  }

  return (
    <Plot
      data={traces}
      layout={layout}
      config={{ displayModeBar: true, responsive: true, displaylogo: false }}
      style={{ width: '100%', height }}
      useResizeHandler
    />
  )
}
