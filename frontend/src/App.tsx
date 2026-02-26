import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { TooltipProvider } from '@/components/ui/tooltip'
import { Layout } from '@/components/layout/Layout'
import { DashboardPage } from '@/pages/DashboardPage'
import { LeadsPage } from '@/pages/LeadsPage'
import { RunsPage } from '@/pages/RunsPage'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 5_000,
    },
  },
})

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider delayDuration={400}>
        <BrowserRouter>
          <Routes>
            <Route element={<Layout />}>
              <Route path="/"       element={<DashboardPage />} />
              <Route path="/leads"  element={<LeadsPage />} />
              <Route path="/runs"   element={<RunsPage />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </TooltipProvider>
    </QueryClientProvider>
  )
}
