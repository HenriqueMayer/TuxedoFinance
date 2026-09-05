# `pages`

A public product overview at `/`, named `pages:landing`, rendered by
`LandingView(TemplateView)`. The app has no models or forms and queries no
financial records. The shared shell supplies presentation context and the
appropriate public or authenticated navigation.

## Content and layout

The homepage contains two sections:

1. **Introduction:** Tuxedo Finance, one factual description, access links, and
   the existing horizontal cat photograph, shown in full without stretching.
   A double rounded frame uses thin forest/cream borders, a translucent glass
   mat, and a subtle caramel ambient glow. The frame is 4:3 on mobile and 16:10
   from `sm` upward; the photograph keeps its native 2814:1536 ratio inside it.
   Padding accommodates a gentle 1.02 hover zoom without clipping the image;
   reduced-motion preferences disable that animation. Text and image sit side
   by side at desktop widths and stack with text first on smaller screens.
2. **Features:** six definition-list rows separated by subtle lines, covering
   transactions/categories, accounts/cards, recurrences/installments,
   investments, reports, and salary planning. Investment operations are
   described separately from income and expenses.

The page copy contains no invented balances, promotional cards, motivational slogans,
repeated final call to action, or timing promises. The shared footer retains
brand and copyright without its former slogan.

## Access and localization

Visitors see Log in and, only when `ALLOW_SIGNUPS=True`, Create account.
Authenticated users see Open dashboard. Signup enforcement remains in the
accounts view. Logging out still redirects here.

All fixed copy and the image alternative text are translated in English and
Brazilian Portuguese. Both themes use the shared design system; the light
palette is unchanged and the dark theme uses black/graphite foundations.
Navigation and access links work without JavaScript.
