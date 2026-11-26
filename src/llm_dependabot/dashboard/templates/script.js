const meta = document.querySelector('meta[name="color-scheme"]');
const systemDark = matchMedia("(prefers-color-scheme: dark)");
document.getElementById("theme").addEventListener("click", () => {
  const system = systemDark.matches ? "dark" : "light";
  const shown = meta.content === "light dark" ? system : meta.content;
  const target = shown === "dark" ? "light" : "dark";
  // Choosing the system's own scheme returns to following the system.
  meta.content = target === system ? "light dark" : target;
  try {
    if (target === system) localStorage.removeItem("color-scheme");
    else localStorage.setItem("color-scheme", target);
  } catch {}
});
addEventListener("storage", (event) => {
  if (event.key === "color-scheme") meta.content = event.newValue ?? "light dark";
});
const filter = document.getElementById("filter");
const runs = [...document.querySelectorAll(".run")];
filter.addEventListener("input", () => {
  const terms = filter.value.toLowerCase().split(/\s+/).filter(Boolean);
  let shown = 0;
  for (const run of runs) {
    const rows = [...run.querySelectorAll("tr[data-search]")];
    let visible = 0;
    for (const row of rows) {
      row.hidden = !terms.every((term) => row.dataset.search.includes(term));
      visible += !row.hidden;
    }
    run.hidden = terms.length > 0 && visible === 0;
    shown += !run.hidden;
  }
  document.getElementById("no-match").hidden = shown > 0;
});
