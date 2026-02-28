import React, { useState } from 'react'
import { ExternalLink, ChevronDown, ChevronUp, MessageSquare, CheckCheck, EyeOff, Undo2 } from 'lucide-react'
import { useLeads, usePatchLead } from '@/hooks/useLeads'
import { useEvents } from '@/hooks/useEvents'
import { ConfidencePill } from '@/components/shared/ConfidencePill'
import { StatusBadge } from '@/components/shared/StatusBadge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'
import { formatDateTime } from '@/lib/utils'

const STATUS_OPTIONS = ['', 'NEW', 'REVIEWED', 'MESSAGED', 'SKIP']

export function LeadsPage() {
  const [filters, setFilters] = useState({
    confidence_min: 0,
    status: '',
    event_id: '',
    username: '',
  })
  const [expanded, setExpanded] = useState<number | null>(null)

  const { data: leads = [], isLoading } = useLeads({
    confidence_min: filters.confidence_min,
    status: filters.status || undefined,
    event_id: filters.event_id || undefined,
    username: filters.username || undefined,
    limit: 200,
  })
  const { data: events = [] } = useEvents()
  const patchLead = usePatchLead()

  const eventMap = Object.fromEntries(events.map((e) => [e.event_id, e.title]))

  const toggleExpand = (id: number) =>
    setExpanded((prev) => (prev === id ? null : id))

  return (
    <div className="p-6 space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-brand-white">Leads</h1>
          <p className="text-brand-muted text-sm mt-0.5">{leads.length} results</p>
        </div>
      </div>

      {/* Filter bar */}
      <div className="flex flex-wrap gap-3 items-center">
        <Input
          type="text"
          placeholder="Search username…"
          value={filters.username}
          onChange={(e) => setFilters((f) => ({ ...f, username: e.target.value }))}
          className="w-44"
        />

        <select
          value={filters.event_id}
          onChange={(e) => setFilters((f) => ({ ...f, event_id: e.target.value }))}
          className="h-8 bg-brand-bg border border-brand-walnut/40 rounded px-3 text-sm text-brand-white focus:outline-none focus:border-brand-gold/50"
        >
          <option value="">All events</option>
          {events.map((e) => (
            <option key={e.event_id} value={e.event_id}>{e.title}</option>
          ))}
        </select>

        <select
          value={filters.status}
          onChange={(e) => setFilters((f) => ({ ...f, status: e.target.value }))}
          className="h-8 bg-brand-bg border border-brand-walnut/40 rounded px-3 text-sm text-brand-white focus:outline-none focus:border-brand-gold/50"
        >
          {STATUS_OPTIONS.map((s) => (
            <option key={s} value={s}>{s || 'All statuses'}</option>
          ))}
        </select>

        <div className="flex items-center gap-2 text-sm text-brand-muted">
          <span>Min confidence</span>
          <input
            type="range"
            min={0} max={100} step={10}
            value={filters.confidence_min * 100}
            onChange={(e) => setFilters((f) => ({ ...f, confidence_min: Number(e.target.value) / 100 }))}
            className="accent-brand-gold w-24"
          />
          <span className="text-brand-white w-8 tabular-nums">{Math.round(filters.confidence_min * 100)}%</span>
        </div>
      </div>

      {/* Table */}
      <div className="rounded-lg border border-brand-walnut/40 bg-brand-surface overflow-hidden">
        <ScrollArea className="h-[calc(100vh-14rem)]">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-8" />
                <TableHead>User</TableHead>
                <TableHead>Event</TableHead>
                <TableHead>Confidence</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                Array.from({ length: 6 }).map((_, i) => (
                  <TableRow key={i}>
                    <TableCell><Skeleton className="h-4 w-4" /></TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <Skeleton className="h-7 w-7 rounded-full" />
                        <Skeleton className="h-3.5 w-28" />
                      </div>
                    </TableCell>
                    <TableCell><Skeleton className="h-3.5 w-32" /></TableCell>
                    <TableCell><Skeleton className="h-5 w-14 rounded-full" /></TableCell>
                    <TableCell><Skeleton className="h-5 w-16 rounded" /></TableCell>
                    <TableCell><Skeleton className="h-6 w-24 rounded ml-auto" /></TableCell>
                  </TableRow>
                ))
              ) : leads.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={6} className="text-center py-12 text-brand-muted">
                    No leads match these filters.
                  </TableCell>
                </TableRow>
              ) : (
                leads.map((lead) => (
                  <React.Fragment key={lead.id}>
                    <TableRow
                      className="cursor-pointer"
                      onClick={() => toggleExpand(lead.id)}
                    >
                      <TableCell className="text-brand-muted">
                        {expanded === lead.id ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2 min-w-0">
                          <div className="w-7 h-7 rounded-full bg-brand-walnut flex items-center justify-center shrink-0">
                            <span className="text-brand-gold text-[10px] font-bold uppercase">{lead.username[0]}</span>
                          </div>
                          <a
                            href={`https://reddit.com/u/${lead.username}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            onClick={(e) => e.stopPropagation()}
                            className="text-brand-white hover:text-brand-gold flex items-center gap-1 transition-colors truncate"
                          >
                            u/{lead.username}
                            <ExternalLink size={10} className="shrink-0" />
                          </a>
                        </div>
                      </TableCell>
                      <TableCell className="max-w-[220px]">
                        <div className="flex flex-wrap items-center gap-1.5">
                          <span className="text-brand-muted truncate">
                            {eventMap[lead.primary_event_id] ?? lead.primary_event_id}
                          </span>
                          {lead.other_event_ids &&
                            lead.other_event_ids.split(',').filter(Boolean).map((eid) => (
                              <span
                                key={eid}
                                className="text-[9px] px-1.5 py-0.5 rounded border border-brand-walnut/50 text-brand-muted/70 shrink-0 whitespace-nowrap"
                              >
                                +{eventMap[eid]?.split(' ').slice(0, 2).join(' ') ?? eid}
                              </span>
                            ))}
                        </div>
                      </TableCell>
                      <TableCell><ConfidencePill score={lead.top_confidence} /></TableCell>
                      <TableCell><StatusBadge status={lead.status} size="sm" /></TableCell>
                      <TableCell>
                        <div className="flex items-center gap-1.5 justify-end" onClick={(e) => e.stopPropagation()}>
                          {lead.status !== 'MESSAGED' && (
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Button variant="gold" size="icon-sm"
                                  onClick={() => patchLead.mutate({ id: lead.id, patch: { status: 'MESSAGED' } })}>
                                  <MessageSquare size={12} />
                                </Button>
                              </TooltipTrigger>
                              <TooltipContent>Mark as messaged</TooltipContent>
                            </Tooltip>
                          )}
                          {lead.status === 'NEW' && (
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Button variant="outline" size="icon-sm"
                                  onClick={() => patchLead.mutate({ id: lead.id, patch: { status: 'REVIEWED' } })}>
                                  <CheckCheck size={12} />
                                </Button>
                              </TooltipTrigger>
                              <TooltipContent>Mark as reviewed</TooltipContent>
                            </Tooltip>
                          )}
                          {lead.status !== 'SKIP' && (
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Button variant="destructive" size="icon-sm"
                                  onClick={() => patchLead.mutate({ id: lead.id, patch: { status: 'SKIP' } })}>
                                  <EyeOff size={12} />
                                </Button>
                              </TooltipTrigger>
                              <TooltipContent>Skip this lead</TooltipContent>
                            </Tooltip>
                          )}
                          {(lead.status === 'REVIEWED' || lead.status === 'MESSAGED' || lead.status === 'SKIP') && (
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Button variant="ghost" size="icon-sm"
                                  onClick={() => patchLead.mutate({ id: lead.id, patch: { status: 'NEW' } })}>
                                  <Undo2 size={12} />
                                </Button>
                              </TooltipTrigger>
                              <TooltipContent>Undo — reset to New</TooltipContent>
                            </Tooltip>
                          )}
                        </div>
                      </TableCell>
                    </TableRow>

                    {expanded === lead.id && (
                      <TableRow className="hover:bg-transparent">
                        <TableCell colSpan={6} className="bg-brand-bg/50 px-12 pb-5 pt-2">
                          <div className="space-y-3">
                            {lead.user_summary && (
                              <p className="text-xs text-brand-muted italic leading-relaxed">
                                "{lead.user_summary}"
                              </p>
                            )}
                            {lead.other_event_ids && lead.other_event_ids.split(',').filter(Boolean).length > 0 && (
                              <div className="flex items-center gap-2 flex-wrap">
                                <span className="text-[10px] text-brand-muted uppercase tracking-widest shrink-0">
                                  Also interested in
                                </span>
                                {lead.other_event_ids.split(',').filter(Boolean).map((eid) => (
                                  <span
                                    key={eid}
                                    className="text-xs px-2 py-0.5 rounded border border-brand-walnut/40 text-brand-muted"
                                  >
                                    {eventMap[eid] ?? eid}
                                  </span>
                                ))}
                              </div>
                            )}
                            {lead.evidence_posts.length > 0 ? (
                              lead.evidence_posts.map((post) => (
                                <div key={post.item_id} className="rounded-lg border border-brand-walnut/40 overflow-hidden">
                                  <div className="flex items-center justify-between px-3 py-2 bg-brand-walnut/20 border-b border-brand-walnut/30">
                                    <span className="text-[10px] font-medium text-brand-gold">r/{post.subreddit}</span>
                                    {post.url.includes('/mock') ? (
                                      <span className="text-[10px] text-brand-muted/50 italic">Mock data</span>
                                    ) : (
                                      <a
                                        href={post.url}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="text-[10px] text-brand-muted hover:text-brand-gold flex items-center gap-1 transition-colors"
                                      >
                                        View on Reddit <ExternalLink size={9} />
                                      </a>
                                    )}
                                  </div>
                                  <div className="px-3 py-2.5">
                                    <p className="text-xs text-brand-white leading-relaxed whitespace-pre-line">
                                      {post.text.length > 500 ? post.text.slice(0, 500) + '…' : post.text}
                                    </p>
                                  </div>
                                </div>
                              ))
                            ) : (
                              lead.evidence_excerpts.map((excerpt, i) => (
                                <div key={i} className="rounded border border-brand-walnut/40 p-3 space-y-1">
                                  <p className="text-xs text-brand-white leading-relaxed">{excerpt}</p>
                                  {lead.evidence_urls[i] && (
                                    <a href={lead.evidence_urls[i]} target="_blank" rel="noopener noreferrer"
                                      className="text-[10px] text-brand-gold hover:underline flex items-center gap-1">
                                      View on Reddit <ExternalLink size={9} />
                                    </a>
                                  )}
                                </div>
                              ))
                            )}
                          </div>
                        </TableCell>
                      </TableRow>
                    )}
                  </React.Fragment>
                ))
              )}
            </TableBody>
          </Table>
        </ScrollArea>
      </div>
    </div>
  )
}
