async function fetchJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || res.statusText);
  return res.json();
}

function pct(n) {
  return `${(n * 100).toFixed(1)}%`;
}

function logoImg(src) {
  const url = src || '/static/logos/default.png';
  return `<img class="team-logo" src="${url}" alt="" onerror="this.onerror=null;this.src='/static/logos/default.png'" />`;
}

function resolveStadiumImg(fixture, homeMeta) {
  const local = homeMeta.stadium_image || '';
  const stored = fixture.stadium_image || '';
  if (local.startsWith('/static/')) return local;
  if (stored.startsWith('/static/')) return stored;
  return local || stored;
}

function renderPlayers(players) {
  if (!players?.length) return '<p class="muted">Squad data not available. Re-run the pipeline to refresh.</p>';
  // Deduplicate by name (keep richest row)
  const byName = new Map();
  for (const p of players) {
    const prev = byName.get(p.name);
    if (!prev || (p.market_value_m || 0) > (prev.market_value_m || 0)) byName.set(p.name, p);
  }
  const unique = [...byName.values()].sort((a, b) => (b.market_value_m || 0) - (a.market_value_m || 0));
  let html = '<div class="table-wrap"><table class="standings-table"><thead><tr><th>Player</th><th>Pos</th><th>Age</th><th>Value</th></tr></thead><tbody>';
  for (const p of unique) {
    html += `<tr><td>${p.name}</td><td>${p.position || '—'}</td><td>${p.age || '—'}</td><td>${p.market_value_m ? `€${p.market_value_m.toFixed(1)}m` : '—'}</td></tr>`;
  }
  html += '</tbody></table></div>';
  return html;
}

function fmt(n, digits = 2) {
  return Number.isFinite(n) ? n.toFixed(digits) : '—';
}

function renderHeatmap(hm) {
  if (!hm?.p?.length) return '<p class="muted">Heatmap unavailable.</p>';
  const max = Math.max(...hm.p.flat());
  let html = '<div class="heatmap-wrap">';
  html += '<div class="heatmap-head"><div class="muted">Score probability heatmap</div><div class="muted small">Columns: home goals · Rows: away goals</div></div>';
  html += '<div class="heatmap-grid">';
  for (let a = 0; a < hm.p.length; a++) {
    for (let h = 0; h < hm.p[a].length; h++) {
      const p = hm.p[h][a]; // stored as [home][away]
      const alpha = max > 0 ? (0.12 + 0.88 * (p / max)) : 0.12;
      html += `<div class="heatmap-cell" style="background: rgba(96,165,250,${alpha})" title="${h}-${a}: ${(p*100).toFixed(1)}%">${(p*100).toFixed(1)}%</div>`;
    }
  }
  html += '</div></div>';
  return html;
}

function polar(cx, cy, r, angleDeg) {
  const rad = (angleDeg * Math.PI) / 180;
  return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
}

function ringSlice(cx, cy, r, ir, start, end, color) {
  if (end - start < 0.05) return '';
  const large = end - start > 180 ? 1 : 0;
  const p1 = polar(cx, cy, r, start);
  const p2 = polar(cx, cy, r, end);
  const p3 = polar(cx, cy, ir, end);
  const p4 = polar(cx, cy, ir, start);
  return `<path d="M ${p1.x.toFixed(2)} ${p1.y.toFixed(2)} A ${r} ${r} 0 ${large} 1 ${p2.x.toFixed(2)} ${p2.y.toFixed(2)} L ${p3.x.toFixed(2)} ${p3.y.toFixed(2)} A ${ir} ${ir} 0 ${large} 0 ${p4.x.toFixed(2)} ${p4.y.toFixed(2)} Z" fill="${color}" />`;
}

