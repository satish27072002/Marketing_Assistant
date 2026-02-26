import * as React from 'react'
import { Slot } from '@radix-ui/react-slot'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/lib/utils'

const buttonVariants = cva(
  'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-brand-gold/50 disabled:pointer-events-none disabled:opacity-40',
  {
    variants: {
      variant: {
        default:     'bg-brand-gold text-brand-bg hover:bg-brand-gold/90 font-semibold',
        outline:     'border border-brand-walnut/60 text-brand-muted hover:text-brand-white hover:border-brand-walnut bg-transparent',
        ghost:       'text-brand-muted hover:text-brand-white hover:bg-brand-walnut/20 bg-transparent',
        destructive: 'text-brand-muted hover:text-red-400 hover:border-red-400/30 border border-brand-walnut/60 bg-transparent',
        gold:        'border border-brand-gold/30 text-brand-gold hover:bg-brand-gold/10 bg-transparent',
      },
      size: {
        default: 'h-9 px-4 py-2',
        sm:      'h-7 px-3 text-xs',
        lg:      'h-11 px-6 text-base',
        icon:    'h-8 w-8 p-0',
        'icon-sm': 'h-7 w-7 p-0',
      },
    },
    defaultVariants: {
      variant: 'default',
      size: 'default',
    },
  }
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : 'button'
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    )
  }
)
Button.displayName = 'Button'

export { Button, buttonVariants }
