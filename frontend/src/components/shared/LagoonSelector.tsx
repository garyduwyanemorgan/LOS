import React from 'react'
import { MapPin, ChevronDown } from 'lucide-react'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useLagoonStore } from '@/stores/lagoon.store'

interface LagoonSelectorProps {
  className?: string
}

export const LagoonSelector: React.FC<LagoonSelectorProps> = ({ className }) => {
  const { lagoons, selectedLagoonId, selectLagoon, isLoadingLagoons } = useLagoonStore()

  if (isLoadingLagoons) {
    return (
      <div className="flex items-center gap-2 px-3 py-2 bg-white/10 rounded-md text-white text-sm">
        <MapPin className="h-4 w-4 opacity-70" />
        <span className="opacity-70">Loading...</span>
      </div>
    )
  }

  if (!lagoons.length) {
    return (
      <div className="flex items-center gap-2 px-3 py-2 bg-white/10 rounded-md text-white text-sm opacity-60">
        <MapPin className="h-4 w-4" />
        <span>No lagoons</span>
      </div>
    )
  }

  return (
    <Select
      value={selectedLagoonId ?? undefined}
      onValueChange={(val) => selectLagoon(val)}
    >
      <SelectTrigger
        className={`bg-white/10 border-white/20 text-white hover:bg-white/20 focus:ring-white/30 ${className ?? ''}`}
      >
        <MapPin className="h-4 w-4 mr-2 shrink-0 opacity-80" />
        <SelectValue placeholder="Select lagoon" />
      </SelectTrigger>
      <SelectContent>
        {lagoons.map((lagoon) => (
          <SelectItem key={lagoon.id} value={lagoon.id}>
            <div className="flex flex-col">
              <span className="font-medium">{lagoon.name}</span>
              <span className="text-xs text-slate-500">
                {lagoon.location.city}, {lagoon.location.country}
              </span>
            </div>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
