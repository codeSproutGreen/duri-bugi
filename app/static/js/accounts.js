window.AppMixins = window.AppMixins || {};
window.AppMixins.accounts = {
  acctList: {},
  acctTab: 'asset',
  allAccounts: [],
  inlineEditId: 0,
  inlineEditName: '',
  _sortables: [],
  showAcctModal: false,
  editingAcct: {},

  async loadAllAccounts() {
    const grouped = await this.get('/accounts');
    this.allAccounts = [];
    for (const type of ['expense', 'asset', 'liability', 'income', 'equity']) {
      if (grouped[type]) this.allAccounts.push(...grouped[type]);
    }
    this.initGroupFilter();
    this.initTxnGroupFilter();
  },

  async loadAccounts() {
    this.acctList = await this.get('/accounts');
    await this.loadAllAccounts();
    this.$nextTick(() => this.initAllSortables());
  },

  async newAcct() {
    this.editingAcct = { code: '', name: '', type: 'asset', parent_id: null, is_group: 0 };
    await this.loadAllAccounts();
    await this.autoFillCode();
  },

  async autoFillCode() {
    if (this.editingAcct.id) return;
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

    const parentDepth = this.getAcctDepth(newParentId);
    const itemHasChildren = this.acctChildren(itemId).length > 0;

    if (parentDepth >= 2 || (parentDepth === 1 && itemHasChildren)) {
      await this.loadAccounts();
      return;
    }

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
};
