import json
import os
import tempfile
import requests
import uuid

from qgis.core import QgsProject, QgsVectorLayer, Qgis, QgsMessageLog
from qgis.PyQt.QtCore import Qt, QSettings, QThread, pyqtSignal
from qgis.PyQt.QtGui import QTextCursor

from qgis.PyQt.QtWidgets import (
    QAction,
    QDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QHBoxLayout,
    QLineEdit,
)

API_URL = "http://localhost:1337/api/v1/chat"



class ApiRequestWorker(QThread):
    result_ready = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def __init__(self, api_url, body, headers):
        super().__init__()

        self.api_url = api_url
        self.body = body
        self.headers = headers

    def run(self):
        try:
            response = requests.post(
                self.api_url,
                json=self.body,
                headers=self.headers,
                timeout=60,
            )

            response.raise_for_status()
            data = response.json()

            self.result_ready.emit(data)

        except Exception as error:
            self.error_occurred.emit(str(error))



class GisMarkDialog(QDialog):
    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface

        self.chat_history = []
        self.session_id = str(uuid.uuid4())

        self.setWindowTitle("GisMark")
        self.resize(460, 380)

        layout = QVBoxLayout(self)

        description = QLabel(
            "Explore OpenStreetMap in Natural Language"
        )
        layout.addWidget(description)

        
        self.loading_indicator = QLabel("")
        self.loading_indicator.setStyleSheet(
            "color: #2879bd; font-style: italic;"
        )

        layout.addWidget(self.loading_indicator)

        self.prompt_input = QLineEdit()
        self.prompt_input.setMinimumHeight(38)
        self.prompt_input.setPlaceholderText(
            "Ask GisMark something..."
        )

        layout.addWidget(self.prompt_input)

        self.search_button = QPushButton("Send")
        self.search_button.clicked.connect(self.search)
        self.prompt_input.returnPressed.connect(
            self.search_button.click
        )
        layout.addWidget(self.search_button)

        layout.addWidget(QLabel("GisMark response"))

        self.chat_output = QTextEdit()
        self.chat_output.setReadOnly(True)
        self.chat_output.setPlaceholderText(
            "Your conversation with GisMark will appear here."
        )

        layout.addWidget(self.chat_output)

        self.new_chat_button = QPushButton("New Chat")
        self.new_chat_button.setFixedWidth(
        self.new_chat_button.sizeHint().width() + 20
        )
        self.new_chat_button.clicked.connect(self.new_chat)


        self.settings_button = QPushButton("Settings")
        self.settings_button.setFixedWidth(
            self.settings_button.sizeHint().width() + 20
        )
        self.settings_button.clicked.connect(self.open_settings)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.new_chat_button)
        button_layout.addStretch()
        button_layout.addWidget(self.settings_button)

        layout.addLayout(button_layout)


    def open_settings(self):
        dialog = SettingsDialog(self)
        dialog.exec()

    def new_chat(self):
        # Generate a new session ID.
        self.session_id = str(uuid.uuid4())

        # Clear the conversation history and display.
        self.chat_history.clear()
        self.chat_output.clear()

        QgsMessageLog.logMessage(
            f"Started new chat: {self.session_id}",
            "GisMark",
            Qgis.Info,
        )


    def search(self):
        prompt = self.prompt_input.text().strip()

        if not prompt:
            return

        self.add_chat_message("user", prompt)
        self.prompt_input.clear()        

        api_key = QSettings().value("GisMark/apiKey", "", type=str)

        if not api_key:
            QMessageBox.information(
                self,
                "GisMark",
                "Please add your API key in Settings first.",
            )
            self.open_settings()
            return

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "x-session-id": self.session_id,
        }

        body = {
            "prompt": prompt,
        }

        self.search_button.setEnabled(False)
        self.search_button.setText("Searching...")

        # Show the loading indicator.
        self.loading_indicator.show()
        self.search_button.setEnabled(False)
        self.search_button.setText("Thinking...")

        # Start the API request in the background.
        self.api_worker = ApiRequestWorker(
            API_URL,
            body,
            headers,
        )

        self.api_worker.result_ready.connect(
            self.handle_api_response
        )

        self.api_worker.error_occurred.connect(
        self.handle_api_error
        )

        self.api_worker.finished.connect(
            self.api_worker.deleteLater
        )

        self.api_worker.start()


    def handle_api_response(self, data):
        self.loading_indicator.setText("")
        self.search_button.setEnabled(True)
        self.prompt_input.setEnabled(True)
        self.search_button.setText("Send")

        # Display the assistant's response.
        message = data.get("message", {})
        content = message.get("content", "")

        self.add_chat_message("assistant", content)

        # Display returned features on the map.
        features = data.get("features", [])

        if features:
            geojson = {
                "type": "FeatureCollection",
                "features": features,
            }

            feature_set = data.get(
                "featureSet",
                "GisMark results",
            )

            self.display_geojson(geojson, feature_set)

        self.prompt_input.setFocus()

    def handle_api_error(self, error_message):
        self.loading_indicator.setText("")
        self.search_button.setEnabled(True)
        self.prompt_input.setEnabled(True)
        self.search_button.setText("Send")

        QMessageBox.warning(
            self,
            "GisMark",
            f"The request failed:\n{error_message}",
        )

        self.prompt_input.setFocus()


    def add_chat_message(self, role, content):
        # Store the message.
        self.chat_history.append({
            "role": role,
            "content": content,
        })

        # Display the message.
        label = "me" if role == "user" else "GisMark"

        self.chat_output.moveCursor(QTextCursor.End)
        self.chat_output.insertPlainText(
            f"{label}: {content}\n\n"
        )
        self.chat_output.ensureCursorVisible()

    
    def display_geojson(self, geojson, feature_set):
        features = geojson.get("features", [])

        # Group features by geometry type.
        groups = {
            "Polygon": [],
            "Line": [],
            "Point": [],
        }

        for feature in features:
            geometry = feature.get("geometry")

            if not geometry:
                continue

            geometry_type = geometry.get("type", "")

            if geometry_type in ("Polygon", "MultiPolygon"):
                groups["Polygon"].append(feature)

            elif geometry_type in ("LineString", "MultiLineString"):
                groups["Line"].append(feature)

            elif geometry_type in ("Point", "MultiPoint"):
                groups["Point"].append(feature)

        project = QgsProject.instance()
        layers = []

        # Create layers in this order so points appear on top.
        for name, layer_features in groups.items():
            if not layer_features:
                continue

            collection = {
                "type": "FeatureCollection",
                "features": layer_features,
            }

            # Write the GeoJSON to a temporary file.
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".geojson",
                encoding="utf-8",
                delete=False,
            ) as file:
                json.dump(collection, file)
                file_path = file.name

            layer = QgsVectorLayer(
                file_path,
                f"{feature_set} - {name}s",
                "ogr",
            )

            if not layer.isValid():
                QMessageBox.warning(
                    self,
                    "GisMark",
                    f"Could not load the {name.lower()} layer.",
                )
                continue

            project.addMapLayer(layer)
            layers.append(layer)

        # Zoom to all the new layers together.
        if layers:
            from qgis.core import QgsCoordinateTransform, QgsRectangle

            project = QgsProject.instance()
            canvas = self.iface.mapCanvas()
            canvas_crs = canvas.mapSettings().destinationCrs()

            extent = QgsRectangle()

            for layer in layers:
                transform = QgsCoordinateTransform(
                    layer.crs(),
                    canvas_crs,
                    project,
                )

                layer_extent = transform.transformBoundingBox(
                    layer.extent()
                )

                extent.combineExtentWith(layer_extent)

            extent.scale(1.1)

            canvas.setExtent(extent)
            canvas.refresh()

            self.iface.setActiveLayer(layers[-1])

       
class GisMarkPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.action = None
        self.dialog = None

    def initGui(self):
        self.action = QAction(
            "Search GisMark...",
            self.iface.mainWindow(),
        )
        self.action.triggered.connect(self.run)
        self.iface.addPluginToMenu("&GisMark", self.action)

    def unload(self):
        self.iface.removePluginMenu("&GisMark", self.action)

    def run(self):
        self.dialog = GisMarkDialog(self.iface, self.iface.mainWindow())
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("GisMark Settings")
        self.setMinimumWidth(320)

        # API key label and password field.
        self.api_key_label = QLabel("GisMark API key:")

        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.Password)
        self.api_key_input.setPlaceholderText("Enter your API key")
        self.api_key_input.setText(
           QSettings().value("GisMark/apiKey", "", type=str)
        )

        # Save and Cancel buttons.
        self.save_button = QPushButton("Save")
        self.cancel_button = QPushButton("Cancel")

        self.save_button.clicked.connect(self.save_settings)
        self.cancel_button.clicked.connect(self.reject)

        # Layout for the buttons.
        button_layout = QHBoxLayout()
        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.cancel_button)

        # Main layout.
        layout = QVBoxLayout()
        layout.addWidget(self.api_key_label)
        layout.addWidget(self.api_key_input)
        layout.addLayout(button_layout)

        self.setLayout(layout)

    def save_settings(self):
        api_key = self.api_key_input.text().strip()

        if not api_key:
            QMessageBox.warning(
                self,
                "GisMark Settings",
                "Please enter your API key.",
            )
            return

        QSettings().setValue("GisMark/apiKey", api_key)
        self.accept()
