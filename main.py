#!/usr/bin/env python3
"""Jira Agent - Polls for assigned tickets and generates implementation plans."""
import time
import sys
from datetime import datetime

from config import Config
from jira_client import JiraClient
from state_manager import StateManager
from plan_generator import PlanGenerator
from discord_client import DiscordClient


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

    def run(self):
        """Main polling loop."""
        print(f"🚀 Jira Agent started at {datetime.utcnow().isoformat()}")
        print(f"📅 Polling every {self.poll_interval} seconds")
        print(f"👤 Watching tickets for: {Config.JIRA_EMAIL}")
        print("-" * 50)

        while True:
            try:
                self.poll_cycle()
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
        ticket_key = ticket.get("key")

        # Try codebase-aware analysis first
        from codebase_analyzer import CodebaseAnalyzer
        analyzer = CodebaseAnalyzer()
        repo_path = analyzer.get_repo_path(ticket_key)
        
        plan = None
        if repo_path:
            print(f"    🔬 Attempting codebase-aware analysis ({repo_path})...")
            codebase_plan = analyzer.analyze_ticket(ticket)
            if codebase_plan:
                print(f"    🧠 Using codebase-aware plan")
                plan = codebase_plan
            else:
                print(f"    ⚠️ Codebase analysis failed, falling back to generic plan")

        # Fall back to generic plan
        if plan is None:
            print(f"    📝 Using generic plan generation")
            plan = self.planner.generate_plan(ticket, clarifications)
        
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

    try:
        agent.run()
    except KeyboardInterrupt:
        print("\n\n👋 Jira Agent stopped by user")
        sys.exit(0)


if __name__ == "__main__":
    main()
