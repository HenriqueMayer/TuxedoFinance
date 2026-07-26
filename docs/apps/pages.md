# `pages`

The public presentation site — a single landing page. No models, no forms, no authentication required.

## Files

| File | Contents |
|---|---|
| `pages/views.py` | `LandingView(TemplateView)` |
| `pages/urls.py` | `app_name = 'pages'`; one route, `landing` |
| `pages/models.py` | empty — this app has no data |
| `pages/tests.py` | 1 test |
| `templates/pages/landing.html` | the actual page content |

## View

```python
class LandingView(TemplateView):
    template_name = 'pages/landing.html'
```

Deliberately the simplest possible CBV — no `LoginRequiredMixin` (this is the one screen in the project that must be reachable by anonymous visitors), no context beyond what `base.html`'s context processors already provide.

## Route

| Path | Name | View |
|---|---|---|
| `/` | `pages:landing` | `LandingView` |

`settings.LOGOUT_REDIRECT_URL = 'pages:landing'` — logging out always lands here.

## Template (`templates/pages/landing.html`)

Extends `base.html`. Four sections, all built from the standard design-system components documented in [frontend.md](../frontend.md) — no one-off markup:

1. **Hero** — value proposition copy, "Sign up" / "Log in" CTAs (linking to `accounts:signup` / `accounts:login`), and a **sample dashboard preview** built from four `partials/stat_card.html` includes with hardcoded example figures (this is presentation only — it does not query the database or require authentication).
2. **How it works** — a static 3-step explanation (Record → Classify → Review), mirroring PRD §3 (Purpose).
3. **Features** — a 4-card grid (Types & categories, Payment methods, Fixed vs. variable, Consolidated dashboard) using the standard `sm:grid-cols-2 lg:grid-cols-4` indicator-grid pattern with inline SVG icons.
4. **Final CTA banner** — a gradient-tinted panel repeating the Sign up / Log in buttons.

## Tests (`pages/tests.py`)

One test: `LandingViewTests.test_landing_page_is_public` — asserts a `GET /` returns `200` and renders `pages/landing.html` with no authentication. This is the only test in the suite that doesn't touch `LoginRequiredMixin` at all, by design (FR01: the landing page must be reachable without login).
