/* =====================================================================
   K8s Panorama 前端
   全部数据来自 /api，页面内不存在写死的图谱内容。
   任何写操作都会真实落库，并在「最近变更」里看到审计记录（含操作者）。
   读接口公开；写接口需登录且角色为 admin（见 backend/app/deps.py）。
   ===================================================================== */
"use strict";

const API_BASE = (location.port === "5173" || location.protocol === "file:")
  ? "http://127.0.0.1:8000" : "";
const API = API_BASE + "/api";

const $ = id => document.getElementById(id);

const S = {
  graph: null,          // {layers, groups, nodes, edges} —— 当前数据源的全景底图
  notes: [], sops: [], yamls: [], audit: [],
  layerOn: {},          // 图层显隐
  sel: null, hov: null,
  view: "all", ptab: "atlas",
  t: { x: 0, y: 0, s: 1 },
  links: true, anim: false,
  offs: {},
  me: null,             // 当前登录用户 {id, username, role}；未登录为 null
  source: "kb",         // 数据源：kb（我的数据）/ official（出厂）/ cluster（集群实况）
  cluster: null,        // 集群标注 {component_id -> {state, detail}}
  clusterMeta: null,    // 集群状态元信息 {degraded, version, elapsed_ms, message}
};
const canWrite = () => !!S.me && S.me.role === "admin";
const isCluster = () => S.source === "cluster";


/* ---------------------------------------------------------------- 工具区 */
/* 渲染范式约定（对应 docs/DEVELOPMENT.md 第 4 节）：
   1) 含用户输入的展示一律经过 esc() 转义，禁止把未转义文本拼进 HTML 字符串；
   2) 画布 / 右栏这类结构化面板用 DOM API（安全性由机制保证）；
   3) 列表类面板用模板字符串 + esc()，但必须逐个字段转义。
   新增代码照此办理，不要再混用第三种写法。 */
