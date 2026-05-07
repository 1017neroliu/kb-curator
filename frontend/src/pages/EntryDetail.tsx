import { useParams, useNavigate } from 'react-router-dom';
import { Descriptions, Card, Spin, Tag, Button, Typography, Space } from 'antd';
import { ArrowLeftOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import { useEntry } from '../hooks/useEntries';
import type { EntryStatus } from '../api/types';

const { Paragraph } = Typography;

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

export default function EntryDetail() {
  const { entryId } = useParams<{ entryId: string }>();
  const navigate = useNavigate();
  const kbId = localStorage.getItem('kb_curator_kb_id') || undefined;
  const { data: entry, isLoading } = useEntry(kbId, entryId);

  if (isLoading) return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />;
  if (!entry) return <Card><div style={{ textAlign: 'center' }}>条目不存在</div></Card>;

  return (
    <div>
      <Button
        icon={<ArrowLeftOutlined />}
        onClick={() => navigate('/entries')}
        style={{ marginBottom: 16 }}
      >
        返回列表
      </Button>
      <Card title={entry.title}>
        <Descriptions column={2} bordered>
          <Descriptions.Item label="ID">{entry.id}</Descriptions.Item>
          <Descriptions.Item label="状态">
            <Tag color={statusColorMap[entry.status]}>
              {statusLabelMap[entry.status]}
            </Tag>
          </Descriptions.Item>
          <Descriptions.Item label="版本">{entry.version}</Descriptions.Item>
          <Descriptions.Item label="来源 ID">{entry.source_id}</Descriptions.Item>
          <Descriptions.Item label="来源 URL" span={2}>
            {entry.source_url || '-'}
          </Descriptions.Item>
          <Descriptions.Item label="标签" span={2}>
            <Space>
              {entry.tags.map((t) => <Tag key={t}>{t}</Tag>)}
              {entry.tags.length === 0 && '-'}
            </Space>
          </Descriptions.Item>
          <Descriptions.Item label="创建时间">
            {dayjs(entry.created_at).format('YYYY-MM-DD HH:mm:ss')}
          </Descriptions.Item>
          <Descriptions.Item label="更新时间">
            {dayjs(entry.updated_at).format('YYYY-MM-DD HH:mm:ss')}
          </Descriptions.Item>
          {entry.expires_at && (
            <Descriptions.Item label="过期时间" span={2}>
              {dayjs(entry.expires_at).format('YYYY-MM-DD HH:mm:ss')}
            </Descriptions.Item>
          )}
          <Descriptions.Item label="内容" span={2}>
            <Paragraph style={{ whiteSpace: 'pre-wrap', margin: 0 }}>
              {entry.content}
            </Paragraph>
          </Descriptions.Item>
        </Descriptions>
      </Card>
    </div>
  );
}
