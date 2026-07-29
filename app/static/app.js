document.addEventListener('click', async (e) => {
  const btn = e.target.closest('[data-copy]');
  if (!btn) return;
  const text = btn.dataset.copy === 'target'
    ? document.querySelector(btn.dataset.target)?.innerText ?? ''
    : btn.dataset.copy;
  try {
    await navigator.clipboard.writeText(text);
    const was = btn.textContent;
    btn.textContent = 'Скопировано';
    setTimeout(() => { btn.textContent = was; }, 1400);
  } catch {
    alert('Не удалось скопировать. Выделите текст вручную.');
  }
});

(function pollRun() {
  const box = document.querySelector('[data-run-poll]');
  if (!box) return;
  const runId = box.dataset.runPoll;
  const stageEl = box.querySelector('[data-stage]');

  const tick = async () => {
    try {
      const r = await fetch(`/api/runs/${runId}/status`);
      if (!r.ok) return;
      const s = await r.json();
      if (stageEl && s.stage) stageEl.textContent = s.stage;
      if (s.status === 'done' || s.status === 'error') {
        location.reload();
        return;
      }
    } catch {  }
    setTimeout(tick, 1500);
  };
  tick();
})();

document.querySelectorAll('[data-phones]').forEach((btn) => {
  btn.addEventListener('click', async () => {
    const r = await fetch(`/api/runs/${btn.dataset.phones}/phones`);
    const { phones } = await r.json();
    await navigator.clipboard.writeText(phones.join('\n'));
    const was = btn.textContent;
    btn.textContent = `Скопировано (${phones.length})`;
    setTimeout(() => { btn.textContent = was; }, 1600);
  });
});
