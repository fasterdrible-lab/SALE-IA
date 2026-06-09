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
  const backendUrlInput = document.getElementById('backend-url');
  const btnSalvarUrl = document.getElementById('btn-salvar-url');
  const urlFeedback = document.getElementById('url-feedback');
  const btnTrocarApi = document.getElementById('btn-trocar-api');
  const btnDefinirApi = document.getElementById('btn-definir-api');
  const provedorPreferido = document.getElementById('provedor-preferido');
  const apiStatus = document.getElementById('api-status');
  const apiFeedback = document.getElementById('api-feedback');
  const statusTexto = document.getElementById('status-texto');
  const statusEl = document.getElementById('popup-status');
  const ultimasDicas = document.getElementById('ultimas-dicas');
  const btnRelatorio = document.getElementById('btn-relatorio');

  // ─────────────────────────────────────────────
  // CARREGAR CONFIGURAÇÕES SALVAS
  // ─────────────────────────────────────────────
  chrome.storage.local.get(
    ['saleiaAtivo', 'saleiaBackendUrl', 'saleiaUltimasDicas', 'saleiaUltimaAtualizacao'],
    function (result) {
      // Toggle on/off
      toggleAtivo.checked = result.saleiaAtivo !== false;

      // URL do backend
      if (result.saleiaBackendUrl) {
        backendUrlInput.value = result.saleiaBackendUrl;
      }

      // Últimas dicas recebidas
      if (result.saleiaUltimasDicas) {
        exibirUltimasDicas(result.saleiaUltimasDicas, result.saleiaUltimaAtualizacao);
      }

      carregarStatusIA();
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
  // TOGGLE ATIVAR/DESATIVAR
  // ─────────────────────────────────────────────
  toggleAtivo.addEventListener('change', function () {
    const novoValor = toggleAtivo.checked;
    chrome.runtime.sendMessage({ tipo: 'setAtivo', valor: novoValor }, function () {
      statusTexto.textContent = novoValor ? 'Monitorando reunião...' : 'Pausado pelo usuário';
    });
  });

  // ─────────────────────────────────────────────
  // SALVAR URL DO BACKEND
  // ─────────────────────────────────────────────
  btnSalvarUrl.addEventListener('click', function () {
    const url = backendUrlInput.value.trim().replace(/\/$/, '');
    if (!url) return;

    chrome.runtime.sendMessage({ tipo: 'setBackendUrl', valor: url }, function () {
      mostrarFeedback('✅ URL salva com sucesso!', 'success');
      carregarStatusIA();
    });
  });

  if (btnTrocarApi) {
    btnTrocarApi.addEventListener('click', function () {
      const btn = this;
      btn.disabled = true;
      mostrarFeedbackApi('Trocando prioridade da IA...', 'success');

      requisitarBackend('/ai/provedor/proximo', 'POST', {})
        .then(function (data) {
          renderizarStatusIA(data);
          mostrarFeedbackApi(data && data.mensagem ? data.mensagem : 'Prioridade da IA atualizada.', 'success');
        })
        .catch(function (error) {
          console.warn('[SALEIA] Falha ao trocar provedor:', error.message);
          mostrarFeedbackApi('Não foi possível trocar a prioridade da IA: ' + error.message, 'error');
        })
        .finally(function () {
          btn.disabled = false;
        });
    });
  }

  if (btnDefinirApi && provedorPreferido) {
    btnDefinirApi.addEventListener('click', function () {
      const btn = this;
      const provedor = provedorPreferido.value;
      btn.disabled = true;
      mostrarFeedbackApi('Definindo provedor preferido...', 'success');

      requisitarBackend('/ai/provedor/preferido', 'POST', { provedor: provedor })
        .then(function (data) {
          renderizarStatusIA(data);
          mostrarFeedbackApi(data && data.mensagem ? data.mensagem : 'Provedor preferido atualizado.', 'success');
        })
        .catch(function (error) {
          console.warn('[SALEIA] Falha ao definir provedor:', error.message);
          mostrarFeedbackApi('Nao foi possivel definir o provedor: ' + error.message, 'error');
        })
        .finally(function () {
          btn.disabled = false;
        });
    });
  }

  // ─────────────────────────────────────────────
  // BOTÃO VER RELATÓRIO COMPLETO
  // ─────────────────────────────────────────────
  btnRelatorio.addEventListener('click', function (e) {
    e.preventDefault();
    const url = backendUrlInput.value.trim().replace(/\/$/, '') + '/relatorio';
    chrome.tabs.create({ url: url });
  });

  // ─────────────────────────────────────────────
  // FUNÇÕES AUXILIARES
  // ─────────────────────────────────────────────
  function mostrarFeedback(mensagem, tipo) {
    urlFeedback.textContent = mensagem;
    urlFeedback.style.display = 'block';
    urlFeedback.className = 'popup-feedback popup-feedback-' + tipo;
    setTimeout(function () {
      urlFeedback.style.display = 'none';
    }, 3000);
  }

  function mostrarFeedbackApi(mensagem, tipo) {
    if (!apiFeedback) return;
    apiFeedback.textContent = mensagem;
    apiFeedback.style.display = 'block';
    apiFeedback.className = 'popup-feedback popup-feedback-' + tipo;
    setTimeout(function () {
      apiFeedback.style.display = 'none';
    }, 3500);
  }

  function backendAtual() {
    return backendUrlInput.value.trim().replace(/\/$/, '') || 'https://api.saleia.app.br';
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

  function classificarStatus(status) {
    if (!status) return 'desconhecido';
    if (status.indexOf('cooldown') === 0) return 'cooldown';
    if (status.indexOf('degradado') === 0) return 'degradado';
    return status;
  }

  function labelStatus(status) {
    if (!status) return 'Desconhecido';
    if (status === 'ok') return 'OK';
    if (status === 'sem_chave') return 'Sem chave';
    if (status.indexOf('cooldown') === 0) return 'Cooldown';
    if (status.indexOf('degradado') === 0) return 'Degradado';
    return status.replace(/_/g, ' ');
  }

  function formatarNomeProvedor(nome) {
    if (!nome) return 'Provedor';
    return nome.charAt(0).toUpperCase() + nome.slice(1);
  }

  function renderizarStatusIA(payload) {
    if (!apiStatus) return;

    const ia = payload && payload.ia ? payload.ia : {};
    const ordem = Array.isArray(payload && payload.ordem_ia) ? payload.ordem_ia : Object.keys(ia);
    const preferido = payload && payload.provedor_preferido ? payload.provedor_preferido : (ordem[0] || 'indisponível');
    const estadoBackend = payload && payload.status ? payload.status : 'desconhecido';

    if (provedorPreferido && preferido) {
      provedorPreferido.value = preferido;
    }

    let html = '<div class="popup-api-summary">Backend: ' + escaparHtml(estadoBackend) + ' | Prioridade: <strong>' + escaparHtml(formatarNomeProvedor(preferido)) + '</strong></div>';
    html += '<div class="popup-api-list">';

    if (!ordem.length) {
      html += '<div class="popup-api-item"><div>Nenhum provedor configurado.</div><div class="popup-api-label desconhecido">indisponível</div></div>';
    } else {
      ordem.forEach(function (nome, index) {
        const item = ia[nome] || {};
        const status = item.status || 'desconhecido';
        const classeStatus = classificarStatus(status);
        const modelo = item.modelo ? '<div class="popup-api-meta">' + escaparHtml(item.modelo) + '</div>' : '';
        const falhas = typeof item.falhas_consecutivas === 'number'
          ? '<div class="popup-api-meta">Falhas: ' + item.falhas_consecutivas + '</div>'
          : '';

        html += '<div class="popup-api-item">';
        html += '<div>';
        html += '<strong>' + (index + 1) + '. ' + escaparHtml(formatarNomeProvedor(nome)) + '</strong>';
        html += modelo + falhas;
        html += '</div>';
        html += '<div class="popup-api-label ' + escaparHtml(classeStatus) + '">' + escaparHtml(labelStatus(status)) + '</div>';
        html += '</div>';
      });
    }

    html += '</div>';
    apiStatus.innerHTML = html;
  }

  function carregarStatusIA() {
    if (!apiStatus) return;
    apiStatus.textContent = 'Carregando status das APIs...';
    requisitarBackend('/health', 'GET')
      .then(function (data) {
        renderizarStatusIA(data);
      })
      .catch(function (error) {
        apiStatus.textContent = 'Não foi possível carregar o status das APIs: ' + error.message;
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
