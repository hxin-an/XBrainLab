# Quick Start

## Launch the GUI

```bash
poetry run python run.py
```

## Programmatic Usage

```python
from XBrainLab import Study

study = Study()

# 1. Load EEG data
loader = study.get_raw_data_loader()
# loader.load_from_files(...)

# 2. Preprocess
# study.preprocess(BandpassFilter, low_freq=1, high_freq=40)

# 3. Split datasets
# generator = study.get_datasets_generator(config)
# study.set_datasets(generator.generate())

# 4. Configure training (委派至 TrainingManager)
# study.set_training_option(option)
# study.set_model_holder(holder)
# study.generate_plan()

# 5. Train (委派至 TrainingManager)
# study.train()
```

> **Note**: `Study` 內部委派至 `DataManager`（資料）與 `TrainingManager`（訓練），
> 但外部 API 不變，使用者可直接透過 `study.*` 方法操作。

See the [API Reference](../api/backend/study.md) for full details.
