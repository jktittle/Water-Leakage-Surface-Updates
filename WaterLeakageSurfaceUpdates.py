#!/usr/bin/env python
# coding: utf-8
# # Script to Update Static Pressures and Interpolate Sample Pressure Points Using Ordinary Kriging
# ![image.png](attachment:image.png)
# **Import all necessary python packages**

import sys, os, csv, fiona, datetime, arcpy
import pandas as pd
import numpy as np
import geopandas as gp
from geopandas import GeoSeries, GeoDataFrame
from shapely.geometry import Point
import matplotlib.pyplot as plt
from arcpy import env
from arcpy.sa import *

# **Set the environment workspace and overwrite settings**


arcpy.env.overwriteOutput = True
arcpy.env.workspace = "C:\\StaticPressureProcess\\StaticPressureData.gdb"

# **Create variables for the pressure update csv, pressure test point file, and pressure zone polygon file**

pressureUpdateFile = "C:\\StaticPressureProcess\\TasksExport.csv"
pressurePoint = "C:\\StaticPressureProcess\\StaticPressureData.gdb\\PZ1838A_PressureTestPnts"
pressureZone = "C:\\StaticPressureProcess\\StaticPressureData.gdb\\PZ1838A_Redefined"
outRaster = "C:\\StaticPressureProcess\\StaticPressureData.gdb\\LeakSurface_" + datetime.date.today().strftime("%m%d%Y")
clippedRaster = "C:\\StaticPressureProcess\\StaticPressureData.gdb\\ClippedSurface_" + datetime.date.today().strftime("%m%d%Y")
redefined1838aDma = "C:\\StaticPressureProcess\\DMA1838A.shp"
geoStatModel = "C:\\StaticPressureProcess\\OrdinaryKrigingModel_1838A_TheBest.xml"
geoStatLayer = "KrigingOutLayer"

# **Read the TaskExport.csv and import into a pandas data frame**
# **Remove spaces from column names and replace them with "_"**

# **Use the fiona library to list all layers within the StaticPressureData geodatabase.  The list will be used to reference the layer imported with geopandas**
fiona.listlayers("C:\\StaticPressureProcess\\StaticPressureData.gdb")

# **Use geopandas to import the PZ1838_PressureTestPnts feature class as a geodataframe.  The layer parameter is taken from the list position of the desired geodatabase feature class**
testSites = gp.read_file("C:\\StaticPressureProcess\\StaticPressureData.gdb",driver='FileGDB', layer=3)
testSites

# **Standardize the DateCollected column**
testSites['DateCollected']=pd.to_datetime(testSites['DateCollected'])
testSites

staticUpdates = gp.read_file( "C:\\StaticPressureProcess\\TasksExport.csv")
staticUpdates

# **Add the FACILITYID column and slice the text to only display water hydrant identifiers.  Then, replace spaces with underscores and convert the Static_Pressure field to numeric values.**
staticUpdates['FACILITYID'] = staticUpdates.Asset.str[14:]
staticUpdates.columns = staticUpdates.columns.str.replace(' ', '_').str.replace('(', '').str.replace(')', '')
staticUpdates['Static_Pressure']=pd.to_numeric(staticUpdates.Static_Pressure)
staticUpdates

# **Standardize the Actual Stop Date column**
staticUpdates['Actual_Stop_Date']=pd.to_datetime(staticUpdates['Actual_Stop_Date'])
staticUpdates

# **Find and remove all rows with a Static_Pressure value equal to zero. This will remove
zeroStaticP = staticUpdates[ staticUpdates['Static_Pressure'] == 0 ].index
staticUpdates.drop(zeroStaticP , inplace=True)
staticUpdates

# **Join the staticUpdates data frame to the testSites data frame using the FACILITYID field.  This creates a new data frame that contains the static pressure updates to apply to the 1838A test hydrants**

mergedPressureInfo = testSites.merge(staticUpdates, on='FACILITYID')
mergedPressureInfo

