// The traced design and text outlines for the current settings, shared by the 2D view and the text panel.
import { useEffect, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { api, type Settings, type Trace } from "./api/client";
import { useStore } from "./store";

const TRACE_DELAY = 300;   // ms after the last change

export interface Traced {
  trace: Trace;
  /** The settings this trace was made for; the current ones may have moved on since. */
  settings: Settings;
}

export function useTrace() {
  const upload = useStore((s) => s.upload);
  const settings = useDebounced(useStore((s) => s.settings), TRACE_DELAY);
  return useQuery({
    queryKey: ["trace", upload?.id, settings],
    queryFn: async ({ signal }): Promise<Traced> => ({
      trace: await api.trace(upload!.id, settings, signal),
      settings,
    }),
    enabled: upload !== null,
    placeholderData: keepPreviousData,
    staleTime: Infinity,
    retry: false,
  });
}

function useDebounced<T>(value: T, ms: number): T {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setSettled(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return settled;
}
