/**
 * SALEIA — popup.js
 * Controles do popup da extensão Chrome.
 */

'use strict';

function escaparHtml(str) {
  if (str == null) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

document.addEventListener('DOMContentLoaded', function () {
  // Versão dinâmica a partir do manifest.json
  var versaoEl = document.getElementById('versao');
  if (versaoEl && chrome.runtime && chrome.runtime.getManifest) {
    versaoEl.textContent = 'v' + chrome.runtime.getManifest().version;
  }
  const toggleAtivo = document.getElementById('toggle-ativo');
  const apiToggleFeedback = document.getElementById('api-toggle-feedback');
  const conexaoStatus = document.getElementById('conexao-status');
  const statusTexto = document.getElementById('status-texto');
  const statusEl = document.getElementById('popup-status');
  const ultimasDicas = document.getElementById('ultimas-dicas');
  const btnRelatorio = document.getElementById('btn-relatorio');

  // URL do backend — configurada internamente (auto-corrigida em background.js),
  // nunca exibida na interface. Carregada uma vez para montar links/requisições.
  var backendUrlAtual = 'https://api.saleia.app.br';

  // ─────────────────────────────────────────────
  // CARREGAR CONFIGURAÇÕES SALVAS
  // ─────────────────────────────────────────────
  chrome.storage.local.get(
    ['saleiaAtivo', 'saleiaBackendUrl', 'saleiaUltimasDicas', 'saleiaUltimaAtualizacao'],
    function (result) {
      // Toggle on/off
      var ativo = result.saleiaAtivo !== false;
      toggleAtivo.checked = ativo;
      atualizarLabelApiToggle(ativo, false);

      if (result.saleiaBackendUrl) {
        backendUrlAtual = result.saleiaBackendUrl;
      }

      // Últimas dicas recebidas
      if (result.saleiaUltimasDicas) {
        exibirUltimasDicas(result.saleiaUltimasDicas, result.saleiaUltimaAtualizacao);
      }

      if (ativo) verificarConexao(); else marcarConexaoInativa();
    }
  );

  // ─────────────────────────────────────────────
  // VERIFICAR SE HÁ ABA DO MEET ATIVA
  // ─────────────────────────────────────────────
  chrome.tabs.query({ url: 'https://meet.google.com/*' }, function (tabs) {
    if (tabs && tabs.length > 0) {
      statusTexto.textContent = 'Monitorando reunião...';
      statusEl.classList.remove('popup-status-aguardando');
      statusEl.classList.add('popup-status-ativo');
    } else {
      statusTexto.textContent = 'Aguardando Google Meet...';
    }
  });

  // ─────────────────────────────────────────────
  // TOGGLE LIGAR/DESLIGAR API
  // ─────────────────────────────────────────────
  toggleAtivo.addEventListener('change', function () {
    const novoValor = toggleAtivo.checked;
    chrome.runtime.sendMessage({ tipo: 'setAtivo', valor: novoValor }, function () {
      statusTexto.textContent = novoValor ? 'Monitorando reunião...' : 'Pausado pelo usuário';
      atualizarLabelApiToggle(novoValor, true);
      if (novoValor) verificarConexao(); else marcarConexaoInativa();
    });
  });

  // ─────────────────────────────────────────────
  // BOTÃO VER RELATÓRIO COMPLETO
  // ─────────────────────────────────────────────
  btnRelatorio.addEventListener('click', function (e) {
    e.preventDefault();
    chrome.tabs.create({ url: backendAtual() + '/relatorio' });
  });

  // ─────────────────────────────────────────────
  // FUNÇÕES AUXILIARES
  // ─────────────────────────────────────────────

  // "API ativa" / "API desligada" — rótulo e mensagem de confirmação (só ao alternar)
  function atualizarLabelApiToggle(ativo, mostrarConfirmacao) {
    if (!apiToggleFeedback) return;
    if (ativo) {
      apiToggleFeedback.innerHTML = '<strong>API ativa</strong>' +
        (mostrarConfirmacao ? '<br>Conexão restabelecida.' : '');
    } else {
      apiToggleFeedback.innerHTML = '<strong>API desligada</strong><br>A extensão não enviará dados até ser reativada.';
    }
  }

  function backendAtual() {
    return backendUrlAtual;
  }

  function requisitarBackend(path, method, payload) {
    return new Promise(function (resolve, reject) {
      if (!chrome.runtime || !chrome.runtime.id) {
        reject(new Error('Extensão indisponível'));
        return;
      }

      chrome.runtime.sendMessage(
        {
          tipo: 'fetchBackend',
          url: backendAtual() + path,
          method: method || 'POST',
          payload: payload || {},
        },
        function (response) {
          if (chrome.runtime.lastError) {
            reject(new Error(chrome.runtime.lastError.message));
            return;
          }
          if (!response || !response.ok) {
            reject(new Error(response && response.error ? response.error : 'Falha na comunicação com o backend'));
            return;
          }
          resolve(response.data);
        }
      );
    });
  }

  // Com a API desligada, nenhuma chamada de rede deve ocorrer — nem para
  // checar conectividade.
  function marcarConexaoInativa() {
    if (!conexaoStatus) return;
    conexaoStatus.textContent = '—';
    conexaoStatus.className = 'popup-conexao popup-conexao-conectando';
  }

  // Indicador simples de conexão — sem nome de provedor, modelo ou URL
  // (informação técnica/administrativa não pertence à extensão do vendedor).
  function verificarConexao() {
    if (!conexaoStatus) return;
    conexaoStatus.textContent = 'Conectando...';
    conexaoStatus.className = 'popup-conexao popup-conexao-conectando';
    requisitarBackend('/health', 'GET')
      .then(function () {
        conexaoStatus.textContent = 'Conectado';
        conexaoStatus.className = 'popup-conexao popup-conexao-ok';
      })
      .catch(function () {
        conexaoStatus.textContent = 'Desconectado';
        conexaoStatus.className = 'popup-conexao popup-conexao-erro';
      });
  }

  function exibirUltimasDicas(dicas, timestamp) {
    if (!dicas) return;

    let html = '';
    if (dicas.proxima_acao) {
      html += '<div class="popup-dica"><span class="popup-dica-icon">💬</span>' + escaparHtml(dicas.proxima_acao) + '</div>';
    }
    if (dicas.perfil_disc && dicas.perfil_disc.tipo) {
      html += '<div class="popup-dica"><span class="popup-dica-icon">🎯</span>Perfil: <strong>' + escaparHtml(dicas.perfil_disc.tipo) + '</strong></div>';
    }
    if (dicas.sinal_financeiro) {
      html += '<div class="popup-dica"><span class="popup-dica-icon">💰</span>' + escaparHtml(dicas.sinal_financeiro) + '</div>';
    }
    if (timestamp) {
      html += '<div class="popup-dica-hora">Atualizado: ' + escaparHtml(new Date(timestamp).toLocaleTimeString('pt-BR')) + '</div>';
    }
    if (html) {
      ultimasDicas.innerHTML = html;
    }
  }

  // ─────────────────────────────────────────────
  // OUVIR ATUALIZAÇÕES DO STORAGE (novas dicas)
  // ─────────────────────────────────────────────
  chrome.storage.onChanged.addListener(function (changes) {
    if (changes.saleiaUltimasDicas) {
      exibirUltimasDicas(
        changes.saleiaUltimasDicas.newValue,
        changes.saleiaUltimaAtualizacao ? changes.saleiaUltimaAtualizacao.newValue : null
      );
    }
  });
});
