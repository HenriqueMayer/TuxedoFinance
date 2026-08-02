"""One-off Pass A class-string rewriter for the light/dark layout switch.

Walks every .html template in templates/ and applies a list of exact-string
substitutions. Each pair is a literal Tailwind class substring the old
dark-only templates repeat verbatim, mapped to its light+dark dual form.

Run with `uv run python scripts/apply_light_dark.py` from the project root.
Idempotent: applying twice is a no-op, because no `new` value contains any
of the `old` values as a substring (verified manually).
"""
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / 'templates'

REPLACEMENTS = [
    # ----------------------------------------------------------------
    # Primary (gradient) button
    # ----------------------------------------------------------------
    (
        'inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-indigo-500 via-violet-500 to-fuchsia-500 px-4 py-2.5 text-sm font-semibold text-white shadow-lg shadow-indigo-500/20 transition hover:opacity-90 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 focus:ring-offset-slate-950',
        'inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-indigo-500 via-violet-500 to-fuchsia-500 px-4 py-2.5 text-sm font-semibold text-white shadow-lg shadow-indigo-500/20 transition hover:opacity-90 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 focus:ring-offset-slate-50 dark:shadow-indigo-500/10 dark:focus:ring-offset-[#2B2B2B]',
    ),
    # Full-width primary button (login/signup cards)
    (
        'inline-flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-indigo-500 via-violet-500 to-fuchsia-500 px-4 py-2.5 text-sm font-semibold text-white shadow-lg shadow-indigo-500/20 transition hover:opacity-90 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 focus:ring-offset-slate-950',
        'inline-flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-indigo-500 via-violet-500 to-fuchsia-500 px-4 py-2.5 text-sm font-semibold text-white shadow-lg shadow-indigo-500/20 transition hover:opacity-90 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 focus:ring-offset-slate-50 dark:shadow-indigo-500/10 dark:focus:ring-offset-[#2B2B2B]',
    ),
    # ----------------------------------------------------------------
    # Secondary button
    # ----------------------------------------------------------------
    (
        'inline-flex items-center gap-2 rounded-xl border border-slate-700 bg-slate-900/60 px-4 py-2.5 text-sm font-medium text-slate-200 transition hover:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 focus:ring-offset-slate-950',
        'inline-flex items-center gap-2 rounded-xl border border-slate-300 dark:border-[#323232] bg-white dark:bg-[#313335] px-4 py-2.5 text-sm font-medium text-slate-700 dark:text-neutral-200 transition hover:bg-slate-100 dark:hover:bg-[#3a3a3a] focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 focus:ring-offset-slate-50 dark:focus:ring-offset-[#2B2B2B]',
    ),
    # ----------------------------------------------------------------
    # Destructive button
    # ----------------------------------------------------------------
    (
        'inline-flex items-center gap-2 rounded-xl bg-rose-500/10 px-4 py-2.5 text-sm font-semibold text-rose-400 ring-1 ring-inset ring-rose-500/30 transition hover:bg-rose-500/20 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 focus:ring-offset-slate-950',
        'inline-flex items-center gap-2 rounded-xl bg-rose-500/10 dark:bg-rose-500/15 px-4 py-2.5 text-sm font-semibold text-rose-600 dark:text-rose-400 ring-1 ring-inset ring-rose-500/30 transition hover:bg-rose-500/20 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 focus:ring-offset-slate-50 dark:focus:ring-offset-[#2B2B2B]',
    ),
    # ----------------------------------------------------------------
    # Card surface — canonical `rounded-2xl` panel with old dark surface.
    # The various `p-5`/`p-6`/`p-4` suffixes ride along untouched.
    # ----------------------------------------------------------------
    (
        'rounded-2xl border border-slate-800 bg-slate-900/60',
        'rounded-2xl ring-1 ring-slate-200 dark:ring-[#323232] bg-white dark:bg-[#313335]',
    ),
    # Final CTA banner keeps its gradient tint, just swaps the edge.
    (
        'rounded-2xl border border-slate-800 bg-gradient-to-r from-indigo-500/10 via-violet-500/10 to-fuchsia-500/10',
        'rounded-2xl ring-1 ring-slate-200 dark:ring-[#323232] bg-gradient-to-r from-indigo-500/10 via-violet-500/10 to-fuchsia-500/10',
    ),
    # Payments form billing-cycle inset (was a slate-950 recessed panel).
    (
        'rounded-xl border border-slate-800 bg-slate-950/40 p-4',
        'rounded-xl ring-1 ring-slate-200 dark:ring-[#323232] bg-slate-100 dark:bg-[#262626] p-4',
    ),
    # Transactions form is_fixed block.
    (
        'rounded-xl border border-slate-800 bg-slate-900/40 p-4',
        'rounded-xl ring-1 ring-slate-200 dark:ring-[#323232] bg-slate-100 dark:bg-[#292929] p-4',
    ),
    # ----------------------------------------------------------------
    # Text color ladder — every screen swaps to its dark-variant pair.
    # ----------------------------------------------------------------
    ('text-slate-100', 'text-slate-900 dark:text-neutral-100'),
    ('text-slate-200', 'text-slate-800 dark:text-neutral-200'),
    ('text-slate-300', 'text-slate-700 dark:text-neutral-300'),
    # `text-slate-400` and `text-slate-500` already read acceptably on both
    # themes, but rebalance the dark variants for Darcula's warmer neutrals.
    ('text-slate-400', 'text-slate-600 dark:text-neutral-400'),
    ('text-slate-500', 'text-slate-500 dark:text-neutral-500'),
    # ----------------------------------------------------------------
    # Borders & dividers
    # ----------------------------------------------------------------
    ('border-slate-800', 'border-slate-200 dark:border-[#323232]'),
    ('divide-slate-800', 'divide-slate-200 dark:divide-[#323232]'),
    # Reused "Now" badge on the dashboard outlook + "Fixed" etc. badges.
    ('border-slate-700 px-2.5 py-0.5', 'border-slate-300 dark:border-[#3a3a3a] px-2.5 py-0.5'),
    # Selected row highlight in the outlook table.
    ('bg-slate-800/40', 'bg-slate-100 dark:bg-[#3a3a3a]/40'),
    # Empty-state icon tile background.
    ('bg-slate-800/60 text-slate-500', 'bg-slate-200 text-slate-500 dark:bg-[#3a3a3a]/60 dark:text-neutral-400'),
    # ----------------------------------------------------------------
    # Semantic indicators — bold dual-class form so light uses -600
    # (slate-50/white background contrast) and dark keeps the -400 they
    # already had. Badges get a slightly denser tint in dark.
    # ----------------------------------------------------------------
    ('text-emerald-400', 'text-emerald-600 dark:text-emerald-400'),
    ('text-rose-400', 'text-rose-600 dark:text-rose-400'),
    ('text-amber-400', 'text-amber-600 dark:text-amber-400'),
    ('bg-emerald-500/10 text-emerald-600 dark:text-emerald-400',
     'bg-emerald-500/10 dark:bg-emerald-500/15 text-emerald-700 dark:text-emerald-400'),
    ('bg-rose-500/10 text-rose-600 dark:text-rose-400',
     'bg-rose-500/10 dark:bg-rose-500/15 text-rose-700 dark:text-rose-400'),
    ('bg-amber-500/10 text-amber-600 dark:text-amber-400',
     'bg-amber-500/10 dark:bg-amber-500/15 text-amber-700 dark:text-amber-400'),
    # Indigo text and badge used for "Billed <date>" + nav links.
    ('text-indigo-400', 'text-indigo-600 dark:text-indigo-400'),
    ('text-indigo-300', 'text-indigo-600 dark:text-indigo-300'),
    # Indigo Billed badge (ring + bg + text).
    ('border-indigo-500/30 bg-indigo-500/10 text-indigo-600 dark:text-indigo-300',
     'border-indigo-500/30 bg-indigo-500/10 dark:bg-indigo-500/15 text-indigo-700 dark:text-indigo-300'),
    # Hero badge.
    ('border-indigo-500/30 bg-indigo-500/10 px-3 py-1 text-xs font-medium text-indigo-300',
     'border-indigo-500/30 bg-indigo-500/10 dark:bg-indigo-500/15 px-3 py-1 text-xs font-medium text-indigo-700 dark:text-indigo-300'),
    # ----------------------------------------------------------------
    # SVG paint (reports charts). `fill-*` and `stroke-*` are not touched
    # by the text/border rules above (different prefix), and need their own
    # dual-class form so axis labels read on both white and Darcula.
    # ----------------------------------------------------------------
    ('fill-slate-200', 'fill-slate-800 dark:fill-slate-200'),
    ('fill-slate-300', 'fill-slate-700 dark:fill-slate-300'),
    ('fill-slate-500', 'fill-slate-600 dark:fill-slate-500'),
    ('fill-slate-950', 'fill-white dark:fill-slate-950'),
    # Chart grid lines (faint) and dashed zero line (a touch stronger).
    ('stroke-slate-800', 'stroke-slate-200 dark:stroke-slate-700'),
    ('stroke-slate-600', 'stroke-slate-300 dark:stroke-slate-600'),
]


def main():
    total_files = 0
    total_subs = 0
    for path in TEMPLATES.rglob('*.html'):
        text = path.read_text()
        new_text = text
        file_subs = 0
        for old, new in REPLACEMENTS:
            count = new_text.count(old)
            if count:
                new_text = new_text.replace(old, new)
                file_subs += count
        if new_text != text:
            path.write_text(new_text)
            print(f'  {path.relative_to(ROOT)}: {file_subs} substitutions')
            total_files += 1
            total_subs += file_subs
    print(f'\n{total_files} files updated, {total_subs} class substitutions.')


if __name__ == '__main__':
    sys.exit(main())