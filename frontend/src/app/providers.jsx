import { createContext, useContext, useMemo } from "react";

const AppContext = createContext({ apiBaseUrl: "" });

export function AppProviders({ children }) {
  const value = useMemo(() => ({ apiBaseUrl: import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8001/api/v1" }), []);
  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useAppConfig() {
  return useContext(AppContext);
}
