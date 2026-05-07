import { useQuery } from '@tanstack/react-query';
import apiClient from '../api/client';
import type { ChangeEventRead, ChangeType } from '../api/types';

export function useEvents(
  kbId: string | undefined,
  params?: { change_type?: ChangeType; limit?: number; offset?: number },
) {
  return useQuery({
    queryKey: ['events', kbId, params],
    queryFn: async () => {
      const { data } = await apiClient.get<ChangeEventRead[]>(
        `/knowledge-bases/${kbId}/events`,
        { params },
      );
      return data;
    },
    enabled: !!kbId,
  });
}

export function useEvent(kbId: string | undefined, eventId: string | undefined) {
  return useQuery({
    queryKey: ['event', kbId, eventId],
    queryFn: async () => {
      const { data } = await apiClient.get<ChangeEventRead>(
        `/knowledge-bases/${kbId}/events/${eventId}`,
      );
      return data;
    },
    enabled: !!kbId && !!eventId,
  });
}
