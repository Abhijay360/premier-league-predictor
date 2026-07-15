async function fetchJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || res.statusText);
  return res.json();
}

function logoImg(src, cls = 'team-logo-lg') {
  const url = src || '/static/logos/default.png';
  return `<img class="${cls}" src="${url}" alt="" onerror="this.onerror=null;this.src='/static/logos/default.png'" />`;
}

function teamUrl(team) {
  return `/team?team=${encodeURIComponent(team)}`;
}

function playerUrl(team, name) {
  return `/player?team=${encodeURIComponent(team)}&name=${encodeURIComponent(name)}`;
}

function matchUrl(m) {
  return `/match?home=${encodeURIComponent(m.HomeTeam)}&away=${encodeURIComponent(m.AwayTeam)}&date=${encodeURIComponent(m.Date || '')}`;
}

function renderTrophies(trophies, recent) {
  const recentBlock = recent
    ? `<div class="highlight-card trophy-highlight">
        <div class="highlight-label">Most recent major honour</div>
        <div class="highlight-value">${recent.label || recent.competition}</div>
        <div class="muted small">${recent.season || recent.most_recent || ''}</div>
      </div>`
    : '';
  const list = trophies?.length
    ? `<div class="trophy-grid">${trophies.map((t) => `
        <div class="trophy-card">
          <div class="trophy-name">${t.competition}</div>
          <div class="trophy-count">${t.count}×</div>
          <div class="trophy-recent muted">Last: ${t.most_recent}</div>
        </div>`).join('')}</div>`
    : '<p class="muted">No trophy data available.</p>';
  return recentBlock + list;
}

function renderHistory(rows) {
  const pl = rows.filter((r) => r.in_pl);
  if (!pl.length) return '<p class="muted">No Premier League history in training data.</p>';
  let html = '<div class="table-wrap"><table class="standings-table"><thead><tr><th>Season</th><th>P</th><th>W</th><th>D</th><th>L</th><th>GF</th><th>GA</th><th>GD</th><th>Pts</th></tr></thead><tbody>';
  for (const r of pl.slice().reverse()) {
    html += `<tr><td>${r.label}</td><td>${r.played}</td><td>${r.won}</td><td>${r.drawn}</td><td>${r.lost}</td><td>${r.gf}</td><td>${r.ga}</td><td>${r.gd > 0 ? '+' : ''}${r.gd}</td><td><strong>${r.points}</strong></td></tr>`;
  }
  html += '</tbody></table></div>';
  return html;
}

function renderFixtures(fixtures, team) {
  const card = (m) => {
    const isHome = m.HomeTeam === team;
    const opp = isHome ? m.AwayTeam : m.HomeTeam;
    const venue = isHome ? 'Home' : 'Away';
    const score = m.played ? `${m.FTHG}–${m.FTAG}` : (m.pred_score || '—');
    const date = m.Date ? new Date(m.Date).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) : '—';
    return `<a class="fixture-mini" href="${matchUrl(m)}">
      <div class="fixture-mini-top"><span class="muted">${date}</span><span class="pill small">${venue}</span></div>
      <div class="fixture-mini-main"><strong>${team}</strong> vs ${opp}</div>
      <div class="fixture-mini-score">${score}</div>
    </a>`;
  };
  const up = fixtures.upcoming || [];
  const played = fixtures.played || [];
  return `
    <div class="grid-2">
      <div>
        <h3>Upcoming (${up.length})</h3>
        <div class="fixture-mini-list">${up.length ? up.slice(0, 8).map(card).join('') : '<p class="muted">No upcoming fixtures.</p>'}</div>
      </div>
      <div>
        <h3>Played (${played.length})</h3>
        <div class="fixture-mini-list">${played.length ? played.slice(-8).reverse().map(card).join('') : '<p class="muted">Season not started.</p>'}</div>
      </div>
    </div>`;
}

