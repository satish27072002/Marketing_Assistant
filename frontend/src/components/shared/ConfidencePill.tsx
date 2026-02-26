import { cn } from '@/lib/utils'

interface ConfidencePillProps {
  score: number // 0–1
}

export function ConfidencePill({ score }: ConfidencePillProps) {
  const pct = Math.round(score * 100)
  const color =
    pct >= 80 ? 'bg-green-500/20 text-green-400 border-green-500/30'
    : pct >= 60 ? 'bg-brand-gold/20 text-brand-gold border-brand-gold/30'
    : 'bg-brand-muted/20 text-brand-muted border-brand-muted/30'

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded border px-2 py-0.5 text-xs font-medium tabular-nums',
        color,
      )}
    >
      <span
        className={cn(
          'w-1.5 h-1.5 rounded-full',
          pct >= 80 ? 'bg-green-400'
          : pct >= 60 ? 'bg-brand-gold'
          : 'bg-brand-muted',
        )}
      />
      {pct}%
    </span>
  )
}
