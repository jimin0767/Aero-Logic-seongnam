// Initial render
try {
  updateDashboard();
} catch (err) {
  document.body.dataset.dashboardError = err && err.stack ? err.stack : String(err);
  throw err;
}
