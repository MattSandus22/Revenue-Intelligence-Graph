import { createContext, useContext, useState } from "react";

interface AuthState {
  token: string | null;
  role: string | null;
  login: (token: string, role: string) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthState>(null!);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState(localStorage.getItem("rig_token"));
  const [role, setRole] = useState(localStorage.getItem("rig_role"));

  const login = (newToken: string, newRole: string) => {
    localStorage.setItem("rig_token", newToken);
    localStorage.setItem("rig_role", newRole);
    setToken(newToken);
    setRole(newRole);
  };
  const logout = () => {
    localStorage.removeItem("rig_token");
    localStorage.removeItem("rig_role");
    setToken(null);
    setRole(null);
  };
  return <AuthContext.Provider value={{ token, role, login, logout }}>{children}</AuthContext.Provider>;
}

export const useAuth = () => useContext(AuthContext);
