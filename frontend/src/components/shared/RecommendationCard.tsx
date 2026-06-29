import React, { useState } from 'react'
import {
  ChevronDown,
  ChevronUp,
  CheckCircle,
  XCircle,
  Clock,
  AlertTriangle,
} from 'lucide-react'
import type { Recommendation } from '@/types'
import { cn, priorityBg, formatRelative } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { ConfidenceIndicator } from './ConfidenceIndicator'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

interface RecommendationCardProps {
  recommendation: Recommendation
  onApprove?: (id: string, notes?: string) => Promise<void>
  onReject?: (id: string, reason: string) => Promise<void>
  showActions?: boolean
  defaultExpanded?: boolean
  expanded?: boolean
  className?: string
}

const LOOP_COLORS: Record<string, string> = {
  HYDROLOGICAL: 'bg-cyan-100 text-cyan-700',
  CHEMICAL: 'bg-purple-100 text-purple-700',
  ECOLOGICAL: 'bg-green-100 text-green-700',
  INFRASTRUCTURE: 'bg-amber-100 text-amber-700',
}

const STATUS_ICONS: Record<string, React.ReactNode> = {
  pending: <Clock className="h-4 w-4 text-amber-500" />,
  approved: <CheckCircle className="h-4 w-4 text-green-500" />,
  rejected: <XCircle className="h-4 w-4 text-red-500" />,
  implemented: <CheckCircle className="h-4 w-4 text-blue-500" />,
  measured: <CheckCircle className="h-4 w-4 text-slate-500" />,
}

