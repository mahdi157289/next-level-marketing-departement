import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import Dashboard from "./pages/Dashboard";
import ScoutHQ from "./pages/ScoutHQ";
import Leads from "./pages/Leads";
import LeadsDetail from "./pages/LeadsDetail";
import Runs from "./pages/Runs";
import RunsDetail from "./pages/RunsDetail";
import Agents from "./pages/Agents";
import AgentsDetail from "./pages/AgentsDetail";
import Tools from "./pages/Tools";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/scout-hq" element={<ScoutHQ />} />
          <Route path="/leads" element={<Leads />} />
          <Route path="/leads/:id" element={<LeadsDetail />} />
          <Route path="/runs" element={<Runs />} />
          <Route path="/runs/:id" element={<RunsDetail />} />
          <Route path="/agents" element={<Agents />} />
          <Route path="/agents/:name" element={<AgentsDetail />} />
          <Route path="/tools" element={<Tools />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
