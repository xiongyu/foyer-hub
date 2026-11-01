const state = {
  sequence: 0,
  status: null,
  token: localStorage.getItem("indoor-api-token") || "",
};

const $ = (selector) => document.querySelector(selector);

function headers(json = false) {
  const value = {};
  if (json) value["Content-Type"] = "application/json";
  if (state.token) value["X-API-Token"] = state.token;
  return value;
}

async function request(path, options = {}) {
  const response = await fetch(path, { ...options, headers: { ...headers(Boolean(options.body)), ...(options.headers || {}) } });
  const payload = await response.json();
  if (!response.ok || !payload.ok) throw new Error(payload.error || `HTTP ${response.status}`);
  return payload;
}

function setText(selector, value) {
  $(selector).textContent = value;
}

function renderStatus(status) {
  state.status = status;
  setText("#site-name", status.site_name);
  const badge = $("#mode-badge");
  badge.textContent = status.mode.toUpperCase();
  badge.className = `mode-badge ${status.mode === "live" ? "live" : "dry"}`;
  const caps = status.capabilities || [];
  setText("#feature-count", String(caps.length));
  setText("#feature-detail", caps.join(" · ") || "暂无能力");
  setText("#connection-note", status.mode === "live" ? "使用已启用的站点服务。" : "演练模式，不会执行设备控制。");
  $("#register").disabled = !caps.includes("station.register@1");
  $("#discover").disabled = !caps.includes("station.discover@1");
  $("#rest-sync").disabled = !caps.includes("content.sync@1");
  setText("#elevator-count", status.elevator.enabled ? "已启用" : "不可用");
  setText("#elevator-detail", "到梯结果需现场确认");
  const remaining = status.elevator.cooldown_remaining_seconds;
  setText("#cooldown", remaining > 0 ? `冷却中：${remaining.toFixed(1)} 秒` : "口令匹配后按钮可用");
  updateElevatorButton();
}

function updateElevatorButton() {
  const input = $("#elevator-confirm");
  const button = $("#call-elevator");
  const ready = state.status && state.status.elevator.enabled && state.status.elevator.cooldown_remaining_seconds <= 0;
  button.disabled = !ready || !input.value.trim();
}

async function refreshStatus() {
  try {
    const payload = await request("/api/status");
    renderStatus(payload.status);
  } catch (error) {
    setText("#operation-result", `状态读取失败：${error.message}`);
  }
}

function eventNode(event) {
  const row = document.createElement("article");
  row.className = `event ${event.level}`;
  const time = document.createElement("time");
  time.textContent = new Date(event.timestamp).toLocaleTimeString("zh-CN", { hour12: false });
  const body = document.createElement("div");
  const title = document.createElement("strong");
  title.textContent = event.message;
  const detail = document.createElement("code");
  detail.textContent = Object.keys(event.data || {}).length ? JSON.stringify(event.data) : event.kind;
  body.append(title, detail);
  row.append(time, body);
  return row;
}

async function pollEvents() {
  try {
    const payload = await request(`/api/events?after=${state.sequence}`);
    const container = $("#events");
    for (const event of payload.events) {
      container.prepend(eventNode(event));
      state.sequence = Math.max(state.sequence, event.sequence);
    }
    while (container.children.length > 80) container.lastElementChild.remove();
  } catch (error) {
    // Status refresh presents connection errors without filling the event list.
  }
}

async function action(path, body = {}) {
  const output = $("#operation-result");
  output.textContent = "执行中…";
  output.className = "operation-result busy";
  try {
    const payload = await request(path, { method: "POST", body: JSON.stringify(body) });
    output.textContent = JSON.stringify(payload.result, null, 2);
    output.className = "operation-result success";
  } catch (error) {
    output.textContent = `失败：${error.message}`;
    output.className = "operation-result failure";
  } finally {
    await refreshStatus();
    await pollEvents();
  }
}

document.addEventListener("DOMContentLoaded", () => {
  $("#api-token").value = state.token;
  $("#api-token").addEventListener("change", (event) => {
    state.token = event.target.value.trim();
    localStorage.setItem("indoor-api-token", state.token);
    refreshStatus();
  });
  $("#refresh").addEventListener("click", refreshStatus);
  $("#register").addEventListener("click", () => action("/api/register"));
  $("#discover").addEventListener("click", () => action("/api/discover"));
  $("#rest-sync").addEventListener("click", () => action("/api/rest/sync"));
  $("#elevator-confirm").addEventListener("input", updateElevatorButton);
  $("#call-elevator").addEventListener("click", async () => {
    await action("/api/elevator/call", { confirmation: $("#elevator-confirm").value });
    $("#elevator-confirm").value = "";
    updateElevatorButton();
  });
  refreshStatus();
  pollEvents();
  setInterval(refreshStatus, 5000);
  setInterval(pollEvents, 1500);
});
