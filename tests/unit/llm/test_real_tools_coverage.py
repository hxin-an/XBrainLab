"""Coverage tests for real preprocess + dataset tools — validation, error, and success paths."""

from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


def _command_result(
    *,
    failed: bool = False,
    message: str = "ok",
    diagnostics: dict | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        failed=failed,
        ok=not failed,
        message=message,
        diagnostics=diagnostics or {},
    )


def _service(
    result: SimpleNamespace | None = None,
    *,
    side_effect: Exception | None = None,
) -> MagicMock:
    service = MagicMock()
    service.preprocess.batch_notifications.return_value = nullcontext()
    if side_effect is not None:
        service.execute.side_effect = side_effect
    else:
        service.execute.return_value = result or _command_result()
    return service


# --- Real Preprocess Tools ---


class TestRealBandPassValidation:
    def test_missing_params_returns_error(self):
        from XBrainLab.llm.tools.real.preprocess_real import RealBandPassFilterTool

        tool = RealBandPassFilterTool()
        assert "Error" in tool.execute(study=MagicMock(), low_freq=None, high_freq=40.0)
        assert "Error" in tool.execute(study=MagicMock(), low_freq=4.0, high_freq=None)

    @patch("XBrainLab.llm.tools.real.preprocess_real.get_application_service")
    def test_service_exception_returns_failed(self, mock_get_service):
        from XBrainLab.llm.tools.real.preprocess_real import RealBandPassFilterTool

        mock_get_service.return_value = _service(side_effect=RuntimeError("boom"))
        tool = RealBandPassFilterTool()
        result = tool.execute(study=MagicMock(), low_freq=4.0, high_freq=40.0)
        assert "Bandpass filter failed" in result


class TestRealNotchValidation:
    def test_missing_freq(self):
        from XBrainLab.llm.tools.real.preprocess_real import RealNotchFilterTool

        tool = RealNotchFilterTool()
        assert "Error" in tool.execute(study=MagicMock(), freq=None)

    @patch("XBrainLab.llm.tools.real.preprocess_real.get_application_service")
    def test_service_exception(self, mock_get_service):
        from XBrainLab.llm.tools.real.preprocess_real import RealNotchFilterTool

        mock_get_service.return_value = _service(side_effect=RuntimeError("x"))
        tool = RealNotchFilterTool()
        assert "Notch filter failed" in tool.execute(study=MagicMock(), freq=50.0)


class TestRealResampleValidation:
    def test_missing_rate(self):
        from XBrainLab.llm.tools.real.preprocess_real import RealResampleTool

        assert "Error" in RealResampleTool().execute(study=MagicMock(), rate=None)

    @patch("XBrainLab.llm.tools.real.preprocess_real.get_application_service")
    def test_service_exception(self, mock_get_service):
        from XBrainLab.llm.tools.real.preprocess_real import RealResampleTool

        mock_get_service.return_value = _service(side_effect=RuntimeError("x"))
        assert "Resample failed" in RealResampleTool().execute(
            study=MagicMock(), rate=256
        )


class TestRealNormalizeValidation:
    def test_missing_method(self):
        from XBrainLab.llm.tools.real.preprocess_real import RealNormalizeTool

        assert "Error" in RealNormalizeTool().execute(study=MagicMock(), method=None)

    @patch("XBrainLab.llm.tools.real.preprocess_real.get_application_service")
    def test_service_exception(self, mock_get_service):
        from XBrainLab.llm.tools.real.preprocess_real import RealNormalizeTool

        mock_get_service.return_value = _service(side_effect=RuntimeError("x"))
        assert "Normalization failed" in RealNormalizeTool().execute(
            study=MagicMock(), method="z-score"
        )


class TestRealRereferenceValidation:
    def test_missing_method(self):
        from XBrainLab.llm.tools.real.preprocess_real import RealRereferenceTool

        assert "Error" in RealRereferenceTool().execute(study=MagicMock(), method=None)

    @patch("XBrainLab.llm.tools.real.preprocess_real.get_application_service")
    def test_service_exception(self, mock_get_service):
        from XBrainLab.llm.tools.real.preprocess_real import RealRereferenceTool

        mock_get_service.return_value = _service(side_effect=RuntimeError("x"))
        assert "Re-reference failed" in RealRereferenceTool().execute(
            study=MagicMock(), method="average"
        )


