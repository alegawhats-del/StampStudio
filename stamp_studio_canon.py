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
from PySide6.QtGui import QRegion
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
from PySide6.QtCore import QUrl, QFileSystemWatcher, QEventLoop, QPoint, QDate
from PySide6.QtWidgets import QDateEdit, QTabWidget, QTextEdit
from PySide6.QtGui import (QTextCursor, QTextCharFormat, QTextBlockFormat, QTextTableFormat, QTextFormat,
                           QTextFrameFormat, QTextLength, QFont, QTextDocument)
from PySide6.QtCore import QFile
from PySide6.QtGui import QShortcut
import datetime
import re
import stamp_ai as AI
import stamp_word as SW
import stamp_cloud as CLOUD
import stamp_act as ACT

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
QToolButton#ghost { background: transparent; border: none; border-radius: 12px; padding: 0; min-width: 0; min-height: 0; }
QToolButton#ghost:hover { background: rgba(214, 154, 51, 0.22); }
QToolButton#ghost:pressed { background: rgba(214, 154, 51, 0.40); }
QPushButton#aiact { text-align: left; padding: 6px 12px; }
QDialog#embedded { background: transparent; }
QToolBar#tools { background: #171a22; border: none; border-right: 1px solid #262b39; padding: 4px 5px; spacing: 2px; }
QToolBar#tools QToolButton { min-width: 30px; max-width: 30px; min-height: 28px; max-height: 28px; padding: 0;
    background: transparent; border: 1px solid transparent; border-radius: 8px; }
QToolBar#tools QToolButton:hover { background: #232735; border-color: #e8b04b; }
QToolBar#tools QToolButton:checked { background: #3a321c; border-color: #e8b04b; }
QToolBar#tools QToolButton:disabled { background: transparent; border-color: transparent; }
QToolBar#tools::separator { background: #2a2f3d; height: 1px; margin: 3px 5px; }
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
QToolButton#ghost { background: transparent; border: none; border-radius: 12px; padding: 0; min-width: 0; min-height: 0; }
QToolButton#ghost:hover { background: rgba(214, 154, 51, 0.22); }
QToolButton#ghost:pressed { background: rgba(214, 154, 51, 0.40); }
QPushButton#aiact { text-align: left; padding: 6px 12px; }
QDialog#embedded { background: transparent; }
QToolBar#tools { background: #fbf9f4; border: none; border-right: 1px solid #e6e1d6; padding: 4px 5px; spacing: 2px; }
QToolBar#tools QToolButton { min-width: 30px; max-width: 30px; min-height: 28px; max-height: 28px; padding: 0;
    background: transparent; border: 1px solid transparent; border-radius: 8px; }
QToolBar#tools QToolButton:hover { background: #ffffff; border-color: #d69a33; }
QToolBar#tools QToolButton:checked { background: #fbefd3; border-color: #d69a33; }
QToolBar#tools QToolButton:disabled { background: transparent; border-color: transparent; }
QToolBar#tools::separator { background: #e6e1d6; height: 1px; margin: 3px 5px; }
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
APP_VERSION = "6.10.2"
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


SETTINGS_CHANGED = []            # кому сообщить, что изменились настройки, которые уходят в облако
_SYNCED_KEYS = ("word_marks", "pen_presets", "name_templates", "doc_counters", "sheet_templates", "act_masters", "act_dict")
_synced_seen = [None]


