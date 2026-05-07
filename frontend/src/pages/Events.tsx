import { Select, Card, Empty } from 'antd';
import { useEvents } from '../hooks/useEvents';
import EventTimeline from '../components/EventTimeline';
import type { ChangeType } from '../api/types';
import { useState } from 'react';

const changeTypeOptions: { label: string; value: ChangeType }[] = [
  { label: '新信息', value: 'new_info' },
  { label: '策略变更', value: 'policy_change' },
  { label: '矛盾', value: 'contradiction' },
  { label: '纠正', value: 'correction' },
  { label: '冗余', value: 'redundant' },
];

export default function Events() {
  const kbId = localStorage.getItem('kb_curator_kb_id') || undefined;
  const [changeType, setChangeType] = useState<ChangeType | undefined>();
  const { data: events, isLoading } = useEvents(kbId, { change_type: changeType, limit: 50 });

  if (!kbId) {
    return <Card><Empty description="请先选择知识库" style={{ marginTop: 40 }} /></Card>;
  }

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <Select
          placeholder="按变更类型过滤"
          allowClear
          style={{ width: 160 }}
          onChange={(v) => setChangeType(v)}
          options={changeTypeOptions}
        />
      </div>

      <Card loading={isLoading}>
        {events && events.length > 0 ? (
          <EventTimeline events={events} />
        ) : (
          <Empty description="暂无变更事件" />
        )}
      </Card>
    </div>
  );
}
