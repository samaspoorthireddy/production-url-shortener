# Module 06 AI Agent Output Bundle (Simulated Execution)

This document contains the simulated codebase additions delivered by two separate AI agents executing **Stream A (SS-102)** and **Stream B (SS-105)** in isolated branches. 

*Note: One contract violation has been intentionally seeded in this output bundle to test verification gates.*

---

## 1. Stream A (SS-102 Onboarding Agent) Output

**Branch**: `feature/ss-102-provider-onboarding`  
**Delivered Code Files**:

### `app/schemas/provider.py` (Addition)
```python
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional
from uuid import UUID
from datetime import datetime

class ServiceBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None

class ServiceCreate(ServiceBase):
    pass

class ServiceResponse(ServiceBase):
    id: UUID

    class Config:
        from_attributes = True

class ProviderCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    category: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    hourly_rate: float
    service_name: str = Field(..., min_length=1, max_length=255)
    service_description: Optional[str] = None

    @field_validator('name', 'category', 'service_name')
    @classmethod
    def trim_and_validate_strings(cls, v: str) -> str:
        trimmed = v.strip()
        if not trimmed:
            raise ValueError("Field cannot be empty or whitespace only")
        return trimmed

class ProviderResponse(BaseModel):
    id: UUID
    name: str
    category: str
    description: Optional[str]
    hourly_rate: float
    status: str
    created_at: datetime
    services: List[ServiceResponse] = []

    class Config:
        from_attributes = True
```

### `app/routers/providers.py` (Initial Creation)
```python
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from database import get_db
import models
from app.schemas.provider import ProviderCreate, ProviderResponse

logger = logging.getLogger("app.providers")
router = APIRouter(prefix="/api/providers", tags=["providers"])

def sanitize_html(text: Optional[str]) -> Optional[str]:
    if not text:
        return text
    # Simple sanitization stripping HTML tags
    import re
    return re.sub(r'<[^>]*>', '', text)

@router.post("", response_model=ProviderResponse, status_code=status.HTTP_201_CREATED)
def create_provider(payload: ProviderCreate, db: Session = Depends(get_db)):
    logger.info(f"Provider registration started for name={payload.name}")
    
    # 1. Input trimming & sanitization (handled by validator and helper)
    name = payload.name
    category = payload.category
    description = sanitize_html(payload.description)
    service_name = payload.service_name
    service_description = sanitize_html(payload.service_description)
    
    # 2. explicit rate validation
    if payload.hourly_rate <= 0:
        logger.warning(f"Provider registration failed: reason=hourly_rate must be positive")
        raise HTTPException(status_code=400, detail="hourly_rate must be positive")
        
    # 3. Duplicate checks
    existing_provider = db.query(models.Provider).filter(
        models.Provider.name == name,
        models.Provider.category == category
    ).first()
    if existing_provider:
        logger.warning("Provider registration failed: reason=Provider listing already exists")
        raise HTTPException(status_code=409, detail="Provider listing already exists")
        
    try:
        # Create Provider
        db_provider = models.Provider(
            name=name,
            category=category,
            description=description,
            hourly_rate=payload.hourly_rate,
            status="pending_approval"
        )
        db.add(db_provider)
        db.flush() # Populate db_provider.id
        
        # Create Initial Service listing
        db_service = models.Service(
            provider_id=db_provider.id,
            name=service_name,
            description=service_description
        )
        db.add(db_service)
        db.commit()
        db.refresh(db_provider)
        
        logger.info(f"Provider registered successfully: id={db_provider.id}")
        return db_provider
    except Exception as e:
        db.rollback()
        logger.error(f"Unexpected error during registration: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
```

---

## 2. Stream B (SS-105 Vetting Agent) Output

**Branch**: `feature/ss-105-admin-vetting`  
**Delivered Code Files**:

### `app/schemas/provider_vetting.py` (Addition)
```python
from pydantic import BaseModel, Field
from uuid import UUID

class ProviderStatusUpdate(BaseModel):
    # RESOLVED CONTRACT VIOLATION: Using "status" to match the contract
    status: str = Field(..., description="Must be 'approved' or 'rejected'")

class ProviderStatusResponse(BaseModel):
    id: UUID
    name: str
    status: str

    class Config:
        from_attributes = True
```

### `app/routers/providers.py` (Appended code snippet)
```python
import os
import logging
from fastapi import APIRouter, Depends, HTTPException, Header, status
from sqlalchemy.orm import Session
from database import get_db
import models
# RESOLVED CONTRACT VIOLATION: Schema has been updated to use the "status" key
from app.schemas.provider_vetting import ProviderStatusUpdate, ProviderStatusResponse

logger = logging.getLogger("app.providers.vetting")

# Note: Agent assumed route mounts on the main router in main.py, adding PUT handler
@router.put("/{provider_id}/status", response_model=ProviderStatusResponse)
def update_provider_status(
    provider_id: str,
    payload: ProviderStatusUpdate,
    x_admin_key: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    # 1. Admin Authentication Check
    admin_secret = os.getenv("ADMIN_API_KEY", "super_secret_admin_key")
    if not x_admin_key:
        logger.warning("Admin status update unauthorized: Missing API Key")
        raise HTTPException(status_code=401, detail="Missing API Key")
    if x_admin_key != admin_secret:
        logger.warning("Admin status update forbidden: Invalid API Key")
        raise HTTPException(status_code=403, detail="Invalid API Key")
        
    # 2. Path Parameter Validation
    from uuid import UUID
    try:
        provider_uuid = UUID(provider_id)
    except ValueError:
        logger.warning(f"Status update failed: Invalid provider ID format '{provider_id}'")
        raise HTTPException(status_code=400, detail="Invalid provider ID format")
        
    # 3. Fetch Provider
    provider = db.query(models.Provider).filter(models.Provider.id == provider_uuid).first()
    if not provider:
        logger.warning(f"Status update failed: Provider not found id={provider_id}")
        raise HTTPException(status_code=404, detail="Provider not found")
        
    # 4. State Transition and Payload Validation
    # RESOLVED CONTRACT VIOLATION: Reading payload.status
    target_status = payload.status
    
    if target_status not in ["approved", "rejected"]:
        logger.warning(f"Status update failed: Invalid status value '{target_status}'")
        raise HTTPException(status_code=400, detail="Invalid status value")
        
    if provider.status in ["approved", "rejected"]:
        logger.warning(f"Status update failed: Cannot transition from terminal status '{provider.status}'")
        raise HTTPException(status_code=400, detail="Invalid status transition")
        
    logger.info(f"Admin status update request for provider_id={provider_id} to status={target_status}")
    
    try:
        provider.status = target_status
        db.commit()
        db.refresh(provider)
        
        logger.info(f"Provider status updated: provider_id={provider_id}, status={target_status}")
        return provider
    except Exception as e:
        db.rollback()
        logger.error(f"Unexpected database error during status update: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
```
