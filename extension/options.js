const DEFAULT_BACKEND = "http://localhost:8000";

chrome.storage.sync.get({ backendUrl: DEFAULT_BACKEND }, (items) => {
  document.getElementById("backendUrl").value = items.backendUrl;
});

document.getElementById("save").addEventListener("click", () => {
  const backendUrl = document.getElementById("backendUrl").value.trim() || DEFAULT_BACKEND;
  chrome.storage.sync.set({ backendUrl }, () => {
    const status = document.getElementById("status");
    status.textContent = "Saved.";
    status.className = "status success";
    setTimeout(() => status.classList.add("hidden"), 1500);
  });
});
