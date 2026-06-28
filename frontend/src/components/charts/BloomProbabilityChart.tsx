import React, { useMemo } from 'react'
import Plot from 'react-plotly.js'
import type { Data, Layout } from 'plotly.js'

interface BloomDataPoint {
  timestamp: string
  probability: number
  lower?: number
  upper?: number
}

interface BloomProbabilityChartProps {
  data: BloomDataPoint[]
  height?: number
  title?: string
  showForecast?: boolean
  forecastStartDate?: string
}

export const BloomProbabilityChart: React.FC<BloomProbabilityChartProps> = ({
  data,
  height = 300,
  title = 'Bloom Probability',
  showForecast = false,
  forecastStartDate,
}) => {
  const historical = useMemo(
    () => (forecastStartDate ? data.filter((d) => d.timestamp < forecastStartDate) : data),
    [data, forecastStartDate]
  )
  const forecast = useMemo(
    () => (forecastStartDate ? data.filter((d) => d.timestamp >= forecastStartDate) : []),
    [data, forecastStartDate]
  )

  const traces = useMemo<Data[]>(() => {
    const result: Data[] = []

    // Historical area
    if (historical.length > 0) {
      result.push({
        type: 'scatter',
        mode: 'lines',
        name: 'Bloom Probability',
        x: historical.map((d) => d.timestamp),
        y: historical.map((d) => d.probability * 100),
        fill: 'tozeroy',
        fillcolor: 'rgba(8, 145, 178, 0.15)',
        line: { color: '#0891B2', width: 2 },
        hovertemplate: '<b>Probability</b>: %{y:.1f}%<br>%{x}<extra></extra>',
      } as Data)
    }

    // Forecast line
    if (showForecast && forecast.length > 0) {
      result.push({
        type: 'scatter',
        mode: 'lines',
        name: 'Forecast',
        x: forecast.map((d) => d.timestamp),
        y: forecast.map((d) => d.probability * 100),
        line: { color: '#D97706', width: 2, dash: 'dash' },
        hovertemplate: '<b>Forecast</b>: %{y:.1f}%<br>%{x}<extra></extra>',
      } as Data)

      // Forecast confidence band
      if (forecast.some((d) => d.upper !== undefined)) {
        result.push({
          type: 'scatter',
          mode: 'lines',
          name: 'Upper bound',
          x: forecast.map((d) => d.timestamp),
          y: forecast.map((d) => (d.upper ?? d.probability) * 100),
          line: { width: 0 },
          showlegend: false,
          hoverinfo: 'skip',
        } as Data)
        result.push({
          type: 'scatter',
          mode: 'lines',
          name: 'Forecast range',
          x: forecast.map((d) => d.timestamp),
          y: forecast.map((d) => (d.lower ?? d.probability) * 100),
          fill: 'tonexty',
          fillcolor: 'rgba(217, 119, 6, 0.12)',
          line: { width: 0 },
          showlegend: false,
          hoverinfo: 'skip',
        } as Data)
      }
    }

    return result
  }, [historical, forecast, showForecast])

  const layout = useMemo<Partial<Layout>>(
    () => ({
      title: title ? { text: title, font: { size: 13, color: '#0D2137' } } : undefined,
      paper_bgcolor: 'rgba(0,0,0,0)',
      plot_bgcolor: 'rgba(0,0,0,0)',
      height,
      margin: { t: title ? 40 : 10, r: 20, b: 50, l: 50 },
      xaxis: { type: 'date', showgrid: true, gridcolor: '#E2E8F0', tickfont: { size: 11 } },
      yaxis: {
        range: [0, 100],
        showgrid: true,
        gridcolor: '#E2E8F0',
        tickfont: { size: 11 },
        title: { text: 'Probability (%)', font: { size: 11 } },
      },
      shapes: [
        // Warning threshold at 40%
        {
          type: 'line',
          x0: data[0]?.timestamp ?? '',
          x1: data[data.length - 1]?.timestamp ?? '',
          y0: 40,
          y1: 40,
          line: { color: '#D97706', width: 1.5, dash: 'dot' },
        },
        // Critical threshold at 70%
        {
          type: 'line',
          x0: data[0]?.timestamp ?? '',
          x1: data[data.length - 1]?.timestamp ?? '',
          y0: 70,
          y1: 70,
          line: { color: '#DC2626', width: 1.5, dash: 'dot' },
        },
      ],
      annotations: [
        {
          x: data[data.length - 1]?.timestamp ?? '',
          y: 40,
          text: 'Warning',
          showarrow: false,
          xanchor: 'right',
          font: { size: 10, color: '#D97706' },
        },
        {
          x: data[data.length - 1]?.timestamp ?? '',
          y: 70,
          text: 'Critical',
          showarrow: false,
          xanchor: 'right',
          font: { size: 10, color: '#DC2626' },
        },
      ],
      legend: { orientation: 'h', y: -0.2 },
      hovermode: 'x unified',
    }),
    [data, title, height]
  )

  if (!data.length) {
    return (
      <div className="flex items-center justify-center text-slate-400 text-sm" style={{ height }}>
        No bloom data available
      </div>
    )
  }

  return (
    <Plot
      data={traces}
      layout={layout}
      config={{ displayModeBar: false, responsive: true, displaylogo: false }}
      style={{ width: '100%', height }}
      useResizeHandler
    />
  )
}
