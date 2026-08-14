import sys

filepath = r"C:\Users\shrey\Desktop\Projects\Braille-Project\Firmware\braille_ui.py"

with open(filepath, 'r', encoding='utf-8') as f:
    lines = f.readlines()

idx = -1
for i, line in enumerate(lines):
    if line.startswith("    class MetricsPanel(QLabel):"):
        idx = i
        break

if idx == -1:
    print("Could not find class MetricsPanel(QLabel):")
    sys.exit(1)

new_content = """    # ══════════════════════════════════════════════════════════════
    # METRIC CARD WIDGET
    # ══════════════════════════════════════════════════════════════

    class MetricCard(QFrame):
        \"\"\"A single styled metric display card with label, value, and subtitle.\"\"\"

        def __init__(self, label: str, accent: str = "#58a6ff", parent=None):
            super().__init__(parent)
            self._accent = accent
            self.setMinimumHeight(80)
            self.setStyleSheet(f\"\"\"
                MetricCard {{
                    background: #161b22;
                    border: 1px solid #21262d;
                    border-left: 3px solid {accent};
                    border-radius: 6px;
                }}
            \"\"\")
            layout = QVBoxLayout(self)
            layout.setContentsMargins(12, 8, 12, 8)
            layout.setSpacing(2)

            self._label_widget = QLabel(label.upper())
            self._label_widget.setStyleSheet(
                f"color: {accent}; font-size: 8pt; font-weight: bold; "
                "font-family: 'Segoe UI', sans-serif; letter-spacing: 1px;"
            )

            self._value_widget = QLabel("—")
            self._value_widget.setStyleSheet(
                "color: #e6edf3; font-size: 22pt; font-weight: bold; "
                "font-family: 'Segoe UI', sans-serif;"
            )

            self._sub_widget = QLabel("")
            self._sub_widget.setStyleSheet(
                "color: #8b949e; font-size: 8pt; font-family: 'Segoe UI', sans-serif;"
            )

            layout.addWidget(self._label_widget)
            layout.addWidget(self._value_widget)
            layout.addWidget(self._sub_widget)

        def set_value(self, value: str, subtitle: str = ""):
            self._value_widget.setText(value)
            self._sub_widget.setText(subtitle)


    # ══════════════════════════════════════════════════════════════
    # LIVE STATUS BAR
    # ══════════════════════════════════════════════════════════════

    class StatusBar(QWidget):
        \"\"\"Top header bar: title, live indicator, session timer, COM port.\"\"\"

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setFixedHeight(44)
            self.setStyleSheet("background: #0d1117; border-bottom: 1px solid #21262d;")
            layout = QHBoxLayout(self)
            layout.setContentsMargins(16, 0, 16, 0)

            # Title
            title = QLabel("BRAILLE PERFORMANCE MONITOR")
            title.setStyleSheet(
                "color: #e6edf3; font-size: 11pt; font-weight: bold; "
                "font-family: 'Segoe UI', sans-serif; letter-spacing: 2px;"
            )

            # Separator
            sep = QLabel("│")
            sep.setStyleSheet("color: #30363d; font-size: 14pt; margin: 0 8px;")

            # Live indicator label
            self._live_label = QLabel("● LIVE")
            self._live_label.setStyleSheet(
                "color: #3fb950; font-size: 9pt; font-weight: bold; "
                "font-family: 'Segoe UI', sans-serif;"
            )

            # Timer
            self._timer_label = QLabel("00:00")
            self._timer_label.setStyleSheet(
                "color: #8b949e; font-size: 9pt; font-family: 'Segoe UI Mono', monospace;"
            )

            # COM port
            self._port_label = QLabel(f"COM: {PORT}")
            self._port_label.setStyleSheet(
                "color: #8b949e; font-size: 9pt; font-family: 'Segoe UI', sans-serif;"
            )

            # Weight preset info
            self._preset_label = QLabel(f"Preset: {_WEIGHT_PRESET}")
            self._preset_label.setStyleSheet(
                "color: #58a6ff; font-size: 8pt; font-family: 'Segoe UI', sans-serif;"
            )

            layout.addWidget(title)
            layout.addWidget(sep)
            layout.addWidget(self._live_label)
            layout.addStretch()
            layout.addWidget(self._preset_label)
            layout.addSpacing(20)
            layout.addWidget(self._timer_label)
            layout.addSpacing(20)
            layout.addWidget(self._port_label)

            # Pulse timer for the LIVE dot
            self._pulse = True
            self._pulse_timer = QTimer()
            self._pulse_timer.timeout.connect(self._pulse_tick)
            self._pulse_timer.start(800)

            self._start_time = time.time()

        def _pulse_tick(self):
            self._pulse = not self._pulse
            if self._pulse:
                self._live_label.setStyleSheet(
                    "color: #3fb950; font-size: 9pt; font-weight: bold; "
                    "font-family: 'Segoe UI', sans-serif;"
                )
            else:
                self._live_label.setStyleSheet(
                    "color: #1a3a1a; font-size: 9pt; font-weight: bold; "
                    "font-family: 'Segoe UI', sans-serif;"
                )

        def tick(self):
            elapsed = int(time.time() - self._start_time)
            m, s = divmod(elapsed, 60)
            self._timer_label.setText(f"{m:02d}:{s:02d}")


    # ══════════════════════════════════════════════════════════════
    # METRICS PANEL (grid of MetricCards)
    # ══════════════════════════════════════════════════════════════

    class MetricsPanel(QWidget):
        \"\"\"Grid of MetricCards showing live session metrics.\"\"\"

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setStyleSheet("background: #0d1117;")
            grid = QGridLayout(self)
            grid.setContentsMargins(8, 8, 8, 8)
            grid.setSpacing(8)

            # ── Row 0: Speed ──────────────────────────────
            self._wpm      = MetricCard("WPM",         "#58a6ff")
            self._trend    = MetricCard("EMA Trend",   "#58a6ff")
            self._chars    = MetricCard("Characters",  "#58a6ff")
            grid.addWidget(self._wpm,   0, 0)
            grid.addWidget(self._trend, 0, 1)
            grid.addWidget(self._chars, 0, 2)

            # ── Row 1: Accuracy ───────────────────────────
            self._eff      = MetricCard("Path Eff.",      "#3fb950")
            self._reg      = MetricCard("Regressions",    "#3fb950")
            self._hes      = MetricCard("Hesitation Rate","#3fb950")
            grid.addWidget(self._eff, 1, 0)
            grid.addWidget(self._reg, 1, 1)
            grid.addWidget(self._hes, 1, 2)

            # ── Row 2: Difficulty ─────────────────────────
            self._diff     = MetricCard("Avg Difficulty", "#f0883e")
            self._rev      = MetricCard("Reversals",      "#f0883e")
            self._consist  = MetricCard("Consistency",    "#f0883e")
            grid.addWidget(self._diff,    2, 0)
            grid.addWidget(self._rev,     2, 1)
            grid.addWidget(self._consist, 2, 2)

            # ── Row 3: Current touch status ───────────────
            self._word_now = MetricCard("Current Word",   "#e6edf3")
            self._skip     = MetricCard("Skip Rate",      "#f85149")
            self._touch_ms = MetricCard("Touch Duration", "#8b949e")
            grid.addWidget(self._word_now, 3, 0)
            grid.addWidget(self._skip,     3, 1)
            grid.addWidget(self._touch_ms, 3, 2)

        def update_metrics(self, m, ws, vt, ewiqr_snap, diff_snap,
                           eff_avg, wpm_ema, finger_wpms, skip_snap):
            _wpm = m["wpm"]
            _eff = eff_avg
            _diff = m["avg_difficulty"]
            _cons = vt["consistency"]

            # WPM color
            wpm_color = (
                "#3fb950" if _wpm >= 50 else
                ("#f0883e" if _wpm >= 20 else "#f85149")
            )
            self._wpm.setStyleSheet(self._wpm.styleSheet()  # keep card style
                .replace(self._wpm._accent, wpm_color))
            self._wpm._accent = wpm_color
            self._wpm.set_value(f"{_wpm:.0f}",
                                f"F0: {finger_wpms[0]:.0f}  F1: {finger_wpms[1]:.0f}")

            self._trend.set_value(f"{wpm_ema:.0f}", "EMA smoothed")
            self._chars.set_value(str(m["chars_total"]),
                                  f"{m['chars_window']} in window")

            self._eff.set_value(f"{_eff:.2f}",
                                f"Backtracks: {m['total_backtracks']}")
            self._reg.set_value(str(ws["total_regressions"]),
                                f"Flagged: {len(ws['flagged_words'])}")
            self._hes.set_value(f"{ws['hesitation_rate']*100:.0f}%",
                                "regression / total touches")

            self._diff.set_value(f"{_diff:.2f}",
                                 f"Word rev: {m['word_reversals_total']}")
            self._rev.set_value(f"{m['avg_reversals']:.1f}",
                                "avg per touch")
            self._consist.set_value(f"{_cons:.2f}",
                                    f"IQR: {vt['iqr']:.2f}")

            cw = m.get("current_word", "") or "—"
            touch_icon = "▶" if m["is_touching"] else "○"
            self._word_now.set_value(cw,
                                     f"{touch_icon} {m['pressed_cells']} cells active")
            self._skip.set_value(f"{skip_snap['skip_rate']:.0f}%",
                                 f"{len(skip_snap['skipped_words'])} words skipped")
            self._touch_ms.set_value(f"{m['avg_duration']*1000:.0f} ms",
                                     f"{vt['mean_vel']:.1f} cells/s")


    # ══════════════════════════════════════════════════════════════
    # WORD STATS TABLE
    # ══════════════════════════════════════════════════════════════

    class WordStatsPanel(QWidget):
        \"\"\"Compact scoreboard table showing per-word stats.\"\"\"

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setStyleSheet("background: #0d1117;")
            layout = QVBoxLayout(self)
            layout.setContentsMargins(8, 8, 8, 8)
            layout.setSpacing(6)

            hdr = QLabel("WORD SCOREBOARD")
            hdr.setStyleSheet(
                "color: #58a6ff; font-size: 9pt; font-weight: bold; "
                "font-family: 'Segoe UI', sans-serif; letter-spacing: 1px;"
            )
            layout.addWidget(hdr)

            from PyQt5.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView
            self._table = QTableWidget(0, 4)
            self._table.setHorizontalHeaderLabels(["Word", "Touches", "Regress.", "Status"])
            self._table.setStyleSheet(f\"\"\"
                QTableWidget {{
                    background: #161b22;
                    color: #e6edf3;
                    font-family: 'Segoe UI', sans-serif;
                    font-size: 9pt;
                    border: 1px solid #21262d;
                    border-radius: 4px;
                    gridline-color: #21262d;
                }}
                QHeaderView::section {{
                    background: #0d1117;
                    color: #8b949e;
                    border: none;
                    border-bottom: 1px solid #30363d;
                    font-size: 8pt;
                    font-weight: bold;
                    padding: 4px 8px;
                    letter-spacing: 1px;
                }}
                QTableWidget::item {{
                    padding: 4px 8px;
                    border-bottom: 1px solid #21262d;
                }}
                QTableWidget::item:selected {{
                    background: #21262d;
                }}
            \"\"\")
            self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
            self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
            self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
            self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
            self._table.verticalHeader().setVisible(False)
            self._table.setSelectionMode(QTableWidget.NoSelection)
            self._table.setEditTriggers(QTableWidget.NoEditTriggers)
            layout.addWidget(self._table, 1)

            # Sequence strip
            seq_hdr = QLabel("RECENT SEQUENCE")
            seq_hdr.setStyleSheet(
                "color: #8b949e; font-size: 8pt; font-weight: bold; "
                "font-family: 'Segoe UI', sans-serif; letter-spacing: 1px; margin-top: 4px;"
            )
            self._seq_label = QLabel("—")
            self._seq_label.setStyleSheet(
                "color: #e6edf3; font-size: 9pt; font-family: 'Segoe UI', sans-serif;"
            )
            self._seq_label.setWordWrap(True)
            layout.addWidget(seq_hdr)
            layout.addWidget(self._seq_label)

        def update_stats(self, ws, skip_snap):
            wc   = ws["word_count"]
            rc   = ws.get("regression_count", {})
            # rc may not be directly in snapshot; rebuild from top_regressed
            reg_dict = dict(ws.get("top_regressed", []))
            flagged  = set(ws["flagged_words"])

            # Sort by touches descending
            sorted_words = sorted(wc.items(), key=lambda x: x[1], reverse=True)

            self._table.setRowCount(len(sorted_words))
            for i, (word, touches) in enumerate(sorted_words):
                regressions = reg_dict.get(word, 0)
                if word in flagged:
                    status, status_color = "FLAGGED", "#f85149"
                    row_bg = QColor("#2d0a0a")
                elif regressions > 0:
                    status, status_color = "Regression", "#f0883e"
                    row_bg = QColor("#2d1a00")
                else:
                    status, status_color = "OK", "#3fb950"
                    row_bg = QColor("#161b22")

                for col_idx, text in enumerate([word, str(touches), str(regressions), status]):
                    item = QTableWidgetItem(text)
                    item.setForeground(QColor(status_color if col_idx == 3 else "#e6edf3"))
                    item.setBackground(row_bg)
                    self._table.setItem(i, col_idx, item)

            seq_display = " → ".join(ws["touch_sequence"][-7:]) \\
                          if ws["touch_sequence"] else "—"
            self._seq_label.setText(seq_display)


    # ══════════════════════════════════════════════════════════════
    # PLOT PANEL (unchanged widget classes, kept internal)
    # ══════════════════════════════════════════════════════════════

    class BarChartWidget(pg.PlotWidget):
        \"\"\"Per-word dual bar chart using pyqtgraph.\"\"\"

        def __init__(self, parent=None):
            super().__init__(parent, background="#0d1117")
            self.setTitle("Per-Word Performance (Time-on-Task & Touch Counts)",
                          color="#e6edf3", size="10pt")
            self.setLabel('left', "Time-on-Task (s)", color="#8b949e")
            self.setLabel('bottom', "Word", color="#8b949e")
            self.showGrid(y=True, alpha=0.2)
            self._last_update = 0
            self._word_list = []

            bottom_ax = self.getAxis('bottom')
            bottom_ax.setTickFont(QFont("Segoe UI", 7))
            bottom_ax.setTextPen(pg.mkPen("#8b949e"))
            bottom_ax.setStyle(tickTextOffset=6, autoExpandTextSpace=True,
                               autoReduceTextSpace=False)
            bottom_ax.setHeight(50)

        def update_chart(self, welford_snap, word_count, ewiqr_snap, wb_snap):
            now = time.time()
            if now - self._last_update < 0.5:
                return
            self._last_update = now

            word_list = []
            word_rows = []
            for ri in range(GRID):
                for e in wb_snap.get(ri, []):
                    word_list.append(e["word"])
                    word_rows.append(ri)

            if not word_list:
                return

            n = len(word_list)
            x = np.arange(n)
            tot_vals = np.array([welford_snap.get(w, {}).get("mean", 0.0) for w in word_list])
            cnt_vals = np.array([word_count.get(w, 0) for w in word_list], dtype=float)

            cnt_max = max(cnt_vals.max(), 1)
            tot_max = max(tot_vals.max(), 0.1)
            cnt_scaled = cnt_vals / cnt_max * tot_max if cnt_max > 0 else cnt_vals

            tab10 = plt.cm.tab10
            colors_tot = [pg.mkColor(*[int(c * 255) for c in tab10(wr)[:3]]) for wr in word_rows]
            colors_cnt = [pg.mkColor(*[int(c * 255) for c in tab10(wr)[:3]], 80) for wr in word_rows]

            self.clear()

            bw = 0.35
            bg_tot = pg.BarGraphItem(x=x - bw/2, height=tot_vals, width=bw, brushes=colors_tot)
            self.addItem(bg_tot)
            bg_cnt = pg.BarGraphItem(x=x + bw/2, height=cnt_scaled, width=bw, brushes=colors_cnt)
            self.addItem(bg_cnt)

            if welford_snap:
                total_n = sum(v.get("n", 0) for v in welford_snap.values())
                if total_n > 0:
                    session_avg = sum(v.get("mean", 0) * v.get("n", 0)
                                      for v in welford_snap.values()) / total_n
                    self.addLine(y=session_avg,
                                 pen=pg.mkPen("#3fb950", style=Qt.DashLine, width=1.5))

            ax = self.getAxis('bottom')
            ax.setTicks([[(i, w) for i, w in enumerate(word_list)]])
            ax.setTickFont(QFont("Segoe UI", 7))
            ax.setTextPen(pg.mkPen("#8b949e"))
            self._word_list = word_list


    class WPMTrendWidget(pg.PlotWidget):
        \"\"\"Live WPM trend plot with raw + EMA lines.\"\"\"

        def __init__(self, parent=None):
            super().__init__(parent, background="#0d1117")
            self.setTitle("Live WPM Trend", color="#e6edf3", size="10pt")
            self.setLabel('left', "Words Per Minute", color="#8b949e")
            self.setLabel('bottom', "Session Time (s)", color="#8b949e")
            self.showGrid(y=True, alpha=0.2)
            self.addLegend(offset=(10, 10))
            self._line_raw = self.plot([], [], pen=pg.mkPen("#334466", width=1), name="Raw WPM")
            self._line_ema = self.plot([], [], pen=pg.mkPen("#58a6ff", width=2.5), name="EMA Trend")
            self.addLine(y=50,  pen=pg.mkPen("#f0883e", style=Qt.DashLine, width=0.9))
            self.addLine(y=100, pen=pg.mkPen("#3fb950", style=Qt.DashLine, width=0.9))
            self._lbl_50 = pg.TextItem("50 WPM", color="#f0883e", anchor=(1.0, 1.0))
            self._lbl_50.setFont(QFont("Segoe UI", 7))
            self._lbl_50.setPos(10, 50)
            self.addItem(self._lbl_50)
            self._lbl_100 = pg.TextItem("100 WPM", color="#3fb950", anchor=(1.0, 1.0))
            self._lbl_100.setFont(QFont("Segoe UI", 7))
            self._lbl_100.setPos(10, 100)
            self.addItem(self._lbl_100)
            self._last_update = 0

        def update_trend(self, x_raw, y_raw, y_ema, y_max):
            now = time.time()
            if now - self._last_update < 0.5:
                return
            self._last_update = now
            if not x_raw:
                return
            self._line_raw.setData(x_raw, y_raw)
            self._line_ema.setData(x_raw, y_ema)
            self.setYRange(0, max(10, y_max))
            x_end = max(x_raw[-1], 10)
            self.setXRange(x_raw[0], x_end)
            self._lbl_50.setPos(x_end, 50)
            self._lbl_100.setPos(x_end, 100)


    class RegressionChartWidget(pg.PlotWidget):
        \"\"\"Horizontal bar chart for inter-word regressions.\"\"\"

        def __init__(self, parent=None):
            super().__init__(parent, background="#0d1117")
            self.setTitle("Most-Regressed Words", color="#e6edf3", size="10pt")
            self.setLabel('bottom', "Regression count", color="#8b949e")
            self.showGrid(x=True, alpha=0.2)
            self._last_update = 0
            self._empty_text = pg.TextItem("No regressions yet", color="#444444", anchor=(0.5, 0.5))
            self._empty_text.setFont(QFont("Segoe UI", 11))
            self.addItem(self._empty_text)
            self._empty_text.setPos(5, 0)

            # Legend note
            self._legend_red  = pg.TextItem(
                f"● Red = flagged (>{REGRESSION_FLAG_THRESHOLD}x)",
                color="#f85149", anchor=(0.0, 0.0))
            self._legend_red.setFont(QFont("Segoe UI", 7))
            self._legend_blue = pg.TextItem("● Blue = normal",
                color="#58a6ff", anchor=(0.0, 0.0))
            self._legend_blue.setFont(QFont("Segoe UI", 7))
            self.addItem(self._legend_red)
            self.addItem(self._legend_blue)

        def update_regressions(self, regression_count, flagged_words):
            now = time.time()
            if now - self._last_update < 0.5:
                return
            self._last_update = now

            visible = {w: c for w, c in regression_count.items() if c > 0}
            sorted_items = sorted(visible.items(), key=lambda x: x[1], reverse=True)

            self.clear()
            self._legend_red  = pg.TextItem(
                f"● Red = flagged (>{REGRESSION_FLAG_THRESHOLD}x)",
                color="#f85149", anchor=(0.0, 0.0))
            self._legend_red.setFont(QFont("Segoe UI", 7))
            self._legend_blue = pg.TextItem("● Blue = normal",
                color="#58a6ff", anchor=(0.0, 0.0))
            self._legend_blue.setFont(QFont("Segoe UI", 7))

            if not sorted_items:
                self._empty_text = pg.TextItem("No regressions yet",
                                               color="#444444", anchor=(0.5, 0.5))
                self._empty_text.setFont(QFont("Segoe UI", 11))
                self.addItem(self._empty_text)
                self._empty_text.setPos(5, 0)
                self.addItem(self._legend_red)
                self.addItem(self._legend_blue)
                return

            words = [item[0] for item in sorted_items]
            counts = [item[1] for item in sorted_items]
            flagged_set = set(flagged_words)
            y_pos = np.arange(len(words))
            colors = [pg.mkColor("#f85149") if w in flagged_set
                      else pg.mkColor("#58a6ff") for w in words]

            bg = pg.BarGraphItem(x0=0, y=y_pos, height=0.6, width=counts, brushes=colors)
            self.addItem(bg)

            ax = self.getAxis('left')
            ax.setTicks([[(i, w) for i, w in enumerate(words)]])
            self.invertY(True)
            self.setXRange(0, max(1, max(counts) * 1.15))

            for i, c in enumerate(counts):
                txt = pg.TextItem(str(c), color="#e6edf3", anchor=(0, 0.5))
                txt.setFont(QFont("Segoe UI", 9, QFont.Bold))
                txt.setPos(c + 0.1, i)
                self.addItem(txt)

            self.addItem(self._legend_red)
            self.addItem(self._legend_blue)
            n = len(words)
            self._legend_red.setPos(0, -1.2 if n > 0 else 0)
            self._legend_blue.setPos(max(counts) * 0.4, -1.2 if n > 0 else 0)


    class PerfHeatmapWidget(pg.GraphicsLayoutWidget):
        \"\"\"Performance heatmap (Time-on-Task or EWIQR Difficulty).\"\"\"

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setBackground("#0d1117")
            self._mode = 'tot'
            self._last_update = 0

            self._plot = self.addPlot(title="Performance Heatmap")
            self._plot.invertY(True)
            self._plot.setRange(xRange=[-0.5, GRID - 0.5], yRange=[-0.5, GRID - 0.5])
            self._plot.setAspectLocked(True)

            self._img = pg.ImageItem()
            ylrd_lut = self._build_ylrd_lut()
            self._img.setLookupTable(ylrd_lut)
            self._plot.addItem(self._img)

            self._texts = {}
            for r in range(GRID):
                for c in range(GRID):
                    word = get_word_from_touch(r, c) or "?"
                    txt = pg.TextItem(f"{word}\\n—", color="#111111", anchor=(0.5, 0.5))
                    txt.setFont(QFont("Segoe UI", 7, QFont.Bold))
                    txt.setPos(c, r)
                    self._plot.addItem(txt)
                    self._texts[(r, c)] = txt

            for i in range(GRID + 1):
                pos = i - 0.5
                self._plot.addLine(x=pos, pen=pg.mkPen("#21262d", width=1))
                self._plot.addLine(y=pos, pen=pg.mkPen("#21262d", width=1))

            x_ticks = [(i, f"C{i}") for i in range(GRID)]
            y_ticks = [(i, f"R{i}") for i in range(GRID)]
            self._plot.getAxis('bottom').setTicks([x_ticks])
            self._plot.getAxis('left').setTicks([y_ticks])

        @staticmethod
        def _build_ylrd_lut():
            colors = [(0, 0, 0), (255, 255, 204), (254, 217, 118),
                      (254, 178, 76), (253, 141, 60), (240, 59, 32), (189, 0, 38)]
            lut = np.zeros((256, 4), dtype=np.ubyte)
            n = len(colors) - 1
            for i in range(256):
                t = i / 255.0 * n
                idx = int(t)
                f = t - idx
                if idx >= n:
                    idx, f = n - 1, 1.0
                c0, c1 = colors[idx], colors[idx + 1]
                lut[i] = [int(c0[j] + f * (c1[j] - c0[j])) for j in range(3)] + [255]
            return lut

        def set_mode(self, mode):
            self._mode = mode
            self._last_update = 0

        def update_perf(self, Z_tot, Z_diff, wb_snap):
            now = time.time()
            if now - self._last_update < 0.5:
                return
            self._last_update = now
            Z = Z_tot if self._mode == 'tot' else Z_diff
            z_max = float(Z.max()) if Z.max() > 0 else 1.0
            normalized = np.clip(Z / z_max * 255, 0, 255).astype(np.ubyte)
            self._img.setImage(normalized.T, levels=[0, 255])
            self._img.setRect(-0.5, -0.5, GRID, GRID)
            mode_label = "Time-on-Task" if self._mode == 'tot' else "EWIQR Difficulty"
            self._plot.setTitle(f"Performance Heatmap — {mode_label}")
            for r in range(GRID):
                for c in range(GRID):
                    word = get_word_from_touch(r, c) or "?"
                    val = Z[r, c]
                    val_str = f"{val:.2f}" if val > 0 else "—"
                    self._texts[(r, c)].setText(f"{word}\\n{val_str}")


    class VelocityProfileWidget(pg.PlotWidget):
        \"\"\"Last-N velocity profile overlay.\"\"\"

        def __init__(self, parent=None):
            super().__init__(parent, background="#0d1117")
            self.setTitle("Velocity Profile — last 20 touches",
                          color="#e6edf3", size="10pt")
            self.setLabel('left', "Velocity (cells/sec)", color="#8b949e")
            self.setLabel('bottom', "Step index", color="#8b949e")
            self.showGrid(y=True, alpha=0.2)
            self.addLine(y=0, pen=pg.mkPen("#30363d", width=0.5))
            self._lines_past = []
            self.addLegend(offset=(10, 10))
            self._line_recent = self.plot([], [], pen=pg.mkPen("#58a6ff", width=2.5),
                                          name="Most recent")
            self._line_mean = self.plot([], [], pen=pg.mkPen("#f0883e", width=2,
                                             style=Qt.DashLine), name="Weighted mean")
            self._last_update = 0

        def update_velocities(self, vel_history_snapshot, alpha_weight=0.15):
            now = time.time()
            if now - self._last_update < 0.2:
                return
            self._last_update = now
            vels = vel_history_snapshot
            if not vels:
                return
            for line in self._lines_past:
                self.removeItem(line)
            self._lines_past = []
            N = len(vels)
            for i in range(N - 1):
                v = vels[i]
                if len(v) >= 2:
                    x = np.arange(len(v))
                    line = self.plot(x, v, pen=pg.mkPen("#444444", width=0.8))
                    line.setOpacity(0.2)
                    self._lines_past.append(line)
            v_recent = vels[-1]
            if len(v_recent) >= 2:
                self._line_recent.setData(np.arange(len(v_recent)), v_recent)
            else:
                self._line_recent.setData([], [])
            mean_vel, _ = VelocityProfileMonitor._compute_weighted_mean_velocity(
                vels, alpha_weight)
            if mean_vel is not None:
                self._line_mean.setData(np.arange(len(mean_vel)), mean_vel)
            else:
                self._line_mean.setData([], [])
            all_vals = []
            for va in vels:
                if len(va) >= 2:
                    all_vals.extend(va.tolist())
            if all_vals:
                self.setYRange(-0.1, max(0.5, max(all_vals) * 1.1))
            max_step = max(len(v) for v in vels)
            self.setXRange(-1, max(2, max_step))


    class EfficiencyWidget(pg.PlotWidget):
        \"\"\"Path efficiency scatter + trend plot.\"\"\"

        def __init__(self, parent=None):
            super().__init__(parent, background="#0d1117")
            self.setTitle("Path Efficiency Over Session", color="#e6edf3", size="10pt")
            self.setLabel('left', "Path efficiency (η)", color="#8b949e")
            self.setLabel('bottom', "Contact # (press→release)", color="#8b949e")
            self.showGrid(y=True, alpha=0.2)
            self.setYRange(0, 1.05)
            self.setXRange(0, 10)
            self.addLine(y=0.8, pen=pg.mkPen("#3fb950", width=1.5, style=Qt.DashLine))
            from pyqtgraph import LinearRegionItem
            band_g = LinearRegionItem([0.8, 1.05], orientation='horizontal',
                                       brush=pg.mkBrush(63, 185, 80, 15), movable=False)
            band_o = LinearRegionItem([0.5, 0.8],  orientation='horizontal',
                                       brush=pg.mkBrush(240, 136, 62, 15), movable=False)
            band_r = LinearRegionItem([0.0, 0.5],  orientation='horizontal',
                                       brush=pg.mkBrush(248, 81, 73, 15), movable=False)
            for b in (band_g, band_o, band_r):
                b.setZValue(-10)
                self.addItem(b)
            _lbl_p = pg.TextItem("Proficient",  color="#3fb950", anchor=(1.0, 0.5))
            _lbl_p.setFont(QFont("Segoe UI", 7))
            _lbl_p.setPos(10, 0.90)
            self.addItem(_lbl_p)
            self._lbl_p = _lbl_p
            _lbl_d = pg.TextItem("Developing", color="#f0883e", anchor=(1.0, 0.5))
            _lbl_d.setFont(QFont("Segoe UI", 7))
            _lbl_d.setPos(10, 0.65)
            self.addItem(_lbl_d)
            self._lbl_d = _lbl_d
            _lbl_s = pg.TextItem("Struggling", color="#f85149", anchor=(1.0, 0.5))
            _lbl_s.setFont(QFont("Segoe UI", 7))
            _lbl_s.setPos(10, 0.25)
            self.addItem(_lbl_s)
            self._lbl_s = _lbl_s
            self.addLegend(offset=(10, 10))
            self._scatter = pg.ScatterPlotItem(size=8, pen=pg.mkPen("#30363d", width=0.5))
            self.addItem(self._scatter)
            self._conn_line = self.plot([], [], pen=pg.mkPen("#58a6ff", width=1.2), name="Path")
            self._conn_line.setOpacity(0.4)
            self._trend_line = self.plot([], [], pen=pg.mkPen("#f0883e", width=3), name="Trend")
            self.plot([], [], pen=pg.mkPen("#3fb950", width=1.5, style=Qt.DashLine),
                      name="Proficiency target (η=0.8)")
            self._last_update = 0

        def update_efficiency(self, eff_hist, evt_idx, cached_trend_x, cached_trend_y):
            now = time.time()
            if now - self._last_update < 0.5:
                return
            self._last_update = now
            if len(eff_hist) < 2:
                return
            colors = []
            for eta in eff_hist:
                if eta >= 0.8:
                    colors.append(pg.mkBrush("#3fb950"))
                elif eta >= 0.5:
                    colors.append(pg.mkBrush("#f0883e"))
                else:
                    colors.append(pg.mkBrush("#f85149"))
            spots = [{'pos': (x, y), 'brush': b}
                     for x, y, b in zip(evt_idx, eff_hist, colors)]
            self._scatter.setData(spots)
            self._conn_line.setData(evt_idx, eff_hist)
            if cached_trend_y is not None and len(cached_trend_y) > 0:
                self._trend_line.setData(cached_trend_x, cached_trend_y)
            if evt_idx:
                x_end = max(evt_idx) + 5
                self.setXRange(0, x_end)
                self._lbl_p.setPos(x_end - 1, 0.90)
                self._lbl_d.setPos(x_end - 1, 0.65)
                self._lbl_s.setPos(x_end - 1, 0.25)


    # ── Plot selector panel ──────────────────────────────────────

    class PlotPanel(QWidget):
        \"\"\"Switchable plot panel with sidebar selector and stacked plots.\"\"\"

        PLOT_LABELS = [
            "Per-Word Bars",
            "WPM Trend",
            "Regression Chart",
            "Perf. Heatmap",
            "Velocity Profile",
            "Path Efficiency",
        ]

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setStyleSheet("background: #0d1117;")
            layout = QHBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)

            # Sidebar
            sidebar = QWidget()
            sidebar.setFixedWidth(120)
            sidebar.setStyleSheet("background: #161b22; border-right: 1px solid #21262d;")
            sb_layout = QVBoxLayout(sidebar)
            sb_layout.setContentsMargins(0, 8, 0, 8)
            sb_layout.setSpacing(0)

            sidebar_lbl = QLabel("CHARTS")
            sidebar_lbl.setStyleSheet(
                "color: #8b949e; font-size: 7pt; font-weight: bold; "
                "font-family: 'Segoe UI'; letter-spacing: 2px; padding: 4px 12px;"
            )
            sb_layout.addWidget(sidebar_lbl)

            self._buttons = []
            for i, label in enumerate(self.PLOT_LABELS):
                btn = QPushButton(label)
                btn.setCheckable(True)
                btn.setStyleSheet(\"\"\"
                    QPushButton {
                        background: transparent;
                        color: #8b949e;
                        border: none;
                        text-align: left;
                        padding: 10px 14px;
                        font-family: 'Segoe UI';
                        font-size: 9pt;
                    }
                    QPushButton:checked {
                        background: #21262d;
                        color: #58a6ff;
                        border-left: 3px solid #58a6ff;
                    }
                    QPushButton:hover:!checked {
                        background: #1a1f26;
                        color: #c9d1d9;
                    }
                \"\"\")
                btn.setCursor(Qt.PointingHandCursor)
                btn.clicked.connect(lambda checked, idx=i: self._on_select(idx))
                sb_layout.addWidget(btn)
                self._buttons.append(btn)

            sb_layout.addStretch()
            layout.addWidget(sidebar)

            # Stacked widget
            self._stack = QStackedWidget()
            self._stack.setStyleSheet("background: #0d1117;")

            self.bar_chart   = BarChartWidget()
            self.wpm_trend   = WPMTrendWidget()
            self.regression  = RegressionChartWidget()
            self.perf_heatmap = PerfHeatmapWidget()
            self.velocity    = VelocityProfileWidget()
            self.efficiency  = EfficiencyWidget()

            # Performance heatmap with mode toggle
            perf_container = QWidget()
            perf_layout = QVBoxLayout(perf_container)
            perf_layout.setContentsMargins(0, 4, 0, 0)
            mode_bar = QHBoxLayout()
            self._btn_tot  = QPushButton("Time-on-Task")
            self._btn_diff = QPushButton("EWIQR Difficulty")
            for btn in (self._btn_tot, self._btn_diff):
                btn.setStyleSheet(\"\"\"
                    QPushButton {
                        background: #161b22; color: #e6edf3;
                        font-size: 9pt; padding: 4px 14px;
                        border: 1px solid #30363d; border-radius: 4px;
                        font-family: 'Segoe UI';
                    }
                    QPushButton:hover { background: #21262d; }
                \"\"\")
                btn.setCursor(Qt.PointingHandCursor)
            self._btn_tot.clicked.connect(lambda: self.perf_heatmap.set_mode('tot'))
            self._btn_diff.clicked.connect(lambda: self.perf_heatmap.set_mode('diff'))
            mode_bar.addWidget(self._btn_tot)
            mode_bar.addWidget(self._btn_diff)
            mode_bar.addStretch()
            perf_layout.addLayout(mode_bar)
            perf_layout.addWidget(self.perf_heatmap, 1)

            self._stack.addWidget(self.bar_chart)    # 0
            self._stack.addWidget(self.wpm_trend)    # 1
            self._stack.addWidget(self.regression)   # 2
            self._stack.addWidget(perf_container)    # 3
            self._stack.addWidget(self.velocity)     # 4
            self._stack.addWidget(self.efficiency)   # 5

            layout.addWidget(self._stack, 1)

            # Select first
            self._on_select(0)

        def _on_select(self, idx):
            self._stack.setCurrentIndex(idx)
            for i, btn in enumerate(self._buttons):
                btn.setChecked(i == idx)

        @property
        def active_index(self):
            return self._stack.currentIndex()


    # ══════════════════════════════════════════════════════════════
    # MAIN WINDOW
    # ══════════════════════════════════════════════════════════════

    class BrailleMainWindow(QMainWindow):
        \"\"\"Main PyQtGraph application window — full redesign.\"\"\"

        def __init__(self):
            super().__init__()
            self.setWindowTitle("Braille Touch Performance Monitor")
            self.setMinimumSize(1400, 860)

            pg.setConfigOptions(background="#0d1117", foreground="#e6edf3",
                                antialias=True)

            palette = QPalette()
            palette.setColor(QPalette.Window,      QColor("#0d1117"))
            palette.setColor(QPalette.WindowText,  QColor("#e6edf3"))
            palette.setColor(QPalette.Base,        QColor("#161b22"))
            palette.setColor(QPalette.Text,        QColor("#e6edf3"))
            palette.setColor(QPalette.Button,      QColor("#161b22"))
            palette.setColor(QPalette.ButtonText,  QColor("#e6edf3"))
            palette.setColor(QPalette.Highlight,   QColor("#58a6ff"))
            palette.setColor(QPalette.HighlightedText, QColor("#0d1117"))
            self.setPalette(palette)
            self.setStyleSheet("QMainWindow { background: #0d1117; }")

            self._build_ui()

            # Snapshot cache
            self._cached_ws    = None
            self._cached_ewiqr = None
            self._cached_welford = None
            self._cached_vt    = None
            self._cached_skip  = None
            self._cached_diff  = None
            self._cached_wb    = None
            self._last_snap    = 0

            # Main update timer — 30fps
            self._timer = QTimer()
            self._timer.timeout.connect(self._update)
            self._timer.start(33)

        def _build_ui(self):
            central = QWidget()
            self.setCentralWidget(central)
            root_layout = QVBoxLayout(central)
            root_layout.setContentsMargins(0, 0, 0, 0)
            root_layout.setSpacing(0)

            # ── Header bar ──────────────────────────────────────
            self._status_bar = StatusBar()
            root_layout.addWidget(self._status_bar)

            # ── Main content area ────────────────────────────────
            content = QWidget()
            content.setStyleSheet("background: #0d1117;")
            content_layout = QVBoxLayout(content)
            content_layout.setContentsMargins(10, 10, 10, 10)
            content_layout.setSpacing(8)

            # ── Upper split: Heatmap | Metrics | Word stats ──────
            upper_splitter = QSplitter(Qt.Horizontal)
            upper_splitter.setHandleWidth(2)
            upper_splitter.setStyleSheet(\"\"\"
                QSplitter::handle { background: #21262d; }
            \"\"\")

            # Heatmap with section label
            heatmap_container = QWidget()
            heatmap_container.setStyleSheet("background: #0d1117;")
            hm_layout = QVBoxLayout(heatmap_container)
            hm_layout.setContentsMargins(0, 0, 0, 0)
            hm_layout.setSpacing(4)
            hm_lbl = QLabel("TOUCH PRESSURE MAP")
            hm_lbl.setStyleSheet(
                "color: #8b949e; font-size: 8pt; font-weight: bold; "
                "font-family: 'Segoe UI'; letter-spacing: 2px; padding: 2px 4px;"
            )
            self._heatmap = HeatmapWidget()
            hm_layout.addWidget(hm_lbl)
            hm_layout.addWidget(self._heatmap, 1)
            upper_splitter.addWidget(heatmap_container)

            # Metrics panel with section label
            metrics_container = QWidget()
            metrics_container.setStyleSheet("background: #0d1117;")
            mc_layout = QVBoxLayout(metrics_container)
            mc_layout.setContentsMargins(0, 0, 0, 0)
            mc_layout.setSpacing(4)
            mc_lbl = QLabel("LIVE METRICS")
            mc_lbl.setStyleSheet(
                "color: #8b949e; font-size: 8pt; font-weight: bold; "
                "font-family: 'Segoe UI'; letter-spacing: 2px; padding: 2px 4px;"
            )
            self._metrics = MetricsPanel()
            mc_layout.addWidget(mc_lbl)
            mc_layout.addWidget(self._metrics, 1)
            upper_splitter.addWidget(metrics_container)

            # Word stats with section label
            ws_container = QWidget()
            ws_container.setStyleSheet("background: #0d1117;")
            ws_layout = QVBoxLayout(ws_container)
            ws_layout.setContentsMargins(0, 0, 0, 0)
            ws_layout.setSpacing(4)
            ws_lbl = QLabel("WORD SCOREBOARD")
            ws_lbl.setStyleSheet(
                "color: #8b949e; font-size: 8pt; font-weight: bold; "
                "font-family: 'Segoe UI'; letter-spacing: 2px; padding: 2px 4px;"
            )
            self._word_stats_panel = WordStatsPanel()
            ws_layout.addWidget(ws_lbl)
            ws_layout.addWidget(self._word_stats_panel, 1)
            upper_splitter.addWidget(ws_container)

            upper_splitter.setSizes([420, 520, 380])
            content_layout.addWidget(upper_splitter, 2)

            # ── Divider ──────────────────────────────────────────
            divider = QFrame()
            divider.setFrameShape(QFrame.HLine)
            divider.setStyleSheet("background: #21262d; max-height: 1px;")
            content_layout.addWidget(divider)

            # ── Lower split: Plot panel | Controls ───────────────
            lower_splitter = QSplitter(Qt.Horizontal)
            lower_splitter.setHandleWidth(2)
            lower_splitter.setStyleSheet("QSplitter::handle { background: #21262d; }")

            # Plot panel
            plot_container = QWidget()
            plot_container.setStyleSheet("background: #0d1117;")
            pc_layout = QVBoxLayout(plot_container)
            pc_layout.setContentsMargins(0, 0, 0, 0)
            pc_layout.setSpacing(4)
            pc_lbl = QLabel("CHARTS")
            pc_lbl.setStyleSheet(
                "color: #8b949e; font-size: 8pt; font-weight: bold; "
                "font-family: 'Segoe UI'; letter-spacing: 2px; padding: 2px 4px;"
            )
            self._plot_panel = PlotPanel()
            pc_layout.addWidget(pc_lbl)
            pc_layout.addWidget(self._plot_panel, 1)
            lower_splitter.addWidget(plot_container)

            # Controls sidebar
            controls = QWidget()
            controls.setFixedWidth(280)
            controls.setStyleSheet(
                "background: #161b22; border-left: 1px solid #21262d;"
            )
            ctrl_layout = QVBoxLayout(controls)
            ctrl_layout.setContentsMargins(12, 12, 12, 12)
            ctrl_layout.setSpacing(12)

            # Threshold group
            thr_lbl = QLabel("TOUCH THRESHOLDS")
            thr_lbl.setStyleSheet(
                "color: #f0883e; font-size: 8pt; font-weight: bold; "
                "font-family: 'Segoe UI'; letter-spacing: 1px;"
            )
            ctrl_layout.addWidget(thr_lbl)

            self._threshold_sliders = []
            for i in range(GRID):
                row_widget = QWidget()
                row_widget.setStyleSheet("background: transparent;")
                row_h = QHBoxLayout(row_widget)
                row_h.setContentsMargins(0, 0, 0, 0)
                row_h.setSpacing(6)

                lbl = QLabel(f"R{i}")
                lbl.setFixedWidth(20)
                lbl.setStyleSheet(
                    "color: #58a6ff; font-family: 'Segoe UI Mono', monospace;"
                    "font-size: 8pt;"
                )
                sl = QSlider(Qt.Horizontal)
                sl.setRange(0, 100)
                sl.setValue(int(ROW_THRESHOLDS[i] * 2))
                sl.setStyleSheet(\"\"\"
                    QSlider::groove:horizontal {
                        background: #21262d; height: 4px; border-radius: 2px;
                    }
                    QSlider::handle:horizontal {
                        background: #f0883e; width: 12px; margin: -4px 0;
                        border-radius: 6px;
                    }
                    QSlider::handle:horizontal:hover {
                        background: #ff9944;
                    }
                \"\"\")
                val_lbl = QLabel(f"{ROW_THRESHOLDS[i]:.1f}")
                val_lbl.setFixedWidth(32)
                val_lbl.setStyleSheet(
                    "color: #e6edf3; font-family: 'Segoe UI Mono', monospace;"
                    "font-size: 8pt;"
                )

                def _on_slider(value, row=i, vlbl=val_lbl):
                    real_val = value / 2.0
                    ROW_THRESHOLDS[row] = real_val
                    vlbl.setText(f"{real_val:.1f}")

                sl.valueChanged.connect(_on_slider)
                row_h.addWidget(lbl)
                row_h.addWidget(sl, 1)
                row_h.addWidget(val_lbl)
                ctrl_layout.addWidget(row_widget)
                self._threshold_sliders.append(sl)

            ctrl_layout.addStretch()

            # Buttons
            btn_edit = QPushButton("✎  Edit Words")
            btn_edit.setStyleSheet(\"\"\"
                QPushButton {
                    background: #161b22; color: #58a6ff;
                    font-size: 10pt; font-weight: bold;
                    padding: 10px; border: 1px solid #30363d;
                    border-radius: 6px; font-family: 'Segoe UI';
                }
                QPushButton:hover { background: #21262d; border-color: #58a6ff; }
            \"\"\")
            btn_edit.setCursor(Qt.PointingHandCursor)
            btn_edit.clicked.connect(self._open_editor)
            ctrl_layout.addWidget(btn_edit)

            btn_end = QPushButton("⏹  End Session")
            btn_end.setStyleSheet(\"\"\"
                QPushButton {
                    background: #161b22; color: #f85149;
                    font-size: 10pt; font-weight: bold;
                    padding: 10px; border: 1px solid #30363d;
                    border-radius: 6px; font-family: 'Segoe UI';
                }
                QPushButton:hover { background: #21262d; border-color: #f85149; }
            \"\"\")
            btn_end.setCursor(Qt.PointingHandCursor)
            btn_end.clicked.connect(self.close)
            ctrl_layout.addWidget(btn_end)

            lower_splitter.addWidget(plot_container)
            lower_splitter.addWidget(controls)

            content_layout.addWidget(lower_splitter, 3)
            root_layout.addWidget(content, 1)

        def _open_editor(self):
            dlg = WordBoundaryEditorQt(self)
            dlg.exec_()
            self._heatmap.refresh_labels()

        def _update(self):
            \"\"\"Main 30fps update loop.\"\"\"
            now = time.time()

            # Tick session timer
            self._status_bar.tick()

            # Read latest frame
            with latest_frame_lk:
                frame = latest_frame.copy()

            # Compute delta + threshold mask
            raw_delta = np.maximum(frame - baseline, 0.0)
            thresh_delta = raw_delta * (raw_delta >= ROW_THRESHOLDS[:, np.newaxis])

            # Update heatmap every frame
            self._heatmap.update_data(thresh_delta)

            # Check for label refresh
            global _cell_labels_dirty
            if _cell_labels_dirty:
                _cell_labels_dirty = False
                self._heatmap.refresh_labels()

            # Throttled snapshots
            if self._cached_ws is None or (now - self._last_snap) >= _SNAPSHOT_INTERVAL:
                self._last_snap = now
                self._cached_diff    = cell_diff.snapshot()
                self._cached_ws      = word_stats.snapshot()
                self._cached_ewiqr   = ewiqr_tracker.snapshot()
                self._cached_welford = welford_per_word.snapshot()
                self._cached_vt      = velocity_tracker.snapshot()
                with word_boundaries_lock:
                    self._cached_wb = {k: list(v) for k, v in word_boundaries.items()}
                self._cached_skip = compute_skip_stats(
                    self._cached_wb, self._cached_ws["word_count"])

                m = perf.snapshot
                self._metrics.update_metrics(
                    m, self._cached_ws, self._cached_vt, self._cached_ewiqr,
                    self._cached_diff, eff_plot.get_avg_efficiency(),
                    wpm_trend.get_current_ema(), list(_cached_finger_wpm),
                    self._cached_skip)

                self._word_stats_panel.update_stats(self._cached_ws, self._cached_skip)

            if self._cached_ws is None:
                return

            # Update active plot only
            idx = self._plot_panel.active_index

            if idx == 0:
                self._plot_panel.bar_chart.update_chart(
                    self._cached_welford, self._cached_ws["word_count"],
                    self._cached_ewiqr, self._cached_wb)

            elif idx == 1:
                x_raw, y_raw, y_ema, y_max = wpm_trend.get_plot_data()
                self._plot_panel.wpm_trend.update_trend(x_raw, y_raw, y_ema, y_max)

            elif idx == 2:
                with word_stats._lock:
                    reg_count = dict(word_stats._regression_count)
                self._plot_panel.regression.update_regressions(
                    reg_count, self._cached_ws["flagged_words"])

            elif idx == 3:
                Z_tot  = np.zeros((GRID, GRID))
                Z_diff = np.zeros((GRID, GRID))
                for r in range(GRID):
                    for e in self._cached_wb.get(r, []):
                        w  = e["word"]
                        wf = self._cached_welford.get(w)
                        if wf:
                            for c in range(e["start"], e["end"] + 1):
                                if 0 <= c < GRID:
                                    Z_tot[r, c] = wf["mean"]
                        ewiqr_pw = self._cached_ewiqr.get("ewiqr_per_word", {})
                        if w in ewiqr_pw:
                            for c in range(e["start"], e["end"] + 1):
                                if 0 <= c < GRID:
                                    Z_diff[r, c] = ewiqr_pw[w]
                self._plot_panel.perf_heatmap.update_perf(Z_tot, Z_diff, self._cached_wb)

            elif idx == 4:
                with vel_profile._lock:
                    vel_snap = list(vel_profile._velocity_history)
                self._plot_panel.velocity.update_velocities(vel_snap)

            elif idx == 5:
                with eff_plot._lock:
                    eff_hist = list(eff_plot.efficiency_history)
                    evt_idx  = list(eff_plot.event_indices)
                cached_tx = eff_plot._cached_trend_x
                cached_ty = eff_plot._cached_trend_y
                self._plot_panel.efficiency.update_efficiency(
                    eff_hist, evt_idx, cached_tx, cached_ty)

            # Check editor request
            if _editor_requested.is_set():
                _editor_requested.clear()
                self._open_editor()

        def closeEvent(self, event):
            \"\"\"Generate session figures, close DataLogger, print report.\"\"\"
            self._timer.stop()

            # ── Generate session figures ────────────────────────────
            try:
                ws_final  = word_stats.snapshot()
                with word_boundaries_lock:
                    wb_final = {k: list(v) for k, v in word_boundaries.items()}
                ewiqr_final = ewiqr_tracker.snapshot()

                x_raw_f, y_raw_f, y_ema_f, _ = wpm_trend.get_plot_data()

                with word_stats._lock:
                    reg_count_f = dict(word_stats._regression_count)

                with vel_profile._lock:
                    vel_hist_f = [np.array(v) for v in vel_profile._velocity_history]

                with eff_plot._lock:
                    eff_hist_f = list(eff_plot.efficiency_history)
                    evt_idx_f  = list(eff_plot.event_indices)

                data_logger.generate_figures(
                    wpm_x=x_raw_f, wpm_raw=y_raw_f, wpm_ema=y_ema_f,
                    regression_count=reg_count_f,
                    flagged_words=ws_final["flagged_words"],
                    vel_history=vel_hist_f if vel_hist_f else [],
                    eff_history=eff_hist_f, eff_indices=evt_idx_f,
                    diff_z=ewiqr_final.get("Z_tot"),
                    wb_snap=wb_final,
                    weight_note=_WEIGHT_NOTE,
                )
            except Exception as e:
                print(f"[DataLogger] Figure generation error: {e}")

            # ── Close DataLogger ──────────────────────────────────
            try:
                data_logger.close()
            except Exception:
                pass

            # ── Print final report ────────────────────────────────
            _print_final_report()

            # ── Session summary dialog ────────────────────────────
            try:
                self._show_summary_dialog()
            except Exception:
                pass

            event.accept()

        def _show_summary_dialog(self):
            \"\"\"Show a styled session summary dialog.\"\"\"
            ws  = word_stats.snapshot()
            vt  = velocity_tracker.snapshot()
            m   = perf.snapshot

            dlg = QDialog(self)
            dlg.setWindowTitle("Session Summary")
            dlg.setMinimumWidth(480)
            dlg.setStyleSheet(\"\"\"
                QDialog { background: #0d1117; }
                QLabel  { color: #e6edf3; font-family: 'Segoe UI'; }
            \"\"\")
            layout = QVBoxLayout(dlg)
            layout.setSpacing(16)
            layout.setContentsMargins(24, 24, 24, 24)

            title = QLabel("Session Complete")
            title.setStyleSheet(
                "color: #e6edf3; font-size: 16pt; font-weight: bold; "
                "font-family: 'Segoe UI';"
            )
            layout.addWidget(title)

            sep = QFrame()
            sep.setFrameShape(QFrame.HLine)
            sep.setStyleSheet("background: #21262d;")
            layout.addWidget(sep)

            grid = QGridLayout()
            grid.setSpacing(10)

            def _stat(label, value, accent="#58a6ff"):
                l = QLabel(label)
                l.setStyleSheet("color: #8b949e; font-size: 9pt;")
                v = QLabel(str(value))
                v.setStyleSheet(f"color: {accent}; font-size: 12pt; font-weight: bold;")
                return l, v

            stats = [
                ("Final WPM",        f"{m['wpm']:.0f}",                "#58a6ff"),
                ("EMA WPM Trend",    f"{wpm_trend.get_current_ema():.1f}", "#58a6ff"),
                ("Total Touches",    str(ws['total_registered']),       "#e6edf3"),
                ("Regressions",      str(ws['total_regressions']),      "#f0883e"),
                ("Hesitation Rate",  f"{ws['hesitation_rate']*100:.0f}%", "#f0883e"),
                ("Consistency",      f"{vt['consistency']:.2f}",        "#3fb950"),
                ("Path Efficiency",  f"{eff_plot.get_avg_efficiency():.2f}", "#3fb950"),
                ("Avg Difficulty",   f"{m['avg_difficulty']:.2f}",      "#f85149"),
                ("Most Touched",     ws['most_touched'] or '—',         "#e6edf3"),
                ("Hardest Word",     ws['hardest_word'] or '—',         "#f85149"),
                ("Data saved to",    "session_data/",                   "#8b949e"),
            ]

            for row_i, (label, value, accent) in enumerate(stats):
                l_w, v_w = _stat(label, value, accent)
                grid.addWidget(l_w, row_i, 0)
                grid.addWidget(v_w, row_i, 1)

            layout.addLayout(grid)

            btn_close = QPushButton("Close")
            btn_close.setStyleSheet(\"\"\"
                QPushButton {
                    background: #161b22; color: #e6edf3;
                    font-size: 10pt; padding: 8px 24px;
                    border: 1px solid #30363d; border-radius: 6px;
                    font-family: 'Segoe UI';
                }
                QPushButton:hover { background: #21262d; }
            \"\"\")
            btn_close.clicked.connect(dlg.accept)
            layout.addWidget(btn_close, 0, Qt.AlignRight)

            dlg.exec_()


    def _print_final_report():
        \"\"\"Print comprehensive session report to console.\"\"\"
        ws = word_stats.snapshot()
        print("\\n═══ FINAL WORD STATS ═══")
        print(f"Total registered touches : {ws['total_registered']}")
        print(f"Most touched word        : {ws['most_touched']}")
        print(f"Hardest word             : {ws['hardest_word']}  "
              f"(avg D={ws['hardest_word_d']:.3f})")
        print(f"Final WPM (sliding window): {perf._wpm_counter.get_wpm()}")
        print(f"Final WPM trend (EMA)    : {wpm_trend.get_current_ema():.1f}")

        print("\\n═══ PER-FINGER STATS (Butterfly) ═══")
        for fi in range(2):
            ft = finger_trackers[fi]
            fi_ws  = ft["word_stats"].snapshot()
            fi_wpm = ft["perf"]._wpm_counter.get_wpm()
            fi_trend = ft["wpm_trend"].get_current_ema()
            fi_vt  = ft["velocity"].snapshot()
            print(f"\\n── Finger {fi} ──")
            print(f"  Touches: {fi_ws['total_registered']}")
            print(f"  WPM: {fi_wpm:.0f}  (EMA trend: {fi_trend:.1f})")
            print(f"  Regressions: {fi_ws['total_regressions']}")
            print(f"  Velocity: {fi_vt['mean_vel']:.1f} cells/s  "
                  f"consistency: {fi_vt['consistency']:.2f}")

        _, y_raw_final, y_ema_final, _ = wpm_trend.get_plot_data()
        if y_ema_final:
            print(f"\\n═══ WPM TREND REPORT  [V-4] ═══")
            print(f"Raw WPM samples          : {len(y_raw_final)}")
            print(f"Peak raw WPM             : {max(y_raw_final):.0f}")
            print(f"Min raw WPM              : {min(y_raw_final):.0f}")
            print(f"Final EMA WPM            : {y_ema_final[-1]:.1f}")
            if len(y_ema_final) > 10:
                avg_ema = sum(y_ema_final) / len(y_ema_final)
                print(f"Session avg EMA WPM      : {avg_ema:.1f}")
                print(f"Peak sustained WPM (EMA) : {max(y_ema_final):.1f}")

        print("\\n═══ REGRESSION REPORT  [M-H1] ═══")
        print(f"Total regressions        : {ws['total_regressions']}")
        print(f"Hesitation rate          : {ws['hesitation_rate']*100:.1f}%")
        if ws["top_regressed"]:
            print("\\n── Top regressed words ──")
            for word, cnt in ws["top_regressed"]:
                flag = "  ⚠ FLAGGED" if word in ws["flagged_words"] else ""
                print(f"  {word:<14}: {cnt} regression(s){flag}")

        final_ewiqr = ewiqr_tracker.snapshot()
        final_welf  = welford_per_word.snapshot()
        print("\\n═══ EWIQR DIFFICULTY REPORT  [M-D2] ═══")
        top5_final = final_ewiqr.get("top5_hardest", [])
        if top5_final:
            print("\\n── Top 5 hardest (by EWIQR) ──")
            for rank, (tw, tewiqr) in enumerate(top5_final, 1):
                tconf = final_ewiqr["confidence_per_word"].get(tw, "?")
                tq1 = final_ewiqr["Q1_per_word"].get(tw, 0)
                tq3 = final_ewiqr["Q3_per_word"].get(tw, 0)
                print(f"  {rank}. {tw:<14}: EWIQR={tewiqr:.3f}s  "
                      f"Q1={tq1:.2f}s  Q3={tq3:.2f}s  [{tconf}]")

        with word_boundaries_lock:
            wb_final = {k: list(v) for k, v in word_boundaries.items()}
        skip_final = compute_skip_stats(wb_final, ws["word_count"])
        print("\\n═══ SKIP STATISTICS REPORT  [M-D3] ═══")
        print(f"Skip rate                : {skip_final['skip_rate']:.1f}%")
        print(f"Skipped words            : {len(skip_final['skipped_words'])} / "
              f"{skip_final.get('total_words', GRID*GRID)}")
        print("\\n── Word counts ──")
        for word, count in sorted(ws["word_count"].items(), key=lambda x: x[1], reverse=True):
            print(f"  {word:<14}: {count}")
        print("\\n── Touch sequence (last 20) ──")
        print("  " + " → ".join(ws["touch_sequence"]))


    def _run_pyqtgraph_ui():
        \"\"\"Entry point for the PyQtGraph real-time UI.\"\"\"
        app = QApplication(sys.argv)
        app.setStyle("Fusion")

        palette = QPalette()
        palette.setColor(QPalette.Window,      QColor("#0d1117"))
        palette.setColor(QPalette.WindowText,  QColor("#e6edf3"))
        palette.setColor(QPalette.Base,        QColor("#161b22"))
        palette.setColor(QPalette.AlternateBase, QColor("#21262d"))
        palette.setColor(QPalette.Text,        QColor("#e6edf3"))
        palette.setColor(QPalette.Button,      QColor("#161b22"))
        palette.setColor(QPalette.ButtonText,  QColor("#e6edf3"))
        palette.setColor(QPalette.Highlight,   QColor("#58a6ff"))
        palette.setColor(QPalette.HighlightedText, QColor("#0d1117"))
        app.setPalette(palette)

        win = BrailleMainWindow()
        win.show()

        try:
            sys.exit(app.exec_())
        except SystemExit:
            pass
        finally:
            try:
                ser.close()
            except Exception:
                pass

# ═══════════════════════════ ENTRY POINT ══════════════════════════
if not _LEGACY_MODE:
    _run_pyqtgraph_ui()
"""
lines = lines[:idx]
lines.append(new_content)

with open(filepath, 'w', encoding='utf-8') as f:
    f.writelines(lines)

print("Replaced successfully!")
