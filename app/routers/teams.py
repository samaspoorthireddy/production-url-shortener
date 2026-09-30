import logging
import secrets
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from database import get_db
from models import Team, UserTeam, TeamInvitation
from app.dependencies import get_current_user
from app.schemas.teams import (
    TeamCreate,
    TeamResponse,
    TeamMemberAdd,
    TeamMemberResponse,
    TeamMemberUpdate,
    InvitationCreate,
    InvitationResponse,
    InvitationAccept
)

logger = logging.getLogger("url_shortener")

router = APIRouter(prefix="/teams", tags=["teams"])


@router.post("/", response_model=TeamResponse, status_code=status.HTTP_201_CREATED)
def create_team(
    team_in: TeamCreate,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user)
):
    """
    Creates a new Team record and adds the creator as an admin member.
    """
    try:
        db_team = Team(
            name=team_in.name,
            description=team_in.description,
            owner_id=current_user
        )
        db.add(db_team)
        db.flush()  # Populates db_team.id

        db_membership = UserTeam(
            user_id=current_user,
            team_id=db_team.id,
            role="admin"
        )
        db.add(db_membership)
        db.commit()
        db.refresh(db_team)
        logger.info(
            f"Audit Log - Team Created: team_id={db_team.id}, owner_id={current_user}, requesting_user_id={current_user}"
        )
        return db_team
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error occurred: {str(e)}"
        )


@router.get("/{team_id}", response_model=TeamResponse)
def get_team(
    team_id: int,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user)
):
    """
    Retrieves the team details by its ID, checking that the user is a member of the team.
    """
    db_team = db.query(Team).filter(Team.id == team_id).first()
    if not db_team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found"
        )

    # Check membership
    membership = db.query(UserTeam).filter(
        UserTeam.team_id == team_id,
        UserTeam.user_id == current_user
    ).first()
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this team"
        )

    return db_team


@router.post("/{team_id}/members", response_model=TeamMemberResponse, status_code=status.HTTP_201_CREATED)
def add_team_member(
    team_id: int,
    member_in: TeamMemberAdd,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user)
):
    """
    Adds a new member to the team. Only team owners or administrators are authorized.
    """
    db_team = db.query(Team).filter(Team.id == team_id).first()
    if not db_team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found"
        )

    # Check if requesting user is the owner or an admin of this team
    is_owner = db_team.owner_id == current_user
    is_admin = db.query(UserTeam).filter(
        UserTeam.team_id == team_id,
        UserTeam.user_id == current_user,
        UserTeam.role == "admin"
    ).first() is not None

    if not (is_owner or is_admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only team owners or administrators can add members"
        )

    # Check if target user is already a member
    existing_membership = db.query(UserTeam).filter(
        UserTeam.team_id == team_id,
        UserTeam.user_id == member_in.user_id
    ).first()
    if existing_membership:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is already a member of this team"
        )

    try:
        db_membership = UserTeam(
            user_id=member_in.user_id,
            team_id=team_id,
            role=member_in.role
        )
        db.add(db_membership)
        db.commit()
        db.refresh(db_membership)
        return db_membership
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error occurred: {str(e)}"
        )


@router.put("/{team_id}/members/{user_id}", response_model=TeamMemberResponse)
def update_team_member_role(
    team_id: int,
    user_id: str,
    member_update: TeamMemberUpdate,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user)
):
    """
    Updates the role of a team member with strict security controls.
    """
    # 2. A user cannot modify their own role.
    if user_id == current_user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot modify your own role."
        )

    # 3. Validate role string
    role = member_update.role.strip() if member_update.role else ""
    if not role or role not in {"owner", "admin", "member", "viewer"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Role must be one of 'owner', 'admin', 'member', or 'viewer'"
        )

    db_team = db.query(Team).filter(Team.id == team_id).first()
    if not db_team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found"
        )

    # Check requester permissions
    requester_membership = db.query(UserTeam).filter(
        UserTeam.team_id == team_id,
        UserTeam.user_id == current_user
    ).first()

    is_owner = db_team.owner_id == current_user
    is_admin = requester_membership is not None and requester_membership.role == "admin"

    if not (is_owner or is_admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only team owners or administrators can modify member roles"
        )

    # 4. Only owner can promote to owner. Admin cannot.
    if role == "owner" and not is_owner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the team owner can transfer ownership"
        )

    # Check if target user is a member
    membership = db.query(UserTeam).filter(
        UserTeam.team_id == team_id,
        UserTeam.user_id == user_id
    ).first()

    if not membership:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found in this team"
        )

    old_role = membership.role

    try:
        if role == "owner":
            db_team.owner_id = user_id
            membership.role = "owner"
            # Demote old owner to admin
            if requester_membership:
                requester_membership.role = "admin"
        else:
            membership.role = role

        db.commit()
        db.refresh(membership)

        # 5. Log audit trail
        logger.info(
            f"Audit Log - Role Change: team_id={team_id}, target_user_id={user_id}, "
            f"old_role={old_role}, new_role={role}, requesting_user_id={current_user}",
            extra={
                "team_id": team_id,
                "target_user_id": user_id,
                "old_role": old_role,
                "new_role": role,
                "requesting_user_id": current_user
            }
        )

        return membership
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error occurred: {str(e)}"
        )


