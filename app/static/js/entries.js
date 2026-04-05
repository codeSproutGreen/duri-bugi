window.AppMixins = window.AppMixins || {};
window.AppMixins.entries = {
  entries: [],
  searchQuery: '',
  filterDebitIds: [],
  filterCreditIds: [],
  showFilterPanel: false,
  filterOpenTypes: {},
  filterShowAllDebit: false,
  filterShowAllCredit: false,
  txnGroupFilter: {},
  bookmarkedDebitIds: JSON.parse(localStorage.getItem('bookmarkedDebitIds') || '[]'),
  bookmarkedCreditIds: JSON.parse(localStorage.getItem('bookmarkedCreditIds') || '[]'),
  _lastConfirmed: null,
  selectedEntryIds: [],

  showEditModal: false,
  selectedEntryId: null,
  showAcctPicker: null,
  showDebitTip: false,
  showCreditTip: false,
  showSearchTip: false,
  editingEntry: {},
  editAmount: 0,
  editAmountRaw: '',
  editDebitAcct: 0,
  editCreditAcct: 0,
  acctGroupFilter: {},

  toggleSelectEntry(id) {
    const idx = this.selectedEntryIds.indexOf(id);
    if (idx >= 0) this.selectedEntryIds.splice(idx, 1);
    else this.selectedEntryIds.push(id);
  },

  isEntrySelected(id) {
    return this.selectedEntryIds.includes(id);
  },

  selectAllEntries() {
    this.selectedEntryIds = this.entries.map(e => e.id);
  },

  clearSelection() {
    this.selectedEntryIds = [];
  },

  allSelected() {
    return this.entries.length > 0 && this.selectedEntryIds.length === this.entries.length;
  },

  async confirmSelected() {
    const ids = [...this.selectedEntryIds];
    this.selectedEntryIds = [];
    for (const id of ids) {
      await this.post(`/entries/${id}/confirm`);
    }
    this.entries = this.entries.filter(e => !ids.includes(e.id));
    this.pendingCount = Math.max(0, this.pendingCount - ids.length);
    this.loadDashboard();
  },

  async loadEntries(confirmed) {
    if (confirmed !== null && confirmed !== undefined) this._lastConfirmed = confirmed;
    let url = '/entries?limit=100';
    if (this._lastConfirmed !== null && this._lastConfirmed !== undefined) url += `&confirmed=${this._lastConfirmed}`;
    if (this.searchQuery) url += `&search=${encodeURIComponent(this.searchQuery)}`;
    if (this.filterDebitIds.length) url += `&debit_accounts=${this.filterDebitIds.join(',')}`;
    if (this.filterCreditIds.length) url += `&credit_accounts=${this.filterCreditIds.join(',')}`;
    this.entries = await this.get(url);
  },

  toggleFilterAcct(side, id) {
    const arr = side === 'debit' ? this.filterDebitIds : this.filterCreditIds;
    const idx = arr.indexOf(id);
    if (idx >= 0) arr.splice(idx, 1); else arr.push(id);
    this.loadEntries();
  },

  clearFilters() {
    this.filterDebitIds = [];
    this.filterCreditIds = [];
    this.searchQuery = '';
    this.loadEntries();
  },

  hasActiveFilters() {
    return this.filterDebitIds.length > 0 || this.filterCreditIds.length > 0;
  },

  async confirmEntry(id) {
    await this.post(`/entries/${id}/confirm`);
    this.entries = this.entries.filter(e => e.id !== id);
    this.selectedEntryIds = this.selectedEntryIds.filter(i => i !== id);
    this.pendingCount = Math.max(0, this.pendingCount - 1);
    this.loadDashboard();
  },

  async rejectEntry(id) {
    await this.post(`/entries/${id}/reject`);
    this.entries = this.entries.filter(e => e.id !== id);
    this.selectedEntryIds = this.selectedEntryIds.filter(i => i !== id);
    this.pendingCount = Math.max(0, this.pendingCount - 1);
  },

  parseInstallment(raw) {
    if (!raw) return null;
    const m = raw.replace(/,/g, '').match(/^(\d+)\s*\/\s*(\d+)$/);
    if (!m) return null;
    const total = Number(m[1]);
    const months = Number(m[2]);
    if (!total || months < 2 || months > 60) return null;
    const monthly = Math.floor(total / months / 100) * 100;
    const first = total - monthly * (months - 1);
    return { total, months, monthly, first };
  },

  installmentInfo() {
    return this.parseInstallment(this.editAmountRaw);
  },

  newEntry() {
    const today = new Date().toISOString().slice(0, 10);
    this.editingEntry = { id: 0, entry_date: today, description: '', memo: '', lines: [], is_confirmed: 0 };
    this.editAmount = 0;
    this.editAmountRaw = '';
    this.editDebitAcct = this.allAccounts.find(a => a.type === 'expense' && !a.is_group)?.id || 0;
    this.editCreditAcct = this.allAccounts.find(a => a.type === 'liability' && !a.is_group)?.id || 0;
    this.loadAllAccounts();
  },

  async saveEntry() {
    if (!this.editAmount || this.editAmount <= 0) return alert('금액을 입력하세요');
    if (!this.editDebitAcct || !this.editCreditAcct) return alert('계정을 선택하세요');

    const data = {
      entry_date: this.editingEntry.entry_date,
      description: this.editingEntry.description,
      memo: this.editingEntry.memo || '',
      lines: [
        { account_id: this.editDebitAcct, debit: this.editAmount, credit: 0 },
        { account_id: this.editCreditAcct, debit: 0, credit: this.editAmount },
      ],
    };

    if (this.editingEntry.id) {
      await this.put(`/entries/${this.editingEntry.id}`, data);
    } else {
      await this.post('/entries', data);
    }

    this.showEditModal = false;
    if (this.page === 'review') this.loadEntries(0);
    else if (this.page === 'transactions') this.loadEntries(1);
    this.loadDashboard();
  },

  async quickSaveEntry() {
    const inst = this.installmentInfo();
    const amount = inst ? inst.total : this.editAmount;
    if (!amount || amount <= 0) return alert('금액을 입력하세요');
    if (!this.editDebitAcct || !this.editCreditAcct) return alert('계정을 선택하세요');
    if (!this.editingEntry.description) return alert('설명을 입력하세요');

    if (inst) {
      // 할부: 여러 건 생성
      const baseDate = new Date(this.editingEntry.entry_date + 'T00:00:00');
      const baseMemo = this.editingEntry.memo || '';
      for (let i = 0; i < inst.months; i++) {
        const d = new Date(baseDate);
        d.setMonth(d.getMonth() + i);
        const dateStr = d.toISOString().slice(0, 10);
        const amt = i === 0 ? inst.first : inst.monthly;
        const memo = (baseMemo ? baseMemo + ' / ' : '') + `할부 ${i + 1}/${inst.months}`;
        await this.post('/entries', {
          entry_date: dateStr,
          description: this.editingEntry.description,
          memo,
          lines: [
            { account_id: this.editDebitAcct, debit: amt, credit: 0 },
            { account_id: this.editCreditAcct, debit: 0, credit: amt },
          ],
        });
      }
    } else {
      await this.post('/entries', {
        entry_date: this.editingEntry.entry_date,
        description: this.editingEntry.description,
        memo: this.editingEntry.memo || '',
        lines: [
          { account_id: this.editDebitAcct, debit: this.editAmount, credit: 0 },
          { account_id: this.editCreditAcct, debit: 0, credit: this.editAmount },
        ],
      });
    }

    const keepDate = this.editingEntry.entry_date;
    const keepDebit = this.editDebitAcct;
    const keepCredit = this.editCreditAcct;
    this.editingEntry = { id: 0, entry_date: keepDate, description: '', memo: '', lines: [], is_confirmed: 0 };
    this.editAmount = 0;
    this.editAmountRaw = '';
    this.editDebitAcct = keepDebit;
    this.editCreditAcct = keepCredit;
    this.showAcctPicker = null;

    this.loadEntries(1);
    this.loadDashboard();
  },

  deleteConfirmId: null,
  deleteConfirmInstallment: false,

  deleteEntry(id) {
    const entry = this.entries.find(e => e.id === id);
    this.deleteConfirmId = id;
    this.deleteConfirmInstallment = !!(entry && /할부 \d+\/\d+$/.test(entry.memo));
  },

  async doDelete(mode) {
    const id = this.deleteConfirmId;
    this.deleteConfirmId = null;
    if (!id) return;
    if (mode === 'all') {
      await this.del(`/entries/${id}/installment-group`);
    } else {
      await this.del(`/entries/${id}`);
    }
    this.loadEntries(1);
    this.loadDashboard();
  },

  async editExistingEntry(e) {
    await this.loadAllAccounts();
    this.editingEntry = { ...e };
    this.editAmount = e.lines.reduce((s, l) => s + l.debit, 0);
    this.editAmountRaw = '';
    this.editDebitAcct = e.lines.find(l => l.debit > 0)?.account_id || 0;
    this.editCreditAcct = e.lines.find(l => l.credit > 0)?.account_id || 0;
    this.showEditModal = true;
  },

  // ── Account selectors & groups ──
  selectableAccounts() {
    return this.allAccounts.filter(a => !a.is_group);
  },

  groupedSelectableAccounts() {
    const typeOrder = ['asset', 'liability', 'expense', 'income', 'equity'];
    const byId = {};
    for (const a of this.allAccounts) byId[a.id] = a;
    const result = [];
    for (const type of typeOrder) {
      const all = this.allAccounts.filter(a => a.type === type);
      if (!all.some(a => !a.is_group)) continue;
      const items = [];
      const addNode = (node, depth) => {
        const children = all.filter(a => a.parent_id === node.id);
        children.sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0) || a.code.localeCompare(b.code));
        if (node.is_group) {
          items.push({ id: 'g_' + node.id, name: node.name, isHeader: true, depth });
          for (const c of children) addNode(c, depth + 1);
        } else {
          items.push({ id: node.id, code: node.code, name: node.name, isHeader: false, depth });
        }
      };
      const roots = all.filter(a => !a.parent_id || !byId[a.parent_id] || byId[a.parent_id].type !== type);
      roots.sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0) || a.code.localeCompare(b.code));
      for (const r of roots) addNode(r, 0);
      result.push({ type, label: this.accountTypeLabel(type), items });
    }
    return result;
  },

  quickAccounts(type) {
    if (type === 'expense') {
      return this.allAccounts.filter(a => a.type === 'expense' && !a.is_group).slice(0, 8);
    }
    return this.allAccounts.filter(a => (a.type === 'asset' || a.type === 'liability') && !a.is_group).slice(0, 8);
  },

  acctGroupLabel(accountId) {
    const a = this.allAccounts.find(x => x.id === accountId);
    if (!a || !a.parent_id) return '';
    let cur = this.allAccounts.find(x => x.id === a.parent_id);
    while (cur && cur.parent_id) {
      const p = this.allAccounts.find(x => x.id === cur.parent_id);
      if (p) cur = p; else break;
    }
    return cur ? cur.name : '';
  },

  acctWithBadge(lines, side) {
    return lines.filter(l => side === 'debit' ? l.debit > 0 : l.credit > 0)
      .map(l => {
        const grp = this.acctGroupLabel(l.account_id);
        const color = grp ? this.groupColors[grp] : null;
        if (color) {
          return `<span style="padding:1px 6px;border-radius:4px;background:${color}30;border-left:3px solid ${color}">${l.account_name}</span>`;
        }
        return l.account_name;
      }).join(', ');
  },

  // ── Group filters (quick entry) ──
  availableGroups() {
    const all = this.allAccounts.filter(a => a.is_group);
    const byName = {};
    for (const g of all) {
      if (!byName[g.name]) {
        byName[g.name] = { name: g.name, ids: [] };
      }
      byName[g.name].ids.push(g.id);
    }
    return Object.values(byName);
  },

  initGroupFilter() {
    const all = this.allAccounts.filter(a => a.is_group);
    const updated = { ...this.acctGroupFilter };
    let changed = false;
    for (const g of all) {
      if (!(g.id in updated)) {
        updated[g.id] = true;
        changed = true;
      }
    }
    if (changed) this.acctGroupFilter = updated;
  },

  toggleGroupFilter(ids) {
    const newVal = !this.acctGroupFilter[ids[0]];
    const updated = { ...this.acctGroupFilter };
    for (const id of ids) updated[id] = newVal;
    this.acctGroupFilter = updated;
  },

  isGroupVisible(groupId) {
    return this.acctGroupFilter[groupId] !== false;
  },

  isGroupNameVisible(ids) {
    return ids.some(id => this.acctGroupFilter[id] !== false);
  },

  // ── Group filters (transaction list) ──
  initTxnGroupFilter() {
    const all = this.allAccounts.filter(a => a.is_group);
    const updated = { ...this.txnGroupFilter };
    let changed = false;
    for (const g of all) {
      if (!(g.id in updated)) { updated[g.id] = true; changed = true; }
    }
    if (changed) this.txnGroupFilter = updated;
  },

  toggleTxnGroupFilter(ids) {
    const newVal = !this.txnGroupFilter[ids[0]];
    const updated = { ...this.txnGroupFilter };
    for (const id of ids) updated[id] = newVal;
    this.txnGroupFilter = updated;
  },

  isTxnGroupVisible(groupId) {
    return this.txnGroupFilter[groupId] !== false;
  },

  isTxnGroupNameVisible(ids) {
    return ids.some(id => this.txnGroupFilter[id] !== false);
  },

  // ── Bookmarks ──
  toggleBookmark(side, id) {
    const arr = side === 'debit' ? this.bookmarkedDebitIds : this.bookmarkedCreditIds;
    const key = side === 'debit' ? 'bookmarkedDebitIds' : 'bookmarkedCreditIds';
    const idx = arr.indexOf(id);
    if (idx >= 0) arr.splice(idx, 1); else arr.push(id);
    localStorage.setItem(key, JSON.stringify(arr));
  },

  isBookmarked(side, id) {
    return (side === 'debit' ? this.bookmarkedDebitIds : this.bookmarkedCreditIds).includes(id);
  },

  bookmarkedAccounts(side) {
    const ids = side === 'debit' ? this.bookmarkedDebitIds : this.bookmarkedCreditIds;
    const accts = this.allAccounts.filter(a => {
      if (a.is_group || !ids.includes(a.id)) return false;
      if (a.parent_id && !this.isTxnGroupVisible(a.parent_id)) return false;
      return true;
    }).sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0));
    const typeOrder = ['expense', 'income', 'asset', 'liability', 'equity'];
    const grouped = [];
    for (const type of typeOrder) {
      const items = accts.filter(a => a.type === type);
      if (items.length) grouped.push({ type, label: this.accountTypeLabel(type), items });
    }
    return grouped;
  },

  allGroupedAccounts() {
    const typeOrder = ['expense', 'income', 'asset', 'liability', 'equity'];
    const result = [];
    for (const type of typeOrder) {
      const accts = this.allAccounts.filter(a => a.type === type && !a.is_group);
      if (!accts.length) continue;
      const groups = [];
      const groupMap = {};
      for (const a of accts) {
        const pid = a.parent_id || 0;
        if (pid && !this.isGroupVisible(pid)) continue;
        if (!groupMap[pid]) {
          const parent = pid ? this.allAccounts.find(p => p.id === pid) : null;
          groupMap[pid] = { label: parent ? parent.name : null, accounts: [], sort: parent ? parent.sort_order : 99999 };
          groups.push(groupMap[pid]);
        }
        groupMap[pid].accounts.push(a);
      }
      groups.sort((a, b) => a.sort - b.sort);
      if (groups.length) result.push({ type, label: this.accountTypeLabel(type), groups });
    }
    return result;
  },
};
