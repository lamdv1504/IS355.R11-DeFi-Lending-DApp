"use client";

import { useCallback, useEffect, useState } from "react";
import { applyDemoAction, createDemo, restoreDemo, STORAGE_KEY, type DemoAction, type DemoState } from "@/lib/lending-demo";

export function useLendingDemo() {
  const [state, setState] = useState<DemoState | null>(null);
  const [now, setNow] = useState(0);
  const [notice, setNotice] = useState("");
  useEffect(() => {
    let active = true;
    const task = window.setTimeout(() => {
      let initial: DemoState;
      try {
        const saved = localStorage.getItem(STORAGE_KEY);
        initial = saved ? restoreDemo(saved) : createDemo();
      } catch {
        initial = createDemo();
        if (active) setNotice("Không đọc được dữ liệu đã lưu. Đã tạo lại phiên mô phỏng.");
      }
      if (active) { setState(initial); setNow(Date.now()); }
    }, 0);
    const ticker = window.setInterval(() => setNow(Date.now()), 1000);
    return () => { active = false; clearTimeout(task); clearInterval(ticker); };
  }, []);
  useEffect(() => {
    if (!state) return;
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(state)); }
    catch {
      const task = setTimeout(() => setNotice("Trình duyệt không cho lưu dữ liệu. Các thao tác chỉ được giữ trong phiên này."), 0);
      return () => clearTimeout(task);
    }
  }, [state]);
  const transact = useCallback((action: DemoAction) => {
    if (!state) throw new Error("Dữ liệu chưa sẵn sàng.");
    const next = applyDemoAction(state, action, Date.now());
    setState(next);
    setNow(next.checkpointAt);
  }, [state]);
  const reset = useCallback(() => { const fresh = createDemo(); setState(fresh); setNow(fresh.checkpointAt); setNotice("Đã đặt lại dữ liệu mô phỏng."); }, []);
  return { state, now, notice, setNotice, transact, reset };
}