@router.post("/{team_id}/invitations", response_model=InvitationResponse, status_code=status.HTTP_201_CREATED)
def invite_to_team(
    team_id: int,
    inv_in: InvitationCreate,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user)
):
    """
    Creates an invitation for a user to join a team. Only owners/admins can invite.
    """
    db_team = db.query(Team).filter(Team.id == team_id).first()
    if not db_team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found"
        )

    # Check requester permission
    requester_membership = db.query(UserTeam).filter(
        UserTeam.team_id == team_id,
        UserTeam.user_id == current_user
    ).first()

    is_owner = db_team.owner_id == current_user
    is_admin = requester_membership is not None and requester_membership.role == "admin"

    if not (is_owner or is_admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only team owners or administrators can invite members"
        )

    email = inv_in.email.strip().lower()
    role = inv_in.role.strip()

    # Extract user_id from email (user_b@example.com -> user_b)
    invited_user_id = email.split("@")[0]

    # Verify if user is already a member of the team
    existing_member = db.query(UserTeam).filter(
        UserTeam.team_id == team_id,
        UserTeam.user_id == invited_user_id
    ).first()
    if existing_member:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is already a member of this team"
        )

    # Verify if there's already a pending invitation for this email in this team
    existing_invitation = db.query(TeamInvitation).filter(
        TeamInvitation.team_id == team_id,
        TeamInvitation.email == email,
        TeamInvitation.status == "pending"
    ).first()
    if existing_invitation:
        # Check if expired
        if existing_invitation.expires_at > datetime.now(timezone.utc):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A pending invitation already exists for this email"
            )
        else:
            existing_invitation.status = "expired"
            db.commit()

    try:
        token = secrets.token_hex(16)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
        invitation = TeamInvitation(
            team_id=team_id,
            email=email,
            role=role,
            token=token,
            status="pending",
            expires_at=expires_at
        )
        db.add(invitation)
        db.commit()
        db.refresh(invitation)

        # Log audit trail
        logger.info(
            f"Audit Log - Invitation Sent: team_id={team_id}, email={email}, "
            f"role={role}, token={token}, requesting_user_id={current_user}"
        )
        return invitation
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error occurred: {str(e)}"
        )


@router.post("/invitations/accept", response_model=TeamMemberResponse)
def accept_invitation(
    accept_in: InvitationAccept,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user)
):
    """
    Accepts an invitation, adding the user to the team.
    """
    invitation = db.query(TeamInvitation).filter(TeamInvitation.token == accept_in.token).first()
    if not invitation or invitation.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invitation token is invalid or has already been accepted/expired"
        )

    # Check expiration
    if invitation.expires_at < datetime.now(timezone.utc):
        try:
            invitation.status = "expired"
            db.commit()
        except Exception:
            db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invitation has expired"
        )

    # Check recipient matching
    invited_username = invitation.email.split("@")[0].lower()
    if current_user.lower() != invited_username:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This invitation was sent to a different user email"
        )

    # Check if already a member
    existing_member = db.query(UserTeam).filter(
        UserTeam.team_id == invitation.team_id,
        UserTeam.user_id == current_user
    ).first()
    if existing_member:
        try:
            invitation.status = "accepted"
            db.commit()
        except Exception:
            db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You are already a member of this team"
        )

    try:
        # Create membership
        membership = UserTeam(
            user_id=current_user,
            team_id=invitation.team_id,
            role=invitation.role
        )
        db.add(membership)
        invitation.status = "accepted"
        db.commit()
        db.refresh(membership)

        # Log audit trail
        logger.info(
            f"Audit Log - Invitation Accepted: team_id={invitation.team_id}, "
            f"email={invitation.email}, role={invitation.role}, user_id={current_user}"
        )
        return membership
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error occurred: {str(e)}"
        )


@router.delete("/{team_id}")
def delete_team(
    team_id: int,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user)
):
    """
    Deletes a team. Restricted to owners/admins.
    """
    db_team = db.query(Team).filter(Team.id == team_id).first()
    if not db_team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found"
        )

    # Check permission boundary
    requester_membership = db.query(UserTeam).filter(
        UserTeam.team_id == team_id,
        UserTeam.user_id == current_user
    ).first()

    is_owner = db_team.owner_id == current_user
    is_admin = requester_membership is not None and requester_membership.role == "admin"

    if not (is_owner or is_admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only team owners or administrators can delete the team"
        )

    try:
        db.delete(db_team)
        db.commit()

        # Log audit trail
        logger.info(f"Audit Log - Team Deleted: team_id={team_id}, requesting_user_id={current_user}")
        return {"status": "deleted"}
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error occurred: {str(e)}"
        )


@router.delete("/{team_id}/members/{user_id}")
def remove_team_member(
    team_id: int,
    user_id: str,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user)
):
    """
    Removes a member from a team.
    """
    db_team = db.query(Team).filter(Team.id == team_id).first()
    if not db_team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found"
        )

    target_membership = db.query(UserTeam).filter(
        UserTeam.team_id == team_id,
        UserTeam.user_id == user_id
    ).first()

    if not target_membership:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found in this team"
        )

    # If user is trying to remove themselves (leave team)
    if user_id == current_user:
        if db_team.owner_id == current_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Owners cannot leave the team. Transfer ownership first."
            )
        # Otherwise allow leaving
    else:
        # Check requester permission to remove others
        requester_membership = db.query(UserTeam).filter(
            UserTeam.team_id == team_id,
            UserTeam.user_id == current_user
        ).first()

        is_owner = db_team.owner_id == current_user
        is_admin = requester_membership is not None and requester_membership.role == "admin"

        if not (is_owner or is_admin):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only team owners or administrators can remove members"
            )

        # Admin cannot remove owner
        if target_membership.user_id == db_team.owner_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot remove the team owner"
            )

        # Admin cannot remove another admin
        if target_membership.role == "admin" and not is_owner:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Administrators cannot remove other administrators"
            )

    try:
        db.delete(target_membership)
        db.commit()

        # Log audit trail
        logger.info(
            f"Audit Log - Member Removed: team_id={team_id}, "
            f"target_user_id={user_id}, requesting_user_id={current_user}"
        )
        return {"status": "removed"}
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error occurred: {str(e)}"
        )
