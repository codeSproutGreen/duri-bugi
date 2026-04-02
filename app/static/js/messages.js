window.AppMixins = window.AppMixins || {};
window.AppMixins.messages = {
  messages: [],
  msgFilter: null,

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

  parseAiResult(raw) {
    if (!raw) return null;
    try {
      return typeof raw === 'string' ? JSON.parse(raw) : raw;
    } catch {
      return null;
    }
  },

  txnTypeLabel(type) {
    const map = {
      card_payment: '카드결제',
      bank_transfer: '계좌이체',
      deposit: '입금',
      withdrawal: '출금',
      cancellation: '승인취소',
      unknown: '미분류',
    };
    return map[type] || type;
  },

  confidenceClass(score) {
    if (score >= 0.8) return 'confidence-high';
    if (score >= 0.5) return 'confidence-mid';
    return 'confidence-low';
  },

  acctName(code) {
    if (!code) return '?';
    const found = (this.allAccounts || []).find(a => a.code === code);
    return found ? found.name : code;
  },

  statusKo(status) {
    const map = {
      pending: '대기',
      parsed: '파싱됨',
      approved: '승인',
      rejected: '거절',
      failed: '실패',
      duplicate: '중복',
    };
    return map[status] || status;
  },
};
