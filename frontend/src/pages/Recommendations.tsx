import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useLagoonStore } from '@/stores/lagoon.store'
import { api } from '@/lib/api'
import { RecommendationCard } from '@/components/shared/RecommendationCard'
import { Card, CardContent } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { CheckCircle, XCircle, Clock, BarChart3 } from 'lucide-react'

const STATUS_TABS = [
  { value: 'pending', label: 'Pending', icon: Clock },
  { value: 'approved', label: 'Approved', icon: CheckCircle },
  { value: 'rejected', label: 'Rejected', icon: XCircle },
  { value: 'implemented', label: 'Implemented', icon: BarChart3 },
]

export default function Recommendations() {
  const { selectedLagoon } = useLagoonStore()
  const [activeTab, setActiveTab] = useState('pending')
  const queryClient = useQueryClient()

  const { data: recommendations, isLoading } = useQuery({
    queryKey: ['recommendations', selectedLagoon?.id, activeTab],
    queryFn: () =>
      api.recommendations.list(selectedLagoon!.id, {
        status: activeTab,
        limit: 50,
      }),
    enabled: !!selectedLagoon,
    refetchInterval: activeTab === 'pending' ? 60_000 : 300_000,
  })

  const approveMutation = useMutation({
    mutationFn: ({ id, notes }: { id: string; notes?: string }) =>
      api.recommendations.approve(id, { notes }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['recommendations', selectedLagoon?.id] })
    },
  })

  const rejectMutation = useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) =>
      api.recommendations.reject(id, { reason }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['recommendations', selectedLagoon?.id] })
    },
  })

  if (!selectedLagoon) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-muted-foreground">Select a lagoon to view recommendations.</p>
      </div>
    )
  }

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Recommendations</h1>
          <p className="text-muted-foreground text-sm mt-1">
            {selectedLagoon.name} — Decision Engine recommendations awaiting operator review
          </p>
        </div>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          {STATUS_TABS.map(({ value, label, icon: Icon }) => (
            <TabsTrigger key={value} value={value} className="flex items-center gap-2">
              <Icon className="h-3.5 w-3.5" />
              {label}
            </TabsTrigger>
          ))}
        </TabsList>

        {STATUS_TABS.map(({ value }) => (
          <TabsContent key={value} value={value} className="mt-4">
            {isLoading ? (
              <div className="space-y-3">
                {[1, 2, 3].map(i => (
                  <div key={i} className="h-40 rounded-lg bg-muted animate-pulse" />
                ))}
              </div>
            ) : recommendations && recommendations.length > 0 ? (
              <div className="space-y-4">
                {recommendations.map((rec: any) => (
                  <RecommendationCard
                    key={rec.id}
                    recommendation={rec}
                    expanded
                    onApprove={
                      value === 'pending'
                        ? async (id: string, notes?: string) => { await approveMutation.mutateAsync({ id, notes }) }
                        : undefined
                    }
                    onReject={
                      value === 'pending'
                        ? async (id: string, reason: string) => { await rejectMutation.mutateAsync({ id, reason }) }
                        : undefined
                    }
                  />
                ))}
              </div>
            ) : (
              <Card>
                <CardContent className="flex items-center justify-center py-16">
                  <p className="text-muted-foreground text-sm">
                    No {value} recommendations.
                  </p>
                </CardContent>
              </Card>
            )}
          </TabsContent>
        ))}
      </Tabs>
    </div>
  )
}
