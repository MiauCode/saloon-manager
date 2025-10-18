"""
Inventory Management Module - Handles stock management, categories, and sales analytics.

This module contains all inventory-related functionality including item management,
category management, stock tracking (storage and front), and sales analytics.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional
from collections import defaultdict

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
    QHBoxLayout,
    QDialog,
    QFormLayout,
    QDoubleSpinBox,
    QComboBox,
    QGridLayout,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QDateEdit,
    QTextEdit,
    QGroupBox,
    QScrollArea,
)

INVENTORY_DATA_FILE = Path("inventory.json")
SALES_DATA_FILE = Path("sales.json")
DEFAULT_CATEGORIES = ["Drinks", "Food"]


@dataclass
class Category:
    name: str
    description: str = ""

    def to_json(self):
        return asdict(self)

    @classmethod
    def from_json(cls, data):
        return cls(**data)


@dataclass
class InventoryItem:
    name: str
    category: str
    storage_quantity: int = 0
    front_quantity: int = 0
    price: float = 0.0
    cost: float = 0.0
    description: str = ""
    barcode: str = ""
    min_stock_level: int = 5

    def to_json(self):
        return asdict(self)

    @classmethod
    def from_json(cls, data):
        return cls(**data)

    @property
    def total_quantity(self):
        return self.storage_quantity + self.front_quantity

    @property
    def is_low_stock(self):
        return self.total_quantity <= self.min_stock_level


@dataclass
class SaleItem:
    item_name: str
    category: str
    quantity: int
    price: float
    total: float
    timestamp: str

    def to_json(self):
        return asdict(self)

    @classmethod
    def from_json(cls, data):
        return cls(**data)


@dataclass
class Sale:
    id: str
    items: List[SaleItem]
    total_amount: float
    timestamp: str
    payment_method: str = "cash"

    def to_json(self):
        return {
            "id": self.id,
            "items": [item.to_json() for item in self.items],
            "total_amount": self.total_amount,
            "timestamp": self.timestamp,
            "payment_method": self.payment_method
        }

    @classmethod
    def from_json(cls, data):
        items = [SaleItem.from_json(item) for item in data["items"]]
        return cls(
            id=data["id"],
            items=items,
            total_amount=data["total_amount"],
            timestamp=data["timestamp"],
            payment_method=data.get("payment_method", "cash")
        )


class InventoryWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.categories = []
        self.items = []
        self.sales = []
        
        self.load_data()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # Create tab widget
        self.tab_widget = QTabWidget()
        
        # Add tabs
        self.tab_widget.addTab(self.create_items_tab(), "📦 Items")
        self.tab_widget.addTab(self.create_categories_tab(), "🏷️ Categories")
        self.tab_widget.addTab(self.create_stock_tab(), "📊 Stock Management")
        self.tab_widget.addTab(self.create_sales_tab(), "💰 Sales")
        self.tab_widget.addTab(self.create_analytics_tab(), "📈 Analytics")
        
        layout.addWidget(self.tab_widget)

    def create_items_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Header with add button
        header = QHBoxLayout()
        header.addWidget(QLabel("Inventory Items"))
        header.addStretch()
        
        add_btn = QPushButton("➕ Add Item")
        add_btn.clicked.connect(self.add_item)
        header.addWidget(add_btn)
        
        layout.addLayout(header)
        
        # Items table
        self.items_table = QTableWidget()
        self.items_table.setColumnCount(8)
        self.items_table.setHorizontalHeaderLabels([
            "Name", "Category", "Storage", "Front", "Total", "Price", "Low Stock", "Actions"
        ])
        
        # Make table stretch to fill space
        self.items_table.horizontalHeader().setStretchLastSection(True)
        
        layout.addWidget(self.items_table)
        
        self.refresh_items_table()
        
        return widget

    def create_categories_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Header with add button
        header = QHBoxLayout()
        header.addWidget(QLabel("Categories"))
        header.addStretch()
        
        add_btn = QPushButton("➕ Add Category")
        add_btn.clicked.connect(self.add_category)
        header.addWidget(add_btn)
        
        layout.addLayout(header)
        
        # Categories list
        self.categories_list = QListWidget()
        layout.addWidget(self.categories_list)
        
        self.refresh_categories_list()
        
        return widget

    def create_stock_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Explanation section
        explanation = QLabel(
            "<b>How Stock Management Works:</b><br>"
            "• <b>Storage:</b> Items in the back storage area<br>"
            "• <b>Front:</b> Items displayed for sale to customers<br>"
            "• <b>Restock Front:</b> When you restock the front, it assumes the previous front items were sold and records them as sales<br>"
            "• <b>Restock Storage:</b> Add new inventory to storage from suppliers"
        )
        explanation.setStyleSheet("""
            QLabel {
                background-color: #e3f2fd;
                border: 1px solid #2196f3;
                border-radius: 6px;
                padding: 10px;
                margin: 5px 0px;
                color: #1565c0;
            }
        """)
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        
        # Quick actions
        actions_group = QGroupBox("Quick Actions")
        actions_layout = QHBoxLayout(actions_group)
        
        restock_front_btn = QPushButton("� Restock Front (Record Sales)")
        restock_front_btn.clicked.connect(self.move_to_front)
        actions_layout.addWidget(restock_front_btn)
        
        restock_btn = QPushButton("📥 Restock")
        restock_btn.clicked.connect(self.restock_items)
        actions_layout.addWidget(restock_btn)
        
        layout.addWidget(actions_group)
        
        # Low stock alerts
        alerts_group = QGroupBox("Low Stock Alerts")
        alerts_layout = QVBoxLayout(alerts_group)
        
        self.low_stock_list = QListWidget()
        alerts_layout.addWidget(self.low_stock_list)
        
        layout.addWidget(alerts_group)
        
        self.refresh_low_stock_alerts()
        
        return widget

    def create_sales_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Header with sell button
        header = QHBoxLayout()
        header.addWidget(QLabel("Sales Management"))
        header.addStretch()
        
        sell_btn = QPushButton("💰 New Sale")
        sell_btn.clicked.connect(self.new_sale)
        header.addWidget(sell_btn)
        
        layout.addLayout(header)
        
        # Sales table
        self.sales_table = QTableWidget()
        self.sales_table.setColumnCount(5)
        self.sales_table.setHorizontalHeaderLabels([
            "Sale ID", "Date", "Items", "Total", "Payment"
        ])
        
        layout.addWidget(self.sales_table)
        
        self.refresh_sales_table()
        
        return widget

    def create_analytics_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Time period selector
        period_group = QGroupBox("Analytics Period")
        period_layout = QHBoxLayout(period_group)
        
        self.period_combo = QComboBox()
        self.period_combo.addItems(["This Week", "This Month", "All Time", "Custom Range"])
        self.period_combo.currentTextChanged.connect(self.update_analytics)
        period_layout.addWidget(self.period_combo)
        
        # Custom date range (initially hidden)
        self.date_from = QDateEdit()
        self.date_to = QDateEdit()
        self.date_from.setDate(datetime.now().date() - timedelta(days=30))
        self.date_to.setDate(datetime.now().date())
        
        period_layout.addWidget(QLabel("From:"))
        period_layout.addWidget(self.date_from)
        period_layout.addWidget(QLabel("To:"))
        period_layout.addWidget(self.date_to)
        
        # Initially hide custom date inputs
        self.date_from.hide()
        self.date_to.hide()
        
        layout.addWidget(period_group)
        
        # Analytics display
        self.analytics_text = QTextEdit()
        self.analytics_text.setReadOnly(True)
        layout.addWidget(self.analytics_text)
        
        self.update_analytics()
        
        return widget

    def load_data(self):
        """Load inventory and sales data from JSON files"""
        # Load categories
        try:
            if INVENTORY_DATA_FILE.exists():
                data = json.loads(INVENTORY_DATA_FILE.read_text())
                self.categories = [Category.from_json(cat) for cat in data.get("categories", [])]
                self.items = [InventoryItem.from_json(item) for item in data.get("items", [])]
            else:
                # Create default categories
                self.categories = [Category(name) for name in DEFAULT_CATEGORIES]
                self.items = []
        except Exception:
            self.categories = [Category(name) for name in DEFAULT_CATEGORIES]
            self.items = []

        # Load sales
        try:
            if SALES_DATA_FILE.exists():
                data = json.loads(SALES_DATA_FILE.read_text())
                self.sales = [Sale.from_json(sale) for sale in data.get("sales", [])]
            else:
                self.sales = []
        except Exception:
            self.sales = []

    def save_data(self):
        """Save inventory and sales data to JSON files"""
        try:
            # Save inventory data
            inventory_data = {
                "categories": [cat.to_json() for cat in self.categories],
                "items": [item.to_json() for item in self.items]
            }
            INVENTORY_DATA_FILE.write_text(json.dumps(inventory_data, indent=2))
            
            # Save sales data
            sales_data = {
                "sales": [sale.to_json() for sale in self.sales]
            }
            SALES_DATA_FILE.write_text(json.dumps(sales_data, indent=2))
            
            return True
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save data: {e}")
            return False

    def add_category(self):
        """Add a new category"""
        dlg = QDialog(self)
        dlg.setWindowTitle("Add Category")
        layout = QFormLayout(dlg)
        
        name_edit = QLineEdit()
        desc_edit = QLineEdit()
        
        layout.addRow("Name:", name_edit)
        layout.addRow("Description:", desc_edit)
        
        buttons = QHBoxLayout()
        ok_btn = QPushButton("Add")
        cancel_btn = QPushButton("Cancel")
        buttons.addWidget(ok_btn)
        buttons.addWidget(cancel_btn)
        layout.addRow(buttons)
        
        ok_btn.clicked.connect(dlg.accept)
        cancel_btn.clicked.connect(dlg.reject)
        
        if dlg.exec() and name_edit.text().strip():
            category = Category(name_edit.text().strip(), desc_edit.text().strip())
            self.categories.append(category)
            self.save_data()
            self.refresh_categories_list()

    def add_item(self):
        """Add a new inventory item"""
        if not self.categories:
            QMessageBox.warning(self, "No Categories", "Please create at least one category first.")
            return
            
        dlg = QDialog(self)
        dlg.setWindowTitle("Add Item")
        layout = QFormLayout(dlg)
        
        name_edit = QLineEdit()
        category_combo = QComboBox()
        category_combo.addItems([cat.name for cat in self.categories])
        
        storage_spin = QSpinBox()
        storage_spin.setRange(0, 9999)
        
        front_spin = QSpinBox()
        front_spin.setRange(0, 9999)
        
        price_spin = QDoubleSpinBox()
        price_spin.setRange(0.0, 9999.99)
        price_spin.setSuffix(" €")
        
        cost_spin = QDoubleSpinBox()
        cost_spin.setRange(0.0, 9999.99)
        cost_spin.setSuffix(" €")
        
        min_stock_spin = QSpinBox()
        min_stock_spin.setRange(0, 999)
        min_stock_spin.setValue(5)
        
        desc_edit = QLineEdit()
        barcode_edit = QLineEdit()
        
        layout.addRow("Name:", name_edit)
        layout.addRow("Category:", category_combo)
        layout.addRow("Storage Quantity:", storage_spin)
        layout.addRow("Front Quantity:", front_spin)
        layout.addRow("Selling Price:", price_spin)
        layout.addRow("Cost Price:", cost_spin)
        layout.addRow("Min Stock Level:", min_stock_spin)
        layout.addRow("Description:", desc_edit)
        layout.addRow("Barcode:", barcode_edit)
        
        buttons = QHBoxLayout()
        ok_btn = QPushButton("Add")
        cancel_btn = QPushButton("Cancel")
        buttons.addWidget(ok_btn)
        buttons.addWidget(cancel_btn)
        layout.addRow(buttons)
        
        ok_btn.clicked.connect(dlg.accept)
        cancel_btn.clicked.connect(dlg.reject)
        
        if dlg.exec() and name_edit.text().strip():
            item = InventoryItem(
                name=name_edit.text().strip(),
                category=category_combo.currentText(),
                storage_quantity=storage_spin.value(),
                front_quantity=front_spin.value(),
                price=price_spin.value(),
                cost=cost_spin.value(),
                description=desc_edit.text().strip(),
                barcode=barcode_edit.text().strip(),
                min_stock_level=min_stock_spin.value()
            )
            self.items.append(item)
            self.save_data()
            self.refresh_items_table()
            self.refresh_low_stock_alerts()

    def new_sale(self):
        """Create a new sale"""
        if not self.items:
            QMessageBox.warning(self, "No Items", "Please add some items to inventory first.")
            return
            
        dlg = QDialog(self)
        dlg.setWindowTitle("New Sale")
        dlg.resize(500, 400)
        
        layout = QVBoxLayout(dlg)
        
        # Item selection
        item_layout = QHBoxLayout()
        item_combo = QComboBox()
        available_items = [item for item in self.items if item.front_quantity > 0]
        item_combo.addItems([f"{item.name} (€{item.price:.2f}) - {item.front_quantity} available" 
                           for item in available_items])
        
        qty_spin = QSpinBox()
        qty_spin.setRange(1, 99)
        
        add_item_btn = QPushButton("Add to Sale")
        
        item_layout.addWidget(QLabel("Item:"))
        item_layout.addWidget(item_combo)
        item_layout.addWidget(QLabel("Qty:"))
        item_layout.addWidget(qty_spin)
        item_layout.addWidget(add_item_btn)
        
        layout.addLayout(item_layout)
        
        # Sale items list
        sale_items_list = QListWidget()
        layout.addWidget(QLabel("Sale Items:"))
        layout.addWidget(sale_items_list)
        
        # Total
        total_label = QLabel("Total: €0.00")
        total_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(total_label)
        
        # Payment method
        payment_layout = QHBoxLayout()
        payment_combo = QComboBox()
        payment_combo.addItems(["Cash", "Card", "Mobile Payment"])
        payment_layout.addWidget(QLabel("Payment:"))
        payment_layout.addWidget(payment_combo)
        layout.addLayout(payment_layout)
        
        # Buttons
        buttons = QHBoxLayout()
        complete_btn = QPushButton("Complete Sale")
        cancel_btn = QPushButton("Cancel")
        buttons.addWidget(complete_btn)
        buttons.addWidget(cancel_btn)
        layout.addRow(buttons)
        
        # Sale tracking
        sale_items = []
        sale_total = 0.0
        
        def add_to_sale():
            nonlocal sale_total
            if not available_items:
                return
                
            selected_item = available_items[item_combo.currentIndex()]
            quantity = qty_spin.value()
            
            if quantity > selected_item.front_quantity:
                QMessageBox.warning(dlg, "Insufficient Stock", 
                                  f"Only {selected_item.front_quantity} available")
                return
            
            item_total = quantity * selected_item.price
            sale_item = SaleItem(
                item_name=selected_item.name,
                category=selected_item.category,
                quantity=quantity,
                price=selected_item.price,
                total=item_total,
                timestamp=datetime.now().isoformat()
            )
            
            sale_items.append(sale_item)
            sale_total += item_total
            
            sale_items_list.addItem(f"{quantity}x {selected_item.name} - €{item_total:.2f}")
            total_label.setText(f"Total: €{sale_total:.2f}")
        
        def complete_sale():
            if not sale_items:
                QMessageBox.warning(dlg, "Empty Sale", "Please add some items to the sale.")
                return
                
            # Create sale record
            sale_id = f"SALE_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            sale = Sale(
                id=sale_id,
                items=sale_items,
                total_amount=sale_total,
                timestamp=datetime.now().isoformat(),
                payment_method=payment_combo.currentText().lower()
            )
            
            # Update inventory quantities
            for sale_item in sale_items:
                for item in self.items:
                    if item.name == sale_item.item_name:
                        item.front_quantity -= sale_item.quantity
                        break
            
            self.sales.append(sale)
            self.save_data()
            self.refresh_items_table()
            self.refresh_sales_table()
            self.refresh_low_stock_alerts()
            
            QMessageBox.information(dlg, "Sale Complete", 
                                  f"Sale {sale_id} completed successfully!\nTotal: €{sale_total:.2f}")
            dlg.accept()
        
        add_item_btn.clicked.connect(add_to_sale)
        complete_btn.clicked.connect(complete_sale)
        cancel_btn.clicked.connect(dlg.reject)
        
        dlg.exec()

    def move_to_front(self):
        """Move items from storage to front - this represents sales of the items currently in front"""
        if not self.items:
            QMessageBox.warning(self, "No Items", "No items in inventory.")
            return
            
        # Show dialog to select items and quantities to move
        dlg = QDialog(self)
        dlg.setWindowTitle("Restock Front (Record Sales)")
        layout = QVBoxLayout(dlg)
        
        # Add explanation
        explanation = QLabel(
            "When you restock the front, it means the items currently in front have been sold.\n"
            "This will record sales for front items and replace them with storage items."
        )
        explanation.setStyleSheet("color: #666; font-size: 11px; padding: 10px; background-color: #f8f9fa; border-radius: 5px;")
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        
        # Filter items that have storage quantity
        storage_items = [item for item in self.items if item.storage_quantity > 0]
        
        if not storage_items:
            QMessageBox.information(self, "No Storage Items", "No items available in storage.")
            return
        
        for item in storage_items:
            item_layout = QHBoxLayout()
            
            # Show current front quantity (what will be "sold")
            current_front = item.front_quantity
            label = QLabel(f"{item.name} - Front: {current_front} (will be sold) | Storage: {item.storage_quantity}")
            
            qty_spin = QSpinBox()
            qty_spin.setRange(0, item.storage_quantity)
            qty_spin.setValue(min(current_front, item.storage_quantity))  # Default to replacing what's in front
            qty_spin.setSuffix(" to front")
            
            item_layout.addWidget(label)
            item_layout.addWidget(QLabel("Move:"))
            item_layout.addWidget(qty_spin)
            
            layout.addLayout(item_layout)
            item.move_quantity = qty_spin  # Store reference for later
        
        buttons = QHBoxLayout()
        ok_btn = QPushButton("🛒 Record Sales & Restock")
        cancel_btn = QPushButton("Cancel")
        buttons.addWidget(ok_btn)
        buttons.addWidget(cancel_btn)
        layout.addLayout(buttons)
        
        ok_btn.clicked.connect(dlg.accept)
        cancel_btn.clicked.connect(dlg.reject)
        
        if dlg.exec():
            sales_items = []
            moved_items = 0
            total_sales_amount = 0
            
            for item in storage_items:
                qty_to_move = item.move_quantity.value()
                current_front = item.front_quantity
                
                if qty_to_move > 0:
                    # Record sales for current front items (they are being "sold")
                    if current_front > 0:
                        sale_item = SaleItem(
                            item_name=item.name,
                            category=item.category,
                            quantity=current_front,
                            price=item.price,
                            total=current_front * item.price,
                            timestamp=datetime.now().isoformat()
                        )
                        sales_items.append(sale_item)
                        total_sales_amount += current_front * item.price
                    
                    # Move items from storage to front
                    item.storage_quantity -= qty_to_move
                    item.front_quantity = qty_to_move  # Replace front items completely
                    moved_items += 1
            
            # Create a sale record if there were any sales
            if sales_items:
                sale = Sale(
                    id=f"AUTO_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                    items=sales_items,
                    total_amount=total_sales_amount,
                    timestamp=datetime.now().isoformat(),
                    payment_method="auto_front_restock"
                )
                self.sales.append(sale)
            
            if moved_items > 0:
                self.save_data()
                self.refresh_items_table()
                self.refresh_low_stock_alerts()
                
                # Show completion message
                message = f"Successfully restocked {moved_items} items."
                if sales_items:
                    items_sold = sum(item.quantity for item in sales_items)
                    message += f"\nRecorded sales: {items_sold} items sold (€{total_sales_amount:.2f})"
                
                QMessageBox.information(self, "Restock Complete", message)

    def restock_items(self):
        """Add items to storage"""
        if not self.items:
            QMessageBox.warning(self, "No Items", "No items in inventory.")
            return
            
        dlg = QDialog(self)
        dlg.setWindowTitle("Restock Items")
        layout = QVBoxLayout(dlg)
        
        for item in self.items:
            item_layout = QHBoxLayout()
            
            label = QLabel(f"{item.name} (Current Storage: {item.storage_quantity})")
            qty_spin = QSpinBox()
            qty_spin.setRange(0, 999)
            qty_spin.setValue(10)
            
            item_layout.addWidget(label)
            item_layout.addWidget(QLabel("Add:"))
            item_layout.addWidget(qty_spin)
            
            layout.addLayout(item_layout)
            item.restock_quantity = qty_spin
        
        buttons = QHBoxLayout()
        ok_btn = QPushButton("Restock")
        cancel_btn = QPushButton("Cancel")
        buttons.addWidget(ok_btn)
        buttons.addWidget(cancel_btn)
        layout.addLayout(buttons)
        
        ok_btn.clicked.connect(dlg.accept)
        cancel_btn.clicked.connect(dlg.reject)
        
        if dlg.exec():
            restocked_items = 0
            for item in self.items:
                qty_to_add = item.restock_quantity.value()
                if qty_to_add > 0:
                    item.storage_quantity += qty_to_add
                    restocked_items += 1
            
            if restocked_items > 0:
                self.save_data()
                self.refresh_items_table()
                self.refresh_low_stock_alerts()
                QMessageBox.information(self, "Restock Complete", f"Successfully restocked {restocked_items} items.")

    def refresh_items_table(self):
        """Refresh the items table display"""
        self.items_table.setRowCount(len(self.items))
        
        for row, item in enumerate(self.items):
            self.items_table.setItem(row, 0, QTableWidgetItem(item.name))
            self.items_table.setItem(row, 1, QTableWidgetItem(item.category))
            self.items_table.setItem(row, 2, QTableWidgetItem(str(item.storage_quantity)))
            self.items_table.setItem(row, 3, QTableWidgetItem(str(item.front_quantity)))
            self.items_table.setItem(row, 4, QTableWidgetItem(str(item.total_quantity)))
            self.items_table.setItem(row, 5, QTableWidgetItem(f"€{item.price:.2f}"))
            
            # Low stock indicator
            low_stock_item = QTableWidgetItem("⚠️ Low Stock" if item.is_low_stock else "✅ OK")
            if item.is_low_stock:
                low_stock_item.setBackground(Qt.yellow)
            self.items_table.setItem(row, 6, low_stock_item)
            
            # Actions button
            edit_btn = QPushButton("Edit")
            edit_btn.clicked.connect(lambda checked, i=item: self.edit_item(i))
            self.items_table.setCellWidget(row, 7, edit_btn)

    def refresh_categories_list(self):
        """Refresh the categories list display"""
        self.categories_list.clear()
        for category in self.categories:
            item_text = f"{category.name}"
            if category.description:
                item_text += f" - {category.description}"
            self.categories_list.addItem(item_text)

    def refresh_sales_table(self):
        """Refresh the sales table display"""
        self.sales_table.setRowCount(len(self.sales))
        
        for row, sale in enumerate(self.sales):
            self.sales_table.setItem(row, 0, QTableWidgetItem(sale.id))
            
            # Format timestamp
            try:
                dt = datetime.fromisoformat(sale.timestamp)
                date_str = dt.strftime("%Y-%m-%d %H:%M")
            except:
                date_str = sale.timestamp
            self.sales_table.setItem(row, 1, QTableWidgetItem(date_str))
            
            # Items summary
            items_text = f"{len(sale.items)} items"
            self.sales_table.setItem(row, 2, QTableWidgetItem(items_text))
            
            self.sales_table.setItem(row, 3, QTableWidgetItem(f"€{sale.total_amount:.2f}"))
            self.sales_table.setItem(row, 4, QTableWidgetItem(sale.payment_method.title()))

    def refresh_low_stock_alerts(self):
        """Refresh the low stock alerts display"""
        self.low_stock_list.clear()
        
        low_stock_items = [item for item in self.items if item.is_low_stock]
        
        if not low_stock_items:
            self.low_stock_list.addItem("✅ All items are well stocked!")
        else:
            for item in low_stock_items:
                alert_text = f"⚠️ {item.name}: {item.total_quantity} remaining (min: {item.min_stock_level})"
                self.low_stock_list.addItem(alert_text)

    def edit_item(self, item):
        """Edit an existing item"""
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Edit {item.name}")
        layout = QFormLayout(dlg)
        
        name_edit = QLineEdit(item.name)
        category_combo = QComboBox()
        category_combo.addItems([cat.name for cat in self.categories])
        category_combo.setCurrentText(item.category)
        
        storage_spin = QSpinBox()
        storage_spin.setRange(0, 9999)
        storage_spin.setValue(item.storage_quantity)
        
        front_spin = QSpinBox()
        front_spin.setRange(0, 9999)
        front_spin.setValue(item.front_quantity)
        
        price_spin = QDoubleSpinBox()
        price_spin.setRange(0.0, 9999.99)
        price_spin.setSuffix(" €")
        price_spin.setValue(item.price)
        
        cost_spin = QDoubleSpinBox()
        cost_spin.setRange(0.0, 9999.99)
        cost_spin.setSuffix(" €")
        cost_spin.setValue(item.cost)
        
        min_stock_spin = QSpinBox()
        min_stock_spin.setRange(0, 999)
        min_stock_spin.setValue(item.min_stock_level)
        
        desc_edit = QLineEdit(item.description)
        barcode_edit = QLineEdit(item.barcode)
        
        layout.addRow("Name:", name_edit)
        layout.addRow("Category:", category_combo)
        layout.addRow("Storage Quantity:", storage_spin)
        layout.addRow("Front Quantity:", front_spin)
        layout.addRow("Selling Price:", price_spin)
        layout.addRow("Cost Price:", cost_spin)
        layout.addRow("Min Stock Level:", min_stock_spin)
        layout.addRow("Description:", desc_edit)
        layout.addRow("Barcode:", barcode_edit)
        
        buttons = QHBoxLayout()
        ok_btn = QPushButton("Save")
        delete_btn = QPushButton("Delete")
        cancel_btn = QPushButton("Cancel")
        
        delete_btn.setStyleSheet("background-color: #dc3545; color: white;")
        
        buttons.addWidget(ok_btn)
        buttons.addWidget(delete_btn)
        buttons.addWidget(cancel_btn)
        layout.addRow(buttons)
        
        ok_btn.clicked.connect(dlg.accept)
        cancel_btn.clicked.connect(dlg.reject)
        
        def delete_item():
            reply = QMessageBox.question(
                dlg, "Delete Item",
                f"Are you sure you want to delete '{item.name}'?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                dlg.done(2)  # Custom result for delete
        
        delete_btn.clicked.connect(delete_item)
        
        result = dlg.exec()
        if result == 1:  # OK
            item.name = name_edit.text().strip()
            item.category = category_combo.currentText()
            item.storage_quantity = storage_spin.value()
            item.front_quantity = front_spin.value()
            item.price = price_spin.value()
            item.cost = cost_spin.value()
            item.min_stock_level = min_stock_spin.value()
            item.description = desc_edit.text().strip()
            item.barcode = barcode_edit.text().strip()
            
            self.save_data()
            self.refresh_items_table()
            self.refresh_low_stock_alerts()
            
        elif result == 2:  # Delete
            self.items.remove(item)
            self.save_data()
            self.refresh_items_table()
            self.refresh_low_stock_alerts()

    def update_analytics(self):
        """Update the analytics display based on selected period"""
        period = self.period_combo.currentText()
        
        # Show/hide custom date inputs
        if period == "Custom Range":
            self.date_from.show()
            self.date_to.show()
        else:
            self.date_from.hide()
            self.date_to.hide()
        
        # Calculate date range
        now = datetime.now()
        if period == "This Week":
            start_date = now - timedelta(days=now.weekday())
        elif period == "This Month":
            start_date = now.replace(day=1)
        elif period == "Custom Range":
            start_date = datetime.combine(self.date_from.date().toPython(), datetime.min.time())
        else:  # All Time
            start_date = datetime.min
        
        if period == "Custom Range":
            end_date = datetime.combine(self.date_to.date().toPython(), datetime.max.time())
        else:
            end_date = now
        
        # Filter sales by date range
        filtered_sales = []
        for sale in self.sales:
            try:
                sale_date = datetime.fromisoformat(sale.timestamp)
                if start_date <= sale_date <= end_date:
                    filtered_sales.append(sale)
            except:
                continue
        
        # Calculate analytics
        analytics = self.calculate_analytics(filtered_sales)
        
        # Display analytics
        analytics_text = f"""
