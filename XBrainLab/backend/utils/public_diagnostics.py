"""Central privacy boundary for logs and public diagnostic payloads."""

from __future__ import annotations

import builtins
import hashlib
import hmac
import ipaddress
import os
import re
import secrets
import unicodedata
from enum import Enum
from pathlib import PosixPath, PurePosixPath, PureWindowsPath, WindowsPath
from typing import Any, cast
from urllib.parse import unquote


class DiagnosticDisclosure(str, Enum):
    """Explicit disclosure mode for diagnostic rendering."""

    PUBLIC = "public"
    DETAILED = "detailed"


class DiagnosticTextLayout(str, Enum):
    """Allowed layout for sanitized diagnostic text."""

    PRESERVE_LINES = "preserve_lines"
    SINGLE_LINE = "single_line"


class _DiagnosticFieldSensitivity(str, Enum):
    PUBLIC = "public"
    SECRET = "secret"  # noqa: S105 - sensitivity classification
    IDENTITY = "identity"
    PATH = "path"


REDACTED_PATH_MARKER = "[REDACTED_PATH]"
REDACTED_SECRET_MARKER = "[REDACTED_SECRET]"  # noqa: S105 - redaction sentinel
REDACTED_EMAIL_MARKER = "[REDACTED_EMAIL]"
PUBLIC_DIAGNOSTIC_MAX_INPUT_BYTES = 128 * 1024
PUBLIC_DIAGNOSTIC_MAX_CONTAINER_DEPTH = 16
PUBLIC_DIAGNOSTIC_MAX_CONTAINER_ITEMS = 256
PUBLIC_DIAGNOSTIC_MAX_TOTAL_NODES = 2_048
PUBLIC_DIAGNOSTIC_MAX_OUTPUT_BYTES = 256 * 1024
PUBLIC_DIAGNOSTIC_CYCLE_MARKER = "[CYCLE]"
PUBLIC_DIAGNOSTIC_SHARED_MARKER = "[SHARED]"
PUBLIC_DIAGNOSTIC_TRUNCATED_MARKER = "[TRUNCATED]"
PUBLIC_DIAGNOSTIC_TRUNCATED_ITEMS_KEY = "[TRUNCATED_ITEMS]"
PUBLIC_DIAGNOSTIC_UNSUPPORTED_MARKER = "[UNSUPPORTED_VALUE]"

