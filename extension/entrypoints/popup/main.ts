const runBtn = document.getElementById('run') as HTMLButtonElement;
const statusEl = document.getElementById('status') as HTMLElement;
const outEl = document.getElementById('out') as HTMLElement;

async function showLast() {
  const { lastRun } = await chrome.storage.local.get('lastRun');
  if (lastRun) {
    outEl.textContent = `last run: ${lastRun.at}\n${JSON.stringify(lastRun.summary, null, 2)}`;
  }
}

runBtn.addEventListener('click', async () => {
  runBtn.disabled = true;
  statusEl.textContent = 'Running… (check the service-worker console for details)';
  try {
    const summary = await chrome.runtime.sendMessage({ type: 'run-now' });
    statusEl.textContent = 'Done.';
    outEl.textContent = JSON.stringify(summary, null, 2);
  } catch (e) {
    statusEl.textContent = `Failed: ${String(e)}`;
  } finally {
    runBtn.disabled = false;
  }
});

showLast();
