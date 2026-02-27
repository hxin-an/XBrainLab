"""Unit tests for BaseTool — abstract interface contract."""

from unittest.mock import MagicMock

import pytest

from XBrainLab.llm.tools.base import BaseTool


class TestBaseTool:
    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError):
            BaseTool()

    def test_concrete_subclass(self):
        class ConcreteTool(BaseTool):
            @property
            def name(self):
                return "test_tool"

            @property
            def description(self):
                return "A test tool"

            @property
            def parameters(self):
                return {"type": "object", "properties": {}}

            def execute(self, study, **kwargs):
                return "executed"

        tool = ConcreteTool()
        assert tool.name == "test_tool"
        assert tool.description == "A test tool"
        assert isinstance(tool.parameters, dict)
        assert tool.execute(MagicMock()) == "executed"

    def test_is_valid_default_true(self):
        class ConcreteTool(BaseTool):
            @property
            def name(self):
                return "t"

            @property
            def description(self):
                return "d"

            @property
            def parameters(self):
                return {}

            def execute(self, study, **kwargs):
                return ""

        tool = ConcreteTool()
        assert tool.is_valid(MagicMock()) is True

    def test_is_valid_override(self):
        class ConditionalTool(BaseTool):
            @property
            def name(self):
                return "t"

            @property
            def description(self):
                return "d"

            @property
            def parameters(self):
                return {}

            def is_valid(self, study):
                return hasattr(study, "data_loaded") and study.data_loaded

            def execute(self, study, **kwargs):
                return ""

        tool = ConditionalTool()
        study = MagicMock()
        study.data_loaded = False
        assert tool.is_valid(study) is False

        study.data_loaded = True
        assert tool.is_valid(study) is True

    def test_missing_abstract_methods(self):
        class PartialTool(BaseTool):
            @property
            def name(self):
                return "t"

            @property
            def description(self):
                return "d"

            # Missing parameters and execute

        with pytest.raises(TypeError):
            PartialTool()

    def test_requires_confirmation_default_false(self):
        class SimpleTool(BaseTool):
            @property
            def name(self):
                return "simple"

            @property
            def description(self):
                return "d"

            @property
            def parameters(self):
                return {}

            def execute(self, study, **kwargs):
                return ""

        tool = SimpleTool()
        assert tool.requires_confirmation is False

    def test_requires_confirmation_override(self):
        class DangerTool(BaseTool):
            @property
            def name(self):
                return "danger"

            @property
            def description(self):
                return "dangerous"

            @property
            def parameters(self):
                return {}

            @property
            def requires_confirmation(self):
                return True

            def execute(self, study, **kwargs):
                return ""

        tool = DangerTool()
        assert tool.requires_confirmation is True
