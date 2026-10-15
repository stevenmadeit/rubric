from typing import Any


PROMPT_VARIANTS = ("basic", "step_by_step", "structured")

_BASIC = (
    "Review the following code for an actual bug. Decide based only on the code; "
    "do not invent missing requirements. Respond as a JSON object with exactly "
    'these fields: {"has_bug": true or false, "explanation": "brief explanation"}. '
    "If there is no clear bug, set has_bug to false."
)

_STEP_BY_STEP = (
    "Analyze the code line by line to identify its behavior, inputs, and edge cases. "
    "Then decide whether there is an actual bug based only on the code; do not invent "
    "missing requirements. Return only a JSON object with exactly these fields: "
    '{"has_bug": true or false, "explanation": "concise bug description or why it is clean"}. '
    "Do not include private reasoning or a line-by-line trace in the response."
)

_STRUCTURED = (
    "Determine whether the code contains an actual bug. Base your answer only on the "
    "provided code; do not invent requirements. Return strict JSON with exactly the "
    '"has_bug" (boolean) and "explanation" (string) fields. Example: '
    'Input code: `def double(n): return n * 2` '
    'Output: {"has_bug": false, "explanation": "The function returns twice its input."}. '
    "For the code below, set has_bug to true only when there is a clear bug."
)

_PROMPTS = {
    "basic": _BASIC,
    "step_by_step": _STEP_BY_STEP,
    "structured": _STRUCTURED,
}


def build_prompt(variant: str, case: dict[str, Any]) -> str:
    if variant not in _PROMPTS:
        raise ValueError(
            f"Unknown prompt variant {variant!r}; choose from {', '.join(PROMPT_VARIANTS)}"
        )
    return (
        f"{_PROMPTS[variant]}\n\n"
        f"Language: {case['language']}\n"
        f"Code:\n```{case['language']}\n{case['code']}\n```"
    )