_REFERENCE_KEY = secrets.token_bytes(32)
_SAFE_PATH_TYPES = (PosixPath, WindowsPath, PurePosixPath, PureWindowsPath)
_SAFE_BUILTIN_EXCEPTION_TYPES = tuple(
    (value, name)
    for name, value in vars(builtins).items()
    if type(value) is type and issubclass(value, BaseException)
)
_SAFE_CONTAINER_TYPES = (dict, list, tuple, set)
_SAFE_PRIMITIVE_TYPES = (bool, int, float)
_MAX_SAFE_PRIMITIVE_TEXT_BYTES = 4 * 1024
_TRUNCATED_INPUT_MARKER = " [TRUNCATED]"
_ANSI_ESCAPE_PATTERN = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|[@-_])")
_SECRET_NAME = (
    r"(?:[a-z0-9]+[_-])*"  # noqa: S105 - secret-field matching regex
    r"(?:api[\s_-]*key|access[\s_-]*token|"
    r"access[\s_-]*key[\s_-]*id|"
    r"secret[\s_-]*access[\s_-]*key|aws[\s_-]*session[\s_-]*token|"
    r"x[\s_-]*amz[\s_-]*(?:credential|signature)|"
    r"auth(?:entication|orization)?[\s_-]*token|authorization|"
    r"bearer[\s_-]*token|hf[\s_-]*token|client[\s_-]*secret|"
    r"private[\s_-]*key|secret[\s_-]*key|"
    r"pass[\s_-]*word|pass[\s_-]*wd|token|secret)"
)
_JSON_SECRET_ASSIGNMENT_PATTERN = re.compile(
    rf"""(?ix)
    (?P<key_escape>\\?)
    (?P<quote>["'])
    {_SECRET_NAME}
    (?P=key_escape)
    (?P=quote)
    \s*:\s*
    (?:bearer\s+)?
    (?:
        (?P<value_escape>\\?)
        (?P<value_quote>["'])
        [^"'\r\n]*
        (?P=value_escape)
        (?P=value_quote)
        |
        [^\s,;}}\]]+
    )
    """,
)
_SECRET_ASSIGNMENT_PATTERN = re.compile(
    rf"""(?ix)
    (?<![\w])
    {_SECRET_NAME}
    \s*(?::|=|%3d)\s*
    (?:(?:bearer|basic)\s+)?
    (?:
        "[^"\r\n]*"
        |
        '[^'\r\n]*'
        |
        [^\r\n,;&}}\]]+?
        (?=
            $
            |
            \r?\n
            |
            [,;&}}\]]
            |
            [.!?\u3002\uFF01\uFF1F](?=\s+\S|\s*$)
        )
    )
    """,
)
_URL_USERINFO_PATTERN = re.compile(
    r"(?i)(?P<scheme>[a-z][a-z0-9+.-]{0,31}://)"
    r"(?P<userinfo>[^/@\s]{1,512})@"
)
_AUTH_PARAMETER_VALUE = r"""(?:"(?:\\.|[^"\r\n])*"|'(?:\\.|[^'\r\n])*'|[^,\s;\r\n]+)"""
_AUTH_PARAMETER_SEQUENCE = (
    rf"(?:[a-z][a-z0-9_-]*\s*=\s*{_AUTH_PARAMETER_VALUE}\s*(?:,\s*)?)+"
)
_DIGEST_AUTH_PATTERN = re.compile(
    rf"(?i)(?P<prefix>authorization\s*:\s*)?"
    rf"\bdige[\s_-]*st\s+{_AUTH_PARAMETER_SEQUENCE}"
)
_AWS_AUTH_PATTERN = re.compile(
    rf"(?i)(?P<prefix>authorization\s*:\s*)?"
    rf"\baws4-hmac(?:[\s_-]*sha)?[\s_-]*256\s+{_AUTH_PARAMETER_SEQUENCE}"
)
_DIGEST_CREDENTIAL_PARAMETER_PATTERN = re.compile(
    r"(?i)\b(?:algorithm|charset|cnonce|nc|nonce|opaque|qop|realm|response|"
    r"uri|userhash|username)\s*="
)
_BEARER_SECRET_PATTERN = re.compile(
    r"(?i)(?<![\w])bearer\s+[a-z0-9._~+/=-]+",
)
_TOKEN_LITERAL_PATTERN = re.compile(
    r"(?i)(?<![\w])(?:hf_[a-z0-9_-]{8,}|sk-[a-z0-9_-]{8,}|"
    r"github_pat_[a-z0-9_]{8,}|gh[pousr]_[a-z0-9]{8,})(?![\w])",
)
_PERCENT_ENCODED_CANDIDATE_PATTERN = re.compile(
    r"""(?ix)
    (?P<encoded>
        (?<![A-Z0-9%])
        (?:[A-Z0-9._~+-]|%[0-9A-F]{2})+
    )
    """
)
_PERCENT_ENCODED_LABEL_ASSIGNMENT_PATTERN = re.compile(
    r"""(?ix)
    (?P<encoded>
        (?<![\w])
        [A-Z0-9._~+\-]*
        %[0-9A-F]{2}
        (?:
            [A-Z0-9._~+\-]
            |
            %[0-9A-F]{2}
        )*
        \s*(?:=|:)\s*
        [^\r\n,;&}\]]+?
        (?=
            $
            |
            [,;&}\]]
            |
            [.!?\u3002\uFF01\uFF1F](?=\s+\S|\s*$)
        )
    )
    """
)
_PERCENT_ESCAPE_PATTERN = re.compile(r"(?i)%[0-9A-F]{2}")
_NESTED_PERCENT_ESCAPE_PATTERN = re.compile(r"(?i)%(?:25)+(?P<byte>[0-9A-F]{2})")
_CLI_SECRET_OPTION_PATTERN = re.compile(
    rf"""(?ix)
    (?<![\w-])
    --(?:api[-_]?key|access[-_]?token|auth[-_]?token|client[-_]?secret|
    password|passwd|private[-_]?key|secret[-_]?key|token|secret)
    (?:\s+|=)
    {_AUTH_PARAMETER_VALUE}
    """
)
_ENV_SECRET_SPACE_PATTERN = re.compile(
    rf"""(?x)
    (?<![\w])
    (?:ANTHROPIC_API_KEY|AWS_ACCESS_KEY_ID|AWS_SECRET_ACCESS_KEY|
    AWS_SESSION_TOKEN|AZURE_CLIENT_SECRET|GITHUB_TOKEN|GITLAB_TOKEN|
    GOOGLE_API_KEY|HF_TOKEN|HUGGINGFACE_TOKEN|OPENAI_API_KEY)
    [ \t]+
    {_AUTH_PARAMETER_VALUE}
    """
)
_MULTILINE_SECRET_HEADER_PATTERN = re.compile(
    rf"""(?ix)
    (?<![\w])
    {_SECRET_NAME}
    \s*(?::|=|%3d)\s*$
    """
)
_SECRET_KEY_PATTERN = re.compile(rf"(?i)^{_SECRET_NAME}$")
_IDENTITY_ENTITY_LABEL = r"(?:subjects?|participants?|patients?|clients?)"
_IDENTITY_LABEL = (
    rf"{_IDENTITY_ENTITY_LABEL}"
    r"(?:(?:[\s_-]+)(?:ids?|names?|codes?|identit(?:y|ies)))?"
)
_CJK_IDENTITY_LABEL = r"(?:受試者|受试者|參與者|参与者|病人|病患|患者|客戶|客户)"
_IDENTITY_KEY_PATTERN = re.compile(
    rf"(?i)^(?:{_IDENTITY_LABEL}|{_CJK_IDENTITY_LABEL})"
    r"(?:(?:[\s_-]+)by(?:[\s_-]+)[a-z0-9_-]+)?$"
)
_IDENTITY_BY_CONTAINER_PATTERN = re.compile(r"(?i)(?:_|-)by(?:_|-)")
_IDENTITY_VALUE_KEY_PATTERN = re.compile(
    r"(?i)^(?:values?|ids?|identifiers?|names?|"
    r"(?:display|full)[_-]?names?)$"
)
_IDENTITY_METADATA_KEYS = frozenset(
    {
        "age",
        "available",
        "confidence",
        "count",
        "decision",
        "field",
        "missing",
        "optional",
        "reason",
        "required",
        "source",
        "status",
        "sex",
    }
)
_PATH_KEY_PATTERN = re.compile(
    r"(?ix)^(?:"
    r"path|paths|filepath|file_path|source_path|target_path|"
    r"directory|output_dir|cache_dir|root|file|files"
    r")$"
)
_NORMALIZED_SECRET_KEY_SUFFIXES = (
    "apikey",
    "authorization",
    "credential",
    "credentials",
    "cookie",
    "cookies",
    "password",
    "passwd",
    "privatekey",
    "secret",
    "secretkey",
    "token",
)
_NORMALIZED_IDENTITY_PREFIXES = (
    "client",
    "clients",
    "patient",
    "patients",
    "participant",
    "participants",
    "subject",
    "subjects",
)
_NORMALIZED_IDENTITY_SUFFIXES = frozenset(
    {
        "code",
        "codes",
        "id",
        "identifier",
        "identifiers",
        "identity",
        "identities",
        "ids",
        "name",
        "names",
        "uuid",
        "uuids",
    }
)
_NORMALIZED_PATH_KEYS = frozenset(
    {
        "cachedir",
        "directory",
        "dir",
        "file",
        "filename",
        "filenames",
        "files",
        "filepath",
        "filepaths",
        "outputdir",
        "path",
        "paths",
        "root",
        "sourcepath",
        "targetpath",
    }
)
_NORMALIZED_PATH_SUFFIXES = (
    "directory",
    "directories",
    "filename",
    "filenames",
    "filepath",
    "filepaths",
    "path",
    "paths",
)
_PRIVATE_FILE_EXTENSION_PATTERN = (
    r"(?:bdf|bin|brainvision|cfg|cnt|conf|csv|edf|eeg|fif|gdf|gguf|gz|"
    r"h5|hdf5|ini|json|lock|log|mat|mff|npy|npz|nwb|pkl|pt|pth|"
    r"safetensors|set|toml|tsv|txt|vhdr|vmrk|xdf|xml|yaml|yml|zip)"
)
_PRIVATE_FILE_BASENAME_PATTERN = re.compile(
    rf".+\.{_PRIVATE_FILE_EXTENSION_PATTERN}$",
    re.IGNORECASE,
)
_SAFE_PUBLIC_PATH_BASENAMES = frozenset(
    {
        "channels.tsv",
        "config.ini",
        "coordsystem.json",
        "dataset_description.json",
        "events.tsv",
        "f.gdf",
        "participants.tsv",
        "recording.gdf",
        "session.edf",
    }
)
_PRIVATE_URI_PREFIXES = ("file://", "ftp://", "sftp://", "smb://")
_GENERIC_PUBLIC_PATH_DISPLAY_PATTERN = re.compile(
    rf"^file \(\.(?:{_PRIVATE_FILE_EXTENSION_PATTERN})\)$",
    re.IGNORECASE,
)
_PUBLIC_SLASH_COMMANDS = frozenset({"/reset"})
_QUOTED_PATH_PREFIX = (
    r"(?:[A-Za-z]:[\\/]|\\\\|//|/|\$HOME[\\/]|%USERPROFILE%[\\/]|"
    r"(?:file|ftp|sftp|smb)://)"
)
_QUOTED_PATH_PATTERNS = (
    re.compile(
        rf"""(?P<quote>")(?P<path>{_QUOTED_PATH_PREFIX}"""
        r"""(?:\\.|"(?![\s,;:.)\]}!?]|$)|[^"\r\n])*)(?P=quote)""",
    ),
    re.compile(
        rf"""(?P<quote>')(?P<path>{_QUOTED_PATH_PREFIX}"""
        r"""(?:\\.|'(?![\s,;:.)\]}!?]|$)|[^'\r\n])*)(?P=quote)""",
    ),
    re.compile(
        rf"""(?P<quote>`)(?P<path>{_QUOTED_PATH_PREFIX}"""
        r"""(?:\\.|`(?![\s,;:.)\]}!?]|$)|[^`\r\n])*)(?P=quote)""",
    ),
)
_UNQUOTED_PRIVATE_FILE_PATH_PATTERN = re.compile(
    r"""(?P<path>
        (?<![\w:/.\-])
        (?:
            [A-Za-z]:[\\/]
            |
            \\\\[^\\/\r\n,;]+[\\/]
            |
            //[^\\/\r\n,;]+[\\/]
            |
            /(?!/)
            |
            \$HOME[\\/]
            |
            %USERPROFILE%[\\/]
            |
            file://(?:localhost)?/
        )
        [^\r\n,;:)\]}]*?
        \."""
    + _PRIVATE_FILE_EXTENSION_PATTERN
    + r"""
    )
    (?=$|[\s,;:.)\]}!?])
    """,
    re.IGNORECASE | re.VERBOSE,
)
_RELATIVE_PRIVATE_FILE_PATH_PATTERN = re.compile(
    r"""(?ix)
    (?P<path>
        (?<![\w:/.\-])
        (?=
            [^\r\n,;:)\]}]*
            (?:private|clinical|subjects?|participants?|patients?|sub-[A-Za-z0-9]+)
            [\\/]
        )
        (?:
            \.{1,2}[\\/]
            |
            [A-Za-z0-9._-]+[\\/]
        )
        [^\r\n,;:)\]}]*?
        \."""
    + _PRIVATE_FILE_EXTENSION_PATTERN
    + r"""
    )
    (?=$|[\s,;:.)\]}!?])
    """,
    re.IGNORECASE | re.VERBOSE,
)
_RELATIVE_FILE_PATH_PATTERN = re.compile(
    r"""(?ix)
    (?P<path>
        (?<![\w:/.\-])
        (?:\.{1,2}[\\/])?
        [A-Z0-9._~-]+[\\/]
        [^\r\n,;:)\]}]*?
        \."""
    + _PRIVATE_FILE_EXTENSION_PATTERN
    + r"""
    )
    (?=$|[\s,;:.)\]}!?])
    """
)
_RELATIVE_PRIVATE_DIRECTORY_START_PATTERN = re.compile(
    r"""(?ix)
    (?<![\w:/.\-])
    (?:\.{1,2}[\\/])?
    (?:[A-Z0-9._~-]+[\\/])*
    (?:
        private
        |
        clinical(?:[\s_-]+records?)?
        |
        subjects?
        |
        participants?
        |
        patients?
        |
        sub-[A-Z0-9]+
    )
    [\\/]
    """
)
_PATH_PROSE_BOUNDARIES = (
    " because ",
    " after ",
    " before ",
    " while ",
    " when ",
    " but ",
    " therefore ",
    " so that ",
    " is unavailable",
    " was rejected",
    " encountered ",
)
_FILE_URI_PATTERN = re.compile(
    r"""(?ix)
    (?P<uri>
        (?<![\w])
        file://
        (?:[A-Z0-9._~-]+)?
        /
        [^"'`\r\n,;)\]}]*?
        \."""
    + _PRIVATE_FILE_EXTENSION_PATTERN
    + r""")
    (?P<trailing>[.!?]?)
    (?=$|[\s,;:)\]}!?'"`])
    """
)
_ENV_PATH_PATTERN = re.compile(
    r"""(?ix)
    (?P<path>
        (?:
            \$HOME
            |
            %USERPROFILE%
        )
        [\\/][^\s,;:)\]}]+
    )
    """,
)
_UNC_PATH_PATTERN = re.compile(
    r"(?P<path>(?<![\w:])(?:\\\\|//)[^\\/\s,;]+[\\/][^\s,;)\]}]+)"
)
_WINDOWS_PATH_PATTERN = re.compile(r"(?P<path>(?<![\w])(?:[A-Za-z]:[\\/])[^\s,;)\]}]+)")
_POSIX_PATH_PATTERN = re.compile(r"(?P<path>(?<![\w:/])/(?!/)[^\s,;:)\]}]+)")
_IDENTITY_INTERNAL_PERIOD_FRAGMENT = (
    r"(?:(?i:\b(?:dr|jr|mr|mrs|ms|mx|prof|sr|st)\.)|"
    r"(?:\b[^\W\d_]\.))(?=\s+\S)"
)
_QUOTED_IDENTITY_ASSIGNMENT_PATTERN = re.compile(
    rf"""(?ix)
    \b(?P<label>{_IDENTITY_LABEL})
    (?P<separator>\s*(?:=|:)\s*)
    (?P<quote>["'])
    (?P<identifier>(?:\\.|(?!(?P=quote))[^\r\n])+)
    (?P=quote)
    """
)
_IDENTITY_ASSIGNMENT_PATTERN = re.compile(
    rf"""(?x)
    \b(?P<label>(?i:{_IDENTITY_LABEL}))
    (?P<separator>\s*(?:=|:)\s*)
    (?!["'])
    (?P<identifier>
        (?:
            """
    + _IDENTITY_INTERNAL_PERIOD_FRAGMENT
    + r"""
            |
            \.(?!\s+\S)
            |
            [^\r\n;.!?\u3002\uFF01\uFF1F]
        )+?
    )
    (?=
        ;
        |
        \r?\n
        |
        $
        |
        [.!?](?=\s+\S|\s*$)
        |
        [\u3002\uFF01\uFF1F](?=\s*\S|\s*$)
    )
    """
)
_IDENTITY_COMMA_ACTION_PATTERN = re.compile(
    r"""(?ix)
    (?P<separator>,\s*)
    (?P<action>
        retry\b
        | choose\b
        | select\b
        | continue\b
        | review\b
        | update\b
        | open\b
        | fix\b
    )
    .*\Z
    """
)
_IDENTITY_STATUS_ACTION_PATTERN = re.compile(
    r"""(?ix)
    (?P<separator>\s+)
    (?P<action>
        failed\s+validation\b
        | was\s+rejected\b
        | loaded\s+successfully\b
        | is\s+invalid\b
        | is\s+missing\b
    )
    .*\Z
    """
)
_IDENTITY_CJK_ACTION_PATTERN = re.compile(
    r"""(?ix)
    (?P<separator>\uFF0C\s*)
    (?P<action>
        \u8acb
        | \u8bf7
        | \u91cd\u65b0
        | \u9078\u64c7
        | \u9009\u62e9
        | \u91cd\u8a66
        | \u91cd\u8bd5
        | \u6aa2\u67e5
        | \u68c0\u67e5
        | \u7e7c\u7e8c
        | \u7ee7\u7eed
    )
    .*\Z
    """
)
_NATURAL_IDENTITY_STATUS_PATTERN = re.compile(
    rf"""(?ix)
    \b(?P<label>{_IDENTITY_LABEL})
    (?P<label_separator>\s+)
    (?P<identifier>[^\r\n;.!?\u3002\uFF01\uFF1F]{{1,160}}?)
    (?P<action_separator>\s+)
    (?P<action>
        failed\s+(?:preprocessing|pre-processing|validation|import|loading)\b
        |
        was\s+rejected\b
        |
        was\s+accepted\b
        |
        was\s+completed\b
        |
        completed\s+(?:preprocessing|pre-processing|validation|import|loading)\b
        |
        (?:loaded|imported|processed)\s+successfully\b
        |
        was\s+successful\b
        |
        encountered\s+an?\s+(?:import|loading|validation)\s+error\b
    )
    """
)
_NATURAL_IDENTITY_FAILURE_PREFIX_PATTERN = re.compile(
    rf"""(?ix)
    (?P<prefix>
        could\s+not\s+(?:load|import|process)\s+
        |
        failed\s+to\s+(?:load|import|process)\s+
        |
        training\s+failed\s+for\s+
    )
    (?P<label>{_IDENTITY_LABEL})
    (?P<label_separator>\s+)
    (?P<identifier>[^\r\n;.!?\u3002\uFF01\uFF1F]{{1,160}}?)
    (?=$|[;.!?\u3002\uFF01\uFF1F])
    """
)
_NATURAL_IDENTITY_CONTEXT_PATTERN = re.compile(
    rf"""(?ix)
    \b(?P<label>{_IDENTITY_LABEL})
    (?P<label_separator>\s+)
    (?P<identifier>[^\r\n;.!?\u3002\uFF01\uFF1F]{{1,160}}?)
    (?P<context_separator>\s+)
    (?P<context>at|because|from|in|during)
    (?=\s+\S)
    """
)
_NATURAL_IDENTITY_TERMINAL_PATTERN = re.compile(
    rf"""(?ix)
    \b(?P<label>{_IDENTITY_LABEL})
    (?P<label_separator>\s+)
    (?P<identifier>[^\r\n;.!?\u3002\uFF01\uFF1F]{{1,160}}?)
    (?=$|[;.!?\u3002\uFF01\uFF1F])
    """
)
_NATURAL_CJK_IDENTITY_STATUS_PATTERN = re.compile(
    rf"""(?x)
    (?P<label>{_CJK_IDENTITY_LABEL})
    (?P<identifier>[\u3400-\u9fff]{{2,6}}?)
    (?P<action>
        前處理失敗
        |
        前处理失败
        |
        預處理失敗
        |
        预处理失败
        |
        失敗
        |
        失败
        |
        已完成(?:匯入|导入|載入|加载|前處理|前处理|預處理|预处理)
        |
        已接受
        |
        匯入成功
        |
        导入成功
        |
        載入成功
        |
        加载成功
        |
        發生(?:匯入|載入|前處理|預處理)錯誤
        |
        发生(?:导入|加载|前处理|预处理)错误
        |
        無法完成(?:匯入|載入|前處理|預處理)
        |
        无法完成(?:导入|加载|前处理|预处理)
    )
    """
)
_NATURAL_CJK_IDENTITY_FAILURE_PREFIX_PATTERN = re.compile(
    rf"""(?x)
    (?P<prefix>
        無法(?:匯入|載入|完成|處理)
        |
        无法(?:导入|加载|完成|处理)
    )
    (?P<label>{_CJK_IDENTITY_LABEL})
    (?P<identifier>[\u3400-\u9fff]{{2,6}})
    """
)
_NATURAL_CJK_IDENTITY_CONTEXT_PATTERN = re.compile(
    rf"""(?x)
    (?P<label>{_CJK_IDENTITY_LABEL})
    (?P<identifier>[\u3400-\u9fff]{{2,6}}?)
    (?P<context>因為|因为|於|于|在|從|从)
    """
)
_NON_IDENTITY_INSTRUCTION_PATTERN = re.compile(
    r"""(?ix)^
    (?:choose|click|close|continue|fix|move|open|press|reset|retry|review|
    select|update|use)\b
    """
)
_BIDS_SUBJECT_PATTERN = re.compile(
    r"(?i)(?<![A-Za-z0-9])sub-(?P<identifier>[A-Za-z0-9]+)"
)
_PREFIXED_IDENTITY_PATTERN = re.compile(
    r"(?i)\b(?P<label>subject|participant|patient|client)"
    r"(?P<separator>[-_])(?!(?:ids?|ref)\b)(?P<identifier>[A-Za-z0-9]+)"
)
_NON_IDENTITY_PREFIX_TOKENS = frozenset(
    {
        "based",
        "centered",
        "centred",
        "dependent",
        "facing",
        "focused",
        "grouped",
        "independent",
        "level",
        "matched",
        "matter",
        "oriented",
        "reported",
        "related",
        "specific",
        "specificity",
        "stratified",
        "wise",
    }
)
_NON_IDENTITY_ASSIGNMENT_TOKENS = frozenset(
    {
        "missing",
        "n/a",
        "none",
        "not set",
        "not-set",
        "optional",
        "required",
        "unknown",
        "unavailable",
        "unset",
    }
)
_NON_IDENTITY_NATURAL_CJK_TOKENS = frozenset(
    {
        "\u8cc7\u6599",
        "\u6570\u636e",
        "\u8a18\u9304",
        "\u8bb0\u5f55",
        "\u6b04\u4f4d",
        "\u5b57\u6bb5",
        "\u5c0d\u6620",
        "\u6620\u5c04",
        "\u6d41\u7a0b",
    }
)
_NON_IDENTITY_BIDS_TOKENS = frozenset(
    {
        "band",
        "bands",
        "gaussian",
        "harmonic",
        "nyquist",
        "sample",
        "second",
        "sampling",
        "threshold",
        "thresholds",
    }
)
_NON_IDENTITY_BIDS_UNIT_PATTERN = re.compile(r"(?i)^\d+(?:\.\d+)?(?:hz|khz|ms|s)$")
_SUBJECT_REFERENCE_PATTERN = re.compile(r"^\[SUBJECT_REF:[0-9a-f]{12}\]$")
_SUBJECT_REFERENCE_SEARCH_PATTERN = re.compile(r"\[SUBJECT_REF:[0-9a-f]{12}\]")
_PUBLIC_PATH_REFERENCE_PATTERN = re.compile(
    r"^(?P<display>.+) \[REDACTED_PATH\] "
    r"\[PATH_REF:(?P<reference>[0-9a-f]{12}):(?P<signature>[0-9a-f]{12})\]$"
)


