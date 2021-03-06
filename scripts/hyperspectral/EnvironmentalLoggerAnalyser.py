#!/usr/bin/env python

'''
EnvironmentalLoggerAnalyser.py

----------------------------------------------------------------------------------------
This module will read data generated by Environmental Sensor and convert to netCDF file
----------------------------------------------------------------------------------------
Prerequisite:
1. Python (2.7+ recommended)
2. netCDF4 module for Python (and many other supplements such as numpy, scipy and HDF5 if needed)
----------------------------------------------------------------------------------------

Usage:
python EnvironmentalLoggerAnalyser.py drc_in drc_out
python EnvironmentalLoggerAnalyser.py fl_in drc_out
where drc_in is input directory, drc_out is output directory, fl_in is input file
Input  filenames must have '.json' extension
Output filenames will have '.nc' extension

UCI test:
python ${HOME}/terraref/computing-pipeline/scripts/hyperspectral/EnvironmentalLoggerAnalyser.py ${DATA}/terraref/input ${DATA}/terraref/output

UCI production:
python ${HOME}/terraref/computing-pipeline/scripts/hyperspectral/EnvironmentalLoggerAnalyser.py ${DATA}/terraref/EnvironmentLogger/2016-04-07/2016-04-07_12-00-07_enviromentlogger.json ~/rgr

Roger production:
module add gdal-stack-2.7.10 
python ${HOME}/terraref/computing-pipeline/scripts/hyperspectral/EnvironmentalLoggerAnalyser.py /projects/arpae/terraref/raw_data/ua-mac/EnvironmentLogger/2016-04-07/2016-04-07_12-00-07_enviromentlogger.json ~/rgr

EnvironmentalLoggerAnalyser.py will take the second parameter as the input folder (containing JSON files,
but it can also be one single file) and the third parameter as the output folder (will dump netCDF files here).
If the output folder does not exist, EnvironmentalLoggerAnalyser.py will create it.

----------------------------------------------------------------------------------------
Update 4.29

The output JSON file is now completely composed by variables
2D spectrometer variables (wavelength and spectrum) are available in the exported file

Update 5.3

Add chuncksizes parameters for time, which significantly reduces the processing time (and the file size)
Add timestamps and commandLine the user used for each exported file
Remind the user currently the script is dealing with which file

TODO List:

1. reassign the variable "time" as the offset to the base time (temporary it is the UNIX base time)
----------------------------------------------------------------------------------------
Thanks for the advice from Professor Zender and testing data from Mr. Maloney
----------------------------------------------------------------------------------------
'''

import json
import time
import sys
import os
from netCDF4 import Dataset

_UNIT_DICTIONARY = {u'm': 'meter', u"hPa": "hecto-Pascal", u"DegCelsius": "Celsius",
                    u's': 'second', u'm/s': 'meter second-1', u"mm/h": 'milimeters hour-1',
                    u"relHumPerCent": "percent", u"?mol/(m^2*s)": "micromole meters-2 second-1",
                    u'kilo Lux': 'kilo Lux', u'degrees': 'degrees', '': ''}
_NAMES = {'sensor par': 'Sensor Photosynthetical Active Radiation'}


def formattingTheJSONFileAndReturnWavelengthAndSpectrum(fileLocation):
    '''
    This function will format the source JSON file including multiple JSON objects
    into a file of JSON array
    '''
    with open(fileLocation, 'r+') as fileHandler:
        tempList, linePosition, wavelengthList, spectrumList, j, k =\
            fileHandler.read().split('\n'), list(), [[]], [[]], 0, 0
        for i in range(len(tempList)):
            if "environment_sensor_set_reading" in tempList[i] and i > 2:
                linePosition.append(i - 1)
            if "wavelength" in tempList[i]:
                wavelengthList[j].append(
                    float(tempList[i][tempList[i].find(':') + 1: -2]))
            if "wavelength" not in tempList[i] and "wavelength" in tempList[i - 4]\
                    and "band" not in tempList[i] and "," not in tempList[i]:
                wavelengthList.append([])
                j += 1
                spectrumList.append([])
                k += 1
            if "spectrum" in tempList[i]:
                spectrumList[k].append(
                    float(tempList[i][tempList[i].find(':') + 1: -2]))

        wavelengthList.remove([])
        spectrumList.remove([])

        for line in linePosition:
            del tempList[line]
            tempList.insert(line, "},{")

        fileHandler.seek(0)
        fileHandler.truncate()

        if '[' not in tempList[0] and ']' not in tempList[-1]:
            tempList.insert(0, '[')
            tempList.append(']')
            fileHandler.write('\n'.join(tempList))
        else:
            fileHandler.write('\n'.join(tempList))
    return wavelengthList, spectrumList


def JSONHandler(fileLocation):
    '''
    Main JSON handler, write JSON file to a Python list with standard JSON module
    '''
    wavelength, spectrum = formattingTheJSONFileAndReturnWavelengthAndSpectrum(
        fileLocation)
    with open(fileLocation, 'r') as fileHandler:
        return json.loads(fileHandler.read()), wavelength, spectrum


def renameTheValue(name):
    '''
    Rename the value so it becomes legal in netCDF
    '''
    if type(name) is unicode:
        name = name.encode('ascii', 'ignore')
    if name in _UNIT_DICTIONARY:
        name = _UNIT_DICTIONARY[name]
    elif name in _NAMES:
        name = _NAMES[name]

    returningString = str()
    for letters in name:
        if letters == ' ':
            returningString += '_'
        else:
            returningString += letters
    return returningString


