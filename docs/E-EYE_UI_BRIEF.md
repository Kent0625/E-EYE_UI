# E-Eye Results UI: Build Brief

Audience: the coding agent in Google Antigravity. Read this whole file before doing anything.
Owner: Kent (E-Eye capstone, USTP CITC, BS Data Science).
Status: v1, 19 Oct 2026.

---

## 0. How to work (agent instructions)

1. **Plan first.** Do not write code until you have produced an Implementation Plan artifact covering the phases in section 16. Stop and wait for the owner's approval.
2. **Work in phases.** Finish one phase, verify it against its acceptance checks, then report. Do not start the next phase until told.
3. **Do not guess.** Anything marked `OPEN` in section 18 is a question for the owner. Ask, don't invent an answer.
4. **Verify visually.** After each UI phase, open the page in the browser tool at the five viewports in section 8 and attach screenshots to your report.
5. **Reference material** lives in `docs/reference/`: eight Base44 screenshots of the first prototype and the manuscript excerpt. Look at the screenshots before designing.

---

## 1. Mission and non-negotiables

Build the operator-facing web UI for **E-Eye**, a low-cost eccentric photorefraction screening device. The UI is served by a Flask app on a Raspberry Pi 4 (4 GB). The operator joins the Pi's own WiFi hotspot and opens `http://192.168.4.1` on a phone, tablet, or laptop.

The UI must:

- **Work fully offline.** No internet at any point. Zero requests to external hosts: no CDN, no Google Fonts, no analytics, no remote icons, no remote images.
- **Be a screening tool, not a diagnostic tool.** It shows what the model outputs and a referral recommendation. Nothing else.
- **Be usable by a non-specialist** (barangay health worker, community health aide) in the field, one-handed on a phone.
- **Be light.** The Pi also runs camera capture and model inference. Keep the page small and the JS simple.
- **Contain no LLM or AI calls.** All text comes from templates and the copy deck in section 10. The app is deterministic.

Out of scope: user accounts, login, cloud sync, sharing or sending results off the device, push notifications, payments, diagnosis or prognosis text, any pediatric flow.

---

## 2. Skills, tools and MCP to use

**Required**

| Item | What to do |
|---|---|
| `no-ai-slop` skill | Provided at `.agent/skills/no-ai-slop/SKILL.md`. Load it before designing, before writing any copy, and again before the final review. Its rules override your defaults. |
| A frontend design skill | If your Antigravity setup has one (for example a `frontend-design` skill), load it for typography and layout decisions. Its output must still pass `no-ai-slop`. |
| Browser tool | Use it to load the running app, resize to each viewport, and take screenshots. Also use it to confirm no external network requests. |

**Optional**

- A Figma or design MCP is allowed for dev-time reference only. The app must not depend on it.

**Rules for any tool or MCP**

- Tools are for development only. Nothing in the shipped app may call out to the internet.
- Do not install a package that fetches assets at runtime. Fonts and icons are copied into the repo.
- If a skill or tool named here is not available in this environment, say so in your plan and fall back to the rules in section 15. Do not silently skip it.

---

## 3. Facts from the manuscript (source of truth)

These come from the E-Eye manuscript. Do not change them.

**Device and capture**

- Raspberry Pi 4 Model B (4 GB), Pi Camera Module 3 NoIR, one 850 nm IR LED, VL53L0X Time-of-Flight (ToF) distance sensor.
- Working distance: **10.0 to 15.0 cm**, measured by the ToF sensor (accuracy about ±3%). The backend applies the sensor-to-camera offset; the UI receives the corrected value.
- Recording: **5 seconds per eye**. Each eye is one instance.
- Preprocessing keeps **T = 10** quality-filtered frames per instance. Frames with no detectable pupil or too much blur are dropped.
- Pre-session check before each participant: a brief 5-second test capture confirming (1) the pupil crescent is visible, (2) the ToF is reporting plausible values, (3) image brightness is in the calibrated range (mean pupil intensity 128 to 200 on 8-bit grayscale).

**Model outputs (per eye)**

- Sphere (D) and cylindrical magnitude (D). No cylinder axis.
- The UI displays **spherical equivalent (SE) = sphere + cylinder / 2**, computed from those two values.

**Referral rule**

