const softToggle = document.getElementById("soft-toggle");

if (softToggle) {
  softToggle.addEventListener("click", () => {
    const enabled = document.body.classList.toggle("soft-mode");
    softToggle.textContent = enabled ? "恢复默认模式" : "切换柔和模式";
  });
}
