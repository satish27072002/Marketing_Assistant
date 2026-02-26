import * as React from 'react'
import { cn } from '@/lib/utils'

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {}

const Input = React.forwardRef<HTMLInputElement, InputProps>(({ className, type, ...props }, ref) => {
  return (
    <input
      type={type}
      className={cn(
        'flex h-8 w-full rounded border border-brand-walnut/40 bg-brand-bg px-3 py-1 text-sm text-brand-white shadow-sm transition-colors',
        'placeholder:text-brand-muted',
        'focus-visible:outline-none focus-visible:border-brand-gold/50',
        'disabled:cursor-not-allowed disabled:opacity-50',
        className,
      )}
      ref={ref}
      {...props}
    />
  )
})
Input.displayName = 'Input'

export { Input }