- SE from **−0.50 D to +0.50 D** (inclusive) = emmetropic range = negative screen = **NO REFERRAL NEEDED**.
- SE outside that range = **REFERRAL RECOMMENDED**.
- The banner is **binary**. No "low / moderate / high risk" tiers.
- For a two-eye result, refer if **either** eye is outside the range, and say which eye.

**Condition labels** (examples from the manuscript: "Myopia Mild", "Hyperopia", "Near-Emmetropia")

- Myopia severity by SE: mild −0.50 to −3.00 D, moderate −3.00 to −6.00 D, high below −6.00 D.
- Hyperopia: SE above +0.50 D. The manuscript defines no hyperopia severity bands, so show "Hyperopia" with no severity. `OPEN` Q3.
- Near-Emmetropia: SE within ±0.50 D.

**What the result screen must show (Section 3.2.5), per eye**

1. Pupil image thumbnail
2. Estimated SE in diopters
3. Condition label
4. Cylindrical magnitude
5. Referral banner with a plain-language explanation

**Must not show:** prognoses, progression forecasts, diagnostic conclusions (for example "anisometropia"), or a confidence percentage. The model produces no calibrated confidence, so a confidence bar would be invented data.

**Language and privacy**

- English and Filipino, switchable.
- Participants are **adults, 18 and above**. Participant identity is an **anonymized code**. No names. No age field.
- Written consent must be confirmed **before** any recording starts.
- All data stays on the Pi. Nothing leaves the device.

**Interface feasibility test in the manuscript:** 100% successful local-IP connection and correct referral banner rendering across 10 independent connections. Build so this passes.

---

## 4. Audit of the Base44 prototype

Screens reviewed: Connect, Dashboard, History, Settings, Screening Result (phone width and laptop width).

**Keep**

- Teal brand colour, white rounded cards on a light grey page.
- Side-by-side OD / OS cards.
- Bottom tab bar on phones.
- Search box and filter chips in History.
- Screening-only disclaimer at the bottom of results.
- The Settings idea of showing device name, connection, and IP.

**Change**

| Prototype | Problem | Replace with |
|---|---|---|
| Patient name, age 10, names in History | Manuscript: adults only, anonymized codes | Participant code only, for example `EE-261019-001`. No name, no age. |
| "Moderate risk" / "Low risk" | Manuscript referral is binary | REFERRAL RECOMMENDED / NO REFERRAL NEEDED |
| Summary text says "exhibits anisometropia" | Diagnostic claim | Template text from section 10 |
| Confidence bars (87%, 84%) | No such model output | Quality line: "10 of 10 frames used" |
| Blurred circle placeholders | Not real data | Real pupil thumbnail from the device |
| Only SE shown | Cylinder required | SE large, cylinder smaller beneath |
| Connect page "Searching for devices..." and a device list | A web page cannot scan WiFi. If the page loaded, the operator is already connected. | Device status screen (section 7.1) |
| Dashboard and Screening Result are nearly the same | Duplicate | One Result screen |
| Share icon on Result | Data must not leave the device | Remove. Offer "Save as PDF" only if Phase 5 is approved. |
| Log Out | No accounts | Remove |
| "Help and Support", "About" as empty rows | Filler | Keep "About" and "Disclaimer" with real content only |
| Content locked to a narrow centred column on laptop, bottom nav clipped, header curve overlapping | Not responsive | Layout in section 8 |
| No capture screen | The core of the device is missing | Section 7.3 and 7.4 |
| Footer "© 2024 All rights reserved", "Offline Mode Available" chip | Filler | Version string only. Show a real status line instead. |

**Remove from the visual language:** the pulsing radar rings on the Connect screen. They suggest scanning that does not happen.

---

## 5. Users and contexts

- **Operator:** non-specialist health worker. Holds a phone or tablet in one hand while positioning a participant. May have gloves or damp hands. Bright indoor or outdoor-adjacent light. May read Filipino more easily than English.
- **Researcher (the capstone team):** uses a laptop to review sessions and, during data collection, record autorefractor ground truth. See Research mode in 7.7.
- **Participant:** never touches the UI.

Design for the operator first. Researcher features sit behind Settings.

---

## 6. Information architecture and flow

Primary navigation, four items:

1. **Home** (device status and pre-session check)
2. **Screen** (the screening flow)
3. **History**
4. **Settings**

Screening flow:

```
Home ──> New Screening ──> Align & Record (OD) ──> Processing
              │                                        │
              │                          Retake? <─────┤
              │                                        ▼
              └──────────────────> Align & Record (OS) ──> Processing ──> Result
```

