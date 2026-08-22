import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Navigate, NavLink, Outlet, Route, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth";
import Account360 from "./pages/Account360";
import BriefPage from "./pages/BriefPage";
import Login from "./pages/Login";
import Renewals from "./pages/Renewals";
import Workbench from "./pages/Workbench";

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 15_000, retry: 1 } },
});

function Shell() {
  const { token, role, logout } = useAuth();
  if (!token) return <Navigate to="/login" replace />;
  return (
    <div className="layout">
      <nav className="sidenav">
        <div className="brand">Revenue Intelligence Graph</div>
        <NavLink to="/" end>Workbench</NavLink>
        <NavLink to="/renewals">Renewals</NavLink>
        <NavLink to="/brief">Executive Brief</NavLink>
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
          <Route element={<Shell />}>
            <Route path="/" element={<Workbench />} />
            <Route path="/renewals" element={<Renewals />} />
            <Route path="/brief" element={<BriefPage />} />
            <Route path="/accounts/:accountId" element={<Account360 />} />
          </Route>
        </Routes>
      </AuthProvider>
    </QueryClientProvider>
  );
}
