import { useCallback, useEffect, useState } from "react";

export function useHistoryRequest<T>(scope: string | null, load: (signal: AbortSignal) => Promise<T>) {
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<{scope: string | null; data: T | null; loading: boolean; error: string | null}>({scope: null, data: null, loading: false, error: null});
  const retry = useCallback(() => setAttempt(n => n + 1), []);
  useEffect(() => {
    if (!scope) return;
    const controller = new AbortController();
    setState({scope, data: null, loading: true, error: null});
    load(controller.signal).then(data => {
      if (!controller.signal.aborted) setState({scope, data, loading: false, error: null});
    }).catch(err => {
      if (controller.signal.aborted) return;
      const status = err?.response?.status;
      const error = status === 401 ? "Sign in to view this history." : status === 403 ? "You do not have access to this history." : status === 404 ? "This league or franchise could not be found." : "History could not be loaded. Please try again.";
      setState({scope, data: null, loading: false, error});
    });
    return () => controller.abort();
  }, [scope, load, attempt]);
  return {...(state.scope === scope ? state : {data: null, loading: !!scope, error: null}), retry};
}
