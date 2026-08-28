"""生成 docs/index.html 看板：每个目的地的当前最低价、历史最低、走势。"""
from __future__ import annotations

import html
from pathlib import Path


def sparkline(series: list, w: int = 120, h: int = 28) -> str:
    pts = [p for _, p in series if p]
    if len(pts) < 2:
        return ""
    lo, hi = min(pts), max(pts)
    rng = (hi - lo) or 1
    step = w / (len(pts) - 1)
    coords = " ".join(f"{i * step:.1f},{h - 3 - (p - lo) / rng * (h - 6):.1f}" for i, p in enumerate(pts))
    return (f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
            f'<polyline fill="none" stroke="#589CE0" stroke-width="1.5" points="{coords}"/>'
            f'<circle cx="{(len(pts)-1)*step:.1f}" cy="{h - 3 - (pts[-1] - lo) / rng * (h - 6):.1f}" r="2.5" fill="#166BC7"/></svg>')


def build_report(cfg: dict, latest: list[dict], history: dict, run_ts: str, out: Path) -> None:
    dests: dict[str, str] = cfg["destinations"]
    priced = [r for r in latest if r["price"]]

    # 每个目的地取最便宜的一条（跨出发地、跨日期）
    best_by_dest: dict[str, dict] = {}
    for r in priced:
        if r["dest"] not in best_by_dest or r["price"] < best_by_dest[r["dest"]]["price"]:
            best_by_dest[r["dest"]] = r
    cards = sorted(best_by_dest.values(), key=lambda r: r["price"])

    def change(r: dict) -> str:
        if not r["prev"]:
            return '<span class="muted">新</span>'
        diff = r["price"] - r["prev"]
        if diff < 0:
            return f'<span class="down">↓{-diff}</span>'
        if diff > 0:
            return f'<span class="up">↑{diff}</span>'
        return '<span class="muted">—</span>'

    card_html = "".join(
        f"""<a class="card" href="{html.escape(r['url'])}" target="_blank">
  <div class="dest">{html.escape(r['dest_name'])}<span class="code">{r['dest']}</span></div>
  <div class="price">¥{r['price']}<small>往返</small></div>
  <div class="meta">{r['origin']} 出发 · {r['depart']} ~ {r['return']}<br>{html.escape(r['label'])} · {html.escape('/'.join(r['airlines']) or '—')}</div>
  <div class="foot">{change(r)}{sparkline(history.get(r['key'], {}).get('series', []))}</div>
</a>""" for r in cards)

    rows_html = "".join(
        f"""<tr>
  <td>{r['origin']}</td><td>{html.escape(r['dest_name'])}</td><td>{r['depart']} ~ {r['return']}</td>
  <td class="muted">{html.escape(r['label'])}</td>
  <td class="num"><b>¥{r['price']}</b></td><td class="num">{change(r)}</td>
  <td class="num muted">{('¥' + str(r['min_seen'])) if r['min_seen'] else '—'}</td>
  <td>{sparkline(history.get(r['key'], {}).get('series', []), 90, 22)}</td>
  <td><a href="{html.escape(r['url'])}" target="_blank">查看</a></td>
</tr>""" for r in sorted(priced, key=lambda r: r["price"]))

    page = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>特价机票雷达</title>
<style>
:root{{--brand:#166BC7;--brand-50:#E8F2FB;--brand-100:#C6DEF5;--brand-700:#0E488A;--t1:#1F2329;--t2:#4E5969;--t3:#86909C;--line:#E5E6EB;--bg:#F5F7FA}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--t1);font:14px/1.5 -apple-system,"PingFang SC","Microsoft YaHei",sans-serif}}
.wrap{{max-width:1100px;margin:0 auto;padding:24px 16px}}
h1{{font-size:20px;margin:0 0 4px}}.sub{{color:var(--t3);font-size:12px;margin-bottom:20px}}
h2{{font-size:15px;color:var(--t2);margin:28px 0 12px;font-weight:600}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:12px}}
.card{{display:block;background:#fff;border:1px solid var(--line);border-radius:10px;padding:14px;text-decoration:none;color:inherit;transition:.15s}}
.card:hover{{border-color:var(--brand);box-shadow:0 4px 14px rgba(22,107,199,.12)}}
.dest{{font-weight:600;font-size:15px}}.code{{font-size:11px;color:var(--t3);margin-left:6px;font-weight:400}}
.price{{color:var(--brand);font-size:26px;font-weight:700;margin:6px 0 2px}}.price small{{font-size:11px;color:var(--t3);font-weight:400;margin-left:4px}}
.meta{{font-size:12px;color:var(--t2)}}.foot{{display:flex;justify-content:space-between;align-items:center;margin-top:8px}}
.down{{color:#00A13B;font-weight:600}}.up{{color:#F53F3F}}.muted{{color:var(--t3)}}
table{{width:100%;border-collapse:collapse;background:#fff;border:1px solid var(--line);border-radius:10px;overflow:hidden;font-size:13px}}
th{{background:var(--brand-50);color:var(--t2);font-weight:600;text-align:left;padding:9px 10px}}td{{padding:8px 10px;border-top:1px solid var(--line)}}
.num{{text-align:right}}a{{color:var(--brand)}}tr:hover td{{background:#FAFBFC}}
@media(max-width:640px){{th:nth-child(4),td:nth-child(4),th:nth-child(7),td:nth-child(7),th:nth-child(8),td:nth-child(8){{display:none}}}}
</style></head><body><div class="wrap">
<h1>✈️ 特价机票雷达</h1>
<div class="sub">更新于 {run_ts}（北京时间） · 出发地 {' / '.join(cfg['origins'])} · 共 {len(priced)} 条有价结果 · 价格为 Google Flights 单人经济舱往返参考价</div>
<h2>各目的地当前最低价</h2>
<div class="grid">{card_html or '<div class="muted">暂无数据</div>'}</div>
<h2>全部航线明细</h2>
<table><thead><tr><th>出发</th><th>目的地</th><th>日期</th><th>类型</th><th class="num">价格</th><th class="num">较上次</th><th class="num">历史最低</th><th>走势</th><th></th></tr></thead>
<tbody>{rows_html}</tbody></table>
</div></body></html>"""
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
