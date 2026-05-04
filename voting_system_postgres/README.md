# SecureVote PostgreSQL Edition

A Flask voting website designed for PostgreSQL and pgAdmin 4 with improved UI/UX, transitions, dual OTP verification, encrypted proof uploads, admin controls, CSV exports, audit logs, and an OpenRouter-powered website assistant.

## What changed in this upgraded build

- Fixed admin database seeding/login problem.
- Added required **email OTP + mobile OTP** verification for voters and candidates.
- Added resend OTP flows.
- Added an AI website assistant widget that uses OpenRouter when `OPENROUTER_API_KEY` is configured.
- Added local assistant fallback answers when OpenRouter is not configured.
- Added stronger admin dashboard search/filter tools.
- Added voter/candidate verification badges.
- Added vote receipt hashes.
- Added safer election reset confirmation.
- Added more polished UI, glass cards, transitions, reveal animations, floating assistant, password visibility toggle, and responsive design.
- Kept PostgreSQL/pgAdmin 4 as the database system.

## Requirements

- Python 3.11+
- PostgreSQL installed locally
- pgAdmin 4

## Create database in pgAdmin 4

1. Open pgAdmin 4.
2. Connect to your PostgreSQL server.
3. Create a database named:

```text
secure_voting
```

## Setup commands on Windows PowerShell

```powershell
cd "C:\Users\DELL\OneDrive\Desktop\secure_voting_postgres"
copy .env.example .env
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Generate strong keys:

```powershell
python manage.py generate-keys
```

Copy the generated `SECRET_KEY` and `FILE_ENCRYPTION_KEY` values into `.env`.

Edit `.env` and set your PostgreSQL password:

```env
DATABASE_URL=postgresql://postgres:your_pgadmin_password@localhost:5432/secure_voting
```

Initialize or upgrade the database:

```powershell
python manage.py init-db
```

Run the website:

```powershell
python manage.py run
```

Open:

```text
http://127.0.0.1:5000
```

## Default admin login

After running `python manage.py init-db`:

```text
Account type: Admin
ID: ADMIN001
Password: admin123
```

For real use, change this in `.env`:

```env
ADMIN_PASSWORD=YourStrongAdminPassword123
```

Then run this again:

```powershell
python manage.py init-db
```

## Email and mobile OTP behavior

Development mode:

- If SMTP settings are empty, email OTP appears as a message on screen.
- If SMS settings are empty, mobile OTP appears as a message on screen.
- This is useful for localhost testing.

Production mode:

- Configure SMTP values before real email OTP delivery.
- Configure `SMS_API_URL` and `SMS_API_TOKEN` before real mobile OTP delivery.
- Set `APP_ENV=production`.
- Use HTTPS and set `SESSION_COOKIE_SECURE=true`.

## OpenRouter assistant setup

Create or get your OpenRouter API key, then add it to `.env`:

```env
OPENROUTER_API_KEY=your_openrouter_api_key_here
OPENROUTER_MODEL=openai/gpt-4o-mini
```

The API key stays on the Flask server. It is not sent to the browser.

If no OpenRouter key is configured, the assistant still works in local FAQ mode for common website questions.

## Security notes

- Passwords are hashed.
- OTPs are hashed in PostgreSQL.
- ID proof uploads are encrypted at rest using `FILE_ENCRYPTION_KEY`.
- CSRF protection is enabled for forms and assistant JSON calls.
- Repeated failed logins trigger a temporary lockout.
- Voting uses PostgreSQL transactions and a unique vote constraint.
- Audit logs track login, approval, export, reset, proof download, OTP, and voting actions.

## Important warning about FILE_ENCRYPTION_KEY

Do not change `FILE_ENCRYPTION_KEY` after uploading proof files. Files encrypted with an old key cannot be decrypted with a new key.

## Useful commands

Smoke-test route loading:

```powershell
python manage.py smoke-test
```

Generate new keys:

```powershell
python manage.py generate-keys
```

Run app:

```powershell
python manage.py run
```
