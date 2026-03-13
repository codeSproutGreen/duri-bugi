const API = '/api';

function app() {
  return {
    page: 'dashboard',

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

    // Messages
    messages: [],
    msgFilter: null,

    // Modals
    showEditModal: false,
    editingEntry: {},
    editAmount: 0,
    editDebitAcct: 0,
    editCreditAcct: 0,
    showAcctModal: false,
    editingAcct: {},

    async init() {
      await this.loadDashboard();
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

    // ── Accounts ──
    async loadAccounts() {
      this.acctList = await this.get('/accounts');
      await this.loadAllAccounts();
    },

    async saveAcct() {
      if (!this.editingAcct.code || !this.editingAcct.name) return alert('코드와 이름을 입력하세요');
      if (this.editingAcct.id) {
        await this.put(`/accounts/${this.editingAcct.id}`, this.editingAcct);
      } else {
        await this.post('/accounts', this.editingAcct);
      }
      this.showAcctModal = false;
      this.loadAccounts();
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
