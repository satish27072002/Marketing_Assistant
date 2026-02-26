import { NavLink } from 'react-router-dom'
import { LayoutDashboard, Users, Play } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Separator } from '@/components/ui/separator'

const nav = [
  { to: '/',      label: 'Dashboard', icon: LayoutDashboard },
  { to: '/leads', label: 'Leads',     icon: Users },
  { to: '/runs',  label: 'Runs',      icon: Play },
]

export function Sidebar() {
  return (
    <aside className="w-56 shrink-0 flex flex-col h-screen bg-brand-surface border-r border-brand-walnut/40 sticky top-0">
      {/* Logo */}
      <div className="px-6 py-6 border-b border-brand-walnut/40">
        <span
          className="text-2xl font-extrabold tracking-tight bg-gradient-to-r from-brand-gold via-yellow-200 to-brand-gold bg-clip-text text-transparent"
          style={{ backgroundSize: '200% auto' }}
        >
          TJAMIGO
        </span>
        <span className="text-brand-muted text-xs block mt-0.5">Lead Generator</span>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 space-y-1">
        {nav.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-3 px-3 py-2.5 rounded-md text-sm font-medium transition-colors',
                isActive
                  ? 'bg-brand-gold/10 text-brand-gold border border-brand-gold/20'
                  : 'text-brand-muted hover:text-brand-white hover:bg-brand-walnut/30',
              )
            }
          >
            <Icon size={16} />
            {label}
          </NavLink>
        ))}
      </nav>

      {/* Footer */}
      <Separator />
      <div className="px-6 py-4">
        <span className="text-brand-muted/60 text-xs">Pipeline v1.0</span>
      </div>
    </aside>
  )
}