function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, c => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}
const rgba = (hex, a) => {
  const r = parseInt(hex.slice(1, 3), 16), g = parseInt(hex.slice(3, 5), 16), b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r},${g},${b},${a})`;
};

/* ---------------------------------------------------------------- API */
async function api(path, opts = {}) {
  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(), 15000);      // 15s 超时，避免永久挂起
  try {
    const res = await fetch(API + path, {
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      signal: ac.signal,
      ...opts,
    });
    const text = await res.text();
    let data = null;
    try { data = text ? JSON.parse(text) : null; } catch { data = text; }
    if (!res.ok) {
      const msg = (data && data.detail) ? JSON.stringify(data.detail) : (text || res.status);
      const err = new Error(msg);
      err.status = res.status;
      throw err;
    }
    return data;
  } catch (err) {
    if (err && err.name === "AbortError") {
      throw new Error("请求超时（15s），请检查后端是否在运行");
    }
    if (err && (err.status === 401 || err.status === 403)) {
      handleAuthError(err);
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}
/* 401/403 统一处理：提示原因并引导去登录（不强制跳转，避免打断浏览） */
function handleAuthError(err) {
  const why = err.status === 401 ? "需要登录" : "需要管理员权限";
  toast(why + "：" + err.message);
  renderAuthChip();
}
/* 拉当前登录用户；未登录时 S.me 置 null */
async function loadMe() {
  try {
    S.me = await api("/auth/me");
  } catch {
    S.me = null;
  }
  renderAuthChip();
  applyWritePermissions();
  return S.me;
}
/* 顶栏右侧的登录态芯片：未登录显示「登录」，已登录显示 用户名·角色 + 登出 */
function renderAuthChip() {
  const host = $("authChip"); if (!host) return;
  host.innerHTML = "";
  if (!S.me) {
    const a = document.createElement("a");
    a.className = "btn"; a.href = "/login.html"; a.textContent = "登录";
    host.appendChild(a);
    return;
  }
  const tag = document.createElement("span");
  tag.className = "btn mono";
  tag.style.cursor = "default";
  tag.textContent = `${S.me.username} · ${S.me.role}`;
  tag.title = `角色：${S.me.role}${S.me.role === "admin" ? "（可写）" : "（只读）"}`;
  const out = document.createElement("button");
  out.className = "btn"; out.textContent = "登出";
  out.onclick = async () => {
    try { await api("/auth/logout", { method: "POST" }); } catch { /* 忽略：本地清理即可 */ }
    S.me = null; renderAuthChip(); applyWritePermissions();
    toast("已登出");
    if (S.ptab !== "atlas") { await refreshPanel(); } else { await reloadGraph(); }
  };
  host.append(tag, out);
}
/* 按权限显示/隐藏写入口（viewer 与未登录看不到新建/编辑/删除） */
function applyWritePermissions() {
  const ok = canWrite();
  document.querySelectorAll("[data-need-write]").forEach(el => {
    el.style.display = ok ? "" : "none";
  });
  const chip = $("writeHint");
  if (chip) {
    chip.textContent = ok ? "" : (S.me ? "当前为只读账号，写操作已隐藏" : "未登录，写操作已隐藏");
    chip.hidden = ok;
  }
}
const nodeById = id => (S.graph ? S.graph.nodes.find(n => n.id === id) : null);
/* 分类色：深色主题用亮色系，浅色主题换深色系（同色相，保证对比度） */
const LAYER_COLOR_LIGHT = {
  control:"#1D64B8", dataplane:"#15803D", l7:"#7E22CE", portnat:"#C2410C",
  policy:"#B91C1C", observe:"#0F766E", monitor:"#0369A1", storage:"#A16208"
};
const layerColor = id => {
  const l = S.graph && S.graph.layers.find(x => x.id === id);
  if (!l) return currentTheme() === "light" ? "#5A6E85" : "#5F7A97";
  return currentTheme() === "light" ? (LAYER_COLOR_LIGHT[id] || l.color) : l.color;
};
/* 连线标签配色（跟随主题） */
const edgeLabelColors = () => {
  const light = currentTheme() === "light";
  return light
    ? { bg:"#FFFFFF", bd:"#C2CEE0", fg:"#3C4F66", fgOn:"#0F1D2E" }
    : { bg:"#0A1626", bd:"#16273C", fg:"#7E95AF", fgOn:"#D6E7FA" };
};

/* ---------------------------------------------------------------- 启动 */
async function boot() {
  try {
    S.graph = await api("/atlas/graph");
  } catch (e) {
    $("status").textContent = "无法连接后端：" + e.message + " —— 请先启动 backend";
    return;
  }
  S.graph.layers.forEach(l => (S.layerOn[l.id] = true));
  await loadMe();                       // 登录态优先拉取，决定写入口是否可见
  buildTabs(); buildSide(); buildLegend(); buildCanvas();
  bindGlobal(); bindCanvas();
  fit();
  const first = S.graph.nodes.find(n => n.id === "netpol") || S.graph.nodes[0];
  if (first) select(first.id, true);
  $("status").textContent =
    `已加载 ${S.graph.nodes.length} 个组件 / ${S.graph.edges.length} 条关系 · 滚轮缩放 · 双击放大 · 点击查看详情`;
}
/* ---------------------------------------------------------------- 主题 */
/* 深浅切换：默认跟随系统，用户手动切过之后记住选择（localStorage）。
   主题只影响外观，不影响数据与交互。 */
const THEME_KEY = "atlas_theme";
const MOON = '<path d="M20.5 14.5A8.5 8.5 0 1 1 9.5 3.5a7 7 0 0 0 11 11z"/>';
const SUN = '<circle cx="12" cy="12" r="4.2"/><path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6l1.4 1.4M17 17l1.4 1.4M18.4 5.6L17 7M7 17l-1.4 1.4"/>';

function currentTheme() {
  const saved = localStorage.getItem(THEME_KEY);
  if (saved === "light" || saved === "dark") return saved;
  return matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
}
function applyTheme(t) {
  document.documentElement.dataset.theme = t;
  const icon = $("themeIcon");
  if (icon) icon.innerHTML = t === "light" ? MOON : SUN;
  const btn = $("bTheme");
  if (btn) btn.title = t === "light" ? "切换到深色" : "切换到浅色";
}
function toggleTheme() {
  const next = currentTheme() === "light" ? "dark" : "light";
  localStorage.setItem(THEME_KEY, next);
  applyTheme(next);
  toast(next === "light" ? "已切换到浅色主题" : "已切换到深色主题");
}

/* ---------------------------------------------------------------- 数据源 */
/* 三个来源共用同一套槽位坐标（布局是心智锚点），只有数据不同：
   kb       知识库（我的数据）     → /api/atlas/graph
   official 官方全景（出厂数据）   → /api/atlas/official（来自 seed，不受编辑影响）
   cluster  集群实况（接入 K8s）   → /api/atlas/graph 做底 + /api/cluster/components 填状态 */
async function loadGraph(source) {
  const path = source === "official" ? "/atlas/official" : "/atlas/graph";
  S.graph = await api(path);
  S.graph.layers.forEach(l => { if (S.layerOn[l.id] === undefined) S.layerOn[l.id] = true; });
  if (source === "cluster") {
    await loadCluster();
  } else {
    S.cluster = null;
    S.clusterMeta = null;
    renderClusterChip();
  }
}

async function loadCluster() {
  const chip = $("clusterChip");
  try {
    const st = await api("/cluster/status");
    S.clusterMeta = st;
    S.cluster = {};
    (st.components || []).forEach(c => { S.cluster[c.component_id] = c; });
    renderClusterChip();
  } catch (e) {
    // 集群不可用：降级为纯知识图谱，不影响其它功能
    S.cluster = null;
    S.clusterMeta = { degraded: true, message: e.message };
    renderClusterChip();
    toast("集群未连接，已降级为知识库视图：" + e.message);
    $("srcSel").value = "kb";
    S.source = "kb";
    await loadGraph("kb");
    return false;
  }
  return true;
}

function renderClusterChip() {
  const chip = $("clusterChip"); if (!chip) return;
  if (S.source !== "cluster") { chip.hidden = true; return; }
  chip.hidden = false;
  const m = S.clusterMeta || {};
  if (m.degraded) {
    chip.className = "chip bad";
    chip.textContent = "集群未连接";
    chip.title = (m.message || "无法连接集群") + "\n已降级为知识库视图";
    return;
  }
  const bad = Object.values(S.cluster || {}).filter(c => c.state === "unhealthy").length;
  chip.className = "chip " + (bad ? "bad" : "ok");
  chip.textContent = bad ? `集群已连接 · ${bad} 项异常` : "集群已连接";
  chip.title = `K8s ${m.version || ""} · 采集耗时 ${m.elapsed_ms || 0}ms`;
}

/* 把集群标注应用到画布卡片上（槽位四态） */
function applyClusterStates() {
  document.querySelectorAll(".node").forEach(d => {
    const id = d.dataset.id;
    const old = d.querySelector(".cs-tag, .cs-live");
    if (old) old.remove();
    if (!isCluster()) { d.removeAttribute("data-cstate"); return; }
    const c = S.cluster && S.cluster[id];
    if (!c) { d.removeAttribute("data-cstate"); return; }
    d.dataset.cstate = c.state;
    const label = { unhealthy: "异常", not_detected: "未检测到", unknown: "采集不到", present: "" }[c.state] || "";
    if (label) {
      const tag = document.createElement("span");
      tag.className = "cs-tag"; tag.textContent = label;
      d.appendChild(tag);
    }
    if (c.state === "present" || c.state === "unhealthy") {
      const live = document.createElement("div");
      live.className = "cs-live";
      live.textContent = liveText(c.detail);
      d.appendChild(live);
    }
  });
}

function liveText(detail) {
  if (!detail) return "";
  if (detail.version) return `v${detail.version}`;
  if (detail.total !== undefined && detail.ready !== undefined) return `就绪 ${detail.ready}/${detail.total}`;
  if (detail.total !== undefined) return `共 ${detail.total} 个`;
  if (detail.name) return detail.name;
  if (detail.note) return "";
  return "";
}

/* ---------------------------------------------------------------- 页签 */
const TABS = [
  { id: "atlas",  label: "全景架构" },
  { id: "path",   label: "网络链路" },
  { id: "table",  label: "对照表" },
  { id: "notes",  label: "知识库" },
  { id: "sops",   label: "排障 SOP" },
  { id: "yamls",  label: "YAML 实验室" },
];
function buildTabs() {
  const el = $("ptabs"); el.innerHTML = "";
  TABS.forEach(t => {
    const b = document.createElement("div");
    b.className = "ptab" + (t.id === S.ptab ? " on" : "");
    b.textContent = t.label;
    b.onclick = () => switchTab(t.id);
    el.appendChild(b);
  });
}
async function switchTab(id) {
  S.ptab = id;
  document.querySelectorAll(".ptab").forEach(e => e.classList.toggle("on", e.textContent === TABS.find(t => t.id === id).label));
  const isCanvas = id === "atlas";
  $("canvasView").hidden = !isCanvas;
  $("panelView").hidden = isCanvas;
  document.querySelector(".legend").style.display = isCanvas ? "" : "none";
  $("status").style.display = isCanvas ? "" : "none";
  if (!isCanvas) await renderPanel(id);
  else { applyT(); }
}

/* ---------------------------------------------------------------- 左栏 */
function buildSide() {
  $("vlist").innerHTML = "";
  [{ id: "all", label: "全景" }, { id: "control", label: "控制面" }, { id: "node", label: "节点" },
   { id: "network", label: "网络" }, { id: "workload", label: "工作负载" }, { id: "security", label: "安全存储" }]
    .forEach(v => {
      const d = document.createElement("div");
      d.className = "vitem" + (v.id === "all" ? " on" : "");
      d.textContent = v.label;
      d.onclick = () => focusView(v.id);
      $("vlist").appendChild(d);
    });

  $("cklist").innerHTML = "";
  S.graph.layers.filter(l => l.show_in_filter !== false).forEach(l => {
    const d = document.createElement("div");
    d.className = "ck"; d.innerHTML = '<span class="box"></span><span></span>';
    d.lastChild.textContent = l.label;
    d.onclick = () => { S.layerOn[l.id] = !S.layerOn[l.id]; syncLayers(); };
    $("cklist").appendChild(d);
  });

  $("olist").innerHTML = "";
  ["kube-apiserver", "etcd", "kubelet", "kube-scheduler", "kube-controller-manager", "kube-proxy"]
    .forEach(nm => {
      const n = S.graph.nodes.find(x => x.name === nm);
      if (!n) return;
      const d = document.createElement("div");
      d.className = "oitem"; d.textContent = nm; d.dataset.id = n.id;
      d.onclick = () => select(n.id, false, true);
      $("olist").appendChild(d);
    });
}
function focusView(vid) {
  document.querySelectorAll(".vitem").forEach(d => d.classList.toggle("on", d.textContent === vid));
  const map = { all: null, control: ["g1"], node: ["g2"], network: ["g3", "g4"], workload: ["g5"], security: ["g7", "g6"] };
  const target = map[vid];
  document.querySelectorAll(".gbox").forEach(d => {
    const on = !target || target.includes(d.dataset.g);
    d.style.opacity = on ? "1" : ".16";
    d.classList.toggle("hot", !!target && on);
  });
  if (target) {
    const boxes = S.graph.groups.filter(g => target.includes(g.id));
    const x0 = Math.min(...boxes.map(g => g.x)) - 24, y0 = Math.min(...boxes.map(g => g.y)) - 24;
    const x1 = Math.max(...boxes.map(g => g.x + g.w)) + 24, y1 = Math.max(...boxes.map(g => g.y + g.h)) + 24;
    const vp = $("viewport");
    S.t.s = Math.min(vp.clientWidth / (x1 - x0), vp.clientHeight / (y1 - y0), 1.05);
    S.t.x = vp.clientWidth / 2 - ((x0 + x1) / 2) * S.t.s;
    S.t.y = vp.clientHeight / 2 - ((y0 + y1) / 2) * S.t.s;
    applyT();
  } else fit();
}
function syncLayers() {
  const filterable = S.graph.layers.filter(x => x.show_in_filter !== false);
  document.querySelectorAll(".ck").forEach((d, i) => {   // forEach 自带下标，不再用 indexOf 反查
    const l = filterable[i];
    if (l) d.classList.toggle("off", !S.layerOn[l.id]);
  });
  document.querySelectorAll(".chip").forEach(d => d.classList.toggle("off", !S.layerOn[d.dataset.id]));
  applyVisibility(); scheduleDrawEdges();
  const vis = S.graph.nodes.filter(n => S.layerOn[n.layer_id]).length;
  const st = $("status");
  if (vis === 0) {
    $("emptyTx").textContent = "所有图层都已隐藏 —— 请在左侧「图层」或顶部图例中重新勾选。";
    $("empty").classList.add("show");
    st.textContent = "当前没有可见组件";
  } else {
    $("empty").classList.remove("show");
    st.textContent = `已加载 ${vis} 个可见组件 / ${S.graph.edges.length} 条关系 · 滚轮缩放 · 双击放大`;
  }
}
function applyVisibility() {
  document.querySelectorAll(".node").forEach(d => {
    const n = nodeById(d.dataset.id);
    d.style.display = S.layerOn[n.layer_id] ? "" : "none";
  });
  document.querySelectorAll(".gbox").forEach(d => {
    const any = S.graph.nodes.some(n => n.group_id === d.dataset.g && S.layerOn[n.layer_id]);
    d.style.display = any ? "" : "none";
  });
}

/* ---------------------------------------------------------------- 图例 */
function buildLegend() {
  const el = $("legend"); el.innerHTML = "";
  S.graph.layers.filter(l => l.show_in_legend !== false).forEach(l => {
    const c = document.createElement("div");
    c.className = "chip"; c.dataset.id = l.id;
    c.style.borderColor = rgba(layerColor(l.id), .5);
    const dot = document.createElement("span");
    dot.className = "dot"; dot.style.background = layerColor(l.id); dot.style.color = layerColor(l.id);
    const tx = document.createElement("span"); tx.textContent = l.label;
    c.append(dot, tx);
    c.onclick = () => { S.layerOn[l.id] = !S.layerOn[l.id]; syncLayers(); };
    el.appendChild(c);
  });
}

/* ---------------------------------------------------------------- 画布 */
/* drawEdges 会重建约 210 个 SVG 节点。hover / 缩放平移会高频触发，
   用合帧调度：同一批触发只画一次。
   rAF 之外加 setTimeout 兜底 —— 部分无头渲染环境里 rAF 不触发，
   没有兜底会出现"连线永远画不出来"。 */
let edgeToken = 0;
function scheduleDrawEdges() {
  const my = ++edgeToken;
  const run = () => {
    if (my === edgeToken) { edgeToken = 0; drawEdges(); }
  };
  if (window.requestAnimationFrame) requestAnimationFrame(run);
  setTimeout(run, 50);          // 谁先到谁画，后到的被 token 挡掉
}
function buildCanvas() {
  const gl = $("glayer"); gl.innerHTML = "";
  S.graph.groups.forEach(g => {
    const d = document.createElement("div");
    d.className = "gbox"; d.dataset.g = g.id;
    d.style.cssText = `left:${g.x}px;top:${g.y}px;width:${g.w}px;height:${g.h}px`;
    const h = document.createElement("div"); h.className = "gh";
    const no = document.createElement("span"); no.className = "no"; no.textContent = g.ordinal || "";
    const tx = document.createElement("span"); tx.className = "tx";
    tx.textContent = g.title + (g.subtitle ? " " + g.subtitle : "");
    h.append(no, tx); d.appendChild(h);
    gl.appendChild(d);
  });

  const nl = $("nlayer"); nl.innerHTML = "";
  S.graph.nodes.forEach(n => {
    const d = document.createElement("div");
    d.className = "node"; d.dataset.id = n.id; d.tabIndex = 0;
    d.style.borderColor = rgba(layerColor(n.layer_id), .62);
    const nm = document.createElement("div"); nm.className = "nm"; nm.textContent = n.name;
    const kd = document.createElement("div"); kd.className = "kd"; kd.textContent = n.kind || "";
    d.append(nm, kd);
    (n.fields || []).forEach(f => {
      const fr = document.createElement("div"); fr.className = "fr";
      const b = document.createElement("b"); b.textContent = f.label + "：";
      fr.append(b, document.createTextNode(f.value));
      d.appendChild(fr);
    });
    place(d, n);
    d.onclick = e => { e.stopPropagation(); select(n.id); };
    d.ondblclick = e => { e.stopPropagation(); zoomTo(n.id); };
    d.onmouseenter = () => { S.hov = n.id; scheduleDrawEdges(); };
    d.onmouseleave = () => { S.hov = null; scheduleDrawEdges(); };
    bindDrag(d, n);
    nl.appendChild(d);
  });
}
function place(d, n) {
  const off = S.offs[n.id] || { x: 0, y: 0 };
  d.style.left = (n.x + off.x) + "px";
  d.style.top = (n.y + off.y) + "px";
}
function box(id) {
  const n = nodeById(id); if (!n) return null;
  const d = document.querySelector('.node[data-id="' + id + '"]'); if (!d) return null;
  const off = S.offs[id] || { x: 0, y: 0 };
  const w = (d.offsetWidth || 152) + 10, h = (d.offsetHeight || 60) + 10;
  return { cx: n.x + off.x + w / 2, cy: n.y + off.y + h / 2, w, h };
}
function anchor(from, to) {
  const dx = to.cx - from.cx, dy = to.cy - from.cy;
  if (!dx && !dy) return { x: from.cx, y: from.cy };
  const tx = dx ? (from.w / 2) / Math.abs(dx) : Infinity;
  const ty = dy ? (from.h / 2) / Math.abs(dy) : Infinity;
  const t = Math.min(tx, ty) * .82;
  return { x: from.cx + dx * t, y: from.cy + dy * t };
}
function drawEdges() {
  const svg = $("elayer");
  svg.setAttribute("width", 1500); svg.setAttribute("height", 1700);
  svg.innerHTML = "";
  const NS = "http://www.w3.org/2000/svg";
  const focus = S.sel || S.hov;
  S.graph.edges.forEach(e => {
    const from = nodeById(e.from_node), to = nodeById(e.to_node);
    if (!from || !to) return;                                   // 先判空再用，避免整片连线消失
    if (!S.layerOn[from.layer_id] || !S.layerOn[to.layer_id]) return;
    const A = box(e.from_node), B = box(e.to_node); if (!A || !B) return;
    const P1 = anchor(A, B), P2 = anchor(B, A);
    const x1 = P1.x, y1 = P1.y, x2 = P2.x, y2 = P2.y, dx = x2 - x1;
    const c1 = x1 + dx * .42, c2 = x2 - dx * .42;
    const col = layerColor(from.layer_id);
    const mx = .125 * x1 + .375 * c1 + .375 * c2 + .125 * x2, my = (y1 + y2) / 2;
    const on = focus && (e.from_node === focus || e.to_node === focus);
    const off = focus && !on;

    /* 集群模式：任一端异常 → 概念连线转琥珀加粗；一端未检测到 → 置灰 */
    let stroke = rgba(col, on ? .95 : (off ? .2 : .44));
    let width = on ? 1.6 : 1;
    if (isCluster() && S.cluster) {
      const ca = S.cluster[e.from_node], cb = S.cluster[e.to_node];
      if ((ca && ca.state === "unhealthy") || (cb && cb.state === "unhealthy")) {
        stroke = "rgba(245,158,11,.92)"; width = on ? 2 : 1.4;
      } else if ((ca && ca.state === "not_detected") || (cb && cb.state === "not_detected")) {
        stroke = "rgba(120,140,165,.26)";
      }
    }
    if (!S.links) return;
    const p = document.createElementNS(NS, "path");
    p.setAttribute("d", `M${x1} ${y1} C${c1} ${y1} ${c2} ${y2} ${x2} ${y2}`);
    p.setAttribute("fill", "none");
    p.setAttribute("stroke", stroke);
    p.setAttribute("stroke-width", width);
    if (S.anim) { p.setAttribute("stroke-dasharray", "5 7"); p.style.animation = "flow 1.1s linear infinite"; }
    svg.appendChild(p);
    [[x1, y1], [x2, y2]].forEach(([cx, cy]) => {
      const c = document.createElementNS(NS, "circle");
      c.setAttribute("cx", cx); c.setAttribute("cy", cy);
      c.setAttribute("r", on ? 2.6 : 1.8);
      c.setAttribute("fill", rgba(col, on ? 1 : (off ? .22 : .58)));
      svg.appendChild(c);
    });
    const tw = e.label.length * 5.5 + 13;
    const k = Math.min(1.5, Math.max(1, 6.5 / (9.5 * S.t.s)));
    const g = document.createElementNS(NS, "g");
    if (k > 1.001) g.setAttribute("transform", `translate(${mx},${my}) scale(${k}) translate(${-mx},${-my})`);
    const r = document.createElementNS(NS, "rect");
    r.setAttribute("x", mx - tw / 2); r.setAttribute("y", my - 8.5);
    r.setAttribute("width", tw); r.setAttribute("height", 16); r.setAttribute("rx", 4.5);
    r.setAttribute("fill", "#0A1626"); r.setAttribute("stroke", "#16273C");
    const tx = document.createElementNS(NS, "text");
    tx.setAttribute("x", mx); tx.setAttribute("y", my + 3.5);
    tx.setAttribute("fill", on ? "#D6E7FA" : "#7E95AF");
    tx.setAttribute("font-size", "9.5"); tx.setAttribute("text-anchor", "middle");
    tx.setAttribute("font-family", 'Inter,-apple-system,"Segoe UI","Microsoft YaHei",sans-serif');
    tx.textContent = e.label;
    if (off) { r.setAttribute("opacity", ".35"); tx.setAttribute("opacity", ".4"); }
    g.append(r, tx); svg.appendChild(g);
  });
}
function applyT() {
  S.graph && ($("stage").dataset.lod = S.t.s >= .4 ? "full" : (S.t.s >= .28 ? "mid" : "min"));
  $("stage").style.transform = `translate(${S.t.x}px,${S.t.y}px) scale(${S.t.s})`;
  $("zoominfo").textContent = Math.round(S.t.s * 100) + "%";
  scheduleDrawEdges();
}
function zoom(k, cx, cy) {
  const vp = $("viewport");
  const px = cx === undefined ? vp.clientWidth / 2 : cx;
  const py = cy === undefined ? vp.clientHeight / 2 : cy;
  const wx = (px - S.t.x) / S.t.s, wy = (py - S.t.y) / S.t.s;
  const ns = Math.min(2.4, Math.max(.22, S.t.s * k));
  S.t.s = ns; S.t.x = px - wx * ns; S.t.y = py - wy * ns;
  applyT();
}
function fit() {
  const vp = $("viewport"), sw = 1500, sh = 1700, top = 54, bot = 52;
  S.t.s = Math.max(.22, Math.min(vp.clientWidth / sw, (vp.clientHeight - top - bot) / sh));
  S.t.x = (vp.clientWidth - sw * S.t.s) / 2;
  S.t.y = top + Math.max(0, (vp.clientHeight - top - bot - sh * S.t.s) / 2);
  applyT();
}
function center(id, s) {
  const b = box(id); if (!b) return;
  const vp = $("viewport");
  S.t.s = s || S.t.s;
  S.t.x = vp.clientWidth / 2 - b.cx * S.t.s;
  S.t.y = vp.clientHeight / 2 - b.cy * S.t.s;
  applyT();
}
function zoomTo(id) { select(id, true); center(id, 1); toast("阅读模式：100%"); }

/* ---------------------------------------------------------------- 选中 / 右栏 */
/* 详情面板渲染令牌：快速切换节点时，丢弃已过期的异步请求结果，
   避免旧节点的「相关知识条目」被追加到新节点的面板后面 */
let inspToken = 0;

function select(id, silent, centerIt) {
  S.sel = id;
  document.querySelectorAll(".node").forEach(d => d.classList.toggle("sel", d.dataset.id === id));
  document.querySelectorAll(".oitem").forEach(d => d.classList.toggle("on", d.dataset.id === id));
  scheduleDrawEdges(); renderInspector(id);
  if (centerIt) center(id);
  const cur = nodeById(id);
  if (!silent && cur) {
    $("status").textContent = "已选中 · " + cur.name + " · 双击放大 · 右侧可编辑";
  }
}
async function renderInspector(id) {
  const my = ++inspToken;
  const n = nodeById(id); if (!n) return;
  const el = $("insp"); el.innerHTML = "";
  const h = document.createElement("h2"); h.textContent = n.name;
  const sub = document.createElement("div"); sub.className = "sub";
  sub.textContent = n.summary || n.kind || "";
  el.append(h, sub);

  const acts = document.createElement("div"); acts.className = "acts";
  const bEdit = document.createElement("button"); bEdit.className = "btn"; bEdit.textContent = "编辑";
  bEdit.dataset.needWrite = "";
  bEdit.onclick = () => openNodeForm(n);
  const bEdge = document.createElement("button"); bEdge.className = "btn"; bEdge.textContent = "+ 关系";
  bEdge.dataset.needWrite = "";
  bEdge.onclick = () => openEdgeForm(n.id);
  const bDel = document.createElement("button"); bDel.className = "btn danger"; bDel.textContent = "删除";
  bDel.dataset.needWrite = "";
  bDel.onclick = () => confirmBox(`删除组件「${n.name}」？相关的连线会一并删除。`, () => delNode(n.id));
  acts.append(bEdit, bEdge, bDel);
  el.appendChild(acts);

  el.appendChild(card("关键属性", () => {
    const box = document.createElement("div");
    (n.fields || []).forEach(f => {
      const row = document.createElement("div"); row.className = "kv";
      const k = document.createElement("span"); k.className = "k"; k.textContent = f.label;
      const v = document.createElement("span"); v.className = "v"; v.textContent = f.value;
      row.append(k, v); box.appendChild(row);
    });
    if (!(n.fields || []).length) box.textContent = "—";
    return box;
  }));

  /* 集群实况卡片：只在集群数据源下出现 */
  if (isCluster()) {
    const c = S.cluster && S.cluster[id];
    el.appendChild(card("集群实况", () => {
      const box = document.createElement("div");
      if (!c) {
        box.innerHTML = '<div class="hint">该组件没有对应的集群探测路径。</div>';
        return box;
      }
      const st = document.createElement("div"); st.className = "kv";
      const sk = document.createElement("span"); sk.className = "k"; sk.textContent = "状态";
      const sv = document.createElement("span"); sv.className = "v";
      const STATE_LB = { present: "在位", unhealthy: "异常", not_detected: "未检测到", unknown: "采集不到" };
      sv.textContent = STATE_LB[c.state] || c.state;
      sv.style.color = c.state === "unhealthy" ? "#FCD34D" : (c.state === "present" ? "#6EE7B7" : "#8A93A3");
      st.append(sk, sv); box.appendChild(st);

      const rows = liveRows(c.detail);
      rows.forEach(([k, v]) => {
        const row = document.createElement("div"); row.className = "kv";
        const kk = document.createElement("span"); kk.className = "k"; kk.textContent = k;
        const vv = document.createElement("span"); vv.className = "v"; vv.textContent = v;
        row.append(kk, vv); box.appendChild(row);
      });
      return box;
    }));
  }

  el.appendChild(card("基础信息", () => {
    const box = document.createElement("div");
    [["ID", n.id], ["分组", groupTitle(n.group_id)], ["分类", layerLabel(n.layer_id)],
     ["类型", n.kind || "—"], ["坐标", `${n.x}, ${n.y}`]].forEach(([k, v]) => {
      const row = document.createElement("div"); row.className = "kv";
      const kk = document.createElement("span"); kk.className = "k"; kk.textContent = k;
      const vv = document.createElement("span"); vv.className = "v"; vv.textContent = v;
      row.append(kk, vv); box.appendChild(row);
    });
    return box;
  }));

  const rels = S.graph.edges.filter(e => e.from_node === id || e.to_node === id).map(e => ({
    from: e.from_node === id ? n.name : nameOf(e.from_node),
    to: e.to_node === id ? n.name : nameOf(e.to_node),
    note: e.label, edgeId: e.id,
  }));
  el.appendChild(card("上下游", () => {
    const box = document.createElement("div");
    if (!rels.length) box.innerHTML = '<div class="hint">暂无关系，点「+ 关系」新增。</div>';
    rels.slice(0, 8).forEach(r => {
      const w = document.createElement("div"); w.className = "relwrap";
      const d = document.createElement("div"); d.className = "rel";
      const f = document.createElement("span"); f.textContent = r.from;
      const ar = document.createElement("span"); ar.className = "ar"; ar.textContent = "→";
      const t = document.createElement("span"); t.textContent = r.to;
      d.append(f, ar, t);
      const nt = document.createElement("div"); nt.className = "relnote"; nt.textContent = r.note || "—";
      w.append(d, nt); box.appendChild(w);
    });
    return box;
  }));

  /* 关联知识条目（真实查询） */
  try {
    const notes = await api("/notes?node_id=" + encodeURIComponent(id));
    if (my !== inspToken) return;          // 已有更新的渲染，丢弃本次结果
    if (notes.length) {
      el.appendChild(card("相关知识条目", () => {
        const box = document.createElement("div");
        notes.forEach(t => {
          const d = document.createElement("div"); d.className = "relwrap";
          const line = document.createElement("div"); line.className = "rel";
          const nm = document.createElement("span"); nm.textContent = t.title;
          line.appendChild(nm);
          const pill = document.createElement("span"); pill.className = "pill " + t.status; pill.textContent = t.status;
          const nt = document.createElement("div"); nt.className = "relnote";
          nt.textContent = t.markdown.slice(0, 90) + (t.markdown.length > 90 ? "…" : "");
          d.append(line, pill, nt); box.appendChild(d);
        });
        return box;
      }));
    }
  } catch { /* 忽略：知识条目不是必须 */ }

  el.appendChild(card("验证命令", () => {
    const box = document.createElement("div");
    box.style.display = "flex"; box.style.flexDirection = "column"; box.style.gap = "7px";

    /* 集群数据源：参数化命令面板（异常时定位命令置顶，写操作加「写」标记） */
    if (isCluster()) {
      const c = S.cluster && S.cluster[id];
      const cmds = orderedCommands(id, c && c.state);
      if (!cmds.length) {
        box.innerHTML = '<div class="hint">该组件暂无预设命令。</div>';
        return box;
      }
      cmds.forEach(item => {
        const text = fillCommand(item.cmd, c && c.detail);
        const d = document.createElement("div");
        d.className = "cmd" + (item.isWrite ? " cmd-write" : "");
        d.title = "点击复制" + (item.isWrite ? "（写操作命令，谨慎执行）" : "");
        const s = document.createElement("span"); s.textContent = text;
        const em = document.createElement("em"); em.textContent = item.isWrite ? "写 · 复制" : "复制";
        d.append(s, em);
        d.onclick = () => copy(text);
        box.appendChild(d);
      });
      return box;
    }

    /* 知识库数据源：组件自带的验证命令 */
    const d = document.createElement("div"); d.className = "cmd";
    const s = document.createElement("span"); s.textContent = n.cmd || "（未配置）";
    const em = document.createElement("em"); em.textContent = "点击复制";
    d.append(s, em);
    d.onclick = () => copy(n.cmd || "");
    box.appendChild(d);
    return box;
  }));
}
const nameOf = id => { const n = nodeById(id); return n ? n.name : id; };
const groupTitle = gid => { const g = S.graph.groups.find(x => x.id === gid); return g ? (g.ordinal + " " + g.title) : gid; };
const layerLabel = lid => { const l = S.graph.layers.find(x => x.id === lid); return l ? l.label : lid; };
function card(title, build, deco) {
  const d = document.createElement("div"); d.className = "icard" + (deco ? " deco" : "");
  const h = document.createElement("h4"); h.textContent = title;
  d.append(h, build());
  return d;
}

/* ---------------------------------------------------------------- 内容面板 */
async function renderPanel(kind) {
  const el = $("panelView");
  el.innerHTML = '<div class="hint">加载中…</div>';
  try {
    if (kind === "notes") { S.notes = await api("/notes"); el.innerHTML = renderNotes(); bindNotes(); }
    else if (kind === "sops") { S.sops = await api("/sops"); el.innerHTML = renderSops(); bindSops(); }
    else if (kind === "yamls") { S.yamls = await api("/yamls"); el.innerHTML = renderYamls(); bindYamls(); }
    else if (kind === "table") { el.innerHTML = renderTable(); }
    else if (kind === "path") { el.innerHTML = renderPath(); bindPath(); }
    S.audit = await api("/audit?limit=8");
    el.insertAdjacentHTML("beforeend", renderAudit());
    applyWritePermissions();      // DOM 重建后重新按权限显隐写按钮
  } catch (e) {
    el.innerHTML = '<div class="err">加载失败：' + e.message + "</div>";
  }
}
function renderNotes() {
  return `<h2>知识库</h2><div class="lead">共 ${S.notes.length} 条 · 状态流转：draft → review → published（可归档/恢复）</div>
  <div class="pvbar"><button class="btn primary" id="nNew" data-need-write>+ 新建条目</button></div>
  <div class="list">${S.notes.map(t => `
    <div class="item" data-slug="${t.slug}">
      <h4>${esc(t.title)} <span class="pill ${t.status}">${t.status}</span></h4>
      <div class="meta">${t.slug}${t.node_id ? " · 关联组件 " + esc(nameOf(t.node_id)) : ""}</div>
      <p>${esc(t.markdown)}</p>
      <div class="acts">
        <button class="btn" data-act="edit" data-need-write>编辑</button>
        ${t.status === "draft" ? '<button class="btn" data-act="publish" data-need-write>提交评审</button>' : ""}
        ${t.status === "review" ? '<button class="btn" data-act="approve" data-need-write>发布</button>' : ""}
        ${t.status !== "archived" ? '<button class="btn" data-act="archive" data-need-write>归档</button>' : ""}
        ${t.status === "archived" ? '<button class="btn" data-act="restore" data-need-write>恢复</button>' : ""}
        <button class="btn danger" data-act="del" data-need-write>删除</button>
      </div>
    </div>`).join("") || '<div class="hint">还没有条目，点「新建条目」。</div>'}</div>`;
}
function bindNotes() {
  $("nNew").onclick = () => openNoteForm(null);
  document.querySelectorAll(".item[data-slug]").forEach(it => {
    const slug = it.dataset.slug;
    it.querySelectorAll("button[data-act]").forEach(b => {
      b.onclick = async () => {
        const act = b.dataset.act;
        const cur = S.notes.find(x => x.slug === slug);
        if (act === "edit") return openNoteForm(cur);
        if (act === "del") return confirmBox("删除条目「" + cur.title + "」？", () => delNote(slug));
        try {
          await api(`/notes/${slug}/transition`, { method: "POST", body: JSON.stringify({ action: act }) });
          toast(`「${cur.title}」已执行 ${act}`);
          refreshPanel();
        } catch (e) { toast("失败：" + e.message); }
      };
    });
  });
}
function renderSops() {
  return `<h2>排障 SOP</h2><div class="lead">共 ${S.sops.length} 条 · 按现象索引，状态流转同知识库</div>
  <div class="pvbar"><button class="btn primary" id="sNew" data-need-write>+ 新建 SOP</button></div>
  <div class="list">${S.sops.map(s => `
    <div class="item" data-sym="${s.symptom}">
      <h4>${esc(s.title)} <span class="pill ${s.status}">${s.status}</span></h4>
      <div class="meta">现象标识：${s.symptom}</div>
      ${(s.steps || []).map(st => `
        <div class="step"><div class="no">${st.step_no}</div><div class="tx">
          <b>${esc(st.action)}</b><span>期望：${esc(st.expect || "—")}</span>
          ${st.command ? `<code>${esc(st.command)}</code>` : ""}
        </div></div>`).join("")}
      <div class="acts">
        <button class="btn" data-act="edit" data-need-write>编辑</button>
        ${s.status === "draft" ? '<button class="btn" data-act="publish" data-need-write>提交评审</button>' : ""}
        ${s.status === "review" ? '<button class="btn" data-act="approve" data-need-write>发布</button>' : ""}
        ${s.status !== "archived" ? '<button class="btn" data-act="archive" data-need-write>归档</button>' : ""}
        ${s.status === "archived" ? '<button class="btn" data-act="restore" data-need-write>恢复</button>' : ""}
        <button class="btn danger" data-act="del" data-need-write>删除</button>
      </div>
    </div>`).join("") || '<div class="hint">还没有 SOP。</div>'}</div>`;
}
function bindSops() {
  $("sNew").onclick = () => openSopForm(null);
  document.querySelectorAll(".item[data-sym]").forEach(it => {
    const sym = it.dataset.sym;
    it.querySelectorAll("button[data-act]").forEach(b => {
      b.onclick = async () => {
        const act = b.dataset.act;
        const cur = S.sops.find(x => x.symptom === sym);
        if (act === "edit") return openSopForm(cur);
        if (act === "del") return confirmBox("删除 SOP「" + cur.title + "」？", () => delSop(sym));
        try {
          await api(`/sops/${sym}/transition`, { method: "POST", body: JSON.stringify({ action: act }) });
          toast(`已执行 ${act}`); refreshPanel();
        } catch (e) { toast("失败：" + e.message); }
      };
    });
  });
}
function renderYamls() {
  return `<h2>YAML 实验室</h2><div class="lead">共 ${S.yamls.length} 条片段</div>
  <div class="pvbar"><button class="btn primary" id="yNew" data-need-write>+ 新建片段</button></div>
  <div class="list">${S.yamls.map(y => `
    <div class="item" data-id="${y.id}">
      <h4>${esc(y.title)}</h4>
      <div class="meta">${y.node_id ? "关联组件：" + esc(nameOf(y.node_id)) : "未关联"}</div>
      <pre class="mono" style="white-space:pre-wrap;color:#C6D6E6;font-size:12px;line-height:1.7">${esc(y.yaml)}</pre>
      <div class="acts">
        <button class="btn" data-act="edit" data-need-write>编辑</button>
        <button class="btn" data-act="copy">复制</button>
        <button class="btn danger" data-act="del" data-need-write>删除</button>
      </div>
    </div>`).join("") || '<div class="hint">还没有片段。</div>'}</div>`;
}
function bindYamls() {
  $("yNew").onclick = () => openYamlForm(null);
  document.querySelectorAll(".item[data-id]").forEach(it => {
    const id = Number(it.dataset.id);
    it.querySelectorAll("button[data-act]").forEach(b => {
      b.onclick = async () => {
        const act = b.dataset.act;
        const cur = S.yamls.find(x => x.id === id);
        if (act === "edit") return openYamlForm(cur);
        if (act === "copy") return copy(cur.yaml);
        if (act === "del") return confirmBox("删除片段「" + cur.title + "」？", () => delYaml(id));
      };
    });
  });
}
function renderTable() {
  const rows = S.graph.layers.map(l => {
    const ns = S.graph.nodes.filter(n => n.layer_id === l.id);
    return `<tr><td><span style="color:${l.color}">●</span> ${esc(l.label)}</td>
      <td>${ns.length}</td>
      <td>${ns.map(n => esc(n.name)).join("、") || "—"}</td></tr>`;
  }).join("");
  return `<h2>对照表</h2><div class="lead">按分类横向对照当前库里的组件（数据实时来自 /api/atlas/graph）</div>
  <table class="tbl"><thead><tr><th>分类</th><th>数量</th><th>组件</th></tr></thead><tbody>${rows}</tbody></table>`;
}
function renderPath() {
  const opts = S.graph.nodes.map(n => `<option value="${n.id}">${esc(n.name)}</option>`).join("");
  return `<h2>网络链路</h2>
  <div class="lead">基于库里的关系数据做真实路径搜索（BFS 最短路径），不是预设图</div>
  <div class="pvbar">
    从 <select id="pFrom" class="mono" style="background:#0A1728;border:1px solid #15263A;border-radius:8px;padding:7px 10px;color:#EAF1FA">${opts}</select>
    到 <select id="pTo" class="mono" style="background:#0A1728;border:1px solid #15263A;border-radius:8px;padding:7px 10px;color:#EAF1FA">${opts}</select>
    <button class="btn primary" id="pGo">搜路径</button>
  </div>
  <div id="pOut" class="hint">选择起点与终点后点击「搜路径」。</div>`;
}
function bindPath() {
  if (!S.graph.nodes.length) return;
  $("pFrom").value = "ingress";
  const dflt = S.graph.nodes.find(n => n.id === "pod");
  if (dflt) $("pTo").value = "pod";
  $("pGo").onclick = () => {
    const a = $("pFrom").value, b = $("pTo").value;
    const path = bfs(a, b);
    $("pOut").innerHTML = path
      ? `<div class="item"><h4>最短路径（${path.length - 1} 跳）</h4>
         <p>${path.map((id, i) => esc(nameOf(id)) + (i < path.length - 1 ? " → " : "")).join("")}</p></div>`
      : '<div class="hint">这两个组件之间在当前关系数据里没有连通路径。可以去画布上新增关系后再试。</div>';
  };
}
function bfs(a, b) {
  if (a === b) return [a];
  const adj = {};
  S.graph.edges.forEach(e => {
    (adj[e.from_node] ||= []).push(e.to_node);
    (adj[e.to_node] ||= []).push(e.from_node);
  });
  const q = [[a]], seen = new Set([a]);
  while (q.length) {
    const p = q.shift();
    const last = p[p.length - 1];
    for (const nx of (adj[last] || [])) {
      if (seen.has(nx)) continue;
      const np = [...p, nx];
      if (nx === b) return np;
      seen.add(nx); q.push(np);
    }
  }
  return null;
}
function renderAudit() {
  return `<div style="margin-top:26px"><div class="gtitle">最近变更（来自 /api/audit，证明操作已落库）</div>
  <table class="tbl"><thead><tr><th>时间</th><th>动作</th><th>实体</th><th>对象</th><th>详情</th></tr></thead><tbody>
  ${(S.audit || []).map(a => `<tr><td class="mono">${esc(String(a.created_at).replace("T", " ").slice(0, 19))}</td>
    <td>${esc(a.action)}</td><td>${esc(a.entity)}</td><td class="mono">${esc(a.entity_id)}</td>
    <td>${esc(String(a.detail || "").slice(0, 60))}</td></tr>`).join("")}
  </tbody></table></div>`;
}

/* ---------------------------------------------------------------- 表单 */
function openModal(title, bodyHtml, footButtons) {
  $("modalTitle").textContent = title;
  $("modalBody").innerHTML = bodyHtml;
  const foot = $("modalFoot"); foot.innerHTML = "";
  footButtons.forEach(b => {
    const btn = document.createElement("button");
    btn.className = "btn " + (b.cls || ""); btn.textContent = b.label;
    btn.onclick = b.onClick;
    foot.appendChild(btn);
  });
  $("modal").hidden = false;
}
function closeModal() { $("modal").hidden = true; }
function formVal(id) { const e = $(id); return e ? e.value.trim() : ""; }

function openNodeForm(node) {
  const isNew = !node;
  const groups = S.graph.groups.map(g => `<option value="${g.id}" ${node && node.group_id === g.id ? "selected" : ""}>${esc(g.ordinal + " " + g.title)}</option>`).join("");
  const layers = S.graph.layers.map(l => `<option value="${l.id}" ${node && node.layer_id === l.id ? "selected" : ""}>${esc(l.label)}</option>`).join("");
  const fields = (node && node.fields || [{}]).map(f =>
    `<div class="fldrow"><div class="fld"><input id="fl" placeholder="字段名" value="${esc(f.label || "")}"></div>
     <div class="fld"><input id="fv" placeholder="值" value="${esc(f.value || "")}"></div></div>`).join("");
  openModal(isNew ? "新建组件" : "编辑组件：" + node.name, `
    ${isNew ? `<div class="fld"><label>ID（英文标识，不可重复）</label><input id="f_id" placeholder="例如 my-component"><div class="tip">只能用字母、数字、-、_</div></div>` : ""}
    <div class="fld"><label>名称</label><input id="f_name" value="${esc(node ? node.name : "")}" placeholder="例如 kube-apiserver"></div>
    <div class="fldrow">
      <div class="fld"><label>所属分组</label><select id="f_group">${groups}</select></div>
      <div class="fld"><label>分类</label><select id="f_layer">${layers}</select></div>
    </div>
    <div class="fld"><label>类型（卡片第二行）</label><input id="f_kind" value="${esc(node ? node.kind : "")}"></div>
    <div class="fld"><label>一句话说明（右栏摘要）</label><input id="f_sum" value="${esc(node ? node.summary : "")}"></div>
    <div class="fld"><label>验证命令</label><input id="f_cmd" class="mono" value="${esc(node ? node.cmd : "")}" placeholder="kubectl get ..."></div>
    <div class="fldrow"><div class="fld"><label>坐标 X</label><input id="f_x" type="number" value="${node ? node.x : 60}"></div>
      <div class="fld"><label>坐标 Y</label><input id="f_y" type="number" value="${node ? node.y : 60}"></div></div>
    <div class="fldset"><div class="cap">关键字段（卡片第三行，可留空）</div><div id="f_fields">${fields}</div>
      <button class="btn" id="f_addfield" type="button">+ 加一行</button></div>
  `, [
    { label: "取消", onClick: closeModal },
    {
      label: isNew ? "创建" : "保存", cls: "primary", onClick: async () => {
        const payload = {
          name: formVal("f_name"), group_id: formVal("f_group"), layer_id: formVal("f_layer"),
          kind: formVal("f_kind"), summary: formVal("f_sum"), cmd: formVal("f_cmd"),
          x: Number(formVal("f_x") || 0), y: Number(formVal("f_y") || 0),
          fields: [...document.querySelectorAll("#f_fields .fldrow")].map(r => ({
            label: r.querySelector("#fl").value.trim(), value: r.querySelector("#fv").value.trim(),
          })).filter(f => f.label || f.value),
        };
        if (!payload.name) return toast("请填写名称");
        try {
          if (isNew) {
            payload.id = formVal("f_id");
            if (!payload.id) return toast("请填写 ID");
            await api("/nodes", { method: "POST", body: JSON.stringify(payload) });
            toast("已创建组件：" + payload.name);
          } else {
            await api("/nodes/" + node.id, { method: "PATCH", body: JSON.stringify(payload) });
            toast("已保存：" + payload.name);
          }
          closeModal(); await reloadGraph();
        } catch (e) { toast("保存失败：" + e.message); }
      }
    },
  ]);
  $("f_addfield").onclick = () => {
    const d = document.createElement("div"); d.className = "fldrow";
    d.innerHTML = '<div class="fld"><input id="fl" placeholder="字段名"></div><div class="fld"><input id="fv" placeholder="值"></div>';
    $("f_fields").appendChild(d);
  };
}
function openEdgeForm(fromId) {
  const opts = S.graph.nodes.map(n => `<option value="${n.id}" ${n.id === fromId ? "selected" : ""}>${esc(n.name)}</option>`).join("");
  openModal("新增关系", `
    <div class="fldrow"><div class="fld"><label>起点</label><select id="e_from">${opts}</select></div>
      <div class="fld"><label>终点</label><select id="e_to">${opts}</select></div></div>
    <div class="fld"><label>连线标签</label><input id="e_label" placeholder="例如 selector / 绑定 / HTTP"></div>
  `, [
    { label: "取消", onClick: closeModal },
    {
      label: "创建", cls: "primary", onClick: async () => {
        const payload = { from_node: formVal("e_from"), to_node: formVal("e_to"), label: formVal("e_label") };
        if (payload.from_node === payload.to_node) return toast("起点和终点不能相同");
        try {
          await api("/edges", { method: "POST", body: JSON.stringify(payload) });
          toast("已新增关系"); closeModal(); await reloadGraph();
        } catch (e) { toast("失败：" + e.message); }
      }
    },
  ]);
}
function openNoteForm(note) {
  const isNew = !note;
  const nopts = ['<option value="">（不关联）</option>'].concat(
    S.graph.nodes.map(n => `<option value="${n.id}" ${note && note.node_id === n.id ? "selected" : ""}>${esc(n.name)}</option>`)
  ).join("");
  openModal(isNew ? "新建知识条目" : "编辑：" + note.title, `
    ${isNew ? `<div class="fld"><label>slug（唯一标识）</label><input id="t_slug" placeholder="例如 networkpolicy-basics"></div>` : ""}
    <div class="fld"><label>标题</label><input id="t_title" value="${esc(note ? note.title : "")}"></div>
    <div class="fld"><label>关联组件</label><select id="t_node">${nopts}</select></div>
    <div class="fld"><label>正文</label><textarea id="t_md">${esc(note ? note.markdown : "")}</textarea></div>
  `, [
    { label: "取消", onClick: closeModal },
    {
      label: isNew ? "创建" : "保存", cls: "primary", onClick: async () => {
        const payload = {
          title: formVal("t_title"), markdown: formVal("t_md"),
          node_id: formVal("t_node") || null,
        };
        if (!payload.title) return toast("请填写标题");
        try {
          if (isNew) {
            payload.slug = formVal("t_slug");
            if (!payload.slug) return toast("请填写 slug");
            await api("/notes", { method: "POST", body: JSON.stringify(payload) });
          } else {
            await api("/notes/" + note.slug, { method: "PATCH", body: JSON.stringify(payload) });
          }
          toast("已保存"); closeModal(); await refreshPanel();
        } catch (e) { toast("失败：" + e.message); }
      }
    },
  ]);
}
function openSopForm(sop) {
  const isNew = !sop;
  const steps = (sop && sop.steps || [{ step_no: 1, action: "", expect: "", command: "" }]).map(s =>
    `<div class="fldset" data-step>
      <div class="fld"><label>第几步</label><input class="s_no" type="number" value="${s.step_no}"></div>
      <div class="fld"><label>做什么</label><input class="s_act" value="${esc(s.action)}"></div>
      <div class="fld"><label>期望看到</label><input class="s_exp" value="${esc(s.expect)}"></div>
      <div class="fld"><label>命令（可选）</label><input class="s_cmd" value="${esc(s.command)}"></div>
      <button class="btn danger s_del" type="button">删除这一步</button>
    </div>`).join("");
  openModal(isNew ? "新建排障 SOP" : "编辑：" + sop.title, `
    ${isNew ? `<div class="fld"><label>现象标识（英文唯一）</label><input id="s_sym" placeholder="例如 service-502"></div>` : ""}
    <div class="fld"><label>标题</label><input id="s_title" value="${esc(sop ? sop.title : "")}"></div>
    <div class="cap" style="font-size:12px;color:#7E95AF;margin-bottom:8px">步骤</div>
    <div id="s_steps">${steps}</div>
    <button class="btn" id="s_add" type="button">+ 加一步</button>
  `, [
    { label: "取消", onClick: closeModal },
    {
      label: isNew ? "创建" : "保存", cls: "primary", onClick: async () => {
        const payload = {
          title: formVal("s_title"),
          steps: [...document.querySelectorAll("#s_steps [data-step]")].map((d, i) => ({
            step_no: Number(d.querySelector(".s_no").value) || i + 1,
            action: d.querySelector(".s_act").value.trim(),
            expect: d.querySelector(".s_exp").value.trim(),
            command: d.querySelector(".s_cmd").value.trim(),
          })),
        };
        if (!payload.title) return toast("请填写标题");
        try {
          if (isNew) {
            payload.symptom = formVal("s_sym");
            if (!payload.symptom) return toast("请填写现象标识");
            await api("/sops", { method: "POST", body: JSON.stringify(payload) });
          } else {
            await api("/sops/" + sop.symptom, { method: "PATCH", body: JSON.stringify(payload) });
          }
          toast("已保存"); closeModal(); await refreshPanel();
        } catch (e) { toast("失败：" + e.message); }
      }
    },
  ]);
  $("s_add").onclick = () => {
    const d = document.createElement("div"); d.className = "fldset"; d.setAttribute("data-step", "");
    d.innerHTML = `<div class="fld"><label>第几步</label><input class="s_no" type="number" value="${document.querySelectorAll("#s_steps [data-step]").length + 1}"></div>
      <div class="fld"><label>做什么</label><input class="s_act"></div>
      <div class="fld"><label>期望看到</label><input class="s_exp"></div>
      <div class="fld"><label>命令（可选）</label><input class="s_cmd"></div>
      <button class="btn danger s_del" type="button">删除这一步</button>`;
    $("s_steps").appendChild(d);
    d.querySelector(".s_del").onclick = () => d.remove();
  };
  document.querySelectorAll("#s_steps .s_del").forEach(b => b.onclick = () => b.closest("[data-step]").remove());
}
function openYamlForm(y) {
  const isNew = !y;
  const nopts = ['<option value="">（不关联）</option>'].concat(
    S.graph.nodes.map(n => `<option value="${n.id}" ${y && y.node_id === n.id ? "selected" : ""}>${esc(n.name)}</option>`)
  ).join("");
  openModal(isNew ? "新建 YAML 片段" : "编辑片段", `
    <div class="fld"><label>标题</label><input id="y_title" value="${esc(y ? y.title : "")}"></div>
    <div class="fld"><label>关联组件</label><select id="y_node">${nopts}</select></div>
    <div class="fld"><label>YAML</label><textarea id="y_yaml" style="min-height:180px">${esc(y ? y.yaml : "")}</textarea></div>
  `, [
    { label: "取消", onClick: closeModal },
    {
      label: isNew ? "创建" : "保存", cls: "primary", onClick: async () => {
        const payload = { title: formVal("y_title"), yaml: formVal("y_yaml"), node_id: formVal("y_node") || null };
        if (!payload.title) return toast("请填写标题");
        try {
          if (isNew) await api("/yamls", { method: "POST", body: JSON.stringify(payload) });
          else await api("/yamls/" + y.id, { method: "PATCH", body: JSON.stringify(payload) });
          toast("已保存"); closeModal(); await refreshPanel();
        } catch (e) { toast("失败：" + e.message); }
      }
    },
  ]);
}
function confirmBox(text, onYes) {
  openModal("请确认", `<p style="font-size:13px;color:#C6D6E6;line-height:1.8">${esc(text)}</p>`, [
    { label: "取消", onClick: closeModal },
    { label: "确认删除", cls: "danger", onClick: async () => { closeModal(); await onYes(); } },
  ]);
}

/* ---------------------------------------------------------------- 写操作 */
async function delNode(id) {
  try { await api("/nodes/" + id, { method: "DELETE" }); toast("已删除组件"); await reloadGraph(); }
  catch (e) { toast("失败：" + e.message); }
}
async function delNote(slug) {
  try { await api("/notes/" + slug, { method: "DELETE" }); toast("已删除条目"); await refreshPanel(); }
  catch (e) { toast("失败：" + e.message); }
}
async function delSop(sym) {
  try { await api("/sops/" + sym, { method: "DELETE" }); toast("已删除 SOP"); await refreshPanel(); }
  catch (e) { toast("失败：" + e.message); }
}
async function delYaml(id) {
  try { await api("/yamls/" + id, { method: "DELETE" }); toast("已删除片段"); await refreshPanel(); }
  catch (e) { toast("失败：" + e.message); }
}
async function reloadGraph() {
  await loadGraph(S.source);
  buildSide(); buildLegend(); buildCanvas(); syncLayers(); applyT();
  applyClusterStates();
  if (S.sel && nodeById(S.sel)) select(S.sel, true);
}
async function refreshPanel() { await renderPanel(S.ptab); }

/* 切换数据源（顶栏下拉） */
async function switchSource(next) {
  if (next === S.source) return;
  S.source = next;
  $("srcSel").value = next;
  if (next === "cluster") {
    const okc = await loadCluster();
    if (!okc) { buildCanvas(); applyClusterStates(); return; }
  } else {
    S.cluster = null; S.clusterMeta = null; renderClusterChip();
  }
  await loadGraph(next);
  buildSide(); buildLegend(); buildCanvas(); syncLayers(); applyT();
  applyClusterStates();
  const label = { kb: "知识库（我的数据）", official: "官方全景（出厂数据）", cluster: "集群实况" }[next];
  $("status").textContent = `数据源已切换：${label} · 滚轮缩放 · 双击放大 · 点击查看详情`;
  $("status").classList.add("act");
  if (S.sel && nodeById(S.sel)) select(S.sel, true);
}

/* 集群实况明细 → 右栏键值行 */
function liveRows(detail) {
  if (!detail) return [];
  const rows = [];
  const push = (k, v) => { if (v !== undefined && v !== null && v !== "") rows.push([k, String(v)]); };
  if (detail.version) push("版本", "v" + detail.version);
  if (detail.total !== undefined) push("总数", detail.total);
  if (detail.ready !== undefined) push("就绪", detail.ready);
  if (detail.not_ready !== undefined) push("未就绪", detail.not_ready);
  if (detail.desired !== undefined) push("期望副本", detail.desired);
  if (detail.bound !== undefined) push("已绑定", detail.bound);
  if (detail.with_endpoints !== undefined) push("有后端", detail.with_endpoints);
  if (detail.name) push("识别", detail.name);
  if (detail.clusterIP) push("ClusterIP", detail.clusterIP);
  if (detail.hosts && detail.hosts.length) push("域名", detail.hosts.join("、"));
  if (detail.default && detail.default.length) push("默认", detail.default.join("、"));
  if (detail.versions && detail.versions.length) push("版本", detail.versions.join("、"));
  if (detail.runtimes && detail.runtimes.length) push("运行时", detail.runtimes.join("、"));
  if (detail.by_type) push("按类型", Object.entries(detail.by_type).map(([k, v]) => `${k}×${v}`).join("、"));
  if (detail.by_phase) push("按阶段", Object.entries(detail.by_phase).filter(([, v]) => v).map(([k, v]) => `${k}×${v}`).join("、"));
  if (detail.psa_enforced) push("PSA", Object.entries(detail.psa_enforced).map(([k, v]) => `${k}:${v}`).join("、"));
  if (detail.evidence && detail.evidence.length) push("依据", detail.evidence.join("、"));
  if (detail.items && detail.items.length) {
    push("异常项", detail.items.map(i => `${i.name}${i.reason ? "(" + i.reason + ")" : ""}`).join("、"));
  }
  if (detail.problems && detail.problems.length) {
    push("问题 Pod", detail.problems.map(p => `${p.name}(${p.reason})`).join("、"));
  }
  if (detail.degraded && detail.degraded.length) {
    push("副本不足", detail.degraded.map(d => `${d.namespace}/${d.name} ${d.ready}/${d.desired}`).join("、"));
  }
  if (detail.pending && detail.pending.length) {
    push("未绑定", detail.pending.map(p => `${p.namespace}/${p.name}`).join("、"));
  }
  if (detail.note) push("说明", detail.note);
  if (detail.error) push("错误", detail.error);
  return rows.slice(0, 8);
}

/* 组件 → 常用命令（参数化：把集群实况里的真实名字填进模板；异常时定位命令置顶） */
const CMD_TABLE = {
  apiserver:    [["kubectl cluster-info", 0], ["kubectl get --raw /healthz", 0], ["kubectl version", 0]],
  etcd:         [["kubectl -n kube-system get pods -l component=etcd", 0], ["ETCDCTL_API=3 etcdctl endpoint health", 1]],
  scheduler:    [["kubectl -n kube-system logs deploy/kube-scheduler --tail=100", 0]],
  kcm:          [["kubectl -n kube-system logs deploy/kube-controller-manager --tail=100", 0]],
  coredns:      [["kubectl -n kube-system get svc kube-dns", 0], ["kubectl -n kube-system logs deploy/coredns --tail=50", 0]],
  node:         [["kubectl get nodes -o wide", 0], ["kubectl describe node {name}", 0], ["kubectl top nodes", 0]],
  kubelet:      [["journalctl -u kubelet -n 100 --no-pager", 1], ["systemctl status kubelet", 0]],
  runtime:      [["crictl ps -a", 0], ["crictl info", 0]],
  "kube-proxy": [["kubectl -n kube-system logs ds/kube-proxy --tail=50", 0], ["iptables -t nat -L -n | head -30", 1]],
  cni:          [["kubectl -n kube-system get ds", 0], ["cilium status", 0]],
  service:      [["kubectl get svc -A -o wide", 0], ["kubectl describe svc {name}", 0]],
  endpointslice:[["kubectl get endpointslice -A", 0], ["kubectl describe endpointslice {name}", 0]],
  netpol:       [["kubectl get networkpolicy -A", 0], ["kubectl describe networkpolicy {name}", 0]],
  pod:          [["kubectl get pods -A -o wide", 0], ["kubectl describe pod {name}", 0],
                 ["kubectl logs {name} --tail=100", 0], ["kubectl top pods", 0]],
  deployment:   [["kubectl get deploy -A", 0], ["kubectl describe deploy {name}", 0], ["kubectl rollout status deploy/{name}", 0]],
  statefulset:  [["kubectl get sts -A", 0], ["kubectl describe sts {name}", 0]],
  daemonset:    [["kubectl get ds -A", 0], ["kubectl describe ds {name}", 0]],
  job:          [["kubectl get jobs -A", 0], ["kubectl logs job/{name} --tail=50", 0]],
  hpa:          [["kubectl get hpa -A", 0], ["kubectl describe hpa {name}", 0]],
  pvc:          [["kubectl get pvc -A", 0], ["kubectl describe pvc {name}", 0]],
  pv:           [["kubectl get pv", 0], ["kubectl describe pv {name}", 0]],
  storageclass: [["kubectl get sc", 0], ["kubectl describe sc {name}", 0]],
  csidriver:    [["kubectl get csidrivers", 0]],
  rbac:         [["kubectl get clusterrole,clusterrolebinding", 0], ["kubectl auth can-i --list", 0]],
  sa:           [["kubectl get sa -A", 0]],
  secret:       [["kubectl get secret -A", 0]],
  psa:          [["kubectl get ns -L pod-security.kubernetes.io/enforce", 0]],
  ingress:      [["kubectl get ingress -A", 0], ["kubectl describe ingress {name}", 0]],
  gateway:      [["kubectl get gateway -A", 0], ["kubectl describe gateway {name}", 0]],
  httproute:    [["kubectl get httproute -A", 0], ["kubectl describe httproute {name}", 0]],
  metricsserver: [["kubectl top nodes", 0], ["kubectl get --raw /apis/metrics.k8s.io/v1beta1/nodes", 0]],
  logs:         [["kubectl -n logging get ds", 0], ["kubectl -n logging logs ds/fluent-bit --tail=50", 0]],
  prometheus:   [["curl -s localhost:9090/api/v1/targets | jq .", 0]],
  admission:    [["kubectl get validatingwebhookconfiguration,mutatingwebhookconfiguration", 0]],
};

/* 异常时把最能定位问题的命令顶到最前 */
function orderedCommands(cid, cstate) {
  const base = (CMD_TABLE[cid] || [["kubectl get all -A", 0]]).map(([cmd, isWrite]) => ({ cmd, isWrite }));
  if (cstate !== "unhealthy") return base;
  const top = base.filter(x => /describe|logs|journalctl|status|rollout/.test(x.cmd));
  const rest = base.filter(x => !top.includes(x));
  return [...top, ...rest];
}

/* 把集群实况里的真实对象名填进命令模板 */
function fillCommand(cmd, detail) {
  let name = "";
  if (detail) {
    if (detail.items && detail.items[0]) name = detail.items[0].name;
    else if (detail.problems && detail.problems[0]) name = detail.problems[0].name;
    else if (detail.degraded && detail.degraded[0]) name = detail.degraded[0].name;
    else if (detail.pending && detail.pending[0]) name = detail.pending[0].name;
    else if (detail.hosts && detail.hosts[0]) name = detail.hosts[0];
  }
  return name ? cmd.replace("{name}", name) : cmd.replace(" {name}", "");
}

/* ---------------------------------------------------------------- 杂项 */
function copy(txt) {
  if (!txt) return toast("没有内容可复制");
  const done = () => toast("已复制：" + txt.slice(0, 40));
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(txt).then(done).catch(() => fallback(txt, done));
  } else fallback(txt, done);
}
function fallback(txt, done) {
  const ta = document.createElement("textarea"); ta.value = txt;
  ta.style.cssText = "position:fixed;opacity:0"; document.body.appendChild(ta);
  ta.select();
  try { document.execCommand("copy"); done(); } catch { toast("复制失败，请手动选择"); }
  document.body.removeChild(ta);
}
let _tt;
function toast(msg) {
  const t = $("toast"); t.textContent = msg; t.classList.add("show");
  clearTimeout(_tt); _tt = setTimeout(() => t.classList.remove("show"), 2400);
}
function bindDrag(el, n) {
  el.addEventListener("mousedown", e => {
    if (e.button !== 0) return;
    e.stopPropagation();
    const sx = e.clientX, sy = e.clientY, o = S.offs[n.id] || { x: 0, y: 0 };
    let moved = false;
    const mv = ev => {
      const dx = (ev.clientX - sx) / S.t.s, dy = (ev.clientY - sy) / S.t.s;
      if (Math.abs(dx) > 1.5 || Math.abs(dy) > 1.5) moved = true;
      S.offs[n.id] = { x: o.x + dx, y: o.y + dy };
      place(el, n); scheduleDrawEdges();
    };
    const up = () => {
      document.removeEventListener("mousemove", mv); document.removeEventListener("mouseup", up);
      if (moved) toast("已挪动位置（刷新页面可复原）");
    };
    document.addEventListener("mousemove", mv); document.addEventListener("mouseup", up);
  });
}

/* ---------------------------------------------------------------- 全局事件 */
function bindGlobal() {
  $("modalClose").onclick = closeModal;
  $("modal").addEventListener("click", e => { if (e.target === $("modal")) closeModal(); });

  $("bNew").onclick = () => openNodeForm(null);
  $("bFit").onclick = () => { fit(); toast("已适配全部可见组件"); };
  $("bRead").onclick = () => { const id = S.sel || (S.graph.nodes[0] || {}).id; if (id) zoomTo(id); };
  $("bLink").onclick = () => {
    S.links = !S.links; $("bLink").classList.toggle("on", S.links);
    $("elayer").style.display = S.links ? "" : "none";
    toast(S.links ? "已显示连线" : "已隐藏连线");
  };
  $("bAnim").onclick = () => {
    S.anim = !S.anim; $("bAnim").classList.toggle("on", S.anim); scheduleDrawEdges();
    toast(S.anim ? "已开启流动动画" : "已关闭流动动画");
  };
  $("bExport").onclick = async () => {
    try {
      const data = await api("/io/export");
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "atlas-export.json";
      a.click();
      toast("已导出全库 JSON");
    } catch (e) { toast("导出失败：" + e.message); }
  };
  $("bK").onclick = () => { $("q").focus(); $("q").select(); };
  $("srcSel").onchange = e => switchSource(e.target.value);
  applyTheme(currentTheme());
  $("bTheme").onclick = toggleTheme;
  matchMedia("(prefers-color-scheme: light)").addEventListener?.("change", () => {
    if (!localStorage.getItem(THEME_KEY)) applyTheme(currentTheme());
  });
  $("brand").onclick = async () => { await reloadGraph(); toast("已从服务端重新拉取数据"); };
  $("bSide").onclick = () => $("side").classList.toggle("open");
  $("bInsp").onclick = () => $("insp").classList.toggle("open");

  let timer;
  $("q").addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(() => doSearch($("q").value), 200);
  });
  $("q").addEventListener("keydown", e => {
    if (e.key === "Enter") doSearch($("q").value);
    if (e.key === "Escape") { $("q").value = ""; doSearch(""); }
  });
  window.addEventListener("keydown", e => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); $("q").focus(); $("q").select(); }
    if (e.key === "Escape" && !$("modal").hidden) closeModal();
  });
  let rt;
  window.addEventListener("resize", () => { clearTimeout(rt); rt = setTimeout(applyT, 120); });
}
async function doSearch(q) {
  q = q.trim();
  if (!q) {
    document.querySelectorAll(".node").forEach(d => d.classList.remove("hit", "dim"));
    $("qhint").textContent = "";
    return;
  }
  const k = q.toLowerCase();
  let hit = 0, first = null;
  document.querySelectorAll(".node").forEach(d => {
    const n = nodeById(d.dataset.id);
    const hay = (n.name + " " + n.kind + " " + (n.fields || []).map(f => f.label + f.value).join(" ") + " " + n.summary + " " + n.cmd).toLowerCase();
    const ok = hay.includes(k);
    d.classList.toggle("hit", ok); d.classList.toggle("dim", !ok);
    if (ok) { hit++; if (!first) first = n.id; }
  });
  $("qhint").textContent = hit ? hit + " 项" : "无结果";
  if (first) { select(first, true, true); center(first, Math.max(S.t.s, .9)); }
}
function bindCanvas() {
  const vp = $("viewport");
  let pan = null;
  vp.addEventListener("mousedown", e => {
    if (e.button !== 0) return;
    pan = { x: e.clientX, y: e.clientY, tx: S.t.x, ty: S.t.y };
    vp.classList.add("grabbing");
  });
  window.addEventListener("mousemove", e => {
    if (!pan) return;
    S.t.x = pan.tx + (e.clientX - pan.x); S.t.y = pan.ty + (e.clientY - pan.y);
    applyT();
  });
  window.addEventListener("mouseup", () => { pan = null; vp.classList.remove("grabbing"); });
  vp.addEventListener("click", e => {
    if (e.target.closest(".node")) return;
    S.sel = null;
    document.querySelectorAll(".node").forEach(d => d.classList.remove("sel"));
    scheduleDrawEdges();
  });
  vp.addEventListener("wheel", e => {
    e.preventDefault();
    const r = vp.getBoundingClientRect();
    zoom(e.deltaY < 0 ? 1.12 : 1 / 1.12, e.clientX - r.left, e.clientY - r.top);
  }, { passive: false });
  $("zIn").onclick = () => zoom(1.2);
  $("zOut").onclick = () => zoom(1 / 1.2);
  $("zFit").onclick = () => fit();
}

window.addEventListener("DOMContentLoaded", boot);
