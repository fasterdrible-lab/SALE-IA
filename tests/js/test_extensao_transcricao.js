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
  assert.equal(corpo.fonte, 'aba');
  assert.deepEqual(bg.enviadosParaAbas.map(([id]) => id), [7]);
});

test('V.1.4.179: pedaço do microfone vai marcado e a resposta do servidor volta ao content.js', async () => {
  const bg = carregarBackground(resposta(true, 200, { texto: '', ok: true, motivo: 'microfone_desligado' }));
  const r = await bg.enviar({ tipo: 'whisperChunk', audio_base64: 'data:audio/webm;base64,AAAA',
    mime_type: 'audio/webm', meeting_id: 'abc-defg-hij', fonte: 'microfone', backendUrl: 'https://x' });
  const corpo = JSON.parse(bg.fetches.find(([u]) => u.endsWith('/audio-transcricao'))[1].body);
  assert.equal(corpo.fonte, 'microfone');
  assert.equal(r.motivo, 'microfone_desligado');
});

test('V.1.4.179: content.js para o microfone quando o servidor o desliga', () => {
  const src = fs.readFileSync(path.join(EXT, 'content.js'), 'utf8');
  const trecho = src.slice(src.indexOf("fonte: 'microfone'"), src.indexOf("commitarFrase('Vendedor', texto, 'audio')"));
  assert.match(trecho, /data\.motivo === 'microfone_desligado'[\s\S]*pararWhisper\(\)[\s\S]*return;/);
});

// ── V.1.4.180 (ext 1.4.26): transcrição em tempo real desligada ─────────

test('V.1.4.180: servidor desligou → background manda o offscreen parar e não repassa texto', async () => {
  const bg = carregarBackground(resposta(true, 200, { texto: '', ok: true, motivo: 'tempo_real_desligado' }));
  await bg.enviar({ tipo: 'audioChunk', base64: 'data:audio/webm;base64,AAAA', mimeType: 'audio/webm',
    fonte: 'aba', meeting_id: 'abc-defg-hij', tabId: 7 });
  assert.ok(bg.enviadosRuntime.some((m) => m.tipo === 'pararGravacaoOffscreen'));
  assert.deepEqual(bg.enviadosParaAbas, []);
});

test('V.1.4.180: captura da aba para transcrição é recusada com o servidor desligado', async () => {
  const bg = carregarBackground(resposta(true, 200, { habilitada: true, transcricao_tempo_real: false }));
  const r = await bg.enviar({ tipo: 'iniciarCaptura', meeting_id: 'abc-defg-hij', tabId: 7 });
  assert.equal(r.ok, false);
  assert.equal(r.desligada, true);
  assert.ok(!bg.enviadosRuntime.some((m) => m.tipo === 'iniciarGravacaoOffscreen'));
});

test('V.1.4.180: captura da aba segue funcionando com o servidor ligado', async () => {
  const bg = require('./background_falso.js').carregarBackground({
    fetch: () => Promise.resolve(resposta(true, 200, { transcricao_tempo_real: true })),
    aoMensagemRuntime: (m) => (m.tipo === 'iniciarGravacaoOffscreen' ? { ok: true } : undefined),
  });
  const r = await bg.enviar({ tipo: 'iniciarCaptura', meeting_id: 'abc-defg-hij', tabId: 7 });
  assert.equal(r.ok, true);
});

test('V.1.4.180: content.js para o microfone e esconde o botão; popup só mostra a captura se ligada', () => {
  const src = fs.readFileSync(path.join(EXT, 'content.js'), 'utf8');
  assert.match(src, /data\.motivo === 'tempo_real_desligado'\)\s*\{\s*pararWhisper\(\);\s*esconderBotaoWhisper\(\);/);
  assert.match(src, /transcricao_tempo_real === false\) esconderBotaoWhisper\(\)/);
  const popup = fs.readFileSync(path.join(EXT, 'popup.js'), 'utf8');
  assert.match(popup, /cfg\.transcricao_tempo_real === true\) capturaSecao\.style\.display = 'block'/);
  assert.doesNotMatch(popup, /meetingIdAtual = meetingId;\s*capturaSecao\.style\.display = 'block'/);
});

// ── V.1.4.27 (ext 1.4.27): legenda lida igual ao Tactiq ─────────────────

test('V.1.4.27: fala nova que começa igual a uma antiga da mesma pessoa não troca a antiga de lugar', () => {
  const t = [fala('Paulo', 'Aí sim.'), fala('Enzo', 'também'), fala('Paulo', 'Que bacana, hein, cara?'), fala('Enzo', 'não tô em casa')];
  const d = regras.decidirCommit(t, fala('Paulo', 'Aí sim foi corrido hoje. Eita,'), 0);
  assert.equal(d.acao, 'adicionar');
});

