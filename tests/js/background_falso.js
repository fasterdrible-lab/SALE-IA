// Carrega chrome-extension/background.js num contexto isolado com um
// `chrome` falso — usado pelos testes da extensão.
'use strict';

const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const EXT = path.join(__dirname, '..', '..', 'chrome-extension');

/**
 * opcoes:
 *  fetch(url, opts) -> Promise<{ok, status, json()}>
 *  token: login salvo (chrome.storage.local)
 *  aoMensagemRuntime(msg) -> resposta (offscreen)
 *  aoMensagemAba(tabId, msg) -> resposta (content.js)
 *  streamId: retorno de chrome.tabCapture.getMediaStreamId
 */
function carregarBackground(opcoes) {
  opcoes = opcoes || {};
  const ouvintes = [];
  const abasFechadas = [];
  const enviadosParaAbas = [];
  const enviadosRuntime = [];
  const fetches = [];
  const sessao = {};
  const filaEmMemoria = new Map();
  const chrome = {
    runtime: {
      onInstalled: { addListener() {} },
      onMessage: { addListener: (fn) => ouvintes.push(fn) },
      getManifest: () => ({ version: 'teste' }),
      sendMessage(msg, cb) {
        enviadosRuntime.push(msg);
        const r = opcoes.aoMensagemRuntime ? opcoes.aoMensagemRuntime(msg) : undefined;
        if (cb) setTimeout(() => cb(r), 0);
      },
      getURL: (p) => p,
      lastError: undefined,
    },
    storage: {
      local: { get(_k, cb) { cb(opcoes.token ? { saleiaToken: opcoes.token } : {}); }, set() {}, remove() {} },
      session: {
        get: async (k) => (k in sessao ? { [k]: JSON.parse(JSON.stringify(sessao[k])) } : {}),
        set: async (obj) => { Object.assign(sessao, JSON.parse(JSON.stringify(obj))); },
      },
    },
    tabs: {
      query() { throw new Error('não deveria consultar todas as abas'); },
      sendMessage(id, msg, cb) {
        enviadosParaAbas.push([id, msg]);
        const r = opcoes.aoMensagemAba ? opcoes.aoMensagemAba(id, msg) : undefined;
        if (cb) setTimeout(() => cb(r), 0);
      },
      onActivated: { addListener() {} },
      onUpdated: { addListener() {} },
      onRemoved: { addListener: (fn) => abasFechadas.push(fn) },
      get() {},
    },
    action: { setBadgeText() {}, setBadgeBackgroundColor() {} },
    offscreen: { closeDocument: () => Promise.resolve(), createDocument: () => Promise.resolve() },
    tabCapture: { getMediaStreamId: async () => opcoes.streamId || 'stream-1' },
    alarms: { create() {}, onAlarm: { addListener() {} } },
  };
  const fetch = (url, opts) => {
    fetches.push([url, opts]);
    if (url.endsWith('/health')) return new Promise(() => {});
    return opcoes.fetch ? opcoes.fetch(url, opts) : Promise.resolve({ ok: true, status: 200, json: async () => ({}) });
  };
  const ctx = {
    chrome, fetch, console: { log() {}, warn() {}, error() {} },
    setInterval() {}, setTimeout, clearTimeout, URL, Date, Promise, JSON,
  };
  ctx.globalThis = ctx;
  ctx.importScripts = (arquivo) => vm.runInContext(fs.readFileSync(path.join(EXT, arquivo), 'utf8'), ctx);
  vm.createContext(ctx);
  vm.runInContext(fs.readFileSync(path.join(EXT, 'background.js'), 'utf8'), ctx);
  // A fila usa IndexedDB no navegador; aqui, um Map com o mesmo contrato.
  Object.assign(ctx.armazenamentoFila, {
    listar: async () => [...filaEmMemoria.keys()].sort().map((k) => filaEmMemoria.get(k)),
    inserir: async (item) => { filaEmMemoria.set(item.id, item); },
    remover: async (id) => { filaEmMemoria.delete(id); },
  });
  // sender: {tab: {id}} quando a mensagem vem de um content.js
  const enviar = (msg, sender) => new Promise((resolve) => {
    ouvintes[0](msg, sender || {}, resolve);
    if (msg.tipo === 'audioChunk') setTimeout(resolve, 20);
  });
  const esperar = (ms) => new Promise((r) => setTimeout(r, ms || 20));
  const fecharAba = (tabId) => abasFechadas.forEach((fn) => fn(tabId));
  return { enviar, esperar, fecharAba, enviadosParaAbas, enviadosRuntime, fetches, sessao, filaEmMemoria, ctx };
}

module.exports = { carregarBackground, EXT };
