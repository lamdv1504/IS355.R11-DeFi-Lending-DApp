"use client";

import { useCallback, useEffect, useState } from "react";
import { applyBorrowAction, BORROW_STORAGE_KEY, borrowCheckpoint, createBorrowDemo, restoreBorrowDemo, type BorrowAction, type BorrowState } from "@/lib/borrowing-demo";

export function useBorrowingDemo() {
  const [state, setState] = useState<BorrowState | null>(null);
  const [now, setNow] = useState(0);
  const [notice, setNotice] = useState("");
  useEffect(() => {
    const load = setTimeout(() => {
      try { const saved = localStorage.getItem(BORROW_STORAGE_KEY); setState(saved ? restoreBorrowDemo(saved) : createBorrowDemo()); }
      catch { setState(createBorrowDemo()); setNotice("Không đọc được phiên đã lưu. Đã tạo lại mô phỏng L03."); }
      setNow(Date.now());
    }, 0);
    const ticker = setInterval(() => setNow(Date.now()), 1000);
    return () => { clearTimeout(load); clearInterval(ticker); };
  }, []);
  useEffect(() => {
    if (!state) return;
    try { localStorage.setItem(BORROW_STORAGE_KEY, JSON.stringify(state)); }
    catch {
      const task = setTimeout(() => setNotice("Không lưu được trên trình duyệt. Dữ liệu chỉ được giữ trong phiên này."), 0);
      return () => clearTimeout(task);
    }
  }, [state]);
  const transact = useCallback((action: BorrowAction) => {
    if (!state) throw new Error("Dữ liệu chưa sẵn sàng.");
    setState(applyBorrowAction(state, action, Date.now()));
    setNow(Date.now());
  }, [state]);
  const reset = useCallback((empty = false) => {
    const at = Date.now(); setState(createBorrowDemo(at, empty)); setNow(at); setNotice("Đã đặt lại dữ liệu mô phỏng L03.");
  }, []);
  return { state, snapshot: state ? borrowCheckpoint(state, now) : createBorrowDemo(0), ready: state !== null, notice, setNotice, transact, reset };
}