test('V.1.4.27: a legenda parcial ainda é completada quando é a última fala da pessoa', () => {
  const t = [fala('Paulo', 'Aí sim.'), fala('Enzo', 'também')];
  const d = regras.decidirCommit(t, fala('Paulo', 'Aí sim foi corrido hoje.'), 0);
  assert.deepEqual([d.acao, d.indice], ['substituir', 0]);
});

test('V.1.4.27: resposta curta da legenda entra na transcrição', () => {
  const t = [fala('Paulo', 'Tudo bem, graças a Deus. E você?')];
  assert.equal(regras.decidirCommit(t, fala('Enzo', 'bem'), 0).acao, 'adicionar');
});

test('V.1.4.27: legenda escondida da tela sem display:none e botão na sidebar', () => {
  const css = fs.readFileSync(path.join(EXT, 'sidebar.css'), 'utf8');
  const bloco = css.slice(css.indexOf('html.saleia-legenda-oculta'));
  assert.match(bloco, /opacity: 0 !important/);
  assert.doesNotMatch(bloco, /display:\s*none/);
  const src = fs.readFileSync(path.join(EXT, 'content.js'), 'utf8');
  assert.match(src, /id="saleia-btn-legenda"/);
  assert.match(src, /saleiaLegendaOculta !== false/);  // escondida por padrão
});

test('V.1.4.29: continuação de bloco já enviado entra só com o resto', () => {
  const t = [{ speaker: 'Ana', text: 'Tá dominado', bloco: 'Tá dominado', fonte: 'legenda' }];
  const d = regras.decidirCommit(t, fala('Ana', 'Tá dominado Só isso. Chama o bombeiro.'), 1);
  assert.deepEqual([d.acao, d.texto, d.bloco], ['adicionar', 'Só isso. Chama o bombeiro.', 'Tá dominado Só isso. Chama o bombeiro.']);
});

test('V.1.4.29: compara com o bloco inteiro, não só com o resto gravado', () => {
  const t = [{ speaker: 'Ana', text: 'Só isso.', bloco: 'Tá dominado Só isso.', fonte: 'legenda' }];
  const d = regras.decidirCommit(t, fala('Ana', 'Tá dominado Só isso. Tive a coragem'), 1);
  assert.deepEqual([d.acao, d.texto], ['adicionar', 'Tive a coragem']);
  assert.equal(regras.decidirCommit(t, fala('Ana', 'Tá dominado Só isso.'), 1).acao, 'ignorar');
  assert.equal(regras.jaGravada(t, 'Ana', 'Tá dominado Só isso.'), true);
});

// ── V.1.4.181 (ext 1.4.32): sessão encerrada ao sair da chamada ─────────

test('V.1.4.181: background avisa o servidor que a sessão acabou', async () => {
  const bg = carregarBackground(resposta(true, 200, { ok: true }));
  const r = await bg.enviar({ tipo: 'encerrarSessao', meeting_id: 'abc-defg-hij' });
  const chamada = bg.fetches.find(([u]) => u.endsWith('/encerrar-sessao'));
  assert.ok(chamada);
  assert.equal(chamada[1].method, 'POST');
  assert.deepEqual(JSON.parse(chamada[1].body), { meeting_id: 'abc-defg-hij' });
  assert.equal(r.ok, true);
});

test('V.1.4.181: content.js encerra ao sair da chamada ou fechar a aba e reabre ao voltar', () => {
  const src = fs.readFileSync(path.join(EXT, 'content.js'), 'utf8');
  assert.match(src, /window\.addEventListener\('pagehide', avisarFimDaSessao\)/);
  assert.match(src, /reuniaoAcabou\(window\.location\.pathname, MEETING_ID, botoesFim\)\)\s*\{[\s\S]*?avisarFimDaSessao\(\)/);
  assert.match(src, /sessaoEncerrada = false;[^\n]*\n\s*registrarSessao\(\);/);
});

test('V.1.4.183 (ext 1.4.33): fala do vendedor leva o nome do login; nome digitado em "Editar participantes" vale mais', () => {
  const src = fs.readFileSync(path.join(EXT, 'content.js'), 'utf8');
  assert.match(src, /chrome\.storage\.local\.get\(\['saleiaParticipantes', 'saleiaUsuario'\]/);
  assert.match(src, /if \(nomeLogado\) estado\.participantes\.vendedor = nomeLogado;/);
  assert.match(src, /if \(saved\.vendedor && saved\.vendedor !== 'Vendedor'\) estado\.participantes\.vendedor = saved\.vendedor;/);
});
