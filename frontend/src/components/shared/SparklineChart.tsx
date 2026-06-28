import React from 'react'
import { LineChart, Line, ResponsiveContainer } from 'recharts'

export const SparklineChart: React.FC<{ data: number[]; color?: string }> = ({
  data,
  color = '#0891B2',
}) => {
  const chartData = data.map((v, i) => ({ i, v }))
  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={chartData} margin={{ top: 0, right: 0, bottom: 0, left: 0 }}>
        <Line
          type="monotone"
          dataKey="v"
          stroke={color}
          strokeWidth={1.5}
          dot={false}
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  )
}
