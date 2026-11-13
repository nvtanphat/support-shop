import { useEffect, useState } from 'react';
import { api } from './api';
import type { OrderDetail } from './types';

export type OrderState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'ready'; order: OrderDetail }
  | { status: 'error'; message: string };

// Orders change (status, return progress), so a fetched order is only reused for a short time.
const TTL_MS = 30_000;
const cache = new Map<string, { at: number; promise: Promise<OrderDetail> }>();

export function fetchOrder(code: string): Promise<OrderDetail> {
  const hit = cache.get(code);
  if (hit && Date.now() - hit.at < TTL_MS) return hit.promise;
  const promise = api.getOrder(code);
  cache.set(code, { at: Date.now(), promise });
  // A failed lookup must not be served from cache: forget it so the next render retries.
  promise.catch(() => cache.delete(code));
  return promise;
}

export function clearOrderCache(): void {
  cache.clear();
}

/** Loads one order by code; `null` means "no order selected". Errors are returned, never hidden. */
export function useOrder(code: string | null): OrderState {
  const [state, setState] = useState<OrderState>({ status: 'idle' });

  useEffect(() => {
    if (!code) {
      setState({ status: 'idle' });
      return;
    }
    let cancelled = false;
    setState({ status: 'loading' });
    fetchOrder(code)
      .then((order) => !cancelled && setState({ status: 'ready', order }))
      .catch((err: unknown) =>
        !cancelled && setState({ status: 'error', message: err instanceof Error ? err.message : 'Không tải được đơn hàng.' })
      );
    return () => {
      cancelled = true;
    };
  }, [code]);

  return state;
}
