// =============================================================================
// FraudSpikeDetector — Frontend Application Controller
// Live telemetry polling, explainability inspection, and threshold optimizer
// =============================================================================

const API_BASE = "http://localhost:8080";
let currentFilter = 'ALL';
let allTransactions = [];
let selectedIndex = 0;

// Audited Benchmark Sweep Table Data (IEEE-CIS 80/20 temporal split)
const benchmarkSweep = [
  { threshold: 0.10, prec: 0.0496, rec: 0.9070, f1: 0.0940, fpr: 0.6192, fp: 5979, tp: 312, net: -174550 },
  { threshold: 0.20, prec: 0.0810, rec: 0.8430, f1: 0.1478, fpr: 0.3408, fp: 3291, tp: 290, net: -61050 },
  { threshold: 0.30, prec: 0.1308, rec: 0.7733, f1: 0.2237, fpr: 0.1831, fp: 1768, tp: 266, net: -7700 },
  { threshold: 0.40, prec: 0.1866, rec: 0.7384, f1: 0.2979, fpr: 0.1146, fp: 1107, tp: 254, net: 13950 },
  { threshold: 0.4777, prec: 0.2367, rec: 0.7093, f1: 0.3549, fpr: 0.0815, fp: 787, tp: 244, net: 20450, optimal: true },
  { threshold: 0.50, prec: 0.2454, rec: 0.6977, f1: 0.3631, fpr: 0.0764, fp: 738, tp: 240, net: 19100 },
  { threshold: 0.60, prec: 0.2861, rec: 0.6512, f1: 0.3975, fpr: 0.0579, fp: 559, tp: 224, net: 12850 },
  { threshold: 0.70, prec: 0.3328, rec: 0.6308, f1: 0.4357, fpr: 0.0450, fp: 435, tp: 217, net: 12400 },
  { threshold: 0.80, prec: 0.3770, rec: 0.6017, f1: 0.4636, fpr: 0.0354, fp: 342, tp: 207, net: 7550 }
];

// Seed initial realistic stream
function seedInitialTransactions() {
  allTransactions = [
    { id: "3024881", cardId: "card:8901", mlScore: 0.8780, amount: 142.50, decision: "SUSPICIOUS", spike: true, txCount: 18, declineRate: "72.0%", ips: 8, devices: 6, time: "14:28:02", reason: "EWMA Z>2.0 Velocity Spike" },
    { id: "3024882", cardId: "card:4242", mlScore: 0.9412, amount: 1.42, decision: "SUSPICIOUS", spike: true, txCount: 34, declineRate: "88.2%", ips: 14, devices: 9, time: "14:27:55", reason: "Distributed Micro-Probing" },
    { id: "3024883", cardId: "card:1156", mlScore: 0.1240, amount: 49.99, decision: "APPROVE", spike: false, txCount: 1, declineRate: "0.0%", ips: 1, devices: 1, time: "14:27:48", reason: "Regular Cardholder Tx" },
    { id: "3024884", cardId: "card:7721", mlScore: 0.7420, amount: 8.20, decision: "SUSPICIOUS", spike: false, txCount: 5, declineRate: "40.0%", ips: 3, devices: 2, time: "14:27:30", reason: "High Risk Score (τ >= 0.4777)" },
    { id: "3024885", cardId: "card:9930", mlScore: 0.0820, amount: 84.50, decision: "APPROVE", spike: false, txCount: 1, declineRate: "0.0%", ips: 1, devices: 1, time: "14:27:12", reason: "Standard Merchant Purchase" },
    { id: "3024886", cardId: "card:6654", mlScore: 0.8650, amount: 18.50, decision: "SUSPICIOUS", spike: true, txCount: 22, declineRate: "63.6%", ips: 7, devices: 4, time: "14:26:50", reason: "Rapid Multi-IP Fanout" },
    { id: "3024887", cardId: "card:3211", mlScore: 0.0410, amount: 215.00, decision: "APPROVE", spike: false, txCount: 1, declineRate: "0.0%", ips: 1, devices: 1, time: "14:26:33", reason: "Trusted Card Pattern" }
  ];
  renderTransactionTable();
  selectTransaction(0);
}

