"""
Unit tests for api/download.py — _generate_presigned_url.

Integration tests always run with dev_mode=True, so the S3 presigned-URL
branch is never exercised there. These unit tests cover the prod path.
"""

import sys
from unittest.mock import MagicMock, patch

from api.download import _generate_presigned_url


class TestGeneratePresignedUrl:
    """_generate_presigned_url: boto3 presigned URL generation for mesh downloads."""

    def _call(self, s3_key: str, mock_s3=None, expires: int = 3600):
        if mock_s3 is None:
            mock_s3 = MagicMock()
            mock_s3.generate_presigned_url.return_value = "https://s3.example.com/signed-url"

        mock_boto3 = MagicMock()
        mock_boto3.client.return_value = mock_s3

        mock_settings = MagicMock()
        mock_settings.s3_region = "us-east-1"
        mock_settings.aws_access_key_id = "key"
        mock_settings.aws_secret_access_key = "secret"
        mock_settings.s3_bucket = "test-bucket"

        with patch("api.download.settings", mock_settings), \
             patch.dict(sys.modules, {"boto3": mock_boto3}):
            url = _generate_presigned_url(s3_key, expires)

        return url, mock_s3

    def test_returns_presigned_url_string(self):
        """Must return the URL string provided by boto3."""
        url, _ = self._call("meshes/job-1/mesh.zip")
        assert url == "https://s3.example.com/signed-url"

    def test_generate_presigned_url_called_with_correct_params(self):
        """boto3 generate_presigned_url must receive 'get_object', correct Params, and ExpiresIn."""
        _, mock_s3 = self._call("meshes/job-1/mesh.zip")

        mock_s3.generate_presigned_url.assert_called_once_with(
            "get_object",
            Params={"Bucket": "test-bucket", "Key": "meshes/job-1/mesh.zip"},
            ExpiresIn=3600,
        )

    def test_custom_expiry_forwarded_to_boto3(self):
        """Non-default expires value must be forwarded to boto3 as ExpiresIn."""
        _, mock_s3 = self._call("meshes/job-2/mesh.zip", expires=7200)
        call_kwargs = mock_s3.generate_presigned_url.call_args[1]
        assert call_kwargs["ExpiresIn"] == 7200
