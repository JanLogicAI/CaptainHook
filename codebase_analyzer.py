"""Codebase analyzer that discovers repos via GitHub and analyzes them with Claude."""
import json
import os
import re
import shutil
import subprocess
import time
from typing import Dict, List, Optional

from config import Config

GH_CLI = "/opt/homebrew/bin/gh"
# Resolve the Claude CLI path: honor explicit config first, then PATH lookup.
CLAUDE_CLI = Config.CLAUDE_CLI_PATH or shutil.which("claude") or ""
REPO_CACHE_DIR = "/tmp/jira-agent-repos"
CACHE_FILE = os.path.join(REPO_CACHE_DIR, "gh_cache.json")
CACHE_TTL = 3600  # 1 hour
LOCAL_DEV_DIR = os.path.expanduser("~/Developer")
MAX_CONTEXT_CHARS = 15000

PREFIX_TO_REPO = {
    "rvz": "rvz",
    "vapde": "verisure",
    "vapnl": "verisure",
    "vep": "vep",
    "crm": "crm",
    "3dp": "3-d-print",
    "log": "virtual-developer",
}

DUTCH_TO_ENGLISH = {
    "aanmaken": "create",
    "verwijderen": "delete remove",
    "bijwerken": "update",
    "toevoegen": "add",
    "wijzigen": "change modify update",
    "fout": "error bug",
    "probleem": "problem issue",
    "pagina": "page",
    "knop": "button",
    "gebruiker": "user",
    "gebruikers": "users",
    "inloggen": "login",
    "uitloggen": "logout",
    "wachtwoord": "password",
    "bestelling": "order",
    "factuur": "invoice",
    "klant": "customer client",
    "product": "product",
    "voorraad": "stock",
    "verzending": "shipping",
    "betaling": "payment",
    "rapport": "report",
    "dashboard": "dashboard",
    "instelling": "setting config",
    "configuratie": "configuration",
    "database": "database",
    "tabel": "table",
    "veld": "field",
    "formulier": "form",
    "overzicht": "overview",
    "zoeken": "search find",
    "filter": "filter",
    "sorteren": "sort",
    "exporteren": "export",
    "importeren": "import",
    "koppeling": "integration",
    "api": "api endpoint",
    "melding": "notification",
    "e-mail": "email",
    "sjabloon": "template",
    "rechten": "permissions",
    "rol": "role",
    "monteur": "technician engineer",
    "afspraak": "appointment schedule",
    "planning": "planning schedule",
    "robot": "robot bot automation",
    "driehoek": "triangle",
    "audio": "audio recording",
    "opname": "recording",
    "installatie": "installation install",
    "werkt": "works working",
    "niet": "not",
    "goed": "good well",
    "nieuwe": "new",
    "oude": "old",
    "test": "test",
    "controleren": "check verify",
    "toewijzen": "assign",
    "oplossen": "fix resolve solve",
}

STOP_WORDS = {
    "de", "het", "een", "van", "in", "op", "te", "voor", "met", "aan",
    "is", "dat", "die", "er", "als", "zijn", "wordt", "naar", "bij",
    "ook", "nog", "maar", "dan", "wel", "niet", "door", "om", "uit",
    "kan", "moet", "zou", "zal", "heeft", "hebben", "was", "waren",
    "the", "a", "an", "of", "in", "on", "to", "for", "with", "at",
    "is", "that", "it", "as", "are", "be", "from", "or", "and", "but",
    "can", "should", "would", "will", "has", "have", "was", "were",
    "this", "these", "those", "we", "they", "i", "you", "he", "she",
    "get", "set", "make", "see", "like", "use", "new", "way",
}


