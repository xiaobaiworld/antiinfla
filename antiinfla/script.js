const statusToggle = document.getElementById("status-toggle");
const statusPanel = document.getElementById("status-panel");

if (statusToggle && statusPanel) {
  statusToggle.addEventListener("click", () => {
    statusPanel.classList.toggle("status-active");
    statusPanel.querySelector("p").textContent = statusPanel.classList.contains("status-active")
      ? "Git status"
      : "Working mode";
    statusPanel.querySelector("h2").textContent = statusPanel.classList.contains("status-active")
      ? "Initialization committed"
      : "Ready for implementation";
    statusPanel.querySelector("p + h2 + p").textContent = statusPanel.classList.contains("status-active")
      ? "目录骨架已经就位，下一步可以直接开始补页面和功能。"
      : "你已经有一个清晰、轻量、可直接修改的起点。后续每个功能点都可以继续按 Git 提交推进。";
  });
}
