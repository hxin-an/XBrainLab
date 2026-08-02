import ast
import os
from pathlib import Path

import pytest

from XBrainLab.backend.utils import secure_log_storage, windows_private_acl


class _FakeWindowsAclApi:
    def __init__(
        self,
        *,
        snapshot: windows_private_acl.AclSnapshot | None = None,
        reparse_point: bool = False,
    ) -> None:
        current_sid = b"current-user-sid"
        self.current_sid = current_sid
        self.snapshot = snapshot or windows_private_acl.AclSnapshot(
            owner_sid=current_sid,
            dacl_protected=True,
            aces=(
                windows_private_acl.AceSnapshot(
                    ace_type=windows_private_acl.ACCESS_ALLOWED_ACE_TYPE,
                    flags=0,
                    mask=windows_private_acl.FILE_ALL_ACCESS,
                    sid=current_sid,
                ),
            ),
        )
        self.reparse_point = reparse_point
        self.calls: list[tuple[object, ...]] = []

    def current_user_sid(self) -> bytes:
        self.calls.append(("current_user_sid",))
        return self.current_sid

    def open_file_security_handle(self, descriptor: int) -> int:
        self.calls.append(("open_file_security_handle", descriptor))
        return 92

    def open_directory(self, path: str) -> int:
        self.calls.append(("open_directory", path))
        return 91

    def close_handle(self, handle: int) -> None:
        self.calls.append(("close_handle", handle))

    def is_reparse_point(self, handle: int) -> bool:
        self.calls.append(("is_reparse_point", handle))
        return self.reparse_point

    def apply_private_acl(
        self,
        handle: int,
        *,
        current_user_sid: bytes,
        inheritance_flags: int,
    ) -> None:
        self.calls.append(
            (
                "apply_private_acl",
                handle,
                current_user_sid,
                inheritance_flags,
            )
        )

    def read_acl(self, handle: int) -> windows_private_acl.AclSnapshot:
        self.calls.append(("read_acl", handle))
        return self.snapshot


def test_windows_file_descriptor_acl_is_applied_and_verified_on_same_handle() -> None:
    api = _FakeWindowsAclApi()

    windows_private_acl._secure_file_descriptor_with_api(17, api=api)

    assert api.calls == [
        ("open_file_security_handle", 17),
        ("current_user_sid",),
        (
            "apply_private_acl",
            92,
            b"current-user-sid",
            windows_private_acl.NO_INHERITANCE,
        ),
        ("read_acl", 92),
        ("close_handle", 92),
    ]


def test_windows_directory_acl_is_private_protected_and_inheritable() -> None:
    directory_flags = (
        windows_private_acl.OBJECT_INHERIT_ACE
        | windows_private_acl.CONTAINER_INHERIT_ACE
    )
    api = _FakeWindowsAclApi(
        snapshot=windows_private_acl.AclSnapshot(
            owner_sid=b"current-user-sid",
            dacl_protected=True,
            aces=(
                windows_private_acl.AceSnapshot(
                    ace_type=windows_private_acl.ACCESS_ALLOWED_ACE_TYPE,
                    flags=directory_flags,
                    mask=windows_private_acl.FILE_ALL_ACCESS,
                    sid=b"current-user-sid",
                ),
            ),
        )
    )

    windows_private_acl._secure_directory_with_api(r"C:\Users\me\logs", api=api)

    assert api.calls == [
        ("open_directory", r"C:\Users\me\logs"),
        ("is_reparse_point", 91),
        ("current_user_sid",),
        (
            "apply_private_acl",
            91,
            b"current-user-sid",
            directory_flags,
        ),
        ("read_acl", 91),
        ("close_handle", 91),
    ]


def test_windows_directory_reparse_point_fails_before_acl_mutation() -> None:
    api = _FakeWindowsAclApi(reparse_point=True)

    with pytest.raises(
        windows_private_acl.WindowsAclError,
        match="reparse point",
    ):
        windows_private_acl._secure_directory_with_api(
            r"C:\Users\me\linked-logs",
            api=api,
        )

    assert not any(call[0] == "apply_private_acl" for call in api.calls)
    assert api.calls[-1] == ("close_handle", 91)


