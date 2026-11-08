import { t } from './i18n.js';

const root = document.getElementById('processing-session');
if (root) {
  const id = encodeURIComponent(root.dataset.sessionId);
  const eye = new URLSearchParams(location.search).get('eye') === 'OS' ? 'OS' : 'OD';
  const message = document.getElementById('processing-message');
  const elapsed = document.getElementById('processing-elapsed');
  const recovery = document.getElementById('processing-recovery');
  const spinner = document.querySelector('.processing-spinner-wrapper');
  let source, timer, observedAt = 0, seconds = null, lastEvent = null;
  const text = (key, fallback) => { const value = t(key); return value === key ? fallback : value; };
  document.getElementById('processing-eye').textContent = eye === 'OD' ? 'Right eye (OD)' : 'Left eye (OS)';
  document.getElementById('btn-retake').href = `/screen/${id}/${eye}`;
  document.getElementById('btn-skip-eye').href = `/screen/${id}/result`;

  function renderTime() {
    elapsed.textContent = seconds === null ? '—' : `${(seconds + (timer ? (performance.now()-observedAt)/1000 : 0)).toFixed(1)} s`;
  }
  function stopTimer() {
    if (timer) {
      clearInterval(timer);
      seconds += (performance.now()-observedAt)/1000;
    }
    timer = null;
    renderTime();
  }
  function showPhases(phases = {}) {
    for (const phase of ['saving', 'quality', 'prediction']) {
      const state = ['waiting','running','complete','unavailable','failed'].includes(phases[phase]) ? phases[phase] : 'waiting';
      const row = document.getElementById(`phase-${phase}`);
      row.dataset.state = state;
      row.querySelector('.phase-state').textContent = text(`processing.state.${state}`, state);
    }
  }
  function connect() {
    source?.close();
    stopTimer();
    recovery.hidden = true;
    document.getElementById('processing-view').hidden = false;
    document.getElementById('retake-view').hidden = true;
    spinner.hidden = false;
    message.textContent = text('processing.connecting', 'Checking the saved capture…');
    source = new EventSource(`/api/sessions/${id}/events?eye=${eye}`);
    source.onmessage = event => {
      let data;
      try { data = JSON.parse(event.data); }
      catch { disconnect(); return; }
      lastEvent = data;
      message.textContent = data.label || text('processing.connecting', 'Checking the saved capture…');
      stopTimer();
      seconds = Number.isFinite(data.processing_elapsed_s) ? data.processing_elapsed_s : null;
      observedAt = performance.now();
      if (!data.done && seconds !== null) timer = setInterval(renderTime, 1000);
      renderTime();
      showPhases(data.phases);
      if (!data.done) return;
      source.close();
      spinner.hidden = true;
      if (data.status === 'retake_needed') {
        const title = document.getElementById('retake-title');
        const qualityFailed = data.reason === 'few_valid_frames';
        title.dataset.i18n = qualityFailed ? 'retake.title' : 'retake.reviewTitle';
        title.textContent = text(title.dataset.i18n, qualityFailed ? title.dataset.qualityTitle : 'This capture needs attention');
        document.getElementById('retake-quality-hint').hidden = !qualityFailed;
        document.getElementById('processing-view').hidden = true;
        document.getElementById('retake-view').hidden = false;
        document.getElementById('retake-message').textContent = data.label || '';
      } else {
        location.assign(eye === 'OD' ? `/screen/${id}/OS` : `/screen/${id}/result`);
      }
    };
    source.onerror = disconnect;
  }
  function disconnect() {
    source?.close();
    stopTimer();
    spinner.hidden = true;
    recovery.hidden = false;
    const warning = text('processing.disconnected', 'Connection lost. Reconnect to the Pi, then check again. A disconnection does not cancel the capture.');
    message.textContent = warning;
    document.getElementById('processing-recovery-message').textContent = warning;
  }
  document.getElementById('processing-retry').addEventListener('click', connect);
  document.addEventListener('eeye:languagechange', () => { if (lastEvent) showPhases(lastEvent.phases); });
  window.addEventListener('pagehide', () => { source?.close(); stopTimer(); });
  window.addEventListener('pageshow', event => { if (event.persisted) connect(); });
  connect();
}
