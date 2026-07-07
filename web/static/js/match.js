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

function renderInsights(ins) {
  if (!ins) return '<p class="empty-state">No insights available.</p>';
  const c = ins.confidence || {};
  const xg = ins.xg || {};
  const form = ins.form || {};
  const hf = form.home || {};
  const af = form.away || {};
  const exps = ins.explanations || [];

  const xgBar = `
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

  const formBlocks = `
    <div class="grid-2">
      <div class="mini-card">
        <h3>${ins.home}</h3>
        <div class="mini-metrics">
          <div><span class="muted">W/D/L</span><strong>${hf.wins ?? 0}/${hf.draws ?? 0}/${hf.losses ?? 0}</strong></div>
          <div><span class="muted">GF</span><strong>${fmt(hf.gf_per_game, 2)}/g</strong></div>
          <div><span class="muted">GA</span><strong>${fmt(hf.ga_per_game, 2)}/g</strong></div>
          <div><span class="muted">CS%</span><strong>${((hf.clean_sheet_rate || 0) * 100).toFixed(0)}%</strong></div>
        </div>
      </div>
      <div class="mini-card">
        <h3>${ins.away}</h3>
        <div class="mini-metrics">
          <div><span class="muted">W/D/L</span><strong>${af.wins ?? 0}/${af.draws ?? 0}/${af.losses ?? 0}</strong></div>
          <div><span class="muted">GF</span><strong>${fmt(af.gf_per_game, 2)}/g</strong></div>
          <div><span class="muted">GA</span><strong>${fmt(af.ga_per_game, 2)}/g</strong></div>
          <div><span class="muted">CS%</span><strong>${((af.clean_sheet_rate || 0) * 100).toFixed(0)}%</strong></div>
        </div>
      </div>
    </div>
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
      <div class="confidence">${c.label || '—'} · ${(100*(c.top_prob||0)).toFixed(1)}% top outcome · ${(100*(c.gap||0)).toFixed(1)} pt gap</div>
    </div>
    ${xgBar}
    <div class="mt-sm"><h3>Recent form (last ${form.recent_n || 5})</h3>${formBlocks}</div>
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
