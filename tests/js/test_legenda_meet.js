// Leitura da legenda do Meet contra a estrutura REAL (fixtures/meet_legenda_20261015.html),
// conversa de referência copiada do Tactiq em 15/10/2026 (nomes trocados).
// Precisa de jsdom (não é dependência do projeto): sem ele o teste é pulado.
// Run: NODE_PATH=<pasta com node_modules/jsdom> node --test tests/js/test_legenda_meet.js
'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

let JSDOM = null;
try { ({ JSDOM } = require('jsdom')); } catch (e) { /* sem jsdom: pula */ }

const EXT = path.join(__dirname, '..', '..', 'chrome-extension');
const src = fs.readFileSync(path.join(EXT, 'content.js'), 'utf8').split('\r\n').join('\n');
const regras = fs.readFileSync(path.join(EXT, 'transcricao_rules.js'), 'utf8');
const quemRegras = fs.readFileSync(path.join(EXT, 'quem_e_quem_rules.js'), 'utf8');
const html = fs.readFileSync(path.join(__dirname, 'fixtures', 'meet_legenda_20261015.html'), 'utf8');

// Objetos criados dentro do jsdom são de outro realm: deepEqual estrito recusa.
const puro = (v) => JSON.parse(JSON.stringify(v));

function trecho(inicio, fim) {
  const a = src.indexOf(inicio);
  const b = src.indexOf(fim, a + inicio.length);
  if (a < 0 || b < 0) throw new Error('trecho não achado em content.js: ' + inicio);
  return src.slice(a, b);
}

// Monta a página com a área de legendas real e as funções de leitura do content.js.
function montar() {
  const codigo = [
    trecho('  function normalizarNomeParticipante', '\n  }\n') + '\n  }\n',
    trecho('  // A10 (V.1.4.20): fala cujo', '  function atualizarResumoParticipantes'),
    trecho('  const captionBuffer = {};', '  // A cada 800ms'),
    trecho('  // Padrões de ruído do Google Meet', '  function verificarLegendas() {'),
  ].join('\n');
  const dom = new JSDOM('<body>' + html + '</body>', { runScripts: 'outside-only' });
  const w = dom.window;
  w.eval(regras);
  w.eval(quemRegras);
  w.eval('var estado = { vendedorPadrao: "Carlos", quemEQuem: {}, quemEQuemPerguntado: true, transcricao: [], ultimoIndexEnviado: 0 };' +
    'function ocultarAvisoLegenda(){}; function atualizarResumoParticipantes(){}; var console = { log(){}, warn(){} };' + codigo +
    ';window.__t = { processarElementoLegenda, commitarFrase, captionBuffer, estado, detectarFalantePorEstrutura, bufferPronto, lerPessoasDaChamada, listaQuemEQuem, get legendasDetectadas() { return legendasDetectadas; } };');
  let relogio = 100000;
  w.Date.now = () => relogio;
  const regiao = w.document.querySelector('[role="region"]');
  const modelo = regiao.querySelector('.nMcdL');
  modelo.remove();
  const t = w.__t;

  // Meet escreve a fala aos pedaços; depois de ~3,5 s parada ela é gravada.
  function falar(nome, fala) {
    const b = modelo.cloneNode(true);
    b.querySelector('.NWpY1d').textContent = nome;
    const txt = b.querySelector('.ygicle');
    txt.textContent = '';
    regiao.insertBefore(b, regiao.querySelector('.IMKgW').previousElementSibling);
    const palavras = fala.split(' ');
    for (let i = 1; i <= palavras.length; i++) {
      txt.textContent = palavras.slice(0, i).join(' ');
      relogio += 300;
      t.processarElementoLegenda(txt);
    }
    relogio += 4000;
    Object.keys(t.captionBuffer).forEach((s) => {
      const buf = t.captionBuffer[s];
      if (relogio - buf.lastSeen > 3500) { t.commitarFrase(s, buf.texto, 'legenda', buf.curta, buf.inicio, buf.lastSeen); delete t.captionBuffer[s]; }
    });
    return b;
  }
  // Varredura de 800 ms do content.js (fecha a fala parada há > 3,5 s).
  function passar(ms) {
    for (let i = 0; i < ms; i += 500) {
      relogio += 500;
      Object.keys(t.captionBuffer).forEach((s) => {
        const buf = t.captionBuffer[s];
        if (t.bufferPronto(buf, relogio)) { t.commitarFrase(s, buf.texto, 'legenda', buf.curta, buf.inicio, buf.lastSeen); delete t.captionBuffer[s]; }
      });
    }
  }
  return { t, falar, w, passar, regiao, modelo };
}

