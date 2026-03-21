import io
import logging

from app import create_app
from app.utils import logger as logger_module


class BrokenReconfigureStream(io.StringIO):
    def reconfigure(self, **kwargs):
        raise OSError(22, "Invalid argument")


def _reset_logger(name: str) -> None:
    logger = logging.getLogger(name)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()


def test_health_request_survives_invalid_stream_reconfigure(monkeypatch):
    _reset_logger("mirofish.request")
    broken_stdout = BrokenReconfigureStream()
    broken_stderr = BrokenReconfigureStream()

    monkeypatch.setattr(logger_module, "_UTF8_RECONFIGURE_ATTEMPTED", False)
    monkeypatch.setattr(logger_module.sys, "stdout", broken_stdout)
    monkeypatch.setattr(logger_module.sys, "stderr", broken_stderr)

    app = create_app()
    client = app.test_client()
    response = client.get("/health")

    assert response.status_code == 200
    assert response.get_json()["status"] == "ok"
