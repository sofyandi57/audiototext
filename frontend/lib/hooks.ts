"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "./api";

/**
 * Load data and keep polling while `shouldPoll(data)` is true. Polling pauses
 * while the tab is hidden to save battery/data on phones.
 */
export function useResource<T>(
  load: () => Promise<T>,
  deps: unknown[],
  shouldPoll: (data: T | null) => boolean = () => false,
  intervalMs = 2000,
) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);
  const loadRef = useRef(load);
  loadRef.current = load;
  const pollRef = useRef(shouldPoll);
  pollRef.current = shouldPoll;
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const alive = useRef(true);
  const generation = useRef(0);

  const refresh = useCallback(async (): Promise<T | null> => {
    const gen = generation.current;
    let d: T | null = null;
    try {
      d = await loadRef.current();
      if (gen !== generation.current) return d; // deps changed meanwhile
      setData(d);
      setError(null);
    } catch (e) {
      if (gen === generation.current) setError(e instanceof ApiError ? e : new ApiError(0, String(e)));
    } finally {
      if (gen === generation.current) setLoading(false);
    }
    // (Re)arm polling after every load, including manual refreshes, so an
    // action that starts a job is followed until the job finishes.
    if (alive.current && gen === generation.current && pollRef.current(d) && !timer.current) {
      const wait = () => {
        timer.current = setTimeout(() => {
          timer.current = null;
          if (!alive.current) return;
          if (typeof document !== "undefined" && document.hidden) return wait();
          refresh();
        }, intervalMs);
      };
      wait();
    }
    return d;
  }, [intervalMs]);

  useEffect(() => {
    alive.current = true;
    generation.current += 1;
    setLoading(true);
    refresh();
    return () => {
      alive.current = false;
      if (timer.current) clearTimeout(timer.current);
      timer.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return { data, error, loading, refresh, setData };
}

export function useLocalStorage<T>(key: string, initial: T): [T, (v: T) => void] {
  const [value, setValue] = useState<T>(initial);
  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(key);
      if (raw != null) setValue(JSON.parse(raw));
    } catch {
      /* storage unavailable (private mode) */
    }
  }, [key]);
  const set = useCallback(
    (v: T) => {
      setValue(v);
      try {
        window.localStorage.setItem(key, JSON.stringify(v));
      } catch {
        /* ignore */
      }
    },
    [key],
  );
  return [value, set];
}
