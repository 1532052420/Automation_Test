/**
 * 压测报告交互图表（离线可用）：坐标轴、网格、悬停 Tooltip、高亮点。
 */
(function (global) {
  "use strict";

  function fmtNum(v, digits) {
    if (v == null || isNaN(v)) return "-";
    digits = digits == null ? 2 : digits;
    if (Math.abs(v) >= 1000) return (v / 1000).toFixed(1) + "k";
    return Number(v).toFixed(digits);
  }

  function niceMax(val) {
    if (val <= 0) return 1;
    var pow = Math.pow(10, Math.floor(Math.log10(val)));
    var n = val / pow;
    var nice = n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10;
    return nice * pow;
  }

  function InteractiveChart(canvas, options) {
    this.canvas = canvas;
    this.labels = options.labels || [];
    this.data = options.data || [];
    this.type = options.type || "line";
    this.color = options.color || "#8ab4f8";
    this.unit = options.unit || "";
    this.title = options.title || "";
    this.fill = options.fill !== false;
    this.wrap = canvas.closest(".chart-wrap");
    this.tooltip = this.wrap ? this.wrap.querySelector(".chart-tooltip") : null;
    this.legendEl = options.legendEl || null;
    this.points = [];
    this.hoverIndex = -1;
    this.pad = { top: 16, right: 16, bottom: 32, left: 48 };
    this._onMove = this._onMove.bind(this);
    this._onLeave = this._onLeave.bind(this);
    canvas.addEventListener("mousemove", this._onMove);
    canvas.addEventListener("mouseleave", this._onLeave);
    window.addEventListener("resize", this._resize.bind(this));
    this._resize();
    this.render();
    this._updateLegend();
  }

  InteractiveChart.prototype._resize = function () {
    var rect = this.canvas.parentElement.getBoundingClientRect();
    var w = Math.max(rect.width || 400, 280);
    var h = 200;
    var dpr = window.devicePixelRatio || 1;
    this.canvas.style.width = w + "px";
    this.canvas.style.height = h + "px";
    this.canvas.width = Math.floor(w * dpr);
    this.canvas.height = Math.floor(h * dpr);
    this.w = w;
    this.h = h;
    this.dpr = dpr;
    this.render();
  };

  InteractiveChart.prototype._plot = function () {
    var p = this.pad;
    return {
      x0: p.left,
      y0: p.top,
      w: this.w - p.left - p.right,
      h: this.h - p.top - p.bottom,
    };
  };

  InteractiveChart.prototype._valueAt = function (i) {
    return this.data[i] != null ? this.data[i] : 0;
  };

  InteractiveChart.prototype._maxY = function () {
    var m = Math.max.apply(null, this.data.concat([0]));
    return niceMax(m * 1.1);
  };

  InteractiveChart.prototype._xy = function (i, plot, maxY) {
    var n = this.data.length;
    var x =
      plot.x0 + (n <= 1 ? plot.w / 2 : (plot.w * i) / (n - 1));
    var y = plot.y0 + plot.h - (this._valueAt(i) / maxY) * plot.h;
    return { x: x, y: y, v: this._valueAt(i) };
  };

  InteractiveChart.prototype.render = function () {
    var ctx = this.canvas.getContext("2d");
    if (!ctx || !this.data.length) return;
    ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    ctx.clearRect(0, 0, this.w, this.h);

    var plot = this._plot();
    var maxY = this._maxY();
    this.points = [];
    for (var i = 0; i < this.data.length; i++) {
      this.points.push(this._xy(i, plot, maxY));
    }

    this._drawGrid(ctx, plot, maxY);
    this._drawSeries(ctx, plot, maxY);
    if (this.hoverIndex >= 0) this._drawHover(ctx, plot);
  };

  InteractiveChart.prototype._drawGrid = function (ctx, plot, maxY) {
    var ticks = 5;
    ctx.strokeStyle = "#3c4043";
    ctx.fillStyle = "#9aa0a6";
    ctx.font = "11px Segoe UI, Microsoft YaHei, sans-serif";
    ctx.lineWidth = 1;

    for (var t = 0; t <= ticks; t++) {
      var ratio = t / ticks;
      var y = plot.y0 + plot.h - ratio * plot.h;
      var val = maxY * ratio;
      ctx.beginPath();
      ctx.moveTo(plot.x0, y);
      ctx.lineTo(plot.x0 + plot.w, y);
      ctx.stroke();
      ctx.textAlign = "right";
      ctx.textBaseline = "middle";
      ctx.fillText(fmtNum(val, val < 10 ? 2 : 1), plot.x0 - 6, y);
    }

    var n = this.labels.length;
    var step = Math.max(1, Math.ceil(n / 8));
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    for (var i = 0; i < n; i += step) {
      var x =
        plot.x0 + (n <= 1 ? plot.w / 2 : (plot.w * i) / (n - 1));
      ctx.fillText(String(this.labels[i]) + "s", x, plot.y0 + plot.h + 6);
    }
    ctx.fillStyle = "#6b7280";
    ctx.font = "10px Segoe UI, Microsoft YaHei, sans-serif";
    ctx.textAlign = "left";
    ctx.fillText("压测秒数 →", plot.x0, plot.y0 + plot.h + 20);
  };

  InteractiveChart.prototype._drawSeries = function (ctx, plot, maxY) {
    var pts = this.points;
    if (this.type === "line") {
      if (this.fill && pts.length > 1) {
        ctx.beginPath();
        ctx.moveTo(pts[0].x, plot.y0 + plot.h);
        for (var i = 0; i < pts.length; i++) ctx.lineTo(pts[i].x, pts[i].y);
        ctx.lineTo(pts[pts.length - 1].x, plot.y0 + plot.h);
        ctx.closePath();
        ctx.fillStyle = this._hexAlpha(this.color, 0.15);
        ctx.fill();
      }
      ctx.beginPath();
      ctx.strokeStyle = this.color;
      ctx.lineWidth = 2;
      ctx.lineJoin = "round";
      for (var j = 0; j < pts.length; j++) {
        if (j === 0) ctx.moveTo(pts[j].x, pts[j].y);
        else ctx.lineTo(pts[j].x, pts[j].y);
      }
      ctx.stroke();
      for (var k = 0; k < pts.length; k++) {
        ctx.beginPath();
        ctx.fillStyle = k === this.hoverIndex ? "#fff" : this.color;
        ctx.strokeStyle = this.color;
        ctx.lineWidth = k === this.hoverIndex ? 2 : 1;
        ctx.arc(pts[k].x, pts[k].y, k === this.hoverIndex ? 5 : 3, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();
      }
    } else {
      var barW = (plot.w / pts.length) * 0.65;
      for (var b = 0; b < pts.length; b++) {
        var bh = plot.y0 + plot.h - pts[b].y;
        var bx = pts[b].x - barW / 2;
        ctx.fillStyle =
          b === this.hoverIndex
            ? this._hexAlpha(this.color, 0.95)
            : this._hexAlpha(this.color, 0.65);
        ctx.fillRect(bx, pts[b].y, barW, bh);
        if (b === this.hoverIndex && pts[b].v > 0) {
          ctx.fillStyle = "#e8eaed";
          ctx.font = "bold 11px Segoe UI, Microsoft YaHei, sans-serif";
          ctx.textAlign = "center";
          ctx.textBaseline = "bottom";
          ctx.fillText(fmtNum(pts[b].v, 2) + this.unit, pts[b].x, pts[b].y - 4);
        }
      }
    }
  };

  InteractiveChart.prototype._drawHover = function (ctx, plot) {
    var i = this.hoverIndex;
    if (i < 0 || !this.points[i]) return;
    var p = this.points[i];
    ctx.strokeStyle = "rgba(138, 180, 248, 0.6)";
    ctx.lineWidth = 1;
    ctx.setLineDash([4, 4]);
    ctx.beginPath();
    ctx.moveTo(p.x, plot.y0);
    ctx.lineTo(p.x, plot.y0 + plot.h);
    ctx.stroke();
    ctx.setLineDash([]);
  };

  InteractiveChart.prototype._hexAlpha = function (hex, a) {
    if (hex.indexOf("rgba") === 0) return hex;
    var h = hex.replace("#", "");
    if (h.length === 3)
      h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
    var r = parseInt(h.slice(0, 2), 16);
    var g = parseInt(h.slice(2, 4), 16);
    var b = parseInt(h.slice(4, 6), 16);
    return "rgba(" + r + "," + g + "," + b + "," + a + ")";
  };

  InteractiveChart.prototype._nearest = function (mx) {
    if (!this.points.length) return -1;
    var best = 0;
    var dist = Math.abs(this.points[0].x - mx);
    for (var i = 1; i < this.points.length; i++) {
      var d = Math.abs(this.points[i].x - mx);
      if (d < dist) {
        dist = d;
        best = i;
      }
    }
    return best;
  };

  InteractiveChart.prototype._onMove = function (e) {
    var rect = this.canvas.getBoundingClientRect();
    var mx = e.clientX - rect.left;
    var idx = this._nearest(mx);
    if (idx !== this.hoverIndex) {
      this.hoverIndex = idx;
      this.render();
    }
    this._showTooltip(e, idx);
  };

  InteractiveChart.prototype._onLeave = function () {
    this.hoverIndex = -1;
    this.render();
    if (this.tooltip) this.tooltip.style.display = "none";
  };

  InteractiveChart.prototype._showTooltip = function (e, idx) {
    if (!this.tooltip || idx < 0) return;
    var p = this.points[idx];
    var sec = this.labels[idx] != null ? this.labels[idx] : idx;
    var html =
      '<div class="tt-title">' +
      this.title +
      "</div>" +
      '<div class="tt-row"><span>时刻</span><b>第 ' +
      sec +
      " 秒</b></div>" +
      '<div class="tt-row"><span>数值</span><b>' +
      fmtNum(p.v, 2) +
      this.unit +
      "</b></div>";
    this.tooltip.innerHTML = html;
    this.tooltip.style.display = "block";
    var wrapRect = this.wrap.getBoundingClientRect();
    var left = e.clientX - wrapRect.left + 12;
    var top = e.clientY - wrapRect.top - 10;
    if (left + 160 > wrapRect.width) left = left - 180;
    if (top < 0) top = 8;
    this.tooltip.style.left = left + "px";
    this.tooltip.style.top = top + "px";
  };

  InteractiveChart.prototype._updateLegend = function () {
    if (!this.legendEl || !this.data.length) return;
    var sum = 0;
    var min = Infinity;
    var max = -Infinity;
    for (var i = 0; i < this.data.length; i++) {
      var v = this._valueAt(i);
      sum += v;
      if (v < min) min = v;
      if (v > max) max = v;
    }
    var avg = sum / this.data.length;
    this.legendEl.innerHTML =
      '<span>最小 <b>' +
      fmtNum(min, 2) +
      this.unit +
      "</b></span>" +
      '<span>平均 <b>' +
      fmtNum(avg, 2) +
      this.unit +
      "</b></span>" +
      '<span>最大 <b>' +
      fmtNum(max, 2) +
      this.unit +
      "</b></span>" +
      '<span class="hint">悬停图表查看各秒明细</span>';
  };

  global.initLoadTestCharts = function (payload) {
    var labels = payload.labels || [];
    var charts = [
      {
        id: "chartTps",
        legend: "legendTps",
        data: payload.tps || [],
        type: "line",
        color: "#8ab4f8",
        unit: " req/s",
        title: "TPS",
      },
      {
        id: "chartRt",
        legend: "legendRt",
        data: payload.rt || [],
        type: "line",
        color: "#34a853",
        unit: " ms",
        title: "响应耗时",
      },
      {
        id: "chartErr",
        legend: "legendErr",
        data: payload.err || [],
        type: "bar",
        color: "#ea4335",
        unit: "%",
        title: "错误率",
        fill: false,
      },
    ];
    charts.forEach(function (cfg) {
      var canvas = document.getElementById(cfg.id);
      if (!canvas || !cfg.data.length) return;
      new InteractiveChart(canvas, {
        labels: labels,
        data: cfg.data,
        type: cfg.type,
        color: cfg.color,
        unit: cfg.unit,
        title: cfg.title,
        fill: cfg.fill,
        legendEl: document.getElementById(cfg.legend),
      });
    });
  };
})(window);