- Right eye (OD) first, then left eye (OS).
- If one eye fails quality checks, the operator can retake that eye, or finish with a single-eye result clearly labelled "Left eye not recorded".
- Result is saved automatically to local storage when processing finishes.

---

## 7. Screen specifications

### 7.1 Home

Purpose: confirm the device is ready, then start.

- Header: "E-Eye" and subtitle "Refractive error screening".
- **Device status card**, all values real, read from `/api/status`:
  - Camera: OK / not detected
  - Distance sensor: OK / not detected
  - IR LED: OK / not responding
  - Model: loaded / not loaded
  - Storage free (GB)
  - Device clock: set / not set (see 11.3)
- **Pre-session check** button. Runs a 5-second test capture and shows three checks as pass/fail rows: crescent visible (operator confirms with Yes/No after seeing the frame), distance readings plausible (auto), brightness in range (auto).
- Primary button: **Start screening**. Disabled with a reason shown if camera, sensor, or model is not OK.
- A short, static 3-step "How to connect" note is allowed on this screen only when the device is not reachable. That state is shown by the client when `/api/status` fails to respond (a "Can't reach the device" banner with: 1. join the E-Eye WiFi, 2. open 192.168.4.1, 3. retry).

### 7.2 New Screening

- **Participant code**: auto-generated, editable, format `EE-YYMMDD-NNN`. Show a one-line note "Do not enter names."
- **Two required checkboxes**, both must be ticked before Continue is enabled:
  - "Participant is 18 or older."
  - "Written consent is signed and on file."
- Optional: site/location text field (short, free text, for the session log).
- Button: **Continue**.

### 7.3 Align and Record

The most important screen. Shown once per eye. Title: "Right eye (OD)" or "Left eye (OS)".

- **Live preview** of the camera (MJPEG stream via `<img>`). If the stream is unavailable, show a clear "Preview unavailable" state and a Retry button.
- **Distance meter**: large number in cm (one decimal), plus a horizontal gauge from 5 to 20 cm with the 10 to 15 cm band marked. States, each with colour **and** icon **and** text:
  - Too close ("Move back")
  - Good ("Distance OK")
  - Too far ("Move closer")
  - No reading ("No distance reading")
- **Record button** ("Record 5 seconds"): enabled only after the distance has stayed in the 10 to 15 cm band for 1 continuous second (a proposal, `OPEN` Q5). When disabled, show why.
- During recording: a countdown ring (5 to 0) and the text "Hold still". Disable all other controls. If distance leaves the band during recording, the backend flags it and the UI shows "Distance changed. Retake" at the end.
- Fixation reminder under the preview: "Ask the participant to look at the target."
- Layout: phone = preview on top, meter below, sticky Record button at the bottom. Tablet and laptop = preview left, meter and controls right.

### 7.4 Processing

- Shows real steps from the backend, ticked as they finish: Extracting frames, Checking frame quality, Computing features, Estimating refraction.
- Use an indeterminate spinner. **Do not show a percentage or progress bar unless the backend reports real progress.**
- On finish: go to the next eye's Align and Record, or to Result after the second eye.
- **Retake state** if fewer than 10 valid frames pass quality filtering (`OPEN` Q4): "Not enough clear frames. Retake this eye." Lists likely causes in plain words (blink, movement, wrong distance). Buttons: Retake, and Skip this eye.

### 7.5 Result

Order of content, top to bottom (phone):

1. **Referral banner**, full width, first thing visible.
   - REFERRAL RECOMMENDED: amber, warning icon, text, and the eye(s) outside range.
   - NO REFERRAL NEEDED: green, check icon, text.
2. One-sentence plain-language explanation (section 10).
3. **OD card** and **OS card**, each with:
   - Pupil thumbnail
   - SE in diopters, large, with sign (use a true minus sign, for example −1.75 D)
   - Condition label chip ("Myopia, mild")
   - Smaller row: Sphere, Cylinder
   - Quality line: "10 of 10 frames used"
4. Session line: participant code, date and time, device distance range during capture.
5. Disclaimer: "Screening only. This is not a diagnosis or a prescription."
6. Buttons: **New screening**, **View history**.

Tablet and laptop: banner and explanation in a right column that stays in view; OD and OS cards left, side by side.

### 7.6 History

