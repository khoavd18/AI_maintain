"use client";

import { createContext, useContext, useMemo, useState } from "react";

export type RagStatus = "not_checked" | "available" | "unavailable";

interface CopilotStatusContextValue {
  ragStatus: RagStatus;
  setRagStatus: (status: RagStatus) => void;
}

const CopilotStatusContext = createContext<CopilotStatusContextValue | null>(null);

export function CopilotStatusProvider({ children }: { children: React.ReactNode }) {
  const [ragStatus, setRagStatus] = useState<RagStatus>("not_checked");
  const value = useMemo(() => ({ ragStatus, setRagStatus }), [ragStatus]);

  return <CopilotStatusContext.Provider value={value}>{children}</CopilotStatusContext.Provider>;
}

export function useCopilotStatus() {
  const value = useContext(CopilotStatusContext);
  if (!value) throw new Error("useCopilotStatus must be used within CopilotStatusProvider");
  return value;
}
