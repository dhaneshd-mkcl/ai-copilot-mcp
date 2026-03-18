import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)

ERROR_PATTERNS = [
    (r"TypeError: (.+)", "TypeError"),
    (r"NameError: (.+)", "NameError"),
    (r"AttributeError: (.+)", "AttributeError"),
    (r"ImportError: (.+)", "ImportError"),
    (r"SyntaxError: (.+)", "SyntaxError"),
    (r"KeyError: (.+)", "KeyError"),
    (r"IndexError: (.+)", "IndexError"),
    (r"ValueError: (.+)", "ValueError"),
    (r"RuntimeError: (.+)", "RuntimeError"),
    (r"(\d{3}) (.*Error.*)", "HTTP Error"),
    (r"ENOENT: no such file", "File Not Found"),
    (r"ECONNREFUSED", "Connection Refused"),
    (r"null pointer|NullPointerException", "Null Reference"),
    (r"SegmentationFault|segfault", "Segmentation Fault"),
]

COMMON_FIXES = {
    "TypeError": [
        "Check variable types before operations",
        "Use isinstance() to validate input types",
        "Ensure function arguments match expected types",
    ],
    "NameError": [
        "Check for typos in variable names",
        "Ensure variable is defined before use",
        "Check import statements",
    ],
    "ImportError": [
        "Run: pip install <package_name>",
        "Check virtual environment activation",
        "Verify package name spelling",
    ],
    "KeyError": [
        "Use dict.get(key, default) instead of dict[key]",
        "Check if key exists with 'in' operator",
        "Print dict keys to debug",
    ],
    "HTTP Error": [
        "Check server logs for details",
        "Verify request headers and body",
        "Check authentication credentials",
        "Inspect network connectivity",
    ],
}


class CodeDebugger:
    def parse_error(self, error_text: str) -> dict:
        logger.info("code_debugger.parse_error", extra={"error_len": len(error_text)})
        detected = []
        for pattern, error_type in ERROR_PATTERNS:
            match = re.search(pattern, error_text, re.IGNORECASE)
            if match:
                detected.append({
                    "type": error_type,
                    "message": match.group(0),
                    "suggestions": COMMON_FIXES.get(error_type, ["Review the stack trace carefully"]),
                })

        # Extract stack trace lines
        stack_lines = [
            line.strip() for line in error_text.splitlines()
            if "File " in line or "line " in line.lower()
        ]

        return {
            "detected_errors": detected,
            "stack_trace_lines": stack_lines[:10],
            "raw_error": error_text[:500],
            "has_known_pattern": len(detected) > 0,
        }

    def build_debug_prompt(self, code: str, error: str, language: str = "python") -> str:
        analysis = self.parse_error(error)
        error_types = [e["type"] for e in analysis["detected_errors"]]
        return f"""Debug this {language} code error:

**Code:**
```{language}
{code}
```

**Error:**
```
{error}
```

**Detected Error Types:** {', '.join(error_types) if error_types else 'Unknown'}

Please:
1. Identify the root cause
2. Explain what went wrong
3. Provide the fixed code
4. Suggest how to prevent this in the future"""


code_debugger = CodeDebugger()
