"""
Testes de reprodução — TAREFA 01 (auditoria da transcrição), 11/10/2026.

Cada teste marcado com `@unittest.expectedFailure` descreve o comportamento
CORRETO e hoje falha — é a reprodução de um defeito comprovado. A suíte
fica verde enquanto o defeito existir; quando ele for corrigido o teste
passa a dar "unexpected success" (falha a suíte) e a marcação deve ser
retirada. Os testes sem marcação são controles: provam o que já funciona.

Nenhum teste altera comportamento de produção. Banco: SQLite temporário
(MeetingMemory) e uma conexão falsa em memória (`sessoes`, que usa pymysql
direto). Matriz completa: docs/AUDITORIA_TRANSCRICAO_T01.md.

Run:
    python -m unittest tests.test_auditoria_transcricao_t01 -v
"""

import asyncio
import base64
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from sqlmodel import Session, create_engine, select

from agent import sessao_manager
from agent.transcript_dedup_rules import compactar_transcricao, eh_ruido_de_tela
from api import database


# ── Conexão falsa para agent/sessao_manager.py (pymysql direto) ─────────

class _BancoSessoesFalso:
    """Guarda a tabela `sessoes` em memória e entende as consultas que
    sessao_manager usa no caminho de tempo real, incluindo a janela de 6
    horas (na coluna que o SQL pedir: `created_at` ou `updated_at`)."""

    def __init__(self):
        self.linhas = []
        self.agora = datetime(2026, 10, 11, 12, 0, 0)

    def conectar(self):
        return _ConexaoFalsa(self)

    def texto(self, meeting_id):
        rows = [r for r in self.linhas if r["meeting_id"] == meeting_id]
        return rows[-1]["t"] if rows else ""


class _ConexaoFalsa:
    def __init__(self, banco):
        self.banco = banco

    def cursor(self):
        return _CursorFalso(self.banco)

    def commit(self):
        pass

    def close(self):
        pass


class _CursorFalso:
    def __init__(self, banco):
        self.banco = banco
        self._resultado = None
        self.lastrowid = None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def _ativas(self, meeting_id, coluna):
        limite = self.banco.agora - timedelta(hours=6)
        rows = [r for r in self.banco.linhas if r["meeting_id"] == meeting_id and r[coluna] >= limite]
        return sorted(rows, key=lambda r: r[coluna], reverse=True)

    def execute(self, sql, params=()):
        s = " ".join(sql.split()).upper()
        coluna = "updated_at" if "UPDATED_AT >= NOW()" in s else "created_at"
        if s.startswith("SELECT ID, TRANSCRICAO_ACUMULADA, NUM_ANALISES"):
            rows = self._ativas(params[0], coluna)
            self._resultado = (rows[0]["id"], rows[0]["t"], rows[0]["n"]) if rows else None
        elif s.startswith("SELECT ID, TRANSCRICAO_ACUMULADA"):
            rows = self._ativas(params[0], coluna)
            self._resultado = (rows[0]["id"], rows[0]["t"]) if rows else None
        elif s.startswith("SELECT ID FROM SESSOES"):
            rows = self._ativas(params[0], coluna)
            self._resultado = (rows[0]["id"],) if rows else None
        elif s.startswith("UPDATE SESSOES SET TRANSCRICAO_ACUMULADA = %S, ULTIMA_ANALISE"):
            row = next(r for r in self.banco.linhas if r["id"] == params[4])
            row["t"], row["n"], row["updated_at"] = params[0], params[3], self.banco.agora
        elif s.startswith("UPDATE SESSOES SET ULTIMA_ANALISE"):
            row = next(r for r in self.banco.linhas if r["id"] == params[3])
            row["n"], row["updated_at"] = params[2], self.banco.agora
        elif s.startswith("UPDATE SESSOES SET TRANSCRICAO_ACUMULADA"):
            row = next(r for r in self.banco.linhas if r["id"] == params[1])
            row["t"], row["updated_at"] = params[0], self.banco.agora
        elif s.startswith("INSERT INTO SESSOES"):
            colunas = [c.strip().lower() for c in s.split("(", 1)[1].split(")", 1)[0].split(",")]
            valores = [v.strip() for v in s.split("VALUES", 1)[1].strip()[1:-1].split(",")]
            dados, i = {}, 0
            for c, v in zip(colunas, valores):
                if v == "%S":
                    dados[c] = params[i]
                    i += 1
                else:
                    dados[c] = v.strip("'")
            novo = {"id": len(self.banco.linhas) + 1, "meeting_id": dados["meeting_id"],
                    "t": dados.get("transcricao_acumulada", ""), "n": int(dados.get("num_analises", 0)),
                    "created_at": self.banco.agora, "updated_at": self.banco.agora}
            self.banco.linhas.append(novo)
            self.lastrowid = novo["id"]
        else:
            raise AssertionError("SQL não esperado no teste: " + sql)

    def fetchone(self):
        return self._resultado


