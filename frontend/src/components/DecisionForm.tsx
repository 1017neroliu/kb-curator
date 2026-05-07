import { useState } from 'react';
import { Form, Select, Input, Button, message } from 'antd';
import { useSubmitDecision } from '../hooks/useReviews';
import type { DecisionType } from '../api/types';

interface DecisionFormProps {
  kbId: string;
  taskId: string;
  onSuccess?: () => void;
}

const decisionOptions: { label: string; value: DecisionType }[] = [
  { label: '采纳新内容', value: 'accept_new' },
  { label: '保留旧内容', value: 'keep_old' },
  { label: '合并内容', value: 'merge' },
  { label: '忽略', value: 'ignore' },
  { label: '删除', value: 'delete' },
  { label: '归档', value: 'archive' },
];

export default function DecisionForm({ kbId, taskId, onSuccess }: DecisionFormProps) {
  const [form] = Form.useForm();
  const [decidedBy, setDecidedBy] = useState('admin');
  const submitDecision = useSubmitDecision(kbId, taskId);

  const handleSubmit = async (values: { decision_type: DecisionType; rationale: string; merge_content?: string }) => {
    try {
      await submitDecision.mutateAsync({
        body: {
          decision_type: values.decision_type,
          rationale: values.rationale,
          merge_content: values.merge_content,
        },
        decidedBy,
      });
      message.success('决策已提交');
      form.resetFields();
      onSuccess?.();
    } catch {
      message.error('提交失败');
    }
  };

  const selectedType = Form.useWatch('decision_type', form);

  return (
    <Form form={form} layout="vertical" onFinish={handleSubmit}>
      <Form.Item label="决策人" required>
        <Input value={decidedBy} onChange={(e) => setDecidedBy(e.target.value)} />
      </Form.Item>
      <Form.Item name="decision_type" label="决策类型" rules={[{ required: true }]}>
        <Select options={decisionOptions} placeholder="选择决策类型" />
      </Form.Item>
      <Form.Item name="rationale" label="理由" rules={[{ required: true }]}>
        <Input.TextArea rows={3} placeholder="请输入决策理由" />
      </Form.Item>
      {selectedType === 'merge' && (
        <Form.Item name="merge_content" label="合并内容">
          <Input.TextArea rows={4} placeholder="请输入合并后的内容" />
        </Form.Item>
      )}
      <Form.Item>
        <Button type="primary" htmlType="submit" loading={submitDecision.isPending}>
          提交决策
        </Button>
      </Form.Item>
    </Form>
  );
}
