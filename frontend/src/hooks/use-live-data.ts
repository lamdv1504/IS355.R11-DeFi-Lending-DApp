"use client";
import { useEffect, useState } from "react";
import { useWallet } from "@/components/wallet-provider";
import { walletError } from "@/lib/wallet-client";
import { CHAINS, same } from "@/lib/wallet-transactions";

export function useLiveData(path: string | null) {
  const { client, state } = useWallet();
  const [result, setResult] = useState<{ path: string | null; data: Record<string, unknown> | null; error: string; loading: boolean }>({ path: null, data: null, error: "", loading: true });
  useEffect(() => {
    const abort = new AbortController();
    if (!path) { const task = setTimeout(() => setResult({ path: null, data: null, error: "", loading: false }), 0); return () => { clearTimeout(task); abort.abort(); }; }
    let inFlight = false;
    const load = async () => {
      if (inFlight) return; inFlight = true;
      try {
        const data = await client.json(path, { signal: abort.signal });
        if (data.network !== state.network || data.chain_id !== CHAINS[state.network] || (data.wallet_address && !same(data.wallet_address, path.match(/\/accounts\/(0x[0-9a-fA-F]{40})\//)?.[1] || state.account))) throw new Error("Dữ liệu API không khớp ví hoặc mạng đã chọn.");
        if (!abort.signal.aborted) setResult({ path, data, error: "", loading: false });
      } catch (error) { if (!abort.signal.aborted) setResult((previous) => ({ path, data: previous.path === path ? previous.data : null, loading: false, error: walletError(error) })); }
      finally { inFlight = false; }
    };
    const initial = setTimeout(() => void load(), 0), ticker = setInterval(() => void load(), 10_000);
    return () => { clearTimeout(initial); clearInterval(ticker); abort.abort(); };
  }, [client, path, state.account, state.network, state.epoch, state.revision]);
  return result.path === path ? result : { data: null, error: "", loading: !!path };
}
