/**
 * SALEIA — background.js
 * Service Worker da extensão Chrome.
 * Gerencia alarmes, configurações e estado por aba.
 *
 * NOTA TÉCNICA: Este arquivo também atua como proxy de fetch para o content.js.
 * O Service Worker do Google Meet (meetsw.js) bloqueia requisições fetch feitas
 * diretamente por content scripts. A solução é delegar o fetch ao background.js
 * via chrome.runtime.sendMessage({ tipo: 'fetchBackend', url, payload }).
 */

'use strict';

// ─────────────────────────────────────────────
// ESTADO GLOBAL DA EXTENSÃO
// ─────────────────────────────────────────────
let estadoExtensao = {
  ativo: true,
  backendUrl: 'https://api.saleia.app.br',
};

// Estado da captura de áudio (Whisper)
let capturaAtiva = false;
let captaMeetingId = 'default';

// URL canônica do backend — sempre usar esta
const BACKEND_URL_CANONICAL = 'https://api.saleia.app.br';

// ─────────────────────────────────────────────
// INICIALIZAÇÃO — carregar configurações salvas
// ─────────────────────────────────────────────
chrome.runtime.onInstalled.addListener(function () {
  // Força reset da URL canônica (corrige IP direto armazenado)
  chrome.storage.local.set({ saleiaBackendUrl: BACKEND_URL_CANONICAL });
  estadoExtensao.backendUrl = BACKEND_URL_CANONICAL;
  chrome.storage.local.get(['saleiaAtivo'], function (result) {
    if (result.saleiaAtivo === undefined) {
      chrome.storage.local.set({ saleiaAtivo: true });
    }
  });
  console.log('[SALEIA] Extensão instalada/atualizada.');
});

// Corrige URL e restaura o estado ativo/desligado na inicialização do
// service worker (não só no install — MV3 pode reciclar o worker a
// qualquer momento, e sem isso o toggle "API desligada" seria perdido).
chrome.storage.local.get(['saleiaBackendUrl', 'saleiaAtivo'], function (result) {
  // Se estiver com IP direto, corrigir para o domínio canônico
  const stored = result.saleiaBackendUrl || '';
  const urlObsoleta = !stored
    || stored.includes('204.168.180.25')
    || stored.includes('127.0.0.1')
    || stored.includes('api.saleia.com.br');
  if (urlObsoleta) {
    chrome.storage.local.set({ saleiaBackendUrl: BACKEND_URL_CANONICAL });
    estadoExtensao.backendUrl = BACKEND_URL_CANONICAL;
  } else {
    estadoExtensao.backendUrl = stored;
  }
  estadoExtensao.ativo = result.saleiaAtivo !== false;
});

