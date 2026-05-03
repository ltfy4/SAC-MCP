# SAC-MCP Agent Client

Interactive test harness that connects to the SAC-MCP server and lets you
query your SAC tenant through an LLM.

## Setup

1. Install the main project: `cd .. && pip install -e ".[dev]"`
2. Install agent deps: `pip install -r requirements.txt`
3. Configure SAC credentials in `../.env`
4. Set your LLM API key: `export ANTHROPIC_API_KEY=sk-...`

## Run

```bash
python agent.py
```

## Example session

```
Connected! 50 tools available.

You: What models are available on this tenant?
Assistant: I'll check the available models for you.
[Calling list_models({})]
There are 3 models on your tenant:
1. BestRunJuice_SampleModel — Sales data
2. HR_Planning_2024 — Headcount planning
3. Finance_Actuals — GL actuals

You: Show me the fact data for BestRunJuice where Region is EMEA
Assistant: [Calling smart_query with model_id=BestRunJuice_SampleModel...]
Here are the EMEA results (showing first 10 rows):
...

You: quit
```

## Configuration

| Variable          | Default                      | Description                        |
| ----------------- | ---------------------------- | ---------------------------------- |
| `LLM_PROVIDER`    | `anthropic`                  | `anthropic` or `openai`            |
| `ANTHROPIC_MODEL` | `claude-sonnet-4-20250514`   | Anthropic model ID                 |
| `OPENAI_MODEL`    | `gpt-4o`                     | OpenAI model ID                    |
