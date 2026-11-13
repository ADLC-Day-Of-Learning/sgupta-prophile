(() => {
  "use strict";

  const SERIES = {
    bt: { label: "Bean temp", axis: "temp", dash: [], width: 2.3, suffix: "°C" },
    et: { label: "Exhaust temp", axis: "temp", dash: [10, 5], width: 1.55, suffix: "°C" },
    ror: { label: "RoR", axis: "ror", dash: [5, 3, 1, 3], width: 1.55, suffix: "°C/min" },
    heat: { label: "Heat", axis: "control", dash: [], width: 1.35, suffix: "%", step: true },
    air: { label: "Air", axis: "control", dash: [2, 4], width: 1.35, suffix: "%", step: true },
  };

  const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
  const finite = value => typeof value === "number" && Number.isFinite(value);
  const timeLabel = seconds => {
    const rounded = Math.max(0, Math.round(seconds));
    return `${String(Math.floor(rounded / 60)).padStart(2, "0")}:${String(rounded % 60).padStart(2, "0")}`;
  };

  function niceRange(values, fallback, includeZero = false) {
    if (!values.length) return fallback;
    let min = Math.min(...values);
    let max = Math.max(...values);
    if (includeZero) { min = Math.min(0, min); max = Math.max(0, max); }
    if (min === max) { min -= 1; max += 1; }
    const pad = (max - min) * 0.08;
    return [min - pad, max + pad];
  }

  function nearestPoint(series, target) {
    if (!series || !series.length) return null;
    let low = 0;
    let high = series.length - 1;
    while (low < high) {
      const mid = Math.floor((low + high) / 2);
      if (series[mid][0] < target) low = mid + 1;
      else high = mid;
    }
    const candidates = [series[low], series[Math.max(0, low - 1)], series[Math.min(series.length - 1, low + 1)]];
    return candidates.filter(point => point && finite(point[1])).sort((a, b) => Math.abs(a[0] - target) - Math.abs(b[0] - target))[0] || null;
  }

  class OverlayChart {
    constructor(canvas, tooltip, empty, summary) {
      this.canvas = canvas;
      this.ctx = canvas.getContext("2d");
      this.tooltip = tooltip;
      this.empty = empty;
      this.summary = summary;
      this.profiles = [];
      this.visibility = { bt: true, et: true, ror: true, heat: true, air: true, events: true };
      this.hover = null;
      this.highlightId = null;
      this.theme = null;
      this.onHoverProfile = () => {};
      this.bounds = null;
      this.resizeObserver = new ResizeObserver(() => this.render());
      this.resizeObserver.observe(canvas.parentElement);
      canvas.addEventListener("mousemove", event => this.onPointer(event));
      canvas.addEventListener("mouseleave", () => { this.hover = null; this.tooltip.hidden = true; this.setHighlight(null); this.render(); });
    }

    setData(profiles, visibility) {
      this.profiles = profiles;
      this.visibility = { ...visibility };
      this.hover = null;
      this.highlightId = null;
      this.onHoverProfile(null);
      this.tooltip.hidden = true;
      this.updateSummary();
      this.render();
    }

    enabledProfiles() { return this.profiles.filter(profile => profile.enabled); }

    isDarkMode() {
      if (this.theme === "dark") return true;
      if (this.theme === "light") return false;
      return (
        document.documentElement.getAttribute("data-theme") === "dark" ||
        document.body?.getAttribute("data-theme") === "dark"
      );
    }

    setTheme(theme) {
      this.theme = theme;
      this.render();
    }

    setHighlight(id) {
      if (this.highlightId === id) return;
      this.highlightId = id;
      this.onHoverProfile(id);
      this.render();
    }

    updateSummary() {
      const profiles = this.enabledProfiles();
      if (!profiles.length) {
        this.summary.textContent = "No roast profiles are selected.";
        return;
      }
      const visible = Object.entries(this.visibility).filter(([, on]) => on).map(([key]) => key === "events" ? "event pins" : SERIES[key].label);
      this.summary.textContent = `Comparing ${profiles.length} profiles: ${profiles.map(p => p.displayName).join(", ")}. Visible: ${visible.join(", ")}.`;
    }

    calculateRanges(profiles) {
      let maxTime = 60;
      const tempValues = [];
      const rorValues = [];
      for (const profile of profiles) {
        for (const [key, definition] of Object.entries(SERIES)) {
          if (!this.visibility[key]) continue;
          for (const point of profile.series[key] || []) {
            if (finite(point[0])) maxTime = Math.max(maxTime, point[0]);
            if (finite(point[1])) {
              if (definition.axis === "temp") tempValues.push(point[1]);
              if (definition.axis === "ror") rorValues.push(point[1]);
            }
          }
        }
        if (this.visibility.events) {
          for (const event of profile.events || []) if (finite(event.time)) maxTime = Math.max(maxTime, event.time);
        }
      }
      const nonNegativeRor = rorValues.filter(value => value >= 0);
      const maximumRor = nonNegativeRor.length ? Math.max(...nonNegativeRor) : 30;
      return {
        time: [0, maxTime * 1.025],
        temp: niceRange(tempValues, [0, 250]),
        ror: [0, Math.max(1, maximumRor)],
        control: [0, 100],
      };
    }

    render() {
      const rect = this.canvas.getBoundingClientRect();
      if (!rect.width || !rect.height) return;
      const dpr = window.devicePixelRatio || 1;
      const pixelWidth = Math.round(rect.width * dpr);
      const pixelHeight = Math.round(rect.height * dpr);
      if (this.canvas.width !== pixelWidth || this.canvas.height !== pixelHeight) {
        this.canvas.width = pixelWidth;
        this.canvas.height = pixelHeight;
      }
      const ctx = this.ctx;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, rect.width, rect.height);

      const profiles = this.enabledProfiles();
      this.empty.hidden = profiles.length > 0;
      if (!profiles.length) { this.bounds = null; return; }

      const compact = rect.width < 650;
      const margin = { top: 30, left: compact ? 83 : 112, right: compact ? 52 : 64, bottom: 52 };
      const plot = { x: margin.left, y: margin.top, w: rect.width - margin.left - margin.right, h: rect.height - margin.top - margin.bottom };
      const ranges = this.calculateRanges(profiles);
      const x = value => plot.x + (value - ranges.time[0]) / (ranges.time[1] - ranges.time[0]) * plot.w;
      const yFor = (value, axis) => {
        const range = ranges[axis];
        return plot.y + plot.h - (value - range[0]) / (range[1] - range[0]) * plot.h;
      };
      this.bounds = { plot, ranges, x, yFor, width: rect.width, height: rect.height };

      this.drawAxes(ctx, plot, ranges, x, yFor, compact);
      ctx.save();
      ctx.beginPath(); ctx.rect(plot.x, plot.y, plot.w, plot.h); ctx.clip();
      for (const profile of profiles) {
        ctx.save();
        if (this.highlightId && profile.id !== this.highlightId) ctx.globalAlpha = 0.12;
        for (const [key, definition] of Object.entries(SERIES)) {
          if (this.visibility[key]) this.drawSeries(ctx, profile.series[key], definition, profile.color, x, value => yFor(value, definition.axis));
        }
        ctx.restore();
      }
      ctx.restore();
      if (this.visibility.events) {
        for (const profile of profiles) {
          ctx.save();
          if (this.highlightId && profile.id !== this.highlightId) ctx.globalAlpha = 0.12;
          this.drawEvents(ctx, [profile], x, value => yFor(value, "temp"), plot);
          ctx.restore();
        }
      }
      if (this.hover) this.drawHover(ctx);
    }

    drawAxes(ctx, plot, ranges, x, yFor, compact) {
      const isDark = this.isDarkMode();
      ctx.font = `${compact ? 10 : 11}px ui-sans-serif, system-ui, sans-serif`;
      ctx.textBaseline = "middle";
      ctx.lineWidth = 1;
      for (let i = 0; i <= 5; i++) {
        const ratio = i / 5;
        const py = plot.y + plot.h * ratio;
        ctx.strokeStyle = i === 5 ? (isDark ? "#384558" : "#cfc9bf") : (isDark ? "#242e3f" : "#e9e5dd");
        ctx.beginPath(); ctx.moveTo(plot.x, py); ctx.lineTo(plot.x + plot.w, py); ctx.stroke();
        const value = ranges.temp[1] - (ranges.temp[1] - ranges.temp[0]) * ratio;
        ctx.fillStyle = isDark ? "#94a3b8" : "#6d7482"; ctx.textAlign = "right"; ctx.fillText(`${Math.round(value)}°`, plot.x - 9, py);
      }
      for (let i = 0; i <= 6; i++) {
        const value = ranges.time[1] * i / 6;
        const px = x(value);
        ctx.strokeStyle = isDark ? "#242e3f" : "#eeeae3";
        ctx.beginPath(); ctx.moveTo(px, plot.y); ctx.lineTo(px, plot.y + plot.h); ctx.stroke();
        ctx.fillStyle = isDark ? "#94a3b8" : "#6d7482"; ctx.textAlign = "center"; ctx.fillText(timeLabel(value), px, plot.y + plot.h + 19);
      }
      for (let i = 0; i <= 5; i++) {
        const ratio = i / 5;
        const py = plot.y + plot.h * ratio;
        const ror = ranges.ror[1] - (ranges.ror[1] - ranges.ror[0]) * ratio;
        const control = 100 - 100 * ratio;
        ctx.textAlign = "left";
        ctx.fillStyle = isDark ? "#60a5fa" : "#355c9e"; ctx.fillText(ror.toFixed(Math.abs(ror) < 10 ? 1 : 0), plot.x + plot.w + 9, py);
        ctx.textAlign = "right";
        ctx.fillStyle = isDark ? "#f59e0b" : "#8b6b3f"; ctx.fillText(`${Math.round(control)}`, plot.x - (compact ? 42 : 55), py);
      }
      ctx.font = `700 ${compact ? 9 : 10}px ui-sans-serif, system-ui, sans-serif`;
      ctx.fillStyle = isDark ? "#94a3b8" : "#687083";
      ctx.textAlign = "left"; ctx.fillText("TEMP °C", plot.x, 13);
      ctx.fillStyle = isDark ? "#60a5fa" : "#355c9e"; ctx.textAlign = "right"; ctx.fillText("ROR", plot.x + plot.w + 34, 13);
      ctx.fillStyle = isDark ? "#f59e0b" : "#8b6b3f"; ctx.textAlign = "left"; ctx.fillText("AIR / HEAT %", compact ? 2 : 8, compact ? 24 : 13);
      ctx.fillStyle = isDark ? "#94a3b8" : "#687083"; ctx.textAlign = "center"; ctx.fillText("TIME FROM CHARGE", plot.x + plot.w / 2, plot.y + plot.h + 42);
    }

    drawSeries(ctx, points, definition, color, x, y) {
      if (!points || points.length < 2) return;
      ctx.save();
      ctx.strokeStyle = color;
      ctx.lineWidth = definition.width;
      ctx.setLineDash(definition.dash);
      ctx.lineJoin = "round";
      ctx.lineCap = "round";
      ctx.beginPath();
      let active = false;
      let previous = null;
      for (const point of points) {
        if (!finite(point[0]) || !finite(point[1])) { active = false; previous = null; continue; }
        const px = x(point[0]);
        const py = y(point[1]);
        if (!active) { ctx.moveTo(px, py); active = true; }
        else if (definition.step && previous) { ctx.lineTo(px, previous[1]); ctx.lineTo(px, py); }
        else ctx.lineTo(px, py);
        previous = [px, py];
      }
      ctx.stroke();
      ctx.restore();
    }

    drawEvents(ctx, profiles, x, y, plot) {
      let sequence = 0;
      for (const profile of profiles) {
        for (const event of profile.events || []) {
          if (!finite(event.time) || !finite(event.bt)) continue;
          const px = x(event.time);
          const py = y(event.bt);
          const offset = 23 + (sequence++ % 3) * 18;
          const labelY = clamp(py - offset, plot.y + 10, plot.y + plot.h - 10);
          ctx.save();
          ctx.strokeStyle = profile.color; ctx.fillStyle = profile.color; ctx.lineWidth = 1;
          ctx.beginPath(); ctx.moveTo(px, py); ctx.lineTo(px, labelY); ctx.stroke();
          ctx.beginPath(); ctx.arc(px, py, 3.5, 0, Math.PI * 2); ctx.fill();
          ctx.font = "700 8px ui-sans-serif, system-ui, sans-serif";
          const width = ctx.measureText(event.abbreviation).width + 8;
          ctx.fillRect(px - width / 2, labelY - 7, width, 14);
          ctx.fillStyle = "#fff"; ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.fillText(event.abbreviation, px, labelY);
          ctx.restore();
        }
      }
    }

    drawHover(ctx) {
      if (!this.bounds || !this.hover) return;
      const isDark = this.isDarkMode();
      const { plot, x } = this.bounds;
      const px = x(this.hover.time);
      ctx.save();
      ctx.strokeStyle = isDark ? "rgba(226, 232, 240, .45)" : "rgba(29, 39, 59, .42)"; ctx.lineWidth = 1; ctx.setLineDash([3, 3]);
      ctx.beginPath(); ctx.moveTo(px, plot.y); ctx.lineTo(px, plot.y + plot.h); ctx.stroke();
      ctx.restore();
    }

    onPointer(event) {
      if (!this.bounds || !this.enabledProfiles().length) return;
      const rect = this.canvas.getBoundingClientRect();
      const mx = event.clientX - rect.left;
      const my = event.clientY - rect.top;
      const { plot, ranges, x, yFor } = this.bounds;
      if (mx < plot.x || mx > plot.x + plot.w || my < plot.y || my > plot.y + plot.h) {
        this.hover = null; this.tooltip.hidden = true; this.setHighlight(null); this.render(); return;
      }
      const time = ranges.time[0] + (mx - plot.x) / plot.w * (ranges.time[1] - ranges.time[0]);
      let hoveredEvent = null;
      if (this.visibility.events) {
        for (const profile of this.enabledProfiles()) {
          for (const item of profile.events || []) {
            if (!finite(item.time) || !finite(item.bt)) continue;
            const distance = Math.hypot(x(item.time) - mx, yFor(item.bt, "temp") - my);
            if (distance <= 11 && (!hoveredEvent || distance < hoveredEvent.distance)) hoveredEvent = { profile, item, distance };
          }
        }
      }
      let hit = hoveredEvent ? { profile: hoveredEvent.profile, distance: hoveredEvent.distance } : null;
      for (const profile of this.enabledProfiles()) {
        for (const [key, definition] of Object.entries(SERIES)) {
          if (!this.visibility[key]) continue;
          const point = nearestPoint(profile.series[key], time);
          if (!point || Math.abs(x(point[0]) - mx) > 14) continue;
          const distance = Math.abs(yFor(point[1], definition.axis) - my);
          if (distance <= 12 && (!hit || distance < hit.distance)) hit = { profile, distance };
        }
      }
      this.setHighlight(hit?.profile.id || null);
      this.hover = { time: hoveredEvent ? hoveredEvent.item.time : time };
      this.showTooltip(hoveredEvent, time, mx, my);
      this.render();
    }

    showTooltip(eventHit, time, mx, my) {
      const node = this.tooltip;
      node.replaceChildren();
      const title = document.createElement("div");
      title.className = "tooltip-title";
      if (eventHit) {
        title.textContent = `${eventHit.item.name} · ${timeLabel(eventHit.item.time)}`;
        node.append(title);
        const profile = document.createElement("div"); profile.className = "tooltip-profile"; profile.textContent = eventHit.profile.displayName; node.append(profile);
        for (const [label, value, suffix] of [["Bean temp", eventHit.item.bt, "°C"], ["Exhaust temp", eventHit.item.et, "°C"]]) {
          if (finite(value)) this.tooltipRow(node, label, `${value.toFixed(1)} ${suffix}`);
        }
      } else {
        title.textContent = timeLabel(time); node.append(title);
        for (const profile of this.enabledProfiles()) {
          const values = [];
          for (const [key, definition] of Object.entries(SERIES)) {
            if (!this.visibility[key]) continue;
            const point = nearestPoint(profile.series[key], time);
            if (point) values.push([definition.label, `${point[1].toFixed(1)} ${definition.suffix}`]);
          }
          if (!values.length) continue;
          const profileNode = document.createElement("div"); profileNode.className = "tooltip-profile"; profileNode.textContent = profile.displayName; profileNode.style.color = profile.color; node.append(profileNode);
          for (const [label, value] of values) this.tooltipRow(node, label, value);
        }
      }
      node.hidden = false;
      const wrap = this.canvas.parentElement.getBoundingClientRect();
      const tooltipRect = node.getBoundingClientRect();
      const left = mx + 14 + tooltipRect.width > wrap.width ? mx - tooltipRect.width - 14 : mx + 14;
      const top = clamp(my - 10, 6, wrap.height - tooltipRect.height - 6);
      node.style.left = `${Math.max(6, left)}px`;
      node.style.top = `${top}px`;
    }

    tooltipRow(parent, label, value) {
      const row = document.createElement("div"); row.className = "tooltip-row";
      const left = document.createElement("span"); left.textContent = label;
      const right = document.createElement("span"); right.textContent = value;
      row.append(left, right); parent.append(row);
    }
  }

  window.RoastOverlayChart = OverlayChart;
})();
