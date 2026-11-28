#!/usr/bin/env python3
"""生成个股盘中监测卡片（dynamic-ui 兼容的自包含 widget HTML）。

用法：python3 monitor/card.py payload.json > card.html
payload 字段见 monitor/demo_payload.json
"""
import json
import sys

TOKENS = """
:root{
  color-scheme:light;
  --surface:#FFFFFF; --surface-muted:#F4F5F7;
  --text:#171717; --text-muted:#52525B;
  --border:rgba(23,23,23,.10);
  --up:#D9302E; --down:#0E9F6E;
  --chart-series-1:#02743B; --chart-series-4:#80C1FF;
  --radius:8px; --radius-card:12px; --radius-full:999px;
  --spacer-4:4px; --spacer-8:8px; --spacer-12:12px; --spacer-16:16px; --spacer-20:20px; --spacer-24:24px;
  --font-sans:"SF Pro Text","PingFang SC",system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
  --font-metric:"Inter","SF Pro Text","PingFang SC",system-ui,-apple-system,sans-serif;
  --weight-regular:400; --weight-medium:500; --weight-strong:600;
  --text-caption:12px/18px; --text-body:14px/20px; --text-title:16px/24px; --text-code:13px/20px;
}
:root[data-widget-theme="dark"]{
  color-scheme:dark;
  --surface:#171717; --surface-muted:#262626;
  --text:#E5E5E5; --text-muted:#A1A1AA;
  --border:rgba(229,229,229,.12);
  --up:#F87454; --down:#32F08C;
  --chart-series-1:#32F08C; --chart-series-4:#64B4FF;
}
.w{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-card);
  padding:var(--spacer-20);color:var(--text);font:var(--weight-regular) var(--text-body) var(--font-sans);width:100%;box-sizing:border-box}
.w .hd{display:flex;justify-content:space-between;align-items:center;gap:var(--spacer-12)}
.w .cap{font:var(--weight-regular) var(--text-caption) var(--font-sans);color:var(--text-muted)}
.w .badge{font:var(--weight-medium) var(--text-caption) var(--font-sans);color:var(--text-muted);
  border:1px solid var(--border);border-radius:var(--radius-full);padding:2px var(--spacer-8);white-space:nowrap}
.w .px{display:flex;align-items:baseline;gap:var(--spacer-8);margin-top:var(--spacer-8)}
.w .px .v{font:var(--weight-strong) var(--text-title) var(--font-metric);font-variant-numeric:tabular-nums}
.w .px .u{font:var(--weight-regular) var(--text-caption) var(--font-sans);color:var(--text-muted)}
.w .px .chg{font:var(--weight-strong) var(--text-caption) var(--font-metric);margin-left:auto}
.up{color:var(--up)} .down{color:var(--down)}
.w .chart{margin:var(--spacer-12) 0 0}
.w .lg{display:flex;gap:var(--spacer-16);justify-content:center;margin:var(--spacer-4) 0 var(--spacer-12);
  font:var(--weight-regular) var(--text-caption) var(--font-sans);color:var(--text-muted)}
.w .lg i{display:inline-block;width:8px;height:8px;border-radius:var(--radius-full);margin-right:var(--spacer-4)}
.w .grid{display:grid;grid-template-columns:1fr 1fr;gap:var(--spacer-12);padding:var(--spacer-12) 0;
  border-top:1px solid var(--border);border-bottom:1px solid var(--border)}
.w .k{font:var(--weight-regular) var(--text-caption) var(--font-sans);color:var(--text-muted)}
.w .kv{font:var(--weight-strong) var(--text-title) var(--font-metric);font-variant-numeric:tabular-nums}
.w .ks{font:var(--weight-regular) var(--text-caption) var(--font-sans);color:var(--text-muted)}
.w .core{margin:var(--spacer-16) 0 var(--spacer-8);font:var(--weight-medium) var(--text-body) var(--font-sans)}
.w .dim{display:grid;grid-template-columns:1fr;gap:var(--spacer-8);margin:var(--spacer-8) 0 var(--spacer-16)}
.w .dim .lab{font:var(--weight-regular) var(--text-caption) var(--font-sans);color:var(--text-muted)}
.w .dim .val{font:var(--weight-regular) var(--text-body) var(--font-sans)}
.w .adv{font:var(--weight-regular) var(--text-body) var(--font-sans)}
.w .adv ul{margin:var(--spacer-4) 0 0;padding-left:var(--spacer-20)}
.w .adv li{margin:var(--spacer-4) 0}
.w .foot{margin-top:var(--spacer-16);font:var(--weight-regular) var(--text-caption) var(--font-sans);color:var(--text-muted)}
"""


