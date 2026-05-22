from __future__ import annotations

import json
import re
import socket
import urllib.error
import urllib.request
from pathlib import PurePath
from uuid import UUID

from app.core.config import Settings
from app.core.schemas import (
    ConfidenceBand,
    OCRConfidenceSummary,
    OCRExtractedField,
    OCRExtractedLineItem,
    OCRExtractionResult,
    OCRProviderMetadata,
    OCRProviderName,
)


REQUIRED_FIELDS = ["invoice_number", "supplier_name", "invoice_date", "currency", "grand_total"]
DATE_VALUE = (
    r"("
    r"\d{4}-\d{1,2}-\d{1,2}"
    r"|\d{1,2}[\/.-]\d{1,2}[\/.-]\d{2,4}"
    r"|[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4}"
    r")"
)
MONEY_VALUE = r"(-?[\d,]+(?:\.\d{2})?)"
OCR_SPACE_FILETYPES = {
    "application/pdf": ("PDF", ".pdf"),
    "image/png": ("PNG", ".png"),
    "image/jpeg": ("JPG", ".jpg"),
    "image/jpg": ("JPG", ".jpg"),
}
FILE_SIGNATURES = {
    "PDF": (b"%PDF-", "pdf"),
    "PNG": (b"\x89PNG\r\n\x1a\n", "png"),
    "JPG": (b"\xff\xd8\xff", "jpg"),
}
OCR_SPACE_ERROR_MESSAGES = {
    "E501": "OCR.space rejected the file because it is not a valid image or PDF.",
    "E580": "OCR.space engine failed while reading this file.",
    "invalid_file_signature": "Uploaded file is not a valid PDF, PNG, or JPG. Please upload the original invoice file.",
    "empty_file": "Uploaded file is empty. Please upload the original invoice PDF, PNG, or JPG.",
    "unsupported_filetype": "Uploaded file type is not supported for OCR.space. Please upload a PDF, PNG, or JPG.",
    "timeout": "OCR.space request timed out.",
    "malformed_response": "OCR.space returned an unexpected response.",
}


