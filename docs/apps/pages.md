# `pages`

A public product overview at `/`, named `pages:landing`, rendered by
`LandingView(TemplateView)`. The public landing has no models or forms and queries no
financial records. The shared shell supplies presentation context and the
appropriate public or authenticated navigation.

## Content and layout

The homepage contains two sections:

1. **Introduction:** product identity, factual description, access links and the
   approved Paper Layers bow tie. Its five planes reveal a workspace index on
   hover or deliberate click, touch, Enter or Space activation. The index links
   to feature descriptions for visitors and the corresponding workspace for
   authenticated users. The shared `static/js/paper-layers.js` engine handles
   focus, motion preferences and HTMX cleanup; without JavaScript, the static
   illustration and native index links remain visible. Text and illustration
   sit side by side on desktop and stack on smaller screens.
   The headline is “Your finances, made clear.” / “Suas finanças de forma clara.”;
   the restrained underline remains on “clear” / “clara”.
2. **Features:** seven definition-list items separated by subtle lines, covering
   transactions/categories, accounts/cards, recurrences/installments,
   investments, reports, budgets/goals and salary planning. Investment operations are
   described separately from income and expenses.

The page copy contains no invented balances, promotional cards, motivational slogans,
repeated final call to action, or timing promises. The shared footer retains
brand and copyright without its former slogan.

## Access and localization

Visitors see Log in and, only when `ALLOW_SIGNUPS=True`, Create account.
Authenticated users see Open dashboard. Signup enforcement remains in the
accounts view. Logging out still redirects here.

All fixed copy and the illustration's accessible labels are translated in English and
Brazilian Portuguese. Both themes use the shared design system; the light
palette is unchanged and the dark theme uses black/graphite foundations.
Navigation and access links work without JavaScript.

## Shared form rendering

The presentation helper `pages.templatetags.form_ui.form_control` supports the
shared form-field partial across apps. It adds the common `entry-input` style to
ordinary fields while preserving native widget types, values, precision and
error/help associations. Specialized controls retain their own presentation;
model choices are automatically marked for the shared keyboard-search
enhancement. See the
[form contract](../frontend/forms.md#keyboard-and-choice-contract).


## Planned features outside the interface

The feature roadmap lives in [../roadmap.md](../roadmap.md). `/roadmap/` is not
an application route. Navigation and account options contain only available
areas; no disabled Net worth/Import tabs or review badges are shown. Existing
review gates still stop old GET/POST operation URLs before execution, returning
to the owning Dashboard or Transactions workspace. Owned posted import
provenance remains available through its read-only history URLs.
