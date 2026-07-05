const SEASON_LABEL = '2026–27';
let PREDICT_SEASON = '2627';
let TEAMS = {};

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

function toast(msg, isError = false) {
  const el = $('#toast');
  el.textContent = msg;
  el.classList.toggle('error', isError);
  el.classList.remove('hidden');
  setTimeout(() => el.classList.add('hidden'), 4000);
}

async function fetchJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || res.statusText);
  return res.json();
}

function pct(n) {
  return `${(n * 100).toFixed(1)}%`;
}

function ftrLabel(code) {
  return { H: 'Home win', D: 'Draw', A: 'Away win' }[code] || code;
}

function teamMeta(name) {
  return TEAMS[name] || { name, logo: '', stadium: 'Home Ground', stadium_image: '', city: '' };
}

function renderProbBars(pHome, pDraw, pAway) {
  return `
    <div class="prob-bars">
      <div class="prob-row">
        <span class="prob-label">Home</span>
        <div class="prob-track"><div class="prob-fill home" style="width:${pHome * 100}%"></div></div>
        <span class="prob-pct">${pct(pHome)}</span>
      </div>
      <div class="prob-row">
        <span class="prob-label">Draw</span>
        <div class="prob-track"><div class="prob-fill draw" style="width:${pDraw * 100}%"></div></div>
        <span class="prob-pct">${pct(pDraw)}</span>
      </div>
      <div class="prob-row">
        <span class="prob-label">Away</span>
        <div class="prob-track"><div class="prob-fill away" style="width:${pAway * 100}%"></div></div>
        <span class="prob-pct">${pct(pAway)}</span>
      </div>
    </div>`;
}

function teamInitials(name) {
  return name.split(/\s+/).filter(Boolean).map((w) => w[0]).join('').slice(0, 3).toUpperCase();
}

function logoImg(src, className = 'team-logo') {
  const url = src || '/static/logos/default.png';
  return `<img class="${className}" src="${url}" alt="" loading="lazy" onerror="this.onerror=null;this.src='/static/logos/default.png'" />`;
}

function renderFixtureCard(m) {
  const date = m.Date ? new Date(m.Date).toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' }) : '—';
  const home = teamMeta(m.HomeTeam);
  const away = teamMeta(m.AwayTeam);
  const homeLogo = m.home_logo || home.logo || '/static/logos/default.png';
  const awayLogo = m.away_logo || away.logo || '/static/logos/default.png';
  const stadium = m.stadium || home.stadium;
  const stadiumImg = (home.stadium_image && home.stadium_image.startsWith('/static/'))
    ? home.stadium_image
    : ((m.stadium_image && m.stadium_image.startsWith('/static/')) ? m.stadium_image : home.stadium_image || m.stadium_image);
  const score = m.pred_score || `${m.pred_home_goals ?? '–'}–${m.pred_away_goals ?? '–'}`;

  const stadiumHtml = stadiumImg
    ? `<div class="fixture-stadium"><img src="${stadiumImg}" alt="" loading="lazy" onerror="this.onerror=null;this.src='${stadiumImg.replace('.jpg','.svg')}'" /><div class="fixture-stadium-overlay"><span class="home-badge">Home · ${m.HomeTeam}</span><span class="stadium-name">${stadium}</span></div></div>`
    : `<div class="fixture-stadium fixture-stadium-plain"><div class="fixture-stadium-overlay"><span class="home-badge">Home · ${m.HomeTeam}</span><span class="stadium-name">${stadium}</span></div></div>`;

  const matchUrl = `/match?home=${encodeURIComponent(m.HomeTeam)}&away=${encodeURIComponent(m.AwayTeam)}&date=${encodeURIComponent(m.Date || '')}`;

  return `
    <a class="fixture-card fixture-link" href="${matchUrl}">
      ${stadiumHtml}
      <div class="fixture-body">
        <div class="fixture-top">
          <span class="fixture-date">${date}${m.Round ? ` · MD ${m.Round}` : ''}</span>
          <span class="pred-badge ${m.pred_ftr}">${ftrLabel(m.pred_ftr)}</span>
        </div>
        <div class="fixture-matchup">
          <div class="team-side home">
            ${logoImg(homeLogo)}
            <span class="team-name">${m.HomeTeam}</span>
          </div>
          <div class="score-center">
            <div class="pred-score">${score}</div>
            <div class="score-label">Predicted score</div>
          </div>
          <div class="team-side away">
            ${logoImg(awayLogo)}
            <span class="team-name">${m.AwayTeam}</span>
          </div>
        </div>
        ${renderProbBars(m.p_home, m.p_draw, m.p_away)}
      </div>
    </a>`;
}

