#!/usr/bin/env python3
"""Jira Agent - Polls for assigned tickets and generates implementation plans."""
import time
import sys
from datetime import datetime

from config import Config
from jira_client import JiraClient, JiraAuthError
from state_manager import StateManager
from plan_generator import PlanGenerator
from discord_client import DiscordClient


# After this many consecutive auth failures, exit rather than spin forever.
MAX_CONSECUTIVE_AUTH_FAILURES = 3


class JiraAgent:
    """Main agent that orchestrates ticket polling and plan generation."""

    def __init__(self):
        self.jira = JiraClient()
        self.state = StateManager()
        self.planner = PlanGenerator()
        self.discord = DiscordClient()
        self.poll_interval = Config.POLL_INTERVAL_SECONDS
        # Map ticket_key -> thread_id for the lifetime of this process
        self.thread_ids: dict = {}
        self._consecutive_auth_failures = 0

    def startup_self_check(self) -> bool:
        """Verify Jira connectivity and credentials before entering the poll loop."""
        print(f"🔐 Running startup self-check against {Config.JIRA_BASE_URL} ...")
        ok, message = self.jira.test_auth()
        if ok:
            print(f"✅ {message}")
            return True
        print(f"❌ Jira self-check failed: {message}")
        return False

    def run(self):
        """Main polling loop."""
        print(f"🚀 Jira Agent started at {datetime.utcnow().isoformat()}")
        print(f"📅 Polling every {self.poll_interval} seconds")
        print(f"🌐 Jira base URL: {Config.JIRA_BASE_URL}")
        print(f"👤 Watching tickets for: {Config.JIRA_EMAIL}")
        print("-" * 50)

        while True:
            try:
                self.poll_cycle()
                self._consecutive_auth_failures = 0
            except JiraAuthError as e:
                self._consecutive_auth_failures += 1
                print(
                    f"🔒 Auth failure #{self._consecutive_auth_failures} "
                    f"(max {MAX_CONSECUTIVE_AUTH_FAILURES}): {e}"
                )
                if self._consecutive_auth_failures >= MAX_CONSECUTIVE_AUTH_FAILURES:
                    print(
                        "❌ Giving up after repeated auth failures. Check JIRA_EMAIL / "
                        "JIRA_API_TOKEN / JIRA_BASE_URL in .env and restart the agent."
                    )
                    sys.exit(2)
            except Exception as e:
                print(f"❌ Error in poll cycle: {e}")

            print(f"\n⏰ Next poll in {self.poll_interval} seconds...\n")
            time.sleep(self.poll_interval)

    def poll_cycle(self):
        """Single polling cycle."""
        print(f"\n🔍 Polling Jira at {datetime.utcnow().isoformat()}")

        tickets = self.jira.get_assigned_tickets()

        if not tickets:
            print("📭 No tickets found or API error")
            return

        print(f"📋 Found {len(tickets)} assigned tickets")

        for ticket in tickets:
            self.process_ticket(ticket)

    def process_ticket(self, ticket: dict):
        """Process a single ticket."""
        ticket_key = ticket.get("key")
        summary = ticket.get("summary", "No summary")
        status = ticket.get("status", "")

        # Only process tickets that are To Do or In Progress
        allowed_statuses = {"To Do", "In Progress"}
        if status not in allowed_statuses:
            print(f"  ⏭️ {ticket_key}: Skipping (status: {status})")
            return

        if self.state.is_processed(ticket_key):
            print(f"  ✓ {ticket_key}: Already processed")
            return

        if self.state.is_awaiting_response(ticket_key):
            print(f"  ⏳ {ticket_key}: Awaiting your response")
            return

        print(f"  🆕 {ticket_key}: {summary[:50]}...")

        self.state.mark_processing(ticket)

        # Create Discord thread (or fall back to webhook notification)
        thread_id = self.discord.notify_new_ticket(ticket_key, summary)
        if thread_id:
            self.thread_ids[ticket_key] = thread_id

        # Analyze ticket for clarification needs
        needs_clarification, questions = self.planner.analyze_ticket(ticket)

        if needs_clarification:
            print(f"    ❓ Needs clarification ({len(questions)} questions)")
            thread_id = self.thread_ids.get(ticket_key)
            if self.discord.ask_clarification(ticket_key, questions, thread_id):
                print(f"    📤 Sent clarification request to Discord")
                self.state.mark_awaiting_response(ticket_key, questions)
            else:
                print(f"    ⚠️ Failed to send clarification, generating plan anyway")
                self.generate_and_save_plan(ticket)
        else:
            print(f"    ✨ Generating plan...")
            self.generate_and_save_plan(ticket)

    def generate_and_save_plan(self, ticket: dict, clarifications: dict = None):
        """Generate plan with codebase analysis, save to file, post to Jira and Discord."""
        from codebase_analyzer import CodebaseAnalyzer

        ticket_key = ticket.get("key")

        analyzer = CodebaseAnalyzer()
        plan = analyzer.analyze_ticket(ticket)

        if plan is None:
            plan = (
                f"⚠️ Could not generate a codebase-aware plan for {ticket_key}. "
                f"The agent searched GitHub but could not find a matching repository "
                f"or the analysis timed out. Please create a plan manually."
            )
            print(f"    ⚠️ Using error message (no plan generated)")

        plan_path = self.planner.save_plan(ticket_key, plan)
        print(f"    📄 Plan saved to: {plan_path}")

        self.state.mark_completed(ticket_key, plan_path)

        # Post plan as comment on Jira ticket
        if self.jira.add_comment(ticket_key, plan):
            print(f"    💬 Plan posted to Jira as comment")
        else:
            print(f"    ⚠️ Failed to post plan to Jira")

        # Post plan to Discord thread (or notify via webhook)
        thread_id = self.thread_ids.get(ticket_key)
        if thread_id:
            self.discord.post_plan_to_thread(thread_id, ticket_key, plan)
            self.discord.notify_plan_complete(ticket_key, f"Plan saved to `{plan_path}`", thread_id)
        else:
            self.discord.notify_plan_complete(ticket_key, f"Plan saved to `{plan_path}`")

        print(f"    ✅ {ticket_key}: Plan complete!")


def main():
    """Entry point."""
    if not Config.validate():
        print("\n💡 Create a .env file from .env.example and fill in your credentials")
        sys.exit(1)

    agent = JiraAgent()

    if not agent.startup_self_check():
        print(
            "\n💡 Fix the issue above (credentials, base URL, or network) and restart. "
            "Refusing to enter the polling loop with broken auth."
        )
        sys.exit(2)

    try:
        agent.run()
    except KeyboardInterrupt:
        print("\n\n👋 Jira Agent stopped by user")
        sys.exit(0)


if __name__ == "__main__":
    main()
