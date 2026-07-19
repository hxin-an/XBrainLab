"""Architecture guards for raw lifecycle and label batch transaction ownership."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.architecture_compliance import check_raw_mutation_atomicity_boundaries


def test_guard_rejects_direct_partial_label_batch_mutation(tmp_path: Path) -> None:
    label_service = tmp_path / "XBrainLab/backend/services/label_import_service.py"
    label_service.parent.mkdir(parents=True)
    label_service.write_text(
        """
class LabelImportService:
    def apply_labels_batch(self, targets):
        for target in targets:
            self.apply_labels_to_single_file(target, [], {})

    def apply_labels_sequence(self, targets):
        for target in targets:
            self._force_apply_single(target, [], {})
""",
        encoding="utf-8",
    )

    violations = check_raw_mutation_atomicity_boundaries(tmp_path)

    assert any("apply_labels_batch() directly mutates" in item for item in violations)
    assert any(
        "apply_labels_sequence() directly mutates" in item for item in violations
    )


@pytest.mark.parametrize(
    ("import_block", "first_binding"),
    (
        ("", "self.apply_labels_to_single_file"),
        (
            "from raw_labels import apply_labels_to_single_file as imported_mutation\n",
            "imported_mutation",
        ),
        (
            "import raw_labels as raw_mutations\n",
            "raw_mutations.apply_labels_to_single_file",
        ),
    ),
    ids=("SELF_ATTRIBUTE", "FROM_IMPORT", "MODULE_ATTRIBUTE"),
)
def test_guard_rejects_transitive_callable_alias_to_raw_label_mutation(
    tmp_path: Path,
    import_block: str,
    first_binding: str,
) -> None:
    label_service = tmp_path / "XBrainLab/backend/services/label_import_service.py"
    label_service.parent.mkdir(parents=True)
    label_service.write_text(
        f"""{import_block}
class LabelImportService:
    def apply_labels_batch(self, target):
        first = {first_binding}
        second = first
        second(target, [], {{}})

    def apply_labels_sequence(self, targets):
        self._apply_label_operations_atomically(targets)
""",
        encoding="utf-8",
    )

    violations = check_raw_mutation_atomicity_boundaries(tmp_path)

    assert any("apply_labels_batch() directly mutates" in item for item in violations)


@pytest.mark.parametrize(
    "mutation_body",
    (
        """
        first, other = self.apply_labels_to_single_file, self.safe
        first(target, [], {})
""",
        """
        [first, other] = [self.apply_labels_to_single_file, self.safe]
        first(target, [], {})
""",
        """
        (other, (first, last)) = (
            self.safe,
            (self.apply_labels_to_single_file, self.safe),
        )
        first(target, [], {})
""",
        """
        first, *others = self.apply_labels_to_single_file, self.safe, self.safe
        first(target, [], {})
""",
        """
        first, other = second, self.safe
        second = self.apply_labels_to_single_file
        first(target, [], {})
""",
        """
        (first := self.apply_labels_to_single_file)(target, [], {})
""",
        """
        first = self.safe
        (first := self.apply_labels_to_single_file)(target, [], {})
""",
    ),
    ids=(
        "TUPLE_UNPACK",
        "LIST_UNPACK",
        "NESTED_UNPACK",
        "STARRED_UNPACK",
        "UNPACK_FIXED_POINT",
        "WALRUS_CALLABLE",
        "WALRUS_REBIND",
    ),
)
def test_guard_rejects_unpack_and_namedexpr_callable_alias_mutation_matrix(
    tmp_path: Path,
    mutation_body: str,
) -> None:
    label_service = tmp_path / "XBrainLab/backend/services/label_import_service.py"
    label_service.parent.mkdir(parents=True)
    label_service.write_text(
        f"""
class LabelImportService:
    def apply_labels_batch(self, target):
{mutation_body}

    def apply_labels_sequence(self, targets):
        self._apply_label_operations_atomically(targets)
""",
        encoding="utf-8",
    )

    violations = check_raw_mutation_atomicity_boundaries(tmp_path)

    assert any("apply_labels_batch() directly mutates" in item for item in violations)


def test_guard_preserves_precise_atomic_callable_unpack_binding(
    tmp_path: Path,
) -> None:
    label_service = tmp_path / "XBrainLab/backend/services/label_import_service.py"
    label_service.parent.mkdir(parents=True)
    label_service.write_text(
        """
class LabelImportService:
    def apply_labels_batch(self, targets):
        first, other = (
            self._apply_label_operations_atomically,
            self.apply_labels_to_single_file,
        )
        first(targets)

    def apply_labels_sequence(self, targets):
        self._apply_label_operations_atomically(targets)
""",
        encoding="utf-8",
    )

    violations = check_raw_mutation_atomicity_boundaries(tmp_path)

    assert not any(
        "apply_labels_batch() directly mutates" in item for item in violations
    )
    assert not any(
        "apply_labels_batch() must delegate to the atomic" in item
        for item in violations
    )


@pytest.mark.parametrize(
    ("mutation_body", "expected_fragment"),
    (
        (
            """
        def factory():
            return self.apply_labels_to_single_file

        mutate = factory()
        mutate(target, [], {})
""",
            "directly mutates",
        ),
        (
            """
        factory = lambda: self.apply_labels_to_single_file
        mutate = factory()
        mutate(target, [], {})
""",
            "directly mutates",
        ),
        (
            """
        import functools

        mutate = functools.partial(
            self.apply_labels_to_single_file,
            target,
        )
        mutate([], {})
""",
            "directly mutates",
        ),
        (
            """
        mutate = getattr(self, "apply_labels_to_single_file")
        mutate(target, [], {})
