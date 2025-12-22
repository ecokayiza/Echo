import time
import json
from enum import Enum
from typing import Any, Dict, List, Optional, Callable

############################################
# Message Tool to Trace the Execution of RAG System
############################################

class EventType(Enum):
    INFO = "INFO"           # General information
    THOUGHT = "THOUGHT"     # Internal reasoning (CoT)
    DECISION = "DECISION"   # Routing or judgment results
    ACTION = "ACTION"       # Tool calls or DB queries
    OUTPUT = "OUTPUT"       # Final or intermediate outputs
    ERROR = "ERROR"         # Exceptions

class TraceEvent:
    def __init__(self, source: str, event_type: EventType, content: Any, details: Optional[Dict] = None):
        self.timestamp = time.time()
        self.source = source
        self.event_type = event_type
        self.content = content
        self.details = details or {}

    def __str__(self):
        return f"[{self.timestamp:.2f}] [{self.source}] {self.event_type.value}: {self.content}"

    def to_dict(self):
        return {
            "timestamp": self.timestamp,
            "source": self.source,
            "type": self.event_type.value,
            "content": self.content,
            "details": self.details
        }

class TraceBoard:
    """
    A shared board to track the execution trace of the RAG system.
    Supports the Observer pattern for streaming updates.
    """
    def __init__(self):
        self._trace: List[TraceEvent] = []
        self._listeners: List[Callable[[Dict], None]] = []

    def log(self, source: str, event_type: str, content: Any, details: Optional[Dict] = None):
        """
        Log an event to the board.
        
        Args:
            source: Name of the module (e.g., "Orchestrator", "Retriever")
            event_type: One of EventType values (e.g., "THOUGHT", "DECISION")
            content: Main message or data
            details: Extra metadata (e.g., latency, scores)
        """
        # Convert string to Enum if needed, or just use string
        try:
            e_type = EventType(event_type) if isinstance(event_type, str) else event_type
        except ValueError:
            e_type = EventType.INFO

        event = TraceEvent(source, e_type, content, details)
        self._trace.append(event)
        self._notify(event)

    def add_listener(self, callback: Callable[[Dict], None], event_types: Optional[List[EventType]] = None, sources: Optional[List[str]] = None):
        """
        Add subscribers to listen for new events.
        
        Args:
            callback: Function to call when event occurs
            event_types: Optional list of EventTypes to filter for
            sources: Optional list of source strings to filter for
        """
        self._listeners.append({
            "func": callback,
            "types": event_types,
            "sources": sources
        })

    def _notify(self, event: TraceEvent):
        data = event.to_dict()
        for listener in self._listeners:
            # Check filters
            if listener["types"] and event.event_type not in listener["types"]:
                continue
            if listener["sources"] and event.source not in listener["sources"]:
                continue
                
            try:
                listener["func"](data)
            except Exception as e:
                print(f"Error in trace listener: {e}")

    def get_history(self):
        return [e.to_dict() for e in self._trace]

    def clear(self):
        self._trace = []
        
