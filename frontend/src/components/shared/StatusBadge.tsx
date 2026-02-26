import { cn, statusColor } from '@/lib/utils'

interface StatusBadgeProps {
  status: string
  size?: 'sm' | 'md'
}

export function StatusBadge({ status, size = 'md' }: StatusBadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded border font-medium uppercase tracking-wider',
        size === 'sm' ? 'px-1.5 py-0.5 text-[10px]' : 'px-2 py-1 text-xs',
        statusColor(status),
      )}
    >
      {status}
    </span>
  )
}
