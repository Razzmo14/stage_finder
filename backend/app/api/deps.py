"""Shared FastAPI dependencies."""

from typing import Annotated

from fastapi import Depends, Request
from sqlmodel import Session

from app.db.engine import get_db
from app.llm.catalog import ModelCatalog
from app.llm.provider import LLMProvider

DbDep = Annotated[Session, Depends(get_db)]


def get_catalog(request: Request) -> ModelCatalog:
    return request.app.state.catalog


def get_provider(request: Request) -> LLMProvider:
    return request.app.state.llm_provider()


CatalogDep = Annotated[ModelCatalog, Depends(get_catalog)]
ProviderDep = Annotated[LLMProvider, Depends(get_provider)]


def get_task_model(request: Request):
    def _task_model(task: str) -> str:
        return request.app.state.get_task_model(task)

    return _task_model


TaskModelDep = Annotated[object, Depends(get_task_model)]