def public_diagnostic_text(
    value: object,
    *,
    disclosure: DiagnosticDisclosure = DiagnosticDisclosure.PUBLIC,
    layout: DiagnosticTextLayout = DiagnosticTextLayout.PRESERVE_LINES,
) -> str:
    """Render diagnostic text without default private-data disclosure."""
    mode = _require_disclosure(disclosure)
    text_layout = _require_layout(layout)
    text = _remove_control_characters(
        _truncate_text_to_bytes(
            _diagnostic_text_input(value),
            PUBLIC_DIAGNOSTIC_MAX_INPUT_BYTES,
        ),
        layout=DiagnosticTextLayout.PRESERVE_LINES,
    )
    text = _redact_percent_encoded_sensitive_text(text, disclosure=mode)
    text = _redact_secrets(text)
    text = _redact_email_identities(text)
    if mode is DiagnosticDisclosure.PUBLIC:
        text = _redact_paths(text)
        text = _redact_subject_identifiers(text)
    rendered = _remove_control_characters(text, layout=text_layout)
    return _truncate_text_to_bytes(rendered, PUBLIC_DIAGNOSTIC_MAX_INPUT_BYTES)


def public_diagnostic_value(
    value: Any,
    *,
    field_name: str | None = None,
    disclosure: DiagnosticDisclosure = DiagnosticDisclosure.PUBLIC,
) -> Any:
    """Recursively project structured diagnostics onto the disclosure boundary."""
    mode = _require_disclosure(disclosure)
    from XBrainLab.backend.utils.public_diagnostic_projection import (  # noqa: PLC0415
        project_public_diagnostic_value,
    )

    return project_public_diagnostic_value(
        value,
        field_name=field_name,
        disclosure=mode,
    )


