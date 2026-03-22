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
};
