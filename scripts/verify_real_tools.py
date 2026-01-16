import logging
import os
import sys
import time

# Setup paths
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(PROJECT_ROOT)
sys.path.append(os.getcwd())

# Import Real Tools (Moved up, but ignore E402 for path setup)
from XBrainLab.backend.load_data.raw_data_loader import (  # noqa: E402
    RawDataLoaderFactory,
    load_gdf_file,
)
from XBrainLab.backend.study import Study  # noqa: E402

# Register loaders
RawDataLoaderFactory.register_loader(".gdf", load_gdf_file)

from XBrainLab.llm.tools.real.dataset_real import (  # noqa: E402
    RealGenerateDatasetTool,
    RealGetDatasetInfoTool,
    RealLoadDataTool,
)
from XBrainLab.llm.tools.real.preprocess_real import (  # noqa: E402
    RealBandPassFilterTool,
    RealEpochDataTool,
)
from XBrainLab.llm.tools.real.training_real import (  # noqa: E402
    RealConfigureTrainingTool,
    RealSetModelTool,
    RealStartTrainingTool,
)


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

    logger.info("Initializing Study...")
    study = Study()

    # 1. Load Data
    data_path = os.path.abspath(os.path.join(PROJECT_ROOT, "tests/data/A01T.gdf"))
    if not os.path.exists(data_path):
        logger.error(f"Data file not found at {data_path}")
        return

    logger.info(f"Step 1: Loading Data from {data_path}")

    load_tool = RealLoadDataTool()
    res_load = load_tool.execute(study, paths=[data_path])
    logger.info(f"Load Result: {res_load}")

    if not study.loaded_data_list:
        logger.error("Data load failed!")
        return

    info_tool = RealGetDatasetInfoTool()
    logger.info(f"Dataset Info:\n{info_tool.execute(study)}")

    # 2. Preprocess
    logger.info("Step 2: Preprocessing (Bandpass 4-40Hz)")
    bp_tool = RealBandPassFilterTool()
    res_bp = bp_tool.execute(study, low_freq=4, high_freq=40)
    logger.info(f"Preprocess Result: {res_bp}")

    logger.info("Step 2.5: Epoching")
    epoch_tool = RealEpochDataTool()
    res_epoch = epoch_tool.execute(study, t_min=0, t_max=4)
    logger.info(f"Epoch Result: {res_epoch}")

    # Check state
    if study.preprocessed_data_list:
        first = study.preprocessed_data_list[0]
        logger.info(f"DEBUG: is_raw = {first.is_raw()}")

    # 3. Model Setup
    logger.info("Step 3: Setting Model to EEGNet")
    model_tool = RealSetModelTool()
    res_model = model_tool.execute(study, model_name="EEGNet")
    logger.info(f"Set Model Result: {res_model}")

    # 4. Configure Training
    logger.info("Step 4: Configure Training")
    config_tool = RealConfigureTrainingTool()
    res_conf = config_tool.execute(
        study, epoch=1, batch_size=2, learning_rate=0.01, device="cpu"
    )
    logger.info(f"Config Result: {res_conf}")

    # 5. Generate Dataset
    logger.info("Step 4.5: Generating Datasets")
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

    # 6. Start Training
    logger.info("Step 6: Start Training (Dry Run)")
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

    logger.info(f"Verification Complete! Log saved to {LOG_FILE}")


if __name__ == "__main__":
    run_verification()
