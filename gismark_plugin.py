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
        self.resize(420, 240)

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

    def search(self):
        prompt = self.prompt_input.toPlainText().strip()

        if not prompt:
            QMessageBox.warning(
                self,
                "GisMark",
                "Please enter a search prompt."
            )
            return

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

            result = json.dumps(
                data,
                indent=2,
                ensure_ascii=False,                
            )

            geojson = data.get("geojson")

            if geojson:
                self.display_geojson(geojson)
            else:
                QMessageBox.information(
                    self,
                    "GisMark API response",
                    result
                )                  
          
            
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
        # Create a temporary GeoJSON file.
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".geojson",
            encoding="utf-8",
            delete=False,
        ) as file:
            json.dump(geojson, file)
            file_path = file.name

        # Ask QGIS to load the file as a vector layer.
        layer = QgsVectorLayer(
            file_path,
            "GisMark results",
            "ogr",
        )

        if not layer.isValid():
            QMessageBox.warning(
                self,
                "GisMark",
                "QGIS could not load the GeoJSON data.",
            )
            return

        # Add the layer to the current QGIS project.
        QgsProject.instance().addMapLayer(layer)

        # Select the layer and zoom to its features.
        self.iface.setActiveLayer(layer)
        self.iface.zoomToActiveLayer()
        


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
