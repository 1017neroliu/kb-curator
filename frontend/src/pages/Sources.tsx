import { useState } from 'react';
import {
  Table, Button, Modal, Form, Input, Select, Switch, InputNumber, message, Popconfirm, Card, Empty, Tag, Space,
} from 'antd';
import { PlusOutlined, SyncOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import { useSources, useCreateSource, useUpdateSource, useDeleteSource, usePollSources } from '../hooks/useSources';
import type { DataSourceRead, SourceType } from '../api/types';

const sourceTypeLabels: Record<string, string> = {
  wiki: 'Wiki',
  confluence: 'Confluence',
  jira: 'Jira',
  file: '文件目录',
  conversation_log: '对话日志',
};

export default function Sources() {
  const kbId = localStorage.getItem('kb_curator_kb_id') || undefined;
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [editingSource, setEditingSource] = useState<DataSourceRead | null>(null);
  const [createForm] = Form.useForm();
  const [editForm] = Form.useForm();

  const { data: sources, isLoading } = useSources(kbId);
  const createSource = useCreateSource(kbId);
  const updateSource = useUpdateSource(kbId);
  const deleteSource = useDeleteSource(kbId);
  const pollSources = usePollSources(kbId);

  // Watch source_type in create form for conditional config fields
  const createSourceType = Form.useWatch('source_type', createForm);

  if (!kbId) {
    return <Card><Empty description="请先选择知识库" style={{ marginTop: 40 }} /></Card>;
  }

  const handleCreate = async (values: {
    name: string;
    source_type: SourceType;
    poll_interval_minutes: number;
    enabled: boolean;
    base_path?: string;
    file_patterns?: string;
    recursive?: boolean;
  }) => {
    try {
      // Build connection_config from form fields
      const connection_config: Record<string, unknown> = {};
      if (values.source_type === 'file') {
        connection_config.base_path = values.base_path || '';
        connection_config.file_patterns = values.file_patterns
          ? values.file_patterns.split(',').map((s) => s.trim())
          : ['*.md', '*.txt'];
        connection_config.recursive = values.recursive !== false;
      }

      await createSource.mutateAsync({
        name: values.name,
        source_type: values.source_type,
        poll_interval_minutes: values.poll_interval_minutes,
        enabled: values.enabled,
        connection_config,
      });
      message.success('数据源已创建');
      setCreateModalOpen(false);
      createForm.resetFields();
    } catch {
      message.error('创建失败');
    }
  };

  const handleUpdate = async (values: { name?: string; poll_interval_minutes?: number; enabled?: boolean }) => {
    if (!editingSource) return;
    try {
      await updateSource.mutateAsync({
        sourceId: editingSource.id,
        body: values,
      });
      message.success('数据源已更新');
      setEditModalOpen(false);
      setEditingSource(null);
    } catch {
      message.error('更新失败');
    }
  };

  const handleToggleEnabled = async (source: DataSourceRead, enabled: boolean) => {
    try {
      await updateSource.mutateAsync({
        sourceId: source.id,
        body: { enabled },
      });
      message.success(enabled ? '已启用' : '已禁用');
    } catch {
      message.error('操作失败');
    }
  };

  const handleDelete = async (sourceId: string) => {
    try {
      await deleteSource.mutateAsync(sourceId);
      message.success('数据源已删除');
    } catch {
      message.error('删除失败');
    }
  };

  const handlePoll = async () => {
    try {
      const result = await pollSources.mutateAsync();
      message.success(`轮询完成：${result.sources_polled} 个数据源，新建 ${result.entries_created} 个条目`);
      if (result.errors && result.errors.length > 0) {
        message.warning(`${result.errors.length} 个错误`);
      }
    } catch {
      message.error('轮询失败');
    }
  };

  const columns = [
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
    },
    {
      title: '类型',
      dataIndex: 'source_type',
      key: 'source_type',
      width: 120,
      render: (type: string) => <Tag>{sourceTypeLabels[type] || type}</Tag>,
    },
    {
      title: '配置',
      key: 'config',
      width: 200,
      render: (_: unknown, record: DataSourceRead) => {
        const config = record.connection_config || {};
        if (record.source_type === 'file') {
          return (
            <span style={{ fontSize: 12, color: '#666' }}>
              {String(config.base_path || '-')}
              {config.recursive !== false ? ' (递归)' : ''}
            </span>
          );
        }
        return '-';
      },
    },
    {
      title: '轮询间隔(分钟)',
      dataIndex: 'poll_interval_minutes',
      key: 'poll_interval_minutes',
      width: 130,
    },
    {
      title: '启用',
      dataIndex: 'enabled',
      key: 'enabled',
      width: 80,
      render: (enabled: boolean, record: DataSourceRead) => (
        <Switch checked={enabled} onChange={(v) => handleToggleEnabled(record, v)} />
      ),
    },
    {
      title: '上次轮询',
      dataIndex: 'last_polled_at',
      key: 'last_polled_at',
      width: 180,
      render: (v: string | null) => v ? dayjs(v).format('YYYY-MM-DD HH:mm') : '-',
    },
    {
      title: '操作',
      key: 'action',
      width: 140,
      render: (_: unknown, record: DataSourceRead) => (
        <Space>
          <Button
            size="small"
            onClick={() => {
              setEditingSource(record);
              setEditModalOpen(true);
              editForm.setFieldsValue(record);
            }}
          >
            编辑
          </Button>
          <Popconfirm title="确定删除？" onConfirm={() => handleDelete(record.id)}>
            <Button size="small" danger>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
        <Button
          icon={<SyncOutlined spin={pollSources.isPending} />}
          onClick={handlePoll}
          loading={pollSources.isPending}
        >
          轮询全部
        </Button>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateModalOpen(true)}>
          新建数据源
        </Button>
      </div>

      <Table
        rowKey="id"
        columns={columns}
        dataSource={sources}
        loading={isLoading}
        pagination={{ pageSize: 20 }}
      />

      <Modal
        title="新建数据源"
        open={createModalOpen}
        onCancel={() => setCreateModalOpen(false)}
        onOk={() => createForm.submit()}
        confirmLoading={createSource.isPending}
        width={560}
      >
        <Form form={createForm} layout="vertical" onFinish={handleCreate}>
          <Form.Item name="name" label="名称" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="source_type" label="类型" rules={[{ required: true }]}>
            <Select
              options={Object.entries(sourceTypeLabels).map(([value, label]) => ({ value, label }))}
            />
          </Form.Item>
          <Form.Item name="poll_interval_minutes" label="轮询间隔(分钟)" initialValue={60}>
            <InputNumber min={1} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="enabled" label="启用" valuePropName="checked" initialValue={true}>
            <Switch />
          </Form.Item>

          {createSourceType === 'file' && (
            <>
              <Form.Item
                name="base_path"
                label="文件目录路径"
                rules={[{ required: createSourceType === 'file', message: '请输入文件目录路径' }]}
              >
                <Input placeholder="/path/to/documents" />
              </Form.Item>
              <Form.Item name="file_patterns" label="文件匹配模式" initialValue="*.md, *.txt">
                <Input placeholder="*.md, *.txt, *.json" />
              </Form.Item>
              <Form.Item name="recursive" label="递归子目录" valuePropName="checked" initialValue={true}>
                <Switch />
              </Form.Item>
            </>
          )}
        </Form>
      </Modal>

      <Modal
        title="编辑数据源"
        open={editModalOpen}
        onCancel={() => { setEditModalOpen(false); setEditingSource(null); }}
        onOk={() => editForm.submit()}
        confirmLoading={updateSource.isPending}
      >
        <Form form={editForm} layout="vertical" onFinish={handleUpdate}>
          <Form.Item name="name" label="名称">
            <Input />
          </Form.Item>
          <Form.Item name="poll_interval_minutes" label="轮询间隔(分钟)">
            <InputNumber min={1} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="enabled" label="启用" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