class TestRealChannelSelectionValidation:
    def test_missing_channels(self):
        from XBrainLab.llm.tools.real.preprocess_real import RealChannelSelectionTool

        assert "Error" in RealChannelSelectionTool().execute(
            study=MagicMock(), channels=None
        )

    @patch("XBrainLab.llm.tools.real.preprocess_real.get_application_service")
    def test_service_exception(self, mock_get_service):
        from XBrainLab.llm.tools.real.preprocess_real import RealChannelSelectionTool

        mock_get_service.return_value = _service(side_effect=RuntimeError("x"))
        assert "Channel selection failed" in RealChannelSelectionTool().execute(
            study=MagicMock(), channels=["C3"]
        )


class TestRealSetMontageValidation:
    def test_missing_montage_name(self):
        from XBrainLab.llm.tools.real.preprocess_real import RealSetMontageTool

        assert "Error" in RealSetMontageTool().execute(
            study=MagicMock(), montage_name=None
        )


class TestRealEpochDataError:
    @patch("XBrainLab.llm.tools.real.preprocess_real.get_application_service")
    def test_service_exception(self, mock_get_service):
        from XBrainLab.llm.tools.real.preprocess_real import RealEpochDataTool

        mock_get_service.return_value = _service(side_effect=RuntimeError("bad epoch"))
        result = RealEpochDataTool().execute(study=MagicMock(), t_min=-0.1, t_max=1.0)
        assert "Epoching failed" in result


class TestRealStandardPreprocessOptionalSteps:
    """Cover the optional branches in RealStandardPreprocessTool."""

    @patch("XBrainLab.llm.tools.real.preprocess_real.get_application_service")
    def test_all_optional_steps(self, mock_get_service):
        from XBrainLab.backend.application import PreprocessCommand, PreprocessOperation
        from XBrainLab.llm.tools.real.preprocess_real import RealStandardPreprocessTool

        service = _service(_command_result())
        mock_get_service.return_value = service

        tool = RealStandardPreprocessTool()
        result = tool.execute(
            study=MagicMock(),
            l_freq=4.0,
            h_freq=40.0,
            notch_freq=50.0,
            resample_rate=256,
            rereference="average",
            normalize_method="z-score",
        )
        assert "successfully" in result.lower()
        operations = [
            call.args[0].operation
            for call in service.execute.call_args_list
            if isinstance(call.args[0], PreprocessCommand)
        ]
        assert operations == [
            PreprocessOperation.BANDPASS,
            PreprocessOperation.NOTCH,
            PreprocessOperation.RESAMPLE,
            PreprocessOperation.REREFERENCE,
            PreprocessOperation.NORMALIZE,
        ]


# --- Real Dataset Tools ---


class TestRealListFilesValidation:
    def test_empty_directory(self):
        from XBrainLab.llm.tools.real.dataset_real import RealListFilesTool

        assert "Error" in RealListFilesTool().execute(study=MagicMock(), directory=None)

    @patch("XBrainLab.llm.tools.real.dataset_real.os.path.isdir", return_value=False)
    def test_nonexistent_directory(self, _mock):
        from XBrainLab.llm.tools.real.dataset_real import RealListFilesTool

        result = RealListFilesTool().execute(
            study=MagicMock(), directory="/nonexistent/path"
        )
        assert "does not exist" in result

    @patch(
        "XBrainLab.llm.tools.real.dataset_real.os.listdir",
        return_value=["a.gdf", "b.set", "c.gdf"],
    )
    @patch("XBrainLab.llm.tools.real.dataset_real.os.path.isdir", return_value=True)
    def test_pattern_filtering(self, _mock_isdir, _mock_listdir):
        from XBrainLab.llm.tools.real.dataset_real import RealListFilesTool

        result = RealListFilesTool().execute(
            study=MagicMock(), directory="/data", pattern="*.gdf"
        )
        assert "a.gdf" in result
        assert "c.gdf" in result
        assert "b.set" not in result


class TestRealListFilesSecurity:
    def test_sensitive_dir_blocked(self):
        from XBrainLab.llm.tools.real.dataset_real import RealListFilesTool

        result = RealListFilesTool().execute(
            study=MagicMock(), directory="C:\\Windows\\System32"
        )
        assert "not allowed" in result or "Error" in result


