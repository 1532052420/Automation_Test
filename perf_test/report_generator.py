# -*- coding: utf-8 -*-
"生成HTML测试报告"

from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from metrics_collector import AggregateMetrics, MetricsCollector, RequestSample

# 详情 JSON 中单条错误信息上限，避免超大脚本块导致浏览器卡死
_DETAIL_ERR_MAX = 200
_CHART_JS_PATH = Path(__file__).resolve().parent / "chart_interactive.js"


def _load_chart_js() -> str:
    js = _CHART_JS_PATH.read_text(encoding="utf-8")
    return js.replace("</script>", r"<\/script>")


def generate_html_report(
    collector: MetricsCollector,
    config: dict[str, Any],
    output_path: str | Path,
) -> Path:
    out = Path(output_path)
    if not out.is_absolute():
        out = Path(__file__).resolve().parent / out
    out.parent.mkdir(parents=True, exist_ok=True)

    agg = collector.get_aggregate()
    samples = collector.get_samples()
    time_series = collector.build_time_series()

    chart_payload = {
        "labels": [str(p["second"]) for p in time_series],
        "tps": [p["tps"] for p in time_series],
        "rt": [p["avg_ms"] for p in time_series],
        "err": [p["error_rate"] for p in time_series],
    }
    samples_detail = _build_samples_detail(samples)

    data_path = out.with_suffix(".data.json")
    data_path.write_text(
        json.dumps(
            {"chart": chart_payload, "samples": samples_detail},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    # ensure_ascii=True 避免 JSON 中出现字面量 </script> 破坏 HTML
    html_content = _build_html(
        config=config,
        agg=agg,
        samples=samples,
        chart_json=json.dumps(chart_payload, ensure_ascii=True),
        samples_json=json.dumps(samples_detail, ensure_ascii=True),
    )
    out.write_text(html_content, encoding="utf-8")
    return out


def _build_samples_detail(samples: list[RequestSample]) -> dict[str, dict[str, Any]]:
    detail: dict[str, dict[str, Any]] = {}
    for i, s in enumerate(samples, 1):
        detail[str(i)] = {
            "request_headers": _truncate(s.request_headers, 800),
            "request_body": _truncate(s.request_body, 800),
            "response_body": _truncate(s.response_body, 800),
            "error_message": _truncate(s.error_message, _DETAIL_ERR_MAX),
            "response_length": s.response_length,
        }
    return detail


def _build_html(
    *,
    config: dict[str, Any],
    agg: AggregateMetrics,
    samples: list[RequestSample],
    chart_json: str,
    samples_json: str,
) -> str:
    mode_label = "阶梯递增加压" if config.get("mode") == "staircase" else "瞬时脉冲峰值"
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    config_path = html.escape(str(config.get("_config_path", "")).replace("\\", "/"))
    stop_label = "手动中断 (Ctrl+C)" if config.get("_interrupted") else "正常结束"

    rows = []
    for i, s in enumerate(samples, 1):
        status_cls = "ok" if s.success else "fail"
        ts_str = datetime.fromtimestamp(s.timestamp).strftime("%H:%M:%S.%f")[:-3]
        resp_preview = s.response_body or ("(未采集)" if not config.get("report", {}).get("capture_response_body", False) else "(空)")
        rows.append(
            f"""<tr class="{status_cls}">
<td>{i}</td>
<td>{html.escape(ts_str)}</td>
<td>{html.escape(s.method)}</td>
<td class="url" title="{html.escape(s.url)}">{html.escape(_truncate(s.url, 60))}</td>
<td>{s.status_code if s.status_code is not None else "-"}</td>
<td>{s.response_time_ms:.0f}</td>
<td>{html.escape("成功" if s.success else "失败")}</td>
<td class="resp" title="{html.escape(s.response_body or '')}">{html.escape(_truncate(resp_preview, 80))}</td>
<td class="err">{html.escape(_truncate(s.error_message, 50))}</td>
<td><button type="button" class="btn-detail" data-sample="{i}">详情</button></td>
</tr>"""
        )

    tbody = "".join(rows) if rows else '<tr><td colspan="10">无采样数据</td></tr>'

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>HTTP 压测报告 - {html.escape(mode_label)}</title>
<style>
:root {{ --bg: #1a1d23; --card: #252830; --text: #e8eaed; --muted: #9aa0a6;
  --ok: #34a853; --fail: #ea4335; --accent: #8ab4f8; --border: #3c4043; }}
* {{ box-sizing: border-box; }}
body {{ font-family: "Segoe UI", "Microsoft YaHei", sans-serif; margin: 0; padding: 24px;
  background: var(--bg); color: var(--text); font-size: 14px; }}
h1 {{ font-size: 1.5rem; margin: 0 0 8px; }}
.meta {{ color: var(--muted); margin-bottom: 24px; font-size: 13px; line-height: 1.6; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin-bottom: 24px; }}
.card {{ background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 16px; }}
.card .label {{ color: var(--muted); font-size: 12px; }}
.card .value {{ font-size: 1.6rem; font-weight: 600; margin-top: 4px; color: var(--accent); }}
.charts {{ display: grid; grid-template-columns: 1fr; gap: 20px; margin-bottom: 28px; }}
@media (min-width: 900px) {{ .charts {{ grid-template-columns: 1fr 1fr; }} .charts .wide {{ grid-column: 1 / -1; }} }}
.chart-box {{ background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 16px; }}
.chart-box h3 {{ margin: 0 0 8px; font-size: 14px; font-weight: 500; }}
.chart-wrap {{ position: relative; width: 100%; cursor: crosshair; }}
.chart-wrap canvas {{ display: block; width: 100%; }}
.chart-tooltip {{
  display: none; position: absolute; z-index: 20; min-width: 140px; padding: 10px 12px;
  background: #1e2229; border: 1px solid var(--accent); border-radius: 8px;
  box-shadow: 0 8px 24px rgba(0,0,0,.45); pointer-events: none; font-size: 12px;
}}
.chart-tooltip .tt-title {{ color: var(--accent); font-weight: 600; margin-bottom: 6px; font-size: 13px; }}
.chart-tooltip .tt-row {{ display: flex; justify-content: space-between; gap: 16px; margin-top: 4px; color: var(--muted); }}
.chart-tooltip .tt-row b {{ color: var(--text); font-weight: 600; }}
.chart-legend {{
  display: flex; flex-wrap: wrap; gap: 16px; margin-top: 10px; padding-top: 10px;
  border-top: 1px solid var(--border); font-size: 12px; color: var(--muted);
}}
.chart-legend b {{ color: var(--text); margin-left: 4px; }}
.chart-legend .hint {{ color: #6b7280; font-style: italic; margin-left: auto; }}
.tree-panel {{ background: var(--card); border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }}
.tree-panel h3 {{ margin: 0; padding: 12px 16px; border-bottom: 1px solid var(--border); font-size: 14px; }}
.toolbar {{ padding: 8px 16px; border-bottom: 1px solid var(--border); display: flex; gap: 12px; flex-wrap: wrap; align-items: center; }}
.toolbar input, .toolbar select {{ background: var(--bg); border: 1px solid var(--border); color: var(--text);
  padding: 6px 10px; border-radius: 4px; }}
.table-wrap {{ max-height: 480px; overflow: auto; }}
table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
th, td {{ padding: 8px 10px; text-align: left; border-bottom: 1px solid var(--border); }}
th {{ position: sticky; top: 0; background: #2d3139; z-index: 1; }}
tr.ok td:nth-child(7) {{ color: var(--ok); }}
tr.fail td:nth-child(7) {{ color: var(--fail); }}
tr.fail {{ background: rgba(234, 67, 53, 0.08); }}
.url {{ max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
.resp {{ max-width: 320px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #c4c7c5; font-size: 11px; }}
.btn-detail {{ background: var(--accent); color: #1a1d23; border: none; padding: 4px 10px;
  border-radius: 4px; cursor: pointer; font-size: 11px; }}
.modal {{ display: none; position: fixed; inset: 0; background: rgba(0,0,0,.6); z-index: 100;
  align-items: center; justify-content: center; padding: 24px; }}
.modal.open {{ display: flex; }}
.modal-inner {{ background: var(--card); border-radius: 8px; max-width: 720px; width: 100%;
  max-height: 85vh; overflow: auto; padding: 20px; border: 1px solid var(--border); }}
.modal-inner h4 {{ margin: 12px 0 6px; font-size: 13px; color: var(--muted); }}
.modal-inner pre {{ background: var(--bg); padding: 12px; border-radius: 6px; overflow: auto;
  font-size: 11px; white-space: pre-wrap; word-break: break-all; }}
.modal-close {{ float: right; cursor: pointer; color: var(--muted); }}
</style>
</head>
<body>
<h1>HTTP 接口性能压测报告</h1>
<p class="meta">
  模式：{html.escape(mode_label)} | 结束方式：{html.escape(stop_label)} | 生成时间：{generated_at}<br/>
  配置：{config_path}<br/>
  <span style="color:#fbbf24">请用 Chrome / Edge 浏览器打开本文件；勿用 IDE 内置预览大文件。</span>
</p>

<div class="grid">
  <div class="card"><div class="label">总请求数</div><div class="value">{agg.total_requests}</div></div>
  <div class="card"><div class="label">TPS（平均）</div><div class="value">{agg.tps:.2f}</div></div>
  <div class="card"><div class="label">平均响应 (ms)</div><div class="value">{agg.avg_response_time_ms:.0f}</div></div>
  <div class="card"><div class="label">P90 (ms)</div><div class="value">{agg.percentile(90):.0f}</div></div>
  <div class="card"><div class="label">P95 (ms)</div><div class="value">{agg.percentile(95):.0f}</div></div>
  <div class="card"><div class="label">最小 / 最大 (ms)</div><div class="value">{agg.min_response_time_ms:.0f} / {agg.max_response_time_ms:.0f}</div></div>
  <div class="card"><div class="label">成功 / 失败</div><div class="value">{agg.success_count} / {agg.fail_count}</div></div>
  <div class="card"><div class="label">错误率 (%)</div><div class="value">{agg.error_rate:.2f}</div></div>
  <div class="card"><div class="label">压测时长 (s)</div><div class="value">{agg.duration_sec:.1f}</div></div>
</div>

<div class="charts">
  <div class="chart-box wide">
    <h3>TPS 趋势（每秒）</h3>
    <div class="chart-wrap"><canvas id="chartTps"></canvas><div class="chart-tooltip"></div></div>
    <div class="chart-legend" id="legendTps"></div>
  </div>
  <div class="chart-box">
    <h3>平均响应耗时</h3>
    <div class="chart-wrap"><canvas id="chartRt"></canvas><div class="chart-tooltip"></div></div>
    <div class="chart-legend" id="legendRt"></div>
  </div>
  <div class="chart-box">
    <h3>错误率</h3>
    <div class="chart-wrap"><canvas id="chartErr"></canvas><div class="chart-tooltip"></div></div>
    <div class="chart-legend" id="legendErr"></div>
  </div>
</div>

<div class="tree-panel">
  <h3>查看结果树（类 JMeter View Results Tree）</h3>
  <div class="toolbar">
    <label>筛选 <select id="filterStatus">
      <option value="all">全部</option>
      <option value="ok">仅成功</option>
      <option value="fail">仅失败</option>
    </select></label>
    <label>搜索 URL <input type="text" id="searchUrl" placeholder="关键字"/></label>
    <span style="color:var(--muted)">共 {len(samples)} 条</span>
  </div>
  <div class="table-wrap">
    <table id="resultsTable">
      <thead>
        <tr>
          <th>#</th><th>时间</th><th>方法</th><th>URL</th><th>状态码</th>
          <th>耗时(ms)</th><th>结果</th><th>响应体摘要</th><th>错误信息</th><th>操作</th>
        </tr>
      </thead>
      <tbody>{tbody}</tbody>
    </table>
  </div>
</div>

<div class="modal" id="detailModal">
  <div class="modal-inner">
    <span class="modal-close" id="modalClose">&#10005; 关闭</span>
    <h3>请求/响应详情</h3>
    <h4>请求头</h4><pre id="detailHeaders"></pre>
    <h4>请求体</h4><pre id="detailReqBody"></pre>
    <h4>响应体摘要</h4><pre id="detailRespBody"></pre>
    <h4>错误信息</h4><pre id="detailError"></pre>
  </div>
</div>

<script type="application/json" id="chart-data">{chart_json}</script>
<script type="application/json" id="sample-data">{samples_json}</script>
<script>
{_load_chart_js()}
</script>
<script>
(function() {{
  function parseJson(id) {{
    var el = document.getElementById(id);
    if (!el) return {{}};
    try {{ return JSON.parse(el.textContent || '{{}}'); }}
    catch (e) {{ console.error('JSON parse failed:', id, e); return {{}}; }}
  }}
  var chartPayload = parseJson('chart-data');
  var sampleDetails = parseJson('sample-data');
  if (typeof initLoadTestCharts === 'function') initLoadTestCharts(chartPayload);

  var modal = document.getElementById('detailModal');
  document.querySelectorAll('.btn-detail').forEach(function(btn) {{
    btn.addEventListener('click', function() {{
      var d = sampleDetails[btn.getAttribute('data-sample')] || {{}};
      document.getElementById('detailHeaders').textContent = d.request_headers || '';
      document.getElementById('detailReqBody').textContent = d.request_body || '';
      document.getElementById('detailRespBody').textContent = d.response_body || '(未采集)';
      document.getElementById('detailError').textContent = d.error_message || '-';
      modal.classList.add('open');
    }});
  }});
  document.getElementById('modalClose').onclick = function() {{ modal.classList.remove('open'); }};
  modal.onclick = function(e) {{ if (e.target === modal) modal.classList.remove('open'); }};

  function applyFilter() {{
    var st = document.getElementById('filterStatus').value;
    var q = (document.getElementById('searchUrl').value || '').toLowerCase();
    document.querySelectorAll('#resultsTable tbody tr').forEach(function(tr) {{
      var ok = tr.classList.contains('ok');
      var fail = tr.classList.contains('fail');
      var show = true;
      if (st === 'ok') show = ok;
      if (st === 'fail') show = fail;
      var url = (tr.querySelector('.url') && tr.querySelector('.url').textContent || '').toLowerCase();
      if (q && url.indexOf(q) === -1) show = false;
      tr.style.display = show ? '' : 'none';
    }});
  }}
  document.getElementById('filterStatus').onchange = applyFilter;
  document.getElementById('searchUrl').oninput = applyFilter;
}})();
</script>
</body>
</html>"""


def _truncate(s: str, n: int) -> str:
    s = s or ""
    return s if len(s) <= n else s[: n - 3] + "..."
