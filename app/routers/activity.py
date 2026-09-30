from fastapi import APIRouter, WebSocket, Depends, status
from sqlalchemy.orm import Session
from database import get_db
from models import Team, UserTeam
from app.dependencies import API_KEYS
from app.services.activity_feed import activity_feed_manager
import logging

logger = logging.getLogger("url_shortener")

router = APIRouter()


@router.websocket("/teams/{team_id}/feed")
async def team_activity_feed(
    websocket: WebSocket,
    team_id: int,
    token: str = None,
    db: Session = Depends(get_db)
):
    # 1. Authenticate token
    if not token:
        # Handshake rejection for missing token
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Missing authentication token")
        return

    user_id = API_KEYS.get(token)
    if not user_id:
        # Handshake rejection for invalid token
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid authentication token")
        return

    # 2. Validate team existence
    db_team = db.query(Team).filter(Team.id == team_id).first()
    if not db_team:
        # Handshake rejection for non-existent team
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Team not found")
        return

    # 3. Validate user is a member of the specified team
    membership = db.query(UserTeam).filter(
        UserTeam.team_id == team_id,
        UserTeam.user_id == user_id
    ).first()
    if not membership:
        # Handshake rejection for unauthorized member
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="User is not a member of this team")
        return

    # 4. Accept connection and store in connection manager
    await activity_feed_manager.connect(team_id, user_id, websocket)
    logger.info(f"User {user_id} connected to team {team_id} activity feed.")

    try:
        # 5. Handle connection lifecycle: keep connection alive and wait for disconnection
        while True:
            # Block waiting for any client messages. Since it's a read-only activity feed,
            # we don't expect messages from the client. But we must listen to detect disconnects.
            await websocket.receive_text()
    except Exception as e:
        logger.info(f"WebSocket disconnected for user {user_id} on team {team_id}: {str(e)}")
    finally:
        # 6. Clean up connection on disconnect
        activity_feed_manager.disconnect(team_id, user_id, websocket)
        logger.info(f"User {user_id} disconnected from team {team_id} activity feed cleaned up.")
