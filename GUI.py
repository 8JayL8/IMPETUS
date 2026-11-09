import sys
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QLabel, QWidget,
    QPushButton, QVBoxLayout, QHBoxLayout,
    QComboBox, QMessageBox, QLineEdit,
    QDialog, QDialogButtonBox, QSizePolicy, QStackedWidget,
    QTabWidget, QFormLayout, QSlider, QScrollArea
)
from PyQt6.QtCore import Qt, QTimer, QLocale
from PyQt6.QtGui import QIcon, QPainter, QColor, QPen, QDoubleValidator
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.ticker import MultipleLocator
from matplotlib.figure import Figure
import numpy as np
import matplotlib.pyplot as plt

import tracks
import file_utils
from recommendation import EnergyRecommendation

# When adding new track types, they should be added to the ALL_TRACKS list and the track_function_map dictionary below.

# ========================================================================
SECTIONS = ["Starts", "Thrills 1", "Turns", "Thrills 2", "Ends"]    # Defines the sections of the track assembly
STARTS = ["Launcher", "Lift Hill", "Rollback"]                      # Defines the starting track types
THRILLS = ["Loop", "Camelback", "Corkscrew"]                        # Defines the thrill track types
TURNS = ["Cobra Roll", "Horseshoe", "Helix"]                        # Defines the turn track types
ENDS = ["Brake", "Rollup"]                                          # Defines the ending track types
ALL_TRACKS = STARTS + THRILLS + TURNS + ENDS                        # Defines all track types for validation
RECOMMEND_SECTIONS = {                                              # Sections that get a recommended range from 'Starts'
    "Thrills 1": THRILLS,
    "Turns": TURNS,
    "Thrills 2": THRILLS,
    "Ends": ENDS,
}
CONTROL = {
    "Height": {
        "Lift Hill", "Rollback",
        "Camelback", "Corkscrew", "Loop",
        "Horseshoe", "Cobra Roll", "Helix",
        "Rollup"
    },

    "Length": {
        "Launcher",
        "Brake"
    },
}

# Physics check -> warning shown when that check fails
CHECK_WARNINGS = {
    "velocity_check": "Not enough velocity to get through this section.",
    "max_g_check": "Riders feel 5Gs or more somewhere in this section.",
    "valley_check": "Valley G-force exceeds 5Gs.",
    "inversion_check": "Too slow or too fast to clear the inversion peak.",
    "peak_check": "Speed too high over crest (Airborne).",
    "lateral_check": "Lateral turning G-forces exceed safe rider comfort (>1.5G).",
    "rollup_check": "Rollup incline is not tall enough. The coaster will fly off the track.",
    "brake_check": "Entry speed into exceeds allowed stopping threshold.",
}

# Shared stylesheets
PANEL_TITLE_STYLE = "color: blue; font-size: 20px; background-color: white; padding: 5px; border-radius: 5px;"
CARD_STYLE = "background-color: {background}; color: {text}; border-radius: 10px; margin-bottom: 2px; padding: 2px;"
REC_LABEL_STYLE = "color: {color}; font-size: 11px; padding: 0px;"
REC_OK_COLOR, REC_BAD_COLOR = "#27ae60", "#c0392b"
# ========================================================================

# Maps track types to their corresponding functions in the tracks module.
# When there are new track types, they should be added to this dictionary with their corresponding function from the tracks module.
track_function_map = {
    # Starts
    "Launcher": tracks.TrackPart.launcher_func,             # Using this will result a return to the beginning of the track
    "Lift Hill": tracks.TrackPart.lifthill_func,            # Using this will result a return to the beginning of the track
    "Rollback": tracks.TrackPart.rollback_func,             # Has no return, but can be used to begin the track with a rollback

    # Thrills
    "Loop": tracks.TrackPart.loopCG_func,
    "Camelback": tracks.TrackPart.camelback_func,
    "Corkscrew": tracks.TrackPart.corkscrew_func,

    # Turns
    "Cobra Roll": tracks.TrackPart.cobrarollCG_func,
    "Horseshoe": tracks.TrackPart.horseshoe_func,
    "Helix": tracks.TrackPart.helix_func,

    # Ends
    "Brake": tracks.TrackPart.brake_func,                   # Using this will result a return to the beginning of the track
    "Rollup": tracks.TrackPart.rollup_func                  # Has no return, but can be used to end the track with a rollup
}


# Custom Dialog Box
class StatsDialog(QDialog):
    def __init__(self, section_name, stats_data, parent=None):
        super().__init__(parent)

        self.setWindowTitle(f"Statistics - {section_name}")
        self.resize(300, 200)
        self.setStyleSheet("""
            QDialog { background-color: #f8f9fa; }
            QLabel { font-size: 12px; color: #2c3e50; }
                           """)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)

        header_label = QLabel(f"Stats Overview for {section_name}")
        header_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #2980b9;")
        main_layout.addWidget(header_label)

        form_layout = QFormLayout()
        form_layout.setSpacing(8)

        for key, value in stats_data.items():
            key_label = QLabel(f"<b>{key}:</b>")
            val_label = QLabel(str(value))
            form_layout.addRow(key_label, val_label)

        main_layout.addLayout(form_layout)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.reject)
        main_layout.addWidget(button_box)


