"""Settings panel — database connection and LLM configuration."""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QLineEdit, QPushButton, QMessageBox, QApplication, QComboBox,
    QSizePolicy,
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
        self.input_port = QLineEdit("5433")
        self.input_dbname = QLineEdit("TPC-H")
        self.input_user = QLineEdit("postgres")
        self.input_password = QLineEdit("qwerty")
        self.input_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.btn_connect = QPushButton("Connect")
        self.btn_connect.clicked.connect(self.connect_db)

        for label, widget, stretch in [
            ("Host", self.input_host, 2),
            ("Port", self.input_port, 1),
            ("DB", self.input_dbname, 2),
            ("User", self.input_user, 2),
            ("Pass", self.input_password, 2),
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
        self.input_llm_provider.addItems(["Azure OpenAI", "OpenAI"])
        self.input_llm_provider.currentTextChanged.connect(self._on_provider_changed)
        col, _ = _field_column("Provider", self.input_llm_provider)
        llm_row.addLayout(col, 2)

        # Endpoint (Azure only) — wrap in a widget so we can toggle visibility
        self.input_llm_endpoint = QLineEdit("https://sc3020-db.openai.azure.com/")
        self.input_llm_endpoint.setReadOnly(True)
        self.endpoint_container = QWidget()
        self.endpoint_container.setObjectName("fieldContainer")
        endpoint_col = QVBoxLayout(self.endpoint_container)
        endpoint_col.setContentsMargins(0, 0, 0, 0)
        endpoint_col.setSpacing(2)
        self.label_llm_endpoint = QLabel("Endpoint")
        self.label_llm_endpoint.setProperty("fieldLabel", True)
        endpoint_col.addWidget(self.label_llm_endpoint)
        endpoint_col.addWidget(self.input_llm_endpoint)
        llm_row.addWidget(self.endpoint_container, 3)

        # Model / Deployment
        self.input_llm_deployment = QLineEdit("gpt-4.1-nano")
        self.deployment_container = QWidget()
        self.deployment_container.setObjectName("fieldContainer")
        dep_col = QVBoxLayout(self.deployment_container)
        dep_col.setContentsMargins(0, 0, 0, 0)
        dep_col.setSpacing(2)
        self.label_llm_deployment = QLabel("Deployment")
        self.label_llm_deployment.setProperty("fieldLabel", True)
        dep_col.addWidget(self.label_llm_deployment)
        dep_col.addWidget(self.input_llm_deployment)
        llm_row.addWidget(self.deployment_container, 2)

        # API Key
        self.input_llm_api_key = QLineEdit()
        self.input_llm_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_llm_api_key.setPlaceholderText("Enter API key here...")
        col, _ = _field_column("API Key", self.input_llm_api_key)
        llm_row.addLayout(col, 3)

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

        # Default to Azure OpenAI — show Azure-only fields
        self._on_provider_changed("Azure OpenAI")
        self.apply_theme()

    def _on_provider_changed(self, provider_text):
        """Show/hide Azure-specific fields based on provider."""
        is_azure = provider_text == "Azure OpenAI"
        self.endpoint_container.setVisible(is_azure)
        # For Azure the deployment name is user-chosen (read-only preset here);
        # for OpenAI the model name should be editable.
        self.input_llm_deployment.setReadOnly(is_azure)
        self.label_llm_deployment.setText("Deployment" if is_azure else "Model")

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

        provider = "azure" if self.input_llm_provider.currentText() == "Azure OpenAI" else "openai"
        set_llm_config(
            api_key=api_key,
            deployment=self.input_llm_deployment.text(),
            provider=provider,
            endpoint=self.input_llm_endpoint.text() if provider == "azure" else None,
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
            provider_name = self.input_llm_provider.currentText()
            QMessageBox.warning(
                self, "LLM Connection Failed",
                f"Could not connect to {provider_name}:\n{e}"
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
