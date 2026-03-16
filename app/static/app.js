const API = '/api';

function app() {
  return {
    page: 'dashboard',
    theme: localStorage.getItem('theme') || 'dark',
    sidebarOpen: localStorage.getItem('sidebar') !== 'collapsed',

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

    // Accounts
    acctList: {},
    acctTab: 'asset',
    allAccounts: [],
    acctEditMode: false,
    acctPendingDeletes: [],
    _sortables: [],

    // Report
    reportStart: new Date(new Date().getFullYear(), new Date().getMonth() - 2, 1).toISOString().slice(0, 10),
    reportEnd: new Date().toISOString().slice(0, 10),
    reportData: [],
    reportShowAsset: true,
    reportShowLiability: true,
    reportTab: 'trend',
    periodMode: 'month',
    periodYear: String(new Date().getFullYear()),
    periodMonth: new Date().getMonth() + 1,
    periodQuarter: Math.ceil((new Date().getMonth() + 1) / 3),
    reportShowNetWorth: true,
    _chart: null,
    incExp: { expense: [], income: [], total_expense: 0, total_income: 0, net_income: 0 },

    // Messages
    messages: [],
    msgFilter: null,

    // Modals & input
    showEditModal: false,
    showAcctPicker: null,
    editingEntry: {},
    editAmount: 0,
    editDebitAcct: 0,
    editCreditAcct: 0,
    showAcctModal: false,
    editingAcct: {},
    rules: [],
    showRuleModal: false,
    editingRule: {},

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
      }
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

    toggleTheme() {
      this.theme = this.theme === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', this.theme);
      localStorage.setItem('theme', this.theme);
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
      let url = '/entries?limit=100';
      if (confirmed !== null && confirmed !== undefined) url += `&confirmed=${confirmed}`;
      if (this.searchQuery) url += `&search=${encodeURIComponent(this.searchQuery)}`;
      this.entries = await this.get(url);
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
      this.editDebitAcct = this.allAccounts.find(a => a.type === 'expense')?.id || 0;
      this.editCreditAcct = this.allAccounts.find(a => a.type === 'liability')?.id || 0;
      this.loadAllAccounts();
    },

    async loadAllAccounts() {
      const grouped = await this.get('/accounts');
      this.allAccounts = [];
      for (const type of ['expense', 'asset', 'liability', 'income', 'equity']) {
        if (grouped[type]) this.allAccounts.push(...grouped[type]);
      }
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
      else if (this.page === 'transactions') this.loadEntries(null);
      this.loadDashboard();
    },

    quickAccounts(type) {
      if (type === 'expense') {
        return this.allAccounts.filter(a => a.type === 'expense' && !a.parent_id).slice(0, 8);
      }
      // payment: asset + liability (banks, cards, cash)
      return this.allAccounts.filter(a => a.type === 'asset' || a.type === 'liability').filter(a => !a.parent_id).slice(0, 8);
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

      this.loadEntries(null);
      this.loadDashboard();
    },

    async deleteEntry(id) {
      if (!confirm('이 거래를 삭제하시겠습니까?')) return;
      await this.del(`/entries/${id}`);
      this.loadEntries(null);
      this.loadDashboard();
    },

    editExistingEntry(e) {
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
    },

    async loadSettings() {
      this.rules = await this.get('/rules');
      await this.loadAllAccounts();
    },

    async newAcct() {
      this.editingAcct = { code: '', name: '', type: 'asset', parent_id: null };
      await this.loadAllAccounts();
      await this.autoFillCode();
    },

    async autoFillCode() {
      if (this.editingAcct.id) return; // don't overwrite existing account codes
      const res = await this.get(`/accounts/next-code?type=${this.editingAcct.type}`);
      if (res && res.code) this.editingAcct.code = res.code;
    },

    acctTree(type) {
      const list = this.acctList[type] || [];
      // Sort: parents first (by code), then children under each parent (by code)
      const roots = list.filter(a => !a.parent_id).sort((a, b) => a.code.localeCompare(b.code));
      const result = [];
      const addWithChildren = (parent, depth) => {
        result.push(parent);
        const children = list
          .filter(a => a.parent_id === parent.id)
          .sort((a, b) => a.code.localeCompare(b.code));
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
      return (this.acctList[type] || [])
        .filter(a => !a.parent_id)
        .sort((a, b) => a.code.localeCompare(b.code));
    },

    acctChildren(parentId) {
      const all = Object.values(this.acctList).flat();
      return all
        .filter(a => a.parent_id === parentId)
        .sort((a, b) => a.code.localeCompare(b.code));
    },

    parentCandidates() {
      const type = this.editingAcct.type || 'expense';
      const list = (this.acctList[type] || []).filter(a => (a.depth || 0) < 2);
      return list.sort((a, b) => a.code.localeCompare(b.code));
    },

    toggleAcctEditMode() {
      if (this.acctEditMode) {
        // "완료" clicked — apply pending deletes
        this.applyAcctDeletes();
      } else {
        this.acctPendingDeletes = [];
      }
      this.acctEditMode = !this.acctEditMode;
      if (!this.acctEditMode) {
        this.destroySortables();
        this.loadAccounts();
      }
    },

    markAcctDelete(id) {
      if (this.acctPendingDeletes.includes(id)) {
        this.acctPendingDeletes = this.acctPendingDeletes.filter(x => x !== id);
      } else {
        this.acctPendingDeletes.push(id);
      }
    },

    async applyAcctDeletes() {
      for (const id of this.acctPendingDeletes) {
        const res = await fetch(`${API}/accounts/${id}`, { method: 'DELETE' });
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          alert(err.detail || '삭제 실패');
        }
      }
      this.acctPendingDeletes = [];
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
        // Revert: reload
        await this.loadAccounts();
        this.$nextTick(() => this.initAllSortables());
        return;
      }

      // Update parent via API
      await this.put(`/accounts/${itemId}`, { parent_id: newParentId });

      // Reload to get fresh depth/children data
      await this.loadAccounts();
      this.$nextTick(() => this.initAllSortables());
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
      // Check duplicate name
      const allAccts = Object.values(this.acctList).flat();
      const dup = allAccts.find(a => a.name === this.editingAcct.name && a.id !== this.editingAcct.id);
      if (dup) return alert(`"${this.editingAcct.name}" 이름의 계정이 이미 존재합니다.`);
      const data = { ...this.editingAcct };
      if (data.parent_id === '' || data.parent_id === 'null') data.parent_id = null;
      if (this.editingAcct.id) {
        await this.put(`/accounts/${this.editingAcct.id}`, data);
      } else {
        await this.post('/accounts', data);
      }
      this.showAcctModal = false;
      this.loadAccounts();
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
        result.push({ ...root, _depth: 0, _isGroup: children.length > 0, _total: root.amount + childrenTotal });
        for (const child of children) {
          const grandchildren = items.filter(a => a.parent_id === child.id).sort((a, b) => a.code.localeCompare(b.code));
          const gcTotal = grandchildren.reduce((s, c) => s + c.amount, 0);
          result.push({ ...child, _depth: 1, _isGroup: grandchildren.length > 0, _total: child.amount + gcTotal });
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
      } else if (this.periodMode === 'month') {
        let m = this.periodMonth + dir;
        let y = parseInt(this.periodYear);
        if (m > 12) { m = 1; y++; }
        if (m < 1) { m = 12; y--; }
        this.periodMonth = m;
        this.periodYear = String(y);
      } else {
        // custom: shift by the current range length
        const s = new Date(this.reportStart);
        const e = new Date(this.reportEnd);
        const days = Math.round((e - s) / 86400000) + 1;
        s.setDate(s.getDate() + days * dir);
        e.setDate(e.getDate() + days * dir);
        this.reportStart = s.toISOString().slice(0, 10);
        this.reportEnd = e.toISOString().slice(0, 10);
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

      const x = (i) => pad.left + (i / (data.length - 1)) * cw;
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
        ctx.fillText(data[i].date.slice(5), x(i), H - pad.bottom + 16);
      }
      if (data.length > 1) ctx.fillText(data[data.length - 1].date.slice(5), x(data.length - 1), H - pad.bottom + 16);

      // Draw lines
      for (const s of series) {
        ctx.strokeStyle = s.color;
        ctx.lineWidth = 2;
        ctx.beginPath();
        for (let i = 0; i < data.length; i++) {
          const px = x(i), py = y(data[i][s.key]);
          i === 0 ? ctx.moveTo(px, py) : ctx.lineTo(px, py);
        }
        ctx.stroke();
      }
    },

    // ── Rules ──
    editRule(r) {
      this.editingRule = { ...r };
      this.loadAllAccounts();
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

    fmtTime(ts) {
      return new Date(ts).toLocaleString('ko-KR', {
        month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit'
      });
    },

    typeLabel(t) {
      return { asset: '자산', liability: '부채', equity: '자본', income: '수입', expense: '비용' }[t] || t;
    },
  };
}
