import React, { useMemo } from 'react'
import {
  RadarChart,
  Radar,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  ResponsiveContainer,
  Legend,
  Tooltip,
} from 'recharts'

interface RadarParameter {
  parameter: string
  current: number
  target: number
  unit: string
  maxValue: number
}

interface WaterQualityRadarProps {
  parameters: RadarParameter[]
  height?: number
}

export const WaterQualityRadar: React.FC<WaterQualityRadarProps> = ({
  parameters,
  height = 300,
}) => {
  const data = useMemo(
    () =>
      parameters.map((p) => ({
        subject: p.parameter,
        current: Math.min(100, (p.current / p.maxValue) * 100),
        target: Math.min(100, (p.target / p.maxValue) * 100),
        currentRaw: p.current,
        targetRaw: p.target,
        unit: p.unit,
      })),
    [parameters]
  )

  const CustomTooltip = ({
    active,
    payload,
  }: {
    active?: boolean
    payload?: Array<{ payload: (typeof data)[0]; name: string; value: number }>
  }) => {
    if (!active || !payload?.length) return null
    const item = payload[0].payload
    return (
      <div className="bg-white border border-slate-200 rounded-md p-3 shadow-sm text-xs">
        <p className="font-semibold text-slate-800 mb-1">{item.subject}</p>
        <p className="text-[#0891B2]">
          Current: {item.currentRaw.toFixed(2)} {item.unit}
        </p>
        <p className="text-[#16A34A]">
          Target: {item.targetRaw.toFixed(2)} {item.unit}
        </p>
      </div>
    )
  }

  if (!parameters.length) {
    return (
      <div className="flex items-center justify-center text-slate-400 text-sm" style={{ height }}>
        No parameters to display
      </div>
    )
  }

  return (
    <ResponsiveContainer width="100%" height={height}>
      <RadarChart data={data} margin={{ top: 10, right: 30, bottom: 10, left: 30 }}>
        <PolarGrid stroke="#E2E8F0" />
        <PolarAngleAxis
          dataKey="subject"
          tick={{ fill: '#475569', fontSize: 11 }}
        />
        <PolarRadiusAxis
          angle={90}
          domain={[0, 100]}
          tick={{ fill: '#94A3B8', fontSize: 9 }}
          tickCount={5}
        />
        <Radar
          name="Current"
          dataKey="current"
          stroke="#0891B2"
          fill="#0891B2"
          fillOpacity={0.15}
          strokeWidth={2}
        />
        <Radar
          name="Target"
          dataKey="target"
          stroke="#16A34A"
          fill="#16A34A"
          fillOpacity={0.1}
          strokeWidth={2}
          strokeDasharray="4 2"
        />
        <Tooltip content={<CustomTooltip />} />
        <Legend
          iconType="line"
          wrapperStyle={{ fontSize: '12px', paddingTop: '8px' }}
        />
      </RadarChart>
    </ResponsiveContainer>
  )
}
