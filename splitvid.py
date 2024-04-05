import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QFileDialog, QComboBox, QMessageBox, QTableWidget, QTableWidgetItem, QGraphicsView
from PyQt5.QtGui import QColor
from PyQt5.QtCore import Qt, QObject, QThread, pyqtSignal
from gui import Ui_MainWindow  # Import the generated UI class
import os
import pickle
import subprocess
import json
from datetime import datetime
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from PyQt5.QtWidgets import QHBoxLayout, QVBoxLayout, QLabel, QWidget
import geopandas as gpd
from moviepy.editor import VideoFileClip
import geopandas as gpd
import folium
from shapely.geometry import LineString
       
            
class YourApplication(QMainWindow, Ui_MainWindow):
    def __init__(self, data = None):
        super().__init__()
        self.setupUi(self)  # Set up the UI from the generated code
        ## Setup the button clicks\
        self.selected_geojson_path = None
        self.selected_video_path = None
        self.points_in_line = {}
        self.shell={}
        self.init_ui()
        self.scrollLayout = QVBoxLayout()  # Create a QVBoxLayout to hold all the widgets
        self.scrollAreaWidgetContents.setLayout(self.scrollLayout)  # Set the QVBoxLayout as the layout for the scroll area
        
 
        
        
        
    def init_ui(self):
        """Initialize all of the buttons and other elements"""
        self.readMatchButton.setEnabled(False)
        self.calcGeomButton.setEnabled(False)
        self.splitFilesButton.setEnabled(False)
        self.readGeojsonButton.clicked.connect(self.select_folder)
        self.readVidsButton.clicked.connect(self.select_folder_2)
        self.readMatchButton.clicked.connect(self.read_match_files)
        self.calcGeomButton.clicked.connect(self.calculate_geometry)
        
    
    def read_match_files(self):
        ###Check if video path and geojson path has been selected
        ### Loop through the geojson folder location and create_details_tables based on it
        ###Populate the scrollArea
        if self.selected_geojson_path and self.selected_video_path:
            for serialnumber, filename in enumerate(os.listdir(self.selected_geojson_path)):
                if filename.endswith('.geojson'):
                    file_path = os.path.join(self.selected_geojson_path, filename)
                    length= self.get_length_in_meters(file_path)
                    # Match the video names
                    matched_vid_path = self.match_video_names_to_geojson(filename)
                    if matched_vid_path == "No Match Found":
                        vid_duration = "Invalid Video Length"
                    else:
                        vid_duration = self.get_video_length(matched_vid_path)
                    self.create_details_table(str(serialnumber+1), str(file_path), str(length.round(2)), matched_vid_path, vid_duration)
                    self.calcGeomButton.setEnabled(True)
        else:
            self.show_message_box('Unable to Process data', "Make sure the geojson folder path and the video folder path are selected first")
        
        
    def get_length_in_meters(self, filepath):
        gdf= gpd.read_file(filepath)
        if not gdf.empty and ('LineString' in gdf.geom_type.unique() or 'MultiLineString' in gdf.geom_type.unique()):
            # Set CRS to WGS84 if not already set
            if gdf.crs is None:
                gdf.crs = 'epsg:4326'  # WGS84

            # Reproject CRS to EPSG 32361
            gdf = gdf.to_crs(epsg=32631)

            # Calculate the length of all LineString and MultiLineString geometries and sum them up
            total_length = gdf.geometry.length.sum()

            return total_length
        
    def match_video_names_to_geojson(self, vidname):
        if self.selected_video_path:
            cleaned_vidname = vidname.replace(".geojson", "").lower()
            ## Check for the video name in video
            for vidname in os.listdir(self.selected_video_path):
                vid_path = os.path.join(self.selected_video_path, vidname)
                vname = vidname.replace('.mp4', "")
                cleaned_vname = vname.split("_")[0].replace(" ", "").lower()
                if cleaned_vidname == cleaned_vname:
                    return vid_path
            return "No Match Found"
                
        else:
            self.show_message_box('Video path not selected', "Can't find video paths....")
        

    def calculate_geometry(self):
        division_length = self.lineEdit.text()
        if division_length:
            try:
                division_length = float(division_length)
            except ValueError:
                self.show_message_box("Invalid division length", "Kindly enter a valid number...")
                return None
            
            # Iterate through each serial number in self.shell
            for sn, geojson_file in self.shell.items():
                # Convert coordinates to UTM projection
                gdf_utm = self.convert_coordinates(geojson_file)
                
                # Extract and join coordinates to form a LineString
                line = self.extract_and_join_coordinates(gdf_utm)
                # Divide LineString into points based on the division length
                divided_points, total_divisions = self.divide_linestring_by_interval(line, division_length)
                # Save the divided points into self.points_in_line dictionary
                self.points_in_line[sn] = divided_points
                self.create_details_table(str(total_divisions.round(2)))
                self.splitFilesButton.setEnabled(True)
                
        else:
            self.show_message_box("Division length is empty", "Kindly enter Division length in meters")
            
    def convert_coordinates(self, geojson_file):
        target_proj_params = {
            'proj': 'utm',
            'zone': 31,
            'south': True,
            'ellps': 'WGS84',
            'datum': 'WGS84',
            'units': 'm'
        }
        gdf = gpd.read_file(geojson_file)
        gdf_utm = gdf.to_crs(target_proj_params)
        return gdf_utm

    def extract_and_join_coordinates(self, gdf_utm):
        if len(gdf_utm) > 1:  # Check if there are multiple features
            features = gdf_utm['geometry']
        else:
            features = [gdf_utm.geometry.iloc[0]]  # If not, assume it's a single feature

        # Extract coordinates from each feature
        coordinates = []
        for geometry in features:
            if geometry.type == 'LineString':
                coordinates.extend(geometry.coords)
            elif geometry.type == 'MultiLineString':
                for line_string in geometry:
                    coordinates.extend(line_string.coords)

        # Remove Z values and create LineString object
        coordinates_2d = [(coord[0], coord[1]) for coord in coordinates]
        line = LineString(coordinates_2d)

        return line

    def divide_linestring_by_interval(self, line, division_length):

        # Calculate total length of the LineString
        total_length = line.length

        # Initialize list to store coordinates of divided points
        divided_points = []

        # Initialize distance along the LineString
        distance = 0

        # Initialize counter for total divisions
        total_divisions = 0

        # Iterate over the LineString and extract coordinates at specified intervals
        while distance <= total_length:
            # Interpolate point at current distance
            point = line.interpolate(distance)

            # Extract coordinates
            coordinates = point.coords[0]  # Extract coordinates as (x, y) tuple

            # Append coordinates to the list
            divided_points.append(coordinates)

            # Increment distance by the interval length
            distance += division_length

            # Increment total divisions counter
            total_divisions += 1

        return divided_points, total_divisions
        

    ## Def functions
    def select_folder(self):
        folder_path = QFileDialog.getExistingDirectory(self, "Select Directory")
        if folder_path:
            self.selectGeojsonLineEdit.setText(folder_path)
            self.selected_geojson_path = folder_path
            
            if self.selected_video_path and self.selected_geojson_path:
                self.readMatchButton.setEnabled(True)

            
    def select_folder_2(self):
        folder_path = QFileDialog.getExistingDirectory(self, "Select Directory")
        if folder_path:
            self.readVidsLineEdit.setText(folder_path)
            self.selected_video_path = folder_path
            
            if self.selected_video_path and self.selected_geojson_path:
                self.readMatchButton.setEnabled(True)
                
    def get_video_length(self,video_path):
            ## Function to get the video length..
            clip=VideoFileClip(video_path)
            duration=clip.duration
            clip.close()
            return duration
    
    def create_map(self, geojson_file, basemap='OpenStreetMap', zoom_start=18, line_color='black'):  
        # Function to create map using the geojason file inputted
        gdf = gpd.read_file(geojson_file)
        m = folium.Map(location=[gdf['geometry'].centroid.y.mean(), gdf['geometry'].centroid.x.mean()], zoom_start=zoom_start, tiles=basemap)

        # Add GeoJSON data to the map with custom line color
        folium.GeoJson(gdf, style_function=lambda x: {'color': line_color}).add_to(m)

        return m 
                
    def create_details_table(self, sn, filepath, length, vid_path, vid_length, total_divisions):
        # Create main layout
        main_layout = QHBoxLayout()
        main_layout.setSpacing(0)
        # Create Col_1 with numbers
        col_1_layout = QVBoxLayout()
        col_1_layout.setSpacing(0)
        label_col_1 = QLabel(str(sn))
        label_col_1.setFixedWidth(30)
        col_1_layout.addWidget(label_col_1)
        # Add your numbers widgets here
        main_layout.addLayout(col_1_layout)

        # Create Col_2 with four rows
        col_2_layout = QVBoxLayout()
        col_2_layout.setSpacing(0)
        # Row 1
        row_1_layout = QVBoxLayout()
        row_1_layout.addWidget(QLabel(f"Vid Path: {vid_path}"))
        col_2_layout.addLayout(row_1_layout)
        # Row 2
        row_2_layout = QHBoxLayout()
        row_2_layout.addWidget(QLabel(f"Geojson Filename: {filepath}"))
        row_2_layout.addWidget(QLabel(f"Vid Length: {vid_length}"))
        col_2_layout.addLayout(row_2_layout)
        # Row 3
        row_3_layout = QVBoxLayout()
        row_3_layout.addWidget(QLabel("Output File Dir: \t path_to_folder"))
        col_2_layout.addLayout(row_3_layout)
        # Row 4
        row_4_layout = QHBoxLayout()
        row_4_layout.addWidget(QLabel(f"{length}m"))
        row_4_layout.addWidget(QLabel(f"{total_divisions}"))
        row_4_layout.addWidget(QLabel("vvcol_3"))
        col_2_layout.addLayout(row_4_layout)

        main_layout.addLayout(col_2_layout)

        # Create Col_3 for map
        col_3_layout = QVBoxLayout()
        col_3_layout.setSpacing(0)
        col_3_layout.addWidget(QLabel("Col_3: Map Display"))
        # Add your map widget here
        main_layout.addLayout(col_3_layout)

        # Create a widget to contain the main layout
        main_widget = QWidget()
        main_widget.setLayout(main_layout)
        
        main_widget.setStyleSheet("border: 0.1px solid rgb(0, 0, 0)")
        scroll_area_width = self.scrollArea.width()
        
        main_widget.setFixedSize(scroll_area_width-20, 250)  # Set your desired width and height
        if int(sn) % 2 == 0:
            pass
        else:            
            main_widget.setStyleSheet("background-color: rgb(219, 243, 255);\n border: 0.1px solid rgb(0,0,0);")

        # Set the alignment of scrollLayout to top
        self.scrollLayout.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        
        # Set the main widget as the widget for the scroll area
        self.scrollLayout.addWidget(main_widget)
        self.shell[sn]={
            "filepath":filepath,
            "length":length,
            "vid_path":vid_path,
            "vid_length":vid_length
        }
