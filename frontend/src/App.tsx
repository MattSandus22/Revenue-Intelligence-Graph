import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Navigate, NavLink, Outlet, Route, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth";
import Account360 from "./pages/Account360";
import AuthCallback from "./pages/AuthCallback";
import BriefPage from "./pages/BriefPage";
import Copilot from "./pages/Copilot";
import DataQuality from "./pages/DataQuality";
import Integrations from "./pages/Integrations";
import Login from "./pages/Login";
import Renewals from "./pages/Renewals";
import Workbench from "./pages/Workbench";

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 15_000, retry: 1 } },
});

const ADMIN_ROLES = ["org_admin", "data_admin"];

function Shell() {
  const { token, role, logout } = useAuth();
  if (!token) return <Navigate to="/login" replace />;
  const isAdmin = ADMIN_ROLES.includes(role ?? "");
  return (
    <div className="layout">
      <nav className="sidenav">
        <div className="brand">Revenue Intelligence Graph</div>
        <NavLink to="/" end>Workbench</NavLink>
        <NavLink to="/renewals">Renewals</NavLink>
        <NavLink to="/brief">Executive Brief</NavLink>
        <NavLink to="/copilot">Copilot</NavLink>
        {isAdmin && <NavLink to="/integrations">Integrations</NavLink>}
        {isAdmin && <NavLink to="/data-quality">Data Quality</NavLink>}
        <div className="whoami">
          role: {role ?? "?"} · <a href="#" onClick={(e) => { e.preventDefault(); logout(); }}>sign out</a>
        </div>
      </nav>
      <main className="main"><Outlet /></main>
    </div>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/auth/callback" element={<AuthCallback />} />
          <Route element={<Shell />}>
            <Route path="/" element={<Workbench />} />
            <Route path="/renewals" element={<Renewals />} />
            <Route path="/brief" element={<BriefPage />} />
            <Route path="/copilot" element={<Copilot />} />
            <Route path="/integrations" element={<Integrations />} />
            <Route path="/data-quality" element={<DataQuality />} />
            <Route path="/accounts/:accountId" element={<Account360 />} />
          </Route>
        </Routes>
      </AuthProvider>
    </QueryClientProvider>
  );
}
