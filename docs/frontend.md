# Frontend: Design System & Templates

Every screen is server-rendered Django Template Language, styled entirely with TailwindCSS utility classes — there is no JavaScript framework, no build-time component system, and (outside the `<details>`-based mobile menu disclosure) no JavaScript at all. This page documents the visual language (PRD §9) and how the template tree is organized; for the actual HTML of any single screen, see the app doc that owns it in [`apps/`](apps/).

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

## Charts without JavaScript (`dashboard/reports.html`)

The report charts are inline `<svg>` built from coordinates computed in `dashboard/charts.py` — the project's zero-JS rule rules out every charting library, so the geometry happens server-side and the template only interpolates attributes.

- **Semantic tones, not colors, cross the Python boundary.** `charts.py` emits `tone: 'income'|'expense'|'investment'`; this template maps them to `fill-emerald-400/80`, `fill-rose-400/80`, `fill-amber-400/80`. Design tokens never leak into Python.
- **The balance line uses the primary gradient** via an SVG `<linearGradient>` (`stroke="url(#balance-line)"`), because Tailwind's `from-*/via-*/to-*` utilities don't apply to SVG strokes. The stop colors are the raw RGB of `indigo-500`/`violet-500`/`fuchsia-500` — the one place in the project where a design token is written as a literal color, and it's flagged in the template comment for that reason.
- **Tooltips are native `<title>` elements** inside each `<circle>`/`<rect>`; browsers show them on hover with no script.
- **The category breakdown needs no SVG at all** — it's a `<div>` with `style="width: {{ category.bar_width }}%"` inside a rounded track. Reaching for SVG there would have been ceremony.

## Responsiveness (PRD §9.6, NFR06)

Mobile-first throughout: single-column layouts expand via `sm:`/`md:`/`lg:` breakpoints (e.g. the dashboard's stat-card grid is `grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6`). The authenticated navbar's desktop links (`hidden md:flex`) collapse into a `<details>`-based dropdown below `md` — no JavaScript, no separate mobile markup to keep in sync (it's the same `<a>` tags, just conditionally visible).

Two elements deliberately **opt out** of shrinking: the dashboard outlook table and the report SVGs sit in `overflow-x-auto` wrappers around a fixed `min-w-[40rem]`/`min-w-[44rem]` canvas. A chart scaled down to a 360px viewport has illegible axis labels; scrolling it sideways *inside its own card* keeps it readable without ever making the page body scroll horizontally.