<h2>Sales Analytics - {period}</h2>
<hr>

<h3>📊 Summary</h3>
<b>Total Sales:</b> {analytics['total_sales']}<br>
<b>Total Revenue:</b> €{analytics['total_revenue']:.2f}<br>
<b>Average Sale:</b> €{analytics['avg_sale']:.2f}<br>
<b>Items Sold:</b> {analytics['total_items']}<br>

<h3>🏆 Best Selling Items</h3>
"""
        
        for i, (item_name, quantity) in enumerate(analytics['best_selling'][:10], 1):
            analytics_text += f"{i}. <b>{item_name}</b> - {quantity} sold<br>"
        
        analytics_text += f"""
<h3>📈 Category Performance</h3>
"""
        
        for category, data in analytics['category_performance'].items():
            analytics_text += f"<b>{category}:</b> {data['quantity']} items, €{data['revenue']:.2f}<br>"
        
        analytics_text += f"""
<h3>💳 Payment Methods</h3>
"""
        
        for method, count in analytics['payment_methods'].items():
            analytics_text += f"<b>{method.title()}:</b> {count} transactions<br>"
        
        self.analytics_text.setHtml(analytics_text)

    def calculate_analytics(self, sales):
        """Calculate analytics from sales data"""
        if not sales:
            return {
                'total_sales': 0,
                'total_revenue': 0.0,
                'avg_sale': 0.0,
                'total_items': 0,
                'best_selling': [],
                'category_performance': {},
                'payment_methods': {}
            }
        
        total_revenue = sum(sale.total_amount for sale in sales)
        total_items = sum(len(sale.items) for sale in sales)
        
        # Best selling items
        item_sales = defaultdict(int)
        category_sales = defaultdict(lambda: {'quantity': 0, 'revenue': 0.0})
        payment_methods = defaultdict(int)
        
        for sale in sales:
            payment_methods[sale.payment_method] += 1
            
            for item in sale.items:
                item_sales[item.item_name] += item.quantity
                category_sales[item.category]['quantity'] += item.quantity
                category_sales[item.category]['revenue'] += item.total
        
        best_selling = sorted(item_sales.items(), key=lambda x: x[1], reverse=True)
        
        return {
            'total_sales': len(sales),
            'total_revenue': total_revenue,
            'avg_sale': total_revenue / len(sales),
            'total_items': total_items,
            'best_selling': best_selling,
            'category_performance': dict(category_sales),
            'payment_methods': dict(payment_methods)
        }
