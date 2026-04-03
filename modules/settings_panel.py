"""Settings panel — database connection and LLM configuration."""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QLineEdit, QPushButton, QMessageBox, QApplication,
)
from PySide6.QtGui import QFont

from preprocessing import connect_db, close_db
from annotation import set_llm_config, _get_llm_client


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

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # --- Database connection ---
        db_group = QGroupBox("Database Connection")
        db_row = QHBoxLayout(db_group)
        self.input_host = QLineEdit("localhost")
        self.input_port = QLineEdit("5433")
        self.input_dbname = QLineEdit("TPC-H")
        self.input_user = QLineEdit("postgres")
        self.input_password = QLineEdit("qwerty")
        self.input_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.btn_connect = QPushButton("Connect")
        self.btn_connect.clicked.connect(self.connect_db)

        for label, widget in [
            ("Host:", self.input_host), ("Port:", self.input_port),
            ("DB:", self.input_dbname), ("User:", self.input_user),
            ("Pass:", self.input_password),
        ]:
            db_row.addWidget(QLabel(label))
            db_row.addWidget(widget)
        db_row.addWidget(self.btn_connect)
        layout.addWidget(db_group)

        # --- LLM settings ---
        llm_group = QGroupBox("LLM Settings (Azure OpenAI)")
        llm_row = QHBoxLayout(llm_group)

        llm_row.addWidget(QLabel("Endpoint:"))
        self.input_llm_endpoint = QLineEdit("https://sc3020-db.openai.azure.com/")
        self.input_llm_endpoint.setReadOnly(True)
        llm_row.addWidget(self.input_llm_endpoint)

        llm_row.addWidget(QLabel("Model:"))
        self.input_llm_deployment = QLineEdit("gpt-4.1-nano")
        self.input_llm_deployment.setReadOnly(True)
        llm_row.addWidget(self.input_llm_deployment)

        llm_row.addWidget(QLabel("API Key:"))
        self.input_llm_api_key = QLineEdit()
        self.input_llm_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_llm_api_key.setPlaceholderText("Enter API key here...")
        llm_row.addWidget(self.input_llm_api_key)

        self.btn_llm_connect = QPushButton("Connect LLM")
        self.btn_llm_connect.clicked.connect(self.connect_llm)
        llm_row.addWidget(self.btn_llm_connect)

        layout.addWidget(llm_group)
        self.apply_theme()

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
        config = self.get_db_config()
        self.conn = connect_db(config)
        if self.conn:
            if self._on_db_status:
                self._on_db_status(True, f"Connected to {config['dbname']}@{config['host']}:{config['port']}")
        else:
            if self._on_db_status:
                self._on_db_status(False, "Connection failed")
            QMessageBox.warning(
                self, "Connection Error",
                "Could not connect to the database. Check your settings."
            )

    def connect_llm(self):
        api_key = self.input_llm_api_key.text().strip()
        if not api_key:
            if self._on_llm_status:
                self._on_llm_status("No API Key", "#F44336")
            QMessageBox.warning(self, "Missing API Key", "Please enter an API key.")
            return

        set_llm_config(
            endpoint=self.input_llm_endpoint.text(),
            api_key=api_key,
            deployment=self.input_llm_deployment.text(),
        )

        if self._status_callback:
            self._status_callback("Testing LLM connection...")
        QApplication.processEvents()

        try:
            client, deployment = _get_llm_client()
            if client:
                client.chat.completions.create(
                    model=deployment,
                    messages=[{"role": "user", "content": "Reply with OK"}],
                    max_tokens=5,
                )
                if self._on_llm_status:
                    self._on_llm_status("Online", "#4CAF50")
                if self._status_callback:
                    self._status_callback("LLM connected successfully")
            else:
                raise Exception("Client not created")
        except Exception as e:
            if self._on_llm_status:
                self._on_llm_status("Failed", "#F44336")
            if self._status_callback:
                self._status_callback("LLM connection failed")
            QMessageBox.warning(
                self, "LLM Connection Failed",
                f"Could not connect to Azure OpenAI:\n{e}"
            )

    def apply_theme(self):
        """Update read-only field backgrounds for current theme."""
        style = self.theme.readonly_field_bg()
        self.input_llm_endpoint.setStyleSheet(style)
        self.input_llm_deployment.setStyleSheet(style)

    def close_connection(self):
        if self.conn:
            close_db(self.conn)
            self.conn = None