function renderTrainingManifest(manifest) {
  const el = $('#training-manifest');
  if (!manifest) {
    el.innerHTML = '<p class="muted">No manifest available.</p>';
    return;
  }
  let html = `<div class="limit-banner">Training data: <strong>${manifest.train_season_count} seasons</strong>, <strong>${manifest.total_training_matches?.toLocaleString()} matches</strong> (2016–17 through 2025–26). Current squad values and net transfer spend from Transfermarkt adjust predictions for ${SEASON_LABEL}.</div>`;
  html += '<div class="table-wrap"><table class="standings-table"><thead><tr><th>Season</th><th>Matches</th><th>From</th><th>To</th></tr></thead><tbody>';
  for (const s of manifest.seasons || []) {
    html += `<tr><td>${s.label}</td><td>${s.matches}</td><td>${s.date_min || '—'}</td><td>${s.date_max || '—'}</td></tr>`;
  }
  html += '</tbody></table></div>';
  html += `<p class="muted" style="margin-top:0.75rem">Source: <a href="${manifest.data_source}" target="_blank" rel="noopener" style="color:var(--accent-2)">football-data.co.uk</a></p>`;
  el.innerHTML = html;
}

function renderMethodology(info) {
  const el = $('#methodology-info');
  if (!info) {
    el.innerHTML = '<p class="muted">No methodology info.</p>';
    return;
  }
  let html = '<div class="limit-banner">' + (info.signings_note || '') + '</div>';
  html += '<p style="margin-bottom:0.75rem"><strong>Fixtures:</strong> Official Premier League 2026/27 release (380 matches)</p>';
  html += '<p style="margin-bottom:0.75rem"><strong>Features used:</strong></p><ul style="margin-left:1.25rem;color:var(--muted);font-size:0.85rem">';
  for (const f of info.features_used) html += `<li style="margin-bottom:0.25rem">${f}</li>`;
  html += '</ul>';
  html += '<p style="margin:0.75rem 0 0.35rem"><strong>Does NOT use:</strong></p><ul style="margin-left:1.25rem;color:var(--muted);font-size:0.85rem">';
  for (const f of info.does_not_use) html += `<li style="margin-bottom:0.25rem">${f}</li>`;
  html += '</ul>';
  html += `<p class="muted" style="margin-top:0.75rem;font-size:0.82rem">${info.how_predictions_update}</p>`;
  el.innerHTML = html;
}

function renderHeroStats(report, accuracy, seasonData, seasonLabel) {
  const el = $('#hero-stats');
  const seasonAcc = seasonData.accuracy != null ? pct(seasonData.accuracy) : '—';
  el.innerHTML = `
    <div class="stat-card">
      <div class="stat-label">Training Seasons</div>
      <div class="stat-value">10</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Training Matches</div>
      <div class="stat-value">${report?.n_rows?.toLocaleString() ?? '3,800'}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">${seasonLabel} Played</div>
      <div class="stat-value">${seasonData.played_count ?? '—'}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">CV Accuracy</div>
      <div class="stat-value">${report ? pct(report.avg_accuracy) : '—'}</div>
    </div>`;
}

function renderModelMetrics(report) {
  const el = $('#model-metrics');
  if (!report) {
    el.innerHTML = '<p class="muted">No report available.</p>';
    return;
  }
  el.innerHTML = `
    <div class="metric-item"><div class="label">CV Log Loss</div><div class="value">${report.avg_log_loss.toFixed(4)}</div></div>
    <div class="metric-item"><div class="label">Features</div><div class="value">${report.n_features}</div></div>
    <div class="metric-item"><div class="label">Train Seasons</div><div class="value">${report.train_seasons?.length ?? '—'}</div></div>
    <div class="metric-item"><div class="label">Predict Season</div><div class="value">${report.predict_season ?? PREDICT_SEASON}</div></div>`;
}

function renderAccuracyBreakdown(data) {
  const el = $('#accuracy-breakdown');
  if (!data) {
    el.innerHTML = '<p class="muted">No accuracy data.</p>';
    return;
  }
  let html = `<div class="metric-item" style="margin-bottom:0.75rem"><div class="label">Last ${data.n} matches</div><div class="value">${pct(data.accuracy)}</div></div>`;
  for (const [label, acc] of Object.entries(data.by_outcome || {})) {
    html += `<div class="prob-row" style="margin-bottom:0.4rem"><span class="prob-label">${label}</span><div class="prob-track"><div class="prob-fill home" style="width:${acc * 100}%"></div></div><span class="prob-pct">${pct(acc)}</span></div>`;
  }
  el.innerHTML = html;
}