function renderDonut(wp, home, away) {
  const pH = wp.home || 0;
  const pD = wp.draw || 0;
  const pA = wp.away || 0;
  const cx = 88;
  const cy = 88;
  const r = 72;
  const ir = 46;
  let angle = -90;
  const slices = [
    { p: pH, color: '#3b82f6' },
    { p: pD, color: '#ef4444' },
    { p: pA, color: '#334155' },
  ];
  let paths = '';
  for (const s of slices) {
    const sweep = s.p * 360;
    if (sweep > 0.2) {
      paths += ringSlice(cx, cy, r, ir, angle, angle + sweep, s.color);
    }
    angle += sweep;
  }
  const favPct = ((wp.favorite_prob || 0) * 100).toFixed(1);
  const favName = wp.favorite_name || home;
  return `
    <div class="donut-wrap">
      <svg class="donut-svg" viewBox="0 0 176 176" aria-hidden="true">
        <circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="rgba(148,163,184,0.12)" stroke-width="${r - ir}" />
        ${paths}
        <text x="${cx}" y="${cy - 4}" text-anchor="middle" class="donut-pct">${favPct}%</text>
        <text x="${cx}" y="${cy + 16}" text-anchor="middle" class="donut-label">${favName}</text>
      </svg>
    </div>`;
}

function renderWinProbability(ins) {
  const wp = ins.win_probability || ins.probs || {};
  const probs = ins.probs || {};
  const c = ins.confidence || {};
  const gapPts = ((c.gap || 0) * 100).toFixed(1);
  const favName = wp.favorite_name || ins.home;
  const confClass = (c.label || '').toLowerCase().includes('high') ? 'high' : (c.label || '').toLowerCase().includes('medium') ? 'medium' : 'low';
  const confFill = Math.min(100, Math.max(8, (c.gap || 0) * 100 * 2.2));

  const tile = (label, val, sub, accent) => `
    <div class="prob-tile${accent ? ' accent' : ''}">
      <div class="prob-tile-head">${label}</div>
      <div class="prob-tile-val">${val}</div>
      <div class="prob-tile-sub muted">${sub}</div>
    </div>`;

  return `
    <div class="section-label">Win probability</div>
    <div class="win-prob-grid">
      ${renderDonut(wp, ins.home, ins.away)}
      <div class="prob-tiles">
        ${tile(ins.home.toUpperCase(), pct(probs.home || wp.home || 0), 'chance of winning', wp.favorite === 'home')}
        ${tile('DRAW', pct(probs.draw || wp.draw || 0), 'chance of draw', wp.favorite === 'draw')}
        ${tile(ins.away.toUpperCase(), pct(probs.away || wp.away || 0), 'chance of winning', wp.favorite === 'away')}
      </div>
    </div>
    <div class="confidence-card conf-${confClass}">
      <div class="confidence-top">
        <div>
          <div class="confidence-title"><span class="conf-icon">🔒</span> ${c.label || 'Confidence'}</div>
          <div class="confidence-detail muted">Model favors <strong>${favName}</strong> by ${gapPts} pts over the next most likely outcome.</div>
        </div>
        <span class="conf-pill">${gapPts} pt gap</span>
      </div>
      <div class="conf-bar"><div class="conf-bar-fill" style="width:${confFill.toFixed(1)}%"></div></div>
    </div>`;
}

function renderCompareCharts(charts, home, away) {
  if (!charts?.length) return '';
  const blocks = charts.map((ch) => {
    const max = Math.max(ch.home, ch.away, 0.01) * 1.15;
    const hPct = Math.max(4, (ch.home / max) * 100);
    const aPct = Math.max(4, (ch.away / max) * 100);
    const fmtVal = (v) => {
      if (ch.fmt === 'pct') return `${v.toFixed(0)}%`;
      if (ch.fmt === 'dec') return v.toFixed(2);
      return String(Math.round(v));
    };
    return `
      <div class="compare-chart">
        <div class="compare-chart-label">${ch.label}</div>
        <div class="compare-bars">
          <div class="compare-bar-col" title="${home}: ${fmtVal(ch.home)}">
            <div class="compare-bar home" style="height:${hPct.toFixed(1)}%"></div>
          </div>
          <div class="compare-bar-col" title="${away}: ${fmtVal(ch.away)}">
            <div class="compare-bar away" style="height:${aPct.toFixed(1)}%"></div>
          </div>
        </div>
      </div>`;
  }).join('');
  return `
    <div class="compare-head">
      <div class="section-label">Form &amp; statistical comparison</div>
      <div class="compare-legend"><span class="legend-dot home"></span>${home}<span class="legend-dot away"></span>${away}</div>
    </div>
    <div class="compare-charts">${blocks}</div>`;
}

function renderFormBadges(sequence) {
  if (!sequence?.length) return '<span class="muted">No recent games</span>';
  return sequence.map((r) => `<span class="form-badge ${r}">${r}</span>`).join('');
}