// Render Table
function renderTransactionTable() {
  const search = (document.getElementById('searchInput')?.value || '').toLowerCase().trim();
  const filtered = allTransactions.filter(tx => {
    const matchesFilter = (currentFilter === 'ALL') || (tx.decision === currentFilter);
    const matchesSearch = !search || 
      tx.cardId.toLowerCase().includes(search) || 
      tx.id.toLowerCase().includes(search) || 
      tx.decision.toLowerCase().includes(search);
    return matchesFilter && matchesSearch;
  });

  const tbody = document.getElementById('transactionTableBody');
  if (!tbody) return;

  if (filtered.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" class="text-center py-6 text-muted font-mono">No matching payment events found</td></tr>`;
    return;
  }

  tbody.innerHTML = filtered.map((tx, idx) => {
    const isFlagged = tx.decision === 'SUSPICIOUS' || tx.decision === 'INSPECT';
    const badgeClass = isFlagged ? 'badge-block' : 'badge-allow';
    const scoreColor = tx.mlScore >= 0.4777 ? 'text-error' : 'text-secondary';
    const isSelected = idx === selectedIndex;
    const selectedStyle = isSelected ? 'bg-surface-container-high/60 border-l-2 border-primary-container' : 'hover:bg-surface-container/50';

    return `
      <tr class="${selectedStyle} transition-colors cursor-pointer border-b border-outline-variant/15" onclick="selectTransaction(${idx})">
        <td class="py-2.5 px-3">
          <span class="badge ${badgeClass}">${tx.decision}</span>
        </td>
        <td class="py-2.5 px-3 font-semibold text-primary">
          <div class="flex items-center gap-1.5 font-mono">
            <span class="material-symbols-outlined text-[15px] ${isFlagged ? 'text-error' : 'text-secondary'}">credit_card</span>
            <span>${tx.cardId}</span>
            <span class="text-muted text-[10px]">#${tx.id}</span>
          </div>
        </td>
        <td class="py-2.5 px-3 font-bold ${scoreColor}">
          <div class="flex items-center gap-1.5 font-mono">
            <span>${tx.mlScore.toFixed(4)}</span>
            <span class="w-8 bg-surface-container-highest rounded-full h-1 overflow-hidden">
              <span class="block h-full ${tx.mlScore >= 0.4777 ? 'bg-error' : 'bg-secondary'}" style="width: ${Math.min(100, tx.mlScore * 100)}%;"></span>
            </span>
          </div>
        </td>
        <td class="py-2.5 px-3 font-semibold font-mono text-on-surface">$${Number(tx.amount).toFixed(2)}</td>
        <td class="py-2.5 px-3 font-mono">
          ${tx.spike ? '<span class="badge badge-block">SPIKE Z>2</span>' : '<span class="text-muted text-[10px]">Normal</span>'}
        </td>
        <td class="py-2.5 px-3 font-mono text-muted">${tx.time || 'Live'}</td>
        <td class="py-2.5 px-3 text-right">
          <button class="px-2 py-0.5 rounded bg-surface-container-high hover:bg-surface-container-highest text-muted hover:text-on-surface text-[10px] font-mono">Inspect</button>
        </td>
      </tr>
    `;
  }).join('');
}

