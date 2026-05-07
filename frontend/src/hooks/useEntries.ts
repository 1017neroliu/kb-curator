import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from '../api/client';
import type {
  KnowledgeEntryCreate,
  KnowledgeEntryUpdate,
  KnowledgeEntryRead,
  SearchRequest,
  SearchResult,
  EntryStatus,
} from '../api/types';

export function useEntries(
  kbId: string | undefined,
  params?: { status?: EntryStatus; limit?: number; offset?: number },
) {
  return useQuery({
    queryKey: ['entries', kbId, params],
    queryFn: async () => {
      const { data } = await apiClient.get<KnowledgeEntryRead[]>(
        `/knowledge-bases/${kbId}/entries`,
        { params },
      );
      return data;
    },
    enabled: !!kbId,
  });
}

export function useEntry(kbId: string | undefined, entryId: string | undefined) {
  return useQuery({
    queryKey: ['entry', kbId, entryId],
    queryFn: async () => {
      const { data } = await apiClient.get<KnowledgeEntryRead>(
        `/knowledge-bases/${kbId}/entries/${entryId}`,
      );
      return data;
    },
    enabled: !!kbId && !!entryId,
  });
}

export function useEntryCount(kbId: string | undefined, status?: EntryStatus) {
  return useQuery({
    queryKey: ['entryCount', kbId, status],
    queryFn: async () => {
      const { data } = await apiClient.get<{ kb_id: string; count: number }>(
        `/knowledge-bases/${kbId}/entries/count`,
        { params: { status } },
      );
      return data;
    },
    enabled: !!kbId,
  });
}

export function useCreateEntry(kbId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: Omit<KnowledgeEntryCreate, 'kb_id'>) => {
      const { data } = await apiClient.post<KnowledgeEntryRead>(
        `/knowledge-bases/${kbId}/entries`,
        { ...body, kb_id: kbId },
      );
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['entries', kbId] });
      queryClient.invalidateQueries({ queryKey: ['entryCount', kbId] });
    },
  });
}

export function useUpdateEntry(kbId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ entryId, body }: { entryId: string; body: KnowledgeEntryUpdate }) => {
      const { data } = await apiClient.patch<KnowledgeEntryRead>(
        `/knowledge-bases/${kbId}/entries/${entryId}`,
        body,
      );
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['entries', kbId] });
    },
  });
}

export function useDeleteEntry(kbId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (entryId: string) => {
      const { data } = await apiClient.delete(`/knowledge-bases/${kbId}/entries/${entryId}`);
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['entries', kbId] });
      queryClient.invalidateQueries({ queryKey: ['entryCount', kbId] });
    },
  });
}

export function useSearchEntries(kbId: string | undefined) {
  return useMutation({
    mutationFn: async (body: SearchRequest) => {
      const { data } = await apiClient.post<SearchResult[]>(
        `/knowledge-bases/${kbId}/entries/search`,
        body,
      );
      return data;
    },
  });
}

export function useProcessEntry(kbId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (entryId: string) => {
      const { data } = await apiClient.post<{
        entry_id: string;
        status: string;
        chunks: number;
        entities: number;
        relations: number;
        errors: string[];
      }>(`/knowledge-bases/${kbId}/entries/${entryId}/process`);
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['entries', kbId] });
    },
  });
}

export interface UploadResult {
  entry_id: string;
  title: string;
  filename: string;
  content_length: number;
  processed: boolean;
  chunks: number;
  entities: number;
  relations: number;
  errors?: string[];
  processing_error?: string;
}

export function useUploadDocument(kbId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ file, sourceId }: { file: File; sourceId?: string }) => {
      const formData = new FormData();
      formData.append('file', file);
      if (sourceId) {
        formData.append('source_id', sourceId);
      }
      const { data } = await apiClient.post<UploadResult>(
        `/knowledge-bases/${kbId}/entries/upload`,
        formData,
        {
          headers: { 'Content-Type': 'multipart/form-data' },
        },
      );
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['entries', kbId] });
      queryClient.invalidateQueries({ queryKey: ['entryCount', kbId] });
    },
  });
}
