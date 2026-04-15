"""Codebase-aware analysis for Jira tickets using pre-search + Claude Code."""
import subprocess
import os
import re
from typing import Dict, Optional, List


import json

# Default paths - override via repo_mappings.json in the project root
_REPO_MAPPINGS_FILE = os.path.join(os.path.dirname(__file__), "repo_mappings.json")

def _load_repo_mappings() -> Dict[str, str]:
    """Load repo mappings from config file, falling back to environment variables."""
    mappings: Dict[str, str] = {}

    # Try loading from JSON config file first
    if os.path.exists(_REPO_MAPPINGS_FILE):
        try:
            with open(_REPO_MAPPINGS_FILE, "r") as f:
                mappings = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass

    # Fall back to environment variable: REPO_MAPPINGS={"PREFIX":"/path/to/repo",...}
    env_mappings = os.getenv("REPO_MAPPINGS", "")
    if env_mappings and not mappings:
        try:
            mappings = json.loads(env_mappings)
        except json.JSONDecodeError:
            pass

    return mappings


REPO_MAPPINGS: Dict[str, str] = _load_repo_mappings()

# Claude CLI path - configurable via env var
CLAUDE_CLI = os.getenv("CLAUDE_CLI_PATH", os.path.expanduser("~/.local/bin/claude"))
MAX_CONTEXT_CHARS = 15000

STOP_WORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "need", "must", "ought",
    "i", "me", "my", "we", "our", "you", "your", "he", "she", "it",
    "they", "them", "his", "her", "its", "our", "their", "this", "that",
    "these", "those", "am", "if", "or", "and", "but", "not", "no", "nor",
    "so", "yet", "both", "each", "few", "more", "most", "other", "some",
    "such", "than", "too", "very", "just", "also", "then", "when", "where",
    "how", "what", "which", "who", "whom", "why", "all", "any", "every",
    "of", "in", "to", "for", "with", "on", "at", "from", "by", "as",
    "into", "about", "between", "through", "during", "before", "after",
    "above", "below", "up", "down", "out", "off", "over", "under", "again",
    "further", "once", "here", "there", "because", "until", "while",
    "get", "set", "make", "see", "like", "use", "new", "way",
}


