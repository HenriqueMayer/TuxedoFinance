# Frontend: Design System & Templates

Every screen is server-rendered Django Template Language, styled entirely with TailwindCSS utility classes — there is no JavaScript framework, no build-time component system, and no client-side charting library. The narrow JavaScript layer is limited to theme persistence, HTMX partial swaps, and restoring the viewport/focus after a chart filter update. This page documents the visual language (PRD §9) and how the template tree is organized; for the actual HTML of any single screen, see the app doc that owns it in [`apps/`](apps/).

## Tailwind strategy: dev/prod

Two completely different delivery mechanisms, switched by `{{ DEBUG }}` (from `core.context_processors.debug_flag`) in `templates/base.html`:

```django
{% if DEBUG %}
<script src="https://cdn.tailwindcss.com"></script>
<script>
    tailwind.config = { theme: { extend: { fontFamily: { sans: ['Inter', 'system-ui', 'sans-serif'] } } } };
</script>
{% else %}
<link rel="stylesheet" href="{% static 'css/output.css' %}">
{% endif %}
```

- **Development (`DEBUG=True`)** — the Tailwind Play CDN, zero build step. Every utility class is compiled client-side, on the fly, by the CDN script. This is what `uv run python manage.py runserver` uses.
- **Production (`DEBUG=False`)** — a pre-compiled, minified `static/css/output.css`, built from `tailwind/input.css` by the **standalone Tailwind CLI** (a plain Linux binary — no Node.js/npm anywhere in this project) at Docker image build time, then served by WhiteNoise. See [deployment.md](deployment.md#stage-1-builder-ghcrioastral-shuvpython312-trixie-slim) for the exact build command.

`tailwind/input.css` is deliberately kept **outside** `static/`:

```css
@import 'tailwindcss';

@theme {
    --font-sans: 'Inter', 'system-ui', 'sans-serif';
}
```

Django's `collectstatic` post-processor rewrites `@import`/`url()` references in every CSS file it collects; if `input.css` lived under `STATICFILES_DIRS`, `collectstatic` would try (and fail) to resolve `@import 'tailwindcss'` as a relative static file. Keeping the *source* out of `static/` sidesteps this — only the already-compiled `output.css` (plain CSS, no imports) ever lives under `static/css/`. Tailwind v4 scans the whole project (respecting `.gitignore`) for utility classes used in `templates/**/*.html` automatically — there's no manual content-glob configuration.

## Design tokens (PRD §9.1)

| Role | Tailwind token | Usage |
|---|---|---|
| Base background | `bg-slate-950` | Main background |
| Surface | `bg-slate-900/60` + `backdrop-blur` | Cards, panels, navbar |
| Border | `border-slate-800` | Subtle outlines |
| Primary (gradient) | `from-indigo-500 via-violet-500 to-fuchsia-500` | Primary buttons, brand mark, active-link underline |
| Income | `text-emerald-400` / `bg-emerald-500/10` | Inflows |
| Expense | `text-rose-400` / `bg-rose-500/10` | Outflows |
| Investment | `text-amber-400` / `bg-amber-500/10` | Investments |
| Primary text | `text-slate-100` | Headings, values |
| Secondary text | `text-slate-400` | Labels, descriptions |
| Focus ring | `ring-indigo-500` | All interactive elements |

Typography: **Inter** (Google Fonts, `font-sans`), fallback `system-ui`. Heading `text-3xl font-bold`; section `text-xl font-semibold`; body `text-base`; helper `text-sm text-slate-400`. All monetary values use `tabular-nums font-semibold` so digits align in columns.

## `templates/base.html` — the root layout

Every single template in the project extends this file — there is no screen that builds its own `<html>`. It owns:

- `<head>`: charset/viewport meta, `<title>` via `{% block title %}` (defaults to `"CashFlow"`), Inter font preconnect/link, the dev/prod Tailwind switch above.
- `<body>`: conditionally includes `partials/navbar_app.html` or `partials/navbar_public.html` based on `request.user.is_authenticated`, then `<main>` wrapping `partials/messages.html` + `{% block content %}`, then `partials/footer.html`.

A page template only ever needs to write:

```django
{% extends 'base.html' %}
{% block title %}My Page — CashFlow{% endblock %}
{% block content %}
  ...
{% endblock %}
```

## Partials (`templates/partials/`)

| Partial | Role |
|---|---|
| `navbar_public.html` | Anonymous navbar — logo + Log in / Sign up buttons. |
| `navbar_app.html` | Authenticated navbar — Dashboard/Transactions/Categories/Payments links (active state = white text + gradient underline), username, POST-only Log out form, and a CSS-only (`<details>`/`<summary>`, no JS) mobile menu disclosure below the `md` breakpoint. |
| `footer.html` | Shared footer with the CashFlow mark and a `{% now 'Y' %}`-stamped copyright line linking to [github.com/HenriqueMayer](https://github.com/HenriqueMayer). |
| `messages.html` | Renders Django's `messages` framework, mapping each message's `.tags` (`success`/`error`/`warning`/other) to the matching semantic color from the token table above. Included once, automatically, by `base.html` — no screen includes it manually. |
| `form_field.html` | The one-and-only field renderer. Renders label + required-asterisk + the bound `{{ field }}` + help text + errors. **Does not inject Tailwind classes into the field itself** — that's the owning form's job (every form's `__init__` sets `field.widget.attrs['class']` to the shared `INPUT_CLASSES` string, duplicated identically in `accounts/forms.py`, `categories/forms.py`, `payments/forms.py`, and `transactions/forms.py`). |
| `stat_card.html` | The dashboard/landing indicator card: a label + a value with an optional semantic `value_class`. Takes an **already-formatted** `value` string (currency symbol and decimal formatting are the caller's job) — this partial only handles layout and color, never currency logic. |
| `empty_state.html` | The standard "nothing here yet" block: icon + title + message + an optional CTA button. Used by every list screen (`transactions/list.html`, `categories/list.html`, `payments/list.html`, `dashboard/index.html`) when its queryset is empty. |

## Shared component classes (PRD §9.3/§9.4, not extracted into template tags — copied verbatim per use)

```html
<!-- Primary button -->
<button class="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-indigo-500 via-violet-500 to-fuchsia-500 px-4 py-2.5 text-sm font-semibold text-white shadow-lg shadow-indigo-500/20 transition hover:opacity-90 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 focus:ring-offset-slate-950">

<!-- Secondary button -->
<button class="inline-flex items-center gap-2 rounded-xl border border-slate-700 bg-slate-900/60 px-4 py-2.5 text-sm font-medium text-slate-200 transition hover:bg-slate-800">

<!-- Destructive button -->
<button class="inline-flex items-center gap-2 rounded-xl bg-rose-500/10 px-4 py-2.5 text-sm font-semibold text-rose-400 ring-1 ring-inset ring-rose-500/30 transition hover:bg-rose-500/20">

<!-- Text/select/textarea input -->
<input class="w-full rounded-xl border border-slate-700 bg-slate-900/60 px-3.5 py-2.5 text-slate-100 placeholder:text-slate-500 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/40">

<!-- Card / form group -->
<div class="rounded-2xl border border-slate-800 bg-slate-900/60 p-6">
```

These exact strings recur across every screen in the project. There's no CSS/Tailwind `@apply` abstraction wrapping them (per the "no over-engineering" house rule) — consistency comes from every app copying the canonical markup rather than inventing new variants.

## Template tree

```
templates/
├── base.html
├── partials/
│   ├── navbar_public.html   navbar_app.html
│   ├── footer.html          messages.html
│   ├── form_field.html      stat_card.html
│   └── empty_state.html
├── pages/landing.html
├── accounts/login.html      signup.html
├── dashboard/index.html     reports.html
├── categories/list.html     form.html    confirm_delete.html
├── payments/list.html       form.html    confirm_delete.html
└── transactions/list.html   form.html    confirm_delete.html
```

Every `list.html`/`form.html`/`confirm_delete.html` triplet (categories, payments, transactions) follows the identical structural pattern:

- **`list.html`** — heading + "New X" primary button, then either a divided `<ul>` of rows (each with Edit/Delete secondary/destructive buttons) or `empty_state.html`. `transactions/list.html` additionally has the GET-param filter form (see [apps/transactions.md](apps/transactions.md#transactionlistview)) and pagination controls using Django's `{% querystring %}` tag so active filters survive page navigation.
- **`form.html`** — a centered `max-w-md` card, `<form method="post" novalidate>` + `{% csrf_token %}`, non-field errors rendered above the fields, then one `{% include 'partials/form_field.html' %}` per field, then Save (primary) / Cancel (secondary, linking back to `list`).
- **`confirm_delete.html`** — a centered `max-w-md` card confirming the object's name/title, a `<form method="post">` with Delete (destructive) / Cancel (secondary) — deletion is **never** a plain link/`GET`, always a POST from this confirmation screen.

## Server-Rendered Charts (`dashboard/_reports_charts.html`)

The report charts are inline `<svg>` built from coordinates computed in `dashboard/charts.py` — there is no charting library or client-side chart geometry. The partial is the HTMX-swapped island inside `reports.html`: every interactive control carries both `hx-*` wiring and a plain `href`/`action` fallback, so the page also works with JavaScript disabled. When HTMX is active, `templates/base.html` captures `window.scrollY` and the focused field before a Reports or Investments chart island swap, then restores both after the swap.

- **Semantic tones, not colors, cross the Python boundary.** `charts.py` emits `tone` values (`'income'|'expense'|'investment'` for the bar chart, `'installment'|'fixed'|'one_off'` for the donut); this template maps them to Tailwind classes (`fill-emerald-400 dark:fill-emerald-300`, `fill-rose-500 dark:fill-rose-400`, `fill-amber-400 dark:fill-amber-300`, and `fill-indigo-500 dark:fill-indigo-400`, `fill-slate-500 dark:fill-slate-400` for the recurrence buckets). Design tokens never leak into Python.
- **The balance line uses the primary gradient** via an SVG `<linearGradient>` (`stroke="url(#balance-line)"`), because Tailwind's `from-*/via-*/to-*` utilities don't apply to SVG strokes. The stop colors are the raw RGB of `indigo-500`/`violet-500`/`fuchsia-500` — the one place in the project where a design token is written as a literal color, and it's flagged in the template comment for that reason.
- **The zero line is dashed rose** (`stroke-rose-400 dark:stroke-rose-500`, `stroke-width="1.5"`, `stroke-dasharray="5 4"`) rather than the muted slate of the rest of the grid — a balance crossing zero is the single most important event on the chart and should read at a glance, not blend into the axis.
- **Tooltips are native `<title>` elements** inside each `<circle>`/`<rect>`/`<path>`; browsers show them on hover with no script.
- **The category breakdown needs no SVG at all** — it's a `<div>` with `style="width: {{ category.bar_width }}%"` inside a rounded track. Reaching for SVG there would have been ceremony.
- **The recurrence donut is one `<path>` per drawn slice** plus a centered `<text>` block for the window total — no `<circle>` stroke tricks, no conic gradients. The `build_donut_chart` geometry produces ready-to-render `d="..."` arc strings, and the special full-ring case splits into two semicircle arcs so a single slice that covers 100% still renders (an SVG `A` command needs two distinct endpoints, so a literal 360° arc would otherwise vanish).

## Investment Charts (`investments/_investments_charts.html`)

The investments list page carries its own two-chart island at the bottom, built from the same `dashboard/charts.py` builders as the Reports page (`build_line_chart` and `build_bar_chart`). The partial wraps everything in `<div id="investments-charts">` so `InvestmentListView.get_template_names()` can return the partial alone when `HX-Request: true` lands — the same exact swap pattern the Reports page established. `{% include %}` wires the partial inside the full `list.html` for normal GETs; in both cases the server runs the same context, so the page renders the same whether the request came from HTMX or a full page load.

Investment structure management uses the standard server-rendered list/form/
confirmation pattern: `investments/settings/index.html` lists institutions,
products, and assets; `investments/setup_form.html` serves both create and
update; and `investments/settings/confirm_delete_entity.html` requires a CSRF
protected POST. The Investments navbar item uses the resolved URL namespace for
its active state, so it stays highlighted on nested settings and edit routes.

The two charts each own an independent 12-month window — they slide independently so the user can scroll chart 1 (Investment evolution) back a year while leaving chart 2 (Monthly flow) anchored on today. The arrows carry `hx-target="#investments-charts"`, `hx-swap="outerHTML"`, `hx-push-url="true"`, mirrored on a plain `href` for the no-JS degradation path: each chart's prev/next anchors are `{% querystring total_offset=N %}` / `{% querystring flow_offset=N %}` respectively, so `{% querystring %}` updates one param while preserving the other — plus any active `?kind`/`?q` filters stay alive across the slide. The two services `get_total_in_base_timeseries` and `get_monthly_flow_in_base` each take their own `offset=` argument.

- **Chart 1 — Investment evolution** (`build_line_chart`): a single area-line of the cumulative portfolio total in `{{ CURRENCY_SYMBOL }}`. The view builds it from `get_total_in_base_timeseries`, which folds each month's per-currency balances through `_resolve_rate` (rate-at-time, with a graceful fall-back to the latest rate when no historical row exists for that pair on that date). Inherits the Reports chart-1 visual contract verbatim — `<linearGradient id="investments-line">` stops `indigo-500`/`violet-500`/`fuchsia-500`, a duplicate `investments-area` gradient for the violet 35%-to-0% fill, dashed rose zero line at `zero_y`, and white/dark `circle` markers with `stroke-violet-400`. The only visual delta is the gradient `id` — the partial can be HTMX-swapped standalone, so the IDs cannot collide with Reports' own.

- **Chart 2 — Monthly flow** (`build_bar_chart`): grouped bars of Deposits × Yields × Withdrawals per month, both in `{{ CURRENCY_SYMBOL }}` via per-entry FX. Deposits use emerald, yields amber, and withdrawals rose. `get_monthly_flow_in_base` walks each month's operations individually (not cumulative) and applies `_resolve_rate` on each entry's own `date`.
| `CHF` | `stroke-amber-500` | matches the Investment semantic |
| anything else | `stroke-slate-500` | safe fallback for a currency added to `core/currencies.py` later |

The colors are spelled out directly in `investments/_investments_charts.html` (one `elif` chain on the code) rather than mapped through a `tone` field, because each currency has a fixed color — the chart never re-tints a series based on what kind of value it is. The legend swatch and the per-point circle's stroke share the same `elif` chain, so a line and its markers always match.

## Responsiveness (PRD §9.6, NFR06)

Mobile-first throughout: single-column layouts expand via `sm:`/`md:`/`lg:` breakpoints (e.g. the dashboard's stat-card grid is `grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6`). The authenticated navbar's desktop links (`hidden md:flex`) collapse into a `<details>`-based dropdown below `md` — no JavaScript, no separate mobile markup to keep in sync (it's the same `<a>` tags, just conditionally visible).

Two elements deliberately **opt out** of shrinking: the dashboard outlook table and the report SVGs sit in `overflow-x-auto` wrappers around a fixed `min-w-[40rem]`/`min-w-[44rem]` canvas. A chart scaled down to a 360px viewport has illegible axis labels; scrolling it sideways *inside its own card* keeps it readable without ever making the page body scroll horizontally.
