"""
supabase_helper.py

Reusable Supabase helper for Big Bang special event packages.

Purpose
-------
This file is designed to be copied into every future special event package.

It provides a small, understandable wrapper around Supabase's REST/RPC API
without requiring the full supabase-py client library.

Why use raw REST?
-----------------
Using raw HTTPS requests keeps the special event package lightweight and
stable on Orange Pi devices.

The helper supports:

- calling Supabase RPC functions,
- validating event codes,
- requesting package download information,
- requesting AI credentials for an event,
- building public Supabase Storage URLs,
- downloading files from Supabase Storage or signed URLs.

Security rules
--------------
Never log or print private API keys.

This helper uses a Supabase publishable/anon key, not a service-role key.
Your Supabase database policies and RPC functions must enforce real security.

Expected RPC style
------------------
This template assumes your Supabase functions accept JSON arguments similar to:

    {
      "p_device_mac": "aa:bb:cc:dd:ee:ff",
      "p_event_code": "DEMO1"
    }

Example functions:
    validate_event_code
    get_special_event_package
    get_event_ai_credentials
    register_event_launch

The helper is flexible about returned field names, but the recommended
package response is:

    {
      "ok": true,
      "event_code": "DEMO1",
      "event_name": "Hello World Demo Template",
      "event_version": "1.0.0",
      "download_url": "https://...",
      "storage_bucket": "event-packages",
      "storage_path": "DEMO1/1.0.0/package.zip"
    }

For private buckets, return a temporary signed download_url from Supabase.
"""

from __future__ import annotations

import json
import mimetypes
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import quote

import requests


# ------------------------------------------------------------
# Exceptions
# ------------------------------------------------------------

class SupabaseHelperError(Exception):
    """
    Base exception for this helper.
    """


class SupabaseRpcError(SupabaseHelperError):
    """
    Raised when a Supabase RPC call fails.
    """

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        response_body: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class SupabaseDownloadError(SupabaseHelperError):
    """
    Raised when a download fails.
    """


# ------------------------------------------------------------
# Data objects
# ------------------------------------------------------------

@dataclass(frozen=True)
class SupabaseConnectionInfo:
    """
    Minimal Supabase connection settings.
    """

    supabase_url: str
    supabase_key: str

    def rest_url(self) -> str:
        """
        Return the base REST API URL.
        """
        return self.supabase_url.rstrip("/") + "/rest/v1"

    def storage_url(self) -> str:
        """
        Return the base Storage API URL.
        """
        return self.supabase_url.rstrip("/") + "/storage/v1"

    def masked_key(self) -> str:
        """
        Return a safe-to-print version of the key.
        """
        key = self.supabase_key

        if len(key) <= 12:
            return "*" * len(key)

        return f"{key[:6]}********{key[-4:]}"


# ------------------------------------------------------------
# Response helpers
# ------------------------------------------------------------

def _safe_json_loads(text: str) -> Any:
    """
    Parse JSON safely. If parsing fails, return the original text.
    """
    try:
        return json.loads(text)
    except Exception:
        return text


def normalize_rpc_response(data: Any) -> Any:
    """
    Normalize common Supabase/PostgREST RPC response shapes.

    Some functions return:
        { ... }

    Some table-returning functions return:
        [ { ... } ]

    This helper unwraps a single-item list for convenience.
    """
    if isinstance(data, list) and len(data) == 1:
        return data[0]

    return data


def response_indicates_success(data: Any) -> bool:
    """
    Guess whether an RPC response indicates success.

    Supports common styles:
        {"ok": true}
        {"success": true}
        {"valid": true}
        {"allowed": true}

    If no status field exists, we assume the HTTP success was enough.
    """
    data = normalize_rpc_response(data)

    if not isinstance(data, dict):
        return True

    for key in ("ok", "success", "valid", "allowed"):
        if key in data:
            return bool(data[key])

    return True


def get_response_message(data: Any, default: str = "") -> str:
    """
    Extract a human-readable message from an RPC response.
    """
    data = normalize_rpc_response(data)

    if not isinstance(data, dict):
        return default

    for key in ("message", "error", "reason", "details"):
        value = data.get(key)

        if value:
            return str(value)

    return default


# ------------------------------------------------------------
# Main client
# ------------------------------------------------------------

