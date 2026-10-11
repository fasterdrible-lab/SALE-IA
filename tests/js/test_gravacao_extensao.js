// Testes da gravação contínua na extensão (T02): gravador e fila de envio.
// Run: node --test tests/js/test_gravacao_extensao.js
'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const { webcrypto } = require('node:crypto');

const G = require(path.join(__dirname, '..', '..', 'chrome-extension', 'gravacao_rules.js'));

// MediaRecorder falso: o teste decide quando sai cada bloco.
class GravadorFalso {
  constructor(stream, opts) { this.stream = stream; this.opts = opts; this.state = 'inactive'; GravadorFalso.todos.push(this); }
  start(timeslice) { this.timeslice = timeslice; this.state = 'recording'; }
  emitir(tamanho) { this.ondataavailable({ data: { size: tamanho, rotulo: 'b' + tamanho } }); }
  stop() { this.state = 'inactive'; this.emitir(1); this.onstop(); }
}
GravadorFalso.todos = [];

function montar(extra) {
  GravadorFalso.todos = [];
  let relogio = 1_000_000;
  const timers = [];
  const eventos = [];
  let ids = 0;
  const g = G.criarGravadorContinuo(Object.assign({
    stream: {}, trackId: 'aba', meetingId: 'abc-defg-hij', blocoMs: 5000, rotacaoMs: 600000,
    mimeType: 'audio/webm;codecs=opus', MediaRecorder: GravadorFalso,
    agora: () => relogio, gerarId: () => 'rec-' + (++ids),
    setTimeout: (fn, ms) => { timers.push({ fn, ms, ativo: true }); return timers.length - 1; },
    clearTimeout: (i) => { if (timers[i]) timers[i].ativo = false; },
    aoIniciar: (i) => eventos.push(['iniciar', i.recording_id]),
    aoBloco: (b) => eventos.push(['bloco', b.recording_id, b.sequence, b.start_ms, b.end_ms]),
    aoEncerrar: (e) => eventos.push(['encerrar', e.recording_id, e.ultima_sequence]),
  }, extra || {}));
  return { g, eventos, timers, avancar: (ms) => { relogio += ms; }, rec: () => GravadorFalso.todos.at(-1) };
}

test('blocos em sequência, relógio contínuo e timeslice de 5s', async () => {
  const t = montar();
  t.g.iniciar();
  assert.equal(t.rec().timeslice, 5000);
  t.avancar(5000); t.rec().emitir(100);
  t.avancar(5000); t.rec().emitir(100);
  await t.g.ocioso();
  assert.deepEqual(t.eventos, [
    ['iniciar', 'rec-1'],
    ['bloco', 'rec-1', 0, 1_000_000, 1_005_000],
    ['bloco', 'rec-1', 1, 1_005_000, 1_010_000],  // começa onde o anterior terminou
  ]);
});

test('rotação: encerra a gravação com a última sequência e abre outra colada', async () => {
  const t = montar();
  t.g.iniciar();
  t.avancar(5000); t.rec().emitir(100);
  t.avancar(1000);
  t.timers[0].fn();  // passou rotacaoMs
  await t.g.ocioso();
  assert.deepEqual(t.eventos.slice(2), [
    ['bloco', 'rec-1', 1, 1_005_000, 1_006_000],  // o resto que o stop entrega
    ['encerrar', 'rec-1', 1],
    ['iniciar', 'rec-2'],
  ]);
  assert.equal(t.g.recordingAtual(), 'rec-2');
  t.avancar(5000); t.rec().emitir(100);
  await t.g.ocioso();
  assert.deepEqual(t.eventos.at(-1), ['bloco', 'rec-2', 0, 1_006_000, 1_011_000]);  // sequência recomeça
});

test('pausar encerra; retomar abre gravação nova; parar não reabre', async () => {
  const t = montar();
  t.g.iniciar();
  t.g.pausar();
  assert.equal(t.g.gravando(), false);
  t.g.retomar();
  t.g.parar();
  await t.g.ocioso();
  assert.deepEqual(t.eventos.filter((e) => e[0] !== 'bloco'), [
    ['iniciar', 'rec-1'], ['encerrar', 'rec-1', 0], ['iniciar', 'rec-2'], ['encerrar', 'rec-2', 0],
  ]);
  assert.equal(t.g.recordingAtual(), null);
});

