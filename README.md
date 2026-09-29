# 🧠 Doc-Mind

> **Intelligent Document Management & Conversational AI Assistant**

[![Python Version](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.141%2B-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18-61DAFB.svg?logo=react&logoColor=black)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.5-3178C6.svg?logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![Vite](https://img.shields.io/badge/Vite-6.x-646CFF.svg?logo=vite&logoColor=white)](https://vitejs.dev/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1.svg?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Tailwind CSS](https://img.shields.io/badge/TailwindCSS-3.4-38B2AC.svg?logo=tailwind-css&logoColor=white)](https://tailwindcss.com/)
[![Google Gemini](https://img.shields.io/badge/Google%20Gemini-GenAI%20SDK-8E75C4.svg?logo=google&logoColor=white)](https://ai.google.dev/)

---

## 📖 Overview

**Doc-Mind** is a full-stack, AI-powered document workspace designed to streamline document storage, management, and interactive conversation. Leveraging FastAPI, PostgreSQL, React, and Google's Gemini models, Doc-Mind enables users to securely upload documents, search their catalog, and conduct real-time streaming conversations powered by modern generative AI.

---

## ✨ Features

- 📄 **Document Management**: Upload single or multiple documents, search documents in real-time, view metadata, download files, and securely delete documents.
- 💬 **Conversational AI with Gemini**: Real-time token streaming with Server-Sent Events (SSE) powered by Google's latest Gemini models via the `google-genai` SDK.
- 🔐 **Secure Authentication**: JWT-based token authorization with OAuth2 password bearer flow and password hashing via Argon2.
- ⚡ **Asynchronous Backend**: High-performance FastAPI application built with asynchronous database operations via SQLAlchemy 2.0 and `asyncpg`.
- 🎨 **Modern Sleek Interface**: Responsive, clean UI built with React 18, TypeScript, Tailwind CSS, Radix UI primitives, Lucide icons, and Zustand for state management.
- 🐳 **Containerized Database**: Instant PostgreSQL 16 database provisioning via Docker Compose.
- 🌱 **Automatic Setup & Seeding**: Automated database table creation and default superuser seeding on startup or via CLI command.

---

## 🛠️ Tech Stack

### Backend
| Technology | Description |
|---|---|
| **FastAPI** | Modern, high-performance web framework for building async APIs |
| **SQLAlchemy 2.0** | Next-generation Python ORM with async engine support |
| **asyncpg** | High-speed PostgreSQL database client library for Python/asyncio |
| **Google GenAI SDK** | Official Google GenAI SDK for Gemini streaming and reasoning |
| **sse-starlette** | Server-Sent Events (SSE) streaming for real-time AI responses |
| **Pydantic v2** | Data parsing, validation, and settings management |
| **Argon2 / Passlib** | Secure password hashing and token generation |
| **uv** | Ultra-fast Python package installer and virtual environment manager |

### Frontend
| Technology | Description |
|---|---|
| **React 18** | Declarative component-based UI library |
| **TypeScript** | Static typing for type safety and developer velocity |
| **Vite** | Fast modern frontend build tool and development server |
| **Tailwind CSS** | Utility-first CSS framework for clean styling |
| **Radix UI** | Accessible UI primitives and dialog components |
| **Zustand** | Lightweight and predictable state management |
| **React Router v6** | Client-side routing with protected route guards |
| **Lucide React** | Consistent and modern icon suite |

### Infrastructure & Database
- **PostgreSQL 16** (Alpine Linux container)
- **Docker & Docker Compose**

---

## 📁 Project Structure

```text
Doc-Mind/
├── docker-compose.yml       # Docker Compose setup for PostgreSQL
├── README.md                # Project documentation
├── client/                  # Frontend React + TypeScript application
│   ├── .env.example         # Client environment template
│   ├── index.html           # HTML entry point
│   ├── package.json         # NPM dependencies and scripts
│   ├── src/
│   │   ├── api/             # API clients, endpoints, and TypeScript types
│   │   ├── components/      # UI components and layout wrappers
│   │   ├── hooks/           # Custom React hooks
│   │   ├── pages/           # Application views (Login, Signup, Documents, Chat)
│   │   ├── router.tsx       # Route definitions & protected routes
│   │   └── store/           # Zustand global state stores (auth, etc.)
│   ├── tailwind.config.ts   # Tailwind CSS configuration
│   └── vite.config.ts       # Vite bundler configuration
└── server/                  # Backend FastAPI application
    ├── .env.example         # Server environment template
    ├── Makefile             # Quality, formatting, and test commands
    ├── pyproject.toml       # Python dependencies and metadata (uv / pip)
    ├── server.py            # Uvicorn entry point
    ├── app/
    │   ├── config.py        # Pydantic application settings
    │   ├── core/            # LLM providers (Gemini), prompts, and processors
    │   ├── cruds/           # Database CRUD operations
    │   ├── db/              # SQLAlchemy session, engine, and init logic
    │   ├── dependencies.py  # FastAPI dependency injection (auth, session)
    │   ├── main.py          # FastAPI application factory and lifespan
    │   ├── models/          # SQLAlchemy database models
    │   ├── routers/         # API routes (auth, document, conversation, heartbeat)
    │   ├── schemas/         # Pydantic request and response schemas
    │   └── security/        # JWT utilities and password verification
    └── scripts/
        ├── run_server.sh    # Server runner script
        └── seed.py          # Database seeding script
```

---

## 🚀 Quick Start Guide

### Prerequisites

Ensure you have the following installed on your machine:
- [Docker](https://www.docker.com/) & Docker Compose
- [Python 3.11+](https://www.python.org/)
- [`uv`](https://docs.astral.sh/uv/) (recommended) or `pip`
- [Node.js 18+](https://nodejs.org/) & `npm`
- A [Google Gemini API Key](https://aistudio.google.com/)

---

### Step 1: Clone the Repository

```bash
git clone https://github.com/hlong24082k/Doc-Mind.git
cd Doc-Mind
```

---

### Step 2: Start the Database

Run PostgreSQL 16 using Docker Compose:

```bash
docker compose up -d postgres
```

> **Note**: Verify the container is healthy by running `docker compose ps`.

---

### Step 3: Backend Setup (FastAPI)

1. **Navigate to the server directory**:
   ```bash
   cd server
   ```

2. **Configure environment variables**:
   ```bash
   cp .env.example .env
   ```
   Open `.env` and fill in your details, notably:
   - `GEMINI_API_KEY`: Your Google Gemini API key.
   - `JWT_SECRET_KEY`: A secure random secret string.
   - Database credentials if modified from defaults.

3. **Install dependencies**:
   Using `uv` (recommended):
   ```bash
   uv sync
   source .venv/bin/activate
   ```
   Or using standard `pip`:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -e .
   ```

4. **Initialize and seed the database**:
   ```bash
   python scripts/seed.py
   ```
   > By default, an administrator account is created:
   > - **Username**: `admin`
   > - **Password**: `Admin@123456`

5. **Start the API server**:
   ```bash
   python server.py
   ```
   The backend API will be running at `http://localhost:8000`.
   - **Interactive API Docs (Swagger UI)**: [http://localhost:8000/docs](http://localhost:8000/docs)
   - **Alternative API Docs (ReDoc)**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

### Step 4: Frontend Setup (React + Vite)

1. **Open a new terminal and navigate to the client directory**:
   ```bash
   cd client
   ```

2. **Configure environment variables**:
   ```bash
   cp .env.example .env
   ```
   Ensure `VITE_API_BASE_URL` points to your backend:
   ```env
   VITE_API_BASE_URL="http://localhost:8000/api"
   ```

3. **Install dependencies**:
   ```bash
   npm install
   ```

4. **Start the development server**:
   ```bash
   npm run dev
   ```
   Open your browser and navigate to:
   ```text
   http://localhost:5173
   ```

5. Log in with the default seeded account (`admin` / `Admin@123456`) or create a new user via the **Sign Up** page.

---

## 📡 API Overview

| Method | Endpoint | Description | Auth Required |
|---|---|---|:---:|
| `GET` | `/api/heartbeat/` | Health check endpoint | No |
| `POST` | `/api/auth/register` | Register a new user | No |
| `POST` | `/api/auth/login` | Log in and receive JWT access token | No |
| `GET` | `/api/document/` | Retrieve all documents for the authenticated user | Yes |
| `POST` | `/api/document/uploadfile` | Upload one or multiple document files | Yes |
| `GET` | `/api/document/{filename}` | Download a document file by filename | No |
| `DELETE` | `/api/document/{file_id}` | Delete a document by file ID | Yes |
| `POST` | `/api/conversation/stream` | Stream AI conversational response (SSE) | No |

---

## 🧪 Development & Code Quality

### Backend Quality Commands (`server/`)

The backend includes a `Makefile` for routine code quality and maintenance tasks:

```bash
cd server

# Run formatting with black and isort
make format

# Check code quality standards (black, isort, flake8)
make quality

# Run unit and integration tests
make test

# Clean temporary cache and build artifacts
make clean
```

### Frontend Scripts (`client/`)

```bash
cd client

# Run local development server
npm run dev

# Run ESLint validation
npm run lint

# Build production bundle
npm run build

# Preview production build locally
npm run preview
```

---

## 📄 License

This project is licensed under the [MIT License](LICENSE) (or applicable workspace license).
