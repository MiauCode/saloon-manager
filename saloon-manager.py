"""
Billiards and darts Manager — a simple desktop GUI application for managing billiards (pool/snooker) tables and darts.

Features implemented
--------------------
* Start / pause / resume / stop timer for every table/board
* Live running clock shown while a table/board is active
* Per-table/board history including start/end times, duration, price charged and membership flag
* Settings dialog to edit table/board name and price per hour
* Membership pricing with configurable discount (default 100% off)
* Data persisted to JSON on shutdown and re-loaded on next start

The code uses **PySide6**. Install with:
    pip install PySide6

Run with:
    python billiards_manager.py
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List

from PySide6.QtCore import QDateTime, QTimer, Qt
from PySide6.QtGui import QAction, QPixmap, QPainter, QFont
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QToolBar,
    QVBoxLayout,
    QWidget,
    QHBoxLayout,
    QDialog,
    QFormLayout,
    QDoubleSpinBox,
    QCheckBox,
    QComboBox,
    QGridLayout,
    QScrollArea,
)

DATA_FILE = Path("tables.json")
MEMBER_DISCOUNT = 0.20  # 20 % off the hourly rate  
SINGLE_PLAYER_MULTIPLIER = 0.5  # 50% discount for single player
TABLE_TYPES = ["Billiard", "Snooker", "Darts"]


@dataclass
class Session:
    start: str
    end: str
    seconds: int
    price: float
    member: bool
    players: int = 2  # Default to 2 players for backward compatibility
    member_players: int = 0  # Number of member players
    paying_players: int = 2  # Number of non-member (paying) players

    @property
    def duration_str(self) -> str:
        mins, sec = divmod(self.seconds, 60)
        hrs, mins = divmod(mins, 60)
        return f"{hrs:02d}:{mins:02d}:{sec:02d}"


@dataclass
class Table:
    name: str
    price_per_hour: float
    table_type: str = "Billiard"  # Default to Billiard
    history: List[Session] = field(default_factory=list)
    start_time: QDateTime | None = None
    paused_seconds: int = 0
    paused: bool = False
    current_players: int = 2  # Current session total player count
    current_member_players: int = 0  # Current session member player count
    current_paying_players: int = 2  # Current session paying player count

    def to_json(self):
        d = asdict(self)
        d["history"] = [asdict(s) for s in self.history]
        d.pop("start_time")  # not serialisable
        d.pop("current_players")  # runtime only
        d.pop("current_member_players")  # runtime only
        d.pop("current_paying_players")  # runtime only
        return d

    @classmethod
    def from_json(cls, d):
        history = []
        for s in d.get("history", []):
            # Handle backward compatibility for sessions without new fields
            session_data = s.copy()
            if "players" not in session_data:
                session_data["players"] = 2
            if "member_players" not in session_data:
                session_data["member_players"] = 2 if session_data.get("member", False) else 0
            if "paying_players" not in session_data:
                session_data["paying_players"] = 0 if session_data.get("member", False) else 2
            history.append(Session(**session_data))
        return cls(
            name=d["name"], 
            price_per_hour=d["price_per_hour"], 
            table_type=d.get("table_type", "Billiard"),  # Default to Billiard for backward compatibility
            history=history
        )

    def is_running(self) -> bool:
        return self.start_time is not None and not self.paused

    def start(self, member_players: int = 0, paying_players: int = 2):
        if self.start_time is None:
            self.start_time = QDateTime.currentDateTime()
            self.paused_seconds = 0
            self.paused = False
            self.current_players = member_players + paying_players
            self.current_member_players = member_players
            self.current_paying_players = paying_players

    def pause(self):
        if self.start_time and not self.paused:
            now = QDateTime.currentDateTime()
            self.paused_seconds += self.start_time.secsTo(now)
            self.start_time = None
            self.paused = True

    def resume(self):
        if self.paused:
            self.start_time = QDateTime.currentDateTime()
            self.paused = False

    def stop(self) -> Session:
        if not self.start_time and not self.paused:
            raise RuntimeError("Timer not running")
        end_time = QDateTime.currentDateTime()
        if self.paused:
            total_secs = self.paused_seconds
        else:
            total_secs = self.paused_seconds + self.start_time.secsTo(end_time)

        # Calculate price based on paying players count
        if self.current_paying_players == 0:
            price = 0.0  # Free if no paying players (all members)
        else:
            total_cost = (total_secs / 3600) * self.price_per_hour
            if self.current_paying_players == 1:
                # Single paying player gets discount
                price = total_cost * SINGLE_PLAYER_MULTIPLIER
            else:
                # Multiple paying players split the cost
                price = total_cost / self.current_paying_players

        session = Session(
            start=(self.start_time or end_time).addSecs(-total_secs).toString(Qt.ISODate),
            end=end_time.toString(Qt.ISODate),
            seconds=total_secs,
            price=round(price, 2),
            member=self.current_member_players > 0,  # True if any members
            players=self.current_players,
            member_players=self.current_member_players,
            paying_players=self.current_paying_players,
        )
        self.history.append(session)
        self.start_time = None
        self.paused = False
        self.paused_seconds = 0
        self.current_players = 2
        self.current_member_players = 0
        self.current_paying_players = 2
        return session


class TableWidget(QWidget):
    def __init__(self, table: Table, parent=None):
        super().__init__(parent)
        self.table = table
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.update_clock)
        self.controls_visible = False

        # Set fixed size for the widget
        self.setFixedSize(200, 430)  # Increased height from 320 to 360 for even more button space
        
        # Apply card-like styling to the widget
        self.setStyleSheet("""
            TableWidget {
                background-color: #ffffff;
                border: 2px solid #d1d5db;
                border-radius: 12px;
                margin: 5px;
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            }
            TableWidget:hover {
                border: 2px solid #3b82f6;
                box-shadow: 0 8px 16px rgba(0, 0, 0, 0.15);
                background-color: #ffffff;
                transform: translateY(-2px);
            }
        """)
        
        # Main layout
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 12, 12, 12)

        # Table image (clickable) - ensure proper stacking order
        self.image_label = QLabel()
        self.image_label.setFixedSize(176, 120)
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.raise_()  # Ensure image stays on top
        self.image_label.setStyleSheet("""
            QLabel {
                border: 2px solid #e5e7eb;
                border-radius: 8px;
                background-color: #f9fafb;
                padding: 4px;
            }
            QLabel:hover {
                border: 2px solid #3b82f6;
                background-color: #eff6ff;
            }
        """)
        self.image_label.mousePressEvent = self.toggle_controls
        self.load_table_image()
        layout.addWidget(self.image_label)

        # Table name
        self.name_lbl = QLabel(table.name)
        self.name_lbl.setAlignment(Qt.AlignCenter)
        self.name_lbl.setStyleSheet("""
            QLabel {
                font-weight: bold;
                font-size: 16px;
                color: #2c3e50;
                background-color: transparent;
                padding: 4px;
                margin: 2px 0px;
                border: none;
            }
        """)
        layout.addWidget(self.name_lbl)

        # Member status label (initially hidden)
        self.member_lbl = QLabel("MEMBER - FREE PLAY")
        self.member_lbl.setAlignment(Qt.AlignCenter)
        self.member_lbl.setStyleSheet("""
            QLabel {
                font-weight: bold;
                font-size: 11px;
                color: #ffffff;
                background-color: #28a745;
                padding: 4px 8px;
                border-radius: 6px;
                margin: 2px 0px;
            }
        """)
        self.member_lbl.hide()  # Initially hidden
        layout.addWidget(self.member_lbl)

        # Clock display
        self.clock_lbl = QLabel("00:00:00")
        self.clock_lbl.setAlignment(Qt.AlignCenter)
        self.clock_lbl.setStyleSheet("""
            QLabel {
                font-size: 18px;
                font-weight: bold;
                color: #495057;
                background-color: #e9ecef;
                border: 1px solid #ced4da;
                border-radius: 6px;
                padding: 6px;
                margin: 2px 0px;
            }
        """)
        layout.addWidget(self.clock_lbl)

        # Controls container (initially hidden)
        self.controls_widget = QWidget()
        self.controls_widget.setStyleSheet("""
            QPushButton {
                background-color: #007bff;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 10px 14px;
                font-weight: bold;
                font-size: 12px;
                min-height: 32px;
                margin: 2px;
            }
            QPushButton:hover {
                background-color: #0056b3;
            }
            QPushButton:pressed {
                background-color: #004085;
            }
            QPushButton:disabled {
                background-color: #6c757d;
                color: #dee2e6;
            }
        """)
        controls_layout = QVBoxLayout(self.controls_widget)
        controls_layout.setContentsMargins(0, 0, 0, 0)

        # Button layout (2x2 grid)
        btn_layout = QGridLayout()
        btn_layout.setSpacing(8)  # Increased from 5 to 8 for even more space
        btn_layout.setContentsMargins(4, 4, 4, 4)  # Add margins around the grid
        
        self.start_btn = QPushButton("Start")
        self.start_btn.setStyleSheet("QPushButton { background-color: #28a745; } QPushButton:hover { background-color: #1e7e34; }")
        self.start_btn.clicked.connect(self.start_timer)
        
        self.pause_btn = QPushButton("Pause")
        self.pause_btn.setStyleSheet("QPushButton { background-color: #ffc107; color: #212529; } QPushButton:hover { background-color: #e0a800; }")
        self.pause_btn.clicked.connect(self.pause_timer)
        
        self.resume_btn = QPushButton("Resume")
        self.resume_btn.setStyleSheet("QPushButton { background-color: #17a2b8; } QPushButton:hover { background-color: #117a8b; }")
        self.resume_btn.clicked.connect(self.resume_timer)
        
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setStyleSheet("QPushButton { background-color: #dc3545; } QPushButton:hover { background-color: #c82333; }")
        self.stop_btn.clicked.connect(self.stop_timer)
        
        btn_layout.addWidget(self.start_btn, 0, 0)
        btn_layout.addWidget(self.pause_btn, 0, 1)
        btn_layout.addWidget(self.resume_btn, 1, 0)
        btn_layout.addWidget(self.stop_btn, 1, 1)
        
        controls_layout.addLayout(btn_layout)

        # Add more spacing between button groups
        controls_layout.addSpacing(12)

        # Settings and History buttons
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(6)  # Add spacing between history and settings buttons
        self.hist_btn = QPushButton("History")
        self.hist_btn.setStyleSheet("QPushButton { background-color: #6c757d; } QPushButton:hover { background-color: #5a6268; }")
        self.hist_btn.clicked.connect(self.show_history)
        
        self.set_btn = QPushButton("Settings")
        self.set_btn.setStyleSheet("QPushButton { background-color: #6c757d; } QPushButton:hover { background-color: #5a6268; }")
        self.set_btn.clicked.connect(self.show_settings)
        
        bottom_layout.addWidget(self.hist_btn)
        bottom_layout.addWidget(self.set_btn)
        controls_layout.addLayout(bottom_layout)

        layout.addWidget(self.controls_widget)
        
        # Initially hide controls
        self.controls_widget.hide()

        # Update UI state
        self.update_button_states()
        
        if self.table.is_running():
            self.timer.start()
            self.update_clock()
            # Show member label if current session has member players
            if self.table.current_member_players > 0:
                self.member_lbl.show()
            # Show controls if table is already running
            if not self.controls_visible:
                self.toggle_controls(None)

    def toggle_controls(self, event):
        """Toggle visibility of control buttons when image is clicked"""
        self.controls_visible = not self.controls_visible
        if self.controls_visible:
            self.controls_widget.show()
            self.image_label.setStyleSheet("""
                QLabel {
                    border: 3px solid #3b82f6;
                    border-radius: 8px;
                    background-color: #dbeafe;
                    padding: 4px;
                    box-shadow: 0 0 0 1px rgba(59, 130, 246, 0.1);
                }
                QLabel:hover {
                    border: 3px solid #2563eb;
                    background-color: #bfdbfe;
                }
            """)
        else:
            self.controls_widget.hide()
            self.image_label.setStyleSheet("""
                QLabel {
                    border: 2px solid #e5e7eb;
                    border-radius: 8px;
                    background-color: #f9fafb;
                    padding: 4px;
                }
                QLabel:hover {
                    border: 2px solid #3b82f6;
                    background-color: #eff6ff;
                }
            """)

    def load_table_image(self):
        """Load the appropriate image for the table type, or create a placeholder"""
        image_path = f"graphics/{self.table.table_type.lower()}.png"
        pixmap = QPixmap(image_path)
        
        if pixmap.isNull():
            # Create a placeholder image if the file doesn't exist
            pixmap = QPixmap(180, 120)
            pixmap.fill(Qt.lightGray)
            
            # Draw placeholder text
            painter = QPainter(pixmap)
            painter.setPen(Qt.black)
            painter.setFont(QFont("Arial", 12, QFont.Bold))
            painter.drawText(pixmap.rect(), Qt.AlignCenter, self.table.table_type)
            painter.end()
        else:
            # Scale the image to fit
            pixmap = pixmap.scaled(180, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        
        self.image_label.setPixmap(pixmap)

    def update_button_states(self):
        """Update button enabled/disabled states based on table status"""
        is_running = self.table.is_running()
        is_paused = self.table.paused
        has_session = self.table.start_time is not None or self.table.paused
        
        self.start_btn.setEnabled(not has_session)
        self.pause_btn.setEnabled(is_running)
        self.resume_btn.setEnabled(is_paused)
        self.stop_btn.setEnabled(has_session)

    def start_timer(self):
        # Ask for player information before starting
        member_players, paying_players = self.ask_player_info()
        if member_players is not None:  # User didn't cancel
            self.table.start(member_players, paying_players)
            self.timer.start()
            self.update_button_states()
            
            # Show/hide member status
            if member_players > 0:
                self.member_lbl.show()
            else:
                self.member_lbl.hide()
            
            # Keep controls visible when timer is active
            if not self.controls_visible:
                self.toggle_controls(None)

    def pause_timer(self):
        self.table.pause()
        self.timer.stop()
        self.update_button_states()

    def resume_timer(self):
        self.table.resume()
        self.timer.start()
        self.update_button_states()

    def stop_timer(self):
        session = self.table.stop()
        self.timer.stop()
        self.clock_lbl.setText("00:00:00")
        self.member_lbl.hide()  # Hide member label when session ends
        self.update_button_states()
        
        # Show session summary with detailed player and pricing info
        total_players = session.member_players + session.paying_players
        player_text = f"{total_players} players"
        if session.member_players > 0 and session.paying_players > 0:
            detail_text = f" ({session.member_players} members + {session.paying_players} paying)"
        elif session.member_players > 0:
            detail_text = f" (all members)"
        else:
            detail_text = f" (all paying)"
        
        if session.price == 0:
            price_text = "Free"
        else:
            # Calculate total amount
            total_amount = session.price * session.paying_players
            if session.paying_players == 1:
                price_text = f"€{session.price:.2f} total (single player discount)"
            else:
                price_text = f"€{session.price:.2f} per paying player (€{total_amount:.2f} total)"
        
        QMessageBox.information(
            self,
            "Session ended",
            f"Duration: {session.duration_str}\n"
            f"Players: {player_text}{detail_text}\n"
            f"Price: {price_text}",
        )

    def ask_player_info(self):
        """Ask for number of member and paying players before starting"""
        dlg = QDialog(self)
        dlg.setWindowTitle("Start Session")
        dlg.setModal(True)
        
        form = QFormLayout(dlg)
        
        # Member player count selection
        member_spin = QSpinBox()
        member_spin.setRange(0, 8)  # Allow 0-8 member players
        member_spin.setValue(0)  # Default to 0 member players
        member_spin.setSuffix(" member players")
        form.addRow("Member players:", member_spin)
        
        # Paying player count selection
        paying_spin = QSpinBox()
        paying_spin.setRange(0, 8)  # Allow 0-8 paying players
        paying_spin.setValue(2)  # Default to 2 paying players
        paying_spin.setSuffix(" paying players")
        form.addRow("Paying players:", paying_spin)
        
        # Total player display
        total_label = QLabel("Total: 2 players")
        total_label.setStyleSheet("font-weight: bold; color: #2c3e50;")
        form.addRow("", total_label)
        
        def update_total():
            total = member_spin.value() + paying_spin.value()
            total_label.setText(f"Total: {total} players")
            start_btn.setEnabled(total > 0)  # At least 1 player required
        
        member_spin.valueChanged.connect(update_total)
        paying_spin.valueChanged.connect(update_total)
        
        # Pricing info
        info_label = QLabel(
            f"Pricing per paying player:\n"
            f"• Members: Always free\n"
            f"• 1 paying player: {int(SINGLE_PLAYER_MULTIPLIER * 100)}% of total cost\n"
            f"• 2+ paying players: Total cost divided equally"
        )
        info_label.setStyleSheet("color: #666; font-size: 10px;")
        form.addRow(info_label)
        
        # Buttons
        btn_layout = QHBoxLayout()
        start_btn = QPushButton("Start")
        cancel_btn = QPushButton("Cancel")
        btn_layout.addWidget(start_btn)
        btn_layout.addWidget(cancel_btn)
        form.addRow(btn_layout)
        
        start_btn.clicked.connect(dlg.accept)
        cancel_btn.clicked.connect(dlg.reject)
        
        # Set default button
        start_btn.setDefault(True)
        
        # Initial update
        update_total()
        
        if dlg.exec():
            return member_spin.value(), paying_spin.value()
        else:
            return None, None  # User cancelled

    def update_clock(self):
        if self.table.start_time:
            elapsed = self.table.start_time.secsTo(QDateTime.currentDateTime()) + self.table.paused_seconds
        else:
            elapsed = self.table.paused_seconds
        mins, sec = divmod(elapsed, 60)
        hrs, mins = divmod(mins, 60)
        self.clock_lbl.setText(f"{hrs:02d}:{mins:02d}:{sec:02d}")

    def show_history(self):
        dlg = QDialog(self)
        dlg.setWindowTitle(f"History — {self.table.name}")
        vbox = QVBoxLayout(dlg)
        listw = QListWidget()
        for s in self.table.history:
            # Handle both old and new session formats
            if hasattr(s, 'member_players') and hasattr(s, 'paying_players'):
                total_players = s.member_players + s.paying_players
                if s.member_players > 0 and s.paying_players > 0:
                    player_text = f"{total_players}P ({s.member_players}M+{s.paying_players}$)"
                elif s.member_players > 0:
                    player_text = f"{total_players}P (all M)"
                else:
                    player_text = f"{total_players}P (all $)"
            else:
                # Old format fallback
                player_text = f"{s.players}P" if hasattr(s, 'players') else "2P"
                if s.member:
                    player_text += " (M)"
            
            if s.price == 0:
                price_text = "Free"
            else:
                # Calculate and show total amount
                if hasattr(s, 'paying_players') and s.paying_players > 0:
                    total_amount = s.price * s.paying_players
                    if s.paying_players == 1:
                        price_text = f"€{s.price:.2f} total"
                    else:
                        price_text = f"€{s.price:.2f}/player (€{total_amount:.2f} total)"
                else:
                    # Old format or single total price
                    price_text = f"€{s.price:.2f}"
                
            item = QListWidgetItem(
                f"{s.start} → {s.end}  |  {s.duration_str}  |  {player_text}  |  {price_text}"
            )
            listw.addItem(item)
        vbox.addWidget(listw)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dlg.accept)
        vbox.addWidget(close_btn)
        dlg.resize(800, 400)  # Slightly wider for longer text
        dlg.exec()

    def show_settings(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Table settings")
        form = QFormLayout(dlg)
        
        name_edit = QLineEdit(self.table.name)
        
        rate_spin = QDoubleSpinBox()
        rate_spin.setRange(0.0, 100.0)
        rate_spin.setSuffix(" €/h")
        rate_spin.setValue(self.table.price_per_hour)
        
        # Table type selection
        type_combo = QComboBox()
        type_combo.addItems(TABLE_TYPES)
        type_combo.setCurrentText(self.table.table_type)
        
        form.addRow("Name", name_edit)
        form.addRow("Rate", rate_spin)
        form.addRow("Table Type", type_combo)
        
        member_discount_lbl = QLabel(
            f"Pricing per paying player:\n"
            f"• Members: Always free\n"
            f"• 1 paying player: {int(SINGLE_PLAYER_MULTIPLIER*100)}% of total cost\n"
            f"• 2+ paying players: Total cost divided equally"
        )
        member_discount_lbl.setStyleSheet("color: #666;")
        form.addRow(member_discount_lbl)
        
        btn_box = QHBoxLayout()
        ok_btn = QPushButton("OK")
        cancel_btn = QPushButton("Cancel")
        delete_btn = QPushButton("Delete Table")
        delete_btn.setStyleSheet("background-color: #e74c3c; color: white; font-weight: bold;")
        
        btn_box.addWidget(ok_btn)
        btn_box.addWidget(cancel_btn)
        btn_box.addWidget(delete_btn)
        form.addRow(btn_box)

        ok_btn.clicked.connect(dlg.accept)
        cancel_btn.clicked.connect(dlg.reject)
        
        def delete_table():
            # Ask for confirmation
            reply = QMessageBox.question(
                dlg,
                "Delete Table",
                f"Are you sure you want to delete '{self.table.name}'?\n\nThis will permanently remove the table and all its history.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                dlg.done(2)  # Custom result code for delete
        
        delete_btn.clicked.connect(delete_table)

        result = dlg.exec()
        if result == 1:  # OK button (accept)
            self.table.name = name_edit.text() or self.table.name
            self.table.price_per_hour = rate_spin.value()
            old_type = self.table.table_type
            self.table.table_type = type_combo.currentText()
            
            # Update UI
            self.name_lbl.setText(self.table.name)
            if old_type != self.table.table_type:
                self.load_table_image()  # Reload image if type changed
        elif result == 2:  # Delete button
            # Find parent MainWindow and remove this table
            parent_window = self.parent()
            while parent_window and not isinstance(parent_window, MainWindow):
                parent_window = parent_window.parent()
            
            if parent_window:
                parent_window.delete_table(self.table)


class MainWindow(QMainWindow):
    def __init__(self, tables: List[Table]):
        super().__init__()
        self.setWindowTitle("Billiards Manager")
        self.tables = tables
        


        tb = QToolBar()
        tb.setStyleSheet("""
            QToolBar {
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                padding: 8px;
                spacing: 8px;
            }
            QToolBar QToolButton {
                background-color: #007bff;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 10px 20px;
                font-weight: bold;
                font-size: 14px;
                min-width: 100px;
                margin: 2px;
            }
            QToolBar QToolButton:hover {
                background-color: #0056b3;
                transform: translateY(-1px);
            }
            QToolBar QToolButton:pressed {
                background-color: #004085;
                transform: translateY(0px);
            }
        """)
        self.addToolBar(tb)
        
        add_act = QAction("➕ Add Table", self)
        add_act.triggered.connect(self.add_table)
        save_act = QAction("💾 Save", self)
        save_act.triggered.connect(self.save_data)
        tb.addAction(add_act)
        tb.addAction(save_act)

        self.container = QWidget()
        self.setCentralWidget(self.container)
        self.main_layout = QVBoxLayout(self.container)
        self.main_layout.setContentsMargins(20, 20, 20, 20)
        
        # Create a scroll area for the tables
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_widget = QWidget()
        self.grid_layout = QGridLayout(self.scroll_widget)
        self.grid_layout.setSpacing(20)  # More spacing between cards
        self.scroll_area.setWidget(self.scroll_widget)
        self.main_layout.addWidget(self.scroll_area)
        
        self.refresh_ui()

    def refresh_ui(self):
        # Clear existing widgets
        while self.grid_layout.count():
            child = self.grid_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        
        # Add tables in a grid layout (3 columns)
        columns = 3
        for i, table in enumerate(self.tables):
            row = i // columns
            col = i % columns
            table_widget = TableWidget(table)
            self.grid_layout.addWidget(table_widget, row, col)
        
        # Add stretch to push everything to the top
        self.grid_layout.setRowStretch(len(self.tables) // columns + 1, 1)

    def add_table(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("New table")
        form = QFormLayout(dlg)
        
        name_edit = QLineEdit()
        
        rate_spin = QDoubleSpinBox()
        rate_spin.setRange(0.0, 100.0)
        rate_spin.setSuffix(" €/h")
        rate_spin.setValue(10.0)
        
        # Table type selection
        type_combo = QComboBox()
        type_combo.addItems(TABLE_TYPES)
        type_combo.setCurrentText("Billiard")  # Default selection
        
        form.addRow("Name", name_edit)
        form.addRow("Rate", rate_spin)
        form.addRow("Table Type", type_combo)
        
        btn_box = QHBoxLayout()
        ok_btn = QPushButton("Add")
        cancel_btn = QPushButton("Cancel")
        btn_box.addWidget(ok_btn)
        btn_box.addWidget(cancel_btn)
        form.addRow(btn_box)

        ok_btn.clicked.connect(dlg.accept)
        cancel_btn.clicked.connect(dlg.reject)

        if dlg.exec():
            table = Table(
                name=name_edit.text() or "Table", 
                price_per_hour=rate_spin.value(),
                table_type=type_combo.currentText()
            )
            self.tables.append(table)
            self.refresh_ui()

    def delete_table(self, table_to_delete: Table):
        """Delete a table from the list and refresh the UI"""
        if table_to_delete in self.tables:
            self.tables.remove(table_to_delete)
            self.refresh_ui()
            QMessageBox.information(self, "Table Deleted", f"Table '{table_to_delete.name}' has been deleted.")

    def closeEvent(self, e):
        self.save_data()
        super().closeEvent(e)

    def save_data(self):
        try:
            data = [t.to_json() for t in self.tables]
            DATA_FILE.write_text(json.dumps(data, indent=2))
            QMessageBox.information(self, "Saved", "Data saved successfully.")
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Failed to save: {exc}")


def load_tables() -> List[Table]:
    if DATA_FILE.exists():
        try:
            data = json.loads(DATA_FILE.read_text())
            return [Table.from_json(d) for d in data]
        except Exception:
            pass
    return [
        Table("Table 1", 10.0, "Billiard"), 
        Table("Table 2", 10.0, "Snooker"),
        Table("Table 3", 10.0, "Darts")
    ]


def main():
    app = QApplication(sys.argv)
    mw = MainWindow(load_tables())
    mw.resize(1050, 700)  # Smaller size since controls are hidden by default
    mw.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
