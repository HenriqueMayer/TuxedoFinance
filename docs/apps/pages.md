# `pages`

The public presentation site — a single landing page. No models, no forms, no authentication required.

## Files

| File | Contents |
|---|---|
| `pages/views.py` | `LandingView(TemplateView)` |
| `pages/urls.py` | `app_name = 'pages'`; one route, `landing` |
| `pages/models.py` | empty — this app has no data |
| `templates/pages/landing.html` | the actual page content |

## View

```python
class LandingView(TemplateView):
    template_name = 'pages/landing.html'
```

Deliberately the simplest possible CBV — no `LoginRequiredMixin` (the landing and authentication entry points are public), no context beyond what `base.html`'s context processors already provide.

## Route

| Path | Name | View |
|---|---|---|
| `/` | `pages:landing` | `LandingView` |

`settings.LOGOUT_REDIRECT_URL = 'pages:landing'` — logging out always lands here.

## Template (`templates/pages/landing.html`)

Extends `base.html`. Five sections, all using the shared design language documented in [frontend.md](../frontend.md):

1. **Hero** — value proposition, a short statement of the spreadsheet frustration that motivated Tuxedo Finance, conditional "Sign up" / "Log in" CTAs (linking to `accounts:signup` / `accounts:login` when `ALLOW_SIGNUPS=True`), and a **sample dashboard preview** built from four `partials/stat_card.html` includes with hardcoded example figures (this is presentation only — the sample figures do not query financial records or require authentication).
2. **Brand story** — the Tuxedo Finance hero image with localized alternative text, served as an optimized static asset with intrinsic dimensions and lazy loading; it is decorative/product storytelling and contains no application data.
3. **How it works** — a static 3-step explanation (Record → Classify → Review), introducing the transaction workflow.
4. **Features** — a 4-card grid (Types & categories, Payment methods, Fixed vs. variable, Consolidated dashboard) using the standard `sm:grid-cols-2 lg:grid-cols-4` indicator-grid pattern with inline SVG icons.
5. **Final CTA banner** — a gradient-tinted panel repeating the conditional Sign up / Log in buttons.
