# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'main_window.ui'
##
## Created by: Qt User Interface Compiler version 6.9.1
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (QCoreApplication, QDate, QDateTime, QLocale,
    QMetaObject, QObject, QPoint, QRect,
    QSize, QTime, QUrl, Qt)
from PySide6.QtGui import (QBrush, QColor, QConicalGradient, QCursor,
    QFont, QFontDatabase, QGradient, QIcon,
    QImage, QKeySequence, QLinearGradient, QPainter,
    QPalette, QPixmap, QRadialGradient, QTransform)
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDockWidget,
    QDoubleSpinBox, QFormLayout, QFrame, QGridLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMainWindow, QPushButton,
    QSizePolicy, QStatusBar, QTabWidget, QWidget)

class Ui_MainWindow(object):
    def setupUi(self, MainWindow):
        if not MainWindow.objectName():
            MainWindow.setObjectName(u"MainWindow")
        MainWindow.resize(1038, 910)
        self.centralwidget = QWidget(MainWindow)
        self.centralwidget.setObjectName(u"centralwidget")
        self.gridLayout_2 = QGridLayout(self.centralwidget)
        self.gridLayout_2.setObjectName(u"gridLayout_2")
        self.horizontalLayout_3 = QHBoxLayout()
        self.horizontalLayout_3.setObjectName(u"horizontalLayout_3")
        self.add_dataset_button = QPushButton(self.centralwidget)
        self.add_dataset_button.setObjectName(u"add_dataset_button")

        self.horizontalLayout_3.addWidget(self.add_dataset_button)

        self.remove_dataset_button = QPushButton(self.centralwidget)
        self.remove_dataset_button.setObjectName(u"remove_dataset_button")

        self.horizontalLayout_3.addWidget(self.remove_dataset_button)


        self.gridLayout_2.addLayout(self.horizontalLayout_3, 3, 0, 1, 1)

        self.plot_container = QWidget(self.centralwidget)
        self.plot_container.setObjectName(u"plot_container")

        self.gridLayout_2.addWidget(self.plot_container, 1, 0, 1, 1)

        self.properties_groupbox = QGroupBox(self.centralwidget)
        self.properties_groupbox.setObjectName(u"properties_groupbox")
        self.properties_groupbox.setEnabled(False)
        self.gridLayout_4 = QGridLayout(self.properties_groupbox)
        self.gridLayout_4.setObjectName(u"gridLayout_4")
        self.formLayout_4 = QFormLayout()
        self.formLayout_4.setObjectName(u"formLayout_4")
        self.plot_type_label = QLabel(self.properties_groupbox)
        self.plot_type_label.setObjectName(u"plot_type_label")
        self.plot_type_label.setFrameShape(QFrame.Shape.NoFrame)

        self.formLayout_4.setWidget(1, QFormLayout.ItemRole.LabelRole, self.plot_type_label)

        self.plot_type_combo = QComboBox(self.properties_groupbox)
        self.plot_type_combo.addItem("")
        self.plot_type_combo.addItem("")
        self.plot_type_combo.addItem("")
        self.plot_type_combo.setObjectName(u"plot_type_combo")

        self.formLayout_4.setWidget(1, QFormLayout.ItemRole.FieldRole, self.plot_type_combo)

        self.color_label = QLabel(self.properties_groupbox)
        self.color_label.setObjectName(u"color_label")

        self.formLayout_4.setWidget(2, QFormLayout.ItemRole.LabelRole, self.color_label)

        self.color_button = QPushButton(self.properties_groupbox)
        self.color_button.setObjectName(u"color_button")

        self.formLayout_4.setWidget(2, QFormLayout.ItemRole.FieldRole, self.color_button)

        self.linestyle_label = QLabel(self.properties_groupbox)
        self.linestyle_label.setObjectName(u"linestyle_label")

        self.formLayout_4.setWidget(3, QFormLayout.ItemRole.LabelRole, self.linestyle_label)

        self.linestyle_combo = QComboBox(self.properties_groupbox)
        self.linestyle_combo.addItem("")
        self.linestyle_combo.addItem("")
        self.linestyle_combo.addItem("")
        self.linestyle_combo.addItem("")
        self.linestyle_combo.setObjectName(u"linestyle_combo")

        self.formLayout_4.setWidget(3, QFormLayout.ItemRole.FieldRole, self.linestyle_combo)

        self.linewidth_label = QLabel(self.properties_groupbox)
        self.linewidth_label.setObjectName(u"linewidth_label")

        self.formLayout_4.setWidget(4, QFormLayout.ItemRole.LabelRole, self.linewidth_label)

        self.linewidth_spinbox = QDoubleSpinBox(self.properties_groupbox)
        self.linewidth_spinbox.setObjectName(u"linewidth_spinbox")
        self.linewidth_spinbox.setValue(1.500000000000000)

        self.formLayout_4.setWidget(4, QFormLayout.ItemRole.FieldRole, self.linewidth_spinbox)

        self.marker_label = QLabel(self.properties_groupbox)
        self.marker_label.setObjectName(u"marker_label")

        self.formLayout_4.setWidget(5, QFormLayout.ItemRole.LabelRole, self.marker_label)

        self.marker_combo = QComboBox(self.properties_groupbox)
        self.marker_combo.addItem("")
        self.marker_combo.addItem("")
        self.marker_combo.addItem("")
        self.marker_combo.addItem("")
        self.marker_combo.addItem("")
        self.marker_combo.addItem("")
        self.marker_combo.setObjectName(u"marker_combo")

        self.formLayout_4.setWidget(5, QFormLayout.ItemRole.FieldRole, self.marker_combo)

        self.makersize_label = QLabel(self.properties_groupbox)
        self.makersize_label.setObjectName(u"makersize_label")

        self.formLayout_4.setWidget(6, QFormLayout.ItemRole.LabelRole, self.makersize_label)

        self.markersize_spinbox = QDoubleSpinBox(self.properties_groupbox)
        self.markersize_spinbox.setObjectName(u"markersize_spinbox")
        self.markersize_spinbox.setValue(6.000000000000000)

        self.formLayout_4.setWidget(6, QFormLayout.ItemRole.FieldRole, self.markersize_spinbox)

        self.smoothing_checkbox = QCheckBox(self.properties_groupbox)
        self.smoothing_checkbox.setObjectName(u"smoothing_checkbox")

        self.formLayout_4.setWidget(7, QFormLayout.ItemRole.SpanningRole, self.smoothing_checkbox)

        self.legend_name_label = QLabel(self.properties_groupbox)
        self.legend_name_label.setObjectName(u"legend_name_label")

        self.formLayout_4.setWidget(0, QFormLayout.ItemRole.LabelRole, self.legend_name_label)

        self.legend_name_edit = QLineEdit(self.properties_groupbox)
        self.legend_name_edit.setObjectName(u"legend_name_edit")

        self.formLayout_4.setWidget(0, QFormLayout.ItemRole.FieldRole, self.legend_name_edit)


        self.gridLayout_4.addLayout(self.formLayout_4, 0, 0, 1, 1)


        self.gridLayout_2.addWidget(self.properties_groupbox, 5, 0, 1, 1)

        self.dataset_list_widget = QListWidget(self.centralwidget)
        self.dataset_list_widget.setObjectName(u"dataset_list_widget")

        self.gridLayout_2.addWidget(self.dataset_list_widget, 2, 0, 1, 1)

        MainWindow.setCentralWidget(self.centralwidget)
        self.properties_groupbox.raise_()
        self.dataset_list_widget.raise_()
        self.plot_container.raise_()
        self.statusbar = QStatusBar(MainWindow)
        self.statusbar.setObjectName(u"statusbar")
        MainWindow.setStatusBar(self.statusbar)
        self.control_dock_widget = QDockWidget(MainWindow)
        self.control_dock_widget.setObjectName(u"control_dock_widget")
        self.control_dock_widget.setMinimumSize(QSize(1015, 372))
        self.control_dock_widget.setFloating(False)
        self.dockWidgetContents = QWidget()
        self.dockWidgetContents.setObjectName(u"dockWidgetContents")
        self.gridLayout_6 = QGridLayout(self.dockWidgetContents)
        self.gridLayout_6.setObjectName(u"gridLayout_6")
        self.axis_tab_widget = QTabWidget(self.dockWidgetContents)
        self.axis_tab_widget.setObjectName(u"axis_tab_widget")
        self.tab = QWidget()
        self.tab.setObjectName(u"tab")
        self.gridLayout = QGridLayout(self.tab)
        self.gridLayout.setObjectName(u"gridLayout")
        self.formLayout = QFormLayout()
        self.formLayout.setObjectName(u"formLayout")
        self.x_min_spinbox = QDoubleSpinBox(self.tab)
        self.x_min_spinbox.setObjectName(u"x_min_spinbox")
        self.x_min_spinbox.setMinimum(-2147483648.000000000000000)
        self.x_min_spinbox.setMaximum(2147483648.000000000000000)

        self.formLayout.setWidget(0, QFormLayout.ItemRole.FieldRole, self.x_min_spinbox)

        self.x_min_label = QLabel(self.tab)
        self.x_min_label.setObjectName(u"x_min_label")

        self.formLayout.setWidget(0, QFormLayout.ItemRole.LabelRole, self.x_min_label)

        self.x_max_label = QLabel(self.tab)
        self.x_max_label.setObjectName(u"x_max_label")

        self.formLayout.setWidget(1, QFormLayout.ItemRole.LabelRole, self.x_max_label)

        self.x_autoscale_checkbox = QCheckBox(self.tab)
        self.x_autoscale_checkbox.setObjectName(u"x_autoscale_checkbox")

        self.formLayout.setWidget(2, QFormLayout.ItemRole.SpanningRole, self.x_autoscale_checkbox)

        self.x_max_spinbox = QDoubleSpinBox(self.tab)
        self.x_max_spinbox.setObjectName(u"x_max_spinbox")
        self.x_max_spinbox.setMinimum(-2147483648.000000000000000)
        self.x_max_spinbox.setMaximum(2147483648.000000000000000)

        self.formLayout.setWidget(1, QFormLayout.ItemRole.FieldRole, self.x_max_spinbox)

        self.x_log_checkbox = QCheckBox(self.tab)
        self.x_log_checkbox.setObjectName(u"x_log_checkbox")

        self.formLayout.setWidget(3, QFormLayout.ItemRole.SpanningRole, self.x_log_checkbox)

        self.x_invert_checkbox = QCheckBox(self.tab)
        self.x_invert_checkbox.setObjectName(u"x_invert_checkbox")

        self.formLayout.setWidget(4, QFormLayout.ItemRole.SpanningRole, self.x_invert_checkbox)

        self.x_major_tick_label = QLabel(self.tab)
        self.x_major_tick_label.setObjectName(u"x_major_tick_label")

        self.formLayout.setWidget(5, QFormLayout.ItemRole.LabelRole, self.x_major_tick_label)

        self.x_major_tick_mode_combo = QComboBox(self.tab)
        self.x_major_tick_mode_combo.addItem("")
        self.x_major_tick_mode_combo.addItem("")
        self.x_major_tick_mode_combo.setObjectName(u"x_major_tick_mode_combo")

        self.formLayout.setWidget(5, QFormLayout.ItemRole.FieldRole, self.x_major_tick_mode_combo)

        self.x_major_tick_interval_spinbox = QDoubleSpinBox(self.tab)
        self.x_major_tick_interval_spinbox.setObjectName(u"x_major_tick_interval_spinbox")
        self.x_major_tick_interval_spinbox.setEnabled(False)
        self.x_major_tick_interval_spinbox.setMinimum(-2147483648.000000000000000)
        self.x_major_tick_interval_spinbox.setMaximum(2147483648.000000000000000)

        self.formLayout.setWidget(6, QFormLayout.ItemRole.FieldRole, self.x_major_tick_interval_spinbox)

        self.x_major_tick_interval_label = QLabel(self.tab)
        self.x_major_tick_interval_label.setObjectName(u"x_major_tick_interval_label")

        self.formLayout.setWidget(6, QFormLayout.ItemRole.LabelRole, self.x_major_tick_interval_label)

        self.x_minor_ticks_visible_checkbox = QCheckBox(self.tab)
        self.x_minor_ticks_visible_checkbox.setObjectName(u"x_minor_ticks_visible_checkbox")

        self.formLayout.setWidget(7, QFormLayout.ItemRole.SpanningRole, self.x_minor_ticks_visible_checkbox)

        self.x_minor_tick_interval_label = QLabel(self.tab)
        self.x_minor_tick_interval_label.setObjectName(u"x_minor_tick_interval_label")

        self.formLayout.setWidget(8, QFormLayout.ItemRole.LabelRole, self.x_minor_tick_interval_label)

        self.x_minor_tick_interval_spinbox = QDoubleSpinBox(self.tab)
        self.x_minor_tick_interval_spinbox.setObjectName(u"x_minor_tick_interval_spinbox")
        self.x_minor_tick_interval_spinbox.setEnabled(False)
        self.x_minor_tick_interval_spinbox.setMinimum(-2147483648.000000000000000)
        self.x_minor_tick_interval_spinbox.setMaximum(2147483648.000000000000000)

        self.formLayout.setWidget(8, QFormLayout.ItemRole.FieldRole, self.x_minor_tick_interval_spinbox)


        self.gridLayout.addLayout(self.formLayout, 0, 0, 1, 1)

        self.axis_tab_widget.addTab(self.tab, "")
        self.tab_2 = QWidget()
        self.tab_2.setObjectName(u"tab_2")
        self.gridLayout_3 = QGridLayout(self.tab_2)
        self.gridLayout_3.setObjectName(u"gridLayout_3")
        self.formLayout_2 = QFormLayout()
        self.formLayout_2.setObjectName(u"formLayout_2")
        self.y_min_label = QLabel(self.tab_2)
        self.y_min_label.setObjectName(u"y_min_label")

        self.formLayout_2.setWidget(0, QFormLayout.ItemRole.LabelRole, self.y_min_label)

        self.y_max_label = QLabel(self.tab_2)
        self.y_max_label.setObjectName(u"y_max_label")

        self.formLayout_2.setWidget(1, QFormLayout.ItemRole.LabelRole, self.y_max_label)

        self.y_min_spinbox = QDoubleSpinBox(self.tab_2)
        self.y_min_spinbox.setObjectName(u"y_min_spinbox")
        self.y_min_spinbox.setMinimum(-2147483648.000000000000000)
        self.y_min_spinbox.setMaximum(2147483648.000000000000000)

        self.formLayout_2.setWidget(0, QFormLayout.ItemRole.FieldRole, self.y_min_spinbox)

        self.y_max_spinbox = QDoubleSpinBox(self.tab_2)
        self.y_max_spinbox.setObjectName(u"y_max_spinbox")
        self.y_max_spinbox.setMinimum(-2147483648.000000000000000)
        self.y_max_spinbox.setMaximum(2147483648.000000000000000)

        self.formLayout_2.setWidget(1, QFormLayout.ItemRole.FieldRole, self.y_max_spinbox)

        self.y_autoscale_checkbox = QCheckBox(self.tab_2)
        self.y_autoscale_checkbox.setObjectName(u"y_autoscale_checkbox")

        self.formLayout_2.setWidget(2, QFormLayout.ItemRole.SpanningRole, self.y_autoscale_checkbox)

        self.y_log_checkbox = QCheckBox(self.tab_2)
        self.y_log_checkbox.setObjectName(u"y_log_checkbox")

        self.formLayout_2.setWidget(3, QFormLayout.ItemRole.SpanningRole, self.y_log_checkbox)

        self.y_invert_checkbox = QCheckBox(self.tab_2)
        self.y_invert_checkbox.setObjectName(u"y_invert_checkbox")

        self.formLayout_2.setWidget(4, QFormLayout.ItemRole.SpanningRole, self.y_invert_checkbox)

        self.y_major_tick_interval_spinbox = QDoubleSpinBox(self.tab_2)
        self.y_major_tick_interval_spinbox.setObjectName(u"y_major_tick_interval_spinbox")
        self.y_major_tick_interval_spinbox.setEnabled(False)
        self.y_major_tick_interval_spinbox.setMinimum(-2147483648.000000000000000)
        self.y_major_tick_interval_spinbox.setMaximum(2147483648.000000000000000)

        self.formLayout_2.setWidget(6, QFormLayout.ItemRole.FieldRole, self.y_major_tick_interval_spinbox)

        self.y_major_tick_mode_combo = QComboBox(self.tab_2)
        self.y_major_tick_mode_combo.addItem("")
        self.y_major_tick_mode_combo.addItem("")
        self.y_major_tick_mode_combo.setObjectName(u"y_major_tick_mode_combo")

        self.formLayout_2.setWidget(5, QFormLayout.ItemRole.FieldRole, self.y_major_tick_mode_combo)

        self.y_major_tick_label = QLabel(self.tab_2)
        self.y_major_tick_label.setObjectName(u"y_major_tick_label")

        self.formLayout_2.setWidget(5, QFormLayout.ItemRole.LabelRole, self.y_major_tick_label)

        self.y_major_tick_interval_label = QLabel(self.tab_2)
        self.y_major_tick_interval_label.setObjectName(u"y_major_tick_interval_label")

        self.formLayout_2.setWidget(6, QFormLayout.ItemRole.LabelRole, self.y_major_tick_interval_label)

        self.y_minor_ticks_visible_checkbox = QCheckBox(self.tab_2)
        self.y_minor_ticks_visible_checkbox.setObjectName(u"y_minor_ticks_visible_checkbox")

        self.formLayout_2.setWidget(7, QFormLayout.ItemRole.SpanningRole, self.y_minor_ticks_visible_checkbox)

        self.y_minor_tick_interval_label = QLabel(self.tab_2)
        self.y_minor_tick_interval_label.setObjectName(u"y_minor_tick_interval_label")

        self.formLayout_2.setWidget(8, QFormLayout.ItemRole.LabelRole, self.y_minor_tick_interval_label)

        self.y_minor_tick_interval_spinbox = QDoubleSpinBox(self.tab_2)
        self.y_minor_tick_interval_spinbox.setObjectName(u"y_minor_tick_interval_spinbox")
        self.y_minor_tick_interval_spinbox.setEnabled(False)
        self.y_minor_tick_interval_spinbox.setMinimum(-2147483648.000000000000000)
        self.y_minor_tick_interval_spinbox.setMaximum(2147483648.000000000000000)

        self.formLayout_2.setWidget(8, QFormLayout.ItemRole.FieldRole, self.y_minor_tick_interval_spinbox)


        self.gridLayout_3.addLayout(self.formLayout_2, 0, 0, 1, 1)

        self.axis_tab_widget.addTab(self.tab_2, "")
        self.tab_3 = QWidget()
        self.tab_3.setObjectName(u"tab_3")
        self.gridLayout_5 = QGridLayout(self.tab_3)
        self.gridLayout_5.setObjectName(u"gridLayout_5")
        self.formLayout_3 = QFormLayout()
        self.formLayout_3.setObjectName(u"formLayout_3")
        self.title_text_label = QLabel(self.tab_3)
        self.title_text_label.setObjectName(u"title_text_label")

        self.formLayout_3.setWidget(0, QFormLayout.ItemRole.LabelRole, self.title_text_label)

        self.title_text_edit = QLineEdit(self.tab_3)
        self.title_text_edit.setObjectName(u"title_text_edit")

        self.formLayout_3.setWidget(0, QFormLayout.ItemRole.FieldRole, self.title_text_edit)

        self.x_label_text_label = QLabel(self.tab_3)
        self.x_label_text_label.setObjectName(u"x_label_text_label")

        self.formLayout_3.setWidget(1, QFormLayout.ItemRole.LabelRole, self.x_label_text_label)

        self.x_label_text_edit = QLineEdit(self.tab_3)
        self.x_label_text_edit.setObjectName(u"x_label_text_edit")

        self.formLayout_3.setWidget(1, QFormLayout.ItemRole.FieldRole, self.x_label_text_edit)

        self.y_label_text_label = QLabel(self.tab_3)
        self.y_label_text_label.setObjectName(u"y_label_text_label")

        self.formLayout_3.setWidget(2, QFormLayout.ItemRole.LabelRole, self.y_label_text_label)

        self.y_label_text_edit = QLineEdit(self.tab_3)
        self.y_label_text_edit.setObjectName(u"y_label_text_edit")

        self.formLayout_3.setWidget(2, QFormLayout.ItemRole.FieldRole, self.y_label_text_edit)

        self.tick_format_label = QLabel(self.tab_3)
        self.tick_format_label.setObjectName(u"tick_format_label")

        self.formLayout_3.setWidget(3, QFormLayout.ItemRole.LabelRole, self.tick_format_label)

        self.horizontalLayout = QHBoxLayout()
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.tick_font_button = QPushButton(self.tab_3)
        self.tick_font_button.setObjectName(u"tick_font_button")

        self.horizontalLayout.addWidget(self.tick_font_button)

        self.tick_color_button = QPushButton(self.tab_3)
        self.tick_color_button.setObjectName(u"tick_color_button")

        self.horizontalLayout.addWidget(self.tick_color_button)


        self.formLayout_3.setLayout(3, QFormLayout.ItemRole.FieldRole, self.horizontalLayout)

        self.axis_label_format_label = QLabel(self.tab_3)
        self.axis_label_format_label.setObjectName(u"axis_label_format_label")

        self.formLayout_3.setWidget(5, QFormLayout.ItemRole.LabelRole, self.axis_label_format_label)

        self.horizontalLayout_2 = QHBoxLayout()
        self.horizontalLayout_2.setObjectName(u"horizontalLayout_2")
        self.axis_label_font_button = QPushButton(self.tab_3)
        self.axis_label_font_button.setObjectName(u"axis_label_font_button")

        self.horizontalLayout_2.addWidget(self.axis_label_font_button)

        self.axis_label_color_button = QPushButton(self.tab_3)
        self.axis_label_color_button.setObjectName(u"axis_label_color_button")

        self.horizontalLayout_2.addWidget(self.axis_label_color_button)


        self.formLayout_3.setLayout(5, QFormLayout.ItemRole.FieldRole, self.horizontalLayout_2)

        self.legend_visible_checkbox = QCheckBox(self.tab_3)
        self.legend_visible_checkbox.setObjectName(u"legend_visible_checkbox")

        self.formLayout_3.setWidget(6, QFormLayout.ItemRole.SpanningRole, self.legend_visible_checkbox)

        self.grid_visible_checkbox = QCheckBox(self.tab_3)
        self.grid_visible_checkbox.setObjectName(u"grid_visible_checkbox")

        self.formLayout_3.setWidget(7, QFormLayout.ItemRole.SpanningRole, self.grid_visible_checkbox)

        self.spine_format_label = QLabel(self.tab_3)
        self.spine_format_label.setObjectName(u"spine_format_label")

        self.formLayout_3.setWidget(9, QFormLayout.ItemRole.LabelRole, self.spine_format_label)

        self.horizontalLayout_4 = QHBoxLayout()
        self.horizontalLayout_4.setObjectName(u"horizontalLayout_4")
        self.spine_width_spinbox = QDoubleSpinBox(self.tab_3)
        self.spine_width_spinbox.setObjectName(u"spine_width_spinbox")
        self.spine_width_spinbox.setValue(1.000000000000000)

        self.horizontalLayout_4.addWidget(self.spine_width_spinbox)

        self.spine_color_button = QPushButton(self.tab_3)
        self.spine_color_button.setObjectName(u"spine_color_button")

        self.horizontalLayout_4.addWidget(self.spine_color_button)


        self.formLayout_3.setLayout(9, QFormLayout.ItemRole.FieldRole, self.horizontalLayout_4)

        self.tick_width_label = QLabel(self.tab_3)
        self.tick_width_label.setObjectName(u"tick_width_label")

        self.formLayout_3.setWidget(4, QFormLayout.ItemRole.LabelRole, self.tick_width_label)

        self.tick_width_spinbox = QDoubleSpinBox(self.tab_3)
        self.tick_width_spinbox.setObjectName(u"tick_width_spinbox")
        self.tick_width_spinbox.setMinimum(0.100000000000000)
        self.tick_width_spinbox.setMaximum(10.000000000000000)
        self.tick_width_spinbox.setSingleStep(0.100000000000000)
        self.tick_width_spinbox.setValue(0.800000000000000)

        self.formLayout_3.setWidget(4, QFormLayout.ItemRole.FieldRole, self.tick_width_spinbox)

        self.minor_grid_visible_checkbox = QCheckBox(self.tab_3)
        self.minor_grid_visible_checkbox.setObjectName(u"minor_grid_visible_checkbox")

        self.formLayout_3.setWidget(8, QFormLayout.ItemRole.LabelRole, self.minor_grid_visible_checkbox)


        self.gridLayout_5.addLayout(self.formLayout_3, 0, 0, 1, 1)

        self.axis_tab_widget.addTab(self.tab_3, "")

        self.gridLayout_6.addWidget(self.axis_tab_widget, 0, 0, 1, 1)

        self.control_dock_widget.setWidget(self.dockWidgetContents)
        MainWindow.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.control_dock_widget)
        self.control_dock_widget.raise_()

        self.retranslateUi(MainWindow)

        self.axis_tab_widget.setCurrentIndex(2)


        QMetaObject.connectSlotsByName(MainWindow)
    # setupUi

    def retranslateUi(self, MainWindow):
        MainWindow.setWindowTitle(QCoreApplication.translate("MainWindow", u"MainWindow", None))
        self.add_dataset_button.setText(QCoreApplication.translate("MainWindow", u"\u30c7\u30fc\u30bf\u8ffd\u52a0", None))
        self.remove_dataset_button.setText(QCoreApplication.translate("MainWindow", u"\u30c7\u30fc\u30bf\u524a\u9664", None))
        self.properties_groupbox.setTitle(QCoreApplication.translate("MainWindow", u"\u9078\u629e\u4e2d\u30c7\u30fc\u30bf\u30bb\u30c3\u30c8\u306e\u30d7\u30ed\u30d1\u30c6\u30a3", None))
        self.plot_type_label.setText(QCoreApplication.translate("MainWindow", u"\u7a2e\u5225\uff1a", None))
        self.plot_type_combo.setItemText(0, QCoreApplication.translate("MainWindow", u"Line", None))
        self.plot_type_combo.setItemText(1, QCoreApplication.translate("MainWindow", u"Scatter", None))
        self.plot_type_combo.setItemText(2, QCoreApplication.translate("MainWindow", u"Line+Scatter", None))

        self.color_label.setText(QCoreApplication.translate("MainWindow", u"\u8272\uff1a", None))
        self.color_button.setText(QCoreApplication.translate("MainWindow", u"\u8272\u3092\u9078\u629e\u2026", None))
        self.linestyle_label.setText(QCoreApplication.translate("MainWindow", u"\u7dda\u306e\u7a2e\u985e\uff1a", None))
        self.linestyle_combo.setItemText(0, QCoreApplication.translate("MainWindow", u"solid", None))
        self.linestyle_combo.setItemText(1, QCoreApplication.translate("MainWindow", u"dashed", None))
        self.linestyle_combo.setItemText(2, QCoreApplication.translate("MainWindow", u"dotted", None))
        self.linestyle_combo.setItemText(3, QCoreApplication.translate("MainWindow", u"dashdot", None))

        self.linewidth_label.setText(QCoreApplication.translate("MainWindow", u"\u7dda\u306e\u592a\u3055\uff1a", None))
        self.marker_label.setText(QCoreApplication.translate("MainWindow", u"\u30de\u30fc\u30ab\u30fc\uff1a", None))
        self.marker_combo.setItemText(0, QCoreApplication.translate("MainWindow", u"o", None))
        self.marker_combo.setItemText(1, QCoreApplication.translate("MainWindow", u"s", None))
        self.marker_combo.setItemText(2, QCoreApplication.translate("MainWindow", u"^", None))
        self.marker_combo.setItemText(3, QCoreApplication.translate("MainWindow", u"v", None))
        self.marker_combo.setItemText(4, QCoreApplication.translate("MainWindow", u"D", None))
        self.marker_combo.setItemText(5, QCoreApplication.translate("MainWindow", u"None", None))

        self.makersize_label.setText(QCoreApplication.translate("MainWindow", u"\u30de\u30fc\u30ab\u30fc\u30b5\u30a4\u30ba\uff1a", None))
        self.smoothing_checkbox.setText(QCoreApplication.translate("MainWindow", u"\u5e73\u6ed1\u5316", None))
        self.legend_name_label.setText(QCoreApplication.translate("MainWindow", u"\u51e1\u4f8b\u540d\uff1a", None))
        self.x_min_label.setText(QCoreApplication.translate("MainWindow", u"\u6700\u5c0f\u5024", None))
        self.x_max_label.setText(QCoreApplication.translate("MainWindow", u"\u6700\u5927\u5024", None))
        self.x_autoscale_checkbox.setText(QCoreApplication.translate("MainWindow", u"\u81ea\u52d5\u30b9\u30b1\u30fc\u30eb", None))
        self.x_log_checkbox.setText(QCoreApplication.translate("MainWindow", u"\u5bfe\u6570\u8868\u793a", None))
        self.x_invert_checkbox.setText(QCoreApplication.translate("MainWindow", u"\u8ef8\u3092\u53cd\u8ee2", None))
        self.x_major_tick_label.setText(QCoreApplication.translate("MainWindow", u"\u4e3b\u76ee\u76db\uff1a", None))
        self.x_major_tick_mode_combo.setItemText(0, QCoreApplication.translate("MainWindow", u"\u81ea\u52d5", None))
        self.x_major_tick_mode_combo.setItemText(1, QCoreApplication.translate("MainWindow", u"\u56fa\u5b9a\u9593\u9694", None))

        self.x_major_tick_interval_label.setText(QCoreApplication.translate("MainWindow", u"\u9593\u9694\uff1a", None))
        self.x_minor_ticks_visible_checkbox.setText(QCoreApplication.translate("MainWindow", u"\u88dc\u52a9\u76ee\u76db\u3092\u8868\u793a", None))
        self.x_minor_tick_interval_label.setText(QCoreApplication.translate("MainWindow", u"\u9593\u9694\uff1a", None))
        self.axis_tab_widget.setTabText(self.axis_tab_widget.indexOf(self.tab), QCoreApplication.translate("MainWindow", u"X\u8ef8", None))
        self.y_min_label.setText(QCoreApplication.translate("MainWindow", u"\u6700\u5c0f\u5024", None))
        self.y_max_label.setText(QCoreApplication.translate("MainWindow", u"\u6700\u5927\u5024", None))
        self.y_autoscale_checkbox.setText(QCoreApplication.translate("MainWindow", u"\u81ea\u52d5\u30b9\u30b1\u30fc\u30eb", None))
        self.y_log_checkbox.setText(QCoreApplication.translate("MainWindow", u"\u5bfe\u6570\u8868\u793a", None))
        self.y_invert_checkbox.setText(QCoreApplication.translate("MainWindow", u"\u8ef8\u3092\u53cd\u8ee2", None))
        self.y_major_tick_mode_combo.setItemText(0, QCoreApplication.translate("MainWindow", u"\u81ea\u52d5", None))
        self.y_major_tick_mode_combo.setItemText(1, QCoreApplication.translate("MainWindow", u"\u56fa\u5b9a\u9593\u9694", None))

        self.y_major_tick_label.setText(QCoreApplication.translate("MainWindow", u"\u4e3b\u76ee\u76db\uff1a", None))
        self.y_major_tick_interval_label.setText(QCoreApplication.translate("MainWindow", u"\u9593\u9694\uff1a", None))
        self.y_minor_ticks_visible_checkbox.setText(QCoreApplication.translate("MainWindow", u"\u88dc\u52a9\u76ee\u76db\u3092\u8868\u793a", None))
        self.y_minor_tick_interval_label.setText(QCoreApplication.translate("MainWindow", u"\u9593\u9694\uff1a", None))
        self.axis_tab_widget.setTabText(self.axis_tab_widget.indexOf(self.tab_2), QCoreApplication.translate("MainWindow", u"Y\u8ef8", None))
        self.title_text_label.setText(QCoreApplication.translate("MainWindow", u"\u30bf\u30a4\u30c8\u30eb\uff1a", None))
        self.x_label_text_label.setText(QCoreApplication.translate("MainWindow", u"X\u8ef8\u30e9\u30d9\u30eb\uff1a", None))
        self.y_label_text_label.setText(QCoreApplication.translate("MainWindow", u"Y\u8ef8\u30e9\u30d9\u30eb\uff1a", None))
        self.tick_format_label.setText(QCoreApplication.translate("MainWindow", u"\u76ee\u76db\u6570\u5024\uff1a", None))
        self.tick_font_button.setText(QCoreApplication.translate("MainWindow", u"\u30d5\u30a9\u30f3\u30c8\u2026", None))
        self.tick_color_button.setText(QCoreApplication.translate("MainWindow", u"\u8272\u2026", None))
        self.axis_label_format_label.setText(QCoreApplication.translate("MainWindow", u"\u8ef8\u30e9\u30d9\u30eb\uff1a", None))
        self.axis_label_font_button.setText(QCoreApplication.translate("MainWindow", u"\u30d5\u30a9\u30f3\u30c8\u2026", None))
        self.axis_label_color_button.setText(QCoreApplication.translate("MainWindow", u"\u8272\u2026", None))
        self.legend_visible_checkbox.setText(QCoreApplication.translate("MainWindow", u"\u51e1\u4f8b\u3092\u8868\u793a", None))
        self.grid_visible_checkbox.setText(QCoreApplication.translate("MainWindow", u"\u30b0\u30ea\u30c3\u30c9\u3092\u8868\u793a", None))
        self.spine_format_label.setText(QCoreApplication.translate("MainWindow", u"\u5916\u67a0\uff1a", None))
        self.spine_color_button.setText(QCoreApplication.translate("MainWindow", u"\u8272\u2026", None))
        self.tick_width_label.setText(QCoreApplication.translate("MainWindow", u"\u76ee\u76db\u306e\u592a\u3055\uff1a", None))
        self.minor_grid_visible_checkbox.setText(QCoreApplication.translate("MainWindow", u"\u88dc\u52a9\u30b0\u30ea\u30c3\u30c9\u306e\u8868\u793a", None))
        self.axis_tab_widget.setTabText(self.axis_tab_widget.indexOf(self.tab_3), QCoreApplication.translate("MainWindow", u"\u30e9\u30d9\u30eb/\u66f8\u5f0f", None))
    # retranslateUi