class CodebaseAnalyzer:
    """Analyzes codebases by pre-searching for relevant code then invoking Claude CLI."""

    def get_repo_path(self, ticket_key: str) -> Optional[str]:
        """Get the repository path for a ticket based on its prefix."""
        prefix = ticket_key.split("-")[0] if "-" in ticket_key else None
        if not prefix:
            return None
        path = REPO_MAPPINGS.get(prefix)
        if path and os.path.exists(path):
            return path
        return None

    def extract_keywords(self, text: str) -> List[str]:
        """Extract meaningful keywords from text by removing stop words and noise.
        Also adds English translations for common Dutch terms.
        """
        # Remove URLs and special chars
        text = re.sub(r"https?://\S+", "", text)
        text = re.sub(r"[^a-zA-Z0-9_\-.]", " ", text)
        tokens = text.lower().split()
        
        # Dutch -> English translations for common dev terms
        dutch_to_english = {
            "gebruikers": "users",
            "gebruiker": "user",
            "toevoegen": "add",
            "verwijderen": "remove delete",
            "wijzigen": "update modify",
            "bekijken": "view",
            "zoeken": "search find",
            "installeratie": "installation install",
            "monteur": "technician engineer",
            "klant": "customer client",
            "bestelling": "order",
            "afspraak": "appointment schedule",
            "planning": "planning schedule",
            "rapport": "report",
            "fout": "error bug",
            "werken": "work",
            "pagina": "page",
            "knop": "button",
            "veld": "field",
            "formulier": "form",
            "lijst": "list",
            "dashboard": "dashboard",
            "instelling": "settings config",
            "notificatie": "notification",
            "upload": "upload",
            "download": "download",
            "export": "export",
            "import": "import",
            "robot": "robot bot automation",
            "api": "api endpoint",
            "driehoek": "triangle",
            "audio": "audio recording",
            "opname": "recording",
        }
        
        keywords = []
        seen = set()
        for token in tokens:
            token = token.strip(".-_")
            if (
                token
                and token not in STOP_WORDS
                and token not in seen
                and len(token) > 2
                and not token.isdigit()
            ):
                keywords.append(token)
                seen.add(token)
                
                # Add English translation if available
                if token in dutch_to_english:
                    for eng in dutch_to_english[token].split():
                        if eng not in seen:
                            keywords.append(eng)
                            seen.add(eng)
        
        return keywords

    def pre_search(self, repo_path: str, keywords: List[str]) -> str:
        """Search the repo for keyword matches using ripgrep (fallback to grep).
        
        Returns a context string with matching file paths and code snippets.
        """
        if not keywords:
            return ""
        
        all_matches = []
        seen_files = set()
        
        # Build search pattern from keywords
        pattern = "|".join(re.escape(kw) for kw in keywords[:10])
        
        # Try ripgrep first
        try:
            result = subprocess.run(
                [
                    "rg", "-l", "-i",
                    "--type-add", "csharp:*.cs",
                    "--type-add", "web:*.{cshtml,razor,html}",
                    "--type-add", "config:*.{json,yaml,yml,xml,config}",
                    "-t", "csharp", "-t", "py", "-t", "dart", "-t", "js", "-t", "ts",
                    "-t", "web", "-t", "config",
                    pattern,
                    repo_path,
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )
            
            if result.returncode == 0 and result.stdout.strip():
                files = result.stdout.strip().splitlines()[:20]
                
                # Get snippets from each file
                for filepath in files:
                    if filepath in seen_files:
                        continue
                    seen_files.add(filepath)
                    
                    try:
                        # Get matching lines with context
                        snippet_result = subprocess.run(
                            [
                                "rg", "-C", "3", "-i", "--max-count", "3",
                                "--max-columns", "150",
                                pattern,
                                filepath,
                            ],
                            capture_output=True,
                            text=True,
                            timeout=10,
                        )
                        if snippet_result.returncode == 0 and snippet_result.stdout.strip():
                            rel_path = os.path.relpath(filepath, repo_path)
                            snippet = snippet_result.stdout.strip()
                            all_matches.append(f"### {rel_path}\n```\n{snippet}\n```\n")
                    except (subprocess.TimeoutExpired, Exception):
                        continue
                    
                    # Check total context size
                    context = "\n".join(all_matches)
                    if len(context) >= MAX_CONTEXT_CHARS:
                        break
        
        except FileNotFoundError:
            # Fallback to grep
            try:
                result = subprocess.run(
                    ["grep", "-r", "-l", "-i", "-E", pattern, repo_path],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                if result.returncode == 0 and result.stdout.strip():
                    files = result.stdout.strip().splitlines()[:15]
                    for filepath in files:
                        if filepath in seen_files:
                            continue
                        seen_files.add(filepath)
                        rel_path = os.path.relpath(filepath, repo_path)
                        all_matches.append(f"### {rel_path}\n")
                        
                        context = "\n".join(all_matches)
                        if len(context) >= MAX_CONTEXT_CHARS:
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
        """
        Analyze codebase for a ticket using pre-search + targeted Claude prompt.
        Falls back to full repo analysis if pre-search fails.
        """
        ticket_key = ticket.get("key", "")
        summary = ticket.get("summary", "")
        description = ticket.get("description", "")
        
        repo_path = self.get_repo_path(ticket_key)
        if not repo_path:
            print(f"    ⚠️ No repo mapping for {ticket_key}")
            return None
        
        # Extract keywords and pre-search
        search_text = f"{summary} {description}"
        keywords = self.extract_keywords(search_text)
        print(f"    🔎 Keywords: {', '.join(keywords[:8])}")
        
        code_context = self.pre_search(repo_path, keywords)
        
        if code_context:
            # TARGETED prompt with pre-searched context (fast, ~30s)
            print(f"    📂 Found relevant code, using targeted analysis")
            prompt = f"""I have a Jira ticket and I've already found the most relevant code in the repo. Analyze and create a specific implementation plan.

## Ticket: {ticket_key}
**Summary:** {summary}
**Description:** {description if description else 'No description provided'}

## Relevant Code Found

{code_context}

## Your Task
Based on this code, create a specific implementation plan with:
- **Files to Modify**: Which files need changes and why
- **Proposed Changes**: Specific modifications for each file
- **Implementation Steps**: Numbered step-by-step instructions
- **Risks & Dependencies**: Potential issues to consider

Be specific - include function names, code examples, and concrete steps. Do NOT give generic advice."""
            
            timeout = 120
        else:
            # FALLBACK: full repo analysis (slow, may timeout)
            print(f"    ⚠️ No code found, falling back to full repo analysis")
            prompt = f"""Analyze this codebase for a Jira ticket and create a detailed implementation plan.

## Ticket: {ticket_key}
**Summary:** {summary}
**Description:** {description if description else 'No description provided'}

## Your Task
1. Search the codebase for relevant code related to this ticket
2. Identify files that need to be modified
3. Propose a detailed solution with specific file changes

Output in markdown with sections for: Relevant Files, Proposed Changes, Implementation Steps, Risks.

Be specific - include file paths, function names, and code examples."""
            
            timeout = 300
        
        try:
            result = subprocess.run(
                [CLAUDE_CLI, "--print", prompt],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout
            else:
                print(f"    ⚠️ Claude Code returned empty or error")
                return None
                
        except subprocess.TimeoutExpired:
            print(f"    ⏱️ Claude Code timed out ({timeout}s)")
            return None
        except FileNotFoundError:
            print(f"    ❌ Claude CLI not found at {CLAUDE_CLI}")
            return None
        except Exception as e:
            print(f"    ❌ Error running Claude: {e}")
            return None