def _linhas(texto):
    return [l.strip() for l in (texto or "").splitlines() if l.strip()]


class _ComBancoSessoes(unittest.TestCase):
    MEETING = "abc-defg-hij"

    def setUp(self):
        self.banco = _BancoSessoesFalso()
        self.corpos_audio = set()
        for alvo, valor in ((sessao_manager, {"_get_conn": self.banco.conectar}),
                            (database, {"corpos_de_audio_recentes": lambda _m, **_k: self.corpos_audio})):
            p = patch.multiple(alvo, **valor)
            p.start()
            self.addCleanup(p.stop)
        sessao_manager.registrar_sessao(self.MEETING)  # /iniciar-sessao (content.js)


# ── 1. sessoes: o que a tela de Sessões, o RAG e a Conta Claude leem ────

class TestSessoesRepeteTexto(_ComBancoSessoes):

    def _ciclo_tempo_real(self, transcricao, enviado_ate, ia_rodou=True):
        """Mesma sequência de gravações de UM POST /tempo-real:
        api/main.py:930 (delta), processador_tempo_real.py:702 (janela,
        só quando a IA roda) e api/main.py:961 (janela, sempre)."""
        janela = "\n".join(transcricao[-60:])   # content.js::montarTranscricaoParcial
        delta = "\n".join(transcricao[enviado_ate:])  # content.js::montarTranscricaoDelta
        sessao_manager.salvar_transcricao_bruta(self.MEETING, delta)
        if ia_rodou:
            sessao_manager.salvar_analise(self.MEETING, janela, {})
        sessao_manager.salvar_analise(self.MEETING, janela, {})

    def test_cada_fala_aparece_uma_vez_apos_3_ciclos(self):
        falas = [f"Cliente: fala número {i} sobre o orçamento do projeto" for i in range(6)]
        for ciclo in range(3):
            self._ciclo_tempo_real(falas[: 2 * (ciclo + 1)], 2 * ciclo)
        contagem = {f: _linhas(self.banco.texto(self.MEETING)).count(f) for f in falas}
        # Antes da correção: a 1ª fala aparecia 7x (1 delta + 2 janelas x 3 ciclos).
        self.assertEqual(set(contagem.values()), {1}, contagem)

    def test_reenvio_do_mesmo_delta_apos_timeout_nao_duplica(self):
        # content.js só avança ultimoIndexEnviado na resposta; queda de
        # conexão depois de o servidor gravar = mesmo delta de novo.
        delta = "Cliente: o contrato tem fidelidade de doze meses?"
        sessao_manager.salvar_transcricao_bruta(self.MEETING, delta)
        sessao_manager.salvar_transcricao_bruta(self.MEETING, delta)
        self.assertEqual(_linhas(self.banco.texto(self.MEETING)).count(delta), 1)

    def test_mesma_fala_do_audio_e_do_tempo_real_aparece_uma_vez(self):
        # Antes: /audio-transcricao gravava "[Whisper Local] X" em `sessoes`
        # e a extensão devolvia o mesmo X como "Cliente: X" no /tempo-real.
        # Agora o áudio só registra o texto; quem grava é o /tempo-real (P3).
        from fastapi.testclient import TestClient
        import api.main as main

        texto = "quanto custa a implantação para as três lojas"
        registrados = []
        with patch.dict(main._TRANSCRICAO_FUNCOES, {"whisper": lambda c, prompt=None: (texto, "[Teste]")}), \
             patch.dict("os.environ", {"TRANSCRICAO_PROVEDOR": "whisper"}), \
             patch.object(main, "_prompt_whisper_da_reuniao", lambda _m: ""), \
             patch.object(database, "registrar_transcricao_audio", lambda m, t: registrados.append((m, t))):
            r = TestClient(main.app).post("/audio-transcricao", json={
                "audio_base64": base64.b64encode(b"\x00" * 2048).decode(),
                "mime_type": "audio/webm", "meeting_id": self.MEETING})
        self.assertEqual(r.json()["texto"], texto)
        self.assertEqual(registrados, [(self.MEETING, texto)])
        self.assertEqual(self.banco.texto(self.MEETING), "")  # nada gravado pelo áudio
        sessao_manager.salvar_transcricao_bruta(self.MEETING, f"Cliente: {texto}")
        ocorrencias = sum(1 for l in _linhas(self.banco.texto(self.MEETING)) if texto in l)
        self.assertEqual(ocorrencias, 1)

    def test_texto_de_tela_nao_e_gravado(self):
        sessao_manager.salvar_transcricao_bruta(
            self.MEETING, "João: Desativar som do microfone de liz ramos\nJoão: position: absolute;")
        self.assertEqual(self.banco.texto(self.MEETING).strip(), "")

    def test_reuniao_com_mais_de_6h_continua_gravando(self):
        # Reunião contínua: fala às 3h e às 6h01 do início da sessão.
        self.banco.agora += timedelta(hours=3)
        sessao_manager.salvar_transcricao_bruta(self.MEETING, "Cliente: vamos revisar a proposta agora")
        self.banco.agora += timedelta(hours=3, minutes=1)
        sessao_manager.salvar_transcricao_bruta(self.MEETING, "Cliente: então podemos fechar hoje")
        texto = self.banco.texto(self.MEETING)
        self.assertIn("revisar a proposta", texto)
        self.assertIn("podemos fechar hoje", texto)

    def test_controle_sala_parada_ha_mais_de_6h_nao_recebe_reuniao_nova(self):
        self.banco.agora += timedelta(hours=7)
        sessao_manager.salvar_transcricao_bruta(self.MEETING, "Cliente: reunião de outro dia")
        self.assertEqual(self.banco.texto(self.MEETING), "")

    def test_controle_fala_vinda_do_audio_junta_com_a_legenda(self):
        texto = "Então, o investimento fica em 12 mil reais por mês, com contrato de 1 ano."
        self.corpos_audio.add("então o investimento fica em 12 mil reais por mês com contrato de 1 ano")
        sessao_manager.salvar_transcricao_bruta(
            self.MEETING, "João: então o investimento fica em doze mil reais por mês com contrato de um ano")
        sessao_manager.salvar_transcricao_bruta(self.MEETING, f"Cliente: {texto}")
        self.assertEqual(len(_linhas(self.banco.texto(self.MEETING))), 1)