function renderFormDetailCard(team, f) {
  const games = (f.wins || 0) + (f.draws || 0) + (f.losses || 0);
  return `
    <div class="form-detail-card">
      <h3>${team}</h3>
      <div class="form-badges">${renderFormBadges(f.sequence)}</div>
      <div class="form-record">${f.wins || 0}W ${f.draws || 0}D ${f.losses || 0}L · ${games} games</div>
      <div class="form-stats">
        <div><span class="muted">Goals scored</span><strong>${fmt(f.gf_per_game, 2)}/game</strong></div>
        <div><span class="muted">Conceded</span><strong>${fmt(f.ga_per_game, 2)}/game</strong></div>
        <div><span class="muted">Clean sheet rate</span><strong>${((f.clean_sheet_rate || 0) * 100).toFixed(0)}%</strong></div>
        <div><span class="muted">GD/game</span><strong>${f.gd_per_game >= 0 ? '+' : ''}${fmt(f.gd_per_game, 2)}</strong></div>
      </div>
    </div>`;
}

function renderFormMomentum(ins) {
  const hf = ins.form?.home || {};
  const af = ins.form?.away || {};
  const row = (team, f) => {
    const m = f.momentum || 0;
    const left = 50 + m * 42;
    const sign = m >= 0 ? '+' : '';
    return `
      <div class="momentum-row">
        <div class="momentum-team">${team}</div>
        <div class="momentum-track">
          <span class="momentum-end muted">Low</span>
          <div class="momentum-bar">
            <div class="momentum-thumb" style="left:${left.toFixed(1)}%"></div>
          </div>
          <span class="momentum-end muted">High</span>
        </div>
        <div class="momentum-val">Neutral ${sign}${m.toFixed(2)}</div>
        <div class="momentum-sub muted">${f.momentum_label || ''}</div>
      </div>`;
  };
  return `
    <div class="section-label">Form momentum</div>
    <p class="momentum-desc muted">Form momentum scores each team's recent run of results weighted by recency — a positive score boosts their predicted attacking output in the simulation.</p>
    ${row(ins.home, hf)}
    ${row(ins.away, af)}`;
}

function renderTeamRadar(ins) {
  const radar = ins.team_radar || {};
  const axes = radar.axes || [];
  if (!axes.length) return '';

  const cx = 210;
  const cy = 210;
  const R = 118;
  const labelR = R + 34;
  const n = axes.length;

  const pt = (idx, norm) => {
    const angle = -Math.PI / 2 + (2 * Math.PI * idx) / n;
    const r = R * Math.max(0, Math.min(1, norm || 0));
    return { x: cx + r * Math.cos(angle), y: cy + r * Math.sin(angle) };
  };

  const poly = (side) => {
    const pts = axes.map((ax, i) => pt(i, ax[`${side}_norm`]));
    return `${pts.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ')}`;
  };

  const rings = [0.25, 0.5, 0.75, 1.0].map((level) => {
    const pts = Array.from({ length: n }, (_, i) => pt(i, level));
    return `<polygon class="radar-ring" points="${pts.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ')}" />`;
  }).join('');

  const spokes = axes.map((_, i) => {
    const end = pt(i, 1);
    return `<line class="radar-spoke" x1="${cx}" y1="${cy}" x2="${end.x.toFixed(1)}" y2="${end.y.toFixed(1)}" />`;
  }).join('');

  const labels = axes.map((ax, i) => {
    const angle = -Math.PI / 2 + (2 * Math.PI * i) / n;
    const x = cx + labelR * Math.cos(angle);
    const y = cy + labelR * Math.sin(angle);
    const anchor = Math.abs(Math.cos(angle)) < 0.2 ? 'middle' : (Math.cos(angle) > 0 ? 'start' : 'end');
    return `<text class="radar-label" x="${x.toFixed(1)}" y="${y.toFixed(1)}" text-anchor="${anchor}" dominant-baseline="middle">${ax.label}</text>`;
  }).join('');

  return `
    <div class="mt-sm radar-card">
      <div class="section-label">Team comparison radar</div>
      <p class="radar-desc muted">Six key stats side by side — a bigger, more filled-out shape means a stronger all-around team. Notice when <strong>Raw Goals/Game</strong> sits further out than <strong>xG</strong>: that can mean some scoring came against weaker opposition.</p>
      <div class="radar-wrap">
        <svg class="radar-svg" viewBox="0 0 420 420" aria-label="Team comparison radar chart">
          ${rings}
          ${spokes}
          <polygon class="radar-fill away" points="${poly('away')}" />
          <polygon class="radar-fill home" points="${poly('home')}" />
          <polygon class="radar-stroke away" points="${poly('away')}" />
          <polygon class="radar-stroke home" points="${poly('home')}" />
          ${labels}
        </svg>
        <div class="radar-legend">
          <span><span class="legend-dot home"></span>${ins.home}</span>
          <span><span class="legend-dot away"></span>${ins.away}</span>
        </div>
      </div>
    </div>`;
}

