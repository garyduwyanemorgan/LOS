import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { Lagoon, SystemState, ScientificLoopState } from '@/types'
import { lagoonApi } from '@/lib/api'

interface LagoonState {
  lagoons: Lagoon[]
  selectedLagoonId: string | null
  selectedLagoon: Lagoon | null
  systemState: SystemState | null
  isLoadingLagoons: boolean
  isLoadingState: boolean
  error: string | null
}

interface LagoonActions {
  fetchLagoons: () => Promise<void>
  selectLagoon: (id: string) => void
  fetchSystemState: (lagoonId: string) => Promise<void>
  updateLoopState: (loop: ScientificLoopState) => void
  clearError: () => void
}

export const useLagoonStore = create<LagoonState & LagoonActions>()(
  persist(
    (set, get) => ({
      lagoons: [],
      selectedLagoonId: null,
      selectedLagoon: null,
      systemState: null,
      isLoadingLagoons: false,
      isLoadingState: false,
      error: null,

      fetchLagoons: async () => {
        set({ isLoadingLagoons: true, error: null })
        try {
          const lagoons = await lagoonApi.list()
          const currentId = get().selectedLagoonId
          set({
            lagoons,
            isLoadingLagoons: false,
            selectedLagoon: lagoons.find((l) => l.id === currentId) ?? lagoons[0] ?? null,
            selectedLagoonId: currentId ?? lagoons[0]?.id ?? null,
          })
        } catch (err) {
          const message = err instanceof Error ? err.message : 'Failed to load lagoons'
          set({ isLoadingLagoons: false, error: message })
        }
      },

      selectLagoon: (id) => {
        const lagoon = get().lagoons.find((l) => l.id === id) ?? null
        set({ selectedLagoonId: id, selectedLagoon: lagoon, systemState: null })
      },

      fetchSystemState: async (lagoonId) => {
        set({ isLoadingState: true })
        try {
          const state = await lagoonApi.getStatus(lagoonId)
          set({ systemState: state, isLoadingState: false })
        } catch (err) {
          const message = err instanceof Error ? err.message : 'Failed to load system state'
          set({ isLoadingState: false, error: message })
        }
      },

      updateLoopState: (loopUpdate) => {
        const current = get().systemState
        if (!current) return
        const loops = current.loops.map((l) =>
          l.loop === loopUpdate.loop ? { ...l, ...loopUpdate } : l
        )
        set({ systemState: { ...current, loops } })
      },

      clearError: () => set({ error: null }),
    }),
    {
      name: 'los-lagoon',
      partialize: (state) => ({
        selectedLagoonId: state.selectedLagoonId,
      }),
    }
  )
)