# ── 2. MeetingMemory: o que alimenta a IA e o relatório ─────────────────

class _ComMeetingMemory(unittest.TestCase):
    MEETING = "abc-defg-hij"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.engine = create_engine(f"sqlite:///{Path(self._tmp.name) / 't01.db'}")
        p = patch.object(database, "engine", self.engine)
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(self.engine.dispose)
        database.criar_tabelas()

    def registrar(self, texto):
        return database.registrar_transcricao_meeting(self.MEETING, texto)

    def transcript(self):
        return database.obter_meeting_memory(self.MEETING)["transcript_full"]


class TestMeetingMemoryDeduplicacao(_ComMeetingMemory):

    def test_controle_reenvio_exato_do_delta_e_descartado(self):
        delta = ("Cliente: o contrato tem fidelidade de doze meses?\n"
                 "Vendedor: tem sim, são doze meses de fidelidade")
        self.registrar(delta)
        self.registrar(delta)
        self.assertEqual(_linhas(self.transcript()), _linhas(delta))

    def test_reenvio_exato_de_fala_curta_e_descartado(self):
        # Corpo < 20 caracteres nunca é comparado — nem com cópia exata do
        # mesmo delta reenviado. "Sim, pode ser." entra 2x no retry.
        delta = "Cliente: o contrato tem fidelidade de doze meses?\nVendedor: tem sim, doze meses"
        self.registrar(delta)
        self.registrar(delta)
        self.assertEqual(_linhas(self.transcript()), _linhas(delta))

    def test_controle_legenda_e_whisper_da_mesma_fala_com_numeros(self):
        # Suspeita refutada (11/10): a similaridade junta as duas versões
        # (desde a correção do P8, só contra o texto que veio do áudio).
        audio = "Então, o investimento fica em 12 mil reais por mês, com contrato de 1 ano."
        database.registrar_transcricao_audio(self.MEETING, audio)
        self.registrar("João: então o investimento fica em doze mil reais por mês com contrato de um ano")
        self.registrar(f"Cliente: {audio}")
        self.assertEqual(len(_linhas(self.transcript())), 1)

    def test_controle_legenda_crescendo_com_pontuacao_fica_so_a_completa(self):
        texto = ("João: Assim 3:30.\nJoão: Assim 3:30 a gente poder também terminar.\n"
                 "João: Assim 3:30 a gente poder também terminar 6:30.")
        self.assertEqual(_linhas(compactar_transcricao(texto)),
                         ["João: Assim 3:30 a gente poder também terminar 6:30."])

    def test_legenda_revisada_pelo_meet_nao_vira_duas_falas(self):
        # O Meet reescreve o começo da frase ao reconhecer melhor — a versão
        # antiga não é prefixo da nova e fica junto (amostra real de 09/10).
        texto = ("João: pentear o cliente B ele tem uma loja física\n"
                 "João: perfil do cliente B ele tem uma loja física só que está começando do zero")
        self.assertEqual(len(_linhas(compactar_transcricao(texto))), 1)

    def test_objecao_repetida_mais_tarde_pelo_cliente_e_mantida(self):
        objecao = "Cliente: está muito caro para nós neste momento"
        self.registrar(objecao)
        for i in range(30):
            self.registrar(f"Vendedor: ponto {i} da apresentação sobre o método de trabalho")
        self.registrar(objecao)
        self.assertEqual(_linhas(self.transcript()).count(objecao), 2)

    def test_falas_parecidas_de_pessoas_diferentes_sao_mantidas(self):
        self.registrar("Ana: a gente precisa ver isso com o financeiro primeiro")
        self.registrar("Bruno: a gente precisa ver isso com o financeiro antes")
        self.assertEqual(len(_linhas(self.transcript())), 2)

    def test_dois_workers_ao_mesmo_tempo_nao_perdem_fragmento(self):
        # registrar_transcricao_meeting lê a linha, deduplica e grava o texto
        # inteiro de volta — sem lock. Simula o 2º worker gravando no meio.
        from agent import transcript_dedup_rules as regras
        original = regras.deduplicar_fragmento
        estado = {"primeira": True}

        def outro_worker_grava_no_meio(base, fragmento, **kw):
            if estado["primeira"]:
                estado["primeira"] = False
                database.registrar_transcricao_meeting(self.MEETING, "Cliente: fragmento do worker B")
            return original(base, fragmento, **kw)

        self.registrar("Vendedor: início da reunião")
        with patch.object(regras, "deduplicar_fragmento", outro_worker_grava_no_meio):
            self.registrar("Vendedor: fragmento do worker A")
        texto = self.transcript()
        self.assertIn("fragmento do worker A", texto)
        self.assertIn("fragmento do worker B", texto)

    def test_sala_recorrente_nao_herda_a_reuniao_de_outro_dia(self):
        # Salas fixas do Meet (ex.: mnk-kvoo-pyj, 36 dias) = 1 MeetingMemory
        # para sempre. O fim dela vai no prompt do Whisper da reunião nova.
        self.registrar("Cliente: reunião de ontem com o Carlos sobre o plano anual")
        with Session(self.engine) as s:
            row = s.exec(select(database.MeetingMemory)).first()
            row.created_at = row.updated_at = datetime.now() - timedelta(days=1)
            s.add(row)
            s.commit()
        self.assertNotIn("Carlos", database.obter_trecho_final_transcricao(self.MEETING))
        # A próxima gravação abre memória nova e arquiva a antiga (P5).
        self.registrar("Cliente: hoje quero falar do plano mensal")
        self.assertNotIn("Carlos", self.transcript())
        with Session(self.engine) as s:
            ids = sorted(r.meeting_id for r in s.exec(select(database.MeetingMemory)).all())
        self.assertEqual(ids[0], self.MEETING)
        self.assertTrue(ids[1].startswith(self.MEETING + "#"), ids)

    def test_controle_frase_diferente_do_mesmo_falante_nao_e_engolida(self):
        # P10 sem efeito colateral: começo parecido, assunto diferente.
        texto = ("João: a gente precisa ver com o financeiro\n"
                 "João: a gente precisa ver com o jurídico também antes de assinar")
        self.assertEqual(len(_linhas(compactar_transcricao(texto))), 2)

    def test_controle_reenvio_de_delta_que_cresceu(self):
        # Retry com o delta maior (índice não avançou): só as novas entram.
        self.registrar("Cliente: primeira pergunta sobre o prazo\nVendedor: Sim.")
        r = self.registrar("Cliente: primeira pergunta sobre o prazo\nVendedor: Sim.\nCliente: e o valor?")
        self.assertEqual(r["fragmento_aceito"], "Cliente: e o valor?")


