import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Table, Button, Space, Tag, Modal, Form, Input, Select, message, Popconfirm, Card, Upload, Tooltip, Dropdown,
} from 'antd';
import type { MenuProps } from 'antd';
import { PlusOutlined, SearchOutlined, UploadOutlined, ThunderboltOutlined, InboxOutlined, StopOutlined, UndoOutlined, MoreOutlined, DeleteOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import {
  useEntries, useCreateEntry, useDeleteEntry, useSearchEntries, useProcessEntry, useUploadDocument, useUpdateEntry,
} from '../hooks/useEntries';
import type { KnowledgeEntryRead, EntryStatus, KnowledgeEntryCreate } from '../api/types';
import SearchBar from '../components/SearchBar';

const statusColorMap: Record<EntryStatus, string> = {
  active: 'green',
  archived: 'default',
  deprecated: 'red',
};
const statusLabelMap: Record<EntryStatus, string> = {
  active: '活跃',
  archived: '已归档',
  deprecated: '已废弃',
};

export default function Entries() {
  const kbId = localStorage.getItem('kb_curator_kb_id') || undefined;
  const navigate = useNavigate();
  const [statusFilter, setStatusFilter] = useState<EntryStatus | undefined>();
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [uploadModalOpen, setUploadModalOpen] = useState(false);
  const [searchMode, setSearchMode] = useState(false);
  const [searchResults, setSearchResults] = useState<KnowledgeEntryRead[]>([]);
  const [processingEntryId, setProcessingEntryId] = useState<string | null>(null);
  const [form] = Form.useForm();

  const { data: entries, isLoading } = useEntries(kbId, { status: statusFilter, limit: 100 });
  const createEntry = useCreateEntry(kbId);
  const deleteEntry = useDeleteEntry(kbId);
  const searchMutation = useSearchEntries(kbId);
  const processEntry = useProcessEntry(kbId);
  const uploadDocument = useUploadDocument(kbId);
  const updateEntry = useUpdateEntry(kbId);

  const handleStatusChange = async (entryId: string, newStatus: EntryStatus) => {
    const labels: Record<EntryStatus, string> = { active: '恢复', archived: '归档', deprecated: '废弃' };
    try {
      await updateEntry.mutateAsync({ entryId, body: { status: newStatus } });
      message.success(`条目已${labels[newStatus]}`);
    } catch {
      message.error('操作失败');
    }
  };

  const handleCreate = async (values: Omit<KnowledgeEntryCreate, 'kb_id'>) => {
    try {
      await createEntry.mutateAsync(values);
      message.success('条目已创建');
      setCreateModalOpen(false);
      form.resetFields();
    } catch {
      message.error('创建失败');
    }
  };

  const handleDelete = async (entryId: string) => {
    try {
      await deleteEntry.mutateAsync(entryId);
      message.success('条目已删除');
    } catch {
      message.error('删除失败');
    }
  };

  const handleSearch = (query: string) => {
    searchMutation.mutate(
      { query, top_k: 20 },
      {
        onSuccess: () => {
          setSearchMode(true);
        },
      },
    );
  };

  const handleProcess = async (entryId: string) => {
    setProcessingEntryId(entryId);
    try {
      const result = await processEntry.mutateAsync(entryId);
      message.success(`处理完成：${result.chunks} 个分块，${result.entities} 个实体，${result.relations} 个关系`);
    } catch {
      message.error('处理失败');
    } finally {
      setProcessingEntryId(null);
    }
  };

  const handleUpload = async (file: File) => {
    try {
      const result = await uploadDocument.mutateAsync({ file });
      if (result.processed) {
        message.success(`上传并处理完成：${result.chunks} 个分块，${result.entities} 个实体`);
      } else {
        message.success('文档已上传，但未自动处理');
      }
      setUploadModalOpen(false);
    } catch {
      message.error('上传失败');
    }
    return false; // prevent default upload behavior
  };

  const isProcessed = (record: KnowledgeEntryRead): boolean => {
    const meta = record.metadata as Record<string, unknown> | null;
    return !!(meta && meta.processed);
  };

  const hasExtractionResults = (record: KnowledgeEntryRead): boolean => {
    const meta = record.metadata as Record<string, unknown> | null;
    if (!meta || !meta.extraction_summary) return false;
    const summary = meta.extraction_summary as { entities?: number; relations?: number };
    return (summary.entities ?? 0) > 0 || (summary.relations ?? 0) > 0;
  };

  const columns = [
    {
      title: '标题',
      dataIndex: 'title',
      key: 'title',
      render: (text: string, record: KnowledgeEntryRead) => (
        <a onClick={() => navigate(`/entries/${record.id}`)}>{text}</a>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: EntryStatus) => (
        <Tag color={statusColorMap[status]}>{statusLabelMap[status]}</Tag>
      ),
    },
    {
      title: '处理',
      key: 'processed',
      width: 80,
      render: (_: unknown, record: KnowledgeEntryRead) => (
        isProcessed(record)
          ? <Tag color="blue">已处理</Tag>
          : <Tag color="default">未处理</Tag>
      ),
    },
    {
      title: '版本',
      dataIndex: 'version',
      key: 'version',
      width: 80,
    },
    {
      title: '标签',
      dataIndex: 'tags',
      key: 'tags',
      width: 200,
      render: (tags: string[]) => tags.map((t) => <Tag key={t}>{t}</Tag>),
    },
    {
      title: '更新时间',
      dataIndex: 'updated_at',
      key: 'updated_at',
      width: 180,
      render: (v: string) => dayjs(v).format('YYYY-MM-DD HH:mm'),
    },
    {
      title: '操作',
      key: 'action',
      width: 140,
      render: (_: unknown, record: KnowledgeEntryRead) => {
        const menuItems: MenuProps['items'] = [
          ...(record.status === 'active'
            ? [
                { key: 'archive', icon: <InboxOutlined />, label: '归档', danger: false },
                { key: 'deprecate', icon: <StopOutlined />, label: '废弃', danger: true },
                { type: 'divider' as const },
              ]
            : []),
          ...(record.status === 'archived' || record.status === 'deprecated'
            ? [
                { key: 'restore', icon: <UndoOutlined />, label: '恢复', danger: false },
                { type: 'divider' as const },
              ]
            : []),
          { key: 'delete', icon: <DeleteOutlined />, label: '删除', danger: true },
        ];

        const handleMenuClick: MenuProps['onClick'] = ({ key }) => {
          const confirmMap: Record<string, { title: string; action: () => void }> = {
            archive: { title: '确定归档该条目？', action: () => handleStatusChange(record.id, 'archived') },
            deprecate: { title: '确定废弃该条目？', action: () => handleStatusChange(record.id, 'deprecated') },
            restore: { title: '确定恢复该条目为活跃状态？', action: () => handleStatusChange(record.id, 'active') },
            delete: { title: '确定删除该条目？此操作不可恢复', action: () => handleDelete(record.id) },
          };
          const item = confirmMap[key];
          if (item) {
            Modal.confirm({
              title: item.title,
              okText: '确定',
              cancelText: '取消',
              okButtonProps: key === 'delete' || key === 'deprecate' ? { danger: true } : undefined,
              onOk: item.action,
            });
          }
        };

        return (
          <Space size={8}>
            {!isProcessed(record) ? (
              <Tooltip title="处理条目：提取知识分块、实体和关系">
                <Button size="small" type="primary" icon={<ThunderboltOutlined />} loading={processingEntryId === record.id} onClick={() => handleProcess(record.id)}>处理</Button>
              </Tooltip>
            ) : !hasExtractionResults(record) ? (
              <Tooltip title="上次抽取结果为空，点击重新处理">
                <Button size="small" type="primary" icon={<ThunderboltOutlined />} loading={processingEntryId === record.id} onClick={() => handleProcess(record.id)}>重新处理</Button>
              </Tooltip>
            ) : (
              <Tooltip title="重新抽取知识（覆盖已有结果）">
                <Button size="small" icon={<ThunderboltOutlined />} loading={processingEntryId === record.id} onClick={() => handleProcess(record.id)}>重新处理</Button>
              </Tooltip>
            )}
            <Dropdown menu={{ items: menuItems, onClick: handleMenuClick }} trigger={['click']}>
              <Button size="small" icon={<MoreOutlined />} />
            </Dropdown>
          </Space>
        );
      },
    },
  ];

  if (!kbId) {
    return <Card><div style={{ textAlign: 'center', padding: 40 }}>请先选择知识库</div></Card>;
  }

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between' }}>
        <Space>
          <Select
            placeholder="状态过滤"
            allowClear
            style={{ width: 120 }}
            onChange={(v) => setStatusFilter(v)}
            options={[
              { label: '活跃', value: 'active' },
              { label: '已归档', value: 'archived' },
              { label: '已废弃', value: 'deprecated' },
            ]}
          />
          <Button
            icon={<SearchOutlined />}
            onClick={() => setSearchMode(!searchMode)}
            type={searchMode ? 'primary' : 'default'}
          >
            语义搜索
          </Button>
        </Space>
        <Space>
          <Button icon={<UploadOutlined />} onClick={() => setUploadModalOpen(true)}>
            上传文档
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateModalOpen(true)}>
            新建条目
          </Button>
        </Space>
      </div>

      {searchMode && (
        <Card style={{ marginBottom: 16 }}>
          <SearchBar
            kbId={kbId}
            onResultClick={(entryId) => navigate(`/entries/${entryId}`)}
          />
        </Card>
      )}

      <Table
        rowKey="id"
        columns={columns}
        dataSource={entries}
        loading={isLoading}
        pagination={{ pageSize: 20 }}
      />

      <Modal
        title="新建知识条目"
        open={createModalOpen}
        onCancel={() => setCreateModalOpen(false)}
        onOk={() => form.submit()}
        confirmLoading={createEntry.isPending}
      >
        <Form form={form} layout="vertical" onFinish={handleCreate}>
          <Form.Item name="title" label="标题" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="content" label="内容" rules={[{ required: true }]}>
            <Input.TextArea rows={4} />
          </Form.Item>
          <Form.Item name="source_id" label="来源 ID" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="source_url" label="来源 URL">
            <Input />
          </Form.Item>
          <Form.Item name="tags" label="标签">
            <Select mode="tags" placeholder="输入标签后回车" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="上传文档"
        open={uploadModalOpen}
        onCancel={() => setUploadModalOpen(false)}
        footer={null}
      >
        <Upload.Dragger
          accept=".txt,.md,.json,.yaml,.yml,.csv,.html,.xml,.rst"
          customRequest={({ file, onSuccess, onError }) => {
            handleUpload(file as File)
              .then(() => onSuccess?.(null))
              .catch(() => onError?.(new Error('Upload failed')));
          }}
          showUploadList={false}
          disabled={uploadDocument.isPending}
        >
          <p className="ant-upload-drag-icon">
            <UploadOutlined style={{ fontSize: 48, color: '#1677ff' }} />
          </p>
          <p className="ant-upload-text">点击或拖拽文件到此区域上传</p>
          <p className="ant-upload-hint">
            支持 .txt, .md, .json, .yaml, .yml, .csv, .html, .xml, .rst 格式
          </p>
        </Upload.Dragger>
        {uploadDocument.isPending && (
          <div style={{ textAlign: 'center', marginTop: 16 }}>
            <span>正在上传并处理文档...</span>
          </div>
        )}
      </Modal>
    </div>
  );
}
