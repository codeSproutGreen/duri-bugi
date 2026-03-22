window.AppMixins = window.AppMixins || {};
window.AppMixins.settings = {
  themePresets: [
    // Light
    { id: 'light', name: 'Forest Light', icon: '🌿', dark: false },
    { id: 'ocean-light', name: 'Ocean Light', icon: '🏖️', dark: false },
    { id: 'sage', name: 'Sage', icon: '🍵', dark: false },
    { id: 'blossom', name: 'Blossom', icon: '🌸', dark: false },
    { id: 'ember', name: 'Linen', icon: '🍂', dark: false },
    // Dark
    { id: 'dark', name: 'Forest Dark', icon: '🌲', dark: true },
    { id: 'ocean-dark', name: 'Ocean Dark', icon: '🌊', dark: true },
    { id: 'sunset-dark', name: 'Sunset', icon: '🌅', dark: true },
    { id: 'tropical', name: 'Tropical', icon: '🌺', dark: true },
    { id: 'midnight', name: 'Midnight', icon: '🌑', dark: true },
  ],
  groupColors: JSON.parse(localStorage.getItem('groupColors') || '{}'),
  rules: [],
  showRuleModal: false,
  editingRule: {},

  setTheme(themeId) {
    this.theme = themeId;
    document.documentElement.setAttribute('data-theme', themeId);
    localStorage.setItem('theme', themeId);
  },

  toggleTheme() {
    const cur = this.themePresets.find(p => p.id === this.theme);
    if (!cur) return this.setTheme('dark');
    const base = this.theme.replace(/-?(dark|light)$/, '');
    const pair = cur.dark
      ? this.themePresets.find(p => p.id === (base ? base + '-light' : 'light'))
      : this.themePresets.find(p => p.id === (base ? base + '-dark' : 'dark'));
    this.setTheme(pair ? pair.id : 'dark');
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

  async loadSettings() {
    this.rules = await this.get('/rules');
    await this.loadAllAccounts();
  },

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
};
