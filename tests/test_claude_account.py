import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cryptography.fernet import Fernet
from sqlmodel import create_engine

from agent import claude_account
from api import database


class ClaudeAccountDbTest(unittest.TestCase):
    """Testa isolamento por usuário e reuso de análise diretamente na camada de persistência
    (mesmo padrão de tests/test_meeting_memory.py: engine SQLite temporário)."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.db_path = Path(self._tmpdir.name) / "saleia_claude_account.db"
        self.engine = create_engine(f"sqlite:///{self.db_path}")
        self.engine_patch = patch.object(database, "engine", self.engine)
        self.engine_patch.start()
        self.addCleanup(self.engine_patch.stop)
        self.addCleanup(self.engine.dispose)
        database.criar_tabelas()

    def test_cada_usuario_ve_apenas_a_propria_conexao(self):
        database.salvar_claude_connection("user-a", "token-cripto-a")
        database.salvar_claude_connection("user-b", "token-cripto-b")

        conexao_a = database.obter_claude_connection("user-a")
        conexao_b = database.obter_claude_connection("user-b")

        self.assertEqual(conexao_a["oauth_token_encrypted"], "token-cripto-a")
        self.assertEqual(conexao_b["oauth_token_encrypted"], "token-cripto-b")
        self.assertEqual(conexao_a["status"], "ativo")

    def test_usuario_sem_conexao_retorna_none(self):
        self.assertIsNone(database.obter_claude_connection("nunca-conectou"))

    def test_disconnect_apaga_token_e_marca_inativo(self):
        database.salvar_claude_connection("user-a", "token-cripto-a")
        atualizado = database.desconectar_claude_connection("user-a")

        self.assertEqual(atualizado["status"], "inativo")
        self.assertIsNone(atualizado["oauth_token_encrypted"])

    def test_analise_repetida_com_mesma_transcricao_e_reaproveitada(self):
        registro = database.criar_claude_analysis_pendente("meeting-1", "user-a", "hash-123")
        database.finalizar_claude_analysis(registro["id"], status="sucesso", resultado={"dores": ["x"]})

        existente = database.obter_claude_analysis_por_hash("meeting-1", "user-a", "hash-123")

        self.assertIsNotNone(existente)
        self.assertEqual(existente["resultado"]["dores"], ["x"])

    def test_analise_com_hash_diferente_nao_e_reaproveitada(self):
        registro = database.criar_claude_analysis_pendente("meeting-1", "user-a", "hash-antigo")
        database.finalizar_claude_analysis(registro["id"], status="sucesso", resultado={"dores": ["x"]})

        existente = database.obter_claude_analysis_por_hash("meeting-1", "user-a", "hash-novo")
        self.assertIsNone(existente)

    def test_analise_de_outro_usuario_nao_e_reaproveitada(self):
        registro = database.criar_claude_analysis_pendente("meeting-1", "user-a", "hash-123")
        database.finalizar_claude_analysis(registro["id"], status="sucesso", resultado={"dores": ["x"]})

        existente = database.obter_claude_analysis_por_hash("meeting-1", "user-b", "hash-123")
        self.assertIsNone(existente)

    def test_feedback_so_pode_ser_gravado_pelo_dono_da_analise(self):
        registro = database.criar_claude_analysis_pendente("meeting-1", "user-a", "hash-123")
        database.finalizar_claude_analysis(registro["id"], status="sucesso", resultado={"dores": ["x"]})

        negado = database.salvar_claude_analysis_feedback(registro["id"], "user-b", "positivo")
        self.assertIsNone(negado)

        permitido = database.salvar_claude_analysis_feedback(registro["id"], "user-a", "positivo")
        self.assertEqual(permitido["feedback_rating"], "positivo")


class SanitizarErroClaudeTest(unittest.TestCase):
    def test_redige_token_oauth_do_claude_code(self):
        texto = "Falha de auth com token sk-ant-oat01-abcXYZ123_-longsecret"
        self.assertNotIn("abcXYZ123", claude_account.sanitizar_erro_claude(texto))
        self.assertIn("[REDACTED]", claude_account.sanitizar_erro_claude(texto))

    def test_redige_bearer_authorization(self):
        texto = "HTTP 401: Authorization Bearer abc.def.ghi rejeitado"
        self.assertNotIn("abc.def.ghi", claude_account.sanitizar_erro_claude(texto))

    def test_trunca_mensagens_muito_longas(self):
        texto = "erro " * 200
        self.assertLessEqual(len(claude_account.sanitizar_erro_claude(texto)), 410)


class ClassificacaoErroTest(unittest.TestCase):
    def test_mensagem_de_limite_vira_usage_limit_reached(self):
        with self.assertRaises(claude_account.ClaudeAccountError) as ctx:
            claude_account.ClaudeAccountExecutor._levantar_erro_classificado(
                "user-a", "Error: rate limit exceeded, please retry later", False
            )
        self.assertEqual(ctx.exception.code, "USAGE_LIMIT_REACHED")

    def test_mensagem_de_auth_vira_auth_required_e_marca_conexao_expirada(self):
        with patch.object(claude_account, "marcar_status_claude_connection") as mock_marcar:
            with self.assertRaises(claude_account.ClaudeAccountError) as ctx:
                claude_account.ClaudeAccountExecutor._levantar_erro_classificado(
                    "user-a", "401 Unauthorized: invalid api_key", False
                )
            self.assertEqual(ctx.exception.code, "AUTH_REQUIRED")
            mock_marcar.assert_called_once_with("user-a", "expirado")

    def test_mensagem_desconhecida_vira_generic_error(self):
        with self.assertRaises(claude_account.ClaudeAccountError) as ctx:
            claude_account.ClaudeAccountExecutor._levantar_erro_classificado(
                "user-a", "algo inesperado aconteceu", False
            )
        self.assertEqual(ctx.exception.code, "GENERIC_ERROR")

    def test_flag_de_rate_limit_do_evento_tem_prioridade(self):
        with self.assertRaises(claude_account.ClaudeAccountError) as ctx:
            claude_account.ClaudeAccountExecutor._levantar_erro_classificado(
                "user-a", "mensagem generica", True
            )
        self.assertEqual(ctx.exception.code, "USAGE_LIMIT_REACHED")


class ClaudeAccountExecutorTest(unittest.TestCase):
    """Testa a lógica de execute() (login/JSON/uso) sem depender do Claude Agent SDK real,
    isolando a chamada ao SDK via mock de _executar_query."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.db_path = Path(self._tmpdir.name) / "saleia_claude_executor.db"
        self.engine = create_engine(f"sqlite:///{self.db_path}")
        self.engine_patch = patch.object(database, "engine", self.engine)
        self.engine_patch.start()
        self.addCleanup(self.engine_patch.stop)
        self.addCleanup(self.engine.dispose)
        database.criar_tabelas()

    def test_execute_sem_conexao_levanta_login_required(self):
        executor = claude_account.ClaudeAccountExecutor()

        with self.assertRaises(claude_account.ClaudeAccountError) as ctx:
            asyncio.run(executor.execute(usuario_id="sem-conta", prompt="p", context="c"))

        self.assertEqual(ctx.exception.code, "LOGIN_REQUIRED")

    def test_execute_usa_apenas_a_conexao_do_proprio_usuario(self):
        database.salvar_claude_connection("user-a", "cripto-a")
        database.salvar_claude_connection("user-b", "cripto-b")

        chamadas = []

        async def fake_query(self_exec, usuario_id, prompt, token, timeout):
            chamadas.append((usuario_id, token))
            return '{"dores": ["dor-x"]}'

        with patch.object(claude_account, "descriptografar_token", side_effect=lambda v: f"plain-{v}"):
            with patch.object(claude_account.ClaudeAccountExecutor, "_executar_query", new=fake_query):
                executor = claude_account.ClaudeAccountExecutor()
                resultado = asyncio.run(executor.execute(usuario_id="user-a", prompt="p", context="c"))

        self.assertEqual(resultado["dores"], ["dor-x"])
        self.assertEqual(chamadas, [("user-a", "plain-cripto-a")])

        conexao_a = database.obter_claude_connection("user-a")
        self.assertIsNotNone(conexao_a["last_used_at"])

    def test_execute_propaga_erro_classificado_sem_marcar_uso(self):
        database.salvar_claude_connection("user-a", "cripto-a")

        async def fake_query_com_erro(self_exec, usuario_id, prompt, token, timeout):
            raise claude_account.ClaudeAccountError("USAGE_LIMIT_REACHED", claude_account.MSG_USAGE_LIMIT)

        with patch.object(claude_account, "descriptografar_token", side_effect=lambda v: f"plain-{v}"):
            with patch.object(claude_account.ClaudeAccountExecutor, "_executar_query", new=fake_query_com_erro):
                executor = claude_account.ClaudeAccountExecutor()
                with self.assertRaises(claude_account.ClaudeAccountError) as ctx:
                    asyncio.run(executor.execute(usuario_id="user-a", prompt="p", context="c"))

        self.assertEqual(ctx.exception.code, "USAGE_LIMIT_REACHED")
        conexao_a = database.obter_claude_connection("user-a")
        self.assertIsNone(conexao_a["last_used_at"])