test('encerrar nunca chega antes do último bloco, mesmo com processamento lento', async () => {
  const t = montar({
    aoBloco: (b) => new Promise((r) => setTimeout(() => { t2.push(['bloco', b.sequence]); r(); }, 5)),
    aoEncerrar: (e) => t2.push(['encerrar', e.ultima_sequence]),
  });
  const t2 = [];
  t.g.iniciar();
  t.rec().emitir(100);
  t.g.parar();
  await t.g.ocioso();
  assert.deepEqual(t2, [['bloco', 0], ['bloco', 1], ['encerrar', 1]]);
});

test('prepararConteudo: SHA-256 e base64 do bloco', async () => {
  const dados = new TextEncoder().encode('audio');
  const r = await G.prepararConteudo({ arrayBuffer: async () => dados.buffer }, webcrypto);
  assert.equal(r.content_hash, require('node:crypto').createHash('sha256').update('audio').digest('hex'));
  assert.equal(Buffer.from(r.audio_base64, 'base64').toString(), 'audio');
});

// ── Fila de envio ────────────────────────────────────────────────────────

// Mesmo contrato do IndexedDB do background: um registro por id, lido em ordem de id.
function armazenamentoEmMemoria() {
  const registros = new Map();
  const disco = {
    get itens() { return [...registros.keys()].sort().map((k) => registros.get(k)); },
    escritas: 0,
  };
  return {
    disco,
    listar: async () => JSON.parse(JSON.stringify(disco.itens)),
    inserir: async (item) => { disco.escritas++; registros.set(item.id, JSON.parse(JSON.stringify(item))); },
    remover: async (id) => { registros.delete(id); },
  };
}

test('envia em ordem e esvazia', async () => {
  const enviados = [];
  const fila = G.criarFilaDeEnvio({ armazenamento: armazenamentoEmMemoria(), enviar: async (i) => { enviados.push(i.tipo); return { status: 200 }; } });
  await fila.adicionar('iniciar', {}); await fila.adicionar('bloco', { sequence: 0 }); await fila.adicionar('encerrar', {});
  assert.deepEqual(await fila.processar(), { pendentes: 0, motivo: 'vazia' });
  assert.deepEqual(enviados, ['iniciar', 'bloco', 'encerrar']);
});

test('queda de conexão: para, guarda e reenvia depois sem pular nem duplicar', async () => {
  const arm = armazenamentoEmMemoria();
  let online = false;
  const recebidos = [];
  const enviar = async (i) => { if (!online) throw new Error('offline'); recebidos.push(i.corpo.sequence); return { status: 200 }; };
  const fila = G.criarFilaDeEnvio({ armazenamento: arm, enviar });
  for (let s = 0; s < 5; s++) await fila.adicionar('bloco', { sequence: s });
  assert.equal((await fila.processar()).motivo, 'tentar_depois');
  assert.equal(arm.disco.itens.length, 5);
  online = true;
  await fila.processar();
  assert.deepEqual(recebidos, [0, 1, 2, 3, 4]);
});

test('service worker reciclado: fila nova lê o que estava salvo', async () => {
  const arm = armazenamentoEmMemoria();
  const f1 = G.criarFilaDeEnvio({ armazenamento: arm, enviar: async () => ({ status: 503 }) });
  await f1.adicionar('bloco', { sequence: 7 });
  await f1.processar();
  const recebidos = [];
  const f2 = G.criarFilaDeEnvio({ armazenamento: arm, enviar: async (i) => { recebidos.push(i.corpo.sequence); return { status: 200 }; } });
  await f2.processar();
  assert.deepEqual(recebidos, [7]);
});

