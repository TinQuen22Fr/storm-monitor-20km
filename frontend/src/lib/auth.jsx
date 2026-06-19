import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { authLogin, authMe, authRegister } from "./api";

const AuthCtx = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    const token = localStorage.getItem("storm_token");
    if (!token) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      const me = await authMe();
      setUser(me);
    } catch {
      localStorage.removeItem("storm_token");
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const login = async (email, password) => {
    const data = await authLogin(email, password);
    localStorage.setItem("storm_token", data.token);
    setUser(data.user);
    return data.user;
  };

  const register = async (email, password, name) => {
    const data = await authRegister(email, password, name);
    // New flow: only auto-logged-in if admin (auto_verified true with token)
    if (data.token) {
      localStorage.setItem("storm_token", data.token);
      setUser(data.user);
      return { user: data.user, autoVerified: true };
    }
    // Non-admin: must verify email first
    return { user: null, autoVerified: false, message: data.message, emailSent: data.email_sent };
  };

  const logout = () => {
    localStorage.removeItem("storm_token");
    setUser(null);
  };

  return (
    <AuthCtx.Provider value={{ user, loading, login, register, logout, refresh }}>
      {children}
    </AuthCtx.Provider>
  );
}

export const useAuth = () => useContext(AuthCtx);
