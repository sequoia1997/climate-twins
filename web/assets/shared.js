// Shared by the Places and Organisms pages: the sliding Places/Organisms switch and the first-visit welcome popup.
document.querySelectorAll(".modes a").forEach(a => a.addEventListener("click", () => { const n = a.parentNode; if (!a.hasAttribute("aria-current")) n.dataset.pos = a === n.lastElementChild ? "1" : "0"; }));
(function () {
  var d = document.getElementById("welcomedlg"); if (!d || !d.showModal) return;
  var K = d.dataset.key, h = d.querySelector("h2");
  var seen = function () { try { return localStorage.getItem(K) === "1"; } catch (e) { return false; } };
  var remember = function () { try { localStorage.setItem(K, "1"); } catch (e) { } };
  d.addEventListener("close", remember);
  document.getElementById("welcomego").addEventListener("click", function () { remember(); d.close(); });
  document.addEventListener("click", function (e) { if (e.target.closest("[data-welcome]")) { e.preventDefault(); d.showModal(); h.focus({ preventScroll: true }); } });
  h.tabIndex = -1; if (!seen()) { d.showModal(); h.focus({ preventScroll: true }); }
})();
