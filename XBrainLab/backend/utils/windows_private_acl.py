"""Native Windows owner-only ACL enforcement for private diagnostic storage."""

from __future__ import annotations

import ctypes
import os
from dataclasses import dataclass
from typing import Any, Protocol, cast


class _MsvcrtApi(Protocol):
    def get_osfhandle(self, descriptor: int) -> int: ...


_msvcrt: _MsvcrtApi | None
try:
    import msvcrt as _msvcrt_module
except ImportError:  # pragma: no cover - non-Windows import boundary
    _msvcrt = None
else:  # pragma: no cover - native Windows only
    _msvcrt = cast(_MsvcrtApi, _msvcrt_module)

ACCESS_ALLOWED_ACE_TYPE = 0x00
OBJECT_INHERIT_ACE = 0x01
CONTAINER_INHERIT_ACE = 0x02
NO_INHERITANCE = 0x00
FILE_ALL_ACCESS = 0x001F01FF

_ACL_REVISION = 2
_ACL_SIZE_INFORMATION_CLASS = 2
_CONTAINER_INHERITANCE = OBJECT_INHERIT_ACE | CONTAINER_INHERIT_ACE
_DACL_SECURITY_INFORMATION = 0x00000004
_ERROR_INSUFFICIENT_BUFFER = 122
_FILE_ATTRIBUTE_REPARSE_POINT = 0x00000400
_FILE_ATTRIBUTE_TAG_INFORMATION_CLASS = 9
_FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
_FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
_FILE_SHARE_DELETE = 0x00000004
_FILE_SHARE_READ = 0x00000001
_FILE_SHARE_WRITE = 0x00000002
_INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
_OPEN_EXISTING = 3
_OWNER_SECURITY_INFORMATION = 0x00000001
_PROTECTED_DACL_SECURITY_INFORMATION = 0x80000000
_READ_CONTROL = 0x00020000
_SE_DACL_PROTECTED = 0x1000
_SE_FILE_OBJECT = 1
_TOKEN_QUERY = 0x0008
_TOKEN_USER_INFORMATION_CLASS = 1
_WRITE_DAC = 0x00040000
_WRITE_OWNER = 0x00080000

_BYTE = ctypes.c_uint8
_WORD = ctypes.c_uint16
_DWORD = ctypes.c_uint32
_BOOL = ctypes.c_int32
_HANDLE = ctypes.c_void_p
_LPVOID = ctypes.c_void_p


class WindowsAclError(PermissionError):
    """Raised when private Windows ACL storage cannot be proven."""


@dataclass(frozen=True, slots=True)
class AceSnapshot:
    """One access-control entry projected without account names."""

    ace_type: int
    flags: int
    mask: int
    sid: bytes


@dataclass(frozen=True, slots=True)
class AclSnapshot:
    """Security properties required for private-storage admission."""

    owner_sid: bytes
    dacl_protected: bool
    aces: tuple[AceSnapshot, ...]


class _Acl(ctypes.Structure):
    _fields_ = (
        ("revision", _BYTE),
        ("reserved_1", _BYTE),
        ("size", _WORD),
        ("ace_count", _WORD),
        ("reserved_2", _WORD),
    )


class _AceHeader(ctypes.Structure):
    _fields_ = (
        ("ace_type", _BYTE),
        ("flags", _BYTE),
        ("size", _WORD),
    )


class _AccessAllowedAce(ctypes.Structure):
    _fields_ = (
        ("header", _AceHeader),
        ("mask", _DWORD),
        ("sid_start", _DWORD),
    )


class _AclSizeInformation(ctypes.Structure):
    _fields_ = (
        ("ace_count", _DWORD),
        ("bytes_in_use", _DWORD),
        ("bytes_free", _DWORD),
    )


class _FileAttributeTagInformation(ctypes.Structure):
    _fields_ = (("attributes", _DWORD), ("reparse_tag", _DWORD))


class _SidAndAttributes(ctypes.Structure):
    _fields_ = (("sid", _LPVOID), ("attributes", _DWORD))


class _TokenUser(ctypes.Structure):
    _fields_ = (("user", _SidAndAttributes),)


class _WindowsAclApi(Protocol):
    def current_user_sid(self) -> bytes: ...

    def open_file_security_handle(self, descriptor: int) -> int: ...

    def open_directory(self, path: str) -> int: ...

    def close_handle(self, handle: int) -> None: ...

    def is_reparse_point(self, handle: int) -> bool: ...

    def apply_private_acl(
        self,
        handle: int,
        *,
        current_user_sid: bytes,
        inheritance_flags: int,
    ) -> None: ...

    def read_acl(self, handle: int) -> AclSnapshot: ...


