import os
import logging
from pydantic import BaseModel
from typing import Optional, List, Any


class ToolResponse(BaseModel):
    success: bool
    message: Optional[str] = None
    content: Optional[Any] = None
    output_path: Optional[str|List[str]] = None
    
    class Config:
        extra = "allow"


def setup_logger(name: str, log_dir: str, log_file: str) -> logging.Logger:
    os.makedirs(log_dir, exist_ok=True)
    log_file_path = os.path.join(log_dir, log_file)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_file_path),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(name)

def redact_secrets(value: Any) -> Any:
    """Return a copy of nested config data with secret-like values masked."""
    secret_markers = ("key", "token", "secret", "password", "access_code")
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            normalized_key = str(key).lower()
            is_secret = (
                any(marker in normalized_key for marker in secret_markers)
                or normalized_key == "api"
                or normalized_key.endswith("_api")
            )
            if is_secret:
                redacted[key] = "***REDACTED***" if item else item
            else:
                redacted[key] = redact_secrets(item)
        return redacted
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    return value

