# React Performance Code Review Agent 🚀

AI-powered multi-agent system for automated React performance analysis in Pull Requests using Google's Agent Development Kit (ADK) and Gemini models.

[![Python 3.12+](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Node 20+](https://img.shields.io/badge/Node-20+-green.svg)](https://nodejs.org/)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue.svg)](https://www.docker.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)

---

## 🎯 Features

- **🤖 Multi-Agent Analysis**: Four-stage AI pipeline (Parser → Analyzer → Reasoner → Reporter)
- **🧠 Smart Memory System**: Tracks patterns across files, detects recurring issues, learns project conventions
- **📝 Inline PR Comments**: Posts detailed review comments on specific lines
- **🎯 Smart Detection**: Identifies critical React performance issues
- **⚙️ Configurable**: Severity thresholds and auto-approval settings
- **🐳 Docker Ready**: One-command deployment anywhere
- **🔗 PR URL Support**: Analyze PRs by URL, no manual configuration needed
- **🚀 GitHub Action**: Automated reviews on every PR

---

## 🔍 What It Detects

### 🚨 Critical Issues
- Inline functions/objects breaking `React.memo`
- Stale closures in hooks
- Missing dependency arrays causing infinite loops

### ⚠️ High Priority
- Unstable hook dependencies
- Unnecessary re-renders
- Derived state anti-patterns

### 💡 Medium Priority
- Inline JSX expressions
- Props not used in render
- State management issues

### ℹ️ Low Priority
- Minor optimizations
- Best practice suggestions

---

## 🏗️ Architecture

**5-Agent Multi-Agent System** orchestrated via Google ADK's `SequentialAgent`:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           PR Analysis Flow                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  File N → [Memory Agent] → "Pattern summary: 10 inline functions..."        │
│            ↓                                                                 │
│           [Sequential Agent Pipeline]                                        │
│            ├→ Parser Agent    (Babel AST parsing)                           │
│            ├→ Analyzer Agent  (Issue detection - 8 tools)                   │
│            ├→ Reasoner Agent  (Prioritization + context)                    │
│            └→ Reporter Agent  (GitHub/JSON output)                          │
│            ↓                                                                 │
│           Store Summary → DatabaseSessionService                             │
│                                                                              │
│  PR Done → Clear Database                                                    │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                         5-AGENT MULTI-AGENT SYSTEM                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  🧠 Memory Agent         →  Cross-file pattern detection                    │
│                              Provides ~50 word summary to pipeline           │
│                                                                              │
│  📝 Parser Agent         →  parse_code() - Babel AST extraction             │
│  🔍 Analyzer Agent       →  8 specialized tools for issue detection         │
│  💡 Reasoner Agent       →  Prioritizes issues, adds suggestions            │
│  📊 Reporter Agent       →  Formats output for GitHub PR reviews            │
│                                                                              │
│  [SequentialAgent orchestration: Parser → Analyzer → Reasoner → Reporter]   │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Configuration:** Set `USE_MULTI_AGENT=false` for single-agent mode (faster, less specialized)

**Tech Stack:**
- 🧠 Google Gemini 2.5 Flash Lite
- 🔧 Google ADK (Agent Development Kit) with SequentialAgent
- 💾 DatabaseSessionService (Persistent SQLite)
- 🤖 5 Specialized Agents (Memory, Parser, Analyzer, Reasoner, Reporter)
- 📝 Babel Parser (AST analysis)
- 🐍 Python 3.12+
- 📦 Node.js 20+
- 🐳 Docker & Docker Compose

---

## 🚀 Quick Start

### Option 1: Docker (Recommended)

```bash
# 1. Clone the repository
git clone <repository-url>
cd code-review-agent

# 2. Copy and configure environment
cp .env.example .env
# Edit .env with your API keys

# 3. Build and run
docker-compose build
docker-compose run code-review-agent python3 agents/main.py examples/UserList.tsx

# 4. Analyze a PR
docker-compose run code-review-agent ./review-pr.sh <PR_URL> --analyze-only
```

### Option 2: Local Installation

```bash
# 1. Install dependencies
cd parser && npm install && npm run build && cd ..
cd agents && pip install -r requirements.txt && cd ..

# 2. Configure environment
cp .env.example agents/.env
# Edit agents/.env with your API keys

# 3. Run analysis
python3 agents/main.py examples/UserList.tsx

# 4. Review a PR
./review-pr.sh <PR_URL> --analyze-only
```

---

## 📋 Prerequisites

### Required API Keys

1. **Google AI API Key**
   - Get from: https://makersuite.google.com/app/apikey
   - Set as: `GOOGLE_API_KEY` in `.env`

2. **GitHub Personal Access Token** (for PR reviews)
   - Get from: https://github.com/settings/tokens
   - Required scopes: `repo` (full control)
   - Set as: `GITHUB_TOKEN` in `.env`

### System Requirements

- **Docker**: 20.10+ (recommended), or
- **Python**: 3.12+
- **Node.js**: 20+
- **Memory**: 2GB minimum
- **Storage**: 500MB

---

## 💻 Usage

### Analyze a Single File

```bash
# Docker
docker-compose run code-review-agent python3 agents/main.py examples/UserList.tsx

# Local
python3 agents/main.py examples/UserList.tsx [markdown|json|github]
```

### Review a Pull Request

```bash
# Dry run (no comments posted)
./review-pr.sh https://github.com/owner/repo/pull/123 --analyze-only

# Post review with default settings
./review-pr.sh https://github.com/owner/repo/pull/123

# High severity only
./review-pr.sh https://github.com/owner/repo/pull/123 --severity high

# Auto-approve if no critical issues
./review-pr.sh https://github.com/owner/repo/pull/123 --auto-approve
```

### GitHub Action

The action runs automatically on PRs that touch React/TypeScript files.

**Setup:**
1. Add `GOOGLE_API_KEY` to repository secrets
2. Workflow file is already configured at `.github/workflows/react-perf-review.yml`
3. Push changes and open a PR

---

## ⚙️ Configuration

### Environment Variables

```bash
# Required
GOOGLE_API_KEY=your-google-api-key-here
GITHUB_TOKEN=your-github-token-here

# Optional
GITHUB_REPOSITORY=owner/repo          # Not needed if using PR URLs
DEBUG_ANALYSIS=0                      # Set to 1 for debug output
SEVERITY_THRESHOLD=medium             # low|medium|high|critical
AUTO_APPROVE=false                    # Auto-approve clean PRs
```

### Severity Levels

| Level | Reports | Blocks Merge |
|-------|---------|-------------|
| `critical` | Only critical issues | Yes |
| `high` | Critical + High | On critical only |
| `medium` | Critical + High + Medium | On critical only |
| `low` | All issues | On critical only |

---

## 📊 Output Formats

### Markdown Report (Default)

```markdown
# React Performance Analysis Report

## Summary
- 🚨 2 critical issues
- ⚠️ 1 high-priority issues
- 💡 3 medium-priority issues

## 🚨 Critical Issues

### `src/Button.tsx:42` - Button
**Inline function breaks memoization**

**Problem:** Arrow function recreates on every render...
**Suggestion:** Use useCallback...
```

### JSON Output

```json
{
  "issues": [
    {
      "file": "src/Button.tsx",
      "line": 42,
      "severity": "critical",
      "title": "Inline function breaks memoization",
      "problem": "...",
      "suggestion": "..."
    }
  ],
  "summary": {
    "critical_count": 2,
    "high_count": 1,
    "files_analyzed": 3
  }
}
```

### GitHub PR Comments

Posted as inline review comments on specific lines with:
- 🚨 Severity indicator
- **Problem** description
- **Suggestion** with code examples
- **Runtime Impact** explanation

---

## 🐳 Docker Details

### Build Image

```bash
docker-compose build
```

### Run Analysis

```bash
# Analyze file
docker-compose run code-review-agent python3 agents/main.py examples/UserList.tsx

# Review PR
docker-compose run code-review-agent ./review-pr.sh <PR_URL> --analyze-only

# Interactive shell
docker-compose run code-review-agent /bin/bash
```

### Deploy on EC2/Server

```bash
# 1. Copy files to server
scp -r . user@server:/app/code-review-agent

# 2. SSH into server
ssh user@server

# 3. Run with docker-compose
cd /app/code-review-agent
docker-compose build
docker-compose run code-review-agent <command>
```

---

## 📝 Examples

### Example 1: Analyze Local File

```bash
docker-compose run code-review-agent \
  python3 agents/main.py examples/UserList.tsx
```

**Output:** Identifies inline function creating new reference on each render.

### Example 2: Review PR from URL

```bash
docker-compose run code-review-agent \
  ./review-pr.sh https://github.com/facebook/react/pull/28977 --analyze-only
```

**Output:** Analyzes all React files in the PR and shows results.

### Example 3: Post Review Comments

```bash
./review-pr.sh https://github.com/owner/repo/pull/123 --severity high
```

**Result:** Posts inline comments on high and critical issues.

---

## 🔧 Development

### Project Structure

```
code-review-agent/
├── parser/                 # TypeScript AST parser (Babel)
│   ├── src/
│   │   ├── analyzer.ts     # AST analysis logic
│   │   ├── cli.ts          # CLI interface
│   │   └── types.ts        # Type definitions
│   └── package.json
│
├── agents/                 # Python agents
│   ├── agents.py           # ADK agent definitions
│   ├── main.py             # Orchestrator
│   ├── tools.py            # Analysis tools
│   ├── github_integration.py  # PR integration
│   └── requirements.txt
│
├── .github/workflows/      # GitHub Actions
│   └── react-perf-review.yml
│
├── examples/               # Sample React files
├── Dockerfile             # Docker image
├── docker-compose.yml     # Docker Compose config
└── README.md
```

---

## 📚 Documentation

- [SETUP.md](./SETUP.md) - Detailed installation guide
- [PROJECT_SUMMARY.md](./PROJECT_SUMMARY.md) - Architecture overview

---

## 🐛 Troubleshooting

### Common Issues

**1. "GOOGLE_API_KEY not set"**
```bash
# Make sure .env file exists and is loaded
cp .env.example .env
# Edit .env with your key
```

**2. Parser errors**
```bash
# Rebuild parser
cd parser && npm run build
```

**3. Docker build fails**
```bash
# Clean build
docker-compose build --no-cache
```

**4. Analysis returns empty results**
- File may be too large (>1000 lines)
- Check DEBUG_ANALYSIS=1 for details
- Try analyzing smaller files first


---

## 🙏 Credits

Built with:
- [Google Gemini](https://ai.google.dev/) - AI models
- [Google ADK](https://developers.google.com/adk) - Agent framework
- [Babel](https://babeljs.io/) - JavaScript parser
- [GitHub API](https://docs.github.com/rest) - PR integration

---


## ⭐ Star History

If you find this useful, please star the repo! It helps others discover the project.

---

**Made with ❤️ for the React community**

*Catch performance issues before they reach production* 🚀