function renderH2H(ins) {
  const h2h = ins.h2h || {};
  const summary = h2h.summary || {};
  const matches = h2h.matches || [];
  const n = h2h.n || matches.length || 8;

  const sumRow = summary.games
    ? `<div class="h2h-summary">
        <div class="h2h-sum-item"><span class="muted">Record</span><strong>${summary.home_wins}W ${summary.draws}D ${summary.away_wins}L</strong></div>
        <div class="h2h-sum-item"><span class="muted">GF</span><strong>${fmt(summary.gf_per_game, 2)}/g</strong></div>
        <div class="h2h-sum-item"><span class="muted">GA</span><strong>${fmt(summary.ga_per_game, 2)}/g</strong></div>
        <div class="h2h-sum-item"><span class="muted">BTTS</span><strong>${((summary.btts_rate || 0) * 100).toFixed(0)}%</strong></div>
        <div class="h2h-sum-item"><span class="muted">CS%</span><strong>${((summary.clean_sheet_rate || 0) * 100).toFixed(0)}%</strong></div>
      </div>`
    : `<p class="muted">No recent head-to-head matches in the training data.</p>`;

  const chip = (r) => `<span class="h2h-chip ${r}">${r}</span>`;

  const list = matches.length
    ? `<div class="h2h-list">
        ${matches.map((m) => `
          <div class="h2h-row">
            <div class="h2h-left">
              ${chip(m.result_for_home)}
              <div class="h2h-teams">${m.home_team} <span class="muted">vs</span> ${m.away_team}</div>
            </div>
            <div class="h2h-mid muted">${m.date || '—'}</div>
            <div class="h2h-score">${m.score || '—'}</div>
          </div>
        `).join('')}
      </div>`
    : '';

  return `
    <div class="mt-sm">
      <div class="h2h-head">
        <h3>Head-to-head (last ${n})</h3>
        <div class="muted small">${ins.home} perspective</div>
      </div>
      ${sumRow}
      ${list}
    </div>
  `;
}

function renderInsights(ins) {
  if (!ins) return '<p class="empty-state">No insights available.</p>';
  const xg = ins.xg || {};
  const form = ins.form || {};
  const hf = form.home || {};
  const af = form.away || {};
  const exps = ins.explanations || [];

  const xgBar = `
    <div class="section-label">Expected goals (xG)</div>
    <div class="xg-cards">
      <div class="xg-card">
        <div class="xg-label">${ins.home} xG</div>
        <div class="xg-value">${fmt(xg.home, 2)}</div>
      </div>
      <div class="xg-card">
        <div class="xg-label">${ins.away} xG</div>
        <div class="xg-value">${fmt(xg.away, 2)}</div>
      </div>
    </div>
    <div class="xg-bar">
      <div class="xg-fill home" style="width:${(100 * (xg.home / Math.max(0.01, (xg.home + xg.away)))).toFixed(1)}%"></div>
      <div class="xg-fill away" style="width:${(100 * (xg.away / Math.max(0.01, (xg.home + xg.away)))).toFixed(1)}%"></div>
    </div>
  `;

  const formSection = `
    <div class="mt-sm">${renderCompareCharts(ins.comparison_charts, ins.home, ins.away)}</div>
    <div class="grid-2 mt-sm">
      ${renderFormDetailCard(ins.home, hf)}
      ${renderFormDetailCard(ins.away, af)}
    </div>
    <div class="mt-sm">${renderFormMomentum(ins)}</div>
  `;

  const expl = exps.length
    ? `<div class="explain-list">${exps.map(e => `
        <div class="explain-row">
          <div class="explain-title">${e.title}</div>
          <div class="explain-badge">${e.badge}</div>
          <div class="explain-detail muted">${e.detail}</div>
        </div>`).join('')}
      </div>`
    : '<p class="muted">No explanation generated.</p>';

  return `
    <div class="insights-head">
      <h2>Match Insights</h2>
    </div>
    ${renderWinProbability(ins)}
    ${xgBar}
    <div class="mt-sm"><h3>Recent form (last ${form.recent_n || 5})</h3>${formSection}</div>
    ${renderTeamRadar(ins)}
    ${renderH2H(ins)}
    <div class="mt-sm">${renderHeatmap(ins.score_heatmap)}</div>
    <div class="mt-sm"><h3>Why the model predicted this</h3>${expl}</div>
  `;
}

