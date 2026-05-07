import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from '../api/client';
import type { DataSourceCreate, DataSourceUpdate, DataSourceRead } from '../api/types';

export function useSources(kbId: string | undefined, enabledOnly = false) {
  return useQuery({
    queryKey: ['sources', kbId, enabledOnly],
    queryFn: async () => {
      const { data } = await apiClient.get<DataSourceRead[]>(
        `/knowledge-bases/${kbId}/sources`,
        { params: { enabled_only: enabledOnly } },
      );
      return data;
    },
    enabled: !!kbId,
  });
}

export function useSource(kbId: string | undefined, sourceId: string | undefined) {
  return useQuery({
    queryKey: ['source', kbId, sourceId],
    queryFn: async () => {
      const { data } = await apiClient.get<DataSourceRead>(
        `/knowledge-bases/${kbId}/sources/${sourceId}`,
      );
      return data;
    },
    enabled: !!kbId && !!sourceId,
  });
}

export function useCreateSource(kbId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: Omit<DataSourceCreate, 'kb_id'>) => {
      const { data } = await apiClient.post<DataSourceRead>(
        `/knowledge-bases/${kbId}/sources`,
        { ...body, kb_id: kbId },
      );
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sources', kbId] });
    },
  });
}

export function useUpdateSource(kbId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ sourceId, body }: { sourceId: string; body: DataSourceUpdate }) => {
      const { data } = await apiClient.patch<DataSourceRead>(
        `/knowledge-bases/${kbId}/sources/${sourceId}`,
        body,
      );
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sources', kbId] });
    },
  });
}

export function useDeleteSource(kbId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (sourceId: string) => {
      const { data } = await apiClient.delete(`/knowledge-bases/${kbId}/sources/${sourceId}`);
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sources', kbId] });
    },
  });
}

export function usePollSources(kbId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const { data } = await apiClient.post<{
        kb_id: string;
        sources_polled: number;
        entries_created: number;
        errors: string[];
      }>(`/knowledge-bases/${kbId}/sources/poll`);
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sources', kbId] });
      queryClient.invalidateQueries({ queryKey: ['entries', kbId] });
    },
  });
}
