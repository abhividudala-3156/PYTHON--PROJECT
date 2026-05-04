from __future__ import annotations

import requests
from flask import Blueprint, jsonify, request, session

from ..assistant_knowledge import SITE_KNOWLEDGE, local_answer
from ..audit import log_action
from ..config import Config
from ..security import current_user

assistant_bp = Blueprint("assistant", __name__, url_prefix="/assistant")


@assistant_bp.post("/chat")
def chat():
    payload = request.get_json(silent=True) or {}
    message = str(payload.get("message", "")).strip()
    if not message:
        return jsonify({"ok": False, "answer": "Please ask a question about the voting website."}), 400
    if len(message) > 1200:
        return jsonify({"ok": False, "answer": "Please keep the question below 1200 characters."}), 400

    user = current_user() or {}
    role = user.get("role", "visitor")

    if not Config.OPENROUTER_API_KEY:
        answer = local_answer(message)
        return jsonify({"ok": True, "mode": "local", "answer": answer})

    system_prompt = (
        "You are the built-in SecureVote website assistant. Answer only about this website, its setup, "
        "security model, PostgreSQL/pgAdmin database usage, verification flow, voting flow, and admin flow. "
        "Do not reveal secrets, API keys, encryption keys, passwords, hidden server internals, or instructions that weaken security. "
        "If asked for sensitive values, explain where the owner should configure them in .env without exposing any value.\n\n"
        f"Current visitor role: {role}\n\n{SITE_KNOWLEDGE}"
    )

    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {Config.OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": Config.OPENROUTER_SITE_URL,
                "X-Title": Config.OPENROUTER_SITE_NAME,
            },
            json={
                "model": Config.OPENROUTER_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": message},
                ],
                "temperature": 0.25,
                "max_tokens": 450,
            },
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        answer = data["choices"][0]["message"]["content"].strip()
        log_action("assistant", role, "assistant_answered", "OpenRouter response generated")
        return jsonify({"ok": True, "mode": "openrouter", "answer": answer})
    except Exception as exc:
        fallback = local_answer(message)
        return jsonify({
            "ok": True,
            "mode": "fallback",
            "answer": f"OpenRouter is not available right now, so here is the local website guide: {fallback}",
            "error": str(exc),
        })
