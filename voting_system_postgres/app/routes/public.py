from __future__ import annotations

from flask import Blueprint, render_template

from .. import db
from ..election import get_setting
from ..security import current_user

public_bp = Blueprint("public", __name__)


def _count(sql: str) -> int:
    row = db.fetch_one(sql)
    return int(row["count"] if row else 0)


@public_bp.get("/")
def home():
    stats = {
        "voters": _count("SELECT COUNT(*) AS count FROM voters WHERE role = 'voter'"),
        "candidates": _count("SELECT COUNT(*) AS count FROM candidates"),
        "approved": _count("SELECT COUNT(*) AS count FROM candidates WHERE status = 'approved'"),
        "votes": _count("SELECT COUNT(*) AS count FROM votes"),
    }
    return render_template("home.html", stats=stats)


@public_bp.get("/results")
def results():
    user = current_user() or {}
    public_enabled = get_setting("public_results_enabled", "true") != "false"
    if not public_enabled and user.get("role") != "admin":
        return render_template("results.html", rows=[], total_votes=0, hidden=True)
    rows = db.fetch_all(
        """
        SELECT candidate_id, name, party, symbol, constituency, votes
        FROM candidates
        WHERE status = 'approved'
        ORDER BY constituency ASC, votes DESC, name ASC
        """
    )
    total_votes = sum(row["votes"] for row in rows)
    return render_template("results.html", rows=rows, total_votes=total_votes, hidden=False)
