import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from '../api/client';
import type { KnowledgeBaseOverview } from '../api/types';

export function useKnowledgeBases() {
  return useQuery({
    queryKey: ['knowledgeBases'],
    queryFn: async () => {
      const { data } = await apiClient.get<{ knowledge_bases: string[] }>('/knowledge-bases');
      return data.knowledge_bases;
    },
  });
}

export function useKnowledgeBase(kbId: string | undefined) {
  return useQuery({
    queryKey: ['knowledgeBase', kbId],
    queryFn: async () => {
      const { data } = await apiClient.get<KnowledgeBaseOverview>(`/knowledge-bases/${kbId}`);
      return data;
    },
    enabled: !!kbId,
  });
}

export function useCreateKnowledgeBase() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (kbId: string) => {
      const { data } = await apiClient.post(`/knowledge-bases/${kbId}`);
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['knowledgeBases'] });
    },
  });
}

export function useDeleteKnowledgeBase() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ kbId, confirm }: { kbId: string; confirm?: boolean }) => {
      const { data } = await apiClient.delete(`/knowledge-bases/${kbId}`, {
        params: { confirm },
      });
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['knowledgeBases'] });
    },
  });
}
