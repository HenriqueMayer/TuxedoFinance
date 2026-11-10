# Visual language

The decisions behind the interface and their reasons. Token values are in
`src/styles.css`; this file explains them. Change it when a decision changes.

## Premise

Tuxedo Finance is a desk in a tuxedo. A dark frame (the jacket) holds the
navigation. A light sheet (the shirt) holds the work. One accent (the bow tie)
marks the one action that matters most, adding an entry. Every financial object
lifts off the sheet into a window.

## Decisions

| Decision | Rule | Follows from |
|---|---|---|
| Layout | Navigation lives on the jacket: a rail on a wide screen, a dock on a phone. The page lives on the sheet, which has one rounded edge against the jacket. | Jacket and shirt |
| Color roles | Forest is structure and text. Cream is the work surface. Caramel (`accent`) is used for the Add action and keyboard focus only. Green and red (`positive`, `negative`) are used on amounts only. | One bow tie for each outfit |
| Type | Inter, bundled with the client. Amounts use tabular figures (`amount`). The answer to a question is the largest text of its block. | The product answers questions with numbers |
| Signature | The window: a title bar with the three macOS lights. Red closes. Green expands to full size. The middle light is inactive, because a window cannot be minimized. | Objects lift off the sheet |
| Density | A list is rows with hairlines on the sheet. A card is used only for an object that opens. | If it is a card, it opens |

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

## Themes

Light and dark share every role. Dark keeps the forest hue: the jacket is
near-black green and the sheet is dark green. Contrast was calculated for each
text role on its surface (WCAG 2.2 SC 1.4.3) before the tokens were written;
every pair is at least 4.5:1, and control borders are at least 3:1.

## Not decided here

The owner did not review this direction; it was chosen during the overnight run
of 2026-11-10. It keeps the 1.0.0 palette and mark. A different premise needs
only new token values and a new shell layout.