// Select Transaction for Explainability Inspection
function selectTransaction(idx) {
  selectedIndex = idx;
  const tx = allTransactions[idx];
  if (!tx) return;

  const isFlagged = tx.decision === 'SUSPICIOUS' || tx.decision === 'INSPECT';

  document.getElementById('inspectorKey').textContent = `${tx.cardId} (Event #${tx.id})`;
  const decBadge = document.getElementById('inspectorDecisionBadge');
  decBadge.textContent = `DECISION: ${tx.decision} (ML: ${tx.mlScore.toFixed(4)})`;
  decBadge.className = isFlagged ? 'badge badge-block' : 'badge badge-allow';

  document.getElementById('inspectorTag').textContent = `Behavior Profile: ${tx.reason || (isFlagged ? 'High Risk Velocity Anomaly' : 'Standard Baseline Traffic')}`;
  document.getElementById('featTxCount').textContent = `${tx.txCount || 1} reqs/60s`;
  document.getElementById('featDecline').textContent = tx.declineRate || "0.0%";
  document.getElementById('featIps').textContent = `${tx.ips || 1} IPs`;
  document.getElementById('featDevices').textContent = `${tx.devices || 1} tokens`;
  document.getElementById('featAmount').textContent = `$${Number(tx.amount).toFixed(2)}`;
  document.getElementById('featProb').textContent = tx.mlScore.toFixed(4);
  document.getElementById('featContribFinal').textContent = tx.mlScore.toFixed(3);

  // Re-render highlight
  renderTransactionTable();
}

// Filter Tab Switcher
function setFilter(filter) {
  currentFilter = filter;
  ['All', 'Suspicious', 'Approve'].forEach(f => {
    const btn = document.getElementById(`btnFilter${f}`);
    if (!btn) return;
    if (f.toUpperCase() === filter) {
      btn.className = "px-2.5 py-1 rounded font-medium bg-surface-container-high text-primary-fixed shadow-sm";
    } else {
      btn.className = "px-2.5 py-1 rounded text-muted hover:text-on-surface transition-colors";
    }
  });
  renderTransactionTable();
}

// Render Benchmark Sweep Table
function renderSweepTable() {
  const tbody = document.getElementById('sweepTableBody');
  if (!tbody) return;

  tbody.innerHTML = benchmarkSweep.map(row => {
    const isOpt = row.optimal;
    const optClass = isOpt ? "bg-primary-container/10 font-semibold text-primary border-l-2 border-primary-container" : "hover:bg-surface-container/40 text-on-surface";
    return `
      <tr class="${optClass} transition-colors border-b border-outline-variant/10">
        <td class="py-2 px-3 font-mono">
          ${row.threshold.toFixed(4)} ${isOpt ? '<span class="ml-1 text-[9px] px-1 py-0.2 rounded bg-primary-container text-on-primary font-bold">COST-OPTIMAL</span>' : ''}
        </td>
        <td class="py-2 px-3 font-mono">${(row.prec * 100).toFixed(2)}%</td>
        <td class="py-2 px-3 font-mono">${(row.rec * 100).toFixed(2)}%</td>
        <td class="py-2 px-3 font-mono">${row.f1.toFixed(4)}</td>
        <td class="py-2 px-3 font-mono text-warning">${(row.fpr * 100).toFixed(2)}%</td>
        <td class="py-2 px-3 font-mono">${row.fp.toLocaleString()}</td>
        <td class="py-2 px-3 font-mono text-secondary">${row.tp}</td>
        <td class="py-2 px-3 text-right font-mono font-bold ${row.net >= 0 ? 'text-secondary' : 'text-error'}">
          ${row.net >= 0 ? '+' : ''}$${row.net.toLocaleString()}.00
        </td>
      </tr>
    `;
  }).join('');
}

// Fetch Live Metrics from Spring Boot / Postgres
async function fetchEvaluationMetrics() {
  try {
    const res = await fetch(`${API_BASE}/api/evaluation/latest`);
    if (res.ok) {
      const data = await res.json();
      updateMetricsUI(data);
      const connStatus = document.getElementById('backendConnStatus');
      if (connStatus) {
        connStatus.textContent = "API: CONNECTED";
        connStatus.className = "text-secondary font-semibold";
      }
    }
  } catch (err) {
    const connStatus = document.getElementById('backendConnStatus');
    if (connStatus) {
      connStatus.textContent = "STATIC AUDIT VIEW";
      connStatus.className = "text-warning font-semibold";
    }
  }
}

