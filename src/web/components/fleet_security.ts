// src/web/components/fleet_security.ts — Varnostni pregled flote (Fleet Security).
import type { FleetSecurityStatus } from '../../shared/types';
import { ageAgo } from '../api';

const SEV_LABEL: Record<string, string> = { critical: 'kritična', high: 'visoka', medium: 'srednja', low: 'nizka' };

function esc(s: unknown): string {
  return String(s ?? '').replace(/[&<>"']/g, (c) =>
    c === '&' ? '&amp;' : c === '<' ? '&lt;' : c === '>' ? '&gt;' : c === '"' ? '&quot;' : '&#39;');
}

function gradeFor(score: number): string {           // skladno s spec (A>=90, B>=80, C>=70, D>=60, F<60)
  if (score >= 90) return 'A';
  if (score >= 80) return 'B';
  if (score >= 70) return 'C';
  if (score >= 60) return 'D';
  return 'F';
}

function gradeVariant(grade: string): string {
  return grade === 'A' || grade === 'B' ? 'good' : grade === 'F' ? 'crit' : 'warn';
}

function craIcon(status: string): string {
  if (status === 'compliant') return '<span class="s-ok">✓</span>';
  if (status === 'non_compliant') return '<span class="s-crit">✗</span>';
  if (status === 'partial') return '<span class="s-warn">~</span>';
  return '<span class="s-run">—</span>';            // not_applicable
}

function sevBadge(sev: string): string {
  const cls = sev === 'critical' ? 'sev-crit' : sev === 'high' ? 'sev-warn' : 'sev-med';
  return `<span class="sev-badge ${cls}">${esc(SEV_LABEL[sev] || sev)}</span>`;
}

export function renderFleetSecurity(el: HTMLElement, d: FleetSecurityStatus): void {
  if (!d || d.ok === false) {                        // defenzivno: data je lahko {ok:false}
    el.innerHTML = `<div class="panel-state err">⚠️ ${esc(d?.error || 'Napaka pri nalaganju')}</div>`;
    return;
  }
  const { fleet = {}, devices = [], findings = [], findings_by_severity = {}, cra = [], monitor = {}, redteam = {}, supplychain = {}, threatintel = {}, generated_at } = d;
  const deviceCount = fleet.device_count ?? devices.length;
  const mean = fleet.mean_score ?? null;
  const meanGrade = mean == null ? '' : gradeFor(mean);
  const sev = findings_by_severity as Record<string, number>;
  const nCrit = sev.critical ?? 0, nHigh = sev.high ?? 0, nMed = sev.medium ?? 0, nLow = sev.low ?? 0;
  const total = nCrit + nHigh + nMed + nLow;
  const kpiVar = nCrit > 0 ? 'crit' : nHigh > 0 ? 'warn' : total > 0 ? 'good' : '';

  let html = `<div class="fsec-meta">posnetek ${generated_at ? ageAgo(new Date(generated_at).getTime() / 1000) : '—'}</div>`;
  html += `<div class="kpis">`;
  html += `<div class="kpi${mean == null ? '' : ' ' + gradeVariant(meanGrade)}"><div class="k">Povprečje</div><div class="v">${mean ?? '—'}${meanGrade ? `<span class="grade-chip g-${meanGrade.toLowerCase()}">${meanGrade}</span>` : ''}</div><div class="d">posture score 0–100</div></div>`;
  html += `<div class="kpi"><div class="k">Naprave</div><div class="v">${deviceCount}</div><div class="d">${devices.length} v inventarju</div></div>`;
  html += `<div class="kpi ${kpiVar}"><div class="k">Odprte najdbe</div><div class="v">${total}</div><div class="sev-mini"><span class="sev-crit">${nCrit} krit</span><span class="sev-warn">${nHigh} vis</span><span class="sev-med">${nMed} med</span><span class="sev-low">${nLow} niz</span></div></div>`;
  html += `</div>`;

  if (devices.length) {
    html += `<div class="fleet-section">Naprave</div><div class="fsec-table">`;
    html += `<div class="fsec-row fsec-head"><span>naprava</span><span>vloga</span><span>score</span><span>ocena</span><span>najdbe (crit/vis)</span></div>`;
    for (const dv of devices) {
      const counts = dv.counts || {};
      const countLabel = dv.score == null ? '—' : `${counts.critical ?? 0} / ${counts.high ?? 0}`;
      html += `<div class="fsec-row"><span class="fsec-host">${esc(dv.hostname || dv.device_id)}</span><span class="fsec-role">${esc(dv.role)}</span><span class="fsec-score">${dv.score ?? '—'}</span><span>${dv.grade ? `<span class="grade-chip g-${esc(dv.grade).toLowerCase()}">${esc(dv.grade)}</span>` : '—'}</span><span class="fsec-counts">${countLabel}</span></div>`;
    }
    html += `</div>`;
  }

  if (findings.length) {
    html += `<div class="fleet-section">Odprte najdbe (${findings.length})</div>`;
    for (const f of findings) {
      html += `<div class="fsec-finding">${sevBadge(f.severity)}<span class="fsec-fdetail">${esc(f.category)} — ${esc(f.detail)}</span><span class="fsec-fhost">${esc(f.device_id)}</span></div>`;
    }
  } else {
    html += `<div class="fleet-section">Odprte najdbe</div><div class="fleet-row" style="color:var(--faint)">— ni odprtih najdb</div>`;
  }

  if (cra.length) {
    html += `<div class="fleet-section">CRA skladnost</div><div class="fsec-cra">`;
    for (const c of cra) {
      html += `<div class="fsec-row fsec-cra-row"><span class="fsec-cra-icon">${craIcon(c.status)}</span><span class="fsec-cra-id">${esc(c.requirement_id)}</span><span class="fsec-cra-title">${esc(c.title)}</span></div>`;
    }
    html += `</div>`;
  }

  html += `<div class="fleet-section">Moduli</div><div class="fsec-modules">`;
  const mods: Array<[string, string, number]> = [
    ['Monitor', 'anomalije', monitor.open_anomaly_findings ?? 0],
    ['Red team', 'vulnerable', redteam.vulnerable ?? 0],
    ['Supply chain', 'odprte', supplychain.open_findings ?? 0],
    ['Threat intel', 'ranljivosti', threatintel.open_vulnerabilities ?? 0],
  ];
  for (const [name, label, n] of mods) {
    html += `<div class="fsec-module"><span class="fsec-mod-name">${name}</span><span class="fsec-mod-count">${n}</span><span class="fsec-mod-label">${label}</span></div>`;
  }
  html += `</div>`;

  el.innerHTML = html;
}
