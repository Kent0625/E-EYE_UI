---
name: no-ai-slop
description: Use before designing UI, writing copy, or writing code for the E-Eye project, and again before any final review. Rules that stop generic, filler, or invented AI-looking output in interfaces, text, and code.
---

# No AI slop

"Slop" is output that looks plausible but carries no real information: generic wording, invented data, decoration with no purpose, boilerplate code. This project is a medical screening tool. Invented content is not just ugly, it is unsafe.

Apply these rules to everything you produce. If a rule conflicts with the project brief, the brief wins, and you tell the owner about the conflict.

## 1. Content and copy

- Every string must be needed by a real screen state. Delete anything that exists only to fill space.
- No lorem ipsum, no "Your journey to better vision", no "Empowering communities", no marketing slogans, no taglines.
- No invented facts or numbers: no accuracy claims, confidence percentages, user counts, awards, testimonials, or statistics unless they come from the brief or the manuscript.
- No "AI-powered", "smart", "intelligent", "next-gen", or "revolutionary" wording in the UI.
- No filler openers or closers ("Welcome back!", "Oops!", "Great job!", "Let's get started!").
- Use short, plain sentences. One idea per sentence. Say what happened and what to do next.
- Error and empty states state the cause and the action. Example: "No distance reading. Check that the sensor is not covered." Not: "Something went wrong."
- Never use sample names, faces, or realistic personal data. Participant codes only, clearly fictional in mock data.
- Do not write medical claims. Show only values the model outputs and the referral rule from the brief.

## 2. Visual design

- No decorative gradients, blurred blobs, glows, glassmorphism, or purple-to-blue hero backgrounds.
- No emoji used as icons or bullets.
- Icons: one consistent set (Lucide, inline SVG). Each icon must carry meaning that the label alone does not, or support a label for scanning. No icons added only for decoration.
- No stock-illustration characters, no 3D shapes, no generic "medical cross and heartbeat line" art.
- One brand colour plus the status colours defined in the brief. Do not add accent colours.
- Do not rely on colour alone for meaning. Pair colour with an icon and text.
- Cards only where content is genuinely grouped. Do not nest cards inside cards. Do not wrap a single line of text in a card.
- No fake progress bars, fake loaders, or animated "scanning" effects. Show a spinner only when something is really happening, and a percentage only when the backend reports one.
- Motion only for state change (150 to 200 ms). Nothing loops for decoration.
- Use consistent spacing from the 4 px scale. No arbitrary one-off values.

## 3. Interaction

- Every button does one clear thing and is labelled with a verb ("Start screening", "Retake", "Delete session").
- Disabled controls always show why they are disabled.
- Destructive actions need a confirmation with plain wording.
- No dark patterns, no upsells, no "Rate this app" prompts, no tours or onboarding carousels.

## 4. Code

- Write only what the current phase needs. No speculative abstractions, no unused helpers, no placeholder functions.
- No boilerplate header comments, no restating comments ("// loop through items"). Comment only to explain why something non-obvious is done.
- No commented-out code. No leftover `console.log`. No `TODO` stubs in a phase marked done.
- Name things for what they are in this project (`distanceInBand`, `referralEyes`), not generic names (`data`, `handler`, `utils`).
- Keep functions short and single-purpose. Prefer plain JS over adding a dependency.
- Do not add packages that load assets or call out at runtime. No telemetry.
- Clinical logic (SE, labels, referral) lives in one place on the server. The client displays it and does not re-derive it, except in tests.

## 5. Reports and commit messages

- Say what changed and why, in specific terms. No "improved the UI" or "enhanced user experience".
- Do not claim something works unless you ran it. Show the screenshot, test output, or network log.
- Report uncertainty plainly. If you are unsure, say so and ask.

## 6. Pre-flight checklist (run before finishing any phase)

1. Read every visible string on every screen. Remove any that you cannot trace to the brief's copy deck or a real data field.
2. Search the code and templates for: `lorem`, `AI-powered`, `smart`, `TODO`, `console.log`, emoji, and any `http://` or `https://` that is not the local app.
3. Check that no number on screen is hard-coded unless it is a fixed rule from the brief (for example the 10 to 15 cm band and the ±0.50 D range).
4. Check that mock data is labelled as mock.
5. Confirm every colour-coded state also has an icon and text.
