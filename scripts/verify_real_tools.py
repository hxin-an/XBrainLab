import logging
import os
import sys
import time

# Setup paths
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(PROJECT_ROOT)
sys.path.append(os.getcwd())

# Import Real Tools
from XBrainLab.backend.load_data.raw_data_loader import (
    RawDataLoaderFactory,
    load_gdf_file,
)
from XBrainLab.backend.study import Study

# Register loaders
RawDataLoaderFactory.register_loader(".gdf", load_gdf_file)

from XBrainLab.llm.tools.real.dataset_real import (
    RealAttachLabelsTool,
    RealClearDatasetTool,
    RealGenerateDatasetTool,
    RealGetDatasetInfoTool,
    RealListFilesTool,
    RealLoadDataTool,
)
from XBrainLab.llm.tools.real.preprocess_real import (
    RealBandPassFilterTool,
    RealChannelSelectionTool,
    RealEpochDataTool,
    RealNormalizeTool,
    RealNotchFilterTool,
    RealRereferenceTool,
    RealResampleTool,
)
from XBrainLab.llm.tools.real.training_real import (
    RealConfigureTrainingTool,
    RealSetModelTool,
    RealStartTrainingTool,
)
from XBrainLab.llm.tools.real.ui_control_real import RealSwitchPanelTool