class TestRuidoDeTela(unittest.TestCase):

    def test_controle_css_e_nome_sozinho_sao_ruido(self):
        self.assertTrue(eh_ruido_de_tela("position: absolute;"))
        self.assertTrue(eh_ruido_de_tela("João: Paulo Henrique Pagoti de Oliveira Silva"))

    def test_css_com_rotulo_de_falante_e_ruido(self):
        # _CSS_RE só testa a linha inteira; com "João: " na frente escapa.
        self.assertTrue(eh_ruido_de_tela("João: position: absolute;"))

    def test_aviso_de_microfone_de_participante_e_ruido(self):
        self.assertTrue(eh_ruido_de_tela("João: Desativar som do microfone de liz ramos"))


# ── 3. Contrato de entrada: sem ordem, sem idempotência ─────────────────

class TestContratoSemOrdem(unittest.TestCase):

    @unittest.expectedFailure
    def test_tempo_real_tem_sequencia_ou_chave_de_idempotencia(self):
        from api.main import TempoRealRequest
        campos = set(TempoRealRequest.model_fields)
        self.assertTrue(campos & {"sequence", "seq", "chunk_id", "idempotency_key"}, campos)

    @unittest.expectedFailure
    def test_audio_tem_sequencia_e_horario_de_gravacao(self):
        from api.main import AudioTranscricaoRequest
        campos = set(AudioTranscricaoRequest.model_fields)
        self.assertTrue({"sequence", "start_ms"} <= campos, campos)


