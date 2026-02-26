import { cn } from '@/lib/utils'
import type { LucideIcon } from 'lucide-react'

interface StatCardProps {
  label: string
  value: string | number
  icon?: LucideIcon
  accent?: boolean
  sub?: string
}

export function StatCard({ label, value, icon: Icon, accent, sub }: StatCardProps) {
  return (
    <div
      className={cn(
        'group relative rounded-lg border p-5 flex flex-col gap-3 transition-all duration-200',
        'bg-brand-surface border-brand-walnut/40',
        'hover:border-l-2 hover:border-l-brand-gold hover:shadow-[0_0_0_1px_rgba(236,203,76,0.08)]',
      )}
    >
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-brand-muted uppercase tracking-widest">
          {label}
        </span>
        {Icon && <Icon size={14} className="text-brand-muted group-hover:text-brand-gold/60 transition-colors" />}
      </div>
      <span
        className={cn(
          'text-3xl font-bold tracking-tight',
          accent ? 'text-brand-gold' : 'text-brand-white',
        )}
      >
        {value}
      </span>
      {sub && <span className="text-xs text-brand-muted">{sub}</span>}
    </div>
  )
}
