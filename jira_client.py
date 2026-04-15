"""Jira API client for fetching assigned tickets."""
import base64
import re
import requests
from typing import List, Dict, Any, Optional
from config import Config


class JiraClient:
    """Client for interacting with Jira API."""

    def __init__(self):
        self.base_url = Config.JIRA_BASE_URL
        self.email = Config.JIRA_EMAIL
        self.api_token = Config.JIRA_API_TOKEN
        self.auth = self._create_auth_header()
        self.headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }

    def _create_auth_header(self) -> str:
        """Create Basic Auth header from email and API token."""
        credentials = f"{self.email}:{self.api_token}"
        encoded = base64.b64encode(credentials.encode()).decode()
        return f"Basic {encoded}"

    def _make_request(self, method: str, endpoint: str, data: Optional[Dict] = None) -> Optional[Dict]:
        """Make a request to Jira API with error handling."""
        url = f"{self.base_url}{endpoint}"
        headers = {**self.headers, "Authorization": self.auth}

        try:
            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                json=data if method == "POST" else None,
                params=data if method == "GET" else None,
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.Timeout:
            print(f"⏱️ Request to {endpoint} timed out")
            return None
        except requests.exceptions.HTTPError as e:
            print(f"❌ HTTP error for {endpoint}: {e}")
            return None
        except requests.exceptions.RequestException as e:
            print(f"❌ Request failed for {endpoint}: {e}")
            return None

    def get_assigned_tickets(self) -> List[Dict[str, Any]]:
        """Fetch all tickets assigned to current user."""
        account_id = self._get_my_account_id()
        if not account_id:
            print("❌ Could not get account ID")
            return []

        jql = f'assignee = "{account_id}" AND status in ("To Do", "In Progress") ORDER BY created DESC'
        data = {
            "jql": jql,
            "fields": ["key", "summary", "description", "status", "priority", "created", "updated", "labels", "components"],
            "maxResults": 100
        }

        result = self._make_request("POST", "/rest/api/3/search/jql", data)
        if not result:
            return []

        tickets = []
        for issue in result.get("issues", []):
            fields = issue.get("fields", {})
            tickets.append({
                "key": issue.get("key"),
                "summary": fields.get("summary"),
                "description": self._extract_description(fields.get("description")),
                "status": fields.get("status", {}).get("name"),
                "priority": fields.get("priority", {}).get("name"),
                "created": fields.get("created"),
                "updated": fields.get("updated"),
                "labels": fields.get("labels", []),
                "components": [c.get("name") for c in fields.get("components", [])]
            })

        return tickets

    def _get_my_account_id(self) -> str:
        """Get the current user's account ID."""
        result = self._make_request("GET", "/rest/api/2/myself")
        if result:
            return result.get("accountId", "")
        return ""

    def _extract_description(self, description: Any) -> str:
        """Extract text from Jira's description field (can be complex ADF format)."""
        if not description:
            return ""
        if isinstance(description, str):
            return description
        if isinstance(description, dict):
            return self._extract_adf_text(description)
        return str(description)

    def _extract_adf_text(self, node: Dict) -> str:
        """Recursively extract text from ADF node."""
        if node.get("type") == "text":
            return node.get("text", "")

        text_parts = []
        for content in node.get("content", []):
            text_parts.append(self._extract_adf_text(content))

        return " ".join(text_parts).strip()

    def add_comment(self, issue_key: str, markdown_text: str) -> bool:
        """Add a comment to a Jira issue, converting markdown to ADF format."""
        endpoint = f"/rest/api/3/issue/{issue_key}/comment"
        adf_body = self._markdown_to_adf(markdown_text)
        data = {"body": adf_body}

        headers = {**self.headers, "Authorization": self.auth}
        url = f"{self.base_url}{endpoint}"

        try:
            response = requests.post(url, json=data, headers=headers, timeout=30)
            response.raise_for_status()
            print(f"    💬 Posted plan as comment on {issue_key}")
            return True
        except requests.exceptions.RequestException as e:
            print(f"❌ Failed to add comment to {issue_key}: {e}")
            return False

    def _markdown_to_adf(self, markdown: str) -> Dict:
        """Convert markdown text to Atlassian Document Format (ADF)."""
        lines = markdown.split("\n")
        content = []
        i = 0

        while i < len(lines):
            line = lines[i]

            # Headings
            heading_match = re.match(r"^(#{1,6})\s+(.+)$", line)
            if heading_match:
                level = len(heading_match.group(1))
                text = heading_match.group(2)
                content.append({
                    "type": "heading",
                    "attrs": {"level": level},
                    "content": self._parse_inline(text),
                })
                i += 1
                continue

            # Horizontal rules
            if re.match(r"^---+$", line.strip()):
                content.append({"type": "rule"})
                i += 1
                continue

            # Ordered list items (consecutive)
            ol_match = re.match(r"^\d+\.\s+(.+)$", line)
            if ol_match:
                items = []
                while i < len(lines):
                    m = re.match(r"^\d+\.\s+(.+)$", lines[i])
                    if not m:
                        break
                    items.append({
                        "type": "listItem",
                        "content": [{
                            "type": "paragraph",
                            "content": self._parse_inline(m.group(1)),
                        }],
                    })
                    i += 1
                content.append({"type": "orderedList", "content": items})
                continue

            # Unordered list / checklist items (consecutive)
            ul_match = re.match(r"^[-*]\s+(\[[ x]\]\s+)?(.+)$", line)
            if ul_match:
                items = []
                while i < len(lines):
                    m = re.match(r"^[-*]\s+(\[[ x]\]\s+)?(.+)$", lines[i])
                    if not m:
                        break
                    items.append({
                        "type": "listItem",
                        "content": [{
                            "type": "paragraph",
                            "content": self._parse_inline(m.group(2)),
                        }],
                    })
                    i += 1
                content.append({"type": "bulletList", "content": items})
                continue

            # Empty line → skip
            if not line.strip():
                i += 1
                continue

            # Default: paragraph
            content.append({
                "type": "paragraph",
                "content": self._parse_inline(line),
            })
            i += 1

        return {"type": "doc", "version": 1, "content": content}

    def _parse_inline(self, text: str) -> List[Dict]:
        """Parse inline markdown (bold, italic, code, links) into ADF inline nodes."""
        nodes: List[Dict] = []
        pattern = re.compile(
            r"(\*\*(.+?)\*\*)"       # bold
            r"|(\*(.+?)\*)"           # italic
            r"|(`(.+?)`)"             # inline code
            r"|(\[(.+?)\]\((.+?)\))"  # link
        )
        last_end = 0

        for match in pattern.finditer(text):
            # Text before this match
            if match.start() > last_end:
                plain = text[last_end:match.start()]
                if plain:
                    nodes.append({"type": "text", "text": plain})

            if match.group(2):  # bold
                nodes.append({"type": "text", "text": match.group(2), "marks": [{"type": "strong"}]})
            elif match.group(4):  # italic
                nodes.append({"type": "text", "text": match.group(4), "marks": [{"type": "em"}]})
            elif match.group(6):  # code
                nodes.append({"type": "text", "text": match.group(6), "marks": [{"type": "code"}]})
            elif match.group(8):  # link
                nodes.append({
                    "type": "text",
                    "text": match.group(8),
                    "marks": [{"type": "link", "attrs": {"href": match.group(9)}}],
                })

            last_end = match.end()

        # Remaining text
        if last_end < len(text):
            remaining = text[last_end:]
            if remaining:
                nodes.append({"type": "text", "text": remaining})

        if not nodes:
            nodes.append({"type": "text", "text": text or " "})

        return nodes
