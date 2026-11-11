// Applies the saved theme before the first paint, so the page does not flash.
// The client keeps the same key in src/lib/theme.ts.
(() => {
  var saved = null;
  try {
    saved = localStorage.getItem("tuxedo.theme");
  } catch (_) {}
  var dark =
    saved === "dark" || (saved !== "light" && matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.dataset.theme = dark ? "dark" : "light";
})();
