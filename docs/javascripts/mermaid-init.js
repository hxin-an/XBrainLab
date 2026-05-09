(function () {
  function convertCodeFences() {
    document
      .querySelectorAll("pre.mermaid > code, pre > code.language-mermaid")
      .forEach(function (code) {
      var pre = code.parentElement;
      if (!pre) {
        return;
      }
      var diagram = document.createElement("div");
      diagram.className = "mermaid";
      diagram.textContent = code.textContent;
      pre.replaceWith(diagram);
      });
  }

  function renderMermaid() {
    if (typeof window.mermaid === "undefined") {
      return;
    }
    convertCodeFences();
    window.mermaid.initialize({
      startOnLoad: false,
      theme: document.body.getAttribute("data-md-color-scheme") === "slate"
        ? "dark"
        : "default",
    });
    window.mermaid.run({ querySelector: ".mermaid" });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", renderMermaid);
  } else {
    renderMermaid();
  }

  if (typeof window.document$ !== "undefined") {
    window.document$.subscribe(renderMermaid);
  }
})();
