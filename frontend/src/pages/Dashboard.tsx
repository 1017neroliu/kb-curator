import { Row, Col, Card, Statistic, Spin, Alert, Empty } from 'antd';
import {
  FileTextOutlined,
  CheckCircleOutlined,
  InboxOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import { useKnowledgeBase } from '../hooks/useKnowledgeBases';
import { useReviews } from '../hooks/useReviews';
import { useQualityReports } from '../hooks/useQuality';
import { useEvents } from '../hooks/useEvents';
import QualityScore from '../components/QualityScore';
import EventTimeline from '../components/EventTimeline';

function useCurrentKbId() {
  return localStorage.getItem('kb_curator_kb_id') || undefined;
}

export default function Dashboard() {
  const kbId = useCurrentKbId();
  const { data: kbOverview, isLoading: kbLoading, error: kbError } = useKnowledgeBase(kbId);
  const { data: reviews } = useReviews(kbId, { status: 'pending', limit: 5 });
  const { data: reports } = useQualityReports(kbId, { limit: 1 });
  const { data: events } = useEvents(kbId, { limit: 10 });
  const latestReport = reports?.[0];

  if (!kbId) {
    return (
      <Empty description="请先在顶部选择一个知识库" style={{ marginTop: 100 }} />
    );
  }

  if (kbLoading) return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />;
  if (kbError) return <Alert type="error" message="加载知识库信息失败" />;

  return (
    <div>
      <Row gutter={[16, 16]}>
        <Col span={6}>
          <Card>
            <Statistic
              title="总条目数"
              value={kbOverview?.total_entries ?? 0}
              prefix={<FileTextOutlined />}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="活跃条目"
              value={kbOverview?.active_entries ?? 0}
              prefix={<CheckCircleOutlined />}
              valueStyle={{ color: '#52c41a' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="已归档"
              value={kbOverview?.archived_entries ?? 0}
              prefix={<InboxOutlined />}
              valueStyle={{ color: '#999' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="待审核"
              value={reviews?.length ?? 0}
              prefix={<WarningOutlined />}
              valueStyle={{ color: '#faad14' }}
            />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col span={8}>
          <Card title="质量评分">
            {latestReport ? (
              <QualityScore score={latestReport.score} />
            ) : (
              <Empty description="暂无质量报告" />
            )}
          </Card>
        </Col>
        <Col span={16}>
          <Card title="最近变更事件">
            {events && events.length > 0 ? (
              <EventTimeline events={events} />
            ) : (
              <Empty description="暂无变更事件" />
            )}
          </Card>
        </Col>
      </Row>
    </div>
  );
}
