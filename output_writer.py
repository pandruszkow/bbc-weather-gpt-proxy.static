"""Output writer for atomic file operations.

Handles persisting content to disk with atomic rename semantics
to prevent partial writes in case of failures.
"""

import logging
import os
import tempfile
from pathlib import Path
from typing import Union

logger = logging.getLogger(__name__)


def write_file_atomic(filepath: Union[str, Path], content: str) -> Path:
    """Write content to a file atomically using rename.
    
    Writes to a temporary file in the same directory, then renames
    to the target filename. This ensures readers never see partially
    written files.
    
    Args:
        filepath: Final destination path for the file
        content: String content to write
        
    Returns:
        The final filepath
        
    Raises:
        IOError: If write or rename fails
    """
    filepath = Path(filepath)
    
    # Ensure parent directory exists
    filepath.parent.mkdir(parents=True, exist_ok=True)
    
    # Create temp file in same directory for atomic rename
    fd, temp_path = tempfile.mkstemp(
        dir=filepath.parent,
        prefix=f".{filepath.name}.tmp."
    )
    
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(content)
        
        # Atomic rename
        os.rename(temp_path, filepath)
        logger.debug(f"Wrote {len(content)} chars to {filepath}")
        return filepath
        
    except Exception:
        # Clean up temp file on failure
        try:
            os.unlink(temp_path)
        except FileNotFoundError:
            pass
        raise


def ensure_directory(path: Union[str, Path]) -> Path:
    """Ensure a directory exists, creating if necessary.
    
    Args:
        path: Directory path to ensure
        
    Returns:
        The directory path
    """
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path