def _require_disclosure(value: DiagnosticDisclosure) -> DiagnosticDisclosure:
    if type(value) is not DiagnosticDisclosure:
        raise TypeError("Diagnostic disclosure must be an explicit enum value.")
    return value


def _require_layout(value: DiagnosticTextLayout) -> DiagnosticTextLayout:
    if type(value) is not DiagnosticTextLayout:
        raise TypeError("Diagnostic text layout must be an explicit enum value.")
    return value


def _redact_percent_encoded_sensitive_text(
    text: str,
    *,
    disclosure: DiagnosticDisclosure,
) -> str:
    if _PERCENT_ESCAPE_PATTERN.search(text) is None:
        return text

    def replace(match: re.Match[str]) -> str:
        return _redact_percent_encoded_candidate(
            match.group("encoded"),
            disclosure=disclosure,
        )

    text = _PERCENT_ENCODED_LABEL_ASSIGNMENT_PATTERN.sub(replace, text)
    return _PERCENT_ENCODED_CANDIDATE_PATTERN.sub(replace, text)


def _redact_percent_encoded_candidate(
    encoded: str,
    *,
    disclosure: DiagnosticDisclosure,
) -> str:
    if _PERCENT_ESCAPE_PATTERN.search(encoded) is None:
        return encoded
    decoded = _NESTED_PERCENT_ESCAPE_PATTERN.sub(
        lambda nested: f"%{nested.group('byte')}",
        encoded,
    )
    for _ in range(2):
        candidate = unquote(decoded)
        if candidate == decoded:
            break
        decoded = candidate
    decoded = _remove_control_characters(
        decoded,
        layout=DiagnosticTextLayout.PRESERVE_LINES,
    )

    redacted_secret = _redact_secrets(decoded)
    if redacted_secret != decoded:
        return redacted_secret
    redacted_email = _redact_email_identities(decoded)
    if redacted_email != decoded:
        return redacted_email
    if disclosure is DiagnosticDisclosure.DETAILED:
        return encoded
    redacted_path = _redact_paths(decoded)
    if redacted_path != decoded:
        return redacted_path
    redacted_identity = _redact_subject_identifiers(decoded)
    return redacted_identity if redacted_identity != decoded else encoded


def _redact_email_identities(text: str) -> str:
    """Redact ASCII, Unicode, and IDNA email identities without regex backtracking."""
    rendered: list[str] = []
    cursor = 0
    search_from = 0
    while True:
        at_index = text.find("@", search_from)
        if at_index < 0:
            rendered.append(text[cursor:])
            return "".join(rendered)

        quoted_start = _quoted_email_local_start(text, cursor, at_index)
        if quoted_start is not None:
            start = quoted_start
        else:
            start = at_index
            while start > cursor and _is_email_local_character(text[start - 1]):
                start -= 1

        end = at_index + 1
        if end < len(text) and text[end] == "[":
            literal_end = text.find("]", end + 1)
            if literal_end >= 0:
                end = literal_end + 1
        else:
            while end < len(text) and _is_email_domain_character(text[end]):
                end += 1
            while end > at_index + 1 and text[end - 1] == ".":
                end -= 1

        candidate = text[start:end]
        if _is_email_identity(candidate):
            rendered.append(text[cursor:start])
            rendered.append(REDACTED_EMAIL_MARKER)
            cursor = end
            search_from = end
            continue
        search_from = at_index + 1


def _quoted_email_local_start(text: str, lower_bound: int, at_index: int) -> int | None:
    if at_index <= lower_bound or text[at_index - 1] != '"':
        return None
    index = at_index - 2
    while index >= lower_bound:
        if text[index] != '"':
            index -= 1
            continue
        preceding_backslashes = 0
        lookbehind = index - 1
        while lookbehind >= lower_bound and text[lookbehind] == "\\":
            preceding_backslashes += 1
            lookbehind -= 1
        if preceding_backslashes % 2 == 0:
            return index
        index = lookbehind
    return None