const VENDEDOR_LONGO = 'Carlos Eduardo Pereira de Almeida Santos';  // 7 palavras
const CLIENTE = 'Bruno Tavares';
const CONVERSA = [
  [VENDEDOR_LONGO, 'Fala, Bruno.'], [CLIENTE, 'Bom,'],
  [VENDEDOR_LONGO, 'Tudo bem, graças a Deus. E você?'], [CLIENTE, 'bem'],
  [VENDEDOR_LONGO, 'Aí sim.'], [CLIENTE, 'também'],
  [VENDEDOR_LONGO, 'Que bacana, hein? Tá em casa ou no serviço?'],
  [CLIENTE, 'não tô em casa. Acabei de chegar'],
  [VENDEDOR_LONGO, 'Aí sim foi corrido hoje. Eita,'], [CLIENTE, 'sempre'],
  ['Você', 'parece que tá um pouco cansado.'],
  [CLIENTE, 'literalmente 18 horas, né?'], [CLIENTE, 'Fácil.'],
];

test('V.1.4.27: conversa sai igual ao Tactiq — todas as falas, na ordem, com o nome', { skip: !JSDOM && 'sem jsdom' }, () => {
  const { t, falar } = montar();
  CONVERSA.forEach(([nome, f]) => falar(nome, f));
  const esperado = CONVERSA.map(([nome, f]) => [nome === 'Você' ? 'Carlos' : nome, f]);
  assert.deepEqual(puro(t.estado.transcricao.map((x) => [x.speaker, x.text])), esperado);
});

test('V.1.4.27: nome vem do texto junto da foto; o próprio nome não vira fala', { skip: !JSDOM && 'sem jsdom' }, () => {
  const { t, falar } = montar();
  const bloco = falar('Ana Maria de Souza Lima Ferreira Costa', 'Pode me mandar a proposta?');
  assert.deepEqual(puro(t.detectarFalantePorEstrutura(bloco.querySelector('.ygicle'))),
    { nome: 'Ana Maria de Souza Lima Ferreira Costa', eONome: false });
  assert.deepEqual(puro(t.detectarFalantePorEstrutura(bloco.querySelector('.NWpY1d'))), { nome: null, eONome: true });
  assert.ok(!t.estado.transcricao.some((x) => x.text.startsWith('Ana Maria')));
});

test('V.1.4.28: Meet redesenhando o bloco com o mesmo texto não impede a fala de ser gravada', { skip: !JSDOM && 'sem jsdom' }, () => {
  // Console real de 15/10: o mesmo bloco ("Você" + fala) reprocessado várias
  // vezes por segundo com texto idêntico. Cada vez renovava o relógio de
  // silêncio e a fala nunca era gravada (painel vazio).
  const { t, passar, regiao, modelo } = montar();
  const b = modelo.cloneNode(true);
  b.querySelector('.NWpY1d').textContent = 'Você';
  const fala = 'A vida é feita de símbolo, né que ela começa a dar aquela vontade';
  b.querySelector('.ygicle').textContent = fala;
  regiao.insertBefore(b, regiao.querySelector('.IMKgW').previousElementSibling);
  for (let i = 0; i < 20; i++) {  // 10 s de redesenho, texto igual
    t.processarElementoLegenda(b.querySelector('.NWpY1d'));
    t.processarElementoLegenda(b.querySelector('.ygicle'));
    passar(500);
  }
  assert.deepEqual(puro(t.estado.transcricao.map((x) => [x.speaker, x.text])), [['Carlos', fala]]);
});

test('V.1.4.28: enquanto o texto cresce (pessoa falando) a fala não é cortada', { skip: !JSDOM && 'sem jsdom' }, () => {
  const { t, passar, regiao, modelo } = montar();
  const b = modelo.cloneNode(true);
  b.querySelector('.NWpY1d').textContent = CLIENTE;
  const txt = b.querySelector('.ygicle');
  regiao.insertBefore(b, regiao.querySelector('.IMKgW').previousElementSibling);
  const palavras = 'hoje a gente faz tudo na planilha e perde muito tempo com isso'.split(' ');
  palavras.forEach((_, i) => { txt.textContent = palavras.slice(0, i + 1).join(' '); t.processarElementoLegenda(txt); passar(1000); });
  passar(5000);
  assert.deepEqual(puro(t.estado.transcricao.map((x) => x.text)), [palavras.join(' ')]);
});

