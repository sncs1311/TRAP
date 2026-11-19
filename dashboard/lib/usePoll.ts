"use client";
import { useCallback, useEffect, useRef, useState } from "react";

export function usePoll<T>(fetcher: () => Promise<T>, intervalMs: number) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const run = useCallback(async () => {
    try {
      setData(await fetcherRef.current());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e)); // keep last good data
    }
  }, []);

  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    const loop = async () => {
      await run();
      if (!stopped) timer = setTimeout(loop, intervalMs);
    };
    loop();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [run, intervalMs]);

  return { data, error, refresh: run };
}