// ─────────────────────────────────────────────
// OUVIR MENSAGENS DO POPUP E CONTENT SCRIPT
// (handler único consolidado para evitar conflitos)
// ─────────────────────────────────────────────
chrome.runtime.onMessage.addListener(function (msg, sender, sendResponse) {

  // Popup → ativar/desativar extensão
  if (msg.tipo === 'setAtivo') {
    estadoExtensao.ativo = msg.valor;
    chrome.storage.local.set({ saleiaAtivo: msg.valor });
    propagarParaMeet({ tipo: 'toggle', valor: msg.valor });
    sendResponse({ ok: true });
  }

  // Popup → mudar URL do backend
  if (msg.tipo === 'setBackendUrl') {
    estadoExtensao.backendUrl = msg.valor;
    chrome.storage.local.set({ saleiaBackendUrl: msg.valor });
    propagarParaMeet({ tipo: 'backendUrl', valor: msg.valor });
    sendResponse({ ok: true });
  }

  // Content script → informar status
  if (msg.tipo === 'status') {
    sendResponse({ ativo: estadoExtensao.ativo, backendUrl: estadoExtensao.backendUrl });
  }

  // ─────────────────────────────────────────────
  // PROXY DE FETCH — contorna bloqueio do meetsw.js
  // O content.js delega o fetch aqui para evitar que o
  // Service Worker do Google Meet intercepte e bloqueie
  // as requisições para o backend SALEIA.
  // ─────────────────────────────────────────────
  if (msg.tipo === 'fetchBackend') {
    const method = (msg.method || 'POST').toUpperCase();
    const options = {
      method: method,
      headers: {
        'Content-Type': 'application/json',
      },
    };

    if (method !== 'GET' && method !== 'HEAD') {
      options.body = JSON.stringify(msg.payload || {});
    }

    fetch(msg.url, options)
      .then(function (res) { return res.json(); })
      .then(function (data) { sendResponse({ ok: true, data: data }); })
      .catch(function (err) { sendResponse({ ok: false, error: err.message }); });
    return true;
  }

  // ─────────────────────────────────────────────
  // CAPTURA DE ÁUDIO — Whisper via tabCapture + offscreen
  // ─────────────────────────────────────────────

  // Content script → iniciar captura de áudio da aba
  if (msg.tipo === 'iniciarCaptura') {
    const tabId = sender.tab ? sender.tab.id : null;
    if (!tabId) { sendResponse({ ok: false, error: 'sem tabId' }); return true; }
    captaMeetingId = msg.meeting_id || 'default';
    handleIniciarCaptura(tabId).then(sendResponse).catch(function (e) {
      sendResponse({ ok: false, error: e.message });
    });
    return true;
  }

  // Content script → parar captura
  if (msg.tipo === 'pararCaptura') {
    chrome.runtime.sendMessage({ tipo: 'pararGravacaoOffscreen' }, function () {
      capturaAtiva = false;
      chrome.offscreen.closeDocument().catch(function () {});
      sendResponse({ ok: true });
    });
    return true;
  }

  // Content.js → chunk de áudio do microfone via MediaRecorder (rota direta sem offscreen)
  if (msg.tipo === 'whisperChunk') {
    const url = (msg.backendUrl || estadoExtensao.backendUrl) + '/audio-transcricao';
    fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        audio_base64: msg.audio_base64,
        mime_type: msg.mime_type,
        meeting_id: msg.meeting_id || 'default',
      }),
    })
      .then(function (res) { return res.json(); })
      .then(function (data) { sendResponse(data); })
      .catch(function (err) {
        console.warn('[SALEIA] whisperChunk erro:', err.message);
        sendResponse({ ok: false, error: err.message });
      });
    return true; // resposta assíncrona
  }

  // Offscreen → chunk de áudio pronto para enviar ao Whisper
  if (msg.tipo === 'audioChunk') {
    const url = estadoExtensao.backendUrl + '/audio-transcricao';
    fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        audio_base64: msg.base64,
        mime_type: msg.mimeType,
        meeting_id: captaMeetingId,
      }),
    })
      .then(function (res) { return res.json(); })
      .then(function (data) {
        if (data.texto && data.texto.trim()) {
          // Envia texto transcrito para o content.js da aba do Meet
          chrome.tabs.query({ url: 'https://meet.google.com/*' }, function (tabs) {
            tabs.forEach(function (tab) {
              chrome.tabs.sendMessage(tab.id, { tipo: 'transcricaoAudio', texto: data.texto.trim() }, function () {
                if (chrome.runtime.lastError) { /* ignora — aba pode não ter content.js */ }
              });
            });
          });
        }
      })
      .catch(function (err) { console.warn('[SALEIA] Whisper erro:', err.message); });
    // audioChunk não precisa de sendResponse
  }

  return true;
});

// ─────────────────────────────────────────────
// PROPAGAR MENSAGEM PARA ABAS DO GOOGLE MEET
// ─────────────────────────────────────────────
function propagarParaMeet(mensagem) {
  chrome.tabs.query({ url: 'https://meet.google.com/*' }, function (tabs) {
    tabs.forEach(function (tab) {
      chrome.tabs.sendMessage(tab.id, mensagem, function () {
        if (chrome.runtime.lastError) {
          console.warn('[SALEIA] Não foi possível enviar para aba:', tab.id);
        }
      });
    });
  });
}