class CodebaseAnalyzer:
    """Discovers repositories via GitHub and analyzes codebases with Claude."""

    def __init__(self):
        os.makedirs(REPO_CACHE_DIR, exist_ok=True)

    def extract_keywords(self, ticket: Dict) -> List[str]:
        """Extract meaningful keywords from a ticket's summary and description."""
        summary = ticket.get("summary", "")
        description = ticket.get("description", "")
        text = f"{summary} {description}".lower()
        text = re.sub(r"https?://\S+", "", text)
        text = re.sub(r"[^a-z0-9\s\-]", " ", text)
        words = text.split()

        keywords = []
        seen = set()
        for word in words:
            word = word.strip(".-_")
            if word in STOP_WORDS or len(word) < 3 or word.isdigit() or word in seen:
                continue
            seen.add(word)
            keywords.append(word)
            # Add English translation
            if word in DUTCH_TO_ENGLISH:
                for eng in DUTCH_TO_ENGLISH[word].split():
                    if eng not in seen:
                        seen.add(eng)
                        keywords.append(eng)

        return keywords[:20]

    def _fetch_github_repos(self) -> List[Dict]:
        """Fetch repos from GitHub orgs/users, with caching."""
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE, "r") as f:
                    cached = json.load(f)
                if time.time() - cached.get("timestamp", 0) < CACHE_TTL:
                    print("    📦 Using cached GitHub repo list")
                    return cached["repos"]
            except (json.JSONDecodeError, KeyError):
                pass

        print("    🔄 Fetching GitHub repo list...")
        all_repos = []

        for owner in ["Code-Art-BV", "JanLogicAI"]:
            try:
                result = subprocess.run(
                    [GH_CLI, "repo", "list", owner, "--limit", "100",
                     "--json", "name,url,primaryLanguage,description"],
                    capture_output=True, text=True, timeout=30,
                )
                if result.returncode == 0:
                    repos = json.loads(result.stdout)
                    for repo in repos:
                        repo["owner"] = owner
                    all_repos.extend(repos)
                    print(f"    📂 Found {len(repos)} repos from {owner}")
                else:
                    print(f"    ⚠️ gh repo list {owner} failed: {result.stderr.strip()}")
            except (subprocess.TimeoutExpired, FileNotFoundError) as e:
                print(f"    ⚠️ Could not fetch repos from {owner}: {e}")

        cache_data = {"timestamp": time.time(), "repos": all_repos}
        try:
            with open(CACHE_FILE, "w") as f:
                json.dump(cache_data, f)
        except OSError:
            pass

        return all_repos

    def discover_repo(self, ticket_key: str, keywords: List[str]) -> Optional[Dict]:
        """Discover the best matching repo for a ticket.
        Returns dict with 'url' and 'name' keys, or None.
        """
        repos = self._fetch_github_repos()
        if not repos:
            print("    ⚠️ No GitHub repos available")
            return None

        prefix = ticket_key.split("-")[0].lower() if "-" in ticket_key else ""
        mapped_name = PREFIX_TO_REPO.get(prefix)

        # Try exact prefix mapping first
        if mapped_name:
            for repo in repos:
                if repo.get("name", "").lower() == mapped_name.lower():
                    print(f"    🎯 Prefix '{prefix}' mapped to repo: {repo['name']}")
                    return {"url": repo["url"], "name": repo["name"]}

            for repo in repos:
                if mapped_name.lower() in repo.get("name", "").lower():
                    print(f"    🎯 Prefix '{prefix}' partial match: {repo['name']}")
                    return {"url": repo["url"], "name": repo["name"]}

        # Keyword matching fallback with improved scoring
        GENERIC_TERMS = {"agent", "api", "web", "app", "service", "tool", "data", "test", "dev", "lib", "core", "base"}
        ticket_context = f"{keywords}".lower()
        
        best_score = 0
        best_repo = None
        for repo in repos:
            score = 0
            repo_name = repo.get("name", "").lower()
            repo_desc = (repo.get("description") or "").lower()
            repo_lang = (repo.get("primaryLanguage") or {}).get("name", "").lower() if isinstance(repo.get("primaryLanguage"), dict) else ""
            
            # Split repo name into parts for better matching
            repo_parts = repo_name.replace("_", "-").split("-")
            part_matches = 0
            
            for kw in keywords:
                kw_lower = kw.lower()
                # Match against individual repo name parts
                for part in repo_parts:
                    if kw_lower == part:
                        score += 5
                        part_matches += 1
                    elif len(kw_lower) > 3 and (kw_lower in part or part in kw_lower):
                        score += 2
                        part_matches += 1
                # Description matching
                if repo_desc and kw_lower in repo_desc:
                    score += 1
                # Bonus for longer keywords
                if len(kw_lower) > 5:
                    score += 1
                # Penalize generic terms
                if kw_lower in GENERIC_TERMS:
                    score -= 2
            
            # Bonus for multiple part matches
            if part_matches >= 2:
                score += part_matches * 2
            
            if score > best_score:
                best_score = score
                best_repo = repo

        if best_repo and best_score >= 2:
            print(f"    🔍 Keyword match (score {best_score}): {best_repo['name']}")
            return {"url": best_repo["url"], "name": best_repo["name"]}

        print(f"    ⚠️ No matching repo found for {ticket_key}")
        return None

    def ensure_repo_local(self, repo_url: str, repo_name: str) -> Optional[str]:
        """Ensure the repo is available locally. Returns local path or None."""
        # Check ~/Developer first
        local_dev_path = os.path.join(LOCAL_DEV_DIR, repo_name)
        if os.path.isdir(local_dev_path):
            print(f"    📁 Found local repo: {local_dev_path}")
            return local_dev_path

        # Check cache dir
        clone_path = os.path.join(REPO_CACHE_DIR, repo_name)
        if os.path.isdir(clone_path):
            print(f"    📁 Found cached clone: {clone_path}")
            return clone_path

        # Clone shallow
        print(f"    📥 Cloning {repo_name} (shallow)...")
        try:
            result = subprocess.run(
                ["git", "clone", "--depth", "1", repo_url, clone_path],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode == 0:
                print(f"    ✅ Cloned to: {clone_path}")
                return clone_path
            else:
                print(f"    ❌ Clone failed: {result.stderr.strip()}")
                return None
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            print(f"    ❌ Clone error: {e}")
            return None

    def pre_search(self, repo_path: str, keywords: List[str]) -> str:
        """Search the repo for relevant files using ripgrep or grep. Returns context string."""
        if not keywords:
            return ""

        all_matches = []
        seen_files = set()
        pattern = "|".join(re.escape(kw) for kw in keywords[:10])

        # Try ripgrep first
        try:
            result = subprocess.run(
                ["rg", "-l", "-i",
                 "--type-add", "csharp:*.cs",
                 "--type-add", "web:*.{cshtml,razor,html}",
                 "-t", "csharp", "-t", "py", "-t", "dart", "-t", "js", "-t", "ts",
                 "-t", "web",
                 pattern, repo_path],
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode == 0 and result.stdout.strip():
                files = result.stdout.strip().splitlines()[:20]
                for filepath in files:
                    if filepath in seen_files:
                        continue
                    seen_files.add(filepath)
                    try:
                        snippet_result = subprocess.run(
                            ["rg", "-C", "3", "-i", "--max-count", "3",
                             "--max-columns", "150", pattern, filepath],
                            capture_output=True, text=True, timeout=10,
                        )
                        if snippet_result.returncode == 0 and snippet_result.stdout.strip():
                            rel_path = os.path.relpath(filepath, repo_path)
                            snippet = snippet_result.stdout.strip()
                            all_matches.append(f"### {rel_path}\n```\n{snippet}\n```\n")
                    except (subprocess.TimeoutExpired, Exception):
                        continue
                    if len("\n".join(all_matches)) >= MAX_CONTEXT_CHARS:
                        break
        except FileNotFoundError:
            # Fallback to grep
            try:
                result = subprocess.run(
                    ["grep", "-r", "-l", "-i", "-E", pattern, repo_path],
                    capture_output=True, text=True, timeout=15,
                )
                if result.returncode == 0 and result.stdout.strip():
                    files = result.stdout.strip().splitlines()[:15]
                    for filepath in files:
                        if filepath in seen_files:
                            continue
                        seen_files.add(filepath)
                        rel_path = os.path.relpath(filepath, repo_path)
                        all_matches.append(f"### {rel_path}\n")
                        if len("\n".join(all_matches)) >= MAX_CONTEXT_CHARS:
                            break
            except Exception:
                pass
        except subprocess.TimeoutExpired:
            print("    ⏱️ Pre-search timed out")

        if not all_matches:
            return ""

        context = "\n".join(all_matches)
        return context[:MAX_CONTEXT_CHARS]

    def analyze_ticket(self, ticket: Dict) -> Optional[str]:
        """Full analysis pipeline: discover repo, search code, generate plan with Claude.
        Returns the Claude-generated plan string, or None if analysis fails.
        """
        ticket_key = ticket.get("key", "UNKNOWN")
        summary = ticket.get("summary", "")
        description = ticket.get("description", "")

        print(f"    🧠 Starting codebase analysis for {ticket_key}")

        keywords = self.extract_keywords(ticket)
        print(f"    🔑 Keywords: {', '.join(keywords[:10])}")

        repo_info = self.discover_repo(ticket_key, keywords)
        if not repo_info:
            return None

        repo_path = self.ensure_repo_local(repo_info["url"], repo_info["name"])
        if not repo_path:
            return None

        print(f"    🔍 Searching codebase for relevant files...")
        code_context = self.pre_search(repo_path, keywords)

        if code_context:
            print(f"    📂 Found relevant code, using targeted analysis")
            prompt = f"""You are a senior software engineer analyzing a Jira ticket to create an implementation plan.

## Ticket: {ticket_key}
**Summary:** {summary}
**Description:** {description if description else 'No description provided'}

## Repository: {repo_info['name']}

## Relevant Code Found

{code_context}

Based on the ticket and the actual codebase, create a detailed, actionable implementation plan. Include:
1. Which specific files need to be modified or created
2. What changes are needed in each file
3. The order of implementation steps
4. Any potential risks or considerations
5. Estimated complexity (Low/Medium/High)

Be specific - include function names, code examples, and concrete steps. Do NOT give generic advice."""
            timeout = 120
        else:
            print(f"    ⚠️ No code context found, using broader analysis")
            prompt = f"""You are a senior software engineer analyzing a Jira ticket to create an implementation plan.

## Ticket: {ticket_key}
**Summary:** {summary}
**Description:** {description if description else 'No description provided'}

## Repository: {repo_info['name']}
The repository is at: {repo_path}

Search the codebase for relevant code and create a detailed plan with:
1. Files to modify
2. Specific changes needed
3. Implementation steps
4. Risks

Be specific. Do NOT give generic advice."""
            timeout = 180

        if not CLAUDE_CLI:
            print("    ⚠️ CLAUDE_CLI_PATH not set and `claude` not on PATH — skipping Claude analysis")
            return None

        print(f"    🤖 Asking Claude to analyze...")
        try:
            result = subprocess.run(
                [CLAUDE_CLI, "--print", prompt],
                capture_output=True, text=True, timeout=timeout,
                cwd=repo_path,
            )
            if result.returncode == 0 and result.stdout.strip():
                print(f"    ✅ Claude analysis complete")
                return result.stdout.strip()
            else:
                print(f"    ❌ Claude analysis failed")
                return None
        except subprocess.TimeoutExpired:
            print(f"    ❌ Claude analysis timed out ({timeout}s)")
            return None
        except FileNotFoundError:
            print(f"    ❌ Claude CLI not found at {CLAUDE_CLI}")
            return None
        except Exception as e:
            print(f"    ❌ Error: {e}")
            return None
