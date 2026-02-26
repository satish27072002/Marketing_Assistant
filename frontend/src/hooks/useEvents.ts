import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'

export function useEvents() {
  return useQuery({
    queryKey: ['events'],
    queryFn: () => api.getEvents(),
    staleTime: 60_000,
  })
}