def _is_email_local_character(character: str) -> bool:
    return bool(
        character in "._%+-" or unicodedata.category(character)[:1] in {"L", "M", "N"}
    )


def _is_email_domain_character(character: str) -> bool:
    return bool(
        character in ".-" or unicodedata.category(character)[:1] in {"L", "M", "N"}
    )


def _is_email_identity(candidate: str) -> bool:
    if candidate.count("@") != 1:
        return False
    local, domain = candidate.split("@", maxsplit=1)
    if not _is_valid_email_local_part(local) or len(domain) > 253:
        return False
    if domain.startswith("[") and domain.endswith("]"):
        address = domain[1:-1]
        if address.casefold().startswith("ipv6:"):
            address = address[5:]
        try:
            ipaddress.ip_address(address)
        except ValueError:
            return False
        return True
    labels = domain.split(".")
    if len(labels) < 2 or any(
        not label or label.startswith("-") or label.endswith("-") for label in labels
    ):
        return False
    final_label = labels[-1]
    if not (
        final_label.casefold().startswith("xn--")
        or (
            len(final_label) >= 2
            and all(
                unicodedata.category(character)[:1] in {"L", "M"}
                for character in final_label
            )
        )
    ):
        return False
    try:
        domain.encode("idna")
    except UnicodeError:
        return False
    return True


def _is_valid_email_local_part(local: str) -> bool:
    if not 1 <= len(local) <= 128:
        return False
    if local.startswith('"') and local.endswith('"'):
        inner = local[1:-1]
        if not inner:
            return False
        escaped = False
        for character in inner:
            if escaped:
                escaped = False
                continue
            if character == "\\":
                escaped = True
                continue
            if character in "\r\n" or unicodedata.category(character) in {
                "Cc",
                "Cs",
            }:
                return False
        return not escaped
    return not (
        local.startswith(".")
        or local.endswith(".")
        or ".." in local
        or any(not _is_email_local_character(character) for character in local)
    )


def _redact_secrets(text: str) -> str:
    text = _redact_private_key_blocks(text)
    text = _redact_multiline_secret_assignments(text)
    text = _URL_USERINFO_PATTERN.sub(
        lambda match: f"{match.group('scheme')}{REDACTED_SECRET_MARKER}@",
        text,
    )
    text = _AWS_AUTH_PATTERN.sub(
        lambda match: (
            f"{match.group('prefix') or ''}AWS4-HMAC-SHA256 {REDACTED_SECRET_MARKER}"
        ),
        text,
    )
    text = _DIGEST_AUTH_PATTERN.sub(_replace_digest_auth, text)
    text = _CLI_SECRET_OPTION_PATTERN.sub(REDACTED_SECRET_MARKER, text)
    text = _ENV_SECRET_SPACE_PATTERN.sub(REDACTED_SECRET_MARKER, text)
    text = _JSON_SECRET_ASSIGNMENT_PATTERN.sub(REDACTED_SECRET_MARKER, text)
    text = _SECRET_ASSIGNMENT_PATTERN.sub(REDACTED_SECRET_MARKER, text)
    text = _BEARER_SECRET_PATTERN.sub(REDACTED_SECRET_MARKER, text)
    return _TOKEN_LITERAL_PATTERN.sub(REDACTED_SECRET_MARKER, text)


def _redact_private_key_blocks(text: str) -> str:
    lines = text.splitlines(keepends=True)
    rendered: list[str] = []
    index = 0
    while index < len(lines):
        body, newline = _split_line_ending(lines[index])
        label = _private_key_pem_label(body)
        if label is None:
            rendered.append(lines[index])
            index += 1
            continue
        rendered.append(f"{REDACTED_SECRET_MARKER}{newline}")
        index += 1
        while index < len(lines):
            candidate, _candidate_newline = _split_line_ending(lines[index])
            index += 1
            if candidate.strip() == f"-----END {label}-----":
                break
    return "".join(rendered)


def _private_key_pem_label(value: str) -> str | None:
    stripped = value.strip()
    prefix = "-----BEGIN "
    suffix = "-----"
    if not stripped.startswith(prefix) or not stripped.endswith(suffix):
        return None
    label = stripped[len(prefix) : -len(suffix)]
    if label == "PRIVATE KEY" or label.endswith(" PRIVATE KEY"):
        return label
    return None


def _redact_multiline_secret_assignments(text: str) -> str:
    lines = text.splitlines(keepends=True)
    rendered: list[str] = []
    index = 0
    while index < len(lines):
        body, newline = _split_line_ending(lines[index])
        match = _MULTILINE_SECRET_HEADER_PATTERN.search(body)
        if match is None:
            rendered.append(lines[index])
            index += 1
            continue

        rendered.append(f"{body[: match.start()]}{REDACTED_SECRET_MARKER}{newline}")
        assignment_indent = _leading_whitespace_width(body)
        index += 1
        if index >= len(lines):
            continue

        next_body, _next_newline = _split_line_ending(lines[index])
        continuation_is_indented = (
            bool(next_body.strip())
            and _leading_whitespace_width(next_body) > assignment_indent
        )
        while index < len(lines):
            candidate, candidate_newline = _split_line_ending(lines[index])
            if continuation_is_indented and (
                not candidate.strip()
                or _leading_whitespace_width(candidate) > assignment_indent
            ):
                rendered.append(candidate_newline)
                index += 1
                continue
            if not continuation_is_indented:
                rendered.append(candidate_newline)
                index += 1
            break
    return "".join(rendered)


def _split_line_ending(value: str) -> tuple[str, str]:
    body = value.rstrip("\r\n")
    return body, value[len(body) :]


def _leading_whitespace_width(value: str) -> int:
    return len(value) - len(value.lstrip(" \t"))


def _replace_digest_auth(match: re.Match[str]) -> str:
    if (
        match.group("prefix") is None
        and _DIGEST_CREDENTIAL_PARAMETER_PATTERN.search(match.group(0)) is None
    ):
        return match.group(0)
    return f"{match.group('prefix') or ''}Digest {REDACTED_SECRET_MARKER}"


def _redact_paths(text: str) -> str:
    text = _FILE_URI_PATTERN.sub(_replace_file_uri, text)
    for pattern in _QUOTED_PATH_PATTERNS:
        text = pattern.sub(_replace_quoted_path, text)
    text = _UNQUOTED_PRIVATE_FILE_PATH_PATTERN.sub(_replace_path_match, text)
    text = _RELATIVE_PRIVATE_FILE_PATH_PATTERN.sub(_replace_path_match, text)
    text = _RELATIVE_FILE_PATH_PATTERN.sub(_replace_path_match, text)
    text = _redact_unquoted_relative_private_directories(text)
    text = _redact_unquoted_absolute_paths(text)
    for pattern in (
        _ENV_PATH_PATTERN,
        _UNC_PATH_PATTERN,
        _WINDOWS_PATH_PATTERN,
        _POSIX_PATH_PATTERN,
    ):
        text = pattern.sub(_replace_path_match, text)
    return text


def _redact_unquoted_relative_private_directories(text: str) -> str:
    """Redact high-confidence private relative directories without an extension."""
    rendered: list[str] = []
    cursor = 0
    while True:
        match = _RELATIVE_PRIVATE_DIRECTORY_START_PATTERN.search(text, cursor)
        if match is None:
            rendered.append(text[cursor:])
            return "".join(rendered)
        start = match.start()
        end = _unquoted_path_end(text, start)
        path = text[start:end].rstrip(" \t")
        if not path:
            rendered.append(text[cursor : match.end()])
            cursor = match.end()
            continue
        rendered.append(text[cursor:start])
        rendered.append(_path_reference(path, force=True))
        cursor = start + len(path)


def _redact_unquoted_absolute_paths(text: str) -> str:
    """Redact unquoted absolute paths while retaining following recovery prose."""
    rendered: list[str] = []
    cursor = 0
    while True:
        start = _next_unquoted_path_start(text, cursor)
        if start is None:
            rendered.append(text[cursor:])
            return "".join(rendered)
        end = _unquoted_path_end(text, start)
        path = text[start:end].rstrip(" \t")
        if not path or _is_public_slash_command(path):
            rendered.append(text[cursor : start + 1])
            cursor = start + 1
            continue
        rendered.append(text[cursor:start])
        rendered.append(_path_reference(path, force=True))
        cursor = start + len(path)


