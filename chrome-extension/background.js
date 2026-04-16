/**
 * SALEIA — background.js
 * Service Worker da extensão Chrome.
 * Gerencia alarmes, configurações e estado por aba.
 */

'use strict';

// ─────────────────────────────────────────────
// ESTADO GLOBAL DA EXTENSÃO
// ─────────────────────────────────────────────
let estadoExtensao = {
  ativo: true,
  backendUrl: 'http://localhost:8000',
};

// ─────────────────────────────────────────────
// INICIALIZAÇÃO — carregar configurações salvas
// ─────────────────────────────────────────────
chrome.runtime.onInstalled.addListener(function () {
  chrome.storage.local.get(['saleiaBackendUrl', 'saleiaAtivo'], function (result) {
    if (!result.saleiaBackendUrl) {
      chrome.storage.local.set({ saleiaBackendUrl: 'http://localhost:8000' });
    }
    if (result.saleiaAtivo === undefined) {
      chrome.storage.local.set({ saleiaAtivo: true });
    }
  });
  console.log('[SALEIA] Extensão instalada/atualizada.');
});

// ─────────────────────────────────────────────
// OUVIR MENSAGENS DO POPUP E CONTENT SCRIPT
// ─────────────────────────────────────────────
chrome.runtime.onMessage.addListener(function (msg, sender, sendResponse) {
  // Popup → ativar/desativar extensão
  if (msg.tipo === 'setAtivo') {
    estadoExtensao.ativo = msg.valor;
    chrome.storage.local.set({ saleiaAtivo: msg.valor });

    // Propagar para a aba ativa do Meet
    propagarParaMeet({ tipo: 'toggle', valor: msg.valor });
    sendResponse({ ok: true });
  }

  // Popup → mudar URL do backend
  if (msg.tipo === 'setBackendUrl') {
    estadoExtensao.backendUrl = msg.valor;
    chrome.storage.local.set({ saleiaBackendUrl: msg.valor });

    // Propagar para a aba ativa do Meet
    propagarParaMeet({ tipo: 'backendUrl', valor: msg.valor });
    sendResponse({ ok: true });
  }

  // Content script → informar status
  if (msg.tipo === 'status') {
    sendResponse({ ativo: estadoExtensao.ativo, backendUrl: estadoExtensao.backendUrl });
  }

  return true; // manter canal aberto para sendResponse assíncrono
});

// ─────────────────────────────────────────────
// PROPAGAR MENSAGEM PARA ABAS DO GOOGLE MEET
// ─────────────────────────────────────────────
function propagarParaMeet(mensagem) {
  chrome.tabs.query({ url: 'https://meet.google.com/*' }, function (tabs) {
    tabs.forEach(function (tab) {
      chrome.tabs.sendMessage(tab.id, mensagem, function () {
        // Ignora erro se a aba não tiver content script ativo
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
      // Aba é do Meet — ícone normal (colorido)
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