function renderStandings(rows) {
  const tbody = $('#standings-table tbody');
  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="10" class="empty-state">No standings data yet.</td></tr>';
    return;
  }
  tbody.innerHTML = rows.map((r) => {
    const meta = teamMeta(r.team);
    return `
    <tr class="pos-${r.position <= 4 ? r.position : ''}">
      <td>${r.position}</td>
      <td class="team-cell">${logoImg(meta.logo, 'team-logo-sm')}<span>${r.team}</span></td>
      <td>${r.played}</td>
      <td>${r.won}</td>
      <td>${r.drawn}</td>
      <td>${r.lost}</td>
      <td>${r.gf}</td>
      <td>${r.ga}</td>
      <td>${r.gd > 0 ? '+' : ''}${r.gd}</td>
      <td><strong>${r.points}</strong></td>
    </tr>`;
  }).join('');
}

function renderResults(matches) {
  const tbody = $('#results-table tbody');
  if (!matches.length) {
    tbody.innerHTML = '<tr><td colspan="6" class="empty-state">No played matches yet this season.</td></tr>';
    return;
  }
  tbody.innerHTML = [...matches].reverse().map((m) => {
    const date = m.Date ? new Date(m.Date).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' }) : '—';
    const ok = m.correct ? 'correct' : 'incorrect';
    return `
      <tr>
        <td>${date}</td>
        <td class="team-cell">${m.HomeTeam} vs ${m.AwayTeam}</td>
        <td>${m.FTHG}–${m.FTAG}</td>
        <td><span class="result-chip ${m.FTR}">${ftrLabel(m.FTR)}</span></td>
        <td class="${ok}"><span class="result-chip ${m.pred_ftr}">${ftrLabel(m.pred_ftr)}</span></td>
        <td class="mini-probs">H ${pct(m.p_home)} · D ${pct(m.p_draw)} · A ${pct(m.p_away)}</td>
      </tr>`;
  }).join('');
}

function setupTabs() {
  $$('.tab').forEach((btn) => {
    btn.addEventListener('click', () => {
      $$('.tab').forEach((b) => b.classList.remove('active'));
      $$('.panel').forEach((p) => p.classList.remove('active'));
      btn.classList.add('active');
      $(`#panel-${btn.dataset.tab}`).classList.add('active');
    });
  });
}

async function load() {
  try {
    const config = await fetchJSON('/api/config').catch(() => ({ predict_season: PREDICT_SEASON, season_label: SEASON_LABEL }));
    PREDICT_SEASON = config.predict_season;
    const seasonLabel = config.season_label;

    TEAMS = await fetchJSON('/api/teams').catch(() => ({}));

    const [report, accuracy, upcoming, standings, season, manifest, methodology] = await Promise.all([
      fetchJSON('/api/report').catch(() => null),
      fetchJSON('/api/accuracy/recent?n=200').catch(() => null),
      fetchJSON('/api/predictions/upcoming').catch(() => []),
      fetchJSON('/api/standings').catch(() => []),
      fetchJSON(`/api/matches/season/${PREDICT_SEASON}`).catch(() => ({ played: [], played_count: 0, accuracy: null })),
      fetchJSON('/api/training-manifest').catch(() => null),
      fetchJSON('/api/methodology').catch(() => null),
    ]);

    renderHeroStats(report, accuracy, season, seasonLabel);
    renderModelMetrics(report);
    renderAccuracyBreakdown(accuracy);
    renderTrainingManifest(manifest);
    renderMethodology(methodology);

    const next5 = upcoming.slice(0, 5);
    $('#next-fixtures').innerHTML = next5.length
      ? next5.map(renderFixtureCard).join('')
      : '<p class="empty-state">No upcoming fixtures. Re-run the pipeline to refresh.</p>';

    $('#upcoming-count').textContent = `${upcoming.length} fixtures`;
    $('#all-predictions').innerHTML = upcoming.length
      ? `<div class="limit-banner">Score predictions use a Poisson model from team scoring rates. Squad market value and net transfer spend from Transfermarkt nudge team strength for ${seasonLabel}.</div>${upcoming.map(renderFixtureCard).join('')}`
      : '<p class="empty-state">No upcoming predictions available.</p>';

    renderStandings(standings);

    if (season.accuracy != null) {
      $('#season-accuracy').textContent = `${pct(season.accuracy)} accuracy (${season.played_count} played)`;
    } else if (season.played_count === 0) {
      $('#season-accuracy').textContent = 'Season not started';
    }
    $('#season-results-label').textContent = `${seasonLabel} Season`;
    renderResults(season.played || []);
  } catch (err) {
    toast(`Failed to load data: ${err.message}`, true);
  }
}

setupTabs();
load();