@pytest.mark.parametrize(
    ("snapshot", "message"),
    [
        (
            windows_private_acl.AclSnapshot(
                owner_sid=b"another-user",
                dacl_protected=True,
                aces=(
                    windows_private_acl.AceSnapshot(
                        ace_type=windows_private_acl.ACCESS_ALLOWED_ACE_TYPE,
                        flags=0,
                        mask=windows_private_acl.FILE_ALL_ACCESS,
                        sid=b"current-user-sid",
                    ),
                ),
            ),
            "owner",
        ),
        (
            windows_private_acl.AclSnapshot(
                owner_sid=b"current-user-sid",
                dacl_protected=False,
                aces=(
                    windows_private_acl.AceSnapshot(
                        ace_type=windows_private_acl.ACCESS_ALLOWED_ACE_TYPE,
                        flags=0,
                        mask=windows_private_acl.FILE_ALL_ACCESS,
                        sid=b"current-user-sid",
                    ),
                ),
            ),
            "protected",
        ),
        (
            windows_private_acl.AclSnapshot(
                owner_sid=b"current-user-sid",
                dacl_protected=True,
                aces=(
                    windows_private_acl.AceSnapshot(
                        ace_type=windows_private_acl.ACCESS_ALLOWED_ACE_TYPE,
                        flags=0,
                        mask=windows_private_acl.FILE_ALL_ACCESS,
                        sid=b"current-user-sid",
                    ),
                    windows_private_acl.AceSnapshot(
                        ace_type=windows_private_acl.ACCESS_ALLOWED_ACE_TYPE,
                        flags=0,
                        mask=windows_private_acl.FILE_ALL_ACCESS,
                        sid=b"another-principal",
                    ),
                ),
            ),
            "exactly one",
        ),
        (
            windows_private_acl.AclSnapshot(
                owner_sid=b"current-user-sid",
                dacl_protected=True,
                aces=(
                    windows_private_acl.AceSnapshot(
                        ace_type=1,
                        flags=0,
                        mask=windows_private_acl.FILE_ALL_ACCESS,
                        sid=b"current-user-sid",
                    ),
                ),
            ),
            "allow entry",
        ),
        (
            windows_private_acl.AclSnapshot(
                owner_sid=b"current-user-sid",
                dacl_protected=True,
                aces=(
                    windows_private_acl.AceSnapshot(
                        ace_type=windows_private_acl.ACCESS_ALLOWED_ACE_TYPE,
                        flags=windows_private_acl.OBJECT_INHERIT_ACE,
                        mask=windows_private_acl.FILE_ALL_ACCESS,
                        sid=b"current-user-sid",
                    ),
                ),
            ),
            "inheritance",
        ),
        (
            windows_private_acl.AclSnapshot(
                owner_sid=b"current-user-sid",
                dacl_protected=True,
                aces=(
                    windows_private_acl.AceSnapshot(
                        ace_type=windows_private_acl.ACCESS_ALLOWED_ACE_TYPE,
                        flags=0,
                        mask=0x1,
                        sid=b"current-user-sid",
                    ),
                ),
            ),
            "full file access",
        ),
        (
            windows_private_acl.AclSnapshot(
                owner_sid=b"current-user-sid",
                dacl_protected=True,
                aces=(
                    windows_private_acl.AceSnapshot(
                        ace_type=windows_private_acl.ACCESS_ALLOWED_ACE_TYPE,
                        flags=0,
                        mask=windows_private_acl.FILE_ALL_ACCESS,
                        sid=b"another-principal",
                    ),
                ),
            ),
            "current user",
        ),
    ],
)
def test_windows_acl_verifier_rejects_non_private_state(
    snapshot: windows_private_acl.AclSnapshot,
    message: str,
) -> None:
    with pytest.raises(windows_private_acl.WindowsAclError, match=message):
        windows_private_acl.verify_private_acl(
            snapshot,
            current_user_sid=b"current-user-sid",
            inheritance_flags=windows_private_acl.NO_INHERITANCE,
        )


def test_prepare_secure_log_directory_requires_windows_acl_admission(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(secure_log_storage.os, "name", "nt")
    monkeypatch.setattr(
        secure_log_storage,
        "_require_directory_chain_without_links",
        lambda _path: None,
    )
    monkeypatch.setattr(
        secure_log_storage,
        "secure_private_windows_directory",
        calls.append,
    )

    secure_log_storage.prepare_secure_log_directory(str(tmp_path))

    assert calls == [str(tmp_path)]


def test_windows_log_descriptor_is_closed_when_acl_admission_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closed: list[int] = []
    monkeypatch.setattr(secure_log_storage.os, "name", "nt")
    monkeypatch.setattr(
        secure_log_storage,
        "_require_directory_chain_without_links",
        lambda _path: None,
    )
    monkeypatch.setattr(secure_log_storage.os.path, "lexists", lambda _path: False)
    monkeypatch.setattr(secure_log_storage.os, "open", lambda *_args: 41)
    monkeypatch.setattr(secure_log_storage.os, "close", closed.append)
    monkeypatch.setattr(
        secure_log_storage,
        "secure_private_windows_directory",
        lambda _path: None,
    )
    monkeypatch.setattr(
        secure_log_storage,
        "secure_private_windows_file_descriptor",
        lambda _descriptor: (_ for _ in ()).throw(
            windows_private_acl.WindowsAclError("Windows ACL verification failed")
        ),
    )
    monkeypatch.setattr(
        secure_log_storage,
        "_require_regular_descriptor",
        lambda _descriptor: None,
    )

    with pytest.raises(
        windows_private_acl.WindowsAclError,
        match="verification failed",
    ):
        secure_log_storage.open_regular_log_descriptor(
            "private.log",
            os.O_WRONLY,
        )

    assert closed == [41]


def test_windows_acl_implementation_has_no_shell_command_surface() -> None:
    source_path = Path(windows_private_acl.__file__)
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imported_modules = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported_modules.update(
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    )

    assert "subprocess" not in imported_modules
    assert "locale" not in imported_modules
