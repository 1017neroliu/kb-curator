import { useState } from 'react';
import { Input, Button, Space, List, Typography, Card } from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import { useSearchEntries } from '../hooks/useEntries';
import type { SearchResult } from '../api/types';

const { Text, Paragraph } = Typography;

interface SearchBarProps {
  kbId: string;
  onResultClick?: (entryId: string) => void;
}

export default function SearchBar({ kbId, onResultClick }: SearchBarProps) {
  const [query, setQuery] = useState('');
  const searchMutation = useSearchEntries(kbId);
  const [results, setResults] = useState<SearchResult[]>([]);

  const handleSearch = () => {
    if (!query.trim()) return;
    searchMutation.mutate(
      { query, top_k: 10 },
      {
        onSuccess: (data) => setResults(data),
      },
    );
  };

  return (
    <div>
      <Space.Compact style={{ width: '100%' }}>
        <Input
          size="large"
          placeholder="输入搜索内容..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onPressEnter={handleSearch}
        />
        <Button
          size="large"
          type="primary"
          icon={<SearchOutlined />}
          loading={searchMutation.isPending}
          onClick={handleSearch}
        >
          搜索
        </Button>
      </Space.Compact>

      {results.length > 0 && (
        <List
          style={{ marginTop: 16 }}
          dataSource={results}
          renderItem={(item) => (
            <List.Item
              style={{ cursor: 'pointer' }}
              onClick={() => onResultClick?.(item.entry_id)}
            >
              <Card size="small" style={{ width: '100%' }}>
                <Paragraph ellipsis={{ rows: 2 }}>{item.content}</Paragraph>
                <Text type="secondary">
                  相似度: {(item.score * 100).toFixed(1)}% | 条目 ID: {item.entry_id}
                </Text>
              </Card>
            </List.Item>
          )}
        />
      )}
    </div>
  );
}
