import * as React from 'react'
import { cn } from '@/lib/utils'

export interface DateInputProps extends React.InputHTMLAttributes<HTMLInputElement> {}

const DateInput = React.forwardRef<HTMLInputElement, DateInputProps>(
  ({ className, ...props }, ref) => (
    <input
      type="date"
      ref={ref}
      className={cn(
        // [color-scheme:dark] makes the browser's native calendar popup dark in Chromium
        '[color-scheme:dark]',
        'w-full bg-brand-bg border border-brand-walnut/40 rounded-md px-3 py-1.5',
        'text-sm text-brand-white placeholder:text-brand-muted',
        'focus:outline-none focus:ring-1 focus:ring-brand-gold/60 focus:border-brand-gold/40',
        'disabled:opacity-50 disabled:cursor-not-allowed',
        'transition-colors duration-150',
        className,
      )}
      {...props}
    />
  )
)
DateInput.displayName = 'DateInput'

export { DateInput }
