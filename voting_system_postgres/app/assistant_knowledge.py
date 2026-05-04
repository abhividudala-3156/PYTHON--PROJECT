from __future__ import annotations

SITE_KNOWLEDGE = """
SecureVote is a Flask + PostgreSQL voting website designed to run locally with pgAdmin 4.

Main user roles:
1. Public visitor: can view home page, election status, public results, and use the assistant.
2. Voter: registers with name, email, mobile number, age, constituency, address, password, photo, and ID proof. The voter must verify both email OTP and mobile OTP. Admin must approve the encrypted proof before voting. A voter can cast exactly one vote in their own constituency during the election window.
3. Candidate: registers with name, email, mobile number, age, constituency, party, symbol, manifesto, password, photo, and ID proof. The candidate must verify both email OTP and mobile OTP. Admin must approve the candidate before they appear on the ballot.
4. Admin: logs in using the configured ADMIN_ID and ADMIN_PASSWORD from .env. Admin can approve/reject voter proofs, approve/reject candidates, configure election start/end times, export CSV reports, view audit logs, download encrypted proof files after server-side decryption, and reset the election.

Security design:
- Passwords are hashed with Werkzeug PBKDF2.
- OTP values are hashed before being stored in PostgreSQL.
- Email OTP and mobile OTP are both required before a voter or candidate becomes verified.
- ID proof files are encrypted at rest using FILE_ENCRYPTION_KEY.
- CSRF protection is enabled for forms and JSON assistant requests.
- Login lockout starts after repeated failed login attempts.
- PostgreSQL transactions and a unique vote constraint enforce one vote per voter.
- Admin actions and important user actions are recorded in audit_log.
- OpenRouter API key stays server-side in .env and is never sent to the browser.

Common setup:
1. Create a PostgreSQL database named secure_voting in pgAdmin 4.
2. Copy .env.example to .env.
3. Set DATABASE_URL with the pgAdmin/PostgreSQL username and password.
4. Generate SECRET_KEY and FILE_ENCRYPTION_KEY.
5. Run: python manage.py init-db
6. Run: python manage.py run
7. Open: http://127.0.0.1:5000

Default local admin after init-db:
- ID: ADMIN001
- Password: admin123 unless changed in .env
For real deployment, change ADMIN_PASSWORD, SECRET_KEY, FILE_ENCRYPTION_KEY, enable HTTPS, set SESSION_COOKIE_SECURE=true, and configure SMTP/SMS delivery.
"""

LOCAL_FAQ = {
    "admin": "Admin login uses the ADMIN_ID and ADMIN_PASSWORD from your .env file. By default after running `python manage.py init-db`, use ID `ADMIN001` and password `admin123`. For real use, change ADMIN_PASSWORD in .env and run init-db again.",
    "otp": "Both email OTP and mobile OTP are required. In development mode, OTPs are shown as flash messages. In production, configure SMTP settings and SMS_API_URL/SMS_API_TOKEN in .env.",
    "database": "This website uses PostgreSQL. Create a database in pgAdmin 4, then set DATABASE_URL in .env like postgresql://postgres:your_password@localhost:5432/secure_voting.",
    "proof": "ID proof files are encrypted before saving. The admin can download them through the dashboard, where the server decrypts them using FILE_ENCRYPTION_KEY.",
    "vote": "A voter can vote only after email OTP, mobile OTP, admin proof approval, and an open election window. The database also has a unique constraint to prevent duplicate voting.",
    "candidate": "A candidate appears on the ballot only after email OTP, mobile OTP, admin approval, approved proof status, and matching constituency.",
    "openrouter": "Add OPENROUTER_API_KEY to .env to enable AI answers. The browser never receives your API key; requests go through the Flask server.",
}


def local_answer(message: str) -> str:
    text = (message or "").lower()
    for key, answer in LOCAL_FAQ.items():
        if key in text:
            return answer
    return (
        "I can help with this SecureVote website: voter registration, candidate registration, "
        "email/mobile OTP verification, admin approval, PostgreSQL setup, encrypted proof files, "
        "election timing, voting rules, reports, and OpenRouter assistant setup."
    )