def getSpectrometerInformation(arrayOfJSON):
    '''
    Collect information from spectrometer with special care
    '''
    maxFixedIntensity = [int(intensityMembers["spectrometer"]["maxFixedIntensity"]) for intensityMembers in
                         arrayOfJSON]
    integrationTime = [int(integrateMembers["spectrometer"]["integration time in ?s"]) for integrateMembers in
                       arrayOfJSON]

    return maxFixedIntensity, integrationTime


def getListOfValue(arrayOfJSON, dataName):
    '''
    Collect data from JSON objects which have "value" member
    '''
    return [float(valueMembers[dataName]['value'].encode('ascii', 'ignore')) for valueMembers in arrayOfJSON]


def getListOfRawValue(arrayOfJSON, dataName):
    '''
    Collect data from JSON objects which have "rawValue" member
    '''
    return [float(valueMembers[dataName]['rawValue'].encode('ascii', 'ignore')) for valueMembers in arrayOfJSON]


def _timeStamp():
    return time.strftime("%a %b %d %H:%M:%S %Y",  time.localtime(int(time.time())))


def main(JSONArray, outputFileName, wavelength=None, spectrum=None, recordTime=None, commandLine=None):
    '''
    Main netCDF handler, write data to the netCDF file indicated.
    '''
    netCDFHandler = Dataset(outputFileName, 'w', format='NETCDF4')
    dataMemberList = [JSONMembers[u"environment_sensor_set_reading"]
                      for JSONMembers in JSONArray]
    timeStampList = [JSONMembers[u'timestamp']
                     for JSONMembers in dataMemberList]
    timeDimension = netCDFHandler.createDimension("time", None)
    tempTimeVariable = netCDFHandler.createVariable(
        'time', str, ('time',), chunksizes=(1,))
    for i in range(len(timeStampList)):  # Assign Times
        tempTimeVariable[i] = timeStampList[i]

    for data in dataMemberList[0]:
        if data != 'spectrometer' and type(dataMemberList[0][data]) not in (str, unicode):
            tempVariable = netCDFHandler.createVariable(
                renameTheValue(data), 'f4', ('time',))
            tempVariable[:] = getListOfValue(
                dataMemberList, data)  # Assign "values"
            if 'unit' in dataMemberList[0][data]:  # Assign Units
                setattr(tempVariable, 'units', _UNIT_DICTIONARY[
                        dataMemberList[0][data]['unit']])
            if 'rawValue' in dataMemberList[0][data]:  # Assign "rawValues"
                netCDFHandler.createVariable(renameTheValue(data) + '_rawValue', 'f4', ('time',))[:] =\
                    getListOfRawValue(dataMemberList, data)
        elif type(dataMemberList[0][data]) in (str, unicode):
            netCDFHandler.createVariable(renameTheValue(data), str)[
                0] = dataMemberList[0][data]

        if data == 'spectrometer':  # Special care for spectrometers :)
            netCDFHandler.createVariable('Spectrometer_maxFixedIntensity', 'f4', ('time',))[:] =\
                getSpectrometerInformation(dataMemberList)[0]
            netCDFHandler.createVariable('Spectrometer_Integration_Time_In_Microseconds', 'f4', ('time',))[:] =\
                getSpectrometerInformation(dataMemberList)[1]

    if wavelength and spectrum:
        netCDFHandler.createDimension("wavelength", len(wavelength[0]))
        netCDFHandler.createVariable("wavelength", 'f4', ('wavelength',))[
            :] = wavelength[0]
        netCDFHandler.createVariable("spectrum", 'f4', ('time', 'wavelength'))[
            :, :] = spectrum

    netCDFHandler.history = recordTime + ': python ' + commandLine
    netCDFHandler.close()


if __name__ == '__main__':
    fileInputLocation, fileOutputLocation = sys.argv[1], sys.argv[2]
    if not os.path.exists(fileOutputLocation):
        os.mkdir(fileOutputLocation)  # Create folder

    if not os.path.isdir(fileInputLocation):
        print "Processing", fileInputLocation + '....'
        tempJSONMasterList, wavelength, spectrum = JSONHandler(
            fileInputLocation)
        if not os.path.isdir(fileOutputLocation):
            main(tempJSONMasterList, fileOutputLocation, wavelength, spectrum,
                 _timeStamp(), sys.argv[1] + ' ' + sys.argv[2])
        else:
            outputFileName = os.path.split(fileInputLocation)[-1]
            main(tempJSONMasterList, os.path.join(fileOutputLocation,
                                                  outputFileName.strip('.json') + '.nc'), wavelength, spectrum,
                 _timeStamp(), sys.argv[1] + ' ' + sys.argv[2])
    else:  # Read and Export netCDF to folder
        for filePath, fileDirectory, fileName in os.walk(fileInputLocation):
            for members in fileName:
                if os.path.join(filePath, members).endswith('.json'):
                    print "Processing", members + '....'
                    outputFileName = members.strip('.json') + '.nc'
                    tempJSONMasterList, wavelength, spectrum = JSONHandler(
                        os.path.join(filePath, members))
                    main(tempJSONMasterList, os.path.join(
                        fileOutputLocation, outputFileName),
                        wavelength, spectrum, _timeStamp(), sys.argv[1] + ' ' + sys.argv[2])
