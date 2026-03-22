window.AppMixins = window.AppMixins || {};
window.AppMixins.utils = {
  // ── API helpers ──
  async get(url) {
    const r = await fetch(API + url);
    return r.json();
  },
  async post(url, body) {
    const r = await fetch(API + url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    return r.json();
  },
  async put(url, body) {
    const r = await fetch(API + url, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    return r.json();
  },
  async del(url) {
    const r = await fetch(API + url, { method: 'DELETE' });
    return r.json();
  },

  // ── Formatters ──
  fmt(n) {
    if (n == null) return '0';
    return n.toLocaleString('ko-KR') + '원';
  },
  fmtTimestamp(ts) {
    return new Date(ts).toLocaleString('ko-KR', {
      month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit'
    });
  },
  fmtTime(dt) {
    if (!dt) return '';
    const t = dt.indexOf('T');
    if (t < 0) return '';
    return dt.slice(t + 1, t + 6);
  },
  fmtDate(d) {
    if (!d) return '';
    if (window.innerWidth <= 768) return d.slice(5).replace('-', '/');
    return d;
  },
  typeLabel(t) {
    return { asset: '자산', liability: '부채', equity: '자본', income: '수입', expense: '비용' }[t] || t;
  },
  accountTypeLabel(type) {
    return { asset: '자산', liability: '부채', equity: '자본', income: '수익', expense: '비용' }[type] || type;
  },
};
