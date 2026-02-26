import React, { useState } from 'react'
import { Play, Square, RefreshCw, Settings2, Zap, Clock, FileText, DollarSign } from 'lucide-react'
import { useRuns, useTriggerRun, useStopRun } from '@/hooks/useRuns'
import type { RunParams } from '@/hooks/useRuns'
import { useSSE } from '@/hooks/useSSE'
import { StatusBadge } from '@/components/shared/StatusBadge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Separator } from '@/components/ui/separator'
import { Progress } from '@/components/ui/progress'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Slider } from '@/components/ui/slider'
import { Input } from '@/components/ui/input'
import { DateInput } from '@/components/ui/date-input'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'
import { formatDateTime, formatDuration, formatCost } from '@/lib/utils'

const DEFAULT_PARAMS: RunParams = {
  time_window_hours: 168,
  max_items: 100,
  max_queries: 20,
  max_cost_usd: 5.0,
}

export function RunsPage() {
  const { data: runs = [], isLoading, refetch } = useRuns(50)
  const triggerRun = useTriggerRun()
  const stopRun = useStopRun()
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [params, setParams] = useState<RunParams>(DEFAULT_PARAMS)
  const [dateMode, setDateMode] = useState<'lookback' | 'range'>('lookback')
  const today = new Date().toISOString().split('T')[0]
  const sevenDaysAgo = new Date(Date.now() - 7 * 24 * 3_600_000).toISOString().split('T')[0]
  const [fromDate, setFromDate] = useState<string>(sevenDaysAgo)
  const [toDate, setToDate] = useState<string>(today)

  const activeRun = runs.find((r) => r.status === 'RUNNING')
  const { update: sseUpdate } = useSSE(!!activeRun)

  const setParam = (key: keyof RunParams, value: number) =>
    setParams((p) => ({ ...p, [key]: value }))

  // Compute effective params: in range mode, derive time_window_hours from the date inputs
  const effectiveParams: RunParams = React.useMemo(() => {
    if (dateMode === 'range' && fromDate) {
      const from = new Date(fromDate).getTime()
      const to = new Date(toDate).getTime()
      const hours = Math.max(1, Math.ceil((to - from) / 3_600_000))
      return { ...params, time_window_hours: hours }
    }
    return params
  }, [dateMode, fromDate, toDate, params])

  const handleTrigger = () => {
    triggerRun.mutate(effectiveParams, {
      onSuccess: () => setTimeout(() => refetch(), 1000),
    })
  }

  // Helper to format a date range for the hero mini-stat
  const lookbackDisplay = React.useMemo(() => {
    if (dateMode === 'range' && fromDate) {
      const fmt = (d: string) => new Date(d).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
      return `${fmt(fromDate)} – ${fmt(toDate)}`
    }
    return `${Math.round((params.time_window_hours ?? 168) / 24)} days`
  }, [dateMode, fromDate, toDate, params.time_window_hours])

  const budgetPct = sseUpdate
    ? Math.min(100, (sseUpdate.estimated_cost_usd / (params.max_cost_usd ?? 5)) * 100)
    : 0

  const budgetColor =
    budgetPct >= 90 ? 'bg-red-400'
    : budgetPct >= 75 ? 'bg-orange-400'
    : budgetPct >= 50 ? 'bg-yellow-400'
    : undefined

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-brand-white">Runs</h1>
          <p className="text-brand-muted text-sm mt-0.5">Pipeline execution history</p>
        </div>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button variant="ghost" size="icon" onClick={() => refetch()}>
              <RefreshCw size={14} />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Refresh</TooltipContent>
        </Tooltip>
      </div>

      {/* Hero CTA card */}
      <Card className={activeRun ? 'border-brand-gold/30 bg-brand-gold/5' : 'border-brand-walnut/40'}>
        <CardContent className="pt-6">
          {activeRun ? (
            /* ── Active run state ── */
            <div className="space-y-5">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <span className="relative flex h-3 w-3">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-brand-gold opacity-75" />
                    <span className="relative inline-flex rounded-full h-3 w-3 bg-brand-gold" />
                  </span>
                  <span className="text-brand-gold font-semibold">
                    Pipeline running · {activeRun.run_id.slice(0, 8)}…
                  </span>
                </div>
                <Button variant="destructive" size="sm" onClick={() => stopRun.mutate(activeRun.run_id)}>
                  <Square size={11} />
                  Stop
                </Button>
              </div>

              {/* Live counters */}
              <div className="grid grid-cols-4 gap-3">
                {[
                  { label: 'Collected', value: sseUpdate?.items_collected ?? activeRun.items_collected },
                  { label: 'Matched',   value: sseUpdate?.items_matched ?? activeRun.items_matched },
                  { label: 'Leads',     value: sseUpdate?.leads_found ?? activeRun.leads_written, gold: true },
                  { label: 'Cost',      value: formatCost(sseUpdate?.estimated_cost_usd ?? activeRun.estimated_cost_usd) },
                ].map(({ label, value, gold }) => (
                  <div key={label} className="rounded border border-brand-walnut/40 bg-brand-bg p-3">
                    <p className="text-[10px] text-brand-muted uppercase tracking-widest">{label}</p>
                    <p className={`text-2xl font-bold mt-1 tabular-nums ${gold ? 'text-brand-gold' : 'text-brand-white'}`}>
                      {value}
                    </p>
                  </div>
                ))}
              </div>

              {/* Budget progress */}
              <div className="space-y-1.5">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-brand-muted">Budget utilization</span>
                  <span className={budgetPct >= 75 ? 'text-orange-400' : 'text-brand-muted'}>
                    {formatCost(sseUpdate?.estimated_cost_usd ?? 0)} / {formatCost(params.max_cost_usd ?? 5)}
                  </span>
                </div>
                <Progress value={budgetPct} indicatorClassName={budgetColor} />
              </div>
            </div>
          ) : (
            /* ── Idle / ready state ── */
            <div className="space-y-5">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-full bg-brand-gold/10 border border-brand-gold/20 flex items-center justify-center">
                  <Zap size={16} className="text-brand-gold" />
                </div>
                <div>
                  <p className="text-lg font-semibold text-brand-white">Ready to scan</p>
                  <p className="text-sm text-brand-muted">Find new leads across your targeted events</p>
                </div>
              </div>

              {/* 4-cell parameter summary — self-explanatory at a glance */}
              <div className="grid grid-cols-4 gap-2">
                {[
                  {
                    icon: Clock,
                    label: 'Lookback',
                    value: lookbackDisplay,
                    desc: 'How far back to search Reddit',
                  },
                  {
                    icon: FileText,
                    label: 'Max posts',
                    value: String(params.max_items ?? 100),
                    desc: 'Posts the AI analyses',
                  },
                  {
                    icon: Settings2,
                    label: 'Max queries',
                    value: String(params.max_queries ?? 20),
                    desc: 'Search terms generated',
                  },
                  {
                    icon: DollarSign,
                    label: 'Budget cap',
                    value: `$${params.max_cost_usd ?? 5}`,
                    desc: 'Safety limit (Groq is free)',
                  },
                ].map(({ icon: Icon, label, value, desc }) => (
                  <div
                    key={label}
                    className="rounded-lg border border-brand-walnut/40 bg-brand-bg p-3 space-y-1"
                  >
                    <div className="flex items-center gap-1.5">
                      <Icon size={10} className="text-brand-gold/60 shrink-0" />
                      <span className="text-[10px] text-brand-muted uppercase tracking-widest">{label}</span>
                    </div>
                    <p className="text-lg font-bold text-brand-gold tabular-nums leading-none">{value}</p>
                    <p className="text-[10px] text-brand-muted/70 leading-tight">{desc}</p>
                  </div>
                ))}
              </div>

              {/* Configure settings — prominent full-width text button */}
              <Button
                variant="outline"
                onClick={() => setSettingsOpen(true)}
                disabled={triggerRun.isPending}
                className="w-full"
              >
                <Settings2 size={14} />
                Configure settings
              </Button>

              <Separator />

              {/* Centred full-width Run button */}
              <Button
                onClick={handleTrigger}
                disabled={triggerRun.isPending}
                className="w-full h-12 text-base font-semibold gap-3"
              >
                <Play size={17} />
                {triggerRun.isPending ? 'Starting…' : 'Generate Leads'}
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Run history */}
      <div className="space-y-3">
        <div className="flex items-center gap-3">
          <Separator className="flex-1" />
          <span className="text-xs text-brand-muted uppercase tracking-widest shrink-0">Run History</span>
          <Separator className="flex-1" />
        </div>

        <div className="rounded-lg border border-brand-walnut/40 bg-brand-surface overflow-hidden">
          {isLoading ? (
            <div className="divide-y divide-brand-walnut/20">
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="flex items-center gap-4 px-4 py-3">
                  <Skeleton className="h-4 w-32" />
                  <Skeleton className="h-4 w-12" />
                  <Skeleton className="h-4 w-8" />
                  <Skeleton className="h-4 w-8" />
                  <Skeleton className="h-4 w-8" />
                  <Skeleton className="h-4 w-14" />
                  <Skeleton className="h-5 w-20 rounded ml-auto" />
                </div>
              ))}
            </div>
          ) : (
            <ScrollArea className="max-h-[400px]">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Started</TableHead>
                    <TableHead>Duration</TableHead>
                    <TableHead>Collected</TableHead>
                    <TableHead>Matched</TableHead>
                    <TableHead>Leads</TableHead>
                    <TableHead>Cost</TableHead>
                    <TableHead>Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {runs.filter((r) => r.items_collected > 0 || r.status === 'RUNNING').length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={7} className="text-center py-12 text-brand-muted">
                        No runs yet — click Run Pipeline to start.
                      </TableCell>
                    </TableRow>
                  ) : (
                    runs
                      .filter((r) => r.items_collected > 0 || r.status === 'RUNNING')
                      .map((run) => (
                        <TableRow key={run.run_id}>
                          <TableCell>
                            <p className="text-brand-white">{formatDateTime(run.started_at)}</p>
                            <p className="text-[10px] text-brand-muted font-mono">{run.run_id.slice(0, 8)}…</p>
                          </TableCell>
                          <TableCell className="text-brand-muted tabular-nums">
                            {formatDuration(run.started_at, run.completed_at)}
                          </TableCell>
                          <TableCell className="text-brand-white tabular-nums">{run.items_collected}</TableCell>
                          <TableCell className="text-brand-white tabular-nums">{run.items_matched}</TableCell>
                          <TableCell className="text-brand-gold font-medium tabular-nums">{run.leads_written}</TableCell>
                          <TableCell className="text-brand-muted tabular-nums">{formatCost(run.estimated_cost_usd)}</TableCell>
                          <TableCell><StatusBadge status={run.status} size="sm" /></TableCell>
                        </TableRow>
                      ))
                  )}
                </TableBody>
              </Table>
            </ScrollArea>
          )}
        </div>
      </div>

      {/* Settings Dialog */}
      <Dialog open={settingsOpen} onOpenChange={setSettingsOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Run Settings</DialogTitle>
            <DialogDescription>
              Adjust parameters for the next pipeline run. Groq is free — cost is a theoretical estimate only.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-7 py-2">
            {/* Time window — toggle between lookback slider and date range */}
            <div className="space-y-3">
              {/* Mode toggle pills */}
              <div className="flex items-center gap-1 p-0.5 rounded-lg bg-brand-bg border border-brand-walnut/40 w-fit">
                {(['lookback', 'range'] as const).map((mode) => (
                  <button
                    key={mode}
                    onClick={() => setDateMode(mode)}
                    className={[
                      'px-3 py-1 text-xs font-medium rounded-md transition-all duration-150',
                      dateMode === mode
                        ? 'bg-brand-walnut/60 text-brand-white'
                        : 'text-brand-muted hover:text-brand-white',
                    ].join(' ')}
                  >
                    {mode === 'lookback' ? 'Lookback days' : 'Date range'}
                  </button>
                ))}
              </div>

              {dateMode === 'lookback' ? (
                <SliderField
                  label="Time window"
                  description="How far back to search Reddit. Longer = more posts, slower run."
                  value={params.time_window_hours ?? 168}
                  min={24} max={720} step={24}
                  display={(v) => `${v}h · ${Math.round(v / 24)} days`}
                  onChange={(v) => setParam('time_window_hours', v)}
                />
              ) : (
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <label className="text-sm text-brand-white font-medium">Date range</label>
                    <span className="text-sm font-semibold text-brand-gold tabular-nums">
                      {fromDate && toDate ? `${Math.max(1, Math.ceil((new Date(toDate).getTime() - new Date(fromDate).getTime()) / 86_400_000))} days` : '—'}
                    </span>
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div className="space-y-1">
                      <p className="text-[10px] text-brand-muted uppercase tracking-widest">From</p>
                      <DateInput
                        value={fromDate}
                        max={toDate}
                        onChange={(e) => setFromDate(e.target.value)}
                      />
                    </div>
                    <div className="space-y-1">
                      <p className="text-[10px] text-brand-muted uppercase tracking-widest">To</p>
                      <DateInput
                        value={toDate}
                        min={fromDate}
                        max={today}
                        onChange={(e) => setToDate(e.target.value)}
                      />
                    </div>
                  </div>
                  <p className="text-xs text-brand-muted leading-relaxed">
                    Reddit is searched from the start date up to now.
                  </p>
                </div>
              )}
            </div>
            <SliderField
              label="Max posts"
              description="How many Reddit posts the AI analyses per run. Higher = more leads found."
              value={params.max_items ?? 100}
              min={10} max={500} step={10}
              display={(v) => `${v} posts`}
              onChange={(v) => setParam('max_items', v)}
            />
            <SliderField
              label="Max queries"
              description="How many search queries the AI generates. More = broader coverage."
              value={params.max_queries ?? 20}
              min={5} max={100} step={5}
              display={(v) => `${v} queries`}
              onChange={(v) => setParam('max_queries', v)}
            />

            <Separator />

            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <label className="text-sm text-brand-white font-medium">Budget cap</label>
              </div>
              <p className="text-xs text-brand-muted">Safety ceiling in USD. Pipeline pauses near this limit.</p>
              <div className="flex items-center gap-2">
                <span className="text-brand-muted text-sm">$</span>
                <Input
                  type="number"
                  min={0.01} max={50} step={0.5}
                  value={params.max_cost_usd}
                  onChange={(e) => setParam('max_cost_usd', Number(e.target.value))}
                  className="w-24"
                />
                <span className="text-xs text-brand-muted italic">(Groq is free — this is for planning only)</span>
              </div>
            </div>
          </div>

          <DialogFooter>
            <Button variant="ghost" size="sm" onClick={() => { setParams(DEFAULT_PARAMS); setDateMode('lookback') }}>
              Reset defaults
            </Button>
            <Button size="sm" onClick={() => setSettingsOpen(false)}>
              Done
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}


interface SliderFieldProps {
  label: string
  description: string
  value: number
  min: number
  max: number
  step: number
  display: (v: number) => string
  onChange: (v: number) => void
}

function SliderField({ label, description, value, min, max, step, display, onChange }: SliderFieldProps) {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <label className="text-sm text-brand-white font-medium">{label}</label>
        <span className="text-sm font-semibold text-brand-gold tabular-nums">{display(value)}</span>
      </div>
      <Slider
        min={min} max={max} step={step}
        value={[value]}
        onValueChange={([v]) => onChange(v)}
      />
      <p className="text-xs text-brand-muted leading-relaxed">{description}</p>
    </div>
  )
}