def _next_unquoted_path_start(text: str, offset: int) -> int | None:
    for index in range(offset, len(text)):
        if _is_unquoted_path_start(text, index):
            return index
    return None


def _is_unquoted_path_start(text: str, index: int) -> bool:
    previous = text[index - 1] if index else ""
    remaining = text[index:]
    uri_prefix = next(
        (
            prefix
            for prefix in _PRIVATE_URI_PREFIXES
            if remaining[: len(prefix)].casefold() == prefix
        ),
        None,
    )
    if uri_prefix is not None:
        authority_and_path = remaining[len(uri_prefix) :]
        separator = min(
            (
                position
                for position in (
                    authority_and_path.find("/"),
                    authority_and_path.find("\\"),
                )
                if position >= 0
            ),
            default=-1,
        )
        return bool(
            separator >= 0
            and (not previous or not (previous.isalnum() or previous == "_"))
        )
    if remaining.startswith(("$HOME/", "$HOME\\", "%USERPROFILE%/", "%USERPROFILE%\\")):
        return not previous or not (previous.isalnum() or previous == "_")
    if (
        remaining[:1].isalpha()
        and len(remaining) >= 3
        and remaining[1] == ":"
        and remaining[2] in "\\/"
    ):
        return not previous or not (previous.isalnum() or previous == "_")
    if remaining.startswith(("\\\\", "//")):
        return not previous or previous != ":"
    if remaining.startswith("/") and not remaining.startswith("//"):
        return not previous or not (previous.isalnum() or previous in ":/")
    return False


def _unquoted_path_end(text: str, start: int) -> int:
    hard_end = len(text)
    for index in range(start + 1, len(text)):
        character = text[index]
        if character in "\r\n,;)]}":
            if (
                character == "]"
                and text[
                    max(start, index - len(REDACTED_SECRET_MARKER) + 1) : index + 1
                ]
                == REDACTED_SECRET_MARKER
            ):
                continue
            hard_end = index
            break
        if character in ".!?" and (index + 1 == len(text) or text[index + 1].isspace()):
            hard_end = index
            break

    candidate = text[start:hard_end]
    folded = candidate.casefold()
    # Favor privacy when a path component itself contains prose-like words. The
    # first recovery boundary after the final separator is safe unless another
    # prose-like token follows without an intervening sentence boundary.
    last_separator = max(candidate.rfind("/"), candidate.rfind("\\"))
    prose_boundary_positions: set[int] = set()
    for boundary in _PATH_PROSE_BOUNDARIES:
        search_from = last_separator + 1
        while (index := folded.find(boundary, search_from)) > last_separator:
            prose_boundary_positions.add(index)
            search_from = index + len(boundary)
    prose_boundaries = sorted(prose_boundary_positions)
    prose_end = len(candidate)
    for position, boundary_index in enumerate(prose_boundaries):
        later_boundary = (
            prose_boundaries[position + 1]
            if position + 1 < len(prose_boundaries)
            else None
        )
        if later_boundary is None:
            prose_end = boundary_index
            break
        between = candidate[boundary_index:later_boundary]
        if any(character in between for character in ".!?\u3002\uff01\uff1f"):
            prose_end = boundary_index
            break
    return start + prose_end


def _replace_quoted_path(match: re.Match[str]) -> str:
    quote = match.group("quote")
    if _is_public_slash_command(match.group("path")):
        return match.group(0)
    return f"{quote}{_path_reference(match.group('path'))}{quote}"


def _replace_file_uri(match: re.Match[str]) -> str:
    return f"{_path_reference(match.group('uri'), force=True)}{match.group('trailing')}"


def _replace_path_match(match: re.Match[str]) -> str:
    path, trailing = _split_trailing_punctuation(match.group("path"))
    if _is_public_slash_command(path):
        return f"{path}{trailing}"
    return f"{_path_reference(path, force=True)}{trailing}"


def _split_trailing_punctuation(value: str) -> tuple[str, str]:
    trailing = ""
    while value.endswith((".", "!", "?")):
        value, last = value[:-1], value[-1]
        trailing = f"{last}{trailing}"
    return value, trailing


def _path_reference(
    value: str,
    *,
    disclosure: DiagnosticDisclosure = DiagnosticDisclosure.PUBLIC,
    force: bool = False,
) -> str:
    if disclosure is DiagnosticDisclosure.DETAILED:
        return public_diagnostic_text(value, disclosure=disclosure)
    if _is_authenticated_path_reference(value):
        return value
    if not force and not _looks_like_private_path(value):
        return _redact_subject_identifiers(value)
    normalized = value.replace("\\", "/").rstrip("/")
    basename = normalized.rsplit("/", maxsplit=1)[-1] if normalized else ""
    display = _public_path_display(basename)
    subject_reference = _path_subject_reference(value)
    if subject_reference is not None:
        display = f"{display} {subject_reference}"
    reference = _private_reference(value, namespace="path")
    signature = _path_reference_signature(display, reference)
    return f"{display} {REDACTED_PATH_MARKER} [PATH_REF:{reference}:{signature}]"


def _looks_like_private_path(value: str) -> bool:
    candidate = value.strip()
    folded = candidate.casefold()
    return bool(
        candidate.startswith(("/", "\\\\", "//", "$HOME/", "$HOME\\"))
        or candidate.upper().startswith("%USERPROFILE%")
        or re.match(r"^[A-Za-z]:[\\/]", candidate)
        or folded.startswith(_PRIVATE_URI_PREFIXES)
    )


def _looks_like_relative_file_path(value: str) -> bool:
    candidate = value.strip()
    return bool(_RELATIVE_FILE_PATH_PATTERN.fullmatch(candidate))


def _looks_like_file_basename(value: str) -> bool:
    return bool(_PRIVATE_FILE_BASENAME_PATTERN.fullmatch(value))


def _public_path_display(basename: str) -> str:
    if not basename:
        return "private location"
    normalized = basename.casefold()
    if (
        unquote(basename) == basename
        and _public_basename_text(basename) == basename
        and normalized in _SAFE_PUBLIC_PATH_BASENAMES
    ):
        return normalized
    if _looks_like_file_basename(basename):
        extension = basename.rsplit(".", maxsplit=1)[-1].casefold()
        return f"file (.{extension})"
    return "private location"


def _is_public_slash_command(value: str) -> bool:
    return value.casefold() in _PUBLIC_SLASH_COMMANDS


def _path_subject_reference(value: str) -> str | None:
    redacted = _redact_subject_identifiers(unquote(value))
    match = _SUBJECT_REFERENCE_SEARCH_PATTERN.search(redacted)
    return match.group(0) if match is not None else None


def _redact_subject_identifiers(text: str) -> str:
    text = _NATURAL_IDENTITY_FAILURE_PREFIX_PATTERN.sub(
        _replace_natural_identity_failure_prefix,
        text,
    )
    text = _NATURAL_CJK_IDENTITY_FAILURE_PREFIX_PATTERN.sub(
        _replace_natural_cjk_identity_failure_prefix,
        text,
    )
    text = _NATURAL_IDENTITY_CONTEXT_PATTERN.sub(
        _replace_natural_identity_context,
        text,
    )
    text = _NATURAL_CJK_IDENTITY_CONTEXT_PATTERN.sub(
        _replace_natural_cjk_identity_context,
        text,
    )
    text = _NATURAL_IDENTITY_STATUS_PATTERN.sub(
        _replace_natural_identity_status,
        text,
    )
    text = _NATURAL_IDENTITY_TERMINAL_PATTERN.sub(
        _replace_natural_identity_terminal,
        text,
    )
    text = _NATURAL_CJK_IDENTITY_STATUS_PATTERN.sub(
        _replace_natural_cjk_identity_status,
        text,
    )
    text = _QUOTED_IDENTITY_ASSIGNMENT_PATTERN.sub(
        _replace_quoted_identity,
        text,
    )
    text = _IDENTITY_ASSIGNMENT_PATTERN.sub(_replace_assigned_identity, text)
    text = _BIDS_SUBJECT_PATTERN.sub(_replace_bids_subject, text)
    return _PREFIXED_IDENTITY_PATTERN.sub(_replace_prefixed_identity, text)