# **Update new StaticPressure column, recalculate the Hydrograde column, and update the DateCollected column with new dates from the Actual_Stop_Date column.**

mergedPressureInfo.StaticPressure = mergedPressureInfo.Static_Pressure
mergedPressureInfo.HydroGrade = mergedPressureInfo.Elevation + 2.31 * mergedPressureInfo.StaticPressure
mergedPressureInfo.DateCollected = mergedPressureInfo.Actual_Stop_Date
mergedPressureInfo


# **Remove unneeded fields**
del mergedPressureInfo['Task_ID']
del mergedPressureInfo['Asset']
del mergedPressureInfo['Activity']
del mergedPressureInfo['Static_Pressure']
del mergedPressureInfo['Actual_Stop_Date']
del mergedPressureInfo['geometry_y']
mergedPressureInfo

mergedPressureInfo.rename(columns={"geometry_x":"geometry"}, inplace=True)
mergedPressureInfo


# **Get rid of duplicate values**
mergedPressureInfo = mergedPressureInfo.sort_values('DateCollected',ascending=True)
mergedPressureInfo = mergedPressureInfo.drop_duplicates(subset='FACILITYID', keep='first')
mergedPressureInfo = mergedPressureInfo.sort_values('FACILITYID',ascending=True)
mergedPressureInfo

# ## Update testSite values with the new static pressure test values**
# **Set the testSites index to the FACILITYID field**

testSites = testSites.set_index('FACILITYID')

testSites

# **Set the mergedPressureInfo index to the FACILITYID field**
mergedPressureInfo = mergedPressureInfo.set_index('FACILITYID')
mergedPressureInfo

# **Update new values in the testSites data frame using the update function, then reset the indexes**
testSites.update(mergedPressureInfo)

testSites.reset_index(inplace=True)

testSites

# **Convert the merged data frame to a GeoDataFrame and remove null HydroGrade Values**
updatedGdf = gp.GeoDataFrame(testSites, geometry='geometry')
NewGdf = updatedGdf[updatedGdf.HydroGrade.notnull()]
NewGdf

# **Convert the DateCollected column to string values in order to export to shapefile.**
NewGdf['DateCollected']=NewGdf['DateCollected'].astype(str)

# **Set the new geodataframe's projection and plot the new pressure tests within 1838A**
NewGdf.crs = {"init":"epsg:2274"}
updatedGdf.plot(figsize=(12,12));

# **Create new shapefile name and export the geodataframe to new shapefile**
shpFileName = r"C:\StaticPressureProcess\UpdatedStaticPressureTests_" + datetime.date.today().strftime("%m%d%Y") + ".shp"

NewGdf.to_file(shpFileName)

# **Check out ESRI extensions needed for the interpolation geoprocessing tools**
#Check out the ESRI Spatial and Geostatistical Analyst Extensions
arcpy.CheckOutExtension("Spatial")
arcpy.CheckOutExtension("GeoStats")

# **Run the Kriging interpolation using the pressure point layer.  This step creates a Geostatistical Layer using tools from Geostatistical Analyst.  The tool uses an existing Geostatistial layer as a model source to duplicate its parameters and should be stored in the project workspace.**
krigingInLayer = shpFileName + " X=Shape Y=Shape F1=HydroGrade"

#arcpy.GACreateGeostatisticalLayer_ga(in_ga_model_source, in_datasets, out_layer)
arcpy.GACreateGeostatisticalLayer_ga(geoStatModel, krigingInLayer, geoStatLayer)

#Export Geostatistical layer to a raster
arcpy.GALayerToRasters_ga(geoStatLayer, outRaster)

#Clip the interpolation surface to the desired DMA or pressure zone polygon boundary layer
arcpy.Clip_management(outRaster, "#",clippedRaster, redefined1838aDma,"0","ClippingGeometry")

#Check back in the ESRI Spatial and Geostatistical Analyst Extensions
arcpy.CheckInExtension("Spatial")
arcpy.CheckInExtension("GeoStats")

print("Completed Script")

