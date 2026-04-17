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
  backendUrl: 'https://dime-flip-protector.ngrok-free.dev',
};

// ─────────────────────────────────────────────
// INICIALIZAÇÃO — carregar configurações salvas
// ─────────────────────────────────────────────
chrome.runtime.onInstalled.addListener(function () {
  chrome.storage.local.get(['saleiaBackendUrl', 'saleiaAtivo'], function (result) {
    if (!result.saleiaBackendUrl) {
      chrome.storage.local.set({ saleiaBackendUrl: 'https://dime-flip-protector.ngrok-free.dev' });
    }
    if (result.saleiaAtivo === undefined) {
      chrome.storage.local.set({ saleiaAtivo: true });
    }
  });
  console.log('[SALEIA] Extensão instalada/atualizada.');
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
    fetch(msg.url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'ngrok-skip-browser-warning': 'true',
      },
      body: JSON.stringify(msg.payload),
    })
      .then(function (res) { return res.json(); })
      .then(function (data) { sendResponse({ ok: true, data: data }); })
      .catch(function (err) { sendResponse({ ok: false, error: err.message }); });
    return true;
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