test('V.1.4.29: bloco que cresce (monólogo) entra só com o pedaço novo, sem repetir o já enviado', { skip: !JSDOM && 'sem jsdom' }, () => {
  // Teste real de 15/10 (sessão 506): a cada pausa o bloco inteiro entrava
  // de novo — "Tá dominado" / "Tá dominado Só isso…" / … em escada.
  const { t, passar, regiao, modelo } = montar();
  const b = modelo.cloneNode(true);
  b.querySelector('.NWpY1d').textContent = 'Você';
  const txt = b.querySelector('.ygicle');
  regiao.insertBefore(b, regiao.querySelector('.IMKgW').previousElementSibling);
  const etapas = ['Tá dominado', 'Só isso. Chama o bombeiro.', 'Tive a coragem de aceitar, dei uma chance.'];
  let bloco = '';
  etapas.forEach((pedaco) => {
    bloco = (bloco + ' ' + pedaco).trim();
    txt.textContent = bloco;
    t.processarElementoLegenda(txt);
    passar(5000);                                          // pausa: a fala é gravada
    t.estado.ultimoIndexEnviado = t.estado.transcricao.length;  // e enviada ao servidor
  });
  assert.deepEqual(puro(t.estado.transcricao.map((x) => x.text)), etapas);
  assert.equal(t.estado.transcricao.map((x) => x.text).join(' '), bloco);
});

test('V.1.4.29: bloco que cresce antes de ser enviado vira uma fala só', { skip: !JSDOM && 'sem jsdom' }, () => {
  const { t, passar, regiao, modelo } = montar();
  const b = modelo.cloneNode(true);
  b.querySelector('.NWpY1d').textContent = CLIENTE;
  const txt = b.querySelector('.ygicle');
  regiao.insertBefore(b, regiao.querySelector('.IMKgW').previousElementSibling);
  txt.textContent = 'Olha, o preço'; t.processarElementoLegenda(txt); passar(5000);
  txt.textContent = 'Olha, o preço ficou acima do que a gente imaginava'; t.processarElementoLegenda(txt); passar(5000);
  assert.deepEqual(puro(t.estado.transcricao.map((x) => x.text)), ['Olha, o preço ficou acima do que a gente imaginava']);
});

test('V.1.4.30: fala contínua sem pausa é gravada aos pedaços (a cada ~15 s), sem repetir', { skip: !JSDOM && 'sem jsdom' }, () => {
  // Teste real de 15/10 (der-vxjx-qab): monólogo de minutos, nenhuma pausa
  // de 3,5 s — a sidebar ficou em "1 frase" e nada chegava ao painel.
  const { t, passar, regiao, modelo } = montar();
  const b = modelo.cloneNode(true);
  b.querySelector('.NWpY1d').textContent = 'Você';
  const txt = b.querySelector('.ygicle');
  regiao.insertBefore(b, regiao.querySelector('.IMKgW').previousElementSibling);
  const palavras = Array.from({ length: 60 }, (_, i) => 'palavra' + i);
  let primeiraGravacaoEm = null;
  palavras.forEach((_, i) => {
    txt.textContent = palavras.slice(0, i + 1).join(' ');
    t.processarElementoLegenda(txt);
    passar(1000);  // 1 palavra por segundo, nunca 3,5 s parado
    if (primeiraGravacaoEm === null && t.estado.transcricao.length) primeiraGravacaoEm = i + 1;
    t.estado.ultimoIndexEnviado = t.estado.transcricao.length;  // envio a cada ciclo
  });
  passar(5000);
  assert.ok(primeiraGravacaoEm !== null && primeiraGravacaoEm <= 17, 'primeira gravação em ' + primeiraGravacaoEm + ' s');
  assert.ok(t.estado.transcricao.length >= 3);
  assert.equal(t.estado.transcricao.map((x) => x.text).join(' '), palavras.join(' '));  // tudo, na ordem, sem repetir
});

test('V.1.4.31: sem a área de legendas (CC desligado), texto de botão não vira fala nem conta como legenda', { skip: !JSDOM && 'sem jsdom' }, () => {
  // Teste real de 15/10 (der-vxjx-qab): depois do F5 o CC voltou desligado;
  // "Fazer upgrade" virou fala, a legenda foi dada como funcionando e o CC
  // nunca foi ligado. Sessão com 3 envios e 0 caracteres.
  const { t, passar, regiao, w } = montar();
  regiao.remove();
  const botao = w.document.createElement('span');
  botao.textContent = 'Fazer upgrade';
  const dica = w.document.createElement('div');
  dica.textContent = 'Faça upgrade para ter acesso aos recursos premium';
  w.document.body.append(botao, dica);
  t.processarElementoLegenda(botao);
  t.processarElementoLegenda(dica);
  passar(5000);
  assert.equal(t.estado.transcricao.length, 0);
  assert.equal(t.legendasDetectadas, false);
});

