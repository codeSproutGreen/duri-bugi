const API = '/api';

function app() {
  return {
    page: 'dashboard',
    theme: localStorage.getItem('theme') || 'dark',
    themePresets: [
      { id: 'dark', name: 'Forest Dark', icon: '🌲', dark: true },
      { id: 'light', name: 'Forest Light', icon: '🌿', dark: false },
      { id: 'ocean-dark', name: 'Ocean Dark', icon: '🌊', dark: true },
      { id: 'ocean-light', name: 'Ocean Light', icon: '🏖️', dark: false },
      { id: 'sunset-dark', name: 'Sunset Dark', icon: '🌅', dark: true },
      { id: 'sunset-light', name: 'Sunset Light', icon: '☀️', dark: false },
      { id: 'sage', name: 'Sage', icon: '🍵', dark: false },
      { id: 'tropical', name: 'Tropical', icon: '🌺', dark: false },
      { id: 'blossom', name: 'Blossom', icon: '🌸', dark: false },
      { id: 'midnight', name: 'Midnight', icon: '🌑', dark: true },
    ],
    sidebarOpen: localStorage.getItem('sidebar') !== 'collapsed',
    groupColors: JSON.parse(localStorage.getItem('groupColors') || '{}'),

    // PIN auth
    pinRequired: false,
    pinAuthenticated: false,
    pinInput: '',
    pinError: '',
    pinLocked: false,
    currentUser: '',

    // Dashboard
    dash: { total_asset: 0, total_liability: 0, total_income: 0, total_expense: 0, net_worth: 0, accounts: [], pending_count: 0 },
    monthly: [],
    pendingCount: 0,

    // Entries
    entries: [],
    searchQuery: '',
    filterDebitIds: [],
    filterCreditIds: [],
    showFilterPanel: false,
    filterOpenTypes: {},
    _lastConfirmed: null,

    // Accounts
    acctList: {},
    acctTab: 'asset',
    allAccounts: [],
    inlineEditId: 0,
    inlineEditName: '',
    _sortables: [],

    // Report
    reportStart: (() => { const d = new Date(); const y = d.getFullYear(), m = d.getMonth() - 11; const s = new Date(y, m, 1); return `${s.getFullYear()}-${String(s.getMonth()+1).padStart(2,'0')}-01`; })(),
    reportEnd: (() => { const d = new Date(); const y = d.getFullYear(), m = d.getMonth(); return `${y}-${String(m+1).padStart(2,'0')}-${String(new Date(y, m+1, 0).getDate()).padStart(2,'0')}`; })(),
    reportData: [],
    reportShowAsset: true,
    reportShowLiability: true,
    reportTab: 'trend',
    periodMode: 'custom',
    periodYear: String(new Date().getFullYear()),
    periodMonth: new Date().getMonth() + 1,
    periodQuarter: Math.ceil((new Date().getMonth() + 1) / 3),
    reportShowNetWorth: true,
    _chart: null,
    incExp: { expense: [], income: [], total_expense: 0, total_income: 0, net_income: 0 },

    // Assets
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

    // Messages
    messages: [],
    msgFilter: null,

    // Modals & input
    showEditModal: false,
    selectedEntryId: null,
    showAcctPicker: null,
    showDebitTip: false,
    showCreditTip: false,
    editingEntry: {},
    editAmount: 0,
    editDebitAcct: 0,
    editCreditAcct: 0,
    showAcctModal: false,
    editingAcct: {},
    rules: [],
    showRuleModal: false,
    editingRule: {},
    acctGroupFilter: {},  // { groupId: true/false } — checked groups show their children

    async init() {
      // Check PIN auth first
      const authRes = await fetch('/api/auth/check');
      const auth = await authRes.json();
      this.pinRequired = auth.pin_required;
      this.pinAuthenticated = auth.authenticated;
      this.currentUser = auth.user || '';
      if (!this.pinRequired || this.pinAuthenticated) {
        this.applyPeriod();
        await this.loadDashboard();
        this._startPendingPoll();
      }
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

    pinKeyPress(key) {
      if (this.pinLocked) return;
      if (key === 'del') {
        this.pinInput = this.pinInput.slice(0, -1);
        this.pinError = '';
        return;
      }
      if (key === 'submit') {
        if (this.pinInput.length > 0) this.submitPin();
        return;
      }
      if (typeof key === 'number') {
        this.pinInput += String(key);
        this.pinError = '';
      }
    },

    async submitPin() {
      try {
        const res = await fetch('/api/auth/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ pin: this.pinInput }),
        });
        if (!res.ok && res.status >= 500) {
          this.pinError = '서버 오류가 발생했습니다.';
          this.pinInput = '';
          return;
        }
        const data = await res.json();
        if (data.success) {
          this.pinAuthenticated = true;
          this.currentUser = data.user || '';
          this.pinError = '';
          this.pinInput = '';
          this.applyPeriod();
          await this.loadDashboard();
        } else {
          this.pinError = data.error;
          this.pinInput = '';
          if (data.locked) {
            this.pinLocked = true;
          }
        }
      } catch (e) {
        this.pinError = '서버에 연결할 수 없습니다.';
        this.pinInput = '';
      }
    },

    setTheme(themeId) {
      this.theme = themeId;
      document.documentElement.setAttribute('data-theme', themeId);
      localStorage.setItem('theme', themeId);
    },

    toggleTheme() {
      // Legacy: toggle between current theme's dark/light pair
      const cur = this.themePresets.find(p => p.id === this.theme);
      if (!cur) return this.setTheme('dark');
      const base = this.theme.replace(/-?(dark|light)$/, '');
      const pair = cur.dark
        ? this.themePresets.find(p => p.id === (base ? base + '-light' : 'light'))
        : this.themePresets.find(p => p.id === (base ? base + '-dark' : 'dark'));
      this.setTheme(pair ? pair.id : 'dark');
    },

    toggleSidebar() {
      this.sidebarOpen = !this.sidebarOpen;
      localStorage.setItem('sidebar', this.sidebarOpen ? 'open' : 'collapsed');
    },

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

    // ── Dashboard ──
    async loadDashboard() {
      this.dash = await this.get('/dashboard');
      this.pendingCount = this.dash.pending_count;
      this.monthly = await this.get('/dashboard/monthly?months=6');
    },

    // ── Entries ──
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
      this.pendingCount = Math.max(0, this.pendingCount - 1);
      this.loadDashboard();
    },

    async rejectEntry(id) {
      await this.post(`/entries/${id}/reject`);
      this.entries = this.entries.filter(e => e.id !== id);
      this.pendingCount = Math.max(0, this.pendingCount - 1);
    },

    newEntry() {
      const today = new Date().toISOString().slice(0, 10);
      this.editingEntry = { id: 0, entry_date: today, description: '', memo: '', lines: [], is_confirmed: 0 };
      this.editAmount = 0;
      this.editDebitAcct = this.allAccounts.find(a => a.type === 'expense' && !a.is_group)?.id || 0;
      this.editCreditAcct = this.allAccounts.find(a => a.type === 'liability' && !a.is_group)?.id || 0;
      this.loadAllAccounts();
    },

    async loadAllAccounts() {
      const grouped = await this.get('/accounts');
      this.allAccounts = [];
      for (const type of ['expense', 'asset', 'liability', 'income', 'equity']) {
        if (grouped[type]) this.allAccounts.push(...grouped[type]);
      }
      this.initGroupFilter();
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
        // Build flat list with indent via tree walk
        const items = [];
        const addNode = (node, depth) => {
          const children = all.filter(a => a.parent_id === node.id);
          children.sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0) || a.code.localeCompare(b.code));
          if (node.is_group) {
            // Group header (non-selectable)
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
      // payment: asset + liability (banks, cards, cash)
      return this.allAccounts.filter(a => (a.type === 'asset' || a.type === 'liability') && !a.is_group).slice(0, 8);
    },

    acctGroupLabel(accountId) {
      const a = this.allAccounts.find(x => x.id === accountId);
      if (!a || !a.parent_id) return '';
      // Walk up to find the top-level group name
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
    saveGroupColor(groupName, color) {
      this.groupColors[groupName] = color;
      localStorage.setItem('groupColors', JSON.stringify(this.groupColors));
    },
    removeGroupColor(groupName) {
      delete this.groupColors[groupName];
      localStorage.setItem('groupColors', JSON.stringify(this.groupColors));
    },
    uniqueGroups() {
      const names = new Set();
      for (const a of this.allAccounts) {
        if (a.is_group && !a.parent_id) names.add(a.name);
      }
      return [...names];
    },
    accountTypeLabel(type) {
      return { asset: '자산', liability: '부채', equity: '자본', income: '수익', expense: '비용' }[type] || type;
    },

    availableGroups() {
      // Deduplicate groups by name, merge IDs
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

    allGroupedAccounts() {
      const typeOrder = ['expense', 'income', 'asset', 'liability', 'equity'];
      const result = [];
      for (const type of typeOrder) {
        const accts = this.allAccounts.filter(a => a.type === type && !a.is_group);
        if (!accts.length) continue;
        // group by parent
        const groups = [];
        const groupMap = {};
        for (const a of accts) {
          const pid = a.parent_id || 0;
          // Filter: ungrouped (no parent) always shown; grouped shown only if group is checked
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

    async quickSaveEntry() {
      if (!this.editAmount || this.editAmount <= 0) return alert('금액을 입력하세요');
      if (!this.editDebitAcct || !this.editCreditAcct) return alert('계정을 선택하세요');
      if (!this.editingEntry.description) return alert('설명을 입력하세요');

      await this.post('/entries', {
        entry_date: this.editingEntry.entry_date,
        description: this.editingEntry.description,
        memo: this.editingEntry.memo || '',
        lines: [
          { account_id: this.editDebitAcct, debit: this.editAmount, credit: 0 },
          { account_id: this.editCreditAcct, debit: 0, credit: this.editAmount },
        ],
      });

      // Reset form but keep date and accounts
      const keepDate = this.editingEntry.entry_date;
      const keepDebit = this.editDebitAcct;
      const keepCredit = this.editCreditAcct;
      this.editingEntry = { id: 0, entry_date: keepDate, description: '', memo: '', lines: [], is_confirmed: 0 };
      this.editAmount = 0;
      this.editDebitAcct = keepDebit;
      this.editCreditAcct = keepCredit;
      this.showAcctPicker = null;

      this.loadEntries(1);
      this.loadDashboard();
    },

    async deleteEntry(id) {
      if (!confirm('이 거래를 삭제하시겠습니까?')) return;
      await this.del(`/entries/${id}`);
      this.loadEntries(1);
      this.loadDashboard();
    },

    async editExistingEntry(e) {
      await this.loadAllAccounts();
      this.editingEntry = { ...e };
      this.editAmount = e.lines.reduce((s, l) => s + l.debit, 0);
      this.editDebitAcct = e.lines.find(l => l.debit > 0)?.account_id || 0;
      this.editCreditAcct = e.lines.find(l => l.credit > 0)?.account_id || 0;
      this.showEditModal = true;
    },

    // ── Accounts ──
    async loadAccounts() {
      this.acctList = await this.get('/accounts');
      await this.loadAllAccounts();
      this.$nextTick(() => this.initAllSortables());
    },

    async loadSettings() {
      this.rules = await this.get('/rules');
      await this.loadAllAccounts();
    },

    async newAcct() {
      this.editingAcct = { code: '', name: '', type: 'asset', parent_id: null, is_group: 0 };
      await this.loadAllAccounts();
      await this.autoFillCode();
    },

    async autoFillCode() {
      if (this.editingAcct.id) return; // don't overwrite existing account codes
      const res = await this.get(`/accounts/next-code?type=${this.editingAcct.type}`);
      if (res && res.code) this.editingAcct.code = res.code;
    },

    _sortBy(list) {
      return [...list].sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0) || a.code.localeCompare(b.code));
    },

    acctTree(type) {
      const list = this.acctList[type] || [];
      const roots = this._sortBy(list.filter(a => !a.parent_id));
      const result = [];
      const addWithChildren = (parent, depth) => {
        result.push(parent);
        const children = this._sortBy(list.filter(a => a.parent_id === parent.id));
        for (const child of children) {
          addWithChildren(child, depth + 1);
        }
      };
      for (const root of roots) addWithChildren(root, 0);
      // Include orphans (parent in different type) at root level
      const inTree = new Set(result.map(a => a.id));
      for (const a of list) {
        if (!inTree.has(a.id)) result.push(a);
      }
      return result;
    },

    acctRoots(type) {
      return this._sortBy((this.acctList[type] || []).filter(a => !a.parent_id));
    },

    acctChildren(parentId) {
      const all = Object.values(this.acctList).flat();
      return this._sortBy(all.filter(a => a.parent_id === parentId));
    },

    parentCandidates() {
      const type = this.editingAcct.type || 'expense';
      const list = (this.acctList[type] || []).filter(a => a.is_group && a.id !== this.editingAcct.id);
      return this._sortBy(list);
    },

    startInlineEdit(acct) {
      this.inlineEditId = acct.id;
      this.inlineEditName = acct.name;
    },

    async saveInlineEdit(acct) {
      if (this.inlineEditId !== acct.id) return;
      const newName = this.inlineEditName.trim();
      this.inlineEditId = 0;
      if (!newName || newName === acct.name) return;
      await this.put(`/accounts/${acct.id}`, { name: newName });
      await this.loadAccounts();
      this.$nextTick(() => this.initAllSortables());
    },

    destroySortables() {
      for (const s of this._sortables) s.destroy();
      this._sortables = [];
    },

    initSortableType(type) {
      const self = this;
      const root = document.getElementById('dnd-root-' + type);
      if (!root) return;

      const opts = () => ({
        group: 'accounts-' + type,
        handle: '.dnd-handle',
        animation: 200,
        fallbackOnBody: true,
        swapThreshold: 0.65,
        ghostClass: 'sortable-ghost',
        chosenClass: 'sortable-chosen',
        onEnd: (evt) => self.onDragEnd(evt),
      });

      this._sortables.push(Sortable.create(root, opts()));
      root.querySelectorAll('.dnd-children').forEach(el => {
        this._sortables.push(Sortable.create(el, opts()));
      });
    },

    async onDragEnd(evt) {
      const itemId = parseInt(evt.item.dataset.id);
      const newParentEl = evt.to;
      let newParentId = null;

      if (newParentEl.dataset.parentId) {
        newParentId = parseInt(newParentEl.dataset.parentId);
      }

      // Depth check: if dropping into a depth-2 container, block it
      const parentDepth = this.getAcctDepth(newParentId);
      const itemHasChildren = this.acctChildren(itemId).length > 0;

      if (parentDepth >= 2 || (parentDepth === 1 && itemHasChildren)) {
        await this.loadAccounts();
        return;
      }

      // Collect new order from ALL affected containers
      const reorderData = [];
      const collectOrder = (container, parentId) => {
        const items = Array.from(container.children).filter(el => el.classList.contains('dnd-item'));
        items.forEach((el, idx) => {
          const id = parseInt(el.dataset.id);
          if (!isNaN(id)) {
            reorderData.push({ id, sort_order: idx, parent_id: parentId });
          }
        });
      };

      // Collect from the root and all child containers in the same type section
      const root = newParentEl.closest('.dnd-tree') || newParentEl;
      collectOrder(root, null);
      root.querySelectorAll('.dnd-children').forEach(el => {
        const pid = el.dataset.parentId ? parseInt(el.dataset.parentId) : null;
        collectOrder(el, pid);
      });

      await this.put('/accounts/reorder', reorderData);
    },

    initAllSortables() {
      this.destroySortables();
      for (const t of ['asset','liability','equity','income','expense']) {
        this.initSortableType(t);
      }
    },

    getAcctDepth(acctId) {
      if (!acctId) return -1;
      const all = Object.values(this.acctList).flat();
      const acct = all.find(a => a.id === acctId);
      return acct ? (acct.depth || 0) : -1;
    },

    async saveAcct() {
      if (!this.editingAcct.name) return alert('이름을 입력하세요');
      // Check duplicate name within same type + same group
      const sameTypeAccts = this.acctList[this.editingAcct.type] || [];
      const pid = this.editingAcct.parent_id || null;
      const dup = sameTypeAccts.find(a => a.name === this.editingAcct.name && a.id !== this.editingAcct.id && (a.parent_id || null) === pid);
      if (dup) return alert(`"${this.editingAcct.name}" 이름의 계정이 같은 그룹에 이미 존재합니다.`);
      const data = { ...this.editingAcct };
      if (data.parent_id === '' || data.parent_id === 'null') data.parent_id = null;
      if (this.editingAcct.id) {
        await this.put(`/accounts/${this.editingAcct.id}`, data);
      } else {
        await this.post('/accounts', data);
      }
      this.showAcctModal = false;
      await this.loadAccounts();
      this.$nextTick(() => this.initAllSortables());
    },

    async deleteAcct(id) {
      if (!confirm('이 계정을 삭제하시겠습니까?')) return;
      const res = await fetch(`${API}/accounts/${id}`, { method: 'DELETE' });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        return alert(err.detail || '삭제 실패');
      }
      this.showAcctModal = false;
      this.loadAccounts();
    },

    // ── Report ──
    async loadReport() {
      this.reportData = await this.get(`/dashboard/trend?start=${this.reportStart}&end=${this.reportEnd}`);
      this.monthly = await this.get('/dashboard/monthly?months=12');
      this.incExp = await this.get(`/dashboard/income-expense?start=${this.reportStart}&end=${this.reportEnd}`);
      this.$nextTick(() => this.drawChart());
    },

    ieTree(type) {
      const items = this.incExp[type] || [];
      const roots = items.filter(a => !a.parent_id).sort((a, b) => a.code.localeCompare(b.code));
      const result = [];
      for (const root of roots) {
        const children = items.filter(a => a.parent_id === root.id).sort((a, b) => a.code.localeCompare(b.code));
        const childrenTotal = children.reduce((s, c) => s + c.amount, 0);
        result.push({ ...root, _depth: 0, _isGroup: root.is_group, _total: root.is_group ? childrenTotal : root.amount + childrenTotal });
        for (const child of children) {
          const grandchildren = items.filter(a => a.parent_id === child.id).sort((a, b) => a.code.localeCompare(b.code));
          const gcTotal = grandchildren.reduce((s, c) => s + c.amount, 0);
          result.push({ ...child, _depth: 1, _isGroup: child.is_group, _total: child.is_group ? gcTotal : child.amount + gcTotal });
          for (const gc of grandchildren) {
            result.push({ ...gc, _depth: 2, _isGroup: false, _total: gc.amount });
          }
        }
      }
      return result;
    },

    iePercent(amount, total) {
      if (!total) return 0;
      return Math.round(Math.abs(amount) / Math.abs(total) * 100);
    },

    periodYears() {
      const cur = new Date().getFullYear();
      const years = [];
      for (let y = cur; y >= cur - 5; y--) years.push(String(y));
      return years;
    },

    setPeriodMode(mode) {
      this.periodMode = mode;
      this.applyPeriod();
    },

    _localDate(y, m, d) {
      return `${y}-${String(m+1).padStart(2,'0')}-${String(d).padStart(2,'0')}`;
    },

    setMonthRange(startYM, endYM) {
      const [sy, sm] = startYM.split('-').map(Number);
      const [ey, em] = endYM.split('-').map(Number);
      this.reportStart = this._localDate(sy, sm - 1, 1);
      this.reportEnd = this._localDate(ey, em - 1, new Date(ey, em, 0).getDate());
      this.periodMode = 'custom';
      this.loadReport();
    },

    setThisMonth() {
      const now = new Date();
      const y = now.getFullYear(), m = now.getMonth();
      this.reportStart = this._localDate(y, m, 1);
      this.reportEnd = this._localDate(y, m, new Date(y, m + 1, 0).getDate());
      this.periodMode = 'thisMonth';
      this.loadReport();
    },

    applyPeriod() {
      const y = parseInt(this.periodYear);
      if (this.periodMode === 'year') {
        this.reportStart = `${y}-01-01`;
        this.reportEnd = `${y}-12-31`;
      } else if (this.periodMode === 'quarter') {
        const q = this.periodQuarter;
        const sm = (q - 1) * 3 + 1;
        const em = q * 3;
        this.reportStart = `${y}-${String(sm).padStart(2,'0')}-01`;
        const lastDay = new Date(y, em, 0).getDate();
        this.reportEnd = `${y}-${String(em).padStart(2,'0')}-${lastDay}`;
      } else if (this.periodMode === 'month') {
        const m = this.periodMonth;
        this.reportStart = `${y}-${String(m).padStart(2,'0')}-01`;
        const lastDay = new Date(y, m, 0).getDate();
        this.reportEnd = `${y}-${String(m).padStart(2,'0')}-${lastDay}`;
      }
      this.loadReport();
    },

    shiftPeriod(dir) {
      if (this.periodMode === 'year') {
        this.periodYear = String(parseInt(this.periodYear) + dir);
      } else if (this.periodMode === 'quarter') {
        let q = this.periodQuarter + dir;
        let y = parseInt(this.periodYear);
        if (q > 4) { q = 1; y++; }
        if (q < 1) { q = 4; y--; }
        this.periodQuarter = q;
        this.periodYear = String(y);
      } else if (this.periodMode === 'thisMonth') {
        const parts = this.reportStart.split('-');
        let y = parseInt(parts[0]), m = parseInt(parts[1]) - 1 + dir;
        if (m > 11) { m = 0; y++; }
        if (m < 0) { m = 11; y--; }
        this.reportStart = this._localDate(y, m, 1);
        this.reportEnd = this._localDate(y, m, new Date(y, m + 1, 0).getDate());
        this.loadReport();
        return;
      } else {
        // custom: shift both start and end by 1 month, preserving range
        const sp = this.reportStart.split('-').map(Number);
        const ep = this.reportEnd.split('-').map(Number);
        let sm = sp[1] - 1 + dir, sy = sp[0];
        if (sm > 11) { sm = 0; sy++; } else if (sm < 0) { sm = 11; sy--; }
        let em = ep[1] - 1 + dir, ey = ep[0];
        if (em > 11) { em = 0; ey++; } else if (em < 0) { em = 11; ey--; }
        this.reportStart = this._localDate(sy, sm, 1);
        this.reportEnd = this._localDate(ey, em, new Date(ey, em + 1, 0).getDate());
        this.loadReport();
        return;
      }
      this.applyPeriod();
    },

    reportDataSampled() {
      const d = this.reportData;
      if (d.length <= 20) return d;
      // Sample ~20 points for the table
      const step = Math.ceil(d.length / 20);
      const result = [];
      for (let i = 0; i < d.length; i += step) result.push(d[i]);
      if (d.length > 0 && result[result.length - 1] !== d[d.length - 1]) result.push(d[d.length - 1]);
      return result;
    },

    drawChart() {
      const canvas = document.getElementById('report-chart');
      if (!canvas || !this.reportData.length) return;
      const ctx = canvas.getContext('2d');
      const dpr = window.devicePixelRatio || 1;
      const rect = canvas.getBoundingClientRect();
      canvas.width = rect.width * dpr;
      canvas.height = rect.height * dpr;
      ctx.scale(dpr, dpr);
      const W = rect.width, H = rect.height;
      const pad = { top: 20, right: 20, bottom: 40, left: 70 };
      const cw = W - pad.left - pad.right;
      const ch = H - pad.top - pad.bottom;

      ctx.clearRect(0, 0, W, H);
      ctx.font = '11px -apple-system, sans-serif';

      const data = this.reportData;
      const series = [];
      if (this.reportShowAsset) series.push({ key: 'asset', color: '#22c55e', label: '자산' });
      if (this.reportShowLiability) series.push({ key: 'liability', color: '#ef4444', label: '부채' });
      if (this.reportShowNetWorth) series.push({ key: 'net_worth', color: '#6366f1', label: '순자산' });

      if (!series.length) return;

      // Find min/max across visible series
      let min = Infinity, max = -Infinity;
      for (const s of series) {
        for (const d2 of data) {
          const v = d2[s.key];
          if (v < min) min = v;
          if (v > max) max = v;
        }
      }
      if (min === max) { min -= 1000; max += 1000; }
      const range = max - min;
      min -= range * 0.05;
      max += range * 0.05;

      const x = (i) => data.length <= 1 ? pad.left + cw / 2 : pad.left + (i / (data.length - 1)) * cw;
      const y = (v) => pad.top + ch - ((v - min) / (max - min)) * ch;

      // Grid lines
      ctx.strokeStyle = 'rgba(255,255,255,0.08)';
      ctx.lineWidth = 1;
      const gridCount = 5;
      for (let i = 0; i <= gridCount; i++) {
        const gy = pad.top + (ch / gridCount) * i;
        ctx.beginPath(); ctx.moveTo(pad.left, gy); ctx.lineTo(pad.left + cw, gy); ctx.stroke();
        const val = max - ((max - min) / gridCount) * i;
        ctx.fillStyle = '#71717a';
        ctx.textAlign = 'right';
        ctx.fillText(Math.round(val).toLocaleString('ko-KR'), pad.left - 8, gy + 4);
      }

      // X-axis labels
      ctx.fillStyle = '#71717a';
      ctx.textAlign = 'center';
      const labelStep = Math.max(1, Math.floor(data.length / 6));
      for (let i = 0; i < data.length; i += labelStep) {
        ctx.fillText(data[i].date.slice(0, 7), x(i), H - pad.bottom + 16);
      }
      if (data.length > 1) ctx.fillText(data[data.length - 1].date.slice(0, 7), x(data.length - 1), H - pad.bottom + 16);

      // Draw lines and dots
      for (const s of series) {
        ctx.strokeStyle = s.color;
        ctx.lineWidth = 2;
        ctx.beginPath();
        for (let i = 0; i < data.length; i++) {
          const px = x(i), py = y(data[i][s.key]);
          i === 0 ? ctx.moveTo(px, py) : ctx.lineTo(px, py);
        }
        ctx.stroke();
        // Draw dots (always visible, especially useful for single data points)
        ctx.fillStyle = s.color;
        for (let i = 0; i < data.length; i++) {
          const px = x(i), py = y(data[i][s.key]);
          ctx.beginPath();
          ctx.arc(px, py, data.length <= 5 ? 4 : 2.5, 0, Math.PI * 2);
          ctx.fill();
        }
      }
    },

    // ── Rules ──
    async editRule(r) {
      this.editingRule = { ...r };
      await this.loadAllAccounts();
      this.showRuleModal = true;
    },

    async saveRule() {
      if (!this.editingRule.merchant_pattern) return alert('가맹점 패턴을 입력하세요');
      await this.put(`/rules/${this.editingRule.id}`, {
        merchant_pattern: this.editingRule.merchant_pattern,
        debit_account_id: this.editingRule.debit_account_id,
        credit_account_id: this.editingRule.credit_account_id,
      });
      this.showRuleModal = false;
      this.loadSettings();
    },

    async deleteRule(id) {
      if (!confirm('이 규칙을 삭제하시겠습니까?')) return;
      await this.del(`/rules/${id}`);
      this.loadSettings();
    },

    // ── Assets ──
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
      } catch (e) { /* not found, user fills manually */ }
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
      console.log('Sell request:', s.id, s.sell_quantity, s.sell_price);
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

    // ── Messages ──
    async loadMessages() {
      let url = '/messages?limit=50';
      if (this.msgFilter) url += `&status=${this.msgFilter}`;
      this.messages = await this.get(url);
    },

    async reparseMsg(id) {
      await this.post(`/messages/${id}/reparse`);
      this.loadMessages();
      this.loadDashboard();
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
      // "2026-03-16T14:30:00" → "14:30"
      if (!dt) return '';
      const t = dt.indexOf('T');
      if (t < 0) return '';
      return dt.slice(t + 1, t + 6);
    },

    groupedAccounts(type) {
      const all = (this.dash.accounts || []).filter(x => x.type === type);
      const byId = {};
      for (const a of all) byId[a.id] = a;
      // Recursive leaf-sum for groups
      const leafSum = (id) => {
        const children = all.filter(a => a.parent_id === id);
        let s = 0;
        for (const c of children) s += c.is_group ? leafSum(c.id) : c.balance;
        return s;
      };
      // Recursively flatten tree with depth
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
      // Root nodes: no parent or parent not in this type
      const roots = all.filter(a => !a.parent_id || !byId[a.parent_id]);
      roots.sort((a, b) => a.code.localeCompare(b.code));
      for (const r of roots) addNode(r, 0);
      return result;
    },
    fmtDate(d) {
      // "2026-03-16" → mobile: "03/16", desktop: "2026-03-16"
      if (!d) return '';
      if (window.innerWidth <= 768) return d.slice(5).replace('-', '/');
      return d;
    },
    typeLabel(t) {
      return { asset: '자산', liability: '부채', equity: '자본', income: '수입', expense: '비용' }[t] || t;
    },
  };
}
