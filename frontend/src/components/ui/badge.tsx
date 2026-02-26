import * as React from 'react'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/lib/utils'

const badgeVariants = cva(
  'inline-flex items-center rounded border font-medium uppercase tracking-wider transition-colors',
  {
    variants: {
      variant: {
        new:       'border-brand-gold/30 bg-brand-gold/10 text-brand-gold',
        reviewed:  'border-blue-500/30 bg-blue-500/10 text-blue-400',
        messaged:  'border-green-500/30 bg-green-500/10 text-green-400',
        skip:      'border-brand-walnut/60 bg-brand-walnut/20 text-brand-muted',
        running:   'border-brand-gold/50 bg-brand-gold/15 text-brand-gold',
        completed: 'border-green-500/30 bg-green-500/10 text-green-400',
        failed:    'border-red-500/30 bg-red-500/10 text-red-400',
        stopped:   'border-brand-walnut/60 bg-brand-walnut/20 text-brand-muted',
        default:   'border-brand-walnut/60 bg-brand-walnut/20 text-brand-muted',
      },
      size: {
        sm: 'px-1.5 py-0.5 text-[10px]',
        md: 'px-2 py-1 text-xs',
      },
    },
    defaultVariants: { variant: 'default', size: 'sm' },
  }
)

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, size, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant, size }), className)} {...props} />
}

export { Badge, badgeVariants }
