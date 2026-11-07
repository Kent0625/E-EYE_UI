// Only explicitly labelled eyes and signed decimal values become editable drafts.
// Ambiguous rows remain in the transcription for the operator to enter manually.
export function parseReceiptDraft(text) {
  const readings = { OD: [], OS: [] };
  let eye = null;
  let ignoreSection = false;
  let summaryNext = false;
  for (const raw of String(text).split(/\r?\n/)) {
    const line = raw.replace(/[−–]/g, '-').trim();
    if (/^[-_=─━.\s]{3,}$/.test(line) && /[-_=─━]/.test(line)) {
      summaryNext = true;
      continue;
    }
    if (/\b(KER|KERATOMETRY|K1|K2|R1|R2)\b/i.test(line)) ignoreSection = true;
    if (/\b(REF|REFRACTION|SPH|SPHERE)\b/i.test(line)) ignoreSection = false;
    const right = /(?:<\s*R\s*>|\bOD\b|\bRIGHT\b)/i.test(line);
    const left = /(?:<\s*L\s*>|\bOS\b|\bLEFT\b)/i.test(line);
    if (right && left) { eye = null; continue; }
    if (right || left) {
      eye = right ? 'OD' : 'OS';
      summaryNext = false;
      if (/\bmm\b.*\bD\b/i.test(line)) ignoreSection = true;
    }
    else if (/\b(SPH|SPHERE)\b.*\b(CYL|CYLINDER)\b/i.test(line)) {
      // An unreadable new eye label must not inherit the preceding eye's rows.
      const label = line.split(/\b(?:SPH|SPHERE)\b/i)[0].trim();
      if (label) eye = null;
    }
    if (!eye || ignoreSection) continue;
    const row = line.replace(/<\s*[RL]\s*>|\b(OD|OS|RIGHT|LEFT|AVG|AVE|AVERAGE)\b/gi, '').replace(/^[*#:\s]+/, '').trim()
      .replace(/([+-])\s+(?=\d)/g, '$1');
    const match = row.match(/^([+-]\d{1,2}\.\d{2}|0\.00)\s+([+-]\d{1,2}\.\d{2}|0\.00)(?:\s+(\d{1,3})(?:\s+\d{1,2}\.\d)?)?\s*$/);
    if (!match) continue;
    const sphere = Number(match[1]), cylinder = Number(match[2]);
    const axis = match[3] === undefined ? null : Number(match[3]);
    if (Math.abs(sphere) > 20 || Math.abs(cylinder) > 20 || (axis !== null && axis > 180)) continue;
    readings[eye].push({ sphere_D: sphere, cylinder_D: cylinder, axis_deg: axis,
      printedAverage: summaryNext || /\b(AVG|AVE|AVERAGE)\b/i.test(line) });
    summaryNext = false;
  }
  const eyes = {};
  for (const key of ['OD', 'OS']) {
    const averages = readings[key].filter(row => row.printedAverage);
    if (averages.length === 1) {
      const { printedAverage, ...values } = averages[0];
      eyes[key] = { ...values, method: 'printed_average' };
    }
  }
  return { eyes, requiresConfirmation: true };
}