- Search by participant code.
- Filter chips: All, Referral, No referral, Myopia, Hyperopia.
- List rows: code, date and time, referral chip, SE for each eye in small text.
- Tapping a row opens the same Result screen (read-only). On laptop, History is master-detail: list left, result right.
- Delete a session: confirmation dialog, plain wording ("Delete this session? This cannot be undone.").
- Empty state: "No sessions yet." plus a Start screening button.

### 7.7 Settings

- **Language**: English / Filipino.
- **Device**: device name, SSID, IP, software version, storage free, clock status with a "Set clock from this device" button.
- **Calibration** (read-only): ToF last calibrated date, LED drive setting.
- **Data**: Export all sessions as CSV; Delete all data (two-step confirmation).
- **Research mode** toggle (off by default). When on:
  - The Result screen gains a form per eye to enter the **autorefractor ground truth** (mean sphere and mean cylinder over three readings, 0.25 D steps), linked to the session. This is what the capstone needs to compute MAE, ±0.50 D accuracy, and Bland-Altman agreement.
  - CSV export includes these fields.
  - This mode is a **proposal beyond the manuscript's described interface** (`OPEN` Q6).
- **About** (one short paragraph, from the copy deck) and **Disclaimer** (full text).

---

## 8. Responsive specification

Mobile-first. Test at **320, 390, 768, 1024, 1440** px wide.

| Width | Layout |
|---|---|
| Under 640 | Single column. Bottom tab bar (4 items). Sticky primary action at the bottom where relevant. Side padding 16 px. |
| 640 to 1023 | Left navigation rail (icons with labels). Content in a two-column grid where specified. |
| 1024 and up | Left rail with labels (about 220 px). Content max width 1200 px. Result and Align screens two-column. History master-detail. |

Rules:

- No horizontal scrolling at any width, including 320 px.
- Touch targets at least **48 × 48 px** on all interactive elements.
- Use `100dvh` and `env(safe-area-inset-*)` so the bottom bar is never clipped on phones.
- Respect landscape orientation on phones: Align and Record uses the two-column layout when height is under 500 px.
- Respect `prefers-reduced-motion`: no animated countdown ring or spinners that move large areas; use a numeric countdown instead.
- Respect `prefers-color-scheme` only if time permits. Light theme is the required deliverable. `OPEN` Q7.

---

## 9. Design system

Sample the exact brand teal from the screenshots in `docs/reference/` and set it as `--teal-600`. The values below are approximate starting points.

```css
:root {
  --bg: #f6f6f6;
  --surface: #ffffff;
  --text: #0f172a;
  --text-muted: #475569;
  --border: #e2e8f0;

  --teal-600: #0f9078;   /* sample from screenshots */
  --teal-700: #0b7562;
  --teal-50:  #e8f6f3;

  --ok-bg: #d1fae5;   --ok-text: #065f46;   --ok-border: #6ee7b7;
  --warn-bg: #fffbeb; --warn-text: #92400e; --warn-border: #fcd34d;
  --danger-text: #991b1b;  /* errors only, never for referral */

  --radius-card: 16px;
  --radius-control: 12px;
  --space: 4px;  /* use multiples: 4, 8, 12, 16, 24, 32 */
}
```

- **Font:** Inter, self-hosted as a subset variable WOFF2 (Latin plus the Filipino characters needed). Fallback `system-ui, sans-serif`.
- **Type scale:** 12 / 14 / 16 / 20 / 28 / 40 px. The SE value on Result is 40 px, semibold, tabular numerals (`font-variant-numeric: tabular-nums`).
- **Icons:** inline SVG sprite, copied from the Lucide set (ISC licence) for only the icons used. No icon font, no CDN.
- **Elevation:** one subtle card shadow. No glow, no neon, no glassmorphism.
- **Referral colours:** amber for REFERRAL RECOMMENDED, green for NO REFERRAL NEEDED. Never red for a referral, because a referral is a routine next step, not an alarm. Colour is never the only signal: always pair with icon and text.
- **Contrast:** WCAG AA minimum (4.5:1 body text, 3:1 large text and UI components).
- **Motion:** 150 to 200 ms ease-out for state changes only. No decorative animation.

---

## 10. Copy deck

All user-visible strings live in `static/i18n/en.json` and `static/i18n/fil.json`. No string is hard-coded in templates or JS.

**The Filipino strings below are drafts and must be reviewed by a native speaker before use.**

