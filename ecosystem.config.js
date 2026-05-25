module.exports = {
  apps: [{
    name: "saleia",
    script: "/root/SALEIA/SALEIA/venv/bin/python3",
    args: "-m uvicorn api.main:app --host 0.0.0.0 --port 8000",
    cwd: "/root/SALEIA/SALEIA",
    env: {
      OPENAI_API_KEY: process.env.OPENAI_API_KEY,
      ANTHROPIC_API_KEY: process.env.ANTHROPIC_API_KEY,
      GEMINI_API_KEY: process.env.GEMINI_API_KEY,
      GOOGLE_API_KEY: process.env.GOOGLE_API_KEY,
      AI_PROVIDER_ORDER: process.env.AI_PROVIDER_ORDER || "openai,anthropic,gemini",
      PATH: "/root/SALEIA/SALEIA/venv/bin:/usr/bin:/bin"
    },
    watch: false,
    restart_delay: 3000
  }]
}