def esc(s):
    return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def chart(points, ref=None, ref_label=''):
    if len(points) > 80:
        step = (len(points) - 1) / 79
        points = [points[int(i * step)] for i in range(80)]
    W, H = 720, 250
    padt, padb, padl, padr = 8, 26, 44, 12
    volh = 38
    priceh = H - padt - padb - volh - 10
    prices = [p for _, p, *_ in points]
    lo, hi = min(prices), max(prices)
    if ref:
        lo, hi = min(lo, ref), max(hi, ref)
    span = (hi - lo) or 0.01
    lo -= span * .18
    hi += span * .18

    def x(i):
        return padl + (W - padl - padr) * i / max(len(points) - 1, 1)

    def y(p):
        return padt + priceh * (1 - (p - lo) / (hi - lo))

    out = [f'<svg class="chart" viewBox="0 0 {W} {H}" width="100%" preserveAspectRatio="none" xmlns="http://www.w3.org/2000/svg" role="img">']
    for k in range(4):
        gy = padt + priceh * k / 3
        out.append(f'<line x1="{padl}" y1="{gy:.1f}" x2="{W-padr}" y2="{gy:.1f}" stroke="var(--border)" stroke-width="1" stroke-dasharray="3 4"/>')
        out.append(f'<text x="{padl-6}" y="{gy+4:.1f}" text-anchor="end" font-size="11" fill="var(--text-muted)">{hi-(hi-lo)*k/3:.2f}</text>')
    vols = [pt[2] if len(pt) > 2 else 0 for pt in points]
    mv = max(vols) if vols else 0
    if mv:
        bw = max((W - padl - padr) / len(points) * .55, 1.2)
        base = H - padb
        for i, v in enumerate(vols):
            h = volh * v / mv
            out.append(f'<rect x="{x(i)-bw/2:.1f}" y="{base-h:.1f}" width="{bw:.1f}" height="{h:.1f}" fill="var(--surface-muted)" rx="1"/>')
    if ref:
        ry = y(ref)
        out.append(f'<line x1="{padl}" y1="{ry:.1f}" x2="{W-padr}" y2="{ry:.1f}" stroke="var(--text-muted)" stroke-width="1" stroke-dasharray="5 4"/>')
        if ref_label:
            out.append(f'<text x="{W-padr}" y="{ry-5:.1f}" text-anchor="end" font-size="11" fill="var(--text-muted)">{esc(ref_label)}</text>')
    pts = ' '.join(f'{x(i):.1f},{y(pt[1]):.1f}' for i, pt in enumerate(points))
    out.append(f'<polyline points="{pts}" fill="none" stroke="var(--chart-series-4)" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>')
    step = max(len(points) // 36, 1)
    for i, pt in enumerate(points):
        if i % step == 0 or i == len(points) - 1:
            out.append(f'<circle cx="{x(i):.1f}" cy="{y(pt[1]):.1f}" r="2.2" fill="var(--chart-series-4)"/>')
    n = len(points)
    picks = sorted({0, int(n * .25), int(n * .5), int(n * .75), n - 1})
    for idx in picks:
        out.append(f'<text x="{x(idx):.0f}" y="{H-6}" text-anchor="middle" font-size="11" fill="var(--text-muted)">{points[idx][0][:5]}</text>')
    out.append('</svg>')
    return ''.join(out)


def render(p):
    chg = float(p['chg_pct'])
    cls = 'up' if chg >= 0 else 'down'
    sign = '+' if chg >= 0 else ''

    legend = ''
    if p['chart'].get('ref'):
        legend = ('<div class="lg"><span><i style="background:var(--chart-series-4)"></i>分时价格</span>'
                  f'<span><i style="background:var(--text-muted)"></i>{esc(p["chart"].get("ref_label","参考线"))}</span></div>')

    kpis = ''.join(
        f'<div><div class="k">{esc(k["label"])}</div>'
        f'<div class="kv">{esc(k["value"])}</div>'
        f'<div class="ks">{esc(k.get("sub",""))}</div></div>'
        for k in p.get('kpis', []))

    dims = ''.join(
        f'<div><div class="lab">{esc(d["k"])}</div><div class="val">{esc(d["v"])}</div></div>'
        for d in p.get('dims', []))

    advice = ''.join(f'<li><b>{esc(a["k"])}：</b>{esc(a["v"])}</li>' for a in p.get('advice', []))

    hold = ''
    if p.get('hold'):
        rows = ''.join(
            f'<div><div class="lab">{esc(k)}</div><div class="val">{esc(v)}</div></div>'
            for k, v in p['hold'].items())
        hold = ('<div class="grid" style="grid-template-columns:1fr 1fr;border-top:0;padding-top:0">'
                f'{rows}</div>')

    return f'''<style>{TOKENS}</style>
<div class="w" data-dynamic-ui-widget data-template="stock-intraday-card">
  <div class="hd">
    <span class="cap">{esc(p['name'])} {esc(p['code'])} · {esc(p['time_label'])}</span>
    <span class="badge">{esc(p.get('tag','盘中快照'))}</span>
  </div>
  <div class="px">
    <span class="v">{esc(p['price'])}</span><span class="u">元</span>
    <span class="chg {cls}">{sign}{p['chg_pct']}%</span>
  </div>
  {chart(p['chart']['points'], p['chart'].get('ref'), p['chart'].get('ref_label',''))}
  {legend}
  <div class="grid">{kpis}</div>
  {hold}
  <div class="core">核心研判：{esc(p['core'])}</div>
  <div class="dim">{dims}</div>
  <div class="adv"><b>操作建议</b><ul>{advice}</ul></div>
  <div class="foot">{esc(p.get('foot',''))}</div>
</div>'''


if __name__ == '__main__':
    payload = json.load(open(sys.argv[1], encoding='utf-8')) if len(sys.argv) > 1 else json.load(sys.stdin)
    print(render(payload))