| Key | English | Filipino (draft) |
|---|---|---|
| app.subtitle | Refractive error screening | Screening ng error sa repraksyon |
| nav.home | Home | Home |
| nav.screen | Screen | I-screen |
| nav.history | History | Kasaysayan |
| nav.settings | Settings | Settings |
| home.start | Start screening | Simulan ang screening |
| flow.consent.age | Participant is 18 or older. | 18 taong gulang pataas ang kalahok. |
| flow.consent.signed | Written consent is signed and on file. | May pirmadong written consent. |
| align.tooClose | Move back | Lumayo nang kaunti |
| align.tooFar | Move closer | Lumapit nang kaunti |
| align.ok | Distance OK | Tama ang layo |
| align.record | Record 5 seconds | Mag-record ng 5 segundo |
| align.hold | Hold still | Huwag gumalaw |
| retake.title | Not enough clear frames. Retake this eye. | Kulang ang malinaw na frame. Ulitin ang mata na ito. |
| result.refer | REFERRAL RECOMMENDED | INIREREKOMENDA ANG REFERRAL |
| result.noRefer | NO REFERRAL NEEDED | HINDI KAILANGAN NG REFERRAL |
| result.explain.refer | One or both eyes are outside the normal range (−0.50 to +0.50 D). Refer to an optometrist or ophthalmologist for a full eye exam. | Isa o parehong mata ay lampas sa normal na saklaw (−0.50 hanggang +0.50 D). Ipa-refer sa optometrist o ophthalmologist para sa buong pagsusuri ng mata. |
| result.explain.noRefer | Both eyes are within the normal range. No referral is needed based on this screening. | Nasa normal na saklaw ang parehong mata. Hindi kailangan ng referral batay sa screening na ito. |
| result.disclaimer | Screening only. This is not a diagnosis or a prescription. | Screening lamang ito. Hindi ito diagnosis o reseta. |
| label.myopia.mild | Myopia, mild | Myopia, banayad |
| label.myopia.moderate | Myopia, moderate | Myopia, katamtaman |
| label.myopia.high | Myopia, high | Myopia, mataas |
| label.hyperopia | Hyperopia | Hyperopia |
| label.emmetropia | Near-emmetropia | Malapit sa normal na paningin |
| result.frames | {n} of {t} frames used | {n} sa {t} na frame ang nagamit |
| about.body | E-Eye is a low-cost screening device that estimates refractive error using eccentric infrared photorefraction. It helps decide who should be referred for a full eye exam. | Ang E-Eye ay murang screening device na tumatantya ng refractive error gamit ang eccentric infrared photorefraction. Tumutulong ito magpasya kung sino ang dapat i-refer para sa buong pagsusuri ng mata. |

Wording rules: short sentences, plain words, no medical jargon on the operator path. Technical terms (SE, OD, OS) appear only as secondary labels next to a plain one ("Right eye (OD)").

---

## 11. Data contract and API

The UI talks to Flask over JSON. Another team member builds the real backend; you build the UI against this contract and a mock (section 13).

### 11.1 Endpoints

| Method and path | Purpose |
|---|---|
| `GET /api/status` | Device health (camera, tof, led, model, storage_free_gb, clock_set, version, device_name, ssid, ip) |
| `GET /api/distance` | Server-Sent Events stream of `{cm, valid, ts}` at about 5 Hz |
| `GET /api/preview.mjpg` | MJPEG preview, about 640×480, 10 fps, paused during recording |
| `POST /api/precheck` | Runs the 5-second test capture, returns `{crescent_frame_url, tof_ok, brightness_ok, brightness_mean}` |
| `POST /api/sessions` | Create session `{participant_code, site, consent_age, consent_signed, client_time}` |
| `POST /api/sessions/{id}/record` | Body `{eye: "OD"|"OS"}`. Starts the 5-second capture. |
| `GET /api/sessions/{id}/events` | SSE: processing steps and completion for the current eye |
| `GET /api/sessions/{id}` | Full session with results |
| `GET /api/sessions` | List with query params `q`, `filter` |
| `DELETE /api/sessions/{id}` | Delete one session |
| `POST /api/sessions/{id}/ground-truth` | Research mode: `{eye, sphere_D, cylinder_D}` |
| `GET /api/export.csv` | Export all sessions |
| `GET/POST /api/settings` | Language and preferences |
| `POST /api/clock` | Set device clock from the client |

### 11.2 Session result shape

