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

  function scroll() { box.scrollTop = box.scrollHeight; }

  function nearBottom() {
    return box.scrollHeight - box.scrollTop - box.clientHeight < 80;
  }

  /* ── 单条消息复制 ──
     历史消息由模板渲染、新消息由本文件动态追加，所以按钮统一由 JS 注入，
     并用事件委托处理点击，避免漏掉任何一条。 */
  var COPY_ICON = '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h8"/></svg>';
  var COPIED_ICON = '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 6L9 17l-5-5"/></svg>';

  function legacyCopy(text) {
    // 非 HTTPS 后台环境没有 Clipboard API，或 API 因权限 / 窗口未聚焦被拒时走这里
    return new Promise(function (resolve, reject) {
      var ta = document.createElement('textarea');
      ta.value = text;
      ta.setAttribute('readonly', '');
      ta.style.cssText = 'position:fixed;top:0;left:-9999px;opacity:0';
      document.body.appendChild(ta);
      ta.select();
      var ok = false;
      try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
      document.body.removeChild(ta);
      ok ? resolve() : reject(new Error('copy failed'));
    });
  }

  function copyToClipboard(text) {
    if (navigator.clipboard && navigator.clipboard.writeText && window.isSecureContext) {
      // 写失败（权限、窗口未聚焦等）时不能就此报失败，再试一次老办法
      return navigator.clipboard.writeText(text).catch(function () {
        return legacyCopy(text);
      });
    }
    return legacyCopy(text);
  }

  function messageText(row) {
    var bubble = row.querySelector('.ai-bubble');
    if (!bubble) return '';
    var clone = bubble.cloneNode(true);
    // 待确认气泡里的「执行 / 取消」不是消息正文；推理过程在 row 上，本来就不在气泡内
    var junk = clone.querySelectorAll('.ai-pending-actions, .ai-status, .ai-dots, .ai-wait');
    for (var i = 0; i < junk.length; i++) {
      if (junk[i].parentNode) junk[i].parentNode.removeChild(junk[i]);
    }
    return clone.textContent.replace(/\n{3,}/g, '\n\n').trim();
  }

  function makeCopyButton() {
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'ai-copy';
    btn.setAttribute('aria-label', '复制这条消息');
    btn.title = '复制这条消息';
    btn.innerHTML = COPY_ICON;
    return btn;
  }

  function decorate(row) {
    if (!row || !row.classList || !row.classList.contains('ai-row')) return;
    if (row.querySelector('.ai-copy')) return;
    var bubble = row.querySelector('.ai-bubble');
    // 流式输出期间不显示按钮，避免复制到半截回复
    if (!bubble || row.classList.contains('ai-live') || bubble.classList.contains('ai-bubble-live')) return;
    var line = document.createElement('div');
    line.className = 'ai-line';
    row.insertBefore(line, bubble);
    var btn = makeCopyButton();
    if (row.classList.contains('ai-row-user')) {
      // 用户气泡靠右，按钮放气泡左侧
      line.appendChild(btn);
      line.appendChild(bubble);
    } else {
      // AI 气泡靠左，按钮放气泡右侧
      line.appendChild(bubble);
      line.appendChild(btn);
    }
  }

  // 流式回复结束：摘掉 live 标记（同时清掉打字光标），再补上复制按钮
  function finishLive(row) {
    if (!row || !row.parentNode) return;
    row.classList.remove('ai-live');
    var bubble = row.querySelector('.ai-bubble-live');
    if (bubble) bubble.classList.remove('ai-bubble-live');
    decorate(row);
  }

  box.addEventListener('click', function (e) {
    var btn = e.target && e.target.closest ? e.target.closest('.ai-copy') : null;
    if (!btn || !box.contains(btn)) return;
    var row = btn.closest('.ai-row');
    var text = row ? messageText(row) : '';
    if (!text) return;
    copyToClipboard(text).then(function () {
      btn.innerHTML = COPIED_ICON;
      btn.className = 'ai-copy is-copied';
      btn.setAttribute('aria-label', '已复制');
      btn.title = '已复制';
      setTimeout(function () {
        btn.innerHTML = COPY_ICON;
        btn.className = 'ai-copy';
        btn.setAttribute('aria-label', '复制这条消息');
        btn.title = '复制这条消息';
      }, 1500);
    }).catch(function () {
      btn.title = '复制失败，请手动选择文本';
      btn.setAttribute('aria-label', '复制失败，请手动选择文本');
      setTimeout(function () {
        btn.title = '复制这条消息';
        btn.setAttribute('aria-label', '复制这条消息');
      }, 2000);
    });
  });

  var rows = box.querySelectorAll('.ai-row');
  for (var ri = 0; ri < rows.length; ri++) decorate(rows[ri]);
  if (window.MutationObserver) {
    var copyObserver = new MutationObserver(function (records) {
      records.forEach(function (rec) {
        rec.addedNodes.forEach(function (node) {
          if (node.nodeType === 1 && node.classList && node.classList.contains('ai-row')) {
            decorate(node);
          }
        });
      });
    });
    copyObserver.observe(box, { childList: true });
  }

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
    bubble.className = 'ai-bubble ai-bubble-assistant ai-bubble-live';
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
        finishLive(row);
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

  // ── SSE：逐行解析 event/data ─────────────────────────────
  function consumeSSE(resp, onEvent) {
    var reader = resp.body.getReader();
    var decoder = new TextDecoder('utf-8');
    var buffer = '';
    function pump() {
      return reader.read().then(function (res) {
        if (res.done) return;
        buffer += decoder.decode(res.value, { stream: true });
        var idx;
        while ((idx = buffer.indexOf('\n\n')) !== -1) {
          var chunk = buffer.slice(0, idx);
          buffer = buffer.slice(idx + 2);
          var name = 'message';
          var data = '';
          chunk.split('\n').forEach(function (line) {
            if (line.indexOf('event:') === 0) name = line.slice(6).trim();
            else if (line.indexOf('data:') === 0) data += line.slice(5).trim();
          });
          if (!data) continue;
          var payload = null;
          try { payload = JSON.parse(data); } catch (err) { payload = null; }
          if (payload) onEvent(name, payload);
        }
        return pump();
      });
    }
    return pump();
  }

  function liveRow() {
    var row = makeRow('assistant');
    row.className += ' ai-live';

    var details = document.createElement('details');
    details.className = 'ai-reasoning ai-reasoning-live';
    details.open = true;
    var summary = document.createElement('summary');
    summary.textContent = '推理过程（推理中…）';
    var rbody = document.createElement('div');
    rbody.className = 'ai-reasoning-body';
    details.appendChild(summary);
    details.appendChild(rbody);
    row.appendChild(details);

    var status = document.createElement('div');
    status.className = 'ai-status';
    status.innerHTML = '<span class="ai-dots"><i></i><i></i><i></i></span>' +
      '<span class="ai-status-text">正在思考</span><span class="ai-wait">0.0s</span>';
    row.appendChild(status);

    var bubble = document.createElement('div');
    bubble.className = 'ai-bubble ai-bubble-assistant ai-bubble-live';
    bubble.style.display = 'none';
    row.appendChild(bubble);

    box.appendChild(row);
    scroll();

    var started = Date.now();
    var wait = status.querySelector('.ai-wait');
    var timer = setInterval(function () {
      wait.textContent = ((Date.now() - started) / 1000).toFixed(1) + 's';
    }, 100);

    var state = {
      row: row,
      details: details,
      summary: summary,
      rbody: rbody,
      status: status,
      statusText: status.querySelector('.ai-status-text'),
      bubble: bubble,
      answer: '',
      reasoning: '',
      toolMode: false,
      settled: false,
    };

    state.stop = function () {
      clearInterval(timer);
      if (state.status && state.status.parentNode) state.status.parentNode.removeChild(state.status);
      state.status = null;
    };
    state.setStatus = function (text) {
      if (state.statusText) state.statusText.textContent = text;
    };
    state.pushReasoning = function (piece) {
      state.reasoning += piece;
      details.style.display = '';
      rbody.textContent = state.reasoning;
      if (state.status) state.setStatus('正在推理');
      if (nearBottom()) scroll();
    };
    state.pushContent = function (piece) {
      state.answer += piece;
      state.bubble.style.display = '';
      state.bubble.textContent = state.answer;
      if (state.details.open) {
        state.details.open = false;
        state.summary.textContent = '推理过程（已完成）';
      }
      if (nearBottom()) scroll();
    };
    state.discard = function () {
      state.answer = '';
      state.toolMode = true;
      state.bubble.textContent = '';
      state.bubble.style.display = 'none';
    };
    state.finish = function (reply, meta) {
      state.stop();
      state.settled = true;
      if (state.reasoning) {
        state.details.open = false;
        state.summary.textContent = '推理过程';
      } else if (state.details.parentNode) {
        state.details.parentNode.removeChild(state.details);
      }
      var text = String(reply || '').trim();
      if (text) {
        state.bubble.textContent = text;
        state.bubble.style.display = '';
      } else if (!state.toolMode) {
        state.bubble.textContent = '（模型没有返回内容）';
        state.bubble.style.display = '';
      }
      var line = metaText(meta);
      if (line) {
        var metaRow = document.createElement('div');
        metaRow.className = 'ai-meta-row';
        metaRow.textContent = line;
        state.row.appendChild(metaRow);
      }
      scroll();
      finishLive(state.row);
    };
    state.fail = function (message) {
      state.stop();
      state.settled = true;
      state.bubble.style.display = '';
      state.bubble.textContent = message;
      scroll();
      finishLive(state.row);
    };
    return state;
  }

  function streamSend(text) {
    var live = liveRow();
    fetch(urls.chatStream, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ conversation_id: conv, message: text })
    })
      .then(function (resp) {
        if (!resp.ok) {
          return resp.json().catch(function () { return {}; }).then(function (d) {
            throw new Error(d.error || ('HTTP ' + resp.status));
          });
        }
        return consumeSSE(resp, function (name, payload) {
          if (name === 'start' && payload.conversation_id) {
            conv = payload.conversation_id;
          } else if (name === 'reasoning') {
            live.pushReasoning(payload.t || '');
          } else if (name === 'content') {
            live.pushContent(payload.t || '');
          } else if (name === 'discard') {
            live.discard();
          } else if (name === 'tool') {
            add('tool', payload.text || '已执行');
            if (live.row.parentNode) box.appendChild(live.row);
            scroll();
          } else if (name === 'pending') {
            if (live.row.parentNode) live.row.parentNode.removeChild(live.row);
            live.stop();
            addPending(payload);
          } else if (name === 'done') {
            live.finish(payload.reply, payload.meta);
          } else if (name === 'error') {
            live.fail(payload.message || 'AI 请求失败');
          }
        });
      })
      .catch(function (err) {
        if (!live.settled) live.fail('请求失败：' + (err && err.message ? err.message : err));
      })
      .then(function () {
        setBusy(false);
        input.focus();
      });
  }

  function legacySend(text) {
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
    var timer = setInterval(function () {
      wait.textContent = ((Date.now() - started) / 1000).toFixed(1) + 's';
    }, 100);

    fetch(urls.chat, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ conversation_id: conv, message: text })
    })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        clearInterval(timer);
        if (row.parentNode) row.parentNode.removeChild(row);
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
        clearInterval(timer);
        if (row.parentNode) row.parentNode.removeChild(row);
        add('assistant', '请求失败：' + err);
      })
      .then(function () {
        setBusy(false);
        input.focus();
      });
  }

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    if (busy) return;
    var text = input.value.trim();
    if (!text) return;
    input.value = '';
    add('user', text);
    setBusy(true);
    if (urls.chatStream && window.fetch && window.TextDecoder) {
      streamSend(text);
    } else {
      legacySend(text);
    }
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
