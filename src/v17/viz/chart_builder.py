"""Standalone TradingView Lightweight Charts HTML Generator (Fixed Overlay & Precision Positioning).

Renders continuous candlestick charts with:
- Shaded Fair Value Gap (FVG) boxes (active until mitigated)
- Order Block (OB) zones (active until invalidated)
- Liquidity levels & sweep markers (Asia H/L, PDH/PDL)
- Killzone session shading (London 03:00-04:00 NY, NY AM 10:00-11:00 NY)
- Exact trade execution overlays (Entry, SL, TP, Exit R)
- "Jump to Trade" dropdown navigation
- Layer toggles (show/hide FVGs, OBs, Levels, Sessions, Trades)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{TITLE}}</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            background-color: #0e1117;
            color: #d1d4dc;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            overflow: hidden;
            display: flex;
            flex-direction: column;
            height: 100vh;
        }
        #header-bar {
            background-color: #171b26;
            border-bottom: 1px solid #2a2e39;
            padding: 8px 16px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            font-size: 13px;
            flex-shrink: 0;
            z-index: 100;
        }
        .header-section {
            display: flex;
            align-items: center;
            gap: 14px;
        }
        .badge {
            background-color: #2962ff;
            color: #fff;
            padding: 3px 8px;
            border-radius: 4px;
            font-weight: 600;
            font-size: 11px;
            letter-spacing: 0.5px;
        }
        .badge-ict {
            background-color: #6200ea;
        }
        select, button {
            background-color: #2a2e39;
            color: #f0f3fa;
            border: 1px solid #363c4e;
            padding: 5px 10px;
            border-radius: 4px;
            font-size: 12px;
            outline: none;
            cursor: pointer;
        }
        select:hover, button:hover {
            border-color: #2962ff;
        }
        .toggle-group {
            display: flex;
            align-items: center;
            gap: 12px;
            font-size: 12px;
        }
        .toggle-label {
            display: flex;
            align-items: center;
            gap: 4px;
            cursor: pointer;
            user-select: none;
        }
        .toggle-label input {
            cursor: pointer;
        }
        #chart-wrapper {
            position: relative;
            flex: 1;
            width: 100%;
            height: 100%;
        }
        #chart-container {
            width: 100%;
            height: 100%;
        }
        #overlay-canvas {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            pointer-events: none;
            z-index: 15; /* Sits directly ON TOP of chart canvas */
        }
        #info-panel {
            position: absolute;
            top: 16px;
            left: 16px;
            background: rgba(23, 27, 38, 0.92);
            border: 1px solid #2a2e39;
            border-radius: 6px;
            padding: 10px 14px;
            font-size: 12px;
            line-height: 1.5;
            z-index: 50;
            pointer-events: none;
            backdrop-filter: blur(4px);
        }
        .metric-val {
            font-weight: 600;
        }
        .metric-win { color: #26a69a; }
        .metric-loss { color: #ef5350; }
        .fvg-bull-legend { color: #26a69a; }
        .fvg-bear-legend { color: #ef5350; }
        .ob-legend { color: #2196f3; }
        .kz-legend { color: #ffb300; }
    </style>
    <!-- Standalone TradingView Lightweight Charts 4.2 -->
    <script src="https://unpkg.com/lightweight-charts@4.2.0/dist/lightweight-charts.standalone.production.js"></script>
</head>
<body>

    <div id="header-bar">
        <div class="header-section">
            <span class="badge badge-ict">ICT 20+ YRS VISUALIZER</span>
            <span class="badge">{{SYMBOL}}</span>
            <strong style="color: #f0f3fa;">{{TITLE}}</strong>
            <span style="color: #787b86;">|</span>
            <label for="trade-select" style="color: #787b86;">Jump to Trade:</label>
            <select id="trade-select" onchange="jumpToSelectedTrade()">
                <option value="">-- Select FTMO Trade ({{NUM_TRADES}} Total) --</option>
            </select>
        </div>

        <div class="header-section toggle-group">
            <label class="toggle-label"><input type="checkbox" id="chk-fvg" checked onchange="redrawOverlay()"> <span class="fvg-bull-legend">■</span> FVGs</label>
            <label class="toggle-label"><input type="checkbox" id="chk-ob" checked onchange="redrawOverlay()"> <span class="ob-legend">■</span> Order Blocks</label>
            <label class="toggle-label"><input type="checkbox" id="chk-levels" checked onchange="redrawOverlay()"> ━ Sweeps/Levels</label>
            <label class="toggle-label"><input type="checkbox" id="chk-kz" checked onchange="redrawOverlay()"> <span class="kz-legend">■</span> Killzones</label>
            <label class="toggle-label"><input type="checkbox" id="chk-trades" checked onchange="toggleTrades()"> 🎯 Trades</label>
            <button onclick="resetView()">Reset Fit</button>
        </div>
    </div>

    <div id="chart-wrapper">
        <div id="chart-container"></div>
        <canvas id="overlay-canvas"></canvas>
        <div id="info-panel">
            <div style="font-weight: 700; color: #fff; margin-bottom: 4px;">{{SYMBOL}} • Continuous M5 Market Structure</div>
            <div>Candles: <span class="metric-val" id="cand-count">0</span></div>
            <div>Active FVGs: <span class="metric-val" id="fvg-count">0</span> | Order Blocks: <span class="metric-val" id="ob-count">0</span></div>
            <div id="trade-hud" style="margin-top: 6px; padding-top: 6px; border-top: 1px solid #363c4e; display: none;">
                <div style="font-weight: 600; color: #ffb300;" id="hud-trade-title">Trade Info</div>
                <div>Entry: <span id="hud-entry">-</span> | SL: <span id="hud-sl">-</span> | TP: <span id="hud-tp">-</span></div>
                <div>Outcome: <span id="hud-outcome" class="metric-val">-</span></div>
            </div>
        </div>
    </div>

    <script>
        const candlesData = {{CANDLES_JSON}};
        const fvgsData = {{FVGS_JSON}};
        const obsData = {{OBS_JSON}};
        const levelsData = {{LEVELS_JSON}};
        const sessionsData = {{SESSIONS_JSON}};
        const tradesData = {{TRADES_JSON}};

        document.getElementById('cand-count').textContent = candlesData.length;
        document.getElementById('fvg-count').textContent = fvgsData.length;
        document.getElementById('ob-count').textContent = obsData.length;

        // Build Fast Timestamp-to-Logical Index Lookup Map
        const timeToIdx = new Map();
        candlesData.forEach((c, idx) => {
            timeToIdx.set(c.time, idx);
        });

        // Function to find nearest logical index if timestamp is between bars
        function getLogicalIndex(t) {
            if (timeToIdx.has(t)) return timeToIdx.get(t);
            // Binary search nearest
            let lo = 0, hi = candlesData.length - 1;
            while (lo <= hi) {
                const mid = (lo + hi) >> 1;
                if (candlesData[mid].time < t) lo = mid + 1;
                else hi = mid - 1;
            }
            return Math.min(Math.max(lo, 0), candlesData.length - 1);
        }

        const container = document.getElementById('chart-container');
        const canvas = document.getElementById('overlay-canvas');
        const ctx = canvas.getContext('2d');

        // Create Chart
        const chart = LightweightCharts.createChart(container, {
            layout: {
                background: { color: '#0e1117' },
                textColor: '#9ea2ad',
                fontSize: 12,
            },
            grid: {
                vertLines: { color: 'rgba(42, 46, 57, 0.4)' },
                horzLines: { color: 'rgba(42, 46, 57, 0.4)' },
            },
            crosshair: {
                mode: LightweightCharts.CrosshairMode.Normal,
            },
            rightPriceScale: {
                borderColor: '#2a2e39',
                scaleMargins: { top: 0.1, bottom: 0.1 },
            },
            timeScale: {
                borderColor: '#2a2e39',
                timeVisible: true,
                secondsVisible: false,
            },
        });

        // Add Candlestick Series
        const candlestickSeries = chart.addCandlestickSeries({
            upColor: '#26a69a',
            downColor: '#ef5350',
            borderVisible: false,
            wickUpColor: '#26a69a',
            wickDownColor: '#ef5350',
        });

        candlestickSeries.setData(candlesData);

        // Populate Trade Select
        const tradeSelect = document.getElementById('trade-select');
        tradesData.forEach((t, idx) => {
            const opt = document.createElement('option');
            opt.value = idx;
            const rSign = t.r >= 0 ? '+' : '';
            opt.textContent = `#${idx + 1}: ${t.day} [${t.pillar || t.window}] ${rSign}${t.r.toFixed(2)}R`;
            tradeSelect.appendChild(opt);
        });

        // Trade Markers Setup
        function buildMarkers() {
            if (!document.getElementById('chk-trades').checked) {
                candlestickSeries.setMarkers([]);
                return;
            }
            const markers = [];
            tradesData.forEach((tr) => {
                if (!tr.fill_time) return;
                const isBuy = tr.side === 1;
                markers.push({
                    time: tr.fill_time,
                    position: isBuy ? 'belowBar' : 'aboveBar',
                    color: isBuy ? '#26a69a' : '#ef5350',
                    shape: isBuy ? 'arrowUp' : 'arrowDown',
                    text: `${isBuy ? 'BUY' : 'SELL'} @ ${tr.entry}`,
                });

                if (tr.exit_time) {
                    const isWin = tr.r > 0;
                    markers.push({
                        time: tr.exit_time,
                        position: isBuy ? 'aboveBar' : 'belowBar',
                        color: isWin ? '#26a69a' : '#ef5350',
                        shape: 'circle',
                        text: `EXIT ${isWin ? '+' : ''}${tr.r.toFixed(2)}R`,
                    });
                }
            });

            // Also add Liquidity Sweep Markers
            if (document.getElementById('chk-levels').checked) {
                levelsData.forEach(lvl => {
                    if (lvl.swept && lvl.sweep_time) {
                        markers.push({
                            time: lvl.sweep_time,
                            position: lvl.side === 1 ? 'aboveBar' : 'belowBar',
                            color: '#ff9800',
                            shape: lvl.side === 1 ? 'arrowDown' : 'arrowUp',
                            text: `SWEPT ${lvl.name}`,
                        });
                    }
                });
            }

            // Sort markers chronologically (Lightweight Charts requirement)
            markers.sort((a, b) => a.time - b.time);
            candlestickSeries.setMarkers(markers);
        }

        buildMarkers();

        function toggleTrades() {
            buildMarkers();
            redrawOverlay();
        }

        // Overlay Drawing Function (FVGs, OBs, Sessions, Levels, Trade Lines)
        function redrawOverlay() {
            const rect = container.getBoundingClientRect();
            const dpr = window.devicePixelRatio || 1;
            canvas.width = rect.width * dpr;
            canvas.height = rect.height * dpr;
            canvas.style.width = `${rect.width}px`;
            canvas.style.height = `${rect.height}px`;
            ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
            ctx.clearRect(0, 0, rect.width, rect.height);

            const timeScale = chart.timeScale();
            const logicalRange = timeScale.getVisibleLogicalRange();
            if (!logicalRange) return;

            const minVisibleIdx = Math.floor(logicalRange.from) - 20;
            const maxVisibleIdx = Math.ceil(logicalRange.to) + 20;

            const showFVGs = document.getElementById('chk-fvg').checked;
            const showOBs = document.getElementById('chk-ob').checked;
            const showLevels = document.getElementById('chk-levels').checked;
            const showKZ = document.getElementById('chk-kz').checked;
            const showTrades = document.getElementById('chk-trades').checked;

            // 1. Draw Killzone Sessions (London & NY AM)
            if (showKZ) {
                sessionsData.forEach(s => {
                    const idx1 = getLogicalIndex(s.start_time);
                    const idx2 = getLogicalIndex(s.end_time);

                    if (idx2 >= minVisibleIdx && idx1 <= maxVisibleIdx) {
                        const x1 = timeScale.logicalToCoordinate(idx1);
                        const x2 = timeScale.logicalToCoordinate(idx2);

                        if (x1 !== null && x2 !== null) {
                            const left = Math.min(x1, x2);
                            const w = Math.max(Math.abs(x2 - x1), 15);

                            if (s.name === 'LDN') {
                                ctx.fillStyle = 'rgba(255, 179, 0, 0.12)';
                                ctx.fillRect(left, 0, w, rect.height);
                                ctx.fillStyle = 'rgba(255, 179, 0, 0.7)';
                                ctx.font = '10px sans-serif';
                                ctx.fillText('LONDON KILLZONE', left + 4, 20);
                            } else if (s.name === 'NY_AM') {
                                ctx.fillStyle = 'rgba(0, 188, 212, 0.12)';
                                ctx.fillRect(left, 0, w, rect.height);
                                ctx.fillStyle = 'rgba(0, 188, 212, 0.7)';
                                ctx.font = '10px sans-serif';
                                ctx.fillText('NY AM KILLZONE', left + 4, 20);
                            } else {
                                ctx.fillStyle = 'rgba(120, 123, 134, 0.06)';
                                ctx.fillRect(left, 0, w, rect.height);
                            }
                        }
                    }
                });
            }

            // 2. Draw Fair Value Gaps (FVGs)
            if (showFVGs) {
                fvgsData.forEach(f => {
                    const idx1 = getLogicalIndex(f.start_time);
                    const idx2 = getLogicalIndex(f.end_time);

                    if (idx2 >= minVisibleIdx && idx1 <= maxVisibleIdx) {
                        const x1 = timeScale.logicalToCoordinate(idx1);
                        const x2 = timeScale.logicalToCoordinate(idx2);
                        const yTop = candlestickSeries.priceToCoordinate(f.top);
                        const yBot = candlestickSeries.priceToCoordinate(f.bottom);

                        if (x1 !== null && x2 !== null && yTop !== null && yBot !== null) {
                            const left = Math.min(x1, x2);
                            const w = Math.max(Math.abs(x2 - x1), 10);
                            const top = Math.min(yTop, yBot);
                            const h = Math.max(Math.abs(yBot - yTop), 2);

                            if (f.side === 1) { // Bullish FVG
                                ctx.fillStyle = f.mitigated ? 'rgba(38, 166, 154, 0.20)' : 'rgba(38, 166, 154, 0.45)';
                                ctx.strokeStyle = f.mitigated ? 'rgba(38, 166, 154, 0.5)' : '#26a69a';
                            } else { // Bearish FVG
                                ctx.fillStyle = f.mitigated ? 'rgba(239, 83, 80, 0.20)' : 'rgba(239, 83, 80, 0.45)';
                                ctx.strokeStyle = f.mitigated ? 'rgba(239, 83, 80, 0.5)' : '#ef5350';
                            }
                            ctx.fillRect(left, top, w, h);
                            ctx.lineWidth = 1;
                            ctx.strokeRect(left, top, w, h);

                            // FVG Label inside box
                            ctx.fillStyle = f.side === 1 ? '#26a69a' : '#ef5350';
                            ctx.font = '9px sans-serif';
                            ctx.fillText(f.mitigated ? 'FVG (Mitigated)' : 'FVG', left + 3, top + Math.min(h - 2, 11));
                        }
                    }
                });
            }

            // 3. Draw Order Blocks (OBs)
            if (showOBs) {
                obsData.forEach(ob => {
                    const idx1 = getLogicalIndex(ob.start_time);
                    const idx2 = getLogicalIndex(ob.end_time);

                    if (idx2 >= minVisibleIdx && idx1 <= maxVisibleIdx) {
                        const x1 = timeScale.logicalToCoordinate(idx1);
                        const x2 = timeScale.logicalToCoordinate(idx2);
                        const yTop = candlestickSeries.priceToCoordinate(ob.top);
                        const yBot = candlestickSeries.priceToCoordinate(ob.bottom);

                        if (x1 !== null && x2 !== null && yTop !== null && yBot !== null) {
                            const left = Math.min(x1, x2);
                            const w = Math.max(Math.abs(x2 - x1), 10);
                            const top = Math.min(yTop, yBot);
                            const h = Math.max(Math.abs(yBot - yTop), 2);

                            if (ob.side === 1) { // Bullish OB
                                ctx.fillStyle = ob.invalidated ? 'rgba(33, 150, 243, 0.15)' : 'rgba(33, 150, 243, 0.35)';
                                ctx.strokeStyle = ob.invalidated ? 'rgba(33, 150, 243, 0.4)' : '#2196f3';
                            } else { // Bearish OB
                                ctx.fillStyle = ob.invalidated ? 'rgba(156, 39, 176, 0.15)' : 'rgba(156, 39, 176, 0.35)';
                                ctx.strokeStyle = ob.invalidated ? 'rgba(156, 39, 176, 0.4)' : '#9c27b0';
                            }
                            ctx.fillRect(left, top, w, h);
                            ctx.lineWidth = 1.5;
                            ctx.setLineDash([4, 2]);
                            ctx.strokeRect(left, top, w, h);
                            ctx.setLineDash([]);

                            ctx.fillStyle = ob.side === 1 ? '#2196f3' : '#9c27b0';
                            ctx.font = '9px sans-serif';
                            ctx.fillText(ob.side === 1 ? '+OB' : '-OB', left + 3, top + Math.min(h - 2, 11));
                        }
                    }
                });
            }

            // 4. Draw Liquidity Levels
            if (showLevels) {
                levelsData.forEach(lvl => {
                    const idx1 = getLogicalIndex(lvl.start_time);
                    const idx2 = getLogicalIndex(lvl.end_time);

                    if (idx2 >= minVisibleIdx && idx1 <= maxVisibleIdx) {
                        const x1 = timeScale.logicalToCoordinate(idx1);
                        const x2 = timeScale.logicalToCoordinate(idx2);
                        const y = candlestickSeries.priceToCoordinate(lvl.price);

                        if (x1 !== null && x2 !== null && y !== null) {
                            const left = Math.min(x1, x2);
                            const right = Math.max(x1, x2);

                            ctx.strokeStyle = lvl.swept ? 'rgba(255, 152, 0, 0.6)' : '#ff9800';
                            ctx.lineWidth = 1.2;
                            ctx.setLineDash(lvl.swept ? [2, 2] : [5, 3]);
                            ctx.beginPath();
                            ctx.moveTo(left, y);
                            ctx.lineTo(right, y);
                            ctx.stroke();
                            ctx.setLineDash([]);

                            // Level Tag
                            ctx.fillStyle = '#ff9800';
                            ctx.font = '10px sans-serif';
                            ctx.fillText(`${lvl.name}`, left + 4, y - 3);
                        }
                    }
                });
            }

            // 5. Draw Trade Execution Lines (Entry, SL, TP)
            if (showTrades) {
                tradesData.forEach(tr => {
                    if (!tr.fill_time || !tr.exit_time) return;
                    const idx1 = getLogicalIndex(tr.fill_time);
                    const idx2 = getLogicalIndex(tr.exit_time);

                    if (idx2 >= minVisibleIdx && idx1 <= maxVisibleIdx) {
                        const x1 = timeScale.logicalToCoordinate(idx1);
                        const x2 = timeScale.logicalToCoordinate(idx2);
                        const yEntry = candlestickSeries.priceToCoordinate(tr.entry);
                        const ySL = candlestickSeries.priceToCoordinate(tr.sl);
                        const yTP = candlestickSeries.priceToCoordinate(tr.tp);

                        if (x1 !== null && x2 !== null) {
                            const left = Math.min(x1, x2);
                            const right = Math.max(x1, x2);

                            // Entry Line (Blue)
                            if (yEntry !== null) {
                                ctx.strokeStyle = '#2962ff';
                                ctx.lineWidth = 2;
                                ctx.beginPath();
                                ctx.moveTo(left, yEntry);
                                ctx.lineTo(right, yEntry);
                                ctx.stroke();
                                ctx.fillStyle = '#2962ff';
                                ctx.font = '10px sans-serif';
                                ctx.fillText(`Entry: ${tr.entry}`, left + 4, yEntry - 3);
                            }
                            // Stop Loss Line (Red dashed)
                            if (ySL !== null) {
                                ctx.strokeStyle = '#ef5350';
                                ctx.lineWidth = 1.5;
                                ctx.setLineDash([4, 3]);
                                ctx.beginPath();
                                ctx.moveTo(left, ySL);
                                ctx.lineTo(right, ySL);
                                ctx.stroke();
                                ctx.fillStyle = '#ef5350';
                                ctx.font = '10px sans-serif';
                                ctx.fillText(`SL: ${tr.sl}`, left + 4, ySL - 3);
                            }
                            // Take Profit Line (Green dashed)
                            if (yTP !== null) {
                                ctx.strokeStyle = '#26a69a';
                                ctx.lineWidth = 1.5;
                                ctx.setLineDash([4, 3]);
                                ctx.beginPath();
                                ctx.moveTo(left, yTP);
                                ctx.lineTo(right, yTP);
                                ctx.stroke();
                                ctx.fillStyle = '#26a69a';
                                ctx.font = '10px sans-serif';
                                ctx.fillText(`TP: ${tr.tp}`, left + 4, yTP - 3);
                            }
                            ctx.setLineDash([]);
                        }
                    }
                });
            }
        }

        // Event Listeners for Dynamic Redraw on Pan & Zoom
        chart.timeScale().subscribeVisibleTimeRangeChange(() => {
            redrawOverlay();
        });
        chart.timeScale().subscribeVisibleLogicalRangeChange(() => {
            redrawOverlay();
        });
        window.addEventListener('resize', redrawOverlay);
        setTimeout(redrawOverlay, 300);

        // Jump to Selected Trade
        function jumpToSelectedTrade() {
            const sel = document.getElementById('trade-select');
            const idx = parseInt(sel.value, 10);
            if (isNaN(idx) || !tradesData[idx]) return;

            const tr = tradesData[idx];
            const hud = document.getElementById('trade-hud');
            hud.style.display = 'block';
            document.getElementById('hud-trade-title').textContent = `Trade #${idx + 1}: ${tr.day} (${tr.pillar || tr.window})`;
            document.getElementById('hud-entry').textContent = tr.entry;
            document.getElementById('hud-sl').textContent = tr.sl;
            document.getElementById('hud-tp').textContent = tr.tp;

            const isWin = tr.r > 0;
            const rElem = document.getElementById('hud-outcome');
            rElem.textContent = `${isWin ? '+' : ''}${tr.r.toFixed(2)} R (${tr.reason || 'Closed'})`;
            rElem.className = isWin ? 'metric-val metric-win' : 'metric-val metric-loss';

            // Center View around trade using exact logical bar indices
            const fillIdx = getLogicalIndex(tr.fill_time);
            chart.timeScale().setVisibleLogicalRange({ from: fillIdx - 35, to: fillIdx + 45 });
            setTimeout(redrawOverlay, 50);
            setTimeout(redrawOverlay, 200);
        }

        function resetView() {
            chart.timeScale().fitContent();
            document.getElementById('trade-hud').style.display = 'none';
            document.getElementById('trade-select').value = "";
            setTimeout(redrawOverlay, 150);
        }
    </script>
</body>
</html>
"""


def build_interactive_chart(
    chart_data: dict[str, Any],
    trades: list[dict[str, Any]],
    symbol: str,
    output_path: Path,
    title: str = "ICT Continuous Market Structure & Silver Bullet Visualizer",
) -> Path:
    """Builds a standalone TradingView Lightweight Charts HTML file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    html = HTML_TEMPLATE
    html = html.replace("{{TITLE}}", title)
    html = html.replace("{{SYMBOL}}", symbol)
    html = html.replace("{{NUM_TRADES}}", str(len(trades)))
    html = html.replace("{{CANDLES_JSON}}", json.dumps(chart_data.get("candles", [])))
    html = html.replace("{{FVGS_JSON}}", json.dumps(chart_data.get("fvgs", [])))
    html = html.replace("{{OBS_JSON}}", json.dumps(chart_data.get("order_blocks", [])))
    html = html.replace("{{LEVELS_JSON}}", json.dumps(chart_data.get("liquidity_levels", [])))
    html = html.replace("{{SESSIONS_JSON}}", json.dumps(chart_data.get("sessions", [])))
    html = html.replace("{{TRADES_JSON}}", json.dumps(trades))

    output_path.write_text(html, encoding="utf-8")
    return output_path
