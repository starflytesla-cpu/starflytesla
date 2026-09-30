import { useQuery } from '@tanstack/react-query'
import { api } from './api'
import { ApiError } from './api/http'

export function useMe() {
  return useQuery({
    queryKey: ['me'],
    queryFn: api.me,
    retry: (count, error) => !(error instanceof ApiError && error.status === 401) && count < 2,
    staleTime: 60_000,
  })
}
