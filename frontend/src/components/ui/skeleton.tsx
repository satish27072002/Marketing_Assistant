import { cn } from '@/lib/utils'

function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn('animate-pulse rounded bg-brand-walnut/30', className)}
      {...props}
    />
  )
}

export { Skeleton }
