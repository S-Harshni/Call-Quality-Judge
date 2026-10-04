'use strict';

const LANG = { en: 'English', hinglish: 'Hinglish', hi: 'Hindi' };
const VNAMES = { zero_shot: 'All-at-once, zero-shot', rubric: 'All-at-once, rubric', few_shot: 'All-at-once, few-shot', per_check: 'One question per check', hybrid: 'Hybrid: rules + LLM' };
const VNAME = k => VNAMES[k.split(':')[0]] || k;
const pctCol = (label, key) => ({ label, key, num: true, format: v => v == null ? '–' : F.pct0(v) });
const norm = t => t.toLowerCase().replace(/[^\p{L}\p{M}\p{N}]+/gu, ' ').trim();  // keeps Devanagari letters and vowel signs

// Highlight the quoted words inside a turn (case and punctuation are ignored, like the evidence check in Python).
function highlight(text, quotes) {
  const el = h('span', {});
  let parts = [text];
  for (const q of quotes) {
    if (!q || norm(q).length < 3) continue;
    const i = text.toLowerCase().indexOf(q.toLowerCase().replace(/[.!?।]+$/, ''));
    if (i < 0) continue;
    const len = q.replace(/[.!?।]+$/, '').length;
    parts = [text.slice(0, i), h('mark', { text: text.slice(i, i + len) }), text.slice(i + len)];
    break;
  }
  el.append(...parts);
  return el;
}

