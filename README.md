# XBrainLab LLM Extension

This repository extends **XBrainLab** with an AI-assisted automation layer, where a Large Language Model (LLM) can interpret natural language and map it into GUI commands to automate EEG analysis workflows.

Our design principle is to **minimize modification to the original XBrainLab**, so that most LLM-related functions are added as new modules, while only minimal changes are made to the existing UI.

---
## File Structure

### Local (XBrainLab GUI)
- **Modified Files**
  - `dash_board.py`  
    - Modified `init_menu()` to record menu widget actions, enabling LLM automation.  
    - Added two helper functions:  
      - `open_ui_helper()` – opens the UI helper for LLM interaction.  
      - `save_chat_history()` – saves chat history for context.

- **Newly Added**
  - `ui/llm/` – folder for LLM-UI integration.  
    - `ChatDialog.py`  
      - Defines the UI helper dialog.  
      - Connects to the server-side model and displays responses.  
    - `ui_auto.py`  
      - Automates GUI execution based on user-confirmed commands.
  
- **Installation**
  - From latest code:
      ```
      pip install --upgrade git+https://github.com/CECNL/XBrainLab.git@AI-agent
      ```
`
    
- **Getting Started**
  - Type in your terminal, and the GUI application will start automatically.
    ```
    XBrainLab
    ```
  - Or download the zip file and run `python run.py`

---
### Remote (runs independently on server)
- **Core Files**
  - `prompts.py`  
    - Predefined prompts for different tasks: preprocessing, training, evaluation, visualization, start.
  - `agent.py`  
    - Runs the Gemma-2b-it model on the server and exposes an API port for local calls.  
    - Includes:  
      - Prompt selection and RAG-based retrieval.  
      - Integration of local chat history + user input.  
      - Command generation via `generate_command(input_text, retrieved_info)` (3x inference).  
      - Command parsing with `parse_commands_from_output(output)` to extract `(command, parameter)` pairs.  
      - Majority voting to finalize execution commands.
  
  - **Enviroment**
    - `environment.yml`
      - Run `conda env create -f environment.yml --name new_name` to create the same environment used in development.

---
## Workflow Overview
1. User interacts with **XBrainLab + UI Helper** on the local machine.  
2. Local helper sends input + chat history to the **server agent**.  
3. Server-side model selects prompt, retrieves context, and generates candidate commands.  
4. Commands are parsed and validated via majority voting.  
5. Proposed commands are returned to the user for confirmation and then automatically executed by `ui_auto.py`.  

---
## Notes
- Only `dash_board.py` is minimally modified in the original XBrainLab.  
- All LLM-specific modules are added separately under `ui/llm/`.  
- Server and local components communicate over a dedicated API port.

---
## Citing
If you use LLM-XBrainLab to assist you research, please cite our paper and the related references in your publication.

XBrainLab software:
```bash
@inproceedings{
hsieh2023xbrainlab,
title={{XB}rainLab: An Open-Source Software for Explainable Artificial Intelligence-Based {EEG} Analysis},
author={Chia-ying Hsieh and Jing-Lun Chou and Yu-Hsin Chang and Chun-Shu Wei},
booktitle={NeurIPS 2023 AI for Science Workshop},
year={2023},
url={https://openreview.net/forum?id=82brfaM02h}
}
```
SCCNet implementation:
```bash
@inproceedings{wei2019spatial,
  title={Spatial component-wise convolutional network (SCCNet) for motor-imagery EEG classification},
  author={Wei, Chun-Shu and Koike-Akino, Toshiaki and Wang, Ye},
  booktitle={2019 9th International IEEE/EMBS Conference on Neural Engineering (NER)},
  pages={328--331},
  year={2019},
  organization={IEEE}
}
```
EEGNet implementation:
```bash
article{lawhern2018eegnet,
  title={EEGNet: a compact convolutional neural network for EEG-based brain--computer interfaces},
  author={Lawhern, Vernon J and Solon, Amelia J and Waytowich, Nicholas R and Gordon, Stephen M and Hung, Chou P and Lance, Brent J},
  journal={Journal of neural engineering},
  volume={15},
  number={5},
  pages={056013},
  year={2018},
  publisher={iOP Publishing}
}
```
ShallowConvNet implementation:
```bash
@article{schirrmeister2017deep,
  title={Deep learning with convolutional neural networks for EEG decoding and visualization},
  author={Schirrmeister, Robin Tibor and Springenberg, Jost Tobias and Fiederer, Lukas Dominique Josef and Glasstetter, Martin and Eggensperger, Katharina and Tangermann, Michael and Hutter, Frank and Burgard, Wolfram and Ball, Tonio},
  journal={Human brain mapping},
  volume={38},
  number={11},
  pages={5391--5420},
  year={2017},
  publisher={Wiley Online Library}
}
```
