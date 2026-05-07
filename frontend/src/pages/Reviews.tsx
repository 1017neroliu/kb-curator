import { useState } from 'react';
import {
  Table, Tag, Select, Button, Modal, Card, Descriptions, Space, Empty,
} from 'antd';
import dayjs from 'dayjs';
import { useReviews, useDecisions } from '../hooks/useReviews';
import DecisionForm from '../components/DecisionForm';
import type { ReviewTaskRead, ReviewTaskStatus, ReviewTaskType } from '../api/types';

const statusColorMap: Record<ReviewTaskStatus, string> = {
  pending: 'orange',
  in_progress: 'blue',
  resolved: 'green',
  expired: 'default',
};
const statusLabelMap: Record<ReviewTaskStatus, string> = {
  pending: '待处理',
  in_progress: '处理中',
  resolved: '已解决',
  expired: '已过期',
};
const typeLabelMap: Record<ReviewTaskType, string> = {
  conflict_resolution: '冲突解决',
  quality_action: '质量整改',
  deprecation: '废弃处理',
};

export default function Reviews() {
  const kbId = localStorage.getItem('kb_curator_kb_id') || undefined;
  const [statusFilter, setStatusFilter] = useState<ReviewTaskStatus | undefined>();
  const [typeFilter, setTypeFilter] = useState<ReviewTaskType | undefined>();
  const [selectedTask, setSelectedTask] = useState<ReviewTaskRead | null>(null);

  const { data: reviews, isLoading } = useReviews(kbId, {
    status: statusFilter,
    type: typeFilter,
    limit: 100,
  });
  const { data: decisions } = useDecisions(kbId, selectedTask?.id);

  if (!kbId) {
    return <Card><Empty description="请先选择知识库" style={{ marginTop: 40 }} /></Card>;
  }

  const columns = [
    {
      title: '标题',
      dataIndex: 'title',
      key: 'title',
      render: (text: string, record: ReviewTaskRead) => (
        <a onClick={() => setSelectedTask(record)}>{text}</a>
      ),
    },
    {
      title: '类型',
      dataIndex: 'task_type',
      key: 'task_type',
      width: 120,
      render: (type: ReviewTaskType) => typeLabelMap[type],
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: ReviewTaskStatus) => (
        <Tag color={statusColorMap[status]}>{statusLabelMap[status]}</Tag>
      ),
    },
    {
      title: '分配给',
      dataIndex: 'assigned_to',
      key: 'assigned_to',
      width: 120,
      render: (v: string | null) => v || '-',
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (v: string) => dayjs(v).format('YYYY-MM-DD HH:mm'),
    },
    {
      title: '操作',
      key: 'action',
      width: 100,
      render: (_: unknown, record: ReviewTaskRead) => (
        <Button
          size="small"
          type="primary"
          disabled={record.status === 'resolved' || record.status === 'expired'}
          onClick={() => setSelectedTask(record)}
        >
          处理
        </Button>
      ),
    },
  ];

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', gap: 12 }}>
        <Select
          placeholder="状态过滤"
          allowClear
          style={{ width: 130 }}
          onChange={(v) => setStatusFilter(v)}
          options={Object.entries(statusLabelMap).map(([value, label]) => ({ value, label }))}
        />
        <Select
          placeholder="类型过滤"
          allowClear
          style={{ width: 130 }}
          onChange={(v) => setTypeFilter(v)}
          options={Object.entries(typeLabelMap).map(([value, label]) => ({ value, label }))}
        />
      </div>

      <Table
        rowKey="id"
        columns={columns}
        dataSource={reviews}
        loading={isLoading}
        pagination={{ pageSize: 20 }}
      />

      <Modal
        title={selectedTask?.title || '审核任务'}
        open={!!selectedTask}
        onCancel={() => setSelectedTask(null)}
        footer={null}
        width={640}
      >
        {selectedTask && (
          <div>
            <Descriptions column={2} size="small" bordered style={{ marginBottom: 16 }}>
              <Descriptions.Item label="ID">{selectedTask.id}</Descriptions.Item>
              <Descriptions.Item label="状态">
                <Tag color={statusColorMap[selectedTask.status]}>
                  {statusLabelMap[selectedTask.status]}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="类型">{typeLabelMap[selectedTask.task_type]}</Descriptions.Item>
              <Descriptions.Item label="分配给">{selectedTask.assigned_to || '-'}</Descriptions.Item>
              <Descriptions.Item label="描述" span={2}>{selectedTask.description}</Descriptions.Item>
              <Descriptions.Item label="创建时间">
                {dayjs(selectedTask.created_at).format('YYYY-MM-DD HH:mm')}
              </Descriptions.Item>
              {selectedTask.resolved_at && (
                <Descriptions.Item label="解决时间">
                  {dayjs(selectedTask.resolved_at).format('YYYY-MM-DD HH:mm')}
                </Descriptions.Item>
              )}
            </Descriptions>

            {selectedTask.status !== 'resolved' && selectedTask.status !== 'expired' && (
              <Card title="提交决策" size="small" style={{ marginBottom: 16 }}>
                <DecisionForm
                  kbId={kbId!}
                  taskId={selectedTask.id}
                  onSuccess={() => setSelectedTask(null)}
                />
              </Card>
            )}

            {decisions && decisions.length > 0 && (
              <Card title="历史决策" size="small">
                {decisions.map((d) => (
                  <Descriptions key={d.id} column={1} size="small" bordered style={{ marginBottom: 8 }}>
                    <Descriptions.Item label="决策类型">{d.decision_type}</Descriptions.Item>
                    <Descriptions.Item label="理由">{d.rationale}</Descriptions.Item>
                    <Descriptions.Item label="决策人">{d.decided_by}</Descriptions.Item>
                    <Descriptions.Item label="时间">{dayjs(d.decided_at).format('YYYY-MM-DD HH:mm')}</Descriptions.Item>
                  </Descriptions>
                ))}
              </Card>
            )}
          </div>
        )}
      </Modal>
    </div>
  );
}