# ── 4. /audio-transcricao trava o event loop do worker ──────────────────

class TestAudioTranscricaoBloqueiaLoop(unittest.TestCase):

    def test_transcricao_roda_fora_do_event_loop(self):
        # faster-whisper em CPU leva segundos por trecho de 15s; chamado
        # direto dentro do `async def`, para todas as requisições do worker
        # (inclusive /tempo-real de outras reuniões) enquanto transcreve.
        from fastapi.testclient import TestClient
        import api.main as main

        visto = {}

        def provedor_falso(caminho, prompt=None):
            try:
                asyncio.get_running_loop()
                visto["no_loop"] = True
            except RuntimeError:
                visto["no_loop"] = False
            return "", "[Teste]"

        with patch.dict(main._TRANSCRICAO_FUNCOES, {"whisper": provedor_falso}), \
             patch.dict("os.environ", {"TRANSCRICAO_PROVEDOR": "whisper"}), \
             patch.object(main, "_prompt_whisper_da_reuniao", lambda _m: ""):
            r = TestClient(main.app).post("/audio-transcricao", json={
                "audio_base64": base64.b64encode(b"\x00" * 2048).decode(),
                "mime_type": "audio/webm", "meeting_id": "default"})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(visto["no_loop"])


if __name__ == "__main__":
    unittest.main()
