# Public site

The public page of Tuxedo Finance, built with Astro and published as static
files on GitHub Pages. It has one page in English and one in Brazilian
Portuguese. Each page runs the real client inside a window, with the data of
a fictional owner.

## Commands

Run them in `site/`. The build needs the dependencies of `backend/`
(`uv sync`), `web/` (`npm ci`) and `site/` (`npm ci`).

| Command | Result |
|---|---|
| `npm run build` | The whole site in `dist/`: the client in demonstration mode, its data, the pages |
| `npm test` | Checks of `dist/` in a browser, served under the base path |
| `npm run dev` | The pages with reload. The window is empty until one build wrote `public/app/` |
| `npm run pages` | The pages only, with the `public/app/` that exists |
| `npm run preview` | Serves the built `dist/` to look at it, under the base path |

## How the demonstration works

1. `web/` is built with `vite build --mode demo` into `public/app/`. In this
   mode the client reads from `web/src/demo/fetch.ts` in place of the
   network, keeps its address after `#`, and shows a line that says the data
   is fictional.
2. The backend exports the data: `manage.py export_demo` creates one
   fictional owner in an empty temporary database, records about four months
   through the API, and writes the answer of every screen
   (`backend/reports/demo.py`). One file for each language goes to
   `public/app/demo/`.
3. Astro builds the pages. A page stores its language for the client and
   loads `app/index.html` in an `iframe`.

Limits:

- The demonstration is read-only. A request that would change a record is
  refused with a message in the form.
- No rule is written twice: an answer is a recorded one. The one exception is
  the search in Transactions, which filters the recorded rows of the month
  and adds their amounts.
- A calculation that needs the server (a changed sheet, the calculators) is
  refused in the same way.
- The data shows the latest 18th on or before the build. The workflow builds
  again on the 19th of each month.
- `public/app/` is generated and not tracked.

## Design

The decisions follow `web/DESIGN.md`: the same roles, type and mark.

**Premise.** The page is the jacket and the product is the shirt. A visitor
does not read about the application first: the application runs in the first
view, inside its own signature, the window.

| Decision | Rule | Follows from |
|---|---|---|
| First view | One question as the heading, one sentence, then the live product | The product answers that question; showing it is the proof |
| Signature | The demonstration sits in a window with the three lights. The lights are decoration here: this window does not close | Objects lift off the sheet into a window |
| Color roles | The jacket color is the page. Caramel is used for the one main action and for keyboard focus. The reading part is the light sheet with one rounded edge | One bow tie for each outfit |
| Sections | Four places as questions and answers in two columns with hairlines, not as cards | A list is rows with hairlines; a card is for an object that opens |
| Claims | Only what the application does and does not do. No numbers, logos or quotes | No proof of that kind exists |
| Motion | None on the page. The motion is the product's own | The product is the subject |

The page loads no script of its own except one line that stores the language,
no outside resource and no tracker. `npm test` fails when a request leaves
the origin.

The text of the page, in both languages, is in `src/copy.ts`.
