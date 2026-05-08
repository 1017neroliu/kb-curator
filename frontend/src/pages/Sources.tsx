import { useState, useEffect, useRef } from 'react';
import {
  Table, Button, Modal, Form, Input, Select, Switch, InputNumber, message, Popconfirm, Card, Empty, Tag, Space, Progress,
} from 'antd';
import { PlusOutlined, SyncOutlined, LoadingOutlined, CheckCircleOutlined, CloseCircleOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import { useQueryClient } from '@tanstack/react-query';
import { useSources, useCreateSource, useUpdateSource, useDeleteSource, usePollSources } from '../hooks/useSources';
import type { DataSourceRead, SourceType } from '../api/types';

const sourceTypeLabels: Record<string, string> = {
  wiki: 'Wiki',
  confluence: 'Confluence',
  jira: 'Jira',
  file: '文件目录',
  conversation_log: '对话日志',
  webpage: '网页链接',
};

export default function Sources() {
  const kbId = localStorage.getItem('kb_curator_kb_id') || undefined;
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [editingSource, setEditingSource] = useState<DataSourceRead | null>(null);
  const [createForm] = Form.useForm();
  const [editForm] = Form.useForm();
  const queryClient = useQueryClient();

  const { data: sources, isLoading } = useSources(kbId);
  const createSource = useCreateSource(kbId);
  const updateSource = useUpdateSource(kbId);
  const deleteSource = useDeleteSource(kbId);
  const pollSources = usePollSources(kbId);

  // Watch source_type in create form for conditional config fields
  const createSourceType = Form.useWatch('source_type', createForm);

  // Auto-refresh sources list while any source is scanning
  const refreshTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const hasScanning = (sources ?? []).some((s) => s.scan_status === 'scanning');

  useEffect(() => {
    if (hasScanning) {
      if (!refreshTimerRef.current) {
        refreshTimerRef.current = setInterval(() => {
          queryClient.invalidateQueries({ queryKey: ['sources', kbId] });
        }, 3000);
      }
    } else {
      if (refreshTimerRef.current) {
        clearInterval(refreshTimerRef.current);
        refreshTimerRef.current = null;
      }
    }
    return () => {
      if (refreshTimerRef.current) {
        clearInterval(refreshTimerRef.current);
        refreshTimerRef.current = null;
      }
    };
  }, [hasScanning, kbId, queryClient]);

  if (!kbId) {
    return <Card><Empty description="请先选择知识库" style={{ marginTop: 40 }} /></Card>;
  }

  const handleCreate = async (values: {
    name: string;
    source_type: SourceType;
    poll_interval_minutes: number;
    enabled: boolean;
    // file fields
    base_path?: string;
    file_patterns?: string;
    recursive?: boolean;
    // wiki fields
    wiki_url?: string;
    api_path?: string;
    wiki_username?: string;
    wiki_password?: string;
    namespaces?: string;
    // confluence fields
    confluence_url?: string;
    confluence_username?: string;
    api_token?: string;
    space_key?: string;
    // jira fields
    jira_url?: string;
    jira_username?: string;
    jira_api_token?: string;
    project_key?: string;
    jql?: string;
    include_comments?: boolean;
    // webpage fields
    webpage_urls?: string;
    css_selector?: string;
    include_links?: boolean;
    max_pages?: number;
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
      } else if (values.source_type === 'wiki') {
        connection_config.url = values.wiki_url || '';
        connection_config.api_path = values.api_path || '/w/api.php';
        if (values.wiki_username) connection_config.username = values.wiki_username;
        if (values.wiki_password) connection_config.password = values.wiki_password;
        if (values.namespaces) {
          connection_config.namespaces = values.namespaces.split(',').map((s) => Number(s.trim())).filter((n) => !isNaN(n));
        }
      } else if (values.source_type === 'confluence') {
        connection_config.url = values.confluence_url || '';
        connection_config.username = values.confluence_username || '';
        connection_config.api_token = values.api_token || '';
        if (values.space_key) connection_config.space_key = values.space_key;
      } else if (values.source_type === 'jira') {
        connection_config.url = values.jira_url || '';
        connection_config.username = values.jira_username || '';
        connection_config.api_token = values.jira_api_token || '';
        if (values.project_key) connection_config.project_key = values.project_key;
        if (values.jql) connection_config.jql = values.jql;
        connection_config.include_comments = values.include_comments !== false;
      } else if (values.source_type === 'webpage') {
        connection_config.urls = (values.webpage_urls || '')
          .split('\n')
          .map((s) => s.trim())
          .filter((s) => s.length > 0);
        if (values.css_selector) connection_config.css_selector = values.css_selector;
        connection_config.include_links = values.include_links === true;
        connection_config.max_pages = values.max_pages || 50;
      }

      const result = await createSource.mutateAsync({
        name: values.name,
        source_type: values.source_type,
        poll_interval_minutes: values.poll_interval_minutes,
        enabled: values.enabled,
        connection_config,
      });

      // Close modal immediately — the initial scan runs in the background
      setCreateModalOpen(false);
      createForm.resetFields();
      message.success(`数据源「${result.name}」已创建` + (result.scan_status === 'scanning' ? '，后台扫描已启动' : ''));
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
        if (record.source_type === 'wiki') {
          return (
            <span style={{ fontSize: 12, color: '#666' }}>
              {String(config.url || '-')}
            </span>
          );
        }
        if (record.source_type === 'confluence') {
          return (
            <span style={{ fontSize: 12, color: '#666' }}>
              {String(config.url || '-')}
              {config.space_key ? ` / ${config.space_key}` : ''}
            </span>
          );
        }
        if (record.source_type === 'jira') {
          return (
            <span style={{ fontSize: 12, color: '#666' }}>
              {String(config.url || '-')}
              {config.project_key ? ` / ${config.project_key}` : ''}
            </span>
          );
        }
        if (record.source_type === 'webpage') {
          const urls = (config.urls as string[]) || [];
          return (
            <span style={{ fontSize: 12, color: '#666' }}>
              {urls.length} 个 URL
              {urls.length > 0 ? ` — ${urls[0]}` : ''}
            </span>
          );
        }
        return '-';
      },
    },
    {
      title: '扫描状态',
      dataIndex: 'scan_status',
      key: 'scan_status',
      width: 160,
      render: (status: string) => {
        if (status === 'scanning') {
          return (
            <Space direction="vertical" size={2} style={{ width: '100%' }}>
              <Space size={4}>
                <LoadingOutlined spin style={{ color: '#1677ff' }} />
                <span style={{ fontSize: 12, color: '#1677ff' }}>扫描中</span>
              </Space>
              <Progress percent={99} size="small" status="active" showInfo={false} />
            </Space>
          );
        }
        if (status === 'completed') {
          return (
            <Space size={4}>
              <CheckCircleOutlined style={{ color: '#52c41a' }} />
              <span style={{ fontSize: 12, color: '#52c41a' }}>已完成</span>
            </Space>
          );
        }
        if (status === 'failed') {
          return (
            <Space size={4}>
              <CloseCircleOutlined style={{ color: '#ff4d4f' }} />
              <span style={{ fontSize: 12, color: '#ff4d4f' }}>失败</span>
            </Space>
          );
        }
        return <span style={{ fontSize: 12, color: '#999' }}>待扫描</span>;
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

          {/* File type fields */}
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

          {/* Wiki type fields */}
          {createSourceType === 'wiki' && (
            <>
              <Form.Item
                name="wiki_url"
                label="Wiki URL"
                rules={[{ required: createSourceType === 'wiki', message: '请输入 Wiki URL' }]}
              >
                <Input placeholder="https://wiki.example.com" />
              </Form.Item>
              <Form.Item name="api_path" label="API 路径" initialValue="/w/api.php">
                <Input placeholder="/w/api.php" />
              </Form.Item>
              <Form.Item name="wiki_username" label="用户名 (可选)">
                <Input placeholder="用于 Basic Auth 认证" />
              </Form.Item>
              <Form.Item name="wiki_password" label="密码 (可选)">
                <Input.Password placeholder="用于 Basic Auth 认证" />
              </Form.Item>
              <Form.Item name="namespaces" label="命名空间 ID" initialValue="0">
                <Input placeholder="0 (多个用逗号分隔，如 0,1,2)" />
              </Form.Item>
            </>
          )}

          {/* Confluence type fields */}
          {createSourceType === 'confluence' && (
            <>
              <Form.Item
                name="confluence_url"
                label="Confluence URL"
                rules={[{ required: createSourceType === 'confluence', message: '请输入 Confluence URL' }]}
              >
                <Input placeholder="https://your-domain.atlassian.net" />
              </Form.Item>
              <Form.Item
                name="confluence_username"
                label="用户名 / 邮箱"
                rules={[{ required: createSourceType === 'confluence', message: '请输入用户名或邮箱' }]}
              >
                <Input placeholder="user@example.com" />
              </Form.Item>
              <Form.Item
                name="api_token"
                label="API Token"
                rules={[{ required: createSourceType === 'confluence', message: '请输入 API Token' }]}
              >
                <Input.Password placeholder="Atlassian API Token" />
              </Form.Item>
              <Form.Item name="space_key" label="Space Key">
                <Input placeholder="PROJ (留空则扫描全部)" />
              </Form.Item>
            </>
          )}

          {/* Jira type fields */}
          {createSourceType === 'jira' && (
            <>
              <Form.Item
                name="jira_url"
                label="Jira URL"
                rules={[{ required: createSourceType === 'jira', message: '请输入 Jira URL' }]}
              >
                <Input placeholder="https://your-domain.atlassian.net" />
              </Form.Item>
              <Form.Item
                name="jira_username"
                label="用户名 / 邮箱"
                rules={[{ required: createSourceType === 'jira', message: '请输入用户名或邮箱' }]}
              >
                <Input placeholder="user@example.com" />
              </Form.Item>
              <Form.Item
                name="jira_api_token"
                label="API Token"
                rules={[{ required: createSourceType === 'jira', message: '请输入 API Token' }]}
              >
                <Input.Password placeholder="Atlassian API Token" />
              </Form.Item>
              <Form.Item name="project_key" label="项目 Key">
                <Input placeholder="PROJ" />
              </Form.Item>
              <Form.Item name="jql" label="JQL (可选)">
                <Input placeholder="project = PROJ ORDER BY updated DESC" />
              </Form.Item>
              <Form.Item name="include_comments" label="包含评论" valuePropName="checked" initialValue={true}>
                <Switch />
              </Form.Item>
            </>
          )}

          {/* Webpage type fields */}
          {createSourceType === 'webpage' && (
            <>
              <Form.Item
                name="webpage_urls"
                label="URL 列表"
                rules={[{ required: createSourceType === 'webpage', message: '请输入至少一个 URL' }]}
              >
                <Input.TextArea rows={4} placeholder="每行一个 URL&#10;https://en.wikipedia.org/wiki/Knowledge_graph&#10;https://example.com/docs" />
              </Form.Item>
              <Form.Item name="css_selector" label="CSS 选择器 (可选)">
                <Input placeholder="article, .content, #main" />
              </Form.Item>
              <Form.Item name="include_links" label="包含同域链接" valuePropName="checked" initialValue={false}>
                <Switch />
              </Form.Item>
              <Form.Item name="max_pages" label="最大页面数" initialValue={50}>
                <InputNumber min={1} max={500} style={{ width: '100%' }} />
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
