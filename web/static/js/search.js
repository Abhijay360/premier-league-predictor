/** Match search — type team names, "Arsenal vs Chelsea", or stadium. */

function matchSearchUrl(m) {
  return `/match?home=${encodeURIComponent(m.HomeTeam)}&away=${encodeURIComponent(m.AwayTeam)}&date=${encodeURIComponent(m.Date || '')}`;
}

function formatMatchDate(d) {
  if (!d) return '—';
  return new Date(d).toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' });
}

function renderSearchResult(m) {
  const played = m.played || (m.FTHG != null && m.FTAG != null);
  const score = played
    ? `${m.FTHG}–${m.FTAG}`
    : (m.pred_score || `${m.pred_home_goals ?? '–'}–${m.pred_away_goals ?? '–'}`);
  const status = played ? 'Played' : 'Upcoming';
  const md = m.Round ? ` · MD ${m.Round}` : '';
  return `
    <a class="search-result" href="${matchSearchUrl(m)}" role="option">
      <div class="search-result-main">
        <span class="search-result-teams">${m.HomeTeam} vs ${m.AwayTeam}</span>
        <span class="search-result-score">${score}</span>
      </div>
      <div class="search-result-meta muted">
        <span>${formatMatchDate(m.Date)}${md}</span>
        <span class="search-result-badge ${played ? 'played' : 'upcoming'}">${status}</span>
      </div>
    </a>`;
}

function initMatchSearch(root) {
  const input = root.querySelector('.match-search-input');
  const dropdown = root.querySelector('.match-search-dropdown');
  if (!input || !dropdown) return;

  let timer = null;
  let activeIdx = -1;

  const hide = () => {
    dropdown.classList.add('hidden');
    dropdown.innerHTML = '';
    activeIdx = -1;
    input.setAttribute('aria-expanded', 'false');
  };

  const show = (html) => {
    dropdown.innerHTML = html;
    dropdown.classList.toggle('hidden', !html);
    input.setAttribute('aria-expanded', html ? 'true' : 'false');
  };

  const runSearch = async (q) => {
    const query = q.trim();
    if (query.length < 2) {
      hide();
      return;
    }
    try {
      const res = await fetch(`/api/matches/search?q=${encodeURIComponent(query)}&limit=20`);
      if (!res.ok) throw new Error('Search failed');
      const data = await res.json();
      const matches = data.matches || [];
      if (!matches.length) {
        show('<div class="search-empty muted">No matches found</div>');
        return;
      }
      show(matches.map(renderSearchResult).join(''));
    } catch {
      show('<div class="search-empty muted">Search unavailable</div>');
    }
  };

  input.addEventListener('input', () => {
    clearTimeout(timer);
    timer = setTimeout(() => runSearch(input.value), 180);
  });

  input.addEventListener('keydown', (e) => {
    const items = dropdown.querySelectorAll('.search-result');
    if (e.key === 'Escape') {
      hide();
      input.blur();
      return;
    }
    if (!items.length) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      activeIdx = Math.min(activeIdx + 1, items.length - 1);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      activeIdx = Math.max(activeIdx - 1, 0);
    } else if (e.key === 'Enter' && activeIdx >= 0) {
      e.preventDefault();
      items[activeIdx].click();
      return;
    } else {
      return;
    }
    items.forEach((el, i) => el.classList.toggle('active', i === activeIdx));
    items[activeIdx]?.scrollIntoView({ block: 'nearest' });
  });

  document.addEventListener('click', (e) => {
    if (!root.contains(e.target)) hide();
  });

  input.addEventListener('focus', () => {
    if (input.value.trim().length >= 2) runSearch(input.value);
  });
}

document.querySelectorAll('[data-match-search]').forEach(initMatchSearch);
