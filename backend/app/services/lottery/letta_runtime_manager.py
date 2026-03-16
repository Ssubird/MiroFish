"""Project-local Letta runtime bootstrap for the lottery world."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
from threading import Lock

import requests

from ...config import PROJECT_ROOT, PROJECT_ROOT_ENV, reload_project_env
from .letta_runtime_support import (
    LOCAL_DB_NAME,
    LOCAL_PG_PORT,
    LOCAL_PG_USER,
    HTTP_TIMEOUT_SECONDS,
    RuntimePaths,
    clear_stale_pid,
    creation_flags,
    is_local_base_url,
    run_command,
    runtime_paths,
    server_port,
    server_ready,
    tcp_open,
    wait_for_http,
    wait_for_tcp,
)


STARTUP_LOCK = Lock()


def ensure_local_letta_runtime(base_url: str) -> None:
    reload_project_env()
    if not _is_local_base_url(base_url):
        return
    with STARTUP_LOCK:
        if _server_ready(base_url):
            _ensure_providers(base_url)
            return
        paths = runtime_paths()
        _ensure_postgres(paths)
        _ensure_database(paths)
        _ensure_letta_server(paths, base_url)
        _ensure_providers(base_url)


def _is_local_base_url(base_url: str) -> bool:
    return is_local_base_url(base_url)


def _server_ready(base_url: str) -> bool:
    return server_ready(base_url)


def _server_port(base_url: str) -> int:
    return server_port(base_url)


def _ensure_postgres(paths: RuntimePaths) -> None:
    if tcp_open("127.0.0.1", LOCAL_PG_PORT):
        return
    if not (paths.pg_data / "PG_VERSION").exists():
        _init_postgres(paths)
    clear_stale_pid(paths.pg_data / "postmaster.pid")
    run_command(
        [
            str(paths.pg_bin / "pg_ctl.exe"),
            "start",
            "-D",
            str(paths.pg_data),
            "-l",
            str(paths.pg_log),
            "-o",
            f"-p {LOCAL_PG_PORT}",
        ]
    )
    wait_for_tcp("127.0.0.1", LOCAL_PG_PORT, "project-local PostgreSQL")


def _init_postgres(paths: RuntimePaths) -> None:
    paths.root.mkdir(parents=True, exist_ok=True)
    run_command(
        [
            str(paths.pg_bin / "initdb.exe"),
            "-D",
            str(paths.pg_data),
            "-U",
            LOCAL_PG_USER,
            "-A",
            "trust",
            "--encoding=UTF8",
            "--no-locale",
        ]
    )


def _ensure_database(paths: RuntimePaths) -> None:
    if not _database_exists(paths):
        run_command(
            [
                str(paths.pg_bin / "createdb.exe"),
                "-h",
                "127.0.0.1",
                "-p",
                str(LOCAL_PG_PORT),
                "-U",
                LOCAL_PG_USER,
                LOCAL_DB_NAME,
            ]
        )
    _run_psql(paths, "CREATE EXTENSION IF NOT EXISTS vector;")
    env = _runtime_env(paths)
    run_command(
        [
            str(paths.alembic_cli),
            "-c",
            str(paths.alembic_ini),
            "upgrade",
            "head",
        ],
        env=env,
        cwd=str(paths.alembic_ini.parent),
        timeout=120,
    )


def _database_exists(paths: RuntimePaths) -> bool:
    output = run_command(
        [
            str(paths.pg_bin / "psql.exe"),
            "-h",
            "127.0.0.1",
            "-p",
            str(LOCAL_PG_PORT),
            "-U",
            LOCAL_PG_USER,
            "-d",
            "postgres",
            "-Atc",
            f"SELECT 1 FROM pg_database WHERE datname = '{LOCAL_DB_NAME}';",
        ]
    )
    return output.strip() == "1"


def _run_psql(paths: RuntimePaths, sql: str) -> None:
    run_command(
        [
            str(paths.pg_bin / "psql.exe"),
            "-h",
            "127.0.0.1",
            "-p",
            str(LOCAL_PG_PORT),
            "-U",
            LOCAL_PG_USER,
            "-d",
            LOCAL_DB_NAME,
            "-c",
            sql,
        ]
    )


def _ensure_letta_server(paths: RuntimePaths, base_url: str) -> None:
    if _server_ready(base_url):
        return
    paths.root.mkdir(parents=True, exist_ok=True)
    log_handle = open(paths.letta_log, "a", encoding="utf-8")
    subprocess.Popen(
        [
            str(paths.letta_cli),
            "server",
            "--host",
            "127.0.0.1",
            "--port",
            str(_server_port(base_url)),
        ],
        cwd=str(Path(PROJECT_ROOT).resolve() / "backend"),
        env=_runtime_env(paths),
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        creationflags=creation_flags(),
        start_new_session=True,
    )
    log_handle.close()
    wait_for_http(base_url, "project-local Letta server", paths.letta_log)


def _runtime_env(paths: RuntimePaths) -> dict[str, str]:
    env = os.environ.copy()
    env["LETTA_DIR"] = str(paths.root)
    env["LETTA_PG_URI"] = _project_pg_uri()
    env.pop("OPENAI_API_KEY", None)
    env.pop("OPENAI_BASE_URL", None)
    env.pop("OPENAI_API_BASE", None)
    return env


def _project_pg_uri() -> str:
    return f"postgresql+pg8000://{LOCAL_PG_USER}@127.0.0.1:{LOCAL_PG_PORT}/{LOCAL_DB_NAME}"


def _ensure_providers(base_url: str) -> None:
    _ensure_openai_provider(base_url, "openai-proxy", os.environ.get("LLM_API_KEY"), os.environ.get("LLM_BASE_URL"))
    _ensure_openai_provider(base_url, "openai", os.environ.get("LETTA_API_KEY"), os.environ.get("LLM_BASE_URL"))


def _ensure_openai_provider(base_url: str, name: str, api_key: str | None, provider_url: str | None) -> None:
    if not api_key:
        raise RuntimeError(f"{name} bootstrap requires API key in {PROJECT_ROOT_ENV}")
    if not provider_url:
        raise RuntimeError(f"{name} bootstrap requires provider base URL in {PROJECT_ROOT_ENV}")
    providers = _request_json("GET", f"{base_url}/providers/")
    existing = next((item for item in providers if item.get("name") == name), None)
    if existing:
        _request_json(
            "PATCH",
            f"{base_url}/providers/{existing['id']}",
            {"api_key": api_key, "base_url": provider_url},
        )
        _request_json("PATCH", f"{base_url}/providers/{existing['id']}/refresh")
        return
    _request_json(
        "POST",
        f"{base_url}/providers/",
        {
            "name": name,
            "provider_type": "openai",
            "api_key": api_key,
            "base_url": provider_url,
        },
    )


def _request_json(method: str, url: str, payload: dict[str, str] | None = None) -> list[dict] | dict:
    response = requests.request(
        method=method,
        url=url,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        json=payload,
        timeout=60,
    )
    if not response.ok:
        raise RuntimeError(f"Letta runtime request failed: HTTP {response.status_code} {response.text}")
    return response.json()