class CriptografiaTokenTest(unittest.TestCase):
    def test_criptografar_e_descriptografar_ida_e_volta(self):
        chave = Fernet.generate_key().decode()
        with patch.dict(os.environ, {"CLAUDE_TOKEN_ENC_KEY": chave}, clear=False):
            cifrado = claude_account.criptografar_token("meu-token-secreto")
            self.assertNotIn("meu-token-secreto", cifrado)
            self.assertEqual(claude_account.descriptografar_token(cifrado), "meu-token-secreto")

    def test_sem_chave_configurada_levanta_erro_claro(self):
        ambiente_sem_chave = dict(os.environ)
        ambiente_sem_chave.pop("CLAUDE_TOKEN_ENC_KEY", None)
        with patch.dict(os.environ, ambiente_sem_chave, clear=True):
            with self.assertRaises(RuntimeError):
                claude_account.criptografar_token("qualquer-token")


class ClaudeAnalisarEndpointTest(unittest.TestCase):
    """POST /claude-account/analisar — cobre o campo opcional `transcricao`
    (análise manual/texto colado, sem sessão gravada em `sessoes`)."""

    @classmethod
    def setUpClass(cls):
        import api.main as _main  # noqa: dispara setup a nivel de modulo

        # Nota: NAO mockar api.database.criar_tabelas aqui — os testes desta
        # classe chamam a versao real em setUp() contra o engine sqlite
        # temporario de cada teste (mesmo padrao de ClaudeAccountDbTest).
        cls._patches = []
        for target in (
            "agent.sessao_manager.criar_tabela_sessoes",
            "agent.sessao_manager.criar_tabela_usuarios",
            "agent.visual_scenario.criar_tabela_visual_scenarios",
            "agent.sales_memory.criar_tabela_sales_memories",
        ):
            try:
                p = patch(target)
                p.start()
                cls._patches.append(p)
            except Exception:
                pass

        from fastapi.testclient import TestClient

        cls._ctx = TestClient(_main.app)
        cls.client = cls._ctx.__enter__()
        cls._main = _main
        cls.token = _main._gerar_token("user-manual", "vendedor@saleia.app.br", "vendedor")
        cls.auth_header = {"Authorization": f"Bearer {cls.token}"}

    @classmethod
    def tearDownClass(cls):
        cls._ctx.__exit__(None, None, None)
        for p in cls._patches:
            p.stop()

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        db_path = Path(self._tmpdir.name) / "saleia_claude_analisar.db"
        self.engine = create_engine(f"sqlite:///{db_path}")
        self.addCleanup(self.engine.dispose)
        engine_patch = patch.object(database, "engine", self.engine)
        engine_patch.start()
        self.addCleanup(engine_patch.stop)
        database.criar_tabelas()

        flag_patch = patch.dict(os.environ, {"CLAUDE_ACCOUNT_PILOT": "true"}, clear=False)
        flag_patch.start()
        self.addCleanup(flag_patch.stop)

    def _mock_execute(self, resultado):
        async def fake_execute(*args, **kwargs):
            return resultado

        return patch.object(claude_account.claude_account_executor, "execute", side_effect=fake_execute)

    def test_transcricao_colada_pula_busca_de_sessao_gravada(self):
        with patch(
            "agent.sessao_manager.obter_transcricao_mais_recente"
        ) as mock_busca, self._mock_execute({"recapitulacao": "ok", "dores": []}):
            r = self.client.post(
                "/claude-account/analisar",
                json={"meeting_id": "manual-abc123", "transcricao": "Vendedor: oi\nCliente: oi"},
                headers=self.auth_header,
            )

        self.assertEqual(r.status_code, 200)
        mock_busca.assert_not_called()
        self.assertEqual(r.json()["resultado"]["recapitulacao"], "ok")

    def test_sem_transcricao_ainda_busca_sessao_gravada_e_404_se_vazia(self):
        with patch("agent.sessao_manager.obter_transcricao_mais_recente", return_value="") as mock_busca:
            r = self.client.post(
                "/claude-account/analisar",
                json={"meeting_id": "meeting-real-1"},
                headers=self.auth_header,
            )

        self.assertEqual(r.status_code, 404)
        mock_busca.assert_called_once_with("meeting-real-1")

    def test_transcricao_colada_em_branco_e_tratada_como_ausente(self):
        with patch(
            "agent.sessao_manager.obter_transcricao_mais_recente", return_value=""
        ) as mock_busca:
            r = self.client.post(
                "/claude-account/analisar",
                json={"meeting_id": "meeting-real-2", "transcricao": "   "},
                headers=self.auth_header,
            )

        self.assertEqual(r.status_code, 404)
        mock_busca.assert_called_once_with("meeting-real-2")


if __name__ == "__main__":
    unittest.main()
