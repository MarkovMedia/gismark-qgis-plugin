import json
import os
import tempfile
import requests

from qgis.core import QgsProject, QgsVectorLayer

from qgis.PyQt.QtWidgets import (
    QAction,
    QDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)


API_URL = "http://localhost:1337/api/v1/chat"
API_KEY = "gm_live_mpFaPHGLjz3YYO9iheC0u42iNfUiK19Hyq_ZlCn95Jk"


class GisMarkDialog(QDialog):
    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface

        self.setWindowTitle("GisMark")
        self.resize(460, 380)

        layout = QVBoxLayout(self)

        description = QLabel(
            "Explore OpenStreetMap in Natural Language"
        )
        layout.addWidget(description)

        layout.addWidget(QLabel("What are you looking for?"))

        self.prompt_input = QTextEdit()
        self.prompt_input.setPlaceholderText(
            "e.g. Hotels near the railway station in Budapest"
        )

        layout.addWidget(self.prompt_input)

        self.search_button = QPushButton("Search GisMark")
        self.search_button.clicked.connect(self.search)
        layout.addWidget(self.search_button)

        layout.addWidget(QLabel("GisMark response"))

        self.response_output = QTextEdit()
        self.response_output.setReadOnly(True)
        self.response_output.setPlaceholderText(
            "GisMark's response will appear here."
        )

        layout.addWidget(self.response_output)

    def search(self):
        prompt = self.prompt_input.toPlainText().strip()

        if not prompt:
            QMessageBox.warning(
                self,
                "GisMark",
                "Please enter a search prompt."
            )
            return

        self.response_output.clear()

        headers = {
            "Authorization": f"Bearer {API_KEY}",
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

            self.response_output.setPlainText(content)

            features = data.get("features", [])

            if features:
                geojson = {
                    "type": "FeatureCollection",
                    "features": features,
                }
                self.display_geojson(geojson)
           
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

    
    def display_geojson(self, geojson):
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
                f"GisMark - {name}s",
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
            extent = layers[0].extent()

            for layer in layers[1:]:
                extent.combineExtentWith(layer.extent())

            self.iface.mapCanvas().setExtent(extent)
            self.iface.mapCanvas().refresh()

            self.iface.setActiveLayer(layers[0])

       
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
