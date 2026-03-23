"""
ROSA OS — Self-improvement analyzer.
Sends collected metrics to Kimi/Claude and asks for improvement suggestions.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger("rosa.self_improvement.analyzer")


ANALYSIS_PROMPT = """You are the self-improvement system of ROSA OS, a hybrid AI assistant platform.

You have been given metrics about recent failures and low-quality interactions. Your job is to:
1. Identify the root causes of the failures.
2. Propose specific, concrete improvements (to code, prompts, routing logic, or configuration).
3. Estimate the risk of each proposed change (low/medium/high).
4. Produce a structured JSON response.

## METRICS
{metrics_json}

## INSTRUCTIONS
Respond ONLY with valid JSON in this exact structure:
{{
  "summary": "One-sentence summary of the main issues",
  "root_causes": ["cause 1", "cause 2"],
  "proposals": [
    {{
      "title": "Short title",
      "description": "What to change and how",
      "target_file": "path/to/file.py or 'config' or 'prompt'",
      "risk": "low|medium|high",
      "expected_benefit": "What improves"
    }}
  ],
  "priority": "high|medium|low"
}}

Be conservative. Only propose changes you are confident about. Mark anything uncertain as high risk.
"""


class Analyzer:
    """Analyzes collected metrics and generates improvement proposals using an LLM."""

    async def analyze(self, metrics: dict[str, Any]) -> dict[str, Any]:
        """
        Send metrics to Kimi K2.5 (or fallback Claude) for analysis.

        Returns a dict with: summary, root_causes, proposals, priority
        """
        from core.config import get_settings
        settings = get_settings()

        metrics_json = json.dumps(metrics, indent=2, ensure_ascii=False)
        prompt = ANALYSIS_PROMPT.format(metrics_json=metrics_json)

        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(
                base_url=settings.openrouter_base_url,
                api_key=settings.openrouter_api_key,
            )

            response = await client.chat.completions.create(
                model=settings.cloud_model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a software engineering expert analyzing AI assistant failures. Respond only with valid JSON.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=2000,
            )

            content = response.choices[0].message.content or "{}"
            # Strip markdown code blocks if present
            content = content.strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
                content = content.strip()

            analysis = json.loads(content)
            logger.info("Analyzer: generated %d proposals", len(analysis.get("proposals", [])))
            return analysis

        except json.JSONDecodeError as exc:
            logger.error("Analyzer: failed to parse LLM response as JSON: %s", exc)
            return {
                "summary": "Analysis failed (JSON parse error)",
                "root_causes": ["LLM returned malformed JSON"],
                "proposals": [],
                "priority": "low",
                "error": str(exc),
            }
        except Exception as exc:
            logger.error("Analyzer: LLM call failed: %s", exc)
            return {
                "summary": f"Analysis failed: {exc}",
                "root_causes": [],
                "proposals": [],
                "priority": "low",
                "error": str(exc),
            }
