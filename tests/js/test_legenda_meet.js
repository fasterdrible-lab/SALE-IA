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
  w.eval('var estado = { participantes: { vendedor: "Carlos", clientes: ["Cliente"] }, transcricao: [], ultimoIndexEnviado: 0 };' +
    'function ocultarAvisoLegenda(){}; var console = { log(){}, warn(){} };' + codigo +
    ';window.__t = { processarElementoLegenda, commitarFrase, captionBuffer, estado, detectarFalantePorEstrutura };');
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
      if (relogio - buf.lastSeen > 3500) { t.commitarFrase(s, buf.texto, 'legenda', buf.curta); delete t.captionBuffer[s]; }
    });
    return b;
  }
  // Varredura de 800 ms do content.js (fecha a fala parada há > 3,5 s).
  function passar(ms) {
    for (let i = 0; i < ms; i += 500) {
      relogio += 500;
      Object.keys(t.captionBuffer).forEach((s) => {
        const buf = t.captionBuffer[s];
        if (relogio - buf.lastSeen > 3500) { t.commitarFrase(s, buf.texto, 'legenda', buf.curta); delete t.captionBuffer[s]; }
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
