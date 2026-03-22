window.AppMixins = window.AppMixins || {};
window.AppMixins.report = {
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
  monthlyShowIncome: true,
  monthlyShowExpense: true,
  monthlyShowNet: true,
  monthlyHover: null,
  tagList: [],
  tagSelectedTag: null,
  tagEntries: [],
  tagMemo: '',
  tagMemoSaving: false,

  async loadReport() {
    this.reportData = await this.get(`/dashboard/trend?start=${this.reportStart}&end=${this.reportEnd}`);
    this.monthly = await this.get(`/dashboard/monthly?months=24&start=${this.reportStart}&end=${this.reportEnd}`);
    this.incExp = await this.get(`/dashboard/income-expense?start=${this.reportStart}&end=${this.reportEnd}`);
    this.$nextTick(() => {
      this.drawChart();
      this.drawMonthlyChart();
    });
    if (this.reportTab === 'tags') this.loadTags();
  },

  async loadTags() {
    this.tagList = await this.get(`/dashboard/tags?start=${this.reportStart}&end=${this.reportEnd}`);
  },

  async selectTag(tag) {
    this.tagSelectedTag = tag;
    await this.loadAllAccounts();
    const [entries, memoData] = await Promise.all([
      this.get(`/dashboard/tag-entries?tag=${encodeURIComponent(tag)}&start=${this.reportStart}&end=${this.reportEnd}`),
      this.get(`/dashboard/tag-memo?tag=${encodeURIComponent(tag)}`),
    ]);
    this.tagEntries = entries;
    this.tagMemo = memoData.memo || '';
  },

  async saveTagMemo() {
    if (!this.tagSelectedTag) return;
    this.tagMemoSaving = true;
    await this.put(`/dashboard/tag-memo?tag=${encodeURIComponent(this.tagSelectedTag)}&memo=${encodeURIComponent(this.tagMemo)}`);
    this.tagMemoSaving = false;
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
    const step = Math.ceil(d.length / 20);
    const result = [];
    for (let i = 0; i < d.length; i += step) result.push(d[i]);
    if (d.length > 0 && result[result.length - 1] !== d[d.length - 1]) result.push(d[d.length - 1]);
    return result;
  },

  monthlySummary() {
    const data = [...this.monthly].reverse();
    if (!data.length) return null;
    const totalIncome = data.reduce((s, m) => s + m.income, 0);
    const totalExpense = data.reduce((s, m) => s + m.expense, 0);
    const net = totalIncome - totalExpense;
    const profitRate = totalIncome ? Math.round((totalIncome - totalExpense) / totalIncome * 10000) / 100 : 0;
    const months = data.length || 1;
    // Calculate total days in the period
    const s = new Date(this.reportStart);
    const e = new Date(this.reportEnd);
    const days = Math.max(1, Math.ceil((e - s) / 86400000) + 1);
    const weeks = days / 7;
    return {
      total: { income: totalIncome, expense: totalExpense, net, profitRate },
      monthly: { income: Math.round(totalIncome / months), expense: Math.round(totalExpense / months), net: Math.round(net / months) },
      weekly: { income: Math.round(totalIncome / weeks), expense: Math.round(totalExpense / weeks), net: Math.round(net / weeks) },
      daily: { income: Math.round(totalIncome / days), expense: Math.round(totalExpense / days), net: Math.round(net / days) },
    };
  },

  drawMonthlyChart() {
    const canvas = document.getElementById('monthly-chart');
    if (!canvas || !this.monthly.length) return;
    const data = [...this.monthly].reverse(); // chronological order
    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.scale(dpr, dpr);
    const W = rect.width, H = rect.height;
    const pad = { top: 30, right: 20, bottom: 40, left: 70 };
    const cw = W - pad.left - pad.right;
    const ch = H - pad.top - pad.bottom;

    ctx.clearRect(0, 0, W, H);
    ctx.font = '11px -apple-system, sans-serif';

    // Compute max/min for scale
    let maxVal = 0;
    let minVal = 0;
    for (const d of data) {
      if (this.monthlyShowIncome) maxVal = Math.max(maxVal, d.income);
      if (this.monthlyShowExpense) maxVal = Math.max(maxVal, d.expense);
      const net = d.income - d.expense;
      if (this.monthlyShowNet) { maxVal = Math.max(maxVal, net); minVal = Math.min(minVal, net); }
    }
    if (maxVal === 0 && minVal === 0) { maxVal = 1000; }
    const range = maxVal - minVal;
    maxVal += range * 0.15;
    minVal -= range * 0.05;

    const y = (v) => pad.top + ch - ((v - minVal) / (maxVal - minVal)) * ch;
    const barGroupWidth = cw / data.length;
    const barWidth = Math.min(barGroupWidth * 0.3, 40);
    const barGap = 4;

    // Grid lines
    const style = getComputedStyle(document.documentElement);
    const gridColor = style.getPropertyValue('--border').trim() || 'rgba(255,255,255,0.08)';
    ctx.strokeStyle = gridColor;
    ctx.lineWidth = 0.5;
    const gridCount = 5;
    for (let i = 0; i <= gridCount; i++) {
      const gy = pad.top + (ch / gridCount) * i;
      ctx.beginPath(); ctx.moveTo(pad.left, gy); ctx.lineTo(pad.left + cw, gy); ctx.stroke();
      const val = maxVal - ((maxVal - minVal) / gridCount) * i;
      ctx.fillStyle = style.getPropertyValue('--text-muted').trim() || '#71717a';
      ctx.textAlign = 'right';
      const label = Math.abs(val) >= 10000 ? Math.round(val / 10000) + '만' : Math.round(val).toLocaleString();
      ctx.fillText(label, pad.left - 8, gy + 4);
    }

    // Zero line
    if (minVal < 0) {
      ctx.strokeStyle = style.getPropertyValue('--text-muted').trim() || '#71717a';
      ctx.lineWidth = 1;
      ctx.setLineDash([4, 4]);
      const zy = y(0);
      ctx.beginPath(); ctx.moveTo(pad.left, zy); ctx.lineTo(pad.left + cw, zy); ctx.stroke();
      ctx.setLineDash([]);
    }

    // X labels
    ctx.fillStyle = style.getPropertyValue('--text-muted').trim() || '#71717a';
    ctx.textAlign = 'center';
    for (let i = 0; i < data.length; i++) {
      const cx = pad.left + barGroupWidth * i + barGroupWidth / 2;
      ctx.fillText(data[i].month, cx, H - pad.bottom + 16);
    }

    // Theme colors
    const incomeColor = style.getPropertyValue('--income').trim() || '#84cc16';
    const expenseColor = style.getPropertyValue('--expense').trim() || '#f97316';
    const netColor = style.getPropertyValue('--primary').trim() || '#a3a310';

    // Bars
    const zeroY = y(0);
    for (let i = 0; i < data.length; i++) {
      const cx = pad.left + barGroupWidth * i + barGroupWidth / 2;
      if (this.monthlyShowIncome) {
        const bh = zeroY - y(data[i].income);
        ctx.fillStyle = incomeColor;
        ctx.fillRect(cx - barWidth - barGap / 2, zeroY - bh, barWidth, bh);
        if (data[i].income > 0 && data.length <= 12) {
          ctx.fillStyle = incomeColor;
          ctx.textAlign = 'center';
          ctx.font = '10px -apple-system, sans-serif';
          const lbl = data[i].income >= 10000 ? (data[i].income / 10000).toFixed(0) + '만' : data[i].income.toLocaleString();
          ctx.fillText(lbl, cx - barWidth / 2 - barGap / 2, zeroY - bh - 4);
          ctx.font = '11px -apple-system, sans-serif';
        }
      }
      if (this.monthlyShowExpense) {
        const bh = zeroY - y(data[i].expense);
        ctx.fillStyle = expenseColor;
        ctx.fillRect(cx + barGap / 2, zeroY - bh, barWidth, bh);
        if (data[i].expense > 0 && data.length <= 12) {
          ctx.fillStyle = expenseColor;
          ctx.textAlign = 'center';
          ctx.font = '10px -apple-system, sans-serif';
          const lbl = data[i].expense >= 10000 ? (data[i].expense / 10000).toFixed(0) + '만' : data[i].expense.toLocaleString();
          ctx.fillText(lbl, cx + barWidth / 2 + barGap / 2, zeroY - bh - 4);
          ctx.font = '11px -apple-system, sans-serif';
        }
      }
    }

    // Net income line
    if (this.monthlyShowNet) {
      ctx.strokeStyle = netColor;
      ctx.lineWidth = 2;
      ctx.beginPath();
      for (let i = 0; i < data.length; i++) {
        const cx = pad.left + barGroupWidth * i + barGroupWidth / 2;
        const net = data[i].income - data[i].expense;
        const py = y(net);
        i === 0 ? ctx.moveTo(cx, py) : ctx.lineTo(cx, py);
      }
      ctx.stroke();
      ctx.fillStyle = netColor;
      for (let i = 0; i < data.length; i++) {
        const cx = pad.left + barGroupWidth * i + barGroupWidth / 2;
        const net = data[i].income - data[i].expense;
        const py = y(net);
        ctx.beginPath();
        ctx.arc(cx, py, 3, 0, Math.PI * 2);
        ctx.fill();
      }
    }

    // Hover detection
    canvas._monthlyData = data;
    canvas._barGroupWidth = barGroupWidth;
    canvas._padLeft = pad.left;
    if (!canvas._hoverBound) {
      canvas._hoverBound = true;
      const self = this;
      canvas.addEventListener('mousemove', (e) => {
        const r = canvas.getBoundingClientRect();
        const mx = e.clientX - r.left;
        const idx = Math.floor((mx - canvas._padLeft) / canvas._barGroupWidth);
        const d = canvas._monthlyData;
        if (idx >= 0 && idx < d.length) {
          const net = d[idx].income - d[idx].expense;
          const rate = d[idx].income ? Math.round((net / d[idx].income) * 10000) / 100 : 0;
          self.monthlyHover = {
            month: d[idx].month,
            income: d[idx].income,
            expense: d[idx].expense,
            net, rate,
            x: e.clientX - r.left,
            y: e.clientY - r.top,
          };
        } else {
          self.monthlyHover = null;
        }
      });
      canvas.addEventListener('mouseleave', () => { self.monthlyHover = null; });
    }
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

    ctx.fillStyle = '#71717a';
    ctx.textAlign = 'center';
    const labelStep = Math.max(1, Math.floor(data.length / 6));
    for (let i = 0; i < data.length; i += labelStep) {
      ctx.fillText(data[i].date.slice(0, 7), x(i), H - pad.bottom + 16);
    }
    if (data.length > 1) ctx.fillText(data[data.length - 1].date.slice(0, 7), x(data.length - 1), H - pad.bottom + 16);

    for (const s of series) {
      ctx.strokeStyle = s.color;
      ctx.lineWidth = 2;
      ctx.beginPath();
      for (let i = 0; i < data.length; i++) {
        const px = x(i), py = y(data[i][s.key]);
        i === 0 ? ctx.moveTo(px, py) : ctx.lineTo(px, py);
      }
      ctx.stroke();
      ctx.fillStyle = s.color;
      for (let i = 0; i < data.length; i++) {
        const px = x(i), py = y(data[i][s.key]);
        ctx.beginPath();
        ctx.arc(px, py, data.length <= 5 ? 4 : 2.5, 0, Math.PI * 2);
        ctx.fill();
      }
    }
  },
};
