"""State manager for tracking processed tickets and awaiting responses."""
import json
import os
from datetime import datetime
from typing import Dict, List, Any, Optional
from config import Config


class StateManager:
    """Manages state for processed tickets and pending questions."""
    
    def __init__(self):
        self.state_dir = Config.STATE_DIR
        self.processed_file = Config.PROCESSED_TICKETS_FILE
        self.awaiting_file = Config.AWAITING_RESPONSES_FILE
        
        # Ensure state directory exists
        os.makedirs(self.state_dir, exist_ok=True)
        
        # Initialize files if they don't exist
        self._init_state_files()
    
    def _init_state_files(self):
        """Create state files if they don't exist."""
        if not os.path.exists(self.processed_file):
            self._write_json(self.processed_file, {"tickets": {}})
        
        if not os.path.exists(self.awaiting_file):
            self._write_json(self.awaiting_file, {"pending": {}})
    
    def _read_json(self, filepath: str) -> Dict:
        """Read JSON file."""
        try:
            with open(filepath, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {}
    
    def _write_json(self, filepath: str, data: Dict):
        """Write JSON file."""
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)
    
    def get_processed_tickets(self) -> Dict[str, Dict]:
        """Get all processed tickets."""
        data = self._read_json(self.processed_file)
        return data.get("tickets", {})
    
    def is_processed(self, ticket_key: str) -> bool:
        """Check if a ticket has been processed."""
        tickets = self.get_processed_tickets()
        return ticket_key in tickets and tickets[ticket_key].get("status") == "completed"
    
    def is_awaiting_response(self, ticket_key: str) -> bool:
        """Check if a ticket is awaiting user response."""
        data = self._read_json(self.awaiting_file)
        return ticket_key in data.get("pending", {})
    
    def mark_processing(self, ticket: Dict[str, Any]):
        """Mark a ticket as being processed."""
        data = self._read_json(self.processed_file)
        if "tickets" not in data:
            data["tickets"] = {}
        
        data["tickets"][ticket["key"]] = {
            "summary": ticket.get("summary"),
            "status": "processing",
            "started_at": datetime.utcnow().isoformat(),
            "plan_generated": False
        }
        
        self._write_json(self.processed_file, data)
    
    def mark_awaiting_response(self, ticket_key: str, questions: List[str]):
        """Mark a ticket as awaiting user response."""
        # Update processed status
        data = self._read_json(self.processed_file)
        if ticket_key in data.get("tickets", {}):
            data["tickets"][ticket_key]["status"] = "awaiting_response"
            self._write_json(self.processed_file, data)
        
        # Add to awaiting responses
        awaiting = self._read_json(self.awaiting_file)
        if "pending" not in awaiting:
            awaiting["pending"] = {}
        
        awaiting["pending"][ticket_key] = {
            "questions": questions,
            "asked_at": datetime.utcnow().isoformat()
        }
        
        self._write_json(self.awaiting_file, awaiting)
    
    def mark_completed(self, ticket_key: str, plan_path: str):
        """Mark a ticket as completed with plan."""
        data = self._read_json(self.processed_file)
        if ticket_key in data.get("tickets", {}):
            data["tickets"][ticket_key]["status"] = "completed"
            data["tickets"][ticket_key]["completed_at"] = datetime.utcnow().isoformat()
            data["tickets"][ticket_key]["plan_generated"] = True
            data["tickets"][ticket_key]["plan_path"] = plan_path
            self._write_json(self.processed_file, data)
        
        # Remove from awaiting responses if present
        awaiting = self._read_json(self.awaiting_file)
        if ticket_key in awaiting.get("pending", {}):
            del awaiting["pending"][ticket_key]
            self._write_json(self.awaiting_file, awaiting)
    
    def get_awaiting_questions(self, ticket_key: str) -> Optional[List[str]]:
        """Get questions for a ticket awaiting response."""
        data = self._read_json(self.awaiting_file)
        pending = data.get("pending", {}).get(ticket_key, {})
        return pending.get("questions")
    
    def get_ticket_state(self, ticket_key: str) -> Optional[Dict]:
        """Get the current state of a ticket."""
        data = self._read_json(self.processed_file)
        return data.get("tickets", {}).get(ticket_key)
