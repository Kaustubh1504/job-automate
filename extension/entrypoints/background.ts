import '../lib/collectors'; // side-effect: self-register every collector
import { runPoll } from '../lib/poller';

const ALARM = 'poll';
const BASE_MIN = 45; // gentle cadence — intentional for account safety
const JITTER_MIN = 5; // + a few minutes of randomness

// One-shot alarm re-armed after every run, so each interval gets fresh jitter.
function scheduleNext() {
  const minutes = BASE_MIN + Math.random() * JITTER_MIN;
  chrome.alarms.create(ALARM, { delayInMinutes: minutes });
  console.log(`[alarm] next poll in ~${minutes.toFixed(1)} min`);
}

export default defineBackground(() => {
  chrome.runtime.onInstalled.addListener(() => scheduleNext());

  chrome.runtime.onStartup.addListener(async () => {
    if (!(await chrome.alarms.get(ALARM))) scheduleNext();
  });

  chrome.alarms.onAlarm.addListener(async (alarm) => {
    if (alarm.name !== ALARM) return;
    await runPoll();
    scheduleNext(); // re-arm with new jitter
  });

  // Manual "run now" for testing (from the popup button).
  chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
    if (msg?.type === 'run-now') {
      runPoll().then(sendResponse);
      return true; // keep the channel open for the async response
    }
  });
});
