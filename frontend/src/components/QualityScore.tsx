import { Progress, Typography } from 'antd';
import type { Severity } from '../api/types';

const { Text } = Typography;

interface QualityScoreProps {
  score: number;
  size?: number;
}

function getScoreColor(score: number): string {
  if (score >= 80) return '#52c41a';
  if (score >= 60) return '#faad14';
  return '#ff4d4f';
}

function getScoreLabel(score: number): string {
  if (score >= 80) return '优秀';
  if (score >= 60) return '良好';
  if (score >= 40) return '一般';
  return '较差';
}

export default function QualityScore({ score, size = 120 }: QualityScoreProps) {
  const color = getScoreColor(score);

  return (
    <div style={{ textAlign: 'center' }}>
      <Progress
        type="dashboard"
        percent={score}
        size={size}
        strokeColor={color}
        format={(percent) => (
          <div>
            <div style={{ fontSize: 24, fontWeight: 600, color }}>{percent}</div>
            <div style={{ fontSize: 12, color: '#999' }}>{getScoreLabel(score)}</div>
          </div>
        )}
      />
    </div>
  );
}

export function SeverityTag({ severity }: { severity: Severity }) {
  const colorMap: Record<Severity, string> = {
    info: 'blue',
    warning: 'orange',
    critical: 'red',
  };
  const labelMap: Record<Severity, string> = {
    info: '信息',
    warning: '警告',
    critical: '严重',
  };
  return <Text style={{ color: colorMap[severity], fontWeight: 500 }}>{labelMap[severity]}</Text>;
}