export const RecommendationCard: React.FC<RecommendationCardProps> = ({
  recommendation: rec,
  onApprove,
  onReject,
  showActions = true,
  defaultExpanded = false,
  expanded: expandedProp,
  className,
}) => {
  const [expandedState, setExpandedState] = useState(defaultExpanded)
  const expanded = expandedProp ?? expandedState
  const setExpanded = (v: boolean) => { if (expandedProp === undefined) setExpandedState(v) }
  const [approveDialogOpen, setApproveDialogOpen] = useState(false)
  const [rejectDialogOpen, setRejectDialogOpen] = useState(false)
  const [approveNotes, setApproveNotes] = useState('')
  const [rejectReason, setRejectReason] = useState('')
  const [loading, setLoading] = useState(false)

  const handleApprove = async () => {
    if (!onApprove) return
    setLoading(true)
    try {
      await onApprove(rec.id, approveNotes || undefined)
      setApproveDialogOpen(false)
      setApproveNotes('')
    } finally {
      setLoading(false)
    }
  }

  const handleReject = async () => {
    if (!onReject || !rejectReason.trim()) return
    setLoading(true)
    try {
      await onReject(rec.id, rejectReason)
      setRejectDialogOpen(false)
      setRejectReason('')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div
      className={cn(
        'bg-white rounded-lg border shadow-sm overflow-hidden',
        rec.priority === 'critical' && 'border-red-200',
        rec.priority === 'high' && 'border-orange-200',
        className
      )}
    >
      {/* Priority stripe */}
      <div
        className={cn(
          'h-1',
          rec.priority === 'critical' && 'bg-red-500',
          rec.priority === 'high' && 'bg-orange-400',
          rec.priority === 'medium' && 'bg-amber-400',
          rec.priority === 'low' && 'bg-blue-400'
        )}
      />

      <div className="p-4">
        {/* Header */}
        <div className="flex items-start gap-3">
          <div className="flex-1 min-w-0">
            <div className="flex flex-wrap items-center gap-2 mb-1">
              <span className={cn('text-xs font-semibold px-2 py-0.5 rounded-full border', priorityBg(rec.priority))}>
                {rec.priority.toUpperCase()}
              </span>
              <span className="text-xs text-slate-500 bg-slate-100 px-2 py-0.5 rounded-full">
                {rec.action_category}
              </span>
              {STATUS_ICONS[rec.status] && (
                <span className="flex items-center gap-1 text-xs text-slate-500 capitalize">
                  {STATUS_ICONS[rec.status]}
                  {rec.status}
                </span>
              )}
            </div>
            <h3 className="font-semibold text-slate-900 text-sm leading-snug">{rec.action}</h3>
          </div>
          <ConfidenceIndicator confidence={rec.confidence} className="shrink-0" />
        </div>

        {/* Contributing loops */}
        <div className="flex flex-wrap gap-1 mt-2">
          {rec.contributing_loops.map((loop) => (
            <span
              key={loop}
              className={cn('text-xs px-1.5 py-0.5 rounded font-medium', LOOP_COLORS[loop] ?? 'bg-slate-100 text-slate-600')}
            >
              {loop}
            </span>
          ))}
        </div>

        {/* Scientific reason preview */}
        <p className="text-xs text-slate-600 mt-2 line-clamp-2">
          {rec.scientific_reason}
        </p>

        {/* Expand toggle */}
        <button
          className="flex items-center gap-1 text-xs text-[#0891B2] mt-2 hover:underline"
          onClick={() => setExpanded(!expanded)}
        >
          {expanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
          {expanded ? 'Show less' : 'Show full reasoning'}
        </button>

        {/* Expanded section */}
        {expanded && (
          <div className="mt-3 space-y-3 border-t pt-3">
            <div>
              <p className="text-xs font-semibold text-slate-700 mb-1">Scientific Reasoning</p>
              <p className="text-xs text-slate-600">{rec.scientific_reason}</p>
            </div>

            <div>
              <p className="text-xs font-semibold text-slate-700 mb-1">Expected Outcome</p>
              <p className="text-xs text-slate-600">{rec.expected_outcome}</p>
              <p className="text-xs text-slate-400 mt-0.5">
                Timeframe: {rec.expected_timeframe_days != null ? `~${rec.expected_timeframe_days} days` : 'Not specified'}
              </p>
            </div>

            {rec.evidence.length > 0 && (
              <div>
                <p className="text-xs font-semibold text-slate-700 mb-1">Supporting Evidence</p>
                <div className="space-y-1">
                  {rec.evidence.map((e, i) => (
                    <div key={i} className="flex items-start gap-2 text-xs text-slate-600">
                      <span className="text-slate-400 shrink-0">{e.source}:</span>
                      <span>{e.description}</span>
                      <ConfidenceIndicator confidence={e.confidence} showLabel={false} className="ml-auto shrink-0" />
                    </div>
                  ))}
                </div>
              </div>
            )}

            {rec.alternative_options.filter(alt => alt.action?.trim() || alt.reason_not_recommended?.trim()).length > 0 && (
              <div>
                <p className="text-xs font-semibold text-slate-700 mb-1">Alternatives Considered</p>
                <div className="space-y-1">
                  {rec.alternative_options
                    .filter(alt => alt.action?.trim() || alt.reason_not_recommended?.trim())
                    .map((alt, i) => (
                    <div key={i} className="text-xs text-slate-500 flex items-start gap-1">
                      <span className="text-slate-300 mt-0.5">—</span>
                      <span>
                        <span className="font-medium text-slate-600">{alt.action}</span>:{' '}
                        {alt.reason_not_recommended}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Footer */}
        <div className="flex items-center justify-between mt-3">
          <span className="text-xs text-slate-400">{formatRelative(rec.created_at)}</span>

          {showActions && rec.status === 'pending' && (
            <div className="flex gap-2">
              <Button
                size="xs"
                variant="outline"
                onClick={() => setRejectDialogOpen(true)}
                className="text-red-600 border-red-200 hover:bg-red-50"
              >
                Reject
              </Button>
              <Button
                size="xs"
                variant="success"
                onClick={() => setApproveDialogOpen(true)}
              >
                Approve
              </Button>
            </div>
          )}
        </div>
      </div>

      {/* Approve Dialog */}
      <Dialog open={approveDialogOpen} onOpenChange={setApproveDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Approve Recommendation</DialogTitle>
          </DialogHeader>
          <div className="py-2">
            <p className="text-sm text-slate-600 mb-3">{rec.action}</p>
            <Label htmlFor="approve-notes" className="text-xs">Notes (optional)</Label>
            <Input
              id="approve-notes"
              placeholder="Add any implementation notes..."
              value={approveNotes}
              onChange={(e) => setApproveNotes(e.target.value)}
              className="mt-1"
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setApproveDialogOpen(false)}>
              Cancel
            </Button>
            <Button variant="success" onClick={handleApprove} loading={loading}>
              Approve
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Reject Dialog */}
      <Dialog open={rejectDialogOpen} onOpenChange={setRejectDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Reject Recommendation</DialogTitle>
          </DialogHeader>
          <div className="py-2">
            <p className="text-sm text-slate-600 mb-3">{rec.action}</p>
            <Label htmlFor="reject-reason" className="text-xs">Reason for rejection *</Label>
            <Input
              id="reject-reason"
              placeholder="Explain why this recommendation is being rejected..."
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              className="mt-1"
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRejectDialogOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleReject}
              loading={loading}
              disabled={!rejectReason.trim()}
            >
              Reject
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
