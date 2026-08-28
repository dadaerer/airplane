#!/usr/bin/env python3
"""特价机票雷达：Google Flights 往返最低价监控 + 降价微信提醒。

用法:
  python monitor.py              # 正式运行（需要能访问 Google）
  python monitor.py --dry-run    # 不访问网络，用随机价格测试整套流程
  python monitor.py --only NGB   # 只查某个出发地
  python monitor.py --limit 20   # 只查前 20 条组合（调试用）

环境变量:
  SERVERCHAN_SEND_KEY   Server酱 SendKey，不设则只打印不推送
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parent
HISTORY = ROOT / "data" / "history.json"
LATEST = ROOT / "data" / "latest.json"
WEEKDAY = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}
TZ_CN = timezone(timedelta(hours=8))


# ---------------------------------------------------------------- 工具函数
def now_cn() -> datetime:
    return datetime.now(TZ_CN)


def load_json(path: Path, default):
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default


def save_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


# ---------------------------------------------------------------- 日期生成
def build_trips(cfg: dict) -> list[dict]:
    """返回 [{label, depart, return}]，按出发日排序去重。"""
    trips: dict[tuple[str, str], dict] = {}
    today = date.today()

    wk = cfg.get("weekends") or {}
    for pat in wk.get("patterns", []):
        d_wd, r_wd = WEEKDAY[pat[0]], WEEKDAY[pat[1]]
        # 找到下一个出发星期
        first = today + timedelta(days=(d_wd - today.weekday()) % 7 or 7)
        for i in range(int(wk.get("weeks_ahead", 8))):
            dep = first + timedelta(weeks=i)
            back_off = (r_wd - d_wd) % 7 or 7
            ret = dep + timedelta(days=back_off)
            key = (dep.isoformat(), ret.isoformat())
            trips.setdefault(key, {"label": f"周末 {pat[0]}→{pat[1]}", "depart": key[0], "return": key[1]})

    for h in cfg.get("holidays") or []:
        dep, ret = str(h["depart"]), str(h["return"])
        if date.fromisoformat(dep) <= today:
            continue
        trips[(dep, ret)] = {"label": f"假期·{h['name']}", "depart": dep, "return": ret}

    return sorted(trips.values(), key=lambda t: t["depart"])


# ---------------------------------------------------------------- 查询
def query_price(origin: str, dest: str, dep: str, ret: str, cfg: dict, dry_run: bool):
    """返回 (min_price, airlines, url) 或 (None, None, url)。"""
    from fast_flights import FlightQuery, Passengers, create_query, get_flights
    from fast_flights.exceptions import FlightsNotFound

    q = create_query(
        flights=[
            FlightQuery(date=dep, from_airport=origin, to_airport=dest, max_stops=cfg.get("max_stops")),
            FlightQuery(date=ret, from_airport=dest, to_airport=origin, max_stops=cfg.get("max_stops")),
        ],
        trip="round-trip",
        seat="economy",
        passengers=Passengers(adults=int(cfg.get("adults", 1))),
        currency=cfg.get("currency", "CNY"),
        language=cfg.get("language", "zh-CN"),
    )
    url = q.url()

    if dry_run:
        return random.choice([None, random.randint(800, 4000)]), ["测试航司"], url

    rq = cfg.get("request") or {}
    last_err = None
    for attempt in range(int(rq.get("retries", 2)) + 1):
        try:
            res = get_flights(q)
            priced = [f for f in res if f.price and f.price > 0]
            if not priced:
                return None, None, url
            best = min(priced, key=lambda f: f.price)
            return int(best.price), list(best.airlines), url
        except FlightsNotFound:
            return None, None, url
        except Exception as e:  # 限流/解析失败等
            last_err = e
            time.sleep(5 * (attempt + 1))
    print(f"  ! {origin}->{dest} {dep} 失败: {last_err}", file=sys.stderr)
    raise RuntimeError(str(last_err))


# ---------------------------------------------------------------- 推送
def push_serverchan(title: str, desp: str) -> None:
    key = os.environ.get("SERVERCHAN_SEND_KEY", "").strip()
    if not key:
        print("\n[未配置 SERVERCHAN_SEND_KEY，以下为推送内容预览]\n" + title + "\n" + desp)
        return
    r = requests.post(f"https://sctapi.ftqq.com/{key}.send", data={"title": title, "desp": desp}, timeout=20)
    print("Server酱:", r.status_code, r.text[:120])


# ---------------------------------------------------------------- 主流程
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only", help="只查某个出发地，如 NGB")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    with open(ROOT / "config.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    origins = [args.only] if args.only else cfg["origins"]
    dests: dict[str, str] = cfg["destinations"]
    trips = build_trips(cfg)
    al = cfg.get("alerts") or {}
    rq = cfg.get("request") or {}

    history: dict = load_json(HISTORY, {})   # key -> {"series":[[ts,price],...], "last_alert": ts, ...}
    run_ts = now_cn().strftime("%Y-%m-%d %H:%M")

    combos = [(o, d, t) for o in origins for d in dests for t in trips]
    if args.limit:
        combos = combos[: args.limit]
    print(f"共 {len(combos)} 个查询（{len(origins)} 出发地 × {len(dests)} 目的地 × {len(trips)} 个日期）")

    latest: list[dict] = []
    alerts: list[dict] = []
    fails = 0

    for i, (o, d, t) in enumerate(combos, 1):
        key = f"{o}-{d}-{t['depart']}-{t['return']}"
        try:
            price, airlines, url = query_price(o, d, t["depart"], t["return"], cfg, args.dry_run)
        except RuntimeError:
            fails += 1
            price, airlines, url = None, None, ""
        rec = history.setdefault(key, {"series": [], "last_alert": None})
        prev = rec["series"][-1][1] if rec["series"] else None
        min_seen = min((p for _, p in rec["series"] if p), default=None)

        if price is not None:
            rec["series"].append([run_ts, price])
            rec["series"] = rec["series"][-60:]  # 每条只保留最近 60 次

        row = {
            "key": key, "origin": o, "dest": d, "dest_name": dests[d], "label": t["label"],
            "depart": t["depart"], "return": t["return"], "price": price, "prev": prev,
            "min_seen": min_seen, "airlines": airlines or [], "url": url, "ts": run_ts,
        }
        latest.append(row)

        # ---- 是否提醒
        if price is not None:
            target = (al.get("target_price") or {}).get(d, al.get("target_price_default", 0))
            reasons = []
            if prev and prev - price >= al.get("drop_abs", 10**9):
                reasons.append(f"↓{prev - price}元")
            if prev and (prev - price) / prev * 100 >= al.get("drop_pct", 999):
                reasons.append(f"↓{(prev - price) / prev * 100:.0f}%")
            if target and price <= target:
                reasons.append(f"低于心理价{target}")
            cooled = True
            if rec.get("last_alert"):
                last = datetime.strptime(rec["last_alert"], "%Y-%m-%d %H:%M").replace(tzinfo=TZ_CN)
                cooled = now_cn() - last >= timedelta(hours=al.get("cooldown_hours", 20))
            if reasons and cooled:
                rec["last_alert"] = run_ts
                alerts.append({**row, "reasons": reasons})

        flag = "" if price else " (无结果)"
        print(f"[{i}/{len(combos)}] {o}→{d} {t['depart']}~{t['return']}: {price}{flag}")
        if not args.dry_run:
            time.sleep(random.uniform(rq.get("sleep_min", 2), rq.get("sleep_max", 5)))

    save_json(HISTORY, history)
    save_json(LATEST, {"run_ts": run_ts, "rows": latest, "fails": fails})

    # ---- 推送
    if alerts:
        alerts.sort(key=lambda a: a["price"])
        n = int(al.get("max_items_per_push", 15))
        lines = []
        for a in alerts[:n]:
            lines.append(
                f"- **{a['origin']}→{a['dest_name']}** {a['depart']}~{a['return']}（{a['label']}）"
                f" **¥{a['price']}** {'/'.join(a['reasons'])}"
                + (f"，上次¥{a['prev']}" if a['prev'] else "")
                + f" [查看]({a['url']})"
            )
        more = f"\n\n…还有 {len(alerts) - n} 条，见看板。" if len(alerts) > n else ""
        push_serverchan(f"✈️ {len(alerts)} 条特价 最低¥{alerts[0]['price']} {alerts[0]['dest_name']}",
                        "\n".join(lines) + more + f"\n\n查询时间 {run_ts}")
    else:
        print("本轮没有触发提醒。")

    if combos and fails / len(combos) > 0.5:
        push_serverchan("⚠️ 机票雷达：超过一半查询失败", f"{fails}/{len(combos)} 失败，可能被限流或 fast-flights 需要升级。")

    # ---- 生成看板
    from report import build_report
    build_report(cfg, latest, history, run_ts, ROOT / "docs" / "index.html")
    print("看板已生成 docs/index.html")
    return 0


if __name__ == "__main__":
    sys.exit(main())
