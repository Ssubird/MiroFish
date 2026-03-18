"""
MiroFish backend entrypoint.
"""

import os
import sys


if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.config import Config


def _env_flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _validate_config() -> None:
    errors = Config.validate()
    if not errors:
        return
    print("Configuration errors:")
    for err in errors:
        print(f"  - {err}")
    print("\nPlease check the .env configuration.")
    sys.exit(1)


def main() -> None:
    _validate_config()
    app = create_app()
    host = os.environ.get("FLASK_HOST", "0.0.0.0")
    port = int(os.environ.get("FLASK_PORT", "5001"))
    debug = Config.DEBUG
    use_reloader = _env_flag("FLASK_USE_RELOADER", False)
    app.run(
        host=host,
        port=port,
        debug=debug,
        threaded=True,
        use_reloader=use_reloader,
    )


if __name__ == "__main__":
    main()
