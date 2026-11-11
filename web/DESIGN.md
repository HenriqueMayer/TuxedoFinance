# Visual language

The decisions behind the interface and their reasons. Token values are in
`src/styles.css`; this file explains them. Change it when a decision changes.

## Premise

Tuxedo Finance is a desk in a tuxedo. A dark frame (the jacket) holds the
navigation. A light sheet (the shirt) holds the work. One accent (the bow tie)
marks the one action that matters most, adding an entry. Every financial object
lifts off the sheet into a window.

## Decisions

| Decision    | Rule                                                                                                                                                                                                                                                                                                    | Follows from                               |
| ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------ |
| Layout      | Navigation lives on the jacket: a rail on a wide screen, a dock on a phone. The page lives on the sheet, which has one rounded edge against the jacket.                                                                                                                                                 | Jacket and shirt                           |
| Color roles | Forest is structure and text. Cream is the work surface. Caramel (`accent`) marks one thing at a time: the Add action, keyboard focus, the text of a link, today in a calendar, and the place where a moving handle or a selection is. Green and red (`positive`, `negative`) are used on amounts only. | One bow tie for each outfit                |
| Type        | Inter, bundled with the client. Amounts use tabular figures (`amount`). The answer to a question is the largest text of its block.                                                                                                                                                                      | The product answers questions with numbers |
| Signature   | The window: a title bar with the three macOS lights. Red closes. Green expands to full size. The middle light is inactive, because a window cannot be minimized.                                                                                                                                        | Objects lift off the sheet                 |
| Density     | A list is rows with hairlines on the sheet. A card is used only for an object that opens.                                                                                                                                                                                                               | If it is a card, it opens                  |

## Controls

| Control        | Use                                                                                                   | Class            |
| -------------- | ----------------------------------------------------------------------------------------------------- | ---------------- |
| Primary button | The one action that completes the form or the screen                                                  | `button-primary` |
| Accent button  | Add entry, and the save of an entry                                                                   | `button-accent`  |
| Quiet button   | A second action beside a primary one                                                                  | `button-quiet`   |
| Danger button  | The second press of a deletion, after the first press asked                                           | `button-danger`  |
| Action         | A small button beside a title, inside a row or inside a card: open, add, undo, remove, import, export | `action`         |
| Link           | Text that leads to another place: another page or a document                                          | `link`           |
| Menu           | The rare actions of a page, behind one "More actions" button: `src/ui/Menu.tsx`                       | `menu-item`      |
| Month control  | The month that a page or a window shows: `src/ui/MonthPicker.tsx`                                     |                  |

Small parts with one job each: `Segmented` (a choice of two to four values),
`Meter` (a bar that compares an amount with its total), `Field` (a label, a
control and its errors) and `Boundary` (the message of a window that failed
to load), all in `src/ui/`.

An action on the same screen is never underlined text. It is a button, and a
frequent one carries a 16px line icon before its label (after it, for a
chevron that means "more"). A section that opens in place ("Edit goal") is an
`action` on the `summary`, with a mark that turns.

The action that completes a window (save, create, transfer) is at the end
of the form, on the right; a deletion, when there is one, is on the left of
the same row. A form inside a window that adds one row (reserve a balance,
record points, record a rate) keeps its button beside its fields, and a
calculator keeps its button under its fields. An action of a row of a list
(undo, skip, remove) is an `action`, not a full button.

An action that the owner uses a few times a year (import a statement) is not
a button beside the title. It is an item of the menu of its page.

The month control is one piece: a step to each side and, between them, the
month. The month opens the twelve months of a year, "This month" and, where
the page allows it, "All months". A page or a window that changes a month
uses this control; `max` stops it at the last month that has a meaning.

A window of settings is a list of rows: the name on the left and a small
control on the right (a segmented choice, or a 32 px select). A currency
select shows the symbol of the chosen currency before its code.

A card that opens a window lifts under the pointer (`card-open`). Cards in one
row have one height.

## Fields that open a panel

No form shows a list, a calendar or a file control of the browser. Their
looks and their words change with the browser and the system, and a long
list of the browser has no search.

| Field                | Component                             | Panel                                                                                 |
| -------------------- | ------------------------------------- | ------------------------------------------------------------------------------------- |
| One choice of a list | `Select` in `src/ui/Select.tsx`       | The choices under their headings. A list of eight or more has a search box            |
| A date               | `DateField` in `src/ui/DateField.tsx` | One month of days. The name of the month opens the months of the year                 |
| A month              | `MonthField` in the same file         | The months of a year, from `src/ui/Months.tsx`, which the month control also uses     |
| A file               | `FileField` in `src/ui/FileField.tsx` | None: a button and the name of the file, in the language of the interface. For a form |

