import { useState } from 'react';
import {
  Table, Card, Button, Tag, Descriptions, Modal, Empty, Select, message, Space, Tooltip,
} from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import { useQualityReports, useRunInspection } from '../hooks/useQuality';
import { useEntries } from '../hooks/useEntries';
import QualityScore, { SeverityTag } from '../components/QualityScore';
import type { QualityReportRead, QualityIssue, QualityIssueType, Severity } from '../api/types';

const issueTypeLabels: Record<QualityIssueType, string> = {
  low_hit_rate: '低命中率',
  high_negative_feedback: '负面反馈多',
  expired: '已过期',
  orphan_entity: '孤立实体',
  metadata_inconsistency: '元数据不一致',
};

const severityColorMap: Record<Severity, string> = {
  info: 'blue',
  warning: 'orange',
  critical: 'red',
};

export default function Quality() {
  const kbId = localStorage.getItem('kb_curator_kb_id') || undefined;
  const [selectedReport, setSelectedReport] = useState<QualityReportRead | null>(null);
  const [inspectionType, setInspectionType] = useState<'full' | 'incremental' | 'targeted'>('incremental');
  const [selectedEntryIds, setSelectedEntryIds] = useState<string[]>([]);
  const runInspection = useRunInspection(kbId);
  const { data: reports, isLoading } = useQualityReports(kbId, { limit: 20 });
  const { data: entries } = useEntries(kbId, { limit: 200 });

  const entryOptions = (entries ?? []).map((e) => ({
    label: e.title?.length > 40 ? `${e.title.slice(0, 40)}...` : e.title || e.id,
    value: e.id,
  }));

  if (!kbId) {
    return <Card><Empty description="请先选择知识库" style={{ marginTop: 40 }} /></Card>;
  }

  const handleInspect = async () => {
    try {
      const params: Record<string, string> = { inspection_type: inspectionType };
      if (inspectionType === 'targeted' && selectedEntryIds.length > 0) {
        params.entry_ids = selectedEntryIds.join(',');
      }
      const result = await runInspection.mutateAsync(params as any);
      message.success(`巡检完成，评分: ${result.score}`);
    } catch {
      message.error('巡检失败');
    }
  };

  const columns = [
    {
      title: '巡检时间',
      dataIndex: 'inspected_at',
      key: 'inspected_at',
      width: 180,
      render: (v: string) => dayjs(v).format('YYYY-MM-DD HH:mm'),
    },
    {
      title: '类型',
      dataIndex: 'inspection_type',
      key: 'inspection_type',
      width: 100,
      render: (type: string) => {
        const labels: Record<string, string> = { full: '全量', incremental: '增量', targeted: '定向' };
        return labels[type] || type;
      },
    },
    {
      title: '评分',
      dataIndex: 'score',
      key: 'score',
      width: 100,
      render: (score: number) => {
        const color = score >= 80 ? '#52c41a' : score >= 60 ? '#faad14' : '#ff4d4f';
        return <span style={{ color, fontWeight: 600 }}>{score}</span>;
      },
    },
    {
      title: '总条目',
      dataIndex: 'total_entries',
      key: 'total_entries',
      width: 80,
    },
    {
      title: '问题数',
      dataIndex: 'issues',
      key: 'issues',
      width: 80,
      render: (issues: QualityIssue[]) => issues.length,
    },
    {
      title: '操作',
      key: 'action',
      width: 80,
      render: (_: unknown, record: QualityReportRead) => (
        <Button size="small" onClick={() => setSelectedReport(record)}>详情</Button>
      ),
    },
  ];

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'flex-end' }}>
        <Space wrap>
          <Select
            value={inspectionType}
            onChange={setInspectionType}
            style={{ width: 180 }}
            options={[
              { label: '增量巡检（轻量）', value: 'incremental' },
              { label: '全量巡检（完整）', value: 'full' },
              { label: '定向巡检（指定条目）', value: 'targeted' },
            ]}
          />
          {inspectionType === 'targeted' && (
            <Select
              mode="multiple"
              placeholder="选择要巡检的条目"
              style={{ minWidth: 320, maxWidth: 500 }}
              value={selectedEntryIds}
              onChange={setSelectedEntryIds}
              options={entryOptions}
              allowClear
              showSearch
              filterOption={(input, option) =>
                (option?.label as string)?.toLowerCase().includes(input.toLowerCase())
              }
              maxTagCount={3}
              maxTagPlaceholder={(omitted) => `+${omitted.length} 个条目`}
            />
          )}
          <Button
            type="primary"
            icon={<ReloadOutlined />}
            onClick={handleInspect}
            loading={runInspection.isPending}
          >
            触发巡检
          </Button>
        </Space>
      </div>

      <Table
        rowKey="id"
        columns={columns}
        dataSource={reports}
        loading={isLoading}
        pagination={{ pageSize: 10 }}
      />

      <Modal
        title="质量报告详情"
        open={!!selectedReport}
        onCancel={() => setSelectedReport(null)}
        footer={null}
        width={700}
      >
        {selectedReport && (
          <div>
            <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 16 }}>
              <QualityScore score={selectedReport.score} size={140} />
            </div>
            <Descriptions column={2} size="small" bordered style={{ marginBottom: 16 }}>
              <Descriptions.Item label="巡检类型">
                {{ full: '全量巡检', incremental: '增量巡检', targeted: '定向巡检' }[selectedReport.inspection_type]}
              </Descriptions.Item>
              <Descriptions.Item label="总条目">{selectedReport.total_entries}</Descriptions.Item>
              <Descriptions.Item label="问题数">{selectedReport.issues.length}</Descriptions.Item>
              <Descriptions.Item label="巡检时间">
                {dayjs(selectedReport.inspected_at).format('YYYY-MM-DD HH:mm')}
              </Descriptions.Item>
            </Descriptions>

            {selectedReport.issues.length > 0 ? (
              <Table
                size="small"
                pagination={{ pageSize: 10, size: 'small', showSizeChanger: false }}
                dataSource={selectedReport.issues}
                rowKey={(r) => `${r.entry_id}-${r.issue_type}`}
                columns={[
                  {
                    title: '条目 ID',
                    dataIndex: 'entry_id',
                    key: 'entry_id',
                    width: 120,
                    ellipsis: { showTitle: true },
                  },
                  {
                    title: '问题类型',
                    dataIndex: 'issue_type',
                    key: 'issue_type',
                    width: 120,
                    render: (type: QualityIssueType) => issueTypeLabels[type] || type,
                  },
                  {
                    title: '严重性',
                    dataIndex: 'severity',
                    key: 'severity',
                    width: 80,
                    render: (s: Severity) => <Tag color={severityColorMap[s]}>{s}</Tag>,
                  },
                  {
                    title: '详情',
                    dataIndex: 'detail',
                    key: 'detail',
                    ellipsis: { showTitle: true },
                  },
                  {
                    title: '建议',
                    dataIndex: 'suggestion',
                    key: 'suggestion',
                    ellipsis: { showTitle: true },
                  },
                ]}
              />
            ) : (
              <Empty description="无问题" />
            )}
          </div>
        )}
      </Modal>
    </div>
  );
}
