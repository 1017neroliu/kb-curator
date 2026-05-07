import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from '../api/client';
import type { KGEntityCreate, KGEntityRead, KGRelationCreate, KGRelationRead, GraphStats } from '../api/types';

export function useGraphEntities(
  kbId: string | undefined,
  params?: { entity_type?: string; limit?: number; offset?: number },
) {
  return useQuery({
    queryKey: ['graphEntities', kbId, params],
    queryFn: async () => {
      const { data } = await apiClient.get<KGEntityRead[]>(
        `/knowledge-bases/${kbId}/graph/entities`,
        { params },
      );
      return data;
    },
    enabled: !!kbId,
  });
}

export function useGraphRelations(
  kbId: string | undefined,
  params?: { relation_type?: string; limit?: number; offset?: number },
) {
  return useQuery({
    queryKey: ['graphRelations', kbId, params],
    queryFn: async () => {
      const { data } = await apiClient.get<KGRelationRead[]>(
        `/knowledge-bases/${kbId}/graph/relations`,
        { params },
      );
      return data;
    },
    enabled: !!kbId,
  });
}

export function useGraphStats(kbId: string | undefined) {
  return useQuery({
    queryKey: ['graphStats', kbId],
    queryFn: async () => {
      const { data } = await apiClient.get<GraphStats>(
        `/knowledge-bases/${kbId}/graph/stats`,
      );
      return data;
    },
    enabled: !!kbId,
  });
}

export function useCreateEntity(kbId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: Omit<KGEntityCreate, 'kb_id'>) => {
      const { data } = await apiClient.post<KGEntityRead>(
        `/knowledge-bases/${kbId}/graph/entities`,
        { ...body, kb_id: kbId },
      );
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['graphEntities', kbId] });
      queryClient.invalidateQueries({ queryKey: ['graphStats', kbId] });
    },
  });
}

export function useDeleteEntity(kbId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (entityId: string) => {
      const { data } = await apiClient.delete(
        `/knowledge-bases/${kbId}/graph/entities/${entityId}`,
      );
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['graphEntities', kbId] });
      queryClient.invalidateQueries({ queryKey: ['graphStats', kbId] });
    },
  });
}

export function useCreateRelation(kbId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: Omit<KGRelationCreate, 'kb_id'>) => {
      const { data } = await apiClient.post<KGRelationRead>(
        `/knowledge-bases/${kbId}/graph/relations`,
        { ...body, kb_id: kbId },
      );
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['graphRelations', kbId] });
      queryClient.invalidateQueries({ queryKey: ['graphStats', kbId] });
    },
  });
}

export function useDeleteRelation(kbId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (relationId: string) => {
      const { data } = await apiClient.delete(
        `/knowledge-bases/${kbId}/graph/relations/${relationId}`,
      );
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['graphRelations', kbId] });
      queryClient.invalidateQueries({ queryKey: ['graphStats', kbId] });
    },
  });
}

export function useEntityNeighbors(kbId: string | undefined, entityId: string | undefined) {
  return useQuery({
    queryKey: ['entityNeighbors', kbId, entityId],
    queryFn: async () => {
      const { data } = await apiClient.get(
        `/knowledge-bases/${kbId}/graph/entities/${entityId}/neighbors`,
      );
      return data;
    },
    enabled: !!kbId && !!entityId,
  });
}
