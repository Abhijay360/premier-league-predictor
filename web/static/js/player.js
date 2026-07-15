async function fetchJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || res.statusText);
  return res.json();
}

function logoImg(src, cls = 'team-logo-sm') {
  const url = src || '/static/logos/default.png';
  return `<img class="${cls}" src="${url}" alt="" onerror="this.onerror=null;this.src='/static/logos/default.png'" />`;
}

function teamUrl(team) {
  return `/team?team=${encodeURIComponent(team)}`;
}

function playerPhoto(p) {
  const initials = (p.name || '?').split(' ').map((w) => w[0]).join('').slice(0, 2).toUpperCase();
  if (p.photo_url) {
    return `<img class="player-photo" src="${p.photo_url}" alt="${p.name || ''}" loading="lazy"
      onerror="this.onerror=null;this.outerHTML='<div class=\\'player-avatar\\'>${initials}</div>'" />`;
  }
  return `<div class="player-avatar">${initials}</div>`;
}

function renderTrophies(trophies) {
  if (!trophies?.length) {
    return '<p class="muted">No individual trophies listed on Transfermarkt for this player yet.</p>';
  }
  return `<div class="trophy-list">${trophies.map((t) => `
    <div class="trophy-pill">
      <span class="trophy-pill-name">${t.competition}${t.club ? ` · ${t.club}` : ''}</span>
      <span class="trophy-pill-season">${t.season || t.label || ''}</span>
    </div>`).join('')}</div>`;
}

function renderCareer(career) {
  if (!career?.length) return '<p class="muted">Career history not curated yet.</p>';
  return `<div class="table-wrap"><table class="standings-table"><thead><tr><th>Club</th><th>From</th><th>To</th></tr></thead><tbody>
    ${career.map((c) => `<tr><td>${c.club}</td><td>${c.from}</td><td>${c.to}</td></tr>`).join('')}
  </tbody></table></div>`;
}

function renderSeasonStats(stats) {
  if (!stats?.length) return '<p class="muted">Past-season stats not available for this player.</p>';
  const hasApps = stats.some((s) => s.apps != null || s.goals != null);
  if (!hasApps) {
    return `<div class="table-wrap"><table class="standings-table"><thead><tr><th>Period</th><th>Club</th></tr></thead><tbody>
      ${stats.map((s) => `<tr><td>${s.season}</td><td>${s.club}</td></tr>`).join('')}
    </tbody></table></div>
    <p class="muted small">Career timeline from Transfermarkt transfers.</p>`;
  }
  return `<div class="table-wrap"><table class="standings-table"><thead><tr><th>Season</th><th>Club</th><th>Competition</th><th>Apps</th><th>G</th><th>A</th><th>Mins</th></tr></thead><tbody>
    ${stats.map((s) => `<tr>
      <td>${s.season}</td>
      <td>${s.club}</td>
      <td>${s.competition || '—'}</td>
      <td>${s.apps ?? '—'}</td>
      <td>${s.goals ?? '—'}</td>
      <td>${s.assists ?? '—'}</td>
      <td>${s.minutes ?? '—'}</td>
    </tr>`).join('')}
  </tbody></table></div>`;
}

async function load() {
  const params = new URLSearchParams(window.location.search);
  const team = params.get('team');
  const name = params.get('name');
  if (!team || !name) {
    document.getElementById('player-content').innerHTML = '<p class="empty-state">Missing player parameters.</p>';
    return;
  }

  const p = await fetchJSON(`/api/players/profile?team=${encodeURIComponent(team)}&name=${encodeURIComponent(name)}`);
  document.title = `${p.name} · ${team}`;
  const totals = p.career_totals || {};

  document.getElementById('player-hero').innerHTML = `
    <div class="profile-hero-row">
      ${playerPhoto(p)}
      <div>
        <h1>${p.name}</h1>
        <p class="hero-sub">
          <a class="inline-team-link" href="${teamUrl(team)}">${logoImg(p.team_info?.logo)} ${team}</a>
          · ${p.position || '—'}${p.age ? ` · ${p.age} yrs` : ''}${p.nationality ? ` · ${p.nationality}` : ''}${p.foot ? ` · ${p.foot} foot` : ''}
        </p>
        ${p.market_value_m ? `<div class="hero-badge">Market value €${p.market_value_m.toFixed(1)}m</div>` : ''}
      </div>
    </div>`;

  const summary = p.summary
    ? `<div class="limit-banner">${p.summary}</div>`
    : '';
  const note = p.club_trophies_note
    ? `<p class="muted">${p.club_trophies_note}</p>`
    : '';

  document.getElementById('player-content').innerHTML = `
    ${summary}${note}
    <div class="stats-row">
      <div class="stat-card"><div class="stat-label">Market value</div><div class="stat-value">${p.market_value_m ? `€${p.market_value_m.toFixed(1)}m` : '—'}</div></div>
      <div class="stat-card"><div class="stat-label">Career apps</div><div class="stat-value">${totals.apps ?? '—'}</div></div>
      <div class="stat-card"><div class="stat-label">Career goals</div><div class="stat-value">${totals.goals ?? '—'}</div></div>
      <div class="stat-card"><div class="stat-label">Career assists</div><div class="stat-value">${totals.assists ?? '—'}</div></div>
      <div class="stat-card"><div class="stat-label">Position</div><div class="stat-value">${p.position || '—'}</div></div>
      <div class="stat-card"><div class="stat-label">Joined</div><div class="stat-value">${p.joined || '—'}</div></div>
    </div>
    <div class="card mt"><h2>Season stats</h2>${renderSeasonStats(p.season_stats)}</div>
    <div class="card mt"><h2>Trophies & honours</h2>${renderTrophies(p.trophies)}</div>
    <div class="grid-2 mt">
      <div class="card"><h2>Career clubs</h2>${renderCareer(p.career)}</div>
      <div class="card">
        <h2>Club honours</h2>
        <p class="muted">See <a href="${teamUrl(team)}" style="color:var(--accent-2)">${team} team page</a> for full club trophy cabinet and fixtures.</p>
      </div>
    </div>`;
}

load().catch((err) => {
  document.getElementById('player-content').innerHTML = `<p class="empty-state">Failed to load: ${err.message}</p>`;
});
