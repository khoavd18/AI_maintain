"use client";

import { useMutation } from "@tanstack/react-query";

import { api } from "@/lib/api/endpoints";
import type { CopilotAskRequest } from "@/lib/api/schemas";

export function useAskCopilot() {
  return useMutation({
    mutationFn: (request: CopilotAskRequest) => api.askCopilot(request),
  });
}
