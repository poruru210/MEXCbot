#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mexcbot_core.py
A minimal gated scalper bot (DryRun by default).
"""
from __future__ import annotations
import json, time, threading, traceback
from collections import deque
from datetime import datetime
from typing import Callable, Optional, Dict, Any
try:
    import websocket  # websocket-client
except Exception:
    websocket = None

# External UI executor module
try:
    from mexcbot_executor import SeleniumBot
except Exception:
    SeleniumBot = None  # Import lazily in MexcTrader to allow DryRun

# ===== Settings =====
SYMBOL              = "suiusdt"
BINANCE_WS_URL      = f"wss://stream.binance.com:9443/stream?streams={SYMBOL}@trade/{SYMBOL}@aggTrade/{SYMBOL}@depth5@100ms"
NET_ENTRY           = 800     # cumulative net volume threshold to enter
NET_EXIT            = 752     # reverse net volume threshold to exit
SPREAD_TIGHT_USD    = 0.00020  # gate: tight spread
TAKE_PROFIT_PCT     = 0.00100  # 0.120%
STOP_LOSS_PCT       = 0.00045  # 0.045%
MAX_HOLD_SEC        = 5.0
TIGHT_GATE_WINDOW_SEC = 2.0
COOLDOWN_SEC          = 8.0
BURST_WINDOW_SEC      = 0.4

USE_SELENIUM    = True
DEBUGGER_ADDR   = "127.0.0.1:9222"

# 追加：数量指定（従来のQTY_SUIを使用）
QTY_SUI = 100.0

# ===== Trader Interfaces =====
class BaseTrader:
    def prepare_next_entry_qty(self, qty: float) -> None: raise NotImplementedError
    def fast_click_long(self) -> None: raise NotImplementedError
    def fast_click_short(self) -> None: raise NotImplementedError
    def fast_click_settle(self) -> None: raise NotImplementedError
    def heartbeat(self) -> bool: return True

class MexcTrader(BaseTrader):
    """Adapter that delegates UI operations to mexcbot_executor.SeleniumBot."""
    def __init__(self):
        if SeleniumBot is None:
            raise RuntimeError("mexcbot_executor.SeleniumBot not available")
        self.ui = SeleniumBot()
        self._qty = 0.0
    def prepare_next_entry_qty(self, qty: float) -> None:
        self._qty = float(qty)
        try:
            self.ui.set_qty(self._qty, mode=1)
        except Exception:
            pass
    def fast_click_long(self) -> None:
        self.ui.open_long()
    def fast_click_short(self) -> None:
        self.ui.open_short()
    def fast_click_settle(self) -> None:
        # Use Close All by default
        self.ui.close_all()
    def heartbeat(self) -> bool:
        try:
            return bool(self.ui.heartbeat())
        except Exception:
            return False

class DryRunTrader(BaseTrader):
    def __init__(self): self.qty = 0.0
    def prepare_next_entry_qty(self, qty: float) -> None:
        self.qty = qty; print(f"[DRY] set qty={qty}")
    def fast_click_long(self) -> None:
        print(f"[DRY] CLICK LONG qty={self.qty}")
    def fast_click_short(self) -> None:
        print(f"[DRY] CLICK SHORT qty={self.qty}")
    def fast_click_settle(self) -> None:
        print("[DRY] CLICK SETTLE (close position)")

class SeleniumTrader(BaseTrader):
    def __init__(self, debugger_addr: str):
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options as ChromeOptions
        from selenium.webdriver.common.by import By
        self.By = By
        opts = ChromeOptions(); opts.debugger_address = debugger_addr
        self.driver = webdriver.Chrome(options=opts)
        self.SELECTOR_QTY_INPUT   = None
        self.SELECTOR_LONG_BUTTON = None
        self.SELECTOR_SHORT_BUTTON= None
        self.SELECTOR_CLOSE_BUTTON= None
        self.qty_cache = 0.0
        print(f"[Selenium] attached to {debugger_addr}.")
    def _find(self, selector: Optional[str]):
        if not selector:
            print("[Selenium] セレクタ未設定。ログのみ。"); return None
        return self.driver.find_element(self.By.CSS_SELECTOR, selector)
    def prepare_next_entry_qty(self, qty: float) -> None:
        el = self._find(self.SELECTOR_QTY_INPUT)
        if el is None: self.qty_cache=qty; print(f"[Selenium] qty={qty}（ログのみ）"); return
        el.clear(); el.send_keys(str(qty)); self.qty_cache=qty; print(f"[Selenium] set qty={qty}")
    def fast_click_long(self) -> None:
        el = self._find(self.SELECTOR_LONG_BUTTON)
        if el is None: print(f"[Selenium] LONG qty={self.qty_cache}（ログのみ）"); return
        el.click(); print("[Selenium] LONG clicked")
    def fast_click_short(self) -> None:
        el = self._find(self.SELECTOR_SHORT_BUTTON)
        if el is None: print(f"[Selenium] SHORT qty={self.qty_cache}（ログのみ）"); return
        el.click(); print("[Selenium] SHORT clicked")
    def fast_click_settle(self) -> None:
        el = self._find(self.SELECTOR_CLOSE_BUTTON)
        if el is None: print("[Selenium] SETTLE（ログのみ）"); return
        el.click(); print("[Selenium] SETTLE clicked")
    def heartbeat(self) -> bool: return True

# ===== Net Volume Aggregator =====
class NetVolumeWindow:
    def __init__(self, window_sec: float):
        self.window = float(window_sec)
        self._win = deque()  # (ts, signed_qty)

    def add(self, qty: float, is_buy: bool):
        now = time.time()
        signed = qty if is_buy else -qty
        self._win.append((now, signed))
        self._cleanup(now)

    def _cleanup(self, now: float):
        cutoff = now - self.window
        w = self._win
        while w and w[0][0] < cutoff:
            w.popleft()

    def sum(self) -> float:
        return sum(v for _, v in self._win)

# ===== Spread Gate =====
class SpreadGate:
    def __init__(self, tight_usd: float):
        self.tight = float(tight_usd)
        self.last_bid = 0.0; self.last_ask = 0.0
    def update_depth(self, bid: float, ask: float) -> None:
        self.last_bid = bid; self.last_ask = ask
    def is_tight(self) -> bool:
        if self.last_bid <= 0 or self.last_ask <= 0: return False
        return (self.last_ask - self.last_bid) <= self.tight

# ===== Gate Timers =====
class GateTimers:
    def __init__(self):
        self.last_entry_ts = 0.0
        self.cooldown_until = 0.0
        self.last_burst_ts = 0.0
    def can_enter(self) -> bool:
        now = time.time()
        return now >= self.cooldown_until and (now - self.last_burst_ts) <= TIGHT_GATE_WINDOW_SEC
    def trigger_burst(self) -> None:
        self.last_burst_ts = time.time()
    def set_cooldown(self) -> None:
        self.cooldown_until = time.time() + COOLDOWN_SEC
        self.last_entry_ts = time.time()

# ===== Monitor & Strategy =====
class StrategyMonitor:
    def __init__(self, trader: BaseTrader):
        self.trader = trader
        self.netwin = NetVolumeWindow(TIGHT_GATE_WINDOW_SEC)
        self.gate = SpreadGate(SPREAD_TIGHT_USD)
        self.timers = GateTimers()
        self.position: Optional[str] = None  # "long" / "short" / None
        self.entry_price = 0.0
        self.qty_to_use = QTY_SUI
        self.running = False

    def on_trade(self, price: float, qty: float, is_buy: bool):
        self.netwin.add(qty, is_buy)
        # antiburst: mark event
        self.timers.trigger_burst()

        net = self.netwin.sum()
        if self.position is None:
            if self.gate.is_tight() and self.timers.can_enter():
                if net >= NET_ENTRY:
                    self._enter("long", price)
                elif net <= -NET_ENTRY:
                    self._enter("short", price)
        else:
            # exit logic
            if self.position == "long":
                if net <= -NET_EXIT or self._should_take_profit(price) or self._should_stop_loss(price) or self._max_hold_elapsed():
                    self._exit(price)
            elif self.position == "short":
                if net >= NET_EXIT or self._should_take_profit(price) or self._should_stop_loss(price) or self._max_hold_elapsed():
                    self._exit(price)

    def on_depth(self, best_bid: float, best_ask: float):
        self.gate.update_depth(best_bid, best_ask)

    def _enter(self, side: str, price: float):
        print(f"[ENTER] side={side} entry={price} time={datetime.utcnow().isoformat()}Z")
        self.trader.prepare_next_entry_qty(self.qty_to_use)
        if side == "long": self.trader.fast_click_long()
        else: self.trader.fast_click_short()
        self.position = side
        self.entry_price = price
        self.timers.set_cooldown()

    def _exit(self, price: float):
        pnl = (price / self.entry_price - 1.0)
        if self.position == "short": pnl = -pnl
        print(f"[EXIT] pnl={pnl*100:.3f}% hold=? at={price}")
        self.trader.fast_click_settle()
        self.position = None
        self.entry_price = 0.0

    def _should_take_profit(self, price: float) -> bool:
        if self.position == "long": return (price / self.entry_price - 1.0) >= TAKE_PROFIT_PCT
        else: return (self.entry_price / price - 1.0) >= TAKE_PROFIT_PCT

    def _should_stop_loss(self, price: float) -> bool:
        if self.position == "long": return (self.entry_price / price - 1.0) >= STOP_LOSS_PCT
        else: return (price / self.entry_price - 1.0) >= STOP_LOSS_PCT

    def _max_hold_elapsed(self) -> bool:
        if self.timers.last_entry_ts <= 0: return False
        return (time.time() - self.timers.last_entry_ts) >= MAX_HOLD_SEC

# ===== WebSocket Consumer =====
class WSClient(threading.Thread):
    def __init__(self, url: str, on_trade: Callable[[float,float,bool],None], on_depth: Callable[[float,float],None]):
        super().__init__(daemon=True)
        self.url = url
        self.on_trade = on_trade
        self.on_depth = on_depth
        self.ws = None
        self._stop = False
    def run(self):
        if websocket is None:
            print("[ERR] websocket-client is not installed.")
            return
        self.ws = websocket.WebSocketApp(
            self.url,
            on_message=self._on_message,
            on_close=lambda ws,a,b: print("[WS] CLOSED"),
            on_error=lambda ws,e: print(f"[WS] ERROR {e}"),
            on_open=lambda ws: print(f"[WS] OPEN {self.url}")
        )
        self.ws.run_forever()
    def stop(self):
        self._stop = True
        try:
            self.ws and self.ws.close()
        except Exception:
            pass
    def _on_message(self, ws, message: str):
        try:
            obj = json.loads(message)
            s = obj.get("stream","")
            d = obj.get("data",{})
            if s.endswith("@trade") or s.endswith("@aggTrade"):
                price = float(d.get("p") or d.get("price"))
                qty   = float(d.get("q") or d.get("quantity") or 0.0)
                is_buy = bool(d.get("m") is False)  # maker is seller; so m=False means buyer taker => up
                self.on_trade(price, qty, is_buy)
            elif s.endswith("@depth5@100ms"):
                # 両対応：b/a と bids/asks
                bids = d.get("b") or d.get("bids") or []
                asks = d.get("a") or d.get("asks") or []
                if bids and asks:
                    best_bid = float(bids[0][0]); best_ask = float(asks[0][0])
                    self.on_depth(best_bid, best_ask)
        except Exception as e:
            print(f"[WS] parse error: {e}")

# ===== Orchestration =====
class AutoTradingSystem:
    def __init__(self):
        trader: BaseTrader
        if USE_SELENIUM:
            try: trader = MexcTrader()
            except Exception as e:
                print(f"[WARN] Selenium起動に失敗: {e}. DryRunに切替。"); trader = DryRunTrader()
        else:
            trader = DryRunTrader()
        self.monitor = StrategyMonitor(trader)
        self.ws = WSClient(BINANCE_WS_URL, self.monitor.on_trade, self.monitor.on_depth)

    def start(self):
        try:
            self.ws.start()
        except Exception:
            traceback.print_exc()
            return
        print(f"Symbol={SYMBOL}  thresholds: NET_ENTRY={int(NET_ENTRY)}, NET_EXIT={int(NET_EXIT)}, SPREAD_TIGHT={SPREAD_TIGHT_USD}")
        print(f"Exit rules: TP={TAKE_PROFIT_PCT*100:.3f}%, SL={STOP_LOSS_PCT*100:.3f}%, MAX_HOLD={int(MAX_HOLD_SEC)}s")
        print(f"Gates: tight<={TIGHT_GATE_WINDOW_SEC}s, cooldown={COOLDOWN_SEC}s, antiburst={BURST_WINDOW_SEC}")
        print(f"Qty={self.monitor.qty_to_use}  Mode={'Selenium' if USE_SELENIUM else 'DryRun'}")
        self.monitor.start = lambda: None  # placeholder for consistency if extended
        # simple loop
        try:
            while True: time.sleep(1.0)
        except KeyboardInterrupt:
            print("\n[CTRL+C] 停止要求を受けました。")
        finally:
            try: self.ws.stop()
            except Exception: pass
            print("[DONE] 停止しました。")

if __name__ == "__main__":
    AutoTradingSystem().start()
