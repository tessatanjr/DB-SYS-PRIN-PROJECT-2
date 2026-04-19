"""Settings panel — database connection and LLM configuration."""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QLineEdit, QPushButton, QMessageBox, QApplication, QComboBox,
    QSizePolicy,
)
from PySide6.QtGui import QFont

from preprocessing import connect_db, close_db
from modules.llm import set_llm_config, test_connection, PROVIDER_PRESETS


class SettingsPanel(QWidget):
    """Collapsible panel containing DB and LLM connection settings."""

    def __init__(self, theme_manager, parent=None):
        super().__init__(parent)
        self.theme = theme_manager
        self.conn = None

        # Callbacks set by MainWindow
        self._on_db_status = None    # callback(connected: bool, msg: str)
        self._on_llm_status = None   # callback(status: str, color: str)
        self._status_callback = None # callback(msg: str)

        self._build_ui()
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        def _field_column(label_text, widget, stretch=1):
            col = QVBoxLayout()
            col.setContentsMargins(0, 0, 0, 0)
            col.setSpacing(2)
            lbl = QLabel(label_text)
            lbl.setProperty("fieldLabel", True)
            col.addWidget(lbl)
            col.addWidget(widget)
            return col, stretch

        # --- Database connection ---
        db_group = QGroupBox("Database Connection")
        db_group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        db_row = QHBoxLayout(db_group)
        db_row.setContentsMargins(10, 6, 10, 8)
        db_row.setSpacing(8)

        self.input_host = QLineEdit("localhost")
        self.input_port = QLineEdit("5432")
        self.input_dbname = QLineEdit("TPC-H")
        self.input_user = QLineEdit("postgres")
        self.input_password = QLineEdit()
        self.input_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_password.setPlaceholderText("Enter password...")
        self.btn_connect = QPushButton("Connect")
        self.btn_connect.clicked.connect(self.connect_db)

        for label, widget, stretch in [
            ("Host", self.input_host, 2),
            ("Port", self.input_port, 1),
            ("DB", self.input_dbname, 2),
            ("User", self.input_user, 2),
            ("Password", self.input_password, 2),
        ]:
            col, _ = _field_column(label, widget)
            db_row.addLayout(col, stretch)

        # Button column — align with input row (empty spacer label on top)
        btn_col = QVBoxLayout()
        btn_col.setContentsMargins(0, 0, 0, 0)
        btn_col.setSpacing(2)
        spacer = QLabel(" ")
        spacer.setProperty("fieldLabel", True)
        btn_col.addWidget(spacer)
        btn_col.addWidget(self.btn_connect)
        db_row.addLayout(btn_col, 0)

        layout.addWidget(db_group)

        # --- LLM settings ---
        self.llm_group = QGroupBox("LLM Settings")
        self.llm_group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        llm_row = QHBoxLayout(self.llm_group)
        llm_row.setContentsMargins(10, 6, 10, 8)
        llm_row.setSpacing(8)

        # Provider selector
        self.input_llm_provider = QComboBox()
        self.input_llm_provider.addItems(list(PROVIDER_PRESETS.keys()))
        self.input_llm_provider.currentTextChanged.connect(self._on_provider_changed)
        col, _ = _field_column("Provider", self.input_llm_provider)
        llm_row.addLayout(col, 1)

        # Endpoint
        default_endpoint = PROVIDER_PRESETS["OpenAI"][0]
        self.input_llm_endpoint = QLineEdit(default_endpoint)
        self.input_llm_endpoint.setReadOnly(True)
        col, _ = _field_column("Endpoint", self.input_llm_endpoint)
        llm_row.addLayout(col, 3)

        # Model
        self.input_llm_deployment = QComboBox()
        self.input_llm_deployment.setEditable(False)
        self.input_llm_deployment.addItems(PROVIDER_PRESETS["OpenAI"][1])
        col, _ = _field_column("Model", self.input_llm_deployment)
        llm_row.addLayout(col, 2)

        # API Key (wrapped in a container so it can be hidden for Ollama)
        self.api_key_container = QWidget()
        self.api_key_container.setStyleSheet("background: transparent;")
        api_key_layout = QVBoxLayout(self.api_key_container)
        api_key_layout.setContentsMargins(0, 0, 0, 0)
        api_key_layout.setSpacing(2)
        api_key_label = QLabel("API Key")
        api_key_label.setProperty("fieldLabel", True)
        api_key_layout.addWidget(api_key_label)
        self.input_llm_api_key = QLineEdit(PROVIDER_PRESETS["OpenAI"][3])
        self.input_llm_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_llm_api_key.setPlaceholderText("Enter API key here...")
        api_key_layout.addWidget(self.input_llm_api_key)
        llm_row.addWidget(self.api_key_container, 3)

        self.btn_llm_connect = QPushButton("Connect LLM")
        self.btn_llm_connect.clicked.connect(self.connect_llm)
        btn_col2 = QVBoxLayout()
        btn_col2.setContentsMargins(0, 0, 0, 0)
        btn_col2.setSpacing(2)
        spacer2 = QLabel(" ")
        spacer2.setProperty("fieldLabel", True)
        btn_col2.addWidget(spacer2)
        btn_col2.addWidget(self.btn_llm_connect)
        llm_row.addLayout(btn_col2, 0)

        layout.addWidget(self.llm_group)

    def _on_provider_changed(self, provider_text):
        """Auto-fill endpoint and model defaults when provider changes."""
        preset = PROVIDER_PRESETS.get(provider_text)
        if not preset:
            return
        endpoint, models, needs_key, default_key = preset
        is_ollama = provider_text == "Ollama"
        self.input_llm_endpoint.setText(endpoint)
        self.input_llm_endpoint.setReadOnly(True)
        self.input_llm_deployment.clear()
        if models:
            self.input_llm_deployment.addItems(models)
        self.input_llm_deployment.setEditable(is_ollama)
        if is_ollama:
            self.input_llm_deployment.setEditText("")
            self.input_llm_deployment.lineEdit().setPlaceholderText("e.g. llama3.2:latest")
        # Hide API key field for Ollama, auto-fill key
        self.api_key_container.setVisible(not is_ollama)
        self.input_llm_api_key.setText(default_key)
        self.input_llm_api_key.setPlaceholderText(
            "Enter API key here..." if needs_key else "Not required"
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def get_db_config(self):
        return {
            "host":     self.input_host.text(),
            "port":     int(self.input_port.text()),
            "dbname":   self.input_dbname.text(),
            "user":     self.input_user.text(),
            "password": self.input_password.text(),
        }

    def connect_db(self):
        if self.conn:
            close_db(self.conn)
            self.conn = None
        config = self.get_db_config()
        try:
            self.conn = connect_db(config)
            if self._on_db_status:
                self._on_db_status(True, f"Connected to {config['dbname']}@{config['host']}:{config['port']}")
        except Exception as e:
            if self._on_db_status:
                self._on_db_status(False, "Connection failed")
            # Clean up psycopg2's multi-line formatting
            msg = " ".join(str(e).split())
            QMessageBox.warning(
                self, "Connection Error",
                f"Could not connect to the database:\n\n{msg}"
            )

    def connect_llm(self):
        provider = self.input_llm_provider.currentText()
        api_key = self.input_llm_api_key.text().strip()
        needs_key = PROVIDER_PRESETS.get(provider, (None, None, True))[2]

        if needs_key and not api_key:
            if self._on_llm_status:
                self._on_llm_status("No API Key", "#F44336")
            QMessageBox.warning(self, "Missing API Key", "Please enter an API key.")
            return

        set_llm_config(
            provider=provider,
            api_key=api_key,
            model=self.input_llm_deployment.currentText(),
            endpoint=self.input_llm_endpoint.text(),
        )

        # Show connecting state
        self.btn_llm_connect.setEnabled(False)
        self.btn_llm_connect.setText("Connecting...")
        if self._on_llm_status:
            self._on_llm_status("Connecting...", "#FF9800")
        if self._status_callback:
            self._status_callback("Testing LLM connection...")
        QApplication.processEvents()

        try:
            test_connection()
            if self._on_llm_status:
                self._on_llm_status("Online", "#4CAF50")
            if self._status_callback:
                self._status_callback("LLM connected successfully")
        except Exception as e:
            if self._on_llm_status:
                self._on_llm_status("Failed", "#F44336")
            if self._status_callback:
                self._status_callback("LLM connection failed")
            QMessageBox.warning(
                self, "LLM Connection Failed",
                f"Could not connect to {provider}:\n{e}"
            )
        finally:
            self.btn_llm_connect.setEnabled(True)
            self.btn_llm_connect.setText("Connect LLM")

    def close_connection(self):
        if self.conn:
            close_db(self.conn)
            self.conn = None
