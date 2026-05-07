import { Routes, Route } from 'react-router-dom';
import { ConfigProvider, App as AntApp } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import MainLayout from './layouts/MainLayout';
import Dashboard from './pages/Dashboard';
import Entries from './pages/Entries';
import EntryDetail from './pages/EntryDetail';
import Reviews from './pages/Reviews';
import Events from './pages/Events';
import Sources from './pages/Sources';
import Quality from './pages/Quality';
import Graph from './pages/Graph';

export default function App() {
  return (
    <ConfigProvider locale={zhCN}>
      <AntApp>
        <Routes>
          <Route element={<MainLayout />}>
            <Route path="/" element={<Dashboard />} />
            <Route path="/entries" element={<Entries />} />
            <Route path="/entries/:entryId" element={<EntryDetail />} />
            <Route path="/reviews" element={<Reviews />} />
            <Route path="/events" element={<Events />} />
            <Route path="/sources" element={<Sources />} />
            <Route path="/quality" element={<Quality />} />
            <Route path="/graph" element={<Graph />} />
          </Route>
        </Routes>
      </AntApp>
    </ConfigProvider>
  );
}
