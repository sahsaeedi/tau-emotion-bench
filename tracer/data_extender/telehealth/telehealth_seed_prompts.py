from __future__ import annotations

SYSTEM_PROMPT = """You are filling deterministic telehealth scenario blueprints.

The blueprint already owns all IDs, dates, times, prescriptions, telemetry uploads, and regimen structure.

Your job is only to write concise, realistic clinical and operational text for the requested fields.

Do not change IDs, dates, times, numeric facts, telemetry metrics, medication names, or any structural fields.

Return valid JSON only."""


USER_PROMPT_TEMPLATE = """# Telehealth Blueprint Fill Task

Fill only the narrative fields requested in these deterministic telehealth blueprints.

## Requirements
- Return valid JSON only.
- Preserve every blueprint ID exactly.
- Do not invent or alter structural fields outside the requested narrative text.
- Keep the writing clinically plausible, concise, and internally consistent with the deterministic facts in the blueprint.
- For appointment text:
  - `chief_complaint` should be short and patient-facing.
  - `notes` should reflect logistics, follow-up needs, or visit framing.
- For medical records:
  - `subjective` should sound like patient-reported symptoms/history.
  - `assessment` should reflect the deterministic objective facts.
  - `plan` should be actionable and match the scenario category.
- For regimen plans:
  - `current_regimen_notes` should be 2-3 brief bullets.
  - each optimized regimen `focus` should be one concise sentence.
  - `synergy_notes` should be 2-3 short bullets grounded in the provided regimen structure.

## Output Shape
Return:
- top-level key `blueprints`
- one object per input blueprint containing:
  - `blueprint_id`
  - `appointments`
  - `medical_records`
  - `regimen_plans`

## Blueprint Batch
{batch_json}"""
