(function () {
  var urls = window.AI_URLS || {};
  var box = document.getElementById('ai-messages');
  var form = document.getElementById('ai-form');
  var input = document.getElementById('ai-input');
  var sendBtn = document.getElementById('ai-send');
  if (!box || !form || !input || !sendBtn) return;

  var conv = parseInt(box.getAttribute('data-conv') || '0', 10) || 0;
  var busy = false;

  function metaText(meta) {
    if (!meta || !meta.model) return '';
    var parts = [meta.model];
    if (meta.elapsed_ms !== undefined && meta.elapsed_ms !== null) parts.push(meta.elapsed_ms + ' ms');
    var total = meta.usage && meta.usage.total_tokens;
    if (total) parts.push(total + ' tokens');
    return parts.join(' · ');
  }

  function add(role, text, meta) {
    var div = document.createElement('div');
    div.className = 'ai-msg ai-' + role;
    div.appendChild(document.createTextNode(text || ''));
    var line = metaText(meta);
    if (line) {
      var span = document.createElement('span');
      span.className = 'ai-meta';
      span.textContent = line;
      div.appendChild(span);
    }
    box.appendChild(div);
    box.scrollTop = box.scrollHeight;
    return div;
  }

  function addPending(p) {
    var div = document.createElement('div');
    div.className = 'ai-msg ai-pending';
    div.setAttribute('data-id', p.id);

    var text = document.createElement('div');
    text.className = 'ai-pending-text';
    text.textContent = p.text || ('准备执行：' + p.tool);
    div.appendChild(text);

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
    div.appendChild(actions);

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

    box.appendChild(div);
    box.scrollTop = box.scrollHeight;
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

    fetch(urls.chat, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ conversation_id: conv, message: text })
    })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (d.conversation_id) conv = d.conversation_id;
        if (d.pending) {
          addPending(d.pending);
        } else if (d.reply) {
          add('assistant', d.reply, d.meta);
        } else if (d.error) {
          add('assistant', d.error, d.meta);
        }
      })
      .catch(function (err) {
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
          if (d.error) {
            add('assistant', d.error);
            return;
          }
          var opt = provider.options[provider.selectedIndex];
          add('tool', '已切换到 ' + (opt ? opt.textContent : provider.value));
        })
        .catch(function (err) { add('assistant', '切换失败：' + err); });
    });
  }

  box.scrollTop = box.scrollHeight;
})();
