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

  const loginForm = document.getElementById('popup-login-form');
  const loginLogado = document.getElementById('popup-login-logado');
  const loginEmail = document.getElementById('login-email');
  const loginSenha = document.getElementById('login-senha');
  const btnLogin = document.getElementById('btn-login');
  const loginFeedback = document.getElementById('login-feedback');
  const loginUsuarioNome = document.getElementById('login-usuario-nome');
  const btnLogout = document.getElementById('btn-logout');

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
  // CONTA — login opcional (habilita o fallback pra conta Claude
  // do vendedor no tempo real quando os provedores centrais falharem)
  // ─────────────────────────────────────────────
  function exibirLogado(usuario) {
    loginForm.style.display = 'none';
    loginLogado.style.display = 'flex';
    loginUsuarioNome.textContent = 'Conectado como ' + ((usuario && usuario.nome) || 'vendedor');
  }

  function exibirFormularioLogin() {
    loginForm.style.display = 'block';
    loginLogado.style.display = 'none';
    loginEmail.value = '';
    loginSenha.value = '';
    loginFeedback.textContent = '';
    loginFeedback.className = 'popup-feedback';
  }

  chrome.runtime.sendMessage({ tipo: 'getAuth' }, function (resp) {
    if (resp && resp.logado) {
      exibirLogado(resp.usuario);
    } else {
      exibirFormularioLogin();
    }
  });

  function tentarLogin() {
    const email = loginEmail.value.trim();
    const senha = loginSenha.value;
    if (!email || !senha) {
      loginFeedback.textContent = 'Preencha e-mail e senha.';
      loginFeedback.className = 'popup-feedback popup-feedback-error';
      return;
    }
    btnLogin.disabled = true;
    loginFeedback.textContent = 'Entrando...';
    loginFeedback.className = 'popup-feedback';
    chrome.runtime.sendMessage({ tipo: 'fazerLogin', email: email, senha: senha }, function (resp) {
      btnLogin.disabled = false;
      if (resp && resp.ok) {
        exibirLogado(resp.usuario);
      } else {
        loginFeedback.textContent = (resp && resp.error) || 'Não foi possível entrar.';
        loginFeedback.className = 'popup-feedback popup-feedback-error';
      }
    });
  }

  if (btnLogin) btnLogin.addEventListener('click', tentarLogin);
  if (loginSenha) {
    loginSenha.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') tentarLogin();
    });
  }
  if (btnLogout) {
    btnLogout.addEventListener('click', function () {
      chrome.runtime.sendMessage({ tipo: 'logout' }, function () {
        exibirFormularioLogin();
      });
    });
  }

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
  // CAPTURA DE ÁUDIO DA ABA (Whisper) — Fase 3 do PROMPT MESTRE
  // Precisa ser disparada daqui: abrir o popup é o gesto que o Chrome
  // reconhece como "invocar a extensão", liberando chrome.tabCapture
  // pra aba ativa. Um botão dentro da própria página do Meet (content
  // script) nunca satisfaz esse requisito — achado real, 19/09/2026.
  // ─────────────────────────────────────────────
  const capturaSecao = document.getElementById('popup-captura-secao');
  const btnCapturaAudio = document.getElementById('btn-captura-audio');
  const capturaFeedback = document.getElementById('captura-feedback');

  function extrairMeetingId(url) {
    var m = (url || '').match(/\/([a-z]{3}-[a-z]{4}-[a-z]{3})/i);
    return m ? m[1] : null;
  }

  function atualizarBotaoCaptura(ativo) {
    if (!btnCapturaAudio) return;
    btnCapturaAudio.dataset.ativo = ativo ? '1' : '0';
    btnCapturaAudio.textContent = ativo ? 'Parar captura de áudio' : 'Iniciar captura de áudio';
  }

  var abaMeetId = null;
  var meetingIdAtual = null;

  chrome.tabs.query({ active: true, currentWindow: true }, function (tabs) {
    var tab = tabs && tabs[0];
    if (!tab || !tab.url || tab.url.indexOf('https://meet.google.com/') !== 0) return;
    var meetingId = extrairMeetingId(tab.url);
    if (!meetingId || !capturaSecao) return;

    abaMeetId = tab.id;
    meetingIdAtual = meetingId;
    prepararGravacao();

    // V.1.4.180 (ext 1.4.26): a captura da aba para transcrição só aparece
    // com a transcrição em tempo real ligada no servidor — ou ativa, para
    // poder parar.
    chrome.runtime.sendMessage({ tipo: 'statusCaptura' }, function (resp) {
      if (chrome.runtime.lastError) return;
      var ativa = !!(resp && resp.ativo);
      atualizarBotaoCaptura(ativa);
      if (ativa) { capturaSecao.style.display = 'block'; return; }
      fetch(backendAtual() + '/gravacao/config').then(function (r) { return r.json(); }).then(function (cfg) {
        if (cfg && cfg.transcricao_tempo_real === true) capturaSecao.style.display = 'block';
      }).catch(function () { /* servidor fora: sem captura */ });
    });
  });

  if (btnCapturaAudio) {
    btnCapturaAudio.addEventListener('click', function () {
      var jaAtiva = btnCapturaAudio.dataset.ativo === '1';
      btnCapturaAudio.disabled = true;
      capturaFeedback.textContent = jaAtiva ? 'Parando...' : 'Iniciando...';
      capturaFeedback.className = 'popup-feedback';

      if (jaAtiva) {
        chrome.runtime.sendMessage({ tipo: 'pararCaptura' }, function () {
          btnCapturaAudio.disabled = false;
          atualizarBotaoCaptura(false);
          capturaFeedback.textContent = 'Captura parada.';
          capturaFeedback.className = 'popup-feedback popup-feedback-success';
        });
        return;
      }

      chrome.runtime.sendMessage(
        { tipo: 'iniciarCaptura', meeting_id: meetingIdAtual, tabId: abaMeetId },
        function (resp) {
          btnCapturaAudio.disabled = false;
          if (chrome.runtime.lastError || !resp || !resp.ok) {
            var erro = chrome.runtime.lastError ? chrome.runtime.lastError.message : (resp && resp.error);
            capturaFeedback.textContent = 'Não foi possível iniciar: ' + (erro || 'erro desconhecido');
            capturaFeedback.className = 'popup-feedback popup-feedback-error';
            atualizarBotaoCaptura(false);
            return;
          }
          atualizarBotaoCaptura(true);
          capturaFeedback.textContent = 'Captura de áudio da aba ativa.';
          capturaFeedback.className = 'popup-feedback popup-feedback-success';
        }
      );
    });
  }

  // ─────────────────────────────────────────────
  // T02 — GRAVAR A REUNIÃO (aba + microfone)
  // Só com login, com a gravação ligada no servidor e com a confirmação
  // de que os participantes foram avisados (a cada reunião).
  // ─────────────────────────────────────────────
  const gravacaoSecao = document.getElementById('popup-gravacao-secao');
  const gravacaoCheck = document.getElementById('gravacao-consentimento');
  const gravacaoTexto = document.getElementById('gravacao-consentimento-texto');
  const gravacaoLabel = document.getElementById('gravacao-consentimento-label');
  const btnGravacao = document.getElementById('btn-gravacao');
  const gravacaoFeedback = document.getElementById('gravacao-feedback');
  var gravacaoAtiva = false;
  var gravacaoDisponivel = false;

  function feedbackGravacao(texto, tipo) {
    gravacaoFeedback.textContent = texto || '';
    gravacaoFeedback.className = 'popup-feedback' + (tipo ? ' popup-feedback-' + tipo : '');
  }

  function atualizarBotaoGravacao() {
    gravacaoLabel.style.display = gravacaoAtiva ? 'none' : 'flex';
    btnGravacao.textContent = gravacaoAtiva ? 'Encerrar gravação' : 'Gravar reunião';
    btnGravacao.disabled = !gravacaoDisponivel || (!gravacaoAtiva && !gravacaoCheck.checked);
  }

  function prepararGravacao() {
    if (!gravacaoSecao || !meetingIdAtual) return;
    gravacaoSecao.style.display = 'block';
    chrome.runtime.sendMessage({ tipo: 'statusGravacao' }, function (est) {
      if (chrome.runtime.lastError) return;
      gravacaoAtiva = !!(est && est.ativa && est.meeting_id === meetingIdAtual);
      chrome.runtime.sendMessage({ tipo: 'getAuth' }, function (auth) {
        if (!auth || !auth.logado) {
          gravacaoDisponivel = gravacaoAtiva;
          feedbackGravacao('Entre na extensão (acima) para gravar a reunião.', 'error');
          atualizarBotaoGravacao();
          return;
        }
        fetch(backendAtual() + '/gravacao/config').then(function (r) { return r.json(); }).then(function (cfg) {
          gravacaoDisponivel = gravacaoAtiva || !!cfg.habilitada;
          if (cfg.texto_consentimento) gravacaoTexto.textContent = cfg.texto_consentimento;
          if (!cfg.habilitada && !gravacaoAtiva) feedbackGravacao('Gravação de áudio desativada no servidor.', 'error');
          else if (gravacaoAtiva) feedbackGravacao('Gravando esta reunião.', 'success');
          atualizarBotaoGravacao();
        }).catch(function () {
          gravacaoDisponivel = gravacaoAtiva;
          feedbackGravacao('Servidor indisponível.', 'error');
          atualizarBotaoGravacao();
        });
      });
    });
  }

  if (gravacaoCheck) gravacaoCheck.addEventListener('change', atualizarBotaoGravacao);

  if (btnGravacao) btnGravacao.addEventListener('click', function () {
    btnGravacao.disabled = true;
    if (gravacaoAtiva) {
      feedbackGravacao('Encerrando...');
      chrome.runtime.sendMessage({ tipo: 'controleGravacao', acao: 'parar' }, function (r) {
        gravacaoAtiva = !(r && r.ok);
        gravacaoCheck.checked = false;
        feedbackGravacao(r && r.ok ? 'Gravação encerrada.' : 'Não foi possível encerrar: ' + ((r && r.error) || 'erro'), r && r.ok ? 'success' : 'error');
        atualizarBotaoGravacao();
      });
      return;
    }
    feedbackGravacao('Iniciando...');
    chrome.runtime.sendMessage({
      tipo: 'iniciarGravacao', meeting_id: meetingIdAtual, tabId: abaMeetId, consentimento: gravacaoCheck.checked === true,
    }, function (r) {
      if (chrome.runtime.lastError || !r || !r.ok) {
        feedbackGravacao('Não foi possível gravar: ' + ((r && r.error) || (chrome.runtime.lastError && chrome.runtime.lastError.message) || 'erro'), 'error');
        atualizarBotaoGravacao();
        return;
      }
      gravacaoAtiva = true;
      feedbackGravacao(r.microfone ? 'Gravando: participantes e seu microfone.'
        : 'Gravando só os participantes — seu microfone não: ' + (r.erro_microfone || 'erro'), r.microfone ? 'success' : 'error');
      atualizarBotaoGravacao();
    });
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
