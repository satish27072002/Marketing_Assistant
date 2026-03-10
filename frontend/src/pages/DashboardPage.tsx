import { Link } from 'react-router-dom'
import { Users, CalendarDays, DollarSign, Zap, ExternalLink, ArrowRight, Undo2 } from 'lucide-react'
import { useLeads, usePatchLead } from '@/hooks/useLeads'
import { useRuns, useStopRun } from '@/hooks/useRuns'
import { useEvents } from '@/hooks/useEvents'
import { useSSE } from '@/hooks/useSSE'
import { StatCard } from '@/components/shared/StatCard'
import { StatusBadge } from '@/components/shared/StatusBadge'
import { ConfidencePill } from '@/components/shared/ConfidencePill'
import { Skeleton } from '@/components/ui/skeleton'
import { Separator } from '@/components/ui/separator'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { Button } from '@/components/ui/button'
import { leadProfileHref, sourceLabel } from '@/lib/leadLinks'
import { formatDate, formatCost } from '@/lib/utils'

export function DashboardPage() {
  const { data: leads = [], isLoading: leadsLoading } = useLeads({ limit: 100 })
  const { data: runs = [] } = useRuns(5)
  const { data: events = [], isLoading: eventsLoading } = useEvents()
  const recentLeads = leads.slice(0, 5)
  const lastRun = runs[0]
  const isRunning = lastRun?.status === 'RUNNING'
  const { update: sseUpdate } = useSSE(isRunning)
  const stopRun = useStopRun()
  const patchLead = usePatchLead()

  const newLeads = leads.filter((l) => l.status === 'NEW').length
  const totalCost = runs.reduce((acc, r) => acc + r.estimated_cost_usd, 0)

  const eventMap = Object.fromEntries(events.map((e) => [e.event_id, e]))
  const leadsByEvent: Record<string, number> = {}
  leads.forEach((l) => {
    leadsByEvent[l.primary_event_id] = (leadsByEvent[l.primary_event_id] ?? 0) + 1
  })

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-brand-white">Dashboard</h1>
        <p className="text-brand-muted text-sm mt-0.5">Lead generation overview</p>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Total Leads" value={leads.length} icon={Users} accent />
        <StatCard label="New" value={newLeads} icon={Zap} sub="awaiting review" />
        <StatCard label="Events" value={events.length} icon={CalendarDays} sub="active targets" />
        <StatCard label="Total Cost" value={formatCost(totalCost)} icon={DollarSign} sub="all runs" />
      </div>

      {isRunning && (
        <div className="rounded-lg border border-brand-gold/30 bg-brand-gold/5 px-5 py-4 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <span className="relative flex h-2.5 w-2.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-brand-gold opacity-75" />
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-brand-gold" />
            </span>
            <span className="text-brand-gold text-sm font-medium">Pipeline running</span>
            {sseUpdate && (
              <div className="flex items-center gap-4 text-xs text-brand-muted ml-2">
                <span><span className="text-brand-white font-medium">{sseUpdate.items_collected}</span> collected</span>
                <span><span className="text-brand-white font-medium">{sseUpdate.items_matched}</span> matched</span>
                <span><span className="text-brand-gold font-medium">{sseUpdate.leads_found}</span> leads</span>
                <span>{formatCost(sseUpdate.estimated_cost_usd)}</span>
              </div>
            )}
          </div>
          <Button variant="outline" size="sm" onClick={() => lastRun && stopRun.mutate(lastRun.run_id)}>
            Stop
          </Button>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        <div className="lg:col-span-3 rounded-lg border border-brand-walnut/40 bg-brand-surface overflow-hidden">
          <div className="px-5 py-4 border-b border-brand-walnut/40 flex items-center justify-between">
            <span className="text-sm font-medium text-brand-white">Recent Leads</span>
            <Link to="/leads" className="text-xs text-brand-muted hover:text-brand-gold flex items-center gap-1 transition-colors">
              View all <ArrowRight size={12} />
            </Link>
          </div>

          {leadsLoading ? (
            <div className="divide-y divide-brand-walnut/20">
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="px-5 py-3.5 flex items-center gap-4">
                  <Skeleton className="w-8 h-8 rounded-full shrink-0" />
                  <div className="flex-1 space-y-1.5">
                    <Skeleton className="h-3.5 w-32" />
                    <Skeleton className="h-3 w-24" />
                  </div>
                  <Skeleton className="h-6 w-14 rounded" />
                </div>
              ))}
            </div>
          ) : recentLeads.length === 0 ? (
            <div className="px-5 py-10 text-center text-brand-muted text-sm">
              No leads yet — run the pipeline to find matches.
            </div>
          ) : (
            <div className="divide-y divide-brand-walnut/20">
              {recentLeads.map((lead) => (
                <div
                  key={lead.id}
                  className="group px-5 py-3.5 flex items-center gap-4 border-l-2 border-l-transparent hover:border-l-brand-gold hover:bg-brand-gold/[0.05] transition-all duration-150"
                >
                  <div className="w-8 h-8 rounded-full bg-brand-walnut flex items-center justify-center shrink-0">
                    <span className="text-brand-gold text-xs font-bold uppercase">{lead.username[0]}</span>
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      {(() => {
                        const href = leadProfileHref(lead)
                        const label = lead.source === 'reddit' ? `u/${lead.username}` : lead.username
                        if (!href) {
                          return <span className="text-sm font-medium text-brand-white truncate">{label}</span>
                        }
                        return (
                          <a
                            href={href}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-sm font-medium text-brand-white hover:text-brand-gold transition-colors flex items-center gap-1"
                          >
                            {label}
                            <ExternalLink size={11} className="shrink-0" />
                          </a>
                        )
                      })()}
                      <span className="text-[10px] px-1.5 py-0.5 rounded border border-brand-walnut/50 text-brand-muted/90">
                        {sourceLabel(lead.source)}
                      </span>
                      <ConfidencePill score={lead.top_confidence} />
                    </div>
                    <p className="text-xs text-brand-muted truncate mt-0.5">
                      {eventMap[lead.primary_event_id]?.title ?? lead.primary_event_id}
                    </p>
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    <StatusBadge status={lead.status} size="sm" />
                    {lead.status === 'NEW' && (
                      <>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Button variant="outline" size="sm" className="text-[10px] px-2 h-6"
                              onClick={() => patchLead.mutate({ id: lead.id, patch: { status: 'REVIEWED' } })}>
                              Review
                            </Button>
                          </TooltipTrigger>
                          <TooltipContent>Mark as reviewed</TooltipContent>
                        </Tooltip>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Button variant="gold" size="sm" className="text-[10px] px-2 h-6"
                              onClick={() => patchLead.mutate({ id: lead.id, patch: { status: 'MESSAGED' } })}>
                              Msg
                            </Button>
                          </TooltipTrigger>
                          <TooltipContent>Mark as messaged</TooltipContent>
                        </Tooltip>
                      </>
                    )}
                    {(lead.status === 'REVIEWED' || lead.status === 'MESSAGED' || lead.status === 'SKIP') && (
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button variant="ghost" size="icon-sm"
                            onClick={() => patchLead.mutate({ id: lead.id, patch: { status: 'NEW' } })}>
                            <Undo2 size={11} />
                          </Button>
                        </TooltipTrigger>
                        <TooltipContent>Undo — reset to New</TooltipContent>
                      </Tooltip>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="lg:col-span-2 rounded-lg border border-brand-walnut/40 bg-brand-surface overflow-hidden">
          <div className="px-5 py-4 border-b border-brand-walnut/40">
            <span className="text-sm font-medium text-brand-white">Targeted Events</span>
          </div>
          {eventsLoading ? (
            <div className="divide-y divide-brand-walnut/20">
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="px-5 py-3.5 space-y-1.5">
                  <Skeleton className="h-3.5 w-40" />
                  <Skeleton className="h-3 w-28" />
                  <div className="flex gap-1 mt-1.5">
                    <Skeleton className="h-4 w-10 rounded" />
                    <Skeleton className="h-4 w-12 rounded" />
                  </div>
                </div>
              ))}
            </div>
          ) : events.length === 0 ? (
            <div className="px-5 py-10 text-center text-brand-muted text-sm">No events loaded.</div>
          ) : (
            <div className="divide-y divide-brand-walnut/20">
              {events.map((event) => (
                <div key={event.event_id} className="px-5 py-3.5 hover:bg-brand-walnut/10 transition-colors">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-brand-white truncate">{event.title}</p>
                      <p className="text-xs text-brand-muted mt-0.5">{formatDate(event.start_time)} · {event.city}</p>
                    </div>
                    {(leadsByEvent[event.event_id] ?? 0) > 0 && (
                      <span className="shrink-0 text-xs font-bold text-brand-gold bg-brand-gold/10 border border-brand-gold/20 rounded px-1.5 py-0.5">
                        {leadsByEvent[event.event_id]}
                      </span>
                    )}
                  </div>
                  {event.tags.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-2">
                      {event.tags.slice(0, 3).map((tag) => (
                        <span key={tag} className="text-[10px] px-1.5 py-0.5 rounded bg-brand-walnut/50 text-brand-muted border border-brand-walnut/40">
                          {tag}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <Separator />
      <p className="text-xs text-brand-muted/50 text-center">TJAMIGO Lead Generator · Pipeline v1.0</p>
    </div>
  )
}
