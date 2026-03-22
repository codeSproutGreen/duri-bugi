const API = '/api';

function app() {
  return Object.assign(
    {
      page: 'dashboard',
      theme: localStorage.getItem('theme') || 'dark',
      sidebarOpen: localStorage.getItem('sidebar') !== 'collapsed',

      async init() {
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

      toggleSidebar() {
        this.sidebarOpen = !this.sidebarOpen;
        localStorage.setItem('sidebar', this.sidebarOpen ? 'open' : 'collapsed');
      },
    },
    AppMixins.utils,
    AppMixins.pin,
    AppMixins.dashboard,
    AppMixins.entries,
    AppMixins.accounts,
    AppMixins.report,
    AppMixins.assets,
    AppMixins.messages,
    AppMixins.settings,
  );
}