test('V.1.4.31: fala lida da área de legendas marca a legenda como funcionando', { skip: !JSDOM && 'sem jsdom' }, () => {
  const { t, falar } = montar();
  falar(CLIENTE, 'Pode me mandar a proposta?');
  assert.equal(t.legendasDetectadas, true);
});

test('V.1.4.34: participante sem foto (avatar de letra) não recebe o nome de quem tem foto', { skip: !JSDOM && 'sem jsdom' }, () => {
  // Teste real de 16/10 (fxc-nrmq-equ): celular como 2º participante, todas
  // as falas saíram com o nome do vendedor. Sem <img>, a busca subia do bloco
  // do cliente até a área inteira e pegava a foto/nome do bloco vizinho.
  const { t, w, passar, regiao, modelo } = montar();
  const doc = w.document;
  const comFoto = modelo.cloneNode(true);
  comFoto.querySelector('.NWpY1d').textContent = 'Você';
  comFoto.querySelector('.ygicle').textContent = 'Então, me conta como vocês fazem hoje o controle de estoque.';
  const semFoto = modelo.cloneNode(true);
  const img = semFoto.querySelector('img');
  const letra = doc.createElement('div');
  letra.className = 'avatar-letra';
  letra.textContent = 'P';
  img.replaceWith(letra);
  semFoto.querySelector('.NWpY1d').textContent = 'Pedro Lima';
  const ref = regiao.querySelector('.IMKgW').previousElementSibling;
  regiao.insertBefore(comFoto, ref);
  regiao.insertBefore(semFoto, ref);
  const fala = semFoto.querySelector('.ygicle');
  fala.textContent = 'Hoje a gente faz tudo na planilha, é bem manual mesmo.';
  assert.deepEqual(puro(t.detectarFalantePorEstrutura(fala)), { nome: 'Pedro Lima', eONome: false });
  t.processarElementoLegenda(comFoto.querySelector('.ygicle'));
  t.processarElementoLegenda(fala);
  passar(5000);
  assert.deepEqual(puro(t.estado.transcricao.map((x) => x.speaker)).sort(), ['Carlos', 'Pedro Lima']);
});

test('V.1.4.186: "quem é quem" — nome do Meet vira o nome real; "Você" vira o vendedor informado', { skip: !JSDOM && 'sem jsdom' }, () => {
  // Conta que só mostra o começo do e-mail na legenda ("fasterdrible").
  const { t, w, falar } = montar();
  w.eval('estado.quemEQuem = { "fasterdrible": { nome: "André", papel: "cliente" }, "Você": { nome: "Pedro", papel: "vendedor" } }');
  falar('fasterdrible', 'Pode me mandar a proposta?');
  falar('Você', 'Mando hoje ainda.');
  falar('Ana Souza', 'E o prazo de entrega?');
  assert.deepEqual(puro(t.estado.transcricao.map((x) => x.speaker)), ['André', 'Pedro', 'Ana Souza']);
  assert.deepEqual(puro(w.eval('_nomesVistos')), ['fasterdrible', 'Ana Souza']);
  assert.deepEqual(puro(t.listaQuemEQuem()), [
    { nome_meet: 'Você', nome: 'Pedro', papel: 'vendedor' },
    { nome_meet: 'fasterdrible', nome: 'André', papel: 'cliente' },
    { nome_meet: 'Ana Souza', nome: 'Ana Souza', papel: '' },
  ]);
});

test('V.1.4.186: sem "quem é quem", "Você" sai com o nome do login e os outros com o nome do Meet', { skip: !JSDOM && 'sem jsdom' }, () => {
  const { t, falar } = montar();
  falar('Você', 'Bom dia, tudo bem?');
  falar('fasterdrible', 'Tudo ótimo.');
  assert.deepEqual(puro(t.estado.transcricao.map((x) => x.speaker)), ['Carlos', 'fasterdrible']);
});

