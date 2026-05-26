# AI App Compiler - React JS + FastAPI

This version uses a React JS frontend and a FastAPI backend.

## What is included

- React Login Page
- Register Page
- Logout Button
- Dashboard opens only after login
- FastAPI Auth APIs
- SQLite user storage
- Token stored in `localStorage`
- Premium page fixed: no infinity symbol in today chances
- Export Project button removed from the sidebar

## Backend setup

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python run.py
```

Backend URL:

```text
http://localhost:8000
```

FastAPI docs:

```text
http://localhost:8000/docs
```

## Frontend setup

```bash
cd frontend
npm install
copy .env.example .env
npm run dev
```

Frontend URL:

```text
http://localhost:5173
```

## Auth APIs

```text
POST /api/auth/register
POST /api/auth/login
GET  /api/auth/me
POST /api/auth/logout
```

## Login flow

1. Open `http://localhost:5173`.
2. Login page appears first.
3. Click `New user? Create account` to register.
4. After register/login, token is saved in `localStorage`.
5. Dashboard opens only after login.
6. Click Logout to remove token and return to login page.

## Admin page access

- The Admin menu is shown only when the logged-in user has role `admin`.
- Normal users will not see the Admin button in the sidebar.
- Backend admin APIs are also protected. Normal users get `403 Admin access required`.

### How admin role is created

For easy setup, the first registered account becomes admin automatically.
All later registered accounts become normal users.

You can also make specific emails admin by editing `backend/.env`:

```env
ADMIN_EMAILS=admin@example.com,yourmail@example.com
```

Then register/login using one of those emails.

Admin APIs:

```text
GET /api/admin/summary
GET /api/admin/users
```
