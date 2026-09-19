/**
 * Windowed table: fixed row height, overscan, server-backed pages.
 * Never mounts more than ~viewport + overscan rows.
 */
export function createVirtualTable(opts) {
  const {
    mount,
    columns,
    rowHeight = 36,
    overscan = 8,
    pageSize = 80,
    fetchPage,
    renderRow,
    onRowClick,
  } = opts;

  const state = {
    items: [],
    total: 0,
    cursor: null,
    loading: false,
    done: false,
    top: 0,
  };

  mount.innerHTML = `
    <div class="vt-wrap">
      <div class="vt-head">${columns.map(c => `<div class="vt-th" style="flex:${c.flex||1}">${c.label}</div>`).join("")}</div>
      <div class="vt-view" tabindex="0"></div>
    </div>`;
  const view = mount.querySelector(".vt-view");

  function visibleCount() {
    return Math.ceil(view.clientHeight / rowHeight) + overscan * 2;
  }

  function paint() {
    const start = Math.max(0, Math.floor(view.scrollTop / rowHeight) - overscan);
    const end = Math.min(state.items.length, start + visibleCount());
    const topPad = start * rowHeight;
    const bottomPad = Math.max(0, (state.total || state.items.length) * rowHeight - end * rowHeight);
    const slice = state.items.slice(start, end);
    view.innerHTML = `<div class="vt-spacer" style="height:${topPad}px"></div>
      ${slice.map((row, i) => renderRow(row, start + i)).join("")}
      <div class="vt-spacer" style="height:${bottomPad}px"></div>`;
    view.querySelectorAll("[data-id]").forEach(el => {
      el.onclick = ev => onRowClick && onRowClick(el.dataset.id, ev, el);
    });
  }

  async function loadMore() {
    if (state.loading || state.done) return;
    state.loading = true;
    const data = await fetchPage({ limit: pageSize, after: state.cursor, offset: state.items.length });
    state.items.push(...(data.items || []));
    if (data.total != null) state.total = data.total;
    else state.total = Math.max(state.total, state.items.length + (data.has_more ? pageSize : 0));
    state.cursor = data.next ?? null;
    if (!data.has_more || !data.items || !data.items.length) state.done = true;
    state.loading = false;
    paint();
  }

  view.addEventListener("scroll", () => {
    paint();
    const remain = view.scrollHeight - view.scrollTop - view.clientHeight;
    if (remain < rowHeight * 12) loadMore();
  });

  return {
    reset() {
      state.items = [];
      state.total = 0;
      state.cursor = null;
      state.done = false;
      view.scrollTop = 0;
      return loadMore();
    },
    get items() { return state.items; },
    paint,
  };
}
