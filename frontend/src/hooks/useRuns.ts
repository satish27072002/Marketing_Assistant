import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'

export function useRuns(limit = 50) {
  return useQuery({
    queryKey: ['runs', limit],
    queryFn: () => api.getRuns(limit),
    refetchInterval: 10_000,
  })
}

export interface RunParams {
  time_window_hours?: number
  max_items?: number
  max_queries?: number
  max_cost_usd?: number
}

export function useTriggerRun() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (params?: RunParams) => api.triggerRun(params),
    onSuccess: () => {
      setTimeout(() => qc.invalidateQueries({ queryKey: ['runs'] }), 500)
    },
  })
}

export function useStopRun() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (runId: string) => api.stopRun(runId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['runs'] }),
  })
}
