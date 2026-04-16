"""
File utility functions for file handling and validation.
"""

import os
import mimetypes
from django.core.exceptions import ValidationError
from django.conf import settings


class FileUtils:
    """Utility class for file operations."""

    # Allowed file types
    ALLOWED_DOCUMENT_TYPES = [
        'application/pdf',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',  # .docx
        'application/msword',  # .doc
        'text/plain',
    ]

    ALLOWED_IMAGE_TYPES = [
        'image/jpeg',
        'image/png',
        'image/gif',
        'image/webp',
    ]

    MAX_FILE_SIZE_MB = 10  # Maximum file size in MB

    @staticmethod
    def validate_file_type(file, allowed_types):
        """
        Validate file MIME type.

        Args:
            file: Uploaded file object
            allowed_types: List of allowed MIME types

        Raises:
            ValidationError: If file type is not allowed
        """
        file_mime = mimetypes.guess_type(file.name)[0]

        if file_mime not in allowed_types:
            allowed_extensions = [mimetypes.guess_extension(t) for t in allowed_types]
            raise ValidationError(
                f"File type not allowed. Allowed types: {', '.join(allowed_extensions)}"
            )

    @staticmethod
    def validate_file_size(file, max_size_mb=None):
        """
        Validate file size.

        Args:
            file: Uploaded file object
            max_size_mb: Maximum file size in MB (default: from class)

        Raises:
            ValidationError: If file is too large
        """
        max_size = (max_size_mb or FileUtils.MAX_FILE_SIZE_MB) * 1024 * 1024  # Convert to bytes

        if file.size > max_size:
            raise ValidationError(
                f"File size exceeds maximum allowed size of {max_size_mb or FileUtils.MAX_FILE_SIZE_MB}MB"
            )

    @staticmethod
    def validate_document(file):
        """
        Validate document file (PDF, DOCX, etc.).

        Args:
            file: Uploaded file object

        Raises:
            ValidationError: If validation fails
        """
        FileUtils.validate_file_type(file, FileUtils.ALLOWED_DOCUMENT_TYPES)
        FileUtils.validate_file_size(file)

    @staticmethod
    def validate_image(file):
        """
        Validate image file.

        Args:
            file: Uploaded file object

        Raises:
            ValidationError: If validation fails
        """
        FileUtils.validate_file_type(file, FileUtils.ALLOWED_IMAGE_TYPES)
        FileUtils.validate_file_size(file, max_size_mb=5)  # Images limited to 5MB

    @staticmethod
    def get_file_extension(filename):
        """
        Get file extension from filename.

        Args:
            filename: File name

        Returns:
            str: File extension (without dot)
        """
        return os.path.splitext(filename)[1][1:].lower()

    @staticmethod
    def generate_unique_filename(filename):
        """
        Generate unique filename to prevent collisions.

        Args:
            filename: Original filename

        Returns:
            str: Unique filename
        """
        import uuid
        from datetime import datetime

        name, ext = os.path.splitext(filename)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        unique_id = str(uuid.uuid4())[:8]

        return f"{name}_{timestamp}_{unique_id}{ext}"