// Fetch Live Audit Log Feed
async function fetchRecentAuditLogs() {
  try {
    const res = await fetch(`${API_BASE}/api/v1/transactions/recent`);
    if (res.ok) {
      const logs = await res.json();
      if (logs && logs.length > 0) {
        const liveCount = logs.length;
        const totalTxEl = document.getElementById('totalTxCard');
        if (totalTxEl) totalTxEl.textContent = liveCount.toLocaleString();

        const badgeEl = document.getElementById('liveStreamBadge');
        if (badgeEl) badgeEl.textContent = `${liveCount} Live`;

        allTransactions = logs.map(l => ({
          id: l.transactionId || l.id,
          cardId: l.cardId,
          mlScore: l.mlScore || 0,
          amount: l.amount || 0,
          decision: l.decision || "APPROVE",
          spike: l.spike || false,
          txCount: l.transactionCount || 1,
          declineRate: (l.declineRate !== undefined ? (l.declineRate * 100).toFixed(0) : "0") + "%",
          ips: l.uniqueIps || 1,
          devices: l.uniqueDevices || 1,
          time: l.transactionTimestamp ? l.transactionTimestamp.split('T')[1]?.substring(0, 8) : "Live",
          reason: l.spike ? "EWMA Spike Triggered" : (l.mlScore >= 0.4777 ? "High ML Risk Alert" : "Normal Authorized Volume")
        }));
        renderTransactionTable();
        selectTransaction(selectedIndex < allTransactions.length ? selectedIndex : 0);
      }
    }
  } catch (e) {}
}

function updateMetricsUI(data) {
  if (!data) return;
  const cm = data.confusion_matrix || data.confusionMatrix;
  const cls = data.classification_metrics || {};
  const costs = data.cost_analysis || {};

  if (data.precisionScore !== undefined) {
    // EvaluationRun JPA Entity
    document.getElementById('precisionCard').textContent = (data.precisionScore * 100).toFixed(2) + "%";
    document.getElementById('benchPrecision').textContent = (data.precisionScore * 100).toFixed(2) + "%";
    document.getElementById('benchRecall').textContent = (data.recallScore * 100).toFixed(2) + "%";
    document.getElementById('benchF1').textContent = data.f1Score.toFixed(4);
    document.getElementById('fprBadge').textContent = (data.falsePositiveRate * 100).toFixed(2) + "%";
    document.getElementById('benchFPR').textContent = (data.falsePositiveRate * 100).toFixed(2) + "%";
    document.getElementById('matrixTP').textContent = data.truePositives;
    document.getElementById('matrixFP').textContent = data.falsePositives;
    document.getElementById('matrixTN').textContent = data.trueNegatives;
    document.getElementById('matrixFN').textContent = data.falseNegatives;
    document.getElementById('fpCountCard').textContent = data.falsePositives;
    document.getElementById('benchFP').textContent = data.falsePositives + " txs";
    document.getElementById('benchTN').textContent = data.trueNegatives + " txs";
    document.getElementById('netValueCard').textContent = "+$" + data.netValue.toLocaleString() + ".00";
    document.getElementById('benchNetValue').textContent = "+$" + data.netValue.toLocaleString() + ".00";
  } else if (cls.precision !== undefined) {
    // metrics.json fallback
    document.getElementById('precisionCard').textContent = (cls.precision * 100).toFixed(2) + "%";
    document.getElementById('benchPrecision').textContent = (cls.precision * 100).toFixed(2) + "%";
    document.getElementById('benchRecall').textContent = (cls.recall * 100).toFixed(2) + "%";
    document.getElementById('benchF1').textContent = cls.f1_score.toFixed(4);
    document.getElementById('fprBadge').textContent = (cls.false_positive_rate * 100).toFixed(2) + "%";
    document.getElementById('benchFPR').textContent = (cls.false_positive_rate * 100).toFixed(2) + "%";
    document.getElementById('matrixTP').textContent = cm.true_positives;
    document.getElementById('matrixFP').textContent = cm.false_positives;
    document.getElementById('matrixTN').textContent = cm.true_negatives;
    document.getElementById('matrixFN').textContent = cm.false_negatives;
    document.getElementById('fpCountCard').textContent = cm.false_positives;
    document.getElementById('benchFP').textContent = cm.false_positives + " txs";
    document.getElementById('benchTN').textContent = cm.true_negatives + " txs";
    if (costs.net_value) {
      document.getElementById('netValueCard').textContent = "+$" + costs.net_value.toLocaleString() + ".00";
      document.getElementById('benchNetValue').textContent = "+$" + costs.net_value.toLocaleString() + ".00";
    }
  }
}

