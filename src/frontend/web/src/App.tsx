import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AppShell } from "./components/layout/AppShell";
import { Overview } from "./pages/Overview";
import { Cameras } from "./pages/Cameras";
import { Security } from "./pages/Security";
import { Assistant } from "./pages/Assistant";
import { Data } from "./pages/Data";
import { Activity } from "./pages/Activity";
import { System } from "./pages/System";
import { Settings } from "./pages/Settings";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<Overview />} />
          <Route path="cameras" element={<Cameras />} />
          <Route path="security" element={<Security />} />
          <Route path="assistant" element={<Assistant />} />
          <Route path="data" element={<Data />} />
          <Route path="activity" element={<Activity />} />
          <Route path="system" element={<System />} />
          <Route path="settings" element={<Settings />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
