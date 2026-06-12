# Author: Krish Vishwakarma
# Date: 28th Jan 2026
# API Logger Utility for Echotels APIs

import frappe
import json
import time
from contextlib import contextmanager
from typing import Any, Dict, Optional


class APILogger:
    """
    Centralized API logger for all Echotels APIs.
    Logs requests, responses, and errors to the API Log DocType.
    """

    # Sensitive fields to mask in logs
    SENSITIVE_FIELDS = {
        "password", "token", "api_key", "secret", "authorization",
        "credit_card", "cvv", "pin", "ssn", "account_number"
    }

    # Maximum payload size (in characters) before truncation
    MAX_PAYLOAD_SIZE = 50000

    def __init__(self, api_name: str, endpoint: str):
        """
        Initialize the API logger.

        Args:
            api_name: Name of the API (Checkin, Checkout, Payment, Reservation)
            endpoint: Function name of the endpoint
        """
        self.api_name = api_name
        self.endpoint = endpoint
        self.start_time = None
        self._request_payload = None
        self._folio_no = None
        self._booking_id = None

    def _mask_sensitive_fields(self, data: Any) -> Any:
        """
        Recursively mask sensitive fields in data structure.

        Args:
            data: Data structure (dict, list, or primitive)

        Returns:
            Sanitized data structure with sensitive fields masked
        """
        if isinstance(data, dict):
            return {
                k: self._mask_sensitive_fields(v) if k.lower() not in self.SENSITIVE_FIELDS else "***MASKED***"
                for k, v in data.items()
            }
        elif isinstance(data, list):
            return [self._mask_sensitive_fields(item) for item in data]
        return data

    def _sanitize_payload(self, payload: Any) -> str:
        """
        Sanitize payload and return as JSON string (as-is, no formatting changes).

        Args:
            payload: Raw payload data

        Returns:
            Sanitized JSON string as-is (compact, no extra formatting)
        """
        if not payload:
            return "{}"

        try:
            # If already a dict, sanitize and convert to JSON
            if isinstance(payload, dict):
                sanitized = self._mask_sensitive_fields(payload)
                json_str = json.dumps(sanitized, default=str, ensure_ascii=False)

            # If string, try to parse as JSON first
            elif isinstance(payload, str):
                try:
                    payload_dict = json.loads(payload)
                    sanitized = self._mask_sensitive_fields(payload_dict)
                    json_str = json.dumps(sanitized, default=str, ensure_ascii=False)
                except json.JSONDecodeError:
                    # Not valid JSON, keep as-is
                    json_str = payload

            # For other types (like frappe.form_dict which is ImmutableMultiDict)
            else:
                payload_dict = dict(payload)
                sanitized = self._mask_sensitive_fields(payload_dict)
                json_str = json.dumps(sanitized, default=str, ensure_ascii=False)

            # Truncate if too large
            if len(json_str) > self.MAX_PAYLOAD_SIZE:
                json_str = json_str[:self.MAX_PAYLOAD_SIZE] + "... [TRUNCATED]"

            return json_str

        except Exception as e:
            frappe.log_error(f"Failed to sanitize payload: {str(e)}", "API Logger Sanitization")
            return str(payload)[:self.MAX_PAYLOAD_SIZE]

    def _create_log_entry(
        self,
        request_payload: str,
        response_data: Optional[str] = None,
        status_code: Optional[int] = None,
        success: bool = True,
        error_message: Optional[str] = None,
        folio_no: Optional[str] = None,
        booking_id: Optional[str] = None
    ) -> None:
        """
        Create a log entry in the API Log DocType.

        Args:
            request_payload: Sanitized request payload
            response_data: Response data (for success cases)
            status_code: HTTP status code
            success: Whether the API call was successful
            error_message: Error message (for failure cases)
            folio_no: Folio number for reference
            booking_id: Booking ID for reference
        """
        try:
            execution_time = None
            if self.start_time:
                execution_time = round(time.time() - self.start_time, 4)

            log_doc = frappe.get_doc({
                "doctype": "API Log",
                "api_name": self.api_name,
                "endpoint": self.endpoint,
                "request_payload": request_payload,
                "response_data": response_data,
                "status_code": status_code,
                "execution_time": execution_time,
                "success": 1 if success else 0,
                "error_message": error_message,
                "folio_no": folio_no,
                "booking_id": booking_id,
                "timestamp": frappe.utils.now()
            })

            # Insert with ignore_permissions to allow logging from guest APIs
            log_doc.insert(ignore_permissions=True)

        except Exception as e:
            # Don't fail the API if logging fails
            frappe.log_error(
                f"Failed to create API log entry: {str(e)}",
                f"API Logger :: {self.api_name} :: Logging Error"
            )

    def log_request(
        self,
        payload: Any,
        folio_no: Optional[str] = None,
        booking_id: Optional[str] = None
    ) -> None:
        """
        Log the incoming API request and start timing.

        Args:
            payload: Request payload (frappe.request.data or frappe.form_dict)
            folio_no: Folio number for reference
            booking_id: Booking ID for reference
        """
        self.start_time = time.time()
        self._folio_no = folio_no
        self._booking_id = booking_id
        self._request_payload = self._sanitize_payload(payload)

    def log_success(
        self,
        response_data: Dict[str, Any],
        status_code: int = 200
    ) -> None:
        """
        Log a successful API response.

        Args:
            response_data: Response data dictionary
            status_code: HTTP status code
        """
        try:
            # Convert response dict to JSON string (as-is, no formatting)
            response_json = json.dumps(response_data, default=str, ensure_ascii=False)

            # Truncate if needed
            if len(response_json) > self.MAX_PAYLOAD_SIZE:
                response_json = response_json[:self.MAX_PAYLOAD_SIZE] + "... [TRUNCATED]"

            self._create_log_entry(
                request_payload=self._request_payload,
                response_data=response_json,
                status_code=status_code,
                success=True,
                folio_no=self._folio_no,
                booking_id=self._booking_id
            )
        except Exception as e:
            frappe.log_error(f"Failed to log success: {str(e)}", "API Logger Success Log")

    def log_error(
        self,
        error: Exception,
        status_code: int = 500,
        response_data: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Log an API error.

        Args:
            error: Exception object
            status_code: HTTP status code
            response_data: Optional response data dictionary to log
        """
        try:
            error_message = f"{type(error).__name__}: {str(error)}"

            # Convert response data to JSON if provided
            response_json = None
            if response_data:
                response_json = json.dumps(response_data, default=str, ensure_ascii=False)
                if len(response_json) > self.MAX_PAYLOAD_SIZE:
                    response_json = response_json[:self.MAX_PAYLOAD_SIZE] + "... [TRUNCATED]"

            self._create_log_entry(
                request_payload=self._request_payload,
                response_data=response_json,
                status_code=status_code,
                success=False,
                error_message=error_message,
                folio_no=self._folio_no,
                booking_id=self._booking_id
            )
        except Exception as e:
            frappe.log_error(f"Failed to log error: {str(e)}", "API Logger Error Log")


@contextmanager
def api_logger_context(api_name: str, endpoint: str):
    """
    Context manager for automatic API logging.

    Usage:
        with api_logger_context("Checkin", "create_sales_invoice"):
            # API logic here
            result = process_request()

    Args:
        api_name: Name of the API
        endpoint: Function name of the endpoint

    Yields:
        APILogger instance
    """
    logger = APILogger(api_name, endpoint)
    try:
        yield logger
    except Exception:
        raise