""",
            "directly mutates",
        ),
        (
            """
        mutate = getattr(self, mutation_name)
        mutate(target, [], {})
""",
            "cannot prove callable construction is atomic",
        ),
    ),
    ids=(
        "NESTED_FACTORY",
        "LAMBDA_FACTORY",
        "FUNCTOOLS_PARTIAL",
        "GETATTR_LITERAL",
        "GETATTR_DYNAMIC",
    ),
)
def test_guard_rejects_callable_construction_raw_mutation_bypasses(
    tmp_path: Path,
    mutation_body: str,
    expected_fragment: str,
) -> None:
    label_service = tmp_path / "XBrainLab/backend/services/label_import_service.py"
    label_service.parent.mkdir(parents=True)
    label_service.write_text(
        f"""
class LabelImportService:
    def apply_labels_batch(
        self,
        target,
        mutation_name="apply_labels_to_single_file",
    ):
        self._apply_label_operations_atomically([])
{mutation_body}

    def apply_labels_sequence(self, targets):
        self._apply_label_operations_atomically(targets)
""",
        encoding="utf-8",
    )

    violations = check_raw_mutation_atomicity_boundaries(tmp_path)

    assert any(
        "apply_labels_batch()" in item and expected_fragment in item
        for item in violations
    )


@pytest.mark.parametrize(
    "atomic_binding",
    (
        """
        def factory():
            return self._apply_label_operations_atomically

        mutate = factory()
        mutate(targets)
""",
        """
        import functools

        mutate = functools.partial(
            self._apply_label_operations_atomically,
            targets,
        )
        mutate()
""",
        """
        mutate = getattr(self, "_apply_label_operations_atomically")
        mutate(targets)
""",
    ),
    ids=("NESTED_FACTORY", "FUNCTOOLS_PARTIAL", "GETATTR_LITERAL"),
)
def test_guard_accepts_provably_atomic_callable_construction(
    tmp_path: Path,
    atomic_binding: str,
) -> None:
    label_service = tmp_path / "XBrainLab/backend/services/label_import_service.py"
    label_service.parent.mkdir(parents=True)
    label_service.write_text(
        f"""
class LabelImportService:
    def apply_labels_batch(self, targets):
{atomic_binding}

    def apply_labels_sequence(self, targets):
        self._apply_label_operations_atomically(targets)
""",
        encoding="utf-8",
    )

    violations = check_raw_mutation_atomicity_boundaries(tmp_path)

    assert not any("apply_labels_batch()" in item for item in violations)


def test_guard_rejects_mapping_subscript_callable_raw_mutation(
    tmp_path: Path,
) -> None:
    label_service = tmp_path / "XBrainLab/backend/services/label_import_service.py"
    label_service.parent.mkdir(parents=True)
    label_service.write_text(
        """
class LabelImportService:
    def apply_labels_batch(self, target):
        factories = {
            "unsafe": self.apply_labels_to_single_file,
            "atomic": self._apply_label_operations_atomically,
        }
        mutate = factories["unsafe"]
        self._apply_label_operations_atomically([])
        mutate(target, [], {})

    def apply_labels_sequence(self, targets):
        self._apply_label_operations_atomically(targets)
""",
        encoding="utf-8",
    )

    violations = check_raw_mutation_atomicity_boundaries(tmp_path)

    assert any(
        "apply_labels_batch()" in item and "directly mutates" in item
        for item in violations
    )


def test_guard_preserves_precise_atomic_mapping_subscript_binding(
    tmp_path: Path,
) -> None:
    label_service = tmp_path / "XBrainLab/backend/services/label_import_service.py"
    label_service.parent.mkdir(parents=True)
    label_service.write_text(
        """
class LabelImportService:
    def apply_labels_batch(self, targets):
        factories = {
            "unsafe": self.apply_labels_to_single_file,
            "atomic": self._apply_label_operations_atomically,
        }
        mutate = factories["atomic"]
        mutate(targets)

    def apply_labels_sequence(self, targets):
        self._apply_label_operations_atomically(targets)
""",
        encoding="utf-8",
    )

    violations = check_raw_mutation_atomicity_boundaries(tmp_path)

    assert not any("apply_labels_batch()" in item for item in violations)


@pytest.mark.parametrize(
    "mapping_mutation",
    (
        """
        factories["selected"] = self.apply_labels_to_single_file
""",
        """
        factories.update(
            {"selected": self.apply_labels_to_single_file}
        )
""",
    ),
    ids=("SUBSCRIPT_ASSIGNMENT", "MAPPING_UPDATE"),
)
def test_guard_rejects_mutated_mapping_subscript_callable_raw_mutation(
    tmp_path: Path,
    mapping_mutation: str,
) -> None:
    label_service = tmp_path / "XBrainLab/backend/services/label_import_service.py"
    label_service.parent.mkdir(parents=True)
    label_service.write_text(
        f"""
class LabelImportService:
    def apply_labels_batch(self, targets):
        factories = {{
            "selected": self._apply_label_operations_atomically,
        }}
{mapping_mutation}
        mutate = factories["selected"]
        mutate(targets)

    def apply_labels_sequence(self, targets):
        self._apply_label_operations_atomically(targets)
""",
        encoding="utf-8",
    )

    violations = check_raw_mutation_atomicity_boundaries(tmp_path)

    assert any(
        "apply_labels_batch()" in item and "directly mutates" in item
        for item in violations
    )


def test_repository_raw_mutation_atomicity_boundaries_are_clean() -> None:
    root = Path(__file__).resolve().parents[4]

    assert check_raw_mutation_atomicity_boundaries(root) == []
