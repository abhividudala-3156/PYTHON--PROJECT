from __future__ import annotations

import argparse
import secrets
import sys

from cryptography.fernet import Fernet
from werkzeug.security import generate_password_hash

from app import create_app, db
from app.config import Config

app = create_app()


def init_db() -> None:
    db.init_schema()
    # Admin seeding must not fail when the default local password is admin123.
    # The normal voter/candidate registration path still enforces a stronger password policy.
    admin_hash = generate_password_hash(Config.ADMIN_PASSWORD, method="pbkdf2:sha256", salt_length=16)
    with db.transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO voters (
                    voter_id, name, email, phone, age, constituency, address, password_hash,
                    role, email_verified, phone_verified, is_verified, proof_status
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'admin', TRUE, TRUE, TRUE, 'approved')
                ON CONFLICT (voter_id) DO UPDATE SET
                    name = EXCLUDED.name,
                    email = EXCLUDED.email,
                    phone = EXCLUDED.phone,
                    password_hash = EXCLUDED.password_hash,
                    role = 'admin',
                    email_verified = TRUE,
                    phone_verified = TRUE,
                    is_verified = TRUE,
                    proof_status = 'approved',
                    updated_at = NOW()
                """,
                (
                    Config.ADMIN_ID,
                    Config.ADMIN_NAME,
                    Config.ADMIN_EMAIL,
                    "0000000000",
                    30,
                    "System",
                    "Admin Office",
                    admin_hash,
                ),
            )
            cur.execute(
                """
                INSERT INTO audit_log (actor_role, actor_identifier, action, details)
                VALUES ('system', %s, 'init_db', 'Database initialized/upgraded and admin upserted')
                """,
                (Config.ADMIN_ID,),
            )
    print("Database initialized/upgraded successfully.")
    print(f"Admin ID: {Config.ADMIN_ID}")
    print(f"Admin Password: {Config.ADMIN_PASSWORD}")
    if Config.ADMIN_PASSWORD == "admin123":
        print("Security note: change ADMIN_PASSWORD in .env before real use, then run init-db again.")


def generate_keys() -> None:
    print("SECRET_KEY=" + secrets.token_hex(32))
    print("FILE_ENCRYPTION_KEY=" + Fernet.generate_key().decode())


def smoke_test() -> None:
    created_app = create_app()
    print("Flask app loaded successfully.")
    print("Registered routes:")
    for rule in sorted(created_app.url_map.iter_rules(), key=lambda r: r.rule):
        print(f"  {rule.rule:40s} -> {rule.endpoint}")


def main() -> int:
    parser = argparse.ArgumentParser(description="SecureVote management commands")
    parser.add_argument("command", nargs="?", default="run", choices=["init-db", "generate-keys", "smoke-test", "run"])
    args = parser.parse_args()

    if args.command == "init-db":
        init_db()
    elif args.command == "generate-keys":
        generate_keys()
    elif args.command == "smoke-test":
        smoke_test()
    else:
        app.run(host="127.0.0.1", port=5000, debug=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