- `src/ui/Panel.tsx` places every panel. On a wide screen the panel sits
  under its control, or above it without room below. On a phone it is a sheet
  at the bottom of the screen, with its name as the title.
- Escape and a press outside close a panel. Inside a window, Escape closes
  the panel and the window stays.
- A choice of two to four fixed values that the owner compares is a segmented
  control, not a select.
- A name that is an existing one or a new one (the bank of an account, the
  institution of an investment) is `NameChoice` in `src/ui/NameChoice.tsx`:
  a select of the existing names whose last choice opens a field for a new
  name. No field uses the list of the browser (`datalist`).
- A select shows words for "no choice" in two ways: `placeholder` is the text
  before a choice, and the owner cannot return to it; `empty` is a real
  choice at the top of the list.
- The search ignores case and accents, and looks in the name, the second
  line and the heading of a choice.

## A field for an amount

`AmountInput` in `src/ui/AmountInput.tsx` is the field of every amount of
money. It writes the amount as the application shows it: "2000" is "2.000"
while the owner types, and "2.000,00" when the owner leaves the field. The
separators are the owner's choice in Settings: a point for thousands and a
comma for decimals, or the reverse.

- Letters do not enter. Zeros before the first digit leave.
- The two separator keys keep their meaning: one groups the thousands and
  the other starts the decimals, as chosen in Settings. A typed thousands
  separator shows at once and stays where it was typed while the digits after
  it can complete a group of three ("1," then "1,0", "1,00", "1,000"). A
  number left in the middle of a group is its digits: "1,00" with a comma for
  thousands is one hundred.
- Backspace on a thousands separator that the field wrote deletes the digit
  before it. A separator that the owner typed, and the decimal separator, are
  deleted alone. The caret stays beside the character that changed.
- A pasted amount is read with either separator. A typed amount is read by
  the meaning of its keys only: `parseAmount` reads by the format that
  `setNumberFormat` holds.
- A balance can start with a minus sign (`signed`).

A quantity, a unit price, an exchange rate and points are not amounts of
money. They have up to eight decimals and keep a plain field.

The rules are `typedAmount`, `finishedAmount`, `pastedAmount` and
`editableAmount` in
`src/lib/money.ts`. They write text; they calculate nothing.

## Options of a form

An option of a form that is on or off is a chip (`OptionChip` in
`src/ui/OptionChip.tsx`), never a checkbox of the browser: confirm each
invoice payment, confirm each month, archive. A checkbox stays for choosing
rows of a list (the blocks of Home, the rows of an import).

An option that most entries do not use is a chip in view, not a field behind
"More options": repeat every month, pay in installments, add a note. A chip
is a toggle button. When it is on, it is dark and its field opens below it;
when the owner turns it off, the field closes and its value is cleared.

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
| A sheet from the bottom of a phone screen       | Orientation: the panel belongs to its control  | 240 ms                                 |
| A field that an option of a form shows          | Orientation: the field belongs to its option   | 220 ms                                 |

With a reduced-motion preference the page, the bars and the lift of a card do
not move, and the window fades.

## Charts

`src/ui/charts.tsx` draws every chart, in SVG, with no chart library. The
windows of analysis are the only places with drawn charts: the analysis of
a period, the origin of a month and the analysis of one Wallet item. A
summary on a page stays a row with a bar and its value as text.

| Question              | Form                                  | Rule                                                                     |
| --------------------- | ------------------------------------- | ------------------------------------------------------------------------ |
| Amounts of each month | Bars, one for each series             | The bars start at zero                                                   |
| A value at month ends | Lines                                 | The axis says its range; it starts at zero when the values are near zero |
| A ranking             | Rows with a bar and the value as text | Largest first                                                            |
| Parts of one total    | One bar of parts, with a list         | Three parts take a color; the others share one gray                      |

- A series takes its color from the tokens: ink, the bow-tie ink, positive
  and negative. A chart has four colored series at most. Items of one kind
  that are compared (the credit cards) take ink, the bow-tie ink and gray,
  because green and red belong to amounts; more than three items share one
  series with their total. A second mark goes
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

## A long window

A window with several subjects (the analysis) divides them into areas. An
area is a block with a band at the top: a round mark, then the name. A bar
with the names of the areas stays at the top while the window scrolls; a
press goes to an area and the bar marks the one in view. The areas stay on
one page, so that two of them can be read together. Only the content of the
window scrolls. On a phone the bar scrolls sideways and keeps the marked
name in view.

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
- **Wide content.** A window with a wide table or with charts (the sheet, the
  review of an import, the analysis) opens at full size.
  The green light still restores the size.
- **A window above a window.** A window can hold one window above it, named
  in the search parameter `w2`. It is for a detail of the window below that
  the owner reads and leaves: the origin of a month of the analysis, or the
  analysis of an item of the Wallet. The
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
