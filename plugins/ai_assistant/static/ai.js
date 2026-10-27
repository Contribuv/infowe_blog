(function () {
  var urls = window.AI_URLS || {};
  var box = document.getElementById('ai-messages');
  var form = document.getElementById('ai-form');
  var input = document.getElementById('ai-input');
  var sendBtn = document.getElementById('ai-send');
  if (!box || !form || !input || !sendBtn) return;

  var conv = parseInt(box.getAttribute('data-conv') || '0', 10) || 0;
  var busy = false;
  var waitTimer = null;

  function metaText(meta) {
    if (!meta || !meta.model) return '';
    var parts = [meta.model];
    if (meta.elapsed_ms !== undefined && meta.elapsed_ms !== null) parts.push(meta.elapsed_ms + ' ms');
    var total = meta.usage && meta.usage.total_tokens;
    if (total) parts.push(total + ' tokens');
    return parts.join(' · ');
  }

  function scroll() { box.scrollTop = box.scrollHeight; }

  function makeRow(role) {
    var row = document.createElement('div');
    row.className = 'ai-row ai-row-' + role;
    return row;
  }

  function addReasoning(row, text) {
    if (!text) return;
    var details = document.createElement('details');
    details.className = 'ai-reasoning';
    var summary = document.createElement('summary');
    summary.textContent = '推理过程';
    var body = document.createElement('div');
    body.textContent = text;
    details.appendChild(summary);
    details.appendChild(body);
    row.appendChild(details);
  }

  function add(role, text, meta) {
    if (role === 'tool') {
      var line = document.createElement('div');
      line.className = 'ai-tool-row';
      line.textContent = text || '';
      box.appendChild(line);
      scroll();
      return line;
    }
    var row = makeRow(role);
    if (role === 'assistant') addReasoning(row, meta && meta.reasoning);
    var bubble = document.createElement('div');
    bubble.className = 'ai-bubble ai-bubble-' + role;
    bubble.textContent = text || '';
    row.appendChild(bubble);
    var line = metaText(meta);
    if (line) {
      var metaRow = document.createElement('div');
      metaRow.className = 'ai-meta-row';
      metaRow.textContent = line;
      row.appendChild(metaRow);
    }
    box.appendChild(row);
    scroll();
    return row;
  }

  function typeAssistant(text, meta) {
    var row = makeRow('assistant');
    addReasoning(row, meta && meta.reasoning);
    var bubble = document.createElement('div');
    bubble.className = 'ai-bubble ai-bubble-assistant';
    row.appendChild(bubble);
    box.appendChild(row);

    var full = String(text || '');
    var i = 0;
    var step = Math.max(1, Math.ceil(full.length / 120));
    var timer = setInterval(function () {
      i += step;
      bubble.textContent = full.slice(0, i);
      scroll();
      if (i >= full.length) {
        clearInterval(timer);
        bubble.textContent = full;
        var line = metaText(meta);
        if (line) {
          var metaRow = document.createElement('div');
          metaRow.className = 'ai-meta-row';
          metaRow.textContent = line;
          row.appendChild(metaRow);
        }
        scroll();
      }
    }, 16);
    return row;
  }

  function startThinking() {
    var row = makeRow('assistant');
    row.className += ' ai-thinking';
    var bubble = document.createElement('div');
    bubble.className = 'ai-bubble ai-bubble-assistant';
    bubble.innerHTML = '<span class="ai-dots"><i></i><i></i><i></i></span><span>正在思考</span><span class="ai-wait">0.0s</span>';
    row.appendChild(bubble);
    box.appendChild(row);
    scroll();
    var started = Date.now();
    var wait = bubble.querySelector('.ai-wait');
    waitTimer = setInterval(function () {
      wait.textContent = ((Date.now() - started) / 1000).toFixed(1) + 's';
    }, 100);
    return row;
  }

  function stopThinking(row) {
    if (waitTimer) { clearInterval(waitTimer); waitTimer = null; }
    if (row && row.parentNode) row.parentNode.removeChild(row);
  }

  function addPending(p) {
    var row = makeRow('assistant');
    row.className += ' ai-pending';
    row.setAttribute('data-id', p.id);
    var bubble = document.createElement('div');
    bubble.className = 'ai-bubble ai-bubble-assistant';
    var text = document.createElement('div');
    text.className = 'ai-pending-text';
    text.textContent = p.text || ('准备执行：' + p.tool);
    bubble.appendChild(text);

    var actions = document.createElement('div');
    actions.className = 'ai-pending-actions';
    var ok = document.createElement('button');
    ok.type = 'button';
    ok.className = 'btn btn-primary btn-sm';
    ok.textContent = '执行';
    var no = document.createElement('button');
    no.type = 'button';
    no.className = 'btn btn-secondary btn-sm';
    no.textContent = '取消';
    actions.appendChild(ok);
    actions.appendChild(no);
    bubble.appendChild(actions);
    row.appendChild(bubble);

    ok.addEventListener('click', function () {
      actions.innerHTML = '<span class="ai-usage">执行中…</span>';
      fetch(urls.confirm, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: p.id })
      })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          var result = d.result || {};
          actions.innerHTML = '';
          add(result.ok ? 'tool' : 'assistant', result.message || result.error || '已执行');
        })
        .catch(function (err) {
          actions.innerHTML = '';
          add('assistant', '执行失败：' + err);
        });
    });
    no.addEventListener('click', function () {
      actions.innerHTML = '<span class="ai-usage">已取消</span>';
    });

    box.appendChild(row);
    scroll();
  }

  function setBusy(value) {
    busy = value;
    sendBtn.disabled = value;
    sendBtn.textContent = value ? '思考中…' : '发送';
  }

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    if (busy) return;
    var text = input.value.trim();
    if (!text) return;
    input.value = '';
    add('user', text);
    setBusy(true);
    var thinking = startThinking();

    fetch(urls.chat, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ conversation_id: conv, message: text })
    })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        stopThinking(thinking);
        if (d.conversation_id) conv = d.conversation_id;
        if (d.pending) {
          addPending(d.pending);
        } else if (d.reply) {
          typeAssistant(d.reply, d.meta);
        } else if (d.error) {
          add('assistant', d.error, d.meta);
        }
      })
      .catch(function (err) {
        stopThinking(thinking);
        add('assistant', '请求失败：' + err);
      })
      .then(function () {
        setBusy(false);
        input.focus();
      });
  });

  input.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      form.dispatchEvent(new Event('submit', { cancelable: true }));
    }
  });

  var newBtn = document.getElementById('ai-new');
  if (newBtn) {
    newBtn.addEventListener('click', function () {
      fetch(urls.newChat, { method: 'POST' })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (d.conversation_id) location.href = urls.page + '?c=' + d.conversation_id;
        });
    });
  }

  var provider = document.getElementById('ai-provider');
  if (provider) {
    provider.addEventListener('change', function () {
      fetch(urls.provider, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: provider.value })
      })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (d.error) { add('assistant', d.error); return; }
          var opt = provider.options[provider.selectedIndex];
          add('tool', '已切换到 ' + (opt ? opt.textContent : provider.value));
        })
        .catch(function (err) { add('assistant', '切换失败：' + err); });
    });
  }

  Array.prototype.forEach.call(document.querySelectorAll('.ai-conv-del'), function (btn) {
    btn.addEventListener('click', function (e) {
      e.preventDefault();
      e.stopPropagation();
      if (!confirm('删除这个对话？')) return;
      fetch(urls.deleteConv, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: btn.getAttribute('data-id') })
      })
        .then(function (r) { return r.json(); })
        .then(function () {
          var wrap = btn.closest('.ai-conv-wrap');
          var wasActive = wrap && wrap.querySelector('.ai-conv.active');
          if (wrap) wrap.remove();
          if (wasActive) location.href = urls.page;
        })
        .catch(function (err) { add('assistant', '删除失败：' + err); });
    });
  });

  scroll();
})();
