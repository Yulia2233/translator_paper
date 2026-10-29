(() => {
  'use strict';
  const meta = document.getElementById('paper-question-meta');
  if (!meta) return;
  const paper = JSON.parse(meta.textContent);
  const storageKey = `paper-questions:${paper.source_sha256}:${paper.id}`;
  const panel = document.createElement('aside');
  panel.className = 'question-panel';
  panel.innerHTML = `<details open><summary>选文提问 · 问题与回答</summary>
    <p>选中正文或导读中的文字，点击“标注问题”。提交后，在聊天中告诉 agent“回答问题”；答案写回后点击刷新。</p>
    <button type="button" data-act="select">标注问题</button>
    <blockquote class="selected-quote">尚未选中文字</blockquote>
    <label>你的问题<textarea rows="3" maxlength="4000" placeholder="这段话是什么意思？为什么这样设计？"></textarea></label>
    <div class="question-actions"><button type="button" data-act="submit">提交问题</button><button type="button" data-act="refresh">刷新问题与回答</button><button type="button" data-act="export">导出未提交问题</button></div>
    <p class="question-status" role="status" aria-live="polite"></p><div class="question-list"></div></details>`;
  document.querySelector('main').prepend(panel);
  const status = panel.querySelector('.question-status');
  const textarea = panel.querySelector('textarea');
  let selected = null, token = null, saved = [], drafts = [];
  const quick = document.createElement('button'); quick.type='button'; quick.className='question-quick'; quick.textContent='标注所选文字'; quick.hidden=true; document.body.append(quick);
  function tell(s) { status.textContent = s; }
  try { drafts = JSON.parse(localStorage.getItem(storageKey) || '[]'); if (!Array.isArray(drafts)) drafts = []; } catch (_) { tell('无法读取浏览器草稿，请使用导出功能备份问题。'); }
  function persist() { try { localStorage.setItem(storageKey, JSON.stringify(drafts)); } catch (_) { tell('浏览器无法保存草稿，请导出问题文件。'); } }
  function render() {
    const list = panel.querySelector('.question-list'); list.replaceChildren();
    const all = [...saved, ...drafts.filter(q => !saved.some(s => s.id === q.id))];
    for (const q of all) {
      const item = document.createElement('section'); item.className = 'question-item';
      const heading = document.createElement('strong'); heading.textContent = `${q.page ? '原文第 '+q.page+' 页' : '论文导读'} · ${q.status === 'answered' ? '已回答' : saved.some(s => s.id === q.id) ? '已提交，等待回答' : '未提交草稿'}`;
      const quote = document.createElement('blockquote'); quote.textContent = q.quote;
      const question = document.createElement('p'); question.textContent = '问题：' + q.question;
      item.append(heading, quote, question);
      if (q.answer) { const answer = document.createElement('div'); answer.className = 'question-answer'; answer.textContent = '回答：\n' + q.answer; item.append(answer); }
      if (q.page) { const link = document.createElement('a'); link.href = '#page-'+q.page; link.textContent = '定位原页'; item.append(link); }
      if (!saved.some(s => s.id === q.id)) {
        const retry = document.createElement('button'); retry.textContent = '重试提交'; retry.onclick = () => submit(q); item.append(retry);
      }
      list.append(item);
    }
  }
  async function refresh() {
    if (location.protocol === 'file:') { tell('离线模式：问题保存在浏览器草稿中。请导出问题文件放到资料库目录，或发给 agent，再说“回答问题”。自动提交请通过本地阅读服务打开。'); render(); return false; }
    try {
      const res = await fetch('../api/questions?paper='+encodeURIComponent(paper.id), {cache:'no-store'});
      if (!res.ok) throw new Error('读取失败');
      const data = await res.json(); token = data.token; saved = data.questions;
      drafts = drafts.filter(q => !saved.some(s => s.id === q.id)); persist(); render(); tell('已同步。提交的问题会保存到资料库；回答后点此刷新。'); return true;
    } catch (_) { tell('未连接本地问题服务。草稿仍保留，可导出后交给 agent。'); render(); return false; }
  }
  async function submit(q) {
    if (!token && !await refresh()) return;
    try {
      const res = await fetch('../api/questions', {method:'POST',headers:{'Content-Type':'application/json','X-Reader-Token':token},body:JSON.stringify(q)});
      const data = await res.json(); if (!res.ok) throw new Error(data.error || '提交失败');
      await refresh(); tell('提交成功。现在回到聊天说“回答问题”；agent 回答后，点击“刷新问题与回答”。');
    } catch (err) { tell('提交失败：'+err.message+'。问题草稿已保留，可重试或导出。'); render(); }
  }
  // Capture before toolbar interaction changes the browser selection.
  function capture() {
    const s = window.getSelection(); if (!s || !s.rangeCount || !s.toString().trim()) return;
    const range = s.getRangeAt(0);
    const el = n => n.nodeType === Node.ELEMENT_NODE ? n : n.parentElement;
    const start = el(range.startContainer)?.closest('article[id^="page-"],.intro');
    const end = el(range.endContainer)?.closest('article[id^="page-"],.intro');
    if (!start || start !== end || el(range.startContainer)?.closest('.pagebar,details') || el(range.endContainer)?.closest('.pagebar,details')) return;
    const quote = s.toString().trim(); if (quote.length > 20000) { tell('选文过长，请缩小范围。'); return; }
    const page = start.id.startsWith('page-') ? Number(start.id.slice(5)) : null;
    selected = {quote,page,section:page ? `原文第 ${page} 页` : '四部分论文导读'}; quick.hidden=false;
  }
  document.addEventListener('selectionchange', capture);
  panel.querySelector('[data-act="select"]').onclick = () => {
    capture(); if (!selected) return tell('请先选中同一页正文或导读中的文字。');
    panel.querySelector('.selected-quote').textContent = selected.quote; panel.querySelector('details').open=true; panel.scrollIntoView({block:'center'}); textarea.focus(); quick.hidden=true;
  };
  quick.onclick = () => panel.querySelector('[data-act="select"]').click();
  panel.querySelector('[data-act="submit"]').onclick = async () => {
    if (!selected || !textarea.value.trim()) return tell('请先选中文字并填写问题。');
    const id = globalThis.crypto?.randomUUID?.() || `q-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    const q = {...selected,id,paper_id:paper.id,source_sha256:paper.source_sha256,question:textarea.value.trim(),created_at:new Date().toISOString(),status:'pending',answer:null};
    drafts.push(q); persist(); render(); textarea.value=''; selected=null; panel.querySelector('.selected-quote').textContent='尚未选中文字'; await submit(q);
  };
  panel.querySelector('[data-act="refresh"]').onclick = refresh;
  panel.querySelector('[data-act="export"]').onclick = () => {
    const blob = new Blob([JSON.stringify({schema_version:1,questions:drafts},null,2)],{type:'application/json'});
    const url = URL.createObjectURL(blob); const a=document.createElement('a'); a.href=url;a.download='论文问题-'+paper.id+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
    tell('已导出草稿。请将文件保存到资料库目录或发给 agent，再说“回答问题”。');
  };
  refresh();
})();
