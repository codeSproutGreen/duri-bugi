window.AppMixins = window.AppMixins || {};
window.AppMixins.dashboard = {
  dash: { total_asset: 0, total_liability: 0, total_income: 0, total_expense: 0, net_worth: 0, accounts: [], pending_count: 0 },
  monthly: [],
  pendingCount: 0,

  async loadDashboard() {
    this.dash = await this.get('/dashboard');
    this.pendingCount = this.dash.pending_count;
    this.monthly = await this.get('/dashboard/monthly?months=6');
  },

  _startPendingPoll() {
    if (this._pendingTimer) return;
    this._pendingTimer = setInterval(async () => {
      try {
        const res = await this.get('/dashboard/pending-count');
        const newCount = res.count;
        if (newCount !== this.pendingCount) {
          this.pendingCount = newCount;
          if (this.page === 'review') this.loadEntries(0);
        }
      } catch {}
    }, 10000);
  },

  groupedAccounts(type) {
    const all = (this.dash.accounts || []).filter(x => x.type === type);
    const byId = {};
    for (const a of all) byId[a.id] = a;
    const leafSum = (id) => {
      const children = all.filter(a => a.parent_id === id);
      let s = 0;
      for (const c of children) s += c.is_group ? leafSum(c.id) : c.balance;
      return s;
    };
    const result = [];
    const addNode = (node, depth) => {
      const children = all.filter(a => a.parent_id === node.id);
      children.sort((a, b) => a.code.localeCompare(b.code));
      if (node.is_group) {
        if (children.length === 0) return;
        result.push({ ...node, _isGroup: true, _subtotal: leafSum(node.id), _depth: depth });
        for (const c of children) addNode(c, depth + 1);
      } else {
        result.push({ ...node, _isGroup: false, _depth: depth });
      }
    };
    const roots = all.filter(a => !a.parent_id || !byId[a.parent_id]);
    roots.sort((a, b) => a.code.localeCompare(b.code));
    for (const r of roots) addNode(r, 0);
    return result;
  },
};
