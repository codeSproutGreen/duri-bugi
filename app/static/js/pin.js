window.AppMixins = window.AppMixins || {};
window.AppMixins.pin = {
  pinRequired: false,
  pinAuthenticated: false,
  pinInput: '',
  pinError: '',
  pinLocked: false,
  currentUser: '',

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
};