class TestRealLoadDataValidation:
    def test_empty_paths(self):
        from XBrainLab.llm.tools.real.dataset_real import RealLoadDataTool

        assert "Error" in RealLoadDataTool().execute(study=MagicMock(), paths=None)
        assert "Error" in RealLoadDataTool().execute(study=MagicMock(), paths=[])

    @patch("XBrainLab.llm.tools.real.dataset_real.os.path.isdir", return_value=True)
    @patch(
        "XBrainLab.llm.tools.real.dataset_real.os.listdir",
        side_effect=PermissionError("no access"),
    )
    def test_directory_scan_error(self, _mock_list, _mock_isdir):
        from XBrainLab.llm.tools.real.dataset_real import RealLoadDataTool

        result = RealLoadDataTool().execute(study=MagicMock(), paths=["/secure/dir"])
        assert "Error scanning directory" in result

    @patch("XBrainLab.llm.tools.real.dataset_real.os.path.isdir", return_value=True)
    @patch("XBrainLab.llm.tools.real.dataset_real.os.listdir", return_value=[])
    def test_no_valid_files(self, _mock_list, _mock_isdir):
        from XBrainLab.llm.tools.real.dataset_real import RealLoadDataTool

        result = RealLoadDataTool().execute(study=MagicMock(), paths=["/empty/dir"])
        assert "No valid files" in result

    @patch("XBrainLab.llm.tools.real.dataset_real.get_application_service")
    @patch("XBrainLab.llm.tools.real.dataset_real.os.path.isdir", return_value=False)
    def test_partial_success(self, _mock_isdir, mock_get_service):
        from XBrainLab.llm.tools.real.dataset_real import RealLoadDataTool

        mock_get_service.return_value = _service(
            _command_result(
                diagnostics={"success_count": 2, "errors": ["err1"]},
            ),
        )
        result = RealLoadDataTool().execute(
            study=MagicMock(), paths=["/a.gdf", "/b.gdf"]
        )
        assert "Successfully loaded 2 files" in result
        assert "Errors" in result


class TestRealAttachLabelsValidation:
    def test_missing_mapping(self):
        from XBrainLab.llm.tools.real.dataset_real import RealAttachLabelsTool

        assert "Error" in RealAttachLabelsTool().execute(
            study=MagicMock(), mapping=None
        )

    @patch("XBrainLab.llm.tools.real.dataset_real.get_application_service")
    def test_no_labels_attached(self, mock_get_service):
        from XBrainLab.llm.tools.real.dataset_real import RealAttachLabelsTool

        mock_get_service.return_value = _service(
            _command_result(diagnostics={"success_count": 0}),
        )
        result = RealAttachLabelsTool().execute(study=MagicMock(), mapping={"a": "b"})
        assert "No labels attached" in result


class TestRealGetDatasetInfoEvents:
    @patch("XBrainLab.llm.tools.real.dataset_real.get_application_service")
    def test_summary_with_events(self, mock_get_service):
        from XBrainLab.llm.tools.real.dataset_real import RealGetDatasetInfoTool

        mock_get_service.return_value = _service(
            _command_result(
                diagnostics={
                    "count": 3,
                    "files": ["a.gdf", "b.gdf", "c.gdf"],
                    "total": 120,
                    "unique_count": 4,
                },
            ),
        )
        result = RealGetDatasetInfoTool().execute(study=MagicMock())
        assert "Events: 120" in result
        assert "Unique: 4" in result


class TestRealGenerateDatasetError:
    @patch("XBrainLab.llm.tools.real.dataset_real.get_application_service")
    def test_generation_failure(self, mock_get_service):
        from XBrainLab.llm.tools.real.dataset_real import RealGenerateDatasetTool

        mock_get_service.return_value = _service(
            _command_result(failed=True, message="fail"),
        )
        result = RealGenerateDatasetTool().execute(study=MagicMock())
        assert "Dataset generation failed" in result


# --- Tool Registry ---


class TestToolRegistryOverwrite:
    def test_overwrite_warning(self):
        from XBrainLab.llm.tools.tool_registry import ToolRegistry

        reg = ToolRegistry()
        mock_tool = MagicMock()
        mock_tool.name = "test_tool"
        reg.register(mock_tool)
        reg.register(mock_tool)  # second register triggers warning
        assert reg.get_tool("test_tool") is mock_tool

    def test_get_tool_existing(self):
        from XBrainLab.llm.tools.tool_registry import ToolRegistry

        reg = ToolRegistry()
        mock_tool = MagicMock()
        mock_tool.name = "x"
        reg.register(mock_tool)
        assert reg.get_tool("x") is mock_tool


# --- UI Control Real ---


class TestRealSwitchPanelNoViewMode:
    def test_no_view_mode(self):
        from XBrainLab.llm.tools.real.ui_control_real import RealSwitchPanelTool

        tool = RealSwitchPanelTool()
        result = tool.execute(study=MagicMock(), panel_name="training", view_mode=None)
        assert "training" in result.lower()
