# Visual language

The decisions behind the interface and their reasons. Token values are in
`src/styles.css`; this file explains them. Change it when a decision changes.

## Premise

Tuxedo Finance is a desk in a tuxedo. A dark frame (the jacket) holds the
navigation. A light sheet (the shirt) holds the work. One accent (the bow tie)
marks the one action that matters most, adding an entry. Every financial object
lifts off the sheet into a window.

## Decisions

| Decision    | Rule                                                                                                                                                                                             | Follows from                               |
| ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------ |
| Layout      | Navigation lives on the jacket: a rail on a wide screen, a dock on a phone. The page lives on the sheet, which has one rounded edge against the jacket.                                          | Jacket and shirt                           |
| Color roles | Forest is structure and text. Cream is the work surface. Caramel (`accent`) is used for the Add action and keyboard focus only. Green and red (`positive`, `negative`) are used on amounts only. | One bow tie for each outfit                |
| Type        | Inter, bundled with the client. Amounts use tabular figures (`amount`). The answer to a question is the largest text of its block.                                                               | The product answers questions with numbers |
| Signature   | The window: a title bar with the three macOS lights. Red closes. Green expands to full size. The middle light is inactive, because a window cannot be minimized.                                 | Objects lift off the sheet                 |
| Density     | A list is rows with hairlines on the sheet. A card is used only for an object that opens.                                                                                                        | If it is a card, it opens                  |

## Controls

| Control        | Use                                                                                                   | Class            |
| -------------- | ----------------------------------------------------------------------------------------------------- | ---------------- |
| Primary button | The one action that completes the form or the screen                                                  | `button-primary` |
| Accent button  | Add entry, and the save of an entry                                                                   | `button-accent`  |
| Quiet button   | A second action beside a primary one                                                                  | `button-quiet`   |
| Action         | A small button beside a title, inside a row or inside a card: open, add, undo, remove, import, export | `action`         |
| Link           | Text that leads to another place: another page or a document                                          | `link`           |
| Menu           | The rare actions of a page, behind one "More actions" button: `src/ui/Menu.tsx`                       | `menu-item`      |
| Month control  | The month that a page or a window shows: `src/ui/MonthPicker.tsx`                                     |                  |

An action on the same screen is never underlined text. It is a button, and a
frequent one carries a 16px line icon before its label (after it, for a
chevron that means "more"). A section that opens in place ("Edit goal") is an
`action` on the `summary`, with a mark that turns.

An action that the owner uses a few times a year (import a statement) is not
a button beside the title. It is an item of the menu of its page.

The month control is one piece: a step to each side and, between them, the
month. The month opens the twelve months of a year, "This month" and, where
the page allows it, "All months". No page has a second way to change a month.

A window of settings is a list of rows: the name on the left and a small
control on the right (a segmented choice, or a 32 px select). A currency
select shows the symbol of the chosen currency before its code.

A card that opens a window lifts under the pointer (`card-open`). Cards in one
row have one height.

## Motion

Motion has three jobs here, and nothing moves without one of them.

| Motion                                          | Job                                            | Time                                   |
| ----------------------------------------------- | ---------------------------------------------- | -------------------------------------- |
| A control under the pointer and under the press | Feedback: the control answered                 | 140 ms, and 90 ms for the press        |
| The window from its origin, and the backdrop    | Orientation: where the object came from        | 260 ms in, 180 ms out, 220 ms backdrop |
| The page of a destination                       | Orientation: the frame stays, the page changes | 90 ms out, 200 ms in                   |
| A bar that grows to its value                   | Meaning: the bar is a measure                  | 520 ms                                 |
| A menu or the months, from their control        | Orientation: which control opened the panel    | 140 ms                                 |
| The marks of a chart on a change of period      | Orientation: the same months, new values       | 260 ms                                 |
| A handle of a slider coming to rest on a month  | Feedback: the handle follows, then settles     | 140 ms                                 |

