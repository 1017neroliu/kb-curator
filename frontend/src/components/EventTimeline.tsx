import { Timeline, Tag, Typography } from 'antd';
import {
  PlusCircleOutlined,
  ExclamationCircleOutlined,
  EditOutlined,
  WarningOutlined,
  MinusCircleOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import type { ChangeEventRead, ChangeType } from '../api/types';

const { Text, Paragraph } = Typography;

const typeConfig: Record<ChangeType, { color: string; icon: React.ReactNode; label: string }> = {
  new_info: { color: 'green', icon: <PlusCircleOutlined />, label: '新信息' },
  policy_change: { color: 'blue', icon: <EditOutlined />, label: '策略变更' },
  contradiction: { color: 'red', icon: <ExclamationCircleOutlined />, label: '矛盾' },
  correction: { color: 'orange', icon: <WarningOutlined />, label: '纠正' },
  redundant: { color: 'default', icon: <MinusCircleOutlined />, label: '冗余' },
};

interface EventTimelineProps {
  events: ChangeEventRead[];
}

export default function EventTimeline({ events }: EventTimelineProps) {
  return (
    <Timeline
      items={events.map((event) => {
        const config = typeConfig[event.change_type];
        return {
          color: config.color,
          dot: config.icon,
          children: (
            <div>
              <div style={{ marginBottom: 4 }}>
                <Tag color={config.color}>{config.label}</Tag>
                <Text strong>{event.title}</Text>
                <Text type="secondary" style={{ marginLeft: 8 }}>
                  {dayjs(event.detected_at).format('YYYY-MM-DD HH:mm')}
                </Text>
              </div>
              {event.content_after && (
                <Paragraph
                  ellipsis={{ rows: 2, expandable: true, symbol: '展开' }}
                  style={{ margin: 0, color: '#666' }}
                >
                  {event.content_after}
                </Paragraph>
              )}
            </div>
          ),
        };
      })}
    />
  );
}