function renderSquad(squad, team) {
  const players = squad?.players || [];
  if (!players.length) return '<p class="muted">Squad data unavailable.</p>';
  const sorted = [...players].sort((a, b) => (b.market_value_m || 0) - (a.market_value_m || 0));
  let html = '<div class="squad-list">';
  for (const p of sorted) {
    const face = p.tm_player_id
      ? `<img class="player-face-sm" src="https://tmssl.akamaized.net/images/portrait/header/${p.tm_player_id}.png" alt="" loading="lazy" onerror="this.style.display='none'" />`
      : '';
    html += `<a class="squad-row" href="${playerUrl(team, p.name)}">
      <div class="squad-row-name">${face}<span>${p.name}</span></div>
      <div class="squad-row-meta muted">${p.position || '—'}</div>
      <div class="squad-row-val">${p.market_value_m ? `€${p.market_value_m.toFixed(1)}m` : '—'}</div>
    </a>`;
  }
  html += '</div>';
  return html;
}

async function load() {
  const params = new URLSearchParams(window.location.search);
  const team = params.get('team');
  if (!team) {
    document.getElementById('team-content').innerHTML = '<p class="empty-state">Missing team parameter.</p>';
    return;
  }

  const [profile, squad] = await Promise.all([
    fetchJSON(`/api/teams/${encodeURIComponent(team)}/profile`),
    fetchJSON(`/api/teams/${encodeURIComponent(team)}/squad`).catch(() => ({ players: [] })),
  ]);

  document.title = `${team} · Premier League Predictor`;
  const info = profile.info || {};
  const stadiumImg = info.stadium_image || '';

  document.getElementById('team-hero').innerHTML = `
    <div class="profile-hero-row">
      <a href="${teamUrl(team)}" class="profile-logo-link">${logoImg(info.logo)}</a>
      <div>
        <h1>${team}</h1>
        <p class="hero-sub">${info.stadium || ''}${info.city ? ` · ${info.city}` : ''}${profile.nickname ? ` · ${profile.nickname}` : ''}${profile.founded ? ` · Est. ${profile.founded}` : ''}</p>
        ${profile.most_recent_major ? `<div class="hero-badge">${profile.most_recent_major.label}</div>` : ''}
      </div>
    </div>
    ${stadiumImg ? `<div class="profile-stadium"><img src="${stadiumImg}" alt="" onerror="this.onerror=null;this.src='${stadiumImg.replace('.jpg','.svg')}'" /></div>` : ''}`;

  const best = profile.best_pl_season;
  const stats = `
    <div class="stats-row">
      <div class="stat-card"><div class="stat-label">Squad value</div><div class="stat-value">${squad.market_value_m ? `€${Math.round(squad.market_value_m)}m` : '—'}</div></div>
      <div class="stat-card"><div class="stat-label">Net spend</div><div class="stat-value">${squad.net_spend_m != null ? `€${squad.net_spend_m.toFixed(0)}m` : '—'}</div></div>
      <div class="stat-card"><div class="stat-label">Best PL season</div><div class="stat-value">${best ? `${best.points} pts` : '—'}</div></div>
      <div class="stat-card"><div class="stat-label">${profile.predict_season_label} fixtures</div><div class="stat-value">${(profile.fixtures?.upcoming?.length || 0) + (profile.fixtures?.played?.length || 0)}</div></div>
    </div>`;

  document.getElementById('team-content').innerHTML = `
    ${stats}
    <div class="card mt"><h2>Honours</h2>${renderTrophies(profile.trophies, profile.most_recent_major)}</div>
    <div class="card mt"><h2>${profile.predict_season_label} fixtures</h2>${renderFixtures(profile.fixtures, team)}</div>
    <div class="grid-2 mt">
      <div class="card"><h2>PL season history</h2>${renderHistory(profile.season_history || [])}</div>
      <div class="card"><h2>Squad</h2>${renderSquad(squad, team)}</div>
    </div>`;
}

load().catch((err) => {
  document.getElementById('team-content').innerHTML = `<p class="empty-state">Failed to load: ${err.message}</p>`;
});
