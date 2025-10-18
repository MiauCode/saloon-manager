"""
Saloon Manager — A comprehensive management system for saloons with billiards/snooker tables, darts, and inventory management.

Features implemented
--------------------
* Table Management: Start/pause/resume/stop timers for billiards, snooker, and darts
* Live running clocks and session history with pricing
* Player management with member/paying player distinctions
* Inventory Management: Full stock control with storage and front quantities
* Category management for inventory items
* Sales tracking and analytics with best-selling reports
* Low stock alerts and restocking functionality
* Data persistence with JSON files

The code uses **PySide6**. Install with:
    pip install PySide6

Run with:
    python saloon-manager.py
"""
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QTabWidget,
)

# Import our modules
from saloon import SaloonMainWindow, load_tables
from inventory import InventoryWidget


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Saloon Manager")
        
        # Load tables for the saloon module
        self.tables = load_tables()
        
        # Set a light background for the main window
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f8f9fa;
            }
            QTabWidget {
                background-color: #f8f9fa;
            }
            QTabBar::tab {
                background-color: #e9ecef;
                color: #495057;
                border: 1px solid #ced4da;
                padding: 10px 20px;
                margin-right: 2px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                font-weight: bold;
                font-size: 14px;
            }
            QTabBar::tab:selected {
                background-color: #007bff;
                color: white;
                border-bottom: 1px solid #007bff;
            }
            QTabBar::tab:hover:!selected {
                background-color: #dee2e6;
            }
        """)

        # Create tab widget
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        
        # Create Saloon tab
        self.saloon_widget = SaloonMainWindow(self.tables)
        self.tabs.addTab(self.saloon_widget, "🎱 Saloon")
        
        # Create Inventory tab
        self.inventory_widget = InventoryWidget()
        self.tabs.addTab(self.inventory_widget, "📦 Inventory")


def main():
    app = QApplication(sys.argv)
    mw = MainWindow()
    mw.resize(1200, 800)  # Larger size for tabbed interface
    mw.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
