import { useState } from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { Layout, Menu, Select, Typography, Space, theme, Button, Modal, Input, App } from 'antd';
import {
  DashboardOutlined,
  FileTextOutlined,
  AuditOutlined,
  SwapOutlined,
  DatabaseOutlined,
  SafetyCertificateOutlined,
  AppstoreOutlined,
  PlusOutlined,
} from '@ant-design/icons';
import { useKnowledgeBases, useCreateKnowledgeBase } from '../hooks/useKnowledgeBases';

const { Sider, Header, Content } = Layout;
const { Title } = Typography;

const menuItems = [
  { key: '/', icon: <DashboardOutlined />, label: '仪表盘' },
  { key: '/entries', icon: <FileTextOutlined />, label: '知识条目' },
  { key: '/reviews', icon: <AuditOutlined />, label: '审核任务' },
  { key: '/events', icon: <SwapOutlined />, label: '变更事件' },
  { key: '/sources', icon: <DatabaseOutlined />, label: '数据源' },
  { key: '/quality', icon: <SafetyCertificateOutlined />, label: '质量报告' },
  { key: '/graph', icon: <AppstoreOutlined />, label: '知识图谱' },
];

export default function MainLayout() {
  const [collapsed, setCollapsed] = useState(false);
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [newKbId, setNewKbId] = useState('');
  const navigate = useNavigate();
  const location = useLocation();
  const { token: themeToken } = theme.useToken();
  const { message } = App.useApp();

  const { data: kbList } = useKnowledgeBases();
  const createKb = useCreateKnowledgeBase();
  const currentKbId = localStorage.getItem('kb_curator_kb_id') || '';
  const setCurrentKbId = (id: string) => {
    localStorage.setItem('kb_curator_kb_id', id);
    window.location.reload();
  };

  const handleCreateKb = () => {
    const id = newKbId.trim();
    if (!id) return;
    createKb.mutate(id, {
      onSuccess: () => {
        message.success(`知识库 "${id}" 创建成功`);
        setCreateModalOpen(false);
        setNewKbId('');
        setCurrentKbId(id);
      },
      onError: () => {
        message.error(`知识库 "${id}" 创建失败`);
      },
    });
  };

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider collapsible collapsed={collapsed} onCollapse={setCollapsed}>
        <div style={{ padding: '12px 16px' }}>
          <Title level={5} style={{ color: '#fff', margin: 0, whiteSpace: 'nowrap' }}>
            {collapsed ? 'KB' : 'KB-Curator'}
          </Title>
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[location.pathname]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
        />
      </Sider>
      <Layout>
        <Header
          style={{
            background: themeToken.colorBgContainer,
            padding: '0 24px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            borderBottom: `1px solid ${themeToken.colorBorderSecondary}`,
          }}
        >
          <Space>
            <span>当前知识库：</span>
            <Select
              value={currentKbId || undefined}
              placeholder="选择知识库"
              style={{ width: 200 }}
              onChange={setCurrentKbId}
              options={(kbList || []).map((id) => ({ label: id, value: id }))}
              allowClear
            />
            <Button
              type="primary"
              icon={<PlusOutlined />}
              size="small"
              onClick={() => setCreateModalOpen(true)}
            >
              新建
            </Button>
          </Space>
        </Header>
        <Content style={{ margin: 24, minHeight: 280 }}>
          <Outlet />
        </Content>
      </Layout>
      <Modal
        title="新建知识库"
        open={createModalOpen}
        onOk={handleCreateKb}
        onCancel={() => { setCreateModalOpen(false); setNewKbId(''); }}
        okText="创建"
        cancelText="取消"
        okButtonProps={{ disabled: !newKbId.trim(), loading: createKb.isPending }}
      >
        <Input
          placeholder="输入知识库 ID（如 my-kb）"
          value={newKbId}
          onChange={(e) => setNewKbId(e.target.value)}
          onPressEnter={handleCreateKb}
          autoFocus
        />
      </Modal>
    </Layout>
  );
}
