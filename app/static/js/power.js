import { getJson, postJson } from './api.js';
import { t } from './i18n.js';

const button = document.getElementById('btn-shutdown');
if (button) {
  const dialog = document.getElementById('shutdown-dialog');
  const confirm = document.getElementById('btn-confirm-shutdown');
  const cancel = document.getElementById('btn-cancel-shutdown');
  const hint = document.getElementById('shutdown-hint');
  const message = (key, fallback) => { const value = t(key); return value === key ? fallback : value; };
  let submitting = false;
  function requested() {
    button.disabled = true;
    hint.removeAttribute('data-i18n');
    hint.textContent = message('power.requested', 'Shutdown requested. Keep power connected until the Raspberry Pi finishes shutting down.');
  }
  getJson('/api/device/power').then(state => {
    if (state.pending && !state.uncertain) requested();
    else button.disabled = !state.available;
    if (state.uncertain) {
      hint.removeAttribute('data-i18n');
      hint.textContent = message('power.failed', 'Shutdown was not confirmed. Check the Pi before retrying.');
    }
    if (state.available && !state.pending) {
      hint.dataset.i18n = 'power.ready';
      hint.textContent = message('power.ready', 'Finish all recordings and downloads before shutting down.');
    }
  }).catch(() => { button.disabled = true; });
  button.addEventListener('click', () => {
    if (!button.disabled) { dialog.showModal(); cancel.focus(); }
  });
  cancel.addEventListener('click', () => { if (!submitting) dialog.close(); });
  dialog.addEventListener('cancel', event => { if (submitting) event.preventDefault(); });
  confirm.addEventListener('click', async () => {
    if (submitting) return;
    submitting = true;
    confirm.disabled = cancel.disabled = true;
    try {
      await postJson('/api/device/shutdown', { confirmed: true });
      requested();
      dialog.close();
    } catch (error) {
      hint.removeAttribute('data-i18n');
      hint.textContent = error instanceof TypeError ? message('power.failed', 'Shutdown was not confirmed. Check the Pi before retrying.') : error.message || message('power.failed', 'Shutdown was not confirmed. Check the Pi before retrying.');
      dialog.close();
    } finally {
      submitting = false;
      confirm.disabled = cancel.disabled = false;
    }
  });
}
