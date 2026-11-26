// Applies a stored light or dark override before the page renders.
try {
  document.querySelector('meta[name="color-scheme"]').content =
    localStorage.getItem("color-scheme") ?? "light dark";
} catch {}