def settings_save(d: dict):
    os.makedirs(LIB_DIR, exist_ok=True)
    with open(SETTINGS_JSON, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    try:
        now = json.dumps([d.get(k) for k in _SYNCED_KEYS], ensure_ascii=False, sort_keys=True, default=str)
    except Exception:
        return
    if _synced_seen[0] is not None and now != _synced_seen[0]:
        for fn in list(SETTINGS_CHANGED):
            try:
                fn()
            except Exception:
                pass
    _synced_seen[0] = now


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


LIB_CHANGED = []                 # кому сообщить, что библиотека печатей изменилась


def lib_save(items: list):
    os.makedirs(LIB_DIR, exist_ok=True)
    with open(LIB_JSON, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    for fn in list(LIB_CHANGED):
        try:
            fn()
        except Exception:
            pass


CLOUD_STATE = os.path.join(LIB_DIR, "cloud_state.json")       # что уже сверено с облаком
CLOUD_CLIENTS = os.path.join(LIB_DIR, "clients_cloud.json")   # клиенты из облака, у которых здесь ещё нет папки


def _json_read(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _json_write(path, data):
    try:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
    except OSError:
        pass


def client_key(folder):
    """Клиент узнаётся по названию своей папки — оно одинаковое на всех компьютерах."""
    return os.path.basename(os.path.normpath(str(folder))).strip().lower()


def cloud_uri():
    return CLOUD.unprotect(settings_load().get("cloud_uri", ""))


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


class PageGrid(QListWidget):
    """Миниатюры страниц: всегда не меньше двух столбцов, размер подстраивается под ширину панели."""

    def fit_grid(self):
        vp = self.viewport().width()
        if vp <= 0:
            return
        cols = max(2, vp // 150)
        cell = max(70, (vp - 2) // cols)
        if self.gridSize().width() != cell:
            iw = max(48, cell - 30)
            ih = int(iw * 1.36)
            self.setIconSize(QSize(iw, ih))
            self.setGridSize(QSize(cell, ih + 30))

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


def pen_natural_ends(dense, raw):
    """Живые концы штриха, как у настоящей ручки: перо касается бумаги не сразу в полную силу,
    а в конце линия сходит на нет лёгким мазком. Возвращает (точки, насыщенность по точкам)."""
    import math
    n = len(dense)
    if n < 4:
        return dense, None
    cum = [0.0]
    for i in range(1, n):
        cum.append(cum[-1] + math.hypot(dense[i][0] - dense[i - 1][0], dense[i][1] - dense[i - 1][1]))
    total = cum[-1]
    ws = sorted(d[2] for d in dense)
    w0 = ws[len(ws) // 2]
    if total < 3 * w0:
        return dense, None
    lead = min(1.6 * w0, 0.15 * total)                     # касание: первые доли миллиметра тоньше
    tail = min(max(3.2 * w0, 0.06 * total), 0.35 * total, 10 * w0)   # отрыв: линия утоньшается и бледнеет
    out, alpha = [], []
    for i, (x, y, w) in enumerate(dense):
        k, a = 1.0, 1.0
        if cum[i] < lead:
            k *= 0.62 + 0.38 * (cum[i] / lead)
            a *= 0.86 + 0.14 * (cum[i] / lead)
        rest = total - cum[i]
        if rest < tail:
            t = rest / tail
            k *= 0.30 + 0.70 * t ** 0.8
            a *= 0.58 + 0.42 * t
        out.append((x, y, w * k))
        alpha.append(a)
    # мазок: если рука в конце ещё двигалась, перо уходит с бумаги по инерции
    pts = [q for q in raw if True]
    while len(pts) >= 2 and math.hypot(pts[-1][0] - pts[-2][0], pts[-1][1] - pts[-2][1]) < 1e-6:
        pts = pts[:-1]
    speed = math.hypot(pts[-1][0] - pts[-2][0], pts[-1][1] - pts[-2][1]) if len(pts) >= 2 else 0.0
    if speed > 1.1 * w0:
        j = n - 1
        while j > 0 and cum[-1] - cum[j] < 2.0 * w0:
            j -= 1
        dx, dy = dense[-1][0] - dense[j][0], dense[-1][1] - dense[j][1]
        d = math.hypot(dx, dy)
        if d > 1e-6:
            dx, dy = dx / d, dy / d
            flick = min(4.5 * w0, 0.7 * speed)
            steps = max(3, int(flick / 0.7))
            x0, y0, wl = out[-1]
            al = alpha[-1]
            for s_ in range(1, steps + 1):
                t = s_ / steps
                out.append((x0 + dx * flick * t, y0 + dy * flick * t, max(0.22, wl * (1 - 0.82 * t))))
                alpha.append(al * (1 - 0.72 * t))
    return out, alpha


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
        alpha = st.get("alpha")
        if alpha is not None and len(alpha) != len(dense):
            alpha = None
        for i, (x, y, w) in enumerate(dense[1:], 1):
            pen.setWidthF(max(0.2, (pw + w) / 2))
            if alpha is not None:
                col.setAlpha(int(238 * alpha[i]))
                pen.setColor(col)
            painter.setPen(pen)
            painter.drawLine(QPointF(px, py), QPointF(x, y))
            px, py, pw = x, y, w
        col.setAlpha(238)


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
        outer.setContentsMargins(10, 10, 10, 10)
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
        lay.setSpacing(6)
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

        self.b_undo = btn("", "Отменить последний штрих  (Ctrl+Z)", on_undo)
        self.b_undo.setIcon(draw_icon("undo", ui_icon_color()))
        self.b_undo.setIconSize(QSize(18, 18))
        self.b_undo.setFixedWidth(40)
        self.b_clear = btn("Очистить", "Стереть всё нарисованное", on_clear)
        self.b_sets = QPushButton("Наборы")
        self.b_sets.setToolTip("Сохранённые настройки ручки: толщина, плавность и цвет под одним именем.\n"
                               "Например «Подпись» и «Пометки» — переключаются одним щелчком.")
        self.b_sets.setMinimumHeight(32)
        self.b_sets.setCursor(Qt.PointingHandCursor)
        self._sets_menu = QMenu(self.b_sets)
        self._sets_menu.aboutToShow.connect(self._fill_sets_menu)
        self.b_sets.setMenu(self._sets_menu)
        lay.addWidget(self.b_sets)
        lay.addStretch(1)
        self.b_cancel = btn("Отмена", "Выйти без подписи  (Esc)", on_cancel)
        self.b_done = btn("Готово", "Оставить подпись на странице  (Enter)", on_done, accent=True)

        self.sl_width.valueChanged.connect(self._changed)
        self.sl_smooth.valueChanged.connect(self._changed)
        self._pick_ink(self.ink_index, notify=False)
        self._changed()

    # ---- наборы настроек ручки
    def current_set(self):
        return {"width": self.sl_width.value(), "smooth": self.sl_smooth.value(), "ink": self.ink_index}

    def apply_set(self, p):
        self.sl_width.setValue(int(p.get("width", 6)))
        self.sl_smooth.setValue(int(p.get("smooth", 55)))
        self._pick_ink(int(p.get("ink", 0)) % len(PEN_INKS))

    @staticmethod
    def set_text(p):
        v = int(p.get("smooth", 55))
        feel = "резко" if v < 15 else ("плавно" if v > 70 else "средне")
        ink = PEN_INKS[int(p.get("ink", 0)) % len(PEN_INKS)][0].lower()
        return f"{p.get('name', '')}  —  {int(p.get('width', 6)) / 10:.1f} мм, {feel}, {ink}"

    def _fill_sets_menu(self):
        m = self._sets_menu
        m.clear()
        sets = settings_load().get("pen_presets") or []
        cur = self.current_set()
        for p in sets:
            a = m.addAction(self.set_text(p))
            a.setCheckable(True)
            a.setChecked(all(p.get(k) == cur[k] for k in cur))
            a.triggered.connect(lambda _=False, p=p: self.apply_set(p))
        if not sets:
            a = m.addAction("пока нет сохранённых наборов")
            a.setEnabled(False)
        m.addSeparator()
        m.addAction("Сохранить текущие настройки как набор…").triggered.connect(self.save_set)
        if sets:
            sub = m.addMenu("Удалить набор")
            for p in sets:
                sub.addAction(p.get("name", "")).triggered.connect(
                    lambda _=False, n=p.get("name", ""): self.delete_set(n))

    def save_set(self):
        name, ok = QInputDialog.getText(self.window(), "Набор для ручки",
                                        "Название набора (например «Подпись»):")
        name = (name or "").strip()[:30]
        if not ok or not name:
            return
        s = settings_load()
        sets = [p for p in (s.get("pen_presets") or []) if p.get("name") != name]
        sets.append(dict(self.current_set(), name=name))
        s["pen_presets"] = sets[-12:]
        settings_save(s)
        self.b_sets.setToolTip(f"Набор «{name}» сохранён. Нажмите, чтобы выбрать другой.")

    def delete_set(self, name):
        s = settings_load()
        s["pen_presets"] = [p for p in (s.get("pen_presets") or []) if p.get("name") != name]
        settings_save(s)

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
            st["dense"], st["alpha"] = pen_natural_ends(pen_dense_points(st["pts"]), st["pts"])
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


def qss_icon_path(kind: str, color: str) -> str:
    """PNG-значок для QSS (стрелки прокрутки вкладок)."""
    path = os.path.join(tempfile.gettempdir(), f"stampstudio_{kind}_{color.strip('#')}.png")
    if not os.path.exists(path):
        try:
            draw_icon(kind, color, 32).pixmap(32, 32).save(path, "PNG")
        except Exception:
            return ""
    return path.replace("\\", "/")


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


def _card_saved(folder):
    st = settings_load()
    reg = st.setdefault("client_dirs", {})
    key = client_key(folder)
    if reg.get(key) != folder:
        reg[key] = folder
        settings_save(st)
    for fn in list(LIB_CHANGED):
        try:
            fn()
        except Exception:
            pass


def register_client_dirs(folders):
    """Запомнить папки, в которых лежат карточки клиентов, — чтобы они уходили в облако. True, если нашлись новые."""
    st = settings_load()
    reg = st.setdefault("client_dirs", {})
    new = False
    for folder in folders:
        key = client_key(folder)
        if key and reg.get(key) != folder and os.path.isfile(SW.card_path(folder)):
            reg[key] = folder
            new = True
    if new:
        settings_save(st)
    return new


def find_client_dirs(folder):
    """Папка клиента и её соседи: обычно все клиенты лежат рядом, в одной общей папке."""
    out = [folder]
    try:
        parent = os.path.dirname(os.path.normpath(folder))
        if parent and parent != folder:
            for name in sorted(os.listdir(parent))[:600]:
                d = os.path.join(parent, name)
                if d != folder and os.path.isdir(d):
                    out.append(d)
    except OSError:
        pass
    return out


SW.ON_CARD_SAVED = _card_saved
SW.CARD_FALLBACK = lambda folder: (_json_read(CLOUD_CLIENTS, {}) or {}).get(client_key(folder)) or {}


def open_pdf_free(path):
    """Открыть PDF, не занимая файл: документ читается в память, и файл на диске сразу свободен —
    его можно удалить, переименовать или перезаписать, пока он открыт в программе."""
    with open(path, "rb") as f:
        data = f.read()
    return fitz.open("pdf", data)


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
            owner.doc = open_pdf_free(path)
            owner.doc_path = path
    return path


# ---------------------------------------------------------------- иконки

from PySide6.QtGui import QPen, QColor, QPainterPath, QBrush
from PySide6.QtCore import QPointF


def ui_icon_color() -> str:
    """Цвет значков под текущую тему — для окон, которые создаются по ходу работы."""
    return "#e8e6e1" if settings_load().get("theme") == "dark" else "#4a4636"


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

    def fl(*pts):
        """Ломаная по точкам в сетке 16×16 — без округления до пикселя, линии выходят чистыми."""
        path = QPainterPath()
        path.moveTo(pts[0] * u, pts[1] * u)
        for i in range(2, len(pts), 2):
            path.lineTo(pts[i] * u, pts[i + 1] * u)
        p.drawPath(path)

    def sheet():
        """Лист с загнутым уголком — основа значков файлов."""
        path = QPainterPath()
        path.moveTo(4.0 * u, 2.4 * u); path.lineTo(9.4 * u, 2.4 * u); path.lineTo(12.4 * u, 5.4 * u)
        path.lineTo(12.4 * u, 13.6 * u); path.lineTo(4.0 * u, 13.6 * u)
        path.closeSubpath()
        p.drawPath(path)
        fl(9.4, 2.4, 9.4, 5.4, 12.4, 5.4)

    def turn(mirror, sweep=290, dot=False):
        """Круговая стрелка в том же начертании, что и «Обновить»."""
        if mirror:
            p.save()
            p.translate(s, 0)
            p.scale(-1, 1)
        path = QPainterPath()
        path.arcMoveTo(3.0 * u, 3.0 * u, 10.0 * u, 10.0 * u, 50)
        path.arcTo(3.0 * u, 3.0 * u, 10.0 * u, 10.0 * u, 50, sweep)
        p.drawPath(path)
        p.setBrush(QBrush(c))
        p.setPen(Qt.NoPen)
        p.drawPolygon([QPointF(13.9 * u, 2.6 * u), QPointF(13.9 * u, 7.0 * u), QPointF(9.7 * u, 6.2 * u)])
        if dot:
            p.drawEllipse(QPointF(8 * u, 8 * u), 1.5 * u, 1.5 * u)
        p.setBrush(Qt.NoBrush)
        p.setPen(pen)
        if mirror:
            p.restore()

    if kind == "back":
        fl(12.8, 8, 3.4, 8)
        fl(7.4, 3.8, 3.2, 8, 7.4, 12.2)
    elif kind == "undo":
        path = QPainterPath()
        path.moveTo(3.6 * u, 6.4 * u); path.lineTo(9.6 * u, 6.4 * u)
        path.arcTo(6.6 * u, 6.4 * u, 6.0 * u, 6.0 * u, 90, -180)
        path.lineTo(6.2 * u, 12.4 * u)
        p.drawPath(path)
        fl(6.6, 3.4, 3.4, 6.4, 6.6, 9.4)
    elif kind == "rot_left":
        turn(True, 250, dot=True)
    elif kind == "rot_right":
        turn(False, 250, dot=True)
    elif kind == "moon":
        big = QPainterPath(); big.addEllipse(QPointF(7.6 * u, 8.4 * u), 5.2 * u, 5.2 * u)
        cut = QPainterPath(); cut.addEllipse(QPointF(10.6 * u, 5.6 * u), 4.4 * u, 4.4 * u)
        p.drawPath(big.subtracted(cut))
    elif kind == "pdf":
        sheet()
        fl(6.2, 8.6, 10.2, 8.6); fl(6.2, 11.0, 10.2, 11.0)
    elif kind == "word":
        sheet()
        fl(5.8, 8.0, 6.9, 11.6, 8.2, 8.8, 9.5, 11.6, 10.6, 8.0)
    elif kind == "word_edit":
        fl(7.0, 13.6, 3.4, 13.6, 3.4, 2.4, 8.6, 2.4, 11.4, 5.2, 11.4, 6.6)      # лист Word
        fl(8.6, 2.4, 8.6, 5.2, 11.4, 5.2)
        fl(5.4, 7.4, 6.2, 10.0, 7.2, 8.0, 8.2, 10.0, 9.0, 7.4)                  # буква W
        fl(9.0, 14.4, 9.6, 11.8, 13.4, 8.0, 15.4, 10.0, 11.6, 13.8, 9.0, 14.4)  # карандаш
        fl(12.4, 9.0, 14.4, 11.0)
    elif kind == "to_pdf":
        sheet()
        fl(8.2, 6.8, 8.2, 11.4); fl(6.2, 9.4, 8.2, 11.4, 10.2, 9.4)
    elif kind == "to_png":
        rect(2.4, 3.0, 11.2, 8.4)
        fl(4.2, 9.4, 6.8, 6.8, 8.6, 8.6, 10.2, 7.0, 11.8, 8.6)
        fl(8, 12.4, 8, 15.0); fl(6.2, 13.4, 8, 15.2, 9.8, 13.4)
    elif kind == "half_v":
        rect(3.0, 2.6, 10.0, 10.8)
        fl(1.6, 8, 14.4, 8)
    elif kind == "half_h":
        rect(2.6, 3.0, 10.8, 10.0)
        fl(8, 1.6, 8, 14.4)
    elif kind == "external":
        fl(7.0, 3.6, 3.4, 3.6, 3.4, 12.6, 12.4, 12.6, 12.4, 9.0)
        fl(9.2, 3.2, 12.8, 3.2, 12.8, 6.8); fl(12.6, 3.4, 7.6, 8.4)
    elif kind == "up":
        fl(8, 12.8, 8, 3.4); fl(4.0, 7.4, 8, 3.2, 12.0, 7.4)
    elif kind == "down":
        fl(8, 3.2, 8, 12.6); fl(4.0, 8.6, 8, 12.8, 12.0, 8.6)
    elif kind == "close":
        fl(4.2, 4.2, 11.8, 11.8); fl(11.8, 4.2, 4.2, 11.8)
    elif kind == "plus":
        fl(8, 3.2, 8, 12.8); fl(3.2, 8, 12.8, 8)
    elif kind == "chev_down":
        fl(4.4, 6.2, 8, 9.8, 11.6, 6.2)
    elif kind == "chev_left":
        fl(9.8, 4.4, 6.2, 8, 9.8, 11.6)
    elif kind == "chev_right":
        fl(6.2, 4.4, 9.8, 8, 6.2, 11.6)
    elif kind == "folder":
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
    elif kind == "word":
        rect(3.4, 2.2, 9.2, 11.6)
        line(5.4, 6.0, 6.6, 10.4); line(6.6, 10.4, 8.0, 7.2)
        line(8.0, 7.2, 9.4, 10.4); line(9.4, 10.4, 10.6, 6.0)
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
    elif kind == "refresh":
        path = QPainterPath()
        path.arcMoveTo(3.0 * u, 3.0 * u, 10.0 * u, 10.0 * u, 50)
        path.arcTo(3.0 * u, 3.0 * u, 10.0 * u, 10.0 * u, 50, 290)
        p.drawPath(path)
        p.setBrush(QBrush(c))
        p.setPen(Qt.NoPen)
        p.drawPolygon([QPointF(13.9 * u, 2.6 * u), QPointF(13.9 * u, 7.0 * u), QPointF(9.7 * u, 6.2 * u)])
        p.setBrush(Qt.NoBrush)
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
    elif kind == "act":
        rect(3.0, 2.2, 10.0, 12.0)
        line(5.2, 5.4, 10.8, 5.4); line(5.2, 8.0, 8.4, 8.0)
        fl(6.4, 11.0, 7.8, 12.4, 10.8, 9.2)
    elif kind == "sheet":
        rect(3.0, 1.5, 10.0, 13.0)
        rect(3.0, 1.5, 5.2, 6.4)
        line(4.4, 3.6, 6.8, 3.6); line(4.4, 5.6, 6.8, 5.6)
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
    elif kind == "chev_left":
        fl(9.8, 4.4, 6.2, 8, 9.8, 11.6)
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
                d = open_pdf_free(p)
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
    "BoAAAAAAADAAPQAAAYAB/9k="
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


_DUST_LAYER = None


def scanner_dust_layer():
    """Пылинки встроенного стекла (L: 0 — чисто, больше — темнее точка); считается один раз.
    Волоски отретушированы в самом встроенном скане стекла, здесь ничего не отбрасывается."""
    global _DUST_LAYER
    if _DUST_LAYER is None:
        bed = builtin_scanner_bg()
        if bed is None:
            _DUST_LAYER = False
            return None
        gray = bed.convert("L")
        smooth = gray.filter(ImageFilter.GaussianBlur(12))
        specks = ImageChops.subtract(smooth, gray)           # >0 там, где точка темнее фона
        specks = specks.point(lambda v: 0 if v < 7 else min(255, int(v * 1.6)))
        _DUST_LAYER = specks
    return _DUST_LAYER or None


def load_scanner_bg(path):
    """Отсканированный пустой фон сканера: PDF (первая страница) или картинка → PIL RGB."""
    if not path or not os.path.isfile(path):
        return None
    try:
        if path.lower().endswith(".pdf"):
            d = open_pdf_free(path)
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
            b_v = QPushButton(" Пополам")
            b_v.setIcon(draw_icon("half_v", ui_icon_color()))
            b_v.setToolTip("Разделить на верхнюю и нижнюю половины")
            b_v.clicked.connect(lambda: self._halves(True))
            b_h = QPushButton(" Пополам")
            b_h.setIcon(draw_icon("half_h", ui_icon_color()))
            b_h.setToolTip("Разделить на левую и правую половины")
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
    # угол° (0 — лист лежит ровно), размытие, зерно бумаги, самый тёмный тон, затемнение края, сдвиг мм, jpeg
    "light":  dict(angle=0.0, blur=0.40, grain=1.6, ink=50, edge=0.000, shift=0.5, q=84),
    "normal": dict(angle=0.0, blur=0.55, grain=2.2, ink=62, edge=0.006, shift=1.0, q=80),
    "strong": dict(angle=0.0, blur=0.85, grain=3.6, ink=78, edge=0.020, shift=2.2, q=72),
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
            # оттиск ровный, как на настоящем скане: без «выцветших» пятен — правило для всех печатей
            ink = ink.filter(ImageFilter.GaussianBlur(0.35 * k))
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
    specks = scanner_dust_layer()
    if specks is not None:
        specks = specks.resize((W, H), Image.LANCZOS)
        if rnd.random() < 0.5:
            specks = specks.transpose(Image.FLIP_LEFT_RIGHT)
        if rnd.random() < 0.5:
            specks = specks.transpose(Image.FLIP_TOP_BOTTOM)
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


# ======================================================================
#  Разместить документ нестандартного размера на листе («скан на стекле»)
# ======================================================================

SHEET_FORMATS = [("A4", 210.0, 297.0), ("A5", 148.0, 210.0), ("A3", 297.0, 420.0), ("Letter", 215.9, 279.4)]
SHEET_ANCHORS = [("— поставить —", None), ("левый верхний угол", (0, 0)), ("сверху по центру", (1, 0)),
                 ("правый верхний угол", (2, 0)), ("по центру листа", (1, 1)), ("левый нижний угол", (0, 2)),
                 ("снизу по центру", (1, 2)), ("правый нижний угол", (2, 2))]


def sheet_templates_load() -> list:
    """Шаблоны размещения на листе: [{name, sheet:[w,h], w, h, x, y, rot, bg, trim}] (мм)."""
    out = []
    for t in settings_load().get("sheet_templates", []) or []:
        try:
            if t.get("name") and float(t.get("w", 0)) > 0 and float(t.get("h", 0)) > 0:
                out.append(t)
        except Exception:
            continue
    return out


def sheet_template_add(t: dict):
    s = settings_load()
    items = [x for x in (s.get("sheet_templates", []) or []) if x.get("name") != t.get("name")]
    items.append(t)
    s["sheet_templates"] = items
    settings_save(s)


def sheet_template_remove(name: str):
    s = settings_load()
    s["sheet_templates"] = [x for x in (s.get("sheet_templates", []) or []) if x.get("name") != name]
    settings_save(s)


def trim_object_box(im):
    """Рамка самого документа на снимке (без однотонных полей). None — обрезать нечего."""
    try:
        W, H = im.size
        small = im.convert("RGB").resize((max(8, W // 6), max(8, H // 6)), Image.BILINEAR)
        w, h = small.size
        c = max(2, min(w, h) // 40)
        corners = Image.new("RGB", (c * 2, c * 2))
        for n, box in enumerate(((0, 0, c, c), (w - c, 0, w, c), (0, h - c, c, h), (w - c, h - c, w, h))):
            corners.paste(small.crop(box), ((n % 2) * c, (n // 2) * c))
        bg = tuple(int(v) for v in ImageStat.Stat(corners).median)
        diff = ImageChops.difference(small, Image.new("RGB", (w, h), bg)).convert("L")
        diff = diff.point(lambda v: 255 if v > 22 else 0).filter(ImageFilter.MedianFilter(5))
        bb = diff.getbbox()
        if not bb:
            return None
        x0, y0, x1, y1 = bb
        if (x1 - x0) * (y1 - y0) > 0.97 * w * h or (x1 - x0) < w * 0.08 or (y1 - y0) < h * 0.08:
            return None
        kx, ky = W / w, H / h
        return (max(0, int(x0 * kx)), max(0, int(y0 * ky)), min(W, int(x1 * kx) + 1), min(H, int(y1 * ky) + 1))
    except Exception:
        return None


def place_on_sheet(obj, t: dict, dpi: int = 200):
    """Положить документ obj (PIL) на лист по настройкам t → PIL RGB всего листа.

    t: sheet [ш, в] мм; w, h — размер документа на листе, мм; x, y — отступ от левого
    и верхнего края, мм; rot — 0/90/180/270; bg — builtin (стекло сканера) или white."""
    mm = dpi / 25.4
    sw, sh = (float(v) for v in (t.get("sheet") or (210.0, 297.0)))
    W, H = max(8, int(round(sw * mm))), max(8, int(round(sh * mm)))
    base = builtin_scanner_bg() if t.get("bg", "builtin") == "builtin" else None
    if base is not None:
        if (W > H) != (base.width > base.height):
            base = base.transpose(Image.ROTATE_90)
        sheet = base.resize((W, H), Image.LANCZOS)
    else:
        sheet = Image.new("RGB", (W, H), (255, 255, 255))
    rot = int(t.get("rot", 0)) % 360
    frag = obj.convert("RGB")
    if rot == 90:
        frag = frag.transpose(Image.ROTATE_270)          # по часовой стрелке
    elif rot == 180:
        frag = frag.transpose(Image.ROTATE_180)
    elif rot == 270:
        frag = frag.transpose(Image.ROTATE_90)
    fw, fh = max(2, int(round(float(t["w"]) * mm))), max(2, int(round(float(t["h"]) * mm)))
    frag = frag.resize((fw, fh), Image.LANCZOS)
    x, y = int(round(float(t.get("x", 0)) * mm)), int(round(float(t.get("y", 0)) * mm))
    if base is not None:
        bgc = tuple(int(v) for v in ImageStat.Stat(sheet.resize((32, 32))).median)
        paste_sheet(sheet, frag, (x, y), bgc)
    else:
        sheet.paste(frag, (x, y))
    return sheet


class SheetPreview(QWidget):
    """Лист с документом: документ можно таскать мышью."""
    moved = Signal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(380, 520)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)
        self._pm = None
        self._sheet = (210.0, 297.0)
        self._obj = (0.0, 0.0, 10.0, 10.0)
        self._grab = None

    def set_state(self, pixmap, sheet_mm, obj_mm):
        self._pm, self._sheet, self._obj = pixmap, sheet_mm, obj_mm
        self.update()

    def _geom(self):
        sw, sh = self._sheet
        k = min((self.width() - 16) / sw, (self.height() - 16) / sh)
        return k, (self.width() - sw * k) / 2, (self.height() - sh * k) / 2

    def _obj_rect(self):
        k, ox, oy = self._geom()
        x, y, w, h = self._obj
        return QRectF(ox + x * k, oy + y * k, w * k, h * k)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        k, ox, oy = self._geom()
        sw, sh = self._sheet
        area = QRectF(ox, oy, sw * k, sh * k)
        p.fillRect(area.adjusted(3, 3, 3, 3), QColor(0, 0, 0, 40))
        if self._pm is not None:
            p.drawPixmap(area, self._pm, QRectF(self._pm.rect()))
        else:
            p.fillRect(area, QColor("#ffffff"))
        p.setPen(QPen(QColor("#9a9482"), 1))
        p.drawRect(area)
        pen = QPen(QColor("#d99a1c"), 1.6, Qt.DashLine)
        p.setPen(pen)
        p.setClipRect(area.adjusted(-2, -2, 2, 2))
        p.drawRect(self._obj_rect())
        p.end()

    def mousePressEvent(self, e):
        r = self._obj_rect()
        if e.button() == Qt.LeftButton and r.contains(e.position()):
            self._grab = (e.position().x() - r.x(), e.position().y() - r.y())

    def mouseMoveEvent(self, e):
        if self._grab is None:
            self.setCursor(Qt.OpenHandCursor if self._obj_rect().contains(e.position()) else Qt.ArrowCursor)
            return
        self.setCursor(Qt.ClosedHandCursor)
        k, ox, oy = self._geom()
        self.moved.emit((e.position().x() - self._grab[0] - ox) / k, (e.position().y() - self._grab[1] - oy) / k)

    def mouseReleaseEvent(self, _):
        self._grab = None
        self.setCursor(Qt.ArrowCursor)


class SheetPlaceDialog(QDialog):
    """Окно «Разместить на листе»: документ любого размера кладётся на лист, как на стекло сканера."""

    def __init__(self, obj_img, natural_mm, parent=None, n_pages=1):
        super().__init__(parent)
        self.setWindowTitle("Разместить на листе")
        self.resize(1040, 800)
        self.setMinimumSize(920, 640)
        self._src = obj_img
        self._src_mm = natural_mm
        self._busy = False
        self._rot = 0
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(60)
        self._timer.timeout.connect(self._render)

        root = QHBoxLayout(self)
        root.setSpacing(14)
        self.preview = SheetPreview()
        self.preview.moved.connect(self._dragged)
        root.addWidget(self.preview, 1)

        side_w = QWidget()
        side = QVBoxLayout(side_w)
        side.setContentsMargins(0, 0, 6, 0)
        side.setSpacing(8)
        hint = QLabel("Задайте настоящий размер документа и место на листе — документ можно "
                      "двигать мышью. Настройки сохраняются шаблоном.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        side.addWidget(hint)

        box_t = QGroupBox("Шаблон")
        lt = QVBoxLayout(box_t)
        lt.setSpacing(6)
        self.cmb_tpl = QComboBox()
        lt.addWidget(self.cmb_tpl)
        row = QHBoxLayout()
        self.btn_tpl_save = QPushButton("Сохранить шаблон…")
        self.btn_tpl_del = QPushButton("Удалить")
        row.addWidget(self.btn_tpl_save, 1)
        row.addWidget(self.btn_tpl_del)
        lt.addLayout(row)
        side.addWidget(box_t)

        box_s = QGroupBox("Лист")
        fs = QFormLayout(box_s)
        fs.setSpacing(6)
        self.cmb_sheet = QComboBox()
        for name, w, h in SHEET_FORMATS:
            self.cmb_sheet.addItem(f"{name} · {w:g}×{h:g}", (w, h))
        self.cmb_sheet.addItem("Свой размер", None)
        self.cmb_orient = QComboBox()
        self.cmb_orient.addItem("книжный", "p")
        self.cmb_orient.addItem("альбомный", "l")
        row = QHBoxLayout()
        row.addWidget(self.cmb_sheet, 1)
        row.addWidget(self.cmb_orient)
        fs.addRow("Формат:", row)
        self.sp_sw, self.sp_sh = self._mm_spin(30, 1200, 210), self._mm_spin(30, 1200, 297)
        row = QHBoxLayout()
        row.addWidget(self.sp_sw)
        row.addWidget(QLabel("×"))
        row.addWidget(self.sp_sh)
        self.row_custom = QWidget()
        self.row_custom.setLayout(row)
        row.setContentsMargins(0, 0, 0, 0)
        self.lbl_custom = QLabel("Размер:")
        fs.addRow(self.lbl_custom, self.row_custom)
        self.cmb_bg = QComboBox()
        self.cmb_bg.addItem("стекло сканера, как скан", "builtin")
        self.cmb_bg.addItem("чистый белый лист", "white")
        fs.addRow("Фон:", self.cmb_bg)
        side.addWidget(box_s)

        box_o = QGroupBox("Документ на листе")
        fo = QFormLayout(box_o)
        fo.setSpacing(6)
        self.sp_w, self.sp_h = self._mm_spin(5, 1200, 100), self._mm_spin(5, 1200, 100)
        row = QHBoxLayout()
        row.addWidget(self.sp_w, 1)
        row.addWidget(QLabel("×"))
        row.addWidget(self.sp_h, 1)
        fo.addRow("Размер:", row)
        self.chk_lock = QCheckBox("Сохранять пропорции")
        self.chk_lock.setChecked(True)
        fo.addRow("", self.chk_lock)
        row = QHBoxLayout()
        self.btn_rl, self.btn_rr = QPushButton(" Влево"), QPushButton(" Вправо")
        for b, kind in ((self.btn_rl, "rot_left"), (self.btn_rr, "rot_right")):
            b.setIcon(draw_icon(kind, ui_icon_color(), 18))
            b.setToolTip("Повернуть документ на 90°")
            row.addWidget(b)
        fo.addRow("Поворот:", row)
        self.sp_x, self.sp_y = self._mm_spin(-600, 1200, 0), self._mm_spin(-600, 1200, 0)
        self.sp_x.setToolTip("Отступ от левого края листа")
        self.sp_y.setToolTip("Отступ от верхнего края листа")
        row = QHBoxLayout()
        row.addWidget(QLabel("слева"))
        row.addWidget(self.sp_x, 1)
        row.addWidget(QLabel("сверху"))
        row.addWidget(self.sp_y, 1)
        fo.addRow("Отступ:", row)
        self.cmb_anchor = QComboBox()
        for name, a in SHEET_ANCHORS:
            self.cmb_anchor.addItem(name, a)
        fo.addRow("Место:", self.cmb_anchor)
        self.chk_trim = QCheckBox("Обрезать пустые поля вокруг документа")
        self.chk_trim.setToolTip("Если документ снят на однотонном фоне — оставить только сам документ")
        fo.addRow("", self.chk_trim)
        side.addWidget(box_o)

        box_r = QGroupBox("Куда положить результат")
        if n_pages > 1:
            box_r.setTitle(f"Куда положить результат (страниц: {n_pages})")
        lr = QHBoxLayout(box_r)
        lr.setSpacing(10)
        self.rb_doc = QRadioButton("Заменить страницу")
        self.rb_doc.setToolTip("Лист встанет на место страницы в открытом документе")
        self.rb_new = QRadioButton("Новым PDF рядом")
        self.rb_new.setToolTip("Лист сохранится отдельным файлом, открытый документ не изменится")
        self.rb_doc.setChecked(True)
        lr.addWidget(self.rb_doc)
        lr.addWidget(self.rb_new)
        lr.addStretch(1)
        side.addWidget(box_r)
        side.addStretch(1)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Разместить")
        bb.button(QDialogButtonBox.Cancel).setText("Отмена")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(side_w)
        col = QVBoxLayout()
        col.setSpacing(8)
        col.addWidget(scroll, 1)
        col.addWidget(bb)
        holder = QWidget()
        holder.setFixedWidth(430)
        holder.setLayout(col)
        col.setContentsMargins(0, 0, 0, 0)
        root.addWidget(holder)

        self._obj = self._src
        self._small = None
        self._prepare_obj()
        self._fill_templates()
        self._natural_size()

        for sp in (self.sp_sw, self.sp_sh, self.sp_x, self.sp_y):
            sp.valueChanged.connect(self._changed)
        self.sp_w.valueChanged.connect(lambda v: self._size_changed("w"))
        self.sp_h.valueChanged.connect(lambda v: self._size_changed("h"))
        self.cmb_sheet.currentIndexChanged.connect(self._sheet_changed)
        self.cmb_orient.currentIndexChanged.connect(self._sheet_changed)
        self.cmb_bg.currentIndexChanged.connect(self._changed)
        self.cmb_anchor.activated.connect(self._anchor)
        self.chk_trim.toggled.connect(self._trim_toggled)
        self.btn_rl.clicked.connect(lambda: self._rotate(-90))
        self.btn_rr.clicked.connect(lambda: self._rotate(90))
        self.cmb_tpl.activated.connect(self._tpl_picked)
        self.btn_tpl_save.clicked.connect(self._tpl_save)
        self.btn_tpl_del.clicked.connect(self._tpl_delete)
        self._sheet_changed()
        last = settings_load().get("sheet_last_template")
        i = self.cmb_tpl.findText(last) if last else -1
        if i > 0:
            self.cmb_tpl.setCurrentIndex(i)
            self._tpl_picked(i)
        self._render()

    # ---------------------------------------------------------- мелочи
    @staticmethod
    def _mm_spin(lo, hi, val):
        sp = QDoubleSpinBox()
        sp.setRange(lo, hi)
        sp.setDecimals(1)
        sp.setSingleStep(1.0)
        sp.setSuffix(" мм")
        sp.setValue(val)
        sp.setMinimumWidth(92)
        return sp

    def _prepare_obj(self):
        """Документ для укладки: целиком или без пустых полей; уменьшенная копия — для превью."""
        self._obj, self._obj_mm = self._src, self._src_mm
        if self.chk_trim.isChecked():
            box = trim_object_box(self._src)
            if box:
                self._obj = self._src.crop(box)
                kx, ky = self._src_mm[0] / self._src.width, self._src_mm[1] / self._src.height
                self._obj_mm = ((box[2] - box[0]) * kx, (box[3] - box[1]) * ky)
        small = self._obj.copy()
        small.thumbnail((640, 640), Image.BILINEAR)
        self._small = small

    def _aspect(self):
        """Ширина / высота документа так, как он лежит на листе."""
        a = self._obj.width / max(1, self._obj.height)
        return 1.0 / a if self._rot in (90, 270) else a

    def sheet_mm(self):
        d = self.cmb_sheet.currentData()
        w, h = d if d else (self.sp_sw.value(), self.sp_sh.value())
        if d and self.cmb_orient.currentData() == "l":
            w, h = h, w
        return float(w), float(h)

    def _natural_size(self):
        """Настоящий размер документа; если он больше листа — вписать."""
        w, h = self._obj_mm
        if self._rot in (90, 270):
            w, h = h, w
        sw, sh = self.sheet_mm()
        k = min(1.0, sw / w, sh / h)
        self._set(self.sp_w, w * k)
        self._set(self.sp_h, h * k)

    def _set(self, sp, v):
        sp.blockSignals(True)
        sp.setValue(round(float(v), 1))
        sp.blockSignals(False)

    # ---------------------------------------------------------- события
    def _changed(self, *_):
        if not self._busy:
            self._timer.start()

    def _size_changed(self, which):
        if self.chk_lock.isChecked():
            a = self._aspect()
            if which == "w":
                self._set(self.sp_h, self.sp_w.value() / a)
            else:
                self._set(self.sp_w, self.sp_h.value() * a)
        self._changed()

    def _sheet_changed(self, *_):
        custom = self.cmb_sheet.currentData() is None
        self.row_custom.setVisible(custom)
        self.lbl_custom.setVisible(custom)
        self.cmb_orient.setEnabled(not custom)
        self._changed()

    def _rotate(self, step):
        self._rot = (self._rot + step) % 360
        w, h = self.sp_w.value(), self.sp_h.value()
        self._set(self.sp_w, h)
        self._set(self.sp_h, w)
        self._changed()

    def _anchor(self, i):
        a = self.cmb_anchor.itemData(i)
        self.cmb_anchor.setCurrentIndex(0)
        if not a:
            return
        sw, sh = self.sheet_mm()
        self._set(self.sp_x, (sw - self.sp_w.value()) * a[0] / 2)
        self._set(self.sp_y, (sh - self.sp_h.value()) * a[1] / 2)
        self._changed()

    def _trim_toggled(self, _):
        self._prepare_obj()
        if self.chk_lock.isChecked():
            self._set(self.sp_h, self.sp_w.value() / self._aspect())
        self._changed()

    def _dragged(self, x, y):
        self._set(self.sp_x, x)
        self._set(self.sp_y, y)
        self._changed()

    # ---------------------------------------------------------- шаблоны
    def _fill_templates(self, pick=None):
        self.cmb_tpl.blockSignals(True)
        self.cmb_tpl.clear()
        self.cmb_tpl.addItem("— без шаблона —", None)
        for t in sheet_templates_load():
            self.cmb_tpl.addItem(t["name"], t)
        i = self.cmb_tpl.findText(pick) if pick else 0
        self.cmb_tpl.setCurrentIndex(max(0, i))
        self.cmb_tpl.blockSignals(False)
        self.btn_tpl_del.setEnabled(self.cmb_tpl.currentIndex() > 0)

    def template(self) -> dict:
        """Текущие настройки (они же — содержимое шаблона)."""
        sw, sh = self.sheet_mm()
        return {"sheet": [round(sw, 1), round(sh, 1)], "w": round(self.sp_w.value(), 1),
                "h": round(self.sp_h.value(), 1), "x": round(self.sp_x.value(), 1),
                "y": round(self.sp_y.value(), 1), "rot": self._rot, "bg": self.cmb_bg.currentData(),
                "trim": self.chk_trim.isChecked()}

    def apply_template(self, t: dict):
        self._busy = True
        try:
            sw, sh = (float(v) for v in (t.get("sheet") or (210, 297)))
            found = False
            for i, (_, w, h) in enumerate(SHEET_FORMATS):
                for orient, (a, b) in (("p", (w, h)), ("l", (h, w))):
                    if abs(a - sw) < 0.6 and abs(b - sh) < 0.6 and not found:
                        self.cmb_sheet.setCurrentIndex(i)
                        self.cmb_orient.setCurrentIndex(0 if orient == "p" else 1)
                        found = True
            if not found:
                self.cmb_sheet.setCurrentIndex(self.cmb_sheet.count() - 1)
                self._set(self.sp_sw, sw)
                self._set(self.sp_sh, sh)
            self.chk_trim.blockSignals(True)
            self.chk_trim.setChecked(bool(t.get("trim")))
            self.chk_trim.blockSignals(False)
            self._prepare_obj()
            self._rot = int(t.get("rot", 0)) % 360
            self.chk_lock.setChecked(False)          # размер из шаблона ставится точно, как сохранён
            self._set(self.sp_w, t["w"])
            self._set(self.sp_h, t["h"])
            self._set(self.sp_x, t.get("x", 0))
            self._set(self.sp_y, t.get("y", 0))
            i = self.cmb_bg.findData(t.get("bg", "builtin"))
            self.cmb_bg.setCurrentIndex(max(0, i))
        finally:
            self._busy = False
        self._sheet_changed()

    def _tpl_picked(self, i):
        t = self.cmb_tpl.itemData(i)
        self.btn_tpl_del.setEnabled(bool(t))
        if t:
            self.apply_template(t)

    def _tpl_save(self):
        cur = self.cmb_tpl.currentText() if self.cmb_tpl.currentIndex() > 0 else ""
        name, ok = QInputDialog.getText(self, "Шаблон", "Название шаблона (например, «СТС Германия»):", text=cur)
        name = (name or "").strip()
        if not ok or not name:
            return
        t = self.template()
        t["name"] = name
        sheet_template_add(t)
        self._fill_templates(name)

    def _tpl_delete(self):
        name = self.cmb_tpl.currentText()
        if self.cmb_tpl.currentIndex() <= 0:
            return
        if QMessageBox.question(self, "Шаблон", f"Удалить шаблон «{name}»?") != QMessageBox.Yes:
            return
        sheet_template_remove(name)
        self._fill_templates()

    # ---------------------------------------------------------- картинка
    def _render(self):
        t = self.template()
        try:
            im = place_on_sheet(self._small, t, dpi=44)
            qi = QImage(im.tobytes(), im.width, im.height, im.width * 3, QImage.Format_RGB888).copy()
            pm = QPixmap.fromImage(qi)
        except Exception:
            pm = None
        self.preview.set_state(pm, tuple(t["sheet"]), (t["x"], t["y"], t["w"], t["h"]))

    def result_object(self, src_img):
        """Документ для укладки из страницы src_img (с учётом «обрезать поля»)."""
        if self.chk_trim.isChecked():
            box = trim_object_box(src_img)
            if box:
                return src_img.crop(box)
        return src_img

    def accept(self):
        s = settings_load()
        s["sheet_last_template"] = self.cmb_tpl.currentText() if self.cmb_tpl.currentIndex() > 0 else ""
        settings_save(s)
        super().accept()


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
        tip_ai = ""
        try:
            if any(AI.page_has_text(src_doc[i]) and not AI.is_scan_page(src_doc[i])
                   for i in range(src_doc.page_count)):
                tip_ai = ("<br><b>Совет:</b> проверку ИИ делайте <b>до</b> этого шага — пока в документе "
                          "текст, ИИ читает его точно.")
        except Exception:
            pass
        hint = QLabel("Сначала поставьте печать и подпись, потом жмите сюда — они окажутся "
                      "на бумаге и «отсканируются» вместе с листом." + tip_ai)
        hint.setTextFormat(Qt.RichText)
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

        b_again = QPushButton("Другой вариант")
        b_again.setToolTip("Зерно бумаги и пылинки каждый раз чуть другие — нажмите, чтобы перебросить.\n"
                           "Лист всегда лежит ровно, без наклона.")
        b_again.clicked.connect(self._reroll)
        side.addWidget(b_again)

        pbox = QGroupBox("Какие страницы")
        pl = QVBoxLayout(pbox)
        pl.setSpacing(6)
        n = self.src_doc.page_count
        # как в окне печати Word: все / текущая / поле с номерами
        self.rb_all = QRadioButton(f"Все страницы ({n})")
        self.rb_cur = QRadioButton(f"Текущая страница (стр. {self.page_index + 1})")
        self.rb_custom = QRadioButton("Страницы:")
        self.rb_all.setChecked(True)
        pl.addWidget(self.rb_all)
        pl.addWidget(self.rb_cur)
        prow = QHBoxLayout()
        prow.setSpacing(8)
        prow.addWidget(self.rb_custom)
        self.ed_pages = QLineEdit()
        self.ed_pages.setPlaceholderText("1-3, 5, 7")
        self.ed_pages.setMinimumHeight(28)
        self.ed_pages.setToolTip("Номера страниц через запятую, диапазоны через дефис.\nНапример: 1-3, 5, 7")
        prow.addWidget(self.ed_pages, 1)
        pl.addLayout(prow)
        self.lbl_pages = QLabel("")
        self.lbl_pages.setObjectName("hint")
        pl.addWidget(self.lbl_pages)
        side.addWidget(pbox)
        tbox = QGroupBox("Куда сохранить")
        tl = QVBoxLayout(tbox)
        tl.setSpacing(6)
        self.rb_here = QRadioButton("В открытый документ")
        self.rb_here.setToolTip("Страницы открытого документа заменяются на «скан».\n"
                                "В файл это попадёт, когда вы нажмёте «Сохранить».")
        self.rb_new = QRadioButton("Новым PDF — только выбранные страницы")
        self.rb_new.setToolTip("Программа спросит имя и сохранит «скан» отдельным файлом.\n"
                               "В новый файл попадут только выбранные страницы, остальные не добавляются.\n"
                               "Открытый документ и печати на нём останутся как были.")
        (self.rb_new if st.get("target") == "new" else self.rb_here).setChecked(True)
        tl.addWidget(self.rb_here)
        tl.addWidget(self.rb_new)
        side.addWidget(tbox)
        if preselect and len(preselect) > 1:
            self.rb_custom.setChecked(True)
            self.ed_pages.setText(pages_to_text(preselect))
        elif n > 1 and st.get("pages_mode") == "current":
            self.rb_cur.setChecked(True)
        for rb in (self.rb_all, self.rb_cur, self.rb_custom):
            rb.toggled.connect(self._pages_changed)
        self.rb_custom.clicked.connect(lambda: self.ed_pages.setFocus())
        self.ed_pages.textEdited.connect(lambda _t: self.rb_custom.setChecked(True))
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
        mode = self.pages_mode()
        n = self.src_doc.page_count
        if mode == "all":
            return list(range(n))
        if mode == "current":
            return [self.page_index]
        return parse_pages(self.ed_pages.text(), n)

    def pages_mode(self):
        return "all" if self.rb_all.isChecked() else "current" if self.rb_cur.isChecked() else "custom"

    def _pages_changed(self, *_):
        pages = self.selected_pages()
        ok_btn = getattr(self, "_ok_btn", None)
        if pages:
            self.lbl_pages.setText(f"будет обработано страниц: {len(pages)}")
        else:
            self.lbl_pages.setText("введите номера страниц, например 1-3, 5, 7")
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
                "pages_mode": self.pages_mode(),
                "target": "new" if self.rb_new.isChecked() else "here",
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


class DateTimeDialog(QDialog):
    """Дата и время программы: часы компьютера, любой часовой пояс или своя дата; сверка с интернетом."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Дата и время")
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.setMinimumWidth(560)
        st = settings_load()
        mode, zone, shift = AI.date_settings(st)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 14)
        lay.setSpacing(10)
        self.lbl_now = QLabel("")
        self.lbl_now.setObjectName("aihead")
        lay.addWidget(self.lbl_now)
        sub = QLabel("Эта дата стоит внизу окна и передаётся ИИ как сегодняшняя — по ней он судит о датах в документе.")
        sub.setObjectName("hint")
        sub.setWordWrap(True)
        lay.addWidget(sub)

        self.rb_pc = QRadioButton("Автоматически — как на этом компьютере")
        self.rb_pc.setToolTip("Дата и время берутся из Windows. Подходит почти всегда.")
        lay.addWidget(self.rb_pc)

        self.rb_zone = QRadioButton("Часовой пояс:")
        self.rb_zone.setToolTip("Если часы компьютера стоят в другом поясе, а документы оформляются по времени другого города.")
        self.cmb_zone = QComboBox()
        self.cmb_zone.setMinimumHeight(30)
        for key, _ in AI.DATE_ZONES:
            self.cmb_zone.addItem(AI.zone_title(key), key)
        i = self.cmb_zone.findData(zone if zone != "pc" else "3")
        self.cmb_zone.setCurrentIndex(max(0, i))
        rz = QHBoxLayout()
        rz.addWidget(self.rb_zone)
        rz.addWidget(self.cmb_zone, 1)
        lay.addLayout(rz)

        self.rb_man = QRadioButton("Своя дата:")
        self.rb_man.setToolTip("Например, документы оформляются завтрашним числом.\n"
                               "Программа запомнит разницу в днях и будет сама переходить на следующий день.")
        self.ed_date = QDateEdit()
        self.ed_date.setCalendarPopup(True)
        self.ed_date.setDisplayFormat("dd.MM.yyyy")
        self.ed_date.setMinimumHeight(30)
        base = datetime.date.today() + datetime.timedelta(days=shift if mode == "manual" else 0)
        self.ed_date.setDate(QDate(base.year, base.month, base.day))
        self.lbl_shift = QLabel("")
        self.lbl_shift.setObjectName("hint")
        rm = QHBoxLayout()
        rm.addWidget(self.rb_man)
        rm.addWidget(self.ed_date)
        rm.addWidget(self.lbl_shift, 1)
        lay.addLayout(rm)

        self.chk_time = QCheckBox("Показывать внизу окна и время (часы:минуты)")
        self.chk_time.setChecked(bool(st.get("date_show_time")))
        lay.addWidget(self.chk_time)

        net = QHBoxLayout()
        self.b_net = QPushButton("Сверить с интернетом")
        self.b_net.setToolTip("Узнать точное время из сети и сравнить с часами компьютера")
        self.b_net.clicked.connect(self._check_net)
        net.addWidget(self.b_net)
        self.lbl_net = QLabel("")
        self.lbl_net.setObjectName("hint")
        self.lbl_net.setWordWrap(True)
        net.addWidget(self.lbl_net, 1)
        lay.addLayout(net)

        row = QHBoxLayout()
        row.addStretch(1)
        ok = QPushButton("Сохранить")
        ok.setObjectName("primary")
        ok.clicked.connect(self._save)
        row.addWidget(ok)
        b = QPushButton("Отмена")
        b.clicked.connect(self.reject)
        row.addWidget(b)
        lay.addLayout(row)

        {"pc": self.rb_pc, "zone": self.rb_zone, "manual": self.rb_man}.get(mode, self.rb_pc).setChecked(True)
        for wdg in (self.rb_pc, self.rb_zone, self.rb_man):
            wdg.toggled.connect(self._sync)
        self.cmb_zone.currentIndexChanged.connect(lambda *_: (self.rb_zone.setChecked(True), self._sync()))
        self.ed_date.dateChanged.connect(lambda *_: (self.rb_man.setChecked(True), self._sync()))
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._sync)
        self._timer.start()
        self._sync()

    def values(self):
        mode = "zone" if self.rb_zone.isChecked() else ("manual" if self.rb_man.isChecked() else "pc")
        qd = self.ed_date.date()
        shift = (datetime.date(qd.year(), qd.month(), qd.day()) - datetime.date.today()).days
        return {"date_mode": mode, "date_zone": self.cmb_zone.currentData() if mode == "zone" else "pc",
                "date_shift": shift if mode == "manual" else 0, "date_show_time": self.chk_time.isChecked()}

    def _sync(self, *_):
        v = self.values()
        t = AI.now(v)
        day = ("понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье")[t.weekday()]
        self.lbl_now.setText(f"{t.strftime('%d.%m.%Y')}, {day} · {t.strftime('%H:%M:%S')}")
        sh = v["date_shift"]
        self.lbl_shift.setText("" if v["date_mode"] != "manual" else
                               ("совпадает с компьютером" if not sh else
                                f"{'+' if sh > 0 else '−'}{abs(sh)} дн. к дате компьютера"))

    def _check_net(self):
        self.b_net.setEnabled(False)
        self.lbl_net.setText("Спрашиваю время в интернете…")
        box = {}

        class _T(QThread):
            def run(self_t):
                box["utc"] = AI.internet_time()

        th = _T(self)
        loop = QEventLoop(self)
        th.finished.connect(loop.quit)
        th.start()
        if th.isRunning():
            loop.exec()
        th.wait()
        self.b_net.setEnabled(True)
        utc = box.get("utc")
        if utc is None:
            self.lbl_net.setText("Не получилось — нет интернета. Программа продолжит брать время с компьютера.")
            return
        pc_utc = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        diff = (pc_utc - utc).total_seconds()
        local = utc + (datetime.datetime.now() - pc_utc)
        if abs(diff) < 90:
            self.lbl_net.setText(f"✔ Часы компьютера точные: в интернете сейчас {local.strftime('%d.%m.%Y %H:%M')} "
                                 "(по поясу компьютера).")
        else:
            m = int(abs(diff) // 60)
            self.lbl_net.setText(f"⚠ Часы компьютера {'спешат' if diff > 0 else 'отстают'} на {m} мин: "
                                 f"в интернете {local.strftime('%d.%m.%Y %H:%M')}. Поправьте время в Windows "
                                 "(Параметры → Время и язык → «Синхронизировать»).")

    def _save(self):
        st = settings_load()
        st.update(self.values())
        settings_save(st)
        self.accept()


class CloudThread(QThread):
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, uri, local, snap, private_local, parent=None):
        super().__init__(parent)
        self.args = (uri, local, snap, private_local)

    def run(self):
        try:
            self.done.emit(CLOUD.sync(*self.args))
        except Exception as e:
            self.failed.emit(CLOUD.explain(e))


class SettingsDialog(QDialog):
    """Файл → Настройки: всё, что настраивается в программе, в одном окне по разделам."""

    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.setWindowTitle("Настройки")
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.resize(780, 580)
        self.setMinimumSize(720, 560)
        st = settings_load()
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 12)
        root.setSpacing(10)
        body = QHBoxLayout()
        body.setSpacing(12)
        root.addLayout(body, 1)
        self.cats = QListWidget()
        self.cats.setFixedWidth(180)
        self.cats.setSpacing(2)
        self.cats.setFocusPolicy(Qt.NoFocus)
        body.addWidget(self.cats)
        self.stack = QStackedWidget()
        body.addWidget(self.stack, 1)

        def page(title, hint=""):
            wdg = QWidget()
            lay = QVBoxLayout(wdg)
            lay.setContentsMargins(6, 2, 6, 2)
            lay.setSpacing(9)
            h = QLabel(title)
            h.setObjectName("aihead")
            lay.addWidget(h)
            if hint:
                t = QLabel(hint)
                t.setObjectName("hint")
                t.setWordWrap(True)
                lay.addWidget(t)
            self.cats.addItem(title)
            self.stack.addWidget(wdg)
            return lay

        def check(lay, text, key, default, tip=""):
            c = QCheckBox(text)
            c.setChecked(bool(st.get(key, default)))
            if tip:
                c.setToolTip(tip)
            lay.addWidget(c)
            self._checks.append((c, key))
            return c

        def button(lay, text, slot, tip=""):
            row = QHBoxLayout()
            b = QPushButton(text)
            b.setMinimumHeight(30)
            if tip:
                b.setToolTip(tip)
            b.clicked.connect(slot)
            row.addWidget(b)
            row.addStretch(1)
            lay.addLayout(row)
            return b

        self._checks = []
        # ---- Общие
        l = page("Общие")
        self.rb_light = QRadioButton("Светлая тема")
        self.rb_dark = QRadioButton("Тёмная тема")
        (self.rb_dark if win.theme == "dark" else self.rb_light).setChecked(True)
        tr = QHBoxLayout()
        tr.addWidget(self.rb_light)
        tr.addWidget(self.rb_dark)
        tr.addStretch(1)
        l.addLayout(tr)
        l.addStretch(1)
        # ---- Обновления
        l = page("Обновления", f"Сейчас установлена версия {APP_VERSION}.")
        check(l, "Проверять обновления при запуске", "auto_update", True,
              "Программа сама спросит, когда выйдет новая версия")
        button(l, "Проверить сейчас", lambda: win.check_updates(silent=False))
        button(l, "Версии и откат…", win.show_versions, "Вернуться к прежней версии, если новая не подошла")
        l.addStretch(1)
        # ---- Дата и время
        l = page("Дата и время", "Дата внизу окна; её же ИИ считает сегодняшней, когда проверяет документ.")
        self.lbl_date = QLabel("")
        self.lbl_date.setObjectName("plain")
        l.addWidget(self.lbl_date)
        button(l, "Настроить дату и время…", self._date)
        l.addStretch(1)
        # ---- Сохранение
        l = page("Сохранение", "Значения по умолчанию для окна «Сохранить как». В самом окне их можно менять на ходу.")
        check(l, "Вшивать печати и подписи в страницу", "flatten_on_save", True,
              "Печать становится частью страницы — её нельзя сдвинуть или вытащить из PDF")
        check(l, "Очищать метаданные PDF (автор, программа, даты)", "clean_metadata", True)
        l.addStretch(1)
        # ---- Сканер
        l = page("Сканер")
        check(l, "Сканировать через окно драйвера сканера", "scan_via_dialog", False,
              "Включите, если нужны настройки самого сканера: двусторонняя подача, яркость и т. п.")
        l.addStretch(1)
        # ---- ИИ
        l = page("ИИ-помощник", "Что ИИ делает сам и через какие сервисы работает.")
        self.chk_ai = QCheckBox("Работать автоматически")
        self.chk_ai.setChecked(bool(st.get("ai_auto")))
        self.chk_ai.setToolTip("То же, что галочка в меню «ИИ»")
        l.addWidget(self.chk_ai)
        check(l, "   после сканирования предлагать имя файла", "ai_auto_name", True)
        check(l, "   после сканирования распознавать текст", "ai_auto_ocr", True)
        check(l, "Если сервис не отвечает — перейти к следующему", "ai_failover", True)
        button(l, "Ключи и сервисы ИИ…", win.ai_settings)
        l.addStretch(1)
        # ---- Редактор Word
        l = page("Редактор Word", "Свои поля шаблонов и номера документов. Хранятся только на этом компьютере.")
        self.box_old = QWidget()
        lo = QVBoxLayout(self.box_old)
        lo.setContentsMargins(0, 0, 0, 0)
        lo.setSpacing(6)
        cap = QLabel("Клиенты, сохранённые до версии 6.7 (теперь карточка лежит в папке клиента):")
        cap.setObjectName("plain")
        lo.addWidget(cap)
        self.lst_cl = QListWidget()
        self.lst_cl.setMaximumHeight(64)
        lo.addWidget(self.lst_cl)
        button(lo, "Удалить выбранного клиента", self._del_client)
        l.addWidget(self.box_old)
        cap = QLabel("Шаблоны со своими полями:")
        cap.setObjectName("plain")
        l.addWidget(cap)
        self.lst_tp = QListWidget()
        self.lst_tp.setMaximumHeight(64)
        l.addWidget(self.lst_tp)
        button(l, "Забыть поля выбранного шаблона", self._del_marks)
        cap = QLabel("Номера документов (последний выданный номер по каждому шаблону):")
        cap.setObjectName("plain")
        l.addWidget(cap)
        self.lst_num = QListWidget()
        self.lst_num.setMinimumHeight(96)
        self.lst_num.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.lst_num.setTextElideMode(Qt.ElideMiddle)
        l.addWidget(self.lst_num)
        nrow = QHBoxLayout()
        b1 = QPushButton("Последний номер…")
        b1.clicked.connect(self._edit_counter)
        nrow.addWidget(b1)
        b2 = QPushButton("Авто / вручную")
        b2.setToolTip("Авто — программа ставит следующий номер сама. Вручную — номер вписываете вы.")
        b2.clicked.connect(self._toggle_counter)
        nrow.addWidget(b2)
        b3 = QPushButton("Сброс с 1 января")
        b3.setToolTip("Если в номере есть год («329–2026»): начинать ли счёт с 1 в новом году")
        b3.clicked.connect(self._toggle_reset)
        nrow.addWidget(b3)
        nrow.addStretch(1)
        l.addLayout(nrow)
        l.addStretch(1)
        # ---- Подписи
        l = page("Подписи", "По умолчанию каждая подпись ставится вручную, на своё место. "
                            "Расстановку разом включайте, только если сами так решили.")
        check(l, "Разрешить ставить подпись на все места разом", "sign_all_enabled", False,
              "Появится пункт «Правка → Подписать все места…»: программа найдёт в документе строки\n"
              "подписи выбранного человека и поставит его подпись на каждую.")
        l.addStretch(1)
        # ---- Облако
        l = page("Облако", "Копия печатей, клиентов и настроек в вашей базе MongoDB Atlas. Всё остаётся и на компьютере: "
                           "без интернета программа работает как обычно и досылает изменения позже.")
        self.ed_uri = QLineEdit(cloud_uri())
        self.ed_uri.setEchoMode(QLineEdit.Password)
        self.ed_uri.setMinimumHeight(30)
        self.ed_uri.setPlaceholderText("mongodb+srv://логин:пароль@cluster0.xxxxx.mongodb.net/")
        self.ed_uri.setToolTip("Строка подключения из Atlas: Connect → Drivers. Как её получить — в справке (F1), раздел «Облако».")
        l.addWidget(self.ed_uri)
        urow = QHBoxLayout()
        b_eye = QPushButton("Показать")
        b_eye.setCheckable(True)
        b_eye.toggled.connect(lambda on: (self.ed_uri.setEchoMode(QLineEdit.Normal if on else QLineEdit.Password),
                                          b_eye.setText("Скрыть" if on else "Показать")))
        urow.addWidget(b_eye)
        b_chk = QPushButton("Проверить подключение")
        b_chk.clicked.connect(self._cloud_check)
        urow.addWidget(b_chk)
        b_cp = QPushButton("Скопировать строку")
        b_cp.setToolTip("Сохраните копию строки у себя: после переустановки Windows её придётся вставить заново")
        b_cp.clicked.connect(lambda: (QApplication.clipboard().setText(self.ed_uri.text().strip()),
                                      self.lbl_cloud.setText("Строка скопирована — сохраните её в надёжном месте.")))
        urow.addWidget(b_cp)
        urow.addStretch(1)
        l.addLayout(urow)
        self.lbl_cloud = QLabel("")
        self.lbl_cloud.setObjectName("plain")
        self.lbl_cloud.setWordWrap(True)
        self.lbl_cloud.setMinimumHeight(38)
        self.lbl_cloud.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        l.addWidget(self.lbl_cloud)
        parts = st.get("cloud_parts") or {}
        self.cloud_checks = {}
        for key, text in (("stamps", "Печати и подписи"), ("clients", "Карточки клиентов"),
                          ("settings", "Поля шаблонов Word, наборы ручки, шаблоны имён"),
                          ("counters", "Номера документов (общий счётчик, без повторов)")):
            c = QCheckBox(text)
            c.setChecked(bool(parts.get(key, True)))
            l.addWidget(c)
            self.cloud_checks[key] = c
        check(l, "Паспортные данные — только на этом компьютере", "cloud_private_local", False,
              "Паспорт, кем выдан, адрес и дата рождения не уйдут в базу. Остальное в карточке — уйдёт.")
        srow = QHBoxLayout()
        b_sync = QPushButton("Синхронизировать сейчас")
        b_sync.clicked.connect(self._cloud_now)
        srow.addWidget(b_sync)
        b_off = QPushButton("Отключить облако")
        b_off.setToolTip("Стереть строку на этом компьютере. Данные в базе и на компьютере останутся.")
        b_off.clicked.connect(lambda: (self.ed_uri.clear(), self.lbl_cloud.setText(
            "Строка будет стёрта, когда нажмёте «Сохранить». Данные никуда не денутся.")))
        srow.addWidget(b_off)
        srow.addStretch(1)
        l.addLayout(srow)
        note = QLabel("Строка хранится в папке данных программы, зашифрованная средствами Windows: обновления и откат "
                      "версии её не трогают. У кого строка одна и та же — у тех общие печати и клиенты.")
        note.setObjectName("hint")
        note.setWordWrap(True)
        l.addWidget(note)
        l.addStretch(1)
        # ---- Данные программы
        l = page("Данные программы", "Библиотека печатей, настройки и ключи лежат в одной папке. "
                                     "Скопируйте её — и перенесёте программу на другой компьютер со всеми печатями.")
        pth = QLabel(LIB_DIR)
        pth.setObjectName("path")
        pth.setTextInteractionFlags(Qt.TextSelectableByMouse)
        pth.setWordWrap(True)
        l.addWidget(pth)
        button(l, "Открыть папку", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(LIB_DIR)))
        l.addStretch(1)

        row = QHBoxLayout()
        row.addStretch(1)
        ok = QPushButton("Сохранить")
        ok.setObjectName("primary")
        ok.clicked.connect(self._save)
        row.addWidget(ok)
        b = QPushButton("Закрыть")
        b.clicked.connect(self.reject)
        row.addWidget(b)
        root.addLayout(row)
        self.cats.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.cats.setCurrentRow(0)
        self._fill()

    def _fill(self):
        st = settings_load()
        mode, zone, _shift = AI.date_settings(st)
        how = {"pc": "как на этом компьютере", "zone": AI.zone_title(zone), "manual": "дата задана вручную"}.get(mode, "")
        self.lbl_date.setText(f"Сегодня: {AI.today_text(True)}  ·  {how}")
        self.lst_cl.clear()
        for name, data in sorted((st.get("word_clients") or {}).items(), key=lambda x: x[0].lower()):
            it = QListWidgetItem(f"{name}  ·  полей: {len(data)}")
            it.setData(Qt.UserRole, name)
            self.lst_cl.addItem(it)
        self.box_old.setVisible(bool(st.get("word_clients")))
        self.lst_num.clear()
        for name, c in sorted((st.get("doc_counters") or {}).items()):
            it = QListWidgetItem(f"{c.get('last') or '—'}  ·  {'авто' if c.get('mode', 'auto') == 'auto' else 'вручную'}"
                                 f"  ·  сброс: {'да' if c.get('reset', True) else 'нет'}  ·  {name}")
            it.setToolTip(name)
            it.setData(Qt.UserRole, name)
            self.lst_num.addItem(it)
        self.lst_tp.clear()
        for name, marks in sorted((st.get("word_marks") or {}).items()):
            if marks:
                it = QListWidgetItem(f"{name}  ·  полей: {len(marks)}")
                it.setData(Qt.UserRole, name)
                self.lst_tp.addItem(it)

    def _date(self):
        if DateTimeDialog(self).exec() == QDialog.Accepted:
            self.win._date_tick()
            self._fill()

    def _del_client(self):
        it = self.lst_cl.currentItem()
        if it is None:
            return
        st = settings_load()
        (st.get("word_clients") or {}).pop(it.data(Qt.UserRole), None)
        settings_save(st)
        self._fill()

    def _cloud_check(self):
        uri = self.ed_uri.text().strip()
        self.lbl_cloud.setText("Проверяю подключение…")
        QApplication.processEvents()
        box = {}

        class _T(QThread):
            def run(self_t):
                box["res"] = CLOUD.check(uri)

        th = _T(self)
        loop = QEventLoop(self)
        th.finished.connect(loop.quit)
        th.start()
        if th.isRunning():
            loop.exec()
        th.wait()
        ok, msg = box.get("res", (False, "Не удалось проверить"))
        self.lbl_cloud.setText(("✔ " if ok else "⚠ ") + msg)
        return ok

    def _cloud_store(self):
        st = settings_load()
        uri = self.ed_uri.text().strip()
        old = CLOUD.unprotect(st.get("cloud_uri", ""))
        if uri != old:
            st["cloud_uri"] = CLOUD.protect(uri) if uri else ""
        st["cloud_parts"] = {k: c.isChecked() for k, c in self.cloud_checks.items()}
        settings_save(st)

    def _cloud_now(self):
        self._cloud_store()
        st = settings_load()
        for c, key in self._checks:
            if key == "cloud_private_local":
                st[key] = c.isChecked()
        settings_save(st)
        if not cloud_uri():
            self.lbl_cloud.setText("⚠ Сначала вставьте строку подключения.")
            return
        self.lbl_cloud.setText("Синхронизирую…")
        self.win.cloud_sync(manual=True, report=lambda text: self.lbl_cloud.setText(text))

    def _counter_edit(self, fn):
        it = self.lst_num.currentItem()
        if it is None:
            return
        st = settings_load()
        c = st.setdefault("doc_counters", {}).setdefault(it.data(Qt.UserRole), {})
        if fn(c) is False:
            return
        settings_save(st)
        row = self.lst_num.currentRow()
        self._fill()
        self.lst_num.setCurrentRow(row)

    def _edit_counter(self):
        def fn(c):
            text, ok = QInputDialog.getText(self, "Последний номер", "Последний выданный номер (следующий будет на 1 больше):",
                                            text=str(c.get("last", "")))
            if not ok:
                return False
            c["last"] = text.strip()
            c["ts"] = c["forced_ts"] = time.time()
        self._counter_edit(fn)

    def _toggle_counter(self):
        self._counter_edit(lambda c: c.__setitem__("mode", "manual" if c.get("mode", "auto") == "auto" else "auto"))

    def _toggle_reset(self):
        self._counter_edit(lambda c: c.__setitem__("reset", not c.get("reset", True)))

    def _del_marks(self):
        it = self.lst_tp.currentItem()
        if it is None:
            return
        st = settings_load()
        (st.get("word_marks") or {}).pop(it.data(Qt.UserRole), None)
        settings_save(st)
        self._fill()

    def _save(self):
        self._cloud_store()
        st = settings_load()
        for c, key in self._checks:
            st[key] = c.isChecked()
        settings_save(st)
        want = "dark" if self.rb_dark.isChecked() else "light"
        if want != self.win.theme:
            self.win.toggle_theme()
        if self.chk_ai.isChecked() != bool(settings_load().get("ai_auto")):
            self.win.act_ai_auto.setChecked(self.chk_ai.isChecked())
            self.win.ai_toggle_auto(self.chk_ai.isChecked())
        self.win._ai_center_refresh()
        self.win._sign_all_state()
        self.win._cloud_label()
        self.win.cloud_soon(1500)
        self.accept()


class ReleasesThread(QThread):
    """Список выпущенных версий с GitHub — для возврата к прежней версии."""
    result = Signal(object, str)        # ([{version, date, url, notes}], текст ошибки)

    def run(self):
        try:
            import urllib.request
            api = GITHUB_URL.replace("https://github.com/", "https://api.github.com/repos/") + "/releases?per_page=40"
            req = urllib.request.Request(api, headers={"User-Agent": "StampStudio-Updater",
                                                       "Accept": "application/vnd.github+json"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            want = "StampStudioCanon-Setup-" if EDITION == "canon" else "StampStudio-Setup-"
            out = []
            for r in data:
                if r.get("draft") or r.get("prerelease"):
                    continue
                url = next((a.get("browser_download_url") for a in r.get("assets") or []
                            if str(a.get("name", "")).startswith(want)), "")
                if not url:
                    continue
                out.append({"version": str(r.get("tag_name", "")).lstrip("v"),
                            "date": str(r.get("published_at") or "")[:10],
                            "url": url, "notes": str(r.get("body") or "").strip()})
            out.sort(key=lambda x: vtuple(x["version"]), reverse=True)
            self.result.emit(out, "")
        except Exception as e:
            self.result.emit(None, str(e))


class VersionsDialog(QDialog):
    """Все выпущенные версии: можно вернуться к прежней или поставить любую заново."""

    def __init__(self, releases, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Версии Stamp Studio")
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.resize(760, 520)
        self.releases = releases
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)
        head = QLabel(f"Сейчас установлена версия {APP_VERSION}")
        head.setObjectName("aihead")
        lay.addWidget(head)
        sub = QLabel("Если после обновления что-то стало хуже — выберите прежнюю версию и нажмите «Установить». "
                     "Печати, подписи, настройки и ключи ИИ сохраняются. После возврата программа не будет сама "
                     "предлагать версию, с которой вы ушли, — только более новую.")
        sub.setObjectName("hint")
        sub.setWordWrap(True)
        lay.addWidget(sub)
        body = QHBoxLayout()
        body.setSpacing(10)
        self.lst = QListWidget()
        self.lst.setFixedWidth(230)
        newest = releases[0]["version"] if releases else ""
        for r in releases:
            tag = "  · установлена" if r["version"] == APP_VERSION else ("  · последняя" if r["version"] == newest else "")
            d = r["date"]
            d = f"{d[8:10]}.{d[5:7]}.{d[:4]}" if len(d) == 10 else d
            it = QListWidgetItem(f"{r['version']}   {d}{tag}")
            if r["version"] == APP_VERSION:
                f = it.font(); f.setBold(True); it.setFont(f)
            self.lst.addItem(it)
        body.addWidget(self.lst)
        self.txt = QTextBrowser()
        self.txt.setOpenExternalLinks(True)
        body.addWidget(self.txt, 1)
        lay.addLayout(body, 1)
        row = QHBoxLayout()
        row.addStretch(1)
        self.b_go = QPushButton("Установить")
        self.b_go.setObjectName("primary")
        self.b_go.clicked.connect(self.accept)
        row.addWidget(self.b_go)
        b = QPushButton("Закрыть")
        b.clicked.connect(self.reject)
        row.addWidget(b)
        lay.addLayout(row)
        self.lst.currentRowChanged.connect(self._show)
        cur = next((i for i, r in enumerate(releases) if vtuple(r["version"]) < vtuple(APP_VERSION)), 0)
        self.lst.setCurrentRow(cur)

    def _show(self, row):
        if not (0 <= row < len(self.releases)):
            self.b_go.setEnabled(False)
            return
        r = self.releases[row]
        same = r["version"] == APP_VERSION
        older = vtuple(r["version"]) < vtuple(APP_VERSION)
        self.b_go.setEnabled(not same)
        self.b_go.setText("Уже установлена" if same else
                          (f"Вернуться к {r['version']}" if older else f"Обновить до {r['version']}"))
        notes = r["notes"] or "Описание для этой версии не сохранилось."
        self.txt.setPlainText(f"Что вошло в версию {r['version']}:\n\n{notes}")

    def chosen(self):
        row = self.lst.currentRow()
        return self.releases[row] if 0 <= row < len(self.releases) else None


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
            t.setAlignment(Qt.AlignTop | Qt.AlignLeft)
            # длинный список прокручивается внутри — окно не вылезает за экран
            sc = QScrollArea()
            sc.setWidgetResizable(True)
            sc.setFrameShape(QFrame.NoFrame)
            sc.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            sc.setWidget(t)
            sc.setMaximumHeight(300)
            sc.setMinimumHeight(min(300, max(60, t.heightForWidth(470) + 6)))
            bl.addWidget(sc)
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
        self.resize(880, 680)
        self.setMinimumSize(820, 640)
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
        self.btn_get = QPushButton(" Получить ключ")
        self.btn_get.setIcon(draw_icon("external", ui_icon_color()))
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
        rest = [p for p in ranked if not self._connected(p)]
        groups = (("ПОДКЛЮЧЕНЫ", [p for p in ranked if self._connected(p)]),
                  ("МОЖНО ДОБАВИТЬ — БЕСПЛАТНЫЕ", [p for p in rest if not p.get("paid") and not p.get("custom")]),
                  ("МОЖНО ДОБАВИТЬ — ПЛАТНЫЕ", [p for p in rest if p.get("paid")]),
                  ("ДРУГОЕ", [p for p in rest if p.get("custom")]))
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
        if state == "нужен ключ":
            state = "нужен ключ — нажмите «Получить ключ», вставьте его ниже и нажмите «Проверить»"
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
        if result.get("parts", 1) > 1:
            text += (" " if text else "") + (f"Документ проверен по частям ({result['parts']} запроса): "
                                             "совпадение данных между далёкими страницами сверьте сами.")
        if "распознан" in (result.get("mode") or ""):
            text += (" " if text else "") + ("Изображения страниц ни один сервис прочитать не смог — проверен текст, "
                                             "распознанный на компьютере, поэтому опечатки не проверялись.")
        if result.get("provider"):
            text += (" " if text else "") + f"Ответил: {result['provider'].split(' (')[0]} · {result.get('model', '')}."
        stars = next((p["stars"] for p in AI.PROVIDERS if p["name"] == result.get("provider")), 5)
        if stars and stars <= 3:
            text += (" Это запасной сервис, он читает документы слабее — для важного документа "
                     "выберите вверху сервис с 4–5 звёздами и повторите.")
        if result.get("dropped"):
            text += (f" Скрыто замечаний без обоснования: {result['dropped']} "
                     "(ИИ назвал что-то «неправильным», но не показал, с чем это расходится).")
        text += (" " if text else "") + (f"Сегодня {AI.today().strftime('%d.%m.%Y')}. "
                                         "ИИ может ошибаться — это подсказка, а не гарантия.")
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
            if it.get("expected"):
                line += f"\n      → {it['expected'][:200]}"
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


class AiCenterDialog(QDialog):
    """ИИ-помощник одним окном: выбор сервиса, счётчики запросов, пять функций и результат тут же."""

    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.setWindowFlags(Qt.Widget)          # не отдельное окно, а страница внутри главного
        self.setObjectName("aipage")
        self._embedded = None
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 10, 16, 10)
        root.setSpacing(8)

        head = QHBoxLayout()
        head.setSpacing(10)
        self.b_back = QPushButton(" К документу")
        self.b_back.setIcon(draw_icon("back", win._icon_color()))
        self.b_back.setIconSize(QSize(16, 16))
        win._themed_buttons.append((self.b_back, "back", False))
        self.b_back.setCursor(Qt.PointingHandCursor)
        self.b_back.setToolTip("Вернуться к странице документа (Esc). Результат ИИ останется здесь.")
        self.b_back.clicked.connect(lambda: win.ai_mode(False))
        head.addWidget(self.b_back)
        ttl = QLabel("ИИ-ПОМОЩНИК")
        ttl.setObjectName("paneltitle")
        head.addWidget(ttl)
        self.lbl_doc = QLabel("")
        self.lbl_doc.setObjectName("hint")
        self.lbl_doc.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        head.addWidget(self.lbl_doc, 1)
        self.lbl_date = QLabel("")
        self.lbl_date.setObjectName("hint")
        self.lbl_date.setToolTip("Эту дату ИИ считает сегодняшней. Изменить пояс — щелчок по дате внизу окна.")
        head.addWidget(self.lbl_date)
        root.addLayout(head)

        # ---- через кого
        top = QHBoxLayout()
        top.setSpacing(8)
        cap = QLabel("Через кого:")
        cap.setObjectName("plain")
        top.addWidget(cap)
        self.cmb = QComboBox()
        self.cmb.setMinimumHeight(32)
        self.cmb.setMinimumWidth(200)
        self.cmb.setToolTip("Какой сервис ИИ читает документ. В списке — только подключённые (с ключом).")
        top.addWidget(self.cmb, 1)
        self.chk_fail = QCheckBox("если не отвечает — перейти к следующему")
        self.chk_fail.setToolTip("Включено: при лимите или сбое программа сама спросит следующий сервис из списка.\n"
                                 "Выключено: спрашивается только выбранный сервис.")
        top.addWidget(self.chk_fail)
        b_set = QPushButton("Ключи и настройки…")
        b_set.clicked.connect(self._settings)
        top.addWidget(b_set)
        root.addLayout(top)

        # ---- что сделать: пять функций в один ряд
        acts = QHBoxLayout()
        acts.setSpacing(8)
        self.btns = []
        for text, sub, slot in (
                ("Проверить", "Проверить перед отправкой: опечатки, расхождения в датах и суммах, пустые поля", win.ai_check),
                ("Данные", "Данные из документа: номер, дата, сумма, VIN — таблицей, можно скопировать", win.ai_extract),
                ("Имя файла", "Предложить имя файла: переименовать или сохранить под этим именем", win.ai_name),
                ("Печать на место", "Печать и подпись на место: найти «М.П.» и строку подписи", win.ai_place),
                ("Текст скана", "Распознать текст скана: в PDF заработают поиск и копирование", win.ai_ocr)):
            b = QPushButton(text)
            b.setObjectName("primary" if not self.btns else "")
            b.setCursor(Qt.PointingHandCursor)
            b.setMinimumHeight(36)
            b.setToolTip(sub)
            b.clicked.connect(lambda _=False, s=slot: s())
            acts.addWidget(b, 1)
            self.btns.append(b)
        root.addLayout(acts)

        # ---- счётчики запросов — компактной строкой
        cnt = QWidget()
        self.cl = QGridLayout(cnt)
        self.cl.setContentsMargins(2, 0, 2, 0)
        self.cl.setHorizontalSpacing(14)
        self.cl.setVerticalSpacing(4)
        root.addWidget(cnt)

        # ---- результат — на всю ширину
        self.res_box = QGroupBox("Результат")
        self.rl = QVBoxLayout(self.res_box)
        self.home = QLabel("")
        self.home.setObjectName("plain")
        self.home.setWordWrap(True)
        self.home.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.home.setTextFormat(Qt.RichText)
        self.rl.addWidget(self.home, 1)
        root.addWidget(self.res_box, 1)

        self.lbl_info = QLabel("")
        self.lbl_info.setObjectName("hint")
        self.lbl_info.setWordWrap(True)
        self.lbl_info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        root.addWidget(self.lbl_info)

        self.cmb.currentIndexChanged.connect(self._pick)
        self.chk_fail.toggled.connect(self._pick)
        self.refresh()
        self.show_home()

    # ---- состояние
    def refresh(self):
        s = settings_load()
        ready = [p for p in AI.PROVIDERS if AI.provider_ready(p, s)]
        chosen = s.get("ai_provider") or AI.default_provider(s)
        self.cmb.blockSignals(True)
        self.cmb.clear()
        for p in sorted(ready, key=lambda p: -p["stars"]):
            today, lim, share = AI.limit_state(p["name"], s)
            stars = "★" * p["stars"] + "☆" * (5 - p["stars"]) if p["stars"] else ""
            left = f"осталось ~{max(0, lim - today)}" if lim else "без дневного лимита"
            self.cmb.addItem(f"{p['name'].split(' (')[0]}  {stars}  ·  {p['short']}  ·  {left}", p["name"])
        i = self.cmb.findData(chosen)
        self.cmb.setCurrentIndex(max(0, i))
        self.cmb.blockSignals(False)
        self.chk_fail.blockSignals(True)
        self.chk_fail.setChecked(bool(s.get("ai_failover", True)))
        self.chk_fail.blockSignals(False)
        # счётчики
        while self.cl.count():
            it = self.cl.takeAt(0)
            if it.widget():
                it.widget().hide()
                it.widget().deleteLater()
        warn = []
        cap = QLabel("Запросы сегодня:")
        cap.setObjectName("hint")
        self.cl.addWidget(cap, 0, 0)
        per_row = 4
        for r, p in enumerate(sorted(ready, key=lambda p: -p["stars"])[:8]):
            name = p["name"]
            today, lim, share = AI.limit_state(name, s)
            cell = QWidget()
            v = QVBoxLayout(cell)
            v.setContentsMargins(0, 0, 0, 0)
            v.setSpacing(2)
            n = QLabel(f"{name.split(' (')[0]} · " + (f"{today} из ~{lim}" if lim else f"{today}, без лимита"))
            n.setObjectName("hint")
            v.addWidget(n)
            bar = QProgressBar()
            bar.setFixedHeight(4)
            bar.setTextVisible(False)
            bar.setRange(0, 100)
            bar.setValue(int(min(1.0, share) * 100) if lim else 0)
            if lim and share >= 0.8:
                bar.setStyleSheet("QProgressBar::chunk { background: #d9534f; border-radius: 2px; }")
                warn.append(name.split(" (")[0])
            v.addWidget(bar)
            cell.setToolTip(f"{name}\nСделано запросов сегодня: {today}" + (f" из примерно {lim} бесплатных" if lim else ""))
            self.cl.addWidget(cell, r // per_row, 1 + r % per_row)
        for col in range(1, 1 + per_row):
            self.cl.setColumnStretch(col, 1)
        has_doc = self.win.doc is not None
        for b in self.btns:
            b.setEnabled(has_doc)
        name = os.path.basename(str(self.win.doc_path or "")) if has_doc else ""
        fm = self.lbl_doc.fontMetrics()
        self.lbl_doc.setText(fm.elidedText(("Документ: " + name) if name else "Документ не открыт — выберите файл слева",
                                           Qt.ElideMiddle, max(120, self.lbl_doc.width() - 6)))
        self.lbl_doc.setToolTip(name)
        self.lbl_date.setText("Сегодня: " + AI.today_text())
        info = []
        if AI.LAST.get("provider"):
            info.append(f"Последний ответ: {AI.LAST['provider'].split(' (')[0]} · {AI.LAST['model']} · "
                        f"читал {AI.LAST['mode']}")
        if AI.LAST.get("problems"):
            info.append("Не ответили: " + "; ".join(AI.LAST["problems"][-4:]))
        if warn:
            info.append("⚠ Лимит на сегодня почти выбран: " + ", ".join(warn) +
                        (" — программа сама перейдёт к следующему сервису" if s.get("ai_failover", True)
                         else " — выберите другой сервис или включите переход к следующему"))
        if not has_doc:
            info.append("Откройте PDF или Word двойным щелчком в списке слева — и функции станут активны")
        self.lbl_info.setText("\n".join(info))

    def _pick(self, *_):
        s = settings_load()
        if self.cmb.currentData():
            s["ai_provider"] = self.cmb.currentData()
        s["ai_failover"] = self.chk_fail.isChecked()
        settings_save(s)

    def _settings(self):
        self.win.ai_settings()
        self.refresh()

    def reject(self):                           # Esc — назад к документу, страницу не прячем
        self.win.ai_mode(False)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        QTimer.singleShot(0, self._doc_label)

    def _doc_label(self):
        try:
            name = os.path.basename(str(self.win.doc_path or "")) if self.win.doc is not None else ""
            fm = self.lbl_doc.fontMetrics()
            self.lbl_doc.setText(fm.elidedText(("Документ: " + name) if name else
                                               "Документ не открыт — выберите файл слева",
                                               Qt.ElideMiddle, max(120, self.lbl_doc.width() - 6)))
        except RuntimeError:
            pass

    # ---- результат
    def show_home(self):
        self._drop()
        self.res_box.setTitle("Результат")
        self.home.setText(
            "<p>Откройте документ в списке файлов слева (PDF или Word) и нажмите кнопку вверху. "
            "Результат появится здесь же: "
            "его можно поправить, скопировать, сохранить в таблицу или применить к файлу.</p>"
            "<p><b>Как ИИ читает документ.</b> Страницы с текстом уходят текстом, сканы — изображениями "
            "(по 4 страницы за запрос). Если ни один сервис не смог прочитать изображения, уходит текст, "
            "распознанный на компьютере; тогда опечатки не проверяются, потому что в таком тексте "
            "искажены буквы. Чем читал последний ответ — написано внизу окна.</p>"
            "<p><b>Счётчик.</b> Над этим окном видно, сколько запросов сделано сегодня у каждого сервиса. "
            "Когда лимит близко, полоска краснеет, а программа сама начинает со следующего сервиса.</p>"
            "<p><b>Порядок работы.</b> Если документ ещё с текстом (из Word, не скан) — сначала "
            "проверка и данные, потом печать с подписью, и только в конце «Как скан». "
            "Пока текст настоящий, ИИ читает его без ошибок и одним запросом.</p>"
            "<p>ИИ может ошибаться — цифры и реквизиты сверяйте с документом.</p>")
        self.home.setVisible(True)

    def _drop(self):
        if self._embedded is not None:
            try:
                self.rl.removeWidget(self._embedded)
                self._embedded.setParent(None)
                self._embedded.deleteLater()
            except RuntimeError:
                pass
            self._embedded = None

    def embed(self, dlg, title):
        """Показать окно результата внутри помощника."""
        self._drop()
        self.home.setVisible(False)
        self.res_box.setTitle(title)
        dlg.setParent(self.res_box)
        dlg.setWindowFlags(Qt.Widget)
        dlg.setObjectName("embedded")
        dlg.setMinimumSize(0, 0)
        if dlg.layout() is not None:
            dlg.layout().setContentsMargins(0, 0, 0, 0)
        dlg.finished.connect(lambda *_: QTimer.singleShot(0, self.show_home))
        self.rl.addWidget(dlg, 1)
        self._embedded = dlg
        dlg.show()
        self.refresh()

    def note(self, text):
        self._drop()
        self.res_box.setTitle("Результат")
        self.home.setText(f"<p style='font-size:14px'>{text}</p>")
        self.home.setVisible(True)
        self.refresh()


WORD_PAR = QTextFormat.UserProperty + 1


class ClickLabel(QLabel):
    """Подпись, по которой можно щёлкнуть."""
    clicked = Signal()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(e)


class WordView(QTextEdit):
    """Документ Word на экране: шрифты, жирный, курсив, выравнивание и таблицы — как в файле.
    Текст правится прямо здесь; абзацы и таблицы нельзя склеить или разорвать, поэтому вёрстка цела."""
    blocked = Signal(str)
    mark_asked = Signal(str)                 # пользователь хочет сделать выделенное полем шаблона

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("wordview")
        self.setAcceptRichText(False)
        self.setAcceptDrops(False)
        self.setStyleSheet("QTextEdit#wordview { background: #ffffff; color: #111111; border: 1px solid "
                           "rgba(128,128,128,0.35); border-radius: 6px; selection-background-color: #f1c15b; "
                           "selection-color: #111111; }")
        self.wd = None
        self.par_pos = {}                    # номер абзаца → позиция блока (сразу после построения)
        self.par_tabs = {}                   # номер абзаца → смещения табуляций в тексте абзаца

    # ---- построение
    def build(self, wd):
        from docx.text.paragraph import Paragraph
        self.wd = wd
        self.par_pos, self.par_tabs = {}, {}
        doc = wd.doc
        idx = {id(p): i for i, p in enumerate(wd.pars)}
        q = lambda n: "{%s}%s" % (SW.W, n)
        d = QTextDocument(self)                 # строим в стороне от экрана: большие таблицы собираются мгновенно
        d.setUndoRedoEnabled(False)
        d.setDocumentMargin(26)
        grid_col = QColor("#c9c9c9")

        def eff(run, par, attr):
            try:
                v = getattr(run.font, attr)
                if v is not None:
                    return v
                for st in (run.style, par.style):
                    while st is not None:
                        v = getattr(st.font, attr, None)
                        if v is not None:
                            return v
                        st = st.base_style
            except Exception:
                pass
            return None

        def put_par(p_el, cur, first):
            i = idx.get(id(p_el))
            par = Paragraph(p_el, doc._body)
            bf = QTextBlockFormat()
            try:
                al = par.alignment
                if al is None and par.style is not None:
                    al = par.style.paragraph_format.alignment
                bf.setAlignment({1: Qt.AlignHCenter, 2: Qt.AlignRight, 3: Qt.AlignJustify}.get(
                    int(al) if al is not None else 0, Qt.AlignLeft))
                pf = par.paragraph_format
                if pf.left_indent:
                    bf.setLeftMargin(max(0.0, pf.left_indent.pt * 1.33))
                if pf.first_line_indent and pf.first_line_indent.pt > 0:
                    bf.setTextIndent(pf.first_line_indent.pt * 1.33)
                bf.setTopMargin((pf.space_before.pt if pf.space_before is not None else 0) * 1.33)
                bf.setBottomMargin((pf.space_after.pt if pf.space_after is not None else 0) * 1.33)
            except Exception:
                pass
            if i is not None:
                bf.setProperty(WORD_PAR, i)
            if first:
                cur.setBlockFormat(bf)
            else:
                cur.insertBlock(bf)
            if i is None:
                return
            self.par_pos[i] = cur.block().position()
            own = set(id(t) for t in wd._texts[i])
            tabs, off = [], 0
            cf_last = None
            try:
                runs = par.runs
            except Exception:
                runs = []
            seen = set()
            for r in runs:
                cf = QTextCharFormat()
                f = QFont(eff(r, par, "name") or "Times New Roman")
                sz = eff(r, par, "size")
                f.setPointSizeF(max(5.0, sz.pt if sz else 11.0))
                f.setBold(bool(eff(r, par, "bold")))
                f.setItalic(bool(eff(r, par, "italic")))
                f.setUnderline(bool(eff(r, par, "underline")))
                cf.setFont(f)
                cf.setForeground(QColor("#111111"))
                cf_last = cf
                for ch in r._r:
                    if ch.tag == q("t") and id(ch) in own:
                        cur.insertText(ch.text or "", cf)
                        off += len(ch.text or "")
                        seen.add(id(ch))
                    elif ch.tag == q("tab"):
                        cur.insertText("\t", cf)
                        tabs.append(off)
            rest = "".join(t.text or "" for t in wd._texts[i] if id(t) not in seen)
            if rest:                                         # текст в гиперссылках и вставках — без потерь
                cur.insertText(rest, cf_last or QTextCharFormat())
            if tabs:
                self.par_tabs[i] = tabs
            if cf_last is None:                              # пустой абзац: шрифт на случай, если сюда впишут
                cf = QTextCharFormat()
                f = QFont("Times New Roman")
                f.setPointSizeF(11.0)
                cf.setFont(f)
                cf.setForeground(QColor("#111111"))
                cur.setBlockCharFormat(cf)

        def span_of(tc):
            pr = tc.find(q("tcPr"))
            gs = pr.find(q("gridSpan")) if pr is not None else None
            try:
                return max(1, int(gs.get(q("val")))) if gs is not None else 1
            except (TypeError, ValueError):
                return 1

        def put_tbl(t_el, cur):
            rows = [r for r in t_el if r.tag == q("tr")]
            if not rows:
                return
            grid = t_el.find(q("tblGrid"))
            cols = []
            if grid is not None:
                for c in grid:
                    try:
                        cols.append(int(c.get(q("w")) or 0))
                    except ValueError:
                        cols.append(0)
            n = max([len(cols)] + [sum(span_of(tc) for tc in r if tc.tag == q("tc")) for r in rows])
            if n <= 0:
                return
            tf = QTextTableFormat()
            tf.setCellPadding(3)
            tf.setCellSpacing(0)
            tf.setBorder(0.5)
            tf.setBorderBrush(grid_col)
            tf.setBorderStyle(QTextFrameFormat.BorderStyle_Solid)
            tf.setBorderCollapse(True)
            tot = sum(cols) or 1
            tf.setColumnWidthConstraints([QTextLength(QTextLength.PercentageLength,
                                                      100.0 * (cols[k] if k < len(cols) and cols[k] else tot / n) / tot)
                                          for k in range(n)])
            tf.setWidth(QTextLength(QTextLength.PercentageLength, 100))
            tbl = cur.insertTable(len(rows), n, tf)
            for ri, r in enumerate(rows):
                ci = 0
                for tc in (c for c in r if c.tag == q("tc")):
                    if ci >= n:
                        break
                    span = min(span_of(tc), n - ci)
                    if span > 1:
                        tbl.mergeCells(ri, ci, 1, span)
                    cc = tbl.cellAt(ri, ci).firstCursorPosition()
                    fst = True
                    for ch in tc:
                        if ch.tag == q("p"):
                            put_par(ch, cc, fst)
                            fst = False
                            nested(ch, cc)
                        elif ch.tag == q("tbl"):
                            put_tbl(ch, cc)
                            fst = False
                    ci += span

        def nested(p_el, cur):
            """Надписи (текстовые рамки) внутри абзаца — отдельными абзацами следом."""
            for sub in p_el.iter(q("p")):
                if sub is not p_el and id(sub) in idx and idx[id(sub)] not in self.par_pos:
                    put_par(sub, cur, False)

        def put_all(container, cur, first):
            for ch in container:
                if ch.tag == q("p"):
                    put_par(ch, cur, first)
                    first = False
                    nested(ch, cur)
                elif ch.tag == q("tbl"):
                    put_tbl(ch, cur)
                    first = False
                    cur = QTextCursor(d)
                    cur.movePosition(QTextCursor.End)
            return cur

        def caption(cur, text, first):
            """Серая подпись-разделитель (колонтитулы); в неё печатать нельзя."""
            bf = QTextBlockFormat()
            bf.setBackground(QColor("#eceae4"))
            bf.setTopMargin(0 if first else 10)
            bf.setBottomMargin(2)
            cf = QTextCharFormat()
            f = QFont("Segoe UI")
            f.setPointSizeF(8.0)
            f.setBold(True)
            cf.setFont(f)
            cf.setForeground(QColor("#7a7466"))
            if first:
                cur.setBlockFormat(bf)
            else:
                cur.insertBlock(bf)
            cur.insertText(text, cf)

        cur = QTextCursor(d)
        first = True
        heads = [z for z in wd.zones if z[0].startswith("Верхний")]
        foots = [z for z in wd.zones if z[0].startswith("Нижний")]
        many = lambda zs, z: f"{z[0]} ({zs.index(z) + 1})" if len(zs) > 1 and sum(1 for x in zs if x[0] == z[0]) > 1 else z[0]
        for z in heads:
            caption(cur, many(heads, z).upper(), first)
            cur = put_all(z[1], cur, False)
            first = False
        if heads:
            caption(cur, "ТЕКСТ ДОКУМЕНТА", False)
        cur = put_all(doc.element.body, cur, first)
        for z in foots:
            cur = QTextCursor(d)
            cur.movePosition(QTextCursor.End)
            caption(cur, many(foots, z).upper(), False)
            cur = put_all(z[1], cur, False)
        d.setUndoRedoEnabled(True)
        d.setModified(False)
        self.setDocument(d)                     # прежний документ Qt удаляет сам
        c = self.textCursor()
        c.movePosition(QTextCursor.Start)
        self.setTextCursor(c)

    def pos_of(self, par, offset):
        """Позиция в окне для смещения внутри текста абзаца."""
        if par not in self.par_pos:
            return None
        return self.par_pos[par] + offset + sum(1 for t in self.par_tabs.get(par, ()) if t < offset or (t == offset == 0))

    def changed_paragraphs(self):
        """{номер абзаца: новый текст} — только то, что отличается от файла."""
        out, seen = {}, set()
        b = self.document().begin()
        while b.isValid():
            v = b.blockFormat().property(WORD_PAR)
            if v is not None and v not in seen:
                seen.add(v)
                text = b.text().replace("\t", "").replace(" ", "")
                if text != self.wd.text(int(v)):
                    out[int(v)] = text
            b = b.next()
        return out

    # ---- правка только внутри абзаца
    def _one_block(self):
        c = self.textCursor()
        if not c.hasSelection():
            return True
        d = self.document()
        return d.findBlock(c.selectionStart()) == d.findBlock(c.selectionEnd())

    def keyPressEvent(self, e):
        k = e.key()
        c = self.textCursor()
        if e.matches(QKeySequence.Copy) or e.matches(QKeySequence.SelectAll) or e.matches(QKeySequence.Undo) \
                or e.matches(QKeySequence.Redo) or k in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down, Qt.Key_Home,
                                                         Qt.Key_End, Qt.Key_PageUp, Qt.Key_PageDown, Qt.Key_Shift,
                                                         Qt.Key_Control, Qt.Key_Alt, Qt.Key_Meta, Qt.Key_Escape):
            if k == Qt.Key_Escape:
                e.ignore()
                return
            return super().keyPressEvent(e)
        if k in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Tab, Qt.Key_Backtab):
            self.blocked.emit("Новые абзацы и табуляция здесь не добавляются — так оформление остаётся целым")
            return
        if not self._one_block():
            self.blocked.emit("Выделите текст в пределах одного абзаца или одной ячейки — и печатайте")
            return
        if c.block().blockFormat().property(WORD_PAR) is None:
            self.blocked.emit("Это служебная строка — щёлкните в тексте документа")
            return
        if not c.hasSelection():
            if k == Qt.Key_Backspace and c.atBlockStart():
                return
            if k == Qt.Key_Delete and c.atBlockEnd():
                return
            if e.matches(QKeySequence.DeleteStartOfWord) or e.matches(QKeySequence.DeleteEndOfWord):
                return
        super().keyPressEvent(e)

    def insertFromMimeData(self, src):
        if not self._one_block() or self.textCursor().block().blockFormat().property(WORD_PAR) is None:
            self.blocked.emit("Выделите текст в пределах одного абзаца — и вставляйте")
            return
        text = re.sub(r"[\r\n\t]+", " ", src.text() or "").strip(" ")
        if text:
            self.textCursor().insertText(text)

    def contextMenuEvent(self, e):
        m = QMenu(self)
        c = self.textCursor()
        sel = c.selectedText() if c.hasSelection() and self._one_block() else ""
        if sel.strip():
            sub = m.addMenu("Сделать полем шаблона")
            sub.setToolTipsVisible(True)
            for key, title in SW.KEYS:
                sub.addAction(title, lambda k=key: self.mark_asked.emit(k))
            sub.addSeparator()
            sub.addAction("Своё название…", lambda: self.mark_asked.emit(""))
            m.addSeparator()
        m.addAction("Копировать", self.copy).setEnabled(c.hasSelection())
        a = m.addAction("Вставить", self.paste)
        a.setEnabled(self.canPaste())
        m.addAction("Отменить", self.undo)
        m.exec(e.globalPos())


class CardScanDialog(QDialog):
    """Что нашлось в сканах: человек проверяет и отмечает, что перенести в карточку."""

    def __init__(self, found, current, how, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Данные из сканов")
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.resize(720, 520)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 12)
        lay.setSpacing(10)
        head = QLabel(f"Найдено значений: {len(found)}" if found else "Ничего не удалось распознать")
        head.setObjectName("aihead")
        lay.addWidget(head)
        sub = QLabel(how + " Проверьте каждое значение по документу и поправьте, если нужно: двойной щелчок по ячейке. "
                           "В карточку попадут только отмеченные строки.")
        sub.setObjectName("hint")
        sub.setWordWrap(True)
        lay.addWidget(sub)
        self.tbl = QTableWidget(0, 3)
        self.tbl.setHorizontalHeaderLabels(["Поле", "Найдено в сканах", "Сейчас в карточке"])
        self.tbl.verticalHeader().setVisible(False)
        hh = self.tbl.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        hh.setSectionResizeMode(2, QHeaderView.Stretch)
        for key in [k for k in SW.CARD_KEYS if k in found]:
            r = self.tbl.rowCount()
            self.tbl.insertRow(r)
            it = QTableWidgetItem(SW.KEY_TITLES.get(key, key))
            it.setFlags((it.flags() | Qt.ItemIsUserCheckable) & ~Qt.ItemIsEditable)
            it.setCheckState(Qt.Checked if not current.get(key) or current.get(key) == found[key] else Qt.Unchecked)
            it.setData(Qt.UserRole, key)
            self.tbl.setItem(r, 0, it)
            self.tbl.setItem(r, 1, QTableWidgetItem(found[key]))
            old = QTableWidgetItem(current.get(key, ""))
            old.setFlags(old.flags() & ~Qt.ItemIsEditable)
            self.tbl.setItem(r, 2, old)
        lay.addWidget(self.tbl, 1)
        row = QHBoxLayout()
        row.addStretch(1)
        ok = QPushButton("Перенести в карточку")
        ok.setObjectName("primary")
        ok.setEnabled(bool(found))
        ok.clicked.connect(self.accept)
        row.addWidget(ok)
        b = QPushButton("Отмена")
        b.clicked.connect(self.reject)
        row.addWidget(b)
        lay.addLayout(row)

    def chosen(self):
        out = {}
        for r in range(self.tbl.rowCount()):
            it = self.tbl.item(r, 0)
            val = self.tbl.item(r, 1).text().strip()
            if it.checkState() == Qt.Checked and val:
                out[it.data(Qt.UserRole)] = val
        return out


class ClientCardDialog(QDialog):
    """Карточка клиента: лежит файлом в папке клиента, из неё заполняются документы."""

    def __init__(self, folder, parent=None, values=None):
        super().__init__(parent)
        self.folder = folder
        self.win = parent.win if hasattr(parent, "win") else parent
        self.setWindowTitle("Карточка клиента")
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.resize(760, 600)
        self.setMinimumSize(700, 480)
        self.stored = SW.card_load(folder)
        vals = dict(self.stored)
        vals.update(values or {})
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 12)
        lay.setSpacing(8)
        head = QLabel("Карточка клиента")
        head.setObjectName("aihead")
        lay.addWidget(head)
        sub = QLabel(f"Папка: {folder}\nДанные хранятся в самой папке клиента и подставляются во все его документы: "
                     "договор, счёт, акт, CMR.")
        sub.setObjectName("hint")
        sub.setWordWrap(True)
        lay.addWidget(sub)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QFrame.NoFrame)
        sc.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        sc.setStyleSheet("QScrollArea { background: transparent; } QScrollArea > QWidget > QWidget { background: transparent; }")
        holder = QWidget()
        g = QGridLayout(holder)
        g.setContentsMargins(2, 2, 10, 2)
        g.setHorizontalSpacing(12)
        g.setVerticalSpacing(6)
        g.setColumnStretch(1, 1)
        self.edits = {}
        row = 0
        for title, keys in SW.CARD_GROUPS:
            cap = QLabel(title.upper())
            cap.setObjectName("paneltitle")
            g.addWidget(cap, row, 0, 1, 2)
            row += 1
            for key in keys:
                lab = QLabel(SW.KEY_TITLES[key])
                lab.setObjectName("plain")
                g.addWidget(lab, row, 0)
                ed = QLineEdit(vals.get(key, ""))
                ed.setMinimumHeight(28)
                if key.startswith("sum_"):
                    ed.setPlaceholderText("число, без «руб.»")
                elif key in ("birth", "contract_date"):
                    ed.setPlaceholderText("ДД.ММ.ГГГГ")
                g.addWidget(ed, row, 1)
                self.edits[key] = ed
                row += 1
        g.setRowStretch(row, 1)
        sc.setWidget(holder)
        lay.addWidget(sc, 1)
        self.chk_ai = QCheckBox("Если на компьютере распознать не получилось — разрешаю отправить сканы в ИИ")
        self.chk_ai.setChecked(bool(settings_load().get("card_scan_ai", False)))
        self.chk_ai.setToolTip("Выключено: сканы никуда не уходят, распознавание делает сама Windows.\n"
                               "Включено: если данных нашлось мало, изображения паспорта и техпаспорта уйдут в сервис ИИ.")
        lay.addWidget(self.chk_ai)
        row_b = QHBoxLayout()
        b_scan = QPushButton("Заполнить из сканов…")
        b_scan.setToolTip("Паспорт, техпаспорт, инвойс: программа распознает их и предложит данные на проверку")
        b_scan.clicked.connect(self.from_scans)
        row_b.addWidget(b_scan)
        self._others = dict(settings_load().get("word_clients") or {})
        for key, vals in (_json_read(CLOUD_CLIENTS, {}) or {}).items():
            self._others.setdefault("облако: " + (vals.get("fio") or key), vals)
        old = sorted(self._others.keys(), key=str.lower)
        if old:
            self.cmb_old = QComboBox()
            self.cmb_old.addItem("Взять данные другого клиента…", None)
            for name in old:
                self.cmb_old.addItem(name, name)
            self.cmb_old.activated.connect(self._take_old)
            row_b.addWidget(self.cmb_old)
        row_b.addStretch(1)
        ok = QPushButton("Сохранить")
        ok.setObjectName("primary")
        ok.clicked.connect(self._save)
        row_b.addWidget(ok)
        b = QPushButton("Закрыть")
        b.clicked.connect(self.reject)
        row_b.addWidget(b)
        lay.addLayout(row_b)

    def values(self):
        return {k: e.text().strip() for k, e in self.edits.items() if e.text().strip()}

    def _take_old(self, *_):
        name = self.cmb_old.currentData()
        data = self._others.get(name) or {}
        for k, v in data.items():
            if k in self.edits and not self.edits[k].text().strip():
                self.edits[k].setText(str(v))

    def merge(self, found):
        for k, v in found.items():
            if k in self.edits:
                self.edits[k].setText(v)

    def from_scans(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Сканы: паспорт, техпаспорт, инвойс", self.folder,
                                                "Сканы и PDF (*.pdf *.jpg *.jpeg *.png)")
        if not paths:
            return
        allow_ai = self.chk_ai.isChecked()
        st = settings_load()
        st["card_scan_ai"] = allow_ai
        settings_save(st)
        try:
            doc = fitz.open()
            for p in paths:
                if p.lower().endswith(".pdf"):
                    src = open_pdf_free(p)
                    doc.insert_pdf(src)
                    src.close()
                else:
                    with Image.open(p) as im:
                        w_pt, h_pt = im.width * 72 / 200, im.height * 72 / 200
                    page = doc.new_page(width=w_pt, height=h_pt)
                    page.insert_image(page.rect, filename=p)
            bundle = AI.collect(doc, None, max_images=6)
        except Exception as e:
            QMessageBox.critical(self, "Сканы", f"Не удалось открыть файлы:\n{e}")
            return
        keys = [(k, SW.KEY_TITLES[k]) for k in SW.CARD_KEYS if not k.startswith("sum_") and k != "contract_date"]

        def work(status, cancel):
            status("Распознаю текст на компьютере…")
            text = bundle["text"] + "\n" + (AI.ocr_text_for(bundle) or "")
            found = SW.parse_client_text(text)
            how = "Распознано на этом компьютере, в интернет ничего не уходило."
            if allow_ai and len(found) < 4:
                status("Локально нашлось мало — спрашиваю ИИ…")
                try:
                    res = AI.task_card(bundle, keys, status, cancel)
                    for k, v in res["values"].items():
                        found.setdefault(k, v)              # найденное на компьютере важнее ответа ИИ
                    how = f"Часть данных прочитал ИИ ({res['provider'].split(' (')[0]}) — сканы были отправлены в этот сервис."
                except Exception as e:
                    how = "Распознано на этом компьютере. ИИ не ответил: " + str(e)[:120] + "."
            return {"found": found, "how": how}

        def done(res):
            cur = self.values()
            dlg = CardScanDialog(res["found"], cur, res["how"], self)
            if dlg.exec() == QDialog.Accepted:
                self.merge(dlg.chosen())

        if allow_ai and not self.win._ai_ready():
            allow_ai = False
        self.win._ai_run("Читаю сканы", work, done)

    def _save(self):
        card = {k: v for k, v in self.stored.items() if k not in self.edits}      # служебные записи (номера) сохраняем
        card.update(self.values())
        if not SW.card_save(self.folder, card):
            QMessageBox.warning(self, "Карточка клиента", "Не удалось записать карточку в папку:\n" + self.folder
                                + "\nПроверьте, что папка доступна для записи.")
            return
        self.accept()


class WordFillPage(QDialog):
    """Редактор документов Word внутри главного окна: слева сам документ с оформлением, справа — поля.
    Меняется только текст; шрифты, таблицы, нумерация и отступы остаются как в файле."""

    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.setWindowFlags(Qt.Widget)
        self.setObjectName("aipage")
        self.wd = None
        self.path = ""
        self.rows = []
        self.client_dir = ""
        self.card = {}
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 10, 16, 10)
        root.setSpacing(8)
        head = QHBoxLayout()
        head.setSpacing(10)
        b_back = QPushButton(" К документу")
        b_back.setIcon(draw_icon("back", win._icon_color()))
        b_back.setIconSize(QSize(16, 16))
        b_back.setCursor(Qt.PointingHandCursor)
        b_back.setToolTip("Вернуться к странице документа (Esc). Введённое здесь останется.")
        b_back.clicked.connect(lambda: win.ai_mode(False))
        win._themed_buttons.append((b_back, "back", False))
        head.addWidget(b_back)
        ttl = QLabel("РЕДАКТОР WORD")
        ttl.setObjectName("paneltitle")
        head.addWidget(ttl)
        self.lbl_doc = QLabel("")
        self.lbl_doc.setObjectName("hint")
        self.lbl_doc.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        head.addWidget(self.lbl_doc, 1)
        self.lbl_client = ClickLabel("")
        self.lbl_client.setObjectName("plain")
        self.lbl_client.setCursor(Qt.PointingHandCursor)
        self.lbl_client.setToolTip("Карточка клиента лежит в его папке: ФИО, паспорт, адрес, автомобиль, суммы.\n"
                                   "Поля документа заполняются из неё сами. Щелчок — открыть карточку.")
        self.lbl_client.clicked.connect(self._open_card)
        head.addWidget(self.lbl_client)
        self.b_card = QPushButton("Карточка…")
        self.b_card.setToolTip("Посмотреть и поправить данные клиента")
        self.b_card.clicked.connect(self._open_card)
        head.addWidget(self.b_card)
        self.b_dir = QPushButton("Папка клиента…")
        self.b_dir.setToolTip("Шаблон лежит отдельно от клиентов? Укажите папку клиента:\n"
                              "данные возьмутся из его карточки, а документ сохранится в эту папку.")
        self.b_dir.clicked.connect(self._pick_dir)
        head.addWidget(self.b_dir)
        root.addLayout(head)

        body = QHBoxLayout()
        body.setSpacing(10)
        root.addLayout(body, 1)
        self.view = WordView()
        self.view.blocked.connect(lambda t: self._say(t, warn=True))
        self.view.mark_asked.connect(self._add_mark)
        self.view.textChanged.connect(self._later)
        body.addWidget(self.view, 1)

        side = QVBoxLayout()
        side.setSpacing(6)
        drow = QHBoxLayout()
        drow.setSpacing(6)
        self.ed_all_date = QLineEdit()
        self.ed_all_date.setPlaceholderText("дата во все даты")
        self.ed_all_date.setMinimumHeight(30)
        self.ed_all_date.setToolTip("ДД.ММ.ГГГГ — встанет во все пустые даты документа: «11» ноября 2026 г.")
        self.ed_all_date.textChanged.connect(self._spread_date)
        drow.addWidget(self.ed_all_date, 1)
        b_today = QPushButton("Сегодня")
        b_today.clicked.connect(lambda: self.ed_all_date.setText(AI.today().strftime("%d.%m.%Y")))
        drow.addWidget(b_today)
        side.addLayout(drow)
        self.lbl_cnt = QLabel("")
        self.lbl_cnt.setObjectName("hint")
        side.addWidget(self.lbl_cnt)
        self.sc = QScrollArea()
        self.sc.setWidgetResizable(True)
        self.sc.setFrameShape(QFrame.NoFrame)
        self.sc.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.sc.setStyleSheet("QScrollArea { background: transparent; } "
                              "QScrollArea > QWidget > QWidget { background: transparent; }")
        side.addWidget(self.sc, 1)
        rrow = QHBoxLayout()
        rrow.setSpacing(6)
        self.ed_find = QLineEdit()
        self.ed_find.setPlaceholderText("найти")
        self.ed_find.setMinimumHeight(30)
        self.ed_repl = QLineEdit()
        self.ed_repl.setPlaceholderText("заменить на")
        self.ed_repl.setMinimumHeight(30)
        rrow.addWidget(self.ed_find, 1)
        rrow.addWidget(self.ed_repl, 1)
        side.addLayout(rrow)
        b_repl = QPushButton("Заменить во всём документе")
        b_repl.setToolTip("Заменить текст везде, где он встречается. Оформление не меняется.")
        b_repl.clicked.connect(self._replace_all)
        side.addWidget(b_repl)
        sw = QWidget()
        sw.setLayout(side)
        sw.setFixedWidth(320)
        body.addWidget(sw)

        foot = QHBoxLayout()
        self.lbl_info = QLabel("")
        self.lbl_info.setObjectName("hint")
        self.lbl_info.setWordWrap(True)
        foot.addWidget(self.lbl_info, 1)
        self.b_save = QPushButton("Сохранить как Word…")
        self.b_save.setObjectName("primary")
        self.b_save.setMinimumHeight(36)
        self.b_save.setToolTip("Сохранить документ новым файлом Word. Исходный файл остаётся нетронутым.")
        self.b_save.clicked.connect(self.save)
        foot.addWidget(self.b_save)
        root.addLayout(foot)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(180)
        self._timer.timeout.connect(self._paint_marks)
        self._home = ("Щёлкните в документе и печатайте: выделите текст — и впишите свой. Жирный, курсив, шрифты и "
                      "таблицы остаются как были. Справа — найденные места для заполнения. "
                      "Правая кнопка по выделенному — сделать его полем шаблона на будущее.")

    def reject(self):
        self.win.ai_mode(False)

    def _say(self, text, warn=False):
        self.lbl_info.setText(("⚠ " if warn else "") + text)
        if warn:
            QTimer.singleShot(5000, lambda: self.lbl_info.setText(self._home) if self.lbl_info.text().startswith("⚠") else None)

    def _later(self):
        self._timer.start()

    # ---- курсоры-якоря
    def _cursor(self, a, b):
        c = QTextCursor(self.view.document())
        c.setPosition(a)
        c.setPosition(b, QTextCursor.KeepAnchor)
        return c

    def _fmt_at(self, a, b):
        c = QTextCursor(self.view.document())
        c.setPosition(min(a + 1, b) if b > a else a)
        f = c.charFormat() if b > a else c.blockCharFormat()
        if b == a and c.block().length() > 1:
            f = c.charFormat()
        f.clearBackground()
        return f

    def _find_all(self, text):
        out = []
        d = self.view.document()
        b = d.begin()
        while b.isValid():
            if b.blockFormat().property(WORD_PAR) is not None:
                s, k = b.text(), 0
                while True:
                    k = s.find(text, k)
                    if k < 0:
                        break
                    out.append((b.position() + k, b.position() + k + len(text)))
                    k += len(text)
            b = b.next()
        return out

    def _new_row(self, label, key, kind, spans, field=None, mark=None, dummy=""):
        cs = [self._cursor(a, b) for a, b in spans]
        return {"label": label, "key": key, "kind": kind, "cursors": cs, "fmts": [self._fmt_at(a, b) for a, b in spans],
                "orig": [c.selectedText() for c in cs], "field": field, "mark": mark, "dummy": dummy,
                "auto": False, "edit": None, "current": (field.current if field is not None else "")}

    def _render(self, row, value):
        value = (value or "").strip()
        if not value:
            return None
        if row["field"] is not None:
            return row["field"].render(value)
        return value

    def _write(self, row, value):
        new = self._render(row, value)
        self.view.blockSignals(True)
        for k, c in enumerate(row["cursors"]):
            text = row["orig"][k] if new is None else new
            if c.selectedText() == text:
                continue
            c.beginEditBlock()
            c.insertText(text, row["fmts"][k])
            end = c.position()
            c.setPosition(end - len(text))
            c.setPosition(end, QTextCursor.KeepAnchor)
            c.endEditBlock()
        self.view.blockSignals(False)
        self._later()

    # ---- загрузка
    def load(self, path):
        self.wd = SW.WordDoc(path)
        self.path = path
        self.lbl_doc.setText(os.path.basename(path))
        self.lbl_doc.setToolTip(path)
        self.view.blockSignals(True)
        self.view.build(self.wd)
        self.view.blockSignals(False)
        self.ed_all_date.blockSignals(True)
        self.ed_all_date.clear()
        self.ed_all_date.blockSignals(False)
        self.ed_find.clear()
        self.ed_repl.clear()
        rows = []
        for f in self.wd.fields:
            a, b = self.view.pos_of(f.par, f.start), self.view.pos_of(f.par, f.end)
            if a is None:
                continue
            before = self.wd.text(f.par)[:f.start][-70:]
            ctx = f.meta.get("ctx", "")
            if f.kind in ("cell", "sum") and ctx:
                key = SW.guess_label(ctx)
            elif f.kind == "tail":
                key = SW.guess_label(f.label) or SW.guess_key(f.label)
            else:
                key = SW.guess_key(before) or (SW.guess_label(ctx) if ctx and len(before.strip()) < 3 else "")
            if f.kind == "date":
                ref = re.search(r"договор\w*\s*№[^№]{0,40}\bот\s*$", before.lower())
                own = bool(re.search(r"к договору\s*№", before.lower()))
                key = "contract_date" if (ref and not own) or (not any(r["kind"] == "date" for r in rows) and
                                                               any(n == "Номер договора" and re.match(r"[А-ЯЁA-Z]", t)
                                                                   for n, t, _c in self.wd.dummies)) else ""
            elif f.kind == "blank" and re.search(r"(?<!к )договор(?:ом|а|у)?\s*№\s*$", before.lower()):
                key = "contract_no"
            row = self._new_row(f.label, key, f.kind, [(a, b)], field=f)
            row["table"] = f.meta.get("table", "")
            row["total"] = bool(f.kind == "sum" and SW.TOTAL_RE.search(ctx or ""))
            rows.append(row)
        for name, text, cnt in self.wd.dummies:
            spans = self._find_all(text)
            if spans:
                key = SW.DUMMY_KEYS.get(name, "")
                if key == "contract_no" and not re.match(r"[А-ЯЁA-Z]", text):
                    key = "doc_no"                       # «000–2026» — собственный номер этого документа
                rows.append(self._new_row(f"{name}: «{text}»" + (f" ×{len(spans)}" if len(spans) > 1 else ""),
                                          key, "dummy", spans, dummy=name))
        taken = [(c.selectionStart(), c.selectionEnd()) for r in rows for c in r["cursors"]]
        for m in self._marks():
            spans = [s for s in self._find_all(m.get("text", "")) if not any(a < s[1] and s[0] < b for a, b in taken)]
            if spans:
                title = SW.KEY_TITLES.get(m.get("key"), m.get("label") or "поле")
                rows.append(self._new_row(f"{title}: «{m['text'][:40]}»" + (f" ×{len(spans)}" if len(spans) > 1 else ""),
                                          m.get("key", ""), "mark", spans, mark=m))
                taken += spans
        rows.sort(key=lambda r: (bool(r["current"]), r["cursors"][0].selectionStart()))
        # номер этого документа: первое по тексту поле-номер (заголовок «ДОГОВОР № …», «Счёт № …»)
        nums = [r for r in rows if r["key"] == "doc_no" or (r["kind"] == "dummy" and r["dummy"] == "Номер договора")]
        own = min(nums, key=lambda r: r["cursors"][0].selectionStart()) if nums else None
        for r in rows:
            r["docnum"] = r is own
            if r["key"] == "doc_no" and r is not own and r["kind"] == "dummy":
                r["twin"] = True                         # тот же номер в другом написании («000-2026»)
        self.rows = rows
        self.client_dir = os.path.dirname(path)
        self._build_panel()
        self._apply_card()
        self._paint_marks()
        self.lbl_info.setText(self._home)

    # ---- карточка клиента и номер документа
    def _counter(self):
        return dict((settings_load().get("doc_counters") or {}).get(self._tpl_id()) or {})

    def _set_counter(self, **kw):
        st = settings_load()
        c = st.setdefault("doc_counters", {}).setdefault(self._tpl_id(), {})
        c.update(kw)
        c["ts"] = time.time()
        settings_save(st)

    def _num_key(self):
        return "doc_no:" + self._tpl_id()

    def _apply_card(self, only_empty=True):
        """Подставить данные клиента из карточки в папке и следующий номер документа."""
        self.card = SW.card_load(self.client_dir) if self.client_dir else {}
        data = SW.derive(self.card)
        who = data.get("fio_short") or data.get("fio") or ""
        self.lbl_client.setText(("Клиент: " + who) if who else "Клиент: карточки нет")
        n = 0
        for r in self.rows:
            if r["edit"] is None:
                continue
            val = data.get(r["key"]) if r["key"] and r["key"] != "doc_no" else None
            if r.get("docnum"):
                val = self.card.get(self._num_key()) or (val if r["key"] == "contract_no" else None)
                if not val and self._num_mode() == "auto":
                    cnt = self._counter()
                    val = SW.next_number(cnt.get("last", ""), AI.today().year, cnt.get("reset", True))
            if val and (not r["edit"].text().strip() or r["auto"] or (not only_empty)):
                r["edit"].setText(val)
                r["auto"] = True
                self._write(r, val)
                n += 1
        own = next((r for r in self.rows if r.get("docnum")), None)
        if own is not None and own["edit"] is not None and own["edit"].text().strip():
            for r in self.rows:
                if r.get("twin") and r["edit"] is not None:
                    val = self._twin_text(r, own["edit"].text().strip())
                    r["edit"].setText(val)
                    r["auto"] = True
                    self._write(r, val)
        self._recalc()
        self._count()
        return n

    @staticmethod
    def _twin_text(row, value):
        """Тот же номер, но с тем тире, которое стоит в этом месте шаблона («000-2026» и «000–2026»)."""
        orig = row["orig"][0] if row["orig"] else ""
        dash = "–" if "–" in orig else ("-" if "-" in orig else "")
        return re.sub(r"[–-]", dash, value) if dash else value

    def _num_mode(self):
        return self._counter().get("mode", "auto")

    def _open_card(self):
        if not self.client_dir:
            return
        merged = dict(self.card)
        merged.update({k: v for k, v in self.client_values().items() if k in SW.CARD_KEYS})
        dlg = ClientCardDialog(self.client_dir, self, values=merged)
        if dlg.exec() == QDialog.Accepted:
            n = self._apply_card(only_empty=False)
            self._say(f"Карточка сохранена, подставлено полей: {n}")

    def _pick_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Папка клиента", self.client_dir or self.win.current_dir())
        if not d:
            return
        self.client_dir = d
        n = self._apply_card(only_empty=False)
        self._say(f"Папка клиента: {os.path.basename(d)}. Подставлено полей: {n}" if n else
                  f"Папка клиента: {os.path.basename(d)}. Карточки в ней пока нет — она появится, когда сохраните документ")

    def _recalc(self):
        """«Итого» и «Общая стоимость» — сумма остальных сумм той же таблицы; составные значения."""
        for tot in self.rows:
            if not tot.get("total") or tot["edit"] is None or not (not tot["edit"].text().strip() or tot["auto"]):
                continue
            parts = [r for r in self.rows if r is not tot and r["kind"] == "sum" and not r.get("total")
                     and r.get("table") and r.get("table") == tot.get("table") and r["edit"] is not None]
            nums = [SW.parse_number(r["edit"].text()) for r in parts if r["edit"].text().strip()]
            if not nums and tot["auto"] and tot["edit"].text().strip():
                tot["edit"].clear()                  # слагаемые стёрли — итог тоже пустой
                self._write(tot, "")
                continue
            if not nums or any(x is None for x in nums):
                continue
            kop = sum(w * 100 + f for w, f in nums)
            text = SW.format_number(kop // 100) + (f",{kop % 100:02d}" if kop % 100 else "")
            if tot["edit"].text().strip() != text:
                tot["edit"].setText(text)
                tot["auto"] = True
                self._write(tot, text)
        vals = self.client_values()
        combo = " / ".join(x for x in (vals.get("engine_volume", ""), vals.get("engine_type", "")) if x)
        if combo:
            for r in self.rows:
                if r["key"] == "engine_combo" and r["edit"] is not None and (not r["edit"].text().strip() or r["auto"]) \
                        and r["edit"].text().strip() != combo:
                    r["edit"].setText(combo)
                    r["auto"] = True
                    self._write(r, combo)

    def _build_panel(self):
        holder = QWidget()
        v = QVBoxLayout(holder)
        v.setContentsMargins(0, 0, 8, 0)
        v.setSpacing(2)
        tips = {"date": "ДД.ММ.ГГГГ", "sum": "число — пропись подставится"}
        sep_done = False
        for row in self.rows:
            if row["current"] and not sep_done:
                sep = QLabel("УЖЕ ЗАПОЛНЕНО В ШАБЛОНЕ")
                sep.setObjectName("paneltitle")
                v.addSpacing(6)
                v.addWidget(sep)
                sep_done = True
            top = QHBoxLayout()
            top.setSpacing(4)
            lab = ClickLabel(row["label"])
            lab.setObjectName("hint")
            lab.setCursor(Qt.PointingHandCursor)
            lab.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
            lab.setFixedHeight(17)
            lab.setToolTip(row["label"] + "\nЩелчок — показать это место в документе")
            lab.clicked.connect(lambda r=row: self._jump(r))
            top.addWidget(lab, 1)
            if row.get("docnum"):
                cmb = QComboBox()
                cmb.addItem("номер: авто", "auto")
                cmb.addItem("номер: вручную", "manual")
                cmb.setCurrentIndex(0 if self._num_mode() == "auto" else 1)
                cmb.setFixedHeight(20)
                cmb.setStyleSheet("QComboBox { min-height: 0; padding: 0 4px; font-size: 11px; }")
                cmb.setToolTip("Авто — программа сама ставит следующий номер после последнего сохранённого.\n"
                               "Вручную — номер вписываете вы. Выбор запоминается для этого шаблона.")
                cmb.currentIndexChanged.connect(lambda _i, c=cmb, r=row: self._num_mode_changed(r, c.currentData()))
                top.addWidget(cmb)
                row["num_cmb"] = cmb
            if row["mark"] is not None:
                x = QToolButton()
                x.setObjectName("ghost")
                x.setAutoRaise(True)
                x.setFixedSize(18, 18)
                x.setIcon(draw_icon("close", self.win._icon_color()))
                x.setIconSize(QSize(10, 10))
                x.setToolTip("Убрать это поле из шаблона")
                x.clicked.connect(lambda _=False, r=row: self._drop_mark(r))
                top.addWidget(x)
            v.addLayout(top)
            ed = QLineEdit()
            ed.setMinimumHeight(28)
            ed.setPlaceholderText("первый номер впишите сами — дальше пойдёт сам" if row.get("docnum") else
                                  tips.get(row["kind"], SW.KEY_TITLES.get(row["key"], "")))
            if row["current"]:
                ed.setText(row["current"])
            ed.textEdited.connect(lambda t, r=row: self._typed(r, t))
            row["edit"] = ed
            v.addWidget(ed)
            v.addSpacing(5)
        if not self.rows:
            none = QLabel("Готовых мест для заполнения не нашлось — это уже заполненный документ.\n\n"
                          "Правьте текст прямо в документе слева: выделите и впишите своё.\n\n"
                          "Чтобы в следующий раз заполнялось само: выделите значение (ФИО, VIN, номер), правая кнопка → "
                          "«Сделать полем шаблона».")
            none.setObjectName("hint")
            none.setWordWrap(True)
            v.addWidget(none)
        v.addStretch(1)
        self.sc.setWidget(holder)
        self._count()

    def _num_mode_changed(self, row, mode):
        self._set_counter(mode=mode)
        if row["edit"] is None:
            return
        if mode == "manual" and row["auto"]:
            row["edit"].clear()
            self._typed(row, "")
        elif mode == "auto" and not row["edit"].text().strip():
            cnt = self._counter()
            val = self.card.get(self._num_key()) or SW.next_number(cnt.get("last", ""), AI.today().year, cnt.get("reset", True))
            if val:
                row["edit"].setText(val)
                self._typed(row, val)
                row["auto"] = True

    def _jump(self, row):
        c = QTextCursor(row["cursors"][0])
        self.view.setTextCursor(c)
        self.view.ensureCursorVisible()
        if row["edit"] is not None:
            row["edit"].setFocus()

    def _typed(self, row, text, spread=True):
        row["auto"] = False
        self._write(row, text)
        if spread and row["key"]:
            self._spread_key(row["key"], text, skip=row)
        if row.get("docnum"):
            for r in self.rows:
                if r.get("twin") and r["edit"] is not None and (not r["edit"].text().strip() or r["auto"]):
                    val = self._twin_text(r, text.strip())
                    r["edit"].setText(val)
                    r["auto"] = True
                    self._write(r, val)
        self._recalc()
        self._count()

    def _spread_key(self, key, text, skip=None):
        """То же значение — во все поля с тем же смыслом; из полного ФИО получается «Фамилия И. О.»."""
        for r in self.rows:
            if r is skip or r["edit"] is None:
                continue
            val = None
            if r["key"] == key and key != "doc_no":
                val = text
            elif key == "fio" and r["key"] == "fio_short":
                val = SW.initials(text)
            if val is not None and (not r["edit"].text().strip() or r["auto"]):
                r["edit"].setText(val)
                r["auto"] = True
                self._write(r, val)

    def _spread_date(self, text):
        if text.strip() and SW.parse_date(text) is None:
            return
        for r in self.rows:
            if r["kind"] == "date" and r["edit"] is not None and (not r["edit"].text().strip() or r["auto"]):
                r["edit"].setText(text.strip())
                r["auto"] = True
                self._write(r, text)
        self._count()

    def _count(self):
        done = sum(1 for r in self.rows if r["edit"] is not None and r["edit"].text().strip())
        self.lbl_cnt.setText(f"Поля: заполнено {done} из {len(self.rows)}" if self.rows else "")

    def _paint_marks(self):
        sels = []
        for r in self.rows:
            filled = bool(r["edit"] is not None and r["edit"].text().strip())
            for c in r["cursors"]:
                if c.hasSelection():
                    s = QTextEdit.ExtraSelection()
                    s.cursor = QTextCursor(c)
                    s.format.setBackground(QColor("#d9f2d0" if filled else "#fff1b8"))
                    sels.append(s)
        self.view.setExtraSelections(sels)

    def _replace_all(self):
        a, b = self.ed_find.text(), self.ed_repl.text()
        if not a:
            return
        spans = self._find_all(a)
        if not spans:
            self._say(f"«{a}» в документе не найдено", warn=True)
            return
        self.view.blockSignals(True)
        c = QTextCursor(self.view.document())
        c.beginEditBlock()
        for s, e in reversed(spans):
            fmt = self._fmt_at(s, e)
            c.setPosition(s)
            c.setPosition(e, QTextCursor.KeepAnchor)
            c.insertText(b, fmt)
        c.endEditBlock()
        self.view.blockSignals(False)
        self._later()
        self._say(f"Заменено: {len(spans)}")

    # ---- поля шаблона, которые отметил пользователь
    def _tpl_id(self):
        return os.path.basename(self.path).lower()

    def _marks(self):
        return list((settings_load().get("word_marks") or {}).get(self._tpl_id(), []))

    def _add_mark(self, key):
        c = self.view.textCursor()
        text = c.selectedText()
        if not text.strip():
            return
        label = ""
        if not key:
            label, ok = QInputDialog.getText(self, "Поле шаблона", "Как назвать это поле (например «Город доставки»):")
            label = (label or "").strip()
            if not ok or not label:
                return
        st = settings_load()
        marks = st.setdefault("word_marks", {}).setdefault(self._tpl_id(), [])
        if any(m.get("text") == text for m in marks):
            self._say("Такое поле в этом шаблоне уже есть", warn=True)
            return
        m = {"key": key or "", "label": label, "text": text}
        marks.append(m)
        settings_save(st)
        self.win.cloud_soon()
        taken = [(x.selectionStart(), x.selectionEnd()) for r in self.rows for x in r["cursors"]]
        spans = [s for s in self._find_all(text) if not any(a < s[1] and s[0] < b for a, b in taken)]
        if not spans:
            self._say("Это место уже занято другим полем", warn=True)
            return
        title = SW.KEY_TITLES.get(key, label or "поле")
        row = self._new_row(f"{title}: «{text[:40]}»" + (f" ×{len(spans)}" if len(spans) > 1 else ""),
                            key or "", "mark", spans, mark=m)
        self.rows.append(row)
        self.rows.sort(key=lambda r: (bool(r["current"]), r["cursors"][0].selectionStart()))
        vals = {id(r): (r["edit"].text() if r["edit"] is not None else "") for r in self.rows}
        self._build_panel()
        for r in self.rows:
            if vals.get(id(r)):
                r["edit"].setText(vals[id(r)])
        self._count()
        self._paint_marks()
        self._jump(row)
        self._say(f"Поле «{title}» запомнено для этого шаблона" + (f" — мест в документе: {len(spans)}" if len(spans) > 1 else "")
                  + ". В следующий раз оно появится справа само.")

    def _drop_mark(self, row):
        st = settings_load()
        marks = (st.get("word_marks") or {}).get(self._tpl_id(), [])
        marks[:] = [m for m in marks if m.get("text") != row["mark"].get("text")]
        settings_save(st)
        self._write(row, "")
        self.rows.remove(row)
        vals = {id(r): r["edit"].text() for r in self.rows if r["edit"] is not None}
        self._build_panel()
        for r in self.rows:
            if vals.get(id(r)):
                r["edit"].setText(vals[id(r)])
        self._count()
        self._paint_marks()

    # ---- данные клиента
    def client_values(self):
        out = {}
        for r in self.rows:
            if r["key"] and r["edit"] is not None and r["edit"].text().strip() and r["key"] not in out:
                out[r["key"]] = r["edit"].text().strip()
        return out

    # ---- сохранение
    def save(self):
        if not self.wd:
            return
        edits = self.view.changed_paragraphs()
        if not edits:
            QMessageBox.information(self, "Редактор Word", "В документе пока ничего не изменено.")
            return
        folder = self.client_dir or os.path.dirname(self.path)
        base = os.path.splitext(os.path.basename(self.path))[0]
        vals = self.client_values()
        name = base
        for r in self.rows:
            if r["kind"] == "dummy" and r["edit"] is not None and r["edit"].text().strip():
                name = name.replace(r["orig"][0], r["edit"].text().strip())
        if name == base:
            who = vals.get("fio_short") or vals.get("fio") or ""
            name = f"{base} — {who}" if who else f"{base} (заполнен)"
        out, _ = QFileDialog.getSaveFileName(self, "Сохранить документ Word",
                                             os.path.join(folder, AI.clean_filename(name) + ".docx"),
                                             "Документ Word (*.docx)")
        if not out:
            return
        if not out.lower().endswith(".docx"):
            out += ".docx"
        if os.path.normcase(os.path.abspath(out)) == os.path.normcase(os.path.abspath(self.path)):
            QMessageBox.warning(self, "Редактор Word", "Это имя исходного файла. Выберите другое имя — шаблон должен "
                                                       "остаться чистым для следующих документов.")
            return
        own0 = next((r for r in self.rows if r.get("docnum") and r["edit"] is not None), None)
        uri = cloud_uri()
        if own0 is not None and own0["edit"].text().strip() and uri and (settings_load().get("cloud_parts") or {}).get("counters", True) \
                and not self.card.get(self._num_key()):
            wanted = own0["edit"].text().strip()
            cnt = self._counter()
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                got = CLOUD.claim_number(uri, self._tpl_id(), wanted, auto=bool(own0["auto"]), year=AI.today().year,
                                         reset=cnt.get("reset", True))
            except Exception:
                got = wanted                              # облако недоступно — номер по счётчику этого компьютера
            finally:
                QApplication.restoreOverrideCursor()
            if got and got != wanted:
                own0["edit"].setText(got)
                self._typed(own0, got)
                own0["auto"] = True
                edits = self.view.changed_paragraphs()
                vals = self.client_values()
                self._say(f"Номер {wanted} уже занят на другом компьютере — поставлен {got}")
        try:
            fresh = SW.WordDoc(self.path)
            n = fresh.save(out, edits=edits)
        except PermissionError:
            QMessageBox.warning(self, "Редактор Word", "Не удалось записать файл — он открыт в Word. "
                                                       "Закройте его там и повторите.")
            return
        except Exception as e:
            QMessageBox.critical(self, "Редактор Word", f"Не удалось сохранить:\n{e}")
            return
        # номер документа занят только теперь, когда файл записан
        own = next((r for r in self.rows if r.get("docnum") and r["edit"] is not None), None)
        num = own["edit"].text().strip() if own is not None else ""
        if num:
            cnt = self._counter()
            if SW.number_value(num) >= SW.number_value(cnt.get("last", "")) or not cnt.get("last") \
                    or str(AI.today().year) in num:
                self._set_counter(last=num)
        # карточка клиента — в папку, куда сохранён документ
        out_dir = os.path.dirname(out)
        card = SW.card_load(out_dir)
        card.update({k: v for k, v in vals.items() if k in SW.CARD_KEYS})
        if num:
            card[self._num_key()] = num
        card.pop("fio_short", None)
        saved = SW.card_save(out_dir, card) if card else True
        self.wd = None                              # следующий документ открывается с чистого шаблона
        self.win.cloud_soon()
        self.win.reload_files()
        self.win.ai_mode(False)
        self.win.open_word(out, quiet=True)
        self.win.show_toast(f"✔  Сохранено: {os.path.basename(out)} — изменено абзацев: {n}. "
                            + ("Карточка клиента обновлена" if saved else "Карточку клиента записать не удалось"), 5200)


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

# ======================================================================
#  Акт осмотра автомобиля: оригинал на немецком + перевод, почерк мастера
# ======================================================================

ACT_DIR = os.path.join(LIB_DIR, "act")


def act_kit_path(which: str) -> str:
    return os.path.join(ACT_DIR, ACT.KIT_FILES[which])


def act_kit_ready() -> bool:
    return all(os.path.isfile(act_kit_path(k)) for k in ACT.KIT_FILES)


def act_kit_ensure() -> bool:
    """Если своих бланков нет — положить те, что идут с программой. True — бланки на месте."""
    if act_kit_ready():
        return True
    try:
        import stamp_act_kit
        act_kit_store(stamp_act_kit.BLANKS)
    except Exception:
        pass
    return act_kit_ready()


def act_kit_value():
    """Бланки для облака: {de, ru} в base64 и время изменения. None — бланков нет."""
    if not act_kit_ready():
        return None, 0
    import base64
    val, mt = {}, 0
    for k in ACT.KIT_FILES:
        with open(act_kit_path(k), "rb") as f:
            val[k] = base64.b64encode(f.read()).decode("ascii")
        mt = max(mt, os.path.getmtime(act_kit_path(k)))
    return val, mt


def act_kit_store(val: dict):
    import base64
    os.makedirs(ACT_DIR, exist_ok=True)
    for k in ACT.KIT_FILES:
        if val.get(k):
            with open(act_kit_path(k), "wb") as f:
                f.write(base64.b64decode(val[k]))


def act_masters_load() -> list:
    return [m for m in (settings_load().get("act_masters") or []) if m.get("name")]


def act_masters_save(items: list):
    s = settings_load()
    s["act_masters"] = items
    settings_save(s)


def act_next_number() -> int:
    last = str(((settings_load().get("doc_counters") or {}).get("act") or {}).get("last") or "")
    d = re.sub(r"\D", "", last)
    return int(d) + 1 if d else ACT.FIRST_NUMBER


def act_set_last(n):
    s = settings_load()
    s.setdefault("doc_counters", {}).setdefault("act", {}).update({"last": str(n), "ts": time.time()})
    settings_save(s)


def _strokes_image(strokes, w, h, color, scale=1.0):
    """Штрихи [[(x, y, толщина)…]…] → прозрачная картинка PIL (как шариковая ручка)."""
    W, H = max(4, int(w * scale)), max(4, int(h * scale))
    img = QImage(W, H, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    items = []
    for pts in strokes:
        if not pts:
            continue
        dense = pen_dense_points(pts)
        dense, alpha = pen_natural_ends(dense, pts)
        items.append({"pts": pts, "dense": dense, "alpha": alpha})
    p = QPainter(img)
    p.scale(scale, scale)
    pen_paint_strokes(p, items, color)
    p.end()
    img = img.convertToFormat(QImage.Format_RGBA8888)
    return Image.frombuffer("RGBA", (img.width(), img.height()), bytes(img.constBits()), "raw", "RGBA",
                            img.bytesPerLine(), 1).copy()


def hand_pil(text, glyphs, height_px, seed=0, color=None):
    """Строка почерком мастера → прозрачная картинка (или None, если писать нечего)."""
    strokes, w, h = ACT.hand_layout(text, glyphs, height_px, seed)
    if not strokes:
        return None
    return _strokes_image(strokes, w, h, color or PEN_INKS[0][1])


def sign_pil(strokes_norm, height_px, color=None):
    """Подпись мастера (как он её нарисовал) → прозрачная картинка, обрезанная по штрихам."""
    pts_all = [(p[0], p[1]) for st in strokes_norm or [] for p in st]
    if len(pts_all) < 2:
        return None
    x0, y0 = min(p[0] for p in pts_all), min(p[1] for p in pts_all)
    x1, y1 = max(p[0] for p in pts_all), max(p[1] for p in pts_all)
    k = height_px / max(0.05, (y1 - y0))
    pen = max(1.6, height_px * 0.030)
    pad = pen * 3
    strokes = [[((p[0] - x0) * k + pad, (p[1] - y0) * k + pad, pen) for p in st] for st in strokes_norm if st]
    return _strokes_image(strokes, (x1 - x0) * k + 2 * pad, height_px + 2 * pad, color or PEN_INKS[0][1])


class GlyphPad(QWidget):
    """Клетка, в которой мастер пишет знак (или подпись) своей рукой. Правая кнопка — стереть."""
    changed = Signal()

    def __init__(self, hint="", w=58, h=72, parent=None):
        super().__init__(parent)
        self.setFixedSize(w, h)
        self.hint = hint
        self.strokes = []            # [[(x, y)…]…] в долях высоты клетки
        self._cur = None
        self.setCursor(Qt.CrossCursor)
        self.setToolTip((f"Напишите «{hint}» так, как пишете от руки. " if len(hint) == 1 else "")
                        + "Правая кнопка мыши — стереть")

    def set_strokes(self, strokes):
        self.strokes = [[(float(p[0]), float(p[1])) for p in st] for st in (strokes or []) if st]
        self.update()

    def data(self):
        return [[[round(x, 3), round(y, 3)] for x, y in st] for st in self.strokes if len(st) >= 1]

    def clear(self):
        self.strokes, self._cur = [], None
        self.update()
        self.changed.emit()

    def mousePressEvent(self, e):
        if e.button() == Qt.RightButton:
            self.clear()
            return
        if e.button() == Qt.LeftButton:
            H = self.height()
            self._cur = [(e.position().x() / H, e.position().y() / H)]
            self.strokes.append(self._cur)
            self.update()

    def mouseMoveEvent(self, e):
        if self._cur is None:
            return
        H = self.height()
        x, y = e.position().x() / H, e.position().y() / H
        lx, ly = self._cur[-1]
        if abs(x - lx) * H + abs(y - ly) * H >= 1.5:
            self._cur.append((x, y))
            self.update()

    def mouseReleaseEvent(self, e):
        if self._cur is not None:
            self._cur = None
            self.changed.emit()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        W, H = self.width(), self.height()
        p.fillRect(self.rect(), QColor("#ffffff"))
        p.setPen(QPen(QColor("#e4dfd0"), 1, Qt.DashLine))
        p.drawLine(0, int(H * 0.2), W, int(H * 0.2))
        p.drawLine(0, int(H * 0.82), W, int(H * 0.82))
        if not self.strokes and self.hint:
            f = p.font()
            f.setPixelSize(int(H * 0.5) if len(self.hint) == 1 else 13)
            p.setFont(f)
            p.setPen(QColor("#d9d4c6"))
            p.drawText(self.rect(), Qt.AlignCenter, self.hint)
        pen = max(1.8, H * 0.036)
        items = [{"pts": [(x * H, y * H, pen) for x, y in st]} for st in self.strokes if st]
        pen_paint_strokes(p, items, PEN_INKS[0][1])
        p.setPen(QPen(QColor("#cfc8b4"), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRect(0, 0, W - 1, H - 1)
        p.end()


class ActMasterDialog(QDialog):
    """Профиль мастера: имя, его почерк (цифры и знаки пишет сам), подпись и печать."""

    def __init__(self, master=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Мастер")
        self.resize(820, 690)
        self.setMinimumSize(800, 670)
        m = dict(master or {})
        root = QVBoxLayout(self)
        root.setSpacing(10)
        row = QHBoxLayout()
        row.addWidget(QLabel("Имя и фамилия:"))
        self.ed_name = QLineEdit(m.get("name", ""))
        self.ed_name.setPlaceholderText("как в акте, например Paul Weber")
        row.addWidget(self.ed_name, 1)
        root.addLayout(row)
        hint = QLabel("Мастер пишет знаки <b>сам, своей рукой</b> — мышью или пером. Этими знаками программа будет "
                      "вписывать его замеры в схему. Ошиблись — правая кнопка мыши по клетке.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        root.addWidget(hint)

        self.pads = {}
        for title, chars in (("Цифры и знаки для замеров (обязательно)", ACT.GLYPHS_NEED),
                             ("Буквы повреждений, запятая, точка (по желанию)", ACT.GLYPHS_MORE)):
            box = QGroupBox(title)
            g = QGridLayout(box)
            g.setSpacing(6)
            for i, ch in enumerate(chars):
                pad = GlyphPad(ch, 48, 60)
                pad.set_strokes((m.get("glyphs") or {}).get(ch))
                pad.changed.connect(self._preview)
                self.pads[ch] = pad
                g.addWidget(pad, 0, i)
            g.setColumnStretch(len(chars), 1)
            root.addWidget(box)

        row = QHBoxLayout()
        row.addWidget(QLabel("Как это выглядит:"))
        self.lbl_prev = QLabel()
        self.lbl_prev.setMinimumHeight(46)
        self.lbl_prev.setStyleSheet("background:#ffffff; border:1px solid #ddd5c0; border-radius:6px;")
        row.addWidget(self.lbl_prev, 1)
        root.addLayout(row)

        box = QGroupBox("Подпись и печать мастера")
        hl = QHBoxLayout(box)
        hl.setSpacing(12)
        self.pad_sign = GlyphPad("подпись", 330, 96)
        self.pad_sign.set_strokes(m.get("sign"))
        hl.addWidget(self.pad_sign)
        col = QVBoxLayout()
        b = QPushButton("Стереть подпись")
        b.clicked.connect(self.pad_sign.clear)
        col.addWidget(b)
        col.addWidget(QLabel("Печать (из «Мои печати»):"))
        self.cmb_stamp = QComboBox()
        self.cmb_stamp.addItem("— без печати —", "")
        for s in lib_load():
            self.cmb_stamp.addItem(s.get("name") or os.path.basename(s["file"]), os.path.basename(s["file"]))
        i = self.cmb_stamp.findData(m.get("stamp", ""))
        self.cmb_stamp.setCurrentIndex(max(0, i))
        col.addWidget(self.cmb_stamp)
        col.addStretch(1)
        hl.addLayout(col, 1)
        root.addWidget(box)

        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Save).setText("Сохранить")
        bb.button(QDialogButtonBox.Cancel).setText("Отмена")
        bb.accepted.connect(self._save)
        bb.rejected.connect(self.reject)
        root.addWidget(bb)
        self._preview()

    def glyphs(self):
        return {ch: pad.data() for ch, pad in self.pads.items() if pad.data()}

    def _preview(self):
        g = self.glyphs()
        text = "118 97 20% -/-"
        text = "".join(ch for ch in text if ch == " " or ch in g)
        im = hand_pil(text, g, 34, seed=7) if text.strip() else None
        if im is None:
            self.lbl_prev.setPixmap(QPixmap())
            self.lbl_prev.setText("  напишите цифры — здесь появится пример")
            return
        buf = io.BytesIO()
        im.save(buf, "PNG")
        pm = QPixmap()
        pm.loadFromData(buf.getvalue(), "PNG")
        self.lbl_prev.setPixmap(pm)

    def master(self):
        return {"name": self.ed_name.text().strip(), "glyphs": self.glyphs(), "sign": self.pad_sign.data(),
                "stamp": self.cmb_stamp.currentData() or ""}

    def _save(self):
        m = self.master()
        if not m["name"]:
            QMessageBox.information(self, "Мастер", "Впишите имя и фамилию мастера.")
            return
        miss = [ch for ch in ACT.GLYPHS_NEED if ch not in m["glyphs"]]
        if miss:
            QMessageBox.information(self, "Мастер", "Не написаны знаки: " + "  ".join(miss) +
                                    "\nБез них замеры в схему не вписать.")
            return
        self.accept()


class LkpBoard(QWidget):
    """Схема автомобиля с окошками: замеры вписываются прямо в них."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(480, 250)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.kind = "car"
        self._pm = None
        self.edits = {}
        self.set_kind("car")

    def set_kind(self, kind):
        old = self.values()
        self.kind = kind if kind in ACT.LKP else "car"
        pm = QPixmap()
        pm.loadFromData(ACT.diagram_png(self.kind), "PNG")
        self._pm = pm
        for e in self.edits.values():
            e.deleteLater()
        self.edits = {}
        for name, *_ in ACT.lkp_places((0, 0, 1, 1), self.kind):
            e = QLineEdit(self)
            e.setAlignment(Qt.AlignCenter)
            e.setFrame(False)
            e.setMaxLength(9 if name.startswith("b") else 3)
            e.setStyleSheet("QLineEdit { background: rgba(255,255,255,0); color: #1b36a8; border: none; "
                            "padding: 0; font-weight: 600; } QLineEdit:focus { background: #fff6dc; }")
            e.setToolTip("Толщина ЛКП в микронах, код повреждения или «-/-»" if name.startswith("b")
                         else "Износ, %  (только число)")
            if old.get(name):
                e.setText(old[name])
            e.show()
            self.edits[name] = e
        self._place()
        self.update()

    def _area(self):
        if self._pm is None or self._pm.isNull():
            return QRectF(self.rect())
        a = self._pm.width() / self._pm.height()
        w = min(self.width(), self.height() * a)
        h = w / a
        return QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h)

    def _place(self):
        r = self._area()
        order = []
        for name, x0, y0, x1, y1 in ACT.lkp_places((r.x(), r.y(), r.x() + r.width(), r.y() + r.height()), self.kind):
            e = self.edits.get(name)
            if e is None:
                continue
            if name.startswith("w"):                     # в круге уже напечатан «%» — число встаёт слева от него
                w, h = x1 - x0, y1 - y0
                e.setGeometry(int(x0 + w * 0.08), int(y0 + h * 0.30), max(14, int(w * 0.46)), max(12, int(h * 0.40)))
            else:
                e.setGeometry(int(x0 + 2), int(y0 + 2), max(20, int(x1 - x0 - 4)), max(12, int(y1 - y0 - 4)))
            f = e.font()
            f.setPixelSize(max(8, int((y1 - y0) * (0.27 if name.startswith("w") else 0.55))))
            e.setFont(f)
            order.append((round(y0 / 30), x0, e))
        order.sort(key=lambda t: (t[0], t[1]))
        for a, b in zip(order, order[1:]):
            QWidget.setTabOrder(a[2], b[2])

    def resizeEvent(self, _):
        self._place()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        p.fillRect(self.rect(), QColor("#ffffff"))
        if self._pm is not None and not self._pm.isNull():
            p.drawPixmap(self._area(), self._pm, QRectF(self._pm.rect()))
        p.end()

    def values(self):
        return {k: e.text().strip() for k, e in self.edits.items() if e.text().strip()}

    def set_values(self, vals):
        for k, e in self.edits.items():
            e.setText(str((vals or {}).get(k, "")))

    def fill_empty(self, text="-/-"):
        for k, e in self.edits.items():
            if k.startswith("b") and not e.text().strip():
                e.setText(text)


class ActPage(QDialog):
    """Акт осмотра внутри главного окна: слева данные автомобиля, справа схема ЛКП и текст перевода."""

    PAIRS = [("color", "Цвет · Farbe"), ("drive", "Привод · Antrieb"), ("gear", "Коробка · Getriebe"),
             ("body", "Кузов · Karosserietyp"), ("fuel", "Топливо · Kraftstoff")]

    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.setWindowFlags(Qt.Widget)
        self.setObjectName("aipage")
        self._auto = {}                 # какие переводы подставила программа (их можно заменять)
        ACT.EXTRA.clear()
        ACT.EXTRA.update({k: list(v) for k, v in (settings_load().get("act_dict") or {}).items()})
        self._sections = []
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 10, 16, 10)
        root.setSpacing(8)

        head = QHBoxLayout()
        head.setSpacing(10)
        b_back = QPushButton(" К документу")
        b_back.setIcon(draw_icon("back", win._icon_color()))
        b_back.setIconSize(QSize(16, 16))
        b_back.setCursor(Qt.PointingHandCursor)
        b_back.setToolTip("Вернуться к странице документа (Esc). Введённое здесь останется.")
        b_back.clicked.connect(lambda: win.ai_mode(False))
        win._themed_buttons.append((b_back, "back", False))
        head.addWidget(b_back)
        ttl = QLabel("АКТ ОСМОТРА")
        ttl.setObjectName("paneltitle")
        head.addWidget(ttl)
        self.lbl_kit = QLabel("")
        self.lbl_kit.setObjectName("hint")
        head.addWidget(self.lbl_kit, 1)
        self.btn_kit = QPushButton("Бланки…")
        self.btn_kit.setToolTip("Бланки акта уже в программе. Здесь их можно заменить своими: "
                                "оригинал на немецком и перевод на русском (.docx)")
        self.btn_kit.clicked.connect(self.load_kit)
        head.addWidget(self.btn_kit)
        self.btn_ai = QPushButton(" Перевести ИИ")
        self.btn_ai.setToolTip("Перевести через ИИ то, чего нет в словаре программы: значения полей и комментарий")
        self.btn_ai.clicked.connect(self.translate_ai)
        head.addWidget(self.btn_ai)
        self.btn_make = QPushButton(" Создать акт")
        self.btn_make.setObjectName("primary")
        self.btn_make.setMinimumHeight(34)
        self.btn_make.setToolTip("Заполнить оригинал и перевод, вписать замеры почерком мастера и открыть оригинал — "
                                 "дальше подпись, печать и сохранение как обычно")
        self.btn_make.clicked.connect(self.make)
        head.addWidget(self.btn_make)
        root.addLayout(head)

        split = QSplitter(Qt.Horizontal)
        split.setChildrenCollapsible(False)

        # ---------------- слева: данные
        form_w = QWidget()
        fl = QVBoxLayout(form_w)
        fl.setContentsMargins(0, 0, 16, 0)
        fl.setSpacing(8)

        box = QGroupBox("Акт")
        f = QFormLayout(box)
        f.setSpacing(6)
        row = QHBoxLayout()
        self.ed_number = QLineEdit(str(act_next_number()))
        self.ed_number.setToolTip("Номер акта. Подставляется следующий по общему счётчику; можно исправить")
        self.ed_number.setMaximumWidth(110)
        row.addWidget(self.ed_number)
        row.addWidget(QLabel("Дата:"))
        self.ed_date = QLineEdit(AI.today().strftime("%d.%m.%Y"))
        self.ed_date.setMaximumWidth(120)
        row.addWidget(self.ed_date)
        row.addStretch(1)
        f.addRow("Номер:", row)
        row = QHBoxLayout()
        self.cmb_master = QComboBox()
        row.addWidget(self.cmb_master, 1)
        for text, tip, slot in (("Добавить", "Новый мастер: имя, почерк, подпись, печать", self._master_add),
                                ("Изменить", "Изменить выбранного мастера", self._master_edit),
                                ("Удалить", "Убрать мастера из списка", self._master_del)):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            row.addWidget(b)
        f.addRow("Мастер:", row)
        fl.addWidget(box)

        box = QGroupBox("Автомобиль")
        f = QFormLayout(box)
        f.setSpacing(6)
        self.ed = {}

        def line(key, ph="", w=None):
            e = QLineEdit()
            e.setPlaceholderText(ph)
            if w:
                e.setMaximumWidth(w)
            self.ed[key] = e
            return e

        row = QHBoxLayout()
        row.addWidget(line("brand", "Marke — Kia"), 1)
        row.addWidget(line("model", "Model — Sportage"), 1)
        row.addWidget(line("year", "год", 70))
        f.addRow("Марка, модель, год:", row)
        row = QHBoxLayout()
        for key, cap, val in (("seats", "мест", "5"), ("doors", "дверей", "5"), ("owners", "владельцев", "1")):
            row.addWidget(QLabel(cap))
            e = line(key, "", 48)
            e.setText(val)
            row.addWidget(e)
        row.addStretch(1)
        f.addRow("Количество:", row)
        row = QHBoxLayout()
        row.addWidget(line("mileage", "53997", 110))
        row.addWidget(QLabel("км"))
        row.addStretch(1)
        f.addRow("Пробег:", row)
        row = QHBoxLayout()
        e = line("vin", "17 знаков")
        fnt = QFont("Consolas")
        fnt.setStyleHint(QFont.Monospace)
        e.setFont(fnt)
        e.setMaxLength(24)
        e.textEdited.connect(self._vin_edited)
        row.addWidget(e, 1)
        self.lbl_vin = QLabel("0 / 17")
        self.lbl_vin.setObjectName("hint")
        row.addWidget(self.lbl_vin)
        f.addRow("VIN:", row)
        row = QHBoxLayout()
        row.addWidget(line("liters", "1.6", 60))
        row.addWidget(QLabel("л"))
        row.addWidget(line("ccm", "1598", 80))
        row.addWidget(QLabel("см³"))
        row.addSpacing(12)
        row.addWidget(QLabel("мощность"))
        row.addWidget(line("hp", "265", 70))
        row.addWidget(QLabel("л. с."))
        row.addStretch(1)
        f.addRow("Двигатель:", row)
        fl.addWidget(box)

        box = QGroupBox("Значения с переводом")
        g = QGridLayout(box)
        g.setHorizontalSpacing(8)
        g.setVerticalSpacing(6)
        row = QHBoxLayout()
        self.rb_de = QRadioButton("Ввожу по-немецки")
        self.rb_ru = QRadioButton("Ввожу по-русски")
        self.rb_ru.setChecked(settings_load().get("act_input", "ru") == "ru")
        self.rb_de.setChecked(not self.rb_ru.isChecked())
        row.addWidget(self.rb_de)
        row.addWidget(self.rb_ru)
        row.addStretch(1)
        g.addLayout(row, 0, 0, 1, 3)
        g.addWidget(QLabel("в оригинал (нем.)"), 1, 1)
        g.addWidget(QLabel("в перевод (рус.)"), 1, 2)
        self.pair = {}
        for n, (key, cap) in enumerate(self.PAIRS):
            g.addWidget(QLabel(cap + ":"), n + 2, 0)
            cd, cr = QComboBox(), QComboBox()
            for c, col in ((cd, 0), (cr, 1)):
                c.setEditable(True)
                c.setInsertPolicy(QComboBox.NoInsert)
                c.addItem("")
                c.addItems(ACT.variants(key, col))
                c.setCurrentIndex(0)
            cd.editTextChanged.connect(lambda t, k=key: self._pair_changed(k, "de"))
            cr.editTextChanged.connect(lambda t, k=key: self._pair_changed(k, "ru"))
            g.addWidget(cd, n + 2, 1)
            g.addWidget(cr, n + 2, 2)
            self.pair[key] = (cd, cr)
        g.setColumnStretch(1, 1)
        g.setColumnStretch(2, 1)
        fl.addWidget(box)

        box = QGroupBox("Резина на момент осмотра")
        g = QGridLayout(box)
        g.setHorizontalSpacing(8)
        g.setVerticalSpacing(4)
        self.tire = {}
        for n, (key, cap) in enumerate((("summer", "Лето · Sommer"), ("winter", "Зима · Winter"),
                                        ("all", "Всесезонная · Ganzjahresreifen"))):
            chk = QCheckBox(cap)
            ed = QLineEdit()
            ed.setPlaceholderText("марка — если нужно указать")
            g.addWidget(chk, n, 0)
            g.addWidget(ed, n, 1)
            self.tire[key] = (chk, ed)
        g.setColumnStretch(1, 1)
        fl.addWidget(box)

        box = QGroupBox("Комментарий (недостатки пишутся сюда)")
        v = QVBoxLayout(box)
        v.setSpacing(4)
        self.lbl_cru = QLabel("по-русски — для перевода ИИ:")
        self.lbl_cru.setObjectName("hint")
        v.addWidget(self.lbl_cru)
        self.txt_cru = QTextEdit()
        self.txt_cru.setAcceptRichText(False)
        self.txt_cru.setFixedHeight(54)
        v.addWidget(self.txt_cru)
        lb = QLabel("в оригинал, по-немецки (Kommentare):")
        lb.setObjectName("hint")
        v.addWidget(lb)
        self.txt_cde = QTextEdit()
        self.txt_cde.setAcceptRichText(False)
        self.txt_cde.setFixedHeight(54)
        self.txt_cde.setPlainText(ACT.DEFAULT_COMMENT_DE)
        v.addWidget(self.txt_cde)
        row = QHBoxLayout()
        row.addWidget(QLabel("Besonderheiten beim Start:"))
        self.ed_start = QLineEdit("-")
        row.addWidget(self.ed_start, 1)
        v.addLayout(row)
        fl.addWidget(box)
        fl.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(form_w)
        scroll.setMinimumWidth(560)
        split.addWidget(scroll)

        # ---------------- справа: схема и перевод
        self.tabs = QTabWidget()
        lk = QWidget()
        ll = QVBoxLayout(lk)
        ll.setContentsMargins(8, 8, 8, 8)
        ll.setSpacing(8)
        row = QHBoxLayout()
        row.addWidget(QLabel("Кузов на схеме:"))
        self.cmb_kind = QComboBox()
        for k, t in ACT.KIND_TITLES:
            self.cmb_kind.addItem(t, k)
        row.addWidget(self.cmb_kind)
        b = QPushButton("Прочерк в пустые окошки")
        b.setToolTip("Вписать «-/-» во все окошки, где замера нет")
        b.clicked.connect(lambda: self.board.fill_empty())
        row.addWidget(b)
        b = QPushButton("Очистить")
        b.clicked.connect(lambda: self.board.set_values({}))
        row.addWidget(b)
        row.addStretch(1)
        ll.addLayout(row)
        self.board = LkpBoard()
        ll.addWidget(self.board, 1)
        note = QLabel("Впишите замеры в окошки (Tab — следующее). В акт они лягут почерком выбранного мастера; "
                      "в колёсах пишется только число — знак «%» уже напечатан.")
        note.setObjectName("hint")
        note.setWordWrap(True)
        ll.addWidget(note)
        self.tabs.addTab(lk, "Схема ЛКП")

        self.tr_host = QWidget()
        self.tr_lay = QVBoxLayout(self.tr_host)
        self.tr_lay.setContentsMargins(8, 8, 8, 8)
        self.tr_lay.setSpacing(6)
        sc2 = QScrollArea()
        sc2.setWidgetResizable(True)
        sc2.setFrameShape(QFrame.NoFrame)
        sc2.setWidget(self.tr_host)
        self.tabs.addTab(sc2, "Текст перевода")
        split.addWidget(self.tabs)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([580, 700])
        root.addWidget(split, 1)

        self.cmb_kind.currentIndexChanged.connect(lambda _: self.board.set_kind(self.cmb_kind.currentData()))
        self.rb_ru.toggled.connect(self._mode_changed)
        self._fill_masters(settings_load().get("act_last_master"))
        self._mode_changed()
        self.refresh()

    # ---------------------------------------------------------- состояние
    def refresh(self):
        """Вызывается при каждом показе страницы: бланки, счётчик, список мастеров."""
        ready = act_kit_ready()
        self.lbl_kit.setText("" if ready else "Бланки не загружены — нажмите «Бланки…»")
        self.btn_make.setEnabled(True)
        cur = self.cmb_master.currentText()
        self._fill_masters(cur)
        self._dict_refresh()
        try:
            if int(re.sub(r"\D", "", self.ed_number.text()) or 0) < act_next_number():
                self.ed_number.setText(str(act_next_number()))
        except Exception:
            pass
        if ready and not self._sections:
            self._load_sections()

    def _load_sections(self):
        while self.tr_lay.count():
            it = self.tr_lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        self._sections = []
        try:
            secs = ACT.ru_sections(act_kit_path("ru"))
        except Exception:
            secs = []
        hint = QLabel("Текст русского акта по разделам. Меняйте, если автомобиль не в идеальном состоянии; "
                      "то, что не тронуто, останется как в бланке.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        self.tr_lay.addWidget(hint)
        last = None
        for s in secs:
            if s["title"] != last:
                lb = QLabel(s["title"])
                lb.setObjectName("paneltitle")
                self.tr_lay.addWidget(lb)
                last = s["title"]
            te = QTextEdit()
            te.setAcceptRichText(False)
            te.setPlainText(s["text"])
            te.setFixedHeight(max(52, min(150, 24 + 19 * (len(s["text"]) // 78 + 1))))
            self.tr_lay.addWidget(te)
            self._sections.append((s["idx"], s["text"], te))
        b = QPushButton("Вернуть текст как в бланке")
        b.clicked.connect(lambda: [te.setPlainText(orig) for _i, orig, te in self._sections])
        self.tr_lay.addWidget(b, 0, Qt.AlignLeft)
        self.tr_lay.addStretch(1)

    def _mode_changed(self, *_):
        ru = self.rb_ru.isChecked()
        self.txt_cru.setVisible(ru)
        self.lbl_cru.setVisible(ru)
        s = settings_load()
        if s.get("act_input") != ("ru" if ru else "de"):
            s["act_input"] = "ru" if ru else "de"
            settings_save(s)

    def _dict_refresh(self):
        """Словарь мог пополниться (здесь или на другом компьютере) — обновить списки, не трогая введённое."""
        ACT.EXTRA.clear()
        ACT.EXTRA.update({k: list(v) for k, v in (settings_load().get("act_dict") or {}).items()})
        self._pair_busy = True
        try:
            for key, (cd, cr) in self.pair.items():
                for c, col in ((cd, 0), (cr, 1)):
                    want = [""] + ACT.variants(key, col)
                    if [c.itemText(i) for i in range(c.count())] != want:
                        text = c.currentText()
                        c.clear()
                        c.addItems(want)
                        c.setEditText(text)
        finally:
            self._pair_busy = False

    def _dict_learn(self, d):
        """Новые пары значений (вписали сами или перевёл ИИ) запоминаются для следующих актов."""
        added = False
        for key, _cap in self.PAIRS:
            added = ACT.learn(key, d.get(key + "_de"), d.get(key + "_ru")) or added
        if added:
            s = settings_load()
            s["act_dict"] = {k: list(v) for k, v in ACT.EXTRA.items()}
            settings_save(s)
            self._dict_refresh()

    def _vin_edited(self, text):
        v = ACT.clean_vin(text)
        e = self.ed["vin"]
        if v != text:
            pos = e.cursorPosition()
            e.setText(v)
            e.setCursorPosition(min(pos, len(v)))
        self.lbl_vin.setText(f"{len(v)} / 17")
        self.lbl_vin.setToolTip(ACT.vin_problem(v))

    def _pair_changed(self, key, side):
        """Ввели значение на одном языке — второе подставляется по словарю."""
        if getattr(self, "_pair_busy", False):
            return
        cd, cr = self.pair[key]
        src, dst = (cd, cr) if side == "de" else (cr, cd)
        other = "ru" if side == "de" else "de"
        self._auto.pop((key, side), None)                       # это значение ввёл человек
        tr = ACT.translate(key, src.currentText(), other)
        if tr is None:
            if self._auto.get((key, other)):                    # старый автоперевод больше не подходит
                self._set_pair(dst, "")
                self._auto.pop((key, other), None)
            return
        if not dst.currentText().strip() or self._auto.get((key, other)) or not src.currentText().strip():
            self._set_pair(dst, tr)
            self._auto[(key, other)] = True

    def _set_pair(self, combo, text):
        self._pair_busy = True
        try:
            combo.setEditText(text)
        finally:
            self._pair_busy = False

    # ---------------------------------------------------------- мастера
    def _fill_masters(self, pick=None):
        self.cmb_master.blockSignals(True)
        self.cmb_master.clear()
        for m in act_masters_load():
            self.cmb_master.addItem(m["name"])
        i = self.cmb_master.findText(pick) if pick else -1
        if self.cmb_master.count():
            self.cmb_master.setCurrentIndex(max(0, i))
        self.cmb_master.blockSignals(False)

    def master(self):
        name = self.cmb_master.currentText()
        return next((m for m in act_masters_load() if m["name"] == name), None)

    def _master_add(self):
        dlg = ActMasterDialog(None, self)
        if dlg.exec() == QDialog.Accepted:
            m = dlg.master()
            items = [x for x in act_masters_load() if x["name"] != m["name"]] + [m]
            act_masters_save(items)
            self._fill_masters(m["name"])

    def _master_edit(self):
        cur = self.master()
        if cur is None:
            self._master_add()
            return
        dlg = ActMasterDialog(cur, self)
        if dlg.exec() == QDialog.Accepted:
            m = dlg.master()
            items = [m if x["name"] == cur["name"] else x for x in act_masters_load() if x["name"] != m["name"] or x["name"] == cur["name"]]
            act_masters_save(items)
            self._fill_masters(m["name"])

    def _master_del(self):
        cur = self.master()
        if cur is None:
            return
        if QMessageBox.question(self, "Мастер", f"Убрать мастера «{cur['name']}» из списка?\n"
                                "Его почерк и подпись удалятся из программы.") != QMessageBox.Yes:
            return
        act_masters_save([x for x in act_masters_load() if x["name"] != cur["name"]])
        self._fill_masters()

    # ---------------------------------------------------------- бланки
    def load_kit(self):
        QMessageBox.information(self, "Бланки акта",
                                "Бланки акта уже есть в программе. Чтобы заменить их своими, выберите два файла Word:\n"
                                "1) оригинал акта на немецком (INSPEKTIONSBERICHT),\n"
                                "2) перевод акта на русском.\n\n"
                                "Подойдёт любой уже заполненный акт — программа заменит в нём данные.")
        de, _ = QFileDialog.getOpenFileName(self, "1 из 2 — оригинал акта на немецком", self.win.current_dir(),
                                            "Документ Word (*.docx)")
        if not de:
            return
        ru, _ = QFileDialog.getOpenFileName(self, "2 из 2 — перевод акта на русском", os.path.dirname(de),
                                            "Документ Word (*.docx)")
        if not ru:
            return
        miss = ACT.check_templates(de, ru)
        if miss:
            QMessageBox.warning(self, "Бланки акта", "Эти файлы не похожи на бланки акта. Не найдено:\n• " +
                                "\n• ".join(miss))
            return
        try:
            os.makedirs(ACT_DIR, exist_ok=True)
            import shutil
            shutil.copyfile(de, act_kit_path("de"))
            shutil.copyfile(ru, act_kit_path("ru"))
        except Exception as e:
            QMessageBox.critical(self, "Бланки акта", f"Не удалось сохранить бланки:\n{e}")
            return
        self._sections = []
        self.refresh()
        self.win._act_btn_state()
        self.win.cloud_soon()
        self.win.show_toast("✔  Бланки акта загружены")

    # ---------------------------------------------------------- данные формы
    def form_data(self):
        d = {k: e.text().strip() for k, e in self.ed.items()}
        d["number"] = self.ed_number.text().strip()
        d["date"] = self.ed_date.text().strip()
        d["master"] = self.cmb_master.currentText().strip()
        d["kind"] = self.cmb_kind.currentData()
        for key, _cap in self.PAIRS:
            cd, cr = self.pair[key]
            d[key + "_de"], d[key + "_ru"] = cd.currentText().strip(), cr.currentText().strip()
        d["tires"] = {k: {"on": chk.isChecked(), "brand": ed.text().strip()} for k, (chk, ed) in self.tire.items()}
        d["comment_de"] = self.txt_cde.toPlainText().strip()
        d["comment_ru"] = self.txt_cru.toPlainText().strip()
        d["start_de"] = self.ed_start.text().strip() or "-"
        d["lkp"] = self.board.values()
        return d

    def problems(self, d):
        """Что мешает создать акт: (ошибки, предупреждения)."""
        err, warn = [], []
        if not act_kit_ready():
            err.append("не загружены бланки — кнопка «Бланки…»")
        m = self.master()
        if m is None:
            err.append("не выбран мастер — добавьте его кнопкой «Добавить»")
        if not re.sub(r"\D", "", d["number"]):
            err.append("не указан номер акта")
        if not re.match(r"^\d{2}\.\d{2}\.\d{4}$", d["date"]):
            err.append("дата нужна в виде ДД.ММ.ГГГГ")
        for key, cap in (("brand", "марка"), ("model", "модель"), ("year", "год выпуска")):
            if not d.get(key):
                err.append("не заполнено: " + cap)
        v = ACT.vin_problem(d.get("vin"))
        if v:
            warn.append(v)
        for key, cap in self.PAIRS:
            if d[key + "_de"] and not d[key + "_ru"]:
                warn.append(f"нет русского значения: {cap.split(' · ')[0]}")
            if d[key + "_ru"] and not d[key + "_de"]:
                err.append(f"нет немецкого значения: {cap.split(' · ')[0]} — впишите или нажмите «Перевести ИИ»")
            if not d[key + "_de"] and not d[key + "_ru"]:
                warn.append(f"не заполнено: {cap.split(' · ')[0]}")
        if d["comment_ru"] and not d["comment_de"]:
            err.append("комментарий не переведён на немецкий — нажмите «Перевести ИИ»")
        if m is not None:
            miss = ACT.glyphs_missing("".join(d["lkp"].values()), m.get("glyphs") or {})
            if miss:
                err.append("в почерке мастера нет знаков: " + "  ".join(miss) +
                           " — допишите их («Изменить») или уберите из замеров")
        if not d["lkp"]:
            warn.append("схема ЛКП пустая")
        return err, warn

    # ---------------------------------------------------------- перевод ИИ
    def translate_ai(self):
        d = self.form_data()
        jobs = []                                    # (язык, текст, куда положить)
        for key, _cap in self.PAIRS:
            cd, cr = self.pair[key]
            if d[key + "_ru"] and not d[key + "_de"]:
                jobs.append(("de", d[key + "_ru"], lambda t, c=cd: self._set_pair(c, t)))
            elif d[key + "_de"] and not d[key + "_ru"]:
                jobs.append(("ru", d[key + "_de"], lambda t, c=cr: self._set_pair(c, t)))
        if self.rb_ru.isChecked() and d["comment_ru"]:
            jobs.append(("de", d["comment_ru"], lambda t: self.txt_cde.setPlainText(t)))
        if not jobs:
            self.win.show_toast("Переводить нечего: всё уже заполнено на обоих языках")
            return
        if not self.win._ai_ready():
            return

        def work(status, cancelled):
            out = {}
            for lang in ("de", "ru"):
                texts = [j[1] for j in jobs if j[0] == lang]
                if texts:
                    out[lang] = ACT.ai_translate(texts, lang, AI.chat, status, cancelled)
            return out

        def done(res):
            it = {"de": iter(res.get("de") or []), "ru": iter(res.get("ru") or [])}
            n = 0
            for lang, _text, put in jobs:
                t = next(it[lang], None)
                if t:
                    put(t)
                    n += 1
            self.win.show_toast(f"✔  Переведено: {n}. Проверьте перевод перед созданием акта", 4200)

        self.win._ai_run("ИИ переводит значения акта", work, done)

    # ---------------------------------------------------------- создание акта
    def make(self):
        d = self.form_data()
        err, warn = self.problems(d)
        if err:
            QMessageBox.information(self, "Акт осмотра", "Сначала поправьте:\n• " + "\n• ".join(err))
            return
        if warn:
            if QMessageBox.question(self, "Акт осмотра", "Обратите внимание:\n• " + "\n• ".join(warn) +
                                    "\n\nСоздать акт всё равно?") != QMessageBox.Yes:
                return
        m = self.master()
        folder = self.win.current_dir()
        if not folder or not os.path.isdir(folder):
            folder = QFileDialog.getExistingDirectory(self, "Куда сохранить акт")
            if not folder:
                return
        # номер: общий счётчик в облаке, чтобы у мастеров разных смен номера не совпали
        wanted = re.sub(r"\D", "", d["number"])
        got = wanted
        uri = cloud_uri()
        if uri:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                got = re.sub(r"\D", "", str(CLOUD.claim_number(uri, "act", wanted, auto=True, year=None, reset=False))) or wanted
            except Exception:
                got = wanted
            finally:
                QApplication.restoreOverrideCursor()
        if got != wanted:
            QMessageBox.information(self, "Акт осмотра", f"Номер {wanted} уже занят другим мастером.\n"
                                    f"Акту присвоен следующий свободный номер: {got}.")
        d["number"] = got
        tail = f"{d['date'][:5]} {d['brand']} {d['model']}".strip()
        tail = re.sub(r'[\\/:*?"<>|]+', " ", tail)
        de_path = os.path.join(folder, f"(Kreuzberg) {tail}.docx")
        ru_path = os.path.join(folder, f"Перевод инспекции {tail}.docx")
        for pth in (de_path, ru_path):
            if os.path.exists(pth):
                if QMessageBox.question(self, "Акт осмотра", f"Файл уже есть:\n{os.path.basename(pth)}\n\nЗаменить?") != QMessageBox.Yes:
                    return
                break
        try:
            ACT.fill_de(act_kit_path("de"), d, de_path)
            texts = {idx: te.toPlainText() for idx, orig, te in self._sections if te.toPlainText().strip() != orig.strip()}
            ACT.fill_ru(act_kit_path("ru"), d, ru_path, texts)
        except PermissionError:
            QMessageBox.critical(self, "Акт осмотра", "Файл акта открыт в другой программе (например, в Word). "
                                 "Закройте его и нажмите «Создать акт» ещё раз.")
            return
        except Exception as e:
            QMessageBox.critical(self, "Акт осмотра", f"Не удалось заполнить бланки:\n{e}")
            return
        act_set_last(got)
        self._dict_learn(d)
        s = settings_load()
        s["act_last_master"] = m["name"]
        settings_save(s)
        self.ed_number.setText(str(int(got) + 1))
        self.win.reload_files()
        self.win.open_word(de_path, quiet=True)                  # оригинал → PDF (через Word) и на страницу
        note = self.win.act_finish(d, m)
        self.win.ai_mode(False)
        self.win.show_toast(f"✔  Акт № {got} создан. {note}", 6500)
        self.win.statusBar().showMessage(f"Перевод сохранён: {os.path.basename(ru_path)} — откройте его в списке файлов, "
                                         "чтобы сохранить в PDF", 15000)


class TabScrollWatch(QObject):
    """Следит за полосой вкладок и показывает свои стрелки, когда вкладки не помещаются."""

    def __init__(self, win):
        super().__init__(win)
        self.win = win

    def eventFilter(self, obj, ev):
        if ev.type() in (QEvent.Paint, QEvent.Resize, QEvent.LayoutRequest):
            QTimer.singleShot(0, self.win._tab_arrows_sync)
        return False


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
        self.center_stack = QStackedWidget()    # 0 — страница документа, 1 — ИИ-помощник
        self.center_stack.addWidget(self.view)
        self.setCentralWidget(self.center_stack)
        self._sc_esc = QShortcut(QKeySequence(Qt.Key_Escape), self)
        self._sc_esc.setContext(Qt.WindowShortcut)
        self._sc_esc.activated.connect(self._esc)
        self.scene.selectionChanged.connect(self.sync_panel_from_selection)
        self.scene.selectionChanged.connect(self._update_geom_title)

        self._build_mascot()
        self._build_toolbar()
        self._build_dir_bar()
        self._build_side_panel()
        self._build_menubar()
        self._sign_all_state()
        self._update_geom_title()
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
        style += ("\nQTabBar::scroller { width: 0px; }"
                  "\nQTabBar QToolButton { width: 0px; max-width: 0px; border: none; margin: 0; padding: 0; background: transparent; }")
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
        self.act_sheet = add("sheet", "Разместить на листе…", self.place_on_sheet, None,
                             "Положить документ нестандартного размера на лист, как на стекло сканера; "
                             "размер и место сохраняются шаблоном")
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
        self.act_close = add("close", "Закрыть документ", self.close_document, "Ctrl+W",
                             "Закрыть документ — закончить работу с открытым PDF")
        tb.widgetForAction(self.act_close).setToolButtonStyle(Qt.ToolButtonIconOnly)
        tb.addSeparator()

        # ИИ-помощник: то же меню стоит в строке меню сверху
        self.btn_ai = QToolButton()
        self.btn_ai.setText("ИИ")
        self._ai_btn_tip = ("ИИ-помощник: открыть его прямо в этом окне, на месте страницы  (Ctrl+Shift+I)\n"
                            "Отдельные функции — в меню «ИИ» вверху")
        self.btn_ai.setToolTip(self._ai_btn_tip)
        self.btn_ai.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self._build_ai_menu()                   # само меню — в строке меню «ИИ»; кнопка цельная, без стрелки
        self.btn_ai.clicked.connect(self.ai_center)
        tb.addWidget(self.btn_ai)
        self._themed_toolbtns = [(self.btn_ai, "ai")]

        self.act_meta = add("meta", "Метаданные PDF…", self.show_metadata, None,
                            "Посмотреть и очистить метаданные PDF", target=self)

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
        hold = str(settings_load().get("update_hold") or "")
        if silent and hold and vtuple(latest) <= vtuple(hold):
            return                              # пользователь сам вернулся с этой версии на прежнюю
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
        st = settings_load()
        st.pop("update_hold", None)
        settings_save(st)
        self._install_from_url(url, "обновление")

    def _install_from_url(self, url, what="обновление"):
        """Скачать установщик и запустить его; программа закроется, установится и откроется снова."""
        dest = os.path.join(LIB_DIR, "updates", "StampStudio-Setup.exe")
        prog = QProgressDialog(f"Скачиваю {what}…", "Отмена", 0, 100, self)
        prog.setWindowTitle("Установка версии")
        prog.setWindowModality(Qt.WindowModal)
        prog.setMinimumDuration(0)
        prog.setAutoClose(False)
        prog.setAutoReset(False)
        th = UpdateDownloadThread(url, dest, self)
        self._upd_dl = th

        def on_progress(got, total):
            if total:
                prog.setValue(int(got * 100 / total))
                prog.setLabelText(f"Скачиваю {what}: {got / 1048576:.0f} из {total / 1048576:.0f} МБ")
            else:
                prog.setLabelText(f"Скачиваю {what}: {got / 1048576:.0f} МБ")

        def on_done(path, error):
            prog.close()
            if error:
                if error != "отменено":
                    QMessageBox.warning(self, "Установка версии", "Не удалось скачать:\n" + error)
                return
            try:
                apply_update_installer(path)
            except Exception as e:
                QMessageBox.warning(self, "Установка версии", f"Не удалось запустить установку:\n{e}")
                return
            QApplication.quit()

        th.progress.connect(on_progress)
        th.done.connect(on_done)
        prog.canceled.connect(lambda: setattr(th, "cancelled", True))
        th.start()

    def show_versions(self):
        """Помощь → Версии и откат: список выпущенных версий, возврат к прежней."""
        if getattr(self, "_rel_thread", None) is not None and self._rel_thread.isRunning():
            return
        self.statusBar().showMessage("Загружаю список версий…", 5000)
        self._rel_thread = ReleasesThread(self)
        self._rel_thread.result.connect(self._on_releases)
        self._rel_thread.start()

    def _on_releases(self, releases, err):
        if not releases:
            QMessageBox.warning(self, "Версии", "Не удалось получить список версий. Проверьте интернет.\n\n" + (err or ""))
            return
        dlg = VersionsDialog(releases, self)
        if dlg.exec() != QDialog.Accepted:
            return
        r = dlg.chosen()
        if not r or r["version"] == APP_VERSION:
            return
        older = vtuple(r["version"]) < vtuple(APP_VERSION)
        if self.doc is not None and (self.stamps or self.view.pen_active()):
            q = QMessageBox.question(self, "Версии", "На документе есть несохранённые печати. Программа закроется "
                                                     "для установки — продолжить без сохранения?")
            if q != QMessageBox.Yes:
                return
        st = settings_load()
        if older:
            st["update_hold"] = releases[0]["version"]      # не предлагать то, с чего ушли
        else:
            st.pop("update_hold", None)
        settings_save(st)
        if not INSTALLED or sys.platform != "win32":
            QDesktopServices.openUrl(QUrl(r["url"]))
            return
        self._install_from_url(r["url"], f"версию {r['version']}")

    def closeEvent(self, event):
        try:
            s = settings_load()
            if hasattr(self, "left_dock"):
                s["left_panel_width"] = self.left_dock.width()
            settings_save(s)
        except Exception:
            pass
        try:                                            # есть неотправленные изменения — отправить перед выходом
            if getattr(self, "_cloud_timer", None) is not None and self._cloud_timer.isActive():
                self._cloud_timer.stop()
                self.cloud_sync()
        except Exception:
            pass
        th = getattr(self, "_cloud_thread", None)       # дать синхронизации закончиться
        try:
            if th is not None and th.isRunning():
                th.failed.disconnect()
                loop = QEventLoop(self)                 # результат применяем, но дольше 6 секунд выход не держим
                th.finished.connect(loop.quit)
                QTimer.singleShot(6000, loop.quit)
                loop.exec()
                if th.isRunning():
                    th.done.disconnect()
                    th.wait(2000)
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
        self.act_settings = act("Настройки…", lambda: SettingsDialog(self).exec(), "Ctrl+,",
                                "Все настройки программы по разделам: тема, обновления, дата, сохранение, сканер, ИИ, Word")
        self.act_word = act("Редактор Word…", self.act_word_fill_run, "Ctrl+Shift+W",
                            "Заполнить шаблон Word: ФИО, паспорт, даты, суммы прописью — оформление не меняется")
        m.addAction(self.act_word)
        self.act_act = act("Акт осмотра…", self.open_act_page, "Ctrl+Shift+K",
                           "Акт осмотра автомобиля: оригинал на немецком и перевод, замеры ЛКП почерком мастера")
        m.addAction(self.act_act)
        m.addAction(self.act_meta)
        m.addAction(self.act_close)
        m.addSeparator()
        m.addAction(self.act_settings)
        m.addSeparator()
        m.addAction(act("Выход", self.close, "Ctrl+Q", "Закрыть программу"))

        # ---- Правка
        m = mb.addMenu("Правка")
        self.act_place = act("Поставить печать на страницу", self.add_stamp, "Ctrl+Return",
                             "Поставить выбранную печать в центр страницы", doc=True)
        m.addAction(self.act_place)
        m.addAction(self.act_pen)
        self.act_sign_all = act("Подписать все места…", self.sign_all, None,
                                "Поставить подпись выбранного человека на все строки его подписи в документе", doc=True)
        m.addAction(self.act_sign_all)
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
        m.addAction(self.act_sheet)
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
        m.addAction(act("Дата и время…", self._date_menu, None,
                        "Какую дату программа и ИИ считают сегодняшней: компьютер, часовой пояс или своя дата"))

        # ---- ИИ (то же меню, что у кнопки «ИИ» в панели)
        mb.addMenu(self.ai_menu)

        # ---- Помощь
        m = mb.addMenu("Помощь")
        m.addAction(self.act_help)
        m.addAction(act("Что нового в этой версии", self.show_whats_new, None, "Список изменений на сайте"))
        m.addAction(act("Проверить обновления", lambda: self.check_updates(silent=False), None,
                        "Проверить, не вышла ли новая версия"))
        m.addAction(act("Версии и откат…", self.show_versions, None,
                        "Вернуться к прежней версии, если новая не подошла"))
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
            [(self.act_scanlook, "scanlook"), (self.act_ai_ocr, "ocr"), (self.act_word, "word_edit")],
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

        self.act_ai_center = act("ИИ-помощник — показать / вернуться к документу", self.ai_center, "Ctrl+Shift+I",
                                 "Выбор сервиса, счётчик запросов, все функции ИИ и результат в одном окне",
                                 doc=False)
        m.addSeparator()
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
        if not quiet and getattr(self, "_ai_busy", False):
            self.show_toast("ИИ ещё отвечает на прошлый запрос — подождите")
            return None
        th = AiThread(fn, self)
        self._ai_threads = [t for t in getattr(self, "_ai_threads", []) if t.isRunning()] + [th]
        busy = None
        if not quiet:
            self._ai_busy = True
            th.finished.connect(lambda: setattr(self, "_ai_busy", False))
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
            if not quiet:
                self._ai_busy = False
            on_done(res)
            self._ai_center_refresh()

        def bad(msg):
            close_busy()
            if not quiet:
                self._ai_busy = False
            (on_fail or self._ai_fail)(msg)
            self._ai_center_refresh()
        th.done.connect(ok)
        th.failed.connect(bad)
        th.start()
        if busy is not None:
            busy.open()
        return th

    def ai_center(self, *_):
        """Окно «ИИ-помощник»: сервис, счётчики, все функции и результат."""
        self.ai_mode(not self._ai_on())

    # ---------------------------------------------------------- облако
    def _cloud_label(self):
        on = bool(settings_load().get("cloud_uri"))
        self.btn_cloud.setVisible(on)
        state, tip = self._cloud_state
        self.btn_cloud.setText(" Облако" + (f": {state} " if state else " "))
        self.btn_cloud.setToolTip((tip + "\n" if tip else "") + "Щелчок — синхронизировать сейчас.\n"
                                  "Настройка: Файл → Настройки → Облако")

    def changeEvent(self, e):
        """Вернулись в окно программы — сразу забрать то, что изменили на других компьютерах."""
        super().changeEvent(e)
        try:
            if e.type() == QEvent.ActivationChange and self.isActiveWindow() and hasattr(self, "_cloud_timer") \
                    and time.time() - getattr(self, "_cloud_last", 0) > 45:
                self.cloud_soon(800)
        except Exception:
            pass

    def cloud_soon(self, ms=4000):
        """Что-то изменилось — отправить в облако чуть позже, одним разом."""
        if getattr(self, "_cloud_applying", False) or not hasattr(self, "_cloud_timer"):
            return
        if settings_load().get("cloud_uri"):
            self._cloud_timer.start(ms)

    def _cloud_local(self):
        """Собрать всё, что сверяется с облаком (в главном потоке)."""
        st = settings_load()
        parts = st.get("cloud_parts") or {}
        local = {"stamps": {}, "clients": {}, "settings": {}, "counters": {}}
        if parts.get("stamps", True):
            for e in lib_load():
                try:
                    with open(e["file"], "rb") as f:
                        data = f.read()
                    local["stamps"][os.path.basename(e["file"])] = {
                        "meta": {k: v for k, v in e.items() if k != "file"}, "data": data,
                        "mtime": max(os.path.getmtime(e["file"]), os.path.getmtime(LIB_JSON))}
                except OSError:
                    pass
        if parts.get("clients", True):
            for key, vals in (_json_read(CLOUD_CLIENTS, {}) or {}).items():
                if vals:
                    local["clients"][key] = {"values": vals, "mtime": 0}
            for key, folder in list((st.get("client_dirs") or {}).items()):
                vals = SW.card_load(folder, fallback=False) if os.path.isdir(folder) else {}
                if vals:
                    try:
                        mt = os.path.getmtime(SW.card_path(folder))
                    except OSError:
                        mt = 0
                    local["clients"][key] = {"values": vals, "mtime": mt}
        if parts.get("settings", True):
            try:
                mt = os.path.getmtime(SETTINGS_JSON)
            except OSError:
                mt = 0
            for name in ("word_marks", "pen_presets", "name_templates", "sheet_templates", "crop_templates", "act_masters", "act_dict"):
                if st.get(name):
                    local["settings"][name] = {"value": st[name], "mtime": mt}
            try:
                kit, kmt = act_kit_value()                   # бланки акта осмотра — общие на всю мастерскую
                if kit:
                    local["settings"]["act_kit"] = {"value": kit, "mtime": kmt}
            except Exception:
                pass
        if parts.get("counters", True):
            local["counters"] = {k: dict(v) for k, v in (st.get("doc_counters") or {}).items() if v.get("last")}
        return local

    def cloud_sync(self, manual=False, report=None):
        uri = cloud_uri()
        if not uri:
            if manual:
                self.show_toast("Облако не настроено: Файл → Настройки → Облако")
            return
        th = getattr(self, "_cloud_thread", None)
        if th is not None and th.isRunning():
            self._cloud_again = True
            return
        state = _json_read(CLOUD_STATE, {})
        uid = CLOUD.digest(uri)[:12]
        snap = state.get("snap") if state.get("uri") == uid else {}       # другая база — сверяем с нуля
        local = self._cloud_local()
        self._cloud_local_hashes = {
            "stamps": {i: CLOUD.digest([e["meta"], CLOUD.digest(e["data"])]) for i, e in local["stamps"].items()}}
        private = bool(settings_load().get("cloud_private_local", False))
        self._cloud_state = ("…", "Идёт синхронизация")
        self._cloud_label()
        th = CloudThread(uri, local, snap or {}, private, self)
        self._cloud_thread = th
        self._cloud_last = time.time()

        def done(res):
            text = self._cloud_apply(res, uid)
            if report:
                report("✔ " + text)
            elif manual:
                self.show_toast("✔  Облако: " + text, 3600)
            if getattr(self, "_cloud_again", False):
                self._cloud_again = False
                self.cloud_soon(2000)

        def failed(msg):
            self._cloud_state = ("нет связи", msg)
            self._cloud_label()
            if report:
                report("⚠ " + msg)
            elif manual:
                QMessageBox.warning(self, "Облако", msg)

        th.done.connect(done)
        th.failed.connect(failed)
        th.start()

    def _cloud_apply(self, res, uid):
        """Применить на этом компьютере то, что пришло из облака."""
        self._cloud_applying = True
        try:
            snap = res["snap"]
            st = settings_load()
            private = bool(st.get("cloud_private_local", False))
            # печати
            if res["stamps_put"] or res["stamps_del"]:
                items = lib_load()
                by_id = {os.path.basename(e["file"]): e for e in items}
                now = {}
                for i, e in by_id.items():
                    try:
                        with open(e["file"], "rb") as f:
                            now[i] = CLOUD.digest([{k: v for k, v in e.items() if k != "file"}, CLOUD.digest(f.read())])
                    except OSError:
                        pass
                for i, d in res["stamps_put"].items():
                    if now.get(i) != d["was"]:
                        snap["stamps"].pop(i, None)          # здесь её успели изменить — разберёмся в следующий раз
                        continue
                    path = os.path.join(LIB_DIR, os.path.basename(i))
                    try:
                        with open(path, "wb") as f:
                            f.write(d["data"])
                    except OSError:
                        snap["stamps"].pop(i, None)
                        continue
                    entry = dict(d["meta"], file=path)
                    if i in by_id:
                        items[items.index(by_id[i])] = entry
                    else:
                        items.append(entry)
                for i, was in res["stamps_del"]:
                    if i in by_id and now.get(i) == was:
                        items = [e for e in items if os.path.basename(e["file"]) != i]
                        try:
                            os.remove(by_id[i]["file"])
                        except OSError:
                            pass
                lib_save(items)
                self.reload_library()
            # клиенты
            if res["clients_put"] or res["clients_del"]:
                reg = st.get("client_dirs") or {}
                cache = _json_read(CLOUD_CLIENTS, {}) or {}
                for key, d in res["clients_put"].items():
                    folder = reg.get(key, "")
                    vals = dict(d["values"])
                    if folder and os.path.isdir(folder):
                        mine = SW.card_load(folder, fallback=False)
                        for k in CLOUD.PRIVATE_KEYS:              # паспортные данные с этого компьютера не теряем
                            if k not in vals and k in mine:
                                vals[k] = mine[k]
                        SW.card_save(folder, vals)
                        cache.pop(key, None)
                    else:
                        cache[key] = vals
                for key, _was in res["clients_del"]:
                    cache.pop(key, None)
                    folder = reg.get(key, "")
                    if folder and os.path.isdir(folder):
                        SW.card_save(folder, {})
                _json_write(CLOUD_CLIENTS, cache)
                self._client_line()
            # настройки и счётчики
            st = settings_load()
            for name, d in res["settings_put"].items():
                if name == "act_kit":
                    try:
                        cur, _mt = act_kit_value()
                        if (CLOUD.digest(cur) if cur else None) == d["was"]:
                            act_kit_store(d["value"])
                            pg = getattr(self, "_act_page", None)
                            if pg is not None:
                                pg._sections = []
                            self._act_btn_state()
                        else:
                            snap["settings"].pop(name, None)
                    except Exception:
                        snap["settings"].pop(name, None)
                    continue
                if (CLOUD.digest(st[name]) if st.get(name) else None) == d["was"]:
                    st[name] = d["value"]
                else:
                    snap["settings"].pop(name, None)
            if res["counters"]:
                st.setdefault("doc_counters", {}).update(res["counters"])
            settings_save(st)
            _json_write(CLOUD_STATE, {"uri": uid, "snap": snap, "time": time.time()})
        finally:
            self._cloud_applying = False
        when = datetime.datetime.now().strftime("%H:%M")
        text = f"отправлено {res['up']}, получено {res['down']}" + (f", удалено {res['removed']}" if res["removed"] else "")
        self._cloud_state = ("✓ " + when, f"Синхронизировано в {when}: {text}")
        self._cloud_label()
        return "синхронизировано — " + text

    def _sign_all_state(self):
        """Пункт «Подписать все места» виден, только если пользователь сам включил это в настройках."""
        if hasattr(self, "act_sign_all"):
            self.act_sign_all.setVisible(bool(settings_load().get("sign_all_enabled", False)))

    def find_sign_places(self, surname):
        """[(страница, cx, cy)] — строки подписи рядом с фамилией: «Фамилия И. О. / ______ /»."""
        key = AI._letters(surname)
        out = []
        if not key or self.doc is None:
            return out
        for pi in range(self.doc.page_count):
            words = AI.page_words(self.doc[pi])
            lines = [w for w in words if w[4].count("_") >= 6]
            used = set()
            for w in words:
                if not AI._letters(w[4]).startswith(key):
                    continue
                h = max(4.0, w[3] - w[1])
                cy = (w[1] + w[3]) / 2
                best, score = None, 1e9
                for k, u in enumerate(lines):
                    if k in used:
                        continue
                    ucy = (u[1] + u[3]) / 2
                    dy = abs(ucy - cy)
                    if dy < h * 1.1:                                   # та же строка
                        dx = u[0] - w[2] if u[0] >= w[2] else w[0] - u[2]
                        if -h <= dx <= 260 and dx + dy < score:
                            best, score = k, dx + dy
                    elif dy < h * 3.2 and u[0] < w[2] + 30 and u[2] > w[0] - 30:   # строкой выше или ниже
                        if 300 + dy < score:
                            best, score = k, 300 + dy
                if best is not None:
                    used.add(best)
                    u = lines[best]
                    out.append((pi, (u[0] + u[2]) / 2, u[1] + (u[3] - u[1]) * 0.25))
        return out

    def sign_all(self):
        if not settings_load().get("sign_all_enabled", False) or not self._ai_need_doc():
            return
        signs = [e for e in lib_load() if "подпис" in (e.get("category", "") + " " + e.get("name", "")).lower()] or lib_load()
        if not signs:
            QMessageBox.information(self, "Подписать все места", "В библиотеке нет подписей. Добавьте подпись "
                                                                  "в «Мои печати» (категория «Подписи»).")
            return
        st = settings_load()
        names = st.get("sign_names") or {}
        dlg = QDialog(self)
        dlg.setWindowTitle("Подписать все места")
        dlg.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        dlg.setMinimumWidth(520)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(18, 16, 18, 14)
        lay.setSpacing(10)
        hint = QLabel("Программа найдёт в документе строки вида «Фамилия И. О. / ________ /» и поставит подпись на каждую. "
                      "Ставьте так только свою подпись или подпись того, кто это разрешил.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        cmb = QComboBox()
        cmb.setMinimumHeight(30)
        for e in signs:
            cmb.addItem(e.get("name", "подпись"), e)
        ed = QLineEdit()
        ed.setMinimumHeight(30)
        ed.setPlaceholderText("фамилия, как в документе — например Воронцов")
        g = QGridLayout()
        g.addWidget(QLabel("Подпись:"), 0, 0)
        g.addWidget(cmb, 0, 1)
        g.addWidget(QLabel("Чья (фамилия):"), 1, 0)
        g.addWidget(ed, 1, 1)
        lay.addLayout(g)
        info = QLabel("")
        info.setObjectName("plain")
        lay.addWidget(info)

        def sync_name(*_):
            e = cmb.currentData()
            ed.setText(names.get(os.path.basename(e.get("file", "")), ""))

        def count(*_):
            n = len(self.find_sign_places(ed.text().strip())) if ed.text().strip() else 0
            info.setText(f"Найдено мест для подписи: {n}" if ed.text().strip() else "")
            ok.setEnabled(n > 0)

        row = QHBoxLayout()
        row.addStretch(1)
        ok = QPushButton("Поставить")
        ok.setObjectName("primary")
        ok.clicked.connect(dlg.accept)
        row.addWidget(ok)
        b = QPushButton("Отмена")
        b.clicked.connect(dlg.reject)
        row.addWidget(b)
        lay.addLayout(row)
        cmb.currentIndexChanged.connect(sync_name)
        ed.textChanged.connect(count)
        sync_name()
        count()
        if dlg.exec() != QDialog.Accepted:
            return
        entry, surname = cmb.currentData(), ed.text().strip()
        st = settings_load()
        st.setdefault("sign_names", {})[os.path.basename(entry.get("file", ""))] = surname
        settings_save(st)
        places = self.find_sign_places(surname)
        lift = float(entry.get("mm_h", 18)) * MM_TO_PT * 0.18
        page_now = self.current_page
        n = 0
        for pi, cx, cy in places:
            if self._place_entry(entry, pi, cx, cy - lift) is not None:
                n += 1
        if places:
            self.page_list.setCurrentRow(places[0][0])
        self.show_toast(f"✔  Подпись «{entry.get('name', '')}» поставлена: {n} мест. Проверьте каждое и подвиньте, "
                        "если нужно", 5200)

    def _client_line(self):
        if not hasattr(self, "lbl_client"):
            return
        try:                                            # карточки этой папки и соседних — в список для облака
            if register_client_dirs(find_client_dirs(self.current_dir())):
                self.cloud_soon()
        except Exception:
            pass
        data = SW.derive(SW.card_load(self.current_dir()))
        who = data.get("fio_short") or data.get("fio") or ""
        car = data.get("car", "")
        text = ("Клиент: " + who + (f" · {car}" if car else "")) if who else "Клиент: карточки нет — создать"
        fm = self.lbl_client.fontMetrics()
        self.lbl_client.setText(fm.elidedText(text, Qt.ElideRight, max(120, self.lbl_client.width() - 4)))

    def open_client_card(self):
        folder = self.current_dir()
        if not os.path.isdir(folder):
            return
        if ClientCardDialog(folder, self).exec() == QDialog.Accepted:
            self._client_line()
            pg = getattr(self, "_word_page", None)
            if pg is not None and pg.wd is not None and os.path.normcase(pg.client_dir) == os.path.normcase(folder):
                pg._apply_card(only_empty=False)
            self.show_toast("✔  Карточка клиента сохранена в папке", 3000)

    def act_word_fill_run(self):
        self.word_fill()

    def _selected_docx(self):
        it = self.file_list.currentItem() if hasattr(self, "file_list") else None
        data = it.data(Qt.UserRole) if it is not None else None
        return data[1] if data and data[0] == "file" and data[1].lower().endswith(".docx") else ""

    def _fill_btn_state(self):
        if hasattr(self, "btn_fill"):
            self.btn_fill.setVisible(bool(self._selected_docx()) or str(self.doc_path or "").endswith(".docx (из Word)"))

    def _fill_selected(self):
        self.word_fill(self._selected_docx() or None)

    def _ai_on(self):
        c = getattr(self, "_ai_center_dlg", None)
        return c is not None and self.center_stack.currentWidget() is c

    def _page_on(self):
        return self.center_stack.currentIndex() != 0

    def word_fill(self, path=None):
        """Заполнить документ Word: поля, образцы, правка текста — без поломки оформления."""
        if not path:
            cur = str(self.doc_path or "")
            if cur.endswith(" (из Word)"):
                path = cur[:-len(" (из Word)")]
            else:
                path, _ = QFileDialog.getOpenFileName(self, "Выберите документ Word для заполнения",
                                                      self.current_dir(), "Документ Word (*.docx)")
                if not path:
                    return
        if not path.lower().endswith(".docx"):
            QMessageBox.information(self, "Заполнение Word",
                                    "Заполнять можно файлы .docx. Откройте этот документ в Word и сохраните "
                                    "как «Документ Word (*.docx)».")
            return
        pg = getattr(self, "_word_page", None)
        if pg is None:
            pg = WordFillPage(self)
            self._word_page = pg
            self.center_stack.addWidget(pg)
        try:
            if pg.path != path or pg.wd is None:
                pg.load(path)
        except Exception as e:
            QMessageBox.critical(self, "Заполнение Word", f"Не удалось прочитать документ:\n{e}")
            return
        if str(self.doc_path or "") != path + " (из Word)":
            self.open_word(path, quiet=True)                 # слева и на странице — тот же документ
        if self.view.pen_active():
            self.pen_finish(commit=True)
        self.right_dock.hide()
        self.left_dock.hide()
        self.center_stack.setCurrentWidget(pg)

    # ---------------------------------------------------------- акт осмотра
    def open_act_page(self):
        """Акт осмотра занимает середину окна, как ИИ и редактор Word."""
        act_kit_ensure()                       # бланки идут с программой; свои можно загрузить кнопкой «Бланки…»
        pg = getattr(self, "_act_page", None)
        if pg is None:
            pg = ActPage(self)
            self._act_page = pg
            self.center_stack.addWidget(pg)
        else:
            pg.refresh()
        if self.view.pen_active():
            self.pen_finish(commit=True)
        self.right_dock.hide()
        self.left_dock.hide()
        self.center_stack.setCurrentWidget(pg)
        self._act_btn_state()

    def _act_btn_state(self):
        b = getattr(self, "btn_act", None)
        if b is not None:
            b.setVisible(act_kit_ready())

    def act_finish(self, d, master):
        """Оригинал акта уже открыт: вписать замеры почерком мастера, положить его подпись и печать.
        Возвращает короткую подсказку, что делать дальше."""
        doc = self.doc
        if doc is None or "(из Word)" not in str(self.doc_path or ""):
            return "Оригинал не открылся — откройте его в списке файлов."
        notes = []
        glyphs = master.get("glyphs") or {}
        vals = d.get("lkp") or {}
        seed = int(time.time() * 1000) % 1000003
        rnd = __import__("random").Random(seed)
        where = ACT.find_diagram(doc)
        if vals and where is None:
            notes.append("Схема в PDF не найдена — замеры не вписаны (нужен Microsoft Word).")
        elif vals:
            pno, rect = where
            page = doc[pno]
            for name, x0, y0, x1, y1 in ACT.lkp_places(rect, d.get("kind", "car")):
                text = vals.get(name)
                if not text:
                    continue
                bw, bh = x1 - x0, y1 - y0
                wheel = name.startswith("w")
                h_pt = bh * (0.40 if wheel else 0.98)
                im = hand_pil(text.replace("%", "") if wheel else text, glyphs, int(h_pt * 300 / 72), rnd.randrange(10 ** 6))
                if im is None:
                    continue
                ang = rnd.uniform(-3.0, 3.0)
                im = im.rotate(ang, expand=True, resample=Image.BICUBIC)
                k = h_pt / (int(h_pt * 300 / 72) * 1.1)
                w_pt, hh_pt = im.width * k, im.height * k
                max_w = bw * (0.50 if wheel else 0.92)
                if w_pt > max_w:
                    hh_pt *= max_w / w_pt
                    w_pt = max_w
                cx = x0 + bw * (0.36 if wheel else 0.5) + rnd.uniform(-0.04, 0.04) * bw
                cy = y0 + bh * 0.5 + rnd.uniform(-0.05, 0.05) * bh
                buf = io.BytesIO()
                im.save(buf, "PNG")
                page.insert_image(fitz.Rect(cx - w_pt / 2, cy - hh_pt / 2, cx + w_pt / 2, cy + hh_pt / 2),
                                  stream=buf.getvalue(), keep_proportion=False, overlay=True)
        last = doc.page_count - 1
        pr = doc[last].rect
        to_px = PREVIEW_DPI / 72.0

        def put(pil, mm_w, fx, fy, opacity):
            mm_h = mm_w * pil.height / max(1, pil.width)
            pm = self._pixmap_from_pil(pil)
            item = StampItem(pm, pil, mm_w, mm_h, last)
            item.opacity_value = opacity
            item.setOpacity(opacity)
            self.scene.addItem(item)
            item.setPos(pr.width * fx * to_px, pr.height * fy * to_px)
            self.stamps.append(item)
            return item

        placed = []
        sg = sign_pil(master.get("sign"), 220)
        if sg is not None:
            put(sg, 46.0, 0.60, 0.80, 1.0)
            placed.append("подпись")
        if master.get("stamp"):
            ent = next((s for s in lib_load() if os.path.basename(s["file"]) == master["stamp"]), None)
            try:
                if ent is not None:
                    st = Image.open(ent["file"]).convert("RGBA")
                    put(st, float(ent.get("mm_w") or 40.0), 0.28, 0.76, 0.9)
                    placed.append("печать")
            except Exception:
                pass
        self.refresh_page_list(last if placed else 0)
        self.show_page(last if placed else 0)
        self._update_ui_state()
        if placed:
            notes.append(f"На последней странице лежат {' и '.join(placed)} мастера — подвиньте на место.")
        else:
            notes.append("У мастера нет подписи и печати в профиле — поставьте их вручную.")
        notes.append("Дальше сохраните как PDF или «Как скан».")
        return " ".join(notes)

    def ai_mode(self, on=True):
        """ИИ-помощник занимает середину главного окна вместо страницы; список файлов слева остаётся."""
        if on:
            if self.view.pen_active():
                self.pen_finish(commit=True)
            c = getattr(self, "_ai_center_dlg", None)
            if c is None:
                c = AiCenterDialog(self)
                self._ai_center_dlg = c
                self.center_stack.addWidget(c)
            self.right_dock.hide()
            self.left_dock.show()
            self.center_stack.setCurrentWidget(c)
            c.refresh()
        else:
            self.center_stack.setCurrentIndex(0)
            self.right_dock.show()
            self.left_dock.show()
            self.view.setFocus()
        try:
            self.btn_ai.setToolTip("Вернуться к странице документа (Esc)" if on else self._ai_btn_tip)
        except AttributeError:
            pass

    def _center(self):
        c = getattr(self, "_ai_center_dlg", None)
        return c if c is not None and self._ai_on() else None

    def _ai_go_page(self, i):
        """Из списка замечаний — к странице документа (результат остаётся в ИИ-помощнике)."""
        if self.doc is None or not (0 <= i < self.doc.page_count):
            return
        if self._ai_on():
            self.ai_mode(False)
            self.statusBar().showMessage("Страница замечания. Вернуться к списку — кнопка «ИИ» "
                                         "или Ctrl+Shift+I", 8000)
        self.page_list.setCurrentRow(i)

    def _ai_center_refresh(self):
        c = self._center()
        if c is not None:
            c.refresh()

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
        return name.replace(" (из изображений)", "").replace(" (из Word)", "")

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
        c = self._center()
        if c is not None:
            dlg.finished.connect(lambda code, d=dlg: self._ai_name_action(d) if code == QDialog.Accepted else None)
            c.embed(dlg, "Имя файла")
            return
        if dlg.exec() != QDialog.Accepted:
            return
        self._ai_name_action(dlg)

    def _ai_name_action(self, dlg):
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
                self.doc = open_pdf_free(old)
                raise
            self.doc = open_pdf_free(new)
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
        c = self._center()
        if c is not None:
            c.note(msg)
            self.ai_mode(False)                 # печати стоят на странице — показываем её
        self.show_toast(msg, 5200)

    # ---------------------------------------------------------- 3. данные

    def ai_extract(self):
        if not self._ai_need_doc() or not self._ai_ready():
            return
        bundle = AI.collect(self.doc, None, max_images=4)
        title = self._doc_title()

        def show(res):
            dlg = AiDataDialog(res, title, self)
            c = self._center()
            if c is not None:
                c.embed(dlg, "Данные из документа")
            else:
                dlg.exec()
        self._ai_run("ИИ выписывает данные из документа",
                     lambda st, c: AI.task_extract(bundle, None, st, c), show)

    # ---------------------------------------------------------- 4. проверка

    def ai_check(self):
        if not self._ai_need_doc() or not self._ai_ready():
            return
        parts = AI.split_pages(self.doc, 4)
        if len(parts) > 6:
            q = QMessageBox.question(
                self, "Большой документ",
                f"В документе много сканов: проверка займёт {len(parts)} запросов к ИИ.\nПродолжить?")
            if q != QMessageBox.Yes:
                return
        bundles = [AI.collect(self.doc, pg, max_images=4, max_chars=24000) for pg in parts]
        title = self._doc_title()

        def work(status, cancelled):
            total = {"summary": "", "issues": [], "skipped": 0, "provider": "", "model": "",
                     "mode": "", "problems": [], "parts": len(bundles)}
            notes = []
            for n, b in enumerate(bundles):
                if cancelled():
                    raise AI.AiCancelled()
                pre = f"часть {n + 1} из {len(bundles)} · " if len(bundles) > 1 else ""
                res = AI.task_check(b, lambda t, pre=pre: status(pre + t), cancelled)
                total["issues"] += res["issues"]
                if res["summary"]:
                    notes.append(res["summary"])
                for k in ("provider", "model", "mode"):
                    total[k] = res[k]
                total["problems"] += res.get("problems") or []
            total["issues"].sort(key=lambda x: (x["severity"] != "error", x["page"]))
            total["summary"] = notes[0] if len(notes) == 1 else ""
            return total

        def show(res):
            dlg = AiCheckDialog(res, title, self)
            dlg.go_page.connect(self._ai_go_page)
            self._ai_check_dlg = dlg
            c = self._center()
            if c is not None:
                c.embed(dlg, "Проверка перед отправкой")
            else:
                dlg.setModal(False)
                dlg.show()
        self._ai_run("ИИ проверяет документ" + (f" — {len(bundles)} запроса(ов)" if len(bundles) > 1 else ""),
                     work, show)

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
        c = self._center()
        if c is not None:
            c.note(msg)

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

        # свои стрелки прокрутки вкладок: родные у Qt рисуются обрезанными
        self._tab_arrows = []
        for kind, tip in (("chev_left", "Предыдущие вкладки"), ("chev_right", "Следующие вкладки")):
            b = QPushButton()
            b.setFixedSize(22, 30)
            b.setToolTip(tip)
            b.setIconSize(QSize(12, 12))
            b.setAutoRepeat(True)
            b.setVisible(False)
            b.clicked.connect(lambda _=False, k=kind: self._tab_scroll(k))
            self._themed_buttons.append((b, kind, False))
            self._tab_arrows.append(b)
            row.addWidget(b, 0)
        self._tab_watch = TabScrollWatch(self)
        self.dir_tabs.installEventFilter(self._tab_watch)

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
        self.lbl_path.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.lbl_path.setMinimumWidth(0)
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
        self.btn_cloud = QPushButton("")
        self.btn_cloud.setFlat(True)
        self.btn_cloud.setObjectName("verbtn")
        self.btn_cloud.setCursor(Qt.PointingHandCursor)
        self.btn_cloud.clicked.connect(lambda: self.cloud_sync(manual=True))
        self.statusBar().addPermanentWidget(self.btn_cloud)
        self._cloud_state = ("", "")
        self._cloud_timer = QTimer(self)
        self._cloud_timer.setSingleShot(True)
        self._cloud_timer.timeout.connect(self.cloud_sync)
        self._cloud_every = QTimer(self)
        self._cloud_every.setInterval(3 * 60 * 1000)      # забирать изменения с других компьютеров
        self._cloud_every.timeout.connect(self.cloud_sync)
        self._cloud_every.start()
        LIB_CHANGED.append(lambda: self.cloud_soon())
        SETTINGS_CHANGED.append(lambda: self.cloud_soon())
        self._cloud_last = 0.0
        self._cloud_label()
        self.cloud_soon(5000)
        self.btn_date = QPushButton("")
        self.btn_date.setFlat(True)
        self.btn_date.setObjectName("verbtn")
        self.btn_date.setCursor(Qt.PointingHandCursor)
        self.btn_date.clicked.connect(self._date_menu)
        self.statusBar().addPermanentWidget(self.btn_date)
        self.statusBar().addPermanentWidget(self.btn_version)
        self._date_timer = QTimer(self)
        self._date_timer.setInterval(30000)
        self._date_timer.timeout.connect(self._date_tick)
        self._date_timer.start()
        self._date_tick()
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
        cap_row = QHBoxLayout()
        cap_row.setContentsMargins(0, 0, 2, 0)
        cap_row.addWidget(cap_files, 1)
        b_ref = QToolButton()
        b_ref.setObjectName("ghost")
        b_ref.setAutoRaise(True)
        b_ref.setCursor(Qt.PointingHandCursor)
        b_ref.setFixedSize(24, 24)
        b_ref.setIconSize(QSize(16, 16))
        b_ref.setToolTip("Обновить список файлов  (F5)\nСписок обновляется и сам, когда в папке что-то меняется")
        b_ref.setShortcut(QKeySequence("F5"))
        b_ref.clicked.connect(lambda: self.reload_files(manual=True))
        self._themed_toolbtns.append((b_ref, "refresh"))
        b_del = QToolButton()
        b_del.setObjectName("ghost")
        b_del.setAutoRaise(True)
        b_del.setCursor(Qt.PointingHandCursor)
        b_del.setFixedSize(24, 24)
        b_del.setIconSize(QSize(16, 16))
        b_del.setToolTip("Удалить выбранный файл в корзину Windows  (Del)\nИз корзины его можно вернуть")
        b_del.clicked.connect(self.trash_selected_file)
        self._themed_toolbtns.append((b_del, "trash"))
        cap_row.addWidget(b_del, 0)
        cap_row.addWidget(b_ref, 0)
        tl.addLayout(cap_row)
        self.lbl_client = ClickLabel("")
        self.lbl_client.setObjectName("hint")
        self.lbl_client.setCursor(Qt.PointingHandCursor)
        self.lbl_client.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.lbl_client.setToolTip("Карточка клиента этой папки: ФИО, паспорт, адрес, автомобиль, суммы.\n"
                                   "Из неё редактор Word заполняет документы. Щелчок — открыть или создать.")
        self.lbl_client.clicked.connect(self.open_client_card)
        tl.addWidget(self.lbl_client)

        self.file_list = QListWidget()
        self.file_list.setAlternatingRowColors(True)
        self.file_list.setTextElideMode(Qt.ElideMiddle)
        self.file_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.file_list.setWordWrap(False)
        self.file_list.setMinimumHeight(80)
        self.file_list.itemDoubleClicked.connect(self.open_from_browser)
        self.file_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.file_list.customContextMenuRequested.connect(self.file_menu)
        sc_del = QShortcut(QKeySequence(Qt.Key_Delete), self.file_list)
        sc_del.setContext(Qt.WidgetShortcut)
        sc_del.activated.connect(self.trash_selected_file)
        tl.addWidget(self.file_list, 1)

        b_open = QPushButton(" Открыть выбранный файл")
        b_open.setIconSize(QSize(14, 14))
        b_open.setMinimumHeight(30)
        b_open.clicked.connect(lambda: self.open_from_browser(self.file_list.currentItem()))
        self._themed_buttons.append((b_open, "folder", False))
        self.btn_fill = QPushButton(" Редактор")
        self.btn_fill.setIconSize(QSize(14, 14))
        self.btn_fill.setMinimumHeight(30)
        self.btn_fill.setToolTip("Редактор Word: открыть выбранный документ, заполнить поля и поправить текст.\n"
                                 "Оформление документа не меняется, исходный файл остаётся чистым  (Ctrl+Shift+W)")
        self.btn_fill.clicked.connect(self._fill_selected)
        self.btn_fill.setVisible(False)
        self._themed_buttons.append((self.btn_fill, "word_edit", False))
        orow = QHBoxLayout()
        orow.setSpacing(6)
        orow.addWidget(b_open, 1)
        orow.addWidget(self.btn_fill, 0)
        self.btn_act = QPushButton(" Акт")
        self.btn_act.setIconSize(QSize(14, 14))
        self.btn_act.setMinimumHeight(30)
        self.btn_act.setToolTip("Акт осмотра автомобиля: оригинал на немецком и перевод  (Ctrl+Shift+K)")
        self.btn_act.clicked.connect(self.open_act_page)
        self.btn_act.setVisible(act_kit_ready())
        self._themed_buttons.append((self.btn_act, "act", False))
        orow.addWidget(self.btn_act, 0)
        tl.addLayout(orow)
        b_open.setText(" Открыть")
        b_open.setToolTip("Открыть выбранный в списке файл (или двойной щелчок по нему)")
        self.file_list.currentItemChanged.connect(lambda *_: self._fill_btn_state())
        splitter.addWidget(top)

        # ---------- низ: страницы открытого документа ----------
        bot = QWidget()
        lay = QVBoxLayout(bot)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        cap_pages = QLabel("<b>Страницы документа</b>")
        lay.addWidget(cap_pages)

        self.page_list = PageGrid()
        self.page_list.setViewMode(QListWidget.IconMode)
        self.page_list.setIconSize(QSize(104, 140))
        self.page_list.setGridSize(QSize(140, 170))
        self.page_list.setResizeMode(QListWidget.Adjust)
        self.page_list.setMovement(QListWidget.Snap)
        self.page_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.page_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.page_list.setSpacing(0)
        self.page_list.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.page_list.currentRowChanged.connect(self.show_page)
        self.page_list.itemClicked.connect(lambda *_: self.ai_mode(False) if self._page_on() else None)
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
                 "и отсканировали", self.scan_look),
                ("sheet", " Разместить на листе", "Положить документ нестандартного размера на лист, как на "
                 "стекло сканера; размер и место сохраняются шаблоном", self.place_on_sheet)]):
            b = QPushButton(text)
            b.setIconSize(QSize(15, 15))
            b.setMinimumHeight(32)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            self._themed_buttons.append((b, kind, False))
            if n == 4:
                tools.addWidget(b, 2, 0, 1, 2)       # пятая кнопка — на всю ширину
            else:
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

    def _tab_native(self):
        """Родные (спрятанные) кнопки прокрутки вкладок: левая, правая."""
        bs = [b for b in self.dir_tabs.findChildren(QToolButton)]
        bs.sort(key=lambda b: 0 if b.arrowType() == Qt.LeftArrow else 1)
        return bs if len(bs) == 2 else []

    def _tab_scroll(self, kind):
        bs = self._tab_native()
        if bs:
            bs[0 if kind == "chev_left" else 1].click()
            self._tab_arrows_sync()

    def _tab_arrows_sync(self):
        bs = self._tab_native()
        show = bool(bs) and bs[0].isVisible()
        for nat in bs:                       # родные кнопки остаются рабочими, но не рисуются
            if nat.mask().isEmpty():
                nat.setMask(QRegion(-2, -2, 1, 1))
        for own, nat in zip(self._tab_arrows, bs or (None, None)):
            if own.isVisible() != show:
                own.setVisible(show)
            if show and own.isEnabled() != nat.isEnabled():
                own.setEnabled(nat.isEnabled())

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

    def reload_files(self, manual=False):
        """Перечитать папку, сохранив выделенный файл (кнопка «Обновить», F5 и слежение за папкой)."""
        if not hasattr(self, "file_list"):
            return
        cur = self.file_list.currentItem()
        keep = cur.data(Qt.UserRole) if cur is not None else None
        scroll = self.file_list.verticalScrollBar().value()
        self.refresh_files()
        if keep:
            for i in range(self.file_list.count()):
                if self.file_list.item(i).data(Qt.UserRole) == keep:
                    self.file_list.setCurrentRow(i)
                    break
        self.file_list.verticalScrollBar().setValue(scroll)
        if manual:
            self.statusBar().showMessage("Список файлов обновлён", 2500)

    def _watch_folder(self, folder):
        """Следить за открытой папкой: новый файл появляется в списке сам."""
        try:
            if not hasattr(self, "_dir_watcher"):
                self._dir_watcher = QFileSystemWatcher(self)
                self._dir_timer = QTimer(self)
                self._dir_timer.setSingleShot(True)
                self._dir_timer.setInterval(500)
                self._dir_timer.timeout.connect(self.reload_files)
                self._dir_watcher.directoryChanged.connect(lambda _p: self._dir_timer.start())
            old = self._dir_watcher.directories()
            if old != [folder]:
                if old:
                    self._dir_watcher.removePaths(old)
                if os.path.isdir(folder):
                    self._dir_watcher.addPath(folder)
        except Exception:
            pass

    def refresh_files(self):
        if not hasattr(self, "file_list"):
            return
        folder = self.current_dir()
        self._watch_folder(folder)
        self.lbl_path.setText(folder)
        self.lbl_path.setToolTip(folder)
        self._client_line()
        self.file_list.clear()
        col = self._icon_color() if hasattr(self, "_icon_color") else "#888888"
        try:
            entries = sorted(os.listdir(folder), key=lambda x: x.lower())
        except OSError:
            self.file_list.addItem("нет доступа к папке")
            return
        subdirs = [e for e in entries
                   if os.path.isdir(os.path.join(folder, e)) and not e.startswith(".")]
        exts = (".pdf", ".png", ".jpg", ".jpeg") + AI.OFFICE_EXT
        files = [e for e in entries if e.lower().endswith(exts) and not e.startswith("~$")]
        dark = getattr(self, "theme", "light") == "dark"
        c_pdf = QColor("#F08A99" if dark else "#8E1B2E")       # PDF — бордовым
        c_doc = QColor("#7DB1FF" if dark else "#1B55B8")       # Word — синим
        for d in subdirs:
            it = QListWidgetItem(draw_icon("folder", col), d)
            it.setToolTip(d)
            it.setData(Qt.UserRole, ("dir", os.path.join(folder, d)))
            self.file_list.addItem(it)
        for f in files:
            low = f.lower()
            is_doc = low.endswith(AI.OFFICE_EXT)
            if low.endswith(".pdf"):
                it = QListWidgetItem(draw_icon("pdf", c_pdf.name()), f)
                it.setForeground(c_pdf)
            elif is_doc:
                it = QListWidgetItem(draw_icon("word", c_doc.name()), f)
                it.setForeground(c_doc)
            else:
                it = QListWidgetItem(draw_icon("images", col), f)
            full = os.path.join(folder, f)
            try:
                tip = f"{f}\n{human_size(os.path.getsize(full))}"
                if is_doc:
                    tip += "\nWord: откроется копия для просмотра и проверки ИИ, сам файл не меняется"
                it.setToolTip(tip)
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
                doc = open_pdf_free(path)
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Не удалось открыть PDF:\n{e}")
                return
            self._set_document(doc, path)
        elif path.lower().endswith(AI.OFFICE_EXT):
            self.open_word(path)
        else:
            self._open_image_paths([path])

    def open_word(self, path, quiet=False):
        """Открыть документ Word: в программе появляется его копия-PDF, сам файл не меняется."""
        box = {}

        class _T(QThread):
            def run(self_t):
                try:
                    box["res"] = AI.office_to_pdf(path)
                except Exception as e:
                    box["err"] = str(e)

        th = _T(self)
        prog = QProgressDialog("Открываю документ Word…", None, 0, 0, self)
        prog.setWindowTitle("Word")
        prog.setWindowModality(Qt.WindowModal)
        prog.setMinimumDuration(300)
        prog.setCancelButton(None)
        loop = QEventLoop(self)
        th.finished.connect(loop.quit)
        th.start()
        if th.isRunning():
            loop.exec()
        th.wait()
        prog.close()
        prog.deleteLater()
        if "res" not in box:
            QMessageBox.critical(self, "Word", "Не удалось открыть документ:\n" + box.get("err", "неизвестная ошибка"))
            return
        data, how = box["res"]
        try:
            doc = fitz.open("pdf", data)
        except Exception as e:
            QMessageBox.critical(self, "Word", f"Не удалось открыть документ:\n{e}")
            return
        self._set_document(doc, path + " (из Word)")
        msg = ("Word открыт как копия: можно проверять ИИ, ставить печать и сохранять в PDF. "
               "Править и заполнять — кнопка «Редактор» под списком файлов")
        if how != "word":
            msg += ". Microsoft Word не найден — вид упрощённый, текст полный"
        if not quiet:
            self.show_toast("✔  Word открыт как копия — сам файл не меняется", 3600)
        self.statusBar().showMessage(msg, 10000)

    def trash_selected_file(self):
        item = self.file_list.currentItem()
        data = item.data(Qt.UserRole) if item is not None else None
        if not data:
            self.statusBar().showMessage("Сначала выберите файл в списке", 4000)
            return
        kind, path = data
        if kind != "file":
            self.statusBar().showMessage("Папки удаляются в Проводнике — здесь удаляются только файлы", 6000)
            return
        self.trash_file(path)

    def trash_file(self, path):
        """Удалить файл в корзину Windows, не выходя из программы."""
        name = os.path.basename(path)
        cur = str(self.doc_path or "")
        for tail in (" (из изображений)", " (из Word)"):
            if cur.endswith(tail):
                cur = cur[:-len(tail)]
        is_open = self.doc is not None and os.path.normcase(os.path.abspath(cur)) == os.path.normcase(os.path.abspath(path))
        text = f"Удалить «{name}» в корзину?"
        if is_open:
            text += ("\n\nЭтот файл сейчас открыт в программе — он будет закрыт."
                     + (" Печати на нём не сохранены и пропадут." if self.stamps else ""))
        box = QMessageBox(self)
        box.setWindowTitle("Удалить файл")
        box.setIcon(QMessageBox.Question)
        box.setText(text)
        box.setInformativeText("Из корзины файл можно вернуть.")
        b_yes = box.addButton("Удалить в корзину", QMessageBox.AcceptRole)
        box.addButton("Отмена", QMessageBox.RejectRole)
        box.setDefaultButton(b_yes)
        box.exec()
        if box.clickedButton() is not b_yes:
            return
        if is_open:
            if self.view.pen_active():
                self.pen_finish(commit=False)
            for st in self.stamps:
                self.scene.removeItem(st)
            self.stamps.clear()
            self.close_document()
        row = self.file_list.currentRow()
        ok = False
        try:
            ok = QFile.moveToTrash(path)
        except Exception:
            ok = False
        if not ok or os.path.exists(path):
            QMessageBox.warning(self, "Удалить файл",
                                f"Не получилось удалить «{name}».\n"
                                "Возможно, файл открыт в другой программе — закройте его там и повторите.")
            return
        self.reload_files()
        if self.file_list.count():
            self.file_list.setCurrentRow(min(row, self.file_list.count() - 1))
        self.show_toast(f"✔  «{name}» — в корзине", 3200)

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
            if path.lower().endswith(".docx"):
                menu.addAction(draw_icon("word_edit", self._icon_color()), "Открыть в редакторе Word", lambda: self.word_fill(path))
            menu.addSeparator()
            menu.addAction("Показать метаданные", lambda: self._meta_for_file(path))
            menu.addSeparator()
            menu.addAction(draw_icon("trash", self._icon_color()), "Удалить в корзину\tDel",
                           lambda: self.trash_file(path))
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
            d = open_pdf_free(path)
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


    def place_on_sheet(self):
        """Положить документ нестандартного размера на лист, как на стекло сканера."""
        if self.doc is None:
            QMessageBox.information(self, "Нет документа",
                                    "Сначала откройте PDF, снимок или отсканируйте документ.")
            return
        idx = max(0, self.page_list.currentRow())
        pages = sorted({self.page_list.row(it) for it in self.page_list.selectedItems()}) or [idx]
        if idx not in pages:
            pages = [idx]
        try:
            src = fitz.open("pdf", self._stamped_pdf_bytes(compress={"mode": "none"}))   # печати — вместе с документом
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось подготовить документ:\n{e}")
            return

        def page_image(i, dpi=200):
            pg = src[i]
            long_mm = max(pg.rect.width, pg.rect.height) / MM_TO_PT
            dpi = max(60, min(dpi, int(4200 / max(1.0, long_mm / 25.4))))    # очень большие листы — без гигантских картинок
            pix = pg.get_pixmap(dpi=dpi, alpha=False)
            return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)

        try:
            first = page_image(idx)
            r = src[idx].rect
            dlg = SheetPlaceDialog(first, (r.width / MM_TO_PT, r.height / MM_TO_PT), self, n_pages=len(pages))
        except Exception as e:
            src.close()
            QMessageBox.critical(self, "Ошибка", f"Не получилось открыть страницу:\n{e}")
            return
        if dlg.exec() != QDialog.Accepted:
            src.close()
            return
        t = dlg.template()
        to_new = dlg.rb_new.isChecked()
        sw, sh = t["sheet"]
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            made = {}
            for i in pages:
                im = place_on_sheet(dlg.result_object(first if i == idx else page_image(i)), t, dpi=200)
                buf = io.BytesIO()
                im.save(buf, "JPEG", quality=88, optimize=True)
                made[i] = buf.getvalue()
            new = fitz.open()
            if to_new:
                for i in pages:
                    pg = new.new_page(width=sw * MM_TO_PT, height=sh * MM_TO_PT)
                    pg.insert_image(pg.rect, stream=made[i])
            else:
                for i in range(src.page_count):
                    if i in made:
                        pg = new.new_page(width=sw * MM_TO_PT, height=sh * MM_TO_PT)
                        pg.insert_image(pg.rect, stream=made[i])
                    else:
                        new.insert_pdf(self.doc, from_page=i, to_page=i)
        except Exception as e:
            QApplication.restoreOverrideCursor()
            src.close()
            QMessageBox.critical(self, "Ошибка", f"Не получилось разместить:\n{e}")
            return
        QApplication.restoreOverrideCursor()
        src.close()
        if to_new:
            self._scan_look_save_new(new, len(pages), suffix="на листе")
            return
        n = self.doc.page_count
        self.doc.insert_pdf(new)
        self.doc.delete_pages(0, n - 1)
        new.close()
        for s in list(self.stamps):               # печати с этих страниц уже внутри картинки
            if s.page_index in made:
                try:
                    self.scene.removeItem(s)
                except Exception:
                    pass
                self.stamps.remove(s)
        self.refresh_page_list(idx)
        self.show_page(idx)
        self._update_ui_state()
        self.show_toast(f"✔  Размещено на листе — страниц: {len(pages)}. Сохраните (Ctrl+S)")

    def scan_look(self):
        """Сделать документ «как напечатали и отсканировали»."""
        if self.doc is None:
            QMessageBox.information(self, "Нет документа",
                                    "Сначала откройте PDF или отсканируйте документ.")
            return
        idx = max(0, self.page_list.currentRow())
        try:
            # сначала готовый PDF — ровно как при «Сохранить», без сжатия, — и уже с него «скан»
            src = fitz.open("pdf", self._stamped_pdf_bytes(compress={"mode": "none"}))
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
        if o.get("target") == "new":
            keep = sorted(set(i for i in pages if 0 <= i < new.page_count))
            if keep and len(keep) < new.page_count:
                new.select(keep)                      # в новый файл — только выбранные страницы
            self._scan_look_save_new(new, len(keep) or len(pages))
            return
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


    def _scan_look_save_new(self, new, n_pages, suffix="скан"):
        """Сохранить «скан» отдельным файлом; открытый документ и печати не трогаем."""
        base = os.path.splitext(os.path.basename(str(self.doc_path or "документ")))[0]
        base = base.replace(" (из изображений)", "").replace(" (из Word)", "")
        folder = self.current_dir()
        if self.doc_path and os.path.isfile(str(self.doc_path)):
            folder = os.path.dirname(str(self.doc_path))
        name = f"{base} {suffix}.pdf"
        k = 2
        while os.path.exists(os.path.join(folder, name)):
            name = f"{base} {suffix} {k}.pdf"
            k += 1
        what = "«Скан»" if suffix == "скан" else "Лист"
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить новым файлом",
                                              os.path.join(folder, name), "PDF (*.pdf)")
        if not path:
            new.close()
            self.statusBar().showMessage(f"{what} не сохранён — открытый документ не изменён", 6000)
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        try:
            if self.doc_path and os.path.abspath(path).lower() == os.path.abspath(str(self.doc_path)).lower():
                raise ValueError("это имя открытого документа — выберите другое имя "
                                 "или вариант «В открытый документ»")
            data = new.tobytes(garbage=3, deflate=True)
            new.close()
            write_file_safely(path, data)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить:\n{e}")
            return
        self.reload_files()
        self.show_toast(f"✔  {what} сохранён новым файлом: {os.path.basename(path)} "
                        f"(страниц: {n_pages}). Открытый документ не изменён", 5200)

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
        if self._page_on():
            self.ai_mode(False)
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

    def _esc(self):
        """Esc: выйти из ручки → вернуться со страницы ИИ/Word → снять выделение → закрыть документ."""
        if self.view.pen_active():
            self.pen_finish(False)
            return
        if self._page_on():
            self.ai_mode(False)
            return
        if self.scene.selectedItems():
            self.scene.clearSelection()
            return
        if self.doc is None:
            return
        path = str(self.doc_path or "")
        unsaved = not (path and os.path.isfile(path))
        try:
            unsaved = unsaved or bool(self.doc.is_dirty)
        except Exception:
            pass
        if unsaved and not self.stamps:               # про печати close_document спросит сам
            box = QMessageBox(self)
            box.setWindowTitle("Закрыть документ")
            box.setIcon(QMessageBox.Question)
            box.setText("В документе есть несохранённые изменения.")
            box.setInformativeText("Закрыть без сохранения?")
            b_yes = box.addButton("Закрыть без сохранения", QMessageBox.DestructiveRole)
            b_no = box.addButton("Отмена", QMessageBox.RejectRole)
            box.setDefaultButton(b_no)
            box.exec()
            if box.clickedButton() is not b_yes:
                return
        self.close_document()

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
        self._update_geom_title()
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

    def _update_geom_title(self):
        """В заголовке карточки видно, за какой печатью закрепляется размер."""
        if not hasattr(self, "gb_geom"):
            return
        name = ""
        target = self._lib_target_file()
        if target:
            name = next((e["name"] for e in lib_load() if e.get("file") == target), "")
        if len(name) > 17:
            name = name[:16] + "…"
        self.gb_geom.setTitle(f"Размер — закреплён за «{name}»" if name else "Размер и наклон")
        self.btn_pin.setEnabled(bool(name))

    def pin_stamp_size(self):
        target = self._lib_target_file()
        if not target:
            self.show_toast("Сначала выберите печать в «Моих печатях»")
            return
        self._remember_stamp_now()
        name = next((e["name"] for e in lib_load() if e.get("file") == target), "печать")
        self.show_toast(f"✔  {self.spin_w.value():g}×{self.spin_h.value():g} мм закреплено за «{name}»")

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
        self.gb_geom = gb_geom
        gb_geom.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        gl = QVBoxLayout(gb_geom)
        gl.setContentsMargins(8, 4, 8, 6)
        gl.setSpacing(5)

        self.preset_box = QComboBox()
        self.preset_box.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.preset_box.setMinimumContentsLength(8)
        for name, w, h in PRESETS:
            self.preset_box.addItem(name, (w, h))
        self.preset_box.currentIndexChanged.connect(self.preset_changed)
        self.btn_pin = QPushButton("Закрепить")
        self.btn_pin.setToolTip("Закрепить этот размер, поворот и непрозрачность за выбранной печатью.\n"
                                "В следующий раз она сразу встанет такой. У каждой печати — свои.\n"
                                "Программа делает это и сама, когда вы меняете размер выбранной печати.")
        self.btn_pin.clicked.connect(self.pin_stamp_size)
        gl.addLayout(hrow(cap("Пресет:"), self.preset_box, self.btn_pin))

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
        self.right_dock = dock
        self.addDockWidget(Qt.RightDockWidgetArea, dock)

    def _date_tick(self):
        st = settings_load()
        mode, zone, shift = AI.date_settings(st)
        text = AI.today_text(bool(st.get("date_show_time")))
        how = {"pc": "по часам этого компьютера", "zone": "часовой пояс " + AI.zone_title(zone),
               "manual": "дата задана вручную"}.get(mode, "")
        self.btn_date.setText(f" Сегодня: {text}{' ✎' if mode == 'manual' and shift else ''} ")
        self.btn_date.setToolTip("Эту дату ИИ считает сегодняшней, когда проверяет документ.\n"
                                 f"Сейчас: {how}.\nЩёлкните, чтобы настроить дату и время.")
        c = getattr(self, "_ai_center_dlg", None)
        if c is not None:
            try:
                c.lbl_date.setText("Сегодня: " + AI.today_text())
            except RuntimeError:
                pass

    def _date_menu(self):
        if DateTimeDialog(self).exec() == QDialog.Accepted:
            self._date_tick()

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
        self._fill_btn_state()
        has_stamp = self.stamp_pil is not None
        self.btn_add.setEnabled(has_doc and has_stamp)
        self.btn_save_lib.setEnabled(has_stamp)
        for act in (getattr(self, "act_save", None), getattr(self, "act_png", None),
                    getattr(self, "act_org", None), getattr(self, "act_close", None),
                    getattr(self, "act_save_as", None), getattr(self, "act_pen", None),
                    getattr(self, "act_scanlook", None), getattr(self, "act_sheet", None)):
            if act is not None:
                act.setEnabled(has_doc)
        for act in getattr(self, "_doc_actions", []):
            act.setEnabled(has_doc)
        if hasattr(self, "_ai_center_dlg"):
            self._ai_center_refresh()
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
        self._update_geom_title()
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
                self._update_geom_title()
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
        path, _ = QFileDialog.getOpenFileName(self, "Открыть документ", self.current_dir(),
                                              "PDF и Word (*.pdf *.docx *.doc *.rtf *.odt);;PDF (*.pdf)")
        if not path:
            return
        if path.lower().endswith(AI.OFFICE_EXT):
            self.open_word(path)
            return
        try:
            doc = open_pdf_free(path)
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
            self._update_geom_title()
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
        src_name = src_name.replace(" (из изображений)", "").replace(" (из Word)", "") or "документ"
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
        src_name = src_name.replace(" (из изображений)", "").replace(" (из Word)", "") or "документ"
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
                doc = open_pdf_free(path)
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
                if img[1]:
                    continue      # картинка с прозрачностью (печать, подпись): JPEG дал бы чёрный фон
                try:
                    if src_doc.xref_get_key(xref, "Mask")[0] != "null" \
                            or src_doc.xref_get_key(xref, "ImageMask")[1] == "true":
                        continue
                except Exception:
                    pass
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
                src_doc = open_pdf_free(path)
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
            self.doc = open_pdf_free(out_path)
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
                    f"ai={len(AI.PROVIDERS)} keys={len(AI.builtin_keys())} ocr={AI.selftest_ocr()} word={SW.selftest()} cloud={CLOUD.selftest()} act={'ok' if ACT.selftest() else 'fail'}")
        sys.exit(0)
    win = MainWindow()
    win.show()
    win.place_mascot()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
