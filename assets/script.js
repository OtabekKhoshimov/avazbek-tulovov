(function () {
  var btn = document.getElementById("menuBtn"), nav = document.getElementById("nav");
  if (btn && nav) {
    btn.addEventListener("click", function () {
      var open = nav.classList.toggle("open");
      btn.setAttribute("aria-expanded", open ? "true" : "false");
    });
    nav.addEventListener("click", function (e) { if (e.target.tagName === "A") { nav.classList.remove("open"); btn.setAttribute("aria-expanded", "false"); } });
  }
  var header = document.querySelector(".site-header");
  function onScroll() { header && header.classList.toggle("scrolled", window.scrollY > 8); }
  window.addEventListener("scroll", onScroll, { passive: true }); onScroll();
  document.querySelectorAll(".copy-link").forEach(function (b) {
    b.addEventListener("click", function () {
      var url = b.getAttribute("data-url");
      (navigator.clipboard ? navigator.clipboard.writeText(url) : Promise.reject()).then(function () {
        var t = b.textContent; b.textContent = "Nusxalandi ✓"; setTimeout(function () { b.textContent = t; }, 1800);
      }, function () { window.prompt("Havola:", url); });
    });
  });
})();
