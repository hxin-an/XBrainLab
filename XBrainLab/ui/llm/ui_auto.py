from ..base import ValidateException
import os
import torch
import inspect
import numpy as np
from scipy.io import loadmat
from matplotlib import pyplot as plt
from XBrainLab.training import (
    parse_device_name,
    parse_optim_name,
)
from XBrainLab.ui.load_data import AutoCnt, AutoEdf, AutoMat, AutoNp, AutoSet
from .DataType import DataTypeBox
from tkinter import messagebox
import tkinter as tk

class UI_Auto():
    def __init__(self, parent, llm_command, menu_items, preprocess_widgets, training_widgets, evaluation_widgets, visualization_widgets, load_data_widgets, data_path, event_path):
        if data_path is None and event_path is None:
            self.command = llm_command.get("command", "").lower()
            self.parameters = llm_command.get("parameters", {})
        else:
            self.command = "load data"
            self.parameters = []
            print(llm_command)
            for examples in llm_command:
                self.parameters.append(examples.get("parameters", {}))
        self.preprocess_command = ["filtering", "normalize", "resample", "time epoch", "export"]
        self.training_command = ["dataset splitting", "model selection", "training setting", "training manager"]
        self.evaluation_command = ["confusion matrix", "performance table", "export model"]
        self.visualization_command = ["saliency map", "saliency topographic map", "saliency spectrogram", "3d saliency plot", "model summary", "clean plots", "Set Saliency Methods"]
        self.load_command = ["load data"]
        self.menu_items = menu_items
        self.preprocess_widgets = preprocess_widgets
        self.training_widgets = training_widgets
        self.evaluation_widgets = evaluation_widgets
        self.visualization_widgets = visualization_widgets
        self.load_data_widgets = load_data_widgets
        self.root = parent
        self.data_path = data_path
        self.event_path = event_path

    def open_training_settings_window(self):
        """ Function to create a pop-up window for modifying training settings """
        settings_window = tk.Toplevel(self.root)
        settings_window.title("Modify Training Settings")
        settings_window.geometry("300x300")

        entries = {}

        default_params = {
            "Epoch": self.parameters.get("epoch", 100),
            "Batch Size": self.parameters.get("batch size", 32),
            "Learning Rate": self.parameters.get("learning rate", 0.001),
            "Optimizer": self.parameters.get("optimizer", "adam"),
            "Output Directory": self.parameters.get("output directory", "./output"),
            "Checkpoint Epoch": self.parameters.get("checkpoint epoch", 10),
            "Evaluation": self.parameters.get("evaluation", "accuracy"),
            "Repeat": self.parameters.get("repeat", 1),
        }

        row = 0
        for key, value in default_params.items():
            tk.Label(settings_window, text=key).grid(row=row, column=0, sticky="w", padx=10, pady=5)
            entry = tk.Entry(settings_window)
            entry.insert(0, str(value))
            entry.grid(row=row, column=1, padx=10, pady=5)
            entries[key] = entry
            row += 1

        def save_settings():
            try:
                # Update parameters from user input
                self.parameters["epoch"] = int(entries["Epoch"].get())
                self.parameters["batch size"] = int(entries["Batch Size"].get())
                self.parameters["learning rate"] = float(entries["Learning Rate"].get())
                self.parameters["optimizer"] = entries["Optimizer"].get()
                self.parameters["output directory"] = entries["Output Directory"].get()
                self.parameters["checkpoint epoch"] = int(entries["Checkpoint Epoch"].get())
                self.parameters["evaluation"] = entries["Evaluation"].get()
                self.parameters["repeat"] = int(entries["Repeat"].get())
                settings_window.destroy()
                print("start")
                self.root.after(1, self.set_values)
                print("end save")
                self.menu_items["Training"]["submenu"].invoke(0)
                self.set_plan()
            except ValueError:
                messagebox.showerror("Input Error", "Please enter valid numbers for numerical fields!")

        # Buttons to confirm or cancel
        tk.Button(settings_window, text="OK", command=save_settings).grid(row=row, column=0, pady=10)
        tk.Button(settings_window, text="Cancel", command=settings_window.destroy).grid(row=row, column=1, pady=10)

    def action_mapping(self):
        if self.command in self.preprocess_command:
            preprocess_menu = self.menu_items["Preprocess"]
            for i in range(preprocess_menu.index("end") + 1):
                if preprocess_menu.entrycget(i, "label").lower() == self.command:
                    self.root.after(1, self.set_values)
                    preprocess_menu.invoke(i)
                    break
        elif self.command in self.training_command:
            print(self.command)
            training_menu = self.menu_items["Training"]["menu"]
            for i in range(training_menu.index("end") + 1):
                if training_menu.entrycget(i, "label").lower() == self.command:
                    if self.command == "training setting":
                        self.open_training_settings_window()
                        # self.root.after(1, self.set_values)
                        # self.menu_items["Training"]["submenu"].invoke(0)
                        # self.set_plan()
                        break
                    self.root.after(1, self.set_values)
                    training_menu.invoke(i)
                    break
        elif self.command in self.evaluation_command:
            if self.command == "Export Model":
                self.command = "Export Model Output (csv)"
            print(self.command)
            evaluation_menu = self.menu_items["Evaluation"]
            for i in range(evaluation_menu.index("end") + 1):
                if evaluation_menu.entrycget(i, "label").lower() == self.command:
                    self.root.after(1, self.set_values)
                    evaluation_menu.invoke(i)
                    break
        elif self.command in self.visualization_command:
            print(self.command)
            visualization_menu = self.menu_items["Visualization"]
            for i in range(visualization_menu.index("end") + 1):
                if visualization_menu.entrycget(i, "label").lower() == self.command:
                    self.root.after(1, self.set_values)
                    visualization_menu.invoke(i)
                    print("invoke")
                    break
        elif self.command in self.load_command:
            print(self.command)
            load_data_menu = self.menu_items["Import data"]
            filename = self.parameters[0].get("data")
            file_type = filename[-3:]
            type_mapping = {
                "set": (self.set_import_value, "Import SET file (EEGLAB toolbox)", AutoSet),
                "mat": (self.set_import_value, "Import MAT file (Matlab array)", AutoMat),
                "edf": (self.set_import_value, "Import EDF/EDF+/GDF file (BIOSIG toolbox)", AutoEdf),
                "df+": (self.set_import_value, "Import EDF/EDF+/GDF file (BIOSIG toolbox)", AutoEdf),
                "gdf": (self.set_import_value, "Import EDF/EDF+/GDF file (BIOSIG toolbox)", AutoEdf),
                "cnt": (self.set_import_value, "Import CNT file (Neuroscan)", AutoCnt),
                "npy": (self.set_import_value, "Import NPY/NPZ file (Numpy array)", AutoNp),
                "npz": (self.set_import_value, "Import NPY/NPZ file (Numpy array)", AutoNp),
            }
            if file_type in type_mapping:
                method, menu_name, auto_class = type_mapping[file_type]
                method(auto_class, menu_name, load_data_menu)

    def set_import_value(self, auto_class, menu_name, load_data_menu):
        data_path = []
        event_path = []
        subject = []
        session = []
        for param in self.parameters:
            print(param)
            data_path.append(f"{self.data_path}\\{param.get('data')}")
            event_path.append(f"{self.event_path}\\{param.get('event')}")
            subject.append(param.get("subject"))
            session.append(param.get("session"))
        
        if auto_class in [AutoMat, AutoNp]:
            type_ctrl = self.check_data_dimensions(data_path[0])
            print(type_ctrl)
        else:
            type_ctrl = 'raw'
        
        auto_instance = auto_class(self.root, data_path, event_path, subject, session, type_ctrl)
        auto_instance.load_data()
        if self.event_path is not None:
            auto_instance.load_events()
        else:
            auto_instance.assign_ids()

        self.root.after(1, self.finalize_widget, menu_name, auto_instance)
        # load_data_menu.invoke(list(self.menu_items["Import data"].keys()).index(menu_name))
        for i in range(load_data_menu.index("end") + 1):
            if load_data_menu.entrycget(i, "label") == menu_name:
                load_data_menu.invoke(i)
                break

    def check_data_dimensions(self, filepath):
        _, ext = os.path.splitext(filepath)
        
        try:
            if ext == '.mat':
                # Load MATLAB file
                data = loadmat(filepath)
                # Look for the largest array
                largest_array = max((v for v in data.values() if isinstance(v, np.ndarray)), key=lambda x: x.size)
                return 'raw' if largest_array.ndim == 2 else 'epochs' if largest_array.ndim == 3 else 'Unknown'
            
            elif ext in ['.npz', '.npy']:
                # Load NumPy file
                data = np.load(filepath, allow_pickle=True)
                if isinstance(data, np.lib.npyio.NpzFile):  # .npz file
                    largest_array = max((v for v in data.values() if isinstance(v, np.ndarray)), key=lambda x: x.size)
                else:  # .npy file
                    largest_array = data
                return 'raw' if largest_array.ndim == 2 else 'epochs' if largest_array.ndim == 3 else 'Unknown'
            
            else:
                return "Unsupported file type"
        
        except Exception as e:
            print(f"Error: {e}")
            return "Unknown"

    def finalize_widget(self, menu_name, auto_instance):
        widget = self.load_data_widgets.get(menu_name)
        if widget:
            widget.ret_val = auto_instance.get_results()
            widget.ret_script_history = auto_instance.get_script()
            widget.destroy()
        else:
            print("No widget found")

    def set_values(self):
        if self.command == "filtering":
            self.set_filter_values()
        elif self.command == "normalize":
            self.set_normalization_values()
        elif self.command == "resample":
            self.set_resample_values()
        elif self.command == "time epoch":
            self.set_timeEpoch_values()
        elif self.command == "export":
            self.set_export_values()
        elif self.command == "dataset splitting":
            self.set_data_split_values()
        elif self.command == "model selection":
            self.set_model_values()
        elif self.command == "training setting":
            self.set_training_setting_values()
        elif self.command == "training manager":
            self.set_training_manager_values()
        elif self.command == "confusion matrix":
            self.set_confusion_values()
        elif self.command == "performance table":
            self.set_performance_values()
        elif self.command == "export model output (csv)":
            self.set_export_model_values()
        elif self.command == "saliency map":
            self.set_saliency_map_values()
        elif self.command == "saliency topographic map":
            self.set_saliency_topo_values()
        elif self.command == "saliency spectrogram":
            self.set_saliency_spec_values()
        elif self.command == "3d saliency plot":
            self.set_3D_values()
        elif self.command == "model summary":
            self.set_model_summary_values()
        elif self.command == "clean plots":
            self.set_clean_plots_values()
        else:
            print("no action mapped")

    def set_filter_values(self):
        l_freq = self.parameters.get("l_freq")
        h_freq = self.parameters.get("h_freq")
        filtering_widget = self.preprocess_widgets.get("Filtering")
        if filtering_widget:
            if l_freq is not None:
                filtering_widget.field_var['l_freq'].set(str(l_freq))
            if h_freq is not None:
                filtering_widget.field_var['h_freq'].set(str(h_freq))
                filtering_widget._data_preprocess()

    def set_normalization_values(self):
        norm_method = self.parameters.get("method")
        normalize_widget = self.preprocess_widgets.get("Normalize")
        if normalize_widget:
            if norm_method is not None:
                if norm_method == "z score":
                    normalize_widget.norm_ctrl.set("z score")
                elif norm_method == "min max":
                    normalize_widget.norm_ctrl.set("minmax")
                else:
                    print(f"Unknown normalization method: {norm_method}")
                    return
                normalize_widget._data_preprocess()

    def set_resample_values(self):
        sfreq = self.parameters.get("frequency")
        resample_widget = self.preprocess_widgets.get("Resample")
        if resample_widget:
            if sfreq is not None:
                resample_widget.field_var['sfreq'].set(str(sfreq))
            resample_widget._data_preprocess()
    
    def set_timeEpoch_values(self):
        select_events = self.parameters.get("event")
        epoch_tmin = self.parameters.get("start_time")
        epoch_tmax = self.parameters.get("end_time")
        baseline_tmin = self.parameters.get("baseline_tmin")
        baseline_tmax = self.parameters.get("baseline_tmax")
        doRemoval = self.parameters.get("doRemoval")
        timeEpoch_widget = self.preprocess_widgets.get("Time Epoch")
        if timeEpoch_widget:
            if select_events is not None:
                event_ids = {str(e): idx for idx, e in enumerate(select_events)}
                timeEpoch_widget.event_id = event_ids
                timeEpoch_widget.field_var['select_events'].set(",".join(str(event) for event in select_events))
            if epoch_tmin is not None:
                timeEpoch_widget.field_var['epoch_tmin'].set(str(epoch_tmin))
            if epoch_tmax is not None:
                timeEpoch_widget.field_var['epoch_tmax'].set(str(epoch_tmax))
            if baseline_tmin is not None:
                timeEpoch_widget.field_var['baseline_tmin'].set(str(baseline_tmin))
            if baseline_tmax is not None:
                timeEpoch_widget.field_var['baseline_tmax'].set(str(baseline_tmax))
            if doRemoval is None:
                timeEpoch_widget.field_var['doRemoval'].set(0)
                timeEpoch_widget._click_checkbox()
            timeEpoch_widget._extract_epoch()

    def set_export_values(self):
        path = self.parameters.get("path")
        export_widget = self.preprocess_widgets.get("Export")
        if export_widget:
            if path is not None:
                if not os.path.exists(path):
                    os.makedirs(path)
                export_widget.file_location_entry.set(path)
                # Trigger the export process directly:
                # export_widget.return_data = export_widget.preprocessor.data_preprocess(path)

    def set_data_split_values(self):
        training_type = self.parameters.get("training_type")
        testing_type = self.parameters.get("testing_type")
        validation_type = self.parameters.get("validation_type")
        cross_validation = self.parameters.get("cross_validation")
        data_split_widget = self.training_widgets.get("Dataset splitting")
        if data_split_widget:
            if training_type is not None:
                data_split_widget.handle_data(training_type)
            if testing_type is not None:
                data_split_widget.testing_var_list[0].set(testing_type)
            if validation_type is not None:
                data_split_widget.validation_var_list[0].set(validation_type)
            if cross_validation is not None:
                data_split_widget.cross_validation_var.set(cross_validation)
            data_split_widget.confirm()

    def set_model_values(self):
        model = self.parameters.get("model")
        model_select_widget = self.training_widgets.get("Model Selection")
        if model_select_widget:
            if model is not None:
                model_select_widget.selected_model_name.set(model)
            model_select_widget.confirm()
    
    def check_device(self):
        if torch.cuda.is_available() and torch.cuda.device_count() > 0:
            use_cpu = False
            gpu_idx = 0
        else:
            use_cpu = True
            gpu_idx = None
        return use_cpu, gpu_idx

    def set_training_setting_values(self):
        epoch = self.parameters.get("epoch")
        batch_size = self.parameters.get("batch size")
        learning_rate = self.parameters.get("learning rate")
        optimizer = self.parameters.get("optimizer")
        output_directory = self.parameters.get("output directory")
        checkpoint = self.parameters.get("checkpoint epoch")
        evaluation = self.parameters.get("evaluation")
        repeat = self.parameters.get("repeat")
           
        train_setting_widget = self.training_widgets.get("Training Setting")
        if train_setting_widget:
            if epoch is not None:
                train_setting_widget.epoch_entry.insert(0, epoch)
            if batch_size is not None:
                train_setting_widget.bs_entry.insert(0, batch_size)
            if learning_rate is not None:
                train_setting_widget.lr_entry.insert(0, learning_rate)
            if checkpoint is not None:
                train_setting_widget.checkpoint_entry.insert(0, checkpoint)
            if optimizer is not None:
                # Step 1: Retrieve the optimizer class based on the provided optimizer_name
                algo_map = {c[0]: c[1] for c in inspect.getmembers(torch.optim, inspect.isclass)}
                if optimizer not in algo_map:
                    raise ValueError(f"Optimizer '{optimizer}' not found in torch.optim.")
                optimizer_cls = algo_map[optimizer]

                signature = inspect.signature(optimizer_cls.__init__)
                optim_params = {}
                reason = None
                for param_name, param in signature.parameters.items():
                    if param_name in ['self', 'params', 'lr']:
                        continue
                    if param.default != inspect.Parameter.empty:
                        optim_params[param_name] = param.default

                # Step 3: Validate and set parameter types to prevent incorrect inputs
                for param_name, param_value in optim_params.items():
                    if isinstance(param_value, str):
                        if param_value.lower() == 'true':
                            param_value = True
                        elif param_value.lower() == 'false':
                            param_value = False
                        elif len(param_value.split()) > 1:
                            param_value = [float(v) for v in param_value.split()]
                        else:
                            try:
                                param_value = float(param_value)
                            except ValueError:
                                reason = f"Invalid parameter value '{param_value}' for '{param_name}'"
                                break
                    optim_params[param_name] = param_value

                # Step 4: Check if parameters are valid by trying to initialize the optimizer
                try:
                    optimizer = optimizer_cls([torch.Tensor()], lr=1, **optim_params)
                except Exception as e:
                    reason = f"Invalid parameter in optimizer initialization: {str(e)}"

                # Step 5: Set optimizer and optim_params in train_setting_widget if no errors
                if reason:
                    print(reason)
                    raise ValueError(reason)
                else:
                    train_setting_widget.optim = optimizer_cls
                    train_setting_widget.optim_params = optim_params
                    train_setting_widget.opt_label.config(text=parse_optim_name(optimizer_cls, optim_params))
            if 1: # set device
                if torch.cuda.is_available() and torch.cuda.device_count() > 0:
                    use_cpu = False
                    gpu_idx = 0
                else:
                    use_cpu = True
                    gpu_idx = None
                train_setting_widget.dev_label.config(text=parse_device_name(use_cpu, gpu_idx))
                train_setting_widget.use_cpu = use_cpu
                train_setting_widget.gpu_idx = gpu_idx
            if output_directory is not None:
                if not os.path.exists(output_directory):
                    os.makedirs(output_directory)
                train_setting_widget.output_dir_label.config(text=output_directory)
                train_setting_widget.output_dir = output_directory
            if evaluation is not None:
                train_setting_widget.evaluation_var.set(evaluation)
            if repeat is not None:
                train_setting_widget.repeat_entry.insert(0, repeat)
            train_setting_widget.confirm()
        # start training in training manager
        visualization_menu = self.menu_items["Visualization"]
        for i in range(visualization_menu.index("end") + 1):
            if visualization_menu.entrycget(i, "label").lower() == "set saliency methods":
                self.root.after(1, self.set_saliency)
                visualization_menu.invoke(i)
                break

    def set_saliency(self):
        set_saliency_widget = self.visualization_widgets.get("Set Saliency Methods")
        if set_saliency_widget:
            set_saliency_widget.confirm()

    def set_plan(self):
        training_menu = self.menu_items["Training"]["menu"]
        for i in range(training_menu.index("end") + 1):
            if training_menu.entrycget(i, "label") == "Generate Training Plan":
                self.root.after(1, self.set_start)
                print("widget of generate training plan")
                training_menu.invoke(i)
                break

    def set_start(self):
        train_manager_widget = self.training_widgets.get("Training Manager")
        if train_manager_widget:
            train_manager_widget.start_training()
            train_manager_widget.destroy()

    def set_training_manager_values(self):
        plot = self.parameters.get("plot")
        train_manager_widget = self.training_widgets.get("Training Manager")
        if train_manager_widget:
            training_plan_holders = train_manager_widget.training_plan_holders
            if training_plan_holders:
                if plot == "loss":
                    train_manager_widget.plot_loss()
                elif plot == "accuracy":
                    train_manager_widget.plot_acc()
                elif plot == "auc":
                    train_manager_widget.plot_auc()
                else:
                    train_manager_widget.plot_lr()
                # last_training_plan = training_plan_holders[-1]  # Get the last training plan
                # plan_name = last_training_plan.get_name()  # Get the name of the last training plan
                
                # first_repeat = last_training_plan.get_plans()[0] if last_training_plan.get_plans() else None
                
                # if first_repeat:
                #     if plot == "loss":
                #         plot_type = PlotType.LOSS
                #     elif plot == "accuracy":
                #         plot_type = PlotType.ACCURACY
                #     elif plot == "auc":
                #         plot_type = PlotType.AUC
                #     elif plot == "learning rate":
                #         plot_type = PlotType.LR
                #     plot_window = PlotFigureWindow(
                #         parent=train_manager_widget,
                #         trainers=[last_training_plan],  # Assuming last_training_plan is the trainer object
                #         plot_type=plot_type,  # Change this based on the plot type you want
                #         plan_name=plan_name,
                #         real_plan_name=first_repeat.get_name()  # Name of the first repeat plan
                #     )
                    
    def set_confusion_values(self):
        confusion_widget = self.evaluation_widgets.get("Confusion matrix")
        if confusion_widget:
            # user may select plan and repeat
            return
        
    def set_performance_values(self):
        plot = self.parameters.get("type")
        performance_widget = self.evaluation_widgets.get("Performance Table")
        if performance_widget:
            performance_widget.selected_metric.set(plot)

    def set_export_model_values(self):
        path = self.parameters.get("path")
        export_model_widget = self.evaluation_widgets.get("Export Model Output (csv)")
        if export_model_widget:
            plan = len(export_model_widget.training_plan_list)
            export_model_widget.selected_plan_name.set(export_model_widget.training_plan_list[plan-1])
            # user may select plan and repeat
            # export_model_widget.selected_real_plan_name.set(export_model_widget.real_plan_list[0])
            # if path is None:
            #     path = "./export_model"
            # if not os.path.exists(path):
            #         os.makedirs(path)
            # export_model_widget.filename.set(path)

    def set_saliency_map_values(self):
        saliency_widget = self.visualization_widgets.get("Saliency map")

    def set_saliency_topo_values(self):
        saliency_widget = self.visualization_widgets.get("Saliency topographic map")

    def set_saliency_spec_values(self):
        saliency_widget = self.visualization_widgets.get("Saliency spectrogram")
    
    def set_3D_values(self):
        saliency_widget = self.visualization_widgets.get("3D Saliency plot")

    def set_model_summary_values(self):
        summary_widget = self.visualization_widgets.get("Model Summary")
        try:
            plan_list = list(summary_widget.trainer_map.keys())
            summary_widget.selected_plan_name.set(plan_list[-1])
        except Exception:
            pass
        
    def set_clean_plots_values(self):
        plt.close('all')
