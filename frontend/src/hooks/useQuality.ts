import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from '../api/client';
import type { QualityReportRead, InspectionType } from '../api/types';

export function useQualityReports(
  kbId: string | undefined,
  params?: { limit?: number; offset?: number },
) {
  return useQuery({
    queryKey: ['qualityReports', kbId, params],
    queryFn: async () => {
      const { data } = await apiClient.get<QualityReportRead[]>(
        `/knowledge-bases/${kbId}/quality/reports`,
        { params },
      );
      return data;
    },
    enabled: !!kbId,
  });
}

export function useQualityReport(kbId: string | undefined, reportId: string | undefined) {
  return useQuery({
    queryKey: ['qualityReport', kbId, reportId],
    queryFn: async () => {
      const { data } = await apiClient.get<QualityReportRead>(
        `/knowledge-bases/${kbId}/quality/reports/${reportId}`,
      );
      return data;
    },
    enabled: !!kbId && !!reportId,
  });
}

export function useRunInspection(kbId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (params: Record<string, string> | string = 'incremental') => {
      const queryParams = typeof params === 'string'
        ? { inspection_type: params }
        : params;
      const { data } = await apiClient.post<QualityReportRead>(
        `/knowledge-bases/${kbId}/quality/inspect`,
        null,
        { params: queryParams },
      );
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['qualityReports', kbId] });
    },
  });
}