// ─────────────────────────────────────────────
// ÍCONE DINÂMICO — verde quando no Meet, cinza fora
// ─────────────────────────────────────────────

/**
 * Verifica se a URL pertence ao Google Meet de forma segura,
 * comparando o hostname exato para evitar falsos positivos.
 */
function ehUrlDoMeet(url) {
  try {
    const parsed = new URL(url);
    return parsed.hostname === 'meet.google.com';
  } catch (_) {
    return false;
  }
}

chrome.tabs.onActivated.addListener(function (activeInfo) {
  chrome.tabs.get(activeInfo.tabId, function (tab) {
    if (tab && tab.url && ehUrlDoMeet(tab.url)) {
      chrome.action.setBadgeText({ text: '●', tabId: tab.id });
      chrome.action.setBadgeBackgroundColor({ color: '#4caf50', tabId: tab.id });
    } else {
      chrome.action.setBadgeText({ text: '', tabId: activeInfo.tabId });
    }
  });
});

chrome.tabs.onUpdated.addListener(function (tabId, changeInfo, tab) {
  if (changeInfo.status === 'complete' && tab.url && ehUrlDoMeet(tab.url)) {
    chrome.action.setBadgeText({ text: '●', tabId: tabId });
    chrome.action.setBadgeBackgroundColor({ color: '#4caf50', tabId: tabId });
  }
});

// ─────────────────────────────────────────────
// HEARTBEAT HTTP — verifica backend a cada 15s
// Usa /health em vez de WebSocket (mais simples
// e sem o problema de 502 do WebSocket).
// ─────────────────────────────────────────────
function verificarHeartbeat() {
  // API desligada pelo usuário — nenhuma chamada de rede deve ocorrer.
  if (!estadoExtensao.ativo) return;
  const url = BACKEND_URL_CANONICAL + '/health';
  fetch(url, { method: 'GET' })
    .then(function (res) {
      const online = res.ok;
      propagarParaMeet({ tipo: 'backendStatus', online: online });
      if (online) console.log('[SALEIA] Heartbeat conectado.');
    })
    .catch(function () {
      console.warn('[SALEIA] Backend offline — verificando novamente em 15s...');
      propagarParaMeet({ tipo: 'backendStatus', online: false });
    });
}

// Verificar imediatamente e depois a cada 15 segundos
verificarHeartbeat();
setInterval(verificarHeartbeat, 15000);

// ─────────────────────────────────────────────
// CAPTURA DE ÁUDIO — helper async
// ─────────────────────────────────────────────
async function handleIniciarCaptura(tabId) {
  // Usa audioCapture (microfone) — não requer invocação da extensão via popup
  return new Promise(function (resolve) {
    chrome.offscreen.createDocument({
      url: chrome.runtime.getURL('offscreen.html'),
      reasons: ['USER_MEDIA'],
      justification: 'Captura microfone para transcrição com OpenAI Whisper',
    }).catch(function (e) {
      // Documento já existe — ok, continuamos
      console.log('[SALEIA] offscreen já existia:', e && e.message);
    }).then(function () {
      var timer = setTimeout(function () {
        console.error('[SALEIA] Timeout: offscreen não respondeu em 6s');
        resolve({ ok: false, error: 'timeout — offscreen não respondeu' });
      }, 6000);

      chrome.runtime.sendMessage(
        { tipo: 'iniciarGravacaoOffscreen' },
        function (resp) {
          clearTimeout(timer);
          if (chrome.runtime.lastError) {
            console.error('[SALEIA] Erro ao contactar offscreen:', chrome.runtime.lastError.message);
            resolve({ ok: false, error: chrome.runtime.lastError.message });
            return;
          }
          capturaAtiva = !!(resp && resp.ok);
          console.log('[SALEIA] offscreen respondeu:', resp);
          resolve({ ok: capturaAtiva, error: resp ? resp.error : 'sem resposta' });
        }
      );
    });
  });
}
