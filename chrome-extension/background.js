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

// T02: gravador contínuo + fila de envio (funções puras, testadas no Node).
importScripts('gravacao_rules.js');

// ─────────────────────────────────────────────
// ESTADO GLOBAL DA EXTENSÃO
// ─────────────────────────────────────────────
let estadoExtensao = {
  ativo: true,
  backendUrl: 'https://api.saleia.app.br',
  token: null,
  usuario: null,
};

// Estado da captura de áudio (Whisper). Só reserva: o MV3 recicla o
// service worker e estas variáveis voltam ao padrão — por isso o
// offscreen manda meeting_id e tabId em cada pedaço (auditoria T01, P20).
let capturaAtiva = false;
let captaMeetingId = 'default';
let captaTabId = null;

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
chrome.storage.local.get(['saleiaBackendUrl', 'saleiaAtivo', 'saleiaToken', 'saleiaUsuario'], function (result) {
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
  // Reidrata login — o Service Worker MV3 pode ser reciclado a qualquer
  // momento, entao o token em memoria sozinho nao e suficiente.
  estadoExtensao.token = result.saleiaToken || null;
  estadoExtensao.usuario = result.saleiaUsuario || null;
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
  // LOGIN OPCIONAL — habilita o fallback pra conta Claude
  // do vendedor no tempo real quando os provedores centrais
  // falharem (agent/multiagente/claude_fallback.py). Quem nao
  // loga continua funcionando exatamente como antes (anonimo).
  // ─────────────────────────────────────────────

  // Popup → tentar login
  if (msg.tipo === 'fazerLogin') {
    fetch(estadoExtensao.backendUrl + '/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: msg.email, senha: msg.senha }),
    })
      .then(function (res) { return res.json().then(function (data) { return { status: res.status, data: data }; }); })
      .then(function (r) {
        if (r.status !== 200 || !r.data.token) {
          sendResponse({ ok: false, error: (r.data && (r.data.detail || r.data.erro)) || 'Não foi possível entrar.' });
          return;
        }
        estadoExtensao.token = r.data.token;
        estadoExtensao.usuario = r.data.usuario || null;
        estadoExtensao.loginEm = Date.now();
        chrome.storage.local.set({ saleiaToken: r.data.token, saleiaUsuario: r.data.usuario || null });
        sendResponse({ ok: true, usuario: estadoExtensao.usuario });
      })
      .catch(function (err) { sendResponse({ ok: false, error: err.message }); });
    return true;
  }

  // Popup → sair
  if (msg.tipo === 'logout') {
    estadoExtensao.token = null;
    estadoExtensao.usuario = null;
    chrome.storage.local.remove(['saleiaToken', 'saleiaUsuario']);
    sendResponse({ ok: true });
  }

  // Content script → resposta do /tempo-real trouxe token renovado
  // (sessão deslizante) ou avisou que o token expirou/é inválido
  // (Tarefa B8). Encerrar limpa o login para o popup voltar a pedir
  // e-mail/senha em vez de seguir mostrando "Conectado".
  if (msg.tipo === 'atualizarSessao') {
    if (msg.token_renovado) {
      estadoExtensao.token = msg.token_renovado;
      chrome.storage.local.set({ saleiaToken: msg.token_renovado });
    } else if (msg.encerrar && Date.now() - (estadoExtensao.loginEm || 0) > 120000) {
      // A janela de 2 min evita que uma resposta ainda em voo, calculada
      // com o token antigo, apague um login que o vendedor acabou de fazer.
      estadoExtensao.token = null;
      estadoExtensao.usuario = null;
      chrome.storage.local.remove(['saleiaToken', 'saleiaUsuario']);
    }
    sendResponse({ ok: true });
  }

  // Popup → estado atual de login (ao abrir o popup)
  if (msg.tipo === 'getAuth') {
    sendResponse({ logado: !!estadoExtensao.token, usuario: estadoExtensao.usuario });
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
        'X-Extensao-Versao': chrome.runtime.getManifest().version,
      },
    };
    // Login e opcional — so anexa o token quando o vendedor esta logado.
    // Ponto unico: cobre /tempo-real e todas as outras chamadas via
    // fetchBackend automaticamente, sem precisar mexer no content.js.
    if (estadoExtensao.token) {
      options.headers['Authorization'] = 'Bearer ' + estadoExtensao.token;
    }

    if (method !== 'GET' && method !== 'HEAD') {
      options.body = JSON.stringify(msg.payload || {});
    }

    // Auditoria T01 (P22): erro HTTP (500/502/503) voltava como ok:true e o
    // content.js avançava o índice do que já foi enviado — fala perdida se o
    // servidor não gravou. Agora ok = status 2xx; o reenvio é seguro porque
    // o backend descarta o trecho repetido.
    fetch(msg.url, options)
      .then(function (res) {
        if (!res.ok) console.warn('[SALEIA] fetchBackend HTTP ' + res.status + ' em ' + msg.url);
        return res.json().catch(function () { return null; }).then(function (data) {
          sendResponse({ ok: res.ok, status: res.status, data: data, error: res.ok ? undefined : 'HTTP ' + res.status });
        });
      })
      .catch(function (err) {
        console.error('[SALEIA] fetchBackend erro de rede em ' + msg.url + ':', err.message);
        sendResponse({ ok: false, error: err.message });
      });
    return true;
  }

  // ─────────────────────────────────────────────
  // CAPTURA DE ÁUDIO — Whisper via tabCapture + offscreen
  // ─────────────────────────────────────────────

  // Popup → iniciar captura de áudio da aba. Precisa vir do popup (não
  // de um content script) — só abrir o popup satisfaz o gesto que o
  // Chrome exige pra liberar chrome.tabCapture (activeTab), achado real
  // de 19/09/2026. sender.tab não existe quando a mensagem vem do
  // popup, por isso msg.tabId é explícito nesse caso.
  if (msg.tipo === 'iniciarCaptura') {
    const tabId = (sender.tab && sender.tab.id) || msg.tabId || null;
    if (!tabId) { sendResponse({ ok: false, error: 'sem tabId' }); return true; }
    captaMeetingId = msg.meeting_id || 'default';
    captaTabId = tabId;
    handleIniciarCaptura(tabId, captaMeetingId).then(sendResponse).catch(function (e) {
      sendResponse({ ok: false, error: e.message });
    });
    return true;
  }

  // Popup → status atual da captura de áudio da aba (pra restaurar o
  // texto do botão ao reabrir o popup).
  if (msg.tipo === 'statusCaptura') {
    sendResponse({ ativo: capturaAtiva });
    return true;
  }

  // Content script → parar captura
  if (msg.tipo === 'pararCaptura') {
    chrome.runtime.sendMessage({ tipo: 'pararGravacaoOffscreen' }, function () {
      capturaAtiva = false;
      // T02: com a gravação contínua ativa, o offscreen continua aberto.
      lerEstadoGravacao().then(function (estado) {
        if (!estado.ativa) chrome.offscreen.closeDocument().catch(function () {});
        sendResponse({ ok: true });
      });
    });
    return true;
  }

  // Content.js → chunk de áudio do microfone via MediaRecorder (rota direta sem offscreen)
  if (msg.tipo === 'whisperChunk') {
    const url = (msg.backendUrl || estadoExtensao.backendUrl) + '/audio-transcricao';
    fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Extensao-Versao': chrome.runtime.getManifest().version },
      body: JSON.stringify({
        audio_base64: msg.audio_base64,
        mime_type: msg.mime_type,
        meeting_id: msg.meeting_id || 'default',
        fonte: msg.fonte || 'microfone',
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

  // ─────────────────────────────────────────────
  // T02 — GRAVAÇÃO CONTÍNUA DO ÁUDIO
  // ─────────────────────────────────────────────

  // Popup → começar a gravar (precisa do gesto do popup para o tabCapture)
  if (msg.tipo === 'iniciarGravacao') {
    iniciarGravacao(msg).then(sendResponse).catch(function (e) {
      sendResponse({ ok: false, error: e.message });
    });
    return true;
  }

  // Popup/sidebar → pausar | retomar | parar
  if (msg.tipo === 'controleGravacao') {
    controlarGravacao(msg.acao).then(sendResponse).catch(function (e) {
      sendResponse({ ok: false, error: e.message });
    });
    return true;
  }

  if (msg.tipo === 'statusGravacao') {
    lerEstadoGravacao().then(function (estado) {
      return filaGravacao.pendentes().then(function (n) {
        sendResponse(Object.assign({}, estado, { pendentes: n }));
      });
    });
    return true;
  }

  // Offscreen (aba) / content.js (microfone) → item para a fila. A resposta
  // só sai depois de o item estar salvo: o gravador espera por ela.
  if (msg.tipo === 'gravacaoIniciar' || msg.tipo === 'gravacaoBloco' || msg.tipo === 'gravacaoEncerrar') {
    enfileirarGravacao(msg.tipo, msg.corpo || {}, sender).then(sendResponse).catch(function (e) {
      console.error('[SALEIA] fila da gravação:', e);
      sendResponse({ aceito: false, motivo: e.message });
    });
    return true;
  }

  // Offscreen (aba) / content.js (microfone) → o áudio da trilha acabou.
  if (msg.tipo === 'gravacaoTrilhaAcabou') {
    trilhaAcabou((msg.corpo || {}).track_id).then(sendResponse, function () { sendResponse({ ok: false }); });
    return true;
  }

  // content.js → página do Meet fechando/recarregando com o microfone gravando.
  if (msg.tipo === 'gravacaoMicrofoneSaiu') {
    var abaQueSaiu = sender.tab && sender.tab.id;
    encerrarAbertas(function (a) { return a.track_id === 'microfone' && a.tabId === abaQueSaiu; })
      .then(function (n) {
        return n ? salvarEstadoGravacao({ microfone: 'parado: página fechada ou recarregada' }) : null;
      })
      .then(function () { sendResponse({ ok: true }); }, function () { sendResponse({ ok: false }); });
    return true;
  }

  // Offscreen → chunk de áudio pronto para enviar ao Whisper
  if (msg.tipo === 'audioChunk') {
    const url = estadoExtensao.backendUrl + '/audio-transcricao';
    const meetingDoPedaco = msg.meeting_id || captaMeetingId;
    const abaDoPedaco = msg.tabId || captaTabId;
    fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Extensao-Versao': chrome.runtime.getManifest().version },
      body: JSON.stringify({
        audio_base64: msg.base64,
        mime_type: msg.mimeType,
        meeting_id: meetingDoPedaco,
        fonte: msg.fonte || 'aba',
      }),
    })
      .then(function (res) { return res.json(); })
      .then(function (data) {
        if (data.texto && data.texto.trim()) {
          // Envia texto transcrito para o content.js da aba CAPTURADA.
          // fonte:'aba' identifica que veio do tabCapture (participantes),
          // não do microfone do vendedor — content.js usa isso pra rotular
          // o speaker corretamente (Fase 3 do PROMPT MESTRE). Antes ia
          // para todas as abas do Meet: 2 reuniões abertas misturavam
          // texto (auditoria T01, P21).
          if (!abaDoPedaco) return;
          chrome.tabs.sendMessage(abaDoPedaco, { tipo: 'transcricaoAudio', texto: data.texto.trim(), fonte: msg.fonte || 'aba' }, function () {
            if (chrome.runtime.lastError) { /* aba fechada ou sem content.js — ignora */ }
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
  fetch(url, { method: 'GET', headers: { 'X-Extensao-Versao': chrome.runtime.getManifest().version } })
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
async function handleIniciarCaptura(tabId, meetingId) {
  // Fase 3 do PROMPT MESTRE ("Meetily") — captura o áudio da ABA (voz dos
  // participantes), complementando o microfone do vendedor que já é
  // capturado direto em content.js (getUserMedia na própria página do
  // Meet). O streamId do tabCapture só pode ser obtido aqui (contexto do
  // service worker) — content scripts não têm acesso a chrome.tabCapture.
  var tabStreamId = null;
  try {
    tabStreamId = await chrome.tabCapture.getMediaStreamId({ targetTabId: tabId });
  } catch (e) {
    console.warn('[SALEIA] tabCapture indisponível para esta aba:', e && e.message);
    return { ok: false, error: 'tabCapture indisponível: ' + (e && e.message) };
  }

  return new Promise(function (resolve) {
    garantirOffscreen().then(function () {
      var timer = setTimeout(function () {
        console.error('[SALEIA] Timeout: offscreen não respondeu em 6s');
        resolve({ ok: false, error: 'timeout — offscreen não respondeu' });
      }, 6000);

      chrome.runtime.sendMessage(
        { tipo: 'iniciarGravacaoOffscreen', tabStreamId: tabStreamId, meeting_id: meetingId, tabId: tabId },
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

function garantirOffscreen() {
  return chrome.offscreen.createDocument({
    url: chrome.runtime.getURL('offscreen.html'),
    reasons: ['USER_MEDIA'],
    justification: 'Captura do áudio da aba (participantes) para transcrição e gravação',
  }).catch(function (e) {
    // Documento já existe — ok, continuamos
    console.log('[SALEIA] offscreen já existia:', e && e.message);
  });
}

// ─────────────────────────────────────────────
// T02 — GRAVAÇÃO CONTÍNUA DO ÁUDIO
// Regras e fila: gravacao_rules.js. Servidor: /gravacao/* (desligado por
// padrão; só com login; nunca começa sozinha — só pelo popup, com a
// confirmação de que os participantes foram avisados).
// ─────────────────────────────────────────────

var BD_GRAVACAO = 'saleia-gravacao';
var LOJA_FILA = 'fila';

function abrirBdGravacao() {
  return new Promise(function (resolve, reject) {
    var req = indexedDB.open(BD_GRAVACAO, 1);
    req.onupgradeneeded = function () { req.result.createObjectStore(LOJA_FILA, { keyPath: 'id' }); };
    req.onsuccess = function () { resolve(req.result); };
    req.onerror = function () { reject(req.error); };
  });
}

function operacaoNaFila(modo, operacao) {
  return abrirBdGravacao().then(function (bd) {
    return new Promise(function (resolve, reject) {
      var tx = bd.transaction(LOJA_FILA, modo);
      var req = operacao(tx.objectStore(LOJA_FILA));
      tx.oncomplete = function () { bd.close(); resolve(req && req.result); };
      tx.onerror = function () { bd.close(); reject(tx.error); };
    });
  });
}

// IndexedDB do service worker: persiste quando o MV3 recicla o worker e
// não tem o limite de 10 MB do chrome.storage.local.
var armazenamentoFila = {
  listar: function () { return operacaoNaFila('readonly', function (loja) { return loja.getAll(); }); },
  inserir: function (item) { return operacaoNaFila('readwrite', function (loja) { return loja.put(item); }); },
  remover: function (id) { return operacaoNaFila('readwrite', function (loja) { return loja.delete(id); }); },
};

var ROTAS_GRAVACAO = { iniciar: '/gravacao/iniciar', bloco: '/gravacao/bloco', encerrar: '/gravacao/encerrar' };

function enviarItemGravacao(item) {
  if (!estadoExtensao.token) return Promise.resolve({ status: 401 });
  return fetch(estadoExtensao.backendUrl + ROTAS_GRAVACAO[item.tipo], {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': 'Bearer ' + estadoExtensao.token,
      'X-Extensao-Versao': chrome.runtime.getManifest().version,
    },
    body: JSON.stringify(item.corpo),
  }).then(function (res) { return { status: res.status }; }, function () { return { status: 0 }; });
}

var filaGravacao = SaleiaGravacao.criarFilaDeEnvio({
  armazenamento: armazenamentoFila,
  enviar: enviarItemGravacao,
  aoDescartar: function (item, status) {
    console.warn('[SALEIA] gravação: servidor recusou ' + item.tipo + ' (' + status + ')', item.corpo.recording_id, item.corpo.sequence);
  },
});

var ESTADO_GRAVACAO_PADRAO = {
  ativa: false, pausada: false, meeting_id: null, tabId: null, inicio_ms: null,
  ultimo_erro: null, microfone: null, consentimento_meeting: null,
  // recording_id → {track_id, tabId}: gravações iniciadas e ainda sem "encerrar",
  // para fechar as que o gravador não consegue (aba fechada, página recarregada).
  abertas: {},
};

function lerEstadoGravacao() {
  return chrome.storage.session.get('saleiaGravacao').then(function (r) {
    return Object.assign({}, ESTADO_GRAVACAO_PADRAO, r.saleiaGravacao || {});
  });
}

// Ler-mudar-gravar em fila: aba e microfone mandam "iniciar" quase juntos.
var correnteEstadoGravacao = Promise.resolve();

function salvarEstadoGravacao(mudancas) {
  var passo = correnteEstadoGravacao.then(function () {
    return lerEstadoGravacao().then(function (estado) {
      var novo = Object.assign(estado, typeof mudancas === 'function' ? mudancas(estado) : mudancas);
      return chrome.storage.session.set({ saleiaGravacao: novo }).then(function () {
        if (novo.tabId) {
          chrome.tabs.sendMessage(novo.tabId, { tipo: 'statusGravacao', estado: novo }, function () {
            if (chrome.runtime.lastError) { /* aba sem content.js */ }
          });
        }
        return novo;
      });
    });
  });
  correnteEstadoGravacao = passo.catch(function () {});
  return passo;
}

function registrarAberta(tipo, corpo, sender) {
  if (!corpo.recording_id || (tipo !== 'iniciar' && tipo !== 'encerrar')) return Promise.resolve();
  return salvarEstadoGravacao(function (estado) {
    var abertas = Object.assign({}, estado.abertas);
    if (tipo === 'iniciar') {
      abertas[corpo.recording_id] = { track_id: corpo.track_id, tabId: (sender && sender.tab && sender.tab.id) || estado.tabId };
    } else {
      delete abertas[corpo.recording_id];
    }
    return { abertas: abertas };
  });
}

/** Põe "encerrar" na fila das gravações abertas que passam no filtro. Devolve quantas. */
function encerrarAbertas(filtro) {
  var ids = [];
  return salvarEstadoGravacao(function (estado) {
    var abertas = Object.assign({}, estado.abertas);
    Object.keys(abertas).forEach(function (id) {
      if (filtro(abertas[id])) { ids.push(id); delete abertas[id]; }
    });
    return { abertas: abertas };
  }).then(function () {
    // ultima_sequence null: o servidor fecha pelo que recebeu (o fim pode ter morrido com a página).
    return ids.reduce(function (p, id) {
      return p.then(function () { return filaGravacao.adicionar('encerrar', { recording_id: id, ultima_sequence: null }); });
    }, Promise.resolve());
  }).then(function () {
    if (ids.length) processarFilaGravacao();
    return ids.length;
  });
}

// Sem áudio da aba não há mais reunião para gravar: encerra tudo. Sem o
// microfone, a aba continua e a sidebar avisa.
function trilhaAcabou(trackId) {
  return lerEstadoGravacao().then(function (estado) {
    if (!estado.ativa) return { ok: true };
    if (trackId === 'aba') return controlarGravacao('parar');
    if (trackId === 'microfone') return salvarEstadoGravacao({ microfone: 'parado: microfone desconectado' }).then(function () { return { ok: true }; });
    return { ok: true };
  });
}

// Aba do Meet fechada: o microfone morreu sem encerrar; a aba é parada no offscreen.
chrome.tabs.onRemoved.addListener(function (tabId) {
  lerEstadoGravacao().then(function (estado) {
    if (estado.tabId !== tabId) return;
    return encerrarAbertas(function (a) { return a.track_id === 'microfone' && a.tabId === tabId; })
      .then(function () { if (estado.ativa) return controlarGravacao('parar'); });
  }).catch(function (e) { console.warn('[SALEIA] gravação ao fechar a aba:', e && e.message); });
});

function processarFilaGravacao() {
  return filaGravacao.processar().then(function (r) {
    var erro = r.motivo === 'parar_login' ? 'login' : r.motivo === 'parar_desligada' ? 'desligada'
      : r.motivo === 'tentar_depois' ? 'sem_conexao' : null;
    return lerEstadoGravacao().then(function (estado) {
      if (estado.ultimo_erro !== erro) return salvarEstadoGravacao({ ultimo_erro: erro });
    });
  }).catch(function (e) { console.warn('[SALEIA] fila da gravação:', e && e.message); });
}

// Corpo de cada item da fila: só os campos que a rota aceita.
function corpoParaFila(tipo, corpo, estado) {
  if (tipo === 'iniciar') {
    return {
      meeting_id: corpo.meeting_id, track_id: corpo.track_id, recording_id: corpo.recording_id,
      codec: corpo.codec || '', sample_rate: null,
      // Só existe gravação iniciada pelo popup, depois da confirmação.
      consentimento: !!estado.consentimento_meeting && estado.consentimento_meeting === corpo.meeting_id,
    };
  }
  if (tipo === 'bloco') {
    return {
      recording_id: corpo.recording_id, sequence: corpo.sequence, start_ms: corpo.start_ms, end_ms: corpo.end_ms,
      content_hash: corpo.content_hash, recorded_at: corpo.recorded_at, audio_base64: corpo.audio_base64,
    };
  }
  return { recording_id: corpo.recording_id, ultima_sequence: corpo.ultima_sequence };
}

function enfileirarGravacao(tipoMsg, corpo, sender) {
  var tipo = { gravacaoIniciar: 'iniciar', gravacaoBloco: 'bloco', gravacaoEncerrar: 'encerrar' }[tipoMsg];
  return lerEstadoGravacao().then(function (estado) {
    return filaGravacao.adicionar(tipo, corpoParaFila(tipo, corpo, estado)).then(function (r) {
      if (!r.aceito) salvarEstadoGravacao({ ultimo_erro: r.motivo });
      return registrarAberta(tipo, corpo, sender).then(function () {
        processarFilaGravacao();
        return r;
      });
    });
  });
}

// A cada 30s (sobrevive ao worker reciclado): reenvia o que ficou na fila.
chrome.alarms.create('saleia-gravacao-fila', { periodInMinutes: 0.5 });
chrome.alarms.onAlarm.addListener(function (alarme) {
  if (alarme.name === 'saleia-gravacao-fila') processarFilaGravacao();
});

function mensagemParaAba(tabId, msg) {
  return new Promise(function (resolve) {
    chrome.tabs.sendMessage(tabId, msg, function (resp) {
      resolve(chrome.runtime.lastError ? { ok: false, error: chrome.runtime.lastError.message } : (resp || { ok: false }));
    });
  });
}

function mensagemParaOffscreen(msg) {
  return new Promise(function (resolve) {
    chrome.runtime.sendMessage(msg, function (resp) {
      resolve(chrome.runtime.lastError ? { ok: false, error: chrome.runtime.lastError.message } : (resp || { ok: false }));
    });
  });
}

async function iniciarGravacao(msg) {
  if (msg.consentimento !== true) return { ok: false, error: 'Confirme que os participantes foram avisados da gravação.' };
  if (!estadoExtensao.token) return { ok: false, error: 'Entre na extensão para gravar a reunião.' };
  if (!msg.tabId || !msg.meeting_id) return { ok: false, error: 'Abra a reunião do Meet antes de gravar.' };
  var estado = await lerEstadoGravacao();
  if (estado.ativa) return { ok: false, error: 'Já existe uma gravação ativa.' };
  var config;
  try {
    config = await (await fetch(estadoExtensao.backendUrl + '/gravacao/config')).json();
  } catch (e) {
    return { ok: false, error: 'Servidor indisponível.' };
  }
  if (!config.habilitada) return { ok: false, error: 'Gravação de áudio desativada no servidor.' };

  await salvarEstadoGravacao({ consentimento_meeting: msg.meeting_id, tabId: msg.tabId });
  var tabStreamId = null;
  if (!capturaAtiva) {  // com a transcrição da aba ligada, o offscreen já tem o stream
    try {
      tabStreamId = await chrome.tabCapture.getMediaStreamId({ targetTabId: msg.tabId });
    } catch (e) {
      await salvarEstadoGravacao({ consentimento_meeting: null });
      return { ok: false, error: 'Não foi possível capturar a aba: ' + (e && e.message) };
    }
  }
  await garantirOffscreen();
  var opcoes = { meeting_id: msg.meeting_id, bloco_s: config.bloco_s, rotacao_s: config.rotacao_s };
  var aba = await mensagemParaOffscreen(Object.assign({ tipo: 'gravarAba', tabStreamId: tabStreamId }, opcoes));
  if (!aba.ok) {
    await salvarEstadoGravacao({ consentimento_meeting: null });
    return { ok: false, error: 'Áudio da aba: ' + (aba.error || 'falhou') };
  }
  var mic = await mensagemParaAba(msg.tabId, Object.assign({ tipo: 'gravarMicrofone' }, opcoes));
  await salvarEstadoGravacao({
    ativa: true, pausada: false, meeting_id: msg.meeting_id, tabId: msg.tabId, inicio_ms: Date.now(),
    ultimo_erro: null, microfone: mic.ok ? 'gravando' : ('erro: ' + (mic.error || 'sem resposta')),
  });
  return { ok: true, microfone: !!mic.ok, erro_microfone: mic.ok ? null : (mic.error || 'sem resposta') };
}

async function controlarGravacao(acao) {
  if (['pausar', 'retomar', 'parar'].indexOf(acao) < 0) return { ok: false, error: 'ação inválida' };
  var estado = await lerEstadoGravacao();
  if (!estado.ativa) return { ok: false, error: 'Nenhuma gravação ativa.' };
  await mensagemParaOffscreen({ tipo: 'controleGravacaoAba', acao: acao });
  if (estado.tabId) await mensagemParaAba(estado.tabId, { tipo: 'controleGravacaoMic', acao: acao });
  if (acao === 'parar') {
    // consentimento_meeting fica até a fila mandar o último "iniciar" (rotação
    // em voo); a próxima gravação pede a confirmação de novo no popup.
    await salvarEstadoGravacao({ ativa: false, pausada: false });
    if (!capturaAtiva) chrome.offscreen.closeDocument().catch(function () {});
  } else {
    await salvarEstadoGravacao({ pausada: acao === 'pausar' });
  }
  processarFilaGravacao();
  return { ok: true };
}