// Operator Overrides
function operatorAction(action) {
  if (action === 'FLAG_INSPECT') {
    showToast("Card flagged for immediate review & temporary suspension.", "error");
  } else if (action === 'REQUEST_3DS') {
    showToast("Step-up 3D-Secure challenge dispatched to cardholder device.", "warning");
  } else {
    showToast("Transaction entity granted 60-minute bypass whitelist.", "success");
  }
}

// Stream Simulator
function triggerSimulation() {
  const isAttack = Math.random() > 0.55;
  const newTx = {
    id: "30" + Math.floor(10000 + Math.random() * 90000),
    cardId: "card:" + Math.floor(1000 + Math.random() * 9000),
    mlScore: isAttack ? (0.75 + Math.random() * 0.22) : (0.04 + Math.random() * 0.35),
    amount: +(Math.random() * 220).toFixed(2),
    decision: isAttack ? "SUSPICIOUS" : "APPROVE",
    spike: isAttack && Math.random() > 0.4,
    txCount: isAttack ? Math.floor(8 + Math.random() * 25) : 1,
    declineRate: isAttack ? "68.0%" : "0.0%",
    ips: isAttack ? Math.floor(4 + Math.random() * 10) : 1,
    devices: isAttack ? Math.floor(3 + Math.random() * 6) : 1,
    time: new Date().toISOString().substring(11, 19),
    reason: isAttack ? "Synthetic Card Velocity Spike Injected" : "Benign Checkout Simulation"
  };

  allTransactions.unshift(newTx);
  if (allTransactions.length > 50) allTransactions.pop();
  renderTransactionTable();
  selectTransaction(0);
  showToast(`Simulated Payment #${newTx.id} -> ${newTx.decision}`, isAttack ? 'warning' : 'success');
}

// Toast Display
function showToast(msg, type) {
  const toast = document.getElementById('toast');
  if (!toast) return;
  toast.textContent = msg;

  if (type === 'error') {
    toast.className = "fixed bottom-6 right-6 z-50 transform translate-y-0 opacity-100 transition-all duration-300 px-4 py-2.5 rounded-lg shadow-xl font-mono text-xs flex items-center gap-2 bg-error/20 text-error border border-error/40";
  } else if (type === 'warning') {
    toast.className = "fixed bottom-6 right-6 z-50 transform translate-y-0 opacity-100 transition-all duration-300 px-4 py-2.5 rounded-lg shadow-xl font-mono text-xs flex items-center gap-2 bg-warning/20 text-warning border border-warning/40";
  } else {
    toast.className = "fixed bottom-6 right-6 z-50 transform translate-y-0 opacity-100 transition-all duration-300 px-4 py-2.5 rounded-lg shadow-xl font-mono text-xs flex items-center gap-2 bg-secondary/20 text-secondary border border-secondary/40";
  }

  setTimeout(() => {
    toast.className = "fixed bottom-6 right-6 z-50 transform translate-y-20 opacity-0 transition-all duration-300 pointer-events-none px-4 py-2.5 rounded-lg shadow-xl font-mono text-xs flex items-center gap-2 border";
  }, 3200);
}

// Live Clock
function updateClock() {
  const clock = document.getElementById('currentTimeUTC');
  if (clock) {
    clock.textContent = new Date().toISOString().substring(11, 19) + " UTC";
  }
}

// Initialize on Load
window.addEventListener('DOMContentLoaded', () => {
  renderSweepTable();
  seedInitialTransactions();
  fetchEvaluationMetrics();
  fetchRecentAuditLogs();
  setInterval(updateClock, 1000);
  setInterval(fetchRecentAuditLogs, 3000);
  setInterval(fetchEvaluationMetrics, 5000);
});