```json
{
  "id": "s_0001",
  "participant_code": "EE-261019-001",
  "created_at": "2026-10-19T09:41:00+08:00",
  "site": "RHU Sumilao",
  "referral": true,
  "referral_eyes": ["OD"],
  "eyes": {
    "OD": {
      "status": "ok",
      "sphere_D": -1.50,
      "cylinder_D": -0.50,
      "se_D": -1.75,
      "label": "myopia_mild",
      "frames_used": 10,
      "frames_total": 118,
      "distance_cm": {"min": 12.1, "max": 13.4},
      "thumbnail_url": "/media/s_0001/OD.jpg",
      "ground_truth": null
    },
    "OS": { "status": "not_recorded" }
  }
}
```

`status` is one of `ok`, `retake_needed`, `not_recorded`. `label` is one of `myopia_mild`, `myopia_moderate`, `myopia_high`, `hyperopia`, `emmetropia`. The server computes `se_D`, `label`, and `referral`. The UI never recalculates clinical logic, except to **display** values. If you need a client-side check for tests, mirror the rule in section 3 exactly.

### 11.3 Notes for the backend team

- The Pi has no battery-backed clock. Offline, timestamps will be wrong after a power cycle. The UI sends `client_time` on session creation and offers "Set clock from this device" in Settings. Show a warning on Home when `clock_set` is false.
- Serve on port 80 (or proxy) so the URL is plain `http://192.168.4.1`.
- Optional: a captive-portal redirect or a local name such as `eeye.local` helps people who mistype the IP.

---

## 12. Tech stack, structure, and budget

**Stack**

- Flask with Jinja templates. Server renders the shell; small ES-module JS files handle live parts (distance, recording, processing, history filtering).
- **Vanilla JS** (ES modules). No React, Vue, or Tailwind CDN. If you want a utility CSS framework, it must be compiled locally to a static file and the build step must not be needed on the Pi.
- One CSS file using custom properties (section 9). No CSS-in-JS.
- No external requests at runtime. No source maps in the shipped build.

**Folder structure**

```
eeye-ui/
  .agent/skills/no-ai-slop/SKILL.md
  docs/E-EYE_UI_BRIEF.md
  docs/reference/            (screenshots, manuscript excerpt)
  app/
    app.py                   (Flask routes; mock-aware)
    mock/                    (fixtures and a fake distance stream)
    templates/               (base.html, home.html, new.html, record.html, result.html, history.html, settings.html)
    static/
      css/app.css
      js/                    (api.js, i18n.js, distance.js, record.js, result.js, history.js, settings.js)
      i18n/en.json, fil.json
      fonts/Inter-subset.woff2
      icons/sprite.svg
  tests/
    viewports.spec.*         (screenshots at the five widths)
    no-external-requests.*   (fails if any request leaves 192.168.4.1 / localhost)
```

**Budget** (so the Pi stays responsive)

- Total initial page weight under 300 KB gzipped, excluding the live preview stream and thumbnails.
- JS under 60 KB gzipped in total.
- No polling faster than 5 Hz. Use SSE for distance and processing events.
- Thumbnails at most 320 px wide, JPEG.

---

## 13. Mock mode and fixtures

Run with `EEYE_MOCK=1` so the UI can be built and tested with no Pi attached.

- `/api/status` returns healthy by default; a query flag can simulate each failure.
- `/api/distance` replays a scripted sequence: too far, approaching, in range, drift out, back in.
- `/api/preview.mjpg` serves a looping set of sample frames or a placeholder image labelled "MOCK".
- Three result fixtures: **refer** (OD −1.75 D, OS −1.37 D), **no refer** (both within ±0.50 D), **retake** (OS fails with `retake_needed`). Use made-up participant codes.
- The mock must be visibly marked in the UI (a small "MOCK DATA" tag in Settings and in the page title) so it can never be mistaken for real results.

---

## 14. Accessibility

- All interactive elements are reachable and operable by keyboard, with a visible focus ring.
- Semantic HTML: `nav`, `main`, headings in order, `button` for actions, `label` for inputs.
- The referral banner has `role="status"` and `aria-live="polite"`.
- Distance meter state changes are announced through a polite live region (throttled to state changes, not every reading).
- Images have meaningful `alt` text ("Right eye pupil image").
- Text can be zoomed to 200% without breaking layout.
- Language attribute (`lang`) updates when the language changes.

---

## 15. Anti-slop rules (summary)

