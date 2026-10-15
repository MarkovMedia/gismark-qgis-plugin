import json
import os
import tempfile
import requests

from qgis.core import QgsProject, QgsVectorLayer, Qgis, QgsMessageLog
from qgis.PyQt.QtCore import Qt, QSettings
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
API_KEY = "gm_live_mpFaPHGLjz3YYO9iheC0u42iNfUiK19Hyq_ZlCn95Jk"


class GisMarkDialog(QDialog):
    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface

        self.chat_history = []

        self.setWindowTitle("GisMark")
        self.resize(460, 380)

        layout = QVBoxLayout(self)

        description = QLabel(
            "Explore OpenStreetMap in Natural Language"
        )
        layout.addWidget(description)

        layout.addWidget(QLabel("What are you looking for?"))

        self.prompt_input = QLineEdit()
        self.prompt_input.setPlaceholderText(
            "Ask GisMark something..."
        )

        layout.addWidget(self.prompt_input)

        self.search_button = QPushButton("Send")
        self.search_button.clicked.connect(self.search)
        layout.addWidget(self.search_button)

        layout.addWidget(QLabel("GisMark response"))

        self.chat_output = QTextEdit()
        self.chat_output.setReadOnly(True)
        self.chat_output.setPlaceholderText(
            "Your conversation with GisMark will appear here."
        )

        layout.addWidget(self.chat_output)

        self.settings_button = QPushButton("Settings")
        self.settings_button.setFixedWidth(
        self.settings_button.sizeHint().width() + 20
        )
        self.settings_button.clicked.connect(self.open_settings)

        layout.addWidget(self.settings_button)
        layout.setAlignment(self.settings_button, Qt.AlignLeft)

    def open_settings(self):
        dialog = SettingsDialog(self)
        dialog.exec()

    def search(self):
        prompt = self.prompt_input.text().strip()

        if not prompt:
            QMessageBox.warning(
                self,
                "GisMark",
                "Please enter a search prompt."
            )
            return

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
        }

        body = {
            "prompt": prompt,
        }

        self.search_button.setEnabled(False)
        self.search_button.setText("Searching...")

        try:
            response = requests.post(
                API_URL,
                data=json.dumps(body),
                headers=headers,
                timeout=30,
            )

            response.raise_for_status()
                       
            data = response.json()

            message = data.get("message", "")
            content = message.get("content", "")       

            QgsMessageLog.logMessage(
                content,
                "GisMark",
                Qgis.Info,
                ) 

            self.add_chat_message("assistant", content)

            features = data.get("features", [])

            if features:
                geojson = {
                    "type": "FeatureCollection",
                    "features": features,
                }

                feature_set = data.get("featureSet", "GisMark")
                self.display_geojson(geojson, feature_set)
           
        except requests.RequestException as error:
            message = str(error)

            if getattr(error, "response", None) is not None:
                message += (
                    "\n\nServer response:\n"
                    + error.response.text[:1500]
                )

            QMessageBox.warning(
                self,
                "GisMark API error",
                message,
            )

        finally:
            self.search_button.setEnabled(True)
            self.search_button.setText("Search GisMark")

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