def secure_private_windows_directory(path: str) -> None:
    """Protect a directory and admit it only after exact ACL verification."""
    _secure_directory_with_api(path, api=_load_native_api())


def secure_private_windows_file_descriptor(descriptor: int) -> None:
    """Protect the file object behind one CRT descriptor and verify its ACL."""
    _secure_file_descriptor_with_api(descriptor, api=_load_native_api())


def _secure_directory_with_api(path: str, *, api: _WindowsAclApi) -> None:
    handle = api.open_directory(path)
    try:
        if api.is_reparse_point(handle):
            raise WindowsAclError(
                "Private Windows log directory admission rejected a reparse point."
            )
        _secure_handle_with_api(
            handle,
            api=api,
            inheritance_flags=_CONTAINER_INHERITANCE,
        )
    finally:
        api.close_handle(handle)


def _secure_file_descriptor_with_api(
    descriptor: int,
    *,
    api: _WindowsAclApi,
) -> None:
    handle = api.open_file_security_handle(descriptor)
    try:
        _secure_handle_with_api(
            handle,
            api=api,
            inheritance_flags=NO_INHERITANCE,
        )
    finally:
        api.close_handle(handle)


def _secure_handle_with_api(
    handle: int,
    *,
    api: _WindowsAclApi,
    inheritance_flags: int,
) -> None:
    current_user_sid = api.current_user_sid()
    if not current_user_sid:
        raise WindowsAclError(
            "Private Windows log ACL admission could not resolve the current user SID."
        )
    api.apply_private_acl(
        handle,
        current_user_sid=current_user_sid,
        inheritance_flags=inheritance_flags,
    )
    verify_private_acl(
        api.read_acl(handle),
        current_user_sid=current_user_sid,
        inheritance_flags=inheritance_flags,
    )


def verify_private_acl(
    snapshot: AclSnapshot,
    *,
    current_user_sid: bytes,
    inheritance_flags: int,
) -> None:
    """Require one protected full-control ACE for the current owner only."""
    if snapshot.owner_sid != current_user_sid:
        raise WindowsAclError(
            "Private Windows log ACL verification failed: owner is not the "
            "current user."
        )
    if not snapshot.dacl_protected:
        raise WindowsAclError(
            "Private Windows log ACL verification failed: DACL is not protected "
            "from inherited access."
        )
    if len(snapshot.aces) != 1:
        raise WindowsAclError(
            "Private Windows log ACL verification failed: expected exactly one "
            "access entry."
        )
    ace = snapshot.aces[0]
    if ace.ace_type != ACCESS_ALLOWED_ACE_TYPE:
        raise WindowsAclError(
            "Private Windows log ACL verification failed: entry is not an allow entry."
        )
    if ace.flags != inheritance_flags:
        raise WindowsAclError(
            "Private Windows log ACL verification failed: unexpected inheritance flags."
        )
    if ace.mask != FILE_ALL_ACCESS:
        raise WindowsAclError(
            "Private Windows log ACL verification failed: current user lacks exact "
            "full file access."
        )
    if ace.sid != current_user_sid:
        raise WindowsAclError(
            "Private Windows log ACL verification failed: access entry is not for "
            "the current user."
        )


def _load_native_api() -> _WindowsAclApi:
    if os.name != "nt":
        raise WindowsAclError(
            "Native Windows private log ACL enforcement is unavailable on this "
            "platform."
        )
    loader = getattr(ctypes, "WinDLL", None)
    if loader is None:
        raise WindowsAclError(
            "Native Windows private log ACL enforcement is unavailable because "
            "Win32 API loading is unsupported."
        )
    try:
        advapi32 = loader("advapi32", use_last_error=True)
        kernel32 = loader("kernel32", use_last_error=True)
        return _NativeWindowsAclApi(advapi32=advapi32, kernel32=kernel32)
    except (AttributeError, OSError) as error:
        raise WindowsAclError(
            "Native Windows private log ACL enforcement could not initialize the "
            "required security APIs."
        ) from error