The full rules are in the `no-ai-slop` skill. The short version:

- No placeholder or filler text anywhere: no lorem ipsum, no "Welcome to the future of eye care", no marketing slogans.
- No invented numbers: no fake accuracy, no fake confidence, no fake user counts, no fake testimonials.
- No emoji as icons. No decorative gradients, blobs, glows, or purple-to-blue hero backgrounds.
- No unexplained "AI-powered" or "smart" labels anywhere in the UI.
- Every component exists for a reason in this brief. If you add one, say why.
- Code comments explain why, not what. No boilerplate headers, no commented-out code, no "TODO: implement" stubs left in a finished phase.
- Commit messages and docs are specific and short.

---

## 16. Phases and deliverables

| Phase | Scope | Done when |
|---|---|---|
| 0. Plan | Implementation Plan artifact, confirm tool availability, list any `OPEN` questions you need answered | Owner approves |
| 1. Foundation | Folder structure, Flask shell, mock mode, design tokens, base template, nav, i18n loader, EN/FIL switch, fonts and icon sprite | Home loads in mock mode at all five widths; zero external requests |
| 2. Screening flow | New Screening, Align and Record, Processing, Retake | A full two-eye run works in mock mode on phone and laptop |
| 3. Result | Result screen with all three fixtures | Refer, no-refer, and retake-then-single-eye states all render correctly at all widths |
| 4. History and Settings | History with search and filters, Settings, CSV export, delete | Filters work; delete works; clock warning shows |
| 5. Optional | Research mode (ground truth entry), Save as PDF | Only if the owner approves |
| 6. Hardening | Accessibility pass, performance check, no-external-requests test, Pi deployment notes | Section 17 checklist all green |

At the end of each phase, report: what changed, screenshots at the five widths, and anything you are unsure about.

---

## 17. Acceptance checklist

- [ ] Works with the network disabled; no request leaves the Pi (verified in the browser network panel and by the automated test).
- [ ] Banner is binary and follows the ±0.50 D rule for all three fixtures.
- [ ] SE shown equals sphere + cylinder / 2 (spot-check two values by hand).
- [ ] No names, no age fields, no "risk" tiers, no confidence bars, no diagnostic wording, no "AI-powered" wording anywhere.
- [ ] Record button stays disabled until distance is valid.
- [ ] Retake path and single-eye result path both work.
- [ ] No horizontal scroll at 320 px. Touch targets at least 48 px.
- [ ] Keyboard-only run-through of the whole flow succeeds.
- [ ] Contrast meets AA (checked with a tool, not by eye).
- [ ] English and Filipino both complete; no missing keys.
- [ ] Page weight and JS within budget.
- [ ] 10 consecutive fresh loads of the Result page render the correct banner (mirrors the manuscript's 10-connection test).
- [ ] Mock mode is clearly marked and cannot be mistaken for real data.

---

## 18. Open questions for the owner (do not guess)

- **Q1.** Final brand colour: keep the Base44 teal, or switch to the defense-deck navy, gold and sky blue?
- **Q2.** Is the cylinder value shown to the operator at all levels, or only in a detail view? (Brief assumes shown, smaller than SE.)
- **Q3.** Hyperopia severity bands: the manuscript defines none. Keep a single "Hyperopia" label?
- **Q4.** Retake threshold: this brief assumes fewer than 10 valid frames triggers Retake. Confirm and add one sentence to Chapter 3 so the manuscript matches the UI.
- **Q5.** Record button enable rule: 1 continuous second in range is a proposal. Confirm.
- **Q6.** Research mode (autorefractor ground-truth entry): in scope for the capstone UI, or handled in a spreadsheet?
- **Q7.** Dark mode: needed, or light only?
- **Q8.** Filipino copy: who reviews it?
- **Q9.** Save as PDF: needed for referral handoff, or skip?

---

## 19. Kickoff prompt (paste into Antigravity)

> Read `docs/E-EYE_UI_BRIEF.md` fully, then load the `no-ai-slop` skill from `.agent/skills/no-ai-slop/SKILL.md`. Look at every image in `docs/reference/`. Do not write code yet. Produce an Implementation Plan artifact for Phases 0 to 6: the file list, the route list, the component list per screen, and a test plan for the five viewports. List which tools and skills you can actually use in this environment and which of the brief's `OPEN` questions you need answered before Phase 1. Wait for my approval before starting.
