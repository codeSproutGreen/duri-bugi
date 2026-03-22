window.AppMixins = window.AppMixins || {};
window.AppMixins.assets = {
  assetTab: 'summary',
  assetSummary: { cash_bank: 0, total_liability: 0, stocks_total: 0, stocks_by_person: [], realestate_total: 0, realestate_items: [], total_assets: 0, net_worth: 0 },
  stockPersons: [],
  realEstateItems: [],
  showStockPersonModal: false,
  showStockAccountModal: false,
  showStockHoldingModal: false,
  showStockSellModal: false,
  showRealEstateModal: false,
  editingStockPerson: {},
  editingStockAccount: {},
  editingStockHolding: {},
  sellingStockHolding: {},
  editingRealEstate: {},
  priceRefreshing: false,
  _holdingSortables: [],

  assetPct(key) {
    const total = this.assetSummary.total_assets;
    if (!total) return '0';
    return Math.round(this.assetSummary[key] / total * 100);
  },
  assetPctVal(val) {
    const total = this.assetSummary.total_assets;
    if (!total) return '0';
    return Math.round(val / total * 100);
  },

  stocksSectionAccounts(type) {
    return (this.assetSummary.stocks_by_person || []).flatMap(p => p.accounts.filter(a => a.account_type === type));
  },
  stocksSectionTotal(type) {
    return this.stocksSectionAccounts(type).reduce((s, a) => s + a.total_value, 0);
  },
  stocksCashTotal() { return this.stocksSectionTotal('cash'); },
  stocksPensionTotal() { return this.stocksSectionTotal('pension'); },

  groupByBrokerage(accounts) {
    const map = {};
    for (const a of accounts) {
      const b = a.brokerage || '기타';
      if (!map[b]) map[b] = { brokerage: b, accounts: [] };
      map[b].accounts.push(a);
    }
    return Object.values(map);
  },

  async loadAssetSummary() {
    this.assetSummary = await this.get('/assets/summary');
  },

  async loadStockPersons() {
    this.stockPersons = await this.get('/assets/stock/persons');
    this.loadAssetSummary();
  },

  async loadRealEstate() {
    this.realEstateItems = await this.get('/assets/realestate');
    this.loadAssetSummary();
  },

  async saveStockPerson() {
    if (!this.editingStockPerson.name) return alert('이름을 입력하세요');
    if (this.editingStockPerson.id) {
      await this.put(`/assets/stock/persons/${this.editingStockPerson.id}`, { name: this.editingStockPerson.name });
    } else {
      await this.post('/assets/stock/persons', { name: this.editingStockPerson.name });
    }
    this.showStockPersonModal = false;
    this.loadStockPersons();
  },

  async deleteStockPerson(id) {
    await this.del(`/assets/stock/persons/${id}`);
    this.loadStockPersons();
  },

  async saveStockAccount() {
    if (!this.editingStockAccount.name) return alert('계좌명을 입력하세요');
    const data = {
      person_id: this.editingStockAccount.person_id,
      brokerage: this.editingStockAccount.brokerage || '',
      name: this.editingStockAccount.name,
      account_type: this.editingStockAccount.account_type || 'cash',
      linked_account_id: this.editingStockAccount.linked_account_id || null,
    };
    if (this.editingStockAccount.id) {
      await this.put(`/assets/stock/accounts/${this.editingStockAccount.id}`, data);
    } else {
      await this.post('/assets/stock/accounts', data);
    }
    this.showStockAccountModal = false;
    this.loadStockPersons();
  },

  async deleteStockAccount(id) {
    await this.del(`/assets/stock/accounts/${id}`);
    this.loadStockPersons();
  },

  async lookupTicker() {
    const h = this.editingStockHolding;
    const ticker = h.ticker?.trim();
    if (!ticker || ticker.length < 2) return;
    try {
      const ex = h.is_foreign ? `?exchange=${h.exchange || 'O'}` : '';
      const res = await this.get(`/assets/stock/lookup/${ticker}${ex}`);
      if (res && res.name) {
        h.name = res.name;
      }
    } catch (e) { /* not found */ }
  },

  async saveStockHolding() {
    const h = this.editingStockHolding;
    if (!h.ticker || !h.name) return alert('종목코드와 이름을 입력하세요');
    const exchange = h.is_foreign ? (h.exchange || 'O') : null;
    if (h.id) {
      await this.put(`/assets/stock/holdings/${h.id}`, { ticker: h.ticker, name: h.name, exchange, quantity: h.quantity, avg_price: h.avg_price });
    } else {
      await this.post('/assets/stock/holdings', { account_id: h.account_id, ticker: h.ticker, name: h.name, exchange, quantity: h.quantity, avg_price: h.avg_price });
    }
    this.showStockHoldingModal = false;
    this.loadStockPersons();
  },

  async deleteStockHolding(id) {
    await this.del(`/assets/stock/holdings/${id}`);
    this.loadStockPersons();
  },

  initHoldingSortable(el, accountId) {
    if (typeof Sortable === 'undefined') return;
    Sortable.create(el, {
      handle: '.dnd-handle',
      animation: 200,
      ghostClass: 'sortable-ghost',
      onEnd: async () => {
        const rows = Array.from(el.querySelectorAll('tr[data-id]'));
        const data = rows.map((r, i) => ({ id: Number(r.dataset.id), sort_order: i }));
        await this.put('/assets/stock/holdings/reorder', data);
        this.loadStockPersons();
      },
    });
  },

  async sellStockHolding() {
    const s = this.sellingStockHolding;
    if (!s.sell_quantity || s.sell_quantity <= 0) return alert('매도 수량을 입력하세요');
    if (!s.sell_price || s.sell_price <= 0) return alert('매도 단가를 입력하세요');
    const r = await fetch(API + '/assets/stock/sell', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ holding_id: s.id, quantity: parseInt(s.sell_quantity), sell_price: parseInt(s.sell_price), fee: parseInt(s.fee) || 0 }),
    });
    const res = await r.json();
    if (!r.ok) {
      alert(res.detail || '매도 실패');
      return;
    }
    const gl = res.realized_gain_loss;
    const glText = gl >= 0 ? `+${this.fmt(gl)}` : this.fmt(gl);
    let msg = `매도 완료\n매도대금: ${this.fmt(res.proceeds)}`;
    if (res.fee) msg += `\n수수료: ${this.fmt(res.fee)}`;
    msg += `\n실현손익: ${glText}`;
    alert(msg);
    this.showStockSellModal = false;
    this.loadStockPersons();
    if (this.assetTab === 'summary') await this.loadAssetSummary();
  },

  async refreshStockPrices() {
    this.priceRefreshing = true;
    try {
      await this.post('/assets/stock/refresh-prices', {});
      await this.loadStockPersons();
      if (this.assetTab === 'summary') await this.loadAssetSummary();
    } finally {
      this.priceRefreshing = false;
    }
  },

  async saveRealEstate() {
    const r = this.editingRealEstate;
    if (!r.name) return alert('이름을 입력하세요');
    if (r.id) {
      await this.put(`/assets/realestate/${r.id}`, { name: r.name, value: r.value, memo: r.memo });
    } else {
      await this.post('/assets/realestate', { name: r.name, value: r.value, memo: r.memo });
    }
    this.showRealEstateModal = false;
    this.loadRealEstate();
  },

  async deleteRealEstate(id) {
    await this.del(`/assets/realestate/${id}`);
    this.loadRealEstate();
  },
};