class _NativeWindowsAclApi:
    def __init__(self, *, advapi32: Any, kernel32: Any) -> None:
        self._advapi32 = advapi32
        self._kernel32 = kernel32
        self._configure_signatures()

    def _configure_signatures(self) -> None:
        self._advapi32.OpenProcessToken.argtypes = (
            _HANDLE,
            _DWORD,
            ctypes.POINTER(_HANDLE),
        )
        self._advapi32.OpenProcessToken.restype = _BOOL
        self._advapi32.GetTokenInformation.argtypes = (
            _HANDLE,
            ctypes.c_int,
            _LPVOID,
            _DWORD,
            ctypes.POINTER(_DWORD),
        )
        self._advapi32.GetTokenInformation.restype = _BOOL
        self._advapi32.GetLengthSid.argtypes = (_LPVOID,)
        self._advapi32.GetLengthSid.restype = _DWORD
        self._advapi32.IsValidSid.argtypes = (_LPVOID,)
        self._advapi32.IsValidSid.restype = _BOOL
        self._advapi32.InitializeAcl.argtypes = (_LPVOID, _DWORD, _DWORD)
        self._advapi32.InitializeAcl.restype = _BOOL
        self._advapi32.AddAccessAllowedAceEx.argtypes = (
            _LPVOID,
            _DWORD,
            _DWORD,
            _DWORD,
            _LPVOID,
        )
        self._advapi32.AddAccessAllowedAceEx.restype = _BOOL
        self._advapi32.SetSecurityInfo.argtypes = (
            _HANDLE,
            ctypes.c_int,
            _DWORD,
            _LPVOID,
            _LPVOID,
            _LPVOID,
            _LPVOID,
        )
        self._advapi32.SetSecurityInfo.restype = _DWORD
        self._advapi32.GetSecurityInfo.argtypes = (
            _HANDLE,
            ctypes.c_int,
            _DWORD,
            ctypes.POINTER(_LPVOID),
            ctypes.POINTER(_LPVOID),
            ctypes.POINTER(_LPVOID),
            ctypes.POINTER(_LPVOID),
            ctypes.POINTER(_LPVOID),
        )
        self._advapi32.GetSecurityInfo.restype = _DWORD
        self._advapi32.GetSecurityDescriptorControl.argtypes = (
            _LPVOID,
            ctypes.POINTER(_WORD),
            ctypes.POINTER(_DWORD),
        )
        self._advapi32.GetSecurityDescriptorControl.restype = _BOOL
        self._advapi32.GetAclInformation.argtypes = (
            _LPVOID,
            _LPVOID,
            _DWORD,
            ctypes.c_int,
        )
        self._advapi32.GetAclInformation.restype = _BOOL
        self._advapi32.GetAce.argtypes = (
            _LPVOID,
            _DWORD,
            ctypes.POINTER(_LPVOID),
        )
        self._advapi32.GetAce.restype = _BOOL

        self._kernel32.GetCurrentProcess.argtypes = ()
        self._kernel32.GetCurrentProcess.restype = _HANDLE
        self._kernel32.CloseHandle.argtypes = (_HANDLE,)
        self._kernel32.CloseHandle.restype = _BOOL
        self._kernel32.CreateFileW.argtypes = (
            ctypes.c_wchar_p,
            _DWORD,
            _DWORD,
            _LPVOID,
            _DWORD,
            _DWORD,
            _HANDLE,
        )
        self._kernel32.CreateFileW.restype = _HANDLE
        self._kernel32.ReOpenFile.argtypes = (_HANDLE, _DWORD, _DWORD, _DWORD)
        self._kernel32.ReOpenFile.restype = _HANDLE
        self._kernel32.GetFileInformationByHandleEx.argtypes = (
            _HANDLE,
            ctypes.c_int,
            _LPVOID,
            _DWORD,
        )
        self._kernel32.GetFileInformationByHandleEx.restype = _BOOL
        self._kernel32.LocalFree.argtypes = (_LPVOID,)
        self._kernel32.LocalFree.restype = _LPVOID

    def current_user_sid(self) -> bytes:
        token = _HANDLE()
        if not self._advapi32.OpenProcessToken(
            self._kernel32.GetCurrentProcess(),
            _TOKEN_QUERY,
            ctypes.byref(token),
        ):
            raise self._last_error("OpenProcessToken")
        token_handle = self._require_handle_value(token.value, "OpenProcessToken")
        try:
            required_size = _DWORD()
            self._clear_last_error()
            first_result = self._advapi32.GetTokenInformation(
                token,
                _TOKEN_USER_INFORMATION_CLASS,
                None,
                0,
                ctypes.byref(required_size),
            )
            if first_result or self._last_error_code() != _ERROR_INSUFFICIENT_BUFFER:
                raise WindowsAclError(
                    "Native Windows private log ACL enforcement could not size the "
                    "current-user token information."
                )
            if required_size.value < ctypes.sizeof(_TokenUser):
                raise WindowsAclError(
                    "Native Windows private log ACL enforcement received invalid "
                    "current-user token information."
                )
            token_buffer = ctypes.create_string_buffer(required_size.value)
            if not self._advapi32.GetTokenInformation(
                token,
                _TOKEN_USER_INFORMATION_CLASS,
                ctypes.cast(token_buffer, _LPVOID),
                required_size,
                ctypes.byref(required_size),
            ):
                raise self._last_error("GetTokenInformation")
            token_user = ctypes.cast(
                token_buffer,
                ctypes.POINTER(_TokenUser),
            ).contents
            return self._sid_bytes(token_user.user.sid)
        finally:
            self.close_handle(token_handle)

    def open_file_security_handle(self, descriptor: int) -> int:
        if _msvcrt is None:  # pragma: no cover - native Windows only
            raise WindowsAclError(
                "Native Windows private log ACL enforcement cannot access the CRT "
                "file handle."
            )
        try:
            native_handle = _msvcrt.get_osfhandle(descriptor)
        except OSError as error:
            raise WindowsAclError(
                "Native Windows private log ACL enforcement received an invalid "
                "file descriptor."
            ) from error
        reopened = self._kernel32.ReOpenFile(
            _HANDLE(native_handle),
            _READ_CONTROL | _WRITE_DAC | _WRITE_OWNER,
            _FILE_SHARE_READ | _FILE_SHARE_WRITE | _FILE_SHARE_DELETE,
            0,
        )
        return self._require_handle_value(reopened, "ReOpenFile")

    def open_directory(self, path: str) -> int:
        handle = self._kernel32.CreateFileW(
            path,
            _READ_CONTROL | _WRITE_DAC | _WRITE_OWNER,
            _FILE_SHARE_READ | _FILE_SHARE_WRITE | _FILE_SHARE_DELETE,
            None,
            _OPEN_EXISTING,
            _FILE_FLAG_BACKUP_SEMANTICS | _FILE_FLAG_OPEN_REPARSE_POINT,
            None,
        )
        return self._require_handle_value(handle, "CreateFileW")

    def close_handle(self, handle: int) -> None:
        if not self._kernel32.CloseHandle(_HANDLE(handle)):
            raise self._last_error("CloseHandle")

    def is_reparse_point(self, handle: int) -> bool:
        information = _FileAttributeTagInformation()
        if not self._kernel32.GetFileInformationByHandleEx(
            _HANDLE(handle),
            _FILE_ATTRIBUTE_TAG_INFORMATION_CLASS,
            ctypes.byref(information),
            ctypes.sizeof(information),
        ):
            raise self._last_error("GetFileInformationByHandleEx")
        return bool(information.attributes & _FILE_ATTRIBUTE_REPARSE_POINT)

    def apply_private_acl(
        self,
        handle: int,
        *,
        current_user_sid: bytes,
        inheritance_flags: int,
    ) -> None:
        sid_buffer = ctypes.create_string_buffer(current_user_sid)
        sid_pointer = ctypes.cast(sid_buffer, _LPVOID)
        if not self._advapi32.IsValidSid(sid_pointer):
            raise WindowsAclError(
                "Native Windows private log ACL enforcement resolved an invalid "
                "current-user SID."
            )
        acl_size = (
            ctypes.sizeof(_Acl)
            + ctypes.sizeof(_AccessAllowedAce)
            - ctypes.sizeof(_DWORD)
            + len(current_user_sid)
        )
        acl_buffer = ctypes.create_string_buffer(acl_size)
        acl_pointer = ctypes.cast(acl_buffer, _LPVOID)
        if not self._advapi32.InitializeAcl(
            acl_pointer,
            acl_size,
            _ACL_REVISION,
        ):
            raise self._last_error("InitializeAcl")
        if not self._advapi32.AddAccessAllowedAceEx(
            acl_pointer,
            _ACL_REVISION,
            inheritance_flags,
            FILE_ALL_ACCESS,
            sid_pointer,
        ):
            raise self._last_error("AddAccessAllowedAceEx")
        result = self._advapi32.SetSecurityInfo(
            _HANDLE(handle),
            _SE_FILE_OBJECT,
            _OWNER_SECURITY_INFORMATION
            | _DACL_SECURITY_INFORMATION
            | _PROTECTED_DACL_SECURITY_INFORMATION,
            sid_pointer,
            None,
            acl_pointer,
            None,
        )
        if result:
            raise WindowsAclError(
                "Native Windows private log ACL enforcement failed in "
                f"SetSecurityInfo with Windows error {int(result)}."
            )

    def read_acl(self, handle: int) -> AclSnapshot:
        owner = _LPVOID()
        dacl = _LPVOID()
        security_descriptor = _LPVOID()
        result = self._advapi32.GetSecurityInfo(
            _HANDLE(handle),
            _SE_FILE_OBJECT,
            _OWNER_SECURITY_INFORMATION | _DACL_SECURITY_INFORMATION,
            ctypes.byref(owner),
            None,
            ctypes.byref(dacl),
            None,
            ctypes.byref(security_descriptor),
        )
        if result:
            raise WindowsAclError(
                "Native Windows private log ACL verification failed in "
                f"GetSecurityInfo with Windows error {int(result)}."
            )
        try:
            if not security_descriptor.value or not dacl.value:
                raise WindowsAclError(
                    "Native Windows private log ACL verification rejected a null DACL."
                )
            control = _WORD()
            revision = _DWORD()
            if not self._advapi32.GetSecurityDescriptorControl(
                security_descriptor,
                ctypes.byref(control),
                ctypes.byref(revision),
            ):
                raise self._last_error("GetSecurityDescriptorControl")
            acl_information = _AclSizeInformation()
            if not self._advapi32.GetAclInformation(
                dacl,
                ctypes.byref(acl_information),
                ctypes.sizeof(acl_information),
                _ACL_SIZE_INFORMATION_CLASS,
            ):
                raise self._last_error("GetAclInformation")
            aces = tuple(
                self._read_ace(dacl, index)
                for index in range(acl_information.ace_count)
            )
            return AclSnapshot(
                owner_sid=self._sid_bytes(owner),
                dacl_protected=bool(control.value & _SE_DACL_PROTECTED),
                aces=aces,
            )
        finally:
            if security_descriptor.value:
                self._kernel32.LocalFree(security_descriptor)

    def _read_ace(self, dacl: _LPVOID, index: int) -> AceSnapshot:
        ace_pointer = _LPVOID()
        if not self._advapi32.GetAce(dacl, index, ctypes.byref(ace_pointer)):
            raise self._last_error("GetAce")
        if not ace_pointer.value:
            raise WindowsAclError(
                "Native Windows private log ACL verification received a null entry."
            )
        header = ctypes.cast(ace_pointer, ctypes.POINTER(_AceHeader)).contents
        if header.ace_type != ACCESS_ALLOWED_ACE_TYPE:
            return AceSnapshot(
                ace_type=int(header.ace_type),
                flags=int(header.flags),
                mask=0,
                sid=b"",
            )
        if header.size < ctypes.sizeof(_AccessAllowedAce):
            raise WindowsAclError(
                "Native Windows private log ACL verification received a malformed "
                "allow entry."
            )
        allowed = ctypes.cast(
            ace_pointer,
            ctypes.POINTER(_AccessAllowedAce),
        ).contents
        sid_address = ace_pointer.value + _AccessAllowedAce.sid_start.offset
        sid_pointer = _LPVOID(sid_address)
        sid = self._sid_bytes(sid_pointer)
        required_size = _AccessAllowedAce.sid_start.offset + len(sid)
        if required_size > header.size:
            raise WindowsAclError(
                "Native Windows private log ACL verification received an invalid "
                "entry size."
            )
        return AceSnapshot(
            ace_type=int(header.ace_type),
            flags=int(header.flags),
            mask=int(allowed.mask),
            sid=sid,
        )

    def _sid_bytes(self, sid: _LPVOID) -> bytes:
        if not sid or not self._advapi32.IsValidSid(sid):
            raise WindowsAclError(
                "Native Windows private log ACL verification received an invalid SID."
            )
        length = int(self._advapi32.GetLengthSid(sid))
        if length <= 0 or length > 68:
            raise WindowsAclError(
                "Native Windows private log ACL verification received an invalid SID "
                "length."
            )
        return ctypes.string_at(sid, length)

    def _require_handle_value(self, handle: object, operation: str) -> int:
        value = handle.value if isinstance(handle, _HANDLE) else handle
        if not isinstance(value, int) or value == _INVALID_HANDLE_VALUE:
            raise self._last_error(operation)
        return value

    def _last_error(self, operation: str) -> WindowsAclError:
        return WindowsAclError(
            "Native Windows private log ACL enforcement failed in "
            f"{operation} with Windows error {self._last_error_code()}."
        )

    @staticmethod
    def _clear_last_error() -> None:
        setter = getattr(ctypes, "set_last_error", None)
        if setter is not None:
            setter(0)

    @staticmethod
    def _last_error_code() -> int:
        getter = getattr(ctypes, "get_last_error", None)
        return int(getter()) if getter is not None else 0
