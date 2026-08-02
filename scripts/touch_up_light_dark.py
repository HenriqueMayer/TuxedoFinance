"""Pass B touch-ups for the light/dark layout switch.

Pass A (apply_light_dark.py) caught the inner `text-slate-200` /
`text-indigo-300` substrings inside hover:-prefixed directives and produced
mangled pairs like `hover:text-slate-800 dark:text-neutral-200`, where the
`dark:` variant is no longer hover-gated. This script restores the
hover-gated `dark:hover:` form, fixes the few remaining dark-only surfaces
(footer bg-slate-950, the manual-mobile-menu blues), and re-leans the indigo
badge colors so they read on a white surface too.

Idempotent: each `new` string does not contain any earlier `old` substring.
"""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / 'templates'

REPLACEMENTS = [
    # Mangled dark-after-light hover states from Pass A. The `dark:` variant
    # must take the same `hover:` prefix the light one did — otherwise the
    # dark-mode link settles on its hover color permanently, defeating the
    # hover affordance in dark mode.
    (
        'hover:text-slate-800 dark:text-neutral-200',
        'hover:text-slate-900 dark:hover:text-neutral-200',
    ),
    (
        'hover:text-indigo-600 dark:text-indigo-300',
        'hover:text-indigo-700 dark:hover:text-indigo-300',
    ),
    # Indigo badges ("Billed <date>" on the list, hero pill on landing) start
    # at -300 in the old dark-only design — too pale on a white surface, and
    # Pass A's catch-all only produced a `dark:text-indigo-300` form without
    # promoting light to -700. Re-tune by hand.
    (
        'text-indigo-600 dark:text-indigo-300',
        'text-indigo-700 dark:text-indigo-400',
    ),
    # Dark-only footer bg lingering.
    (
        'border-t border-slate-200 dark:border-[#323232] bg-slate-950',
        'border-t border-slate-200 dark:border-[#323232] bg-white dark:bg-[#2B2B2B]',
    ),
    # Any leftover `hover:bg-slate-800` should also become light/dark.
    (
        'hover:bg-slate-800',
        'hover:bg-slate-100 dark:hover:bg-[#3a3a3a]',
    ),
    # Leftover `border-slate-700 bg-slate-900/60` mobile menu / nav surfaces
    # not covered by Pass A's narrower menu button rule.
    (
        'border-slate-700 bg-slate-900/60',
        'border-slate-300 dark:border-[#323232] bg-white dark:bg-[#313335]',
    ),
    # `bg-slate-900/95` dropdown surfaces (mobile menus, hovered selects).
    (
        'bg-slate-900/95',
        'bg-white dark:bg-[#313335]/95',
    ),
    # `bg-slate-950/80` navbar background not caught by Pass A (the pass
    # rewrites card surfaces, not page chrome). Use white/Darcula pair so the
    # sticky header matches the new page background.
    (
        'bg-slate-950/80',
        'bg-white/80 dark:bg-[#2B2B2B]/80',
    ),
    # `ring-offset-slate-950` focus ring offsets still anchored to the old
    # page background. Needed anywhere a focus ring has an offset.
    (
        'ring-offset-slate-950',
        'ring-offset-slate-50 dark:ring-offset-[#2B2B2B]',
    ),
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
    main()