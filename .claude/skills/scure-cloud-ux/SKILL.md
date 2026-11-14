---
name: scure-cloud-ux
description: Usability and look rules for the sCure Cloud portal (cloud/google/Page.html) - make every screen simple, clear and comfortable for engineers working at a bench, on a phone or a desktop. Use this skill whenever the user asks to change, add or review a screen, a tab, a button, a table, a form, wording, colours or layout of the cloud portal, asks for "user friendly", "simpler", "easier", "phone version", "UX" or "look", or when a new feature (a tab, a card, a dialog) is about to be added to the portal - even if they do not say "UX".
---

# sCure Cloud - usability and look

The portal is used by integrators and engineers who are standing at a machine, often with a phone in one hand and gloves or a tool in the other. They open it to answer one question ("how far is my unit?", "can I start this test?", "who is ahead?") and then go back to the machine. A screen is good when that person finds the answer in a few seconds without reading.

Work from the file `cloud/google/Page.html` (one file: CSS, markup, script) and keep the tests green (`cloud/google/test_*.cjs`, run each with `node`). Publishing is `npx @google/clasp push -f` and `clasp deploy -i <id>`; bump `PORTAL_BUILD` in both `Code.gs` and `Page.html` on every change (a mismatch tells open tabs to reload).

## What to decide before touching a screen

1. **Who is looking, and what is the one question?** Write it down in one sentence. If a screen answers three questions, it is three screens (or one answer and a "more" fold).
2. **What is the one next action?** One primary button per screen, in the accent colour; everything else is quiet. If nothing needs doing, say so in words ("Nothing needs your attention").
3. **What can be decided for the person?** One CureBox - choose it. One unit - open it. A value with a known default - fill it. A choice the person never has to make is the best kind of simple.

## Rules, and why

- **Say what it means, not what it is called inside.** "Runs finished 2 of 412" beats "Completion 0.5 %". Use the words the people use (test, unit, CureBox, run); no codes or field names unless the code is the thing being looked up. Reason: the reader will not stop to translate.
- **Few numbers, then more on request.** Show at most four figures at first; the rest sit behind "More numbers". Reason: every extra figure competes with the one that matters.
- **Phone first.** Layout works at 390 px with no sideways scroll; tap targets are at least 44 px; text fields use 16 px so the phone does not zoom; lists become cards with the label on each line; the sections are a bottom bar a thumb can reach. Reason: that is how the portal is really used at the bench.
- **Colour carries meaning, so spend it carefully.** One accent for "do this" and for progress; green = good, red = broken, amber = needs a look, grey = nothing. Never colour alone: the word (PASS, FAIL, blocked) is always there too.
- **Sentence case, normal weight for labels.** All-caps tracked labels everywhere make a page look generated and are harder to read. Headings are short sentence-case phrases; the biggest, boldest thing on a screen is the answer.
- **Structure is information.** A border, a card, a number badge is there because the content is a group, a list item or a sequence - not to decorate. Prefer space between groups over a box around each.
- **Always show the state.** Loading, empty, offline, waiting for the machine, saved: each says what is happening and what (if anything) to do next. A button that cannot be used says why, near the button.
- **Be careful with the irreversible.** Starting a race, resetting it, deleting a program: ask once, in plain words that name the effect ("Start the race now? Every unit's clock starts together."). Everything else: no confirmation, but an undo or a clear way back.
- **Stay consistent.** The same thing looks and is worded the same on every screen; the sections keep their order; the primary action sits in the same place.
- **Keyboard and contrast.** Visible focus, text at least 4.5:1 against its ground, dark mode follows the phone (tokens, not literals).

## Checklist before you finish a change

- [ ] The screen's one question and one action can be named; the answer is the largest thing on it.
- [ ] 390 px: no sideways scroll, every control at least 44 px, fields 16 px (`node cloud/google/test_phone.cjs` checks this on every section).
- [ ] Labels are plain words; no all-caps tracked labels added; numbers have units.
- [ ] Empty, loading and error states are written, not blank.
- [ ] A test covers what the person would now be able to do (click the thing, read the value), not only that the page loads.
- [ ] No `//` hidden in a regex in `Page.html` (the Apps Script HTML service cuts the rest of the line) - `test_errors_page.cjs` guards it. Do not put a `//` comment in the middle of a line of code either.
- [ ] After deploying, load the live page once (`login_check` style) to see that it still opens - a script error leaves a blank page.

## The portal's look (tokens in `:root` of Page.html)

Calm and neutral so the status colours stand out: a near-white ground, ink text, one cobalt accent for primary actions and progress, soft grey lines, 8-10 px radii used sparingly. Type is the system sans, 15 px body, headings 1.05-1.25 rem semi-bold, numbers tabular. A dark theme is the same tokens redefined under `prefers-color-scheme`. Change the look by changing tokens first; a literal colour in a rule is a smell.
