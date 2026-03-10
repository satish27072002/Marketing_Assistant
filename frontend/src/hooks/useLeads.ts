import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api, type LeadPatch } from '@/lib/api'

interface LeadFilters {
  confidence_min?: number
  status?: string
  source?: 'reddit' | 'facebook'
  event_id?: string
  username?: string
  limit?: number
}

export function useLeads(filters: LeadFilters = {}) {
  return useQuery({
    queryKey: ['leads', filters],
    queryFn: () => api.getLeads(filters),
    refetchInterval: 15_000,
  })
}

export function usePatchLead() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, patch }: { id: number; patch: LeadPatch }) =>
      api.patchLead(id, patch),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['leads'] }),
  })
}