class OCRSpaceOCRAdapter:
    provider_name = OCRProviderName.OCR_SPACE

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def get_provider_name(self) -> str:
        return self.provider_name

    def is_configured(self) -> bool:
        return bool(self.settings.ocr_space_api_key and self.settings.ocr_space_api_url)

    def health_check(self) -> dict:
        configured = self.is_configured()
        return {
            "provider": self.provider_name,
            "configured": configured,
            "status": "ok" if configured else "missing_credentials",
            "api_url_configured": bool(self.settings.ocr_space_api_url),
            "language": self.settings.ocr_space_language or "eng",
            "engine": str(self.settings.ocr_space_engine or "2"),
            "fallback_engine": str(self.settings.ocr_space_fallback_engine or ""),
            "engine_fallback_enabled": bool(self.settings.ocr_space_enable_engine_fallback),
        }

    def extract_invoice(self, document_reference: dict, tenant_id: UUID) -> OCRExtractionResult:
        if not self.is_configured():
            return self.normalize_provider_response(
                {"error": "OCR.space API key is not configured"},
                tenant_id,
            )
        content = document_reference.get("content")
        if content is None:
            return self.normalize_provider_response(
                {"error": "OCR.space OCR requires invoice bytes in the current runtime"},
                tenant_id,
            )
        body = content if isinstance(content, bytes) else str(content).encode("utf-8")
        content_type = str(document_reference.get("mime_type") or "application/octet-stream")
        prepared = self._prepare_file_metadata(
            file_name=str(document_reference.get("file_name") or ""),
            content_type=content_type,
        )
        if prepared is None:
            return self.normalize_provider_response(
                {
                    "error": f"OCR.space does not support content type {content_type}",
                    "_apflow_content_type": content_type,
                    "_apflow_sent_content_type": content_type,
                },
                tenant_id,
                raw_provider_status="unsupported_content_type",
            )
        safe_file_name, file_type, normalized_content_type = prepared
        signature = self._validate_file_signature(body, file_type)
        if not signature["valid"]:
            return self.normalize_provider_response(
                {
                    "error": signature["safe_message"],
                    "_apflow_provider_error_code": signature["reason"],
                    "_apflow_content_type": content_type,
                    "_apflow_sent_file_name": safe_file_name,
                    "_apflow_sent_filetype": file_type,
                    "_apflow_sent_content_type": normalized_content_type,
                    "_apflow_detected_filetype": signature["detected_filetype"],
                    "_apflow_file_size_bytes": signature["size_bytes"],
                },
                tenant_id,
                raw_provider_status=signature["reason"],
            )
        try:
            raw_response = self._post_with_optional_fallback(
                file_name=safe_file_name,
                content=body,
                content_type=normalized_content_type,
                file_type=file_type,
            )
            raw_response["_apflow_content_type"] = content_type
            raw_response["_apflow_sent_file_name"] = safe_file_name
            raw_response["_apflow_sent_filetype"] = file_type
            raw_response["_apflow_sent_content_type"] = normalized_content_type
            return self.normalize_provider_response(raw_response, tenant_id)
        except Exception as exc:
            return self.normalize_provider_response(
                {
                    "error": f"OCR.space extraction failed: {exc.__class__.__name__}",
                    "_apflow_provider_error_code": "provider_exception",
                    "_apflow_content_type": content_type,
                    "_apflow_sent_file_name": safe_file_name,
                    "_apflow_sent_filetype": file_type,
                    "_apflow_sent_content_type": normalized_content_type,
                },
                tenant_id,
                raw_provider_status="provider_error",
            )

    def normalize_provider_response(
        self,
        raw_response: dict,
        tenant_id: UUID,
        raw_provider_status: str | None = None,
    ) -> OCRExtractionResult:
        parsed_text = self._parsed_text(raw_response)
        provider_error = self._provider_error(raw_response, parsed_text)
        if raw_response.get("error"):
            return self._error_result(
                provider_error["message"] if provider_error is not None else str(raw_response["error"]),
                tenant_id,
                raw_response,
                parsed_text,
                raw_provider_status=raw_provider_status
                or (provider_error["status"] if provider_error is not None else "missing_credentials"),
            )
        if provider_error is not None:
            return self._error_result(
                provider_error["message"],
                tenant_id,
                raw_response,
                parsed_text,
                raw_provider_status=provider_error["status"],
            )

        fields = self._fields_from_text(parsed_text)
        line_items = self._line_items_from_text(parsed_text)
        diagnostics = self._safe_diagnostics(raw_response, parsed_text)
        status = "ok" if parsed_text else "no_parsed_text"
        return OCRExtractionResult(
            tenant_id=tenant_id,
            provider_metadata=OCRProviderMetadata(
                provider_name=OCRProviderName.OCR_SPACE,
                configured=self.is_configured(),
                model_version=f"engine-{diagnostics['engine_used'] or self.settings.ocr_space_engine or '2'}",
                raw_provider_status=status,
                is_errored_on_processing=diagnostics["is_errored_on_processing"],
                ocr_exit_code=diagnostics["ocr_exit_code"],
                parsed_result_count=diagnostics["parsed_result_count"],
                parsed_text_length=diagnostics["parsed_text_length"],
                detected_content_type=diagnostics["detected_content_type"],
                sent_file_name=diagnostics["sent_file_name"],
                sent_filetype=diagnostics["sent_filetype"],
                sent_content_type=diagnostics["sent_content_type"],
                provider_error_code=diagnostics["provider_error_code"],
                provider_error_message=diagnostics["provider_error_message"],
                engine_used=diagnostics["engine_used"],
                fallback_engine=diagnostics["fallback_engine"],
                fallback_used=diagnostics["fallback_used"],
                primary_provider_error_code=diagnostics["primary_provider_error_code"],
                primary_provider_error_message=diagnostics["primary_provider_error_message"],
            ),
            fields=fields,
            line_items=line_items,
            confidence_summary=self._summary(fields),
            raw_response={
                **diagnostics,
                "ocr_text_preview": parsed_text[:1000],
            },
        )

    def _post_with_optional_fallback(
        self,
        file_name: str,
        content: bytes,
        content_type: str,
        file_type: str,
    ) -> dict:
        primary_engine = str(self.settings.ocr_space_engine or "2")
        fallback_engine = str(self.settings.ocr_space_fallback_engine or "").strip()
        raw_response = self._post_to_ocr_space(
            file_name=file_name,
            content=content,
            content_type=content_type,
            file_type=file_type,
            engine=primary_engine,
        )
        raw_response["_apflow_engine_used"] = primary_engine
        raw_response["_apflow_primary_engine"] = primary_engine
        raw_response["_apflow_fallback_engine"] = fallback_engine or None
        raw_response["_apflow_fallback_used"] = False

        provider_error = self._provider_error(raw_response, self._parsed_text(raw_response))
        should_retry = (
            bool(self.settings.ocr_space_enable_engine_fallback)
            and fallback_engine
            and fallback_engine != primary_engine
            and provider_error is not None
            and provider_error["code"] in {"E580", "engine_failed"}
        )
        if not should_retry:
            return raw_response

        fallback_response = self._post_to_ocr_space(
            file_name=file_name,
            content=content,
            content_type=content_type,
            file_type=file_type,
            engine=fallback_engine,
        )
        fallback_response["_apflow_engine_used"] = fallback_engine
        fallback_response["_apflow_primary_engine"] = primary_engine
        fallback_response["_apflow_fallback_engine"] = fallback_engine
        fallback_response["_apflow_fallback_used"] = True
        fallback_response["_apflow_primary_provider_error_code"] = provider_error["code"]
        fallback_response["_apflow_primary_provider_error_message"] = provider_error["message"]
        return fallback_response

    def _post_to_ocr_space(
        self,
        file_name: str,
        content: bytes,
        content_type: str,
        file_type: str,
        engine: str | None = None,
    ) -> dict:
        boundary = "----apflow-ocr-space-boundary"
        data_fields = {
            "language": self.settings.ocr_space_language or "eng",
            "isOverlayRequired": "false",
            "OCREngine": str(engine or self.settings.ocr_space_engine or "2"),
            "scale": "true",
            "detectOrientation": "true",
            "filetype": file_type,
        }
        chunks: list[bytes] = []
        for name, value in data_fields.items():
            chunks.extend(
                [
                    f"--{boundary}\r\n".encode(),
                    f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                    str(value).encode(),
                    b"\r\n",
                ]
            )
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="file"; filename="{file_name}"\r\n'.encode(),
                f"Content-Type: {content_type}\r\n\r\n".encode(),
                content,
                b"\r\n",
                f"--{boundary}--\r\n".encode(),
            ]
        )
        request = urllib.request.Request(
            self.settings.ocr_space_api_url,
            data=b"".join(chunks),
            method="POST",
            headers={
                "apikey": self.settings.ocr_space_api_key,
                "content-type": f"multipart/form-data; boundary={boundary}",
            },
        )
        try:
            with urllib.request.urlopen(
                request,
                timeout=self.settings.ocr_space_timeout_seconds,
            ) as response:
                return self._decode_provider_json(response.read(), http_status=getattr(response, "status", None))
        except urllib.error.HTTPError as exc:
            decoded = self._decode_provider_json(exc.read(), http_status=exc.code)
            decoded.setdefault("error", self._http_error_message(exc.code, decoded))
            return decoded
        except (TimeoutError, socket.timeout) as exc:
            return {
                "error": OCR_SPACE_ERROR_MESSAGES["timeout"],
                "_apflow_provider_error_code": "timeout",
                "_apflow_transport_error": exc.__class__.__name__,
            }
        except urllib.error.URLError as exc:
            reason = getattr(exc, "reason", None)
            timed_out = isinstance(reason, (TimeoutError, socket.timeout))
            return {
                "error": OCR_SPACE_ERROR_MESSAGES["timeout"]
                if timed_out
                else "OCR.space request failed before a response was received.",
                "_apflow_provider_error_code": "timeout" if timed_out else "connection_failed",
                "_apflow_transport_error": exc.__class__.__name__,
            }

    def _decode_provider_json(self, body: bytes, http_status: int | None = None) -> dict:
        try:
            decoded = json.loads(body.decode("utf-8"))
            if isinstance(decoded, dict):
                decoded["_apflow_http_status"] = http_status
                return decoded
        except (UnicodeDecodeError, json.JSONDecodeError):
            pass
        return {
            "error": OCR_SPACE_ERROR_MESSAGES["malformed_response"],
            "_apflow_provider_error_code": "malformed_response",
            "_apflow_http_status": http_status,
        }

    def _http_error_message(self, status_code: int, decoded: dict) -> str:
        provider_error = self._provider_error(decoded, self._parsed_text(decoded))
        if provider_error is not None:
            return provider_error["message"]
        if status_code in {401, 403}:
            decoded["_apflow_provider_error_code"] = "unauthorized"
            return "OCR.space rejected the request. Check OCR.space API credentials."
        if status_code == 429:
            decoded["_apflow_provider_error_code"] = "rate_limited"
            return "OCR.space rate limit or quota was reached."
        return f"OCR.space HTTP {status_code} error."

    def _prepare_file_metadata(
        self,
        file_name: str,
        content_type: str,
    ) -> tuple[str, str, str] | None:
        normalized_content_type = content_type.lower().split(";", 1)[0].strip()
        mapping = OCR_SPACE_FILETYPES.get(normalized_content_type)
        if mapping is None:
            return None
        file_type, extension = mapping
        safe_name = PurePath(file_name).name.strip() if file_name else ""
        if not safe_name:
            safe_name = f"invoice{extension}"
        current_extension = PurePath(safe_name).suffix.lower()
        valid_extensions = {extension}
        if file_type == "JPG":
            valid_extensions = {".jpg", ".jpeg"}
        if current_extension not in valid_extensions:
            safe_name = f"{safe_name}{extension}"
        return safe_name, file_type, normalized_content_type

    def _validate_file_signature(self, content: bytes, expected_file_type: str) -> dict:
        size = len(content)
        if size == 0:
            return {
                "valid": False,
                "detected_filetype": "unknown",
                "reason": "empty_file",
                "safe_message": OCR_SPACE_ERROR_MESSAGES["empty_file"],
                "size_bytes": size,
            }
        expected_signature = FILE_SIGNATURES.get(expected_file_type)
        detected = self._detect_filetype(content)
        if expected_signature is None:
            return {
                "valid": False,
                "detected_filetype": detected,
                "reason": "unsupported_filetype",
                "safe_message": OCR_SPACE_ERROR_MESSAGES["unsupported_filetype"],
                "size_bytes": size,
            }
        if not content.startswith(expected_signature[0]):
            return {
                "valid": False,
                "detected_filetype": detected,
                "reason": "invalid_file_signature",
                "safe_message": OCR_SPACE_ERROR_MESSAGES["invalid_file_signature"],
                "size_bytes": size,
            }
        return {
            "valid": True,
            "detected_filetype": expected_signature[1],
            "reason": "ok",
            "safe_message": "File signature is valid.",
            "size_bytes": size,
        }

    def _detect_filetype(self, content: bytes) -> str:
        for _file_type, (signature, detected) in FILE_SIGNATURES.items():
            if content.startswith(signature):
                return detected
        return "unknown"

    def _fields_from_text(self, text: str) -> list[OCRExtractedField]:
        invoice_number = self._find(
            text,
            [
                r"\b(?:invoice[ \t]*(?:number|no\.?|#)|inv[ \t]*(?:no\.?|#)|tax[ \t]*invoice[ \t]*(?:number|no\.?|#)?)[ \t]*[:#-]?[ \t]*([A-Z0-9][A-Z0-9\-\/]{1,})",
                r"(?ims)^\s*(?:invoice|tax invoice)\s*$\s*^\s*#\s*([A-Z0-9][A-Z0-9\-\/]{1,})\s*$",
                r"(?im)^\s*(?:invoice|tax invoice)\s+([A-Z0-9][A-Z0-9\-\/]{2,})\s*$",
            ],
            confidence=0.9,
        )
        supplier_name = self._find(
            text,
            [
                r"(?im)^\s*(?:vendor|supplier|from|sold by|seller)\s*[:#-]\s*(.+?)\s*$",
                r"(?im)^\s*(?:bill from|remit to)\s*[:#-]\s*(.+?)\s*$",
            ],
        ) or self._infer_supplier_name(text)
        return [
            self._field("invoice_number", invoice_number, required=True),
            self._field("supplier_name", supplier_name, required=True),
            self._field(
                "supplier_tax_id",
                self._find(text, [r"\b(?:vendor\s*)?(?:tax\s*id|vat\s*id|tin)\s*[:#-]?\s*([A-Z0-9\-]+)"]),
            ),
            self._field(
                "invoice_date",
                self._find(
                    text,
                    [
                        rf"(?im)^\s*invoice\s*date\s*[:#-]?\s*{DATE_VALUE}\s*$",
                        rf"(?im)^\s*date\s*[:#-]?\s*{DATE_VALUE}\s*$",
                    ],
                ),
                required=True,
            ),
            self._field(
                "due_date",
                self._find(
                    text,
                    [
                        rf"\b(?:due\s*date|payment\s*due)\s*[:#-]?\s*{DATE_VALUE}",
                    ],
                ),
            ),
            self._field("currency", self._currency(text), required=True),
            self._field(
                "subtotal",
                self._money(
                    text,
                    [
                        rf"\b(?:sub[\s-]?total|net\s*amount|net)\s*[:#-]?\s*(?:[^\d\r\n-]{{0,20}}){MONEY_VALUE}",
                    ],
                ),
            ),
            self._field(
                "tax_total",
                self._money(
                    text,
                    [
                        rf"\b(?:sales\s*tax|tax\s*amount|tax|vat)\s*[:#-]?\s*(?:[^\d\r\n-]{{0,20}}){MONEY_VALUE}",
                    ],
                ),
            ),
            self._field(
                "shipping_amount",
                self._money(
                    text,
                    [
                        rf"\b(?:shipping|freight|delivery)\s*[:#-]?\s*(?:[^\d\r\n-]{{0,20}}){MONEY_VALUE}",
                    ],
                ),
            ),
            self._field(
                "fee_total",
                self._money(
                    text,
                    [
                        rf"\b(?:handling|service\s*fee)\s*[:#-]?\s*(?:[^\d\r\n-]{{0,20}}){MONEY_VALUE}",
                    ],
                ),
            ),
            self._field(
                "discount_total",
                self._money(
                    text,
                    [
                        rf"\bdiscount\s*[:#-]?\s*(?:[^\d\r\n-]{{0,20}}){MONEY_VALUE}",
                    ],
                ),
            ),
            self._field(
                "grand_total",
                self._money(
                    text,
                    [
                        rf"\b(?:grand\s*total|amount\s*due|balance\s*due|total\s*amount)\s*[:#-]?\s*(?:[^\d\r\n-]{{0,20}}){MONEY_VALUE}",
                        rf"(?im)^\s*total\s*[:#-]?\s*(?:[^\d\r\n-]{{0,20}}){MONEY_VALUE}\s*$",
                    ],
                    confidence=0.82,
                ),
                required=True,
            ),
            self._field(
                "po_number",
                self._find(
                    text,
                    [
                        r"\b(?:purchase\s*order|p\.?\s*o\.?|po)\s*(?:number|no\.?|#)?\s*[:#-]?\s*([A-Z0-9][A-Z0-9\-\/]{1,})",
                    ],
                ),
            ),
        ]

    def _field(
        self,
        field_name: str,
        match: tuple[str | float | None, str | None, float] | None,
        required: bool = False,
    ) -> OCRExtractedField:
        value, raw_text, confidence = match if match is not None else (None, None, 0)
        missing = value in (None, "")
        return OCRExtractedField(
            field_name=field_name,
            value=value,
            confidence=confidence,
            raw_text=raw_text,
            requires_review=(required and (missing or confidence < 0.75)) or (not missing and confidence < 0.75),
        )

    def _find(
        self,
        text: str,
        patterns: list[str],
        confidence: float = 0.8,
    ) -> tuple[str | None, str | None, float] | None:
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                value = match.group(1).strip().strip(" .,:;")
                if value:
                    return value, match.group(0).strip(), confidence
        return None

    def _money(
        self,
        text: str,
        patterns: list[str],
        confidence: float = 0.8,
    ) -> tuple[float | None, str | None, float] | None:
        found = self._find(text, patterns, confidence=confidence)
        if found is None or found[0] is None:
            return None
        value = self._parse_amount(found[0])
        return value, found[1], confidence if value is not None else 0

    def _parse_amount(self, value: str) -> float | None:
        cleaned = re.sub(r"[^0-9.\-]", "", value.replace(",", ""))
        if not cleaned:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None

    def _currency(self, text: str) -> tuple[str | None, str | None, float] | None:
        explicit = self._find(text, [r"\bcurrency\s*[:#-]?\s*([A-Z]{3})\b"], confidence=0.84)
        if explicit:
            return explicit[0], explicit[1], explicit[2]
        code_match = re.search(r"\b(USD|EUR|GBP|ILS|NIS|CAD|AUD)\b", text, flags=re.IGNORECASE)
        if code_match:
            value = code_match.group(1).upper()
            return "ILS" if value == "NIS" else value, code_match.group(0), 0.8
        symbols = {
            "$": "USD",
            chr(0x20AC): "EUR",
            chr(0x00A3): "GBP",
            chr(0x20AA): "ILS",
        }
        for symbol, code in symbols.items():
            if symbol in text:
                return code, symbol, 0.76
        return None

    def _infer_supplier_name(self, text: str) -> tuple[str | None, str | None, float] | None:
        business_terms = re.compile(r"\b(inc|llc|ltd|limited|corp|corporation|company|co\.|solutions|systems|services|group|technologies)\b", re.I)
        skip_terms = re.compile(r"\b(invoice|tax invoice|date|due|total|amount|purchase order|po\s*#|bill to|ship to|page|vat|tax id)\b", re.I)
        lines = [line.strip(" \t:-") for line in text.splitlines()[:14]]
        candidates = [line for line in lines if len(line) >= 3 and re.search(r"[A-Za-z]", line) and not skip_terms.search(line)]
        for line in candidates:
            if business_terms.search(line):
                return line[:120], line, 0.62
        if candidates:
            return candidates[0][:120], candidates[0], 0.55
        return None

    def _line_items_from_text(self, text: str) -> list[OCRExtractedLineItem]:
        items: list[OCRExtractedLineItem] = []
        skip_terms = re.compile(r"\b(subtotal|total|tax|vat|amount due|balance due)\b", re.I)
        for line in text.splitlines():
            if len(items) >= 5 or skip_terms.search(line) or not re.search(r"[A-Za-z]", line):
                continue
            amounts = re.findall(r"-?[\d,]+(?:\.\d{2})", line)
            if len(amounts) < 2:
                continue
            description = re.split(r"\s+-?[\d,]+(?:\.\d{2})", line, maxsplit=1)[0].strip(" -:\t")
            if len(description) < 3:
                continue
            unit_price = self._parse_amount(amounts[-2])
            total = self._parse_amount(amounts[-1])
            item_fields = [
                OCRExtractedField(field_name="description", value=description[:160], confidence=0.55, requires_review=True),
                OCRExtractedField(field_name="quantity", value=1, confidence=0.55, requires_review=True),
                OCRExtractedField(field_name="unit_price", value=unit_price, confidence=0.55, requires_review=True),
                OCRExtractedField(field_name="total", value=total, confidence=0.55, requires_review=True),
            ]
            items.append(OCRExtractedLineItem(fields=item_fields, confidence=0.55, requires_review=True))
        return items

    def _parsed_text(self, raw_response: dict) -> str:
        results = raw_response.get("ParsedResults") or []
        texts = [str(result.get("ParsedText") or "") for result in results if isinstance(result, dict)]
        return "\n".join(text for text in texts if text)

    def _provider_error(self, raw_response: dict, parsed_text: str) -> dict | None:
        code = self._provider_error_code(raw_response)
        message = self._provider_error_message(raw_response)
        results = raw_response.get("ParsedResults") or []
        first_result = results[0] if isinstance(results, list) and results and isinstance(results[0], dict) else {}
        file_parse_exit_code = first_result.get("FileParseExitCode")
        has_result_error = bool(first_result.get("ErrorMessage") or first_result.get("ErrorDetails"))
        if code == "E501" or self._contains_error_token(message, "E501"):
            return {
                "code": "E501",
                "message": OCR_SPACE_ERROR_MESSAGES["E501"],
                "status": "invalid_file_signature",
            }
        if code == "E580" or self._contains_error_token(message, "E580"):
            if raw_response.get("_apflow_fallback_used"):
                primary = raw_response.get("_apflow_primary_engine")
                fallback = raw_response.get("_apflow_fallback_engine")
                message = f"OCR.space failed with primary engine {primary} and fallback engine {fallback}."
            else:
                message = OCR_SPACE_ERROR_MESSAGES["E580"]
            return {
                "code": "E580",
                "message": message,
                "status": "engine_failed",
            }
        if raw_response.get("_apflow_provider_error_code"):
            safe_code = str(raw_response["_apflow_provider_error_code"])
            return {
                "code": safe_code,
                "message": str(raw_response.get("error") or OCR_SPACE_ERROR_MESSAGES.get(safe_code) or message),
                "status": safe_code,
            }
        if raw_response.get("IsErroredOnProcessing"):
            return {"code": code or "provider_error", "message": message, "status": "provider_error"}
        if not parsed_text and (file_parse_exit_code in {-1, "-1"} or has_result_error):
            return {
                "code": code or "engine_failed",
                "message": OCR_SPACE_ERROR_MESSAGES["E580"] if code == "E580" else message,
                "status": "engine_failed",
            }
        return None

    def _provider_error_code(self, raw_response: dict) -> str | None:
        explicit = raw_response.get("_apflow_provider_error_code")
        if explicit:
            return str(explicit)
        message = self._provider_error_message(raw_response)
        match = re.search(r"\b(E\d{3})\b", message)
        if match:
            return match.group(1)
        return None

    def _contains_error_token(self, message: str, token: str) -> bool:
        return token.lower() in message.lower()

    def _provider_error_message(self, raw_response: dict) -> str:
        message = raw_response.get("ErrorMessage") or raw_response.get("ErrorDetails")
        if not message:
            results = raw_response.get("ParsedResults") or []
            first_result = results[0] if isinstance(results, list) and results and isinstance(results[0], dict) else {}
            message = first_result.get("ErrorMessage") or first_result.get("ErrorDetails")
        if isinstance(message, list):
            return "; ".join(str(item) for item in message if item)
        if message:
            return str(message)
        return "OCR.space returned an OCR processing error"

    def _safe_diagnostics(self, raw_response: dict, parsed_text: str) -> dict:
        results = raw_response.get("ParsedResults") or []
        provider_error = self._provider_error(raw_response, parsed_text)
        return {
            "provider": "ocr_space",
            "is_errored_on_processing": bool(raw_response.get("IsErroredOnProcessing")),
            "ocr_exit_code": raw_response.get("OCRExitCode"),
            "parsed_result_count": len(results) if isinstance(results, list) else 0,
            "parsed_text_length": len(parsed_text),
            "detected_content_type": raw_response.get("_apflow_content_type"),
            "sent_file_name": raw_response.get("_apflow_sent_file_name"),
            "sent_filetype": raw_response.get("_apflow_sent_filetype"),
            "sent_content_type": raw_response.get("_apflow_sent_content_type"),
            "provider_error_code": provider_error["code"] if provider_error is not None else self._provider_error_code(raw_response),
            "provider_error_message": provider_error["message"]
            if provider_error is not None
            else raw_response.get("error"),
            "engine_used": raw_response.get("_apflow_engine_used") or str(self.settings.ocr_space_engine or "2"),
            "fallback_engine": raw_response.get("_apflow_fallback_engine") or str(self.settings.ocr_space_fallback_engine or ""),
            "fallback_used": bool(raw_response.get("_apflow_fallback_used")),
            "primary_provider_error_code": raw_response.get("_apflow_primary_provider_error_code"),
            "primary_provider_error_message": raw_response.get("_apflow_primary_provider_error_message"),
            "file_size_bytes": raw_response.get("_apflow_file_size_bytes"),
            "detected_filetype": raw_response.get("_apflow_detected_filetype"),
        }

    def _error_result(
        self,
        message: str,
        tenant_id: UUID,
        raw_response: dict | None = None,
        parsed_text: str = "",
        raw_provider_status: str = "missing_credentials",
    ) -> OCRExtractionResult:
        raw_response = raw_response or {}
        diagnostics = self._safe_diagnostics(raw_response, parsed_text)
        return OCRExtractionResult(
            tenant_id=tenant_id,
            provider_metadata=OCRProviderMetadata(
                provider_name=OCRProviderName.OCR_SPACE,
                configured=self.is_configured(),
                raw_provider_status=raw_provider_status,
                is_errored_on_processing=diagnostics["is_errored_on_processing"],
                ocr_exit_code=diagnostics["ocr_exit_code"],
                parsed_result_count=diagnostics["parsed_result_count"],
                parsed_text_length=diagnostics["parsed_text_length"],
                detected_content_type=diagnostics["detected_content_type"],
                sent_file_name=diagnostics["sent_file_name"],
                sent_filetype=diagnostics["sent_filetype"],
                sent_content_type=diagnostics["sent_content_type"],
                provider_error_code=diagnostics["provider_error_code"],
                provider_error_message=diagnostics["provider_error_message"],
                engine_used=diagnostics["engine_used"],
                fallback_engine=diagnostics["fallback_engine"],
                fallback_used=diagnostics["fallback_used"],
                primary_provider_error_code=diagnostics["primary_provider_error_code"],
                primary_provider_error_message=diagnostics["primary_provider_error_message"],
            ),
            fields=[],
            line_items=[],
            confidence_summary=OCRConfidenceSummary(
                average_confidence=0,
                required_fields_missing=REQUIRED_FIELDS,
            ),
            raw_response={**diagnostics, "ocr_text_preview": parsed_text[:1000]},
            error=message,
        )

    def _summary(self, fields: list[OCRExtractedField]) -> OCRConfidenceSummary:
        missing = [
            field_name
            for field_name in REQUIRED_FIELDS
            if not any(field.field_name == field_name and field.value not in (None, "") for field in fields)
        ]
        low_required = [
            field.field_name
            for field in fields
            if field.field_name in REQUIRED_FIELDS and field.value not in (None, "") and field.confidence < 0.75
        ]
        average_fields = [
            field
            for field in fields
            if field.value not in (None, "") or field.field_name in REQUIRED_FIELDS
        ]
        average = round(sum(field.confidence for field in average_fields) / len(average_fields), 4) if average_fields else 0
        return OCRConfidenceSummary(
            average_confidence=average,
            high_confidence_fields=sum(1 for field in fields if self._band(field.confidence) == ConfidenceBand.HIGH),
            medium_confidence_fields=sum(1 for field in fields if self._band(field.confidence) == ConfidenceBand.MEDIUM),
            low_confidence_fields=sum(1 for field in fields if self._band(field.confidence) == ConfidenceBand.LOW),
            required_fields_missing=missing,
            required_fields_low_confidence=low_required,
        )

    def _band(self, confidence: float) -> ConfidenceBand:
        if confidence >= 0.9:
            return ConfidenceBand.HIGH
        if confidence >= 0.75:
            return ConfidenceBand.MEDIUM
        return ConfidenceBand.LOW
