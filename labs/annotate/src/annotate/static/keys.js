// Keyboard control for the review panel. Plain JavaScript; HTMX does the requests.
(function () {
  "use strict";
  function typing(e) {
    const t = e.target;
    return t && (t.tagName === "TEXTAREA" || t.tagName === "SELECT" || (t.tagName === "INPUT" && t.type === "text") || t.isContentEditable);
  }
  function form() { return document.getElementById("label-form"); }
  function setVerdict(v) {
    const r = form() && form().querySelector('input[name="verdict"][value="' + v + '"]');
    if (r) { r.checked = true; }
  }
  function toggleMode(i) {
    const boxes = form() ? form().querySelectorAll('input[name="modes"]') : [];
    if (boxes[i]) { boxes[i].checked = !boxes[i].checked; setVerdict("fail"); }
  }
  function submit() { const f = form(); if (f) { f.requestSubmit(); } }
  function go(sel) { const a = document.querySelector(sel); if (a) { a.click(); } }
  function toggle(sel) { document.querySelectorAll(sel).forEach(function (el) { el.hidden = !el.hidden; }); }

  document.addEventListener("keydown", function (e) {
    if (e.ctrlKey || e.metaKey || e.altKey) { return; }
    if (typing(e)) {
      if (e.key === "Escape") { e.target.blur(); }
      if (e.key === "Enter" && e.target.id === "new-mode") { e.preventDefault(); submit(); }
      return;
    }
    const k = e.key;
    if (k === "?") { toggle("#help"); return; }
    if (k === "Escape") { document.getElementById("help").hidden = true; return; }
    if (!form()) { return; }
    if (k === "p") { setVerdict("pass"); }
    else if (k === "f") { setVerdict("fail"); }
    else if (k >= "1" && k <= "9") { toggleMode(Number(k) - 1); }
    else if (k === "n") { e.preventDefault(); document.getElementById("note").focus(); }
    else if (k === "m") { e.preventDefault(); setVerdict("fail"); document.getElementById("new-mode").focus(); }
    else if (k === "g") { const g = form().querySelector('input[name="golden"]'); g.checked = !g.checked; }
    else if (k === "Enter" || k === "s") { e.preventDefault(); submit(); }
    else if (k === "j") { go("[data-next]"); }
    else if (k === "k") { go("[data-prev]"); }
    else if (k === "c") { toggle(".context"); }
    else if (k === "t") {
      const all = document.querySelectorAll("details.tool");
      const open = Array.from(all).some(function (d) { return !d.open; });
      all.forEach(function (d) { d.open = open; });
    }
  });
  document.addEventListener("click", function (e) {
    if (e.target.closest("[data-help]")) { toggle("#help"); }
    if (e.target.closest("[data-context]")) { toggle(".context"); }
    if (e.target.id === "help") { e.target.hidden = true; }
  });
})();
