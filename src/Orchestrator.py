from utils.TraceBoard import TraceBoard, EventType
from typing import Any, Callable, Dict, List, Optional
import os
import time

############################################
# !Core
# Another LLM. Judge Quality and Decide the Flow. 
# Interact With:
#   - QueryProcessor    (Query Level)
#   - Adapter           (Retrival Level)
#   - ContextManager    (Response Level)
#   - ChatModel         (Prompt Level)
# Extra Injection:
#   - User Profile.
############################################


class Orchestrator:
    def __init__(self, board: TraceBoard = None):
        self.board = board or TraceBoard()
        
        # Setup reactive hooks (Event-Driven Architecture)
        self._setup_hooks()

    def _setup_hooks(self):
        """
        Decide How to React to events (Immediate reactions).
        (By adding a new listener with reaction function)
        """
        self.board.add_listener(
            self._on_error_detected, 
            event_types=[EventType.ERROR]
        )

    def _on_error_detected(self, event: Dict):
        # some logic
        pass


    def run(self, user_query: str):
        """
        Main entry point for the RAG flow.
        """
        self.board.clear()
        self.board.log("Orchestrator", "INFO", f"Starting process for query: {user_query}")
        time.sleep(1)  # Simulate processing delay
        self.board.log("Orchestrator", "THOUGHT", "Decomposing the query and deciding next steps.")
        time.sleep(1)  # Simulate processing delay
        self.board.log("Orchestrator", "DECISION", "Decided to fetch documents from the knowledge base.")
        time.sleep(1)  # Simulate processing delay
        self.board.log("Orchestrator", "ACTION", "Invoking Retriever to fetch relevant documents.")
        time.sleep(1)  # Simulate processing delay
        self.board.log("Orchestrator", "ERROR", "Process completed successfully.")
        
    def get_trace_stream(self, callback):
        """
        Allow frontend/API to subscribe to the stream
        """
        self.board.add_listener(callback) 

class ConsoleStreamer:
    """
    A simple console-based streamer that prints events in real-time.
    """
    def on_event(self, event: dict):
        timestamp = time.strftime("%H:%M:%S", time.localtime(event['timestamp']))
        source = event['source']
        e_type = event['type']
        content = event['content']
        
        if e_type == EventType.ERROR.value:
            print(f"\033[91m[{timestamp}] [{source}] {e_type}: {content}\033[0m", flush=True)
            return
        if e_type == EventType.DECISION.value:
            print(f"\033[34m[{timestamp}] [{source}] {e_type}: {content}\033[0m", flush=True)
            return
        
        print(f"[{timestamp}] [{source}]: {content}", flush=True)

def main():
    board = TraceBoard()
    orchestrator = Orchestrator(board=board)
    streamer = ConsoleStreamer()
    
    orchestrator.get_trace_stream(streamer.on_event)

    orchestrator.run("如何使用 RL 微调 Orchestrator?")


if __name__ == "__main__":
    main()
        
