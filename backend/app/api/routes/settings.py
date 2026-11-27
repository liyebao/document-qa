import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, settings_rate_limit
from app.db.session import get_db
from app.models.user import User
from app.schemas.settings import (
    ConnectionTestRequest,
    ConnectionTestResult,
    ModelProviderConfigCreate,
    ModelProviderConfigOut,
    ModelProviderSettingsOut,
    ProviderModelsOut,
    ProviderRoleRequest,
)
from app.services import model_provider

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/model-providers", response_model=ModelProviderSettingsOut)
def get_model_provider_settings(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> ModelProviderSettingsOut:
    return model_provider.build_settings(db, user)


@router.post("/model-providers", response_model=ModelProviderConfigOut)
def save_model_provider(
    payload: ModelProviderConfigCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _: None = Depends(settings_rate_limit),
) -> ModelProviderConfigOut:
    return model_provider.upsert_config(db, user, payload)


@router.post("/model-providers/{config_id}/role", response_model=ModelProviderSettingsOut)
def set_model_provider_role(
    config_id: uuid.UUID,
    payload: ProviderRoleRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _: None = Depends(settings_rate_limit),
) -> ModelProviderSettingsOut:
    return model_provider.set_preferred_provider(db, user, config_id, payload.role)


@router.get("/model-providers/{provider_key}/models", response_model=ProviderModelsOut)
def list_provider_models(
    provider_key: str,
    user: User = Depends(get_current_user),
    _: None = Depends(settings_rate_limit),
) -> ProviderModelsOut:
    """本地服务商实际已下载的模型；云端服务商返回不可探测。"""
    reachable, installed, message = model_provider.list_installed_models(provider_key)
    return ProviderModelsOut(
        provider_key=provider_key,
        reachable=reachable,
        installed=installed,
        message=message,
    )


@router.post("/model-providers/{config_id}/test", response_model=ConnectionTestResult)
def test_model_provider(
    config_id: uuid.UUID,
    payload: ConnectionTestRequest | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _: None = Depends(settings_rate_limit),
) -> ConnectionTestResult:
    role = payload.role if payload else None
    return model_provider.test_connection(db, user, config_id, role)


@router.delete("/model-providers/{config_id}", status_code=204)
def delete_model_provider(
    config_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _: None = Depends(settings_rate_limit),
) -> Response:
    model_provider.delete_config(db, user, config_id)
    return Response(status_code=204)
