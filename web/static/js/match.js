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

async function load() {
  const params = new URLSearchParams(window.location.search);
  const home = params.get('home');
  const away = params.get('away');
  const date = params.get('date');
  if (!home || !away) {
    document.getElementById('match-preview').innerHTML = '<p class="empty-state">Missing match parameters.</p>';
    return;
  }

  const [fixture, homeSquad, awaySquad, teams] = await Promise.all([
    fetchJSON(`/api/fixture?home=${encodeURIComponent(home)}&away=${encodeURIComponent(away)}&date=${encodeURIComponent(date || '')}`),
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
}

load().catch((err) => {
  document.getElementById('match-preview').innerHTML = `<p class="empty-state">Failed to load: ${err.message}</p>`;
});
