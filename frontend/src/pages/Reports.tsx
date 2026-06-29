import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { useLagoonStore } from '@/stores/lagoon.store'
import { api } from '@/lib/api'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { FileText, Download, Plus, Clock } from 'lucide-react'

const REPORT_TYPES = [
  { value: 'executive', label: 'Executive Summary' },
  { value: 'operational', label: 'Operational Report' },
  { value: 'scientific', label: 'Scientific Report' },
  { value: 'compliance', label: 'Compliance Report' },
]

export default function Reports() {
  const { selectedLagoon } = useLagoonStore()
  const [selectedType, setSelectedType] = useState('executive')

  const { data: reports, isLoading, refetch } = useQuery({
    queryKey: ['reports', selectedLagoon?.id],
    queryFn: () => api.reports.list(selectedLagoon!.id),
    enabled: !!selectedLagoon,
  })

  const generateMutation = useMutation({
    mutationFn: () =>
      api.reports.generate({
        lagoon_id: selectedLagoon!.id,
        report_type: selectedType,
        period_start: new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString(),
        period_end: new Date().toISOString(),
      }),
    onSuccess: () => refetch(),
  })

  if (!selectedLagoon) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-muted-foreground">Select a lagoon to view reports.</p>
      </div>
    )
  }

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Reports</h1>
          <p className="text-muted-foreground text-sm mt-1">
            {selectedLagoon.name} — Generated performance and compliance reports
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Select value={selectedType} onValueChange={setSelectedType}>
            <SelectTrigger className="w-[220px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {REPORT_TYPES.map(t => (
                <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            onClick={() => generateMutation.mutate()}
            disabled={generateMutation.isPending}
          >
            <Plus className="h-4 w-4 mr-2" />
            {generateMutation.isPending ? 'Generating...' : 'Generate'}
          </Button>
        </div>
      </div>

      {generateMutation.isError && (
        <div className="rounded-md bg-destructive/10 border border-destructive/20 px-4 py-3 text-sm text-destructive">
          Failed to generate report. Please try again.
        </div>
      )}

      {isLoading ? (
        <div className="space-y-3">
          {[1, 2, 3].map(i => (
            <div key={i} className="h-20 rounded-lg bg-muted animate-pulse" />
          ))}
        </div>
      ) : (
        <div className="space-y-3">
          {reports?.map((report: any) => (
            <Card key={report.id}>
              <CardContent className="flex items-center gap-4 p-4">
                <FileText className="h-8 w-8 text-muted-foreground flex-shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="font-medium text-sm truncate">
                    {REPORT_TYPES.find(t => t.value === report.report_type)?.label ?? report.report_type}
                  </p>
                  <div className="flex items-center gap-2 mt-1">
                    <Clock className="h-3 w-3 text-muted-foreground" />
                    <span className="text-xs text-muted-foreground">
                      {new Date(report.created_at ?? report.generated_at).toLocaleString()}
                    </span>
                  </div>
                </div>
                <Badge
                  variant={
                    report.status === 'completed' ? 'default' :
                    report.status === 'generating' ? 'secondary' : 'destructive'
                  }
                >
                  {report.status}
                </Badge>
                {report.status === 'completed' && (
                  <Button variant="ghost" size="sm" asChild>
                    <a href={report.download_url} download>
                      <Download className="h-4 w-4" />
                    </a>
                  </Button>
                )}
              </CardContent>
            </Card>
          ))}
          {(!reports || reports.length === 0) && (
            <Card>
              <CardContent className="flex items-center justify-center py-16">
                <div className="text-center">
                  <FileText className="h-12 w-12 text-muted-foreground mx-auto mb-3" />
                  <p className="text-muted-foreground text-sm">No reports generated yet.</p>
                  <p className="text-xs text-muted-foreground mt-1">
                    Select a report type and click Generate to create your first report.
                  </p>
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      )}
    </div>
  )
}