async function load() {
  const params = new URLSearchParams(window.location.search);
  const home = params.get('home');
  const away = params.get('away');
  const date = params.get('date');
  if (!home || !away) {
    document.getElementById('match-preview').innerHTML = '<p class="empty-state">Missing match parameters.</p>';
    return;
  }

  const [fixture, insights, homeSquad, awaySquad, teams] = await Promise.all([
    fetchJSON(`/api/fixture?home=${encodeURIComponent(home)}&away=${encodeURIComponent(away)}&date=${encodeURIComponent(date || '')}`),
    fetchJSON(`/api/fixture/insights?home=${encodeURIComponent(home)}&away=${encodeURIComponent(away)}&date=${encodeURIComponent(date || '')}`).catch(() => null),
    fetchJSON(`/api/teams/${encodeURIComponent(home)}/squad`),
    fetchJSON(`/api/teams/${encodeURIComponent(away)}/squad`),
    fetchJSON('/api/teams').catch(() => ({})),
  ]);

  const homeMeta = teams[home] || {};
  const awayMeta = teams[away] || {};
  const stadiumImg = resolveStadiumImg(fixture, homeMeta);
  const dateLabel = fixture.Date ? new Date(fixture.Date).toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' }) : '';

  document.getElementById('match-title').textContent = `${home} vs ${away}`;
  document.getElementById('match-sub').textContent = `${dateLabel}${fixture.stadium ? ` · ${fixture.stadium}` : ''}`;

  const stadiumBanner = stadiumImg
    ? `<div class="fixture-stadium match-hero-stadium"><img src="${stadiumImg}" alt="" onerror="this.onerror=null;this.src='${stadiumImg.replace('.jpg','.svg')}'" /><div class="fixture-stadium-overlay"><span class="home-badge">Home · ${home}</span><span class="stadium-name">${fixture.stadium || homeMeta.stadium || ''}</span></div></div>`
    : '';

  document.getElementById('match-preview').innerHTML = `
    ${stadiumBanner}
    <div class="fixture-body">
      <div class="fixture-matchup">
        <div class="team-side home">${logoImg(fixture.home_logo || homeMeta.logo)}<span class="team-name">${home}</span></div>
        <div class="score-center"><div class="pred-score">${fixture.pred_score || '—'}</div><div class="score-label">Predicted score</div></div>
        <div class="team-side away">${logoImg(fixture.away_logo || awayMeta.logo)}<span class="team-name">${away}</span></div>
      </div>
      <p style="text-align:center;margin:0.75rem 0;color:var(--muted);font-size:0.85rem">
        Home ${pct(fixture.p_home)} · Draw ${pct(fixture.p_draw)} · Away ${pct(fixture.p_away)}
      </p>
    </div>`;

  document.getElementById('home-squad-title').textContent = `${home} Squad`;
  document.getElementById('away-squad-title').textContent = `${away} Squad`;
  document.getElementById('home-squad').innerHTML = renderPlayers(homeSquad.players);
  document.getElementById('away-squad').innerHTML = renderPlayers(awaySquad.players);

  const insightsEl = document.getElementById('match-insights');
  if (insightsEl) insightsEl.innerHTML = renderInsights(insights);
}

load().catch((err) => {
  document.getElementById('match-preview').innerHTML = `<p class="empty-state">Failed to load: ${err.message}</p>`;
});
