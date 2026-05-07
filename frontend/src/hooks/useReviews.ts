import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from '../api/client';
import type {
  ReviewTaskRead,
  ReviewTaskStatus,
  ReviewTaskType,
  DecisionRequest,
  DecisionRead,
} from '../api/types';

export function useReviews(
  kbId: string | undefined,
  params?: { status?: ReviewTaskStatus; type?: ReviewTaskType; limit?: number; offset?: number },
) {
  return useQuery({
    queryKey: ['reviews', kbId, params],
    queryFn: async () => {
      const { data } = await apiClient.get<ReviewTaskRead[]>(
        `/knowledge-bases/${kbId}/reviews`,
        { params },
      );
      return data;
    },
    enabled: !!kbId,
  });
}

export function useReview(kbId: string | undefined, taskId: string | undefined) {
  return useQuery({
    queryKey: ['review', kbId, taskId],
    queryFn: async () => {
      const { data } = await apiClient.get<ReviewTaskRead>(
        `/knowledge-bases/${kbId}/reviews/${taskId}`,
      );
      return data;
    },
    enabled: !!kbId && !!taskId,
  });
}

export function useDecisions(kbId: string | undefined, taskId: string | undefined) {
  return useQuery({
    queryKey: ['decisions', kbId, taskId],
    queryFn: async () => {
      const { data } = await apiClient.get<DecisionRead[]>(
        `/knowledge-bases/${kbId}/reviews/${taskId}/decisions`,
      );
      return data;
    },
    enabled: !!kbId && !!taskId,
  });
}

export function useSubmitDecision(kbId: string | undefined, taskId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ body, decidedBy }: { body: DecisionRequest; decidedBy: string }) => {
      const { data } = await apiClient.post<DecisionRead>(
        `/knowledge-bases/${kbId}/reviews/${taskId}/decisions`,
        body,
        { params: { decided_by: decidedBy } },
      );
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['reviews', kbId] });
      queryClient.invalidateQueries({ queryKey: ['decisions', kbId, taskId] });
    },
  });
}

export function useUpdateReviewStatus(kbId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      taskId,
      taskStatus,
      assignedTo,
    }: {
      taskId: string;
      taskStatus?: ReviewTaskStatus;
      assignedTo?: string;
    }) => {
      const { data } = await apiClient.patch<ReviewTaskRead>(
        `/knowledge-bases/${kbId}/reviews/${taskId}`,
        { task_status: taskStatus, assigned_to: assignedTo },
      );
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['reviews', kbId] });
    },
  });
}
