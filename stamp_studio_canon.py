# -*- coding: utf-8 -*-
"""
Stamp Studio (версия для сканеров Canon) — конвертер PDF <-> PNG + редактор наложения факсимиле печати
+ библиотека печатей + сжатие PDF. Светлая/тёмная тема (переключатель, запоминается).
Запуск:  python stamp_studio.py
Зависимости:  pip install PySide6 PyMuPDF Pillow
"""

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

try:                      # новое имя библиотеки
    import pymupdf as fitz
except ImportError:       # старые версии PyMuPDF
    import fitz
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageStat
from PySide6.QtCore import Qt, QRect, QRectF, QSize, QThread, Signal, QEvent, QObject
from PySide6.QtCore import QTimer, QPropertyAnimation
from PySide6.QtWidgets import (QGraphicsOpacityEffect, QGraphicsObject,
                               QGraphicsDropShadowEffect, QTextBrowser, QGridLayout)
from PySide6.QtGui import (QAction, QIcon, QImage, QPixmap, QTransform, QPainter,
                           QKeySequence, QPen, QColor)
from PySide6.QtWidgets import (
    QGraphicsOpacityEffect,
    QApplication, QMainWindow, QFileDialog, QGraphicsScene, QGraphicsView,
    QGraphicsPixmapItem, QLabel, QComboBox, QDoubleSpinBox, QSlider, QPushButton,
    QVBoxLayout, QHBoxLayout, QWidget, QDockWidget, QMessageBox, QCheckBox,
    QSpinBox, QListWidget, QListWidgetItem, QGroupBox, QFormLayout,
    QProgressDialog, QDialog, QRadioButton, QDialogButtonBox, QInputDialog,
    QScrollArea, QSizePolicy, QFrame, QToolButton, QStatusBar, QLineEdit,
    QTabBar, QSplitter, QMenu, QToolBar
)
from PySide6.QtWidgets import (QProgressBar, QTableWidget, QTableWidgetItem, QHeaderView,
                               QAbstractItemView, QStackedWidget)
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl
import stamp_ai as AI

PREVIEW_DPI = 150          # DPI отрисовки страницы в редакторе
EXPORT_STAMP_DPI = 300     # DPI растеризации печати при экспорте

def _pick_lib_dir() -> str:
    """Папка библиотеки: домашняя, а если туда нельзя писать — рядом с программой."""
    candidates = [
        os.path.join(os.path.expanduser("~"), ".stamp_studio"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "stamp_studio_data"),
        os.path.join(tempfile.gettempdir(), "stamp_studio_data"),
    ]
    for d in candidates:
        try:
            os.makedirs(d, exist_ok=True)
            probe = os.path.join(d, ".write_test")
            with open(probe, "w") as f:
                f.write("ok")
            os.remove(probe)
            return d
        except Exception:
            continue
    return candidates[-1]


LIB_DIR = _pick_lib_dir()
LIB_JSON = os.path.join(LIB_DIR, "stamps.json")

PRESETS = [
    ("Круглая печать 38 мм", 38, 38),
    ("Круглая печать 40 мм", 40, 40),
    ("Круглая печать 45 мм", 45, 45),
    ("Треугольный штамп 45×45 мм", 45, 45),
    ("Прямоугольный штамп 70×37 мм", 70, 37),
    ("Факсимиле подписи 40×15 мм", 40, 15),
    ("Свой размер", 0, 0),
]

GOLD = "#e8b04b"

DARK_STYLE = f"""
QMainWindow, QDialog {{ background: #14161c; }}
QWidget {{ color: #e8e6e1; font-size: 13px; }}
QToolBar {{
    background: #1b1e27; border: none; padding: 6px; spacing: 6px;
}}
QToolBar QToolButton {{
    background: #232735; color: #e8e6e1; border: 1px solid #2e3345;
    border-radius: 9px; padding: 0 9px; margin: 0;
    min-height: 36px; max-height: 36px; min-width: 22px;
}}
QToolBar QToolButton:pressed {{ background: #2c3145; }}
QToolBar QToolButton:disabled {{ color: #565c70; border-color: #262a37; }}
QToolBar::separator {{ background: #2e3345; width: 1px; margin: 5px 6px; }}
QToolBar QToolButton:hover {{ border-color: {GOLD}; color: {GOLD}; }}
QDockWidget {{ background: #14161c; titlebar-close-icon: none; }}
QDockWidget::title {{ height: 0px; padding: 0; margin: 0; }}
QLabel#paneltitle {{
    color: {GOLD}; font-weight: bold; font-size: 12px; letter-spacing: 1.2px;
    padding: 6px 2px 4px 2px; border-bottom: 1px solid #2a2f3d;
}}
QGroupBox {{
    background: #1b1e27; border: 1px solid #2a2f3d; border-radius: 12px;
    margin-top: 4px; padding: 30px 10px 10px 10px; font-weight: bold;
}}
QGroupBox::title {{
    subcontrol-origin: padding; subcontrol-position: top left;
    left: 12px; top: 9px; padding: 0; color: {GOLD};
    font-size: 12px; letter-spacing: 0.6px; text-transform: uppercase;
}}
QPushButton {{
    background: #232735; border: 1px solid #2e3345; border-radius: 8px;
    padding: 8px 12px;
}}
QPushButton:hover {{ border-color: {GOLD}; color: {GOLD}; }}
QPushButton:disabled {{ color: #5a5f70; }}
QPushButton#accent {{
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #f0be62, stop:1 #d69a33);
    color: #1b1300; font-weight: bold; border: none;
}}
QPushButton#accent:hover {{ background: #ffd27a; }}
QComboBox, QDoubleSpinBox, QSpinBox, QLineEdit {{
    background: #232735; border: 1px solid #2e3345; border-radius: 8px;
    padding: 5px 8px;
}}
QComboBox:hover, QDoubleSpinBox:hover, QSpinBox:hover {{ border-color: {GOLD}; }}
QComboBox QAbstractItemView {{
    background: #232735; selection-background-color: {GOLD};
    selection-color: #1b1300; border: 1px solid #2e3345;
}}
QListWidget {{
    background: #171a22; border: 1px solid #262b38; border-radius: 10px; padding: 4px;
}}
QListWidget::item {{ padding: 6px; border-radius: 6px; }}
QListWidget::item:selected {{ background: #2c3145; color: {GOLD}; }}
QSlider::groove:horizontal {{
    height: 5px; background: #2e3345; border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {GOLD}; width: 16px; height: 16px; margin: -6px 0; border-radius: 8px;
}}
QSlider::sub-page:horizontal {{ background: {GOLD}; border-radius: 2px; }}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 16px; height: 16px; border: 1px solid #2e3345; border-radius: 4px;
    background: #232735;
}}
QRadioButton::indicator {{ border-radius: 8px; }}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background: {GOLD}; border-color: {GOLD};
}}
QLabel#hint {{ color: #8a8fa3; }}
QLabel#stampinfo {{ color: #8a8fa3; }}
QMessageBox {{ background: #1b1e27; }}
QProgressDialog {{ background: #1b1e27; }}
QScrollBar:vertical {{ background: #171a22; width: 10px; border-radius: 5px; }}
QScrollBar::handle:vertical {{ background: #2e3345; border-radius: 5px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {GOLD}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}

QTabBar::tab {{
    background: #1f2330; color: #9aa0b5; border: 1px solid #2e3345;
    border-radius: 8px; padding: 0 10px; margin: 3px 4px 3px 0;
    min-width: 72px; max-width: 160px; height: 28px;
}}
QTabBar::tab:selected {{ background: #2a3040; color: #e8b04b; font-weight: bold; }}
QTabBar::tab:hover {{ color: #e8b04b; }}
QSplitter::handle {{ background: transparent; }}
QSplitter::handle:vertical {{ height: 8px; }}
QListWidget::item:alternate {{ background: #1b1f28; }}
QMenu {{ background: #232735; border: 1px solid #2e3345; border-radius: 8px; padding: 4px; }}
QMenu::item {{ padding: 6px 22px 6px 14px; border-radius: 5px; }}
QMenu::item:selected {{ background: #2c3145; color: #e8b04b; }}
QMenu::separator {{ height: 1px; background: #2e3345; margin: 4px 8px; }}
QToolTip {{
    background: #2c3145; color: #e8e6e1; border: 1px solid #3a4055;
    border-radius: 6px; padding: 6px 9px;
}}
QProgressBar {{
    border: 1px solid #2e3345; border-radius: 7px; text-align: center;
    background: #171a22; height: 16px;
}}
QProgressBar::chunk {{ background: #e8b04b; border-radius: 6px; }}
QStatusBar {{ background: #1b1e27; color: #8a8fa3; border-top: 1px solid #2e3345; }}
QStatusBar::item {{ border: none; }}
QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus, QSpinBox:focus {{
    border: 2px solid #e8b04b;
}}

QToolBar#dirbar {{
    background: #171a22; border: none; border-bottom: 1px solid #2e3345;
    padding: 3px 2px;
}}
QToolBar#dirbar QPushButton {{ background: #232735; border: 1px solid #2e3345; }}
QToolBar#dirbar QPushButton:hover {{ border-color: #e8b04b; }}
QLabel#path {{ color: #7c8299; padding-left: 2px; }}

QPushButton {{
    min-height: 22px; font-size: 13px; padding: 6px 11px;
}}
QPushButton:hover {{ background: #2a2f40; border-color: #e8b04b; color: #e8b04b; }}
QPushButton:pressed {{ background: #1d2130; border-color: #c69430; }}
QPushButton:checked {{ background: #2c3145; border-color: #e8b04b; color: #e8b04b; }}
QPushButton:disabled {{ background: #1d212b; color: #565c70; border-color: #262a37; }}
QPushButton#accent {{
    min-height: 38px; font-size: 14px; letter-spacing: 0.3px;
    border-radius: 10px; padding: 8px 12px;
}}
QPushButton#accent:pressed {{
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #d69a33, stop:1 #c08a26);
}}
QPushButton#accent:disabled {{ background: #262a37; color: #565c70; }}
QCheckBox {{ spacing: 7px; }}
QCheckBox:hover {{ color: #e8b04b; }}
QGroupBox::title {{ letter-spacing: 0.4px; }}
"""

GOLD_L = "#c07f16"  # золото потемнее для светлого фона

LIGHT_STYLE = f"""
QMainWindow, QDialog {{ background: #f3f1ec; }}
QWidget {{ color: #2b2a26; font-size: 13px; }}
QToolBar {{
    background: #ffffff; border: none; border-bottom: 1px solid #e2ddd2;
    padding: 6px; spacing: 6px;
}}
QToolBar QToolButton {{
    background: #faf8f4; color: #2b2a26; border: 1px solid #e2ddd2;
    border-radius: 9px; padding: 0 9px; margin: 0;
    min-height: 36px; max-height: 36px; min-width: 22px;
}}
QToolBar QToolButton:pressed {{ background: #f0e6d2; }}
QToolBar QToolButton:disabled {{ color: #b8b2a4; border-color: #ece7db; }}
QToolBar::separator {{ background: #e2ddd2; width: 1px; margin: 5px 6px; }}
QToolBar QToolButton:hover {{ border-color: {GOLD_L}; color: {GOLD_L}; }}
QDockWidget {{ background: #f3f1ec; }}
QDockWidget::title {{ height: 0px; padding: 0; margin: 0; }}
QLabel#paneltitle {{
    color: {GOLD_L}; font-weight: bold; font-size: 12px; letter-spacing: 1.2px;
    padding: 6px 2px 4px 2px; border-bottom: 1px solid #e2ddd2;
}}
QGroupBox {{
    background: #ffffff; border: 1px solid #e6e1d6; border-radius: 12px;
    margin-top: 4px; padding: 30px 10px 10px 10px; font-weight: bold;
}}
QGroupBox::title {{
    subcontrol-origin: padding; subcontrol-position: top left;
    left: 12px; top: 9px; padding: 0; color: {GOLD_L};
    font-size: 12px; letter-spacing: 0.6px; text-transform: uppercase;
}}
QPushButton {{
    background: #faf8f4; border: 1px solid #e2ddd2; border-radius: 8px;
    padding: 8px 12px;
}}
QPushButton:hover {{ border-color: {GOLD_L}; color: {GOLD_L}; }}
QPushButton:disabled {{ color: #b3ada0; }}
QPushButton#accent {{
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #f0be62, stop:1 #d69a33);
    color: #2a1e00; font-weight: bold; border: none;
}}
QPushButton#accent:hover {{ background: #ffd27a; }}
QComboBox, QDoubleSpinBox, QSpinBox, QLineEdit {{
    background: #ffffff; border: 1px solid #d8d2c4; border-radius: 8px;
    padding: 5px 8px;
}}
QComboBox:hover, QDoubleSpinBox:hover, QSpinBox:hover {{ border-color: {GOLD_L}; }}
QComboBox QAbstractItemView {{
    background: #ffffff; selection-background-color: {GOLD_L};
    selection-color: #ffffff; border: 1px solid #d8d2c4;
}}
QListWidget {{
    background: #faf8f4; border: 1px solid #e9e4d9; border-radius: 10px; padding: 4px;
}}
QListWidget::item {{ padding: 6px; border-radius: 6px; }}
QListWidget::item:selected {{ background: #f4e3c2; color: #6b4a00; }}
QSlider::groove:horizontal {{
    height: 5px; background: #e2ddd2; border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {GOLD_L}; width: 16px; height: 16px; margin: -6px 0; border-radius: 8px;
}}
QSlider::sub-page:horizontal {{ background: {GOLD_L}; border-radius: 2px; }}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 16px; height: 16px; border: 1px solid #d8d2c4; border-radius: 4px;
    background: #ffffff;
}}
QRadioButton::indicator {{ border-radius: 8px; }}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background: {GOLD_L}; border-color: {GOLD_L};
}}
QLabel#hint {{ color: #97917f; }}
QLabel#stampinfo {{ color: #97917f; }}
QMessageBox {{ background: #ffffff; }}
QProgressDialog {{ background: #ffffff; }}
QScrollBar:vertical {{ background: #f3f1ec; width: 10px; border-radius: 5px; }}
QScrollBar::handle:vertical {{ background: #d8d2c4; border-radius: 5px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {GOLD_L}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}

/* --- проводник, вкладки папок, меню --- */
QTabBar::tab {{
    background: #f3efe6; color: #6b6553; border: 1px solid #ddd6c8;
    border-radius: 8px; padding: 0 10px; margin: 3px 4px 3px 0;
    min-width: 72px; max-width: 160px; height: 28px;
}}
QTabBar::tab:selected {{ background: #ffffff; color: #8a5f0a; font-weight: bold; }}
QTabBar::tab:hover {{ color: #c07f16; }}
QTabBar::close-button {{ subcontrol-position: right; margin-right: 4px; }}
QSplitter::handle {{ background: transparent; }}
QSplitter::handle:vertical {{ height: 8px; }}
QListWidget::item:alternate {{ background: #f7f5f0; }}
QMenu {{ background: #ffffff; border: 1px solid #ddd6c8; border-radius: 8px; padding: 4px; }}
QMenu::item {{ padding: 6px 22px 6px 14px; border-radius: 5px; }}
QMenu::item:selected {{ background: #f4e3c2; color: #6b4a00; }}
QMenu::separator {{ height: 1px; background: #e6e0d2; margin: 4px 8px; }}
QToolTip {{
    background: #2b2a26; color: #f5f2ea; border: none;
    border-radius: 6px; padding: 6px 9px;
}}
QProgressBar {{
    border: 1px solid #ddd6c8; border-radius: 7px; text-align: center;
    background: #f3f1ec; height: 16px;
}}
QProgressBar::chunk {{ background: #c07f16; border-radius: 6px; }}
QStatusBar {{ background: #efece5; color: #6b6553; border-top: 1px solid #e2ddd2; }}
QStatusBar::item {{ border: none; }}
QDockWidget::title {{ border-right: 1px solid #e2ddd2; }}
QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus, QSpinBox:focus {{
    border: 2px solid #c07f16;
}}

QToolBar#dirbar {{
    background: #efece5; border: none; border-bottom: 1px solid #e2ddd2;
    padding: 3px 2px;
}}
QToolBar#dirbar QPushButton {{ background: #ffffff; border: 1px solid #ddd6c8; }}
QToolBar#dirbar QPushButton:hover {{ border-color: #c07f16; }}
QLabel#path {{ color: #8a8474; padding-left: 2px; }}

/* --- кнопки: единая высота, отклик на наведение и нажатие --- */
QPushButton {{
    min-height: 22px; font-size: 13px; padding: 6px 11px;
}}
QPushButton:hover {{ background: #fffdf8; border-color: #c07f16; color: #8a5f0a; }}
QPushButton:pressed {{ background: #f2e8d4; border-color: #a86d0e; }}
QPushButton:checked {{ background: #f4e3c2; border-color: #c07f16; color: #6b4a00; }}
QPushButton:disabled {{ background: #f5f3ee; color: #b8b2a4; border-color: #ece7db; }}
QPushButton#accent {{
    min-height: 38px; font-size: 14px; letter-spacing: 0.3px;
    border-radius: 10px; padding: 8px 12px;
}}
QPushButton#accent:pressed {{
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #d69a33, stop:1 #c08a26);
}}
QPushButton#accent:disabled {{
    background: #ece7db; color: #b8b2a4;
}}
QCheckBox {{ spacing: 7px; }}
QCheckBox:hover {{ color: #8a5f0a; }}
QGroupBox::title {{ letter-spacing: 0.4px; }}
"""



# Дополнения к темам: ручка, компактные «золотые» кнопки, справка, сворачиваемый блок
EXTRA_QSS_DARK = """
QFrame#penbar { background: #1f2330; border: 1px solid #3a4057; border-radius: 14px; }
QLabel#pencap { color: #8a8fa3; font-size: 11px; }
QLabel#penval { color: #e8b04b; font-size: 11px; font-weight: bold; }
QPushButton#primary {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #f0be62, stop:1 #d69a33);
    color: #1b1300; font-weight: bold; border: none; border-radius: 9px; padding: 6px 16px;
}
QPushButton#primary:hover { background: #ffd27a; }
QPushButton#primary:disabled { background: #2a2e3b; color: #5a6072; }
QToolButton#section {
    background: transparent; border: none; color: #8a8fa3; font-weight: bold;
    font-size: 12px; letter-spacing: 0.6px; text-align: left; padding: 6px 4px;
}
QToolButton#section:hover { color: #e8b04b; }
QToolBar QToolButton::menu-indicator { image: none; width: 0; }
QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }
QPushButton#verbtn { color: #8a8fa3; border: none; background: transparent; padding: 0 10px; min-height: 18px; max-height: 18px; }
QStatusBar { min-height: 24px; max-height: 24px; }
QPushButton#verbtn:hover { color: #e8b04b; }
QTextBrowser#guide { background: #171a22; border: none; padding: 6px 18px; font-size: 14px; }
QListWidget#guidenav { background: #1b1e27; border: none; border-right: 1px solid #2a2f3d;
    padding: 10px 6px; font-size: 13px; outline: none; }
QListWidget#guidenav::item { padding: 9px 12px; border-radius: 8px; margin: 1px 0; }
QListWidget#guidenav::item:selected { background: #2c3145; color: #e8b04b; }
QListWidget#guidenav::item:hover { background: #232735; }
QToolBar { padding: 4px 6px; spacing: 3px; }
QToolBar QToolButton { min-height: 32px; max-height: 32px; padding: 0 6px; }
QToolBar#tools { background: #171a22; border: none; border-right: 1px solid #262b39; padding: 6px 5px; spacing: 3px; }
QToolBar#tools QToolButton { min-width: 30px; max-width: 30px; min-height: 30px; max-height: 30px; padding: 0;
    background: transparent; border: 1px solid transparent; border-radius: 8px; }
QToolBar#tools QToolButton:hover { background: #232735; border-color: #e8b04b; }
QToolBar#tools QToolButton:checked { background: #3a321c; border-color: #e8b04b; }
QToolBar#tools QToolButton:disabled { background: transparent; border-color: transparent; }
QToolBar#tools::separator { background: #2a2f3d; height: 1px; margin: 4px 5px; }
QMenuBar { background: #171a22; border-bottom: 1px solid #262b39; padding: 1px 6px; }
QMenuBar::item { background: transparent; padding: 4px 12px; border-radius: 6px; color: #c9cddb; }
QMenuBar::item:selected, QMenuBar::item:pressed { background: #2c3145; color: #e8b04b; }
QMenu::item:disabled { color: #5a6072; }
QMenu::indicator { width: 13px; height: 13px; margin-left: 8px; border-radius: 4px; }
QMenu::indicator:unchecked { border: 1px solid #4a5068; background: transparent; }
QMenu::indicator:checked { border: 1px solid #e8b04b; background: #e8b04b; }
QPushButton#seg { background: transparent; border: 1px solid #2e3345; border-radius: 9px; padding: 7px 16px; color: #9aa0b4; font-weight: bold; }
QPushButton#seg:hover { color: #e8e6e1; }
QPushButton#seg:checked { background: #2c3145; border-color: #e8b04b; color: #e8b04b; font-weight: bold; }
QGroupBox QLabel#plain, QGroupBox QCheckBox { font-weight: normal; }
QLabel#aihead { font-size: 15px; font-weight: bold; color: #f1efe9; }
QPushButton#aichip { text-align: left; border: 1px solid #5a4a22; background: #2a2618; color: #e8b04b;
    border-radius: 8px; padding: 6px 12px; }
QPushButton#aichip:hover { background: #352f1c; }
QPushButton#aichip:disabled { color: #8a8fa3; border-color: #2e3345; background: transparent; }
QListWidget#ailist { background: #1b1e27; border: 1px solid #2a2f3d; border-radius: 10px; padding: 6px; outline: none; }
QListWidget#ailist::item { padding: 8px 10px; border-radius: 8px; margin: 1px 0; }
QListWidget#ailist::item:selected { background: #2c3145; color: #e8b04b; }
QListWidget#ailist::item:hover { background: #232735; }
QListWidget#aiissues { background: #1b1e27; border: 1px solid #2a2f3d; border-radius: 10px; padding: 6px; outline: none; }
QListWidget#aiissues::item { padding: 8px 10px; border-radius: 8px; border-bottom: 1px solid #262b39; }
QListWidget#aiissues::item:selected { background: #2c3145; color: #f1efe9; }
QTableWidget#aitable { background: #1b1e27; alternate-background-color: #20232e; border: 1px solid #2a2f3d;
    border-radius: 10px; gridline-color: #2a2f3d; }
QTableWidget#aitable { outline: none; }
QTableWidget#aitable::item { padding: 6px 8px; }
QTableWidget#aitable::item:selected { background: #2c3145; color: #f1efe9; }
QHeaderView::section { background: #232735; color: #8a8fa3; border: none; border-bottom: 1px solid #2e3345;
    padding: 6px 8px; font-weight: bold; }
QProgressBar { background: #262b39; border: none; border-radius: 3px; }
QProgressBar::chunk { background: #e8b04b; border-radius: 3px; }
"""

EXTRA_QSS_LIGHT = """
QFrame#penbar { background: #ffffff; border: 1px solid #d9d3c5; border-radius: 14px; }
QLabel#pencap { color: #8a8474; font-size: 11px; }
QLabel#penval { color: #a8730c; font-size: 11px; font-weight: bold; }
QPushButton#primary {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #f0be62, stop:1 #d69a33);
    color: #2a1e00; font-weight: bold; border: none; border-radius: 9px; padding: 6px 16px;
}
QPushButton#primary:hover { background: #ffd27a; }
QPushButton#primary:disabled { background: #ece7db; color: #b8b2a4; }
QToolButton#section {
    background: transparent; border: none; color: #8a8474; font-weight: bold;
    font-size: 12px; letter-spacing: 0.6px; text-align: left; padding: 6px 4px;
}
QToolButton#section:hover { color: #a8730c; }
QToolBar QToolButton::menu-indicator { image: none; width: 0; }
QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }
QPushButton#verbtn { color: #8a8474; border: none; background: transparent; padding: 0 10px; min-height: 18px; max-height: 18px; }
QStatusBar { min-height: 24px; max-height: 24px; }
QPushButton#verbtn:hover { color: #a8730c; }
QTextBrowser#guide { background: #ffffff; border: none; padding: 6px 18px; font-size: 14px; }
QListWidget#guidenav { background: #f6f3ec; border: none; border-right: 1px solid #e6e1d6;
    padding: 10px 6px; font-size: 13px; outline: none; }
QListWidget#guidenav::item { padding: 9px 12px; border-radius: 8px; margin: 1px 0; }
QListWidget#guidenav::item:selected { background: #fbefd3; color: #8a5f0a; }
QListWidget#guidenav::item:hover { background: #efeadf; }
QToolBar { padding: 4px 6px; spacing: 3px; }
QToolBar QToolButton { min-height: 32px; max-height: 32px; padding: 0 6px; }
QToolBar#tools { background: #fbf9f4; border: none; border-right: 1px solid #e6e1d6; padding: 6px 5px; spacing: 3px; }
QToolBar#tools QToolButton { min-width: 30px; max-width: 30px; min-height: 30px; max-height: 30px; padding: 0;
    background: transparent; border: 1px solid transparent; border-radius: 8px; }
QToolBar#tools QToolButton:hover { background: #ffffff; border-color: #d69a33; }
QToolBar#tools QToolButton:checked { background: #fbefd3; border-color: #d69a33; }
QToolBar#tools QToolButton:disabled { background: transparent; border-color: transparent; }
QToolBar#tools::separator { background: #e6e1d6; height: 1px; margin: 4px 5px; }
QMenuBar { background: #fbf9f4; border-bottom: 1px solid #e6e1d6; padding: 1px 6px; }
QMenuBar::item { background: transparent; padding: 4px 12px; border-radius: 6px; color: #4a4636; }
QMenuBar::item:selected, QMenuBar::item:pressed { background: #f4e3c2; color: #6b4a00; }
QMenu::item:disabled { color: #b8b2a4; }
QMenu::indicator { width: 13px; height: 13px; margin-left: 8px; border-radius: 4px; }
QMenu::indicator:unchecked { border: 1px solid #b8b2a4; background: transparent; }
QMenu::indicator:checked { border: 1px solid #d69a33; background: #d69a33; }
QPushButton#seg { background: transparent; border: 1px solid #e2ddd2; border-radius: 9px; padding: 7px 16px; color: #6b6553; font-weight: bold; }
QPushButton#seg:hover { color: #2b2820; }
QPushButton#seg:checked { background: #fbefd3; border-color: #d69a33; color: #6b4a00; font-weight: bold; }
QGroupBox QLabel#plain, QGroupBox QCheckBox { font-weight: normal; }
QLabel#aihead { font-size: 15px; font-weight: bold; color: #2b2820; }
QPushButton#aichip { text-align: left; border: 1px solid #e3c98d; background: #fdf4dd; color: #7a5200;
    border-radius: 8px; padding: 6px 12px; }
QPushButton#aichip:hover { background: #fbeac0; }
QPushButton#aichip:disabled { color: #8a8474; border-color: #e6e1d6; background: transparent; }
QListWidget#ailist { background: #f6f3ec; border: 1px solid #e6e1d6; border-radius: 10px; padding: 6px; outline: none; }
QListWidget#ailist::item { padding: 8px 10px; border-radius: 8px; margin: 1px 0; }
QListWidget#ailist::item:selected { background: #fbefd3; color: #6b4a00; }
QListWidget#ailist::item:hover { background: #efeadf; }
QListWidget#aiissues { background: #ffffff; border: 1px solid #e6e1d6; border-radius: 10px; padding: 6px; outline: none; }
QListWidget#aiissues::item { padding: 8px 10px; border-radius: 8px; border-bottom: 1px solid #efeadf; }
QListWidget#aiissues::item:selected { background: #fbefd3; color: #2b2820; }
QTableWidget#aitable { background: #ffffff; alternate-background-color: #faf7f0; border: 1px solid #e6e1d6;
    border-radius: 10px; gridline-color: #ece7db; }
QTableWidget#aitable { outline: none; }
QTableWidget#aitable::item { padding: 6px 8px; }
QTableWidget#aitable::item:selected { background: #fbefd3; color: #2b2820; }
QHeaderView::section { background: #f6f3ec; color: #8a8474; border: none; border-bottom: 1px solid #e6e1d6;
    padding: 6px 8px; font-weight: bold; }
QProgressBar { background: #ece7db; border: none; border-radius: 3px; }
QProgressBar::chunk { background: #d69a33; border-radius: 3px; }
"""

SETTINGS_JSON = os.path.join(LIB_DIR, "settings.json")

# ---------------------------------------------------------------- версия и обновления
APP_VERSION = "6.4.2"
EDITION = "canon"                 # main — основная, canon — для сканеров Canon
APP_TITLE = "Stamp Studio" + (" Canon" if EDITION == "canon" else "")
GITHUB_URL = "https://github.com/alegawhats-del/StampStudio"
UPDATE_URL = "https://raw.githubusercontent.com/alegawhats-del/StampStudio/main/version.json"


def app_base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


# установленная через установщик копия умеет обновляться сама
INSTALLED = os.path.exists(os.path.join(app_base_dir(), "installed.flag"))


def vtuple(v):
    out = []
    for part in str(v).strip().lstrip("v").split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        out.append(int(digits) if digits else 0)
    return tuple(out + [0] * (3 - len(out)))



def settings_load() -> dict:
    try:
        with open(SETTINGS_JSON, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def settings_save(d: dict):
    os.makedirs(LIB_DIR, exist_ok=True)
    with open(SETTINGS_JSON, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)


MM_TO_PT = 72.0 / 25.4


def mm_to_preview_px(mm: float) -> float:
    return mm / 25.4 * PREVIEW_DPI


def human_size(nbytes: int) -> str:
    for unit in ("Б", "КБ", "МБ", "ГБ"):
        if nbytes < 1024 or unit == "ГБ":
            return f"{nbytes:.1f} {unit}" if unit != "Б" else f"{nbytes} {unit}"
        nbytes /= 1024


# ---------------------------------------------------------------- библиотека

def lib_load() -> list:
    try:
        with open(LIB_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
        return [s for s in data if os.path.exists(s.get("file", ""))]
    except Exception:
        return []


def lib_save(items: list):
    os.makedirs(LIB_DIR, exist_ok=True)
    with open(LIB_JSON, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


STAMP_CATEGORIES = ["Без категории", "Печати компаний", "Штампы", "Подписи",
                    "Банковские", "Таможня", "Архив"]


def lib_categories() -> list:
    used = []
    for e in lib_load():
        c = (e.get("category") or "").strip()
        if c and c not in STAMP_CATEGORIES and c not in used:
            used.append(c)
    return STAMP_CATEGORIES + used


def lib_add(name: str, mm_w: float, mm_h: float,
            src_path: str = None, pil_image=None, category: str = "") -> dict:
    """Добавить печать в библиотеку из файла ИЛИ из уже загруженной картинки."""
    os.makedirs(LIB_DIR, exist_ok=True)
    dst = os.path.join(LIB_DIR, f"stamp_{int(time.time() * 1000)}.png")
    if src_path and os.path.exists(src_path):
        if os.path.splitext(src_path)[1].lower() == ".png":
            shutil.copy2(src_path, dst)
        else:
            Image.open(src_path).convert("RGBA").save(dst, "PNG")
    elif pil_image is not None:
        pil_image.convert("RGBA").save(dst, "PNG")
    else:
        raise ValueError("нечего сохранять")
    entry = {"name": name, "file": dst, "mm_w": round(mm_w, 1),
             "mm_h": round(mm_h, 1), "category": category or "Без категории"}
    items = lib_load()
    items.append(entry)
    lib_save(items)
    return entry



INK_COLORS = {
    "file": None,
    "blue": (28, 52, 148),
    "violet": (86, 40, 130),
    "black": (25, 25, 25),
}


def prepare_stamp(pil_image, remove_bg=True, threshold=10, ink="file"):
    """Оставить только краску печати, убрав любую подложку.

    Наличие альфа-канала само по себе НЕ значит, что фон убран: часто внутри
    рамки лежит сплошная чёрная или белая заливка. Поэтому решаем по плотности
    непрозрачной области: если она закрывает почти весь свой прямоугольник —
    это подложка, и её надо снять. Краска отличается от подложки насыщенностью
    цвета (а для чёрных печатей — яркостью).
    """
    im = pil_image.convert("RGBA")
    r, g, b, a0 = im.split()

    opaque = a0.point(lambda v: 255 if v > 128 else 0)
    opaque_count = opaque.histogram()[255]
    bbox = im.getbbox()
    box_area = ((bbox[2] - bbox[0]) * (bbox[3] - bbox[1])) if bbox else 0
    fill_ratio = opaque_count / box_area if box_area else 0.0
    # краска занимает меньше половины своего прямоугольника, подложка — почти весь
    already_clean = fill_ratio < 0.55
    cleaned = False
    a = a0

    if remove_bg and opaque_count and not already_clean:
        mx = ImageChops.lighter(ImageChops.lighter(r, g), b)
        mn = ImageChops.darker(ImageChops.darker(r, g), b)
        chroma = ImageChops.subtract(mx, mn)       # 0 = белый/серый/чёрный
        colored = sum(chroma.histogram(opaque)[35:])
        ink_mask = None

        if colored / opaque_count > 0.02:          # цветная краска — чистим по цвету
            lo = int(6 + threshold * 0.45)
            hi = lo + 28
            span = max(1, hi - lo)
            ink_mask = chroma.point(lambda v: 0 if v <= lo else
                                    (255 if v >= hi else int((v - lo) * 255 / span)))
        else:                                      # чёрная печать — чистим по яркости
            gray = im.convert("L")
            gh = gray.histogram(opaque)
            light, dark = sum(gh[200:]), sum(gh[:56])
            if max(light, dark) / opaque_count > 0.25:
                base = gray.point(lambda v: 255 - v) if light >= dark else gray
                lo = int(30 + threshold * 1.5)
                hi = min(255, lo + 60)
                span = max(1, hi - lo)
                ink_mask = base.point(lambda v: 0 if v <= lo else
                                      (255 if v >= hi else int((v - lo) * 255 / span)))

        if ink_mask is not None:
            new_a = ImageChops.multiply(a0, ink_mask)
            left = new_a.point(lambda v: 255 if v > 128 else 0).histogram()[255]
            # защита: если "очистка" стёрла почти всю печать — откатываемся
            if left > opaque_count * 0.02:
                a = new_a
                cleaned = True
                im = Image.merge("RGBA", (r, g, b, a))

    ink_rgb = INK_COLORS.get(ink)
    if ink_rgb is not None:
        solid = Image.new("RGBA", im.size, ink_rgb + (255,))
        solid.putalpha(a)
        im = solid
    elif cleaned:
        # краска со снимка на тёмном фоне слишком светлая для белой бумаги — притемняем
        try:
            binary = a.point(lambda v: 255 if v > 128 else 0)
            ink_lum = ImageStat.Stat(im.convert("L"), mask=binary).mean[0]
        except Exception:
            ink_lum = 0
        if ink_lum > 135:
            k = 110.0 / max(1.0, ink_lum)
            im = Image.merge("RGBA", (
                r.point(lambda v: int(min(255, v * k))),
                g.point(lambda v: int(min(255, v * k))),
                b.point(lambda v: int(min(255, v * k * 1.25))),
                a))

    bbox2 = im.getbbox()
    return (im.crop(bbox2) if bbox2 else im), already_clean


# ---------------------------------------------------------------- элементы



class ColumnGrid(QListWidget):
    """Плитка с фиксированным числом столбцов — подстраивается под ширину сама."""

    def __init__(self, columns=3, min_cell=76, parent=None):
        super().__init__(parent)
        self.columns = columns
        self.min_cell = min_cell
        self.max_icon = 512         # потолок размера иконки
        self.min_rows = 0           # сколько рядов должно быть видно всегда
        self.setViewMode(QListWidget.IconMode)
        self.setResizeMode(QListWidget.Adjust)
        self.setMovement(QListWidget.Static)
        self.setUniformItemSizes(True)
        self.setWordWrap(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

    def fit_grid(self):
        vp = self.viewport().width()
        if vp <= 0:
            return
        gap = self.spacing() * 2
        cell = max(self.min_cell, (vp - 4) // self.columns - gap)
        if self.gridSize().width() != cell:
            icon = max(44, min(self.max_icon, cell - gap - 20))
            self.setGridSize(QSize(cell, icon + 26))
            self.setIconSize(QSize(icon, icon))
            if self.min_rows:
                self.setMinimumHeight(self.min_rows * (icon + 26) + 2 * self.spacing() + 4)

    def sizeHint(self):
        # по умолчанию QListWidget просит 192px — из-за этого панель
        # переставала помещаться на невысоких экранах
        return QSize(220, self.minimumHeight() or 96)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fit_grid()


class NoWheelFilter(QObject):
    """Колесо мыши не меняет значения полей, пока они не в фокусе.

    Иначе при прокрутке панели случайно уезжают размеры и повороты.
    """

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Wheel and not obj.hasFocus():
            event.ignore()
            return True
        return False


class StampItem(QGraphicsPixmapItem):
    """Печать на странице. Позиция хранится в координатах превью-страницы."""

    def __init__(self, pixmap: QPixmap, pil_image: Image.Image, mm_w: float, mm_h: float, page_index: int):
        super().__init__(pixmap)
        self.pil_image = pil_image
        self.mm_w = mm_w
        self.mm_h = mm_h
        self.page_index = page_index
        self.opacity_value = 0.85
        self.setFlags(
            QGraphicsPixmapItem.ItemIsMovable
            | QGraphicsPixmapItem.ItemIsSelectable
            | QGraphicsPixmapItem.ItemSendsGeometryChanges
        )
        self.setTransformationMode(Qt.SmoothTransformation)
        self.setTransformOriginPoint(pixmap.width() / 2, pixmap.height() / 2)
        self.setOpacity(self.opacity_value)
        self.apply_size()

    def apply_size(self):
        pw, ph = self.pixmap().width(), self.pixmap().height()
        if pw == 0 or ph == 0:
            return
        t = QTransform()
        t.scale(mm_to_preview_px(self.mm_w) / pw, mm_to_preview_px(self.mm_h) / ph)
        self.setTransform(t)

    def center_scene_pos(self):
        return self.mapToScene(self.pixmap().width() / 2, self.pixmap().height() / 2)



class MascotOverlay(QLabel):
    """Картинка-талисман в углу рабочей области. Не перехватывает мышь."""

    def __init__(self, view, image_path):
        super().__init__(view)
        self.view = view
        self.pix = QPixmap(image_path)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setScaledContents(True)
        self.setStyleSheet("background: transparent;")
        self._opacity = 0.92
        self._height = 200
        self.wanted_visible = True
        eff = QGraphicsOpacityEffect(self)
        eff.setOpacity(self._opacity)
        self.setGraphicsEffect(eff)
        self.effect = eff
        self.apply_size()

    MIN_SIDE = 46

    def apply_size(self, height=None):
        if self.pix.isNull():
            return
        h = int(height or self._height)
        w = max(1, int(self.pix.width() * h / self.pix.height()))
        self.setPixmap(self.pix)
        self.resize(w, h)

    def _height_for_width(self, width):
        if self.pix.isNull() or self.pix.width() == 0:
            return 0
        return int(width * self.pix.height() / self.pix.width())

    def set_height(self, h):
        self._height = max(80, min(420, h))
        self.apply_size()

    def set_opacity(self, value):
        self._opacity = max(0.15, min(1.0, value))
        self.effect.setOpacity(self._opacity)

    def reposition(self, page_rect=None):
        """Встать в свободное место рядом с листом, при нехватке — ужаться."""
        vp = self.view.viewport()
        m = 12
        self.apply_size()                      # сперва желаемый размер

        def try_place():
            spots = [
                (vp.width() - self.width() - m, vp.height() - self.height() - m),
                (m, vp.height() - self.height() - m),
                (vp.width() - self.width() - m, m),
                (m, m),
            ]
            for x, y in spots:
                if x < 0 or y < 0:
                    continue
                box = QRect(x, y, self.width(), self.height())
                if page_rect is None or not box.intersects(page_rect):
                    self.move(x, y)
                    self.setVisible(self.wanted_visible)
                    self.raise_()
                    return True
            return False

        if try_place():
            return True
        if page_rect is None:
            self.setVisible(False)
            return False

        # места в полный размер нет — вписываемся в самое широкое свободное поле
        gap = 6                                # у поля отступы поменьше
        right = vp.width() - page_rect.right() - gap * 2
        left = page_rect.left() - gap * 2
        bottom = vp.height() - page_rect.bottom() - gap * 2
        top = page_rect.top() - gap * 2

        if max(right, left) >= max(bottom, top):
            width = max(right, left)
            if width >= self.MIN_SIDE:
                h = min(self._height, self._height_for_width(width),
                        vp.height() - gap * 2)
                if h >= self.MIN_SIDE:
                    self.apply_size(h)
                    x = (vp.width() - self.width() - gap) if right >= left else gap
                    y = max(gap, vp.height() - self.height() - gap)
                    self.move(x, y)
                    self.setVisible(self.wanted_visible)
                    self.raise_()
                    return True
        else:
            height = max(bottom, top)
            if height >= self.MIN_SIDE:
                h = min(self._height, height)
                self.apply_size(h)
                if self.width() <= vp.width() - gap * 2:
                    x = max(gap, vp.width() - self.width() - gap)
                    y = (vp.height() - self.height() - gap) if bottom >= top else gap
                    self.move(x, y)
                    self.setVisible(self.wanted_visible)
                    self.raise_()
                    return True

        self.apply_size()
        self.setVisible(False)     # свободного места нет совсем — не мешаем
        return False



# ======================================================================
#  Ручка: подпись рисуется мышью прямо на странице
# ======================================================================

PEN_INKS = [("Синяя", (27, 54, 168)), ("Тёмно-синяя", (22, 32, 104)), ("Чёрная", (28, 28, 32))]


def pen_dense_points(pts):
    """Сглаженная ломаная: квадратичные кривые через середины отрезков,
    с шагом около 0.7 px. pts — [(x, y, w)], возвращает такие же тройки."""
    n = len(pts)
    if n == 0:
        return []
    if n == 1:
        return [pts[0]]
    if n == 2:
        pts = [pts[0], ((pts[0][0] + pts[1][0]) / 2, (pts[0][1] + pts[1][1]) / 2,
                        (pts[0][2] + pts[1][2]) / 2), pts[1]]
        n = 3

    def mid(a, b):
        return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2)

    out = [pts[0]]
    start = pts[0]
    for i in range(1, n - 1):
        ctrl = pts[i]
        end = mid(pts[i], pts[i + 1]) if i < n - 2 else pts[n - 1]
        length = (abs(ctrl[0] - start[0]) + abs(ctrl[1] - start[1])
                  + abs(end[0] - ctrl[0]) + abs(end[1] - ctrl[1]))
        steps = max(2, int(length / 0.7))
        for s in range(1, steps + 1):
            t = s / steps
            a, b, c = (1 - t) ** 2, 2 * (1 - t) * t, t * t
            out.append((a * start[0] + b * ctrl[0] + c * end[0],
                        a * start[1] + b * ctrl[1] + c * end[1],
                        a * start[2] + b * ctrl[2] + c * end[2]))
        start = end
    return out


def pen_paint_strokes(painter, strokes, color):
    """Нарисовать штрихи переменной толщины (как шариковая ручка)."""
    r, g, b = color
    painter.setRenderHint(QPainter.Antialiasing, True)
    col = QColor(r, g, b, 238)
    for st in strokes:
        dense = st.get("dense") or pen_dense_points(st["pts"])
        if not dense:
            continue
        if len(dense) == 1:
            x, y, w = dense[0]
            painter.setPen(Qt.NoPen)
            painter.setBrush(col)
            painter.drawEllipse(QPointF(x, y), w / 2, w / 2)
            continue
        pen = QPen(col, 1.0)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        px, py, pw = dense[0]
        for x, y, w in dense[1:]:
            pen.setWidthF(max(0.3, (pw + w) / 2))
            painter.setPen(pen)
            painter.drawLine(QPointF(px, py), QPointF(x, y))
            px, py, pw = x, y, w


class PenLayer(QGraphicsObject):
    """Слой поверх страницы, на котором видно, что рисуется."""

    def __init__(self, rect):
        super().__init__()
        self._rect = QRectF(rect)
        self.strokes = []
        self.color = PEN_INKS[0][1]
        self.setZValue(50)

    def boundingRect(self):
        return self._rect

    def paint(self, painter, option, widget=None):
        pen_paint_strokes(painter, self.strokes, self.color)


class PenBar(QFrame):
    """Плавающая панель ручки над страницей."""

    def __init__(self, parent, on_change, on_undo, on_clear, on_done, on_cancel):
        super().__init__(parent)
        self.setObjectName("penbar")
        self.on_change = on_change
        st = settings_load().get("pen", {})
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 10, 14, 10)
        outer.setSpacing(8)
        lay = QHBoxLayout()
        lay.setSpacing(12)
        outer.addLayout(lay)
        try:
            sh = QGraphicsDropShadowEffect(self)
            sh.setBlurRadius(28)
            sh.setOffset(0, 6)
            sh.setColor(QColor(0, 0, 0, 70))
            self.setGraphicsEffect(sh)
        except Exception:
            pass

        def labelled(text, slider, value_label):
            box = QVBoxLayout()
            box.setSpacing(1)
            top = QHBoxLayout()
            cap = QLabel(text)
            cap.setObjectName("pencap")
            top.addWidget(cap)
            top.addStretch(1)
            value_label.setObjectName("penval")
            top.addWidget(value_label)
            box.addLayout(top)
            box.addWidget(slider)
            return box

        self.sl_width = QSlider(Qt.Horizontal)
        self.sl_width.setRange(2, 30)                       # 0.2 … 3.0 мм
        self.sl_width.setValue(int(st.get("width", 6)))
        self.sl_width.setFixedWidth(120)
        self.sl_width.setToolTip("Толщина линии ручки")
        self.lbl_width = QLabel()
        lay.addLayout(labelled("Толщина", self.sl_width, self.lbl_width))

        self.sl_smooth = QSlider(Qt.Horizontal)
        self.sl_smooth.setRange(0, 100)
        self.sl_smooth.setValue(int(st.get("smooth", 55)))
        self.sl_smooth.setFixedWidth(120)
        self.sl_smooth.setToolTip("Влево — линия резкая, точно за мышью.\n"
                                  "Вправо — плавная, дрожание руки сглаживается.")
        self.lbl_smooth = QLabel()
        lay.addLayout(labelled("Плавность", self.sl_smooth, self.lbl_smooth))

        self.ink_index = int(st.get("ink", 0)) % len(PEN_INKS)
        self.ink_btns = []
        inks = QHBoxLayout()
        inks.setSpacing(6)
        for i, (name, rgb) in enumerate(PEN_INKS):
            b = QPushButton()
            b.setCheckable(True)
            b.setFixedSize(26, 26)
            b.setToolTip(f"Цвет ручки: {name.lower()}")
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet(
                "QPushButton { background: rgb(%d,%d,%d); border: 2px solid transparent; "
                "border-radius: 13px; min-height: 0; padding: 0; }"
                "QPushButton:checked { border: 2px solid #e8b04b; }" % rgb)
            b.clicked.connect(lambda _=False, i=i: self._pick_ink(i))
            self.ink_btns.append(b)
            inks.addWidget(b)
        lay.addLayout(inks)
        lay.addStretch(1)

        lay = QHBoxLayout()                    # второй ряд — действия
        lay.setSpacing(8)
        outer.addLayout(lay)

        def btn(text, tip, slot, accent=False):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.setMinimumHeight(32)
            b.setCursor(Qt.PointingHandCursor)
            if accent:
                b.setObjectName("primary")
            b.clicked.connect(slot)
            lay.addWidget(b)
            return b

        self.b_undo = btn("↶ Отменить штрих", "Убрать последний штрих  (Ctrl+Z)", on_undo)
        self.b_clear = btn("Очистить", "Стереть всё нарисованное", on_clear)
        lay.addStretch(1)
        self.b_cancel = btn("Отмена", "Выйти без подписи  (Esc)", on_cancel)
        self.b_done = btn("Готово", "Оставить подпись на странице  (Enter)", on_done, accent=True)

        self.sl_width.valueChanged.connect(self._changed)
        self.sl_smooth.valueChanged.connect(self._changed)
        self._pick_ink(self.ink_index, notify=False)
        self._changed()

    def _pick_ink(self, i, notify=True):
        self.ink_index = i
        for k, b in enumerate(self.ink_btns):
            b.setChecked(k == i)
        if notify:
            self._changed()

    def _changed(self, *_):
        self.lbl_width.setText(f"{self.sl_width.value() / 10:.1f} мм")
        v = self.sl_smooth.value()
        self.lbl_smooth.setText("резко" if v < 15 else ("плавно" if v > 70 else "средне"))
        try:
            s = settings_load()
            s["pen"] = {"width": self.sl_width.value(), "smooth": v, "ink": self.ink_index}
            settings_save(s)
        except Exception:
            pass
        self.on_change()

    def width_px(self):
        return mm_to_preview_px(self.sl_width.value() / 10.0)

    def smooth(self):
        return self.sl_smooth.value() / 100.0

    def ink(self):
        return PEN_INKS[self.ink_index][1]


class EditorView(QGraphicsView):
    def __init__(self, scene):
        super().__init__(scene)
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.set_theme("light")

    def set_theme(self, theme: str):
        bg = "#0e1015" if theme == "dark" else "#dfdacf"
        self.setStyleSheet("QGraphicsView { border: none; background: %s; }" % bg)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
            self.scale(factor, factor)
            self._notify()
        else:
            super().wheelEvent(event)


    # ---------------- ручка ----------------
    pen_layer = None
    pen_bar = None

    def pen_active(self):
        return self.pen_layer is not None

    def _pen_scene_pos(self, event):
        return self.mapToScene(event.position().toPoint())

    def mousePressEvent(self, event):
        if not self.pen_active():
            return super().mousePressEvent(event)
        if event.button() != Qt.LeftButton:
            return
        p = self._pen_scene_pos(event)
        self._pen_brush = (p.x(), p.y())
        self._pen_target = (p.x(), p.y())
        self._pen_t = time.time()
        self._pen_w = self.pen_bar.width_px()
        self._pen_stroke = {"pts": [(p.x(), p.y(), self._pen_w)], "dense": None}
        self.pen_layer.strokes.append(self._pen_stroke)
        self.pen_layer.update()
        event.accept()

    def mouseMoveEvent(self, event):
        if not self.pen_active():
            return super().mouseMoveEvent(event)
        st = getattr(self, "_pen_stroke", None)
        if st is None or not (event.buttons() & Qt.LeftButton):
            return
        p = self._pen_scene_pos(event)
        self._pen_target = (p.x(), p.y())
        self._pen_advance(st, finishing=False)
        event.accept()

    def _pen_advance(self, st, finishing):
        """«Ленивая кисть»: перо тянется к мыши; чем больше плавность, тем сильнее отстаёт."""
        smooth = self.pen_bar.smooth()
        alpha = 1.0 - 0.9 * smooth                    # доля пути за одно событие
        base = self.pen_bar.width_px()
        bx, by = self._pen_brush
        tx, ty = self._pen_target
        steps = 1 if not finishing else 14
        for _ in range(steps):
            a = alpha if not finishing else max(alpha, 0.35)
            nx, ny = bx + (tx - bx) * a, by + (ty - by) * a
            dist = ((nx - bx) ** 2 + (ny - by) ** 2) ** 0.5
            if dist < 0.35:
                if finishing:
                    break
                continue
            now = time.time()
            dt = max(0.004, now - self._pen_t)
            self._pen_t = now
            speed = dist / dt / PREVIEW_DPI * 25.4        # мм/с
            # быстро — тоньше, медленно — жирнее (как у шариковой ручки)
            k = 1.18 - 0.5 * min(1.0, speed / 320.0)
            w = self._pen_w + (base * k - self._pen_w) * 0.35
            self._pen_w = w
            st["pts"].append((nx, ny, w))
            bx, by = nx, ny
        self._pen_brush = (bx, by)
        st["dense"] = None
        self.pen_layer.update()

    def mouseReleaseEvent(self, event):
        if not self.pen_active():
            return super().mouseReleaseEvent(event)
        st = getattr(self, "_pen_stroke", None)
        if st is not None:
            self._pen_advance(st, finishing=True)
            last = st["pts"][-1]
            st["pts"].append((last[0], last[1], last[2] * 0.7))    # перо отрывается — хвостик тоньше
            st["dense"] = pen_dense_points(st["pts"])
            self.pen_layer.update()
        self._pen_stroke = None
        event.accept()

    def keyPressEvent(self, event):
        if self.pen_active():
            cb = getattr(self, "on_pen_key", None)
            if cb is not None and cb(event):
                return
        super().keyPressEvent(event)

    def place_pen_bar(self):
        if self.pen_bar is not None:
            self.pen_bar.adjustSize()
            self.pen_bar.move(max(8, (self.width() - self.pen_bar.width()) // 2), 12)
            self.pen_bar.raise_()

    def _notify(self):
        cb = getattr(self, "on_view_changed", None)
        if cb is not None:
            cb()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.place_pen_bar()
        self._notify()

    def scrollContentsBy(self, dx, dy):
        super().scrollContentsBy(dx, dy)
        self._notify()


class CompressDialog(QDialog):
    def __init__(self, parent=None, source_path=None):
        super().__init__(parent)
        self.setWindowTitle("Сжатие PDF")
        self.source_path = source_path
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Выберите режим сжатия:"))

        self.rb_light = QRadioButton("Лёгкое — без потери качества\n(чистка мусора; экономия небольшая, если файл уже сжат)")
        self.rb_medium = QRadioButton("Среднее — пережать картинки внутри PDF ★ рекомендуется\n(фото/сканы внутри станут JPEG, текст останется текстом)")
        self.rb_strong = QRadioButton("Сильное — весь документ в JPEG\n(максимальная экономия; текст перестанет выделяться)")
        self.rb_tiny = QRadioButton("Минимальное — для отправки по почте/мессенджеру\n"
                                    "(110 dpi, JPEG 50 %: читаемо, но качество низкое; ~150 КБ на лист)")
        self.rb_medium.setChecked(True)
        lay.addWidget(self.rb_light)
        lay.addWidget(self.rb_medium)
        lay.addWidget(self.rb_strong)
        lay.addWidget(self.rb_tiny)

        row = QHBoxLayout()
        row.addWidget(QLabel("Качество JPEG:"))
        self.spin_q = QSpinBox(); self.spin_q.setRange(30, 95); self.spin_q.setValue(70); self.spin_q.setSuffix(" %")
        row.addWidget(self.spin_q)
        row.addWidget(QLabel("DPI (для сильного):"))
        self.spin_dpi = QSpinBox(); self.spin_dpi.setRange(72, 300); self.spin_dpi.setValue(150); self.spin_dpi.setSuffix(" DPI")
        row.addWidget(self.spin_dpi)
        lay.addLayout(row)

        self.chk_meta = QCheckBox("удалить метаданные (автор, программа, даты)")
        self.chk_meta.setChecked(True)
        lay.addWidget(self.chk_meta)

        self.chk_replace = QCheckBox("сохранить поверх исходного файла (с заменой)")
        self.chk_replace.setEnabled(bool(self.source_path))
        self.chk_replace.setToolTip(
            "Сжатый документ запишется вместо исходного, в ту же папку "
            "и под тем же именем.")
        lay.addWidget(self.chk_replace)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Сжать")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)



def resource_path(name: str) -> str:
    """Путь к файлу и при обычном запуске, и внутри собранного приложения."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


_close_icon_path = None


def tab_close_icon_path(color: str) -> str:
    """PNG-крестик для вкладок (QSS умеет только url())."""
    path = os.path.join(tempfile.gettempdir(), f"stampstudio_close_{color.strip('#')}.png")
    if not os.path.exists(path):
        try:
            draw_icon("close", color, 32).pixmap(32, 32).save(path, "PNG")
        except Exception:
            return ""
    return path


def find_resource(name: str):
    """Найти файл: сначала рядом с программой, потом внутри сборки.

    Благодаря первому варианту картинку можно заменить, просто положив
    другой файл рядом с готовым .exe — пересобирать не нужно.
    """
    places = []
    if getattr(sys, "frozen", False):
        places.append(os.path.dirname(os.path.abspath(sys.executable)))
        places.append(getattr(sys, "_MEIPASS", ""))
    else:
        places.append(os.path.dirname(os.path.abspath(__file__)))
        places.append(getattr(sys, "_MEIPASS", ""))
    for base in places:
        if not base:
            continue
        p = os.path.join(base, name)
        if os.path.exists(p):
            return p
    return None


AI.SETTINGS_LOAD = settings_load
AI.SETTINGS_SAVE = settings_save
AI.FIND_RESOURCE = find_resource


def write_file_safely(path: str, data: bytes, owner=None) -> str:
    """Записать файл, даже если он сейчас открыт в самой программе.

    На Windows PyMuPDF держит открытый PDF занятым, поэтому перезапись
    падала с «отказано в доступе». Пишем во временный файл рядом и
    подменяем; если цель — открытый документ, сначала освобождаем его.
    """
    path = os.path.abspath(path)
    folder = os.path.dirname(path) or "."
    os.makedirs(folder, exist_ok=True)

    reopen_after = False
    if owner is not None and getattr(owner, "doc", None) is not None:
        cur = getattr(owner, "doc_path", None)
        try:
            same = cur and os.path.exists(str(cur)) and os.path.samefile(str(cur), path)
        except OSError:
            same = False
        if same:
            owner.doc.close()          # освобождаем файл, страницы уже в data
            reopen_after = True

    tmp = os.path.join(folder, f".~{os.path.basename(path)}.tmp")
    try:
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, path)          # атомарная замена, работает поверх существующего
    except PermissionError:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise PermissionError(
            "Файл занят другой программой или открыт в просмотрщике PDF.\n"
            "Закройте его и попробуйте снова, либо сохраните под другим именем.")
    except Exception:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
        raise
    finally:
        if reopen_after:
            owner.doc = fitz.open(path)
            owner.doc_path = path
    return path


# ---------------------------------------------------------------- иконки

from PySide6.QtGui import QPen, QColor, QPainterPath, QBrush
from PySide6.QtCore import QPointF


def draw_icon(kind: str, color: str, size: int = 64) -> QIcon:
    """Единый набор нарисованных иконок — выглядит цельно в обеих темах."""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    c = QColor(color)
    pen = QPen(c, size * 0.085)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    s = size
    u = s / 16.0

    def line(x1, y1, x2, y2):
        p.drawLine(int(x1 * u), int(y1 * u), int(x2 * u), int(y2 * u))

    def rect(x, y, w, h, r=1.5):
        p.drawRoundedRect(int(x * u), int(y * u), int(w * u), int(h * u), r * u, r * u)

    if kind == "folder":
        path = QPainterPath()
        path.moveTo(2 * u, 5 * u)
        path.lineTo(2 * u, 3.4 * u); path.lineTo(6.4 * u, 3.4 * u)
        path.lineTo(7.8 * u, 5 * u); path.lineTo(14 * u, 5 * u)
        path.lineTo(14 * u, 12.6 * u); path.lineTo(2 * u, 12.6 * u)
        path.closeSubpath()
        p.drawPath(path)
    elif kind == "images":
        rect(2.2, 3.2, 11.6, 9.6)
        p.setBrush(QBrush(c)); p.drawEllipse(int(5 * u), int(5.4 * u), int(1.8 * u), int(1.8 * u))
        p.setBrush(Qt.NoBrush)
        line(4, 11, 7.2, 7.8); line(7.2, 7.8, 9.4, 10); line(9.4, 10, 11.6, 7.8); line(11.6, 7.8, 12.6, 8.8)
    elif kind == "scanner":
        rect(2.2, 6.6, 11.6, 5.4)
        line(4.4, 6.6, 5.6, 3.4); line(5.6, 3.4, 11.6, 3.4); line(11.6, 3.4, 12.4, 6.6)
        line(4.6, 9.3, 11.4, 9.3)
    elif kind == "save":
        line(8, 2.6, 8, 9.4)
        line(5.4, 7, 8, 9.6); line(10.6, 7, 8, 9.6)
        path = QPainterPath()
        path.moveTo(2.6 * u, 9.6 * u); path.lineTo(2.6 * u, 12.8 * u)
        path.lineTo(13.4 * u, 12.8 * u); path.lineTo(13.4 * u, 9.6 * u)
        p.drawPath(path)
    elif kind == "save_as":
        line(6.6, 2.6, 6.6, 8.6)
        line(4.2, 6.4, 6.6, 8.8); line(9.0, 6.4, 6.6, 8.8)
        path = QPainterPath()
        path.moveTo(2.2 * u, 9.6 * u); path.lineTo(2.2 * u, 12.8 * u)
        path.lineTo(11.0 * u, 12.8 * u); path.lineTo(11.0 * u, 9.6 * u)
        p.drawPath(path)
        line(12.2, 2.4, 12.2, 6.4); line(10.2, 4.4, 14.2, 4.4)
    elif kind == "to_png":
        rect(3.4, 2.4, 9.2, 8.0)
        line(8, 12.0, 8, 13.4)   # хвостик вниз
        line(5.8, 11.8, 8, 13.8); line(10.2, 11.8, 8, 13.8)
    elif kind == "to_pdf":
        rect(3.4, 5.6, 9.2, 8.0)
        line(8, 2.2, 8, 4.4)
        line(5.8, 4.2, 8, 2.0); line(10.2, 4.2, 8, 2.0)
    elif kind == "compress":
        line(3, 3, 6.4, 6.4); line(6.4, 6.4, 6.4, 4.0); line(6.4, 6.4, 4.0, 6.4)
        line(13, 13, 9.6, 9.6); line(9.6, 9.6, 9.6, 12.0); line(9.6, 9.6, 12.0, 9.6)
        line(13, 3, 9.6, 6.4); line(9.6, 6.4, 12.0, 6.4); line(9.6, 6.4, 9.6, 4.0)
        line(3, 13, 6.4, 9.6); line(6.4, 9.6, 4.0, 9.6); line(6.4, 9.6, 6.4, 12.0)
    elif kind == "close":
        line(4.4, 4.4, 11.6, 11.6); line(11.6, 4.4, 4.4, 11.6)
    elif kind == "plus":
        line(8, 3.4, 8, 12.6); line(3.4, 8, 12.6, 8)
    elif kind == "star":
        path = QPainterPath()
        import math as _m
        pts = []
        for i in range(10):
            ang = -_m.pi / 2 + i * _m.pi / 5
            r = 6.4 * u if i % 2 == 0 else 2.8 * u
            pts.append((8 * u + r * _m.cos(ang), 8.4 * u + r * _m.sin(ang)))
        path.moveTo(*pts[0])
        for pt in pts[1:]:
            path.lineTo(*pt)
        path.closeSubpath()
        p.drawPath(path)
    elif kind == "trash":
        line(3.4, 4.8, 12.6, 4.8)
        line(6.4, 4.6, 6.8, 3.0); line(6.8, 3.0, 9.2, 3.0); line(9.2, 3.0, 9.6, 4.6)
        path = QPainterPath()
        path.moveTo(4.4 * u, 4.9 * u); path.lineTo(5.2 * u, 13.0 * u)
        path.lineTo(10.8 * u, 13.0 * u); path.lineTo(11.6 * u, 4.9 * u)
        p.drawPath(path)
        line(7.0, 7.0, 7.2, 11.0); line(9.0, 7.0, 8.8, 11.0)
    elif kind == "up":
        line(8, 3.6, 8, 12.4); line(4.6, 7.0, 8, 3.4); line(11.4, 7.0, 8, 3.4)
    elif kind == "down":
        line(8, 3.6, 8, 12.4); line(4.6, 9.0, 8, 12.6); line(11.4, 9.0, 8, 12.6)
    elif kind == "moon":
        path = QPainterPath()
        path.moveTo(10.2 * u, 2.8 * u)
        path.arcTo(2.8 * u, 2.8 * u, 10.4 * u, 10.4 * u, 65, 250)
        path.arcTo(5.4 * u, 2.4 * u, 7.6 * u, 7.6 * u, -45, -160)
        p.drawPath(path)
    elif kind == "sun":
        p.drawEllipse(int(5.4 * u), int(5.4 * u), int(5.2 * u), int(5.2 * u))
        for a in range(8):
            import math as _m
            ang = a * _m.pi / 4
            x1 = 8 + 4.2 * _m.cos(ang); y1 = 8 + 4.2 * _m.sin(ang)
            x2 = 8 + 5.8 * _m.cos(ang); y2 = 8 + 5.8 * _m.sin(ang)
            line(x1, y1, x2, y2)
    elif kind == "rot_left":
        path = QPainterPath()
        path.moveTo(3.4 * u, 7.6 * u)
        path.arcTo(3.4 * u, 3.0 * u, 9.2 * u, 9.2 * u, 180, -260)
        p.drawPath(path)
        p.setBrush(QBrush(c))
        p.drawPolygon([QPointF(3.4 * u, 7.9 * u), QPointF(1.4 * u, 4.9 * u),
                       QPointF(5.6 * u, 4.9 * u)])
        p.setBrush(Qt.NoBrush)
    elif kind == "rot_right":
        path = QPainterPath()
        path.moveTo(12.6 * u, 7.6 * u)
        path.arcTo(3.4 * u, 3.0 * u, 9.2 * u, 9.2 * u, 0, 260)
        p.drawPath(path)
        p.setBrush(QBrush(c))
        p.drawPolygon([QPointF(12.6 * u, 7.9 * u), QPointF(10.4 * u, 4.9 * u),
                       QPointF(14.6 * u, 4.9 * u)])
        p.setBrush(Qt.NoBrush)
    elif kind == "crop":
        line(5.2, 1.8, 5.2, 11.4); line(5.2, 11.4, 14.2, 11.4)
        line(1.8, 4.8, 10.8, 4.8); line(10.8, 4.8, 10.8, 14.2)
    elif kind == "frame":
        rect(2.2, 2.2, 11.6, 11.6)
        line(5.4, 2.2, 5.4, 13.8); line(10.6, 2.2, 10.6, 13.8)
        line(2.2, 5.4, 13.8, 5.4); line(2.2, 10.6, 13.8, 10.6)
    elif kind == "split":
        rect(2.0, 3.0, 5.2, 10.0)
        rect(8.8, 3.0, 5.2, 10.0)
        pen2 = QPen(c, size * 0.085, Qt.DashLine)
        pen2.setCapStyle(Qt.RoundCap)
        p.setPen(pen2)
        line(8.0, 1.6, 8.0, 14.4)
        p.setPen(pen)
    elif kind == "scanlook":
        rect(2.0, 6.0, 12.0, 6.0)
        line(2.0, 9.0, 14.0, 9.0)
        path = QPainterPath()
        path.moveTo(4.6 * u, 6.0 * u); path.lineTo(4.6 * u, 2.4 * u)
        path.lineTo(11.4 * u, 2.4 * u); path.lineTo(11.4 * u, 6.0 * u)
        p.drawPath(path)
        line(5.0, 12.0, 5.0, 14.0); line(11.0, 12.0, 11.0, 14.0)
    elif kind == "pen":
        path = QPainterPath()
        path.moveTo(3.0 * u, 13.0 * u); path.lineTo(3.8 * u, 9.8 * u)
        path.lineTo(10.6 * u, 3.0 * u); path.lineTo(13.0 * u, 5.4 * u)
        path.lineTo(6.2 * u, 12.2 * u); path.closeSubpath()
        p.drawPath(path)
        line(9.2, 4.4, 11.6, 6.8)
    elif kind == "help":
        p.drawEllipse(int(2.4 * u), int(2.4 * u), int(11.2 * u), int(11.2 * u))
        path = QPainterPath()
        path.moveTo(6.2 * u, 6.4 * u)
        path.cubicTo(6.2 * u, 4.2 * u, 9.9 * u, 4.2 * u, 9.9 * u, 6.5 * u)
        path.cubicTo(9.9 * u, 7.9 * u, 8.0 * u, 7.8 * u, 8.0 * u, 9.4 * u)
        p.drawPath(path)
        p.setBrush(c)
        p.drawEllipse(QPointF(8.0 * u, 11.4 * u), 0.5 * u, 0.5 * u)
        p.setBrush(Qt.NoBrush)
    elif kind == "ai":
        path = QPainterPath()
        path.moveTo(7.0 * u, 2.8 * u)
        path.quadTo(7.0 * u, 8.4 * u, 12.6 * u, 8.4 * u)
        path.quadTo(7.0 * u, 8.4 * u, 7.0 * u, 14.0 * u)
        path.quadTo(7.0 * u, 8.4 * u, 1.4 * u, 8.4 * u)
        path.quadTo(7.0 * u, 8.4 * u, 7.0 * u, 2.8 * u)
        p.drawPath(path)
        line(12.6, 2.2, 12.6, 5.0); line(11.2, 3.6, 14.0, 3.6)
    elif kind in ("zoom_in", "zoom_out"):
        p.drawEllipse(QPointF(7.0 * u, 7.0 * u), 4.4 * u, 4.4 * u)
        line(10.3, 10.3, 13.6, 13.6)
        line(5.0, 7.0, 9.0, 7.0)
        if kind == "zoom_in":
            line(7.0, 5.0, 7.0, 9.0)
    elif kind == "fit":
        for (x, y, dx, dy) in ((2.6, 2.6, 1, 1), (13.4, 2.6, -1, 1), (2.6, 13.4, 1, -1), (13.4, 13.4, -1, -1)):
            line(x, y, x + 3.4 * dx, y); line(x, y, x, y + 3.4 * dy)
        rect(5.6, 5.6, 4.8, 4.8, 0.8)
    elif kind == "ocr":
        for (x, y, dx, dy) in ((2.4, 2.4, 1, 1), (13.6, 2.4, -1, 1), (2.4, 13.6, 1, -1), (13.6, 13.6, -1, -1)):
            line(x, y, x + 2.6 * dx, y); line(x, y, x, y + 2.6 * dy)
        line(5.4, 5.4, 10.6, 5.4); line(8.0, 5.4, 8.0, 11.0)
    elif kind == "aim":
        p.drawEllipse(QPointF(8.0 * u, 8.0 * u), 4.6 * u, 4.6 * u)
        line(8.0, 1.6, 8.0, 4.6); line(8.0, 11.4, 8.0, 14.4)
        line(1.6, 8.0, 4.6, 8.0); line(11.4, 8.0, 14.4, 8.0)
        p.setBrush(c)
        p.drawEllipse(QPointF(8.0 * u, 8.0 * u), 0.9 * u, 0.9 * u)
        p.setBrush(Qt.NoBrush)
    elif kind == "more":
        p.setBrush(c)
        for cx in (4.0, 8.0, 12.0):
            p.drawEllipse(QPointF(cx * u, 8.0 * u), 0.9 * u, 0.9 * u)
        p.setBrush(Qt.NoBrush)
    elif kind == "chev_down":
        line(4.5, 6.5, 8.0, 10.0); line(8.0, 10.0, 11.5, 6.5)
    elif kind == "chev_right":
        line(6.5, 4.5, 10.0, 8.0); line(10.0, 8.0, 6.5, 11.5)
    elif kind == "pages":
        rect(2.4, 3.4, 5.6, 9.2)
        rect(8.4, 3.4, 5.2, 9.2)
        line(3.6, 6.2, 6.8, 6.2); line(3.6, 8.0, 6.8, 8.0)
        line(9.6, 6.2, 12.4, 6.2); line(9.6, 8.0, 12.4, 8.0)
    elif kind == "meta":
        path = QPainterPath()
        path.moveTo(8.6 * u, 2.6 * u); path.lineTo(13.4 * u, 7.4 * u)
        path.lineTo(7.8 * u, 13.0 * u); path.lineTo(3.0 * u, 8.2 * u)
        path.lineTo(3.0 * u, 2.6 * u); path.closeSubpath()
        p.drawPath(path)
        p.setBrush(QBrush(c))
        p.drawEllipse(int(4.9 * u), int(4.5 * u), int(1.7 * u), int(1.7 * u))
        p.setBrush(Qt.NoBrush)
    elif kind == "stamp":
        p.drawEllipse(int(4.6 * u), int(2.6 * u), int(6.8 * u), int(5.4 * u))
        line(8, 8.0, 8, 9.8)
        line(3.4, 12.8, 12.6, 12.8)
        path = QPainterPath()
        path.moveTo(4.6 * u, 12.6 * u); path.lineTo(5.4 * u, 10.2 * u)
        path.lineTo(10.6 * u, 10.2 * u); path.lineTo(11.4 * u, 12.6 * u)
        p.drawPath(path)
    p.end()
    return QIcon(pm)


# ---------------------------------------------------------------- сканер

WIA_FORMAT_BMP = "{B96B3CAB-0728-11D3-9D7B-0000F81EF32E}"
WIA_FORMAT_PNG = "{B96B3CAF-0728-11D3-9D7B-0000F81EF32E}"
WIA_FORMAT_JPEG = "{B96B3CAE-0728-11D3-9D7B-0000F81EF32E}"
WIA_FORMAT_TIFF = "{B96B3CB1-0728-11D3-9D7B-0000F81EF32E}"
WIA_FORMAT_PNG = "{B96B3CAF-0728-11D3-9D7B-0000F81EF32E}"
WIA_FORMAT_JPEG = "{B96B3CAE-0728-11D3-9D7B-0000F81EF32E}"
WIA_FORMAT_TIFF = "{B96B3CB1-0728-11D3-9D7B-0000F81EF32E}"
WIA_PROP = {
    "res_x": "6147", "res_y": "6148", "start_x": "6149", "start_y": "6150",
    "ext_x": "6151", "ext_y": "6152", "intent": "6146",
}
WIA_INTENT = {"Color": 1, "Gray": 2}  # 1 = цвет, 2 = оттенки серого


def _wia_devices():
    """Список сканеров через WIA COM (pywin32). Без PowerShell."""
    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()
    devices = []
    try:
        dm = win32com.client.Dispatch("WIA.DeviceManager")
        for i in range(1, dm.DeviceInfos.Count + 1):
            info = dm.DeviceInfos(i)
            if info.Type != 1:  # 1 = ScannerDeviceType
                continue
            name = "Сканер"
            try:
                for j in range(1, info.Properties.Count + 1):
                    p = info.Properties(j)
                    if p.Name in ("Name", "Description"):
                        name = str(p.Value)
                        if p.Name == "Name":
                            break
            except Exception:
                pass
            devices.append((info.DeviceID, name))
    finally:
        pass
    return devices


def _wia_set(item, prop_id, value):
    try:
        item.Properties(prop_id).Value = value
        return True
    except Exception:
        return False


def _wia_supported_formats(item):
    """Форматы, которые сканер реально умеет отдавать."""
    try:
        return {str(f).strip().upper() for f in item.Formats}
    except Exception:
        return set()


def _wia_pick_format(item):
    """Выбрать формат ЗАРАНЕЕ: слепой перебор заставляет сканер
    прогонять лист несколько раз."""
    supported = _wia_supported_formats(item)
    order = [WIA_FORMAT_BMP, WIA_FORMAT_PNG, WIA_FORMAT_JPEG, WIA_FORMAT_TIFF]
    if supported:
        for fmt in order:
            if fmt.upper() in supported:
                return fmt, True
        for fmt in supported:
            return fmt, True
    return WIA_FORMAT_BMP, False


def _wia_save_image(img, out_path, errors=None):
    """Сохранить результат скана. Возвращает реальный путь или None.

    Расширение берём у драйвера: если он отдал JPEG, а мы пишем в .bmp,
    сохранение падает — именно так скан «пропадал» после реального прогона.
    """
    if img is None:
        if errors is not None:
            errors.append("драйвер вернул пустой объект")
        return None

    base, _ = os.path.splitext(out_path)
    ext = ""
    try:
        ext = str(img.FileExtension or "").strip().lstrip(".").lower()
    except Exception:
        pass
    candidates = []
    if ext:
        candidates.append(f"{base}.{ext}")
    for e in ("bmp", "jpg", "png", "tif"):
        p = f"{base}.{e}"
        if p not in candidates:
            candidates.append(p)

    for path in candidates:
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            continue
        try:
            img.SaveFile(path)
        except Exception as e:
            if errors is not None:
                errors.append(f"сохранение {os.path.basename(path)}: {e}")
            continue
        if os.path.exists(path) and os.path.getsize(path) > 0:
            return path

    try:                                    # драйвер может отдать сырые байты
        data = img.FileData.BinaryData
        if data:
            path = candidates[0]
            with open(path, "wb") as f:
                f.write(bytes(data))
            if os.path.getsize(path) > 0:
                return path
    except Exception as e:
        if errors is not None:
            errors.append(f"сырые данные: {e}")
    return None


def _wia_items(dev):
    """Все источники устройства: у части МФУ рабочий не первый."""
    items = []
    try:
        for i in range(1, dev.Items.Count + 1):
            try:
                items.append(dev.Items(i))
            except Exception:
                pass
    except Exception:
        try:
            items.append(dev.Items(1))
        except Exception:
            pass
    return items


def _wia_setup(item, dpi, mode, level=2):
    """Настроить источник. level: 2 — всё, 1 — только режим и DPI, 0 — ничего.

    Некоторые драйверы (Canon G3030 и родня) молча возвращают пустой
    результат, если им выставить область сканирования, поэтому при повторе
    настройки урезаются.
    """
    if level <= 0:
        return
    _wia_set(item, WIA_PROP["intent"], WIA_INTENT.get(mode, 1))
    _wia_set(item, WIA_PROP["res_x"], dpi)
    _wia_set(item, WIA_PROP["res_y"], dpi)
    if level < 2:
        return
    try:
        cur_dpi = int(item.Properties(WIA_PROP["res_x"]).Value) or dpi
        inches_x = int(item.Properties(WIA_PROP["ext_x"]).Value) / cur_dpi
        inches_y = int(item.Properties(WIA_PROP["ext_y"]).Value) / cur_dpi
    except Exception:
        inches_x, inches_y = 8.27, 11.69          # A4 по умолчанию
    _wia_set(item, WIA_PROP["start_x"], 0)
    _wia_set(item, WIA_PROP["start_y"], 0)
    _wia_set(item, WIA_PROP["ext_x"], int(inches_x * dpi))
    _wia_set(item, WIA_PROP["ext_y"], int(inches_y * dpi))


def _wia_connect(device_id):
    """Свежее подключение к сканеру. Повторная попытка часто спасает:
    после неудачной передачи драйвер остаётся в подвисшем состоянии."""
    import win32com.client
    dm = win32com.client.Dispatch("WIA.DeviceManager")
    for i in range(1, dm.DeviceInfos.Count + 1):
        info = dm.DeviceInfos(i)
        if info.Type == 1 and (device_id is None or info.DeviceID == device_id):
            return info.Connect()
    return None


def _wia_try_transfer(item, dpi, mode, level, out_path, errors, tag):
    """Одна попытка передачи. Возвращает путь к файлу или None."""
    try:
        _wia_setup(item, dpi, mode, level)
    except Exception as e:
        errors.append(f"{tag}: настройки не приняты ({e})")
    fmt, known = _wia_pick_format(item)
    try:
        img = item.Transfer(fmt)
        saved = _wia_save_image(img, out_path, errors)
        if saved:
            return saved
    except Exception as e:
        errors.append(f"{tag}: {e}")
    if not known:
        try:
            img = item.Transfer()
            saved = _wia_save_image(img, out_path, errors)
            if saved:
                return saved
        except Exception as e:
            errors.append(f"{tag} (формат драйвера): {e}")
    return None


def _wia_windows_dialog(out_path, dpi, mode, errors):
    """Штатное окно сканера Windows. Пробуем несколько способов вызова."""
    import win32com.client
    cd = win32com.client.Dispatch("WIA.CommonDialog")
    intent = 1 if mode == "Color" else 2
    attempts = [
        ("окно Windows", lambda: cd.ShowAcquireImage(1, intent, 131072,
                                                     WIA_FORMAT_BMP, False, True, False)),
        ("окно Windows (JPEG)", lambda: cd.ShowAcquireImage(1, intent, 131072,
                                                            WIA_FORMAT_JPEG, False, True, False)),
        ("окно Windows (по умолчанию)", lambda: cd.ShowAcquireImage()),
    ]
    for tag, call in attempts:
        try:
            img = call()
        except Exception as e:
            errors.append(f"{tag}: {e}")
            continue
        saved = _wia_save_image(img, out_path, errors)
        if saved:
            return saved
        errors.append(f"{tag}: изображение не получено")
    return None


def _wia_scan(device_id, out_path, dpi, mode, use_dialog=False):
    """Скан через WIA COM. Вызывать ТОЛЬКО из главного потока.

    Драйверы Canon нередко отдают пустой результат с первого раза, поэтому
    попытки идут на свежем подключении и с постепенно урезанными настройками.
    """
    try:
        import pythoncom
        pythoncom.CoInitialize()
    except Exception:
        pythoncom = None

    errors = []

    if use_dialog:
        saved = _wia_windows_dialog(out_path, dpi, mode, errors)
        if saved:
            return saved
        raise RuntimeError("; ".join(errors[:3]) or
                           "окно сканера закрыли или оно не вернуло изображение")

    for attempt, level in enumerate((2, 1, 0), start=1):
        dev = _wia_connect(device_id)
        if dev is None:
            raise RuntimeError("Сканер не найден в системе")
        items = _wia_items(dev)
        if not items:
            errors.append(f"попытка {attempt}: устройство не отдало источник")
        for n, item in enumerate(items, 1):
            tag = f"попытка {attempt}, источник {n}"
            saved = _wia_try_transfer(item, dpi, mode, level, out_path, errors, tag)
            if saved:
                return saved
        try:
            if pythoncom is not None:
                pythoncom.CoFreeUnusedLibraries()
        except Exception:
            pass
        time.sleep(1.2)

    saved = _wia_windows_dialog(out_path, dpi, mode, errors)
    if saved:
        return saved
    raise RuntimeError("; ".join(errors[:5]))


def _sane_devices():
    """Список сканеров через SANE (scanimage -L)."""
    if not shutil.which("scanimage"):
        return []
    try:
        out = subprocess.run(["scanimage", "-L"], capture_output=True,
                             timeout=25).stdout.decode(errors="ignore")
    except Exception:
        return []
    devices = []
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("device") and "`" in line and "'" in line:
            dev_id = line.split("`", 1)[1].split("'", 1)[0]
            name = line.split(" is a ", 1)[1] if " is a " in line else dev_id
            devices.append((dev_id, name))
    return devices


def _sane_scan(device_id, out_path, dpi, mode):
    cmd = ["scanimage", "--format=tiff", f"--resolution={dpi}",
           f"--mode={mode}", "-o", out_path]
    if device_id:
        cmd[1:1] = ["-d", device_id]
    proc = subprocess.run(cmd, capture_output=True)
    if not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
        err = (proc.stderr or b"").decode(errors="ignore")[:400]
        raise RuntimeError(err or "Сканер не вернул изображение")
    return out_path


def scanner_backend():
    """'wia' | 'sane' | None — какой бэкенд доступен на этой машине."""
    if sys.platform == "win32":
        try:
            import win32com.client  # noqa: F401
            return "wia"
        except ImportError:
            return None
    return "sane" if shutil.which("scanimage") else None


def list_scanners():
    b = scanner_backend()
    try:
        if b == "wia":
            return _wia_devices()
        if b == "sane":
            return _sane_devices()
    except Exception:
        return []
    return []


class ScanWorker(QThread):
    """Сканирование в отдельном потоке — окно не подвисает."""
    finished_ok = Signal(str)
    failed = Signal(str)

    def __init__(self, device_id, dpi, mode, parent=None, use_dialog=False):
        super().__init__(parent)
        self.device_id = device_id
        self.dpi = dpi
        self.mode = mode
        self.use_dialog = use_dialog

    def run(self):
        b = scanner_backend()
        ext = ".bmp" if b == "wia" else ".tiff"
        out_path = os.path.join(tempfile.gettempdir(),
                                f"stampstudio_scan_{int(time.time() * 1000)}{ext}")
        try:
            if b == "wia":
                out_path = _wia_scan(self.device_id, out_path, self.dpi, self.mode,
                                     use_dialog=self.use_dialog)
            elif b == "sane":
                _sane_scan(self.device_id, out_path, self.dpi, self.mode)
            else:
                raise RuntimeError("Бэкенд сканера не найден")
            self.finished_ok.emit(out_path)
        except Exception as e:
            self.failed.emit(str(e))


class ScanDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Сканирование")
        lay = QVBoxLayout(self)
        lay.setSpacing(10)

        row0 = QHBoxLayout()
        row0.addWidget(QLabel("Сканер:"))
        self.combo_dev = QComboBox()
        self.combo_dev.setMinimumWidth(240)
        row0.addWidget(self.combo_dev, 1)
        btn_refresh = QPushButton("Обновить")
        btn_refresh.clicked.connect(self.reload_devices)
        row0.addWidget(btn_refresh)
        lay.addLayout(row0)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Разрешение:"))
        self.combo_dpi = QComboBox()
        for d in (150, 200, 300, 600):
            self.combo_dpi.addItem(f"{d} DPI", d)
        self.combo_dpi.setCurrentIndex(2)  # 300
        row1.addWidget(self.combo_dpi, 1)
        lay.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Режим:"))
        self.combo_mode = QComboBox()
        self.combo_mode.addItem("Цветной", "Color")
        self.combo_mode.addItem("Оттенки серого", "Gray")
        row2.addWidget(self.combo_mode, 1)
        lay.addLayout(row2)

        self.chk_dialog = QCheckBox("сканировать через штатное окно Windows")
        self.chk_dialog.setToolTip(
            "Самый надёжный способ, если сканер капризничает (Canon и др.).\n"
            "Откроется окно драйвера — там нажмите «Сканировать».")
        self.chk_dialog.setChecked(bool(settings_load().get("scan_via_dialog", False)))
        lay.addWidget(self.chk_dialog)

        self.note = QLabel("")
        self.note.setObjectName("hint")
        self.note.setWordWrap(True)
        lay.addWidget(self.note)

        self.bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.bb.button(QDialogButtonBox.Ok).setText("Сканировать")
        self.bb.accepted.connect(self.accept)
        self.bb.rejected.connect(self.reject)
        lay.addWidget(self.bb)

        self.reload_devices()

    def reload_devices(self):
        self.combo_dev.clear()
        devices = list_scanners()
        for dev_id, name in devices:
            self.combo_dev.addItem(name, dev_id)
        ok = bool(devices)
        if ok:
            self.note.setText(
                "Сканирование идёт напрямую. Если сканер капризничает и часто "
                "выдаёт ошибку — поставьте галочку выше, это надёжнее.")
        elif scanner_backend() is None:
            if sys.platform == "win32":
                self.note.setText("Не установлен модуль pywin32. Выполните один раз "
                                  "в командной строке:\n\n    pip install pywin32")
            else:
                self.note.setText("Не установлен SANE. Выполните один раз в Терминале:"
                                  "\n\n    brew install sane-backends\n\n"
                                  "Либо отсканируйте через «Захват изображений» и "
                                  "нажмите «Открыть сканы».")
            self.combo_dev.addItem("— сканеры не найдены —", None)
        else:
            self.note.setText("Сканеры не найдены. Проверьте, что устройство включено "
                              "и подключено, затем нажмите «Обновить».")
            self.combo_dev.addItem("— сканеры не найдены —", None)
        self.bb.button(QDialogButtonBox.Ok).setEnabled(ok or self.chk_dialog.isChecked())
        self.chk_dialog.stateChanged.connect(
            lambda _=0: self.bb.button(QDialogButtonBox.Ok).setEnabled(
                bool(list_scanners()) or self.chk_dialog.isChecked()))



class QuickSaveDialog(QDialog):
    """Ctrl+S: записать в открытый файл. Спрашивает только «Сжать?» — по умолчанию да."""

    def __init__(self, parent=None, compress_profile=None):
        super().__init__(parent)
        self.setWindowTitle("Сохранить изменения")
        self.compress_profile = compress_profile
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        lbl = QLabel("Изменения запишутся в открытый файл.")
        lbl.setWordWrap(True)
        lay.addWidget(lbl)

        row = QHBoxLayout()
        row.addWidget(QLabel("Сжать?"))
        self.combo_compress = QComboBox()
        self.combo_compress.setMinimumHeight(30)
        self.combo_compress.addItem("Среднее — картинки в JPEG, текст остаётся", "medium")
        self.combo_compress.addItem("Сильное — весь документ в JPEG, минимальный размер", "strong")
        self.combo_compress.addItem("Минимальное — для отправки: 110 dpi, читаемо, но качество низкое", "tiny")
        self.combo_compress.addItem("Лёгкое — без потерь, экономия небольшая", "light")
        self.combo_compress.addItem("Не сжимать", "none")
        row.addWidget(self.combo_compress, 1)
        lay.addLayout(row)

        st = settings_load()
        mode = (compress_profile or {}).get("mode") or st.get("quick_save_compress", "medium")
        if (compress_profile or {}).get("preset") == "tiny":
            mode = "tiny"
        if mode == "none":
            mode = st.get("quick_save_compress", "medium")
        i = self.combo_compress.findData(mode)
        self.combo_compress.setCurrentIndex(i if i >= 0 else 0)

        self.chk_flat = QCheckBox("свести документ в изображение (печать вплавляется намертво)")
        self.chk_flat.setChecked(bool(st.get("flatten_on_save", True)))
        lay.addWidget(self.chk_flat)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Сохранить")
        bb.button(QDialogButtonBox.Ok).setDefault(True)
        bb.button(QDialogButtonBox.Cancel).setText("Отмена")
        for b in (bb.button(QDialogButtonBox.Ok), bb.button(QDialogButtonBox.Cancel)):
            b.setMinimumHeight(32)
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.setMinimumWidth(520)

    def _ok(self):
        try:
            st = settings_load()
            st["quick_save_compress"] = self.combo_compress.currentData()
            st["flatten_on_save"] = self.chk_flat.isChecked()
            settings_save(st)
        except Exception:
            pass
        self.accept()

    def compress_choice(self):
        mode = self.combo_compress.currentData()
        if mode == "none":
            return {"mode": "none"}
        if self.compress_profile and self.compress_profile.get("mode") == mode:
            return dict(self.compress_profile)
        if mode == "medium":
            return {"mode": "medium", "quality": 70}
        if mode == "strong":
            return {"mode": "strong", "dpi": 150, "quality": 70}
        if mode == "tiny":
            return {"mode": "strong", "dpi": 110, "quality": 50, "preset": "tiny"}
        return {"mode": "light"}


class SaveDialog(QDialog):
    """Одно окно сохранения: имя файла, шаблоны, папка, очистка метаданных."""

    DEFAULT_TEMPLATES = [
        "{исходник}_с_печатью",
        "{исходник}_подписан_{дата}",
        "{исходник}_{дата}",
        "скан_{дата}_{время}",
        "{исходник}",
    ]

    def __init__(self, src_name: str, parent=None, default_dir=None,
                 compress_profile=None):
        super().__init__(parent)
        self.setWindowTitle("Сохранение PDF")
        self.compress_profile = compress_profile
        self.setMinimumWidth(560)
        self.src_name = src_name
        s = settings_load()

        lay = QVBoxLayout(self)
        lay.setSpacing(10)

        # --- имя файла
        lay.addWidget(QLabel("<b>Имя файла</b>"))
        name_row = QHBoxLayout()
        name_row.setSpacing(6)
        self.edit_name = QLineEdit()
        self.edit_name.setPlaceholderText("введите имя файла")
        self.edit_name.setMinimumHeight(32)
        name_row.addWidget(self.edit_name, 1)
        name_row.addWidget(QLabel(".pdf"))
        lay.addLayout(name_row)
        self.btn_ai = QPushButton("")
        self.btn_ai.setObjectName("aichip")
        self.btn_ai.setCursor(Qt.PointingHandCursor)
        self.btn_ai.setVisible(False)
        self.btn_ai.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.btn_ai.clicked.connect(self._use_ai_name)
        lay.addWidget(self.btn_ai)
        self._ai_name = None

        # --- шаблоны
        lay.addWidget(QLabel("<b>Готовые шаблоны</b> — нажмите, чтобы подставить имя"))
        tpl_row = QHBoxLayout()
        tpl_row.setSpacing(6)
        self.combo_tpl = QComboBox()
        self.combo_tpl.setMinimumHeight(30)
        self.combo_tpl.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.combo_tpl.setMinimumContentsLength(18)
        user_tpls = s.get("name_templates", [])
        for tpl in user_tpls + [t for t in self.DEFAULT_TEMPLATES if t not in user_tpls]:
            self.combo_tpl.addItem(self.resolve(tpl), tpl)
        self.combo_tpl.currentIndexChanged.connect(self.apply_template)
        tpl_row.addWidget(self.combo_tpl, 1)
        b_tpl = QPushButton("Подставить")
        b_tpl.clicked.connect(self.apply_template)
        tpl_row.addWidget(b_tpl)
        b_new = QPushButton("Свой шаблон…")
        b_new.setToolTip("Создать собственный шаблон имени")
        b_new.clicked.connect(self.new_template)
        tpl_row.addWidget(b_new)
        lay.addLayout(tpl_row)

        hint = QLabel("В шаблоне можно использовать: {исходник} — имя открытого файла, "
                      "{дата}, {время}")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        lay.addWidget(hint)

        # --- папка
        lay.addWidget(QLabel("<b>Куда сохранить</b>"))
        dir_row = QHBoxLayout()
        dir_row.setSpacing(6)
        self.folder = default_dir or s.get("last_save_dir") or os.path.join(
            os.path.expanduser("~"), "Desktop")
        if not os.path.isdir(self.folder):
            self.folder = os.path.expanduser("~")
        self.lbl_dir = QLabel(self.folder)
        self.lbl_dir.setWordWrap(True)
        dir_row.addWidget(self.lbl_dir, 1)
        b_dir = QPushButton("Обзор…")
        b_dir.clicked.connect(self.pick_folder)
        dir_row.addWidget(b_dir)
        lay.addLayout(dir_row)

        # --- метаданные
        comp_row = QHBoxLayout()
        comp_row.setSpacing(6)
        comp_row.addWidget(QLabel("<b>Сжать?</b>"))
        self.combo_compress = QComboBox()
        self.combo_compress.setMinimumHeight(30)
        self.combo_compress.addItem("Не сжимать", "none")
        self.combo_compress.addItem("Среднее — картинки в JPEG, текст остаётся (рекомендуется)", "medium")
        self.combo_compress.addItem("Сильное — весь документ в JPEG, минимальный размер", "strong")
        self.combo_compress.addItem("Минимальное — для отправки: 110 dpi, читаемо, но качество низкое", "tiny")
        self.combo_compress.addItem("Лёгкое — без потерь, экономия небольшая", "light")
        comp_row.addWidget(self.combo_compress, 1)
        lay.addLayout(comp_row)

        self.lbl_compress = QLabel("")
        self.lbl_compress.setObjectName("hint")
        self.lbl_compress.setWordWrap(True)
        lay.addWidget(self.lbl_compress)

        self.chk_flat = QCheckBox("свести документ в изображение (печать вплавляется намертво)")
        self.chk_flat.setToolTip(
            "Каждая страница превращается в картинку внутри PDF.\n"
            "Печать становится неотделимой частью листа, текст перестаёт выделяться.\n"
            "Заменяет ручную конвертацию PDF → PNG → PDF.")
        s_flat = settings_load()
        self.chk_flat.setChecked(bool(s_flat.get("flatten_on_save", True)))
        lay.addWidget(self.chk_flat)

        self.chk_meta = QCheckBox("очистить метаданные: автор, программа, даты создания")
        self.chk_meta.setChecked(bool(s.get("clean_metadata", True)))
        lay.addWidget(self.chk_meta)

        self.warn = QLabel("")
        self.warn.setObjectName("hint")
        self.warn.setWordWrap(True)
        lay.addWidget(self.warn)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.btn_ok = bb.button(QDialogButtonBox.Ok)
        self.btn_ok.setText("Сохранить")
        self.btn_ok.setDefault(True)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

        self.edit_name.textChanged.connect(self.check_state)
        # что предложить по умолчанию
        if self.compress_profile:
            mode = self.compress_profile.get("mode", "medium")
            if self.compress_profile.get("preset") == "tiny":
                mode = "tiny"
            names = {"light": "лёгкое", "medium": "среднее", "strong": "сильное",
                     "tiny": "минимальное"}
            self.lbl_compress.setText(
                f"Документ уже сжимался ({names.get(mode, mode)}) — предложено то же "
                "качество, чтобы размер не вырос после правки страниц.")
        else:
            mode = s.get("save_compress", "none")
            self.lbl_compress.setVisible(False)
        i = self.combo_compress.findData(mode)
        self.combo_compress.setCurrentIndex(i if i >= 0 else 0)

        last = s.get("last_template") or self.DEFAULT_TEMPLATES[0]
        idx = self.combo_tpl.findData(last)
        if idx >= 0:
            self.combo_tpl.setCurrentIndex(idx)
        self.edit_name.setText(self.resolve(last))
        self._initial_name = self.edit_name.text()
        self.check_state()

    # ---- имя от ИИ (автоматический режим) ----
    def set_ai_wait(self):
        self.btn_ai.setText("✨  ИИ читает документ и подбирает имя…")
        self.btn_ai.setEnabled(False)
        self.btn_ai.setVisible(True)

    def set_ai_name(self, name):
        self._ai_name = name
        shown = name if len(name) <= 60 else name[:59] + "…"
        self.btn_ai.setText(f"✨  ИИ предлагает: {shown}")
        self.btn_ai.setToolTip(f"Нажмите, чтобы подставить имя:\n{name}")
        self.btn_ai.setEnabled(True)
        self.btn_ai.setVisible(True)
        if self.edit_name.text() == self._initial_name:      # имя ещё не трогали руками
            self.edit_name.setText(name)

    def set_ai_fail(self, msg):
        self.btn_ai.setText("ИИ не подобрал имя — введите вручную")
        self.btn_ai.setToolTip(msg)
        self.btn_ai.setEnabled(False)
        self.btn_ai.setVisible(True)

    def _use_ai_name(self):
        if self._ai_name:
            self.edit_name.setText(self._ai_name)

    # ---- шаблоны ----
    def resolve(self, tpl: str) -> str:
        name = (tpl.replace("{исходник}", self.src_name)
                   .replace("{дата}", time.strftime("%Y-%m-%d"))
                   .replace("{время}", time.strftime("%H-%M")))
        for ch in '\\/:*?"<>|':
            name = name.replace(ch, "_")
        return name.strip()

    def apply_template(self):
        tpl = self.combo_tpl.currentData()
        if tpl:
            self.edit_name.setText(self.resolve(tpl))

    def new_template(self):
        tpl, ok = QInputDialog.getText(
            self, "Свой шаблон имени",
            "Шаблон (можно использовать {исходник}, {дата}, {время}):",
            text="{исходник}_с_печатью_{дата}")
        if not ok or not tpl.strip():
            return
        tpl = tpl.strip()
        if self.combo_tpl.findData(tpl) < 0:
            self.combo_tpl.insertItem(0, self.resolve(tpl), tpl)
        self.combo_tpl.setCurrentIndex(self.combo_tpl.findData(tpl))
        self.apply_template()

    # ---- папка и состояние ----
    def pick_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Папка для сохранения", self.folder)
        if path:
            self.folder = path
            self.lbl_dir.setText(path)
            self.check_state()

    def full_path(self) -> str:
        name = self.edit_name.text().strip() or "документ"
        for ch in '\\/:*?"<>|':
            name = name.replace(ch, "_")
        if not name.lower().endswith(".pdf"):
            name += ".pdf"
        return os.path.join(self.folder, name)

    def check_state(self):
        ok = bool(self.edit_name.text().strip())
        self.btn_ok.setEnabled(ok)
        if ok and os.path.exists(self.full_path()):
            self.warn.setText("⚠ Файл с таким именем уже есть — он будет перезаписан.")
        else:
            self.warn.setText("")

    def compress_choice(self):
        mode = self.combo_compress.currentData()
        if mode == "none":
            return {"mode": "none"}
        if self.compress_profile and self.compress_profile.get("mode") == mode:
            return dict(self.compress_profile)
        if mode == "medium":
            return {"mode": "medium", "quality": 70}
        if mode == "strong":
            return {"mode": "strong", "dpi": 150, "quality": 70}
        if mode == "tiny":
            return {"mode": "strong", "dpi": 110, "quality": 50, "preset": "tiny"}
        return {"mode": "light"}

    def remember(self):
        s = settings_load()
        tpl = self.combo_tpl.currentData()
        tpls = s.get("name_templates", [])
        if tpl and tpl not in tpls and tpl not in self.DEFAULT_TEMPLATES:
            tpls.insert(0, tpl)
        s["name_templates"] = tpls[:8]
        s["last_template"] = tpl
        s["clean_metadata"] = self.chk_meta.isChecked()
        s["flatten_on_save"] = self.chk_flat.isChecked()
        s["save_compress"] = self.combo_compress.currentData()
        s["last_save_dir"] = self.folder
        settings_save(s)


class PngExportDialog(QDialog):
    """Имя файлов, нумерация, качество и папка для экспорта в PNG."""

    DEFAULT_TEMPLATES = [
        "{исходник}_стр{n}",
        "{исходник}_page{n}",
        "{исходник}_{дата}_стр{n}",
        "скан_{дата}_стр{n}",
        "{исходник}",
    ]

    def __init__(self, src_name: str, pages: int, default_dpi: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Экспорт в PNG")
        self.setMinimumWidth(560)
        self.src_name = src_name
        self.pages = max(1, pages)
        s = settings_load()

        lay = QVBoxLayout(self)
        lay.setSpacing(10)

        lay.addWidget(QLabel("<b>Имя файлов</b>"))
        name_row = QHBoxLayout()
        name_row.setSpacing(6)
        self.edit_name = QLineEdit()
        self.edit_name.setMinimumHeight(32)
        self.edit_name.setPlaceholderText("имя без расширения")
        name_row.addWidget(self.edit_name, 1)
        name_row.addWidget(QLabel(".png"))
        lay.addLayout(name_row)

        lay.addWidget(QLabel("<b>Готовые шаблоны</b> — {n} подставит номер страницы"))
        tpl_row = QHBoxLayout()
        tpl_row.setSpacing(6)
        self.combo_tpl = QComboBox()
        self.combo_tpl.setMinimumHeight(30)
        user_tpls = s.get("png_templates", [])
        for tpl in user_tpls + [t for t in self.DEFAULT_TEMPLATES if t not in user_tpls]:
            self.combo_tpl.addItem(self.resolve(tpl, 1), tpl)
        self.combo_tpl.currentIndexChanged.connect(self.apply_template)
        tpl_row.addWidget(self.combo_tpl, 1)
        b_new = QPushButton("Свой шаблон…")
        b_new.clicked.connect(self.new_template)
        tpl_row.addWidget(b_new)
        lay.addLayout(tpl_row)

        opts = QHBoxLayout()
        opts.setSpacing(10)
        opts.addWidget(QLabel("Нумерация:"))
        self.combo_num = QComboBox()
        self.combo_num.addItem("1, 2, 3…", 1)
        self.combo_num.addItem("01, 02, 03…", 2)
        self.combo_num.addItem("001, 002, 003…", 3)
        self.combo_num.setCurrentIndex(int(s.get("png_digits", 1)) - 1)
        self.combo_num.currentIndexChanged.connect(self.update_preview)
        opts.addWidget(self.combo_num)
        opts.addSpacing(12)
        opts.addWidget(QLabel("Качество:"))
        self.spin_dpi = QSpinBox()
        self.spin_dpi.setRange(72, 600)
        self.spin_dpi.setSingleStep(50)
        self.spin_dpi.setValue(default_dpi)
        self.spin_dpi.setSuffix(" DPI")
        self.spin_dpi.setMinimumWidth(96)
        opts.addWidget(self.spin_dpi)
        opts.addStretch()
        lay.addLayout(opts)

        lay.addWidget(QLabel("<b>Куда сохранить</b>"))
        dir_row = QHBoxLayout()
        dir_row.setSpacing(6)
        self.folder = s.get("last_png_dir") or s.get("last_save_dir") or \
            os.path.join(os.path.expanduser("~"), "Desktop")
        if not os.path.isdir(self.folder):
            self.folder = os.path.expanduser("~")
        self.lbl_dir = QLabel(self.folder)
        self.lbl_dir.setWordWrap(True)
        dir_row.addWidget(self.lbl_dir, 1)
        b_dir = QPushButton("Обзор…")
        b_dir.clicked.connect(self.pick_folder)
        dir_row.addWidget(b_dir)
        lay.addLayout(dir_row)

        self.preview = QLabel("")
        self.preview.setObjectName("hint")
        self.preview.setWordWrap(True)
        lay.addWidget(self.preview)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.btn_ok = bb.button(QDialogButtonBox.Ok)
        self.btn_ok.setText("Экспортировать")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

        self.edit_name.textChanged.connect(self.update_preview)
        last = s.get("last_png_template") or self.DEFAULT_TEMPLATES[0]
        idx = self.combo_tpl.findData(last)
        if idx >= 0:
            self.combo_tpl.setCurrentIndex(idx)
        self.edit_name.setText(self.resolve(last, None))
        self.update_preview()

    # ---- имена ----
    def resolve(self, tpl: str, page=None) -> str:
        name = (tpl.replace("{исходник}", self.src_name)
                   .replace("{дата}", time.strftime("%Y-%m-%d"))
                   .replace("{время}", time.strftime("%H-%M")))
        if page is None:
            return self._clean(name)
        return self._clean(name.replace("{n}", str(page).zfill(self.digits())))

    @staticmethod
    def _clean(name: str) -> str:
        for ch in '\\/:*?"<>|':
            name = name.replace(ch, "_")
        return name.strip()

    def digits(self) -> int:
        combo = getattr(self, "combo_num", None)
        return (combo.currentData() if combo is not None else 1) or 1

    def file_name(self, page: int) -> str:
        base = self._clean(self.edit_name.text().strip()) or "страница"
        if base.lower().endswith(".png"):
            base = base[:-4]
        num = str(page).zfill(self.digits())
        name = base.replace("{n}", num) if "{n}" in base else f"{base}_{num}"
        return name + ".png"

    def apply_template(self):
        tpl = self.combo_tpl.currentData()
        if tpl:
            self.edit_name.setText(self.resolve(tpl, None))

    def new_template(self):
        tpl, ok = QInputDialog.getText(
            self, "Свой шаблон имени",
            "Шаблон (доступно {исходник}, {дата}, {время}, {n} — номер страницы):",
            text="{исходник}_скан_{n}")
        if not ok or not tpl.strip():
            return
        tpl = tpl.strip()
        if self.combo_tpl.findData(tpl) < 0:
            self.combo_tpl.insertItem(0, self.resolve(tpl, 1), tpl)
        self.combo_tpl.setCurrentIndex(self.combo_tpl.findData(tpl))
        self.apply_template()

    def pick_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Папка для PNG", self.folder)
        if path:
            self.folder = path
            self.lbl_dir.setText(path)
            self.update_preview()

    def update_preview(self):
        self.btn_ok.setEnabled(bool(self.edit_name.text().strip()))
        first = self.file_name(1)
        if self.pages > 1:
            n = self.pages
            word = "файла" if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14) else "файлов"
            self.preview.setText(f"Получится {n} {word}: {first}, {self.file_name(2)} "
                                 f"… {self.file_name(self.pages)}")
        else:
            self.preview.setText(f"Получится файл: {first}")

    def remember(self):
        s = settings_load()
        tpl = self.combo_tpl.currentData()
        tpls = s.get("png_templates", [])
        if tpl and tpl not in tpls and tpl not in self.DEFAULT_TEMPLATES:
            tpls.insert(0, tpl)
        s["png_templates"] = tpls[:8]
        s["last_png_template"] = tpl
        s["png_digits"] = self.digits()
        s["last_png_dir"] = self.folder
        settings_save(s)


class PngExportDialog(QDialog):
    """Имя файлов, качество и папка для экспорта страниц в PNG."""

    DEFAULT_TEMPLATES = [
        "{исходник}_стр{номер}",
        "{исходник}_{дата}_стр{номер}",
        "скан_{дата}_стр{номер}",
        "страница_{номер}",
    ]

    def __init__(self, src_name: str, page_count: int, parent=None, default_dir=None):
        super().__init__(parent)
        self.setWindowTitle("Экспорт страниц в PNG")
        self.setMinimumWidth(560)
        self.src_name = src_name
        self.page_count = max(1, page_count)
        s = settings_load()

        lay = QVBoxLayout(self)
        lay.setSpacing(10)

        lay.addWidget(QLabel(f"<b>Имя файлов</b> — будет создано {self.page_count} шт."))
        self.edit_name = QLineEdit()
        self.edit_name.setMinimumHeight(32)
        self.edit_name.textChanged.connect(self.check_state)
        lay.addWidget(self.edit_name)

        lay.addWidget(QLabel("<b>Готовые шаблоны</b>"))
        tpl_row = QHBoxLayout()
        tpl_row.setSpacing(6)
        self.combo_tpl = QComboBox()
        self.combo_tpl.setMinimumHeight(30)
        user_tpls = s.get("png_templates", [])
        for tpl in user_tpls + [t for t in self.DEFAULT_TEMPLATES if t not in user_tpls]:
            self.combo_tpl.addItem(self.resolve(tpl, 1), tpl)
        self.combo_tpl.currentIndexChanged.connect(self.apply_template)
        tpl_row.addWidget(self.combo_tpl, 1)
        b_tpl = QPushButton("Подставить")
        b_tpl.clicked.connect(self.apply_template)
        tpl_row.addWidget(b_tpl)
        b_new = QPushButton("Свой шаблон…")
        b_new.clicked.connect(self.new_template)
        tpl_row.addWidget(b_new)
        lay.addLayout(tpl_row)

        hint = QLabel("Подстановки: {номер} — номер страницы, {исходник} — имя документа, "
                      "{дата}, {время}")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        lay.addWidget(hint)

        # качество
        dpi_row = QHBoxLayout()
        dpi_row.setSpacing(6)
        dpi_row.addWidget(QLabel("Качество:"))
        self.combo_dpi = QComboBox()
        for d, txt in [(150, "150 DPI — для экрана и почты"),
                       (300, "300 DPI — обычная печать"),
                       (600, "600 DPI — максимум качества")]:
            self.combo_dpi.addItem(txt, d)
        idx = self.combo_dpi.findData(int(s.get("png_dpi", 300)))
        self.combo_dpi.setCurrentIndex(idx if idx >= 0 else 1)
        dpi_row.addWidget(self.combo_dpi, 1)
        lay.addLayout(dpi_row)

        # папка
        lay.addWidget(QLabel("<b>Куда сохранить</b>"))
        dir_row = QHBoxLayout()
        dir_row.setSpacing(6)
        self.folder = (default_dir or s.get("last_png_dir")
                       or s.get("last_save_dir") or os.path.expanduser("~"))
        if not os.path.isdir(self.folder):
            self.folder = os.path.expanduser("~")
        self.lbl_dir = QLabel(self.folder)
        self.lbl_dir.setWordWrap(True)
        dir_row.addWidget(self.lbl_dir, 1)
        b_dir = QPushButton("Обзор…")
        b_dir.clicked.connect(self.pick_folder)
        dir_row.addWidget(b_dir)
        lay.addLayout(dir_row)

        self.preview = QLabel("")
        self.preview.setObjectName("hint")
        self.preview.setWordWrap(True)
        lay.addWidget(self.preview)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.btn_ok = bb.button(QDialogButtonBox.Ok)
        self.btn_ok.setText("Экспортировать")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

        last = s.get("last_png_template") or self.DEFAULT_TEMPLATES[0]
        i = self.combo_tpl.findData(last)
        if i >= 0:
            self.combo_tpl.setCurrentIndex(i)
        self.edit_name.setText(self.resolve(last, 1, keep_number=True))
        self.check_state()

    # ---- имена ----
    def _num(self, n: int) -> str:
        width = len(str(self.page_count))
        return str(n).zfill(width)

    def resolve(self, tpl: str, page: int, keep_number=False) -> str:
        name = (tpl.replace("{исходник}", self.src_name)
                   .replace("{дата}", time.strftime("%Y-%m-%d"))
                   .replace("{время}", time.strftime("%H-%M")))
        name = name.replace("{номер}", "{номер}" if keep_number else self._num(page))
        for ch in '\\/:*?"<>|':
            name = name.replace(ch, "_")
        return name.strip()

    def file_name(self, page: int) -> str:
        tpl = self.edit_name.text().strip() or "страница_{номер}"
        if "{номер}" not in tpl and self.page_count > 1:
            tpl += "_{номер}"
        name = tpl.replace("{номер}", self._num(page))
        for ch in '\\/:*?"<>|':
            name = name.replace(ch, "_")
        if name.lower().endswith(".png"):
            name = name[:-4]
        return name + ".png"

    def apply_template(self):
        tpl = self.combo_tpl.currentData()
        if tpl:
            self.edit_name.setText(self.resolve(tpl, 1, keep_number=True))

    def new_template(self):
        tpl, ok = QInputDialog.getText(
            self, "Свой шаблон имени",
            "Шаблон (можно использовать {номер}, {исходник}, {дата}, {время}):",
            text="{исходник}_стр{номер}")
        if not ok or not tpl.strip():
            return
        tpl = tpl.strip()
        if self.combo_tpl.findData(tpl) < 0:
            self.combo_tpl.insertItem(0, self.resolve(tpl, 1), tpl)
        self.combo_tpl.setCurrentIndex(self.combo_tpl.findData(tpl))
        self.apply_template()

    def pick_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Папка для PNG", self.folder)
        if path:
            self.folder = path
            self.lbl_dir.setText(path)
            self.check_state()

    def dpi(self) -> int:
        return self.combo_dpi.currentData()

    def check_state(self):
        ok = bool(self.edit_name.text().strip())
        self.btn_ok.setEnabled(ok)
        if not ok:
            self.preview.setText("")
            return
        names = [self.file_name(1)]
        if self.page_count > 1:
            names.append(self.file_name(2) if self.page_count == 2 else "…")
            names.append(self.file_name(self.page_count))
        txt = "Получится: " + ", ".join(dict.fromkeys(names))
        exists = sum(1 for p in range(1, self.page_count + 1)
                     if os.path.exists(os.path.join(self.folder, self.file_name(p))))
        if exists:
            txt += f"\n⚠ В папке уже есть файлы с такими именами ({exists} шт.) — перезапишутся."
        self.preview.setText(txt)

    def remember(self):
        s = settings_load()
        tpl = self.combo_tpl.currentData()
        tpls = s.get("png_templates", [])
        if tpl and tpl not in tpls and tpl not in self.DEFAULT_TEMPLATES:
            tpls.insert(0, tpl)
        s["png_templates"] = tpls[:8]
        s["last_png_template"] = tpl
        s["last_png_dir"] = self.folder
        s["png_dpi"] = self.dpi()
        settings_save(s)


class PageOrganizer(QDialog):
    """Отдельное окно управления страницами: порядок, поворот, удаление, добавление."""

    def __init__(self, doc, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Упорядочить страницы")
        self.resize(940, 660)
        self.doc = doc
        self.added_docs = []          # чтобы не закрылись раньше времени
        # модель: список (источник, индекс_в_источнике, поворот)
        self.items = [("main", i, 0) for i in range(doc.page_count)]

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(10)

        top = QHBoxLayout()
        top.setSpacing(8)
        title = QLabel("<b>Страницы документа</b>")
        top.addWidget(title)
        top.addStretch()
        self.lbl_count = QLabel("")
        self.lbl_count.setObjectName("hint")
        top.addWidget(self.lbl_count)
        lay.addLayout(top)

        self.list = QListWidget()
        self.list.setViewMode(QListWidget.IconMode)
        self.list.setIconSize(QSize(132, 176))
        self.list.setGridSize(QSize(164, 218))
        self.list.setResizeMode(QListWidget.Adjust)
        self.list.setMovement(QListWidget.Snap)
        self.list.setSelectionMode(QListWidget.ExtendedSelection)
        self.list.setDragDropMode(QListWidget.NoDragDrop)   # двигаем сами — группой
        self.list.setSpacing(6)
        self.list.viewport().installEventFilter(self)
        lay.addWidget(self.list, 1)

        tools = QHBoxLayout()
        tools.setSpacing(6)

        def tool(text, kind, slot, tip=""):
            b = QPushButton(" " + text)
            b.setIconSize(QSize(16, 16))
            b.setMinimumHeight(34)
            b.setToolTip(tip or text)
            b.clicked.connect(slot)
            if parent is not None and hasattr(parent, "_icon_color"):
                b.setIcon(draw_icon(kind, parent._icon_color()))
            tools.addWidget(b)
            return b

        tool("Добавить из PDF", "folder", self.add_from_pdf,
             "Вставить страницы из другого PDF-файла")
        tools.addSpacing(12)
        tool("Влево", "rot_left", lambda: self.rotate(-90), "Повернуть выбранные влево")
        tool("Вправо", "rot_right", lambda: self.rotate(90), "Повернуть выбранные вправо")
        tools.addSpacing(12)
        tool("Выше", "up", lambda: self.shift(-1), "Сдвинуть выбранные выше")
        tool("Ниже", "down", lambda: self.shift(1), "Сдвинуть выбранные ниже")
        tool("Удалить", "trash", self.remove, "Удалить выбранные страницы")
        tools.addStretch()
        lay.addLayout(tools)

        hint = QLabel("Перетаскивайте страницы мышкой. Выделите несколько "
                      "(Ctrl или Shift) — они переедут вместе.")
        hint.setObjectName("hint")
        lay.addWidget(hint)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Применить")
        bb.button(QDialogButtonBox.Cancel).setText("Отмена")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

        self.reload()

    # ---- перетаскивание мышкой (в т.ч. нескольких выделенных) ----
    def eventFilter(self, obj, event):
        if obj is self.list.viewport():
            if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                self._drag_from = self.list.indexAt(event.position().toPoint()).row()
                self._drag_started = False
            elif event.type() == QEvent.MouseMove and event.buttons() & Qt.LeftButton:
                if getattr(self, "_drag_from", -1) >= 0:
                    self._drag_started = True
                    self.list.viewport().setCursor(Qt.ClosedHandCursor)
            elif event.type() == QEvent.MouseButtonRelease:
                self.list.viewport().unsetCursor()
                if getattr(self, "_drag_started", False):
                    to = self.list.indexAt(event.position().toPoint()).row()
                    self._drag_started = False
                    src_row = getattr(self, "_drag_from", -1)
                    self._drag_from = -1
                    if to >= 0 and src_row >= 0 and to != src_row:
                        self.move_selection_to(src_row, to)
                        return True
                self._drag_from = -1
        return super().eventFilter(obj, event)

    def move_selection_to(self, grabbed_row, target_row):
        rows = self._selected_rows()
        if grabbed_row not in rows:
            rows = [grabbed_row]
        moving = [self.items[r] for r in rows]
        rest = [it for i, it in enumerate(self.items) if i not in rows]
        before = sum(1 for r in rows if r < target_row)
        pos = max(0, min(len(rest), target_row - before))
        if target_row > max(rows):
            pos = max(0, min(len(rest), target_row - len(rows) + 1))
        self.items = rest[:pos] + moving + rest[pos:]
        self.reload(keep=list(range(pos, pos + len(moving))))

    # ---- отрисовка ----
    def _source_doc(self, tag):
        return self.doc if tag == "main" else self.added_docs[tag]

    def reload(self, keep=None):
        self.list.blockSignals(True)
        self.list.clear()
        for n, (tag, idx, rot) in enumerate(self.items):
            d = self._source_doc(tag)
            page = d[idx]
            saved = page.rotation
            try:
                page.set_rotation((saved + rot) % 360)
                pix = page.get_pixmap(dpi=26, alpha=False)
            finally:
                page.set_rotation(saved)
            img = QImage(pix.samples, pix.width, pix.height, pix.stride,
                         QImage.Format_RGB888)
            pm = QPixmap.fromImage(img.copy()).scaled(
                132, 176, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            label = f"{n + 1}" if tag == "main" else f"{n + 1} (добавлена)"
            it = QListWidgetItem(QIcon(pm), label)
            it.setTextAlignment(Qt.AlignHCenter)
            it.setData(Qt.UserRole, n)
            self.list.addItem(it)
        self.list.blockSignals(False)
        self.lbl_count.setText(f"всего страниц: {len(self.items)}")
        if keep:
            for row in keep:
                if 0 <= row < self.list.count():
                    self.list.item(row).setSelected(True)
            if keep:
                self.list.setCurrentRow(keep[0])

    def sync_from_view(self, *args):
        order = [self.list.item(i).data(Qt.UserRole) for i in range(self.list.count())]
        self.items = [self.items[i] for i in order]
        self.reload()

    def _selected_rows(self):
        return sorted(self.list.row(i) for i in self.list.selectedItems())

    # ---- операции ----
    def rotate(self, delta):
        rows = self._selected_rows()
        if not rows:
            QMessageBox.information(self, "Ничего не выбрано",
                                    "Выделите страницы, которые нужно повернуть.")
            return
        for r in rows:
            tag, idx, rot = self.items[r]
            self.items[r] = (tag, idx, (rot + delta) % 360)
        self.reload(keep=rows)

    def shift(self, delta):
        rows = self._selected_rows()
        if not rows:
            return
        if delta < 0 and rows[0] == 0:
            return
        if delta > 0 and rows[-1] == len(self.items) - 1:
            return
        order = list(range(len(self.items)))
        for r in (rows if delta < 0 else reversed(rows)):
            order[r], order[r + delta] = order[r + delta], order[r]
        self.items = [self.items[i] for i in order]
        self.reload(keep=[r + delta for r in rows])

    def remove(self):
        rows = self._selected_rows()
        if not rows:
            QMessageBox.information(self, "Ничего не выбрано",
                                    "Выделите страницы, которые нужно удалить.")
            return
        if len(rows) >= len(self.items):
            QMessageBox.information(self, "Нельзя",
                                    "Нельзя удалить все страницы — хотя бы одна должна остаться.")
            return
        self.items = [it for i, it in enumerate(self.items) if i not in rows]
        self.reload(keep=[max(0, rows[0] - 1)])

    def add_from_pdf(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Выбрать PDF, страницы которого добавить", "", "PDF (*.pdf)")
        if not paths:
            return
        where = len(self.items)
        rows = self._selected_rows()
        if rows:
            where = rows[-1] + 1
        added = 0
        for p in paths:
            try:
                d = fitz.open(p)
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Не удалось открыть:\n{p}\n{e}")
                continue
            tag = len(self.added_docs)
            self.added_docs.append(d)
            for i in range(d.page_count):
                self.items.insert(where + added, (tag, i, 0))
                added += 1
        if added:
            self.reload(keep=list(range(where, where + added)))

    def result_doc(self) -> "fitz.Document":
        """Собрать новый документ по текущему порядку."""
        out = fitz.open()
        for tag, idx, rot in self.items:
            d = self._source_doc(tag)
            out.insert_pdf(d, from_page=idx, to_page=idx)
            page = out[out.page_count - 1]
            if rot:
                page.set_rotation((page.rotation + rot) % 360)
        return out

    def page_mapping(self):
        """Куда переехали страницы исходного документа: старый индекс -> новый."""
        remap = {}
        for new, (tag, idx, rot) in enumerate(self.items):
            if tag == "main" and idx not in remap:
                remap[idx] = new
        return remap

    def closeEvent(self, e):
        for d in self.added_docs:
            try:
                d.close()
            except Exception:
                pass
        super().closeEvent(e)


class CropDialog(QDialog):
    """Обрезка страницы: поля с любой стороны, результат виден сразу."""

    def __init__(self, doc, page_index, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Обрезать страницу")
        self.doc = doc
        self.page_index = page_index
        page = doc[page_index]
        self.page_w = page.rect.width
        self.page_h = page.rect.height

        lay = QVBoxLayout(self)
        lay.setSpacing(10)

        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumSize(420, 470)
        self.preview.setStyleSheet(
            "background: #ffffff; border: 1px solid #d8d2c4; border-radius: 8px;")
        lay.addWidget(self.preview, 1)

        self.spins = {}
        grid = QFormLayout()
        grid.setSpacing(6)
        for key, title in (("top", "Сверху"), ("bottom", "Снизу"),
                           ("left", "Слева"), ("right", "Справа")):
            sp = QDoubleSpinBox()
            sp.setRange(0, 200)
            sp.setSuffix(" мм")
            sp.setDecimals(1)
            sp.setSingleStep(1.0)
            sp.valueChanged.connect(self.update_preview)
            sp.setFocusPolicy(Qt.StrongFocus)
            self.spins[key] = sp
            grid.addRow(title + ":", sp)
        lay.addLayout(grid)

        row = QHBoxLayout()
        b_auto = QPushButton("Убрать белые поля")
        b_auto.setToolTip("Определить края документа автоматически")
        b_auto.clicked.connect(self.auto_crop)
        b_reset = QPushButton("Сбросить")
        b_reset.clicked.connect(self.reset)
        row.addWidget(b_auto)
        row.addWidget(b_reset)
        lay.addLayout(row)

        self.chk_all = QCheckBox("применить ко всем страницам документа")
        lay.addWidget(self.chk_all)

        self.lbl_size = QLabel("")
        self.lbl_size.setObjectName("hint")
        lay.addWidget(self.lbl_size)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Обрезать")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

        self.base_pix = self._render()
        self.update_preview()

    def _render(self):
        page = self.doc[self.page_index]
        pix = page.get_pixmap(dpi=60, alpha=False)
        img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
        return QPixmap.fromImage(img.copy())

    def margins_mm(self):
        return {k: sp.value() for k, sp in self.spins.items()}

    def crop_rect(self):
        mm = self.margins_mm()
        r = self.doc[self.page_index].rect
        x0 = r.x0 + mm["left"] * MM_TO_PT
        y0 = r.y0 + mm["top"] * MM_TO_PT
        x1 = r.x1 - mm["right"] * MM_TO_PT
        y1 = r.y1 - mm["bottom"] * MM_TO_PT
        if x1 - x0 < 20 or y1 - y0 < 20:
            return None
        return fitz.Rect(x0, y0, x1, y1)

    def update_preview(self):
        pm = self.base_pix
        if pm.isNull():
            return
        mm = self.margins_mm()
        sx = pm.width() / self.page_w
        sy = pm.height() / self.page_h
        shot = QPixmap(pm)
        p = QPainter(shot)
        p.setBrush(QColor(0, 0, 0, 110))
        p.setPen(Qt.NoPen)
        t = int(mm["top"] * MM_TO_PT * sy)
        b = int(mm["bottom"] * MM_TO_PT * sy)
        l = int(mm["left"] * MM_TO_PT * sx)
        r = int(mm["right"] * MM_TO_PT * sx)
        if t: p.drawRect(0, 0, shot.width(), t)
        if b: p.drawRect(0, shot.height() - b, shot.width(), b)
        if l: p.drawRect(0, 0, l, shot.height())
        if r: p.drawRect(shot.width() - r, 0, r, shot.height())
        p.setPen(QPen(QColor(200, 130, 20), 2, Qt.DashLine))
        p.setBrush(Qt.NoBrush)
        p.drawRect(l, t, max(1, shot.width() - l - r), max(1, shot.height() - t - b))
        p.end()
        self.preview.setPixmap(shot.scaled(self.preview.width() - 8,
                                           self.preview.height() - 8,
                                           Qt.KeepAspectRatio, Qt.SmoothTransformation))
        new_w = (self.page_w - (mm["left"] + mm["right"]) * MM_TO_PT) / MM_TO_PT
        new_h = (self.page_h - (mm["top"] + mm["bottom"]) * MM_TO_PT) / MM_TO_PT
        self.lbl_size.setText(
            f"Было {self.page_w / MM_TO_PT:.0f}×{self.page_h / MM_TO_PT:.0f} мм → "
            f"станет {max(0, new_w):.0f}×{max(0, new_h):.0f} мм")

    def reset(self):
        for sp in self.spins.values():
            sp.setValue(0)

    def auto_crop(self):
        page = self.doc[self.page_index]
        pix = page.get_pixmap(dpi=50, alpha=False)
        im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples).convert("L")
        box = im.point(lambda v: 255 if v < 235 else 0).getbbox()
        if not box:
            QMessageBox.information(self, "Пусто", "На странице не нашлось содержимого.")
            return
        pad = 3
        sx = self.page_w / im.width
        sy = self.page_h / im.height
        self.spins["left"].setValue(max(0, (box[0] * sx) / MM_TO_PT - pad))
        self.spins["top"].setValue(max(0, (box[1] * sy) / MM_TO_PT - pad))
        self.spins["right"].setValue(max(0, ((im.width - box[2]) * sx) / MM_TO_PT - pad))
        self.spins["bottom"].setValue(max(0, ((im.height - box[3]) * sy) / MM_TO_PT - pad))



# Встроенный фон: настоящий скан пустого стекла сканера (A4, 1556×2200 JPEG)
SCANNER_BG_B64 = (
    "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"
)


# ======================================================================
#  Кадрирование рамкой (как в iLovePDF) и разделение страницы на два листа
# ======================================================================

def crop_templates_load(kind: str) -> list:
    """Шаблоны обрезки из settings.json: [{name, kind, rects:[{x,y,w,h}]}] (мм)."""
    out = []
    for t in settings_load().get("crop_templates", []) or []:
        try:
            if t.get("kind", "crop") == kind and t.get("name") and t.get("rects"):
                out.append(t)
        except Exception:
            continue
    return out


def crop_templates_save_all(items: list):
    s = settings_load()
    s["crop_templates"] = items
    settings_save(s)


def crop_template_add(name: str, kind: str, rects_mm: list):
    items = [t for t in (settings_load().get("crop_templates", []) or [])
             if not (t.get("name") == name and t.get("kind", "crop") == kind)]
    items.append({"name": name, "kind": kind,
                  "rects": [{"x": round(r[0], 1), "y": round(r[1], 1),
                             "w": round(r[2], 1), "h": round(r[3], 1)} for r in rects_mm]})
    crop_templates_save_all(items)


def crop_template_remove(name: str, kind: str):
    items = [t for t in (settings_load().get("crop_templates", []) or [])
             if not (t.get("name") == name and t.get("kind", "crop") == kind)]
    crop_templates_save_all(items)


def find_two_sheets(page):
    """Найти на странице два отдельных листа: вернуть два прямоугольника (pt, как видно)."""
    pix = page.get_pixmap(dpi=40, alpha=False)
    im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples).convert("L")
    W, H = im.size
    # фон сканера — медиана яркости полосы у краёв; «лист» — всё, что от него отличается
    # (и текст, и сама бумага, которая обычно светлее фона)
    bgv = 255
    try:
        band = Image.new("L", (W, 2 * 4 + 2 * 4))
        band.paste(im.crop((0, 2, W, 6)), (0, 0))
        band.paste(im.crop((0, H - 6, W, H - 2)), (0, 4))
        band.paste(im.crop((2, 0, 6, H)).resize((W, 4)), (0, 8))
        band.paste(im.crop((W - 6, 0, W - 2, H)).resize((W, 4)), (0, 12))
        bgv = int(ImageStat.Stat(band).median[0])
    except Exception:
        pass
    if bgv >= 245:
        ink = im.point(lambda v: 255 if v < 215 else 0)
    else:
        ink = im.point(lambda v, b=bgv: 255 if (v < 215 or abs(v - b) > 10) else 0)
    pw, ph = page.rect.width, page.rect.height
    sx, sy = pw / W, ph / H
    px = ink.load()
    rows = [sum(1 for x in range(W) if px[x, y]) for y in range(H)]
    cols = [sum(1 for y in range(H) if px[x, y]) for x in range(W)]
    # тёмные линии кромки стекла сканера у краёв (во всю длину) — не содержимое
    edge = max(2, int(8 * MM_TO_PT * 40 / 72))
    dr = ImageDraw.Draw(ink)
    for x in list(range(0, edge)) + list(range(W - edge, W)):
        if cols[x] > 0.4 * H:
            dr.line((x, 0, x, H - 1), fill=0)
            cols[x] = 0
    for y in list(range(0, edge)) + list(range(H - edge, H)):
        if rows[y] > 0.4 * W:
            dr.line((0, y, W - 1, y), fill=0)
            rows[y] = 0
    rows = [sum(1 for x in range(W) if px[x, y]) for y in range(H)]
    cols = [sum(1 for y in range(H) if px[x, y]) for x in range(W)]
    total = sum(rows)
    if total < 20:
        return [fitz.Rect(0, 0, pw, ph / 2), fitz.Rect(0, ph / 2, pw, ph)]

    def best_gap(prof):
        """Пустой промежуток, по обе стороны от которого достаточно содержимого."""
        n = len(prof)
        thr = max(2, int(0.004 * (W if prof is rows else H)))
        best = None
        i = 0
        while i < n:
            if prof[i] <= thr:
                j = i
                while j < n and prof[j] <= thr:
                    j += 1
                before = sum(prof[:i])
                after = sum(prof[j:])
                if j - i >= 3 and before >= 0.12 * total and after >= 0.12 * total:
                    score = min(before, after)
                    if best is None or score > best[0]:
                        best = (score, (i + j) / 2.0)
                i = j
            else:
                i += 1
        return best

    gy = best_gap(rows)
    gx = best_gap(cols)
    pad_px = 3

    def bbox_of(x0, y0, x1, y1):
        """Границы содержимого в области, без учёта одиночных точек-пылинок."""
        sub = ink.crop((int(x0), int(y0), int(x1), int(y1)))
        sw, sh = sub.size
        sp = sub.load()
        r = [sum(1 for x in range(sw) if sp[x, y]) for y in range(sh)]
        c = [sum(1 for y in range(sh) if sp[x, y]) for x in range(sw)]
        ys = [i for i, v in enumerate(r) if v > 2]
        xs = [i for i, v in enumerate(c) if v > 2]
        if not ys or not xs:
            return (x0, y0, x1, y1)
        return (max(0, x0 + xs[0] - pad_px), max(0, y0 + ys[0] - pad_px),
                min(W, x0 + xs[-1] + 1 + pad_px), min(H, y0 + ys[-1] + 1 + pad_px))

    if gy and (not gx or gy[0] >= gx[0]):
        a = bbox_of(0, 0, W, gy[1])
        b = bbox_of(0, gy[1], W, H)
    elif gx:
        a = bbox_of(0, 0, gx[1], H)
        b = bbox_of(gx[1], 0, W, H)
    elif H >= W:
        a = bbox_of(0, 0, W, H / 2)
        b = bbox_of(0, H / 2, W, H)
    else:
        a = bbox_of(0, 0, W / 2, H)
        b = bbox_of(W / 2, 0, W, H)
    return [fitz.Rect(a[0] * sx, a[1] * sy, a[2] * sx, a[3] * sy),
            fitz.Rect(b[0] * sx, b[1] * sy, b[2] * sx, b[3] * sy)]


_BUILTIN_BG = None


def builtin_scanner_bg():
    """Встроенный скан пустого стекла (зашит в программу)."""
    global _BUILTIN_BG
    if _BUILTIN_BG is None:
        try:
            import base64
            _BUILTIN_BG = Image.open(io.BytesIO(base64.b64decode(SCANNER_BG_B64))).convert("RGB")
        except Exception:
            _BUILTIN_BG = False
    return _BUILTIN_BG or None


def load_scanner_bg(path):
    """Отсканированный пустой фон сканера: PDF (первая страница) или картинка → PIL RGB."""
    if not path or not os.path.isfile(path):
        return None
    try:
        if path.lower().endswith(".pdf"):
            d = fitz.open(path)
            pix = d[0].get_pixmap(dpi=150, alpha=False)
            im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            d.close()
            return im
        return Image.open(path).convert("RGB")
    except Exception:
        return None


def synth_scanner_bg(W, H, mm):
    """Искусственный фон сканера: светло-серое стекло с зерном и тёмной кромкой."""
    base = Image.new("RGB", (W, H), (232, 234, 231))
    try:
        noise = Image.effect_noise((W, H), 5).convert("RGB")
        base = ImageChops.add(base, noise, 1.0, -128)
    except Exception:
        pass
    dr = ImageDraw.Draw(base)
    e = max(1, int(0.8 * mm))
    dr.rectangle((0, 0, W - 1, e), fill=(70, 70, 68))
    dr.rectangle((0, 0, e, H - 1), fill=(70, 70, 68))
    dr.line((0, e + 1, W - 1, e + 1), fill=(150, 150, 148))
    dr.line((e + 1, 0, e + 1, H - 1), fill=(150, 150, 148))
    return base


def paste_sheet(canvas, frag, pos, bg):
    """Положить «бумагу» на стекло: мягкая тень по краям, чтобы лист выделялся."""
    x, y = pos
    fw, fh = frag.size
    sh = max(2, int(fw * 0.004) + 2)
    try:
        lw, lh = fw + 4 * sh, fh + 4 * sh
        mask = Image.new("L", (lw, lh), 0)
        ImageDraw.Draw(mask).rectangle((2 * sh + 1, 2 * sh + 1, 2 * sh + fw + 1, 2 * sh + fh + 1), fill=110)
        mask = mask.filter(ImageFilter.GaussianBlur(sh))
        box = (x - 2 * sh, y - 2 * sh, x - 2 * sh + lw, y - 2 * sh + lh)
        region = canvas.crop(box)
        darker = ImageChops.multiply(region, Image.new("RGB", region.size, (150, 150, 150)))
        canvas.paste(Image.composite(darker, region, mask), (box[0], box[1]))
    except Exception:
        pass
    ImageDraw.Draw(canvas).rectangle((x - 1, y - 1, x + fw, y + fh), outline=(200, 200, 198))
    canvas.paste(frag, (x, y))


def build_split_doc(page, rects, layout="side", rotate=0, dpi=200, bg_mode="builtin", bg_path=None):
    """Один лист-скан, на котором два фрагмента лежат как две отдельные бумаги.
    rects — прямоугольники в pt (как страница видна).
    layout: side (рядом слева направо) / stack (друг под другом) / original (где были).
    bg_mode: builtin (встроенный настоящий скан пустого стекла — по умолчанию),
             auto (фон с этой же страницы; если страница белая — искусственный),
             synth (искусственный серый фон сканера), file (скан пустого фона из bg_path).
    Возвращает (документ из одной страницы, сдвиги фрагментов в pt)."""
    pix = page.get_pixmap(dpi=dpi, alpha=False)
    im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    W, H = im.size
    k = dpi / 72.0
    mm = MM_TO_PT * k  # пикселей в миллиметре

    # цвет фона сканера: медиана полосы 4–8 мм от краёв страницы
    band = []
    for crop in ((0, int(4 * mm), W, int(8 * mm)), (0, H - int(8 * mm), W, H - int(4 * mm)),
                 (int(4 * mm), 0, int(8 * mm), H), (W - int(8 * mm), 0, W - int(4 * mm), H)):
        try:
            band.append(im.crop(crop).resize((64, 64)))
        except Exception:
            pass
    if band:
        strip = Image.new("RGB", (64, 64 * len(band)))
        for i, b in enumerate(band):
            strip.paste(b, (0, 64 * i))
        bg = tuple(int(v) for v in ImageStat.Stat(strip).median)
    else:
        bg = (236, 237, 235)
    white_source = sum(bg) > 740
    if white_source:
        bg = (250, 250, 250)

    # основа листа: собственный скан, скан пустого фона из файла или искусственный
    base = None
    if bg_mode == "file":
        base = load_scanner_bg(bg_path)
    if bg_mode == "builtin" or (bg_mode == "file" and base is None):
        base = builtin_scanner_bg()
    if base is not None:
        base = base.resize((W, H), Image.LANCZOS)
    if base is None and (bg_mode in ("synth", "file") or (bg_mode == "auto" and white_source)):
        base = synth_scanner_bg(W, H, mm)
    if base is not None:
        bg = tuple(int(v) for v in ImageStat.Stat(base.crop((W // 3, H // 3, 2 * W // 3, 2 * H // 3))).median)

    def to_px(r):
        return (max(0, int(r.x0 * k)), max(0, int(r.y0 * k)),
                min(W, int(r.x1 * k) + 1), min(H, int(r.y1 * k) + 1))

    px_rects = [to_px(r) for r in rects]
    frags = [im.crop(pr) for pr in px_rects]

    def erase(img, pr):
        x0, y0, x1, y1 = pr
        g = int(2.5 * mm)
        x0, y0, x1, y1 = max(0, x0 - g), max(0, y0 - g), min(W, x1 + g), min(H, y1 + g)
        w, h = x1 - x0, y1 - y0
        if w <= 0 or h <= 0:
            return
        fill = Image.new("RGB", (w, h), bg)
        try:
            noise = Image.effect_noise((w, h), 6).convert("RGB")
            fill = ImageChops.add(fill, noise, 1.0, -128)
        except Exception:
            pass
        img.paste(fill, (x0, y0))

    if base is not None:
        sheet = base
    else:
        sheet = im.copy()
        for pr in px_rects:
            if layout != "original":
                erase(sheet, pr)
    margin = int(6 * mm)
    gap = int(8 * mm)
    moves = []  # (dx_pt, dy_pt, scale) для каждого фрагмента — чтобы переехали печати
    if layout == "original":
        moves = [(0.0, 0.0, 1.0) for _ in frags]
        if base is not None:
            for i, f in enumerate(frags):
                paste_sheet(sheet, f, (px_rects[i][0], px_rects[i][1]), bg)
    else:
        sizes = [f.size for f in frags]
        if layout == "side":
            need_w = sum(w for w, _ in sizes) + gap + 2 * margin
            need_h = max(h for _, h in sizes) + 2 * margin
        else:  # stack
            need_w = max(w for w, _ in sizes) + 2 * margin
            need_h = sum(h for _, h in sizes) + gap + 2 * margin
        scale = min(1.0, (W - 2 * margin) / max(1, need_w - 2 * margin),
                    (H - 2 * margin) / max(1, need_h - 2 * margin))
        if scale < 0.999:
            frags = [f.resize((max(1, int(f.width * scale)), max(1, int(f.height * scale))),
                              Image.LANCZOS) for f in frags]
        x, y = margin, margin
        for i, f in enumerate(frags):
            paste_sheet(sheet, f, (x, y), bg)
            moves.append(((x - px_rects[i][0]) / k, (y - px_rects[i][1]) / k, scale))
            if layout == "side":
                x += f.width + gap
            else:
                y += f.height + gap
    buf = io.BytesIO()
    sheet.save(buf, "JPEG", quality=85, optimize=True)
    out = fitz.open()
    np_ = out.new_page(width=page.rect.width, height=page.rect.height)
    np_.insert_image(np_.rect, stream=buf.getvalue())
    if rotate:
        np_.set_rotation(rotate % 360)
    return out, moves


class CropCanvas(QWidget):
    """Страница с одной или двумя рамками, которые можно рисовать, двигать и тянуть за края."""
    changed = Signal()
    HANDLE = 7

    def __init__(self, pixmap, page_w, page_h, areas=1, parent=None):
        super().__init__(parent)
        self.pix = pixmap
        self.page_w = float(page_w)
        self.page_h = float(page_h)
        self.areas = [QRectF(0, 0, page_w, page_h) for _ in range(areas)]
        if areas == 2:
            self.areas = [QRectF(0, 0, page_w, page_h / 2), QRectF(0, page_h / 2, page_w, page_h / 2)]
        self.active = 0
        self.link_sizes = False
        self.colors = [QColor(230, 140, 20), QColor(40, 140, 220)]
        self._drag = None
        self.setMinimumSize(460, 480)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    # --- геометрия ---------------------------------------------------
    def _fit(self):
        m = 12
        w, h = self.width() - 2 * m, self.height() - 2 * m
        s = min(w / self.page_w, h / self.page_h)
        ox = m + (w - self.page_w * s) / 2
        oy = m + (h - self.page_h * s) / 2
        return s, ox, oy

    def _to_screen(self, r):
        s, ox, oy = self._fit()
        return QRectF(ox + r.x() * s, oy + r.y() * s, r.width() * s, r.height() * s)

    def _to_page(self, pt):
        s, ox, oy = self._fit()
        x = min(self.page_w, max(0.0, (pt.x() - ox) / s))
        y = min(self.page_h, max(0.0, (pt.y() - oy) / s))
        return QPointF(x, y)

    def area(self, i=0):
        return QRectF(self.areas[i])

    def set_area(self, i, r):
        r = QRectF(r).normalized()
        min_sz = 5 * MM_TO_PT
        w = min(self.page_w, max(min_sz, r.width()))
        h = min(self.page_h, max(min_sz, r.height()))
        x = min(self.page_w - w, max(0.0, r.x()))
        y = min(self.page_h - h, max(0.0, r.y()))
        self.areas[i] = QRectF(x, y, w, h)
        if self.link_sizes and len(self.areas) == 2:
            # вторая рамка получает тот же размер, остаётся на своём месте
            j = 1 - i
            o = self.areas[j]
            ox = min(self.page_w - w, max(0.0, o.x()))
            oy = min(self.page_h - h, max(0.0, o.y()))
            self.areas[j] = QRectF(ox, oy, w, h)
        self.update()
        self.changed.emit()

    def set_active(self, i):
        self.active = i
        self.update()

    # --- отрисовка ---------------------------------------------------
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        page = self._to_screen(QRectF(0, 0, self.page_w, self.page_h))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 40))
        p.drawRoundedRect(page.adjusted(3, 4, 3, 4), 4, 4)
        p.drawPixmap(page.toRect(), self.pix)
        path = QPainterPath()
        path.addRect(page)
        for r in self.areas:
            sub = QPainterPath()
            sub.addRect(self._to_screen(r))
            path = path.subtracted(sub)
        p.setBrush(QColor(0, 0, 0, 115))
        p.drawPath(path)
        for i, r in enumerate(self.areas):
            sr = self._to_screen(r)
            col = self.colors[i % len(self.colors)]
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(255, 255, 255, 200), 3))
            p.drawRect(sr)
            pen = QPen(col, 2 if i == self.active else 1.5)
            if i != self.active:
                pen.setStyle(Qt.DashLine)
            p.setPen(pen)
            p.drawRect(sr)
            if i == self.active:
                p.setBrush(QColor(255, 255, 255))
                hs = self.HANDLE
                for hx, hy in self._handle_points(sr):
                    p.drawRect(QRectF(hx - hs / 2, hy - hs / 2, hs, hs))
            txt = f"{r.width() / MM_TO_PT:.0f}×{r.height() / MM_TO_PT:.0f} мм"
            if len(self.areas) > 1:
                txt = f"{i + 1}:  " + txt
            f = p.font()
            f.setPointSize(9)
            f.setBold(True)
            p.setFont(f)
            tw = p.fontMetrics().horizontalAdvance(txt) + 12
            tx = sr.x() + 4
            ty = sr.y() + 4
            if sr.height() < 30:
                ty = sr.y() - 24
            p.setPen(Qt.NoPen)
            p.setBrush(col)
            p.drawRoundedRect(QRectF(tx, ty, tw, 20), 4, 4)
            p.setPen(QColor(255, 255, 255))
            p.drawText(QRectF(tx, ty, tw, 20), Qt.AlignCenter, txt)
        p.end()

    def _handle_points(self, sr):
        cx, cy = sr.center().x(), sr.center().y()
        return [(sr.left(), sr.top()), (cx, sr.top()), (sr.right(), sr.top()),
                (sr.right(), cy), (sr.right(), sr.bottom()), (cx, sr.bottom()),
                (sr.left(), sr.bottom()), (sr.left(), cy)]

    _HANDLE_EDGES = [("l", "t"), ("", "t"), ("r", "t"), ("r", ""), ("r", "b"),
                     ("", "b"), ("l", "b"), ("l", "")]

    def _hit(self, pos):
        sr = self._to_screen(self.areas[self.active])
        for idx, (hx, hy) in enumerate(self._handle_points(sr)):
            if abs(pos.x() - hx) <= self.HANDLE + 2 and abs(pos.y() - hy) <= self.HANDLE + 2:
                return ("resize", self._HANDLE_EDGES[idx])
        for i, r in enumerate(self.areas):
            if self._to_screen(r).contains(pos):
                return ("move", i)
        return ("new", None)

    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        kind, info = self._hit(e.position())
        pp = self._to_page(e.position())
        if kind == "resize":
            self._drag = ("resize", info, QRectF(self.areas[self.active]))
        elif kind == "move":
            self.active = info
            self._drag = ("move", pp, QRectF(self.areas[info]))
            self.update()
        else:
            self._drag = ("new", pp, None)
        e.accept()

    def mouseMoveEvent(self, e):
        if self._drag is None:
            kind, info = self._hit(e.position())
            if kind == "resize":
                ex, ey = info
                if (ex, ey) in (("l", "t"), ("r", "b")):
                    self.setCursor(Qt.SizeFDiagCursor)
                elif (ex, ey) in (("r", "t"), ("l", "b")):
                    self.setCursor(Qt.SizeBDiagCursor)
                elif ex:
                    self.setCursor(Qt.SizeHorCursor)
                else:
                    self.setCursor(Qt.SizeVerCursor)
            elif kind == "move":
                self.setCursor(Qt.SizeAllCursor)
            else:
                self.setCursor(Qt.CrossCursor)
            return
        pp = self._to_page(e.position())
        mode, a, b = self._drag
        if mode == "new":
            self.set_area(self.active, QRectF(a, pp))
        elif mode == "move":
            d = pp - a
            r = QRectF(b)
            r.translate(d)
            r.moveLeft(min(self.page_w - r.width(), max(0.0, r.left())))
            r.moveTop(min(self.page_h - r.height(), max(0.0, r.top())))
            self.set_area(self.active, r)
        else:
            ex, ey = a
            r = QRectF(b)
            min_sz = 5 * MM_TO_PT
            if ex == "l":
                r.setLeft(min(pp.x(), r.right() - min_sz))
            elif ex == "r":
                r.setRight(max(pp.x(), r.left() + min_sz))
            if ey == "t":
                r.setTop(min(pp.y(), r.bottom() - min_sz))
            elif ey == "b":
                r.setBottom(max(pp.y(), r.top() + min_sz))
            self.set_area(self.active, r)
        e.accept()

    def mouseReleaseEvent(self, e):
        self._drag = None
        e.accept()


class FrameCropDialog(QDialog):
    """Кадрирование рамкой (mode='crop') или разделение на два листа (mode='split')."""

    def __init__(self, doc, page_index, parent=None, mode="crop"):
        super().__init__(parent)
        self.mode = mode
        self.doc = doc
        self.page_index = page_index
        self.page = doc[page_index]
        self.page_w = self.page.rect.width
        self.page_h = self.page.rect.height
        self.setWindowTitle("Кадрировать страницу" if mode == "crop"
                            else "Разделить на две бумаги на одном скане")
        self.setMinimumSize(1100, 700)
        self.resize(1180, 740)
        self._syncing = True   # пока окно строится, синхронизация выключена

        pix = self.page.get_pixmap(dpi=110, alpha=False)
        img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
        pm = QPixmap.fromImage(img.copy())

        root = QHBoxLayout(self)
        root.setSpacing(12)
        self.canvas = CropCanvas(pm, self.page_w, self.page_h, 2 if mode == "split" else 1)
        self.canvas.changed.connect(self._from_canvas)
        root.addWidget(self.canvas, 1)

        side = QVBoxLayout()
        side.setSpacing(8)
        hint = QLabel("Нарисуйте рамку мышью на странице.\nРамку можно двигать и тянуть за края."
                      if mode == "crop" else
                      "Две рамки — две «бумаги» на одном скане с фоном сканера.\n"
                      "Рамки можно двигать и тянуть за края.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        side.addWidget(hint)

        if mode == "split":
            rr = QHBoxLayout()
            self.rb_area = []
            for i, title in enumerate(("Бумага 1", "Бумага 2")):
                rb = QRadioButton(title)
                rb.toggled.connect(lambda on, i=i: on and self._pick_area(i))
                self.rb_area.append(rb)
                rr.addWidget(rb)
            self.rb_area[0].setChecked(True)
            side.addLayout(rr)
            self.chk_link = QCheckBox("обе рамки одного размера")
            self.chk_link.setToolTip("Меняете размер одной рамки — вторая повторяет его, "
                                     "чтобы не промахнуться с размерами")
            self.chk_link.setChecked(bool(settings_load().get("split_link_sizes", True)))
            self.chk_link.toggled.connect(self._set_link)
            side.addWidget(self.chk_link)
            self.canvas.link_sizes = self.chk_link.isChecked()

        box = QGroupBox("Размер и положение рамки")
        form = QFormLayout(box)
        form.setSpacing(6)
        self.sp = {}
        for key, title, mx in (("w", "Ширина", 2000), ("h", "Высота", 2000),
                               ("x", "Отступ слева", 2000), ("y", "Отступ сверху", 2000)):
            s = QDoubleSpinBox()
            s.setRange(0, mx)
            s.setDecimals(1)
            s.setSuffix(" мм")
            s.setSingleStep(1.0)
            s.setMinimumHeight(28)
            s.setFocusPolicy(Qt.StrongFocus)
            s.valueChanged.connect(self._from_spins)
            self.sp[key] = s
            form.addRow(title + ":", s)
        side.addWidget(box)

        quick = QVBoxLayout()
        quick.setSpacing(6)
        if mode == "crop":
            b_auto = QPushButton("Убрать белые поля")
            b_auto.clicked.connect(self.auto_content)
            b_all = QPushButton("Вся страница")
            b_all.clicked.connect(lambda: self.canvas.set_area(0, QRectF(0, 0, self.page_w, self.page_h)))
            quick.addWidget(b_auto)
            quick.addWidget(b_all)
        else:
            b_auto = QPushButton("Найти два листа")
            b_auto.setToolTip("Автоматически найти два документа на странице")
            b_auto.clicked.connect(self.auto_two)
            b_v = QPushButton("Пополам ↕")
            b_v.setToolTip("Верхняя и нижняя половины")
            b_v.clicked.connect(lambda: self._halves(True))
            b_h = QPushButton("Пополам ↔")
            b_h.setToolTip("Левая и правая половины")
            b_h.clicked.connect(lambda: self._halves(False))
            quick.addWidget(b_auto)
            row2 = QHBoxLayout()
            row2.addWidget(b_v)
            row2.addWidget(b_h)
            quick.addLayout(row2)
        side.addLayout(quick)

        tbox = QGroupBox("Шаблоны")
        tl = QVBoxLayout(tbox)
        tl.setSpacing(6)
        self.cmb_tpl = QComboBox()
        self.cmb_tpl.setToolTip("Сохранённые размеры рамок — для документов, которые режутся одинаково")
        self.cmb_tpl.activated.connect(self._apply_template)
        tl.addWidget(self.cmb_tpl)
        tr = QHBoxLayout()
        b_tsave = QPushButton("Сохранить как шаблон…")
        b_tsave.clicked.connect(self._save_template)
        b_tdel = QPushButton("Удалить")
        b_tdel.setToolTip("Удалить выбранный шаблон")
        b_tdel.clicked.connect(self._delete_template)
        tr.addWidget(b_tsave, 1)
        tr.addWidget(b_tdel)
        tl.addLayout(tr)
        side.addWidget(tbox)

        if mode == "crop":
            self.chk_all = QCheckBox("применить ко всем страницам документа")
            side.addWidget(self.chk_all)
        else:
            obox = QGroupBox("Как разложить на скане")
            of = QFormLayout(obox)
            of.setSpacing(6)
            self.cmb_place = QComboBox()
            self.cmb_place.addItem("рядом, слева направо", "side")
            self.cmb_place.addItem("друг под другом", "stack")
            self.cmb_place.addItem("оставить где были", "original")
            of.addRow("На скане:", self.cmb_place)
            self.cmb_rot = QComboBox()
            self.cmb_rot.addItem("не поворачивать", 0)
            self.cmb_rot.addItem("повернуть на 90° по часовой", 90)
            self.cmb_rot.addItem("повернуть на 90° против часовой", 270)
            of.addRow("Поворот:", self.cmb_rot)
            self.cmb_dpi = QComboBox()
            native = self._native_dpi()
            if native:
                self.cmb_dpi.addItem(f"как у исходника ({native} dpi)", native)
            for d in (150, 200, 300):
                self.cmb_dpi.addItem(f"{d} dpi", d)
            self.cmb_dpi.setCurrentIndex(0 if native else 1)
            of.addRow("Качество:", self.cmb_dpi)
            self.cmb_bg = QComboBox()
            self.cmb_bg.addItem("встроенный скан пустого сканера", "builtin")
            self.cmb_bg.addItem("с этой страницы (авто)", "auto")
            self.cmb_bg.addItem("серый фон сканера (искусственный)", "synth")
            self.cmb_bg.addItem("из файла — скан пустого стекла", "file")
            self.cmb_bg.setToolTip("Откуда взять фон стекла сканера. По умолчанию — настоящий "
                                   "скан пустого сканера, зашитый в программу")
            self.cmb_bg.currentIndexChanged.connect(self._bg_changed)
            of.addRow("Фон:", self.cmb_bg)
            bgrow = QHBoxLayout()
            self.lbl_bg = QLabel("")
            self.lbl_bg.setObjectName("hint")
            self.b_bg = QPushButton("Выбрать файл фона…")
            self.b_bg.setToolTip("Отсканируйте пустой сканер (без бумаги) и укажите этот PDF или картинку")
            self.b_bg.clicked.connect(self._pick_bg)
            bgrow.addWidget(self.b_bg)
            bgrow.addWidget(self.lbl_bg, 1)
            of.addRow("", bgrow)
            side.addWidget(obox)
            self.chk_replace = QCheckBox("заменить исходную страницу новым сканом")
            self.chk_replace.setChecked(True)
            side.addWidget(self.chk_replace)
            opts = settings_load().get("split_opts", {})
            for cmb, key in ((self.cmb_place, "place"), (self.cmb_rot, "rot"),
                             (self.cmb_dpi, "dpi"), (self.cmb_bg, "bg")):
                if key in opts:
                    k = cmb.findData(opts[key])
                    if k >= 0:
                        cmb.setCurrentIndex(k)
            self.bg_path = settings_load().get("scanner_bg_file", "")
            self._bg_changed()

        side.addStretch(1)
        self.lbl_info = QLabel("")
        self.lbl_info.setObjectName("hint")
        self.lbl_info.setWordWrap(True)
        if mode == "crop":
            side.addWidget(self.lbl_info)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Обрезать" if mode == "crop" else "Разделить")
        bb.button(QDialogButtonBox.Cancel).setText("Отмена")
        for b in (bb.button(QDialogButtonBox.Ok), bb.button(QDialogButtonBox.Cancel)):
            b.setMinimumHeight(32)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        side.addWidget(bb)

        for b in self.findChildren(QPushButton):
            b.setMinimumHeight(30)
        for cmb in self.findChildren(QComboBox):
            cmb.setMinimumHeight(28)
        sidew = QWidget()
        sidew.setLayout(side)
        sidew.setFixedWidth(380)
        root.addWidget(sidew)

        self._syncing = False
        self.setMinimumHeight(max(700, self.sizeHint().height() + 16))
        self._reload_templates()
        if mode == "split":
            try:
                self.auto_two()
            except Exception:
                pass
        self._from_canvas()

    # --- фон сканера ---------------------------------------------------
    def _bg_changed(self, *_):
        is_file = self.cmb_bg.currentData() == "file"
        self.b_bg.setVisible(is_file)
        self.lbl_bg.setVisible(is_file)
        name = os.path.basename(self.bg_path) if self.bg_path and os.path.isfile(self.bg_path) else "файл не выбран"
        self.lbl_bg.setText(name)

    def _pick_bg(self):
        start = os.path.dirname(self.bg_path) if self.bg_path else ""
        path, _ = QFileDialog.getOpenFileName(
            self, "Скан пустого фона сканера", start,
            "Скан (*.pdf *.png *.jpg *.jpeg *.bmp *.tif *.tiff)")
        if not path:
            return
        if load_scanner_bg(path) is None:
            QMessageBox.warning(self, "Фон", "Не удалось прочитать этот файл как картинку или PDF.")
            return
        self.bg_path = path
        try:
            st = settings_load()
            st["scanner_bg_file"] = path
            settings_save(st)
        except Exception:
            pass
        self._bg_changed()

    # --- синхронизация -----------------------------------------------
    def _set_link(self, on):
        self.canvas.link_sizes = bool(on)
        try:
            st = settings_load()
            st["split_link_sizes"] = bool(on)
            settings_save(st)
        except Exception:
            pass
        if on:
            self.canvas.set_area(self.canvas.active, self.canvas.area(self.canvas.active))

    def _pick_area(self, i):
        self.canvas.set_active(i)
        self._from_canvas()

    def _from_canvas(self):
        if self._syncing:
            return
        self._syncing = True
        r = self.canvas.area(self.canvas.active)
        self.sp["w"].setValue(r.width() / MM_TO_PT)
        self.sp["h"].setValue(r.height() / MM_TO_PT)
        self.sp["x"].setValue(r.x() / MM_TO_PT)
        self.sp["y"].setValue(r.y() / MM_TO_PT)
        if self.mode == "split" and hasattr(self, "rb_area"):
            self.rb_area[self.canvas.active].setChecked(True)
        self._syncing = False
        self._update_info()

    def _from_spins(self):
        if self._syncing:
            return
        self._syncing = True
        r = QRectF(self.sp["x"].value() * MM_TO_PT, self.sp["y"].value() * MM_TO_PT,
                   self.sp["w"].value() * MM_TO_PT, self.sp["h"].value() * MM_TO_PT)
        self.canvas.set_area(self.canvas.active, r)
        self._syncing = False
        self._from_canvas()

    def _update_info(self):
        if self.mode == "crop":
            r = self.canvas.area(0)
            self.lbl_info.setText(
                f"Страница {self.page_w / MM_TO_PT:.0f}×{self.page_h / MM_TO_PT:.0f} мм → "
                f"после обрезки {r.width() / MM_TO_PT:.0f}×{r.height() / MM_TO_PT:.0f} мм")
        else:
            self.lbl_info.setText(
                "Получится один лист того же размера с двумя отдельными бумагами; "
                "фон — как у сканера, взят с этой же страницы.")

    def _native_dpi(self):
        """Разрешение скана на странице (0, если картинки нет)."""
        try:
            best = 0
            for inf in self.page.get_image_info():
                bw = inf["bbox"][2] - inf["bbox"][0]
                if bw > 50:
                    best = max(best, inf["width"] / (bw / 72.0))
            if best:
                return int(min(300, max(100, round(best / 10.0) * 10)))
        except Exception:
            pass
        return 0

    # --- быстрые действия ---------------------------------------------
    def auto_content(self):
        pix = self.page.get_pixmap(dpi=50, alpha=False)
        im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples).convert("L")
        box = im.point(lambda v: 255 if v < 235 else 0).getbbox()
        if not box:
            QMessageBox.information(self, "Пусто", "На странице не нашлось содержимого.")
            return
        pad = 3 * MM_TO_PT
        sx = self.page_w / im.width
        sy = self.page_h / im.height
        self.canvas.set_area(0, QRectF(box[0] * sx - pad, box[1] * sy - pad,
                                       (box[2] - box[0]) * sx + 2 * pad,
                                       (box[3] - box[1]) * sy + 2 * pad))

    def auto_two(self):
        a, b = find_two_sheets(self.page)
        if self.canvas.link_sizes:
            w, h = max(a.width, b.width), max(a.height, b.height)
            a = fitz.Rect(a.x0, a.y0, a.x0 + w, a.y0 + h)
            b = fitz.Rect(b.x0, b.y0, b.x0 + w, b.y0 + h)
        link, self.canvas.link_sizes = self.canvas.link_sizes, False
        self.canvas.set_area(0, QRectF(a.x0, a.y0, a.width, a.height))
        self.canvas.set_area(1, QRectF(b.x0, b.y0, b.width, b.height))
        self.canvas.link_sizes = link

    def _halves(self, vertical):
        link, self.canvas.link_sizes = self.canvas.link_sizes, False
        try:
            self._halves_do(vertical)
        finally:
            self.canvas.link_sizes = link

    def _halves_do(self, vertical):
        if vertical:
            self.canvas.set_area(0, QRectF(0, 0, self.page_w, self.page_h / 2))
            self.canvas.set_area(1, QRectF(0, self.page_h / 2, self.page_w, self.page_h / 2))
        else:
            self.canvas.set_area(0, QRectF(0, 0, self.page_w / 2, self.page_h))
            self.canvas.set_area(1, QRectF(self.page_w / 2, 0, self.page_w / 2, self.page_h))

    # --- шаблоны -----------------------------------------------------
    def _reload_templates(self, select=None):
        self.cmb_tpl.blockSignals(True)
        self.cmb_tpl.clear()
        self.cmb_tpl.addItem("— выбрать шаблон —", None)
        for t in crop_templates_load(self.mode):
            r0 = t["rects"][0]
            label = f'{t["name"]}  ({r0["w"]:.0f}×{r0["h"]:.0f} мм)'
            self.cmb_tpl.addItem(label, t)
            if select and t["name"] == select:
                self.cmb_tpl.setCurrentIndex(self.cmb_tpl.count() - 1)
        self.cmb_tpl.blockSignals(False)

    def _apply_template(self, index):
        t = self.cmb_tpl.itemData(index)
        if not t:
            return
        link, self.canvas.link_sizes = self.canvas.link_sizes, False
        for i, r in enumerate(t["rects"][:len(self.canvas.areas)]):
            self.canvas.set_area(i, QRectF(r["x"] * MM_TO_PT, r["y"] * MM_TO_PT,
                                           r["w"] * MM_TO_PT, r["h"] * MM_TO_PT))
        self.canvas.link_sizes = link
        self._from_canvas()

    def _save_template(self):
        cur = self.cmb_tpl.currentData()
        name, ok = QInputDialog.getText(self, "Шаблон", "Название шаблона:",
                                        text=cur["name"] if cur else "")
        name = (name or "").strip()
        if not ok or not name:
            return
        rects = []
        for r in self.canvas.areas:
            rects.append((r.x() / MM_TO_PT, r.y() / MM_TO_PT, r.width() / MM_TO_PT, r.height() / MM_TO_PT))
        try:
            crop_template_add(name, self.mode, rects)
        except Exception as e:
            QMessageBox.warning(self, "Не сохранилось", f"Не удалось записать шаблон:\n{e}")
            return
        self._reload_templates(select=name)

    def _delete_template(self):
        t = self.cmb_tpl.currentData()
        if not t:
            QMessageBox.information(self, "Шаблон", "Сначала выберите шаблон в списке.")
            return
        if QMessageBox.question(self, "Удалить шаблон", f"Удалить шаблон «{t['name']}»?") != QMessageBox.Yes:
            return
        crop_template_remove(t["name"], self.mode)
        self._reload_templates()

    # --- результат ---------------------------------------------------
    def selected_rects(self):
        """Рамки в pt в координатах страницы, как она видна."""
        return [fitz.Rect(r.x(), r.y(), r.x() + r.width(), r.y() + r.height())
                for r in self.canvas.areas]

    def split_options(self):
        o = {"place": self.cmb_place.currentData(), "rot": int(self.cmb_rot.currentData()),
             "dpi": int(self.cmb_dpi.currentData()), "bg": self.cmb_bg.currentData(),
             "bg_file": self.bg_path or ""}
        if o["bg"] == "file" and not (o["bg_file"] and os.path.isfile(o["bg_file"])):
            o["bg"] = "builtin"
        try:
            s = settings_load()
            s["split_opts"] = o
            settings_save(s)
        except Exception:
            pass
        return o


def page_cropbox_for_visible_rect(page, rect):
    """Перевести прямоугольник, выделенный на странице как она видна (с учётом поворота
    и уже сделанной обрезки), в cropbox для page.set_cropbox()."""
    r = fitz.Rect(rect) * page.derotation_matrix
    r.normalize()
    cb = page.cropbox
    return fitz.Rect(r.x0 + cb.x0, r.y0 + cb.y0, r.x1 + cb.x0, r.y1 + cb.y0)



# ======================================================================
#  «Как скан»: цифровой документ → будто напечатали и отсканировали
# ======================================================================

SCAN_LOOK_PRESETS = {
    # угол°, размытие, зерно бумаги, самый тёмный тон, затемнение края, сдвиг мм, jpeg
    "light":  dict(angle=0.12, blur=0.40, grain=1.6, ink=50, edge=0.000, shift=0.5, q=84),
    "normal": dict(angle=0.25, blur=0.55, grain=2.2, ink=62, edge=0.006, shift=1.0, q=80),
    "strong": dict(angle=0.60, blur=0.85, grain=3.6, ink=78, edge=0.020, shift=2.2, q=72),
}
SCAN_PAPER_TONE = (231, 234, 239)     # тон бумаги на настоящем скане (образец договора)


def parse_pages(text, n):
    """«1-3, 5, 7» → [0, 1, 2, 4, 6]. Пустой список, если ничего годного."""
    out = []
    for part in str(text).replace(";", ",").replace(" ", "").split(","):
        if not part:
            continue
        try:
            if "-" in part:
                a, b = part.split("-", 1)
                a, b = int(a), int(b)
                if a > b:
                    a, b = b, a
                rng = range(a, b + 1)
            else:
                rng = [int(part)]
        except ValueError:
            return []
        for p in rng:
            if 1 <= p <= n and (p - 1) not in out:
                out.append(p - 1)
    return sorted(out)


def pages_to_text(pages):
    """[0, 1, 2, 4] → «1-3, 5»."""
    pages = sorted(set(pages))
    parts, i = [], 0
    while i < len(pages):
        j = i
        while j + 1 < len(pages) and pages[j + 1] == pages[j] + 1:
            j += 1
        parts.append(f"{pages[i] + 1}-{pages[j] + 1}" if j > i else f"{pages[i] + 1}")
        i = j + 1
    return ", ".join(parts)


def scan_back_page(doc, i, enabled=True):
    """Что могло бы просвечивать с оборота листа: следующая страница (если есть)."""
    return None      # просвет оборота отключён: он давал зеркальный текст и полосы


def scan_look_page(page, dpi=190, preset="normal", color=True, seed=0, back_page=None,
                   show_bed=False, base_page=None):
    """Одна страница → PIL RGB, как будто её распечатали, заверили и отсканировали.

    base_page — та же страница БЕЗ печатей: тогда печать и подпись ложатся отдельным
    слоем «чернил поверх тонера» (умножением), а не как часть распечатки."""
    import random
    rnd = random.Random(seed)
    P = SCAN_LOOK_PRESETS.get(preset, SCAN_LOOK_PRESETS["normal"])
    pix = page.get_pixmap(dpi=dpi, alpha=False)
    full = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    W, H = full.size
    mm = dpi / 25.4
    k = dpi / 190.0

    # печать/подпись отдельно от распечатки
    ink = None
    printed = full
    if base_page is not None:
        try:
            bp = base_page.get_pixmap(dpi=dpi, alpha=False)
            base = Image.frombytes("RGB", (bp.width, bp.height), bp.samples)
            if base.size == full.size:
                diff = ImageChops.difference(full, base).convert("L").point(lambda v: 255 if v > 10 else 0)
                if diff.getbbox():
                    diff = diff.filter(ImageFilter.MaxFilter(3))
                    ink = Image.composite(full, Image.new("RGB", (W, H), (255, 255, 255)), diff)
                    printed = base
        except Exception:
            ink, printed = None, full

    # 1. тонер и бумага: чёрное становится тёмно-серым, белое — тоном бумаги
    pw, lo = SCAN_PAPER_TONE, P["ink"]
    luts = []
    for ch in range(3):
        luts += [int(lo + (pw[ch] - lo) * ((v / 255.0) ** 1.12)) for v in range(256)]
    paper = printed.point(luts)
    paper = ImageEnhance.Color(paper).enhance(0.88)

    # 1а. оборот листа слегка просвечивает
    if back_page is not None:
        try:
            bq = back_page.get_pixmap(dpi=max(40, dpi // 3), alpha=False)
            back = Image.frombytes("RGB", (bq.width, bq.height), bq.samples).convert("L")
            back = back.transpose(Image.FLIP_LEFT_RIGHT).resize((W, H), Image.BILINEAR)
            back = back.filter(ImageFilter.GaussianBlur(1.6 * k))
            back = back.point(lambda v: int(255 - (255 - v) * 0.045))
            paper = ImageChops.multiply(paper, Image.merge("RGB", (back, back, back)))
        except Exception:
            pass

    # 1б. чернила печати и подписи поверх тонера
    if ink is not None:
        try:
            ink = ink.filter(ImageFilter.GaussianBlur(0.35 * k))
            # неравномерный оттиск: местами бледнее
            blot = Image.effect_noise((max(8, W // 14), max(8, H // 14)), 26).resize((W, H), Image.BICUBIC)
            blot = blot.point(lambda v: max(0, min(60, (v - 128) + 18)))
            ink = ImageChops.add(ink, Image.merge("RGB", (blot, blot, blot)))
            paper = ImageChops.multiply(paper, ink)
        except Exception:
            pass

    # 2. оптика сканера: мягкость букв
    paper = paper.filter(ImageFilter.GaussianBlur(P["blur"] * k))

    # 3. фактура бумаги: крупные «облака» + мелкое зерно
    try:
        fine = Image.effect_noise((W, H), P["grain"])
        paper = ImageChops.add(paper, fine.convert("RGB"), 1.0, -128)
    except Exception:
        pass

    # 4. настоящие пылинки и разводы стекла — из встроенного пустого скана
    bed = builtin_scanner_bg()
    if bed is not None:
        bed = bed.resize((W, H), Image.LANCZOS)
        if rnd.random() < 0.5:
            bed = bed.transpose(Image.FLIP_LEFT_RIGHT)
        if rnd.random() < 0.5:
            bed = bed.transpose(Image.FLIP_TOP_BOTTOM)
        gray = bed.convert("L")
        smooth = gray.filter(ImageFilter.GaussianBlur(14 * k))
        # разница со сглаженной копией = только пылинки; полосы и тени стекла уходят
        specks = ImageChops.subtract(smooth, gray)              # >0 там, где точка темнее фона
        specks = specks.point(lambda v: 0 if v < 7 else min(255, int(v * 1.6)))
        dust = ImageChops.invert(specks)
        paper = ImageChops.multiply(paper, Image.merge("RGB", (dust, dust, dust)))

    # 5. один край листа темнее (крышка сканера прижата неравномерно)
    try:
        grad = Image.linear_gradient("L").resize((W, H))          # сверху 0 → снизу 255
        side = rnd.choice((0, 1, 2, 3))
        if side == 1:
            grad = grad.transpose(Image.FLIP_TOP_BOTTOM)
        elif side == 2:
            grad = grad.transpose(Image.ROTATE_90).resize((W, H))
        elif side == 3:
            grad = grad.transpose(Image.ROTATE_270).resize((W, H))
        e = P["edge"]
        grad = grad.point(lambda v: int(255 * (1.0 - e * (v / 255.0) ** 3)))
        paper = ImageChops.multiply(paper, Image.merge("RGB", (grad, grad, grad)))
    except Exception:
        pass

    try:
        med = ImageStat.Stat(paper.resize((64, 64))).median
        offs = [int(SCAN_PAPER_TONE[i] - med[i]) for i in range(3)]
        if any(offs):
            lut = []
            for i in range(3):
                lut += [max(0, min(255, v + offs[i])) for v in range(256)]
            paper = paper.point(lut)
    except Exception:
        pass

    ang = rnd.uniform(0.4, 1.0) * P["angle"] * rnd.choice((-1, 1))
    dx = int(rnd.uniform(-1, 1) * P["shift"] * mm)
    dy = int(rnd.uniform(-1, 1) * P["shift"] * mm)
    if not show_bed:
        # лист закрывает всё стекло: лёгкий наклон и сдвиг, края не видны
        tone = tuple(int(v) for v in ImageStat.Stat(paper.resize((32, 32))).median)
        out = paper.rotate(ang, resample=Image.BICUBIC, translate=(dx, dy), fillcolor=tone)
    else:
        # видно стекло по краям: лист чуть меньше, с тенью
        glass = (bed if bed is not None else synth_scanner_bg(W, H, mm)).copy()
        sw, sh = int(W * 0.985), int(H * 0.985)
        sheet = paper.resize((sw, sh), Image.LANCZOS).convert("RGBA")
        sheet = sheet.rotate(ang, resample=Image.BICUBIC, expand=True)
        alpha = sheet.getchannel("A")
        ox, oy = (W - sheet.width) // 2 + dx, (H - sheet.height) // 2 + dy
        try:
            shadow = Image.new("L", (W, H), 0)
            shadow.paste(alpha.point(lambda a: 90 if a > 128 else 0), (ox + 2, oy + 3))
            shadow = shadow.filter(ImageFilter.GaussianBlur(3 * k))
            darker = ImageChops.multiply(glass, Image.new("RGB", (W, H), (150, 150, 150)))
            glass = Image.composite(darker, glass, shadow)
        except Exception:
            pass
        glass.paste(sheet.convert("RGB"), (ox, oy), alpha)
        out = glass
    if not color:
        out = out.convert("L").convert("RGB")
    return out


def build_scan_look_doc(src_doc, pages=None, dpi=190, preset="normal", color=True, seed=0,
                        progress=None, show_bed=False, show_back=True, base_doc=None):
    """Документ, где выбранные страницы заменены «отсканированными»."""
    P = SCAN_LOOK_PRESETS.get(preset, SCAN_LOOK_PRESETS["normal"])
    pages = list(range(src_doc.page_count)) if pages is None else list(pages)
    out = fitz.open()
    for i in range(src_doc.page_count):
        if progress:
            progress(i)
        page = src_doc[i]
        if i not in pages:
            out.insert_pdf(src_doc, from_page=i, to_page=i)
            continue
        im = scan_look_page(page, dpi, preset, color, seed * 1000 + i,
                            scan_back_page(src_doc, i, show_back), show_bed,
                            base_doc[i] if base_doc is not None else None)
        buf = io.BytesIO()
        (im if color else im.convert("L")).save(buf, "JPEG", quality=P["q"], optimize=True)
        np_ = out.new_page(width=page.rect.width, height=page.rect.height)
        np_.insert_image(np_.rect, stream=buf.getvalue())
    return out


class ScanLookDialog(QDialog):
    """Окно «Сделать как скан» с живым превью текущей страницы."""

    def __init__(self, src_doc, page_index, parent=None, base_doc=None, preselect=None):
        super().__init__(parent)
        self.setWindowTitle("Сделать как скан")
        self.src_doc = src_doc
        self.base_doc = base_doc
        self.page_index = page_index
        self.seed = int(time.time()) % 100000
        st = settings_load().get("scan_look", {})

        root = QHBoxLayout(self)
        root.setSpacing(12)
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumSize(480, 600)
        self.preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        root.addWidget(self.preview, 1)

        side = QVBoxLayout()
        side.setSpacing(8)
        hint = QLabel("Порядок как в жизни: документ напечатан → на нём печать и подпись "
                      "→ скан. Поэтому сначала поставьте печать и подпись, потом жмите "
                      "сюда — они окажутся на бумаге и «отсканируются» вместе с листом.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        side.addWidget(hint)

        box = QGroupBox("Настройки")
        form = QFormLayout(box)
        form.setSpacing(8)
        self.cmb_preset = QComboBox()
        self.cmb_preset.addItem("лёгкий — почти ровно", "light")
        self.cmb_preset.addItem("обычный — как в офисе", "normal")
        self.cmb_preset.addItem("сильный — уставший сканер", "strong")
        form.addRow("Эффект:", self.cmb_preset)
        self.cmb_color = QComboBox()
        self.cmb_color.addItem("цветной (печати синие)", True)
        self.cmb_color.addItem("чёрно-белый", False)
        form.addRow("Цвет:", self.cmb_color)
        self.cmb_dpi = QComboBox()
        for d, t in ((150, "150 dpi"), (190, "190 dpi — как обычный скан"), (300, "300 dpi")):
            self.cmb_dpi.addItem(t, d)
        form.addRow("Качество:", self.cmb_dpi)
        side.addWidget(box)
        self.chk_bed = QCheckBox("видно стекло сканера по краям листа")
        self.chk_bed.setChecked(bool(st.get("bed", False)))
        self.chk_bed.toggled.connect(self.update_preview)
        side.addWidget(self.chk_bed)

        for cmb, key, default in ((self.cmb_preset, "preset", "normal"),
                                  (self.cmb_color, "color", True),
                                  (self.cmb_dpi, "dpi", 190)):
            k = cmb.findData(st.get(key, default))
            cmb.setCurrentIndex(k if k >= 0 else 0)
            cmb.currentIndexChanged.connect(self.update_preview)

        b_again = QPushButton("Другой вариант наклона")
        b_again.setToolTip("Каждый «скан» чуть отличается — нажмите, чтобы перебросить")
        b_again.clicked.connect(self._reroll)
        side.addWidget(b_again)

        pbox = QGroupBox("Какие страницы")
        pl = QVBoxLayout(pbox)
        pl.setSpacing(6)
        n = self.src_doc.page_count
        self.cmb_pages = QComboBox()
        self.cmb_pages.addItem(f"все страницы ({n})", "all")
        self.cmb_pages.addItem(f"только текущая (стр. {self.page_index + 1})", "current")
        self.cmb_pages.addItem("выбранные…", "custom")
        pl.addWidget(self.cmb_pages)
        self.ed_pages = QLineEdit()
        self.ed_pages.setPlaceholderText("например: 1-3, 5, 7")
        self.ed_pages.setMinimumHeight(28)
        self.ed_pages.setToolTip("Номера страниц через запятую, диапазоны через дефис")
        pl.addWidget(self.ed_pages)
        self.lbl_pages = QLabel("")
        self.lbl_pages.setObjectName("hint")
        pl.addWidget(self.lbl_pages)
        side.addWidget(pbox)
        if preselect and len(preselect) > 1:
            self.cmb_pages.setCurrentIndex(2)
            self.ed_pages.setText(pages_to_text(preselect))
        elif n > 1 and st.get("pages_mode") == "current":
            self.cmb_pages.setCurrentIndex(1)
        self.cmb_pages.currentIndexChanged.connect(self._pages_changed)
        self.ed_pages.textChanged.connect(self._pages_changed)
        self._pages_changed()
        side.addStretch(1)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Сделать как скан")
        bb.button(QDialogButtonBox.Cancel).setText("Отмена")
        self._ok_btn = bb.button(QDialogButtonBox.Ok)
        self._ok_btn.setObjectName("primary")
        self._pages_changed()
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        side.addWidget(bb)
        for b in self.findChildren(QPushButton):
            b.setMinimumHeight(30)
        for c in self.findChildren(QComboBox):
            c.setMinimumHeight(28)
            c.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
            c.setMinimumContentsLength(14)

        sidew = QWidget()
        sidew.setLayout(side)
        sidew.setFixedWidth(380)
        root.addWidget(sidew)
        self.resize(990, 720)
        self.update_preview()

    def _reroll(self):
        self.seed = (self.seed * 7 + 13) % 100000
        self.update_preview()

    def selected_pages(self):
        """Список индексов страниц (с нуля) или None, если ввод неверный."""
        mode = self.cmb_pages.currentData()
        n = self.src_doc.page_count
        if mode == "all":
            return list(range(n))
        if mode == "current":
            return [self.page_index]
        return parse_pages(self.ed_pages.text(), n)

    def _pages_changed(self, *_):
        custom = self.cmb_pages.currentData() == "custom"
        self.ed_pages.setVisible(custom)
        pages = self.selected_pages()
        ok_btn = getattr(self, "_ok_btn", None)
        if pages:
            self.lbl_pages.setText(f"будет обработано страниц: {len(pages)}")
        else:
            self.lbl_pages.setText("введите номера страниц, например 1-3, 5")
        if ok_btn is not None:
            ok_btn.setEnabled(bool(pages))

    def update_preview(self, *_):
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            im = scan_look_page(self.src_doc[self.page_index], 90,
                                self.cmb_preset.currentData(),
                                bool(self.cmb_color.currentData()),
                                self.seed * 1000 + self.page_index,
                                None,
                                self.chk_bed.isChecked(),
                                self.base_doc[self.page_index] if self.base_doc is not None else None)
            data = im.tobytes("raw", "RGB")
            qi = QImage(data, im.width, im.height, im.width * 3, QImage.Format_RGB888).copy()
            pm = QPixmap.fromImage(qi)
            self.preview.setPixmap(pm.scaled(self.preview.size() * 0.98, Qt.KeepAspectRatio,
                                             Qt.SmoothTransformation))
        except Exception as e:
            self.preview.setText(f"Не удалось построить превью:\n{e}")
        finally:
            QApplication.restoreOverrideCursor()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if getattr(self, "_shown", False):
            self.update_preview()

    def showEvent(self, e):
        super().showEvent(e)
        self._shown = True

    def _ok(self):
        try:
            s = settings_load()
            o = self.options()
            o.pop("pages", None)
            s["scan_look"] = o
            settings_save(s)
        except Exception:
            pass
        self.accept()

    def options(self):
        return {"preset": self.cmb_preset.currentData(),
                "color": bool(self.cmb_color.currentData()),
                "dpi": int(self.cmb_dpi.currentData()),
                "pages": self.selected_pages(),
                "pages_mode": self.cmb_pages.currentData(),
                "bed": self.chk_bed.isChecked(),
                "seed": self.seed}



# ======================================================================
#  Автообновление: version.json в репозитории → установщик из GitHub Releases
# ======================================================================

class UpdateCheckThread(QThread):
    result = Signal(object, str)        # (данные version.json или None, текст ошибки)

    def run(self):
        try:
            import urllib.request
            req = urllib.request.Request(f"{UPDATE_URL}?t={int(time.time())}",
                                         headers={"User-Agent": "StampStudio-Updater"})
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            self.result.emit(data, "")
        except Exception as e:
            self.result.emit(None, str(e))


class UpdateDownloadThread(QThread):
    progress = Signal(int, int)         # скачано, всего (байт)
    done = Signal(str, str)             # путь к файлу, текст ошибки

    def __init__(self, url, dest, parent=None):
        super().__init__(parent)
        self.url, self.dest = url, dest
        self.cancelled = False

    def run(self):
        try:
            import urllib.request
            os.makedirs(os.path.dirname(self.dest), exist_ok=True)
            req = urllib.request.Request(self.url, headers={"User-Agent": "StampStudio-Updater"})
            tmp = self.dest + ".part"
            with urllib.request.urlopen(req, timeout=60) as resp, open(tmp, "wb") as f:
                total = int(resp.headers.get("Content-Length") or 0)
                got = 0
                while True:
                    if self.cancelled:
                        raise RuntimeError("отменено")
                    chunk = resp.read(262144)
                    if not chunk:
                        break
                    f.write(chunk)
                    got += len(chunk)
                    self.progress.emit(got, total)
            if os.path.getsize(tmp) < 1_000_000:
                raise RuntimeError("скачанный файл подозрительно мал")
            os.replace(tmp, self.dest)
            self.done.emit(self.dest, "")
        except Exception as e:
            try:
                os.remove(self.dest + ".part")
            except OSError:
                pass
            self.done.emit("", str(e))


class UpdateDialog(QDialog):
    """«Вышла новая версия»: что нового + Обновить / Позже."""

    def __init__(self, info, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Обновление Stamp Studio")
        self.setMinimumWidth(520)
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        head = QLabel(f"Вышла версия {info.get('version', '?')}")
        f = head.font()
        f.setPointSize(f.pointSize() + 4)
        f.setBold(True)
        head.setFont(f)
        lay.addWidget(head)
        sub = QLabel(f"У вас установлена {APP_VERSION}. Обновление займёт около минуты, "
                     "программа перезапустится сама. Печати и настройки сохранятся.")
        sub.setObjectName("hint")
        sub.setWordWrap(True)
        lay.addWidget(sub)
        notes = (info.get("notes") or "").strip()
        if notes:
            box = QGroupBox("Что нового")
            bl = QVBoxLayout(box)
            t = QLabel(notes)
            t.setWordWrap(True)
            t.setTextInteractionFlags(Qt.TextSelectableByMouse)
            bl.addWidget(t)
            lay.addWidget(box)
        self.chk_auto = QCheckBox("проверять обновления при запуске")
        self.chk_auto.setChecked(bool(settings_load().get("auto_update", True)))
        lay.addWidget(self.chk_auto)
        bb = QDialogButtonBox()
        self.b_now = bb.addButton("Обновить сейчас", QDialogButtonBox.AcceptRole)
        self.b_later = bb.addButton("Позже", QDialogButtonBox.RejectRole)
        self.b_now.setObjectName("primary")
        for b in (self.b_now, self.b_later):
            b.setMinimumHeight(34)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def done(self, r):
        try:
            s = settings_load()
            s["auto_update"] = self.chk_auto.isChecked()
            settings_save(s)
        except Exception:
            pass
        super().done(r)


def apply_update_installer(path):
    """Тихо поставить скачанный установщик и запустить новую версию."""
    exe = sys.executable
    bat = os.path.join(os.path.dirname(path), "apply_update.bat")
    with open(bat, "w", encoding="cp866", errors="replace") as f:
        f.write("@echo off\r\ntimeout /t 1 >nul\r\n"
                f'start /wait "" "{path}" /SILENT /CLOSEAPPLICATIONS /NORESTART\r\n'
                f'start "" "{exe}"\r\ndel "{path}" 2>nul\r\ndel "%%~f0"\r\n'.replace("%%", "%"))
    subprocess.Popen(["cmd", "/c", bat],
                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))



# ======================================================================
#  Справка: иллюстрированное руководство внутри программы
# ======================================================================

class GuideDialog(QDialog):
    """Окно справки: слева разделы, справа страница с картинками."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Stamp Studio — как пользоваться")
        self.resize(1080, 760)
        self.setMinimumSize(820, 560)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.nav = QListWidget()
        self.nav.setObjectName("guidenav")
        self.nav.setFixedWidth(250)
        self.nav.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        lay.addWidget(self.nav)
        self.view = QTextBrowser()
        self.view.setObjectName("guide")
        self.view.setOpenExternalLinks(True)
        lay.addWidget(self.view, 1)

        self.sections = []
        index = find_resource(os.path.join("docs", "guide.json"))
        base = os.path.dirname(index) if index else ""
        try:
            with open(index, encoding="utf-8") as f:
                self.sections = json.load(f)
        except Exception:
            self.sections = []
        if base:
            self.view.setSearchPaths([base])
        if not self.sections:
            self.view.setHtml("<h2>Справка не найдена</h2><p>Файлы руководства лежат в папке "
                              "<b>docs</b> рядом с программой. Переустановите программу или "
                              f"откройте руководство на сайте: <a href='{GITHUB_URL}'>{GITHUB_URL}</a></p>")
            return
        for sec in self.sections:
            self.nav.addItem(sec.get("title", ""))
        self.nav.currentRowChanged.connect(self._show)
        self.nav.setCurrentRow(0)

    def _show(self, row):
        if not (0 <= row < len(self.sections)):
            return
        dark = settings_load().get("theme", "light") == "dark"
        fg, mute, gold, card = (("#e8e6e1", "#9aa0b4", "#e8b04b", "#232735") if dark
                                else ("#2b2820", "#6b6553", "#a8730c", "#f6f3ec"))
        css = (f"<style>body {{ color: {fg}; }} h1 {{ color: {gold}; font-size: 22px; margin-top: 14px; }}"
               f" h2 {{ font-size: 16px; margin-top: 18px; }} p, li {{ line-height: 150%; }}"
               f" .note {{ color: {mute}; }} .key {{ color: {gold}; font-weight: bold; }}"
               f" td.tip {{ background: {card}; padding: 10px 14px; }}</style>")
        self.view.setHtml(css + self.sections[row].get("html", ""))
        self.view.verticalScrollBar().setValue(0)


# ====================================================================== ИИ-помощник: окна

class AiThread(QThread):
    """Запрос к ИИ в фоне: fn(status, cancelled) → результат."""
    done = Signal(object)
    failed = Signal(str)
    status = Signal(str)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self.fn = fn
        self.cancelled = False

    def run(self):
        try:
            res = self.fn(self.status.emit, lambda: self.cancelled)
            if not self.cancelled:
                self.done.emit(res)
        except AI.AiCancelled:
            pass
        except AI.AiError as e:
            if not self.cancelled:
                self.failed.emit(str(e))
        except Exception as e:
            if not self.cancelled:
                self.failed.emit(f"{type(e).__name__}: {e}")


class AiBusyDialog(QDialog):
    """Небольшое окно ожидания с кнопкой «Отмена»."""

    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ИИ-помощник")
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.setModal(True)
        self.setMinimumWidth(420)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 16)
        lay.setSpacing(10)
        head = QLabel(title)
        head.setObjectName("aihead")
        head.setWordWrap(True)
        lay.addWidget(head)
        self.bar = QProgressBar()
        self.bar.setRange(0, 0)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(6)
        lay.addWidget(self.bar)
        self.lbl = QLabel("Готовлю документ…")
        self.lbl.setObjectName("hint")
        lay.addWidget(self.lbl)
        row = QHBoxLayout()
        row.addStretch(1)
        b = QPushButton("Отмена")
        b.clicked.connect(self.reject)
        row.addWidget(b)
        lay.addLayout(row)

    def set_status(self, text):
        self.lbl.setText(text)


class AiSettingsDialog(QDialog):
    """Ключи и поведение ИИ: провайдеры, проверка ключа, автоматический режим."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Настройки ИИ")
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.resize(860, 600)
        self.setMinimumSize(820, 580)
        s = settings_load()
        self.keys = dict(s.get("ai_keys") or {})
        self.models = dict(s.get("ai_models") or {})
        self.custom_url = s.get("ai_custom_url", "")
        self.chosen = s.get("ai_provider") or AI.default_provider(s)
        self._cur = None
        self._test_thread = None

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(12)

        # ---- переключатель страниц
        seg = QHBoxLayout()
        seg.setSpacing(6)
        self.seg_btns = []
        for i, text in enumerate(("Сервисы и ключи", "Автоматика и правила")):
            b = QPushButton(text)
            b.setObjectName("seg")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, n=i: self._page(n))
            seg.addWidget(b)
            self.seg_btns.append(b)
        seg.addStretch(1)
        root.addLayout(seg)
        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)

        # ================= страница 1: сервисы
        page1 = QWidget()
        top = QHBoxLayout(page1)
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(14)
        self.lst = QListWidget()
        self.lst.setObjectName("ailist")
        self.lst.setFixedWidth(250)
        self.lst.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        top.addWidget(self.lst)

        card = QGroupBox("Сервис")
        cl = QVBoxLayout(card)
        cl.setSpacing(8)
        self.lbl_name = QLabel("")
        self.lbl_name.setObjectName("aihead")
        cl.addWidget(self.lbl_name)
        self.lbl_best = QLabel("")
        self.lbl_best.setObjectName("plain")
        self.lbl_best.setWordWrap(True)
        self.lbl_best.setTextFormat(Qt.RichText)
        self.lbl_best.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.lbl_best.setMinimumHeight(96)
        cl.addWidget(self.lbl_best)
        self.lbl_count = QLabel("")
        self.lbl_count.setObjectName("hint")
        cl.addWidget(self.lbl_count)
        cl.addSpacing(4)

        self.lbl_url = QLabel("Адрес сервиса")
        self.lbl_url.setObjectName("plain")
        cl.addWidget(self.lbl_url)
        self.ed_url = QLineEdit()
        self.ed_url.setPlaceholderText("https://…/v1/chat/completions")
        self.ed_url.setMinimumHeight(32)
        cl.addWidget(self.ed_url)

        self.lbl_key = QLabel("Ключ API")
        self.lbl_key.setObjectName("plain")
        cl.addWidget(self.lbl_key)
        krow = QHBoxLayout()
        krow.setSpacing(6)
        self.ed_key = QLineEdit()
        self.ed_key.setEchoMode(QLineEdit.Password)
        self.ed_key.setMinimumHeight(32)
        krow.addWidget(self.ed_key, 1)
        self.btn_eye = QPushButton("Показать")
        self.btn_eye.setCheckable(True)
        self.btn_eye.toggled.connect(self._eye)
        krow.addWidget(self.btn_eye)
        self.btn_get = QPushButton("Получить ключ ↗")
        self.btn_get.setToolTip("Откроется страница сервиса, где создаётся бесплатный ключ")
        self.btn_get.clicked.connect(self._open_key_page)
        krow.addWidget(self.btn_get)
        cl.addLayout(krow)

        lbl_m = QLabel("Модель")
        lbl_m.setObjectName("plain")
        cl.addWidget(lbl_m)
        self.ed_model = QLineEdit()
        self.ed_model.setMinimumHeight(32)
        cl.addWidget(self.ed_model)
        hint = QLabel("Оставьте пустым — программа сама подберёт модель, которая понимает сканы.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        cl.addWidget(hint)
        cl.addSpacing(4)

        trow = QHBoxLayout()
        trow.setSpacing(8)
        self.btn_test = QPushButton("Проверить")
        self.btn_test.setToolTip("Отправить короткий пробный запрос: текст и маленькую картинку")
        self.btn_test.clicked.connect(self._test)
        trow.addWidget(self.btn_test)
        self.btn_main = QPushButton("Сделать основным")
        self.btn_main.setObjectName("primary")
        self.btn_main.clicked.connect(self._make_main)
        trow.addWidget(self.btn_main)
        trow.addStretch(1)
        cl.addLayout(trow)
        self.lbl_test = QLabel("")
        self.lbl_test.setObjectName("plain")
        self.lbl_test.setWordWrap(True)
        self.lbl_test.setMinimumHeight(38)
        self.lbl_test.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.lbl_test.setTextInteractionFlags(Qt.TextSelectableByMouse)
        cl.addWidget(self.lbl_test)
        cl.addStretch(1)
        top.addWidget(card, 1)
        self.stack.addWidget(page1)

        # ================= страница 2: автоматика и правила
        page2 = QWidget()
        p2 = QVBoxLayout(page2)
        p2.setContentsMargins(0, 0, 0, 0)
        p2.setSpacing(12)
        auto = QGroupBox("Автоматический режим")
        al = QVBoxLayout(auto)
        al.setSpacing(8)
        self.chk_auto = QCheckBox("Работать автоматически — то же, что галочка в меню «ИИ»")
        self.chk_auto.setChecked(bool(s.get("ai_auto", False)))
        al.addWidget(self.chk_auto)
        sub = QVBoxLayout()
        sub.setContentsMargins(26, 0, 0, 0)
        sub.setSpacing(8)
        self.chk_auto_name = QCheckBox("имя файла подставляется само в окне «Сохранить как»")
        self.chk_auto_name.setChecked(bool(s.get("ai_auto_name", True)))
        sub.addWidget(self.chk_auto_name)
        self.chk_auto_ocr = QCheckBox("текст распознаётся сразу после сканирования")
        self.chk_auto_ocr.setChecked(bool(s.get("ai_auto_ocr", True)))
        sub.addWidget(self.chk_auto_ocr)
        al.addLayout(sub)
        off = QLabel("Когда галочка снята, ИИ работает только по вашей команде из меню «ИИ».")
        off.setObjectName("hint")
        off.setWordWrap(True)
        al.addWidget(off)
        self.chk_auto.toggled.connect(self._sync_auto)
        p2.addWidget(auto)

        rules = QGroupBox("Правила")
        g = QGridLayout(rules)
        g.setHorizontalSpacing(14)
        g.setVerticalSpacing(10)

        def cap(text):
            l = QLabel(text)
            l.setObjectName("plain")
            return l
        g.addWidget(cap("Имя файла по правилу"), 0, 0)
        self.ed_rule = QLineEdit(s.get("ai_name_rule") or AI.DEFAULT_NAME_RULE)
        self.ed_rule.setMinimumHeight(32)
        self.ed_rule.setToolTip("Опишите словами, из чего собирать имя. Пример результата: «CMR №597 Иванов 26.09.2026»")
        g.addWidget(self.ed_rule, 0, 1)
        g.addWidget(cap("Какие данные выписывать"), 1, 0)
        self.ed_fields = QLineEdit(s.get("ai_fields") or AI.DEFAULT_FIELDS)
        self.ed_fields.setMinimumHeight(32)
        self.ed_fields.setCursorPosition(0)
        self.ed_fields.setToolTip("Через запятую. Эти же поля станут столбцами таблицы.")
        g.addWidget(self.ed_fields, 1, 1)
        g.addWidget(cap("Распознавание текста"), 2, 0)
        orow = QHBoxLayout()
        orow.setSpacing(8)
        self.cmb_ocr = QComboBox()
        self.cmb_ocr.setMinimumHeight(32)
        win = AI.win_ocr_available()
        self.cmb_ocr.addItem("Авто — Windows, а если его нет — ИИ", "auto")
        self.cmb_ocr.addItem("Windows — на этом компьютере, без интернета" + ("" if win else " (недоступно)"), "windows")
        self.cmb_ocr.addItem("ИИ — через интернет, медленнее", "ai")
        i = self.cmb_ocr.findData(s.get("ai_ocr_engine", "auto"))
        self.cmb_ocr.setCurrentIndex(max(0, i))
        orow.addWidget(self.cmb_ocr, 1)
        self.cmb_lang = QComboBox()
        self.cmb_lang.setMinimumHeight(32)
        self.cmb_lang.setMinimumWidth(120)
        self.cmb_lang.addItem("язык: авто", "auto")
        for tag in AI.win_ocr_languages():
            self.cmb_lang.addItem(tag, tag)
        i = self.cmb_lang.findData(s.get("ai_ocr_lang", "auto"))
        self.cmb_lang.setCurrentIndex(max(0, i))
        self.cmb_lang.setEnabled(win)
        orow.addWidget(self.cmb_lang)
        g.addLayout(orow, 2, 1)
        g.setColumnStretch(1, 1)
        p2.addWidget(rules)
        p2.addStretch(1)
        self.stack.addWidget(page2)

        note = QLabel("Когда работает ИИ, текст или изображение страниц уходит в выбранный сервис через интернет. "
                      "Для документов, которые нельзя никому показывать, ИИ не используйте. "
                      "Распознавание «Windows» и поиск «М.П.» в документах с текстом работают на компьютере.")
        note.setObjectName("hint")
        note.setWordWrap(True)
        root.addWidget(note)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Сохранить")
        bb.button(QDialogButtonBox.Cancel).setText("Отмена")
        bb.accepted.connect(self._save)
        bb.rejected.connect(self.reject)
        root.addWidget(bb)

        self._page(0)
        self._fill_list()
        self.lst.currentRowChanged.connect(self._show)
        self.select(self.chosen)
        self._sync_auto()

    def _page(self, n):
        self.stack.setCurrentIndex(n)
        for i, b in enumerate(self.seg_btns):
            b.setChecked(i == n)

    # ---- список
    def _state(self, p):
        if p.get("custom"):
            return "адрес задан" if self.custom_url.strip() else "не настроен"
        if p.get("nokey"):
            return "ключ не нужен"
        if self.keys.get(p["name"], "").strip():
            return "свой ключ"
        if AI.builtin_keys().get(p["name"]):
            return "встроенный ключ"
        return "нужен ключ"

    def _connected(self, p):
        return self._state(p) not in ("нужен ключ", "не настроен")

    def _fill_list(self):
        """Сначала подключённые (с ключом), потом доступные; внутри — по рейтингу."""
        self.lst.blockSignals(True)
        self.lst.clear()
        ranked = sorted(AI.PROVIDERS, key=lambda p: -p["stars"])
        groups = (("ПОДКЛЮЧЕНЫ", [p for p in ranked if self._connected(p)]),
                  ("ДОСТУПНЫ — НУЖЕН КЛЮЧ", [p for p in ranked if not self._connected(p)]))
        for title, items in groups:
            if not items:
                continue
            head = QListWidgetItem(title)
            head.setFlags(Qt.NoItemFlags)
            head.setData(Qt.UserRole, None)
            f = head.font()
            f.setBold(True)
            f.setPointSizeF(max(7.0, f.pointSizeF() - 1.5))
            head.setFont(f)
            head.setForeground(QColor("#b08a3c"))
            self.lst.addItem(head)
            for p in items:
                on = self._connected(p)
                stars = ("★" * p["stars"] + "☆" * (5 - p["stars"])) if p["stars"] else ""
                mark = "✓ " if on else "+ "
                main = "основной · " if p["name"] == self.chosen else ""
                it = QListWidgetItem(f"{mark}{p['name'].split(' (')[0]}  {stars}\n     {main}{p['short']}")
                it.setData(Qt.UserRole, p["name"])
                it.setToolTip(f"{self._state(p)}\nЛучше всего для: {p['tasks']}\n{p['why']}")
                if not on:
                    it.setForeground(QColor("#9a9486"))
                self.lst.addItem(it)
        self.lst.blockSignals(False)
        self.select(self._cur, show=False)

    def select(self, name, show=True):
        for i in range(self.lst.count()):
            if self.lst.item(i).data(Qt.UserRole) == name:
                self.lst.blockSignals(not show)
                self.lst.setCurrentRow(i)
                self.lst.blockSignals(False)
                return

    def _current(self):
        return AI.provider(self._cur) if self._cur else None

    def _keep(self):
        """Запомнить то, что введено для открытого сервиса."""
        p = self._current()
        if p is None:
            return
        name = p["name"]
        key = self.ed_key.text().strip()
        if key:
            self.keys[name] = key
        else:
            self.keys.pop(name, None)
        m = self.ed_model.text().strip()
        if m:
            self.models[name] = m
        else:
            self.models.pop(name, None)
        if p.get("custom"):
            self.custom_url = self.ed_url.text().strip()

    def _show(self, row):
        item = self.lst.item(row)
        name = item.data(Qt.UserRole) if item is not None else None
        if not name:
            return
        self._keep()
        self._cur = name
        p = self._current()
        self.lbl_name.setText(name.split(" (")[0] + ("   · основной" if name == self.chosen else ""))
        stars = ("★" * p["stars"] + "☆" * (5 - p["stars"]) + "   ") if p["stars"] else ""
        state = self._state(p)
        self.lbl_best.setText(f"{stars}{state}<br><b>Лучше всего для:</b> {p['tasks']}<br>"
                              f"<b>Почему:</b> {p['why']}")
        self.lbl_count.setText(AI.count_text(name))
        custom, nokey = bool(p.get("custom")), bool(p.get("nokey"))
        self.lbl_url.setVisible(custom)
        self.ed_url.setVisible(custom)
        self.ed_url.setText(self.custom_url)
        self.ed_key.setEnabled(not nokey)
        self.ed_key.setText(self.keys.get(name, ""))
        builtin = bool(AI.builtin_keys().get(name))
        self.lbl_key.setText("Ключ API" + (" — необязательно, есть встроенный" if builtin else
                                           " — не нужен" if nokey else ""))
        self.ed_key.setPlaceholderText("встроенный ключ уже работает — сюда можно вписать свой" if builtin
                                       else p["key_hint"])
        self.btn_get.setVisible(bool(p.get("key_url")) and not nokey)
        s = settings_load()
        found = (s.get("ai_models_found") or {}).get(name) or (p["models"][0] if p["models"] else "")
        self.ed_model.setText(self.models.get(name, ""))
        self.ed_model.setPlaceholderText(f"авто: {found}" if found else "название модели")
        self.btn_main.setEnabled(name != self.chosen)
        self.lbl_test.setText("")

    def _eye(self, on):
        self.ed_key.setEchoMode(QLineEdit.Normal if on else QLineEdit.Password)
        self.btn_eye.setText("Скрыть" if on else "Показать")

    def _open_key_page(self):
        p = self._current()
        if p and p.get("key_url"):
            QDesktopServices.openUrl(QUrl(p["key_url"]))

    def _make_main(self):
        p = self._current()
        if p is None:
            return
        self._keep()
        self.chosen = p["name"]
        self._fill_list()
        self._show(self.lst.currentRow())

    def _sync_auto(self):
        on = self.chk_auto.isChecked()
        self.chk_auto_name.setEnabled(on)
        self.chk_auto_ocr.setEnabled(on)

    def _apply(self):
        self._keep()
        s = settings_load()
        s["ai_keys"] = self.keys
        s["ai_models"] = self.models
        s["ai_custom_url"] = self.custom_url
        s["ai_provider"] = self.chosen
        s["ai_auto"] = self.chk_auto.isChecked()
        s["ai_auto_name"] = self.chk_auto_name.isChecked()
        s["ai_auto_ocr"] = self.chk_auto_ocr.isChecked()
        s["ai_name_rule"] = self.ed_rule.text().strip() or AI.DEFAULT_NAME_RULE
        s["ai_fields"] = ", ".join(AI.fields_list(self.ed_fields.text()))
        s["ai_ocr_engine"] = self.cmb_ocr.currentData()
        s["ai_ocr_lang"] = self.cmb_lang.currentData()
        settings_save(s)

    def _test(self):
        p = self._current()
        if p is None or self._test_thread is not None:
            return
        self._apply()
        self._fill_list()
        if not AI.provider_ready(p):
            self.lbl_test.setText("Сначала вставьте ключ" + (" и адрес сервиса." if p.get("custom") else "."))
            return
        name = p["name"]
        self.btn_test.setEnabled(False)
        self.lbl_test.setText("Проверяю… обычно это 5–20 секунд")
        th = AiThread(lambda status, cancelled: AI.test_provider(name), self)
        self._test_thread = th

        def fin(text):
            self._test_thread = None
            self.btn_test.setEnabled(True)
            self.lbl_test.setText(text)
            self.lbl_count.setText(AI.count_text(name))
        th.done.connect(lambda r: fin("✔ " + str(r)))
        th.failed.connect(lambda m: fin("✖ " + m))
        th.start()

    def _save(self):
        self._apply()
        self.accept()

    def reject(self):
        if self._test_thread is not None:
            self._test_thread.cancelled = True
            self._test_thread.wait(200)
        super().reject()


class AiNameDialog(QDialog):
    """Имя файла, предложенное ИИ: поправить и применить."""

    def __init__(self, name, can_rename, source, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Имя файла от ИИ")
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.setMinimumWidth(780)
        self.action = None
        self._can_rename = can_rename
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(10)
        head = QLabel("ИИ прочитал документ и предлагает имя")
        head.setObjectName("aihead")
        lay.addWidget(head)
        row = QHBoxLayout()
        row.setSpacing(6)
        self.edit = QLineEdit(name)
        self.edit.setMinimumHeight(34)
        self.edit.selectAll()
        row.addWidget(self.edit, 1)
        row.addWidget(QLabel(".pdf"))
        lay.addLayout(row)
        src = QLabel(f"Можно поправить вручную. Ответил: {source}")
        src.setObjectName("hint")
        lay.addWidget(src)
        btns = QHBoxLayout()
        btns.setSpacing(8)
        self.b_rename = QPushButton("Переименовать файл")
        self.b_rename.setObjectName("primary")
        self.b_rename.setEnabled(can_rename)
        if not can_rename:
            self.b_rename.setToolTip("Документ ещё не сохранён в файл — нажмите «Сохранить как…»")
        self.b_rename.clicked.connect(lambda: self._done("rename"))
        btns.addWidget(self.b_rename)
        b_as = QPushButton("Сохранить как…")
        if not can_rename:
            b_as.setObjectName("primary")
        b_as.clicked.connect(lambda: self._done("saveas"))
        btns.addWidget(b_as)
        b_copy = QPushButton("Скопировать")
        b_copy.clicked.connect(lambda: self._done("copy"))
        btns.addWidget(b_copy)
        b_again = QPushButton("Другой вариант")
        b_again.setToolTip("Спросить ИИ ещё раз")
        b_again.clicked.connect(lambda: self._done("again"))
        btns.addWidget(b_again)
        btns.addStretch(1)
        b_close = QPushButton("Закрыть")
        b_close.clicked.connect(self.reject)
        btns.addWidget(b_close)
        lay.addLayout(btns)
        self.edit.textChanged.connect(self._check)
        self._check()

    def _check(self):
        ok = bool(AI.clean_filename(self.edit.text()))
        self.b_rename.setEnabled(ok and self._can_rename)

    def name(self):
        return AI.clean_filename(self.edit.text())

    def _done(self, action):
        if not self.name():
            return
        self.action = action
        self.accept()


class AiDataDialog(QDialog):
    """Данные из документа: таблица «поле — значение», копирование, запись в CSV."""

    def __init__(self, result, file_name, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Данные из документа")
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.resize(720, 560)
        self.file_name = file_name
        self.n_main = len(result["fields"])
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)
        head = QLabel(f"Данные из «{file_name}»")
        head.setObjectName("aihead")
        lay.addWidget(head)
        sub = QLabel("Значения можно править двойным щелчком. Сверьте с документом: ИИ иногда ошибается в цифрах. "
                     f"Ответил: {result['provider'].split(' (')[0]}")
        sub.setObjectName("hint")
        sub.setWordWrap(True)
        lay.addWidget(sub)
        rows = list(result["fields"]) + list(result["other"])
        self.tbl = QTableWidget(len(rows), 2)
        self.tbl.setObjectName("aitable")
        self.tbl.setHorizontalHeaderLabels(["Поле", "Значение"])
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.tbl.horizontalHeader().setStretchLastSection(True)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl.setAlternatingRowColors(True)
        self.tbl.setWordWrap(True)
        for r, (k, v) in enumerate(rows):
            a = QTableWidgetItem(k)
            a.setFlags(a.flags() & ~Qt.ItemIsEditable)
            if r >= self.n_main:
                a.setForeground(QColor("#9a9486"))
            self.tbl.setItem(r, 0, a)
            self.tbl.setItem(r, 1, QTableWidgetItem(v))
        self.tbl.resizeRowsToContents()
        self.tbl.setCurrentCell(-1, -1)
        self.tbl.setFocusPolicy(Qt.ClickFocus)
        lay.addWidget(self.tbl, 1)
        btns = QHBoxLayout()
        btns.setSpacing(8)
        b_all = QPushButton("Скопировать всё")
        b_all.setObjectName("primary")
        b_all.setToolTip("Поле и значение через табуляцию — вставляется в Excel двумя столбцами")
        b_all.clicked.connect(self.copy_all)
        btns.addWidget(b_all)
        b_one = QPushButton("Скопировать значение")
        b_one.setToolTip("Только значение выбранной строки")
        b_one.clicked.connect(self.copy_value)
        btns.addWidget(b_one)
        b_csv = QPushButton("Добавить в таблицу…")
        b_csv.setToolTip("Дописать строку в файл-таблицу (CSV, открывается в Excel).\n"
                         "Один документ — одна строка, столбцы — ваши поля.")
        b_csv.clicked.connect(self.to_csv)
        btns.addWidget(b_csv)
        self.b_open = QPushButton("Открыть таблицу")
        self.b_open.clicked.connect(self.open_csv)
        self.b_open.setVisible(bool(settings_load().get("ai_csv_path")))
        btns.addWidget(self.b_open)
        btns.addStretch(1)
        b_close = QPushButton("Закрыть")
        b_close.clicked.connect(self.accept)
        btns.addWidget(b_close)
        lay.addLayout(btns)
        self.lbl = QLabel("")
        self.lbl.setObjectName("hint")
        lay.addWidget(self.lbl)

    def rows(self):
        out = []
        for r in range(self.tbl.rowCount()):
            out.append((self.tbl.item(r, 0).text(), self.tbl.item(r, 1).text().strip()))
        return out

    def copy_all(self):
        QApplication.clipboard().setText("\n".join(f"{k}\t{v}" for k, v in self.rows() if v))
        self.lbl.setText("✔ Скопировано — вставьте в Excel или в сообщение (Ctrl+V)")

    def copy_value(self):
        r = self.tbl.currentRow()
        if r < 0:
            self.lbl.setText("Сначала щёлкните по строке")
            return
        QApplication.clipboard().setText(self.tbl.item(r, 1).text())
        self.lbl.setText(f"✔ Скопировано: {self.tbl.item(r, 0).text()}")

    def to_csv(self):
        import csv
        s = settings_load()
        path = s.get("ai_csv_path") or ""
        if not path or not os.path.isdir(os.path.dirname(path)):
            start = os.path.join(os.path.expanduser("~"), "Documents")
            if not os.path.isdir(start):
                start = os.path.expanduser("~")
            path, _ = QFileDialog.getSaveFileName(
                self, "Таблица для данных", os.path.join(start, "Stamp Studio — данные.csv"),
                "Таблица CSV (*.csv)", options=QFileDialog.DontConfirmOverwrite)
            if not path:
                return
            if not path.lower().endswith(".csv"):
                path += ".csv"
        rows = self.rows()
        main = rows[:self.n_main]
        other = [f"{k}: {v}" for k, v in rows[self.n_main:] if v]
        try:
            header = None
            if os.path.exists(path) and os.path.getsize(path) > 0:
                with open(path, "r", encoding="utf-8-sig", newline="") as f:
                    header = next(csv.reader(f, delimiter=";"), None)
            new_file = not header
            if new_file:
                header = ["Файл", "Добавлено"] + [k for k, _ in main] + ["Прочее"]
            vals = dict(main)
            line = []
            for col in header:
                if col == "Файл":
                    line.append(self.file_name)
                elif col == "Добавлено":
                    line.append(time.strftime("%d.%m.%Y %H:%M"))
                elif col == "Прочее":
                    extra = [f"{k}: {v}" for k, v in main if k not in header and v] + other
                    line.append(" | ".join(extra))
                else:
                    line.append(vals.get(col, ""))
            with open(path, "a", encoding="utf-8-sig" if new_file else "utf-8", newline="") as f:
                w = csv.writer(f, delimiter=";")
                if new_file:
                    w.writerow(header)
                w.writerow(line)
        except PermissionError:
            QMessageBox.warning(self, "Таблица занята",
                                "Файл таблицы открыт в Excel — закройте его и нажмите ещё раз.")
            return
        except Exception as e:
            QMessageBox.warning(self, "Не получилось", f"Не удалось записать таблицу:\n{e}")
            return
        s = settings_load()
        s["ai_csv_path"] = path
        settings_save(s)
        self.b_open.setVisible(True)
        self.lbl.setText(f"✔ Строка добавлена в {os.path.basename(path)}")

    def open_csv(self):
        path = settings_load().get("ai_csv_path") or ""
        if os.path.exists(path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))


class AiCheckDialog(QDialog):
    """Результат проверки документа: список замечаний, двойной щелчок — к странице."""
    go_page = Signal(int)

    def __init__(self, result, file_name, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Проверка документа")
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.resize(680, 520)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)
        issues = result["issues"]
        errs = sum(1 for i in issues if i["severity"] == "error")
        if not issues:
            title = "✔ Проблем не найдено"
        else:
            title = f"Найдено замечаний: {len(issues)}" + (f", из них важных: {errs}" if errs else "")
        head = QLabel(title)
        head.setObjectName("aihead")
        lay.addWidget(head)
        text = result.get("summary") or ""
        if result.get("skipped"):
            text += (" " if text else "") + (f"Проверены не все страницы: за один раз ИИ читает до 6 сканов "
                                             f"(пропущено: {result['skipped']}).")
        text += (" " if text else "") + "ИИ может ошибаться — это подсказка, а не гарантия."
        sub = QLabel(text.strip())
        sub.setObjectName("hint")
        sub.setWordWrap(True)
        lay.addWidget(sub)
        self.lst = QListWidget()
        self.lst.setObjectName("aiissues")
        self.lst.setWordWrap(True)
        self.lst.setSpacing(2)
        self.lst.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        for it in issues:
            mark = "⛔" if it["severity"] == "error" else "⚠"
            page = f"стр. {it['page']} · " if it["page"] else ""
            line = f"{mark}  {page}{it['text']}"
            if it["quote"]:
                line += f"\n      «{it['quote'][:160]}»"
            li = QListWidgetItem(line)
            li.setData(Qt.UserRole, it["page"])
            self.lst.addItem(li)
        self.lst.itemDoubleClicked.connect(self._go)
        self.lst.setVisible(bool(issues))
        lay.addWidget(self.lst, 1)
        if not issues:
            lay.addStretch(1)
        row = QHBoxLayout()
        tip = QLabel("Двойной щелчок — перейти к странице" if issues else "")
        tip.setObjectName("hint")
        row.addWidget(tip)
        row.addStretch(1)
        b_copy = QPushButton("Скопировать список")
        b_copy.setVisible(bool(issues))
        b_copy.clicked.connect(lambda: QApplication.clipboard().setText(
            "\n".join(self.lst.item(i).text() for i in range(self.lst.count()))))
        row.addWidget(b_copy)
        b = QPushButton("Закрыть")
        b.clicked.connect(self.accept)
        row.addWidget(b)
        lay.addLayout(row)

    def _go(self, item):
        page = item.data(Qt.UserRole)
        if page:
            self.go_page.emit(int(page) - 1)


class AiPlaceDialog(QDialog):
    """Что и куда ставить автоматически: печать, подпись, страницы."""

    def __init__(self, current_file, n_pages, cur_page, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Поставить печать и подпись на место")
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.setMinimumWidth(560)
        s = settings_load().get("ai_place") or {}
        lib = lib_load()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(10)
        head = QLabel("Программа найдёт «М.П.» и строку подписи и поставит их сама")
        head.setObjectName("aihead")
        head.setWordWrap(True)
        lay.addWidget(head)
        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)
        self.cmb_stamp = QComboBox()
        self.cmb_stamp.setMinimumHeight(30)
        self.cmb_stamp.addItem("— не ставить —", None)
        self.cmb_sign = QComboBox()
        self.cmb_sign.setMinimumHeight(30)
        self.cmb_sign.addItem("— не ставить —", None)
        for e in lib:
            label = e["name"] + (f"  ·  {e.get('category')}" if e.get("category") not in (None, "", "Без категории") else "")
            self.cmb_stamp.addItem(label, e["file"])
            self.cmb_sign.addItem(label, e["file"])
        is_sign = lambda e: (e.get("category") == "Подписи") or ("подпис" in e["name"].lower())
        cur = next((e for e in lib if e["file"] == current_file), None)
        want_stamp = current_file if cur and not is_sign(cur) else s.get("stamp")
        if want_stamp is None or self.cmb_stamp.findData(want_stamp) < 0:
            want_stamp = next((e["file"] for e in lib if not is_sign(e)), None)
        want_sign = current_file if cur and is_sign(cur) else s.get("sign", "?")
        if want_sign == "?" or (want_sign and self.cmb_sign.findData(want_sign) < 0):
            want_sign = next((e["file"] for e in lib if is_sign(e)), None)
        self.cmb_stamp.setCurrentIndex(max(0, self.cmb_stamp.findData(want_stamp)))
        self.cmb_sign.setCurrentIndex(max(0, self.cmb_sign.findData(want_sign)))
        form.addRow("Печать:", self.cmb_stamp)
        form.addRow("Подпись:", self.cmb_sign)
        self.cmb_pages = QComboBox()
        self.cmb_pages.setMinimumHeight(30)
        self.cmb_pages.addItem(f"Только текущая (стр. {cur_page + 1})", "current")
        self.cmb_pages.addItem(f"Все страницы, где есть место ({n_pages})", "all")
        self.cmb_pages.setCurrentIndex(1 if s.get("pages") == "all" and n_pages > 1 else 0)
        self.cmb_pages.setEnabled(n_pages > 1)
        form.addRow("Страницы:", self.cmb_pages)
        lay.addLayout(form)
        self.hint = QLabel("")
        self.hint.setObjectName("hint")
        self.hint.setWordWrap(True)
        lay.addWidget(self.hint)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.b_ok = bb.button(QDialogButtonBox.Ok)
        self.b_ok.setText("Найти и поставить")
        self.b_ok.setObjectName("primary")
        bb.button(QDialogButtonBox.Cancel).setText("Отмена")
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.cmb_stamp.currentIndexChanged.connect(self._check)
        self.cmb_sign.currentIndexChanged.connect(self._check)
        self._empty = not lib
        self._check()

    def _check(self):
        ok = bool(self.cmb_stamp.currentData() or self.cmb_sign.currentData())
        self.b_ok.setEnabled(ok)
        if self._empty:
            self.hint.setText("В «Моих печатях» пока пусто. Сначала добавьте печать и подпись в библиотеку "
                              "(правая панель → «Загрузить файл» → «В библиотеку»).")
        elif not ok:
            self.hint.setText("Выберите печать, подпись или обе.")
        else:
            self.hint.setText("Размер берётся тот, что запомнен за печатью. После расстановки всё можно "
                              "подвинуть мышью. Если мест несколько, программа выберет сторону по названию печати.")

    def _ok(self):
        s = settings_load()
        s["ai_place"] = {"stamp": self.cmb_stamp.currentData(), "sign": self.cmb_sign.currentData(),
                         "pages": self.cmb_pages.currentData()}
        settings_save(s)
        self.accept()

    def choice(self):
        return self.cmb_stamp.currentData(), self.cmb_sign.currentData(), self.cmb_pages.currentData()


class MetadataDialog(QDialog):
    """Показать метаданные PDF и предложить их очистить."""

    FIELDS = [("title", "Заголовок"), ("author", "Автор"), ("subject", "Тема"),
              ("keywords", "Ключевые слова"), ("creator", "Создано в программе"),
              ("producer", "Обработано программой"),
              ("creationDate", "Дата создания"), ("modDate", "Дата изменения")]

    def __init__(self, meta: dict, file_label: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Метаданные PDF")
        self.setMinimumWidth(460)
        lay = QVBoxLayout(self)
        lay.setSpacing(8)

        head = QLabel(f"Файл: {file_label}")
        head.setWordWrap(True)
        lay.addWidget(head)

        rows = []
        for key, title in self.FIELDS:
            val = (meta or {}).get(key) or ""
            if val:
                rows.append(f"<b>{title}:</b> {val}")
        if rows:
            body = QLabel("<br>".join(rows))
            info = ("В файле найдены данные, которые видит любой получатель: "
                    "кто и в какой программе его сделал.")
        else:
            body = QLabel("Метаданных нет — файл уже чистый.")
            info = "Очищать нечего."
        body.setWordWrap(True)
        body.setTextFormat(Qt.RichText)
        lay.addWidget(body)

        note = QLabel(info)
        note.setObjectName("hint")
        note.setWordWrap(True)
        lay.addWidget(note)

        self.bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.bb.button(QDialogButtonBox.Ok).setText("Очистить и сохранить как…")
        self.bb.button(QDialogButtonBox.Cancel).setText("Закрыть")
        self.bb.button(QDialogButtonBox.Ok).setEnabled(bool(rows))
        self.bb.accepted.connect(self.accept)
        self.bb.rejected.connect(self.reject)
        lay.addWidget(self.bb)


# ---------------------------------------------------------------- главное окно

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_TITLE} {APP_VERSION}")
        self.resize(1400, 860)
        self.setMinimumSize(1180, 680)

        self.doc = None
        self.doc_path = None
        self.current_page = 0
        self.stamps = []
        self.stamp_pil = None
        self.compress_profile = None      # чем сжимали документ
        self.stamp_raw = None
        self.stamp_pixmap = None
        self.stamp_src_path = None
        self.current_lib_file = None      # печать из библиотеки, за которой запоминается размер
        self.page_item = None

        self.scene = QGraphicsScene()
        self.view = EditorView(self.scene)
        self.setCentralWidget(self.view)
        self.scene.selectionChanged.connect(self.sync_panel_from_selection)

        self._build_mascot()
        self._build_toolbar()
        self._build_dir_bar()
        self._build_side_panel()
        self._build_menubar()
        self.reload_library()
        self.theme = settings_load().get("theme", "light")
        self.apply_theme()
        self._update_ui_state()

    def apply_theme(self):
        style = DARK_STYLE if self.theme == "dark" else LIGHT_STYLE
        icon = tab_close_icon_path("#8a8fa3" if self.theme == "dark" else "#8a8474")
        if icon:
            url = icon.replace("\\", "/")
            style += (f"\nQTabBar::close-button {{ image: url('{url}'); width: 14px; height: 14px; "
                      f"subcontrol-position: right; margin-right: 6px; }}"
                      f"\nQTabBar::close-button:hover {{ background: rgba(200,130,20,0.25); "
                      f"border-radius: 7px; }}")
        style += EXTRA_QSS_DARK if self.theme == "dark" else EXTRA_QSS_LIGHT
        QApplication.instance().setStyleSheet(style)
        self.view.set_theme(self.theme)
        self._retint_icons()
        if hasattr(self, "act_dark"):
            self.act_dark.setChecked(self.theme == "dark")

    def toggle_theme(self):
        self.theme = "light" if self.theme == "dark" else "dark"
        s = settings_load(); s["theme"] = self.theme; settings_save(s)
        self.apply_theme()

    # ---------------- UI ----------------

    def _build_toolbar(self):
        tb = self.addToolBar("Главная")
        tb.setMovable(False)
        tb.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        tb.setIconSize(QSize(18, 18))
        self._themed_actions = []   # (QAction, kind) — перекрашиваются при смене темы
        self._doc_actions = []      # действия, которым нужен открытый документ

        def add(kind, text, slot, shortcut=None, tip=None, target=None, checkable=False):
            a = QAction(text, self)
            a.triggered.connect(slot)
            a.setCheckable(checkable)
            if shortcut:
                a.setShortcut(QKeySequence(shortcut))
            full_tip = tip or text
            if shortcut:
                full_tip = f"{full_tip}  ({shortcut})"
            a.setToolTip(full_tip)
            a.setStatusTip(full_tip)
            (target if target is not None else tb).addAction(a)
            self._themed_actions.append((a, kind))
            return a

        # файл
        self.act_open = add("folder", "Открыть", self.open_pdf, "Ctrl+O", "Открыть PDF-документ")
        self.act_scan = add("scanner", "Сканер", self.scan_document, None,
                            "Отсканировать документ со сканера")
        self.act_save = add("save", "Сохранить", self.save_pdf, "Ctrl+S",
                            "Записать изменения в открытый файл")
        self.act_save_as = add("save_as", "Сохранить как", self.export_pdf, "Ctrl+Shift+S",
                               "Сохранить под новым именем")
        tb.addSeparator()
        # заверение документа
        self.act_pen = add("pen", "Ручка", self.toggle_pen, "Ctrl+R",
                           "Подписать от руки синей ручкой — рисуется мышью на странице",
                           checkable=True)
        self.act_scanlook = add("scanlook", "Как скан", self.scan_look, None,
                                "Сделать документ таким, будто его распечатали и отсканировали")
        tb.addSeparator()
        # страницы и размер файла
        self.act_org = add("pages", "Страницы", self.organize_pages, "Ctrl+P",
                           "Порядок страниц, поворот, добавление из другого PDF")
        self.act_compress = add("compress", "Сжать", self.compress_pdf, None,
                                "Сжать PDF — уменьшить размер файла")
        tb.addSeparator()

        # картинки ↔ PDF: на панели значки с подсказкой, в меню «Файл» — с полным названием
        self.act_images = add("images", "Открыть картинки как документ…", self.open_images_as_doc, None,
                              "Открыть картинки PNG/JPG как страницы документа")
        tb.widgetForAction(self.act_images).setToolButtonStyle(Qt.ToolButtonIconOnly)
        self.act_topdf = add("to_pdf", "Собрать PDF из картинок…", self.images_to_pdf, None,
                             "Собрать PDF из готовых картинок")
        tb.widgetForAction(self.act_topdf).setToolButtonStyle(Qt.ToolButtonIconOnly)
        self.act_png = add("to_png", "Сохранить страницы картинками PNG…", self.export_pngs, None,
                           "Сохранить все страницы картинками PNG")
        tb.widgetForAction(self.act_png).setToolButtonStyle(Qt.ToolButtonIconOnly)
        tb.addSeparator()

        # ИИ-помощник: то же меню стоит в строке меню сверху
        self.btn_ai = QToolButton()
        self.btn_ai.setText("ИИ")
        self.btn_ai.setToolTip("ИИ-помощник: имя файла, печать на место, данные, проверка, распознавание текста")
        self.btn_ai.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.btn_ai.setPopupMode(QToolButton.InstantPopup)
        self.btn_ai.setMenu(self._build_ai_menu())
        tb.addWidget(self.btn_ai)
        self._themed_toolbtns = [(self.btn_ai, "ai")]

        self.act_meta = add("meta", "Метаданные PDF…", self.show_metadata, None,
                            "Посмотреть и очистить метаданные PDF", target=self)
        self.act_close = add("close", "Закрыть документ", self.close_document, "Ctrl+W",
                             "Закрыть открытый документ", target=self)

        tb.addSeparator()      # всё стоит плотно слева — вид панели не зависит от ширины окна
        self.act_help = add("help", "Справка", self.show_guide, "F1",
                            "Как пользоваться программой — с картинками")
        tb.widgetForAction(self.act_help).setToolButtonStyle(Qt.ToolButtonIconOnly)
        self.theme_action = add("moon", "", self.toggle_theme, None, "Светлая / тёмная тема")

        # Удаление выбранной печати — по Del
        self.act_delete = QAction("Удалить выбранную печать", self)
        self.act_delete.setShortcut(QKeySequence("Del"))
        self.act_delete.setStatusTip("Убрать со страницы выделенную печать или подпись  (Del)")
        self.act_delete.triggered.connect(self.delete_selected)
        self.addAction(self.act_delete)
        self._doc_actions.append(self.act_delete)


    # ---------------------------------------------------------- обновления
    def check_updates(self, silent=False):
        """Спросить у GitHub, есть ли версия новее. silent — молчать, если нет."""
        if getattr(self, "_upd_thread", None) is not None and self._upd_thread.isRunning():
            return
        self._upd_silent = silent
        if not silent:
            self.statusBar().showMessage("Проверяю обновления…", 4000)
        self._upd_thread = UpdateCheckThread(self)
        self._upd_thread.result.connect(self._on_update_info)
        self._upd_thread.start()

    def _on_update_info(self, info, err):
        silent = getattr(self, "_upd_silent", True)
        if info is None:
            if not silent:
                QMessageBox.warning(self, "Обновления",
                                    "Не удалось проверить обновления. Проверьте интернет.\n\n" + err)
            return
        latest = str(info.get("version", "0"))
        if vtuple(latest) <= vtuple(APP_VERSION):
            if not silent:
                self.show_toast(f"✔  У вас последняя версия — {APP_VERSION}")
            return
        if hasattr(self, "btn_version"):
            self.btn_version.setText(f" Обновить до {latest} ")
            self.btn_version.setToolTip("Вышла новая версия — нажмите, чтобы обновить")
        dlg = UpdateDialog(info, self)
        if dlg.exec() != QDialog.Accepted:
            return
        url = info.get("setup_canon" if EDITION == "canon" else "setup") or ""
        if not INSTALLED or not url or sys.platform != "win32":
            # программа запущена не из установленной копии — открываем страницу релиза
            from PySide6.QtGui import QDesktopServices
            from PySide6.QtCore import QUrl
            QDesktopServices.openUrl(QUrl(url or (GITHUB_URL + "/releases/latest")))
            return
        dest = os.path.join(LIB_DIR, "updates", "StampStudio-Setup.exe")
        prog = QProgressDialog("Скачиваю обновление…", "Отмена", 0, 100, self)
        prog.setWindowTitle("Обновление")
        prog.setWindowModality(Qt.WindowModal)
        prog.setMinimumDuration(0)
        prog.setAutoClose(False)
        prog.setAutoReset(False)
        th = UpdateDownloadThread(url, dest, self)
        self._upd_dl = th

        def on_progress(got, total):
            if total:
                prog.setValue(int(got * 100 / total))
                prog.setLabelText(f"Скачиваю обновление: {got / 1048576:.0f} из {total / 1048576:.0f} МБ")
            else:
                prog.setLabelText(f"Скачиваю обновление: {got / 1048576:.0f} МБ")

        def on_done(path, error):
            prog.close()
            if error:
                if error != "отменено":
                    QMessageBox.warning(self, "Обновление",
                                        "Не удалось скачать обновление:\n" + error)
                return
            try:
                apply_update_installer(path)
            except Exception as e:
                QMessageBox.warning(self, "Обновление", f"Не удалось запустить установку:\n{e}")
                return
            QApplication.quit()

        th.progress.connect(on_progress)
        th.done.connect(on_done)
        prog.canceled.connect(lambda: setattr(th, "cancelled", True))
        th.start()

    def closeEvent(self, event):
        try:
            s = settings_load()
            if hasattr(self, "left_dock"):
                s["left_panel_width"] = self.left_dock.width()
            settings_save(s)
        except Exception:
            pass
        for th in getattr(self, "_ai_threads", []):     # не бросать запросы ИИ на полуслове
            try:
                th.cancelled = True
                th.done.disconnect()
                th.failed.disconnect()
            except Exception:
                pass
        for th in getattr(self, "_ai_threads", []):
            try:
                if th.isRunning() and not th.wait(1500):
                    th.setParent(None)                  # сетевой запрос сам закончится по таймауту
            except Exception:
                pass
        super().closeEvent(event)

    # ====================================================================== меню и ИИ

    def _build_menubar(self):
        mb = self.menuBar()
        mb.setNativeMenuBar(False)
        mb.clear()

        def act(text, slot, shortcut=None, tip=None, checkable=False, doc=False):
            a = QAction(text, self)
            a.triggered.connect(slot)
            a.setCheckable(checkable)
            if shortcut:
                a.setShortcut(QKeySequence(shortcut))
            a.setStatusTip(tip or text.replace("…", ""))
            if doc:
                self._doc_actions.append(a)
            return a

        # ---- Файл
        m = mb.addMenu("Файл")
        for a in (self.act_open, self.act_scan, self.act_images, self.act_topdf):
            m.addAction(a)
        m.addSeparator()
        for a in (self.act_save, self.act_save_as, self.act_png):
            m.addAction(a)
        m.addSeparator()
        m.addAction(self.act_meta)
        m.addAction(self.act_close)
        m.addSeparator()
        m.addAction(act("Выход", self.close, "Ctrl+Q", "Закрыть программу"))

        # ---- Правка
        m = mb.addMenu("Правка")
        self.act_place = act("Поставить печать на страницу", self.add_stamp, "Ctrl+Return",
                             "Поставить выбранную печать в центр страницы", doc=True)
        m.addAction(self.act_place)
        m.addAction(self.act_pen)
        m.addAction(self.act_delete)
        m.addSeparator()
        self.act_rot_l = act("Повернуть страницу влево", lambda: self.rotate_page(-90), "Ctrl+L", doc=True)
        m.addAction(self.act_rot_l)
        self.act_rot_r = act("Повернуть страницу вправо", lambda: self.rotate_page(90), "Ctrl+Shift+L", doc=True)
        m.addAction(self.act_rot_r)
        self.act_crop = act("Обрезать поля…", self.crop_page, None, "Убрать лишние поля по краям", doc=True)
        m.addAction(self.act_crop)
        self.act_frame = act("Кадрировать рамкой…", self.frame_crop_page, None,
                             "Оставить от страницы только область в рамке", doc=True)
        m.addAction(self.act_frame)
        self.act_split = act("Разрезать на две бумаги…", self.split_page_two, None,
                             "Разложить два документа со страницы как два листа на стекле сканера", doc=True)
        m.addAction(self.act_split)
        m.addAction(self.act_scanlook)
        m.addSeparator()
        m.addAction(self.act_org)
        m.addAction(self.act_compress)
        m.addSeparator()
        m.addAction(act("Скопировать текст страницы", self.copy_page_text, "Ctrl+Shift+C",
                        "Скопировать весь текст открытой страницы в буфер обмена", doc=True))

        # ---- Вид
        m = mb.addMenu("Вид")
        self.act_zoom_in = act("Увеличить", lambda: self._zoom(1.2), "Ctrl+=", "Приблизить страницу", doc=True)
        m.addAction(self.act_zoom_in)
        self.act_zoom_out = act("Уменьшить", lambda: self._zoom(1 / 1.2), "Ctrl+-", "Отдалить страницу", doc=True)
        m.addAction(self.act_zoom_out)
        self.act_fit = act("Страница целиком", lambda: self._zoom(0), "Ctrl+0",
                           "Показать страницу целиком", doc=True)
        m.addAction(self.act_fit)
        m.addSeparator()
        m.addAction(act("Следующая страница", lambda: self._step_page(1), "Ctrl+PgDown", doc=True))
        m.addAction(act("Предыдущая страница", lambda: self._step_page(-1), "Ctrl+PgUp", doc=True))
        m.addSeparator()
        self.act_dark = act("Тёмная тема", self.toggle_theme, None, "Светлая / тёмная тема", checkable=True)
        m.addAction(self.act_dark)

        # ---- ИИ (то же меню, что у кнопки «ИИ» в панели)
        mb.addMenu(self.ai_menu)

        # ---- Помощь
        m = mb.addMenu("Помощь")
        m.addAction(self.act_help)
        m.addAction(act("Что нового в этой версии", self.show_whats_new, None, "Список изменений на сайте"))
        m.addAction(act("Проверить обновления", lambda: self.check_updates(silent=False), None,
                        "Проверить, не вышла ли новая версия"))
        m.addSeparator()
        m.addAction(act("О программе", self.show_about))
        self._build_toolstrip()

    def _build_toolstrip(self):
        """Вертикальная панель инструментов у левого края, как в графических редакторах:
        те же действия, что в меню «Правка», «Вид» и «ИИ», — одним щелчком."""
        tb = QToolBar("Инструменты", self)
        tb.setObjectName("tools")
        tb.setMovable(False)
        tb.setOrientation(Qt.Vertical)
        tb.setToolButtonStyle(Qt.ToolButtonIconOnly)
        tb.setIconSize(QSize(18, 18))
        self.addToolBar(Qt.LeftToolBarArea, tb)
        self.tool_strip = tb
        known = {a: k for a, k in self._themed_actions}
        groups = [
            [(self.act_place, "stamp"), (self.act_pen, "pen"), (self.act_ai_place, "aim"), (self.act_delete, "trash")],
            [(self.act_rot_l, "rot_left"), (self.act_rot_r, "rot_right"), (self.act_crop, "crop"),
             (self.act_frame, "frame"), (self.act_split, "split")],
            [(self.act_scanlook, "scanlook"), (self.act_ai_ocr, "ocr")],
            [(self.act_zoom_in, "zoom_in"), (self.act_zoom_out, "zoom_out"), (self.act_fit, "fit")],
        ]
        for n, group in enumerate(groups):
            if n:
                tb.addSeparator()
            for a, kind in group:
                if a not in known:
                    self._themed_actions.append((a, kind))
                key = a.shortcut().toString()
                name = a.text().replace("…", "")
                tip = a.statusTip() if a.statusTip() and a.statusTip() != name else ""
                a.setToolTip(name + (f"  ({key})" if key else "") + (f"\n{tip}" if tip and name not in tip else ""))
                tb.addAction(a)

    def _build_ai_menu(self):
        """Меню «ИИ»: пять помощников, галочка «автоматически», настройки."""
        m = QMenu("ИИ", self)
        m.setToolTipsVisible(True)

        def act(text, slot, shortcut, tip, doc=True, checkable=False):
            a = QAction(text, self)
            a.triggered.connect(slot)
            a.setCheckable(checkable)
            if shortcut:
                a.setShortcut(QKeySequence(shortcut))
            a.setToolTip(tip)
            a.setStatusTip(tip)
            m.addAction(a)
            self.addAction(a)
            if doc:
                self._doc_actions.append(a)
            return a

        self.act_ai_name = act("Предложить имя файла", self.ai_name, "Ctrl+I",
                               "ИИ читает документ и предлагает имя: «CMR №597 Иванов 26.09.2026»")
        self.act_ai_place = act("Поставить печать и подпись на место…", self.ai_place, "Ctrl+M",
                                "Найти «М.П.» и строку подписи и поставить туда печать и подпись")
        self.act_ai_data = act("Данные из документа…", self.ai_extract, "Ctrl+D",
                               "Номер, дата, сумма, VIN, ФИО — в буфер обмена или в таблицу")
        self.act_ai_check = act("Проверить перед отправкой…", self.ai_check, "Ctrl+E",
                                "Опечатки, несовпадения дат, сумм и реквизитов, пустые поля")
        self.act_ai_ocr = act("Распознать текст скана", self.ai_ocr, "Ctrl+T",
                              "После этого в скане работают поиск и копирование текста")
        m.addSeparator()
        self.act_ai_auto = act("Работать автоматически", self.ai_toggle_auto, None,
                               "Имя файла подставляется само при «Сохранить как», текст распознаётся после "
                               "сканирования. Что именно делать само — в настройках ИИ.",
                               doc=False, checkable=True)
        self.act_ai_auto.setChecked(bool(settings_load().get("ai_auto", False)))
        self.act_ai_settings = act("Настройки ИИ и ключи…", self.ai_settings, None,
                                   "Сервисы ИИ, ключи, что делать автоматически", doc=False)
        self.ai_menu = m
        return m

    def _zoom(self, factor):
        if self.doc is None:
            return
        if factor == 0:
            self.view.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)
        else:
            self.view.scale(factor, factor)
        self.place_mascot()

    def _step_page(self, delta):
        if self.doc is None:
            return
        row = max(0, min(self.doc.page_count - 1, self.page_list.currentRow() + delta))
        self.page_list.setCurrentRow(row)

    def copy_page_text(self):
        if self.doc is None:
            return
        text = self.doc[self.current_page].get_text().strip()
        if not text:
            QMessageBox.information(
                self, "Текста нет",
                "Эта страница — картинка (скан), текста в ней нет.\n"
                "Сначала распознайте текст: меню «ИИ → Распознать текст скана».")
            return
        QApplication.clipboard().setText(text)
        self.show_toast("✔  Текст страницы скопирован")

    def show_whats_new(self):
        QDesktopServices.openUrl(QUrl(f"{GITHUB_URL}/releases/tag/v{APP_VERSION}"))

    def show_about(self):
        QMessageBox.about(
            self, "О программе",
            f"<h3>{APP_TITLE} {APP_VERSION}</h3>"
            "<p>Печати и подписи на PDF в точных миллиметрах, сканирование, сжатие, "
            "обрезка, вид «как скан» и ИИ-помощник.</p>"
            f"<p><a href='{GITHUB_URL}'>{GITHUB_URL}</a></p>")

    # ---------------------------------------------------------- ИИ: общее

    def ai_settings(self):
        dlg = AiSettingsDialog(self)
        dlg.exec()
        self.act_ai_auto.setChecked(bool(settings_load().get("ai_auto", False)))

    def ai_toggle_auto(self, on):
        if on and not self._ai_ready():
            self.act_ai_auto.setChecked(False)
            return
        s = settings_load()
        s["ai_auto"] = bool(on)
        settings_save(s)
        if on:
            parts = []
            if s.get("ai_auto_name", True):
                parts.append("имя файла — само в окне «Сохранить как»")
            if s.get("ai_auto_ocr", True):
                parts.append("текст — сразу после сканирования")
            self.show_toast("✨  ИИ работает автоматически: " + ("; ".join(parts) or "ничего не выбрано в настройках"), 4200)
        else:
            self.statusBar().showMessage("ИИ работает только по вашей команде из меню «ИИ»", 6000)

    def _ai_ready(self):
        """Первое использование ИИ: один раз объяснить, что уходит в интернет."""
        s = settings_load()
        if s.get("ai_consent"):
            return True
        name = (s.get("ai_provider") or AI.default_provider(s)).split(" (")[0]
        box = QMessageBox(self)
        box.setWindowTitle("ИИ-помощник")
        box.setIcon(QMessageBox.Information)
        box.setText("ИИ читает документ через интернет")
        box.setInformativeText(
            f"Текст или изображение страниц будет отправлено в сервис ИИ ({name}).\n"
            "Бесплатные сервисы могут использовать присланное для обучения своих моделей.\n\n"
            "Не используйте ИИ для документов, которые нельзя никому показывать.\n"
            "Сервис и ключи — в меню «ИИ → Настройки ИИ и ключи».")
        ok = box.addButton("Понятно, продолжить", QMessageBox.AcceptRole)
        box.addButton("Отмена", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is not ok:
            return False
        s = settings_load()
        s["ai_consent"] = True
        settings_save(s)
        return True

    def _ai_run(self, title, fn, on_done, quiet=False, on_fail=None):
        """Выполнить fn(status, cancelled) в фоне, показать окно ожидания, вернуть поток."""
        th = AiThread(fn, self)
        self._ai_threads = [t for t in getattr(self, "_ai_threads", []) if t.isRunning()] + [th]
        busy = None
        if not quiet:
            busy = AiBusyDialog(title, self)
            th.status.connect(busy.set_status)
            busy.rejected.connect(lambda: setattr(th, "cancelled", True))

        def close_busy():
            if busy is not None:
                busy.blockSignals(True)
                busy.accept()

        def ok(res):
            close_busy()
            on_done(res)

        def bad(msg):
            close_busy()
            (on_fail or self._ai_fail)(msg)
        th.done.connect(ok)
        th.failed.connect(bad)
        th.start()
        if busy is not None:
            busy.open()
        return th

    def _ai_fail(self, msg):
        box = QMessageBox(self)
        box.setWindowTitle("ИИ-помощник")
        box.setIcon(QMessageBox.Warning)
        box.setText("ИИ не справился")
        box.setInformativeText(msg)
        b_set = box.addButton("Настройки ИИ…", QMessageBox.ActionRole)
        box.addButton("Закрыть", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is b_set:
            self.ai_settings()

    def _ai_need_doc(self):
        if self.doc is None:
            QMessageBox.information(self, "Нет документа",
                                    "Сначала откройте PDF или отсканируйте документ.")
            return False
        return True

    def _doc_title(self):
        name = os.path.basename(str(self.doc_path or "документ"))
        return name.replace(" (из изображений)", "")

    # ---------------------------------------------------------- 1. имя файла

    def ai_name(self):
        if not self._ai_need_doc() or not self._ai_ready():
            return
        pages = list(range(min(3, self.doc.page_count)))
        bundle = AI.collect(self.doc, pages, max_images=3, max_chars=7000)
        self._ai_run("ИИ читает документ и подбирает имя файла",
                     lambda st, c: AI.task_name(bundle, None, st, c), self._ai_name_done)

    def _ai_name_done(self, res):
        self._ai_name_cache = (str(self.doc_path), self.doc.page_count if self.doc else 0, res["name"])
        path = str(self.doc_path or "")
        can = bool(path and os.path.isfile(path) and path.lower().endswith(".pdf"))
        dlg = AiNameDialog(res["name"], can, f"{res['provider'].split(' (')[0]} · {res['model']}", self)
        if dlg.exec() != QDialog.Accepted:
            return
        name = dlg.name()
        if dlg.action == "copy":
            QApplication.clipboard().setText(name)
            self.show_toast("✔  Имя скопировано")
        elif dlg.action == "saveas":
            self.export_pdf(suggest=name)
        elif dlg.action == "rename":
            self._rename_current(name)
        elif dlg.action == "again":
            self._ai_name_cache = None
            self.ai_name()

    def _rename_current(self, name):
        old = str(self.doc_path)
        new = os.path.join(os.path.dirname(old), name + ".pdf")
        if os.path.abspath(new).lower() == os.path.abspath(old).lower():
            self.show_toast("Файл уже так называется")
            return
        if os.path.exists(new):
            QMessageBox.warning(self, "Имя занято",
                                f"В этой папке уже есть файл «{name}.pdf».\nПоправьте имя и попробуйте снова.")
            return
        try:
            data = self.doc.tobytes()          # вместе с несохранёнными правками страниц
            self.doc.close()
            try:
                write_file_safely(new, data)
            except Exception:
                self.doc = fitz.open(old)
                raise
            self.doc = fitz.open(new)
            self.doc_path = new
            try:
                os.remove(old)
            except OSError:
                pass
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось переименовать:\n{e}")
            return
        self.setWindowTitle(f"{APP_TITLE} {APP_VERSION} — {os.path.basename(new)}")
        self.refresh_files()
        self.show_toast(f"✔  Файл переименован: {name}.pdf")

    def _ai_name_for_dialog(self, dlg):
        """Автоматический режим: подобрать имя, пока открыто окно «Сохранить как»."""
        s = settings_load()
        if not (s.get("ai_auto") and s.get("ai_auto_name", True) and s.get("ai_consent")) or self.doc is None:
            return
        cache = getattr(self, "_ai_name_cache", None)
        if cache and cache[0] == str(self.doc_path) and cache[1] == self.doc.page_count:
            dlg.set_ai_name(cache[2])
            return
        pages = list(range(min(3, self.doc.page_count)))
        bundle = AI.collect(self.doc, pages, max_images=3, max_chars=7000)
        dlg.set_ai_wait()
        key = (str(self.doc_path), self.doc.page_count)

        def ok(res):
            self._ai_name_cache = (key[0], key[1], res["name"])
            try:
                dlg.set_ai_name(res["name"])
            except RuntimeError:
                pass

        def bad(msg):
            try:
                dlg.set_ai_fail(msg)
            except RuntimeError:
                pass
        th = self._ai_run("", lambda st, c: AI.task_name(bundle, None, st, c), ok, quiet=True, on_fail=bad)
        dlg.finished.connect(lambda *_: setattr(th, "cancelled", True))

    # ---------------------------------------------------------- 2. печать и подпись на место

    def ai_place(self):
        if not self._ai_need_doc():
            return
        if self.view.pen_active():
            self.pen_finish(commit=True)
        dlg = AiPlaceDialog(getattr(self, "current_lib_file", None), self.doc.page_count,
                            self.current_page, self)
        if dlg.exec() != QDialog.Accepted:
            return
        stamp_file, sign_file, scope = dlg.choice()
        pages = [self.current_page] if scope == "current" else list(range(self.doc.page_count))
        lib = {e["file"]: e for e in lib_load()}
        stamp_name = (lib.get(stamp_file) or {}).get("name", "")
        win = AI.win_ocr_available()
        jobs = []
        for i in pages:
            page = self.doc[i]
            job = {"page": i, "w": page.rect.width, "h": page.rect.height, "words": None, "jpeg": None, "iw": 1}
            if AI.page_has_text(page):
                job["words"] = AI.page_words(page)
            else:
                im = AI.page_image(page, 2200 if win else 1600)
                job["jpeg"], job["iw"] = AI.jpeg_bytes(im, 85), im.width
            jobs.append(job)
        if any(j["words"] is None for j in jobs) and not win and not self._ai_ready():
            return
        allow_ai = bool(settings_load().get("ai_consent"))

        def work(status, cancelled):
            out = []
            for n, j in enumerate(jobs):
                if cancelled():
                    raise AI.AiCancelled()
                status(f"Ищу место: стр. {j['page'] + 1} ({n + 1} из {len(jobs)})")
                res = {"page": j["page"], "stamps": [], "signs": [], "many": False}
                words = j["words"]
                if words is None and win:
                    try:
                        k = j["w"] / j["iw"]
                        words = [(a * k, b * k, c * k, d * k, t)
                                 for a, b, c, d, t in AI.win_ocr_words(Image.open(io.BytesIO(j["jpeg"])))]
                    except AI.AiError:
                        words = None
                if words:
                    st, sg = AI.find_marks(words)
                    res["signs"] = [(c[0], c[1]) for c in sg]
                    if len(st) > 1 and stamp_name:
                        k = AI.choose_place(st, words, stamp_name)
                        if k is None and allow_ai:
                            try:
                                k = AI.task_choose_place(st, words, stamp_name, status, cancelled)
                            except AI.AiError:
                                k = None
                        if k is not None:
                            st = [st[k]]
                        else:
                            res["many"] = True
                    elif len(st) > 1:
                        res["many"] = True
                    res["stamps"] = [(c[0], c[1]) for c in st]
                if not res["stamps"] and not res["signs"] and j["jpeg"] is not None and allow_ai:
                    try:
                        sp, gp = AI.task_find_places_vision(j["jpeg"], stamp_name, status, cancelled)
                    except AI.AiError:
                        sp = gp = None
                    if sp:
                        res["stamps"] = [(sp[0] * j["w"], sp[1] * j["h"])]
                    if gp:
                        res["signs"] = [(gp[0] * j["w"], gp[1] * j["h"])]
                out.append(res)
            return out
        self._ai_run("Ищу «М.П.» и строку подписи", work,
                     lambda out: self._ai_place_apply(out, stamp_file, sign_file))

    def _pick_entry(self, entry):
        it = QListWidgetItem()
        it.setData(Qt.UserRole, entry)
        self.lib_pick(it)

    def _place_entry(self, entry, page, cx_pt, cy_pt):
        if self.page_list.currentRow() != page:
            self.page_list.setCurrentRow(page)
        if self.current_page != page:
            self.show_page(page)
        self.scene.clearSelection()       # иначе смена печати меняет размер выделенной
        self._pick_entry(entry)
        before = len(self.stamps)
        self.add_stamp()
        if len(self.stamps) == before:
            return None
        it = self.stamps[-1]
        k = PREVIEW_DPI / 72.0
        it.setPos(cx_pt * k - it.pixmap().width() / 2 * it.transform().m11(),
                  cy_pt * k - it.pixmap().height() / 2 * it.transform().m22())
        return it

    def _ai_place_apply(self, out, stamp_file, sign_file):
        lib = {e["file"]: e for e in lib_load()}
        st_e, sg_e = lib.get(stamp_file), lib.get(sign_file)
        mm = MM_TO_PT
        n_st = n_sg = 0
        many, first = [], None
        for res in out:
            page = self.doc[res["page"]]
            W, H = page.rect.width, page.rect.height
            spots, signs = res["stamps"], list(res["signs"])
            targets = []
            if sg_e:
                lift = float(sg_e.get("mm_h", 20)) * mm * 0.18      # подпись чуть выше линии
                if spots:
                    for (x, y) in spots:
                        near = sorted(signs, key=lambda s: (s[0] - x) ** 2 + (s[1] - y) ** 2)
                        if near and ((near[0][0] - x) ** 2 + (near[0][1] - y) ** 2) ** 0.5 <= 85 * mm:
                            targets.append((near[0][0], near[0][1] - lift))
                            signs.remove(near[0])
                        else:
                            targets.append((max(18 * mm, x - 40 * mm), y - 3 * mm))
                elif signs and not st_e:
                    targets = [(s[0], s[1] - lift) for s in signs]
                    if len(signs) > 1:
                        res["many"] = True
            placed = False
            if st_e:
                for (x, y) in spots:
                    x = max(6 * mm, min(W - 6 * mm, x))
                    y = max(6 * mm, min(H - 6 * mm, y))
                    if self._place_entry(st_e, res["page"], x, y) is not None:
                        n_st += 1
                        placed = True
            for (x, y) in targets:
                if self._place_entry(sg_e, res["page"], x, y) is not None:
                    n_sg += 1
                    placed = True
            if placed and first is None:
                first = res["page"]
            if placed and res["many"]:
                many.append(res["page"] + 1)
        self.scene.clearSelection()
        if st_e:
            self._pick_entry(st_e)
        if not (n_st or n_sg):
            QMessageBox.information(
                self, "Место не найдено",
                "Не нашёл на странице «М.П.» и строку подписи.\n\n"
                "Поставьте печать обычным способом: выберите её справа и нажмите "
                "«Поставить печать на страницу», затем подвиньте мышью.")
            return
        if first is not None:
            self.page_list.setCurrentRow(first)
            if self.current_page != first:
                self.show_page(first)
        parts = []
        if n_st:
            parts.append(f"печать — {n_st}")
        if n_sg:
            parts.append(f"подпись — {n_sg}")
        msg = "✔  Поставил: " + ", ".join(parts) + ". Проверьте и подвиньте мышью, если нужно"
        if many:
            msg += f". На стр. {', '.join(map(str, many))} мест несколько — лишнее удалите клавишей Del"
        self.show_toast(msg, 5200)

    # ---------------------------------------------------------- 3. данные

    def ai_extract(self):
        if not self._ai_need_doc() or not self._ai_ready():
            return
        bundle = AI.collect(self.doc, None, max_images=6)
        title = self._doc_title()
        self._ai_run("ИИ выписывает данные из документа",
                     lambda st, c: AI.task_extract(bundle, None, st, c),
                     lambda res: AiDataDialog(res, title, self).exec())

    # ---------------------------------------------------------- 4. проверка

    def ai_check(self):
        if not self._ai_need_doc() or not self._ai_ready():
            return
        bundle = AI.collect(self.doc, None, max_images=6, max_chars=24000)
        title = self._doc_title()

        def show(res):
            dlg = AiCheckDialog(res, title, self)
            dlg.go_page.connect(lambda i: self.page_list.setCurrentRow(i)
                                if self.doc is not None and 0 <= i < self.doc.page_count else None)
            dlg.setModal(False)
            self._ai_check_dlg = dlg
            dlg.show()
        self._ai_run("ИИ проверяет документ", lambda st, c: AI.task_check(bundle, st, c), show)

    # ---------------------------------------------------------- 5. распознавание текста

    def ai_ocr(self, checked=False, pages=None, silent_if_nothing=False):
        if not self._ai_need_doc():
            return
        s = settings_load()
        engine = s.get("ai_ocr_engine", "auto")
        win = AI.win_ocr_available()
        if engine == "windows" and not win:
            QMessageBox.information(
                self, "Распознавание Windows недоступно",
                "На этом компьютере не установлен язык распознавания текста Windows.\n"
                "Выберите в «ИИ → Настройки ИИ и ключи» распознавание «Авто» или «ИИ».")
            return
        use_win = win and engine in ("auto", "windows")
        todo = [i for i in (pages if pages is not None else range(self.doc.page_count))
                if not AI.page_has_text(self.doc[i])]
        if not todo:
            if not silent_if_nothing:
                self.show_toast("✔  Текст в документе уже есть — поиск и копирование работают")
            return
        if not use_win:
            if not self._ai_ready():
                return
            if len(todo) > 12:
                q = QMessageBox.question(
                    self, "Много страниц",
                    f"Распознать через ИИ {len(todo)} стр.? Это {len(todo)} запросов и несколько минут.")
                if q != QMessageBox.Yes:
                    return
        jobs = []
        for i in todo:
            AI.normalize_rotation(self.doc[i])
            page = self.doc[i]
            im = AI.page_image(page, 2400 if use_win else 1600)
            jobs.append((i, page.rect.width, page.rect.height, AI.jpeg_bytes(im, 88 if use_win else 75), im.width))

        def work(status, cancelled):
            res, errors = {}, []
            for n, (i, w, h, jpg, iw) in enumerate(jobs):
                if cancelled():
                    raise AI.AiCancelled()
                status(f"Распознаю текст: стр. {i + 1} ({n + 1} из {len(jobs)})")
                try:
                    if use_win:
                        k = w / iw
                        res[i] = [(a * k, b * k, c * k, d * k, t)
                                  for a, b, c, d, t in AI.win_ocr_words(Image.open(io.BytesIO(jpg)))]
                    else:
                        res[i] = [(a * w, b * h, c * w, d * h, t)
                                  for a, b, c, d, t in AI.task_ocr_vision(jpg, status, cancelled)]
                except AI.AiError as e:
                    errors.append(f"стр. {i + 1}: {e}")
                    if use_win or len(errors) >= 3:
                        break
            if not res and errors:
                raise AI.AiError("\n".join(errors[:3]))
            return res, errors
        self._ai_run("Распознаю текст" + (" на этом компьютере" if use_win else " через ИИ"),
                     work, self._ai_ocr_done)

    def _ai_ocr_done(self, result):
        res, errors = result
        done = words = 0
        for i, ws in res.items():
            if self.doc is None or i >= self.doc.page_count or not ws:
                continue
            k = AI.add_text_layer(self.doc[i], ws)
            if k:
                done += 1
                words += k
        try:
            self.doc.subset_fonts()
        except Exception:
            pass
        if not done:
            QMessageBox.information(self, "Текст не найден",
                                    "На страницах не нашлось текста, который можно распознать.")
            return
        msg = f"✔  Текст распознан: {done} стр., {words} слов. Сохраните документ (Ctrl+S) — в нём заработают поиск и копирование"
        if errors:
            msg += f". Не получилось: {len(errors)} стр."
        self.show_toast(msg, 5200)
        self.statusBar().showMessage(msg.replace("✔  ", ""), 9000)

    def _ai_after_scan(self):
        """Автоматический режим: распознать текст, когда сканирование закончено."""
        s = settings_load()
        if not (s.get("ai_auto") and s.get("ai_auto_ocr", True)) or self.doc is None:
            return
        win = AI.win_ocr_available() and s.get("ai_ocr_engine", "auto") in ("auto", "windows")
        if not win and not s.get("ai_consent"):
            return
        self.ai_ocr(silent_if_nothing=True)

    def _icon_color(self):
        return "#e8e6e1" if getattr(self, "theme", "light") == "dark" else "#4a4636"

    def _retint_icons(self):
        col = self._icon_color()
        for a, kind in self._themed_actions:
            a.setIcon(draw_icon(kind, col))
        for b, kind, accent in getattr(self, "_themed_buttons", []):
            b.setIcon(draw_icon(kind, "#2a1e00" if accent else col))
        for b, kind in getattr(self, "_themed_toolbtns", []):
            b.setIcon(draw_icon(kind, col))
        if hasattr(self, "btn_adv"):
            self._adv_toggle(self.btn_adv.isChecked(), save=False)
        if hasattr(self, "theme_action"):
            self.theme_action.setIcon(draw_icon(
                "sun" if self.theme == "dark" else "moon", col))
        if hasattr(self, "file_list"):
            self.refresh_files()

    def place_mascot(self):
        """Держать картинку в стороне от страницы документа."""
        m = getattr(self, "mascot", None)
        if m is None:
            return
        if not m.wanted_visible:
            m.setVisible(False)
            return
        page_rect = None
        if self.page_item is not None and self.page_item.scene() is not None:
            r = self.view.mapFromScene(
                self.page_item.sceneBoundingRect()).boundingRect()
            page_rect = r.adjusted(-4, -4, 4, 4)
        m.reposition(page_rect)

    def _build_mascot(self):
        """Картинка в углу: файл mascot.png рядом с программой."""
        self.mascot = None
        path = find_resource("mascot.png")
        if not path:
            return
        s = settings_load()
        self.mascot = MascotOverlay(self.view, path)
        if self.mascot.pix.isNull():
            self.mascot.deleteLater()
            self.mascot = None
            return
        self.view.mascot = self.mascot
        self.mascot.set_height(int(s.get("mascot_height", 200)))
        self.mascot.set_opacity(float(s.get("mascot_opacity", 0.92)))
        self.mascot.wanted_visible = bool(s.get("mascot_visible", True))
        self.view.on_view_changed = self.place_mascot
        self.place_mascot()
        self.view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self.mascot_menu)

    def mascot_menu(self, pos):
        if self.mascot is None:
            return
        menu = QMenu(self)
        act_show = menu.addAction("Показывать картинку")
        act_show.setCheckable(True)
        act_show.setChecked(self.mascot.wanted_visible)
        menu.addSeparator()
        sizes = [("Маленькая", 120), ("Средняя", 200), ("Большая", 300)]
        for title, h in sizes:
            a = menu.addAction(title)
            a.setCheckable(True)
            a.setChecked(abs(self.mascot._height - h) < 20)
            a.triggered.connect(lambda _=False, hh=h: self._mascot_size(hh))
        menu.addSeparator()
        for title, o in [("Полупрозрачная", 0.45), ("Обычная", 0.92)]:
            a = menu.addAction(title)
            a.triggered.connect(lambda _=False, oo=o: self._mascot_opacity(oo))
        act_show.triggered.connect(self._mascot_toggle)
        menu.exec(self.view.mapToGlobal(pos))

    def _mascot_toggle(self, checked):
        self.mascot.wanted_visible = checked
        self.place_mascot()
        s = settings_load(); s["mascot_visible"] = checked; settings_save(s)

    def _mascot_size(self, h):
        self.mascot.set_height(h)
        self.place_mascot()
        s = settings_load(); s["mascot_height"] = h; settings_save(s)

    def _mascot_opacity(self, o):
        self.mascot.set_opacity(o)
        s = settings_load(); s["mascot_opacity"] = o; settings_save(s)

    def _build_dir_bar(self):
        """Панель вкладок открытых папок — во всю ширину под главной панелью."""
        self.addToolBarBreak()
        bar = self.addToolBar("Папки")
        bar.setObjectName("dirbar")
        bar.setMovable(False)
        bar.setFloatable(False)
        self._themed_buttons = getattr(self, "_themed_buttons", [])

        holder = QWidget()
        row = QHBoxLayout(holder)
        row.setContentsMargins(8, 2, 8, 2)
        row.setSpacing(8)

        self.dir_tabs = QTabBar()
        self.dir_tabs.setTabsClosable(True)
        self.dir_tabs.setMovable(True)
        self.dir_tabs.setExpanding(False)
        self.dir_tabs.setDrawBase(False)
        self.dir_tabs.setElideMode(Qt.ElideRight)
        self.dir_tabs.setUsesScrollButtons(True)
        self.dir_tabs.currentChanged.connect(self.on_dir_tab_changed)
        self.dir_tabs.tabCloseRequested.connect(self.close_dir_tab)
        row.addWidget(self.dir_tabs, 0)

        b_newtab = QPushButton()
        b_newtab.setFixedSize(30, 30)
        b_newtab.setToolTip("Открыть ещё одну папку во вкладке")
        b_newtab.setIconSize(QSize(13, 13))
        b_newtab.clicked.connect(self.add_dir_tab)
        self._themed_buttons.append((b_newtab, "plus", False))
        row.addWidget(b_newtab, 0)

        b_up = QPushButton()
        b_up.setFixedSize(30, 30)
        b_up.setToolTip("Перейти в папку уровнем выше")
        b_up.setIconSize(QSize(13, 13))
        b_up.clicked.connect(self.dir_go_up)
        self._themed_buttons.append((b_up, "up", False))
        row.addWidget(b_up, 0)

        row.addSpacing(6)
        self.lbl_path = QLabel("")
        self.lbl_path.setObjectName("path")
        self.lbl_path.setTextInteractionFlags(Qt.TextSelectableByMouse)
        row.addWidget(self.lbl_path, 1)

        bar.addWidget(holder)

    def _build_side_panel(self):
        self.no_wheel = NoWheelFilter(self)
        self._build_left_panel()
        self._build_right_panel()
        self.setStatusBar(QStatusBar())
        self.btn_version = QPushButton(f" v{APP_VERSION} ")
        self.btn_version.setFlat(True)
        self.btn_version.setObjectName("verbtn")
        self.btn_version.setCursor(Qt.PointingHandCursor)
        self.btn_version.setToolTip("Проверить обновления")
        self.btn_version.clicked.connect(lambda: self.check_updates(silent=False))
        self.statusBar().addPermanentWidget(self.btn_version)
        if settings_load().get("auto_update", True):
            QTimer.singleShot(2500, lambda: self.check_updates(silent=True))
        self._guard_wheel()

    def _guard_wheel(self):
        """Колесо больше не крутит значения полей случайно."""
        for cls in (QComboBox, QDoubleSpinBox, QSpinBox, QSlider):
            for wd in self.findChildren(cls):
                wd.setFocusPolicy(Qt.StrongFocus)
                wd.installEventFilter(self.no_wheel)

    # ---- левая панель: страницы ----
    def _build_left_panel(self):
        dock = QDockWidget("ОБЗОР", self)
        dock.setFeatures(QDockWidget.NoDockWidgetFeatures)
        dock.setTitleBarWidget(QWidget())      # своя шапка внутри панели
        box = QWidget()
        outer = QVBoxLayout(box)
        outer.setContentsMargins(10, 6, 10, 10)
        outer.setSpacing(8)
        title = QLabel("ОБЗОР")
        title.setObjectName("paneltitle")
        outer.addWidget(title)
        self._themed_buttons = getattr(self, "_themed_buttons", [])

        splitter = QSplitter(Qt.Vertical)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(8)

        # ---------- верх: проводник по папкам ----------
        top = QWidget()
        tl = QVBoxLayout(top)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.setSpacing(6)
        cap_files = QLabel("<b>Файлы в папке</b>")
        tl.addWidget(cap_files)

        self.file_list = QListWidget()
        self.file_list.setAlternatingRowColors(True)
        self.file_list.setTextElideMode(Qt.ElideMiddle)
        self.file_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.file_list.setWordWrap(False)
        self.file_list.setMinimumHeight(80)
        self.file_list.itemDoubleClicked.connect(self.open_from_browser)
        self.file_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.file_list.customContextMenuRequested.connect(self.file_menu)
        tl.addWidget(self.file_list, 1)

        b_open = QPushButton(" Открыть выбранный файл")
        b_open.setIconSize(QSize(14, 14))
        b_open.setMinimumHeight(30)
        b_open.clicked.connect(lambda: self.open_from_browser(self.file_list.currentItem()))
        self._themed_buttons.append((b_open, "folder", False))
        tl.addWidget(b_open)
        splitter.addWidget(top)

        # ---------- низ: страницы открытого документа ----------
        bot = QWidget()
        lay = QVBoxLayout(bot)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        cap_pages = QLabel("<b>Страницы документа</b>")
        lay.addWidget(cap_pages)

        self.page_list = QListWidget()
        self.page_list.setViewMode(QListWidget.IconMode)
        self.page_list.setIconSize(QSize(104, 140))
        self.page_list.setGridSize(QSize(140, 170))
        self.page_list.setResizeMode(QListWidget.Adjust)
        self.page_list.setMovement(QListWidget.Snap)
        self.page_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.page_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.page_list.setSpacing(2)
        self.page_list.currentRowChanged.connect(self.show_page)
        self.page_list.model().rowsMoved.connect(self._pages_dragged)
        self.page_list.setToolTip("Страницы можно перетаскивать мышкой")
        self.page_list.setMinimumHeight(120)
        lay.addWidget(self.page_list, 1)

        btns = QHBoxLayout()
        btns.setSpacing(4)
        for kind, tip, slot in [
                ("rot_left", "Повернуть страницу влево на 90°",
                 lambda: self.rotate_page(-90)),
                ("rot_right", "Повернуть страницу вправо на 90°",
                 lambda: self.rotate_page(90)),
                ("up", "Переместить страницу выше", lambda: self.move_page(-1)),
                ("down", "Переместить страницу ниже", lambda: self.move_page(1)),
                ("trash", "Удалить страницу", self.delete_page)]:
            b = QPushButton()
            b.setToolTip(tip)
            b.setFixedHeight(30)
            b.setIconSize(QSize(16, 16))
            b.clicked.connect(slot)
            self._themed_buttons.append((b, kind, False))
            btns.addWidget(b)
        lay.addLayout(btns)

        tools = QGridLayout()
        tools.setSpacing(4)
        for n, (kind, text, tip, slot) in enumerate([
                ("crop", " Обрезать поля", "Обрезать поля скана с любой стороны (в мм)",
                 self.crop_page),
                ("frame", " Кадрировать", "Выделить нужную область мышью; размер можно "
                 "сохранить как шаблон", self.frame_crop_page),
                ("split", " Разрезать на 2", "Разрезать страницу на две бумаги и разложить их "
                 "на одном скане с фоном сканера", self.split_page_two),
                ("scanlook", " Как скан", "Сделать документ таким, будто его распечатали "
                 "и отсканировали", self.scan_look)]):
            b = QPushButton(text)
            b.setIconSize(QSize(15, 15))
            b.setMinimumHeight(32)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            self._themed_buttons.append((b, kind, False))
            tools.addWidget(b, n // 2, n % 2)
        lay.addLayout(tools)
        splitter.addWidget(bot)

        splitter.setSizes([340, 430])
        outer.addWidget(splitter)

        dock.setWidget(box)
        self.left_dock = dock
        dock.setMinimumWidth(270)
        dock.setMaximumWidth(620)
        self.addDockWidget(Qt.LeftDockWidgetArea, dock)
        saved_w = int(settings_load().get("left_panel_width", 340))
        self.resizeDocks([dock], [max(270, min(620, saved_w))], Qt.Horizontal)

        s = settings_load()
        dirs = [d for d in s.get("open_dirs", []) if os.path.isdir(d)]
        if not dirs:
            desk = os.path.join(os.path.expanduser("~"), "Desktop")
            dirs = [desk if os.path.isdir(desk) else os.path.expanduser("~")]
        self._dirs = []
        for d in dirs[:6]:
            self._add_tab_silent(d)
        self.dir_tabs.setCurrentIndex(0)
        self.refresh_files()

    # ---------------- проводник ----------------

    def current_dir(self) -> str:
        i = self.dir_tabs.currentIndex()
        if 0 <= i < len(self._dirs):
            return self._dirs[i]
        return os.path.expanduser("~")

    @staticmethod
    def _tab_title(path: str) -> str:
        name = os.path.basename(path.rstrip(os.sep)) or path
        return name if len(name) <= 14 else name[:13] + "…"

    def _add_tab_silent(self, path):
        self._dirs.append(path)
        self.dir_tabs.addTab(self._tab_title(path))
        self.dir_tabs.setTabToolTip(self.dir_tabs.count() - 1, path)

    def add_dir_tab(self):
        path = QFileDialog.getExistingDirectory(self, "Открыть папку", self.current_dir())
        if not path:
            return
        path = os.path.abspath(path)
        if path in self._dirs:
            self.dir_tabs.setCurrentIndex(self._dirs.index(path))
            self.statusBar().showMessage("Эта папка уже открыта — перешли на её вкладку", 4000)
            return
        self._add_tab_silent(path)
        self.dir_tabs.setCurrentIndex(self.dir_tabs.count() - 1)
        self.remember_dirs()

    def close_dir_tab(self, index):
        if self.dir_tabs.count() <= 1:
            return
        closing = os.path.abspath(self._dirs[index])
        doc_inside = False
        if self.doc is not None and self.doc_path:
            try:
                doc_inside = os.path.abspath(
                    os.path.dirname(str(self.doc_path))) == closing
            except Exception:
                doc_inside = False
        if doc_inside:
            ans = QMessageBox.question(
                self, "Закрыть вкладку",
                "Из этой папки открыт документ — пока он открыт, папку нельзя "
                "переименовать или удалить.\nЗакрыть документ вместе с вкладкой?",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
            if ans == QMessageBox.Cancel:
                return
            if ans == QMessageBox.Yes:
                self.stamps.clear()
                self.close_document()
        self.dir_tabs.removeTab(index)
        del self._dirs[index]
        self.remember_dirs()
        self._release_folder(closing)
        self.refresh_files()

    def _release_folder(self, folder):
        """Не держать папку занятой: уводим рабочий каталог программы."""
        try:
            cur = os.path.abspath(os.getcwd())
        except OSError:
            cur = ""
        if cur == folder or cur.startswith(folder + os.sep):
            try:
                os.chdir(tempfile.gettempdir())
            except OSError:
                pass

    def on_dir_tab_changed(self, index):
        self.refresh_files()

    def set_dir(self, path, allow_switch=True):
        path = os.path.abspath(path)
        if allow_switch and path in self._dirs:
            idx = self._dirs.index(path)
            if idx != self.dir_tabs.currentIndex():
                self.dir_tabs.setCurrentIndex(idx)
                return
        i = self.dir_tabs.currentIndex()
        if 0 <= i < len(self._dirs):
            self._dirs[i] = path
            self.dir_tabs.setTabText(i, self._tab_title(path))
            self.dir_tabs.setTabToolTip(i, path)
        self.remember_dirs()
        self.refresh_files()

    def dir_go_up(self):
        cur = self.current_dir()
        parent = os.path.dirname(cur.rstrip(os.sep))
        if parent and os.path.isdir(parent) and parent != cur:
            self.set_dir(parent)

    def remember_dirs(self):
        s = settings_load()
        s["open_dirs"] = self._dirs[:6]
        settings_save(s)

    def refresh_files(self):
        if not hasattr(self, "file_list"):
            return
        folder = self.current_dir()
        self.lbl_path.setText(folder)
        self.file_list.clear()
        col = self._icon_color() if hasattr(self, "_icon_color") else "#888888"
        try:
            entries = sorted(os.listdir(folder), key=lambda x: x.lower())
        except OSError:
            self.file_list.addItem("нет доступа к папке")
            return
        subdirs = [e for e in entries
                   if os.path.isdir(os.path.join(folder, e)) and not e.startswith(".")]
        exts = (".pdf", ".png", ".jpg", ".jpeg")
        files = [e for e in entries if e.lower().endswith(exts)]
        for d in subdirs:
            it = QListWidgetItem(draw_icon("folder", col), d)
            it.setToolTip(d)
            it.setData(Qt.UserRole, ("dir", os.path.join(folder, d)))
            self.file_list.addItem(it)
        for f in files:
            kind = "to_pdf" if f.lower().endswith(".pdf") else "images"
            it = QListWidgetItem(draw_icon(kind, col), f)
            full = os.path.join(folder, f)
            try:
                it.setToolTip(f"{f}\n{human_size(os.path.getsize(full))}")
            except OSError:
                pass
            it.setData(Qt.UserRole, ("file", full))
            self.file_list.addItem(it)
        if not subdirs and not files:
            self.file_list.addItem("папка пуста")

    def open_from_browser(self, item):
        if item is None:
            return
        data = item.data(Qt.UserRole)
        if not data:
            return
        kind, path = data
        if kind == "dir":
            self.set_dir(path)
            return
        if path.lower().endswith(".pdf"):
            try:
                doc = fitz.open(path)
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Не удалось открыть PDF:\n{e}")
                return
            self._set_document(doc, path)
        else:
            self._open_image_paths([path])

    def file_menu(self, pos):
        item = self.file_list.itemAt(pos)
        if item is None or not item.data(Qt.UserRole):
            return
        kind, path = item.data(Qt.UserRole)
        menu = QMenu(self)
        if kind == "dir":
            menu.addAction("Открыть папку", lambda: self.set_dir(path))
            menu.addAction("Открыть в новой вкладке", lambda: self._tab_for(path))
        else:
            menu.addAction("Открыть", lambda: self.open_from_browser(item))
            menu.addSeparator()
            menu.addAction("Показать метаданные", lambda: self._meta_for_file(path))
        menu.exec(self.file_list.mapToGlobal(pos))

    def _tab_for(self, path):
        if path in self._dirs:
            self.dir_tabs.setCurrentIndex(self._dirs.index(path))
            return
        self._add_tab_silent(path)
        self.dir_tabs.setCurrentIndex(self.dir_tabs.count() - 1)
        self.remember_dirs()

    def _meta_for_file(self, path):
        try:
            d = fitz.open(path)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))
            return
        MetadataDialog(dict(d.metadata or {}), os.path.basename(path), self).exec()
        d.close()

    def organize_pages(self):
        if self.doc is None:
            QMessageBox.information(self, "Нет документа",
                                    "Сначала откройте PDF или отсканируйте документ.")
            return
        dlg = PageOrganizer(self.doc, self)
        if dlg.exec() != QDialog.Accepted:
            return
        remap = dlg.page_mapping()
        new_doc = dlg.result_doc()
        old_stamps = list(self.stamps)
        for s in old_stamps:
            self.scene.removeItem(s)
        self.stamps = []
        if self.page_item is not None:
            self.scene.removeItem(self.page_item)
            self.page_item = None
        self.doc.close()
        self.doc = new_doc
        for s in old_stamps:
            if s.page_index in remap:
                s.page_index = remap[s.page_index]
                self.scene.addItem(s)
                self.stamps.append(s)
        self.refresh_page_list(0)
        self.show_page(0)
        self._update_ui_state()

    def crop_page(self):
        if self.doc is None:
            QMessageBox.information(self, "Нет документа",
                                    "Сначала откройте PDF или отсканируйте документ.")
            return
        idx = max(0, self.page_list.currentRow())
        dlg = CropDialog(self.doc, idx, self)
        if dlg.exec() != QDialog.Accepted:
            return
        if dlg.crop_rect() is None:
            QMessageBox.information(self, "Слишком много",
                                    "После такой обрезки от страницы почти ничего "
                                    "не останется. Уменьшите поля.")
            return
        mm = dlg.margins_mm()
        targets = list(range(self.doc.page_count)) if dlg.chk_all.isChecked() else [idx]
        for i in targets:
            page = self.doc[i]
            r = page.rect
            new = fitz.Rect(r.x0 + mm["left"] * MM_TO_PT, r.y0 + mm["top"] * MM_TO_PT,
                            r.x1 - mm["right"] * MM_TO_PT, r.y1 - mm["bottom"] * MM_TO_PT)
            if new.width < 20 or new.height < 20:
                continue
            try:
                page.set_cropbox(page_cropbox_for_visible_rect(page, new))
            except Exception:
                continue
        dx = mm["left"] * MM_TO_PT / 72 * PREVIEW_DPI
        dy = mm["top"] * MM_TO_PT / 72 * PREVIEW_DPI
        for s in self.stamps:
            if s.page_index in targets:
                s.setPos(s.pos().x() - dx, s.pos().y() - dy)
        self.refresh_page_list(idx)
        self.show_page(idx)
        self.statusBar().showMessage("Страница обрезана", 4000)


    def frame_crop_page(self):
        """Кадрировать страницу рамкой (как в iLovePDF), с шаблонами размеров."""
        if self.doc is None:
            QMessageBox.information(self, "Нет документа",
                                    "Сначала откройте PDF или отсканируйте документ.")
            return
        idx = max(0, self.page_list.currentRow())
        dlg = FrameCropDialog(self.doc, idx, self, mode="crop")
        if dlg.exec() != QDialog.Accepted:
            return
        sel = dlg.selected_rects()[0]
        if sel.width < 20 or sel.height < 20:
            QMessageBox.information(self, "Слишком мало",
                                    "Рамка слишком маленькая. Нарисуйте её побольше.")
            return
        targets = list(range(self.doc.page_count)) if dlg.chk_all.isChecked() else [idx]
        done = 0
        for i in targets:
            page = self.doc[i]
            r = fitz.Rect(sel) & page.rect
            if r.is_empty or r.width < 20 or r.height < 20:
                continue
            try:
                page.set_cropbox(page_cropbox_for_visible_rect(page, r))
                done += 1
            except Exception:
                continue
            dx = r.x0 / 72 * PREVIEW_DPI
            dy = r.y0 / 72 * PREVIEW_DPI
            for s in self.stamps:
                if s.page_index == i:
                    s.setPos(s.pos().x() - dx, s.pos().y() - dy)
        self.refresh_page_list(idx)
        self.show_page(idx)
        self.statusBar().showMessage(
            f"Обрезано страниц: {done}" if done != 1 else "Страница обрезана", 4000)

    def split_page_two(self):
        """Разрезать страницу на две «бумаги» и разложить их на одном скане."""
        if self.doc is None:
            QMessageBox.information(self, "Нет документа",
                                    "Сначала откройте PDF или отсканируйте документ.")
            return
        idx = max(0, self.page_list.currentRow())
        dlg = FrameCropDialog(self.doc, idx, self, mode="split")
        if dlg.exec() != QDialog.Accepted:
            return
        rects = dlg.selected_rects()
        opts = dlg.split_options()
        replace = dlg.chk_replace.isChecked()
        page = self.doc[idx]
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            new, moves = build_split_doc(page, rects, opts["place"], opts["rot"], opts["dpi"],
                                         opts.get("bg", "builtin"), opts.get("bg_file"))
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "Ошибка", f"Не удалось разделить страницу:\n{e}")
            return
        try:
            self.doc.insert_pdf(new, start_at=idx + 1)
            new.close()
            if replace:
                self.doc.delete_page(idx)
        finally:
            QApplication.restoreOverrideCursor()
        keep = []
        for s in list(self.stamps):
            if s.page_index > idx:
                s.page_index += 0 if replace else 1
                keep.append(s)
            elif s.page_index == idx and replace:
                # печать уезжает вместе с той бумагой, на которой лежит её центр
                c = s.center_scene_pos()
                pt = fitz.Point(c.x() * 72 / PREVIEW_DPI, c.y() * 72 / PREVIEW_DPI)
                placed = False
                if opts["rot"] == 0:
                    for k, r in enumerate(rects):
                        if r.contains(pt) and k < len(moves):
                            dx, dy, sc = moves[k]
                            nx = (r.x0 + dx + (pt.x - r.x0) * sc) / 72 * PREVIEW_DPI
                            ny = (r.y0 + dy + (pt.y - r.y0) * sc) / 72 * PREVIEW_DPI
                            s.setPos(s.pos().x() + nx - c.x(), s.pos().y() + ny - c.y())
                            keep.append(s)
                            placed = True
                            break
                if not placed:
                    self.scene.removeItem(s)
            else:
                keep.append(s)
        self.stamps = keep
        self.refresh_page_list(idx)
        self.show_page(idx)
        self._update_ui_state()
        self.statusBar().showMessage("Страница разрезана на две бумаги на одном скане", 4000)


    def scan_look(self):
        """Сделать документ «как напечатали и отсканировали»."""
        if self.doc is None:
            QMessageBox.information(self, "Нет документа",
                                    "Сначала откройте PDF или отсканируйте документ.")
            return
        idx = max(0, self.page_list.currentRow())
        try:
            src = fitz.open("pdf", self._stamped_pdf_bytes())   # печати впечатываются
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось подготовить документ:\n{e}")
            return
        base = None
        if self.stamps:
            try:
                base = fitz.open("pdf", self.doc.tobytes())      # тот же документ без печатей
                if base.page_count != src.page_count:
                    base = None
            except Exception:
                base = None
        pre = sorted({self.page_list.row(it) for it in self.page_list.selectedItems()})
        dlg = ScanLookDialog(src, min(idx, src.page_count - 1), self, base_doc=base,
                             preselect=pre)
        if dlg.exec() != QDialog.Accepted:
            src.close()
            return
        o = dlg.options()
        pages = o["pages"] or [idx]
        prog = QProgressDialog("Делаю «скан»…", None, 0, src.page_count, self)
        prog.setWindowModality(Qt.WindowModal)
        prog.setMinimumDuration(0)
        try:
            new = build_scan_look_doc(src, pages, o["dpi"], o["preset"], o["color"], o["seed"],
                                      progress=lambda i: (prog.setValue(i),
                                                          QApplication.processEvents()),
                                      show_bed=o["bed"], show_back=False, base_doc=base)
        except Exception as e:
            prog.close()
            src.close()
            QMessageBox.critical(self, "Ошибка", f"Не получилось:\n{e}")
            return
        prog.setValue(src.page_count)
        prog.close()
        src.close()
        n = self.doc.page_count
        self.doc.insert_pdf(new)
        self.doc.delete_pages(0, n - 1)
        new.close()
        for s in list(self.stamps):           # печати уже внутри листов
            try:
                self.scene.removeItem(s)
            except Exception:
                pass
        self.stamps = []
        self.refresh_page_list(idx)
        self.show_page(idx)
        self._update_ui_state()
        self.show_toast(f"✔  Готово — страниц «как скан»: {len(pages)}. Сохраните (Ctrl+S)")


    # ---------------------------------------------------------- ручка
    def toggle_pen(self):
        if self.view.pen_active():
            self.pen_finish(commit=True)
        else:
            self.pen_start()

    def pen_start(self):
        if self.doc is None:
            QMessageBox.information(self, "Нет документа",
                                    "Сначала откройте PDF или отсканируйте документ.")
            self.act_pen.setChecked(False)
            return
        layer = PenLayer(self.scene.sceneRect())
        self.scene.addItem(layer)
        self.scene.clearSelection()
        bar = PenBar(self.view, self._pen_changed, self.pen_undo, self.pen_clear,
                     lambda: self.pen_finish(True), lambda: self.pen_finish(False))
        self.view.pen_layer = layer
        self.view.pen_bar = bar
        self.view.on_pen_key = self._pen_key
        layer.color = bar.ink()
        self.view.setDragMode(QGraphicsView.NoDrag)
        self.view.viewport().setCursor(Qt.CrossCursor)
        bar.show()
        self.view.place_pen_bar()
        self.view.setFocus()
        self.act_pen.setChecked(True)
        self.statusBar().showMessage(
            "Ручка: ведите мышью с зажатой левой кнопкой • Ctrl+Z — отменить штрих • "
            "Enter — готово • Esc — выйти")

    def _pen_changed(self):
        layer = self.view.pen_layer
        if layer is not None and self.view.pen_bar is not None:
            layer.color = self.view.pen_bar.ink()
            layer.update()

    def _pen_key(self, event):
        if event.key() == Qt.Key_Escape:
            self.pen_finish(False)
            return True
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.pen_finish(True)
            return True
        if event.key() == Qt.Key_Z and (event.modifiers() & Qt.ControlModifier):
            self.pen_undo()
            return True
        return False

    def pen_undo(self):
        layer = self.view.pen_layer
        if layer is not None and layer.strokes:
            layer.strokes.pop()
            layer.update()

    def pen_clear(self):
        layer = self.view.pen_layer
        if layer is not None:
            layer.strokes = []
            layer.update()

    def pen_finish(self, commit=True):
        """Выйти из режима ручки; commit — оставить нарисованное как подпись."""
        layer, bar = self.view.pen_layer, self.view.pen_bar
        if layer is None:
            return
        made = None
        if commit and layer.strokes:
            try:
                made = self._pen_to_stamp(layer)
            except Exception as e:
                QMessageBox.warning(self, "Ручка", f"Не удалось сохранить подпись:\n{e}")
        self.view.pen_layer = None
        self.view.pen_bar = None
        self.scene.removeItem(layer)
        if bar is not None:
            bar.hide()
            bar.deleteLater()
        self.view.setDragMode(QGraphicsView.RubberBandDrag)
        self.view.viewport().unsetCursor()
        self.act_pen.setChecked(False)
        self._update_ui_state()
        if made is not None:
            self.scene.clearSelection()
            made.setSelected(True)
            self.show_toast("✔  Подпись на странице. Чтобы ставить её снова — «В библиотеку»")

    def _pen_to_stamp(self, layer):
        """Нарисованные штрихи → прозрачная картинка → обычная «печать» на странице."""
        xs, ys, pad = [], [], 4.0
        for st in layer.strokes:
            st["dense"] = st.get("dense") or pen_dense_points(st["pts"])
            for x, y, wd in st["dense"]:
                xs += [x - wd, x + wd]
                ys += [y - wd, y + wd]
        if not xs:
            return None
        x0, y0, x1, y1 = min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad
        scale = 3.0                                    # 450 dpi — линия гладкая при любом зуме
        w_px, h_px = max(4, int((x1 - x0) * scale)), max(4, int((y1 - y0) * scale))
        img = QImage(w_px, h_px, QImage.Format_ARGB32_Premultiplied)
        img.fill(Qt.transparent)
        p = QPainter(img)
        p.scale(scale, scale)
        p.translate(-x0, -y0)
        pen_paint_strokes(p, layer.strokes, layer.color)
        p.end()
        img = img.convertToFormat(QImage.Format_RGBA8888)
        pil = Image.frombuffer("RGBA", (img.width(), img.height()),
                               bytes(img.constBits()), "raw", "RGBA", img.bytesPerLine(), 1).copy()
        mm_w = (x1 - x0) / PREVIEW_DPI * 25.4
        mm_h = (y1 - y0) / PREVIEW_DPI * 25.4
        pm = self._pixmap_from_pil(pil)
        item = StampItem(pm, pil, mm_w, mm_h, self.current_page)
        item.opacity_value = 1.0
        item.setOpacity(1.0)
        self.scene.addItem(item)
        item.setPos(x0, y0)
        self.stamps.append(item)
        # подпись становится «текущей печатью» — её можно сохранить в библиотеку
        self.stamp_raw = pil
        self.stamp_src_path = None
        self.current_lib_file = None
        self.stamp_pil = pil
        self.stamp_pixmap = pm
        self.stamp_status = "подпись ручкой"
        for sp, v in ((self.spin_w, mm_w), (self.spin_h, mm_h)):
            sp.blockSignals(True)
            sp.setValue(v)
            sp.blockSignals(False)
        self.slider_op.blockSignals(True)
        self.slider_op.setValue(100)
        self.slider_op.blockSignals(False)
        self.lbl_op.setText("Непрозрачность: 100%")
        self.stamp_info.setText("подпись ручкой")
        try:
            self.preview.setPixmap(pm.scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        except Exception:
            pass
        return item


    # ---------------------------------------------------------- память размера печати
    def _lib_target_file(self):
        """Чью запись в библиотеке обновлять: выделенной на странице печати или текущей."""
        try:
            sel = [i for i in self.scene.selectedItems() if isinstance(i, StampItem)]
        except RuntimeError:
            sel = []
        if sel:
            return getattr(sel[0], "lib_file", None)
        return getattr(self, "current_lib_file", None)

    def _remember_stamp_later(self):
        """Отложенная запись — чтобы не писать на диск на каждое движение ползунка."""
        if not self._lib_target_file():
            return
        t = getattr(self, "_remember_timer", None)
        if t is None:
            t = QTimer(self)
            t.setSingleShot(True)
            t.timeout.connect(self._remember_stamp_now)
            self._remember_timer = t
        t.start(500)

    def _remember_stamp_now(self):
        """Записать в библиотеку текущие размер/поворот/непрозрачность этой печати."""
        target = self._lib_target_file()
        if not target:
            return
        try:
            items = lib_load()
            changed = None
            for e in items:
                if e.get("file") == target:
                    new = {"mm_w": round(self.spin_w.value(), 1),
                           "mm_h": round(self.spin_h.value(), 1),
                           "rot": int(self.slider_rot.value()),
                           "opacity": int(self.slider_op.value())}
                    if any(e.get(k) != v for k, v in new.items()):
                        e.update(new)
                        changed = e
                    break
            if changed is None:
                return
            lib_save(items)
            for i in range(self.lib_list.count()):
                it = self.lib_list.item(i)
                d = it.data(Qt.UserRole)
                if d and d.get("file") == target:
                    it.setData(Qt.UserRole, changed)
                    it.setToolTip(f"{changed['name']} — {changed['mm_w']:g}×{changed['mm_h']:g} мм\n"
                                  f"категория: {changed.get('category') or 'Без категории'}\n"
                                  "размер запоминается за этой печатью")
            self.statusBar().showMessage(
                f"Размер {changed['mm_w']:g}×{changed['mm_h']:g} мм запомнен за печатью "
                f"«{changed['name']}»", 3500)
        except Exception:
            pass

    def rotate_page(self, delta, all_pages=False):
        """Повернуть страницу (или все) на 90°. Печати поворачиваются вместе."""
        if self.doc is None:
            QMessageBox.information(self, "Нет документа",
                                    "Сначала откройте PDF или отсканируйте документ.")
            return
        idx = range(self.doc.page_count) if all_pages else [self.page_list.currentRow()]
        idx = [i for i in idx if 0 <= i < self.doc.page_count]
        if not idx:
            return
        for i in idx:
            page = self.doc[i]
            old_rect = page.rect
            page.set_rotation((page.rotation + delta) % 360)
            for s in self.stamps:
                if s.page_index != i:
                    continue
                c = s.center_scene_pos()
                w_px = old_rect.width / 72 * PREVIEW_DPI
                h_px = old_rect.height / 72 * PREVIEW_DPI
                if delta > 0:
                    nx, ny = h_px - c.y(), c.x()
                else:
                    nx, ny = c.y(), w_px - c.x()
                s.setRotation((s.rotation() + delta) % 360)
                pm_w = s.pixmap().width() * s.transform().m11()
                pm_h = s.pixmap().height() * s.transform().m22()
                s.setPos(nx - pm_w / 2, ny - pm_h / 2)
        cur = self.page_list.currentRow()
        self.refresh_page_list(max(0, cur))
        self.show_page(max(0, cur))

    def refresh_page_list(self, current=0):
        """Перестроить список страниц с миниатюрами."""
        self.page_list.blockSignals(True)
        self.page_list.clear()
        if self.doc is not None:
            for i in range(self.doc.page_count):
                pix = self.doc[i].get_pixmap(dpi=24, alpha=False)
                img = QImage(pix.samples, pix.width, pix.height, pix.stride,
                             QImage.Format_RGB888)
                pm = QPixmap.fromImage(img.copy()).scaled(
                    104, 140, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                it = QListWidgetItem(QIcon(pm), f"стр. {i + 1}")
                it.setData(Qt.UserRole, i)
                it.setTextAlignment(Qt.AlignHCenter)
                self.page_list.addItem(it)
        self.page_list.blockSignals(False)
        if self.doc is not None and self.doc.page_count:
            current = max(0, min(current, self.doc.page_count - 1))
            self.page_list.setCurrentRow(current)

    def apply_page_order(self, order):
        """Применить новый порядок/набор страниц (список старых индексов)."""
        if self.doc is None:
            return
        remap = {old: new for new, old in enumerate(order)}
        self.doc.select(order)
        kept = []
        for s in self.stamps:
            if s.page_index in remap:
                s.page_index = remap[s.page_index]
                kept.append(s)
            else:
                self.scene.removeItem(s)
        self.stamps = kept
        new_current = remap.get(self.current_page, 0)
        self.refresh_page_list(new_current)
        self.show_page(new_current)

    def _pages_dragged(self, *args):
        order = [self.page_list.item(i).data(Qt.UserRole)
                 for i in range(self.page_list.count())]
        self.apply_page_order(order)

    def move_page(self, delta):
        if self.doc is None:
            return
        i = self.page_list.currentRow()
        j = i + delta
        if i < 0 or j < 0 or j >= self.doc.page_count:
            return
        order = list(range(self.doc.page_count))
        order[i], order[j] = order[j], order[i]
        self.current_page = i
        self.apply_page_order(order)
        self.page_list.setCurrentRow(j)

    def delete_page(self):
        if self.doc is None:
            return
        i = self.page_list.currentRow()
        if i < 0:
            return
        if self.doc.page_count == 1:
            QMessageBox.information(self, "Нельзя",
                                    "Это единственная страница. Чтобы убрать документ, "
                                    "нажмите «Закрыть документ».")
            return
        n_stamps = sum(1 for s in self.stamps if s.page_index == i)
        msg = f"Удалить страницу {i + 1}?"
        if n_stamps:
            msg += f"\nНа ней стоят печати ({n_stamps} шт.) — они тоже удалятся."
        if QMessageBox.question(self, "Удаление страницы", msg) != QMessageBox.Yes:
            return
        order = [k for k in range(self.doc.page_count) if k != i]
        self.apply_page_order(order)

        # ---- правая панель: всё про печать, без прокрутки ----
    def _build_right_panel(self):
        dock = QDockWidget("ПЕЧАТЬ", self)
        dock.setFeatures(QDockWidget.NoDockWidgetFeatures)
        dock.setTitleBarWidget(QWidget())
        panel = QWidget()
        lay = QVBoxLayout(panel)
        ptitle = QLabel("ПЕЧАТЬ")
        ptitle.setObjectName("paneltitle")
        lay.addWidget(ptitle)
        lay.setContentsMargins(10, 6, 10, 8)
        lay.setSpacing(7)

        def cap(text, w=64):
            lbl = QLabel(text)
            lbl.setMinimumWidth(w)
            return lbl

        def hrow(*widgets, spacing=6):
            h = QHBoxLayout()
            h.setSpacing(spacing)
            for wd in widgets:
                h.addWidget(wd)
            return h

        # === библиотека: плитка иконок ===
        gb_lib = QGroupBox("Мои печати")
        ll = QVBoxLayout(gb_lib)
        ll.setContentsMargins(8, 4, 8, 6)
        ll.setSpacing(5)
        self.combo_cat = QComboBox()
        self.combo_cat.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.combo_cat.setMinimumContentsLength(12)
        self.combo_cat.setToolTip("Показывать печати выбранной категории")
        self.combo_cat.currentIndexChanged.connect(lambda _=0: self.reload_library())
        ll.addLayout(hrow(cap("Категория:", 74), self.combo_cat))

        self.lib_list = ColumnGrid(columns=3, min_cell=84)
        self.lib_list.setSpacing(3)
        self.lib_list.max_icon = 48
        self.lib_list.min_rows = 2              # два ряда печатей видны всегда
        self.lib_list.setWordWrap(False)
        self.lib_list.setMinimumHeight(178)
        self.lib_list.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self.lib_list.itemDoubleClicked.connect(self.lib_pick)
        self.lib_list.itemClicked.connect(self.lib_pick)
        self.lib_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.lib_list.customContextMenuRequested.connect(self.lib_menu)
        ll.addWidget(self.lib_list)

        self._themed_buttons = getattr(self, "_themed_buttons", [])
        b_add = QPushButton(" Добавить")
        b_add.setToolTip("Добавить печать в библиотеку из файла")
        b_add.setIconSize(QSize(15, 15))
        b_add.clicked.connect(self.add_file_to_library)
        self._themed_buttons.append((b_add, "plus", False))
        b_save = QPushButton(" В библиотеку")
        b_save.setToolTip("Сохранить текущую печать с её размером")
        b_save.setIconSize(QSize(15, 15))
        b_save.clicked.connect(self.save_to_library)
        self._themed_buttons.append((b_save, "star", False))
        self.btn_save_lib = b_save
        b_del = QPushButton()
        b_del.setFixedWidth(36)
        b_del.setIconSize(QSize(15, 15))
        b_del.setToolTip("Удалить выбранную печать из библиотеки")
        b_del.clicked.connect(self.lib_delete)
        self._themed_buttons.append((b_del, "trash", False))
        ll.addLayout(hrow(b_add, b_save, b_del))
        lay.addWidget(gb_lib, 1)

        # === текущая печать: превью слева, параметры справа ===
        gb_stamp = QGroupBox("Файл, фон и краска")
        self.gb_stamp = gb_stamp
        gb_stamp.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        sl = QVBoxLayout(gb_stamp)
        sl.setContentsMargins(8, 4, 8, 6)
        sl.setSpacing(5)

        self.preview = QLabel()
        self.preview.setFixedSize(72, 72)
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setStyleSheet(
            "background: #ffffff; color: #9a9486; border: 1px solid #d8d2c4; "
            "border-radius: 8px;")
        self.preview.setText("нет\nпечати")

        right_col = QVBoxLayout()
        right_col.setSpacing(6)
        self.btn_load_stamp = QPushButton(" Загрузить файл…")
        self.btn_load_stamp.setIconSize(QSize(15, 15))
        self.btn_load_stamp.clicked.connect(self.load_stamp)
        self._themed_buttons.append((self.btn_load_stamp, "folder", False))
        right_col.addWidget(self.btn_load_stamp)

        self.stamp_info = QLabel("файл не загружен")
        self.stamp_info.setObjectName("stampinfo")
        self.stamp_info.setWordWrap(True)
        self.stamp_info.setFixedHeight(28)
        right_col.addWidget(self.stamp_info)

        self.chk_bg = QCheckBox("убирать фон")
        self.chk_bg.setChecked(True)
        self.chk_bg.stateChanged.connect(self.reprocess_stamp)
        right_col.addWidget(self.chk_bg)
        right_col.addStretch()

        top_row = QHBoxLayout()
        top_row.setSpacing(10)
        top_row.addWidget(self.preview)
        top_row.addLayout(right_col, 1)
        sl.addLayout(top_row)

        self.lbl_thr = QLabel("Очистка фона: 10")
        self.lbl_thr.setMinimumWidth(126)
        self.slider_thr = QSlider(Qt.Horizontal)
        self.slider_thr.setRange(0, 100)
        self.slider_thr.setValue(10)
        self.slider_thr.valueChanged.connect(self.reprocess_stamp)
        sl.addLayout(hrow(self.lbl_thr, self.slider_thr))

        self.combo_ink = QComboBox()
        self.combo_ink.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.combo_ink.setMinimumContentsLength(12)
        self.combo_ink.addItem("Цвет как в файле", "file")
        self.combo_ink.addItem("Синяя", "blue")
        self.combo_ink.addItem("Фиолетовая", "violet")
        self.combo_ink.addItem("Чёрная", "black")
        self.combo_ink.currentIndexChanged.connect(self.reprocess_stamp)
        sl.addLayout(hrow(cap("Краска:"), self.combo_ink))

        # === размер и вид ===
        gb_geom = QGroupBox("Размер и наклон")
        gb_geom.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        gl = QVBoxLayout(gb_geom)
        gl.setContentsMargins(8, 4, 8, 6)
        gl.setSpacing(5)

        self.preset_box = QComboBox()
        self.preset_box.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.preset_box.setMinimumContentsLength(14)
        for name, w, h in PRESETS:
            self.preset_box.addItem(name, (w, h))
        self.preset_box.currentIndexChanged.connect(self.preset_changed)
        gl.addLayout(hrow(cap("Пресет:"), self.preset_box))

        self.spin_w = QDoubleSpinBox()
        self.spin_w.setRange(3, 300); self.spin_w.setValue(40)
        self.spin_w.setSuffix(" мм"); self.spin_w.setDecimals(1)
        self.spin_w.setMinimumWidth(88)
        self.spin_h = QDoubleSpinBox()
        self.spin_h.setRange(3, 300); self.spin_h.setValue(40)
        self.spin_h.setSuffix(" мм"); self.spin_h.setDecimals(1)
        self.spin_h.setMinimumWidth(88)
        self.spin_w.valueChanged.connect(lambda v: self.size_changed("w"))
        self.spin_h.valueChanged.connect(lambda v: self.size_changed("h"))
        self.chk_lock = QCheckBox("проп.")
        self.chk_lock.setChecked(True)
        self.chk_lock.setToolTip("Сохранять пропорции печати")
        gl.addLayout(hrow(cap("Ш×В:", 40), self.spin_w, self.spin_h, self.chk_lock))

        self.lbl_rot = QLabel("Поворот: 0°")
        self.lbl_rot.setMinimumWidth(120)
        self.slider_rot = QSlider(Qt.Horizontal)
        self.slider_rot.setRange(-180, 180)
        self.slider_rot.valueChanged.connect(self.rotation_changed)
        gl.addLayout(hrow(self.lbl_rot, self.slider_rot))

        self.lbl_op = QLabel("Непрозрачность: 85%")
        self.lbl_op.setMinimumWidth(120)
        self.slider_op = QSlider(Qt.Horizontal)
        self.slider_op.setRange(20, 100); self.slider_op.setValue(85)
        self.slider_op.valueChanged.connect(self.opacity_changed)
        gl.addLayout(hrow(self.lbl_op, self.slider_op))
        lay.addWidget(gb_geom)

        # редкие настройки свёрнуты: готовым печатям они не нужны
        self.btn_adv = QToolButton()
        self.btn_adv.setObjectName("section")
        self.btn_adv.setText(" ФАЙЛ, ФОН И КРАСКА ПЕЧАТИ")
        self.btn_adv.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.btn_adv.setIconSize(QSize(12, 12))
        self.btn_adv.setCheckable(True)
        self.btn_adv.setCursor(Qt.PointingHandCursor)
        self.btn_adv.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.btn_adv.setToolTip("Загрузить печать из файла, убрать фон, перекрасить")
        self.btn_adv.setChecked(bool(settings_load().get("stamp_adv_open", False)))
        self.btn_adv.toggled.connect(lambda on: self._adv_toggle(on))
        lay.addWidget(self.btn_adv)
        lay.addWidget(gb_stamp)
        gb_stamp.setVisible(self.btn_adv.isChecked())

        # === главная кнопка ===
        self.btn_add = QPushButton("  ПОСТАВИТЬ ПЕЧАТЬ")
        self.btn_add.setObjectName("accent")
        self.btn_add.setMinimumHeight(40)
        self.btn_add.setToolTip("Поставить выбранную печать на текущую страницу")
        self.btn_add.setIconSize(QSize(19, 19))
        self.btn_add.clicked.connect(self.add_stamp)
        self._themed_buttons.append((self.btn_add, "stamp", True))
        self.btn_add.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        # DPI спрашиваем в момент экспорта — панель не захламляем
        self.spin_dpi = QSpinBox(panel)   # хранит выбранный DPI, в панели не показывается
        self.spin_dpi.setRange(72, 600)
        self.spin_dpi.setValue(300)
        self.spin_dpi.setVisible(False)
        lay.addStretch(0)

        # содержимое — в области, которая при нехватке высоты прокручивается,
        # а главная кнопка закреплена снизу и видна всегда
        scroll = QScrollArea()
        scroll.setWidget(panel)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        holder = QWidget()
        hl = QVBoxLayout(holder)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(0)
        hl.addWidget(scroll, 1)

        foot = QWidget()
        fl2 = QVBoxLayout(foot)
        fl2.setContentsMargins(10, 8, 10, 10)
        fl2.addWidget(self.btn_add)
        hl.addWidget(foot, 0)

        dock.setWidget(holder)
        dock.setFixedWidth(372)
        self.addDockWidget(Qt.RightDockWidgetArea, dock)

    def _adv_toggle(self, on, save=True):
        """Свернуть/развернуть блок «Файл, фон и краска»."""
        self.gb_stamp.setVisible(bool(on))
        self.btn_adv.setIcon(draw_icon("chev_down" if on else "chev_right", self._icon_color()))
        if save:
            try:
                st = settings_load()
                st["stamp_adv_open"] = bool(on)
                settings_save(st)
            except Exception:
                pass

    def show_guide(self):
        """Открыть иллюстрированное руководство."""
        dlg = getattr(self, "_guide", None)
        if dlg is None:
            dlg = GuideDialog(self)
            self._guide = dlg
        else:
            dlg._show(dlg.nav.currentRow())
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def _update_ui_state(self):
        has_doc = self.doc is not None
        has_stamp = self.stamp_pil is not None
        self.btn_add.setEnabled(has_doc and has_stamp)
        self.btn_save_lib.setEnabled(has_stamp)
        for act in (getattr(self, "act_save", None), getattr(self, "act_png", None),
                    getattr(self, "act_org", None), getattr(self, "act_close", None),
                    getattr(self, "act_save_as", None), getattr(self, "act_pen", None),
                    getattr(self, "act_scanlook", None)):
            if act is not None:
                act.setEnabled(has_doc)
        for act in getattr(self, "_doc_actions", []):
            act.setEnabled(has_doc)
        if hasattr(self, "statusBar") and self.statusBar():
            if not has_doc:
                self.statusBar().showMessage(
                    "Откройте PDF или отсканируйте документ — кнопка «Открыть» слева вверху")
            elif not has_stamp:
                self.statusBar().showMessage(
                    "Выберите печать в «Мои печати» или загрузите файл печати")
            else:
                self.statusBar().showMessage(
                    "Печать двигается мышкой • Ctrl+колесо — зум • Del — удалить • "
                    "Ctrl+S — сохранить с именем файла")

    # ---------------- библиотека печатей ----------------

    def _refresh_categories(self):
        cats = lib_categories()
        current = self.combo_cat.currentData()
        self.combo_cat.blockSignals(True)
        self.combo_cat.clear()
        self.combo_cat.addItem("Все категории", None)
        for c in cats:
            self.combo_cat.addItem(c, c)
        idx = self.combo_cat.findData(current)
        self.combo_cat.setCurrentIndex(idx if idx >= 0 else 0)
        self.combo_cat.blockSignals(False)

    def reload_library(self):
        self._refresh_categories()
        self.lib_list.fit_grid()
        self.lib_list.clear()
        entries = lib_load()
        chosen = self.combo_cat.currentData()
        if chosen:
            entries = [e for e in entries
                       if (e.get("category") or "Без категории") == chosen]
        if not entries:
            empty = QListWidgetItem("пусто")
            empty.setFlags(Qt.NoItemFlags)
            self.lib_list.addItem(empty)
            return
        for entry in entries:
            name = self.lib_list.fontMetrics().elidedText(
                entry['name'], Qt.ElideRight, max(40, self.lib_list.gridSize().width() - 10))
            it = QListWidgetItem(name)
            it.setData(Qt.UserRole, entry)
            it.setTextAlignment(Qt.AlignHCenter | Qt.AlignBottom)
            it.setToolTip(f"{entry['name']} — {entry['mm_w']:g}×{entry['mm_h']:g} мм\n"
                          f"категория: {entry.get('category') or 'Без категории'}")
            pm = QPixmap(entry["file"])
            if not pm.isNull():
                side = max(48, self.lib_list.iconSize().width()) * 2      # ×2 — чётко на любом экране
                chip = QPixmap(side, side)
                chip.fill(Qt.transparent)
                qp = QPainter(chip)
                qp.setRenderHint(QPainter.Antialiasing)
                qp.setRenderHint(QPainter.SmoothPixmapTransform)
                qp.setPen(QPen(QColor(0, 0, 0, 28), 1))
                qp.setBrush(QColor(255, 255, 255))
                qp.drawRoundedRect(QRectF(1, 1, side - 2, side - 2), side * 0.14, side * 0.14)
                inner = pm.scaled(int(side * 0.82), int(side * 0.82), Qt.KeepAspectRatio,
                                  Qt.SmoothTransformation)
                qp.drawPixmap((side - inner.width()) // 2, (side - inner.height()) // 2, inner)
                qp.end()
                it.setIcon(QIcon(chip))
            self.lib_list.addItem(it)

    def lib_pick(self, item):
        if item is None:
            return
        entry = item.data(Qt.UserRole)
        if not entry:
            return
        self._load_stamp_file(entry["file"], from_library=True)
        self.current_lib_file = entry["file"]
        self.scene.clearSelection()
        ws = (self.spin_w, self.spin_h, self.slider_rot, self.slider_op)
        for wd in ws:
            wd.blockSignals(True)
        self.spin_w.setValue(entry["mm_w"]); self.spin_h.setValue(entry["mm_h"])
        self.slider_rot.setValue(int(entry.get("rot", 0)))
        self.slider_op.setValue(int(entry.get("opacity", 85)))
        for wd in ws:
            wd.blockSignals(False)
        self.lbl_rot.setText(f"Поворот: {self.slider_rot.value()}°")
        self.lbl_op.setText(f"Непрозрачность: {self.slider_op.value()}%")
        self.stamp_info.setText(f"{entry['name']} · {entry['mm_w']:g}×{entry['mm_h']:g} мм\n"
                                "размер запоминается за этой печатью")
        try:
            self.preview.setPixmap(self.stamp_pixmap.scaled(
                64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        except Exception:
            pass
        self._update_ui_state()

    def lib_menu(self, pos):
        item = self.lib_list.itemAt(pos)
        if item is None or not item.data(Qt.UserRole):
            return
        entry = item.data(Qt.UserRole)
        menu = QMenu(self)
        menu.addAction("Использовать", lambda: self.lib_pick(item))
        menu.addAction("Сменить категорию…", lambda: self.lib_set_category(entry))
        menu.addAction("Переименовать…", lambda: self.lib_rename(entry))
        menu.addSeparator()
        menu.addAction("Удалить", self.lib_delete)
        menu.exec(self.lib_list.mapToGlobal(pos))

    def _lib_update(self, entry, **changes):
        items = lib_load()
        for e in items:
            if e["file"] == entry["file"]:
                e.update(changes)
        lib_save(items)
        self.reload_library()

    def lib_set_category(self, entry):
        cats = lib_categories()
        cur = entry.get("category") or "Без категории"
        start = cats.index(cur) if cur in cats else 0
        cat, ok = QInputDialog.getItem(self, "Категория печати",
                                       "Выберите или впишите свою:", cats, start, True)
        if ok and cat.strip():
            self._lib_update(entry, category=cat.strip())

    def lib_rename(self, entry):
        name, ok = QInputDialog.getText(self, "Название печати", "Новое название:",
                                        text=entry.get("name", ""))
        if ok and name.strip():
            self._lib_update(entry, name=name.strip())

    def lib_delete(self):
        item = self.lib_list.currentItem()
        if item is None:
            return
        entry = item.data(Qt.UserRole)
        if not entry:
            return
        if QMessageBox.question(self, "Удалить", f"Удалить «{entry['name']}» из библиотеки?") != QMessageBox.Yes:
            return
        items = [s for s in lib_load() if s["file"] != entry["file"]]
        lib_save(items)
        try:
            os.remove(entry["file"])
        except OSError:
            pass
        self.reload_library()

    def save_to_library(self):
        """Сохранить текущую печать в библиотеку (из файла или из выбранной на странице)."""
        pil = self.stamp_pil
        mm_w, mm_h = self.spin_w.value(), self.spin_h.value()
        # если на странице выделена печать — берём её размеры
        sel = [i for i in self.scene.selectedItems() if isinstance(i, StampItem)]
        if sel:
            pil = sel[0].pil_image
            mm_w, mm_h = sel[0].mm_w, sel[0].mm_h
        if pil is None:
            QMessageBox.information(
                self, "Нет печати",
                "Сначала загрузите файл печати кнопкой «Загрузить новый файл печати…».")
            return

        default = ""
        if self.stamp_src_path:
            default = os.path.splitext(os.path.basename(self.stamp_src_path))[0]
        name, ok = QInputDialog.getText(self, "Название печати",
                                        "Как назвать печать?", text=default)
        if not ok or not name.strip():
            return
        cats = lib_categories()
        cur_cat = self.combo_cat.currentData() or "Без категории"
        start = cats.index(cur_cat) if cur_cat in cats else 0
        cat, ok2 = QInputDialog.getItem(self, "Категория печати",
                                        "К какой категории отнести?\n(можно вписать свою)",
                                        cats, start, True)
        if not ok2:
            return
        try:
            entry = lib_add(name.strip(), mm_w, mm_h, pil_image=pil,
                            category=(cat or "").strip())
            if sel:
                sel[0].lib_file = entry["file"]
            else:
                self.current_lib_file = entry["file"]
        except Exception as e:
            QMessageBox.critical(
                self, "Не удалось сохранить",
                f"Печать не сохранилась в библиотеку.\n\nПапка: {LIB_DIR}\nОшибка: {e}")
            return
        self.reload_library()
        self.show_toast(f"✔  «{name.strip()}» в «Мои печати» — размер {mm_w:g}×{mm_h:g} мм запомнен")

    def add_file_to_library(self):
        """Добавить печать в библиотеку прямо из блока «Мои печати»."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Файл печати", "", "Изображения (*.png *.jpg *.jpeg *.webp)")
        if not path:
            return
        if not self._load_stamp_file(path):
            return
        im = self.stamp_pil
        self.stamp_info.setText(f"{os.path.basename(path)} ({im.width}×{im.height}px)")
        self._update_ui_state()
        self.save_to_library()

    # ---------------- документ ----------------

    def open_pdf(self):
        path, _ = QFileDialog.getOpenFileName(self, "Открыть PDF",
                                              self.current_dir(), "PDF (*.pdf)")
        if not path:
            return
        try:
            doc = fitz.open(path)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось открыть PDF:\n{e}")
            return
        self._set_document(doc, path)

    def open_images_as_doc(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Открыть изображения", self.current_dir(),
            "Изображения (*.png *.jpg *.jpeg)")
        if not paths:
            return
        self._open_image_paths(paths)

    def _open_image_paths(self, paths):
        doc = fitz.open()
        for p in paths:
            with Image.open(p) as im:
                dpi = im.info.get("dpi", (300, 300))
                dx = dpi[0] or 300
                dy = dpi[1] or 300
                w_pt = im.width / dx * 72
                h_pt = im.height / dy * 72
            page = doc.new_page(width=w_pt, height=h_pt)
            page.insert_image(page.rect, filename=p)
        self._set_document(doc, paths[0] + " (из изображений)")

    def _set_document(self, doc, path):
        for s in self.stamps:
            self.scene.removeItem(s)
        self.stamps.clear()
        self.doc = doc
        self.doc_path = path
        self.compress_profile = None
        folder = os.path.dirname(str(path))
        if os.path.isdir(folder) and hasattr(self, "_dirs") and folder != self.current_dir():
            self.set_dir(folder)
        self.refresh_page_list(0)
        self.show_page(0)
        self.setWindowTitle(f"{APP_TITLE} {APP_VERSION} — {os.path.basename(str(path))}")
        self._update_ui_state()

    def close_document(self):
        if self.doc is None:
            return
        if self.view.pen_active():
            self.pen_finish(commit=True)
        if self.stamps:
            q = QMessageBox.question(
                self, "Закрыть документ",
                "На документе стоят печати, которые не были сохранены.\n"
                "Закрыть без сохранения?")
            if q != QMessageBox.Yes:
                return
        for s in self.stamps:
            self.scene.removeItem(s)
        self.stamps.clear()
        if self.page_item is not None:
            self.scene.removeItem(self.page_item)
            self.page_item = None
        self.doc.close()
        self.doc = None
        self.doc_path = None
        self.current_page = 0
        self.page_list.blockSignals(True)
        self.page_list.clear()
        self.page_list.blockSignals(False)
        self.scene.setSceneRect(QRectF(0, 0, 1, 1))
        self.setWindowTitle(f"{APP_TITLE} {APP_VERSION}")
        self.place_mascot()
        self._update_ui_state()

    def show_page(self, index):
        if self.doc is None or index < 0 or index >= self.doc.page_count:
            return
        if self.view.pen_active() and index != self.current_page:
            self.pen_finish(commit=True)
        self.current_page = index
        pix = self.doc[index].get_pixmap(dpi=PREVIEW_DPI, alpha=False)
        img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
        pm = QPixmap.fromImage(img.copy())
        if self.page_item is not None:
            self.scene.removeItem(self.page_item)
        self.page_item = self.scene.addPixmap(pm)
        self.page_item.setZValue(-1)
        self.scene.setSceneRect(QRectF(0, 0, pm.width(), pm.height()))
        if self.view.pen_layer is not None:
            self.view.pen_layer._rect = QRectF(0, 0, pm.width(), pm.height())
        for s in self.stamps:
            s.setVisible(s.page_index == index)
        self.view.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)
        self.place_mascot()

    # ---------------- печать ----------------

    def _load_stamp_file(self, path, from_library=False):
        try:
            im = Image.open(path).convert("RGBA")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось открыть изображение:\n{e}")
            return False
        self.stamp_raw = im
        self.stamp_src_path = None if from_library else path
        if not from_library:
            self.current_lib_file = None
        self.reprocess_stamp()
        return True

    def _pixmap_from_pil(self, im):
        buf = io.BytesIO()
        im.save(buf, "PNG")
        pm = QPixmap()
        pm.loadFromData(buf.getvalue(), "PNG")
        return pm

    def reprocess_stamp(self):
        """Пересобрать печать из оригинала с текущими настройками фона/цвета."""
        if getattr(self, "stamp_raw", None) is None:
            return
        self.lbl_thr.setText(f"Очистка фона: {self.slider_thr.value()}")
        try:
            im, had_alpha = prepare_stamp(
                self.stamp_raw,
                remove_bg=self.chk_bg.isChecked(),
                threshold=self.slider_thr.value(),
                ink=self.combo_ink.currentData())
        except Exception:
            im, had_alpha = self.stamp_raw, False
        self.stamp_pil = im
        self.stamp_status = ("✓ печать чистая" if had_alpha
                             else "подложка убрана автоматически")
        self.chk_bg.setEnabled(True)
        self.slider_thr.setEnabled(not had_alpha)
        self.stamp_pixmap = self._pixmap_from_pil(im)

        # пропорции обновляем под обрезанную картинку
        if self.chk_lock.isChecked() and im.width:
            self.spin_h.blockSignals(True)
            self.spin_h.setValue(round(self.spin_w.value() * im.height / im.width, 1))
            self.spin_h.blockSignals(False)

        # превью на белом фоне
        prev = im.copy()
        prev.thumbnail((110, 110), Image.LANCZOS)
        canvas = Image.new("RGBA", (114, 114), (255, 255, 255, 255))
        d = ImageDraw.Draw(canvas)          # шахматка = видно, где прозрачно
        cell = 10
        for yy in range(0, 114, cell):
            for xx in range(0, 114, cell):
                if (xx // cell + yy // cell) % 2:
                    d.rectangle([xx, yy, xx + cell - 1, yy + cell - 1],
                                fill=(236, 236, 236, 255))
        canvas.paste(prev, ((114 - prev.width) // 2, (114 - prev.height) // 2), prev)
        self.preview.setPixmap(self._pixmap_from_pil(canvas))

        # если печать уже стоит на странице и выделена — обновляем и её
        for it in self.scene.selectedItems():
            if isinstance(it, StampItem):
                it.pil_image = im
                it.setPixmap(self.stamp_pixmap)
                it.setTransformOriginPoint(self.stamp_pixmap.width() / 2,
                                           self.stamp_pixmap.height() / 2)
                it.mm_h = self.spin_h.value()
                it.apply_size()
        self._update_ui_state()

    def load_stamp(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Файл печати", "", "Изображения (*.png *.jpg *.jpeg *.webp)")
        if not path:
            return
        if not self._load_stamp_file(path):
            return
        im = self.stamp_raw
        try:
            self.preview.setPixmap(self.stamp_pixmap.scaled(
                64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        except Exception:
            pass
        self.stamp_info.setText(f"{os.path.basename(path)} — {im.width}×{im.height}px\n"
                                f"{getattr(self, 'stamp_status', '')}")
        self._update_ui_state()

    def preset_changed(self):
        w, h = self.preset_box.currentData()
        if w:
            self.spin_w.blockSignals(True); self.spin_h.blockSignals(True)
            self.spin_w.setValue(w); self.spin_h.setValue(h)
            self.spin_w.blockSignals(False); self.spin_h.blockSignals(False)
            self.apply_size_to_selection()

    def size_changed(self, which):
        if self.chk_lock.isChecked() and self.stamp_pil is not None:
            ratio = self.stamp_pil.height / self.stamp_pil.width
            if which == "w":
                self.spin_h.blockSignals(True)
                self.spin_h.setValue(self.spin_w.value() * ratio)
                self.spin_h.blockSignals(False)
            else:
                self.spin_w.blockSignals(True)
                self.spin_w.setValue(self.spin_h.value() / ratio)
                self.spin_w.blockSignals(False)
        self.preset_box.blockSignals(True)
        self.preset_box.setCurrentIndex(self.preset_box.count() - 1)
        self.preset_box.blockSignals(False)
        self.apply_size_to_selection()
        self._remember_stamp_later()

    def apply_size_to_selection(self):
        for it in self.scene.selectedItems():
            if isinstance(it, StampItem):
                it.mm_w = self.spin_w.value()
                it.mm_h = self.spin_h.value()
                it.apply_size()

    def rotation_changed(self, v):
        self.lbl_rot.setText(f"Поворот: {v}°")
        for it in self.scene.selectedItems():
            if isinstance(it, StampItem):
                it.setRotation(v)
        self._remember_stamp_later()

    def opacity_changed(self, v):
        self.lbl_op.setText(f"Непрозрачность: {v}%")
        for it in self.scene.selectedItems():
            if isinstance(it, StampItem):
                it.opacity_value = v / 100.0
                it.setOpacity(it.opacity_value)
        self._remember_stamp_later()

    def add_stamp(self):
        if self.doc is None:
            QMessageBox.information(self, "Нет документа",
                                    "Сначала откройте PDF или отсканируйте документ.")
            return
        if self.stamp_pil is None:
            QMessageBox.information(self, "Нет печати",
                                    "Выберите печать в «Мои печати» или загрузите файл.")
            return
        self.scene.clearSelection()
        self._remember_stamp_now()
        item = StampItem(self.stamp_pixmap, self.stamp_pil,
                         self.spin_w.value(), self.spin_h.value(), self.current_page)
        item.lib_file = getattr(self, "current_lib_file", None)
        item.setRotation(self.slider_rot.value())
        item.opacity_value = self.slider_op.value() / 100.0
        item.setOpacity(item.opacity_value)
        self.scene.addItem(item)
        center = self.view.mapToScene(self.view.viewport().rect().center())
        item.setPos(center.x() - item.pixmap().width() / 2 * item.transform().m11(),
                    center.y() - item.pixmap().height() / 2 * item.transform().m22())
        self.stamps.append(item)
        self.scene.clearSelection()
        item.setSelected(True)

    def delete_selected(self):
        for it in list(self.scene.selectedItems()):
            if isinstance(it, StampItem):
                self.scene.removeItem(it)
                self.stamps.remove(it)

    def sync_panel_from_selection(self):
        try:
            sel = [i for i in self.scene.selectedItems() if isinstance(i, StampItem)]
        except RuntimeError:
            return  # сцена уже уничтожена при выходе из программы
        if not sel:
            return
        it = sel[0]
        for w in (self.spin_w, self.spin_h, self.slider_rot, self.slider_op):
            w.blockSignals(True)
        self.spin_w.setValue(it.mm_w)
        self.spin_h.setValue(it.mm_h)
        self.slider_rot.setValue(int(it.rotation()))
        self.slider_op.setValue(int(it.opacity_value * 100))
        for w in (self.spin_w, self.spin_h, self.slider_rot, self.slider_op):
            w.blockSignals(False)
        self.lbl_rot.setText(f"Поворот: {int(it.rotation())}°")
        self.lbl_op.setText(f"Непрозрачность: {int(it.opacity_value * 100)}%")

    # ---------------- сканер ----------------

    def scan_document(self):
        dlg = ScanDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        self._scan_dpi = dlg.combo_dpi.currentData()
        self._scan_mode = dlg.combo_mode.currentData()
        self._scan_device = dlg.combo_dev.currentData()
        self._scan_prog = None
        self._scan_use_dialog = dlg.chk_dialog.isChecked()
        s = settings_load()
        s["scan_via_dialog"] = self._scan_use_dialog
        settings_save(s)
        self._run_scan()

    def _scan_now_main_thread(self):
        """WIA работает только в главном потоке — сканируем прямо здесь.
        Своего окна прогресса не показываем: Windows рисует собственное,
        а наше перекрывало окно драйвера."""
        out_path = os.path.join(tempfile.gettempdir(),
                                f"stampstudio_scan_{int(time.time() * 1000)}.bmp")
        self.statusBar().showMessage("Идёт сканирование… окно Windows покажет ход работы")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        QApplication.processEvents()
        try:
            saved = _wia_scan(self._scan_device, out_path, self._scan_dpi,
                              self._scan_mode, use_dialog=self._scan_use_dialog)
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self._update_ui_state()
            self._on_scan_failed(str(e))
            return
        QApplication.restoreOverrideCursor()
        self._update_ui_state()
        try:
            self._on_scan_ok(saved)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка после сканирования", str(e))

    def _run_scan(self):
        if scanner_backend() == "wia":
            self._scan_now_main_thread()
            return

        self._scan_prog = QProgressDialog("Сканирование…", None, 0, 0, self)
        self._scan_prog.setWindowModality(Qt.WindowModal)
        self._scan_prog.setMinimumDuration(0)
        self._scan_prog.setCancelButton(None)
        self._scan_prog.show()

        self._scan_worker = ScanWorker(self._scan_device, self._scan_dpi, self._scan_mode,
                                       self, use_dialog=getattr(self, "_scan_use_dialog", False))
        self._scan_worker.finished_ok.connect(self._on_scan_ok)
        self._scan_worker.failed.connect(self._on_scan_failed)
        self._scan_worker.start()

    def _close_scan_progress(self):
        prog = getattr(self, "_scan_prog", None)
        if prog is not None:
            try:
                prog.close()
            except Exception:
                pass
            self._scan_prog = None

    def _on_scan_ok(self, path):
        self._close_scan_progress()
        try:
            if not path or not os.path.exists(path) or os.path.getsize(path) == 0:
                raise RuntimeError("сканер не сохранил файл изображения")
            self._add_scanned_image(path, self._scan_dpi)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка",
                                 f"Скан получен, но не удалось добавить страницу:\n{e}")
            return
        QApplication.processEvents()
        again = QMessageBox.question(
            self, "Готово",
            f"Страница добавлена (всего страниц: {self.doc.page_count}).\n"
            "Сканировать ещё одну?")
        if again == QMessageBox.Yes:
            self._run_scan()
        else:
            self._ai_after_scan()

    def _on_scan_failed(self, msg):
        self._close_scan_progress()
        QMessageBox.critical(
            self, "Сканирование не удалось",
            "Не удалось получить изображение со сканера.\n\n"
            "Что можно сделать:\n"
            "• убедиться, что сканер включён, а лист лежит на стекле;\n"
            "• закрыть другие программы сканирования (они занимают устройство);\n"
            "• поставить галочку «сканировать через штатное окно Windows» "
            "в окне сканирования — для Canon это обычно решает вопрос;\n"
            "• попробовать другое разрешение — 300 DPI подходит почти всем;\n"
            "• отсканировать штатной программой Windows и открыть файл "
            "кнопкой «Открыть сканы»."
            + (f"\n\nТехнические детали:\n{msg}" if msg.strip() else ""))

    def _add_scanned_image(self, img_path: str, dpi: int):
        """Добавить скан страницей: к открытому документу или как новый документ."""
        with Image.open(img_path) as im:
            im = im.convert("RGB")
            buf = io.BytesIO()
            im.save(buf, "PNG", dpi=(dpi, dpi))
            png = buf.getvalue()
            w_pt = im.width / dpi * 72
            h_pt = im.height / dpi * 72
        if self.doc is None:
            doc = fitz.open()
            page = doc.new_page(width=w_pt, height=h_pt)
            page.insert_image(page.rect, stream=png)
            self._set_document(doc, "скан")
        else:
            page = self.doc.new_page(width=w_pt, height=h_pt)
            page.insert_image(page.rect, stream=png)
            self.refresh_page_list(self.doc.page_count - 1)
            self.show_page(self.doc.page_count - 1)
        try:
            os.remove(img_path)
        except OSError:
            pass

    # ---------------- экспорт ----------------

    def _stamped_pdf_bytes(self, clean_meta=False, flatten=False, flat_dpi=200,
                           compress=None):
        out = fitz.open()
        out.insert_pdf(self.doc)
        for it in self.stamps:
            page = out[it.page_index]
            px_w = max(1, int(it.mm_w / 25.4 * EXPORT_STAMP_DPI))
            px_h = max(1, int(it.mm_h / 25.4 * EXPORT_STAMP_DPI))
            im = it.pil_image.resize((px_w, px_h), Image.LANCZOS)
            if it.opacity_value < 1.0:
                alpha = im.getchannel("A").point(lambda a: int(a * it.opacity_value))
                im.putalpha(alpha)
            rot = it.rotation()
            if abs(rot) > 0.01:
                im = im.rotate(-rot, expand=True, resample=Image.BICUBIC)
            c = it.center_scene_pos()
            cx_pt = c.x() / PREVIEW_DPI * 72
            cy_pt = c.y() / PREVIEW_DPI * 72
            w_pt = im.width / EXPORT_STAMP_DPI * 72
            h_pt = im.height / EXPORT_STAMP_DPI * 72
            rect = fitz.Rect(cx_pt - w_pt / 2, cy_pt - h_pt / 2,
                             cx_pt + w_pt / 2, cy_pt + h_pt / 2)
            buf = io.BytesIO()
            im.save(buf, "PNG")
            page.insert_image(rect, stream=buf.getvalue(),
                              keep_proportion=False, overlay=True)
        if flatten:
            flat = fitz.open()
            for i in range(out.page_count):
                page = out[i]
                pix = page.get_pixmap(dpi=flat_dpi, alpha=False)
                im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                buf = io.BytesIO()
                im.save(buf, "JPEG", quality=92, optimize=True)
                np_ = flat.new_page(width=page.rect.width, height=page.rect.height)
                np_.insert_image(np_.rect, stream=buf.getvalue())
                AI.add_text_layer(np_, AI.hidden_words(page))
            try:
                flat.subset_fonts()
            except Exception:
                pass
            out.close()
            out = flat

        if clean_meta:
            out.set_metadata({})
            try:
                out.del_xml_metadata()
            except Exception:
                pass
        else:
            try:
                out.set_metadata(self.doc.metadata or {})
            except Exception:
                pass
        data = out.tobytes(deflate=True, garbage=3)
        out.close()

        # сжатие: явно выбранное в окне сохранения, либо то, которым
        # документ уже сжимали (чтобы размер не возвращался к исходному)
        prof = compress if compress is not None else getattr(self, "compress_profile", None)
        if prof and prof.get("mode") and prof.get("mode") != "none":
            try:
                tmp = fitz.open("pdf", data)
                if prof["mode"] == "medium":
                    data = self.compress_medium_bytes(tmp, prof.get("quality", 70))
                elif prof["mode"] == "strong":
                    data = self.compress_strong_bytes(tmp, prof.get("dpi", 150),
                                                      prof.get("quality", 70))
                else:
                    data = self.compress_light_bytes(tmp)
                tmp.close()
                self.compress_profile = prof
            except Exception:
                pass
        return data


    def save_pdf(self):
        """Ctrl+S: записать изменения прямо в открытый файл.
        Если документ ещё не файл (скан, картинки) — обычное «Сохранить как»."""
        if self.doc is None:
            QMessageBox.information(
                self, "Нечего сохранять",
                "Сначала откройте PDF или отсканируйте документ.")
            return
        path = str(self.doc_path or "")
        if not path or not os.path.isfile(path) or not path.lower().endswith(".pdf"):
            self.export_pdf()
            return
        dlg = QuickSaveDialog(self, compress_profile=getattr(self, "compress_profile", None))
        if dlg.exec() != QDialog.Accepted:
            return
        comp = dlg.compress_choice()
        try:
            data = self._stamped_pdf_bytes(flatten=dlg.chk_flat.isChecked(), compress=comp)
            write_file_safely(path, data, owner=self)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить:\n{e}")
            return
        if comp.get("mode") != "none":
            self.compress_profile = dict(comp)
        self._after_saved_in_place()
        self.refresh_files()
        msg = f"Сохранено в {os.path.basename(path)} ({human_size(len(data))})"
        self.statusBar().showMessage(msg, 6000)
        self.show_toast("✔  " + msg)

    def show_toast(self, text, ms=2600):
        """Заметная плашка по центру внизу окна: само исчезает, клики не перехватывает."""
        try:
            old = getattr(self, "_toast", None)
            if old is not None:
                old.deleteLater()
        except Exception:
            pass
        t = QLabel(text, self)
        t.setAttribute(Qt.WA_TransparentForMouseEvents)
        t.setStyleSheet("QLabel { background: rgba(32, 140, 76, 235); color: white; "
                        "border-radius: 10px; padding: 12px 22px; font-size: 11pt; "
                        "font-weight: 600; }")
        t.adjustSize()
        t.move((self.width() - t.width()) // 2, self.height() - t.height() - 56)
        t.show()
        t.raise_()
        self._toast = t
        eff = QGraphicsOpacityEffect(t)
        t.setGraphicsEffect(eff)
        eff.setOpacity(1.0)
        anim = QPropertyAnimation(eff, b"opacity", t)
        anim.setDuration(500)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.finished.connect(t.deleteLater)
        QTimer.singleShot(ms, anim.start)
        try:
            QApplication.beep()
        except Exception:
            pass

    def _after_saved_in_place(self):
        """Файл перезаписан и открыт заново: печати уже внутри, убираем их со сцены."""
        for s in list(self.stamps):
            try:
                self.scene.removeItem(s)
            except Exception:
                pass
        self.stamps = []
        cur = max(0, self.page_list.currentRow())
        if self.doc is not None:
            cur = min(cur, self.doc.page_count - 1)
            self.refresh_page_list(cur)
            self.show_page(cur)
        self._update_ui_state()

    def export_pdf(self, suggest=None):
        if self.doc is None:
            QMessageBox.information(
                self, "Нечего сохранять",
                "Сначала откройте PDF или отсканируйте документ — "
                "тогда появится окно с именем файла.")
            return
        src_name = os.path.splitext(os.path.basename(str(self.doc_path)))[0]
        src_name = src_name.replace(" (из изображений)", "") or "документ"
        dlg = SaveDialog(src_name, self, default_dir=self.current_dir(),
                         compress_profile=getattr(self, 'compress_profile', None))
        if isinstance(suggest, str) and suggest:
            dlg.edit_name.setText(suggest)
        else:
            self._ai_name_for_dialog(dlg)
        if dlg.exec() != QDialog.Accepted:
            return
        dlg.remember()
        path = dlg.full_path()
        try:
            data = self._stamped_pdf_bytes(clean_meta=dlg.chk_meta.isChecked(),
                                           flatten=dlg.chk_flat.isChecked(),
                                           compress=dlg.compress_choice())
            same = bool(self.doc_path and os.path.exists(str(self.doc_path))
                        and os.path.exists(path)
                        and os.path.samefile(str(self.doc_path), path))
            write_file_safely(path, data, owner=self)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить:\n{e}")
            return
        if same:
            self._after_saved_in_place()
        self.refresh_files()
        QMessageBox.information(self, "Готово",
                                f"Сохранено ({human_size(len(data))}):\n{path}")

    def export_pngs(self):
        if self.doc is None:
            QMessageBox.information(self, "Нечего экспортировать",
                                    "Сначала откройте PDF или отсканируйте документ.")
            return
        src_name = os.path.splitext(os.path.basename(str(self.doc_path)))[0]
        src_name = src_name.replace(" (из изображений)", "") or "документ"
        dlg = PngExportDialog(src_name, self.doc.page_count, self,
                              default_dir=self.current_dir())
        if dlg.exec() != QDialog.Accepted:
            return
        dlg.remember()
        dpi = dlg.dpi()
        self.spin_dpi.setValue(dpi)
        folder = dlg.folder
        saved = []
        try:
            data = self._stamped_pdf_bytes() if self.stamps else None
            src = fitz.open("pdf", data) if data else self.doc
            prog = QProgressDialog("Экспорт страниц…", "Отмена", 0, src.page_count, self)
            prog.setWindowModality(Qt.WindowModal)
            for i in range(src.page_count):
                if prog.wasCanceled():
                    break
                pix = src[i].get_pixmap(dpi=dpi, alpha=False)
                out_file = os.path.join(folder, dlg.file_name(i + 1))
                pix.save(out_file)
                saved.append(out_file)
                prog.setValue(i + 1)
            if src is not self.doc:
                src.close()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось экспортировать:\n{e}")
            return
        first = os.path.basename(saved[0]) if saved else ""
        QMessageBox.information(
            self, "Готово",
            f"Сохранено файлов: {len(saved)}\nПервый: {first}\n\nПапка:\n{folder}")

    def images_to_pdf(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Выбрать PNG/JPG (в порядке страниц)", "",
            "Изображения (*.png *.jpg *.jpeg)")
        if not paths:
            return
        out_path, _ = QFileDialog.getSaveFileName(self, "Сохранить PDF", "из_картинок.pdf", "PDF (*.pdf)")
        if not out_path:
            return
        try:
            doc = fitz.open()
            for p in paths:
                with Image.open(p) as im:
                    dpi = im.info.get("dpi", (300, 300))
                    dx = dpi[0] or 300
                    dy = dpi[1] or 300
                    w_pt = im.width / dx * 72
                    h_pt = im.height / dy * 72
                page = doc.new_page(width=w_pt, height=h_pt)
                page.insert_image(page.rect, filename=p)
            data = doc.tobytes(deflate=True, garbage=3)
            doc.close()
            write_file_safely(out_path, data, owner=self)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось собрать PDF:\n{e}")
            return
        QMessageBox.information(self, "Готово", f"Сохранено:\n{out_path}")

    # ---------------- метаданные ----------------

    def show_metadata(self):
        doc = None
        label = ""
        from_disk = False
        if self.doc is not None:
            ans = QMessageBox.question(
                self, "Метаданные",
                "Посмотреть метаданные открытого документа?\n"
                "«Нет» — выбрать другой PDF с диска.",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
            if ans == QMessageBox.Cancel:
                return
            if ans == QMessageBox.Yes:
                doc = self.doc
                label = os.path.basename(str(self.doc_path))
        if doc is None:
            path, _ = QFileDialog.getOpenFileName(self, "Выбрать PDF", "", "PDF (*.pdf)")
            if not path:
                return
            try:
                doc = fitz.open(path)
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Не удалось открыть PDF:\n{e}")
                return
            label = os.path.basename(path)
            from_disk = True

        meta = dict(doc.metadata or {})
        dlg = MetadataDialog(meta, label, self)
        do_clean = dlg.exec() == QDialog.Accepted
        if not do_clean:
            if from_disk:
                doc.close()
            return

        base = os.path.splitext(label)[0]
        out_path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить очищенный PDF", f"{base}_без_метаданных.pdf", "PDF (*.pdf)")
        if not out_path:
            if from_disk:
                doc.close()
            return
        try:
            if doc is self.doc:
                data = self._stamped_pdf_bytes(clean_meta=True)
            else:
                doc.set_metadata({})
                try:
                    doc.del_xml_metadata()
                except Exception:
                    pass
                data = doc.tobytes(deflate=True, garbage=3)
            write_file_safely(out_path, data, owner=self)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить:\n{e}")
            return
        finally:
            if from_disk:
                doc.close()
        QMessageBox.information(self, "Готово",
                                f"Метаданные удалены.\nСохранено:\n{out_path}")

    # ---------------- сжатие ----------------

    @staticmethod
    def compress_light_bytes(src_doc: fitz.Document) -> bytes:
        """Без потерь: пересборка с чисткой мусора и deflate."""
        return src_doc.tobytes(deflate=True, deflate_images=True,
                               deflate_fonts=True, garbage=4, clean=True)

    @staticmethod
    def compress_medium_bytes(src_doc: fitz.Document, quality: int,
                              max_dim: int = 2200, progress=None) -> bytes:
        """Пережать встроенные изображения в JPEG (текст остаётся текстом)."""
        seen = {}
        for page in src_doc:
            for img in page.get_images(full=True):
                xref = img[0]
                if xref not in seen:
                    seen[xref] = page
        for n, (xref, page) in enumerate(seen.items()):
            if progress:
                progress(n)
            try:
                base = src_doc.extract_image(xref)
                if not base:
                    continue
                im = Image.open(io.BytesIO(base["image"]))
                if im.mode != "L":
                    im = im.convert("RGB")
                w0, h0 = im.size
                if max(w0, h0) > max_dim:
                    k = max_dim / max(w0, h0)
                    im = im.resize((max(1, int(w0 * k)), max(1, int(h0 * k))),
                                   Image.LANCZOS)
                buf = io.BytesIO()
                im.save(buf, "JPEG", quality=quality, optimize=True)
                new_data = buf.getvalue()
                if len(new_data) < len(base["image"]) * 0.95:
                    page.replace_image(xref, stream=new_data)
            except Exception:
                continue  # проблемную картинку пропускаем, документ не ломаем
        return src_doc.tobytes(deflate=True, deflate_images=True,
                               deflate_fonts=True, garbage=4, clean=True)

    @staticmethod
    def compress_strong_bytes(src_doc: fitz.Document, dpi: int, quality: int,
                              progress=None) -> bytes:
        """С потерями: каждая страница -> JPEG. Максимальная экономия для сканов."""
        out = fitz.open()
        for i in range(src_doc.page_count):
            if progress:
                progress(i)
            page = src_doc[i]
            pix = page.get_pixmap(dpi=dpi, alpha=False)
            im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=quality, optimize=True)
            new_page = out.new_page(width=page.rect.width, height=page.rect.height)
            new_page.insert_image(new_page.rect, stream=buf.getvalue())
            AI.add_text_layer(new_page, AI.hidden_words(page))
        try:
            out.subset_fonts()
        except Exception:
            pass
        data = out.tobytes(deflate=True, garbage=3)
        out.close()
        return data

    def compress_pdf(self):
        # сжимаем либо открытый документ (с печатями, если есть), либо любой файл с диска
        src_doc = None
        src_size = None
        source_path = None
        if self.doc is not None:
            use_open = QMessageBox.question(
                self, "Сжатие PDF",
                "Сжать открытый документ (вместе с поставленными печатями)?\n"
                "«Нет» — выбрать другой файл с диска.",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
            if use_open == QMessageBox.Cancel:
                return
            if use_open == QMessageBox.Yes:
                data = self._stamped_pdf_bytes() if self.stamps else self.doc.tobytes()
                src_doc = fitz.open("pdf", data)
                src_size = len(data)
                p = str(self.doc_path)
                if os.path.exists(p):
                    source_path = os.path.abspath(p)
                    src_size = os.path.getsize(source_path)
        if src_doc is None:
            path, _ = QFileDialog.getOpenFileName(self, "Выбрать PDF для сжатия",
                                                  self.current_dir(), "PDF (*.pdf)")
            if not path:
                return
            try:
                src_doc = fitz.open(path)
                src_size = os.path.getsize(path)
                source_path = os.path.abspath(path)
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Не удалось открыть PDF:\n{e}")
                return

        meta_before = {k: v for k, v in (src_doc.metadata or {}).items()
                       if v and k not in ("format", "encryption")}

        dlg = CompressDialog(self, source_path=source_path)
        if dlg.exec() != QDialog.Accepted:
            src_doc.close()
            return

        if dlg.chk_replace.isChecked() and source_path:
            out_path = source_path
        else:
            base = "сжатый.pdf"
            if source_path:
                stem = os.path.splitext(os.path.basename(source_path))[0]
                base = f"{stem}_сжатый.pdf"
            start_dir = os.path.dirname(source_path) if source_path else self.current_dir()
            out_path, _ = QFileDialog.getSaveFileName(
                self, "Сохранить сжатый PDF", os.path.join(start_dir, base), "PDF (*.pdf)")
        if not out_path:
            src_doc.close()
            return

        try:
            if dlg.rb_light.isChecked():
                data = self.compress_light_bytes(src_doc)
            elif dlg.rb_medium.isChecked():
                prog = QProgressDialog("Пережатие картинок…", None, 0, 0, self)
                prog.setWindowModality(Qt.WindowModal)
                prog.show()
                QApplication.processEvents()
                data = self.compress_medium_bytes(
                    src_doc, dlg.spin_q.value(),
                    progress=lambda i: QApplication.processEvents())
                prog.close()
            else:
                tiny = dlg.rb_tiny.isChecked()
                prog = QProgressDialog("Сжатие страниц…", None, 0, src_doc.page_count, self)
                prog.setWindowModality(Qt.WindowModal)
                data = self.compress_strong_bytes(
                    src_doc, 110 if tiny else dlg.spin_dpi.value(),
                    50 if tiny else dlg.spin_q.value(),
                    progress=lambda i: prog.setValue(i))
                prog.setValue(src_doc.page_count)
            if dlg.chk_meta.isChecked():
                tmp_doc = fitz.open("pdf", data)
                tmp_doc.set_metadata({})
                try:
                    tmp_doc.del_xml_metadata()
                except Exception:
                    pass
                data = tmp_doc.tobytes(deflate=True, garbage=3)
                tmp_doc.close()
            write_file_safely(out_path, data, owner=self)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось сжать:\n{e}")
            src_doc.close()
            return
        src_doc.close()

        if dlg.rb_light.isChecked():
            self.compress_profile = {"mode": "light"}
        elif dlg.rb_medium.isChecked():
            self.compress_profile = {"mode": "medium", "quality": dlg.spin_q.value()}
        elif dlg.rb_tiny.isChecked():
            self.compress_profile = {"mode": "strong", "dpi": 110, "quality": 50, "preset": "tiny"}
        else:
            self.compress_profile = {"mode": "strong", "dpi": dlg.spin_dpi.value(),
                                     "quality": dlg.spin_q.value()}
        self.refresh_files()
        try:
            same_as_open = (self.doc is not None and self.doc_path
                            and os.path.exists(str(self.doc_path))
                            and os.path.samefile(str(self.doc_path), out_path))
        except OSError:
            same_as_open = False
        if same_as_open:
            page_now = self.current_page
            for s in list(self.stamps):
                self.scene.removeItem(s)
            self.stamps.clear()
            self.doc.close()
            self.doc = fitz.open(out_path)
            self.refresh_page_list(page_now)
            self.show_page(min(page_now, self.doc.page_count - 1))

        meta_after = {k: v for k, v in (fitz.open("pdf", data).metadata or {}).items()
                      if v and k not in ("format", "encryption")}
        meta_line = ""
        if meta_before or meta_after:
            meta_line = (f"\n\nМетаданные: было {len(meta_before)} полей, "
                         f"стало {len(meta_after)}.")
            if meta_before and not meta_after:
                meta_line += " Все удалены."

        saved = (1 - len(data) / src_size) * 100 if src_size else 0
        if saved < 3:
            QMessageBox.information(
                self, "Готово",
                f"Было: {human_size(src_size)}, стало: {human_size(len(data))}.\n\n"
                "Файл уже был хорошо сжат — существенной экономии нет.\n"
                "Попробуйте режим «Среднее» или «Сильное» с качеством пониже."
                f"{meta_line}\n\n{out_path}")
        else:
            QMessageBox.information(
                self, "Готово",
                f"Было: {human_size(src_size)}\nСтало: {human_size(len(data))}\n"
                f"Экономия: {saved:.0f}%{meta_line}\n\n{out_path}")


def main():
    try:
        os.chdir(tempfile.gettempdir())   # чтобы не занимать рабочие папки
    except OSError:
        pass
    app = QApplication(sys.argv)
    app.setApplicationName(APP_TITLE)
    from PySide6.QtGui import QFont
    base_font = QFont("Segoe UI" if sys.platform == "win32" else app.font().family(), 10)
    app.setFont(base_font)
    icon_file = find_resource("icon.png") or resource_path("icon.png")
    if os.path.exists(icon_file):
        app.setWindowIcon(QIcon(icon_file))
    if "--selftest" in sys.argv:
        win = MainWindow()
        app.processEvents()
        with open(os.path.join(tempfile.gettempdir(), "stampstudio_selftest.txt"), "w",
                  encoding="utf-8") as f:
            try:
                with open(find_resource(os.path.join("docs", "guide.json")), encoding="utf-8") as g:
                    guide_n = len(json.load(g))
            except Exception:
                guide_n = 0
            f.write(f"OK {APP_VERSION} {EDITION} scanner={scanner_backend()} guide={guide_n} "
                    f"ai={len(AI.PROVIDERS)} keys={len(AI.builtin_keys())} ocr={AI.selftest_ocr()}")
        sys.exit(0)
    win = MainWindow()
    win.show()
    win.place_mascot()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