test('V.1.4.186: pessoas da chamada lidas dos quadros do Meet antes de falarem (sem o próprio vendedor)', { skip: !JSDOM && 'sem jsdom' }, () => {
  const { t, w } = montar();
  const doc = w.document;
  const quadro = (id, nome, extra) => {
    const d = doc.createElement('div');
    d.setAttribute('data-participant-id', id);
    d.innerHTML = '<span class="notranslate">' + nome + '</span><i>more_vert</i>' + (extra || '');
    return d;
  };
  const proprio = doc.createElement('div');
  proprio.setAttribute('data-self-name', 'Pedro Henrique');
  doc.body.append(proprio, quadro('a', 'Pedro Henrique'), quadro('b', 'fasterdrible'), quadro('c', 'Maria Clara (Você)'),
    quadro('d', 'fasterdrible'));
  const icone = doc.createElement('div');
  icone.setAttribute('data-participant-id', 'e');
  icone.innerHTML = '<i>mic_off</i>';
  doc.body.append(icone);
  t.lerPessoasDaChamada();
  assert.deepEqual(puro(w.eval('_nomesVistos')), ['fasterdrible']);
});

test('V.1.4.186: o próprio quadro (com "Reenquadrar") fica fora da lista; texto de botão não é nome', { skip: !JSDOM && 'sem jsdom' }, () => {
  // Teste real 16/10 (fpo-vjpg-rrx): sem data-self-name, a lista mostrou a
  // própria conta ("fasterdrible") e o botão "Reenquadrar".
  const { t, w } = montar();
  const doc = w.document;
  const proprio = doc.createElement('div');
  proprio.setAttribute('data-participant-id', 'eu');
  proprio.innerHTML = '<div><button aria-label="Reenquadrar"><span>Reenquadrar</span></button></div><span class="notranslate">fasterdrible</span>';
  const outro = doc.createElement('div');
  outro.setAttribute('data-participant-id', 'ele');
  outro.innerHTML = '<div role="button"><span>Fixar</span></div><span class="notranslate">motomec 17 GB</span>';
  doc.body.append(proprio, outro);
  t.lerPessoasDaChamada();
  assert.deepEqual(puro(w.eval('_nomesVistos')), ['motomec 17 GB']);
  // Só quem falou ou foi preenchido vai ao servidor.
  assert.deepEqual(puro(t.listaQuemEQuem(true).map((p) => p.nome_meet)), ['Você']);
});

test('V.1.4.186: área de legendas com classe "caption"/"a4cQT" — cada fala com o nome do PRÓPRIO bloco, e o nome não vira fala', { skip: !JSDOM && 'sem jsdom' }, () => {
  // Testes reais de 16/10: a busca antiga por classe pegava o 1º nome da
  // área inteira — tudo "ANDRE" (ele falou primeiro) e depois tudo "PAULO"
  // + a linha "PAULO: motomec 17 GB".
  const { t, w, falar, regiao } = montar();
  regiao.classList.add('a4cQT');
  w.eval('estado.quemEQuem = { "Você": { nome: "PAULO", papel: "vendedor" }, "motomec 17 GB": { nome: "JOSE", papel: "cliente" } }');
  falar('Você', 'teste teste testando para ver se esse negócio funciona');
  falar('motomec 17 GB', 'Manga chupa essa manga chupa essa manga.');
  assert.deepEqual(puro(t.estado.transcricao.map((x) => [x.speaker, x.text])), [
    ['PAULO', 'teste teste testando para ver se esse negócio funciona'],
    ['JOSE', 'Manga chupa essa manga chupa essa manga.'],
  ]);
});

test('A8 (ext 1.4.37): cada fala guarda início/fim; continuação de bloco já enviado começa onde a anterior acabou', { skip: !JSDOM && 'sem jsdom' }, () => {
  const { t, passar, regiao, modelo, w } = montar();
  const b = modelo.cloneNode(true);
  b.querySelector('.NWpY1d').textContent = 'Você';
  const txt = b.querySelector('.ygicle');
  regiao.insertBefore(b, regiao.querySelector('.IMKgW').previousElementSibling);
  const t0 = w.Date.now();
  txt.textContent = 'olha'; t.processarElementoLegenda(txt);
  passar(5000);  // pausa: "olha" gravada
  const primeira = t.estado.transcricao[0];
  assert.equal(primeira.inicio, t0);
  assert.equal(primeira.fim, t0);
  t.estado.ultimoIndexEnviado = 1;  // enviada
  passar(1000);
  txt.textContent = 'olha nos meus olhos'; t.processarElementoLegenda(txt);
  passar(2000);
  txt.textContent = 'olha nos meus olhos esqueçam que passou'; t.processarElementoLegenda(txt);
  passar(5000);
  const segunda = t.estado.transcricao[1];
  assert.equal(segunda.text, 'nos meus olhos esqueçam que passou');
  assert.ok(segunda.inicio >= primeira.fim, 'sem tempo contado 2 vezes');
  assert.ok(segunda.fim > segunda.inicio);
});