test('401 para a fila (precisa login) sem perder nada; 409 descarta só o item', async () => {
  const arm = armazenamentoEmMemoria();
  const respostas = [409, 401];
  const descartados = [];
  const fila = G.criarFilaDeEnvio({ armazenamento: arm, enviar: async () => ({ status: respostas.shift() }),
    aoDescartar: (i, s) => descartados.push([i.corpo.sequence, s]) });
  await fila.adicionar('bloco', { sequence: 0 }); await fila.adicionar('bloco', { sequence: 1 });
  assert.equal((await fila.processar()).motivo, 'parar_login');
  assert.deepEqual(descartados, [[0, 409]]);
  assert.deepEqual(arm.disco.itens.map((i) => i.corpo.sequence), [1]);
});

test('processar chamado 2x ao mesmo tempo não envia o mesmo item 2x', async () => {
  const enviados = [];
  const fila = G.criarFilaDeEnvio({ armazenamento: armazenamentoEmMemoria(),
    enviar: (i) => new Promise((r) => setTimeout(() => { enviados.push(i.corpo.sequence); r({ status: 200 }); }, 5)) });
  await fila.adicionar('bloco', { sequence: 0 });
  await Promise.all([fila.processar(), fila.processar()]);
  assert.deepEqual(enviados, [0]);
});

test('1h offline: cada bloco é uma escrita só e a ordem sobrevive mesmo no mesmo milissegundo', async () => {
  const arm = armazenamentoEmMemoria();
  const fila = G.criarFilaDeEnvio({ armazenamento: arm, enviar: async () => ({ status: 0 }), agora: () => 42 });
  for (let s = 0; s < 1440; s++) await fila.adicionar('bloco', { sequence: s });
  assert.equal(arm.disco.escritas, 1440);
  const recebidos = [];
  const f2 = G.criarFilaDeEnvio({ armazenamento: arm, enviar: async (i) => { recebidos.push(i.corpo.sequence); return { status: 200 }; } });
  await f2.processar();
  assert.deepEqual(recebidos, Array.from({ length: 1440 }, (_, i) => i));
});

// ── background.js: começar, enfileirar, controlar ───────────────────────

const { carregarBackground } = require('./background_falso.js');

const json = (status, corpo) => Promise.resolve({ ok: status < 300, status, json: async () => corpo });
const CONFIG_LIGADA = { habilitada: true, bloco_s: 5, rotacao_s: 600 };

function bgGravando(extra) {
  return carregarBackground(Object.assign({
    token: 'tok-1',
    fetch: (url) => (url.endsWith('/gravacao/config') ? json(200, CONFIG_LIGADA) : json(200, {})),
    aoMensagemRuntime: () => ({ ok: true }),
    aoMensagemAba: () => ({ ok: true }),
  }, extra || {}));
}

const PEDIDO = { tipo: 'iniciarGravacao', meeting_id: 'abc-defg-hij', tabId: 7, consentimento: true };

test('não grava sem a confirmação de que os participantes foram avisados', async () => {
  const bg = bgGravando();
  const r = await bg.enviar(Object.assign({}, PEDIDO, { consentimento: false }));
  assert.equal(r.ok, false);
  assert.match(r.error, /participantes foram avisados/);
  assert.deepEqual(bg.enviadosRuntime, []);
});

test('não grava sem login', async () => {
  const bg = bgGravando({ token: null });
  const r = await bg.enviar(PEDIDO);
  assert.match(r.error, /Entre na extensão/);
});

test('não grava com a gravação desligada no servidor', async () => {
  const bg = bgGravando({ fetch: () => json(200, { habilitada: false }) });
  const r = await bg.enviar(PEDIDO);
  assert.match(r.error, /desativada no servidor/);
  assert.deepEqual(bg.enviadosRuntime, []);
});

test('começa as 2 trilhas: aba no offscreen e microfone no content.js da aba certa', async () => {
  const bg = bgGravando();
  const r = await bg.enviar(PEDIDO);
  assert.equal(r.ok, true);
  const aba = bg.enviadosRuntime.find((m) => m.tipo === 'gravarAba');
  assert.deepEqual([aba.tabStreamId, aba.meeting_id, aba.bloco_s, aba.rotacao_s], ['stream-1', 'abc-defg-hij', 5, 600]);
  assert.deepEqual(bg.enviadosParaAbas.filter(([, m]) => m.tipo === 'gravarMicrofone').map(([id]) => id), [7]);
  assert.equal(bg.sessao.saleiaGravacao.ativa, true);
});

