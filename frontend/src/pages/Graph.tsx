import { useState } from 'react';
import {
  Card, Table, Tag, Statistic, Row, Col, Space, Button, Modal, Descriptions, Empty, Input, Tabs,
} from 'antd';
import {
  AppstoreOutlined, NodeIndexOutlined, ShareAltOutlined, SearchOutlined,
} from '@ant-design/icons';
import {
  useGraphStats, useGraphEntities, useGraphRelations, useEntityNeighbors,
} from '../hooks/useGraph';
import type { KGEntityRead, KGRelationRead } from '../api/types';

export default function Graph() {
  const kbId = localStorage.getItem('kb_curator_kb_id') || undefined;
  const [entityTypeFilter, setEntityTypeFilter] = useState<string | undefined>();
  const [relationTypeFilter, setRelationTypeFilter] = useState<string | undefined>();
  const [selectedEntity, setSelectedEntity] = useState<string | null>(null);
  const [neighborModalOpen, setNeighborModalOpen] = useState(false);

  const { data: stats, isLoading: statsLoading } = useGraphStats(kbId);
  const { data: entities, isLoading: entitiesLoading } = useGraphEntities(kbId, {
    entity_type: entityTypeFilter,
    limit: 100,
  });
  const { data: relations, isLoading: relationsLoading } = useGraphRelations(kbId, {
    relation_type: relationTypeFilter,
    limit: 100,
  });
  const { data: neighbors, isLoading: neighborsLoading } = useEntityNeighbors(kbId, selectedEntity || undefined);

  if (!kbId) {
    return <Card><Empty description="请先选择知识库" style={{ marginTop: 40 }} /></Card>;
  }

  const handleViewNeighbors = (entityId: string) => {
    setSelectedEntity(entityId);
    setNeighborModalOpen(true);
  };

  const entityColumns = [
    {
      title: 'ID',
      dataIndex: 'id',
      key: 'id',
      width: 120,
      render: (id: string) => <span style={{ fontFamily: 'monospace', fontSize: 12 }}>{id.slice(0, 12)}...</span>,
    },
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
      width: 200,
    },
    {
      title: '类型',
      dataIndex: 'entity_type',
      key: 'entity_type',
      width: 120,
      render: (type: string) => <Tag color="blue">{type}</Tag>,
    },
    {
      title: '置信度',
      dataIndex: 'confidence',
      key: 'confidence',
      width: 100,
      render: (v: number) => v.toFixed(2),
    },
    {
      title: '邻居数',
      key: 'neighbor_count',
      width: 90,
      render: (_: unknown, record: KGEntityRead) => {
        const props = record.properties as Record<string, unknown> | null;
        return (props?._neighbor_count as number) ?? 0;
      },
    },
    {
      title: '操作',
      key: 'action',
      width: 100,
      render: (_: unknown, record: KGEntityRead) => (
        <Button size="small" onClick={() => handleViewNeighbors(record.id)}>
          邻居
        </Button>
      ),
    },
  ];

  const relationColumns = [
    {
      title: 'ID',
      dataIndex: 'id',
      key: 'id',
      width: 120,
      render: (id: string) => <span style={{ fontFamily: 'monospace', fontSize: 12 }}>{id.slice(0, 12)}...</span>,
    },
    {
      title: '源实体',
      dataIndex: 'source_entity_id',
      key: 'source',
      width: 140,
      render: (id: string) => {
        const name = entities?.find(e => e.id === id)?.name;
        return name || <span style={{ fontFamily: 'monospace', fontSize: 12 }}>{id.slice(0, 12)}...</span>;
      },
    },
    {
      title: '关系类型',
      dataIndex: 'relation_type',
      key: 'relation_type',
      width: 150,
      render: (type: string) => <Tag color="green">{type}</Tag>,
    },
    {
      title: '目标实体',
      dataIndex: 'target_entity_id',
      key: 'target',
      width: 140,
      render: (id: string) => {
        const name = entities?.find(e => e.id === id)?.name;
        return name || <span style={{ fontFamily: 'monospace', fontSize: 12 }}>{id.slice(0, 12)}...</span>;
      },
    },
    {
      title: '置信度',
      dataIndex: 'confidence',
      key: 'confidence',
      width: 100,
      render: (v: number) => v.toFixed(2),
    },
  ];

  return (
    <div>
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={8}>
          <Card loading={statsLoading}>
            <Statistic
              title="实体数量"
              value={stats?.entity_count || 0}
              prefix={<NodeIndexOutlined />}
            />
          </Card>
        </Col>
        <Col span={8}>
          <Card loading={statsLoading}>
            <Statistic
              title="关系数量"
              value={stats?.relation_count || 0}
              prefix={<ShareAltOutlined />}
            />
          </Card>
        </Col>
        <Col span={8}>
          <Card loading={statsLoading}>
            <Statistic
              title="孤立实体"
              value={stats?.orphan_entity_count || 0}
              prefix={<AppstoreOutlined />}
              valueStyle={stats?.orphan_entity_count ? { color: '#faad14' } : undefined}
            />
          </Card>
        </Col>
      </Row>

      <Card>
        <Tabs
          items={[
            {
              key: 'entities',
              label: `实体 (${entities?.length || 0})`,
              children: (
                <div>
                  <div style={{ marginBottom: 16 }}>
                    <Space>
                      <span>按类型过滤：</span>
                      <Input
                        placeholder="输入实体类型"
                        style={{ width: 200 }}
                        value={entityTypeFilter || ''}
                        onChange={(e) => setEntityTypeFilter(e.target.value || undefined)}
                        allowClear
                      />
                    </Space>
                  </div>
                  <Table
                    rowKey="id"
                    columns={entityColumns}
                    dataSource={entities || []}
                    loading={entitiesLoading}
                    pagination={{ pageSize: 20 }}
                    size="small"
                  />
                </div>
              ),
            },
            {
              key: 'relations',
              label: `关系 (${relations?.length || 0})`,
              children: (
                <div>
                  <div style={{ marginBottom: 16 }}>
                    <Space>
                      <span>按类型过滤：</span>
                      <Input
                        placeholder="输入关系类型"
                        style={{ width: 200 }}
                        value={relationTypeFilter || ''}
                        onChange={(e) => setRelationTypeFilter(e.target.value || undefined)}
                        allowClear
                      />
                    </Space>
                  </div>
                  <Table
                    rowKey="id"
                    columns={relationColumns}
                    dataSource={relations || []}
                    loading={relationsLoading}
                    pagination={{ pageSize: 20 }}
                    size="small"
                  />
                </div>
              ),
            },
          ]}
        />
      </Card>

      <Modal
        title={`实体邻居 — ${selectedEntity?.slice(0, 12)}...`}
        open={neighborModalOpen}
        onCancel={() => { setNeighborModalOpen(false); setSelectedEntity(null); }}
        footer={null}
        width={640}
      >
        {neighborsLoading ? (
          <div style={{ textAlign: 'center', padding: 24 }}>加载中...</div>
        ) : neighbors?.neighbors?.length ? (
          <Table
            rowKey={(_: unknown, index?: number) => `neighbor-${index ?? 0}`}
            columns={[
              {
                title: '邻居实体',
                key: 'neighbor',
                render: (_: unknown, record: Record<string, unknown>) => (
                  <span>{String(record.neighbor_name || record.neighbor_id || '-')}</span>
                ),
              },
              {
                title: '类型',
                key: 'neighbor_type',
                dataIndex: 'neighbor_type',
                render: (type: string) => type ? <Tag color="blue">{type}</Tag> : '-',
              },
              {
                title: '关系',
                key: 'relation',
                dataIndex: 'relation_type',
                render: (type: string) => type ? <Tag color="green">{type}</Tag> : '-',
              },
              {
                title: '置信度',
                key: 'confidence',
                dataIndex: 'confidence',
                render: (v: number) => v != null ? v.toFixed(2) : '-',
              },
            ]}
            dataSource={neighbors.neighbors}
            pagination={false}
            size="small"
          />
        ) : (
          <Empty description="该实体无邻居" />
        )}
      </Modal>
    </div>
  );
}
