from typing import Dict, List
from fastapi import WebSocket

class ActivityFeedManager:
    """
    Manages active WebSocket connections for the real-time team activity feed.
    Connections are stored in a nested structure: team_id -> user_id -> list of WebSockets.
    This allows broadcasting to all members of a specific team, and tracking connections
    per user.
    """
    def __init__(self):
        # Maps team_id -> user_id -> List[WebSocket]
        self.active_connections: Dict[int, Dict[str, List[WebSocket]]] = {}

    async def connect(self, team_id: int, user_id: str, websocket: WebSocket):
        """
        Accepts a connection and registers it in the manager.
        """
        await websocket.accept()
        if team_id not in self.active_connections:
            self.active_connections[team_id] = {}
        if user_id not in self.active_connections[team_id]:
            self.active_connections[team_id][user_id] = []
        self.active_connections[team_id][user_id].append(websocket)

    def disconnect(self, team_id: int, user_id: str, websocket: WebSocket):
        """
        Removes a connection from the manager and cleans up empty dictionaries.
        """
        if team_id in self.active_connections:
            if user_id in self.active_connections[team_id]:
                if websocket in self.active_connections[team_id][user_id]:
                    self.active_connections[team_id][user_id].remove(websocket)
                if not self.active_connections[team_id][user_id]:
                    del self.active_connections[team_id][user_id]
            if not self.active_connections[team_id]:
                del self.active_connections[team_id]

    async def broadcast(self, team_id: int, event: dict):
        """
        Broadcasts an event as a JSON dict to all active WebSocket connections for a specific team.
        """
        if team_id not in self.active_connections:
            return

        # Iterate over a copy of the dictionary/lists to prevent issues if a disconnect happens concurrently
        for user_id, websockets in list(self.active_connections[team_id].items()):
            for websocket in list(websockets):
                try:
                    await websocket.send_json(event)
                except Exception:
                    # Clean up the connection if broadcasting fails (e.g. client disconnected silently)
                    self.disconnect(team_id, user_id, websocket)

activity_feed_manager = ActivityFeedManager()
