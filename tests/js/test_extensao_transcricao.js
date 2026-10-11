// Testes da extensão (auditoria T01 — P8, P11, P12, P20, P21, P22).
// Run: node --test tests/js/
'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const EXT = path.join(__dirname, '..', '..', 'chrome-extension');
const regras = require(path.join(EXT, 'transcricao_rules.js'));

const fala = (speaker, text, fonte) => ({ speaker, text, fonte: fonte || 'legenda' });

// ── Regra de gravação (transcricao_rules.js) ─────────────────────────────

test('P11: versão mais completa substitui a parcial ainda não enviada', () => {
  const t = [fala('Ana', 'Assim 3:30.')];
  const d = regras.decidirCommit(t, fala('Ana', 'Assim 3:30 a gente pode também terminar 6:30.'), 0);
  assert.deepEqual([d.acao, d.indice], ['substituir', 0]);
});

test('P11: parcial já enviada → a completa entra como nova (nada se perde)', () => {
  const t = [fala('Ana', 'Assim 3:30.')];
  const d = regras.decidirCommit(t, fala('Ana', 'Assim 3:30 a gente pode também terminar.'), 1);
  assert.equal(d.acao, 'adicionar');
});

test('P12: pontuação não impede reconhecer o pedaço de uma fala gravada', () => {
  const t = [fala('Ana', 'Assim, 3:30 a gente pode terminar.')];
  assert.equal(regras.decidirCommit(t, fala('Ana', 'Assim 3:30'), 0).acao, 'ignorar');
});

test('fala de outra pessoa que começa igual não é engolida', () => {
  const t = [fala('Cliente', 'Está caro.')];
  assert.equal(regras.decidirCommit(t, fala('Vendedor', 'Está caro em relação a quê exatamente?'), 0).acao, 'adicionar');
});

test('P8: falas parecidas de pessoas diferentes, ambas da legenda, ficam', () => {
  const t = [fala('Ana', 'a gente precisa ver isso com o financeiro primeiro')];
  const d = regras.decidirCommit(t, fala('Bruno', 'a gente precisa ver isso com o financeiro antes'), 0);
  assert.equal(d.acao, 'adicionar');
});

test('P8: mesma fala pela legenda e pelo áudio entra uma vez', () => {
  const t = [fala('Felipe', 'Caraca vocês estão botando um bichinho para trabalhar então, hein?')];
  const d = regras.decidirCommit(t, fala('Vendedor', 'Caraca, vocês estão botando bichinho pra trabalhar, então hein? Caraca!', 'audio'), 0);
  assert.equal(d.acao, 'ignorar');
});

test('legenda ainda na tela já gravada igual não é regravada pela varredura', () => {
  const t = [fala('Ana', 'Vamos fechar na sexta-feira.')];
  assert.equal(regras.jaGravada(t, 'Ana', 'vamos fechar na sexta feira'), true);
  assert.equal(regras.jaGravada(t, 'Bruno', 'vamos fechar na sexta feira'), false);
});

test('scripts de regras carregam antes do content.js no manifest', () => {
  const m = JSON.parse(fs.readFileSync(path.join(EXT, 'manifest.json'), 'utf8'));
  assert.deepEqual(m.content_scripts[0].js, ['transcricao_rules.js', 'gravacao_rules.js', 'content.js']);
});

test('todos os scripts da extensão têm sintaxe válida', () => {
  for (const f of fs.readdirSync(EXT).filter((n) => n.endsWith('.js'))) {
    assert.doesNotThrow(() => new vm.Script(fs.readFileSync(path.join(EXT, f), 'utf8'), { filename: f }), f);
  }
});

// ── background.js com um chrome falso ────────────────────────────────────

function carregarBackground(respostaFetch) {
  return require('./background_falso.js').carregarBackground({ fetch: () => Promise.resolve(respostaFetch) });
}

const resposta = (ok, status, corpo) => ({ ok, status, json: () => Promise.resolve(corpo) });

test('P22: erro HTTP do backend volta como falha para o content.js', async () => {
  const bg = carregarBackground(resposta(false, 500, { detail: 'Erro ao processar' }));
  const r = await bg.enviar({ tipo: 'fetchBackend', url: 'https://x/tempo-real', payload: {} });
  assert.equal(r.ok, false);
  assert.equal(r.status, 500);
});

test('P22: resposta 200 continua ok', async () => {
  const bg = carregarBackground(resposta(true, 200, { dica: 'x' }));
  const r = await bg.enviar({ tipo: 'fetchBackend', url: 'https://x/tempo-real', payload: {} });
  assert.deepEqual([r.ok, r.data.dica], [true, 'x']);
});

test('P20/P21: pedaço da aba usa a própria reunião e volta só para a aba capturada', async () => {
  const bg = carregarBackground(resposta(true, 200, { texto: 'quanto custa a implantação' }));
  await bg.enviar({ tipo: 'audioChunk', base64: 'data:audio/webm;base64,AAAA', mimeType: 'audio/webm',
    fonte: 'aba', meeting_id: 'abc-defg-hij', tabId: 7 });
  const corpo = JSON.parse(bg.fetches.find(([u]) => u.endsWith('/audio-transcricao'))[1].body);
  assert.equal(corpo.meeting_id, 'abc-defg-hij');
  assert.deepEqual(bg.enviadosParaAbas.map(([id]) => id), [7]);
});
