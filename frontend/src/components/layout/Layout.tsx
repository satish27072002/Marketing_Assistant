import { Outlet } from 'react-router-dom'
import { Sidebar } from './Sidebar'

export function Layout() {
  return (
    <div className="flex min-h-screen bg-brand-bg text-brand-white font-sans">
      {/* Subtle grid pattern on background */}
      <div
        className="fixed inset-0 pointer-events-none"
        style={{
          backgroundImage: `
            linear-gradient(rgba(68,51,36,0.12) 1px, transparent 1px),
            linear-gradient(90deg, rgba(68,51,36,0.12) 1px, transparent 1px)
          `,
          backgroundSize: '40px 40px',
        }}
      />
      <Sidebar />
      <main className="flex-1 relative overflow-auto">
        <Outlet />
      </main>
    </div>
  )
}