const TABS = {
  'Score a call'(D) {
    const byCheck = Object.fromEntries(D.checks.map(c => [c.id, c]));
    const chat = h('div', { class: 'chat' }), side = h('div', {});
    function show(call) {
      const flags = {};
      // Place each flag on the agent turn that really contains the quote (the model's turn number is sometimes off).
      const where = v => {
        const q = norm(v.quote || ''), has = i => call.turns[i] && call.turns[i].speaker === 'Agent' && norm(call.turns[i].text).includes(q);
        if (!q || has(v.turn)) return v.turn;
        const i = call.turns.findIndex((t, k) => has(k));
        return i >= 0 ? i : v.turn;
      };
      for (const [cid, v] of Object.entries(call.judge)) if (v.fail && where(v) != null) (flags[where(v)] ||= []).push(cid);
      chat.replaceChildren(...call.turns.map((t, i) => {
        const f = flags[i] || [];
        return h('div', { class: `msg ${t.speaker.toLowerCase()}${f.length ? ' flag' : ''}` },
          h('span', { class: 'who', text: `[${i}] ${t.speaker === 'Agent' ? 'Agent (Priya)' : 'Customer'}` }),
          highlight(t.text, f.map(c => call.judge[c].quote)),
          f.length ? h('div', { class: 'flagtag', text: 'Flagged: ' + f.map(c => byCheck[c].name).join(', ') }) : null);
      }));
      const fails = D.checks.filter(c => call.judge[c.id].fail).length;
      const agree = D.checks.filter(c => call.judge[c.id].fail === call.labels[c.id]).length;
      side.replaceChildren(h('div', { class: 'card' },
        h('p', { class: 'sub', text: 'Judge score' }), h('div', { class: 'score', text: `${6 - fails}/6` }),
        h('p', { class: 'sub', text: `Agrees with the reference labels on ${agree} of 6 checks` }),
        h('ul', { class: 'checks' }, D.checks.map(c => {
          const v = call.judge[c.id], ref = call.labels[c.id];
          return h('li', {},
            h('div', { class: 'row1' }, h('span', { text: c.name }), h('span', { class: 'pill ' + (v.fail ? 'fail' : 'pass'), text: v.fail ? 'FAIL' : 'PASS' })),
            v.fail ? h('div', { class: 'why', text: `${where(v) != null ? 'Turn ' + where(v) + ': ' : ''}"${v.quote}"${v.evidence_ok ? '' : ' (quote not found in the call)'}` }) : null,
            h('div', { class: 'ref', text: `Reference: ${ref ? 'fail' : 'pass'}${v.fail === ref ? '' : '  ·  judge disagrees'}` }));
        }))));
    }
    const label = c => `${c.subset === 'injected' ? 'Planted: ' + c.injected.replace('_', ' ') : 'Real call ' + c.id} · ${LANG[c.lang]}`;
    const sel = h('select', { 'aria-label': 'Call', onchange: e => show(D.explorer[+e.target.value]) },
      D.explorer.map((c, i) => h('option', { value: i, text: label(c) })));
    show(D.explorer[0]);
    return section(
      intro(`Pick a call. The judge (${VNAME(D.judge)}, Qwen 2.5 3B) read the whole transcript, scored six checks and copied the exact words behind every FAIL; flagged turns are outlined and the quote is highlighted. "Reference" is the label the judge is measured against.`),
      h('div', { class: 'control' }, 'Call', sel),
      h('div', { class: 'explorer' }, h('div', { class: 'card' }, chat), side));
  },

  'Judge accuracy'(D) {
    const R = D.eval.results, cfgs = Object.keys(R);
    const shown = ['few_shot', 'per_check', 'hybrid'].map(v => cfgs.find(k => k.startsWith(v + ':'))).filter(Boolean);
    const series = shown.map((k, i) => ({ name: VNAME(k), color: [C.baseline, C.model, C.actual][i] }));
    const best = R[D.judge];
    const subsetChecks = subset => D.checks.filter(c => R[cfgs[0]][subset].checks[c.id]);
    const checkRows = subset => subsetChecks(subset).map(c => ({ label: c.name, values: shown.map(k => R[k][subset].checks[c.id].f1 ?? 0) }));
    const tbl = subset => ({ columns: [{ label: 'Check', key: 'check' }, ...cfgs.map(k => pctCol(VNAME(k), k))],
      rows: subsetChecks(subset).map(c => ({ check: c.name, ...Object.fromEntries(cfgs.map(k => [k, R[k][subset].checks[c.id].f1])) })) });
    return section(
      intro(`Five judge designs on the same calls, all with Qwen 2.5 3B on a laptop. ${D.counts.injected} calls have one planted defect each (exact labels, all six checks). On the ${D.counts.real} real calls the judge is scored on compliance and outcome, whose labels come from the agent's code and the simulated customer's true profile. F1 is for catching failures.`),
      tiles([
        ['Macro F1, planted defects', F.pct0(best.injected.macro_f1), VNAME(D.judge)],
        ['Macro F1, real calls', F.pct0(best.real.macro_f1), 'compliance + outcome'],
        ['LLM evidence verified', best.evidence_valid == null ? '–' : F.pct0(best.evidence_valid), 'quote is the agent\'s words'],
        ['Time per call', (best.latency_p50_ms / 1000).toFixed(1) + 's', 'median'],
      ]),
      grid(
        card({ title: 'Catching planted defects', sub: 'F1 per check', legend: series.map(s2 => ({ ...s2, shape: 'box' })), table: tbl('injected') },
          plot => hbars(plot, { rows: checkRows('injected'), series, format: F.pct0, max: 1 })),
        card({ title: 'Real calls', sub: 'F1 per check', legend: series.map(s2 => ({ ...s2, shape: 'box' })), table: tbl('real') },
          plot => hbars(plot, { rows: checkRows('real'), series, format: F.pct0, max: 1 })),
        card({ title: 'All five designs', wide: true, notes: [
            'All-at-once: one prompt scores all six checks. A 3B model mostly answers "pass" for everything.',
            'One question per check: six short prompts. Better, but it over-flags mechanical checks.',
            'Hybrid: code decides language, repeated questions and next step (exact and free); the LLM judges compliance, outcome and tone.'],
          table: { columns: [{ label: 'Design', key: 'name' }, pctCol('Macro F1 planted', 'mi'), pctCol('Macro F1 real', 'mr'),
          pctCol('LLM evidence verified', 'ev'), pctCol('Valid JSON', 'js'), { label: 'p50 s', key: 'ms', num: true, format: v => (v / 1000).toFixed(1) }],
          rows: cfgs.map(k => ({ name: VNAME(k), mi: R[k].injected.macro_f1, mr: R[k].real.macro_f1, ev: R[k].evidence_valid, js: R[k].json_ok, ms: R[k].latency_p50_ms })) } }, null)));
  },

  Insights(D) {
    const I = D.insights;
    const cfgRows = I.fail_rate_by_voice_config.map(r => ({ label: r.voice_config.replace(/:/g, ' · '), values: [r.clean_call_share] }));
    const checkRows = I.fail_rate_by_check.map(r => ({ label: D.checks.find(c => c.id === r.check_id).name, values: [r.judge_fail_rate, r.logged_fail_rate] }));
    return section(
      intro(`What the judge found when it reviewed all ${I.calls} real calls of the voice sales agent: which failures are most common, which agent versions are cleanest, and where it disagrees with the agent's own logs. Computed with SQL (sql/insights.sql) over the verdicts.`),
      grid(
        card({ title: 'How often each check fails', sub: 'Share of calls', legend: [{ name: 'Judge', color: C.actual, shape: 'box' }, { name: 'Agent logs', color: C.baseline, shape: 'box' }],
          table: { columns: [{ label: 'Check', key: 'label' }, pctCol('Judge', 'a'), pctCol('Logs', 'b')], rows: checkRows.map(r => ({ label: r.label, a: r.values[0], b: r.values[1] })) } },
          plot => hbars(plot, { rows: checkRows, series: [{ name: 'Judge', color: C.actual }, { name: 'Logs', color: C.baseline }], format: F.pct0, max: 1 })),
        card({ title: 'Clean calls by agent version', sub: 'Share of calls with no failed check (judge)',
          table: { columns: [{ label: 'Voice agent version', key: 'label' }, pctCol('Clean calls', 'v')], rows: cfgRows.map(r => ({ label: r.label, v: r.values[0] })) } },
          plot => hbars(plot, { rows: cfgRows, series: [{ name: 'Clean calls', color: C.actual }], format: F.pct0, max: 1 })),
        card({ title: 'By customer behaviour', wide: true, table: { columns: [{ label: 'Simulated customer', key: 'behavior' }, pctCol('Checks failed', 'fail_rate'), { label: 'Calls', key: 'calls', num: true }],
          rows: I.fail_rate_by_customer_behavior } }, null),
        card({ title: 'Judge vs agent logs', wide: true, sub: '"Judge only" is either a judge mistake or a problem the logs cannot see',
          table: { columns: [{ label: 'Check', key: 'check_id' }, { label: 'Both fail', key: 'both_fail', num: true }, { label: 'Judge only', key: 'judge_only', num: true }, { label: 'Logs only', key: 'logs_only', num: true }],
            rows: I.judge_vs_logs } }, null)));
  },

  'Rubric & use'(D) {
    return section(
      intro('Six checks a call-centre QA reviewer would score. In the hybrid judge, language, repeated questions and next step are decided by code (callqa/rules.py); compliance, outcome and tone are judged by the LLM with the definitions below, one focused question each. Every LLM FAIL must quote the agent\'s words, and the quote is verified in code.'),
      h('div', { class: 'rubric' }, D.checks.map(c => h('div', { class: 'card' }, h('h3', { text: c.name }), h('p', { class: 'sub', text: c.definition })))),
      h('div', { class: 'card', style: 'margin-top:14px' }, h('h3', { text: 'Run it on your own transcript' }),
        h('p', { class: 'sub', text: 'Write the call as "Agent: ..." / "Customer: ..." lines, then:' }),
        h('pre', { class: 'cmd', text: 'ollama pull qwen2.5:3b\npip install -r requirements.txt\npython -m callqa score examples/hinglish_repeat_question.txt   # hybrid judge by default\npython -m callqa batch data/calls.db   # every call into SQLite' })));
  },
};