def run_verification():
    # Setup Output Directory
    OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    LOG_FILE = os.path.join(OUTPUT_DIR, "verification_log.txt")

    # Clear existing log
    if os.path.exists(LOG_FILE):
        os.remove(LOG_FILE)

    # Setup Logger
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    logger = logging.getLogger(__name__)

    logger.info("Starting Comprehensive Real Tools Verification")
    study = Study()

    # --- Paths ---
    data_dir = os.path.abspath(os.path.join(PROJECT_ROOT, "tests/data"))
    data_path = os.path.join(data_dir, "A01T.gdf")
    label_path = os.path.join(data_dir, "label", "A01T.mat")

    if not os.path.exists(data_path):
        logger.error(f"Data file not found at {data_path}")
        return

    # 1. Dataset Tools Verification
    logger.info("--- Step 1: Dataset Tools ---")

    # 1.1 List Files
    list_tool = RealListFilesTool()
    res_list = list_tool.execute(study, directory=data_dir, pattern="*.gdf")
    logger.info(f"List Files Result: {res_list}")

    # 1.2 Load Data
    logger.info(f"Loading {data_path}")
    load_tool = RealLoadDataTool()
    res_load = load_tool.execute(study, paths=[data_path])
    logger.info(f"Load Result: {res_load}")

    if not study.loaded_data_list:
        logger.error("Data load failed!")
        return

    # 1.3 Attach Labels
    logger.info("Attaching Labels")
    label_tool = RealAttachLabelsTool()
    # Mapping base filename to full label path
    res_label = label_tool.execute(study, mapping={"A01T.gdf": label_path})
    logger.info(f"Attach Labels Result: {res_label}")

    # 1.4 Get Info
    info_tool = RealGetDatasetInfoTool()
    logger.info(f"Dataset Info Before Clear:\n{info_tool.execute(study)}")

    # 1.5 Clear Dataset (Requested Verification)
    logger.info("Testing RealClearDatasetTool...")
    clear_tool = RealClearDatasetTool()
    res_clear = clear_tool.execute(study)
    logger.info(f"Clear Result: {res_clear}")

    if study.loaded_data_list:
        logger.error("Dataset was NOT cleared!")
        return
    logger.info("Dataset successfully cleared.")

    # 1.6 Reload (Restore State)
    logger.info("Reloading Data for Preprocessing Steps...")
    load_tool.execute(study, paths=[data_path])
    label_tool.execute(study, mapping={"A01T.gdf": label_path})
    logger.info("Data reloaded and labels attached.")

    # 2. Preprocessing Verification
    logger.info("\n--- Step 2: Preprocessing Tools ---")

    # 2.1 Channel Selection (e.g., first 3 channels)
    # Note: Need valid channel names. Usually EEG-*, or typical 10-20.
    # Let's inspect current channels first or just try indices if tool supports it?
    # Tool only supports names list.
    # Let's grab names from info if possible, or just skip if dangerous.
    # We can try commonly available channels. 'EEG-Fz', 'EEG-0', etc.
    # Check info again
    # logger.info(f"Channels: {study.loaded_data_list[0].raw.info['ch_names']}")
    # For safety, let's select first 3 channels dynamically if possible,
    # or skip to avoid error.
    # If we are using A01T, it has 22 EEG + 3 EOG.
    sel_channels = study.loaded_data_list[0].mne_data.info["ch_names"][:3]
    logger.info(f"Selecting channels: {sel_channels}")

    chan_tool = RealChannelSelectionTool()
    res_chan = chan_tool.execute(study, channels=sel_channels)
    logger.info(f"Channel Selection Result: {res_chan}")

    # 2.2 Resample
    logger.info("Resampling to 128Hz")
    resample_tool = RealResampleTool()
    res_resample = resample_tool.execute(study, rate=128)
    logger.info(f"Resample Result: {res_resample}")

    # 2.3 Notch Filter
    logger.info("Applying Notch Filter (50Hz)")
    notch_tool = RealNotchFilterTool()
    res_notch = notch_tool.execute(study, freq=50)
    logger.info(f"Notch Filter Result: {res_notch}")

    # 2.4 Bandpass Filter
    logger.info("Applying Bandpass Filter (8-30Hz)")
    bp_tool = RealBandPassFilterTool()
    res_bp = bp_tool.execute(study, low_freq=8, high_freq=30)
    logger.info(f"Bandpass Result: {res_bp}")

    # 2.5 Rereference
    logger.info("Applying CAR Rereference")
    reref_tool = RealRereferenceTool()
    # 'CAR' or 'average' depending on backend
    res_reref = reref_tool.execute(study, method="CAR")
    logger.info(f"Rereference Result: {res_reref}")

    # 2.6 Normalize
    logger.info("Applying Z-Score Normalization")
    norm_tool = RealNormalizeTool()
    res_norm = norm_tool.execute(study, method="z-score")
    logger.info(f"Normalize Result: {res_norm}")

    # 2.7 Epoching
    logger.info("Epoching Data (0-4s)")
    epoch_tool = RealEpochDataTool()
    res_epoch = epoch_tool.execute(study, t_min=0, t_max=4)
    logger.info(f"Epoch Result: {res_epoch}")

    # 3. UI Control Verification
    logger.info("\n--- Step 3: UI Control Tools ---")
    ui_tool = RealSwitchPanelTool()
    res_ui = ui_tool.execute(study, panel_name="Training", view_mode="advanced")
    logger.info(f"Switch Panel Result: {res_ui}")
    assert "Switch UI to 'Training'" in res_ui

    # 4. Training Workflow Verification
    logger.info("\n--- Step 4: Training Workflow ---")

    # 4.1 Set Model
    logger.info("Setting Model to EEGNet")
    model_tool = RealSetModelTool()
    res_model = model_tool.execute(study, model_name="EEGNet")
    logger.info(f"Set Model Result: {res_model}")

    # 4.2 Configure Training
    logger.info("Configure Training")
    config_tool = RealConfigureTrainingTool()
    res_conf = config_tool.execute(
        study, epoch=1, batch_size=2, learning_rate=0.01, device="cpu"
    )
    logger.info(f"Config Result: {res_conf}")

    # 4.3 Generate Datasets
    logger.info("Generating Datasets")
    split_tool = RealGenerateDatasetTool()
    res_split = split_tool.execute(
        study,
        test_ratio=0.2,
        val_ratio=0.2,
        split_strategy="trial",
        training_mode="individual",
    )
    logger.info(f"Split Result: {res_split}")

    if not study.datasets:
        logger.error("Dataset generation failed!")
        return

    # 4.4 Start Training
    logger.info("Start Training (Dry Run)")
    start_tool = RealStartTrainingTool()
    res_start = start_tool.execute(study)
    logger.info(f"Start Training Result: {res_start}")

    time.sleep(2)
    if study.is_training():
        logger.info("Training is running!")
        study.stop_training()
        logger.info("Training stopped.")
    else:
        logger.warning("Training did not appear to start.")

    logger.info(f"\nVerification Complete! Log saved to {LOG_FILE}")


if __name__ == "__main__":
    run_verification()