test('microfone recusado: a aba continua gravando e o motivo aparece', async () => {
  const bg = bgGravando({ aoMensagemAba: (_id, m) => (m.tipo === 'gravarMicrofone' ? { ok: false, error: 'NotAllowedError' } : { ok: true }) });
  const r = await bg.enviar(PEDIDO);
  assert.deepEqual([r.ok, r.microfone, r.erro_microfone], [true, false, 'NotAllowedError']);
  assert.match(bg.sessao.saleiaGravacao.microfone, /NotAllowedError/);
});

test('itens da fila vão ao servidor com o login e o consentimento só da reunião confirmada', async () => {
  const bg = bgGravando();
  await bg.enviar(PEDIDO);
  await bg.enviar({ tipo: 'gravacaoIniciar', corpo: { meeting_id: 'abc-defg-hij', track_id: 'aba', recording_id: 'rec-1', codec: 'audio/webm' } });
  await bg.enviar({ tipo: 'gravacaoIniciar', corpo: { meeting_id: 'xyz-wxyz-xyz', track_id: 'aba', recording_id: 'rec-2' } });
  await bg.esperar(30);
  const inicios = bg.fetches.filter(([u]) => u.endsWith('/gravacao/iniciar'));
  assert.deepEqual(inicios.map(([, o]) => JSON.parse(o.body).consentimento), [true, false]);
  assert.equal(inicios[0][1].headers.Authorization, 'Bearer tok-1');
  assert.equal(bg.filaEmMemoria.size, 0);
});

test('bloco vai só com os campos da rota (sem o blob nem meeting_id)', async () => {
  const bg = bgGravando();
  await bg.enviar({ tipo: 'gravacaoBloco', corpo: { recording_id: 'rec-1', meeting_id: 'abc-defg-hij', track_id: 'aba', sequence: 3,
    start_ms: 1, end_ms: 2, content_hash: 'h', recorded_at: 'x', audio_base64: 'QQ==', blob: {} } });
  await bg.esperar(30);
  const [, opts] = bg.fetches.find(([u]) => u.endsWith('/gravacao/bloco'));
  assert.deepEqual(Object.keys(JSON.parse(opts.body)).sort(),
    ['audio_base64', 'content_hash', 'end_ms', 'recorded_at', 'recording_id', 'sequence', 'start_ms']);
});

test('sem conexão: o bloco fica na fila', async () => {
  const bg = bgGravando({ fetch: () => Promise.reject(new Error('offline')) });
  await bg.enviar({ tipo: 'gravacaoBloco', corpo: { recording_id: 'rec-1', sequence: 0, start_ms: 1, end_ms: 2, content_hash: 'h', audio_base64: 'QQ==' } });
  await bg.esperar(30);
  assert.equal(bg.filaEmMemoria.size, 1);
  assert.equal(bg.sessao.saleiaGravacao.ultimo_erro, 'sem_conexao');
});

test('parar avisa as 2 trilhas e marca a gravação como encerrada', async () => {
  const bg = bgGravando();
  await bg.enviar(PEDIDO);
  const r = await bg.enviar({ tipo: 'controleGravacao', acao: 'parar' });
  assert.equal(r.ok, true);
  assert.ok(bg.enviadosRuntime.some((m) => m.tipo === 'controleGravacaoAba' && m.acao === 'parar'));
  assert.ok(bg.enviadosParaAbas.some(([id, m]) => id === 7 && m.tipo === 'controleGravacaoMic' && m.acao === 'parar'));
  assert.equal(bg.sessao.saleiaGravacao.ativa, false);
});

test('fila cheia recusa em vez de crescer sem limite', async () => {
  const fila = G.criarFilaDeEnvio({ armazenamento: armazenamentoEmMemoria(), enviar: async () => ({ status: 0 }), maxItens: 2 });
  await fila.adicionar('bloco', {}); await fila.adicionar('bloco', {});
  assert.deepEqual(await fila.adicionar('bloco', {}), { aceito: false, motivo: 'fila_cheia' });
});
