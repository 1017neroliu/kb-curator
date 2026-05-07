import { useState, useRef, useEffect, useCallback } from 'react';
import { Button, Input, Typography, Space, Empty, Spin, Collapse, Tag, App } from 'antd';
import { SendOutlined, ClearOutlined, RobotOutlined, UserOutlined } from '@ant-design/icons';
import { useQAStream } from '../hooks/useQA';
import type { QASource, ChatMessage } from '../api/types';

const { TextArea } = Input;
const { Text } = Typography;

interface DisplayMessage {
  role: 'user' | 'assistant';
  content: string;
  sources?: QASource[];
  loading?: boolean;
}

export default function QA() {
  const kbId = localStorage.getItem('kb_curator_kb_id') || '';
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const streamContentRef = useRef<string>('');
  const streamSourcesRef = useRef<QASource[]>([]);
  const { message: messageApi } = App.useApp();

  const qaStream = useQAStream();

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  const handleSend = useCallback(() => {
    const question = inputValue.trim();
    if (!question || isStreaming) return;

    if (!kbId) {
      messageApi.warning('请先选择知识库');
      return;
    }

    // Add user message
    const userMsg: DisplayMessage = { role: 'user', content: question };
    // Add placeholder assistant message
    const assistantMsg: DisplayMessage = {
      role: 'assistant',
      content: '',
      sources: [],
      loading: true,
    };

    setMessages(prev => [...prev, userMsg, assistantMsg]);
    setInputValue('');
    setIsStreaming(true);

    // Reset streaming refs
    streamContentRef.current = '';
    streamSourcesRef.current = [];

    // Build history from current messages (exclude the ones we just added)
    const history: ChatMessage[] = messages.map(m => ({
      role: m.role,
      content: m.content,
    }));

    qaStream.mutate({
      request: {
        kb_id: kbId,
        question,
        history,
      },
      callbacks: {
        onSources: (sources: QASource[]) => {
          streamSourcesRef.current = sources;
        },
        onToken: (token: string) => {
          streamContentRef.current += token;
          const content = streamContentRef.current;
          const sources = streamSourcesRef.current;
          setMessages(prev => {
            const next = [...prev];
            const lastIdx = next.length - 1;
            if (next[lastIdx]?.role === 'assistant') {
              next[lastIdx] = {
                ...next[lastIdx],
                content,
                sources: sources.length > 0 ? sources : undefined,
                loading: true,
              };
            }
            return next;
          });
        },
        onDone: () => {
          const finalContent = streamContentRef.current;
          const finalSources = streamSourcesRef.current;
          setMessages(prev => {
            const next = [...prev];
            const lastIdx = next.length - 1;
            if (next[lastIdx]?.role === 'assistant') {
              next[lastIdx] = {
                ...next[lastIdx],
                content: finalContent,
                sources: finalSources.length > 0 ? finalSources : undefined,
                loading: false,
              };
            }
            return next;
          });
          setIsStreaming(false);
        },
        onError: (error: Error) => {
          setMessages(prev => {
            const next = [...prev];
            const lastIdx = next.length - 1;
            if (next[lastIdx]?.role === 'assistant') {
              next[lastIdx] = {
                ...next[lastIdx],
                content: `回答生成失败: ${error.message}`,
                loading: false,
              };
            }
            return next;
          });
          setIsStreaming(false);
        },
      },
    });
  }, [inputValue, isStreaming, kbId, messages, qaStream, messageApi]);

  const handleClear = useCallback(() => {
    setMessages([]);
    streamContentRef.current = '';
    streamSourcesRef.current = [];
  }, []);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend],
  );

  if (!kbId) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '60vh' }}>
        <Empty description="请先在顶部选择一个知识库" />
      </div>
    );
  }

  const renderSources = (sources: QASource[]) => {
    const vectorSources = sources.filter(s => s.source_type === 'vector');
    const graphSources = sources.filter(s => s.source_type === 'graph');

    const items = [];

    if (vectorSources.length > 0) {
      items.push({
        key: 'vector',
        label: `向量检索 (${vectorSources.length})`,
        children: (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {vectorSources.map((s, i) => (
              <div key={i} style={{ padding: '4px 8px', background: '#fafafa', borderRadius: 4, fontSize: 13 }}>
                <Space>
                  <Tag color="blue">score: {s.score?.toFixed(3)}</Tag>
                  {s.entry_id && <Tag>entry: {s.entry_id.slice(0, 8)}...</Tag>}
                </Space>
                <div style={{ marginTop: 4, color: '#666', whiteSpace: 'pre-wrap' }}>
                  {s.content ? (s.content.length > 150 ? s.content.slice(0, 150) + '...' : s.content) : '无内容'}
                </div>
              </div>
            ))}
          </div>
        ),
      });
    }

    if (graphSources.length > 0) {
      items.push({
        key: 'graph',
        label: `图谱关系 (${graphSources.length})`,
        children: (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {graphSources.map((s, i) => (
              <div key={i} style={{ padding: '4px 8px', background: '#fafafa', borderRadius: 4, fontSize: 13 }}>
                <Tag color="green">{s.entity_name}</Tag>
                <span style={{ color: '#999' }}>--[{s.relation_type}]--&gt;</span>
                <Tag color="orange">{s.neighbor_name}</Tag>
              </div>
            ))}
          </div>
        ),
      });
    }

    if (items.length === 0) return null;

    return (
      <Collapse
        size="small"
        items={items}
        style={{ marginTop: 8 }}
        defaultActiveKey={[]}
      />
    );
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 140px)' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Typography.Title level={4} style={{ margin: 0 }}>知识问答</Typography.Title>
        <Button
          icon={<ClearOutlined />}
          onClick={handleClear}
          disabled={messages.length === 0 || isStreaming}
        >
          清空对话
        </Button>
      </div>

      {/* Messages area */}
      <div
        style={{
          flex: 1,
          overflowY: 'auto',
          padding: '16px',
          background: '#f5f5f5',
          borderRadius: 8,
        }}
      >
        {messages.length === 0 ? (
          <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%' }}>
            <Empty description="输入问题开始对话" image={Empty.PRESENTED_IMAGE_SIMPLE} />
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {messages.map((msg, idx) => (
              <div
                key={idx}
                style={{
                  display: 'flex',
                  justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
                }}
              >
                <div
                  style={{
                    maxWidth: '70%',
                    display: 'flex',
                    flexDirection: msg.role === 'user' ? 'row-reverse' : 'row',
                    alignItems: 'flex-start',
                    gap: 8,
                  }}
                >
                  <div
                    style={{
                      width: 32,
                      height: 32,
                      borderRadius: '50%',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      flexShrink: 0,
                      background: msg.role === 'user' ? '#1677ff' : '#f0f0f0',
                      color: msg.role === 'user' ? '#fff' : '#333',
                      fontSize: 16,
                    }}
                  >
                    {msg.role === 'user' ? <UserOutlined /> : <RobotOutlined />}
                  </div>
                  <div>
                    <div
                      style={{
                        padding: '10px 14px',
                        borderRadius: msg.role === 'user'
                          ? '12px 12px 2px 12px'
                          : '12px 12px 12px 2px',
                        background: msg.role === 'user' ? '#1677ff' : '#fff',
                        color: msg.role === 'user' ? '#fff' : '#333',
                        whiteSpace: 'pre-wrap',
                        wordBreak: 'break-word',
                        boxShadow: '0 1px 2px rgba(0,0,0,0.06)',
                      }}
                    >
                      {msg.loading && !msg.content ? (
                        <Spin size="small" />
                      ) : (
                        <Text style={{ color: msg.role === 'user' ? '#fff' : 'inherit', whiteSpace: 'pre-wrap' }}>
                          {msg.content}
                        </Text>
                      )}
                      {msg.loading && msg.content && (
                        <span className="cursor-blink" style={{ display: 'inline-block', width: 2, height: 14, background: '#999', marginLeft: 2, verticalAlign: 'middle', animation: 'blink 1s step-end infinite' }}>|</span>
                      )}
                    </div>
                    {msg.role === 'assistant' && msg.sources && msg.sources.length > 0 && !msg.loading && (
                      <div style={{ maxWidth: '100%' }}>
                        {renderSources(msg.sources)}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ))}
            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      {/* Input area */}
      <div style={{ marginTop: 16, display: 'flex', gap: 8 }}>
        <TextArea
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="输入问题，按 Enter 发送，Shift+Enter 换行"
          autoSize={{ minRows: 1, maxRows: 4 }}
          disabled={isStreaming}
          style={{ flex: 1 }}
        />
        <Button
          type="primary"
          icon={<SendOutlined />}
          onClick={handleSend}
          disabled={!inputValue.trim() || isStreaming}
          loading={isStreaming}
          style={{ alignSelf: 'flex-end' }}
        >
          发送
        </Button>
      </div>

      {/* Blinking cursor animation */}
      <style>{`
        @keyframes blink {
          0%, 100% { opacity: 1; }
          50% { opacity: 0; }
        }
      `}</style>
    </div>
  );
}
