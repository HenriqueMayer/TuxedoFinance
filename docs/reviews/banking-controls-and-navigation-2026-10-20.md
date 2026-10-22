# Banking controls and workspace entry — 2026-10-20

This dated review covers the working tree based on `cc110a8` on
`feat/tuxedo-assistant-foundation`. It records interface changes and their
validation, not a release or an authorization to publish. Earlier pending
assistant changes were retained.

## Delivered behavior

- Bank markers and debit/credit-card creation and editing share six optional
  color shortcuts with an adjacent native custom-color input. Black, Blue gray,
  Purple, Blue, Orange and Gold are practical visual choices, not a statistical
  ranking or a restriction on valid HEX values. Official
  [Inter card examples](https://www.inter.co/pra-voce/cartoes/) and the
  [Nubank card page](https://nubank.com.br/nu/cartao) informed the visual palette.
- Native color controls are 48×44px, including the gradient's second stop.
  Preset buttons retain 44px targets. Phone layouts group the shortcuts into
  two rows beside the custom picker; narrow layouts retain wrapping. Gradients,
  the rotary angle handle and live previews keep their existing behavior.
- Invalid bound HEX text remains editable beside its server error instead of
  being silently replaced with black by the browser. Presets are progressive
  shortcuts; native color fields, datalists and complete POSTs work without
  JavaScript. Existing appearance defaults and saved records are unchanged.
- Account openings are labelled **Balance when tracking starts** and **Start
  tracking on**, with visible copy explaining that the balance precedes that
  date's movements. A new nonzero balance still needs its date; unknown legacy
  dates are not inferred.
- **Planning adjustments (optional)** groups account inclusion and **Keep outside
  monthly planning**. The disclosure explains that a reserve does not move cash
  and that goal reservations are not added twice. It opens for saved reserves,
  excluded accounts and errors; closing it never drops submitted values.
- The workspace brand opens the dashboard on desktop and phone. Authenticated
  visits to `/` redirect there too; public entry and logout retain the cover.
  Native navigation and unsaved-edit departure handling remain intact.

Current contracts are maintained in [forms](../frontend/forms.md#card-appearance),
[banking](../apps/banking.md), [navigation](../frontend/navigation.md) and the
[catalogue guide](../frontend/catalogue.md). The synthetic Design Lab now offers
the same six colors and custom gradients during creation and editing.

## Validation

All application checks used disposable settings/databases and disabled real
assistant integrations. Browser checks used `npm run test:e2e`, never the
installation server or database.

| Check | Observed result |
| --- | --- |
| Django system checks and migration drift | Passed; no model/migration change required. |
| Complete Django suite | 1,180 tests passed in 240.328 seconds. |
| JavaScript unit suite | 26 tests passed. |
| Targeted browser coverage | 75 distinct scenarios obtained passing results, including the focused corrections below. |
| Frontend build, JS syntax, focused executable-correctness lint | Passed. |
| Translations | English/Brazilian Portuguese aligned; no active fuzzy/untranslated entries; compiled catalog reproducible. |
| Installation and pending work | Installation database hash unchanged; 53 unrelated pending files retained byte for byte. |

The browser selection covered color controls, account presentation, gradient
keyboard/touch/native fallback, banking workspaces, the Design Lab editor,
shared form choices, contextual help, public entry and brand navigation. The
initial 75-case pass had 73 successes and two assertions for the former
currency/balance row. Those assertions now check the intended balance/date pair.
A 13-case repeat passed those cases and identified a Portuguese custom-color
caption wrapping below its palette. The caption and responsive spacing were
corrected; the final nine color cases passed, including both languages, both
themes and 390/1440px widths. The touch dial also passed at 320/390px.

Rendered captures were inspected for compact inputs, six visible shortcuts,
custom selection, readable labels, keyboard focus, expanded/invalid planning
settings and final actions above fixed navigation. Viewport captures supplement
full-page images, whose fixed headers may appear at the document's captured
scroll position. Native POSTs, malformed colors, invalid reserves, retained
saved values, logout and edited-form departure were exercised.

Private validation artifacts remain under ignored `.local/`: the review's
`banking-controls-2026-10-20` directory and the browser output directories
`banking-controls-2026-10-20`, `banking-controls-final-2026-10-20` and
`banking-colors-confirmed-2026-10-20`.

## Limits

Desktop and phone checks used Chromium and emulated touch; physical devices,
screen readers and other browser engines were not certified. The operating
system's color-dialog appearance is browser-owned. No real model calls, banking
connections, financial-data updates, commit or publication were performed for
this interface change.