class DualInputDialog(QDialog):
    def __init__(self, parent=None, section="", coaster=""):
        super().__init__(parent)
        self.setWindowTitle("Coaster Details")

        layout = QFormLayout(self)

        # Pre-filled with the previous build's names (empty the first time)
        self.section_input = QLineEdit(section, self)
        self.coaster_input = QLineEdit(coaster, self)

        layout.addRow("Enter Section:", self.section_input)
        layout.addRow("Enter Coaster Name:", self.coaster_input)

        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.button_box.setStyleSheet("QPushButton { color: black; }")
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addRow(self.button_box)

    def get_inputs(self):
        return self.section_input.text(), self.coaster_input.text()


# Custom Slider (draws the recommended range from recommendation.py as a green band)
class RangeIndicatorSlider(QSlider):
    def __init__(self, orientation=Qt.Orientation.Horizontal, parent=None):
        super().__init__(orientation, parent)
        # Initalize with no bounds
        self.rec_min = None
        self.rec_max = None
    
    def set_recommendation_bounds(self, rec_min, rec_max):
        self.rec_min = rec_min
        self.rec_max = rec_max
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)

        if self.rec_min is None or self.rec_max is None:
            return
        
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        slider_range = self.maximum() - self.minimum()
        if slider_range <= 0:
            return
        
        w = self.width()
        margin = 10
        usable_width = w - (2* margin)

        pos_min = margin + int(((self.rec_min - self.minimum()) / slider_range) * usable_width)
        pos_max = margin + int(((self.rec_max - self.minimum()) / slider_range) * usable_width)

        # Bound calculations to physical layout limits
        pos_min = max(margin, min(pos_min, w - margin))
        pos_max = max(margin, min(pos_max, w - margin))

        # --- Draw a transparent green background zone for the "Sweet Spot" ---
        painter.fillRect(pos_min, 4, pos_max - pos_min, self.height() - 8, QColor(46, 204, 113, 40))

        # --- Draw the Lower Target Line (Green) ---
        pen_min = QPen(QColor(39, 174, 96), 2, Qt.PenStyle.SolidLine)
        painter.setPen(pen_min)
        painter.drawLine(pos_min, 2, pos_min, self.height() - 2)

        # --- Draw the Upper Target Line (Orange/Red Warning boundary) ---
        pen_max = QPen(QColor(230, 126, 34), 2, Qt.PenStyle.SolidLine)
        painter.setPen(pen_max)
        painter.drawLine(pos_max, 2, pos_max, self.height() - 2)

        painter.end() 