def _replace_natural_identity_failure_prefix(match: re.Match[str]) -> str:
    identifier = match.group("identifier").strip()
    if not _is_narrow_natural_identity(identifier):
        return match.group(0)
    reference = _private_reference(identifier, namespace="subject")
    return (
        f"{match.group('prefix')}{match.group('label')}"
        f"{match.group('label_separator')}[SUBJECT_REF:{reference}]"
    )


def _replace_natural_cjk_identity_failure_prefix(match: re.Match[str]) -> str:
    identifier = match.group("identifier")
    if identifier in _NON_IDENTITY_NATURAL_CJK_TOKENS:
        return match.group(0)
    reference = _private_reference(identifier, namespace="subject")
    return f"{match.group('prefix')}{match.group('label')}[SUBJECT_REF:{reference}]"


def _replace_natural_identity_context(match: re.Match[str]) -> str:
    identifier = match.group("identifier").strip()
    if not _is_narrow_natural_identity(identifier) or _is_subject_reference(identifier):
        return match.group(0)
    reference = _private_reference(identifier, namespace="subject")
    return (
        f"{match.group('label')}{match.group('label_separator')}"
        f"[SUBJECT_REF:{reference}]{match.group('context_separator')}"
        f"{match.group('context')}"
    )


def _replace_natural_cjk_identity_context(match: re.Match[str]) -> str:
    identifier = match.group("identifier")
    if identifier in _NON_IDENTITY_NATURAL_CJK_TOKENS:
        return match.group(0)
    reference = _private_reference(identifier, namespace="subject")
    return f"{match.group('label')}[SUBJECT_REF:{reference}]{match.group('context')}"


def _replace_natural_identity_status(match: re.Match[str]) -> str:
    identifier = match.group("identifier").strip()
    if not _is_narrow_natural_identity(identifier):
        return match.group(0)
    reference = _private_reference(identifier, namespace="subject")
    return (
        f"{match.group('label')}{match.group('label_separator')}"
        f"[SUBJECT_REF:{reference}]{match.group('action_separator')}"
        f"{match.group('action')}"
    )


def _replace_natural_identity_terminal(match: re.Match[str]) -> str:
    identifier = match.group("identifier").strip()
    if not _is_narrow_natural_identity(identifier) or _is_subject_reference(identifier):
        return match.group(0)
    reference = _private_reference(identifier, namespace="subject")
    return (
        f"{match.group('label')}{match.group('label_separator')}"
        f"[SUBJECT_REF:{reference}]"
    )


def _replace_natural_cjk_identity_status(match: re.Match[str]) -> str:
    identifier = match.group("identifier")
    if identifier in _NON_IDENTITY_NATURAL_CJK_TOKENS:
        return match.group(0)
    reference = _private_reference(identifier, namespace="subject")
    return f"{match.group('label')}[SUBJECT_REF:{reference}]{match.group('action')}"


def _is_narrow_natural_identity(value: str) -> bool:
    words = value.split()
    if not 1 <= len(words) <= 6:
        return False
    if len(words) == 1:
        return bool(
            any(character.isdigit() or character.isupper() for character in value)
            or _is_compact_non_ascii_identity(value)
        )
    connectors = {"da", "de", "del", "der", "di", "la", "van", "von"}
    title_cased = all(
        word.casefold() in connectors
        or next(
            (character.isupper() for character in word if character.isalpha()),
            False,
        )
        for word in words
    )
    return title_cased or _is_lowercase_multilingual_identity(words)


def _is_lowercase_multilingual_identity(words: list[str]) -> bool:
    if not any(ord(character) > 127 for word in words for character in word):
        return False
    return all(
        word
        and all(
            unicodedata.category(character)[:1] in {"L", "M"}
            or character in {"-", "'", "\u2019"}
            for character in word
        )
        for word in words
    )


def _is_compact_non_ascii_identity(value: str) -> bool:
    characters = [
        character
        for character in value
        if unicodedata.category(character)[:1] in {"L", "M"}
    ]
    return bool(
        2 <= len(characters) <= 32
        and any(ord(character) > 127 for character in characters)
        and all(
            unicodedata.category(character)[:1] in {"L", "M"}
            or character in {"-", "'", "\u2019"}
            for character in value
        )
    )


def _replace_quoted_identity(match: re.Match[str]) -> str:
    if _is_non_identity_assignment(match.group("identifier")) or _is_subject_reference(
        match.group("identifier")
    ):
        return match.group(0)
    reference = _private_reference(match.group("identifier"), namespace="subject")
    return (
        f"{match.group('label')}{match.group('separator')}"
        f"{match.group('quote')}[SUBJECT_REF:{reference}]{match.group('quote')}"
    )


def _replace_assigned_identity(match: re.Match[str]) -> str:
    identifier, action = _split_identity_action(match.group("identifier"))
    identifier, trailing = _split_trailing_punctuation(identifier)
    if _is_non_identity_assignment(identifier) or _is_subject_reference(identifier):
        return match.group(0)
    reference = _private_reference(identifier, namespace="subject")
    return (
        f"{match.group('label')}{match.group('separator')}"
        f"[SUBJECT_REF:{reference}]{trailing}{action}"
    )


def _replace_bids_subject(match: re.Match[str]) -> str:
    identifier = match.group("identifier")
    if _is_non_identity_bids_token(
        identifier
    ) or not _is_high_confidence_prefixed_identity(match, label="sub"):
        return match.group(0)
    reference = _private_reference(identifier, namespace="subject")
    return f"sub-[SUBJECT_REF:{reference}]"


def _replace_prefixed_identity(match: re.Match[str]) -> str:
    if (
        match.group("identifier").casefold() in _NON_IDENTITY_PREFIX_TOKENS
        or not _is_high_confidence_prefixed_identity(
            match,
            label=match.group("label"),
        )
    ):
        return match.group(0)
    reference = _private_reference(match.group("identifier"), namespace="subject")
    return f"{match.group('label')}{match.group('separator')}[SUBJECT_REF:{reference}]"


def _is_non_identity_assignment(value: str) -> bool:
    normalized = re.sub(r"[\s._-]+", " ", value.strip()).strip().casefold()
    return bool(
        normalized in _NON_IDENTITY_ASSIGNMENT_TOKENS
        or _NON_IDENTITY_INSTRUCTION_PATTERN.match(normalized)
    )


def _is_high_confidence_prefixed_identity(
    match: re.Match[str],
    *,
    label: str,
) -> bool:
    identifier = match.group("identifier")
    if any(character.isdigit() or character.isupper() for character in identifier):
        return True
    text = match.string
    next_character = text[match.end() : match.end() + 1]
    if next_character == "_":
        return True
    if label.casefold() == "sub" and re.match(
        rf"^\.{_PRIVATE_FILE_EXTENSION_PATTERN}\b",
        text[match.end() :],
        flags=re.IGNORECASE,
    ):
        return True
    context = text[max(0, match.start() - 64) : match.start()].casefold()
    return label.casefold() == "sub" and "bids" in context


def _split_identity_action(value: str) -> tuple[str, str]:
    for pattern in (
        _IDENTITY_COMMA_ACTION_PATTERN,
        _IDENTITY_CJK_ACTION_PATTERN,
        _IDENTITY_STATUS_ACTION_PATTERN,
    ):
        match = pattern.search(value)
        if match is not None:
            return value[: match.start()], value[match.start() :]
    return value, ""


def _public_basename_text(value: str) -> str:
    text = _remove_control_characters(
        value,
        layout=DiagnosticTextLayout.SINGLE_LINE,
    )
    text = _redact_secrets(text)
    text = _redact_email_identities(text)
    text = _redact_subject_identifiers(text)
    return _remove_control_characters(
        text,
        layout=DiagnosticTextLayout.SINGLE_LINE,
    )


def _is_subject_reference(value: str) -> bool:
    return bool(_SUBJECT_REFERENCE_PATTERN.fullmatch(value.strip()))


def _is_non_identity_bids_token(value: str) -> bool:
    normalized = value.casefold()
    return bool(
        normalized in _NON_IDENTITY_BIDS_TOKENS
        or _NON_IDENTITY_BIDS_UNIT_PATTERN.fullmatch(normalized)
    )


