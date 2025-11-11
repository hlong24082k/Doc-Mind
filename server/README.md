# 🚀 LocalMind (MVP)  

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)  [![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)  [![Status](https://img.shields.io/badge/status-MVP%20Ready-orange.svg)]()  

## 📌 Overview  
**LocalMind** is an AI-powered local assistant that allows you to interact with your files and folders using natural language. It ensures **privacy-first** by running entirely on your machine — no data leaves your device.  

The system uses an **LLM + Planner + Executor** architecture:  
- 💬 You describe what you want in plain English.  
- 🧠 The Planner (AI) interprets your request and creates an execution plan.  
- ⚙️ The Executor safely performs validated file/folder operations.  
- 🎨 The UI provides a popup chat for interaction and feedback.  


## ✨ Features (MVP)  
- 🗂 **File & Folder Operations**: list, read, create, rename, delete.  
- 🧩 **Action Execution Layer**: safe primitives exposed to AI.  
- 🔒 **Validator / Sandbox Rules**: block unsafe/dangerous operations.  
- 💬 **Popup Chat UI**: interact with the agent in a small window.  
- ⏪ **Rollback**: undo the last executed action.  
- 📜 **Logging**: record executed commands & results.  

## ⚙️ Tech Stack (MVP)
- Language: Python 3.10+
- UI: CustomTkinter (lightweight popup chat interface)
- LLM Runtime: Local LLM (e.g., Ollama or GPT4All)
- Core Modules:
    - Executor (file/folder actions)
    - Validator (sandbox rules, safety checks)
    - Orchestrator (conversation + plan execution)
    - Logger (execution trace & rollback support)

## 📅 MVP Delivery (1 Week)
- [ ] Core Executor (file operations)
- [ ] Basic Planner & Validator
- [ ] Popup Chat UI
- [ ] Logging & Rollback
- [ ] Initial Release