class BigBangSupabaseClient:
    """
    Small Supabase REST/RPC client for special event packages.
    """

    def __init__(
        self,
        supabase_url: str,
        supabase_key: str,
        timeout_seconds: int = 30,
    ) -> None:
        if not supabase_url:
            raise ValueError("supabase_url is required.")

        if not supabase_key:
            raise ValueError("supabase_key is required.")

        self.info = SupabaseConnectionInfo(
            supabase_url=supabase_url.rstrip("/"),
            supabase_key=supabase_key,
        )
        self.timeout_seconds = timeout_seconds

    def _headers(self) -> Dict[str, str]:
        """
        Headers required for Supabase REST calls.

        We intentionally do not print these headers anywhere because they
        contain the Supabase key.
        """
        return {
            "apikey": self.info.supabase_key,
            "Authorization": f"Bearer {self.info.supabase_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def rpc(self, function_name: str, payload: Optional[Dict[str, Any]] = None) -> Any:
        """
        Call a Supabase RPC function.

        Args:
            function_name:
                Name of the Postgres function exposed through Supabase RPC.

            payload:
                JSON object containing function arguments.

        Returns:
            Parsed JSON response, normalized so a single-item list becomes a dict.

        Raises:
            SupabaseRpcError if the HTTP call fails or the response indicates failure.
        """
        if not function_name:
            raise ValueError("function_name is required.")

        if payload is None:
            payload = {}

        url = f"{self.info.rest_url()}/rpc/{function_name}"

        try:
            response = requests.post(
                url,
                headers=self._headers(),
                json=payload,
                timeout=self.timeout_seconds,
            )
        except requests.RequestException as exc:
            raise SupabaseRpcError(
                f"Network error while calling Supabase RPC '{function_name}': {exc}"
            ) from exc

        text = response.text or ""

        if response.status_code < 200 or response.status_code >= 300:
            parsed_error = _safe_json_loads(text)
            raise SupabaseRpcError(
                message=(
                    f"Supabase RPC '{function_name}' failed with "
                    f"HTTP {response.status_code}: {parsed_error}"
                ),
                status_code=response.status_code,
                response_body=text,
            )

        if not text.strip():
            return None

        data = _safe_json_loads(text)
        data = normalize_rpc_response(data)

        if not response_indicates_success(data):
            message = get_response_message(
                data,
                default=f"Supabase RPC '{function_name}' returned a failure response.",
            )

            raise SupabaseRpcError(
                message=message,
                status_code=response.status_code,
                response_body=text,
            )

        return data

    def validate_event_code(
        self,
        rpc_name: str,
        device_mac: str,
        event_code: str,
    ) -> Any:
        """
        Validate that this device can use a special event code.
        """
        payload = {
            "p_device_mac": device_mac,
            "p_event_code": event_code,
        }

        return self.rpc(rpc_name, payload)

    def get_special_event_package(
        self,
        rpc_name: str,
        device_mac: str,
        event_code: str,
    ) -> Any:
        """
        Request package download information for a special event.

        Your Supabase RPC should return either:
            - download_url / package_url / signed_url
        or:
            - storage_bucket and storage_path
        """
        payload = {
            "p_device_mac": device_mac,
            "p_event_code": event_code,
        }

        return self.rpc(rpc_name, payload)

    def get_event_ai_credentials(
        self,
        rpc_name: str,
        device_mac: str,
        event_code: str,
    ) -> Any:
        """
        Request AI credentials for an event.

        Important:
            Future AI-enabled events should use this at runtime and keep the
            returned credential in memory only.

            Do not write returned AI credentials to:
                - event.json
                - .env
                - config.py
                - logs
                - local database files
        """
        payload = {
            "p_device_mac": device_mac,
            "p_event_code": event_code,
        }

        return self.rpc(rpc_name, payload)

    def register_event_launch(
        self,
        rpc_name: str,
        device_mac: str,
        event_code: str,
        event_version: str,
    ) -> Any:
        """
        Optional: notify Supabase that an event was launched.

        If your database does not have this function yet, leave
        BIGBANG_VALIDATE_ON_LAUNCH=0 or do not call this.
        """
        payload = {
            "p_device_mac": device_mac,
            "p_event_code": event_code,
            "p_event_version": event_version,
        }

        return self.rpc(rpc_name, payload)


# ------------------------------------------------------------
# Storage/download helpers
# ------------------------------------------------------------

def build_public_storage_url(
    supabase_url: str,
    bucket: str,
    object_path: str,
) -> str:
    """
    Build a public Supabase Storage object URL.

    This works only if:
        - the bucket/object is public, or
        - your Storage policies allow public access.

    For private buckets, your Supabase backend/RPC should return a signed URL.
    """
    clean_base = supabase_url.rstrip("/")
    clean_bucket = quote(bucket.strip("/"), safe="")
    clean_path = quote(object_path.strip("/"), safe="/")

    return f"{clean_base}/storage/v1/object/public/{clean_bucket}/{clean_path}"


def find_download_url_from_package_info(
    package_info: Any,
    supabase_url: Optional[str] = None,
) -> str:
    """
    Extract a usable download URL from a Supabase package response.

    Supported direct URL fields:
        - download_url
        - package_url
        - signed_url
        - signedURL
        - url

    Supported storage fields:
        - storage_bucket / storage_path
        - bucket / path
        - bucket_name / object_path

    If only bucket/path is returned, this function creates a public URL.
    For private buckets, return a signed URL from Supabase instead.
    """
    package_info = normalize_rpc_response(package_info)

    if not isinstance(package_info, dict):
        raise SupabaseDownloadError(
            f"Package info must be a JSON object/dict. Got: {type(package_info).__name__}"
        )

    for key in ("download_url", "package_url", "signed_url", "signedURL", "url"):
        value = package_info.get(key)

        if value:
            return str(value)

    bucket = (
        package_info.get("storage_bucket")
        or package_info.get("bucket")
        or package_info.get("bucket_name")
    )

    object_path = (
        package_info.get("storage_path")
        or package_info.get("path")
        or package_info.get("object_path")
        or package_info.get("package_path")
    )

    if bucket and object_path and supabase_url:
        return build_public_storage_url(
            supabase_url=supabase_url,
            bucket=str(bucket),
            object_path=str(object_path),
        )

    raise SupabaseDownloadError(
        "Could not find a download URL in package info. "
        "Expected download_url/package_url/signed_url, or bucket/path fields."
    )


def guess_content_type(path: Path) -> str:
    """
    Guess content type for a file path.
    """
    content_type, _ = mimetypes.guess_type(str(path))

    return content_type or "application/octet-stream"


def download_file(
    url: str,
    destination: Path,
    headers: Optional[Dict[str, str]] = None,
    timeout_seconds: int = 120,
    show_progress: bool = True,
) -> Path:
    """
    Download a URL to a local file.

    This works with:
        - public Supabase Storage URLs,
        - signed Supabase Storage URLs,
        - any normal HTTPS download URL.
    """
    if headers is None:
        headers = {}

    destination = destination.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)

    temp_destination = destination.with_suffix(destination.suffix + ".download")

    if temp_destination.exists():
        temp_destination.unlink()

    started = time.time()
    downloaded = 0

    try:
        with requests.get(
            url,
            headers=headers,
            stream=True,
            timeout=timeout_seconds,
        ) as response:
            if response.status_code < 200 or response.status_code >= 300:
                raise SupabaseDownloadError(
                    f"Download failed with HTTP {response.status_code}: {response.text[:500]}"
                )

            total_raw = response.headers.get("content-length")
            total = int(total_raw) if total_raw and total_raw.isdigit() else None

            with temp_destination.open("wb") as file_handle:
                for chunk in response.iter_content(chunk_size=1024 * 256):
                    if not chunk:
                        continue

                    file_handle.write(chunk)
                    downloaded += len(chunk)

                    if show_progress and total:
                        percent = int((downloaded / total) * 100)
                        print(f"\rDownloading... {percent:3d}% ", end="", flush=True)

        if show_progress:
            print()

        temp_destination.replace(destination)

    except requests.RequestException as exc:
        raise SupabaseDownloadError(f"Network error during download: {exc}") from exc
    except Exception:
        if temp_destination.exists():
            try:
                temp_destination.unlink()
            except Exception:
                pass

        raise

    elapsed = max(time.time() - started, 0.001)

    if show_progress:
        mb = downloaded / (1024 * 1024)
        speed = mb / elapsed
        print(f"Downloaded {mb:.2f} MB in {elapsed:.1f}s ({speed:.2f} MB/s)")
        print(f"Saved to: {destination}")

    return destination


def load_supabase_client_from_environment() -> BigBangSupabaseClient:
    """
    Convenience helper for standalone scripts.

    Reads:
        SUPABASE_URL
        SUPABASE_PUBLISHABLE_KEY
        SUPABASE_ANON_KEY
        SUPABASE_KEY
    """
    supabase_url = os.environ.get("SUPABASE_URL", "").strip()
    supabase_key = (
        os.environ.get("SUPABASE_PUBLISHABLE_KEY", "").strip()
        or os.environ.get("SUPABASE_ANON_KEY", "").strip()
        or os.environ.get("SUPABASE_KEY", "").strip()
    )

    if not supabase_url:
        raise SupabaseHelperError("SUPABASE_URL is missing.")

    if not supabase_key:
        raise SupabaseHelperError(
            "SUPABASE_PUBLISHABLE_KEY, SUPABASE_ANON_KEY, or SUPABASE_KEY is missing."
        )

    return BigBangSupabaseClient(
        supabase_url=supabase_url,
        supabase_key=supabase_key,
    )