def _normalized_field_name(value: object) -> str:
    text = _ANSI_ESCAPE_PATTERN.sub(
        "",
        _truncate_text_to_bytes(_diagnostic_text_input(value), 4096),
    )
    characters = [
        character
        for character in text
        if unicodedata.category(character) not in {"Cc", "Cf", "Cs"}
    ]
    return " ".join("".join(characters).split())


def _diagnostic_field_sensitivity(value: object) -> _DiagnosticFieldSensitivity:
    field_name = _normalized_field_name(value)
    normalized_key = "".join(
        character
        for character in unicodedata.normalize("NFKC", field_name).casefold()
        if character.isalnum()
    )
    if not normalized_key:
        return _DiagnosticFieldSensitivity.PUBLIC
    if _SECRET_KEY_PATTERN.fullmatch(field_name) or normalized_key.endswith(
        _NORMALIZED_SECRET_KEY_SUFFIXES
    ):
        return _DiagnosticFieldSensitivity.SECRET
    if _IDENTITY_KEY_PATTERN.fullmatch(field_name) or _is_normalized_identity_key(
        normalized_key
    ):
        return _DiagnosticFieldSensitivity.IDENTITY
    if (
        _PATH_KEY_PATTERN.fullmatch(field_name)
        or normalized_key in _NORMALIZED_PATH_KEYS
        or normalized_key.endswith(_NORMALIZED_PATH_SUFFIXES)
    ):
        return _DiagnosticFieldSensitivity.PATH
    return _DiagnosticFieldSensitivity.PUBLIC


def _is_normalized_identity_key(value: str) -> bool:
    for prefix in _NORMALIZED_IDENTITY_PREFIXES:
        if not value.startswith(prefix):
            continue
        suffix = value[len(prefix) :]
        if suffix in _NORMALIZED_IDENTITY_SUFFIXES or suffix.startswith("by"):
            return True
    return False


def _private_reference(value: object, *, namespace: str) -> str:
    safe_value = _truncate_text_to_bytes(_diagnostic_text_input(value), 4096)
    encoded = f"{namespace}\0{safe_value}".encode(
        "utf-8",
        errors="surrogatepass",
    )
    return hmac.new(_REFERENCE_KEY, encoded, hashlib.sha256).hexdigest()[:12]


def _path_reference_signature(display: str, reference: str) -> str:
    return _private_reference(f"{display}\0{reference}", namespace="path-marker")


def _is_authenticated_path_reference(value: str) -> bool:
    match = _PUBLIC_PATH_REFERENCE_PATTERN.fullmatch(value)
    if match is None:
        return False
    display = match.group("display")
    if not _is_safe_public_path_display(display):
        return False
    expected = _path_reference_signature(display, match.group("reference"))
    return hmac.compare_digest(expected, match.group("signature"))


def _is_safe_public_path_display(value: str) -> bool:
    base_display = value
    maybe_base, separator, maybe_reference = value.rpartition(" ")
    if separator and _SUBJECT_REFERENCE_PATTERN.fullmatch(maybe_reference):
        base_display = maybe_base
    if unquote(value) != value or _public_basename_text(value) != value:
        return False
    return bool(
        base_display == "private location"
        or base_display in _SAFE_PUBLIC_PATH_BASENAMES
        or _GENERIC_PUBLIC_PATH_DISPLAY_PATTERN.fullmatch(base_display)
    )


def _truncate_text_to_bytes(text: str, budget: int) -> str:
    if budget <= 0:
        return ""
    candidate = text if len(text) <= budget else text[:budget]
    encoded = candidate.encode("utf-8", errors="replace")
    if candidate is text and len(encoded) <= budget:
        return text
    marker = _TRUNCATED_INPUT_MARKER.encode("utf-8")
    if budget <= len(marker):
        return marker[:budget].decode("utf-8", errors="ignore")
    prefix = encoded[: budget - len(marker)].decode("utf-8", errors="ignore")
    return f"{prefix}{_TRUNCATED_INPUT_MARKER}"


def _diagnostic_text_input(value: object) -> str:
    if type(value) is str:
        return value
    if _has_exact_type(value, _SAFE_PATH_TYPES):
        return _pathlike_text(cast(os.PathLike[str] | os.PathLike[bytes], value))
    if value is None or _has_exact_type(value, _SAFE_PRIMITIVE_TYPES):
        rendered = _safe_primitive_text(
            cast(bool | int | float | None, value),
            max_bytes=_MAX_SAFE_PRIMITIVE_TEXT_BYTES,
        )
        return rendered or PUBLIC_DIAGNOSTIC_UNSUPPORTED_MARKER
    value_type = type(value)
    exception_name = _safe_builtin_exception_type_name(value_type)
    if exception_name is not None:
        args = cast(Any, BaseException.args).__get__(value, value_type)
        if type(args) is not tuple:
            return PUBLIC_DIAGNOSTIC_UNSUPPORTED_MARKER
        parts = [
            _truncate_text_to_bytes(_diagnostic_text_input(item), 4096)
            for item in args[:8]
        ]
        detail = ", ".join(parts)
        return f"{exception_name}: {detail}" if detail else exception_name
    return PUBLIC_DIAGNOSTIC_UNSUPPORTED_MARKER


def safe_exception_type_name(error: BaseException) -> str:
    """Return a bounded exception label without consulting the dynamic class."""
    exception_name = _safe_builtin_exception_type_name(type(error))
    return exception_name or "Exception"


def public_exception_message(
    error: BaseException,
    *,
    fallback: str = PUBLIC_DIAGNOSTIC_UNSUPPORTED_MARKER,
) -> str:
    """Return one sanitized built-in exception message or a fixed fallback."""
    value_type = type(error)
    if _safe_builtin_exception_type_name(value_type) is None:
        return fallback
    args = cast(Any, BaseException.args).__get__(error, value_type)
    if type(args) is not tuple or len(args) != 1 or type(args[0]) is not str:
        return fallback
    rendered = public_diagnostic_text(
        args[0],
        layout=DiagnosticTextLayout.SINGLE_LINE,
    )
    return rendered or fallback


def _safe_builtin_exception_type_name(value_type: type[object]) -> str | None:
    for safe_type, safe_name in _SAFE_BUILTIN_EXCEPTION_TYPES:
        if value_type is safe_type:
            return safe_name
    return None


def _has_exact_type(value: object, allowed_types: tuple[type[object], ...]) -> bool:
    value_type = type(value)
    return any(value_type is allowed_type for allowed_type in allowed_types)


def _safe_primitive_text(
    value: None | bool | int | float,
    *,
    max_bytes: int,
) -> str | None:
    if max_bytes <= 0:
        return None
    if type(value) is int and _estimated_int_text_bytes(value) > max_bytes:
        return None
    try:
        rendered = str(value)
    except ValueError:
        return None
    if len(rendered.encode("utf-8")) > max_bytes:
        return None
    return rendered


def _estimated_int_text_bytes(value: int) -> int:
    if value == 0:
        return 1
    digits = (abs(value).bit_length() * 30_103) // 100_000 + 1
    return digits + int(value < 0)


def _pathlike_text(value: os.PathLike[str] | os.PathLike[bytes]) -> str:
    try:
        path = os.fspath(value)
    except (OSError, TypeError, ValueError):
        return PUBLIC_DIAGNOSTIC_UNSUPPORTED_MARKER
    if type(path) is bytes:
        return path[:PUBLIC_DIAGNOSTIC_MAX_INPUT_BYTES].decode(
            "utf-8",
            errors="replace",
        )
    if type(path) is str:
        return _truncate_text_to_bytes(path, PUBLIC_DIAGNOSTIC_MAX_INPUT_BYTES)
    return PUBLIC_DIAGNOSTIC_UNSUPPORTED_MARKER


def _remove_control_characters(
    text: str,
    *,
    layout: DiagnosticTextLayout,
) -> str:
    text = _ANSI_ESCAPE_PATTERN.sub("", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    characters: list[str] = []
    for character in text:
        category = unicodedata.category(character)
        if category in {"Cc", "Cf", "Cs"}:
            if character == "\n" and layout is DiagnosticTextLayout.PRESERVE_LINES:
                characters.append(character)
            elif category == "Cc":
                characters.append(" ")
            continue
        characters.append(character)
    rendered = "".join(characters)
    if layout is DiagnosticTextLayout.SINGLE_LINE:
        return " ".join(rendered.split())
    return rendered