(async function main() {
  const D = await (await fetch('data.json')).json();
  document.getElementById('lede').textContent = 'An LLM judge that reviews Hindi, Hinglish and English sales calls on six quality checks and quotes the exact words behind every failure. Measured against hundreds of labelled calls; runs on a laptop with an open-source model.';
  document.getElementById('src').href = D.repo;
  document.getElementById('foot').textContent = `Built by ${D.author}. Calls come from the author's Voice Sales Agent project (simulated customers).`;
  const mainEl = document.getElementById('main'), nav = document.getElementById('tabs');
  const names = Object.keys(TABS), built = {};
  const slug = n => n.toLowerCase().replace(/[^a-z]+/g, '-');
  function open(name) {
    hideTip();
    for (const b of nav.children) b.setAttribute('aria-selected', String(b.textContent === name));
    for (const el of mainEl.children) el.hidden = true;
    built[name] ??= mainEl.appendChild(TABS[name](D));
    built[name].hidden = false;
    history.replaceState(null, '', '#' + slug(name));
    renderAll();
  }
  nav.append(...names.map(n => h('button', { type: 'button', role: 'tab', text: n, onclick: () => open(n) })));
  open(names.find(n => '#' + slug(n) === location.hash) || names[0]);
  let timer;
  addEventListener('resize', () => { clearTimeout(timer); timer = setTimeout(renderAll, 150); });
  const btn = document.getElementById('theme');
  const dark = () => (document.documentElement.dataset.theme || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')) === 'dark';
  btn.textContent = dark() ? 'Light mode' : 'Dark mode';
  btn.addEventListener('click', () => { document.documentElement.dataset.theme = dark() ? 'light' : 'dark'; btn.textContent = dark() ? 'Light mode' : 'Dark mode'; });
})();
