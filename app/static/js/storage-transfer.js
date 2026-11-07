import { getJson, postJson } from './api.js';

const section = document.getElementById('storage-transfer');
if (section) {
  const label = document.getElementById('storage-device-label');
  const prepare = document.getElementById('storage-prepare');
  const download = document.getElementById('storage-download');
  const feedback = document.getElementById('storage-feedback');
  const locations = document.getElementById('storage-locations');
  const endpoint = `/api/sessions/${encodeURIComponent(section.dataset.sessionId)}/transfers`;
  let deviceId;
  try {
    deviceId = localStorage.getItem('eeye_storage_device_id');
    if (!deviceId) {
      deviceId = Array.from(crypto.getRandomValues(new Uint8Array(16)), n => n.toString(16).padStart(2, '0')).join('');
      localStorage.setItem('eeye_storage_device_id', deviceId);
    }
    label.value = localStorage.getItem('eeye_storage_device_label') || '';
  } catch {
    prepare.disabled = true;
    feedback.textContent = 'Device storage settings are unavailable. Allow site storage, then reload.';
  }

  async function refreshLocations() {
    const result = await getJson(endpoint);
    locations.replaceChildren();
    const items = result.transfers || [];
    for (const transfer of items) {
      if (!['verified', 'released'].includes(transfer.state)) continue;
      const row = document.createElement('li');
      row.textContent = `${transfer.device_label}: ${transfer.state === 'released' ? 'saved copy checked; transferred files removed from Pi' : 'saved copy checked; Pi copy retained'}.`;
      locations.append(row);
    }
    locations.hidden = !locations.children.length;
  }

  prepare.addEventListener('click', async () => {
    const deviceLabel = label.value.trim();
    if (!deviceLabel) {
      feedback.textContent = 'Name the phone or computer where this session will be saved.';
      label.focus();
      return;
    }
    prepare.disabled = true;
    download.hidden = true;
    feedback.dataset.error = 'false';
    feedback.textContent = 'Preparing the session archive. The Pi copy is retained.';
    try {
      localStorage.setItem('eeye_storage_device_label', deviceLabel);
      const transfer = await postJson(endpoint, { device_id: deviceId, device_label: deviceLabel });
      const destination = new URL(transfer.download_url, location.origin);
      if (destination.origin !== location.origin || !/^\/api\/transfers\/[a-f0-9]{32}\/archive$/.test(destination.pathname)) {
        throw new Error('The device returned an invalid download address. The Pi copy is retained.');
      }
      download.href = destination.href;
      download.hidden = false;
      feedback.textContent = 'Archive ready. Choose “Save to this device” and select a local destination.';
      await refreshLocations();
    } catch (error) {
      feedback.dataset.error = 'true';
      feedback.textContent = `${error.message} The Pi copy has been kept.`;
    } finally {
      prepare.disabled = false;
    }
  });
  window.addEventListener('focus', () => refreshLocations().catch(() => {}));
  refreshLocations().catch(() => {
    feedback.textContent = 'Saved-copy status could not load. Check the Pi connection and reload. Files have not been removed.';
  });
}
