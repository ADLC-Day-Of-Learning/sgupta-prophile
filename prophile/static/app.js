(() => {
  "use strict";

  const MAX_FILE_BYTES = 5 * 1024 * 1024;
  const profiles = [];
  const duplicateKeys = new Set();
  let colorSequence = 0;

  const elements = typeof document !== "undefined" ? {
    input: document.querySelector("#file-input"),
    status: document.querySelector("#status"),
    messages: document.querySelector("#messages"),
    groups: document.querySelector("#bean-groups"),
    filterEmpty: document.querySelector("#filter-empty"),
    gridEmpty: document.querySelector("#grid-empty"),
    tableScroll: document.querySelector("#table-scroll"),
    rows: document.querySelector("#profile-rows"),
    legend: document.querySelector("#profile-legend"),
    controls: document.querySelector("#curve-controls"),
    selectAll: document.querySelector("#select-all"),
    selectNone: document.querySelector("#select-none"),
    clearAll: document.querySelector("#clear-all"),
    dateRangeFilter: document.querySelector("#date-range-filter"),
    dateStart: document.querySelector("#date-start"),
    dateEnd: document.querySelector("#date-end"),
    notesTooltip: document.querySelector("#notes-tooltip"),
    themeToggle: document.querySelector("#theme-toggle"),
  } : {};

  const chart = typeof document !== "undefined" && typeof window !== "undefined" && window.RoastOverlayChart ? new window.RoastOverlayChart(
    document.querySelector("#chart"),
    document.querySelector("#tooltip"),
    document.querySelector("#chart-empty"),
    document.querySelector("#chart-summary"),
  ) : null;
  if (chart) {
    chart.onHoverProfile = id => highlightRow(id);
  }

  function highlightRow(id) {
    for (const row of elements.rows.querySelectorAll("tr[data-profile-id]")) {
      row.classList.toggle("profile-highlight", id !== null && row.dataset.profileId === id);
    }
  }

  const PROFILE_PALETTE = [
    "#3d6f8e", "#b45f4b", "#4f7a5b", "#80649a", "#b08a3e", "#3f7f7a",
    "#a5526b", "#c0783e", "#5966a1", "#76824a", "#397d9a", "#8d5a75",
  ];

  function adjustColor(hex, amount) {
    const value = Number.parseInt(hex.slice(1), 16);
    const adjust = channel => Math.max(0, Math.min(255, channel + amount));
    const red = adjust(value >> 16);
    const green = adjust((value >> 8) & 255);
    const blue = adjust(value & 255);
    return `#${[red, green, blue].map(channel => channel.toString(16).padStart(2, "0")).join("")}`;
  }

  function profileColor(index) {
    const base = PROFILE_PALETTE[index % PROFILE_PALETTE.length];
    const cycle = Math.floor(index / PROFILE_PALETTE.length) % 3;
    return cycle === 0 ? base : adjustColor(base, cycle === 1 ? 20 : -18);
  }

  function visibility() {
    return Object.fromEntries([...elements.controls.querySelectorAll("input[data-series]")].map(input => [input.dataset.series, input.checked]));
  }

  function updateChart() {
    if (chart) chart.setData(profiles, visibility());
    renderFilters();
    renderLegend();
  }

  function getTodayIso() {
    const now = new Date();
    const year = now.getFullYear();
    const month = String(now.getMonth() + 1).padStart(2, "0");
    const day = String(now.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
  }

  function profileDate(profile) {
    if (!profile) return null;
    if (profile.roastisodate && /^\d{4}-\d{2}-\d{2}$/.test(profile.roastisodate)) {
      return profile.roastisodate;
    }
    if (profile.roastDate && /^\d{4}-\d{2}-\d{2}$/.test(profile.roastDate)) {
      return profile.roastDate;
    }
    if (profile.date && /^\d{4}-\d{2}-\d{2}$/.test(profile.date)) {
      return profile.date;
    }
    const match = (profile.filename || "").match(/(?:^|[^0-9])(\d{2,4})-(\d{2})-(\d{2})(?:[^0-9]|$)/);
    if (match) {
      let year = Number.parseInt(match[1], 10);
      if (year < 100) year += 2000;
      const month = match[2];
      const day = match[3];
      return `${year}-${month}-${day}`;
    }
    return null;
  }

  function updateDateBounds() {
    if (!elements.dateStart || !elements.dateEnd) return;
    const today = getTodayIso();
    const allDates = profiles.map(p => profileDate(p)).filter(Boolean).sort();
    if (allDates.length) {
      const oldest = allDates[0];
      const newest = allDates[allDates.length - 1];
      const maxDate = newest > today ? newest : today;
      elements.dateStart.min = oldest;
      elements.dateStart.max = maxDate;
      elements.dateEnd.min = oldest;
      elements.dateEnd.max = maxDate;
    } else {
      if (elements.dateStart.removeAttribute) elements.dateStart.removeAttribute("min");
      else delete elements.dateStart.min;
      if (elements.dateEnd.removeAttribute) elements.dateEnd.removeAttribute("min");
      else delete elements.dateEnd.min;
      elements.dateStart.max = today;
      elements.dateEnd.max = today;
    }
  }

  function updateDateRangeFromSelection() {
    if (!elements.dateStart || !elements.dateEnd) return;
    const selected = profiles.filter(p => p.enabled);
    if (!selected.length) {
      const today = getTodayIso();
      elements.dateStart.value = today;
      elements.dateEnd.value = today;
      return;
    }
    const dates = selected
      .map(p => profileDate(p))
      .filter(Boolean)
      .sort();
    if (dates.length) {
      elements.dateStart.value = dates[0];
      elements.dateEnd.value = dates[dates.length - 1];
    }
  }

  function applyDateRangeFilter() {
    if (!elements.dateStart || !elements.dateEnd) return;
    const start = elements.dateStart.value;
    const end = elements.dateEnd.value;
    if (start && !/^\d{4}-\d{2}-\d{2}$/.test(start)) return;
    if (end && !/^\d{4}-\d{2}-\d{2}$/.test(end)) return;
    if (!start && !end) return;

    for (const profile of profiles) {
      const d = profileDate(profile);
      if (!d) continue;
      let inRange = true;
      if (start && end && start > end) {
        inRange = false;
      } else {
        if (start && d < start) inRange = false;
        if (end && d > end) inRange = false;
      }
      profile.enabled = inRange;
    }
    renderProfiles();
    updateChart();
  }

  function setStatus(message) { if (elements.status) elements.status.textContent = message; }

  function addMessage(message, type = "warning") {
    const item = document.createElement("div");
    item.className = `message ${type === "error" ? "error" : ""}`;
    item.textContent = message;
    elements.messages.append(item);
  }

  function formatDuration(seconds) {
    if (typeof seconds !== "number" || !Number.isFinite(seconds)) return null;
    const rounded = Math.max(0, Math.round(seconds));
    return `${String(Math.floor(rounded / 60)).padStart(2, "0")}:${String(rounded % 60).padStart(2, "0")}`;
  }

  function phaseText(phase) {
    const duration = phase ? formatDuration(phase.seconds) : null;
    if (!duration) return "—";
    return typeof phase.percent === "number" ? `${duration} · ${Math.round(phase.percent)}%` : duration;
  }

  function eventTemperature(profile, key) {
    const event = (profile.events || []).find(item => item.key === key);
    return event && typeof event.bt === "number" && Number.isFinite(event.bt) ? `${event.bt.toFixed(1)} °C` : "—";
  }

  function weightText(value, unit) {
    return typeof value === "number" && Number.isFinite(value) ? `${value.toFixed(1)}${unit ? ` ${unit}` : ""}` : "—";
  }

  function densityText(value) {
    return typeof value === "number" && Number.isFinite(value) ? `${value.toFixed(1)} g/L` : "—";
  }

  function greenWeightDensityText(weights, density) {
    const greenWeight = weightText(weights?.green, weights?.unit);
    const hasDensity = typeof density === "number" && Number.isFinite(density);
    if (greenWeight === "—" && !hasDensity) return "—";
    return `${greenWeight}${hasDensity ? ` (${densityText(density)})` : ""}`;
  }

  function finalWeightText(weights) {
    const finalWeight = weightText(weights?.final, weights?.unit);
    const hasLoss = typeof weights?.lossPercent === "number" && Number.isFinite(weights.lossPercent);
    if (finalWeight === "—" && !hasLoss) return "—";
    return `${finalWeight}${hasLoss ? ` (-${weights.lossPercent.toFixed(1)}%)` : ""}`;
  }

  function notesFor(profile) {
    const roastNotes = profile.notes?.roast
      ?.replace(/(?:\\n|\/n|\r?\n)+/g, " ")
      .replace(/\s+/g, " ")
      .trim();
    return [
      ["Roast notes", roastNotes],
      ["Cupping notes", profile.notes?.cupping?.trim()],
    ].filter(([, value]) => value);
  }

  function positionNotesTooltip(clientX, clientY) {
    const tooltip = elements.notesTooltip;
    const gap = 14;
    const bounds = tooltip.getBoundingClientRect();
    const left = clientX + gap + bounds.width > window.innerWidth ? clientX - bounds.width - gap : clientX + gap;
    const top = Math.max(8, Math.min(clientY + gap, window.innerHeight - bounds.height - 8));
    tooltip.style.left = `${Math.max(8, Math.min(left, window.innerWidth - bounds.width - 8))}px`;
    tooltip.style.top = `${top}px`;
  }

  function showNotesTooltip(profile, clientX, clientY) {
    const notes = notesFor(profile);
    if (!notes.length) return;
    const tooltip = elements.notesTooltip;
    tooltip.replaceChildren();
    const title = document.createElement("strong"); title.textContent = profile.displayName; tooltip.append(title);
    for (const [label, value] of notes) {
      const heading = document.createElement("span"); heading.className = "notes-label"; heading.textContent = label; tooltip.append(heading);
      const content = document.createElement("p"); content.textContent = value; tooltip.append(content);
    }
    tooltip.hidden = false;
    positionNotesTooltip(clientX, clientY);
  }

  function hideNotesTooltip() {
    if (elements.notesTooltip) elements.notesTooltip.hidden = true;
  }

  function renderProfiles() {
    hideNotesTooltip();
    if (!elements.gridEmpty || !elements.tableScroll || !elements.rows) return;
    const selected = profiles.filter(profile => profile.enabled);
    elements.gridEmpty.hidden = selected.length > 0;
    elements.tableScroll.hidden = selected.length === 0;
    elements.rows.replaceChildren();
    for (const profile of selected) {
      const row = document.createElement("tr");
      row.dataset.profileId = profile.id;
      row.addEventListener("mouseenter", () => chart.setHighlight(profile.id));
      row.addEventListener("mouseleave", () => chart.setHighlight(null));

      const name = document.createElement("td"); name.className = "profile-name"; name.textContent = profile.displayName; name.style.color = profile.color;

      const greenWeight = document.createElement("td"); greenWeight.className = "weight-value"; greenWeight.textContent = greenWeightDensityText(profile.weights, profile.density);
      const finalWeight = document.createElement("td"); finalWeight.className = "weight-value"; finalWeight.textContent = finalWeightText(profile.weights);
      const chargeTemp = document.createElement("td"); chargeTemp.className = "temperature-value"; chargeTemp.textContent = eventTemperature(profile, "charge");
      const dropTemp = document.createElement("td"); dropTemp.className = "temperature-value"; dropTemp.textContent = eventTemperature(profile, "drop");
      const drying = document.createElement("td"); drying.className = "phase-value phase-drying"; drying.textContent = phaseText(profile.phases.drying);
      const browning = document.createElement("td"); browning.className = "phase-value phase-browning"; browning.textContent = phaseText(profile.phases.browning);
      const development = document.createElement("td"); development.className = "phase-value phase-development"; development.textContent = phaseText(profile.phases.development);

      const noteSections = notesFor(profile);
      if (noteSections.length) {
        row.classList.add("has-notes");
        row.tabIndex = 0;
        row.setAttribute("aria-describedby", "notes-tooltip");
        row.addEventListener("mouseenter", event => showNotesTooltip(profile, event.clientX, event.clientY));
        row.addEventListener("mousemove", event => positionNotesTooltip(event.clientX, event.clientY));
        row.addEventListener("mouseleave", hideNotesTooltip);
        row.addEventListener("focus", () => {
          const bounds = row.getBoundingClientRect();
          showNotesTooltip(profile, bounds.left + bounds.width / 2, bounds.bottom);
        });
        row.addEventListener("blur", hideNotesTooltip);
      }

      const actions = document.createElement("td");
      const remove = document.createElement("button"); remove.type = "button"; remove.className = "remove-button"; remove.textContent = "×";
      remove.title = `Remove ${profile.displayName} from comparison`; remove.setAttribute("aria-label", remove.title);
      remove.addEventListener("click", () => { profile.enabled = false; updateDateRangeFromSelection(); renderProfiles(); updateChart(); }); actions.append(remove);
      row.append(name, greenWeight, finalWeight, chargeTemp, dropTemp, drying, browning, development, actions);
      elements.rows.append(row);
    }
  }

  function batchLabel(profile) {
    const match = profile.filename.match(/^(\d{2,4}-\d{2}-\d{2})_.+?_batch_(\d+)(_glitch)?\.alog$/i);
    return match ? `${match[1]} · Batch ${match[2]}${match[3] ? " · glitch" : ""}` : profile.displayName;
  }

  function renderFilters() {
    if (!elements.groups || !elements.filterEmpty) return;
    elements.groups.replaceChildren();
    elements.filterEmpty.hidden = profiles.length > 0;
    const groups = new Map();
    for (const profile of profiles) {
      const bean = profile.bean || "Unknown bean";
      const key = bean.toLocaleLowerCase();
      if (!groups.has(key)) groups.set(key, { bean, items: [] });
      groups.get(key).items.push(profile);
    }
    for (const { bean, items } of [...groups.values()].sort((a, b) => a.bean.localeCompare(b.bean))) {
      const group = document.createElement("section"); group.className = "bean-group";
      const heading = document.createElement("label"); heading.className = "bean-heading";
      const groupCheck = document.createElement("input"); groupCheck.type = "checkbox";
      groupCheck.checked = items.every(profile => profile.enabled);
      groupCheck.indeterminate = !groupCheck.checked && items.some(profile => profile.enabled);
      groupCheck.setAttribute("aria-label", `Select all batches of ${bean}`);
      groupCheck.addEventListener("change", () => {
        items.forEach(profile => { profile.enabled = groupCheck.checked; });
        updateDateRangeFromSelection();
        renderProfiles(); updateChart();
      });
      const title = document.createElement("strong"); title.textContent = bean;
      const count = document.createElement("small"); count.textContent = String(items.length);
      heading.append(groupCheck, title, count); group.append(heading);
      for (const profile of items) {
        const item = document.createElement("div"); item.className = "batch-item";
        const label = document.createElement("label");
        const check = document.createElement("input"); check.type = "checkbox"; check.checked = profile.enabled;
        check.setAttribute("aria-label", `Show ${profile.displayName}`);
        check.addEventListener("change", () => {
          profile.enabled = check.checked;
          updateDateRangeFromSelection();
          renderProfiles(); updateChart();
        });
        const name = document.createElement("span"); name.textContent = batchLabel(profile);
        name.title = profile.displayName;
        name.style.color = profile.color;
        label.append(check, name);
        const remove = document.createElement("button"); remove.type = "button";
        remove.className = "remove-button"; remove.textContent = "×";
        remove.title = `Remove ${profile.displayName}`; remove.setAttribute("aria-label", remove.title);
        remove.addEventListener("click", () => removeProfile(profile.id));
        item.append(label, remove); group.append(item);
      }
      elements.groups.append(group);
    }
  }

  function renderLegend() {
    if (!elements.legend) return;
    elements.legend.replaceChildren();
    for (const profile of profiles.filter(profile => profile.enabled)) {
      const key = document.createElement("span"); key.className = "profile-key";
      const dot = document.createElement("i"); dot.style.backgroundColor = profile.color;
      const label = document.createElement("span"); label.textContent = profile.displayName;
      key.append(dot, label); elements.legend.append(key);
    }
  }

  function removeProfile(id) {
    const index = profiles.findIndex(profile => profile.id === id);
    if (index < 0) return;
    duplicateKeys.delete(profiles[index].duplicateKey);
    profiles.splice(index, 1);
    updateDateBounds();
    updateDateRangeFromSelection();
    renderProfiles(); updateChart();
    setStatus(profiles.length ? `${profiles.length} profile${profiles.length === 1 ? "" : "s"} loaded.` : "");
  }

  function clearAll() {
    profiles.splice(0); duplicateKeys.clear();
    if (elements.messages) elements.messages.replaceChildren();
    updateDateBounds();
    updateDateRangeFromSelection();
    renderProfiles(); updateChart(); setStatus("");
  }

  async function importFiles(fileList) {
    const files = [...fileList];
    if (!files.length) return;
    elements.messages.replaceChildren();
    const accepted = [];
    for (const file of files) {
      const key = `${file.name}::${file.size}`;
      if (!file.name.toLowerCase().endsWith(".alog")) { addMessage(`${file.name}: unsupported extension; choose an .alog file.`, "error"); continue; }
      if (file.size > MAX_FILE_BYTES) { addMessage(`${file.name}: file exceeds the 5 MB limit.`, "error"); continue; }
      if (file.size === 0) { addMessage(`${file.name}: file is empty.`, "error"); continue; }
      if (duplicateKeys.has(key)) { addMessage(`${file.name}: already loaded.`); continue; }
      duplicateKeys.add(key);
      accepted.push({ file, key });
    }
    if (!accepted.length) { setStatus("No new profiles were loaded."); return; }

    setStatus(`Loading ${accepted.length} profile${accepted.length === 1 ? "" : "s"}…`);
    let loaded = 0;
    for (const { file, key } of accepted) {
      const id = globalThis.crypto?.randomUUID?.() || `profile-${Date.now()}-${Math.random().toString(16).slice(2)}`;
      try {
        const response = await fetch("/api/parse", {
          method: "POST",
          headers: { "Content-Type": "text/plain; charset=utf-8", "X-Filename": encodeURIComponent(file.name), "X-Profile-Id": id },
          body: file,
        });
        let payload;
        try { payload = await response.json(); }
        catch { throw new Error("The server returned an unreadable response."); }
        if (!response.ok) throw new Error(payload.error || "The profile could not be imported.");
        payload.enabled = true;
        payload.color = profileColor(colorSequence++);
        payload.duplicateKey = key;
        profiles.push(payload);
        loaded += 1;
        for (const warning of payload.warnings || []) addMessage(`${file.name}: ${warning}`);
      } catch (error) {
        duplicateKeys.delete(key);
        const networkMessage = error instanceof TypeError ? "server/network failure." : error.message;
        addMessage(`${file.name}: ${networkMessage}`, "error");
      }
    }
    updateDateBounds();
    updateDateRangeFromSelection();
    renderProfiles(); updateChart();
    setStatus(`${loaded} profile${loaded === 1 ? "" : "s"} loaded${accepted.length !== loaded ? `; ${accepted.length - loaded} failed` : ""}.`);
    elements.input.value = "";
  }

  async function loadLocalProfiles() {
    try {
      const response = await fetch("/api/local-profiles");
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Could not load local profiles.");
      for (const profile of result.profiles) {
        if (duplicateKeys.has(`${profile.filename}::${profile.fileSize}`)) continue;
        profile.enabled = false;
        profile.color = profileColor(colorSequence++);
        profile.duplicateKey = `${profile.filename}::${profile.fileSize}`;
        duplicateKeys.add(profile.duplicateKey);
        profiles.push(profile);
        for (const warning of profile.warnings || []) addMessage(`${profile.filename}: ${warning}`);
      }
      for (const error of result.errors) addMessage(error, "error");
      updateDateBounds();
      updateDateRangeFromSelection();
      renderProfiles(); updateChart();
      setStatus(`${profiles.length} profile${profiles.length === 1 ? "" : "s"} found in ${result.directory}. Select batches to compare.`);
    } catch (error) {
      addMessage(`Local profiles: ${error.message}`, "error");
    }
  }

  if (elements.input) elements.input.addEventListener("change", () => importFiles(elements.input.files));
  if (elements.controls) elements.controls.addEventListener("change", event => {
    const input = event.target;
    if (!(input instanceof HTMLInputElement)) return;
    const measurements = [...elements.controls.querySelectorAll("input[data-series]:not([data-series='events'])")];
    if (!measurements.some(item => item.checked)) {
      input.checked = true;
      setStatus("At least one measurement must remain visible.");
      return;
    }
    updateChart();
  });
  if (elements.selectAll) elements.selectAll.addEventListener("click", () => { profiles.forEach(profile => { profile.enabled = true; }); updateDateRangeFromSelection(); renderProfiles(); updateChart(); });
  if (elements.selectNone) elements.selectNone.addEventListener("click", () => { profiles.forEach(profile => { profile.enabled = false; }); updateDateRangeFromSelection(); renderProfiles(); updateChart(); });
  if (elements.clearAll) elements.clearAll.addEventListener("click", clearAll);

  if (elements.dateStart) {
    elements.dateStart.addEventListener("change", applyDateRangeFilter);
    elements.dateStart.addEventListener("input", applyDateRangeFilter);
  }
  if (elements.dateEnd) {
    elements.dateEnd.addEventListener("change", applyDateRangeFilter);
    elements.dateEnd.addEventListener("input", applyDateRangeFilter);
  }

  // The page itself accepts files without needing a dedicated drop area.
  if (typeof document !== "undefined") {
    document.addEventListener("dragover", event => {
      if (event.dataTransfer?.types.includes("Files")) event.preventDefault();
    });
    document.addEventListener("drop", event => {
      if (!event.dataTransfer?.files.length) return;
      event.preventDefault();
      importFiles(event.dataTransfer.files);
    });
  }

  function setTheme(theme) {
    const isDark = theme === "dark";
    const mode = isDark ? "dark" : "light";
    document.documentElement.setAttribute("data-theme", mode);
    if (document.body) document.body.setAttribute("data-theme", mode);
    try {
      localStorage.setItem("theme", mode);
    } catch (_) {}
    if (elements.themeToggle) {
      elements.themeToggle.setAttribute("aria-label", isDark ? "Switch to light mode" : "Switch to dark mode");
      elements.themeToggle.setAttribute("title", isDark ? "Switch to light mode" : "Switch to dark mode");
      elements.themeToggle.setAttribute("aria-pressed", isDark ? "true" : "false");
      const label = elements.themeToggle.querySelector(".theme-label");
      if (label) label.textContent = isDark ? "Light mode" : "Dark mode";
    }
    chart.setTheme(mode);
  }

  function toggleTheme() {
    const current = document.documentElement.getAttribute("data-theme");
    const next = current === "dark" ? "light" : "dark";
    setTheme(next);
  }

  function initTheme() {
    let saved = null;
    try {
      saved = localStorage.getItem("theme");
    } catch (_) {}
    setTheme(saved === "dark" ? "dark" : "light");
    if (elements.themeToggle) {
      elements.themeToggle.addEventListener("click", toggleTheme);
    }
  }

  if (typeof document !== "undefined") {
    initTheme();
    updateDateBounds();
    updateDateRangeFromSelection();
    renderProfiles(); updateChart();
    loadLocalProfiles();
  }

  if (typeof module !== "undefined" && module.exports) {
    module.exports = {
      getTodayIso,
      profileDate,
      updateDateBounds,
      updateDateRangeFromSelection,
      applyDateRangeFilter,
      clearAll,
      profiles,
      elements,
    };
  }
})();
