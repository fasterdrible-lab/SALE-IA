"""
agent/visual_scenario.py — Visual Scenario AI

Gera cenários visuais personalizados do cliente durante a reunião usando IA.

Módulos:
  criar_tabela_visual_scenarios() — migração da tabela no MySQL
  PainExtractor                   — extrai contexto da transcrição via IA de texto
  PromptBuilder                   — constrói prompts para DALL-E 3
  ImageGenerator                  — gera imagens via OpenAI Images API
  ScenarioComposer                — orquestra o fluxo completo
"""

import json
import logging
import os
from datetime import datetime

import pymysql

logger = logging.getLogger("saleia.visual_scenario")


# ─────────────────────────────────────────────────────────
# BANCO DE DADOS
# ─────────────────────────────────────────────────────────

def _get_conn():
    return pymysql.connect(
        host=os.environ["DB_HOST"],
        port=int(os.environ.get("DB_PORT", 3306)),
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASS"],
        database=os.environ["DB_NAME"],
        charset="utf8mb4",
        connect_timeout=10,
    )


def criar_tabela_visual_scenarios():
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS visual_scenarios (
                    id            INT AUTO_INCREMENT PRIMARY KEY,
                    meeting_id    VARCHAR(100) NOT NULL,
                    context_json  LONGTEXT,
                    current_url   LONGTEXT,
                    future_url    LONGTEXT,
                    summary       TEXT,
                    pain_points   TEXT,
                    maturity      VARCHAR(50),
                    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_vs_meeting (meeting_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
        conn.commit()
        logger.info("[visual_scenario] Tabela visual_scenarios OK.")
    finally:
        conn.close()


def _salvar_cenario(meeting_id: str, context: dict, current_url: str,
                    future_url: str, summary: str, pain_points: list, maturity: str) -> int:
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO visual_scenarios
                   (meeting_id, context_json, current_url, future_url, summary, pain_points, maturity)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (
                    meeting_id,
                    json.dumps(context, ensure_ascii=False),
                    current_url,
                    future_url,
                    summary,
                    json.dumps(pain_points, ensure_ascii=False),
                    maturity,
                ),
            )
            new_id = cur.lastrowid
        conn.commit()
        return new_id
    finally:
        conn.close()


def listar_cenarios(meeting_id: str) -> list:
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, context_json, current_url, future_url, summary, pain_points, maturity, created_at
                   FROM visual_scenarios WHERE meeting_id = %s ORDER BY created_at DESC LIMIT 10""",
                (meeting_id,),
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    result = []
    for row in rows:
        try:
            context = json.loads(row[1]) if row[1] else {}
        except Exception:
            context = {}
        try:
            pain_points = json.loads(row[5]) if row[5] else []
        except Exception:
            pain_points = []
        result.append({
            "id": row[0],
            "context": context,
            "current_url": row[2],
            "future_url": row[3],
            "summary": row[4],
            "pain_points": pain_points,
            "maturity": row[6],
            "created_at": row[7].isoformat() if row[7] else None,
        })
    return result


# ─────────────────────────────────────────────────────────
# PAIN EXTRACTOR
# ─────────────────────────────────────────────────────────

_PAIN_EXTRACTOR_PROMPT = """Você é um consultor de vendas especialista em diagnóstico empresarial.

Analise a transcrição da reunião abaixo e extraia o contexto completo do cliente.

DADOS DISPONÍVEIS:
- Score de compra: {score}
- Perfil DISC: {disc_profile}
- Estado emocional inicial: {emotional_state}

TRANSCRIÇÃO:
{transcript}

Retorne APENAS um JSON válido sem markdown:
{{
  "segmento": "segmento do negócio do cliente (ex: varejo, serviços, industria)",
  "dores_principais": ["dor 1", "dor 2", "dor 3"],
  "emocoes_dominantes": "descreva as emoções principais identificadas (ansiedade, frustração, esperança...)",
  "maturidade_operacional": "iniciante|em_desenvolvimento|maduro",
  "gargalos": ["gargalo 1", "gargalo 2"],
  "urgencia": "alta|media|baixa",
  "perfil_disc_confirmado": "D|I|S|C",
  "potencial_crescimento": "alto|medio|baixo",
  "ambiente_atual_descricao": "descreva em 2 linhas o ambiente atual do cliente: caos, problemas visíveis, estilo de operação",
  "ambiente_futuro_descricao": "descreva em 2 linhas o ambiente futuro após solução: organização, crescimento, transformação",
  "tom_visual": "austero|dinamico|tecnico|emocional",
  "resumo_executivo": "2-3 frases resumindo o diagnóstico completo do cliente"
}}"""


class PainExtractor:
    """Extrai contexto, dores e perfil do cliente a partir da transcrição via IA."""

    async def extract(self, transcript: str, score: int = 0,
                      disc_profile: str = "", emotional_state: str = "") -> dict:
        from api.ai_router import chamar_ia_async

        prompt = _PAIN_EXTRACTOR_PROMPT.format(
            transcript=transcript[:6000],
            score=score,
            disc_profile=disc_profile or "não identificado",
            emotional_state=emotional_state or "não informado",
        )

        try:
            resultado = await chamar_ia_async(
                "Você é um especialista em diagnóstico empresarial. Responda APENAS com JSON válido.",
                prompt,
            )
            # Remove chaves internas de metadados da IA
            return {k: v for k, v in resultado.items() if not k.startswith("_")}
        except Exception as e:
            logger.error("[PainExtractor] Falha: %s", e)
            return {
                "segmento": "não identificado",
                "dores_principais": ["informações insuficientes na transcrição"],
                "emocoes_dominantes": "neutro",
                "maturidade_operacional": "em_desenvolvimento",
                "gargalos": [],
                "urgencia": "media",
                "perfil_disc_confirmado": disc_profile or "C",
                "potencial_crescimento": "medio",
                "ambiente_atual_descricao": "operação com desafios operacionais e processos manuais",
                "ambiente_futuro_descricao": "operação organizada com processos automatizados e crescimento consistente",
                "tom_visual": "tecnico",
                "resumo_executivo": "Cliente em processo de diagnóstico e estruturação do negócio.",
            }


# ─────────────────────────────────────────────────────────
# PROMPT BUILDER
# ─────────────────────────────────────────────────────────

_DISC_VISUAL = {
    "D": "executivo determinado, postura assertiva, ambiente de alto desempenho",
    "I": "profissional comunicativo, expressivo, ambiente dinâmico e social",
    "S": "gestor estável e confiável, ambiente colaborativo e estruturado",
    "C": "profissional analítico e metódico, ambiente de dados e processos precisos",
}

_MATURITY_DETAIL = {
    "iniciante":       "pequena empresa, processos totalmente manuais, equipe reduzida",
    "em_desenvolvimento": "empresa em crescimento, mistura de processos manuais e digitais",
    "maduro":          "empresa estabelecida, processos parcialmente digitalizados",
}

_URGENCY_INTENSITY = {
    "alta":  "crise operacional evidente, pressão máxima, prazo crítico",
    "media": "problemas recorrentes impactando resultados, necessidade de mudança",
    "baixa": "oportunidade de melhoria identificada, ritmo moderado de evolução",
}


class PromptBuilder:
    """Constrói prompts otimizados para DALL-E 3 baseados no contexto extraído."""

    def build_current(self, context: dict) -> str:
        disc = context.get("perfil_disc_confirmado", "C")
        disc_visual = _DISC_VISUAL.get(disc, _DISC_VISUAL["C"])
        segmento = context.get("segmento", "empresa")
        dores = "; ".join(context.get("dores_principais", [])[:3])
        gargalos = "; ".join(context.get("gargalos", [])[:2])
        maturity = _MATURITY_DETAIL.get(context.get("maturidade_operacional", "em_desenvolvimento"), "")
        urgency = _URGENCY_INTENSITY.get(context.get("urgencia", "media"), "")
        ambiente = context.get("ambiente_atual_descricao", "")

        return (
            "Cinematic corporate illustration, semi-realistic premium style, dramatic lighting. "
            f"A {disc_visual} in a chaotic {segmento} business environment. "
            f"{ambiente}. "
            f"Visible problems: {dores}. Bottlenecks: {gargalos}. {maturity}. {urgency}. "
            "Red and orange accent dashboards showing declining metrics, manual paperwork stacks, "
            "stressed team members in background, cluttered desk, multiple unresolved issues visible. "
            "Cinematic color grading: cool desaturated tones, dramatic shadows, tense atmosphere. "
            "Style: high-end consulting visual, NOT photorealistic, cinematic corporate illustration. "
            "No text overlays, no brand logos. Abstract professional figure, not a real person."
        )

    def build_future(self, context: dict) -> str:
        disc = context.get("perfil_disc_confirmado", "C")
        disc_visual = _DISC_VISUAL.get(disc, _DISC_VISUAL["C"])
        segmento = context.get("segmento", "empresa")
        potencial = context.get("potencial_crescimento", "medio")
        ambiente = context.get("ambiente_futuro_descricao", "")

        growth_scale = {
            "alto": "exceptional growth, market leadership, scale and innovation",
            "medio": "solid growth, organized operation, consistent results",
            "baixo": "stable foundation, reliable processes, sustainable evolution",
        }.get(potencial, "solid growth")

        return (
            "Cinematic corporate illustration, semi-realistic premium style, warm golden lighting. "
            f"A {disc_visual} in a transformed, thriving {segmento} business environment. "
            f"{ambiente}. {growth_scale}. "
            "Green and teal accent dashboards showing upward metrics, modern automated workflows, "
            "organized confident team, clean modern workspace, multiple monitors with positive data. "
            "Sense of control, clarity and scale. Bright professional atmosphere. "
            "Cinematic color grading: warm golden tones, soft highlights, peaceful confidence. "
            "Style: high-end consulting visual, NOT photorealistic, cinematic corporate illustration. "
            "No text overlays, no brand logos. Abstract professional figure, not a real person."
        )


# ─────────────────────────────────────────────────────────
# IMAGE GENERATOR
# ─────────────────────────────────────────────────────────

class ImageGenerator:
    """Gera imagens via DALL-E 3 (OpenAI). Retorna data URI base64 para persistência permanente."""

    async def generate(self, prompt: str, size: str = "1792x1024") -> str:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY não configurada.")

        import asyncio
        from openai import OpenAI

        def _call():
            client = OpenAI(api_key=api_key, timeout=90)
            response = client.images.generate(
                model="dall-e-3",
                prompt=prompt,
                size=size,
                quality="standard",
                n=1,
                response_format="b64_json",
            )
            b64 = response.data[0].b64_json
            return f"data:image/png;base64,{b64}"

        return await asyncio.to_thread(_call)


# ─────────────────────────────────────────────────────────
# SCENARIO COMPOSER
# ─────────────────────────────────────────────────────────

class ScenarioComposer:
    """Orquestra o fluxo completo: extração → prompts → geração → persistência."""

    def __init__(self):
        self.extractor = PainExtractor()
        self.builder = PromptBuilder()
        self.generator = ImageGenerator()

    async def compose(
        self,
        meeting_id: str,
        transcript: str,
        score: int = 0,
        disc_profile: str = "",
        emotional_state: str = "",
    ) -> dict:
        import asyncio

        logger.info("[ScenarioComposer] Iniciando para meeting_id=%s", meeting_id)

        # 1 — Extrai contexto via IA de texto
        context = await self.extractor.extract(
            transcript=transcript,
            score=score,
            disc_profile=disc_profile,
            emotional_state=emotional_state,
        )
        logger.info("[ScenarioComposer] Contexto extraído: segmento=%s", context.get("segmento"))

        # 2 — Constrói prompts
        prompt_atual = self.builder.build_current(context)
        prompt_futuro = self.builder.build_future(context)

        # 3 — Gera imagens em paralelo
        try:
            current_url, future_url = await asyncio.gather(
                self.generator.generate(prompt_atual),
                self.generator.generate(prompt_futuro),
            )
        except Exception as e:
            logger.error("[ScenarioComposer] Falha na geração de imagens: %s", e)
            raise RuntimeError(f"Erro ao gerar imagens: {e}")

        # 4 — Persiste no banco
        scenario_id = _salvar_cenario(
            meeting_id=meeting_id,
            context=context,
            current_url=current_url,
            future_url=future_url,
            summary=context.get("resumo_executivo", ""),
            pain_points=context.get("dores_principais", []),
            maturity=context.get("maturidade_operacional", ""),
        )

        logger.info("[ScenarioComposer] Cenário #%s salvo.", scenario_id)

        return {
            "scenario_id": scenario_id,
            "current_scenario_image": current_url,
            "future_scenario_image": future_url,
            "scenario_summary": context.get("resumo_executivo", ""),
            "detected_pain_points": context.get("dores_principais", []),
            "maturity_level": context.get("maturidade_operacional", ""),
            "context": context,
        }