With a reduced-motion preference the page, the bars and the lift of a card do
not move, and the window fades.

## Charts

`src/ui/charts.tsx` draws every chart, in SVG, with no chart library. The
analysis window is the only place with drawn charts. A summary on a page
stays a row with a bar and its value as text.

| Question              | Form                                  | Rule                                                                     |
| --------------------- | ------------------------------------- | ------------------------------------------------------------------------ |
| Amounts of each month | Bars, one for each series             | The bars start at zero                                                   |
| A value at month ends | Lines                                 | The axis says its range; it starts at zero when the values are near zero |
| A ranking             | Rows with a bar and the value as text | Largest first                                                            |
| Parts of one total    | One bar of parts, with a list         | Three parts take a color; the others share one gray                      |

- A series takes its color from the tokens: ink, the bow-tie ink, positive
  and negative. A chart has four colored series at most. A second mark goes
  with a color that carries meaning: a dashed line for a debt or a cost, a
  dashed edge for a month that is not over.
- Every chart has a table with the same values for a screen reader.
- One line above the marks names the series. Under the pointer, or with the
  arrow keys, a label with the values of one month floats above the plot. It
  follows the month and stays above the plot, so it never covers a mark.
- A click or Enter picks a month. A drag, or Shift with an arrow key, selects
  a run of months. Escape, a press outside the chart, a click in the chart or
  the button of the selection ends it; Escape then does not close the window.
  The chart reports both and decides nothing: the window opens the origin of
  a month and asks the server for the figures of a run. The figures of a run
  show under the marks, so the chart keeps its place. With the pointer on the
  selected run, the floating label shows those figures in place of one month.
- A selected run is a soft band behind the marks, in the bow-tie color, with
  round corners and a short grip at each end. The months outside the run step
  back. It has no hard edge.
- A value at month ends is not added over months. A selected run of a line
  chart shows the change from its first month end to its last.
- A chart only draws. Every total, change, average and percentage comes
  calculated from the server.

## The window

`src/ui/Window.tsx` is the only implementation. It is a native modal
`<dialog>`: the browser supplies the focus trap, Escape and the inert page.

- **Address.** The open window is the search parameter `w` of the current
  page. Back closes it, a link reopens it, and the page behind keeps its path,
  filters and scroll position.
- **Motion.** It opens from the clicked element to its frame in 260 ms and
  returns in 180 ms. A second close request during the exit is ignored. With a
  reduced-motion preference both become a 120 ms fade with no travel.
- **Close.** Red light, Escape, a click on the backdrop, or Back. Focus returns
  to the element that opened it.
- **Phone.** The window fills the screen. The expand light is hidden.
- **Wide content.** A window with a wide table (the sheet) opens at full size.
  The green light still restores the size.
- **A window above a window.** A window can hold one window above it, named
  in the search parameter `w2`. It is for a detail of the window below that
  the owner reads and leaves: the origin of a month of the analysis. The
  window below stays open, dimmed, with its state. Back, Escape and the red
  light act on the window above. A link inside the window above takes its
  place, at the same level. There is no third level.

## The slider of a period

`src/ui/RangeSlider.tsx` is two native range inputs on one track. A handle
follows the pointer and comes to rest on the nearest position. The owner sees
where a handle stops in three ways: each position has a dot on the track; the
dot where a moving handle will rest is lit in the bow-tie color, with the
name of its month under it; and the positions of the presets have their
names under the track. A preset is dark while the handles are on it. The
track does not change its length while a handle moves.

## Themes

Light and dark share every role. Dark keeps the forest hue: the jacket is
near-black green and the sheet is dark green. Contrast was calculated for each
text role on its surface (WCAG 2.2 SC 1.4.3) before the tokens were written;
every pair is at least 4.5:1, and control borders are at least 3:1.

## Not decided here

The owner did not review this direction; it was chosen during the overnight run
of 2026-11-10. It keeps the 1.0.0 palette and mark. A different premise needs
only new token values and a new shell layout.
