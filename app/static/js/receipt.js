import { parseReceiptDraft } from './receipt-parser.js';

const form = document.getElementById('form-ground-truth');
if (form) initializeReceiptForm(form);

function initializeReceiptForm(form) {
  const sessionId = form.dataset.sessionId;
  const participantCode = form.dataset.participantCode;
  const endpoint = `/api/sessions/${encodeURIComponent(sessionId)}`;
  const field = id => document.getElementById(id);
  const preview = field('receipt-preview');
  const select = field('receipt-select');
  const method = field('reference-method');
  const confirm = field('gt-confirmed');
  const save = field('btn-save-ground-truth');
  let savedEyes = JSON.parse(field('receipt-saved-eyes').textContent);
  let receipts = [], rotation = 0, originalImage = null;
  let ocrText = '', ocrDraft = {}, busy = false;

  function message(id, text, error = false) {
    const element = field(id);
    element.textContent = text;
    element.dataset.error = String(error);
  }

  function resetConfirmation() {
    confirm.checked = false;
    save.disabled = true;
    field('gt-confirm-hint').textContent = 'Confirm the values to enable saving.';
  }

  function setBusy(value, reason = '') {
    busy = value;
    form.querySelectorAll('button, input, select').forEach(control => { control.disabled = value; });
    save.disabled = value || !confirm.checked;
    field('gt-confirm-hint').textContent = value ? reason :
      (confirm.checked ? 'The confirmed values will be linked to this participant.' : 'Confirm the values to enable saving.');
  }

  async function fetchJson(path, options = {}) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 30000);
    try {
      const response = await fetch(path, { ...options, signal: controller.signal });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || 'The device could not save this change. Retry.');
      return result;
    } catch (error) {
      if (error instanceof TypeError || error.name === 'AbortError') {
        throw new Error('Connection lost. Reconnect to the Pi and reopen the record to check whether the change was saved.');
      }
      throw error;
    } finally { clearTimeout(timer); }
  }

  function updateMethod() {
    const three = method.value === 'three_readings';
    form.querySelectorAll('.receipt-three-readings').forEach(element => { element.hidden = !three; });
    form.querySelectorAll('.receipt-summary-inputs').forEach(element => { element.hidden = three; });
    resetConfirmation();
  }

  function clearValues() {
    form.querySelectorAll('input[type="number"]').forEach(input => { input.value = ''; });
    ocrText = '';
    ocrDraft = {};
    field('receipt-transcription').hidden = true;
    resetConfirmation();
  }

  function fillEye(key, values) {
    const prefix = key.toLowerCase();
    for (const [name, suffix] of [['sphere_D', 'sphere'], ['cylinder_D', 'cylinder'], ['axis_deg', 'axis']]) {
      field(`gt-${prefix}-${suffix}`).value = values[name] ?? '';
    }
    (values.readings || []).forEach((reading, index) => {
      field(`gt-${prefix}-${index + 1}-sphere`).value = reading.sphere_D ?? '';
      field(`gt-${prefix}-${index + 1}-cylinder`).value = reading.cylinder_D ?? '';
    });
  }

  async function showReceipt(id, clear = true) {
    select.value = id || '';
    rotation = 0;
    originalImage = null;
    preview.hidden = true;
    field('receipt-photo-actions').hidden = true;
    if (clear) clearValues();
    const receipt = receipts.find(item => item.id === id);
    if (!receipt) {
      method.value = 'manual';
      updateMethod();
      message('receipt-status', 'No receipt selected. Enter the reference manually or attach a photo.');
      return;
    }
    try {
      const image = new Image();
      image.src = receipt.image_url;
      await image.decode();
      originalImage = image;
      preview.src = image.src;
      preview.hidden = false;
      field('receipt-photo-actions').hidden = false;
      message('receipt-status', `Receipt saved with participant ${participantCode}. Read the numbers or enter them below.`);
      if (clear) {
        const matching = Object.entries(savedEyes).filter(([, eye]) => eye.ground_truth?.receipt_id === id);
        const methods = new Set(matching.map(([, eye]) => eye.ground_truth.reference_method));
        method.value = methods.size === 1 ? [...methods][0] : 'printed_average';
        if (methods.size === 1) matching.forEach(([key, eye]) => fillEye(key, eye.ground_truth));
        updateMethod();
      }
    } catch {
      message('receipt-status', 'Receipt photo could not load. Reconnect to the Pi and select it again.', true);
    }
  }

  async function loadReceipts(selectedId) {
    const response = await fetchJson(`${endpoint}/receipts`);
    receipts = response.receipts;
    select.replaceChildren(new Option('No photo selected', ''));
    receipts.forEach((receipt, index) => select.add(new Option(`Receipt ${index + 1} · ${receipt.created_at.slice(0, 16).replace('T', ' ')} UTC`, receipt.id)));
    await showReceipt(selectedId || '', false);
  }

  function canvasForReceipt() {
    const canvas = document.createElement('canvas');
    const sideways = rotation % 180 !== 0;
    const scale = Math.min(1, 2200 / Math.max(originalImage.naturalWidth, originalImage.naturalHeight));
    const width = Math.round(originalImage.naturalWidth * scale), height = Math.round(originalImage.naturalHeight * scale);
    canvas.width = sideways ? height : width;
    canvas.height = sideways ? width : height;
    const context = canvas.getContext('2d');
    context.fillStyle = 'white';
    context.fillRect(0, 0, canvas.width, canvas.height);
    context.translate(canvas.width / 2, canvas.height / 2);
    context.rotate(rotation * Math.PI / 180);
    context.drawImage(originalImage, -width / 2, -height / 2, width, height);
    return canvas;
  }

  async function uploadReceipt(file) {
    if (!file || busy) return;
    resetConfirmation();
    if (file.size > 12 * 1024 * 1024 || !['image/jpeg', 'image/png'].includes(file.type)) {
      message('receipt-status', 'Choose a JPEG or PNG photo under 12 MB.', true);
      return;
    }
    setBusy(true, 'Wait for the receipt upload to finish.');
    message('receipt-status', 'Saving receipt to this participant record…');
    try {
      const data = new FormData();
      data.append('image', file);
      data.append('participant_code', participantCode);
      const receipt = await fetchJson(`${endpoint}/receipts`, { method: 'POST', body: data });
      await loadReceipts(receipt.id);
      clearValues();
      method.value = 'printed_average';
      updateMethod();
    } catch (error) { message('receipt-status', error.message, true); }
    finally { setBusy(false); }
  }

  for (const source of ['camera', 'file']) {
    field(`receipt-${source}-button`).addEventListener('click', () => field(`receipt-${source}-input`).click());
    field(`receipt-${source}-input`).addEventListener('change', event => {
      uploadReceipt(event.target.files[0]);
      event.target.value = '';
    });
  }
  select.addEventListener('change', async () => {
    setBusy(true, 'Loading the selected receipt.');
    await showReceipt(select.value);
    setBusy(false);
  });
  method.addEventListener('change', updateMethod);
  form.querySelectorAll('input[type="number"]').forEach(input => input.addEventListener('input', resetConfirmation));
  confirm.addEventListener('change', () => {
    save.disabled = busy || !confirm.checked;
    field('gt-confirm-hint').textContent = confirm.checked ?
      'The confirmed values will be linked to this participant.' : 'Confirm the values to enable saving.';
  });
  field('receipt-rotate-button').addEventListener('click', () => {
    if (!originalImage) return;
    rotation = (rotation + 90) % 360;
    preview.src = canvasForReceipt().toDataURL('image/jpeg', 0.9);
    resetConfirmation();
  });

  field('receipt-read-button').addEventListener('click', async () => {
    if (!originalImage || busy) return;
    setBusy(true, 'Wait for receipt reading to finish, then check the values.');
    resetConfirmation();
    message('receipt-status', 'Loading the local receipt reader…');
    let timedOut = false, worker = null, timer;
    const timeout = new Promise((_, reject) => {
      timer = setTimeout(() => { timedOut = true; reject(new Error('Receipt reading timed out. Enter the numbers manually or retry.')); }, 90000);
    });
    try {
      if (!window.Tesseract) throw new Error('Local receipt reader could not load. Reload the page or enter the values manually.');
      const recognize = async () => {
        const createdWorker = await window.Tesseract.createWorker('eng', 1, {
        workerPath: '/static/vendor/ocr/worker.min.js',
        corePath: '/static/vendor/ocr/tesseract-core-lstm.wasm.js',
        langPath: '/static/vendor/ocr', workerBlobURL: false, gzip: true,
        logger: event => {
          if (!timedOut && event.status === 'recognizing text') {
            message('receipt-status', `Reading receipt text: ${Math.round(event.progress * 100)}%.`);
          }
        },
        });
        if (timedOut) { await createdWorker.terminate(); throw new Error('Receipt reading timed out.'); }
        worker = createdWorker;
        await worker.setParameters({ tessedit_pageseg_mode: '6' });
        return worker.recognize(rotation === 0 ? originalImage.src : canvasForReceipt().toDataURL('image/png'));
      };
      const result = await Promise.race([recognize(), timeout]);
      clearValues();
      ocrText = result.data.text;
      const parsed = parseReceiptDraft(ocrText);
      ocrDraft = { ...parsed, rotation_degrees: rotation };
      field('receipt-ocr-text').textContent = ocrText;
      field('receipt-transcription').hidden = false;
      const methods = new Set(Object.values(parsed.eyes).map(eye => eye.method));
      if (methods.size === 1) {
        method.value = [...methods][0];
        Object.entries(parsed.eyes).forEach(([key, values]) => fillEye(key, values));
        message('receipt-status', 'Unconfirmed draft filled. Check every eye label, sign and value against the photo.');
      } else {
        method.value = 'manual';
        message('receipt-status', 'The receipt rows or reference method are ambiguous. Read the photo and enter the values manually.', true);
      }
      updateMethod();
    } catch (error) {
      message('receipt-status', timedOut ? error.message : 'Receipt text could not be read. Rotate or retake the photo, retry, or enter the numbers manually.', true);
    } finally {
      clearTimeout(timer);
      if (worker) await worker.terminate();
      setBusy(false);
    }
  });

  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (busy || !confirm.checked) return;
    const eyes = {};
    for (const key of ['OD', 'OS']) {
      const prefix = key.toLowerCase();
      const values = { expected_revision: Number(form.querySelector(`[data-eye="${key}"]`).dataset.revision) };
      if (method.value === 'three_readings') {
        values.readings = [1, 2, 3].map(number => ({
          sphere_D: field(`gt-${prefix}-${number}-sphere`).value,
          cylinder_D: field(`gt-${prefix}-${number}-cylinder`).value,
        }));
        if (values.readings.every(reading => reading.sphere_D === '' && reading.cylinder_D === '')) continue;
      } else {
        values.sphere_D = field(`gt-${prefix}-sphere`).value;
        values.cylinder_D = field(`gt-${prefix}-cylinder`).value;
        if (values.sphere_D === '' && values.cylinder_D === '') continue;
      }
      values.axis_deg = field(`gt-${prefix}-axis`).value;
      eyes[key] = values;
    }
    setBusy(true, 'Saving the confirmed reference.');
    message('gt-save-feedback', 'Saving confirmed ground truth…');
    try {
      const session = await fetchJson(`${endpoint}/confirmed-ground-truth`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ confirmed: true, participant_code: participantCode,
          reference_method: method.value, receipt_id: select.value || null,
          eyes, ocr_text: ocrText, ocr_draft: ocrDraft }),
      });
      savedEyes = session.eyes;
      for (const [key, eye] of Object.entries(savedEyes)) {
        if (!eye.ground_truth) continue;
        const truth = eye.ground_truth;
        form.querySelector(`[data-eye="${key}"]`).dataset.revision = truth.revision || 0;
        const sign = truth.se_D < 0 ? '−' : truth.se_D > 0 ? '+' : '';
        field(`gt-${key.toLowerCase()}-se-display`).textContent = `Saved reference SE: ${sign}${Math.abs(truth.se_D).toFixed(2)} D`;
      }
      message('gt-save-feedback', `Confirmed ground truth saved for ${participantCode}.`);
      resetConfirmation();
    } catch (error) { message('gt-save-feedback', error.message, true); }
    finally { setBusy(false); }
  });

  const existing = Object.values(savedEyes).map(eye => eye.ground_truth).filter(Boolean);
  const ids = new Set(existing.map(truth => truth.receipt_id).filter(Boolean));
  const methods = new Set(existing.map(truth => truth.reference_method).filter(Boolean));
  if (methods.size === 1) method.value = [...methods][0];
  Object.entries(savedEyes).forEach(([key, eye]) => { if (eye.ground_truth) fillEye(key, eye.ground_truth); });
  updateMethod();
  setBusy(true, 'Loading saved receipts.');
  loadReceipts(ids.size === 1 ? [...ids][0] : '').catch(error => message('receipt-status', error.message, true))
    .finally(() => setBusy(false));
}