# ===============================================================================
#                               User Interface
# ===============================================================================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Track RollerCoaster")
        self.setGeometry(100, 100, 1000, 680)

        self.main_widget = QWidget()
        self.main_widget.setStyleSheet("background-color: white;")
        self.setCentralWidget(self.main_widget)
        self.main_layout = QVBoxLayout(self.main_widget)

        # Title
        title = QLabel("IMPETUS Coaster Creation")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("color: white; font-size: 24px; font-weight: bold; padding: 10px; background-color: #34495e; border-radius: 10px;")
        title.setFixedHeight(60)
        self.main_layout.addWidget(title)

        # Track Panel (Assembly and Visualization)
        self.track_widget = QWidget()
        self.track_widget.setStyleSheet("background-color: green; border-radius: 10px; padding: 10px;")
        self.track_layout = QHBoxLayout(self.track_widget)

        # Assembly structures setup ahead of panel assignments
        self.section_layouts = {}
        self.tracks = {section: [] for section in SECTIONS}

        # Assembly and Visual Panels
        self.assembly_panel()
        self.visual_panel()
        self.main_layout.addWidget(self.track_widget)
        self.create_button()

        # Recommendations are recalculated shortly after the user stops typing/changing inputs
        self.recommendation_timer = QTimer(self)
        self.recommendation_timer.setSingleShot(True)
        self.recommendation_timer.setInterval(300)
        self.recommendation_timer.timeout.connect(self.update_recommendations)

        # Setup the track assembly sections (Initialize each section)
        for section in SECTIONS:
            self.track_type(section)
        self.switch_view_mode(0)

        # Initialize stats
        self.track_stats = {}
        self.checks = {}

        # Remember the last names used so the dialog is pre-filled next time
        self.last_section = ""
        self.last_coaster = ""

    # ========================================================================
    #                       Assembly Panels and Controls
    # ========================================================================
    def assembly_panel(self):
        self.assembly_widget = QWidget()
        self.assembly_widget.setStyleSheet("background-color: #34495e; border-radius: 10px; padding: 0px;")
        self.assembly_layout = QVBoxLayout(self.assembly_widget)

        track_assembly_label = QLabel("Track Assembly")
        track_assembly_label.setStyleSheet(PANEL_TITLE_STYLE)
        track_assembly_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        track_assembly_label.setFixedHeight(40)
        self.assembly_layout.addWidget(track_assembly_label)

        # Setup Mode Selector (Dropdown to switch between single page and tabbed view)
        selector_layout = QHBoxLayout()
        selector_label = QLabel("View Mode: ")
        selector_label.setStyleSheet("color: white; font-size: 14px; font-weight: bold;")

        self.setup_selector = QComboBox()
        self.setup_selector.addItems(["Setup 1: All on 1 Page", "Setup 2: Tabbed View"])
        self.setup_selector.setStyleSheet("""
            QComboBox { background-color: white; color: #2c3e50; padding: 6px; border-radius: 5px; font-size: 12px; font-weight: bold; }
            QComboBox QAbstractItemView { background-color: white; color: black; border-radius: 5px; font-size: 12px; font-weight: bold; }
                                          """)
        selector_layout.addWidget(selector_label)
        selector_layout.addWidget(self.setup_selector)
        self.assembly_layout.addLayout(selector_layout)

        self.assembly_stack = QStackedWidget()
        self.assembly_layout.addWidget(self.assembly_stack)

        self.single_page_view() # Setup 1: All on 1 page
        self.tabbed_view()      # Setup 2: Multiple pages

        self.setup_selector.currentIndexChanged.connect(self.switch_view_mode)

        # Add to the main layout, with a scale factor of 1 to make it smaller
        self.track_layout.addWidget(self.assembly_widget, 1)
        

    # ========================================================================
    #                       Visual Panels and Controls
    # ========================================================================
    def visual_panel(self):
        # Visual Widget
        self.visual_widget = QWidget()
        self.visual_widget.setStyleSheet("background-color: #bdc3c7; border-radius: 10px; padding: 10px;")
        visual_layout = QVBoxLayout(self.visual_widget)

        # Visual Label
        visual_label = QLabel("Track Visualization")
        visual_label.setStyleSheet(PANEL_TITLE_STYLE)
        visual_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        visual_label.setFixedHeight(40)
        visual_layout.addWidget(visual_label)

        # Visual Stack (Placeholder and Tab Widget)
        self.visual_content_layout = QVBoxLayout()
        visual_layout.addLayout(self.visual_content_layout)

        # Placeholder Label (Inital State)
        self.placeholder_label = QLabel("Track visualization will appear here after assembly.")
        self.placeholder_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.placeholder_label.setStyleSheet("color: #7f8c8d; font-size: 16px;")
        self.placeholder_label.setWordWrap(True)
        self.visual_content_layout.addWidget(self.placeholder_label)

        # Inital Tab Widget (Hidden until assembly is complete)
        self.visual_tab_widget = QTabWidget()
        self.visual_tab_widget.setStyleSheet("""
            background-color: white; color: blue; font-size: 12px; font-weight: bold;
            
            QTabBar::tab {
                background-color: white;
                color: #0000cc;
                font-size: 12px;
                font-weight: bold;
                padding: 6px 14px;         
                border: 1px solid #dcdcdc; 
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                margin-right: -1px;
            }
            QTabBar::tab:selected {
                background-color: white;
                color: #0000ff;
                border-bottom: 1px solid white;
            }
        """)
        self.visual_tab_widget.hide()
        self.visual_content_layout.addWidget(self.visual_tab_widget)

        # Keep track of the plots
        self.track_plots = {}

        # === Tab 1: 3D Visualization ===
        fig_3d = Figure(layout="constrained")  # Use constrained layout for better spacing
        canvas_3d = FigureCanvas(fig_3d)
        canvas_3d.setMinimumSize(200, 200)
        ax_3d = fig_3d.add_subplot(111, projection='3d')

        self.track_plots["3d"] = {
            "figure": fig_3d,
            "canvas": canvas_3d,
            "ax": ax_3d
        }
        
        tab_3d_page = QWidget()
        tab_3d_layout = QVBoxLayout(tab_3d_page)
        tab_3d_layout.setContentsMargins(0, 0, 0, 0)
        tab_3d_layout.addWidget(canvas_3d)
        self.visual_tab_widget.addTab(tab_3d_page, "3D View")

        # === Rest of the Tab: 2D Visualization ===
        tabs_2d = [
            ("whole_track_topview", "2D View (Whole Track Top View)"),
            ("whole_track_sideview", "2D View (Whole Track Side View)"),
            ("section_12", "2D View (Sections 1/2)"),
            ("section_3", "2D View (Sections 3)"),
            ("section_45", "2D View (Sections 45)")
        ]

        for key, tab_title in tabs_2d:
            fig = Figure(figsize=(24, 12))
            canvas = FigureCanvas(fig)
            canvas.setMinimumSize(200, 200)
            ax = fig.add_subplot(111)

            self.track_plots[key] = {
                "figure": fig,
                "canvas": canvas,
                "ax": ax
            }
            
            # Add to the tab widget
            self.visual_tab_widget.addTab(canvas, tab_title)

        # Add to the main layout, with a scale factor of 3 to make it larger
        self.track_layout.addWidget(self.visual_widget, 3)


    # ========================================================================
    #                           Create Button
    # ========================================================================
    def create_button(self):
        self.create_btn = QPushButton("Create")
        self.create_btn.setStyleSheet(
            "background-color: #2ecc71; color: white; font-size: 18px;"
            "padding: 10px; border-radius: 10px;"
        )
        self.create_btn.clicked.connect(self.start_generating)
        self.main_layout.addWidget(self.create_btn)      


    # ========================================================================
    #                       Assembly Helper Functions
    # ========================================================================
    def single_page_view(self):
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("border: none; background: transparent; color: blue; font-size: 12px; font-weight: bold;")
        
        self.single_page_widget = QWidget()
        self.single_page_widget.setStyleSheet("background-color: #ecf0f1; border-radius: 10px; padding: 10px;")
        self.single_page_main_layout = QVBoxLayout(self.single_page_widget)
        self.single_page_main_layout.setContentsMargins(5, 5, 5, 5)
        self.single_page_main_layout.setSpacing(10)

        self.single_page_cards_layouts = {}
        self.single_page_cards = {}
        for section in SECTIONS:
            card = QWidget()
            card.setStyleSheet(CARD_STYLE.format(background="#ffffff", text="blue"))
            
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(10, 10, 10, 10)
            card_layout.setSpacing(2)

            header_layout = QHBoxLayout()
            header_layout.setContentsMargins(0, 0, 0, 0)
            
            title = QLabel(f"[{section}]")
            title.setStyleSheet("color: #2c3e50; font-weight: bold; font-size: 14px;")
            title.setAlignment(Qt.AlignmentFlag.AlignCenter)

            stats_btn = QPushButton("[ ? ]")
            stats_btn.setStyleSheet("""
                QPushButton { background-color: #3498db;  color: white; border-radius: 5px; padding: 4px 8px; font-size: 11px; }
                QPushButton:hover { background-color: #2980b9; }
                                    """)
            
            # When the stats button is clicked, open a dialog box which shows the stats of that section
            stats_btn.clicked.connect(lambda checked, s=section: self.show_section_stats(s))
            
            header_layout.addStretch()
            header_layout.addWidget(title)
            header_layout.addStretch()
            header_layout.addWidget(stats_btn)
            
            # Add the horizontal header layout to the vertical card layout
            card_layout.addLayout(header_layout)

            self.single_page_cards_layouts[section] = card_layout
            self.single_page_cards[section] = card
            self.single_page_main_layout.addWidget(card)
            
        self.single_page_main_layout.addStretch()
        scroll_area.setWidget(self.single_page_widget)
        self.assembly_stack.addWidget(scroll_area)

    def tabbed_view(self):
        self.assembly_tabs = QTabWidget()
        self.assembly_tabs.setStyleSheet("""
            QTabWidget::panel {background-color: white; color: black; border-radius: 10px; padding: 10px; font-size: 12px; font-weight: bold;}
            QTabBar::tab {background-color: white; color: black; padding: 8px 16px; border-top-left-radius: 6px; border-top-right-radius: 6px; margin-right: 2px; font-size: 12px; font-weight: bold;}
            QTabBar::tab:selected {background-color: #ffffff; color: #2c3e50; font-size: 12px; font-weight: bold;}
        """)

        self.tab_layouts = {}
        self.tab_widgets = {}
        for section in SECTIONS:
            tab_widget = QWidget()
            tab_widget.setStyleSheet("background-color: #ffffff; color: blue; border-radius: 10px; border-top-left-radius: 0px; padding: 10px; font-size: 12px; font-weight: bold;")
            tab_layout = QVBoxLayout(tab_widget)
            tab_layout.setContentsMargins(5, 5, 5, 5)
            
            self.tab_layouts[section] = tab_layout
            self.tab_widgets[section] = tab_widget
            self.assembly_tabs.addTab(tab_widget, section)
            
        self.assembly_stack.addWidget(self.assembly_tabs)

    def switch_view_mode(self, index):
        # The default is all on 1 page, but can change between them if the user wants

        for section in SECTIONS:
            if index == 0:
                target_layout = self.single_page_cards_layouts[section]
            else:
                target_layout = self.tab_layouts[section]
                
            # Re-setup the layout
            for widget in self.tracks[section]:
                widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
                target_layout.addWidget(widget)

        # Flip the visible stack page
        self.assembly_stack.setCurrentIndex(index)

    def track_type(self, section):        
        # Form Widget (Selecting Track Type)
        form_widget = QWidget()
        form = QFormLayout(form_widget)

        # col_layout = QVBoxLayout(col_widget)
        track_dropdown = QComboBox()
        track_dropdown.setPlaceholderText("Select Track Type")

        if section == "Starts":
            track_dropdown.addItems(STARTS)
        elif section in ("Thrills 1", "Thrills 2"):
            track_dropdown.addItems(THRILLS)
        elif section == "Turns":
            track_dropdown.addItems(TURNS)
        elif section == "Ends":
            track_dropdown.addItems(ENDS)
        
        # Setup the Slider
        length_slider = RangeIndicatorSlider(Qt.Orientation.Horizontal)
        length_slider.setRange(1, 50)

        # Setup the Length Input Field (only numbers can be typed; the range is checked on Create)
        length_input = QLineEdit()
        length_input.setPlaceholderText("Track Value (Meters)")
        validator = QDoubleValidator(length_slider.minimum(), length_slider.maximum(), 2, length_input)
        validator.setNotation(QDoubleValidator.Notation.StandardNotation)
        validator.setLocale(QLocale.c())   # always "." as the decimal point
        length_input.setValidator(validator)

        # ======= Test Value =======
        # length_input.setText("11")
        # length_slider.setValue(11)
        # ==========================
        
        # Connects Slider to Line Input Field (Moving the slider updates the text)
        length_slider.valueChanged.connect(lambda value: length_input.setText(str(value)))

        # Connects Line Input Field to Slider (Changing input value changes the slider position)
        def sync_slider_from_text(text):
            try:
                val = float(text)
            except ValueError:
                return   # empty, or still being typed (e.g. "12.")
            if length_slider.minimum() <= val <= length_slider.maximum():
                length_slider.blockSignals(True)
                length_slider.setValue(round(val))
                length_slider.blockSignals(False)
        length_input.textChanged.connect(sync_slider_from_text)

        def update_length_label(track_name):
            param_text = "Value"

            for key, items in CONTROL.items():
                if track_name in items:
                    param_text = key
                    break
            length_input.setPlaceholderText(f"Track {param_text} (Meters)")
        
        track_dropdown.currentTextChanged.connect(update_length_label)

        if track_dropdown.currentText():
            update_length_label(track_dropdown.currentText())

        # Add the widgets to the row layout
        form.addRow(track_dropdown)
        form.addRow(length_input)
        form.addRow(length_slider)

        # Recommended range label (filled in by update_recommendations)
        rec_label = QLabel("")
        rec_label.setStyleSheet(REC_LABEL_STYLE.format(color=REC_OK_COLOR))
        rec_label.hide()
        form.addRow(rec_label)

        form_widget.dropdown = track_dropdown
        form_widget.input_field = length_input
        form_widget.slider = length_slider
        form_widget.rec_label = rec_label

        # Changing the 'Starts' track/value, or any section's track type, updates the recommendations
        schedule_update = lambda *_: self.recommendation_timer.start()
        track_dropdown.currentTextChanged.connect(schedule_update)
        if section == "Starts":
            length_input.textChanged.connect(schedule_update)

        self.tracks[section].append(form_widget)

    def show_section_stats(self, section_name):        
        if section_name in self.track_stats and section_name in self.checks:
            stats = self.track_stats[section_name]
            check_data = self.checks[section_name]

            # Checks the Starts section of the track
            if section_name == "Starts":
                velocity_status = "PASSED"
            else:
                velocity_status = "PASSED" if check_data.get("velocity_check") else "FAILED/STALL"

            section_data = {"Track Status": velocity_status}

            # Checks the rest of the sections
            if velocity_status != "FAILED/STALL":
                # Display acceleration (Launcher and Brake sections will have acceleration, but the rest of the sections will not)
                if stats.get('acceleration') is not None:
                    section_data["Acceleration"] = f"{stats['acceleration']:.2f}g m/s²"

                # Display velocity exiting the section (Not applicable for the Ends section)
                if stats.get('velocity_exit') is not None and section_name != "Ends":
                    section_data["Exit Velocity"] = f"{stats['velocity_exit']:.2f} m/s"


                if section_name.startswith("Thrills") or section_name == "Turns":
                    track_type = stats["type"]

                    if stats.get('v_top') is not None:
                        section_data["Apex (Top) Velocity"] = f"{stats['v_top']:.2f} m/s"
                    if stats.get('v_bottom') is not None:
                        section_data["Valley (Bottom) Velocity"] = f"{stats['v_bottom']:.2f} m/s"


                    if track_type in ["Horseshoe", "Helix"]:
                        if stats.get('r_bottom') is not None:
                            section_data["Radius"] = f"{stats['r_bottom']:.2f} m"
                    else:
                        if stats.get('r_top') is not None:
                            section_data["Apex (Top) Radius"] = f"{stats['r_top']:.2f} m"
                        if stats.get('r_bottom') is not None:
                            section_data["Valley (Bottom) Radius"] = f"{stats['r_bottom']:.2f} m"
    

                    if stats.get('deg_banking') is not None:
                        section_data["Degrees Banking"] = f"{stats['deg_banking']:.2f}°"
                               
                    if stats.get('deg_top') is not None:
                        section_data["Degrees Top"] = f"{stats['deg_top']:.2f}°"
                    
                    if stats.get('deg_bottom') is not None:
                        section_data["Degrees Bottom"] = f"{stats['deg_bottom']:.2f}°"

                    
                passed_list = []
                failed_list = []
                for check_key, check_val in check_data.items():
                    if check_key == "velocity_check":
                        continue  # Handled separately by status
                    if check_val is True:
                        passed_list.append(check_key.replace("_check", "").title())
                    elif check_val is False:
                        failed_list.append(check_key.replace("_check", "").title())

                if passed_list:
                    section_data["Passed Physics"] = ", ".join(passed_list)
                if failed_list:
                    section_data["Failed Physics"] = ", ".join(failed_list)

        else:
            # Default is a blank state
            section_data = {"Track Status": "Not Generated",}
        
        # Create and display the dialog
        dialog = StatsDialog(section_name, section_data, parent=self)
        dialog.exec()


    # ========================================================================
    #                       Visual Helper Functions
    # ========================================================================
    def update_visual(self, images_folder, track_data, xy_composition):
        self.placeholder_label.hide()  # Hide the placeholder label
        self.visual_tab_widget.show()  # Show the visual widget

        X, Y, Z, Fx, Fy, Fz, Lx, Ly, Lz, Nx, Ny, Nz, file_name = track_data
        font_size, grid_padding= 8, 5

        for plot in self.track_plots.values():
            plot["ax"].clear()

        # === 3D View ===
        # This might look weird, but the axes are swapped to make the visualization more intuitive (X, Z, Y) instead of (X, Y, Z).
        # Right hand rule is used to determine the orientation of the axes, and this swap makes it easier to visualize the track in a more natural way.
        # X is the forward direction axis, Y is the left direction axis, and Z is the upward direction axis.
        ax3d = self.track_plots["3d"]["ax"]
        canvas_3d = self.track_plots["3d"]["canvas"]
        ax3d.plot3D(X, Z, Y, 'b-', label='Track Path')
        ax3d.plot3D(X + Nx, Z + Nz, Y + Ny, 'r-', alpha=0.4, label='Normals')
        ax3d.set_xlabel("X", fontsize=font_size)
        ax3d.set_ylabel("Z", fontsize=font_size)
        ax3d.set_zlabel("Y", fontsize=font_size)
        ax3d.tick_params(axis='both', which='major', labelsize=font_size - 2)
        ax3d.tick_params(axis='both', which='minor', labelsize=font_size - 4)
        
        # Scale the 3D plot to fit the data better (A 1:1:1 aspect ratio for better visualization)
        x_range = np.max(X) - np.min(X)
        y_range = np.max(Y) - np.min(Y)
        z_range = np.max(Z) - np.min(Z)
        max_range = max(x_range, y_range, z_range)
        box_x = x_range / max_range
        box_y = y_range / max_range
        box_z = z_range / max_range
        ax3d.set_box_aspect((box_x, box_z, box_y))  # Adjust aspect ratio for better visualization

        ax3d.set_xlim(np.min(X) - grid_padding, np.max(X) + grid_padding)
        ax3d.set_ylim(np.min(Z) - grid_padding, np.max(Z)+ grid_padding)
        ax3d.set_zlim(np.min(Y) - grid_padding, np.max(Y) + grid_padding)

        ax3d.legend(loc='upper right', bbox_to_anchor=(1.0, 1.0), fontsize=font_size)
        canvas_3d.draw()

        # === 2D View ===
        x_min_top, x_max_top = np.min(X), np.max(X)
        z_min_top, z_max_top = np.min(Z), np.max(Z)
        top_view_x_span = x_max_top - x_min_top
        top_view_y_span = z_max_top - z_min_top

        # === Plotting Individual Segments ===
        # Top View
        self.track_plots["whole_track_topview"]["ax"].plot(X, Z, color='black')
        # Starting point
        self.track_plots["whole_track_topview"]["ax"].plot(0, 0, color='black', marker='o', markersize=6, zorder=5)

        # Side view
        current_horizontal_offset = 0
        array_idx_start = 0

        for idx, segment in enumerate(xy_composition):
            local_horizontal = segment["XY"]
            Z_elevation = segment["Z"]
            global_2d_horizontal = local_horizontal + current_horizontal_offset
            
            # Update the individual standalone views
            self.track_plots["whole_track_sideview"]["ax"].plot(global_2d_horizontal, Z_elevation)

            if idx in (0, 1):
                self.track_plots["section_12"]["ax"].plot(global_2d_horizontal, Z_elevation)
            elif idx == 2:
                self.track_plots["section_3"]["ax"].plot(global_2d_horizontal, Z_elevation)
            elif idx in (3, 4):
                self.track_plots["section_45"]["ax"].plot(global_2d_horizontal, Z_elevation)

            segment_len = len(local_horizontal)
            array_idx_end = array_idx_start + segment_len
            
            if idx < len(xy_composition) - 1:
                # The last index of the current segment data block
                transition_idx = min(array_idx_end - 1, len(X) - 1)
                
                # 1. Plot dot on the standalone UI top view
                self.track_plots["whole_track_topview"]["ax"].plot(
                    X[transition_idx], Z[transition_idx], 
                    color='black', marker='o', markersize=6, zorder=5
                )
            
            array_idx_start = array_idx_end - 1
            current_horizontal_offset = global_2d_horizontal[-1]

        # === Finalize Formatting, Scaling, and File Outputs ===
        # Format and save the individual UI plot windows
        view_configs = [
            ("whole_track_topview",     "Whole Track Top View",     "X",    "Y", True),
            ("whole_track_sideview",    "Whole Track Side View",    "XY",   "Z", False),
            ("section_12",              "Section 1-2",              "XY",   "Z", False),
            ("section_3",               "Section 3",                "XY",   "Z", False),
            ("section_45",              "Section 4-5",              "XY",   "Z", False)
        ]

        for key, title, xlabel, ylabel, is_top_view in view_configs:
            plot = self.track_plots[key]
            ax, canvas = plot["ax"], plot["canvas"]
            ax.relim()
            ax.autoscale_view()

            if is_top_view:
                ax.set_xlim(x_min_top, x_max_top)
                ax.set_ylim(z_min_top, z_max_top)
                ax.axis('scaled')

            else:
                ax.autoscale(True, axis='both')
                mid_x = np.sum(ax.get_xlim()) / 2.0
                mid_y = np.sum(ax.get_ylim()) / 2.0
                
                ax.set_xlim(mid_x - (top_view_x_span / 2.0), mid_x + (top_view_x_span / 2.0))
                ax.set_ylim(mid_y - (top_view_y_span / 2.0), mid_y + (top_view_y_span / 2.0))
                ax.axis('scaled')

            ax.set_xlabel(xlabel, fontsize=font_size)
            ax.set_ylabel(ylabel, fontsize=font_size)
            ax.set_title(title, fontsize=font_size)
            canvas.draw()

        # Export the image files once, after every view is formatted
        file_utils.export_layouts(images_folder, track_data, xy_composition, self.track_plots)


    # ========================================================================
    #               Recommendation Based on 'Starts' Input
    # ========================================================================
    # Shows the safe range (green band on the slider + label) for each section's track,
    # based on the speed coming out of the 'Starts' section.
    def update_recommendations(self):
        start_row = self.tracks["Starts"][0]
        start_type = start_row.dropdown.currentText()
        try:
            start_val = float(start_row.input_field.text())
        except ValueError:
            start_val = None   # Empty, or the user is still typing

        recs = None
        if start_type and start_val is not None and start_val > 0:
            try:
                recs = EnergyRecommendation.get_recommendations(
                    start_type, start_val, track_function_map, RECOMMEND_SECTIONS,
                    value_range=(start_row.slider.minimum(), start_row.slider.maximum()))
            except Exception as e:
                print(f"Recommendation failed: {e}")

        for section_name in RECOMMEND_SECTIONS:
            for row in self.tracks[section_name]:
                track_type = row.dropdown.currentText()

                # Nothing to recommend yet (no valid 'Starts' or no track picked)
                if recs is None or not track_type:
                    row.slider.set_recommendation_bounds(None, None)
                    row.rec_label.hide()
                    continue

                bounds = recs[section_name].get(track_type)
                if bounds:
                    low, high = bounds
                    row.slider.set_recommendation_bounds(low, high)
                    row.rec_label.setText(f"Recommended: {low} - {high} m" if low != high else f"Recommended: {low} m")
                    row.rec_label.setStyleSheet(REC_LABEL_STYLE.format(color=REC_OK_COLOR))
                else:
                    row.slider.set_recommendation_bounds(None, None)
                    row.rec_label.setText(f"No safe {track_type} size for this start")
                    row.rec_label.setStyleSheet(REC_LABEL_STYLE.format(color=REC_BAD_COLOR))
                row.rec_label.show()


    # ========================================================================
    #                       Proccesing Physics Checks
    # ========================================================================
    def process_physics_checks(self, checks):
        warnings = []
        for section_name, section_data in checks.items():
            if section_name == "Starts":
                continue

            # A check that is None doesn't apply to this track type, so only False fails
            failed = [message for check, message in CHECK_WARNINGS.items() if section_data.get(check) is False]
            warnings.extend(f"{section_name}: {message}" for message in failed)

            # Changes the color of the section, based on whether they passed or failed the checks
            if section_name in self.single_page_cards:
                background = "#e74c3c" if failed else "#2ecc71"
                self.single_page_cards[section_name].setStyleSheet(CARD_STYLE.format(background=background, text="#ffffff"))

        return warnings


    # ========================================================================
    #                       Create Helper Functions
    # ========================================================================
    def ask_build_names(self):
        # Keeps asking until the user picks a new name, confirms a replace, or cancels
        while True:
            dialog = DualInputDialog(self, self.last_section, self.last_coaster)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return None

            section_folder, coaster_name = dialog.get_inputs()
            section_folder = section_folder.strip() or "Test_Section"
            coaster_name = coaster_name.strip() or "Test_Coaster"
            self.last_section, self.last_coaster = section_folder, coaster_name

            # Same section + coaster name as an existing build -> confirm replacing it
            if file_utils.build_exists(section_folder, coaster_name):
                reply = QMessageBox.question(
                    self, "Replace Previous Build?",
                    f'"{coaster_name}" already exists in "{section_folder}".\n'
                    "Do you want to replace the previous build?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if reply != QMessageBox.StandardButton.Yes:
                    continue   # reopen the dialog so they can change the name

            print(f"Section: {section_folder} | Coaster: {coaster_name}")
            return section_folder, coaster_name

    def start_generating(self):
        # === 1) Validate every input before asking for names ===
        requests = []
        for section in self.tracks:
            for track_row in self.tracks[section]:
                track_type = track_row.dropdown.currentText()
                track_length = track_row.input_field.text()

                if not track_type or not track_length:
                    QMessageBox.warning(self, "Incomplete Entry", "Please select a track type and enter a length for all tracks.")
                    return
                try:
                    length_value = float(track_length)
                except ValueError:
                    QMessageBox.warning(self, "Invalid Length", f"Please enter a valid number for the length of the {track_type} track.")
                    return
                low, high = track_row.slider.minimum(), track_row.slider.maximum()
                if not low <= length_value <= high:
                    QMessageBox.warning(self, "Invalid Number",
                                        f"The {track_type} track value must be within the range of {low} - {high}.")
                    return
                if track_type not in track_function_map:
                    QMessageBox.warning(self, "Unknown Track", f"Track type {track_type} is not recognized.")
                    return

                requests.append((section, track_type, length_value))

        if not requests:
            QMessageBox.warning(self, "No Tracks", "No valid tracks to assemble.")
            return

        # === 2) Ask for section/coaster name (pre-filled, confirms replace) ===
        names = self.ask_build_names()
        if names is None:
            return
        section_folder, coaster_name = names

        # === 3) Make the section folder FIRST so segments are saved inside it ===
        # <section>/Coasters/<coaster>_0.csv, <section>/Images/<coaster>/, <section>/Segments/<coaster>/
        # Only this coaster's old files are cleared; other coasters in the section are kept.
        folders = file_utils.initalize_folders(section_folder, coaster_name)
        section_path = folders["master"]

        wait = QMessageBox(self)
        wait.setWindowTitle("Assembling Tracks")
        wait.setText("Assembling tracks, please wait...")
        wait.show()
        QApplication.processEvents()

        try:
            # === 4) Build each track part (writes to <section>/Segments) ===
            data = []
            for section, track_type, length_value in requests:
                result = track_function_map[track_type](length_value)
                segment_v_exit = 0.0
                if track_type in STARTS and isinstance(result, tuple) and len(result) == 2:
                    segment, raw_v = result
                    segment_v_exit = float(np.ravel(raw_v)[0])
                else:
                    segment = result

                data.append({
                    "section": section,
                    "type": track_type,
                    "arrays": segment,
                    "v_exit": segment_v_exit
                })

            # === 5) Combine, check physics, visualize, export ===
            combined_track, xy_composition, track_data = tracks.TrackPart.combine_tracks(
                *data, section_folder=section_path, coaster_name=coaster_name)
            self.track_stats = {name: {"type": d["section_type"], **d["stats"]} for name, d in track_data.items()}
            self.checks = {name: d["checks"] for name, d in track_data.items()}

            warnings = self.process_physics_checks(self.checks)
            self.update_visual(folders["images"], combined_track, xy_composition)

        except Exception as e:
            wait.close()
            QMessageBox.critical(self, "Assembly Error", f"An error occurred during assembly: {str(e)}")
            return

        wait.close()

        if warnings:
            warning_msg = "The track was built, but failed the following physics checks:\n\n" + "\n".join(warnings)
            QMessageBox.warning(self, "Physics Warning", warning_msg)

        QMessageBox.information(self, "Success", f"Assembly Complete!\nCSV file generated: {coaster_name}")


if __name__ == "__main__":
    try:
        app = QApplication(sys.argv)
        window = MainWindow()
        window.show()
        sys.exit(app.exec())
    except Exception as sys_error:
        print(f"CRITICAL SYSTEM CRASH DETECTED: {sys_error}")
